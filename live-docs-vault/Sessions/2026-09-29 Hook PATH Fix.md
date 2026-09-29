---
type: session
status: active
authority: log
summary: "Bug from the globustore session: the Stop hook looped when livedocs was off PATH. Hook commands now find the launcher off PATH, and the Stop fallback no longer re-invokes the model."
created: 2026-09-29
updated: 2026-09-29
reviewed: 2026-09-29
tags: [live-docs, session]
---

# 2026-09-29 Hook PATH Fix

## The bug (reported by the globustore session)

A resumed Claude Code session had no `~/.local/bin` on PATH. The Stop hook written by `livedocs init` was `livedocs hook stop || printf '<additionalContext: "crashed…">'`. The bare `livedocs` was not found, so the fallback fired after every reply. On Stop, `additionalContext` starts a new turn, so the session looped: the same notice six times in a row. The shell fallback never checked `stop_hook_active`. (The Python path does check it, so the normal heads-up fires at most once.)

## Fix (`src/livedocs/install.py`, released in 0.1.4)

- **Launcher resolution.** The command tries `livedocs` on PATH first, then the launcher found at init time, then `$HOME/.local/bin/livedocs`. The init-time launcher is written only into `settings.local.json`; a shared `settings.json` gets no machine paths. It uses `shutil.which`, not symlink-resolved, so a uv/pipx shim stays a shim and survives upgrades. This keeps D14's rule: PATH first, and never an interpreter path.
- **Stop fallback is a `systemMessage`** (shown to the user, not fed to the model), so a missing or broken launcher cannot loop. The read-gate fallback stays `additionalContext`, because on PostToolUse it only annotates the tool result.
- **"Not found" is reported separately from "crashed."**
- Tests: `tests/test_install.py` runs the generated commands under `sh` with `PATH=/usr/bin:/bin`.

Existing installs keep the old command until `livedocs init` is re-run with the new version.
