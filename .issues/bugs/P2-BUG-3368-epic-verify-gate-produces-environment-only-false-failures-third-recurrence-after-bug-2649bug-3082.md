---
id: BUG-3368
type: BUG
title: "Epic verify gate produces environment-only false failures \u2014 third recurrence\
  \ after BUG-2649/BUG-3082"
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-08-31'
captured_at: '2026-08-31T21:18:18Z'
relates_to: [BUG-2649, BUG-3082]
---

# BUG-3368: Epic verify gate produces environment-only false failures — third recurrence after BUG-2649/BUG-3082

## Summary

During `ll-loop run sprint-refine-and-implement EPIC-1463` (run dir `.loops/runs/sprint-refine-and-implement-20260831T135628/`), the epic-worktree verify gate reported 6 test failures on commit d8e8b9ed1 (ENH-1718, Codex PreToolUse adapter parity — see verify-detail.txt, verify-returncode.txt, summary.json):

- test_recheck_set_folds_back_abandoned_residual (scripts/tests/test_builtin_loops.py)
- test_no_new_unverifiable_evidence (scripts/tests/test_verify_evidence.py)
- test_hint_fires_for_root_level_report (scripts/tests/test_check_private_refs_hook.py)
- test_policy_builder_renders_byte_identically_to_golden_fixture (scripts/tests/test_enh3035_artifact_template_kit.py)
- test_tsc_noemit_passes (scripts/tests/test_opencode_adapter.py)
- test_tsc_noemit_passes (scripts/tests/test_omp_adapter.py)

The tsc failures were `Cannot find type definition file for 'bun'`.

## Root Cause

Unknown — this is a false-failure report, not yet root-caused. Repro / evidence these are false failures, not real regressions:

- All 6 tests pass on clean main in ~5.5s when run directly (outside the verify-gate's worktree/subprocess environment).
- Commit d8e8b9ed1's diff (Codex adapter shell script, hooks.json entry, docs) is completely disjoint from all 6 failing tests' code paths — nothing in the commit touches builtin-loops recheck logic, verify-evidence gates, private-refs hints, the artifact template kit, or TypeScript/bun tooling.

This is the third instance of the epic-worktree verify gate producing environment-only false failures, after BUG-2649 (PYTHONPATH injection non-hermeticity, fixed by hermeticity regression tests + an LL_VERIFY_GATE skipif quarantine) and BUG-3082 (ambient LL_AUTOMATION leaking into the subprocess tree causing 48 phantom failures, fixed by scrubbing LL_AUTOMATION/LL_AUTOMATION_PROFILE in scripts/tests/conftest.py's env-scrub list). Neither prior fix covers this new set of 6 tests, so a third, distinct contamination vector is implicated — the bun-types tsc failures specifically suggest a PATH or node-module-resolution difference specific to the verify gate's subprocess/worktree environment, separate from the PYTHONPATH and LL_AUTOMATION vectors already fixed.

## Note for triage

This bug did NOT actually block ENH-1718's merge in this run. The run's `epic_merge_verdict` was `held_open`, but that traces to a separate defect in the epic-merge `all_done` completion gate (EPIC-1463 has 5 cancelled children, which permanently blocks the `all_done` check regardless of verify outcome — filed separately). The verify failure and the `held_open` verdict were coincidentally co-occurring, not causally linked, in this run. ENH-1718 was merged to main by hand (commit 6e158e703) after confirming the 6 failures were environment-only.

## Current Behavior

[If applicable - describe what currently happens]

## Expected Behavior

[What should happen instead]

## Motivation

[Why this issue matters - business value, user impact, technical debt cost]

## Proposed Solution

TBD - requires investigation

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

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: [YYYY-MM-DD] | Priority: [P0-P5]

## Steps to Reproduce

1. [Step 1]
2. [Step 2]
3. [Observe: description of the bug]

## Root Cause

- **File**: `path/to/file.py`
- **Anchor**: `in function buggy_func()`
- **Cause**: [Explanation of why bug happens]

## Error Messages

## Environment

## Frequency

## Location

- **File**: `path/to/file`
- **Line(s)**: [lines] (at scan commit: [COMMIT_HASH_SHORT])
- **Anchor**: `in function name()`
- **Code**:
```
# Relevant code snippet
```

## Reproduction Steps

## Proposed Fix


## Session Log
- `/ll:capture-issue` - 2026-08-31T21:19:00 - `8f60449e-8767-4de4-9ff3-4177cfb2cbee.jsonl`
