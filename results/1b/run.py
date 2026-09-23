#!/usr/bin/env python3
"""Phase 1b runner (D13 form): one headless Claude Code session per task on the testbench, each on a
fresh branch from `1b-base`, with the gate installed. Collects everything needed to grade how the
agent reconciled the notes it affected: commits, code/note/stamp diffs, the gate's audit log, and
the session result.

usage: run.py <testbench-repo> <out-dir> [--only t1-rename,...] [--model opus]
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
VAULT = "docs/hpc-bridge-vault"
STAMPS = f"{VAULT}/.livedocs/stamps.jsonl"
AUDIT = f"{VAULT}/.livedocs/cache/precommit.jsonl"


def sh(repo: Path, *args: str, check: bool = True) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=check).stdout


def run_task(repo: Path, task: dict, out: Path, model: str) -> dict:
    tid = task["id"]
    tdir = out / tid
    tdir.mkdir(parents=True, exist_ok=True)
    branch = f"1b/{tid}-{int(time.time())}"
    sh(repo, "checkout", "-q", "-B", branch, "1b-base")
    audit = repo / AUDIT
    if audit.exists():
        audit.unlink()
    env = os.environ | {"PATH": f"{Path.home() / '.local/bin'}:{os.environ['PATH']}"}
    t0 = time.time()
    p = subprocess.run(
        ["claude", "-p", task["prompt"], "--model", model, "--max-turns", "40",
         "--permission-mode", "acceptEdits", "--allowedTools", "Read,Edit,Write,Bash,Grep,Glob",
         "--output-format", "json"],
        cwd=str(repo), capture_output=True, text=True, env=env, timeout=1800)
    secs = round(time.time() - t0)
    try:
        res = json.loads(p.stdout)
    except json.JSONDecodeError:
        res = {"raw_stdout": p.stdout[-4000:], "stderr": p.stderr[-2000:]}
    (tdir / "session.json").write_text(json.dumps(res, indent=1))

    commits = sh(repo, "log", "--format=%H %s", "1b-base..HEAD").splitlines()
    (tdir / "commits.txt").write_text("\n".join(commits) + "\n")
    (tdir / "code.diff").write_text(sh(repo, "diff", "1b-base..HEAD", "--", "src", "tests"))
    (tdir / "notes.diff").write_text(sh(repo, "diff", "1b-base..HEAD", "--", VAULT, ":(exclude)" + STAMPS))
    (tdir / "stamps.diff").write_text(sh(repo, "diff", "1b-base..HEAD", "--", STAMPS, "drift.lock"))
    (tdir / "uncommitted.txt").write_text(sh(repo, "status", "--short"))
    (tdir / "precommit-audit.jsonl").write_text(audit.read_text() if audit.exists() else "")
    # New stamp lines, parsed, so the grader sees verdict/by/reason at a glance
    new_stamps = []
    for line in sh(repo, "diff", "1b-base..HEAD", "--", STAMPS).splitlines():
        if line.startswith("+{"):
            s = json.loads(line[1:])
            new_stamps.append({k: s[k] for k in ("note", "verdict", "by", "reason", "stamped")})
    summary = {
        "task": tid, "expect": task["expect"], "branch": branch, "model": model, "seconds": secs,
        "turns": res.get("num_turns"), "cost_usd": res.get("total_cost_usd"),
        "commits": len(commits), "gate_runs": sum(1 for _ in (audit.read_text().splitlines() if audit.exists() else [])),
        "new_stamps": new_stamps, "uncommitted": bool((tdir / "uncommitted.txt").read_text().strip()),
        "result_tail": (res.get("result") or "")[-600:],
    }
    (tdir / "summary.json").write_text(json.dumps(summary, indent=1))
    sh(repo, "checkout", "-q", "--", ".")
    sh(repo, "clean", "-qfd", "--", "src", "tests")
    return summary


def main() -> int:
    repo = Path(sys.argv[1]).resolve()
    out = Path(sys.argv[2]).resolve()
    only = None
    model = "opus"
    args = sys.argv[3:]
    while args:
        a = args.pop(0)
        if a == "--only":
            only = set(args.pop(0).split(","))
        elif a == "--model":
            model = args.pop(0)
    tasks = json.loads((HERE / "tasks.json").read_text())
    results = []
    for t in tasks:
        if only and t["id"] not in only:
            continue
        print(f"== {t['id']}", flush=True)
        s = run_task(repo, t, out, model)
        print(json.dumps(s, indent=1), flush=True)
        results.append(s)
    (out / "summary.json").write_text(json.dumps(results, indent=1))
    sh(repo, "checkout", "-q", "1b-base")
    return 0


if __name__ == "__main__":
    sys.exit(main())
