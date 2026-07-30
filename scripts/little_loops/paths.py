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


def resolve_ll_dir(start: Path | None = None, create: bool = False) -> Path | None:
    """Return the resolved project's ``.ll/`` directory, optionally creating it.

    Delegates upward resolution to :func:`find_project_root`, starting from
    *start* (``Path.cwd()`` when omitted). Sole authority for *creating*
    ``.ll/`` outside of ``ll-init`` itself (ENH-2927) — every other consumer
    (session store, hook state files, decisions log, queue DB) should resolve
    through this function rather than building ``Path(".ll/...")`` against a
    bare cwd, which is what let stray ``.ll/`` directories accumulate outside
    the project root.

    When ``create`` is False (the default), this is a pure lookup: mirrors
    :func:`~little_loops.config.core.resolve_config_path`'s contract of never
    creating directories or mutating global state. Returns ``<root>/.ll`` when
    ``find_project_root`` resolves a root (which itself requires an existing
    ``.ll`` somewhere on the walk), or ``None`` when no root resolves.

    When ``create`` is True and a root resolves, ensures ``<root>/.ll`` exists
    (``mkdir(parents=True, exist_ok=True)``) and returns it. When ``create``
    is True but no root resolves at all — no ``.git`` boundary and no
    existing ``.ll`` anywhere upward — this still returns ``None`` rather than
    inventing a root at *start*; callers that want to originate a brand-new
    project (``ll-init``) must choose an explicit root themselves instead of
    relying on this helper to guess one.

    Never raises: an ``OSError`` from the ``mkdir`` call (e.g. a read-only
    filesystem) is swallowed and ``None`` is returned, matching the
    never-raise contract the rest of this module follows.
    """
    root = find_project_root(start if start is not None else Path.cwd())
    if root is None:
        return None
    ll_dir = root / ".ll"
    if create:
        try:
            ll_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            return None
    return ll_dir
