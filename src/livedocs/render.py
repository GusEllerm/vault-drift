"""Text an agent sees for a check report. M4-minimal; the §6.7 template comes in M3."""

from __future__ import annotations

from . import astdiff
from .check import BROKEN, CHANGED, FRESH, UNKNOWN, Report

RULE = "The code decides what the system does; where this note disagrees about that, the code is right."


def render(r: Report, max_chars: int = 1500, show_warnings: bool = True, max_warnings: int = 3) -> str:
    name = r.note.rsplit("/", 1)[-1].removesuffix(".md")
    warn = ""
    if show_warnings and r.warnings:
        shown = r.warnings[:max_warnings]
        more = f"\n(+{len(r.warnings) - max_warnings} more possibly stale names)" if len(r.warnings) > max_warnings else ""
        warn = "\n" + "\n".join(f"Warning: {w}." for w in shown) + more
    if r.state == FRESH:
        return f'LIVE-DOCS: "{name}" is FRESH (verified {r.stamp.stamped[:10] if r.stamp else "?"}).' + warn
    if r.state == UNKNOWN:
        return f'LIVE-DOCS: "{name}" is UNVERIFIED ({"; ".join(r.reasons)}). Treat it as possibly out of date.' + warn
    head = f'LIVE-DOCS: "{name}" is {r.state.upper()} since last verified ({r.stamp.stamped[:10] if r.stamp else "?"}).\n{RULE}'
    body: list[str] = []
    for f in r.findings:
        loc = f"Note lines mentioning it: {', '.join(map(str, f.note_lines)) or '?'}."
        if f.kind == "anchor-missing":
            body.append(f"{f.target}: no longer found ({f.detail}). {loc}")
        elif f.kind == "file":
            body.append(f"{f.path}: file changed since {f.base_commit[:7] if f.base_commit else '?'}. {loc}")
        elif f.kind == astdiff.UNCHANGED:
            body.append(f"{f.path}#{f.qualname}: {f.detail or 'unchanged'}. {loc}")
        elif f.kind == "moved":
            body.append(f"{f.path}#{f.qualname}: {f.detail} (unchanged there). {loc}")
        elif f.kind == astdiff.REMOVED:
            body.append(f"{f.path}#{f.qualname}: no longer defined in the file. {loc}")
        elif f.kind == astdiff.ADDED:
            body.append(f"{f.path}#{f.qualname}: newly defined since last verified. {loc}")
        elif f.kind == "unknown-base":
            body.append(f"{f.path}#{f.qualname}: changed (stamp not yet committed, so no 'was' available)\n  now: {astdiff.first_line(f.now)}\n{loc}")
        else:
            was, now = astdiff.first_line(f.was), astdiff.first_line(f.now)
            line = f"{f.path}#{f.qualname}: {f.kind} changed"
            if f.kind == astdiff.SIGNATURE or was != now:
                line += f"\n  was: {was}\n  now: {now}"
            body.append(line + f"\n{loc}")
    out = head + "\n" + "\n".join(body) + warn
    if len(out) > max_chars:
        out = out[: max_chars - 20].rstrip() + "\n… (truncated)"
    return out
