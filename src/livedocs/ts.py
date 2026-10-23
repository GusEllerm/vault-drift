"""TypeScript, JavaScript and Astro: symbols, member hashes and change classification (tree-sitter).

drift v0.10.1 fingerprints top-level symbols in `.ts` and `.js` files only: nothing in a `.tsx` file that
contains JSX, nothing in `.jsx`/`.mjs`/`.cjs`/`.mts`, `.astro` only as a whole file, never methods, keys
or `default`. So for these languages livedocs parses the code itself. Every mentioned member carries a
comment- and formatting-insensitive hash; drift is the trigger where it can fingerprint the symbol and
binds the whole file where it can't (the P24 constant pattern, `symbols.Symbol.drift_target`).

What a member is (qualnames):
  top level    function, class, interface, type, enum, namespace, const/let/var (an arrow function or
               function expression is a function; anything else a constant); an anonymous default
               export is `default`
  class        methods, fields, accessors, constructor parameter properties: `Box.area`
  interface    property and method signatures: `Props.title`; also `type P = { … }`
  enum         members: `Color.Red`
  object keys  of a top-level object literal, through `as`/`satisfies` and the first argument of a call
               (`defineConfig({…})`, `z.object({…}).strict()`): `SET_TOKENS.kitchen.background`
  closures     functions declared directly in a top-level function's body: `boot.probeStep`
  .astro       the component (`default`, aliased by the file name) and the frontmatter's declarations
"""

from __future__ import annotations

import functools
import hashlib
import posixpath
import re
from dataclasses import dataclass, field

TS_EXTS = (".ts", ".tsx", ".mts", ".cts", ".js", ".jsx", ".mjs", ".cjs")
ASTRO_EXTS = (".astro",)
EXTS = TS_EXTS + ASTRO_EXTS
# Where drift v0.10.1 can fingerprint a top-level symbol. `.tsx` works only while the file has no JSX,
# which a component file nearly always has, so it is never relied on.
DRIFT_SYMBOL_EXTS = (".ts", ".js")

FUNCTION, CLASS, METHOD, ATTRIBUTE, CONSTANT = "function", "class", "method", "attribute", "constant"
INTERFACE, TYPE, ENUM, NAMESPACE, KEY, COMPONENT = "interface", "type", "enum", "namespace", "key", "component"
LOCAL = "local"  # a function declared directly inside a top-level function: `boot.probeStep`

MAX_KEY_DEPTH = 4  # SET_TOKENS.a.b.c.d
MAX_KEYS = 300  # per top-level constant: a data table is not a config


def is_ts(path: str) -> bool:
    return path.endswith(EXTS)


class Unavailable(RuntimeError):
    pass


@functools.cache
def _parser(grammar: str):
    try:
        import tree_sitter_typescript as tst
        from tree_sitter import Language, Parser
    except ImportError as e:  # pragma: no cover - the wheels are dependencies
        raise Unavailable("TypeScript support needs the tree-sitter and tree-sitter-typescript packages") from e
    return Parser(Language(tst.language_typescript() if grammar == "ts" else tst.language_tsx()))


def available() -> bool:
    try:
        _parser("ts")
        return True
    except Unavailable:
        return False


def _grammar(path: str) -> str:
    # `<T>x` is a cast in .ts and a JSX tag in .tsx; JS may contain JSX, so it parses as TSX.
    return "ts" if path.endswith((".ts", ".mts", ".cts", ".astro")) else "tsx"


# --- the parsed module -------------------------------------------------------


@dataclass
class Decl:
    qualname: str
    kind: str
    nodes: list  # whose canonical form is this member's substance (overloads and merged declarations add more)
    span: tuple[int, int]  # byte range shown as was/now
    lineno: int
    end_lineno: int
    prefix: tuple[str, ...] = ()  # tokens outside the nodes that belong to it: export, default, const
    decorators: list = field(default_factory=list)  # decorator nodes
    sig_nodes: list = field(default_factory=list)  # signature-bearing nodes (function-likes, class heads)
    shell: bool = False  # class-like: the hash covers the shell, not member bodies
    extra: tuple[str, ...] = ()  # .astro component: the normalised template


@dataclass
class Module:
    ok: bool  # parsed without syntax errors
    source: bytes  # what was parsed (for .astro: the frontmatter, line-aligned)
    full: str = ""  # the whole file (an Astro component's source is frontmatter plus template)
    decls: dict[str, Decl] = field(default_factory=dict)
    aliases: dict[str, str] = field(default_factory=dict)  # exported name → local qualname (`export { a as b }`)
    reexports: list[tuple[str, str, str]] = field(default_factory=list)  # (exported name, specifier, imported name)
    default: str | None = None  # qualname of the default export
    exported: set[str] = field(default_factory=set)  # local names an `export { … }` clause exports


def module(path: str, source: str | None) -> Module | None:
    if source is None:
        return None
    return _module(_grammar(path), path.endswith(ASTRO_EXTS), source)


@functools.lru_cache(maxsize=256)
def _module(grammar: str, astro: bool, source: str) -> Module:
    source = source.removeprefix("\ufeff")  # a byte-order mark is not code
    template = None
    if astro:
        fm, template, tline = split_astro(source)
        code = fm
    else:
        code = source
    data = code.encode("utf-8")
    tree = _parser(grammar).parse(data)
    m = Module(ok=not tree.root_node.has_error, source=data, full=source)
    _Walker(m).program(tree.root_node)
    if astro:
        root = tree.root_node
        props = m.decls.get("Props")
        nlines = source.count("\n") + 1
        m.decls["default"] = Decl("default", COMPONENT, [root], (0, len(data)), tline + 1, nlines,
                                  sig_nodes=list(props.nodes) if props else [],
                                  extra=tuple(normalise_template(template).split(" ")))
        m.default = "default"
    return m


_FENCE = re.compile(r"^---\s*$")


def split_astro(source: str) -> tuple[str, str, int]:
    """(frontmatter as a line-aligned TS source, template, 0-based line where the template starts)."""
    lines = source.split("\n")
    i = 0
    while i < len(lines) and not lines[i].strip():
        i += 1
    if i < len(lines) and _FENCE.match(lines[i]):
        for j in range(i + 1, len(lines)):
            if _FENCE.match(lines[j]):
                fm = "\n" * (i + 1) + "\n".join(lines[i + 1:j])  # keeps line numbers aligned with the file
                return fm, "\n".join(lines[j + 1:]), j + 1
    return "", source, 0


_HTML_COMMENT = re.compile(r"<!--.*?-->", re.S)
_JSX_COMMENT = re.compile(r"\{\s*/\*.*?\*/\s*\}", re.S)
_SCRIPT = re.compile(r"(<script\b[^>]*>)(.*?)(</script\s*>)", re.S | re.I)
_STYLE = re.compile(r"(<style\b[^>]*>)(.*?)(</style\s*>)", re.S | re.I)
_CSS_COMMENT = re.compile(r"/\*.*?\*/", re.S)


def _script_canon(code: str) -> str:
    tree = _parser("ts").parse(code.encode("utf-8"))
    if tree.root_node.has_error:  # not TS (JSON-LD, a template language): compare it as text
        return code
    return "\x1e".join(tokens([tree.root_node]))


def normalise_template(t: str) -> str:
    """An Astro template without comments, whitespace collapsed: formatting-insensitive, not a parse.
    `<script>` bodies compare as TS tokens and `<style>` bodies without CSS comments."""
    t = _SCRIPT.sub(lambda m: f"{m.group(1)} {_script_canon(m.group(2))} {m.group(3)}", t or "")
    t = _STYLE.sub(lambda m: m.group(1) + _CSS_COMMENT.sub(" ", m.group(2)) + m.group(3), t)
    t = _HTML_COMMENT.sub(" ", t)
    t = _JSX_COMMENT.sub(" ", t)
    return " ".join(t.split())


def _text(n) -> str:
    return n.text.decode("utf-8", "replace") if n is not None else ""


def _string_value(n) -> str:
    return "".join(_text(c) for c in n.children if c.type not in ('"', "'"))


_IDENT = re.compile(r"^[A-Za-z_$][A-Za-z0-9_$]*$")
FUNC_VALUES = frozenset({"arrow_function", "function_expression", "function", "generator_function"})
_WRAPPERS = frozenset({"as_expression", "satisfies_expression", "non_null_expression", "parenthesized_expression"})
_DECLS = frozenset({
    "function_declaration", "generator_function_declaration", "function_signature", "class_declaration",
    "abstract_class_declaration", "interface_declaration", "type_alias_declaration", "enum_declaration",
    "lexical_declaration", "variable_declaration", "internal_module", "module", "ambient_declaration",
})


def _unwrap(n):
    while n is not None and n.type in _WRAPPERS:
        inner = [c for c in n.named_children if c.type != "comment"]
        if not inner:
            break
        n = inner[0]
    return n


def _name(n) -> str | None:
    nm = n.child_by_field_name("name")
    if nm is None:
        return None
    if nm.type == "string":
        s = _string_value(nm)
        return s if _IDENT.match(s) else None
    s = _text(nm)
    return s if _IDENT.match(s.lstrip("#")) else None


class _Walker:
    def __init__(self, m: Module):
        self.m = m

    def add(self, qualname: str, kind: str, node, *, show=None, prefix=(), decorators=(), sig=(), shell=False) -> Decl:
        show = show if show is not None else node
        d = self.m.decls.get(qualname)
        if d is not None:  # overload signatures, declaration merging, get/set pairs
            d.nodes.append(node)
            d.span = (min(d.span[0], show.start_byte), max(d.span[1], show.end_byte))
            d.end_lineno = max(d.end_lineno, show.end_point[0] + 1)
            d.decorators.extend(decorators)
            d.sig_nodes.extend(sig)
            return d
        d = Decl(qualname, kind, [node], (show.start_byte, show.end_byte), show.start_point[0] + 1,
                 show.end_point[0] + 1, tuple(prefix), list(decorators), list(sig), shell)
        self.m.decls[qualname] = d
        return d

    # statements ------------------------------------------------------------

    def program(self, root) -> None:
        for st in root.named_children:
            self.statement(st)

    def statement(self, st) -> None:
        t = st.type
        if t == "export_statement":
            self.export(st)
        elif t in _DECLS:
            self.declaration(st, wrapper=None, default=False, decorators=[])
        elif t == "expression_statement":
            self.commonjs(st)

    def export(self, st) -> None:
        decos = [c for c in st.children if c.type == "decorator"]
        is_default = any(c.type == "default" for c in st.children)
        decl = st.child_by_field_name("declaration")
        if decl is not None:
            self.declaration(decl, wrapper=st, default=is_default, decorators=decos)
            return
        val = st.child_by_field_name("value")
        if is_default and val is not None:
            v = _unwrap(val)
            if v.type == "identifier":  # export default Header
                self.m.default = _text(v)
                self.m.exported.add(_text(v))
                return
            kind = FUNCTION if v.type in FUNC_VALUES else CLASS if v.type == "class" else CONSTANT
            self.add("default", kind, st, prefix=(), sig=[v] if kind != CONSTANT else [], shell=kind == CLASS)
            if kind == CONSTANT:
                self.keys(v, "default", 1, [0])
            elif kind == CLASS:
                self.class_body(v.child_by_field_name("body"), "default")
            self.m.default = "default"
            return
        source = st.child_by_field_name("source")
        for clause in (c for c in st.named_children if c.type == "export_clause"):
            for spec in clause.named_children:
                if spec.type != "export_specifier":
                    continue
                n = _text(spec.child_by_field_name("name"))
                alias_node = spec.child_by_field_name("alias")
                a = _text(alias_node) if alias_node is not None else n
                if source is not None:
                    if a != n or n == "default":  # renames only: same-name re-exports resolve to the definition
                        self.m.reexports.append((a, _string_value(source), n))
                elif a == "default":
                    self.m.default = n
                    self.m.exported.add(n)
                else:
                    self.m.exported.add(n)
                    if a != n:
                        self.m.aliases[a] = n

    def commonjs(self, st) -> None:
        # module.exports = { … } is a CommonJS config file's default export
        e = st.named_children[0] if st.named_children else None
        if e is None or e.type != "assignment_expression":
            return
        left = e.child_by_field_name("left")
        if left is not None and _text(left).replace(" ", "") == "module.exports":
            right = _unwrap(e.child_by_field_name("right"))
            kind = FUNCTION if right is not None and right.type in FUNC_VALUES else CONSTANT
            self.add("default", kind, st)
            if right is not None and kind == CONSTANT:
                self.keys(right, "default", 1, [0])
            self.m.default = "default"

    def declaration(self, decl, *, wrapper, default: bool, decorators: list, scope: str = "") -> None:
        t = decl.type
        prefix = (("export",) if wrapper is not None else ()) + (("default",) if default else ())
        show = wrapper if wrapper is not None else decl
        q = lambda n: f"{scope}{n}"
        if t == "ambient_declaration":
            for inner in decl.named_children:
                if inner.type in _DECLS and inner.type not in ("internal_module", "module"):
                    self.declaration(inner, wrapper=wrapper, default=default, decorators=decorators, scope=scope)
            return
        name = _name(decl)
        if t in ("function_declaration", "generator_function_declaration", "function_signature"):
            if name:
                self.add(q(name), FUNCTION, decl, show=show, prefix=prefix, decorators=decorators, sig=[decl])
                if not scope:
                    self.locals(decl.child_by_field_name("body"), name)
                if default and not scope:
                    self.m.default = name
        elif t in ("class_declaration", "abstract_class_declaration"):
            if name:
                decos = decorators + [c for c in decl.children if c.type == "decorator"]
                self.add(q(name), CLASS, decl, show=show, prefix=prefix, decorators=decos, sig=[decl], shell=True)
                self.class_body(decl.child_by_field_name("body"), q(name))
                if default and not scope:
                    self.m.default = name
        elif t == "interface_declaration":
            if name:
                self.add(q(name), INTERFACE, decl, show=show, prefix=prefix)
                self.type_members(decl.child_by_field_name("body"), q(name))
        elif t == "type_alias_declaration":
            if name:
                self.add(q(name), TYPE, decl, show=show, prefix=prefix)
                v = decl.child_by_field_name("value")
                if v is not None and v.type == "object_type":
                    self.type_members(v, q(name))
        elif t == "enum_declaration":
            if name:
                self.add(q(name), ENUM, decl, show=show, prefix=prefix)
                body = decl.child_by_field_name("body")
                for c in (body.named_children if body is not None else ()):
                    n = _name(c) if c.type == "enum_assignment" else (_text(c) if c.type == "property_identifier" else None)
                    if n:
                        self.add(f"{q(name)}.{n}", ATTRIBUTE, c)
        elif t in ("lexical_declaration", "variable_declaration"):
            kind_tok = _text(decl.child_by_field_name("kind")) if decl.child_by_field_name("kind") is not None else "var"
            for d in decl.named_children:
                if d.type != "variable_declarator":
                    continue
                nm = d.child_by_field_name("name")
                if nm is None or nm.type != "identifier":
                    continue  # destructuring binds no single symbol
                n = _text(nm)
                v = _unwrap(d.child_by_field_name("value"))
                if v is not None and v.type in FUNC_VALUES:
                    self.add(q(n), FUNCTION, d, show=show, prefix=prefix + (kind_tok,), sig=[d, v])
                    if not scope:
                        self.locals(v.child_by_field_name("body"), q(n))
                elif v is not None and v.type == "class":
                    self.add(q(n), CLASS, d, show=show, prefix=prefix + (kind_tok,), sig=[v], shell=True)
                    self.class_body(v.child_by_field_name("body"), q(n))
                else:
                    self.add(q(n), CONSTANT, d, show=show, prefix=prefix + (kind_tok,))
                    if v is not None:
                        self.keys(v, q(n), 1, [0])
        elif t in ("internal_module", "module"):
            if name and not scope:
                self.add(name, NAMESPACE, decl, show=show, prefix=prefix)
                body = decl.child_by_field_name("body")
                for st in (body.named_children if body is not None else ()):
                    inner = st.child_by_field_name("declaration") if st.type == "export_statement" else st
                    if inner is not None and inner.type in _DECLS:
                        self.declaration(inner, wrapper=None, default=False, decorators=[], scope=f"{name}.")

    # members ---------------------------------------------------------------

    def locals(self, body, owner: str) -> None:
        """Closures: functions declared directly in a top-level function's body (one level)."""
        if body is None or body.type != "statement_block":
            return
        for st in body.named_children:
            if st.type in ("function_declaration", "generator_function_declaration"):
                n = _name(st)
                if n:
                    self.add(f"{owner}.{n}", LOCAL, st, sig=[st])
            elif st.type == "lexical_declaration":
                kt = _text(st.child_by_field_name("kind")) if st.child_by_field_name("kind") is not None else "const"
                for d in st.named_children:
                    nm = d.child_by_field_name("name") if d.type == "variable_declarator" else None
                    v = _unwrap(d.child_by_field_name("value")) if nm is not None else None
                    if nm is not None and nm.type == "identifier" and v is not None and v.type in FUNC_VALUES:
                        self.add(f"{owner}.{_text(nm)}", LOCAL, d, prefix=(kt,), sig=[d, v])

    def class_body(self, body, cls: str) -> None:
        if body is None:
            return
        pending: list = []
        for c in body.named_children:
            t = c.type
            if t == "decorator":
                pending.append(c)
                continue
            if t in ("method_definition", "method_signature", "abstract_method_signature"):
                n = _name(c)
                if n:
                    # a get/set accessor is a property to its readers, so it is an attribute
                    accessor = any(x.type in ("get", "set") for x in c.children)
                    self.add(f"{cls}.{n}", ATTRIBUTE if accessor else METHOD, c, decorators=pending, sig=[c])
                    if n == "constructor":
                        self.parameter_properties(c, cls)
            elif t == "public_field_definition":
                n = _name(c)
                if n:
                    self.add(f"{cls}.{n}", ATTRIBUTE, c, decorators=pending + [d for d in c.children if d.type == "decorator"])
            pending = []

    def parameter_properties(self, ctor, cls: str) -> None:
        params = ctor.child_by_field_name("parameters")
        for p in (params.named_children if params is not None else ()):
            if p.type not in ("required_parameter", "optional_parameter"):
                continue
            if not any(c.type in ("accessibility_modifier", "readonly", "override_modifier") for c in p.children):
                continue
            pat = p.child_by_field_name("pattern")
            if pat is not None and pat.type == "identifier":
                self.add(f"{cls}.{_text(pat)}", ATTRIBUTE, p)

    def type_members(self, body, owner: str) -> None:
        for c in (body.named_children if body is not None else ()):
            if c.type in ("property_signature", "method_signature"):
                n = _name(c)
                if n:
                    self.add(f"{owner}.{n}", ATTRIBUTE if c.type == "property_signature" else METHOD, c,
                             sig=[c] if c.type == "method_signature" else [])

    def keys(self, value, prefix: str, depth: int, budget: list[int]) -> None:
        obj = _object_of(value)
        if obj is None:
            return
        for c in obj.named_children:
            if budget[0] >= MAX_KEYS:
                return
            if c.type == "pair":
                k = c.child_by_field_name("key")
                if k is None:
                    continue
                kt = _string_value(k) if k.type == "string" else _text(k) if k.type == "property_identifier" else None
                if not kt or not _IDENT.match(kt):
                    continue
                budget[0] += 1
                self.add(f"{prefix}.{kt}", KEY, c)
                if depth < MAX_KEY_DEPTH:
                    self.keys(c.child_by_field_name("value"), f"{prefix}.{kt}", depth + 1, budget)
            elif c.type in ("method_definition", "shorthand_property_identifier"):
                n = _name(c) if c.type == "method_definition" else _text(c)
                if n and _IDENT.match(n):
                    budget[0] += 1
                    self.add(f"{prefix}.{n}", KEY, c, sig=[c] if c.type == "method_definition" else [])


def _object_of(n):
    """The object literal a value is, or configures: `{…}`, `{…} as const satisfies X`, `defineConfig({…})`,
    `z.object({…}).strict()` (the innermost call in a chain whose first argument is an object)."""
    n = _unwrap(n)
    for _ in range(8):
        if n is None:
            return None
        if n.type == "object":
            return n
        if n.type != "call_expression":
            return None
        args = n.child_by_field_name("arguments")
        first = next((a for a in (args.named_children if args is not None else ()) if a.type != "comment"), None)
        first = _unwrap(first)
        if first is not None and first.type == "object":
            return first
        fn = n.child_by_field_name("function")
        n = _unwrap(fn.child_by_field_name("object")) if fn is not None and fn.type == "member_expression" else None
    return None


# --- canonical form ----------------------------------------------------------

_QUOTES = frozenset({'"', "'"})
_CLOSERS = frozenset({")", "]", "}", ">"})


def _next_real(kids, i):
    for j in range(i + 1, len(kids)):
        if kids[j].type != "comment":
            return kids[j]
    return None


def tokens(nodes) -> list[str]:
    """The structure and tokens of `nodes`, insensitive to comments, whitespace, quote style, optional
    semicolons, trailing commas and redundant parentheses. Grouping survives: the inner expression is a
    subtree of its own, so `(a + b) * c` and `a + b * c` stay different."""
    out: list[str] = []
    stack: list = list(reversed(list(nodes)))
    while stack:
        n = stack.pop()
        if isinstance(n, str):
            out.append(n)
            continue
        t = n.type
        if t == "comment":
            continue
        if t == "parenthesized_expression":
            inner = [c for c in n.named_children if c.type != "comment"]
            if len(inner) == 1:
                stack.append(inner[0])
                continue
        if t == "jsx_expression" and all(c.type == "comment" for c in n.named_children):
            continue  # {/* a JSX comment */}
        if n.child_count == 0:
            if t in _QUOTES or t == ";":
                continue
            s = _text(n)
            if t == "jsx_text":
                s = _jsx_text(s)
                if not s:
                    continue
            out.append(s)
            continue
        if t == "string":
            out.append("S:" + _string_value(n))
            continue
        out.append("(" + t)
        stack.append(")")
        kids = n.children
        keep = [c for i, c in enumerate(kids)
                if not (c.type == "," and ((nx := _next_real(kids, i)) is None or nx.type in _CLOSERS))]
        stack.extend(reversed(keep))
    return out


def _jsx_text(s: str) -> str:
    """JSX text as React renders it: whitespace that contains a line break disappears (lines are trimmed
    and joined with one space), other runs become one space. So reflowing text is formatting, but
    `<b>x</b> y` and `<b>x</b>y` stay different."""
    lines = s.split("\n")
    kept = []
    for i, line in enumerate(lines):
        if i > 0:
            line = line.lstrip()
        if i < len(lines) - 1:
            line = line.rstrip()
        if line:
            kept.append(line)
    return re.sub(r"[ \t]+", " ", " ".join(kept))


def _digest(parts: list[str]) -> str:
    return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()[:16]


def _fields_except(n, skip_fields=frozenset({"body"}), skip_types=frozenset({"decorator", "comment"})) -> list:
    out = []
    for i, c in enumerate(n.children):
        if n.field_name_for_child(i) in skip_fields or c.type in skip_types:
            continue
        out.append(c)
    return out


def _signature(d: Decl) -> list[str]:
    """Signature tokens: name, type parameters, parameters, return type, modifiers; a class's head; an
    Astro component's Props. Bodies are excluded."""
    parts: list[str] = []
    for n in d.sig_nodes:
        if n.type == "variable_declarator":  # const f: FC<P> = …  — the annotation is part of the signature
            ann = n.child_by_field_name("type")
            parts += ["T"] + (tokens([ann]) if ann is not None else [])
        elif n.type in ("class_declaration", "abstract_class_declaration", "class"):
            parts += tokens(_fields_except(n))
        elif d.kind == COMPONENT:
            parts += tokens([n])
        else:
            parts += tokens(_fields_except(n))
    return parts


def _shell(d: Decl) -> list[str]:
    """A class's shell: head, decorators, fields with their types and initialisers, method names and
    modifiers — not method bodies or parameters (a note that names the class, not the method, doesn't
    depend on them; same rule as the Python class shell)."""
    parts = list(d.prefix) + [p for dn in d.decorators for p in tokens([dn])] + _signature(d)
    # The class node is a signature node (a declaration, or the `class` expression of a const or of an
    # anonymous default export); its body holds the members.
    classes = [n for n in d.sig_nodes if n.type in ("class_declaration", "abstract_class_declaration", "class")]
    for node in classes:
        body = node.child_by_field_name("body")
        for c in (body.named_children if body is not None else ()):
            t = c.type
            if t in ("method_definition", "method_signature", "abstract_method_signature"):
                parts += ["M"] + tokens(_fields_except(c, frozenset({"body", "parameters", "return_type", "type_parameters"})))
                if _name(c) == "constructor":
                    params = c.child_by_field_name("parameters")
                    for p in (params.named_children if params is not None else ()):
                        if any(x.type in ("accessibility_modifier", "readonly", "override_modifier") for x in p.children):
                            parts += tokens([p])
            elif t in ("public_field_definition", "class_static_block", "index_signature", "decorator"):
                parts += tokens([c])
    return parts


def _payload(d: Decl, full: bool) -> list[str]:
    if d.shell and not full:
        return _shell(d)
    return list(d.prefix) + [p for dn in d.decorators for p in tokens([dn])] + tokens(d.nodes) + list(d.extra)


# --- the astdiff interface ---------------------------------------------------


def parses(path: str, source: str | None) -> bool:
    m = module(path, source)
    return m is not None and m.ok


def find(path: str, source: str | None, qualname: str) -> Decl | None:
    m = module(path, source)
    if m is None or not m.ok:
        return None
    d = m.decls.get(qualname)
    if d is None and qualname in m.aliases:
        d = m.decls.get(m.aliases[qualname])
    return d


def symbol_source(path: str, source: str | None, qualname: str) -> str | None:
    d = find(path, source, qualname)
    if d is None:
        return None
    m = module(path, source)
    if d.kind == COMPONENT:  # the whole component: was/now and "unchanged" must see the template too
        return m.full
    return m.source[d.span[0]:d.span[1]].decode("utf-8", "replace")


def member_hash(path: str, source: str | None, qualname: str) -> str | None:
    d = find(path, source, qualname)
    return _digest(_payload(d, full=False)) if d is not None else None


def full_hash(path: str, source: str | None, qualname: str) -> str | None:
    d = find(path, source, qualname)
    return _digest(_payload(d, full=True)) if d is not None else None


def signature_hash(path: str, source: str | None, qualname: str) -> str:
    d = find(path, source, qualname)
    return _digest(_signature(d)) if d is not None and d.sig_nodes else ""


def file_hash(path: str, source: str | None) -> str | None:
    """The whole module, comment- and formatting-insensitive (a whole-file anchor's benign test)."""
    m = module(path, source)
    if m is None or not m.ok:
        return None
    from_tree = tokens([_parser(_grammar(path)).parse(m.source).root_node])
    extra = list(m.decls["default"].extra) if path.endswith(ASTRO_EXTS) and "default" in m.decls else []
    return _digest(from_tree + extra)


def decorator_hash(path: str, source: str | None, top_level_name: str) -> str:
    d = find(path, source, top_level_name)
    if d is None or not d.decorators:
        return ""
    return _digest([p for dn in d.decorators for p in tokens([dn])])


# --- index-level facts -------------------------------------------------------


@dataclass
class FileSymbols:
    symbols: list[tuple[str, str, int, int, tuple[str, ...]]]  # (qualname, kind, lineno, end_lineno, decorators)
    default: str | None
    aliases: dict[str, str]
    reexports: list[tuple[str, str, str]]


def file_symbols(path: str, source: str) -> FileSymbols:
    m = module(path, source)
    if m is None:
        return FileSymbols([], None, {}, [])
    syms = [(d.qualname, d.kind, d.lineno, d.end_lineno, tuple(_text(x) for x in d.decorators)) for d in m.decls.values()]
    return FileSymbols(syms, m.default, dict(m.aliases), list(m.reexports))


def default_alias(path: str) -> str | None:
    """The name a default export is imported under: its file's stem (`Header.tsx` → `Header`), or the
    folder's for an index module (`components/index.ts` → `components`)."""
    stem = posixpath.basename(path)
    stem = stem[: -len(next(e for e in EXTS if stem.endswith(e)))] if stem.endswith(EXTS) else stem
    if stem == "index" and not path.endswith(ASTRO_EXTS):
        stem = posixpath.basename(posixpath.dirname(path))
    return stem if _IDENT.match(stem) else None


def resolve_specifier(from_path: str, spec: str, files: set[str], path_aliases: list[tuple[str, list[str]]] = ()) -> str | None:
    """A module specifier → a tracked file: relative paths, tsconfig `paths` aliases, extensionless and
    `index` forms, and the ESM-in-TS convention of importing `./x.js` for `./x.ts`."""
    if spec.startswith("."):
        bases = [posixpath.normpath(posixpath.join(posixpath.dirname(from_path), spec))]
    else:
        bases = alias_targets(spec, path_aliases)
    for base in bases:
        hit = file_for(base, files)
        if hit:
            return hit
    return None


def file_for(base: str, files: set[str]) -> str | None:
    base = base.removeprefix("./")
    if base in files:
        return base
    stem = re.sub(r"\.(m|c)?jsx?$", "", base)
    if stem != base:  # import './x.js' resolves to x.ts
        for e in (".ts", ".tsx", ".mts", ".cts"):
            if stem + e in files:
                return stem + e
    for e in EXTS:
        if base + e in files:
            return base + e
    for e in EXTS:
        if f"{base}/index{e}" in files:
            return f"{base}/index{e}"
    return None


def alias_targets(spec: str, path_aliases) -> list[str]:
    out = []
    for pattern, targets in path_aliases:
        if pattern.endswith("*"):
            if spec.startswith(pattern[:-1]):
                rest = spec[len(pattern) - 1:]
                out += [t[:-1] + rest if t.endswith("*") else t for t in targets]
        elif spec == pattern:
            out += [t for t in targets]
    return out


# --- tsconfig ----------------------------------------------------------------


def jsonc_loads(text: str):
    """JSON with comments and trailing commas (tsconfig.json, wrangler.jsonc)."""
    import json
    out, i, n, in_str = [], 0, len(text), False
    while i < n:
        ch = text[i]
        if in_str:
            out.append(ch)
            if ch == "\\" and i + 1 < n:
                out.append(text[i + 1])
                i += 2
                continue
            if ch == '"':
                in_str = False
            i += 1
            continue
        if ch == '"':
            in_str = True
            out.append(ch)
            i += 1
        elif text.startswith("//", i):
            j = text.find("\n", i)
            i = n if j < 0 else j
        elif text.startswith("/*", i):
            j = text.find("*/", i + 2)
            i = n if j < 0 else j + 2
        else:
            out.append(ch)
            i += 1
    cleaned = re.sub(r",(\s*[}\]])", r"\1", "".join(out))
    return json.loads(cleaned)


def path_aliases(read) -> list[tuple[str, list[str]]]:
    """tsconfig/jsconfig `compilerOptions.paths`, made repo-relative through `baseUrl`, following
    `extends` within the repository. `read(path)` returns a file's text or None."""
    for root_cfg in ("tsconfig.json", "jsconfig.json"):
        txt = read(root_cfg)
        if txt is None:
            continue
        seen: set[str] = set()
        cfg_path, merged_paths, base_url = root_cfg, None, None
        while cfg_path and cfg_path not in seen:
            seen.add(cfg_path)
            try:
                data = jsonc_loads(txt)
            except ValueError:
                break
            opts = data.get("compilerOptions") or {}
            here = posixpath.dirname(cfg_path)
            if base_url is None and "baseUrl" in opts:
                base_url = posixpath.normpath(posixpath.join(here, opts["baseUrl"]))
            if merged_paths is None and "paths" in opts:
                merged_paths = (opts["paths"], here)
            ext = data.get("extends")
            cfg_path = None
            if isinstance(ext, str) and ext.startswith("."):
                cfg_path = posixpath.normpath(posixpath.join(here, ext if ext.endswith(".json") else ext + ".json"))
                txt = read(cfg_path)
                if txt is None:
                    break
        if not merged_paths:
            return []
        paths, here = merged_paths
        base = base_url if base_url is not None else here
        out = []
        for pattern, targets in paths.items():
            if isinstance(targets, list):
                out.append((pattern, [posixpath.normpath(posixpath.join(base, t)).removeprefix("./")
                                      for t in targets if isinstance(t, str)]))
        return out
    return []
