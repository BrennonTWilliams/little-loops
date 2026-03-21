# Implementation Plan: FEAT-789 — context-health-monitor FSM Loop

**Date**: 2026-03-20
**Issue**: FEAT-789
**Status**: In Progress

---

## Summary

Create `loops/context-health-monitor.yaml` — an FSM loop that monitors context health using scratch file accumulation as an observable proxy for context pressure, then applies targeted remediation (scratch compaction, output archival).

## Research Findings

- **Path resolution**: `ll-loop validate` resolves names via: `.loops/<name>.yaml` → `loops/<name>.yaml` (built-in). File goes in `loops/` alongside `backlog-flow-optimizer.yaml`, `docs-sync.yaml`, etc.
- **Required top-level fields**: `name`, `initial`, `states` — all others optional.
- **Pure routing states**: Valid — only `evaluate:` + transition keys, no `action:` or `action_type:`.
- **`capture:` on shell states**: Stores `{output, stderr, exit_code, duration_ms}`; accessed as `${captured.<name>.output}` in subsequent states.
- **`evaluate.type: output_contains`**: Regex match against `source:` string; `on_yes` fires on match, `on_no` on non-match.
- **`${context.<key>}`**: Interpolated from top-level `context:` block before shell/prompt execution.
- **All state transitions**: Must reference states present in `states:` — validated by `validate_fsm`.
- **Terminal state**: At least one state must have `terminal: true`.

## Corrections Applied (from issue Second Pass)

1. **`assess_context` sort**: `find ... -exec du -sk {} \; | sort -rn` (not `sort -k5 -rn` which expects 5-field input)
2. **`compact_scratch`**: Include `${captured.snapshot.output}` so LLM has the file list
3. **`archive_outputs`**: Include `${captured.snapshot.output}` so LLM has the file list

## State Machine

```
assess_context → self_assess → route → done (CONTEXT_HEALTHY)
                                     ↘ route_scratch → compact_scratch → verify → assess_context
                                                     ↘ archive_outputs → verify → assess_context
```

## Implementation

**Single file**: `loops/context-health-monitor.yaml`

Key design decisions:
- `route` and `route_scratch` are pure routing states (no action, only evaluate + transitions)
- Both routing states include `on_error:` for robustness (following `backlog-flow-optimizer.yaml` pattern)
- `max_iterations: 10` prevents infinite `verify → assess_context` cycle

## Verification

- [ ] `ll-loop validate context-health-monitor` passes (exit 0)
- [ ] `assess_context` reads `.claude/ll-context-state.json` with graceful fallback
- [ ] All state transitions reference valid state names
- [ ] `done` has `terminal: true`
- [ ] `max_iterations: 10`, `timeout: 3600`
