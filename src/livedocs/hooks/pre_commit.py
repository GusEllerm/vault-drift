"""git pre-commit: block the commit while a staged code change leaves a note CHANGED or BROKEN (D11).

Checks the *index*: a checkout-index snapshot is what drift and the checker read, so an unstaged fix
doesn't count and an unstaged code change doesn't flag. Mechanically benign reports (comment-only
edits, verified moves, 'class changed elsewhere') are auto-acked with a recorded reason and the
stamps file is re-staged. UNKNOWN never blocks.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from . import repo_root, vault_rel_for


def snapshot_index(repo: Path) -> Path:
    tmp = Path(tempfile.mkdtemp(prefix="livedocs-index-"))
    subprocess.run(["git", "-C", str(repo), "checkout-index", "-a", "--prefix", str(tmp) + "/"], check=True)
    return tmp


def _audit(repo: Path, vault_rel: str, staged: list[str], reports) -> None:
    """Untracked audit line per gate run (.livedocs/cache/precommit.jsonl): a commit that has no
    matching line was made with --no-verify. Used by experiments; harmless in production."""
    import json
    import time
    try:
        p = repo / vault_rel / ".livedocs" / "cache" / "precommit.jsonl"
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a") as f:
            f.write(json.dumps({"ts": int(time.time()), "staged": staged,
                                "notes": {r.note: r.state for r in reports}}) + "\n")
    except OSError:
        pass


def main() -> int:
    try:
        repo = repo_root(None)
        vault_rel = vault_rel_for(repo)
        if not vault_rel:
            return 0
        from .. import affected as af, check as ck, gitx, stamps as st, stamp as stp
        stamps_rel = f"{vault_rel}/{st.STAMPS_REL}"
        # A fix to the stamps file that isn't staged won't be in the commit: refuse rather than mislead.
        unstaged = set(gitx.changed_files(repo, cached=False))
        staged = gitx.changed_files(repo, cached=True)
        if stamps_rel in unstaged and stamps_rel not in staged:
            print(f"livedocs: {stamps_rel} is modified but not staged; stage it (git add) or discard the change.")
            return 1
        snap = snapshot_index(repo)
        try:
            reports = af.affected(repo, vault_rel, changed=staged, snapshot=snap)
            _audit(repo, vault_rel, staged, reports)
            blocking: list[ck.Report] = []
            acked: list[str] = []
            for r in reports:
                if r.state in (ck.FRESH, ck.UNKNOWN, ck.SNAPSHOT):
                    continue
                if ck.mechanically_benign(r):
                    kinds = ", ".join(sorted({f.kind for f in r.findings}))
                    stp.stamp(repo, vault_rel, r.note, by="pre-commit", verdict=st.ACK, reason=f"mechanical: {kinds}")
                    acked.append(r.note)
                    continue
                blocking.append(r)
            if acked:
                gitx.run(repo, "add", stamps_rel, "drift.lock")
                print("livedocs: auto-acked (benign to the mentioned members): " + ", ".join(acked))
            if not blocking:
                return 0
            from .. import render
            print("livedocs: commit blocked — these notes mention code this commit changes and have not been reconciled:\n")
            for r in blocking:
                print(render.render(r, max_chars=1200, show_warnings=False))
                print()
            print("Reconcile each, then commit again:")
            print("  edit the note, then:  livedocs stamp <note>            (update)")
            print("  or, if it is still right: livedocs stamp <note> --ack --reason '<why>'")
            print("Then: git add drift.lock", stamps_rel)
            return 1
        finally:
            shutil.rmtree(snap, ignore_errors=True)
    except Exception as e:
        # Fail closed at commit time too, but say so plainly.
        print(f"livedocs: pre-commit check could not run ({type(e).__name__}: {e}). Commit blocked; use --no-verify to override.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
