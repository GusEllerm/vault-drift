---
type: design
status: draft
authority: specifies
summary: "Implementation plan v0.2 for the Phase 1 code: the livedocs wrapper over drift (stamp, check, replay first; hooks and pre-commit after), revised after review, with verified drift facts and the 1a harness design."
created: 2026-09-22
updated: 2026-09-22
reviewed: 2026-09-22
tags: [live-docs, design, implementation]
---

# Implementation Plan

> **Status: draft v0.2, 2026-09-22.** Revised after [[2026-09-22 Implementation Plan Review]]. Implements [[Live Docs Design]] v0.3 for Phase 1 only. drift facts below were verified on the testbench with drift v0.10.1.

## 1. Scope

Build what Phase 1 needs ([[Live Docs Design#8. Plan]]), in the order that produces the 1a number first:
- **M1–M2, M4 (the 1a number):** `livedocs stamp | check | replay | grade`
- **M3, M5 (after 1a):** Claude Code hooks (read gate, Stop heads-up, bypass log), `affected`, pre-commit gate (D11), `install-hooks`

Documented code is **Python only** (hpc-bridge). Symbol resolution and diff classification use Python's `ast`; fingerprinting is drift's.

## 2. Verified facts about drift v0.10.1

| Fact | Consequence |
|---|---|
| Binds **top-level** symbols only. `path#Class.method` → "cannot compute fingerprint". Module constants also can't be anchored. | Method mentions resolve to the enclosing class; the wrapper narrows the explanation with `ast`. Constants are recorded as unverified mentions. Tag over-flags from unrelated methods as `class-granularity`. |
| **Re-linking an existing binding is refused** ("target changed since last link … relink with `--doc-is-still-accurate`"), even with unchanged code. | `stamp` always passes `--doc-is-still-accurate`. The note hash in our stamp is what carries "the author vouched for this". |
| **No `broken` result.** Renamed symbol → `stale` + `reason.code: symbol_not_found`; deleted file → `stale` + `file_not_found`. | Wrapper maps those reason codes to `broken`. |
| `drift check --format json` (`drift.check.v1`): per doc `path`, `result`, `anchors[]` (`identity`, `path`, `symbol`, `provenance.value` = sig, `result`, `reason`, `blame`), `links[]`, `summary`. | Consume `anchors[]` only. Ignore `links[]`: drift counts a broken markdown link as stale and doesn't percent-decode targets (report upstream). |
| `drift.lock` is TOML: `[[bindings]]` with `doc`, `target`, `sig`. | Diff base by pickaxe on the block (§4.5). `affected` reads the lock directly. |
| `drift refs` takes a **target** (`path#Symbol`); a bare path prints nothing. | Don't use it; read the lock. |
| drift hashes what is on disk from cwd and ignores git, mtimes and `.gitignore` (a no-`.git` copy gives identical sigs). | The index snapshot for pre-commit works; run with cwd at the snapshot root. |
| Fingerprint sensitivity: whitespace → `fresh`; **decorator added → `fresh`** (a miss); comment, docstring or quote-style change → `stale` (false flags). | Stamp carries a decorator hash per binding. `check` classifies the ast diff so `comment-only` / `formatter` / `decorator` cause tags are automatic. |

## 3. Layout

```
live-docs/                      (repo GusEllerm/vault-drift)
  pyproject.toml                uv; python >= 3.12; stdlib only (tomllib, ast, json, subprocess, hashlib)
  src/livedocs/
    cli.py                      stamp, check, replay, grade   (M4);  affected, install-hooks (M3/M5)
    mentions.py                 backtick spans → Mention(text, line, kind)
    symbols.py                  ast symbol index at a git ref; resolution rules
    drift_io.py                 drift subprocess wrapper; drift.lock reader
    stamps.py                   .livedocs/stamps.jsonl (append-only); note hash; freshness rule
    gitx.py                     blobs at refs; diff base; first-parent walk; index snapshot
    astdiff.py                  symbol source at two blobs; signature/decorator/body/comment classification
    check.py                    state machine + findings
    render.py                   §6.7 text (minimal in M4; polish in M3)
    replay.py  grade.py         1a harness and grading view
    hooks/ read_gate.py stop_heads_up.py bypass_log.py pre_commit.py   (M3/M5)
  tests/  fixtures/mini_repo/ + one test module per source module
  testbench/                    gitignored; hpc-bridge clone
```

A documented repo gains: `drift.lock` (drift's), `<vault>/.livedocs/stamps.jsonl`, `<vault>/.livedocs/cache/` (gitignored), `.gitattributes` line `stamps.jsonl merge=union`, and later hook config.

## 4. Components

### 4.1 `mentions.py`
- Only **backtick spans**, frontmatter excluded, fenced blocks included. Line numbers 1-based over the file.
- Dropped as noise: spans that are quoted strings, contain `$`, `=`, spaces or start with `-`; bare identifiers shorter than 4 chars or ALL_CAPS (env vars).
- Normalised: strip a trailing `:NNN` line hint (`credentials.py:78` → `credentials.py`), trailing `()`.
- Kinds: `path` (contains `/` or ends `.py`), `dotted` (`A.b`), `name`.

### 4.2 `symbols.py`
- `index(repo, ref)`: every tracked `*.py` **under `src/`** at `ref` (`git ls-tree`, `git show`, cached by blob id), parsed with `ast` → `Symbol(path, qualname, kind ∈ {function, class, method, constant}, top_level_name, decorators)`.
- `resolve(mention, note, index)`:
  1. `path` mentions → that file (plus symbol if `path#Sym`).
  2. Exact qualname match.
  3. **The note's own module first**: the module named by the note's H1 (`# server.py`) or filename (`facility-remote.md` → `facility/remote.py`); a unique match there wins.
  4. Unique top-level name in `src/`; else unique method name in `src/`.
  5. Still ambiguous → **bind all `src/` candidates** (a superset over-flags but never yields a false `fresh`), tagged `ambiguous-superset`.
  6. No candidate → `Unresolved` (kept in the stamp as a prose-only mention for 1a accounting).
- Drift target is always `path#<top_level_name>`; the stamp keeps the full qualname.

### 4.3 `drift_io.py`
- `link(doc, target)` runs `drift link <doc> <target> --doc-is-still-accurate`, succeeds on `added`/`updated` in stdout, raises on `error:`/`refused`. `unlink(doc, target)`. `check_json()`. `lock()` via `tomllib`.
- 20 s timeouts; failures raise `DriftError` → `unknown(checker-error)`.

### 4.4 `stamps.py`
- `<vault>/.livedocs/stamps.jsonl`, append-only:
  ```json
  {"note":"Modules/server.md","note_hash":"sha256:…","bindings":{"src/hpc_bridge/server.py#_connect_facility":{"sig":"656b9cc0…","deco":"ab12…"}},"mentions":{"src/hpc_bridge/server.py#_connect_facility":["_connect_facility"]},"unresolved":["Executor","Client"],"stamped":"…","by":"history|claude-code:<sid>|human","verdict":"initial|update|ack","reason":""}
  ```
- **Note hash** = sha256 over: body after the frontmatter block, line endings normalised to `\n`, trailing whitespace stripped per line, **plus** the `depends_on` frontmatter value if present.
- **Freshness rule:** among stamps whose `note_hash` equals the current hash, take the newest whose bindings are **all present in `drift.lock` with the same sig**; the note is `fresh` iff such a stamp exists, every one of its anchors is `fresh` in drift's JSON, and every decorator hash still matches. Anything else is not `fresh`.

### 4.5 `gitx.py`
- **Diff base for (doc, target, sig):** `git log --first-parent --format=%H -S'<block>' -- drift.lock` where `<block>` is the exact three-line `doc = … / target = … / sig = …` text; take the newest commit and **verify** its `drift.lock` blob contains the block. No such commit (uncommitted stamp) → no diff base, report `now` only. Reformatting `drift.lock` moves the base to a later commit whose code still matches the sig, which is harmless.
- `index_snapshot()`: `git checkout-index -a --prefix=<tmp>/`, with `drift.lock` required to be staged.
- `first_parent(from, to)`.

### 4.6 `astdiff.py` and `check.py`
- `check(note)` state machine (design §6.5):
  1. no stamps → `unknown(never-stamped)`
  2. hash matches no stamp → `unknown(edited-since-stamp)`
  3. matching stamp has zero bindings → `unknown(unbound)`
  4. drift error/timeout → `unknown(checker-error)`
  5. any anchor with `reason.code ∈ {symbol_not_found, file_not_found}` → `broken`
  6. any anchor `stale`, or decorator hash differs, or stamp sig ≠ lock sig → `changed`
  7. else `fresh`
- For each `changed` anchor, `astdiff` extracts the **mentioned qualname's** source at the diff base and now and classifies: `signature` (def line, args, annotations, return) / `decorator` / `body` / `comment-or-docstring-only`; or `"class changed elsewhere; <method> unchanged"` (the class-granularity case). Findings carry `note_lines` from the stamp's mentions re-located in the current text.
- `check` never writes outside `.livedocs/cache/`.

### 4.7 `render.py`
- M4: a plain text block per finding (state, anchor, kind, was/now, note lines). M3: the §6.7 template, the 1,500-char cap, tombstone header for `broken`, one line for `unknown`. **No once-per-session dedupe in Phase 1.**

### 4.8 `replay.py` and `grade.py` (the 1a harness)
- `livedocs replay --repo testbench/hpc-bridge --vault docs/hpc-bridge-vault --from 0ff0646 --to HEAD --out results/`
- Walks `--first-parent` (141 commits) on a branch `replay/<date>` in a dedicated worktree. Per commit `c`:
  1. `git read-tree -u --reset c` on the replay branch; restore the carried `drift.lock` and `stamps.jsonl`.
  2. **Check every stamped note first** and write a row `{commit, note, state, findings}`; for notes edited in `c`, also record `pre_edit_state` (the state *before* the author's edit — the strongest miss signal: 44 of 86 note edits in the window coincide with a change to the note's own module).
  3. Notes **deleted or renamed** in `c` → `unlink` their bindings, mark retired.
  4. Notes **added or edited** in `c` → `stamp` (verdict `update`, by `history`). All notes with mentions are stamped, not just `Modules/`.
  5. `git add drift.lock stamps.jsonl && git commit` on the replay branch so §4.5 works exactly as in production.
- **Flag episodes:** a flag is counted once per (note, anchor, stamp), not per commit, so a note that stays stale for 30 commits is one episode.
- **Sampling:** grade **all** rows where the note is `fresh` but its own module changed in that commit ("at risk", ~120–160 expected), not a random 10%; plus every flag episode.
- Output: `results/episodes.jsonl`, `results/at_risk.jsonl`, `results/summary.json`.
- `livedocs grade results/` shows one item at a time — note text at stamp, findings, code was/now, and at author edits the note diff — and records `{verdict ∈ {wrong, still-right}, cause}` with causes `real`, `class-granularity`, `formatter`, `comment-only`, `decorator`, `prose-only-claim`, `moved`, `ambiguous-superset`. Grading split per D10.

### 4.9 Hooks (M3) and pre-commit (M5)
- Hook commands are shell wrappers: `python -m livedocs.hooks.<name> || printf '%s' '<unknown JSON>'`, so import errors and crashes still emit `unknown(checker-error)`. Hook `timeout` in settings is set above the internal deadline (`signal.alarm` at 15 s, subprocess timeouts inside).
- `read_gate` (PostToolUse `Read`, vault `.md` only) → `additionalContext`. `stop_heads_up` (Stop; exit 0 if `stop_hook_active`; never `decision: block`) → `additionalContext`. `bypass_log` (PostToolUse `Grep|Bash`) → append to `.livedocs/cache/bypass.jsonl`, no output.
- `pre_commit`: `index_snapshot()`, cwd at its root, `check` every stamped note; `changed`/`broken` → print findings and exit 1; `unknown` never blocks; refuse if `stamps.jsonl` is modified but unstaged.
- `affected`: `git diff --name-only [--cached]` → bindings in `drift.lock` whose path changed → notes → `check`.

## 5. CLI

| Command | Milestone | Writes |
|---|---|---|
| `livedocs stamp <note> [--ack --reason R] [--by X]` | M2 | `drift.lock`, `stamps.jsonl` |
| `livedocs check <note> [--json]` | M2 | cache only |
| `livedocs replay …` / `livedocs grade …` | M4 | `results/`, replay branch |
| `livedocs affected [--cached]` | M3 | cache only |
| `livedocs install-hooks [--claude] [--git]` | M3/M5 | `.claude/settings.json`, `.git/hooks/pre-commit` |

`stamp --ack` requires an unchanged body hash; plain `stamp` on an unchanged hash is refused (design §6.8).

## 6. Milestones

| # | Deliverable | Proof |
|---|---|---|
| M1 | `mentions`, `symbols` | Over all 70 hpc-bridge notes at HEAD: counts of resolved / own-module / superset / unresolved / noise per note; hand-check 3 notes against the reviewer's numbers (399 unique top-level, 37 unique method, ~67 ambiguous, 231 unresolvable of 1,435 spans in `Modules/`). Unit tests on the mini repo. |
| M2 | `stamp`, `check`, `astdiff`, minimal `render` | On the testbench: stamp `server.md`; edit `_connect_facility` → `changed(signature|body)` with correct was/now and note lines; add a decorator → `changed(decorator)`; rename it → `broken`; revert → `fresh`; edit the note → `unknown(edited-since-stamp)`; re-`stamp` → `fresh`. |
| M4 | `replay`, `grade`, first 1a run | Full `--first-parent 0ff0646..HEAD`; `summary.json`; grade per D10; **miss rate (excluding prose-only) and precision with cause tags.** This is the Phase 1a result. |
| M3 | hooks, `affected` | **Done 2026-09-23** (exercised via stdin, not yet in a live session): gate fires on Read; `cat` is logged; Stop heads-up lists affected notes; drift missing or import crash yields the `unknown` line. |
| M5 | pre-commit | **Done 2026-09-23:** staged staling change → refused with was/now; `--ack` → passes; benign change → auto-acked with a recorded reason; unstaged `stamps.jsonl` → refused. |

## 7. Design choices (resolved by review)

- **a.** Class-level anchors for method mentions, plus a decorator hash now; add a method-level `ast` hash (~30 lines) only if `class-granularity` dominates 1a.
- **b.** Body-only note hash with `depends_on` folded in and line endings normalised.
- **c.** Diff base by block pickaxe + blob verification on `drift.lock`.
- **d.** `checkout-index` snapshot for pre-commit (0.04 s on hpc-bridge).
- **e.** No once-per-session dedupe in Phase 1.
- **f.** Backtick-only mentions with the §4.1–4.2 rules.
- **g.** No tree-sitter; Python `ast` only.

## 8. Not in Phase 1 code

MCP gateway, CI workflow, LLM judge, move suggestions, `livedocs_id`, per-language normalization, Bases/report, Grep tagging, Bash deny, non-code anchors, session dedupe.

## Changelog

- **v0.2 (2026-09-22):** after review — corrected drift facts (re-link refusal, no `broken`, `refs` semantics, fingerprint sensitivity); ambiguity superset policy and own-module preference; decorator hash; block pickaxe with blob verification; harness redesigned (first-parent, check-before-stamp with `pre_edit_state`, flag episodes, grade-all-at-risk, deletion handling, `read-tree` on the replay branch, all 70 notes); fail-closed shell wrappers; dedupe dropped; M4 pulled ahead of M3/M5 with `affected` and `install-hooks` deferred to M3.
- **v0.1 (2026-09-22):** first draft.
