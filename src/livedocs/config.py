"""Repo-level configuration: .livedocs/config.json at the repository root."""

from __future__ import annotations

import fnmatch
import json
import re
from pathlib import Path

from .mentions import frontmatter_end


def load(repo: str | Path) -> dict:
    p = Path(repo) / ".livedocs" / "config.json"
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def ignored(repo: str | Path, path: str, cfg: dict | None = None) -> bool:
    """Whether a repo-relative path is out of livedocs' scope by `ignore_paths` (globs, e.g. "content/**"):
    it never resolves as a code mention, never binds, and a commit touching only such paths passes the gate
    without running anything (the Obsidian Git plugin committing site content)."""
    cfg = load(repo) if cfg is None else cfg
    return any(fnmatch.fnmatch(path, g) or path.startswith(g.rstrip("*").rstrip("/") + "/")
               for g in cfg.get("ignore_paths", ()) if g)


_FLAG = re.compile(r"^livedocs:\s*snapshot\s*$", re.M)


def is_snapshot(repo: str | Path, note: str, text: str | None = None) -> bool:
    """Snapshot notes (P25) are dated records — reviews, reports, logs — that describe the code as it
    was, not as it is. They bind nothing and never block. Declared per note (`livedocs: snapshot` in
    the frontmatter) or in bulk (`snapshot_globs` in config, matched against the vault-relative path)."""
    for g in load(repo).get("snapshot_globs", []):
        if fnmatch.fnmatch(note, g):
            return True
    if text:
        lines = text.replace("\r\n", "\n").split("\n")
        end = frontmatter_end(lines)
        if end and _FLAG.search("\n".join(lines[:end])):
            return True
    return False
