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
