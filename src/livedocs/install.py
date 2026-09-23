"""`livedocs init` / `install-hooks`: the git gate (D14), the Claude Code adapter, and the vault config.

The guarantee is a mechanism of the development framework, not a capability of the agent:
  - Tier 0 (always): a versioned pre-commit hook in .githooks/ activated with `core.hooksPath`, plus the
    same check in CI. Works for any agent or human; only needs git and `livedocs` on PATH.
  - Tier 1 (recommended): the Claude Code Stop heads-up, in the user's settings.local.json by default
    (--shared writes the project settings.json). Non-blocking; injects note names and states only.
  - Tier 2 (opt-in, --read-gate): the read-time gate.
  - Tier 3 (measurement, --bypass-log): telemetry for experiments, never a default.
Hook commands call `livedocs hook <name>` resolved on PATH, never an absolute interpreter path.
"""

from __future__ import annotations

import json
import shutil
import stat
import subprocess
from pathlib import Path

UNVERIFIED = "LIVE-DOCS: freshness check crashed before it could run. Treat any vault note you read as UNVERIFIED."


def _fallback(event: str) -> str:
    return json.dumps({"hookSpecificOutput": {"hookEventName": event, "additionalContext": UNVERIFIED}})


def _cmd(name: str, event: str | None = None) -> str:
    """Fail closed: if livedocs is missing or crashes, the agent still gets an explicit line."""
    base = f"livedocs hook {name}"
    if event is None:
        return f"{base} || true"
    return f"{base} || printf '%s' '{_fallback(event)}'"


def claude_hooks(*, read_gate: bool, bypass_log: bool, timeout: int = 30) -> dict:
    hooks: dict = {"Stop": [{"hooks": [{"type": "command", "command": _cmd("stop", "Stop"), "timeout": timeout}]}]}
    post = []
    if read_gate:
        post.append({"matcher": "Read", "hooks": [{"type": "command", "command": _cmd("read-gate", "PostToolUse"), "timeout": timeout}]})
    if bypass_log:
        post.append({"matcher": "Grep|Bash", "hooks": [{"type": "command", "command": _cmd("bypass-log"), "timeout": 10}]})
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
    for event, entries in claude_hooks(read_gate=read_gate, bypass_log=bypass_log).items():
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

Notes under `{vault}/` are bound to the code they mention. A pre-commit gate blocks any commit that
changes code a note mentions until that note is reconciled: edit it and run `livedocs stamp <note>`, or
if it is still correct run `livedocs stamp <note> --ack --reason "<why>"`, then stage `drift.lock` and
`{vault}/.livedocs/stamps.jsonl`. `livedocs affected` lists the notes your uncommitted changes touch.
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
