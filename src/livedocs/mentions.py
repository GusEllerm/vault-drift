"""Code mentions in a note.

Only backtick spans count (design §6.3). Frontmatter is skipped; spans inside
fenced blocks are kept. Line numbers are 1-based over the whole file, which is
what the read gate reports back to the agent.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterator

# A single-backtick span. Triple backticks (fence lines) never match because
# the lookarounds refuse a backtick on either side.
_SPAN = re.compile(r"(?<!`)`([^`\n]+)`(?!`)")
_IDENT = r"[A-Za-z_][A-Za-z0-9_]*"
_RE_IDENT = re.compile(rf"^{_IDENT}$")
_RE_DOTTED = re.compile(rf"^{_IDENT}(\.{_IDENT})+$")
_RE_PATH = re.compile(r"^@?[A-Za-z0-9_./-]+$")  # a leading @ is a tsconfig alias: @/lib/x, @components/Card
_RE_LINE_HINT = re.compile(r":\d+$")
_RE_CALL = re.compile(r"\((.*)\)$")
_RE_HASH_SYMBOL = re.compile(rf"^(?P<path>[^#]+)#(?P<sym>{_IDENT}(\.{_IDENT})*)$")
_CODE_EXTS = (".py", ".toml", ".json", ".yaml", ".yml", ".sh", ".cfg", ".ini",
              ".ts", ".tsx", ".mts", ".cts", ".js", ".jsx", ".mjs", ".cjs", ".astro", ".jsonc")
# TypeScript forms, normalised to the name they mention:
#   <ProjectCard />, <ProjectCard title={t}>      → ProjectCard (a component)
#   useStore<T>(), Map<K, V>                     → useStore, Map
#   generateShareCard(state): Promise<Blob>      → generateShareCard (a call with its return type)
_RE_JSX = re.compile(rf"^<({_IDENT}(?:\.{_IDENT})*)(?:[\s/>]|$)")
_RE_GENERIC = re.compile(rf"^({_IDENT}(?:\.{_IDENT})*)<[^()]*>(?=\(|$)")
_RE_TS_SIG = re.compile(rf"^({_IDENT}(?:\.{_IDENT})*)(?:<[^()]*>)?(\(.*\))\s*:\s*[^()]+$")

# Kinds. `noise` never leaves this module.
PATH, DOTTED, NAME, CAPS = "path", "dotted", "name", "caps"


@dataclass(frozen=True)
class Mention:
    text: str  # normalised: line hints and call parens stripped
    raw: str  # the span as written
    line: int  # 1-based
    kind: str  # PATH | DOTTED | NAME | CAPS
    symbol: str | None = None  # for PATH mentions of the form path#Symbol
    call: bool = False  # written as a call: `wait(timeout_s)`, `foo()`
    jsx: bool = False  # written as a JSX/Astro tag: `<ProjectCard />`


def frontmatter_end(lines: list[str]) -> int:
    """Index of the first body line (0 if there is no frontmatter block)."""
    if not lines or lines[0].rstrip() != "---":
        return 0
    for i in range(1, len(lines)):
        if lines[i].rstrip() in ("---", "..."):
            return i + 1
    return 0


def _normalise(span: str) -> tuple[str, str | None] | None:
    """Return (text, kind) for a span worth keeping, else None."""
    n = _normalise_flags(span)
    return n[:2] if n else None


def _normalise_flags(span: str) -> tuple[str, str, bool, bool] | None:
    """(text, kind, call, jsx) for a span worth keeping, else None."""
    s = span.strip()
    if not s:
        return None
    j = _RE_JSX.match(s)
    if j and j.group(1)[0].isupper() and any(ch.islower() for ch in j.group(1)):
        # a component tag: <ProjectCard />. Lowercase tags are HTML; <NAME> is a placeholder.
        name = j.group(1)
        return (name, DOTTED if "." in name else NAME, False, True)
    call = span.endswith(")")
    if s[0].isalpha() or s[0] == "_":
        sig = _RE_TS_SIG.match(s)
        if sig:
            s, call = sig.group(1) + sig.group(2), True
        s = _RE_GENERIC.sub(r"\1", s)
    # A call with arguments — `total(items, tax_rate=0.15)` — is the most informative mention there
    # is; strip the argument list before the noise rules can reject the spaces and `=` inside it.
    s = _RE_LINE_HINT.sub("", s)  # credentials.py:78 -> credentials.py
    s = _RE_CALL.sub("", s)  # wait(timeout_s) -> wait
    if not s:
        return None
    # Obvious non-code: quoted strings, shell, assignments, prose with spaces.
    if s[0] in "\"'-<>$" or any(ch in s for ch in " \t$=<>{}|,;\"'"):
        return None
    if "#" in s:
        m = _RE_HASH_SYMBOL.match(s)
        return (s, PATH, False, False) if m else None
    if "/" in s or s.endswith(_CODE_EXTS):
        return (s, PATH, False, False) if _RE_PATH.match(s) else None
    if ":" in s:  # purdue:anvil, visible_to: public
        return None
    if _RE_DOTTED.match(s):
        return (s, DOTTED, call, False)
    if _RE_IDENT.match(s):
        if s.isupper() or (s.replace("_", "").isupper() and "_" in s):
            return (s, CAPS, call, False)
        if len(s) < 3:  # id, x; anything longer is left for the symbol index to reject
            return None
        if s in _PYTHON_NOISE or s in _JS_NOISE:
            return None
        return (s, NAME, call, False)
    return None


# Bare words that are Python keywords/builtins or vault vocabulary, never anchors.
_PYTHON_NOISE = frozenset(
    "None True False self None list dict tuple bool float bytes print main "
    "fresh stale broken unknown failed waiting done expired running down warm cold".split()
)
# JS/TS keywords, builtins and framework words that also name members everywhere (`Props.children`).
_JS_NOISE = frozenset(
    "undefined null this props children default string number boolean unknown never void any "
    "const let var async await".split()
)


def iter_mentions(text: str) -> Iterator[Mention]:
    lines = text.splitlines()
    start = frontmatter_end(lines)
    for i in range(start, len(lines)):
        for m in _SPAN.finditer(lines[i]):
            norm = _normalise_flags(m.group(1))
            if norm is None:
                continue
            s, kind, call, jsx = norm
            symbol = None
            if kind == PATH and "#" in s:
                path, symbol = s.split("#", 1)
                s = path
            yield Mention(text=s, raw=m.group(1), line=i + 1, kind=kind, symbol=symbol, call=call, jsx=jsx)


def mentions(text: str) -> list[Mention]:
    return list(iter_mentions(text))
