---
id: ENH-741
type: ENH
priority: P3
status: completed
discovered_date: 2026-03-14
discovered_by: manual
confidence_score: 100
outcome_confidence: 100
---

# ENH-741: Extend `plugin-health-check` into a convergence FSM loop

## Summary

`plugin-health-check` was restructured from a sequential workflow with a one-shot repair branch
into a genuine convergence FSM loop that iterates until the plugin configuration is provably
healthy. The `audit_config` state was first decomposed into `audit_counts` + `audit_refs`
(committed separately), then the loop was extended with proper convergence routing, terminal
failure states, increased iteration budget, and session-handoff support.

## Problem

The original loop was a linear happy path masquerading as a loop:

- `fix_config` routed back to `validate_plugin` (re-ran shell validation but skipped the
  audit that detected the problem, so fixes were never re-verified by the audit states)
- `route_audit` had no `on_partial` branch — an ambiguous audit result would fall through to
  `on_error: verify_hooks`, skipping repair entirely
- `fix_hooks` had no `on_error` exit — a broken prompt state had no escape route
- `max_iterations: 5` was too low for a loop that may need multiple fix→audit cycles
- No `failed` terminal state — the loop could not represent a definitive failure outcome
- No `on_handoff` — the loop couldn't survive a session boundary

## Solution

### Structural changes

**Before** (broken convergence):
```
validate_plugin → count_assets → audit_counts → audit_refs → route_audit
                                                                    ↓ on_failure
                                               fix_config ←─────────┘
                                                    ↓ next
                                               validate_plugin  ← skips audit re-check
```

**After** (true convergence):
```
[SETUP ONCE]  validate_plugin → count_assets →
[CONVERGE]    audit_counts → audit_refs → route_audit
                    ↑                         ↓ on_partial (ambiguous)
                    ↑                         ↓ on_failure
                    └──── fix_config ─────────┘
                               ↓ on_error
                            failed (terminal)
[EXIT OK]     route_audit → on_success → verify_hooks → commit → done
[EXIT FAIL]   verify_hooks/fix_hooks → on_error → failed
```

### Specific edits to `loops/plugin-health-check.yaml`

1. **`fix_config`**: `next: validate_plugin` → `next: audit_counts`; added `on_error: failed`
2. **`route_audit`**: added `on_partial: audit_counts`
3. **`fix_hooks`**: added `on_error: failed`
4. **`max_iterations`**: `5` → `15`
5. **`on_handoff: spawn`**: added at top level
6. **`failed` terminal state**: added after `done`

## Verification

```
ll-loop validate plugin-health-check
# → plugin-health-check is valid
# → States: validate_plugin, count_assets, audit_counts, audit_refs, route_audit,
#            fix_config, verify_hooks, fix_hooks, commit, done, failed
# → Max iterations: 15
```

- `fix_config` routes to `audit_counts` (not `validate_plugin`) ✓
- `route_audit` has `on_partial: audit_counts` ✓
- `failed` terminal state exists ✓
- 11 states, 18 transitions ✓

## Files Changed

- `loops/plugin-health-check.yaml` — convergence routing, `failed` state, `max_iterations`, `on_handoff`

## Commits

- `refactor(loops): split audit_config into audit_counts + audit_refs in plugin-health-check`
- `feat(loops): extend plugin-health-check into convergence FSM loop`
