"""The 1a harness: replay a repo's first-parent history, stamping notes as their authors
edited them and checking every stamped note at every commit (Implementation Plan §4.8).

Per commit c on a replay branch in a dedicated worktree:
  1. read-tree c (code + notes as of c); restore the carried drift.lock and stamps.
  2. check every stamped note against c's code and write a row.  Notes edited in c are
     checked with their PRE-edit text (pre_edit row): was the old note wrong about the new code?
  3. notes deleted/renamed in c: unlink their bindings.
  4. notes added/edited in c: stamp them (verdict update, by history).
  5. commit lock + stamps on the replay branch so the diff base resolves as in production.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from . import check as ck, drift_io, gitx, mentions as mn, stamp as stp, stamps as st, symbols as sy

LOCK = "drift.lock"


@dataclass
class Row:
    commit: str
    seq: int
    note: str
    phase: str  # "check" | "pre_edit"
    state: str
    reasons: list[str]
    findings: list[dict]
    stamp_id: str | None  # stamped timestamp+hash identifies the stamp an episode belongs to
    bound_paths_changed: list[str]  # anchored files that changed in this commit
    at_risk: bool  # state fresh, note untouched, but an anchored file changed

    def to_json(self) -> str:
        return json.dumps(self.__dict__, separators=(",", ":"))


@dataclass
class Summary:
    commits: int = 0
    rows: int = 0
    pre_edit_rows: int = 0
    stamps: int = 0
    stamp_failures: int = 0
    states: dict = field(default_factory=dict)
    pre_edit_states: dict = field(default_factory=dict)
    episodes: int = 0
    at_risk: int = 0
    seconds: float = 0.0


def _git(wt: Path, *args: str, check: bool = True) -> str:
    return gitx.run(wt, *args, check=check)


def note_events(wt: Path, commit: str, vault_rel: str) -> dict[str, list]:
    """{'A': [note], 'M': [note], 'D': [note], 'R': [(old, new)]} for notes touched in `commit`."""
    # Explicit first-parent range: `--first-parent` is a rev-list flag and silently empties diff-tree output.
    out = subprocess.run(
        ["git", "-C", str(wt), "diff-tree", "--no-commit-id", "-r", "-M", "--name-status", f"{commit}^", commit, "--", vault_rel],
        capture_output=True, text=True, check=True).stdout
    ev: dict[str, list] = {"A": [], "M": [], "D": [], "R": []}
    for line in out.splitlines():
        parts = line.split("\t")
        code = parts[0][0]
        if code == "R":
            old, new = parts[1], parts[2]
            if new.endswith(".md"):
                ev["R"].append((_rel(old, vault_rel), _rel(new, vault_rel)))
        elif code in ev and parts[1].endswith(".md"):
            ev[code].append(_rel(parts[1], vault_rel))
    return ev


def _rel(doc: str, vault_rel: str) -> str:
    return doc[len(vault_rel) + 1:] if vault_rel and doc.startswith(vault_rel + "/") else doc


def _changed_paths(wt: Path, commit: str) -> set[str]:
    out = subprocess.run(["git", "-C", str(wt), "diff-tree", "--no-commit-id", "-r", "--name-only", f"{commit}^", commit],
                         capture_output=True, text=True, check=True).stdout
    return {l for l in out.splitlines() if l}


def _has_mentions(text: str) -> bool:
    return any(True for _ in mn.iter_mentions(text))


def run(repo: str | Path, vault_rel: str, start: str, end: str, out_dir: str | Path, *,
        limit: int | None = None, file_anchors: bool = False, log=print) -> Summary:
    repo = Path(repo).resolve()
    out_dir = Path(out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    t0 = time.time()

    commits = [c for c in gitx.run(repo, "rev-list", "--first-parent", "--reverse", f"{start}^..{end}").split() if c]
    if limit:
        commits = commits[:limit]
    branch = "replay/" + datetime.now().strftime("%Y%m%d-%H%M%S")
    wt = repo.parent / f"{repo.name}-replay-wt"
    if wt.exists():
        gitx.run(repo, "worktree", "remove", "--force", str(wt), check=False)
        shutil.rmtree(wt, ignore_errors=True)
    gitx.run(repo, "worktree", "add", "-q", "-b", branch, str(wt), commits[0])
    vault = wt / vault_rel
    stamps_rel = f"{vault_rel}/{st.STAMPS_REL}"

    rows_f = (out_dir / "rows.jsonl").open("w")
    summ = Summary()
    carried_lock = carried_stamps = None  # bytes carried between commits
    stamped_notes: set[str] = set()

    for seq, c in enumerate(commits):
        short = c[:8]
        # 1. tree of c, plus carried livedocs state
        _git(wt, "read-tree", "-u", "--reset", c)
        if carried_lock is not None:
            (wt / LOCK).write_bytes(carried_lock)
        if carried_stamps is not None:
            (vault / st.STAMPS_REL).parent.mkdir(parents=True, exist_ok=True)
            (vault / st.STAMPS_REL).write_bytes(carried_stamps)
        ev = note_events(wt, c, vault_rel) if seq > 0 else {"A": [], "M": [], "D": [], "R": []}
        if seq == 0:  # everything present at the start commit counts as added
            ev["A"] = [str(p.relative_to(vault)) for p in vault.rglob("*.md") if ".obsidian" not in p.parts]
        changed = _changed_paths(wt, c)
        edited = set(ev["M"]) | {new for _, new in ev["R"]}
        gone = set(ev["D"]) | {old for old, _ in ev["R"]}

        # 2. check every stamped note (edited ones with their pre-edit text)
        all_stamps = st.load(vault)
        drift_json = None
        idx = sy.index(wt, "WORKTREE")  # one symbol index per commit, shared by check (moves) and stamp
        if stamped_notes:
            try:
                drift_json = drift_io.check_json(wt)
            except drift_io.DriftError as e:
                log(f"[{short}] drift check failed: {e}")
        for note in sorted(stamped_notes):
            phase, text = "check", None
            if note in edited or note in gone:
                prev = gitx.blob_at(wt, "HEAD", f"{vault_rel}/{note}")
                if prev is None:
                    continue
                phase, text = "pre_edit", prev
            rep = ck.check(wt, vault_rel, note, drift_json=drift_json, text=text, all_stamps=all_stamps, idx=idx)
            bound = sorted({t.split("#", 1)[0] for t in (rep.stamp.bindings if rep.stamp else {})} & changed)
            row = Row(c, seq, note, phase, rep.state, rep.reasons + [f"refined:{t}" for t in rep.refined],
                      [f.__dict__ | {"was": None, "now": None} for f in rep.findings],  # sources are recoverable from git; keep rows small
                      f"{rep.stamp.stamped}|{rep.stamp.note_hash[:12]}" if rep.stamp else None,
                      bound, rep.state == ck.FRESH and phase == "check" and bool(bound))
            rows_f.write(row.to_json() + "\n")
            summ.rows += 1
            if phase == "pre_edit":
                summ.pre_edit_rows += 1
                summ.pre_edit_states[rep.state] = summ.pre_edit_states.get(rep.state, 0) + 1
            else:
                summ.states[rep.state] = summ.states.get(rep.state, 0) + 1
            summ.at_risk += row.at_risk

        # 3. deleted / renamed notes: drop their bindings
        for note in sorted(gone & stamped_notes):
            doc = f"{vault_rel}/{note}"
            for (d, t), _sig in drift_io.lock(wt).items():
                if d == doc:
                    try:
                        drift_io.unlink(wt, d, t)
                    except drift_io.DriftError:
                        pass
            stamped_notes.discard(note)

        # 4. added / edited notes: stamp them as the author's re-verification
        to_stamp = sorted((set(ev["A"]) | edited) - gone)
        if to_stamp:
            for note in to_stamp:
                p = vault / note
                if not p.exists() or not _has_mentions(p.read_text(encoding="utf-8")):
                    continue
                # drop stale bindings for this doc first so the lock only holds what the new text mentions
                doc = f"{vault_rel}/{note}"
                for (d, t), _sig in drift_io.lock(wt).items():
                    if d == doc:
                        try:
                            drift_io.unlink(wt, d, t)
                        except drift_io.DriftError:
                            pass
                try:
                    r = stp.stamp(wt, vault_rel, note, by="history", verdict=st.UPDATE if note in stamped_notes else st.INITIAL,
                                  file_anchors=file_anchors, idx=idx)
                    summ.stamps += 1
                    summ.stamp_failures += len(r.failed)
                    stamped_notes.add(note)
                except stp.StampError as e:  # unchanged body (a rename or whitespace-only edit): keep the old stamp
                    log(f"[{short}] {note}: {e}")

        # 5. commit the replay state
        _git(wt, "add", "-A")
        _git(wt, "commit", "-q", "--allow-empty", "-m", f"replay {short} (seq {seq})")
        carried_lock = (wt / LOCK).read_bytes() if (wt / LOCK).exists() else None
        carried_stamps = (vault / st.STAMPS_REL).read_bytes() if (vault / st.STAMPS_REL).exists() else None
        summ.commits += 1
        log(f"[{seq:3}/{len(commits)}] {short} stamped={len(stamped_notes):3} rows={summ.rows} states={summ.states} pre_edit={summ.pre_edit_states}")

    rows_f.close()
    summ.episodes = _episodes(out_dir / "rows.jsonl", out_dir / "episodes.jsonl")
    summ.seconds = round(time.time() - t0, 1)
    (out_dir / "summary.json").write_text(json.dumps(summ.__dict__, indent=1))
    (out_dir / "replay.txt").write_text(f"branch={branch}\nworktree={wt}\nstart={commits[0]}\nend={commits[-1]}\n")
    return summ


def _episodes(rows_path: Path, out_path: Path) -> int:
    """One episode per (note, stamp, anchor target) that was ever non-fresh: the first row that flagged it."""
    seen: dict[tuple, dict] = {}
    for line in rows_path.read_text().splitlines():
        r = json.loads(line)
        if r["phase"] != "check" or r["state"] in ("fresh",):
            continue
        targets = {f["target"] for f in r["findings"]} or {"(none)"}
        for t in targets:
            key = (r["note"], r["stamp_id"], t)
            if key not in seen:
                seen[key] = {"note": r["note"], "stamp_id": r["stamp_id"], "target": t, "first_commit": r["commit"],
                             "first_seq": r["seq"], "state": r["state"], "reasons": r["reasons"],
                             "findings": [f for f in r["findings"] if f["target"] == t]}
    with out_path.open("w") as f:
        for e in seen.values():
            f.write(json.dumps(e, separators=(",", ":")) + "\n")
    return len(seen)
