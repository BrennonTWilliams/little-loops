---
id: FEAT-1899
title: Implement ll-sprint FSM wave driver and shim
type: FEAT
priority: P3
status: deferred
captured_at: 2026-06-03 19:12:39+00:00
discovered_date: 2026-06-03
discovered_by: scope-epic
parent: EPIC-1867
relates_to:
- FEAT-1901
- FEAT-2000
blocked_by:
- FEAT-1901
- FEAT-2000
- FEAT-2001
blocks:
- ENH-1903
labels:
- feature
- orchestration
- fsm
- sprint
confidence_score: 90
outcome_confidence: 84
score_complexity: 21
score_test_coverage: 18
score_ambiguity: 20
score_change_surface: 25
---

# FEAT-1899: Implement ll-sprint FSM wave driver and shim

## Summary

Convert `ll-sprint` into an FSM wave driver that reuses the Layer-1 per-issue
states for sequential orchestration and delegates to `ParallelOrchestrator` for
parallel waves. Deliverables:

- `ll-sprint plan --json` subcommand emitting an ordered wave definition (list of
  waves, each with issue IDs and execution mode: `sequential` or `parallel`).
- An FSM wave driver (`loops/ll-sprint.yaml` or equivalent) that iterates over
  wave definitions, dispatches single/contention sub-waves to the Layer-1 per-issue
  states, and shells out to `ParallelOrchestrator` for multi-issue waves.
- Convert `ll-sprint` CLI to a thin shim over the FSM driver.
- Pass `ll-loop validate ll-sprint` (MR-1/MR-3).

Depends on FEAT-1901 (Layer 0 CLI subcommands) and FEAT-1902 (Layer-1 per-issue states to reuse).

## Use Case

**Who**: Developer running `ll-sprint` to execute a curated set of issues with dependency-aware ordering.

**Context**: After Layer-1 per-issue states (FEAT-1902) are available, the sprint orchestrator needs a structured wave driver — dispatching sequential single-issue sub-waves and delegating parallel batches to `ParallelOrchestrator` — rather than embedding orchestration logic directly in the CLI.

**Goal**: Run `ll-sprint execute` and have dependency-ordered waves driven by a validated FSM loop that reuses Layer-1 states, with parallel batches automatically delegated to `ParallelOrchestrator`.

**Outcome**: `ll-sprint` becomes a thin shim over `loops/ll-sprint.yaml`; the FSM wave driver passes `ll-loop validate` (MR-1/MR-3).

## Current Behavior

`ll-sprint` is a standalone CLI that executes curated issue sets sequentially with dependency-aware ordering. It does not emit structured wave definitions, does not use an FSM wave driver, and does not delegate parallel waves to `ParallelOrchestrator`. All orchestration logic lives directly in the CLI rather than in a validated loop.

## Expected Behavior

- `ll-sprint plan --json` emits an ordered list of waves: `[{"wave": N, "issues": [...], "mode": "sequential|parallel"}, ...]`.
- An FSM wave driver (`loops/ll-sprint.yaml`) iterates over wave definitions, dispatches single/contention sub-waves to Layer-1 per-issue states, and delegates multi-issue parallel waves to `ParallelOrchestrator`.
- `ll-sprint execute` becomes a thin shim that invokes `ll-loop run ll-sprint`.
- `ll-loop validate ll-sprint` passes (MR-1 and MR-3 compliant).

## Motivation

This feature completes the EPIC-1867 FSM decomposition at the sprint/wave level:
- Reuses Layer-1 per-issue states (FEAT-1902) rather than duplicating per-issue orchestration logic in `ll-sprint`.
- Enables `ll-loop validate` enforcement of meta-loop rules (MR-1/MR-3) on sprint execution.
- Reduces `ll-sprint` to a thin shim, concentrating wave dispatch logic in a structured, testable FSM.
- Unlocks parallel wave delegation to `ParallelOrchestrator` in a validated, observable way.

## Acceptance Criteria

- [ ] `ll-sprint plan --json` emits a valid ordered wave definition (list of waves with `issue_ids` and `mode: sequential|parallel`).
- [ ] `loops/ll-sprint.yaml` FSM wave driver iterates over wave definitions and routes correctly to sequential vs. parallel dispatch states.
- [ ] Sequential/contention sub-waves delegate to Layer-1 per-issue states from FEAT-1902.
- [ ] Parallel waves shell out to `ParallelOrchestrator`.
- [ ] `ll-sprint execute` is a thin shim — no duplicated orchestration logic in the CLI.
- [ ] `ll-loop validate ll-sprint` passes (MR-1 and MR-3).
- [ ] Existing `ll-sprint` CLI interface is preserved (no breaking changes to argument surface).

## Proposed Solution

**Step 1 — Add `ll-sprint plan --json`**: Extend `scripts/little_loops/sprint.py` with a `plan` subcommand that reads the sprint definition, resolves dependency order, and emits a JSON wave list.

**Step 2 — Author `loops/ll-sprint.yaml`** following the meta-loop diagnosis-first shape (CLAUDE.md § Loop Authoring):
- States: `load_plan` → `dispatch_wave` → `run_sequential` / `delegate_parallel` → `check_wave_complete` → `done`.
- `dispatch_wave` routes on `mode` field from the wave definition.
- `run_sequential` delegates to `loop: per-issue-processor` (the shared sub-loop from ENH-2106/ARCHITECTURE-030) via `with: {issue_id, baseline_sha}` — do NOT inline per-issue states.
- `delegate_parallel` shells out to `ParallelOrchestrator`.
- Every LLM-structured state paired with a non-LLM evaluator (`exit_code` or `convergence`) — MR-1.
- All intermediate artifacts written under `${context.run_dir}/` — MR-3.

**Step 3 — Shim `ll-sprint execute`**: Replace orchestration logic with `ll-loop run ll-sprint --args <wave-plan-path>`.

**Step 4 — Validate**: `ll-loop validate ll-sprint`; fix any MR-1/MR-3 violations.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**`plan --json` mode-field derivation** — the `mode` field comes from `refine_waves_for_contention()` output: `mode = "sequential" if (len(wave) == 1 or contention_note is not None) else "parallel"`. Both `get_execution_waves()` and `refine_waves_for_contention()` already exist in `_cmd_sprint_run()` and `_cmd_sprint_show()`; `plan --json` can share the same call sequence. See `_show_json()` in `scripts/little_loops/cli/sprint/show.py` and `_cmd_sprint_analyze()` in `scripts/little_loops/cli/sprint/manage.py` for the JSON wave-output templates.

**FSM loop structure** — `scripts/little_loops/loops/goal-cluster.yaml` is the closest structural reference for the wave-driver pattern: it writes wave items to `${context.run_dir}/wave-queue/NNNN.json`, pops the front file per iteration, routes to sub-loop delegation via `loop:` + `with:`, and tracks success/failure in `${context.run_dir}/cluster-state.json`. Use this as the FSM template rather than the older `sprint-refine-and-implement.yaml` (which uses bare `.loops/tmp/` paths, violating MR-3).

**MR-1 will NOT trigger for `ll-sprint.yaml`** — `_is_meta_loop()` in `scripts/little_loops/fsm/validation.py` only flags loops whose action strings write to `loops/*.yaml`, `skills/*/SKILL.md`, `agents/*.md`, `commands/*.md`, or `.claude/CLAUDE.md`. A wave-driver that only calls `ll-loop run` and `ll-sprint run` is not a meta-loop. Use `exit_code` evaluators throughout for clean `ll-loop validate` passes.

**CRITICAL — `.sprint-state.json` CWD compatibility**: `scripts/little_loops/loops/sprint-build-and-validate.yaml`'s `extract_unresolved` state reads `.sprint-state.json` from `Path.cwd()` via `jq`:
```yaml
ISSUES=$(jq -r '[...] | flatten | unique | join(",")' .sprint-state.json 2>/dev/null)
```
If the FSM driver moves state persistence to `${context.run_dir}/sprint-state.json`, this upstream loop will silently stop recovering failed issues (empty `ISSUES` var). Resolution options: (a) keep writing `.sprint-state.json` at CWD for the shim path (consistent with existing `_save_sprint_state()`/`_cleanup_sprint_state()` helpers in `run.py`), or (b) update `sprint-build-and-validate.yaml` to read from `${context.run_dir}/`. **Option (a) is safer** — the shim must preserve the state-file location at CWD.

**`lib/cli.yaml` fragment** — `scripts/little_loops/loops/lib/cli.yaml` already defines an `ll_loop_run` fragment (`action: "ll-loop run ${context.loop_name}"`). The shim in `run.py` can delegate using the same pattern, substituting `ll-sprint` as the loop name.

## API/Interface

```
# New subcommand
ll-sprint plan --json [--sprint <name>]

# Output schema
[
  {"wave": 1, "issues": ["FEAT-001"], "mode": "sequential"},
  {"wave": 2, "issues": ["FEAT-002", "FEAT-003"], "mode": "parallel"},
  ...
]

# Thin shim (internal)
ll-sprint execute → ll-loop run ll-sprint --args <wave-plan>
```

## Integration Map

### Files to Modify
- `scripts/little_loops/sprint.py` — add `plan --json` subcommand; refactor `execute` to thin shim
- `loops/ll-sprint.yaml` — new FSM wave driver (create)
- `scripts/little_loops/cli/sprint/__init__.py` — register `plan` subparser in `main_sprint()` argparse table; add dispatch branch `_cmd_sprint_plan`; update `__all__` and epilog examples
- `scripts/little_loops/cli/sprint/run.py` — convert `_cmd_sprint_run()` wave orchestration logic to thin shim delegating to `ll-loop run ll-sprint`

_Wiring pass added by `/ll:wire-issue`:_

### Dependent Files (Callers/Importers)
- `scripts/little_loops/parallel/orchestrator.py` — invoked by `delegate_parallel` state (path corrected; was incorrectly listed as standalone `parallel_orchestrator.py`)
- FEAT-1902 Layer-1 per-issue loop YAML — referenced by `run_sequential` state
- `scripts/little_loops/cli/sprint/__init__.py` — imports `SprintManager`; houses `main_sprint()` dispatch; primary site for `plan` subparser registration
- `scripts/little_loops/cli/sprint/run.py` — contains `_cmd_sprint_run()` with all wave orchestration logic that becomes the shim target; also exports `_sprint_signal_handler`, `_sprint_shutdown_requested`, state-file helpers
- `scripts/little_loops/cli/sprint/create.py` — imports `SprintManager` for CRUD; not modified but depends on sprint module
- `scripts/little_loops/cli/sprint/show.py` — imports `SprintManager`; `_cmd_sprint_show()` used in dry-run tests
- `scripts/little_loops/cli/sprint/manage.py` — imports `SprintManager` for list/delete/analyze
- `scripts/little_loops/cli/sprint/edit.py` — imports `SprintManager` for modification
- `scripts/little_loops/cli/__init__.py` — re-exports `main_sprint` and all sprint CLI symbols at package level
- `scripts/little_loops/dependency_graph.py` — `DependencyGraph.get_execution_waves()` is the wave-ordering method called by the new `plan --json` subcommand
- `scripts/little_loops/cli/loop/run.py` — `ll-loop run` entry point; invoked by the `execute` thin shim
- `scripts/little_loops/fsm/validation.py` — used by `ll-loop validate ll-sprint` (MR-1/MR-3 enforcement gate)
- `scripts/little_loops/loops/sprint-build-and-validate.yaml` — contains a `run_sprint` state that calls `ll-sprint run ${captured.sprint_name.output}`; external interface must be preserved or this loop breaks

_Wiring pass added by `/ll:wire-issue`:_

### Similar Patterns
- Existing loop YAMLs in `loops/` — structural reference for FSM state design
- CLAUDE.md § Loop Authoring — meta-loop rules (diagnosis-first, MR-1, MR-3)
- `scripts/little_loops/parallel/orchestrator.py` — `ParallelOrchestrator` public interface: `__init__(parallel_config, br_config, repo_path, verbose, wave_label, event_bus)`, `run() -> int`, `execution_duration` property; read `queue.completed_ids`/`queue.failed_ids` after `run()`; invoked with `clean_start=True`, `overlap_detection=False` in sprint context

### Tests

**Tests to update (behavior changes when `execute`/`run` becomes a thin shim):**
- `scripts/tests/test_sprint.py` — `TestSprintErrorHandling`: `test_keyboard_interrupt_returns_130`, `test_unexpected_exception_returns_1`, `test_exception_saves_state` — all call `_cmd_sprint_run` directly and monkeypatch internals that disappear in the shim
- `scripts/tests/test_sprint.py` — `TestSprintDependencyAnalysis`: `test_run_shows_dependency_analysis`, `test_run_skip_analysis_flag` — assert on stdout strings produced inside old `_cmd_sprint_run` body
- `scripts/tests/test_sprint_integration.py` — `TestMultiWaveExecution`: `test_sprint_run_multiple_waves`, `test_sprint_disables_runtime_overlap_detection`, `test_sprint_wires_transports_per_wave` — patch `ParallelOrchestrator` inside old runner; bypassed by shim
- `scripts/tests/test_sprint_integration.py` — `TestErrorRecovery` (all ~8 tests) — call `_cmd_sprint_run` and assert `.sprint-state.json` written at repo root; FSM driver writes state to `${context.run_dir}/`
- `scripts/tests/test_cli_sprint.py` — `TestMainSprintDispatch.test_run_routes_to_handler` — mock target changes if handler is renamed

**New tests to write:**
- `scripts/tests/test_ll_sprint_loop.py` — NEW file following `test_rn_build.py`/`test_loop_router.py` pattern:
  - `TestLlSprintFile` — file exists, parses, `name == "ll-sprint"`, passes `is_runnable_loop()`
  - `TestLlSprintFSMValidation` — `load_and_validate` returns no ERROR-severity violations; no MR-1/MR-3 violations
  - `TestLlSprintStates` — required states (`load_plan`, `dispatch_wave`, `run_sequential`, `delegate_parallel`, `check_wave_complete`, `done`, `failed`) exist with correct routing fields
  - `TestLlSprintMr3Compliance` — no bare `.loops/tmp` writes; all artifacts under `${context.run_dir}/`
- `scripts/tests/test_cli_sprint_commands.py` (or `test_sprint.py`) — `TestCmdSprintPlan`:
  - `test_plan_json_emits_wave_list` — assert `list` of `{wave, issues, mode}` objects; follow `test_show_json_output` pattern
  - `test_plan_json_wave_ordering_respects_dependencies`
  - `test_plan_sprint_not_found_returns_1`
- `scripts/tests/test_cli_sprint.py` — add `test_plan_routes_to_handler` to `TestMainSprintDispatch` following the existing `_mock_handlers` pattern

_Wiring pass added by `/ll:wire-issue`:_

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/SPRINT_GUIDE.md` — `## Running a Sprint` (flag table), `## How Waves Work` (dispatch description), `## Handling Interruptions / Resume` (state-file location changes from `.sprint-state.json` to `${context.run_dir}/`)
- `docs/reference/CLI.md` — `#### ll-sprint run` exhaustive flag reference; `## Common Flags` table row; milestone write-back note (currently states `_cmd_sprint_run` writes `milestone:` frontmatter — shim must preserve or doc must update)
- `docs/ARCHITECTURE.md` — `## Sprint Mode (ll-sprint)` Mermaid sequence diagram (`ll-sprint run → SprintManager → DependencyGraph → ParallelOrchestrator` becomes FSM-mediated); EventBus wiring table row
- `docs/reference/API.md` — document `plan --json` subcommand; add `plan` row to subcommand table in `main_sprint()` entry
- `.claude/CLAUDE.md` — `## CLI Tools` entry for `ll-sprint` omits `plan` subcommand — update description
- `commands/create-sprint.md` — `## Integration` section states "Sprint execution uses `ParallelOrchestrator` from `parallel/orchestrator.py`" directly — update to reflect FSM-mediated dispatch

### Configuration
- N/A — uses existing sprint config in `.ll/ll-config.json`; no new keys required

## Implementation Steps

1. Add `ll-sprint plan --json` subcommand to emit ordered wave definitions.
2. Author `loops/ll-sprint.yaml` FSM wave driver with `load_plan`, `dispatch_wave`, `run_sequential`, `delegate_parallel`, `check_wave_complete`, `done` states.
3. Wire `run_sequential` state to delegate via `loop: per-issue-processor` (shared sub-loop, decision ARCHITECTURE-030 / ENH-2106) — do NOT inline per-issue states from FEAT-1902 directly.
4. Wire `ParallelOrchestrator` (`scripts/little_loops/parallel/orchestrator.py`) into `delegate_parallel` state.
5. Refactor `ll-sprint execute` to thin shim invoking `ll-loop run ll-sprint`.
6. Run `ll-loop validate ll-sprint`; resolve any MR-1/MR-3 violations.
7. Run existing `ll-sprint` tests; verify CLI interface is preserved.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

8. Update `scripts/little_loops/cli/sprint/__init__.py` — add `plan` subparser to `main_sprint()` argparse table; add dispatch branch; update `__all__` and epilog examples
9. Update `scripts/little_loops/cli/sprint/run.py` — convert `_cmd_sprint_run()` wave logic to thin shim; preserve `_sprint_signal_handler` and `_sprint_shutdown_requested` module-level globals (test coverage depends on them); ensure milestone write-back to issue frontmatter still occurs before delegating
10. Update `TestSprintErrorHandling` tests in `scripts/tests/test_sprint.py` — adapt for shim exit-code propagation; update `.sprint-state.json` assertions to reflect `${context.run_dir}/` state location
11. Update `TestMultiWaveExecution` + `TestErrorRecovery` in `scripts/tests/test_sprint_integration.py` — patch points change when `ParallelOrchestrator` is invoked by FSM rather than directly by `_cmd_sprint_run`
12. Create `scripts/tests/test_ll_sprint_loop.py` — FSM YAML structural tests following `test_rn_build.py`/`test_loop_router.py` pattern (MR-1, MR-3, required states, `is_runnable_loop`)
13. Add `TestCmdSprintPlan` tests (plan JSON schema, wave ordering, sprint-not-found) and `test_plan_routes_to_handler` in `TestMainSprintDispatch`
14. Update `docs/guides/SPRINT_GUIDE.md`, `docs/reference/CLI.md`, `docs/ARCHITECTURE.md`, `.claude/CLAUDE.md`, `commands/create-sprint.md` — reflect FSM-mediated execution model, updated sequence diagram, new `plan` subcommand

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Step 1 anchors** — `plan --json` subcommand: register `plan_parser` in `main_sprint()` at `scripts/little_loops/cli/sprint/__init__.py:196` (follows `analyze_parser` pattern); handler `_cmd_sprint_plan()` in a new file `scripts/little_loops/cli/sprint/plan.py`; call `dep_graph.get_execution_waves()` at `scripts/little_loops/dependency_graph.py:172` then `refine_waves_for_contention()` at line 388; map `contention_notes[i] is not None or len(wave)==1` → `mode: "sequential"`, else `mode: "parallel"`.

**Step 2 anchors** — FSM state structure: `initial: load_plan` → `read_wave` (pop next wave from `${context.run_dir}/wave-queue/`) → `dispatch_wave` (route on `mode` captured from wave JSON) → `run_sequential` (call `ll-loop run ll-auto --only <id>` per issue, or delegate to Layer-1 FEAT-1902 loop) → `delegate_parallel` (call `ParallelOrchestrator` via `ll-sprint run --only <ids>` or shell invocation) → `check_wave_complete` → loop back to `read_wave` or → `done`/`failed`. Model after `scripts/little_loops/loops/goal-cluster.yaml` queue dispatch pattern.

**Step 5 anchors** — thin shim: replace `_cmd_sprint_run()` orchestration body in `scripts/little_loops/cli/sprint/run.py` with `subprocess.run(["ll-loop", "run", "ll-sprint", "--args", wave_plan_path])` after completing pre-flight steps (filter pipeline, `validate_issues()`, milestone write-back via `update_frontmatter()`, dependency graph cycle check). Milestone write-back via `update_frontmatter()` at `scripts/little_loops/sprint.py` MUST occur before shim delegates. Preserve `_sprint_signal_handler` and `_sprint_shutdown_requested` module-level globals — tests mock them directly.

**Step 5 — `.sprint-state.json` compatibility**: shim MUST continue writing `.sprint-state.json` at `Path.cwd()` (not `${context.run_dir}/`). The FSM driver writes its internal checkpoints under `${context.run_dir}/` but the final state summary (failed/skipped issues) must be at CWD for `sprint-build-and-validate.yaml`'s `extract_unresolved` state to read it.

**Step 12 test anchors** — `test_ll_sprint_loop.py` setup:
```python
from little_loops.fsm import is_runnable_loop
from little_loops.fsm.validation import ValidationSeverity, load_and_validate, validate_fsm
LOOP_FILE = Path(__file__).parent.parent / "little_loops" / "loops" / "ll-sprint.yaml"
```
Four test classes following `scripts/tests/test_rn_build.py`: `TestLlSprintFile`, `TestLlSprintFSMValidation` (check `load_and_validate()` no ERROR, no MR-3 `".loops/tmp"` violations), `TestLlSprintStates`, `TestLlSprintMr3Compliance`.

**Step 13 test anchors** — `TestCmdSprintPlan`: follow `_setup_show_project()` helper from `scripts/tests/test_cli_sprint_show.py:421`; use `capsys.readouterr()` + `json.loads(captured.out)` to validate output schema; assert `"mode"` key in each wave dict. Add `"_cmd_sprint_plan"` to `_mock_handlers()` in `scripts/tests/test_cli_sprint.py:25`.

## Impact

- **Priority**: P3 — builds on Layer 1; delivers wave-level orchestration
- **Effort**: Medium — wave driver logic + plan subcommand + shim
- **Risk**: Medium — wave dispatch logic is new; parallel delegation to ParallelOrchestrator is well-understood
- **Breaking Change**: No (shim preserves CLI interface)

## Status

**Deferred** | Created: 2026-06-03 | Priority: P3

**Deferral rationale (2026-07-07, backlog grooming)**: Five weeks after EPIC-1867 capture (2026-06-02), 0 of 4 layers delivered. ENH-2106 (the only real blocker on the critical path) was resolved 2026-06-13, but the four open/blocked children of EPIC-1867 have not been picked up — the team has voted with its time. Meanwhile `ll-auto`/`ll-sprint`/`ll-parallel` are actively *gaining* Python behavior (ENH-2182 feature-branch holding, ENH-2210 batch learning-test gate, `--feature-branches` override, push & PR creation, etc.) — the decomposition premise (orchestrators stable enough to wrap in an FSM) is weakening, not strengthening, and the v0.2 plan from 2026-06-02 is already partly stale. This Layer-2 issue is the *last* in the chain (depends on Layers 0+1 via FEAT-1901/FEAT-2000/FEAT-2001), so its deferral is mechanical once the chain is acknowledged as dormant. **Re-activation criteria** (any one is sufficient): (a) the orchestrator surface has had ≥ 2 consecutive release cycles with bug fixes only, no new features; (b) an FSM-driven loop (`rn-*` family) has run successfully in production for ≥ 10 distinct issues; (c) a user-visible orchestrator failure is reported that the FSM decomposition would have prevented. Tracked at EPIC-1867.

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): This issue's `ll-sprint execute` shim follows the canonical thin-shim pattern established by FEAT-1902 (`<cli> → ll-loop run <loop>`). Coordinate shim implementation approach with FEAT-1902 to avoid divergent patterns.

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-06-07_

**Readiness Score**: 65/100 → STOP — ADDRESS GAPS
**Outcome Confidence**: 82/100 → HIGH CONFIDENCE

### Gaps to Address
- **FEAT-1901 is unresolved**: Issue is declared `blocked_by: FEAT-1901` (Stabilize shared orchestration core) which is still `Open`. Either wait for FEAT-1901 to complete, or reassess whether the dependency is hard-blocking (DependencyGraph code already exists in sprint.py:348 — the declared blocker may be softer than it appears).

### Concerns
- Integration Map has an incorrect path: `scripts/little_loops/parallel_orchestrator.py` should be `scripts/little_loops/parallel/orchestrator.py` (flagged in Verification Notes but not yet corrected — fix before implementation).

## Session Log
- backlog-grooming - 2026-07-03T00:00:00Z - Absorbed ENH-1903's residual: when this lands, flip the Layer 2 row in docs/ARCHITECTURE.md § Orchestration Layers status table from planned to shipped. ENH-1903 closed (docs shipped).
- `/ll:verify-issues` - 2026-06-27T19:13:21 - `35d33eaf-2aad-4754-8c3e-650bb7940593.jsonl`
- `/ll:verify-issues` - 2026-06-14T00:14:00 - `7db6ce0f-4d7c-486d-927d-6804d39ee7b7.jsonl`
- `/ll:verify-issues` - 2026-06-13T21:13:58 - `cfa3cf65-c671-4bf6-a513-92cc448d76e6.jsonl`
- `/ll:audit-issue-conflicts` - 2026-06-09T14:41:03 - `f2966d2e-3f0a-473f-b22c-b54b2a15ad9c.jsonl`
- `/ll:verify-issues` - 2026-06-09T09:21:00 - `e40557ae-4da3-4ea7-b023-bf5e57e8b61a.jsonl`
- `/ll:confidence-check` - 2026-06-07T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e92309da-4e12-4435-9943-a5af8ba8057d.jsonl`
- `/ll:refine-issue` - 2026-06-07T18:48:53 - `f6435e9b-344b-4a99-b530-899f95d858ea.jsonl`
- `/ll:wire-issue` - 2026-06-07T18:43:17 - `aa353b88-f16e-4347-9174-4ecbe1ab3f27.jsonl`
- `/ll:confidence-check` - 2026-06-07T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d266d950-9156-4f39-841f-f5de8aa33820.jsonl`
- `/ll:verify-issues` - 2026-06-05T22:34:33 - `1a4d9590-60c8-47b0-9997-b0f543664183.jsonl`
- `/ll:verify-issues` - 2026-06-05T21:00:23 - `current-session.jsonl`

- `/ll:verify-issues` - 2026-06-05T01:35:35 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/579edc97-1110-41b7-9283-1612d1e82fee.jsonl`
- `/ll:audit-issue-conflicts` - 2026-06-04T19:54:00 - `2f12f6ef-94a2-4725-933e-626b1ef4cdff.jsonl`
- `/ll:audit-issue-conflicts` - 2026-06-04T19:47:17 - `6dbe3977-0d8f-47aa-b338-9f0b66da4be5.jsonl`
- `/ll:verify-issues` - 2026-06-03T22:42:45 - `25083174-f806-4589-a206-0f8b53978497.jsonl`
- `/ll:audit-issue-conflicts` - 2026-06-03T22:04:03 - `882d6aa0-cbf0-47c3-9d9c-32d8d6c6ef92.jsonl`
- `/ll:format-issue` - 2026-06-03T19:23:35 - `1f79d2d5-df37-42dc-a0f8-73e20acc795b.jsonl`
- `/ll:scope-epic` - 2026-06-03T19:12:39Z - `87e9f36b-36c2-4e9e-a0c8-3a57aa45d1f5.jsonl`

## Verification Notes
_Added by `/ll:verify-issues` (2026-06-27):_ The Readiness/Concerns section contains a stale note stating the `parallel_orchestrator.py` path 'has not yet been corrected'. This is wrong — the Integration Map already uses the correct path `scripts/little_loops/parallel/orchestrator.py`, which exists. Ignore that stale note.

- **Path correction needed**: References `scripts/little_loops/parallel_orchestrator.py` (standalone file)
  but `ParallelOrchestrator` is at `scripts/little_loops/parallel/orchestrator.py` (subpackage).
- `sprint.py` and `cli/sprint/run.py` — CORRECT.
- `loops/ll-sprint.yaml` does not exist (expected).

- `/ll:verify-issues` - 2026-06-05 - Feature not implemented. Body reference to `scripts/little_loops/parallel_orchestrator.py` is incorrect — `ParallelOrchestrator` lives at `scripts/little_loops/parallel/orchestrator.py`. This was flagged previously but never corrected. Fix path reference before starting.
- `/ll:verify-issues` - 2026-06-13 - Status corrected from `open` → `blocked` (has active blocked_by items). ENH-2106 removed from `blocked_by` (now `done`). Added `blocks: [ENH-1903]` backlink. Stale path reference still present in Integration Map — must be corrected before implementing.
- 2026-06-13: Corrected Integration Map path: `parallel_orchestrator.py` → `parallel/orchestrator.py`. Feature is unimplemented (no ll-sprint.yaml, no plan subcommand exist yet). File references otherwise accurate.
- 2026-06-18 (OUTDATED): `loops/ll-sprint.yaml` still does not exist; `ll-sprint plan --json` subcommand not registered. Infrastructure code (`get_execution_waves()`, `refine_waves_for_contention()`, `ParallelOrchestrator`) confirmed present at correct paths. Issue remains accurately described and blocked on FEAT-1901/2000/2001.
