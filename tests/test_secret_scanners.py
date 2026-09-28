"""Stamps must not look like secrets to scanners (GitGuardian flagged a user's stamps.jsonl, 2026-09-28)."""

import json
import re

from livedocs import install, stamps as st

# The exact line GitGuardian flagged (stamp format v1), trimmed to the relevant binding.
V1_LINE = json.dumps({
    "note": "Modules/ALCF Gateway.md", "note_hash": "sha256:" + "41a9" * 16,
    "bindings": {"benchmark/src/smbench/alcf/auth.py#get_access_token": {
        "sig": "5d95c969dc260ad9", "deco": "", "qualnames": ["get_access_token"],
        "members": {"get_access_token": "4bda567785f5c517"}}},
    "mentions": {"benchmark/src/smbench/alcf/auth.py#get_access_token": [["get_access_token", 26]]},
    "unresolved": [], "stamped": "2026-09-28T14:37:48Z", "by": "human", "verdict": "ack",
    "reason": "r", "dangling": [], "snapshot": False})

# A secret-ish key mapped straight to a bare hex string: the shape generic detectors match.
SECRET_SHAPE = re.compile(r'"[^"]*(token|secret|key|password|passwd|auth|sig)[^"]*"\s*:\s*"[0-9a-f]{12,}"', re.I)


def test_v1_line_is_what_scanners_flag_and_still_reads():
    assert SECRET_SHAPE.search(V1_LINE)  # sanity: the regex reproduces the incident
    s = st.Stamp.from_json(V1_LINE)
    b = s.bindings["benchmark/src/smbench/alcf/auth.py#get_access_token"]
    assert b.sig == "5d95c969dc260ad9" and b.members == {"get_access_token": "4bda567785f5c517"}


def test_v2_line_has_no_secret_shape_and_round_trips():
    s = st.Stamp.from_json(V1_LINE)
    out = s.to_json()
    assert not SECRET_SHAPE.search(out), out
    assert '"v":2' in out and '"drift:5d95c969dc260ad9"' in out and '["get_access_token","ast:4bda567785f5c517"]' in out
    back = st.Stamp.from_json(out)
    assert back == s  # internal representation unchanged: raw hex, members as a dict


def test_gitguardian_config_created_and_merged(tmp_path):
    p, changed = install.install_gitguardian(tmp_path, "docs/vault")
    text = p.read_text()
    assert changed and "version: 2" in text and "'drift.lock'" in text and "'**/.livedocs/stamps.jsonl'" in text
    assert install.install_gitguardian(tmp_path, "docs/vault") == (p, False)  # idempotent

    existing = tmp_path / "other"
    existing.mkdir()
    (existing / ".gitguardian.yaml").write_text("version: 2\nsecret:\n  ignored_paths:\n    - 'fixtures/*'\n  show_secrets: false\n")
    p2, changed2 = install.install_gitguardian(existing, "vault")
    t2 = p2.read_text()
    assert changed2 and "    - 'fixtures/*'" in t2 and "    - 'drift.lock'" in t2 and "  show_secrets: false" in t2
    assert t2.count("ignored_paths:") == 1 and t2.count("secret:") == 1
