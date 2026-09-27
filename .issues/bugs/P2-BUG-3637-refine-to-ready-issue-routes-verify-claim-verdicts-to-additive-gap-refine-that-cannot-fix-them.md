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
confidence_score: 100
outcome_confidence: 90
score_complexity: 15
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
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

**C — CLI-resolved satisfied-edge rule (do first; independently shippable).** Treat a `blocked_by` / `depends_on` edge whose target is `done` or `cancelled` as satisfied, never as a failing verify finding (at most an informational note). `deferred` stays non-terminal. Target status comes from the `ll-issues` CLI, not from LLM judgment or directory location; the rule itself is still applied by the model following §2E prose, so it is CLI-grounded rather than fully deterministic.

`commands/verify-issues.md` §2E already half-states this rule ("If in completed: note as 'satisfied' (informational, not an error)", `:261-263`), but it keys on the body `## Blocked By` section and on directory location ("in completed"), which is not a status signal — done issues stay in their type dirs. Fix §2E to:
- read the frontmatter `blocked_by` / `depends_on` lists (body `## Blocked By` as fallback only);
- resolve each target's status via `ll-issues show <REF> --json`, lowercasing the value and treating `done` / `completed` / `cancelled` as satisfied (`show --json` status is display-cased, e.g. `"Completed"` for `done`);
- **skip the §2E.2 `MISSING_BACKLINK` check for satisfied edges.** Otherwise a satisfied edge whose done target lacks a `## Blocks` backlink still yields `DEP_ISSUES` → `NON_VALID`, which is in A's never-auto-correct set and outranks `CLAIMS_OUTDATED` — the run would still end `gate_unmet`;
- for prose dependency claims, consume the existing deterministic `stale_prose_dep` / `prose_dep_drift` output of `ll-issues format-check <ID> --format json` (computed from issue statuses in `issue_parser.py:1170-1193`, and already run by `normalize_structure` before every verify) instead of re-deriving it by LLM judgment;
- state explicitly that a satisfied edge never contributes to a non-VALID verdict, and that prose asserting a dependency is resolved, satisfied, or no longer present is **consistent** with a satisfied edge — not a contradiction. (This is the exact ENH-3630 finding in Steps to Reproduce: frontmatter `blocked_by: [ENH-3630]` → `done` vs Confidence Check Notes saying no `blocked_by` remains.) Only prose asserting a satisfied target is still *open/active* (the BUG-3628 finding) remains a claim finding for A.

Add `Bash(ll-issues:*)` to `commands/verify-issues.md` `allowed-tools` (currently only `git`, `ll-code`, `ll-verify-evidence`; §4.5's `ll-issues append-log` already depends on it implicitly). **Decision:** C does not wait for ENH-3636 — per-edge `show --json` lookups work today; once ENH-3636 lands, §2E can switch to reading its single-call annotation.

**A — let verify correct its own claim findings.**
1. Persist a finer check-mode verdict so claim-correctable verdicts are distinguishable: `verify_verdict: CLAIMS_OUTDATED` for `OUTDATED` / `NEEDS_UPDATE` **whose findings are all in the correctable scope below**. Every other claim verdict stays `NON_VALID` and must never be auto-corrected: `INVALID`, `RESOLVED`, `DECISIONS_VIOLATION`, `REGRESSION_LIKELY`, `POSSIBLE_REGRESSION`, `DEP_ISSUES`. **Precedence** (one persisted value per issue, highest wins):
   `NON_VALID` (any finding in the never-auto-correct set, or any out-of-scope `OUTDATED`/`NEEDS_UPDATE` finding) > `EVIDENCE_UNVERIFIED` > `CLAIMS_OUTDATED` > `PROPOSAL_UNSOUND` > `DIRECTIVE_DRIFT` > `VALID`.
   `CLAIMS_OUTDATED` above `PROPOSAL_UNSOUND`/`DIRECTIVE_DRIFT` restates §2C's existing "claim-verdict wins" rule; `EVIDENCE_UNVERIFIED` above it because a fabricated quote is not a stale fact and must not be "corrected" into the file.

   **Correctable scope — classify by which section the fix touches, not by verdict label** (the same principle §2C already applies to split `PROPOSAL_UNSOUND` from `DIRECTIVE_DRIFT`). `OUTDATED` means "Referenced code has changed", which also covers a *premise* change (bug partially fixed, targeted code refactored). Auto-rewriting a premise in place is unsafe because the independent `--check` re-pass cannot catch it: the rewritten issue is internally consistent. So a finding is correctable only when it is a **factual metadata correction** — another issue's status, a file path, a line number/range, a count (line/state/test counts), a citation anchor or symbol location — whose fix is confined to Codebase Research Findings, Confidence Check Notes, Verification Notes, Integration Map citations, Similar Patterns/Tests citations, or frontmatter references. Any finding whose fix requires changing Summary, Current Behavior, Expected Behavior, Root Cause, Motivation, Steps to Reproduce, or Proposed Solution stays `NON_VALID`.
2. **Persist the findings, not just the verdict.** For `CLAIMS_OUTDATED`, `--check` also writes `verify_evidence:` (same single-line double-quoted YAML scalar contract already used for `PROPOSAL_UNSOUND`, `verify-issues.md:337-343`), one item per stale claim, `; `-separated, each item shaped `<section>: '<stale text>' -> <current truth>` (single quotes inside the item avoid `"` escaping), e.g. `verify_evidence: "Confidence Check Notes: 'BUG-3628 is open' -> BUG-3628 is done; Integration Map: 'prepare-issue.yaml (91 lines)' -> 90 lines"`. Naming the section lets `correct_claims` apply the fix without re-locating the claim. `clear_verify_verdict` already removes `verify_evidence` (`clear_verify_verdict.py:49`), so no new cleanup is needed.
3. Add `"VERIFY:CLAIMS_OUTDATED": check_claim_correction_budget` → new `correct_claims` state running `/ll:verify-issues <ID> --auto --from-evidence` (non-check mode, targeted), which reads `verify_evidence` as its work list, then `normalize_structure` → `clear_verify_verdict` → `verify_issue` (`--check`), so an independent check pass re-judges the edit (mitigates self-grading).
4. **Add a targeted `--from-evidence` mode (§0 flag parse + `argument-hint` + `flags` description).** Without it, non-check `--auto` re-runs the full 2A–2E sweep — a second full verify session per correction on top of the `--check` re-pass — and may apply fixes beyond the work list. With `--from-evidence`: read the issue's `verify_evidence`, re-check **only** the listed claims against the codebase, apply only those corrections, and skip 2A–2E otherwise. If `verify_evidence` is absent or empty, make no edits and exit (the `--check` re-pass then decides). An explicit flag, not implicit detection of a leftover `verify_evidence` field, so a manual `/ll:verify-issues <ID>` on an issue left behind by a `gate_unmet` run keeps its normal full-sweep behavior.
5. **Widen non-check §4 so it can actually correct claims.** Today §3/§4 (`verify-issues.md:364-376`) authorize only adding `## Verification Notes` and updating paths/line numbers — nothing permits rewriting a stale fact in Confidence Check Notes / Research Findings or dropping a stale frontmatter reference, so `correct_claims` would otherwise be the same additive no-op this bug describes. Add: under `--from-evidence` (or for an in-scope `OUTDATED`/`NEEDS_UPDATE` finding in a normal non-check run), rewrite each stale statement **in place** in whichever section holds it (including frontmatter status/line-count references); a Verification Notes entry alone does not count as a correction. The correctable-scope limit from step 1 applies: never rewrite Summary / Current Behavior / Expected Behavior / Root Cause / Motivation / Steps to Reproduce / Proposed Solution in this mode. Never-auto-correct verdicts from step 1 stay read-only, and resolved-status changes stay out of auto mode (existing §3 rule).
6. Budget: one correction attempt per run, own counter (`refine-to-ready-claim-corrections`) seeded in `resolve_issue`. **Exhausted → `record_gate_unmet`**, not `check_gate_refine_limit`: this bug demonstrates `refine_followup` cannot repair this verdict class, so falling back to it spends another ~15 min for nothing.
7. Keep `VERIFY:other` → `check_gate_refine_limit` → `refine_followup` for genuine research gaps (including out-of-scope `OUTDATED`/`NEEDS_UPDATE` findings, now persisted as `NON_VALID`).
8. Update the verify-issues §2C prose so the remedy it names (`refine_followup`) becomes `correct_claims` for `CLAIMS_OUTDATED`.

Rejected fallback (B) — persist findings to `${context.run_dir}/verify-findings` and feed them into `refine_followup`: gap-analysis can at most append `⚠ Superseded` markers beside stale claims, whether a later verify accepts that is unproven, and it grows the marker debt reconcile flags. A.2 keeps B's one useful idea (findings persisted and handed to the repair state) without the additive-only limitation.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/issues/check_verify_verdict.py` — add `"CLAIMS_OUTDATED"` to the pass-through tuple in `classify_verify_verdict()` (`:36`); no new `--claims-outdated` query flag is needed (routing goes through `next-obligation`, not this CLI's flags)
- `scripts/little_loops/cli/issues/next_obligation.py` — no logic change: `_verify_class()` delegates to the classifier and `select_next_obligation()` already emits `VERIFY:<class>`; docstrings only (see Documentation)
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` — `route_pre_score_obligation` route table, new `check_claim_correction_budget` / `correct_claims` states, counter seed in `resolve_issue`
- `commands/verify-issues.md` — `allowed-tools` (+`Bash(ll-issues:*)`); frontmatter `argument-hint` / `flags` description and §0 flag parse (+`--from-evidence`, Proposed Solution A.4); §2C verdict rule (remedy name + correctable-scope rule, A.1); §2E satisfied-edge rule keyed on frontmatter + `ll-issues show --json` status, backlink-check exemption for satisfied edges, and `format-check` `stale_prose_dep` consumption (Proposed Solution C); §2.5 persistence (`CLAIMS_OUTDATED` + `verify_evidence` item format, full precedence order); §3/§4 in-place claim correction driven by `verify_evidence`, limited to the correctable scope (A.5); §4.1 frontmatter-sync residual mapping includes `CLAIMS_OUTDATED`; §Arguments / §Examples list `--from-evidence`
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
- `scripts/little_loops/dependency_graph.py:283` `DependencyGraph.get_blocking_issues(issue_id, completed=...)` — already implements "an edge to a `done`/`cancelled` target is never a live blocker" at the graph layer (covered by `test_dependency_graph.py` `TestGetBlockingIssues.test_completed_blockers_excluded` `:333-363` and `TestDependencyGraphConstruction.test_completed_blocker_not_added` `:128-140`). Semantic precedent for Proposed Solution C only — C is implemented in `commands/verify-issues.md` prose, not in Python, so there is no new Python code path to unit-test this way; C is covered by the prose test in `test_enh3250_verify_issues_proposal_vs_code.py` [Agent 3 finding, corrected in review]
- `scripts/little_loops/issue_parser.py:1170-1193` — `ll-issues format-check` already classifies prose dependency claims against issue statuses (`stale_prose_dep` for `done`/`cancelled` targets, `prose_dep_drift` for active targets missing from `blocked_by`/`depends_on`) and runs in `normalize_structure` before every `verify_issue`. §2E should consume its `--format json` output for prose deps rather than re-judge them [review finding]

### Tests
- `scripts/tests/test_builtin_loops.py` — routing table coverage for the new `VERIFY:CLAIMS_OUTDATED` route and `ll-loop validate refine-to-ready-issue`. Specific sites that must update in lockstep or they fail: `TestRefineToReadyDispatch.PRE_TABLE` dict (`:3118-3131`, exact-equality assertion in `test_pre_score_routing_table` `:3180-3184`); `_tokens()`'s `sub["VERIFY"]` list (`:3154-3161`, consumed by `test_dispatch_tokens_are_complete` `:3198-3203` — a silent under-verification gap, not a red test, if missed); `test_reachability_of_kept_budget_states` (`:3292-3294`) requires `check_claim_correction_budget`/`correct_claims` to exist once referenced in `PRE_TABLE` [Agent 3 finding]
- `scripts/tests/test_ll_issues_next_obligation.py` — `TestVerify.test_classifier` (`:63-77`, parametrized over `classify_verify_verdict()` value/expected pairs): add `("CLAIMS_OUTDATED", "CLAIMS_OUTDATED")`, `("claims_outdated", "CLAIMS_OUTDATED")`, and pin `("OUTDATED", "other")` / `("NEEDS_UPDATE", "other")` — raw §2C labels are never persisted, so they must not be silently accepted as aliases. `TestVerify.test_sub_reasons` (`:85-95`): add `"CLAIMS_OUTDATED"` to the `verdict` list (expects `VERIFY:CLAIMS_OUTDATED`). Additive, not breaking [Agent 3 finding, corrected in review]
- `scripts/tests/test_ll_issues_check_verify_verdict.py` — existing CLI-contract suite for `cmd_check_verify_verdict()`; does not yet construct `OUTDATED`/`NEEDS_UPDATE`/`CLAIMS_OUTDATED` frontmatter — add coverage for the new class falling through the same non-`VALID` exit-1 branch (lines 150-166 of the source) [Agent 2/3 finding]
- `scripts/tests/test_enh3250_verify_issues_proposal_vs_code.py` — established precedent module for prose-level verdict carve-outs: `TestProposalUnsoundVerdict.test_verdict_table_has_proposal_unsound` / `test_persistence_carves_out_proposal_unsound` / `test_persistence_still_exits_1_in_check_mode` (`:78-110`), and `TestDirectiveDriftVerdict` (`:114-125`) for BUG-3574's carve-out. `CLAIMS_OUTDATED` is the same shape — per this repo's own precedent, add an equivalent `TestClaimsOutdatedVerdict` class here (not a new file) asserting: §2.5 names `CLAIMS_OUTDATED` distinctly from `NON_VALID`, writes `verify_evidence` for it (with the `<section>: '<stale>' -> <truth>` item shape), and keeps `INVALID`/`RESOLVED`/`DECISIONS_VIOLATION`/`REGRESSION_*`/`DEP_ISSUES` in `NON_VALID`; §2.5 states the precedence order; §2C/§2.5 state the correctable-scope rule (Summary / Current Behavior / Expected Behavior / Root Cause / Proposed Solution fixes stay `NON_VALID`); §4 contains the in-place-correction rule; §0 parses `--from-evidence` and the text says it re-checks only the listed claims; §2E names frontmatter `blocked_by`/`depends_on` and `ll-issues show` (not "in completed"), exempts satisfied edges from `MISSING_BACKLINK`, and references `stale_prose_dep`; `allowed-tools` includes `Bash(ll-issues:*)` [Agent 2/3 finding, extended in review]
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
| `commands/refine-issue.md` | Preserved — the Summary's "cannot delete or rewrite" clause describes `refine_followup`'s existing additive-only contract (§5c) as the *reason* this bug exists, not a change target. This fix does not modify `commands/refine-issue.md`; `refine_followup` keeps running unmodified for genuine research gaps (Proposed Solution A.7). |

## Program Design

### Types

- `verify_verdict: Literal["VALID", "CLAIMS_OUTDATED", "NON_VALID", "EVIDENCE_UNVERIFIED", "PROPOSAL_UNSOUND", "DIRECTIVE_DRIFT"]` — new `CLAIMS_OUTDATED` value carved out of the current `NON_VALID` collapse (frontmatter field written by `/ll:verify-issues --check`)

### Signatures

- `classify_verify_verdict(verdict: object) -> str` (`scripts/little_loops/cli/issues/check_verify_verdict.py`) — the classifier reads the *persisted* value, which is `CLAIMS_OUTDATED` (never raw `OUTDATED`/`NEEDS_UPDATE`); add `"CLAIMS_OUTDATED"` to the upper-value pass-through tuple so it returns `"CLAIMS_OUTDATED"` instead of `"other"`
- `_verify_class(fm: dict[str, Any]) -> str` / `select_next_obligation(...)` (`scripts/little_loops/cli/issues/next_obligation.py`) — unchanged; the new class flows through to a `"VERIFY:CLAIMS_OUTDATED"` token distinct from `"VERIFY:other"` with no code edit

### Call Path

`route_pre_score_obligation` (`scripts/little_loops/loops/refine-to-ready-issue.yaml`) -> `next_obligation.select_next_obligation` -> `next_obligation._verify_class` -> `check_verify_verdict.classify_verify_verdict` -> route `"VERIFY:CLAIMS_OUTDATED"` -> `check_claim_correction_budget` (new state, counter seeded in `resolve_issue`; exhausted -> `record_gate_unmet`) -> `correct_claims` (new state, `/ll:verify-issues ${issue_id} --auto --from-evidence`, consumes `verify_evidence`) -> `normalize_structure` -> `clear_verify_verdict` -> `verify_issue` (`--check`) -> `route_pre_score_obligation` (re-entry)

## Implementation Steps

1. Implement C: rewrite `commands/verify-issues.md` §2E to key on frontmatter `blocked_by`/`depends_on` and `ll-issues show <REF> --json` status (lowercased; `done`/`completed`/`cancelled` = satisfied); exempt satisfied edges from the §2E.2 `MISSING_BACKLINK` check; consume `ll-issues format-check <ID> --format json` `stale_prose_dep`/`prose_dep_drift` for prose deps; state that prose calling a dependency resolved/absent is consistent with a satisfied edge; add `Bash(ll-issues:*)` to `allowed-tools`. Independently shippable — can land (and be split out) before A.
2. Add the `CLAIMS_OUTDATED` persisted verdict + correctable-scope rule + `verify_evidence` findings write (`<section>: '<stale>' -> <truth>` items) + precedence order to §2C/§2.5; add `"CLAIMS_OUTDATED"` to `classify_verify_verdict()`'s pass-through tuple.
3. Add the `--from-evidence` flag (§0 parse, `argument-hint`, `flags` description, §Arguments/§Examples): re-check only the listed claims, apply only those, no-op when `verify_evidence` is absent.
4. Widen §3/§4 (non-check mode) to rewrite stale claims in place from the `verify_evidence` work list, bounded by the correctable scope; update §2C's remedy name and §4.1's residual mapping.
5. Add `check_claim_correction_budget` (exhausted → `record_gate_unmet`) / `correct_claims` states and the route; seed `refine-to-ready-claim-corrections` in `resolve_issue`; bump `max_steps` 100 → 110.
6. ~~Mirror the route in `autodev.yaml` / `prepare-issue.yaml`~~ — N/A, confirmed in Dependent Files: neither has its own pre-score route table.
7. Tests: routing table in `test_builtin_loops.py`; verdict classification; `TestClaimsOutdatedVerdict` prose assertions; a fixture issue with a stale status claim reaching `confidence_check` (selector-level).

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Update `test_builtin_loops.py` — add `"VERIFY:CLAIMS_OUTDATED": "check_claim_correction_budget"` to `TestRefineToReadyDispatch.PRE_TABLE` (`:3118-3131`) and `"CLAIMS_OUTDATED"` to `_tokens()`'s `sub["VERIFY"]` list (`:3154-3161`) in the same change as the YAML route, or `test_pre_score_routing_table` / `test_dispatch_tokens_are_complete` fail or silently under-verify
- Update `test_ll_issues_next_obligation.py` — add `CLAIMS_OUTDATED` → `CLAIMS_OUTDATED` (and pin raw `OUTDATED`/`NEEDS_UPDATE` → `other`) to `TestVerify.test_classifier` (`:63-77`); add `CLAIMS_OUTDATED` to `TestVerify.test_sub_reasons` (`:85-95`)
- Add `TestClaimsOutdatedVerdict` to `test_enh3250_verify_issues_proposal_vs_code.py` (alongside `TestProposalUnsoundVerdict`/`TestDirectiveDriftVerdict`) asserting §2C's verdict table and §2.5's persistence text name `CLAIMS_OUTDATED` distinctly from `NON_VALID`
- Update `docs/guides/LOOPS_REFERENCE.md:146-158` — add `VERIFY:CLAIMS_OUTDATED → check_claim_correction_budget` row to the claim-verification gate chain table
- Update `docs/reference/CLI.md:2384-2405,2577-2597` — add `CLAIMS_OUTDATED` to the `next-obligation` and `check-verify-verdict` vocabulary lists
- Update docstrings: `check_verify_verdict.py` `classify_verify_verdict()` (`:29-31`); `next_obligation.py` module docstring (`:1-18`) and `Obligation` class docstring (`:34-45`)
- Update `refine-to-ready-issue.yaml` — seed `refine-to-ready-claim-corrections` in `resolve_issue` (`:178-197`, mirroring `check_proposal_revision_budget`'s counter at `:611-616`); `check_claim_correction_budget` `on_no`/`on_error` → `record_gate_unmet`; `correct_claims` action `/ll:verify-issues ${captured.issue_id.output} --auto --from-evidence`, `pruning_profile: verify-issues-auto`, `on_error: normalize_structure`; add a routing-summary header line (`:24`) for `VERIFY:CLAIMS_OUTDATED`; bump `max_steps` (`:132`) **100 → 110** with a dated ledger comment entry per the file's established convention (see prior ENH-3031/BUG-3065/ENH-3248/etc. entries) — the correction cycle is `check_claim_correction_budget → correct_claims → normalize_structure → clear_verify_verdict → verify_issue → route_pre_score_obligation` (6 steps, 7 if `normalize_structure` falls back to `format_issue_post`), rounded up for headroom
- After editing `commands/verify-issues.md`, run `ll-adapt --host gemini --apply`, `ll-adapt --host kimi-code --apply`, `ll-adapt --host qwen --apply` to resync `.gemini/commands/verify-issues.toml`, `.kimi-code/skills/ll-verify-issues/SKILL.md`, `.qwen/commands/ll/verify-issues.md` — `test_wiring_skills_and_commands.py` gates staleness
- ~~Add a `DependencyGraph.get_blocking_issues`-style test module for Proposed Solution C~~ — dropped in review: C lives in `commands/verify-issues.md` prose, so no Python module hosts it; C is covered by the `TestClaimsOutdatedVerdict` prose assertions (§2E frontmatter keying, backlink exemption, `stale_prose_dep` reference)
- No change needed at `preparation_policy.py:749-766` (VERIFY is in its `skip=tier1` set) or `clear_verify_verdict.py:49` (value-agnostic key removal) — verified, not touchpoints

## Impact

- **Priority**: P2 — every refine-to-ready run on an issue whose dependencies landed mid-flight can fail `gate_unmet` after ~50 min regardless of research quality; autodev inherits this.
- **Effort**: Medium
- **Risk**: Medium — the verdict enum is consumed only by `refine-to-ready-issue.yaml` (grep: no other `VERIFY:` route table, `preparation_policy.py` skips VERIFY), so the enum change itself is low-risk; the real risk is A.5 widening verify's non-check write authority to in-place rewrites of issue prose/frontmatter, bounded by the never-auto-correct set, the correctable-scope rule (no premise sections), the targeted `--from-evidence` mode, and the independent `--check` re-pass.

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

- A verify finding limited to stale status/line-count claims is corrected **in place** (the stale statement is rewritten, not merely annotated in `## Verification Notes`) within the run and the loop reaches `confidence_check`.
- `--check` persists `verify_verdict: CLAIMS_OUTDATED` plus a single-line `verify_evidence:` naming each stale claim with its section (`<section>: '<stale>' -> <truth>`) for in-scope `OUTDATED`/`NEEDS_UPDATE`, and `correct_claims` consumes that evidence.
- An `OUTDATED`/`NEEDS_UPDATE` finding whose fix requires changing Summary, Current Behavior, Expected Behavior, Root Cause, Motivation, Steps to Reproduce, or Proposed Solution persists as `NON_VALID`, never `CLAIMS_OUTDATED`, and is never rewritten by `correct_claims`.
- `correct_claims` runs `/ll:verify-issues --auto --from-evidence`, which re-checks and edits only the claims in `verify_evidence` (no full 2A–2E sweep) and makes no edits when `verify_evidence` is absent; a plain `/ll:verify-issues <ID>` run keeps its full-sweep behavior.
- `commands/verify-issues.md` §2E resolves `blocked_by`/`depends_on` target status via frontmatter (`ll-issues show --json`, lowercased), not directory location, and states that an edge to a `done`/`cancelled` target is satisfied and never contributes to a non-VALID verdict — including via `MISSING_BACKLINK`/`DEP_ISSUES` — and that prose calling such a dependency resolved/absent is not a contradiction (asserted by a prose test in `test_enh3250_verify_issues_proposal_vs_code.py`).
- `INVALID` / `RESOLVED` / `DECISIONS_VIOLATION` / `REGRESSION_*` / `DEP_ISSUES` persist as `NON_VALID` and outrank `CLAIMS_OUTDATED`, so they are never routed to auto-correction.
- A second `CLAIMS_OUTDATED` after the one correction attempt terminates via `record_gate_unmet` without re-entering `refine_followup`.
- `ll-loop validate refine-to-ready-issue` passes.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Verification Notes

Verdict at time of check: **NEEDS_UPDATE** (corrections below applied in the same
pass, so the issue as it now reads is up to date — this section is a record of
what was wrong and fixed, not an outstanding action item).

Extensive cross-check against the current codebase (~40+ discrete file/line
citations across `commands/verify-issues.md`, `scripts/little_loops/cli/issues/
{check_verify_verdict,next_obligation,clear_verify_verdict}.py`,
`scripts/little_loops/{preparation_policy,dependency_graph}.py`,
`scripts/little_loops/loops/refine-to-ready-issue.yaml`, three test modules, and
two docs files) confirmed every anchor exact except two minor citation
inaccuracies, both corrected in place:

- **Proposed Solution C**: the `:256-261` line citation for the quoted
  `commands/verify-issues.md` §2E text ("If in completed: note as 'satisfied'...")
  was off by two lines — the quote is at `:263` (with `:261-262` being the
  preceding `## Blocked By` list-item and "in active issues or completed"
  context). Corrected to `:261-263`.
- **Similar Patterns**: `test_completed_blocker_not_added` was attributed to
  `TestGetBlockingIssues`, but it is actually a method of the earlier
  `TestDependencyGraphConstruction` class (lines 128-140); `TestGetBlockingIssues`
  (which does contain `test_completed_blockers_excluded`, lines 333-363) starts
  at line 333. Corrected to attribute each test to its actual class.

Also independently confirmed: the `refine-to-ready-issue-20260927T160415` run
cited in Steps to Reproduce (`ll-loop history refine-to-ready-issue
2026-09-27T160415`) matches exactly — iter 18 `refine_followup` session
`5e0fa7a0…`, iter 23 `verify_issue` session `71473c3f…`, 26 total iterations,
terminating `record_gate_unmet` → `failed`. No active required decision rules
were in effect to check against (`ll-issues decisions list --type rule
--enforcement required --active-only` returned none). `ll-verify-evidence
--json` reported no unverifiable evidence spans.

## Status

**Open** | Created: 2026-09-27 | Priority: P2


## Session Log
- `/ll:confidence-check` - 2026-09-27T19:23:39 - `617b18f3-202b-4610-be95-e3e7537c77c8.jsonl`
- `/ll:verify-issues` - 2026-09-27T19:19:41 - `2c6cabf6-8e36-428f-84cd-fbe8dd7ed1ef.jsonl`
- `/ll:verify-issues` - 2026-09-27T19:13:48 - `77430911-8298-494f-9a26-f51a933d45b2.jsonl`
- `/ll:confidence-check` - 2026-09-27T18:57:47 - `2c6cabf6-8e36-428f-84cd-fbe8dd7ed1ef.jsonl`
- `/ll:verify-issues` - 2026-09-27T18:41:47 - `faf37470-642a-4009-8ad8-fa55667af3ab.jsonl`
- `/ll:wire-issue` - 2026-09-27T18:20:18 - `a542cb1a-fb64-418c-96c1-dffa8cf6d60f.jsonl`
- `/ll:refine-issue` - 2026-09-27T18:07:47 - `45431681-0957-443f-9bca-12828c2ee935.jsonl`
- `/ll:format-issue` - 2026-09-27T18:05:46 - `1bdd3eba-088f-4b15-88f8-1d11e0d8cb3b.jsonl`
- `/ll:capture-issue` - 2026-09-27T17:40:28 - `4759cc5d-e905-4259-b830-49d49c1712bf.jsonl`
