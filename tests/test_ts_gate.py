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


def test_bindings_follow_symbols(ts_repo):
    r = stp.stamp(ts_repo, V, "Modules/util.md", by="test")
    b = r.stamp.bindings
    assert not r.failed
    # symbols bind at drift's symbol granularity with their own member hashes
    assert set(b) == {"src/lib/util.ts#add", "src/lib/util.ts#mul", "src/lib/util.ts#Box",
                      "src/lib/util.ts#config", "src/lib/util.ts#Props"}
    assert set(b["src/lib/util.ts#Box"].members) == {"Box.area", "Box.w"}
    assert set(b["src/lib/util.ts#config"].members) == {"config.theme.color"}
    r = stp.stamp(ts_repo, V, "Modules/components.md", by="test")
    assert set(r.stamp.bindings) == {"src/components/Header.tsx", "src/components/Footer.tsx",
                                     "src/components/ProjectCard.astro"}
    assert r.stamp.bindings["src/components/Footer.tsx"].members.keys() == {"default"}


def test_module_paths_bind_small_files_whole(ts_repo):
    (ts_repo / "vault/Concepts/paths.md").write_text("# paths\n\nSee `src/lib/util.ts` and `@/components/Footer`.\n")
    _git(ts_repo, "add", "-A"); _git(ts_repo, "commit", "-qm", "paths note")
    b = stp.stamp(ts_repo, V, "Concepts/paths.md", by="test").stamp.bindings
    assert b["src/lib/util.ts"].qualnames == [""]  # a small module binds whole (P29)
    assert set(b["src/components/Footer.tsx"].qualnames) == {"default", ""}
    _git(ts_repo, "add", "-A"); _git(ts_repo, "commit", "-qm", "stamp")
    _edit(ts_repo, "src/lib/util.ts", "return 1;", "return 2;")  # any real change in the file is the note's concern
    rep = ck.check(ts_repo, V, "Concepts/paths.md")
    assert rep.state == ck.CHANGED and not ck.mechanically_benign(rep) and "file" in {f.kind for f in rep.findings}
    _git(ts_repo, "checkout", "--", ".")
    _edit(ts_repo, "src/lib/util.ts", "// Helpers.", "// Helpers for the site.")  # comments only: benign
    assert ck.mechanically_benign(ck.check(ts_repo, V, "Concepts/paths.md"))
    _git(ts_repo, "checkout", "--", ".")
    # a 5-line limit: util.ts (30 lines) binds nothing by path, the one-line Footer.tsx still binds whole;
    # "default-export": only the default export binds by path
    for mode, footer in (('5', {"default", ""}), ('"default-export"', {"default"})):
        (ts_repo / ".livedocs/config.json").write_text('{"vault": "vault", "path_anchors": %s}\n' % mode)
        b = stp.stamp(ts_repo, V, "Concepts/paths.md", by="test", verdict=st.ACK, reason="mode").stamp.bindings
        assert "src/lib/util.ts" not in b and set(b["src/components/Footer.tsx"].qualnames) == footer, mode


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

    # Astro: a template comment is benign; a template change is not (it is outside the frontmatter, and
    # once slipped through as "unchanged"); a Props change is a signature change of the component.
    _edit(ts_repo, "src/components/ProjectCard.astro", "<!-- a card -->", "<!-- card -->")
    assert ck.mechanically_benign(ck.check(ts_repo, V, "Modules/components.md"))
    _edit(ts_repo, "src/components/ProjectCard.astro", '<article class="card">', '<article class="card wide">')
    _git(ts_repo, "add", "-A"); _git(ts_repo, "commit", "-qm", "wider card")  # a committed base: classify runs
    rep = ck.check(ts_repo, V, "Modules/components.md")
    assert not ck.mechanically_benign(rep) and ("default", "body") in {(f.qualname, f.kind) for f in rep.findings}
    assert "card wide" in next(f.now for f in rep.findings if f.qualname == "default")
    _git(ts_repo, "reset", "-q", "--hard", "HEAD~1")
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
    moved = [f for f in rep.findings if f.kind.startswith("moved")]
    assert rep.state == ck.CHANGED and moved and "SiteFooter.tsx" in moved[0].detail
    # the note names `@/components/Footer`, the file the component left: not benign (see the next test)
    assert moved[0].kind == "moved-from-named-file" and not ck.mechanically_benign(rep)


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
    (ts_repo / "public/engine.wasm").write_bytes(b"\x00asm\x01\x00\x00\x00\x89\xff")
    (ts_repo / "vault/Concepts/engine.md").write_text("# Engine\n\nThe physics runs in `public/engine.wasm`.\n")
    _git(ts_repo, "add", "-A"); _git(ts_repo, "commit", "-qm", "wasm")
    stp.stamp(ts_repo, V, "Concepts/engine.md", by="test")
    _git(ts_repo, "add", "-A"); _git(ts_repo, "commit", "-qm", "stamp")
    (ts_repo / "public/engine.wasm").write_bytes(b"\x00asm\x01\x00\x00\x00\xfe\xfe")
    _git(ts_repo, "commit", "-qam", "new engine")
    rep = ck.check(ts_repo, V, "Concepts/engine.md")
    assert rep.state == ck.CHANGED and rep.findings[0].kind == "file"


def test_paths_to_notes_media_and_lockfiles_never_bind(ts_repo):
    (ts_repo / "content").mkdir()
    (ts_repo / "content/Site.md").write_text("Hello.\n")
    (ts_repo / "logo.png").write_bytes(b"\x89PNG")
    (ts_repo / "package-lock.json").write_text("{}\n")
    (ts_repo / "vault/Concepts/site.md").write_text(
        "# Site\n\nThe tagline is in `content/Site.md`; the logo is `logo.png`; deps pinned in `package-lock.json`; "
        "the worker is configured in `wrangler.jsonc`; see `vault/Modules/util.md`.\n")
    _git(ts_repo, "add", "-A"); _git(ts_repo, "commit", "-qm", "content")
    b = stp.stamp(ts_repo, V, "Concepts/site.md", by="test").stamp.bindings
    # config and a Markdown file outside the vault bind; an image, a lockfile and another note don't
    assert set(b) == {"wrangler.jsonc", "content/Site.md"}
    (ts_repo / ".livedocs/config.json").write_text('{"vault": "vault", "ignore_paths": ["content/**"]}\n')
    b = stp.stamp(ts_repo, V, "Concepts/site.md", by="test", verdict=st.ACK, reason="content is out of scope").stamp.bindings
    assert set(b) == {"wrangler.jsonc"}  # site content, declared out of scope


def test_ignore_paths_and_the_gates_fast_path(ts_repo, monkeypatch, capsys):
    from livedocs import drift_io
    _stamp_all(ts_repo)
    (ts_repo / ".livedocs/config.json").write_text('{"vault": "vault", "ignore_paths": ["src/lib/**"]}\n')
    from livedocs import symbols as sy
    assert "src/lib/util.ts" not in sy.index(ts_repo, "WORKTREE").files  # out of scope: never indexed
    (ts_repo / ".livedocs/config.json").write_text('{"vault": "vault"}\n')  # as committed
    monkeypatch.chdir(ts_repo)
    # A commit touching nothing any note is bound to passes without drift (Obsidian committing content).
    (ts_repo / "README.md").write_text("# site\n")
    _git(ts_repo, "add", "-A")
    drift_io.binary.cache_clear()
    monkeypatch.setenv("PATH", "/usr/bin:/bin"); monkeypatch.setenv("HOME", "/nonexistent")
    monkeypatch.setattr(drift_io, "_DIRS", ())
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", "/dev/null")
    _git(ts_repo, "config", "--unset-all", "livedocs.drift") if "livedocs.drift" in _git(ts_repo, "config", "--list") else None
    assert pre_commit.main() == 0
    # The same missing drift with bound code staged: blocked, saying why (never a silently unbound stamp).
    _edit(ts_repo, "src/lib/util.ts", "return a + b", "return a - b")
    _git(ts_repo, "add", "-A")
    assert pre_commit.main() == 1
    assert "drift not found" in capsys.readouterr().out
    drift_io.binary.cache_clear()


def test_rebind_replaces_whole_file_anchors_and_drops_orphans(ts_repo):
    from livedocs import drift_io
    cfg = ts_repo / ".livedocs/config.json"
    (ts_repo / "vault/Modules/util.md").write_text((ts_repo / "vault/Modules/util.md").read_text() + "See `src/lib/util.ts`.\n")
    cfg.write_text('{"vault": "vault", "file_anchors": true}\n')  # binds the file whole
    stp.stamp(ts_repo, V, "Modules/util.md", by="test")
    assert ("vault/Modules/util.md", "src/lib/util.ts") in drift_io.lock(ts_repo)
    cfg.write_text('{"vault": "vault", "path_anchors": "default-export"}\n')  # a rule under which it doesn't
    _git(ts_repo, "add", "-A"); _git(ts_repo, "commit", "-qm", "old-style stamps")
    done, skipped = stp.rebind(ts_repo, V, reason="rebind")
    assert done == ["Modules/util.md"] and skipped == []
    lock = drift_io.lock(ts_repo)
    assert ("vault/Modules/util.md", "src/lib/util.ts") not in lock  # orphan unlinked
    assert ("vault/Modules/util.md", "src/lib/util.ts#add") in lock
    latest = st.latest(st.for_note(st.load(ts_repo / V), "Modules/util.md"))
    assert latest.verdict == st.ACK and latest.reason == "rebind" and "src/lib/util.ts" not in latest.bindings
    (ts_repo / "vault/Modules/util.md").write_text("# src/lib/util.ts\n\nNow only `mul`.\n")  # edited: left for its commit
    assert stp.rebind(ts_repo, V, reason="rebind") == ([], ["Modules/util.md"])


def test_a_move_is_benign_unless_the_note_names_the_old_file(ts_repo):
    _stamp_all(ts_repo)
    # components.md names `@/components/Footer` (the file) → moving Footer.tsx is a location change it states
    (ts_repo / "vault/Modules/footer.md").write_text("# Footer\n\nThe footer is `SiteFooter`.\n")
    stp.stamp(ts_repo, V, "Modules/footer.md", by="test")
    _git(ts_repo, "add", "-A"); _git(ts_repo, "commit", "-qm", "footer note")
    _git(ts_repo, "mv", "src/components/Footer.tsx", "src/components/SiteFooter.tsx")
    named = ck.check(ts_repo, V, "Modules/components.md")
    assert {f.kind for f in named.findings} >= {"moved-from-named-file"} and not ck.mechanically_benign(named)
    plain = ck.check(ts_repo, V, "Modules/footer.md")
    assert {f.kind for f in plain.findings} == {"moved"} and ck.mechanically_benign(plain)


def test_keys_and_accessors_do_not_bind_bare_words(ts_repo):
    from livedocs import mentions as mn, symbols as sy
    (ts_repo / "package.json").write_text('{"name": "site", "version": "1.0.0"}\n')
    (ts_repo / "src/lib/clock.ts").write_text("export class Clock { get time() { return 1 } }\n")
    _git(ts_repo, "add", "-A"); _git(ts_repo, "commit", "-qm", "pkg")
    idx = sy.index(ts_repo)
    res = lambda t, note="vault/Concepts/x.md", body="# X\n": sy.resolve(mn.mentions(f"`{t}`")[0], idx, sy.module_hints(note, body))
    assert res("name").status == sy.UNRESOLVED  # not package.json's key
    assert res("time").status == sy.UNRESOLVED  # a short accessor name outside its module
    assert res("time", "vault/Modules/clock.md", "# clock\n").candidates[0].qualname == "Clock.time"
