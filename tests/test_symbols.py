from livedocs import mentions as mn
from livedocs import symbols as sy


def _res(idx, text, note="vault/Modules/a.md", body="# a.py\n"):
    (m,) = mn.mentions(text)
    return sy.resolve(m, idx, sy.module_hints(note, body))


def test_index_only_src_and_kinds(mini_repo):
    idx = sy.index(mini_repo)
    assert "tests/test_x.py" not in idx.files
    kinds = {s.qualname: s.kind for s in idx.symbols if s.path == "src/pkg/a.py"}
    assert kinds == {"CONST": sy.CONSTANT, "baz": sy.FUNCTION, "Foo": sy.CLASS, "Foo.level": sy.ATTRIBUTE, "Foo.bar": sy.METHOD, "Foo.shared": sy.METHOD}
    foo = idx.by_qualname("Foo")[0]
    assert foo.decorators == ("dataclass",)
    assert idx.by_qualname("Foo.bar")[0].drift_target == "src/pkg/a.py#Foo"


def test_module_hints():
    assert sy.module_hints("vault/Modules/facility-remote.md", "# facility-remote.py — `facility/remote.py`\n") == ["facility/remote.py"]
    assert sy.module_hints("vault/Modules/binding.md", "# binding\n") == ["binding.py"]
    assert sy.module_hints("vault/Modules/login_flow_manager.md", "# login_flow_manager.py\n") == ["login_flow_manager.py"]
    assert sy.module_hints("vault/Concepts/Facility catalog.md", "# Facility catalog\n") == ["Facility catalog.py"]


def test_own_module_wins_over_ambiguity(mini_repo):
    idx = sy.index(mini_repo)
    r = _res(idx, "`baz`")  # baz in a.py and sub/b.py; note is about a.py
    assert r.status == sy.RESOLVED and r.targets == ["src/pkg/a.py#baz"] and "own-module" in r.rule


def test_ambiguous_without_hint_is_superset(mini_repo):
    idx = sy.index(mini_repo)
    r = _res(idx, "`baz`", note="vault/Concepts/idea.md", body="# An idea\n")
    assert r.status == sy.SUPERSET and r.targets == ["src/pkg/a.py#baz", "src/pkg/sub/b.py#baz"]


def test_method_name_resolves_to_enclosing_class(mini_repo):
    idx = sy.index(mini_repo)
    r = _res(idx, "`only_here()`", note="vault/Concepts/idea.md", body="# An idea\n")
    assert r.status == sy.RESOLVED and r.targets == ["src/pkg/sub/b.py#Qux"] and r.candidates[0].qualname == "Qux.only_here"
    r = _res(idx, "`shared`", note="vault/Concepts/idea.md", body="# An idea\n")
    assert r.status == sy.SUPERSET and r.targets == ["src/pkg/a.py#Foo", "src/pkg/sub/b.py#Qux"]


def test_dotted_forms(mini_repo):
    idx = sy.index(mini_repo)
    assert _res(idx, "`Foo.bar`").targets == ["src/pkg/a.py#Foo"]
    assert _res(idx, "`b.baz`").targets == ["src/pkg/sub/b.py#baz"]  # module.name
    r = _res(idx, "`Nope.bar`")  # class part is an alias; member name still resolves
    assert r.status == sy.RESOLVED and r.targets == ["src/pkg/a.py#Foo"] and r.rule == "dotted:member"
    assert _res(idx, "`Nope.zzz`").status == sy.UNRESOLVED


def test_attributes_and_module_names(mini_repo):
    idx = sy.index(mini_repo)
    r = _res(idx, "`level`", note="vault/Concepts/idea.md", body="# An idea\n")
    assert r.status == sy.RESOLVED and r.targets == ["src/pkg/a.py#Foo"] and r.rule == "name:member"
    r = _res(idx, "`thing`", note="vault/Concepts/idea.md", body="# An idea\n")
    assert r.status == sy.RESOLVED and r.targets == ["src/pkg/thing.py"] and r.rule == "name:module"
    assert r.candidates[0].kind == sy.FILE


def test_paths_and_constants(mini_repo):
    idx = sy.index(mini_repo)
    r = _res(idx, "`sub/b.py:3`")
    assert r.status == sy.RESOLVED and r.targets == ["src/pkg/sub/b.py"] and r.candidates[0].kind == sy.FILE
    r = _res(idx, "`src/pkg/a.py#Foo.bar`")
    assert r.targets == ["src/pkg/a.py#Foo"]
    r = _res(idx, "`CONST`")
    assert r.status == sy.CONSTANT_ONLY and r.targets == []
    assert _res(idx, "`nothing_here`").status == sy.UNRESOLVED
