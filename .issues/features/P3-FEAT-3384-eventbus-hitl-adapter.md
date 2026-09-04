---
id: FEAT-3384
type: FEAT
title: EventBus HITL adapter
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-04'
captured_at: '2026-09-04T07:05:03Z'
parent: EPIC-1929
labels:
- fsm
- harness
- hitl
- extension
blocked_by:
- FEAT-1930
---

# FEAT-3384: EventBus HITL adapter

## Summary

Implement the `eventbus` `CommunicationAdapter` (FEAT-1930): a HITL channel
that emits a `human_approval_requested` event (`HUMAN_APPROVAL_REQUESTED_EVENT`,
from `little_loops.fsm.communication_adapter`) via `send_alert()`, then resumes
`await_response()` when a matching `human_response` event
(`HUMAN_RESPONSE_EVENT`) arrives for the same `alert_id`. This is the async
channel Hermes consumes and relays to whatever channel the operator is on
(text, Telegram, etc.) — replacing the cancelled bespoke PushNotification
adapter (FEAT-1932, cancelled 2026-06-20).

## Current Behavior

[If applicable - describe what currently happens]

## Expected Behavior

[What should happen instead]

## Motivation

FEAT-1930's 2026-06-20 re-scope resolved Open Question #2 (event bus vs.
file-poller for the inbound callback) in favor of the event bus — that is
precisely the surface Hermes already subscribes to via the EventBus/extension
system, so no new inbound transport is needed. FEAT-1930 Pre-implementation
Review #7 (2026-09-04) scoped this adapter out to its own child issue rather
than bundling it into FEAT-1930, to keep that issue at its stated "Small"
effort.

## Proposed Solution

TBD - requires investigation

## Integration Map

### Files to Modify
- TBD - requires codebase analysis

### Dependent Files (Callers/Importers)
- TBD - use grep to find references

### Similar Patterns
- TBD - search for consistency

### Tests
- TBD - identify test files to update

### Documentation
- TBD - docs that need updates

### Configuration
- N/A or list config files

## Implementation Steps

1. [Major phase 1]
2. [Major phase 2]
3. [Verification approach]

## Impact

- **Priority**: [P0-P5] - [Justification]
- **Effort**: [Small/Medium/Large] - [Justification]
- **Risk**: [Low/Medium/High] - [Justification]
- **Breaking Change**: [Yes/No]

## Acceptance Criteria

- [ ] `EventBusAdapter(CommunicationAdapter)` implements `send_alert()`
  (emits `HUMAN_APPROVAL_REQUESTED_EVENT` with `loop_name`, `state_name`,
  `prompt`, `captured_context`, and a generated `alert_id`),
  `await_response()` (re-entrant per `alert_id`, per FEAT-1930's contract —
  polls/subscribes for a matching `HUMAN_RESPONSE_EVENT`, retains an
  unconsumed verdict across `TimeoutResponse`s), and `supports_async()`
  returning `True`
- [ ] Registers via a `CommunicationAdapterExtension` (`provided_adapters()`
  returns `{"eventbus": EventBusAdapter(...)}`), consistent with FEAT-1931's
  `TerminalAdapter` registration pattern
- [ ] `cancel_alert()` override withdraws a pending alert (no-op default on
  the base class is insufficient for an async channel — a late verdict must
  not target a dead alert per FEAT-1930 Review #15)
- [ ] Tests: adapter emits the correct event shape, resolves a verdict from a
  matching `human_response` event, re-entrancy across repeated
  `await_response()` calls, `cancel_alert()` withdraws the alert

## Related Key Documentation

- `scripts/little_loops/fsm/communication_adapter.py` — `CommunicationAdapter`
  ABC, `AdapterResponse`/`TimeoutResponse`, event-name constants (FEAT-1930)
- `scripts/little_loops/extension.py` — `CommunicationAdapterExtension`
  Protocol, `wire_extensions()` registration path
- `scripts/little_loops/events.py` — `EventBus` — the pub/sub surface this
  adapter subscribes to for inbound `human_response` events

## Status

**Open** | Created: 2026-09-04 | Priority: P3


## Session Log
- `/ll:manage-issue` - 2026-09-04T07:19:43 - `edcf388a-123e-4783-8b95-eba3c9e4b3da.jsonl`
