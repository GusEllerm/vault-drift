---
type: design
status: draft
authority: specifies
summary: "Optional automation (superseded as core by D13): an LLM judge between the hash and the agent for changes made without an agent in the loop. The committing agent is the judge in the core design."
created: 2026-09-23
updated: 2026-09-23
reviewed: 2026-09-23
tags: [live-docs, design, judge]
---

# Judge

> **Status: optional automation, not core (D13, 2026-09-23).** The user's reframing: the hash mismatch is a deterministic signal ("note unedited, code it mentions changed"), and the agent that made the change is the judge, at commit. A model judge would re-derive context that agent already has. This note is kept as a design for automating reconciliation later (e.g. for changes made by tools or humans without an agent in the loop). The draft below predates D13.

## Why

Run 1 measured what a hash can and can't do: 96% of the note-wrong changes an anchor covered were flagged, but only ~3% of flags marked a change that made the note wrong, and ~7% even after the tooling noise is removed. A `CHANGED` state that is benign 19 times in 20 will be tuned out, which defeats the guarantee (D5) as surely as silence.

The literature's recipe (READU, DocPrism) is a two-stage pipeline: a cheap high-recall filter, then a model that judges only what the filter passed. The graders in run 1 *were* that judge, at roughly 4k tokens per episode, and their verdicts are the ground truth this design is tuned against.

## What the judge decides

Given one **episode** — a note, one flagged anchor, the `was`/`now` source of what the note mentions, the note lines that mention it, and the note text — it answers the rubric's question:

> Does this change make any claim in the note false? (`wrong` / `still-right`, one cause tag, one sentence.)

It also answers the note-level question when asked (`note_wrong`), but that is a different product (a periodic audit), not the read-time gate.

## Where it sits

```
code change ──► drift + member hashes ──► episode (note, anchor, was/now)
                       (recall ≈ 96%)             │
                                                  ▼
                                            LLM judge ──► wrong ──► agent sees CHANGED + the correction
                                        (precision = judge's)  └─► still-right ──► agent sees FRESH*
```

`FRESH*` means "verified by the judge against this change". The stamp records the judge's verdict so the same change is never judged twice (see Stamps).

Two placements, both wanted:
- **At commit (D11).** The pre-commit gate runs the judge on the episodes the staged change creates. `wrong` blocks until reconciled; `still-right` auto-acks with the judge's reason recorded. This is where nearly all judging happens: ~6 episodes per commit in the hpc-bridge history.
- **At read time, as a fallback.** If a note has unjudged episodes (uncommitted work, `--no-verify`, another tool's edit), the read gate either runs the judge synchronously (bounded: ≤ N episodes, else falls back) or shows the raw hash fact with an explicit "unjudged" label. Never silence.

## Stamps

A judge verdict is a stamp line with `verdict: "judge"`, the anchor, the sig pair it judged, the answer, cause and reason, and the model id. Freshness then reads: the note is `fresh` if its current member hashes match a stamp **or** every mismatch has a `judge: still-right` stamp for exactly that sig pair. A later change to the same anchor produces a new sig pair and is judged again.

Verdicts are append-only and reviewable in the diff, which is the anti-gaming property D11 bought; the judge can't be talked into re-stamping, it only ever sees one change at a time.

## What the judge sees (the prompt)

Exactly what the run-1 graders saw, since their verdicts are the benchmark:
1. The rubric's definition of "wrong" (claims about code only; incomplete ≠ wrong; exhaustive enumerations are claims; plan/status prose is not).
2. The finding: anchor, kind (signature / body / decorator / moved / missing), a unified diff of `was` → `now` (not two truncated prefixes — run-1 lesson).
3. The note lines that mention the symbol, with ±4 lines of context, and the whole note if it is short.
4. Nothing else. No repo access; the judge should not go looking for reasons the note is wrong for other changes — that is the audit product.

Output is the verdict line format from `results/rubric.md`.

## Cost

From run 1: 830 episodes over 141 commits ≈ 6 per commit; 4k tokens each on the grader agents, which also read full notes and often consulted the tree. A judge with the tight prompt above should sit at 1.5–3k tokens per episode. At commit time that is a few seconds and cents per commit; the D fixes (run 2) should cut the episode count by roughly half.

## Evaluation

The judge is only useful if it agrees with careful human grading. Plan:
- **Benchmark** = the run-1 (and run-2) verdicts, with the user's calibration verdicts where they exist.
- **Metric** = agreement with the benchmark on `verdict` (target ≥ 90%), and separately precision/recall of `wrong` (the judge must not miss real catches: recall of `wrong` ≥ 90%).
- **Cost** per episode.
- Run it on the 427 reader-graded run-1 episodes first (cheap, reproducible), then on run 2.

## Open questions

1. Which model, and does a small model reach the agreement target on the tight prompt?
2. Should `still-right` auto-ack at commit, or only mark the episode as judged and leave the ack to the human? (Auto-ack is convenient; it also means the vault's acks are mostly machine-written.)
3. Read-time synchronous judging: bounded how?
4. Does the judge see `note_wrong` (other-reason staleness) at all, or is that strictly the audit product?
