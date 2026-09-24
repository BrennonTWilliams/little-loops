---
id: BUG-3571
type: BUG
title: Refine-to-ready accepts stale or absent verify verdict and confidence scores
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-24'
captured_at: '2026-09-24T19:33:13Z'
parent: EPIC-3565
blocks:
- ENH-3577
---

# BUG-3571: Refine-to-ready accepts stale or absent verify verdict and confidence scores

## Summary

Readiness evidence is checked for presence, not currency:

- `ll-issues check-verify-verdict` (`cli/issues/check_verify_verdict.py`) returns 0 when
  `verify_verdict` is absent. This fail-open is deliberate (ENH-3031). But nothing in
  `refine-to-ready-issue` clears a prior verdict before `verify_issue` runs, and
  `verify_issue.on_error` routes into the check. A `VALID` from an earlier run, against
  earlier content, satisfies the gate even when the current verification errored.
- `oracles/verify-confidence-scores.yaml` `verify_scores_persisted` only asserts that
  `confidence` and `outcome` exist in frontmatter. Pre-existing scores pass even when the
  current `/ll:confidence-check` call wrote nothing.
- Autodev's outer `rerun_confidence_after_*` states route `on_error` into score checks, so a
  failed rescoring falls through to the old scores.

## Current Behavior

A failed verify or scoring call can be followed by a pass based on evidence from a previous
revision of the issue.

## Expected Behavior

A gate passes only on evidence produced by the current invocation, or on cached evidence
provably bound to the current issue content. A missing result from a current call is a
retryable infrastructure failure, not a pass.

## Steps to Reproduce

1. Run refine-to-ready-issue on an issue carrying `verify_verdict: VALID` and scores from an earlier run
2. Make `/ll:verify-issues --check` error (e.g. host failure) and have confidence-check write nothing
3. Observe `check_verify_verdict` exit 0 and `verify_scores_persisted` exit 0 on the stale values

## Motivation

Autodev's repair loop edits issue content (reconcile, wire, refine) and then rescores. Without freshness, the implementation gate can be satisfied by evidence about content that no longer exists.

## Proposed Solution

Design decision needed first: clearing the verdict at refine start is a no-op while an absent
verdict passes. Options:

1. **Invocation stamp**: record a run-scoped nonce or timestamp before each verify/score
   call. The check requires the persisted field's stamp to be at least that recent.
2. **Content fingerprint**: persist verdict/scores with a hash of the issue body that
   excludes the Session Log and score fields themselves. The check recomputes and compares.
3. **Clear-then-require**: clear `verify_verdict`/scores before the call, and make absence
   after a completed call fail (keeping fail-open only for the pre-ENH-3031 legacy case).

Option 3 is the cheapest. Option 2 also covers the outer loop's post-repair rescoring.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/issues/check_verify_verdict.py` — `cmd_check_verify_verdict`
- `scripts/little_loops/loops/oracles/verify-confidence-scores.yaml` — `verify_scores_persisted`, `verify_scores_persisted_final`
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` — `verify_issue`, `check_verify_verdict`
- `scripts/little_loops/loops/autodev.yaml` — `rerun_confidence_after_*` `on_error` routes

### Dependent Files (Callers/Importers)
- `commands/verify-issues.md` (`--check` verdict persistence)
- `skills/confidence-check/SKILL.md` (score persistence via `ll-issues set-scores`)

### Similar Patterns
- The resolve-decision oracle's `done` terminal: its description should also be corrected, since it can return `done` with the flag armed (see BUG-3568)

### Tests
- `scripts/tests/test_builtin_loops.py`, `scripts/tests/test_autodev_loop.py`; new stateful-stub regression cases

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Choose the freshness mechanism
2. Apply it to `check_verify_verdict` (default mode) and `verify-confidence-scores`
3. Route `rerun_confidence_*` `on_error` to a retry/infra path, not score checks
4. Regression tests: failed verify with an old `VALID`; no-op confidence-check with old scores

## Impact

- **Priority**: P2. Old scores come from real earlier runs, so this is not fabrication, but
  post-repair content goes unverified.
- **Effort**: Medium
- **Risk**: Medium. A stricter gate raises deferral rates.

## Acceptance Criteria

- [ ] A verify call that errors cannot pass on a verdict from a prior run
- [ ] A confidence-check that writes nothing cannot pass on pre-existing scores
- [ ] Session Log appends do not invalidate cached evidence

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-24 | Priority: P2


## Session Log
- `/ll:capture-issue` - 2026-09-24T19:42:31 - `59fe3bd4-3622-4dd2-bb8b-ad5cc55e79ec.jsonl`
