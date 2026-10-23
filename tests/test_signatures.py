"""`livedocs signatures`: exported API changes between two versions, and staged / per-commit over git."""

import json
import subprocess

from livedocs import cli, signatures as sg

TS = '''\
// Store API.
export function fileCard(id: string, opts = { draft: false }): Card { return make(id) }
export const listCards = async (tag?: string): Promise<Card[]> => all(tag)
function helper() { return 1 }
function internal() { return 2 }
export interface Card { id: string; title: string }
export type Id = string
export class Store extends Base {
  version: number = 1
  #hidden = 2
  private cache = new Map()
  save(card: Card): void { this.cache.set(card.id, card) }
}
export { helper as util }
export default function main() {}
'''

PY = '''\
__all__ = ["Card", "file_card"]
class Card:
    id: str
    title: str = ""
    def render(self, width: int = 80) -> str: return self.title
    def _private(self): pass
def file_card(card_id: str, draft: bool = False) -> "Card": return Card()
def internal(): pass
'''


def kinds(path, old, new):
    return {(c.qualname, c.kind) for c in sg.compare(path, old, new)}


def test_ts_exported_surface():
    names = set(sg.api("src/api.ts", TS))
    assert names == {"fileCard", "listCards", "Card", "Id", "Store", "Store.version", "Store.save", "util", "main"}
    # not exported: internal, helper under its own name; not API: #hidden, private cache


def test_ts_what_counts():
    p = "src/api.ts"
    edit = lambda a, b: TS.replace(a, b)
    assert kinds(p, TS, edit("opts = { draft: false }", "opts = { draft: true }")) == {("fileCard", "signature")}
    assert kinds(p, TS, edit("save(card: Card): void", "save(card: Card, force = false): void")) == {("Store.save", "signature")}
    assert kinds(p, TS, edit("title: string }", "title: string; tags: string[] }")) == {("Card", "signature")}
    assert kinds(p, TS, edit("async (tag?: string)", "(tag?: string)")) == {("listCards", "signature")}
    assert kinds(p, TS, edit("extends Base", "extends Other")) == {("Store", "signature")}
    assert kinds(p, TS, edit("version: number = 1", "version: string = '1'")) == {("Store.version", "signature")}
    for a, b in [("return make(id)", "return make2(id)"),  # body
                 ("// Store API.", "// The Store API."),  # comment
                 ("version: number = 1", "version: number = 2"),  # a field's initial value
                 ("private cache = new Map()", "private cache = new Map<string, Card>()"),  # private
                 ("function internal() { return 2 }", "function internal(x: number) { return x }")]:  # not exported
        assert kinds(p, TS, edit(a, b)) == set(), a
    assert kinds(p, TS, edit("export type Id = string\n", "")) == {("Id", "removed")}
    assert kinds(p, TS, TS + "export const VERSION = '1'\n") == {("VERSION", "added")}


def test_python_what_counts():
    p = "pkg/models.py"
    edit = lambda a, b: PY.replace(a, b)
    assert set(sg.api(p, PY)) == {"Card", "Card.id", "Card.title", "Card.render", "file_card"}  # __all__ decides
    assert kinds(p, PY, edit("width: int = 80", "width: int = 100")) == {("Card.render", "signature")}
    assert kinds(p, PY, edit('title: str = ""', 'title: str = "x"')) == {("Card.title", "signature")}  # a dataclass default
    assert kinds(p, PY, edit("draft: bool = False) ->", "draft: bool = False, *, tags=()) ->")) == {("file_card", "signature")}
    assert kinds(p, PY, edit("return Card()", "return Card()  # new")) == set()
    assert kinds(p, PY, edit("def internal(): pass", "def internal(x): pass")) == set()
    c = next(iter(sg.compare(p, PY, edit("width: int = 80", "width: int = 100"))))
    assert c.was == "def render(self, width: int=80) -> str" and c.now == "def render(self, width: int=100) -> str"


def _git(repo, *a):
    return subprocess.run(["git", "-C", str(repo), *a], check=True, capture_output=True, text=True).stdout


def test_staged_and_per_commit_over_git(tmp_path, capsys, monkeypatch):
    repo = tmp_path
    _git(repo, "init", "-q", "-b", "main"); _git(repo, "config", "user.email", "t@t"); _git(repo, "config", "user.name", "t")
    (repo / "src").mkdir(); (repo / "tests").mkdir()
    (repo / "src/api.ts").write_text(TS)
    (repo / "tests/api.test.ts").write_text("export function fixture() {}\n")  # a test file is not API
    _git(repo, "add", "-A")
    assert {c.qualname for c in sg.changes(repo)} >= {"fileCard", "Card"}  # before the first commit: all added
    assert "fixture" not in {c.qualname for c in sg.changes(repo)}
    _git(repo, "commit", "-qm", "init")
    assert sg.changes(repo) == []
    (repo / "src/api.ts").write_text(TS.replace("opts = { draft: false }", "opts = { draft: true }"))
    _git(repo, "add", "-A")
    monkeypatch.chdir(repo)
    assert cli.main(["signatures", "--cached", "--json"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out == [{"path": "src/api.ts", "qualname": "fileCard", "kind": "signature",
                    "was": "function fileCard(id: string, opts = { draft: false }): Card",
                    "now": "function fileCard(id: string, opts = { draft: true }): Card"}]
    _git(repo, "commit", "-qm", "draft default")
    assert [c.qualname for c in sg.changes(repo, rev="HEAD")] == ["fileCard"]
    assert all(c.kind == "added" for c in sg.changes(repo, rev="HEAD~1"))  # a root commit: against the empty tree
    assert cli.main(["signatures", "--rev", "no-such-rev"]) == 2  # errors are the only nonzero exit
