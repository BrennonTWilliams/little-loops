---
id: ENH-777
type: ENH
priority: P3
status: completed
discovered_date: 2026-03-16
discovered_by: manual
completed_date: 2026-03-16
confidence_score: 100
outcome_confidence: 100
---

# ENH-777: Implement loop-level `default_timeout` for FSM executor

## Summary

Implemented a `default_timeout` field on `FSMLoop` that serves as the per-state action timeout fallback, eliminating the hardcoded 120s executor default and the need to annotate every prompt state individually. Updated `issue-refinement.yaml` to use `default_timeout: 3600` with a `timeout: 86400` total cap, updated BUG-773's proposed fix, created the ENH-776 tracking issue, and added tests covering the full fallback chain.

## Problem

`executor.py` hardcoded `state.timeout or 120` — there was no loop-level default. Any loop author who forgot to annotate a prompt state silently got 120s, which causes SIGKILL on multi-step skills that routinely run 200–300s. The only fix was per-state annotation, which is fragile and hard to discover.

## What Was Implemented

### `scripts/little_loops/fsm/schema.py`
- Added `default_timeout: int | None = None` to `FSMLoop` dataclass (after `timeout`)
- Added serialization in `to_dict()` (only emitted when non-None)
- Added deserialization in `from_dict()` via `data.get("default_timeout")`

### `scripts/little_loops/fsm/executor.py`
- MCP tool path (line 640): `state.timeout or self.fsm.default_timeout or 30`
- Prompt/action path (line 644): `state.timeout or self.fsm.default_timeout or 3600`
- Replaces the previous hardcoded 120s default with a proper fallback chain

### `loops/issue-refinement.yaml`
- Added `default_timeout: 3600` at loop level
- Added `timeout: 86400` loop-level total cap (24h wall-clock bound; replaces removed `timeout: 14400`)
- Removed `timeout: 600` from `refine_issues` (covered by loop default)

### `docs/generalized-fsm-loop.md`
- Added `default_timeout` to the Optional Loop-Level Settings YAML schema reference
- Expanded the Timeouts section from two to three levels: state `timeout:` → loop `default_timeout:` → hardcoded fallback (3600s prompt / 30s MCP)

### `.issues/enhancements/P3-ENH-776-add-loop-level-default-timeout.md`
- Created tracking issue for the schema/executor changes with full acceptance criteria

### `.issues/bugs/P2-BUG-773-…`
- Revised Proposed Fix section: split into "immediate (no dependency)" (`on_error: check_commit`) and "once ENH-776 lands" (`default_timeout: 3600`)
- Revised Acceptance Criteria to match the two-phase fix
- Added `schema.py` and `executor.py` as dependency files

### `scripts/tests/test_fsm_executor.py`
- Added `TestDefaultTimeout` class with three tests:
  - `test_state_timeout_used_when_set`: per-state timeout takes precedence (300 wins over default_timeout=3600)
  - `test_default_timeout_used_when_state_has_none`: loop default used when no state timeout
  - `test_hardcoded_fallback_when_neither_set`: 3600s hardcoded fallback when both are None

## Verification

- All 3 new tests pass
- Full suite: 3552 passed, 5 pre-existing failures (unrelated CLI list output tests)
