"""`livedocs stamp`: derive anchors from a note's mentions, bind them with drift, append a stamp."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from . import astdiff, config, configkeys, drift_io, mentions as mn, stamps as st, symbols as sy, ts


class StampError(RuntimeError):
    pass


def _code_like(m: mn.Mention) -> bool:
    """A mention that reads as a Python identifier the author expected to exist in this codebase:
    snake_case with an underscore, or a call. Bare CamelCase is excluded — it is usually an external
    name (an SSH option, a library class) and produced noise in the first gate run."""
    t = m.text
    if m.call:
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


PATH_ANCHOR_MAX_LINES = 1000


def path_anchor_mode(repo: str | Path, file_anchors: bool = False):
    """`path_anchors` from config: "file" (every named file binds whole: 0.1's rule), "default-export"
    (only a module's default export binds by path), or a line count (the default): a named TS/JS/Astro
    module of at most that many lines binds whole, a larger one only its default export."""
    mode = config.load(repo).get("path_anchors", PATH_ANCHOR_MAX_LINES)
    if file_anchors or config.load(repo).get("file_anchors"):
        return "file"
    return mode


def binds(r: sy.Resolution, c: sy.Symbol, file_anchors: bool = False, *, mode=PATH_ANCHOR_MAX_LINES,
          idx: sy.SymbolIndex | None = None) -> bool:
    """Whether stamping binds candidate `c` of resolution `r` (coverage counts the same thing).

    Bare module mentions (`server`) are noisy whole-file anchors and stay opt-in. Explicit paths to
    non-code files (`pyproject.toml`, `wrangler.jsonc`) are cheap and catch config claims. A path to a
    Python file binds nothing by itself (since run 1). A path to a TS/JS/Astro module binds its default
    export, and the whole file when the module is small (P29): on gravity-works, whole-file anchors on
    every named module cost 931 hand reconciliations in 338 commits, half of them from one 1,600-line
    hub, while 10 of the 11 misses they rescued named a module of 620 lines or fewer (TS Run 1). Constants
    bind the file too (drift can't hash them) but carry their own member hash."""
    if r.status == sy.UNRESOLVED:
        return False
    if c.kind != sy.FILE:
        return True
    if r.mention.kind != mn.PATH:
        return file_anchors or mode == "file"
    if not sy.is_code(c.path) or file_anchors or mode == "file":
        return True
    if isinstance(mode, int) and ts.is_ts(c.path) and idx is not None:
        return idx.lines.get(c.path, mode + 1) <= mode
    return False


def _hashable(path: str) -> bool:
    return sy.is_code(path) or configkeys.is_config(path)


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
    if config.is_snapshot(repo, note, text):
        # Snapshot notes bind nothing: drop any bindings an earlier stamp made and record the fact.
        # Declaring a snapshot is always a valid re-stamp, so this precedes the update/ack rules.
        for (d, t), _sig in drift_io.lock(repo).items():
            if d == doc:
                try:
                    drift_io.unlink(repo, d, t)
                except drift_io.DriftError:
                    pass
        s = st.Stamp(note=note, note_hash=current, bindings={}, mentions={}, unresolved=[],
                     stamped=st.now_iso(), by=by, verdict=verdict, reason=reason or "snapshot", snapshot=True)
        st.append(vault, s)
        return StampResult(s, 0, [])
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
    mode = path_anchor_mode(repo, file_anchors)
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
            if not binds(r, c, file_anchors, mode=mode, idx=idx):
                continue
            t = c.drift_target
            # "" marks a whole-file anchor, so a symbol mentioned in the same file can't narrow it
            q = c.qualname if c.kind != sy.FILE else ""
            if q not in quals[t]:
                quals[t].append(q)
            raws[t].append([r.mention.raw, r.mention.line])

    sigs: dict[str, str] = {}
    failed: list[str] = []
    fallback: list[str] = []
    for target in sorted(quals.keys() | raws.keys()):
        try:
            sigs[target] = drift_io.link(repo, doc, target)
        except drift_io.DriftError as e:
            path = target.split("#", 1)[0]
            if "#" in target and not path.endswith(".py") and "cannot compute fingerprint" in str(e):
                # drift can't fingerprint this symbol (JSX in a .js file, a declaration form it doesn't
                # parse): bind the file and let the member hashes carry the substance (P24's pattern).
                for q in quals.pop(target, []):
                    if q not in quals[path]:
                        quals[path].append(q)
                raws[path].extend(raws.pop(target, []))
                fallback.append(path)
                continue
            failed.append(f"{target}: {e}")
    for path in sorted(set(fallback) - sigs.keys()):
        try:
            sigs[path] = drift_io.link(repo, doc, path)
        except drift_io.DriftError as e:
            failed.append(f"{path}: {e}")

    bindings: dict[str, st.Binding] = {}
    for target, sig in sorted(sigs.items()):
        deco = ""
        members: dict[str, str] = {}
        path = target.split("#", 1)[0]
        if _hashable(path) and (repo / path).exists():
            src = (repo / path).read_text(encoding="utf-8", errors="replace")
            if "#" in target:
                deco = astdiff.decorator_hash(src, target.split("#", 1)[1], path=path)
            for q in quals.get(target, []):
                if not q:
                    continue
                h = astdiff.member_hash(src, q, path=path)
                if h:
                    members[q] = h
        bindings[target] = st.Binding(sig=sig, deco=deco, qualnames=quals.get(target, []), members=members)

    # The lock holds what the note mentions now: drop bindings to code it no longer names (an edit
    # removed the mention, or a rule changed what binds). Orphans cost drift time and list the note
    # in `affected` for changes it doesn't depend on.
    for (d, t), _sig in drift_io.lock(repo).items():
        if d == doc and t not in bindings:
            try:
                drift_io.unlink(repo, d, t)
            except drift_io.DriftError:
                pass

    unresolved_set = set(unresolved)
    s = st.Stamp(note=note, note_hash=current, bindings=bindings,
                 mentions={t: raws[t] for t in bindings}, unresolved=sorted(unresolved_set),
                 stamped=st.now_iso(), by=by, verdict=verdict, reason=reason,
                 dangling=_dangling(ms, unresolved_set, previous))
    st.append(vault, s)
    return StampResult(s, len(bindings), failed)


def rebind(repo: str | Path, vault_rel: str, *, reason: str, by: str = "human") -> tuple[list[str], list[str]]:
    """Re-stamp every note whose text is what its latest stamp vouched for, under the current binding
    rules (an ack: the note is unchanged, only what it binds is). For upgrades that change resolution,
    e.g. 0.2's TypeScript symbols replacing whole-file anchors. Notes edited since their stamp are left
    for the commit that contains the edit. Returns (rebound, skipped)."""
    repo = Path(repo)
    vault = repo / vault_rel
    all_stamps = st.load(vault)
    idx = sy.index(repo, "WORKTREE")
    done, skipped = [], []
    for note in sorted({s.note for s in all_stamps}):
        p = vault / note
        latest = st.latest(st.for_note(all_stamps, note))
        if not p.exists() or latest is None or latest.snapshot:
            continue
        if latest.note_hash != st.note_hash(p.read_text(encoding="utf-8")):
            skipped.append(note)
            continue
        stamp(repo, vault_rel, note, by=by, verdict=st.ACK, reason=reason, idx=idx)
        done.append(note)
    return done, skipped
