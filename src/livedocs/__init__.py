"""livedocs: a thin wrapper over drift that binds notes to code and tells agents when a note is out of date."""

try:
    from importlib.metadata import version as _version

    __version__ = _version("livedocs")
except Exception:  # pragma: no cover - running from a source tree without metadata
    __version__ = "0+unknown"
