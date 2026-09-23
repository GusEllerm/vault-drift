"""Python symbol index at a git ref, and mention → symbol resolution.

Resolution rules (Implementation Plan §4.2):
  1. path mentions → the file (and symbol if `path#Sym`)
  2. exact qualname
  3. the note's own module
  4. unique top-level name under src/, else unique method name
  5. still ambiguous → all candidates (superset: over-flags, never a false fresh)
  6. nothing → unresolved
drift only anchors top-level symbols, so `drift_target` is always
`path#<top_level_name>`; the qualname is kept for narrowing later.
"""

from __future__ import annotations

import ast
import re
import subprocess
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from .mentions import CAPS, DOTTED, NAME, PATH, Mention

FUNCTION, CLASS, METHOD, ATTRIBUTE, CONSTANT, FILE = "function", "class", "method", "attribute", "constant", "file"


@dataclass(frozen=True)
class Symbol:
    path: str  # repo-relative, e.g. src/hpc_bridge/facility/remote.py
    qualname: str  # SshTarget.preauth_command; "" for a whole file
    kind: str
    lineno: int = 0
    end_lineno: int = 0
    decorators: tuple[str, ...] = ()

    @property
    def name(self) -> str:
        return self.qualname.rsplit(".", 1)[-1]

    @property
    def top_level_name(self) -> str:
        return self.qualname.split(".", 1)[0]

    @property
    def module(self) -> str:
        """Module path without the src prefix and extension: facility/remote."""
        p = self.path
        for prefix in ("src/",):
            if p.startswith(prefix):
                p = p[len(prefix):]
        return re.sub(r"\.py$", "", p)

    @property
    def drift_target(self) -> str:
        if self.kind == FILE:
            return self.path
        return f"{self.path}#{self.top_level_name}"


@dataclass
class SymbolIndex:
    ref: str
    symbols: list[Symbol] = field(default_factory=list)
    files: set[str] = field(default_factory=set)  # indexed .py files under the roots
    all_files: set[str] = field(default_factory=set)  # every tracked file (for path mentions like pyproject.toml)
    _by_qualname: dict[str, list[Symbol]] = field(default_factory=lambda: defaultdict(list))
    _by_name: dict[str, list[Symbol]] = field(default_factory=lambda: defaultdict(list))

    def add(self, s: Symbol) -> None:
        self.symbols.append(s)
        self.files.add(s.path)
        self._by_qualname[s.qualname].append(s)
        self._by_name[s.name].append(s)

    def by_qualname(self, q: str) -> list[Symbol]:
        return list(self._by_qualname.get(q, ()))

    def by_name(self, n: str) -> list[Symbol]:
        return list(self._by_name.get(n, ()))

    def files_matching(self, suffix: str) -> list[str]:
        suffix = suffix.lstrip("./")
        pool = self.files if suffix.endswith(".py") else (self.all_files or self.files)
        hits = sorted(f for f in pool if f == suffix or f.endswith("/" + suffix))
        if len(hits) > 1 and suffix.endswith(".py"):  # prefer src/ over tests/ or docs copies
            src = [h for h in hits if h.startswith("src/")]
            hits = src or hits
        return hits


# --- building the index ------------------------------------------------------


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True, timeout=60
    ).stdout


def _symbols_in_source(path: str, source: str) -> list[Symbol]:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    out: list[Symbol] = []

    def deco(n: ast.AST) -> tuple[str, ...]:
        return tuple(ast.unparse(d) for d in getattr(n, "decorator_list", ()))

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            out.append(Symbol(path, node.name, FUNCTION, node.lineno, node.end_lineno or 0, deco(node)))
        elif isinstance(node, ast.ClassDef):
            out.append(Symbol(path, node.name, CLASS, node.lineno, node.end_lineno or 0, deco(node)))
            for sub in node.body:
                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    out.append(
                        Symbol(path, f"{node.name}.{sub.name}", METHOD, sub.lineno, sub.end_lineno or 0, deco(sub))
                    )
                elif isinstance(sub, (ast.Assign, ast.AnnAssign)):  # dataclass fields, class attrs
                    targets = sub.targets if isinstance(sub, ast.Assign) else [sub.target]
                    for t in targets:
                        if isinstance(t, ast.Name):
                            out.append(Symbol(path, f"{node.name}.{t.id}", ATTRIBUTE, sub.lineno, sub.end_lineno or 0))
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for t in targets:
                if isinstance(t, ast.Name):
                    out.append(Symbol(path, t.id, CONSTANT, node.lineno, node.end_lineno or 0))
    return out


def index(repo: str | Path, ref: str = "HEAD", roots: tuple[str, ...] = ("src/",)) -> SymbolIndex:
    """Index every tracked *.py under `roots` at `ref`, or the working tree if ref is "WORKTREE"."""
    repo = Path(repo)
    idx = SymbolIndex(ref=ref)
    if ref == "WORKTREE":
        listing = _git(repo, "ls-files", "--", *roots)
        idx.all_files = {l for l in _git(repo, "ls-files").split("\n") if l}
    else:
        listing = _git(repo, "ls-tree", "-r", "--name-only", ref, "--", *roots)
        idx.all_files = {l for l in _git(repo, "ls-tree", "-r", "--name-only", ref).split("\n") if l}
    for path in listing.split("\n"):
        if not path.endswith(".py"):
            continue
        if ref == "WORKTREE":
            p = repo / path
            if not p.exists():
                continue
            source = p.read_text(encoding="utf-8", errors="replace")
        else:
            source = _git(repo, "show", f"{ref}:{path}")
        idx.files.add(path)
        for s in _symbols_in_source(path, source):
            idx.add(s)
    return idx


# --- the note's own module ---------------------------------------------------

_H1 = re.compile(r"^#\s+(.+?)\s*$", re.M)


def module_hints(note_path: str, note_text: str) -> list[str]:
    """Module suffixes a note is 'about', best first: from its H1, then its filename.

    `# facility-remote.py — \\`facility/remote.py\\`` → ["facility/remote.py", "facility/remote.py"]
    `# binding` → ["binding.py"];  facility-remote.md → ["facility/remote.py"]
    """
    hints: list[str] = []
    m = _H1.search(note_text)
    if m:
        h1 = m.group(1)
        for span in re.findall(r"`([^`]+)`", h1):
            if span.endswith(".py"):
                hints.append(span)
        head = re.split(r"\s+[—–-]\s+|\s+\(|:", h1)[0].strip()
        if re.fullmatch(r"[A-Za-z0-9_./-]+", head):
            hints.append(_stem_to_module(head))
    hints.append(_stem_to_module(Path(note_path).stem))
    out: list[str] = []
    for h in hints:
        if h and h not in out:
            out.append(h)
    return out


def _stem_to_module(stem: str) -> str:
    stem = re.sub(r"\.py$", "", stem)
    # facility-remote → facility/remote ; login_flow_manager stays
    return stem.replace("-", "/") + ".py"


# --- resolution --------------------------------------------------------------

RESOLVED, SUPERSET, CONSTANT_ONLY, UNRESOLVED = "resolved", "superset", "constant", "unresolved"


@dataclass(frozen=True)
class Resolution:
    mention: Mention
    status: str
    candidates: tuple[Symbol, ...]
    rule: str

    @property
    def targets(self) -> list[str]:
        return sorted({c.drift_target for c in self.candidates if c.kind != CONSTANT})


def _prefer_module(cands: list[Symbol], hints: list[str]) -> list[Symbol]:
    for h in hints:
        own = [c for c in cands if c.path == h or c.path.endswith("/" + h)]
        if own:
            return own
    return cands


def resolve(m: Mention, idx: SymbolIndex, hints: list[str] = ()) -> Resolution:
    hints = list(hints)
    if m.kind == PATH:
        files = idx.files_matching(m.text)
        if not files:
            return Resolution(m, UNRESOLVED, (), "path:no-file")
        if m.symbol:
            cands = [s for f in files for s in idx.by_qualname(m.symbol) if s.path == f]
            if not cands:
                return Resolution(m, UNRESOLVED, (), "path:no-symbol")
            return Resolution(m, RESOLVED if len(cands) == 1 else SUPERSET, tuple(cands), "path#symbol")
        cands = [Symbol(f, "", FILE) for f in files]
        return Resolution(m, RESOLVED if len(cands) == 1 else SUPERSET, tuple(cands), "path")

    if m.kind == CAPS:
        cands = idx.by_qualname(m.text)
        if not cands:
            return Resolution(m, UNRESOLVED, (), "caps:no-symbol")
        return Resolution(m, CONSTANT_ONLY, tuple(_prefer_module(cands, hints)), "caps:constant")

    if m.kind == DOTTED:
        head, tail = m.text.rsplit(".", 1)
        cands = idx.by_qualname(m.text)  # Class.method
        rule = "dotted:qualname"
        if not cands:  # module.name, e.g. config._control_settings
            cands = [s for s in idx.by_qualname(tail) if s.module == head or s.module.endswith("/" + head)]
            rule = "dotted:module.name"
        if not cands:  # Class.member where the class part is an alias, e.g. `app.teardown_task`
            cands = [s for s in idx.by_name(tail) if s.kind in (METHOD, ATTRIBUTE)]
            rule = "dotted:member"
        return _finish(m, cands, hints, rule)

    # NAME
    cands = idx.by_qualname(m.text)  # top-level function/class/constant
    rule = "name:top-level"
    if not cands:
        cands = [s for s in idx.by_name(m.text) if s.kind in (METHOD, ATTRIBUTE)]
        rule = "name:member"
        # A bare, short attribute name (`compute`, `status`) binds to whichever class happens to have
        # that field — the run-1 `attribute-guess` false flags. Require the note's own module for those.
        if cands and all(c.kind == ATTRIBUTE for c in cands) and not m.raw.endswith(")") \
                and "_" not in m.text and len(m.text) < 8:
            own = _prefer_module(cands, hints)
            cands = own if own is not cands else []
            rule = "name:member:weak"
    if not cands:  # a bare module name: `server`, `login` → the whole file
        files = idx.files_matching(m.text + ".py")
        cands = [Symbol(f, "", FILE) for f in files]
        rule = "name:module"
    return _finish(m, cands, hints, rule)


def _finish(m: Mention, cands: list[Symbol], hints: list[str], rule: str) -> Resolution:
    if not cands:
        return Resolution(m, UNRESOLVED, (), rule + ":none")
    if all(c.kind == CONSTANT for c in cands):
        return Resolution(m, CONSTANT_ONLY, tuple(cands), rule + ":constant")
    cands = [c for c in cands if c.kind != CONSTANT]
    if len(cands) > 1:
        own = _prefer_module(cands, hints)
        if own is not cands:
            cands, rule = own, rule + ":own-module"
    if len({c.drift_target for c in cands}) == 1:
        return Resolution(m, RESOLVED, tuple(cands), rule)
    return Resolution(m, SUPERSET, tuple(cands), rule + ":superset")


def resolve_note(note_path: str, note_text: str, idx: SymbolIndex, ms: list[Mention]) -> list[Resolution]:
    hints = module_hints(note_path, note_text)
    return [resolve(m, idx, hints) for m in ms]
