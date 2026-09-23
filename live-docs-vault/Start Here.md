---
type: index
status: active
authority: describes
summary: "Entry point to this vault: what the project is, where it stands, and what to read first."
created: 2026-09-21
updated: 2026-09-22
reviewed: 2026-09-22
tags: [live-docs, index]
---

# Start Here

## What this project is

**live-docs** explores using an Obsidian vault as agent-first *live documentation* for software that agents build. Notes that describe code are bound to fingerprints (hashes) of the code they mention. When an agent reads a note whose code has changed, it gets the current facts instead of acting on out-of-date docs.

This vault is also the long-term, cross-session memory for the live-docs project itself. Agents working on the project read and write it across sessions.

## Current status

*As of 2026-09-22.*

- **Research and review are done.** Three critic agents reviewed design v0.1 ([[2026-09-21 Design Review]]); the user then resolved the contested points ([[2026-09-22 Resolving the Review]]).
- **[[Live Docs Design]] is at v0.3.** The product is a **guarantee**: an agent reading a note about code is told if that code is technically out of date. Scope is documentation of code only; Obsidian is the interface, not a dependency.
- **Phase 1 measures whether the guarantee holds** with strict kill criteria ([[Live Docs Design#8. Plan]]). **Testbench: hpc-bridge**, a detached clone at `testbench/hpc-bridge` (gitignored). Its vault was created 249 commits before tip, so the replay window is vault-creation → tip.
- **drift v0.10.1 is installed and smoke-tested** on the clone: it binds notes to Python symbols, flags body edits, ignores whitespace. Details in [[2026-09-22 Resolving the Review]].
- **No livedocs code yet.** The repo is `GusEllerm/vault-drift` on GitHub (private); the local folder is still named `live-docs`.
- **[[Implementation Plan]] v0.2 is written and reviewed.** Order: M1 mentions+symbols → M2 stamp/check → M4 replay harness (the 1a number) → M3 hooks → M5 pre-commit.
- **M1, M2 and M4 are done** (2026-09-23): `livedocs survey | stamp | check | replay | grade` work on the testbench.
- **The first 1a run is graded** — [[1a Run 1]]. Recall passes (4.3% misses); flag precision fails (2.7%; 26% at note level). The hash is a high-recall trigger, not a staleness verdict.
- **D is done and measured** — [[1a Run 2]]: false flags −40%, but member-level *suppression* lost a quarter of the real catches. **Then the user reframed the signal (D13):** a flag is the deterministic fact "note unedited, code it mentions changed"; the committing agent is the judge, at commit. No separate LLM judge ([[Judge]] is optional automation now); precision is overhead, not a kill criterion; recall, per-commit overhead and coverage are what matter.
- **M3 and M5 are done and proven** (2026-09-23): `livedocs affected | coverage | install-hooks`; the read gate, Stop heads-up and bypass log hooks; the pre-commit gate with mechanical auto-ack for provably benign changes. See the session log for the proof.
- **Pending:** the user's calibration pass, `results/1a-run1/user-calibration.md` (7 misses + 25 random flags).
- **D14 (2026-09-23):** the guarantee is a mechanism of the development framework, not the agent: versioned git gate + CI always; Stop heads-up recommended; read gate opt-in; bypass log measurement-only. `livedocs init` sets this up.
- **D15:** "aligned" = stamped against the current code (`update` or `ack --reason`); the gate as built implements it.
- **Constant anchors (P24) done.** A constant binds its file with drift and carries its own member hash; `shapes.md` flags on a value change and stays benign on unrelated edits.
- **Live hook test done:** in headless Claude Code sessions the read gate, Stop heads-up and bypass log all reached (or bypassed) the model as designed; **subagents are covered** by the read gate.
- **Phase 1b run 1 done** — [[1b Run 1]]: six Opus sessions made real changes against the gate; every update and ack was correct and specific, no gaming; two mechanism bugs found and fixed. Overhead is set by how many notes mention a symbol; dated review notes dominate the acks (P25).
- **Next:** P25 (snapshot notes), then packaging (`uv tool install`) and a CI job.

*Update this section at the end of every session.*

## Reading order for a fresh agent

**Short path** (enough to act on): this note, then [[Live Docs Design#1. Summary]], then [[Live Docs Design#8. Plan]], then the "Accepted" table in [[Decision Log]].

**Full path:**
1. This note.
2. [[Vault Conventions]]: how to read and write here.
3. [[Live Docs Design]]: the current proposal (v0.3).
4. [[Decision Log]]: accepted and proposed decisions.
5. [[2026-09-21 Design Review]]: why v0.2 differs from v0.1.
6. The latest session log: [[2026-09-23 Runs 1 and 2]].
7. Research notes, as needed (listed below).

Quick triage without opening every note: `grep -rh --include='*.md' '^summary:' live-docs-vault/`

## Map

- **Design:**
  - [[Live Docs Design]] (v0.3): summary, components, freshness states, what the agent sees, the Phase 1 experiment, open questions, and the deferred backlog.
  - [[Implementation Plan]] (v0.2): the Phase 1 code — package layout, verified drift facts, components, the 1a replay harness, milestones.
  - [[Judge]] (draft): step C — an LLM judge between the hash and the agent, its placement, stamps, prompt, cost and evaluation.
- **Results:**
  - [[1a Run 1]]: the first replay run on hpc-bridge — numbers, causes, and the options they leave open.
  - [[1a Run 2]]: the same history with the D fixes — what improved, and the precision/recall trade-off that shapes the judge.
  - [[1b Run 1]]: six agent sessions reconciling notes at the commit gate — honest, substantive, two bugs found.
- **Reviews:**
  - [[2026-09-21 Design Review]]: three critics, two rounds, and what changed as a result.
  - [[2026-09-22 Implementation Plan Review]]: eleven issues against plan v0.1, most verified on the testbench.
- **Research** (authority `reference`; re-check anything older than a few months):
  - [[Evidence - Agents and Stale Context]]: why the problem matters, and the corrected Meetless reading.
  - [[Prior Art - Code-Coupled Documentation]]: Fiberplane drift, Swimm, detection research, fingerprinting.
  - [[Prior Art - Agent Memory Systems]]: how agent memory handles staleness today.
  - [[Obsidian Platform Constraints]]: what Obsidian can and can't do here.
- **Decisions:** [[Decision Log]]
- **Sessions** (newest first):
  - [[2026-09-23 Runs 1 and 2]]
  - [[2026-09-22 Resolving the Review]]
  - [[2026-09-21 Research and Design]]
- **Templates:** `Templates/` holds [[Session Log]], [[Research Note]] and [[Decision]].

## Key terms

*Vault*, *anchor*, *fingerprint*, *stamp*, *diff base*, *authority* and *freshness* are defined in [[Live Docs Design#4. Concepts]].
