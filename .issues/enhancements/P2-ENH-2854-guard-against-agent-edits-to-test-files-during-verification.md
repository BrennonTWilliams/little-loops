---
id: ENH-2854
title: Guard against agent edits to test files during verification
type: ENH
priority: P2
status: open
discovered_date: 2026-07-27
epic: EPIC-2856
parent: EPIC-2856
labels:
- rework
- verification
blocked_by:
- ENH-2865
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

## Integration Map

_Added by `/ll:refine-issue` — based on codebase analysis. No code implements this guard today; this is new machinery threaded through the FSM executor, config schema, and a new shared module._

### Files to Modify

_Rewritten 2026-07-30 (placement review) — split into a core plus two adapters so the guard reaches the non-FSM orchestrators. See Design Notes, "Gate placement."_

**Layer 1 — guard core (no FSM knowledge):**
- `scripts/little_loops/test_tamper_guard.py` (new) — snapshot / compare / revert over a changed-file set, parameterized by policy (`revert` | `fail` | `allow`). Consumes ENH-2865's `test_file_patterns` module for identification; includes the resolved pytest config files in the snapshot set per Design Notes. This is the single implementation both adapters call.

**Layer 2 — FSM adapter:**
- `scripts/little_loops/fsm/executor.py` — resolve the state-level `tamper_guard:` key (state over loop default) and hook snapshot-on-entry / compare-on-exit around the guarded state's execution. The stall-detector integration (~L1398-1429: `self._stall_detector.record`/`.check()` → abort-or-route, applied as a side-channel check independent of the main evaluator verdict) is the structural analog to follow; the main action-result → verdict wiring is ~L1326-1420, L1954-2010.
- `scripts/little_loops/fsm/definition.py` + `ll-loop validate` — declare and lint the `tamper_guard:` state key (WARN on an unrecognized value).
- `scripts/little_loops/fsm/evaluators.py` — `evaluate_diff_stall()` (L572-665) is the persistence idiom to copy: a prior snapshot cached under a key derived from `scope`. This guard needs the same cache-key/persistence shape but hashing test-file *content*, not `git diff --stat` output. Note `evaluate_exit_code()` (~L220) is what currently maps a test-run state's exit code to a verdict, and has no concept of "revert."

**Layer 3 — Python adapter (the `ll-auto` / `ll-parallel` / `ll-sprint` coverage fix):**
- `scripts/little_loops/work_verification.py` — call the guard core from the shared verification path. This module is already imported by `issue_manager.py:31` and `worker_pool.py:38`, and `verify_work_was_done()` (L44) already receives the changed-file set the guard needs. `filter_excluded_files()`/`EXCLUDED_DIRECTORIES` (L18-41) remains the inclusion/exclusion-predicate shape reference.
- `scripts/little_loops/issue_manager.py` (~L1052-1109, Phase 3) and `scripts/little_loops/parallel/worker_pool.py` (~L596, `_verify_work_was_done` L1212) — confirm the guard fires on both call sites; prefer inheriting it from `work_verification.py` over adding two independent hooks.
- `scripts/little_loops/config-schema.json` — the non-FSM policy default key (see Design Notes); `code_query.staleness` (~L1296) is the shape and location precedent.

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

### Tests
- FSM-schema test for the new `tamper_guard:` state key (decided location — loop YAML, not `config-schema.json`; the `project.test_patterns` schema test belongs to ENH-2865). Follow the existing per-key state-field tests around `fsm/definition.py`'s schema.
- `scripts/tests/test_codequery_codegraph.py:TestStalenessMatrix` — pattern to replicate for the `revert`/`fail`/`allow` policy matrix. Confirmed the only comparable 3-mode-policy test class in the codebase [Agent 3 finding].
- No existing test file covers this guard; a new file (e.g. `scripts/tests/test_test_file_tamper_guard.py`) is needed.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_builtin_loops.py:TestCodeRunGateOracle`, `TestCodeRunGateOracleWiring`, `TestVerifyStateConfigReadShell` — update if the guard's hook rewrites the `verify`/`code-run-gate` state `action` strings these tests assert on literally; confirmed no existing test in `test_rn_implement.py`/`test_builtin_loops.py` currently references tamper-guard concepts [Agent 3 finding].
- Config-schema round-trip note: no existing test performs strict `additionalProperties: false` jsonschema validation against a real config fixture (`test_config_schema.py`/`test_config.py`/`test_config_properties.py` all confirmed to use structural JSON-key assertions only) — adding `project.test_patterns` cannot break an existing round-trip test; only the new `test_test_patterns_in_schema`-style test needs writing [Agent 3 finding].

### Configuration
- `project.test_patterns` — owned by **ENH-2865** (schema entry, `ProjectConfig` field, per-template defaults, `CONFIGURATION.md` row). Consumed here; not defined here.
- The `revert` / `fail` / `allow` policy key **is** this issue's — decided: a state-level `tamper_guard:` key in loop YAML (with optional loop-level default), **not** a `config-schema.json` entry. `config-schema.json:code_query.staleness` (~L1296) remains the shape reference for a 3-mode enum with a default, consumed via branching as in `codequery/codegraph.py:CodegraphProvider.status()` (~L156-224); the FSM schema (`fsm/definition.py` / `ll-loop validate`) is where the key is declared and linted.

### Documentation
_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CONFIGURATION.md` — the `### project` table's `test_patterns` row (including the deliberate-non-introspection note about `_COMMAND_FIELDS`) is written by **ENH-2865**; this issue adds only the new `revert`/`fail`/`allow` tamper-guard policy key's row to the same table (~L294-305), in the same shape.

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
  `test_file_patterns.py` module — all owned by **ENH-2865**, consumed here.
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
- **Risk**: Low technical risk (deterministic, no LLM calls, git-based revert has a direct precedent in `worker_pool.py`). The main risk is scope creep into ENH-2865's `project.test_patterns` ownership or ENH-2853's pre-patch check ordering — both are explicitly bounded in Design Notes.

## Acceptance Criteria

- [ ] Test files are snapshotted at verification-step start (not issue start) and compared after it; a TDD-mode run whose implement phase added tests does not trip the guard.
- [ ] The policy is declared as a state-level `tamper_guard: revert | fail | allow` key in loop YAML (optional loop-level default, state wins); presence of the key is what marks a state as guarded — no separate verify-step event and no project-global config key.
- [ ] `ll-loop validate` warns on an unrecognized `tamper_guard` value.
- [ ] Test discovery goes through ENH-2865's shared `test_file_patterns` module / `project.test_patterns` key, not a hardcoded list defined here.
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


## Status

**Open** | Created: 2026-07-27 | Priority: P2

## Session Log
- gate-placement review (manual, no skill) - 2026-07-30 - rewrote `### Files to Modify` into core/FSM-adapter/Python-adapter layers, added Design Notes "Gate placement" + non-FSM policy-default decision, 6 ACs, 1 Impact note
- `/ll:format-issue` - 2026-07-27T20:01:34 - `74d428f0-7103-4a58-9168-ff504878fb04.jsonl`
- `/ll:audit-issue-conflicts` - 2026-07-27T19:42:08 - `e2303183-4e52-4649-af90-4b53254bbda4.jsonl`
- `/ll:wire-issue` - 2026-07-27T17:06:41 - `addc0661-0c81-4c9b-99bf-77c7e6079b2c.jsonl`
- `/ll:refine-issue` - 2026-07-27T16:32:16 - `72c3b345-e826-4b46-a5ba-58f62b13e67c.jsonl`
