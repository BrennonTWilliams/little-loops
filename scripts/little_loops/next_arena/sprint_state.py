"""Captured sprint definitions and executor state evidence for ``run-sprint`` (FEAT-3713).

``collect_sprint_domain`` reads, once at the CLI boundary, every sprint definition in the
effective ``sprints.sprints_dir`` (resolved against the project root, which is where the emitted
``ll-sprint run -- NAME`` runs) through a **pure, read-only parser**:

* it never constructs :class:`~little_loops.sprint.SprintManager` (whose constructor creates the
  directory) and never calls :meth:`~little_loops.sprint.Sprint.from_dict` (which reads the clock
  for a missing ``created`` and trusts unchecked option values);
* each file's bytes are read **once**; the parsed document and the SHA-256 definition digest come
  from that same buffer, so the offered identity is exactly what was validated;
* validation is pinned here rather than inherited: the YAML root is a mapping whose declared
  ``name`` equals the file stem, ``issues`` is an array of full issue-ID strings (repeats are
  normalized, never edited in the YAML), and ``options`` is absent/null or a mapping whose
  supplied ``max_iterations``/``timeout``/``max_workers`` are positive integers (booleans,
  floats and numeric strings rejected; unknown keys are ignored by the runtime and only
  diagnosed). A malformed definition is excluded independently and keeps its bytes/digest for
  ``--explain``.

Only ``NAME.yaml`` is runnable by ``ll-sprint run``; ``NAME.yml`` is diagnosed, never offered.
Names matching ``^EPIC-\\d+$`` (case-insensitive) are rejected: ``SprintManager.load_or_resolve``
dispatches them to an ephemeral EPIC sprint before reading any YAML.

The executor's cwd-relative, single, sprint-unkeyed ``.sprint-state.json`` is read once as
evidence only (no process-liveness signal exists, so it is never a veto).
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml

from little_loops.next_arena.inputs import Diagnostic, sort_diagnostics

if TYPE_CHECKING:
    from little_loops.config import BRConfig

__all__ = [
    "DEFAULT_MAX_ITERATIONS",
    "DEFAULT_MAX_WORKERS",
    "DEFAULT_TIMEOUT",
    "STATE_FILENAME",
    "SprintDefinition",
    "SprintDomain",
    "SprintOptionsRecord",
    "SprintStateEvidence",
    "collect_sprint_domain",
    "parse_sprint_definition",
    "sprint_history_names",
    "sprint_subject",
]

#: Runtime defaults of :class:`~little_loops.sprint.SprintOptions` (the arena never reads config
#: defaults as definition identity).
DEFAULT_MAX_ITERATIONS = 100
DEFAULT_TIMEOUT = 3600
DEFAULT_MAX_WORKERS = 2
#: ``<working_directory>/.sprint-state.json`` -- the executor's cwd-relative resume file.
STATE_FILENAME = ".sprint-state.json"

_EPIC_NAME_RE = re.compile(r"^EPIC-\d+$", re.IGNORECASE)
_ISSUE_ID_RE = re.compile(r"^[A-Z][A-Z0-9]*-\d+$")
_OPTION_KEYS = ("max_iterations", "timeout", "max_workers")

# Definition exclusion codes (gate ``definition`` reasons).
INVALID_ENCODING = "invalid_encoding"
INVALID_YAML = "invalid_yaml"
NOT_A_MAPPING = "definition_not_mapping"
NAME_MISMATCH = "name_mismatch"
RESERVED_NAME = "reserved_epic_name"
UNSUPPORTED_EXTENSION = "unsupported_extension"
INVALID_ISSUES = "invalid_issues"
INVALID_OPTIONS = "invalid_options"
UNREADABLE = "unreadable_definition"
OUTSIDE_PROJECT = "definition_source_outside_project"


def sprint_subject(name: str) -> str:
    """The diagnostic subject of sprint *name* (``sprint:NAME``)."""
    return f"sprint:{name}"


@dataclass(frozen=True)
class SprintOptionsRecord:
    """Effective option values (runtime defaults where omitted). Definition bytes only: just
    ``max_workers`` is consumed by the executor."""

    max_iterations: int = DEFAULT_MAX_ITERATIONS
    timeout: int = DEFAULT_TIMEOUT
    max_workers: int = DEFAULT_MAX_WORKERS

    def to_dict(self) -> dict[str, int]:
        """JSON-ready mapping."""
        return {
            "max_iterations": self.max_iterations,
            "timeout": self.timeout,
            "max_workers": self.max_workers,
        }


@dataclass(frozen=True)
class SprintDefinition:
    """One discovered sprint file, valid or not (``valid`` says whether it is assessable).

    ``members`` holds the distinct declared issue IDs in first-occurrence file order and
    ``repeated`` the IDs the file declares more than once (normalized, never edited).
    ``source`` is the normalized project-relative POSIX path of the YAML (``None`` when the
    configured directory is outside the project, which cannot supply a relative identity).
    """

    name: str
    path: Path
    source: str | None
    digest: str | None
    valid: bool
    exclusion: str | None
    exclusion_detail: str | None
    declared_name: Any
    description: str | None
    created_raw: Any
    members: tuple[str, ...]
    repeated: tuple[str, ...]
    options: SprintOptionsRecord
    ignored_option_keys: tuple[str, ...]
    diagnostics: tuple[Diagnostic, ...]


@dataclass(frozen=True)
class SprintStateEvidence:
    """The executor's ``.sprint-state.json`` as captured (``exists`` False when absent)."""

    path: str
    exists: bool
    sprint_name: str | None
    completed_issues: tuple[str, ...]
    error: str | None


@dataclass(frozen=True)
class SprintDomain:
    """Captured sprint evidence in :class:`~little_loops.next_arena.state.ProjectState`."""

    definitions: tuple[SprintDefinition, ...]
    state: SprintStateEvidence
    diagnostics: tuple[Diagnostic, ...] = ()


def _positive_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _exclusion(
    name: str,
    path: Path,
    source: str | None,
    digest: str | None,
    code: str,
    detail: str,
    *,
    declared_name: Any = None,
    diagnostics: list[Diagnostic] | None = None,
) -> SprintDefinition:
    notes = list(diagnostics or [])
    notes.append(
        Diagnostic(
            "sprint_definition_invalid", f"{name}: {code}: {detail}", (), sprint_subject(name)
        )
    )
    return SprintDefinition(
        name=name,
        path=path,
        source=source,
        digest=digest,
        valid=False,
        exclusion=code,
        exclusion_detail=detail,
        declared_name=declared_name,
        description=None,
        created_raw=None,
        members=(),
        repeated=(),
        options=SprintOptionsRecord(),
        ignored_option_keys=(),
        diagnostics=sort_diagnostics(notes),
    )


def parse_sprint_definition(
    name: str, path: Path, source: str | None, data: bytes, *, extension: str = ".yaml"
) -> SprintDefinition:
    """Parse one sprint definition from the **same buffer** its digest is computed over.

    Pure: no file access, clock or configuration. *name* is the file stem and *extension*
    the file's suffix (anything but ``.yaml`` is excluded).
    """
    digest = "sha256:" + hashlib.sha256(data).hexdigest()
    if extension != ".yaml":
        return _exclusion(
            name,
            path,
            source,
            digest,
            UNSUPPORTED_EXTENSION,
            f"{path.name}: ll-sprint run only loads NAME.yaml, so a {extension} definition "
            "cannot be run by name; rename it to .yaml",
        )
    if _EPIC_NAME_RE.match(name):
        return _exclusion(
            name,
            path,
            source,
            digest,
            RESERVED_NAME,
            f"{name!r} is dispatched to an ephemeral EPIC sprint by `ll-sprint run`, "
            "never to this file; rename the definition",
        )
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        return _exclusion(name, path, source, digest, INVALID_ENCODING, str(exc))
    try:
        document = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        return _exclusion(name, path, source, digest, INVALID_YAML, str(exc).splitlines()[0])
    if not isinstance(document, Mapping):
        return _exclusion(
            name,
            path,
            source,
            digest,
            NOT_A_MAPPING,
            f"the YAML root must be a mapping, got {type(document).__name__}",
        )
    declared = document.get("name")
    if not isinstance(declared, str) or declared != name:
        return _exclusion(
            name,
            path,
            source,
            digest,
            NAME_MISMATCH,
            f"declared name {declared!r} must be the string {name!r} (the file stem)",
            declared_name=declared,
        )

    notes: list[Diagnostic] = []
    issues = document.get("issues")
    if not isinstance(issues, list) or not all(
        isinstance(i, str) and _ISSUE_ID_RE.match(i) for i in issues
    ):
        return _exclusion(
            name,
            path,
            source,
            digest,
            INVALID_ISSUES,
            "`issues` must be an array of full issue-ID strings (e.g. FEAT-123); "
            f"got {_describe(issues)}",
            declared_name=declared,
        )
    distinct = tuple(dict.fromkeys(issues))
    repeated = tuple(i for i in distinct if issues.count(i) > 1)
    if repeated:
        notes.append(
            Diagnostic(
                "sprint_repeated_member",
                f"{name}: {', '.join(repeated)} declared more than once; counted once "
                "(the YAML is not edited)",
                (),
                sprint_subject(name),
            )
        )

    options = SprintOptionsRecord()
    ignored: tuple[str, ...] = ()
    raw_options = document.get("options")
    if raw_options is not None:
        if not isinstance(raw_options, Mapping):
            return _exclusion(
                name,
                path,
                source,
                digest,
                INVALID_OPTIONS,
                f"`options` must be absent, null or a mapping, got {type(raw_options).__name__}",
                declared_name=declared,
            )
        bad = [k for k in _OPTION_KEYS if k in raw_options and not _positive_int(raw_options[k])]
        if bad:
            return _exclusion(
                name,
                path,
                source,
                digest,
                INVALID_OPTIONS,
                "options must be positive integers: "
                + ", ".join(f"{k}={raw_options[k]!r}" for k in bad),
                declared_name=declared,
            )
        options = SprintOptionsRecord(
            max_iterations=raw_options.get("max_iterations", DEFAULT_MAX_ITERATIONS),
            timeout=raw_options.get("timeout", DEFAULT_TIMEOUT),
            max_workers=raw_options.get("max_workers", DEFAULT_MAX_WORKERS),
        )
        ignored = tuple(sorted(str(k) for k in raw_options if k not in _OPTION_KEYS))
        if ignored:
            notes.append(
                Diagnostic(
                    "sprint_option_ignored",
                    f"{name}: unknown option key(s) {', '.join(ignored)} are ignored by the "
                    "runtime",
                    (),
                    sprint_subject(name),
                )
            )
    description = document.get("description")
    created = document.get("created") if "created" in document else None
    return SprintDefinition(
        name=name,
        path=path,
        source=source,
        digest=digest,
        valid=True,
        exclusion=None,
        exclusion_detail=None,
        declared_name=declared,
        description=description if isinstance(description, str) else None,
        created_raw=_json_safe(created),
        members=distinct,
        repeated=repeated,
        options=options,
        ignored_option_keys=ignored,
        diagnostics=sort_diagnostics(notes),
    )


def _describe(value: object) -> str:
    return "missing" if value is None else type(value).__name__


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _relative_source(path: Path, root: Path) -> str | None:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except (ValueError, OSError):
        return None


def _read_state(root: Path) -> SprintStateEvidence:
    state_path = root / STATE_FILENAME
    shown = str(state_path)
    try:
        if not state_path.is_file():
            return SprintStateEvidence(shown, False, None, (), None)
        loaded = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return SprintStateEvidence(shown, True, None, (), f"{type(exc).__name__}: {exc}")
    if not isinstance(loaded, dict):
        return SprintStateEvidence(shown, True, None, (), "state root is not an object")
    name = loaded.get("sprint_name")
    completed = loaded.get("completed_issues")
    return SprintStateEvidence(
        shown,
        True,
        name if isinstance(name, str) and name else None,
        tuple(c for c in completed if isinstance(c, str)) if isinstance(completed, list) else (),
        None,
    )


def collect_sprint_domain(project_root: Path, *, config: BRConfig) -> SprintDomain:
    """Capture every sprint definition and the executor state evidence (one read each).

    Reads ``sprints.sprints_dir`` as a path relative to *project_root* (an absolute path is used
    as given). Creates nothing. An absent directory is simply no definitions.
    """
    root = project_root.resolve()
    configured = Path(config.sprints.sprints_dir)
    directory = configured if configured.is_absolute() else root / configured
    diagnostics: list[Diagnostic] = []
    definitions: list[SprintDefinition] = []
    entries: list[Path] = []
    try:
        if directory.is_dir():
            entries = sorted(p for p in directory.iterdir() if p.suffix in (".yaml", ".yml"))
    except OSError as exc:
        diagnostics.append(
            Diagnostic(
                "sprint_directory_unreadable",
                f"{configured}: {type(exc).__name__}: {exc}",
                (),
                None,
            )
        )
    yaml_stems = {p.stem for p in entries if p.suffix == ".yaml"}
    outside_noted = False
    for path in entries:
        name = path.stem
        if path.suffix == ".yml" and name in yaml_stems:
            diagnostics.append(
                Diagnostic(
                    "sprint_yml_shadowed",
                    f"{path.name} is ignored: {name}.yaml is the runnable definition",
                    (),
                    sprint_subject(name),
                )
            )
            continue
        try:
            if not path.is_file():
                continue
            data = path.read_bytes()  # the single read of this definition
        except OSError as exc:
            definitions.append(
                _exclusion(name, path, None, None, UNREADABLE, f"{type(exc).__name__}: {exc}")
            )
            continue
        source = _relative_source(path, root)
        definition = parse_sprint_definition(name, path, source, data, extension=path.suffix)
        if source is None:
            note = Diagnostic(
                "sprint_source_outside_project",
                f"{name}: {path} is outside the project root, so it has no project-relative "
                "definition identity and cannot be offered",
                (),
                sprint_subject(name),
            )
            if definition.valid:
                definition = _outside(definition, note)
            else:
                definition = _with_diagnostic(definition, note)
            outside_noted = True
        definitions.append(definition)
    if outside_noted:
        diagnostics.append(
            Diagnostic(
                "sprint_directory_outside_project",
                f"sprints.sprints_dir {configured} resolves outside the project root",
                (),
                None,
            )
        )
    return SprintDomain(
        definitions=tuple(sorted(definitions, key=lambda d: d.name)),
        state=_read_state(root),
        diagnostics=sort_diagnostics(diagnostics),
    )


def _with_diagnostic(definition: SprintDefinition, note: Diagnostic) -> SprintDefinition:
    return replace(definition, diagnostics=sort_diagnostics([*definition.diagnostics, note]))


def _outside(definition: SprintDefinition, note: Diagnostic) -> SprintDefinition:
    return replace(
        _with_diagnostic(definition, note),
        valid=False,
        exclusion=OUTSIDE_PROJECT,
        exclusion_detail="the definition file lies outside the project root",
    )


def sprint_history_names(definitions: tuple[SprintDefinition, ...] | None) -> tuple[str, ...]:
    """Names to batch into the single ``RecentSprintInvocations`` request (valid definitions)."""
    if not definitions:
        return ()
    return tuple(sorted(d.name for d in definitions if d.valid))
