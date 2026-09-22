---
type: research
status: active
authority: reference
summary: "Existing tools and research for binding docs to code and detecting drift: Fiberplane drift, Swimm, time-based freshness, detection research, content addressing."
created: 2026-09-21
updated: 2026-09-21
reviewed: 2026-09-21
tags: [live-docs, research, prior-art]
---

# Prior Art - Code-Coupled Documentation

> **Provenance.** Research subagents gathered this by web search on 2026-09-21. **The Fiberplane drift section was verified directly against its README the same day.** Other items are as reported; anything marked *unverified* couldn't be confirmed. Star counts and versions change, so re-check them before relying on them.

## Fiberplane drift: the closest match (verified)

- Repo: https://github.com/fiberplane/drift. Blog: https://fiberplane.com/blog/drift-documentation-linter/ (MIT license, March 2026)
- **Declaring links:** either inline in the doc body (`@./src/auth/provider.ts#AuthConfig`) or with `drift link docs/auth.md src/auth/login.ts`. Anchors can point at a symbol (`path#Symbol`).
- **Storage:** `drift.lock` (TOML) at the repo root, one `[[bindings]]` entry per link, each with `doc`, `target` and `sig`.
- **What gets hashed:** for TypeScript, Python, Rust, Go, Zig and Java, a tree-sitter syntax tree normalized to "node kinds + token text, no whitespace or position data". Symbol anchors hash only that declaration's subtree. Other languages fall back to comparing raw content. It hashes what's on disk, so uncommitted files work.
- **Git:** SHAs aren't stored in anchors. History is optional and only used for blame information in CI output.
- **Commands:**
  - `drift check` (exits 1 if anything is stale; alias `drift lint`)
  - `drift link` / `drift unlink`
  - `drift status`
  - `drift refs`, which does the reverse lookup: which docs reference a given file.
- **Agent integration:** a skill for Claude Code and Codex that teaches the agent to run `drift link` as it changes code. No MCP server and no Obsidian wikilink support.
- **Compared with our design:** it checks in CI rather than at read time, has no sig/impl split, doesn't store the commit so can't say what changed, and has no notion of authority. See [[Live Docs Design#7. Build vs. adopt]].

## Swimm Auto-sync (commercial)

- **Storage:** no hashes. Each reference embeds a copy of the code:
  - Snippets: `<SwmSnippet path=… line=…>` plus the copied code.
  - Tokens: `<SwmToken path=… pos="line:startToken:endToken" line-data="<whole source line>">`.
  - Paths: `SwmPath`.
- **Detection:** needs the full git history. It combines line markers, line numbers, token references, how big the change was and the file's history.
- **Outcomes:**
  - Unchanged, only moved, or renamed without functional impact: fixed silently.
  - A bigger change: marked outdated, or "needs review".
  - In CI: the check fails, and either blocks the PR or opens an issue with a deadline.
- **Status in 2026:** Swimm's homepage now pitches "agentic modernization" (legacy and mainframe work). The Auto-sync docs pages are still up. *Unverified* whether the feature is still actively developed.
- **Lesson:** to auto-fix trivial changes you need more than a hash. You need the anchor text or a normalized copy of the source, plus the commit last verified against.
- Sources:
  - https://swimm.io/blog/how-does-swimm-s-auto-sync-feature-work
  - https://docs.swimm.io/features/keep-docs-updated-with-auto-sync/

## Time-based freshness

- **Google g3doc** (*Software Engineering at Google*, chapter 10):
  - Docs carry `<!--* freshness: { owner: 'username' reviewed: '2019-02-27' } *-->`.
  - Owners get reminder emails after about three months without changes.
  - Bumping the review date goes through code review.
  - A "Last reviewed by…" byline helped adoption.
  - https://abseil.io/resources/swe-book/html/ch10.html
- **Notion verified pages:** a page stays verified until an expiry date, after which the owner is reminded. https://www.notion.com/help/wikis-and-verified-pages
- **Backstage TechDocs:** no built-in freshness check. The Tech Insights fact retriever only checks that TechDocs is configured.
- **Lesson:** keep `reviewed` (and possibly `owner`) next to the hash. The hash catches code changes; the date catches drift you can't hash, such as intent or architecture. Adopted as the `overdue` state in [[Live Docs Design#6.5 Freshness states]].

## Detecting drift: research methods

- **Tan et al. (2023):** regexes plus backtick spans pull code-element names out of READMEs and wikis. A reference counts as outdated if the element existed when the doc was last updated and every instance has since been deleted. The follow-up **DOCER** GitHub Action comments on PRs. Numbers in [[Evidence - Agents and Stale Context]]. https://arxiv.org/abs/2212.01479
- **DocPrism (ISSTA 2026):** asking an LLM directly flags more than 90% of functions as inconsistent. Categorizing first and then filtering cut the flag rate from 98% to 14%, and raised F1 from 0.22 to 0.77. https://arxiv.org/abs/2511.00215
- **READU (Baek, Krampf & Pradel, July 2026):**
  - Runs per commit: a commit filter tuned to miss little, then consistency checkers, then an LLM "alert judge", then patch generation.
  - On 6,000 commits: 244 true positives at 75% precision, 217 correct repairs, under $0.01 and under a minute per commit.
  - https://arxiv.org/abs/2607.15780
- **CASCADE (Apr 2026):** generates tests from the docs, and reports a mismatch only when the real code fails a test that code generated from the docs passes. https://arxiv.org/abs/2604.19400
- **Nguyen et al. (SANER 2026):** a small model reading structured diffs beats fine-tuned LLMs by 4–11% F1. https://arxiv.org/abs/2512.19883
- **HebCup (ICPC 2021):** simple token-replacement rules matched the deep-learning comment updater CUP, 96.6% of whose successes were single-token changes.
- **Lesson:** use the hash as a cheap first filter that misses little, and only then an LLM judge on what it flags. Never ask an LLM "is this stale?" about every note. See [[Live Docs Design#6.8 Reconciliation]].

## Tools that auto-update docs (2024–2026)

- **Mintlify agent / Autopilot (Dec 2025):** runs on a schedule or on push, reads the diff and drafts a docs PR. https://www.mintlify.com/blog/autopilot
- **Promptless:** triggered by PRs, Slack or tickets; opens a docs PR with citations. https://promptless.ai/docs/getting-started/welcome/
- **Dosu recipe (Mar 2026):** a do-it-yourself setup using `claude-code-action`, with a CLAUDE.md table mapping code paths to doc pages. On merge it opens a follow-up PR. https://dosu.dev/blog/how-to-catch-documentation-drift-claude-code-github-actions
- **DeepWiki / Devin Wiki:** "We auto-refresh DeepWikis if their repo has a badge", and `.devin/wiki.json` steers which pages get generated. The refresh cadence is *unverified*. https://docs.devin.ai/work-with-devin/deepwiki
- **pallaprolus/drift** (a different project, 2 stars): checks function signatures against doc comments and stores "a hash of the code it was reviewed against" in `.drift/state.json`. https://github.com/pallaprolus/drift
- **SimonCropp/MarkdownSnippets:** copies code between `begin-snippet`/`end-snippet` markers into docs, so embedded code can't drift. https://github.com/SimonCropp/MarkdownSnippets
- **Pattern:** the commercial tools start from diffs and link code to docs implicitly through an LLM. Explicitly declared dependencies with stored fingerprints are rare.

## Content addressing and early cutoff

- **Git objects:** a blob id is sha1("blob <size>\0" + content), available for free via `git hash-object` or `git rev-parse HEAD:path`. It works per file, so it's cheap but noisy. https://git-scm.com/book/en/v2/Git-Internals-Git-Objects
- **Unison:** a definition's id is the hash of its syntax tree. Local names are replaced by positions, and dependencies are referenced by their own hashes. Renaming changes nothing, but a change to a dependency changes every hash that uses it. **We shouldn't fold in dependency hashes like this; it would cause cascades.** https://www.unison-lang.org/docs/the-big-idea/
- **Tree-sitter:** there's no standard tool for hashing syntax trees (*unverified*); drift has its own. The recipe: find the definition node, serialize its named nodes with their leaf text, skip comments and whitespace, then hash.
- **Early cutoff:** if a rebuilt step's output is unchanged, the steps that depend on it don't re-run.
  - Shake: a comment edit leaves `main.o` unchanged, so there's no relink.
  - Bazel Skyframe calls this "change pruning".
  - Salsa calls it "backdating", and adds "durability" tiers for inputs that rarely change.
  - Sources:
    - https://bazel.build/reference/skyframe
    - https://salsa-rs.github.io/salsa/reference/algorithm.html
    - https://www.microsoft.com/en-us/research/uploads/prod/2018/03/build-systems.pdf
- **Applied in:** [[Live Docs Design#6.4 Fingerprints and diffs]]. As of v0.2, Phase 1 uses drift's fingerprints unmodified, and early cutoff is deferred, because it made reads write to the lock file.
