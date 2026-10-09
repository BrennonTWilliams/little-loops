"""Configured scan scope and scoped-activity evidence for ``capture-issues`` (FEAT-3713).

``collect_scan_domain`` captures, once at the CLI boundary, the effective ``scan.focus_dirs`` /
``scan.exclude_patterns`` scope (canonicalized, with the existence and symlink checks that are
the only filesystem reads) and -- only when that scope is usable -- the batched scoped-commit
activity from :mod:`~little_loops.next_arena.scan_activity`. The pure generator
(:mod:`~little_loops.next_arena.scan_candidates`) consumes the resulting :class:`ScanDomain`
and never reads git, config, the clock or live files.

Scope rules:

* Directory entries are normalized lexically (separators, harmless ``.`` segments, trailing
  slashes) to project-relative POSIX paths; ``..`` that leaves the project or an absolute path
  outside it is *invalid*; duplicates collapse and the result is sorted so equivalent scopes
  hash identically. Exclusion patterns keep their matching text and are only deduplicated and
  sorted.
* An entry is *eligible* only when it names an existing directory below the resolved project
  root and no component of its path (intermediate ones included) is a symlink: Git emits
  physical paths, so an alias cannot be translated without changing exclusion meaning. A
  symlink anywhere vetoes the **whole** scope (``symlink_scope_unsupported``), as does any
  invalid entry; a merely missing entry is dropped with a diagnostic while at least one
  eligible directory remains.
* Matching uses :func:`~little_loops.git_operations.file_matches_pattern` in its
  ``literal_path`` mode, so a literal backslash or newline in a Git filename is never read as
  a separator, plus a separator-anchored directory prefix (``src`` never matches ``src-extra``).
"""

from __future__ import annotations

import posixpath
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from little_loops.git_operations import file_matches_pattern
from little_loops.next_arena.actions import SCAN_TARGET, scan_scope_hash
from little_loops.next_arena.inputs import Diagnostic, sort_diagnostics

if TYPE_CHECKING:
    from little_loops.config import BRConfig
    from little_loops.next_arena.registry import ArenaSettings
    from little_loops.next_arena.scan_activity import Clock, PopenFactory, ScanActivity

__all__ = [
    "DIR_INVALID",
    "DIR_MISSING",
    "DIR_NOT_DIRECTORY",
    "DIR_OK",
    "DIR_SYMLINK",
    "SCAN_SUBJECT",
    "ScanDirectory",
    "ScanDomain",
    "ScanScope",
    "canonical_exclude_patterns",
    "collect_scan_domain",
    "normalize_scan_dir",
    "resolve_scan_scope",
]

#: Diagnostic subject of every scan finding (``scope_subject("capture-issues", "project")``).
SCAN_SUBJECT = f"scan:{SCAN_TARGET}"

DIR_OK = "ok"
DIR_MISSING = "missing"
DIR_NOT_DIRECTORY = "not_directory"
DIR_SYMLINK = "symlink"
DIR_INVALID = "invalid"

# Scope-level failure codes (gate ``scope`` reasons).
SCOPE_EMPTY = "scope_empty"
SCOPE_INVALID = "scope_invalid"
SCOPE_SYMLINK = "symlink_scope_unsupported"
SCOPE_NO_DIRECTORY = "scope_no_existing_directory"


@dataclass(frozen=True)
class ScanDirectory:
    """One configured focus-directory entry and its eligibility.

    ``normalized`` is the project-relative POSIX path (``"."`` for the project root) or
    ``None`` when the configured text is invalid; ``status`` is one of the ``DIR_*`` values.
    """

    configured: str
    normalized: str | None
    status: str
    detail: str

    def to_dict(self) -> dict[str, str | None]:
        """JSON-ready mapping."""
        return {
            "configured": self.configured,
            "normalized": self.normalized,
            "status": self.status,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class ScanScope:
    """The effective, canonicalized scan scope as captured (immutable)."""

    directories: tuple[ScanDirectory, ...]
    exclude_patterns: tuple[str, ...]
    diagnostics: tuple[Diagnostic, ...] = ()

    @property
    def focus_dirs(self) -> tuple[str, ...]:
        """Sorted, deduplicated eligible directories -- the offered ``focus_dirs``."""
        return tuple(
            sorted({d.normalized for d in self.directories if d.status == DIR_OK and d.normalized})
        )

    @property
    def declared_dirs(self) -> tuple[str, ...]:
        """Sorted, deduplicated syntactically valid directories (eligible or not)."""
        return tuple(sorted({d.normalized for d in self.directories if d.normalized}))

    @property
    def failure(self) -> tuple[str, str] | None:
        """``(code, detail)`` when the scope cannot be offered, else ``None``."""
        if not self.directories:
            return SCOPE_EMPTY, "scan.focus_dirs is empty; configure at least one directory"
        symlinks = [d for d in self.directories if d.status == DIR_SYMLINK]
        if symlinks:
            names = ", ".join(repr(d.configured) for d in symlinks)
            return (
                SCOPE_SYMLINK,
                f"focus director{'y' if len(symlinks) == 1 else 'ies'} {names} traverse"
                f"{'s' if len(symlinks) == 1 else ''} a directory symlink; Git reports physical "
                "paths, so alias scopes are unsupported in v1 (configure the physical directory)",
            )
        invalid = [d for d in self.directories if d.status == DIR_INVALID]
        if invalid:
            return SCOPE_INVALID, "; ".join(f"{d.configured!r}: {d.detail}" for d in invalid)
        if not self.focus_dirs:
            return (
                SCOPE_NO_DIRECTORY,
                "no configured focus directory exists below the project root",
            )
        return None

    @property
    def target_key_dirs(self) -> tuple[str, ...]:
        """Directories hashed into the ``scan:SCOPE_HASH`` target (offered scope when usable)."""
        return self.focus_dirs if self.failure is None else self.declared_dirs

    @property
    def scope_hash(self) -> str:
        """Full SHA-256 hex of the canonical scope JSON (``scan:`` target suffix)."""
        return scan_scope_hash(self.target_key_dirs, self.exclude_patterns)

    def contains(self, git_path: str) -> bool:
        """True when the literal Git-emitted *git_path* is in scope (dirs, then exclusions)."""
        return path_in_scope(git_path, self.focus_dirs, self.exclude_patterns)

    def to_dict(self) -> dict[str, object]:
        """JSON-ready scope description for evidence."""
        return {
            "focus_dirs": list(self.focus_dirs),
            "exclude_patterns": list(self.exclude_patterns),
            "configured_directories": [d.to_dict() for d in self.directories],
            "scope_hash": self.scope_hash,
        }


def path_in_scope(
    git_path: str, focus_dirs: Sequence[str], exclude_patterns: Sequence[str]
) -> bool:
    """Scope predicate for one literal, project-relative Git path.

    Reuses the pure ``codequery.codegraph._is_scan_relevant`` policy (exclusions first, then a
    separator-anchored directory prefix; ``"."`` is the whole project) with two deliberate
    differences: the Git path is matched **literally** (no backslash conversion), and an empty
    *focus_dirs* is an empty scope (nothing matches) rather than the codegraph's unrestricted
    default.
    """
    if not focus_dirs:
        return False
    if any(file_matches_pattern(git_path, p, literal_path=True) for p in exclude_patterns):
        return False
    for directory in focus_dirs:
        if directory == ".":
            return True
        if git_path == directory or git_path.startswith(directory + "/"):
            return True
    return False


def normalize_scan_dir(value: object, project_root: Path) -> tuple[str | None, str]:
    """Normalize one configured focus directory to ``(path, "")`` or ``(None, reason)``.

    Purely lexical: no filesystem access. The root spellings (``.``, ``./``, ``/``) are the
    whole project (``"."``); an absolute path is accepted only inside *project_root*.
    """
    if not isinstance(value, str):
        return None, f"not a string ({type(value).__name__})"
    text = value.strip()
    if not text or "\x00" in text:
        return None, "empty or contains NUL"
    text = text.replace("\\", "/")
    root = project_root.as_posix().rstrip("/")
    if text.startswith("/") and text.rstrip("/") not in ("",):
        normal = posixpath.normpath(text)
        if normal == root:
            return ".", ""
        if not normal.startswith(root + "/"):
            return None, "absolute path outside the project root"
        text = normal[len(root) + 1 :]
    elif text.startswith("/"):
        return ".", ""  # "/" is the root spelling used by canonical_dir
    normal = posixpath.normpath(text)
    if normal == ".." or normal.startswith("../"):
        return None, "path escapes the project root"
    return normal, ""


def canonical_exclude_patterns(
    patterns: Sequence[object],
) -> tuple[tuple[str, ...], tuple[Diagnostic, ...]]:
    """Deduplicated, sorted exclusion patterns plus diagnostics for dropped entries."""
    kept: set[str] = set()
    diagnostics: list[Diagnostic] = []
    for pattern in patterns:
        if isinstance(pattern, str) and pattern and "\x00" not in pattern:
            kept.add(pattern)
        else:
            diagnostics.append(
                Diagnostic(
                    "scan_exclude_ignored",
                    f"scan.exclude_patterns entry {pattern!r} is not a nonempty string; ignored",
                    (),
                    SCAN_SUBJECT,
                )
            )
    return tuple(sorted(kept)), tuple(diagnostics)


def _directory_status(root: Path, normalized: str) -> tuple[str, str]:
    """Filesystem eligibility of *normalized* below *root* (symlinks anywhere on the path)."""
    current = root
    if normalized != ".":
        for part in normalized.split("/"):
            current = current / part
            if current.is_symlink():
                return DIR_SYMLINK, f"{current.relative_to(root).as_posix()} is a symlink"
    if not current.exists():
        return DIR_MISSING, "directory does not exist"
    if not current.is_dir():
        return DIR_NOT_DIRECTORY, "not a directory"
    return DIR_OK, ""


def resolve_scan_scope(
    focus_dirs: Sequence[object], exclude_patterns: Sequence[object], project_root: Path
) -> ScanScope:
    """Canonicalize the configured scope against *project_root* (the only filesystem reads)."""
    root = project_root.resolve()
    directories: list[ScanDirectory] = []
    diagnostics: list[Diagnostic] = []
    seen: set[str] = set()
    for raw in focus_dirs:
        configured = raw if isinstance(raw, str) else repr(raw)
        normalized, reason = normalize_scan_dir(raw, root)
        if normalized is None:
            directories.append(ScanDirectory(configured, None, DIR_INVALID, reason))
            diagnostics.append(
                Diagnostic(
                    "scan_dir_invalid",
                    f"scan.focus_dirs entry {configured!r} is invalid: {reason}",
                    (),
                    SCAN_SUBJECT,
                )
            )
            continue
        if normalized in seen:
            continue  # equivalent spellings collapse; the first spelling is kept
        seen.add(normalized)
        status, detail = _directory_status(root, normalized)
        directories.append(ScanDirectory(configured, normalized, status, detail))
        if status != DIR_OK:
            code = "scan_dir_symlink" if status == DIR_SYMLINK else "scan_dir_missing"
            diagnostics.append(
                Diagnostic(
                    code,
                    f"scan.focus_dirs entry {configured!r} ({normalized}) is not eligible: {detail}",
                    (),
                    SCAN_SUBJECT,
                )
            )
    patterns, pattern_diagnostics = canonical_exclude_patterns(exclude_patterns)
    return ScanScope(
        directories=tuple(directories),
        exclude_patterns=patterns,
        diagnostics=sort_diagnostics([*diagnostics, *pattern_diagnostics]),
    )


@dataclass(frozen=True)
class ScanDomain:
    """Captured scan evidence in :class:`~little_loops.next_arena.state.ProjectState`.

    ``activity`` is ``None`` when the scope is unusable (no git call is made then).
    """

    scope: ScanScope
    activity: ScanActivity | None
    diagnostics: tuple[Diagnostic, ...] = ()


def collect_scan_domain(
    project_root: Path,
    *,
    config: BRConfig,
    as_of: datetime,
    settings: ArenaSettings,
    popen: PopenFactory | None = None,
    clock: Clock | None = None,
) -> ScanDomain:
    """Capture the scan scope and, when usable, its scoped commit activity (at most 2 git calls).

    *popen* / *clock* are test seams forwarded to the activity loader.
    """
    from little_loops.next_arena.scan_activity import load_scope_activity

    scope = resolve_scan_scope(config.scan.focus_dirs, config.scan.exclude_patterns, project_root)
    activity = None
    if scope.failure is None:
        kwargs: dict[str, Any] = {}
        if popen is not None:
            kwargs["popen"] = popen
        if clock is not None:
            kwargs["clock"] = clock
        activity = load_scope_activity(
            project_root.resolve(),
            scope,
            as_of=as_of,
            threshold=settings.activity_threshold,
            lookback_days=settings.activity_lookback_days,
            **kwargs,
        )
    return ScanDomain(scope=scope, activity=activity, diagnostics=scope.diagnostics)
