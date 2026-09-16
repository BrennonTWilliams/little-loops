"""Spike: a persistent, idempotent, host-decision-gated request ledger.

Proves the FEAT-3488 Artifact Control Level 2 ("ask-to-run-prompt") mechanism
in isolation: a browser-submitted run request is recorded but never
auto-decided; a separate, explicit `decide()` call stands in for a host
session's own action (never invoked automatically by `submit()`); results are
observed asynchronously via `observe()`, not returned synchronously from
`submit()`. See ../../../../.ll/spikes/spike-FEAT-3488.md for the full plan.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Literal


class RequestStatus(str, Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    COMPLETED = "completed"
    FAILED = "failed"


class LedgerError(Exception):
    """Base class for ledger validation/transition failures."""


class ValidationError(LedgerError):
    """Raised when a submission is missing required binding fields."""


class BindingMismatchError(LedgerError):
    """Raised when an operation's binding does not match the stored record."""


class InvalidTransitionError(LedgerError):
    """Raised when a status transition is attempted out of order."""


class UnknownRequestError(LedgerError):
    """Raised when an operation targets a request_id with no record."""


@dataclass(frozen=True)
class RequestBinding:
    """Immutable identity a request is bound to: project, policy revision, issue."""

    project_id: str
    revision_id: str
    issue_id: str


@dataclass
class RequestRecord:
    request_id: str
    binding: RequestBinding
    status: RequestStatus
    run_id: str | None = None
    result: dict[str, Any] | None = None

    def to_json(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["status"] = self.status.value
        return payload

    @classmethod
    def from_json(cls, payload: dict[str, Any]) -> "RequestRecord":
        return cls(
            request_id=payload["request_id"],
            binding=RequestBinding(**payload["binding"]),
            status=RequestStatus(payload["status"]),
            run_id=payload.get("run_id"),
            result=payload.get("result"),
        )


@dataclass
class DuplicateSubmission(Exception):
    """Signals `submit()` saw an existing request_id; carries that record.

    Not an error condition — the caller should treat this as an idempotent
    no-op and use `.record` rather than re-deciding or re-completing.
    """

    record: RequestRecord = field(repr=False)

    def __str__(self) -> str:
        return f"duplicate submission for request_id={self.record.request_id!r}"


_REQUIRED_BINDING_FIELDS = ("project_id", "revision_id", "issue_id")


class RequestLedger:
    """File-backed, idempotent ledger for level-2 run-request handoff.

    Persistence is a single JSON file re-read/re-written on every call — this
    spike proves the state machine and persistence-across-restart property,
    not concurrent-writer safety (out of scope; see spike plan).
    """

    def __init__(self, store_path: Path) -> None:
        self._store_path = store_path
        if not self._store_path.exists():
            self._write_all({})

    def _read_all(self) -> dict[str, dict[str, Any]]:
        return json.loads(self._store_path.read_text())

    def _write_all(self, records: dict[str, dict[str, Any]]) -> None:
        self._store_path.write_text(json.dumps(records))

    def submit(self, request_id: str, binding: RequestBinding) -> RequestRecord:
        missing = [f for f in _REQUIRED_BINDING_FIELDS if not getattr(binding, f)]
        if missing:
            raise ValidationError(f"missing required binding fields: {missing}")

        records = self._read_all()
        if request_id in records:
            raise DuplicateSubmission(RequestRecord.from_json(records[request_id]))

        record = RequestRecord(
            request_id=request_id, binding=binding, status=RequestStatus.PENDING
        )
        records[request_id] = record.to_json()
        self._write_all(records)
        return record

    def decide(
        self, request_id: str, decision: Literal["accept", "reject"]
    ) -> RequestRecord:
        record = self._require(request_id)
        if record.status is not RequestStatus.PENDING:
            raise InvalidTransitionError(
                f"cannot decide request_id={request_id!r} from status "
                f"{record.status.value!r} (must be pending)"
            )
        record.status = (
            RequestStatus.ACCEPTED if decision == "accept" else RequestStatus.REJECTED
        )
        self._save(record)
        return record

    def complete(
        self,
        request_id: str,
        *,
        binding: RequestBinding,
        run_id: str,
        result: dict[str, Any],
    ) -> RequestRecord:
        record = self._require(request_id)
        if record.status is not RequestStatus.ACCEPTED:
            raise InvalidTransitionError(
                f"cannot complete request_id={request_id!r} from status "
                f"{record.status.value!r} (must be accepted)"
            )
        if record.binding != binding:
            raise BindingMismatchError(
                f"binding mismatch for request_id={request_id!r}: "
                f"stored={record.binding!r} supplied={binding!r}"
            )
        record.status = RequestStatus.COMPLETED
        record.run_id = run_id
        record.result = result
        self._save(record)
        return record

    def fail(self, request_id: str, *, error: str) -> RequestRecord:
        record = self._require(request_id)
        if record.status is not RequestStatus.ACCEPTED:
            raise InvalidTransitionError(
                f"cannot fail request_id={request_id!r} from status "
                f"{record.status.value!r} (must be accepted)"
            )
        record.status = RequestStatus.FAILED
        record.result = {"error": error}
        self._save(record)
        return record

    def observe(self, request_id: str) -> RequestRecord:
        """Read-only poll — models an async SSE-observed status check."""
        return self._require(request_id)

    def _require(self, request_id: str) -> RequestRecord:
        records = self._read_all()
        if request_id not in records:
            raise UnknownRequestError(f"no such request_id={request_id!r}")
        return RequestRecord.from_json(records[request_id])

    def _save(self, record: RequestRecord) -> None:
        records = self._read_all()
        records[record.request_id] = record.to_json()
        self._write_all(records)
