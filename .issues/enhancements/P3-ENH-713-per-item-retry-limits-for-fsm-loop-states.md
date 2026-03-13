---
discovered_date: 2026-03-12
discovered_by: capture-issue
confidence_score: 98
outcome_confidence: 72
---

# ENH-713: Per-Item Retry Limits for FSM Loop States

## Summary

Add first-class per-state retry tracking to the FSM executor so that loops processing multiple work items can limit retries per item without burning the global `max_iterations` budget. Currently, a loop stuck on one bad item retries until the global limit is exhausted; this enhancement adds `max_retries` and `on_retry_exhausted` fields to `StateConfig` for automatic per-state retry gating.

## Current Behavior

- `max_iterations` is the only iteration limit, applied globally across all states (`executor.py:409-411`)
- A loop stuck retrying one item (e.g., a single issue that can't be refined) burns through the entire global budget
- The workaround is manual: simulate retry counting with shell states writing to `/tmp/` files (as `issue-refinement.yaml` does at lines 98-111 with `/tmp/issue-refinement-commit-count`)
- This pattern is duplicated across loops that process multiple items

## Expected Behavior

`StateConfig` gains two new optional fields:

```yaml
states:
  execute:
    action: "/ll:refine-issue ${current_item}"
    max_retries: 3
    on_retry_exhausted: skip_item  # transition target when retries exceeded
    on_success: evaluate
    on_failure: execute  # retries up to max_retries times
```

The executor tracks how many times each state has been entered consecutively (or since last reset) and automatically transitions to `on_retry_exhausted` when the count exceeds `max_retries`. The counter resets when a different state is entered or when explicitly reset via a transition.

## Motivation

Every multi-item loop needs retry limiting, and every one currently reimplements it as a shell counter state. This adds 10-15 lines of boilerplate YAML per loop, introduces temp file coupling, and is easy to get wrong (forgetting to reset the counter, race conditions with parallel loops using the same temp file). A first-class mechanism reduces loop complexity and eliminates a class of bugs.

## Proposed Solution

**Option A (Recommended): Executor-level retry tracking**

Add a `_retry_counts: dict[str, int]` to `FSMExecutor`. On each state entry:
- If entering the same state as last time, increment `_retry_counts[state_name]`
- If entering a different state, reset `_retry_counts[prev_state]` to 0
- If `_retry_counts[state_name] > state.max_retries`, transition to `on_retry_exhausted` instead of executing

This requires changes to:
- `schema.py:StateConfig` — add `max_retries: int | None` and `on_retry_exhausted: str | None`
- `executor.py:_execute_state()` — add retry check before action execution
- `validation.py` — validate `on_retry_exhausted` references a valid state, require it when `max_retries` is set
- `fsm-loop-schema.json` — add fields to state schema

**Option B: Reset-on-transition tracking**

Track retries per state independently, only reset when the state succeeds (transitions via `on_success`). This handles cases where a state is re-entered after visiting other states (e.g., evaluate → fix → evaluate → fix). More complex but handles non-consecutive retry patterns.

## API/Interface

New optional fields on `StateConfig` (`schema.py`):

```python
@dataclass
class StateConfig:
    # ... existing fields ...
    max_retries: int | None = None          # Max consecutive entries before on_retry_exhausted
    on_retry_exhausted: str | None = None   # State to transition to when retries exceeded
```

Corresponding additions to `fsm-loop-schema.json` state object:

```json
"max_retries": {
  "type": "integer",
  "minimum": 1,
  "description": "Max consecutive re-entries before transitioning to on_retry_exhausted"
},
"on_retry_exhausted": {
  "type": "string",
  "description": "State to transition to when max_retries is exceeded"
}
```

YAML loop config usage (no breaking change — both fields are optional):

```yaml
states:
  execute:
    action: "/ll:refine-issue ${current_item}"
    max_retries: 3
    on_retry_exhausted: skip_item
    on_success: evaluate
    on_failure: execute
```

Validation constraint: if `max_retries` is set, `on_retry_exhausted` must also be set and must reference a valid state.

## Scope Boundaries

- **In scope**: Per-state retry limits with automatic transition on exhaustion
- **Out of scope**: Per-item tracking (would require the executor to understand "items" as a concept); retry backoff (can be layered via existing `backoff` field); retry limits on terminal states (meaningless)

## Success Metrics

- Loops like `issue-refinement.yaml` can remove shell counter states and use `max_retries` directly
- Generated harness loops (FEAT-712) can use `max_retries` instead of counter boilerplate

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/schema.py` — Add `max_retries` and `on_retry_exhausted` to `StateConfig`
- `scripts/little_loops/fsm/executor.py` — Add retry tracking in `_execute_state()`
- `scripts/little_loops/fsm/validation.py` — Validate `on_retry_exhausted` target exists
- `config-schema.json` or `fsm-loop-schema.json` — Add fields to JSON schema

### Dependent Files (Callers/Importers)
- `scripts/little_loops/fsm/persistence.py` — May need to persist retry counts across handoffs
- `scripts/little_loops/cli/loop/info.py` — Display retry config in loop info

### Similar Patterns
- `issue-refinement.yaml:98-111` — Manual retry counter pattern this replaces
- `executor.py:409-411` — Global `max_iterations` check (similar gate mechanism)

### Tests
- `scripts/tests/test_fsm_executor.py` — Add retry limit tests
- `scripts/tests/test_fsm_validation.py` — Validate retry field requirements

### Documentation
- `skills/create-loop/loop-types.md` — Document `max_retries` in state config reference
- `skills/create-loop/reference.md` — Add retry fields to quick reference

### Configuration
- N/A

## Implementation Steps

1. Add `max_retries` and `on_retry_exhausted` fields to `StateConfig` in `schema.py`
2. Add retry tracking dict and check logic in `FSMExecutor._execute_state()`
3. Add validation rules for retry fields in `validation.py`
4. Update JSON schema
5. Add unit tests for retry exhaustion, counter reset, and handoff persistence
6. Update existing loops (optional) to use `max_retries` instead of shell counters

## Impact

- **Priority**: P3 - Quality-of-life improvement; workaround exists but is verbose and error-prone
- **Effort**: Small - Localized changes to schema, executor, and validation
- **Risk**: Low - Additive feature; existing loops unaffected unless they opt in
- **Breaking Change**: No

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `docs/reference/API.md` | FSM module API reference |

## Labels

`fsm-loops`, `executor`, `schema`, `captured`

## Session Log
- `/ll:verify-issues` - 2026-03-13T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4a26704e-7913-498d-addf-8cd6c2ce63ff.jsonl`
- `/ll:capture-issue` - 2026-03-12 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3b28391f-b086-4d28-86cb-448201c8b40e.jsonl`
- `/ll:format-issue` - 2026-03-13 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/979c9695-36c6-4165-bbbc-4639795e9b05.jsonl`
- `/ll:verify-issues` - 2026-03-13 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/979c9695-36c6-4165-bbbc-4639795e9b05.jsonl`
- `/ll:confidence-check` - 2026-03-13 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/979c9695-36c6-4165-bbbc-4639795e9b05.jsonl`

---

## Verification Notes

- **Date**: 2026-03-13
- **Verdict**: VALID
- `scripts/little_loops/fsm/schema.py` has no `max_retries` or `on_retry_exhausted` fields on `StateConfig`. `executor.py` has no retry tracking dict. `loops/issue-refinement.yaml` lines 101-111 confirm the manual `/tmp/issue-refinement-commit-count` shell counter workaround is present. Feature not yet implemented.

## Status

**Open** | Created: 2026-03-12 | Priority: P3
