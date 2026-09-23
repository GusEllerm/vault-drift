"""A tiny git repo with a Python package and two notes, rebuilt per test session."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

FILES = {
    "src/pkg/__init__.py": "",
    "src/pkg/a.py": '''\
CONST = 1
TEMPLATE = """\\
engine:
  type: x
"""

def baz(x):
    return x

@dataclass
class Foo:
    level: int = 0

    def bar(self, y: int) -> int:
        return y

    def shared(self):
        return 1

    def unmentioned(self):
        return 0
''',
    "src/pkg/sub/__init__.py": "",
    "src/pkg/sub/b.py": '''\
def baz(x):
    return -x

class Qux:
    def shared(self):
        return 2

    def only_here(self):
        return 3
''',
    "src/pkg/thing.py": "def go():\n    pass\n",
    "tests/test_x.py": "def baz():\n    pass\n",
    "vault/Modules/a.md": "---\ntags: [x]\n---\n# a.py\n\n`Foo` is a dataclass; `Foo.bar` calls `baz` and `shared`; `CONST` is `1`; `TEMPLATE` has two keys. See `sub/b.py:3` and `only_here()`.\n",
    "vault/Concepts/idea.md": "# An idea\n\nUses `baz`, `Qux`, `nothing_here`, `visible_to: public`, `$HOME`, `id`.\n",
    "vault/Reference/Review 2026-01-01.md": "# Review 2026-01-01\n\nAt this date `baz` returned x and `Foo.bar` had one arg.\n",
    "vault/Sessions/log.md": "---\nlivedocs: snapshot\n---\n# Log\n\nWe changed `baz` today.\n",
    ".livedocs/config.json": '{"vault": "vault", "snapshot_globs": ["Reference/Review *"]}\n',
}


@pytest.fixture(scope="session")
def mini_repo(tmp_path_factory) -> Path:
    root = tmp_path_factory.mktemp("mini")
    for rel, content in FILES.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
    run = lambda *a: subprocess.run(["git", "-C", str(root), *a], check=True, capture_output=True)
    run("init", "-q", "-b", "main")
    run("config", "user.email", "t@t")
    run("config", "user.name", "t")
    run("add", "-A")
    run("commit", "-q", "-m", "init")
    return root
