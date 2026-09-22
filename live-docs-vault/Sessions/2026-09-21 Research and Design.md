---
type: session
status: active
authority: log
summary: "First session: researched prior art, wrote design v0.1, set up the vault and git repo, then ran a three-critic review that produced design v0.2."
created: 2026-09-21
updated: 2026-09-21
reviewed: 2026-09-21
tags: [live-docs, session]
---

# 2026-09-21 Research and Design

## Goal

The user asked for research on, and thoughts about, the live-docs idea. They then asked for a design doc written into this vault, which is to serve as the project's long-term memory and be navigable by a fresh agent.

## What was done

- **Research:** three parallel web-research threads, run by subagents:
  - prior art on docs coupled to code;
  - Obsidian as a platform for agents;
  - how agent memory systems handle staleness.
  
  The findings are condensed in the `Research/` notes.
- **Spot-checks:**
  - Fiberplane drift's README, which confirmed its mechanism.
  - The Claude Code hooks docs (via Context7), which confirmed that `PostToolUse` supports `additionalContext` and `updatedToolOutput`, making a read-time gate on `Read` feasible.
- **Wrote** [[Live Docs Design]], [[Vault Conventions]], [[Decision Log]], [[Start Here]] and three templates.
- **Housekeeping:**
  - Replaced Obsidian's default `Welcome.md` with [[Start Here]].
  - Pointed the Templates core plugin at `Templates/`.
  - Added a `CLAUDE.md` at the project root pointing agents to this vault.

## Key findings

- **The core mechanism already exists.** Fiberplane drift (MIT license, March 2026) fingerprints `path#Symbol` anchors with tree-sitter into a lock file and checks them in CI.
- **What's left open:**
  - a read-time gate;
  - authority, i.e. which side wins a mismatch;
  - a graded policy for out-of-sync notes and a way to fix them;
  - Obsidian conventions.
- **The evidence supports a mechanical check.** Agents trust confident stale context (STALE, 2026: 55% at best), and 28.9% of top GitHub projects have outdated code references.
- **Obsidian's constraints push the checking outside Obsidian.** Plugins only run in the open app, and nested frontmatter doesn't display and gets rewritten.

## Decisions

- **User:** D1 (the core concept) and D2 (this vault is the project's memory). See [[Decision Log]].
- **Agent proposals P1–P9:** all awaiting the user's review.

## Open threads / next steps

- The user reviews [[Live Docs Design]] and answers the open questions in §9.
- Done at the user's request: `git init -b main` at the project root. `.gitignore` excludes per-machine Obsidian state (`workspace.json`, `workspace-mobile.json`, `.trash/`) and local Claude Code state; the shared `.obsidian/` config is versioned (D3).
- The Phase 1 spike (design §8).

## Design review (later the same session)

- At the user's request, three critic subagents reviewed design v0.1 over two rounds:
  - a skeptical pragmatist;
  - a systems engineer;
  - an agent's advocate.
- **Output:** [[2026-09-21 Design Review]], and the design revised to **v0.2**.
- **Biggest changes:**
  - **Phase 1 now tests value first.** Arms: no notes; notes plus a CLAUDE.md rule; notes plus the gate. It has kill criteria written down in advance.
  - **The read-time output now delivers was / now code facts,** not a "code wins" banner. v0.1 had misread the Meetless evidence; the orchestrating agent re-checked the source and corrected [[Evidence - Agents and Stale Context]].
  - **Freshness is down to four states and fails closed.** Checks are read-only, and stamps include the note hash.
  - **Most hardening is deferred** (design §11).
- **Four points are contested** and need the user (C1–C4 in [[Decision Log]]):
  - `specifies` notes;
  - the size of Phase 1;
  - Obsidian's role;
  - the continue threshold.
- **Vault changes:** added a `Reviews/` folder, a `review` type, and the rule that a `specifies` note only binds when it's active or accepted.

## Notes for the next agent

- The research notes rest on subagent web searches. Only the drift README and the Claude Code hooks docs were checked directly. Items marked *unverified* weren't confirmed, and star counts and versions will drift.
- Claude Code's per-user auto-memory for this project holds only a pointer to this vault. Durable project knowledge belongs here.
