---
type: conventions
status: active
authority: specifies
summary: "Rules for reading and writing this vault: folder layout, frontmatter schema, writing rules, and what to do at the end of a session."
created: 2026-09-21
updated: 2026-09-21
reviewed: 2026-09-21
tags: [live-docs, conventions]
---

# Vault Conventions

These rules are for any agent or human writing to this vault. The vault follows the conventions in [[Live Docs Design]], so the project uses its own ideas.

## Folder layout

| Path | Holds |
|---|---|
| `Start Here.md` | Entry point, current status and reading order |
| `Vault Conventions.md` | This note |
| `Decision Log.md` | Decisions, with who made them and whether they're accepted or only proposed |
| `Design/` | Design docs |
| `Research/` | Findings about the outside world: tools, papers, platforms |
| `Reviews/` | Critiques of designs and plans, named `YYYY-MM-DD Topic.md` |
| `Results/` | Experiment results, one note per run; the raw artefacts live in the repo's `results/` |
| `Sessions/` | One log per working session, named `YYYY-MM-DD Topic.md` |
| `Templates/` | Note templates (the Templates core plugin points here) |
| `Archive/` | Retired or superseded notes (create it when first needed) |

## Frontmatter

Every note except templates starts with this block:

```yaml
---
type: index | conventions | design | research | review | results | decision-log | decision | session
status: draft | active | superseded | retired      # decision notes: proposed | accepted | rejected | superseded
authority: describes | specifies | log | reference
summary: "One sentence: enough for an agent to decide whether to open the note."
created: YYYY-MM-DD
updated: YYYY-MM-DD
reviewed: YYYY-MM-DD
tags: [live-docs]
---
```

- **`authority`** says what to do when the note and reality disagree. This is a convention for agents working in *this* vault; as of design v0.3 the Live Docs mechanism itself doesn't read it ([[Live Docs Design#6.2 What gets checked]]).
  - `describes`: reality wins, so update the note.
  - `specifies`: the note wins, so check whatever it governs. **It only binds when `status` is `active` or `accepted`.** A `draft` or `proposed` note is a proposal, not a rule.
  - `log`: historical; never update it after the session ends.
  - `reference`: facts about the outside world; re-check them once they're old.
- **`summary`** is for triage. Agents can scan summaries with grep instead of opening every note, so keep it accurate when the content changes.
- **`updated` and `reviewed` mean different things.** `updated` is when the content last changed. `reviewed` is when someone last confirmed the content is still accurate.
- **Keep frontmatter flat,** with no nested objects. Obsidian can't display them and rewrites the block when properties are edited. Quote strings that could look like numbers or hashes.
- **Code anchors come later.** Once the project has code, notes that describe it add `depends_on` anchors as in [[Live Docs Design#6.3 Declaring dependencies]]. Until the checker exists, list the anchors anyway so they can be stamped later.

## Writing rules

- **Use absolute dates** (2026-09-21), never "yesterday" or "last week".
- **Link with wikilinks,** `[[Note Name]]`, and link generously. A link to a note that doesn't exist yet is fine; it marks something worth writing.
- **Keep what the user decided separate from what an agent proposed.** Record decisions in [[Decision Log]] with who made them. Never present a proposal as agreed.
- **Cite URLs for external facts.** Mark claims you didn't check yourself as *unverified*, and say in a provenance line at the top of the note how its content was gathered.
- **Update an existing note rather than creating a near-duplicate.** When a note is replaced, set `status: superseded` and link to the replacement.
- **Leave `.obsidian/` alone** unless you mean to change it; it's the human's app configuration.

## Session protocol

- **At the start:** read [[Start Here]] and follow its reading order. Read the latest session log before starting work.
- **At the end, if anything changed:**
  1. Add `Sessions/YYYY-MM-DD Topic.md` from the [[Session Log]] template.
  2. Update [[Start Here#Current status]], including its "as of" date.
  3. Add a row to [[Decision Log]] for any decision made.
  4. Add the new session to the map in [[Start Here]].
