# ENH-2937: reconcile-issue: rewrite Scope Boundaries claims contradicted by its own findings

---
id: ENH-2937
type: ENH
priority: P3
status: open
captured_at: "2026-07-31T21:54:57Z"
discovered_date: 2026-07-31
discovered_by: capture-issue
relates_to: [ENH-2866, ENH-2936, ENH-2689]
---

## Summary

`/ll:reconcile-issue` (rewrite directive sections from own findings) can leave a
factually refuted `## Scope Boundaries` claim intact while updating other directive
sections in the same pass. In ENH-2866, Scope Boundaries claimed "no separate ll-sprint
stamp is needed" because `ll-sprint` delegates to `ParallelOrchestrator` — but the wiring
pass had already found that `_run_issue_with_wall_clock_timeout()` in `cli/sprint/run.py`
calls `process_issue_inplace()` directly and sequentially, a distinct unstamped code path
contradicting the claim verbatim. A reconcile pass (2026-07-31T03:03:58) touched
`## Proposed Change` (added ll-auto as a stamp site) yet never rewrote or flagged the
contradicted Scope Boundaries sentence. The contradiction then survived three
confidence-check passes, holding the Ambiguity subscore down.

## Motivation

A contradiction between a directive section's claim and the issue's own research findings
is exactly the staleness class reconcile exists to fix — and it is not a decision, so
`/ll:decide-issue` correctly won't touch it (see ENH-2936 for the decision-shaped
sibling gap). If reconcile skips it, no automation remedy remains: the contradiction
recurs in every confidence-check as capped Ambiguity, contributing to dishonest
`readiness_stagnated` deferrals. This was one of the two concrete blockers behind
ENH-2866's 56/100 outcome confidence.

## Current Behavior

Reconcile's rewrite scope is not an emergent habit — it is a **binding contract** in
`commands/reconcile-issue.md` ("Contract (read this first — it is binding)"): rewrite
ONLY `## Implementation Steps`, `## Acceptance Criteria`, and `### Files to Modify`;
everything else — explicitly including `## Scope Boundaries` — is "Preserve untouched —
never edit, reorder, or delete." So a `## Scope Boundaries` sentence whose justification
is directly refuted by content elsewhere in the same issue (wiring findings, Codebase
Research Findings) is left standing by design. This enhancement is therefore a
**contract amendment**, in tension with the skill's core promise ("without bulldozing
human prose") — it must be scoped tightly, not as general rewrite-eligibility.

## Expected Behavior

During a reconcile pass, claims in `## Scope Boundaries` (and other directive sections,
e.g. exclusion rationales) are checked against the issue's own recorded findings. When a
finding directly contradicts a claim's stated justification, reconcile either rewrites
the claim to match the evidence (e.g. "ll-sprint's `_run_issue_with_wall_clock_timeout()`
path calls `process_issue_inplace()` directly and needs its own stamp") or — if the
resolution requires a scope call rather than a factual correction — rewrites it into an
explicit decision-directive shape ("stamp it or exempt it — decide before
implementation") so the ENH-2936 decide path can pick it up. It must not leave the
refuted sentence standing verbatim.

## Proposed Solution

In `commands/reconcile-issue.md`:

1. Amend the binding contract: `## Scope Boundaries` (and any section asserting "X is
   not needed because Y") becomes **conditionally** rewrite-eligible — ONLY for a claim
   whose stated justification is directly contradicted by a recorded finding in the
   same issue. It is NOT added to the general rewrite list; unrefuted scope prose stays
   under "Preserve untouched."
2. Add an explicit contradiction check step: for each scope claim with a stated
   justification, verify the justification against Integration Map / wiring /
   Codebase Research Findings content in the same issue. On contradiction:
   - factual mismatch → rewrite the claim from the findings;
   - open scope call → rewrite as an imperative decision directive (ENH-2936's
     Pattern E shape) rather than silently keeping the stale claim, AND set
     `decision_needed: true` in frontmatter — without the flag, the decide pipeline
     never picks the directive up.
3. Carve out the contract line "Every rewritten claim must trace to an existing
   finding" for branch 2b: the decision-directive text is new imperative prose, not
   finding-traceable; the contract must explicitly permit it for this branch only.
4. Extend `--check` mode's staleness detection to include the contradicted-scope-claim
   class — autodev's plateau gate reaches reconcile via staleness detection, so if the
   contradiction check only runs in rewrite mode the gate never routes this shape to
   reconcile at all.
5. Log each rewrite in the reconcile output report (existing report template) so the
   change is auditable.

**Sequencing**: implement after ENH-2936 (or at minimum after Pattern E's
imperative-marker phrasing is finalized), since branch 2b hardcodes examples of that
shape. Soft ordering only — the factual-rewrite branch is independent, so no hard
`blocked_by` edge (which would over-block this issue in autodev).

## Scope Boundaries

- **In scope**: reconcile's rewrite-eligibility rules and contradiction check; prompt/
  instruction text changes; a fixture-based test if reconcile has one.
- **Out of scope**: making the scope decision itself (ENH-2936); changes to
  confidence-check scoring.

## Integration Map

### Files to Modify
- `commands/reconcile-issue.md` (contract amendment + contradiction check + `--check`
  mode + report template)
- `skills/ll-reconcile-issue/SKILL.md` — no duplicated logic (it is a 22-line Codex
  bridge), but its `description` frontmatter enumerates the three rewrite sections and
  must be updated to mention the conditional Scope Boundaries eligibility

### Tests
- TBD — check whether reconcile has skill/eval fixtures; if not, this is
  instruction-text-only (`testable` judgment at refine time)

### Documentation
- N/A

## Acceptance Criteria

- [ ] Reconcile's contract marks Scope Boundaries as conditionally rewrite-eligible
      (contradicted-claim-only) and includes the claim-vs-findings contradiction check;
      unrefuted scope prose remains under "Preserve untouched."
- [ ] On the ENH-2866 shape (scope claim justified by delegation, refuted by a direct
      call path recorded in the same issue), a reconcile pass rewrites or
      decision-directive-izes the claim instead of leaving it verbatim; the
      decision-directive branch also sets `decision_needed: true`.
- [ ] `--check` mode reports a contradicted scope claim as a stale section (plateau
      gate can route this shape to reconcile).
- [ ] Rewrites are listed in the reconcile output report.
- [ ] `skills/ll-reconcile-issue/SKILL.md`'s `description` reflects the amended scope.

## Session Log
- `/ll:capture-issue` - 2026-07-31T21:54:57Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0da828f8-33c5-4a86-bdb0-74648c03bab5.jsonl`
