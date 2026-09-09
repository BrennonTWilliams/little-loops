---
id: ENH-3415
title: Require n-run redundancy before an ll-harness verdict on a stochastic subject
  counts
type: ENH
priority: P2
status: done
discovered_date: '2026-09-08'
completed_at: '2026-09-09T05:50:46Z'
labels:
- harness
- evaluation
- statistics
relates_to:
- ENH-3421
decision_needed: false
confidence_score: 100
outcome_confidence: 82
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 18
---

## Summary

`ll-harness` evaluates a runner one-shot: a single pass against exit-code and semantic criteria produces a pass/fail verdict. But the subject under test is an LLM-driven runner whose behavior varies run to run, so a one-shot verdict certifies only "this runner passed once" — a lucky sample is indistinguishable from a real capability, and any promotion decision resting on it is unsound.

Require redundancy as structure, not as optional rigor: a verdict on a stochastic subject does not count until the criterion has been evaluated over n samples, and the harness reports pass-rate-over-n rather than a bare pass/fail. The threshold and the reporting change travel together — reporting a rate without requiring a minimum n just relabels the same weak evidence, and requiring n without surfacing the rate throws away the variance information the extra runs bought.

Scope: identify which runner types have stochastic subjects (a deterministic `cmd` runner should not pay for n samples it does not need), define the default n and how it is overridden per invocation, and decide what the verdict surface looks like when the rate lands between clear pass and clear fail.

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
per-invocation `--samples N` override are configurable, and a rate landing
between clear pass and clear fail is reported as its own explicit state
(`INCONCLUSIVE`, exit 3) rather than rounded to pass/fail. The sample loop
never stops early once a pass is observed: all n samples run. Each sample is
persisted as its own `attempt_kind='repetition'` row against the invocation's
`cell_key`, so the intra-invocation rate and the existing cross-invocation
`history_pass_rate` are the same statistic over different windows.

## Why redundancy has to be structural

The argument comes from evolutionary-search harnesses that select a candidate on a measured fitness signal. Two guards recur in those systems, and both are treated as *mandatory structure of the loop* rather than as extra rigor a careful operator adds:

- **N-sample redundancy.** High-variance evaluation environments produce flukes. Mandating multiple evaluations per unique match-up is what stops a single lucky win from promoting a candidate — the thing that separates principled selection from prompt-and-hope.
- **A frozen external reference.** A candidate is tested against both the incumbent and an unchanged baseline, so a lineage cannot drift into a self-referential local optimum where every generation only beats its immediate parent.

Neither is novel as statistics. What is worth copying is the posture: the loop is not considered runnable without them. The second guard is out of scope here and belongs in its own issue; this issue supplies the first. **No such issue exists yet** (checked 2026-09-09: nothing in `.issues/` describes a frozen external reference / baseline guard for `ll-harness`). File a stub for it when this issue is implemented and add it under `related:` so the deferral is tracked rather than lost.

## Dependencies and tensions to resolve explicitly

This sits directly on top of the harness run model that defines how an attempt is recorded against a named cell — as a repetition, an infrastructure retry, or a continuation, with only repetitions incrementing n. That model deliberately leaves the threshold open. This issue supplies the missing half: how large n must be before the harness will certify anything.

It also resolves a standing tension with the capability-preflight work, whose stop-on-first-confirmation is a budget policy pulling in the opposite direction. The two need an explicit boundary — **preflight capability probes may stop early; verdicts that gate promotion may not** — because leaving it implicit means whichever code path runs last silently wins.

The existing score-reproducible-not-byte-reproducible stance on judging stochastic agent runs is the auditing posture this makes mechanical: that stance says what a verdict on a stochastic subject may claim, and this issue supplies the mechanism that makes the claim true.

## Scope Boundaries

- **In scope**: classifying `RunnerType` members as stochastic vs. deterministic (table fixed in "Pre-Implementation Review Decisions" below), a default n plus a per-invocation `--samples N` override, the pass-rate-over-n verdict surface, defined behavior for a rate landing between clear pass/fail, per-sample timeout/error handling, and the no-early-exit rule for the sample loop.
- **Out of scope**: the frozen-external-reference / baseline guard described in "Why redundancy has to be structural" — that guard is explicitly called out as belonging to its own issue. Also out of scope: redefining the underlying attempt-recording model (repetition vs. infra-retry vs. continuation) referenced in "Dependencies and tensions to resolve explicitly" — this issue consumes that model's `n`, it does not change how attempts are classified.
- **Out of scope — judge-side stochasticity**: `--semantic` grades output with an LLM judge (`evaluate_llm_structured`) regardless of runner, so `cmd --semantic` at n=1 still certifies one judge sample. Classification here is by *subject* (`RunnerType`) only. Re-judging the same output n times to measure judge variance is a separate concern; an operator who wants it today can pass `--samples N` explicitly on a `cmd` runner, which re-runs the command as well.
- **Out of scope — DSL per-task resampling**: `cmd_dsl`'s rate is already computed *across tasks* with its own parent/child `harness_events` rows and a `--retry-of` single-file constraint. Resampling each task n times multiplies cost and complicates that row structure. In this issue `cmd_dsl` refuses `--samples` > 1 with a message naming the flag (mirroring its `--retry-of` directory refusal at `cli/harness.py:1180`); DSL resampling can be its own follow-up.
- **Out of scope — a new exit code**: the inconclusive band reuses exit 3 (see decision below); no change to `evaluate_exit_code()`, `abstain_on_exit_3`, or the ENH-3222 structural lint.

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

#### Caveat found in pre-implementation review (2026-09-08)

Option B as decided has a hole the rationale did not cover: `_evaluate_and_report()` **prints** on every call — the text status block or a full `--output json` payload (`cli/harness.py:875-910`), plus the ENH-3223 history line and the ENH-2998 prepatch lookup. Looping it n times at a call site emits n JSON objects on stdout and n identical history lines. `cmd_dsl` tolerates this only because per-task output is intended there. Option B therefore requires splitting grading from reporting:

- Extract the grading half of `_evaluate_and_report()` (lines `:798-845` and the outcome/exit-code derivation `:912-926`) into `_grade(runner_label, result, args, *, expected_grade=None) -> tuple[int, HarnessEvalOutcome]` with no stdout or DB writes. It is **not** pure: it still makes the `evaluate_llm_structured()` judge call when `--semantic` is set (one judge call per sample). Do not hoist that call out.
- `_evaluate_and_report()` becomes `_grade()` + the existing single-result report, preserving its signature and behavior for n=1 and for `cmd_dsl`.
- The n-sample path calls `_grade()` per sample and prints **one** aggregate report (new `_report_samples()`), performing the prepatch and history DB reads once.

This keeps Option B's selection intact (loop at the call sites, single-result contract preserved) while making the output surface correct.

## Pre-Implementation Review Decisions

_Added by pre-implementation review on 2026-09-08. These close the open judgment calls listed in the Confidence Check Notes so the implementer does not have to re-derive them._

### D1. Persistence: one `repetition` row per sample, no parent row

Each sample is written through the existing `_record_harness_event()` (`cli/harness.py:196`) as its own `attempt_kind='repetition'` row against the invocation's `cell_key`. This is exactly what ENH-3407/3408 built: `record_attempt()` allocates the next repetition index per cell, and `history_pass_rate_runs`/`harness_eval_pass_rate()` already count authoritative repetitions. Consequences:

- n samples in one invocation are indistinguishable in the DB from n separate invocations — the intra-invocation rate and the cross-invocation `history_pass_rate` are the same statistic over different windows.
- `harness_eval_pass_rate()`, `session_store/schema.py`, and `session_store/writers.py` need **no change**. The Wiring Phase item asking whether to store aggregate-only or both is resolved: per-sample rows only.
- **No DSL-style parent aggregate row** for `skill`/`prompt`/`mcp`/`cmd`. `cmd_dsl` gets away with a parent row because parent and children use different `runner` values (`dsl` vs `dsl-task`); a `skill` parent row would share `runner="skill"` with its children and double-count in the target-scoped rate.

### D2. `--retry-of` implies n = 1; refused only with an explicit `--samples` > 1

`--retry-of` supersedes one attempt and reuses its repetition index; a sample loop allocates n fresh indices. The two cannot compose. But a retry replaces exactly one attempt, so **when `--retry-of` is given and `--samples` is not, the effective sample count is 1** — the stochastic default of 3 does not apply. Otherwise every `ll-harness skill X --retry-of ID` (the common case, no `--samples`) would be refused and the operator would have to type `--samples 1` every time. Refuse before running, with exit 1 and a message naming both flags, **only when `retry_of is not None` and `args.samples` is explicitly > 1**, in the same place `_retry_gate()` is consulted today. `--samples 1 --retry-of ID` remains valid. This is what lets D3 compose: a timed-out sample from an n=3 run is retried individually as a one-sample invocation that supersedes that one row. (Revised 2026-09-09 pre-implementation review; the earlier "refused when *effective* n > 1" wording would have refused the default case.)

### D3. Per-sample timeout/error handling follows `cmd_dsl`'s tally

Per sample, `_grade()`'s exit code is tallied exactly as `cmd_dsl` tallies per task (`cli/harness.py:1293-1314`): `2` → `errored`, `3` → `abstained`, `0` → `passed`, `1` → `failed`. The loop **continues** after an errored sample (an infra failure on sample 2 of 5 should not discard samples 3–5). The graded denominator is `passed + failed`. Every sample, including errored ones, is still recorded via D1 so `--retry-of` can later supersede a timed-out sample individually (D2). Verdict precedence over the tally (mirrors BUG-3196's ordering):

1. `graded == 0 and errored > 0` → `ERROR`, exit 2
2. `graded == 0` (all abstained) → `ABSTAIN`, exit 3
3. otherwise band on the tally per D4

### D4. Banding is on counts, not on the Wilson CI; PASS requires every requested sample

If "between clear pass and clear fail" were defined as `paired_direction()`'s CI-straddles-0.5 rule, small n could never PASS: `wilson_ci(3,3)` has lower bound 0.438, `wilson_ci(4,4)` 0.510, `wilson_ci(5,5)` 0.566. Rather than force n ≥ 5, band on the tally:

- `PASS` iff `passed == requested` (every requested sample graded and passed — no failure, no abstention, no error), exit 0
- `FAIL` iff `passed == 0 and graded > 0` (every graded sample failed; errored/abstained samples alongside do not soften a unanimous failure), exit 1
- `INCONCLUSIVE` otherwise (mixed pass/fail, **or** passes with any abstained or errored sample), exit 3

Why PASS is on `requested`, not `graded` (revised 2026-09-09 pre-implementation review): the earlier `PASS iff failed == 0` rule let 1 pass + 2 timeouts certify PASS on a single graded sample — exactly the "lucky sample" the Summary calls unsound. It also contradicted both precedents this issue cites: the single-run precedence is fail > abstain > pass (`cli/harness.py:840-845`), and `cmd_dsl` returns exit 3 on any abstained task and exit 2 on any errored task even when every graded task passed (`cli/harness.py:1398-1405`). A shortfall is recoverable: the tally names the errored count, and each errored sample has its own row for `--retry-of`, or the operator re-runs.

The Wilson 95% CI is still computed with `wilson_ci(passed, graded)` and **printed as information** in the same `k/n  [lo, hi] (95% CI)` shape `cmd_dsl` uses (`cli/harness.py:1375`). Operating characteristic to state in the docs: a runner with per-run pass probability *p* slips through a PASS at *pⁿ* (0.7³ ≈ 0.34, 0.7⁵ ≈ 0.17); an operator who needs tighter certification raises `--samples`.

### D5. Exit 3 is reused for `INCONCLUSIVE`; no new exit code

`cli/harness.py:919` already documents exit 3 as "inconclusive"; the `harness_exit` fragment routes it to `on_cannot_judge`; `EvaluateConfig.abstain_on_exit_3` exists. Reusing it means **no change** to `evaluate_exit_code()`'s three call sites, `_is_abstention_capable()`/`_validate_abstention_route()`, or the five doc sites' exit-code tables beyond adding "or inconclusive rate" to the exit-3 description. `ABSTAIN` and `INCONCLUSIVE` are distinguished in the `result` string and the `samples` payload block, not by exit code.

### D6. Classification table

| `RunnerType` | Stochastic | Default n | Notes |
|---|---|---|---|
| `SKILL` | yes | 3 | `_run_skill()` drives the host LLM CLI |
| `PROMPT` | yes | 3 | `_run_prompt()` drives the host LLM CLI |
| `CMD` | no | 1 | `_run_cmd()` is `subprocess.Popen` |
| `MCP` | no | 1 | `call_mcp_tool()` is an arbitrary tool call, not an LLM |
| `DSL` | yes | 1 | already loops across tasks; `--samples` > 1 refused in this issue (see Scope Boundaries) |
| `LOOP` | n/a | — | never dispatched by `run_action()`; excluded from the table with a completeness test mirroring `test_loop_not_in_dispatch_table` |

`is_stochastic_runner(runner: RunnerType) -> bool` is a module-level dict lookup keyed by every member (the `_AXIS_NEEDS_SYMBOL` shape), colocated in `runner_spec.py` next to `RunnerType`. `DEFAULT_STOCHASTIC_SAMPLES = 3` lives beside it.

### D7. Override is per invocation: `--samples N`

There is no criterion list to key a per-criterion override on (refine confirmed: one `--exit-code` slot, one `--semantic` slot), and the runner invocation is the expensive part shared by both criteria. Add `--samples N` (`dest="samples"`, `type=_positive_int`, `default=None`) to `_add_evaluator_flags()`. Effective n = `args.samples` if given, else 1 if `args.retry_of is not None` (D2), else `DEFAULT_STOCHASTIC_SAMPLES` if `is_stochastic_runner(runner)`, else 1. An explicit `--samples` overrides in **both** directions — raising n on a `cmd` runner is useful for flaky shell tests — so the flag is never rejected on a deterministic runner. `--samples 0` or negative is an argparse error: plain `type=int` accepts `0`, so reuse the existing `_positive_int` argparse `type=` callable at `scripts/little_loops/cli/history.py:29` (import it, or lift it to a shared spot) rather than post-parse validation. No config-schema key in this issue.

Wall time and timeout scale with n: `--timeout` is per runner invocation, so a default `skill`/`prompt` run can take up to 3 × `--timeout`. State this in the docs next to the `--samples` row.

### D8. Names

- `HarnessEvalOutcome` gains `sample_pass_rate: float | None = None` (not `pass_rate`, per the `history_pass_rate`/`ab_writer.harness_pass_rate` collision noted under Documentation) and `samples: SampleTally | None = None`.
- New `@dataclass SampleTally` in `cli/harness.py`: `requested: int`, `graded: int`, `passed: int`, `failed: int`, `abstained: int`, `errored: int`, `ci_lo: float | None`, `ci_hi: float | None`.
- `--output json` gains a `samples` object with those fields plus `sample_pass_rate` at top level, **only when effective n > 1**; the n=1 payload is byte-identical to today's.
- **n > 1 JSON payload shape** (pinned 2026-09-09; the single-result keys `exit_code`/`stdout`/`stderr` have no honest aggregate value): top level carries `runner`, `result`, `sample_pass_rate`, `samples` (the `SampleTally` fields), plus `prepatch_evidence` and the `history_*` keys exactly as today. It does **not** carry top-level `exit_code`/`exit_code_check`/`semantic`/`stdout`/`stderr`. Instead `samples` gains a `results` list, one entry per sample in run order: `{"index": i, "exit_code": ..., "exit_code_check": ..., "semantic": ..., "result": "PASS"|"FAIL"|"ABSTAIN"|"ERROR", "error": str|None}`, with `stdout`/`stderr` added per entry only under `--verbose` or when that sample did not pass (mirroring `show_output`).
- Text output for n > 1 prints one status block whose `Result` is `PASS`/`FAIL`/`INCONCLUSIVE`/`ABSTAIN`/`ERROR` and adds a `Samples: k/n graded  [lo, hi] (95% CI)` line (append `, e errored` / `, a abstained` when non-zero so a shortfall is visible); per-sample stdout is shown only under `--verbose` (or for failing samples, matching today's `show_output` rule).
- **History and prepatch lookups run once, before the first sample.** `_read_target_history()` today runs before the run's own `_record_harness_event()` so the reported figures exclude the current run (`cli/harness.py:707-709`). The Call Path places `_report_samples()` after the loop; if the read happened there, the n fresh rows would be included, and because `_HISTORY_MIN_SCORED = 3` equals the default n, a first-ever n=3 invocation would print a history line derived entirely from itself. Read both before the loop and pass them into `_report_samples()`.

### D9. No early exit; the preflight boundary is prose, not code

Refine confirmed there is no preflight/stop-on-first-confirmation code path in `ll-harness` to refuse. The enforceable form of the boundary is: the sample loop runs all n samples and never short-circuits on a pass, tested directly. The preflight-vs-promotion rationale moves to `docs/guides/EVALUATION_GUIDE.md` prose alongside the first definition of "stochastic".

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
- ~~Tests that will break on the literal PASS/FAIL/ABSTAIN report text~~ — **superseded** (2026-09-09 review): the `PASS`/`FAIL`/`ABSTAIN` labels are unchanged, `return_value=` mocks serve n calls unchanged, and the JSON assertions (`test_cmd_json_output`, `TestMainHarness.test_main_harness_json_output`) are on the `cmd` runner where n stays 1. `captured_prompt[0]` (`:222`, `:695`) still works with three appends. Expect essentially no existing-test breakage from the default n=3 on `skill`/`prompt`; the regression net that matters is `TestCmdDsl` for the `_grade()` extraction.
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

- ~~Resolve how a stochastic subject's n-sample outcome persists~~ **Resolved by D1**: one `repetition` row per sample via the existing `_record_harness_event()`; no schema, writer, or `harness_eval_pass_rate()` change.
- `loops/lib/common.yaml`'s `harness_exit` fragment (`:23-29`) and its three consumer loops: **prose-only update** — the 0/1/3 contract is unchanged by D5; add "or inconclusive sample rate" to the exit-3 description. Verify `test-coverage-improvement.yaml`/`incremental-refactor.yaml`/`dead-code-cleanup.yaml` still validate (`ll-loop validate`).
- Update `docs/reference/CLI.md` (`### ll-harness` section: `--samples` row in the shared-flags table, `samples`/`sample_pass_rate` rows in the `--output json` payload table, exit-3 description), `docs/reference/API.md` (`:8992` — one sentence distinguishing intra-invocation `sample_pass_rate` from cross-invocation `history_pass_rate`; `:6144-6146`), and `docs/guides/EVALUATION_GUIDE.md` (four-runner prose, `passed`-scalar description whose `harness.py:419-433` anchor is stale, Result/Exit/Semantic table; first definition of "stochastic"; the D4 operating-characteristic note; the D9 preflight-vs-promotion prose).
- ~~Decide the `pass_rate` field name~~ **Resolved by D8**: `sample_pass_rate` + `samples: SampleTally`.
- Tests: `return_value=` mocks already serve n calls unchanged, so most of the at-risk tests below keep passing. Only tests that assert a call count or index a captured list (`TestCmdPrompt.test_prompt_sends_request` indexes `captured_prompt[0]`) need adjusting; new n-sample tests use `side_effect=[...]` lists or the `iter()`+lambda pattern from `test_cmd_dsl_partial_abstain_flips_pass_to_inconclusive`.
- ~~Thread `EvaluateConfig.abstain_on_exit_3`/`evaluate_exit_code()` for a new exit code~~ **Not needed by D5**: exit 3 is reused; `evaluate_exit_code()`, its three call sites, and the ENH-3222 structural lint are untouched.
- Update `cli/logs.py`'s `_fixture_to_harness_argv()`/`_cmd_eval_export()`/`_build_eval_fixture()` (~`:1972-2018`) to carry `--samples N` when present, so log-derived fixture round-trips do not silently drop it; verify against `scripts/tests/test_ll_logs.py::TestEvalExportHelpers::test_fixture_to_harness_argv_round_trips_through_parser`.
- Update `docs/reference/EVENT-SCHEMA.md` (~`:1795`, "CLI exit-code conventions") and `docs/generalized-fsm-loop.md:641-646` alongside the other three doc files — prose only, since the exit-code contract is unchanged; note that one invocation may now write n `harness_events` rows.
- `_grade()` extraction from `_evaluate_and_report()` (see Decision Rationale caveat) must leave `cmd_dsl`'s per-task call at `cli/harness.py:1289` byte-for-byte equivalent in behavior; `TestCmdDsl` (~33 tests) is the regression net.

## Program Design

_Rewritten 2026-09-08 to reflect the decided Option B plus review decisions D1–D9; the earlier draft (loop inside `_evaluate_and_report()`, a `cmd_run` entry point) is superseded._

### Deviations

_Added during implementation — 2026-09-09:_

- **A shared `_run_sample_loop()` helper, not one inline loop per call site.** The Call Path
  section describes the n-sample loop as living directly inside each of `cmd_skill`/`cmd_cmd`/
  `cmd_mcp`/`cmd_prompt`. Implementation factors the loop mechanics (tally, per-sample grading,
  building `samples.results` entries, banding, calling `_report_samples()`) into one shared
  `_run_sample_loop(runner_label, args, n, invoke, record)` used by all four handlers, each
  passing its own `invoke`/`record` closures for the runner-specific invocation and
  `_record_harness_event()` kwargs. This does not change Option B's core selection
  (`_evaluate_and_report()`'s single-result contract stays intact and untouched by any of
  this); it only avoids duplicating ~30 lines of identical loop-control-flow four times. Also
  added `_retry_samples_refusal()` as a small shared helper for the D2 refusal check, called
  by all four handlers *before* `_retry_gate()` (reordered from the Call Path pseudocode's
  implied ordering) so the refusal fires without needing a real prior `harness_events` row to
  exist first.
- **`_report_samples()` takes an explicit `label: str` keyword-only parameter.** The Call Path
  pseudocode elides the exact arguments passed to `_report_samples()` after computing
  `label, exit_code = _band_samples(tally)`; implementation passes `label` through explicitly
  rather than having `_report_samples()` recompute it from `tally`.

### Types

- `RunnerType` (`scripts/little_loops/runner_spec.py:59-67`) — existing enum; unchanged. Classification lives beside it, not on it.
- `_STOCHASTIC_RUNNERS: dict[RunnerType, bool]` (new, `runner_spec.py`) — keyed by every member except `LOOP` per D6; `DEFAULT_STOCHASTIC_SAMPLES = 3` alongside.
- `SampleTally` (new `@dataclass`, `cli/harness.py`) — `requested`, `graded`, `passed`, `failed`, `abstained`, `errored: int`; `ci_lo`, `ci_hi: float | None` (D8).
- `HarnessEvalOutcome` (`cli/harness.py:670-677`) — gains `sample_pass_rate: float | None = None` and `samples: SampleTally | None = None`; existing `passed`/`verdict`/`eval_result`/`abstained` unchanged.

### Signatures

- `is_stochastic_runner(runner: RunnerType) -> bool` — new, `runner_spec.py`; `KeyError` on `LOOP` is acceptable (never dispatched).
- `_effective_samples(args: argparse.Namespace, runner: RunnerType) -> int` — new, `cli/harness.py`; implements D7.
- `_grade(runner_label: str, result: RunnerResult, args, *, expected_grade: ExpectedGrade | None = None) -> tuple[int, HarnessEvalOutcome]` — new, extracted from `_evaluate_and_report()` lines `:798-845,912-926`; no stdout/DB writes (still performs the `--semantic` judge call).
- `_evaluate_and_report(...)` (`cli/harness.py:789`) — **signature unchanged**; body becomes `_grade()` + the existing single-result report. All existing callers, including `cmd_dsl`, are behaviorally unaffected.
- `_band_samples(tally: SampleTally) -> tuple[str, int]` — new; implements D3 precedence + D4 banding, returns `(result_label, exit_code)`.
- `_report_samples(runner_label: str, tally: SampleTally, sample_results: list[RunnerResult], args, *, prepatch_evidence, target_history) -> None` — new; prints one aggregate text block or JSON payload (D8).

### Call Path

For each of `cmd_skill` (`:951`), `cmd_cmd` (`:1000`), `cmd_mcp` (`:1042`), `cmd_prompt` (`:1120`):

```
n = _effective_samples(args, spec.runner)                    # D7: --retry-of without --samples => 1
if retry_of is not None and args.samples is not None and args.samples > 1:
    refuse, exit 1                                           # D2 (explicit --samples only)
if n == 1: existing path, byte-identical output              # unchanged
else:
    prepatch_evidence = _read_prepatch_evidence(...)         # once, BEFORE the loop
    target_history = _read_target_history(args.target)       # once, BEFORE the loop (D8)
    for i in range(n):
        result = run_action(spec) | _run_prompt_action(...)
        rc, outcome = _grade(runner_label, result, args)
        tally.record(rc)                                     # D3
        _record_harness_event(..., cell_key=cell_key)        # D1: one repetition row per sample
    label, exit_code = _band_samples(tally)                  # D4/D5
    _report_samples(..., prepatch_evidence=..., target_history=...)   # once
    return exit_code
```

`cmd_dsl` (`:1156`) refuses `--samples` > 1 and is otherwise untouched (Scope Boundaries).

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

1. `is_stochastic_runner()` classifies every dispatched `RunnerType` per the D6 table, with a completeness test mirroring `TestRunnerTypeCompleteness`; `LOOP` is excluded and tested as such.
2. Without `--samples`, `skill` and `prompt` run `DEFAULT_STOCHASTIC_SAMPLES` (3) times; `cmd` and `mcp` run once with output byte-identical to today (existing `TestCmdCmd`/`TestCmdMcp` tests pass unmodified).
3. `--samples N` overrides the default in both directions on any of the four runners; `--samples 0` or negative is an argparse error (`_positive_int` type); `cmd_dsl` refuses `--samples` > 1 with exit 1 and a message naming the flag.
4. For effective n > 1, the verdict is `PASS`/exit 0 iff `passed == requested`, `FAIL`/exit 1 iff `passed == 0 and graded > 0`, `ABSTAIN`/exit 3 when all samples abstained, `ERROR`/exit 2 when no sample graded and at least one errored, and `INCONCLUSIVE`/exit 3 otherwise — including 2 pass + 1 abstain and 2 pass + 1 timeout, each with its own test (D3/D4/D5). No new exit code is introduced.
5. For n > 1, exactly **one** report is printed: a single JSON object under `--output json` (top-level `samples`/`sample_pass_rate`, per-sample `samples.results`, no top-level `exit_code`/`stdout`/`stderr`) or a single text status block with a `Samples: k/n graded  [lo, hi] (95% CI)` line. The history and prepatch lookups run once, **before the first sample**: a test seeds no prior rows, runs n=3, and asserts no `history_pass_rate` key/line is emitted (the run's own rows must not feed its history figure). A test asserts `stdout` parses as exactly one JSON object for n=3.
6. Each sample is persisted as its own `attempt_kind='repetition'` row against the invocation's `cell_key`; a test asserts n rows with distinct `repetition` indices after one n=3 invocation, and that a *subsequent* invocation's `history_pass_rate_runs` counts them.
7. `--retry-of ID` with an explicit `--samples` > 1 is refused before any runner invocation, exit 1, message naming both flags. `--retry-of ID` without `--samples` on a `skill`/`prompt` runner runs exactly one sample (test asserts one runner invocation and one `infra_retry` row).
8. An errored (exit 2) sample does not stop the loop; the remaining samples still run and are tallied, with a test using a `side_effect` list that times out sample 2 of 3.
9. The sample loop never exits early on a pass: a test with `side_effect=[pass, pass, fail]` asserts three runner invocations and an `INCONCLUSIVE` verdict.
10. `cli/logs.py` fixture round-trip preserves `--samples N` (`test_fixture_to_harness_argv_round_trips_through_parser` extended).
11. `docs/reference/CLI.md`, `docs/reference/API.md`, `docs/guides/EVALUATION_GUIDE.md`, `docs/reference/EVENT-SCHEMA.md`, `docs/generalized-fsm-loop.md`, and `loops/lib/common.yaml`'s `harness_exit` prose are updated per the Wiring Phase; EVALUATION_GUIDE defines "stochastic", states the *pⁿ* operating characteristic, and carries the preflight-vs-promotion boundary (D9).
12. `python -m pytest scripts/tests/` exits 0; `ll-loop validate` passes for the three `harness_exit` consumer loops.

## Impact

- **Priority**: P2 - a stochastic verdict today certifies a lucky sample rather than a real capability; not yet gating a live promotion decision, but any harness-driven promotion built on the current one-shot verdict is unsound.
- **Effort**: Medium - extracts `_grade()` from `_evaluate_and_report`, adds a sample loop at four `cmd_*` call sites in `cli/harness.py`, a classification table in `runner_spec.py`, one new flag, and doc updates; no schema, writer, or FSM-evaluator change (D1, D5).
- **Risk**: Low-Medium - exit codes and the n=1 output surface are unchanged; the new code path is reached only for `skill`/`prompt` by default or via an explicit `--samples`. The main regression risk is the `_grade()` extraction altering `cmd_dsl`'s per-task behavior, covered by the ~33 existing `TestCmdDsl` tests.
- **Breaking Change**: No - `HarnessEvalOutcome` gains defaulted fields and has no consumers outside `cli/harness.py`; the 0/1/2/3 exit contract is preserved. **Behavior change to call out**: default `ll-harness skill` and `ll-harness prompt` invocations now run the subject 3x, so wall time (up to 3 × `--timeout`), host-CLI cost, and `--semantic` judge calls triple, and one invocation writes three `harness_events` rows. `--output json` for those two runners changes shape by default (D8: no top-level `exit_code`/`stdout`/`stderr`; per-sample `samples.results` instead). No shipped loop, skill, command, or hook invokes those two runners today, so the change lands on hand-run and future callers only; `cli/logs.py` fixture replays of `skill`/`prompt` invocations also pay 3x unless the fixture carries `--samples 1`.

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-09-08_

**Readiness Score**: 95/100 → PROCEED
**Outcome Confidence**: 48/100 → LOW

### Outcome Risk Factors
- ~~Persistence strategy for the n-sample outcome is unresolved~~ — closed by D1 (per-sample `repetition` rows through the existing writer; no schema/writer change).
- ~~Broad-ish dependent surface for a verdict-format change~~ — narrowed by D5 (exit codes unchanged, so the `harness_exit` consumers and FSM evaluator sites need prose-only updates).
- ~~Several judgment calls remain open~~ — closed by D4 (count banding), D6 (default n=3), D8 (`sample_pass_rate`/`SampleTally`).
- Remaining: the `_grade()` extraction (added in review) touches the shared grading path used by `cmd_dsl`; regression risk is contained by `TestCmdDsl` but the extraction must be done first and verified green before the sample loop is added.

## Resolution

Implemented per the decided Option B design (see Program Design → Deviations for two small
implementation-level refinements — a shared `_run_sample_loop()` helper instead of four
inline copies, and a reordered D2 refusal check).

- `runner_spec.py`: `_STOCHASTIC_RUNNERS` classification dict, `DEFAULT_STOCHASTIC_SAMPLES = 3`,
  `is_stochastic_runner()` (D6), with a completeness test mirroring `TestRunnerTypeCompleteness`.
- `cli/harness.py`: extracted `_grade()` (grading only, no stdout/DB writes) from
  `_evaluate_and_report()`, which now delegates to it and is otherwise byte-identical for n=1
  and `cmd_dsl`. New `SampleTally`, `_effective_samples()` (D7), `_band_samples()` (D3/D4/D5),
  `_report_samples()` (D8), `_retry_samples_refusal()` (D2), and `_run_sample_loop()` shared by
  `cmd_skill`/`cmd_cmd`/`cmd_mcp`/`cmd_prompt`. `--samples N` added to the shared evaluator
  flags (`_positive_int` reused from `cli/history.py`). `cmd_dsl` refuses `--samples` > 1.
- `cli/logs.py`: `_build_eval_fixture()`/`_fixture_to_harness_argv()` carry a `samples` field
  through the eval-export fixture round-trip (AC10).
- Docs updated per the Wiring Phase: `docs/reference/CLI.md` (`--samples` flag, n>1 JSON/text
  report shape, exit-3 description), `docs/reference/API.md` (intra- vs cross-invocation rate
  distinction, exit-3 reuse), `docs/guides/EVALUATION_GUIDE.md` (new "N-sample redundancy for
  stochastic subjects" section defining "stochastic", the *pⁿ* operating characteristic, and
  the preflight-vs-promotion boundary; stale `harness.py:419-433` anchor fixed), `docs/reference/
  EVENT-SCHEMA.md` and `docs/generalized-fsm-loop.md` (exit-3 reuse), and `loops/lib/common.yaml`'s
  `harness_exit` fragment description (prose only — the 0/1/3 contract is unchanged).
- Tests: new unit tests for `is_stochastic_runner`/`_effective_samples`/`_band_samples`/
  `SampleTally.record`, and integration tests for the default n=3, `--samples` override in both
  directions, all five verdict bands (including the "2 pass + 1 abstain/error → INCONCLUSIVE,
  not PASS" case), no-early-exit-on-pass, an errored sample not stopping the loop, exactly-one-
  JSON-object output, the pre-loop single history read, per-sample `repetition` rows (and that a
  later invocation's `history_pass_rate` counts them), the `--retry-of`+`--samples`>1 refusal,
  `--retry-of` alone pinning n to 1 on a stochastic runner, and the `dsl` refusal. `_make_namespace()`
  in `test_cli_harness.py` now defaults `samples=1` so pre-existing tests keep their pre-ENH-3415
  single-invocation behavior unless a test opts into the sample loop explicitly.
- Verification: `python -m pytest scripts/tests/ -q -m "not integration and not conformance"`
  passes (22802 passed; the 6 residual failures — `test_host_runner.py`,
  `test_issue_parser.py` ×2, `test_verify_evidence.py`, `test_feat3418_workspace_quality.py` ×2
  — are pre-existing and unrelated: none touch a file this issue changed, confirmed via
  `git diff --stat`). `ruff check`/`ruff format --check`/`mypy` clean on every changed file.
  `ll-loop validate` passes for the three `harness_exit` consumer loops (pre-existing
  unrelated warnings only).
- Per the Summary's own instruction, filed ENH-3421 (P3) as the stub for the frozen-external-
  reference/baseline guard called out in "Why redundancy has to be structural"; wired both
  ways via `related:`.

## Status

**Open** | Created: 2026-09-08 | Priority: P2


## Session Log
- `/ll:manage-issue` - 2026-09-09T05:50:22 - `14a3300d-cd3a-4c89-a5cb-ae4cd98e17ec.jsonl`
- `/ll:confidence-check` - 2026-09-09T04:51:06 - `9f7ba440-a9e9-425e-a48b-4802e0b2ac21.jsonl`
- pre-implementation review (manual) - 2026-09-09 - revised D2 (`--retry-of` implies n=1), D4 (PASS requires `passed == requested`), D7 (`_positive_int`, timeout scaling), D8 (n>1 JSON shape; history/prepatch read before the loop), `_grade()` I/O wording, struck the stale test-breakage bullet, updated AC3–AC7 and Impact, noted the missing frozen-baseline follow-up issue
- `/ll:confidence-check` - 2026-09-09T04:41:40 - `4d4ff5a0-23ef-4021-a8a3-820b60906276.jsonl`
- `/ll:verify-issues` - 2026-09-09T04:38:13 - `8dab0813-a8db-483a-974b-e9db8e0998dc.jsonl`
- pre-implementation review (manual) - 2026-09-08 - added "Pre-Implementation Review Decisions" D1–D9, Option B print caveat, rewrote Program Design / Acceptance Criteria / Impact
- `/ll:confidence-check` - 2026-09-09T04:13:05 - `e1e686a9-1440-44fa-b3e0-814ed4ea3e38.jsonl`
- `/ll:wire-issue` - 2026-09-09T04:09:36 - `6a60b145-4b40-4e2a-b6c3-1f8fc4e6cbf8.jsonl`
- `/ll:decide-issue` - 2026-09-09T03:58:57 - `9dcdf7fc-6452-4110-90f8-74e389f6f78f.jsonl`
- `/ll:confidence-check` - 2026-09-09T03:48:44 - `5fcac4b3-76bf-4d53-b918-3bca0bf5f931.jsonl`
- `/ll:decide-issue` - 2026-09-09T03:42:56 - `b83f9a4d-c528-406f-9176-2cc312651f52.jsonl`
- `/ll:confidence-check` - 2026-09-09T03:40:31 - `dc741478-49cb-43bb-b19d-71e11a3fc887.jsonl`
- `/ll:wire-issue` - 2026-09-09T03:19:28 - `5eb4008f-a2a4-4aff-8262-28202dc28907.jsonl`
- `/ll:decide-issue` - 2026-09-09T03:12:12 - `98789ba8-7f76-42c3-b7d8-1f86848792ca.jsonl`
- `/ll:refine-issue` - 2026-09-09T03:03:38 - `a4badc70-f3c5-4caf-beea-29940135de9c.jsonl`
- `/ll:format-issue` - 2026-09-09T02:34:54 - `b326158e-3610-46e0-8daf-a6fb008cff1f.jsonl`
