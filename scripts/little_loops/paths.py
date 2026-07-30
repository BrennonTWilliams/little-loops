"""Project-root resolution — dependency-free core, shared by issue and session layers.

Relocated from ``little_loops.issues.program_design`` (ENH-2924) so lower layers
(``session_store``, hook state files, the queue DB) can resolve a project root without
pulling in issue-parsing imports. ``little_loops.issues.program_design`` re-exports
``find_project_root`` for backward compatibility.
"""

from __future__ import annotations

from pathlib import Path


def find_project_root(start: Path) -> Path | None:
    """Return the project root for *start*, preferring a ``.git`` ancestor.

    Walks ``start`` and its parents nearest-out. A candidate with both ``.ll`` and
    ``.git`` wins outright. Absent that, the nearest ``.ll``-only candidate seen
    during the walk is returned as a fallback — but only if it was found at or
    below the repository boundary: the walk stops considering further candidates
    once it passes one with a ``.git`` (a fallback ``.ll`` seen above that point,
    e.g. ``~/.ll``, is never returned). ``.git`` is checked with ``.exists()``, not
    ``.is_dir()``, since worktrees and submodules use a ``.git`` file. Non-git
    projects keep plain nearest-``.ll`` semantics. Never raises; ``OSError`` on
    ``start.resolve()`` returns ``None``.
    """
    try:
        current = start.resolve()
    except OSError:
        return None

    fallback: Path | None = None
    for candidate in (current, *current.parents):
        has_ll = (candidate / ".ll").is_dir()
        has_git = (candidate / ".git").exists()
        if has_ll and has_git:
            return candidate
        if has_ll and fallback is None:
            fallback = candidate
        if has_git:
            break
    return fallback
