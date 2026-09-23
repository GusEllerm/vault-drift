"""Stop: a non-blocking heads-up listing the notes this task's code changes affect (D11).
Never returns decision: block."""

from __future__ import annotations

import sys

from . import UNKNOWN_CONTEXT, arm_deadline, emit, read_input, repo_root, vault_rel_for

EVENT = "Stop"


def main() -> int:
    arm_deadline(EVENT)
    try:
        data = read_input()
        if data.get("stop_hook_active"):
            return 0
        repo = repo_root(data.get("cwd"))
        vault_rel = vault_rel_for(repo)
        if not vault_rel:
            return 0
        from .. import affected as af
        reports = af.affected(repo, vault_rel, cached=False)
        lines = af.summary_lines(reports)
        if not lines:
            return 0
        body = "\n".join(lines[:20]) + ("\n…" if len(lines) > 20 else "")
        emit(EVENT, "LIVE-DOCS heads-up: your code changes touch these notes; the pre-commit gate will "
                    "require each to be updated or acked (livedocs stamp <note> [--ack --reason …]):\n" + body)
        return 0
    except Exception as e:
        emit(EVENT, UNKNOWN_CONTEXT.format(why=f"{type(e).__name__}: {e}"[:200]))
        return 0


if __name__ == "__main__":
    sys.exit(main())
