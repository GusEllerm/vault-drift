"""`livedocs coverage`: the coverage signal (D13) — which of a vault's code claims are anchored.

Per note: anchored mentions (bound to a symbol or file), dangling mentions (code-like names that
resolve to nothing: stale names), other unresolved mentions, and whether the note is stamped.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from . import mentions as mn, stamp as stp, stamps as st, symbols as sy


@dataclass
class NoteCoverage:
    note: str
    mentions: int
    anchored: int
    dangling: list[str]
    unresolved: int
    stamped: bool
    bindings: int

    @property
    def ratio(self) -> float:
        return self.anchored / self.mentions if self.mentions else 0.0


def coverage(repo: str | Path, vault_rel: str) -> list[NoteCoverage]:
    repo = Path(repo)
    vault = repo / vault_rel
    idx = sy.index(repo, "WORKTREE")
    all_stamps = st.load(vault)
    out: list[NoteCoverage] = []
    for p in sorted(vault.rglob("*.md")):
        if ".obsidian" in p.parts or ".livedocs" in p.parts:
            continue
        note = str(p.relative_to(vault))
        text = p.read_text(encoding="utf-8")
        ms = mn.mentions(text)
        res = sy.resolve_note(f"{vault_rel}/{note}", text, idx, ms)
        anchored = sum(1 for r in res if r.status in (sy.RESOLVED, sy.SUPERSET) and r.targets)
        unresolved = [r for r in res if r.status in (sy.UNRESOLVED, sy.CONSTANT_ONLY)]
        dangling = sorted({r.mention.raw for r in unresolved if stp._code_like(r.mention)})
        latest = st.latest(st.for_note(all_stamps, note))
        out.append(NoteCoverage(note, len(ms), anchored, dangling, len(unresolved) - len(dangling),
                                latest is not None and latest.note_hash == st.note_hash(text),
                                len(latest.bindings) if latest else 0))
    return out


def report(rows: list[NoteCoverage], as_json: bool = False) -> str:
    if as_json:
        return json.dumps([r.__dict__ | {"ratio": round(r.ratio, 2)} for r in rows], indent=1)
    lines = [f"{'note':52} {'ment':>5} {'anch':>5} {'cov':>5} {'dang':>5} {'stamp':>5}"]
    tm = ta = 0
    for r in rows:
        lines.append(f"{r.note[-52:]:52} {r.mentions:5} {r.anchored:5} {r.ratio:5.0%} {len(r.dangling):5} {'yes' if r.stamped else 'no':>5}")
        tm += r.mentions; ta += r.anchored
    lines.append(f"{'TOTAL':52} {tm:5} {ta:5} {ta / tm if tm else 0:5.0%}")
    dang = [(r.note, d) for r in rows for d in r.dangling]
    if dang:
        lines.append("\nDangling (code-like mentions that resolve to nothing — stale names?):")
        lines += [f"  {n}: `{d}`" for n, d in dang[:40]]
        if len(dang) > 40:
            lines.append(f"  … {len(dang) - 40} more")
    return "\n".join(lines)
