---
type: research
status: active
authority: reference
summary: "How agent memory systems handle stale memory as of 2026-09: coding-tool memory, memory frameworks, code-wiki generators, and small projects that anchor memory to code."
created: 2026-09-21
updated: 2026-09-21
reviewed: 2026-09-21
tags: [live-docs, research, prior-art]
---

# Prior Art - Agent Memory Systems

> **Provenance.** Research subagents gathered this by web search on 2026-09-21. It hasn't been independently re-checked; items marked *unverified* couldn't be confirmed. Star counts are from 2026-09-21.

## Takeaway

- **Mainstream coding-agent memory has no mechanism for staleness.** It relies on instructions ("verify before use") or on humans pruning by hand.
- **GitHub Copilot Memory** is the only large product that validates memories against code before using them, and it does so by model judgment, not hashes.
- **Several small projects hash code anchors.** Fiberplane drift is the most mature (see [[Prior Art - Code-Coupled Documentation]]). None of them works in Obsidian.

## Memory in coding tools

- **Claude Code** (CLAUDE.md and auto-memory):
  - Auto-memory lives in `~/.claude/projects/<proj>/memory/`, and only the first 200 lines or 25KB are loaded.
  - There's no invalidation. The harness asks the agent to "merge or drop stale entries" when the file nears its limit, the docs tell users to prune by hand, and the agent is told to verify remembered files and functions before recommending them.
  - https://code.claude.com/docs/en/memory
- **AGENTS.md:** the nearest file wins, plus the advice to treat it as "living documentation". No check. https://agents.md/
- **Cursor:** Memories seem to have been removed in 2.1 (Nov 2025); users report it, but staff haven't fully confirmed (*unverified*). Rules have no staleness check.
- **Windsurf** (its docs now redirect to Devin Desktop): auto-memories are kept per workspace with no expiry or verification. Users are told to review them and promote durable facts into rules. https://docs.devin.ai/desktop/cascade/memories
- **Kiro:** steering docs are refined by hand. The one automated route is an agent hook that rewrites docs when a file is saved. https://kiro.dev/docs/steering/
- **GitHub Copilot Memory (the closest production analogue):**
  - Each memory is stored with citations to code locations.
  - Before a memory is used, Copilot checks its citations against the current branch and only uses the memory if they validate.
  - Memories are deleted after 28 days unused; the timer resets whenever a memory is validated and used.
  - The check is the model's judgment, not a hash.
  - Sources:
    - https://docs.github.com/en/copilot/concepts/agents/copilot-memory
    - https://github.blog/ai-and-ml/github-copilot/building-an-agentic-memory-system-for-github-copilot/
- **Cline Memory Bank:** purely a prompt convention. The agent reads every memory file at the start of each task and updates them on request or after significant changes. https://docs.cline.bot/best-practices/memory-bank

## Memory frameworks

- **Zep / Graphiti:**
  - Every edge has two timelines: when the fact was true (`t_valid`/`t_invalid`) and when the system recorded or retired it (`t'_created`/`t'_expired`).
  - An LLM compares each new edge with related existing ones. When they contradict and their validity periods overlap, the old edge's `t_invalid` is set to the new edge's `t_valid`. Nothing is deleted.
  - This handles contradictions between statements, not drift against code.
  - https://arxiv.org/html/2501.13956v1
- **mem0:**
  - The 2025 algorithm had an LLM choose ADD, UPDATE, DELETE or NOOP.
  - The current algorithm only adds, keeps time metadata, and ranks current facts higher at retrieval.
  - Issue #5867 reports that it ends up storing contradictory memories.
  - https://docs.mem0.ai/migration/platform-v2-to-v3
- **Letta:**
  - Memory blocks, plus background "sleep-time" agents that rewrite memory.
  - "Context Repositories" (Feb 2026) are git-versioned markdown.
  - Nothing checks memory against code.
  - https://www.letta.com/blog/context-repositories/
- **Basic Memory:** writes markdown that Obsidian can open and keeps a SQLite index. Its checksums keep the index in sync with the notes, not the notes with the code. https://github.com/basicmachines-co/basic-memory

## Code-wiki generators

- **Google Code Wiki (Nov 2025):** "regenerates the documentation after each change". The exact trigger isn't stated. https://developers.googleblog.com/en/introducing-code-wiki-accelerating-your-code-understanding/
- **DeepWiki / Devin:** regenerates on a schedule or on demand, and a 2025 tweet says badged repos refresh weekly (*unverified*).
- **Augment:** a real-time index per developer. Nothing is written down, so nothing goes stale.
- **Sourcegraph Cody:** looks up code at query time, so it's only as fresh as its index.
- **Relevance:** these tools avoid staleness by regenerating everything or storing nothing. Neither approach keeps judgments that agents wrote themselves, which is exactly what the vault is for.

## Projects that anchor memory to code

All of these are small and experimental, with no sign of adoption beyond their stars.
- **Kage** (GPL-3.0, 33 stars):
  - Markdown memory files with YAML frontmatter in `.agent_memory/`, committed with the code.
  - Citations are checked when a memory is written, when it's recalled (stale memories are withheld) and on diffs (`kage pr check`).
  - What counts as "changed" is unclear.
  - https://github.com/kage-core/Kage
- **ctx-memory** (MIT, 0 stars):
  - Notes in `.memory/entries/`, with frontmatter holding `commit`, `fingerprint`, `refs` (`file#symbol`) and `last_checked`.
  - No AI. Checks sort each note into missing, STALE, low or ok.
  - https://github.com/kishore600/ctx-memory
- **true-memory-fragments:** checks file blob hashes and per-function hashes on every retrieval, and returns a "reread" signal on a mismatch. https://github.com/kyle641320/true-memory-fragments
- **OMP:** per-function and per-file hashes, checked on retrieval; a mismatch marks the note stale and triggers a re-parse. https://github.com/open-mem/omp
- **Mnemex:** decisions tracked against a hash of the symbol's content (fresh, stale or orphaned), stored in SQLite. https://glama.ai/mcp/servers/notsointresting/mnemex
- **anchored-memory:** anchors to files or symbols, checked on recall. https://github.com/HT0710/anchored-memory
- **stalebrain:** audits prose claims in CLAUDE.md-style files, with a decay period per claim type and `<!-- verified date -->` stamps. https://github.com/stalebrainlabs/stalebrain
- **doc-lattice:** `derives_from: [{ref, seen: <hash>}]`, but only between markdown documents. It's relevant to note-to-note anchors ([[Live Docs Design#6.12 Beyond code]]). https://github.com/Guardantix/doc-lattice
