"""The Claude Code hook commands `livedocs init` writes, run under `sh` with a PATH that lacks livedocs
(resumed and GUI-launched sessions often have no ~/.local/bin)."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from livedocs import install

BARE_PATH = "/usr/bin:/bin"


def _fake(d: Path, body: str) -> Path:
    d.mkdir(parents=True, exist_ok=True)
    p = d / "livedocs"
    p.write_text(f"#!/bin/sh\n{body}\n")
    p.chmod(0o755)
    return p


def _run(cmd: str, home: Path) -> str:
    r = subprocess.run(["sh", "-c", cmd], input="{}", capture_output=True, text=True,
                       env={"PATH": BARE_PATH, "HOME": str(home)})
    assert r.returncode == 0, r.stderr
    return r.stdout


def _stop(pinned: str | None = None) -> str:
    return install.claude_hooks(read_gate=True, bypass_log=True, pinned=pinned)["Stop"][0]["hooks"][0]["command"]


def test_pinned_launcher_found_off_path(tmp_path):
    exe = _fake(tmp_path / "some bin", "echo ran \"$@\"")
    assert _run(_stop(str(exe)), tmp_path / "home") == "ran hook stop\n"


def test_home_local_bin_found_off_path(tmp_path):
    home = tmp_path / "home"
    _fake(home / ".local" / "bin", "echo ran \"$@\"")
    assert _run(_stop(), home) == "ran hook stop\n"


def test_stop_not_found_is_a_user_message_not_context(tmp_path):
    out = json.loads(_run(_stop(str(tmp_path / "gone" / "livedocs")), tmp_path / "home"))
    # additionalContext on Stop starts a new turn; a missing launcher then loops every reply
    assert set(out) == {"systemMessage"}
    assert "not found" in out["systemMessage"]


def test_stop_crash_is_a_user_message(tmp_path):
    exe = _fake(tmp_path / "bin", "exit 1")
    out = json.loads(_run(_stop(str(exe)), tmp_path / "home"))
    assert set(out) == {"systemMessage"} and "crashed" in out["systemMessage"]


def test_read_gate_fallback_stays_context(tmp_path):
    hooks = install.claude_hooks(read_gate=True, bypass_log=True)
    cmd = hooks["PostToolUse"][0]["hooks"][0]["command"]
    out = json.loads(_run(cmd, tmp_path / "home"))
    ctx = out["hookSpecificOutput"]["additionalContext"]
    assert "not found" in ctx and "UNVERIFIED" in ctx


def test_bypass_log_silent_when_missing(tmp_path):
    cmd = install.claude_hooks(read_gate=False, bypass_log=True)["PostToolUse"][0]["hooks"][0]["command"]
    assert _run(cmd, tmp_path / "home") == ""


def test_shared_settings_carry_no_machine_path(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    local = json.loads(install.install_claude(tmp_path).read_text())
    shared = json.loads(install.install_claude(tmp_path, shared=True).read_text())
    launcher = install._launcher()
    if launcher:
        assert launcher in json.dumps(local)
        assert launcher not in json.dumps(shared)
    assert "$HOME/.local/bin/livedocs" in json.dumps(shared)
