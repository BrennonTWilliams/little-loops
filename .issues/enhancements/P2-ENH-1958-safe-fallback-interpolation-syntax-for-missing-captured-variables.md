---
id: ENH-1958
type: ENH
priority: P2
status: done
captured_at: '2026-06-05T18:05:10Z'
discovered_date: 2026-06-05
discovered_by: capture-issue
parent: EPIC-1962
confidence_score: 90
---

# ENH-1958: Add Safe/Fallback Interpolation Syntax for Missing Captured Variables

## Summary

The FSM interpolation engine in `scripts/little_loops/fsm/interpolation.py` always raises `InterpolationError` when a `${namespace.path}` reference cannot be resolved. There is no syntax for "use this variable if it exists, otherwise use a default value." This makes any state that references a captured variable from a potentially-bypassed state a ticking time bomb — if the capturing state was skipped (e.g., via `resume_check` bypass), the loop terminates with an unrecoverable error.

Add a default-value syntax to `${...}` interpolation: `${captured.var.path:default=fallback}` or `${captured.var.path?}` (returns empty string).

## Current Behavior

When a state's action template contains `${captured.selected_step.output}` but `select_step` was never executed (e.g., because `resume_check` emitted `RESUME_SKIP → mark_done`, bypassing `select_step`), `interpolate()` calls `InterpolationContext.resolve("captured", "selected_step.output")` which raises `InterpolationError("Path 'selected_step' not found in captured")`.

The executor catches this in `_run_action_or_route()` and routes to `state.on_error`. If `on_error` points to a terminal state (like `diagnose`), the loop ends. There is no way for the loop author to say "this variable might not exist yet — use a default."

**Specific failure trace** (from `general-task` loop, 2026-06-05):
```
[1] define_done → ✅
[2] plan → ✅
[3] resume_check → RESUME_SKIP (false positive from stale checkpoint)
[4] mark_done → ✅ (bypassed — no step was selected)
[5] check_done → ❌ Path 'selected_step' not found in captured → diagnose (terminal)
```

The `resume_check` false positive is a separate bug (BUG-1960), but the terminal crash in `check_done` would have been avoidable if the action could safely reference `${captured.selected_step.output}` with a fallback.

## Expected Behavior

Loop authors should be able to write:

```
${captured.selected_step.output:default=No step was selected}
```

or:

```
${captured.selected_step.output?}
```

When the path doesn't exist:
- The `:default=...` form returns the specified default string
- The `?` form returns an empty string

When the path DOES exist, both forms return the resolved value as normal.

This allows states to gracefully degrade when optional upstream captures are missing, without needing `on_error` gymnastics or duplicated states for every possible bypass path.

## Motivation

- **Prevents terminal crashes**: The `check_done` → `diagnose` terminal failure would have been a graceful degradation instead
- **Simplifies loop authoring**: Authors don't need to design complex routing just to handle "maybe this capture exists"
- **General utility**: Many loops have optional or conditionally-captured variables. Currently every one is a potential crash site
- **Defense in depth**: Even with careful routing, unforeseen code paths can bypass capture states. Safe interpolation is a safety net

## Scope Boundaries

- **In scope**: Addition of `:default=` and `?` suffix syntax to `VARIABLE_PATTERN` and `replace_var()` in `scripts/little_loops/fsm/interpolation.py`; tests for both forms across all namespaces (`captured`, `context`, `state`)
- **Out of scope**: Changes to how `$${...}` escape sequences work (unchanged); broader templating engines beyond FSM interpolation; changes to `executor.py` error routing (existing `on_error` behavior is preserved for unsuffixed references); bash `:-` / `:+` parameter expansion syntax (intentionally avoided to prevent confusion with `${...}` escape)

## Proposed Solution

### Syntax Design

Two forms, both implemented in `interpolate()`:

**Form A — Explicit default:**
```
${namespace.path:default=value}
```
Example: `${captured.selected_step.output:default=No step was selected}`

**Form B — Nullable (empty string fallback):**
```
${namespace.path?}
```
Example: `${captured.selected_step.output?}`

### Implementation

In `scripts/little_loops/fsm/interpolation.py`:

1. Update `VARIABLE_PATTERN` regex to optionally capture a `:default=...` or `?` suffix
2. In `replace_var()`, after resolving (or catching `InterpolationError`), apply the fallback:
   - If `?` suffix: return `""` on resolution failure
   - If `:default=...` suffix: return the default string on resolution failure
   - If no suffix: raise `InterpolationError` as before (backward compatible)

### Edge Cases

- `$${:default=...}` — the `$${` escape still produces literal `${:default=...}` for the shell (no change to escape logic)
- Default values containing `}` — use a quoting/escaping mechanism or document the limitation
- `${context.input?}` — works identically for all namespaces, not just `captured`

## API/Interface

N/A — No public API changes. The `interpolate()` function signature (`def interpolate(template: str, ctx: 'InterpolationContext') -> str`) is unchanged. The `InterpolationContext.resolve()` method signature is unchanged. The new `:default=` and `?` suffixes are parsed internally within `replace_var()` and `VARIABLE_PATTERN`; callers of `interpolate()` see only the resolved string result.

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/interpolation.py` — add `:default=` and `?` syntax parsing in `replace_var()` and `VARIABLE_PATTERN`; update `_get_nested()` or `resolve()` to support graceful failure mode
- `scripts/tests/test_fsm_interpolation.py` — add tests for both forms across all namespaces

### Dependent Files (Callers/Importers)
- `scripts/little_loops/fsm/executor.py` — no changes needed; `interpolate()` return type is still `str`
- All loop YAML files — no changes needed; existing `${...}` without suffix continues to raise on missing paths

### Similar Patterns
- BUG-1384 (done): `$${...}` escape handling — same code path, different concern (making escapes work vs. handling missing values)
- BUG-770 (done): `InterpolationError` for missing `context.input` — the same crash class, but for context vars instead of captured vars

### Tests
- `test_fsm_interpolation.py::TestInterpolate` — add:
  - `interpolate("${captured.missing?:default=fallback}", ctx)` → `"fallback"` when `missing` not in captured
  - `interpolate("${captured.missing?}", ctx)` → `""` when `missing` not in captured
  - `interpolate("${captured.present.output?:default=fb}", ctx)` → actual value when `present` exists
  - `interpolate("${captured.missing.output}", ctx)` → still raises `InterpolationError` (no suffix = backward compatible)
  - Mixed: `interpolate("X=${captured.a?:default=N/A} Y=${context.real_var}", ctx)` with `a` missing
  - Default containing special chars: `interpolate("${captured.x?:default=no step -- see plan}")`

### Documentation
- `docs/generalized-fsm-loop.md` — add `:default=` and `?` to the Resolution Rules table
- `docs/guides/LOOPS_GUIDE.md` — add examples of safe interpolation
- `docs/reference/API.md` — update interpolation code samples

## Implementation Steps

1. **Design final syntax** — confirm `:default=` and `?` are unambiguous with existing `${namespace.path}` format and don't conflict with bash operators (`:-`, `:+`) that pass through via `$${...}`
2. **Update `VARIABLE_PATTERN`** — extend the regex to capture the optional suffix without breaking existing matches
3. **Update `replace_var()`** — add try/except around `ctx.resolve()`, apply fallback on `InterpolationError` when suffix present
4. **Add tests** — cover both forms, all namespaces, backward compatibility, mixed patterns
5. **Update docs** — three doc files as listed above
6. **Verify** — run full test suite: `python -m pytest scripts/tests/test_fsm_interpolation.py scripts/tests/test_fsm_executor.py -x --tb=short`

## Success Metrics

- **Crash elimination**: Zero `InterpolationError` terminations for `${...}` references using `:default=` or `?` suffix when the captured path is missing (measured by running loops with intentionally-bypassed capture states)
- **Backward compatibility**: All existing tests in `test_fsm_interpolation.py` and `test_fsm_executor.py` continue to pass without modification — unsuffixed `${...}` references still raise `InterpolationError` on missing paths
- **Loop resilience**: The `general-task` loop (or equivalent test loop) survives a `resume_check → RESUME_SKIP` false positive without terminating, when `check_done` references use the new fallback syntax

## Impact

- **Priority**: P2 — Causes terminal loop failures; the workaround (complex routing) is fragile and easy to get wrong
- **Effort**: Medium — ~50-100 lines of code + tests + docs; regex change is the riskiest part
- **Risk**: Low — backward compatible (unsuffixed `${...}` still raises); only affects states that opt in with the new syntax
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`enhancement`, `fsm`, `interpolation`, `safety`, `loops`

## Session Log
- `/ll:format-issue` - 2026-06-05T18:13:16 - `98f9b886-3494-4e5c-987d-3e42dd40ad14.jsonl`
- `/ll:capture-issue` - 2026-06-05T18:05:10Z - `6111e846-8894-477b-81b3-17824f89e659.jsonl`
