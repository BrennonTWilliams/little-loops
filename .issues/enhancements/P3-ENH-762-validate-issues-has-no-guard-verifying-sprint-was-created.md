---
discovered_date: 2026-03-15
discovered_by: analyze-loop
source_loop: sprint-build-and-validate
source_state: validate_issues
---

# ENH-762: validate_issues proceeds without confirming sprint was created

## Summary

In the `sprint-build-and-validate` loop, the `create_sprint` state ran `/ll:create-sprint` interactively and captured output that asked a clarifying question ("What should this sprint be named?") rather than actually creating a sprint. The FSM routed to `validate_issues` regardless, which then ran `/ll:confidence-check` against an empty context and returned "No active sprint is loaded." This ambiguous output cascaded into `route_validation` getting a `blocked` verdict and failing the loop. The `create_sprint → validate_issues` transition has no guard to verify the sprint was actually created before proceeding.

## Loop Context

- **Loop**: `sprint-build-and-validate`
- **State**: `validate_issues`
- **Signal type**: retry_flood (ambiguous downstream failure from missing guard)
- **Occurrences**: 1 (captured at iteration ~5–6)
- **Last observed**: 2026-03-15T22:48:44+00:00

## History Excerpt

Events leading to this signal:

```json
[
  {
    "event": "action_complete",
    "state": "create_sprint",
    "exit_code": 0,
    "duration_ms": 86585,
    "is_prompt": true,
    "output": "What should this sprint be named? Suggested options:\n1. `init-and-arch` (Recommended)..."
  },
  {
    "event": "route",
    "from": "create_sprint",
    "to": "validate_issues"
  },
  {
    "event": "action_complete",
    "state": "validate_issues",
    "exit_code": 0,
    "duration_ms": 115055,
    "is_prompt": true,
    "output": "No active sprint is loaded — `ll-sprint show` returns nothing..."
  }
]
```

## Expected Behavior

The `create_sprint` state should verify that a sprint was successfully created before routing to `validate_issues`. A lightweight check — e.g., `ll-sprint show` returning a non-empty result — would catch the case where the prompt action asked a question but no sprint file was written.

## Proposed Fix

Add a `route_create` evaluate state between `create_sprint` and `validate_issues`:

```yaml
route_create:
  evaluate:
    type: shell
    command: "ll-sprint show --json 2>/dev/null | python3 -c 'import sys,json; d=json.load(sys.stdin); sys.exit(0 if d.get(\"issues\") else 1)'"
  on_pass: validate_issues
  on_fail: create_sprint   # retry sprint creation
```

Alternatively, update the `create_sprint` prompt to instruct Claude to confirm sprint creation with `ll-sprint show` before completing.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

> **Note:** The YAML snippet above has 4 schema errors that must be corrected in the implementation:
>
> 1. `type: shell` — not a valid `EvaluateConfig` type. Valid types per `scripts/little_loops/fsm/schema.py:56–65`: `exit_code`, `output_numeric`, `output_json`, `output_contains`, `convergence`, `diff_stall`, `llm_structured`, `mcp_result`.
> 2. `command:` — not a valid field on `EvaluateConfig`. The shell command goes in `action:` on the state itself, with `action_type: shell`.
> 3. `on_pass:` / `on_fail:` — not valid `StateConfig` fields (`schema.py:179–226`). Correct field names are `on_yes:` and `on_no:`.
> 4. `ll-sprint show --json` — `show` has no `--json` flag (`scripts/little_loops/cli/sprint/__init__.py:142–147`). `--json` exists only on `list`.

**Correct YAML** (following the pattern at `loops/docs-sync.yaml:11–19`):

```yaml
route_create:
  action: "ll-sprint list 2>/dev/null | grep -q ."
  action_type: shell
  evaluate:
    type: exit_code
  on_yes: validate_issues
  on_no: create_sprint
  on_error: create_sprint
```

`ll-sprint list | grep -q .` exits 0 if any sprint exists, exits 1 if no output (no sprint was created). `ll-sprint show` is an alternative but requires a sprint name argument; `ll-sprint list` needs no arguments and is the simpler guard.

The `create_sprint` state at `loops/sprint-build-and-validate.yaml:35` also needs its `next:` updated:

```yaml
# Before:
    next: validate_issues
# After:
    next: route_create
```

## Integration Map

### Files to Modify
- `loops/sprint-build-and-validate.yaml` — add `route_create` state (after line 35) and update `create_sprint.next` from `validate_issues` to `route_create` (line 35)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/fsm/executor.py:564–578` — handles `next:` unconditional transitions; will naturally follow the updated `next: route_create`
- `scripts/little_loops/fsm/executor.py:580–602` — handles evaluate states; will execute the new `route_create` shell action and route via `on_yes`/`on_no`
- `scripts/little_loops/fsm/evaluators.py:93–112` — `evaluate_exit_code`: exits 0 → verdict `yes`, exit 1 → verdict `no`, exit 2+ → verdict `error`

### Similar Patterns
- `loops/docs-sync.yaml:11–19` — canonical `action_type: shell` + `evaluate: type: exit_code` + `on_yes`/`on_no`/`on_error` pattern to follow directly
- `loops/fix-quality-and-tests.yaml:64–81` — `exit_code` evaluate with `on_no` retrying an earlier state

### Tests
- `scripts/tests/test_builtin_loops.py` — tests for all built-in loop YAML files; will validate the new state passes schema checks
- `scripts/tests/test_fsm_evaluators.py` — evaluate state handling (relevant if adding unit tests)

### Documentation
- `docs/guides/LOOPS_GUIDE.md` — loop YAML format guide; no update needed (existing evaluate patterns already documented)

## Implementation Steps

1. In `loops/sprint-build-and-validate.yaml:35`, change `next: validate_issues` → `next: route_create`
2. Insert the `route_create` state block after the `create_sprint` state (between lines 35 and 36), using the correct schema pattern from `loops/docs-sync.yaml:11–19`
3. Verify the new state is reachable and `validate_issues` remains reachable from `route_create.on_yes`
4. Run `python -m pytest scripts/tests/test_builtin_loops.py -v` to confirm schema validation passes
5. Optionally run `ll-loop test sprint-build-and-validate` to validate the loop structure

## Acceptance Criteria

- [ ] Loop does not route to `validate_issues` when no sprint has been created
- [ ] If sprint creation fails or is incomplete, the loop retries `create_sprint`
- [ ] `validate_issues` always runs against a valid, non-empty sprint

## Labels

`enhancement`, `loops`, `captured`

## Status

**Open** | Created: 2026-03-15 | Priority: P3


## Session Log
- `/ll:refine-issue` - 2026-03-15T23:06:05 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3e607ee0-ad85-4e70-ba70-ec2a6350e59a.jsonl`
