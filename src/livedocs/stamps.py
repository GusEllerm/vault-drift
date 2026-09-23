"""Append-only stamps: the record that a note was verified against specific fingerprints."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path

from .mentions import frontmatter_end

STAMPS_REL = ".livedocs/stamps.jsonl"
INITIAL, UPDATE, ACK = "initial", "update", "ack"


@dataclass
class Binding:
    sig: str  # drift's fingerprint of the top-level target
    deco: str = ""  # our hash of the target's decorators (drift misses decorator changes)
    qualnames: list[str] = field(default_factory=list)  # what the note actually mentioned under this target
    members: dict[str, str] = field(default_factory=dict)  # qualname → member_hash at stamp time


@dataclass
class Stamp:
    note: str  # vault-relative path
    note_hash: str
    bindings: dict[str, Binding]  # drift target → Binding
    mentions: dict[str, list[list]]  # drift target → [[raw, line], …]
    unresolved: list[str]
    stamped: str
    by: str
    verdict: str
    reason: str = ""
    dangling: list[str] = field(default_factory=list)  # code-like mentions that resolve to nothing in src

    def to_json(self) -> str:
        d = asdict(self)
        return json.dumps(d, separators=(",", ":"))

    @classmethod
    def from_json(cls, line: str) -> "Stamp":
        d = json.loads(line)
        d["bindings"] = {k: Binding(**v) for k, v in d["bindings"].items()}
        return cls(**d)


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


_DEPENDS_ON = re.compile(r"^depends_on:\s*(.*)$", re.M)


def note_hash(text: str) -> str:
    """sha256 over the body after frontmatter, CRLF→LF, trailing whitespace stripped,
    plus the depends_on frontmatter value (it is a claim about code)."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = text.split("\n")
    start = frontmatter_end(lines)
    fm, body = lines[:start], lines[start:]
    while body and not body[-1].strip():  # trailing blank lines don't change the note
        body.pop()
    h = hashlib.sha256()
    for l in body:
        h.update(l.rstrip().encode("utf-8"))
        h.update(b"\n")
    m = _DEPENDS_ON.search("\n".join(fm))
    if m:
        h.update(b"depends_on:" + m.group(1).strip().encode("utf-8"))
    return "sha256:" + h.hexdigest()


def stamps_path(vault: str | Path) -> Path:
    return Path(vault) / STAMPS_REL


def load(vault: str | Path) -> list[Stamp]:
    p = stamps_path(vault)
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        if line.strip():
            out.append(Stamp.from_json(line))
    return out


def append(vault: str | Path, stamp: Stamp) -> None:
    p = stamps_path(vault)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(stamp.to_json() + "\n")


def for_note(all_stamps: list[Stamp], note: str) -> list[Stamp]:
    return [s for s in all_stamps if s.note == note]


def matching(note_stamps: list[Stamp], current_hash: str, lock: dict[tuple[str, str], str], doc: str) -> Stamp | None:
    """Newest stamp whose note_hash matches and whose bindings are all in drift.lock with the same sig."""
    for s in reversed(note_stamps):
        if s.note_hash != current_hash:
            continue
        if all(lock.get((doc, t)) == b.sig for t, b in s.bindings.items()):
            return s
    return None


def latest(note_stamps: list[Stamp]) -> Stamp | None:
    return note_stamps[-1] if note_stamps else None
