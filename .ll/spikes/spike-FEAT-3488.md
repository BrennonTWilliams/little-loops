# Spike Plan: FEAT-3488 — Level-2 host-mediated run-request ledger

## Context

FEAT-3488's `unproven_mechanism: true` frontmatter flag plus the explicit
`⚠ Unproven mechanism — no level-2 render target ever built` callout in the
issue's `### Codebase Research Findings` (line 56) lower outcome confidence.
Two canonical drivers apply:

**(a) Zero precedent in the codebase.** `docs/reference/ARTIFACT_CONTROL_LEVELS.md`'s
"Declared levels by render target" table lists only level 1 (`html-anything.yaml`
dashboards, `ui://` resources, `ll-artifact serve`'s event page,
`interaction_url=None` at `cli/artifact/serve.py:157`) and level 3
(`ll-loop run --serve` via `LocalBridgeTransport`). No render target has ever
declared level 2 ("ask-to-run-prompt"), and the doc deliberately leaves level 2's
wire shape as prose only — "the host's own normal session actions," no schema.
`HandoffBehavior.SPAWN` (`fsm/handoff_handler.py:29,68-94`), the doc's named
closest analog, is executor-triggered (fired by the executor's own
`SignalDetector` on loop output), not artifact/user-triggered from a rendered
page — it proves nothing about a browser-submitted request.

**(b) No existing test exercises the risky core.** `LocalBridgeTransport._handle_interaction()`
(`transport.py:692-716`) is level 3's only implemented interaction mechanism, and
it is structurally wrong for level 2: it responds `204` *before* touching its
inbound queue and does `put_nowait()` fire-and-forget with **no request-ID
correlation at all** — accept/reject/result concepts don't exist in it. No test
in `test_transport.py` or `test_feat3323_sse_bridge.py` exercises
request-ID-keyed idempotency, explicit host-decision gating, or revision-bound
immutability. Separately, no persistent request-ID/idempotency ledger exists
anywhere in this codebase — the three narrower conventions found in research
(`parallel/orchestrator.py:219` in-memory `set()`, `rn_synth_queue.py`'s
`done/<node_id>.done` sentinel files, `mcp_server/tools.py`'s declarative
`idempotent_hint` annotation) are each scoped to one process or one narrow
use case, none reusable directly as a request-ID ledger.

The spike must rule out: (1) a level-2 mechanism accidentally reusing level-3's
auto-consumed-queue shape (violating the doc's "host session, not the executor,
owns the decision" requirement), and (2) a request-ID ledger that either loses
state across a process restart or lets a duplicate submission trigger a second
decision/effect.

## Approach

Build a `level2_run_handoff` library under `scripts/tests/spike/` implementing a
file-backed `RequestLedger`: `submit()` creates a `pending` record keyed by
`request_id`, bound immutably to `(project_id, revision_id, issue_id)`; a
separate, explicit `decide()` call — standing in for a human/agent host session
action, never invoked automatically by `submit()` — transitions the record to
`accepted`/`rejected`; `complete()` (only reachable after `accepted`) attaches a
result and a run identifier. A driver simulates the full scenario: submit →
(nothing happens automatically) → explicit host `decide()` → `complete()` →
async `observe()` polling reflects each transition, mirroring "observed over an
already-open SSE stream" without a synchronous decision in the submit response.

What is faked: the actual HTTP POST/SSE wire framing (replaced by direct Python
calls into the ledger API) and the "host session" (replaced by an explicit
`decide()` call). What is real: file-backed persistence (actual file I/O,
actual reload in a fresh process-simulating `RequestLedger` instance), the
state machine's transition guards, and the idempotency/immutability invariants
— these are the risky core; faking only the wire layer removes accidental
complexity, not mechanism risk.

## Critical files

**Read-only production references** (the spike imports from or cites, never
modifies):
- `docs/reference/ARTIFACT_CONTROL_LEVELS.md:16-71` — the three-level table,
  prohibitions ("must not emit above its level"), and the level-2 prose contract
  the spike's state machine must match
- `scripts/little_loops/transport.py:692-716` — `LocalBridgeTransport._handle_interaction()`,
  cited as the contrasting level-3 shape the spike must NOT reproduce (fire-and-forget,
  no request-ID correlation)
- `scripts/little_loops/cli/artifact/serve.py:138-163` — `_make_page_html_factory`,
  the existing level-1 declaration (`interaction_url=None`) this issue's
  level-2 target must not silently upgrade past
- `scripts/little_loops/fsm/handoff_handler.py:29,68-94` — `HandoffBehavior.SPAWN`,
  cited as the doc's named non-identical analog (executor-triggered, not
  artifact-triggered)
- `scripts/little_loops/mcp_server/resources.py:60-69` — `_ResourceEntry`,
  confirmed to have no `ArtifactControlLevel`-valued field yet (the doc's
  named, not-yet-built forward slot)

**New spike paths** (created in this skill):
- `scripts/tests/spike/level2_run_handoff/__init__.py`
- `scripts/tests/spike/level2_run_handoff/ledger.py` — `RequestLedger`, `RequestRecord`
- `scripts/tests/spike/level2_run_handoff/driver.py` — end-to-end scenario driver
- `scripts/tests/spike/level2_run_handoff/test_level2_run_handoff.py` — AC test class

## Implementation

```
scripts/tests/spike/level2_run_handoff/
├── __init__.py
├── ledger.py                        # RequestLedger: submit/decide/complete/observe
├── driver.py                        # simulates browser-submit -> host-decide -> observe
└── test_level2_run_handoff.py       # AC test class
```

**Public API sketch:**

```python
# ledger.py
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Literal

class RequestStatus(str, Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    COMPLETED = "completed"
    FAILED = "failed"

@dataclass(frozen=True)
class RequestBinding:
    project_id: str
    revision_id: str
    issue_id: str

@dataclass
class RequestRecord:
    request_id: str
    binding: RequestBinding
    status: RequestStatus
    run_id: str | None = None
    result: dict | None = None

class DuplicateSubmission(Exception):
    """Raised distinctly from validation errors; carries the existing record."""

class RequestLedger:
    def __init__(self, store_path: Path) -> None: ...
    def submit(self, request_id: str, binding: RequestBinding) -> RequestRecord:
        """Creates a PENDING record. Raises on missing binding fields.
        A duplicate request_id returns the existing record unchanged —
        never re-creates or re-triggers a decision."""
    def decide(self, request_id: str, decision: Literal["accept", "reject"]) -> RequestRecord:
        """Explicit host-session action. Only legal from PENDING."""
    def complete(self, request_id: str, *, run_id: str, result: dict) -> RequestRecord:
        """Only legal from ACCEPTED. Binding is immutable — raises if the
        caller's binding no longer matches the stored one."""
    def observe(self, request_id: str) -> RequestRecord:
        """Read-only poll, models an async SSE-observed status check."""

# driver.py
def run_accept_scenario(ledger: RequestLedger, binding: RequestBinding) -> RequestRecord: ...
def run_reject_scenario(ledger: RequestLedger, binding: RequestBinding) -> RequestRecord: ...
```

## Acceptance Criteria → Test Table

| Test | Retires (AC / risk) | Kind |
|------|---------------------|------|
| `test_submit_creates_pending_record_not_auto_decided` | Risk (a): level-2 must not auto-execute like level-3's queue; host session owns the decision | behavior |
| `test_decide_accept_then_complete_exposes_run_id_and_result` | AC: accepted requests expose status and a run identifier | behavior |
| `test_decide_reject_leaves_no_run_id` | AC: rejection is a tested, distinct terminal state | behavior |
| `test_duplicate_submit_returns_existing_record_without_retriggering` | AC: duplicate-submission case tested; risk (b): no existing dedup convention is directly reusable | behavior |
| `test_submit_rejects_missing_binding_fields` | AC: validation failure / missing issue ID cases tested | behavior |
| `test_complete_rejects_binding_mismatch` | AC: bound to exact policy revision/project/issue ID; stale-revision-shaped tampering rejected | behavior |
| `test_ledger_persists_across_process_restart` | Risk (b): no persistent request-ID ledger exists anywhere in this codebase today | behavior |
| `test_observe_reflects_transitions_without_synchronous_decision_in_submit` | Risk (a): level-2's async-observed contract, contrasted with a synchronous response | behavior |
| `test_spike_does_not_import_local_bridge_transport` | Isolation guard: proves this is a structurally separate mechanism, not a level-3 queue reuse (doc prohibits emitting/behaving above/outside a declared level) | regression |

## Verification

All commands must exit 0 (foreground-blocking, never backgrounded):

```bash
python -m pytest scripts/tests/spike/level2_run_handoff/ -v
python -m pytest scripts/tests/test_transport.py -v
python -m pytest scripts/tests/test_wiring_reference_docs.py -v
```

The first command runs the spike's AC suite. The second confirms
`LocalBridgeTransport` (level 3) is untouched and its own tests still pass —
the spike must not have been tempted to extend or monkeypatch it. The third
confirms the `ARTIFACT_CONTROL_LEVELS.md` doc-string pins
(`DOC_STRINGS_PRESENT`, `test_wiring_reference_docs.py:216`) are unaffected,
since this spike documents against but never edits that file.

## Out of Scope

- Real HTTP/SSE wire transport or browser-side JS (the spike is in-process
  throughout; `observe()` is a direct poll, not a socket read)
- Wiring a route into `cli/artifact/serve.py` or registering
  `ArtifactControlLevel` on `mcp_server/resources.py::_ResourceEntry` (both
  the doc's named, not-yet-built forward slots — FEAT-3488's implementation
  job, not this spike's)
- Canonical YAML validation (`load_and_validate`) or actually invoking an FSM
  run — the ledger only proves the request/decision/observe state machine
- Any policy-builder JS/UI surface — this spike proves the Python-side
  handoff mechanism only, independent of `policy_builder_core.mjs`

## Promotion

On acceptance, promote `scripts/tests/spike/level2_run_handoff/` to
`scripts/little_loops/spike/level2_run_handoff/` in a separate PR (mirrors the
ENH-2565 spike-promotion pattern). The promoted `RequestLedger` becomes the
persistence/idempotency layer FEAT-3488's real level-2 render target wires into
`cli/artifact/serve.py`, with `decide()` invoked from whatever concrete host
surface (CLI prompt, MCP tool, etc.) the implementation refinement selects for
"host session decides" — that transport-selection question is explicitly
deferred per the issue's own Call Path note ("Transport registration and
concrete handler ownership require refinement before implementation").
