---
type: session
status: active
authority: log
summary: "TypeScript/JavaScript, Astro and JSON config-key support built for the user's personal website (0.2.0, branch ts-support), measured on gravity-works (gate: 931 → 210 hand reconciliations) and scheduler-dojo; seven bugs found, including a CPython-version hash bug and a false-benign Astro template change; the global livedocs tool was found to run this checkout."
created: 2026-10-23
updated: 2026-10-23
reviewed: 2026-10-23
tags: [live-docs, session, typescript]
---

# 2026-10-23 TypeScript Support

Follows [[2026-10-23 Vault Gaps]] in the same session.

## Goal

The personal-website session, relaying the user, asked for livedocs beyond Python: TypeScript/TSX/JavaScript first, then `.astro` (confirmed mid-session: the user chose Astro), and optionally key anchors in JSON config. The user asked for it to be "mature for hand back and use within another project".

## What was done

- **Verified drift's limits** (scratch repo): symbols in `.ts`/`.js` only, nothing in a `.tsx` file with JSX, `.mjs`/`.jsx`/`.cjs`/`.mts`, methods, `default` or keys; Astro as a whole file; TS fingerprints change on comments. See [[TypeScript Support#1. Why livedocs has to parse TypeScript itself]].
- **Built** (`ts.py`, `configkeys.py`, changes across `symbols`, `mentions`, `stamp`, `check`, `astdiff`, hooks, scaffold): [[TypeScript Support]]. 60 tests (was 36), including end-to-end gate tests on a TS/Astro fixture.
- **Testbenches:** detached clones of gravity-works and scheduler-dojo in `testbench/` (several copies for parallel runs). Nothing was run in the user's game repositories except read-only git.
- **Measured:** [[TS Run 1]]: a new gate-simulation replay mode, 0.1.4 vs 0.2.0 on both repos; a 1a run on gravity-works graded on a stratified sample by eight Opus agents; Python regression on hpc-bridge; Astro on 374 real files.
- **Early guidance sent to the website session** (cheap vs costly coding patterns), adopted there as provisional conventions.

## Key findings

- **Gate overhead on gravity-works: 931 → 210 hand reconciliations (−77%); blocked commits 42% → 26%.** The 0.1.4 simulation is close to the real history (766 hand acks, 0 mechanical).
- **Python is unchanged** on hpc-bridge (0 changed resolutions, 1,669 binding mentions).
- **Bugs found, all fixed on the branch:**
  1. the gate blocked the first commit of a repository without commits (worse than the reported Stop-hook symptom);
  2. a note bound to an image crashed `check` and the gate when the image changed;
  3. 0.1's Python member hashes used `ast.dump`, which differs between CPython 3.12 and 3.13, so CI on another Python read notes as changed (scheduler-dojo's agent had worked around it);
  4. an Astro template change was auto-acked as "unchanged" because the classifier compared only the frontmatter text, a false benign caught by the site-shaped end-to-end flow (now covered by a test and a safety net: a current-scheme hash change can never be classed unchanged);
  5. the Home template's examples bound real files in adopters' repos, and a brace in it crashed `new-vault` (reported by the Baesian session too);
  6. `--scaffold-modules` found nothing before a project's first commit;
  7. `stamp` left orphaned bindings in `drift.lock`; and `drift.lock` was re-parsed for every note check.
- **The user's global `livedocs` is an editable install of this checkout** (`uv tool` receipt). From the first source edit (shortly before 10:00) until about 10:43, this session's work in progress was what every project's gate and Stop hook ran, without its new tree-sitter dependency. Only one commit landed meanwhile (agentic-memory, Python, 10:00); re-stamping it with 0.1.4 under Python 3.12 gave identical bindings and hashes. The checkout went back to `main`; work continued in the worktree `../live-docs-ts`.
- Recall: see [[TS Run 1#4. Recall]].

## Decisions

- **Agent proposals:** P26–P32 in [[Decision Log]] (tree-sitter dependency, drift targets, mixed-language preference, module paths bind only the default export, JSON keys, orphan cleanup and `rebind`, hash schemes).
- **User:** none this phase. Merging to `main`, tagging `v0.2.0` and publishing to PyPI wait for the user.

## Open threads / next steps

- The user: accept or reject P26–P32; approve the merge and release; decide whether the global tool should stay an editable install of the working checkout.
- After release: `livedocs rebind` in gravity-works and scheduler-dojo (an upgrade of their real repos, the user's call); the website and Baesian make their first commits on 0.2.0 (or once with `--no-verify` on 0.1.4).
- Report drift's gaps upstream (JSX in `.tsx`, `.mjs` and friends, comment-sensitive TS fingerprints, per-file caching).
- Replay a repository with Astro/JSX history once one exists (the website, in a few weeks).

## Notes for the next agent

- **Never develop in `/Users/gusellerm/Projects/live-docs` itself:** the user's global `livedocs` runs that checkout (editable). Keep it on a released commit and work in a worktree (`../live-docs-ts` for this branch).
- Graders' TS item excerpts are capped at 12,000 characters (gravity-works' notes have paragraph-long lines).
- `results/sample_items.py` and `results/summarize_sample.py` are the stratified-grading pipeline for large runs.
