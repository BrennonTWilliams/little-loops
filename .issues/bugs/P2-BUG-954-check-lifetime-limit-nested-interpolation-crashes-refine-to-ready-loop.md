---
id: BUG-954
discovered_date: 2026-04-05
discovered_by: capture-issue
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

Replace the nested bash fallback on line 46 of `refine-to-ready-issue.yaml` with a non-nested equivalent that the interpolation engine can resolve:

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
- `scripts/little_loops/fsm/executor.py:275` — catches `InterpolationError` and calls `_finish("error")`

### Similar Patterns
- Other `*.yaml` loop files in `scripts/little_loops/loops/` that use bash fallback with `${VAR:-${...}}` syntax should be audited

### Tests
- `scripts/tests/` — add test asserting `check_lifetime_limit` executes (not errors) when `context.max_refine_count` is set

## Implementation Steps

1. Open `scripts/little_loops/loops/refine-to-ready-issue.yaml`, locate line 46
2. Replace `MAX_TOTAL=${MAX_TOTAL:-${context.max_refine_count}}` with `[ -z "$MAX_TOTAL" ] && MAX_TOTAL=${context.max_refine_count}`
3. Audit other loop YAMLs for the same nested `${VAR:-${...}}` pattern
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

**Open** | Created: 2026-04-05 | Priority: P2

---

## Session Log

- `/ll:capture-issue` - 2026-04-05T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a3203fd4-ea84-4c13-b186-96678a2c9062.jsonl`
