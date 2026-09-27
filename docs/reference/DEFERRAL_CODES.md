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
| `decision_unresolved` | `prepare-issue.yaml` (`ll-issues prep apply`, when the preparation policy stops on a still-open decision after its decision re-entry is spent) and `refine-to-ready-issue.yaml`'s `record_decision_unresolved` state (ENH-3611 removed autodev's copy; ENH-3623 moved autodev's re-entry cap into `prepare-issue`) | The issue has `decision_needed: true` and no recorded decision. |
| `spike_inconclusive` | `refine-to-ready-issue.yaml`'s `record_spike_inconclusive` state (autodev's copy removed in ENH-3611; autodev ledgers the child's stop) | `/ll:spike` ran but could not reach a verdict (neither proven nor refuted). Fix the cause, run `/ll:spike <ID> --force`, and re-run. |
| `proposal_unsound` | `refine-to-ready-issue.yaml` `record_proposal_unsound` state | `/ll:verify-issues` found the selected Proposed Solution refuted and no eligible alternative remains (or the one revision per run was spent). Revise `## Proposed Solution`, then re-run. |
| `low_readiness` | `prepare-issue.yaml` (`ll-issues prep apply`), from the preparation policy's post-size-review recheck | Readiness score below threshold with no applicable pre-deferral remedy (BUG-2803: never written without at least one non-refine remedy attempt). Also written when `/ll:go-no-go` waived the outcome gate of an `oversized_atomic` issue but its readiness is still below threshold — the waiver covers only the outcome half (ENH-3623). |
| `oversized_atomic` | `prepare-issue.yaml` (`ll-issues prep apply`), from the preparation policy's oversized-atomic remediation step | `issue-size-review --auto` scored the issue Very Large (8-11) but decomposition was deliberately declined (strictly sequential / shared-infra children), and one-shot remediation still failed outcome risk (BUG-2734). The policy then runs `/ll:go-no-go --auto` at most once per run; a GO stamps `outcome_gate_waived: true` and reopens the issue for implementation, a NO-GO leaves it deferred with this code. |
| `readiness_stagnated` | `prepare-issue.yaml` (`ll-issues prep apply`), from the preparation policy's post-remedy recheck | ≥2 repair-class attempts ran this pass (refine/wire/size-review/spike/reconcile/refine-for-design) and readiness is no better than the dequeue-time snapshot — every remedy including reconcile was attempted (FEAT-2751). |
| `design_gate_failed` | `prepare-issue.yaml` (`ll-issues prep apply`), from the preparation policy's post-size-review recheck or its post-atomic-remediation regate | The deterministic `## Program Design` gate failed even after the design remedy (`/ll:refine-issue --auto --gap-analysis`, BUG-3002), which runs at most once per run — retargeted from `/ll:reconcile-issue`, whose contract excludes that section. |
| `blocked_by_gate` | `autodev.yaml`'s `defer_gated` state | The issue is explicitly gated by policy (an unsatisfied structured `gate` field, or — when the field is absent — prose gate language and/or a placeholder Acceptance Criteria section; ENH-3575) — caught by the pre-dequeue `check_gate_at_dequeue` state before `prepare-issue` runs, since no refine/wire/confidence-check cycle can unblock an external evidence gate (ENH-3148). Distinct from `gate_blocked`, which is a different, post-implementation learning-gate condition. |

**Not a deferral — scores absent (BUG-3588):** when a post-repair `/ll:confidence-check` run by `prepare-issue` writes no scores (after one retry), the issue is *not* deferred. `prepare-issue` ends `RETRYABLE_ERROR:infra` and autodev ledgers it as `refine_failed_infra` (ENH-3623; the old `autodev-scores-absent.txt` record is gone), leaving the issue in place to retry on a later run — an infra failure, never a `low_readiness` quality verdict. Distinct from `autodev-gate-infra.txt` (the learning-gate record).

## Related

- `ll-issues deferred-triage` — visibility into deferred issues by reason code, without re-evaluating each one every run.
- The built-in `autodev`, `prepare-issue`, `refine-to-ready-issue` and `rn-implement` loops (`ll-loop show <name>`) and `little_loops.preparation_policy` (`ll-issues prep apply`) — emission sites.
