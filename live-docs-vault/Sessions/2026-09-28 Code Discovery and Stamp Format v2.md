---
type: session
status: active
authority: log
summary: "Two fixes reported from adopters' repos: 0.1.2 discovers Python code wherever it lives (code_roots config); 0.1.3 stamp format v2 so secret scanners don't misread member fingerprints."
created: 2026-09-28
updated: 2026-09-28
reviewed: 2026-10-23
tags: [live-docs, session]
---

# 2026-09-28 Code Discovery and Stamp Format v2

> Provenance: written on 2026-09-28 as sections appended to [[2026-09-23 Runs 1 and 2]]; moved here unchanged on 2026-10-23 so each session has its own log.

## 0.1.2: code discovery (2026-09-28)

- A user's agent reported that code under `benchmark/src/` was invisible: `symbols.index` hard-coded `src/`, so the note was stamped unbound, its names read as dangling, and the gate had nothing to block on. Fixed: discovery indexes every tracked `.py` outside tests/environments/build/docs wherever it lives, `code_roots` in config pins it explicitly, `Symbol.module` strips any `…/src/` segment, and `new-vault --scaffold-modules` uses the same discovery. Tests cover nested `src/`, flat packages, excluded test doubles and the config override. Released as 0.1.2 via the tag workflow.

## 0.1.3: stamps that don't look like secrets (2026-09-28)

- GitGuardian flagged a `stamps.jsonl` line in the user's smbench project as a generic high-entropy secret: `"members":{"get_access_token":"4bda567785f5c517"}` — a member fingerprint keyed by a function named like a credential. A false positive (hashes of the repo's own code); the repo scan found no real secrets and the PyPI token nowhere in history.
- Fix: stamp format v2 tags every fingerprint (`drift:`, `ast:`) and stores members as `[qualname, fp]` pairs; v1 lines still read identically. `init`/`new-vault` write or merge `.gitguardian.yaml` (`drift.lock`, `**/.livedocs/stamps.jsonl`); this repo's config also covers `results/**/stamps.diff`. Tests reproduce the flagged line and assert v2 has no secret-shaped pairs; the end-to-end run confirmed 6 → 0 on a note about an auth module.
- **Incident:** during testing a chained `cd` into a cleared scratch folder failed and the following `git stash` ran in this repo, stashing the uncommitted 0.1.3 changes; recovered with `git stash pop`, nothing lost. Test scripts now run from a file with `set -u`, a guarded `cd`, and `git -C` only.
