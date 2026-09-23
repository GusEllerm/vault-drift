"""livedocs command line. M1: `survey` only."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

from . import mentions as mn
from . import symbols as sy


def cmd_survey(args: argparse.Namespace) -> int:
    """Resolve every mention in every note of a vault; print per-note counts (M1 proof)."""
    repo = Path(args.repo).resolve()
    vault = repo / args.vault
    idx = sy.index(repo, args.ref)
    notes = sorted(p for p in vault.rglob("*.md") if ".obsidian" not in p.parts and ".livedocs" not in p.parts)
    total = Counter()
    rows = []
    for p in notes:
        text = p.read_text(encoding="utf-8")
        rel = str(p.relative_to(repo))
        ms = mn.mentions(text)
        res = sy.resolve_note(rel, text, idx, ms)
        c = Counter(r.status for r in res)
        c["mentions"] = len(ms)
        c["targets"] = len({t for r in res for t in r.targets})
        total.update(c)
        rows.append((rel, c, res))
        if args.verbose:
            for r in res:
                print(f"{rel}:{r.mention.line}\t{r.status}\t{r.mention.raw!r}\t{r.rule}\t{','.join(r.targets)}")
    print(f"{'note':60} {'ment':>5} {'res':>4} {'sup':>4} {'const':>5} {'unres':>5} {'targets':>7}")
    for rel, c, _ in rows:
        print(f"{rel[-60:]:60} {c['mentions']:5} {c[sy.RESOLVED]:4} {c[sy.SUPERSET]:4} {c[sy.CONSTANT_ONLY]:5} {c[sy.UNRESOLVED]:5} {c['targets']:7}")
    print(f"{'TOTAL':60} {total['mentions']:5} {total[sy.RESOLVED]:4} {total[sy.SUPERSET]:4} {total[sy.CONSTANT_ONLY]:5} {total[sy.UNRESOLVED]:5}")
    print(f"symbols indexed: {len(idx.symbols)} in {len(idx.files)} files at {args.ref}")
    if args.json:
        Path(args.json).write_text(json.dumps(
            [{"note": rel, "counts": dict(c), "resolutions": [
                {"line": r.mention.line, "raw": r.mention.raw, "status": r.status, "rule": r.rule, "targets": r.targets}
                for r in res]} for rel, c, res in rows], indent=1))
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="livedocs")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("survey", help="resolve mentions across a vault and report counts")
    s.add_argument("--repo", required=True)
    s.add_argument("--vault", required=True, help="vault path relative to the repo")
    s.add_argument("--ref", default="HEAD")
    s.add_argument("--json", help="write per-note resolutions here")
    s.add_argument("-v", "--verbose", action="store_true")
    s.set_defaults(fn=cmd_survey)
    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
