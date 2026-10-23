from livedocs import astdiff

SRC = '''\
import x

@deco
def f(a, b=1):
    """doc"""
    # comment
    return a + b

class C(Base):
    level: int = 0

    def m(self, y: int) -> int:
        return y

    def other(self):
        return 1
'''


def mut(old, new):
    assert old in SRC
    return SRC.replace(old, new)


def test_member_hash_ignores_comments_docstrings_formatting():
    h = astdiff.member_hash(SRC, "f")
    assert h == astdiff.member_hash(mut("# comment", "# changed"), "f")
    assert h == astdiff.member_hash(mut('"""doc"""', '"""other"""'), "f")
    assert h == astdiff.member_hash(mut("return a + b", "return  a+b"), "f")
    assert h != astdiff.member_hash(mut("return a + b", "return a - b"), "f")
    assert h != astdiff.member_hash(mut("@deco", "@other"), "f")
    assert h != astdiff.member_hash(mut("def f(a, b=1)", "async def f(a, b=1)"), "f")


def test_class_shell_hash_ignores_method_bodies_but_not_members_or_fields():
    h = astdiff.member_hash(SRC, "C")
    assert h == astdiff.member_hash(mut("return y", "return y + 1"), "C")  # method body: not the class's concern
    assert h != astdiff.member_hash(mut("    def other(self):\n        return 1\n", ""), "C")  # member removed
    assert h != astdiff.member_hash(mut("level: int = 0", "level: int = 1"), "C")  # field changed
    assert h != astdiff.member_hash(mut("class C(Base)", "class C(Other)"), "C")
    m = astdiff.member_hash(SRC, "C.m")
    assert m != astdiff.member_hash(mut("return y", "return y + 1"), "C.m")
    assert m == astdiff.member_hash(mut("return 1", "return 2"), "C.m")  # sibling method: irrelevant
    assert astdiff.member_hash(SRC, "C.level") != astdiff.member_hash(mut("level: int = 0", "level: int = 1"), "C.level")
    assert astdiff.member_hash(SRC, "nope") is None and astdiff.member_hash("def (", "f") is None


def test_member_hashes_are_tagged_and_python_version_stable():
    h = astdiff.member_hash(SRC, "f")
    assert h.startswith("py2:")
    assert "posonlyargs" not in astdiff._stable_dump(__import__("ast").parse(SRC).body[1])  # no empty fields
    legacy = astdiff._py_member_hash(SRC, "f", astdiff._dump)  # a 0.1 stamp's bare hash
    assert astdiff.member_matches(legacy, SRC, "f") and astdiff.member_matches(h, SRC, "f")
    assert not astdiff.member_matches(h, mut("return a + b", "return a - b"), "f")
    assert astdiff.member_hash("export function f() {}", "f", path="x.ts").startswith("ts1:")


def test_stamp_round_trip_keeps_hash_schemes():
    from livedocs import stamps as st
    b = st.Binding(sig="abcd", members={"f": "py2:0011", "g": "ts1:2233", "h": "4455"})
    s = st.Stamp(note="n.md", note_hash="sha256:x", bindings={"a.py#f": b}, mentions={}, unresolved=[],
                 stamped="2026-10-23T00:00:00Z", by="t", verdict="initial")
    line = s.to_json()
    assert '["h","ast:4455"]' in line and '["f","py2:0011"]' in line  # legacy stays `ast:`-tagged on disk
    assert st.Stamp.from_json(line).bindings["a.py#f"].members == {"f": "py2:0011", "g": "ts1:2233", "h": "4455"}
