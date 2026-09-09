---
id: ENH-3415
title: Require n-run redundancy before an ll-harness verdict on a stochastic subject counts
type: ENH
priority: P2
status: open
discovered_date: '2026-09-08'
labels:
- harness
- evaluation
- statistics
decision_needed: true
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

**Recommended**: Option B — `HarnessEvalOutcome` and `_evaluate_and_report()` have zero consumers outside `cli/harness.py` (see Integration Map → Dependent Files), so either option is low-blast-radius, but Option B leaves `_evaluate_and_report()`'s existing single-result contract intact and localizes the new looping logic to the five call sites, which already duplicate the runner-invocation-then-evaluate shape today.

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

### Dependent Files (Callers/Importers)
- `cli/harness.py:951` — `cmd_skill()` calls `_evaluate_and_report()` at `:972`
- `cli/harness.py:1000` — `cmd_cmd()` calls `_evaluate_and_report()` at `:1019`
- `cli/harness.py:1042` — `cmd_mcp()` calls `_evaluate_and_report()` at `:1077`
- `cli/harness.py:1120` — `cmd_prompt()` calls `_evaluate_and_report()` at `:1132`
- `cli/harness.py:1156` — `cmd_dsl()` calls `_evaluate_and_report()` at `:1289` (looped over distinct task files, not the same-subject resampling this issue introduces)
- `cli/harness.py:983-984,1027-1028,1085-1086,1140-1141,1321-1322` — the only readers of `HarnessEvalOutcome.passed/verdict/abstained`, each immediately after its `_evaluate_and_report()` call site, feeding `_record_harness_event()`
- `HarnessEvalOutcome` has zero consumers outside `cli/harness.py` itself (repo-wide grep for the class name) — the "Breaking Change" in Impact is narrowly scoped to this one file
- `queue_store.py` and `cli/queue.py` import `RunnerType` from `runner_spec.py` but have zero references to "harness" — not coupled to this issue's verdict-surface change

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

## Status

**Open** | Created: 2026-09-08 | Priority: P2


## Session Log
- `/ll:refine-issue` - 2026-09-09T03:03:38 - `a4badc70-f3c5-4caf-beea-29940135de9c.jsonl`
- `/ll:format-issue` - 2026-09-09T02:34:54 - `b326158e-3610-46e0-8daf-a6fb008cff1f.jsonl`
