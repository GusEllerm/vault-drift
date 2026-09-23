"""Subprocess wrapper for drift (v0.10.x) and a drift.lock reader."""

from __future__ import annotations

import json
import re
import subprocess
import tomllib
from pathlib import Path

TIMEOUT = 20
_SIG = re.compile(r"sig:([0-9a-f]+)")


class DriftError(RuntimeError):
    pass


def _run(repo: str | Path, *args: str) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(["drift", *args], cwd=str(repo), capture_output=True, text=True, timeout=TIMEOUT)
    except FileNotFoundError as e:
        raise DriftError("drift binary not found") from e
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


def lock(repo: str | Path, lock_path: str = "drift.lock") -> dict[tuple[str, str], str]:
    p = Path(repo) / lock_path
    if not p.exists():
        return {}
    data = tomllib.loads(p.read_text(encoding="utf-8"))
    return {(b["doc"], b["target"]): b["sig"] for b in data.get("bindings", ())}
