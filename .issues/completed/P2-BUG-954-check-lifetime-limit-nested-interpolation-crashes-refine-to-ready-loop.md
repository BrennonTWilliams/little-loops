---
id: BUG-954
discovered_date: 2026-04-05
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 93
---

# BUG-954: Nested `${}` in `check_lifetime_limit` causes `InterpolationError` crashing `refine-to-ready-issue` loop

## Summary

`check_lifetime_limit` in `refine-to-ready-issue.yaml:46` uses a nested bash variable fallback `${MAX_TOTAL:-${context.max_refine_count}}`. The FSM interpolation engine's regex can't handle nested `${}` syntax — it captures `MAX_TOTAL:-${context.max_refine_count` as the variable name and throws `InterpolationError: Unknown namespace: MAX_TOTAL:-${context`. The sub-loop terminates with `terminated_by: error` before `action_start` is ever emitted, causing any outer loop with `on_error: skip_issue` to cycle indefinitely.

## Current Behavior

Every invocation of the `refine-to-ready-issue` sub-loop crashes at `check_lifetime_limit` with `InterpolationError`. The outer loop routes to `on_error` (e.g. `skip_issue`) on every iteration — never making progress — creating an infinite loop cycling every ~90s.

## Expected Behavior

`check_lifetime_limit` executes its shell command, reads `MAX_TOTAL` from the config context, and either routes to `refine_issue` (under limit) or `issue_ready` (at limit).

## Motivation

Any automation using `refine-to-ready-issue` as a sub-loop hangs indefinitely. This is the primary root cause of the `auto-issue-processor` infinite-loop incident on FEAT-013. The bug is silent — the sub-loop exits in under 1ms with no meaningful error surface to the user.

## Proposed Solution

Replace the nested bash fallback in `check_lifetime_limit` of `refine-to-ready-issue.yaml` with a non-nested equivalent that the interpolation engine can resolve:

```bash
# Before (broken — nested ${} unsupported by interpolation regex):
MAX_TOTAL=${MAX_TOTAL:-${context.max_refine_count}}

# After (clean — simple [ -z ] test, single ${context.*} interpolation):
[ -z "$MAX_TOTAL" ] && MAX_TOTAL=${context.max_refine_count}
```

The Python heredoc above line 46 already sets `MAX_TOTAL` from `context.max_refine_count` when Python succeeds, so this bash fallback is only a safety net; correctness is preserved.

## Root Cause

- **File**: `scripts/little_loops/loops/refine-to-ready-issue.yaml`
- **Anchor**: `check_lifetime_limit` action (line 46)
- **Cause**: The interpolation engine at `scripts/little_loops/fsm/interpolation.py:25` uses `VARIABLE_PATTERN = re.compile(r"\$\{([^}]+)\}")`. The `[^}]+` pattern is greedy and stops at the **first** `}`, so `${MAX_TOTAL:-${context.max_refine_count}}` is parsed as variable name `MAX_TOTAL:-${context.max_refine_count` — an unrecognized namespace — triggering `InterpolationError` at `interpolation.py:100`. The executor catches this at `executor.py:275` and calls `_finish("error")`.

## Location

- **File**: `scripts/little_loops/loops/refine-to-ready-issue.yaml`
- **Line(s)**: 46
- **Anchor**: `check_lifetime_limit` action block
- **Code**:
```bash
MAX_TOTAL=${MAX_TOTAL:-${context.max_refine_count}}
```

## Steps to Reproduce

1. Configure a loop that invokes `refine-to-ready-issue` as a sub-loop (e.g. `auto-issue-processor`)
2. Run the loop with any issue
3. Observe: sub-loop emits `loop_complete terminated_by: error` immediately with no `action_start` event; `check_lifetime_limit` never executes

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` — replace line 46 nested bash fallback

### Dependent Files (Callers/Importers)
- Any project-level loop YAML that invokes `refine-to-ready-issue` as a `loop` action
- `scripts/little_loops/fsm/interpolation.py` — root regex (consider hardening against nested `${}` in a follow-up)
- `scripts/little_loops/fsm/executor.py:423` — `interpolate(action_template, ctx)` call site where `InterpolationError` originates
- `scripts/little_loops/fsm/executor.py:275` — catches `InterpolationError` and calls `_finish("error")`

### Similar Patterns
- Audit of all loop YAMLs in `scripts/little_loops/loops/` confirmed **only one occurrence** of `${VAR:-${context.*}}` nested syntax: `refine-to-ready-issue.yaml:46` — no other files need fixing
- Safe single-level `${context.VAR}` form used correctly in `scripts/little_loops/loops/rl-coding-agent.yaml:56,64` — follow this pattern
- `refine-to-ready-issue.yaml:43` itself already uses the safe single-level form (`${context.max_refine_count}` inside a Python heredoc default)

### Tests
- Add test to `scripts/tests/test_fsm_interpolation.py` — follow `TestInterpolate.test_numeric_value` pattern (line ~180): construct `InterpolationContext(context={"max_refine_count": 5})`, call `interpolate("[ -z \"$MAX_TOTAL\" ] && MAX_TOTAL=${context.max_refine_count}", ctx)`, assert `"MAX_TOTAL=5"` in result
- Or add executor-level test to `scripts/tests/test_fsm_executor.py` — follow `TestVariableInterpolation.test_context_interpolation` pattern (line ~535): use `MockActionRunner` and assert the resolved action string reaches the runner

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Open `scripts/little_loops/loops/refine-to-ready-issue.yaml`, locate line 46
2. Replace `MAX_TOTAL=${MAX_TOTAL:-${context.max_refine_count}}` with `[ -z "$MAX_TOTAL" ] && MAX_TOTAL=${context.max_refine_count}`
3. ~~Audit other loop YAMLs for the same nested `${VAR:-${...}}` pattern~~ — confirmed via grep: `refine-to-ready-issue.yaml:46` is the only occurrence; no other files need changes
4. Add a test for `check_lifetime_limit` execution with a set `max_refine_count`
5. Re-run `auto-issue-processor` and confirm `action_start` appears for `check_lifetime_limit`

## Impact

- **Priority**: P2 — silently breaks all `refine-to-ready-issue` sub-loop invocations, causing infinite outer loops
- **Effort**: Small — one-line fix; optional audit of other loop files
- **Risk**: Low — the change is equivalent behavior; Python path already sets `MAX_TOTAL`
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`bug`, `fsm`, `interpolation`, `refine-to-ready-issue`, `captured`

## Status

**Resolved** | Created: 2026-04-05 | Resolved: 2026-04-05 | Priority: P2

## Resolution

- **Fix**: Replaced nested `${MAX_TOTAL:-${context.max_refine_count}}` on line 46 of `scripts/little_loops/loops/refine-to-ready-issue.yaml` with `[ -z "$MAX_TOTAL" ] && MAX_TOTAL=${context.max_refine_count}`.
- **Tests added**: Two regression tests in `scripts/tests/test_fsm_interpolation.py::TestInterpolate` — `test_check_lifetime_limit_bash_fallback` (validates fixed form) and `test_nested_variable_syntax_raises_interpolation_error` (documents broken nested pattern).
- **Root cause confirmed**: `VARIABLE_PATTERN = re.compile(r"\$\{([^}]+)\}")` in `interpolation.py:25` stops at the first `}`, mangling the nested expression into an unknown namespace.

---

## Session Log
- `/ll:ready-issue` - 2026-04-05T20:59:17 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fe65ef92-61d7-48e7-9480-2ddbdda7849a.jsonl`
- `/ll:confidence-check` - 2026-04-05T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6ee6c09c-8ee0-4bad-8093-0998a2a2b822.jsonl`
- `/ll:refine-issue` - 2026-04-05T20:53:51 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/7aaf98df-ca35-41ef-907a-497c0d4415fb.jsonl`
- `/ll:format-issue` - 2026-04-05T20:47:14 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/93bb5375-947f-4363-9244-b165bc2b59d1.jsonl`

- `/ll:capture-issue` - 2026-04-05T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a3203fd4-ea84-4c13-b186-96678a2c9062.jsonl`
- `/ll:manage-issue` - 2026-04-05T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fe65ef92-61d7-48e7-9480-2ddbdda7849a.jsonl`
