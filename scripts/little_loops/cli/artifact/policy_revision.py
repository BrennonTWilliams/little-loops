"""Policy-revision validation and persistence for builder-origin run requests (FEAT-3498).

Pure functions: no transport or queue imports. Shared by FEAT-3504's
same-origin serve route and by ``ll-queue``'s approval flow (via
:func:`little_loops.queue_store.create_or_get_run_request`), and directly
exercisable from tests with no browser involved.
"""

from __future__ import annotations

import hashlib
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

import yaml

from little_loops.fsm.validation._base import ValidationSeverity
from little_loops.fsm.validation.structural_rules import load_and_validate

__all__ = [
    "RunRequest",
    "ValidationOutcome",
    "PolicyRevisionConflictError",
    "validate_policy_revision",
    "persist_policy_revision",
]

# First release accepts `issue_lifecycle` policies only (FEAT-3498 scope). A
# generated loop declares its policy mode via the existing `category:` field
# (FSMLoop.category) rather than a new schema key — `category` already exists
# as the loop's topical classification, so reusing it avoids a duplicate
# concept for a single-mode first release.
_SUPPORTED_MODES = frozenset({"issue_lifecycle"})


@dataclass(frozen=True)
class RunRequest:
    """Wire-shape input to :func:`little_loops.queue_store.create_or_get_run_request`.

    FEAT-3504's POST route deserializes into this; ``revision_id`` is the
    caller-computed SHA-256 of ``yaml``'s exact UTF-8 bytes. The route (not
    :func:`persist_policy_revision`, which only compares bytes when a
    same-name file already exists) recomputes the hash and rejects mismatches.
    """

    request_id: str
    project_id: str
    workspace_id: str
    revision_id: str
    yaml: bytes
    issue_id: str


@dataclass
class ValidationOutcome:
    """Return of :func:`validate_policy_revision`."""

    ok: bool
    errors: list[str]
    warnings: list[str]
    mode: str | None = None


class PolicyRevisionConflictError(ValueError):
    """Raised by :func:`persist_policy_revision` on a same-name/different-bytes collision."""


def validate_policy_revision(yaml_bytes: bytes, *, project_root: Path) -> ValidationOutcome:
    """Validate a submitted policy revision's bytes, returning a structured outcome.

    Wraps :func:`~little_loops.fsm.validation.structural_rules.load_and_validate`
    with ``raise_on_error=False`` (precedent: ``cli/doctor.py``, ``cli/logs.py``
    already consume its returned violations list the same way), converting the
    expected pre-parse failures (missing file, non-mapping YAML, missing
    required top-level fields, YAML syntax errors) into the same structured
    outcome rather than letting them propagate. There is no run directory yet
    at validation time (submission precedes acceptance), so a temp file is
    written under the project's own artifact directory to preserve the
    relative-path resolution behavior ``load_and_validate`` expects, and
    cleaned up unconditionally.

    Callers must not enqueue a request when ``ok`` is False.
    """
    artifact_dir = project_root / ".loops" / "policy-builder"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=artifact_dir, prefix=".validate-", suffix=".yaml")
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(yaml_bytes)

        try:
            fsm, violations = load_and_validate(tmp_path, raise_on_error=False)
        except (FileNotFoundError, ValueError, yaml.YAMLError) as exc:
            return ValidationOutcome(ok=False, errors=[str(exc)], warnings=[], mode=None)

        errors = [v.message for v in violations if v.severity == ValidationSeverity.ERROR]
        warnings = [v.message for v in violations if v.severity == ValidationSeverity.WARNING]
        mode = fsm.category or None

        if not errors:
            if mode not in _SUPPORTED_MODES:
                errors.append(
                    f"Unsupported policy mode {mode!r}; only {sorted(_SUPPORTED_MODES)} "
                    "accepted in this release"
                )
            else:
                issue_param = fsm.parameters.get("issue_id")
                if issue_param is None or not issue_param.required:
                    errors.append(
                        "issue_lifecycle policies must declare a required 'issue_id' parameter"
                    )

        return ValidationOutcome(ok=not errors, errors=errors, warnings=warnings, mode=mode)
    finally:
        tmp_path.unlink(missing_ok=True)


def persist_policy_revision(yaml_bytes: bytes, revision_id: str, *, project_root: Path) -> Path:
    """Atomically persist a validated revision's exact bytes, project-anchored.

    Written with ``write_bytes`` semantics (temp file + ``os.replace``), never
    ``write_text``, so no newline/encoding normalization can change the
    on-disk SHA-256 relative to *revision_id*. The filename uses a short
    (12-char) prefix of the hash rather than the full 64 hex chars so
    ``_make_instance_id(loop_name)`` (which derives from the YAML stem) and
    run-dir names stay readable.

    An existing file at the target path is left untouched if its bytes are
    identical to *yaml_bytes* (idempotent re-persist of the same revision);
    a same-name file with *different* content raises
    :class:`PolicyRevisionConflictError` rather than silently overwriting.
    Compared by direct byte equality, not by trusting the caller's
    *revision_id* label — a 12-char filename prefix collision between two
    different full hashes is exactly the case this guards against.
    """
    dest_dir = project_root / ".loops" / "policy-builder"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"lifecycle-{revision_id[:12]}.yaml"

    if dest.exists():
        existing_bytes = dest.read_bytes()
        if existing_bytes != yaml_bytes:
            existing_hash = hashlib.sha256(existing_bytes).hexdigest()
            raise PolicyRevisionConflictError(
                f"revision file {dest} already exists with different content "
                f"(on-disk hash {existing_hash}, expected {revision_id})"
            )
        return dest

    fd, tmp_name = tempfile.mkstemp(dir=dest_dir, prefix=".persist-", suffix=".tmp")
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(yaml_bytes)
        os.replace(tmp_path, dest)
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise
    return dest
