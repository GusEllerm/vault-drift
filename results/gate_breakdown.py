"""Per-language breakdown of a gate-mode replay's hand reconciliations. Usage: gate_breakdown.py <run dir>"""
import collections, json, sys
from pathlib import Path

BENIGN = {"unchanged", "comment-or-docstring-only", "moved"}
run = Path(sys.argv[1])
rows = {}
for l in (run / "rows.jsonl").open():
    r = json.loads(l)
    if r["phase"] == "check":
        rows[(r["commit"], r["note"])] = r
lang = lambda t: "py" if t.split("#")[0].endswith(".py") else "ts" if t.split("#")[0].endswith((".ts", ".tsx", ".js", ".mjs", ".jsx", ".cjs", ".astro")) else "other"
by_lang, by_kind, per_commit = collections.Counter(), collections.Counter(), []
for l in (run / "gate.jsonl").open():
    g = json.loads(l)
    per_commit.append(len(g["hand"]))
    for n in g["hand"]:
        r = rows.get((g["commit"], n), {"findings": [], "state": "?"})
        real = [f for f in r["findings"] if f["kind"] not in BENIGN]
        by_lang[tuple(sorted({lang(f["target"]) for f in real})) or (r["state"],)] += 1
        by_kind.update({f["kind"] for f in real})
blocked = [x for x in per_commit if x]
print(f"{run.name}: hand={sum(per_commit)} over {len(per_commit)} commits; blocked commits={len(blocked)}; "
      f"mean notes per blocked commit={sum(blocked) / max(1, len(blocked)):.1f}; max={max(per_commit, default=0)}")
print("  by language of the non-benign findings:", dict(by_lang.most_common()))
print("  by finding kind:", dict(by_kind.most_common()))
