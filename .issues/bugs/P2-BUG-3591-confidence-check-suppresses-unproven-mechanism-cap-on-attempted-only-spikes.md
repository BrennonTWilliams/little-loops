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
confidence_score: 100
outcome_confidence: 93
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
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
   writes; there is no `set-flag`/unset verb and `set-flags` is set-only). If the issue
   already carries a `## Spike Results` section from an earlier proven run, the failure
   branch also marks it superseded (e.g. a `_Superseded by the failed /ll:spike --force run
   on [YYYY-MM-DD] — see ## Spike Findings_` line under its heading), so the body does not
   show a "✓ pass" table next to the new findings for the LLM scorer to read. "On success" is
   unchanged. BUG-3592 later replaces the success/failure pair with the full three-verdict
   flag table (proven/refuted/inconclusive); this child only needs the proven-vs-not split.
3. **Stop asserting disproof**: until BUG-3592 lands, the skill cannot tell a refutation
   from an environment failure. Soften all three sites together:
   - Phase 6 "On failure" preamble (`skills/spike/SKILL.md` ~L255, "A failed spike is
     signal: the approach is wrong.") → "A failed spike did not prove the mechanism; the
     cause may be the approach or the environment."
   - Phase 6 "On failure" step 2 (~L258, "documenting what was disproven") → "documenting
     which Verification commands failed and the failing output".
   - Phase 7 failure message → "Spike did not prove the mechanism — see `## Spike Findings`".
4. **Docs**:
   - `docs/reference/API.md:719` — the `unproven_mechanism` comment's "cleared by /ll:spike
     (spike_completed) or /ll:reconcile-issue" is wrong on both halves: nothing clears
     `unproven_mechanism` (`commands/reconcile-issue.md` never mentions it). Replace with
     "cap suppressed only by `spike_completed: true` (confidence-check Phase 1.9); the flag
     itself is never cleared".
   - `docs/reference/ISSUE_TEMPLATE.md` — `spike_attempted` row (L919) states it does not
     suppress the unproven-mechanism cap; `spike_completed` row (L920) states it is the sole
     flag that suppresses the cap, and that a failed spike run removes it.
   - `docs/reference/COMMANDS.md` `/ll:spike` **Write-back** paragraph (~L382) — "On
     failure" also removes a stale `spike_completed` (and marks a prior `## Spike Results`
     superseded); drop "documenting what was disproven".
   - `scripts/little_loops/loops/spike-gate.yaml:63` — the comment cites
     `SKILL.md:248,257`, which shift with the Phase 6 edit; cite "Phase 6" instead of line
     numbers.
   - `docs/guides/LOOPS_REFERENCE.md` needs no change: it does not describe cap suppression.

### Interim behavior (until BUG-3593 lands)

A failed spike now keeps the cap, and neither loop routes on the spike's result yet:

- **refine-to-ready**: `run_spike` → `confidence_check` → the capped outcome fails
  `check_outcome` → `check_decision_needed` (no) → `check_spike_needed` (no, attempted) →
  `check_missing_artifacts` → toward `breakdown_issue`. An issue whose spike failed may be
  decomposed.
- **autodev**: the rescored, capped issue falls into the existing sub-threshold paths
  (size review / deferral) instead of `implement_current`.

- **Re-decided issues stay capped**: nothing clears `unproven_mechanism`, and
  `spike_attempted` blocks an automatic re-spike. An issue whose spike failed and that
  `/ll:decide-issue` then moved to a different approach stays capped until a spike
  succeeds. BUG-3593's re-arm rule (in `/ll:decide-issue`) removes `spike_attempted` after
  such a decision; until then the manual escape is `/ll:spike <ID> --force`.

All of these are conservative: decomposing or deferring is safer than implementing an
unproven approach. BUG-3593 replaces them with verdict routing. Accept this as known
interim behavior; do not add routing here.

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
- `skills/spike/SKILL.md` — Phase 6 "On failure" removes stale `spike_completed` and marks a prior `## Spike Results` superseded; softened disproof wording at ~L255, ~L258 and the Phase 7 failure message
- `docs/reference/API.md` (L719), `docs/reference/ISSUE_TEMPLATE.md` (L919–920), `docs/reference/COMMANDS.md` (`/ll:spike` Write-back, ~L382)
- `scripts/little_loops/loops/spike-gate.yaml` — L63 comment only (line citation → "Phase 6")

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/issues/set_flags.py` — `_spike_not_already_flagged()` gates `spike_needed` re-flagging on attempted-or-completed; stays attempt-bound (unchanged)
- `scripts/little_loops/loops/spike-gate.yaml` — already completion-keyed; logic unchanged (comment-only edit above)
- `scripts/little_loops/loops/autodev.yaml` (`check_spike_needed` ~L1545, `check_spike_needed_before_skip` ~L1806, remedy dispatcher ~L2641) and `scripts/little_loops/loops/refine-to-ready-issue.yaml` (`check_spike_needed` ~L784) — key on `spike_attempted` as an attempt bound; unchanged
- `commands/refine-issue.md` (~L1083), `commands/reconcile-issue.md` (~L144) — read the spike flags; confirm semantics unchanged

### Tests
- `scripts/tests/test_confidence_check_skill.py`:
  - `test_phase_1_9_reads_spike_suppression` (`:766-773`) — **will fail as written** (it
    requires Phase 1.9 to name both `spike_attempted` and `spike_completed`). Invert it:
    the `SPIKE_SUPPRESSED` assignment line names `spike_completed` and does **not** name
    `spike_attempted`.
  - `test_cap_suppressed_by_spike_completion` (`:828`) — also assert the rubric cap
    section's new "suppressed only by a proven spike (`spike_completed`)" wording.
  - `test_spike_attempted_guard_enforced` (`:315`) — tests `set_flags._spike_not_already_flagged`,
    not Phase 1.9; leave unchanged.
- `scripts/tests/test_spike_skill.py` — add literal-string assertions (same pattern as
  `:100-107`): the Phase 6 "On failure" block contains "remove `spike_completed`"; the
  failure branch no longer contains "Approach disproven" or "the approach is wrong".
- `scripts/tests/test_set_flags_cli.py` — `_spike_not_already_flagged` behavior unchanged
- `scripts/tests/test_wiring_skills_and_commands.py` — `test_host_artifacts_are_not_stale` (all five `GATED_HOSTS`, incl. `rubric.md` companion drift)

## Implementation Steps

1. Re-run the legacy scan just before landing (`unproven_mechanism: true` +
   `spike_attempted: true`, no `spike_completed`) and record the result in the commit
   body. As of 2026-09-24 the only match is FEAT-3498 (`status: done`), so no active issue
   changes behavior.
2. Phase 1.9 change + `rubric.md` wording.
3. Spike Phase 6 stale-flag removal + superseded `## Spike Results` marker + softened
   disproof wording (Phase 6 preamble, step 2, Phase 7 message).
4. Tests, docs, `spike-gate.yaml` comment, then
   `ll-adapt --host <gemini|kimi-code|qwen|codex|omp> --apply`.

## Acceptance Criteria

- [ ] A failed (attempted-only) spike does not suppress the unproven-mechanism cap
- [ ] Only `spike_completed: true` suppresses the cap
- [ ] A failed `--force` rerun after a proven spike removes `spike_completed`, and the cap re-applies
- [ ] `spike_attempted` still bounds re-spiking in both loops and in `set_flags.py`
- [ ] Legacy attempted-only issues are listed before landing
- [ ] The spike skill no longer claims a failed spike disproved the approach (Phase 6 preamble, step 2, Phase 7)
- [ ] A failed `--force` rerun marks an earlier `## Spike Results` section superseded
- [ ] `docs/reference/API.md` no longer claims `/ll:spike` or `/ll:reconcile-issue` clears `unproven_mechanism`

## Impact

- **Priority**: P2 - a refuted approach can pass the outcome gate and reach implementation
- **Effort**: Small - a one-line cap change, one skill-phase edit, docs and mirrors
- **Risk**: Low - fail-safe direction (more issues capped, never fewer)
- **Breaking Change**: No. The only legacy attempted-only issue today (FEAT-3498) is `done`, so no active issue is newly capped at landing; the change affects future failed spikes only

## Status

**Open** | Created: 2026-09-25 | Priority: P2


## Session Log
- `/ll:confidence-check` - 2026-09-25T03:58:39 - `e649b48b-f380-457c-89a4-a5ed32cc660d.jsonl`
