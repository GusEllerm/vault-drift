import subprocess

from livedocs import gitx


def _commit_lock(repo, content, msg):
    (repo / "drift.lock").write_text(content)
    subprocess.run(["git", "-C", str(repo), "add", "drift.lock"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", msg], check=True)
    return gitx.head(repo)


def _lock(*bindings):
    return "version = 1\n\n" + "\n\n".join(f'[[bindings]]\n{gitx.lock_block(d, t, s)}' for d, t, s in bindings) + "\n"


def test_diff_base_survives_shared_and_recurring_sigs(tmp_path):
    repo = tmp_path
    run = lambda *a: subprocess.run(["git", "-C", str(repo), *a], check=True, capture_output=True)
    run("init", "-q", "-b", "main"); run("config", "user.email", "t@t"); run("config", "user.name", "t")
    c1 = _commit_lock(repo, _lock(("a.md", "x.py#f", "aaaa")), "c1")
    c2 = _commit_lock(repo, _lock(("a.md", "x.py#f", "aaaa"), ("b.md", "x.py#f", "aaaa")), "c2")
    c3 = _commit_lock(repo, _lock(("a.md", "x.py#f", "bbbb"), ("b.md", "x.py#f", "aaaa")), "c3")
    c4 = _commit_lock(repo, _lock(("a.md", "x.py#f", "aaaa"), ("b.md", "x.py#f", "aaaa")), "c4 revert")
    assert gitx.diff_base(repo, "b.md", "x.py#f", "aaaa") == c2  # shared sig: b's own introduction
    assert gitx.diff_base(repo, "a.md", "x.py#f", "bbbb") == c3
    assert gitx.diff_base(repo, "a.md", "x.py#f", "aaaa") == c4  # recurring sig: newest introduction
    assert gitx.diff_base(repo, "a.md", "x.py#f", "zzzz") is None
    assert gitx.blob_at(repo, c1, "drift.lock").startswith("version = 1")
    assert gitx.blob_at(repo, c1, "nope") is None
