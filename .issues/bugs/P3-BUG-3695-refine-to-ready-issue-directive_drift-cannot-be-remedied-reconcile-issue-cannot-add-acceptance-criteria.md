---
id: BUG-3695
type: BUG
title: 'refine-to-ready-issue DIRECTIVE_DRIFT cannot be remedied: reconcile-issue
  cannot add Acceptance Criteria'
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-10-02'
captured_at: '2026-10-02T17:46:29Z'
parent: EPIC-3694
---

# BUG-3695: refine-to-ready-issue DIRECTIVE_DRIFT cannot be remedied: reconcile-issue cannot add Acceptance Criteria

## Summary

`refine-to-ready-issue` routes a `DIRECTIVE_DRIFT` verify verdict to `reconcile_issue`, but `/ll:reconcile-issue` is forbidden from adding Acceptance Criteria, so the one remedy the verdict promises cannot clear the finding. The loop then exhausts its budgets and ends `GATE_UNMET`, even though the fix is small and fully specified by the verify finding.

## Current Behavior

Observed in run `refine-to-ready-issue-20261002T111524` on ENH-3678 (history run `2026-10-02T171524-refine-to-ready-issue`, 33 iterations, 24m39s, `failed`):

1. `verify_issue` returned `DIRECTIVE_DRIFT` on iterations 14, 20 and 29. Every claim about current code held; the only finding was a check B6 AC-coverage gap — the Integration Map lists a `ll-doctor` "rebuild pending" surface (`cli/doctor.py`) with no Acceptance Criterion. Later passes added further uncovered points: notice suppression on the automation-pruning path, the replay-duration measurement, and the `session_store/__init__.py` re-export.
2. `commands/verify-issues.md:263` defines `DIRECTIVE_DRIFT` as "remedied by `reconcile-issue`", and the loop routes `VERIFY:DIRECTIVE_DRIFT` -> `check_reconcile_limit` -> `reconcile_issue` (`refine-to-ready-issue.yaml:589`).
3. `reconcile_issue` ran once (iteration 17) and reported `RECONCILED` with "Acceptance Criteria: unchanged". Its CONCERNS said adding the AC "would be a new requirement rather than a correction". That follows `commands/reconcile-issue.md:120`: "do not invent new requirements" — it only rewrites directive text contradicted by the issue's own findings.
4. `check_reconcile_limit` (counter increments on every entry, `target: 2`) allows one reconcile per run. The second `DIRECTIVE_DRIFT` fell to `check_gate_refine_limit` -> `refine_followup`, which is research-only and additive (`commands/refine-issue.md` §5c) and cannot add ACs; it appended more findings instead.
5. The third `DIRECTIVE_DRIFT` found both budgets exhausted -> `record_gate_unmet` -> `failed`.

This is a contract mismatch: a coverage gap (missing AC) is not a contradiction, so neither remedy state can fix it. Sibling of BUG-3574 (`PROPOSAL_UNSOUND` routed to reconcile, which cannot edit Proposed Solution) and ENH-3690 (`NON_VALID` citation-only findings have no repair route).

## Expected Behavior

A `DIRECTIVE_DRIFT` verdict whose finding is "Integration Map entry has no Acceptance Criterion" is repaired in-loop by adding the missing AC(s), after which `verify_issue` returns `VALID`. Budget exhaustion is reached only when the repair genuinely cannot converge.

## Motivation

[Why this issue matters - business value, user impact, technical debt cost]

## Proposed Solution

- **Option A (smallest):** add a narrow carve-out to `commands/reconcile-issue.md`. When `verify_verdict: DIRECTIVE_DRIFT`, reconcile may add ACs that map one-to-one to Integration Map entries lacking an AC, traceable to `verify_evidence` / the Integration Map. All other "no new requirements" rules stay intact.
- **Option B:** add a dedicated `add_missing_acs` repair state to `refine-to-ready-issue.yaml` for coverage-gap drift, with its own per-run budget counter (convention: counter file under `${context.run_dir}`, seeded in `resolve_issue`, `output_numeric lt 2`, exhaustion to `record_gate_unmet`, plus the `max_steps` comment-block entry).

Either option must update the `DIRECTIVE_DRIFT` wording in `commands/verify-issues.md` and the dispatch tests (`TestRefineToReadyDispatch` route table in `scripts/tests/test_builtin_loops.py`, reconcile-issue tests). Consider whether `check_reconcile_limit` should count only actual reconcile attempts rather than every entry.

## Integration Map

### Files to Modify
- `commands/reconcile-issue.md` - scope carve-out (Option A)
- `commands/verify-issues.md` - `DIRECTIVE_DRIFT` verdict table wording (~line 263) and B6 verdict text
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` - route at ~589, `check_reconcile_limit`, `reconcile_issue` (Option B adds a state)

### Tests
- `scripts/tests/test_builtin_loops.py` - `TestRefineToReadyDispatch` route table
- `scripts/tests/test_enh3250_verify_issues_proposal_vs_code.py` and reconcile-issue tests

## Implementation Steps

1. [Major phase 1]
2. [Major phase 2]
3. [Verification approach]

## Impact

- **Priority**: P3 - blocks automated refinement of any issue whose Integration Map has uncovered points; a manual AC edit is the workaround
- **Effort**: Small (Option A) to Medium (Option B)
- **Risk**: Low - scoped to one verdict path

## Acceptance Criteria

- [ ] A `DIRECTIVE_DRIFT` finding consisting only of Integration Map entries with no Acceptance Criterion is cleared by one in-loop repair pass, and the next `verify_issue` returns `VALID`
- [ ] `reconcile-issue` still refuses to invent requirements for any case outside the carve-out
- [ ] `commands/verify-issues.md` verdict table names the actual remedy for `DIRECTIVE_DRIFT`
- [ ] Route-table and reconcile tests updated and `python -m pytest scripts/tests/` exits 0
- [ ] Replaying ENH-3678's three-AC gap no longer ends in `GATE_UNMET`

## Secondary Observations

- In the same run, `refine_followup`'s evidence delta check was incomplete because its scratch snapshot in `.loops/tmp/scratch/` vanished mid-state (possible scratch-cleanup race during a long state).
- `verify_issue` on iteration 29 spent turns on a failed glob for the issue file before recovering.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-10-02 | Priority: P3


## Session Log
- `/ll:capture-issue` - 2026-10-02T17:46:36 - `f95760a1-28e5-4de5-bec7-aaf05cf7e5d8.jsonl`
