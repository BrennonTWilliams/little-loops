"""``<template>.llat.lock`` format (FEAT-3310 / FEAT-3311).

Single home for the lockfile's shape: this issue's ``cmd_refresh`` is the
first writer; FEAT-3311's ``status`` reader and ``render --source`` writer
import this module rather than redefining the format. FEAT-3311
§ Expected Behavior is the authoritative spec for the format — this module
implements it.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any

import yaml

LOCKFILE_VERSION = 1


class LockfileError(ValueError):
    """Raised when a ``<template>.llat.lock`` fails validation."""


def lock_path_for(root: Path) -> Path:
    """Return the lockfile path for a ``.llat/`` template root."""
    return root.parent / f"{root.name}.lock"


def relativize_path(path: Path, project_root: Path) -> str:
    """Store *path* project-root-relative (POSIX separators) when inside *project_root*.

    Stores the absolute path verbatim otherwise. Never returns a
    ``..``-prefixed relative path — the single path-storage rule shared by
    every writer of a lockfile ``renders`` key/``output`` value and of
    ``manifest.source``.
    """
    resolved = path.resolve()
    root = project_root.resolve()
    try:
        rel = resolved.relative_to(root)
    except ValueError:
        return str(resolved)
    return rel.as_posix()


def resolve_stored_path(stored: str, project_root: Path) -> Path:
    """Invert ``relativize_path``: an absolute key is used as-is, a relative key

    resolves against *project_root* — never against cwd.
    """
    candidate = Path(stored)
    if candidate.is_absolute():
        return candidate
    return project_root / candidate


def load_lockfile(path: Path) -> dict[str, Any]:
    """Load and validate a lockfile, fail-closed.

    Returns ``{"version": 1, "renders": {}}`` if *path* does not exist yet
    (there is nothing to fail closed on — the file simply hasn't been
    written). Raises LockfileError on unparseable YAML, a non-mapping
    top-level document, a missing/non-mapping ``renders`` key, or an
    unknown ``version``.
    """
    if not path.is_file():
        return {"version": LOCKFILE_VERSION, "renders": {}}

    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise LockfileError(f"{path}: invalid YAML: {exc}") from exc

    if not isinstance(data, dict):
        raise LockfileError(f"{path}: expected a top-level mapping")

    if data.get("version") != LOCKFILE_VERSION:
        raise LockfileError(f"{path}: unknown lockfile version {data.get('version')!r}")

    renders = data.get("renders")
    if not isinstance(renders, dict):
        raise LockfileError(f"{path}: 'renders' must be a mapping")

    return data


def write_lockfile(path: Path, entries: dict[str, dict[str, Any]]) -> None:
    """Atomically merge *entries* into the lockfile at *path*.

    *entries* maps a (already-relativized) source key to its ``renders``
    sub-mapping (``sha256``, ``rendered_at``, ``output``). Entries for
    other sources already present in the lockfile are preserved
    (EPIC-3299's one-template-many-sources case). The write goes to a
    sibling temp file, then ``os.replace`` — mirroring ``templatize.py``'s
    tmp-dir-then-swap discipline — so an interrupted write cannot leave a
    truncated lockfile.
    """
    existing = load_lockfile(path)
    renders = dict(existing.get("renders", {}))
    renders.update(entries)
    payload = {"version": LOCKFILE_VERSION, "renders": renders}

    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f"{path.name}.tmp-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(yaml.safe_dump(payload, sort_keys=False, allow_unicode=True))
        os.replace(tmp_name, path)
    except Exception:
        Path(tmp_name).unlink(missing_ok=True)
        raise
