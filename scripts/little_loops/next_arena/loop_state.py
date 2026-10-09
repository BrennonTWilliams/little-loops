"""Captured loop-domain evidence for the ``run-loop`` verb (FEAT-3769).

Everything the pure loop assessment needs is read **once** at collection time and frozen
here; ``assess_run_loops`` performs no live I/O. The module owns

* :func:`collect_loop_sources` -- recursive project/built-in ``*.yaml`` discovery in the
  catalog's filesystem shapes, single-buffer capture of each top-level source (bytes hashed,
  parsed and validated from the same buffer), runner-equivalent validation with the printed
  project root as the resolution base, and the captured source inventory,
* :class:`LoopSourceInventory` + :func:`resolve_target` -- a pure mirror of
  ``loop_paths.resolve_loop_path``'s precedence from the printed root,
* :func:`zero_argument_context` -- the symbolic zero-argument preflight (what ``cmd_run``
  would bind without supplied input/context), and
* :func:`collect_loop_history` -- one batched pass over ``<loops_dir>/.history`` with
  per-record qualification evidence.

Nothing here runs a loop, reads design tokens, opens ``history.db`` or writes a file.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING, Any

import yaml

from little_loops.fsm.context_seed import (
    parse_program_md_text,
    required_context_keys,
    seed_parameter_defaults,
)
from little_loops.fsm.loop_paths import get_builtin_loops_dir, resolution_context
from little_loops.next_arena.actions import BUILTIN_SOURCE_PREFIX
from little_loops.next_arena.axes import parse_utc_datetime
from little_loops.next_arena.inputs import Diagnostic, sort_diagnostics

if TYPE_CHECKING:
    from little_loops.config import BRConfig

__all__ = [
    "DEFAULT_VISIBILITY",
    "KIND_BUILTIN",
    "KIND_DRAFT",
    "KIND_PROJECT",
    "LoopContextInputs",
    "LoopDefinitionRecord",
    "LoopDomain",
    "LoopHistory",
    "LoopRunRecord",
    "LoopSourceInventory",
    "Resolution",
    "ZeroArgContext",
    "collect_loop_definitions",
    "collect_loop_domain",
    "collect_loop_history",
    "collect_loop_inputs",
    "collect_loop_sources",
    "loop_subject",
    "resolve_target",
    "zero_argument_context",
]

KIND_PROJECT = "project"
KIND_BUILTIN = "builtin"
KIND_DRAFT = "draft"

#: Visibility tiers a loop may declare; anything else normalizes to ``public``.
VALID_VISIBILITIES: frozenset[str] = frozenset({"public", "internal", "example"})
DEFAULT_VISIBILITY = "public"

#: Exclusion codes of a :class:`LoopDefinitionRecord` (``exclusion``).
EXCL_READ_ERROR = "read_error"
EXCL_DECODE_ERROR = "decode_error"
EXCL_YAML_ERROR = "yaml_error"
EXCL_VALIDATION = "validation_error"
EXCL_LOAD_ERROR = "load_error"
EXCL_OUT_OF_ROOT = "out_of_root_loops_dir"

_MISSING_FIELDS_PREFIX = "FSM file missing required fields"
_GENERATED = "<generated>"


def loop_subject(target: str) -> str:
    """Diagnostic subject (and target key) of a loop operand: ``loop:NAME``."""
    return f"loop:{target}"


# ----------------------------------------------------------------------------- seams
# Module-level so tests can count reads or inject failures.


def _read_bytes(path: Path) -> bytes:
    """The single filesystem read of a top-level loop source."""
    return path.read_bytes()


def _read_text(path: Path) -> str:
    """Read one small text input (steering file)."""
    return path.read_text(encoding="utf-8")


def _scandir(path: Path) -> Any:
    """``os.scandir`` seam for the single batched ``.history`` enumeration."""
    return os.scandir(path)


def _read_state_bytes(path: Path) -> bytes:
    """The single read of one archived run's ``state.json``."""
    return path.read_bytes()


# ----------------------------------------------------------------------------- records


class _Unknown:
    """Marker for a context value that exists at run time but is unknown here."""

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return "<unknown>"

    def __bool__(self) -> bool:  # truthiness must never be guessed
        raise TypeError("truthiness of an unknown symbolic value must not be evaluated")


UNKNOWN = _Unknown()


@dataclass(frozen=True)
class DraftInfo:
    """Inventory facts about one generator draft (``runs/<folder>/workflow.yaml``)."""

    folder: str
    path: Path
    internal_name: str | None
    mtime: float | None


@dataclass(frozen=True)
class LoopSourceInventory:
    """Captured filesystem facts the pure target resolver needs.

    ``project_files``/``builtin_files`` hold POSIX paths (relative to the loops directory /
    the built-in directory) of every non-hidden ``*.yaml`` plus the direct
    ``runs/*/workflow.yaml`` drafts; ``direct`` maps an operand to the kind of thing that
    exists at ``project_root/operand`` (``file``/``dir``/``other``), captured for every
    canonical target so the direct-path probe never silently falls through.
    """

    project_root: Path
    loops_dir: Path
    builtin_dir: Path
    project_files: frozenset[str]
    builtin_files: frozenset[str]
    drafts: Mapping[str, DraftInfo]
    direct: Mapping[str, str]


@dataclass(frozen=True)
class Resolution:
    """Where an operand resolves from the printed root (``None`` path: nothing matches)."""

    kind: str
    path: Path | None
    detail: str = ""


@dataclass(frozen=True)
class LoopDefinitionRecord:
    """One discovered, validated top-level loop source (immutable, built at collection).

    ``digest`` is the SHA-256 of the **captured top-level bytes**; ``source`` the
    project-relative or ``builtin:`` identity (``None`` when it cannot be represented).
    A record with ``valid=False`` carries its ``exclusion`` code and detail and stays
    explainable; ``diagnostics`` holds validation warnings and resolver notes.
    """

    target: str
    kind: str
    path: Path
    source: str | None
    digest: str | None
    valid: bool
    exclusion: str | None
    exclusion_detail: str | None
    errors: tuple[str, ...]
    logical_name: str | None
    visibility: str
    draft_folder: str | None
    draft_internal_name: str | None
    mtime: float | None
    context: Mapping[str, Any]
    parameter_defaults: Mapping[str, Any]
    required_keys: frozenset[str]
    required_inputs: tuple[str, ...]
    max_steps: int
    max_iterations: int | None
    diagnostics: tuple[Diagnostic, ...] = ()

    @property
    def is_draft(self) -> bool:
        """True for an unpromoted generator draft."""
        return self.kind == KIND_DRAFT


@dataclass(frozen=True)
class LoopContextInputs:
    """Runner inputs captured once: steering file and config-derived context defaults."""

    steering_path: str
    steering_present: bool
    steering_sections: Mapping[str, str]
    steering_error: str | None
    include_default: Any
    readiness_threshold: Any
    outcome_threshold: Any


@dataclass(frozen=True)
class LoopRunRecord:
    """One archived run folder under ``<loops_dir>/.history`` with qualification evidence."""

    folder: str
    rel_path: str
    run_id: str
    logical_name: str
    state_read: str
    started_at_raw: Any
    started_at: datetime | None
    status_raw: Any
    status: str | None
    qualified: bool
    exclusion: str | None

    def to_dict(self) -> dict[str, Any]:
        """JSON-ready mapping (raw captured provenance retained)."""
        return {
            "folder": self.folder,
            "run_id": self.run_id,
            "logical_name": self.logical_name,
            "state_read": self.state_read,
            "started_at_raw": self.started_at_raw if _json_safe(self.started_at_raw) else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "status": self.status,
            "qualified": self.qualified,
            "exclusion": self.exclusion,
        }


def _json_safe(value: Any) -> bool:
    return value is None or isinstance(value, (str, int, float, bool))


@dataclass(frozen=True)
class LoopHistory:
    """Captured filesystem run history.

    ``available`` is ``False`` when the ``.history`` enumeration failed (the batch is
    discarded, never scored as complete). A genuinely absent directory is available and
    empty. No qualifying record is not proof that a loop never ran.
    """

    available: bool
    unavailable_reason: str | None
    records: tuple[LoopRunRecord, ...]
    diagnostics: tuple[Diagnostic, ...] = ()


@dataclass(frozen=True)
class LoopDomain:
    """Everything collected for the loop domain, assembled into :class:`ProjectState`."""

    definitions: tuple[LoopDefinitionRecord, ...]
    inventory: LoopSourceInventory
    history: LoopHistory
    inputs: LoopContextInputs
    diagnostics: tuple[Diagnostic, ...] = field(default=())


# ------------------------------------------------------------------- source discovery


def _list_yaml(base: Path, *, split_runs: bool) -> list[Path]:
    """Non-hidden ``*.yaml`` files below *base* (path order).

    With *split_runs*, ``base/runs`` is not descended into: only its direct
    ``<instance>/workflow.yaml`` drafts are listed (the catalog's shapes).
    """
    found: list[Path] = []
    if not base.is_dir():
        return found
    for dirpath, dirnames, filenames in os.walk(base):
        here = Path(dirpath)
        dirnames[:] = sorted(d for d in dirnames if not d.startswith("."))
        if split_runs and here == base and "runs" in dirnames:
            dirnames.remove("runs")
            runs_root = base / "runs"
            try:
                children = sorted(os.listdir(runs_root))
            except OSError:
                children = []
            for child in children:
                if child.startswith("."):
                    continue
                workflow = runs_root / child / "workflow.yaml"
                if workflow.is_file():
                    found.append(workflow)
        found.extend(here / name for name in sorted(filenames) if name.endswith(".yaml"))
    return sorted(found)


def _canonical_target(path: Path, base: Path, kind: str) -> str:
    if kind == KIND_DRAFT:
        return path.parent.name
    rel = path.relative_to(base).as_posix()
    if kind == KIND_PROJECT and rel.endswith(".fsm.yaml"):
        return rel[: -len(".fsm.yaml")]
    return rel[: -len(".yaml")]


def _is_draft_path(path: Path, loops_dir: Path) -> bool:
    try:
        rel = path.relative_to(loops_dir / "runs")
    except ValueError:
        return False
    return len(rel.parts) == 2 and rel.parts[1] == "workflow.yaml"


def _normalize_visibility(raw: Any) -> str:
    return raw if isinstance(raw, str) and raw in VALID_VISIBILITIES else DEFAULT_VISIBILITY


def _validation_diagnostics(
    target: str, source: str | None, warnings: Sequence[Any], notes: Sequence[str]
) -> tuple[Diagnostic, ...]:
    paths = (source,) if source else ()
    found = [
        Diagnostic("loop_validation_warning", f"{target}: {w}", paths, loop_subject(target))
        for w in warnings
    ]
    found.extend(
        Diagnostic("loop_resolution_note", f"{target}: {note}", paths, loop_subject(target))
        for note in notes
    )
    return sort_diagnostics(found)


def _blank_record(
    target: str, kind: str, path: Path, source: str | None, **overrides: Any
) -> LoopDefinitionRecord:
    base: dict[str, Any] = {
        "target": target,
        "kind": kind,
        "path": path,
        "source": source,
        "digest": None,
        "valid": False,
        "exclusion": None,
        "exclusion_detail": None,
        "errors": (),
        "logical_name": None,
        "visibility": DEFAULT_VISIBILITY,
        "draft_folder": path.parent.name if kind == KIND_DRAFT else None,
        "draft_internal_name": None,
        "mtime": None,
        "context": MappingProxyType({}),
        "parameter_defaults": MappingProxyType({}),
        "required_keys": frozenset(),
        "required_inputs": (),
        "max_steps": 50,
        "max_iterations": None,
        "diagnostics": (),
    }
    base.update(overrides)
    return LoopDefinitionRecord(**base)


def _exclusion_diagnostic(record: LoopDefinitionRecord) -> Diagnostic:
    paths = (record.source,) if record.source else ()
    return Diagnostic(
        "loop_definition_excluded",
        f"{record.target}: {record.exclusion}: {record.exclusion_detail}",
        paths,
        loop_subject(record.target),
    )


def _capture_source(
    path: Path, kind: str, base: Path, source: str | None, root: Path, representable: bool
) -> tuple[LoopDefinitionRecord | None, DraftInfo | None]:
    """Read, hash, parse and validate one top-level source from a single buffer.

    Returns ``(record, draft_info)``; ``record`` is ``None`` for a source that is not a loop
    definition (non-mapping YAML, or a fragment/library lacking the required top-level keys).
    """
    target = _canonical_target(path, base, kind)
    mtime: float | None = None
    if kind == KIND_DRAFT:
        try:
            mtime = path.stat().st_mtime
        except OSError:
            mtime = None
    if not representable:
        record = _blank_record(
            target,
            kind,
            path,
            None,
            exclusion=EXCL_OUT_OF_ROOT,
            exclusion_detail=(
                "loops.loops_dir resolves outside the project root, so the definition source "
                "cannot be a project-relative identity"
            ),
            mtime=mtime,
        )
        return record, DraftInfo(
            path.parent.name, path, None, mtime
        ) if kind == KIND_DRAFT else None

    def draft(name: str | None) -> DraftInfo | None:
        return DraftInfo(path.parent.name, path, name, mtime) if kind == KIND_DRAFT else None

    try:
        raw = _read_bytes(path)
    except OSError as exc:
        record = _blank_record(
            target, kind, path, source, exclusion=EXCL_READ_ERROR,
            exclusion_detail=f"{type(exc).__name__}: {exc}", mtime=mtime,
        )  # fmt: skip
        return record, draft(None)
    digest = "sha256:" + hashlib.sha256(raw).hexdigest()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        record = _blank_record(
            target, kind, path, source, digest=digest, exclusion=EXCL_DECODE_ERROR,
            exclusion_detail=str(exc), mtime=mtime,
        )  # fmt: skip
        return record, draft(None)
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        record = _blank_record(
            target, kind, path, source, digest=digest, exclusion=EXCL_YAML_ERROR,
            exclusion_detail=" ".join(str(exc).split()), mtime=mtime,
        )  # fmt: skip
        return record, draft(None)
    if not isinstance(data, dict):
        return None, draft(None)
    internal = data.get("name")
    internal_name = internal if isinstance(internal, str) and internal else None
    info = draft(internal_name)
    # Cheap fragment/library screen on the captured top level (no second parse).
    if "from" not in data and not (
        "name" in data and "initial" in data and ("states" in data or "flow" in data)
    ):
        return None, info

    from little_loops.fsm.validation import load_and_validate

    notes: list[str] = []
    common: dict[str, Any] = {
        "digest": digest,
        "mtime": mtime,
        "draft_internal_name": internal_name,
    }
    try:
        with resolution_context(root, notes):
            fsm, violations = load_and_validate(path, raise_on_error=False, source_data=data)
    except Exception as exc:  # per-definition containment: explainable exclusion
        if isinstance(exc, ValueError) and str(exc).startswith(_MISSING_FIELDS_PREFIX):
            return None, info  # fragment / non-runnable source: not a definition
        code = EXCL_LOAD_ERROR
        record = _blank_record(
            target, kind, path, source, exclusion=code,
            exclusion_detail=f"{type(exc).__name__}: {' '.join(str(exc).split())}",
            diagnostics=_validation_diagnostics(target, source, (), notes), **common,
        )  # fmt: skip
        return record, info

    errors = tuple(str(v) for v in violations if v.severity.value == "error")
    warnings = [v for v in violations if v.severity.value != "error"]
    diagnostics = _validation_diagnostics(target, source, warnings, notes)
    parameter_defaults = {
        name: spec.default
        for name, spec in fsm.parameters.items()
        if not spec.required and spec.default is not None
    }
    record = _blank_record(
        target,
        kind,
        path,
        source,
        valid=not errors,
        exclusion=EXCL_VALIDATION if errors else None,
        exclusion_detail="; ".join(errors) if errors else None,
        errors=errors,
        logical_name=fsm.name,
        visibility=_normalize_visibility(fsm.visibility),
        context=MappingProxyType(copy.deepcopy(fsm.context)),
        parameter_defaults=MappingProxyType(copy.deepcopy(parameter_defaults)),
        required_keys=frozenset(required_context_keys(fsm.states.values())),
        required_inputs=tuple(fsm.required_inputs),
        max_steps=fsm.max_steps,
        max_iterations=fsm.max_iterations,
        diagnostics=diagnostics,
        **common,
    )
    return record, info


def collect_loop_sources(
    project_root: Path, *, config: BRConfig
) -> tuple[tuple[LoopDefinitionRecord, ...], LoopSourceInventory, tuple[Diagnostic, ...]]:
    """Discover and capture every loop definition (project, drafts, built-ins).

    Each unique top-level source is read once; its bytes are hashed, parsed and validated
    from that buffer with the original source path as the reference base. Validation uses
    the runner's argument set (no ``orchestration_request_path``/``host_cli``/
    ``model_hints``), ``raise_on_error=False`` and the printed *project_root* as the
    resolution base for every cwd-sensitive lookup. Returns ``(records, inventory,
    diagnostics)``; records are ordered project, draft, built-in then target.
    """
    root = project_root.resolve()
    loops_dir = config.get_loops_dir()
    builtin_dir = get_builtin_loops_dir()
    diagnostics: list[Diagnostic] = []

    try:
        loops_rel = loops_dir.resolve().relative_to(root)
        representable = True
    except ValueError:
        loops_rel = Path()
        representable = False
        diagnostics.append(
            Diagnostic(
                "loops_dir_out_of_root",
                f"loops.loops_dir resolves to {loops_dir}, outside the project root; "
                "project loop definitions cannot be offered (definition_source must be "
                "project-relative)",
                (),
                "run-loop",
            )
        )

    project_paths = _list_yaml(loops_dir, split_runs=True)
    builtin_paths = _list_yaml(builtin_dir, split_runs=False)

    records: list[LoopDefinitionRecord] = []
    drafts: dict[str, DraftInfo] = {}
    for path in project_paths:
        kind = KIND_DRAFT if _is_draft_path(path, loops_dir) else KIND_PROJECT
        source = (loops_rel / path.relative_to(loops_dir)).as_posix() if representable else None
        record, info = _capture_source(path, kind, loops_dir, source, root, representable)
        if info is not None:
            drafts[info.folder] = info
        if record is not None:
            records.append(record)
    for path in builtin_paths:
        rel = path.relative_to(builtin_dir).as_posix()
        record, _info = _capture_source(
            path, KIND_BUILTIN, builtin_dir, BUILTIN_SOURCE_PREFIX + rel, root, True
        )
        if record is not None:
            records.append(record)

    ordered_kinds = {KIND_PROJECT: 0, KIND_DRAFT: 1, KIND_BUILTIN: 2}
    records.sort(key=lambda r: (ordered_kinds[r.kind], r.target, str(r.path)))

    direct: dict[str, str] = {}
    for record in records:
        operand = root / record.target
        if operand.exists():
            direct[record.target] = (
                "dir" if operand.is_dir() else "file" if operand.is_file() else "other"
            )

    inventory = LoopSourceInventory(
        project_root=root,
        loops_dir=loops_dir,
        builtin_dir=builtin_dir,
        project_files=frozenset(p.relative_to(loops_dir).as_posix() for p in project_paths),
        builtin_files=frozenset(p.relative_to(builtin_dir).as_posix() for p in builtin_paths),
        drafts=MappingProxyType(dict(sorted(drafts.items()))),
        direct=MappingProxyType(dict(sorted(direct.items()))),
    )
    for record in records:
        if record.exclusion in (EXCL_READ_ERROR, EXCL_DECODE_ERROR, EXCL_YAML_ERROR):
            diagnostics.append(_exclusion_diagnostic(record))
    return tuple(records), inventory, sort_diagnostics(diagnostics)


def collect_loop_definitions(
    project_root: Path, *, config: BRConfig
) -> tuple[LoopDefinitionRecord, ...]:
    """Collection-phase discovery and validation of every loop definition (records only)."""
    return collect_loop_sources(project_root, config=config)[0]


# ------------------------------------------------------------------------ resolution


def resolve_target(inventory: LoopSourceInventory, target: str) -> Resolution:
    """Mirror ``resolve_loop_path`` precedence for *target* from the printed project root.

    Order: direct ``project_root/target`` path, compiled FSM, project YAML, built-in, draft
    instance folder, then the latest-mtime draft whose internal ``name:`` equals *target*.
    Pure over the captured inventory -- no filesystem access.
    """
    kind = inventory.direct.get(target)
    if kind is not None:
        return Resolution("direct", inventory.project_root / target, kind)
    loops_dir = inventory.loops_dir
    for suffix in (".fsm.yaml", ".yaml"):
        rel = f"{target}{suffix}"
        if rel in inventory.project_files:
            return Resolution("project", loops_dir / rel)
    rel = f"{target}.yaml"
    if rel in inventory.builtin_files:
        return Resolution("builtin", inventory.builtin_dir / rel)
    draft = inventory.drafts.get(target)
    if draft is not None and f"runs/{target}/workflow.yaml" in inventory.project_files:
        return Resolution("draft", draft.path)
    matches = [d for _folder, d in sorted(inventory.drafts.items()) if d.internal_name == target]
    if matches:
        matches.sort(key=lambda d: d.mtime if d.mtime is not None else 0.0)
        return Resolution("draft_name", matches[-1].path, f"{len(matches)} draft(s)")
    return Resolution("none", None)


# ------------------------------------------------------------------ zero-arg context


@dataclass(frozen=True)
class ZeroArgContext:
    """Result of the symbolic zero-argument preflight for one definition.

    ``missing_keys`` are template context keys left unbound; ``unresolved_inputs`` are
    ``required_inputs`` that are falsy/absent; ``unknown_inputs`` are required inputs whose
    truthiness depends on an unknown loaded value (design-token context). Any of the three
    makes the definition ineligible. ``provenance`` records where each relevant key comes
    from -- eligibility evidence, never fingerprint material or an emitted override.
    """

    missing_keys: tuple[str, ...]
    unresolved_inputs: tuple[str, ...]
    unknown_inputs: tuple[str, ...]
    provenance: Mapping[str, str]

    @property
    def ok(self) -> bool:
        """True when ``ll-loop run -- TARGET`` passes both runner preflight checks."""
        return not (self.missing_keys or self.unresolved_inputs or self.unknown_inputs)

    def to_dict(self) -> dict[str, Any]:
        """JSON-ready mapping."""
        return {
            "ok": self.ok,
            "missing_keys": list(self.missing_keys),
            "unresolved_inputs": list(self.unresolved_inputs),
            "unknown_inputs": list(self.unknown_inputs),
            "provenance": dict(self.provenance),
        }


def _design_tokens_enabled(value: Any) -> Any:
    if isinstance(value, str):
        return value.strip().lower() not in ("", "0", "false", "no", "off")
    return value


def zero_argument_context(
    record: LoopDefinitionRecord, inputs: LoopContextInputs
) -> ZeroArgContext:
    """Model ``cmd_run``'s zero-argument context construction without running anything.

    Order mirrors the runner: YAML ``context:`` literals, optional-parameter defaults
    (``setdefault``), steering sections (which **overwrite**), generated ``run_dir``,
    conditional ``input_hash``/``max_steps``/``max_iterations``/``include`` seeds, confidence
    thresholds, then the always-bound design-context keys. Design values are never loaded:
    key presence is symbolic and an unknown value is never assumed truthy.
    """
    ctx: dict[str, Any] = dict(record.context)
    prov: dict[str, str] = dict.fromkeys(ctx, "loop context: literal")

    # seed_parameter_defaults(): the shared leaf sets only unbound optional parameters.
    before = set(ctx)
    specs = {name: _DefaultSpec(value) for name, value in record.parameter_defaults.items()}
    seed_parameter_defaults(ctx, specs)  # type: ignore[arg-type]
    for key in set(ctx) - before:
        prov[key] = "parameter default"

    for key, value in inputs.steering_sections.items():
        ctx[key] = value
        prov[key] = f"steering ({inputs.steering_path})"

    if "run_dir" not in ctx:
        ctx["run_dir"] = _GENERATED
        prov["run_dir"] = "runner: generated run directory (symbolic)"
    if "input_hash" not in ctx and isinstance(ctx.get("input"), str):
        ctx["input_hash"] = _GENERATED
        prov["input_hash"] = "runner: derived from string input"
    if "max_steps" not in ctx:
        ctx["max_steps"] = record.max_steps
        prov["max_steps"] = "runner: loop max_steps"
    if record.max_iterations is not None and "max_iterations" not in ctx:
        ctx["max_iterations"] = record.max_iterations
        prov["max_iterations"] = "runner: loop max_iterations"
    if "include" not in ctx and inputs.include_default:
        ctx["include"] = inputs.include_default
        prov["include"] = "config: loops.run_defaults.include"
    for key, value in (
        ("readiness_threshold", inputs.readiness_threshold),
        ("outcome_threshold", inputs.outcome_threshold),
    ):
        if key not in ctx:
            ctx[key] = value
            prov[key] = "config: commands.confidence_gate"

    use_tokens = _design_tokens_enabled(ctx.get("use_design_tokens", True))
    if use_tokens and not ctx.get("design_tokens_context"):
        for key in ("design_tokens_context", "design_guidance_context"):
            ctx[key] = UNKNOWN
            prov[key] = "runner: design context (symbolic, value unknown)"
    else:
        for key in ("design_tokens_context", "design_guidance_context"):
            if key not in ctx:
                ctx[key] = ""
                prov[key] = "runner: design context opt-out (empty)"

    missing = tuple(sorted(key for key in record.required_keys if key not in ctx))
    unresolved: list[str] = []
    unknown: list[str] = []
    for key in record.required_inputs:
        value = ctx.get(key, "")
        if value is UNKNOWN:
            unknown.append(key)
        elif not value:
            unresolved.append(key)
    relevant = sorted(set(record.required_keys) | set(record.required_inputs))
    return ZeroArgContext(
        missing_keys=missing,
        unresolved_inputs=tuple(unresolved),
        unknown_inputs=tuple(unknown),
        provenance=MappingProxyType({k: prov[k] for k in relevant if k in prov}),
    )


@dataclass(frozen=True)
class _DefaultSpec:
    """Minimal stand-in for ``ParameterSpec`` used by ``seed_parameter_defaults``."""

    default: Any
    required: bool = False


def collect_loop_inputs(project_root: Path, *, config: BRConfig) -> LoopContextInputs:
    """Capture the runner's steering file and config defaults once."""
    steering = project_root / ".ll" / "program.md"
    present = False
    sections: dict[str, str] = {}
    error: str | None = None
    if steering.exists():
        present = True
        try:
            sections = parse_program_md_text(_read_text(steering))
        except OSError as exc:  # the runner treats an unreadable steering file as absent
            error = f"{type(exc).__name__}: {exc}"
    try:
        include = config.loops.run_defaults.include
    except Exception:  # config shape drift: no default include
        include = None
    readiness: Any = None
    outcome: Any = None
    try:
        gate = config.commands.confidence_gate
        readiness, outcome = gate.readiness_threshold, gate.outcome_threshold
    except Exception:
        readiness = outcome = None
    return LoopContextInputs(
        steering_path=".ll/program.md",
        steering_present=present,
        steering_sections=MappingProxyType(sections),
        steering_error=error,
        include_default=include,
        readiness_threshold=readiness,
        outcome_threshold=outcome,
    )


# ----------------------------------------------------------------------------- history

HISTORY_DIR_NAME = ".history"


def _summarize_exclusions(records: Sequence[LoopRunRecord]) -> list[Diagnostic]:
    reasons: Counter[str] = Counter()
    samples: dict[str, list[str]] = {}
    for rec in records:
        if rec.exclusion is None:
            continue
        reasons[rec.exclusion] += 1
        samples.setdefault(rec.exclusion, []).append(rec.rel_path)
    return [
        Diagnostic(
            "loop_history_record_excluded",
            f"{count} archived run record(s) excluded from history: {reason}",
            tuple(sorted(samples[reason])[:3]),
            "run-loop",
        )
        for reason, count in sorted(reasons.items())
    ]


def _qualify(folder: str, rel_path: str, state: dict[str, Any] | None, read: str, as_of: datetime,
             run_id: str, name: str) -> LoopRunRecord:  # fmt: skip
    started_raw = state.get("started_at") if state is not None else None
    status_raw = state.get("status") if state is not None else None
    status = status_raw if isinstance(status_raw, str) else None
    started: datetime | None = None
    exclusion: str | None = None
    if state is None:
        exclusion = f"state_{read}"
    else:
        started, reason = parse_utc_datetime(started_raw)
        if started is None:
            exclusion = f"started_at_{reason}"
        elif started > as_of:
            exclusion = "started_at_future"
    return LoopRunRecord(
        folder=folder,
        rel_path=rel_path,
        run_id=run_id,
        logical_name=name,
        state_read=read,
        started_at_raw=started_raw,
        started_at=started,
        status_raw=status_raw,
        status=status,
        qualified=exclusion is None,
        exclusion=exclusion,
    )


def collect_loop_history(loops_dir: Path, *, as_of: datetime, project_root: Path) -> LoopHistory:
    """One batched pass over ``<loops_dir>/.history`` (archived runs only).

    Each ``state.json`` is read at most once. A qualifying run needs a readable JSON mapping
    and a valid UTC-normalized ``started_at`` at/before *as_of*; every other record keeps its
    exclusion reason and raw provenance. A missing directory is available and empty; a
    non-directory, unreadable directory or failed enumeration is *unavailable* and the whole
    partial batch is discarded.
    """
    from little_loops.fsm.persistence import HISTORY_DIR, _parse_run_folder

    base = loops_dir / HISTORY_DIR
    try:
        rel_base = base.relative_to(project_root).as_posix()
    except ValueError:
        rel_base = str(base)

    def unavailable(reason: str) -> LoopHistory:
        diag = Diagnostic(
            "loop_history_unavailable",
            f"{rel_base}: loop run history is unavailable ({reason}); history axes are "
            "missing, which is not proof that a loop never ran",
            (),
            "run-loop",
        )
        return LoopHistory(False, reason, (), (diag,))

    if not base.exists():
        return LoopHistory(True, None, ())
    if not base.is_dir():
        return unavailable("not_a_directory")

    records: list[LoopRunRecord] = []
    try:
        with _scandir(base) as entries:
            for entry in sorted(entries, key=lambda e: e.name):
                if not entry.is_dir():
                    continue
                parsed = _parse_run_folder(entry.name)
                if not parsed:
                    continue
                run_id, name = parsed
                rel_path = f"{rel_base}/{entry.name}"
                state_path = base / entry.name / "state.json"
                state: dict[str, Any] | None = None
                read = "ok"
                try:
                    payload = json.loads(_read_state_bytes(state_path))
                except FileNotFoundError:
                    read = "missing"
                except OSError:
                    read = "unreadable"
                except ValueError:
                    read = "malformed_json"
                else:
                    if isinstance(payload, dict):
                        state = payload
                    else:
                        read = "not_mapping"
                records.append(_qualify(entry.name, rel_path, state, read, as_of, run_id, name))
    except OSError as exc:
        return unavailable(f"enumeration_failed: {type(exc).__name__}")
    return LoopHistory(True, None, tuple(records), tuple(_summarize_exclusions(records)))


# ------------------------------------------------------------------------------ domain


def collect_loop_domain(project_root: Path, *, config: BRConfig, as_of: datetime) -> LoopDomain:
    """Collect definitions, inventory, steering/config inputs and history (loop verbs only)."""
    root = project_root.resolve()
    definitions, inventory, diagnostics = collect_loop_sources(root, config=config)
    history = collect_loop_history(config.get_loops_dir(), as_of=as_of, project_root=root)
    inputs = collect_loop_inputs(root, config=config)
    all_diagnostics = sort_diagnostics([*diagnostics, *history.diagnostics])
    return LoopDomain(definitions, inventory, history, inputs, all_diagnostics)
