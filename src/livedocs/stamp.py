"""`livedocs stamp`: derive anchors from a note's mentions, bind them with drift, append a stamp."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from . import astdiff, drift_io, mentions as mn, stamps as st, symbols as sy


class StampError(RuntimeError):
    pass


@dataclass
class StampResult:
    stamp: st.Stamp
    linked: int
    failed: list[str]


def stamp(repo: str | Path, vault_rel: str, note: str, *, by: str, verdict: str | None = None,
          reason: str = "", file_anchors: bool = False, idx: sy.SymbolIndex | None = None) -> StampResult:
    repo = Path(repo)
    vault = repo / vault_rel
    doc = f"{vault_rel}/{note}" if vault_rel else note
    text = (vault / note).read_text(encoding="utf-8")
    current = st.note_hash(text)
    previous = st.latest(st.for_note(st.load(vault), note))

    if verdict is None:
        verdict = st.INITIAL if previous is None else st.UPDATE
    if verdict == st.ACK:
        if previous is None:
            raise StampError("--ack needs an earlier stamp")
        if previous.note_hash != current:
            raise StampError("note body changed since the last stamp: that is an update, not an ack")
        if not reason:
            raise StampError("--ack requires --reason")
    elif verdict == st.UPDATE and previous is not None and previous.note_hash == current:
        raise StampError("note body unchanged since the last stamp: use --ack --reason to re-verify without edits")

    idx = idx or sy.index(repo, "WORKTREE")
    ms = mn.mentions(text)
    resolutions = sy.resolve_note(doc, text, idx, ms)

    # drift target → qualnames mentioned under it, and the raw mentions with lines
    quals: dict[str, list[str]] = defaultdict(list)
    raws: dict[str, list[list]] = defaultdict(list)
    unresolved: list[str] = []
    for r in resolutions:
        if r.status in (sy.UNRESOLVED, sy.CONSTANT_ONLY):
            unresolved.append(r.mention.raw)
            continue
        for c in r.candidates:
            if c.kind == sy.CONSTANT:
                continue
            if c.kind == sy.FILE and not file_anchors:
                continue
            t = c.drift_target
            if c.qualname and c.qualname not in quals[t]:
                quals[t].append(c.qualname)
            raws[t].append([r.mention.raw, r.mention.line])

    bindings: dict[str, st.Binding] = {}
    failed: list[str] = []
    for target in sorted(quals.keys() | raws.keys()):
        try:
            sig = drift_io.link(repo, doc, target)
        except drift_io.DriftError as e:
            failed.append(f"{target}: {e}")
            continue
        deco = ""
        if "#" in target:
            path, top = target.split("#", 1)
            src = (repo / path).read_text(encoding="utf-8", errors="replace")
            deco = astdiff.decorator_hash(src, top)
        bindings[target] = st.Binding(sig=sig, deco=deco, qualnames=quals.get(target, []))

    s = st.Stamp(note=note, note_hash=current, bindings=bindings,
                 mentions={t: raws[t] for t in bindings}, unresolved=sorted(set(unresolved)),
                 stamped=st.now_iso(), by=by, verdict=verdict, reason=reason)
    st.append(vault, s)
    return StampResult(s, len(bindings), failed)
