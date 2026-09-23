---
type: session
status: active
authority: log
summary: "The user answered the six questions from the design review; design revised to v0.3 around 'the guarantee', scope narrowed to code docs, strict thresholds, testbench = clone of a real project."
created: 2026-09-22
updated: 2026-09-22
reviewed: 2026-09-22
tags: [live-docs, session]
---

# 2026-09-22 Resolving the Review

## Goal

Apply the user's answers to the questions left open by [[2026-09-21 Design Review]].

## What was done

- The user answered all six questions put to them (recorded as D4–D8 in [[Decision Log]]).
- [[Live Docs Design]] revised to **v0.3**. The biggest change is a reframing, not a mechanism change: the product is a *guarantee* that an agent reading a note about code is told if the code is technically out of date. Whether notes make agents better is now a secondary question.
- Consequences worked through in the design:
  - `specifies` notes, invariant routing, arm D and non-code anchors are cut, not deferred.
  - Authority is removed from the mechanism (this vault's own `authority` property stays as a convention for agents working here).
  - The guarantee's two conditions are stated explicitly: it covers reads through the gate, and claims that mention code. Prose-only claims are `unbound` → `unknown`.
  - 1a (signal quality on replayed history) is primary; its kill criteria are strict (misses > 10%, precision < 50%). 1b (agent behaviour) gates Phase 2 investment at 15 points but can't kill the guarantee.
  - Bypasses get a concrete escalation path (Bash deny → Grep tagging → MCP gateway) if Phase 1 measures them above 5%.
  - A grading method for 1a is proposed (P19): agent grades everything by rubric, user grades every miss plus 25 calibration flags.

## Decisions

- **User:** D4 (code docs only), D5 (the guarantee is the product), D6 (markdown in repo, Obsidian as interface), D7 (strict thresholds), D8 (testbench is a detached clone of a real project + vault).
- **Agent proposals:** P19–P21, awaiting review. The specific 1a numbers (10% / 50%) are the agent's reading of "more strict"; the user set only the direction.

## Testbench set up (later the same session)

- The user delegated the project choice and accepted the grading split (D9, D10).
- **Survey of `~/Projects`:** hpc-bridge was the only repo with Python, 300+ commits *and* an Obsidian vault. Runners-up: Academy and Harnesses (439 commits, no vault), cairn-service (298, no vault).
- **hpc-bridge facts:** 324 commits (2026-05-30 → 2026-09-22); vault at `docs/hpc-bridge-vault/`, created at `0ff0646` (2026-06-25, 249 commits before tip), grown from its first notes to 49 at tip−100 and 70 at tip; `Modules/` has 27 notes naming real symbols with line hints and the caveat "exact line numbers drift — grep the symbol".
- **Detached clone** at `live-docs/testbench/hpc-bridge` (origin removed; `testbench/` gitignored).
- **drift v0.10.1 installed** via Homebrew. Smoke test on the clone:
  - `drift link Modules/server.md src/hpc_bridge/server.py#_connect_facility` resolved and stamped (`sig:656b9cc0…`); same for `config.py#_control_settings`.
  - Inserting a no-op line in `_connect_facility`'s body → flagged stale. Inserting blank lines only → not flagged. Both as designed.
  - `drift check --format json` exists (schema `drift.check.v1`), which the livedocs wrapper can consume. `--help` on subcommands is not supported.
  - On the untouched repo drift reports "3 docs stale, 3 broken links". Inspected: the three are markdown links to vault notes with URL-encoded spaces (`Reference/MEP%20facilities%20survey.md`); the files exist. **drift doesn't percent-decode link targets** — a drift false positive, not real drift. Worth reporting upstream, and a ready-made cause tag for 1a.
  - JSON schema per doc: `path`, `result` (`fresh`/`stale`/`broken`), `anchors[]`, `links[]` each with `result` and `reason.code`. The wrapper can build on this directly.
- **Plan change (P22):** the replay window is vault-creation → tip, and real note edits in history count as re-stamps.

## Open threads / next steps

- Inspect the 3 stale / 3 broken items drift found on the clean repo.
- Write the livedocs wrapper: `stamp` (derive anchors from mentions), `check` (read-only, was/now output), `affected`.
- Build the replay harness for 1a over `0ff0646..HEAD`.
## Write-time posture decided (D11)

- Discussed the postures for what happens when an agent changes code that notes depend on: list-don't-block, block at Stop, block once with a deferral queue, block at commit, graded, queue + separate reconciler, auto-reconcile.
- **The user chose block at commit.** Recorded as D11 and written into design §6.6. Key properties: index-based check; `unknown` never blocks; CI backstop; Stop hook stays a non-blocking heads-up; every commit's notes are vouched for against that commit's code, which makes the diff base always resolvable.
- Phase 1a stays list-only for clean measurement; 1b tests block-at-commit.

## Implementation plan and its review

- Wrote [[Implementation Plan]] v0.1 (package layout, components, CLI, milestones, seven flagged choices), after probing drift: it binds top-level symbols only (`Class.method` fails), `drift refs` takes a target, and the Stop hook supports non-blocking `additionalContext`.
- One reviewer subagent, with read access to the testbench, found eleven issues ([[2026-09-22 Implementation Plan Review]]). The orchestrating agent re-verified the two with the largest code impact: drift refuses to re-link an existing binding (use `--doc-is-still-accurate`), and a renamed symbol is `stale` + `symbol_not_found`, not `broken`.
- Plan revised to **v0.2**. Biggest changes: the 1a harness (first-parent, check-before-stamp, grade all at-risk rows, flag episodes), the ambiguity superset policy for mentions, decorator hashing, the block-pickaxe diff base, and fail-closed shell wrappers for hooks. M4 (the 1a number) now comes before hooks and pre-commit.
- Useful numbers from the reviewer: the first-parent window is 141 commits; 1,435 backtick spans in the 27 `Modules/` notes; 86 note-edit events, 44 coinciding with a change to the note's own module.

## M1 built: mentions and symbols

- Package `livedocs` (uv, stdlib only, hatchling) with `mentions.py`, `symbols.py`, a `survey` CLI, and 12 tests on a mini git fixture.
- **Survey of all 70 hpc-bridge notes at HEAD:** 6,779 backtick mentions; 2,832 resolved, 352 superset, 111 constant-only, 3,484 unresolved; 670 symbols in 37 files. **Modules/ only:** 1,003 mentions → 660 resolved, 60 superset, 31 constant, 252 unresolved, 405 distinct drift targets.
- Hand-check: every sampled `name:top-level` and `dotted` binding was correct; all supersets were legitimate over-binding (e.g. `manager_online` → the four facility classes). No false anchor found.
- Changes made during the check:
  - Dropped the "identifier shorter than 4 chars" noise rule to "shorter than 3"; the index rejects the rest.
  - Indexed class attributes / dataclass fields (`phase`, `session_id`), which lifted Modules resolution from 549 to 660.
  - Bare module names (`server`, `login`) resolve to the whole file (rule `name:module`, 12 bindings). Whole-file anchors are noisy; the stamp step should make them optional.
  - `Class.member` where the class part is an alias (`app.teardown_task`) resolves by member name.
- Caveat for grading: short attribute names (`profile`, `compute`, `tasks`) bind to whichever class has that field; wrong guesses over-flag, never false-fresh. Cause tag `attribute-guess`.

## Repo published

- Initial commit `46c102f`, then pushed to **https://github.com/GusEllerm/vault-drift** (private). The user chose the name `vault-drift`. The local directory remains `~/Projects/live-docs`.

## Notes for the next agent

- The user said they are "happy to discuss further" on scope (D4). Treat it as decided unless they reopen it.
- drift is installed and smoke-tested (see above). `drift refs <file>` printed nothing in the smoke test; its argument form still needs working out.
- The testbench clone has an untracked `drift.lock` from the smoke test with two bindings. Delete it or build on it; it is not part of hpc-bridge.
