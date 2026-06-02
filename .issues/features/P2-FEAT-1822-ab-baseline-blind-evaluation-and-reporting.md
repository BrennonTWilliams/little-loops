---
id: FEAT-1822
title: A/B Baseline Blind Evaluation and Reporting
type: FEAT
priority: P2
status: done
parent: FEAT-1790
completed_at: 2026-05-30 23:59:00+00:00
labels:
- feature
- loops
- harness
- evaluation
- ab-testing
confidence_score: 93
outcome_confidence: 83
score_complexity: 14
score_test_coverage: 22
score_ambiguity: 25
score_change_surface: 22
---

# FEAT-1822: A/B Baseline Blind Evaluation and Reporting

## Summary

Add blind LLM evaluation of paired harness/baseline outputs, aggregate results into `ab.json`, print a terminal summary with pass-rate and token/duration deltas, and update documentation. Builds on the parallel execution infrastructure from FEAT-1821.

## Current Behavior

`ll-loop run` does not support A/B comparison. Harness authors can run a single loop iteration but cannot quantitatively compare outputs against a baseline (ungated) arm to validate harness effectiveness.

## Expected Behavior

`ll-loop run --baseline` executes the loop in two parallel arms (harnessed and ungated), feeds paired outputs into a blind LLM judge, aggregates results into `ab.json`, and prints a terminal summary with pass-rate deltas and token/duration comparisons. Harness authors use this quantitative evidence to validate their harnesses.

## Parent Issue

Decomposed from FEAT-1790: A/B Baseline Mode for `ll-loop run`

## Motivation

FEAT-1821 provides the CLI surface and parallel execution. This child completes the A/B baseline feature by evaluating outputs blind, aggregating results, and producing the quantitative evidence that meta-loop authors need to defend their harnesses.

## Use Case

**Who**: Harness author (meta-loop developer)

**Context**: They've just written or modified a meta-loop harness and need to verify the harness actually improves output quality over unguided LLM calls.

**Goal**: Quantitatively compare harnessed vs. baseline (ungated) outputs to confirm the harness adds value.

**Outcome**: A terminal summary showing pass-rate delta, token/duration ratios, and per-item verdicts — plus `ab.json` for deeper analysis.

## Pre-requisite

FEAT-1821 (CLI flag wiring and parallel execution) must be complete. The blind evaluator and aggregation logic can be developed concurrently using mock arm outputs, but integration testing requires FEAT-1821's execution infrastructure.

## Implementation Steps

### Phase 3: Blind evaluation

Feed both arm outputs into a blind LLM judge. Build as a standalone function (NOT a new evaluator type — no registration in `evaluate()` dispatcher or `_EXIT_CODE_AWARE_EVALUATORS` needed). Reuse `evaluate_llm_structured()` at `fsm/evaluators.py:572`:

- Randomize order per item via `random.shuffle` (stdlib `random` already imported at `executor.py:14`; `random.shuffle()` is novel to codebase — only `random.uniform()` for jitter exists at L1544). Anonymize outputs as "Output A" and "Output B" with no indication of which is the harness arm.
- Call `evaluate_llm_structured()` once per output with a judgment prompt comparing the two anonymized outputs. The function internally calls `resolve_host().build_blocking_json()` (pattern at `evaluators.py:609`) which returns `HostInvocation` — the blind comparator must manually append `--json-schema` to `args` (same pattern as `evaluators.py:612-616`) since `ClaudeCodeRunner.build_blocking_json()` silently drops `json_schema` at `host_runner.py:294`.
- Use a custom schema extending `DEFAULT_LLM_SCHEMA` at `evaluators.py:59` — add a `better_output` field (`"enum": ["A", "B", "tie"]`) so the judge picks which anonymized output is better.
- De-anonymize after judgment to attribute scores to each arm.

### Phase 5: Aggregate and report

- Compute pass-rate delta, median token/duration, and per-item verdicts.
- Model aggregation after `calculate_summary()` in `issue_history/summary.py:21` (iterate items, accumulate counts into dataclass). Follow the `to_dict()` convention on all result dataclasses (`ExecutionResult`, `HistorySummary`, `CompletedIssue`) — `ABResults` must implement `to_dict() -> dict[str, Any]`.
- Write `ab.json` to `${context.run_dir}/ab.json` using `atomic_write_json()` from `file_utils.py:35` (handles `mkdir(parents=True)`, `json.dumps(indent=2)`, and defensive round-trip validation). `run_dir` is injected at `cmd_run()` line 162.
- Define `ab.json` schema using the `_schema()` builder pattern from `generate_schemas.py:23-74`.
- Print terminal summary using `run_foreground()` completion block at `cli/loop/_helpers.py:1226-1248` as the output point. Use `colorize()` at `cli/output.py:139` for ANSI formatting, `status_block()` at L266 for aligned key-value pairs, and `table()` at L218 for the per-item verdict table.
- A/B summary output renders after the existing "Loop completed" line (L1226-1248) — read `ab.json` from run directory and print delta table.

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

### Wiring Phase (added by `/ll:wire-issue`)

_Wiring pass added by `/ll:wire-issue`:_
_These touchpoints were identified by wiring analysis and must be included in the implementation._

15. Add `_schema()` calls in `scripts/little_loops/generate_schemas.py` for `baseline_complete`, `ab_comparison`, and `ab_summary` event types — use `_schema()` builder pattern at `generate_schemas.py:23-74`; each emits to `docs/reference/schemas/`.
16. Add `evaluate_blind_comparator()` function signature and description to the Evaluators section of `docs/reference/API.md` (lines 4283-4382) — follow existing pattern for `evaluate_llm_structured()`.
17. Update the Quick Import block in `docs/reference/API.md` (lines 3941-3964) — add `evaluate_blind_comparator`, `BLIND_COMPARATOR_SCHEMA`, `DEFAULT_BLIND_COMPARATOR_PROMPT`, `ABResults`, `calculate_ab_summary`, `write_ab_json` to the `from little_loops.fsm import (...)` example.
18. Add `baseline_complete`, `ab_comparison`, `ab_summary` event type documentation to `docs/reference/EVENT-SCHEMA.md` with field tables following existing event-type format.
19. Add disambiguation note in `skills/create-loop/templates.md` (lines 22, 124-177) and `skills/create-loop/loop-types.md` (lines 1219-1300) — `baseline:` state name in meta-optimize template is distinct from `--baseline` CLI flag for A/B comparison.
20. Cross-reference FEAT-1790/1822 in `.issues/epics/P2-EPIC-1663-*.md` and `.issues/enhancements/P2-ENH-1665-*.md` as the empirical validation primitive for harness design rules.
21. Verify `scripts/tests/test_enh1138_doc_wiring.py` after API.md Quick Import block is updated — test asserts on specific symbol names in the doc import block.

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
- `scripts/little_loops/fsm/executor.py` — call blind comparator after both arms complete; accumulate `_ab_results`; write `ab.json` in `_finish()`; emit `ab_comparison` and `ab_summary` events
- `scripts/little_loops/fsm/__init__.py` — export new public symbols from `ab_writer` and `evaluators`
- `scripts/little_loops/cli/loop/_helpers.py` — A/B summary output in `run_foreground()` completion block
- `scripts/little_loops/generate_schemas.py` — add `_schema()` calls for `baseline_complete`, `ab_comparison`, `ab_summary` event types
- `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` — "Validating Your Harness" section
- `.claude/CLAUDE.md` — cross-reference in § Loop Authoring
- `docs/reference/CLI.md` — flag table entries
- `docs/guides/LOOPS_GUIDE.md` — `--baseline` usage section
- `docs/reference/API.md` — add `evaluate_blind_comparator()` to evaluators section; update Quick Import block with new symbols
- `CHANGELOG.md` — feature entry

### Dependent Files (Callers/Importers)
- `scripts/little_loops/host_runner.py` — `build_blocking_json()` for blind comparator
- `scripts/little_loops/issue_history/summary.py` — `calculate_summary()` aggregation pattern
- `scripts/little_loops/issue_history/formatting.py` — multi-format output pattern
- `scripts/little_loops/generate_schemas.py` — `_schema()` builder for ab.json schema and new event type schemas
- `scripts/little_loops/cli/loop/run.py` — reads `args.baseline` to populate `fsm.context["_baseline"]` (FEAT-1821); wiring step may add ab.json path injection
- `scripts/little_loops/cli/loop/lifecycle.py` — gates baseline support during resume (FEAT-1821); verify no ab.json orphan on resume-with-baseline

### Similar Patterns
- `scripts/little_loops/loops/harness-single-shot.yaml:113-131` — `check_semantic` state with `llm_structured` evaluator and `source:` redirection
- `scripts/little_loops/issue_history/summary.py:21` — `calculate_summary()` aggregation pattern
- `scripts/little_loops/generate_schemas.py:23-74` — JSON schema generation using `_schema()` helper
- `scripts/little_loops/file_utils.py:35` — `atomic_write_json()` with round-trip validation for writing `ab.json`
- `scripts/little_loops/cli/output.py:139,218,266` — `colorize()`, `table()`, `status_block()` for terminal summary formatting
- `scripts/little_loops/issue_history/models.py:17,46` — `to_dict()` convention on `CompletedIssue` and `HistorySummary` dataclasses

### Codebase Research Findings

- **Blind evaluator limitation**: `evaluate_llm_structured()` in `fsm/evaluators.py:572` calls `resolve_host().build_blocking_json()` (line 609) which returns JSON output only — no streaming, no token count. The blind comparator's own token usage won't be available.
- **No existing anonymization**: Confirmed — no blind/anonymization/shuffle pattern exists anywhere in the codebase. The `random` stdlib module is available (`import random` at `executor.py:14`); the blind comparator prompt must avoid revealing which output came from the harnessed arm. `random.shuffle()` would be novel to the codebase — the only existing randomization is `random.uniform()` for rate-limit jitter at `executor.py:1544`.
- **run_dir injection**: Context key `run_dir` is injected at `cmd_run()` in `cli/loop/run.py:162` as `str(loops_dir / "runs" / instance_id) + "/"` — the `ab.json` path `.loops/runs/<id>/ab.json` aligns with this convention.
- **baseline_complete event shape**: Emitted at `executor.py:1379-1388` with fields `harness_duration_ms`, `baseline_duration_ms`, `harness_tokens`, `baseline_tokens`. The blind comparator runs after this event — it receives paired outputs but needs to add pass/fail verdicts that the current event does not carry.
- **atomic_write_json() available**: `file_utils.py:35` provides `atomic_write_json(path, data)` with `mkdir(parents=True)`, `json.dumps(indent=2, allow_nan=False)`, and defensive round-trip validation. Use this for writing `ab.json` instead of bare `Path.write_text()` or `json.dump()`.
- **to_dict() convention**: All existing result dataclasses (`ExecutionResult` at `fsm/types.py:16`, `HistorySummary` at `issue_history/models.py:46`, `CompletedIssue` at `issue_history/models.py:17`) implement `to_dict() -> dict[str, Any]` for JSON serialization. `ABResults` should follow this convention.
- **Terminal formatting utilities**: `colorize(text, code)` at `cli/output.py:139`, `status_block(items: dict[str, str])` at L266, and `table(headers, rows)` at L218 are available for the A/B terminal summary output. The existing completion block at `_helpers.py:1226-1248` shows the pattern for post-execution summary display.
- **build_blocking_json() drops schema for Claude CLI**: `ClaudeCodeRunner.build_blocking_json()` at `host_runner.py:274` silently drops the `json_schema` parameter. `evaluate_llm_structured()` manually appends `--json-schema` to args at `evaluators.py:612-616`. The blind comparator calling `build_blocking_json()` directly must do the same.
- **Blind comparator is NOT a new evaluator type**: It does not need registration in the `evaluate()` dispatcher at `evaluators.py:743` or `_EXIT_CODE_AWARE_EVALUATORS` at L779. It's a standalone function that calls `evaluate_llm_structured()` under the hood — pairing two outputs through it with randomized anonymization.

### Tests
- `scripts/tests/test_ab_writer.py` (NEW) — schema validation tests (JSON Schema draft-07), writer round-trip tests, summary aggregation tests (pass-rates, medians, deltas), edge cases (empty results, single item, all-pass, all-fail)
- `scripts/tests/test_fsm_evaluators.py` — blind comparator tests in new `TestBlindComparator` class: anonymization verification (judge prompt must not contain "harness"/"baseline"/"gated"/"ungated"), de-anonymization correctness (scores map back to correct arm), verdict combination tests (both-pass, harness-only-pass, baseline-only-pass, both-fail)
- `scripts/tests/test_fsm_executor.py` — baseline arm integration tests: verify `_ab_results` accumulation across items, `ab_summary` event emission with correct fields, `ab.json` written in `_finish()` when `_ab_results` is populated, degraded-result path when blind evaluation fails
- `scripts/tests/test_ll_loop_display.py` — terminal summary format assertions: verify A/B summary output contains "A/B Summary", "Harness pass-rate:", "Baseline pass-rate:", "Delta:", token/duration ratios; verify no crash when `ab.json` missing or corrupt
- `scripts/tests/test_enh1138_doc_wiring.py` — may need update after new symbols added to `__all__` and API.md Quick Import block; verify new exports appear in doc

### Documentation
- `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` — add "Validating Your Harness" section
- `.claude/CLAUDE.md` — cross-reference in § Loop Authoring
- `docs/reference/CLI.md:381-444` — add `--baseline`, `--baseline-skill`, `--items` to flag table
- `docs/guides/LOOPS_GUIDE.md` — add `--baseline` usage section
- `docs/reference/API.md:4393-4449,4450-4476` — update `FSMExecutor` docs if `_execute_state()` spawns parallel arms; update `ActionResult` docs if token field added
- `docs/reference/API.md:3941-3964` — update Quick Import block with `evaluate_blind_comparator`, `BLIND_COMPARATOR_SCHEMA`, `DEFAULT_BLIND_COMPARATOR_PROMPT`, `ABResults`, `calculate_ab_summary`, `write_ab_json`
- `docs/reference/API.md:4283-4382` — add `evaluate_blind_comparator()` function signature and description in Evaluators section
- `docs/reference/EVENT-SCHEMA.md` — add `baseline_complete`, `ab_comparison`, `ab_summary` event type documentation with field tables
- `CHANGELOG.md` — standard feature entry
- `skills/create-loop/SKILL.md:157` — disambiguation note for `baseline` state in `meta-optimize` template vs. `--baseline` CLI flag
- `skills/create-loop/templates.md:22,124-177` — same disambiguation: `baseline:` state name in meta-optimize template vs. A/B baseline flag
- `skills/create-loop/loop-types.md:1219-1300` — same disambiguation in meta-optimize reference docs
- `.issues/epics/P2-EPIC-1663-codify-meta-loop-harness-design-rules.md` — cross-reference FEAT-1790/1822 as empirical validation primitive for harness design rules
- `.issues/enhancements/P2-ENH-1665-ll-loop-validate-meta-loop-lint-rules.md` — cross-reference FEAT-1790/1822 as empirical validation primitive for lint rules

## API/Interface

### New module: `scripts/little_loops/ab_writer.py`

```python
@dataclass
class ABResults:
    """Aggregated A/B comparison results."""
    harness_pass_rate: float
    baseline_pass_rate: float
    delta: float
    median_tokens_harness: int
    median_tokens_baseline: int
    median_duration_harness: float
    median_duration_baseline: float
    per_item: list[dict]

def write_ab_json(results: ABResults, run_dir: str) -> None:
    """Write ab.json to the run directory."""

def calculate_ab_summary(per_item_results: list[dict]) -> ABResults:
    """Aggregate per-item verdicts into summary statistics."""
```

### Modified: `scripts/little_loops/fsm/__init__.py`

- Add `ABResults`, `write_ab_json` to `__all__`

### Modified: `scripts/little_loops/fsm/evaluators.py`

- New blind comparator evaluator (reuses `evaluate_llm_structured()` pattern)

## Out of Scope

- CLI flag wiring and parallel execution (FEAT-1821)
- Multi-iteration improvement tracking
- Non-discriminating evaluator detection
- Auto-tuning the harness based on A/B results

## Session Log
- `/ll:wire-issue` - 2026-05-31T04:50:10 - `723a5598-07cc-4fa4-8ccd-f304cb75343b.jsonl`
- `/ll:wire-issue` - 2026-05-31T04:50:06 - `723a5598-07cc-4fa4-8ccd-f304cb75343b.jsonl`
- `/ll:refine-issue` - 2026-05-31T04:42:30 - `f9590608-82fc-47be-be21-ce61b52c070b.jsonl`
- `/ll:format-issue` - 2026-05-31T04:30:15 - `ab2f4112-ed66-4b9b-8254-f2481b5689f4.jsonl`
- `/ll:issue-size-review` - 2026-05-30T23:00:00Z - `fffefcf7-6dbd-438c-bdd1-259bea8d77b7.jsonl`
- `/ll:confidence-check` - 2026-05-31T04:54:16Z - `702b1067-ab29-4c28-85f5-65e4d6327c3f.jsonl`
