---
id: ENH-2328
title: 'Test-suite breadth: dedicated tests for incidental-only modules + executor
  coverage spot-check'
type: ENH
status: done
priority: P3
captured_at: '2026-06-26T22:35:39Z'
completed_at: '2026-06-28T04:44:19Z'
discovered_date: '2026-06-26'
discovered_by: capture-issue
labels:
- testing
- coverage
relates_to:
- ENH-2325
depends_on:
- ENH-2329
learning_tests_required:
- pytest
- hypothesis
confidence_score: 98
outcome_confidence: 84
score_complexity: 18
score_test_coverage: 22
score_ambiguity: 22
score_change_surface: 22
---

# ENH-2328: Test-suite breadth — dedicated tests for incidental-only modules

## Summary

Phase 2 (Breadth) of the test-suite quality remediation
(`thoughts/audits/2026-06-26-test-suite-audit.md`). Several non-trivial source
modules have only incidental coverage (exercised indirectly, never pinned by a
dedicated test of intent). Add dedicated `test_<module>.py` files for them, then
a coverage-guided spot-check of the genuinely uncovered branches in
`fsm/executor.py`.

Phase 1 (depth: vacuous-pass guard + integration layer + no-assert hardening) is
already complete (`scripts/tests/integration/`); this issue tracks Phase 2 only.
Phase 3 (maintainability) is tracked separately.

## Motivation

A module with only incidental coverage passes as long as its *callers* pass —
its own edge cases (long names, empty fields, error propagation) are never
asserted. That is exactly where regressions hide. The audit graded breadth as
otherwise excellent, so this is targeted gap-closing, not a broad rewrite.

## Current Behavior

No dedicated test module exists for these (audit findings M5 and L1):

- `cli/issues/show.py` (~509 loc) — **highest value**: summary-card formatting
  edge cases (long names, empty/missing fields) untested.
- `cli/parallel.py` (~290 loc) — worker spawn / cleanup / error propagation.
- `config/automation.py` (~283 loc) — rule-matching / false-positive logic.
- `dependency_mapper/formatting.py` (~296 loc) — graph-traversal edge cases
  (likely some indirect coverage via `test_dependency_mapper.py`'s 146 tests;
  confirm with coverage before adding).
- Smaller (L1): `worktree_utils.py` (~170 loc, highest value of this group),
  `decisions_sync.py` (~41 loc), `sft_formatter.py` (~56 loc), and the
  `analytics/` package (~295 loc, referenced incidentally in 11 test files).

`fsm/executor.py` (2,141 loc) is well covered for evaluator types and routing
(see audit §2), so the only remaining gap is specific uncovered branches inside
the file — not a systemic hole.

## Expected Behavior

- Each listed module has a dedicated `test_<module>.py` (or `test_analytics_*.py`
  for the package) asserting its own edge cases, not just smoke coverage.
- `fsm/executor.py` has tests added only for the branches a coverage report shows
  as genuinely uncovered (error/interpolation paths), avoiding redundant tests
  where coverage is already strong.

## Proposed Solution

1. **`cli/issues/show.py` (start here).** Add `test_show.py` covering card
   formatting: long titles, empty/missing frontmatter fields, absent optional
   sections, and ID resolution via `_resolve_issue_id`. Model on the existing
   integration-style fixtures (`temp_project_dir`, `config_file`, `issues_dir`).
2. **`cli/parallel.py`.** Add `test_parallel_cli.py` for worker spawn/cleanup and
   error propagation (mock only the host-CLI/subprocess boundary, real config).
3. **`config/automation.py`.** Add `test_config_automation.py` for rule-matching
   and false-positive logic, parametrized over rule cases.
4. **L1 modules.** Add `test_worktree_utils.py` (highest value), then
   `test_decisions_sync.py`, `test_sft_formatter.py`, and a focused
   `test_analytics_*.py` covering the capture paths.
5. **Coverage-guided executor spot-check.** Run
   `pytest --cov=little_loops.fsm.executor --cov-report=term-missing`, take the
   reported missing lines, and add tests only for the genuinely uncovered
   error/interpolation branches.

## Scope Boundaries

- New test modules only; no source changes unless a test surfaces a real bug
  (file that separately).
- `dependency_mapper/formatting.py`: confirm the coverage gap before adding — it
  may already be covered indirectly by `test_dependency_mapper.py`.
- The executor work is a *spot-check* of uncovered branches, not a rewrite of the
  already-strong evaluator/routing coverage.
- Out of scope: standing up CI / coverage gates (explicitly excluded from the
  remediation); Phase 3 maintainability work (tracked separately).
- New test modules must use ENH-2329's project-setup factory fixture (`conftest.py`) rather than raw `tempfile.TemporaryDirectory` + hand-rolled config; write these tests only after ENH-2329 lands (hence `depends_on: ENH-2329`).

## Success Metrics

- Each listed module (`show.py`, `parallel.py`, `config/automation.py`, `worktree_utils.py`, `decisions_sync.py`, `sft_formatter.py`, `analytics/`) gains a dedicated `test_<module>.py` asserting edge cases identified in Current Behavior.
- `dependency_mapper/formatting.py` coverage confirmed before adding tests; new test file added only if a real gap exists.
- `fsm/executor.py` uncovered branches identified via `pytest --cov=little_loops.fsm.executor --cov-report=term-missing`; tests added for all genuinely uncovered error/interpolation paths.
- All new test modules pass `python -m pytest scripts/tests/` with zero failures.

## Integration Map

### Files to Modify
- `scripts/tests/test_show.py` — new, dedicated tests for `cli/issues/show.py` formatting edge cases
- `scripts/tests/test_parallel_cli.py` — new, dedicated tests for `cli/parallel.py` worker lifecycle
- `scripts/tests/test_config_automation.py` — new, dedicated tests for `config/automation.py` rule matching
- `scripts/tests/test_worktree_utils.py` — new (highest-value L1 module)
- `scripts/tests/test_decisions_sync.py` — new
- `scripts/tests/test_sft_formatter.py` — new
- `scripts/tests/test_analytics_*.py` — new, focused capture-path tests
- `scripts/tests/test_formatting.py` — conditional; add only if coverage gap confirmed in `dependency_mapper/formatting.py`

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_cli_loop_worktree.py` — UPDATE: add `base_branch` validation path and directory-skip warning cases; existing `TestSetupWorktree`/`TestCleanupWorktree` already cover the happy paths — replaces proposed `test_worktree_utils.py` (new file is wrong target)
- `scripts/tests/test_decisions.py` — UPDATE: add `_resolve_path(None)` default-path branch and multiple `## Active Rules` rfind-vs-find case to `TestSyncToLocalMd`; replaces proposed `test_decisions_sync.py`
- `scripts/tests/test_loop_run_analytics.py` — UPDATE: add `OSError` branch and malformed-JSON skip case to `TestComputeEvaluatorVariance`; replaces proposed `test_analytics_*.py`
- `scripts/tests/test_fsm_executor.py` — UPDATE: add uncovered `_evaluate()` branch tests (lines 1444–1493) from the executor spot-check; this is the existing main executor test file
- ~~`scripts/tests/test_config_automation.py`~~ — REDUNDANT; `TestAutomationConfig`, `TestParallelAutomationConfig`, and siblings in `test_config.py` already cover all cases including legacy-key fallbacks — skip
- ~~`scripts/tests/test_worktree_utils.py`~~ — WRONG TARGET; use `test_cli_loop_worktree.py` instead
- ~~`scripts/tests/test_decisions_sync.py`~~ — WRONG TARGET; use `test_decisions.py` instead
- ~~`scripts/tests/test_sft_formatter.py`~~ — REDUNDANT; `TestSFTFormatter` in `test_user_messages.py` covers `to_chatml`/`to_alpaca`/`to_sharegpt` and edge cases — skip
- ~~`scripts/tests/test_analytics_*.py`~~ — WRONG TARGET; use `test_loop_run_analytics.py` instead

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/issues/show.py` — module under test
- `scripts/little_loops/cli/parallel.py` — module under test
- `scripts/little_loops/config/automation.py` — module under test
- `scripts/little_loops/dependency_mapper/formatting.py` — module under test (verify gap first)
- `scripts/little_loops/worktree_utils.py` — module under test
- `scripts/little_loops/decisions_sync.py` — module under test
- `scripts/little_loops/sft_formatter.py` — module under test
- `scripts/little_loops/analytics/` — package under test

### Similar Patterns
- `scripts/tests/test_dependency_mapper.py` — established integration-style fixture pattern to follow
- `scripts/tests/conftest.py` — project-setup factory fixture (from ENH-2329); required for all new test modules

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_orchestrator.py` — parallel mocking pattern: `patch("little_loops.parallel.WorkerPool")` / `patch("little_loops.parallel.ParallelOrchestrator")` with `make_project(config=..., extra_dirs=[...])` setup
- `scripts/tests/test_cli.py` — CLI argument-parsing pattern: `patch.object(sys, "argv", ["ll-parallel", ...])` + `from little_loops.cli import main_parallel`

### Tests
- N/A — this issue IS the test additions

_Wiring pass added by `/ll:wire-issue`:_

Existing test files to **UPDATE** (not create new files for):
- `scripts/tests/test_cli_loop_worktree.py` — add 2 narrow-gap cases to `TestSetupWorktree`
- `scripts/tests/test_decisions.py` — add 2 narrow-gap cases to `TestSyncToLocalMd`
- `scripts/tests/test_loop_run_analytics.py` — add 2 narrow-gap cases to `TestComputeEvaluatorVariance`
- `scripts/tests/test_fsm_executor.py` — target file for executor spot-check additions (lines 1444–1493 branches)

Existing test files whose coverage makes a new dedicated file **redundant**:
- `scripts/tests/test_config.py` — `TestAutomationConfig`, `TestParallelAutomationConfig`, etc. fully cover `config/automation.py`
- `scripts/tests/test_user_messages.py` — `TestSFTFormatter` fully covers `sft_formatter.py`

### Documentation
- N/A

### Configuration
- `scripts/tests/conftest.py` — shared fixtures; ENH-2329 adds the factory required here

_Wiring pass added by `/ll:wire-issue`:_
- `stable_snapshot_env` fixture (in `conftest.py`) — **required** for any `test_show.py` assertion on exact rendered card strings; patches `terminal_width()` to return `80` and disables color so `_render_card` output is deterministic
- `_restore_cmd_run_env_vars` autouse fixture (in `conftest.py`) — already handles teardown of `LL_HANDOFF_THRESHOLD` / `LL_CONTEXT_LIMIT` written by `main_parallel()`; no extra cleanup needed in `test_parallel_cli.py`
- `_isolate_history_db` autouse fixture (in `conftest.py`) — `main_parallel()` wraps all execution in `cli_event_context()` which opens SQLite via `session_store`; all `test_parallel_cli.py` tests that invoke `main_parallel()` implicitly depend on this fixture redirecting the DB to `tmp_path`
- `make_project` does **not** auto-create `.issues/<category>/` subdirs unless `config` dict includes `issues.categories` entries — any `test_show.py` test using `_resolve_issue_id()` must pass a config with category definitions or the resolver will find no issue directories

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Coverage Reality Check — affects scope of Proposed Solution steps 3–5:**

| Module | Existing Dedicated Tests | True Gap |
|--------|--------------------------|----------|
| `config/automation.py` | `test_config.py`: `TestAutomationConfig`, `TestParallelAutomationConfig`, `TestConfidenceGateConfig`, `TestRateLimitsConfig`, `TestCommandsConfig`, `TestScoringWeightsConfig`, `TestDependencyMappingConfig` | No functional gap — skip `test_config_automation.py` unless parametrized legacy-key fallback cases are desired |
| `sft_formatter.py` | `test_user_messages.py`: `TestSFTFormatter` — `to_chatml`, `to_alpaca`, `to_sharegpt` all tested including edge cases | Already fully covered — skip `test_sft_formatter.py` |
| `analytics/` package | `test_loop_run_analytics.py`: `TestEvaluatorVariance`, `TestVarianceReport` — thorough | Narrow gaps only: `OSError` branch and malformed-JSON skip in `compute_evaluator_variance` — targeted additions to existing file, not a new file |
| `worktree_utils.py` | `test_cli_loop_worktree.py`: `TestSetupWorktree`, `TestCleanupWorktree`, `_is_ll_worktree`, `_is_ll_branch` | Narrow gaps: `base_branch` validation path in `setup_worktree`, directory-skip warning in `copy_files` |
| `decisions_sync.py` | `test_decisions.py`: `TestSyncToLocalMd` — 5 cases | Narrow gaps: `_resolve_path(None)` default path, multiple `## Active Rules` in file (exercises `rfind` vs `find`) |

**`make_project` fixture:** Already landed in `scripts/tests/conftest.py` (ENH-2329 complete). Returns `(project_root, issues_base)` tuple. Accepts optional `config: dict` and `extra_dirs: list[str]`. Can be called multiple times per test (uses internal counter to avoid collisions).

**Specific unit-test targets for `cli/issues/show.py`** (no existing function-level tests):
- `_source_label(discovered_by)` — falsy input → `"—"` (em dash); known alias (`"/ll:capture-issue"` → `"capture"`); unknown string >7 chars (truncated to 7); unknown string ≤7 chars (returned as-is)
- `_resolve_issue_id(config, user_input)` — three input formats: `P\d-TYPE-NNN`, `TYPE-NNN`, bare `\d+`; non-existent numeric → `None`; stale-type fallback (input `FEAT-1903` when file is `ENH-1903`); multi-candidate tie-breaking via priority prefix
- `_parse_card_fields(path, config)` — issue file with no `##` headers; empty `## Summary` section; `labels:` as YAML list vs. comma-string vs. body backtick items; `learning_tests_raw` as list vs. `None`
- `_ljust(text, width)` — ANSI-colored text (visible width differs from byte length); text longer than `width` (returns unpadded)
- `_render_card(fields)` — minimal card (all optional fields absent, falls back to `"???"` / `"Untitled"`); extremely long unbreakable word (extends box past structural width)

**Specific uncovered branches in `fsm/executor.py` `_evaluate()` for spot-check:**
- Lines 1444–1449: `LLMConfig(enabled=False)` + prompt-mode action without explicit `evaluate:` → returns `EvaluationResult(verdict="error", ...)`
- Lines 1474–1478: `state.evaluate.source` set to unresolvable template → `InterpolationError` caught, falls back to `raw_output`
- Lines 1482–1488: `state.evaluate.type` matches a key in `_contributed_evaluators` → contributed evaluator dispatched (not yet tested in `_evaluate`, only `_execute_state`)
- Lines 1489–1493: `LLMConfig(enabled=False)` + explicit `evaluate: {type: llm_structured}` → returns `EvaluationResult(verdict="error", ...)`

**Mock pattern for `cli/parallel.py` tests** (follows `test_cli.py` / `test_orchestrator.py` conventions):
- Mock manager classes: `patch("little_loops.cli.parallel.WorkerPool")`, `patch("little_loops.cli.parallel.ParallelOrchestrator")`
- Drive CLI: `patch.object(sys, "argv", ["ll-parallel", ...])`
- Capture env-var side effects after call: `assert os.environ["LL_HANDOFF_THRESHOLD"] == "75"`
- Mock git branch detection: `patch("subprocess.run", return_value=subprocess.CompletedProcess([], 0, "main\n", ""))`

## Implementation Steps

1. Add `test_show.py` for `cli/issues/show.py` formatting edge cases.
2. Add `test_parallel_cli.py` for `cli/parallel.py` worker lifecycle.
3. Add `test_config_automation.py` for `config/automation.py` rule matching.
4. Confirm `dependency_mapper/formatting.py` coverage; add `test_formatting.py`
   only if a real gap exists.
5. Add L1 module tests (`worktree_utils.py`, `decisions_sync.py`,
   `sft_formatter.py`, `analytics/`).
6. Run the executor coverage report; add tests for uncovered branches only.
7. Verify the affected files are green and report new coverage deltas.

### Wiring Phase (added by `/ll:wire-issue`)

_Corrections and additions from wiring analysis — integrate into steps 3, 5, and 6:_

- **Step 3 correction**: Skip `test_config_automation.py` — `test_config.py` already has `TestAutomationConfig`, `TestParallelAutomationConfig`, and five sibling classes covering all rule-matching and legacy-key fallback cases.
- **Step 5 correction — do not create new files; update existing**:
  - `worktree_utils.py` → UPDATE `test_cli_loop_worktree.py`: add `base_branch` auto-detection case to `TestSetupWorktree` and a `copy_files` directory-skip warning case.
  - `decisions_sync.py` → UPDATE `test_decisions.py`: add `_resolve_path(None)` default-path case and multiple `## Active Rules` rfind-vs-find case to `TestSyncToLocalMd`.
  - `analytics/` → UPDATE `test_loop_run_analytics.py`: add `OSError` on file-open and malformed-JSON line-skip cases to `TestComputeEvaluatorVariance`.
  - `sft_formatter.py` → SKIP entirely — `TestSFTFormatter` in `test_user_messages.py` fully covers `to_chatml`, `to_alpaca`, `to_sharegpt`, and edge cases.
- **Step 6 clarification**: Executor spot-check additions go into `test_fsm_executor.py` (existing main executor test file), not a new file. **Corrected** target branches (lines 1482–1488 are already covered by `TestContributedEvaluatorDispatch` in `test_ll_loop_execution.py` — audit predated that class):
  - Lines 1444–1449: `LLMConfig(enabled=False)` + prompt-mode action without explicit `evaluate:` → `EvaluationResult(verdict="error", ...)`
  - Lines 1474–1478: `state.evaluate.source` set but `interpolate(...)` raises `InterpolationError` → falls back to `raw_output`
  - Lines 1489–1493: `LLMConfig(enabled=False)` + explicit `evaluate: {type: llm_structured}` → `EvaluationResult(verdict="error", ...)`
- **Step 6 — `test_parallel_cli.py` mock requirement**: `subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], ...)` is called unconditionally at `parallel.py:239` in all non-cleanup/non-prune paths — it must be mocked in every test that reaches `config.create_parallel_config(...)`; omitting it will attempt a real git subprocess call.
- **Step 1 — `test_show.py` helper duplication**: `test_cli_loop_worktree.py` defines `_make_git_lock`, `_ok`, `_ok_with_stdout` locally; if `test_worktree_utils.py` is incorrectly created as a new file, these would need re-declaration. Use `test_cli_loop_worktree.py` directly (per step 5 correction above) to avoid this.

## Impact

- **Priority**: P3 — Closes real dedicated-test gaps in non-trivial modules; no
  user-facing change, but reduces regression risk in CLI/config/parallel paths.
- **Effort**: Medium — several focused test modules; each is independently
  shippable.
- **Risk**: Low — additive tests; no production code changes expected.
- **Breaking Change**: No

## Related Key Documentation

- `thoughts/audits/2026-06-26-test-suite-audit.md` — full test-suite audit findings (M5 and L1) that identified the dedicated-test gaps this issue closes.

## Session Log
- `/ll:ready-issue` - 2026-06-28T04:19:31 - `5004a26b-734b-4a90-8ae2-f4befc10c9c5.jsonl`
- `/ll:wire-issue` - 2026-06-28T04:12:00 - `0fbd1812-a5bf-439a-8e7c-d1ffcf8956ff.jsonl`
- `/ll:refine-issue` - 2026-06-28T04:00:56 - `ee42cc0b-b46d-425f-a338-9467f693e4a5.jsonl`
- `/ll:format-issue` - 2026-06-28T03:47:16 - `25ba2309-4656-4619-af35-ad7f705d9b29.jsonl`
- `/ll:audit-issue-conflicts` - 2026-06-27T22:09:57 - `60b514f4-3db2-4641-831b-e2895943cc2b.jsonl`
- `/ll:audit-issue-conflicts` - 2026-06-27T01:23:43 - `14bc42e7-76a4-4427-8347-44e5b2c9966b.jsonl`
- `/ll:capture-issue` - 2026-06-26T22:35:39Z - test-suite audit remediation Phase 2

---

## Status

- **Status**: open
- **Priority**: P3
