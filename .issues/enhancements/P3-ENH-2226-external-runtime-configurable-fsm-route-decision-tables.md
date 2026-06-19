---
id: ENH-2226
type: ENH
priority: P3
status: open
discovered_date: 2026-06-19
discovered_by: capture-issue
captured_at: '2026-06-19T03:17:41Z'
---

# ENH-2226: External/runtime-configurable FSM route decision tables

## Summary

Add the ability to configure FSM loop routing (the `route:` decision table) from outside the loop YAML — via CLI override, a shared config file, or context variables — without editing the loop YAML directly.

## Motivation

Currently, `route:` tables are fixed at YAML authoring time and embedded inline in each loop file. There is no mechanism to:

- Override routing for a specific run without modifying the loop YAML
- Share a decision table across multiple loops or states
- Inject routing policy via `--context` or a config file at invocation time

This makes it hard to experiment with routing variants (A/B test a new routing policy), reuse common dispatch tables, or let downstream callers customize routing behavior without forking the loop.

## Current Behavior

`route:` is a static `dict[str, str]` field on `StateConfig` (`schema.py:425`), populated from YAML at parse time. `RouteConfig.from_dict` (`schema.py:204`) builds it once; the executor resolves it from the frozen state object at runtime (`executor.py:1492`). There is no injection point for external overrides.

## Expected Behavior / Options

At minimum, one of:

1. **Context-variable interpolation in route targets** — allow `route: { IMPLEMENT: "{{context.override_implement_state}}" }` so callers can redirect a single arm without touching the YAML.
2. **Named shared route tables** — define a `route_tables:` block at loop top-level (or in a lib fragment) and reference it as `route: $my_table` from any state.
3. **CLI route-override flag** — `ll-loop run <loop> --route-override IMPLEMENT=gate_b` patches a single arm for one run without editing the file.

## Implementation Steps

1. Audit `RouteConfig` and `StateConfig` in `schema.py` to understand the parse-time freeze point.
2. Pick the lightest approach (context interpolation is probably the smallest delta — `_resolve_route` in `executor.py:1524` already calls `interpolate()`; check if `route:` values are passed through it).
3. If interpolation already threads through `_resolve_route`, the only change may be allowing `context.*` refs in route values and documenting it.
4. Add tests verifying a context variable redirects routing to the expected state.
5. Update `LOOPS_REFERENCE.md` with the new syntax.

## Related

- ENH-2166 (implemented `classify + route:` pattern in rn-remediate)
- ENH-2165 (added `classify` evaluator)
- `scripts/little_loops/fsm/schema.py` — `RouteConfig`, `StateConfig`
- `scripts/little_loops/fsm/executor.py` — `_route()` (line ~1492), `_resolve_route()` (line ~1524)

## Status

open

---

## Session Log
- `/ll:capture-issue` - 2026-06-19T03:17:41Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/546354e6-5520-427c-b4d8-a9c8a1f4198c.jsonl`
