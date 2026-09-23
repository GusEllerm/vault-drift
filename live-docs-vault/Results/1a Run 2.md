---
type: results
status: active
authority: log
summary: "Phase 1a, run 2 (with the D fixes): false flags cut 40%, precision 2.7% → 5.1%, but member-level suppression lost recall (misses 1 → 6). Conclusion: triggers should stay coarse and feed a judge; refinement is an annotation, not a suppressor."
created: 2026-09-23
updated: 2026-09-23
reviewed: 2026-09-23
tags: [live-docs, results, phase-1a]
---

# 1a Run 2

> **Status:** agent-graded (Opus graders for the 455 new items; 728 verdicts carried over from [[1a Run 1]] where the question was unchanged; 67 pre-graded mechanically). The user's calibration pass is still pending. Artefacts in `results/1a-run2/`.

## What changed between runs (D12, step D)

- Member-level fingerprints: a drift class-level flag is **suppressed** when none of the members the note mentions changed.
- Comment/docstring/formatting-insensitive hashes.
- Move detection: a symbol drift can't find, whose mentioned members hash identically elsewhere, reads `changed(moved)` instead of `broken`.
- Short bare attribute names need the note's own module (no more `attribute-guess` binding).
- Dangling-mention warnings (`_login_wait_s()` no longer exists) and file anchors for explicit config-file paths (`pyproject.toml`, `SKILL.md`).

## Numbers

| Metric | Run 1 | Run 2 | Rule |
|---|---|---|---|
| Flag episodes | 830 | 509 | |
| Real catches (flag made the note wrong) | 22 | 26 | |
| False flags | 808 | 483 | |
| **Flag precision** | 2.7% | **5.1%** | kill < 50%: still fails |
| Note-level precision (flagged note wrong for any reason) | 26.5% | 26.1% | |
| At-risk rows (note fresh, anchored file changed) | 377 | 650 | |
| Misses an anchor could have caught | 1 | **6** | |
| Prose-only misses (excluded) | 6 | 11 | |
| **Miss rate** (excluding prose-only) | 4.3% | **18.8%** | kill > 10%: **now fails** |
| Checks refined away from a drift flag | — | 4,462 | |

False-flag causes, run 2: irrelevant 329, moved 66, file-anchor 34, class-granularity 23, other 14, attribute-guess 10, formatter 5. The fixable classes did shrink (class-granularity 338 → 23, comment-only 89 → 0, moved 56 → 66 but now auto-graded). `irrelevant` — the mentioned symbol changed, the claim survived — is now two-thirds of all false flags, as predicted.

## The trade-off the refinement exposed

Four of the five new non-prose misses were **flagged in run 1 and graded "still-right" per flag**, with `note_wrong = true`. Examples: `Cost control.md` at the commit that added `_stop_mep` (the note says stop always cancels over the login endpoint); `The MCP tools.md` when `stop_endpoint` started returning `down` on an orphaned endpoint; `state.md`'s "nothing calls `LoginNodeStore.remove`" when `_drop_dead_pin` appeared. In each case the class or module the note anchors changed *somewhere the note didn't name*, and that somewhere is what made the note wrong. Run 1's coarse flag was right for the wrong reason; run 2's precise flag was absent.

So the member-level hash is a **precision/recall knob**, not a free improvement:
- as a *suppressor* it removes 40% of flags and loses a quarter of the real catches;
- as an *annotation* ("the class changed; the members you mention did not") it costs nothing and gives a judge exactly the fact it needs.

## Other findings

- **File anchors** (new): 58 episodes, 4 real catches (`SKILL.md`, `plugin.json`, a seed YAML whose facility id was renamed), 34 false. The catches are real config drift a symbol anchor can't see; the noise is mostly dated review notes that quote files.
- **Constants can't be anchored** (`shapes.md` → `SHAPES`, `DEFAULT_SHAPE`): drift can't bind them, and that was the one `unbound-mention` miss. Now that member hashes exist this is cheap: bind the file with drift and hash the assignment ourselves.
- **Callee behaviour** is the residual, inherent miss class: the note's claim is about what a function *does*, and that behaviour lives one call down. Anchors deliberately don't follow the call graph (design §6.4); the judge can't see it either. Only the author's edit catches it.
- **Prose-only misses doubled** (6 → 11) because there are far more at-risk rows to grade; they are the same kinds of claim as before (tool counts, env-var semantics, "no behaviour lives here").

## Against the pre-registered rules

Precision fails (5.1% < 50%) and, with suppression on, the miss rate now fails too (18.8% > 10%). The mechanism as a **verdict** is dead either way; that was already the run-1 conclusion. As a **trigger**, run 1's configuration (coarse flags) had the recall the guarantee needs, and the judge is what turns that trigger into something an agent can trust.

## Consequences for the judge (step C)

1. **Triggers stay coarse.** drift's top-level flag fires the judge; member hashes annotate which mentioned members changed (or "none — the change is elsewhere in the class").
2. **Suppression becomes a config option, off when a judge is present**, on only as a no-judge fallback where alarm fatigue matters more than the last quarter of recall.
3. **The judge's benchmark is now 1,231 + 455 graded items** across the two runs, with per-flag and note-level labels. Target: ≥ 90% agreement, `wrong`-recall ≥ 90%.
4. **Add constant anchors** before run 3.

## Caveats

- Opus graders for run 2's new items, Fable for run 1's; graders applied the same rubric and reused precedents, but model mix is a confound the user's calibration pass will partly test.
- Run-1 verdicts were reused for 728 items by (note text, commit, target); a changed finding kind (e.g. `moved` vs `anchor-missing`) does not invalidate a reused verdict, which is intended.
- Same single-repo caveat as run 1.
