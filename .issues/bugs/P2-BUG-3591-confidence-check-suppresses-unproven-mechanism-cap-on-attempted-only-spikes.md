---
id: BUG-3591
type: BUG
title: Confidence-check suppresses unproven-mechanism cap on attempted-only spikes
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-25'
captured_at: '2026-09-25T03:40:42Z'
parent: EPIC-3565
supersedes:
- BUG-3572
blocks:
- BUG-3592
- BUG-3593
- ENH-3577
---

# BUG-3591: Confidence-check suppresses unproven-mechanism cap on attempted-only spikes

## Summary

Part (a) of BUG-3572's split: the cap and flag contract. confidence-check Phase 1.9
(ENH-3350) sets `SPIKE_SUPPRESSED` when **either** `spike_attempted` or `spike_completed` is
set (`skills/confidence-check/SKILL.md:231`, one `{ …||… }` group). A failed spike sets only
`spike_attempted: true` (`skills/spike/SKILL.md` Phase 6 "On failure"), so a spike that
*disproved* the mechanism removes the unproven-mechanism outcome cap that demanded the
proof. This child closes that hole on its own: only a proven spike retires the cap.

The full design record, including the research behind these decisions, is BUG-3572
(cancelled, superseded by this issue, BUG-3592 and BUG-3593).

## Current Behavior

`/ll:spike --auto` fails → only `spike_attempted: true` is written → `/ll:confidence-check`
Phase 1.9 sets `SPIKE_SUPPRESSED` → `rubric.md` § "Outcome Confidence Cap (ENH-3350)" skips
`min(raw_sum, outcome_threshold − 1)` → `outcome_confidence` is the raw Criteria A–D sum,
and the issue can pass the outcome threshold on an approach its own spike refuted.

A second, related hole: Phase 6 only adds flags ("skip the write if already `true`"), so a
`/ll:spike --force` rerun that fails after an earlier proven spike keeps the stale
`spike_completed: true`, and the cap stays suppressed on a mechanism that now fails.

## Expected Behavior

- Phase 1.9 sets `SPIKE_SUPPRESSED` on `spike_completed` only. `spike_attempted` stays
  purely an attempt bound (autodev's remedy dispatcher and both loops' `check_spike_needed`
  rely on it).
- A failed spike run removes any stale `spike_completed`, so a failed `--force` rerun
  re-applies the cap.
- Legacy attempted-only issues read as "not proven" and keep the cap (fail-safe).

## Steps to Reproduce

1. Take an issue with `unproven_mechanism: true` whose mechanism is wrong
2. Run `/ll:spike --auto`; verification fails, and only `spike_attempted: true` is written
3. Run `/ll:confidence-check`: Phase 1.9 sets `SPIKE_SUPPRESSED`, and the outcome is scored with no unproven-mechanism cap

## Root Cause

- **File**: `skills/confidence-check/SKILL.md`
- **Anchor**: Phase 1.9 (ENH-3350), the `SPIKE_SUPPRESSED` assignment
- **Cause**: suppression keys on the attempt flag as well as the completion flag, so an
  attempt that disproved the mechanism counts as proof.

## Proposed Solution

1. **Cap**: change Phase 1.9 to
   `ll-issues check-flag {{issue_id}} spike_completed >/dev/null 2>&1 && SPIKE_SUPPRESSED="yes"`.
   Update the `rubric.md` cap row wording to "suppressed only by a proven spike
   (`spike_completed`)".
2. **Stale-flag removal on failure**: spike Phase 6 "On failure" sets `spike_attempted: true`
   **and removes `spike_completed`** if present (same Edit-the-frontmatter convention as the
   writes; there is no `set-flag` verb and `set-flags` is set-only). "On success" is
   unchanged. BUG-3592 later replaces the success/failure pair with the full three-verdict
   flag table (proven/refuted/inconclusive); this child only needs the proven-vs-not split.
3. **Phase 7 message**: the failure message stops asserting "Approach disproven" — until
   BUG-3592 lands, the skill cannot tell a refutation from an environment failure. Use
   "Spike did not prove the mechanism — see `## Spike Findings`".
4. **Docs**: correct `docs/reference/API.md`'s "cleared by /ll:spike (spike_completed)"
   comment (the spike skill never clears `unproven_mechanism`; suppression is purely the
   Phase 1.9 read); `docs/reference/ISSUE_TEMPLATE.md` `spike_attempted` row states it no
   longer suppresses the cap; `docs/reference/COMMANDS.md` / `docs/guides/LOOPS_REFERENCE.md`
   where they describe cap suppression.

### Interim behavior (until BUG-3593 lands)

A failed spike now keeps the cap, and neither loop routes on the spike's result yet:

- **refine-to-ready**: `run_spike` → `confidence_check` → the capped outcome fails
  `check_outcome` → `check_decision_needed` (no) → `check_spike_needed` (no, attempted) →
  `check_missing_artifacts` → toward `breakdown_issue`. An issue whose spike failed may be
  decomposed.
- **autodev**: the rescored, capped issue falls into the existing sub-threshold paths
  (size review / deferral) instead of `implement_current`.

Both are conservative: decomposing or deferring is safer than implementing an unproven
approach. BUG-3593 replaces them with verdict routing. Accept this as known interim
behavior; do not add routing here.

## Program Design

### Types

- No new types. `spike_completed` / `spike_attempted` keep their existing lowercase-bool frontmatter shape.

### Signatures

- `cmd_check_flag(config: BRConfig, args: argparse.Namespace) -> int` — existing `ll-issues check-flag` (`cli/issues/check_flag.py`); Phase 1.9 calls it once, for `spike_completed`, instead of twice.

### Call Path

`cmd_check_flag` -> `parse_frontmatter`

## Integration Map

### Files to Modify
- `skills/confidence-check/SKILL.md` — Phase 1.9 `SPIKE_SUPPRESSED` on `spike_completed` only
- `skills/confidence-check/rubric.md` — cap row wording (companion file; mirror drift check covers it)
- `skills/spike/SKILL.md` — Phase 6 "On failure" removes stale `spike_completed`; Phase 7 failure message
- `docs/reference/API.md`, `docs/reference/ISSUE_TEMPLATE.md`, `docs/reference/COMMANDS.md`, `docs/guides/LOOPS_REFERENCE.md`

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/issues/set_flags.py` — `_spike_not_already_flagged()` gates `spike_needed` re-flagging on attempted-or-completed; stays attempt-bound (unchanged)
- `scripts/little_loops/loops/spike-gate.yaml` — already completion-keyed; unchanged
- `commands/refine-issue.md` (~L1083), `commands/reconcile-issue.md` (~L144) — read the spike flags; confirm semantics unchanged

### Tests
- `scripts/tests/test_confidence_check_skill.py` — update the Phase 1.9 assertions / `test_spike_attempted_guard_enforced`; add: attempted-only keeps the cap
- `scripts/tests/test_spike_skill.py` — "On failure" removes a stale `spike_completed` (literal-string pattern at `:100-107`)
- `scripts/tests/test_set_flags_cli.py` — `_spike_not_already_flagged` behavior unchanged
- `scripts/tests/test_wiring_skills_and_commands.py` — `test_host_artifacts_are_not_stale` (all five `GATED_HOSTS`, incl. `rubric.md` companion drift)

## Implementation Steps

1. Before landing, list the affected legacy issues: `unproven_mechanism: true` +
   `spike_attempted: true` with no `spike_completed`. Record the list in the PR/commit body.
2. Phase 1.9 change + `rubric.md` wording.
3. Spike Phase 6 stale-flag removal + Phase 7 message.
4. Tests, docs, then `ll-adapt --host <gemini|kimi-code|qwen|codex|omp> --apply`.

## Acceptance Criteria

- [ ] A failed (attempted-only) spike does not suppress the unproven-mechanism cap
- [ ] Only `spike_completed: true` suppresses the cap
- [ ] A failed `--force` rerun after a proven spike removes `spike_completed`, and the cap re-applies
- [ ] `spike_attempted` still bounds re-spiking in both loops and in `set_flags.py`
- [ ] Legacy attempted-only issues are listed before landing

## Impact

- **Priority**: P2 - a refuted approach can pass the outcome gate and reach implementation
- **Effort**: Small - a one-line cap change, one skill-phase edit, docs and mirrors
- **Risk**: Low - fail-safe direction (more issues capped, never fewer)
- **Breaking Change**: No; expect a one-time rise in capped/deferred `unproven_mechanism` issues at their next rescoring

## Status

**Open** | Created: 2026-09-25 | Priority: P2
