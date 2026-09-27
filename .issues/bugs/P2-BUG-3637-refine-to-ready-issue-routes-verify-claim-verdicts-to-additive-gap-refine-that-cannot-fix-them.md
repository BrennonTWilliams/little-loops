---
id: BUG-3637
type: BUG
title: refine-to-ready-issue routes verify claim verdicts to additive gap-refine that
  cannot fix them
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-27'
captured_at: '2026-09-27T17:40:15Z'
relates_to:
- ENH-3636
- ENH-3623
---

# BUG-3637: refine-to-ready-issue routes verify claim verdicts to additive gap-refine that cannot fix them

## Summary

When `/ll:verify-issues --check` finds a false claim about current state (OUTDATED / NEEDS_UPDATE), `refine-to-ready-issue` routes the resulting `verify_verdict: NON_VALID` through `VERIFY:other` → `check_gate_refine_limit` → `refine_followup` (`/ll:refine-issue --auto --gap-analysis`). That repair state (a) never receives verify's findings — `--check` mode persists only the verdict, the reasons live solely in the verify session transcript — and (b) is additive-only by contract (`commands/refine-issue.md` §5c), so it cannot delete or rewrite a stale fact even if it knew which one. The loop burns its gap-refine budget on a no-op repair and terminates `gate_unmet` without ever reaching `confidence_check`.

## Current Behavior

A NON_VALID caused by fixable stale claims is unrecoverable within the run: the only remedy the router reaches cannot see or correct the findings.

## Expected Behavior

Claim-level verify findings are corrected (or deterministically classified as non-defects) and the run proceeds to `confidence_check`.

## Motivation

[Why this issue matters - business value, user impact, technical debt cost]

## Proposed Solution

**C — deterministic satisfied-edge rule (do first).** Treat a `blocked_by` / `depends_on` edge whose target is `done` or `cancelled` as satisfied, never as a failing verify finding (at most a warning). Prefer a deterministic check (e.g. a `format-check` / gate rule) over verify prose so the verdict is reproducible. `deferred` stays non-terminal. Prose that contradicts the frontmatter remains a legitimate claim finding for A.

**A — let verify correct its own claim findings.**
1. Persist a finer check-mode verdict so claim-correctable verdicts are distinguishable: e.g. `verify_verdict: CLAIMS_OUTDATED` for OUTDATED / NEEDS_UPDATE, keeping INVALID / RESOLVED / DECISIONS_VIOLATION as `NON_VALID` (these must never be auto-corrected). Update `check_verify_verdict.py` and `ll-issues next-obligation` token mapping accordingly.
2. Add `"VERIFY:CLAIMS_OUTDATED": check_claim_correction_budget` → new `correct_claims` state running `/ll:verify-issues <ID> --auto` (non-check mode, which already writes corrections back — see the anchor-relocation and Verification Notes behavior in `commands/verify-issues.md`), then `normalize_structure` → `clear_verify_verdict` → `verify_issue --check`, so an independent check pass re-judges the edit (mitigates self-grading).
3. Budget: one correction attempt per run, own counter seeded in `resolve_issue`, exhausted → `check_gate_refine_limit` (existing fallback).
4. Keep `VERIFY:other` → `refine_followup` for genuine research gaps.
5. Update the verify-issues §2C prose so the remedy it names matches the route.

Fallback (B), only if verify must stay read-only inside the loop: persist verify findings to `${context.run_dir}/verify-findings` and feed them into `refine_followup`. Weaker: gap-analysis can at most append `⚠ Superseded` markers beside stale claims; whether a later verify accepts that is unproven, and it grows the marker debt reconcile flags.

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

1. Implement C (deterministic satisfied-edge rule) and add verify-issues prose deferring to it.
2. Add the finer check-mode verdict + `next-obligation` token + `check_verify_verdict` classification.
3. Add `check_claim_correction_budget` / `correct_claims` states and the route; seed the counter in `resolve_issue`.
4. Mirror the route in any caller that reuses the pre-score obligation map (check `autodev.yaml` / `prepare-issue.yaml` for equivalents).
5. Tests: routing table in `test_builtin_loops.py`; verdict classification; a fixture issue with a stale status claim reaching `confidence_check`.

## Impact

- **Priority**: P2 — every refine-to-ready run on an issue whose dependencies landed mid-flight can fail `gate_unmet` after ~50 min regardless of research quality; autodev inherits this.
- **Effort**: Medium
- **Risk**: Medium — changes the verify verdict enum consumed by multiple loops.

## Steps to Reproduce

Observed on run `refine-to-ready-issue-20260927T110415` for ENH-3623 (`ll-loop history refine-to-ready-issue 2026-09-27T160415`):

1. `verify_issue` (iter 15) → NON_VALID. Session `c66e52ca…` reported NEEDS_UPDATE; every citation, signature, state count and fixture shape checked out. Findings were only: `blocked_by: [ENH-3630]` stale (ENH-3630 is `done`, contradicting the issue's own Confidence Check Notes prose that no `blocked_by` remains), and Confidence Check Notes describing BUG-3628 as `open` (it is `done`).
2. `route_pre_score_obligation` → `VERIFY:other` → `refine_followup` (iter 18). Gap-analysis session `5e0fa7a0…` researched unrelated gaps (`_apply_outcome` crash-safety, `resume()` KeyError path), appended 11 lines, and touched none of the flagged facts.
3. `verify_issue` (iter 23) → NON_VALID again (session `71473c3f…`, OUTDATED): same BUG-3628 finding, plus a `prepare-issue.yaml` line-count drift (91 vs 90).
4. `check_gate_refine_limit` exhausted → `record_gate_unmet` → `failed` (26 iters, 50m, ~$5). `confidence_check` never ran; `refine-to-ready-reconcile-attempts` = 0.

## Root Cause

A broken remedy contract spanning three artifacts:

- **`commands/verify-issues.md` §2C verdict rule** (around lines 186-198) states that when a claim about current state is false, the claim-verdict wins and the existing `refine_followup` remedy repairs the research. It assumes the follow-up can repair claims.
- **`commands/verify-issues.md` §2.5 check-mode persistence** (around lines 343-349) collapses OUTDATED / RESOLVED / INVALID / NEEDS_UPDATE / DECISIONS_VIOLATION into one `verify_verdict: NON_VALID`, and `--check` writes nothing else — findings are dropped.
- **`scripts/little_loops/loops/refine-to-ready-issue.yaml`** `route_pre_score_obligation` maps `"VERIFY:other": check_gate_refine_limit`, whose remedy is `refine_followup` running `--gap-analysis` — additive-only, findings-blind.

Rejected alternative: routing to `check_reconcile_limit` / `reconcile_issue` does not help — `/ll:reconcile-issue` rewrites only Implementation Steps, Acceptance Criteria, Integration Map and contradicted Scope Boundaries, not Confidence Check Notes, Research Findings, or frontmatter where these stale facts live.

A contributing cause: verify's treatment of a `blocked_by` edge to a `done`/`cancelled` issue is LLM-judged and inconsistent — the first pass failed the issue for it, the second called it not a defect. Elsewhere such edges are durable by design and resolved at read time (`DependencyGraph.get_blocking_issues()` returns blockers minus completed; `cli/issues/set_status.py` never cascades association edges; ENH-3636 makes `show` annotate them).

## Acceptance Criteria

- A verify finding limited to stale status/line-count claims is corrected within the run and the loop reaches `confidence_check`.
- A `blocked_by` edge to a `done`/`cancelled` issue never produces a non-VALID verdict on its own.
- INVALID / RESOLVED verdicts are never routed to auto-correction.
- `ll-loop validate refine-to-ready-issue` passes.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-27 | Priority: P2


## Session Log
- `/ll:capture-issue` - 2026-09-27T17:40:28 - `4759cc5d-e905-4259-b830-49d49c1712bf.jsonl`
