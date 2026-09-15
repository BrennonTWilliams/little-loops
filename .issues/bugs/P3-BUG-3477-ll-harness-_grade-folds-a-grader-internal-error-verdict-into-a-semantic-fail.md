---
id: BUG-3477
type: BUG
title: ll-harness _grade() folds a grader-internal error verdict into a semantic fail
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-14'
captured_at: '2026-09-14T21:36:04Z'
---

# BUG-3477: ll-harness _grade() folds a grader-internal error verdict into a semantic fail

## Summary

`_grade()` in `scripts/little_loops/cli/harness.py` folds an internal grader error (`EvaluationResult(verdict="error", ...)`) into the same `passed = False` outcome as a legitimate semantic `"no"`. A judge that crashed, timed out, or returned unparseable JSON is reported as the subject failing the criteria.

## Context

Surfaced during `/ll:refine-issue` research for ENH-3463 (deterministic grader tests). Split out because it changes grading behavior, which ENH-3463's Impact section explicitly excludes. See ENH-3463.

## Current Behavior

`_grade()` (`harness.py:1293`) handles the semantic verdict as:

```python
if is_abstention_verdict(eval_result.verdict):
    abstained = True
elif eval_result.verdict != "yes":
    passed = False
```

`is_abstention_verdict()` (`fsm/verdicts.py:25`) recognizes only `cannot_judge`. So `verdict="error"` — produced for example by the `BlockingJsonError` catch at `fsm/evaluators.py:~1123` — falls through to `passed = False` and is indistinguishable from a semantic `"no"` in `HarnessEvalOutcome.passed`.

## Expected Behavior

A grader-internal error is neither a pass nor a fail of the subject. `_grade()` should report it distinctly (a third outcome alongside pass/abstain, or an explicit `grader_error` flag on `HarnessEvalOutcome`) so n-sample tallies and `harness_events` do not count judge failures as subject failures. Precedence stays fail > abstain > pass; error should not silently become fail.

## Steps to Reproduce

1. In `scripts/tests/test_cli_harness.py::TestGradeEvidenceChannels`, patch `little_loops.cli.harness.evaluate_llm_structured` to return `EvaluationResult(verdict="error", details={"error": "BlockingJsonError"})`. <!-- ll-evidence-ok: hypothetical repro construct, not a verbatim quote of existing test code -->
2. Call `_grade()` with `args.semantic` set and `args.exit_code` unset against a synthetic `RunnerResult` with exit code 0.
3. Observe `HarnessEvalOutcome.passed is False` and `abstained is False` — identical to a semantic `"no"`. <!-- ll-evidence-ok: hypothetical repro outcome description, not a verbatim quote of existing test code -->

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-14 — based on codebase analysis:_

Files, callers, conventions, and tests relevant to threading a `grader_error` outcome through `_grade()`, `harness_events`, and `_rc_from_event()`.

_Added by `/ll:refine-issue` — 2026-09-15 — based on codebase analysis:_

Line-number drift corrections (this pass) — `cli/harness.py` has grown ~38-490 lines since the issue's last refine (three commits landed 2026-09-14 after the 21:36-22:50 capture/refine/wire window, plus an uncommitted BUG-3479 `_git_blob()` helper); every citation below supersedes the equivalent one in "Files to Modify" above:
- `_grade()` now at `harness.py:1331` (was `:1293`)
- `HarnessEvalOutcome` now at `harness.py:961` (was `:923`)
- `SampleTally`/`.record()` now at `harness.py:876` (was `:838`)
- `_band_samples()` now at `harness.py:1474` (was `:1436`)
- Five DB-recording call sites now at `harness.py:2741` (`cmd_skill`), `:2907` (`cmd_cmd`), `:3035` (`cmd_mcp`), `:3162` (`cmd_prompt`), `:3438` (`cmd_dsl`) — corrects `:2285, 2427, 2555, 2682, 2951`
- New finding: `cmd_dsl` now has a SECOND `_record_harness_event()` call site at `harness.py:3341` (the malformed-task early-write path), which hardcodes `semantic_verdict=None` and is unaffected by this bug — only the per-task graded write at `:3438` inherits the fold this issue describes
- `_run_sample_loop()` (def now `harness.py:2403`) calls `_grade()` at `:2434` (was `:1969`/`:2000` — two different stale values were previously cited); its `_band_samples()` call is at `:2466` (was `:2032`)
- `_evaluate_and_report()` (def now `harness.py:2504`) calls `_grade()` at `:2526` (was `:2070`/`:2092`)
- `_run_compare_arm()` defined at `harness.py:2323`, reads `res.tally.passed`/`res.tally.graded` at `:2352` (was `:1907-1968`)
- Confirmed unchanged (no drift): `history_reader/harness.py:_rc_from_event()` (`:314-326`), `harness_eval_pass_rate()`/`harness_eval_abstention_rate()` (`:410`/`:451`), `fsm/verdicts.py:is_abstention_verdict()` (`:25`), `fsm/evaluators.py`'s `BlockingJsonError` catch (`:1123`), `fsm/executor.py`'s `is_abstention_verdict` call (`:2371`), `session_store/writers.py` param blocks (`:1116-1117, 1173, 1189-1190, 1242-1243, 1311-1312`), `session_store/schema.py` (`:724-725, 1004-1012, 1130`), `schema_manifest.json` (`:156-158, 1122, 1128`), `test_fsm_verdicts.py:32-34`, `test_session_store_writers.py:2403-2404, 2426-2427`, `test_session_store_schema.py:1636-1637`
- `TestGradeEvidenceChannels` now at `test_cli_harness.py:4381` (was `:3682-3768`/`:3696`); `TestBandSamples` at `:965`; `TestAbstentionVerdict` at `:870`; `TestSampleTallyRecord` at `:1012`
- `EVALUATION_GUIDE.md`'s non-NULL-`semantic_passed` note is now at `:501-502` (was `:449`)
- Confirmed repo-wide (unfiltered grep): no `grader_error` symbol exists anywhere in `scripts/little_loops/` outside this issue file and one cross-reference in ENH-3476 — the fix described here has not been implemented yet

### Files to Modify
- `scripts/little_loops/cli/harness.py` — `_grade()` (`:1293-1416`), `HarnessEvalOutcome` (`:923-941`), `SampleTally`/`.record()` (`:838-865`), `_band_samples()` (`:1436-1451`); five DB-recording call sites at `:2285, 2427, 2555, 2682, 2951`
- `scripts/little_loops/history_reader/harness.py` — `_rc_from_event()` (`:314-326`), which independently mirrors the same banding over persisted rows

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/harness.py` — `_evaluate_and_report()` (n=1 CLI report): independently re-derives an exhaustive `passed`/`abstained` pair (`if not passed: overall = "FAIL" elif abstained: overall = "ABSTAIN" else: overall = "PASS"`) feeding both the `--output json` `"result"` key and the human-readable `status_block()` `"Result"` field. This is the third exhaustive-pair site (alongside `_grade()` and `_band_samples()`) and, left untouched, would render a grader error as `"PASS"` — the exact class of bug this issue exists to fix, resurfacing at the n=1 reporting layer. `TestAbstentionVerdict::test_semantic_abstain_exits_3`/`::test_exit_code_fail_dominates_semantic_abstain` already assert literal `"ABSTAIN"`/`"FAIL"` stdout from this function.
- `scripts/little_loops/cli/harness.py` — `_report_samples()` (n>1 CLI report): the `--output json` `"samples"` dict is hand-enumerated (`requested`, `graded`, `passed`, `failed`, `abstained`, `errored`, `ci_lo`, `ci_hi`) and the human-readable `samples_line` builds `extras` only from `tally.errored`/`tally.abstained` (`if tally.errored: extras.append(...)`); a distinct `grader_error` tally field needs its own key/line here or it is silently absent from both outputs. `test_errored_sample_does_not_stop_loop` asserts literal `"1 errored"` against this function's output.
- `scripts/little_loops/cli/harness.py` — per-sample result label dict inside `_run_sample_loop()`: `label = {2: "ERROR", 3: "ABSTAIN", 0: "PASS"}.get(rc, "FAIL")`, a second, independent rc→label banding (distinct from the aggregate `_band_samples()` verdict) used for each sample's entry in the JSON `results` array; falls through to `"FAIL"` for any unrecognized rc.
- `scripts/little_loops/cli/harness.py:2032` — `_run_sample_loop()` also calls `_band_samples(tally)` directly (a second `_band_samples()` call site beyond `_run_baseline_phase()`'s at `:1837`).
- `scripts/little_loops/cli/harness.py:1907-1968` — `_run_compare_arm()` (ENH-3435) reads `res.tally.passed`/`res.tally.graded` directly (`candidate_rate = res.tally.passed / res.tally.graded if res.tally.graded else None`) to compute `BaselineDelta`; a `SampleTally`-field consumer not previously listed.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/harness.py:2000` — `_run_sample_loop()` calls `_grade()`
- `scripts/little_loops/cli/harness.py:2092` — `_evaluate_and_report()` calls `_grade()`
- `scripts/little_loops/history_reader/harness.py:387` — `baseline_for()` calls `tally.record(_rc_from_event(event))`
- `scripts/little_loops/session_store/writers.py:1116-1171, 1217-1275` — `harness_events` row writer taking `semantic_verdict`/`semantic_passed` params
- `scripts/little_loops/fsm/evaluators.py:1123-1124` — `evaluate_llm_structured()`'s `BlockingJsonError` catch, one of the origins of `verdict="error"`

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/__init__.py:69` — `from little_loops.cli.harness import main_harness`, direct importer of the modified module
- `scripts/little_loops/history_reader/__init__.py:184` — re-export block importing from `history_reader/harness.py`
- `scripts/little_loops/cli/harness.py:1013, 1018` — reporting block calls `harness_eval_pass_rate(...)`/`harness_eval_abstention_rate(...)`
- `scripts/little_loops/history_reader/harness.py:410-450` (`harness_eval_pass_rate()`) and `:451-501` (`harness_eval_abstention_rate()`) — both read `semantic_passed`/`semantic_verdict` off persisted rows; their docstrings encode the current two-bucket assumption (`semantic_passed IS NULL` ⇒ abstained). A `grader_error` bucket changes what "abstained" means to these readers — `harness_eval_pass_rate()`'s denominator (`COUNT(semantic_passed)`) shrinks automatically (matches the already-known `EVALUATION_GUIDE.md:449` note); `harness_eval_abstention_rate()` keys only on `semantic_verdict` (already non-NULL `"error"` today) so its behavior is unaffected.
- `scripts/little_loops/session_store/schema.py:724-725, 1004-1012, 1130` — DDL definition of `harness_events.semantic_verdict TEXT`/`semantic_passed INTEGER` and the `idx_harness_semantic_verdict` index; comments at `:1004-1012` document "`semantic_passed = NULL` for an abstained row" as the existing 2-bucket convention `harness_eval_pass_rate()`/`harness_eval_abstention_rate()` rely on. Columns are unconstrained (no CHECK/enum), so no migration is needed to persist a `grader_error` bucket via `semantic_verdict='error'`/`semantic_passed=NULL`.
- `scripts/little_loops/session_store/schema_manifest.json:156-158, 1122, 1128` — manifest mirror of the same column/index definitions.

### Conventions in Force
- A "third outcome" on this dataclass is added as a plain `bool` field with a `False` default (the `abstained` field's own shape), checked in an `if`/`elif` chain ahead of the `passed = False` fallthrough — not as a new enum type — evidence: `HarnessEvalOutcome.abstained` (`harness.py:929`).
- Precedence between outcome buckets is stated as an explicit "A > B > C" comment wherever a state can satisfy more than one bucket — evidence: `_grade()`'s "fail > abstain > pass" comment (`harness.py:1382-1385`), `_band_samples()`'s docstring precedence list (`:1437-1444`).

### Tests
- `scripts/tests/test_cli_harness.py::TestGradeEvidenceChannels` (`:3682-3768`) — direct `_grade()` calls
- `scripts/tests/test_cli_harness.py::TestBandSamples` (`:958-989`) — direct `_band_samples()` unit tests
- `scripts/tests/test_cli_harness.py::TestSampleTallyRecord` (`:1005`) — `SampleTally.record()` per exit code
- `scripts/tests/test_cli_harness.py::TestAbstentionVerdict` (`:863-911`) — `cmd_cmd()` + `capsys` style
- `scripts/tests/test_fsm_verdicts.py:32-34` — locks `is_abstention_verdict("error") is False`
- `scripts/tests/test_history_reader_harness.py` — covers `history_reader/harness.py` (no direct `_rc_from_event` test found — a gap)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_session_store_schema.py:1636-1637` — asserts `semantic_verdict`/`semantic_passed` column presence in the schema manifest/DDL; unaffected by this fix but confirms no migration is required
- `scripts/tests/test_session_store_writers.py:2403-2404, 2426-2427` — round-trips `semantic_verdict`/`semantic_passed` through the writer; unaffected (writer signature unchanged)
- `scripts/tests/test_history_reader_harness.py:59-268, 378-444` (`TestHarnessEvalPassRate`/`TestBaselineFor`-style cases, incl. ENH-3408 authoritative-counting cases) — exercise `harness_eval_pass_rate()`/`harness_eval_abstention_rate()`/`baseline_for()` against the current NULL-`semantic_passed`-as-abstained convention; extend with a `semantic_verdict="error"` row to confirm it bands distinctly from `cannot_judge`, since both currently fall into the same `_rc_from_event()` branch (`harness.py:310-311`)
- `scripts/tests/test_cli_harness.py:1194` — exercises the `harness_eval_pass_rate()` reporting call site at `harness.py:944`
- New test needed: `_run_baseline_phase()` has no direct unit test today (only indirect coverage via `TestBaselineMeasure`/`TestBaselineDegrade`, `:2922-3603`, none of which mock a `verdict="error"` judge response) — add a `--measure-baseline` case with a mocked grader error across n samples
- New test needed: an end-to-end `cmd_cmd()`/`cmd_skill()` test mirroring `TestAbstentionVerdict` (`:863-911`) driving a mocked `verdict="error"` response through one of the five DB-recording call sites, asserting `semantic_passed` is written as something other than `False` and that `_evaluate_and_report()`'s stdout does not read `"PASS"` or `"FAIL"`
- New test needed: `_report_samples()` `samples_line` assertion for the new bucket, mirroring `test_errored_sample_does_not_stop_loop`'s literal `"1 errored"` check
- Flag for explicit decision, not silent: `TestBandSamples::test_all_errored_is_error`/`::test_two_pass_one_errored_is_inconclusive` currently lock the existing `errored` bucket to rc==2 infra errors only — if `grader_error` is folded into the same `SampleTally.errored` counter rather than a new field, these tests' semantics silently widen to also mean "judge crashed"

### Documentation
- `docs/guides/EVALUATION_GUIDE.md:449` — documents `harness_eval_pass_rate` counting rows with non-NULL `semantic_passed` "on every non-abstained run"; will need a note once a grader-error bucket exists that is also non-abstained but not gradeable

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/EVALUATION_GUIDE.md:78` — exit-code contract line ("`0` PASS, `1` FAIL, `2` internal error or timeout, `3` ABSTAIN or ... INCONCLUSIVE") needs reconciling with where a grader-error bucket lands
- `docs/guides/EVALUATION_GUIDE.md:138-141` — `ll-harness dsl` exit-code table's `2` = "every task was ungraded, or ≥1 task hit a per-task infra error" bucket definition
- `docs/guides/EVALUATION_GUIDE.md:351` — narrative precedence prose duplicating `_band_samples()`'s docstring, needs the same update
- `docs/reference/CLI.md:262-331` — the exit-code table, `--output json` payload shape (`"result"`: PASS/FAIL/ABSTAIN/ERROR/INCONCLUSIVE), and the n-sample `"samples"` object's exact field list; more exposed than the already-known `EVALUATION_GUIDE.md:442-448` note since it's the CLI reference doc users read for the JSON contract
- `docs/reference/EVENT-SCHEMA.md` — the `ll-harness` "JSON output conventions" bullet enumerates the invocation-level verdict set (PASS/FAIL/ABSTAIN/ERROR/INCONCLUSIVE), a third location stating the same set
- `docs/ARCHITECTURE.md` (`v31 harness_events` schema-history row) — checked, no update needed: encoding `grader_error` via existing `semantic_verdict='error'`/`semantic_passed=NULL` implies no new column

## Program Design

### Types

- `HarnessEvalOutcome` (`scripts/little_loops/cli/harness.py:923`, `abstained` field at `:929`): add `grader_error: bool = False` (or widen `abstained` into a tri-state outcome enum; decide at implementation).
- `EvaluationResult` (`scripts/little_loops/fsm/evaluators.py:56`): unchanged; `verdict="error"` is already the signal.

### Signatures

- `_grade(runner_label, result, args, *, expected_grade=None, side_effects=None, duration_ms=None) -> tuple[int, HarnessEvalOutcome]` (`harness.py:1293`): unchanged signature; new branch `elif eval_result.verdict == "error": grader_error = True` placed before the `!= "yes"` fall-through.
- `is_abstention_verdict(verdict: str) -> bool` (`fsm/verdicts.py:25`): unchanged; `"error"` is not an abstention.

### Call Path

`_run_sample_loop()`/`_evaluate_and_report()` (`harness.py:1969`/`:2070`) -> `_grade()` -> `evaluate_llm_structured()` returns `verdict="error"` -> `is_abstention_verdict()` returns False -> new `grader_error` on the outcome -> sample tally and `harness_events` writer report it as a distinct bucket; `history_reader/harness.py:_rc_from_event` (`:314-326`) mirrors the banding and must gain the same bucket.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-14 — based on codebase analysis:_

- `SampleTally` already has a structurally distinct `errored: int = 0` field and `_band_samples()` (`harness.py:838-865`, `:1436-1451`) already has an `ERROR` band — but it is populated only by `rc==2` from the top-of-function infra guard (`_grade()`, `harness.py:1323`: `result.timed_out or result.error is not None`), not by a judge-internal error. A grader error never reaches this existing bucket today.
- `ChannelRecord.passed: bool | None = None` (`harness.py:869-909`) is an existing precedent in this same file for a tri-state "carries no verdict of its own" field on a result dataclass, documented in its own docstring as "internal fold state."
- `is_abstention_verdict()` (`fsm/verdicts.py:25-27`) is a shared predicate also consumed by FSM routing (`fsm/executor.py:2371`) and locked by `test_fsm_verdicts.py:32-34`, which asserts `is_abstention_verdict("error") is False`. Any grader-error handling in `_grade()` must be additive alongside this predicate, not a redefinition of it.
- FSM state routing (`fsm/executor.py:3253-3304`) already treats `verdict == "error"` as a distinct destination (`route.error`/`on_error`), separate from `on_no`. `"error"` is already a first-class, separately-routed verdict elsewhere in this codebase (`evaluate_llm_structured()` returns it from dozens of internal failure sites in `fsm/evaluators.py`); `_grade()` is the one place found that folds it into `passed=False`.
- Every DB-recording call site independently repeats the same expression rather than sharing one: `semantic_passed=None if outcome.abstained else outcome.passed` at `harness.py:2285, 2427, 2555, 2682, 2951` (one per runner subcommand: `cmd_skill`, `cmd_cmd`, `cmd_mcp`, `cmd_prompt`, `cmd_dsl`). Any new outcome dimension (e.g. `grader_error`) must be threaded through all five, not just through `_grade()`.
- `_rc_from_event()` (`history_reader/harness.py:314-326`) is a second, independent re-implementation of the pass/fail/abstain/error banding, operating on persisted `HarnessEvent` rows. Its docstring states it "mirrors the run-time banding," kept in sync by hand-written comment cross-reference (e.g. "ENH-3435") rather than a shared function — the new bucket has to be added here too, by the same convention, not by calling shared code.
- Existing test-style precedents in `test_cli_harness.py`: `TestAbstentionVerdict` (`:864-919`) drives `cmd_cmd()` + `capsys` output assertions; `TestBandSamples` (`:959-1005`) unit-tests `_band_samples()` directly via explicit `SampleTally(...)` construction; `TestGradeEvidenceChannels` (`:3696`) calls `_grade()` directly with a mocked `evaluate_llm_structured`. No existing test in this file constructs `EvaluationResult(verdict="error", ...)`.
- Related: sibling issues ENH-3463 and ENH-3464 reference this same `_grade()` / `evaluate_llm_structured()` / `is_abstention_verdict()` call chain; parent epic EPIC-3475 ("harden ll-harness verdicts") covers this bucket of work.

_Added by `/ll:refine-issue` — 2026-09-15 — based on codebase analysis:_

- A second, independent tri-state precedent in this same file disagrees in shape with `HarnessEvalOutcome.abstained`: `ChannelRecord.passed: bool | None = None` (`harness.py:906-925`), documented in its own docstring as "internal fold state" — `None` when a channel carries no verdict of its own. `abstained` uses a plain `bool = False`; `ChannelRecord.passed` uses `bool | None = None`. Both exist as precedent in this file for a non-strict-pass/fail field, and they disagree on shape — an implementer choosing between them is making a real decision, not following one established convention.
- Verdict banding is independently re-implemented at five sites in this codebase, none calling into another: `_grade()`'s per-sample exit-code chain (`harness.py:1446-1451`), `_band_samples()` (`:1474-1490`), `_evaluate_and_report()`'s n=1 report block (`:2543-2548`), the per-sample rc→label dict inside `_run_sample_loop()` (`label = {2: "ERROR", 3: "ABSTAIN", 0: "PASS"}.get(rc, "FAIL")`, `:2439`), and `_rc_from_event()` (`history_reader/harness.py:314-327`, whose own docstring says it "mirrors the run-time banding" rather than calling it). None of the five currently distinguishes `verdict="error"` from a semantic `"no"` — a fix threading `grader_error` through only `_grade()` would leave the other four sites banding it as an ordinary fail.
- FSM routing (`fsm/executor.py`) already treats `verdict == "error"` as a distinct destination in both its `route:` table form (`route.error`, confirmed `:3276`) and its shorthand form (`on_error`, confirmed `:3289`, plus a third occurrence at `:2346`) — separate from `on_no`/`route.routes["no"]`. Confirms `"error"` is already a first-class, separately-routed verdict value elsewhere in this codebase, not a novel concept this fix introduces.
- Three coexisting test styles for grading/verdict logic in `test_cli_harness.py`, none used exclusively: (1) pure-function unit test on `SampleTally`/`_band_samples()` with no mocking (`TestBandSamples`, `harness.py:965`), (2) direct `_grade()` call with a mocked `evaluate_llm_structured` (`TestGradeEvidenceChannels`, `:4381`), (3) end-to-end `cmd_cmd()` + `capsys` stdout assertions with a mocked judge (`TestAbstentionVerdict`, `:870`). No existing test in this file constructs `EvaluationResult(verdict="error", ...)` — confirmed via file-wide grep, zero matches.
- No `Enum`/`StrEnum` convention found for a grading/verdict tri-state field anywhere in `harness.py` or `fsm/verdicts.py` — every existing tri-state precedent (`HarnessEvalOutcome.abstained`, `ChannelRecord.passed`) uses a plain `bool` or `bool | None` field, not an enum.
- `_run_sample_loop()`/`_evaluate_and_report()` (Call Path above, cited `harness.py:1969`/`:2070`) are now defined at `:2403`/`:2504` respectively.

## Impact

- **Priority**: P3 - judge infrastructure failures are miscounted as subject failures, skewing n-sample pass rates; no incident traced yet.
- **Effort**: Small - one branch in `_grade()`, a field on `HarnessEvalOutcome`, reporting/tally updates, tests in `test_cli_harness.py::TestGradeEvidenceChannels`.
- **Risk**: Medium - changes grading semantics; `history_reader/harness.py:_rc_from_event` mirrors the banding and must be reconciled.
- **Breaking Change**: No

## Verification Notes

Verdict at time of check: **OUTDATED** (corrections below applied in the same
pass, so the issue as it now reads is up to date — this section is a record
of what was wrong and fixed, not an outstanding action item).

Three commits landed after this issue was captured (`b17eabb54`
"widen ll-harness evidence surface beyond stdout", `80d2d38d0` "score
ll-harness runs on a named efficiency vector", `e3739238b` "persist
ll-harness widened evidence to harness_events" — all 2026-09-14, after the
21:36–22:50 capture/refine/wire window) and added ~180 net lines to
`scripts/little_loops/cli/harness.py` ahead of `_grade()`. A currently
uncommitted working-tree change (BUG-3479's `_git_blob()` helper) adds a
further ~27 lines earlier still. Every `harness.py`/`history_reader/harness.py`
line citation in this issue's Integration Map and Program Design sections was
stale as a result; all have been corrected against the current file state
(`_grade()` now at `:1293-1416`, `HarnessEvalOutcome` at `:923-941`,
`SampleTally` at `:838-865`, `_band_samples()` at `:1436-1451`, the five
DB-recording call sites at `:2285, 2427, 2555, 2682, 2951`, `_rc_from_event()`
at `history_reader/harness.py:314-326`, etc.).

The underlying claim is unchanged and confirmed still true: `_grade()`
(`harness.py:1382-1385`, current `elif eval_result.verdict != "yes": passed =
False` branch) still folds a grader-internal `"error"` verdict into
`passed = False` identically to a semantic `"no"` — the fix this issue
describes is still needed, at the corrected locations. Files not touched by
the recent commits (`fsm/evaluators.py`, `fsm/verdicts.py`, `session_store/writers.py`,
`session_store/schema.py`, `schema_manifest.json`, `cli/__init__.py`,
`history_reader/__init__.py`) were checked and their citations are unchanged.

`ll-verify-evidence --json` flagged two spans in `## Steps to Reproduce`
(the `EvaluationResult(verdict="error", ...)` patch instruction and the
`HarnessEvalOutcome.passed is False` expected-observation line) as
unverifiable against `test_cli_harness.py`. Reviewed: both are reproduction
*instructions*/expected outputs, not quotes claimed to already exist verbatim
in that file — the tool's nearest-file attribution heuristic misread
procedural prose as an evidence quote. Not treated as `EVIDENCE_UNVERIFIED`;
the underlying claim was independently confirmed by reading `_grade()`
directly (above).

## Status

**Open** | Created: 2026-09-14 | Priority: P3


## Session Log
- `/ll:refine-issue` - 2026-09-15T17:59:03 - `87cb899f-60d1-4042-81cb-33c78f6d04d3.jsonl`
- `/ll:verify-issues` - 2026-09-15T15:57:34 - `fe401c2e-e475-43b1-b588-44df23082884.jsonl`
- `/ll:wire-issue` - 2026-09-14T22:50:06 - `bac75f45-b587-45bb-bf3c-443b0c5e805a.jsonl`
- `/ll:refine-issue` - 2026-09-14T21:57:11 - `76fd614d-af9c-461c-9480-143acb792f32.jsonl`
- `/ll:format-issue` - 2026-09-14T21:47:59 - `b8b46581-a38f-4aa7-a1ba-71f0319e7405.jsonl`
