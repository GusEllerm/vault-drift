"""End-to-end on the TS fixture: stamp → check → the pre-commit gate. Needs drift; skipped otherwise."""

import os
import shutil
import subprocess

import pytest

from livedocs import check as ck, stamp as stp, stamps as st
from livedocs.hooks import pre_commit

pytestmark = pytest.mark.skipif(shutil.which("drift") is None, reason="drift not installed")
V = "vault"


def _git(repo, *a):
    return subprocess.run(["git", "-C", str(repo), *a], check=True, capture_output=True, text=True).stdout


def _stamp_all(repo):
    for n in ("Modules/util.md", "Modules/components.md", "Concepts/deploy.md"):
        stp.stamp(repo, V, n, by="test")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "stamps")


def _edit(repo, rel, old, new):
    p = repo / rel
    assert old in p.read_text(), old
    p.write_text(p.read_text().replace(old, new))


def test_bindings_follow_symbols_not_module_paths(ts_repo):
    r = stp.stamp(ts_repo, V, "Modules/util.md", by="test")
    b = r.stamp.bindings
    assert not r.failed
    # `src/lib/util.ts` (a module path, no default export) binds nothing by itself (P29) ...
    assert "src/lib/util.ts" not in b
    # ... its symbols bind at drift's symbol granularity with their own member hashes.
    assert set(b) == {"src/lib/util.ts#add", "src/lib/util.ts#mul", "src/lib/util.ts#Box",
                      "src/lib/util.ts#config", "src/lib/util.ts#Props"}
    assert set(b["src/lib/util.ts#Box"].members) == {"Box.area", "Box.w"}
    assert set(b["src/lib/util.ts#config"].members) == {"config.theme.color"}
    r = stp.stamp(ts_repo, V, "Modules/components.md", by="test")
    assert set(r.stamp.bindings) == {"src/components/Header.tsx", "src/components/Footer.tsx",
                                     "src/components/ProjectCard.astro"}
    assert r.stamp.bindings["src/components/Footer.tsx"].members.keys() == {"default"}


def test_benign_and_real_changes(ts_repo):
    _stamp_all(ts_repo)
    for n in ("Modules/util.md", "Modules/components.md", "Concepts/deploy.md"):
        assert ck.check(ts_repo, V, n).state == ck.FRESH, n

    # An unmentioned method's body and an unmentioned key: drift flags Box/config, the members say benign.
    _edit(ts_repo, "src/lib/util.ts", "return 1;", "return 2;")
    _edit(ts_repo, "src/lib/util.ts", 'font: "serif"', 'font: "sans"')
    rep = ck.check(ts_repo, V, "Modules/util.md")
    assert rep.state == ck.CHANGED and ck.mechanically_benign(rep)
    # A comment and reformat inside a mentioned function: drift's TS fingerprint flags it; benign by hash.
    _edit(ts_repo, "src/lib/util.ts", "  return a + b;", "  // sum\n  return a + b")
    assert ck.mechanically_benign(ck.check(ts_repo, V, "Modules/util.md"))
    # A real change to a mentioned symbol: blocks, with was/now.
    _edit(ts_repo, "src/lib/util.ts", "return a + b", "return a - b")
    rep = ck.check(ts_repo, V, "Modules/util.md")
    assert rep.state == ck.CHANGED and not ck.mechanically_benign(rep)
    f = next(f for f in rep.findings if f.qualname == "add")
    assert f.kind == "body" and "a + b" in f.was and "a - b" in f.now and f.note_lines == [3]
    _git(ts_repo, "checkout", "--", ".")

    # JSX: a comment is benign, a text change is not; the whole-file anchor narrows to the component.
    _edit(ts_repo, "src/components/Header.tsx", "{title} don't", "{title}{/* why */} don't")
    assert ck.mechanically_benign(ck.check(ts_repo, V, "Modules/components.md"))
    _edit(ts_repo, "src/components/Header.tsx", "don't", "do not")
    rep = ck.check(ts_repo, V, "Modules/components.md")
    assert not ck.mechanically_benign(rep) and {(f.qualname, f.kind) for f in rep.findings} >= {("Header", "body")}
    _git(ts_repo, "checkout", "--", ".")

    # Astro: a template comment is benign; a Props change is a signature change of the component.
    _edit(ts_repo, "src/components/ProjectCard.astro", "<!-- a card -->", "<!-- card -->")
    assert ck.mechanically_benign(ck.check(ts_repo, V, "Modules/components.md"))
    _edit(ts_repo, "src/components/ProjectCard.astro", "title: string;", "title: string;\n  href: string;")
    rep = ck.check(ts_repo, V, "Modules/components.md")
    assert ("default", "signature") in {(f.qualname, f.kind) for f in rep.findings}
    _git(ts_repo, "checkout", "--", ".")

    # Config keys: a sibling key or a comment is benign; the mentioned key's value is not.
    _edit(ts_repo, "wrangler.jsonc", '"404-page"', '"none"')
    assert ck.mechanically_benign(ck.check(ts_repo, V, "Concepts/deploy.md"))
    _edit(ts_repo, "wrangler.jsonc", "./dist", "./build")
    rep = ck.check(ts_repo, V, "Concepts/deploy.md")
    assert not ck.mechanically_benign(rep) and ("assets.directory", "body") in {(f.qualname, f.kind) for f in rep.findings}
    _git(ts_repo, "checkout", "--", ".")


def test_renamed_component_file_is_a_move(ts_repo):
    _stamp_all(ts_repo)
    _git(ts_repo, "mv", "src/components/Footer.tsx", "src/components/SiteFooter.tsx")
    rep = ck.check(ts_repo, V, "Modules/components.md")
    moved = [f for f in rep.findings if f.kind == "moved"]
    assert rep.state == ck.CHANGED and moved and "SiteFooter.tsx" in moved[0].detail
    assert ck.mechanically_benign(rep)


def test_pre_commit_gate_blocks_real_changes_and_acks_benign_ones(ts_repo, monkeypatch, capsys):
    _stamp_all(ts_repo)
    monkeypatch.chdir(ts_repo)
    _edit(ts_repo, "src/lib/util.ts", "return a + b", "return a - b")
    _git(ts_repo, "add", "-A")
    assert pre_commit.main() == 1
    out = capsys.readouterr().out
    assert "commit blocked" in out and "util" in out and "src/lib/util.ts#add" in out
    _git(ts_repo, "checkout", "HEAD", "--", ".")

    _edit(ts_repo, "src/lib/util.ts", "return 1;", "return 2;")  # unmentioned method: benign
    _git(ts_repo, "add", "-A")
    assert pre_commit.main() == 0
    assert "auto-acked" in capsys.readouterr().out
    acks = [s for s in st.load(ts_repo / V) if s.by == "pre-commit" and s.verdict == st.ACK]
    assert [s.note for s in acks] == ["Modules/util.md"] and acks[0].reason.startswith("mechanical")
    assert "vault/.livedocs/stamps.jsonl" in _git(ts_repo, "diff", "--cached", "--name-only")


def test_first_commit_of_a_new_repo_passes_the_gate(tmp_path, monkeypatch):
    run = lambda *a: subprocess.run(["git", "-C", str(tmp_path), *a], check=True, capture_output=True)
    run("init", "-q", "-b", "main")
    (tmp_path / ".livedocs").mkdir()
    (tmp_path / ".livedocs" / "config.json").write_text('{"vault": "vault"}\n')
    (tmp_path / "vault").mkdir()
    (tmp_path / "vault" / "Home.md").write_text("# Home\n")
    run("add", "-A")
    monkeypatch.chdir(tmp_path)
    assert pre_commit.main() == 0


def test_a_bound_binary_file_flags_without_crashing(ts_repo):
    (ts_repo / "public").mkdir()
    (ts_repo / "public/logo.png").write_bytes(b"\x89PNG\r\n\x1a\n\x00\x01")
    (ts_repo / "vault/Concepts/brand.md").write_text("# Brand\n\nThe logo is `public/logo.png`.\n")
    _git(ts_repo, "add", "-A"); _git(ts_repo, "commit", "-qm", "logo")
    stp.stamp(ts_repo, V, "Concepts/brand.md", by="test")
    _git(ts_repo, "add", "-A"); _git(ts_repo, "commit", "-qm", "stamp")
    (ts_repo / "public/logo.png").write_bytes(b"\x89PNG\r\n\x1a\n\xff\xfe")
    _git(ts_repo, "commit", "-qam", "new logo")
    rep = ck.check(ts_repo, V, "Concepts/brand.md")
    assert rep.state == ck.CHANGED and rep.findings[0].kind == "file"
