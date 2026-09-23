"""`livedocs stamp`: derive anchors from a note's mentions, bind them with drift, append a stamp."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from . import astdiff, drift_io, mentions as mn, stamps as st, symbols as sy


class StampError(RuntimeError):
    pass


def _code_like(m: mn.Mention) -> bool:
    """A mention that reads as a Python identifier the author expected to exist in this codebase:
    snake_case with an underscore, or a call. Bare CamelCase is excluded — it is usually an external
    name (an SSH option, a library class) and produced noise in the first gate run."""
    t = m.text
    if m.raw.endswith(")"):
        return True
    if m.kind == mn.DOTTED:
        return "_" in t
    if m.kind == mn.NAME:
        return "_" in t and t.islower()
    return False


def _dangling(ms: list[mn.Mention], unresolved: set[str], previous: st.Stamp | None) -> list[str]:
    """Stale names: mentions that resolve to nothing now but either look like local Python identifiers
    or resolved in the note's previous stamp (the strongest signal: it existed, and doesn't)."""
    previously_resolved = {raw for raws in previous.mentions.values() for raw, _ in raws} if previous else set()
    out = set()
    for m in ms:
        if m.raw not in unresolved:
            continue
        if m.raw in previously_resolved or _code_like(m):
            out.add(m.raw)
    return sorted(out)


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
        if r.status == sy.UNRESOLVED:
            unresolved.append(r.mention.raw)
            continue
        for c in r.candidates:
            # Bare module mentions (`server`) are noisy whole-file anchors and stay opt-in;
            # explicit paths to non-Python files (`pyproject.toml`) are cheap and catch config claims.
            # Constants bind the file too (drift can't hash them) but carry their own member hash.
            if c.kind == sy.FILE and not file_anchors and (r.mention.kind != mn.PATH or c.path.endswith(".py")):
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
        members: dict[str, str] = {}
        path = target.split("#", 1)[0]
        if path.endswith(".py") and (repo / path).exists():
            src = (repo / path).read_text(encoding="utf-8", errors="replace")
            if "#" in target:
                deco = astdiff.decorator_hash(src, target.split("#", 1)[1])
            for q in quals.get(target, []):
                h = astdiff.member_hash(src, q)
                if h:
                    members[q] = h
        bindings[target] = st.Binding(sig=sig, deco=deco, qualnames=quals.get(target, []), members=members)

    unresolved_set = set(unresolved)
    s = st.Stamp(note=note, note_hash=current, bindings=bindings,
                 mentions={t: raws[t] for t in bindings}, unresolved=sorted(unresolved_set),
                 stamped=st.now_iso(), by=by, verdict=verdict, reason=reason,
                 dangling=_dangling(ms, unresolved_set, previous))
    st.append(vault, s)
    return StampResult(s, len(bindings), failed)
