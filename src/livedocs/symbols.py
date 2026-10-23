"""Symbol index at a git ref (Python, TypeScript/JavaScript, Astro, JSON config keys), and
mention → symbol resolution.

Resolution rules (Implementation Plan §4.2):
  1. path mentions → the file (and symbol if `path#Sym`); a TS/JS/Astro module path → its default export
  2. exact qualname (TS: also export aliases, re-export renames and a default export's file name)
  3. the note's own module
  4. unique top-level name under src/, else unique method name
  5. still ambiguous → all candidates (superset: over-flags, never a false fresh)
  6. nothing → unresolved
drift anchors top-level symbols in .py, .ts and .js only, so `drift_target` is `path#<top_level_name>`
there and the whole file elsewhere; the qualname is kept for narrowing (member hashes) later.
"""

from __future__ import annotations

import ast
import posixpath
import re
import subprocess
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from . import configkeys, ts
from .mentions import CAPS, DOTTED, NAME, PATH, Mention

FUNCTION, CLASS, METHOD, ATTRIBUTE, CONSTANT, FILE = "function", "class", "method", "attribute", "constant", "file"
INTERFACE, TYPE, ENUM, NAMESPACE, KEY, COMPONENT = ts.INTERFACE, ts.TYPE, ts.ENUM, ts.NAMESPACE, ts.KEY, ts.COMPONENT
CODE_EXTS = (".py",) + ts.EXTS  # files whose path mention names a module, not a config file


def is_code(path: str) -> bool:
    return path.endswith(CODE_EXTS)


def _strip_ext(p: str) -> str:
    for e in CODE_EXTS:
        if p.endswith(e):
            return p[: -len(e)]
    return p


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
        """Module path without any leading `…/src/` and the extension: facility/remote.
        Code may live at src/, benchmark/src/, packages/x/src/ — the src segment is not the root.
        A TS `index` module is its folder: components/index.ts → components."""
        p = self.path
        m = re.search(r"(?:^|/)src/", p)
        if m:
            p = p[m.end():]
        if p.endswith(".py"):
            return re.sub(r"\.py$", "", p)
        p = _strip_ext(p)
        return p[: -len("/index")] if p.endswith("/index") and ts.is_ts(self.path) else p

    @property
    def drift_target(self) -> str:
        # drift binds top-level functions/classes; Python constants can't be fingerprinted by it, so a
        # constant binds the whole file and livedocs hashes the assignment itself (P24). The same holds
        # for everything drift can't fingerprint: TSX/JSX/MJS/Astro, a TS `default`, JSON keys.
        if self.kind == FILE:
            return self.path
        if self.path.endswith(".py"):
            return self.path if self.kind == CONSTANT else f"{self.path}#{self.top_level_name}"
        if self.path.endswith(ts.DRIFT_SYMBOL_EXTS) and self.top_level_name != "default":
            return f"{self.path}#{self.top_level_name}"
        return self.path


@dataclass
class SymbolIndex:
    ref: str
    symbols: list[Symbol] = field(default_factory=list)
    files: set[str] = field(default_factory=set)  # indexed .py files under the roots
    all_files: set[str] = field(default_factory=set)  # every tracked file (for path mentions like pyproject.toml)
    defaults: dict[str, str] = field(default_factory=dict)  # TS/Astro file → qualname of its default export
    path_aliases: list = field(default_factory=list)  # tsconfig `paths`: [(pattern, [targets])]
    ts_files: int = 0
    unavailable: set[str] = field(default_factory=set)  # languages present but not parseable here
    _by_qualname: dict[str, list[Symbol]] = field(default_factory=lambda: defaultdict(list))
    _by_name: dict[str, list[Symbol]] = field(default_factory=lambda: defaultdict(list))
    _at: dict[tuple[str, str], Symbol] = field(default_factory=dict)

    def add(self, s: Symbol) -> None:
        self.symbols.append(s)
        if is_code(s.path):  # config keys are symbols, but their files are not "the code"
            self.files.add(s.path)
        self._by_qualname[s.qualname].append(s)
        self._by_name[s.name].append(s)
        self._at.setdefault((s.path, s.qualname), s)

    def add_alias(self, alias: str, s: Symbol) -> None:
        """Another top-level name for `s` (an export alias, a default export's file name)."""
        if s not in self._by_qualname[alias]:
            self._by_qualname[alias].append(s)

    def at(self, path: str, qualname: str) -> Symbol | None:
        return self._at.get((path, qualname))

    def by_qualname(self, q: str) -> list[Symbol]:
        return list(self._by_qualname.get(q, ()))

    def by_name(self, n: str) -> list[Symbol]:
        return list(self._by_name.get(n, ()))

    def files_matching(self, suffix: str) -> list[str]:
        suffix = suffix.lstrip("./")
        hits = self._suffix_hits(suffix)
        if not hits and self.ts_files:
            for alt in self._ts_forms(suffix):  # @/components/Header, src/world/world, src/components
                hits = self._suffix_hits(alt)
                if hits:
                    break
        return hits

    def _suffix_hits(self, suffix: str) -> list[str]:
        code = is_code(suffix)
        pool = self.files if code else (self.all_files or self.files)
        hits = sorted(f for f in pool if f == suffix or f.endswith("/" + suffix))
        if len(hits) > 1 and code:  # prefer real code over test or docs copies
            src = [h for h in hits if not is_excluded(h)]
            hits = src or hits
        return hits

    def _ts_forms(self, suffix: str) -> list[str]:
        bases = [suffix] + ts.alias_targets(suffix, self.path_aliases)
        out: list[str] = []
        for b in bases:
            if b != suffix:
                out.append(b)
            if not posixpath.splitext(b)[1]:
                out += [b + e for e in ts.EXTS] + [f"{b}/index{e}" for e in ts.EXTS]
        return out


# --- building the index ------------------------------------------------------


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True, timeout=60
    ).stdout


def _symbols_in_source(path: str, source: str) -> list[Symbol]:
    """Python symbols (TS and JSON go through their own modules in `index`)."""
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


# Directories whose Python is not "the code": tests, environments, build output, vendored copies.
EXCLUDED_SEGMENTS = frozenset({
    "tests", "test", "testing", ".venv", "venv", "env", "node_modules", "build", "dist", "site-packages",
    ".git", ".tox", ".nox", "__pycache__", ".eggs", "examples", "docs", "doc", "scripts",
})


# Further folders and file names that are not "the code" in a JS/TS project. Kept apart from the shared
# set so Python repositories index exactly what they did before.
TS_EXCLUDED_SEGMENTS = frozenset({
    "__tests__", "__mocks__", "e2e", "coverage", "public", "vendor", "playwright-report", "test-results",
    "storybook-static", "out", "tmp", "temp", "scratch",
})
# test files, stories, and scratch probes (`tmp-find-eq2.mjs` at a repo root defines names like `build`)
_TS_TEST_FILE = re.compile(r"(\.(test|spec|stories|e2e)\.[cm]?[jt]sx?$)|^(tmp|temp|scratch)[-_.]")


def is_excluded(path: str) -> bool:
    parts = path.split("/")
    name = parts[-1]
    if any(p in EXCLUDED_SEGMENTS or p.startswith(".") for p in parts[:-1]):
        return True
    if ts.is_ts(path) or configkeys.is_config(path):
        if any(p in TS_EXCLUDED_SEGMENTS for p in parts[:-1]) or _TS_TEST_FILE.search(name):
            return True
    return name.startswith("test_") or name.endswith("_test.py") or name == "conftest.py" or name == "setup.py"


def code_roots(repo: str | Path) -> tuple[str, ...] | None:
    """Explicit code roots from .livedocs/config.json (`code_roots`), else None = discover."""
    from . import config
    roots = config.load(repo).get("code_roots")
    if roots:
        return tuple(r.rstrip("/") + "/" for r in roots)
    return None


def index(repo: str | Path, ref: str = "HEAD", roots: tuple[str, ...] | None = None) -> SymbolIndex:
    """Index the project's Python at `ref` (or the working tree if ref is "WORKTREE").

    Which files count as code: `roots` if given, else `code_roots` from config, else every tracked
    *.py outside tests, environments, build output and docs — wherever it lives (src/, benchmark/src/,
    a flat package at the root). A note should never be silently unbound because of the layout."""
    repo = Path(repo)
    idx = SymbolIndex(ref=ref)
    roots = roots or code_roots(repo)
    if ref == "WORKTREE" and not (repo / ".git").exists():
        # A checkout-index snapshot (the pre-commit gate) has no .git: walk the files instead.
        all_files = {str(p.relative_to(repo)) for p in repo.rglob("*") if p.is_file()}
    elif ref == "WORKTREE":
        all_files = {l for l in _git(repo, "ls-files").split("\n") if l}
    else:
        all_files = {l for l in _git(repo, "ls-tree", "-r", "--name-only", ref).split("\n") if l}
    idx.all_files = all_files
    if roots:
        candidates = [f for f in all_files if any(f.startswith(r) for r in roots)]
    else:
        candidates = [f for f in all_files if not is_excluded(f)]
    listing = "\n".join(sorted(candidates))

    def read(path: str) -> str | None:
        if ref == "WORKTREE":
            p = repo / path
            return p.read_text(encoding="utf-8", errors="replace") if p.is_file() else None
        if path not in all_files:
            return None
        return _git(repo, "show", f"{ref}:{path}")

    ts_files: dict[str, ts.FileSymbols] = {}
    for path in listing.split("\n"):
        if path.endswith(".py"):
            source = read(path)
            if source is None:
                continue
            idx.files.add(path)
            for s in _symbols_in_source(path, source):
                idx.add(s)
        elif ts.is_ts(path):
            if "typescript" in idx.unavailable:
                continue
            source = read(path)
            if source is None:
                continue
            try:
                fs = ts.file_symbols(path, source)
            except ts.Unavailable:
                idx.unavailable.add("typescript")
                continue
            idx.files.add(path)
            ts_files[path] = fs
            for q, kind, a, b, decos in fs.symbols:
                idx.add(Symbol(path, q, kind, a, b, decos))
    # Config files live at the root whatever the code roots are (wrangler.jsonc, tsconfig.json).
    for path in sorted(f for f in all_files if configkeys.is_config(f) and not is_excluded(f)):
        source = read(path)
        if source is None:
            continue
        for q, line in configkeys.keys(path, source):
            idx.add(Symbol(path, q, KEY, line, line))
    idx.ts_files = len(ts_files)
    if ts_files:
        idx.path_aliases = ts.path_aliases(read)
        _link_ts(idx, ts_files)
    return idx


def _link_ts(idx: SymbolIndex, files: dict[str, "ts.FileSymbols"]) -> None:
    """Second names for TS symbols: `export { a as b }`, default exports (by `default` and by the file's
    name, which is what `import Header from './Header'` calls it), and renaming re-exports through barrels
    (`export { default as Header } from './Header'`). Same-name re-exports need nothing: a mention
    resolves to the definition, never to the barrel."""
    for path, fs in files.items():
        for alias, local in fs.aliases.items():
            s = idx.at(path, local)
            if s:
                idx.add_alias(alias, s)
        if fs.default and idx.at(path, fs.default):
            idx.defaults[path] = fs.default
    for path, q in idx.defaults.items():
        s = idx.at(path, q)
        if q != "default":
            idx.add_alias("default", s)
        stem = ts.default_alias(path)
        if stem and stem != q and not idx.at(path, stem):
            idx.add_alias(stem, s)

    def exported(path: str, name: str, depth: int = 0) -> Symbol | None:
        if depth > 5:
            return None
        fs = files.get(path)
        if fs is None:
            return None
        if name == "default":
            q = idx.defaults.get(path)
            return idx.at(path, q) if q else None
        s = idx.at(path, fs.aliases.get(name, name))
        if s:
            return s
        for alias, spec, orig in fs.reexports:
            if alias == name:
                target = ts.resolve_specifier(path, spec, idx.files, idx.path_aliases)
                return exported(target, orig, depth + 1) if target else None
        return None

    for path, fs in files.items():
        for alias, spec, orig in fs.reexports:
            target = ts.resolve_specifier(path, spec, idx.files, idx.path_aliases)
            s = exported(target, orig) if target else None
            if s and alias != "default":
                idx.add_alias(alias, s)


# --- the note's own module ---------------------------------------------------

_H1 = re.compile(r"^#\s+(.+?)\s*$", re.M)


def module_hints(note_path: str, note_text: str) -> list[str]:
    """Module suffixes a note is 'about', best first: from its H1, then its filename.

    `# facility-remote.py — \\`facility/remote.py\\`` → ["facility/remote.py"]
    `# benchmark/src/gateway.py` → ["benchmark/src/gateway.py"] (a path H1 matches by suffix)
    `# binding` → ["binding.py"];  facility-remote.md → ["facility/remote.py"]
    """
    hints: list[str] = []
    m = _H1.search(note_text)
    if m:
        h1 = m.group(1)
        for span in re.findall(r"`([^`]+)`", h1):
            if span.endswith(CODE_EXTS):
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
    if stem.endswith(ts.EXTS):  # `# src/components/Header.tsx`: already a file
        return stem
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
        return sorted({c.drift_target for c in self.candidates})


def _hint_matches(path: str, h: str) -> bool:
    if not ts.is_ts(path):
        return path == h or path.endswith("/" + h)
    # A TS/Astro module note names a file in any extension, or a folder: `# Modules/world` covers src/world/*.
    base = h[: -len(".py")] if h.endswith(".py") else h
    if base.endswith(CODE_EXTS):
        return path == base or path.endswith("/" + base)
    stem = "/" + _strip_ext(path)
    return stem.endswith("/" + base) or stem.endswith(f"/{base}/index") or f"/{base}/" in "/" + path


def _prefer_module(cands: list[Symbol], hints: list[str]) -> list[Symbol]:
    for h in hints:
        own = [c for c in cands if _hint_matches(c.path, h)]
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
        # A TS/JS/Astro module's identity is its default export (a component, a defineConfig object):
        # that is what a path names. A module without one names nothing finer than the file (P29).
        cands = [idx.at(f, idx.defaults[f]) if f in idx.defaults else Symbol(f, "", FILE) for f in files]
        rule = "path:default" if any(c.kind != FILE for c in cands) else "path"
        return Resolution(m, RESOLVED if len(cands) == 1 else SUPERSET, tuple(cands), rule)

    if m.kind == CAPS:
        cands = idx.by_qualname(m.text)
        if not cands:
            return Resolution(m, UNRESOLVED, (), "caps:no-symbol")
        return Resolution(m, CONSTANT_ONLY, tuple(_prefer_module(cands, hints)), "caps:constant")

    if m.kind == DOTTED:
        head, tail = m.text.rsplit(".", 1)
        cands = idx.by_qualname(m.text)  # Class.method
        rule = "dotted:qualname"
        if not cands and idx.ts_files:  # an exported alias as the head: `config.title`, export { cfg as config }
            first, rest = m.text.split(".", 1)
            cands = [t for s in idx.by_qualname(first) if s.qualname != first
                     for t in [idx.at(s.path, f"{s.qualname}.{rest}")] if t is not None]
            rule = "dotted:alias"
        if not cands:  # module.name, e.g. config._control_settings
            cands = [s for s in idx.by_qualname(tail) if s.module == head or s.module.endswith("/" + head)]
            rule = "dotted:module.name"
        if not cands:  # a key path below its constant: `configuration.pageTitle` → config.configuration.pageTitle
            cands = [s for s in idx.by_name(tail) if s.kind == KEY and s.qualname.endswith("." + m.text)]
            rule = "dotted:key-suffix"
        if not cands:  # Class.member where the class part is an alias, e.g. `app.teardown_task`
            cands = [s for s in idx.by_name(tail) if s.kind in (METHOD, ATTRIBUTE)]
            rule = "dotted:member"
        return _finish(m, cands, hints, rule)

    # NAME
    cands = idx.by_qualname(m.text)  # top-level function/class/constant
    rule = "name:top-level"
    if m.jsx:  # <ProjectCard /> names a component: a TS/Astro top-level symbol, nothing else
        cands = [c for c in cands if ts.is_ts(c.path) and c.kind in (FUNCTION, CLASS, CONSTANT, COMPONENT)]
        return _finish(m, cands, hints, "jsx:component")
    if not cands:
        cands = [s for s in idx.by_name(m.text) if s.kind in (METHOD, ATTRIBUTE)]
        rule = "name:member"
        # A bare, short attribute name (`compute`, `status`) binds to whichever class happens to have
        # that field — the run-1 `attribute-guess` false flags. Require the note's own module for those.
        if cands and all(c.kind == ATTRIBUTE for c in cands) \
                and not m.call and "_" not in m.text and len(m.text) < 8:
            own = _prefer_module(cands, hints)
            cands = own if own is not cands else []
            rule = "name:member:weak"
    if not cands:  # a bare module name: `server`, `login` → the whole file
        files = idx.files_matching(m.text + ".py")
        for e in (ts.EXTS if idx.ts_files and not files else ()):
            files = idx.files_matching(m.text + e)
            if files:
                break
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


def _lang_of(path: str) -> str:
    return "py" if path.endswith(".py") else "ts" if ts.is_ts(path) else "other"


class _LangView:
    """The index seen from a note written about one language: same lookups, other-language symbols
    hidden. In a repository with Python and TypeScript, `nodes` in a note about a Python module means
    the Python attribute, not every TS interface field of that name."""

    def __init__(self, idx: SymbolIndex, lang: str):
        self._idx, self._lang = idx, lang

    def __getattr__(self, name):
        return getattr(self._idx, name)

    def _keep(self, cands: list[Symbol]) -> list[Symbol]:
        return [c for c in cands if _lang_of(c.path) in (self._lang, "other")]

    def by_qualname(self, q: str) -> list[Symbol]:
        return self._keep(self._idx.by_qualname(q))

    def by_name(self, n: str) -> list[Symbol]:
        return self._keep(self._idx.by_name(n))


def note_language(idx: SymbolIndex, hints: list[str], first_pass: list[Resolution]) -> str | None:
    """Which language a note is about, in a repository that has more than one: the language of the
    module it is named after, else of at least three quarters (and at least three) of its unambiguous
    mentions. None means no preference."""
    langs_present = {_lang_of(f) for f in idx.files} - {"other"}
    if len(langs_present) < 2:
        return None
    for h in hints:
        langs = {_lang_of(f) for f in idx.files if _hint_matches(f, h)} - {"other"}
        if len(langs) == 1:
            return langs.pop()
        if langs:
            break
    counts = Counter(_lang_of(r.candidates[0].path) for r in first_pass
                     if r.status == RESOLVED and len({_lang_of(c.path) for c in r.candidates}) == 1)
    counts.pop("other", None)
    if counts:
        lang, n = counts.most_common(1)[0]
        if n >= 3 and n >= 0.75 * sum(counts.values()):
            return lang
    return None


def resolve_note(note_path: str, note_text: str, idx: SymbolIndex, ms: list[Mention]) -> list[Resolution]:
    hints = module_hints(note_path, note_text)
    first = [resolve(m, idx, hints) for m in ms]
    lang = note_language(idx, hints, first)
    if lang is None:
        return first
    view = _LangView(idx, lang)
    out = []
    for m, r in zip(ms, first):
        if m.kind != PATH and any(_lang_of(c.path) not in (lang, "other") for c in r.candidates):
            r2 = resolve(m, view, hints)  # type: ignore[arg-type]
            if r2.status != UNRESOLVED:
                r = r2
        out.append(r)
    return out
