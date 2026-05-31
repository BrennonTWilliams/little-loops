---
id: FEAT-1790
title: A/B Baseline Mode for `ll-loop run`
type: FEAT
priority: P2
captured_at: '2026-05-29T19:08:54Z'
discovered_date: '2026-05-29'
discovered_by: capture-issue
status: done
size: Very Large
parent: EPIC-1663
labels:
- feature
- loops
- harness
- evaluation
- ab-testing
- meta-loop
confidence_score: 100
outcome_confidence: 71
score_complexity: 10
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 18
---

# FEAT-1790: A/B Baseline Mode for `ll-loop run`

## Summary

Add an opt-in baseline-comparison mode to `ll-loop run` that executes the harness's `execute` action twice in parallel — once with the harness's evaluation gates active, once as an ungated bare-skill invocation — and logs the delta in pass-rate, tokens, and duration to `.loops/runs/<id>/ab.json`. Produces measurable evidence that the harness improves on the bare skill, rather than relying on LLM self-grades.

## Current Behavior

`ll-loop run` executes a harness's `execute` action with evaluation gates active (retrying on failed evals). There is no native way to measure whether the harness improves output quality over a bare skill invocation. Meta-loop authors rely on LLM self-grades for harness quality, which are ~33–55% accurate (SHOR Table 1; Sonnet 4.6 = 33.4%). The harness's value is asserted, not measured.

## Expected Behavior

When `--baseline` is passed, `ll-loop run` executes both arms in parallel:
1. **Harness arm** — normal gated execution with eval chain and retries
2. **Baseline arm** — single-shot skill invocation with no eval gates or retries

Both outputs are fed to `check_semantic` blind (anonymized as A/B, randomized per item). Results — pass-rate, tokens, duration for each arm — are written to `.loops/runs/<id>/ab.json` and summarized on the terminal with delta calculations.

## Motivation

EPIC-1663's MR-1 rule (CLAUDE.md § Loop Authoring) requires meta-loops to pair LLM judges with non-LLM external evidence because LLM self-grades on harness updates are ~33–55% accurate (SHOR Table 1; Sonnet 4.6 = 33.4%). The rule catches *missing* non-LLM evidence but doesn't *produce* the evidence — authors still have no native way to demonstrate that a harness beats the underlying skill.

`revfactory/harness` (reviewed 2026-05-29) addresses this by spawning two subagents per test prompt — `with_skill/` and `without_skill/` — into a per-iteration workspace, capturing `total_tokens`, `duration_ms`, and assertion grading for both. Their A/B (n=15) shows +60% quality with the harness; whether that holds for *our* harnesses is currently untestable. Without baseline comparison the harness's value is asserted, not measured.

This is also the empirical foundation for downstream issues in this batch (non-discriminating evaluator detection, blind comparator) — both depend on having paired with/without runs to analyze.

## Use Case

A user has built a `harness-refine-issue` loop and wonders whether the eval chain (`check_concrete` + `check_semantic` + `check_invariants`) actually improves output quality over just running `/ll:refine-issue` once. They run:

```bash
ll-loop run harness-refine-issue --baseline --items 10
```

The loop processes 10 issues. For each, it executes `/ll:refine-issue` twice: once inside the gated harness (retrying on failed evals), once as a one-shot bare invocation. Both outputs are passed to `check_semantic` blind (anonymized) for scoring. The output:

```
A/B Summary (n=10)
  Harness pass-rate:  9/10  (90%)
  Baseline pass-rate: 6/10  (60%)
  Delta:              +30%

  Median tokens:      harness=84k  baseline=42k  (+100%)
  Median duration:    harness=3m   baseline=1m   (+200%)
  Verdict:            harness wins on quality, costs ~2× tokens

Per-item: .loops/runs/<id>/ab.json
```

This converts MR-1's qualitative warning into a quantitative artifact authors can cite when defending or refining a harness.

## API/Interface

```bash
ll-loop run <loop> --baseline [--baseline-skill <skill>] [--items N]
```

- `--baseline` — enables A/B mode. Both arms run; verdicts go to a blind comparator.
- `--baseline-skill` (optional) — override what the baseline arm runs. Default: extract the slash command from `execute.action` and invoke it once with no retries.
- `--items N` (optional, multi-item only) — limit the sample size for the A/B run (full backlog can be expensive).

Output:
- `.loops/runs/<id>/ab.json` — per-item record:
  ```json
  {
    "items": [
      {
        "id": "BUG-1759",
        "harness": {"verdict": "yes", "tokens": 84852, "duration_ms": 23332},
        "baseline": {"verdict": "no",  "tokens": 41200, "duration_ms": 9870},
        "blind_compare": {"winner": "A", "rationale": "..."}
      }
    ],
    "summary": {"harness_pass_rate": 0.9, "baseline_pass_rate": 0.6, "delta": 0.3}
  }
  ```
- Summary printed at end of run (as shown in Use Case).

## Implementation Steps

### Phase 1: Wire `--baseline` flag

Add `--baseline`, `--baseline-skill`, and `--items` to the `run` subparser in `main_loop()` at `cli/loop/__init__.py:111-231`. Follow the existing boolean-flag pattern used for `--dry-run` / `--no-llm` / `--background` (lines 131-201). Consume the flags in `cmd_run()` at `cli/loop/run.py:88` — same pattern as `--max-iterations` (line 117) and `--context` (lines 147-151). Forward flags to background-spawned children following `run_background()` in `cli/loop/_helpers.py:1010-1055`.

### Phase 2: Parallel execute (harness arm + baseline arm)

When `--baseline` is active, modify `FSMExecutor._execute_state()` at `fsm/executor.py:772` to spawn two subprocess invocations in parallel after `discover` resolves an item:

- **Harness arm**: Normal gated execution — `_run_action()` (line 970) → `DefaultActionRunner.run()` (`fsm/runners.py:62`) → `run_claude_command()` (`subprocess_utils.py:221`) with streaming output and eval-chain retries.
- **Baseline arm**: Single-shot skill invocation — call `resolve_host().build_streaming()` (`host_runner.py:233`) with the bare slash command (extracted from `execute.action`), no eval gates, no retries. Run via `subprocess.Popen` with selector-based streaming (pattern at `subprocess_utils.py:277-386`).

Use the same concurrency pattern as `ll-parallel`'s `ParallelOrchestrator` (`parallel/orchestrator.py:44`) with `ThreadPoolExecutor`, or a simpler two-thread `concurrent.futures` spawn for paired execution. The two arms are independent — no shared state needed.

### Phase 3: Blind evaluation

Feed both outputs into a blind LLM judge. Build a new evaluator or reuse `evaluate_llm_structured()` at `fsm/evaluators.py:572`:

- Randomize order per item (stdlib `random.shuffle`) — anonymize outputs as "Output A" and "Output B" with no indication of which is the harness arm.
- Call `resolve_host().build_blocking_json()` (pattern at `evaluators.py:609`) with the judgment prompt.
- The judge returns structured output (`verdict`, `confidence`, `reason`) via the `DEFAULT_LLM_SCHEMA` at `evaluators.py:59`.
- De-anonymize after judgment to attribute scores to each arm.

### Phase 4: Capture timing and tokens

- **duration_ms**: Already available via `ActionResult.duration_ms` (`fsm/types.py:58`) and `run_claude_command()` timing (`subprocess_utils.py:122`).
- **total_tokens**: Wire the `on_usage` callback (currently unused by `DefaultActionRunner`) from `run_claude_command()` at `subprocess_utils.py:365`. The `result` stream-json event includes `usage.input_tokens` and `usage.output_tokens` (lines 362-369). Store immediately on receipt per the completion-notification constraint.
- **Evaluator tokens**: The blind comparator's own token usage via `build_blocking_json()` is not available from the current host-runner path — accept this as a known limitation or extend `HostRunner.build_blocking_json()` to return usage data.

### Phase 5: Aggregate and report

- Compute pass-rate delta, median token/duration, and per-item verdicts.
- Model aggregation after `calculate_summary()` in `issue_history/summary.py:21` (iterate items, accumulate counts into dataclass).
- Write `ab.json` to `${context.run_dir}/ab.json` — `run_dir` is injected at `cmd_run()` line 162.
- Define `ab.json` schema using the `_schema()` builder pattern from `generate_schemas.py:23-74`.
- Print terminal summary using `run_foreground()` completion block at `cli/loop/_helpers.py:1204-1225` as the output point.

### Phase 6: Tests

Add to `scripts/tests/test_ll_loop_execution.py` following existing test patterns:

- **Mock host runner**: Patch `resolve_host()` (pattern at `test_subprocess_mocks.py:28`) to return mock invocations for both arms.
- **Four combinations**: both-pass, harness-only-pass, baseline-only-pass, both-fail.
- **ab.json schema validation**: Assert the written JSON matches the schema.
- **Blind anonymization**: Verify judge prompt does not contain arm-identifying labels.
- Use `tmp_path` fixture for loop definitions (pattern at `test_ll_loop_state.py:79`) and `patch.object(sys, "argv", [...])` to test CLI entry (pattern at `test_ll_loop_errors.py:98`).

### Phase 7: Documentation

- Add "Validating Your Harness" section to `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` with `--baseline` usage example and output interpretation guidance.
- Cross-reference in `.claude/CLAUDE.md` § Loop Authoring (lines 88-131) — link to the new guide section.
- Mention in EPIC-1663 and ENH-1665 issue files as the empirical validation primitive.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

8. Flag forwarding in `run_background()` at `scripts/little_loops/cli/loop/_helpers.py:941-1074` — forward `--baseline`/`--baseline-skill`/`--items` to child process args following existing flag-forwarding pattern (lines 1010-1055); without this, background mode silently drops baseline flags.

9. A/B summary in `run_foreground()` at `scripts/little_loops/cli/loop/_helpers.py:1204-1225` — insert A/B summary output after the existing "Loop completed" line; read `ab.json` from run directory and print delta table.

10. `PersistentExecutor` event handling in `scripts/little_loops/fsm/persistence.py:606-641` — `_handle_event()` and `_save_state()` must handle new parallel-arm event types (`baseline_complete`, `ab_comparison`, `ab_summary`) to avoid state-save failures during baseline runs.

11. Public API exports in `scripts/little_loops/fsm/__init__.py:162-231` — add `ABResults`, `write_ab_json`, and any other public symbols from `ab_writer.py` to `__all__`.

12. CLI flag table in `docs/reference/CLI.md:381-444` — add `--baseline`, `--baseline-skill`, and `--items` rows to the `ll-loop run` flag table following existing boolean-flag row format.

13. Loop guide update in `docs/guides/LOOPS_GUIDE.md` — add `--baseline` usage section with example invocation and output interpretation following existing feature-subsection pattern.

14. Changelog entry in `CHANGELOG.md` — standard feature entry under dated version header referencing FEAT-1790.

## Acceptance Criteria

- [ ] `ll-loop run <loop> --baseline` runs both arms in parallel without serializing
- [ ] Blind anonymization verified (judge prompt does not reveal which arm is the harness)
- [ ] `ab.json` written with per-item records and summary block
- [ ] Terminal summary prints delta, token/duration ratios
- [ ] Tests cover all four pass/fail combinations
- [ ] Documentation updated with usage example

## Impact

- **Priority**: P2 — High value for harness authors validating their loops; unblocks downstream issues (non-discriminating evaluator detection, blind comparator) that depend on paired with/without data
- **Effort**: Medium — CLI flag wiring, parallel execution, blind evaluation, token/timing capture, aggregation, tests, and docs across 7 implementation phases
- **Risk**: Low — Additive feature behind an opt-in `--baseline` flag; no changes to existing `ll-loop run` behavior when flag is omitted
- **Breaking Change**: No

## Integration Map

### Files to Modify
- `scripts/little_loops/ll_loop.py` — argparse wiring and runner dispatch for `--baseline` / `--baseline-skill` / `--items` flags
- `scripts/little_loops/loop_runner.py` — parallel execution orchestration, blind evaluator, timing/token capture
- `scripts/little_loops/ab_writer.py` (new) — `ab.json` schema, writer, and summary aggregation
- `scripts/little_loops/cli/loop/_helpers.py` — flag forwarding in `run_background()`, A/B summary output in `run_foreground()`
- `scripts/little_loops/fsm/persistence.py` — `PersistentExecutor` event handling for parallel-arm event types
- `scripts/little_loops/fsm/__init__.py` — export new public symbols from `ab_writer`

### Dependent Files (Callers/Importers)
- `scripts/little_loops/host_runner.py` — baseline arm uses `HostInvocation` / `build_streaming()`
- `scripts/little_loops/session_log.py` — session log entries for baseline runs
- `scripts/little_loops/fsm/persistence.py` — `PersistentExecutor` wraps `FSMExecutor`, intercepts execution events; must handle parallel-arm event types emitted during baseline runs

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/loop/_helpers.py` — `run_background()` at line 941 must forward `--baseline`/`--baseline-skill`/`--items` to child process following existing flag-forwarding pattern (lines 1010-1055); `run_foreground()` completion block (lines 1204-1225) prints the terminal summary and needs the A/B delta output
- `scripts/little_loops/fsm/__init__.py` — re-exports `FSMExecutor`, `ActionResult`, `evaluate_llm_structured`; must export new public symbols from `ab_writer` (e.g., `ABResults`, `write_ab_json`)
- `scripts/little_loops/cli/loop/lifecycle.py` — `cmd_resume()` calls `run_foreground()` and may need to gate `--baseline` incompatibility with resume mode

### Similar Patterns
- `scripts/little_loops/loops/harness-single-shot.yaml:113-131` — `check_semantic` state with `llm_structured` evaluator and `source:` redirection (evaluates captured output from a different state)
- `scripts/little_loops/loops/harness-optimize.yaml:179-192` — `convergence` evaluator paired with non-LLM evidence (the MR-1 pattern this feature operationalizes)
- `scripts/little_loops/generate_schemas.py:23-74` — JSON schema generation using `_schema()` helper builder; follow this for `ab.json` schema definition
- `scripts/little_loops/issue_history/summary.py:21` — `calculate_summary()` aggregation pattern (iterate items, accumulate counts, build dataclass)
- `scripts/little_loops/issue_history/formatting.py` — multi-format output pattern (text/JSON/YAML/Markdown) for terminal summary
- `scripts/little_loops/cli/loop/__init__.py:131-201` — existing boolean flag wiring (`--dry-run`, `--no-llm`, `--background`) — model `--baseline` after these
- `scripts/little_loops/cli/parallel.py:41-152` — `ll-parallel` flag wiring with config dataclass; `ParallelOrchestrator` uses `ThreadPoolExecutor` for concurrent work

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Token capture gap**: `run_claude_command()` in `subprocess_utils.py:365` exposes `on_usage` and `on_model_detected` callbacks that parse `total_tokens` from stream-json `result` events, but `DefaultActionRunner.run()` in `fsm/runners.py:62` does NOT wire them — it only passes `on_process_start` and `on_process_end`. Both the harness arm and baseline arm will need to wire `on_usage` to capture per-arm token counts.
- **Blind evaluator limitation**: `evaluate_llm_structured()` in `fsm/evaluators.py:572` calls `resolve_host().build_blocking_json()` (line 609) which returns JSON output only — no streaming, no token count. The blind comparator's own token usage won't be available from this path.
- **No existing anonymization**: Confirmed — no blind/anonymization/shuffle pattern exists anywhere in the codebase. The `random` stdlib module is available; the blind comparator prompt must avoid revealing which output came from the harnessed arm.
- **duration_ms already available**: `ActionResult.duration_ms` (from `fsm/types.py:58`) and `ExecutionResult.duration_ms` (from `fsm/runners.py:122`) already track timing. The A/B feature needs per-arm duration, not just aggregate.
- **run_dir injection**: Context key `run_dir` is injected at `cmd_run()` in `cli/loop/run.py:162` as `str(loops_dir / "runs" / instance_id) + "/"` — the `ab.json` path `.loops/runs/<id>/ab.json` aligns with this convention.

### Tests
- `scripts/tests/test_ll_loop.py` — `test_baseline_happy_path`, `test_baseline_blind`, `test_baseline_ab_json_schema`
- Mock host runner for both-pass, harness-only-pass, baseline-only-pass, both-fail cases

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_ab_writer.py` (NEW) — schema validation tests (JSON Schema draft-07), writer round-trip tests, summary aggregation tests (pass-rates, medians, deltas), edge cases (empty results, single item, all-pass, all-fail)
- `scripts/tests/test_fsm_evaluators.py` — blind comparator tests in new `TestBlindComparator` class: anonymization verification (judge prompt must not contain "harness"/"baseline"/"gated"/"ungated"), de-anonymization correctness (scores map back to correct arm), verdict combination tests (both-pass, harness-only-pass, baseline-only-pass, both-fail)
- `scripts/tests/test_cli_loop_background.py` — verify `--baseline`/`--baseline-skill`/`--items` are forwarded through `run_background()` to child process
- `scripts/tests/test_ll_loop_display.py` — terminal summary format assertions: verify A/B summary output contains "A/B Summary", "Harness pass-rate:", "Baseline pass-rate:", "Delta:", token/duration ratios

### Documentation
- `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` — add "Validating Your Harness" section with `--baseline` usage
- `.claude/CLAUDE.md` — cross-reference in § Loop Authoring

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md:381-444` — add `--baseline`, `--baseline-skill`, `--items` to `ll-loop run` flag table following existing boolean-flag row pattern
- `docs/guides/LOOPS_GUIDE.md` — add `--baseline` usage section and command-reference row following existing feature-subsection pattern (e.g., the `--context` JSON auto-unpack section)
- `docs/reference/API.md:4393-4449,4450-4476` — update `FSMExecutor` docs if `_execute_state()` spawns parallel arms; update `ActionResult` docs if token field added
- `docs/reference/EVENT-SCHEMA.md` — add new event types if `baseline_complete`, `ab_comparison`, or `ab_summary` events are emitted
- `CHANGELOG.md` — standard feature entry for `ll-loop run --baseline`
- `skills/create-loop/SKILL.md:157` — the `meta-optimize` template has a state named `baseline` (capturing a `baseline_score`); distinct from the `--baseline` CLI flag, but naming overlap warrants a disambiguation note in docs

### Configuration
- N/A — no config changes required

## Out of Scope

- Multi-iteration improvement tracking (covered by ENH "Cross-iteration comparator").
- Non-discriminating evaluator detection (covered by ENH "Detect non-discriminating evaluators").
- Auto-tuning the harness based on A/B results (a future meta-loop on top of this primitive).

## Related Key Documentation

| Path | Why relevant |
|------|--------------|
| `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` | The harness pattern being measured; this gates whether harnessing pays off |
| `.claude/CLAUDE.md` § Loop Authoring | MR-1 rule that this issue operationalizes |
| `.issues/enhancements/P2-ENH-1665-ll-loop-validate-meta-loop-lint-rules.md` | Sibling rule-enforcement work under EPIC-1663 |

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-05-30_

**Readiness Score**: 100/100 → PROCEED
**Outcome Confidence**: 71/100 → MODERATE

### Outcome Risk Factors
- Moderate per-site complexity: the parallel execution coordination in `_execute_state()` (spawning two subprocess arms with threading, blind anonymization, and de-anonymized scoring) is the highest-complexity change — multi-function, cross-module logic with shared state. Existing `ThreadPoolExecutor` patterns in `parallel/orchestrator.py` provide a proven template.
- Minor unresolved ambiguity: whether to extend `HostRunner.build_blocking_json()` to return token usage for the blind comparator, or accept the limitation. Defaulting to "accept limitation" is low-risk but should be decided before Phase 4 implementation.

## Session Log
- `/ll:confidence-check` - 2026-05-30T22:41:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d542f308-7cab-474d-867c-e6f0880d809d.jsonl`
- `/ll:refine-issue` - 2026-05-31T03:29:40 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/978f76da-364f-47df-9714-284d10ef065f.jsonl`
- `/ll:verify-issues` - 2026-05-31T02:30:14 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5267cfef-4fe8-420d-9d08-62e8f926a297.jsonl`
- `/ll:format-issue` - 2026-05-29T19:24:46 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d5eabe11-4b00-427f-9af0-61ff507f3409.jsonl`
- `/ll:capture-issue` - 2026-05-29T19:08:54Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5f057c8d-4a84-4a3e-a47b-50580694d9d6.jsonl`
- `/ll:wire-issue` - 2026-05-30T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/7cd48205-807a-4498-ba78-6558afacbf4d.jsonl`
- `/ll:issue-size-review` - 2026-05-30T23:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fffefcf7-6dbd-438c-bdd1-259bea8d77b7.jsonl`

---

## Resolution

- **Status**: Decomposed
- **Completed**: 2026-05-30
- **Reason**: Issue too large for single session (scored 11/11 — Very Large)

### Decomposed Into
- FEAT-1821: A/B Baseline CLI Flag Wiring and Parallel Execution
- FEAT-1822: A/B Baseline Blind Evaluation and Reporting
