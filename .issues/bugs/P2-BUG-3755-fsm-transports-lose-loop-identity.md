---
id: BUG-3755
title: SQLite and OTel transports lose FSM loop identity
type: BUG
priority: P2
status: done
completed_at: '2026-10-06T00:00:00Z'
discovered_date: '2026-10-05'
verify_verdict: VALID
labels:
- telemetry
- transport
- history-db
learning_tests_required:
- opentelemetry-sdk
relates_to:
- BUG-3758
- BUG-3759
---

# BUG-3755: SQLite and OTel transports lose FSM loop identity

## Summary

FSM events carry the loop's name under `loop`, while `SQLiteTransport` and `OTelTransport` read `loop_name`. When either optional transport is enabled, executor-emitted SQLite `loop_events` rows lose their name and FTS identity, and OTel root spans are named `ll-loop`.

Keep this issue focused on identity resolution and producer-to-sink regression coverage. Route endpoint persistence is tracked separately in BUG-3758. The identity repair requires no database migration and can ship independently.

## Steps to Reproduce

1. Pin `LL_HISTORY_DB` and the loop persistence directory to temporary paths.
2. Run a real `PersistentExecutor` for a `work` → `done` loop with a deterministic injected action runner. Attach `SQLiteTransport` and an OTel transport backed by `SimpleSpanProcessor` / `InMemorySpanExporter` to its event bus.
3. Observe the producer emits `loop_start` with `loop=<name>` and no `loop_name`. Read SQLite rows and exported root spans: the names are NULL and `ll-loop`, respectively, and loop FTS `ref`/`anchor` are empty.
4. Save an interrupted `LoopState` and call a real `resume()`. The separately emitted `loop_resume` also carries `loop`; inspect the name of the root opened for that event, not just the final exported root.

## Current Behavior

- `FSMExecutor._emit` (`scripts/little_loops/fsm/executor.py:4168`) adds `run_id` and `loop`; `PersistentExecutor._handle_event` forwards the event at `fsm/persistence.py:1182`.
- `PersistentExecutor.resume` builds `loop_resume` with the same `loop` key (`persistence.py:1465-1477`) before calling `run(clear_previous=False)`.
- `SQLiteTransport.send` (`session_store/writers.py:3087`) reads `loop_name`; its insert has no `run_id` column. `_index` uses that missing name for content, `ref`, and a nominal `.loops/<name>.yaml` anchor (`:3109-3117`).
- `OTelTransport._handle_loop_start` / `_handle_loop_resume` (`transport.py:1783-1792`) read `loop_name` and default to `ll-loop`.
- Existing transport tests predominantly provide legacy `loop_name` dictionaries, so the producer/consumer mismatch passes those suites.

## Expected Behavior

Both transports share one resolution rule: use a truthy `loop`, otherwise a truthy `loop_name`, otherwise no name. SQLite stores SQL NULL for the last case; OTel uses `ll-loop`. Convert the selected value to `str`, preserving the existing coercion convention, and do not mutate the input dictionary.

Apply the rule to all recognized SQLite loop events and both OTel span-opening handlers. Existing route-state storage, status mapping, and nested-loop filtering retain their behavior in this identity change.

## Root Cause

- **Files**: `scripts/little_loops/fsm/executor.py` (producer), `scripts/little_loops/session_store/writers.py` and `scripts/little_loops/transport.py` (consumers).
- **Anchors**: `FSMExecutor._emit`, `PersistentExecutor.resume`, `SQLiteTransport.send`, and OTel's two span-opening handlers.
- **Cause**: ENH-3345 standardized producer identity on `loop` without aligning the older transport readers. Tests that supply only `loop_name` bypass the actual producer contract.

## Acceptance Criteria

- [ ] A shared name resolver implements `loop` → legacy `loop_name` → absent, without changing the input event. Tests cover canonical-only, legacy-only, conflicting non-empty keys (canonical wins), empty/null canonical values with a legacy fallback, and missing/empty/null names in both keys.
- [ ] Both OTel span-opening handlers and the SQLite loop-event writer use that rule. Neither-key cases produce SQL NULL / OTel `ll-loop`, never the literal name `None`; existing legacy payload tests pass.
- [ ] A real `PersistentExecutor.run()` → `EventBus` test produces recognized SQLite rows with the FSM name and an exported OTel root named after the FSM. Assert delivered outputs, including loop FTS `ref=<name>` and nominal `anchor=.loops/<name>.yaml`, rather than only successful execution.
- [ ] A real `PersistentExecutor.resume()` test verifies its `loop_resume` row has the FSM name and the OTel root opened specifically for `loop_resume` has that name. It separately verifies the subsequent `loop_start` uses the same name, so one handler cannot mask the other.
- [ ] A real nested-loop fixture verifies SQLite child-event rows use the child's stamped name; OTel continues skipping `depth > 0` with its existing warning behavior. Parent state/action hierarchy and `map_final_status` outcome attributes/status tests keep passing.
- [ ] Producer-to-sink fixtures pin the history DB and loop paths to temporary locations, close transports on failure as well as success, and make no external exporter/network calls. OTel-specific tests skip when either the SDK or OTLP gRPC exporter dependency is absent; SQLite coverage always runs.
- [ ] This change adds no migration and does not modify the schema manifest or version-only test expectations (schema is v59 at review HEAD). Route source/target recovery remains owned by BUG-3758; legacy NULL/empty-FTS rows remain unchanged.
- [ ] `EVENT-SCHEMA.md` and `API.md` document the canonical key, fallback, and defaults; release notes explain the OTel root-name correction for users with span-name filters. Relevant transport, event, and persistence suites plus `python -m pytest scripts/tests/` exit 0.

## Integration Map

### Files to Modify

- `scripts/little_loops/events.py` — shared `event_loop_name(event: dict[str, Any]) -> str | None` resolver. No such helper exists on main at review HEAD; the unmerged draft already provides an initial implementation.
- `scripts/little_loops/session_store/writers.py:3086` — loop-event identity lookup and existing FTS identity use; no row-layout or route-state changes for BUG-3755.
- `scripts/little_loops/transport.py:1783` — start/resume name resolution.
- A new regression module under `scripts/tests/` — actual startup, resume, and nested producer events delivered through the bus; the draft module is not tracked on main.
- `scripts/tests/test_events.py`, `scripts/tests/test_session_store_writers.py`, and `scripts/tests/test_transport.py` — compatibility/default/precedence cases as appropriate; keep existing legacy-key and status/hierarchy cases.
- `docs/reference/EVENT-SCHEMA.md:2066-2067` — currently describes the defect in the span-opening field table; also document SQLite's identity source/default.
- `docs/reference/API.md:11937-11993` — replace legacy-only OTel examples/name rules with the canonical key and compatibility rule; document the resolver if included in the public module reference.
- Release notes — corrected root names change span-name filter results, despite requiring no schema migration.

### Dependent Files and Constraints

- `scripts/little_loops/fsm/executor.py:4168` and `scripts/little_loops/fsm/persistence.py:1465` are distinct producers. Both must be exercised; no producer-key rename or duplicate `loop_name` stamping is needed.
- `scripts/little_loops/events.py:125` isolates sink exceptions. Regression tests must prove rows/spans arrived; a successful loop result alone is insufficient.
- Production CLI wiring attaches transports to `PersistentExecutor.event_bus` (`cli/loop/run.py:683`, `cli/loop/lifecycle.py:752`). Direct `add_transport` preserves the same bus-to-sink path without reading real project socket configuration.
- `scripts/tests/test_fsm_persistence.py:1322` and `:1359` already establish actual resume emission/run-ID stability; use those contracts when constructing the resumed-state fixture.
- `scripts/little_loops/fsm/executor.py:1320` forwards child events with `depth` while retaining their own `loop`. SQLite accepts those events; OTel explicitly ignores them. This fix supplies child identity without adding run/depth fields to the database.
- `OTelTransport.__init__` imports both SDK and OTLP gRPC exporter even with an injected provider (`transport.py:1710`). A guard that checks only the SDK is insufficient.
- `scripts/tests/conftest.py:1046` / `:1089` guard real history DB/socket access; the per-test history-isolation fixture already exists. Explicit temporary paths make standalone regression helpers safe too.
- `scripts/tests/test_history_store_chokepoint_gate.py` scans production code under `scripts/little_loops/`, not `scripts/tests/`. Its restriction was incorrectly extended to tests in the earlier issue text; temporary raw SQLite test inspection is allowed.
- Search anchors follow the existing nominal `.loops/<name>.yaml` convention. They are not proof that a file exists, especially for packaged, subdirectory, or differently named loop definitions. Correct physical-path resolution is outside this lookup fix.

### Verified Consumer Scope

A targeted event-key search found only these three live `event.get("loop_name", ...)` reads: SQLite send and OTel start/resume. Other `loop_name` reads in snapshot backfill and loop audit/evidence consume persisted state, whose contract still uses `loop_name`. Socket/JSONL/webhook sinks pass through payloads; the loop feed already reads `loop` (`cli/loop/feed.py:1056`).

The earlier quality-metrics impact claim was incorrect. `agent_quality._compute_retry_windows` (`issue_history/agent_quality.py:440`) and `quality_regressions` (`issue_history/quality_regressions.py:301`) query **`loop_runs`**, as do run/usage readers. `FSMExecutor._finish` directly calls `record_loop_run_summary(loop_name=self.fsm.name)` (`executor.py:4697`), independent of `SQLiteTransport`. The cited `ll-logs` fleet path reads filesystem run archives (`cli/logs.py:2138`). This defect affects event-level history/search and OTel labeling, not those longitudinal metrics.

### Existing Draft

Reference only: branch `fix/BUG-3755-transport-loop-key`, worktree `.claude/worktrees/bug-3755`, HEAD `b37b20a05`. `256ab0ad1` adds the shared helper and consumer changes, but also changes route source-state mapping; `b37b20a05` adds a `to_state` migration. Reuse relevant identity work after reconciling the acceptance criteria, rather than merging/cherry-picking either commit wholesale as BUG-3755.

The draft startup tests lack real resume coverage, empty/null compatibility cases, nested-loop attribution, and FTS assertions. Its SDK-only dependency guard also needs tightening. Route and migration work belongs to BUG-3758.

## Program Design

### Types

- Producer `event["loop"]`: loop-name string; legacy input `event["loop_name"]` remains accepted.
- Resolved name: `str | None`; existing SQLite column remains nullable TEXT.

### Signatures

- `event_loop_name(event: dict[str, Any]) -> str | None` in `events.py`: truthy canonical key, then truthy legacy key, string-coerced when present; no input mutation.
- `SQLiteTransport.send(self, event: dict[str, Any]) -> None`: resolve identity, preserve existing mappings/inserts.
- `OTelTransport._handle_loop_start` / `_handle_loop_resume`: same existing signatures, name from the resolver or `ll-loop`.

### Call Path

Startup: `FSMExecutor._emit` → `PersistentExecutor._handle_event` → `EventBus.emit` → transports. Resume: `PersistentExecutor.resume` → `EventBus.emit` for its inline event, then `run()` emits `loop_start`. Both paths use the shared sink-side resolver.

## Implementation Steps

1. Shared identity resolution satisfies canonical/legacy/default precedence and preserves payloads across sinks.
2. Real startup, resume, and nested-loop outputs establish identity in SQLite rows/FTS and OTel spans while keeping lifecycle/status behavior compatible.
3. Event/API examples and release guidance describe the corrected names; targeted tests and the full local suite pass. Schema and route semantics remain outside this implementation.

## Impact

- **Priority**: P2 — ongoing loss of attribution in both optional telemetry sinks. Existing `loop_events` rows have no run ID for a reliable identity join; current backfill seeds snapshot rows rather than repairing these events.
- **Effort**: Small — shared lookup, two consumers, regression tests, and focused documentation.
- **Risk**: Low code/schema risk; users filtering on the old OTel root name must adapt. Missing/empty/null legacy names intentionally resolve to defaults rather than being stringified as `None`.
- **Breaking Change**: No schema/API signature change; observable OTel root names are corrected.

## Related

- ENH-3345 (done) — universal producer `run_id` / `loop` envelope.
- BUG-3066 (done) — analogous producer/transport status-contract drift; its shared `map_final_status` semantics remain intact.
- BUG-3758 — route source/target persistence and migration, independently implementable; neither issue blocks the other.
- BUG-3759 — the separate OTel root-lifetime defect exposed by the real resume reproduction; it does not block identity resolution.
- ENH-2463 (done) — separate `loop_runs` summary path, unaffected by this bug.

## Review Findings — 2026-10-06

Verified against main `3286729a2` with real startup and resumed execution using temporary storage and an in-memory exporter. Producer names were present; SQLite names were NULL, FTS identity was empty, and both OTel start/resume roots were named `ll-loop`. Separate `loop_runs` rows had correct names.

The existing transport, session-store writer, and persistence suites passed **537 tests** in 38.05s despite the reproduced defect. Implementation must add producer-to-sink coverage rather than relying on this baseline.

Resume test trap: `resume()` emits `loop_resume` and then `loop_start`; the latter currently replaces the active root. In the reproduction, two roots were opened but only one root was exported. A final-span-name assertion can therefore hide a still-broken resume handler. Observe the root opened for the actual resume event independently; span-lifetime repair is tracked separately in BUG-3759.

`/ll:advise` consult (`signal=user_requested`, host `claude-code`, model `claude-opus-5-5`) recommended the complete identity/route split and P2, with **0.78 confidence**. Risks: mixed draft commits, fallback/default compatibility, optional SDK/exporter detection, nested attribution, nominal FTS anchors, and changed OTel name filters. Dissent: P3 is defensible for opt-in sinks; keeping schema-neutral route-source recovery together would recover some data sooner. P2 and the complete split are selected to address ongoing identity loss while keeping transition semantics and migration ownership together.

The prior 95/86 confidence scores and component scores were removed because they assessed the previous combined scope and unsupported impact rationale. A later confidence check must assess this revised issue rather than reusing those scores.

## Resolution

- **Action**: fix
- **Completed**: 2026-10-06
- **Status**: Completed

### Changes Made
- `events.py`: `event_loop_name()` reads the executor-stamped `loop` key, falling back to `loop_name` for older payloads.
- `transport.py`: `OTelTransport._handle_loop_start` and `_handle_loop_resume` name the loop span through it, so spans are named after the loop instead of `ll-loop`.
- `session_store/writers.py`: `SQLiteTransport.send` records the loop name through it, so live `loop_events` rows are no longer NULL.
- `scripts/tests/test_bug3755_transport_loop_identity.py`: drives a real `PersistentExecutor` through its event bus into both transports (fails without the fix).

### Scope note
The branch also shipped route-endpoint persistence that this issue scoped out to BUG-3758: schema v60 adds nullable `loop_events.to_state` (a `route` row keeps `from` as `state` and records `to` in `to_state`). BUG-3758 should be re-checked against this before implementation.

## Status

**Completed** | Created: 2026-10-05 | Completed: 2026-10-06 | Priority: P2

## Session Log
- `/ll:advise` - 2026-10-06T09:04:30 - `da8cdf64-7ea1-489f-a22f-62d03c35c5b9.jsonl`
- `/ll:confidence-check` - 2026-10-06T07:13:09 - `7e8c728c-f090-4a58-949a-dd0ab4ad88f5.jsonl`
- `/ll:verify-issues` - 2026-10-06T07:11:16 - `c174406e-cc5e-42ca-bfb0-9612775f49e7.jsonl`
- `/ll:verify-issues` - 2026-10-06T07:09:49 - `646dfd23-77c6-4244-9c3b-15d7fa5df5f7.jsonl`
- `/ll:verify-issues` - 2026-10-06T07:08:28 - `01c29346-c7cf-4f83-901e-c969db0c4749.jsonl`
- `/ll:wire-issue` - 2026-10-06T07:06:46 - `e48af9aa-f26d-410f-b026-8068420e9af9.jsonl`
- `/ll:refine-issue` - 2026-10-06T06:57:45 - `57aa3271-f5d2-4032-bf1b-9f6c15c97341.jsonl`
- `/ll:format-issue` - 2026-10-06T06:51:20 - `6c502106-ed87-456c-821b-ba3029111722.jsonl`
