---
id: ENH-1678
title: Add `retryable_exit_codes` filter to FSM state retry config
type: ENH
priority: P3
status: done
captured_at: "2026-05-24T13:15:53Z"
discovered_date: 2026-05-24
discovered_by: capture-issue
parent: EPIC-1744
labels:
- fsm-loops
- executor
- schema
- resilience
---

# ENH-1678: Add `retryable_exit_codes` filter to FSM state retry config

## Summary

Extend the existing `max_retries`/`on_retry_exhausted` mechanism (ENH-713) with an optional `retryable_exit_codes` list so loop states can limit automatic retries to known-transient exit codes (e.g., `1` for API socket disconnect, `137` for OOM/SIGKILL) without retrying substantive failures that indicate logic errors.

## Motivation

The `general-task` loop's `continue_work` state lost a run due to an API socket disconnect (exit 1) that routed directly to `diagnose → failed`. Adding `max_retries: 3` + `on_retry_exhausted: diagnose` with `on_error: continue_work` would retry on any failure — but exit code 1 is also returned by substantive tool failures that should not be retried. Loop authors need a way to say "retry only for known transient signals."

## Current Behavior

- `StateConfig` supports `max_retries: int | None` and `on_retry_exhausted: str | None` (added in ENH-713)
- Retry triggers on any consecutive same-state re-entry; there is no exit-code filter
- A state with `on_error: self` retries on any non-zero exit, including substantive failures

## Expected Behavior

`StateConfig` gains an optional `retryable_exit_codes: list[int] | None` field. When set:
- Only non-zero exits whose code is in the list trigger a retry (re-enter the state)
- Non-zero exits with codes **not** in the list route to `on_error` immediately (no retry consumed)
- `max_retries` / `on_retry_exhausted` still apply as the cap when retryable codes are encountered

```yaml
states:
  continue_work:
    action: "..."
    on_error: continue_work
    max_retries: 3
    on_retry_exhausted: diagnose
    retryable_exit_codes: [1, 137]
```

## Proposed Solution

**`schema.py`** — add `retryable_exit_codes: list[int] | None = None` to `StateConfig`.

**`executor.py`** — in the non-zero exit branch of `_execute_state`, before deciding to re-enter or route to `on_error`, check:
```python
if state.retryable_exit_codes and exit_code not in state.retryable_exit_codes:
    # Not a retryable code — bypass retry, route on_error directly
    return interpolate(state.on_error, ctx)
```

**`validation.py`** — validate that `retryable_exit_codes` is only set when `on_error` is also set (since the field is meaningless without a retry route), and that all entries are positive integers.

**`fsm-loop-schema.json`** — add `retryable_exit_codes` to the state object definition.

## Implementation Steps

1. Add `retryable_exit_codes: list[int] | None = None` to `StateConfig` in `scripts/little_loops/fsm/schema.py`; update `to_dict()` / `from_dict()`.
2. In `executor.py` non-zero exit branch, add the exit-code filter check before the retry counter increment.
3. Add validation in `validation.py`: require `on_error` when `retryable_exit_codes` is set; reject non-positive integers.
4. Update `fsm-loop-schema.json` to add the field.
5. Add unit tests in `scripts/tests/test_fsm_executor.py`: retryable code retries; non-retryable code bypasses retry and routes `on_error`; exhaustion still fires when retryable codes accumulate.
6. Update `skills/create-loop/reference.md` to document the new field alongside `max_retries`.

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/schema.py` — add field to `StateConfig`
- `scripts/little_loops/fsm/executor.py` — exit-code filter in retry branch
- `scripts/little_loops/fsm/validation.py` — field co-constraint
- `scripts/little_loops/fsm/fsm-loop-schema.json` — JSON schema update

### Reference Sites
- `executor.py` — existing `max_retries` / `on_retry_exhausted` logic (ENH-713)
- `schema.py` — `StateConfig` dataclass

### Dependent Files (Callers/Importers)
- `scripts/little_loops/fsm/runners.py` — executes states via executor; reads `StateConfig` from loop YAML; no changes needed
- TBD — run `grep -r "StateConfig" scripts/little_loops/` to confirm full importer list

### Similar Patterns
- `StateConfig.max_retries: int | None = None` and `on_retry_exhausted: str | None = None` (ENH-713) — direct precedent; follow the same optional-field + `to_dict()`/`from_dict()` pattern
- Executor non-zero exit branch — new filter inserts before the retry counter increment; follow existing conditional branching style

### Tests
- `scripts/tests/test_fsm_executor.py` — extend `TestPerStateRetryLimits`

### Documentation
- `skills/create-loop/reference.md` — document `retryable_exit_codes` in state config reference

### Configuration
- N/A — JSON schema update is already covered in Files to Modify above

## Impact

- **Priority**: P3
- **Effort**: Small — additive field, localized to schema + executor + validation
- **Risk**: Low — no change to states that don't opt in
- **Breaking Change**: No

## Scope Boundaries

- **In scope**: `retryable_exit_codes: list[int] | None` field on `StateConfig`; exit-code filter in executor non-zero exit branch; validation co-constraint (`on_error` required when `retryable_exit_codes` is set; all entries must be positive integers); `fsm-loop-schema.json` schema update; unit tests covering retryable/non-retryable routing and retry exhaustion
- **Out of scope**: Retry backoff or delay between retries; per-exit-code custom error routes beyond the existing `on_error` target; retry observability or logging; changes to states that do not opt in to `retryable_exit_codes`

## Labels

`fsm-loops`, `executor`, `schema`, `resilience`

---

**Open** | Created: 2026-05-24 | Priority: P3

## Verification Notes

_Added by `/ll:verify-issues` on 2026-05-31_

**Verdict: RESOLVED** — Feature is fully implemented in the codebase:
- `retryable_exit_codes: list[int] | None = None` in `schema.py:379` ✓
- `to_dict()`/`from_dict()` round-trip at `schema.py:434-525` ✓
- Executor uses it at `executor.py:836` for retry filtering ✓
- Confirmed in `fsm-loop-schema.json` and `validation.py` ✓
- Action: Set `status: done` in frontmatter

## Session Log
- `/ll:verify-issues` - 2026-05-31T05:53:48 - `e9b1fe44-19f3-4b83-9d6b-0194f265fb9a.jsonl`
- `/ll:verify-issues` - 2026-05-31T00:00:00 - `fffefcf7-6dbd-438c-bdd1-259bea8d77b7.jsonl`
- `/ll:verify-issues` - 2026-05-31T02:30:16 - `5267cfef-4fe8-420d-9d08-62e8f926a297.jsonl`
- `/ll:verify-issues` - 2026-05-28T23:48:15 - `0efd786b-4b4c-43ee-9e8e-268bad2cc8a5.jsonl`
- `/ll:format-issue` - 2026-05-24T13:21:58 - `765fa3c6-1a05-4cb7-8170-c01366684b4e.jsonl`
- `/ll:capture-issue` - 2026-05-24T13:15:53Z - `bfd5e964-4cba-4f63-8354-255b3fbb9f18.jsonl`
