"""The freshness check: state machine (design §6.5) plus findings with was/now.

`check` never writes anything.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from . import astdiff, config, configkeys, drift_io, gitx, stamps as st, ts

FRESH, CHANGED, BROKEN, UNKNOWN, SNAPSHOT = "fresh", "changed", "broken", "unknown", "snapshot"


@dataclass
class Finding:
    target: str  # drift target, path#Top or path
    path: str
    qualname: str  # what the note mentioned (may be Top.method)
    kind: str  # astdiff kind, or "anchor-missing"
    was: str | None
    now: str | None
    note_lines: list[int]
    base_commit: str | None
    detail: str = ""


@dataclass
class Report:
    note: str
    state: str
    reasons: list[str] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    stamp: st.Stamp | None = None
    warnings: list[str] = field(default_factory=list)  # state-independent: dangling mentions etc.
    refined: list[str] = field(default_factory=list)  # anchors drift flagged but the mentioned members are unchanged

    def to_dict(self) -> dict:
        return {
            "note": self.note, "state": self.state, "reasons": self.reasons,
            "findings": [f.__dict__ for f in self.findings],
            "stamped": self.stamp.stamped if self.stamp else None,
            "warnings": self.warnings, "refined": self.refined,
        }


def _doc_path(vault_rel: str, note: str) -> str:
    return f"{vault_rel}/{note}" if vault_rel else note


def _note_lines(text: str, raws: list[list]) -> list[int]:
    """Re-locate mentions in the current note text (line numbers may have moved)."""
    lines = text.splitlines()
    out: set[int] = set()
    for raw, old_line in raws:
        needle = f"`{raw}`"
        if 0 < old_line <= len(lines) and needle in lines[old_line - 1]:
            out.add(old_line)
            continue
        for i, l in enumerate(lines, 1):
            if needle in l:
                out.add(i)
    return sorted(out)


def check(repo: str | Path, vault_rel: str, note: str, drift_json: dict | None = None,
          text: str | None = None, all_stamps: list[st.Stamp] | None = None, idx=None,
          refine: bool = False, git_repo: str | Path | None = None) -> Report:
    """`text` overrides the note's on-disk content (the replay harness passes the pre-edit text
    to ask whether the old note was wrong about the new code).
    `refine=True` suppresses a drift flag when none of the mentioned members changed (run-2 mode:
    −40% flags, −25% real catches). Default is annotation: the flag stands, the findings say which
    mentioned members changed, or that the change is elsewhere in the class (D13).
    `git_repo` points at the repository for git operations when `repo` is a snapshot without .git
    (the pre-commit index snapshot)."""
    repo = Path(repo)
    git_repo = Path(git_repo) if git_repo else repo
    vault = repo / vault_rel
    doc = _doc_path(vault_rel, note)
    note_path = vault / note
    if text is None:
        if not note_path.exists():
            return Report(note, UNKNOWN, ["note-missing"])
        text = note_path.read_text(encoding="utf-8")
    current = st.note_hash(text)

    note_stamps = st.for_note(all_stamps if all_stamps is not None else st.load(vault), note)
    latest = st.latest(note_stamps)
    if config.is_snapshot(git_repo, note, text) or (latest is not None and latest.snapshot):
        return Report(note, SNAPSHOT, ["dated record; not checked against code"], stamp=latest)
    if not note_stamps:
        return Report(note, UNKNOWN, ["never-stamped"])
    lock = drift_io.lock(repo)
    stamp = st.matching(note_stamps, current, lock, doc)
    if stamp is None:
        if all(s.note_hash != current for s in note_stamps):
            return Report(note, UNKNOWN, ["edited-since-stamp"], stamp=st.latest(note_stamps))
        return Report(note, UNKNOWN, ["stamp-not-in-lock"], stamp=st.latest(note_stamps))
    if not stamp.bindings:
        return Report(note, UNKNOWN, ["unbound"], stamp=stamp)

    try:
        dj = drift_json if drift_json is not None else drift_io.check_json(repo)
    except drift_io.DriftError as e:
        return Report(note, UNKNOWN, [f"checker-error: {e}"], stamp=stamp)
    anchors = drift_io.anchors_for(dj, doc)
    if anchors is None:
        return Report(note, UNKNOWN, ["doc-not-in-drift-output"], stamp=stamp)
    by_target = {a["identity"]: a for a in anchors}

    state = FRESH
    reasons: list[str] = []
    findings: list[Finding] = []
    refined: list[str] = []
    cfg = config.load(git_repo)
    for target, binding in stamp.bindings.items():
        a = by_target.get(target)
        path = target.split("#", 1)[0]
        if cfg.get("ignore_paths") and config.ignored(git_repo, path, cfg):
            continue  # declared out of scope after this stamp was made: takes effect without re-stamping
        if a is None:
            state = _worse(state, UNKNOWN)
            reasons.append(f"anchor-not-in-drift-output: {target}")
            continue
        code = (a.get("reason") or {}).get("code")
        lines = _note_lines(text, stamp.mentions.get(target, []))
        # Only code and config files are read as text: a note may bind an image, which has no text.
        current_text = (repo / path).read_text(encoding="utf-8", errors="replace") \
            if _parsed(path) and (repo / path).is_file() else None
        # drift reports a TS symbol missing when it can no longer parse the file (JSX added to a .js
        # file); if livedocs still finds it there, it is a change to compare, not a broken anchor.
        lost_by_drift = (code == "symbol_not_found" and "#" in target and ts.is_ts(path)
                         and astdiff.symbol_source(current_text, target.split("#", 1)[1], path=path) is not None)
        if a["result"] != "fresh" and code in drift_io.BROKEN_CODES and not lost_by_drift:
            moved = _find_move(repo, target, binding, idx) if binding.members else None
            if moved:
                state = _worse(state, CHANGED)
                # A pure move is benign, unless the note names the file the code left: then "X is in
                # src/boot.ts" became false (gravity-works seq 332, two auto-acked misses in TS Run 1).
                kind = MOVED_FROM_NAMED if _names_path(text, path) else "moved"
                findings.append(Finding(target, path, binding.qualnames[0] if binding.qualnames else target,
                                        kind, None, None, lines, None, f"now in {moved}"))
            else:
                state = _worse(state, BROKEN)
                findings.append(Finding(target, path, binding.qualnames[0] if binding.qualnames else target,
                                        "anchor-missing", None, None, lines, None, code))
            continue
        if current_text is not None and _parsed(path) and not astdiff.parses(current_text, path=path):
            # Mid-edit file: fail closed rather than report every symbol as removed.
            state = _worse(state, UNKNOWN)
            if f"parse-error: {path}" not in reasons:
                reasons.append(f"parse-error: {path}")
            continue
        deco_now = astdiff.decorator_hash(current_text or "", target.split("#", 1)[1], path=path) if "#" in target and current_text else ""
        # The member hashes are authoritative for what the note mentions: drift's fingerprint is the
        # trigger for symbols, but it does not see everything (a line added inside a string constant
        # left a file anchor `fresh` in 1b t5), so compare members whether or not drift flagged.
        changed_members: list[str] = []
        if binding.members and current_text is not None:
            changed_members = [q for q, h in binding.members.items()
                               if not astdiff.member_matches(h, current_text, q, path=path)]
        if a["result"] != "fresh" or deco_now != binding.deco or changed_members:
            if binding.members and not changed_members:
                refined.append(target)
                if refine:
                    continue
            state = _worse(state, CHANGED)
            findings.extend(_findings_for(repo, doc, target, binding, text, stamp, current_text, git_repo))
    warnings = [f"mentions `{d}`, which does not exist in src" for d in stamp.dangling]
    return Report(note, state, reasons, findings, stamp, warnings, refined)


def _parsed(path: str) -> bool:
    return path.endswith(".py") or ts.is_ts(path) or configkeys.is_config(path)


def _find_move(repo: Path, target: str, binding: st.Binding, idx) -> str | None:
    """An anchor drift can't find any more: is each mentioned symbol, under its top-level name, somewhere
    else with identical member hashes? Then it moved (the run-1 'split server.py' case; a renamed
    component file). A whole-file anchor moves when every member it carries is found elsewhere."""
    from . import symbols as sy
    old_path = target.split("#", 1)[0]
    if "#" in target:
        tops = [target.split("#", 1)[1]]
    elif binding.members:
        tops = sorted({q.split(".", 1)[0] for q in binding.members})
    else:
        return None
    if idx is None:
        idx = sy.index(repo, "WORKTREE")
    dests: set[str] = set()
    for top in tops:
        members = {q: h for q, h in binding.members.items() if q == top or q.startswith(top + ".")}
        hit = None
        for cand in idx.by_qualname(top):
            if cand.path == old_path or cand.qualname != top:
                continue
            src = (repo / cand.path).read_text(encoding="utf-8", errors="replace")
            if all(astdiff.member_matches(h, src, q, path=cand.path) for q, h in members.items()):
                hit = cand.path
                break
        if hit is None:
            return None
        dests.add(hit)
    return ", ".join(sorted(dests)) or None


MECHANICAL_KINDS = frozenset({astdiff.UNCHANGED, astdiff.COMMENT_ONLY, "moved"})


def _file_finding(target, path, was_src, now_src, lines, base) -> Finding:
    """A whole-file anchor's finding: comment/format-only across the whole TS module is benign."""
    if ts.is_ts(path) and was_src is not None and now_src is not None:
        a, b = ts.file_hash(path, was_src), ts.file_hash(path, now_src)
        if a is not None and a == b:
            return Finding(target, path, "", astdiff.COMMENT_ONLY, None, None, lines, base,
                           "the whole file: comments/formatting only")
    return Finding(target, path, "", "file", None, None, lines, base, "file changed")
MOVED_FROM_NAMED = "moved-from-named-file"  # not mechanical: the note names the file the code left


def _names_path(text: str, path: str) -> bool:
    """Whether the note mentions `path` (or a suffix of it, `boot.ts`) as a path in backticks."""
    from . import mentions as mn, symbols as sy
    stem = sy._strip_ext(path)
    for m in mn.mentions(text):
        if m.kind != mn.PATH:
            continue
        t = m.text.removeprefix("./")
        if t.startswith("@"):  # a tsconfig alias (@/components/Card, @components/Card) names a path below a root
            t = t[1:].lstrip("/")
        t_stem = sy._strip_ext(t)
        if t and (path == t or path.endswith("/" + t) or stem == t_stem or stem.endswith("/" + t_stem)):
            return True
    return False


def mechanically_benign(r: Report) -> bool:
    """True when every finding is provably benign to the mentioned members: comment/docstring-only
    edits, verified pure moves, or 'the class changed elsewhere'. Such a report can be acked
    mechanically with a recorded reason; it must never be treated as fresh silently."""
    return r.state == CHANGED and bool(r.findings) and all(f.kind in MECHANICAL_KINDS for f in r.findings)


def _worse(a: str, b: str) -> str:
    order = {FRESH: 0, UNKNOWN: 1, CHANGED: 2, BROKEN: 3}
    return a if order[a] >= order[b] else b


def _findings_for(repo: Path, doc: str, target: str, binding: st.Binding, text: str, stamp: st.Stamp,
                  now_src: str | None, git_repo: Path | None = None) -> list[Finding]:
    git_repo = git_repo or repo
    path = target.split("#", 1)[0]
    try:
        base = gitx.diff_base(git_repo, doc, target, binding.sig)
    except gitx.GitError:
        base = None
    was_src = gitx.blob_at(git_repo, base, path) if base else None
    lines = _note_lines(text, stamp.mentions.get(target, []))
    quals = binding.qualnames or ([target.split("#", 1)[1]] if "#" in target else [])
    sx = lambda src, q: astdiff.symbol_source(src or "", q, path=path)
    out: list[Finding] = []
    if not quals or quals == [""]:  # whole-file anchor with nothing specific mentioned
        out.append(_file_finding(target, path, was_src, now_src, lines, base))
        return out
    top = target.split("#", 1)[1] if "#" in target else path.rsplit("/", 1)[-1]
    for q in quals:
        if not q:  # the note names the whole file (a small module): any change in it is the note's concern
            if was_src is None or was_src != now_src:
                out.append(_file_finding(target, path, was_src, now_src, lines, base))
            continue
        member_same = bool(binding.members.get(q)) and astdiff.member_matches(binding.members[q], now_src, q, path=path)
        if member_same:
            # The member hash is what a mention depends on (a class's shell, a function's substance):
            # if it is unchanged the change is benign by construction, whatever a full-AST diff says
            # (a class mention must not flag when only an unmentioned method body changed — 1b, t6).
            ch = astdiff.Change(astdiff.UNCHANGED, sx(was_src, q) if was_src else None, sx(now_src, q))
        elif was_src is not None:
            ch = astdiff.classify(was_src, now_src, q, path=path)
            if ch.kind == astdiff.UNCHANGED and ":" in binding.members.get(q, ""):
                # The member hash (current scheme) says this changed; equal source text must not overrule
                # it, or the gate would ack a real change as benign. Only 0.1's bare Python hashes, which
                # differ across CPython minors, are left to the text comparison.
                ch = astdiff.Change(astdiff.BODY, ch.was, ch.now)
        else:
            ch = astdiff.Change("unknown-base", None, sx(now_src, q))
        detail = ""
        if ch.kind == astdiff.UNCHANGED:
            if was_src is None:
                detail = f"{q} unchanged (comments/formatting or elsewhere in {top}; no committed base yet)"
            elif "#" not in target:
                detail = f"{top} changed elsewhere; {q} unchanged"
            elif q != top:
                top_ch = astdiff.classify(was_src, now_src, top, path=path)
                detail = f"{top} changed elsewhere ({top_ch.kind}); {q} unchanged"
            elif astdiff.classify(was_src, now_src, q, path=path).kind in (astdiff.UNCHANGED, astdiff.COMMENT_ONLY):
                detail = f"{q} unchanged in substance (comments/formatting only)"
            else:  # a class whose shell is unchanged: the edit is inside members the note doesn't name
                detail = f"{q} unchanged where the note depends on it (its shell); the change is inside members it doesn't name"
        out.append(Finding(target, path, q, ch.kind, ch.was, ch.now, lines, base, detail))
    return out
