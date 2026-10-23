---
type: session
status: active
authority: log
summary: "TypeScript/JavaScript, Astro and JSON config-key support built for the user's personal website and released as 0.2.0. Measured on gravity-works: the first path rule failed graded recall (~20% misses); with the user's 600-line rule (D18) the gate asked 362 times where 0.1.4 asked 931. Bugs fixed include a CPython-version hash bug and a false-benign Astro change; the global tool moved to PyPI."
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
- **Released (D19, D20):** `main` fast-forwarded to `389ac3c` and tag `v0.2.0` pushed; the publish, tests and livedocs workflows passed and 0.2.0 is on PyPI. The user's global tool was reinstalled from PyPI (tree-sitter included, TS parser verified). The branch and both worktrees were removed; raw replay outputs were moved out of the repo (the compressed copies are committed). The website and Baesian sessions were told, including a correction to the early path guidance.

- **Personal-website Phase 0 review, three issues (fixed on branch `hooks-paths`):**
  1. The pre-commit hook failed under the Obsidian Git plugin, which runs hooks with `PATH=/usr/bin:/bin`: `livedocs` and a Homebrew `drift` weren't found. The hook now tries the clone's recorded launcher (git config, written by `init`) and the usual install directories, and passes the extended PATH on so drift is found too.
  2. A dev note naming `content/Site.md` bound the site's content page. A path now never binds vault notes, media, fonts, archives or lockfiles. Markdown outside the vault still binds, because hpc-bridge's skills and commands are Markdown, and `ignore_paths` takes content out of scope.
  3. Commits that touch nothing bound now pass without running drift.
  Also found: a missing drift made the gate stamp notes silently unbound; it now blocks with a clear message. Reproduced end to end with real commits under `/usr/bin:/bin` from a built wheel; 70 tests.

- **`livedocs signatures`** (P36), requested by the Baesian session for its exported-API detector. Python: `__all__` or public names. TS/JS: `export` declarations, export clauses under their public names, the default export, non-private class members. Signatures include defaults; bodies, comments, decorators and field values never count. JSON; exit 0 unless an error. 74 tests.

## Key findings

- **Gate overhead on gravity-works:** 0.1.4 demanded 931 hand reconciliations (the real history has 766 hand acks and 0 mechanical). The first path rule (a module path binds only its default export) cut that to 210, but graded recall showed a ~20% miss rate, above D7's 10%. 11 of the 12 sampled misses were notes naming small modules by path. The revised rule binds small modules whole: 540 at 1,000 lines (measured), 362 at 600 lines (re-scored). The user chose 600 (D18).
- **Graded recall** (215 items, 8 Opus graders): see [[TS Run 1#4. Recall]]. Two auto-acked real catches were moves out of a file the note names; a move is no longer benign in that case.
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

## Decisions

- **Agent proposals:** P26–P32 in [[Decision Log]] (tree-sitter dependency, drift targets, mixed-language preference, module paths bind only the default export, JSON keys, orphan cleanup and `rebind`, hash schemes).
- **User:** D18 (P29 with a 600-line limit), D19 (release 0.2.0), D20 (global tool from PyPI).

## Open threads / next steps

- The user: review P26–P28 and P30–P32 (shipped as built).
- `livedocs rebind` in gravity-works and scheduler-dojo, an upgrade of their real repos and the user's call; until then, their 0.1 stamps keep working with whole-file TS anchors.
- Report drift's gaps upstream (JSX in `.tsx`, `.mjs` and friends, comment-sensitive TS fingerprints, per-file caching).
- Replay a repository with Astro/JSX history once one exists (the website, in a few weeks).

## Notes for the next agent

- Until D20 the user's global `livedocs` was an editable install of this checkout, so a branch checked out here ran in every project's gate. Since D20 it is the PyPI release. If it is ever made editable again, develop only in a worktree.
- Graders' TS item excerpts are capped at 12,000 characters (gravity-works' notes have paragraph-long lines).
- `results/sample_items.py` and `results/summarize_sample.py` are the stratified-grading pipeline for large runs.
