"""PostToolUse(Grep|Bash): log reads of vault paths that bypass the Read gate. No output to the agent."""

from __future__ import annotations

import json
import re
import sys
import time

from . import read_input, repo_root, vault_rel_for


def main() -> int:
    try:
        data = read_input()
        repo = repo_root(data.get("cwd"))
        vault_rel = vault_rel_for(repo)
        if not vault_rel:
            return 0
        tool = data.get("tool_name", "")
        ti = data.get("tool_input") or {}
        text = json.dumps(ti)
        hits = sorted(set(re.findall(re.escape(vault_rel) + r"/[^\s\"']+\.md", text)))
        if not hits:
            return 0
        log = repo / vault_rel / ".livedocs" / "cache" / "bypass.jsonl"
        log.parent.mkdir(parents=True, exist_ok=True)
        with log.open("a") as f:
            f.write(json.dumps({"ts": int(time.time()), "session": data.get("session_id"), "tool": tool, "paths": hits}) + "\n")
        return 0
    except Exception:
        return 0


if __name__ == "__main__":
    sys.exit(main())
