"""`livedocs signatures`: exported API signatures that a commit changes, added or removed.

For a gate that treats a public API change as a decision (Baesian's `api:<qualname>` facts). Compares the
staged index with HEAD (`--cached`; the empty tree before the first commit) or a commit with its first
parent (`--rev`). Python and TypeScript/JavaScript/Astro, using the same parsers as the rest of livedocs.

Exported:
  Python  names in `__all__` when the module defines it, else names without a leading underscore; public
          methods (and dunders such as `__init__`) and attributes of exported classes.
  TS/JS   declarations marked `export`, names in an `export { … }` clause, the default export; members of
          exported classes that are not `#private` or `private`, members of exported interfaces via the
          interface. "Exported anywhere": re-export reachability from an entry point is not computed.
Signature:
  functions/methods  name, parameters with their defaults, return type, type parameters, async/generator
  classes            name, type parameters, heritage (Python: bases and keywords)
  fields/attributes  name, modifiers and type (TS); the whole assignment (Python: a dataclass default is API)
  interfaces/types/enums/namespaces  everything (they have no body)
  constants          a declared type annotation only
Bodies, comments, formatting and decorators never count. A symbol that moves files is `removed` from one
path and `added` to the other.
"""

from __future__ import annotations

import ast
import json
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path

from . import config, gitx, symbols as sy, ts


@dataclass
class Change:
    path: str
    qualname: str
    kind: str  # "signature" | "added" | "removed"
    was: str | None
    now: str | None


# --- Python -------------------------------------------------------------------


def _py_api(source: str) -> dict[str, tuple[str, str]]:
    """qualname → (comparison key, display text) for the exported API of a Python module."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return {}
    explicit = _dunder_all(tree)
    public = (lambda n: n in explicit) if explicit is not None else (lambda n: not n.startswith("_"))
    member = lambda n: not n.startswith("_") or (n.startswith("__") and n.endswith("__"))
    out: dict[str, tuple[str, str]] = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and public(node.name):
            out[node.name] = _py_func(node)
        elif isinstance(node, ast.ClassDef) and public(node.name):
            out[node.name] = _py_class(node)
            for sub in node.body:
                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)) and member(sub.name):
                    out[f"{node.name}.{sub.name}"] = _py_func(sub)
                elif isinstance(sub, (ast.Assign, ast.AnnAssign)):
                    for t in (sub.targets if isinstance(sub, ast.Assign) else [sub.target]):
                        if isinstance(t, ast.Name) and member(t.id):
                            out[f"{node.name}.{t.id}"] = (_dump(sub), ast.unparse(sub))
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and public(node.target.id):
            out[node.target.id] = ("const:" + _dump(node.annotation), f"{node.target.id}: {ast.unparse(node.annotation)}")
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and public(t.id) and t.id != "__all__":
                    out[t.id] = ("const:", t.id)  # untyped constant: only added/removed count
    return out


def _dunder_all(tree: ast.Module) -> set[str] | None:
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "__all__" for t in node.targets):
            if isinstance(node.value, (ast.List, ast.Tuple)):
                return {e.value for e in node.value.elts if isinstance(e, ast.Constant) and isinstance(e.value, str)}
    return None


def _dump(node: ast.AST) -> str:
    from .astdiff import _stable_dump
    return _stable_dump(node)


def _py_func(n) -> tuple[str, str]:
    key = type(n).__name__ + n.name + _dump(n.args) + (_dump(n.returns) if n.returns else "")
    text = f"{'async ' if isinstance(n, ast.AsyncFunctionDef) else ''}def {n.name}({ast.unparse(n.args)})"
    return key, text + (f" -> {ast.unparse(n.returns)}" if n.returns else "")


def _py_class(n: ast.ClassDef) -> tuple[str, str]:
    heads = [ast.unparse(b) for b in n.bases] + [ast.unparse(k) for k in n.keywords]
    key = n.name + "".join(_dump(b) for b in n.bases) + "".join(_dump(k) for k in n.keywords)
    return key, f"class {n.name}" + (f"({', '.join(heads)})" if heads else "")


# --- TypeScript / JavaScript / Astro ------------------------------------------

_NO_BODY = (ts.INTERFACE, ts.TYPE, ts.ENUM, ts.NAMESPACE)


def _ts_api(path: str, source: str) -> dict[str, tuple[str, str]]:
    m = ts.module(path, source)
    if m is None or not m.ok:
        return {}
    # local top-level name → the names it is exported under (`export { helper as util }` exports `util`)
    public: dict[str, set[str]] = {}
    for q, d in m.decls.items():
        if "." not in q and "export" in d.prefix:
            public.setdefault(q, set()).add(q)
    renamed = {local for local in m.aliases.values()}
    for local in m.exported:
        if local not in renamed:
            public.setdefault(local, set()).add(local)
    for alias, local in m.aliases.items():
        public.setdefault(local, set()).add(alias)
    if m.default and m.default not in public:
        public[m.default] = {m.default}
    out: dict[str, tuple[str, str]] = {}
    for q, d in m.decls.items():
        top, _, rest = q.partition(".")
        if top not in public or d.kind in (ts.LOCAL, ts.KEY):
            continue
        if rest and m.decls[top].kind in _NO_BODY:
            continue  # an interface's or enum's members are part of the interface's own signature
        if rest and (rest.startswith("#") or _is_private(d)):
            continue
        sig = (_ts_key(d), _ts_text(m, d))
        for name in public[top]:
            out[name + ("." + rest if rest else "")] = sig
    return out


def _is_private(d: "ts.Decl") -> bool:
    node = d.nodes[0]
    return any(c.type == "accessibility_modifier" and ts._text(c) == "private" for c in node.children)


def _ts_key(d: "ts.Decl") -> str:
    if d.kind in _NO_BODY:
        return "|".join(ts._payload(d, full=True))
    if d.kind == ts.COMPONENT:  # an Astro component's API is its Props
        return "|".join(ts._signature(d))
    if d.kind == ts.ATTRIBUTE:  # a field: name, modifiers, type; not its initial value
        return "|".join(ts.tokens(ts._fields_except(d.nodes[0], frozenset({"value"}))))
    if d.kind == ts.CONSTANT:
        ann = d.nodes[0].child_by_field_name("type") if d.nodes[0].type == "variable_declarator" else None
        return "const:" + ("|".join(ts.tokens([ann])) if ann is not None else "")
    return "|".join(list(d.prefix) + ts._signature(d))


def _ts_text(m: "ts.Module", d: "ts.Decl") -> str:
    """The signature as written, whitespace collapsed: the declaration up to its body or initial value."""
    if d.kind == ts.COMPONENT:
        props = m.decls.get("Props")
        return "Props " + _collapse(ts._text(props.nodes[0])) if props else "(no Props)"
    node = d.nodes[-1]
    stop = None
    if d.kind not in _NO_BODY:
        target = node
        if node.type == "variable_declarator":
            v = ts._unwrap(node.child_by_field_name("value"))
            if d.kind == ts.FUNCTION and v is not None and v.type in ts.FUNC_VALUES:
                target = v
            else:
                stop = node.child_by_field_name("value")
        body = target.child_by_field_name("body") if stop is None else None
        stop = body if body is not None else stop
        if stop is None and d.kind == ts.ATTRIBUTE:
            stop = node.child_by_field_name("value")
    end = stop.start_byte if stop is not None else node.end_byte
    text = m.source[node.start_byte:end].decode("utf-8", "replace").rstrip(" =\n\t")
    if node.type == "variable_declarator":
        text = " ".join(t for t in d.prefix if t in ("const", "let", "var")) + " " + text
    return _collapse(text)


def _collapse(s: str, limit: int = 300) -> str:
    s = " ".join(s.split())
    return s if len(s) <= limit else s[: limit - 1] + "…"


# --- comparing two versions ---------------------------------------------------


def api(path: str, source: str | None) -> dict[str, tuple[str, str]]:
    if source is None:
        return {}
    if path.endswith(".py"):
        return _py_api(source)
    if ts.is_ts(path):
        return _ts_api(path, source)
    return {}


def compare(path: str, old: str | None, new: str | None) -> list[Change]:
    a, b = api(path, old), api(path, new)
    out: list[Change] = []
    for q in sorted(a.keys() | b.keys()):
        if q not in b:
            out.append(Change(path, q, "removed", a[q][1], None))
        elif q not in a:
            out.append(Change(path, q, "added", None, b[q][1]))
        elif a[q][0] != b[q][0]:
            out.append(Change(path, q, "signature", a[q][1], b[q][1]))
    return out


def _changed(repo: Path, args: list[str]) -> list[tuple[str, str]]:
    out = gitx.run(repo, "diff", "--name-status", "--no-renames", *args)
    return [(l.split("\t", 1)[0][0], l.split("\t", 1)[1]) for l in out.splitlines() if "\t" in l]


def _index_blob(repo: Path, path: str) -> str | None:
    p = subprocess.run(["git", "-C", str(repo), "show", f":{path}"], capture_output=True, text=True, errors="replace")
    return p.stdout if p.returncode == 0 else None


def changes(repo: str | Path, *, rev: str | None = None) -> list[Change]:
    """`rev=None`: the staged index against HEAD (the empty tree before the first commit).
    `rev`: that commit against its first parent (the empty tree for a root commit)."""
    repo = Path(repo)
    if rev is None:
        base = "HEAD" if gitx.has_head(repo) else gitx.empty_tree(repo)
        files = _changed(repo, ["--cached", base])
        old_at = lambda p: gitx.blob_at(repo, base, p)
        new_at = lambda p: _index_blob(repo, p)
    else:
        commit = gitx.run(repo, "rev-parse", "--verify", f"{rev}^{{commit}}").strip()
        parents = gitx.run(repo, "rev-list", "--parents", "-n", "1", commit).split()[1:]
        base = parents[0] if parents else gitx.empty_tree(repo)
        files = _changed(repo, [base, commit])
        old_at = lambda p: gitx.blob_at(repo, base, p)
        new_at = lambda p: gitx.blob_at(repo, commit, p)
    cfg = config.load(repo)
    roots = sy.code_roots(repo)
    out: list[Change] = []
    for status, path in files:
        if not sy.is_code(path) or sy.is_excluded(path) or config.ignored(repo, path, cfg):
            continue
        if roots and not any(path.startswith(r) for r in roots):
            continue
        old = None if status == "A" else old_at(path)
        new = None if status == "D" else new_at(path)
        out += compare(path, old, new)
    return out


def to_json(cs: list[Change]) -> str:
    return json.dumps([asdict(c) for c in cs], indent=1)
