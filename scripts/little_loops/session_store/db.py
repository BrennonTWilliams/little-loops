"""DB path resolution for the session store (ENH-2890 split from session_store.py).

Resolves the on-disk location of ``.ll/history.db`` via the unified
env → config → explicit/default precedence chain (ENH-2623). Deliberately has
no dependency on :mod:`little_loops.session_store.schema` — ``schema.py``
depends on this module (for ``ensure_db``/``connect``), not the reverse.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

DEFAULT_DB_PATH = Path(".ll/history.db")


def _is_default_shaped(path: Path | str | None) -> bool:
    """True when *path* names the default DB location (ENH-2623).

    Default-shaped means ``None``, ``DEFAULT_DB_PATH``, or a ``history.db`` under
    a ``.ll/`` directory (matched by basename + parent, not strict equality — so
    the cwd-*absolute* ``.ll/history.db`` that hooks construct still routes
    through the env → config → default chain). Any other path is a deliberate
    override and is returned verbatim by :func:`_resolve_db_path`.
    """
    if path is None:
        return True
    p = Path(path)
    if p == DEFAULT_DB_PATH:
        return True
    return p.name == "history.db" and p.parent.name == ".ll"


def _config_db_path(*, root: Path | None = None) -> Path | None:
    """Best-effort read of ``history.db_path`` from the project config (ENH-2623).

    Returns the configured path (relative paths resolved against the
    resolved project root — see :func:`~little_loops.paths.resolve_ll_dir`,
    ENH-2927 — rather than the bare current working directory), or ``None``
    when the key is unset, no project root resolves, or the config is
    missing/malformed. Never raises — mirroring the guarded
    ``resolve_config_path`` + ``json.loads`` pattern the bootstrap hooks
    use — so the hot ``SessionStart`` / ``UserPromptSubmit`` path is never
    blocked by a bad config file.

    BUG-3181: *root* seeds the upward walk that finds the project. Omitted, it
    starts at ``Path.cwd()`` as before — which is only correct for a process
    already running inside the project it is answering about.
    """
    try:
        from little_loops.config.core import resolve_config_path
        from little_loops.paths import resolve_ll_dir

        ll_dir = resolve_ll_dir(start=root)
        if ll_dir is None:
            return None
        root = ll_dir.parent
        cfg_path = resolve_config_path(root)
        if cfg_path is None:
            return None
        data = json.loads(cfg_path.read_text(encoding="utf-8"))
        raw = (data.get("history") or {}).get("db_path")
        if not raw:
            return None
        p = Path(raw)
        return p if p.is_absolute() else root / p
    except (OSError, json.JSONDecodeError, ValueError, TypeError, AttributeError):
        return None


def _resolve_db_path(path: Path | str | None = None, *, root: Path | None = None) -> Path:
    """Unified DB-path resolution (ENH-2623): env → config → explicit/default.

    Precedence for a *default-shaped* *path* (see :func:`_is_default_shaped`):

    1. ``LL_HISTORY_DB`` env var — unconditional ephemeral override.
    2. ``history.db_path`` config key — persistent per-project setting.
    3. the explicit *path* argument, or ``DEFAULT_DB_PATH`` when ``None``.

    A deliberate (non-default-shaped) override path is returned verbatim, so
    callers that hand an explicit location (recompress maintenance, tests) are
    always honored — resolving the historical ``resolve_history_db`` /
    ``ensure_db`` divergence into one rule.

    For a default-shaped *path* with no env override and no config key, the
    default now anchors at the resolved project root (ENH-2927) instead of a
    bare cwd-relative ``DEFAULT_DB_PATH`` — the exact rerouting that stops
    ``ll-doctor``/``ll-ctx-stats``/``ll-gitignore`` from creating stray
    ``.ll/`` directories when invoked from a project subdirectory. When no
    project root resolves at all (no ``.git`` boundary, no ``.ll`` anywhere
    upward), this falls back to a cwd-*absolute* form of the legacy default
    (``Path.cwd() / DEFAULT_DB_PATH``) rather than inventing a root — same
    on-disk location as the old bare-relative default, just resolved eagerly
    instead of left for the sqlite layer to interpret relative to whatever
    cwd happens to be at connect-time.

    BUG-3181: "the resolved project root" above means *root*'s project when a
    caller supplies one, and cwd's otherwise. Passing a default-shaped *path*
    under some other root does **not** select that root — the path is discarded
    by design (that is what makes it default-shaped), so a caller that knows its
    root must say so here. `ll-mcp`, whose root arrives as `--project-root` and
    may be nowhere near cwd, is the caller that needs it.
    """
    if not _is_default_shaped(path):
        return Path(path)  # type: ignore[arg-type]
    env_val = os.environ.get("LL_HISTORY_DB")
    if env_val:
        return Path(env_val)
    cfg = _config_db_path(root=root)
    if cfg is not None:
        return cfg
    from little_loops.paths import resolve_ll_dir

    ll_dir = resolve_ll_dir(start=root)
    if ll_dir is not None:
        return ll_dir / "history.db"
    return (root or Path.cwd()) / DEFAULT_DB_PATH


def resolve_history_db(path: Path | str | None = None, *, root: Path | None = None) -> Path:
    """Return the DB path via the unified env → config → default chain (ENH-2623).

    ``LL_HISTORY_DB`` takes precedence, then the ``history.db_path`` config key,
    then the explicit *path* / ``DEFAULT_DB_PATH`` — but only for a default-shaped
    *path*; a deliberate override is returned verbatim. Delegates to
    :func:`_resolve_db_path` so this and :func:`ensure_db` never diverge.

    *root* (BUG-3181) anchors the config lookup and the default at a known project
    root instead of walking up from ``Path.cwd()``; omitted, behavior is unchanged.
    """
    return _resolve_db_path(path, root=root)
