---
type: results
status: active
authority: log
summary: "Phase 1a, run 1 on hpc-bridge: recall passes (4.3% misses), flag precision fails (2.7%); the hash is a high-recall trigger, not a verdict. Decision needed on the pre-registered kill rule."
created: 2026-09-23
updated: 2026-09-23
reviewed: 2026-09-23
tags: [live-docs, results, phase-1a]
---

# 1a Run 1

> **Status:** agent-graded; the user's calibration pass (7 misses + 25 random flags, `results/1a-run1/user-calibration.md`) is pending. Numbers may move slightly after it.
> **Artefacts:** `results/1a-run1/` in the repo (summary, episodes, verdicts; rows and items compressed). Replay branch `replay/20260923-…` in the testbench clone.

## Setup (as run)

- Testbench: hpc-bridge, first-parent history `0ff0646..main`, 141 commits after the vault's creation (2026-06-25 → 2026-09-22).
- All 70 notes with code mentions stamped; anchors derived from backtick mentions; drift v0.10.1 fingerprints (top-level symbols) plus a decorator hash; author edits to notes treated as re-stamps (P22).
- 7,744 checks; 302 history re-stamps; 830 flag episodes (one per note × stamp × anchor); 377 at-risk rows (note read fresh while an anchored file changed) and 24 pre-edit-fresh rows.
- Grading per D10 and `results/rubric.md`: 403 episodes graded mechanically (nothing the note mentioned changed), 828 items by 12 grader agents, `verdict` per flagged change and `note_wrong` at note level. Two conventions fixed after the pilot: an exhaustive enumeration gaining a member is *wrong*; a new optional field is *incomplete, not wrong*.

## Numbers

| Metric | Value | Pre-registered rule |
|---|---|---|
| Real catches (flag made the note wrong) | 22 | — |
| Misses an anchor could have caught | 1 | — |
| **Miss rate** (excluding prose-only) | **4.3%** | kill above 10% → **passes** |
| Prose-only misses (nothing anchorable) | 6 | reported separately |
| **Flag precision** (all 830 episodes) | **2.7%** | kill below 50% → **fails** |
| Flag precision, reader-graded episodes only | 5.2% | |
| Note-level precision (note wrong for any reason when flagged) | 26.5% | |
| Fresh-reading notes that were in fact wrong for unanchored reasons | 42 of 394 at-risk rows (11%) | condition 2 of the guarantee |
| Pre-edit signal | 104 of 128 author edits to notes whose anchored code changed were already flagged | |

**Why the flags were false** (808 episodes):

| Cause | Count | Fixable? |
|---|---|---|
| class-granularity (the class changed, not the member mentioned) | 362 | yes — member-level fingerprints (drift only binds top-level symbols) |
| irrelevant (the mentioned symbol changed; the claim survived) | 304 | **no** — the inherent limit of a hash |
| comment / docstring only | 89 | yes — mechanical |
| moved (the "split server.py" refactor; pure moves with re-exports) | 56 | yes — move detection |
| attribute-guess (short field name bound to the wrong class) | 11 | yes — resolution rules |
| formatter | 4 | yes |
| other | 6 | |

Fixing everything fixable leaves 22 real vs ~310 false: precision ≈ 7%.

**The seven misses** (`results/1a-run1/user-calibration.md`, items 1–7): six are claims with no anchorable symbol — "the shape is still hardcoded today", "no behaviour lives here", env-var semantics in `Configuration.md`, "zero `instructions=` in src". One is a callee behaviour change (`_stop_endpoint` now returns `draining`) behind an unchanged anchored wrapper — anchors deliberately don't follow the call graph.

## What the data says

1. **As a trigger, the mechanism works.** When an anchored symbol changed and that mattered, the check fired 22 of 23 times. Authors' own edits confirm it: 81% of relevant note edits were preceded by a flag.
2. **As a verdict, "symbol changed ⇒ note out of date" is wrong 93–97% of the time** in this repo, and ~90% even after all tooling noise is removed. This is exactly the literature's result (a hash says *that*, not *how*), now measured on real history.
3. **The note-level picture is worse than the flag-level one for the guarantee's second condition:** 11% of notes reading `fresh` were wrong for reasons no anchor covers — tool counts ("eleven tools"), stale helper names (`_login_wait_s()` no longer exists), `pyproject.toml` dependency claims, PR-status prose. Two of these are addressable: a *dangling-mention* lint (a name that used to resolve and no longer does) and package anchors.
4. **Broken ≠ wrong.** The "split server.py" refactor produced 218 `broken` episodes, almost all pure moves with re-exports. Without move detection, a large refactor floods the vault with the loudest state for no real drift.

## Against the pre-registered rules (design §8)

- Miss rate: **pass**.
- Precision: **fail**, well below the "fix causes and re-run" band (30%).
- Bypass rate: not measured (no agent trials in 1a).

Read literally, 1a kills the design as written: a `CHANGED` state that is benign 19 times in 20 will be ignored, which defeats the guarantee just as surely as silence would.

## Options for the user

- **A. Stop.** Ship drift-in-CI plus a CLAUDE.md rule, per the pragmatist's fallback.
- **B. Change what the state means, keep the mechanism.** `CHANGED` becomes "code this note relies on changed since it was verified; here is what changed" — a fact, not a staleness verdict — and 1b tests whether agents *use* that fact or tune it out. Cheap; but 1a already says the signal is 93% benign, so 1b would be testing alarm fatigue directly.
- **C. Add the judge (the literature's recipe).** Keep the hash as the high-recall filter and put an LLM judge between it and the agent: hash flags ~6 episodes per commit; the judge decides "does this change contradict the note?" and only then does the agent see `CHANGED`. The graders in this run *were* that judge, at ~4k tokens per episode. Precision then depends on the judge; recall stays at the hash's. This is the deferred item from §11 promoted to core, and it changes the cost model (a model call per flagged episode at commit time).
- **D. Fix the fixable noise first** (member-level fingerprints, comment stripping, move detection, dangling-mention lint, package anchors), re-run 1a, then choose between B and C on ~7% inherent precision instead of 3%.

The agent's recommendation is **D then C**: the fixable noise (65% of false flags) is worth removing regardless, and the judge is the only path to a state an agent can trust. B is the honest minimum if the judge's cost is unacceptable.

## Caveats

- Agent-graded; calibration pending. Graders reported the hardest calls consistently: "incomplete vs wrong" and whether dated review notes count as code claims.
- Batch files truncated long `was`/`now` excerpts identically, so graders often read the replay branch directly; the export should show a diff.
- Run 1 predates the sync→async = signature fix (affects `kind` labels only).
- One repo, one author, one vault style (dense notes with many code mentions). Precision would differ on sparser docs.
