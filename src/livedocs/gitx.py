"""Git helpers: blobs at refs, the diff base for a binding, changed files."""

from __future__ import annotations

import subprocess
from pathlib import Path


class GitError(RuntimeError):
    pass


def run(repo: str | Path, *args: str, check: bool = True, timeout: int = 60) -> str:
    p = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, timeout=timeout)
    if check and p.returncode != 0:
        raise GitError(f"git {' '.join(args)}: {p.stderr.strip()}")
    return p.stdout


def head(repo: str | Path) -> str:
    return run(repo, "rev-parse", "HEAD").strip()


def blob_at(repo: str | Path, ref: str, path: str) -> str | None:
    """File contents at `ref`, or None if it doesn't exist there."""
    p = subprocess.run(["git", "-C", str(repo), "show", f"{ref}:{path}"], capture_output=True, text=True, timeout=60)
    return p.stdout if p.returncode == 0 else None


def changed_files(repo: str | Path, cached: bool = False, base: str = "HEAD") -> list[str]:
    args = ["diff", "--name-only"] + (["--cached"] if cached else []) + [base]
    return [l for l in run(repo, *args).split("\n") if l]


def lock_block(doc: str, target: str, sig: str) -> str:
    """The exact three lines drift writes for one binding."""
    return f'doc = "{doc}"\ntarget = "{target}"\nsig = "{sig}"'


def diff_base(repo: str | Path, doc: str, target: str, sig: str, lock_path: str = "drift.lock") -> str | None:
    """Newest first-parent commit whose drift.lock contains this exact binding.

    A plain `-S'sig = "…"'` returns the wrong commit when a sig is shared by two
    docs or recurs after a revert (review issue 4), so pickaxe the whole block
    and verify the blob really contains it.
    """
    block = lock_block(doc, target, sig)
    out = run(repo, "log", "--first-parent", "--format=%H", f"-S{block}", "--", lock_path, check=False)
    for commit in out.split():
        blob = blob_at(repo, commit, lock_path)
        if blob and block in blob:
            return commit
    return None
