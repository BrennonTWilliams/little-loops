---
id: FEAT-1932
title: PushNotification adapter for async HITL communication
type: FEAT
priority: P2
captured_at: "2026-06-04T00:00:00Z"
discovered_date: 2026-06-04
discovered_by: scope-epic
status: open
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

**Response callback mechanism** (resolve during refinement):

- **Option A: Event bus subscription** — `EventBus.register()` with a glob
  filter for `human_response` events. The FSM emits `human_approval_request` on
  state entry; the adapter subscribes to `human_response` events matching the
  alert ID. Architecturally cleanest, but requires the response to come through
  the event bus (which may need a new transport).
- **Option B: File-poller** — Write alert to `.ll/hitl-responses/<alert-id>.json`;
  the operator (or a helper script) writes a response file; the adapter polls
  for it. Simpler, works cross-host, no event bus dependency. The response file
  is the callback.

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


## Session Log
- `/ll:format-issue` - 2026-06-05T22:18:11 - `cb5e8fb4-eab5-4e81-938d-fe8a00b0ba87.jsonl`
- `/ll:verify-issues` - 2026-06-05T21:00:23 - `current-session.jsonl`

- `/ll:verify-issues` - 2026-06-05T01:35:35 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/579edc97-1110-41b7-9283-1612d1e82fee.jsonl`