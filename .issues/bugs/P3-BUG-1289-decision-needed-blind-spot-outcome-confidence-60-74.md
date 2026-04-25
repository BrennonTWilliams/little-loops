---
captured_at: "2026-04-25T19:07:05Z"
discovered_date: 2026-04-25
discovered_by: capture-issue
---

# BUG-1289: `decision_needed` blind spot for outcome_confidence 60–74

## Summary

`confidence-check` Phase 4.6 sets `decision_needed: true` only when `outcome_confidence < 60`, but autodev's `outcome_threshold` defaults to 75. Issues scoring 60–74 with genuine unresolved ambiguity (`score_ambiguity ≤ 10`) never get flagged, so autodev's `check_decision_before_size_review` gate never fires for them — they fall straight through to `run_size_review` and risk spurious decomposition.

## Current Behavior

Phase 4.6 of `confidence-check` (`skills/confidence-check/SKILL.md`, "Phase 4.6: Decision-Needed Flag") has this condition:

> "This phase only has effect when Phase 4.5 produced Outcome Risk Factors (i.e., `HAS_FINDINGS` is true and `outcome_confidence < 60`)"

The Phase 4.5 write-back that generates `Outcome Risk Factors` (which Phase 4.6 scans for signal phrases) is itself skipped when `outcome_confidence >= 60`. So the Phase 4.6 trigger cannot fire for any issue with `outcome_confidence` between 60 and 74, even if `score_ambiguity` is 0.

Meanwhile, `autodev.yaml` `context.outcome_threshold` defaults to 75. An issue with `outcome_confidence: 64` fails `check_passed`, but `decision_needed` is never set, so `check_decision_before_size_review` exits 1 → `run_size_review`.

## Expected Behavior

When `outcome_confidence` is below the project's `outcome_threshold` AND `score_ambiguity ≤ 10`, `decision_needed: true` should be set on the issue regardless of whether `outcome_confidence` is above or below 60. The current 60 threshold is an implementation artifact, not an intentional design boundary.

## Motivation

The `decision_needed` flag exists precisely to steer autodev away from size-review when the right intervention is `decide-issue`. The blind spot negates this protection for the 60–74 range — a realistic band where issues are "moderately risky" with ambiguity problems but not low enough to trigger the existing write-back path.

## Steps to Reproduce

1. Create an issue with `outcome_confidence: 64` and `score_ambiguity: 5` in frontmatter (unresolved design decision)
2. Set project `outcome_threshold: 75` in `.ll/ll-config.json`
3. Run `/ll:confidence-check [ID]`
4. Observe: Phase 4.5 generates no `Outcome Risk Factors` (because 64 ≥ 60)
5. Observe: Phase 4.6 never runs; `decision_needed` remains unset
6. Run autodev: `check_decision_before_size_review` exits 1 → `run_size_review` fires
7. Issue is incorrectly sent to size-review instead of `decide-issue`

## Root Cause

- **File**: `skills/confidence-check/SKILL.md`
- **Anchor**: Phase 4.5 (`HAS_FINDINGS` condition) and Phase 4.6 ("only has effect when... `outcome_confidence < 60`")
- **Cause**: The Phase 4.5 `HAS_FINDINGS` trigger for `Outcome Risk Factors` uses a hardcoded 60 threshold rather than the project-configurable `outcome_threshold`. Phase 4.6 depends on Phase 4.5 having fired, so it inherits the same gap.

## Proposed Solution

Two complementary options:

**Option A (preferred)**: In Phase 4.5, lower the `Outcome Risk Factors` trigger so it fires whenever `outcome_confidence < outcome_threshold` (read from `.ll/ll-config.json` `commands.confidence_gate.outcome_threshold`, defaulting to 75). Update Phase 4.5 trigger from hardcoded 60 to the project threshold.

**Option B** (additional safety net): In Phase 4.6, add a second trigger that sets `decision_needed: true` when `score_ambiguity ≤ 10` regardless of `outcome_confidence` — because low ambiguity score is a direct and unambiguous signal of a decision bottleneck.

Recommend implementing Option A first (closes the gap fully), then evaluate Option B separately.

## Integration Map

### Files to Modify
- `skills/confidence-check/SKILL.md` — Phase 4.5 `HAS_FINDINGS` condition and Phase 4.6 guard

### Dependent Files (Callers/Importers)
- `scripts/little_loops/loops/autodev.yaml` — reads `decision_needed` field via `ll-issues show --json`; no change needed

### Similar Patterns
- `manage-issue` Phase 2.3 Decision Gate — also reads `decision_needed`; unaffected

### Tests
- TBD — test fixture: issue with `outcome_confidence: 64`, `score_ambiguity: 5`; after confidence-check, verify `decision_needed: true` in frontmatter

### Documentation
- N/A — Phase 4.6 behavior not separately documented

### Configuration
- `.ll/ll-config.json` `commands.confidence_gate.outcome_threshold` — used to parameterize the trigger

## Implementation Steps

1. Read `commands.confidence_gate.outcome_threshold` from `.ll/ll-config.json` in confidence-check Phase 4.5 (default 75)
2. Change Phase 4.5 `Outcome Risk Factors` condition from `outcome_confidence < 60` to `outcome_confidence < outcome_threshold`
3. Phase 4.6 inherits the fix automatically since it depends on Phase 4.5 having produced Risk Factors
4. Add test fixture to verify `decision_needed` is set for issues in the 60–74 range with `score_ambiguity ≤ 10`

## Impact

- **Priority**: P3 — affects projects with `outcome_threshold > 60` (the default); fixes a systematic miss in the decision gate
- **Effort**: Small — single condition change in SKILL.md; no new logic
- **Risk**: Low — only affects Phase 4.5/4.6 write-back; does not change scoring or readiness gate behavior
- **Breaking Change**: No — adds write-back for issues that previously got no write-back; additive

## Labels

`bug`, `confidence-check`, `decision-needed`, `autodev`, `captured`

## Session Log
- `/ll:capture-issue` - 2026-04-25T19:07:05Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3e47d1ef-2bc6-4299-8018-0c5ef506b76e.jsonl`

---

**Open** | Created: 2026-04-25 | Priority: P3
