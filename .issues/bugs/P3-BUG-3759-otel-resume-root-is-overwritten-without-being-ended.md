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
- BUG-3758
learning_tests_required:
- opentelemetry-sdk
---

# BUG-3759: OTel resume root is overwritten without being ended

## Summary

During a real `PersistentExecutor.resume()`, OTel opens a root for `loop_resume`, then receives `loop_start` and overwrites that active root without ending it. The abandoned span is never delivered to the exporter. This remains after BUG-3755's completed span-name repair.

## Current Behavior

`PersistentExecutor.resume` emits `loop_resume`, then calls `run(clear_previous=False)`. `FSMExecutor.run` unconditionally emits `loop_start`; their source anchors are listed in the Integration Map.

`OTelTransport._handle_loop_resume` in `scripts/little_loops/transport.py` closes prior spans and starts a root. `_handle_loop_start` replaces `_loop_span` with another root without ending the first or clearing live descendants. At completion, only the replacement root is ended. `close()` flushes/shuts down the provider; it does not end the abandoned root.

Review reproduction on `main` at `fec7d6462`: an interrupted saved state resumed through the actual event bus opened two same-name root spans, one for `loop_resume` and one for `loop_start`, but `InMemorySpanExporter.get_finished_spans()` returned only one root before close and after repeated close. The abandoned root was still recording. A direct `loop_start` replacement with live state/action spans also leaves those old descendants open until later events close them. The corresponding `loop_resume` replacement already closes action → state → root before starting its replacement.

The proven `opentelemetry-sdk` learning test establishes that `start_span` spans are exported only after `end()`. A review probe also confirmed that two calls to the same span's `end()` produce only one `SpanProcessor.on_end` callback; exporter or callback counts alone cannot prove exactly-once invocation.

## Expected Behavior

Both span-opening events keep their documented behavior of opening a root. Before a start/resume replaces an active root, its open state/action descendants and the root are ended. Every root created for the normal resumed execution is therefore ended at replacement/completion, allowing its sampled spans to reach the configured processor for export; no span is abandoned merely by overwriting its reference. State/action children attach to the current root, and the final root retains completion attributes/status. A root replaced before completion keeps its existing unset status and receives no completion attributes. Close order is action → state → root; each live span is ended once before the replacement starts, without reparenting any already-created child. Descendant references are cleared, so subsequent span events cannot be added to stale children.

This issue owns closing spans before root replacement. It does not require removing or renaming producer events, changing their run IDs, or changing the schema. Both producer events are consumed by other sinks and should keep their established behavior.

Root assertions in tests use an explicitly empty OTel context. Existing ambient-parent inheritance remains unchanged: `start_span()` can inherit a caller's current span, so this fix does not introduce a new context-propagation policy.

## Motivation

Missing resumed-root spans make exported traces incomplete and can conceal a broken `loop_resume` name handler when a test checks only the final exported root. This is a P3 defect in an optional tracing sink.

## Proposed Solution

Prepend the existing resume handler's cleanup to `_handle_loop_start`: call `_close_state_and_action()`, then end `_loop_span` if it exists, before creating the new root using `event_loop_name(event) or "ll-loop"`. No new helper or signature is necessary. A shared lifecycle implementation is acceptable, but tests should constrain behavior, not delegation between handlers.

Consecutive resume/start events still open their documented roots; both are ended/exported, and children attach to the replacement root. Keep final-status assignment on `loop_complete` and preserve producer behavior. Do not change `close()` or add a dependency, trace-link scheme, or new telemetry attributes for this fix.

## Integration Map

### Files to Modify

- `scripts/little_loops/transport.py` — ownership/lifetime of the active root in the start/resume handlers.
- `scripts/tests/test_transport.py`, `TestOTelTransport` — direct replacement lifecycle/parentage with live descendants and explicit nested-start noninterference.
- `scripts/tests/test_bug3755_transport_loop_identity.py`, `_run_loop` / `TestOTelTransportLiveLoop` — extend the existing producer-to-sink harness with saved-state resume setup and observation before teardown; do not copy it into a second harness.
- `docs/reference/EVENT-SCHEMA.md`, **OTel Transport Field Mapping**, and `docs/reference/API.md`, **OTelTransport / Event → span mapping** — short lifecycle clarification: start also closes old spans; real resume exports two same-name loop spans, including a childless resume span; only the final loop span gets completion attributes/status. Correct stale naming text only on the touched rows (`loop` → legacy `loop_name` → `"ll-loop"`, already shipped with BUG-3755). Remove the touched rows' unconditional "new trace" wording and explain that each loop span inherits any ambient parent, becoming a parentless root when no parent is active; preserve the existing context policy.

### Dependent Files

- `scripts/little_loops/fsm/persistence.py`, `PersistentExecutor.resume`, and `scripts/little_loops/fsm/executor.py`, `FSMExecutor.run` — the actual resume/start producers; preserve their contracts.
- `scripts/little_loops/events.py`, `EventBus.emit` / `close_transports` — dispatch/teardown catches transport exceptions; the integration regression must assert that no transport exception was logged.
- `scripts/tests/test_fsm_persistence.py`, `TestPersistentExecutor.test_resume_emits_resume_event` / `test_resume_run_id_stable_across_pause_resume_boundary` — current resume event and run-ID stability coverage.
- `scripts/tests/conftest.py`, `_isolate_history_db` / `_guard_real_history_db` — existing per-test history isolation; reuse it rather than add redundant setup.
- `.ll/learning-tests/opentelemetry-sdk.md` — proven start/end/export lifecycle; no new external API is needed.

### Similar Patterns

- `OTelTransport._handle_loop_resume` already performs the required replacement ordering.
- `OTelTransport._close_state_and_action` clears descendant references; `_handle_loop_complete` owns final status and completion attributes.

### Configuration

N/A — no configuration, producer schema, database migration, or dependency changes.

## Program Design

### Types

- `OTelTransport._loop_span: Any | None`
- `OTelTransport._state_span: Any | None`
- `OTelTransport._action_span: Any | None`

These existing fields represent live spans owned by the transport. End the old spans before assigning a replacement; clear descendant references through the existing helper.

### Signatures

- `OTelTransport._handle_loop_start(self, event: dict[str, Any]) -> None`
- `OTelTransport._handle_loop_resume(self, event: dict[str, Any]) -> None`
- `OTelTransport._close_state_and_action(self) -> None`

Existing signatures stay intact. Start follows resume's existing close-before-replace lifecycle so each documented span-opening event still creates a root.

### Call Path

`PersistentExecutor.resume` → `EventBus.emit(loop_resume)` → `OTelTransport.send` → `_handle_loop_resume` → `PersistentExecutor.run(clear_previous=False)` → `FSMExecutor.run` → `EventBus.emit(loop_start)` → `OTelTransport.send` → `_handle_loop_start` → state/action/completion events.

## Implementation Steps

1. Extend the existing live-executor harness to resume a saved interrupted `LoopState`, and add the failing span-conservation regression before shutdown. Make new harness options keyword-only with defaults; preserve all existing fresh-start callers and ensure teardown runs in `finally`, even if the pre-shutdown assertions fail. Incorporate BUG-3758's helper edits if they have landed first.
2. Apply close-before-replace to start while preserving resume's existing lifecycle, naming, producer contracts, final status assignment, and provider shutdown.
3. Add direct replacement coverage with live descendants; use a test-local recording `SpanProcessor` on the injected provider to verify old action end → old state end → old root end → replacement root start. Retain the separate duplicate-end warning/spy guard: processor callbacks alone cannot detect repeated `end()` calls. Verify parentage/event routing after replacement and nested-start noninterference.
4. Update the two OTel reference mappings, then run the transport/persistence suites and full local suite.

## Impact

- **Priority**: P3 — a lost root span in the optional tracing sink; execution and SQLite history are unaffected.
- **Effort**: Small — align root replacement with existing resume behavior and add regression coverage.
- **Risk**: Low — span counts increase by exporting the previously abandoned root; consumers must not assume one root per resumed segment.
- **Breaking Change**: No event/schema change; exported traces now include the previously missing root.

## Root Cause

- **File**: `scripts/little_loops/transport.py`
- **Anchor**: `OTelTransport._handle_loop_start` / `_handle_loop_resume`
- **Cause**: start does not share resume's close-before-replace lifecycle, so the real producer's consecutive resume/start sequence overwrites an active root and loses ownership of its live span.

## Steps to Reproduce

1. Save an interrupted `LoopState` in a temporary persistence directory, with a fixed `started_at`, a nonterminal `current_state`, and an iteration below `max_steps`.
2. Construct a real `PersistentExecutor` with a deterministic shell action runner and attach OTel using a local `TracerProvider`, `SimpleSpanProcessor`, and `InMemorySpanExporter`. Use an empty OTel `Context` and temporary `LL_HISTORY_DB`; the pytest suite already supplies history isolation.
3. Register an event recorder while calling `resume()` and running to completion; observe `loop_resume` → `loop_start` before state/action events, using the same persisted run ID.
4. Before closing the transport, compare the exported span count with top-level span-opening events (`loop_resume`, `loop_start`, `state_enter`, `action_start`). Two loop spans should have distinct IDs and the same name, but only the final root is exported. An optional `SpanProcessor.on_start` probe exposes the abandoned root, which remains recording; repeated close does not recover it.

## Test Plan

Use the existing in-memory exporter with `SimpleSpanProcessor`, which exports synchronously in end order. Compare the number of finished spans **before close** with the number of recorded depth-0 span-opening events, and identify the two same-name roots by span ID and parentage; do not collapse spans into a name dictionary. In the direct replacement test, add a test-local recording `SpanProcessor` whose `on_start`/`on_end` callbacks only record span IDs and callback order; assert the sequence after `send()` returns, outside the callbacks. This establishes close-before-open without relying on wall-clock end/start timestamp inequalities, which can be affected by clock adjustments. The integration test's event/span conservation check supplies the separate live-producer regression; it does not need a timestamp assertion or an additional processor. The synchronous callbacks and ended-span flushing are documented in the [OpenTelemetry Python SDK reference](https://opentelemetry-python.readthedocs.io/en/stable/sdk/trace.html#opentelemetry.sdk.trace.SpanProcessor).

Pin the local provider to `ALWAYS_ON` sampling. Run parentless-root assertions in an empty `Context`, restoring it afterward; do not install a global tracer provider or require different trace IDs. Use `caplog` to reject transport exception warnings and the SDK's duplicate-end warning (`Calling end() on an ended span`). If end-call spies are used instead, keep them local to the lifecycle test; exporter counts alone cannot detect duplicate calls.

| Case | Required evidence |
|---|---|
| Actual saved-state resume | Exactly two exported same-name root IDs, with the childless resume root first and the completed start root last. Finished-span count equals recorded span-opening events before close; only start root has completion status/attributes and parents resumed state spans. |
| Existing root/state/action → replacement (`loop_start` and `loop_resume`, parameterized) | Immediately after replacement, finished spans are old action → old state → old root, and the new root is still open. Recording callbacks prove those three ends precede replacement start, in that order. No duplicate ending; old spans retain original parents. New state/action attach to the replacement; an intervening span event goes to the new root, not an old child. |
| Nested `loop_start` (`depth > 0`) | Extend the existing depth-filter test with live outer state/action spans and assert that the original root and descendants remain open and unchanged. Drive through `send()`, not private handlers. |
| Fresh-start execution | Existing producer-to-sink and outcome/hierarchy tests stay green; one completed loop root with valid state/action parentage. |

The real `loop_resume` → `loop_start` sequence has no descendants between its two roots; it cannot establish the live-descendant replacement requirement by itself. Keep the focused direct-send test for that case. Existing outcome mapping and nested-event filtering tests supply compatibility coverage; do not create a second matrix for all final-status buckets.

For new SDK-backed regressions, skip if either `opentelemetry-sdk` or the OTLP gRPC exporter import is unavailable: the constructor imports both even with `_tracer_provider` injected. Inject only the local in-memory provider, invoke no network exporter, and close the provider in `finally`/fixture teardown even if an assertion fails. Retrofitting all existing optional-dependency guards is outside this bug.

## Acceptance Criteria

- [ ] A real resume → event-bus → OTel regression observes `loop_resume` → `loop_start` and exports exactly two distinct same-name root IDs. Finished-span count equals recorded depth-0 span-opening events after completion **before** shutdown; no transport dispatch/teardown exception is logged.
- [ ] The replaced resume root is exported first, is childless, stays `StatusCode.UNSET`, and has neither `ll.terminated_by` nor `ll.final_status`. Resumed state/action spans attach to the start root, which receives the actual completion attributes/status. Close-before-open is proven by the direct callback-order regression below rather than a wall-clock timestamp comparison.
- [ ] Separate live-descendant replacement coverage for both `loop_start` and `loop_resume` proves action → state → old root end → new root start ordering through a test-local recording processor, no duplicate `end()` calls through the separate warning/spy guard, original child parentage, and valid new child parentage/event routing after replacement. The new root remains open until completion.
- [ ] A `depth > 0` `loop_start` sent through `send()` leaves the live parent root and descendants open. Fresh-start execution and existing OTel naming, outcome mapping, and nested-event filtering tests pass; ambient-parent behavior in production is unchanged.
- [ ] Producer event shapes, ordering, and stable resumed run IDs retain their current contracts. This fix adds no database migration and is independently implementable from BUG-3755 and BUG-3758.
- [ ] Both OTel reference mappings briefly describe close-before-replace on start/resume and the consecutive two-span resume lifecycle; touched naming rows accurately reflect the already-installed naming fallback. The touched rows do not promise a new trace: they describe ambient-parent inheritance and parentless roots when no parent is active, without changing production propagation or requiring a new propagation test.
- [ ] New regression tests reuse temporary history/persistence isolation, an in-memory provider with explicit sampling/context and exception-safe teardown, and skip if either the SDK or OTLP gRPC exporter is absent; no network exporter is invoked. Provider shutdown, general interrupted-close cleanup, and overlapping action-start replacement remain outside this issue. The transport/persistence suites and `python -m pytest scripts/tests/` pass.

## Review Notes

Reviewed on 2026-10-06 after BUG-3755 merged. The identity helper is now installed, but start still overwrites an active root without ending it, so this remains independent open work. An in-memory start/resume sequence probe created two roots and exported one; the replaced resume root was still recording after completion. Reuse the merged producer-to-sink harness; add close-order/span-ID accounting rather than another harness. Opus supported explicit unset status, closure before replacement and completion attributes only on the current root (confidence 0.72). General close-on-interruption/action-replacement changes are outside this fix. No implementation edits were made.

Implementation-readiness review on `main` at `fec7d6462` (2026-10-06) reproduced the leak through an actual saved-state resume and verified the live-descendant asymmetry between start and resume. Split the integration/unit evidence, replaced line references with stable anchors, specified narrow OTel documentation updates, and accounted for sampling/context, both optional imports, existing history isolation, and SDK suppression of duplicate end callbacks. Targeted baseline: `python -m pytest -n 0 scripts/tests/test_transport.py scripts/tests/test_bug3755_transport_loop_identity.py scripts/tests/test_fsm_persistence.py -q` — **311 passed**. `ll-learning-tests assess --issue BUG-3759 --json` reports proven. No implementation changes were made in this review.

`/ll:advise --signal user_requested --host claude-code --model opus` (task budget scoped to BUG-3759) returned **ready after trimming**, confidence **0.85**. Adopted its event-driven conservation check, direct-send test split, explicit nested-start protection, and removal of unrelated repeated-close/dependency-guard refactoring requirements. Its dissent allowed a processor-based conservation probe but found no correctness reason to reopen the chosen two-root behavior. Kept an empty test context because `start_span()` inherits an ambient parent, so unconditional `parent is None` assertions otherwise depend on the test environment; no trace-ID or production propagation change is required. Risks remain increased visible childless-root counts and EventBus swallowing transport exceptions, addressed by documentation and log assertions.

Additional review on 2026-10-06 at `46f696c4b` reproduced the defect through saved-state resume: **4 spans opened, 3 finished before close**, with the abandoned resume root still recording. A separate in-memory probe confirmed that an active ambient parent produces the same trace ID, so the touched API rows must not promise a new trace. An Opus consult through `/ll:advise` (`user_requested`, confidence **0.80**) supported callback-order evidence for direct replacement, accurate context wording, and additive shared-harness changes. Its dissent considered timestamp assertions defensible as secondary evidence; omit them from the required regression because ordered callbacks prove the intended behavior directly. Keep the separate duplicate-end guard because SDK callbacks suppress repeated endings. The shared live/writer/OTel/persistence/query baseline passed **272 tests**, the learning target remains proven, and format/evidence checks were clean. These are review results; no implementation changes were made.

## Related

- BUG-3755 — completed identity repair; extend its live producer-to-sink harness to observe both same-name roots directly.
- BUG-3758 — independent route FTS destination indexing and defensive source-precedence fix. Both issues touch `_run_loop` in `scripts/tests/test_bug3755_transport_loop_identity.py` and separate sections of `docs/reference/API.md`. Whichever is implemented second should incorporate the first issue's edits; neither requires a dependency edge. Preserve existing fresh-start callers with defaulted keyword-only harness options and exception-safe teardown. Coordinate ownership of those shared files if implementation runs concurrently.

## Related Key Documentation

| Category | Document | Relevance |
|---|---|---|
| architecture | `docs/reference/API.md` | OTel transport lifecycle and event → span mapping. |
| reference | `docs/reference/EVENT-SCHEMA.md` | Span replacement lifecycle and OTel field mapping. |

## Status

**Open** | Created: 2026-10-06 | Reviewed: 2026-10-06 | Priority: P3


## Session Log
- `/ll:ready-issue` - 2026-10-06T18:23:36 - `rollout-2026-10-06T12-12-23-01a1126a-ab9e-7362-9b58-e87fb7718a10.jsonl`
- `/ll:advise` - 2026-10-06T18:23:36 - `rollout-2026-10-06T12-12-23-01a1126a-ab9e-7362-9b58-e87fb7718a10.jsonl`
- `/ll:capture-issue` - 2026-10-06T09:07:39 - `69fbb543-02d8-48e4-bbb6-a2a33935a7ec.jsonl`
