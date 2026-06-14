---
loop: refine-to-ready-issue
timestamp: 2026-06-13T18:59:00Z
scope: builtin
states_before: 23
states_after: 20
flows_collapsed: 0
subloops_extracted: 1
---

# Simplification: refine-to-ready-issue

## Flows collapsed
None — loop has multiple branch points; not a single linear chain.

## Sub-loops extracted
- **verify-confidence-scores** (`scripts/little_loops/loops/oracles/verify-confidence-scores.yaml`)
  — region `confidence_check` .. `verify_scores_persisted_final`, 4 states
  - parameters: `issue_id` (string, required)
  - parent routing: `confidence_check.loop: verify-confidence-scores`
    — `on_success → check_readiness`, `on_failure → diagnose`, `on_error → diagnose`
  - states moved to child: `confidence_check`, `verify_scores_persisted`, `retry_confidence_check`, `verify_scores_persisted_final`
  - `${captured.issue_id.output}` references in action bodies rewritten to `${context.issue_id}`

## Oracle reuse
No existing oracle matched this shape; new file created.

## Equivalence checks
- resolved-graph: equivalent — same initial (`resolve_issue`), same terminals (`done`, `failed`), all original transitions preserved (confidence_check→verify path now lives inside child, parent routes on_success/on_failure instead)
- simulate: no new signals (parent: error-terminates as before; child: terminates normally)
- builtin tests: 3 assertions updated (stale state-name references migrated to child oracle); 826/826 pass

## Test updates
- `test_confidence_check_routes_to_verify_scores_persisted` → renamed to `test_confidence_check_delegates_to_verify_confidence_scores_oracle`; now checks `confidence_check.loop == "verify-confidence-scores"` and `on_success == "check_readiness"`
- `test_verify_scores_persisted_on_yes_routes_to_check_readiness` → loads child oracle YAML; asserts `on_yes == "done"` (maps to parent `on_success → check_readiness`)
- `test_verify_scores_persisted_on_no_routes_to_retry_confidence_check` → loads child oracle YAML; asserts `on_no == "retry_confidence_check"` (unchanged internal routing)
