"""Captured evidence for the ``ll-next`` arena: diagnostics, formatting policy, thresholds.

Everything the pure assessment layer needs from "outside the issue bytes" is read
**once** at collection time and frozen here:

* :class:`FormattingPolicy` -- per-type required-section sets (resolved exactly like
  :func:`little_loops.issue_parser.is_formatted` with ``templates_dir=None``,
  including the ``CLAUDE_PLUGIN_ROOT`` override), per-type load failures and the
  Program Design cutover date (or ``None`` when no stamp exists).
* :class:`Thresholds` -- the effective merged ``commands.confidence_gate`` limits,
  validated as integers ``0..100`` (booleans rejected).

:func:`is_formatted_from_state` then reproduces ``is_formatted`` semantics from the
captured record and policy without touching the clock, cwd, environment, templates
or the cutover stamp (FEAT-3561 phase B).
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING, Any

from little_loops.issue_parser import _ISSUE_TYPE_RE, _required_sections
from little_loops.issue_template import _default_templates_dir, load_issue_sections
from little_loops.issues.program_design import (
    SECTION_TITLE as PROGRAM_DESIGN_TITLE,
)
from little_loops.issues.program_design import (
    _is_true,
    issue_design_timestamp,
    read_cutover_stamp,
)

if TYPE_CHECKING:
    from little_loops.config import BRConfig
    from little_loops.next_arena.state import SourceRecord

#: Issue types ``is_formatted`` can resolve a template for (the ``_ISSUE_TYPE_RE`` alternation).
FORMAT_ISSUE_TYPES: tuple[str, ...] = ("BUG", "FEAT", "ENH", "EPIC")

#: Session Log marker that short-circuits the structural formatting check.
FORMAT_LOG_COMMAND = "/ll:format-issue"

_H2_RE = re.compile(r"^##\s+(.+)$", re.MULTILINE)

#: Defaults mirrored from ``cmd_next_action`` (readiness, outcome).
DEFAULT_THRESHOLDS: tuple[int, int] = (85, 65)


@dataclass(frozen=True)
class Diagnostic:
    """A deterministic, structured source/state finding.

    ``paths`` are project-root-relative POSIX strings in sorted order; ``subject`` is
    the issue ID (or other key) the finding is about, when there is one.
    """

    code: str
    message: str
    paths: tuple[str, ...] = ()
    subject: str | None = None

    def sort_key(self) -> tuple[str, str, tuple[str, ...], str]:
        """Total order used wherever diagnostics are listed."""
        return (self.code, self.subject or "", self.paths, self.message)

    def to_dict(self) -> dict[str, Any]:
        """JSON-ready mapping."""
        return {
            "code": self.code,
            "message": self.message,
            "paths": list(self.paths),
            "subject": self.subject,
        }


def sort_diagnostics(diagnostics: Iterable[Diagnostic]) -> tuple[Diagnostic, ...]:
    """Return *diagnostics* deduplicated and in :meth:`Diagnostic.sort_key` order."""
    return tuple(sorted(set(diagnostics), key=Diagnostic.sort_key))


# --------------------------------------------------------------------------- formatting


@dataclass(frozen=True)
class FormattingPolicy:
    """Captured formatting evidence (assessment provenance, not fingerprint material).

    ``required_sections`` maps an issue type to its non-deprecated required section
    titles (``Program Design`` included when the template requires it); a type whose
    template failed to load appears in ``load_failures`` instead, which makes
    :func:`is_formatted_from_state` return ``False`` exactly as ``is_formatted`` does.
    """

    required_sections: Mapping[str, frozenset[str]]
    load_failures: Mapping[str, str]
    program_design_cutover: date | None
    templates_dir: str | None = None


def capture_formatting_policy(project_root: Path) -> FormattingPolicy:
    """Capture the formatting policy once, resolving templates like ``is_formatted(path)``.

    Uses ``load_issue_sections(type, None)`` so the bundled templates and the
    ``CLAUDE_PLUGIN_ROOT`` override resolve exactly as the legacy ``next-action`` path.
    """
    required: dict[str, frozenset[str]] = {}
    failures: dict[str, str] = {}
    for issue_type in FORMAT_ISSUE_TYPES:
        try:
            sections = load_issue_sections(issue_type, None)
            required[issue_type] = frozenset(_required_sections(sections))
        except Exception as exc:  # is_formatted treats any load failure as "not formatted"
            failures[issue_type] = f"{type(exc).__name__}: {exc}"
    try:
        templates_dir: str | None = str(_default_templates_dir())
    except Exception:  # pragma: no cover - defensive; provenance only
        templates_dir = None
    return FormattingPolicy(
        required_sections=MappingProxyType(required),
        load_failures=MappingProxyType(failures),
        program_design_cutover=read_cutover_stamp(project_root),
        templates_dir=templates_dir,
    )


def program_design_gate_active_from_policy(record: SourceRecord, policy: FormattingPolicy) -> bool:
    """Pure analogue of ``program_design_gate_active`` over captured evidence.

    Gate is off when no cutover is captured, the issue sets
    ``program_design_not_applicable``, or its design timestamp is strictly earlier
    than the cutover (grandfathered).
    """
    cutover = policy.program_design_cutover
    if cutover is None:
        return False
    if _is_true(record.frontmatter.get("program_design_not_applicable")):
        return False
    stamp = issue_design_timestamp(record.content)
    return not (stamp is not None and stamp < cutover)


def is_formatted_from_state(record: SourceRecord, policy: FormattingPolicy) -> bool:
    """Reproduce :func:`little_loops.issue_parser.is_formatted` from captured evidence.

    Order matches the original: unreadable source -> ``False``; ``/ll:format-issue`` in
    the Session Log -> ``True``; type from the filename (``-TYPE-`` anywhere, like the
    original) else ``False``; template load failure -> ``False``; Program Design is
    dropped from the requirement unless the captured gate is active; required headings
    must be a subset of the ``## `` headings.
    """
    if record.read_error is not None:
        return False
    if FORMAT_LOG_COMMAND in record.session_commands:
        return True

    type_match = _ISSUE_TYPE_RE.search(record.path.name)
    if not type_match:
        return False
    issue_type = type_match.group(1)
    if issue_type in policy.load_failures or issue_type not in policy.required_sections:
        return False

    required = policy.required_sections[issue_type]
    if PROGRAM_DESIGN_TITLE in required and not program_design_gate_active_from_policy(
        record, policy
    ):
        required = required - {PROGRAM_DESIGN_TITLE}
    if not required:
        return True

    headings = {m.strip() for m in _H2_RE.findall(record.content)}
    return required.issubset(headings)


# --------------------------------------------------------------------------- thresholds


@dataclass(frozen=True)
class Thresholds:
    """Effective merged readiness/outcome thresholds; ``None`` marks an invalid value."""

    readiness: int | None
    outcome: int | None
    enabled: bool


def _valid_threshold(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= 100


def capture_thresholds(config: BRConfig) -> tuple[Thresholds, tuple[str, ...]]:
    """Resolve and validate thresholds from the merged ``commands.confidence_gate``.

    Returns ``(thresholds, config_errors)``. An invalid value (non-integer, bool,
    outside ``0..100``) yields ``None`` for that limit and a captured error string the
    CLI surfaces as a configuration error (exit 2).
    """
    from little_loops.cli.issues.check_readiness import confidence_thresholds_from_gate

    readiness, outcome, enabled = confidence_thresholds_from_gate(
        config.confidence_gate_raw(), DEFAULT_THRESHOLDS
    )
    errors: list[str] = []
    resolved: list[int | None] = []
    for key, value in (("readiness_threshold", readiness), ("outcome_threshold", outcome)):
        if _valid_threshold(value):
            resolved.append(value)
        else:
            resolved.append(None)
            errors.append(
                f"commands.confidence_gate.{key} must be an integer 0..100 "
                f"(got {value!r}); booleans are not accepted"
            )
    return Thresholds(resolved[0], resolved[1], enabled), tuple(errors)
