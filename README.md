# livedocs

Notes that know when the code moved on.

`livedocs` binds Markdown notes (an Obsidian vault, or any folder of `.md` files inside a repo) to the
code they mention, and makes the git commit the place where notes and code are reconciled. It is a
thin layer over [Fiberplane drift](https://github.com/fiberplane/drift) (which fingerprints symbols)
that adds what an agent-written vault needs:

- **Anchors derived from the note's own backtick mentions** — nothing to declare by hand. Python,
  TypeScript/JavaScript (`.ts .tsx .js .jsx .mjs .cjs .mts .cts`), Astro components, and keys in JSON
  config files ([Languages](#languages)).
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

## New project? One command

```sh
livedocs new-vault docs/vault --scaffold-modules
```

creates an Obsidian vault (`Home.md`, `Modules/ Concepts/ Reference/ Sessions/ Templates/`, a minimal
`.obsidian/`), one empty note per source module, the livedocs config (sessions, reviews and templates
are snapshots), the git gate, the Claude Code adapter, and an `AGENTS.md` block — then commit. Open the
folder in Obsidian as a vault. From there: write notes, commit, reconcile when the gate says so.

## Install

```sh
brew install fiberplane/tap/drift          # or: curl -fsSL https://drift.fp.dev/install.sh | sh
```

Then `livedocs` itself, from PyPI (its only dependencies are the tree-sitter TypeScript parser wheels):

```sh
uv tool install livedocs                   # or: pipx install livedocs
```

To hack on it: `uv tool install --editable /path/to/vault-drift`.

Then, in the repository that holds the vault:

```sh
livedocs init --vault docs/vault           # git gate (.githooks + core.hooksPath), .livedocs/config.json,
                                           # Claude Code Stop heads-up (settings.local.json), AGENTS.md block
```

That is the whole setup. Notes are stamped by the commit that adds or edits them: write a note, commit
it, and the gate binds its code mentions and records the stamp in the same commit. For an existing vault,
`git add` the notes and commit once (or run `livedocs stamp <note>` per note to see what each binds).
Each clone activates the versioned hook with `git config core.hooksPath .githooks` (`init` does it).
`--repo` defaults to the current git repository and `--vault` to the configured one, so inside the repo
the commands need no arguments.

## The commit flow

```
edit code ──► git commit
              │  gate: notes that mention the changed code, not yet reconciled?
              ├─ none / benign ────────────────────────────────► commit passes (benign ones auto-acked;
              │                                                   new or edited notes stamped)
              └─ some ──► "CHANGED: <note> … was: … now: … note lines 13, 30"
                          edit the note and commit again          (the commit stamps it)
                          or, still correct:  livedocs stamp <note> --ack --reason "…"; git add -A; commit
```

`livedocs affected` lists the notes your uncommitted changes touch before you get there.

## Commands

| Command | Does |
|---|---|
| `livedocs new-vault <path> [--scaffold-modules]` | scaffold an Obsidian vault and wire everything in |
| `livedocs init --vault <path> [--read-gate] [--shared]` | install the gate, config and harness adapter for an existing vault |
| `livedocs stamp <note> [--ack --reason R]` | bind a note's mentions with drift and record a stamp |
| `livedocs check <note> [--json]` | one note's state: `fresh`, `changed`, `broken`, `unknown`, `snapshot` |
| `livedocs affected [--cached]` | notes bound to files changed in the working tree (or the index) |
| `livedocs verify` | CI: every stamped note against the checked-out tree; exit 1 on changed/broken |
| `livedocs coverage` | per-note anchored / dangling mentions |
| `livedocs rebind` | after an upgrade: re-stamp every unedited note under the current binding rules |
| `livedocs survey` | resolution statistics over a vault (diagnostics) |

## Languages

| Language | Files | A mention can name |
|---|---|---|
| Python | `.py` | functions, classes, methods, class attributes, module constants |
| TypeScript / JavaScript | `.ts .tsx .mts .cts .js .jsx .mjs .cjs` | functions and arrow-function consts, classes and their methods/fields, interfaces and their members, type aliases, enums, constants, keys of top-level object literals (`SET_TOKENS.kitchen.background`, also inside `defineConfig({…})` and `z.object({…})`), default exports |
| Astro | `.astro` | the component (by its file name: `ProjectCard`, `<ProjectCard />`) and its frontmatter's declarations (`Props`, `getStaticPaths`) |
| JSON config | `package.json`, `tsconfig.json`, `wrangler.jsonc`, `*.config.json`, any `.jsonc` | key paths: `wrangler.jsonc#assets.directory`, `compilerOptions.paths` |

How TypeScript mentions resolve: `<Header />` names a component; `@/components/Header` follows
tsconfig `paths`; a barrel's `export { default as Header } from './Header'` resolves to the definition,
never to the barrel; a default export is also found by its file's name. Every mentioned member carries a
hash that ignores comments, whitespace, quote style, optional semicolons, trailing commas and redundant
parentheses, so formatting and comment edits are acked mechanically at commit. drift fingerprints
top-level symbols in `.ts` and `.js`; everywhere else (JSX, `.mjs`, Astro, `default`, keys) the file is
bound and the member hashes decide.

**Paths name a module's default export, not its every line.** A backtick path to a code file binds that
module's default export (a component, a `defineConfig({…})` object) and nothing else; a module with no
default export binds nothing by path. Whole-file anchors on hub modules made the gate block every note
that names the file on every commit that touched it (one TypeScript project hand-acked 766 times on them). Name the
functions and types a note describes. Set `"file_anchors": true` in `.livedocs/config.json` to bind
whole files anyway.

Notes that stay cheap to keep anchored:
- name symbols, not files: `getProjects()`, `projectSchema.title`, `<ProjectCard />`;
- give exported symbols names that are unique across the repo: a bare `load` defined in every
  `src/modules/*/loader.ts` binds all of them (safe, but each change flags every note that says `load`);
- title a module note with its path (`# src/modules/projects/schema.ts`): ambiguous names then prefer
  that module;
- one default-exported component per file, named after the file.

In a repository with both Python and TypeScript, a note resolves in the language it is about (the module
it is named after, or most of what it names) before falling back to both.

**Upgrading from 0.1.x** in a TypeScript project: notes stamped by 0.1 hold whole-file anchors. Run
`livedocs rebind`, then commit `drift.lock` and the stamps file. Every unedited note is acked under the
new rules; edited notes are re-bound by the commit that contains them. In any project, 0.1 stamps keep
working, but their Python member hashes depend on the CPython minor version (a stamp made on 3.13 read as
changed in CI on 3.12); 0.2's are stable across versions, and `rebind` moves existing notes to them.

## Snapshot notes

Dated records — reviews, session logs, reports — describe the code as it *was*. Mark them with
`livedocs: snapshot` in the frontmatter, or list globs in `.livedocs/config.json`:

```json
{ "vault": "docs/vault", "snapshot_globs": ["Reference/Review *", "Sessions/*"] }
```

They bind nothing, report `snapshot`, and never block.

## Secret scanners

`drift.lock` and `<vault>/.livedocs/stamps.jsonl` hold fingerprints — hashes of your own code's syntax
trees. Anyone who can read them can read the code they were computed from; they grant access to
nothing. Secret scanners can still misread a hash next to a name like `get_access_token` as a leaked
token. Since 0.1.3, stamps tag every fingerprint (`drift:…`, `ast:…`) and store members as pairs so they
don't have that shape, and `init` / `new-vault` add both files to `.gitguardian.yaml`'s
`secret.ignored_paths`, which ggshield (pre-commit, CI) reads. If you use the GitGuardian dashboard's
repository monitoring, add the same two paths as exclusions in its workspace settings, and mark any
earlier alert on these files as a false positive. `drift.lock` itself is drift's format and still holds
bare `sig = "<hex>"` values.

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
      - run: uv tool install livedocs
      - run: livedocs verify --repo . --vault docs/vault
```

Or with the [pre-commit](https://pre-commit.com) framework, add to `.pre-commit-config.yaml`:

```yaml
- repo: https://github.com/GusEllerm/vault-drift
  rev: v0.2.0
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
- Python, TypeScript/JavaScript, Astro and JSON config keys (see [Languages](#languages)). Module
  resolution reads tsconfig/jsconfig `paths`, not bundler aliases (Vite `resolve.alias`). An Astro
  template is compared as normalised text (comments and whitespace removed, `<script>` as TS tokens), not
  parsed. YAML and TOML files bind as whole files.
- Code is discovered wherever it lives — `src/`, `benchmark/src/`, a flat package — excluding tests,
  environments, build output and docs. To pin it, set `"code_roots": ["lib", "services/api"]` in
  `.livedocs/config.json`.

## Background

Design, decisions and the measurements behind every choice live in the vault at `live-docs-vault/`
(start at `Start Here.md`). The short version: on a real 141-commit history, the hash flagged 22 of the
23 note-invalidating changes an anchor covered; only ~5% of flags marked a change that made a note wrong
— which is why the signal is delivered as a fact at commit time, to the agent that has the context, and
never as a verdict.
