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

---
## Status

open
