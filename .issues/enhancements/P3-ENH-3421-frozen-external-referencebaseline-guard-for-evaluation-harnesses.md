---
id: ENH-3421
type: ENH
title: Frozen external reference/baseline guard for evaluation harnesses
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-09'
captured_at: '2026-09-09T05:49:43Z'
labels:
- harness
- evaluation
- statistics
relates_to:
- ENH-3415
decision_needed: false
confidence_score: 97
outcome_confidence: 77
score_complexity: 15
score_test_coverage: 20
score_ambiguity: 20
score_change_surface: 22
---

# ENH-3421: Frozen external reference/baseline guard for evaluation harnesses

## Summary

Companion guard to ENH-3415's n-sample redundancy: a candidate should be tested against both
the incumbent and an unchanged frozen external reference/baseline, not just its immediate
parent — otherwise a lineage of promotions can drift into a self-referential local optimum
where every generation only beats the one before it, never an outside bar. ENH-3415's
Summary calls this out as a second mandatory-structure guard from evolutionary-search
harnesses, explicitly deferred as its own issue rather than folded into that one.

**Scope resolution (2026-09-09):** this issue is the implementation vehicle for Option A
(selected under Proposed Solution). The original "stub / research-only" framing is
superseded — refinement, decision, and wiring passes below resolved the open questions
(harness: the `convergence_gate` loops; "frozen": a captured numeric score that no state
inside the iterate cycle re-captures).

**Corrected rationale.** The "lineage drift" framing above does not, on its own, apply to
`harness-optimize.yaml`: its gate requires a candidate to *strictly* beat `prev_score`, and
`prev_score` is seeded from the baseline and only advances on acceptance, so every accepted
score already exceeds the frozen baseline by transitivity. The concrete hole the guard closes
is the **`target` short-circuit** in `evaluate_convergence()` (`fsm/evaluators.py:461`):
a candidate within `tolerance` of `target` returns verdict `target` *before* any comparison
to `previous`, and `harness-optimize.yaml` routes `target → commit_and_log` and keeps
iterating. With baseline 0.85, `target_score` 0.80, tolerance 0.02, a candidate scoring 0.79
is committed — a regression below the frozen baseline. A frozen-reference check that runs
*before* the target check is the only placement that fires; one added "alongside `previous`"
in the progress/stall branch is a tautology in this loop and must not be how this is built.

## Current Behavior

No frozen external reference/baseline guard exists in `ll-harness` or any other little-loops
evaluation harness today (confirmed by ENH-3415's own codebase research, 2026-09-09: nothing
in `.issues/` described this before ENH-3415 filed it).

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-09 — based on codebase analysis:_

- Confirmed by direct read of `cli/harness.py`: `ll-harness` itself has no incumbent/candidate concept anywhere — `HarnessEvalOutcome`, `_grade()`, and the ENH-3415 `_run_sample_loop()`/`SampleTally` tally only *this invocation's* samples; `_read_target_history()` (`cli/harness.py:1136`) prints a cross-invocation historical pass-rate line for display only — it never feeds `passed`/`verdict`/exit code. Any "did this beat something" decision is made one layer up, by whatever FSM loop calls `ll-harness`.
- Two existing FSM-level mechanisms already compare a candidate to *something*, but neither is frozen: (1) `harness-optimize.yaml`'s `convergence` gate (`evaluate_convergence()`, `fsm/evaluators.py:438`) compares each candidate only to `prev_score`, which the loop's own `capture_prev` state overwrites with the just-accepted candidate's score every iteration — `evaluate_convergence`'s signature (`current, previous, target, tolerance, direction`) has no fourth "frozen" input, so there is nowhere to plug an unchanging reference in today. (2) `evaluate_comparator()` (`fsm/evaluators.py:1604`) already reads a persisted `.loops/baselines/<loop>/output.txt` file that *can* stay genuinely frozen (`auto_promote: false` + manual `ll-loop promote-baseline`), but with the default `auto_promote: true` it is overwritten with the winning candidate's output on every "yes" verdict — the same rolling-drift shape as `prev_score`, via a different mechanism. `check_comparator` is also not wired into `harness-optimize.yaml`'s gate at all today; it is used by other loops (e.g. `harness-single-shot.yaml`) for whole-loop regression checks.
- Repo-wide search for "incumbent" or "frozen" (as an evaluation-baseline concept) found zero hits outside ENH-3415/ENH-3421's own issue text — confirms no prior art or naming convention exists to reuse.

_Added by `/ll:refine-issue` — 2026-09-09 — based on codebase analysis:_

- Two independently-implemented "capture once outside the iterate cycle" patterns already exist in shipped loops, with no shared/reusable primitive between them: `harness-optimize.yaml`'s `baseline_score` state (lines 110-116, reached once via `init_run → load_directive → baseline_score`, before the iterate region) versus `capture_prev` (lines 262-266, inside the iterate region, reassigned every accepted iteration). `captured.baseline.output` is referenced only for display (`propose` prompt) and to seed `prev_score` today — never inside `gate`'s `evaluate:` block.
- A second, independently-arrived precedent for the same frozen-vs-rolling distinction exists in `general-task.yaml`: `check_baseline_tests` (the `initial:` state, line 85) writes `${context.run_dir}/baseline-ref.txt` exactly once; `final_verify_spin_gate` (line 457) and `check_provisional_markers` (line 1011) only ever read it. A code comment at lines 434-437 already names the distinction explicitly ("both are frozen values on this cycle... would make the gate fail open forever if used as a condition"). This mechanism is a raw file under `${context.run_dir}` read by shell, not an FSM `capture:`/`EvaluateConfig` field — a second established shape for the same underlying rule, alongside `harness-optimize.yaml`'s.
- Repo-wide search found no shared "frozen-capture" primitive, decorator, or field type anywhere in `scripts/little_loops/` — each loop hand-rolls its own frozen value; no existing consolidation candidate to reuse instead of adding a new field.
- `baseline_path` (`fsm/schema.py:133`) is a name-adjacent but semantically unrelated existing `EvaluateConfig` field — scoped to the `comparator` evaluator type only, and names a directory path for blind A/B artifact comparison, not a numeric score reference. Do not conflate with the new field this issue proposes.

## Expected Behavior

`harness-optimize.yaml` (and any confirmed sibling `convergence_gate` loop, see Scope
Boundaries' Codebase Research Findings) gates each accepted candidate against both its
immediate parent (the existing `prev_score`/`convergence` comparison) and a reference that
does not advance across iterations — closing the gap this issue's Summary describes, where
today `prev_score` is reseeded from the winning candidate every cycle (`capture_prev`) and the
codebase's only existing frozen-capable comparison mechanism (`evaluate_comparator`'s
`auto_promote: false` baseline file) is not wired into that loop's gate at all. Two viable
mechanical shapes for this, grounded in what already exists, are laid out under Proposed
Solution.

### Guard semantics (binding for implementation)

1. **Check ordering.** When `evaluate.reference` is set and resolves, `evaluate_convergence()`
   compares `current` to the reference **first**, before the existing target-reached check.
   This is the whole point (see Summary's corrected rationale): the `target` short-circuit
   is the only path by which a below-baseline candidate is accepted today.
2. **Comparison rule.** Direction-aware, non-strict: for `maximize`, regression iff
   `current < reference`; for `minimize`, iff `current > reference`. Equality is not a
   regression (re-running the baseline unchanged must not be rejected). `tolerance` does
   **not** apply to this comparison — it belongs to the target check only.
3. **Verdict on regression.** Reuse the existing `stall` verdict, with
   `details["regressed_vs_reference"] = True` and `details["reference"] = <float>`. No new
   verdict: every `convergence_gate` consumer already routes `stall` to its reject/revert
   edge, so no loop `route:` block changes and no validator route-vocabulary changes.
4. **Fail-closed resolution.** Unlike `previous` (where an unresolvable value legitimately
   means "first iteration" and falls back to `None`), a `reference` that is *set* but cannot
   be interpolated or parsed as a float returns verdict `error` with
   `details["error"]` naming the field. A silently-disabled guard is worse than none.
5. **Default unchanged.** `reference` unset (the default) leaves `evaluate_convergence()`
   behavior byte-for-byte identical to today; all existing convergence tests pass unmodified.
6. **Details on every path.** When `reference` resolves, `details["reference"]` is included
   in `target`/`progress`/`stall` results too, so trajectory logs can show the bar.

## Scope Boundaries

- **In scope**: implementing Option A end-to-end — the `reference` field on `EvaluateConfig`,
  the ordered check in `evaluate_convergence()`, the JSON-schema mirror and MR-2 candidate
  list, the `convergence_gate` fragment description, and wiring the field into
  `harness-optimize.yaml` (populated from `captured.baseline.output`, see Integration Map).
- **In scope, with a seed state**: `rl-coding-agent.yaml` has **no** baseline capture today
  (`initial: act`; `prev_reward` is first written by `persist_reward` only after the first
  `improve`). Wiring the guard there needs a new one-shot seed state before the iterate cycle.
  Because that loop is a template whose `improve`/`persist_reward` bodies are echo stubs, the
  implementer may instead **drop it from scope** and record why in the Session Log — either
  outcome is acceptable; leaving it half-wired (field set, nothing captured) is not, since
  fail-closed resolution (Expected Behavior §4) would make every `score` pass route `error`.
- **Frozen is per baseline capture, not per run.** In `harness-optimize.yaml` state-mode,
  `dequeue_state → baseline_score` re-captures `baseline` for each queued state, so the
  reference is frozen for the duration of *that state's* optimization segment and re-seeded
  for the next. That is the intended behavior (different target state, different score scale)
  and must not be "fixed" into a run-global value.
- **Out of scope**: `ll-harness` itself (`cli/harness.py`) — it has no incumbent/candidate
  concept (see Current Behavior) and needs none; the guard lives one layer up in the FSM
  evaluator. Any change to ENH-3415's n-sample redundancy guard — the two are companions, not
  the same mechanism. Fixed-target `convergence_gate` consumers that set no `previous`
  (`agent-eval-improve.yaml`, `rl-policy.yaml`, `test-coverage-improvement.yaml`) — the new
  field is optional and they are untouched. Option B (`check_comparator` wiring) — rejected,
  see Decision Rationale.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-09 — based on codebase analysis:_

- Confirmed candidate: `harness-optimize.yaml` is the one loop in the codebase confirmed to exhibit the drift risk this issue describes — it populates `convergence_gate`'s `evaluate.previous` with a rolling `prev_score` that advances every accepted iteration. Other `convergence_gate` consumers (`agent-eval-improve.yaml`, `rl-policy.yaml`) do **not** populate `evaluate.previous` at all — they compare only against a fixed target, not a rolling prior score — so they do not currently exhibit this drift shape and are not confirmed in-scope. `rl-coding-agent.yaml` and `test-coverage-improvement.yaml` also use the `convergence_gate` fragment; whether they populate `evaluate.previous` with a rolling value was not confirmed either way and needs a direct check before scoping them in or out.

_Resolved by `/ll:wire-issue` — 2026-09-09:_
- `scripts/little_loops/loops/rl-coding-agent.yaml` **IS** in scope: its `score` state (`convergence_gate` fragment, lines 109-112) sets `previous: "${captured.prev_reward.output}"`, fed by a `persist_reward` state inside the same iterate cycle (`capture: prev_reward`, line 137, re-capturing the just-observed reward every pass) — the identical rolling-reseed shape as `harness-optimize.yaml`'s `capture_prev`/`prev_score`.
- `scripts/little_loops/loops/test-coverage-improvement.yaml` is **NOT** in scope: its `extract_percentage` state (`convergence_gate` fragment, lines 69-71) sets only `target`/`tolerance`, no `previous` key at all — same fixed-target shape as `agent-eval-improve.yaml`/`rl-policy.yaml`.

## Proposed Solution

**Option A**: Add a frozen-reference input to the `convergence` evaluator itself — a new
`EvaluateConfig` field that `evaluate_convergence()` (`fsm/evaluators.py:438`) checks alongside
`previous`, set in `harness-optimize.yaml`'s `gate` state from `baseline_score`'s captured
output, which no state inside the iterate cycle re-captures. Keeps the guard inside the numeric
mechanism `harness-optimize.yaml` already runs every iteration.

**Option B**: Wire the existing `check_comparator` evaluator (`evaluate_comparator()`,
`fsm/evaluators.py:1604`) into `harness-optimize.yaml`'s per-iteration `gate` state as a second,
required check alongside `convergence`, with `auto_promote: false` enforced so
`.loops/baselines/<loop>/output.txt` stays genuinely frozen between manual
`ll-loop promote-baseline` runs. Reuses a mechanism that already has frozen semantics, at the
cost of an LLM-judged blind A/B (`min_pairs`) on every iteration instead of a numeric
comparison.

**Recommended**: Option A for `harness-optimize.yaml` and its `convergence_gate`-family loops —
it keeps the guard numeric and cheap, matching the per-iteration scorer these loops already run,
and it closes the exact gap found (no frozen slot in `evaluate_convergence`'s current signature)
without requiring loop authors to adopt a second, differently-shaped evaluator. Option B remains
the better fit for `harness-single-shot.yaml`-style whole-loop regression checks, where it is
already used today.

> **Selected:** Option A — keeps the guard numeric and cheap inside the evaluator
> `harness-optimize.yaml` already runs, and scored 11/12 vs. Option B's 5/12 on codebase
> evidence (see Decision Rationale below).

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-09-09.

**Selected**: Option A — frozen-reference field on `EvaluateConfig`/`evaluate_convergence()`

**Reasoning**: Option A has direct, recent precedent (`abstain_on_exit_3`, ENH-3224) for
threading a new optional `EvaluateConfig` field through `to_dict`/`from_dict` and the
dispatcher's `interpolate()` call, gets MR-14 unknown-key lint coverage for free via
`evaluate_config_known_fields()`, and needs no new executor primitive because
`harness-optimize.yaml`'s `baseline_score` state already sits outside the iterate cycle
(naturally frozen by ordinary FSM capture semantics). Option B is not directly buildable as
described: `StateDef.evaluate` permits exactly one evaluator per state, so "a second, required
check alongside `convergence`" in the same `gate` state requires a new chained state with a
disjoint `route:` vocabulary (`yes`/`no`/`tie`/`no_baseline` vs. `target`/`progress`/`stall`) —
a wiring pattern with zero shipped precedent (only doc snippets in
`AUTOMATIC_HARNESSING_GUIDE.md`) that also stacks a per-iteration LLM-judged blind A/B onto an
already LLM-heavy 2-hour loop budget.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|--------------|------|-------|
| Option A | 3/3 | 3/3 | 3/3 | 2/3 | 11/12 |
| Option B | 1/3 | 1/3 | 2/3 | 1/3 | 5/12 |

**Key evidence**: the frozen-reference field is backed by 25+ existing `EvaluateConfig` fields
threaded this exact way (`fsm/schema.py:39-146`), with `evaluate_config_known_fields()`
auto-registering new fields for MR-14, and `baseline_score` (`harness-optimize.yaml:110-116`)
already sitting outside the iterate cycle unlike `prev_score`, which `capture_prev` overwrites
every accepted iteration. The comparator-wiring alternative rests on solid, shipped, tested
reuse targets in `evaluate_comparator()` and `TestComparatorEvaluator`, but no loop file in the
repo (`grep "type: comparator"` across `scripts/little_loops/loops/`) wires `check_comparator`
into a `gate` state — the pattern exists only in documentation, and `StateDef.evaluate` is
single-valued per state (`fsm/schema.py:696`), forcing a second state rather than an in-place
addition.

## Integration Map

### Files to Modify (Option A — selected)
- `scripts/little_loops/fsm/schema.py` (`EvaluateConfig`, ~line 133) — new `reference: str | None`
  field, plus docstring `Attributes:` entry, `to_dict()` emit-when-set, `from_dict()` parse.
- `scripts/little_loops/fsm/evaluators.py:438` (`evaluate_convergence`) — new `reference`
  parameter, checked **before** the target-reached branch (Expected Behavior §1); dispatcher
  `convergence` branch (~1908) — resolve `config.reference` fail-closed (§4).
- `scripts/little_loops/loops/lib/common.yaml` (`convergence_gate` fragment, ~151-162) —
  description only: add `evaluate.reference` to the "optionally" list.
- `scripts/little_loops/loops/harness-optimize.yaml` `gate` state — add
  `reference: "${captured.baseline.output}"`. Nothing else in the loop changes: `baseline` is
  captured only by `baseline_score` (outside the iterate cycle) and no state re-captures it, so
  it is already frozen by ordinary FSM capture semantics. `capture_prev` never touches it.
  `run_benchmark`'s scorer contract (`lib/benchmark.yaml:20-21`) is a bare float on stdout, so
  the raw capture parses without the `tail -1 | tr -d` normalization `init_prev` applies.
- `scripts/little_loops/loops/rl-coding-agent.yaml` — either add a one-shot seed state before
  `act` (capture `baseline_reward`, `initial:` moves to it) and set
  `reference: "${captured.baseline_reward.output}"` in `score`, or drop from scope (Scope
  Boundaries).
- Option B (`check_comparator` in `gate`) — rejected; not modified.

_Wiring pass added by `/ll:wire-issue` (Option A candidate wiring):_
- `scripts/little_loops/fsm/fsm-loop-schema.json` — `definitions.evaluateConfig.properties`
  (property block starts ~718) hand-lists every `EvaluateConfig` field and sets
  `"additionalProperties": false`. This is a **hard, test-enforced** companion edit distinct from
  the dynamic MR-14 lint — `test_fsm_schema.py:262-278`
  (`test_schema_json_evaluate_config_properties_match_dataclass_fields`) diffs this file's
  property keys against `dataclasses.fields(EvaluateConfig)` and **fails outright** if the new
  field is added to the dataclass without a matching property block here. Not named in this
  issue's Program Design and not covered by the MR-14 auto-registration the Decision Rationale
  cites — that auto-registration is real (`evaluate_config_known_fields()` derives from the
  dataclass, no manual list) but is a separate mechanism from this JSON-Schema mirror.
- `scripts/little_loops/fsm/validation/meta_rules.py` — MR-2's `_has_baseline_reference` (~581-597)
  builds its `candidates` list by hand: `[ev.previous, ev.source]` plus `ev.target` if it's a
  string. This is a **hardcoded, non-dynamic** field list (unlike MR-14's
  `evaluate_config_known_fields()`) — if `harness-optimize.yaml`'s gate state references the
  frozen baseline only via the new field (not via `evaluate.previous`), MR-2's
  `_has_baseline_reference` needs the new field name added to `candidates` manually or it will
  stop recognizing the loop as meeting the baseline-reference requirement.
- Precedent to mirror exactly (per the Decision Rationale's own citation): `abstain_on_exit_3`
  (ENH-3224) touches `fsm/schema.py`'s docstring `Attributes:` entry, the field declaration
  (line 123), the `to_dict()` skip-if-default emit (173-174), and `from_dict()` parse (235); no
  `fsm/executor.py` change is needed since the dispatcher receives `state.evaluate` as a whole
  config object (`executor.py:3150-3156`) and never unpacks individual fields itself. For a
  string-valued reference field (vs. `abstain_on_exit_3`'s bool), the closer sibling is `previous`'s
  `if self.previous is not None: result["previous"] = self.previous` / `previous=data.get("previous")`
  shape (schema.py:177-178, 237), and the `interpolate(config.previous, context)` +
  `try/except (InterpolationError, ValueError)` resolution block in `evaluate()`'s `convergence`
  branch (`fsm/evaluators.py:1908-1916`) is the exact shape a new frozen-reference field's
  resolution should mirror.

### Tests
- `scripts/tests/test_fsm_evaluators.py` — `TestComparatorEvaluator` (line 2357) and the
  `evaluate_convergence` call sites (lines 453-500) cover whichever evaluator the chosen option
  extends.
- `scripts/tests/test_harness_optimize.py` — rubric/behavior tests for the loop itself.

_Wiring pass added by `/ll:wire-issue` (Option A candidate wiring):_
- `scripts/tests/test_fsm_schema.py:262-278` (`test_schema_json_evaluate_config_properties_match_dataclass_fields`)
  will fail until `fsm-loop-schema.json` gets the matching property (see Files to Modify above) —
  the test itself needs no edit, only the schema file does. `test_fsm_schema.py:257-260`
  (`test_known_fields_helper_matches_dataclass_fields`) passes automatically once the field is
  declared — no edit needed there.
- `scripts/tests/test_fsm_evaluators.py::TestExitCodeEvaluator` (80-95) and the dispatcher-level
  `test_dispatch_exit_code_abstain_on_exit_3`/`test_dispatch_exit_code_without_abstain_flag`
  (~1601-1615) are the exact test shapes to mirror for a new field: one pair of raw-function tests
  in the matching `TestConvergenceEvaluator` class (448) proving default-unset behavior is
  unchanged and the field-set behavior differs, plus one dispatcher-level pair proving
  `interpolate()` resolution works (model: `test_dispatch_convergence_with_previous`, 657-663).
- `scripts/tests/test_fsm_fragments.py::TestConvergenceGateFragment` (1526-1610) is the template
  class to extend if the new field is threaded through the `convergence_gate` fragment description
  in `lib/common.yaml`.
- Test gap: no existing `FSMExecutor`-level test proves a captured value stays frozen across
  multiple loop iterations while a sibling captured value (like `prev_score`) keeps advancing —
  `test_fsm_executor.py:3207-3243` (`test_convergence_evaluator_tracks_progress`) only exercises
  the rolling `${prev.output}` shape. `test_harness_optimize.py:97-108`
  (`test_baseline_score_uses_run_benchmark_fragment`) is the closest existing precedent for the
  "seeded once, never reassigned" state shape, but it is a static/structural YAML-dict assertion,
  not a dynamic multi-iteration execution test — a new dynamic test is needed to prove the frozen
  field's value doesn't drift across iterations the way `capture_prev` does.

### Documentation
- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` — already hosts the MR-1..MR-14 design-rule table
  and baseline semantics (MR-2); natural home for the new rule.
- `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` — documents the existing `--baseline` vs.
  `check_comparator` distinction this guard sits beside.

_Wiring pass added by `/ll:wire-issue` (Option A candidate wiring):_
- `docs/reference/API.md:6009-6064` — the `#### EvaluateConfig` section reproduces every field as
  a code block; already stale relative to `schema.py` (omits `abstain_on_exit_3` from the code
  block itself) — add the new field here too, and note the existing drift for a future pass.
- `docs/generalized-fsm-loop.md:712-731` — the `convergence` evaluator-type section's worked YAML
  example and "Result details" line (`{ current, previous, target, delta }`) needs a new example
  line and a `details` update if the new field adds a details key.
- `docs/guides/LOOPS_REFERENCE.md:3489` — the `convergence_gate` fragment's field-contract table
  row ("optionally evaluate.previous, route.error") needs the new optional field added to its
  "optionally" list.
- `docs/reference/CLI.md:978` — the MR-2 rule prose ("a captured baseline value in
  `evaluate.previous`, `evaluate.target`, or `evaluate.source`") needs updating if the new field
  becomes an additional accepted baseline-reference site (see MR-2 `_has_baseline_reference` above).

### Related Issues (context, not this issue's scope)
- `ENH-1122` (deferred) — a *different* "frozen" concept (byte-region edit-mutation guard for
  `harness-optimize`'s own file edits) — do not conflate with this issue's frozen-evaluation-
  reference concept.
- `ENH-1793`/`ENH-1828`/`ENH-1829` (done) — existing comparator-evaluator-core and
  baseline-lifecycle CLI; the mechanism Option B would reuse.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-09 — based on codebase analysis:_

- The codebase's convention for testing a new optional `EvaluateConfig` field is a five-test cluster per field in `test_fsm_schema.py::TestEvaluateConfig` (see the `key` field cluster, lines 198-236): `test_<field>_field_default_none`, `test_to_dict_includes_<field>_when_set`, `test_to_dict_omits_<field>_when_none`, `test_from_dict_reads_<field>`, `test_<field>_roundtrip_serialization`.
- The `interpolate(...) → float() → except (InterpolationError, ValueError)` idiom at `fsm/evaluators.py:1908-1916` (already cited above) recurs three more times in the same dispatch function — `output_numeric`'s target (1876-1879), `convergence`'s target (1929-1932), and `convergence`'s tolerance (1945-1948) — confirming it as the codebase's one idiom for resolving an interpolated string to a float with a safe fallback, not a one-off.
- Confirmed test gap (strengthens the existing claim above): no test in `test_fsm_executor.py` constructs an FSM with one state capturing a value once outside a loop-back edge and a separate looping state resolving that captured value across multiple iterations while asserting it stays unchanged — every `convergence`-type executor test (`test_convergence_evaluator_tracks_progress`/`test_convergence_evaluator_detects_stall`, lines 3207-3279) uses a single self-looping state with a reseed-per-pass value.

## Program Design

### Types

- `reference: str | None = None` — new optional field on `EvaluateConfig`
  (`scripts/little_loops/fsm/schema.py`, beside `previous: str | None`); an interpolation
  string resolving to a float. Name chosen to parallel `previous`; nothing else on
  `EvaluateConfig` uses it, and it is deliberately not `baseline`/`baseline_path` to avoid
  conflation with the comparator evaluator's directory field.

### Signatures

- `evaluate_convergence(current: float, previous: float | None, target: float, tolerance: float = 0, direction: str = "minimize", reference: float | None = None) -> EvaluationResult`
  — existing function, new trailing keyword parameter; when `reference` is not `None` the
  regression comparison (Expected Behavior §2) runs before the target-reached check and
  returns `stall` with `details["regressed_vs_reference"] = True`.
- `EvaluateConfig.to_dict(self) -> dict[str, Any]` — emit `"reference"` only when set (mirrors `previous`).
- `EvaluateConfig.from_dict(cls, data: dict[str, Any]) -> EvaluateConfig` — `reference=data.get("reference")`.
- `_has_baseline_reference(fsm: FSMLoop, capture_names: set[str]) -> bool`
  (`fsm/validation/meta_rules.py`) — existing; `ev.reference` appended to its hand-built
  `candidates` list so MR-2 recognizes a loop whose only captured-baseline reference is via the
  new field.

### Call Path

`FSMExecutor` -> `evaluate()` (`fsm/evaluators.py` dispatcher, `convergence` branch) ->
resolves `config.reference` via `interpolate()`; on `InterpolationError`/`ValueError` with the
field set, returns `EvaluationResult(verdict="error", ...)` (fail-closed) -> otherwise
`evaluate_convergence(..., reference=<float>)` -> reference check -> target check -> previous
check. Consumers: `harness-optimize.yaml` `gate` (`route.stall: revert_and_log`) and, if kept
in scope, `rl-coding-agent.yaml` `score` (`route.stall: act`).

## Acceptance Criteria

- [ ] `evaluate_convergence(current=0.79, previous=0.85, target=0.80, tolerance=0.02, direction="maximize", reference=0.85)` returns `stall` with `details["regressed_vs_reference"] is True` — the target short-circuit no longer accepts a below-reference candidate.
- [ ] Same call with `reference=None` returns `target` (existing behavior unchanged); every pre-existing test in `TestConvergenceEvaluator` passes without edits.
- [ ] `current == reference` is not a regression in either direction; `minimize` direction treats `current > reference` as the regression.
- [ ] Dispatcher: `EvaluateConfig(type="convergence", reference="${captured.baseline.output}", ...)` with an unresolvable or non-numeric capture returns verdict `error` naming `reference`; with `previous` unresolvable and `reference` unset, behavior is unchanged (`previous` still falls back to `None`).
- [ ] New `FSMExecutor` test: a seed state captures a value once, a looping `convergence` state sets both `previous` (re-captured each pass) and `reference` (the seed capture) and runs ≥3 iterations; `details["reference"]` is identical on every iteration while `details["previous"]` advances.
- [ ] `test_fsm_schema.py::test_schema_json_evaluate_config_properties_match_dataclass_fields` passes (property added to `fsm-loop-schema.json`); the five-test `reference` cluster in `TestEvaluateConfig` (default-none / to_dict-includes / to_dict-omits / from_dict / roundtrip) passes.
- [ ] `ll-loop validate scripts/little_loops/loops/harness-optimize.yaml` passes with `reference` set in `gate`, and a synthetic loop whose *only* captured-baseline reference is `evaluate.reference` passes MR-2.
- [ ] `test_harness_optimize.py` asserts `gate.evaluate.reference == "${captured.baseline.output}"` and that no state other than `baseline_score` has `capture: baseline`.
- [ ] `rl-coding-agent.yaml` is either wired with a seed state and validates, or explicitly dropped with the reason logged in this issue's Session Log — never left with `reference` set and no capture.
- [ ] Docs updated per Integration Map → Documentation (`API.md` `EvaluateConfig` block, `generalized-fsm-loop.md` convergence section and `details` line, `LOOPS_REFERENCE.md` fragment table row, `CLI.md` MR-2 prose).
- [ ] `python -m pytest scripts/tests/` exits 0.

## Impact

- **Priority**: P3 - matches the filed priority; the concrete defect (a candidate within tolerance of `target_score` but below the baseline is committed by `harness-optimize.yaml`) is real but bounded — the loop cannot drift below `target - tolerance`.
- **Effort**: Medium - ~9 files across three layers (dataclass + JSON-schema mirror, evaluator + dispatcher, MR-2 validation, loop YAML) plus one new dynamic multi-iteration executor test with no existing precedent to mirror.
- **Risk**: Low - the field is optional and defaults to unset, leaving every existing `convergence` consumer byte-for-byte unchanged; the only behavioral change is in `harness-optimize.yaml`'s `gate`, where a previously-accepted regression now routes to the existing `revert_and_log` edge.
- **Breaking Change**: No

## Confidence Check Notes

_Added by `/ll:confidence-check` — 2026-09-09:_

**Readiness**: 92/100 (PROCEED WITH CAUTION) | **Outcome Confidence**: 72/100

### Concerns

- **Scope Boundaries is stale relative to the decision/wiring that happened after it was written.** The Summary and Scope Boundaries sections still frame this as a "stub" — "Out of scope: implementing the guard mechanism... this issue is a stub; implementation is a follow-up once scope is resolved." But `/ll:decide-issue` has since selected Option A with full scoring rationale, and `/ll:wire-issue` has fully wired the implementation (exact files, line numbers, test mirrors, doc updates, MR-2 candidates-list edit). The issue now contradicts itself on whether implementation belongs in this issue or a follow-up. Resolve before starting: either update Summary/Scope Boundaries to drop the "stub"/"out of scope" framing and confirm this issue is the implementation vehicle, or split implementation into a new issue as originally scoped.

### Outcome Risk Factors

- **Ambiguity (15/25)**: same scope-resolution question above is an execution risk, not just a documentation nit — an implementer could reasonably start the full Option A wiring in this issue, or stop and file a follow-up per the original scope text, and the file gives inconsistent guidance on which is correct.
  - _Resolved 2026-09-09 (manual review):_ this issue is the implementation vehicle. Summary,
    Scope Boundaries, Files to Modify, and Impact rewritten accordingly; `program_design_not_applicable`
    dropped and a Program Design + Acceptance Criteria section added. The review also found that
    the guard as originally described (checked "alongside `previous`") would be a no-op in
    `harness-optimize.yaml` — see Summary's corrected rationale and Expected Behavior's binding
    Guard semantics for the check ordering that actually fires.
- **Complexity (15/25)**: touches ~9-10 files across three layers (dataclass/evaluator schema, JSON-schema mirror + MR-2 meta-rule validation, loop YAML fragment) plus a genuinely new test shape — a dynamic, multi-iteration test proving the frozen field doesn't drift across iterations the way `capture_prev`/`prev_score` does. The closest cited precedent (`test_baseline_score_uses_run_benchmark_fragment`) is a static structural assertion, not the dynamic execution test this needs, so that test has to be authored from scratch rather than mirrored.

## Status

**Open** | Created: 2026-09-09 | Priority: P3


## Session Log
- `/ll:confidence-check` - 2026-09-09T16:33:20 - `3bf7ddf5-f1c3-4461-90f7-4d411c62ae41.jsonl`
- `/ll:refine-issue` - 2026-09-09T16:20:49 - `fa9f7cba-187f-4268-b323-59e2fd18c32b.jsonl`
- `/ll:confidence-check` - 2026-09-09T15:01:48 - `4490c2ea-90df-42ee-8816-5029d9abb8d8.jsonl`
- `/ll:wire-issue` - 2026-09-09T14:51:25 - `8e56ec89-cd99-46e0-b932-f07e5ea9315c.jsonl`
- `/ll:decide-issue` - 2026-09-09T14:19:44 - `79d7b43c-377f-45d3-9e5c-2fc5ef853497.jsonl`
- `/ll:refine-issue` - 2026-09-09T14:08:38 - `1658f0c5-d510-42b4-beb1-234626dbd6e5.jsonl`
- `/ll:format-issue` - 2026-09-09T13:23:21 - `94cf9e94-a0b2-480c-8238-e366777de95e.jsonl`
