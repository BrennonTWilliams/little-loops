"""Workspace membership discovery for cross-repo history.db aggregation (FEAT-3409).

Parses an ``ll-workspace.yaml`` manifest naming member repos by path with a role
apiece into a `WorkspaceMember` list. FEAT-3410's ATTACH-based aggregation is the
sole intended consumer: it iterates the returned members to build one
``ATTACH DATABASE`` call per member. Hand-parsed with ``yaml.safe_load()``
following ``decisions.py::load_decisions()``'s dispatch-model precedent — no
schema-validator dependency (none of this codebase's other YAML manifests use
one).

No caller-supplied manifest exists anywhere in a project by default; absence is
the common case and must degrade cleanly to ``[]`` so a project with no declared
workspace falls back to single-repo behavior byte-for-byte. A manifest path that
*was* declared (explicit argument or the ``history.workspace_manifest_path``
config key) but does not exist on disk is treated differently: it raises
``FileNotFoundError`` rather than degrading, since a typo there would otherwise
silently look identical to "no workspace declared".
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

MANIFEST_FILENAME = "ll-workspace.yaml"


@dataclass(frozen=True)
class WorkspaceMember:
    """One repo in a declared workspace.

    ``repo_path`` and ``db_path`` are always absolute and resolved (symlinks
    followed), regardless of how they were spelled in the manifest. Frozen
    because this value crosses the producer (this module) / consumer
    (FEAT-3410) boundary — the convention ``host_runner.HostInvocation``
    establishes for new value objects of this shape.
    """

    repo_path: Path
    role: str
    db_path: Path


@dataclass(frozen=True)
class _ResolvedManifest:
    """A resolved manifest path plus whether it was explicitly declared.

    ``declared`` is ``True`` when *path* came from the explicit
    ``manifest_path`` argument or the ``history.workspace_manifest_path``
    config key, and ``False`` when it came from the nearest-ancestor walk.
    Only an undeclared miss degrades to ``[]``; a declared miss raises.
    """

    path: Path
    declared: bool


def _find_manifest_upward(start: Path) -> Path | None:
    """Return the first ``<dir>/ll-workspace.yaml`` found in *start* or a parent.

    *start* must already be resolved. Walks *start* itself, then each parent,
    nearest first.
    """
    for candidate in (start, *start.parents):
        manifest = candidate / MANIFEST_FILENAME
        if manifest.exists():
            return manifest
    return None


def _config_manifest_path(root: Path | None) -> Path | None:
    """Read ``history.workspace_manifest_path`` from *root*'s project config.

    Returns ``None`` when *root* is ``None`` (no project root resolved) or the
    key is unset. Relative values resolve against *root*; ``~`` is expanded —
    a deliberate divergence from ``history.db_path``'s reader, which does not
    expand ``~`` (a machine-local manifest path is the expected home for a
    ``~``-path here). Reads through ``BRConfig`` rather than raw JSON so a
    ``.ll/ll.local.md`` override of the key is honored (BUG-3123); this means
    constructing a ``BRConfig`` also runs ``load_env_fallback()`` for *root*,
    the same side effect every ``ll-*`` CLI already incurs. The import is
    lazy, mirroring ``design_tokens.py``, to keep import cost low for callers
    that pass an explicit ``manifest_path`` and never need config at all.
    """
    if root is None:
        return None

    from little_loops.config.core import BRConfig

    raw = BRConfig(root).history.workspace_manifest_path
    if not raw:
        return None

    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = root / path
    return path


def _resolve_manifest_path(manifest_path: Path | None, start: Path) -> _ResolvedManifest:
    """Resolve the manifest path: explicit arg -> config key -> ancestor walk.

    *start* must already be resolved (``discover_workspace_members`` does
    this once, up front, and seeds both the config-root lookup and the
    ancestor walk with it).
    """
    if manifest_path is not None:
        return _ResolvedManifest(path=manifest_path.expanduser().resolve(), declared=True)

    from little_loops.paths import find_project_root

    root = find_project_root(start)
    config_path = _config_manifest_path(root)
    if config_path is not None:
        return _ResolvedManifest(path=config_path.resolve(), declared=True)

    found = _find_manifest_upward(start)
    if found is not None:
        return _ResolvedManifest(path=found, declared=False)
    return _ResolvedManifest(path=start / MANIFEST_FILENAME, declared=False)


def _member_from_entry(entry: Any, manifest_dir: Path) -> WorkspaceMember:
    """Build one `WorkspaceMember` from a manifest entry, no-wrap/propagate on error.

    A missing ``repo``/``role`` key raises ``KeyError`` (bare dict indexing,
    mirroring ``decisions.py``); a non-mapping entry, or a non-string/empty
    ``repo``/``role``, or a present non-string ``db_path``, raises
    ``ValueError``.
    """
    if not isinstance(entry, dict):
        raise ValueError(f"ll-workspace.yaml member entry must be a mapping, got {entry!r}")

    repo_raw = entry["repo"]
    role = entry["role"]
    if not isinstance(repo_raw, str) or not repo_raw:
        raise ValueError(
            f"ll-workspace.yaml member 'repo' must be a non-empty string, got {repo_raw!r}"
        )
    if not isinstance(role, str) or not role:
        raise ValueError(
            f"ll-workspace.yaml member 'role' must be a non-empty string, got {role!r}"
        )

    repo_path = (manifest_dir / Path(repo_raw).expanduser()).resolve()

    db_path_raw = entry.get("db_path")
    if db_path_raw:
        if not isinstance(db_path_raw, str):
            raise ValueError(
                f"ll-workspace.yaml member 'db_path' must be a string, got {db_path_raw!r}"
            )
        db_path = (repo_path / Path(db_path_raw).expanduser()).resolve()
    else:
        db_path = (repo_path / ".ll" / "history.db").resolve()

    return WorkspaceMember(repo_path=repo_path, role=role, db_path=db_path)


def discover_workspace_members(
    manifest_path: Path | None = None, *, start: Path | None = None
) -> list[WorkspaceMember]:
    """Parse ``ll-workspace.yaml`` into a list of `WorkspaceMember` rows.

    Manifest path resolution, highest precedence first:

    1. Explicit *manifest_path* — normalized with ``.expanduser().resolve()``
       before use (not returned verbatim).
    2. ``history.workspace_manifest_path`` from the project config rooted at
       ``find_project_root(start)`` — see `_config_manifest_path`.
    3. The nearest ancestor of *start* (itself, then each parent) containing
       ``ll-workspace.yaml``.

    *start* (default ``Path.cwd()``) seeds steps 2 and 3; step 1 ignores it.

    A manifest resolved via step 1 or 2 ("declared") that does not exist
    raises ``FileNotFoundError`` naming the path and its provenance — a typo
    there must not silently look like "no workspace declared". A manifest
    resolved via step 3 ("discovered") that does not exist returns ``[]``
    (never ``None``), so a project with no workspace manifest falls back to
    single-repo behavior byte-for-byte.

    A present-but-malformed manifest is not wrapped: bad YAML syntax raises
    ``yaml.YAMLError`` unmodified; a missing ``repo``/``role`` key raises
    ``KeyError``; a non-mapping top level, a missing/non-list ``members``, a
    non-mapping entry, a non-string/empty ``repo``/``role``, or a present
    non-string ``db_path`` raises ``ValueError``.

    Per entry: ``repo`` resolves against the manifest's parent directory;
    ``db_path`` (optional) resolves against *that entry's* resolved
    ``repo_path`` — not the manifest directory — defaulting to
    ``(repo_path / ".ll" / "history.db").resolve()`` via a plain `Path` join,
    never ``resolve_history_db()`` (its unconditional ``LL_HISTORY_DB``
    env-var check would collapse every member's ``db_path`` onto the same
    value). The default is ``.resolve()``d exactly like an explicit
    ``db_path`` so two entries aliasing one database through a symlink still
    collide. ``repo`` and ``db_path`` are passed through
    ``Path.expanduser()`` so ``~`` works in a gitignored, machine-local
    manifest. Two entries whose resolved ``db_path`` collide raise
    ``ValueError`` naming the path (FEAT-3410 would otherwise ``ATTACH`` one
    database twice). A member's own ``history.db_path`` config key is never
    consulted — a member with a custom one must repeat it in the manifest.

    No existence check is performed on ``repo_path`` or ``db_path``;
    FEAT-3410 owns skip-and-report for a missing or schema-skewed member
    database.
    """
    resolved_start = (start or Path.cwd()).resolve()
    resolved = _resolve_manifest_path(manifest_path, resolved_start)

    if not resolved.path.exists():
        if resolved.declared:
            provenance = (
                "explicit manifest_path"
                if manifest_path is not None
                else "history.workspace_manifest_path"
            )
            raise FileNotFoundError(f"Workspace manifest not found ({provenance}): {resolved.path}")
        return []

    data = yaml.safe_load(resolved.path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("members"), list):
        raise ValueError(
            f"{resolved.path}: ll-workspace.yaml must be a mapping with a 'members' list"
        )

    manifest_dir = resolved.path.parent
    members = [_member_from_entry(entry, manifest_dir) for entry in data["members"]]

    seen_db_paths: set[Path] = set()
    for member in members:
        if member.db_path in seen_db_paths:
            raise ValueError(f"Duplicate workspace member db_path: {member.db_path}")
        seen_db_paths.add(member.db_path)

    return members
