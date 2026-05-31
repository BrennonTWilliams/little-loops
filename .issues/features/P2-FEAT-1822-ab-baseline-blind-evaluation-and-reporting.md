---
id: FEAT-1822
title: A/B Baseline Blind Evaluation and Reporting
type: FEAT
priority: P2
status: open
parent: FEAT-1790
labels:
- feature
- loops
- harness
- evaluation
- ab-testing
---

# FEAT-1822: A/B Baseline Blind Evaluation and Reporting

## Summary

Add blind LLM evaluation of paired harness/baseline outputs, aggregate results into `ab.json`, print a terminal summary with pass-rate and token/duration deltas, and update documentation. Builds on the parallel execution infrastructure from FEAT-1821.

## Parent Issue

Decomposed from FEAT-1790: A/B Baseline Mode for `ll-loop run`

## Motivation

FEAT-1821 provides the CLI surface and parallel execution. This child completes the A/B baseline feature by evaluating outputs blind, aggregating results, and producing the quantitative evidence that meta-loop authors need to defend their harnesses.

## Pre-requisite

FEAT-1821 (CLI flag wiring and parallel execution) must be complete. The blind evaluator and aggregation logic can be developed concurrently using mock arm outputs, but integration testing requires FEAT-1821's execution infrastructure.

## Implementation Steps

### Phase 3: Blind evaluation

Feed both arm outputs into a blind LLM judge. Build a new evaluator or reuse `evaluate_llm_structured()` at `fsm/evaluators.py:572`:

- Randomize order per item (stdlib `random.shuffle`) — anonymize outputs as "Output A" and "Output B" with no indication of which is the harness arm.
- Call `resolve_host().build_blocking_json()` (pattern at `evaluators.py:609`) with the judgment prompt.
- The judge returns structured output (`verdict`, `confidence`, `reason`) via the `DEFAULT_LLM_SCHEMA` at `evaluators.py:59`.
- De-anonymize after judgment to attribute scores to each arm.

### Phase 5: Aggregate and report

- Compute pass-rate delta, median token/duration, and per-item verdicts.
- Model aggregation after `calculate_summary()` in `issue_history/summary.py:21` (iterate items, accumulate counts into dataclass).
- Write `ab.json` to `${context.run_dir}/ab.json` — `run_dir` is injected at `cmd_run()` line 162.
- Define `ab.json` schema using the `_schema()` builder pattern from `generate_schemas.py:23-74`.
- Print terminal summary using `run_foreground()` completion block at `cli/loop/_helpers.py:1204-1225` as the output point.

**Evaluator tokens limitation**: The blind comparator's own token usage via `build_blocking_json()` is not available from the current host-runner path — accept this as a known limitation.

### Phase 7: Documentation

- Add "Validating Your Harness" section to `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` with `--baseline` usage example and output interpretation guidance.
- Cross-reference in `.claude/CLAUDE.md` § Loop Authoring (lines 88-131) — link to the new guide section.
- Mention in EPIC-1663 and ENH-1665 issue files as the empirical validation primitive.

### Wiring Step 9: A/B summary in `run_foreground()`

Insert A/B summary output after the existing "Loop completed" line at `scripts/little_loops/cli/loop/_helpers.py:1204-1225`; read `ab.json` from run directory and print delta table.

### Wiring Step 11: Public API exports

Add `ABResults`, `write_ab_json`, and any other public symbols from `ab_writer.py` to `__all__` in `scripts/little_loops/fsm/__init__.py:162-231`.

### Wiring Step 12: CLI flag table

Add `--baseline`, `--baseline-skill`, and `--items` rows to the `ll-loop run` flag table at `docs/reference/CLI.md:381-444` following existing boolean-flag row format.

### Wiring Step 13: Loop guide update

Add `--baseline` usage section with example invocation and output interpretation to `docs/guides/LOOPS_GUIDE.md` following existing feature-subsection pattern.

### Wiring Step 14: Changelog entry

Standard feature entry in `CHANGELOG.md` under dated version header referencing FEAT-1790.

## Acceptance Criteria

- [ ] Blind anonymization verified (judge prompt does not reveal which arm is the harness)
- [ ] De-anonymization correct (scores map back to correct arm after judgment)
- [ ] `ab.json` written with per-item records and summary block matching schema
- [ ] Terminal summary prints delta, token/duration ratios
- [ ] All four pass/fail combinations handled (both-pass, harness-only-pass, baseline-only-pass, both-fail)
- [ ] Documentation updated with usage example in AUTOMATIC_HARNESSING_GUIDE.md
- [ ] Cross-reference in CLAUDE.md § Loop Authoring
- [ ] CLI flag table updated in docs/reference/CLI.md

## Output Format

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

## Impact

- **Priority**: P2
- **Effort**: Medium — blind evaluator, aggregation logic, ab.json schema/writer, terminal summary formatting, documentation updates
- **Risk**: Low — Additive; builds on FEAT-1821's execution infrastructure
- **Breaking Change**: No

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/evaluators.py` — blind LLM judge (new evaluator or reuse `evaluate_llm_structured()`)
- `scripts/little_loops/ab_writer.py` (new) — `ab.json` schema, writer, and summary aggregation
- `scripts/little_loops/fsm/__init__.py` — export new public symbols from `ab_writer`
- `scripts/little_loops/cli/loop/_helpers.py` — A/B summary output in `run_foreground()` completion block
- `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` — "Validating Your Harness" section
- `.claude/CLAUDE.md` — cross-reference in § Loop Authoring
- `docs/reference/CLI.md` — flag table entries
- `docs/guides/LOOPS_GUIDE.md` — `--baseline` usage section
- `CHANGELOG.md` — feature entry

### Dependent Files (Callers/Importers)
- `scripts/little_loops/host_runner.py` — `build_blocking_json()` for blind comparator
- `scripts/little_loops/issue_history/summary.py` — `calculate_summary()` aggregation pattern
- `scripts/little_loops/issue_history/formatting.py` — multi-format output pattern
- `scripts/little_loops/generate_schemas.py` — `_schema()` builder for ab.json schema

### Similar Patterns
- `scripts/little_loops/loops/harness-single-shot.yaml:113-131` — `check_semantic` state with `llm_structured` evaluator and `source:` redirection
- `scripts/little_loops/issue_history/summary.py:21` — `calculate_summary()` aggregation pattern
- `scripts/little_loops/generate_schemas.py:23-74` — JSON schema generation using `_schema()` helper

### Codebase Research Findings

- **Blind evaluator limitation**: `evaluate_llm_structured()` in `fsm/evaluators.py:572` calls `resolve_host().build_blocking_json()` (line 609) which returns JSON output only — no streaming, no token count. The blind comparator's own token usage won't be available.
- **No existing anonymization**: Confirmed — no blind/anonymization/shuffle pattern exists anywhere in the codebase. The `random` stdlib module is available; the blind comparator prompt must avoid revealing which output came from the harnessed arm.
- **run_dir injection**: Context key `run_dir` is injected at `cmd_run()` in `cli/loop/run.py:162` as `str(loops_dir / "runs" / instance_id) + "/"` — the `ab.json` path `.loops/runs/<id>/ab.json` aligns with this convention.

### Tests
- `scripts/tests/test_ab_writer.py` (NEW) — schema validation tests (JSON Schema draft-07), writer round-trip tests, summary aggregation tests (pass-rates, medians, deltas), edge cases (empty results, single item, all-pass, all-fail)
- `scripts/tests/test_fsm_evaluators.py` — blind comparator tests in new `TestBlindComparator` class: anonymization verification (judge prompt must not contain "harness"/"baseline"/"gated"/"ungated"), de-anonymization correctness (scores map back to correct arm), verdict combination tests (both-pass, harness-only-pass, baseline-only-pass, both-fail)
- `scripts/tests/test_ll_loop_display.py` — terminal summary format assertions: verify A/B summary output contains "A/B Summary", "Harness pass-rate:", "Baseline pass-rate:", "Delta:", token/duration ratios

### Documentation
- `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` — add "Validating Your Harness" section
- `.claude/CLAUDE.md` — cross-reference in § Loop Authoring
- `docs/reference/CLI.md:381-444` — add `--baseline`, `--baseline-skill`, `--items` to flag table
- `docs/guides/LOOPS_GUIDE.md` — add `--baseline` usage section
- `docs/reference/API.md:4393-4449,4450-4476` — update `FSMExecutor` docs if `_execute_state()` spawns parallel arms; update `ActionResult` docs if token field added
- `docs/reference/EVENT-SCHEMA.md` — add new event types if `baseline_complete`, `ab_comparison`, or `ab_summary` events are emitted
- `CHANGELOG.md` — standard feature entry
- `skills/create-loop/SKILL.md:157` — disambiguation note for `baseline` state in `meta-optimize` template vs. `--baseline` CLI flag

## Out of Scope

- CLI flag wiring and parallel execution (FEAT-1821)
- Multi-iteration improvement tracking
- Non-discriminating evaluator detection
- Auto-tuning the harness based on A/B results

## Session Log
- `/ll:issue-size-review` - 2026-05-30T23:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fffefcf7-6dbd-438c-bdd1-259bea8d77b7.jsonl`
