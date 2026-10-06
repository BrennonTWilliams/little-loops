---
id: BUG-3753
type: BUG
title: verify-issues --from-evidence re-introduces the stale claim it corrects via
  a verbatim Verification Notes quote
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-10-06'
captured_at: '2026-10-06T01:01:37Z'
---

# BUG-3753: verify-issues --from-evidence re-introduces the stale claim it corrects via a verbatim Verification Notes quote

## Summary

`/ll:verify-issues --from-evidence` (the `correct_claims` state of `refine-to-ready-issue`) repairs a stale claim in place, then writes a `## Verification Notes` entry that quotes the stale token verbatim. `ll-issues format-check` scans that note, so the follow-up `--check` flags the same finding again. The one-attempt claim-correction budget is already spent, so the loop routes to `record_gate_unmet` and fails.

## Current Behavior

Observed in run `refine-to-ready-issue-20261005T180418` on ENH-3742 (23 iterations, failed):

1. First `--check` returned `CLAIMS_OUTDATED`: a slash-joined shorthand for several file names in a Tests bullet was read as a nonexistent path (`stale_file_ref`).
2. `correct_claims` rewrote the bullet correctly, then wrote a Verification Notes entry that quoted the original slash-joined token verbatim.
3. The second `--check` flagged that note as the same `stale_file_ref`; its `verify_evidence` named the Verification Notes quote.
4. `check_claim_correction_budget` (counter `lt 2`, one attempt per run) was exhausted, so the run ended `failed` with `gate_unmet`.

## Expected Behavior

A correction pass never leaves behind a note that re-triggers the finding it fixed: notes paraphrase stale citations, and the pass confirms `ll-issues format-check <ID>` is clean of findings it introduced before finishing.

## Motivation

[Why this issue matters - business value, user impact, technical debt cost]

## Proposed Solution

Already applied in the working tree (uncommitted):

- `commands/verify-issues.md`: new paragraph "Verification Notes must not re-introduce the finding" before §4.1 (paraphrase, never quote; post-write `format-check`, reword and re-run until clean, also under `--from-evidence`), plus a clarifying comment at the `FROM_EVIDENCE` flag parse.
- Host mirrors regenerated with `ll-adapt --host <gemini|kimi-code|qwen> --apply`.
- ENH-3742's offending note reworded by hand and its stale verdict cleared.

Optional follow-ups:

- Loop- or CLI-level guard so this cannot depend on model compliance: a deterministic `format-check` state after `correct_claims`, or have `format-check` ignore or limit citation tokens inside `## Verification Notes`.
- Regression test asserting the verify-issues command text contains the paraphrase and post-write-check rule.

## Integration Map

### Files to Modify
- TBD - requires codebase analysis

### Dependent Files (Callers/Importers)
- TBD - use grep to find references

### Similar Patterns
- TBD - search for consistency

### Tests
- TBD - identify test files to update

### Documentation
- TBD - docs that need updates

### Configuration
- N/A or list config files

## Implementation Steps

1. [Major phase 1]
2. [Major phase 2]
3. [Verification approach]

## Impact

- **Priority**: [P0-P5] - [Justification]
- **Effort**: [Small/Medium/Large] - [Justification]
- **Risk**: [Low/Medium/High] - [Justification]
- **Breaking Change**: [Yes/No]

## Root Cause

- `commands/verify-issues.md` §4 / §4.1 instruct the pass to record what was wrong, with no rule against quoting path, symbol or line citations verbatim.
- Check B8 (format-check citations) is skipped under `--from-evidence`, so the pass never re-runs `ll-issues format-check` after writing its own note.
- `normalize_structure` runs `format-check --fix`, but `stale_file_ref` is not auto-fixable, so nothing repairs the note afterwards.
- `check_claim_correction_budget` allows exactly one correction per run, so one self-inflicted failure is terminal.

## Acceptance Criteria

- [ ] After `correct_claims`, a Verification Notes entry never contains a path or symbol citation that `ll-issues format-check` flags.
- [ ] A regression test covers the rule (command text or a deterministic guard).
- [ ] The ENH-3742 reproduction passes `refine-to-ready-issue` past the claim-correction gate.

## Related

BUG-3637 (introduced `correct_claims`), ENH-3690, BUG-3695.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-10-06 | Priority: P3


## Session Log
- `/ll:capture-issue` - 2026-10-06T01:01:57 - `89b97fde-6836-4bf2-b412-cd83564e6b38.jsonl`
