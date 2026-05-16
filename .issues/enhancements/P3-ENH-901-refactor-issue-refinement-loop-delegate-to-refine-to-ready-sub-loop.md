---
discovered_date: 2026-03-31
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 93
---

# ENH-901: Refactor issue-refinement loop to delegate to refine-to-ready-issue sub-loop

## Summary

Replace the inline refinement states in `issue-refinement.yaml` (format_issues, score_issues, refine_issues, verify_only) with a single sub-loop invocation of `refine-to-ready-issue.yaml`, passing the current issue_id as input.

## Current Behavior

`issue-refinement.yaml` duplicates refinement logic inline:
- `format_issues` — runs `/ll:format-issue` then `/ll:verify-issues`
- `score_issues` — runs `/ll:confidence-check`
- `refine_issues` — runs `/ll:refine-issue` then `/ll:confidence-check`
- `verify_only` — runs `/ll:verify-issues`

These `prompt`-type states perform the same pipeline that `refine-to-ready-issue.yaml` already encodes as a proper FSM loop: resolve → format → refine → confidence_check (with retry until thresholds met).

## Expected Behavior

The `route_*` states in `issue-refinement.yaml` collapse into a single sub-loop dispatch state that invokes `refine-to-ready-issue` with `context.input = ${captured.issue_id.output}`. The sub-loop handles all routing internally. After the sub-loop completes, control returns to `check_commit`.

## Motivation

- **DRY**: The four inline states duplicate logic already maintained in `refine-to-ready-issue.yaml`. Bug fixes or improvements to the refinement pipeline must currently be applied in two places.
- **Correctness**: `refine-to-ready-issue` retries refinement until confidence thresholds are met; the inline states run each step only once and rely on the outer loop to re-evaluate.
- **Simplicity**: Removing ~30 lines of routing and prompt states makes the outer loop easier to read and audit.

## Proposed Solution

Replace `route_format`, `route_verify`, `route_score`, `format_issues`, `score_issues`, `refine_issues`, `verify_only` with a single state.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Critical: `action_type: sub_loop` does not exist.** Valid action types are `prompt`, `slash_command`, `shell`, `mcp_tool` (`schema.py:214`). Sub-loop invocation is triggered by the presence of a `loop:` field on a state — no `action_type` at all. The `_execute_state` method in `executor.py:634` checks `if state.loop is not None` before any action_type dispatch.

**Critical: `input:` is not a `StateConfig` field.** `StateConfig` has no `input` attribute (`schema.py:208-231`). To pass a value into the child's `${context.input}`, use `context_passthrough: true` — the executor merges `{**self.fsm.context, **self.captured, **child_fsm.context}` into the child's context (`executor.py:590`). This means any captured variable on the parent becomes `context[key]` in the child. To map `${captured.issue_id.output}` → `context.input` in the child, rename the `parse_id` capture from `"issue_id"` to `"input"`.

**Sub-loop routing uses `on_yes`/`on_no`, not `next`.** Child terminates via `terminal: true` → parent routes `on_yes`; child exhausts iterations or hits error → parent routes `on_no` (`executor.py:615-619`).

**Only existing `loop:` sub-loop state in production**: `examples-miner.yaml:135-139`.

The correct replacement state is:

```yaml
run_refine_to_ready:
  loop: refine-to-ready-issue
  context_passthrough: true
  on_yes: check_commit
  on_no: check_commit
```

And `parse_id` must be updated:
- `capture: "input"` (was `"issue_id"`) — so `context_passthrough` injects the issue ID as `context.input` in the child loop
- `on_yes: run_refine_to_ready` (was `route_format`)

`refine-to-ready-issue.yaml:10-13` already reads `${context.input}` with a fallback to `ll-issues next-issue`, so no changes are needed in the child loop.

`check_commit` does not reference `${captured.issue_id.output}` — it only uses a counter file — so renaming the capture is safe.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/issue-refinement.yaml` — rename `parse_id.capture` to `"input"`, change `parse_id.on_yes` to `run_refine_to_ready`, remove 7 states (`route_format`, `route_verify`, `route_score`, `format_issues`, `score_issues`, `refine_issues`, `verify_only`), add `run_refine_to_ready` sub-loop state
- `scripts/tests/test_builtin_loops.py` — update refs to removed states

### Dependent Files (Callers/Importers)

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `scripts/little_loops/fsm/executor.py` — sub-loop support confirmed at `_execute_state:634` (`if state.loop is not None: return self._execute_sub_loop(state, ctx)`), `_execute_sub_loop:571-619`. The `loop_executor.py` path in the issue was incorrect; the executor lives in `fsm/executor.py`.
- `scripts/little_loops/fsm/schema.py:208-231` — `StateConfig` dataclass; `loop: str | None` field at line 230; `action_type` is a `Literal["prompt", "slash_command", "shell", "mcp_tool"]` (no `sub_loop`)
- `scripts/little_loops/fsm/validation.py:201-209` — `loop` and `action` are mutually exclusive; `validation.py:252` — state with `loop:` set satisfies routing requirements without needing `next:`
- `scripts/little_loops/loops/refine-to-ready-issue.yaml:10-17` — `resolve_issue` state already checks `${context.input}` with fallback; no changes needed
- `scripts/tests/test_builtin_loops.py:377` — `PROMPT_STATES_REQUIRING_ON_ERROR = ["format_issues", "score_issues", "refine_issues"]` — must be removed/updated when those states are deleted
- `scripts/tests/test_builtin_loops.py:384-404` — parametrized tests asserting `on_error == "check_commit"` for the three prompt states — must be removed/updated

### Similar Patterns
- `scripts/little_loops/loops/examples-miner.yaml:135-139` — only existing `loop:` sub-loop state in production YAML; uses `loop: apo-textgrad`, `context_passthrough: true`, `on_success`/`on_failure` routing (aliases for `on_yes`/`on_no`)
- `scripts/little_loops/fsm/executor.py:590` — `context_passthrough` merge: `{**self.fsm.context, **self.captured, **child_fsm.context}`; child's own context keys win, then parent captured, then parent context

### Tests
- `scripts/tests/test_fsm_executor.py:3278-3481` — sub-loop test patterns to model after; constructs child YAML inline and asserts `result.final_state`
- `scripts/tests/test_builtin_loops.py` — must update parametrized tests at lines 377, 384-404

### Documentation
- `docs/guides/LOOPS_GUIDE.md` — documents `issue-refinement` states; update state listing for the loop
- `docs/generalized-fsm-loop.md` — documents `sub_loop` concept; verify the `loop:` field syntax is documented accurately
- `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` — references `issue-refinement.yaml` as a real-world harness example

### Configuration
- N/A

## Implementation Steps

1. In `scripts/little_loops/loops/issue-refinement.yaml`, update `parse_id` (line 21-28):
   - Change `capture: "issue_id"` → `capture: "input"` (required so `context_passthrough` injects the value as `context.input` in the child loop)
   - Change `on_yes: route_format` → `on_yes: run_refine_to_ready`
2. In `issue-refinement.yaml`, remove 7 states: `route_format` (line 29), `route_verify` (line 37), `route_score` (line 45), `format_issues` (line 59), `score_issues` (line 67), `refine_issues` (line 74), `verify_only` (line 53)
3. In `issue-refinement.yaml`, add `run_refine_to_ready` sub-loop state (no `action_type`; use `loop:` field):
   ```yaml
   run_refine_to_ready:
     loop: refine-to-ready-issue
     context_passthrough: true
     on_yes: check_commit
     on_no: check_commit
   ```
4. In `scripts/tests/test_builtin_loops.py`, update lines 377 and 384-404 — remove `"format_issues"`, `"score_issues"`, `"refine_issues"` from `PROMPT_STATES_REQUIRING_ON_ERROR` and the parametrized tests that assert their `on_error == "check_commit"`
5. Run `python -m pytest scripts/tests/test_builtin_loops.py scripts/tests/test_fsm_executor.py -v` to confirm state transitions are valid

## Scope Boundaries

- **In scope**:
  - Renaming `parse_id.capture` from `"issue_id"` to `"input"` in `issue-refinement.yaml`
  - Updating `parse_id.on_yes` from `route_format` to `run_refine_to_ready`
  - Removing states `route_format`, `route_verify`, `route_score`, `format_issues`, `score_issues`, `refine_issues`, `verify_only` from `issue-refinement.yaml`
  - Adding `run_refine_to_ready` sub-loop state using `loop:` + `context_passthrough: true`
  - Updating `test_builtin_loops.py` to remove assertions on deleted states
- **Out of scope**:
  - Changes to `refine-to-ready-issue.yaml` (already compatible via `context.input` at lines 10-13)
  - Modifications to the `ll-loop` FSM executor (sub-loop support already exists in `fsm/executor.py:571-619`)
  - Changes to other loops or automation scripts

## Impact

- **Priority**: P3 - Reduces duplication and improves correctness; not blocking
- **Effort**: Small - Mechanical YAML edit once sub_loop support is confirmed
- **Risk**: Low - No logic change; behavior delegates to an existing tested loop
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`enhancement`, `loops`, `refactor`, `captured`

---

## Resolution

**Resolved** | 2026-03-31 | `/ll:manage-issue enhancement improve ENH-901`

- Renamed `parse_id.capture` from `"issue_id"` to `"input"` so `context_passthrough` injects the issue ID as `context.input` in the child loop
- Updated `parse_id.on_yes` from `route_format` to `run_refine_to_ready`
- Removed 7 inline states: `route_format`, `route_verify`, `route_score`, `format_issues`, `score_issues`, `refine_issues`, `verify_only`
- Added `run_refine_to_ready` sub-loop state using `loop: refine-to-ready-issue` + `context_passthrough: true`
- Removed `TestIssueRefinementLoopOnError` class from `test_builtin_loops.py` (deleted states)
- Added `TestIssueRefinementSubLoop` class with 13 tests covering the new sub-loop wiring

All 175 tests pass.

---

## Status

**Completed** | Created: 2026-03-31 | Priority: P3

## Session Log
- `/ll:ready-issue` - 2026-03-31T23:30:34 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2c43e1fa-eb24-4bbf-9798-e3ba3416d9d0.jsonl`
- `/ll:confidence-check` - 2026-03-31T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/aa9b1b58-ba01-4d31-9284-dc3b8ec1fd7e.jsonl`
- `/ll:refine-issue` - 2026-03-31T23:24:38 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/aa9b1b58-ba01-4d31-9284-dc3b8ec1fd7e.jsonl`
- `/ll:format-issue` - 2026-03-31T23:19:38 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/aa9b1b58-ba01-4d31-9284-dc3b8ec1fd7e.jsonl`
- `/ll:capture-issue` - 2026-03-31T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/aa9b1b58-ba01-4d31-9284-dc3b8ec1fd7e.jsonl`
- `/ll:manage-issue` - 2026-03-31T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2c43e1fa-eb24-4bbf-9798-e3ba3416d9d0.jsonl`
