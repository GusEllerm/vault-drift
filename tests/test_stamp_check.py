"""End-to-end stamp → check on the mini repo. Needs the drift binary; skipped otherwise."""

import shutil
import subprocess

import pytest

from livedocs import check as ck, stamp as stp, stamps as st

pytestmark = pytest.mark.skipif(shutil.which("drift") is None, reason="drift not installed")


def _git(repo, *a):
    subprocess.run(["git", "-C", str(repo), *a], check=True, capture_output=True)


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
