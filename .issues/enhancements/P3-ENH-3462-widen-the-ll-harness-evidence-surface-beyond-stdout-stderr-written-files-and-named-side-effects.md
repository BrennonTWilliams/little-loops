---
id: ENH-3462
title: "Widen the ll-harness evidence surface beyond stdout \u2014 stderr, written\
  \ files, and named side effects"
type: ENH
priority: P3
status: open
discovered_date: '2026-09-13'
labels:
- evals
- reliability
size: Large
parent: EPIC-3475
epic: EPIC-3475
confidence_score: 100
outcome_confidence: 74
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 10
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

### Decisions (review pass, 2026-09-14)

The research passes below surfaced several open forks. They are resolved here so the implementer does not have to re-derive them; later research sections that describe alternatives are context, not options.

- **D1 — Declaration syntax lives in `_add_evaluator_flags()`, on all five subparsers.** New flags: `--evidence {stderr}` (repeatable, **additive**: `stdout` is always examined and cannot be undeclared, so `--evidence stderr` means stdout+stderr — naming one channel must never silently drop the default; amended 2026-09-14 review), `--expect-no-git-changes` (store_true; named for its semantics, see D5 — not `--expect-git-clean`, which would promise a clean tree). `cmd_dsl` builds a fresh per-task `argparse.Namespace` (`harness.py:2328-2337`) copying only eight fields (`target`, `exit_code`, `semantic`, `timeout`, `output`, `verbose`, `model`, `issue_id`); it must also copy `evidence`, `require_artifact`, `forbid_path`, `expect_no_git_changes`, or the flags are silently inert on the dsl runner despite AC11. The existing inert FEAT-2878 flags `--require-artifact PATH` (repeatable) and `--forbid-path PATH` (repeatable) **move** from `_add_trace_flags()` into `_add_evaluator_flags()` and become the declared-artifact mechanism — enforced, not just fingerprinted. Paths resolve relative to the process cwd (or the trace-mode workspace when `--trace-mode` is set, unchanged); rewrite both flags' help strings, which still say "relative to the workspace". `--trace-mode`, `--require-order`, `--keep-workspace`, `--hosts` stay in `_add_trace_flags()` and stay out of scope. Rationale: building a parallel `--expect-file` beside a dead `--require-artifact` is the duplication the wiring pass warned against; reusing the flag names keeps `_conditions_fp()` and `logs.py`'s fixture round-trip stable.
- **D2 — Channel provenance is an in-memory record on the outcome, not a reuse of `EvidenceBundle`.** Add `ChannelRecord(name: str, examined: bool, content: str | None, note: str | None = None)` (dataclass in `cli/harness.py`) and `HarnessEvalOutcome.channels: list[ChannelRecord]`. `examined=False, content=None` means never read; `examined=True, content=""` means read and empty. `_evaluate_and_report()` renders the list in both the human report and the `--json` payload. **JSON shape (amended 2026-09-14, second review):** `ChannelRecord.to_dict()` emits `{"name", "examined", "chars": int | None, "note"}` — **not** `content`. The `--json` payload already carries `stdout`/`stderr` as top-level keys (`harness.py:1659-1660`), so echoing them under `channels` doubles the payload, and an artifact body could add an arbitrarily large file. `chars` is `None` when `content is None` (never read / missing), `0` when read-and-empty, else `len(content)`. Bodies stay in memory on the dataclass for the judge and the human report's per-channel char count. `cli/loop/evidence.py`'s `EvidenceBundle`/`GapEntry` is the wrong module and the wrong shape (a gap list, not a per-channel status) — cite it as precedent, do not import it.
- **D3 — Judge evidence is pre-composed in `_grade()`; `evaluate()`, `FSMExecutor._evaluate()`, and `cli/queue.py` are not touched. `evaluate_llm_structured()` gains one additive, keyword-only, default-preserving parameter (amended 2026-09-14, see Verification Notes).** **Composition rule (amended 2026-09-14 review, reconciles AC1/AC2):** when the declaration is exactly the default — stdout only, no `--require-artifact` paths — `_grade()` passes raw `result.stdout` unchanged, exactly as today. Otherwise it builds one string from the declared channels, each wrapped in its own tag (`<stdout>`, `<stderr>`, `<artifact path="...">`), joined by blank lines. Note the composed string then sits inside the evaluator's existing `<action_output>` wrapper, so tags nest. Each channel gets its **own** 4000-char truncation budget (the `evaluate_contract()` per-file precedent), applied before composition, **keep-last** (matching the evaluator's own direction) for every channel including artifacts. `evaluate_llm_structured()`'s own truncation (`fsm/evaluators.py:1100`, a keep-last-4000-chars slice of the *whole* `output` string) would otherwise re-truncate the already-composed multi-channel string and silently drop earlier channels' tags entirely — so `evaluate_llm_structured()` gains `max_output_chars: int | None = 4000` (keyword-only; `None` disables truncation; default `4000` is unchanged, so every other caller — `FSMExecutor._evaluate()`, `cli/queue.py`, FSM loops — stays byte-identical, preserving AC2). `_grade()` passes a value covering the full composed length (or `None`, meaning "already bounded, do not re-truncate") since it has already applied the per-channel budget itself. This is the only touch to `evaluate_llm_structured()`'s signature — its `output=` parameter, `evaluate()`'s dispatch, and every other consumer stay untouched — matching `evaluate_convergence()`'s additive `reference` param (ENH-3421) as precedent. Update the docstring's `output:` line (`fsm/evaluators.py:1083`, currently "Action stdout to evaluate") to say the caller may pass a pre-composed multi-channel string and should then pass `max_output_chars=None`. The FSM executor's identical single-channel gap is unaffected and remains a separate issue.
- **D4 — Persistence is deferred to a follow-up child issue under EPIC-3475.** No `harness_events` column, no `SCHEMA_VERSION` bump, no `HarnessEvent`/manifest/DES/doctor changes in this issue. The follow-up persists `outcome.channels` (JSON) and the side-effect results. This issue's deliverable is the widened verdict plus the report/JSON record.
- **D5 — Side-effect semantics.**
  - **Snapshot placement.** `_evaluate_and_report()` receives an already-executed `RunnerResult`; `run_action()` is called inside each handler's `_invoke` closure (`harness.py:1755`, `:1889`, `:2009`, `:2093`) and via `_run_prompt_action()` for dsl. The pre-run snapshot and post-run check therefore wrap the *invoke*, not the grade (amended 2026-09-14 review; the original step 3 placed it in `_evaluate_and_report()`, which is unreachable-before-run). **Callable contract (amended 2026-09-14, second review):** the `invoke: Callable[[], tuple[RunnerResult, int]]` type is shared by `_run_sample_loop()` (`:1537`) and `_run_baseline_phase()` (`:1380`, which forwards it at `:1425`/`:1490`); do **not** change it to a 3-tuple. Instead `_run_sample_loop()` itself calls `_snapshot_side_effects()` before and `_check_side_effects()` after each `invoke()` (which also gives D8's per-sample re-snapshot for free), and only the four single-run paths (`:1842`, `:1948`, `:2068`, `:2187`) plus `cmd_dsl`'s per-task `_run_prompt_action()` call go through the `_invoke_with_side_effects(invoke, args) -> (result, duration_ms, side_effects)` wrapper. Net: the `_invoke` closures and the baseline phase are untouched.
  - `--require-artifact PATH`: snapshot pre-run existence + sha256 + `st_mtime_ns` (sha256 shared with `--forbid-path`). After the run, `PATH` must exist, be a regular file, **and** have been *touched* by the run: did not exist pre-run, **or** sha256 differs, **or** `st_mtime_ns` differs (amended 2026-09-14, second review — sha256 alone false-fails a deterministic runner that rewrites byte-identical content, which is exactly the `--samples N` case in AC8 where sample 2 produces the same bytes as sample 1; a real rewrite always bumps mtime on APFS/ext4, an untouched file never does). A pre-existing, untouched file → `passed=False`, `note="pre-existing, unchanged"` — otherwise a stale artifact from a previous run (or from sample 1 under `--samples N`) satisfies the check while the runner did nothing, which is exactly the failure this issue exists to close. When present and touched, its content is read (per-channel budget) and appended to the judge evidence when `--semantic` is set. Missing or unreadable → `passed=False`, record `examined=True, content=None, note="missing"` / `note="unreadable: <err>"`.
  - `--forbid-path PATH`: after the run, `PATH` must **not** exist, or, if it existed before the run, must be byte-identical to its pre-run content. Snapshot pre-run existence + sha256 for each declared path — **sha256 only, no mtime** (byte-identical is the promise here; a rewrite with identical bytes is harmless and must pass). If `PATH` is a directory, the check is existence-only (no sha256; a pre-existing directory passes, a newly created one fails).
  - `--expect-no-git-changes`: means "the run introduced no new changes," **not** "the tree is clean afterward." Run `git status --porcelain -z` before and after and parse with `porcelain_paths()` (`git_operations.py:551`, which consumes NUL-delimited records). **Do not reuse `_git_dirty()`'s subprocess call** (`harness.py:90`, amended 2026-09-14, second review): it passes `--untracked-files=no` by design, and AC5 requires a run that *adds an untracked path* to fail — so this criterion issues its own `git status --porcelain -z` **without** `--untracked-files=no` (git's default `normal` mode), and `porcelain_paths()`'s rename handling is why `-z` is mandatory. Fail if the post-run set minus the pre-run set is non-empty. **Also** snapshot a sha256 of the working-tree content for each *pre-dirty* path, so a run that further modifies an already-dirty file (same path in both sets) fails too; note the offending paths. Do not use `_git_dirty()`'s boolean for this criterion; it stays as descriptive provenance only.
  - **Path resolution / cwd.** Declared paths and the git snapshot resolve against the harness process cwd. The `cmd` runner inherits that cwd, so relative paths line up; for `skill`/`prompt`/`mcp`/`dsl` the host CLI decides where it writes, so **run `ll-harness` from the target project root** for relative `--require-artifact`/`--forbid-path` paths to match. Document this in the flag help strings and `docs/reference/CLI.md`.
  - Every side effect that fails sets `passed=False` (exit 1), same precedence as `--exit-code`; they never abstain.
- **D6 — Undeclared channels never influence the verdict.** An `--exit-code 0` run with warnings on stderr keeps passing unless `--evidence stderr` is declared; stderr is then judged only through `--semantic`. There is no built-in "stderr must be empty" rule.
- **D7 — `tool_trace` is out of scope.** It is populated only in trace mode, which is unreachable from the CLI today.
- **D8 — `--samples N` (ENH-3415) runs the side-effect checks per sample**, re-snapshotting before each sample, so each of the n runs yields the widened evidence. With the D5 touched rule (sha256 or `st_mtime_ns` changed), sample k's artifact snapshot includes sample k-1's output, so each sample must itself write the artifact to pass — a byte-identical rewrite still passes because mtime advances. Re-snapshotting happens inline in `_run_sample_loop()` around each `invoke()`.
- **D9 — dsl runner: per-task side effects.** `cmd_dsl` runs N tasks in one process; the snapshot/check wraps each task's `_run_prompt_action()` individually, so declared artifacts and git changes are attributed to the task that produced them.
- **D10 — Every read of a new flag uses `getattr(args, name, default)`.** (Added 2026-09-14, second review.) `test_cli_harness.py`'s `_make_namespace()` (`:48-64`) builds an `argparse.Namespace` with only seven attributes and is used by roughly a hundred existing tests; a bare `args.evidence` in `_grade()`, `_snapshot_side_effects()`, `_check_side_effects()`, or `_compose_judge_evidence()` raises `AttributeError` across all of them. `_conditions_fp()` (`:1231-1234`) already follows this rule for `forbid_path`/`require_artifact`; the defaults are `evidence=[]`, `require_artifact=[]`, `forbid_path=[]`, `expect_no_git_changes=False`, and the absent-attribute case must behave identically to the default declaration (AC2). Do not widen `_make_namespace()` as the fix — that would hide the same crash for the `cmd_dsl` `task_args` Namespace and any external caller.

## Why it matters

The instrument that certifies runner correctness is scoring the narration rather than the work. Every downstream consumer of a harness verdict — candidate selection, regression detection, improvement loops — inherits a verdict that is blind to the actual work product, and an improvement loop cannot diagnose what its harness never captured.

## Current Behavior

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-13 — based on codebase analysis:_

- `_grade()` (`scripts/little_loops/cli/harness.py:916-982`) reads only the exit code and stdout fields on its `result` argument; on `--semantic`, it calls `evaluate_llm_structured(output=result.stdout, ...)` (:956-958) — the stderr and tool-trace fields never reach it.
- The stderr field is captured on every run but only ever used for display: `_evaluate_and_report()` (`scripts/little_loops/cli/harness.py:1591`) embeds it in the JSON payload (`:1660`) and error report (`:1707`); `_run_sample_loop()` (`scripts/little_loops/cli/harness.py:1533`) attaches it to a sample's dict only `if args.verbose or label != "PASS"` (`:1578`). `record_harness_event()` (`session_store/writers.py:1210-1241`) has no stderr parameter and the `harness_events` schema (`session_store/schema.py:718-736`) has no stderr column — stderr is discarded once the process exits, never persisted or graded.
- The tool-trace field (`scripts/little_loops/runner_spec.py:113`, populated only in the `trace_mode` branch of `_run_skill()` at `scripts/little_loops/runner_spec.py:221`/`:229`) has zero readers anywhere in `scripts/little_loops/cli/harness.py` (repo-wide search, no hits) — captured but never surfaced or consulted.
- `--trace-mode`/`--require-order`/`--require-artifact`/`--forbid-path` (`_add_trace_flags()`, `scripts/little_loops/cli/harness.py:639-688`, attached only to `skill_p`) have exactly one consumer repo-wide: `_conditions_fp()` (`harness.py:1231/1234/1235`), which folds them into a baseline-matching fingerprint hash. None of the four `ActionSpec(...)` construction sites (`harness.py:1747-1753`, `:1882-1887`, `:2001-2007`, `:2085-2091`) forward `trace_mode`/`require_artifact`/`forbid_path` into `spec.args`, so the `trace_mode` branch of `_run_skill()` (`scripts/little_loops/runner_spec.py:196-230`) is unreachable via any `ll-harness` command path today — the flags perturb the fingerprint and otherwise do nothing.
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
- `--require-artifact`/`--forbid-path`/`--trace-mode` flags (`_add_trace_flags()`, :639-672) are parsed only onto `skill_p` (:702) today, not `cmd_p`/`mcp_p`/`prompt_p`/`dsl_p` (`prompt_p` gets `_add_evaluator_flags()` only, not `_add_trace_flags()`); their only consumer is `_conditions_fp()` (:1215-1243), a baseline-fingerprint identity use, not a runtime assertion. A declared-side-effect mechanism reusing this flag set touches all five parsers and needs a new consumer beyond `_conditions_fp()`.
- `harness_events` schema (`session_store/schema.py:718`) has no `stderr`/artifact/channel-provenance columns — persistence, not just in-memory grading, is a dependent surface if the widened evidence is meant to survive past the single report.

**Conventions in Force**
- This codebase already holds a convention for "evidence must be source-traced, and an unread/missing input produces an explicit gap marker rather than a silent omission" — `EvidenceBundle`/`EvidenceEntry`/`GapEntry` (`scripts/little_loops/cli/loop/evidence.py:56-119`, FEAT-3182). Every entry traces to one of a closed `_EVIDENTIARY_SOURCES` set; LLM-sourced facts are segregated into a separately labeled, non-evidentiary section; any absent/incomplete input produces an explicit `GapEntry`. This is the closest existing analog to this issue's "examined-and-empty vs. unexamined" requirement, though it lives in `cli/loop/evidence.py`, not `cli/harness.py`.
- This codebase already holds a convention for "a run declares one expected artifact, and downstream code checks existence against the declaration rather than scraping" — `ArtifactOutput` (`fsm/schema.py:1330-1373`) / `promote_run_artifact()` (`fsm/persistence.py:741-791`): a missing declared artifact is logged and treated as a distinguishable no-op, never silently promoted, never a hard crash.
- This codebase already holds a convention for "an evaluator's input channel can be redirected away from raw action stdout by explicit declaration" — `EvaluateConfig.source` (`fsm/schema.py:72`) / `fsm/executor.py:3129-3137` — but this exists only in the FSM loop-execution layer, not as an `ll-harness` CLI flag; `_grade()` has no equivalent.
- This codebase already holds a convention for "declaring named file paths and reading their content as judge evidence, with a per-file unreadable-file path that produces an explicit error verdict rather than a crash" — `evaluate_contract()` (`fsm/evaluators.py:1349-1438`).
- Two **disagreeing** conventions exist for git-status-as-evidence: `_compute_worktree_digest()` (`fsm/executor.py:1757-1776`) hashes `git status --porcelain` + `git diff HEAD` into one opaque sha256 (detects *that* something changed); `issue_lifecycle.py`'s pre-run-dirty snapshot/diff (:490-548) produces an explicit changed-path set (detects *what* changed). Neither calls into the other; `git_operations.py::porcelain_paths()` (:551) is the one shared parsing utility between them, used only by the latter.
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

_Added by `/ll:refine-issue` — 2026-09-14 — based on codebase analysis:_

- `scripts/little_loops/session_store/schema_manifest.json` — a checked-in column list for `harness_events` (`:1089`) that `test_schema_manifest_matches_checked_in_file` (`scripts/tests/test_session_store_schema.py:3152`) asserts matches the live PRAGMA-derived schema byte-for-byte after every migration; a new `harness_events` column not also reflected here fails CI. Not previously listed in the Wiring Phase's schema-migration checklist.
- `scripts/little_loops/session_store/__init__.py` (`record_harness_event` re-export, docstring `:56`, `__all__` `:270`) and `scripts/little_loops/history_reader/__init__.py` (`HarnessEvent`/`recent_harness_events`/`harness_event_by_id`/`authoritative_attempt(s)` re-exports, `:63,121-127,185,194,278,341`) — package-level re-export points for the writer/reader that stay in sync automatically once the underlying functions change, but confirm the full public surface touched.
- `scripts/little_loops/cli/doctor.py` (`_schema_manifest`/`_reference_manifest_at`, `~:537-540`) — `ll-doctor` validates the live DB schema against the same manifest `schema_manifest.json` backs, a second consumer of manifest correctness beyond the test gate.
- Additional test files exercising functions this issue widens, not previously listed: `scripts/tests/test_session_store_schema.py` (`TestHarnessEventsTable`, `TestHarnessEventsRunModelColumns` ~:1692, `TestHarnessEventsContentPinColumns` ~:2183, `TestHarnessEventsBaselineConditionColumns` ~:3332 — precedent for extending `harness_events` migration coverage — plus the schema-manifest gate classes `test_schema_manifest_matches_checked_in_file` :3152 and `test_manifest_schema_version_matches_live_schema_version` :3169); `scripts/tests/test_session_store_writers.py::TestRecordHarnessEvent` (:2390, exercises `record_harness_event()`'s INSERT/parent-linking/repetition/superseding behavior directly); `scripts/tests/test_history_reader_harness.py` (read-side counterpart to `history_reader/harness.py`, not previously named despite the module itself being listed); `scripts/tests/test_ll_session.py` (`test_recent_kind_harness_outputs_row`/`test_search_kind_harness_matches_indexed_rows`, :1380-1409 — exercises `ll-session recent/search --kind harness` over `record_harness_event()` rows, a CLI-surface consumer parallel to but distinct from `history_reader/harness.py`); `scripts/tests/test_ll_loop_execution.py` (patches `evaluate_llm_structured` at both `little_loops.fsm.executor.evaluate_llm_structured` and `little_loops.fsm.evaluators.evaluate_llm_structured`, e.g. `:1234`/`:1383` — another call site exercising the widened function, structurally identical to `test_ll_loop_scaffold_verify.py`); `scripts/tests/test_ll_loop_scaffold_verify.py` (`:19,373` — imports `EvaluationResult`, patches `little_loops.fsm.evaluators.evaluate_llm_structured`).
- Correction to a graph-seeded lead: `scripts/little_loops/cli/loop/feed.py`'s `harness_duration_ms`/`harness_tokens` fields (`:867-878`) were flagged as a candidate `harness_events` consumer during seeding but, on direct read, come from a different data path — `fsm/executor.py:3640-3651`'s `_on_harness_usage`/`_on_baseline_usage` closures populate them from `ab_writer.py`'s A/B blind-evaluation comparator (FEAT-1822/ENH-1790), not from the `harness_events` SQL table this issue is about. Not a dependent file for this issue's persistence scope.

**Documentation staleness (resolves this pass's research-triage "stale" verdict on `docs/reference/API.md`)**
- `docs/reference/API.md` is stale beyond line-number drift: `evaluate_llm_structured()`'s documented signature (now at `:6250-6258`, drifted from the `:6228-6237` cited 2026-09-13) still shows `timeout: int = 30` against actual code's `timeout: int = 1800` (`fsm/evaluators.py:1075`, matching this issue's own Program Design citation — the doc is wrong, not the issue); the `evaluate()` dispatcher's documented signature (now at `:6266-6272`, drifted from `:6244-6249`) omits the `model: str | None = None` parameter present in code (`:1832`); the `SCHEMA_VERSION` annotation (now at `:9623`, drifted from `:9601`) reads "# 45" against code's `50` (`schema.py:25`) — the same stuck-at-v45 staleness already flagged for `HISTORY_SESSION_GUIDE.md`, found independently here too; the `RunnerResult` section cited at `:10726-10761` has drifted to `:10790-10827`. Citations at `:2806`, `:6157-6171`, `EvaluationResult :6139`, `evaluate_llm_structured :6228` are re-confirmed accurate in substance (line numbers re-drifted again as of 2026-09-14's re-verification, per above).
- `docs/guides/EVALUATION_GUIDE.md`'s `` `_grade()`, `harness.py:~865` `` citation (`:96`) has drifted ~51 lines from `_grade()`'s actual location (`harness.py:916-982`).
- `docs/reference/CLI.md`, `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md`, `docs/reference/EVENT-SCHEMA.md`, `docs/ARCHITECTURE.md` citations re-confirmed still accurate (not stale).

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/fsm/executor.py` — `FSMExecutor._evaluate()` (:3076-3169) has the identical single-channel gap as `_grade()`: the default-evaluation branch (:3108-3113) calls `evaluate_llm_structured(action_result.output, ...)` and the explicit-evaluation branch (:3152-3158) calls `evaluate(config=state.evaluate, output=eval_input, ...)` — both ignore `action_result.stderr` (populated at :3059/:3070 on every `ActionResult`). A signature widening on `evaluate_llm_structured`/`evaluate` touches both call sites. [confirmed by direct read, :3100-3160]
- `scripts/little_loops/fsm/evaluators.py` — the `evaluate()` dispatcher itself (:1827-1833, signature `(config, output, exit_code, context, model=None)`) has no `stderr` parameter; its `llm_structured` branch (:2039-2053, confirmed via `ll-code callers-of`) forwards only `output=output`. Widening `evaluate_llm_structured` requires widening `evaluate()`'s own signature too, since every other evaluator type (`mcp_result`, `contract`, `comparator`, `classify`, :2055-2087) is dispatched through the same function.
- `scripts/little_loops/cli/queue.py` — `_run_loop_entry` (:382-433) constructs `RunnerResult` **directly** (`RunnerResult(stdout=stdout, stderr=stderr, exit_code=returncode, error=error)`, :433), bypassing `runner_spec.run_action()` entirely (by design — `RunnerType.LOOP` is excluded from `run_action()`'s dispatch table, per comments at `runner_spec.py:129-134`). Any new evidence field populated inside `run_action()` will NOT automatically appear on this second, independent `RunnerResult` producer — it needs the matching change made here too.
- `scripts/little_loops/cli/harness.py` — `_conditions_fp()` (:1215-1243, ENH-3435 baseline-fingerprint payload) enumerates every condition-relevant CLI flag (`exit_code`, `forbid_path`, `require_artifact`, `trace_mode`, etc., payload dict :1229-1241). Any new CLI flag this issue introduces to declare which channels/artifacts to examine must be added to this payload, or two runs graded under different evidence-declaration configs will collide on the same `conditions_fp` and incorrectly share a baseline (`baseline_for()` in `history_reader/harness.py:315-392` matches purely on `conditions_fp`).
- `scripts/little_loops/session_store/schema.py` — `SCHEMA_VERSION = 50` (:25) and the `_MIGRATIONS` list (v50 entry :1390-1415) are the established pattern for a new `harness_events` evidence column: a new list entry (`ALTER TABLE harness_events ADD COLUMN <name> <TYPE>;`, nullable, no DEFAULT, fix-forward only).
- `scripts/little_loops/session_store/writers.py` — `_insert_harness_event()` (:1109-1207, column list :1156-1164, parameter tuple :1165-1195) and `record_harness_event()` (:1210-1299, thin wrapper) both need new evidence kwargs threaded through if a column is added.
- `scripts/little_loops/cli/harness.py` — `_record_harness_event()` (:214-261) and its `record_attempt()` call (:264) is the harness CLI's own wrapper; needs new kwargs added and threaded from `_grade()`'s new evidence data.
- `scripts/little_loops/history_reader/harness.py` — read-side consumer of the same schema: `HarnessEvent` dataclass (:53-98, needs new trailing-default fields per its own v49/v50-precedent docstring at :61-64/:92-94) and `_HARNESS_EVENT_COLUMNS` (:101-108, the single SQL column-list string reused by every reader — `recent_harness_events`, `harness_event_by_id`, `authoritative_attempt(s)`, `baseline_for`). Also imports `SampleTally` from `cli.harness` at :367 (bidirectional coupling with `cli/harness.py`, not previously noted).

_Wiring pass added by `/ll:wire-issue` — 2026-09-14:_
- `scripts/little_loops/observability/schema.py` — `HarnessEventVariant(DESVariant)` (:731-734, registered in the `DESVariant` registry list at :884, docstring `"""record_harness_event writes to harness_events (ll-harness, ENH-2739)."""`) is a second, independent enumeration of the `harness_events` row shape — a Data-Event-Schema audit registration distinct from `session_store/schema.py`'s migration list and `schema_manifest.json`'s column list. A new evidence column needs reflecting here too, or the DES audit drifts from the live schema.
- `scripts/little_loops/cli/logs.py` — `_build_eval_fixture()`/`_fixture_to_harness_argv()` (:1857-1910, FEAT-1971) round-trip a subset of the `ll-harness` CLI flag surface (`runner_args`, `exit_code`, `semantic`, `timeout`, `samples`) for eval-fixture export/import. A new evidence-declaration CLI flag silently drops out of this round-trip unless added here too.
- `scripts/little_loops/session_store/writers.py` — `record_attempt()` (:1367-1452, ENH-3407) is the actual write path for 6 of `_record_harness_event()`'s 7 call sites in `cli/harness.py` (:1762, :1896, :2016, :2135, :2299, :2382); `record_harness_event()` (already listed above) is used only at :2276. Confirmed by direct read: `record_attempt()` forwards `**event_fields` straight into `_insert_harness_event()`, so it needs **no code change** itself — but it means `_record_harness_event()` in `cli/harness.py` is the real assembly point for new evidence kwargs on the dominant write path, not `record_harness_event()` alone as the existing bullet above implies in isolation.

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/ARCHITECTURE.md` — schema-migration table (`| v31 |` … `| v49 |` rows, e.g. :670/:682) documents every `harness_events` migration; a new evidence-channel migration needs a new row following the v49/v50 entries' style.
- `docs/guides/HISTORY_SESSION_GUIDE.md` — an independent, separate copy of the same schema-migration table (:57-99, e.g. `| v31 | ENH-2739 | harness_events table... |` at :91). This table already reads "Current schema version: 45" at :57 while code is at `SCHEMA_VERSION = 50` — already stale by several migrations; a new v51 row is one more it needs.
- `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` § "Contract Gates (`check_contract`)" — comparison table at :189-194 documents the current limitation in prose (`| Reads files | No — evaluates action stdout | Yes — reads both files directly |`, :192); this specific row/anchor should be updated once the gap it describes is closed.
- `docs/reference/EVENT-SCHEMA.md` § "CLI exit-code conventions" (:1795) — prose paragraph explicitly stating *"Only `RunnerResult.timed_out` is persisted to `harness_events`; `RunnerResult.error` has no column."* — becomes stale the moment new evidence fields are persisted.

_Wiring pass added by `/ll:wire-issue` — 2026-09-14:_
- `scripts/little_loops/init/writers.py:207-216` — `_LL_COMMANDS` tuple's `ll-harness` entry (`"One-shot runner evaluation (skill, cmd, mcp, prompt, dsl) with exit-code and semantic criteria"`) is written verbatim into every consuming project's generated `CLAUDE.md`/`AGENTS.md` via `ll-init`; update this phrasing alongside `docs/reference/CLI.md` if the criterion vocabulary widens.
- `skills/create-eval-from-issues/SKILL.md:4` — same "exit-code and semantic criteria" phrasing describing `ll-harness`'s current flag surface. Host-adapter mirrors (`.qwen/skills/...`, `.kimi-code/skills/...`, `.gemini/skills/...`) carry the identical line but sync from this file via `ll-adapt --apply` — edit only the canonical `skills/` copy, not the mirrors.

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_fsm_executor.py` — extensive `llm_structured` evaluator coverage (~40 `patch("little_loops.fsm.executor.evaluate_llm_structured", ...)` sites; dedicated methods `test_llm_structured_evaluator_routes_on_verdict` :3354, `test_llm_structured_evaluator_failure_verdict` :3402, `test_llm_structured_evaluator_blocked_verdict` :3442). `test_llm_structured_evaluator_routes_on_verdict` (:3354) patches one level lower (`little_loops.fsm.evaluators.subprocess.run`) and already sets `.stderr = ""` on the fake CLI result without asserting on `evaluate_llm_structured`'s call signature — the pattern to model widened-channel evaluator tests after.
- `scripts/tests/test_cli_queue_run.py` — ~20 sites construct `RunnerResult(stdout=..., stderr=..., exit_code=..., ...)` via keyword args only to stub `run_action`/`Popen` results for `ll-queue run`; additive-safe for new fields as long as they default and stay keyword-only.
- `scripts/tests/test_fsm_evaluators.py` `TestLLMStructuredEvaluator` (976-1395) — `test_empty_stdout_includes_stderr` (:1218) is today's *only* place stderr feeds `evaluate_llm_structured`, but only as an empty-stdout fallback error string, not as judged evidence content — a gap to close. `test_output_truncation` (:1318) asserts `len(prompt_content) < 5000` as an upper bound on a 4000-char truncated `output`; needs a stderr/artifact-bearing counterpart if those channels share the same truncation budget (won't break, since it's an upper bound).
- `scripts/tests/test_fsm_persistence.py` `TestPromoteRunArtifact` (1670-2129+) and `scripts/tests/test_fsm_schema.py` `TestFSMLoopArtifactOutput` (4116-4198) — concrete "declared X, checked against declaration" test pattern (e.g. `test_no_op_when_declared_source_missing`, `test_fsm_persistence.py:1721`) to model a new "declared artifact, read and graded" test after.
- `scripts/tests/test_feat3182_evidence_bundle.py` `TestGapTaxonomy` (:204+) — concrete pattern (`test_missing_run_dir_produces_explicit_gap`, :205-211) of one `any(g.category == "<taxonomy-string>" for g in bundle.gaps)` assertion per gap kind plus `any(e.source == "<channel>" for e in bundle.evidentiary)` for provenance — the model for testing a new "examined vs never-examined" taxonomy, since no such convention exists anywhere else in the repo today (confirmed by repo-wide search).
- `scripts/tests/test_cli_e2e.py` `TestLlHarnessE2E::test_cmd_echo_hello_passes` (:472-488) — the only subprocess-level e2e test for `ll-harness` in the repo; exercises `cmd` + `--exit-code` only, no `--semantic`, no stderr assertion, no file-artifact declaration. A new e2e test exercising the widened evidence surface (real subprocess writing a file / producing stderr / leaving git status dirty, graded end-to-end) is the concrete gap here.
- `scripts/little_loops/cli/harness.py:660,667` — `--require-artifact`/`--forbid-path` (FEAT-2878) are parsed and folded into `_conditions_fp()`'s fingerprint but have **zero enforcement code path anywhere in the tree** and **zero test coverage** (confirmed by repo-wide, unfiltered search). Flagged as an adjacent, currently-inert declared-artifact surface with overlapping naming — new work should not collide with or silently duplicate this flag's eventual implementation.

_Wiring pass added by `/ll:wire-issue` — 2026-09-14:_
- `scripts/tests/test_session_store_writers.py::TestRecordAttemptAndAdmitRetry` (:2492-2723, ENH-3407) — the actual write-path test class for `record_attempt()`, the function that 6 of `_record_harness_event()`'s 7 call sites route through (see Dependent Files above). Extend this class, not `TestRecordHarnessEvent`, for write-path coverage of new evidence kwargs on the dominant path.
- `scripts/tests/test_cli_doctor_install_checks.py::TestSchemaDrift` (:333-533, ENH-3242) — covers `doctor.py::_schema_drift_data()`, which calls `_schema_manifest()`/`_reference_manifest_at()` against a live `.ll/history.db`. A new `harness_events` column needs this class's drift-detection coverage extended alongside `test_schema_manifest_matches_checked_in_file`.
- Gap: no test anywhere calls the real (unpatched) `_git_dirty()` implementation (`harness.py:90-119`) — all 11 references in `test_cli_harness.py` mock it out (`patch("little_loops.cli.harness._git_dirty", ...)`, e.g. :1022, :2083, :2892). If this issue makes git-cleanliness an assertable criterion, add a test exercising the real subprocess-based implementation via a temp git repo fixture, not only the mocked pass-through.

## Program Design

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-13 — based on codebase analysis:_

**Types**
- `RunnerResult` (`scripts/little_loops/runner_spec.py:100-113`) already has the fields this issue needs at the source: `stdout: str`, `stderr: str`, `exit_code: int`, `tool_trace: list[dict[str, Any]] | None`. No new capture-side type is required — the gap is entirely on the grading/assertion side, not the capture side.
- No existing type represents "which channels were read vs. left unread" anywhere in this codebase (confirmed by repo-wide search for `scope-of-claim`, `evidence surface`, `examined channel`, and equivalents — zero hits outside this issue file). `EvidenceEntry`/`GapEntry` (`cli/loop/evidence.py:56-119`) is the nearest existing analog but is scoped to `cli/loop/evidence.py`'s bundle, not to `ll-harness`.
- No existing type represents a "declared side effect" assertion checked against a criterion (as opposed to an artifact promoted at loop-terminal time). `ArtifactOutput` (`fsm/schema.py:1330-1373`) is a single-file promotion declaration, not a per-run multi-artifact assertion set graded by a criterion.

**Signatures**
- `_grade()` (`harness.py:916`) — currently reads only `result.exit_code` (:937) and `result.stdout` (:956-958, via `evaluate_llm_structured(output=result.stdout, ...)`). `result.stderr` and `result.tool_trace` are both already available on the same `result` argument and are unread by this function.
- `evaluate_llm_structured(output: str, prompt=None, schema=None, min_confidence=0.5, uncertain_suffix=False, model=DEFAULT_LLM_MODEL, max_tokens=256, timeout=1800, max_output_chars: int = 4000) -> EvaluationResult` (`fsm/evaluators.py:1067`) — a widened-channel call site pre-composes a multi-channel string and passes it as `output`; the new `max_output_chars` param (D3 amendment, 2026-09-14) is additive and keyword-only, default `4000` preserving today's truncation for every existing caller, letting `_grade()` opt out of re-truncation for its own already-bounded composed string.
- `_add_trace_flags()` (`harness.py:639`) defines `--trace-mode`, `--require-order`, `--require-artifact` (repeatable), `--forbid-path` (repeatable) but attaches them only to `skill_p` (:702); their sole consumer is `_conditions_fp()` (:1215-1243) — a fingerprint/identity function, not an assertion function.

**Call Path**
`cmd_skill`/`cmd_cmd`/`cmd_mcp`/`cmd_prompt`/`cmd_dsl` -> `run_action()` (`runner_spec.py`) -> `RunnerResult(stdout, stderr, exit_code, tool_trace)` -> `_grade()` (`harness.py:916`, reads `exit_code` + `stdout` only) -> `evaluate_llm_structured(output=result.stdout, ...)` (`fsm/evaluators.py:1067`) -> `EvaluationResult` -> `_evaluate_and_report()`/`_run_sample_loop()` -> printed report / `harness_events` persistence (`session_store/schema.py:718`, no stderr/artifact/channel-provenance columns).

**Decision Rules**
Resolved in `## Design → Decisions (D1–D10)`. Summary of the verdict logic `_grade()` gains:
- `passed = False` if any `--require-artifact` path is missing/unreadable/pre-existing-and-untouched (same sha256 and same `st_mtime_ns`), any `--forbid-path` was created or content-modified, or `--expect-no-git-changes` sees new porcelain paths (untracked included) or a further-modified pre-dirty path (D5). Precedence: fail > abstain > pass, unchanged.
- Judge input = raw `result.stdout` under the default declaration; tag-wrapped composition of declared channels otherwise (D3, D6). `stdout` is always declared; `--evidence` is additive (D1).
- `outcome.channels` always lists `stdout`, `stderr`, each `--require-artifact` path, each `--forbid-path` path, and `git` — with `examined=False` for any that was not declared (D2).

**New types / signatures**
- `ChannelRecord` dataclass (`cli/harness.py`): `name`, `examined`, `content`, `note`; `to_dict()` emits `name`/`examined`/`chars`/`note` (no `content`, per D2).
- `HarnessEvalOutcome.channels: list[ChannelRecord] = field(default_factory=list)` (trailing default, additive).
- `_snapshot_side_effects(args, cwd) -> SideEffectSnapshot` (pre-run: per-path exists/sha256 for both `--require-artifact` and `--forbid-path`, plus `st_mtime_ns` for `--require-artifact` only; porcelain path set from an untracked-inclusive `git status --porcelain -z`; sha256 per pre-dirty path) and `_check_side_effects(snapshot, args, cwd) -> list[ChannelRecord]` (post-run). `_invoke_with_side_effects(invoke, args) -> tuple[RunnerResult, int, list[ChannelRecord]]` wraps the two around one runner invocation on the four single-run paths and `cmd_dsl`'s per-task call; `_run_sample_loop()` calls the snapshot/check pair inline around its own `invoke()` so the shared `invoke: Callable[[], tuple[RunnerResult, int]]` contract (also used by `_run_baseline_phase()`) is unchanged (D5). `_grade()` gains a keyword-only `side_effects: list[ChannelRecord] | None = None` parameter; `_evaluate_and_report()` and `_run_sample_loop()` pass it through. All flag reads via `getattr(args, name, default)` (D10).
- `_compose_judge_evidence(result, args, side_effects) -> str` — returns raw `result.stdout` under the default declaration; otherwise tag-wrap, per-channel keep-last 4000-char truncation, blank-line join. `_grade()` calls `evaluate_llm_structured(output=_compose_judge_evidence(...), max_output_chars=None)` only on the composed path (the raw-stdout path keeps the evaluator's default truncation, preserving AC2 byte-for-byte).

_Added by `/ll:refine-issue` — 2026-09-13 — based on codebase analysis:_

- Multi-channel composition precedent for `evaluate_llm_structured()`'s single `output: str` parameter: this codebase already wraps each evidence source in its own open/close tag named for its semantic role, joined by blank lines, each truncated to the same 4000-char budget, before composing one prompt string — `evaluate_llm_structured()`'s own `<action_output>` tag (`fsm/evaluators.py:1102`), `evaluate_contract()`'s attributed `<producer path="...">`/`<consumer path="...">` tags (`:1461-1469`), and the blind comparator's `<output_a>`/`<output_b>` tags (`:1209-1213`). A widened call composing stdout+stderr+artifact evidence into one string before calling `evaluate_llm_structured()` has this tag-wrap-and-concatenate shape as precedent; no single fixed tag vocabulary is shared across call sites today, so a new tag name is a free choice, not a violation of an existing constant.

_Added by `/ll:refine-issue` — 2026-09-14 — based on codebase analysis:_

- Precedent for widening a single evidence-channel evaluator into a multi-channel one: `evaluate_convergence()` (`fsm/evaluators.py:438-520`) added a `reference: float | None = None` parameter (ENH-3421) — a second, independently-sourced evidence value checked before the existing target-reached branch — threaded through `EvaluateConfig.reference` (`fsm/schema.py:74-79`) into the `evaluate()` dispatcher (`:1928-1954`). Its absence/resolution-failure semantics are declared explicitly and deliberately *differ* from the pre-existing `previous` channel's semantics (an unresolvable `reference` fails closed with `verdict="error"`; an unresolvable `previous` falls back silently to `None`) — the precedent is "each channel declares its own absence rule," not one shared rule. This is the only repo-wide precedent found for signature-level widening of an already-shipped evidence-bearing evaluator (`evaluate_contract()`/the blind comparator were multi-channel from their first commit, not widened later).
- ⚠ Superseded by D1 (2026-09-14): the flags go into `_add_evaluator_flags()`; the route question below is closed. Kept as context only. — No precedent exists for widening a partial CLI-flag-set helper (like `_add_trace_flags()`, attached only to `skill_p`) up to all five subparsers by editing that helper's call sites — searched repo-wide (comments, docstrings, CHANGELOG.md, issue history), none found. The one adjacent precedent, `--retry-of` (ENH-3407), reaches all five subparsers by declaring the flag inside the already-uniform `_add_evaluator_flags()` helper instead of widening the partial one. `_add_trace_flags()`'s own docstring states it was deliberately scoped to two parsers from birth (FEAT-2878), not narrowed down from five. Which route applies depends on whether a new evidence-declaration flag is evaluator-generic or trace-mode-specific — undetermined by precedent, a decision the implementer needs to make knowingly.
- A more complete end-to-end migration precedent than the v49/v50 entries already cited: `verdict_events`'s `abstention_reason` column (v44, ENH-230) required a full table rebuild (rename/copy-with-explicit-NULL/drop/rename) rather than a plain `ALTER TABLE ADD COLUMN`, because SQLite cannot `ALTER TABLE` a `CHECK` constraint onto an existing column (`session_store/schema.py:1178-1237`). The writer kwarg (`record_verdict_event(..., abstention_reason: str | None = None, ...)`, `writers.py:1498-1551`) and reader field (`VerdictEvent.abstention_reason: str | None`, `history_reader/events.py:48-77`) both document the SQL-NULL-vs-Python-None contract explicitly in their docstrings. The dedicated backfill test shape (`test_v43_db_upgrades_preserving_existing_rows`, `test_session_store_schema.py:2753-2787` — bootstrap old schema, insert a pre-migration row, run `ensure_db`, assert the new column reads back `None`) is distinct from `_MIGRATIONS`'s own DDL-correctness tests and is the concrete pattern to model a `harness_events` evidence-column backfill test after, if a CHECK constraint ends up involved.
- ⚠ Superseded by D2 (2026-09-14): `ChannelRecord(examined: bool, content: str | None)` is the chosen shape — a paired presence flag plus optional value, neither option below verbatim. Kept as context only. — Two design-precedent options for representing "channel not examined," both present in the codebase and not obviously reconcilable:
  - **Value-type widening**: `T | None` with no paired presence flag — `issue_parser.py`'s `_coerce_optional_int()`/`_coerce_tristate_bool()` (`:4336-4363`) and `IssueInfo.confidence_score: int | None` (`:3745`) treat "not set" as `None`, distinguishable from an explicit `0`/`False`, with no sibling `_present: bool` field.
  - **Closed-enum member**: an outcome enum gains an explicit non-outcome value — `learning_tests/gate.py`'s verdict function returns `Literal["passed", "blocked", "impl_failed", "infra_failed", "skipped"]` (`:211-262`, `skip=True` short-circuits to `"skipped"`), and `verdict_events.verdict` (v44) admits `cannot_judge` as a fourth member alongside `pass`/`fail`/`implement`, paired with a CHECK-enforced closed-enum `abstention_reason` naming *why*. This is a different shape from `EvidenceEntry`/`GapEntry`'s already-cited record-level gap list — here the absence lives inside the same field as the real outcomes, not a separate list. Neither option is used elsewhere specifically for "channel not examined"; both are precedents for adjacent problems (not-set field, not-evaluated outcome), not a directly reusable existing type.
- `EvaluateConfig.source` (already cited) redirects which whole channel an evaluator reads; a finer granularity already exists on the same dataclass for naming a sub-datum *within or beyond* a channel — `evaluate_output_json()`'s `path` (a JSON key, `:324-378`), `evaluate_classify()`'s `line` (`'last'`/`'first'`/an integer index, `:523-567+`), and `evaluate_contract()`'s `producer`/`consumer`/`*_pattern` (specific file paths, optionally regex-narrowed, `:1390-1393`) are all sibling fields on `EvaluateConfig` (`fsm/schema.py:39-148`), each meaningful only for its own evaluator `type`. A criterion-language addition for "which channel(s) am I asserting over" sits at the channel-selection granularity of `source`; naming a specific artifact path or side-effect within that channel sits at this finer granularity instead.

## Implementation Steps

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-13 — based on codebase analysis:_

⚠ Superseded — the original five research-derived steps (grade on `tool_trace`, leave the evidence-record shape open, leave the declaration syntax open) were replaced on 2026-09-14 by the concrete steps below, which follow Decisions D1–D8. The `docs/reference/API.md` staleness noted under Integration Map (`timeout: int = 30` vs. 1800, missing `model` param, `SCHEMA_VERSION` 45 vs. 50) is a doc defect to fix in step 6, not a reason to distrust the code citations.

1. **Flags (D1).** Add `--evidence` and `--expect-no-git-changes` to `_add_evaluator_flags()`; move `--require-artifact`/`--forbid-path` there from `_add_trace_flags()` and rewrite their help strings (no "workspace"). Add `evidence` and `expect_no_git_changes` to `_conditions_fp()`'s payload (`require_artifact`/`forbid_path` are already in it). Copy all four onto `cmd_dsl`'s per-task `task_args` Namespace (`harness.py:2328-2337`).
2. **Types (D2).** Add `ChannelRecord`; add `channels` to `HarnessEvalOutcome`.
3. **Snapshot/check (D5, D8, D9, D10).** Add `_snapshot_side_effects()` / `_check_side_effects()` / `_invoke_with_side_effects()`. Wrap the four single-run call sites (`harness.py:1842`, `:1948`, `:2068`, `:2187`) and each task's `_run_prompt_action()` in `cmd_dsl` with `_invoke_with_side_effects()`; inside `_run_sample_loop()` call snapshot/check inline around `invoke()` so the `invoke` callable type shared with `_run_baseline_phase()` is unchanged. Leave the `_invoke` closures themselves and `_evaluate_and_report()` (runs after the fact) untouched. Git snapshot runs its own `git status --porcelain -z` (untracked included), not `_git_dirty()`'s call. `--require-artifact` snapshots sha256 + `st_mtime_ns`; `--forbid-path` sha256 only. All new-flag reads via `getattr`.
4. **Grade (D3, D6).** `_grade()` takes `side_effects`, folds their pass/fail, builds the channel list, and calls `evaluate_llm_structured(output=_compose_judge_evidence(...), max_output_chars=None)` when `--semantic` is set and the declaration is non-default (raw stdout with default truncation otherwise). `evaluate_llm_structured()` gains `max_output_chars: int | None = 4000` and its `output:` docstring line is updated (D3). `tool_trace` is not read (D7).
5. **Report.** `_evaluate_and_report()` prints a `Channels:` block (`name  examined|not examined  <n> chars | missing | note`) and adds `"channels": [...]` (via `to_dict()`, `chars` not `content`, D2) to the `--json` payload; `_run_sample_loop()` attaches `channels` to each sample dict.
6. **Docs.** `docs/reference/CLI.md` `### ll-harness` flag table + a widened-evidence example + the run-from-project-root note for relative paths (D5); `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md:192` "Reads files" row; `init/writers.py` `_LL_COMMANDS` and `skills/create-eval-from-issues/SKILL.md:4` phrasing; `docs/reference/API.md` `HarnessEvalOutcome`/`_grade()`/`evaluate_llm_structured()` entries.
7. **Follow-up (D4).** Capture a child issue under EPIC-3475 for persisting `channels` + side-effect results to `harness_events` (v51 migration, manifest, DES variant, `HarnessEvent`, doctor drift test, EVENT-SCHEMA/ARCHITECTURE/HISTORY_SESSION_GUIDE tables).
8. `python -m pytest scripts/tests/test_cli_harness.py scripts/tests/test_cli_e2e.py -k harness scripts/tests/test_runner_spec.py -v` passes; full suite passes.

### Wiring Phase (added by `/ll:wire-issue`)

_Touchpoints from the wiring passes, filtered by the Decisions block. Items struck by a decision are listed under "Not touched" so they are not re-added._

**In scope**
- Update `scripts/little_loops/cli/harness.py` — `_conditions_fp()`'s payload dict (:1229-1241) to include `evidence` and `expect_no_git_changes`, so runs under different declarations don't collide on the same baseline fingerprint (`require_artifact`/`forbid_path` are already present).
- Update `scripts/little_loops/cli/logs.py`'s `_fixture_to_harness_argv()`/`_build_eval_fixture()` (:1857-1910) to round-trip `evidence`, `require_artifact`, `forbid_path`, `expect_no_git_changes`, or eval-fixture export/import silently drops them. The fixture schema is pinned by decision ARCHITECTURE-017 (`.ll/decisions.yaml`, cited in `_build_eval_fixture()`'s docstring); amend that decision's field list in the same change.
- Update `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md`'s Contract Gates comparison table (:189-194) — the "evaluates action stdout only" row is no longer accurate.
- Update `scripts/little_loops/init/writers.py`'s `_LL_COMMANDS` `ll-harness` entry (:207-216) and `skills/create-eval-from-issues/SKILL.md:4` — both describe today's "exit-code and semantic criteria" surface. Edit only the canonical `skills/` copy; run `ll-adapt --apply` for mirrors.
- Add an e2e test to `scripts/tests/test_cli_e2e.py`'s `TestLlHarnessE2E` exercising the widened surface via real subprocess (stderr, a declared artifact, a forbidden path, new git changes), since today's sole e2e test only covers `cmd` + `--exit-code`.
- Add a `TestChannelRecords` class in `test_cli_harness.py` modeled on `test_feat3182_evidence_bundle.py::TestGapTaxonomy` (:204+) — one method per (declared / not declared) × (present / empty / missing) cell, asserting by membership over `outcome.channels`.
- Add a real (unpatched) side-effect test via a temp git repo fixture (`git init`, commit, run, assert the new-path set) — today's 11 `_git_dirty()` references all mock it out, and D5's snapshot/diff path needs real-subprocess coverage.

**Not touched (per Decisions)**
- `fsm/executor.py` `FSMExecutor._evaluate()`, `fsm/evaluators.py` `evaluate()`, `cli/queue.py` `_run_loop_entry` — D3 pre-composes in `_grade()`; no evaluator *channel* signature widens. **Amendment (2026-09-14):** `fsm/evaluators.py::evaluate_llm_structured()` is the one exception — it gains an additive, keyword-only, default-preserving `max_output_chars` param so `_grade()`'s composed multi-channel string isn't re-truncated by the evaluator's own 4000-char default (see D3, Verification Notes). Every other caller of `evaluate_llm_structured()` is unaffected. The FSM executor's identical gap is a separate issue.
- `session_store/schema.py`, `session_store/writers.py`, `cli/harness.py::_record_harness_event()`, `history_reader/harness.py`, `schema_manifest.json`, `observability/schema.py::HarnessEventVariant`, `cli/doctor.py`, `test_session_store_writers.py::TestRecordAttemptAndAdmitRetry`, `test_cli_doctor_install_checks.py::TestSchemaDrift`, `docs/ARCHITECTURE.md` / `HISTORY_SESSION_GUIDE.md` migration tables, `docs/reference/EVENT-SCHEMA.md:1795` — D4 defers persistence to the follow-up child issue, which inherits this list verbatim.

## Acceptance Criteria

- [ ] AC1 — `ll-harness cmd ... --semantic "..." --evidence stderr` sends stderr to the judge: the prompt passed to `evaluate_llm_structured` contains both a `<stdout>` block and a `<stderr>` block (stdout is always declared; `--evidence` is additive).
- [ ] AC2 — With no new flags, `_grade()`'s judge input and verdict are byte-identical to today for the same `RunnerResult` (regression test pins `evaluate_llm_structured` is called with `output=result.stdout`, untagged, and without `max_output_chars`).
- [ ] AC3 — `--require-artifact PATH`: missing after the run → exit 1, `outcome.passed is False`, channel `PATH` recorded `examined=True, content=None, note="missing"`; present before the run and untouched (same sha256 **and** same `st_mtime_ns`) → exit 1, `note="pre-existing, unchanged"`; created, content-modified, **or rewritten with identical bytes (mtime advanced)** by the run → pass. With the path present-and-touched and `--semantic` set, the judge prompt contains `<artifact path="PATH">` with the file's content.
- [ ] AC4 — `--forbid-path PATH`: created during the run → exit 1; pre-existing and byte-identical after → pass; pre-existing and modified → exit 1; a pre-existing directory → pass (existence-only).
- [ ] AC5 — `--expect-no-git-changes`: a repo dirty before the run and unchanged by it passes; a run that adds one untracked or modified path fails with that path named in the channel note (the untracked case is asserted explicitly, since `_git_dirty()`'s `--untracked-files=no` call would miss it); a run that further modifies an already-dirty tracked file fails with that path named.
- [ ] AC6 — Every `HarnessEvalOutcome` carries `channels` covering `stdout`, `stderr`, every declared path, and `git`; undeclared entries are `examined=False, content=None`; an examined-but-empty stderr is `examined=True, content=""`. The `--json` payload includes `"channels"` as a list of `{name, examined, chars, note}` objects with **no `content` key** (stdout/stderr bodies remain only at their existing top-level keys), and the human report prints a `Channels:` block.
- [ ] AC7 — `--exit-code 0` with non-empty stderr and no `--evidence stderr` passes (D6).
- [ ] AC8 — `--samples 3` re-snapshots side effects before each sample; each sample dict carries its own `channels`; with `--require-artifact`, a sample that does not itself rewrite the artifact fails (`pre-existing, unchanged`), while a sample that rewrites it with byte-identical content passes. `_run_sample_loop()`'s and `_run_baseline_phase()`'s `invoke` parameter type is unchanged (`Callable[[], tuple[RunnerResult, int]]`).
- [ ] AC14 — Grading a `RunnerResult` with a Namespace lacking every new attribute (the existing `_make_namespace()` shape) behaves exactly as the default declaration: no `AttributeError`, `channels` lists stdout examined and everything else unexamined, and no side-effect check runs (D10).
- [ ] AC9 — Two runs differing only in `--evidence`/`--expect-no-git-changes` produce different `conditions_fp` values; `ll-logs` eval-fixture export/import round-trips all four declaration flags.
- [ ] AC10 — Each channel is truncated to 4000 chars (keep-last) independently before composition; a test with 6000-char stdout and 6000-char stderr asserts both tags are present and each body ≤ 4000, and that `evaluate_llm_structured` was called with `max_output_chars=None`.
- [ ] AC11 — `--require-artifact`/`--forbid-path`/`--evidence`/`--expect-no-git-changes` are accepted by all five subparsers (`skill`, `cmd`, `mcp`, `prompt`, `dsl`), and the dsl runner enforces them per task; `--trace-mode`/`--require-order` remain skill-only (they were never on `prompt_p`).
- [ ] AC12 — One subprocess-level e2e test in `TestLlHarnessE2E` covers a real command that writes a declared file, emits stderr, and dirties git.
- [x] AC13 — A child issue for `harness_events` persistence exists under EPIC-3475 and is linked from this issue's Session Log before this issue is marked done. (ENH-3476, `blocked_by: ENH-3462`, confirmed 2026-09-14.)

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
- **Effort**: Large (matches `size:`) — confined to `cli/harness.py` plus `logs.py`'s fixture round-trip, docs, and tests, after D3 (no evaluator signature widening) and D4 (persistence deferred) removed the FSM executor, `evaluate()` dispatcher, `queue.py`, and the schema-migration surface. The remaining work is one file's flag/grade/report/snapshot changes plus a real-git e2e test.
- **Risk**: Low — additive by construction (existing stdout-only grading keeps working when no new channel is declared, AC2 pins it). The per-channel 4000-char budget (D3) interacting with `evaluate_llm_structured()`'s own truncation (`fsm/evaluators.py:1100`) was flagged in 2026-09-14 verification as a real defect (the outer truncation would silently drop earlier channels) and resolved the same day by giving `evaluate_llm_structured()` an additive `max_output_chars` param so `_grade()`'s composed string isn't re-truncated — AC10 covers it. Moving `--require-artifact`/`--forbid-path` between flag helpers changes their subparser membership, but they had no enforcement or tests to break.
- **Breaking Change**: No — existing `--semantic` runs with no declared channel keep evaluating `result.stdout` alone. `--require-artifact`/`--forbid-path` go from inert to enforced; any existing invocation passing them (none found in-repo) would start failing on missing artifacts, which is the documented intent of the flag.

## Verification Notes

Verdict at time of check (2026-09-14, this pass): **NEEDS_UPDATE** (corrections
below applied in the same pass, so the issue as it now reads is up to date — this
section is a record of what was wrong and fixed, not an outstanding action item).
Evidence-quote check (`ll-verify-evidence`) and required-decisions-rule check both
came back clean (no active required rules in the decisions log); graph=`codegraph`
freshness=`fresh`. B6 proposal-vs-code consequence check: no `PROPOSAL_UNSOUND`
finding — D5's snapshot/check placement (wrapping the four `_invoke()` calls plus
`cmd_dsl`'s per-task action, with `_run_sample_loop()` calling snapshot/check
inline around its own `invoke()`) matches the real shape of `_run_sample_loop()`
(:1533-1556+) and `_run_baseline_phase()` (:1380); `_run_baseline_phase()`'s broad
`try/except Exception` around its `_run_sample_loop()` call would swallow a raised
exception, but D5 already designs the snapshot/check functions to fail closed into
a `ChannelRecord(note=...)` rather than raise, so no incompatibility exists.

Corrected in this pass (2026-09-14, this verify-issues run):
- D1 and Implementation Steps step 1 both cited `cmd_dsl`'s per-task
  `argparse.Namespace` build at `harness.py:2331-2340` "copying only seven
  fields." Direct read: the actual block is `harness.py:2328-2337` and copies
  **eight** fields (`target`, `exit_code`, `semantic`, `timeout`, `output`,
  `verbose`, `model`, `issue_id`). The substance (four new flags still need
  copying in) was already correct — only the line range and field count were
  wrong; both citations corrected.
- D3's docstring-line citation for `evaluate_llm_structured()`'s `output:` line
  (`fsm/evaluators.py:1082`) had drifted one line to `:1083`; corrected.
- The `porcelain_paths()` citation (`git_operations.py:552`, appearing twice —
  once in D5, once in Program Design's "Conventions in Force") had drifted one
  line to `:551`; both corrected.

Corrected in the prior pass (2026-09-14T18:46:52):
- Current Behavior / Integration Map claimed `_add_trace_flags()` is "attached only
  to `skill_p`/`prompt_p`." Direct read confirms it is attached only to `skill_p`
  (harness.py:702) — `prompt_p` gets `_add_evaluator_flags()` only. AC11's "remain
  skill/prompt-only" corrected to "remain skill-only" for the same reason.
- Integration Map cited a `cli/queue.py::_run_loop_action` function that does not
  exist; the actual function constructing `RunnerResult` directly is
  `_run_loop_entry` (:382-433) — same location/behavior otherwise, name only.
- `docs/reference/API.md` citations had drifted another ~20-22 lines since the
  2026-09-13 refine pass (`:6228-6237`→`:6250-6258`, `:6244-6249`→`:6266-6272`,
  `:9601`→`:9623`); the staleness claims themselves (stale `timeout: int = 30`,
  missing `model` param, stuck-at-v45 `SCHEMA_VERSION` comment) are still accurate.
- AC13 checked: ENH-3476 exists (`blocked_by: ENH-3462`, parent EPIC-3475) and is
  linked from this issue's Session Log, satisfying the AC.
- **D3's truncation strategy, flagged as unsound in this pass, resolved same-day.**
  `evaluate_llm_structured()`'s own truncation (`fsm/evaluators.py:1100`) is a
  keep-last-4000-chars slice of the *whole* `output` string, not per-tag — a
  `_compose_judge_evidence()` string where each channel is already capped at 4000
  chars but the combined string exceeds 4000 would have that second, outer
  truncation silently drop the earlier channel's tag(s) entirely, directly
  threatening AC10. Decision: `evaluate_llm_structured()` gains an additive,
  keyword-only, default-preserving `max_output_chars: int = 4000` param (default
  unchanged, so every other caller — `FSMExecutor._evaluate()`, `cli/queue.py`,
  FSM loops — stays byte-identical); `_grade()` passes it a value that covers the
  full composed length (or `None`) since it has already applied the per-channel
  budget itself. Rejected alternative: capping the *total* composed length to
  ≤4000 across channels — this would have defeated the per-channel-cap intent
  (the more channels declared, the less of each reaches the judge) and required
  rewriting AC10. Applied to D3, the "Not touched" list in the Wiring Phase, the
  Program Design Signatures/New-types sections, the Risk line in Impact, and
  Scope Boundaries in this pass. This is now the only touch to
  `evaluate_llm_structured()`'s signature anywhere in this issue's scope.

## Session Log
- `/ll:verify-issues` - 2026-09-14T19:19:41 - `708ccabe-e639-4624-a706-2da95f048b50.jsonl`
- review pass (manual) - 2026-09-14 - second pre-implementation review: D5 git snapshot must not reuse `_git_dirty()` (its `--untracked-files=no` contradicts AC5); `--require-artifact` touched-check adds `st_mtime_ns` (sha256 alone false-fails byte-identical rewrites under `--samples`); `invoke` callable contract kept 2-tuple (`_run_sample_loop`/`_run_baseline_phase` untouched, snapshot/check inline in the loop); D2 `to_dict()` emits `chars` not `content`; new D10 `getattr` rule + AC14; cwd/run-from-project-root note; `evaluate_llm_structured` docstring update; two Program Design bullets marked superseded by D1/D2
- `/ll:confidence-check` - 2026-09-14T19:04:11 - `90921241-8f93-4ac8-825a-1666912c6844.jsonl`
- review pass (manual) - 2026-09-14 - pre-implementation review: fixed snapshot placement (wraps invoke, not `_evaluate_and_report()`; dsl `task_args` copies new flags; D9 per-task); `--require-artifact` now requires created-or-modified (stale-artifact hole); `--expect-git-clean` → `--expect-no-git-changes` with pre-dirty content digests; `--evidence` additive (stdout always on); D3 composition rule reconciles AC1/AC2 (raw stdout under default declaration); `max_output_chars: int | None`; keep-last truncation; forbid-path dir semantics; ARCHITECTURE-017 amendment; ACs 1–5, 8–11 updated
- review pass (manual) - 2026-09-14 - amended D3 per verify-issues finding: `evaluate_llm_structured()` gains additive `max_output_chars` param so `_grade()`'s composed multi-channel string isn't re-truncated (AC10 fix); applied across D3, Wiring "Not touched", Program Design, Impact/Risk, Scope Boundaries
- `/ll:verify-issues` - 2026-09-14T18:46:52 - `2b263489-0fde-43e6-b776-33707f05f579.jsonl`
- review pass (manual) - 2026-09-14 - AC13: created ENH-3476 (persist `outcome.channels`/side-effect results to `harness_events`) under EPIC-3475, blocked-by this issue
- review pass (manual) - 2026-09-14 - resolved D1–D8, added Acceptance Criteria, pruned wiring per decisions, cleared stale `verify_verdict: NON_VALID` (re-run `/ll:verify-issues` to re-derive), size Very Large → Large
- `/ll:wire-issue` - 2026-09-14T18:08:39 - `2c4c9b5c-4176-4456-8fbd-bcd820d953fc.jsonl`
- `/ll:refine-issue` - 2026-09-14T17:57:00 - `ed6df677-344b-44cd-8920-d8f25b2d204a.jsonl`
- `/ll:audit-issue-conflicts` - 2026-09-13T21:28:46 - `23df08cc-836b-4f77-a1e2-bfb5aedb0f55.jsonl`
- `/ll:refine-issue:gap-analysis` - 2026-09-13T20:01:33 - `ba1e78b0-d003-48c9-ad54-d85428e37f7d.jsonl`
- `/ll:wire-issue` - 2026-09-13T19:41:39 - `a869cc2b-c93b-4b9c-afec-ff74a5703ae9.jsonl`
- `/ll:refine-issue` - 2026-09-13T19:26:36 - `021c5145-df0e-49c1-af9a-18ee5ea0a32b.jsonl`

## Scope Boundaries

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-13 — based on codebase analysis:_

- **In scope**: widening `_grade()`/`_evaluate_and_report()` (`harness.py`) to treat `result.stderr` as a distinct, declarable judge channel; making a declared-written file's content available as judge evidence; making named side effects assertable (`--require-artifact` touched by the run per sha256 or `st_mtime_ns`, `--forbid-path` byte-identical, `--expect-no-git-changes` no new porcelain paths (untracked included) and no further-modified pre-dirty paths via a pre/post snapshot — **not** `_git_dirty()`'s boolean or its `--untracked-files=no` call, which stay descriptive); and an in-memory `channels` record on the outcome that distinguishes unexamined from examined-and-empty (D1–D10).
- **In scope (pulled in by D1)**: enforcing the previously inert `--require-artifact`/`--forbid-path` flags and moving them to `_add_evaluator_flags()` so all five subparsers accept them. They are the declared-artifact mechanism; no parallel `--expect-file` flag.
- **Out of scope, adjacent**: `--trace-mode`/`--require-order`/`--keep-workspace` (`harness.py:639-688`, `runner_spec.py:196-230`) and `RunnerResult.tool_trace` — the trace-mode workspace path stays unreachable from the CLI and is a separate unit of work (D7).
- **Out of scope, adjacent**: `FSMExecutor._evaluate()`'s identical single-channel gap (`fsm/executor.py:3092-3116`) — a different action-result type, call site, and consumer. D3's `max_output_chars` addition to `evaluate_llm_structured()` is additive and default-preserving; `FSMExecutor._evaluate()`'s call path is unaffected, so this issue still does not touch it.
- **Out of scope, deferred to a child issue (D4)**: persisting `channels`/side-effect results to `harness_events` and everything downstream of that column (migration, manifest, DES variant, reader dataclass, doctor drift, migration-table docs).
- **Out of scope**: `loops/harness-optimize.yaml`'s benchmark-score capture reads `captured.benchmark_score.output` directly and never calls `ll-harness`/`_grade()` — not a consumer of this code path.

## Status

**Open** | Created: 2026-09-13 | Priority: P3
