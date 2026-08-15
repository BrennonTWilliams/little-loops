"""Cheap staleness signal shared by `resources.py` and `prompts.py` (ENH-3172).

A directory's own mtime changes when an entry is added, removed, or renamed directly
inside it — exactly the staleness the resource/prompt indices care about, since they
re-enumerate from scratch on every rebuild rather than caching file bodies. An edit to
an already-known file's *contents* doesn't need to be detected here: `resources/read`
and `prompts/get` already read bodies fresh on every call, only the `uri`/`name` -> path
mapping is what goes stale.

This intentionally does not `rglob` for nested changes (e.g. a new `docs/foo/bar.md` in
an existing subdirectory, or a new `SKILL.md` two levels under `skills/`) — that would
make every request pay a full recursive walk just to decide whether to *do* the walk.
The signal is the top-level directory mtime only, per this issue's own scoping (Option 1).
"""

from __future__ import annotations

from pathlib import Path

Signature = tuple[tuple[str, float | None], ...]


def dir_signature(paths: list[Path]) -> Signature:
    """A comparable snapshot of each path's mtime (`None` if it doesn't exist)."""
    signature: list[tuple[str, float | None]] = []
    for path in paths:
        try:
            signature.append((str(path), path.stat().st_mtime))
        except OSError:
            signature.append((str(path), None))
    return tuple(signature)
