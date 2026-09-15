---
id: ENH-3465
title: Benchmark every self-improvement candidate against a frozen external baseline, not only the incumbent
type: ENH
priority: P4
status: open
discovered_date: '2026-09-13'
labels:
- evaluation
- apo
- regression
parent: EPIC-3475
epic: EPIC-3475
---

## Summary

Every improvement comparison `ll-harness` can make today is incumbent-relative. `--compare-baseline` (ENH-3435) measures a candidate against the unmutated HEAD content of the same target, and `harness-optimize.yaml` scores each iteration against a `baseline` captured at the start of *that run*. Neither holds a reference that survives across runs: once a run commits its winner, the next run's incumbent *and* its run-start baseline are both that winner. A lineage where each run genuinely beats the previous run's winner can therefore drift away from any fixed standard while every comparison still passes — the cross-run regression is invisible because nothing outside the lineage is ever re-measured.

The guard is structural: a candidate is measured against two opponents — the incumbent (is the lineage still improving?) and a **pinned** baseline whose content identity is fixed at pin time and never re-derived from HEAD (is the lineage still ahead of a fixed reference?). Each comparison is three-valued (`ahead` / `behind` / `inconclusive`, decided from the Wilson CIs `ll-harness` already computes), and the pair is reported as one named outcome. Because sampled pass rates are noisy, `ahead` of the incumbent but `behind` the pin is a reachable, reportable state — and it is the signal that the lineage has drifted below its anchor.

## Current Behavior

- `ll-harness <runner> --compare-baseline` (`cli/harness.py:1855`, `_run_compare_arm()`) reports exactly one delta, against `baseline_for()` rows keyed on the HEAD content hash (`_incumbent_content_hash()`, `:1682`) or an explicit `--baseline-of` attempt. There is no second arm and no way to name a reference other than "current HEAD" or "one prior attempt".
- `harness-optimize.yaml` captures `baseline` once per run (`baseline_score` state, `:111-117`) and ENH-3421's `reference:` (`gate` state, `:199`) blocks any iteration that regresses below it — so drift *within* a run is already blocked. But `${captured.baseline}` lives in the per-run context: the next run re-captures it from the freshly committed HEAD, so across runs the reference rolls forward with the lineage.
- No comparison result anywhere is three-valued: `BaselineDelta.delta` is a raw rate difference or `None` (`cli/harness.py:1559-1574`), with no notion of an inconclusive result despite both tallies carrying Wilson CIs.

## Expected Behavior

- A target can carry a **pin**: a recorded content hash of that target (plus HEAD SHA, timestamp, reason) that is written only by an explicit CLI verb and never recomputed from HEAD.
- When a pin exists for the target, `ll-harness <runner> --compare-baseline` reports **two arms**: the existing incumbent arm and a frozen arm resolved by calling `baseline_for()` with the pinned content hash under the current conditions. Each arm is classified `ahead` / `behind` / `inconclusive` by CI comparison, and the pair is reported as one named outcome in both the text and `--json` reports.
- The exit code is unchanged (still the candidate tally's banding alone); the dual outcome is report content, exactly as `delta` is today. The only new refusal is fail-closed: a pin that exists but has no full-n matching rows under current conditions refuses before any subject invocation with an actionable message (measure the pinned content first), mirroring `_compare_baseline_refusal()`.
- Re-pinning is refused unless the proposed new pin has a measured pass rate at or above the current pin's under matching conditions; pin history is append-only.

## Scope Boundaries

- **In scope**: the pin record and its CLI verb, the second arm in `ll-harness --compare-baseline`, the three-valued classification, the widened `BaselineDelta`/report/JSON shape, docs and tests.
- **Out of scope (follow-up issue)**: wiring the dual outcome into any loop's routing (`harness-optimize.yaml` or otherwise) and deciding what a loop *does* on `ahead`/`behind`. This issue makes the signal exist and be durable; consuming it is a separate change with its own MR-lint implications.
- **Out of scope**: any change to `evaluate_convergence()`'s `reference` field or the FSM evaluator layer (see D1).
- **Out of scope**: `evaluate_comparator()`'s `.loops/baselines/` file mechanism — unrelated and unwired; left untouched.

## Design

This is a different axis from the evaluator-hardening siblings in EPIC-3475 (ENH-3462/ENH-3463 keep the *measuring instrument* honest); this keeps the *subject* honest by pinning a permanent second opponent.

Complements the unmutated baseline arm shipped as ENH-3435, and is a different thing: that baseline is a control arm measured inside a single harness run (it answers "did this change help relative to no change"); this issue's baseline is a standing external opponent for the lineage (it answers "is the lineage still ahead of a fixed reference"). A run that has both can distinguish a change that helps from a lineage that is drifting.

### Decisions

- **D1 — Layer: `ll-harness` CLI, not the FSM evaluator.** The epic is "Harden ll-harness Verdicts"; `--compare-baseline` is wired into no loop or skill today, so there is no consumer to break; and the ENH-3421 decision record (`.ll/decisions.d/a2c57916-…`) already rejected stacking a second FSM-layer check on `harness-optimize.yaml`'s `gate` for cost and single-`evaluate`-per-state reasons. No `EvaluateConfig` field is added, so MR-2's `_has_baseline_reference` allowlist and `EvaluateConfig`'s `to_dict`/`from_dict`/docstring/API.md mirror are **not** touched.
- **D2 — The frozen baseline is pinned *content*, re-measured, not a stored score.** A stored number goes stale the moment the scorer, task set, judge model, or conditions change. The pin records `target_content_hash` (the HEAD blob hash at pin time, same `_hash_bytes` as `_incumbent_content_hash()`) plus `pinned_head_sha`, `pinned_at`, `reason`. The frozen arm's rate always comes from `harness_events` rows under the *current* `conditions_fp`.
- **D3 — Reuse `baseline_for()`; do not add a second store.** `baseline_for()` keys on whatever `target_content_hash` the caller passes. Passing the pinned hash instead of HEAD's yields the frozen arm, with the reader's existing full-n / conditions-fp / authoritative-rows guarantees and caching for free (rows measured on the pinned content are reused until conditions change). The earlier finding that "neither existing mechanism has a key component set at freeze time" is correct about the *callers*, not the reader: the pin record supplies that component. This supersedes the earlier Program Design line calling for a "new frozen-external-baseline record distinct from `BaselineResult`" — the only new type is the pin, and the frozen arm *is* a `BaselineResult`.
- **D4 — Each comparison is three-valued, from Wilson CIs.** `ahead` if the candidate's CI lower bound exceeds the arm's CI upper bound; `behind` if the candidate's upper bound is below the arm's lower bound; else `inconclusive`. With a scalar transitive score, "beats incumbent but loses to pin" would imply the incumbent was already below the pin; the outcome is meaningful only because sampled rates are interval-valued. `paired_direction()` (`stats.py:43-79`) is the vocabulary precedent for naming an inconclusive result, but it needs paired per-item outcomes that `ll-harness` repetitions don't have, so CI-overlap on the two independent proportions is used instead. Vocabulary lives as a string-tuple constant + helper (the `fsm/verdicts.py` convention), in `cli/harness.py`.
- **D5 — Named pair outcome.** The pair `(vs_incumbent, vs_pin)` is reported verbatim as two fields plus one derived `outcome` label: `drift` when `vs_incumbent == "ahead"` and `vs_pin == "behind"`; `regression` when `vs_pin == "behind"` otherwise; `improvement` when both are `ahead`; `inconclusive` otherwise (name follows the `q_high_low`-style bucket precedent in `cli/issues/impact_effort.py:194-211`). `drift` is the lineage-local-optimum signal this issue exists to surface.
- **D6 — Pinning is explicit, monotone, and append-only.** New CLI verb `ll-harness pin-baseline <runner> <target> [--reason …]` writes the pin from HEAD content. Never automatic (contrast `EvaluateConfig.auto_promote`, whose rolling overwrite is the drift shape this issue guards against). Re-pinning is **refused** unless `baseline_for()` finds a full-n measurement of the new content under the current conditions with a pass rate ≥ the current pin's under the same conditions (or `--force`, which is logged in the pin's `reason`). The pin file holds a `pins: [...]` list; the last entry is active, earlier entries are never deleted. Storage: `.ll/harness-pins/<runner>--<target-slug>.json`, committed (like `.ll/decisions.d/`), not `.loops/` (per-machine).
- **D7 — Pin absent ⇒ single-arm behaviour unchanged.** No pin means today's one-delta report, byte-for-byte for the existing keys; `test_delta_json_payload` etc. keep passing. The dual shape is additive (`baseline.vs_incumbent`, `baseline.frozen`, `baseline.vs_pin`, `baseline.outcome`), never a rename of existing keys.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-14 — based on codebase analysis:_

- Two independent "frozen reference" mechanisms already exist in this codebase, neither of which is the standing lineage opponent this issue proposes: (1) `evaluate_convergence()`'s `reference` field (`fsm/schema.py:132`, `fsm/evaluators.py:438-496`, ENH-3421, status done) — captured once outside `harness-optimize.yaml`'s iterate cycle (`baseline_score` state), checked before the target-reached branch, fails closed on an unresolvable value, and folds a regression into the existing `stall` verdict rather than a distinct outcome; wired into exactly one loop (`harness-optimize.yaml`), explicitly not `rl-coding-agent.yaml`. (2) `evaluate_comparator()`'s `.loops/baselines/<loop>/output.txt` file (`fsm/evaluators.py:1636-1702`, `EvaluateConfig.auto_promote`/`baseline_path`) — a literal file surviving across all future runs until re-pinned via `ll-loop promote-baseline` (`cli/loop/info.py:1256`) or, with the default `auto_promote: true`, overwritten on every winning candidate — the same rolling-drift shape a frozen baseline is meant to guard against. ENH-3421's own prior research states explicitly: no shared "frozen-capture" primitive exists between these two.
- `BaselineKey`/`baseline_for()` (ENH-3435) is a content-identity-keyed rolling cache, not a permanently-pinned record: `baseline_for()`'s match query explicitly ignores `head_sha` (`test_ignores_head_sha_and_cell_key`, `test_history_reader_harness.py:578-598`), so a baseline row simply stops matching — with no explicit invalidation step — the moment `target_content_hash` changes. This confirms this section's own distinction that ENH-3435's baseline is not a standing external opponent.
- No "self-improvement lineage" (successive wrapper drafts, plan-scoring rubrics judged against their own dimensions) exists as a named implementation anywhere in the codebase — a repo-wide unfiltered search for `lineage`, `wrapper.?draft`, `plan_scoring`/`plan-scoring` returns zero code hits; these terms appear only in this issue's own prose. The nearest structural analogue found is `harness-optimize.yaml`'s rolling `prev_score`/`capture_prev` incumbent comparison (a hill-climbing loop, not a multi-candidate lineage).
- A different, unrelated "frozen" concept already exists and should not be conflated: `ENH-1122` ("Frozen-Boundary Convention", status deferred) is a byte-region edit-mutation guard (`<!-- ll:frozen -->` markers restricting which lines `harness-optimize` may edit), not an evaluation-reference concept. ENH-3421's own issue text makes this same distinction explicitly.
- The "epoch-bounded objective versioning" / "versioned evaluator prompts over golden sets" work this section contrasts itself against (as "keeping the measuring instrument honest") has no locatable implementation under those names either — zero repo-wide hits for `epoch-bounded`, `objective_version`, or a golden-set evaluator-hardening concept distinct from `test_adapt_golden_corpus.py`'s unrelated host-adapter snapshot fixtures.

_Added by `/ll:refine-issue` — 2026-09-14 — based on codebase analysis:_

- Anchor relocation (verify-issues, 2026-09-14): `scripts/little_loops/cli/harness.py` shifted ~35 lines since these findings were recorded (`feat(harness): score ll-harness runs on a named efficiency vector`, 80d2d38d0) and `scripts/little_loops/history_reader/harness.py`/its test file shifted independently. Corrected below via `ll-code defines`; substance of every finding is unaffected.
- Correction: `EvaluateConfig.auto_promote`'s dataclass default is `False` (`scripts/little_loops/fsm/schema.py:141`, `auto_promote: bool = False`), not `True`. This section's earlier "with the default `auto_promote: true`" language describes what happens when a loop author sets it true (the drift risk this issue flags), not the schema's own default value.
- Verbatim rationale from `.ll/decisions.d/a2c57916-aa1c-48db-86ad-cf1c3964d62d.json` (ENH-3421, 2026-09-09, category: architecture), confirming the prior rejection of the design shape closest to this issue's own four-way-outcome proposal: "Direct precedent (ENH-3224 abstain_on_exit_3 field-threading), free MR-14 lint coverage via evaluate_config_known_fields(), and baseline_score already sits outside the iterate cycle so no new executor primitive is needed. Option B is not directly buildable as described: StateDef.evaluate is single-valued per state, forcing a second chained state with a disjoint route vocabulary and zero shipped precedent, plus stacks LLM cost onto an already LLM-heavy loop."
- No structural test enforces "captured exactly once" for the `evaluate_comparator()`/`baseline_path`/`auto_promote` file-based mechanism, unlike `evaluate_convergence()`'s `reference` (which has `test_only_baseline_score_captures_baseline`, `test_harness_optimize.py:140-148`) — an asymmetry between the two existing "frozen reference" mechanisms worth noting if this issue's new mechanism is expected to carry the same structural guarantee.
- Confirmed `BaselineDelta` (`cli/harness.py:1559-1574`) remains the sole comparison-result dataclass anywhere in the codebase; a repo-wide search for `beats_incumbent`/`beats_baseline`/`four.way`/`dual.outcome` finds zero code hits (only coincidental substring matches inside `.issues/*.md`) — no existing shape to extend for a four-way outcome.
- Re-confirmed the `convergence_gate` fragment's consumer set is unchanged from the prior wiring pass: `rl-bandit.yaml` (direct `type: convergence`), `test-coverage-improvement.yaml`, `agent-eval-improve.yaml`, `rl-policy.yaml`, `rl-coding-agent.yaml` (all via `fragment: convergence_gate`).

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-14 — based on codebase analysis:_

Confirmed file paths and call sites for the two existing baseline/reference mechanisms this issue's frozen-external-baseline record must integrate alongside without conflating.

_Added by `/ll:refine-issue` — 2026-09-14 — based on codebase analysis:_

- A two-independent-boolean-axis outcome (impact×effort) is combined into one of four named buckets via an `if/elif/elif/else` chain in application code, not a single dataclass field — evidence: `cli/issues/impact_effort.py:194-211` (`q_high_low`/`q_high_high`/`q_low_low`/`q_low_high`). No FSM-evaluator-layer precedent for combining 2+ independent comparison results into one reportable value exists; `BaselineDelta` (`cli/harness.py:1559-1574`) remains single-reference.
- A non-binary comparator verdict already exists one layer up: `evaluate_comparator()` returns `"yes"`/`"no"`/`"tie"`/`"no_baseline"` (`fsm/evaluators.py:1646,1663,1683-1688`) — the evaluator layer's verdict vocabulary is not constrained to pass/fail.
- The one direct precedent for "two independent signals disagreeing" sits in the statistical layer, not the FSM-evaluator layer: `paired_direction()` (`stats.py:43-79`) names disagreement as a first-class quantity (`discordant = b+c`) and resolves it to a distinct `"inconclusive"` outcome when a Wilson CI straddles 0.5, otherwise a directional winner — consumed by `cli/loop/summary.py:105-117`. Elsewhere, "disagree"/"conflicting" language in the codebase only asserts two things structurally cannot disagree (single source of truth), never a runtime disagreement verdict.
- When multiple call sites need one verdict vocabulary, the convention is a shared module of string-tuple constants plus a predicate helper, not independent per-site enums — evidence: `fsm/verdicts.py` (`DEFAULT_VERDICT_ENUM`, `is_abstention_verdict`), created specifically because three schemas had previously disagreed on verdict counts. Non-LLM evaluators like `convergence`/`comparator` do not use this shared vocabulary today — their verdict strings are declared inline at each `elif eval_type ==` branch.
- Re-pinning a stored value happens two ways in this codebase for the same file (`.loops/baselines/<loop>/output.txt`): an explicit CLI verb (`ll-loop promote-baseline` → `cmd_promote_baseline()`, `cli/loop/info.py:1256-1308`) and an implicit auto-overwrite gated by a boolean config field (`EvaluateConfig.auto_promote`, defaulting to `False`) inside `evaluate_comparator()` (`fsm/evaluators.py:1690-1691`). No `frozen=True` dataclass anywhere in the codebase pairs with a separate "unfreeze"/re-pin constructor — `frozen=True` is used only for identity/match-key hashability (e.g. `BaselineKey`), never for a write-once value with an audit trail.
- Extending the evaluator dispatch table with a new outcome (the `convergence` case is the direct precedent) touches five sites, not one: the `elif eval_type ==` branch itself, an `_EXIT_CODE_AWARE_EVALUATORS` allowlist entry if non-zero exit codes need custom handling, a companion `EvaluateConfig` field's four manual touch points (docstring, `to_dict`, `from_dict`, and MR-2's `_has_baseline_reference` candidates list), and a structural test asserting the field on the parsed loop-YAML dict directly (no JSON Schema layer exists for `EvaluateConfig`).

### Files to Modify
- `scripts/little_loops/cli/harness.py` — `BaselineDelta` (`:1559-1574`, additive widening), `_run_compare_arm()` (`:1855`, `frozen=` parameter), `_report_samples()` (`:1405`, render the second arm), the four `cmd_skill`/`cmd_cmd`/`cmd_mcp`/`cmd_prompt` compare branches (`:2292-2662`, `read_pin()` + second refusal), new `BaselinePin`/`read_pin`/`write_pin`/`_arm_verdict`/`_pair_outcome`/`cmd_pin_baseline` and the `pin-baseline` subparser registration
- `scripts/little_loops/history_reader/harness.py` — `BaselineKey`/`BaselineConditions`/`BaselineResult`/`baseline_for()` (`:250-404`) — **read-only dependency, no change** (D3: the frozen arm is `baseline_for()` called with the pinned hash)
- `scripts/little_loops/fsm/validation/meta_rules.py` — **not touched** under D1 (no `EvaluateConfig` field is added, so MR-2's `_has_baseline_reference()` allowlist at `:581-596` is unaffected)
- `.ll/harness-pins/` — new committed directory for pin files (D6)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/harness.py:30`, `scripts/little_loops/history_reader/__init__.py:184` — importers of `history_reader/harness.py`
- `scripts/tests/test_history_reader_harness.py` `TestBaselineFor::*` (lines 506-693), `scripts/tests/test_cli_harness.py` `TestBaselineStoreBidirectional`/`TestBaselineDegrade` (`:3449`,`:3520`) — existing callers of `baseline_for()` a new frozen-record type must not break
- `scripts/little_loops/loops/harness-optimize.yaml` `gate` state (`:191`) — the one shipped loop wired to ENH-3421's `reference` field; `rl-coding-agent.yaml` explicitly excluded by that issue despite the same rolling-`previous` shape

_Wiring pass added by `/ll:wire-issue`:_
- `.ll/decisions.d/a2c57916-aa1c-48db-86ad-cf1c3964d62d.json` — a decision record from ENH-3421 titled "Option A: frozen-reference field on `EvaluateConfig`/`evaluate_convergence()`", rejecting "Option B: wire `check_comparator` into `harness-optimize.yaml`'s `gate` state as a second required check" — direct prior art on the exact design tradeoff this issue revisits; confirms `rl-coding-agent.yaml`'s exclusion was a deliberate 2026-09-09 review decision (`.issues/enhancements/P3-ENH-3421-*.md:146,177,291,464,482,517,575,604,624`), not an oversight
- `scripts/little_loops/loops/lib/common.yaml:151-164` (the `convergence_gate` fragment definition, documenting `evaluate.reference` as "a frozen baseline that must not advance across iterations"), and its consumers `rl-bandit.yaml` (direct `type: convergence`, not via fragment), `test-coverage-improvement.yaml`, `agent-eval-improve.yaml`, `rl-policy.yaml`, `rl-coding-agent.yaml` (all `fragment: convergence_gate`) — every loop reachable from the existing `evaluate_convergence()` reference mechanism, beyond `harness-optimize.yaml` alone
- Confirmed `type: comparator` has zero hits in any shipped loop YAML under `scripts/little_loops/loops/` — `evaluate_comparator()`'s standing-file mechanism is not wired into any loop today, only documented in `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` as a worked example
- `scripts/little_loops/cli/loop/__init__.py` (`cmd_promote_baseline` import/registration/dispatch, lines 40,79,901,904,1119-1120), `scripts/tests/test_ll_loop_commands.py:7519-7589`, `test_ll_loop_execution.py:1853`, `test_ll_loop_integration.py:515`, `test_cli_loop_dispatch.py:510` — the `ll-loop promote-baseline` command surface for the other existing frozen mechanism, relevant if this issue's re-pinning UX is modeled on it
- `scripts/tests/test_verify_evidence.py::TestBaselineKeying` (`:1104`), `scripts/tests/test_cli_loop_dispatch.py::test_baseline_forwarded` (`:803`) — additional test-side callers of `BaselineKey`/`baseline_for()` beyond `TestBaselineFor`

### Conventions in Force
- A field that must stay frozen (never re-captured) is enforced structurally, checked by a dedicated test that scans every other state for the forbidden capture — evidence: `test_only_baseline_score_captures_baseline` (`test_harness_optimize.py:140-148`), asserting no state but `baseline_score` sets `capture: baseline`
- A frozen reference fails *closed* on an unresolvable value while a rolling/incumbent reference fails *open* (absent means "first iteration, no check") — evidence: `evaluate_convergence()`'s handling of `reference` vs. `previous` (ENH-3421 Expected Behavior §4)
- Two independently-built "capture once, keep fixed" mechanisms already coexist with no shared primitive between them — evidence: ENH-3421's own confirmed research stating no shared "frozen-capture" primitive, decorator, or field type exists anywhere in `scripts/little_loops/`
- A comparison-result dataclass reports one delta against one reference (`candidate, baseline, delta, source, head_sha_differs`), never a multi-reference outcome — evidence: `BaselineDelta` (`cli/harness.py:1559-1574`)

### Tests
- `scripts/tests/test_harness_optimize.py:125-156` — structural YAML-dict assertions for ENH-3421's frozen-reference wiring (`test_gate_has_convergence_evaluator`, `test_only_baseline_score_captures_baseline`, `test_trajectory_lines_include_baseline`)
- `scripts/tests/test_cli_harness.py:3081-3239` (`TestBaselineCompare`) — end-to-end CLI tests for the existing delta/outcome shape (`test_delta_reported_with_provenance`, `test_delta_json_payload`, `test_delta_null_when_candidate_ungraded`)
- `scripts/tests/test_history_reader_harness.py` (`TestBaselineFor`) — reader-layer tests, including `test_ignores_head_sha_and_cell_key` confirming the content-identity-keyed (not frozen) nature of the existing store

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_harness_optimize.py:140-148` (`test_only_baseline_score_captures_baseline`) — the exact "scan every other state for the forbidden capture" pattern (iterate `loop_data["states"]`, exclude the one legitimate capture site by name, assert total exclusion); an analogous test for a frozen-external-baseline capture key would follow this shape
- `scripts/tests/test_fsm_validation_meta_rules.py:213-324` (`TestMetaLoopValidation`), specifically `test_mr2_does_not_fire_when_capture_referenced_in_reference` (`:274-304`, itself annotated "(ENH-3421)" as the precedent for extending MR-2's field allowlist) — a new evaluate field needs both an addition to `_has_baseline_reference`'s `candidates` list (`meta_rules.py:588-590`) and a mirrored `test_mr2_does_not_fire_when_capture_referenced_in_<new_field>` case
- `scripts/tests/test_cli_harness.py:3204-3227,3189-3202,3229-3237` (`test_delta_json_payload`, `test_delta_reported_with_provenance`, `test_delta_null_when_candidate_ungraded`) — existing tests at risk if `BaselineDelta`'s single-reference shape changes to report a dual/four-way outcome; each asserts on the current flattened `payload["baseline"]` key set or the `"Delta:"`/`"Delta: n/a"` printed line
- `scripts/little_loops/cli/harness.py:1837-1853` (`_compare_baseline_refusal`) and its indirect test coverage in `TestBaselineCompare` (`test_no_baseline_refused_before_any_invocation`, `test_partial_baseline_refused_before_any_invocation`, `test_conditions_fp_mismatch_refused_before_any_invocation`) — reusable fail-closed precedent; each test asserts a 3-4 part combination (exit code 2, zero subject invocations, a stderr substring, and for the no-baseline case zero rows written) that a frozen-baseline refusal check should follow

## Program Design

### Types

- `BaselineKey`: `runner, target, input_hash, target_content_hash` (frozen) (`scripts/little_loops/history_reader/harness.py:250`)
- `BaselineConditions`: `n, conditions_fp, semantic_prompt, semantic_model, subject_model, timeout_s, host_cli` (`scripts/little_loops/history_reader/harness.py:267`)
- `BaselineResult`: `key, conditions, tally, attempt_ids, head_sha, measured_at, subject_model, dirty_rows, source` (`scripts/little_loops/history_reader/harness.py:288`)
- `BaselineDelta`: `candidate, baseline, delta, source, head_sha_differs` (`scripts/little_loops/cli/harness.py:1560`) — widened additively with `vs_incumbent: str`, `frozen: BaselineResult | None`, `vs_pin: str | None`, `outcome: str | None` (D5/D7).
- New `BaselinePin` (frozen dataclass, `cli/harness.py`): `runner, target, target_content_hash, pinned_head_sha, pinned_at, reason` — the only new record (D2/D3). The frozen arm itself is an ordinary `BaselineResult` returned by `baseline_for()`.
- New vocabulary constants in `cli/harness.py`: `ARM_VERDICTS = ("ahead", "behind", "inconclusive")`, `PAIR_OUTCOMES = ("improvement", "drift", "regression", "inconclusive")` (D4/D5).

### Signatures

- `_compare_baseline_refusal(key: BaselineKey, conditions: BaselineConditions) -> str | None` — existing pre-run compare gate (`cli/harness.py:1837`); called a second time with `BaselineKey(..., target_content_hash=pin.target_content_hash)` when a pin exists, so the frozen arm fails closed the same way.
- `baseline_for(db_path: Path | str, *, runner: str, target: str, input_hash: str, target_content_hash: str, conditions: BaselineConditions) -> BaselineResult | None` (`history_reader/harness.py:325`) — **reused unchanged** for the frozen arm by passing the pinned hash (D3).
- New `read_pin(runner: str, target: str) -> BaselinePin | None` / `write_pin(pin: BaselinePin, *, force: bool) -> str | None` (returns a refusal message on a non-monotone re-pin, D6) — `cli/harness.py`.
- New `_arm_verdict(candidate: SampleTally, arm: SampleTally) -> str` and `_pair_outcome(vs_incumbent: str, vs_pin: str) -> str` — pure functions over Wilson CI bounds (D4/D5), unit-testable without a DB.
- `_run_compare_arm(...)` (`cli/harness.py:1855`) gains a `frozen: BaselineResult | None` parameter; `_report_samples(...)` (`:1405`) renders the extra fields when `delta.frozen` is set.
- New `cmd_pin_baseline(args) -> int` registered in the `ll-harness` subparser alongside the existing runners.

### Call Path

`cmd_skill`/`cmd_cmd`/`cmd_mcp`/`cmd_prompt` (compare branch) -> `read_pin()` -> if a pin exists, `_compare_baseline_refusal()` on the pinned key (fail closed) -> `_run_compare_arm(..., frozen=baseline_for(pinned hash))` -> one `_run_sample_loop()` (unchanged; the candidate is sampled exactly once) -> `_arm_verdict()` ×2, `_pair_outcome()` -> widened `BaselineDelta` -> `_report_samples()` renders `vs_incumbent`/`vs_pin`/`outcome` in text and under the existing `payload["baseline"]` object in JSON. Exit code path untouched.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-14 — based on codebase analysis:_

- `_run_compare_arm()`/`_run_baseline_phase()` (`cli/harness.py:1855`,`:1764`) confirmed scoped to one CLI invocation: the "baseline" arm is either just-run samples or previously-stored rows for the same content identity — no notion of a lineage of successive generations exists in either function; each call is stateless with respect to prior `--compare-baseline` invocations beyond what `baseline_for()` finds.
- `BaselineDelta` (`cli/harness.py:1559-1574`) is `candidate, baseline, delta, source, head_sha_differs` — `delta` is `None` (not a banded verdict) when the candidate has zero graded samples, and the CLI's exit code always comes from the candidate tally alone; `delta` is additive report content, never a pass/fail input today. A four-way outcome (beats both / incumbent-only / baseline-only / neither) as this section's Call Path proposes has no existing shape to extend — `BaselineDelta` reports one delta against one reference, not two.
- MR-2's `_has_baseline_reference()` (`fsm/validation/meta_rules.py:581-596`) is a hand-maintained field allowlist (`[ev.previous, ev.source, ev.reference]` plus `ev.target` if string) that recognizes which `EvaluateConfig` fields count as "a captured baseline value is referenced" — not dynamic; a new frozen-baseline field would need to be added to this list by hand to be recognized by the lint rule, distinct from adding the field itself.
- Existing fail-closed precedent directly reusable for a frozen-baseline refusal: `_compare_baseline_refusal()` (`cli/harness.py:1837-1853`) is a pre-run, zero-side-effect existence check (not staleness) that refuses with exit 2 before any subject invocation when no full-n baseline row set exists; ENH-3421's `reference` resolution is separately fail-closed on an unresolvable (but present) value, distinct from "value absent."

_Added by `/ll:refine-issue` — 2026-09-14 — based on codebase analysis:_

- `evaluate_convergence()`'s reference-regression check (`fsm/evaluators.py:466-477`) runs before the target-reached branch: `regressed = current > reference if direction=="minimize" else current < reference`, folding a regression into the existing `"stall"` verdict with a `details["regressed_vs_reference"]=True` marker — confirmed there is no separate verdict string for "regressed vs. frozen reference" today.
- The fail-open/fail-closed distinction is narrower than it first appears: no code in `evaluators.py` handles an explicitly *absent* `reference` differently from a resolved-but-non-regressing one — both simply skip the regression branch (`if reference is not None:`). The fail-closed behavior is scoped specifically to "a `reference` string is set but fails to interpolate to a float," which the dispatch site handles separately by returning verdict `"error"`.

_Added by `/ll:refine-issue` — 2026-09-14 — based on codebase analysis:_

- `_run_compare_arm()`'s candidate sampling happens exactly once per invocation, inside `_run_sample_loop()` (called at `cli/harness.py:1874`); a frozen-baseline comparison must read that same `res` rather than triggering a second sample loop. `_report_samples()` (`:1405`) and `BaselineDelta` (`:1559-1574`) each carry exactly one reference/delta pair today, and both the JSON (`:~1432-1483`) and text (`:~1486-1510`) render paths pick a single `shown` object — a second arm requires widening one or both of these shapes, not adding a parallel call path.
- `evaluate_convergence()`'s reference-regression check folds into the existing `"stall"` verdict via a `details["regressed_vs_reference"]` marker (`fsm/evaluators.py:466-477`); that marker is unreachable downstream today. The executor persists only `eval_result.verdict` into `self.captured[state.capture]` (`fsm/executor.py:2207-2208`), never `.details`, and `STALL_DETECTED_EVENT` carries no `details` either (`executor.py:2227-2236`, `:2258-2267`). `${result.*}` interpolation only reaches the evaluating state's own `route:` table (same-state-only), so a bare `details` marker cannot drive a later state's routing — a distinct, reportable "beats-incumbent-not-baseline" outcome needs either a new verdict string (not a reuse of `"stall"`) or a change to what the executor persists into `captured`.
- Reusing `BaselineKey`/`baseline_for()`'s existing lookup pattern unmodified for the frozen-baseline record would rediscover ENH-3435's roll-forward, not avoid it: `target_content_hash` is recomputed from current HEAD at every call site (e.g. `_incumbent_content_hash()`, `cli/harness.py:1682`), and `baseline_for()`'s match key has no field that is fixed once and never recomputed. A frozen record needs a key component set at freeze time and never re-derived from current HEAD — neither existing mechanism has one.
  - _Correction (review, 2026-09-14):_ the roll-forward lives in the **callers** (every call site derives the hash from HEAD), not in `baseline_for()` itself, which filters on whatever `target_content_hash` it is handed. A pin record that stores the hash at pin time and passes it through is sufficient; no new reader or store is needed (Design D3). The rest of the finding stands.
- No production code enforces "capture once" for any FSM `capture:` key — every capture site in `fsm/executor.py` (`:1275`, `:1282`, `:2681`, `:2207-2208`) performs an unconditional overwrite with no existing-value guard. The only "must stay frozen" enforcement anywhere is a test-side scan of one loop's static YAML (`test_only_baseline_score_captures_baseline`, `test_harness_optimize.py:140-148`) — it does not generalize to other loops or other capture keys and has no runtime counterpart.

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` (`check_comparator`/`type: comparator`/`baseline_path`/`auto_promote` worked example, lines 29,337-370,1137-1175) — narrates the "other" existing frozen mechanism this issue's Design says not to conflate with
- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md:305-314,454-458` — the "Frozen-reference guard (ENH-3421)" subsection and `promote-baseline`/comparator-baseline cross-references; the closest existing prose to a "four-way outcome" concept, likely extension point rather than replacement
- `docs/reference/API.md` — verbatim-mirrors the full `EvaluateConfig` dataclass as a hand-maintained code block (`#### EvaluateConfig`, lines 6048-6104) including `reference`/`baseline_path`/`auto_promote`; does **not** currently document `BaselineDelta`/`BaselineResult`/`BaselineKey`/`baseline_for`/`BaselineConditions` at all
- `docs/reference/CLI.md` — `--measure-baseline`/`--baseline-of`/`--compare-baseline` option-table rows (`:233-239`) and `ll-loop promote-baseline` full command doc (`:1418-1431`)
- `docs/guides/EVALUATION_GUIDE.md:386,400-404` — worked `--compare-baseline` example plus refusal/bidirectional-store prose; needs a companion frozen-baseline paragraph, not a rewrite
- `CHANGELOG.md` — carries one-line entries for both prior mechanisms (ENH-3435 line 70, ENH-3421 line 129); establishes the convention this issue's landing should follow
- `scripts/tests/test_wiring_reference_docs.py` — a data-driven `(doc_file, required_string, issue_id)` gate asserting specific strings land in specific docs; any new doc string this issue adds is only durably enforced if a corresponding tuple is added here

### Configuration

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/fsm/validation/meta_rules.py:588-590` (MR-2's `_has_baseline_reference` `candidates` list) is hand-maintained and must be manually extended for a new frozen-baseline field — contrast with MR-14 (`_validate_evaluate_unknown_keys`, `fsm/validation/structural_rules.py:1796-1846`), which derives its known-fields set dynamically from `dataclasses.fields(EvaluateConfig)` via `evaluate_config_known_fields()` (`fsm/schema.py:270-278`) and needs no manual update
- `scripts/little_loops/fsm/schema.py` `EvaluateConfig` (class from line 39) has three additional manual-touch sites beyond the field declaration itself if a new frozen-baseline field is added: the docstring `Attributes:` block (`reference`'s ENH-3421 entry at lines 74-79 is the template), a `to_dict`-style serializer (`result["reference"] = self.reference` pattern, `~186-187`), and a `from_dict`-style deserializer (`reference=data.get("reference")` pattern, `~247`)
- No FSM-specific JSON Schema file exists (`fsm*.schema.json` repo-wide glob: zero hits) and `scripts/little_loops/config-schema.json` has zero hits for `EvaluateConfig`/`"reference"`/`"previous"` — schema validation for `EvaluateConfig` fields is enforced purely by the Python dataclass plus MR-2/MR-14, not a separate JSON Schema artifact

## Implementation Steps

1. **Pure verdict helpers first (TDD).** Add `ARM_VERDICTS`/`PAIR_OUTCOMES`, `_arm_verdict()`, `_pair_outcome()` to `cli/harness.py` with table-driven unit tests over hand-built `SampleTally` CI bounds: disjoint-above → `ahead`, disjoint-below → `behind`, overlapping → `inconclusive`, zero-graded candidate → `inconclusive`; all 9 `(vs_incumbent, vs_pin)` combinations map to the D5 label.
2. **Pin record.** Add `BaselinePin`, `read_pin()`, `write_pin()` (append-only `pins` list under `.ll/harness-pins/`, monotone-refusal per D6 using `baseline_for()` for both old and new content under the current `BaselineConditions`), and `cmd_pin_baseline` with `--reason` and `--force`. Refusal exits 2 with zero DB writes, following the `_baseline_flag_refusal` / `--retry-of` precedent.
3. **Second arm.** In the four `cmd_*` compare branches, call `read_pin()`; when present, run `_compare_baseline_refusal()` on the pinned key, then pass `frozen=read_baseline(pinned_key, conditions)` into `_run_compare_arm()`. When the pin's content hash equals the incumbent hash, set `frozen` to the same `BaselineResult` (no second query) and note it in the report.
4. **Widen `BaselineDelta` and reporting.** Add the four optional fields; in `_report_samples()` render `Arms: vs-incumbent=<v> vs-pin=<v> → <outcome>` plus the frozen arm's rate/CI/provenance in text, and `vs_incumbent`/`frozen`/`vs_pin`/`outcome` keys inside the existing `payload["baseline"]` object in JSON. Existing keys and `Delta:` lines unchanged (D7).
5. **Tests.** Extend `TestBaselineCompare` (`test_cli_harness.py:3081-3239`): no-pin path byte-identical (existing three `test_delta_*` tests untouched and passing); pin present + full-n rows → dual report and JSON keys; pin present + no rows → exit 2, zero subject invocations, stderr names `pin-baseline`/`--measure-baseline`; re-pin refused when new content measures below the current pin, allowed when ≥ or `--force`; pin history never shrinks.
6. **Docs.** `docs/reference/CLI.md` (new `pin-baseline` command doc next to `:233-239`; `--compare-baseline` row gains the dual-arm sentence), `docs/guides/EVALUATION_GUIDE.md:386,400-404` (companion frozen-arm paragraph), `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md:305-314` (cross-link from the ENH-3421 frozen-reference subsection: within-run vs cross-run anchoring), `docs/reference/API.md` (document `BaselineDelta`/`BaselineResult`/`BaselineKey`/`BaselinePin` — none exist there today), `CHANGELOG.md` one-liner in the current release section (never `[Unreleased]`). Register each new doc string in `scripts/tests/test_wiring_reference_docs.py`.
7. **Follow-up issue.** Open a child of EPIC-3475 for loop consumption: wiring `ll-harness --compare-baseline --output json` into `harness-optimize.yaml` and routing on `outcome` (`drift`/`regression` → `revert_and_log`). Link it from this issue's Session Log on landing.
8. `python -m pytest scripts/tests/test_cli_harness.py scripts/tests/test_history_reader_harness.py scripts/tests/test_harness_optimize.py scripts/tests/test_wiring_reference_docs.py -v` passes; `ruff check scripts/` and `python -m mypy scripts/little_loops/` clean.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Read `.ll/decisions.d/a2c57916-aa1c-48db-86ad-cf1c3964d62d.json` and `.issues/enhancements/P3-ENH-3421-*.md`'s prior-art discussion before choosing a design — ENH-3421 explicitly rejected wiring `check_comparator` into `harness-optimize.yaml`'s `gate` state as a second required check, the design shape closest to this issue's own proposal. _(Resolved by D1: this issue stays at the `ll-harness` CLI layer.)_
- ~~If the mechanism is added to `EvaluateConfig`, extend `_has_baseline_reference`'s hand-maintained `candidates` list (`meta_rules.py:588-590`) plus the docstring, `to_dict`, and `from_dict` sites on `EvaluateConfig` (`fsm/schema.py`)~~ — _not applicable under D1; no `EvaluateConfig` field is added._
- Update `docs/reference/API.md` to add `BaselineDelta`/`BaselineResult`/`BaselineKey`/`BaselinePin` documentation, which does not exist there today (the `EvaluateConfig` mirror is untouched under D1)
- Register any new doc strings in `scripts/tests/test_wiring_reference_docs.py` so the doc coupling is durably enforced
- `test_delta_json_payload`, `test_delta_reported_with_provenance`, `test_delta_null_when_candidate_ungraded` (`test_cli_harness.py`) must keep passing unmodified — D7 makes the widening additive
- ~~Add a `test_only_baseline_score_captures_<new-key>`-shaped scan test~~ — _not applicable; no loop gains a new capture under this issue (deferred to the step-7 follow-up)._

## Acceptance Criteria

1. `ll-harness pin-baseline <runner> <target>` writes a pin whose `target_content_hash` equals `_incumbent_content_hash()` of the target at that moment; a second invocation appends rather than replaces, and the file's `pins` list never loses an entry.
2. Re-pinning is refused (exit 2, no write) when the new content's full-n rate under current conditions is below the active pin's, and allowed when it is ≥ or `--force` is given; a forced re-pin records `force` in the entry.
3. With no pin, `--compare-baseline` text and `--json` output are unchanged from ENH-3435 for every existing key and line (the three existing `test_delta_*` tests pass unmodified).
4. With a pin and full-n rows for the pinned content, the report carries `vs_incumbent`, `vs_pin` ∈ `{ahead, behind, inconclusive}` and `outcome` ∈ `{improvement, drift, regression, inconclusive}`, computed from Wilson CI bounds per D4/D5, in both text and JSON.
5. With a pin but no full-n rows for the pinned content under current conditions, the run refuses before any subject invocation (exit 2, zero candidate rows written) and the message names how to measure the pinned content.
6. A candidate whose CI is wholly above the incumbent's and wholly below the pin's reports `outcome: drift`; the exit code is still the candidate tally's banding alone.
7. The candidate is sampled exactly once per invocation (one `_run_sample_loop()` call) regardless of how many arms are reported.
8. Docs listed in step 6 carry the new strings and `test_wiring_reference_docs.py` enforces them; `CHANGELOG.md` has the entry.

## Impact

- **Priority**: P4 — addresses a slow, cross-run drift failure mode rather than an active incident; no loop consumes `--compare-baseline` yet, so the signal has no automated consumer until the step-7 follow-up.
- **Effort**: Small-Medium — no new store or reader (D3), no FSM-layer change (D1); the work is a pin record + CLI verb, two pure classification helpers, an additive widening of `BaselineDelta`/report, tests, and docs.
- **Risk**: Low — additive report shape (D7); the one behavioural change (fail-closed refusal when a pin exists but is unmeasured) only fires for users who have explicitly pinned. Re-pin monotonicity (D6) closes the backdoor the earlier draft warned about.
- **Breaking Change**: No

## Verification Notes

Verdict at time of check: **OUTDATED** (corrections below applied in the same pass, so the
issue as it now reads is up to date — this section is a record of what was wrong and fixed,
not an outstanding action item)

- **Graph**: provider=`codegraph` freshness=`fresh`
- Systematic line-number drift found and corrected in citations against
  `scripts/little_loops/cli/harness.py` (~35 lines, from `feat(harness): score ll-harness
  runs on a named efficiency vector`, 80d2d38d0) and `scripts/little_loops/history_reader/harness.py`
  plus `scripts/tests/test_history_reader_harness.py` (10-38 lines, drift independent of
  the above). Affected: `BaselineDelta`, `_compare_baseline_refusal`, `_run_compare_arm`,
  `_run_baseline_phase`, `_incumbent_content_hash`, `_report_samples`, the `cmd_skill`/
  `cmd_cmd`/`cmd_mcp`/`cmd_prompt` call sites, `BaselineKey`/`BaselineConditions`/
  `BaselineResult`/`baseline_for()`, and `TestBaselineFor`/`test_ignores_head_sha_and_cell_key`
  — corrected via `ll-code defines`, cross-checked with direct grep, across the Codebase
  Research Findings, Files to Modify, Program Design (Types/Signatures/Call Path), and
  Dependent Files sections.
- No substantive research conclusion was affected by the drift: the two pre-existing
  "frozen reference" mechanisms (ENH-3421's `reference` field, `evaluate_comparator()`'s
  standing baseline file), the absence of any "self-improvement lineage" concept in the
  codebase, and the ENH-3421 prior-art rejection of the closest design shape all verified
  accurate as stated. `fsm/evaluators.py`, `fsm/executor.py`, `fsm/schema.py`, and
  `cli/loop/info.py` citations checked with zero drift.
- Evidence-quote check (`ll-verify-evidence --json`): `ok: true`, 0 findings.
- Decisions check: no active required rules in `.ll/decisions.yaml`/`.ll/decisions.d/` —
  nothing to gate against.
- No `## Proposed Solution` section exists on this issue, so the proposal-vs-code
  consequence check (B6) does not apply.
- No `## Blocked By`/`## Blocks` sections present — dependency-reference checks (§E) N/A.

## Status

**Open** | Created: 2026-09-13 | Priority: P4


## Session Log
- `/ll:verify-issues` - 2026-09-15T03:54:03 - `bd6fcb1a-598c-4be7-8f16-9ee73f80016e.jsonl`
- `/ll:refine-issue` - 2026-09-14T22:49:26 - `bac75f45-b587-45bb-bf3c-443b0c5e805a.jsonl`
- `/ll:refine-issue` - 2026-09-14T21:18:34 - `b80e42ca-40bb-4d8a-b6d8-3b9dab6f1bf1.jsonl`
- `/ll:wire-issue` - 2026-09-14T20:51:04 - `df520d06-750a-40b3-acb9-fb846e40ee7a.jsonl`
- `/ll:refine-issue` - 2026-09-14T20:30:29 - `32822b8f-688a-416a-8c16-7d6cacd02e0d.jsonl`
- `/ll:format-issue` - 2026-09-14T20:15:11 - `94434fad-8258-433c-9701-ead707bb03a6.jsonl`
