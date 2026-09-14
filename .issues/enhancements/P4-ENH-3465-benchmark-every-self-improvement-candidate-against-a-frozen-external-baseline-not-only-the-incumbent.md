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

Every improvement claim the self-improvement tooling can currently make is incumbent-relative. Successive wrapper drafts are judged against the previous draft; plan-scoring rubrics score against their own dimensions. Neither holds a fixed reference the whole lineage could fail against. That admits a specific failure mode: a lineage where each generation genuinely beats its immediate parent while the lineage as a whole drifts away from any absolute standard — every local comparison passes and the global regression is invisible.

The guard is cheap and structural: a candidate must be measured against two opponents — the incumbent (proving the lineage is still improving) and a frozen external baseline that never changes (proving "better" is still anchored outside the lineage). Beating one but not the other is a distinct, reportable outcome — not a pass — and a candidate that beats the incumbent while losing to the baseline is the signal that the lineage has entered a self-referential local optimum.

## Current Behavior

Every improvement claim the self-improvement tooling can currently make is incumbent-relative. Successive wrapper drafts are judged against the previous draft; plan-scoring rubrics score against their own dimensions. Neither holds a fixed reference the whole lineage could fail against, so a lineage where each generation genuinely beats its immediate parent can drift away from any absolute standard while every local comparison still passes.

## Expected Behavior

A candidate is measured against two opponents: the incumbent (proving the lineage is still improving) and a frozen external baseline that never changes (proving "better" is still anchored outside the lineage). Beating one but not the other is a distinct, reportable outcome — not a pass — and a candidate that beats the incumbent while losing to the baseline is the signal that the lineage has entered a self-referential local optimum.

## Scope Boundaries

- Decide what the frozen baseline is per improvement loop: a pinned wrapper version, a shipped default, or a recorded run.
- Decide how and when the baseline is allowed to be re-pinned, without re-pinning becoming a backdoor for drift.
- Decide what the loop does when the two comparisons disagree.

## Design

This is a different axis from the evaluator-hardening work (epoch-bounded objective versioning, versioned evaluator prompts over golden sets): those keep the *measuring instrument* honest; this keeps the *subject* honest by pinning a permanent second opponent. Golden sets test the evaluator; a frozen baseline tests the lineage.

Complements the unmutated baseline arm shipped as ENH-3435, and is a different thing: that baseline is a control arm measured inside a single harness run (it answers "did this change help relative to no change"); this issue's baseline is a standing external opponent for the lineage (it answers "is the lineage still ahead of a fixed reference"). A loop that has both can distinguish a change that helps from a lineage that is drifting. Also pairs naturally with two-number reporting of structure-vs-tuning decomposition, which needs exactly this kind of dual result as input.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-14 — based on codebase analysis:_

- Two independent "frozen reference" mechanisms already exist in this codebase, neither of which is the standing lineage opponent this issue proposes: (1) `evaluate_convergence()`'s `reference` field (`fsm/schema.py:132`, `fsm/evaluators.py:438-496`, ENH-3421, status done) — captured once outside `harness-optimize.yaml`'s iterate cycle (`baseline_score` state), checked before the target-reached branch, fails closed on an unresolvable value, and folds a regression into the existing `stall` verdict rather than a distinct outcome; wired into exactly one loop (`harness-optimize.yaml`), explicitly not `rl-coding-agent.yaml`. (2) `evaluate_comparator()`'s `.loops/baselines/<loop>/output.txt` file (`fsm/evaluators.py:1636-1702`, `EvaluateConfig.auto_promote`/`baseline_path`) — a literal file surviving across all future runs until re-pinned via `ll-loop promote-baseline` (`cli/loop/info.py:1256`) or, with the default `auto_promote: true`, overwritten on every winning candidate — the same rolling-drift shape a frozen baseline is meant to guard against. ENH-3421's own prior research states explicitly: no shared "frozen-capture" primitive exists between these two.
- `BaselineKey`/`baseline_for()` (ENH-3435) is a content-identity-keyed rolling cache, not a permanently-pinned record: `baseline_for()`'s match query explicitly ignores `head_sha` (`test_ignores_head_sha_and_cell_key`, `test_history_reader_harness.py:547-566`), so a baseline row simply stops matching — with no explicit invalidation step — the moment `target_content_hash` changes. This confirms this section's own distinction that ENH-3435's baseline is not a standing external opponent.
- No "self-improvement lineage" (successive wrapper drafts, plan-scoring rubrics judged against their own dimensions) exists as a named implementation anywhere in the codebase — a repo-wide unfiltered search for `lineage`, `wrapper.?draft`, `plan_scoring`/`plan-scoring` returns zero code hits; these terms appear only in this issue's own prose. The nearest structural analogue found is `harness-optimize.yaml`'s rolling `prev_score`/`capture_prev` incumbent comparison (a hill-climbing loop, not a multi-candidate lineage).
- A different, unrelated "frozen" concept already exists and should not be conflated: `ENH-1122` ("Frozen-Boundary Convention", status deferred) is a byte-region edit-mutation guard (`<!-- ll:frozen -->` markers restricting which lines `harness-optimize` may edit), not an evaluation-reference concept. ENH-3421's own issue text makes this same distinction explicitly.
- The "epoch-bounded objective versioning" / "versioned evaluator prompts over golden sets" work this section contrasts itself against (as "keeping the measuring instrument honest") has no locatable implementation under those names either — zero repo-wide hits for `epoch-bounded`, `objective_version`, or a golden-set evaluator-hardening concept distinct from `test_adapt_golden_corpus.py`'s unrelated host-adapter snapshot fixtures.

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-14 — based on codebase analysis:_

Confirmed file paths and call sites for the two existing baseline/reference mechanisms this issue's frozen-external-baseline record must integrate alongside without conflating.

### Files to Modify
- `scripts/little_loops/cli/harness.py` — `_run_compare_arm()` (`:1820`), `_compare_baseline_refusal()` (`:1802`), the four `cmd_skill`/`cmd_cmd`/`cmd_mcp`/`cmd_prompt` call sites (`:2198-2547`) that reach them today for the incumbent-only comparison
- `scripts/little_loops/history_reader/harness.py` — `BaselineKey`/`BaselineConditions`/`BaselineResult`/`baseline_for()` (`:239-315`), the unmutated-arm store this issue's own Design section says the new frozen-external-baseline record must be distinct from
- `scripts/little_loops/fsm/validation/meta_rules.py` — `_has_baseline_reference()` (`:581-596`) — a new frozen-baseline `EvaluateConfig` field (if the mechanism is wired at the FSM-evaluator layer like ENH-3421's `reference`, rather than the `ll-harness` CLI layer like ENH-3435) needs manual addition to this allowlist to be lint-recognized

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/harness.py:30`, `scripts/little_loops/history_reader/__init__.py:184` — importers of `history_reader/harness.py`
- `scripts/tests/test_history_reader_harness.py` `TestBaselineFor::*` (lines 530-653), `scripts/tests/test_cli_harness.py` `TestBaselineStoreBidirectional`/`TestBaselineDegrade` (`:3449`,`:3520`) — existing callers of `baseline_for()` a new frozen-record type must not break
- `scripts/little_loops/loops/harness-optimize.yaml` `gate` state (`:191`) — the one shipped loop wired to ENH-3421's `reference` field; `rl-coding-agent.yaml` explicitly excluded by that issue despite the same rolling-`previous` shape

### Conventions in Force
- A field that must stay frozen (never re-captured) is enforced structurally, checked by a dedicated test that scans every other state for the forbidden capture — evidence: `test_only_baseline_score_captures_baseline` (`test_harness_optimize.py:140-148`), asserting no state but `baseline_score` sets `capture: baseline`
- A frozen reference fails *closed* on an unresolvable value while a rolling/incumbent reference fails *open* (absent means "first iteration, no check") — evidence: `evaluate_convergence()`'s handling of `reference` vs. `previous` (ENH-3421 Expected Behavior §4)
- Two independently-built "capture once, keep fixed" mechanisms already coexist with no shared primitive between them — evidence: ENH-3421's own confirmed research stating no shared "frozen-capture" primitive, decorator, or field type exists anywhere in `scripts/little_loops/`
- A comparison-result dataclass reports one delta against one reference (`candidate, baseline, delta, source, head_sha_differs`), never a multi-reference outcome — evidence: `BaselineDelta` (`cli/harness.py:1524-1538`)

### Tests
- `scripts/tests/test_harness_optimize.py:125-156` — structural YAML-dict assertions for ENH-3421's frozen-reference wiring (`test_gate_has_convergence_evaluator`, `test_only_baseline_score_captures_baseline`, `test_trajectory_lines_include_baseline`)
- `scripts/tests/test_cli_harness.py:3081-3239` (`TestBaselineCompare`) — end-to-end CLI tests for the existing delta/outcome shape (`test_delta_reported_with_provenance`, `test_delta_json_payload`, `test_delta_null_when_candidate_ungraded`)
- `scripts/tests/test_history_reader_harness.py` (`TestBaselineFor`) — reader-layer tests, including `test_ignores_head_sha_and_cell_key` confirming the content-identity-keyed (not frozen) nature of the existing store

## Program Design

### Types

- `BaselineKey`: `runner, target, input_hash, target_content_hash` (frozen) (`scripts/little_loops/history_reader/harness.py:239`)
- `BaselineConditions`: `n, conditions_fp, semantic_prompt, semantic_model, subject_model, timeout_s, host_cli` (`scripts/little_loops/history_reader/harness.py:~250`)
- `BaselineResult`: `key, conditions, tally, attempt_ids, head_sha, measured_at, subject_model, dirty_rows, source` (`scripts/little_loops/history_reader/harness.py:~260`)
- `BaselineDelta`: `candidate, baseline, delta, source, head_sha_differs` (`scripts/little_loops/cli/harness.py:1525`)
- New: a frozen-external-baseline record, distinct from `BaselineResult` — `BaselineResult` is an unmutated in-run control arm (ENH-3435), not a standing lineage opponent, per this issue's own Design distinction.

### Signatures

- `_compare_baseline_refusal(key: BaselineKey, conditions: BaselineConditions) -> str | None` — existing pre-run compare gate in `scripts/little_loops/cli/harness.py:1802`; the new frozen-baseline comparison needs an analogous refusal check against the external baseline record.
- `baseline_for(db_path: Path | str, *, runner: str, ...) -> BaselineResult | None` — existing unmutated-arm reader in `scripts/little_loops/history_reader/harness.py:315`; the new frozen-external-baseline lookup is a distinct function, not a reuse of this one.
- `_run_baseline_phase(runner_label: str, args: argparse.Namespace, n: int, ...)` (`cli/harness.py:1729`), `_run_compare_arm(runner_label: str, args: argparse.Namespace, n: int, ...)` (`cli/harness.py:1820`) — existing single-run control-arm comparison logic; the new incumbent-vs-frozen-baseline comparison is additive to this call path, not a replacement.

### Call Path

Candidate result -> existing `_run_compare_arm()` (incumbent comparison, `cli/harness.py:1820`) run alongside a new frozen-baseline comparison against a record outside `baseline_for()`'s unmutated-arm store -> combined into a `BaselineDelta`-shaped pair (beats-incumbent, beats-baseline) reported as the four-way outcome this issue's Summary specifies.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-14 — based on codebase analysis:_

- `_run_compare_arm()`/`_run_baseline_phase()` (`cli/harness.py:1820`,`:1729`) confirmed scoped to one CLI invocation: the "baseline" arm is either just-run samples or previously-stored rows for the same content identity — no notion of a lineage of successive generations exists in either function; each call is stateless with respect to prior `--compare-baseline` invocations beyond what `baseline_for()` finds.
- `BaselineDelta` (`cli/harness.py:1524-1538`) is `candidate, baseline, delta, source, head_sha_differs` — `delta` is `None` (not a banded verdict) when the candidate has zero graded samples, and the CLI's exit code always comes from the candidate tally alone; `delta` is additive report content, never a pass/fail input today. A four-way outcome (beats both / incumbent-only / baseline-only / neither) as this section's Call Path proposes has no existing shape to extend — `BaselineDelta` reports one delta against one reference, not two.
- MR-2's `_has_baseline_reference()` (`fsm/validation/meta_rules.py:581-596`) is a hand-maintained field allowlist (`[ev.previous, ev.source, ev.reference]` plus `ev.target` if string) that recognizes which `EvaluateConfig` fields count as "a captured baseline value is referenced" — not dynamic; a new frozen-baseline field would need to be added to this list by hand to be recognized by the lint rule, distinct from adding the field itself.
- Existing fail-closed precedent directly reusable for a frozen-baseline refusal: `_compare_baseline_refusal()` (`cli/harness.py:1802-1817`) is a pre-run, zero-side-effect existence check (not staleness) that refuses with exit 2 before any subject invocation when no full-n baseline row set exists; ENH-3421's `reference` resolution is separately fail-closed on an unresolvable (but present) value, distinct from "value absent."

## Implementation Steps

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-14 — based on codebase analysis:_

1. A frozen-external-baseline record exists that is distinct from `BaselineResult` (per this issue's own Program Design line) — `BaselineResult`/`baseline_for()` roll over implicitly on `target_content_hash` change and are not a candidate to reuse for a record that must survive content changes.
2. A candidate's comparison result names both outcomes — beats-incumbent and beats-baseline — as a single reportable value, not two separate pass/fail checks a caller must reconcile; `BaselineDelta`'s single-reference shape is not extended in place without deciding this.
3. Beating the incumbent while losing to the frozen baseline is distinguishable, in the reported outcome, from beating both or beating neither.
4. The mechanism does not silently disable itself the way an unresolvable-but-present frozen value would (per `evaluate_convergence()`'s fail-closed precedent for `reference`) — an absent frozen baseline and an unresolvable one are handled, and the difference between them is intentional, not an oversight.
5. Whichever of the two existing "frozen reference" shapes (ENH-3421's FSM-evaluator `reference` field vs. `evaluate_comparator`'s standing `.loops/baselines/` file) this issue's mechanism most resembles, the Scope Boundaries' three open decisions (what the frozen baseline is per loop, how/when it's re-pinned, what happens when the two comparisons disagree) are resolved before this integrates with `_run_compare_arm()`.
6. `python -m pytest scripts/tests/test_cli_harness.py scripts/tests/test_history_reader_harness.py scripts/tests/test_harness_optimize.py -v` passes.

## Impact

- **Priority**: P4 — the guard is cheap and structural but addresses a slow-drift failure mode rather than an active incident; the Scope Boundaries section leaves baseline-pinning mechanics as open decisions still to be made.
- **Effort**: Medium — depends on the outstanding Scope Boundaries decisions (what the frozen baseline is per loop, how/when it's re-pinned, what happens when the two comparisons disagree) before implementation can start.
- **Risk**: Low-Medium — a poorly chosen re-pinning policy could itself become the drift backdoor this issue is designed to prevent.
- **Breaking Change**: No

## Status

**Open** | Created: 2026-09-13 | Priority: P4


## Session Log
- `/ll:refine-issue` - 2026-09-14T20:30:29 - `32822b8f-688a-416a-8c16-7d6cacd02e0d.jsonl`
- `/ll:format-issue` - 2026-09-14T20:15:11 - `94434fad-8258-433c-9701-ead707bb03a6.jsonl`
