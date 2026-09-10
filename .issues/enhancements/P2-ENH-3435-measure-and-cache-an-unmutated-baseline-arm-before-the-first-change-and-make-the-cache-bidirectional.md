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
decision_needed: true
relates_to:
  - ENH-3397
  - ENH-3407
  - ENH-3415
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

`ll-harness` is a one-shot CLI: it runs whatever is on disk and has no proposal phase of its own. The baseline arm is therefore a **separate invocation on the unmutated subject**, made by the loop before it mutates anything, and the candidate arm is a later invocation on the mutated subject that reads the baseline back:

1. `ll-harness <runner> <target> --measure-baseline` runs n repetitions on the subject as it currently exists on disk and records them as the baseline for that subject (keyed on the subject's *content*, not just `head_sha` — see Design).
2. `ll-harness <runner> <target> --compare-baseline` runs n repetitions on the (now mutated) subject, looks up a baseline for the same runner/target under matching conditions and n, and reports a delta with provenance. If no such baseline exists, or it is partial or condition-mismatched, the run **refuses** with an explicit "no measured baseline" state — it never compares against a remembered number.

Verdicts compute deltas only against a measured baseline. The baseline persists in a store that both the loop and post-hoc analysis read and write, so a rollout paid for on either path is reusable by the other. A corrupt or partial entry triggers re-measurement rather than being trusted, and every reported delta states whether its baseline was freshly measured or reused, along with the n and conditions it was measured under.

Ordering ("before the first change") is enforced by refusal, not by the CLI observing proposals: the candidate run cannot report a delta unless a baseline was already recorded for the unmutated content.

## Design

Mechanics borrowed from evolutionary-search harness design, where the baseline arm is treated as mandatory loop structure rather than optional rigor:

- **Baseline phase before the first proposal — as a separate invocation.** Per task, before the loop's first proposal or mutation is applied, the loop invokes `ll-harness ... --measure-baseline`, which executes n runs of the subject as it stands — same task, same effective n as the candidate arm will use, same conditions (model, host, timeout, criteria) — and records the result. The candidate arm later invokes `--compare-baseline`. The n is whatever the candidate arm will use, so the two arms are directly comparable; nothing about the sample machinery is redefined here. The CLI never checks out or stashes an incumbent; it only measures what is on disk and refuses a delta when no baseline exists for the unmutated content.
- **Key on content, not only on `head_sha`.** Meta-loops (`harness-optimize.yaml`) mutate skill files in the working tree and commit only on acceptance, so the incumbent and the candidate share `head_sha`. `record_attempt`'s docstring (`session_store/writers.py:1297`) states that `dirty` is deliberately excluded from `_cell_key`. A baseline keyed on `_cell_key(runner, target, head_sha)` alone would therefore let the candidate run read *its own arm* as the baseline and then overwrite it. The baseline key must include `target_content_hash` (already computed for `skill`, `prompt`, and `dsl-task` — `_hash_file`/`_hash_bytes`, `cli/harness.py:114-129`) alongside `head_sha`. For `cmd` and `mcp`, which have no content hash today, `--compare-baseline` refuses unless the caller names the baseline explicitly (`--baseline-of <attempt-id>`), because the CLI has no way to tell the two arms apart.
- **Stored bidirectionally.** The baseline persists in a store with a defined result shape. The loop writes it; any post-hoc analysis reads it — and writes the same shape back, so a checkpoint evaluation performed after the fact feeds the next run's baseline lookup. Either direction can consume the other's already-paid rollouts. This is the difference between paying for a baseline once and paying for it per analysis. **Which store** is the one open decision on this issue — see "Decision: baseline store" under Program Design; the recommended option is `harness_events` itself, not a second file.
- **Degrade, never lie.** A corrupt or partial entry is discarded and re-measured. "Partial" concretely means fewer than n authoritative (non-superseded) repetitions for the baseline cell, or a conditions mismatch (model, semantic prompt, timeout, host). The failure mode being guarded against is a silently wrong baseline — a plausible-looking cached number that no longer describes the system it claims to. Resilience is explicitly unit-testable and must be tested.
- **The delta is a pass-rate difference with both intervals, never a banded verdict.** `delta = candidate.passed/candidate.graded − baseline.passed/baseline.graded`, reported alongside both arms' Wilson intervals (`wilson_ci`, already used by `_report_samples`). At the default n=3 the delta's granularity is one third and the intervals will usually overlap; the report shows that rather than hiding it behind a PASS/FAIL band. `--compare-baseline` refuses at effective n=1 (a delta between two booleans is not a measurement). The existing exit-code contract (0/1/2/3) is unchanged; the delta is additive report content.
- **Provenance on the delta.** A verdict that reports a delta names its baseline: task set, n, conditions, whether the baseline was freshly measured or reused, and the attempt ids (or cell) it was derived from.
- **Loud writes when baseline is on.** Harness event writes are best-effort today (`contextlib.suppress` in `_record_harness_event`). With `--measure-baseline` set, a swallowed write would mean the baseline silently never landed, so the write failure must propagate and exit non-zero — the precedent is the `--retry-of` path, which already does this.

On the run model (ENH-3397): baseline runs are ordinary repetitions recorded against their own named cells (`task × repetition × subject`), with the unmutated incumbent as the subject. Nothing about attempt classification changes; the baseline arm simply is another subject the existing machinery scores — the content hash is what makes it a *distinct* subject from the mutated candidate.

### Design Review Findings

_Added by manual review — 2026-09-10 — after verifying the refine/wire findings against `cli/harness.py`, `session_store/writers.py`, `harness-optimize.yaml`, and `.gitignore`:_

- The prior Design text described the baseline phase as if it ran *inside* one `cmd_*` invocation ("before the agent's first proposal"). Nothing in `cli/harness.py` observes proposals, and no mechanism for running an unmutated arm from a mutated tree was specified. Rewritten above as a two-invocation contract; AC1/AC2 rewritten to match.
- The refine finding "`head_sha` is what already distinguishes an unmutated-incumbent run from a post-change candidate run" is only true for *committed* changes. The primary consumer (`harness-optimize.yaml`'s propose → benchmark → commit-or-revert cycle) benchmarks *uncommitted* mutations. Content-hash keying added above.
- The storage-location fork flagged by `/ll:wire-issue` is settled by precedent if a file cache is kept: `.ll/evidence-verdict-cache.json` is a gitignored, per-file cache under `.ll/` (`.gitignore:109`) whose reader (`load_verdict_cache`) discards the whole cache when a parameter it was built under changes — the same invalidate-on-conditions-mismatch behaviour this issue needs. Neither `.loops/` (FSM-run scoped, `${context.run_dir}` is per-instance) nor the git-tracked `.ll/learning-tests/` is the right model.
- `harness_events` already stores every field the baseline needs per repetition (`head_sha`, `target_content_hash`, `dirty`, `semantic_model`, `semantic_prompt`, `semantic_passed`, `superseded_by`, `cell_key`, `repetition`), and `history_reader.harness.authoritative_attempts(cell_key)` already reads it post-hoc. A JSON side-cache would duplicate that data and create a second source of truth. Raised as the one decision below rather than silently adopted.
- `BaselineResult.outcome: HarnessEvalOutcome` in the original Program Design typed the baseline as one sample's outcome; a baseline over n runs is a `SampleTally` (`cli/harness.py:697`). Fixed below.
- `timeout` and the host CLI are not recorded on `harness_events` today; both are conditions the baseline must match on. Added to the conditions fingerprint below.

## Scope Boundaries

- **In scope**: `--measure-baseline` / `--compare-baseline` on the four non-DSL entry points (`cmd_skill`, `cmd_prompt`, `cmd_cmd`, `cmd_mcp`), the baseline store and its result shape, content-hash keying, the bidirectional read/write contract between loop-time and post-hoc analysis, corrupt/partial-entry degradation, the delta definition, and delta provenance reporting.
- **Out of scope — `cmd_dsl`.** The DSL runner has no per-task n (it refuses `--samples > 1`, `cli/harness.py:1497-1504`) and already writes its own aggregate + per-task cell rows. A DSL baseline arm is a task-set-breadth question, not a repetition-depth one, and needs its own definition. `cmd_dsl` rejects both new flags with an explicit "not supported on the dsl runner" message (same shape as its `--samples` refusal). A follow-up issue defines the DSL baseline arm.
- **Out of scope**: n-run redundancy and its `--samples` semantics (ENH-3415, done); the frozen external reference guard (ENH-3421, done); the repetition/infra-retry/continuation attempt model (ENH-3397, done); widening the evidence surface beyond the current channels; scoring runs on an efficiency vector; any checkout/stash/worktree mechanism for running an incumbent from a mutated tree (the loop sequences the two invocations). Those are separate concerns that compose with this one.

## Acceptance Criteria

1. `ll-harness <skill|prompt|cmd|mcp> <target> --measure-baseline` runs the effective n repetitions on the subject as it exists on disk and records them as the baseline for `(runner, target, head_sha, target_content_hash, conditions)`. A write failure on this path exits non-zero instead of being suppressed.
2. `ll-harness ... --compare-baseline` refuses with an explicit "no measured baseline" state (exit 1, message names the runner/target/content hash it looked for) when no baseline exists for the unmutated content, when the stored baseline has fewer than n authoritative repetitions, or when its conditions (model, semantic prompt, timeout, host) differ from the current invocation. It never compares against `_read_target_history()` or any other remembered number.
3. The baseline key includes `target_content_hash`: a test mutates a skill file in a dirty tree without committing, runs `--compare-baseline`, and asserts that the candidate's own repetitions are *not* read back as the baseline. For `cmd`/`mcp` (no content hash), `--compare-baseline` without `--baseline-of <attempt-id>` refuses.
4. Baseline results persist under a defined result shape, keyed so subsequent invocations on the same target, content, and conditions reuse them without re-running the subject.
5. The store is bidirectional: one test shows a loop-produced baseline consumed by post-hoc analysis (`history_reader`) without re-running the subject, and one shows a post-hoc-produced result consumed as a run's baseline by `--compare-baseline`.
6. A corrupt or partial entry causes re-measurement and re-write, not use: one test writes a deliberately corrupted entry, one writes an entry with fewer than n repetitions, and one writes an entry under mismatched conditions; each asserts the baseline is re-measured and the store afterwards holds the fresh result.
7. A reported delta is `candidate pass rate − baseline pass rate` with both arms' Wilson intervals, and names its baseline's provenance: fresh or reused, the n, the conditions, and the attempt ids/cell it came from. Both the text and `--output json` renderings carry these fields; the exit-code contract is unchanged.
8. `--compare-baseline` refuses at effective n=1, and `cmd_dsl` refuses both flags, each with an explicit message.
9. Existing single-shot and n-sample verdict behavior is unchanged when neither flag is given; the test suite passes.

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-10 — based on codebase analysis:_

**Files to Modify**
- `scripts/little_loops/cli/harness.py` — the two flags in `_build_harness_parser` (`:466`), `_baseline_key`, `read_baseline`/`write_baseline`, `_run_baseline_phase`, and the delta/provenance extension of `_report_samples` (`:950`) land here alongside the existing `_cell_key` (`:144`), `_effective_samples` (`:912`), `_run_sample_loop` (`:1036`); `_record_harness_event` (`:206`) gains a `loud: bool` (or equivalent) so the measure path propagates write failures
- `scripts/little_loops/session_store/writers.py` (`record_attempt`, `:1282`) and `scripts/little_loops/session_store/schema.py` — **if Option A of the store decision is taken**: a schema migration adding `timeout_s`/`host_cli` condition columns (and, if needed, an `arm` marker) to `harness_events`, plus the post-hoc write path
- `scripts/little_loops/history_reader/harness.py` — **Option A**: a `baseline_for(cell_key, *, n, conditions)` reader built on `authoritative_attempts` (`:186`); **Option B**: unchanged, but the post-hoc analysis side of AC5 needs a `write_baseline` call site somewhere in this module or a sibling
- `.gitignore` — **Option B only**: a `.ll/harness-baselines/` line, following `.ll/evidence-verdict-cache.json` (`:109`)

_Not a file to modify_: `scripts/little_loops/learning_tests/__init__.py` was previously listed here; it is only the *model* for a read/write pair (and, per Conventions in Force below, a model whose corrupt-content handling is narrower than AC6 requires). Nothing in this issue calls into it.

**Dependent Files (Callers/Importers)**
- `scripts/little_loops/cli/__init__.py:69` — imports `cli.harness`
- `scripts/tests/test_cli_harness.py:14` — imports `cli.harness`; contains ~30 `cmd_dsl` call sites (`TestCmdDsl`, `TestCmdDslRetryOf`, `TestHarnessEventPersistence` classes) and the `TestSampleLoopIntegration::test_dsl_refuses_samples_gt_1` case that would need updating if the baseline phase changes `cmd_dsl`'s `--samples` handling
- `scripts/little_loops/history_reader/harness.py` — reads `harness_events` post-hoc (`authoritative_attempts`, `harness_eval_pass_rate`); a distinct SQLite-backed read surface from the disk-file `BaselineResult` cache this issue proposes — no existing code here reads or writes a `BaselineResult`-shaped artifact

_Wiring pass added by `/ll:wire-issue`:_
- **Flag-name collision risk (not a file to modify, an implementation constraint)**: `--baseline` is already a flag on a *different* CLI in this same package — `ll-loop run <loop> --baseline` / `ll-loop promote-baseline <loop>` (an FSM A/B score-reversion comparator spanning `scripts/little_loops/cli/loop/run.py`, `cli/loop/runner.py`, `cli/loop/lifecycle.py`, `fsm/executor.py`, `cli/loop/summary.py`, `cli/history.py` — 51 files repo-wide reference `--baseline`/`--no-baseline`, none in `cli/harness.py` itself today). Reusing the bare `--baseline` spelling for AC1/AC2's flags on `ll-harness` would put two CLIs in the same package defining `--baseline` with unrelated contracts. Pick a distinct spelling for the new `ll-harness` flag (e.g. `--measure-baseline`/`--no-baseline-measure`). [Agent 2 finding]
- `scripts/little_loops/file_utils.py:16,35` (`atomic_write`, `atomic_write_json`) — candidate helper for `write_baseline` to delegate to instead of hand-rolling its own tempfile+`os.replace`, which is the convention gap the issue's own "Conventions in Force" section already flags (rate_limit_circuit/persistence.py reimplement it manually; this shared, already-28-files-used helper exists but neither calls it). Not itself a file requiring modification — an import target for the new `write_baseline`. [Agent 1/3 finding]

**Tests**
- `scripts/tests/test_cli_harness.py` — existing `ll-harness` coverage; no baseline/cache tests present yet (0 hits for `BaselineResult`/`read_baseline`/`write_baseline`/`_run_baseline_phase` outside the issue file itself)
- `scripts/tests/test_learning_tests.py::TestReadRecord` (lines 183-229) — the test class for the cited model; covers only the missing-file case (`test_returns_none_when_missing`) and successful round-trips. It contains no test that writes malformed YAML content and asserts degrade behavior — that gap is analyzed further under Program Design's findings below.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_file_utils.py::TestAtomicWriteJson` — pattern model for `write_baseline` if it reuses `file_utils.atomic_write`/`atomic_write_json` (`:16`/`:35`): `test_overwrites_existing_file`, `test_no_tmp_orphan_on_replace_failure`, `test_preserves_existing_file_on_replace_failure` cover the atomic-replace contract `write_baseline` would inherit for free by delegating to it rather than hand-rolling its own tempfile+`os.replace`. [Agent 3 finding]
- `scripts/tests/test_verify_evidence.py::test_corrupt_cache_is_ignored_not_fatal` (`:755`) — closest existing precedent for "corrupt disk-cache degrades gracefully rather than raising," matching `read_baseline`'s "returns `None` on missing or corrupt entry" contract. Like every other corrupt-cache test found repo-wide, it asserts only the read-returns-None half — no test anywhere in the codebase (confirmed by an unfiltered repo-wide search) exercises "corrupt entry → read → then write → assert the corrupt file was overwritten," so AC6's rewrite-after-corrupt assertion has no existing template to adapt; it is new test surface. [Agent 3 finding]
- `scripts/tests/test_ab_writer.py::TestABJsonIO` — the closest existing same-path round-trip test (`write_ab_json`/`read_ab_json`), confirmed by full read to write and read the *same* `tmpdir` variable within one test — no cross-path (write-from-path-A, read-from-path-B) test exists anywhere in this file or elsewhere in the repo. AC5's bidirectional-store tests (loop-writes/analysis-reads and vice versa) have no existing bidirectional-cache test to model structurally, only same-path round-trip tests to borrow assertion style from. [Agent 3 finding]

**Documentation**
- `docs/guides/EVALUATION_GUIDE.md` — `ll-harness` conceptual/usage docs (`_grade()` reference at `:96`, `DEFAULT_STOCHASTIC_SAMPLES` at `:343`, `harness_events`/`.ll/history.db` at `:373`)
- `docs/reference/API.md` — `little_loops.learning_tests` module reference (`:7354` `## little_loops.learning_tests` section, `write_record`/`check_learning_test` examples at `:7432`/`:7482`)

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md` — the `ll-harness` CLI reference; load-bearing, not just descriptive. `:236` documents `--samples` in the shared evaluator-flags table (the new `--measure-baseline`/`--compare-baseline` flags per AC1/AC2 needs a row here); `:245` restates `cmd_dsl`'s `--samples > 1` refusal (must stay in sync with whatever DSL's baseline scope ends up being, see Program Design addendum below); `:259-296` enumerates the `--output json` payload field table — AC7's provenance fields (fresh/reused, n, conditions) are new additive JSON keys that belong here, following the existing `prepatch_evidence`/`history_*` "Present when" column convention. `scripts/tests/test_wiring_cli_registry.py:71` asserts `("docs/reference/CLI.md", "ll-harness", "FEAT-1689")` is present in a coupling table — this file is under an automated presence check today (coarse string-presence, not flag-content), so a missing `--baseline` row would not itself be caught by that test. [Agent 2 finding]
- `docs/reference/EVENT-SCHEMA.md:1795` — documents that an n>1 invocation writes one `harness_events` row per sample (`attempt_kind='repetition'`). Per the Program Design's "baseline runs are ordinary repetitions recorded against their own named cells" line, baseline-arm runs land in this same table under this same convention — this doc line's scope (currently framed as "candidate-arm samples") needs to explicitly cover baseline-arm samples too. [Agent 2 finding]

**Conventions in Force**
- Disk caches in this codebase degrade to `None` on read failure via an explicit `try/except` around the parse call, not an unguarded call — e.g. `rate_limit_circuit._read_unlocked()` catches `json.JSONDecodeError` and logs a `logger.warning` naming the file (`scripts/little_loops/fsm/rate_limit_circuit.py:104`); `fsm/persistence.py:load_state()` uses two separate `try/except` blocks — one for `json.JSONDecodeError` on the raw parse, a second `except KeyError` around `from_dict()` construction for schema-level corruption (`scripts/little_loops/fsm/persistence.py:525`). The cited model, `learning_tests.read_record`/`_read_frontmatter_yaml` (`scripts/little_loops/learning_tests/__init__.py:106,129`), degrades to `None` only when the `---\n...\n---` frontmatter delimiter regex fails to match (file absent or no frontmatter block) — a `yaml.safe_load()` call on content that has valid delimiters but malformed YAML inside them is unguarded and would raise `yaml.YAMLError` uncaught, and `LearnTestRecord.from_dict()` (`:77`) does unguarded `data["target"]`/`data["date"]` key access that would raise `KeyError` on a partial entry. Two disagreeing conventions exist for the corrupt-content case; the mirrored model does not itself satisfy the broader "degrade on corrupt OR partial" contract this issue's AC6 requires.
- Cache writes in this codebase use a tempfile-then-`os.replace` atomic-write idiom — `rate_limit_circuit._write_atomic()` (`:121`) and `fsm/persistence.py:save_state()` (`:502`) each reimplement it manually via `tempfile.mkstemp(dir=parent)` + `os.replace`, while a shared, already-used-in-28-files helper (`scripts/little_loops/file_utils.py:atomic_write()` at `:16`, `atomic_write_json()` at `:35`, which round-trip-validates via a defensive `json.loads` before replacing) exists but is not called by either. The cited model, `learning_tests.write_record` (`:114`), instead does a plain unguarded `Path.write_text()` with no atomicity guard at all.
- No dataclass in this codebase serializes via `dataclasses_json`/`pydantic` — every example found (`LearnTestRecord`/`Assertion`, `ABResults`, `ProcessingState`, `LoopState`) hand-writes its own serialization. Two distinct shapes coexist: classmethod-based `to_dict`/`from_dict` on the dataclass itself (`LearnTestRecord.to_dict`/`.from_dict`, `learning_tests/__init__.py:65,77` — the shape the issue's Program Design's `BaselineResult` implicitly follows) versus standalone module-level serialize/deserialize functions with the dataclass itself carrying neither (`ab_results_to_dict()` plus inlined `.get(key, default)` deserialization in `read_ab_json()`, `scripts/little_loops/ab_writer.py:210,245`).
- No existing example in the codebase is a *fully* bidirectional cache (two independent call paths that each both read and write the same artifact shape). The closest is `ab_writer.write_ab_json()`/`read_ab_json()` (`scripts/little_loops/ab_writer.py:233,245`) — the executor writes `ab.json` (`scripts/little_loops/fsm/executor.py:4341-4346`), and two separate consumer sites read it (`cli/loop/summary.py:52,219-220`) — but nothing currently writes `ab.json` from the read/summary side, so it is write-once/read-many, not bidirectional. No second example of a genuinely bidirectional shared-cache file was found in a repo-wide search.
- The corrupt-cache tests that do exist in this codebase (`test_fsm_persistence.py::test_load_state_returns_none_for_invalid_json:276`, `test_state.py::test_load_invalid_json:260`, `test_ab_writer.py::test_read_invalid_json:198`) share one shape: write a literal malformed-content string directly to the target file path, call the read function, and assert `is None` (two of the three also assert a `logger.error`/`logger.warning` call). None of them then calls the writer and asserts the corrupt file gets overwritten — every existing test covers only the read-degrades-to-None half of AC6's "re-measurement and re-write" requirement, not the write-back half.

## Program Design

### Decision: baseline store

`decision_needed: true` is set for this one choice. Both options satisfy every AC; they differ in how many sources of truth exist for a harness measurement.

- **Option A (recommended) — `harness_events` is the store.** A baseline *is* the set of authoritative (non-superseded) `harness_events` rows for the incumbent's cell. `--measure-baseline` writes ordinary repetition rows (loudly); `--compare-baseline` reads them back via a new `history_reader.harness.baseline_for(...)`. Post-hoc analysis reads with the same function and writes with `record_attempt`, so AC5's bidirectionality is the existing table's read/write surface, not new plumbing. AC6's "corrupt or partial" becomes "fewer than n authoritative rows, or a conditions mismatch" — no JSON-corruption story to test, but the partial-row and mismatch cases are. Requires a schema migration adding `timeout_s` and `host_cli` columns (the other conditions — `semantic_model`, `semantic_prompt`, `target_content_hash`, `head_sha`, `dirty` — are already on the row). Cost: a migration; `history.db` is the only place the baseline lives, so an unavailable DB refuses the baseline flags outright (it already degrades `--retry-of` the same way).
- **Option B — a JSON file cache under `.ll/harness-baselines/<key>.json`.** `read_baseline`/`write_baseline` on a `BaselineResult` file, following `.ll/evidence-verdict-cache.json` (gitignored per-file cache with invalidate-on-mismatch) and delegating writes to `file_utils.atomic_write_json` (`file_utils.py:35`). Independent of `history.db` availability, and the corruption story is literally testable with a malformed file. Cost: every baseline measurement is now stored twice (the repetition rows still land in `harness_events`), the two can drift, and the post-hoc "write the same shape back" path has to be built and kept in sync with the row shape by hand.

The recommendation is A because ENH-3397/3407/3408 already made `harness_events` the cell-keyed record of every repetition, and a delta computed from the same rows the run wrote is the strongest form of "measured, not remembered."

### Types

- `BaselineKey`: `runner: str`, `target: str`, `head_sha: str | None`, `target_content_hash: str | None` — `_baseline_key(...)` serialises it the way `_cell_key` does (JSON array, `separators=(",", ":")`), so it is greppable in sqlite and stable across processes. For `cmd`/`mcp`, `target_content_hash` is `None` and `--compare-baseline` requires `--baseline-of`.
- `BaselineConditions`: `model: str | None`, `semantic_prompt: str | None`, `timeout_s: int`, `host_cli: str`, `n: int` — the fingerprint a reused baseline must match exactly.
- `BaselineResult`: `key: BaselineKey`, `conditions: BaselineConditions`, `tally: SampleTally` (`cli/harness.py:697` — passed/graded/failed/abstained/errored + Wilson bounds), `attempt_ids: list[int]`, `measured_at: str`. `source: Literal["measured", "reused"]` is **read-side provenance set by the reader, never persisted** — a stored entry always describes a measurement.
- `BaselineDelta`: `candidate: SampleTally`, `baseline: BaselineResult`, `delta: float` (candidate pass rate − baseline pass rate), `source: Literal["measured", "reused"]` — what `_report_samples` renders.

### Signatures

- `_baseline_key(runner: str, target: str, head_sha: str | None, target_content_hash: str | None) -> str` — sibling of `_cell_key` (`cli/harness.py:144`)
- `read_baseline(key: str, conditions: BaselineConditions) -> BaselineResult | None` — returns `None` on missing, partial (fewer than `conditions.n` authoritative rows), condition-mismatched, or corrupt entry (degrade-to-remeasure). Option A: thin wrapper over `history_reader.harness.baseline_for`. Option B: file read with the two-stage `try/except` from `fsm/persistence.py:load_state()` (`:525`) around parse *and* construction — the `learning_tests.read_record` model is insufficient here (see Conventions in Force).
- `write_baseline(result: BaselineResult) -> None` — Option A: no-op beyond the loud `record_attempt` rows already written by the sample loop (the rows *are* the baseline). Option B: `file_utils.atomic_write_json`.
- `_run_baseline_phase(runner_label, args, n, invoke, record) -> BaselineResult` — new function in `cli/harness.py`, sibling to `_run_sample_loop` (`:1036`); drives n runs through `_run_sample_loop`'s closures with `loud=True` recording and returns the tally as a `BaselineResult`. Only reached with `--measure-baseline`.
- `_compare_baseline(args, key, conditions, candidate: SampleTally) -> BaselineDelta | str` — returns the delta or a refusal message (no baseline / partial / mismatch / n=1 / cmd-mcp-without-`--baseline-of`), mirroring `_retry_refusal`'s message-or-None shape (`:156`).
- `_report_samples(..., delta: BaselineDelta | None = None)` — additive keyword; when set, appends the delta line(s) to the text report and a `baseline` object to the JSON payload.

### Call Path

`cmd_skill` (`cli/harness.py:1217`) / `cmd_prompt` (`:1433`) — the stochastic runners that already loop — are the primary integration points; `cmd_cmd` (`:1282`) / `cmd_mcp` (`:1340`) get the same insertion with the `--baseline-of` requirement:

`cmd_*` -> flag refusals (`--measure-baseline` + `--compare-baseline` together; either with `--retry-of`; `--compare-baseline` at n=1) -> `cell_key`/`_baseline_key` -> `_effective_samples` -> **measure**: `_run_baseline_phase` -> loud `_record_harness_event` × n -> `write_baseline` -> `_report_samples`; **compare**: `_run_sample_loop` (candidate, existing path) -> `read_baseline` -> `_compare_baseline` -> `_report_samples(delta=...)`.

`cmd_dsl` (`:1484`) refuses both flags — see Scope Boundaries. The prior Call Path named `cmd_dsl` as the sole integration point; it is the one entry point with no `n` of the shape this design needs, so that has been inverted.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-10 — based on codebase analysis:_

- `_cell_key(runner, target, head_sha)` (`scripts/little_loops/cli/harness.py:144`) already encodes exactly the triple the Program Design's `write_baseline`/`read_baseline` key on: per ENH-3397's run model (`cell = (target, task, subject)`, `subject = runner_label + head_sha`), `head_sha` is what already distinguishes an unmutated-incumbent run from a post-change candidate run of the same `runner`/`target`. No new key scheme needs inventing — confirmed call sites are `cmd_skill:1222`, `cmd_cmd:1286`, and `cmd_dsl`'s inline `task_cell_key = _cell_key("dsl-task", task_file.name, head_sha)` (`:1568`).
- `_run_sample_loop` (`cli/harness.py:1036`) is runner-agnostic — it takes `invoke()`/`record()` closures rather than hardcoding what it invokes — so it can drive an unmutated-incumbent arm without modification, which is what `_run_baseline_phase`'s proposed cache-miss path assumes.
- Satisfying AC6 ("a corrupt or partial cache entry causes re-measurement and re-write, not use") requires exception handling broader than what `learning_tests.read_record` (the function `read_baseline` is designed to mirror) currently performs: `_read_frontmatter_yaml` (`learning_tests/__init__.py:106`) degrades to `None` only on a missing/malformed `---` delimiter block, not on a `yaml.safe_load()` failure inside a well-delimited block (unguarded, raises `yaml.YAMLError`) or a missing required key in `from_dict()` (`:77`, unguarded `data["target"]`/`data["date"]`, raises `KeyError`). `read_baseline` needs its own `try/except` around both the parse and the `from_dict`-equivalent construction — see the two-stage pattern at `fsm/persistence.py:load_state()` (`:525`) for a codebase precedent that already does this for a different cache.
- No existing test in this codebase exercises the "corrupt entry causes re-measurement and re-write" half of AC6 — every existing corrupt-cache test (`test_fsm_persistence.py:276`, `test_state.py:260`, `test_ab_writer.py:198`) asserts only that the read returns `None`, never that a subsequent write overwrites the corrupt file. AC6's own test (writing a deliberately corrupted entry and asserting re-measurement) has no template to extend in this codebase; it is new test surface, not an adaptation of an existing one.
- The Program Design's Call Path names only `cmd_dsl` as the integration point. The other four `cmd_*` entry points (`cmd_skill:1217`, `cmd_cmd:1282`, `cmd_mcp:1340`, `cmd_prompt:1433`) share an identical shape — compute `cell_key`, resolve `n = _effective_samples(...)`, then branch to `_run_sample_loop` (n>1) or a single invoke+`_evaluate_and_report`+record (n==1) — and are not addressed by the current Call Path. `cmd_dsl` itself differs from all four: it refuses `--samples > 1` outright (`:1497-1504`, "the dsl runner already resamples across tasks") and has no per-task n-sample loop today — each task runs exactly once via `_run_prompt_action` (`:1613`). Whether the baseline phase applies uniformly to all five entry points or is scoped to `cmd_dsl` alone is not settled by the Design section's prose, which speaks generally of "an `ll-harness` run" without naming which entry points that covers.

_Wiring pass added by `/ll:wire-issue`:_
- **`cmd_dsl`'s baseline-phase gap, confirmed at the code level.** `cmd_dsl` never calls `_effective_samples()` or `_run_sample_loop()` — its `--samples > 1` refusal (`:1499-1501`) and single-run-per-task-file loop via `_run_prompt_action` (`:1613`) mean there is no `n` value of the shape `_run_baseline_phase(args, runner, n)` expects. `_run_baseline_phase` needs either a DSL-specific `n` derivation (task-file count, not a sample-loop repetition count — a different axis: task-set breadth vs. repetition depth) or `cmd_dsl` is explicitly excluded from the uniform baseline-phase insertion until a follow-up defines what a DSL baseline arm means. This is a design decision this issue must settle before implementation, not an open question to carry into code. [Agent 2 finding]
- **Cache location convention fork, unresolved.** The Program Design's `read_baseline`/`write_baseline` mirror `learning_tests.read_record`/`write_record`, whose default base dir (`_DEFAULT_BASE_DIR = Path(".ll") / "learning-tests"`, `learning_tests/__init__.py:23`) is **git-tracked** — no `.gitignore` rule covers it, and `.ll/learning-tests/raw/mcp-tasks-start-path.txt` exists as a committed file today. But the issue frames `BaselineResult` as a *cache* with degrade-on-corruption/re-measure semantics, matching the **gitignored** `.loops/`-style convention instead (`rate_limit_circuit`'s `.loops/tmp/rate-limit-circuit.json`, `fsm/persistence.py`'s `.loops/.running/*.state.json` — both under `.gitignore` rules). These are two different storage contracts (curated/committed vs. ephemeral/regenerable) and the Program Design currently points at the tracked one while describing the ephemeral one. Must be resolved explicitly before choosing `read_baseline`/`write_baseline`'s default `base_dir`. No existing `config-schema.json` entry configures a path for either model to fall back on if this needs to be user-configurable — the closest schema precedent is `automation.rate_limits.circuit_breaker_path` (`config-schema.json:571-573`). [Agent 2 finding]

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- ~~Decide `cmd_dsl`'s baseline-phase scope~~ **Resolved (review 2026-09-10)**: `cmd_dsl` is excluded and refuses both flags; follow-up issue defines a DSL baseline arm. See Scope Boundaries.
- ~~Decide the cache's storage contract~~ **Resolved as far as location goes**: if a file cache exists it lives at `.ll/harness-baselines/` with a `.gitignore` line, following `.ll/evidence-verdict-cache.json`. *Whether* a file cache exists at all is the "Decision: baseline store" block under Program Design (Option A needs no file).
- ~~Pick a flag name~~ **Resolved**: `--measure-baseline` and `--compare-baseline` (plus `--baseline-of <attempt-id>` for `cmd`/`mcp`). No bare `--baseline` on `ll-harness`.
- Add the content-hash keying test (AC3): mutate a skill file in a dirty tree without committing, run the compare path, assert the candidate's own rows are not read back as the baseline. No existing test exercises dirty-tree/same-`head_sha` disambiguation.
- Option A only: schema migration adding `timeout_s` and `host_cli` to `harness_events` (`session_store/schema.py`), with the usual v-bump test in `scripts/tests/test_session_store*.py`; `record_attempt` gains the two kwargs; `_record_harness_event` passes them.
- Update `docs/reference/CLI.md` — add both flags to the evaluator-flags table (`:236`), note the `cmd_dsl` refusal beside the `--samples` one (`:245`), and add the `baseline` provenance/delta object to the `--output json` payload field table (`:259-296`).
- Update `docs/reference/EVENT-SCHEMA.md:1795` — extend the "one `harness_events` row per sample" line to explicitly cover baseline-arm repetitions, and (Option A) document the new condition columns.
- Update `docs/guides/EVALUATION_GUIDE.md` — a short "measuring a delta" section showing the two-invocation sequence a loop runs, and the note that a baseline doubles first-run spend.
- Write the AC6 corrupt/partial/mismatch-then-rewrite tests — no existing test covers the rewrite half; use `test_verify_evidence.py::test_corrupt_cache_is_ignored_not_fatal` for the read-degrades half only.
- Write the AC5 bidirectional tests from scratch — no existing test (including `test_ab_writer.py`, the closest analog) covers a cross-path write/read round trip to adapt.
- Option B only: delegate `write_baseline` to `file_utils.atomic_write_json` (`file_utils.py:35`) rather than hand-rolling tempfile+`os.replace`.
- Make the measure path's `_record_harness_event` loud: a test patches `record_attempt` to raise and asserts `--measure-baseline` exits non-zero with the error on stderr, while the flagless path still suppresses.

## Impact

- **Priority**: P2 — the remaining leg of verdict integrity after ENH-3415 and ENH-3421; without it, "this change helped" remains a claim against a remembered number.
- **Effort**: Medium — two flags on four entry points, a content-hash key, a baseline store (Option A: a two-column migration plus a reader; Option B: a file cache), the delta/provenance report extension, and tests for keying, both directions of the store contract, and the three degrade cases.
- **Risk**: Low-medium — additive path; the existing verdict surface and exit-code contract are unchanged when neither flag is given.
- **Cost**: measuring a baseline runs the subject n more times, so the first run of a loop that opts in roughly doubles its API spend; every later run on the same content and conditions reuses it. Both flags are opt-in.
- **Breaking Change**: No.

## Status

**Open** | Created: 2026-09-10 | Priority: P2


## Session Log
- manual design review - 2026-09-10T21:30:00 - folded review findings (two-invocation contract, content-hash key, store decision, cmd_dsl exclusion, delta definition)
- `/ll:wire-issue` - 2026-09-10T20:50:09 - `2557344f-8422-414b-93b6-7ef3ec9dd3f8.jsonl`
- `/ll:refine-issue` - 2026-09-10T20:32:27 - `16155f03-6c19-41ff-86d3-335dcd9e206f.jsonl`
- `/ll:format-issue` - 2026-09-10T20:19:51 - `001a54e1-1d47-4c04-9575-71e91821717e.jsonl`
