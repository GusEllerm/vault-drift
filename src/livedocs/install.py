"""`livedocs install-hooks`: Claude Code hook config, the git pre-commit hook, and the vault config."""

from __future__ import annotations

import json
import os
import stat
import sys
from pathlib import Path

UNKNOWN_JSON = json.dumps({"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext":
    "LIVE-DOCS: freshness check crashed before it could run. Treat any vault note you read as UNVERIFIED."}})
UNKNOWN_JSON_STOP = UNKNOWN_JSON.replace('"PostToolUse"', '"Stop"')


def _py() -> str:
    return sys.executable


def claude_hooks(repo: Path, timeout: int = 30) -> dict:
    py = _py()
    wrap = lambda mod, fallback: f"{py} -m livedocs.hooks.{mod} || printf '%s' '{fallback}'"
    return {
        "PostToolUse": [
            {"matcher": "Read", "hooks": [{"type": "command", "command": wrap("read_gate", UNKNOWN_JSON), "timeout": timeout}]},
            {"matcher": "Grep|Bash", "hooks": [{"type": "command", "command": f"{py} -m livedocs.hooks.bypass_log || true", "timeout": 10}]},
        ],
        "Stop": [
            {"hooks": [{"type": "command", "command": wrap("stop_heads_up", UNKNOWN_JSON_STOP), "timeout": timeout}]},
        ],
    }


def install_claude(repo: Path) -> Path:
    p = repo / ".claude" / "settings.json"
    p.parent.mkdir(exist_ok=True)
    cfg = json.loads(p.read_text()) if p.exists() else {}
    hooks = cfg.setdefault("hooks", {})
    for event, entries in claude_hooks(repo).items():
        existing = [e for e in hooks.get(event, []) if "livedocs" not in json.dumps(e)]
        hooks[event] = existing + entries
    p.write_text(json.dumps(cfg, indent=2) + "\n")
    return p


def install_git(repo: Path) -> Path:
    hook = repo / ".git" / "hooks" / "pre-commit"
    script = f"#!/bin/sh\n# livedocs pre-commit gate (D11)\nexec {_py()} -m livedocs.hooks.pre_commit\n"
    hook.write_text(script)
    hook.chmod(hook.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return hook


def install_config(repo: Path, vault_rel: str) -> Path:
    p = repo / ".livedocs" / "config.json"
    p.parent.mkdir(exist_ok=True)
    p.write_text(json.dumps({"vault": vault_rel}, indent=2) + "\n")
    return p
