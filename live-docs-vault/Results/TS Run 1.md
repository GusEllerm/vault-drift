---
type: results
status: active
authority: log
summary: "TypeScript support measured on the user's TS repos: on gravity-works' 338 commits the simulated gate demanded 210 hand reconciliations instead of 931 (−77%), blocking 26% of commits instead of 42%; Python unchanged on hpc-bridge; Astro handling checked on 374 real files. Recall: see §4."
created: 2026-10-23
updated: 2026-10-23
reviewed: 2026-10-23
tags: [live-docs, results, typescript]
---

# TS Run 1

> **Provenance:** replays run by the agent on 2026-10-23 on detached clones in `testbench/` (gitignored) with livedocs 0.2.0 (branch `ts-support`) and, for the baseline, 0.1.4 (`a9f2e4a`) with the same harness patch. Artefacts: `results/gw-gate-base`, `gw-gate-new`, `gw-1a`, `sd-gate-base`, `sd-gate-new` (rows compressed). Design: [[TypeScript Support]].

## 1. Method

- **Testbenches:** gravity-works (TypeScript only: 277 `.ts` files and some `.mjs`, **no `.tsx`/`.jsx`/`.astro`**; 40 live notes and about 200 snapshot notes; 338 first-parent commits from the vault's creation `eb9fc1f`, 2026-10-03, to 2026-10-16) and scheduler-dojo (Python simulator plus a TS front end; 78 commits from `59c72f8`, 2026-09-24). Both used livedocs 0.1.x for real, so their own `stamps.jsonl` records what the 0.1 gate cost.
- **Gate simulation (new, `replay --gate`):** at every commit, every unedited note left `changed`/`broken` is re-stamped as an ack, mechanically when provably benign, otherwise as a simulated hand ack. Each commit's hand acks are what the gate would have demanded of the committing agent. Run with 0.1.4 and 0.2.0 on the same history.
- **1a run (as runs 1 and 2):** flags persist until the author edits the note; graded for recall (§4).
- **Harness fix:** the replay no longer inherits a repository's own `drift.lock` and stamps at its first commit (both testbenches have them).

## 2. Overhead at the gate

**gravity-works**

| | 0.1.4 | 0.2.0 |
|---|---|---|
| Hand reconciliations demanded | **931** | **210** (−77%) |
| Acked mechanically (unseen) | 0 | 113 |
| Commits blocked | 143 of 338 (42%) | 89 (26%) |
| Notes per blocked commit (mean / max) | 6.5 / 18 | 2.4 / 18 |
| Finding kinds behind hand acks | file 931 | body 147, file 80, signature 14, anchor-missing 8, removed 2, added 1 |

- **The simulation reproduces the real history:** gravity-works' agents hand-acked 766 times under 0.1, with zero mechanical acks (931 simulated, and the gap is notes the agents updated instead of acking). Every 0.1 binding there was a whole-file anchor, which can never be proven benign.
- Of 0.2's 210, 130 involve TypeScript symbols. The 80 `file` findings are whole-file anchors on non-code files (JSON data, CSS), which still bind by path.

**scheduler-dojo**

| | 0.1.4 | 0.2.0 |
|---|---|---|
| Hand reconciliations demanded | 90 | 84 |
| — from Python code | 71 | 71 |
| — from TypeScript | 14 | 7 |
| Acked mechanically | 76 | 132 |
| Commits blocked | 24 of 78 | 23 |

The real history has 178 hand acks and 29 mechanical: agents acked many benign changes by hand (58 of the 178 reasons say "unchanged", "benign" or "re-read") and re-stamped under Python 3.12 because member hashes depended on the CPython minor (fixed: P32).

## 3. Binding and coverage

| | gravity-works 0.1.4 → 0.2.0 | scheduler-dojo |
|---|---|---|
| Mentions that bind (live notes) | 778 → 2,250 | 757 → 890 |
| Mentions bound to a whole `.ts` file with no member hash | 707 → 0 | 60 → 0 (1 left in a note edited since its stamp, re-bound by its next commit) |
| Coverage (`livedocs coverage`, live notes) | 19% → 51% (module notes 40–77%) | 47% → 55% |
| `drift.lock` bindings after `rebind` | 505 → 1,714 | 468 → 635 |

- **Python unchanged** (hpc-bridge, 61 live notes): 0 changed resolutions, the same 1,669 binding mentions.
- What stays unresolved in gravity-works is mostly vocabulary: piece kinds that are string-literal values (`drop`, `gapLip`), test-file paths, folders, level ids, `window.__gw*` test globals, DOM APIs.
- **Gate latency** grows with bindings, all of it drift's: `drift check` takes 3.0 s for gravity-works' 1,559 bindings (0.8 s for 0.1's 505); a hub-file edit ran the whole gate in about 4.7 s while three replays shared the CPU.

## 4. Recall

*(pending: stratified sample of 185 items graded by 7 Opus agents; see `results/gw-1a/sample/`.)*

## 5. Astro and TSX on real files

gravity-works has no JSX or Astro, so those paths were checked separately on 374 `.astro` and 45 `.tsx` files from `withastro/astro` (examples, components, e2e fixtures; shallow sparse clone in scratch, nothing executed):
- frontmatter parses: 373 of 374 (the exception is Astro's own `astro-frontmatter-syntax-error.astro` fixture); TSX: 45 of 45;
- a component's hash ignores an inserted HTML comment (373/373) and reflowed whitespace between tags (373/373), and sees a one-character text change (231/231).
- The site-shaped end-to-end flow (fresh repo, `new-vault`, Zod schema, loader/queries modules, an Astro component, `wrangler.jsonc`) found two bugs, both fixed: an Astro template change was auto-acked as "unchanged" (the classifier compared only the frontmatter text), and the Home template's examples bound real config files.

## 6. Caveats

- One TypeScript repository and one mixed repository, both agent-written by the user's sessions.
- The gate simulation acks every flag; it does not model notes an agent would have edited instead.
- No Astro or JSX history was replayed: those numbers are from fixtures and a static check.
