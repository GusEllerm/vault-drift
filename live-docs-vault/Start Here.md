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
- **The first 1a run is graded** — [[1a Run 1]]. Recall passes (4.3% misses); flag precision fails (2.7%; 26% at note level). The hash is a high-recall trigger, not a staleness verdict. **The user has to decide** between stopping, redefining the state, adding an LLM judge, or fixing the tooling noise and re-running (options A–D in the results note).
- **Pending:** the user's calibration pass, `results/1a-run1/user-calibration.md` (7 misses + 25 random flags).
- **Next:** the user's decision on 1a; then either M3/M5 (hooks, pre-commit) or the noise fixes and run 2.

*Update this section at the end of every session.*

## Reading order for a fresh agent

**Short path** (enough to act on): this note, then [[Live Docs Design#1. Summary]], then [[Live Docs Design#8. Plan]], then the "Accepted" table in [[Decision Log]].

**Full path:**
1. This note.
2. [[Vault Conventions]]: how to read and write here.
3. [[Live Docs Design]]: the current proposal (v0.3).
4. [[Decision Log]]: accepted and proposed decisions.
5. [[2026-09-21 Design Review]]: why v0.2 differs from v0.1.
6. The latest session log: [[2026-09-22 Resolving the Review]].
7. Research notes, as needed (listed below).

Quick triage without opening every note: `grep -rh --include='*.md' '^summary:' live-docs-vault/`

## Map

- **Design:**
  - [[Live Docs Design]] (v0.3): summary, components, freshness states, what the agent sees, the Phase 1 experiment, open questions, and the deferred backlog.
  - [[Implementation Plan]] (v0.2): the Phase 1 code — package layout, verified drift facts, components, the 1a replay harness, milestones.
- **Results:**
  - [[1a Run 1]]: the first replay run on hpc-bridge — numbers, causes, and the options they leave open.
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
  - [[2026-09-22 Resolving the Review]]
  - [[2026-09-21 Research and Design]]
- **Templates:** `Templates/` holds [[Session Log]], [[Research Note]] and [[Decision]].

## Key terms

*Vault*, *anchor*, *fingerprint*, *stamp*, *diff base*, *authority* and *freshness* are defined in [[Live Docs Design#4. Concepts]].
