"""TypeScript / JavaScript / Astro / JSON config: index, resolution, member hashes, classification."""

import subprocess

from livedocs import astdiff, gitx, mentions as mn, symbols as sy, ts


def _res(idx, text, note="vault/Modules/util.md", body="# src/lib/util.ts\n"):
    (m,) = mn.mentions(text)
    return sy.resolve(m, idx, sy.module_hints(note, body))


def test_index_kinds_targets_and_exclusions(ts_repo):
    idx = sy.index(ts_repo)
    assert "tests/util.test.ts" not in idx.files and "wrangler.jsonc" not in idx.files
    kinds = {s.qualname: s.kind for s in idx.symbols if s.path == "src/lib/util.ts"}
    assert kinds["add"] == sy.FUNCTION and kinds["mul"] == sy.FUNCTION  # an arrow const is a function
    assert kinds["Box"] == sy.CLASS and kinds["Box.area"] == sy.METHOD and kinds["Box.w"] == sy.ATTRIBUTE  # parameter property
    assert kinds["Props"] == sy.INTERFACE and kinds["Props.title"] == sy.ATTRIBUTE and kinds["Id"] == sy.TYPE
    assert kinds["Color.Green"] == sy.ATTRIBUTE and kinds["config"] == sy.CONSTANT and kinds["config.theme.color"] == sy.KEY
    at = lambda p, q: idx.at(p, q).drift_target
    assert at("src/lib/util.ts", "Box.area") == "src/lib/util.ts#Box"  # drift fingerprints .ts top-level symbols
    assert at("src/lib/util.ts", "config.theme") == "src/lib/util.ts#config"
    assert at("src/components/Header.tsx", "Header") == "src/components/Header.tsx"  # JSX: drift can't, the file binds
    assert at("src/components/ProjectCard.astro", "default") == "src/components/ProjectCard.astro"
    assert at("wrangler.jsonc", "assets.directory") == "wrangler.jsonc"
    assert idx.path_aliases == [("@/*", ["src/*"])]


def test_default_exports_aliases_and_barrels(ts_repo):
    idx = sy.index(ts_repo)
    assert idx.defaults["src/components/Header.tsx"] == "Header"  # named default
    assert idx.defaults["src/components/Footer.tsx"] == "default"  # anonymous default
    names = lambda n: [(s.path, s.qualname) for s in idx.by_qualname(n)]
    assert names("Footer") == [("src/components/Footer.tsx", "default")]  # by its file name
    assert names("SiteFooter") == [("src/components/Footer.tsx", "default")]  # barrel rename → the definition
    assert names("siteConfig") == [("src/lib/util.ts", "config")]  # export { config as siteConfig }
    assert names("ProjectCard") == [("src/components/ProjectCard.astro", "default")]
    assert names("Header") == [("src/components/Header.tsx", "Header")]  # the barrel is never a candidate


def test_resolution_forms(ts_repo):
    idx = sy.index(ts_repo)
    r = _res(idx, "`siteConfig.theme.color`")
    assert r.rule == "dotted:alias" and r.candidates[0].qualname == "config.theme.color"
    r = _res(idx, "`<Header />`")
    assert r.status == sy.RESOLVED and r.rule == "jsx:component" and r.candidates[0].path == "src/components/Header.tsx"
    assert _res(idx, "`<Box />`").status == sy.RESOLVED  # a class is a component
    assert _res(idx, "`<Color />`").status == sy.UNRESOLVED  # an enum is not
    r = _res(idx, "`@/components/Footer`")  # alias, extensionless → the module's default export (P29)
    assert r.rule == "path:default" and r.candidates[0].qualname == "default"
    r = _res(idx, "`src/lib/util.ts`")  # a module with no default export names only the file
    assert r.rule == "path" and r.candidates[0].kind == sy.FILE
    r = _res(idx, "`wrangler.jsonc#assets.directory`")
    assert r.status == sy.RESOLVED and r.candidates[0].kind == sy.KEY
    r = _res(idx, "`assets.directory`", note="vault/Concepts/deploy.md", body="# Deploy\n")
    assert r.candidates[0].path == "wrangler.jsonc"
    r = _res(idx, "`theme.color`", note="vault/Concepts/x.md", body="# X\n")  # key path below its constant
    assert r.rule == "dotted:key-suffix" and r.candidates[0].qualname == "config.theme.color"
    assert _res(idx, "`color`").status == sy.UNRESOLVED  # bare key names never bind
    r = _res(idx, "`ProjectCard.Props`", note="vault/Concepts/x.md", body="# X\n")
    assert r.candidates[0].path == "src/components/ProjectCard.astro"  # module.name
    r = _res(idx, "`Props`", note="vault/Modules/ProjectCard.md", body="# ProjectCard\n")
    assert r.status == sy.RESOLVED and r.candidates[0].path == "src/components/ProjectCard.astro"  # own module
    r = _res(idx, "`Props`", note="vault/Concepts/x.md", body="# X\n")
    assert r.status == sy.SUPERSET  # two Props, no hint: all of them, never a false fresh
    r = _res(idx, "`Header`", note="vault/Modules/components.md", body="# Modules/components\n")
    assert r.candidates[0].path == "src/components/Header.tsx"


def test_module_hints_for_ts_paths():
    assert sy.module_hints("vault/Modules/x.md", "# src/components/Header.tsx\n")[0] == "src/components/Header.tsx"
    assert sy._hint_matches("src/world/stars.ts", "world.py")  # `# Modules/world` covers the folder
    assert sy._hint_matches("src/world/world.ts", "world")
    assert not sy._hint_matches("src/worlds/x.ts", "world")
    assert not sy._hint_matches("src/world/world.py", "world")  # Python keeps its own rule


def test_mentions_ts_forms():
    got = lambda t: [(m.text, m.kind, m.call, m.jsx) for m in mn.mentions(f"`{t}`")]
    assert got("<ProjectCard title={t} />") == [("ProjectCard", mn.NAME, False, True)]
    assert got("<button>") == [] and got("<NAME>") == []
    assert got("useStore<T>()") == [("useStore", mn.NAME, True, False)]
    assert got("generateShareCard(state): Promise<Blob>") == [("generateShareCard", mn.NAME, True, False)]
    assert got("porch01.level.ts")[0][1] == mn.PATH and got("@/components/Header.astro")[0][1] == mn.PATH
    (m,) = mn.mentions("`wrangler.jsonc#assets.directory`")
    assert (m.text, m.symbol) == ("wrangler.jsonc", "assets.directory")


SRC = '''\
// lead
@Component({ sel: "x" })
export class Widget extends Base {
  @Input() name = "w";
  render(): string {
    return "a";
  }
  other() {
    return 1;
  }
}

export function total(items: number[], rate = 0.15): number {
  return items.reduce((s, x) => s + x, 0) * (1 + rate);
}

export const Card = ({ title }: P) => (
  <div className="card">{title} — don't</div>
);
'''


def mut(old, new):
    assert old in SRC
    return SRC.replace(old, new)


def h(src, q, path="src/w.tsx"):
    return ts.member_hash(path, src, q)


def test_member_hash_ignores_comments_and_formatting_only():
    assert h(SRC, "total") == h(mut("return items", "// sum\n  return  items"), "total")
    assert h(SRC, "total") == h(mut("(1 + rate);", "(1 + rate)"), "total")  # optional semicolon
    assert h(SRC, "total") != h(mut("(1 + rate)", "1 + rate"), "total")  # grouping is meaning
    assert h(SRC, "Card") == h(mut("{title} — don't", "{title}{/* jsx comment */} — don't"), "Card")
    assert h(SRC, "Card") == h(mut('className="card"', "className='card'"), "Card")  # quote style
    assert h(SRC, "Card") != h(mut("don't", "do not"), "Card")  # JSX text is content
    assert h(SRC, "Card") == h(mut("(\n  <div", "<div").replace("</div>\n);", "</div>;"), "Card")  # redundant parens


def test_class_shell_and_members():
    assert h(SRC, "Widget") == h(mut('return "a"', 'return "b"'), "Widget")  # a method body is not the class's
    assert h(SRC, "Widget.render") != h(mut('return "a"', 'return "b"'), "Widget.render")
    assert h(SRC, "Widget.render") == h(mut("return 1", "return 2"), "Widget.render")  # sibling method
    assert h(SRC, "Widget") != h(mut('name = "w"', 'name = "v"'), "Widget")  # field
    assert h(SRC, "Widget") != h(mut('sel: "x"', 'sel: "y"'), "Widget")  # decorator
    assert h(SRC, "Widget") != h(mut("extends Base", "extends Other"), "Widget")


def test_classify_kinds():
    c = lambda new, q: astdiff.classify(SRC, new, q, path="src/w.tsx").kind
    assert c(mut("rate = 0.15", "rate = 0.2"), "total") == astdiff.SIGNATURE
    assert c(mut("s + x", "s - x"), "total") == astdiff.BODY
    assert c(mut("return items", "// note\n  return items"), "total") == astdiff.COMMENT_ONLY
    assert c(mut('sel: "x"', 'sel: "y"'), "Widget") == astdiff.DECORATOR
    assert c(mut("export function total", "export async function total"), "total") == astdiff.SIGNATURE
    assert c(SRC.replace("export function total", "function totalx"), "total") == astdiff.REMOVED
    assert c(SRC + "\nexport function (", "total") == astdiff.UNPARSEABLE


def test_astro_component_and_frontmatter(ts_repo):
    p = "src/components/ProjectCard.astro"
    src = (ts_repo / p).read_text()
    assert h(src, "default", p) == h(src.replace("<!-- a card -->", "<!-- the card -->"), "default", p)
    assert h(src, "default", p) == h(src.replace('<article class="card">', '<article  class="card"  >'.replace("  >", ">")), "default", p)
    assert h(src, "default", p) != h(src.replace("<article", "<section").replace("</article>", "</section>"), "default", p)
    assert h(src, "Props", p) == h(src.replace('<article class="card">', "<article>"), "Props", p)  # template edit
    assert astdiff.classify(src, src.replace("title: string;", "title?: string;"), "default", path=p).kind == astdiff.SIGNATURE


def test_config_keys_values_not_text(ts_repo):
    p = "wrangler.jsonc"
    src = (ts_repo / p).read_text()
    k = lambda s, q: astdiff.member_hash(s, q, path=p)
    assert k(src, "assets.directory") == k(src.replace("// the worker", "// renamed"), "assets.directory")
    assert k(src, "assets.directory") == k(src.replace('"404-page"', '"none"'), "assets.directory")  # sibling key
    assert k(src, "assets.directory") != k(src.replace("./dist", "./build"), "assets.directory")
    assert astdiff.classify(src, src.replace("./dist", "./build"), "assets.directory", path=p).kind == astdiff.BODY


def test_changed_files_before_the_first_commit(tmp_path):
    run = lambda *a: subprocess.run(["git", "-C", str(tmp_path), *a], check=True, capture_output=True)
    run("init", "-q", "-b", "main")
    assert not gitx.has_head(tmp_path) and gitx.changed_files(tmp_path) == []
    (tmp_path / "a.md").write_text("x")
    run("add", "a.md")
    assert gitx.changed_files(tmp_path, cached=True) == ["a.md"]
