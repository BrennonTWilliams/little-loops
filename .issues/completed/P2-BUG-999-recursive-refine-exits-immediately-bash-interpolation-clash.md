---
discovered_date: 2026-04-08
discovered_by: session-investigation
---

# BUG-999: recursive-refine loop exits immediately due to bash/interpolation syntax clash

## Summary

`ll-loop run recursive-refine <ID>` completes after exactly 1 iteration with no action output and no error message, leaving the user with no indication of what went wrong.

## Context

The Python interpolation engine (`fsm/interpolation.py`) uses `VARIABLE_PATTERN = re.compile(r"\$\{([^}]+)\}")`, which matches **any** `${...}` token in a shell action — including bare bash variables like `${COUNT}`. Since bash variables have no dot-separated namespace prefix (the engine requires `namespace.path` format), `interpolate()` raises:

```
InterpolationError("Invalid variable: ${COUNT} (expected namespace.path)")
```

This exception fires at `executor.py:475` (`action = interpolate(action_template, ctx)`) — **before** `action_start` is emitted at line 478. The `InterpolationError` is caught silently at `executor.py:307-313`:

```python
except InterpolationError as exc:
    return self._finish("error", error=...)
```

`_finish` does not include the error in `ExecutionResult` or in any emitted event, so the loop ends with no diagnostic output. The user only sees:

```
[1/500] parse_input (0s)
Loop completed: parse_input (1 iterations, 0.0s)
```

The pre-run validation (`run.py:97-115`) uses `r"\$\{context\.([^}.]+)"` — it only checks `${context.xxx}` patterns and silently misses bare `${VAR}` tokens.

## Affected States

| State | Bad token | Namespace check |
|---|---|---|
| `parse_input` | `${COUNT}` | No dot → InterpolationError |
| `enqueue_children` | `${CHILD_COUNT}` | No dot → InterpolationError |
| `enqueue_or_skip` | `${CHILD_COUNT}` | No dot → InterpolationError |
| `done` | `${PASSED_LIST:-none}` | No dot (colon-dash, not dot) → InterpolationError |
| `done` | `${SKIPPED_LIST:-none}` | No dot → InterpolationError |

`parse_input` is hit first (initial state), causing the immediate exit.

## Impact

- **Priority**: P2 — `recursive-refine` is completely non-functional; failure is silent with no actionable error
- **Effort**: Trivial — drop braces from simple vars; use `$${...}` escape for default-value expansions
- **Risk**: Low — pure YAML text change

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| architecture | docs/ARCHITECTURE.md | FSM loop execution model |
| API | docs/reference/API.md | interpolation module |

---

**Priority**: P2 | **Created**: 2026-04-08

---

## Resolution

- **Action**: fix
- **Completed**: 2026-04-08
- **Status**: Completed

### Root Cause

`recursive-refine.yaml` used `${VAR}` bash variable syntax in shell actions. The Python interpolation engine treated these as template variables, found no dot-separated namespace, and raised `InterpolationError` silently before any shell execution occurred.

### Changes Made

`scripts/little_loops/loops/recursive-refine.yaml` — five token fixes:

| State | Before | After | Rationale |
|---|---|---|---|
| `parse_input` | `${COUNT}` | `$COUNT` | Drop braces; bash accepts brace-free |
| `enqueue_children` | `${CHILD_COUNT}` | `$CHILD_COUNT` | Same |
| `enqueue_or_skip` | `${CHILD_COUNT}` | `$CHILD_COUNT` | Same |
| `done` | `${PASSED_LIST:-none}` | `$${PASSED_LIST:-none}` | Braces required for `:-` default; use engine escape |
| `done` | `${SKIPPED_LIST:-none}` | `$${SKIPPED_LIST:-none}` | Same |

### Verification Results

- Loop now advances past `parse_input` to `dequeue_next` on the first run
- No other built-in loops use bare `${VAR}` (confirmed by grep)
