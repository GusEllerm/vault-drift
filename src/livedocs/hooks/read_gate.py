"""PostToolUse(Read): the read-time gate. Attaches the freshness report to every vault note read."""

from __future__ import annotations

import sys

from . import UNKNOWN_CONTEXT, arm_deadline, emit, in_vault, read_input, repo_root, vault_rel_for

EVENT = "PostToolUse"


def main() -> int:
    arm_deadline(EVENT)
    try:
        data = read_input()
        path = (data.get("tool_input") or {}).get("file_path")
        if not path:
            return 0
        repo = repo_root(data.get("cwd"))
        vault_rel = vault_rel_for(repo)
        if not vault_rel:
            return 0
        note = in_vault(path, repo, vault_rel)
        if note is None:
            return 0
        from .. import check as ck, render
        rep = ck.check(repo, vault_rel, note)
        emit(EVENT, render.render(rep))
        return 0
    except Exception as e:  # fail closed
        emit(EVENT, UNKNOWN_CONTEXT.format(why=f"{type(e).__name__}: {e}"[:200]))
        return 0


if __name__ == "__main__":
    sys.exit(main())
