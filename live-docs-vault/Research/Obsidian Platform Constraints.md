---
type: research
status: active
authority: reference
summary: "What Obsidian can and can't do for an agent-first vault: properties, Bases, CLI, plugins, MCP servers, code-linking plugins, git and concurrency."
created: 2026-09-21
updated: 2026-09-21
reviewed: 2026-09-21
tags: [live-docs, research, obsidian]
---

# Obsidian Platform Constraints

> **Provenance.** Research subagents gathered this by web search on 2026-09-21. It hasn't been independently re-checked; items marked *unverified* couldn't be confirmed.

## Constraints that shape the design

1. **Plugins only run inside the open app.** Agents write files directly to disk, bypassing every plugin. **Any check that must always happen belongs in an external CLI, hook or CI job.**
2. **Nested frontmatter isn't supported in the UI,** and Obsidian rewrites the whole frontmatter block whenever it writes a property. Keep frontmatter flat and put machine data elsewhere.
3. **Bases can't compute hashes.** Staleness has to be computed outside Obsidian and written back as a flat property or a generated note.

## Properties (frontmatter)

- Supported types: Text, List, Number, Checkbox, Date and Date & time; `tags` is special. Nested properties aren't supported in the UI ("use source mode"). Markdown inside properties isn't allowed. https://obsidian.md/help/properties
- `deps: [{path, hash}]` stays in the file as raw YAML, and the Properties panel shows it as an "unsupported type" blob. Community plugins (Nested Properties, Nested Frontmatter Properties) can display and edit it.
- **The catch:** when Obsidian writes frontmatter (through the Properties UI, Bases, or any plugin using `processFrontMatter`), it re-serializes the whole block. Comments are dropped and quoting and formatting change, and the developers consider this intended. https://forum.obsidian.md/t/yaml-properties-api-processfrontmatter-removes-alters-string-quotes-comments-types-formatting/65851
- Quote hashes: unquoted hex like `1234e5` parses as a number.

## Bases and Dataview

- **Bases** can filter on `note.<prop>` and `file.mtime`, and has list functions (`filter`, `map`, `reduce`, `contains`) and object functions (`keys`, `values`). https://obsidian.md/help/bases/syntax
- Hand-written Bases formulas can reach nested properties, though the UI neither lists them nor autocompletes them. The only source is one forum post from August 2026 (*unverified*).
- **Dataview** reads nested YAML fully (`deps.hash` returns a list), but it has been in maintenance mode since v0.5.9 (April 2025). Its successor, Datacore, is at v0.1.9.

## Official CLI and other ways in

- **Official Obsidian CLI:**
  - Shipped with 1.12 and became generally available in 1.12.4 (2026-02-27). **It needs the app running**; the first command launches it.
  - Commands include file operations, `search`, `links`, `unresolved`, `property:set/read/remove`, `base:query` (JSON/CSV) and `eval`.
  - `property:set` can't set nested objects.
  - https://obsidian.md/help/cli
- **Obsidian Headless (`ob`, open beta):** runs without the app, but only handles Sync and Publish.
- **Local REST API plugin:**
  - HTTPS on 127.0.0.1:27124, with a built-in MCP endpoint at `/mcp/`.
  - PATCH can target a heading, a block or a frontmatter key.
  - Needs the app running.
  - https://github.com/coddingtonbear/obsidian-local-rest-api

## MCP servers and agent skills

- **Through the Local REST API** (so they need the app): MarkusPfundstein/mcp-obsidian, cyanheads/obsidian-mcp-server.
- **Reading files directly** (no app needed): Bert-Proesmans/obsidian-mcp, seekstone, bitbonsai/mcpvault.
- **Basic Memory:** markdown that Obsidian can open, backed by its own SQLite index. See [[Prior Art - Agent Memory Systems]].
- **kepano/obsidian-skills:** official agent skills from Obsidian's CEO (obsidian-markdown, obsidian-bases, obsidian-cli, json-canvas). https://github.com/kepano/obsidian-skills
- **None of these handles staleness or links notes to code.**

## Plugins that link notes to code

- **Code Linker (max-fluff):**
  - Links point at a symbol's declaration line and can be "pinned".
  - A pin goes stale when that line no longer declares the symbol.
  - Has batch fix commands, and only works while the app is open.
  - https://github.com/max-fluff/obsidian-code-linker
- **Import Code, Embed Code File and Code File Embed:** embed code by line range or symbol, with no drift checking.
- **obsidian-git:** version control only.

## Git, multiple vaults and concurrent writes

- **Don't nest vaults;** links may not update correctly. Each vault has its own `.obsidian/`. Keep `workspace.json` out of git. https://obsidian.md/help/data-storage
- **obsidian-git with the vault in a repo subfolder** lists, stages and commits files from the whole repo. This is issue #1172, still open as of 2026-09-05 (v2.39.0). A "Custom base path" setting exists. https://github.com/Vinzent03/obsidian-git/issues/1172
- **External edits:** Obsidian picks up changes made outside the app. If a note is open while something else edits it, the app shows "modified externally, merging changes automatically".
- **No file locking:** the last write to disk wins. Obsidian Sync merges markdown with diff-match-patch, and since 1.9.7 can create conflict files instead.
- **Several agents writing at once** needs our own conventions, git branches with merges, or append-only notes. Obsidian won't referee.
