---
id: BUG-3566
type: BUG
title: Autodev pre-deferral remedy dispatcher binds env vars to ll-issues instead
  of python3
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-24'
captured_at: '2026-09-24T19:33:11Z'
parent: EPIC-3565
---

# BUG-3566: Autodev pre-deferral remedy dispatcher binds env vars to ll-issues instead of python3

## Summary

In `autodev.yaml` state `recheck_after_size_review`, the BUG-2803 / ENH-2978 / ENH-2992
pre-deferral remedy selector computed `REMEDY` with the `GATE_MARKER` and `CONTRA_ONLY`
environment assignments prefixed to `ll-issues show`, not to the `python3 -c` process that
reads them through `os.environ`. A `VAR=x a | b` prefix binds only to `a`, so the Python
selector never saw either value. The measurement-gate → spike branch (ENH-2978) and the
contradiction-only reconcile → spike exemption (ENH-2992) were dead code.

## Current Behavior

Before the fix, an issue with a proof-gate marker in its body fell through to the
ambiguity-subscore comparison and usually got `reconcile` instead of `spike`. An issue whose
reconcile stamp was contradiction-only got an empty remedy and was deferred as
`low_readiness`, losing access to `spike`.

## Expected Behavior

`GATE_MARKER=true` dispatches `spike`. A contradiction-only reconcile stamp with no prior
spike dispatches `spike`.

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

- **Priority**: P2 — two documented remedy branches were silently inert
- **Effort**: Small
- **Risk**: Low

## Root Cause

- **File**: `scripts/little_loops/loops/autodev.yaml`
- **Anchor**: state `recheck_after_size_review`, the `REMEDY=$(...)` pipeline
- **Cause**: the env prefix was on the wrong side of the pipe. The shell variables are not
  exported, so the consumer process never inherited them.

The existing test helper `_run_pre_deferral_remedy_selector` in
`scripts/tests/test_autodev_loop.py` extracted only the Python script and injected the env
vars directly into it, which masked the bug.

## Resolution

- Moved the env prefix onto `python3` in `recheck_after_size_review`.
- Rewrote `_run_pre_deferral_remedy_selector` to run the real extracted shell pipeline under
  bash, with a stub `ll-issues` on `PATH` and unexported shell variables. Against the pre-fix
  YAML it fails 2 tests (`test_marker_present_forces_spike_even_when_ambiguity_not_weakest`,
  `test_contradiction_sourced_stamp_still_dispatches_spike`). Against the fix, all pass.
- Landed in commit `9a5d0f523`.

## Acceptance Criteria

- [x] Env assignments bind to the `python3` consumer
- [x] Test exercises the real pipeline with unexported shell vars and fails on the old YAML

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-24 | Priority: P2
