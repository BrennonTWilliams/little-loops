---
id: BUG-3767
type: BUG
title: refine-to-ready-issue has no repair path for VERIFY:other (Current Behavior
  citations, unapplied_decision)
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-10-07'
captured_at: '2026-10-07T01:12:47Z'
---

# BUG-3767: refine-to-ready-issue has no repair path for VERIFY:other (Current Behavior citations, unapplied_decision)

## Summary

`refine-to-ready-issue` deterministically fails with `GATE_UNMET` when `/ll:verify-issues --check` persists `verify_verdict: NON_VALID` for a stale line-number/symbol citation in `## Current Behavior`, or for `unapplied_decision` residue left in directive sections after `resolve-decision`. The only route from `VERIFY:other` is `check_gate_refine_limit` -> `refine_followup`, an additive-only pass that cannot fix a stale fact, so the shared refine budget burns on a no-op and the loop ends `failed`.

## Current Behavior

Observed run (transient, gitignored): `.loops/runs/refine-to-ready-issue-20261006T180316/` on BUG-3762 — 26 iterations, final state `failed`, run-record `outcome: deferred, legacy_class: gate_unmet`.

1. BUG-3762 `## Current Behavior` cited `raw_redaction.py:266` (real location: `_projection` at `:260`) and `:391` (real: `_plan_column`'s `col.value is None` check at `:374-375`; `:391` is the replacement-over-`STORED_CAP` check). Both citations predate the run (present in commit `e3dd5cdac`); `refine_issue` (iter 6) left them uncorrected.
2. `verify_issue` (iters 15, 23) persisted `verify_verdict: NON_VALID`. `commands/verify-issues.md:349` (BUG-3637) states a finding whose fix touches Current Behavior stays `NON_VALID`, never `CLAIMS_OUTDATED`, "regardless of how narrow the actual text change looks". The verify output in the run said Current Behavior "is outside the correctable scope" (run events, transient).
3. `route_pre_score_obligation` (`scripts/little_loops/loops/refine-to-ready-issue.yaml`, route table ~L600) maps `"VERIFY:other"` -> `check_gate_refine_limit` -> `refine_followup` (`/ll:refine-issue --auto --gap-analysis`), which is additive-only (`commands/refine-issue.md` §5c; the gap-analysis contract at ~L893). Iter 18 reported that nothing else was changed (run events, transient). The shared `refine-to-ready-refine-count` budget hit 2, so iter 25 routed `check_gate_refine_limit` -> `record_gate_unmet` -> `failed`.
4. Secondary: after `resolve-decision` selected Option A, `ll-issues format-check` still reported 4 `unapplied_decision` hits (`unverifiable_oversize`, `_fetch_one`, `complete: true`, `max_row_bytes`) in Program Design / Implementation Steps / Acceptance Criteria. verify and refine_followup both named `/ll:reconcile-issue` as the fix, but no route reaches `reconcile_issue` because the persisted verdict is `NON_VALID`, not `DIRECTIVE_DRIFT`.

## Expected Behavior

An otherwise-valid issue with (a) stale line/symbol citations in Current Behavior and/or (b) unapplied-decision residue converges to `VALID` within one repair cycle instead of reaching `record_gate_unmet`. Premise changes in Current Behavior still stay `NON_VALID`.

## Motivation

[Why this issue matters - business value, user impact, technical debt cost]

## Proposed Solution

Decision needed — options:

- **Option A**: route `VERIFY:other` to `check_reconcile_limit` -> `reconcile_issue` (-> `normalize_structure`) when the finding is a Current Behavior citation or `unapplied_decision`, instead of `check_gate_refine_limit`. Needs a discriminator (e.g. new sub-reason tokens from `ll-issues next-obligation` such as `VERIFY:CITATION` / `VERIFY:UNAPPLIED_DECISION`), and `reconcile-issue` must be permitted to edit Current Behavior citations.
- **Option B**: widen the `CLAIMS_OUTDATED` correctable scope in `commands/verify-issues.md` §2C to include pure line-number/range/symbol-location fixes inside Current Behavior (not premise changes), so they use the existing `check_claim_correction_budget` -> `correct_claims` path. Must preserve the BUG-3637 rationale (an independent `--check` re-pass cannot catch a rewritten premise) — restrict to pure citation anchors; route the `unapplied_decision` case separately (e.g. persist as `DIRECTIVE_DRIFT`).
- **Option C**: both — B for citations, A / `DIRECTIVE_DRIFT` classification for `unapplied_decision` residue.

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

## Acceptance Criteria

- A BUG-3762-shaped issue (stale Current Behavior line citations and/or `unapplied_decision` residue, otherwise valid) reaches `VALID` within one repair cycle and does not reach `record_gate_unmet`.
- A Current Behavior finding that changes the premise (not a pure citation anchor) still persists `NON_VALID` and is not auto-rewritten.
- `ll-loop validate refine-to-ready-issue` (MR rules) passes; `scripts/tests/test_builtin_loops.py` passes with new coverage for the new route.
- The route-table comment header in `refine-to-ready-issue.yaml` and the verdict docs in `commands/verify-issues.md` reflect the change.

## Related

BUG-3637 (CLAIMS_OUTDATED scope), BUG-3551 (shared refine budget), ENH-3604 (next-obligation dispatch), ENH-3248 (reconcile), BUG-3695 (DIRECTIVE_DRIFT via verify-evidence), ENH-3765 (unapplied_decision detection in format-check).

Side finding (minor, not part of this fix): in the same run's `resolve-decision` sub-loop, `assert_decision_cleared` (`ll-issues check-flag BUG-3762 decision_needed`) exited 1 although `/ll:decide-issue` reported `decision_needed: false`; it routed through `rearm_refuted_spike` and still reached `done`. Worth a separate look.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-10-07 | Priority: P3


## Session Log
- `/ll:capture-issue` - 2026-10-07T01:12:58 - `26bbdec0-accc-4f17-94d6-3d59f60b2e3f.jsonl`
