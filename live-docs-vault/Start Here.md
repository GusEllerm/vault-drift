---
type: index
status: active
authority: describes
summary: "Entry point to this vault: what the project is, where it stands, and what to read first."
created: 2026-09-21
updated: 2026-10-23
reviewed: 2026-10-23
tags: [live-docs, index]
---

# Start Here

## What this project is

**live-docs** explores using an Obsidian vault as agent-first *live documentation* for software that agents build. Notes that describe code are bound to fingerprints (hashes) of the code they mention. When an agent reads a note whose code has changed, it gets the current facts instead of acting on out-of-date docs.

This vault is also the long-term, cross-session memory for the live-docs project itself. Agents working on the project read and write it across sessions.

## Current status

*As of 2026-10-23 (evening).*

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
- **P25 done (snapshot notes):** dated records bind nothing; on hpc-bridge that removed 44% of bindings and took a rename task from 4 hand acks to 0.
- **Packaging done** (2026-09-23): README, `livedocs verify` for CI, GitHub workflows, pre-commit-framework hook, 0.1.0. Installable with `uv tool install git+https://github.com/GusEllerm/vault-drift`.
- **MIT licence added.** Notes are now stamped by the commit that adds or edits them; `--repo`/`--vault` default sensibly. The whole flow is verified on a fresh empty-vault repo (session log).
- **`livedocs new-vault`** scaffolds an Obsidian vault and wires everything in with one command.
- **On PyPI (2026-09-24):** `uv tool install livedocs`. Future releases: bump the version, tag `v*`, push — after the user adds the trusted publisher on PyPI. The repo stays private. See [[2026-09-24 PyPI Release]].
- **0.1.2 and 0.1.3 (2026-09-28), both from adopters' reports:** Python code is discovered wherever it lives, not only under `src/` (`code_roots` in config pins it); stamp format v2 tags fingerprints and stores members as pairs so secret scanners don't misread stamps, and `init`/`new-vault` write `.gitguardian.yaml`. See [[2026-09-28 Code Discovery and Stamp Format v2]].
- **Hook PATH fix (2026-09-29, released in 0.1.4):** Stop hooks looped in sessions without `livedocs` on PATH. The commands now fall back to the init-time launcher and `~/.local/bin`, and the Stop fallback is a user-facing `systemMessage`. See [[2026-09-29 Hook PATH Fix]]. Existing repos need `livedocs init` re-run after release.
- **Vault housekeeping (2026-10-23):** session logs split one per session; D16 (MIT) and D17 (PyPI, private repo) recorded; P8–P25 checked against the code in [[Decision Log#Where the proposals stand (agent summary, 2026-10-23)]]; the design note's banner names the decisions that override v0.3. See [[2026-10-23 Vault Gaps]].
- **TypeScript support, 0.2.0 (2026-10-23):** TS/TSX/JS, Astro and JSON config keys, for the user's Astro website ([[TypeScript Support]], measured in [[TS Run 1]]). On gravity-works the gate asked for 362 hand reconciliations where 0.1.4 asked for 931 (600-line path rule, D18); recall was graded on a 215-item sample. Python resolution is unchanged on hpc-bridge. Seven bugs fixed on the way, three of them already in 0.1.4: the first commit of a new repository was blocked; an image bound by a note crashed the gate; Python member hashes depended on the CPython minor version. Released as 0.2.0 (D19); the global tool now installs from PyPI (D20). See [[2026-10-23 TypeScript Support]].
- **Open for the user:** the run-1 calibration pass (`results/1a-run1/user-calibration.md`); accepting or rejecting P8–P28 and P30–P32; whether gravity-works and scheduler-dojo run `livedocs rebind` (their TS notes bind whole files until then). (PyPI trusted publishing works: 0.1.1–0.1.4 shipped through it.)
- **Note for agents:** develop livedocs in this checkout or a worktree; since D20 the user's global tool is the PyPI release, so neither reaches other projects' gates.
- **Candidate next steps:** report the TS gaps upstream to drift (JSX in `.tsx`, `.mjs` and friends, comment-sensitive fingerprints); replay an Astro history once the website has one; note-hygiene guidance (widely mentioned symbols cost per mention); a testbench written by someone else (all three so far were built by the user's agents); report drift's two gaps upstream (percent-encoded links; file fingerprints blind to lines inside module-level strings).

*Update this section at the end of every session.*

## Reading order for a fresh agent

**Short path** (enough to act on): this note, then [[Live Docs Design#1. Summary]], then [[Live Docs Design#8. Plan]], then the "Accepted" table in [[Decision Log]].

**Full path:**
1. This note.
2. [[Vault Conventions]]: how to read and write here.
3. [[Live Docs Design]]: the current proposal (v0.3).
4. [[Decision Log]]: accepted and proposed decisions.
5. [[2026-09-21 Design Review]]: why v0.2 differs from v0.1.
6. The latest session logs (newest first in the Map below). [[2026-09-23 Runs 1 and 2]] holds most of Phase 1.
7. Research notes, as needed (listed below).

Quick triage without opening every note: `grep -rh --include='*.md' '^summary:' live-docs-vault/`

## Map

- **Design:**
  - [[Live Docs Design]] (v0.3): summary, components, freshness states, what the agent sees, the Phase 1 experiment, open questions, and the deferred backlog.
  - [[Implementation Plan]] (v0.2): the Phase 1 code — package layout, verified drift facts, components, the 1a replay harness, milestones.
  - [[Judge]] (draft): step C — an LLM judge between the hash and the agent, its placement, stamps, prompt, cost and evaluation.
  - [[TypeScript Support]] (draft v0.1): TS/JS/Astro/JSON parsing, binding rules, member hashes, hash schemes (P26–P32).
- **Results:**
  - [[1a Run 1]]: the first replay run on hpc-bridge — numbers, causes, and the options they leave open.
  - [[1a Run 2]]: the same history with the D fixes — what improved, and the precision/recall trade-off that shapes the judge.
  - [[1b Run 1]]: six agent sessions reconciling notes at the commit gate — honest, substantive, two bugs found.
  - [[TS Run 1]]: TypeScript on gravity-works and scheduler-dojo — gate overhead 0.1.4 vs 0.2.0, graded recall, the path-rule threshold curve.
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
  - [[2026-10-23 TypeScript Support]]
  - [[2026-10-23 Vault Gaps]]
  - [[2026-09-29 Hook PATH Fix]]
  - [[2026-09-28 Code Discovery and Stamp Format v2]]
  - [[2026-09-24 PyPI Release]]
  - [[2026-09-23 Runs 1 and 2]]
  - [[2026-09-22 Resolving the Review]]
  - [[2026-09-21 Research and Design]]
- **Templates:** `Templates/` holds [[Session Log]], [[Research Note]] and [[Decision]].

## Key terms

*Vault*, *anchor*, *fingerprint*, *stamp*, *diff base*, *authority* and *freshness* are defined in [[Live Docs Design#4. Concepts]].
