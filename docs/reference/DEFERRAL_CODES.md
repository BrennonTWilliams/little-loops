# Deferral Reason Codes

When an issue transitions to `status: deferred` via `ll-issues set-status <ID>
deferred --by automation --reason <CODE>`, the `deferred_reason` frontmatter
field is stamped with one of the machine enum codes below (as opposed to
`--by human`, where `deferred_reason` is free-text prose). This is the single
cross-code index; each code's canonical definition still lives as inline
comments at its emission site, linked below.

See `.claude/CLAUDE.md` § Issue File Format for the deferral-discriminator
mechanism itself (`deferred_by`/`deferred_reason`/`deferred_date`, and why
`deferred` is non-terminal for dependency purposes).

## Codes

| Code | Emitted by | Meaning |
|---|---|---|
| `blocked_by_unmet` | `rn-implement.yaml`'s `mark_deferred` state | An unmet `blocked_by` dependency — recoverable once the blocker resolves. |
| `remediation_stalled` | `rn-implement.yaml`'s `mark_deferred` state | Remediation stalled and decomposition was declined — needs human attention. |
| `gate_blocked` | `autodev.yaml`'s `mark_gate_blocked` state | A required gate (e.g. decision, learning test) is unresolved; distinct from a readiness-score deferral. |
| `decision_unresolved` | `autodev.yaml`'s `record_decision_unresolved` state | The issue has `decision_needed: true` and no recorded decision. |
| `low_readiness` | `autodev.yaml`'s `recheck_after_size_review` low-readiness skip | Readiness score below threshold with no applicable pre-deferral remedy (BUG-2803: never written without at least one non-refine remedy attempt). |
| `oversized_atomic` | `autodev.yaml`'s `remediate_oversized_atomic` fallback | `issue-size-review --auto` scored the issue Very Large (8-11) but decomposition was deliberately declined (strictly sequential / shared-infra children), and one-shot remediation still failed outcome risk (BUG-2734). |
| `readiness_stagnated` | `autodev.yaml`'s post-remedy revisit (`recheck_after_size_review`) | ≥2 repair-class attempts ran this cycle (refine/wire/size-review/spike/reconcile/refine-for-design) and readiness is no better than the dequeue-time snapshot — every remedy including reconcile was attempted (FEAT-2751). |
| `design_gate_failed` | `autodev.yaml`'s `regate_after_atomic_remediation` / `recheck_after_size_review` | The deterministic `## Program Design` gate failed even after the one-shot `refine_for_design` remedy (`/ll:refine-issue --auto --gap-analysis`, BUG-3002) — retargeted from `reconcile_current`, whose contract excludes that section. |

## Related

- `ll-issues deferred-triage` — visibility into deferred issues by reason code, without re-evaluating each one every run.
- `scripts/little_loops/loops/autodev.yaml`, `scripts/little_loops/loops/rn-implement.yaml` — emission sites.
