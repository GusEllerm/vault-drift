---
type: session
status: active
authority: log
summary: "livedocs 0.1.0 published to PyPI (the user chose PyPI over making the repo public); sdist trimmed to code; tag-driven publish workflow awaiting the trusted publisher."
created: 2026-09-24
updated: 2026-09-24
reviewed: 2026-10-23
tags: [live-docs, session]
---

# 2026-09-24 PyPI Release

> Provenance: written on 2026-09-24 as a section appended to [[2026-09-23 Runs 1 and 2]]; moved here unchanged on 2026-10-23 so each session has its own log.

## Published (2026-09-24)

- An agent on the user's machine could not install from the private repo; the user chose PyPI over making the repo public. **livedocs 0.1.0 is on PyPI** (`uv tool install livedocs`), published with a token the user saved to a mode-600 file that was read by the shell and never printed. The sdist was trimmed to code, tests, README and licence first (it had been sweeping in the vault and results: 8.4 MB → 46 KB).
- `publish.yml` publishes on `v*` tags via PyPI trusted publishing once the user adds the GitHub publisher on PyPI (repo `GusEllerm/vault-drift`, workflow `publish.yml`, environment `pypi`).

## Decisions

- **User:** distribute through PyPI; the repo stays private (recorded on 2026-10-23 as D17 in [[Decision Log]]).
