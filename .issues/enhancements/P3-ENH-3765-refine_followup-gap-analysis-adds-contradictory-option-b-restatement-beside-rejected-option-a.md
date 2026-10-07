---
id: ENH-3765
type: ENH
title: refine_followup gap-analysis adds contradictory Option B restatement beside
  rejected Option A
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-10-07'
captured_at: '2026-10-07T00:49:19Z'
relates_to:
- BUG-3763
- BUG-3764
---

# ENH-3765: refine_followup gap-analysis adds contradictory Option B restatement beside rejected Option A

## Summary

On BUG-3761, `refine_followup` (`/ll:refine-issue --auto --gap-analysis`, ~6 min) was routed a residual `unapplied_decision` finding. Gap-analysis is additive-only, so it could not remove the rejected Option A text. Instead it folded in an Option B restatement inside Program Design plus a note that the older bullets describe the rejected option, and restated Impact Effort/Risk the same way. The issue now holds both designs in the same section; its own report said the gate still failed and that a rewrite was needed.

The loop run: `.loops/.history/2026-10-07T000313-refine-to-ready-issue`.

An implementer or later automated pass reading that section has to guess which design is live, and the next `format-check` still fails on the old identifiers.

## Current Behavior

`/ll:refine-issue --auto --gap-analysis` is additive-only by contract. On the observed run it appended an Option B restatement beside rejected Option A text in Program Design and Impact. It also added useful AC/research findings, so the pass was not a literal no-op, but it could not discharge the rewrite obligation. `refine_followup` has an unconditional next state; its prose output does not control routing. The shared loop retry counter is incremented before the command runs. That counter is separate from the lifetime `max_refine_count` exemption provided by the gap-analysis Session Log discriminator.

## Expected Behavior

When the remaining finding is not fixable additively (`unapplied_decision` on a rejected option), `refine-issue --gap-analysis` should detect that and either decline to add contradictory text, or hand off with a clear marker so the loop can route to a rewrite rung instead of spending its one gate-refine budget.

## Motivation

This enhancement would:
- Stop the issue body from holding two live designs in one section, which forces an implementer or later automated pass to guess which is current.
- Save the ~6 min `refine_followup` pass and its gate-refine budget on a case it cannot fix (BUG-3761 run `.loops/.history/2026-10-07T000313-refine-to-ready-issue`).
- Give the loop a detectable marker so it can route to a rewrite rung (see BUG-3763) instead of failing the gate after a no-op.

## Proposed Solution

In the refine-issue gap-analysis path, check `ll-issues format-check` for `unapplied_decision` before writing; if present, emit a refuse-and-report result (no body edit) so `check_gate_refine_limit` budget is not burned on a no-op. Pairs with the Program Design rewrite rung bug.

## Integration Map

### Files to Modify
- `commands/refine-issue.md` - Step 5c Gap-Analysis Mode: add the `unapplied_decision` pre-write check and the refuse-and-report output (section "6. Gap-Analysis Output")
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` - `refine_followup` state: route on the refusal marker (coordinate with BUG-3763)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/issue_parser.py` - defines `FormatGaps.unapplied_decision` (and `unapplied_decision_detail`) that the check reads
- `scripts/little_loops/cli/issues/format_check.py` - `cmd_format_check` prints the `unapplied_decision` finding the pre-write check consumes
- `scripts/little_loops/cli/issues/check_verify_verdict.py` - sibling checker whose output routes the loop; reference for loop-detectable markers

### Similar Patterns
- Step 3.9 / covered-triage no-op report in `commands/refine-issue.md` - an existing "report the no-op explicitly, still append the Session Log" path to model the refusal on

### Tests
- `scripts/tests/test_refine_issue_command.py` - add a doc-contract test that Step 5c documents the refusal and its marker (same style as the `--gap-analysis` flag tests)
- `scripts/tests/test_ll_issues_format_check.py` - only if the marker needs a new machine-readable field

### Documentation
- N/A - the contract lives in `commands/refine-issue.md` itself

### Configuration
- N/A

## Implementation Steps

1. Pick the marker string the loop can detect and document it in Step 5c and "6. Gap-Analysis Output" of `commands/refine-issue.md`.
2. Add the pre-write `ll-issues format-check` `unapplied_decision` check to Step 5c; on a hit, make no body edits, report the rewrite requirement with the marker, and still append the Session Log entry (Step 6.5).
3. Update `refine_followup` routing in `refine-to-ready-issue.yaml` to consume the marker (or leave the hand-off to BUG-3763's rewrite rung).
4. Add the doc-contract test, then run `python -m pytest scripts/tests/test_refine_issue_command.py scripts/tests/test_ll_issues_format_check.py`.

## Scope Boundaries

- **In scope**: Detect an `unapplied_decision` residual in the gap-analysis path, decline to edit, and emit a loop-detectable rewrite-required marker.
- **Out of scope**: The Program Design rewrite rung itself (BUG-3763); relaxing gap-analysis's additive-only contract; changing `max_refine_count` or `check_gate_refine_limit` accounting; repairing issues already holding both designs (BUG-3761).

## Program Design

### Types

- `unapplied_decision: list[str]` — existing `FormatGaps` field in `little_loops.issue_parser` that the check reads; no new types

### Signatures

- `check_format_gaps(issue_path: Path) -> FormatGaps` — existing and unchanged; the refusal is a documented step in `commands/refine-issue.md`, not new Python
- `emit_rewrite_required(finding: str) -> str` — documented output-contract step that prints the marker line `GAP_ANALYSIS:REWRITE_REQUIRED unapplied_decision` in the Step 6 Gap-Analysis Output

### Call Path

`refine_followup` -> `/ll:refine-issue --auto --gap-analysis` -> `check_format_gaps` -> `cmd_format_check`

## Impact

- **Severity**: Low-medium; wasted loop time and a less coherent issue file.
- **Affected**: `commands/refine-issue.md`, `scripts/little_loops/loops/refine-to-ready-issue.yaml` (`refine_followup`).

## Acceptance Criteria

- Gap-analysis on an issue with an unapplied-decision residual makes no Program Design/Impact edits that coexist with the rejected-option text.
- Its output states the rewrite requirement in a form the loop can detect.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-10-07 | Priority: P3


## Session Log
- `/ll:format-issue` - 2026-10-07T00:51:36 - `9aaef30f-0230-47c7-ac7f-df1e0deadca8.jsonl`
- `/ll:capture-issue` - 2026-10-07T00:49:26 - `a47df9fa-6eb0-42c9-bccf-a5644c5b0d50.jsonl`
