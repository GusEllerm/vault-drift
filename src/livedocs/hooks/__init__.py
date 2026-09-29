"""Claude Code hook entry points and the git pre-commit gate.

Every hook fails closed: any exception or timeout inside produces an explicit `unknown` line for
the agent instead of silence. The shell wrapper installed by `livedocs install-hooks` adds a second
layer for a missing launcher, import errors and interpreter crashes (see install._cmd).
"""

from __future__ import annotations

import json
import os
import signal
import sys
from pathlib import Path

DEADLINE_S = 15
UNKNOWN_CONTEXT = "LIVE-DOCS: freshness check failed to run ({why}). Treat any vault note you read as UNVERIFIED."


def read_input() -> dict:
    try:
        return json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError:
        return {}


def emit(event: str, context: str) -> None:
    print(json.dumps({"hookSpecificOutput": {"hookEventName": event, "additionalContext": context}}))


def arm_deadline(event: str) -> None:
    def _timeout(signum, frame):
        emit(event, UNKNOWN_CONTEXT.format(why=f"timed out after {DEADLINE_S}s"))
        sys.stdout.flush()
        os._exit(0)
    signal.signal(signal.SIGALRM, _timeout)
    signal.alarm(DEADLINE_S)


def repo_root(cwd: str | None) -> Path:
    from .. import gitx
    p = Path(cwd or os.getcwd())
    return Path(gitx.run(p, "rev-parse", "--show-toplevel").strip())


def vault_rel_for(repo: Path) -> str | None:
    """The vault path, from LIVEDOCS_VAULT or a .livedocs/config.json at the repo root."""
    env = os.environ.get("LIVEDOCS_VAULT")
    if env:
        return env.strip("/")
    cfg = repo / ".livedocs" / "config.json"
    if cfg.exists():
        try:
            return json.loads(cfg.read_text()).get("vault", "").strip("/") or None
        except json.JSONDecodeError:
            return None
    return None


def in_vault(path: str, repo: Path, vault_rel: str) -> str | None:
    """Vault-relative note path if `path` is a markdown note inside the vault, else None."""
    try:
        rel = Path(path).resolve().relative_to((repo / vault_rel).resolve())
    except (ValueError, OSError):
        return None
    s = str(rel)
    if not s.endswith(".md") or s.startswith(".livedocs") or s.startswith(".obsidian"):
        return None
    return s
