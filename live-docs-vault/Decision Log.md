---
type: decision-log
status: active
authority: specifies
summary: "Every project decision, with date, who made it (user or agent), and status (accepted, proposed, contested or superseded)."
created: 2026-09-21
updated: 2026-09-22
reviewed: 2026-09-22
tags: [live-docs, decisions]
---

# Decision Log

**Status meanings:**
- **accepted:** the user decided it, or approved an agent's proposal.
- **proposed:** an agent suggested it and the user hasn't confirmed it. Don't build on it as if it were settled.
- **contested:** reviewers disagree, and the user has to call it.
- **superseded / rejected:** kept for history.

For a decision that needs more than one row, write a note from the [[Decision]] template and link it here.

## Accepted

| ID | Date | Decision | By | Source |
|---|---|---|---|---|
| D1 | 2026-09-21 | Core concept: notes in an Obsidian vault act as long-term live documentation for agent-built software. Notes that depend on code embed a fingerprint of it, checked when read. | user | [[2026-09-21 Research and Design]] |
| D2 | 2026-09-21 | The vault at `live-docs-vault/` in the project directory is this project's long-term, cross-session memory; notes go there. | user | [[2026-09-21 Research and Design]] |
| D3 | 2026-09-21 | The project is a git repo (branch `main`) and the vault is versioned in it. Only per-machine Obsidian UI state is ignored. | user | [[2026-09-21 Research and Design]] |
| D4 | 2026-09-22 | Scope is documentation of code only. Decisions, specs and invariants are a different system. (Resolves C1; the user is open to discussing further.) | user | [[2026-09-22 Resolving the Review]] |
| D5 | 2026-09-22 | The product is a guarantee: an agent reading a note about code is told if that code is technically out of date. Whether notes help agents is secondary. | user | [[2026-09-22 Resolving the Review]] |
| D6 | 2026-09-22 | Markdown in the repo; Obsidian is the interface for those files, not a dependency. (Resolves C3.) | user | [[2026-09-22 Resolving the Review]] |
| D7 | 2026-09-22 | Thresholds are strict rather than lenient: 15 points for Phase 2 investment; 1a kill at >10% misses or <50% precision. (Resolves C4; the 1a numbers are the agent's reading of "more strict".) | user | [[2026-09-22 Resolving the Review]] |
| D8 | 2026-09-22 | The Phase 1 testbench is a clone of one of the user's existing projects plus its Obsidian vault, disconnected from the remote or on a never-pushed branch. | user | [[2026-09-22 Resolving the Review]] |
| D9 | 2026-09-22 | Testbench project: **hpc-bridge** (324 commits, 189 Python files, 70-note vault at `docs/hpc-bridge-vault/` with a `Modules/` folder naming real symbols). Detached clone at `live-docs/testbench/hpc-bridge` (origin removed, gitignored). The user delegated the choice; the agent chose because it was the only project meeting all three criteria. | user (delegated) | [[2026-09-22 Resolving the Review]] |
| D10 | 2026-09-22 | 1a grading split: agent grades everything by rubric; user grades every miss plus 25 calibration flags, 25 more if agreement < 85%. (Accepts P19.) | user | [[2026-09-22 Resolving the Review]] |
| D12 | 2026-09-23 | **1a verdict: D then C.** Fix the tooling noise (member-level fingerprints, comment-insensitive hashing, move detection, attribute resolution, dangling-mention warning, file anchors for config files), re-run 1a, then add an LLM judge between the hash and the agent. (Resolves C5.) | user | [[1a Run 1]] |
| D11 | 2026-09-22 | **Write-time posture: block at commit.** A pre-commit hook compares *staged* blobs; `changed` and `broken` notes in the staged tree must be updated or acked before the commit; `unknown` never blocks. CI runs the same check as the backstop for `--no-verify`, merges and rebases. The Stop hook stays non-blocking (a heads-up). Consequence: every commit's notes are vouched for against that commit's code, so the diff base is always the last commit that touched the stamp. Phase 1a stays list-only; 1b tests block-at-commit directly (update / ack / `--no-verify` behaviour). | user | [[2026-09-22 Resolving the Review]] |

## Proposed: design v0.2 (awaiting user review)

These came out of [[2026-09-21 Design Review]]. All three critics agreed on them after round 2.

| ID | Date | Proposal | Design ref |
|---|---|---|---|
| P10 | 2026-09-21 | Phase 1 tests value first: 1a signal quality on replayed history, then 1b agent trials with arms A (no notes), B (notes + CLAUDE.md rule) and C (notes + gate), with kill criteria written down in advance | §8 |
| P11 | 2026-09-21 | Use drift unmodified plus a thin livedocs wrapper; go upstream before forking | §7 |
| P12 | 2026-09-21 | Read-time output delivers was / now code facts pinned to note lines, never "this line is wrong"; ≤1,500 characters; each change once per session | §6.7 |
| P13 | 2026-09-21 | "Code wins" covers only what the system does, never what it should do | §6.2, §6.7 |
| P14 | 2026-09-21 | Four states (`fresh` / `changed` / `broken` / `unknown`), failing closed; any change to an anchored symbol is `changed` | §6.5 |
| P15 | 2026-09-21 | Checks are read-only; stamps are append-only and include the note's hash; the diff base comes from `git log -S<sig> -- drift.lock` | §6.3, §6.4 |
| P16 | 2026-09-21 | Anchors are derived from code mentions (`depends_on` is an optional override); zero anchors means `unknown` | §6.3 |
| P17 | 2026-09-21 | Write-time output is batched into one Stop hook; read-time gate on `Read`; bypasses logged | §6.6 |
| P18 | 2026-09-21 | Retire only `broken` notes or with the user's sign-off; measure gaming before building an LLM judge | §6.8 |
| P8 | 2026-09-21 | The vault lives inside the repo it documents (unchanged from v0.1) | §6.10 |

## Proposed: v0.3 additions (awaiting user review)

| ID | Date | Proposal | Design ref |
|---|---|---|---|
| P19 | 2026-09-22 | 1a grading: an agent grades everything against a rubric; the user grades every miss plus 25 calibration flags (another 25 if agreement < 85%) | §9 Q2 |
| P20 | 2026-09-22 | Bypass escalation: measure in Phase 1; above 5% of vault reads, close holes in cost order (Bash deny → Grep tagging → MCP gateway) | §6.6 |
| P21 | 2026-09-22 | 1a is primary and tests the guarantee; 1b is secondary and gates Phase 2 investment only | §8 |
| P22 | 2026-09-22 | Replay window is vault-creation → tip (~249 commits), not tip−200. A real edit to a note in history counts as a re-stamp by its author; the check runs against the note as last stamped. | §8 |

## Contested: resolved

| ID | Question | Resolution |
|---|---|---|
| C5 | 1a verdict: recall passed, flag precision failed. Stop / redefine / judge / fix-and-rerun? | D then C (D12, 2026-09-23). |

| ID | Question | Resolution |
|---|---|---|
| C1 | Keep `specifies` notes? | Cut (D4). |
| C2 | Phase 1 size | 3 arms; arm D and invariant tasks cut with C1 (D4). |
| C3 | Obsidian's role | Interface, not dependency (D6). |
| C4 | Continue threshold | Strict: 15 points (D7). |

## Superseded proposals (v0.1)

| ID | Proposal | Status |
|---|---|---|
| P1 | Four authority kinds, with mismatches resolved by authority | superseded: only `describes` is hashed in Phase 1; `specifies` is contested (C1) |
| P2 | `depends_on` declared by hand; fingerprints in `.livedocs/lock.toml` | superseded by P15, P16 |
| P3 | Two-stage check with sig/impl hashes and early cutoff | superseded by P11, P14 (early cutoff made reads write; sig/impl split deferred) |
| P4 | Record `verified_at` for diffs | superseded by P15 (a commit can't record its own SHA) |
| P5 | Write-time hook per edit; read-time as safety net; CI backstop | superseded by P17 (CI deferred) |
| P6 | Graded policy with a "code wins" banner | superseded by P12, P13 (evidence misread) |
| P7 | Update / ack / retire with an LLM judge for stale acks | superseded by P18 |
| P9 | Spike by wrapping drift | refined into P11 |
