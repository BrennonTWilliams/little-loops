---
id: ENH-3435
title: Measure and cache an unmutated baseline arm before the first change, and make the cache bidirectional
type: ENH
priority: P2
status: open
discovered_date: '2026-09-10'
labels: []
learning_tests_required:
  - pyyaml
---

## Summary

An `ll-harness` verdict of the form "this change improved things" is a claim against a before-number, and today that number is remembered rather than measured. The delta must come from an unmutated arm run on the same task, at the same n, under the same conditions as the candidate, or the claimed delta describes two different systems. Make the baseline an explicit phase of the run: before the first proposal, execute n unmutated runs and record the result. That also calibrates magnitude, which is what makes any subsequent proposal meaningful — "make this better" is not actionable when the baseline is already at zero, exactly as "make this harder" is not.

Make the cache bidirectional, which is the part that pays for itself. The loop and any post-hoc analysis write and read the same result shape, so a rollout paid for once is reusable in either direction instead of being re-paid per analysis. In a system where every measurement is an API call, this is a direct cost argument sitting inside a verdict-integrity mechanism.

Cache resilience is part of the contract: a corrupt or partial cache entry must degrade to re-measuring, never to a silently wrong baseline.

## Current Behavior

`ll-harness` comparisons are incumbent-relative: a candidate is graded against whatever the incumbent lineage last produced, and any "before" number cited in a verdict is remembered from an earlier run rather than measured as part of this one. The existing cache is one-directional — a result paid for on one path is not reusable by the other. The two sibling guards are now in place: n-run redundancy (ENH-3415) supplies a sound n, and the frozen external reference (ENH-3421) supplies an external anchor. Both assume a baseline exists; neither makes producing the unmutated incumbent-arm baseline a phase of the run itself. This issue is that remaining piece.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-10 — based on codebase analysis:_

- The "remembered" before-number characterized above is, concretely, `_read_target_history()` (`scripts/little_loops/cli/harness.py:760`) — a rolling 30-day historical pass/abstention rate pulled from `harness_events` via `history_reader.harness.recent_harness_events`, filtered to non-superseded rows (ENH-3408), and suppressed per-rate when its denominator is below `_HISTORY_MIN_SCORED = 3` (`:757`). It is not a single prior run's number, and it is not scoped to the same conditions/n as the current invocation — it is a wider-window rate, rendered via `_format_target_history_line()` (`:826`) as a status line displayed alongside the current run's verdict, never algebraically diffed against it. `ll-harness` computes no delta today: a case-insensitive grep of `cli/harness.py` for `delta`/`baseline` returns zero hits outside the unrelated `datetime.timedelta` import.
- ENH-3421's "frozen external reference" guard lives in the FSM `convergence` evaluator (`scripts/little_loops/fsm/evaluators.py`, ~line 1938) — a different subsystem from `ll-harness`'s cell/repetition run model in `cli/harness.py`. No shared code, cache, or `_cell_key` usage was found between the two; ENH-3421 does not currently supply an anchor into `ll-harness` runs. Treat the "two sibling guards ... both assume a baseline exists" framing above as aspirational architecture, not a description of code that exists today.
- A separate, architecturally unrelated "baseline" concept already exists: `ll-loop run <loop> --baseline` / `ll-loop promote-baseline <loop>`, an FSM meta-loop A/B score-reversion comparator (`docs/guides/HARNESS_OPTIMIZATION_GUIDE.md:438-500`, `scripts/little_loops/loops/harness-optimize.yaml`'s `baseline_score` state). It shares no code path with `ll-harness`'s cell/repetition model and should not be conflated with the baseline phase this issue proposes.

## Expected Behavior

Before an `ll-harness` run reports any delta, it executes n unmutated runs of the incumbent (same task set, same effective n, same conditions as the candidate arm) and records that result as the measured baseline. Verdicts compute deltas only against this measured baseline — never against a remembered number from a prior run. The baseline result persists to a disk cache in a defined shape that both the loop and post-hoc analysis read and write, so a rollout paid for on either path is reusable by the other. A corrupt or partial cache entry triggers re-measurement rather than being trusted, and every reported delta states whether its baseline was freshly measured or reused from cache, along with the n and conditions it was measured under.

## Design

Mechanics borrowed from evolutionary-search harness design, where the baseline arm is treated as mandatory loop structure rather than optional rigor:

- **Baseline phase before the first proposal.** Per task, before the agent's first proposal or mutation is evaluated, execute n unmutated runs — same task, same effective n as the candidate arm, same conditions (model, host, timeout, criteria) — and record the result. The n is whatever the candidate arm will use, so the two arms are directly comparable; nothing about the sample machinery is redefined here.
- **Disk-cached, bidirectional.** The baseline result persists to a disk cache with a defined result shape. The loop writes it; any post-hoc analysis reads it — and writes the same shape back, so a checkpoint evaluation performed after the fact feeds the next run's baseline lookup. Either direction can consume the other's already-paid rollouts. This is the difference between paying for a baseline once and paying for it per analysis.
- **Degrade, never lie.** A corrupt or partial cache entry is discarded and re-measured. The failure mode being guarded against is a silently wrong baseline — a plausible-looking cached number that no longer describes the system it claims to. Cache resilience is explicitly unit-testable and must be tested.
- **Provenance on the delta.** A verdict that reports a delta names its baseline: task set, n, conditions, and whether the baseline was freshly measured or reused from cache.

On the run model (ENH-3397): baseline runs are ordinary repetitions recorded against their own named cells (`task × repetition × subject`), with the unmutated incumbent as the subject. Nothing about attempt classification changes; the baseline arm simply is another subject the existing machinery scores.

## Scope Boundaries

- **In scope**: the baseline phase in the `ll-harness` run path (execute-before-first-change, at the candidate's effective n), the disk cache and its result shape, the bidirectional read/write contract between loop-time and post-hoc analysis, corrupt/partial-entry degradation, and delta provenance reporting.
- **Out of scope**: n-run redundancy and its `--samples` semantics (ENH-3415, done); the frozen external reference guard (ENH-3421, done); the repetition/infra-retry/continuation attempt model (ENH-3397, done); widening the evidence surface beyond the current channels; scoring runs on an efficiency vector. Those are separate concerns that compose with this one.

## Acceptance Criteria

1. Before the first proposal in a harness run that will report a delta, n unmutated runs execute on the same task set, at the same effective n, under the same conditions as the candidate arm.
2. A run that would report a delta without a measured baseline either refuses or reports an explicit "no measured baseline" state — it never falls back to comparing against a remembered number.
3. Baseline results persist to a disk cache under a defined result shape, keyed so subsequent invocations on the same task and conditions reuse them.
4. The cache is bidirectional: one test shows a loop-produced baseline consumed by post-hoc analysis without re-running the subject, and one shows a post-hoc-produced result consumed as a run's baseline.
5. A corrupt or partial cache entry causes re-measurement and re-write, not use; a test writes a deliberately corrupted entry and asserts the baseline is re-measured.
6. A reported delta names its baseline's provenance: fresh or reused, the n, and the conditions.
7. Existing single-shot and n-sample verdict behavior is unchanged when no baseline is requested; the test suite passes.

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-10 — based on codebase analysis:_

**Files to Modify**
- `scripts/little_loops/cli/harness.py` — the baseline phase, `read_baseline`/`write_baseline`, and `_run_baseline_phase` land here alongside the existing `_cell_key` (`:144`), `_effective_samples` (`:912`), `_run_sample_loop` (`:1036`), `_evaluate_and_report` (`:1094`)
- `scripts/little_loops/learning_tests/__init__.py` — cited by the issue's Program Design as the model for `read_baseline`/`write_baseline`; its own `read_record`/`write_record` pair is the reference implementation, not a shared function this issue calls into

**Dependent Files (Callers/Importers)**
- `scripts/little_loops/cli/__init__.py:69` — imports `cli.harness`
- `scripts/tests/test_cli_harness.py:14` — imports `cli.harness`; contains ~30 `cmd_dsl` call sites (`TestCmdDsl`, `TestCmdDslRetryOf`, `TestHarnessEventPersistence` classes) and the `TestSampleLoopIntegration::test_dsl_refuses_samples_gt_1` case that would need updating if the baseline phase changes `cmd_dsl`'s `--samples` handling
- `scripts/little_loops/history_reader/harness.py` — reads `harness_events` post-hoc (`authoritative_attempts`, `harness_eval_pass_rate`); a distinct SQLite-backed read surface from the disk-file `BaselineResult` cache this issue proposes — no existing code here reads or writes a `BaselineResult`-shaped artifact

**Tests**
- `scripts/tests/test_cli_harness.py` — existing `ll-harness` coverage; no baseline/cache tests present yet (0 hits for `BaselineResult`/`read_baseline`/`write_baseline`/`_run_baseline_phase` outside the issue file itself)
- `scripts/tests/test_learning_tests.py::TestReadRecord` (lines 183-229) — the test class for the cited model; covers only the missing-file case (`test_returns_none_when_missing`) and successful round-trips. It contains no test that writes malformed YAML content and asserts degrade behavior — that gap is analyzed further under Program Design's findings below.

**Documentation**
- `docs/guides/EVALUATION_GUIDE.md` — `ll-harness` conceptual/usage docs (`_grade()` reference at `:96`, `DEFAULT_STOCHASTIC_SAMPLES` at `:343`, `harness_events`/`.ll/history.db` at `:373`)
- `docs/reference/API.md` — `little_loops.learning_tests` module reference (`:7354` `## little_loops.learning_tests` section, `write_record`/`check_learning_test` examples at `:7432`/`:7482`)

**Conventions in Force**
- Disk caches in this codebase degrade to `None` on read failure via an explicit `try/except` around the parse call, not an unguarded call — e.g. `rate_limit_circuit._read_unlocked()` catches `json.JSONDecodeError` and logs a `logger.warning` naming the file (`scripts/little_loops/fsm/rate_limit_circuit.py:104`); `fsm/persistence.py:load_state()` uses two separate `try/except` blocks — one for `json.JSONDecodeError` on the raw parse, a second `except KeyError` around `from_dict()` construction for schema-level corruption (`scripts/little_loops/fsm/persistence.py:525`). The cited model, `learning_tests.read_record`/`_read_frontmatter_yaml` (`scripts/little_loops/learning_tests/__init__.py:106,129`), degrades to `None` only when the `---\n...\n---` frontmatter delimiter regex fails to match (file absent or no frontmatter block) — a `yaml.safe_load()` call on content that has valid delimiters but malformed YAML inside them is unguarded and would raise `yaml.YAMLError` uncaught, and `LearnTestRecord.from_dict()` (`:77`) does unguarded `data["target"]`/`data["date"]` key access that would raise `KeyError` on a partial entry. Two disagreeing conventions exist for the corrupt-content case; the mirrored model does not itself satisfy the broader "degrade on corrupt OR partial" contract this issue's AC5 requires.
- Cache writes in this codebase use a tempfile-then-`os.replace` atomic-write idiom — `rate_limit_circuit._write_atomic()` (`:121`) and `fsm/persistence.py:save_state()` (`:502`) each reimplement it manually via `tempfile.mkstemp(dir=parent)` + `os.replace`, while a shared, already-used-in-28-files helper (`scripts/little_loops/file_utils.py:atomic_write()` at `:16`, `atomic_write_json()` at `:35`, which round-trip-validates via a defensive `json.loads` before replacing) exists but is not called by either. The cited model, `learning_tests.write_record` (`:114`), instead does a plain unguarded `Path.write_text()` with no atomicity guard at all.
- No dataclass in this codebase serializes via `dataclasses_json`/`pydantic` — every example found (`LearnTestRecord`/`Assertion`, `ABResults`, `ProcessingState`, `LoopState`) hand-writes its own serialization. Two distinct shapes coexist: classmethod-based `to_dict`/`from_dict` on the dataclass itself (`LearnTestRecord.to_dict`/`.from_dict`, `learning_tests/__init__.py:65,77` — the shape the issue's Program Design's `BaselineResult` implicitly follows) versus standalone module-level serialize/deserialize functions with the dataclass itself carrying neither (`ab_results_to_dict()` plus inlined `.get(key, default)` deserialization in `read_ab_json()`, `scripts/little_loops/ab_writer.py:210,245`).
- No existing example in the codebase is a *fully* bidirectional cache (two independent call paths that each both read and write the same artifact shape). The closest is `ab_writer.write_ab_json()`/`read_ab_json()` (`scripts/little_loops/ab_writer.py:233,245`) — the executor writes `ab.json` (`scripts/little_loops/fsm/executor.py:4341-4346`), and two separate consumer sites read it (`cli/loop/summary.py:52,219-220`) — but nothing currently writes `ab.json` from the read/summary side, so it is write-once/read-many, not bidirectional. No second example of a genuinely bidirectional shared-cache file was found in a repo-wide search.
- The corrupt-cache tests that do exist in this codebase (`test_fsm_persistence.py::test_load_state_returns_none_for_invalid_json:276`, `test_state.py::test_load_invalid_json:260`, `test_ab_writer.py::test_read_invalid_json:198`) share one shape: write a literal malformed-content string directly to the target file path, call the read function, and assert `is None` (two of the three also assert a `logger.error`/`logger.warning` call). None of them then calls the writer and asserts the corrupt file gets overwritten — every existing test covers only the read-degrades-to-None half of AC5's "re-measurement and re-write" requirement, not the write-back half.

## Program Design

### Types

- `BaselineResult`: `task: str`, `n: int`, `conditions: dict[str, Any]`, `outcome: HarnessEvalOutcome`, `measured_at: str`, `source: Literal["measured", "cached"]`

### Signatures

- `read_baseline(cell_key: str, *, base_dir: Path | None = None) -> BaselineResult | None` — cache read; returns `None` on missing or corrupt entry (degrade-to-remeasure), mirroring `learning_tests.read_record` (`scripts/little_loops/learning_tests/__init__.py:129`)
- `write_baseline(result: BaselineResult, *, base_dir: Path | None = None) -> Path` — cache write, keyed by `_cell_key(runner, target, head_sha)` (`scripts/little_loops/cli/harness.py:144`), mirroring `learning_tests.write_record` (`scripts/little_loops/learning_tests/__init__.py:114`)
- `_run_baseline_phase(args: argparse.Namespace, runner, n: int) -> BaselineResult` — new function in `cli/harness.py`, sibling to `_run_sample_loop` (`cli/harness.py:1036`); on cache miss, drives n unmutated runs via the existing `_run_sample_loop`/`_effective_samples` (`cli/harness.py:912`) machinery and calls `write_baseline`

### Call Path

`cmd_dsl` (`cli/harness.py:1484`) -> `_run_baseline_phase` -> `read_baseline` (cache hit) or `_run_sample_loop` + `write_baseline` (cache miss) -> `_evaluate_and_report` (`cli/harness.py:1094`, extended to accept the `BaselineResult` for delta + provenance reporting)

`cmd_skill` (`:1217`), `cmd_cmd` (`:1282`), `cmd_mcp` (`:1340`), and `cmd_prompt` (`:1433`) follow the identical cell_key -> `_effective_samples` -> (`_run_sample_loop` or single invoke) -> `_evaluate_and_report` shape as `cmd_dsl`, so the same `_run_baseline_phase` insertion point exists in each — but this Call Path names only `cmd_dsl`. `cmd_dsl` also refuses `--samples > 1` today (`:1497-1504`) and runs each task exactly once via `_run_prompt_action` (`:1613`), unlike the other four, which already branch through `_run_sample_loop` for n>1.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-10 — based on codebase analysis:_

- `_cell_key(runner, target, head_sha)` (`scripts/little_loops/cli/harness.py:144`) already encodes exactly the triple the Program Design's `write_baseline`/`read_baseline` key on: per ENH-3397's run model (`cell = (target, task, subject)`, `subject = runner_label + head_sha`), `head_sha` is what already distinguishes an unmutated-incumbent run from a post-change candidate run of the same `runner`/`target`. No new key scheme needs inventing — confirmed call sites are `cmd_skill:1222`, `cmd_cmd:1286`, and `cmd_dsl`'s inline `task_cell_key = _cell_key("dsl-task", task_file.name, head_sha)` (`:1568`).
- `_run_sample_loop` (`cli/harness.py:1036`) is runner-agnostic — it takes `invoke()`/`record()` closures rather than hardcoding what it invokes — so it can drive an unmutated-incumbent arm without modification, which is what `_run_baseline_phase`'s proposed cache-miss path assumes.
- Satisfying AC5 ("a corrupt or partial cache entry causes re-measurement and re-write, not use") requires exception handling broader than what `learning_tests.read_record` (the function `read_baseline` is designed to mirror) currently performs: `_read_frontmatter_yaml` (`learning_tests/__init__.py:106`) degrades to `None` only on a missing/malformed `---` delimiter block, not on a `yaml.safe_load()` failure inside a well-delimited block (unguarded, raises `yaml.YAMLError`) or a missing required key in `from_dict()` (`:77`, unguarded `data["target"]`/`data["date"]`, raises `KeyError`). `read_baseline` needs its own `try/except` around both the parse and the `from_dict`-equivalent construction — see the two-stage pattern at `fsm/persistence.py:load_state()` (`:525`) for a codebase precedent that already does this for a different cache.
- No existing test in this codebase exercises the "corrupt entry causes re-measurement and re-write" half of AC5 — every existing corrupt-cache test (`test_fsm_persistence.py:276`, `test_state.py:260`, `test_ab_writer.py:198`) asserts only that the read returns `None`, never that a subsequent write overwrites the corrupt file. AC5's own test (writing a deliberately corrupted entry and asserting re-measurement) has no template to extend in this codebase; it is new test surface, not an adaptation of an existing one.
- The Program Design's Call Path names only `cmd_dsl` as the integration point. The other four `cmd_*` entry points (`cmd_skill:1217`, `cmd_cmd:1282`, `cmd_mcp:1340`, `cmd_prompt:1433`) share an identical shape — compute `cell_key`, resolve `n = _effective_samples(...)`, then branch to `_run_sample_loop` (n>1) or a single invoke+`_evaluate_and_report`+record (n==1) — and are not addressed by the current Call Path. `cmd_dsl` itself differs from all four: it refuses `--samples > 1` outright (`:1497-1504`, "the dsl runner already resamples across tasks") and has no per-task n-sample loop today — each task runs exactly once via `_run_prompt_action` (`:1613`). Whether the baseline phase applies uniformly to all five entry points or is scoped to `cmd_dsl` alone is not settled by the Design section's prose, which speaks generally of "an `ll-harness` run" without naming which entry points that covers.

## Impact

- **Priority**: P2 — the remaining leg of verdict integrity after ENH-3415 and ENH-3421; without it, "this change helped" remains a claim against a remembered number.
- **Effort**: Medium — a new baseline phase in the harness run path, a disk cache with a defined shape and degradation rule, and tests for both directions of the cache contract.
- **Risk**: Low-medium — additive path; the existing verdict surface is unchanged when no baseline is requested.
- **Breaking Change**: No.

## Status

**Open** | Created: 2026-09-10 | Priority: P2


## Session Log
- `/ll:refine-issue` - 2026-09-10T20:32:27 - `16155f03-6c19-41ff-86d3-335dcd9e206f.jsonl`
- `/ll:format-issue` - 2026-09-10T20:19:51 - `001a54e1-1d47-4c04-9575-71e91821717e.jsonl`
