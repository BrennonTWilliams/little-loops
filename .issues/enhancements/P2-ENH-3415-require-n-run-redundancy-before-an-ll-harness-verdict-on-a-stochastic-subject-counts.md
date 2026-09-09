---
id: ENH-3415
title: Require n-run redundancy before an ll-harness verdict on a stochastic subject
  counts
type: ENH
priority: P2
status: open
discovered_date: '2026-09-08'
labels:
- harness
- evaluation
- statistics
decision_needed: false
confidence_score: 95
outcome_confidence: 48
score_complexity: 10
score_test_coverage: 18
score_ambiguity: 10
score_change_surface: 10
---

## Summary

`ll-harness` evaluates a runner one-shot: a single pass against exit-code and semantic criteria produces a pass/fail verdict. But the subject under test is an LLM-driven runner whose behavior varies run to run, so a one-shot verdict certifies only "this runner passed once" — a lucky sample is indistinguishable from a real capability, and any promotion decision resting on it is unsound.

Require redundancy as structure, not as optional rigor: a verdict on a stochastic subject does not count until the criterion has been evaluated over n samples, and the harness reports pass-rate-over-n rather than a bare pass/fail. The threshold and the reporting change travel together — reporting a rate without requiring a minimum n just relabels the same weak evidence, and requiring n without surfacing the rate throws away the variance information the extra runs bought.

Scope: identify which runner types have stochastic subjects (a deterministic `cmd` runner should not pay for n samples it does not need), define the default n and how it is overridden per criterion, and decide what the verdict surface looks like when the rate lands between clear pass and clear fail.

## Current Behavior

`ll-harness` evaluates a runner one-shot via `_evaluate_and_report()`
(`scripts/little_loops/cli/harness.py:789`), which returns `(exit_code,
HarnessEvalOutcome)` where `HarnessEvalOutcome.passed: bool`
(`cli/harness.py:671-675`) is set from a single invocation of the runner
against `--exit-code` and `--semantic` criteria. There is no sampling loop:
one run produces one pass/fail verdict, for both deterministic `cmd` runners
and stochastic LLM-driven runners alike.

## Expected Behavior

For a `RunnerType` (`scripts/little_loops/runner_spec.py:59`) classified as
stochastic, the harness runs the criterion n times and reports a
pass-rate-over-n instead of a single `passed: bool`. A deterministic `cmd`
runner still gets a one-shot verdict — n stays 1 for it. A default n and a
per-criterion override are configurable, and a rate landing between clear
pass and clear fail is reported as its own explicit state rather than rounded
to pass/fail. Preflight capability probes may still stop on first
confirmation; verdicts that gate promotion may not.

## Why redundancy has to be structural

The argument comes from evolutionary-search harnesses that select a candidate on a measured fitness signal. Two guards recur in those systems, and both are treated as *mandatory structure of the loop* rather than as extra rigor a careful operator adds:

- **N-sample redundancy.** High-variance evaluation environments produce flukes. Mandating multiple evaluations per unique match-up is what stops a single lucky win from promoting a candidate — the thing that separates principled selection from prompt-and-hope.
- **A frozen external reference.** A candidate is tested against both the incumbent and an unchanged baseline, so a lineage cannot drift into a self-referential local optimum where every generation only beats its immediate parent.

Neither is novel as statistics. What is worth copying is the posture: the loop is not considered runnable without them. The second guard is out of scope here and belongs in its own issue; this issue supplies the first.

## Dependencies and tensions to resolve explicitly

This sits directly on top of the harness run model that defines how an attempt is recorded against a named cell — as a repetition, an infrastructure retry, or a continuation, with only repetitions incrementing n. That model deliberately leaves the threshold open. This issue supplies the missing half: how large n must be before the harness will certify anything.

It also resolves a standing tension with the capability-preflight work, whose stop-on-first-confirmation is a budget policy pulling in the opposite direction. The two need an explicit boundary — **preflight capability probes may stop early; verdicts that gate promotion may not** — because leaving it implicit means whichever code path runs last silently wins.

The existing score-reproducible-not-byte-reproducible stance on judging stochastic agent runs is the auditing posture this makes mechanical: that stance says what a verdict on a stochastic subject may claim, and this issue supplies the mechanism that makes the claim true.

## Scope Boundaries

- **In scope**: classifying `RunnerType` members as stochastic vs. deterministic, a default n plus a per-criterion override, the pass-rate-over-n verdict surface, defined behavior for a rate landing between clear pass/fail, and the preflight-vs-promotion boundary.
- **Out of scope**: the frozen-external-reference / baseline guard described in "Why redundancy has to be structural" — that guard is explicitly called out as belonging to its own issue. Also out of scope: redefining the underlying attempt-recording model (repetition vs. infra-retry vs. continuation) referenced in "Dependencies and tensions to resolve explicitly" — this issue consumes that model's `n`, it does not change how attempts are classified.

## Proposed Solution

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-09 — based on codebase analysis:_

The current Program Design → Call Path/Signatures describe `_evaluate_and_report()` itself looping n times, but codebase research (see Integration Map → Files to Modify, Program Design → Call Path) found that function only ever receives an already-computed `RunnerResult` — it has no callable or spec it could re-invoke. Restructuring where the sampling loop lives is a genuine fork, not a detail:

**Option A**: Refactor `_evaluate_and_report()` to accept the action spec plus a runner-invocation callable (e.g. `ActionSpec` and `run_action`/`_run_prompt_action`), so it owns the n-sample loop internally and populates `pass_rate` itself. Keeps each `cmd_*` handler's call site to a single call.

**Option B**: Keep `_evaluate_and_report()`'s signature as pure grading-of-one-result. Add a new sampling loop at each of the five `cmd_*` call sites that wraps the pair of calls (`run_action()`/`_run_prompt_action()` + `_evaluate_and_report()`) n times for a stochastic `RunnerType`, aggregating pass/fail counts across the n calls before deriving `pass_rate` and constructing one final `HarnessEvalOutcome`.

> **Selected:** Option B — leaves `_evaluate_and_report()`'s single-result contract intact and follows the `cmd_dsl` per-function sampling-loop precedent; scored higher than Option A on codebase fit and risk (see Decision Rationale below).

**Recommended**: Option B — `HarnessEvalOutcome` and `_evaluate_and_report()` have zero consumers outside `cli/harness.py` (see Integration Map → Dependent Files), so either option is low-blast-radius, but Option B leaves `_evaluate_and_report()`'s existing single-result contract intact and localizes the new looping logic to the five call sites, which already duplicate the runner-invocation-then-evaluate shape today.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-09-08.

**Selected**: Option B — loop at the five `cmd_*` call sites

**Reasoning**: Option B preserves `_evaluate_and_report()`'s existing single-result contract and follows the `cmd_dsl` precedent (`cli/harness.py:1223-1340`) of a loop wrapping invoke+evaluate calls that tallies pass/fail counts inside a `cmd_*` function, reusing `wilson_ci` (`stats.py:14`, already used the same way at `cli/harness.py:1374`) for the rate. Option A's single-injected-callable design collides with two already-divergent runner-invocation shapes in the codebase today (`run_action()` vs. `_run_prompt_action()`) and with post-call state (`duration_ms`, `_record_harness_event` inputs) that currently lives outside `_evaluate_and_report()` at each call site — not a mechanical drop-in. Option B's per-site duplication is a real but contained cost, addressable later via extraction the same way `_run_prompt_action()` itself was (BUG-3196).

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option A (loop inside `_evaluate_and_report()`) | 1/3 | 1/3 | 2/3 | 1/3 | 5/12 |
| Option B (loop at `cmd_*` call sites) | 2/3 | 2/3 | 1/3 | 2/3 | 7/12 |

**Key evidence**:
- Against the rejected approach: `run_action`'s uniform `Callable[[ActionSpec], RunnerResult]` dispatch (`runner_spec.py:395-399`) exists, but `cmd_prompt`/`cmd_dsl` already call the divergent `_run_prompt_action()` wrapper instead, and `duration_ms`/event-recording inputs live outside `_evaluate_and_report()` at every call site today.
- For the winner: `cmd_dsl`'s existing task-file loop (`cli/harness.py:1223-1340`) is a direct structural precedent for a per-function invoke+evaluate+tally loop; the four non-DSL `cmd_*` handlers already duplicate near-identical boilerplate, so a per-site loop compounds existing duplication rather than introducing a new pattern.

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-09 — based on codebase analysis:_

Findings below are grouped by the Integration Map's own subsections.

### Files to Modify
- `scripts/little_loops/cli/harness.py` — `HarnessEvalOutcome` dataclass (decorator `:670`, class `:671`, fields `:674-677`: `passed: bool`, `verdict: str | None`, `eval_result: EvaluationResult | None`, `abstained: bool = False`) needs a new `pass_rate` field; `_evaluate_and_report()` (`:789-926`) grades one already-computed `RunnerResult` and has no loop over multiple runner invocations
- `scripts/little_loops/cli/harness.py` — five `cmd_*` handlers (`cmd_skill` `:951`, `cmd_cmd` `:1000`, `cmd_mcp` `:1042`, `cmd_prompt` `:1120`, `cmd_dsl` `:1156`) each call `run_action()`/`_run_prompt_action()` exactly once before `_evaluate_and_report()` — a sampling loop must wrap the runner invocation together with the grading call at each site (see Program Design → Call Path correction below), not live inside `_evaluate_and_report()` alone
- `scripts/little_loops/runner_spec.py` — `RunnerType` enum (`:59-67`: `SKILL, CMD, MCP, PROMPT, DSL, LOOP`) has no stochastic/deterministic classification anywhere; `_DISPATCH` (`:395-399`) only maps `SKILL, MCP, PROMPT` to handlers, `CMD` is special-cased (`:433-434`), `LOOP` is never dispatched by `run_action()` (module docstring `:12-22`)
- `scripts/little_loops/stats.py` — `wilson_ci(k, n, z=1.96)` (`:14`) already computes a rate + 95% CI and is already imported/used by `cmd_dsl()`'s pass-rate reporting (`cli/harness.py:1374-1375`) — reusable for this issue's pass-rate-over-n rather than a new statistic
- `scripts/little_loops/fsm/executor.py` — no existing "run N times, need M successes" redundancy gate (searched for `max_attempts|min_successes|repeat|n_runs|redundan` — no hits); closest concept is `circuit.repeated_failure`, a stall *detector* on repeated failed states, not a required-successes-out-of-N sampling gate — this issue is not a port of existing FSM redundancy logic

### Conventions in Force
- Enum-to-boolean classification has two coexisting shapes in this codebase, not one: a module-level dict keyed by every enum member (`_AXIS_NEEDS_SYMBOL`, `scripts/little_loops/issues/research_triage.py:97`) vs. a `@property` computed from a single `is` comparison colocated on the value object (`ExpectedGrade.passed`, `cli/harness.py:287-308`) — `is_stochastic_runner(runner: RunnerType) -> bool` can follow either; `RunnerType`'s own `_DISPATCH` (`runner_spec.py:395`) is a third, incomplete precedent (omits `CMD`/`LOOP` by design)
- A rate landing between clear pass/fail already has a codebase precedent for being reported as its own explicit third state rather than rounded: `paired_direction()` (`stats.py:43,76-79`) returns `"inconclusive"` when the Wilson CI straddles 0.5; `_evaluate_and_report()` itself already has a documented FAIL > ABSTAIN > PASS precedence (`cli/harness.py:832-845`)
- A configurable default-with-override for a numeric threshold already exists in the loop `context:`/`parameters:` shape (`loops/oracles/code-run-gate.yaml:63-68,104,291` — `min_pass_rate` default 0.95, overridable per invocation), a sibling convention to a plain CLI-flag default (`_add_evaluator_flags()`, `cli/harness.py:482-542`) — the codebase has both shapes and does not consolidate them
- No named-criterion list exists today: `_add_evaluator_flags()` (`cli/harness.py:482`) gives exactly one `--exit-code` slot and one `--semantic` slot per invocation, so "a per-criterion n override" would be a new mechanism layered on top of a flat two-criterion flag set, not an extension of an existing list

### Tests
- `scripts/tests/test_cli_harness.py` — no test currently exercises `HarnessEvalOutcome.pass_rate` or a `RunnerType` stochastic classification (neither exists yet); `TestAbstentionVerdict` (`:851`) is the closest structural precedent for testing a new multi-way verdict surface (patches `evaluate_llm_structured`, asserts exit code + stdout substring); CMD-runner tests mock `subprocess.Popen`/`selectors.DefaultSelector` at the `runner_spec` module boundary rather than mocking `_run_cmd` itself, with no existing example of chaining multiple mock invocations for N-sample tests
- `scripts/tests/test_stats.py` — one `Test<FunctionName>` class per function, covering boundary cases (`k=n`, `k=0`, `n=1`) via parametrized `cases` lists — the convention a new stats helper for this issue would follow
- `scripts/tests/test_runner_spec.py` — 34 existing references to `RunnerType`; would need new cases for a stochastic/deterministic classification function

_Wiring pass added by `/ll:wire-issue`:_
- **Tests that will break on the literal PASS/FAIL/ABSTAIN report text** once a rate-based verdict is introduced — `TestCmdSkill.test_skill_pass_no_criteria` (`:187`, asserts `"PASS" in out` `:202`), `test_skill_exit_code_fail` (`:236`, `"FAIL" in out` `:248`), `TestCmdCmd.test_cmd_exit_code_fail` (`:407`, `:421`), `test_cmd_json_output` (`:462`, `data["result"] == "PASS"` `:477`), `TestSemanticEvaluator.test_semantic_yes_passes` (`:779`, `:799`), `test_semantic_non_yes_fails` (`:803`, `:823`), `TestAbstentionVerdict.test_semantic_abstain_exits_3` (`:855`, `:875`), `test_exit_code_fail_dominates_semantic_abstain` (`:877`, `:899`), `TestMainHarness.test_main_harness_json_output` (`:970`, `:985`) — all in `scripts/tests/test_cli_harness.py`; whichever `RunnerType`s `is_stochastic_runner()` classifies as stochastic determines which of these actually break
- **Single-mock-invocation tests that need `side_effect=[...]` conversion** for an n-sample loop (no existing example of this chaining pattern in the file): `TestCmdSkill.test_skill_pass_no_criteria/test_skill_exit_code_pass/test_skill_exit_code_fail` (`:187,224,236`, patch `subprocess.run`), `TestCmdCmd.test_cmd_exit_code_pass/test_cmd_exit_code_fail/test_cmd_no_criteria_always_pass` (`:393,407,423`, patch `Popen`/`DefaultSelector`), `TestCmdMcp.test_mcp_tool_error_exit_code/test_mcp_exit_code_criterion_fail` (`:643,655`, patch `call_mcp_tool`), `TestCmdPrompt.test_prompt_sends_request` (`:676`, patches `subprocess.run` and indexes `captured_prompt[0]`, assuming exactly one call)
- `scripts/tests/test_runner_spec.py:102-111` — `TestRunnerTypeCompleteness.test_all_harness_runner_kinds_present` and `test_loop_not_in_dispatch_table` are the exact existing precedent for a per-`RunnerType`-member classification/exclusion test; a new `is_stochastic_runner()` completeness test should follow this shape
- `scripts/little_loops/stats.py:43-79` (`paired_direction()`) and its test `TestPairedDirection` (`scripts/tests/test_stats.py:113`) — a closer structural precedent than `wilson_ci` alone: it tallies raw pass/fail counts, calls `wilson_ci`, then collapses the CI into a discrete three-way verdict (`"inconclusive"` when the CI straddles 0.5) — the same tally-then-threshold-to-discrete-state shape this issue's "rate landing between clear pass and clear fail" behavior needs
- Correction: `TestCmdDsl` (`scripts/tests/test_cli_harness.py:1070`, ~33 methods over `cmd_dsl`'s existing multi-invocation loop) is a stronger n-sample-loop precedent than `TestAbstentionVerdict` — `test_cmd_dsl_directory_scans_yaml_files` (`:1134`) asserts an N-of-M count string (`"3/3"`); `test_cmd_dsl_partial_abstain_flips_pass_to_inconclusive` (`:1181-1210`) already uses a **per-call-varying mock** (`verdicts = iter([...])` + `side_effect=lambda **_: next(verdicts)`) — the exact chaining pattern the issue text claims has no existing example, just applied to `evaluate_llm_structured` rather than `subprocess.run`/`RunnerResult`; `test_cmd_dsl_wilson_ci_in_output` (`:1567-1581`) asserts `"95% CI" in out`, the pattern a new `pass_rate` report line should follow (substring, not numeric-bounds, assertion)
- Gap confirmed: no fixture/helper anywhere in the repo builds a *list* of fake `RunnerResult`/`CompletedProcess` objects for multi-call mocking (`FakeRunner`/`_make_completed()` in both `test_cli_harness.py:30-61` and `test_runner_spec.py:30-42` each produce one fixed result); a new n-sample test for the four non-DSL `cmd_*` handlers needs to write a `side_effect=[...]` list or `iter()`+lambda pattern fresh for `subprocess.run`/`Popen`

### Dependent Files (Callers/Importers)
- `cli/harness.py:951` — `cmd_skill()` calls `_evaluate_and_report()` at `:972`
- `cli/harness.py:1000` — `cmd_cmd()` calls `_evaluate_and_report()` at `:1019`
- `cli/harness.py:1042` — `cmd_mcp()` calls `_evaluate_and_report()` at `:1077`
- `cli/harness.py:1120` — `cmd_prompt()` calls `_evaluate_and_report()` at `:1132`
- `cli/harness.py:1156` — `cmd_dsl()` calls `_evaluate_and_report()` at `:1289` (looped over distinct task files, not the same-subject resampling this issue introduces)
- `cli/harness.py:983-984,1027-1028,1085-1086,1140-1141,1321-1322` — the only readers of `HarnessEvalOutcome.passed/verdict/abstained`, each immediately after its `_evaluate_and_report()` call site, feeding `_record_harness_event()`
- `HarnessEvalOutcome` has zero consumers outside `cli/harness.py` itself (repo-wide grep for the class name) — the "Breaking Change" in Impact is narrowly scoped to this one file
- `queue_store.py` and `cli/queue.py` import `RunnerType` from `runner_spec.py` but have zero references to "harness" — not coupled to this issue's verdict-surface change

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/action.py:218` and `scripts/little_loops/cli/loop/run.py:130` — additional `RunnerType` importers beyond `queue_store.py`/`cli/queue.py`; confirmed not coupled to the harness-verdict change (use `RunnerType` only for generic runner dispatch, never reference `HarnessEvalOutcome`)
- `scripts/little_loops/session_store/writers.py:1109-1170` — `record_harness_event()` takes `semantic_passed: bool | None` (`:1117`) and coerces `outcome.passed` to a single `int` (`:1075` in `cli/harness.py`) before insert; the DB write path assumes one bool sample per invocation, not an n-sample rate
- `scripts/little_loops/session_store/schema.py:717-729` — `harness_events` table DDL (`semantic_verdict TEXT`, `semantic_passed INTEGER`); a comment at `:1005` cites `harness_eval_pass_rate()`'s `COUNT(semantic_passed)` denominator, which assumes each row is one independent bool sample
- `scripts/little_loops/history_reader/harness.py:67-68,228-290` — `harness_eval_pass_rate()`'s SQL (`SUM(CASE WHEN semantic_passed = 1 ...)/COUNT(semantic_passed)`) computes a *historical, across-invocation* rate from these per-row bools — a distinct concept from this issue's new *intra-invocation* n-sample `pass_rate`, but reading the same `semantic_passed` column this issue's write path populates
- `scripts/little_loops/history_reader/__init__.py:122,192,320` — barrel re-export of `harness_eval_pass_rate`
- `scripts/tests/test_session_store_writers.py:2220-2244`, `scripts/tests/test_session_store_schema.py:1590-1591`, `scripts/tests/test_history_reader_harness.py` (extensive `semantic_passed=` usage) — existing tests over this persistence path
- `scripts/little_loops/loops/lib/common.yaml` — `harness_exit` fragment (`:23-29`) hard-codes the current single-trial exit-code contract ("0=pass, 1=fail, 3=abstained") as an `on_yes`/`on_no`/`on_cannot_judge` routing precondition; consumed by `scripts/little_loops/loops/test-coverage-improvement.yaml`, `incremental-refactor.yaml`, and `dead-code-cleanup.yaml` — any change to what triggers exit 0 vs 1 for a stochastic-subject rate verdict is a direct behavioral dependency for these loops
- Clarification: those 3 loops' `verify_tests.action` shells out to the project's own `test_cmd` (`sh -c`/`bash -c`), not to `ll-harness` itself — confirmed by `scripts/tests/test_builtin_loops.py`'s `TestDeadCodeCleanupVerifyTestsResolution`/`TestTestCoverageImprovementVerifyTestsResolution`. The `harness_exit` fragment's 0/1/3 contract is a shared/parallel convention, not a live `ll-harness` CLI call site for these three — the actual enforcement-level touchpoints are the FSM symbols listed below.
- `scripts/little_loops/cli/logs.py` — `_fixture_to_harness_argv()`/`_cmd_eval_export()`/`_build_eval_fixture()` (~`:1972-2018`) reconstruct an `ll-harness <runner> <target> [--exit-code N] [--semantic TEXT] [--timeout S]` invocation from session JSONL logs (decision `ARCHITECTURE-017`); has no notion of a new n-sample/redundancy flag, so a CLI-level flag this issue adds must also be threaded here or fixture round-trips silently drop it. Tested by `scripts/tests/test_ll_logs.py::TestEvalExportHelpers::test_fixture_to_harness_argv_round_trips_through_parser` and `TestEvalExportRoundTrip::test_export_then_replay_under_harness`
- The single-trial `0/1/3` exit-code contract the `harness_exit` YAML fragment describes in prose is also implemented as first-class FSM engine code — the actual enforcement points if a stochastic-subject verdict introduces a new exit code (e.g. an "inconclusive rate" band): `EvaluateConfig.abstain_on_exit_3` (`scripts/little_loops/fsm/schema.py:123`, docstring `:65-68`), `evaluate_exit_code(exit_code, abstain_on_exit_3=False)` (`scripts/little_loops/fsm/evaluators.py:176-202`, hard-codes `0→yes,1→no,3→cannot_judge(opt-in),else→error`), its 3 call sites (`evaluators.py:1870` dispatcher — threads the flag; `fsm/executor.py:3114` default shell-evaluator path — does not thread it; `cli/loop/testing.py:128` `ll-loop test` simulate fallback — does not thread it), and the ENH-3222 structural-lint pair `_is_abstention_capable()`/`_validate_abstention_route()` (`scripts/little_loops/fsm/validation/structural_rules.py:1619-1638,1663+`) that requires an `on_cannot_judge`/`on_error` route wherever `abstain_on_exit_3` is set — none of these recognize a 4th/5th code today

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md` — `### ll-harness` section (`:212`): the summary line (`:214`, "One-shot runner evaluation CLI ... exits `0` (PASS) / `1` (FAIL) / `2` (error/timeout)"), the exit-code list (`:254`), and the `--output json` payload fields table (`:257-269`) all describe single-trial semantics this issue changes for stochastic `RunnerType`s; the `dsl` runner's row (`:224`) already documents rate-based reporting and is the closest existing precedent, but the other four runner rows (`:220-223`) have no rate-reporting language yet
- `docs/reference/API.md:8992` — `_evaluate_and_report()` prose describing the *existing* `history_pass_rate`/`history_admissions` fold-in (ENH-3223) into the same `--output json` payload this issue adds a new `pass_rate` field to; needs a sentence distinguishing the new intra-invocation rate from this existing across-invocation historical rate
- `docs/reference/API.md:6144-6146` — second citation of the `harness_exit` fragment / exit-code contract (see `loops/lib/common.yaml` above)
- `docs/guides/EVALUATION_GUIDE.md` — the "Four runners, all with the same evaluation flags" / shared exit-code-contract prose (`:60-69`), the `passed`-scalar description (`:83-85`, note: its own cited line anchor `harness.py:419-433` is already stale — the code is now at `:805`), the Result/Exit/Semantic single-run table (`:301-309`), the `history_pass_rate` proximity (`:314-323,469`); the term "stochastic" (central to this issue's classification) appears nowhere in `docs/` today and needs introducing, not just patching
- **Naming-collision risk**: `docs/reference/API.md:8986` records that this codebase already renamed `harness_eval_pass_rate` (not `harness_pass_rate`) specifically to avoid colliding with `ab_writer.ABResults.harness_pass_rate`, an unrelated in-memory field. The Program Design's proposed `HarnessEvalOutcome.pass_rate` would sit in the identical `--output json` payload dict (`harness.py:876-891`) alongside the existing `history_pass_rate`/`history_pass_rate_runs` fields — the same kind of proximity that precedent was renamed to avoid. Flagging for the implementer to consider a more distinguishing name (e.g. `sample_pass_rate`) rather than adopting `pass_rate` unexamined.
- Concrete `harness_pass_rate` collision sites beyond `ab_writer.py` itself: field definitions `scripts/little_loops/ab_writer.py:146-147,194-195,221-222,265-266`; emitted in an `ab_summary` event at `scripts/little_loops/fsm/executor.py:4348`; read at `scripts/little_loops/cli/loop/summary.py:57` and `scripts/little_loops/cli/loop/info.py:240`; schema-described at `scripts/little_loops/generate_schemas.py:286-291` — all unrelated A/B baseline-comparison reporting, not `HarnessEvalOutcome`, but confirms the collision surface is wider than one file.
- `docs/reference/EVENT-SCHEMA.md` — "CLI exit-code conventions" section (~`:1795`) has an `ll-harness`-specific bullet describing `RunnerResult.exit_code`/`timed_out` single-invocation semantics and the ENH-3407 `--retry-of` admissibility gate reading the persisted `timed_out` column — a fourth doc site (beyond CLI.md/API.md/EVALUATION_GUIDE.md) reasoning about one-exit-code-per-invocation that needs updating for a pass-rate-over-n surface.
- `docs/generalized-fsm-loop.md:641-646` — cites the `harness_exit` fragment as the worked example for `abstain_on_exit_3`/`on_cannot_judge`; a fifth doc site describing the current single-trial contract.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Resolve how a stochastic subject's n-sample outcome persists through `record_harness_event()`/`harness_events` (session_store schema stores one `semantic_passed` bool per row) — decide whether each sample becomes its own row, only the aggregate rate is recorded, or both, and whether `harness_eval_pass_rate()`'s historical rollup semantics need to change as a result. Not addressed anywhere in the current Acceptance Criteria.
- Update `loops/lib/common.yaml`'s `harness_exit` fragment (and verify `test-coverage-improvement.yaml`/`incremental-refactor.yaml`/`dead-code-cleanup.yaml` still route correctly) for whatever exit-code contract a stochastic-subject rate verdict produces.
- Update `docs/reference/CLI.md` (`### ll-harness` section), `docs/reference/API.md` (`:8992`, `:6144-6146`), and `docs/guides/EVALUATION_GUIDE.md` (four-runner exit-code prose, `passed`-scalar description, Result/Exit/Semantic table) to describe the new pass-rate-over-n verdict surface and define "stochastic" for the first time.
- Decide the `pass_rate` field name in light of the `history_pass_rate` naming-collision risk above before implementing `HarnessEvalOutcome`'s new field.
- Convert the single-mock `return_value=` patches in the at-risk tests below to `side_effect=[...]` lists of length n wherever the covered `RunnerType` is classified stochastic.
- Thread `EvaluateConfig.abstain_on_exit_3`/`evaluate_exit_code()`'s exit-code contract change (if a stochastic-subject verdict introduces a new code, e.g. for an inconclusive rate band) through its 3 call sites — `fsm/evaluators.py:1870` dispatcher, `fsm/executor.py:3114` default shell-evaluator path, and `cli/loop/testing.py:128` `ll-loop test` simulate fallback — and extend the ENH-3222 structural-lint pair `_is_abstention_capable()`/`_validate_abstention_route()` (`fsm/validation/structural_rules.py:1619-1638,1663+`) to recognize the new code, or a new state authored against it will silently lack a required route.
- Update `cli/logs.py`'s `_fixture_to_harness_argv()`/`_cmd_eval_export()`/`_build_eval_fixture()` (~`:1972-2018`) if this issue adds a new CLI flag (e.g. `--samples`/`-n`) — these currently reconstruct `ll-harness` invocations with no notion of such a flag, so log-derived fixture round-trips would silently drop it; verify against `scripts/tests/test_ll_logs.py::TestEvalExportHelpers::test_fixture_to_harness_argv_round_trips_through_parser`.
- Update `docs/reference/EVENT-SCHEMA.md` (~`:1795`, "CLI exit-code conventions") and `docs/generalized-fsm-loop.md:641-646` alongside the other three doc files already listed above — both describe the current single-trial `ll-harness` exit-code contract.

## Program Design

### Types

- `RunnerType` (`scripts/little_loops/runner_spec.py:59`) — existing enum (`CMD`, `SKILL`, `MCP`, `PROMPT`, `DSL`, `LOOP`); each member gets a stochastic/deterministic classification
- `HarnessEvalOutcome.pass_rate: float | None` — new field alongside the existing `passed: bool` (`cli/harness.py:671-675`)

### Signatures

- `_evaluate_and_report(runner_label: str, result, args) -> tuple[int, HarnessEvalOutcome]` (`cli/harness.py:789`) — loop the criterion n times for a stochastic `RunnerType` and populate `pass_rate`
- `is_stochastic_runner(runner: RunnerType) -> bool` — new; backs the default-n/override lookup

### Call Path

`cmd_run` (`cli/harness.py`) -> `is_stochastic_runner` -> `_evaluate_and_report` (looped n times when stochastic) -> `HarnessEvalOutcome`

- Confirmed correction: no unified `cmd_run` function exists — the five call sites are `cmd_skill`, `cmd_cmd`, `cmd_mcp`, `cmd_prompt`, `cmd_dsl` (`cli/harness.py:951,1000,1042,1120,1156`), each invoking `run_action()`/`_run_prompt_action()` exactly once before calling `_evaluate_and_report()`. `_evaluate_and_report()` receives an already-computed `RunnerResult` with no callable/spec it could re-invoke, so a sampling loop must wrap the runner invocation together with the grading call at each `cmd_*` site — it cannot live inside `_evaluate_and_report()` alone without also changing what that function receives (see Proposed Solution → Codebase Research Findings for the resulting decision point).

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-09 — based on codebase analysis:_

- Precise anchor correction: `HarnessEvalOutcome` dataclass is at `cli/harness.py:670` (decorator), `:671` (class), fields `:674-677` — the Types section above cites `:671-675`, off by a few lines from the fields themselves
- `RunnerType` full member list (`runner_spec.py:59-67`): `SKILL, CMD, MCP, PROMPT, DSL, LOOP`. `_DISPATCH` (`:395-399`) maps only `SKILL, MCP, PROMPT` to handlers; `CMD` is special-cased via `is`-comparison (`:433-434`); `LOOP` is never dispatched by `run_action()` at all (module docstring `:12-22`, `run_action()` docstring `:423-431` — FSM `PersistentExecutor` drives it instead)
- Deterministic vs. LLM-driven split confirmed at the implementation level: `_run_cmd()` (`:240-357`) shells out via `subprocess.Popen`, no LLM involved. `_run_skill()` (`:106-237`) and `_run_prompt()` (`:375-392`) both invoke `resolve_host().build_streaming(...)`/`build_blocking_json(...)` — an LLM host CLI. `_run_mcp()`/`call_mcp_tool()` (`:359-372`) is an arbitrary tool call, not itself an LLM invocation, but is dispatched alongside the LLM-driven runners
- No default-n or minimum-n constant, config key, or CLI flag exists anywhere in the tree for this purpose (searched `config-schema.json`, `_add_evaluator_flags()`, `session_store/schema.py` migrations). `_HISTORY_MIN_SCORED = 3` (`cli/harness.py:698`) is unrelated — a display-suppression threshold for the historical-rate line, not a sampling gate
- The attempt-recording model this issue sits on top of (ENH-3397/3406/3407/3408, all `status: done`) explicitly deferred any default/minimum n as future work in its own Scope Boundaries and Design Decisions — confirms no other issue already owns defining n
- Reusable statistic: `wilson_ci(k, n, z=1.96)` (`scripts/little_loops/stats.py:14`) is already imported and used by `cmd_dsl()`'s pass-rate reporting (`cli/harness.py:1374-1375`) for a rate + 95% CI — available to reuse for this issue's pass-rate-over-n rather than a new statistic
- Existing three-state precedent for "a rate landing between clear pass and clear fail": `paired_direction()` (`stats.py:43`, `:76-79`) returns an explicit `"inconclusive"` when the Wilson CI straddles 0.5, rather than rounding to either side; `_evaluate_and_report()` itself already has a documented FAIL > ABSTAIN > PASS precedence (`cli/harness.py:832-845`). No existing function bands a *continuous rate* against two thresholds into pass/fail/ambiguous — that piece is new
- No existing FSM "run N times, need M successes" redundancy gate (searched `fsm/executor.py` for `max_attempts|min_successes|repeat|n_runs|redundan` — no hits); closest is `circuit.repeated_failure`, a stall detector on repeated failed states, not a required-successes-out-of-N gate
- "score-reproducible-not-byte-reproducible" and "stop-on-first-confirmation" appear only in issue prose (ENH-3397, this issue) — no code or doc states either concept under that name anywhere in `scripts/` or `docs/`. The capability-preflight subsystem this issue draws a boundary against is `ll-doctor`/FEAT-1496 (decomposed into FEAT-1523/1503/1504); the closest actual first-match-wins code is `host_runner.py::resolve_host()`'s `_PROBE_ORDER` loop, which is host-CLI auto-detection, unrelated to runner-evaluation

## Acceptance Criteria

- Runner types are classified as stochastic or deterministic, and only stochastic subjects incur n samples; a deterministic `cmd` runner's cost is unchanged.
- A default n is defined, and a per-criterion override mechanism exists.
- The harness verdict surface reports pass-rate-over-n. A bare pass/fail is no longer emitted for a stochastic subject.
- The behavior for a rate landing between clear pass and clear fail is specified rather than left to the caller.
- The preflight-vs-promotion boundary is stated in code and enforced: early stop on first confirmation is permitted for capability probes and refused for verdicts that gate promotion.

## Impact

- **Priority**: P2 - a stochastic verdict today certifies a lucky sample rather than a real capability; not yet gating a live promotion decision, but any harness-driven promotion built on the current one-shot verdict is unsound.
- **Effort**: Medium - touches `_evaluate_and_report` and its call sites in `cli/harness.py` plus a new runner classification table; no new subsystem.
- **Risk**: Medium - changes the harness verdict surface (bare pass/fail -> pass-rate-over-n) for a stochastic subject, a behavior change for any caller currently pattern-matching on `HarnessEvalOutcome.passed`.
- **Breaking Change**: Yes - `HarnessEvalOutcome` gains a field, and stochastic-subject callers must switch from bare pass/fail to a rate.

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-09-08_

**Readiness Score**: 95/100 → PROCEED
**Outcome Confidence**: 48/100 → LOW

### Outcome Risk Factors
- Persistence strategy for the n-sample outcome is unresolved: the Wiring Phase flags a genuine open decision (each sample as its own `harness_events` row vs. only the aggregate rate vs. both) touching `session_store/schema.py` and `session_store/writers.py`, not just `cli/harness.py` — cross-module depth beyond the five call-site loops themselves.
- Broad-ish dependent surface for a verdict-format change: 5 `cmd_*` call sites plus `record_harness_event()`/`harness_eval_pass_rate()` plus 3 loop YAMLs (`test-coverage-improvement.yaml`, `incremental-refactor.yaml`, `dead-code-cleanup.yaml`) consuming the `harness_exit` exit-code contract this issue changes.
- Several judgment calls remain open rather than pre-decided: the `pass_rate` field name (flagged naming-collision risk with `history_pass_rate`), the actual default-n value, and the rate-to-verdict banding thresholds — expect iteration during implementation even though the architectural approach (Option B) is settled.

## Status

**Open** | Created: 2026-09-08 | Priority: P2


## Session Log
- `/ll:wire-issue` - 2026-09-09T04:09:36 - `6a60b145-4b40-4e2a-b6c3-1f8fc4e6cbf8.jsonl`
- `/ll:decide-issue` - 2026-09-09T03:58:57 - `9dcdf7fc-6452-4110-90f8-74e389f6f78f.jsonl`
- `/ll:confidence-check` - 2026-09-09T03:48:44 - `5fcac4b3-76bf-4d53-b918-3bca0bf5f931.jsonl`
- `/ll:decide-issue` - 2026-09-09T03:42:56 - `b83f9a4d-c528-406f-9176-2cc312651f52.jsonl`
- `/ll:confidence-check` - 2026-09-09T03:40:31 - `dc741478-49cb-43bb-b19d-71e11a3fc887.jsonl`
- `/ll:wire-issue` - 2026-09-09T03:19:28 - `5eb4008f-a2a4-4aff-8262-28202dc28907.jsonl`
- `/ll:decide-issue` - 2026-09-09T03:12:12 - `98789ba8-7f76-42c3-b7d8-1f86848792ca.jsonl`
- `/ll:refine-issue` - 2026-09-09T03:03:38 - `a4badc70-f3c5-4caf-beea-29940135de9c.jsonl`
- `/ll:format-issue` - 2026-09-09T02:34:54 - `b326158e-3610-46e0-8daf-a6fb008cff1f.jsonl`
