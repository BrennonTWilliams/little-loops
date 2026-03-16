---
discovered_date: 2026-03-16
discovered_by: /ll:capture-issue
source_loop: issue-refinement
confidence_score: 100
outcome_confidence: 93
---

# BUG-786: issue-refinement loop `evaluate` conflates `formatted=False` and `has_verify=False` into one route

## Summary

The `issue-refinement` loop's `evaluate` state outputs `NEEDS_FORMAT <id>` for two distinct failure conditions — an issue that is not yet formatted AND an issue that is formatted but hasn't had `/ll:verify-issues` run yet — and routes both to the `format_issues` state. The `format_issues` state always runs `/ll:format-issue` first, so an already-formatted issue gets unnecessarily re-formatted on every cycle until the session log is recognised.

## Current Behavior

The evaluate script in the loop's `evaluate` state:

```python
has_verify = '/ll:verify-issues' in cmds
if not issue.get('formatted', False) or not has_verify:
    print(f'NEEDS_FORMAT {issue["id"]}')
    sys.exit(1)
```

Both `formatted=False` and `has_verify=False` produce identical output (`NEEDS_FORMAT`) and route to `format_issues`, which always runs:

```
1. /ll:format-issue <id> --auto
2. /ll:verify-issues <id> --auto
```

When an issue is already fully formatted but `has_verify=False` (e.g. because `parse_session_log` returns `[]` due to BUG-785), every loop iteration re-runs `/ll:format-issue` unnecessarily. Observed: FEAT-638 had format-issue called 9 times across one run, with the second invocation already reporting "0 structural gaps, 0 actionable quality findings — no changes needed."

## Root Cause

The evaluate script does not distinguish between "needs formatting" and "needs verification" as separate failure modes. The single `NEEDS_FORMAT` signal hides which step is actually needed, and the loop has no `NEEDS_VERIFY`-only route that skips format-issue.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **File**: `loops/issue-refinement.yaml:21`
- **Anchor**: `evaluate` state inline Python classifier — `if not issue.get('formatted', False) or not has_verify:`
- **Routing chain**: `route_format` at `loops/issue-refinement.yaml:54-61` uses `output_contains "NEEDS_FORMAT"` against `${captured.classify.output}`; currently both failure modes emit the same `NEEDS_FORMAT` token and route to `format_issues` at line 70
- **FSM exit code mapping** (`scripts/little_loops/fsm/evaluators.py:93-112`): exit 0 → "yes" → `done`; exit 1 → "no" → `parse_id`; exit 2+ → "error" → `on_error: done` — this informs the exit code fix (see Proposed Fix)

## Proposed Fix

Split the evaluate condition into two distinct output tokens and add a `NEEDS_VERIFY` route in the loop YAML that goes directly to a `verify_only` state (running only `/ll:verify-issues`):

```python
has_verify = '/ll:verify-issues' in cmds
if not issue.get('formatted', False):
    print(f'NEEDS_FORMAT {issue["id"]}')
    sys.exit(1)
if not has_verify:
    print(f'NEEDS_VERIFY {issue["id"]}')
    sys.exit(2)
```

Then add a `route_format` branch for `NEEDS_VERIFY` that routes to a `verify_only` state instead of `format_issues`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**⚠️ Exit code correction**: The `sys.exit(2)` above for `NEEDS_VERIFY` is incorrect. The FSM engine (`scripts/little_loops/fsm/evaluators.py:93-112`) maps exit 2+ → "error" → `on_error: done` in the `evaluate` state (`loops/issue-refinement.yaml:45`), which would terminate the loop rather than route to `parse_id`. **Both `NEEDS_FORMAT` and `NEEDS_VERIFY` must use `sys.exit(1)`**; the `output_contains` routing chain distinguishes the tokens downstream.

**YAML additions required** (`loops/issue-refinement.yaml`):

1. Change `route_format.on_no` at line 60 from `route_score` → `route_verify`
2. Insert new `route_verify` state after `route_format` (before `route_score`):

```yaml
  route_verify:
    evaluate:
      type: output_contains
      source: "${captured.classify.output}"
      pattern: "NEEDS_VERIFY"
    on_yes: verify_only
    on_no: route_score
    on_error: evaluate
```

3. Insert new `verify_only` state after `route_verify` (modeled after `score_issues` at line 77):

```yaml
  verify_only:
    action_type: prompt
    action: |
      Run this command for issue ${captured.issue_id.output}:
      /ll:verify-issues ${captured.issue_id.output} --auto
    next: check_commit
```

**Pattern reference**: Follows the chained `output_contains` router pattern at `loops/backlog-flow-optimizer.yaml:61-84` — three sequential router states each checking one token, falling through via `on_no` to the next.

## Integration Map

### Files to Modify
- `loops/issue-refinement.yaml` — Python classifier condition at line 21; `route_format.on_no` at line 60; add `route_verify` and `verify_only` states

### Dependent Files
- `scripts/little_loops/fsm/evaluators.py:93-112` — `evaluate_exit_code()` maps exit codes to verdicts; constrains exit code choice for NEEDS_VERIFY to 1
- `scripts/little_loops/session_log.py:23-39` — `parse_session_log()` supplies the `commands` list driving `has_verify`; BUG-785 may cause `has_verify=False` even after verify runs (separate issue)

### Similar Patterns
- `loops/backlog-flow-optimizer.yaml:61-84` — three-way chained `output_contains` router to model `route_verify` after
- `loops/issue-refinement.yaml:62-69` — existing `route_score` state as direct template for `route_verify`
- `loops/issue-refinement.yaml:77-82` — existing `score_issues` prompt state as direct template for `verify_only`

### Tests
- `scripts/tests/test_builtin_loops.py:53,179,221` — references `issue-refinement` loop config; verify new states pass schema validation
- `scripts/tests/test_fsm_evaluators.py:290-344` — `output_contains` evaluator tests confirm `NEEDS_VERIFY` pattern matching behavior

## Acceptance Criteria

- [ ] Issues that are `formatted=True` but lack a `verify-issues` session log entry are routed to verify-only (not re-formatted)
- [ ] Issues that are `formatted=False` continue to be routed to `format_issues` (which runs both)
- [ ] `NEEDS_FORMAT` output only appears when `formatted=False`
- [ ] Loop no longer calls `/ll:format-issue` on an issue that already reports "0 structural gaps"
- [ ] Loop YAML has a `NEEDS_VERIFY` branch and corresponding `verify_only` state

## Implementation Steps

1. **Update Python classifier** at `loops/issue-refinement.yaml:21`: split `or` into two separate `if` blocks — `NEEDS_FORMAT` when `not formatted`, `NEEDS_VERIFY` when `not has_verify` — both using `sys.exit(1)` (not 2).
2. **Update `route_format.on_no`** at `loops/issue-refinement.yaml:60`: change `route_score` → `route_verify`.
3. **Add `route_verify` state** after `route_format`: `output_contains "NEEDS_VERIFY"` → `verify_only`; `on_no: route_score` (see Proposed Fix for full YAML).
4. **Add `verify_only` state** after `route_verify`: prompt-type running only `/ll:verify-issues ${captured.issue_id.output} --auto`, `next: check_commit`.
5. **Run tests**: `python -m pytest scripts/tests/test_builtin_loops.py -v -k issue-refinement`
6. **Manual smoke test**: start loop with a `formatted=True` issue missing a verify session log entry; confirm it routes to `verify_only` and does not call `/ll:format-issue`.

## Related Issues

- BUG-785: Root cause of `has_verify=False` persisting for FEAT-638 despite verify running (parser reads wrong section)
- BUG-773 (active): Prompt states missing timeout/on-error in issue-refinement loop

## Labels

`bug`, `loops`, `issue-refinement`, `captured`

## Status

**Open** | Created: 2026-03-16 | Priority: P3

## Session Log
- `/ll:confidence-check` - 2026-03-16T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/846dd31f-a623-4c2c-a94c-fed5d665b7f6.jsonl`
- `/ll:refine-issue` - 2026-03-16T20:30:06 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6197d55e-7699-4fd1-8daf-6cfcd67f79f2.jsonl`
- `/ll:capture-issue` - 2026-03-16T20:08:11Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fffc83c9-009a-4696-8010-040737bf7247.jsonl`
