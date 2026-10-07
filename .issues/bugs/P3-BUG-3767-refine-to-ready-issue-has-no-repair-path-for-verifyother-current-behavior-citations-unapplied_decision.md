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

Observed run (transient, gitignored): `.loops/runs/refine-to-ready-issue-20261006T180316/` on BUG-3762 — 26 iterations, final state `failed`. <!-- ll-evidence-ok: run record is in transient gitignored directory, not tracked issue file -->
Run-record outcome: `deferred`, legacy class: `gate_unmet`.

1. BUG-3762 `## Current Behavior` cited `raw_redaction.py:266` (real location: `_projection` at `:260`) and `:391` (real: `_plan_column`'s `col.value is None` check at `:374-375`; `:391` is the replacement-over-`STORED_CAP` check). Both citations predate the run (present in commit `e3dd5cdac`); `refine_issue` (iter 6) left them uncorrected.
2. `verify_issue` (iters 15, 23) persisted `verify_verdict: NON_VALID`. `commands/verify-issues.md:349` (BUG-3637) states a finding whose fix touches Current Behavior stays `NON_VALID`, never `CLAIMS_OUTDATED`, "regardless of how narrow the actual text change looks". The verify output in the run said Current Behavior "is outside the correctable scope" (run events, transient).
3. `route_pre_score_obligation` (`scripts/little_loops/loops/refine-to-ready-issue.yaml`, route table ~L600) maps `"VERIFY:other"` -> `check_gate_refine_limit` -> `refine_followup` (`/ll:refine-issue --auto --gap-analysis`), which is additive-only (`commands/refine-issue.md` §5c; the gap-analysis contract at ~L893). Iter 18 reported that nothing else was changed (run events, transient). The shared `refine-to-ready-refine-count` budget hit 2, so iter 25 routed `check_gate_refine_limit` -> `record_gate_unmet` -> `failed`.
4. Secondary: after `resolve-decision` selected Option A, `ll-issues format-check` still reported 4 `unapplied_decision` hits (`unverifiable_oversize`, `_fetch_one`, `complete: true`, `max_row_bytes`) in Program Design / Implementation Steps / Acceptance Criteria. verify and refine_followup both named `/ll:reconcile-issue` as the fix, but no route reaches `reconcile_issue` because the persisted verdict is `NON_VALID`, not `DIRECTIVE_DRIFT`.

## Expected Behavior

An otherwise-valid issue with (a) stale line/symbol citations in Current Behavior and/or (b) unapplied-decision residue converges to `VALID` within one repair cycle instead of reaching `record_gate_unmet`. Premise changes in Current Behavior still stay `NON_VALID`.

## Steps to Reproduce

1. Take an otherwise-valid issue whose `## Current Behavior` cites a stale line number/symbol location (e.g. BUG-3762's `raw_redaction.py:266` / `:391`), and/or that still carries `unapplied_decision` residue in Program Design / Implementation Steps / Acceptance Criteria after `resolve-decision`.
2. Run `ll-loop run refine-to-ready-issue` on it (e.g. `BUG-3762`).
3. Observe: `verify_issue` persists `verify_verdict: NON_VALID`; `route_pre_score_obligation` emits `VERIFY:other` -> `check_gate_refine_limit` -> `refine_followup` (additive-only, changes nothing); the shared refine budget exhausts and the loop ends `record_gate_unmet` -> `failed`.

## Motivation

This fix would:
- Stop a deterministic, avoidable `GATE_UNMET` failure: the loop burns its whole shared refine budget (26 iterations in the observed BUG-3762 run) on a no-op `refine_followup` pass and ends `failed`.
- Remove a manual step: the issue is otherwise valid, yet a human must hand-edit citations or run `/ll:reconcile-issue` to unblock it.
- Close a dead end in the verdict model: `reconcile_issue` is named as the fix by both verify and `refine_followup`, but no persisted verdict reaches it for these two finding classes.

## Proposed Solution

Decision needed — options:

- **Option A**: route `VERIFY:other` to `check_reconcile_limit` -> `reconcile_issue` (-> `normalize_structure`) when the finding is a Current Behavior citation or `unapplied_decision`, instead of `check_gate_refine_limit`. Needs a discriminator (e.g. new sub-reason tokens from `ll-issues next-obligation` such as `VERIFY:CITATION` / `VERIFY:UNAPPLIED_DECISION`), and `reconcile-issue` must be permitted to edit Current Behavior citations.
- **Option B**: widen the `CLAIMS_OUTDATED` correctable scope in `commands/verify-issues.md` §2C to include pure line-number/range/symbol-location fixes inside Current Behavior (not premise changes), so they use the existing `check_claim_correction_budget` -> `correct_claims` path. Must preserve the BUG-3637 rationale (an independent `--check` re-pass cannot catch a rewritten premise) — restrict to pure citation anchors; route the `unapplied_decision` case separately (e.g. persist as `DIRECTIVE_DRIFT`).
- **Option C**: both — B for citations, A / `DIRECTIVE_DRIFT` classification for `unapplied_decision` residue.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` — `route_pre_score_obligation` route table and its header comment (`"VERIFY:other"` -> `check_gate_refine_limit`); `check_reconcile_limit` / `reconcile_issue` / `check_claim_correction_budget` / `correct_claims` states (reach depends on the selected option)
- `commands/verify-issues.md` — §2C verdict table and "Correctable scope for `CLAIMS_OUTDATED`" rule (BUG-3637), §2.5 persisted-verdict mapping and verdict precedence
- `commands/reconcile-issue.md` — only if Current Behavior citation edits must become permitted
- `scripts/little_loops/cli/issues/check_verify_verdict.py` — `classify_verify_verdict` (token set), only if new sub-reason tokens are introduced
- `scripts/little_loops/cli/issues/next_obligation.py` — `_verify_class` / `select_next_obligation`, only if new `VERIFY:*` tokens are introduced

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/issues/check_verify_verdict.py:classify_verify_verdict` is shared by `cmd_check_verify_verdict` and `next_obligation._verify_class`; any new token must be handled in both
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` — sole consumer of the `VERIFY:*` token table; `autodev.yaml` reuses the refine loop's run_dir across issues (see `check_verify_retries` comment)

### Similar Patterns
- BUG-3637 `check_claim_correction_budget` -> `correct_claims` (own counter, exhaustion goes straight to `record_gate_unmet`)
- BUG-3695 `VERIFY:DIRECTIVE_DRIFT` -> `check_reconcile_limit` -> `reconcile_issue --from-verify-evidence`
- BUG-3574 `check_proposal_revision_budget` (per-verdict dedicated budget)

### Tests
- `scripts/tests/test_builtin_loops.py` — `PRE_TABLE` route-table assertions (~L3131-3145) and `check_reconcile_limit` / `check_gate_refine_limit` budget tests (~L1680-1760)
- `scripts/tests/test_ll_issues_next_obligation.py` — token emission for any new `VERIFY:*` sub-reason

### Documentation
- `docs/guides/LOOPS_REFERENCE.md` — documents the `VERIFY:other` route
- `commands/verify-issues.md` verdict docs (also listed under Files to Modify)

### Configuration
- N/A

## Program Design

### Types

- Persisted `verify_verdict: str` and `verify_evidence: str` (existing frontmatter fields) carry the finding class; any new sub-reason token is an additional value returned by `classify_verify_verdict`. The exact set depends on the option selected in Proposed Solution.

### Signatures

- `classify_verify_verdict(verdict: object) -> str` — existing; extended only if a new token is added.
- `select_next_obligation(...)` in `scripts/little_loops/cli/issues/next_obligation.py` — existing; emits `VERIFY:<class>` via `_verify_class(fm: dict[str, Any]) -> str`.

### Call Path

`route_pre_score_obligation` -> `ll-issues next-obligation` -> `select_next_obligation` -> `_verify_class` -> `classify_verify_verdict`; the emitted `VERIFY:*` token is routed by the loop's `route:` table to an existing budget state (`check_reconcile_limit` or `check_claim_correction_budget`) instead of `check_gate_refine_limit`.

## Implementation Steps

1. Resolve the Proposed Solution decision (`/ll:decide-issue BUG-3767`), then add a discriminator that separates a Current Behavior citation / `unapplied_decision` finding from other `NON_VALID` causes.
2. Update `commands/verify-issues.md` §2C/§2.5 (and, if needed, `classify_verify_verdict` + `next_obligation`) to persist/emit the discriminated verdict while keeping premise changes `NON_VALID`.
3. Update `route_pre_score_obligation`'s route table and header comment to send the new class to an existing repair budget state; extend `commands/reconcile-issue.md` scope only if required.
4. Extend `PRE_TABLE` and budget tests in `scripts/tests/test_builtin_loops.py` and the token tests in `scripts/tests/test_ll_issues_next_obligation.py`.
5. Verify: `ll-loop validate refine-to-ready-issue`, `python -m pytest scripts/tests/test_builtin_loops.py scripts/tests/test_ll_issues_next_obligation.py`, then re-run the loop against a BUG-3762-shaped fixture and confirm it reaches `VALID`.

## Impact

- **Priority**: P3 - deterministic loop failure with a manual workaround (hand-edit or `/ll:reconcile-issue`); not data-losing
- **Effort**: Medium - touches loop routing, verify verdict docs, and (for some options) a CLI token set plus tests
- **Risk**: Medium - changes shared refine-loop routing used by autodev; must preserve the BUG-3637 premise-change guard
- **Breaking Change**: No

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
- `/ll:format-issue` - 2026-10-07T01:16:48 - `7610b26f-db95-4e3a-b048-687107034721.jsonl`
- `/ll:capture-issue` - 2026-10-07T01:12:58 - `26bbdec0-accc-4f17-94d6-3d59f60b2e3f.jsonl`
