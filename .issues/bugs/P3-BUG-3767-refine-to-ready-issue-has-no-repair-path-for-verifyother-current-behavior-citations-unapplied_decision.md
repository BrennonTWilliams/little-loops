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
verify_verdict: VALID
confidence_score: 85
outcome_confidence: 50
score_complexity: 5
score_test_coverage: 25
score_ambiguity: 10
score_change_surface: 10
risk_factors:
- id: adjacent-repair-paths-overlap
  domain: readiness
  criterion: duplicate_implementations
  description: DIRECTIVE_DRIFT->reconcile and CLAIMS_OUTDATED->correct_claims already
    exist; new route must extend rather than duplicate them.
- id: b8-never-repairs-citations-conflict
  domain: readiness
  criterion: architecture
  description: Option B widening CLAIMS_OUTDATED conflicts with verify-issues B8 'never
    repairs citations' and the BUG-3637 premise-change guard.
- id: pinned-test-and-mirror-fanout
  domain: outcome
  criterion: change_surface
  description: Many doc-contract and topology tests plus four max_steps==113 pins
    and host mirrors break on anchor or step-count changes.
- id: repair-option-unresolved
  domain: outcome
  criterion: ambiguity
  description: Proposed Solution lists Options A/B/C with no Selected decision; route,
    verdict token and unapplied_decision handling all depend on it.
- id: verdict-model-contract-change
  domain: outcome
  criterion: complexity
  description: Per-site change alters the persisted-verdict/route-table contract shared
    by autodev, with fan-in to budgeted states.
- id: wide-integration-surface
  domain: outcome
  criterion: complexity
  description: 16 integration files across loop YAML, verify/reconcile commands, CLI
    classifier, docs and three host mirrors.
size: Large
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

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/loops/refine-to-ready-issue.yaml:16-60` — route-table header comment (line 24 `VERIFY:EVIDENCE_UNVERIFIED, VERIFY:other → check_gate_refine_limit`) must be updated with the route table in `route_pre_score_obligation`; no test pins the comment text [Agent 2 finding]
- `scripts/little_loops/loops/refine-to-ready-issue.yaml:100-153` — `max_steps: 113` rationale comment block (BUG-3637 cycle at 138-144, BUG-3740 at 149-152); add an entry for any new repair cycle, and bump `max_steps` only if the new path adds steps — which breaks four pins (see Tests) [Agent 2 finding]
- `scripts/little_loops/loops/refine-to-ready-issue.yaml:205-223` — counter-seed block in `resolve_issue`: any new per-run budget state must seed its own counter file here (`autodev.yaml` reuses `run_dir` across issues) [Agent 2 finding]
- `scripts/little_loops/loops/refine-to-ready-issue.yaml:1480-1592` — `diagnose` / `write_failure_evidence` capture lists enumerate `check_reconcile_limit` and `check_gate_refine_limit`; add any new capture-bearing budget state by convention [Agent 2 finding]
- `scripts/little_loops/loops/refine-to-ready-issue.yaml:1306` — `record_gate_unmet`'s `check-verify-verdict --directive-drift` probe: only runtime consumer of a `check-verify-verdict` flag; a new persisted verdict would need its own scoped `[GATE_UNMET:*]` signal or an explicit decision to leave it out [Agent 2 finding]
- `commands/verify-issues.md:251-295` — check B8 "Citation findings via format-check (BUG-3708)"; line 272 states B8 "never repairs citations" and is pinned by `TestB8Modes` — Option B (widening `CLAIMS_OUTDATED` to citations) must reconcile with it [Agent 2 finding]
- `commands/verify-issues.md:482-514` — §2.5 `CLAIMS_OUTDATED` persistence bullet (482-499), "Any other verdict → NON_VALID" (500-505) and full verdict precedence (507-514); §4 in-place correction (547-565) and §4.1 frontmatter sync (604-609) repeat the premise-section exclusion [Agent 2 finding]
- `commands/reconcile-issue.md:88-98` — "Preserve untouched" list names `## Current Behavior`; Option A must carve out citation anchors here and extend the `--from-verify-evidence` eligibility sentence (lines 124-139, 214), which gates on `verify_verdict` being exactly `DIRECTIVE_DRIFT` [Agent 2 finding]
- `.gemini/commands/verify-issues.toml`, `.qwen/commands/ll/verify-issues.md`, `.kimi-code/skills/ll-verify-issues/SKILL.md` — host mirrors of `commands/verify-issues.md` (each carries `CLAIMS_OUTDATED` / `Correctable scope`); regenerate with `ll-adapt --host <gemini|kimi-code|qwen> --apply` after any verify-issues edit. No `reconcile-issue` mirror exists [Agent 1 + 2 finding]
- `scripts/little_loops/cli/issues/check_verify_verdict.py:56-94` — `add_check_verify_verdict_parser`: there is no `--claims-outdated` flag today; a new persisted verdict read by `check-verify-verdict` needs its own flag alongside `--directive-drift`, otherwise it is read only via `next-obligation` [Agent 2 finding]
- `scripts/little_loops/cli/issues/__init__.py:163,190` — `ll-issues` epilog help lines for `next-obligation` and `check-verify-verdict`; update only if the token set or exit contract text changes [Agent 1 finding]

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/issues/check_verify_verdict.py:classify_verify_verdict` is shared by `cmd_check_verify_verdict` and `next_obligation._verify_class`; any new token must be handled in both
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` — sole consumer of the `VERIFY:*` token table; `autodev.yaml` reuses the refine loop's run_dir across issues (see `check_verify_retries` comment)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/preparation_policy.py:785` — calls `select_next_obligation()` in `snapshot_issue()` but skips every tier-1 obligation including `VERIFY`, so a new `VERIFY:*` sub-reason can never reach `Facts.obligation_post`; no change needed (note: `obligation_post` comment at ~273) [Agent 1 + 2 finding]
- `scripts/little_loops/cli/issues/__init__.py:804-809` — registers `add_check_verify_verdict_parser` and `add_next_obligation_parser` and dispatches `args.command == "next-obligation"` / `"check-verify-verdict"` in `main_issues()`; imports only, no change unless a subcommand flag is added [Agent 1 finding]
- `scripts/little_loops/cli/issues/clear_verify_verdict.py:cmd_clear_verify_verdict` — removes `verify_verdict` / `verify_evidence` by key name (value-agnostic); a new verdict value or evidence shape needs no change [Agent 2 finding]
- `scripts/little_loops/cli/issues/arm_proposal_revision.py:113` — reads `verify_evidence` only for `PROPOSAL_UNSOUND`; unaffected by a reshaped evidence field for a new verdict [Agent 2 finding]
- `scripts/little_loops/issue_parser.py:directive_gaps` (~4953) — projects only `missing`/`empty`/`boilerplate`/`renamed`; `unapplied_decision` is a blocking `FormatGaps` field but is **not** a FORMAT obligation, so in the loop it can only enter through the persisted `verify_verdict`. Any `unapplied_decision` route must either persist it as `DIRECTIVE_DRIFT` (Option B/C) or add a new discriminator [Agent 2 finding]
- `skills/decide-issue/SKILL.md:437-442` and `skills/decide-issue/reference.md:8` — Phase 7c documents that a non-empty `unapplied_decision_detail` residual is "expected under the bounded-scope rule"; this is the origin of the residue in finding 4, so a repair route must not contradict that rule [Agent 2 finding]
- `skills/confidence-check/SKILL.md:197-207` and `skills/confidence-check/rubric.md:318,326` — cap the outcome score on `unapplied_decision`; this is the downstream effect of leaving the residue unrepaired [Agent 2 finding]

### Similar Patterns
- BUG-3637 `check_claim_correction_budget` -> `correct_claims` (own counter, exhaustion goes straight to `record_gate_unmet`)
- BUG-3695 `VERIFY:DIRECTIVE_DRIFT` -> `check_reconcile_limit` -> `reconcile_issue --from-verify-evidence`
- BUG-3574 `check_proposal_revision_budget` (per-verdict dedicated budget)

### Tests
- `scripts/tests/test_builtin_loops.py` — `PRE_TABLE` route-table assertions (~L3131-3145) and `check_reconcile_limit` / `check_gate_refine_limit` budget tests (~L1680-1760)
- `scripts/tests/test_ll_issues_next_obligation.py` — token emission for any new `VERIFY:*` sub-reason

_Wiring pass added by `/ll:wire-issue`:_

Existing tests to update (new `VERIFY:*` token / reroute):
- `scripts/tests/test_builtin_loops.py:3132-3146` — `PRE_TABLE` is compared whole by `TestRefineToReadyDispatch.test_pre_score_routing_table` (L3196/3200); update the `"VERIFY:other"` entry and any new token [Agent 2 + 3 finding]
- `scripts/tests/test_builtin_loops.py:3170-3177` — hardcoded `sub["VERIFY"]` list in `TestRefineToReadyDispatch._tokens`; `test_dispatch_tokens_are_complete` (L3214) fails if the selector emits a token missing from the route table [Agent 2 + 3 finding]
- `scripts/tests/test_ll_issues_next_obligation.py:64-109` — `TestVerify.test_classifier` and `test_sub_reasons` parametrize rows (incl. `("NON_VALID", "other")`, `expected = "other" if verdict == "NON_VALID" else verdict`) need a row per new token; `TestYamlParity.test_tier1_dispatch_covers_selector_tokens` (~L371) in `TestYamlParity` [Agent 2 + 3 finding]
- `max_steps == 113` is pinned in four tests — `scripts/tests/test_builtin_loops.py:1884` in `TestRefineToReadyIssue`-adjacent budget test, `scripts/tests/test_autodev_proof_reentry.py:131`, `scripts/tests/test_bug3695_directive_drift_repair.py:292` in `test_route_table_budget_and_step_cap_unchanged`, `scripts/tests/test_advise_ready_gate.py:216` in `test_max_steps_113`; all break if a `max_steps` bump is needed [Agent 2 + 3 finding]
- `scripts/tests/test_bug3695_directive_drift_repair.py:281-292` — `TestFlagReachesOnlyReconcileIssue.test_route_table_budget_and_step_cap_unchanged` pins `check_reconcile_limit` `on_yes`/`on_no`/`target == 2` and `reconcile_issue.next == "normalize_structure"`; Option A adds fan-in to `check_reconcile_limit`; `test_reconcile_issue_alone_has_flag` (L269) asserts only `reconcile_issue` carries `--from-verify-evidence` [Agent 3 finding]
- `scripts/tests/test_builtin_loops.py:2776-2819` — `test_proposal_revision_cycle_routing` asserts `check_reconcile_limit.on_yes == "reconcile_issue"` and that nothing but `check_proposal_revision` routes to `reconcile_revision` [Agent 2 finding]
- `scripts/tests/test_bug3708_verify_issues_b8.py:126-150` — `TestB8Modes.test_check_and_from_evidence_behavior` asserts `"never repairs citations"` (L130); `test_context_section_is_ruled_outside_correctable_scope` slices from `**Correctable scope for \`CLAIMS_OUTDATED\`` to `#### E. Validate Dependency` — both break if Option B moves/rewords the anchors [Agent 2 + 3 finding]
- `scripts/tests/test_enh3250_verify_issues_proposal_vs_code.py:128-207` — `TestClaimsOutdatedVerdict`: `test_correctable_scope_rule_excludes_premise_sections` (all seven section names incl. `Current Behavior` must remain), `test_persistence_states_full_precedence_order` (`` `CLAIMS_OUTDATED` > `PROPOSAL_UNSOUND` `` substrings must survive a precedence edit), `test_persistence_carves_out_claims_outdated_with_evidence` [Agent 2 + 3 finding]
- `scripts/tests/test_bug3695_directive_drift_repair.py:423-442` — `TestVerifyIssuesB6AndPersistence.test_drift_branch_persists_verdict_and_evidence_together` slices from the `DIRECTIVE_DRIFT` bullet to the literal `CLAIMS_OUTDATED verdict (BUG-3637)` bullet; inserting a bullet between them breaks the slice [Agent 3 finding]
- `scripts/tests/test_bug3753_historical_verification_notes.py:141-148` — `TestCommandAndLoopPins.test_loop_reentry_topology_and_single_attempt_budget` pins `check_claim_correction_budget` (`on_yes` → `correct_claims`, `on_no` → `record_gate_unmet`, target 2) and `correct_claims.next → normalize_structure` (Option B reuse) [Agent 2 + 3 finding]
- `scripts/tests/test_bug3695_directive_drift_repair.py:300-386` — `TestReconcileFlagContract.test_additions_scope_and_boundaries` and `TestBug3726ContextOnlyTriage` slice `reconcile-issue.md` by heading/contract strings; relevant only if Option A widens reconcile scope to Current Behavior [Agent 3 finding]
- `scripts/tests/test_reconcile_issue_command.py` — `TestReconcileScopeBoundariesEligibility` requires the `Preserve untouched` literal under `## Contract (read this first`; keep it when editing line 88 [Agent 2 finding]
- `scripts/tests/test_wiring_reference_docs.py:280-290` — pins the `#### \`ll-issues next-obligation\`` heading and `OBLIGATION[:sub_reason]` text in `docs/reference/CLI.md`, the `API.md` row, and the `LOOPS_REFERENCE.md` "Typed run record (ENH-3597)" anchor; preserve them in doc edits [Agent 2 finding]

New tests to write (patterns to follow):
- Real-child scenario via `run_refine_to_ready` (`scripts/tests/autodev_harness.py:1103`) modeled on `test_bug3695_directive_drift_repair.py:TestRealChildRepairRouting.test_drift_repaired_within_one_reconcile` (L88-120): BUG-3762-shaped verdict → scripted repair → `VALID`, assert `"record_gate_unmet" not in r.path` [Agent 3 finding]
- Exhaustion scenario modeled on `TestRealChildExhaustion` (L140-170) — no real-child test covers the `VERIFY:other` → `check_gate_refine_limit` → `refine_followup` → `record_gate_unmet` path today [Agent 3 finding]
- Premise-change scenario asserting a Current Behavior premise change stays `NON_VALID` and routes to `check_gate_refine_limit` (AC 2) [Agent 3 finding]
- Topology pin in the style of `test_bug3753_historical_verification_notes.py:test_loop_reentry_topology_and_single_attempt_budget` for any new budget state, plus a counter test in the style of `test_builtin_loops.py:_run_counter_state` (L1698) / `test_check_reconcile_limit_counts_up_and_gates_at_two` (L1904) [Agent 3 finding]
- Doc-contract tests in the `test_enh3250_verify_issues_proposal_vs_code.py:TestClaimsOutdatedVerdict` style (slice between `Persist the verdict to frontmatter` and `### 3. Request User Approval`, whitespace-flattened) for any new verdict row, persistence bullet, or narrowed correctable-scope text [Agent 3 finding]
- CLI exit-code test in the style of `test_ll_issues_check_verify_verdict.py:TestCheckVerifyVerdictClaimsOutdated.test_claims_outdated_verdict_exits_one` (L172-180) if `check_verify_verdict.py` gains a flag [Agent 3 finding]

### Documentation
- `docs/guides/LOOPS_REFERENCE.md` — documents the `VERIFY:other` route
- `commands/verify-issues.md` verdict docs (also listed under Files to Modify)

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_REFERENCE.md:146-158` — token routing table in `Claim-verification gate chain (ENH-3031, ENH-3604)`; line 156 groups `VERIFY:other` with `VERIFY:EVIDENCE_UNVERIFIED` and `DESIGN` → `check_gate_refine_limit`, lines 153-154 hold the `DIRECTIVE_DRIFT` / `CLAIMS_OUTDATED` rows; add a row for any new token and split `VERIFY:other` out if its route changes. Paragraphs at ~160 and ~196 (claim-verification failure split by which section must change) describe the budget and repair split and need a matching edit [Agent 1 + 2 finding]
- `docs/reference/CLI.md:2458` — `VERIFY` `sub_reason` list in `ll-issues next-obligation` (pre-score gates); also line 2464 token examples and 2471 "`VERIFY` reflects the last persisted `verify_verdict`" [Agent 1 + 2 finding]
- `docs/reference/CLI.md:2652` — non-VALID umbrella sentence and flag rows (2661-2662) in `ll-issues check-verify-verdict`; update if a new persisted verdict or flag is added [Agent 1 + 2 finding]
- `docs/reference/CLI.md:2761` — `format-check` gap-key list (and JSON example ~3038) in `ll-issues format-check`; touch only if `unapplied_decision` classification or severity changes [Agent 2 finding]
- `docs/reference/COMMANDS.md:305` — `/ll:reconcile-issue` row naming `--from-verify-evidence` and its `DIRECTIVE_DRIFT` eligibility; update if the eligibility widens (Option A) [Agent 1 + 2 finding]
- `docs/reference/API.md:1475,4755,7637` — `next-obligation` rows; sub-reasons are not enumerated, so no edit needed unless the rows begin enumerating them [Agent 2 finding]
- `CHANGELOG.md` — add the entry under a concrete `## [X.Y.Z]` section during release prep, not `[Unreleased]` [Agent 2 finding]

### Configuration
- N/A

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/config-schema.json` and frontmatter validators — verified no `verify_verdict` allow-list exists; `classify_verify_verdict` is the sole enumeration (unlisted values fall to `other`), so no schema change is needed [Agent 2 finding]

### Prior Art (not wiring)
_Wiring pass added by `/ll:wire-issue`:_
- ENH-3690 (cancelled as superseded by BUG-3708) already proposed a citation-only repair route and was closed on the premise that B8 makes citation findings verdict-neutral; BUG-3767's observed run contradicts that for a stale line/symbol citation *inside Current Behavior* (`:266`, `:391`). Any option must state why B8's demotion did not apply here (the `examined_refs` entries for `raw_redaction.py:266` report `line_in_range: ok`, so the staleness is a content/premise judgment B8 explicitly leaves to the model) [Agent 1 + 2 finding]

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

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Update `scripts/little_loops/loops/refine-to-ready-issue.yaml` — route table in `route_pre_score_obligation`, header comment (~L24), `max_steps` rationale block (~L100-153), and, for any new budget state, its counter seed in `resolve_issue` (~L205-223) and the capture lists in `diagnose`/`write_failure_evidence` (~L1480-1592)
- Update `commands/verify-issues.md` — §2C table/correctable scope, §2.5 persistence + precedence (~L482-514), §4/§4.1, and reconcile with check B8's "never repairs citations" (L272) under Option B
- Update `commands/reconcile-issue.md` — "Preserve untouched" (L88) and `--from-verify-evidence` eligibility (L124-139, L214) under Option A; keep the `Preserve untouched` literal that `test_reconcile_issue_command.py` requires
- Regenerate host mirrors after any `commands/verify-issues.md` edit — `ll-adapt --host <gemini|kimi-code|qwen> --apply` (`.gemini/commands/verify-issues.toml`, `.qwen/commands/ll/verify-issues.md`, `.kimi-code/skills/ll-verify-issues/SKILL.md`)
- Update `scripts/little_loops/cli/issues/check_verify_verdict.py` (`classify_verify_verdict`, `add_check_verify_verdict_parser` flag if a new persisted verdict) and `next_obligation.py` (`_verify_class`) only if a new token is introduced; `preparation_policy.snapshot_issue` needs no change (it skips VERIFY)
- Decide the `unapplied_decision` path explicitly: it is not a FORMAT obligation (`issue_parser.directive_gaps` omits it), so it can reach repair only via a persisted verdict — persist it as `DIRECTIVE_DRIFT` (existing `reconcile_issue --from-verify-evidence` route) or add a discriminator; keep consistent with `skills/decide-issue/SKILL.md` Phase 7c's bounded-scope residual rule
- Update tests — `PRE_TABLE` and `_tokens()` VERIFY list in `test_builtin_loops.py`; `TestVerify` parametrize rows in `test_ll_issues_next_obligation.py`; the four `max_steps == 113` pins if the cap changes; B8/`CLAIMS_OUTDATED` doc-contract tests (`test_bug3708_verify_issues_b8.py`, `test_enh3250_verify_issues_proposal_vs_code.py`, `test_bug3695_directive_drift_repair.py`) if verify-issues anchors move
- Add new tests — real-child scenario (`run_refine_to_ready`) reaching `VALID` without `record_gate_unmet`; a premise-change scenario staying `NON_VALID`; topology/counter pins for any new budget state
- Update docs — `docs/guides/LOOPS_REFERENCE.md` (L146-158 route table, L156 `VERIFY:other` row, ~L196 split paragraph), `docs/reference/CLI.md` (L2458 `sub_reason` list, L2652/2661-2662 `check-verify-verdict`), `docs/reference/COMMANDS.md` (L305) while preserving strings pinned by `test_wiring_reference_docs.py`
- Verify with `ll-loop validate refine-to-ready-issue` and run the scoped suites above plus `test_wiring_skills_and_commands.py`

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

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-10-06_

**Readiness Score**: 85/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 50/100 → LOW

### Concerns
- Proposed Solution is still "Decision needed" (Options A/B/C, no `> **Selected:**`); the discriminator token, route target and `unapplied_decision` handling all hinge on it. Run `/ll:decide-issue BUG-3767` first.
- Option B (widen `CLAIMS_OUTDATED`) contradicts verify-issues B8's "never repairs citations" (pinned by `TestB8Modes`) and the BUG-3637 premise-change guard; the issue must state why B8's demotion did not apply to the BUG-3762 citations.
- Existing repair paths (`DIRECTIVE_DRIFT` -> `reconcile_issue`, `CLAIMS_OUTDATED` -> `correct_claims`) overlap; the fix should extend them, not add a parallel path.

### Outcome Risk Factors
- Unresolved design decision (Options A/B/C) leaves several judgment calls open.
- Broad enumeration across ~16 sites (loop YAML, verify/reconcile commands, CLI classifier, docs, three host mirrors) with moderate-to-deep per-site complexity: the persisted-verdict/route-table contract is shared by autodev and fans into budgeted states.
- Wide pinned surface: four `max_steps == 113` pins, topology/doc-contract tests and host mirrors break on any anchor or step-count change.

### Risk Factor Delta
- Baseline: none recorded

## Session Log
- `/ll:confidence-check` - 2026-10-07T01:31:37 - `e18126dd-317b-417c-86ac-4401ea214536.jsonl`
- `/ll:verify-issues` - 2026-10-07T01:29:30 - `b059f0e8-765a-45cb-b2ac-1828f56d58b5.jsonl`
- `/ll:wire-issue` - 2026-10-07T01:27:14 - `ce6bd152-644a-4781-8ad3-92fcd1e54a6a.jsonl`
- `/ll:refine-issue` - 2026-10-07T01:17:50 - `67f77c85-f910-4236-837b-e92f1170426b.jsonl`
- `/ll:format-issue` - 2026-10-07T01:16:48 - `7610b26f-db95-4e3a-b048-687107034721.jsonl`
- `/ll:capture-issue` - 2026-10-07T01:12:58 - `26bbdec0-accc-4f17-94d6-3d59f60b2e3f.jsonl`
