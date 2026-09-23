"""The freshness check: state machine (design §6.5) plus findings with was/now.

`check` never writes anything.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from . import astdiff, drift_io, gitx, stamps as st

FRESH, CHANGED, BROKEN, UNKNOWN = "fresh", "changed", "broken", "unknown"


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

    def to_dict(self) -> dict:
        return {
            "note": self.note, "state": self.state, "reasons": self.reasons,
            "findings": [f.__dict__ for f in self.findings],
            "stamped": self.stamp.stamped if self.stamp else None,
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
          text: str | None = None, all_stamps: list[st.Stamp] | None = None) -> Report:
    """`text` overrides the note's on-disk content (the replay harness passes the pre-edit text
    to ask whether the old note was wrong about the new code)."""
    repo = Path(repo)
    vault = repo / vault_rel
    doc = _doc_path(vault_rel, note)
    note_path = vault / note
    if text is None:
        if not note_path.exists():
            return Report(note, UNKNOWN, ["note-missing"])
        text = note_path.read_text(encoding="utf-8")
    current = st.note_hash(text)

    note_stamps = st.for_note(all_stamps if all_stamps is not None else st.load(vault), note)
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
    for target, binding in stamp.bindings.items():
        a = by_target.get(target)
        path = target.split("#", 1)[0]
        if a is None:
            state = _worse(state, UNKNOWN)
            reasons.append(f"anchor-not-in-drift-output: {target}")
            continue
        code = (a.get("reason") or {}).get("code")
        if a["result"] != "fresh" and code in drift_io.BROKEN_CODES:
            state = _worse(state, BROKEN)
            findings.append(Finding(target, path, binding.qualnames[0] if binding.qualnames else target, "anchor-missing",
                                    None, None, _note_lines(text, stamp.mentions.get(target, [])), None, code))
            continue
        current_text = (repo / path).read_text(encoding="utf-8") if (repo / path).exists() else None
        if current_text is not None and path.endswith(".py") and not astdiff.parses(current_text):
            # Mid-edit file: fail closed rather than report every symbol as removed.
            state = _worse(state, UNKNOWN)
            if f"parse-error: {path}" not in reasons:
                reasons.append(f"parse-error: {path}")
            continue
        deco_now = astdiff.decorator_hash(current_text or "", target.split("#", 1)[1]) if "#" in target and current_text else ""
        if a["result"] != "fresh" or deco_now != binding.deco:
            state = _worse(state, CHANGED)
            findings.extend(_findings_for(repo, doc, target, binding, text, stamp, current_text))
    return Report(note, state, reasons, findings, stamp)


def _worse(a: str, b: str) -> str:
    order = {FRESH: 0, UNKNOWN: 1, CHANGED: 2, BROKEN: 3}
    return a if order[a] >= order[b] else b


def _findings_for(repo: Path, doc: str, target: str, binding: st.Binding, text: str, stamp: st.Stamp, now_src: str | None) -> list[Finding]:
    path = target.split("#", 1)[0]
    base = gitx.diff_base(repo, doc, target, binding.sig)
    was_src = gitx.blob_at(repo, base, path) if base else None
    lines = _note_lines(text, stamp.mentions.get(target, []))
    quals = binding.qualnames or ([target.split("#", 1)[1]] if "#" in target else [])
    out: list[Finding] = []
    if not quals:  # whole-file anchor
        out.append(Finding(target, path, "", "file", None, None, lines, base, "file changed"))
        return out
    top = target.split("#", 1)[1]
    for q in quals:
        ch = astdiff.classify(was_src, now_src, q) if was_src is not None else astdiff.Change("unknown-base", None, astdiff.symbol_source(now_src or "", q))
        detail = ""
        if ch.kind == astdiff.UNCHANGED and q != top:
            top_ch = astdiff.classify(was_src, now_src, top)
            detail = f"{top} changed elsewhere ({top_ch.kind}); {q} unchanged"
        out.append(Finding(target, path, q, ch.kind, ch.was, ch.now, lines, base, detail))
    return out
