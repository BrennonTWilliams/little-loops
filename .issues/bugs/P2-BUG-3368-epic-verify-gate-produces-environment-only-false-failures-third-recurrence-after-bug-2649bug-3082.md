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

## Note for triage

This bug did NOT actually block ENH-1718's merge in this run. The run's `epic_merge_verdict` was `held_open`, but that traces to a separate defect in the epic-merge `all_done` completion gate (EPIC-1463 has 5 cancelled children, which permanently blocks the `all_done` check regardless of verify outcome — filed separately). The verify failure and the `held_open` verdict were coincidentally co-occurring, not causally linked, in this run. ENH-1718 was merged to main by hand (commit 6e158e703) after confirming the 6 failures were environment-only.

## Current Behavior

The epic-worktree verify gate runs the test suite inside a subprocess/worktree environment as part of epic-merge completion. That environment sometimes diverges from a direct clean-checkout test run, producing test failures that do not reflect real regressions in the commit under test. This has now happened three times (BUG-2649, BUG-3082, this bug), each from a different contamination vector.

## Expected Behavior

The verify gate's subprocess/worktree environment should reproduce the same test results as running the same tests directly on the same commit outside that environment. Environment-only failures should not block epic merges or require manual hand-merging.

## Motivation

This is the third recurrence of the same failure class. Each occurrence silently blocks automated epic merges, requires a human to manually confirm the failures are environment-only and hand-merge (as happened here with commit 6e158e703), and erodes trust in the verify gate as an automated safety check.

## Proposed Solution

TBD — root cause is unidentified (see Root Cause below). Once found, the fix should follow the established pattern from BUG-2649 (hermeticity regression test + scrubbing the offending environment difference) and BUG-3082 (scrub the leaking variable in `scripts/tests/conftest.py`'s env-scrub list): diagnose the concrete environment divergence first (see Implementation Steps), then scrub/normalize it at the source and add a regression test.

## Integration Map

### Files to Modify
- TBD — depends on the diagnosed contamination vector; likely candidates are `scripts/tests/conftest.py` (env-scrub list, per the BUG-3082 pattern) and the epic-worktree verify gate's subprocess invocation (`merge_epic_branch` state, `scripts/little_loops/loops/auto-refine-and-implement.yaml`)

### Dependent Files (Callers/Importers)
- The 6 currently-failing test files: `scripts/tests/test_builtin_loops.py`, `scripts/tests/test_verify_evidence.py`, `scripts/tests/test_check_private_refs_hook.py`, `scripts/tests/test_enh3035_artifact_template_kit.py`, `scripts/tests/test_opencode_adapter.py`, `scripts/tests/test_omp_adapter.py`

### Similar Patterns
- BUG-2649's PYTHONPATH hermeticity regression tests and BUG-3082's LL_AUTOMATION env-scrub fix are the two prior fixes for this same failure class

### Tests
- TBD — a new hermeticity regression test for the identified contamination vector, mirroring the BUG-2649/BUG-3082 tests

### Documentation
- N/A

### Configuration
- N/A

## Program Design

### Types

- (none yet — root cause unidentified; see Implementation Steps)

### Signatures

- `dump_verify_gate_env() -> dict[str, str]` — diagnostic helper added temporarily to the verify-gate subprocess invocation to capture `PATH`, node/bun toolchain resolution, `PYTHONPATH`, and other env vars for comparison against a direct clean-checkout run

### Call Path

`merge_epic_branch` (epic-worktree verify gate, `scripts/little_loops/loops/auto-refine-and-implement.yaml`) -> `dump_verify_gate_env()` -> diff against direct `python -m pytest scripts/tests/` on a clean checkout of the same commit

## Implementation Steps

1. Capture and diff the verify gate's subprocess/worktree environment (`PATH`, node/bun module resolution, `PYTHONPATH`, other env vars) against a direct clean-checkout test run to isolate the contamination vector — the bun-types tsc failures suggest a PATH/node-module-resolution difference distinct from BUG-2649 (PYTHONPATH) and BUG-3082 (LL_AUTOMATION).
2. Root-cause the specific mechanism and fix it at the source (scrub/normalize the diverging env value), following the BUG-2649/BUG-3082 pattern.
3. Add a hermeticity regression test asserting this contamination vector stays fixed, mirroring the existing BUG-2649/BUG-3082 tests.

## Impact

- **Priority**: P2 - third recurrence of a failure class that silently blocks automated epic merges and requires manual investigation/hand-merge every time it happens.
- **Effort**: Medium - investigation-heavy since the root cause is unidentified; the fix itself is likely small once found, per the BUG-2649/BUG-3082 precedent.
- **Risk**: Low - the fix targets test/gate infrastructure, not production code paths.
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-08-31 | Priority: P2

## Steps to Reproduce

1. Run `ll-loop run sprint-refine-and-implement EPIC-1463` (or any epic run whose verify gate covers commit d8e8b9ed1 / ENH-1718).
2. Observe the epic-worktree verify gate report the 6 test failures listed in Summary (see `verify-detail.txt`, `verify-returncode.txt`, `summary.json` under the run's `.loops/runs/sprint-refine-and-implement-20260831T135628/` directory).
3. Run the same 6 tests directly on a clean checkout of the same commit (e.g. `python -m pytest scripts/tests/`) and observe they pass in ~5.5s — confirming the failures are environment-only, not real regressions.

## Root Cause

Unknown — this is a false-failure report, not yet root-caused.

- **File**: Unknown — see Implementation Steps for the diagnostic plan
- **Anchor**: N/A (root cause not yet identified)
- **Cause**: All 6 tests pass on clean main in ~5.5s when run directly, outside the verify gate's worktree/subprocess environment. Commit d8e8b9ed1's diff (Codex adapter shell script, hooks.json entry, docs) is completely disjoint from all 6 failing tests' code paths. This is the third instance of the epic-worktree verify gate producing environment-only false failures, after BUG-2649 (PYTHONPATH injection non-hermeticity) and BUG-3082 (ambient LL_AUTOMATION leaking into the subprocess tree). Neither prior fix covers this new set of 6 tests, so a third, distinct contamination vector is implicated — the bun-types tsc failures specifically suggest a PATH or node-module-resolution difference specific to the verify gate's subprocess/worktree environment.

## Error Messages

The tsc failures were `Cannot find type definition file for 'bun'`.

## Environment

## Frequency

## Session Log
- `/ll:format-issue` - 2026-08-31T21:28:22 - `24eb8111-3a52-4364-98e0-699548ae82fc.jsonl`
- `/ll:capture-issue` - 2026-08-31T21:19:00 - `8f60449e-8767-4de4-9ff3-4177cfb2cbee.jsonl`
