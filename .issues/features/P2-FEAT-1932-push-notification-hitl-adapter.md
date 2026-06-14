---
id: FEAT-1932
title: PushNotification adapter for async HITL communication
type: FEAT
priority: P2
captured_at: "2026-06-04T00:00:00Z"
discovered_date: 2026-06-04
discovered_by: scope-epic
status: blocked
blocked_by: [FEAT-1930]
parent: EPIC-1929
relates_to: [FEAT-1930, FEAT-1794, FEAT-1931]
labels:
  - fsm
  - harness
  - hitl
  - adapter
  - push-notification
---

# FEAT-1932: PushNotification adapter for async HITL communication

## Summary

Implement the `CommunicationAdapter` protocol (FEAT-1930) using the
`PushNotification` tool for outbound delivery and a response callback mechanism
for inbound verdict collection. This is the **first truly async channel** — the
FSM blocks, the operator receives a phone notification, and execution resumes
when they respond (or the timeout fires).

This adapter is what makes `human_approval` useful for unattended and
semi-attended automation. Without it, HITL means "watching the terminal."

## Current Behavior

HITL communication is currently synchronous and terminal-bound. When an FSM
enters a `human_approval` state, the operator must be watching the terminal to
respond. This defeats the purpose of unattended/semi-attended automation:
`ll-auto` runs over 30+ issues, multi-hour `harness-optimize` loops, and other
long-running FSM executions all stall waiting for terminal input.

## Expected Behavior

1. Implements `CommunicationAdapter.send_alert()`: formats the prompt + context
   as a push notification message (≤200 chars, per `PushNotification` limits),
   sends via the `PushNotification` tool, records the alert ID for response
   correlation.
2. Implements `CommunicationAdapter.await_response()`: blocks in a polling loop
   (using `_interruptible_sleep()` pattern) waiting for a response to arrive via
   the callback channel (event bus subscription or file-poller). On response,
   returns `HumanResponse`. On timeout, returns `TimeoutResponse`.
3. `supports_async()` returns `True` — the operator can respond from their phone
   while away from the terminal.
4. If `PushNotification` is unavailable (host doesn't support it, or no
   notification target configured), adapter reports `is_available() → False` so
   the system can fall back to the terminal adapter.

## Use Case

**Who**: A developer running `ll-auto` over 30+ issues overnight, or a
multi-hour `harness-optimize` loop that may hit approval gates.

**Context**: The FSM reaches a `human_approval` state requiring operator
judgment (e.g., "this refactor changes 15 files — proceed?"). The operator is
away from the terminal — at dinner, in a meeting, or asleep.

**Goal**: Receive a push notification on their phone with a concise summary of
the approval request, review it, and respond with approve/reject/edit — all
without returning to the terminal.

**Outcome**: The FSM resumes execution with the operator's verdict. If the
operator does not respond within the timeout window, the FSM follows the
default path and sends a follow-up notification confirming the timeout.

## Motivation

FEAT-1794's core use case is unattended/semi-attended automation: `ll-auto` over
30 issues, multi-hour `harness-optimize` runs. A `human_approval` state that
requires the operator to be at the terminal defeats that purpose. The
PushNotification adapter makes HITL genuinely async — the operator gets paged,
reviews on their phone, and the FSM resumes.

## Acceptance Criteria

- [ ] Implements `CommunicationAdapter` protocol
- [ ] `send_alert()` truncates to PushNotification's character limit, includes
  state name and response instructions
- [ ] `await_response()` polls for a response via the chosen callback mechanism;
  respects FSM shutdown signal during polling
- [ ] Response callback mechanism supports three verdicts: approve, reject, edit
  (with edited text)
- [ ] Timeout returns `TimeoutResponse` and sends a follow-up notification
  ("HITL request timed out — FSM resumed on default path")
- [ ] `supports_async()` returns `True`
- [ ] `is_available()` returns `False` when PushNotification tool is unavailable
  or no target is configured
- [ ] Tests: mock PushNotification tool, verify message format, response parsing,
  timeout fallback, unavailability detection

## API/Interface

```python
class PushNotificationAdapter(CommunicationAdapter):
    """PushNotification-based async HITL adapter.

    Sends alerts via the PushNotification tool and awaits responses
    through a callback channel (event bus or file-poller).
    """

    def send_alert(self, prompt: str, context: dict) -> str:
        """Format prompt as ≤200 char push notification, send it,
        return alert_id for response correlation."""

    def await_response(self, alert_id: str, timeout: float) -> HumanResponse | TimeoutResponse:
        """Block in polling loop waiting for response to arrive via
        callback channel. Returns HumanResponse on receipt,
        TimeoutResponse if deadline expires. Respects FSM shutdown
        signal during polling."""

    def supports_async(self) -> bool:
        """Returns True — this adapter supports phone-based responses."""

    def is_available(self) -> bool:
        """Returns False when PushNotification tool is unavailable
        or no notification target is configured, so the system can
        fall back to the terminal adapter."""
```

## Proposed Solution

**Response callback mechanism**:

> **Selected:** Option B — file-poller — works cross-host with no new inbound transport, and the issue's own implementation steps already specify a polling loop; the event bus has no path for an off-terminal operator's response to enter the process.

- **Option A: Event bus subscription** — `EventBus.register()` with a glob
  filter for `human_response` events. The FSM emits `human_approval_request` on
  state entry; the adapter subscribes to `human_response` events matching the
  alert ID. Architecturally cleanest, but requires the response to come through
  the event bus (which may need a new transport).
- **Option B: File-poller** — Write alert to `.ll/hitl-responses/<alert-id>.json`;
  the operator (or a helper script) writes a response file; the adapter polls
  for it. Simpler, works cross-host, no event bus dependency. The response file
  is the callback.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-06-12 (epic audit follow-through, paired with the FEAT-1930 extension-protocol decision).

**Selected**: Option B — file-poller (`.ll/hitl-responses/<alert-id>.json`).

**Reasoning**: The push-notification operator is by definition away from the terminal, often on another device; their response has no existing path into the in-process `EventBus` — Option A would require building a new inbound transport (existing transports `UnixSocketTransport`/`WebhookTransport` in `transport.py` serve outbound/local delivery) before the adapter could work at all. Option B needs zero new infrastructure, works cross-host, and matches the implementation steps already written for this issue (`await_response()` polling loop with `_interruptible_sleep()`). An event-bus subscription can layer on later as a v2 latency optimization without changing the `CommunicationAdapter` protocol surface.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| A — event bus subscription | 1/3 | 1/3 | 2/3 | 1/3 | 5/12 |
| B — file-poller | 2/3 | 3/3 | 3/3 | 3/3 | 11/12 |

**Push notification format**: The `PushNotification` tool has a ~200 char
message limit. The adapter should send a concise summary + instructions, not the
full prompt. The operator can request more context if needed (v2 enhancement).

## Implementation Steps

1. Implement `CommunicationAdapter` protocol base in `push_adapter.py`
   (depends on FEAT-1930 for the protocol interface)
2. Implement `send_alert()` — format prompt as ≤200 char push notification,
   send via `PushNotification` tool, record alert ID for correlation
3. Implement `await_response()` — polling loop with `_interruptible_sleep()`,
   FSM shutdown signal respect, response parsing for approve/reject/edit
   verdicts
4. Implement response callback mechanism (event bus subscription or
   file-poller per Proposed Solution options A/B; resolve during refinement)
5. Implement `is_available()` capability detection and `supports_async()`
   returning `True`
6. Add comprehensive tests: mock `PushNotification` tool, verify message
   format, response parsing, timeout fallback, unavailability detection
7. Register adapter in `extension.py`; add `hitl.push.target` to config schema
8. Run tests and verify end-to-end with a mock FSM hitting `human_approval`

## Integration Map

### Files to Create
- `scripts/little_loops/fsm/adapters/push_adapter.py` —
  `PushNotificationAdapter(CommunicationAdapter)`
- `scripts/tests/test_push_adapter.py`

### Files to Modify
- `scripts/little_loops/extension.py` — register `PushNotificationAdapter`
- `scripts/little_loops/fsm/executor.py` — no changes (uses protocol interface)
- `.ll/ll-config.json` schema — `hitl.push.target` for notification routing

### Dependencies
- `PushNotification` tool (must exist in the host; verify capability before use)
- FEAT-1930 (protocol interface)
- FEAT-1794 (FSM state that calls this adapter)

## Impact

- **Priority**: P2 — unlocks unattended HITL, the primary use case
- **Effort**: Medium — protocol implementation + callback mechanism + push
  formatting + availability detection
- **Risk**: Medium — depends on `PushNotification` tool availability across
  hosts; needs graceful degradation when unavailable
- **Breaking Change**: No

## Related Key Documentation

- `docs/reference/API.md` — FSM adapter protocol and HITL integration
- `docs/ARCHITECTURE.md` — HITL system design and communication channel overview

---
## Status

open

## Verification Notes (2026-06-05)

- **Line drift**: References `executor.py:1647 _interruptible_sleep` — now at L1735 (drift +88).
- References `PushNotification` tool which does not exist in codebase (per FEAT-1794).
- Proposed file `scripts/little_loops/fsm/adapters/push_adapter.py` does not exist (expected).


---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts` 2026-06-09): FEAT-1794's codebase research explicitly states that the `PushNotification` tool does not currently exist in the codebase and defers it to v2 scope. This issue should be treated as **blocked until a concrete push notification transport (PushNotification tool, webhook, or equivalent) is available**. Add `blocked_by` tracking for the transport prerequisite before starting implementation; otherwise the `send_alert()` step has no callable API.

**Note** (added by `/ll:audit-issue-conflicts` 2026-06-09): The `API/Interface` section above shows `PushNotificationAdapter.send_alert(prompt, context)` but the `CommunicationAdapter` protocol in FEAT-1930 defines `send_alert(loop_name, state_name, prompt, captured_context, timeout) -> str` (returning an `alert_id`). Align this issue's `send_alert()` signature with FEAT-1930's protocol **before** implementing — the mismatch will produce a non-conforming `CommunicationAdapter` implementation. Also add the `alert_id` return type to match the `await_response(alert_id, timeout)` correlation contract.

## Verification Notes (2026-06-13)

- `_interruptible_sleep` has drifted further — current location is `executor.py:1766` (previous verification note said 1735; issue body says 1647). Update before implementing.
- `PushNotification` tool remains absent from codebase; scope boundary blocker condition unchanged.

2026-06-13: Line number drift: `_interruptible_sleep` now at :1766 (was :1647). Signature mismatch with FEAT-1930 protocol (missing `loop_name`, `state_name` params, missing `alert_id` return). Hard blocker: `PushNotification` tool does not exist in the codebase — a concrete push transport must be identified or created before this issue can proceed.

## Session Log
- `/ll:verify-issues` - 2026-06-14T00:12:58 - `dcbaf608-eff5-4e7b-8a64-4d13a266c421.jsonl`
- `/ll:verify-issues` - 2026-06-13T21:13:57 - `cfa3cf65-c671-4bf6-a513-92cc448d76e6.jsonl`
- `/ll:decide-issue` - 2026-06-12T16:31:51 - `5f156fda-1001-478e-926c-73ffddf7e4b1.jsonl`
- `/ll:audit-issue-conflicts` - 2026-06-09T14:41:01 - `f2966d2e-3f0a-473f-b22c-b54b2a15ad9c.jsonl`
- `/ll:format-issue` - 2026-06-05T22:18:11 - `cb5e8fb4-eab5-4e81-938d-fe8a00b0ba87.jsonl`
- `/ll:verify-issues` - 2026-06-05T21:00:23 - `current-session.jsonl`

- `/ll:verify-issues` - 2026-06-05T01:35:35 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/579edc97-1110-41b7-9283-1612d1e82fee.jsonl`