"""Typed per-issue preparation run records (ENH-3597).

``refine-to-ready-issue`` (and, per ENH-3601, the ``prepare-issue`` wrapper that
will subsume it) write one JSON record per issue per run under
``<run_dir>/run-records/<writer>/<ID>.json``, alongside — never replacing — the
legacy ``refine-terminal-class`` / ``refine-broke-down`` files autodev's
``skip_inflight`` still consumes. The per-writer, per-issue path is the
isolation contract: a child re-running in autodev's shared ``run_dir`` can never
leak one issue's record into the next issue's exit, and the two writers'
records never collide (ENH-3600 reads the ``prepare-issue`` record from this
exact layout).

Readers treat a missing record as absent: ``read_run_record`` returns ``None``
for a missing file, malformed JSON, an OSError, or a stored writer/issue_id that
does not match the request — the same tolerant-read shape as
``ab_writer.read_ab_json`` (FEAT-1790).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from little_loops.file_utils import atomic_write_json

#: Per-issue preparation verdict. ``ready`` means autodev's ``check_passed``
#: predicate (``ll-issues check-readiness --honor-waiver`` and ``check-design``)
#: would pass for the issue's current state; everything else names why
#: preparation stopped.
PreparationOutcome = Literal[
    "ready", "decomposed", "cancelled", "blocked", "deferred", "retryable_error"
]

#: Which loop wrote the record. ``prepare-issue`` lands with ENH-3601; the
#: schema and writer accept it from day one so the second writer needs no
#: format change (ENH-3597 AC).
RunRecordWriter = Literal["refine-to-ready-issue", "prepare-issue"]

WRITERS: tuple[str, ...] = ("refine-to-ready-issue", "prepare-issue")

#: Legacy ``refine-terminal-class`` tokens the mapping knows how to translate.
LEGACY_CLASSES: tuple[str, ...] = (
    "proposal_unsound",
    "gate_unmet",
    "infra",
    "spike_inconclusive",
    "decision_unresolved",
    "quality",
)

RECORD_DIR_NAME = "run-records"


@dataclass(frozen=True)
class RunRecord:
    """One issue's preparation outcome for one loop run.

    ``legacy_class`` is ``None`` exactly when no ``refine-terminal-class`` was
    written — the done paths — which is what distinguishes them from
    ``classify_terminal``'s explicit ``quality`` in the mapping.
    ``readiness``/``outcome_confidence`` snapshot the issue's scores at terminal
    time (``None`` when never scored).
    """

    writer: RunRecordWriter
    issue_id: str
    outcome: PreparationOutcome
    child_ids: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()
    legacy_class: str | None = None
    readiness: int | None = None
    outcome_confidence: int | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to the wire dict (all eight keys always present)."""
        return {
            "writer": self.writer,
            "issue_id": self.issue_id,
            "outcome": self.outcome,
            "child_ids": list(self.child_ids),
            "evidence_refs": list(self.evidence_refs),
            "legacy_class": self.legacy_class,
            "readiness": self.readiness,
            "outcome_confidence": self.outcome_confidence,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RunRecord:
        """Rebuild from a wire dict, field-tolerant (missing keys default)."""
        writer = data.get("writer")
        if writer not in WRITERS:
            raise ValueError(f"unknown run-record writer: {writer!r}")
        return cls(
            writer=writer,  # type: ignore[arg-type]
            issue_id=str(data.get("issue_id") or ""),
            outcome=data.get("outcome"),  # type: ignore[arg-type]
            child_ids=tuple(str(c) for c in data.get("child_ids") or ()),
            evidence_refs=tuple(str(e) for e in data.get("evidence_refs") or ()),
            legacy_class=data.get("legacy_class"),
            readiness=data.get("readiness"),
            outcome_confidence=data.get("outcome_confidence"),
        )


def record_path(run_dir: Path, writer: str, issue_id: str) -> Path:
    """Return the isolation-contract path for one writer's record of one issue."""
    return Path(run_dir) / RECORD_DIR_NAME / writer / f"{issue_id}.json"


def write_run_record(run_dir: Path, record: RunRecord) -> Path:
    """Atomically write *record* under ``run_dir``; returns the path written."""
    path = record_path(run_dir, record.writer, record.issue_id)
    atomic_write_json(path, record.to_dict())
    return path


def read_run_record(run_dir: Path, writer: str, issue_id: str) -> RunRecord | None:
    """Read one writer's record for one issue; ``None`` when not legitimately there.

    ``None`` on absent file, malformed JSON, OSError, or a stored
    writer/issue_id mismatching the request — a stale or foreign record must
    read as absent, never as this run's verdict.
    """
    path = record_path(run_dir, writer, issue_id)
    try:
        data = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(data, dict):
        return None
    if data.get("writer") != writer or data.get("issue_id") != issue_id:
        return None
    try:
        return RunRecord.from_dict(data)
    except ValueError:
        return None


#: Closed routing-token vocabulary emitted by ``ll-issues run-record read``.
#: FSM ``route:`` tables match exactly (no prefix/glob), so consumers enumerate it.
RUN_RECORD_TOKENS: tuple[str, ...] = (
    "READY",
    "BLOCKED",
    "BLOCKED:decision_unresolved",
    "BLOCKED:proposal_unsound",
    "BLOCKED:quality",
    "DEFERRED:spike_inconclusive",
    "DEFERRED:gate_unmet",
    "RETRYABLE_ERROR:rate_limited",
    "RETRYABLE_ERROR:infra",
    "DECOMPOSED",
    "CANCELLED",
    "MISSING",
)

#: ``evidence_refs`` entry marking a child run that ended on an exhausted rate limit.
RATE_LIMIT_EXHAUSTED_REF = "rate_limit_exhausted"


def record_token(record: RunRecord | None) -> str:
    """Map a record (or ``None``) to its member of :data:`RUN_RECORD_TOKENS`.

    Anything unrecognised reads as ``MISSING`` — never ``READY``.
    """
    if record is None:
        return "MISSING"
    outcome = record.outcome
    if outcome == "ready":
        return "READY"
    if outcome == "decomposed":
        return "DECOMPOSED"
    if outcome == "cancelled":
        return "CANCELLED"
    if outcome == "retryable_error":
        if RATE_LIMIT_EXHAUSTED_REF in record.evidence_refs:
            return "RETRYABLE_ERROR:rate_limited"
        return "RETRYABLE_ERROR:infra"
    if outcome in ("blocked", "deferred"):
        if record.legacy_class is None:
            token = outcome.upper()
        else:
            token = f"{outcome.upper()}:{record.legacy_class}"
        return token if token in RUN_RECORD_TOKENS else "MISSING"
    return "MISSING"


def outcome_from_legacy_class(
    legacy_class: str | None,
    broke_down: bool,
    thresholds_met: bool,
    status: str | None,
) -> PreparationOutcome:
    """Map terminal-time signals to a :data:`PreparationOutcome`, first match wins.

    Rules (ENH-3597 Proposed Solution):

    1. frontmatter ``status`` is ``cancelled`` (closed during verify/refine)
       → ``cancelled``.
    2. broke-down → ``decomposed``.
    3. ``infra`` → ``retryable_error``.
    4. ``decision_unresolved``/``proposal_unsound``/``quality`` → ``blocked``.
    5. ``spike_inconclusive``/``gate_unmet`` → ``deferred``.
    6. no legacy class (the done paths) → ``ready`` only when the autodev
       ``check_passed`` predicate (readiness and Program Design gate) passes with
       fresh scores, else ``blocked``.
    """
    if status is not None and status.strip().lower() == "cancelled":
        return "cancelled"
    if broke_down:
        return "decomposed"
    if legacy_class == "infra":
        return "retryable_error"
    if legacy_class in ("decision_unresolved", "proposal_unsound", "quality"):
        return "blocked"
    if legacy_class in ("spike_inconclusive", "gate_unmet"):
        return "deferred"
    return "ready" if thresholds_met else "blocked"
