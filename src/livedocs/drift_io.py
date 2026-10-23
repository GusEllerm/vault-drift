"""Subprocess wrapper for drift (v0.10.x) and a drift.lock reader."""

from __future__ import annotations

import functools
import json
import os
import re
import shutil
import subprocess
import tomllib
from pathlib import Path

TIMEOUT = 20
_SIG = re.compile(r"sig:([0-9a-f]+)")


class DriftError(RuntimeError):
    pass


class DriftMissing(DriftError):
    """drift is not installed (or not findable): nothing can be bound or checked. Never a per-binding failure."""


_DIRS = ("~/.local/bin", "/opt/homebrew/bin", "/usr/local/bin")  # drift's installer, Homebrew


@functools.cache
def binary() -> str:
    """The drift executable: $LIVEDOCS_DRIFT, PATH, this clone's `git config livedocs.drift` (written by
    init), then the usual install directories. GUI apps (the Obsidian Git plugin) run hooks with
    PATH=/usr/bin:/bin, where a Homebrew drift is invisible."""
    env = os.environ.get("LIVEDOCS_DRIFT")
    cands = [env] if env else []
    cands.append(shutil.which("drift"))
    try:
        cands.append(subprocess.run(["git", "config", "--get", "livedocs.drift"], capture_output=True,
                                    text=True, timeout=10).stdout.strip())
    except (OSError, subprocess.TimeoutExpired):
        pass
    cands += [str(Path(d).expanduser() / "drift") for d in _DIRS]
    for c in cands:
        if c and os.path.isfile(c) and os.access(c, os.X_OK):
            return c
    raise DriftMissing("drift not found (PATH, LIVEDOCS_DRIFT, git config livedocs.drift, ~/.local/bin, "
                       "/opt/homebrew/bin, /usr/local/bin); install it: brew install fiberplane/tap/drift")


def _run(repo: str | Path, *args: str) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run([binary(), *args], cwd=str(repo), capture_output=True, text=True, timeout=TIMEOUT)
    except FileNotFoundError as e:
        raise DriftMissing("drift binary not found") from e
    except subprocess.TimeoutExpired as e:
        raise DriftError(f"drift {args[0]} timed out") from e


def link(repo: str | Path, doc: str, target: str) -> str:
    """Bind doc → target and return the sig. Always vouches, so re-links aren't refused;
    the note hash in our stamp carries the real "author verified this" semantics."""
    p = _run(repo, "link", doc, target, "--doc-is-still-accurate")
    out = (p.stdout + p.stderr).strip()
    m = _SIG.search(out)
    # Match drift's own prefixes, not substrings: a symbol may be called _explain_provision_error.
    bad = any(l.startswith(("error:", "refused")) for l in out.splitlines())
    if p.returncode != 0 or bad or not m:
        raise DriftError(out or f"drift link {target} failed")
    return m.group(1)


def unlink(repo: str | Path, doc: str, target: str) -> None:
    p = _run(repo, "unlink", doc, target)
    if p.returncode != 0:
        raise DriftError((p.stdout + p.stderr).strip())


def check_json(repo: str | Path) -> dict:
    p = _run(repo, "check", "--format", "json")
    try:
        return json.loads(p.stdout)
    except json.JSONDecodeError as e:
        raise DriftError(f"drift check: bad JSON ({(p.stderr or p.stdout)[:200]})") from e


def anchors_for(check: dict, doc: str) -> list[dict] | None:
    """Anchor entries for one doc from check_json output, or None if drift didn't list it."""
    for d in check.get("docs", ()):
        if d.get("path") == doc:
            return list(d.get("anchors", ()))
    return None


BROKEN_CODES = frozenset({"symbol_not_found", "file_not_found"})


_LOCKS: dict[str, tuple[tuple[int, int, int], dict[tuple[str, str], str]]] = {}


def lock(repo: str | Path, lock_path: str = "drift.lock") -> dict[tuple[str, str], str]:
    """drift.lock as {(doc, target): sig}. Parsed once per version of the file: the gate and the checks
    read it for every note, and a vault with ~1,500 bindings takes ~30 ms to parse."""
    p = Path(repo) / lock_path
    try:
        stt = p.stat()
    except FileNotFoundError:
        return {}
    key, version = str(p.resolve()), (stt.st_ino, stt.st_mtime_ns, stt.st_size)
    hit = _LOCKS.get(key)
    if hit is None or hit[0] != version:
        data = tomllib.loads(p.read_text(encoding="utf-8"))
        hit = (version, {(b["doc"], b["target"]): b["sig"] for b in data.get("bindings", ())})
        _LOCKS[key] = hit
    return dict(hit[1])
