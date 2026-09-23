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


def cmd_stamp(args: argparse.Namespace) -> int:
    from . import stamp as stp, stamps as st
    verdict = st.ACK if args.ack else None
    try:
        r = stp.stamp(Path(args.repo), args.vault, args.note, by=args.by, verdict=verdict,
                      reason=args.reason or "", file_anchors=args.file_anchors)
    except stp.StampError as e:
        print(f"refused: {e}", file=sys.stderr)
        return 2
    print(f"stamped {args.note}: {r.linked} bindings, {len(r.stamp.unresolved)} unresolved mentions, verdict={r.stamp.verdict}")
    for f in r.failed:
        print(f"  failed: {f}", file=sys.stderr)
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    from . import check as ck, render
    rep = ck.check(Path(args.repo), args.vault, args.note)
    if args.json:
        print(json.dumps(rep.to_dict(), indent=1))
    else:
        print(render.render(rep))
    return 0 if rep.state == ck.FRESH else 1


def _common(p: argparse.ArgumentParser) -> None:
    p.add_argument("--repo", required=True)
    p.add_argument("--vault", required=True, help="vault path relative to the repo")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="livedocs")
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("survey", help="resolve mentions across a vault and report counts")
    _common(s)
    s.add_argument("--ref", default="HEAD")
    s.add_argument("--json", help="write per-note resolutions here")
    s.add_argument("-v", "--verbose", action="store_true")
    s.set_defaults(fn=cmd_survey)

    s = sub.add_parser("stamp", help="bind a note's code mentions with drift and record a stamp")
    _common(s)
    s.add_argument("note", help="note path relative to the vault")
    s.add_argument("--by", default="human")
    s.add_argument("--ack", action="store_true", help="re-verify without edits (requires --reason)")
    s.add_argument("--reason")
    s.add_argument("--file-anchors", action="store_true", help="also bind bare module mentions to whole files")
    s.set_defaults(fn=cmd_stamp)

    s = sub.add_parser("check", help="report a note's freshness (read-only)")
    _common(s)
    s.add_argument("note")
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_check)

    s = sub.add_parser("replay", help="1a harness: replay history, stamping and checking notes")
    _common(s)
    s.add_argument("--from", dest="start", required=True)
    s.add_argument("--to", dest="end", default="HEAD")
    s.add_argument("--out", required=True)
    s.add_argument("--limit", type=int)
    s.add_argument("--file-anchors", action="store_true")
    s.add_argument("--refine", action="store_true", help="suppress flags when mentioned members are unchanged (run-2 mode)")
    s.set_defaults(fn=cmd_replay)

    s = sub.add_parser("affected", help="notes bound to files changed in the working tree (or --cached: the index)")
    _common(s)
    s.add_argument("--cached", action="store_true")
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_affected)

    s = sub.add_parser("coverage", help="which of each note's code mentions are anchored; dangling names")
    _common(s)
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_coverage)

    s = sub.add_parser("init", aliases=["install-hooks"],
                       help="set up the git gate (.githooks + core.hooksPath), .livedocs/config.json, and the Claude Code Stop heads-up")
    _common(s)
    s.add_argument("--no-claude", action="store_true", help="skip the Claude Code adapter")
    s.add_argument("--shared", action="store_true", help="write .claude/settings.json (project) instead of settings.local.json")
    s.add_argument("--read-gate", action="store_true", help="also install the read-time gate (Tier 2, opt-in)")
    s.add_argument("--bypass-log", action="store_true", help="also log reads that bypass the gate (measurement only)")
    s.add_argument("--no-agents-block", action="store_true", help="don't append the instruction block to AGENTS.md/CLAUDE.md")
    s.set_defaults(fn=cmd_install)

    s = sub.add_parser("hook", help="hook entry points (called by git and by the harness adapters)")
    s.add_argument("name", choices=["pre-commit", "stop", "read-gate", "bypass-log"])
    s.set_defaults(fn=cmd_hook)

    s = sub.add_parser("grade", help="export grading items from a replay run, or summarise verdicts")
    s.add_argument("action", choices=["export", "pregrade", "reuse", "split", "summarize"])
    s.add_argument("--repo")
    s.add_argument("--vault")
    s.add_argument("--out", required=True, help="the replay output directory")
    s.add_argument("--batch-size", type=int, default=80)
    s.add_argument("--from-run", help="reuse: the earlier run directory to carry verdicts from")
    s.set_defaults(fn=cmd_grade)

    args = ap.parse_args(argv)
    return args.fn(args)


def cmd_grade(args: argparse.Namespace) -> int:
    from . import grade
    if args.action == "export":
        if not (args.repo and args.vault):
            print("grade export needs --repo and --vault", file=sys.stderr)
            return 2
        grade.export(Path(args.repo), args.vault, args.out)
    elif args.action == "pregrade":
        grade.pregrade(args.out)
    elif args.action == "reuse":
        grade.reuse(args.from_run, args.out)
    elif args.action == "split":
        grade.split(args.out, args.batch_size)
    else:
        grade.summarize(args.out)
    return 0


def cmd_replay(args: argparse.Namespace) -> int:
    from . import replay
    summ = replay.run(Path(args.repo), args.vault, args.start, args.end, args.out, limit=args.limit,
                      file_anchors=args.file_anchors, refine=args.refine)
    print(json.dumps(summ.__dict__, indent=1))
    return 0


def cmd_affected(args: argparse.Namespace) -> int:
    from . import affected as af, render
    reports = af.affected(Path(args.repo), args.vault, cached=args.cached)
    if args.json:
        print(json.dumps([r.to_dict() for r in reports], indent=1))
    else:
        lines = af.summary_lines(reports)
        print("\n".join(lines) if lines else "no affected notes")
    return 0


def cmd_coverage(args: argparse.Namespace) -> int:
    from . import coverage as cov
    print(cov.report(cov.coverage(Path(args.repo), args.vault), as_json=args.json))
    return 0


def cmd_install(args: argparse.Namespace) -> int:
    from . import install
    repo = Path(args.repo).resolve()
    print("wrote", install.install_config(repo, args.vault))
    print("wrote", install.install_git(repo), "(core.hooksPath = .githooks)")
    if not args.no_claude:
        print("wrote", install.install_claude(repo, shared=args.shared, read_gate=args.read_gate, bypass_log=args.bypass_log))
    if not args.no_agents_block:
        p = install.install_agents_block(repo, args.vault)
        print("agents block:", p or "no AGENTS.md/CLAUDE.md found; add the block by hand if you want channel 3")
    if not install.check_drift():
        print("warning: `drift` is not on PATH. Install it: brew install fiberplane/tap/drift  (or curl -fsSL https://drift.fp.dev/install.sh | sh)")
    print("done. CI: run `livedocs affected --cached` or `livedocs check` in a job to catch --no-verify commits.")
    return 0


def cmd_hook(args: argparse.Namespace) -> int:
    mod = {"pre-commit": "pre_commit", "stop": "stop_heads_up", "read-gate": "read_gate", "bypass-log": "bypass_log"}[args.name]
    import importlib
    return importlib.import_module(f"livedocs.hooks.{mod}").main()


if __name__ == "__main__":
    sys.exit(main())
