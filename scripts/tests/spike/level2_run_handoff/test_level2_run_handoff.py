"""AC suite for the FEAT-3488 level-2 run-request ledger spike.

See ../../../../.ll/spikes/spike-FEAT-3488.md for the plan and risk mapping.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from scripts.tests.spike.level2_run_handoff.driver import (
    run_accept_scenario,
    run_reject_scenario,
)
from scripts.tests.spike.level2_run_handoff.ledger import (
    BindingMismatchError,
    DuplicateSubmission,
    RequestBinding,
    RequestLedger,
    RequestStatus,
    ValidationError,
)

BINDING = RequestBinding(project_id="proj-1", revision_id="rev-1", issue_id="FEAT-3488")


@pytest.fixture
def ledger(tmp_path: Path) -> RequestLedger:
    return RequestLedger(tmp_path / "ledger.json")


def test_submit_creates_pending_record_not_auto_decided(ledger: RequestLedger) -> None:
    record = ledger.submit("req-1", BINDING)
    assert record.status is RequestStatus.PENDING
    assert record.run_id is None
    # No side effect from submit() alone re-reading the store.
    assert ledger.observe("req-1").status is RequestStatus.PENDING


def test_decide_accept_then_complete_exposes_run_id_and_result(
    ledger: RequestLedger,
) -> None:
    record = run_accept_scenario(ledger, "req-2", BINDING)
    assert record.status is RequestStatus.COMPLETED
    assert record.run_id == "run-req-2"
    assert record.result == {"status": "ok"}


def test_decide_reject_leaves_no_run_id(ledger: RequestLedger) -> None:
    record = run_reject_scenario(ledger, "req-3", BINDING)
    assert record.status is RequestStatus.REJECTED
    assert record.run_id is None


def test_duplicate_submit_returns_existing_record_without_retriggering(
    ledger: RequestLedger,
) -> None:
    first = ledger.submit("req-4", BINDING)
    ledger.decide("req-4", "accept")

    with pytest.raises(DuplicateSubmission) as excinfo:
        ledger.submit("req-4", BINDING)

    # The duplicate submission surfaces the *current* record — already
    # accepted, not reset to pending, and no second decision was made.
    assert excinfo.value.record.status is RequestStatus.ACCEPTED
    assert excinfo.value.record.request_id == first.request_id


def test_submit_rejects_missing_binding_fields(ledger: RequestLedger) -> None:
    incomplete = RequestBinding(project_id="proj-1", revision_id="", issue_id="FEAT-3488")
    with pytest.raises(ValidationError):
        ledger.submit("req-5", incomplete)
    with pytest.raises(Exception):
        ledger.observe("req-5")


def test_complete_rejects_binding_mismatch(ledger: RequestLedger) -> None:
    ledger.submit("req-6", BINDING)
    ledger.decide("req-6", "accept")
    stale_binding = RequestBinding(
        project_id="proj-1", revision_id="rev-STALE", issue_id="FEAT-3488"
    )
    with pytest.raises(BindingMismatchError):
        ledger.complete(
            "req-6", binding=stale_binding, run_id="run-req-6", result={"status": "ok"}
        )
    # The record is untouched by the rejected completion attempt.
    assert ledger.observe("req-6").status is RequestStatus.ACCEPTED


def test_ledger_persists_across_process_restart(tmp_path: Path) -> None:
    store_path = tmp_path / "ledger.json"
    first_process = RequestLedger(store_path)
    run_accept_scenario(first_process, "req-7", BINDING)

    # A fresh RequestLedger instance simulates a new process reading the
    # same on-disk store — proves state survives a restart, which none of
    # the codebase's three narrower idempotency conventions demonstrate.
    second_process = RequestLedger(store_path)
    record = second_process.observe("req-7")
    assert record.status is RequestStatus.COMPLETED
    assert record.run_id == "run-req-7"


def test_observe_reflects_transitions_without_synchronous_decision_in_submit(
    ledger: RequestLedger,
) -> None:
    submitted = ledger.submit("req-8", BINDING)
    # submit()'s own return value never carries a decision — only PENDING.
    assert submitted.status is RequestStatus.PENDING

    ledger.decide("req-8", "accept")
    assert ledger.observe("req-8").status is RequestStatus.ACCEPTED

    ledger.complete(
        "req-8", binding=BINDING, run_id="run-req-8", result={"status": "ok"}
    )
    assert ledger.observe("req-8").status is RequestStatus.COMPLETED


def test_spike_does_not_import_local_bridge_transport() -> None:
    """Regression guard: this mechanism must stay structurally separate from
    level 3's LocalBridgeTransport / auto-consumed inbound queue — reusing it
    would silently promote this render target past its declared level.
    """
    spike_dir = Path(__file__).parent
    forbidden = {"transport", "LocalBridgeTransport"}

    for py_file in spike_dir.glob("*.py"):
        tree = ast.parse(py_file.read_text(), filename=str(py_file))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = {alias.name.split(".")[-1] for alias in node.names}
            elif isinstance(node, ast.ImportFrom):
                names = {alias.name for alias in node.names}
                if node.module:
                    names.add(node.module.split(".")[-1])
            else:
                continue
            assert not (names & forbidden), (
                f"{py_file.name} imports forbidden name(s) "
                f"{names & forbidden} — level-2 spike must not depend on "
                f"level-3's LocalBridgeTransport"
            )
