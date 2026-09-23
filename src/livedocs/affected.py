"""Which notes does a code change touch? Changed files → bindings in drift.lock → notes → check."""

from __future__ import annotations

from pathlib import Path

from . import check as ck, drift_io, gitx, stamps as st


def affected_notes(repo: str | Path, vault_rel: str, changed: list[str]) -> list[str]:
    """Notes (vault-relative) with a binding whose path is in `changed`."""
    repo = Path(repo)
    changed_set = set(changed)
    notes: set[str] = set()
    prefix = f"{vault_rel}/" if vault_rel else ""
    for (doc, target), _sig in drift_io.lock(repo).items():
        if target.split("#", 1)[0] in changed_set and doc.startswith(prefix):
            notes.add(doc[len(prefix):])
    return sorted(notes)


def affected(repo: str | Path, vault_rel: str, *, cached: bool = False, base: str = "HEAD",
             changed: list[str] | None = None, snapshot: str | Path | None = None,
             refine: bool = False) -> list[ck.Report]:
    """Reports for every note bound to a changed file. `snapshot` runs the checks against a
    checkout-index copy (the pre-commit gate) while git operations use `repo`."""
    repo = Path(repo)
    if changed is None:
        changed = gitx.changed_files(repo, cached=cached, base=base)
    files_root = Path(snapshot) if snapshot else repo
    notes = affected_notes(files_root, vault_rel, changed)
    if not notes:
        return []
    try:
        dj = drift_io.check_json(files_root)
    except drift_io.DriftError as e:
        return [ck.Report(n, ck.UNKNOWN, [f"checker-error: {e}"]) for n in notes]
    all_stamps = st.load(files_root / vault_rel)
    return [ck.check(files_root, vault_rel, n, drift_json=dj, all_stamps=all_stamps, refine=refine, git_repo=repo) for n in notes]


def summary_lines(reports: list[ck.Report]) -> list[str]:
    out = []
    for r in reports:
        if r.state in (ck.FRESH, ck.SNAPSHOT):
            continue
        if ck.mechanically_benign(r):
            extra = " (benign: the members it mentions are unchanged — will be auto-acked at commit)"
        else:
            kinds = sorted({f.kind for f in r.findings} - {"unchanged"})
            extra = f" ({', '.join(kinds)})" if kinds else (f" ({'; '.join(r.reasons)})" if r.reasons else "")
        out.append(f"{r.state.upper():8} {r.note}{extra}")
    return out
