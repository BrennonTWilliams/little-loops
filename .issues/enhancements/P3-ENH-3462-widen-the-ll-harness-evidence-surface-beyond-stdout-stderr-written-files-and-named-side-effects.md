---
id: 3462
title: "Widen the ll-harness evidence surface beyond stdout \u2014 stderr, written\
  \ files, and named side effects"
type: ENH
priority: P3
status: open
discovered_date: '2026-09-13'
labels:
- evals
- reliability
verify_verdict: NON_VALID
size: Very Large
---

## Summary

`ll-harness` forms its verdict over a single channel. `_evaluate_and_report` (`scripts/little_loops/cli/harness.py:659`) checks `result.exit_code` and hands `result.stdout` alone to the semantic evaluator. The runners actually being harnessed — skills and commands whose real output is an edited file, a captured issue, a git change — do their work somewhere the harness never looks. The verdict is being formed over the narration while the work product goes unexamined, which means a runner that describes success convincingly and does nothing at all passes.

Widen the evidence surface the evaluator sees: stderr as a channel distinct from stdout, the content of files the run was declared to write, and named side effects the criterion can assert against (a file exists, a path changed, a git status is clean). The criterion language needs a way to name which channels it is asserting over, so that a claim about a written artifact is checkable rather than inferred from prose about it.

## Design

Two design points are load-bearing:

- **An unexamined channel must be distinguishable from an examined-and-empty one.** Silently treating a channel the harness never read as absent evidence reproduces the current failure with more machinery. The verdict's evidence record should carry which channels were read and which were not.
- **Side effects must be declared, not scraped.** Declaring the expected side effects is what makes the check meaningful; a harness that scrapes for arbitrary file changes will drown in incidental ones. A run declares the artifacts it is expected to produce; the criterion asserts against the declaration.

The precedent this follows is a production tournament harness over a stochastic subject whose authors found that the failures that mattered were *absent from the text logs* and only recoverable from other channels (rendered screens, recording files). Its analysis stage synthesizes three distinct channels — rendered evidence, structured artifacts, and post-hoc diagnosis prose — while selection uses one number. Selection needs one number; diagnosis needs the richer channels. `ll-harness` currently reads neither the richer channels nor anything but stdout.

Distinct from adjacent verdict work: scope-of-claim envelope work bounds what a verdict *asserts*; triage-vs-verdict score separation changes how scores are used; failure-evidence ranking orders evidence for classification. All three operate on evidence the harness already has. None enlarges the set of channels it reads.

Composes with the n-run redundancy requirement (ENH-3415, shipped): redundancy is only worth its cost if each run yields more than a boolean, and each of the n runs should yield the widened evidence, not only the first.

## Why it matters

The instrument that certifies runner correctness is scoring the narration rather than the work. Every downstream consumer of a harness verdict — candidate selection, regression detection, improvement loops — inherits a verdict that is blind to the actual work product, and an improvement loop cannot diagnose what its harness never captured.

## Current Behavior

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-13 — based on codebase analysis:_

- `_grade()` (`scripts/little_loops/cli/harness.py:916-982`) reads only the exit code and stdout fields on its `result` argument; on `--semantic`, it calls `evaluate_llm_structured(output=result.stdout, ...)` (:956-958) — the stderr and tool-trace fields never reach it.
- The stderr field is captured on every run but only ever used for display: `_evaluate_and_report()` (`scripts/little_loops/cli/harness.py:1591`) embeds it in the JSON payload (`:1660`) and error report (`:1707`); `_run_sample_loop()` (`scripts/little_loops/cli/harness.py:1533`) attaches it to a sample's dict only `if args.verbose or label != "PASS"` (`:1578`). `record_harness_event()` (`session_store/writers.py:1210-1241`) has no stderr parameter and the `harness_events` schema (`session_store/schema.py:718-736`) has no stderr column — stderr is discarded once the process exits, never persisted or graded.
- The tool-trace field (`scripts/little_loops/runner_spec.py:113`, populated only in the `trace_mode` branch of `_run_skill()` at `scripts/little_loops/runner_spec.py:221`/`:229`) has zero readers anywhere in `scripts/little_loops/cli/harness.py` (repo-wide search, no hits) — captured but never surfaced or consulted.
- `--trace-mode`/`--require-order`/`--require-artifact`/`--forbid-path` (`_add_trace_flags()`, `scripts/little_loops/cli/harness.py:639-688`, attached only to `skill_p`/`prompt_p`) have exactly one consumer repo-wide: `_conditions_fp()` (`harness.py:1231/1234/1235`), which folds them into a baseline-matching fingerprint hash. None of the four `ActionSpec(...)` construction sites (`harness.py:1747-1753`, `:1882-1887`, `:2001-2007`, `:2085-2091`) forward `trace_mode`/`require_artifact`/`forbid_path` into `spec.args`, so the `trace_mode` branch of `_run_skill()` (`scripts/little_loops/runner_spec.py:196-230`) is unreachable via any `ll-harness` command path today — the flags perturb the fingerprint and otherwise do nothing.
- `_git_dirty()` (`harness.py:90-119`) is called post-run and recorded via `_record_harness_event(...dirty=...)`, but is read back only as descriptive provenance (`BaselineResult.dirty_rows`, `history_reader/harness.py:295,390`) — never consulted inside `_grade()`, so no criterion can assert on git cleanliness today.

## Expected Behavior

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-13 — based on codebase analysis:_

- A criterion can name which channel(s) it asserts over (stdout, stderr, a declared artifact path, a named side effect), and `_grade()` routes the named channel's content into the judge/assertion the same way it already routes `result.stdout` — instead of the single implicit channel today.
- The verdict's evidence record carries an explicit per-channel status (examined vs. not examined) distinct from the channel's content, so an unread channel and a read-and-empty channel produce different, inspectable records rather than the same absence.
- A declared side effect (file exists, path changed, git status clean) is assertable as a criterion outcome with a recorded pass/fail, rather than being descriptive-only metadata the way `_git_dirty()`'s result is today.

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-13 — based on codebase analysis:_

**Files to Modify**
- `scripts/little_loops/cli/harness.py` — `_grade()` (:916-982) is the sole verdict-forming function; it reads only `result.exit_code` and `result.stdout` (`evaluate_llm_structured(output=result.stdout, ...)`, :956-958). `_evaluate_and_report()` (:1591-1690) and `_report()` (:1692) already thread `result.stderr` into the JSON/report payload as a **display-only** field — it never reaches `_grade()`.
- `scripts/little_loops/runner_spec.py` — `RunnerResult` (:100-113) already carries `stderr: str` (populated by both `_run_skill()` and `_run_cmd()`) and `tool_trace: list[dict] | None` (populated only in trace-mode runs, FEAT-2878) — both channels are captured today but neither is graded.
- `scripts/little_loops/fsm/evaluators.py` — `evaluate_llm_structured()` (:1067) has exactly one evidence parameter (`output: str`); widening the channel set means either adding parameters or pre-composing a multi-channel string before this call.

**Dependent Files (Callers/Importers)**
- `_grade()` is called from `_evaluate_and_report()` (single-run path, :1591) and from `_run_sample_loop()` (:1533, ENH-3415 n-run loop) — a channel widening in `_grade()`'s signature touches both call sites.
- `cmd_skill` (:1714), `cmd_cmd` (:1852), `cmd_mcp` (:1958), `cmd_prompt`/`_run_prompt_action` (:2078/:2098), `cmd_dsl` (:2197) — the five runner command handlers that construct the `RunnerResult` (via `run_action()`) and hand it to `_grade()`/`_evaluate_and_report()`.
- `--require-artifact`/`--forbid-path`/`--trace-mode` flags (`_add_trace_flags()`, :639-672) are parsed only onto `skill_p` (:702) today, not `cmd_p`/`mcp_p`/`prompt_p`/`dsl_p`; their only consumer is `_conditions_fp()` (:1215-1243), a baseline-fingerprint identity use, not a runtime assertion. A declared-side-effect mechanism reusing this flag set touches all five parsers and needs a new consumer beyond `_conditions_fp()`.
- `harness_events` schema (`session_store/schema.py:718`) has no `stderr`/artifact/channel-provenance columns — persistence, not just in-memory grading, is a dependent surface if the widened evidence is meant to survive past the single report.

**Conventions in Force**
- This codebase already holds a convention for "evidence must be source-traced, and an unread/missing input produces an explicit gap marker rather than a silent omission" — `EvidenceBundle`/`EvidenceEntry`/`GapEntry` (`scripts/little_loops/cli/loop/evidence.py:56-119`, FEAT-3182). Every entry traces to one of a closed `_EVIDENTIARY_SOURCES` set; LLM-sourced facts are segregated into a separately labeled, non-evidentiary section; any absent/incomplete input produces an explicit `GapEntry`. This is the closest existing analog to this issue's "examined-and-empty vs. unexamined" requirement, though it lives in `cli/loop/evidence.py`, not `cli/harness.py`.
- This codebase already holds a convention for "a run declares one expected artifact, and downstream code checks existence against the declaration rather than scraping" — `ArtifactOutput` (`fsm/schema.py:1330-1373`) / `promote_run_artifact()` (`fsm/persistence.py:741-791`): a missing declared artifact is logged and treated as a distinguishable no-op, never silently promoted, never a hard crash.
- This codebase already holds a convention for "an evaluator's input channel can be redirected away from raw action stdout by explicit declaration" — `EvaluateConfig.source` (`fsm/schema.py:72`) / `fsm/executor.py:3129-3137` — but this exists only in the FSM loop-execution layer, not as an `ll-harness` CLI flag; `_grade()` has no equivalent.
- This codebase already holds a convention for "declaring named file paths and reading their content as judge evidence, with a per-file unreadable-file path that produces an explicit error verdict rather than a crash" — `evaluate_contract()` (`fsm/evaluators.py:1349-1438`).
- Two **disagreeing** conventions exist for git-status-as-evidence: `_compute_worktree_digest()` (`fsm/executor.py:1757-1776`) hashes `git status --porcelain` + `git diff HEAD` into one opaque sha256 (detects *that* something changed); `issue_lifecycle.py`'s pre-run-dirty snapshot/diff (:490-548) produces an explicit changed-path set (detects *what* changed). Neither calls into the other; `git_operations.py::porcelain_paths()` (:552) is the one shared parsing utility between them, used only by the latter.
- The closest existing precedent inside `harness.py` itself for "add one more read-only evidence source into the report without touching `_grade()`'s verdict" is `_read_prepatch_evidence()` (:807-818, ENH-2998) and `_read_target_history()` (:828-891, ENH-3223) — both are additive, absent-is-not-an-error, and merged into `_evaluate_and_report()`'s printed report but never fold into the pass/fail computation.

**Tests**
- `scripts/tests/test_cli_harness.py` — existing `_grade()`/`_evaluate_and_report()` coverage; `FakeRunner`/`_make_completed(returncode, stdout, stderr)`/`_make_namespace()` fixture helpers (:1-80) already parametrize stdout/stderr independently, so widened-channel tests can reuse them directly.
- `scripts/tests/test_feat3182_evidence_bundle.py` — the test-class taxonomy for the closest existing "source-traced evidence, explicit gaps" convention (`TestEvidenceEntryTracing`, `TestReproducibility`, `TestAllowlist`, `TestGapTaxonomy`) — a reusable shape for testing any new evidence-record structure this issue introduces.
- `scripts/tests/test_runner_spec.py` — covers `RunnerResult` including `stderr`/`tool_trace` capture.

**Documentation**
- `docs/reference/CLI.md` (`### ll-harness`, :212; `--semantic` examples :330-357; exit-code docs :321) — describes today's single-channel grading contract.
- `docs/reference/API.md` (`cli/harness.py` references :2806, :6157-6171, :10726-10761; `EvaluationResult` :6139; `evaluate_llm_structured` :6228).
- `docs/guides/EVALUATION_GUIDE.md` (:54-96) and `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` — describe `ll-harness`'s role and the stochastic-subject rationale this issue's Design section cites.

_Added by `/ll:refine-issue` — 2026-09-13 — based on codebase analysis:_

- CLI flag threading: `harness.py`'s `_build_harness_parser()` (:495) has two shared nested-closure flag helpers, not one — `_add_evaluator_flags()` (:521, applied uniformly to all five subparsers: skill_p/cmd_p/mcp_p/prompt_p/dsl_p) and `_add_trace_flags()` (:639, applied only to skill_p/prompt_p). Neither is a module-level/exported helper; a repo-wide search found no `_add_*_flags` pattern outside this one parser builder — a new evidence-declaration flag has this in-file closure shape to extend, not a cross-file convention.
- Multi-source judge-prompt composition: this codebase already holds a convention for composing multiple evidence sources into one LLM-judge prompt string — wrap each source in its own open/close tag named for its semantic role, joined by blank lines, each truncated to the same 4000-char budget before insertion: `evaluate_llm_structured()`'s `<action_output>` tag (`fsm/evaluators.py:1102`), `evaluate_contract()`'s attributed `<producer path="...">`/`<consumer path="...">` tags (`:1461-1469`), and the blind comparator's `<output_a>`/`<output_b>` tags (`:1209-1213`). No single fixed tag vocabulary is shared across call sites — each names its own tags — but the wrap-and-concatenate-with-blank-line shape and the 4000-char truncation budget are held in common by all three.
- The two disagreeing git-status-as-evidence conventions already noted are tested at different precision levels: the opaque-digest convention (`_compute_worktree_digest()`) is tested only for inequality/type (`before != after`, `isinstance(str)`, `test_feat3182_executor_git_facts.py`), while the explicit-changed-path-set convention (`issue_lifecycle.py`'s `_completion_preflight()`) is tested by literal frozenset equality (`preflight.run_window == frozenset({...})`, `test_issue_lifecycle.py:428+`) — a criterion asserting "git status clean"/"path changed" inherits whichever precision level it is built on.

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/fsm/executor.py` — `FSMExecutor._evaluate()` (:3076-3169) has the identical single-channel gap as `_grade()`: the default-evaluation branch (:3108-3113) calls `evaluate_llm_structured(action_result.output, ...)` and the explicit-evaluation branch (:3152-3158) calls `evaluate(config=state.evaluate, output=eval_input, ...)` — both ignore `action_result.stderr` (populated at :3059/:3070 on every `ActionResult`). A signature widening on `evaluate_llm_structured`/`evaluate` touches both call sites. [confirmed by direct read, :3100-3160]
- `scripts/little_loops/fsm/evaluators.py` — the `evaluate()` dispatcher itself (:1827-1833, signature `(config, output, exit_code, context, model=None)`) has no `stderr` parameter; its `llm_structured` branch (:2039-2053, confirmed via `ll-code callers-of`) forwards only `output=output`. Widening `evaluate_llm_structured` requires widening `evaluate()`'s own signature too, since every other evaluator type (`mcp_result`, `contract`, `comparator`, `classify`, :2055-2087) is dispatched through the same function.
- `scripts/little_loops/cli/queue.py` — `_run_loop_action` (~:380-433) constructs `RunnerResult` **directly** (`RunnerResult(stdout=stdout, stderr=stderr, exit_code=returncode, error=error)`, :433), bypassing `runner_spec.run_action()` entirely (by design — `RunnerType.LOOP` is excluded from `run_action()`'s dispatch table, per comments at `runner_spec.py:129-134`). Any new evidence field populated inside `run_action()` will NOT automatically appear on this second, independent `RunnerResult` producer — it needs the matching change made here too.
- `scripts/little_loops/cli/harness.py` — `_conditions_fp()` (:1215-1243, ENH-3435 baseline-fingerprint payload) enumerates every condition-relevant CLI flag (`exit_code`, `forbid_path`, `require_artifact`, `trace_mode`, etc., payload dict :1229-1241). Any new CLI flag this issue introduces to declare which channels/artifacts to examine must be added to this payload, or two runs graded under different evidence-declaration configs will collide on the same `conditions_fp` and incorrectly share a baseline (`baseline_for()` in `history_reader/harness.py:315-392` matches purely on `conditions_fp`).
- `scripts/little_loops/session_store/schema.py` — `SCHEMA_VERSION = 50` (:25) and the `_MIGRATIONS` list (v50 entry :1390-1415) are the established pattern for a new `harness_events` evidence column: a new list entry (`ALTER TABLE harness_events ADD COLUMN <name> <TYPE>;`, nullable, no DEFAULT, fix-forward only).
- `scripts/little_loops/session_store/writers.py` — `_insert_harness_event()` (:1109-1207, column list :1156-1164, parameter tuple :1165-1195) and `record_harness_event()` (:1210-1299, thin wrapper) both need new evidence kwargs threaded through if a column is added.
- `scripts/little_loops/cli/harness.py` — `_record_harness_event()` (:214-261) and its `record_attempt()` call (:264) is the harness CLI's own wrapper; needs new kwargs added and threaded from `_grade()`'s new evidence data.
- `scripts/little_loops/history_reader/harness.py` — read-side consumer of the same schema: `HarnessEvent` dataclass (:53-98, needs new trailing-default fields per its own v49/v50-precedent docstring at :61-64/:92-94) and `_HARNESS_EVENT_COLUMNS` (:101-108, the single SQL column-list string reused by every reader — `recent_harness_events`, `harness_event_by_id`, `authoritative_attempt(s)`, `baseline_for`). Also imports `SampleTally` from `cli.harness` at :367 (bidirectional coupling with `cli/harness.py`, not previously noted).

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/ARCHITECTURE.md` — schema-migration table (`| v31 |` … `| v49 |` rows, e.g. :670/:682) documents every `harness_events` migration; a new evidence-channel migration needs a new row following the v49/v50 entries' style.
- `docs/guides/HISTORY_SESSION_GUIDE.md` — an independent, separate copy of the same schema-migration table (:57-99, e.g. `| v31 | ENH-2739 | harness_events table... |` at :91). This table already reads "Current schema version: 45" at :57 while code is at `SCHEMA_VERSION = 50` — already stale by several migrations; a new v51 row is one more it needs.
- `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` § "Contract Gates (`check_contract`)" — comparison table at :189-194 documents the current limitation in prose (`| Reads files | No — evaluates action stdout | Yes — reads both files directly |`, :192); this specific row/anchor should be updated once the gap it describes is closed.
- `docs/reference/EVENT-SCHEMA.md` § "CLI exit-code conventions" (:1795) — prose paragraph explicitly stating *"Only `RunnerResult.timed_out` is persisted to `harness_events`; `RunnerResult.error` has no column."* — becomes stale the moment new evidence fields are persisted.

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_fsm_executor.py` — extensive `llm_structured` evaluator coverage (~40 `patch("little_loops.fsm.executor.evaluate_llm_structured", ...)` sites; dedicated methods `test_llm_structured_evaluator_routes_on_verdict` :3354, `test_llm_structured_evaluator_failure_verdict` :3402, `test_llm_structured_evaluator_blocked_verdict` :3442). `test_llm_structured_evaluator_routes_on_verdict` (:3354) patches one level lower (`little_loops.fsm.evaluators.subprocess.run`) and already sets `.stderr = ""` on the fake CLI result without asserting on `evaluate_llm_structured`'s call signature — the pattern to model widened-channel evaluator tests after.
- `scripts/tests/test_cli_queue_run.py` — ~20 sites construct `RunnerResult(stdout=..., stderr=..., exit_code=..., ...)` via keyword args only to stub `run_action`/`Popen` results for `ll-queue run`; additive-safe for new fields as long as they default and stay keyword-only.
- `scripts/tests/test_fsm_evaluators.py` `TestLLMStructuredEvaluator` (976-1395) — `test_empty_stdout_includes_stderr` (:1218) is today's *only* place stderr feeds `evaluate_llm_structured`, but only as an empty-stdout fallback error string, not as judged evidence content — a gap to close. `test_output_truncation` (:1318) asserts `len(prompt_content) < 5000` as an upper bound on a 4000-char truncated `output`; needs a stderr/artifact-bearing counterpart if those channels share the same truncation budget (won't break, since it's an upper bound).
- `scripts/tests/test_fsm_persistence.py` `TestPromoteRunArtifact` (1670-2129+) and `scripts/tests/test_fsm_schema.py` `TestFSMLoopArtifactOutput` (4116-4198) — concrete "declared X, checked against declaration" test pattern (e.g. `test_no_op_when_declared_source_missing`, `test_fsm_persistence.py:1721`) to model a new "declared artifact, read and graded" test after.
- `scripts/tests/test_feat3182_evidence_bundle.py` `TestGapTaxonomy` (:204+) — concrete pattern (`test_missing_run_dir_produces_explicit_gap`, :205-211) of one `any(g.category == "<taxonomy-string>" for g in bundle.gaps)` assertion per gap kind plus `any(e.source == "<channel>" for e in bundle.evidentiary)` for provenance — the model for testing a new "examined vs never-examined" taxonomy, since no such convention exists anywhere else in the repo today (confirmed by repo-wide search).
- `scripts/tests/test_cli_e2e.py` `TestLlHarnessE2E::test_cmd_echo_hello_passes` (:472-488) — the only subprocess-level e2e test for `ll-harness` in the repo; exercises `cmd` + `--exit-code` only, no `--semantic`, no stderr assertion, no file-artifact declaration. A new e2e test exercising the widened evidence surface (real subprocess writing a file / producing stderr / leaving git status dirty, graded end-to-end) is the concrete gap here.
- `scripts/little_loops/cli/harness.py:660,667` — `--require-artifact`/`--forbid-path` (FEAT-2878) are parsed and folded into `_conditions_fp()`'s fingerprint but have **zero enforcement code path anywhere in the tree** and **zero test coverage** (confirmed by repo-wide, unfiltered search). Flagged as an adjacent, currently-inert declared-artifact surface with overlapping naming — new work should not collide with or silently duplicate this flag's eventual implementation.

## Program Design

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-13 — based on codebase analysis:_

**Types**
- `RunnerResult` (`scripts/little_loops/runner_spec.py:100-113`) already has the fields this issue needs at the source: `stdout: str`, `stderr: str`, `exit_code: int`, `tool_trace: list[dict[str, Any]] | None`. No new capture-side type is required — the gap is entirely on the grading/assertion side, not the capture side.
- No existing type represents "which channels were read vs. left unread" anywhere in this codebase (confirmed by repo-wide search for `scope-of-claim`, `evidence surface`, `examined channel`, and equivalents — zero hits outside this issue file). `EvidenceEntry`/`GapEntry` (`cli/loop/evidence.py:56-119`) is the nearest existing analog but is scoped to `cli/loop/evidence.py`'s bundle, not to `ll-harness`.
- No existing type represents a "declared side effect" assertion checked against a criterion (as opposed to an artifact promoted at loop-terminal time). `ArtifactOutput` (`fsm/schema.py:1330-1373`) is a single-file promotion declaration, not a per-run multi-artifact assertion set graded by a criterion.

**Signatures**
- `_grade()` (`harness.py:916`) — currently reads only `result.exit_code` (:937) and `result.stdout` (:956-958, via `evaluate_llm_structured(output=result.stdout, ...)`). `result.stderr` and `result.tool_trace` are both already available on the same `result` argument and are unread by this function.
- `evaluate_llm_structured(output: str, prompt=None, schema=None, min_confidence=0.5, uncertain_suffix=False, model=DEFAULT_LLM_MODEL, max_tokens=256, timeout=1800) -> EvaluationResult` (`fsm/evaluators.py:1067`) — exactly one evidence-carrying parameter (`output`); a widened-channel call site needs either a new parameter shape or a composed multi-channel string built by the caller before this call.
- `_add_trace_flags()` (`harness.py:639`) defines `--trace-mode`, `--require-order`, `--require-artifact` (repeatable), `--forbid-path` (repeatable) but attaches them only to `skill_p` (:702); their sole consumer is `_conditions_fp()` (:1215-1243) — a fingerprint/identity function, not an assertion function.

**Call Path**
`cmd_skill`/`cmd_cmd`/`cmd_mcp`/`cmd_prompt`/`cmd_dsl` -> `run_action()` (`runner_spec.py`) -> `RunnerResult(stdout, stderr, exit_code, tool_trace)` -> `_grade()` (`harness.py:916`, reads `exit_code` + `stdout` only) -> `evaluate_llm_structured(output=result.stdout, ...)` (`fsm/evaluators.py:1067`) -> `EvaluationResult` -> `_evaluate_and_report()`/`_run_sample_loop()` -> printed report / `harness_events` persistence (`session_store/schema.py:718`, no stderr/artifact/channel-provenance columns).

**Decision Rules**
N/A — no new decision logic proposed with concrete, resolvable inputs. The issue names the *shape* of a new decision surface (a criterion-language way to name which channel it asserts over; a declared-artifact set a criterion checks against) but does not fix the literal syntax, keyword set, or threshold — those are open implementation choices the issue's own Design section leaves to be resolved, not facts research can pin down from the current codebase.

_Added by `/ll:refine-issue` — 2026-09-13 — based on codebase analysis:_

- Multi-channel composition precedent for `evaluate_llm_structured()`'s single `output: str` parameter: this codebase already wraps each evidence source in its own open/close tag named for its semantic role, joined by blank lines, each truncated to the same 4000-char budget, before composing one prompt string — `evaluate_llm_structured()`'s own `<action_output>` tag (`fsm/evaluators.py:1102`), `evaluate_contract()`'s attributed `<producer path="...">`/`<consumer path="...">` tags (`:1461-1469`), and the blind comparator's `<output_a>`/`<output_b>` tags (`:1209-1213`). A widened call composing stdout+stderr+artifact evidence into one string before calling `evaluate_llm_structured()` has this tag-wrap-and-concatenate shape as precedent; no single fixed tag vocabulary is shared across call sites today, so a new tag name is a free choice, not a violation of an existing constant.

## Implementation Steps

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-13 — based on codebase analysis:_

1. `_grade()` (`harness.py:916`) forms its verdict from more than `result.exit_code` + `result.stdout` — `result.stderr` and, where captured, `result.tool_trace` become inputs to the decision, not only to the printed report. `test_cli_harness.py`'s existing stdout/stderr fixture helpers (`_make_completed`, :1-80) already parametrize both independently.
2. The verdict's evidence record distinguishes an unexamined channel from an examined-and-empty one. The closest existing analog is `EvidenceEntry`/`GapEntry`'s source-traced, explicit-gap convention (`cli/loop/evidence.py:56-119`); whether to reuse or diverge from it is left open (see Program Design → Decision Rules).
3. A run can declare the artifacts/side effects it expects to produce, and a criterion asserts against that declaration rather than scraping arbitrary changes. `ArtifactOutput`/`promote_run_artifact()` (`fsm/schema.py:1330-1373`, `fsm/persistence.py:741-791`) is the closest existing "declared, not scraped" precedent in this codebase, scoped to a single promoted file rather than a criterion-checkable set.
4. The criterion language gains a way to name which channel(s) it is asserting over. `--require-artifact`/`--forbid-path`/`--trace-mode` (`harness.py:639-672`) are parsed today only on `skill_p` and consumed only by `_conditions_fp()`'s fingerprint (:1215-1243) — not wired to the other four command parsers or to any runtime assertion.
5. `python -m pytest scripts/tests/test_cli_harness.py scripts/tests/test_runner_spec.py -v` passes.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Update `scripts/little_loops/fsm/executor.py` — `FSMExecutor._evaluate()`'s two call sites (:3108-3113, :3152-3158) to pass the widened evidence (stderr, declared artifacts) once `evaluate_llm_structured()`/`evaluate()` accept it; `action_result.stderr` is already captured (:3059/:3070) but unused here.
- Update `scripts/little_loops/fsm/evaluators.py` — the `evaluate()` dispatcher (:1827-1833) signature, since every non-`llm_structured` evaluator branch (`mcp_result`, `contract`, `comparator`, `classify`) is routed through it and must tolerate the new parameter.
- Update `scripts/little_loops/cli/queue.py` — `_run_loop_action`'s direct `RunnerResult` construction (:433) to populate any new evidence field, since it bypasses `runner_spec.run_action()` and won't inherit the change automatically.
- Update `scripts/little_loops/cli/harness.py` — `_conditions_fp()`'s payload dict (:1229-1241) to include any new evidence-declaration CLI flag, so runs under different declarations don't collide on the same baseline fingerprint.
- If evidence gains `harness_events` persistence: bump `SCHEMA_VERSION` in `scripts/little_loops/session_store/schema.py` (:25, currently 50) and add a `_MIGRATIONS` entry; thread new columns through `session_store/writers.py`'s `_insert_harness_event()`/`record_harness_event()`, `cli/harness.py`'s `_record_harness_event()`, and `history_reader/harness.py`'s `HarnessEvent` dataclass + `_HARNESS_EVENT_COLUMNS`.
- Update `docs/ARCHITECTURE.md` and `docs/guides/HISTORY_SESSION_GUIDE.md` schema-migration tables with the new migration row (note: the latter is already stale at "v45" vs. code's v50 — fix opportunistically, not required by this issue's scope).
- Update `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md`'s Contract Gates comparison table (:189-194) once the "evaluates action stdout only" row it documents is no longer accurate.
- Update `docs/reference/EVENT-SCHEMA.md`'s "Only `RunnerResult.timed_out` is persisted" sentence (:1795) once more fields are persisted.
- Add an e2e test to `scripts/tests/test_cli_e2e.py`'s `TestLlHarnessE2E` exercising the widened surface via real subprocess (stderr, a declared artifact, dirty git status), since today's sole e2e test only covers `cmd` + `--exit-code`.
- Add taxonomy-style gap tests to a new test class modeled on `test_feat3182_evidence_bundle.py`'s `TestGapTaxonomy` (:204+) for the "examined vs never-examined" channel distinction — no such convention exists elsewhere to reuse directly.

## Tests

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-13 — based on codebase analysis:_

- `scripts/tests/test_cli_harness.py` — existing `_grade()`/`_evaluate_and_report()` coverage; `FakeRunner`, `_make_completed(returncode, stdout, stderr)`, and `_make_namespace()` (:1-80) already parametrize stdout/stderr independently and are directly reusable for widened-channel test cases.
- `scripts/tests/test_feat3182_evidence_bundle.py` — the test-class taxonomy for the closest existing "source-traced evidence, explicit gaps" convention (`TestEvidenceEntryTracing`, `TestReproducibility`, `TestAllowlist`, `TestGapTaxonomy`) is a reusable shape for testing any new evidence-record structure this issue introduces.
- `scripts/tests/test_runner_spec.py` — covers `RunnerResult` construction, including `stderr`/`tool_trace` capture, that any widened-grading test would build on.

_Added by `/ll:refine-issue` — 2026-09-13 — based on codebase analysis:_

- `EvidenceEntry`/`GapEntry` coverage (`test_feat3182_evidence_bundle.py`) asserts by membership-over-generator (`assert any(g.category == "..." for g in bundle.gaps)`), never by fixed list index — one test class per taxonomy axis, one method per gap category.
- `ArtifactOutput`/`promote_run_artifact()` coverage (`test_fsm_persistence.py::TestPromoteRunArtifact`, :1670) is a full round-trip: real `tmp_path` file writes, a real `FSMLoop`, return-value assertions (`None` for no-op, `Path.read_text()` re-verified for promote) — each no-op guard condition gets its own dedicated test (`test_no_op_when_declared_source_missing`, :1721).
- `evaluate_contract()` coverage (`test_fsm_evaluators.py::TestContractEvaluator`, :2603) patches `subprocess.run` via a `mock_cli` fixture and a `_cli_stdout(verdict, confidence, reason)` helper; short-circuit branches assert both an error-substring in `result.details["pair_results"]` and `mock_run.assert_not_called()`.
- No existing test in `test_cli_harness.py` calls `_grade()` directly by name (repo-wide search, no hits) — current coverage (`TestSemanticEvaluator`, :779) exercises grading only indirectly through `cmd_cmd()`.

## Impact

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-13 — based on codebase analysis:_

- **Priority**: P3 (set) — widens grading fidelity for an internal evaluation tool rather than fixing a user-facing defect; justified as non-critical but compounding, since every downstream consumer of a `_grade()` verdict inherits the same blind spot.
- **Effort**: Medium — the codebase already holds close analogs to reuse (`EvidenceEntry`/`GapEntry` source-traced-evidence-with-gaps convention, `cli/loop/evidence.py:56-119`; `ArtifactOutput`/`promote_run_artifact()` declared-artifact convention, `fsm/schema.py:1330-1373`; an established XML-tag-wrapped multi-section judge-prompt convention shared by `evaluate_llm_structured()`/`evaluate_contract()`/the blind comparator, `fsm/evaluators.py:1102`/`:1461-1469`/`:1209-1213`) — but the change touches multiple call sites (`_grade()`, `evaluate_llm_structured()`, the `evaluate()` dispatcher, five CLI subparsers) and, if evidence is meant to persist, a `harness_events` schema migration (`session_store/schema.py`, currently `SCHEMA_VERSION = 50`).
- **Risk**: Low-to-Medium — additive by construction (existing stdout-only grading keeps working when no new channel is declared); the schema-migration precedent in this codebase is fix-forward, nullable, no-default; the concrete risk is regressing the existing 4000-char truncation budget shared by every judge-prompt call site (`fsm/evaluators.py:1100`,`:1199-1200`,`:1440`,`:1458`) if new sections are concatenated without re-deriving that budget across channels.
- **Breaking Change**: No — existing `--semantic` runs with no declared channel keep evaluating `result.stdout` alone.

## Session Log
- `/ll:audit-issue-conflicts` - 2026-09-13T21:28:46 - `23df08cc-836b-4f77-a1e2-bfb5aedb0f55.jsonl`
- `/ll:refine-issue:gap-analysis` - 2026-09-13T20:01:33 - `ba1e78b0-d003-48c9-ad54-d85428e37f7d.jsonl`
- `/ll:wire-issue` - 2026-09-13T19:41:39 - `a869cc2b-c93b-4b9c-afec-ff74a5703ae9.jsonl`
- `/ll:refine-issue` - 2026-09-13T19:26:36 - `021c5145-df0e-49c1-af9a-18ee5ea0a32b.jsonl`

## Scope Boundaries

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-13 — based on codebase analysis:_

- **In scope**: widening `_grade()`/`_evaluate_and_report()` (`harness.py`) to treat `result.stderr` as a distinct gradable channel; making a declared-written file's content available as judge/criterion evidence; making a named side effect (file exists, path changed, git status clean via the existing `_git_dirty()` primitive, `harness.py:90`) an assertable criterion outcome; and an evidence record that distinguishes unexamined from examined-and-empty channels.
- **Out of scope, adjacent**: completing the pre-existing, already-CLI-surfaced but unenforced `--require-artifact`/`--forbid-path`/`--require-order`/`--trace-mode` plumbing (`harness.py:639-688`, `runner_spec.py:196-230`) — those flags exist and are already fingerprinted into `conditions_fp` but have zero enforcement code path anywhere in the tree (confirmed by repo-wide search); wiring them from inert to enforced is a distinguishable unit of work, not a prerequisite for this issue.
- **Out of scope, adjacent**: `FSMExecutor._evaluate()`'s identical single-channel gap (`fsm/executor.py:3092-3116`, `evaluate_llm_structured(action_result.output, ...)` at `:3108`) — a different action-result type (`ActionResult`, not `runner_spec.RunnerResult`), a different call site, and a different consumer (FSM loop states, not the `ll-harness` CLI). Already flagged as a dependent-files wiring touchpoint by `/ll:wire-issue`, but the fix itself belongs to whichever issue owns the FSM executor's evaluation path.
- **Out of scope**: `loops/harness-optimize.yaml`'s benchmark-score capture reads `captured.benchmark_score.output` directly and never calls `ll-harness`/`_grade()` — not a consumer of this code path.
