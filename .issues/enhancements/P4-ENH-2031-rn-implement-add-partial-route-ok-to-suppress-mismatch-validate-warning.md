---
id: ENH-2031
type: ENH
priority: P4
status: done
captured_at: '2026-06-08T00:00:00Z'
discovered_date: 2026-06-08
discovered_by: audit-loop-run
confidence_score: 100
outcome_confidence: 90
score_complexity: 25
score_test_coverage: 15
score_ambiguity: 25
score_change_surface: 25
---

# ENH-2031: Add `partial_route_ok: true` to rn-implement to suppress MR-4 validate warning

## Summary

`run_remediation` state has `on_yes: classify_remediation` and `on_no: classify_remediation` — identical targets. By the MR-4 validation rule, `ll-loop validate` flags this as a potential verdict-laundering defect. The design is intentional: outcome discrimination happens via the `subloop_outcome_<ID>.txt` artifact that `classify_remediation` reads. Adding `partial_route_ok: true` at the loop top-level suppresses the false-positive warning.

## Current Behavior

`ll-loop validate rn-implement` emits a MR-4 warning for the `run_remediation` state because `on_yes` and `on_no` both target `classify_remediation` — identical routing triggers the validator's verdict-laundering check, even though the design is intentional.

## Expected Behavior

`ll-loop validate rn-implement` completes without emitting a MR-4 warning. The `partial_route_ok: true` top-level annotation signals to the validator that the identical routing is intentional.

## Acceptance Criteria

- [ ] `ll-loop validate rn-implement` no longer emits a MR-4 warning for `run_remediation`
- [ ] The YAML diff is minimal (top-level annotation only, no state changes)

## Implementation Notes

Add one line to `loops/rn-implement.yaml` top-level block:

```yaml
partial_route_ok: true  # run_remediation.on_yes==on_no by design; classify_remediation reads subloop_outcome artifact
```

## Scope Boundaries

- Top-level `partial_route_ok: true` annotation only — no state logic changes
- Does not modify any other loop files or validator rules
- Does not alter FSM behavior of `rn-implement` at runtime

## Files

- `loops/rn-implement.yaml` — top-level block

## Impact

- **Priority**: P4 - Low; affects developer experience (spurious validation warnings), not runtime behavior
- **Effort**: Small - Single-line addition to a YAML file
- **Risk**: Low - Annotation-only change; no FSM logic altered
- **Breaking Change**: No

## Labels

`loop-validation`, `enhancement`, `captured`

## Status

**Open** | Created: 2026-06-08 | Priority: P4


## Session Log
- `/ll:format-issue` - 2026-06-09T00:50:02 - `faa24824-7ca1-473e-8164-dd5a22466140.jsonl`
