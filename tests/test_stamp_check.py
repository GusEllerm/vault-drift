"""End-to-end stamp → check on the mini repo. Needs the drift binary; skipped otherwise."""

import shutil
import subprocess

import pytest

from livedocs import check as ck, stamp as stp, stamps as st

pytestmark = pytest.mark.skipif(shutil.which("drift") is None, reason="drift not installed")


def _git(repo, *a):
    subprocess.run(["git", "-C", str(repo), *a], check=True, capture_output=True)


def test_snapshot_notes_bind_nothing_and_never_block(mini_repo):
    repo, vault = mini_repo, "vault"
    for note in ("Reference/Review 2026-01-01.md", "Sessions/log.md"):  # glob-declared, frontmatter-declared
        r = stp.stamp(repo, vault, note, by="test")
        assert r.stamp.snapshot and r.stamp.bindings == {}
        rep = ck.check(repo, vault, note)
        assert rep.state == ck.SNAPSHOT and not ck.mechanically_benign(rep)
    a = repo / "src/pkg/a.py"
    a.write_text(a.read_text().replace("return x", "return -x"))  # baz changes; snapshots don't care
    assert ck.check(repo, vault, "Reference/Review 2026-01-01.md").state == ck.SNAPSHOT
    _git(repo, "checkout", "--", "src")


def test_verify_reports_unreconciled_notes(mini_repo):
    from livedocs import affected as af
    repo, vault = mini_repo, "vault"
    stp.stamp(repo, vault, "Modules/a.md", by="test")
    _git(repo, "add", "-A"); _git(repo, "commit", "-qm", "stamps")
    states = {r.note: r.state for r in af.verify(repo, vault)}
    assert states["Modules/a.md"] == ck.FRESH and states.get("Sessions/log.md") in (ck.SNAPSHOT, None)
    a = repo / "src/pkg/a.py"
    a.write_text(a.read_text().replace("CONST = 1", "CONST = 3"))
    _git(repo, "commit", "-qam", "no-verify style change")
    assert {r.note: r.state for r in af.verify(repo, vault)}["Modules/a.md"] == ck.CHANGED
    _git(repo, "reset", "-q", "--hard", "HEAD~1")


def test_constant_anchor_and_member_annotation(mini_repo):
    repo, vault = mini_repo, "vault"
    r = stp.stamp(repo, vault, "Modules/a.md", by="test")
    b = r.stamp.bindings
    # `CONST` binds the file, carrying its own member hash (P24); `Foo.bar` binds the class.
    assert "src/pkg/a.py" in b and "CONST" in b["src/pkg/a.py"].members
    assert "src/pkg/a.py#Foo" in b and {"Foo", "Foo.bar"} <= set(b["src/pkg/a.py#Foo"].members)
    _git(repo, "add", "-A"); _git(repo, "commit", "-qm", "stamps")
    assert ck.check(repo, vault, "Modules/a.md").state == ck.FRESH

    # Change the constant's value → changed(body) for CONST with was/now.
    a = repo / "src/pkg/a.py"
    a.write_text(a.read_text().replace("CONST = 1", "CONST = 2"))
    rep = ck.check(repo, vault, "Modules/a.md")
    kinds = {(f.qualname, f.kind) for f in rep.findings}
    assert rep.state == ck.CHANGED and ("CONST", "body") in kinds
    const = next(f for f in rep.findings if f.qualname == "CONST")
    assert "CONST = 1" in const.was and "CONST = 2" in const.now
    assert not ck.mechanically_benign(rep)

    # A line added inside a module-level string constant: drift's file fingerprint misses this
    # (1b t5); the member hash must catch it on its own.
    a.write_text(a.read_text().replace("CONST = 2", "CONST = 1").replace("engine:\n  type: x", "engine:\n  label: y\n  type: x"))
    rep = ck.check(repo, vault, "Modules/a.md")
    assert rep.state == ck.CHANGED and ("TEMPLATE", "body") in {(f.qualname, f.kind) for f in rep.findings}
    assert not ck.mechanically_benign(rep)
    a.write_text(a.read_text().replace("engine:\n  label: y\n  type: x", "engine:\n  type: x").replace("CONST = 1", "CONST = 2"))

    # Revert; edit an unmentioned method's body → annotation only, mechanically benign.
    a.write_text(a.read_text().replace("CONST = 2", "CONST = 1").replace("return 0", "return 9"))
    rep = ck.check(repo, vault, "Modules/a.md")
    assert rep.state == ck.CHANGED and all(f.kind == "unchanged" for f in rep.findings)
    assert ck.mechanically_benign(rep)
    assert any("changed elsewhere" in f.detail for f in rep.findings)
    # and with refine=True the same edit is suppressed entirely
    assert ck.check(repo, vault, "Modules/a.md", refine=True).state == ck.FRESH

    # Ack rules: ack needs a reason; update on an unchanged body is refused.
    with pytest.raises(stp.StampError):
        stp.stamp(repo, vault, "Modules/a.md", by="test", verdict=st.ACK)
    with pytest.raises(stp.StampError):
        stp.stamp(repo, vault, "Modules/a.md", by="test")
    stp.stamp(repo, vault, "Modules/a.md", by="test", verdict=st.ACK, reason="sibling method only")
    assert ck.check(repo, vault, "Modules/a.md").state == ck.FRESH
    _git(repo, "checkout", "--", "src")
