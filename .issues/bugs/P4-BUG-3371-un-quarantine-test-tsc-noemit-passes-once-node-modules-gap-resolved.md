---
id: BUG-3371
type: BUG
title: "Un-quarantine test_tsc_noemit_passes once the verify gate's node_modules gap is resolved"
priority: P4
status: open
discovered_by: manage-issue
discovered_date: '2026-08-31'
relates_to:
- BUG-3368
decision_needed: false
program_design_not_applicable: true
---

# BUG-3371: Un-quarantine `test_tsc_noemit_passes` once the verify gate's node_modules gap is resolved

## Summary

BUG-3368 quarantined `test_tsc_noemit_passes` (`scripts/tests/test_opencode_adapter.py`
and `scripts/tests/test_omp_adapter.py`) under the `LL_VERIFY_GATE=1` self-detection
marker, because the epic-worktree verify gate's ephemeral `git worktree add` checkout
only materializes git-tracked content — the gitignored `node_modules/@types/bun`
devDependency is never installed there, so `tsc --noEmit` fails on a missing type
definition regardless of the commit under test.

This mirrors the BUG-2649→BUG-2650 lifecycle: quarantine now, track removal once the
underlying gap is closed (or the gate's scope is deliberately revisited).

## Current Behavior

`test_tsc_noemit_passes` in both files carries a permanent
`@pytest.mark.skipif(os.environ.get("LL_VERIFY_GATE") == "1", ...)` decorator, so it
never runs the real `tsc --noEmit` check under the gate. No tooling enforces
un-quarantine — this bug is the only tracking mechanism.

## Expected Behavior

Either:
- The verify gate's worktree setup materializes `node_modules` (e.g. a `bun install`
  step) before running tests, making the quarantine unnecessary and this skipif
  removable, or
- The gate's scope is deliberately redefined to exclude JS/TS type-checking from
  worktree-based verification, and this bug is closed as won't-fix with that
  rationale recorded.

## Proposed Solution

Revisit once there is a concrete driver (e.g. another false-negative from Option A's
absence, or a deliberate decision to make the gate hermetic for JS toolchains).
Not urgent — filed per BUG-2650 precedent to keep the quarantine auditable, not
because removal is expected soon.

## Impact

- **Priority**: P4 — tracking-only; no active harm while quarantined.
- **Effort**: Unknown — depends on which resolution path is chosen.
- **Risk**: Low.

## Status

**Open** | Created: 2026-08-31 | Priority: P4
