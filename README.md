# livedocs

Notes that know when the code moved on.

`livedocs` binds Markdown notes (an Obsidian vault, or any folder of `.md` files inside a repo) to the
code they mention, and makes the git commit the place where notes and code are reconciled. It is a
thin layer over [Fiberplane drift](https://github.com/fiberplane/drift) (which fingerprints symbols)
that adds what an agent-written vault needs:

- **Anchors derived from the note's own backtick mentions** — nothing to declare by hand.
- **A note hash and member-level hashes in append-only stamps**, so "this note was verified against
  this code" is a recorded fact, and only changes to what the note actually mentions count.
- **A git pre-commit gate**: a commit that changes code a note mentions is blocked until the note is
  updated or acked with a reason. Provably benign changes (comment-only edits, pure moves, changes to
  members the note doesn't mention) are acked mechanically. `unknown` never blocks.
- **A read-time report** for agents: `CHANGED` with *was / now* pinned to the note lines that mention
  the symbol — a fact, not a verdict. The agent that made the change decides what the note should say.
- **Coverage**: which of a note's code claims are anchored, and which names it uses that no longer exist.

The guarantee is a mechanism of the development framework (git), not a capability of any agent:
it holds for Claude Code, Codex, a human at a terminal, or anything else that commits.

## Install

```sh
brew install fiberplane/tap/drift          # or: curl -fsSL https://drift.fp.dev/install.sh | sh
uv tool install git+https://github.com/GusEllerm/vault-drift   # puts `livedocs` on PATH
```

Then, in the repository that holds the vault:

```sh
livedocs init --vault docs/vault           # git gate (.githooks + core.hooksPath), .livedocs/config.json,
                                           # Claude Code Stop heads-up (settings.local.json), AGENTS.md block
livedocs stamp "Modules/server.md"         # bind one note's mentions; repeat for each note (or loop)
git add drift.lock docs/vault/.livedocs/stamps.jsonl && git commit -m "livedocs baseline"
```

Each clone activates the versioned hook with `git config core.hooksPath .githooks` (`init` does it).

## The commit flow

```
edit code ──► git commit
              │  gate: notes that mention the changed code, not yet reconciled?
              ├─ none / benign ────────────────────────────────► commit passes (benign ones auto-acked)
              └─ some ──► "CHANGED: <note> … was: … now: … note lines 13, 30"
                          edit the note, then   livedocs stamp <note>                 (update)
                          or, still correct:    livedocs stamp <note> --ack --reason "…"
                          git add drift.lock <vault>/.livedocs/stamps.jsonl ; commit again
```

`livedocs affected` lists the notes your uncommitted changes touch before you get there.

## Commands

| Command | Does |
|---|---|
| `livedocs init --vault <path> [--read-gate] [--shared]` | install the gate, config and harness adapter |
| `livedocs stamp <note> [--ack --reason R]` | bind a note's mentions with drift and record a stamp |
| `livedocs check <note> [--json]` | one note's state: `fresh`, `changed`, `broken`, `unknown`, `snapshot` |
| `livedocs affected [--cached]` | notes bound to files changed in the working tree (or the index) |
| `livedocs verify` | CI: every stamped note against the checked-out tree; exit 1 on changed/broken |
| `livedocs coverage` | per-note anchored / dangling mentions |
| `livedocs survey` | resolution statistics over a vault (diagnostics) |

## Snapshot notes

Dated records — reviews, session logs, reports — describe the code as it *was*. Mark them with
`livedocs: snapshot` in the frontmatter, or list globs in `.livedocs/config.json`:

```json
{ "vault": "docs/vault", "snapshot_globs": ["Reference/Review *", "Sessions/*"] }
```

They bind nothing, report `snapshot`, and never block.

## CI

Pre-commit is skipped by `--no-verify`, merges and rebases. Run the same check in CI:

```yaml
# .github/workflows/livedocs.yml
name: livedocs
on: [push, pull_request]
jobs:
  verify:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: curl -fsSL https://drift.fp.dev/install.sh | sh && echo "$HOME/.local/bin" >> "$GITHUB_PATH"
      - uses: astral-sh/setup-uv@v5
      - run: uv tool install git+https://github.com/GusEllerm/vault-drift
      - run: livedocs verify --repo . --vault docs/vault
```

Or with the [pre-commit](https://pre-commit.com) framework, add to `.pre-commit-config.yaml`:

```yaml
- repo: https://github.com/GusEllerm/vault-drift
  rev: v0.1.0
  hooks: [{ id: livedocs-gate }]
```

## What it can and cannot guarantee

- It guarantees that a *committed* note has been vouched for against the code it mentions, at that
  commit. A read-time `changed` means the working tree has moved since.
- It sees code the note names in backticks. A prose claim with nothing to anchor ("tokens rotate every
  15 minutes") is reported `unknown`, never `fresh`. `livedocs coverage` shows how much of each note that is.
- It does not follow the call graph: a note's claim about what a function *does* can go stale when a
  callee changes. That is the residual miss class, measured at about 1 in 20 real changes on the
  reference history.
- Python only, for now (symbol resolution uses `ast`; drift fingerprints six languages).

## Background

Design, decisions and the measurements behind every choice live in the vault at `live-docs-vault/`
(start at `Start Here.md`). The short version: on a real 141-commit history, the hash flagged 22 of the
23 note-invalidating changes an anchor covered; only ~5% of flags marked a change that made a note wrong
— which is why the signal is delivered as a fact at commit time, to the agent that has the context, and
never as a verdict.
