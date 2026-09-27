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

- Every `refine-to-ready-issue` run that hits a claim-correctable NON_VALID verdict burns its entire gate-refine budget on a no-op (`refine_followup` cannot touch the flagged facts) and fails `gate_unmet` without ever reaching `confidence_check` — the observed run cost ~50 minutes and ~$5 for zero progress.
- `autodev.yaml` inherits this router, so the failure mode is not confined to manual `/ll:manage-issue` runs.
- Fixing it recovers runs that are otherwise correct except for a stale `blocked_by`/status claim that landed mid-flight — a routine occurrence given how many issues resolve dependencies while a long refine run is in progress.

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
- `scripts/little_loops/cli/issues/check_verify_verdict.py` — `classify_verify_verdict()` gains a `CLAIMS_OUTDATED` branch
- `scripts/little_loops/cli/issues/next_obligation.py` — `_verify_class()` / `select_next_obligation()` propagate the new token
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` — `route_pre_score_obligation` route table, new `check_claim_correction_budget` / `correct_claims` states
- `commands/verify-issues.md` — §2C verdict rule and §2.5 check-mode persistence prose updated to match the new remedy path (no code change to the command itself)
- `commands/refine-issue.md` — cited only as evidence that the existing additive-only contract (§5c) is unchanged by this fix; not modified

### Dependent Files (Callers/Importers)
- `scripts/little_loops/loops/autodev.yaml` / `scripts/little_loops/loops/prepare-issue.yaml` — check for an equivalent pre-score obligation route table that needs the same `VERIFY:CLAIMS_OUTDATED` branch (Implementation Step 4). Confirmed via `ll-code`/grep: neither has its own `route_pre_score_obligation`-style table — `prepare-issue.yaml` delegates via `loop: refine-to-ready-issue` (`:38`), and `autodev.yaml` only narrates the chain in comments (`:101,197,480,...`); a repo-wide grep for `VERIFY:` under `scripts/little_loops/loops/` returns only `refine-to-ready-issue.yaml`, so Implementation Step 4 is confirmed unnecessary — no other loop has a table to mirror
- `scripts/little_loops/cli/issues/__init__.py` — `next-obligation` token mapping is surfaced through this CLI entry point
- `scripts/little_loops/preparation_policy.py:749-766` — calls `select_next_obligation()` with `skip=tier1` where `tier1` includes `Obligation.VERIFY` (`:751`); this call site never resolves a `VERIFY:*` token today and is unaffected by the new `CLAIMS_OUTDATED` class (caller-suitability guard: VERIFY is explicitly skipped here) [Agent 1/2 finding]
- `scripts/little_loops/cli/issues/clear_verify_verdict.py:49` — `remove_frontmatter_keys(content, ("verify_verdict", "verify_evidence"))` deletes the key by name only, value-agnostic; confirmed unaffected by the new `CLAIMS_OUTDATED` value (no hardcoded enum check) [Agent 1 finding]
- `.kimi-code/skills/ll-verify-issues/SKILL.md`, `.gemini/commands/verify-issues.toml`, `.qwen/commands/ll/verify-issues.md` — verbatim host mirrors of `commands/verify-issues.md`'s §2C/§2.5 prose (matching `NON_VALID`/`verify_verdict` line offsets); `scripts/tests/test_wiring_skills_and_commands.py` (`SKILL_MIRROR_ROOTS`/`GATED_HOSTS`) gates them for staleness — resync with `ll-adapt --host <gemini|kimi-code|qwen> --apply` after editing `commands/verify-issues.md` [Agent 1/2 finding]

_Wiring pass added by `/ll:wire-issue`:_ the four items above.

### Similar Patterns
- `check_evidence_unverified` / `check_proposal_revision_budget` / `check_reconcile_limit` — existing one-shot-budget gate states in `refine-to-ready-issue.yaml` that `check_claim_correction_budget` should mirror (counter seeded in `resolve_issue`, exhaustion falls through to `check_gate_refine_limit`). Correction from wiring pass: `check_evidence_unverified` was consolidated away by the ENH-3604 dispatch refactor (`test_builtin_loops.py:3106` `REMOVED_STATES`) — `VERIFY:EVIDENCE_UNVERIFIED` now shares `check_gate_refine_limit` directly, no dedicated counter. Only `check_proposal_revision_budget` (states `refine-to-ready-issue.yaml:605-620`) and `check_reconcile_limit` (`test_builtin_loops.py:1646-1684`, `:1882-1922`) have the seeded-counter shape to mirror [Agent 3 finding]
- `scripts/tests/test_dependency_graph.py` `TestGetBlockingIssues.test_completed_blockers_excluded` / `test_completed_blocker_not_added` (lines 128-140, 333-363) with shared `make_issue()` fixture — `DependencyGraph.get_blocking_issues(issue_id, completed=...)` (`scripts/little_loops/dependency_graph.py:283`) already implements "an edge to a `done`/`cancelled` target is never a live blocker" at the graph layer; model Proposed Solution C's deterministic satisfied-edge rule test after this shape [Agent 3 finding]

### Tests
- `scripts/tests/test_builtin_loops.py` — routing table coverage for the new `VERIFY:CLAIMS_OUTDATED` route and `ll-loop validate refine-to-ready-issue`. Specific sites that must update in lockstep or they fail: `TestRefineToReadyDispatch.PRE_TABLE` dict (`:3118-3131`, exact-equality assertion in `test_pre_score_routing_table` `:3180-3184`); `_tokens()`'s `sub["VERIFY"]` list (`:3154-3161`, consumed by `test_dispatch_tokens_are_complete` `:3198-3203` — a silent under-verification gap, not a red test, if missed); `test_reachability_of_kept_budget_states` (`:3292-3294`) requires `check_claim_correction_budget`/`correct_claims` to exist once referenced in `PRE_TABLE` [Agent 3 finding]
- `scripts/tests/test_ll_issues_next_obligation.py` — `TestVerify.test_classifier` (`:63-77`, parametrized over `classify_verify_verdict()` value/expected pairs) and `TestVerify.test_sub_reasons` (`:85-95`, parametrized `verdict` list asserting `res.token()`) — both need new `OUTDATED`/`NEEDS_UPDATE` → `CLAIMS_OUTDATED` cases; neither currently asserts the old collapse, so this is additive, not breaking [Agent 3 finding]
- `scripts/tests/test_ll_issues_check_verify_verdict.py` — existing CLI-contract suite for `cmd_check_verify_verdict()`; does not yet construct `OUTDATED`/`NEEDS_UPDATE`/`CLAIMS_OUTDATED` frontmatter — add coverage for the new class falling through the same non-`VALID` exit-1 branch (lines 150-166 of the source) [Agent 2/3 finding]
- `scripts/tests/test_enh3250_verify_issues_proposal_vs_code.py` — established precedent module for prose-level verdict carve-outs: `TestProposalUnsoundVerdict.test_verdict_table_has_proposal_unsound` / `test_persistence_carves_out_proposal_unsound` / `test_persistence_still_exits_1_in_check_mode` (`:78-110`), and `TestDirectiveDriftVerdict` (`:114-125`) for BUG-3574's carve-out. `CLAIMS_OUTDATED` is the same shape — per this repo's own precedent, add an equivalent `TestClaimsOutdatedVerdict` class here (not a new file) asserting §2C's verdict table and §2.5's persistence text name `CLAIMS_OUTDATED` distinctly from `NON_VALID` [Agent 2/3 finding]
- Unit test for `classify_verify_verdict()` distinguishing `CLAIMS_OUTDATED` from `NON_VALID`/`other` — resolved: see `test_ll_issues_next_obligation.py` entry above (no separate new file needed)
- Fixture issue with a stale status claim (e.g. `blocked_by` pointing at a `done` issue) reaching `confidence_check` end-to-end — closest existing harness is `TestTier1GateParity.test_clean_issue_is_clean_for_both` (`test_ll_issues_next_obligation.py:455-461`, builds a `.issues/` fixture project and asserts selector + `ll-issues` gate CLI agree); no full FSM-driven end-to-end run of `refine-to-ready-issue.yaml` exists anywhere in the suite — searched `scripts/tests/integration/test_loop_run_e2e.py` (no hits) — so this new test is selector-level (Pattern 6), not a real FSM run [Agent 3 finding]

### Documentation
- `commands/verify-issues.md` §2C / §2.5 prose (see Files to Modify)
- `docs/guides/LOOPS_REFERENCE.md:146-158` — "Claim-verification gate chain" token-routing table (`:154` lists `VERIFY:EVIDENCE_UNVERIFIED, VERIFY:other, PLACEHOLDERS, DESIGN → check_gate_refine_limit`); needs a new row `VERIFY:CLAIMS_OUTDATED → check_claim_correction_budget` plus a sentence on `correct_claims`'s budget semantics [Agent 2 finding]
- `docs/reference/CLI.md:2384-2405` (`ll-issues next-obligation` section, closed-vocabulary list at `:2388`) and `:2577-2597` (`check-verify-verdict` section's exhaustive value list) — both enumerate the VERIFY sub-reason vocabulary and need `CLAIMS_OUTDATED` added [Agent 2 finding]
- Intra-file docstrings that go stale in files already in Files to Modify (sites_to_add, not new files): `check_verify_verdict.py` `classify_verify_verdict()` docstring (`:29-31`, exhaustive value list); `next_obligation.py` module docstring (`:1-18`) and `Obligation` class docstring (`:34-45`) [Agent 2 finding]

### Configuration
- N/A

### Behavior Parity

| File | Status |
|---|---|
| `commands/refine-issue.md` | Preserved — the Summary's "cannot delete or rewrite" clause describes `refine_followup`'s existing additive-only contract (§5c) as the *reason* this bug exists, not a change target. This fix does not modify `commands/refine-issue.md`; `refine_followup` keeps running unmodified for genuine research gaps (Proposed Solution A.4). |

## Program Design

### Types

- `verify_verdict: Literal["VALID", "CLAIMS_OUTDATED", "NON_VALID", "EVIDENCE_UNVERIFIED", "PROPOSAL_UNSOUND", "DIRECTIVE_DRIFT"]` — new `CLAIMS_OUTDATED` value carved out of the current `NON_VALID` collapse (frontmatter field written by `/ll:verify-issues --check`)

### Signatures

- `classify_verify_verdict(verdict: object) -> str` (`scripts/little_loops/cli/issues/check_verify_verdict.py`) — extend the upper-value branch to return `"CLAIMS_OUTDATED"` for the OUTDATED/NEEDS_UPDATE case instead of falling through to `"other"`
- `_verify_class(fm: dict[str, Any]) -> str` / `select_next_obligation(...)` (`scripts/little_loops/cli/issues/next_obligation.py`) — propagate the new class into a `"VERIFY:CLAIMS_OUTDATED"` token distinct from `"VERIFY:other"`

### Call Path

`route_pre_score_obligation` (`scripts/little_loops/loops/refine-to-ready-issue.yaml`) -> `next_obligation.select_next_obligation` -> `next_obligation._verify_class` -> `check_verify_verdict.classify_verify_verdict` -> route `"VERIFY:CLAIMS_OUTDATED"` -> `check_claim_correction_budget` (new state, counter seeded in `resolve_issue`) -> `correct_claims` (new state, `/ll:verify-issues ${issue_id} --auto`) -> `normalize_structure` -> `clear_verify_verdict` -> `route_pre_score_obligation` (re-entry)

## Implementation Steps

1. Implement C (deterministic satisfied-edge rule) and add verify-issues prose deferring to it.
2. Add the finer check-mode verdict + `next-obligation` token + `check_verify_verdict` classification.
3. Add `check_claim_correction_budget` / `correct_claims` states and the route; seed the counter in `resolve_issue`.
4. Mirror the route in any caller that reuses the pre-score obligation map (check `autodev.yaml` / `prepare-issue.yaml` for equivalents).
5. Tests: routing table in `test_builtin_loops.py`; verdict classification; a fixture issue with a stale status claim reaching `confidence_check`.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Update `test_builtin_loops.py` — add `"VERIFY:CLAIMS_OUTDATED": "check_claim_correction_budget"` to `TestRefineToReadyDispatch.PRE_TABLE` (`:3118-3131`) and `"CLAIMS_OUTDATED"` to `_tokens()`'s `sub["VERIFY"]` list (`:3154-3161`) in the same change as the YAML route, or `test_pre_score_routing_table` / `test_dispatch_tokens_are_complete` fail or silently under-verify
- Update `test_ll_issues_next_obligation.py` — add `OUTDATED`/`NEEDS_UPDATE` → `CLAIMS_OUTDATED` cases to `TestVerify.test_classifier` (`:63-77`) and `TestVerify.test_sub_reasons` (`:85-95`)
- Add `TestClaimsOutdatedVerdict` to `test_enh3250_verify_issues_proposal_vs_code.py` (alongside `TestProposalUnsoundVerdict`/`TestDirectiveDriftVerdict`) asserting §2C's verdict table and §2.5's persistence text name `CLAIMS_OUTDATED` distinctly from `NON_VALID`
- Update `docs/guides/LOOPS_REFERENCE.md:146-158` — add `VERIFY:CLAIMS_OUTDATED → check_claim_correction_budget` row to the claim-verification gate chain table
- Update `docs/reference/CLI.md:2384-2405,2577-2597` — add `CLAIMS_OUTDATED` to the `next-obligation` and `check-verify-verdict` vocabulary lists
- Update docstrings: `check_verify_verdict.py` `classify_verify_verdict()` (`:29-31`); `next_obligation.py` module docstring (`:1-18`) and `Obligation` class docstring (`:34-45`)
- Update `refine-to-ready-issue.yaml` — seed a new counter (e.g. `refine-to-ready-claim-corrections`) in `resolve_issue` (`:178-197`, mirroring `check_proposal_revision_budget`'s counter at `:611-616`); add a routing-summary header line (`:24`) for `VERIFY:CLAIMS_OUTDATED`; bump `max_steps` (`:132`) with a dated ledger comment entry per the file's established convention (see prior ENH-3031/BUG-3065/ENH-3248/etc. entries)
- After editing `commands/verify-issues.md`, run `ll-adapt --host gemini --apply`, `ll-adapt --host kimi-code --apply`, `ll-adapt --host qwen --apply` to resync `.gemini/commands/verify-issues.toml`, `.kimi-code/skills/ll-verify-issues/SKILL.md`, `.qwen/commands/ll/verify-issues.md` — `test_wiring_skills_and_commands.py` gates staleness
- Add a new test module/class exercising `DependencyGraph.get_blocking_issues(completed=...)`-style satisfied-edge semantics for Proposed Solution C, modeled on `test_dependency_graph.py:TestGetBlockingIssues` (`:128-140,333-363`), in whichever module ends up hosting the deterministic check
- No change needed at `preparation_policy.py:749-766` (VERIFY is in its `skip=tier1` set) or `clear_verify_verdict.py:49` (value-agnostic key removal) — verified, not touchpoints

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
- `/ll:wire-issue` - 2026-09-27T18:20:18 - `a542cb1a-fb64-418c-96c1-dffa8cf6d60f.jsonl`
- `/ll:refine-issue` - 2026-09-27T18:07:47 - `45431681-0957-443f-9bca-12828c2ee935.jsonl`
- `/ll:format-issue` - 2026-09-27T18:05:46 - `1bdd3eba-088f-4b15-88f8-1d11e0d8cb3b.jsonl`
- `/ll:capture-issue` - 2026-09-27T17:40:28 - `4759cc5d-e905-4259-b830-49d49c1712bf.jsonl`
