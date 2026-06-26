---
id: BUG-2304
type: BUG
priority: P2
title: loop_complete event omits the error field, hiding sub-loop crash reasons from
  audit tooling
status: open
captured_at: '2026-06-26T02:05:38Z'
discovered_date: 2026-06-26
discovered_by: capture-issue
relates_to:
- BUG-623
confidence_score: 100
outcome_confidence: 86
score_complexity: 18
score_test_coverage: 22
score_ambiguity: 23
score_change_surface: 23
---

# BUG-2304: `loop_complete` event omits the `error` field

## Summary

When an FSM loop terminates with `terminated_by: "error"`, the `loop_complete`
event written to the JSONL event stream contains no `error` field explaining
*why* it crashed. The error string is known at crash time and is correctly
threaded into the programmatic `ExecutionResult` return value, but it is never
written into the event archive that `ll-loop history` and all audit/debug
tooling read from.

Surfaced by an audit of `qa-pipeline` run `2026-06-26T014210` (cards repo): a
`cua-fix-verify` sub-loop terminated at `cua_observe` with `terminated_by:
"error"` but no reason. Diagnosing it required inspecting the resolved FSM,
filesystem-searching for the referenced loop file, cross-referencing `ll-loop
list`, and inferring by elimination that the loop file was missing.

## Steps to Reproduce

1. Author a loop YAML with a `run_loop` state referencing a non-existent sub-loop file (or any other condition that triggers `terminated_by: "error"` in `ExecutionEngine._finish()`).
2. Run the loop: `ll-loop run <loop-name>`.
3. Open the run's JSONL event archive (`.loops/runs/<loop-name>-<timestamp>/events.jsonl`).
4. Find the `loop_complete` event entry.
5. Observe: the event dict has `final_state`, `iterations`, and `terminated_by: "error"` but **no `error` field** — the crash reason is absent from the event stream.

## Current Behavior

`_finish()` in `scripts/little_loops/fsm/executor.py` emits the `loop_complete`
event with only `final_state`, `iterations`, and `terminated_by`. The `error`
parameter it accepts is passed through to `ExecutionResult` (whose `to_dict()`
correctly includes `error`), so `ll-loop run --json` carries the reason — but
the JSONL event stream never sees it.

```python
def _finish(self, terminated_by: str, error: str | None = None) -> ExecutionResult:
    self._emit(
        "loop_complete",
        {
            "final_state": self.current_state,
            "iterations": self.iteration,
            "terminated_by": terminated_by,
            # ← `error` is NOT included here
        },
    )
```

Separately, at the sub-loop routing boundary (`executor.py`, ~lines 728-741),
`child_result.error` is **not inspected** when routing on `terminated_by ==
"error"`. Even if the event carried the error, the parent loop's `on_error` /
`on_no` states never receive the child's reason.

```python
elif child_result.terminated_by == "error":
    if state.on_error:
        return interpolate(state.on_error, ctx)
    return interpolate(state.on_no, ctx) if state.on_no else None
```

## Expected Behavior

The `loop_complete` event should include the `error` string (guarded on
`error is not None`) so audit/debug tooling can read the crash reason directly
from the JSONL stream without filesystem forensics. Optionally, the child's
`error` string should be surfaced into the parent context (e.g.
`${captured.<state>.error}`) so `on_error` / `on_no` states can log or capture
it.

## Root Cause

**File**: `scripts/little_loops/fsm/executor.py`
**Anchor**: `ExecutionEngine._finish()` (the `loop_complete` `_emit` call)

The `error` parameter is correctly threaded to the `ExecutionResult` dataclass
but the event dict construction drops it on the floor. This is a one-line data
flow gap between the return value and the event archive. A secondary gap exists
at the sub-loop routing boundary where `child_result.error` is never read.

This is the untouched follow-on to **BUG-623** (done), which fixed the
`final_status` mapping in the *state file* for `timeout` vs `error` and
explicitly noted "the reason is buried in the event detail" — but did not add
the missing `error` field to the event.

## Proposed Solution

1. Add `"error": error` to the `loop_complete` event dict in `_finish()`,
   guarded on `error is not None`.
2. (Optional, secondary) At the sub-loop routing boundary, surface
   `child_result.error` into the parent context under the state name so
   `on_error` / `on_no` handlers can reference it.

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/executor.py` — `_finish()` event dict; optionally the sub-loop `terminated_by == "error"` routing branch
- `scripts/little_loops/cli/loop/info.py` — `_format_event()` at the `"loop_complete"` branch: currently renders `"final_state  N iter  [terminated_by]"` but never reads `error`; the audit tooling fix is incomplete unless this display also surfaces the error string when present
- `scripts/little_loops/generate_schemas.py` — **CRITICAL**: Python source that generates `docs/reference/schemas/loop_complete.json` via `ll-generate-schemas`; the `loop_complete` schema at line ~376-396 defines only `{final_state, iterations, terminated_by}` with no `error` property. If only the JSON file is updated, the next `ll-generate-schemas` run overwrites the fix. Must add `"error": _str("Error message explaining why loop crashed. Present only when terminated_by='error'.")` to the properties dict here. [Wire: Agent 1 + Agent 2]

### Dependent Files (Callers/Importers)
- `ll-loop history` rendering and any audit/debug tooling that reads `loop_complete` events — they gain the field; verify no consumer assumes its absence

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/transport.py` — `_handle_loop_complete()` (line ~462) reads `outcome` for OTel span status; passively gains the `error` field. Advisory: optionally set span error description from `event.get("error")` when `terminated_by == "error"`. [Agent 2 finding]
- `scripts/little_loops/session_store.py` — ingests `loop_complete` at line ~909; passively gains the field (no code change required; raw JSONL carries it). [Agent 1 finding]
- `scripts/little_loops/hooks/pre_compact_handoff.py` — consumes `loop_complete` for context compaction; passively gains the field (no code change required). [Agent 1 finding]
- `scripts/little_loops/analytics/variance.py` — reads `loop_complete` events to track `terminated_by` outcomes for evaluator variance; passively gains the field (no code change required). [Agent 1 finding]
- `scripts/little_loops/cli/logs.py` — processes `loop_complete` from session logs; advisory: check if any `loop_complete` formatting path in this module also needs to surface `error`. [Agent 2 finding]

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `scripts/little_loops/history_reader.py` — reads JSONL event archives for `ll-loop history`; gains the `error` field passively (additive, no breakage)
- `scripts/little_loops/cli/history.py` — `ll-loop history` command implementation; should be checked to confirm it surfaces `error` when rendering error-terminated runs
- `scripts/tests/test_history_reader.py` — test coverage for the history reader; add a case asserting `error` is preserved when read from JSONL
- `skills/audit-loop-run/SKILL.md` and `skills/debug-loop-run/SKILL.md` — audit/debug skills that read `loop_complete` events; they gain the field and no code changes needed, but their prompts may reference the field once available
- `scripts/tests/test_debug_loop_run_synthesis.py:601-602` — synthesizes from `loop_complete` with `terminated_by: "error"` but does not read `error` field; no breakage, but a new case asserting the field is used would improve coverage

### Tests
- Add an executor test asserting a forced-error termination emits `loop_complete` with the `error` field populated
- If parent-context surfacing is implemented, add a sub-loop test asserting `${captured.<state>.error}` is available to `on_error`

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_fsm_executor.py` — **Gap 1**: `test_exception_during_execution_returns_error_result` (line ~2193) uses a `FailingRunner` and asserts on `LoopResult.error` but does NOT collect events via `event_callback`. Extend with a companion test (or add `event_callback=events.append` to the existing one) to also assert `complete_event["error"] == "Connection failed"` and `complete_event["terminated_by"] == "error"`. [Agent 3 finding]
- `scripts/tests/test_fsm_executor.py` — **Gap 2** (if optional sub-loop surfacing is implemented): `test_sub_loop_error_routes_to_on_error_when_set` (line ~4778) and `test_sub_loop_missing_loop_with_on_error` (line ~4878) do NOT assert on `executor.captured` contents. Add assertion that after a sub-loop error, the parent's `captured` dict contains the child's error string. [Agent 3 finding]
- `scripts/tests/test_ll_loop_commands.py` — **Gap 3 — zero coverage**: The `_format_history_event("loop_complete")` branch in `info.py` (line ~356–361) has no test that exercises it with `json=False`. The `mixed_events_file` fixture at line ~3822 includes a `loop_complete` event but all consuming tests use `json=True` (bypassing the formatter). Add a test that passes a `loop_complete` event through `cmd_history(json=False)` and asserts human-readable output contains `final_state`, `iterations`, `terminated_by`. Also add a variant with `terminated_by="error"` + `error="..."` once the display is updated. [Agent 3 finding]
- `scripts/tests/test_session_store.py` — `test_loop_complete_records_outcome_as_state` (line ~238) ingests a `loop_complete` event but does not assert that an `error` field from the event is stored or queryable. Update to verify the `error` field is preserved in the raw JSONL path. [Agent 3 finding]
- `scripts/tests/test_ll_loop_execution.py` — Full E2E integration test reads `events.jsonl` after a real run (line ~565); does not exercise the error-terminated path. Verify this test passes with the new field (additive, no break expected); optionally add an error-path variant. [Agent 3 finding]

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `scripts/tests/test_fsm_executor.py:test_loop_complete_event_details` — direct template for the new test: builds `events: list[dict] = []`, passes `event_callback=events.append`, runs the executor, then asserts fields on `next(e for e in events if e["event"] == "loop_complete")`
- `scripts/tests/test_fsm_executor.py:test_exception_during_execution_returns_error_result` — shows how to force a crash via a `FailingRunner` that raises `RuntimeError`; combine with the event-capture pattern above to assert `loop_complete["error"]` is populated
- `scripts/tests/test_debug_loop_run_synthesis.py:601-602` — consumes `loop_complete` with `terminated_by: "error"` today but does NOT reference an `error` field; add a case that does once the field exists

### Documentation
- `docs/reference/schemas/loop_complete.json` — add optional `error` property (currently absent from `required` list and `properties`; `additionalProperties: true` means no runtime breakage, but schema needs updating for correctness)
- `docs/reference/EVENT-SCHEMA.md` — verify `loop_complete` field table includes `error`

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_REFERENCE.md` — contains a `loop_complete` event section describing the standard fields (`final_state`, `iterations`, `terminated_by`); add `error` field description: present only when `terminated_by="error"`. [Agent 2 finding]
- `docs/guides/LOOPS_GUIDE.md` — has user-facing debugging/error output section that references reading `terminated_by` from `events.jsonl`; should mention that `error` field appears alongside `terminated_by="error"` to give the crash reason. [Agent 2 finding]
- `skills/debug-loop-run/reference.md` — event payload table at line ~26 lists `loop_complete` fields as `terminated_by (str), final_state (str), iterations (int)`; add `error (str, optional)` to this table. The FATAL_ERROR signal rules at lines ~62–76 tell consumers to read error reason from `evaluate.error`; can optionally also reference `loop_complete.error` as a direct source once the field exists. [Agent 2 finding]
- `docs/reference/COMMANDS.md` — audit signal documentation at lines ~762–764 describes the FATAL_ERROR signal as fetching the crash reason from the `evaluate` event's `error` field; after this fix, the reason is available directly on `loop_complete.error`. Update to reference both sources or prefer `loop_complete.error` as the primary. [Agent 2 finding]

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `docs/reference/schemas/loop_complete.json` — add to `properties`: `"error": {"type": "string", "description": "Error message explaining why the loop crashed. Present only when terminated_by=\"error\"."}`. Do NOT add to `required` (conditional field).
- `docs/reference/EVENT-SCHEMA.md:583-587` — add `| error | str | only when terminated_by="error" | Error message explaining why the loop crashed |` row to the field table; also update the example JSON at line 591-598 to show the `error` key for an error-terminated case.

### Configuration
- N/A

## Implementation Steps

1. Add guarded `error` field to the `loop_complete` event in `_finish()`
2. (Optional) Thread `child_result.error` into the parent context at the sub-loop routing boundary
3. Add/extend executor tests covering error-termination event emission

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Step 1 — `executor.py:_finish()`**: Use the established conditional-field pattern (same as `action_complete` payload builder at `executor.py:1284-1305`): build the base dict first, then extend conditionally:
```python
payload = {
    "final_state": self.current_state,
    "iterations": self.iteration,
    "terminated_by": terminated_by,
}
if error is not None:
    payload["error"] = error
self._emit("loop_complete", payload)
```

**Step 2 (optional) — `executor.py:_execute_loop_state()` at the `elif child_result.terminated_by == "error":` branch (line ~734)**: surface `child_result.error` into `self.captured` so `on_error`/`on_no` states can reference `${captured.<state_name>.error}`:
```python
elif child_result.terminated_by == "error":
    if child_result.error:
        self.captured.setdefault(self.current_state, {})["error"] = child_result.error
    if state.on_error:
        ...
```
Note: the existing `context_passthrough`/`with_` merge at line 724-725 copies `child_executor.captured` (the child's own captures), not `child_result.error` (the crash string) — these are distinct and both need independent handling.

**Step 3 — Tests**: Extend `test_loop_complete_event_details` in `test_fsm_executor.py:1608` with a parallel test that uses `FailingRunner` (pattern from `test_exception_during_execution_returns_error_result` at line 2193) and asserts `complete_event["error"]` is set and `complete_event.get("error")` is `None` for non-error terminations.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

4. Update `scripts/little_loops/generate_schemas.py` — **Do this in Step 1**, not as a separate step. Add `"error": _str("Error message explaining why loop crashed. Present only when terminated_by='error'.")` to the `loop_complete` properties dict (~line 390). Then run `ll-generate-schemas` to regenerate `docs/reference/schemas/loop_complete.json` (do not edit the JSON by hand).
5. Add test for `_format_history_event("loop_complete")` with `json=False` in `test_ll_loop_commands.py` — this branch has zero coverage today. Cover both the normal-termination case (no `error` key in output) and the error-termination case (after Step 1 changes `info.py`).
6. Extend `test_exception_during_execution_returns_error_result` in `test_fsm_executor.py` — add `event_callback=events.append` and assert `complete_event["error"]` matches the exception message (in addition to the existing `result.error` assertion).
7. Update `docs/guides/LOOPS_REFERENCE.md` and `docs/guides/LOOPS_GUIDE.md` — add `error` field description to the `loop_complete` event table/section in each.

## Impact

- **Priority**: P2 - Diagnostic data loss; every error-terminated loop is harder to debug, and the fix is small and low-risk.
- **Effort**: Small - One-line core change plus a test; optional secondary surfacing is a small addition.
- **Risk**: Low - Additive field on an event dict; no existing consumer relies on its absence.
- **Breaking Change**: No

## Labels

`bug`, `captured`, `fsm`, `observability`

## Session Log
- `/ll:confidence-check` - 2026-06-25T00:00:00Z - `c7b6754c-da25-4a60-8d9c-c8a7add2118c.jsonl`
- `/ll:wire-issue` - 2026-06-26T02:26:04 - `0a840081-0788-4460-9fde-d46c92621d4d.jsonl`
- `/ll:refine-issue` - 2026-06-26T02:15:51 - `a7de4d39-918e-442e-8ba7-d49e06022c2b.jsonl`
- `/ll:format-issue` - 2026-06-26T02:10:21 - `6a879ef6-fde0-4367-b70f-158714386389.jsonl`
- `/ll:capture-issue` - 2026-06-26T02:05:38Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/47212e05-8450-445f-aa2c-7353511e59fa.jsonl`

---

## Status

open
