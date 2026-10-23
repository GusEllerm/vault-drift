"""Key-level anchors in JSON config files: `wrangler.jsonc#assets.directory`, `compilerOptions.paths`.

The P24 pattern applied to configuration: drift binds the whole file and livedocs hashes the value at
the key path, so a note that names one key is not flagged when another key changes. Only config files
are indexed (by name, `*.config.json`, any `.jsonc`): data files and lock files are not configuration.
"""

from __future__ import annotations

import hashlib
import json
import posixpath
import re

_NAMES = frozenset({
    "package.json", "tsconfig.json", "jsconfig.json", "wrangler.json", "deno.json", "vercel.json",
    "netlify.json", "firebase.json", "app.json", "manifest.json", "components.json", "biome.json",
    "turbo.json", "nx.json", "lerna.json", "renovate.json", ".eslintrc.json", ".prettierrc.json",
})
_PATTERN = re.compile(r"^(tsconfig\..+|.+\.config)\.json$")
_IDENT = re.compile(r"^[A-Za-z_$][A-Za-z0-9_$]*$")
MAX_BYTES = 128 * 1024
MAX_DEPTH = 4
MAX_KEYS = 400


def is_config(path: str) -> bool:
    name = posixpath.basename(path)
    return name.endswith(".jsonc") or name in _NAMES or bool(_PATTERN.match(name))


def _load(source: str | None):
    if source is None or len(source) > MAX_BYTES:
        return None
    from .ts import jsonc_loads
    try:
        return jsonc_loads(source)
    except ValueError:
        return None


def keys(path: str, source: str) -> list[tuple[str, int]]:
    """(dotted key path, line) for identifier-like keys of nested objects, arrays not descended."""
    data = _load(source)
    out: list[tuple[str, int]] = []
    lines = source.split("\n")

    def line_of(k: str) -> int:
        needle = f'"{k}"'
        for i, l in enumerate(lines, 1):
            if needle in l:
                return i
        return 0

    def walk(obj, prefix: str, depth: int) -> None:
        for k, v in obj.items():
            if len(out) >= MAX_KEYS:
                return
            if not isinstance(k, str) or not _IDENT.match(k):
                continue
            q = f"{prefix}.{k}" if prefix else k
            out.append((q, line_of(k)))
            if isinstance(v, dict) and depth < MAX_DEPTH:
                walk(v, q, depth + 1)

    if isinstance(data, dict):
        walk(data, "", 1)
    return out


_MISSING = object()


def value(source: str | None, qualname: str):
    data = _load(source)
    for part in qualname.split("."):
        if not isinstance(data, dict) or part not in data:
            return _MISSING
        data = data[part]
    return data


def parses(source: str | None) -> bool:
    return _load(source) is not None


def member_hash(source: str | None, qualname: str) -> str | None:
    v = value(source, qualname)
    if v is _MISSING:
        return None
    return hashlib.sha256(json.dumps(v, sort_keys=True, separators=(",", ":")).encode()).hexdigest()[:16]


def symbol_source(source: str | None, qualname: str) -> str | None:
    v = value(source, qualname)
    if v is _MISSING:
        return None
    s = json.dumps(v, sort_keys=True)
    return f"{qualname}: {s if len(s) <= 200 else s[:197] + '...'}"
