from livedocs import astdiff, stamps as st


def test_note_hash_ignores_frontmatter_crlf_and_trailing_ws_but_not_depends_on():
    a = "---\nupdated: 2026-01-01\n---\nbody `x`\n"
    b = "---\nupdated: 2026-02-02\ntags: [y]\n---\nbody `x`   \r\n"
    assert st.note_hash(a) == st.note_hash(b)
    assert st.note_hash(a) != st.note_hash(a.replace("body", "other"))
    c = "---\ndepends_on: [\"src/a.py#f\"]\n---\nbody `x`\n"
    assert st.note_hash(c) != st.note_hash(a)
    assert st.note_hash("no frontmatter\n") == st.note_hash("no frontmatter")


OLD = '''\
import x

@deco
def f(a, b=1):
    """doc"""
    # comment
    return a + b

class C:
    def m(self, y: int) -> int:
        return y
'''


def _mut(s: str, old: str, new: str) -> str:
    assert old in s
    return s.replace(old, new)


def test_classify_kinds():
    assert astdiff.classify(OLD, OLD, "f").kind == astdiff.UNCHANGED
    assert astdiff.classify(OLD, _mut(OLD, "def f(a, b=1)", "def f(a, b=2)"), "f").kind == astdiff.SIGNATURE
    assert astdiff.classify(OLD, _mut(OLD, "def f(a, b=1)", "async def f(a, b=1)"), "f").kind == astdiff.SIGNATURE
    assert astdiff.classify(OLD, _mut(OLD, "@deco", "@other"), "f").kind == astdiff.DECORATOR
    assert astdiff.classify(OLD, _mut(OLD, "# comment", "# changed"), "f").kind == astdiff.COMMENT_ONLY
    assert astdiff.classify(OLD, _mut(OLD, '"""doc"""', '"""new doc"""'), "f").kind == astdiff.COMMENT_ONLY
    assert astdiff.classify(OLD, _mut(OLD, "return a + b", "return a - b"), "f").kind == astdiff.BODY
    assert astdiff.classify(OLD, _mut(OLD, "-> int:", "-> str:"), "C.m").kind == astdiff.SIGNATURE
    assert astdiff.classify(OLD, _mut(OLD, "def m(self", "def n(self"), "C.m").kind == astdiff.REMOVED
    assert astdiff.classify(OLD, _mut(OLD, "def m(self", "def n(self"), "C").kind == astdiff.BODY


def test_unparseable_new_source_is_not_a_removal():
    ch = astdiff.classify(OLD, _mut(OLD, "def f(a, b=1):", "def f(a, b=1"), "f")
    assert ch.kind == astdiff.UNPARSEABLE and ch.was and ch.now is None


def test_symbol_source_includes_decorators_and_decorator_hash():
    src = astdiff.symbol_source(OLD, "f")
    assert src.startswith("@deco\ndef f(")
    assert astdiff.decorator_hash(OLD, "f") and astdiff.decorator_hash(OLD, "C") == ""
    assert astdiff.decorator_hash(OLD, "f") != astdiff.decorator_hash(_mut(OLD, "@deco", "@other"), "f")
    assert astdiff.first_line(src) == "def f(a, b=1):"


def test_stamp_roundtrip(tmp_path):
    s = st.Stamp("a.md", "sha256:x", {"p.py#T": st.Binding("ab", "cd", ["T.m"])}, {"p.py#T": [["T.m()", 3]]}, ["zz"], "t", "me", st.INITIAL)
    st.append(tmp_path, s)
    st.append(tmp_path, s)
    loaded = st.load(tmp_path)
    assert len(loaded) == 2 and loaded[0] == s
    lock = {("v/a.md", "p.py#T"): "ab"}
    assert st.matching(loaded, "sha256:x", lock, "v/a.md") is loaded[1]
    assert st.matching(loaded, "sha256:x", {("v/a.md", "p.py#T"): "ZZ"}, "v/a.md") is None
    assert st.matching(loaded, "sha256:other", lock, "v/a.md") is None
