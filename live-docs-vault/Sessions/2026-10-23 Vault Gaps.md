---
type: session
status: active
authority: log
summary: "Vault housekeeping: later sessions split out of the 2026-09-23 log, Start Here's map and status caught up, two unlogged user decisions recorded (D16, D17), proposal status checked against the code, design-note banner. A TypeScript-support request arrived from the personal-website session."
created: 2026-10-23
updated: 2026-10-23
reviewed: 2026-10-23
tags: [live-docs, session]
---

# 2026-10-23 Vault Gaps

## Goal

The user asked for the vault gaps found while getting up to speed to be fixed before any new work.

## What was done

- **Session logs split.** The 2026-09-24 and 2026-09-28 work had been appended to [[2026-09-23 Runs 1 and 2]], a `log` note. Those sections moved unchanged into [[2026-09-24 PyPI Release]] and [[2026-09-28 Code Discovery and Stamp Format v2]], and the 2026-09-23 log was restored to its end-of-day content (commit `6705076`).
- **[[Start Here]]:** status gained the 0.1.2/0.1.3 bullet; the map lists every session; reading-order step 6 points at the map instead of naming one log, so it can't go stale again.
- **[[Decision Log]]:**
  - D16 (MIT licence) and D17 (PyPI, repo stays private) recorded. Both were the user's choices, written only in session logs until now.
  - P19 marked as accepted via D10, which already said so.
  - New agent-written table, "Where the proposals stand": P8–P25 checked against the 0.1.4 code. No status was changed.
- **[[Live Docs Design]]:** a banner says D11, D13, D14 and D15 override the v0.3 draft where they disagree. The note itself is not rewritten.

## Key findings

- Proposals built only in part: P12 has no once-per-session dedupe; under P16, `depends_on` enters the note hash but is not an anchor override; P18's retire is not built; P20's bypass escalation is not built (measurement only, D14).
- The tests pass (36) and `main` matched `origin/main` at the start of the session. Since 2026-09-29, only Obsidian's UI files had changed.

## Decisions

- **User:** none new. D16 and D17 record choices the user made on 2026-09-23 and 2026-09-24.
- **Agent:** none proposed.

## Open threads / next steps

- **Incoming request (from the personal-website session, relaying the user):** extend livedocs beyond Python to TypeScript/TSX/JS, contingently `.astro`, and optionally key-level JSON/YAML config anchors, for the user's new personal site. Use the TS game repos gravity-works and scheduler-dojo as detached testbench clones, plus a 1a-style replay. Deferred until after the vault gaps, at the user's direction. Not started.
- The user's open items are unchanged: the PyPI trusted publisher, the run-1 calibration pass, and accepting or rejecting P8–P25.

## Notes for the next agent

- A design v0.4 that folds in D11–D15 would let the design note bind again. It needs the user's review.
