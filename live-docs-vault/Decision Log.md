---
type: decision-log
status: active
authority: specifies
summary: "Every project decision, with date, who made it (user or agent), and status (accepted, proposed, contested or superseded)."
created: 2026-09-21
updated: 2026-10-23
reviewed: 2026-10-23
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
| D15 | 2026-09-23 | **"Aligned" means stamped against the current code:** an `update` (note edited, then stamped) or an `ack` with a required reason; provably benign changes are acked mechanically. Text edits are not forced — a forced touch invites cosmetic edits and vaguer notes; an ack with a committed reason is reviewable. (The signature-tightening option was offered and not adopted.) | user | [[2026-09-23 Runs 1 and 2]] |
| D14 | 2026-09-23 | **The guarantee is a mechanism of the development framework, not a capability of the agent.** Tier 0, always: a versioned pre-commit hook (`.githooks/`, activated with `core.hooksPath`) plus the same check in CI; works for any agent or human. Tier 1, recommended: the Claude Code Stop heads-up (non-blocking, note names only), installed in `settings.local.json`; the failed commit's own output is the universal fallback channel. Tier 2, opt-in: the read-time gate. Tier 3, measurement only: the bypass log. The `AGENTS.md` instruction block is convenience, not part of the guarantee. Hook commands resolve `livedocs` on PATH, never an interpreter path. | user | [[2026-09-23 Runs 1 and 2]] |
| D13 | 2026-09-23 | **The signal is deterministic, not a verdict.** A flag means exactly "this note has not been edited and code it mentions has changed". Whether the note still reads correctly is the job of the agent who made the change, at commit (D11), where it has the context. Consequences: no separate LLM judge (the committing agent is the judge; the [[Judge]] note becomes optional automation); precision is an overhead measure, not a kill criterion; what matters is recall, reconciliation overhead per commit, and a coverage signal for claims no anchor can see. Member-level suppression is a knob (−40% overhead, −25% catches); the default is annotation. Supersedes the "then C" half of D12. | user | [[2026-09-23 Runs 1 and 2]] |
| D12 | 2026-09-23 | **1a verdict: D then C.** Fix the tooling noise (member-level fingerprints, comment-insensitive hashing, move detection, attribute resolution, dangling-mention warning, file anchors for config files), re-run 1a, then add an LLM judge between the hash and the agent. (Resolves C5.) | user | [[1a Run 1]] |
| D11 | 2026-09-22 | **Write-time posture: block at commit.** A pre-commit hook compares *staged* blobs; `changed` and `broken` notes in the staged tree must be updated or acked before the commit; `unknown` never blocks. CI runs the same check as the backstop for `--no-verify`, merges and rebases. The Stop hook stays non-blocking (a heads-up). Consequence: every commit's notes are vouched for against that commit's code, so the diff base is always the last commit that touched the stamp. Phase 1a stays list-only; 1b tests block-at-commit directly (update / ack / `--no-verify` behaviour). | user | [[2026-09-22 Resolving the Review]] |
| D16 | 2026-09-23 | **MIT licence.** (Recorded 2026-10-23; the choice is in the session log.) | user | [[2026-09-23 Runs 1 and 2]] |
| D18 | 2026-10-23 | **P29 accepted with a 600-line limit:** a backtick path to a TS/JS/Astro module binds the whole file if the module has at most 600 lines, otherwise only its default export (`path_anchors` configurable). Chosen from [[TS Run 1]]'s curve: 362 hand reconciliations on gravity-works (931 under 0.1.4), 5 of the 6 sampled anchorable misses flagged. | user | [[2026-10-23 TypeScript Support]] |
| D19 | 2026-10-23 | **Release 0.2.0:** merge `ts-support` into `main`, tag `v0.2.0`, publish to PyPI. P26–P28 and P30–P32 ship as built; their status stays proposed until reviewed. | user | [[2026-10-23 TypeScript Support]] |
| D20 | 2026-10-23 | **The global `livedocs` tool is installed from PyPI**, not as an editable install of the live-docs checkout, so development can't reach other projects' gates. | user | [[2026-10-23 TypeScript Support]] |
| D17 | 2026-09-24 | **Distribute through PyPI; the repo stays private.** Chosen over making the repo public when an agent couldn't install from the private repo. Releases are tag-driven (`v*`) via trusted publishing. (Recorded 2026-10-23.) | user | [[2026-09-24 PyPI Release]] |

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
| P19 | 2026-09-22 | 1a grading: an agent grades everything against a rubric; the user grades every miss plus 25 calibration flags (another 25 if agreement < 85%). **Accepted as D10.** | §9 Q2 |
| P20 | 2026-09-22 | Bypass escalation: measure in Phase 1; above 5% of vault reads, close holes in cost order (Bash deny → Grep tagging → MCP gateway) | §6.6 |
| P21 | 2026-09-22 | 1a is primary and tests the guarantee; 1b is secondary and gates Phase 2 investment only | §8 |
| P22 | 2026-09-22 | Replay window is vault-creation → tip (~249 commits), not tip−200. A real edit to a note in history counts as a re-stamp by its author; the check runs against the note as last stamped. | §8 |
| P23 | 2026-09-23 | With a judge present, triggers stay coarse (drift top-level flags) and member hashes only annotate; member-level suppression is a no-judge fallback option. Run 2 showed suppression costs a quarter of real catches. | [[1a Run 2]] |
| P25 | 2026-09-23 | **Snapshot notes are not live documentation.** Dated review/report notes (`Reference/Review 2026-09-03 — …`) mention nearly every symbol and were hand-acked "dated snapshot" in every 1b task. Proposal: a frontmatter flag (`livedocs: snapshot`, or `authority: log`) makes `stamp` bind nothing and `check` report `snapshot` (never `changed`), so they cost no reconciliation. **Implemented 2026-09-23** (`livedocs: snapshot` frontmatter or `snapshot_globs` in config); on hpc-bridge it removed 44% of bindings and took t1 from 4 hand acks to 0. | [[1b Run 1]] |
| P24 | 2026-09-23 | Anchor module constants (drift binds the file; we hash the assignment). The one `unbound-mention` miss in run 2 was a constant. **Implemented 2026-09-23** and proven on `shapes.md`. | [[1a Run 2]] |

## Proposed: TypeScript support (awaiting user review)

From [[TypeScript Support]], built on 2026-10-23 for the personal-website request; measured in [[TS Run 1]].

| ID | Date | Proposal | Ref |
|---|---|---|---|
| P26 | 2026-10-23 | **Parse TS/JS/Astro with tree-sitter**, a hard dependency (`tree-sitter`, `tree-sitter-typescript`, about 4 MB of wheels), imported only when a repository has such files. Retires the README's "stdlib only" line. Alternatives: a hand-written scanner (JSX text, regex literals and ASI make a false *benign* likely, which silently breaks the guarantee); the project's own `node`/`tsc` (not present in the gate's index snapshot or every CI). | [[TypeScript Support#2. What is built]] |
| P27 | 2026-10-23 | **drift fingerprints where it can, the file is bound elsewhere.** `.ts`/`.js` top-level symbols bind at drift's symbol granularity; JSX files, `.mjs` and similar, Astro, `default`, keys and closures bind the file and carry member hashes (P24's pattern). Stamp falls back to the file when drift refuses a symbol; a symbol drift loses but livedocs still parses is a change, not `broken`. | §2 |
| P28 | 2026-10-23 | **Mixed repositories resolve in the note's language first** (its module's, else at least ¾ of its unambiguous mentions), falling back to both. scheduler-dojo: 61 → 23 Python mentions picking up TS candidates. | §2 |
| P29 | 2026-10-23 | **Accepted as D18 (with a 600-line limit).** A path to a TS/JS/Astro module binds the whole file if it has at most N lines, otherwise only its default export (`path_anchors`: a line limit, `"file"`, or `"default-export"`). *Revised the same day:* the first version (default export only, never the whole file) cut gate overhead on gravity-works by 77% but its graded 1a miss rate was about 20%, above D7's 10%. Under the revised rule 11 of the 12 sampled misses are flagged (all 6 anchorable), 10 of them through whole-file anchors on named modules of 620 lines or fewer, while half of 0.1's overhead came from one 1,600-line hub ([[TS Run 1]]). `.py` paths still bind nothing. **Changes behaviour for existing TS vaults** (upgrade with `livedocs rebind`). | §2, README |
| P30 | 2026-10-23 | **JSON config key anchors**: known config files and `.jsonc` only; the value's hash per key path. | §2 |
| P31 | 2026-10-23 | **Stamping drops a note's orphaned bindings; `livedocs rebind`** re-acks every unedited note under the current rules (the upgrade path for P29). | §2 |
| P33 | 2026-10-23 | **A path never binds another vault note, media, fonts, archives or lockfiles**; Markdown outside the vault still binds (in a plugin it is the product: hpc-bridge's skills and commands). From the personal-website Phase 0 review; Python repos unchanged (hpc-bridge: same 1,669 binding mentions). | [[2026-10-23 TypeScript Support]] |
| P34 | 2026-10-23 | **`ignore_paths` config** (globs): nothing in them is indexed or bound, checks skip existing bindings to them, and a commit touching only such paths passes the gate untouched (site content committed from Obsidian). | [[2026-10-23 TypeScript Support]] |
| P35 | 2026-10-23 | **The gate runs nothing for a commit that touches no note and no bound file, and blocks with a clear message when drift is genuinely missing** (before, a missing drift silently stamped notes unbound). Hooks find `livedocs` and `drift` under a GUI app's minimal PATH via the clone's git config (`livedocs.launcher`, `livedocs.drift`, recorded by `init`) and the usual install directories. | [[2026-10-23 TypeScript Support]] |
| P32 | 2026-10-23 | **Member hashes carry their scheme** (`py2:`, `ts1:`, `json1:`; bare = 0.1 Python), each compared with the function that made it. `py2` is stable across CPython minors (0.1's was not: CI on 3.12 failed stamps made on 3.13). The TS grammar is pinned exactly; upgrading it is a new scheme. | §2 |

## Where the proposals stand (agent summary, 2026-10-23)

Agent-written, checked against the code at 0.1.4. **Nothing here changes a proposal's status**; the user accepts or rejects each one. "Overlaps" names accepted decisions that already settle part of it.

| ID | In the code | Overlaps |
|---|---|---|
| P8 | Yes: the vault lives in the repo it documents. | — |
| P10 | 1a ran twice; 1b ran in D13's form (the commit gate, one arm), not arms A/B/C. | D13 |
| P11 | Yes: drift unmodified, livedocs wraps it. | — |
| P12 | Partly: was/now pinned to note lines, capped at 1,500 characters (`render.py`). No once-per-session dedupe. | — |
| P13 | Yes: the report's rule line says the code decides what the system does. | — |
| P14 | Yes, plus a fifth state, `snapshot` (P25). | — |
| P15 | Yes: checks are read-only, stamps append-only with the note hash, diff base from `git log -S` on `drift.lock` (`gitx.py`). | — |
| P16 | Partly: anchors come from mentions. `depends_on` enters the note hash but doesn't add or override anchors. | — |
| P17 | Yes, as tiers: Stop heads-up recommended; read gate and bypass log opt-in. | D11, D14 |
| P18 | Retire isn't built. Gaming was measured in [[1b Run 1]] (none seen). | D13 (no separate judge) |
| P19 | Accepted as D10. | D10 |
| P20 | Not built; the bypass log is measurement only. | D14 |
| P21 | 1a ran first and was primary; its metrics are now recall, overhead and coverage. | D13 |
| P22 | Yes (`replay.py`). | — |
| P23 | Annotation is the default and suppression a flag; there is no judge. | D13 |
| P24 | Yes. | — |
| P25 | Yes. | — |
| P26–P32 | Built in 0.2.0 (branch `ts-support`). | — |

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
