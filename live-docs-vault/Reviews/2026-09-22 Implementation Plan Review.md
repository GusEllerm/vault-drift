---
type: review
status: active
authority: log
summary: "Single-reviewer critique of Implementation Plan v0.1; eleven issues, most verified against drift on the testbench; all folded into plan v0.2."
created: 2026-09-22
updated: 2026-09-22
reviewed: 2026-09-22
tags: [live-docs, review, implementation]
---

# 2026-09-22 Implementation Plan Review

> **Provenance.** One reviewer subagent, read-only, with permission to run drift and git in the testbench. Items marked *verified* were run by the reviewer; the orchestrating agent independently re-ran #2 and #3. Everything below was folded into [[Implementation Plan]] v0.2.

## Verdict

Buildable, and M1 → M2 → M4 is the right spine. But v0.1's replay harness would not have produced a defensible miss rate, and four of its "verified facts" about drift were wrong in ways that would have broken `stamp`, `affected` and the diff-base lookup.

## Issues

| # | Sev | Finding | Fix adopted |
|---|---|---|---|
| 1 | High | **Harness can't bound the miss rate** (*verified* on the testbench history). The first-parent window is 141 commits (249 with side branches, 21 merges). Of ~3,200 (commit, note) rows only ~120–160 are "at risk" (the note's own module changed, note untouched); a 10% random sample of fresh rows gives ~12–16 of them. Also stamp-then-check discards the best miss signal: 86 note-edit events, 44 in the same commit as a change to the note's own module. | Replay `--first-parent`. Check every note **before** re-stamping and record `pre_edit_state`. Grade **all** at-risk fresh rows. Count a flag episode once per (note, anchor, stamp), not per commit. |
| 2 | High | **`drift link` refuses to re-link** an existing binding, even with unchanged code (*verified twice*). Parsing `added` would yield zero-binding stamps → `unknown(unbound)` everywhere. | Always pass `--doc-is-still-accurate`; the note hash in our stamp carries the real semantics. |
| 3 | High | **drift has no `broken` result** (*verified twice*): renamed symbol → `stale` + `reason.code: symbol_not_found`; deleted file → `stale` + `file_not_found`. | Map those reason codes to `broken`. |
| 4 | High | **`git log -1 -S'sig = "<sig>"'` returns the wrong commit when a sig is shared** by two docs or recurs after a revert (*verified* in a throwaway repo). | Pickaxe the three-line `doc/target/sig` block, then verify the returned commit's `drift.lock` blob contains it. |
| 5 | High | **Ambiguity policy missing and would dominate** (*verified*: of 1,435 backtick spans in 27 Modules notes, 399 resolve to a unique top-level def/const, 37 to a unique method, ~67 are ambiguous names, 231 unresolvable, ~545 noise). Design §6.5 says ambiguous → `unknown`; applied literally most notes never reach `fresh`. | Prefer the note's own module (resolves 29 of ~95). Index `src/` only for name matches. Remaining ambiguity → bind **all** src candidates (superset: over-flags, never false-fresh), tagged. Strip `:NNN` line hints. Drop quoted spans. Constants can't be anchored by drift → recorded as unverified mentions. |
| 6 | Med | **Deleted notes stay fresh** in drift (*verified*); two notes are deleted in the window. | Delete/rename → `unlink` + retire before the per-commit check. |
| 7 | Med | **Worktree mechanics**: `git checkout c` detaches HEAD, so per-step commits don't extend the replay branch and the diff-base walk finds nothing. | `git read-tree -u --reset c` on the replay branch, restore carried lock + stamps, commit. |
| 8 | Med | **"Emit unknown" unreachable** on import error or harness timeout: a traceback exits 1 and goes to the user, not the model. | Hook command is a shell wrapper `… \|\| printf '<unknown JSON>'`; hook `timeout` set above the internal deadline; `signal.alarm` + subprocess timeouts. |
| 9 | Med | **Fingerprint sensitivity** (*verified*): decorator added → `fresh` (a miss); comment inside body, docstring edit, quote-style change → `stale` (false flags); whitespace → `fresh`. | Add a decorator hash per binding in the stamp. Classify the ast diff (signature / decorator / body / comment-or-docstring-only) so cause tags are automatic. |
| 10 | Low | **`drift refs` takes a target, not a file**; bare path prints nothing. drift ignores git, mtimes and `.gitignore` (*verified*: a no-`.git` copy gives identical sigs). | `affected` reads `drift.lock` directly. Index snapshot works; run with cwd at its root. |
| 11 | Low | **Freshness rule not enforced**: v0.1's state machine never compared the matching stamp's sigs to `drift.lock`. Line endings not normalised → Obsidian re-saves would unstamp notes. | Explicit stamp-vs-lock comparison; several matching stamps → newest whose bindings are all in the lock. Normalise line endings before hashing. |

## §7 recommendations (adopted)

- **a.** Measure class-granularity, but add decorator hashing now; a method-level `ast` hash is ~30 lines if needed.
- **b.** Body-only hash is fine (Modules notes have no frontmatter); fold `depends_on` into the hash input.
- **c.** Keep the `drift.lock` pickaxe with the block + blob-verify fix. It only needs "the commit that introduces a sig has matching code", which holds whether or not D11 does.
- **d.** Index snapshot is fine: 0.04 s on hpc-bridge.
- **e.** Drop once-per-session dedupe from Phase 1.
- **f.** Backtick-only mentions, with the issue-5 rules.
- **g.** No tree-sitter.

## For M4 specifically

- **Cut:** render polish, session dedupe, `affected`, `install-hooks`, pre-commit.
- **Add:** check-before-stamp with `pre_edit_state`; grade-all-at-risk; flag-episode dedupe; deletion handling; first-parent; the ambiguity superset; reason-code mapping; `--doc-is-still-accurate`; a `grade` view showing the note diff at author edits; stamp **all** notes with mentions (70), not just `Modules/`.
