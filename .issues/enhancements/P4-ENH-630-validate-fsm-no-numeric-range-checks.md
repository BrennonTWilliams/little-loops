---
discovered_commit: 12a6af03c58a3b8f355e265a895b3950db89b66c
discovered_branch: main
discovered_date: 2026-03-07T05:53:04Z
discovered_by: scan-codebase
confidence_score: 100
outcome_confidence: 85
---

# ENH-630: `validate_fsm` has no range checks for `max_iterations`, `backoff`, or `timeout` numeric fields

## Summary

`validate_fsm()` checks structural concerns (unreachable states, missing routing, required evaluator fields) but performs no validation of FSM-level numeric field values. `max_iterations=0`, `backoff=-5.0`, and `timeout=0` are all accepted without warning. The related BUG-602 covers the `max_iterations=0` runtime behavior; this issue covers adding validation to `validate_fsm` to catch these at load time.

## Location

- **File**: `scripts/little_loops/fsm/validation.py`
- **Line(s)**: 193–264 (at scan commit: 12a6af0)
- **Anchor**: `in function validate_fsm()`
- **Permalink**: [View on GitHub](https://github.com/BrennonTWilliams/little-loops/blob/12a6af03c58a3b8f355e265a895b3950db89b66c/scripts/little_loops/fsm/validation.py#L190-L261)
- **Code**:
```python
def validate_fsm(fsm: FSMLoop) -> list[str]:
    errors: list[str] = []
    # Checks: initial state, terminal states, state references, evaluator fields
    # No checks for: max_iterations > 0, backoff >= 0, timeout > 0
    ...
```

## Current Behavior

Invalid numeric values pass validation silently:
- `max_iterations: 0` — loop exits immediately (BUG-602)
- `backoff: -5` — negative sleep, likely raises `time.sleep(-5)` ValueError at runtime
- `timeout: 0` — loop times out immediately on first state entry

## Expected Behavior

`validate_fsm()` should emit validation errors for:
- `max_iterations <= 0`
- `backoff < 0` (negative sleep duration)
- `timeout <= 0`
- `LLMConfig.max_tokens <= 0`
- `LLMConfig.timeout <= 0`

## Motivation

Catching these at load time (before execution begins) gives users a clear error message pointing to the misconfiguration. Runtime errors for these cases are confusing — `time.sleep(-5)` is a `ValueError`, `timeout=0` appears as an immediate `"timed_out"` status.

## Proposed Solution

```python
# In validate_fsm(), after existing structural checks:
if fsm.max_iterations is not None and fsm.max_iterations <= 0:
    errors.append(f"max_iterations must be > 0, got {fsm.max_iterations}")
if fsm.backoff is not None and fsm.backoff < 0:
    errors.append(f"backoff must be >= 0, got {fsm.backoff}")
if fsm.timeout is not None and fsm.timeout <= 0:
    errors.append(f"timeout must be > 0, got {fsm.timeout}")
```

## Scope Boundaries

- Only `validate_fsm()` changes; no runtime behavior changes
- Schema types remain the same (validation is a check, not a type constraint)

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/validation.py` — `validate_fsm()`

### Dependent Files (Callers/Importers)
- `scripts/little_loops/fsm/validation.py` — `load_and_validate()` calls `validate_fsm()` internally
- `scripts/little_loops/cli/loop/config_cmds.py` — `cmd_validate()` calls `validate_fsm()` directly
- `scripts/little_loops/cli/loop/_helpers.py` — calls `load_and_validate()` (indirect)
- `scripts/little_loops/cli/loop/run.py` — calls `load_and_validate()` (indirect)
- `scripts/little_loops/fsm/__init__.py` — re-exports `validate_fsm` as public API

### Similar Patterns
- Existing structural checks in `validate_fsm()` (unreachable states, missing routing, evaluator fields) use the same `errors.append(...)` pattern — new numeric checks follow the same convention

### Tests
- `scripts/tests/test_fsm_schema.py` — primary test file for `validate_fsm()`; add tests for `max_iterations=0`, `backoff=-1`, `timeout=0` (file `test_fsm_validation.py` does not yet exist)

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Add numeric range checks at end of `validate_fsm()`
2. Add tests for each: `max_iterations=0`, `backoff=-1`, `timeout=0`

## Impact

- **Priority**: P4 — Improves developer experience; prevents confusing runtime errors from misconfiguration
- **Effort**: Small — Straightforward additions to `validate_fsm()`
- **Risk**: Low — Purely additive validation; no existing valid configs are rejected
- **Breaking Change**: No (configs with 0/negative values were already broken at runtime)

## Labels

`enhancement`, `fsm`, `validation`, `captured`

## Verification Notes

**Verdict**: VALID — Verified 2026-03-07

- `validate_fsm()` confirmed at `scripts/little_loops/fsm/validation.py` (function `validate_fsm`); no numeric range checks present for `max_iterations`, `backoff`, or `timeout`
- `FSMLoop` fields confirmed: `max_iterations: int = 50`, `backoff: float | None = None`, `timeout: int | None = None` (`scripts/little_loops/fsm/schema.py`)
- Primary existing test file is `test_fsm_schema.py` (not `test_fsm_validation.py` which does not exist); Integration Map updated accordingly

## Resolution

**Status**: Completed — 2026-03-07

### Changes Made

- `scripts/little_loops/fsm/validation.py` — Added 5 numeric range checks in `validate_fsm()` after existing structural checks:
  - `max_iterations <= 0` → error
  - `backoff < 0` → error
  - `timeout <= 0` → error
  - `llm.max_tokens <= 0` → error
  - `llm.timeout <= 0` → error
- `scripts/tests/test_fsm_schema.py` — Added 11 tests covering all new checks (valid and invalid cases for each field)

### Verification

- 96 tests pass (`python -m pytest scripts/tests/test_fsm_schema.py`)
- Lint clean (`ruff check`)
- Type check clean (`mypy`)

## Session Log
- `/ll:scan-codebase` - 2026-03-07T05:53:04Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8d7aaeac-a482-4a78-9f78-be55d16b7093.jsonl`
- `/ll:format-issue` - 2026-03-07T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6a043191-c6ab-48e4-9698-8dbd73149442.jsonl`
- `/ll:verify-issues` - 2026-03-07T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6a043191-c6ab-48e4-9698-8dbd73149442.jsonl`
- `/ll:confidence-check` - 2026-03-07T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6a043191-c6ab-48e4-9698-8dbd73149442.jsonl`
- `/ll:ready-issue` - 2026-03-07T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4e25ef1f-a191-43bd-9b43-c3291051d8a0.jsonl`
- `/ll:manage-issue` - 2026-03-07T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/current.jsonl`

---

## Status

**Completed** | Created: 2026-03-07 | Completed: 2026-03-07 | Priority: P4
