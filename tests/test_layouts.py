"""Code discovery must not depend on a top-level src/ (user-reported: benchmark/src/ was invisible)."""

import subprocess

from livedocs import mentions as mn, symbols as sy


def _repo(tmp_path, files):
    for rel, content in files.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
    run = lambda *a: subprocess.run(["git", "-C", str(tmp_path), *a], check=True, capture_output=True)
    run("init", "-q", "-b", "main"); run("config", "user.email", "t@t"); run("config", "user.name", "t")
    run("add", "-A"); run("commit", "-qm", "init")
    return tmp_path


def test_nested_src_and_flat_packages_are_indexed(tmp_path):
    repo = _repo(tmp_path, {
        "benchmark/src/gateway.py": "def create_app():\n    return 1\n\ndef get_access_token(x):\n    return x\n",
        "app/models.py": "class User:\n    name: str = ''\n",
        "tests/test_gateway.py": "def create_app():\n    pass\n",  # a test double, never the target
        ".venv/lib/site-packages/junk.py": "def create_app():\n    pass\n",
        "vault/gateway.md": "# benchmark/src/gateway.py\n\n`create_app()` builds it; `get_access_token` signs in; `User` is the model.\n",
    })
    idx = sy.index(repo)
    assert "benchmark/src/gateway.py" in idx.files and "app/models.py" in idx.files
    assert "tests/test_gateway.py" not in idx.files and not any("site-packages" in f for f in idx.files)
    text = (repo / "vault/gateway.md").read_text()
    res = sy.resolve_note("vault/gateway.md", text, idx, mn.mentions(text))
    targets = {r.mention.text: r.targets for r in res}
    assert targets["create_app"] == ["benchmark/src/gateway.py#create_app"]
    assert targets["get_access_token"] == ["benchmark/src/gateway.py#get_access_token"]
    assert targets["User"] == ["app/models.py#User"]
    assert idx.by_qualname("create_app")[0].module == "gateway"  # the src segment is stripped wherever it is


def test_code_roots_config_overrides_discovery(tmp_path):
    repo = _repo(tmp_path, {
        "lib/a.py": "def f():\n    pass\n",
        "other/b.py": "def g():\n    pass\n",
        ".livedocs/config.json": '{"vault": "vault", "code_roots": ["lib"]}\n',
    })
    idx = sy.index(repo)
    assert idx.files == {"lib/a.py"}
