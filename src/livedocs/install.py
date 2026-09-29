"""`livedocs init` / `install-hooks`: the git gate (D14), the Claude Code adapter, and the vault config.

The guarantee is a mechanism of the development framework, not a capability of the agent:
  - Tier 0 (always): a versioned pre-commit hook in .githooks/ activated with `core.hooksPath`, plus the
    same check in CI. Works for any agent or human; only needs git and `livedocs` on PATH.
  - Tier 1 (recommended): the Claude Code Stop heads-up, in the user's settings.local.json by default
    (--shared writes the project settings.json). Non-blocking; injects note names and states only.
  - Tier 2 (opt-in, --read-gate): the read-time gate.
  - Tier 3 (measurement, --bypass-log): telemetry for experiments, never a default.
Hook commands resolve `livedocs` on PATH first, never via an interpreter path. Sessions that are resumed
or launched from a GUI often lack ~/.local/bin on PATH, so the command then tries the launcher found at
init time (local settings only) and $HOME/.local/bin. The Stop fallback is a systemMessage (shown to the
user): additionalContext on Stop starts a new turn, so a failing hook would loop.
"""

from __future__ import annotations

import json
import shlex
import shutil
import stat
import subprocess
import sys
from pathlib import Path

NOT_FOUND = ("LIVE-DOCS: `livedocs` was not found (not on PATH or in ~/.local/bin), so the freshness check did not run. "
             "Install it (uv tool install livedocs) or re-run `livedocs init`.")
CRASHED = "LIVE-DOCS: freshness check crashed before it could run."
UNVERIFIED = " Treat any vault note you read as UNVERIFIED."


def _fallback(event: str, msg: str) -> str:
    assert "'" not in msg  # the command wraps this JSON in single quotes
    if event == "Stop":
        return json.dumps({"systemMessage": msg})
    return json.dumps({"hookSpecificOutput": {"hookEventName": event, "additionalContext": msg + UNVERIFIED}})


def _launcher() -> str | None:
    """The `livedocs` launcher running now: PATH's, else argv[0] if it is one. Not resolved through
    symlinks, so a uv/pipx shim stays a shim and survives upgrades."""
    found = shutil.which("livedocs")
    if found:
        return str(Path(found).absolute())
    argv0 = Path(sys.argv[0])
    return str(argv0.absolute()) if argv0.name == "livedocs" and argv0.exists() else None


def _cmd(name: str, event: str | None = None, *, pinned: str | None = None) -> str:
    """Fail closed: if livedocs is missing or crashes, the agent (or on Stop, the user) gets an explicit line."""
    cands = ["livedocs"] + ([shlex.quote(pinned)] if pinned else []) + ['"$HOME/.local/bin/livedocs"']
    find = "L=$(" + " || ".join(f"command -v {c}" for c in cands) + ")"
    if event is None:
        return f'{find}; [ -z "$L" ] || "$L" hook {name} || true'
    return (f'{find}; if [ -z "$L" ]; then printf \'%s\' \'{_fallback(event, NOT_FOUND)}\'; '
            f'else "$L" hook {name} || printf \'%s\' \'{_fallback(event, CRASHED)}\'; fi')


def claude_hooks(*, read_gate: bool, bypass_log: bool, timeout: int = 30, pinned: str | None = None) -> dict:
    hooks: dict = {"Stop": [{"hooks": [{"type": "command", "command": _cmd("stop", "Stop", pinned=pinned), "timeout": timeout}]}]}
    post = []
    if read_gate:
        post.append({"matcher": "Read", "hooks": [{"type": "command", "command": _cmd("read-gate", "PostToolUse", pinned=pinned), "timeout": timeout}]})
    if bypass_log:
        post.append({"matcher": "Grep|Bash", "hooks": [{"type": "command", "command": _cmd("bypass-log", pinned=pinned), "timeout": 10}]})
    if post:
        hooks["PostToolUse"] = post
    return hooks


def install_claude(repo: Path, *, shared: bool = False, read_gate: bool = False, bypass_log: bool = False) -> Path:
    p = repo / ".claude" / ("settings.json" if shared else "settings.local.json")
    p.parent.mkdir(exist_ok=True)
    cfg = json.loads(p.read_text()) if p.exists() else {}
    hooks = cfg.setdefault("hooks", {})
    # replace any earlier livedocs entries, keep everything else
    for event in list(hooks):
        hooks[event] = [e for e in hooks[event] if "livedocs" not in json.dumps(e)]
        if not hooks[event]:
            del hooks[event]
    # a shared (committed) settings.json must not carry this machine's paths
    pinned = None if shared else _launcher()
    for event, entries in claude_hooks(read_gate=read_gate, bypass_log=bypass_log, pinned=pinned).items():
        hooks.setdefault(event, []).extend(entries)
    p.write_text(json.dumps(cfg, indent=2) + "\n")
    return p


PRE_COMMIT = """#!/bin/sh
# livedocs: block the commit while a staged code change leaves a vault note unreconciled (D11/D14).
# Versioned in .githooks/; activated per clone with `git config core.hooksPath .githooks`
# (livedocs init does this). Skipping with --no-verify is caught by the same check in CI.
if ! command -v livedocs >/dev/null 2>&1; then
  echo "livedocs: not on PATH; install it (uv tool install livedocs) or commit with --no-verify." >&2
  exit 1
fi
exec livedocs hook pre-commit
"""


def install_git(repo: Path) -> Path:
    d = repo / ".githooks"
    d.mkdir(exist_ok=True)
    hook = d / "pre-commit"
    hook.write_text(PRE_COMMIT)
    hook.chmod(hook.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    subprocess.run(["git", "-C", str(repo), "config", "core.hooksPath", ".githooks"], check=True)
    return hook


SCANNER_PATHS = ("drift.lock", "**/.livedocs/stamps.jsonl")
_GG_COMMENT = ("# livedocs: drift.lock and stamps.jsonl hold fingerprints (hashes) of this repository's own code.\n"
               "# They grant access to nothing; secret scanners misread them as high-entropy secrets.\n")


def install_gitguardian(repo: Path, vault_rel: str, extra: tuple[str, ...] = ()) -> tuple[Path, bool]:
    """Add livedocs' fingerprint files to .gitguardian.yaml's secret.ignored_paths (read by ggshield:
    hooks and CI). Creates the file, or inserts into an existing one without a YAML dependency.
    Returns (path, changed)."""
    paths = [*SCANNER_PATHS, f"{vault_rel}/.livedocs/stamps.jsonl", *extra]
    p = repo / ".gitguardian.yaml"
    if not p.exists():
        items = "".join(f"    - '{x}'\n" for x in paths)
        p.write_text(f"{_GG_COMMENT}version: 2\nsecret:\n  ignored_paths:\n{items}")
        return p, True
    text = p.read_text()
    missing = [x for x in paths if x not in text]
    if not missing:
        return p, False
    lines = text.splitlines(keepends=True)
    import re as _re
    ip = next((i for i, l in enumerate(lines) if _re.match(r"^\s*ignored_paths:\s*$", l)), None)
    if ip is not None:
        ind = len(lines[ip]) - len(lines[ip].lstrip())
        # match the indent of the first existing item if any, else two deeper than the key
        item_ind = next((len(l) - len(l.lstrip()) for l in lines[ip + 1:] if l.strip().startswith("-")), ind + 2)
        lines[ip + 1:ip + 1] = [" " * item_ind + f"- '{x}'\n" for x in missing]
    else:
        sp = next((i for i, l in enumerate(lines) if _re.match(r"^secret:\s*$", l)), None)
        block = ["  ignored_paths:\n"] + [f"    - '{x}'\n" for x in missing]
        if sp is not None:
            lines[sp + 1:sp + 1] = block
        else:
            if lines and not lines[-1].endswith("\n"):
                lines[-1] += "\n"
            lines += ["secret:\n"] + block
    p.write_text(_GG_COMMENT + "".join(lines) if "livedocs:" not in text else "".join(lines))
    return p, True


def install_config(repo: Path, vault_rel: str) -> Path:
    p = repo / ".livedocs" / "config.json"
    p.parent.mkdir(exist_ok=True)
    cfg = json.loads(p.read_text()) if p.exists() else {}
    cfg["vault"] = vault_rel
    # P25: dated records bind nothing. Add vault-relative globs here (or `livedocs: snapshot` in a
    # note's frontmatter); e.g. ["Reference/Review *", "Sessions/*"].
    cfg.setdefault("snapshot_globs", [])
    p.write_text(json.dumps(cfg, indent=2) + "\n")
    # The vault's cache (audit and bypass logs, symbol caches) is per-machine noise; keep it out of git
    # so agents never see it as an unexplained modified file (a 1b finding).
    vd = repo / vault_rel / ".livedocs"
    vd.mkdir(parents=True, exist_ok=True)
    gi = vd / ".gitignore"
    if not gi.exists() or "cache/" not in gi.read_text():
        gi.write_text((gi.read_text() if gi.exists() else "") + "cache/\n")
    return p


AGENTS_BLOCK = """
## Live documentation (livedocs)

Notes under `{vault}/` are bound to the code they mention (names in backticks). A pre-commit gate blocks
any commit that changes code a note mentions until the note is reconciled: edit the note and commit
again (the commit stamps it), or if the note is still correct run
`livedocs stamp <note> --ack --reason "<why>"`, `git add -A`, and commit. New and edited notes are stamped
by the commit that contains them; nothing else to run. `livedocs affected` lists the notes your
uncommitted changes touch; `livedocs coverage` shows which claims are anchored.
"""


def install_agents_block(repo: Path, vault_rel: str) -> Path | None:
    """Append the instruction block to AGENTS.md or CLAUDE.md if one exists and doesn't have it (channel 3)."""
    for name in ("AGENTS.md", "CLAUDE.md"):
        p = repo / name
        if p.exists():
            text = p.read_text()
            if "livedocs" not in text:
                p.write_text(text.rstrip("\n") + "\n" + AGENTS_BLOCK.format(vault=vault_rel))
            return p
    return None


def check_drift() -> str | None:
    return shutil.which("drift")
