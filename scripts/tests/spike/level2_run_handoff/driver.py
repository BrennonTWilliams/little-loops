"""End-to-end scenario driver for the level-2 run-request ledger spike.

Simulates the full handoff: a browser-shaped `submit()`, an explicit
host-session `decide()` (never automatic), then either `complete()` or
`fail()`, observed asynchronously via `observe()`.
"""

from __future__ import annotations

from .ledger import RequestBinding, RequestLedger, RequestRecord


def run_accept_scenario(
    ledger: RequestLedger, request_id: str, binding: RequestBinding
) -> RequestRecord:
    ledger.submit(request_id, binding)
    ledger.decide(request_id, "accept")
    return ledger.complete(
        request_id,
        binding=binding,
        run_id=f"run-{request_id}",
        result={"status": "ok"},
    )


def run_reject_scenario(
    ledger: RequestLedger, request_id: str, binding: RequestBinding
) -> RequestRecord:
    ledger.submit(request_id, binding)
    return ledger.decide(request_id, "reject")
