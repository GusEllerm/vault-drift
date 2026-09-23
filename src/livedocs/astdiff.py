"""Symbol source at two versions of a file, and what kind of change happened.

Kinds: signature | decorator | body | comment-or-docstring-only | unchanged | removed | added
"""

from __future__ import annotations

import ast
import hashlib
from dataclasses import dataclass

SIGNATURE, DECORATOR, BODY, COMMENT_ONLY, UNCHANGED, REMOVED, ADDED, UNPARSEABLE = (
    "signature", "decorator", "body", "comment-or-docstring-only", "unchanged", "removed", "added", "unparseable",
)


def parses(source: str | None) -> bool:
    if source is None:
        return False
    try:
        ast.parse(source)
        return True
    except SyntaxError:
        return False


def _find(tree: ast.Module, qualname: str) -> ast.AST | None:
    parts = qualname.split(".")
    scope: list[ast.stmt] = tree.body
    node: ast.AST | None = None
    for i, part in enumerate(parts):
        node = None
        for n in scope:
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and n.name == part:
                node = n
                break
            if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == part for t in n.targets):
                node = n
                break
            if isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name) and n.target.id == part:
                node = n
                break
        if node is None:
            return None
        if i < len(parts) - 1:
            if not isinstance(node, ast.ClassDef):
                return None
            scope = node.body
    return node


def symbol_source(source: str, qualname: str) -> str | None:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None
    node = _find(tree, qualname)
    if node is None:
        return None
    seg = ast.get_source_segment(source, node, padded=True)
    if seg is None:
        return None
    decos = getattr(node, "decorator_list", ())
    if decos:  # get_source_segment starts at `def`; include decorator lines
        lines = source.splitlines()
        start = min(d.lineno for d in decos) - 1
        end = (node.end_lineno or node.lineno)
        seg = "\n".join(lines[start:end])
    return seg


def decorator_hash(source: str, top_level_name: str) -> str:
    """Hash of a top-level symbol's decorators (empty string if none or unparseable)."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return ""
    node = _find(tree, top_level_name)
    decos = getattr(node, "decorator_list", ()) if node is not None else ()
    if not decos:
        return ""
    return hashlib.sha256("\n".join(ast.unparse(d) for d in decos).encode()).hexdigest()[:16]


def _strip_docstrings(node: ast.AST) -> ast.AST:
    for n in ast.walk(node):
        body = getattr(n, "body", None)
        if isinstance(body, list) and body and isinstance(body[0], ast.Expr) and isinstance(getattr(body[0], "value", None), ast.Constant) and isinstance(body[0].value.value, str):
            n.body = body[1:] or [ast.Pass()]
    return node


def _dump(node: ast.AST) -> str:
    return ast.dump(node, include_attributes=False)


def _sig_dump(node: ast.AST) -> str:
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return node.name + _dump(node.args) + (_dump(node.returns) if node.returns else "")
    if isinstance(node, ast.ClassDef):
        return node.name + "".join(_dump(b) for b in node.bases) + "".join(_dump(k) for k in node.keywords)
    return ""


@dataclass(frozen=True)
class Change:
    kind: str
    was: str | None
    now: str | None


def classify(old_source: str | None, new_source: str | None, qualname: str) -> Change:
    if new_source is not None and not parses(new_source):
        return Change(UNPARSEABLE, symbol_source(old_source, qualname) if old_source else None, None)
    old = symbol_source(old_source, qualname) if old_source is not None else None
    new = symbol_source(new_source, qualname) if new_source is not None else None
    if old is None and new is None:
        return Change(REMOVED, None, None)
    if old is None:
        return Change(ADDED, None, new)
    if new is None:
        return Change(REMOVED, old, None)
    if old == new:
        return Change(UNCHANGED, old, new)
    on, nn = _find(ast.parse(old_source), qualname), _find(ast.parse(new_source), qualname)
    if _sig_dump(on) != _sig_dump(nn):
        return Change(SIGNATURE, old, new)
    if [ast.unparse(d) for d in getattr(on, "decorator_list", ())] != [ast.unparse(d) for d in getattr(nn, "decorator_list", ())]:
        return Change(DECORATOR, old, new)
    if _dump(_strip_docstrings(on)) == _dump(_strip_docstrings(nn)):
        return Change(COMMENT_ONLY, old, new)
    return Change(BODY, old, new)


def first_line(src: str | None) -> str:
    """The def/class line (after decorators), for compact was/now output."""
    if not src:
        return ""
    for l in src.splitlines():
        s = l.strip()
        if s and not s.startswith("@"):
            return s
    return src.splitlines()[0].strip()
