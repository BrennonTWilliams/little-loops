---
id: ENH-2854
title: Guard against agent edits to test files during verification
type: ENH
priority: P2
status: done
discovered_date: 2026-07-27
epic: EPIC-2856
parent: EPIC-2856
labels:
- rework
- verification
confidence_score: 100
outcome_confidence: 58
score_complexity: 10
score_test_coverage: 18
score_ambiguity: 20
score_change_surface: 10
size: Very Large
completed_at: '2026-07-31T03:25:32Z'
---

# ENH-2854: Guard against agent edits to test files during verification

Origin: ll-product #ENH-052

## Summary

Any loop that uses a green test suite as a transition predicate can be satisfied by editing or commenting out the tests instead of fixing the code. Detect agent modifications to test files across a verification step and either revert them before scoring or fail the transition.

The natural host is the embedded-verification-in-FSM-transitions mechanism (ll-product #ENH-025 — not this repo's local ENH-025, which is unrelated), which currently does not address tamper detection.

## Motivation

"Make the tests pass" is a reward an agent can collect by weakening the tests. Deleting an assertion, commenting out a case, loosening a comparison, or adding a skip marker all turn a suite green without touching the defect. Where a loop treats suite status as a transition predicate, this converts a verification gate into a no-op — and it is invisible in the loop's own telemetry, because from the harness's point of view the tests passed.

Detecting it is mechanical: diff the test files across the step and compare against what the agent was authorized to change.

## Current Behavior

A verification step that gates a transition on suite exit code has no way to distinguish "the code was fixed" from "the tests were weakened." An agent can comment out an assertion, add a skip/xfail marker, loosen a comparison, or delete a test file, and the suite still reports green. The harness's own telemetry shows the step passing — the tamper is invisible from the loop's point of view.

## Expected Behavior

A verification step declaring `tamper_guard:` snapshots test-file content hashes at step start and compares them at step end. Any modification, deletion, or newly-skipped test file is reported in the run's verification evidence, and the configured policy (`revert`, `fail`, or `allow`, default `fail`) determines whether the transition proceeds.

## Proposed Solution

1. **Snapshot** test-file state at the start of a verification step (content hashes over the paths matching the project's test patterns).
2. **Compare** at the end of the step. Any modified, deleted, or newly-skipped test file is a tamper candidate.
3. **Policy** — carried by a state-level `tamper_guard:` key in loop YAML (see Design Notes); **default is `fail`** (decided, epic review 2026-07-27 — least surprising: a guard silently rewriting files mid-run is confusing in telemetry; `revert` is an explicit opt-in for loops wanting score-the-code-alone semantics):
   - `revert` — restore test files to their pre-step state, then score. Scoring then reflects the code change alone.
   - `fail` — fail the transition and report which files were touched.
   - `allow` — permit the edits but record them prominently in the run's evidence (for steps whose *purpose* is editing tests).
4. **Report** — the set of touched test files, and the nature of each change, lands in the verification evidence for the run regardless of policy.

## Design Notes

- Test-file identification should reuse the project's existing test discovery configuration rather than hardcoding a pattern; a false negative here (a test file the guard doesn't know about) is the failure mode that matters.
- Detect weakening that is not a file modification too, where cheap: newly added skip/xfail markers and removed assertions are the common shapes. Content hashing catches all of these as "modified"; the report should say *which* if it can, but the guard's correctness does not depend on classifying them.
- Some legitimate steps modify tests — an issue whose whole point is fixing a broken test. That is what `allow` is for; it must be an explicit per-loop opt-in, never the default and never inferred.
- Deterministic only. No LLM judgment about whether an edit was "reasonable".
- **Scope the guard to the verification step, not the whole issue run.** With `commands.tdd_mode: true`, the implement phase legitimately writes tests before code. The snapshot is taken at *verify-step start*, never at issue start — otherwise every TDD run trips the guard. Make this boundary explicit in the implementation and tests.
- **Ordering with ENH-2853 is a constraint, not a dependency** (clarified at epic review, 2026-07-27 — the two issues previously carried a circular `blocked_by`). `revert` must not destroy ENH-2853's evidence: where both are present, the pre-patch check reads the step's diff *before* any revert is applied. `revert` applies only to modifications/deletions of tests that existed at verify-step start; a test file newly added during the verification step is never "reverted" (deleted) by this guard — it is handed to ENH-2853's pre-patch check, which is the correct arbiter for new tests. This guard must be fully functional and testable with ENH-2853 absent.
- **Both open design questions are decided (2026-07-27): a state-level `tamper_guard:` key in loop YAML answers them together.** (1) *Where the policy lives*: on the FSM state, as `tamper_guard: revert | fail | allow` — not a project-global `config-schema.json` key. The guard's scope is "this verification step," so its policy belongs to the state, matching how other per-state behavior (`model:`, `session_mode:`, `pruning_profile:`) is declared; the `strict`/`warn`/`off` enum in `code_query.staleness` remains the *shape* precedent (3-mode enum with a default), not the *location* precedent. (2) *What marks a verification step*: presence of the key. The snapshot is taken when a `tamper_guard`-bearing state is entered and compared when it exits — no new FSM-level "verify-step start" event or inference is needed, and a state without the key gets no guard. A loop-level `tamper_guard:` default that states inherit (same pattern as `pruning_profile`) is an acceptable convenience; the executor resolves state-over-loop. `ll-loop validate` should WARN on an unknown value. The `project.test_patterns` config key, its per-project-type template defaults, and the shared `scripts/little_loops/test_file_patterns.py` module land there and are consumed here — not defined by this issue. A false negative in identification is this guard's worst failure mode, which is exactly why it has one owner.
- **Gate placement: the state-level key is right, but it covers only the FSM half of the surface** (placement review, 2026-07-30). `tamper_guard:` as an FSM state key is the correct primitive — declarative, per-state, lintable by `ll-loop validate`, inheriting the `pruning_profile` state-over-loop resolution. Keep it. But it reaches only loops, and `ll-auto` never enters the FSM to verify:
  - `issue_manager.py`'s Phase 3 (L1052-1109) verifies in plain Python via `verify_issue_completed()` and `verify_work_was_done()`. No FSM state is entered, so no `tamper_guard:` key can apply.
  - `worker_pool.py:596` → `_verify_work_was_done()` (L1212) does the same for `ll-parallel`, and `ll-sprint` inherits it via the shared `ParallelOrchestrator`.
  - **`work_verification.py` is the shared non-FSM chokepoint, not merely a shape reference.** Both orchestrators already import it (`issue_manager.py:31`, `worker_pool.py:38`), and `verify_work_was_done()` already receives the changed-file set — which is exactly this guard's input. The Integration Map previously listed it under "Files to Modify" for its `filter_excluded_files()` inclusion/exclusion *analogy*; it is in fact the install site for the CLI half of the guard.
  - **Adopt the learning-test gate's three-layer shape**: a policy-parameterized core with no FSM knowledge, an FSM adapter (the `tamper_guard:` key, hooked in `executor.py` beside the stall-detector side-channel at ~L1398-1429), and a Python adapter called from `work_verification.py` so `ll-auto` / `ll-parallel` / `ll-sprint` inherit it. This mirrors `ready-to-implement-gate.yaml` + `learning_tests/gate.py` + the three orchestrator hooks behind one shared flag.
- **The non-FSM path needs a policy default source — this is the one justified `config-schema.json` key** (placement review, 2026-07-30). Design Notes previously ruled out a project-global config key categorically. That decision is correct *for FSM states* (the policy belongs to the state whose scope it describes) but leaves `ll-auto`'s Python verification path with no policy source at all, since there is no state to carry the key. Resolve it as a precedence chain: state-level `tamper_guard:` wins inside loops; a project-global config key supplies the default for the non-FSM path (and as the loop-level fallback); the built-in default remains `fail`. The `code_query.staleness` 3-mode-enum-with-default shape (`config-schema.json` ~L1296) is now both the shape *and* the location precedent for that key.
- **Config-level tamper is the guard's blind spot — close it in the snapshot set** (added 2026-07-29). Hashing only files matching `project.test_patterns` misses the cheapest green-suite attack that touches no test file at all: editing pytest configuration — `addopts = --deselect ...` or `-k "not slow"` in `pytest.ini` / `pyproject.toml [tool.pytest.ini_options]` / `tox.ini`, `collect_ignore` outside `conftest.py`, or `--ignore` in an invoked script. The snapshot set must therefore include the *resolved pytest config files* (whichever of `pytest.ini`, `pyproject.toml`, `tox.ini`, `setup.cfg` pytest actually reads for the run) alongside the test-pattern-matched files. These are few, cheap to hash, and almost never legitimately edited during a verification step; treat them under the same policy as test files and name them separately in the report so a config change is visibly a config change.

## Program Design

_Added by `/ll:refine-issue` (2026-07-30 pass) — the Program Design gate (ENH-2852)
flagged this section as missing (see Confidence Check Notes below)._

### Types

- `TamperPolicy = Literal["revert", "fail", "allow"]`
- `TamperFinding`: dataclass — `path: str`, `kind: Literal["modified", "deleted", "added"]`, `is_config: bool`
- `TamperSnapshot = dict[str, str | None]` — path → sha256, `None` for a path that is missing/unreadable at snapshot time
- `TamperReport`: dataclass — `policy: TamperPolicy`, `findings: list[TamperFinding]`, `reverted: list[str]`, `passed: bool`

### Signatures

- `snapshot_test_paths(paths: list[str], repo_root: Path) -> TamperSnapshot`
- `compare_snapshots(before: TamperSnapshot, after: TamperSnapshot) -> list[TamperFinding]`
- `resolved_pytest_config_paths(repo_root: Path) -> list[str]`
- `apply_tamper_policy(policy: TamperPolicy, findings: list[TamperFinding], repo_root: Path) -> TamperReport`
- `run_tamper_guard(changed_files: list[str], config: BRConfig, policy: TamperPolicy, repo_root: Path) -> TamperReport`

### Call Path

FSM adapter (state-level `tamper_guard:` key): `StateConfig` → `executor._execute_state` →
`run_tamper_guard` → `filter_test_files` → `snapshot_test_paths` (on state entry) →
`compare_snapshots` (on state exit) → `apply_tamper_policy`.

Python adapter (`ll-auto` / `ll-parallel` / `ll-sprint`): `verify_work_was_done` →
`run_tamper_guard` → `filter_test_files` → `snapshot_test_paths` → `compare_snapshots` →
`apply_tamper_policy`.

`apply_tamper_policy`'s `revert` branch reuses `_cleanup_leaked_files`'s tracked-vs-untracked
git split; `snapshot_test_paths`'s hashing reuses `_sha256_file`'s shape (both cited in
Similar Patterns below). `BRConfig` is the config object `filter_test_files` and
`run_tamper_guard` both read `project.test_patterns` from.

## Integration Map

_Added by `/ll:refine-issue` — based on codebase analysis. No code implements this guard today; this is new machinery threaded through the FSM executor, config schema, and a new shared module._

### Codebase Research Findings

_Added by `/ll:refine-issue` (2026-07-30 pass) — the `blocked_by: ENH-2973` edge above has been removed: ENH-2973 completed 2026-07-28, so the dependency is resolved, not just unblocked._

- **ENH-2973's module now exists and is directly consumable**: `scripts/little_loops/test_file_patterns.py` (55 lines) exports `is_test_file(path: str, config: BRConfig | None = None) -> bool` and `filter_test_files(paths: list[str], config: BRConfig | None = None) -> list[str]`, both reading `config.project.test_patterns` and matching via `little_loops.git_operations.file_matches_pattern`. Both are pure/deterministic (no git calls, no filesystem stat). The guard core should call `filter_test_files()` directly rather than re-deriving test-file membership.
- **State-key declaration site correction**: the Integration Map's "Layer 2" entry above names `scripts/little_loops/fsm/definition.py` for declaring the `tamper_guard:` state field — this is wrong. The `StateConfig` dataclass (where `model:`, `session_mode:`, `pruning_profile:` are declared, ~L677-690) actually lives in `scripts/little_loops/fsm/schema.py` (~L570-699); the JSON Schema counterpart is `scripts/little_loops/fsm/fsm-loop-schema.json` (state-level string props ~L567-572, loop-level default + `_ok` suppression flag ~L354-358).
- **A closer WARN-validator template than the learning-gate analogy**: `scripts/little_loops/fsm/validation/evaluator_rules.py:450-496`, `_validate_session_mode_evaluator_inheritance()`, is the exact recipe for "declare a bare `str | None` state field, enforce its enum only in the validation layer, WARN on misuse, gate the rule behind a suppression flag." The suppression-flag allowlist is `scripts/little_loops/fsm/validation/_base.py` (~L120-122, `pruning_profile_ok`/`session_mode_ok`); a `tamper_guard_ok` flag needs registering there. Hook the new validator into the pipeline the same way `_validate_pruning_profile()` is wired in `scripts/little_loops/fsm/validation/structural_rules.py` (~L1082), and register it for import in `scripts/little_loops/fsm/validation/__init__.py` (which also maintains the running MR-rule-code docstring registry — add an entry there per this repo's own convention).
- **Reusable content-hashing utility, not previously cited**: `scripts/little_loops/codequery/codegraph.py` already has a snapshot-vs-current-bytes comparator: `_sha256_file()` (~L140-146, `hashlib.sha256(path.read_bytes()).hexdigest()`, `None` on `OSError`) and `_content_aware_head_moved()` (~L157-185, builds a `{path: sha256}` baseline dict and flags any path whose current hash differs or is missing). The guard core's snapshot/compare step should reuse this shape rather than writing file-hashing from scratch — it is the only existing content-hash-over-a-file-set comparator in the codebase (every other `hashlib` use in `scripts/little_loops/` is single-string cache-key hashing, e.g. `evaluate_diff_stall`'s `hashlib.md5(scope_str...)`).
- **Line-number drift in this issue's own citations** (confirmed against current code, all in `scripts/little_loops/`): `fsm/executor.py`'s stall-detector hook is actually at L1408-1439 (cited ~L1398-1429); `fsm/evaluators.py:evaluate_diff_stall()` actually runs L594-686 (cited ~L572-665, and the function extends past the cited end); `fsm/executor.py:_evaluate()` is at L1955 (cited L1954, negligible). `worker_pool.py:_cleanup_leaked_files()` (L1362), `work_verification.py:verify_work_was_done()` (L44), and `config-schema.json:code_query.staleness` (L1307-1312) are all confirmed exact. Re-verify line numbers at implementation time regardless — these will drift further before this issue is picked up.
- **`work_verification.verify_work_was_done()` signature confirmed**: `verify_work_was_done(logger: Logger, changed_files: list[str] | None = None, baseline_sha: str | None = None) -> bool`. When `changed_files` is `None` (the `ll-auto` path), it derives the set itself from three sequential `git diff` calls (uncommitted, staged, committed-since-`baseline_sha`) — this is the natural point for the Python adapter to intersect the changed-file set against `filter_test_files()` before deciding revert/fail/allow. `issue_manager.py`'s two call sites needing the hook are confirmed at L1072 and L1109 (Phase 3 spans L1049-1129, not L1052-1109 as cited); `worker_pool.py`'s call site is confirmed exact at L596, with `_verify_work_was_done()` at L1212.

### Files to Modify

_Rewritten 2026-07-30 (placement review) — split into a core plus two adapters so the guard reaches the non-FSM orchestrators. See Design Notes, "Gate placement."_

**Layer 1 — guard core (no FSM knowledge):**
- `scripts/little_loops/test_tamper_guard.py` (new) — snapshot / compare / revert over a changed-file set, parameterized by policy (`revert` | `fail` | `allow`). Consumes ENH-2973's `test_file_patterns` module for identification; includes the resolved pytest config files in the snapshot set per Design Notes. This is the single implementation both adapters call.

**Layer 2 — FSM adapter:**
- `scripts/little_loops/fsm/executor.py` — resolve the state-level `tamper_guard:` key (state over loop default) and hook snapshot-on-entry / compare-on-exit around the guarded state's execution. The stall-detector integration (~L1398-1429: `self._stall_detector.record`/`.check()` → abort-or-route, applied as a side-channel check independent of the main evaluator verdict) is the structural analog to follow; the main action-result → verdict wiring is ~L1326-1420, L1954-2010.
- `scripts/little_loops/fsm/definition.py` + `ll-loop validate` — declare and lint the `tamper_guard:` state key (WARN on an unrecognized value).
- `scripts/little_loops/fsm/evaluators.py` — `evaluate_diff_stall()` (L572-665) is the persistence idiom to copy: a prior snapshot cached under a key derived from `scope`. This guard needs the same cache-key/persistence shape but hashing test-file *content*, not `git diff --stat` output. Note `evaluate_exit_code()` (~L220) is what currently maps a test-run state's exit code to a verdict, and has no concept of "revert."

**Layer 3 — Python adapter (the `ll-auto` / `ll-parallel` / `ll-sprint` coverage fix):**
- `scripts/little_loops/work_verification.py` — call the guard core from the shared verification path. This module is already imported by `issue_manager.py:31` and `worker_pool.py:38`, and `verify_work_was_done()` (L44) already receives the changed-file set the guard needs. `filter_excluded_files()`/`EXCLUDED_DIRECTORIES` (L18-41) remains the inclusion/exclusion-predicate shape reference.
- `scripts/little_loops/issue_manager.py` (~L1052-1109, Phase 3) and `scripts/little_loops/parallel/worker_pool.py` (~L596, `_verify_work_was_done` L1212) — confirm the guard fires on both call sites; prefer inheriting it from `work_verification.py` over adding two independent hooks.
- `scripts/little_loops/config-schema.json` — the non-FSM policy default key (see Design Notes); `code_query.staleness` (~L1296) is the shape and location precedent.

_Wiring pass added by `/ll:wire-issue` (2026-07-31):_
- `scripts/little_loops/config/core.py` — `ProjectConfig` (~L148-195: field/default declaration, `from_dict()` at ~L172-195, and the reverse-serialization block at ~L866-872) is the Python-side mirror `config-schema.json` keys are triple-declared against; a schema entry alone is not sufficient. If the new policy-default key lands under `project.*`, this dataclass needs the matching field/`from_dict`/serialization lines. If it instead mirrors `code_query.staleness` more literally as a sibling `CodeQueryConfig` field (`scripts/little_loops/config/features.py:834-847`), that dataclass needs them instead — either way, exactly one `scripts/little_loops/config/*.py` dataclass outside the files already listed needs a matching change [Agent 2 finding].
- `scripts/little_loops/config/core.py:912` — `BRConfig.resolve_variable()` (the method `ll-config get <key>` wraps, per `.claude/CLAUDE.md`'s `ll-config` entry) should be smoke-checked to confirm the new key resolves through it [Agent 2 finding].

### Dependent Files (Callers/Importers)
- `scripts/little_loops/loops/oracles/code-run-gate.yaml:run_test` (L201-249) — existing test-execution oracle state; likely host for the new snapshot/compare wrapping.
- `scripts/little_loops/loops/rn-implement.yaml`, `scripts/little_loops/loops/autodev.yaml` — loops whose verification steps use a green-suite predicate and would opt into this guard's policy.
- `skills/manage-issue/SKILL.md` (L184-186, L239), `skills/manage-issue/templates.md` (L130-133) — the only consumers of `commands.tdd_mode`, entirely prose/LLM-facing (a repo-wide grep of `loops/*.yaml` for `tdd_mode` returns zero matches). No FSM-level "verify-step start" event exists today — the guard's snapshot trigger is new instrumentation, not an existing hook to attach to.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_builtin_loops.py:TestCodeRunGateOracle`/`TestCodeRunGateOracleWiring` (~L9699, L12576-12668) and `TestVerifyStateConfigReadShell` (~L3714, `test_verify_reads_project_test_and_lint_cmd` L2789) — assert on the literal `verify`/`code-run-gate` state `action` string and topology; if the guard's snapshot/compare hook rewrites those action strings, these literal-string assertions break [Agent 3 finding].

### Similar Patterns
- `scripts/little_loops/parallel/worker_pool.py:_cleanup_leaked_files()` (L1362) — git-based revert distinguishing tracked (`git checkout -- <files>`) vs. untracked (`unlink()`) files; directly reusable shape for the `revert` policy.
- `scripts/little_loops/loops/test-coverage-improvement.yaml:revert` state (L186); `incremental-refactor.yaml` (L53, `git checkout -- .`); `harness-optimize.yaml` (L202, `git restore ${context.targets}`) — existing FSM-level revert precedents, but all are LLM-prompt-driven ("revert the files using..."), not deterministic — this guard must be deterministic per Design Notes, so these are shape references only.
- `scripts/little_loops/config-schema.json:code_query.staleness` (L1296) — exact 3-mode enum precedent (`strict`/`warn`/`off`, default `warn`) for the `revert`/`fail`/`allow` policy; consumed via branching in `scripts/little_loops/codequery/codegraph.py:CodegraphProvider.status()` (~L156-224).
- `scripts/tests/test_codequery_codegraph.py:TestStalenessMatrix` (L266), parametrized over policy — template for the three-policy test matrix. Helpers `_init_repo()`/`_git()`/`_commit_at()`/`_write_config()` (L56-213) build a real git repo in `tmp_path` rather than mocking subprocess — the established convention for file-change-detection tests in this codebase.
- `scripts/tests/test_config_schema.py:test_health_url_in_schema()` (L337-357) — exact template for asserting a new `project.*` key's presence, type, and default in `config-schema.json`.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_fsm_evaluators.py:TestDiffStallEvaluator` (~L1461-1610), exercising `evaluate_diff_stall()` — the two-invocation "baseline call, then compare call" pattern (`test_first_iteration_returns_success` → `test_different_diff_returns_success` → threshold tests) maps directly onto snapshot-then-compare; its `clean_state_files` autouse fixture (L1474) and `test_dispatch_diff_stall` (L1581) evaluator-dispatch wiring test are the templates a new tamper-guard evaluator's tests should copy [Agent 3 finding].
- `scripts/little_loops/fsm/executor.py`'s stall-detector integration (~L1398-1429: `self._stall_detector.record`/`.check()` → abort-or-route, applied as a side-channel check independent of the main evaluator verdict) is the closest existing structural analog for how the tamper guard should hook into `_execute_state` [Agent 3 finding].

_Wiring pass added by `/ll:wire-issue` (2026-07-31):_
- `scripts/tests/test_fsm_executor.py:8680`, `TestStallDetector` — a stronger copy template than `TestCodeRunGateOracle` for the FSM hook specifically: it drives a real `FSMExecutor.run()` through a minimal `FSMLoop`/`StateConfig` fixture with a `MockActionRunner` and asserts on `result.terminated_by`/routed events, exercising the exact side-channel-near-`_execute_state` shape the tamper guard needs, rather than a whole-oracle-loop integration test [Agent 3 finding].
- `scripts/tests/test_fsm_validation_evaluator_rules.py:540`, `TestSessionModeEvaluatorInheritance` (testing `_validate_session_mode_evaluator_inheritance()`, `fsm/validation/evaluator_rules.py:450-496`) — the exact copy template for the new WARN validator's test class: an `_fsm(...)` fixture helper, `test_fires_for_*`/`test_does_not_fire_for_*` pairs, a `test_suppressed_by_<flag>_ok` case, and a `test_wired_into_validate_fsm` case asserting the rule fires through the top-level `validate_fsm()` aggregator, not just the private function [Agent 3 finding].
- `scripts/little_loops/fsm/fsm-loop-schema.json`'s `stateConfig` definition (starts ~L403) sets `additionalProperties: false` (confirmed ~L652) — the same drift risk `test_fsm_schema.py:261-277`'s `test_schema_json_evaluate_config_properties_match_dataclass_fields` (ENH-2896) was added to catch for `EvaluateConfig`. A `tamper_guard` field added to `StateConfig` (`fsm/schema.py`) but omitted from `stateConfig.properties` would be silently rejected by schema validation with no existing test catching it — the state-config equivalent of that lockstep test should be added alongside this issue's own schema change [Agent 3 finding].

### Tests
- FSM-schema test for the new `tamper_guard:` state key (decided location — loop YAML, not `config-schema.json`; the `project.test_patterns` schema test belongs to ENH-2973). Follow the existing per-key state-field tests around `fsm/definition.py`'s schema.
- `scripts/tests/test_codequery_codegraph.py:TestStalenessMatrix` — pattern to replicate for the `revert`/`fail`/`allow` policy matrix. Confirmed the only comparable 3-mode-policy test class in the codebase [Agent 3 finding].
- No existing test file covers this guard; a new file (e.g. `scripts/tests/test_test_file_tamper_guard.py`) is needed.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_builtin_loops.py:TestCodeRunGateOracle`, `TestCodeRunGateOracleWiring`, `TestVerifyStateConfigReadShell` — update if the guard's hook rewrites the `verify`/`code-run-gate` state `action` strings these tests assert on literally; confirmed no existing test in `test_rn_implement.py`/`test_builtin_loops.py` currently references tamper-guard concepts [Agent 3 finding].
- Config-schema round-trip note: no existing test performs strict `additionalProperties: false` jsonschema validation against a real config fixture (`test_config_schema.py`/`test_config.py`/`test_config_properties.py` all confirmed to use structural JSON-key assertions only) — adding `project.test_patterns` cannot break an existing round-trip test; only the new `test_test_patterns_in_schema`-style test needs writing [Agent 3 finding].

_Wiring pass added by `/ll:wire-issue` (2026-07-31):_
- `scripts/little_loops/git_operations.py:15-18` re-exports `verify_work_was_done` (`from little_loops.work_verification import (... verify_work_was_done, ...)  # noqa: F401`) for backward compatibility. Three distinct import/patch surfaces now resolve to it: `little_loops.work_verification.verify_work_was_done`, `little_loops.git_operations.verify_work_was_done` (used directly by `scripts/tests/test_subprocess_mocks.py:~451-545`, 7 test cases), and `"little_loops.issue_manager.verify_work_was_done"` (the name patched in `scripts/tests/test_issue_manager.py:~2632-2932`, 6+ call sites). Existing tests that patch `verify_work_was_done` wholesale will bypass the new `run_tamper_guard` call path entirely — tamper-guard-specific tests must patch/exercise `run_tamper_guard` (or its call site inside `verify_work_was_done`), not stub `verify_work_was_done` itself, or they silently don't exercise the guard [Agent 2 finding].
- `scripts/tests/test_worker_pool.py:1316-1350` — four existing direct unit tests of `_verify_work_was_done` (`test_verify_work_was_done_accepts_code_changes`, `_rejects_no_changes`, `_rejects_excluded_only`, `_respects_config`) not previously listed under Tests; these operate on a pre-collected `changed_files` list plus exclusion/config checks (distinct from `work_verification.verify_work_was_done`'s git-diff detection) and are the existing coverage the Python adapter's worker_pool hook extends [Agent 3 finding].
- `scripts/tests/test_work_verification.py:512-539`, `TestVerifyWorkWasDoneIntegration` — the existing integration-style test class (mocks `subprocess.run`, calls `verify_work_was_done` end-to-end) where a tamper-guard-tripped scenario (a diff touching only test-pattern-matched files) should be added [Agent 3 finding].
- `scripts/tests/test_config_schema.py:359`, `test_project_test_patterns_in_schema` — a second worked example immediately following `test_health_url_in_schema` (L337), giving two consecutive templates for the new policy-key schema-presence test [Agent 3 finding].

### Configuration
- `project.test_patterns` — owned by **ENH-2973** (schema entry, `ProjectConfig` field, per-template defaults, `CONFIGURATION.md` row). Consumed here; not defined here.
- The `revert` / `fail` / `allow` policy key **is** this issue's — decided: a state-level `tamper_guard:` key in loop YAML (with optional loop-level default), **not** a `config-schema.json` entry. `config-schema.json:code_query.staleness` (~L1296) remains the shape reference for a 3-mode enum with a default, consumed via branching as in `codequery/codegraph.py:CodegraphProvider.status()` (~L156-224); the FSM schema (`fsm/definition.py` / `ll-loop validate`) is where the key is declared and linted.

### Documentation
_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CONFIGURATION.md` — the `### project` table's `test_patterns` row (including the deliberate-non-introspection note about `_COMMAND_FIELDS`) is written by **ENH-2973**; this issue adds only the new `revert`/`fail`/`allow` tamper-guard policy key's row to the same table (~L294-305), in the same shape.

_Wiring pass added by `/ll:wire-issue` (2026-07-31):_
- `docs/guides/LOOPS_GUIDE.md` — every other state-level key (`model:`, `pruning_profile:` L606-636, `session_mode:` L640-662) gets its own prose subsection with a YAML example and a cross-reference to the validator that lints it. This is distinct from the `CONFIGURATION.md` row (which documents the *config default*, not the *loop-YAML key*) — a new `tamper_guard:` subsection following the `pruning_profile:`/`session_mode:` pattern is needed here [Agent 2 finding].
- `docs/reference/API.md` — the `## little_loops.X` module index table (~L33) needs a row for the new `little_loops.test_tamper_guard` module (every other module gets one); the existing `## little_loops.work_verification` section (~L2293-2364) documents `verify_work_was_done`'s signature literally and goes stale if the Python adapter changes it; `### ProjectConfig` (~L386-406) reproduces the dataclass field list verbatim with `# ENH-NNNN` provenance comments and needs a new field row (with `# ENH-2854`) if the policy-default key lands on `ProjectConfig` [Agent 2 finding].
- `docs/reference/CLI.md:761-787` (`ll-loop validate` rule catalog) and the consolidated suppression-flag sentence at `docs/reference/CLI.md:779` — need a new entry for the tamper-guard WARN validator and its `tamper_guard_ok` suppression flag, in addition to the `.claude/CLAUDE.md` rule table already implied by this repo's own convention [Agent 2 finding].
- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md:313,326` — the guide's own MR-rule-code summary strings need the new validator folded in if it's given an MR code, or explicitly left out (matching how `session-mode-eval`/`pruning_profile`/`terminal-action-ok` are named-not-MR-coded) if it isn't [Agent 2 finding].

## Scope Boundaries

_Added 2026-07-30 (placement review) — the section was absent, though its
constraints were already stated across Design Notes._

**In scope:** the guard core (snapshot / compare / revert over test files plus
the resolved pytest config files); the FSM adapter (state-level `tamper_guard:`
key, its loop-level default, and its `ll-loop validate` lint); the Python
adapter hooked into `work_verification.py` so `ll-auto` / `ll-parallel` /
`ll-sprint` inherit the guard; the policy-precedence chain and the config key
that supplies the non-FSM default.

**Out of scope:**
- `project.test_patterns`, its schema entry, template defaults, and the shared
  `test_file_patterns.py` module — all owned by **ENH-2973**, consumed here.
- ENH-2853's pre-patch check. The two are peers with no dependency edge in
  either direction; the only interaction is ordering (`revert` runs after the
  pre-patch check has read the step's diff), and this guard must be fully
  functional and testable with ENH-2853 absent.
- Any LLM judgment about whether a test edit was "reasonable" — the guard is
  deterministic by design.
- Guarding non-test source files. The snapshot set is test files plus resolved
  pytest config files; general work verification stays `work_verification.py`'s
  existing job.

## Impact

- **Priority (P2)**: Not a correctness bug in shipped behavior — no loop is known to have been gamed this way in production — but it closes a gap in every green-suite transition predicate across `rn-implement.yaml`, `autodev.yaml`, and `code-run-gate.yaml`, so the blast radius of *not* having it grows with every new loop that adopts a test-gated transition.
- **Effort**: Medium — new snapshot/compare evaluator plus a state-level schema key, but it follows an existing structural analog (`evaluate_diff_stall()`, the stall-detector hook in `executor.py`) rather than inventing a new mechanism. _Revised 2026-07-30 (placement review): still Medium, but the scope now includes a second adapter — the `work_verification.py` hook covering `ll-auto`/`ll-parallel`/`ll-sprint` — plus the policy-precedence chain and its config key. Re-check the size estimate before implementation; if it scores Very Large, the FSM adapter and the Python adapter are a clean sequential split over a shared core._
- **Risk**: Low technical risk (deterministic, no LLM calls, git-based revert has a direct precedent in `worker_pool.py`). The main risk is scope creep into ENH-2973's `project.test_patterns` ownership or ENH-2853's pre-patch check ordering — both are explicitly bounded in Design Notes.

## Acceptance Criteria

- [ ] Test files are snapshotted at verification-step start (not issue start) and compared after it; a TDD-mode run whose implement phase added tests does not trip the guard.
- [ ] The policy is declared as a state-level `tamper_guard: revert | fail | allow` key in loop YAML (optional loop-level default, state wins); presence of the key is what marks a state as guarded — no separate verify-step event and no project-global config key.
- [ ] `ll-loop validate` warns on an unrecognized `tamper_guard` value.
- [ ] Test discovery goes through ENH-2973's shared `test_file_patterns` module / `project.test_patterns` key, not a hardcoded list defined here.
- [ ] The guard is functional and fully tested with ENH-2853 absent; where ENH-2853 is present, `revert` runs only after the pre-patch check has read the step's diff.
- [ ] Modified, deleted, and newly-added test files are all detected.
- [ ] The resolved pytest config files (`pytest.ini`, `pyproject.toml`, `tox.ini`, `setup.cfg` — whichever pytest reads for the run) are included in the snapshot set, and a config-only tamper (e.g. an added `--deselect`) trips the guard and is labeled as a config change in the report.
- [ ] `revert` policy restores pre-existing test files to their pre-step state before scoring; it never deletes a test file newly added during the step, and ENH-2853's pre-patch check (when present) runs on the diff before any revert.
- [ ] `fail` policy fails the transition and names the touched files.
- [ ] `allow` policy is opt-in per loop and still records the edits in the run evidence.
- [ ] The default policy is `fail` (decided); `revert` and `allow` are explicit per-loop opt-ins.
- [ ] Touched-file details appear in the run's verification evidence under every policy.
- [ ] The guard makes no LLM calls.
- [ ] Tests cover: commented-out assertion, added skip marker, deleted test file, untouched tests, and each of the three policies.

_Added 2026-07-30 (placement review) — see Design Notes, "Gate placement":_

- [ ] The guard core lives in its own module with no FSM imports; the `tamper_guard:` state key and the Python verification path both call that one implementation.
- [ ] The guard fires on the non-FSM verification path: an `ll-auto` run (`issue_manager.py` Phase 3) whose agent weakened a test trips the guard, with no FSM state involved. A test covers this path directly.
- [ ] The guard fires for `ll-parallel` / `ll-sprint` workers via the same shared `work_verification.py` path, rather than a second hook maintained independently.
- [ ] Policy resolution follows a documented precedence chain: state-level `tamper_guard:` > loop-level default > project config key > built-in `fail`. A test covers each level winning over the one below it.
- [ ] The project-global config key exists solely to supply the default for the non-FSM path and the loop-level fallback; it never overrides an explicit state-level key.
- [ ] `revert` on the non-FSM path uses the same git tracked-vs-untracked handling as `worker_pool.py:_cleanup_leaked_files()` (L1362) rather than a second revert implementation.


## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-07-30_

**Readiness Score**: 95/100 → PROCEED (overridden — see Gaps to Address)
**Outcome Confidence**: 58/100 → LOW

### Gaps to Address
- Program Design gate (ENH-2852) forces `STOP — ADDRESS GAPS` regardless of aggregate score: this issue has no `## Program Design` section with concrete types/signatures/call path. The issue's `### Codebase Research Findings` and `### Files to Modify` sections already carry file:line-level detail, but the gate requires a dedicated, repo-resolvable Program Design section. Run `/ll:refine-issue` or `/ll:reconcile-issue` to populate it, or set `program_design_not_applicable: true` if judged genuinely inapplicable (unlikely here given the amount of new machinery — a guard core module, an FSM adapter, and a Python adapter — this issue introduces).

### Outcome Risk Factors
- Moderate cross-module depth: the guard core, the FSM adapter (executor.py hook + schema + validator), and the Python adapter (work_verification.py + two orchestrator call sites + a new config key) span ~8 files across three layers with a shared precedence chain — more surface than a single-site change, raising integration risk between the layers.
- No existing test file covers this guard yet (`scripts/tests/test_test_file_tamper_guard.py` is net-new); the issue cites strong structural analogs to copy (`TestStalenessMatrix`, `TestDiffStallEvaluator`) but the policy-precedence chain across state/loop/config-default/built-in levels is a new interaction surface those analogs don't individually cover.

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-07-30_

**Readiness Score**: 100/100 → PROCEED
**Outcome Confidence**: 58/100 → LOW

The Program Design gate (ENH-2852) that previously forced `STOP — ADDRESS GAPS`
now passes: the `## Program Design` section (types, signatures, call path) was
populated by the 2026-07-30 `/ll:refine-issue` pass, and `ll-issues format-check
ENH-2854 --format json` confirms both `program_design_nonspecific` and the
`missing`/`empty` Program Design entry are empty. All five readiness criteria
score full marks: no existing tamper-guard code (`grep -rn "tamper_guard"` across
`scripts/` returns nothing), the design follows verified structural precedents
(`StateConfig`'s `pruning_profile`/`session_mode` fields at `fsm/schema.py:685-690`,
the stall-detector side-channel hook at `fsm/executor.py:~1408-1439`, the
`code_query.staleness` 3-mode enum at `config-schema.json:1307`), ENH-2973's
`test_file_patterns.py` module and `work_verification.verify_work_was_done()`
are confirmed to exist with the cited signatures, and ENH-2853 is a peer with no
blocking dependency edge.

### Outcome Risk Factors
- Moderate cross-module depth: the guard core, FSM adapter (executor hook +
  schema + validator), and Python adapter (`work_verification.py` + two
  orchestrator call sites + a new config key) span roughly 8-10 code files
  across three layers plus a validation-suppression-flag registration and
  doc updates — more surface than a single-site change, raising integration
  risk between the layers even though each individual site follows a cited
  precedent.
- No existing test file covers this guard yet
  (`scripts/tests/test_test_file_tamper_guard.py` is net-new); the issue cites
  strong structural analogs to copy (`TestStalenessMatrix`,
  `TestDiffStallEvaluator`, `TestStallDetector`,
  `TestSessionModeEvaluatorInheritance`), but the policy-precedence chain
  across state/loop/config-default/built-in levels is a new interaction
  surface those analogs don't individually cover.

---

## Resolution

- **Status**: Decomposed
- **Completed**: 2026-07-30
- **Reason**: Issue too large for single session (size-review score 11/11,
  Very Large). The issue's own Impact section anticipated this: "if it
  scores Very Large, the FSM adapter and the Python adapter are a clean
  sequential split over a shared core."

### Decomposed Into
- ENH-2933: Tamper guard core - snapshot/compare/revert over test files
- ENH-2934: Tamper guard FSM adapter - state-level tamper_guard key
- ENH-2935: Tamper guard Python adapter - ll-auto/ll-parallel/ll-sprint coverage

## Status

**Done** | Created: 2026-07-27 | Priority: P2

## Session Log
- `/ll:issue-size-review` - 2026-07-31T03:22:37 - `8a99a216-98a4-4273-8b35-65acee67e859.jsonl`
- `/ll:confidence-check` - 2026-07-31T03:20:13 - `3a9377ba-111e-4b12-af5b-d51941552579.jsonl`
- `/ll:wire-issue` - 2026-07-31T03:17:19 - `6eefcd5c-eb60-4ad0-863d-5e903c51410f.jsonl`
- `/ll:refine-issue` - 2026-07-31T03:09:49 - `98f2371c-8850-4871-9e42-25d5c3dc25c1.jsonl`
- `/ll:confidence-check` - 2026-07-30T00:00:00 - `1e8905af-5b3f-4a28-9295-5acc3ad4a358.jsonl`
- `/ll:refine-issue` - 2026-07-31T02:28:34 - `567ffd0e-2852-4419-9e29-36ccbb071297.jsonl`
- gate-placement review (manual, no skill) - 2026-07-30 - rewrote `### Files to Modify` into core/FSM-adapter/Python-adapter layers, added Design Notes "Gate placement" + non-FSM policy-default decision, 6 ACs, 1 Impact note
- `/ll:format-issue` - 2026-07-27T20:01:34 - `74d428f0-7103-4a58-9168-ff504878fb04.jsonl`
- `/ll:audit-issue-conflicts` - 2026-07-27T19:42:08 - `e2303183-4e52-4649-af90-4b53254bbda4.jsonl`
- `/ll:wire-issue` - 2026-07-27T17:06:41 - `addc0661-0c81-4c9b-99bf-77c7e6079b2c.jsonl`
- `/ll:refine-issue` - 2026-07-27T16:32:16 - `72c3b345-e826-4b46-a5ba-58f62b13e67c.jsonl`

---

## Resolution

- **Status**: Decomposed
- **Closed**: 2026-07-31
- **Decomposed into**: ENH-2933, ENH-2934, ENH-2935

Work for ENH-2854 is now carried by its child issues; this parent was closed by rn-decompose.
