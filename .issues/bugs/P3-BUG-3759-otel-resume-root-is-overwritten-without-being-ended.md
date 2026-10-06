---
id: BUG-3759
type: BUG
title: OTel resume root is overwritten without being ended
priority: P3
status: open
discovered_by: capture-issue
discovered_date: '2026-10-06'
captured_at: '2026-10-06T09:07:03Z'
labels:
- telemetry
- transport
relates_to:
- BUG-3755
learning_tests_required:
- opentelemetry-sdk
---

# BUG-3759: OTel resume root is overwritten without being ended

## Summary

During a real `PersistentExecutor.resume()`, OTel opens a root for `loop_resume`, then receives `loop_start` and overwrites that active root without ending it. The abandoned span is never delivered to the exporter. This is separate from BUG-3755's span-name lookup defect and persists even if both names are corrected.

## Current Behavior

`PersistentExecutor.resume` emits `loop_resume`, then calls `run(clear_previous=False)` (`scripts/little_loops/fsm/persistence.py:1465-1482`). `FSMExecutor.run` unconditionally emits `loop_start` (`scripts/little_loops/fsm/executor.py:678`).

`OTelTransport._handle_loop_resume` (`scripts/little_loops/transport.py:1787`) closes prior spans and starts a root. `_handle_loop_start` (`:1783`) replaces `_loop_span` with another root without ending the first. At completion, only the replacement root is ended. `close()` flushes/shuts down the provider; it does not end the abandoned root.

Review reproduction on main `3286729a2`: an interrupted saved state resumed through the actual event bus opened two root spans, one for `loop_resume` and one for `loop_start`, but `InMemorySpanExporter.get_finished_spans()` returned only one root. The proven `opentelemetry-sdk` learning test establishes that `start_span` spans are exported only after `end()`.

## Expected Behavior

Both span-opening events keep their documented behavior of opening a root. Before a start/resume replaces an active root, its open state/action descendants and the root are ended. Every root created for the normal resumed execution is therefore exported; no span is abandoned merely by overwriting its reference. State/action children attach to the current root, and the final root retains completion attributes/status. A root replaced before completion keeps its existing unset status.

This issue owns closing spans before root replacement. It does not require removing or renaming producer events, changing their run IDs, or changing the schema. Both producer events are consumed by other sinks and should keep their established behavior.

## Motivation

Missing resumed-root spans make exported traces incomplete and can conceal a broken `loop_resume` name handler when a test checks only the final exported root. This is a P3 defect in an optional tracing sink.

## Proposed Solution

Apply the existing resume handler's close-before-replace lifecycle to `loop_start`: end open state/action spans, end any active root, and then create the new root. Consecutive resume/start events still open their documented roots; both are ended/exported, and children attach to the replacement root. Keep final-status assignment on `loop_complete` and preserve producer behavior.

## Integration Map

### Files to Modify

- `scripts/little_loops/transport.py` — ownership/lifetime of the active root in the start/resume handlers.
- `scripts/tests/test_transport.py` and a real-resume producer-to-sink regression module under `scripts/tests/` — created/ended root accounting and lifecycle/parentage checks.
- `docs/reference/EVENT-SCHEMA.md` and `docs/reference/API.md` — trace lifecycle wording if the consecutive-event behavior needs clarification.

### Dependent Files

- `scripts/little_loops/fsm/persistence.py:1465` and `scripts/little_loops/fsm/executor.py:678` — the actual resume/start producers; preserve their contracts.
- `scripts/tests/test_fsm_persistence.py:1322` and `:1359` — current resume event and run-ID stability coverage.
- `.ll/learning-tests/opentelemetry-sdk.md` — proven start/end/export lifecycle; no new external API is needed.

## Program Design

### Types

OTel `_loop_span`, `_state_span`, and `_action_span` represent live spans owned by the transport; replacing a live reference must retain or terminate its span.

### Signatures

- `OTelTransport._handle_loop_start(self, event: dict[str, Any]) -> None`
- `OTelTransport._handle_loop_resume(self, event: dict[str, Any]) -> None`

Existing signatures stay intact. Start follows resume's existing close-before-replace lifecycle so each documented span-opening event still creates a root.

### Call Path

`PersistentExecutor.resume` → `loop_resume` → `OTelTransport._handle_loop_resume` → `FSMExecutor.run` → `loop_start` → `_handle_loop_start` → state/action/completion events.

## Implementation Steps

1. The active-root lifecycle handles the real consecutive resume/start events with explicit ownership and no abandoned spans.
2. A real resumed execution establishes created/ended span-ID accounting, correct child parentage, and completion status alongside existing fresh-start coverage.
3. Trace lifecycle documentation and the targeted/full suites agree with the selected behavior.

## Impact

- **Priority**: P3 — a lost root span in the optional tracing sink; execution and SQLite history are unaffected.
- **Effort**: Small — align root replacement with existing resume behavior and add regression coverage.
- **Risk**: Low — span counts increase by exporting the previously abandoned root; consumers must not assume one root per resumed segment.
- **Breaking Change**: No event/schema change; exported traces now include the previously missing root.

## Root Cause

- **File**: `scripts/little_loops/transport.py`
- **Anchor**: `OTelTransport._handle_loop_start` / `_handle_loop_resume`
- **Cause**: span-opening handlers do not account for the real producer's consecutive resume/start sequence; start overwrites an active root without closing/reusing it.

## Steps to Reproduce

1. Save an interrupted `LoopState` in a temporary persistence directory.
2. Construct a real `PersistentExecutor` with a deterministic action runner and attach OTel with `TracerProvider`, `SimpleSpanProcessor`, and `InMemorySpanExporter`. Pin `LL_HISTORY_DB` to temporary storage.
3. Record the root spans opened while calling `resume()` and running to completion; observe both `loop_resume` and `loop_start`.
4. Compare created root IDs with finished/exported IDs after closing the transport. The first root is absent from finished spans.

## Acceptance Criteria

- [ ] A real resume → event-bus → OTel regression test proves every transport-created root is ended/exported after completion, including the root opened for `loop_resume`.
- [ ] The test asserts distinct exported resume/start root IDs, state/action parentage under the start root, and final outcome attributes/status on that root; checking names alone is insufficient. The replaced resume root remains unset and has no completion attributes.
- [ ] Fresh-start execution and an existing-root → resume sequence retain valid state/action parentage and end their spans; existing OTel outcome and nested-event filtering tests pass.
- [ ] Producer event shapes, ordering, and stable resumed run IDs retain their current contracts. This fix adds no database migration and is independently implementable from BUG-3755 and BUG-3758.
- [ ] Regression tests use temporary history/persistence paths, an in-memory exporter, and skip if either the SDK or OTLP gRPC exporter is absent; no network exporter is invoked. The transport/persistence suites and full local suite pass.

## Related

- BUG-3755 — identity repair; its resume tests must observe the resume root directly because the current replacement masks it.
- BUG-3758 — unrelated route persistence follow-up from the same review.

## Related Key Documentation

| Category | Document | Relevance |
|---|---|---|
| architecture | `docs/reference/API.md` | OTel transport lifecycle. |

## Status

**Open** | Created: 2026-10-06 | Priority: P3


## Session Log
- `/ll:capture-issue` - 2026-10-06T09:07:39 - `69fbb543-02d8-48e4-bbb6-a2a33935a7ec.jsonl`
