"""Stratified grading sample for a TypeScript 1a run (gravity-works, 2026-10-23).

After `livedocs grade export` and `pregrade`, the item population is far larger than run 1/2 graded in
full, so graders read a seeded random sample per stratum and the summary scales each stratum back up:

  S1 episode-reader   flagged, not provably benign        → real catches
  S2 episode-auto     flagged but provably benign (the gate would ack it unseen) → hidden misses at the gate
  S3 at_risk          fresh while an anchored file changed  → misses
  S4 pre_edit_fresh   the author edited a fresh note whose anchored file changed → misses (all graded)
  S5 path_risk        fresh, no anchored file changed, but a file the note names by path did (P29's cost)

Usage: sample_items.py <run dir> <repo> <vault_rel> [--n 50] [--seed 7]
Writes <run>/sample/{manifest.json, items.jsonl, batch-XX.md}.
"""

from __future__ import annotations

import argparse
import json
import random
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from livedocs import grade, mentions as mn  # noqa: E402


def git(repo, *a):
    return subprocess.run(["git", "-C", str(repo), *a], capture_output=True, text=True, errors="replace").stdout


def path_risk_items(run: Path, repo: Path, vault_rel: str) -> list[dict]:
    meta = dict(l.split("=", 1) for l in (run / "replay.txt").read_text().splitlines() if "=" in l)
    seqs = grade._replay_commits(repo, meta["branch"])
    rows = [json.loads(l) for l in (run / "rows.jsonl").read_text().splitlines()]
    out, seen = [], set()
    changed_cache: dict[str, set[str]] = {}
    for r in rows:
        if r["phase"] != "check" or r["state"] != "fresh" or r["bound_paths_changed"]:
            continue
        c = r["commit"]
        if c not in changed_cache:
            changed_cache[c] = set(git(repo, "diff-tree", "--no-commit-id", "-r", "--name-only", f"{c}^", c).split("\n")) - {""}
        changed = changed_cache[c]
        if not changed:
            continue
        text = git(repo, "show", f"{seqs[r['seq']]}:{vault_rel}/{r['note']}")
        hits = sorted({f for m in mn.mentions(text) if m.kind == mn.PATH
                       for f in changed if f == m.text.lstrip("./") or f.endswith("/" + m.text.lstrip("./"))})
        hits = [h for h in hits if not h.startswith(vault_rel + "/")]
        if not hits or (r["note"], c) in seen:
            continue
        seen.add((r["note"], c))
        lines = sorted({m.line for m in mn.mentions(text) if m.kind == mn.PATH and any(h.endswith(m.text.lstrip("./")) for h in hits)})
        out.append({"id": f"path_risk:{r['note']}|{c[:8]}", "kind": "path_risk", "note": r["note"], "seq": r["seq"],
                    "commit": c[:8], "state": r["state"], "changed_paths": hits,
                    "code_diff": grade._diff(repo, seqs[r["seq"] - 1], seqs[r["seq"]], hits),
                    "note_excerpt": grade._note_excerpt(text, lines, ctx=2),
                    "question": "The note names these files by path only (no symbol in them is anchored) and they changed "
                                "while the note read FRESH. Did the change make any claim in the note wrong?"})
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("run"); ap.add_argument("repo"); ap.add_argument("vault")
    ap.add_argument("--n", type=int, default=50); ap.add_argument("--n-auto", type=int, default=30)
    ap.add_argument("--n-path", type=int, default=30); ap.add_argument("--max-pre", type=int, default=40)
    ap.add_argument("--seed", type=int, default=7); ap.add_argument("--batch", type=int, default=28)
    a = ap.parse_args()
    run, repo = Path(a.run).resolve(), Path(a.repo).resolve()
    items = [json.loads(l) for l in (run / "items.jsonl").read_text().splitlines()]
    auto = {json.loads(l)["id"] for l in (run / "verdicts" / "auto.jsonl").read_text().splitlines() if l.strip()}
    strata = {
        "S1 episode-reader": [i for i in items if i["kind"] == "episode" and i["id"] not in auto],
        "S2 episode-auto": [i for i in items if i["kind"] == "episode" and i["id"] in auto],
        "S3 at_risk": [i for i in items if i["kind"] == "at_risk"],
        "S4 pre_edit_fresh": [i for i in items if i["kind"] == "pre_edit_fresh"],
        "S5 path_risk": path_risk_items(run, repo, a.vault),
    }
    sizes = {"S1 episode-reader": a.n, "S2 episode-auto": a.n_auto, "S3 at_risk": a.n,
             "S4 pre_edit_fresh": a.max_pre, "S5 path_risk": a.n_path}
    rng = random.Random(a.seed)
    sample, manifest = [], {}
    for name, pop in strata.items():
        k = min(sizes[name], len(pop))
        picked = rng.sample(pop, k)
        for i in picked:
            i["stratum"] = name
        sample += picked
        manifest[name] = {"population": len(pop), "sampled": k, "ids": [i["id"] for i in picked]}
    rng.shuffle(sample)  # graders see strata mixed, so a batch never reads as "all misses"
    out = run / "sample"
    out.mkdir(exist_ok=True)
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1))
    (out / "items.jsonl").write_text("\n".join(json.dumps(i, separators=(",", ":")) for i in sample) + "\n")
    for b in range(0, len(sample), a.batch):
        with (out / f"batch-{b // a.batch:02d}.md").open("w") as f:
            for i in sample[b:b + a.batch]:
                grade._write_item_md(f, i)
    print(json.dumps({k: {"population": v["population"], "sampled": v["sampled"]} for k, v in manifest.items()}, indent=1))
    print(f"{len(sample)} items → {(len(sample) + a.batch - 1) // a.batch} batches in {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
