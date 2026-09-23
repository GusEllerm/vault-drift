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
_RE_PATH = re.compile(r"^[A-Za-z0-9_./-]+$")
_RE_LINE_HINT = re.compile(r":\d+$")
_RE_CALL = re.compile(r"\((.*)\)$")
_RE_HASH_SYMBOL = re.compile(rf"^(?P<path>[^#]+)#(?P<sym>{_IDENT}(\.{_IDENT})*)$")
_CODE_EXTS = (".py", ".toml", ".json", ".yaml", ".yml", ".sh", ".cfg", ".ini")

# Kinds. `noise` never leaves this module.
PATH, DOTTED, NAME, CAPS = "path", "dotted", "name", "caps"


@dataclass(frozen=True)
class Mention:
    text: str  # normalised: line hints and call parens stripped
    raw: str  # the span as written
    line: int  # 1-based
    kind: str  # PATH | DOTTED | NAME | CAPS
    symbol: str | None = None  # for PATH mentions of the form path#Symbol


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
    s = span.strip()
    if not s:
        return None
    # Obvious non-code: quoted strings, shell, assignments, prose with spaces.
    if s[0] in "\"'-<>$" or any(ch in s for ch in " \t$=<>{}|,;\"'"):
        return None
    s = _RE_LINE_HINT.sub("", s)  # credentials.py:78 -> credentials.py
    s = _RE_CALL.sub("", s)  # wait(timeout_s) -> wait
    if not s:
        return None
    if "#" in s:
        m = _RE_HASH_SYMBOL.match(s)
        return (s, PATH) if m else None
    if "/" in s or s.endswith(_CODE_EXTS):
        return (s, PATH) if _RE_PATH.match(s) else None
    if ":" in s:  # purdue:anvil, visible_to: public
        return None
    if _RE_DOTTED.match(s):
        return (s, DOTTED)
    if _RE_IDENT.match(s):
        if s.isupper() or (s.replace("_", "").isupper() and "_" in s):
            return (s, CAPS)
        if len(s) < 3:  # id, x; anything longer is left for the symbol index to reject
            return None
        if s in _PYTHON_NOISE:
            return None
        return (s, NAME)
    return None


# Bare words that are Python keywords/builtins or vault vocabulary, never anchors.
_PYTHON_NOISE = frozenset(
    "None True False self None list dict tuple bool float bytes print main "
    "fresh stale broken unknown failed waiting done expired running down warm cold".split()
)


def iter_mentions(text: str) -> Iterator[Mention]:
    lines = text.splitlines()
    start = frontmatter_end(lines)
    for i in range(start, len(lines)):
        for m in _SPAN.finditer(lines[i]):
            norm = _normalise(m.group(1))
            if norm is None:
                continue
            s, kind = norm
            symbol = None
            if kind == PATH and "#" in s:
                path, symbol = s.split("#", 1)
                s = path
            yield Mention(text=s, raw=m.group(1), line=i + 1, kind=kind, symbol=symbol)


def mentions(text: str) -> list[Mention]:
    return list(iter_mentions(text))
