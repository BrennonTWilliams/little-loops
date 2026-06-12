---
id: FEAT-2102
title: Adapter-swap integration test for `human_approval` FSM state
type: FEAT
priority: P2
status: blocked
captured_at: "2026-06-12T00:00:00Z"
discovered_date: 2026-06-12
discovered_by: review-epic
parent: EPIC-1929
blocked_by: [FEAT-1930, FEAT-1931, FEAT-1932]
relates_to: [FEAT-1794]
labels:
  - fsm
  - hitl
  - testing
  - integration
---

# FEAT-2102: Adapter-swap integration test for `human_approval` FSM state

## Summary

Add a parametrized integration test proving that swapping HITL communication
adapters is a **config-only** change: the same loop YAML containing an
`action_type: human_approval` state runs unmodified against both the terminal
adapter (FEAT-1931) and the push-notification adapter (FEAT-1932), selected
solely via the `hitl.channel` key in `.ll/ll-config.json`.

## Motivation

EPIC-1929's acceptance gates include two cross-cutting criteria that no
existing child owns:

1. "Switching adapters is a config change, not a loop YAML change — the same
   loop works with either channel."
2. "The protocol interface is documented and a third-party adapter can be
   written against it without touching `executor.py`."

FEAT-1930 covers unit-level mock-adapter tests; FEAT-1931 and FEAT-1932 cover
unit tests for their respective adapters. The integration test that exercises
a real loop YAML across both channels is unowned — without it, the epic's
core promise is asserted but never verified.

## Acceptance Criteria

- [ ] A minimal fixture loop YAML containing one `action_type: human_approval`
  state lives under the test fixtures directory
- [ ] Parametrized test runs the fixture against a mock terminal adapter and a
  mock push adapter, switching only `hitl.channel` in config — the loop YAML
  bytes are identical across both runs (assert on file hash or shared fixture)
- [ ] Both runs route `send_alert()` / `await_response()` through the selected
  adapter (assert via adapter call records)
- [ ] A third "swap-back" case verifies no state leaks between adapter
  selections within one process
- [ ] Test asserts `executor.py` is not imported/patched per-adapter — adapter
  resolution goes through config + extension registry only

## Integration Map

### Files to Create
- `scripts/tests/test_hitl_adapter_swap.py` — the parametrized integration test
- Test fixture loop YAML (location per existing fixture conventions in
  `scripts/tests/`)

### Dependent Files
- `scripts/little_loops/fsm/communication_adapter.py` (FEAT-1930)
- Adapter implementations from FEAT-1931 / FEAT-1932
- `scripts/little_loops/fsm/executor.py` — adapter resolution under test

## Impact

- **Priority**: P2 — owns EPIC-1929's closure-gating acceptance criteria
- **Effort**: Small — one test module + fixture once the three blockers land
- **Risk**: Low — test-only change
- **Breaking Change**: No

## Status

**Blocked** | Created: 2026-06-12 | Priority: P2

Blocked by FEAT-1930 (protocol), FEAT-1931 (terminal adapter), and FEAT-1932
(push adapter) — all three must land before this test can be written.
