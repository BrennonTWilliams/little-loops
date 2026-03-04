---
id: BUG-567
priority: P2
status: active
discovered_date: 2026-03-04
discovered_by: capture-issue
confidence_score: null
outcome_confidence: null
---

# BUG-567: `on_partial` transition silently dropped — not in schema or executor

## Summary

The `on_partial` transition key is referenced in loop YAML files (e.g., `.loops/issue-refinement.yaml` evaluate state has `on_partial: fix`) but is completely absent from the codebase:

- Not defined in `StateConfig` dataclass (`scripts/little_loops/fsm/schema.py`)
- Not handled in `executor.py` routing logic
- Not displayed in `cmd_show` (`scripts/little_loops/cli/loop/info.py`)

When the YAML is parsed via `StateConfig.from_dict()`, any `on_partial` key is silently discarded. The transition never fires at runtime — the loop falls through to whatever `on_failure` resolves to (or errors) instead of routing to the intended state. This is a silent, invisible data loss bug.

## Root Cause

- **File**: `scripts/little_loops/fsm/schema.py`
- **Class**: `StateConfig.from_dict()` (line ~236)
- **Explanation**: `from_dict` only reads explicitly named keys (`on_success`, `on_failure`, `on_error`, `next`). The `on_partial` key is not mapped to any field, so it's ignored. The executor's `_route()` method (~line 629) only handles `success`, `failure`, and `error` verdicts via shorthand fields — `partial` is not a recognized verdict shorthand.

## Expected Behavior

`on_partial` should be a first-class transition on `StateConfig`, routing when an LLM evaluator returns `"partial"` as its verdict. The `llm_structured` evaluator already can return `"partial"` (per the evaluate prompt in issue-refinement), but there's no routing path to act on it.

## Steps to Reproduce

1. Create a loop YAML with `on_partial: some_state` in a state
2. Run the loop such that the LLM evaluator returns `"partial"`
3. Observe: the `partial` verdict is not routed to `some_state`

## Impact

Any loop relying on `on_partial` for graceful handling of ambiguous/truncated evaluator output silently fails to route correctly. The `issue-refinement` loop is affected: its evaluate state specifies `on_partial: fix` to re-run refinement when output is ambiguous, but this never fires.

## Proposed Solution

1. Add `on_partial: str | None = None` to `StateConfig` dataclass and `from_dict`/`to_dict`
2. Handle `partial` verdict in `executor._route()` via `state.on_partial`
3. Display `on_partial` transition in `cmd_show` alongside `on_success`/`on_failure`/`on_error`
4. Include `on_partial` edges in the FSM diagram renderer

## Implementation Steps

1. Add `on_partial` field to `StateConfig` dataclass in `schema.py` and update `from_dict`/`to_dict`
2. Handle `partial` verdict in `executor._route()` — map `partial` → `state.on_partial` the same way `success` maps to `state.on_success`
3. Update `cmd_show` in `info.py` to display `on_partial` transition alongside `on_success`/`on_failure`/`on_error`
4. Add `on_partial` edges to `_render_fsm_diagram` in `info.py`
5. Add regression tests covering: partial verdict routing, missing `on_partial` fallback behavior

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/schema.py` — `StateConfig` dataclass + `from_dict`/`to_dict`
- `scripts/little_loops/fsm/executor.py` — `_route()` method (~line 629)
- `scripts/little_loops/cli/loop/info.py` — `cmd_show` display + `_render_fsm_diagram` edges

### Dependent Files (Callers/Importers)
- TBD — `grep -r "on_partial" scripts/` to find any existing references
- Any `.loops/*.yaml` files that use `on_partial` (e.g., `.loops/issue-refinement.yaml`)

### Similar Patterns
- `on_success`, `on_failure`, `on_error` in `schema.py` and `executor.py` — follow same pattern

### Tests
- `scripts/tests/test_fsm_evaluators.py` — add tests for `partial` verdict routing

### Documentation
- TBD — check if FSM state docs reference verdict types

### Configuration
- N/A

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `docs/ARCHITECTURE.md` | FSM state routing design |

## Session Log
- `/ll:capture-issue` - 2026-03-04T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0d569869-6d78-45db-ae07-4c05f23b46fe.jsonl`
- `/ll:format-issue` - 2026-03-04T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4f47bc1e-2cb1-41eb-be41-2e8dd439840b.jsonl`
