"""Grading for the 1a run: export items with all the context a grader needs, and summarise verdicts.

Item kinds
  episode        a (note, stamp, anchor) that was flagged non-fresh — grader asks: was the note actually wrong?
  at_risk        a fresh row where an anchored file changed in that commit — grader asks: did this commit make
                 the note wrong?  (a "yes" is a miss)
  pre_edit_fresh the author edited a note although its anchors read fresh — same question (candidate miss)

Verdicts (verdicts.jsonl): {"id": …, "verdict": "wrong" | "still-right", "cause": <tag>, "by": …}
Causes: real, class-granularity, formatter, comment-only, decorator, prose-only-claim, moved, ambiguous-superset,
        attribute-guess, file-anchor, other
"""

from __future__ import annotations

import json
import subprocess
from collections import Counter
from pathlib import Path

from . import astdiff, gitx

MAX_DIFF_LINES = 160
MAX_NOTE_LINES = 120


def _replay_commits(repo: Path, branch: str) -> dict[int, str]:
    """seq → replay commit hash, from the branch's own commit messages."""
    out = gitx.run(repo, "log", "--reverse", "--format=%H %s", branch)
    m: dict[int, str] = {}
    for line in out.splitlines():
        h, _, msg = line.partition(" ")
        if msg.startswith("replay ") and "(seq " in msg:
            m[int(msg.rsplit("(seq ", 1)[1].rstrip(")"))] = h
    return m


def _note_excerpt(text: str, lines: list[int], ctx: int = 4) -> str:
    ls = text.splitlines()
    if len(ls) <= MAX_NOTE_LINES or not lines:
        return "\n".join(f"{i:4}: {l}" for i, l in enumerate(ls[:MAX_NOTE_LINES], 1))
    keep: set[int] = set()
    for n in lines:
        keep.update(range(max(1, n - ctx), min(len(ls), n + ctx) + 1))
    out, last = [], 0
    for i in sorted(keep):
        if i != last + 1:
            out.append("   …")
        out.append(f"{i:4}: {ls[i - 1]}")
        last = i
    return "\n".join(out)


def _diff(repo: Path, a: str, b: str, paths: list[str]) -> str:
    if not paths:
        return ""
    out = subprocess.run(["git", "-C", str(repo), "diff", "--stat=80", "-p", a, b, "--", *paths],
                         capture_output=True, text=True).stdout.splitlines()
    if len(out) > MAX_DIFF_LINES:
        out = out[:MAX_DIFF_LINES] + [f"… ({len(out) - MAX_DIFF_LINES} more lines)"]
    return "\n".join(out)


def export(repo: str | Path, vault_rel: str, out_dir: str | Path) -> Path:
    repo, out_dir = Path(repo).resolve(), Path(out_dir).resolve()
    meta = dict(l.split("=", 1) for l in (out_dir / "replay.txt").read_text().splitlines() if "=" in l)
    branch = meta["branch"]
    seqs = _replay_commits(repo, branch)
    rows = [json.loads(l) for l in (out_dir / "rows.jsonl").read_text().splitlines()]
    episodes = [json.loads(l) for l in (out_dir / "episodes.jsonl").read_text().splitlines()]
    items: list[dict] = []

    def note_at(seq: int, note: str, pre: bool = False) -> str:
        rc = seqs[seq - 1] if pre else seqs[seq]
        return gitx.blob_at(repo, rc, f"{vault_rel}/{note}") or ""

    for e in episodes:
        seq = e["first_seq"]
        rc = seqs[seq]
        lines = sorted({n for f in e["findings"] for n in f["note_lines"]})
        findings = []
        for f in e["findings"]:
            was = now = None
            path, _, top = f["target"].partition("#")
            if f["base_commit"] and f["qualname"]:
                was = astdiff.symbol_source(gitx.blob_at(repo, f["base_commit"], path) or "", f["qualname"])
                now = astdiff.symbol_source(gitx.blob_at(repo, rc, path) or "", f["qualname"])
            findings.append({"target": f["target"], "qualname": f["qualname"], "kind": f["kind"], "detail": f["detail"],
                             "was": was, "now": now, "note_lines": f["note_lines"]})
        items.append({"id": f"ep:{e['note']}|{e['stamp_id']}|{e['target']}", "kind": "episode", "note": e["note"],
                      "seq": seq, "commit": e["first_commit"][:8], "state": e["state"], "reasons": e["reasons"],
                      "findings": findings, "note_excerpt": _note_excerpt(note_at(seq, e["note"]), lines),
                      "question": "Given the code change, is any claim in this note now wrong?"})

    for r in rows:
        if r["at_risk"] or (r["phase"] == "pre_edit" and r["state"] == "fresh" and r["bound_paths_changed"]):
            kind = "at_risk" if r["at_risk"] else "pre_edit_fresh"
            seq = r["seq"]
            text = note_at(seq, r["note"], pre=(r["phase"] == "pre_edit"))
            items.append({"id": f"{kind}:{r['note']}|{r['commit'][:8]}", "kind": kind, "note": r["note"], "seq": seq,
                          "commit": r["commit"][:8], "state": r["state"], "changed_paths": r["bound_paths_changed"],
                          "code_diff": _diff(repo, seqs[seq - 1], seqs[seq], r["bound_paths_changed"]),
                          "note_excerpt": _note_excerpt(text, []),
                          "question": "These anchored files changed but the note read FRESH. Did the change make any claim in the note wrong?"})

    (out_dir / "items.jsonl").write_text("\n".join(json.dumps(i, separators=(",", ":")) for i in items) + "\n")
    with (out_dir / "items.md").open("w") as f:
        for i in items:
            f.write(f"\n---\n## {i['id']}\n**{i['kind']}** · note `{i['note']}` · seq {i['seq']} · commit {i['commit']} · state {i['state']}\n\n")
            f.write(f"**Q:** {i['question']}\n\n")
            for fd in i.get("findings", []):
                f.write(f"- `{fd['target']}` {fd['qualname']} — **{fd['kind']}** {fd['detail']} (note lines {fd['note_lines']})\n")
                if fd.get("was") or fd.get("now"):
                    f.write(f"  ```\n  was: {(fd['was'] or '').strip()[:600]}\n  ---\n  now: {(fd['now'] or '').strip()[:600]}\n  ```\n")
            if i.get("code_diff"):
                f.write(f"\n```diff\n{i['code_diff']}\n```\n")
            f.write(f"\n<details><summary>note</summary>\n\n```\n{i['note_excerpt']}\n```\n</details>\n")
    counts = Counter(i["kind"] for i in items)
    print(f"exported {len(items)} items: {dict(counts)} → {out_dir / 'items.jsonl'}, {out_dir / 'items.md'}")
    return out_dir / "items.jsonl"


def summarize(out_dir: str | Path, exclude_prose_only: bool = True) -> dict:
    out_dir = Path(out_dir)
    items = {json.loads(l)["id"]: json.loads(l) for l in (out_dir / "items.jsonl").read_text().splitlines()}
    verdicts = [json.loads(l) for l in (out_dir / "verdicts.jsonl").read_text().splitlines() if l.strip()]
    hits = false_flags = misses = at_risk_ok = 0
    causes: Counter = Counter()
    for v in verdicts:
        it = items.get(v["id"])
        if not it:
            continue
        causes[(it["kind"], v["verdict"], v.get("cause", ""))] += 1
        if it["kind"] == "episode":
            if v["verdict"] == "wrong":
                hits += 1
            else:
                false_flags += 1
        else:
            if v["verdict"] == "wrong":
                if exclude_prose_only and v.get("cause") == "prose-only-claim":
                    continue
                misses += 1
            else:
                at_risk_ok += 1
    precision = hits / (hits + false_flags) if hits + false_flags else None
    miss_rate = misses / (misses + hits) if misses + hits else None
    res = {"graded": len(verdicts), "episodes_wrong(hits)": hits, "episodes_still_right(false_flags)": false_flags,
           "unflagged_wrong(misses)": misses, "unflagged_ok": at_risk_ok,
           "precision": precision, "miss_rate": miss_rate,
           "causes": {f"{k[0]}/{k[1]}/{k[2]}": n for k, n in causes.most_common()}}
    print(json.dumps(res, indent=1))
    return res
