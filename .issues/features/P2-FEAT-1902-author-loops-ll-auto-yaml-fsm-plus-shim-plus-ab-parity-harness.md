---
id: FEAT-1902
title: Author loops/ll-auto.yaml FSM + ll-auto shim + A/B parity harness
type: FEAT
priority: P2
status: cancelled
captured_at: 2026-06-03 19:12:39+00:00
discovered_date: 2026-06-03
discovered_by: scope-epic
parent: EPIC-1867
relates_to:
- FEAT-1901
blocked_by:
- FEAT-1901
confidence_score: 85
outcome_confidence: 60
score_complexity: 14
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 10
missing_artifacts: true
size: Very Large
completed_at: '2026-06-07T17:47:47Z'
---

# FEAT-1902: Author loops/ll-auto.yaml FSM + ll-auto shim + A/B parity harness

## Summary

Write `loops/ll-auto.yaml` as the FSM that replaces `AutoManager.run()` control
flow. The FSM calls Layer-0 CLIs (`ll-issues next`, `ll-issues verify-work`,
`ll-issues classify-failure`) as shell actions. Key requirements:

- Mandatory `verify_work` state backed by an `exit_code` evaluator calling
  `ll-issues verify-work <id> --baseline <sha>` — never trust the implement step's
  exit code alone. This satisfies CLAUDE.md MR-1.
- `max_iterations` derived from backlog size (not hard-coded 50, which halts after
  ~10 issues).
- Convert `ll-auto` CLI to a thin shim over `ll-loop run ll-auto`.
- Pass `ll-loop validate ll-auto` (MR-1/MR-3 clean).
- Pass `ll-loop diagnose-evaluators ll-auto` with `verify_work` verdict variance
  `p(1-p) ≥ 0.05` over ≥10 runs.
- Pass `ll-loop run ll-auto --baseline` showing the harness ≥ unguided baseline.
- **A/B parity harness**: run the same fixed backlog through legacy `ll-auto`
  (`AutoManager.run()`) and the new FSM loop; assert identical `completed/failed`
  sets and matching `history.db` event payloads. This gates merging to main.

Soft-deprecate `AutoManager.run()` for one release (do not delete yet).

Depends on FEAT-1901 (Layer 0 CLI subcommands).

## Use Case

**Who**: Developer or CI automation running `ll-auto` to process a prioritized issue backlog

**Context**: Running automated sequential issue processing against a real codebase, expecting verified outcomes — not just "Claude said done"

**Goal**: Replace brittle `AutoManager.run()` control flow with a testable FSM that provides mandatory post-implementation verification and behavioral parity guarantees vs. the legacy path

**Outcome**: `ll-auto` reliably processes all backlog issues through a validated FSM with a non-LLM `verify_work` gate, `max_iterations` derived from actual backlog size, and A/B-confirmed parity with the legacy runner

## Current Behavior

`ll-auto` invokes `AutoManager.run()` directly — hard-coded Python control flow with no FSM abstraction. The loop halts after ~10 issues due to a `max_iterations=50` that does not account for per-issue overhead, and there is no mandatory post-implementation verification step independent of the implement state's own exit code.

## Expected Behavior

`ll-auto` becomes a thin CLI shim over `ll-loop run ll-auto`. Control flow is defined in `loops/ll-auto.yaml` as an FSM with a mandatory `verify_work` state backed by a non-LLM `exit_code` evaluator. `max_iterations` is derived from backlog size. Legacy `AutoManager.run()` is soft-deprecated (warning added, not deleted). An A/B parity harness confirms behavioral equivalence before merge.

## Motivation

This feature would:
- **Fix run truncation**: Hard-coded `max_iterations=50` halts `ll-auto` mid-backlog; dynamic sizing unblocks long-running automated sessions
- **Enforce verification**: The current path trusts the implement step's own exit code — the FSM's `verify_work` state adds an independent non-LLM gate (satisfies CLAUDE.md MR-1)
- **Unlock FSM testability**: Moving control flow into `loops/ll-auto.yaml` enables `ll-loop validate`, `diagnose-evaluators`, and `--baseline` quality checks impossible against `AutoManager.run()`
- **Gate-safe migration**: A/B parity harness ensures the new FSM is behaviorally equivalent before the legacy path is deprecated

## Acceptance Criteria

- [ ] `loops/ll-auto.yaml` exists and passes `ll-loop validate ll-auto` (MR-1 and MR-3 clean)
- [ ] `verify_work` state uses an `exit_code` evaluator calling `ll-issues verify-work <id> --baseline <sha>` — does not rely on the implement step's exit code alone
- [ ] `max_iterations` is derived from backlog size, not hard-coded
- [ ] `ll-auto` CLI is a thin shim over `ll-loop run ll-auto` (CLI interface preserved)
- [ ] `ll-loop diagnose-evaluators ll-auto` reports `verify_work` verdict variance `p(1-p) ≥ 0.05` over ≥10 runs
- [ ] `ll-loop run ll-auto --baseline` confirms harness performance ≥ unguided baseline
- [ ] A/B parity harness asserts identical `completed/failed` sets and matching `history.db` event payloads between legacy `AutoManager.run()` and the new FSM loop
- [ ] `AutoManager.run()` is soft-deprecated (deprecation warning added; class not deleted)

## Integration Map

### Files to Modify
- `loops/ll-auto.yaml` — new FSM loop definition (create)
- `scripts/little_loops/issue_manager.py` — add deprecation notice to `AutoManager.run()` (class at L1021, `run()` at L1198; `auto_manager.py` does not exist)
- `scripts/little_loops/cli/auto.py` — `main_auto()` entrypoint; convert to thin shim over `ll-loop run ll-auto` (preserve all existing CLI flags)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/auto.py` — `main_auto()` constructs `AutoManager` directly and calls `.run()`; this file becomes the shim
- `scripts/little_loops/__init__.py` — re-exports `AutoManager` as part of public API (line ~40); review export after soft-deprecation
- `scripts/tests/test_issue_manager.py` — direct `AutoManager` unit tests; expand here for A/B parity harness
- `scripts/tests/test_issue_workflow_integration.py` — integration tests instantiating `AutoManager` (L25+); update after shim conversion
- `scripts/tests/test_cli.py` — patches `little_loops.cli.auto.AutoManager` (L303, L337, L363); adjust if shim changes construction site
- `scripts/tests/test_cli_e2e.py` — end-to-end tests that invoke `main_auto()` (L282, L298)
- `scripts/tests/test_wiring_guides_and_meta.py` — asserts `AutoManager.__init__()` referenced in `docs/ARCHITECTURE.md` (L127); review after deprecation
- `scripts/tests/test_wiring_skills_and_commands.py` — asserts `AutoManager` referenced in `config-schema.json` (L89)
- `scripts/tests/test_wiring_reference_docs.py` — asserts `AutoManager` referenced in `docs/reference/CONFIGURATION.md` (L130)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/__init__.py` — re-exports `main_auto` at line 39 via `from little_loops.cli.auto import main_auto`; stays valid but should be reviewed if `main_auto` module-level imports change during shim conversion
- `scripts/little_loops/loops/autodev.yaml` — calls `ll-auto --only "$CURRENT"` in `implement_current` state; exit-code routing survives shim if CLI interface is preserved; audit after conversion
- `scripts/little_loops/loops/oracles/implement-issue-chain.yaml` — calls `ll-auto --only $${ISSUE}`; same exit-code routing dependency
- `scripts/little_loops/loops/rn-remediate.yaml` — calls `ll-auto --only "$ID" 2>&1` in shell action at line 233
- `scripts/little_loops/loops/eval-driven-development.yaml` — calls `ll-auto --priority P1,P2 --quiet` in `implement` state
- `scripts/little_loops/loops/lib/cli.yaml` — fragment with `action: "ll-auto"`; used by loops that need the default backlog sweep

### Similar Patterns
- `loops/autodev.yaml` — closest structural template: queue-based orchestration loop calling `ll-auto --only` as a shell action; shows `fragment: shell_exit` (non-LLM evaluator), `on_handoff: spawn`, `scope`, `max_iterations: 500` static ceiling + queue-file depletion for termination
- `loops/rn-refine.yaml` — canonical MR-1 pattern: pairs an LLM evaluator state with a separate `verify_score` shell state using `output_contains` + `source: "${captured.<var>.output}"`; also uses `artifact_versioning: true`
- `loops/sprint-build-and-validate.yaml` — calls `ll-sprint run` as a shell action (`fragment: shell_exit`); direct template for how a YAML loop invokes a CLI tool as a step
- `loops/eval-driven-development.yaml` — calls `ll-loop run ${context.harness_name}` as a shell action; demonstrates calling `ll-loop run` from within a loop state
- **Note**: Neither `ll-parallel` nor `ll-auto` is currently a shim — both instantiate Python orchestrators directly. This issue introduces the FSM-shim pattern for the first time for `ll-auto`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**AutoManager.run() internals (scripts/little_loops/issue_manager.py:AutoManager):**
- `AutoManager` class at L1021, `run()` at L1198: `while not self._shutdown_requested` loop; terminates when `self.max_issues > 0 and self.processed_count >= self.max_issues`, or `_get_next_issue()` returns `None`
- The FSM equivalent of `max_iterations` is the loop's `max_iterations` YAML field — a separate concept from `AutoManager.max_issues`. The shim should forward `--max-issues` as `--max-iterations $(ll-issues list --json | jq length) * states_per_issue` or use a static ceiling (500+) and rely on queue depletion (same as `autodev.yaml`)
- Phase sequence in `process_issue_inplace()`: (1) ready-issue gate, (2) optional decide-issue if `decision_needed`, (3) implement with continuation handling, (4) verify via `verify_issue_completed()` / `verify_work_was_done()`
- Failure classification in `scripts/little_loops/issue_lifecycle.py:classify_failure()` — returns `(FailureType.TRANSIENT, reason)` or `(FailureType.REAL, reason)` by pattern-matching stderr/stdout; no subprocess needed for FSM `classify_failure` state — can call `ll-issues classify-failure` (FEAT-1901)

**FEAT-1901 prerequisite status:** `ll-issues verify-work` and `ll-issues classify-failure` do NOT exist yet as subcommands. Only `ll-issues next-issue` / `ll-issues next-issues` exist (`scripts/little_loops/cli/issues/next_issue.py:cmd_next_issue()`). The FSM loop states that call these commands cannot be fully tested until FEAT-1901 lands.

**ll-loop run context injection (scripts/little_loops/cli/loop/run.py:cmd_run()):**
- `run_dir` is injected as `.loops/runs/<loop>-<timestamp>/` with trailing slash; folder is created before FSM execution
- `input_hash`, `.ll/program.md` sections (`## Directive`, `## Targets`, etc.) are also injected
- CLI override: `if args.max_iterations: fsm.max_iterations = args.max_iterations` (L118-119)
- Pre-run validation checks all `${context.<key>}` references; missing keys cause a hard error

**history.db event schema (scripts/little_loops/session_store.py:SQLiteTransport):**
- `issue_events` table: `(ts, issue_id, transition, discovered_by, issue_type, priority, captured_at, completed_at)`
- `_ISSUE_TRANSITION_MAP`: `issue.completed → "done"`, `issue.closed → "done"`, `issue.deferred → "deferred"`, `issue.skipped → "cancelled"`, `issue.started → "in_progress"`, `issue.failure_captured → "failure_captured"`
- A/B parity check: query `SELECT issue_id, transition FROM issue_events ORDER BY issue_id, ts` and assert sets match between legacy and FSM runs

**Deprecation pattern (scripts/little_loops/config/core.py:BRConfig.get_completed_dir()):**
```python
import warnings
warnings.warn(
    "AutoManager.run() is deprecated; use ll-loop run ll-auto instead",
    DeprecationWarning,
    stacklevel=2,
)
```
Test with: `pytest.warns(DeprecationWarning, match="AutoManager.run")`

**A/B parity test pattern (scripts/tests/test_generate_schemas.py:test_idempotent_on_second_run(), scripts/tests/test_issues_search.py:test_confidence_first_matches_legacy_lambda()):**
- Create shared fixture (fixed backlog); run `AutoManager(tmp_path).run()` and capture `issue_events` rows; run FSM via `ll-loop run ll-auto` and capture same; assert `{issue_id: transition}` dicts are identical

**ll-issues next-issue output format:**
- `ll-issues next-issue` prints the full issue ID (e.g. `FEAT-1902`), exit 0 when found, exit 1 when no issues remain — use this as the FSM queue-depletion signal; `--skip ID1,ID2`, `--json`, `--path` flags also supported

**fragment: queue_pop vs fragment: shell_exit:**
- `fragment: queue_pop` (from `scripts/little_loops/loops/lib/common.yaml:131-139`) is the canonical choice for `dequeue_next` state — supplies `action_type: shell` + `evaluate.type: exit_code`, designed for head-pop operations; add `capture: input` at the state level so subsequent states reference the popped ID as `${captured.input.output}`
- `fragment: shell_exit` is appropriate for `init`, `implement`, `verify_work`, `classify_failure`, `done` states

**on_handoff: spawn for context overflow:**
- `autodev.yaml` uses `on_handoff: spawn` as a top-level field to resume in a fresh session when context fills — `ll-auto.yaml` should do the same since a full backlog sweep can exceed context limits; pair with `timeout: 28800` (8 hours)

**--context KEY=VALUE flag mechanics (scripts/little_loops/cli/loop/__init__.py:211-217):**
- `--context` uses `action="append"`, accepts repeated `KEY=VALUE` pairs; processed last in `cmd_run()` so they override positional `input`, `program.md` sections, and `run_dir`; values are plain strings; the shim should forward CLI flags (e.g. `--max-issues 10`) as `--context max_issues=10`

**MR-1 exit_code evaluator pattern:**
```yaml
verify_work:
  action_type: shell
  action: |
    ll-issues verify-work ${context.current_issue} --baseline ${context.baseline_sha}
  evaluate:
    type: exit_code
  on_yes: dequeue_next
  on_no: classify_failure
  on_error: classify_failure
```

### Tests
- New: A/B parity harness — run same fixed backlog through legacy and FSM, assert identical `completed/failed` sets and `history.db` payloads; follow pattern in `scripts/tests/test_generate_schemas.py:test_idempotent_on_second_run()`
- `scripts/tests/test_issue_manager.py` — expand for A/B parity tests; existing test class `TestSequentialProcessing` (L25+) is the insertion point
- `scripts/tests/` — add unit tests for shim behavior and dynamic `max_iterations` derivation

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_builtin_loops.py` — **WILL BREAK**: `test_expected_loops_exist()` at line 73 has a hardcoded `expected` set that does not include `"ll-auto"`; adding `scripts/little_loops/loops/ll-auto.yaml` makes `actual != expected` — add `"ll-auto"` to the set
- `scripts/tests/test_ll_auto_loop.py` — **NEW FILE**: per-loop YAML test; follow pattern from `scripts/tests/test_rn_plan.py` using `load_and_validate` + `validate_fsm`; assert required states (`init`, `dequeue_next`, `implement`, `verify_work`, `classify_failure`, `done`), initial state, and that `verify_work` state action contains `ll-issues verify-work`
- `scripts/tests/test_issue_manager.py` — existing `manager.run()` call sites will emit `DeprecationWarning`; wrap calls with `pytest.warns(DeprecationWarning, match="AutoManager.run")` following pattern in `scripts/tests/test_config.py:667` (`TestBRConfig.test_get_completed_dir`)
- `scripts/tests/test_cli.py` — `TestMainAutoIntegration` and `TestMainAutoAdditionalCoverage` patch `little_loops.cli.auto.AutoManager` and assert `mock_manager_cls.assert_called_once()`; after shim conversion `AutoManager` is never instantiated inside `main_auto()` — replace with subprocess/`ll-loop` invocation assertions
- `scripts/tests/test_cli_e2e.py` — `test_ll_auto_dry_run()` (line 235) asserts `mock_popen.call_count == 0`; after shim, `main_auto()` invokes `ll-loop run ll-auto` via subprocess — update assertion; `test_ll_auto_max_issues_limit()` (line 279) and `test_ll_auto_category_filter()` (line 295) instantiate `AutoManager` directly — rewrite to test shim behavior

_Wiring pass 2 added by `/ll:wire-issue`:_
- `scripts/tests/test_issue_workflow_integration.py` — `TestSequentialWorkflowIntegration.test_dry_run_makes_no_changes` calls `manager.run()` directly (~L109) and will emit unhandled `DeprecationWarning` after step 8; wrap with `pytest.warns(DeprecationWarning, match="AutoManager.run")` — not covered by step 11 which only targets `test_issue_manager.py` [Agent 3 finding]

### Documentation
- `docs/` — update any references to `AutoManager.run()` to note soft-deprecation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/ARCHITECTURE.md` — Mermaid sequence diagram (`## Sequential Mode (ll-auto)`) names `AutoManager`, class diagram shows `class AutoManager { +run() int }`, and transport table row references `AutoManager.__init__()`; update all three after soft-deprecation
- `docs/reference/API.md` — `### AutoManager` section (full constructor + `run()` docs) and `### main_auto` section need to reflect shim behavior and deprecation
- `docs/reference/CONFIGURATION.md` — transport section note mentioning `AutoManager.__init__()` (line ~1166) must be updated; this is the anchor asserted by `test_wiring_reference_docs.py` parametrized case `("docs/reference/CONFIGURATION.md", "AutoManager", "ENH-1734")`
- `docs/reference/CLI.md` — `### ll-auto` section (lines 217–256) describes current `AutoManager`-backed behavior; update to describe shim and FSM delegation

_Wiring pass 2 added by `/ll:wire-issue`:_
- `docs/development/E2E_TESTING.md` — section "3. Sequential Execution Workflow (ll-auto)" describes `TestSequentialExecutionWorkflow` class structure; must be updated after step 13 rewrites those tests to reflect new shim assertion patterns [Agent 2 finding]
- `docs/development/TESTING.md` — contains `main_auto` and `AutoManager` code-snippet annotations in test class docstrings; update after shim conversion to reflect that `main_auto()` no longer constructs `AutoManager` directly [Agent 2 finding]

### Configuration

_Wiring pass added by `/ll:wire-issue`:_
- `config-schema.json` — `"sqlite"` object description at line 1293 states `"AutoManager.__init__() wires SQLiteTransport directly for ll-auto runs..."`; update to reflect that the FSM shim now owns that wiring; this is the anchor asserted by `test_wiring_skills_and_commands.py` parametrized case `("config-schema.json", "AutoManager", "ENH-1734")`

## Implementation Steps

1. Confirm FEAT-1901 Layer-0 CLI subcommands are available (`ll-issues next`, `ll-issues verify-work`, `ll-issues classify-failure`); stub the `verify_work` state with a placeholder shell command if FEAT-1901 is not yet merged
2. Author `loops/ll-auto.yaml` FSM: model on `loops/autodev.yaml` queue-orchestration shape; top-level fields: `initial: init`, `max_iterations: 500`, `timeout: 28800`, `on_handoff: spawn`, `import: - lib/common.yaml`; states: `init` (count backlog), `dequeue_next` (use `fragment: queue_pop` + `capture: input`; subsequent states reference dequeued ID as `${captured.input.output}`), `implement`, `verify_work` (exit_code evaluator calling `ll-issues verify-work ${captured.input.output} --baseline ${context.baseline_sha}`), `classify_failure`, `done`; use `fragment: shell_exit` for `init`, `implement`, `verify_work`, `classify_failure`; write all intermediate files to `${context.run_dir}/`; set `on_handoff: spawn` to handle context overflow across a full backlog
3. Convert `scripts/little_loops/cli/auto.py:main_auto()` to thin shim over `ll-loop run ll-auto`; forward all existing flags as `--context KEY=VALUE` overrides: `--max-issues` → `max_issues`, `--resume` → `resume`, `--only` → `only_ids`, `--skip` → `skip_ids`, `--type` → `type_prefixes`, `--priority` → `priority_filter`, `--label` → `label_filter`, `--category` → `category`, `--quiet`/`--verbose` → `verbose`, `--dry-run` → `dry_run`, `--config` → `config`, `--idle-timeout` → `idle_timeout`, `--handoff-threshold` → `handoff_threshold`, `--context-limit` → `context_limit`; preserve `cli_event_context(DEFAULT_DB_PATH, ...)` wrapper around the `ll-loop run` subprocess call
4. Run `ll-loop validate ll-auto` — fix MR-1/MR-3 violations until clean
5. Run `ll-loop diagnose-evaluators ll-auto` over ≥10 runs — confirm `verify_work` verdict variance `p(1-p) ≥ 0.05`
6. Run `ll-loop run ll-auto --baseline` — confirm harness ≥ unguided baseline
7. Build and run A/B parity harness: shared fixture of ≥5 fixed issues; run legacy via `AutoManager(tmp_path).run()` and FSM via `ll-loop run ll-auto`; compare `SELECT issue_id, transition FROM issue_events ORDER BY issue_id` from each run's `.ll/history.db`; assert sets identical; follow test shape from `scripts/tests/test_generate_schemas.py:test_idempotent_on_second_run()`; add to `scripts/tests/test_issue_manager.py`
8. Add `warnings.warn("AutoManager.run() is deprecated; use ll-loop run ll-auto instead", DeprecationWarning, stacklevel=2)` at the top of `AutoManager.run()` in `scripts/little_loops/issue_manager.py:AutoManager.run()` (L1165); follow pattern from `scripts/little_loops/config/core.py:BRConfig.get_completed_dir()`; update wiring tests in `scripts/tests/test_wiring_guides_and_meta.py` (L127) and `scripts/tests/test_wiring_reference_docs.py` (L130) to note deprecation in docs

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

9. Add `"ll-auto"` to the `expected` set in `scripts/tests/test_builtin_loops.py:test_expected_loops_exist()` (line 73) — placing `ll-auto.yaml` in `scripts/little_loops/loops/` without this update causes `test_expected_loops_exist` to fail with `actual != expected`
10. Create `scripts/tests/test_ll_auto_loop.py` — per-loop YAML test following pattern from `scripts/tests/test_rn_plan.py`; set `LOOP_FILE = BUILTIN_LOOPS_DIR / "ll-auto.yaml"`; assert file exists, YAML parses, `load_and_validate` passes `validate_fsm` with no ERROR-severity results, required states present (`init`, `dequeue_next`, `implement`, `verify_work`, `classify_failure`, `done`), `verify_work` action contains `"ll-issues verify-work"`
11. Wrap all `manager.run()` call sites in `scripts/tests/test_issue_manager.py` with `pytest.warns(DeprecationWarning, match="AutoManager.run")` — follow pattern from `scripts/tests/test_config.py:667` (`TestBRConfig.test_get_completed_dir`); prevents DeprecationWarning from polluting test output
12. Rewrite `scripts/tests/test_cli.py:TestMainAutoIntegration` and `TestMainAutoAdditionalCoverage` — replace `patch("little_loops.cli.auto.AutoManager")` + `mock_manager_cls.assert_called_once()` with subprocess/`ll-loop` invocation assertions; `AutoManager` is no longer constructed inside `main_auto()` after shim conversion
13. Update `scripts/tests/test_cli_e2e.py` — `test_ll_auto_dry_run()` (line 235): update `mock_popen.call_count == 0` assertion to expect `ll-loop run ll-auto` subprocess call; rewrite `test_ll_auto_max_issues_limit()` (line 279) and `test_ll_auto_category_filter()` (line 295) to test shim flag-forwarding rather than direct `AutoManager` attribute inspection
14. Update `config-schema.json` `"sqlite"` description (line 1293) — replace `"AutoManager.__init__() wires SQLiteTransport directly for ll-auto runs"` with a note that reflects FSM shim ownership; update the corresponding parametrized assertion in `test_wiring_skills_and_commands.py` (`("config-schema.json", "AutoManager", "ENH-1734")`) to match the new anchor string
15. Update documentation: `docs/ARCHITECTURE.md` (Mermaid diagrams + transport table), `docs/reference/API.md` (`### AutoManager` + `### main_auto`), `docs/reference/CONFIGURATION.md` (transport section), `docs/reference/CLI.md` (`### ll-auto` section) — reflect soft-deprecation of `AutoManager.run()` and shim behavior
16. Audit `loops/autodev.yaml`, `loops/oracles/implement-issue-chain.yaml`, `loops/rn-remediate.yaml`, `loops/eval-driven-development.yaml`, `loops/lib/cli.yaml` — confirm exit-code routing still works after shim; no changes expected if `ll-auto` preserves exit codes, but verify before merge
17. Wrap `manager.run()` call in `scripts/tests/test_issue_workflow_integration.py:TestSequentialWorkflowIntegration.test_dry_run_makes_no_changes` (~L82) with `pytest.warns(DeprecationWarning, match="AutoManager.run")` — separate from step 11 which covers only `test_issue_manager.py` call sites
18. After steps 12–13 rewrite the E2E test classes, update `docs/development/E2E_TESTING.md` (section "3. Sequential Execution Workflow (ll-auto)") and `docs/development/TESTING.md` to reflect the new shim assertion patterns

## Impact

- **Priority**: P2 — critical path; the core deliverable of Layer 1
- **Effort**: Large — new FSM YAML, CLI shim refactor, parity test harness
- **Risk**: High — risk concentrated in the verify/parity gates
- **Breaking Change**: No (shim preserves CLI interface)

## Labels

`automation`, `fsm`, `ll-auto`, `layer-1`, `orchestration`

## Status

**Open** | Created: 2026-06-03 | Priority: P2

## Verification Notes

_Added by `/ll:verify-issues` on 2026-06-03_

**Verdict: NEEDS_UPDATE** — Integration Map referenced `scripts/little_loops/auto_manager.py` which does not exist. `AutoManager` lives in `scripts/little_loops/issue_manager.py` (class at L988, `run()` at L1165). This has been corrected in the Integration Map. Also: FEAT-1901 prerequisite (Layer-0 CLI subcommands) is still open and unimplemented.

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): This issue defines the canonical thin-shim pattern for EPIC-1867 CLI migrations (`<cli> → ll-loop run <loop>`). FEAT-1899 (`ll-sprint execute`) should follow this pattern for consistency rather than implementing an independent shim approach.

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-06-07_

**Readiness Score**: 85/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 60/100 → MODERATE

### Concerns
- FEAT-1901 is still open (formal `blocked_by`); `ll-issues verify-work` and `ll-issues classify-failure` subcommands do not exist — the `verify_work` FSM state must use a placeholder stub, and acceptance criteria 5 (evaluator variance p(1-p) ≥ 0.05) and 6 (baseline comparison) cannot be validated until the dependency lands.

### Outcome Risk Factors
- **Broad change surface**: 16 files across 4 subsystems (FSM YAML, Python CLI, tests, docs/config) — Breadth > 15 penalizes Criterion A to 5/12; coordination failure across touchpoints is the primary integration risk.
- **Moderate blast radius**: ~10-11 callers/dependents of `AutoManager` and `main_auto()` must be consistently updated after shim conversion (6 loop files + 3 test class groups + `__init__.py`); `test_cli.py` requires a full class rewrite.
- **Missing prerequisite**: `ll-issues verify-work` does not exist yet (pending FEAT-1901) — the `verify_work` FSM state requires a stub; the A/B parity harness can still be built, but parity of the real verification path needs FEAT-1901.

---

## Resolution

- **Status**: Decomposed
- **Completed**: 2026-06-07
- **Reason**: Issue too large for single session (score 11/11)

### Decomposed Into
- FEAT-2000: Author loops/ll-auto.yaml FSM definition and validate
- FEAT-2001: Convert ll-auto CLI to thin shim over ll-loop and build A/B parity harness
- FEAT-2002: Update docs and config for ll-auto FSM migration and AutoManager soft-deprecation

## Session Log
- `/ll:issue-size-review` - 2026-06-07T00:00:00Z - `5db94c28-db76-4bed-885c-95a49da744cb.jsonl`
- `/ll:confidence-check` - 2026-06-07T00:00:00Z - `e8764177-a179-44c4-9ca9-3f2696ce0963.jsonl`
- `/ll:refine-issue` - 2026-06-07T17:38:54 - `6214237c-b270-42ac-a4cf-ca15ba6ea67c.jsonl`
- `/ll:wire-issue` - 2026-06-07T17:33:58 - `a55668b4-c556-4d7d-9ea0-414f6469420e.jsonl`
- `/ll:confidence-check` - 2026-06-07T00:00:00Z - `e286ef25-ca50-473e-9751-1a34064b1849.jsonl`
- `/ll:wire-issue` - 2026-06-06T00:00:00 - `current-session.jsonl`
- `/ll:refine-issue` - 2026-06-07T00:00:06 - `7dd0b9eb-6086-431f-a60e-1813df9e769a.jsonl`
- `/ll:verify-issues` - 2026-06-05T21:00:23 - `current-session.jsonl`

- `/ll:verify-issues` - 2026-06-05T01:35:35 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/579edc97-1110-41b7-9283-1612d1e82fee.jsonl`
- `/ll:audit-issue-conflicts` - 2026-06-04T19:53:59 - `2f12f6ef-94a2-4725-933e-626b1ef4cdff.jsonl`
- `/ll:audit-issue-conflicts` - 2026-06-04T19:47:22 - `d0974b20-4737-4771-8c63-e70d193dc3d5.jsonl`
- `/ll:verify-issues` - 2026-06-04T04:21:13 - `94e89e68-ddb3-448e-a123-eae4ee9ba582.jsonl`
- `/ll:verify-issues` - 2026-06-03T22:42:45 - `25083174-f806-4589-a206-0f8b53978497.jsonl`
- `/ll:audit-issue-conflicts` - 2026-06-03T22:04:03 - `882d6aa0-cbf0-47c3-9d9c-32d8d6c6ef92.jsonl`
- `/ll:format-issue` - 2026-06-03T19:22:56 - `1489a8f1-014d-4d2b-9f62-365c703f374a.jsonl`
- `/ll:scope-epic` - 2026-06-03T19:12:39Z - `87e9f36b-36c2-4e9e-a0c8-3a57aa45d1f5.jsonl`

---

## Resolution

- **Status**: Decomposed
- **Closed**: 2026-06-07
- **Decomposed into**: FEAT-2000, FEAT-2001, FEAT-2002

Work for FEAT-1902 is now carried by its child issues; this parent was closed by rn-decompose.

- **Status correction** (2026-06-12, epic audit): frontmatter was `done`, which inflated EPIC-1867 progress (1/7 done) although `loops/ll-auto.yaml` was never authored under this issue. Corrected to `cancelled` (superseded by the FEAT-2000/FEAT-2001/FEAT-2002 decomposition).
