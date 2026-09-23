from livedocs import mentions as mn


def spans(text):
    return {(m.text, m.kind) for m in mn.mentions(text)}


def test_frontmatter_skipped_and_lines_are_file_lines():
    text = "---\ntags: [`fake`]\n---\n# T\n\n`real_name`\n"
    ms = mn.mentions(text)
    assert [(m.text, m.line) for m in ms] == [("real_name", 6)]


def test_noise_rules():
    text = "`visible_to: public` `$HOME` `id` `on: each_login` `\"quoted\"` `a b` `x=1` `-flag` `None` `main`"
    assert mn.mentions(text) == []


def test_kinds_and_normalisation():
    text = "`credentials.py:78` `wait(timeout_s)` `Foo.bar()` `config._x` `PUBLIC_INDEX` `facility/remote.py` `src/a.py#Foo.bar` `SshTarget`"
    assert spans(text) == {
        ("credentials.py", mn.PATH),
        ("wait", mn.NAME),
        ("Foo.bar", mn.DOTTED),
        ("config._x", mn.DOTTED),
        ("PUBLIC_INDEX", mn.CAPS),
        ("facility/remote.py", mn.PATH),
        ("src/a.py", mn.PATH),
        ("SshTarget", mn.NAME),
    }
    hashed = [m for m in mn.mentions(text) if m.raw.startswith("src/")][0]
    assert hashed.symbol == "Foo.bar"


def test_calls_with_arguments_are_mentions():
    ms = mn.mentions("`total(items, tax_rate=0.15)` and `Foo.bar(x=1)` but not `x = 1` or `a b`")
    assert [(m.text, m.kind) for m in ms] == [("total", mn.NAME), ("Foo.bar", mn.DOTTED)]


def test_fence_lines_are_not_spans_but_inline_spans_inside_fences_are():
    text = "```python\nx = `inner_name`\n```\n"
    assert spans(text) == {("inner_name", mn.NAME)}
