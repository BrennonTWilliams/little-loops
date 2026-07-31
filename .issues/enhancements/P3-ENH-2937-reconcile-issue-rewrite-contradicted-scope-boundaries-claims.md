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

Reconcile's rewrite scope in practice concentrates on `## Proposed Change` /
`## Proposed Solution` / implementation-plan sections. A `## Scope Boundaries` sentence
whose justification is directly refuted by content elsewhere in the same issue (wiring
findings, Codebase Research Findings) is left untouched and unflagged.

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

In `commands/reconcile-issue.md` (and `skills/ll-reconcile-issue/SKILL.md` if the logic
is duplicated there):

1. Add Scope Boundaries (and any section asserting "X is not needed because Y") to the
   enumerated rewrite-eligible directive sections.
2. Add an explicit contradiction check step: for each scope claim with a stated
   justification, verify the justification against Integration Map / wiring /
   Codebase Research Findings content in the same issue. On contradiction:
   - factual mismatch → rewrite the claim from the findings;
   - open scope call → rewrite as an imperative decision directive (ENH-2936's
     Pattern E shape) rather than silently keeping the stale claim.
3. Log each rewrite in the reconcile output report so the change is auditable.

## Scope Boundaries

- **In scope**: reconcile's rewrite-eligibility rules and contradiction check; prompt/
  instruction text changes; a fixture-based test if reconcile has one.
- **Out of scope**: making the scope decision itself (ENH-2936); changes to
  confidence-check scoring.

## Integration Map

### Files to Modify
- `commands/reconcile-issue.md`
- `skills/ll-reconcile-issue/SKILL.md` (check for duplicated section-scope logic)

### Tests
- TBD — check whether reconcile has skill/eval fixtures; if not, this is
  instruction-text-only (`testable` judgment at refine time)

### Documentation
- N/A

## Acceptance Criteria

- [ ] Reconcile's instructions enumerate Scope Boundaries as rewrite-eligible and include
      the claim-vs-findings contradiction check.
- [ ] On the ENH-2866 shape (scope claim justified by delegation, refuted by a direct
      call path recorded in the same issue), a reconcile pass rewrites or
      decision-directive-izes the claim instead of leaving it verbatim.
- [ ] Rewrites are listed in the reconcile output report.

## Session Log
- `/ll:capture-issue` - 2026-07-31T21:54:57Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0da828f8-33c5-4a86-bdb0-74648c03bab5.jsonl`
