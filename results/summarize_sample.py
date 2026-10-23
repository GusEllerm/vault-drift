"""Summarise a stratified grading sample (see sample_items.py). Usage: summarize_sample.py <run dir>

Each stratum's graded rate is scaled to its population (Wilson 95% interval on the rate). Then:
  real catches   = wrong in S1 (flagged, needed a reader) + wrong in S2 (flagged, provably benign)
  misses         = wrong in S3 (at risk) + S4 (pre-edit fresh), prose-only claims reported apart
  1a miss rate   = misses / (catches + misses)                 — comparable to the Python runs
  gate miss rate = (misses + S2 catches) / (catches + misses)  — S2 is acked unseen at the gate
  P29 cost       = wrong in S5 (a file named only by path changed), reported apart and folded in
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float, float]:
    if n == 0:
        return 0.0, 0.0, 0.0
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return p, max(0.0, c - h), min(1.0, c + h)


def main() -> int:
    run = Path(sys.argv[1])
    s = run / "sample"
    manifest = json.loads((s / "manifest.json").read_text())
    verdicts: dict[str, dict] = {}
    for p in sorted(s.glob("verdicts-*.jsonl")):
        for l in p.read_text().splitlines():
            if l.strip():
                v = json.loads(l)
                verdicts[v["id"]] = v
    est, report = {}, {}
    for name, m in manifest.items():
        ids = m["ids"]
        graded = [verdicts[i] for i in ids if i in verdicts]
        wrong = [v for v in graded if v["verdict"] == "wrong"]
        prose = [v for v in wrong if v.get("cause") == "prose-only-claim"]
        anch = len(wrong) - len(prose)
        n, pop = len(graded), m["population"]
        p, lo, hi = wilson(anch, n)
        pp, plo, phi = wilson(len(prose), n)
        est[name] = (p * pop, lo * pop, hi * pop)
        est[name + " prose"] = (pp * pop, plo * pop, phi * pop)
        causes: dict[str, int] = {}
        for v in graded:
            key = f"{v['verdict']}:{v.get('cause', '')}"
            causes[key] = causes.get(key, 0) + 1
        report[name] = {"population": pop, "graded": n, "of_sampled": m["sampled"], "wrong(anchorable)": anch,
                        "wrong(prose-only)": len(prose), "rate": round(p, 3), "rate_95ci": [round(lo, 3), round(hi, 3)],
                        "estimated": round(p * pop, 1), "estimated_95ci": [round(lo * pop, 1), round(hi * pop, 1)],
                        "causes": causes}
    g = lambda k, i=0: est.get(k, (0, 0, 0))[i]
    catches = g("S1 episode-reader") + g("S2 episode-auto")
    misses = g("S3 at_risk") + g("S4 pre_edit_fresh")
    path = g("S5 path_risk")
    rate = lambda m, c: m / (c + m) if c + m else 0.0
    out = {
        "strata": report,
        "estimated_real_catches": round(catches, 1),
        "estimated_misses_anchorable": round(misses, 1),
        "estimated_prose_only_misses": round(g("S3 at_risk prose") + g("S4 pre_edit_fresh prose"), 1),
        "1a_miss_rate": round(rate(misses, catches), 3),
        "gate_miss_rate": round(rate(misses + g("S2 episode-auto"), catches), 3),
        "path_only_misses (P29 cost)": round(path, 1),
        "1a_miss_rate_with_path_only": round(rate(misses + path, catches), 3),
        "gate_miss_rate_with_path_only": round(rate(misses + path + g("S2 episode-auto"), catches), 3),
        "note": "point estimates; per-stratum 95% intervals in strata[*].estimated_95ci",
    }
    (s / "summary.json").write_text(json.dumps(out, indent=1))
    print(json.dumps(out, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
