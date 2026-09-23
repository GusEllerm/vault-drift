"""`livedocs new-vault`: scaffold an Obsidian vault for a project and wire livedocs into the repo.

Creates the vault (folders, Home, templates, minimal .obsidian/ so Obsidian opens it as a vault),
.livedocs/config.json with sensible snapshot globs, the git ignore entries Obsidian needs, the gate
and harness adapter (same as `livedocs init`), and an AGENTS.md block — creating AGENTS.md if the
project has none. With --scaffold-modules it also seeds one empty note per source module, without
code mentions, so nothing binds until someone writes a claim.
"""

from __future__ import annotations

import json
from pathlib import Path

from . import install

HOME = """\
# {name}

This vault is the long-term memory for **{project}**. Agents and people write it as the code takes shape;
`livedocs` keeps the notes honest: every note that names code in backticks is bound to that code, and a
commit that changes the code is blocked until the note is updated or acknowledged.

## Where things go

| Folder | Holds | Checked against code? |
|---|---|---|
| `Modules/` | one note per module or package: what it does, how it works, what depends on it | yes |
| `Concepts/` | ideas that span modules: an architecture, a lifecycle, an invariant | yes, where they name code |
| `Reference/` | external facts, surveys, dated reviews | reviews (`Review *`) are snapshots |
| `Sessions/` | one log per working session | snapshots (never checked) |
| `Templates/` | note templates (the Templates core plugin points here) | — |

## How to write a note that stays true

- Name code in backticks: `` `module.function()` ``, `` `ClassName` ``, `` `path/to/file.py` ``. Those are the
  claims livedocs checks. Prose that names no code is not checked (and is reported as such).
- Commit the note; the commit stamps it. There is nothing else to run.
- When a commit is blocked, the message shows *was / now* for the code that changed and the note lines
  that mention it. Edit the note and commit again, or `livedocs stamp <note> --ack --reason "…"` if the
  note is still right.
- Dated records go in `Sessions/` or are named `Reference/Review …`; they are snapshots and never block.

## Map

- [[Modules]] · [[Concepts]] · [[Reference]] · [[Sessions]]
"""

MODULE_TEMPLATE = """\
---
tags: [module]
---
# {{title}}

> [!abstract] Role
> One sentence: what this module is for.

## What it does

## How it works

## Depends on / used by
"""

SESSION_TEMPLATE = """\
---
livedocs: snapshot
tags: [session]
---
# {{date}} {{title}}

## Goal

## What was done

## Decisions

## Next
"""

CONCEPT_TEMPLATE = """\
---
tags: [concept]
---
# {{title}}

## In one line

## How it works
"""

FOLDER_NOTE = "# {folder}\n\n{blurb}\n"

FOLDERS = {
    "Modules": "One note per module or package. Name the code in backticks; livedocs checks it.",
    "Concepts": "Ideas that span modules. Name code where you make a claim about it.",
    "Reference": "External facts and dated reviews. Notes named `Review …` are snapshots.",
    "Sessions": "One log per working session. Snapshots: never checked, never block.",
}

OBSIDIAN = {
    "app.json": {},
    "appearance.json": {},
    "core-plugins.json": {
        "file-explorer": True, "global-search": True, "switcher": True, "graph": True, "backlink": True,
        "outgoing-link": True, "tag-pane": True, "properties": True, "page-preview": True,
        "templates": True, "command-palette": True, "outline": True, "word-count": True, "file-recovery": True,
    },
    "templates.json": {"folder": "Templates"},
}

GITIGNORE = """
# Obsidian per-machine state (livedocs new-vault)
{vault}/.obsidian/workspace.json
{vault}/.obsidian/workspace-mobile.json
{vault}/.trash/
"""

AGENTS_HEADER = """# Agent instructions

"""


def new_vault(repo: Path, vault_rel: str, *, name: str | None = None, scaffold_modules: bool = False,
              roots: tuple[str, ...] = ("src/",)) -> list[str]:
    repo = repo.resolve()
    vault = repo / vault_rel
    project = repo.name
    name = name or f"{project} vault"
    written: list[str] = []

    def w(path: Path, text: str) -> None:
        if path.exists():
            return  # never overwrite a note or config the project already has
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        written.append(str(path.relative_to(repo)))

    for folder, blurb in FOLDERS.items():
        w(vault / folder / f"{folder}.md", FOLDER_NOTE.format(folder=folder, blurb=blurb))
    w(vault / "Home.md", HOME.format(name=name, project=project))
    w(vault / "Templates" / "Module note.md", MODULE_TEMPLATE)
    w(vault / "Templates" / "Session log.md", SESSION_TEMPLATE)
    w(vault / "Templates" / "Concept.md", CONCEPT_TEMPLATE)
    for fname, data in OBSIDIAN.items():
        w(vault / ".obsidian" / fname, json.dumps(data, indent=2) + "\n")

    if scaffold_modules:
        for root in roots:
            for py in sorted((repo / root).rglob("*.py")) if (repo / root).exists() else []:
                rel = py.relative_to(repo / root)
                if py.name == "__init__.py" or "test" in py.name or any(p.startswith(".") for p in rel.parts):
                    continue
                stem = "-".join(rel.with_suffix("").parts)
                # H1 names the file so resolution prefers this module; no backticks, so nothing binds yet.
                w(vault / "Modules" / f"{stem}.md",
                  f"# {rel.as_posix()}\n\n> [!abstract] Role\n> (describe what this module is for)\n\n## What it does\n\n## How it works\n")

    # .gitignore entries Obsidian needs
    gi = repo / ".gitignore"
    block = GITIGNORE.format(vault=vault_rel)
    if not gi.exists() or "livedocs new-vault" not in gi.read_text():
        with gi.open("a") as f:
            f.write(block)
        written.append(".gitignore")

    # livedocs config with the vault's snapshot conventions, then the gate and adapter
    cfg_path = repo / ".livedocs" / "config.json"
    cfg = json.loads(cfg_path.read_text()) if cfg_path.exists() else {}
    cfg["vault"] = vault_rel
    globs = set(cfg.get("snapshot_globs", [])) | {"Sessions/*", "Reference/Review *", "Templates/*"}
    cfg["snapshot_globs"] = sorted(globs)
    cfg_path.parent.mkdir(exist_ok=True)
    cfg_path.write_text(json.dumps(cfg, indent=2) + "\n")
    written.append(".livedocs/config.json")
    install.install_config(repo, vault_rel)  # .livedocs/.gitignore for the cache
    written.append(str(install.install_git(repo).relative_to(repo)))
    written.append(str(install.install_claude(repo).relative_to(repo)))

    # AGENTS.md: append the block, creating the file if the project has none
    if not (repo / "AGENTS.md").exists() and not (repo / "CLAUDE.md").exists():
        (repo / "AGENTS.md").write_text(AGENTS_HEADER)
        written.append("AGENTS.md")
    p = install.install_agents_block(repo, vault_rel)
    if p:
        with p.open("a") as f:
            f.write(f"Write notes in `{vault_rel}/` (see `{vault_rel}/Home.md` for the layout); commit them and they are "
                    "stamped. Session logs go in `Sessions/` and are never checked.\n")
    return written
