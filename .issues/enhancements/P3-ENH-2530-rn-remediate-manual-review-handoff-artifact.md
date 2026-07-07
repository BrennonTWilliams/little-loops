---
id: ENH-2530
type: ENH
priority: P3
status: open
captured_at: '2026-07-07T21:00:00Z'
discovered_date: '2026-07-07'
discovered_by: audit-loop-run
relates_to:
- ENH-2533
decision_needed: false
labels:
- loops
- observability
---

# ENH-2530: rn-remediate — manual_review_handoff_<id>.md with decision_context

## Summary

When `emit_needs_manual_review` in
`scripts/little_loops/loops/rn-remediate.yaml` parks an issue, write a
per-issue handoff markdown that states the specific reason and recommended
next action, pulling `decision_context` from issue frontmatter when
`decision_needed: true` is the proximate cause.

## Source

Audit of an rn-implement run in a downstream project
(`AUDIT-rn-implement-2026-07-07T201030.md`, proposals 2 and 3). Two parked
issues surfaced only "requires human decision before automation can proceed" —
too vague to act on. The operator had to re-read `events.jsonl` and the issue
files to learn that one needed TTL options enumerated and the other a refactor
scope decision.

## Current Behavior

`emit_needs_manual_review` writes a one-line token to
`subloop_outcome_<ID>.txt` (`MANUAL_REVIEW_NEEDED` or
`MANUAL_REVIEW_RECOMMENDED`, distinguished per ENH-2443) and the parent appends
one line to `blocked.txt`. Nothing captures *which* decision is needed, the
score gap, or the remediation next step.

## Expected Behavior

`emit_needs_manual_review` additionally writes
`${context.run_dir}/manual_review_handoff_<ID>.md` containing:

- issue ID and title
- specific reason: outcome vs threshold (e.g. "outcome_confidence=70,
  threshold=75"), convergence delta and remediation pass count when available
- `decision_context` frontmatter verbatim when `decision_needed: true`
  (fallback to the generic sentence only when the field is absent)
- recommended next action: `/ll:refine-issue <ID>` for options-missing,
  `/ll:explore-api <target>` for learning gates
- captured pre/post scores

## Proposed Solution

- Extend the `emit_needs_manual_review` shell action with an inline python3
  heredoc that reads the issue frontmatter (mirror check_blocked_by's
  yaml-with-regex-fallback parser) plus `pre_scores_<ID>.json` /
  `convergence_<ID>.json` sidecars and renders the handoff file.
- Keep the existing token write unchanged (parent routing depends on it).
- Per MR-3, the handoff lives under `${context.run_dir}/` — already the
  convention here.
- If refine-issue does not yet reliably populate `decision_context`, note the
  fallback path in the handoff rather than blocking on it.

## Impact

- **Severity**: Medium (turns post-hoc audits into one-click handoffs)
- **Effort**: Small–Medium
- **Risk**: Low (additive artifact; no routing changes)
