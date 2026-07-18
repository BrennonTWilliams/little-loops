---
id: ENH-2668
title: Extract shared runner abstraction (RunnerType enum + ActionSpec) from ll-harness/ll-action/ll-loop
type: ENH
priority: P2
status: done
captured_at: '2026-07-18T00:00:00Z'
completed_at: '2026-07-18T15:37:29Z'
discovered_date: 2026-07-18
discovered_by: capture-issue
parent: EPIC-2670
relates_to:
- FEAT-2669
labels:
- refactor
- runners
- cli
decision_needed: false
confidence_score: 100
outcome_confidence: 79
score_complexity: 16
score_test_coverage: 23
score_ambiguity: 22
score_change_surface: 18
---

# ENH-2668: Extract shared runner abstraction (RunnerType/ActionSpec)

## Summary

Extract `ll-harness`'s five-way dispatch (`skill`/`cmd`/`mcp`/`prompt`/`dsl`)
plus FSM loop execution into a real `RunnerType` enum + `ActionSpec`
dataclass (name, runner type, invocation args, timeout, etc.) with a single
dispatch function returning `RunnerResult`. `ll-action`, `ll-harness`, and
`ll-loop run` become thin callers of this shared primitive instead of each
owning their own if/elif dispatch. This is Phase 1 of
`thoughts/plans/2026-07-17-generic-ll-queue-design.md` and the prerequisite
for FEAT-2669 (generic `ll-queue`).

## Motivation

- No shared runner abstraction exists today. `ll-action` (`cli/action.py`)
  dispatches via if/elif over skill-name strings calling
  `run_claude_command()`; `ll-harness` (`cli/harness.py:119-170, 450-469`)
  dispatches via argparse subparsers over five runner kinds — also if/elif,
  not an enum/protocol.
- The only shared type between them is `RunnerResult` (`harness.py:25-33`) —
  an output shape, not a dispatch abstraction.
- A generic queue (FEAT-2669) needs a "run this generic work item" primitive;
  this extraction provides it. It is independently useful even if the queue
  never ships: it removes the `ll-action`/`ll-harness` dispatch duplication.

## Current Behavior

- Three CLIs (`ll-action`, `ll-harness`, `ll-loop run`) each own their own
  dispatch logic over overlapping runner kinds; adding a runner type means
  touching each in a different way.

## Expected Behavior

- A `RunnerType` enum covering at least `skill`/`cmd`/`mcp`/`prompt`/`dsl`
  plus FSM loop execution.
- An `ActionSpec` dataclass (name, runner type, invocation args, timeout,
  etc.) and a single dispatch function `run(spec: ActionSpec) -> RunnerResult`.
- `ll-action`, `ll-harness`, and `ll-loop run` call the shared primitive;
  their existing CLI UX and flags are unchanged (no new scheduling behavior).

## Proposed Solution

1. New module (e.g. `scripts/little_loops/runners/` or
   `scripts/little_loops/runner_spec.py`) holding `RunnerType`, `ActionSpec`,
   `RunnerResult` (moved from `harness.py`), and the dispatch function.
2. Port `ll-harness`'s five subparser paths onto the dispatch function.
3. Port `ll-action`'s skill-name if/elif onto `ActionSpec(runner=skill, ...)`.
4. Wrap FSM loop execution (`PersistentExecutor`/`run_foreground` path in
   `cli/loop/run.py`) as a `RunnerType.LOOP` spec. Watch for impedance
   mismatch here — long-running/persistent execution vs. one-shot runners is
   the riskiest part of the extraction; if it doesn't fit cleanly, keep loop
   execution as a thin adapter rather than forcing it into the one-shot shape.
5. Keep `RunnerResult` importable from its old location (re-export) to avoid
   breaking existing importers.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in
the implementation:_

6. Update the `unittest.mock.patch()` target strings in `test_cli_harness.py`,
   `test_action.py`, and `test_cli_loop_lifecycle.py` that reference
   `little_loops.cli.harness.resolve_host`/`call_mcp_tool`/
   `evaluate_llm_structured`/`cmd_dsl`, `little_loops.cli.action.resolve_host`/
   `subprocess.run`, and `little_loops.cli.loop.run.os.getpid` to their new
   module paths if the dispatch calls move.
7. Re-verify the file/line-anchored claims in `docs/reference/EVENT-SCHEMA.md`
   (`RunnerResult.exit_code`) and `docs/observability/otel-mapping.md`
   (`cli/action.py`'s `cmd_invoke` as an OTel caller) after the move; update
   anchors if they drift.
8. Add a `RunnerResult` re-export test and a `FrozenInstanceError` test for
   `ActionSpec`, modeled on `test_host_runner.py`'s `HostInvocation`
   coverage, to lock in the byte-for-byte-unchanged and frozen-boundary
   guarantees this issue's AC and Codebase Research Findings call for.

## Integration Map

### Files to Modify

- `scripts/little_loops/cli/harness.py` — dispatch extracted; becomes caller
- `scripts/little_loops/cli/action.py` — becomes caller
- `scripts/little_loops/cli/loop/run.py` — loop execution exposed via spec
- New runner module (see Proposed Solution)

### Dependent Files (Callers/Importers)

- Any importers of `RunnerResult` from `harness.py` (re-export preserves them)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/extension.py` — `ActionProviderExtension.provided_actions()`
  returns `dict[str, ActionRunner]` (line 87); TYPE_CHECKING import of
  `ActionRunner` (line 28). Not in scope to change, but the new module's
  docstrings should disambiguate `ActionRunner`/`ActionResult` (FSM-internal)
  from `RunnerType`/`ActionSpec`/`RunnerResult` (new) so readers don't
  conflate the two dispatch systems.
- `scripts/little_loops/cli/loop/testing.py` — imports `DefaultActionRunner`
  (line 25), `SimulationActionRunner` (line 65), `ActionResult` from
  `fsm.executor` (line 65/76) — consumer of the FSM runner abstraction that
  sits adjacent to the new one.
- `scripts/little_loops/fsm/__init__.py` — re-exports `ActionRunner`,
  `ActionResult`, `FSMExecutor`, `PersistentExecutor` — must stay stable.
- `scripts/little_loops/cli/__init__.py` — re-exports `main_harness`,
  `main_action`, `main_loop` (lines 44/64/70) — entry-point re-export
  surface that must remain importable from the same location.
- `scripts/little_loops/cli/loop/_helpers.py` — `run_foreground()` (1627)
  and `run_background()` (1463) call `resolve_host()`; relevant if
  `RunnerType.LOOP` wraps this orchestration per Proposed Solution step 4.
- `scripts/little_loops/cli/loop/lifecycle.py`, `info.py`, `next_loop.py` —
  import `PersistentExecutor`; downstream of the loop-execution wrap.

### Similar Patterns

- `harness.py` five-way subparser dispatch is the closest existing template

### Tests

- New unit tests for `ActionSpec` normalization + dispatch per runner type
- Existing `ll-action`/`ll-harness`/`ll-loop` test suites must stay green
  unchanged (behavior-preserving refactor)

_Wiring pass added by `/ll:wire-issue`:_
- **Mock-patch coupling risk** — these `unittest.mock.patch()` targets are
  module-path-qualified at the *current* call site (the standard convention
  here); they break if the dispatch calls physically move out of
  `cli/harness.py`/`cli/action.py` into the new module:
  - `test_cli_harness.py` — `patch("little_loops.cli.harness.resolve_host", ...)`
    (lines 704, 725), `patch("little_loops.cli.harness.call_mcp_tool", ...)`
    (715), plus ~25 more call sites patching `evaluate_llm_structured`/
    `cmd_dsl` at the same module path.
  - `test_action.py` — `patch("little_loops.cli.action.resolve_host", ...)`
    (482), `patch("little_loops.cli.action.subprocess.run", ...)` (484).
  - `test_cli_loop_lifecycle.py` — `patch("little_loops.cli.loop.run.os.getpid", ...)`
    (497).
  - The issue's own AC ("no test modifications other than import-path
    updates") already anticipates this; these patch-target string updates
    count as import-path updates, not logic changes.
- Additional test files touching the affected modules, beyond those already
  listed under Codebase Research Findings: `test_harness_optimize.py`,
  `test_host_guard.py` (tests `DefaultActionRunner`), `test_cli_loop_worktree.py`,
  `test_cli_loop_background.py`, `tests/integration/test_loop_run_e2e.py`,
  `test_subprocess_mocks.py`, `test_ll_loop_commands.py`,
  `test_cli_loop_dispatch.py`, `test_cli_loop_queue.py`,
  `test_cli_loop_layout.py`, `test_cli_loop_testing.py`,
  `test_autodev_decision_gate.py`, `test_usage_journal.py`,
  `test_learning_state.py` (import `ActionResult`), `test_builtin_loops.py`,
  `test_create_loop.py`, `test_ll_loop_integration.py`, `test_rn_implement.py`,
  `test_rn_plan.py`, `test_cross_host_baseline.py`, `test_ll_logs.py` (imports
  `main_harness` incidentally, not a dispatch-coverage risk),
  `test_create_eval_from_issues.py` (imports `_parse_harness_args`, `DslTask`
  from `harness.py`).
- No subprocess-level/out-of-process integration test exists today for
  `ll-action`, `ll-harness`, or `ll-loop run` (grep for
  `subprocess.run(["ll-harness"...`/`["ll-action"...`/`["ll-loop"...` across
  `scripts/tests/` returned no matches) — a gap relative to the
  "byte-for-byte CLI UX unchanged" AC; closest existing analogue is
  `test_claude_runner_matches_legacy_args` (`test_host_runner.py:121-140`),
  which asserts a literal argv list.
- New tests to write (confirmed greenfield — repo-wide grep found zero
  existing references to `RunnerType`/`ActionSpec`):
  - `FrozenInstanceError` test for `ActionSpec`, modeled on `HostInvocation`'s
    frozen-dataclass convention (`test_host_runner.py:15` import + docstring
    at `host_runner.py:97-109`).
  - Registry-completeness test (all five harness runner kinds +
    `RunnerType.LOOP` present in the dispatch table), modeled on
    `test_codex_runner_registered` (`test_host_runner.py:213-218`).
  - Per-`RunnerType` argv/`RunnerResult`-shape snapshot test, modeled on
    `test_claude_runner_matches_legacy_args` (`test_host_runner.py:121-140`),
    to enforce byte-for-byte CLI UX at the unit level.
  - `RunnerResult` re-export test (`from little_loops.cli.harness import
    RunnerResult` still resolves post-move) — required by Proposed Solution
    step 5.

### Documentation

- `docs/reference/API.md` — document the new runner module

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/EVENT-SCHEMA.md:1050` — references `RunnerResult.exit_code`
  by name; update if the module path or name changes.
- `docs/reference/CLI.md:178-221` — documents `ll-harness`'s five-way
  dispatch and `0/1/2` exit-code contract with literal invocation examples;
  the acceptance surface any extraction must not drift from.
- `docs/ARCHITECTURE.md:187-193,827-850` — package-layout comment for
  `cli/harness.py`; `HostRunner` section explicitly lists `ll-action`/
  `ll-loop` among callers routed through `resolve_host()` (relevant since
  the new dispatch function will itself call `resolve_host()`).
- `docs/observability/otel-mapping.md:96-99` — names `cli/action.py`
  (`cmd_invoke`'s call to `run_claude_command`) as one of three callers
  stamping `gen_ai.*` OTel attributes; re-verify if that call relocates.
- `docs/development/CONFORMANCE.md:3-49` — describes a pytest-parametrized
  conformance suite validating host-runner invocation construction for
  `ll-action`'s golden path; behavioral, no textual change needed, but is a
  coupling point to keep green.
- `commands/help.md`, `skills/create-eval-from-issues/SKILL.md:162-166`,
  `docs/reference/COMMANDS.md:2266` — embed literal `ll-harness`/`ll-action`
  invocation examples; CLI-surface only, should not need edits if UX stays
  byte-for-byte unchanged, but are the examples that would surface any
  drift.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Verified/corrected line references** (issue text above cites approximate
ranges; confirmed exact anchors):
- `RunnerResult` dataclass: `scripts/little_loops/cli/harness.py:25-33` —
  confirmed exact (`stdout`, `stderr`, `exit_code`, `timed_out=False`,
  `error=None`).
- Five-way subparser construction (not the dispatch itself):
  `_build_harness_parser()` at `harness.py:61-184` (`skill_p` 119, `cmd_p`
  132, `mcp_p` 140, `prompt_p` 156, `dsl_p` 170).
- The actual if/elif dispatch routing `args.runner` to a handler is in
  `main_harness()`, `harness.py:457-469` (function starts at 450).
- Dispatch targets: `cmd_skill()` (277), `cmd_cmd()` (303), `cmd_mcp()`
  (357), `cmd_prompt()` (380), `cmd_dsl()` (402) — `cmd_dsl` is a batch
  driver that calls `cmd_prompt()` per task, not an independent execution
  path.
- `ll-action`'s dispatch is `main_action()` if/elif over subcommand name at
  `action.py:273-281` (`invoke`/`capabilities`/`list`) — narrower than
  harness's runner-type dispatch. Its execution path (`cmd_invoke()`, line
  67) calls `run_claude_command()` from `subprocess_utils.py:282` directly —
  **not** `resolve_host()` — a `claude`-specific legacy path that predates
  `host_runner.py`. Only `cmd_capabilities()` (line 152) calls
  `resolve_host().describe_capabilities()`.
- FSM per-state dispatch: `FSMExecutor._action_mode()` at
  `fsm/executor.py:1903-1918` maps `state.action_type` (a bare `str | None`
  field, `fsm/schema.py:534` — not an enum) to `"contract"`/`"mcp_tool"`/
  `"prompt"`/`"shell"`/`"contributed"`. Actual dispatch is
  `_run_action()` at `fsm/executor.py:1452-1621`: `mcp_tool` and
  `contributed` are special-cased directly; everything else (`shell`,
  `prompt`, `contract`) falls through to `self.action_runner.run(...)` —
  the `ActionRunner` Protocol (`fsm/runners.py:36`), concretely
  `DefaultActionRunner.run()` (`fsm/runners.py:91`), which itself only
  branches on a boolean `is_slash_command`, not a runner-type enum.
- FSM's result type is `ActionResult` (`fsm/types.py:69-87`), a superset of
  `RunnerResult`: adds `duration_ms`, `usage_events: list[TokenUsage]`,
  `peak_rss_mb`; renames `stdout`→`output`; encodes timeout as
  `exit_code=124` + `stderr="Action timed out"` instead of a dedicated
  `timed_out` bool.

**Impedance-mismatch detail** (the FSM/one-shot risk flagged in Proposed
Solution step 4): `ll-harness`/`ll-action` are single blocking calls
(parse argv → dispatch → subprocess → print → exit). The FSM path
(`cli/loop/run.py:cmd_run()` at line 91 → `PersistentExecutor`
(`fsm/persistence.py:629`) → `run_foreground()`
(`cli/loop/_helpers.py:1627`)) is a stateful, resumable engine: one
invocation executes many states over a long duration, with per-state
persistence-to-disk, an event bus, signal handling, scope locking
(`LockManager`) spanning the *entire run* (not one action), and a baseline
A/B execution mode (`_execute_with_baseline()`, `executor.py:1920`) that
runs two arms concurrently via `ThreadPoolExecutor`. None of this exists in
the one-shot runners. `ActionRunner.run()` (the FSM's existing internal
runner interface) is itself agnostic to a `RunnerType`-style enum — it only
takes `is_slash_command: bool` plus optional kwargs — so wrapping loop
execution as `RunnerType.LOOP` means wrapping the *whole `cmd_run()`
orchestration*, not just `_run_action()`.

**Pattern to model after**: `scripts/little_loops/host_runner.py` is the
existing precedent for exactly this class of refactor (CLAUDE.md's "Host
CLI Abstraction" section already mandates routing through it). Structure:
`HostCapabilities` (frozen dataclass, `host_runner.py:76-94`),
`HostInvocation` (frozen dataclass value object, `host_runner.py:97-115` —
docstring: "frozen because instances cross the runner/caller boundary;
mutating one in-flight would silently corrupt argv"), `HostRunner`
(`@runtime_checkable` `Protocol`, `host_runner.py:159-217`, `name: str`
class attr + `build_*` factory methods), a name-keyed registry
`_HOST_RUNNER_REGISTRY` (`host_runner.py:1154-1161`, explicitly mirrors
`hooks/__init__.py:_dispatch_table`), and single entry point
`resolve_host()` (`host_runner.py:1182-1227`). `ActionSpec`/`RunnerType`
should likely follow the same frozen-dataclass-crossing-a-boundary +
registry-backed-dispatch shape rather than the `Enum` + `to_dict`/`from_dict`
convention used in `parallel/types.py` (`MergeStatus`, `WorkerStage`) — the
latter is used where the discriminator crosses a JSON/state-file
serialization boundary, which is not obviously true here since `ActionSpec`
is an in-process call.

**Additional dependent files not yet listed above:**
- `scripts/little_loops/fsm/runners.py` — `ActionRunner` Protocol (36),
  `DefaultActionRunner.run()` (91), `SimulationActionRunner.run()` (299) —
  closest existing internal runner abstraction; may be foldable into the
  new module rather than duplicated.
- `scripts/little_loops/fsm/types.py` — `ActionResult` (69-87), to
  reconcile/re-export against the new `RunnerResult`.
- `scripts/little_loops/subprocess_utils.py` — `run_claude_command()`
  (282), used by both `action.py:cmd_invoke()` and
  `fsm/runners.py:DefaultActionRunner.run()`'s prompt path; a shared
  dependency both `ll-action` and the FSM engine already funnel through.
- `scripts/little_loops/host_runner.py` — `resolve_host()`,
  `HostInvocation`, `HostRunner` — model/dependency for the new module.

**Existing test doubles to consolidate**: `test_cli_harness.py:29-38` and
`test_action.py:25-50` each define a near-identical local `FakeRunner` test
double implementing the `HostRunner` Protocol surface
(`test_cli_harness.py` comments "mirroring test_action.py patterns")
instead of importing one shared fake — worth sharing once a common module
exists.

**Additional test files covering affected code** (beyond harness/action
suites already named): `test_fsm_executor.py`, `test_fsm_runners.py`,
`test_ll_loop_execution.py`, `test_fsm_persistence.py`,
`test_cli_loop_lifecycle.py`, `test_host_runner.py`,
`test_subprocess_utils.py`.

## Acceptance Criteria

- `RunnerType` + `ActionSpec` + single dispatch function exist and cover all
  five harness runner kinds plus FSM loop execution.
- `ll-action`, `ll-harness`, and `ll-loop run` route through the shared
  primitive; their CLI UX is byte-for-byte unchanged (flags, output, exit
  codes).
- No duplicated runner dispatch if/elif remains in `action.py`/`harness.py`.
- `python -m pytest scripts/tests/` exits 0 with no test modifications other
  than import-path updates.

## Scope Boundaries

- **In**: mechanical extraction, re-exports, unit tests for the new module.
- **Out**: any queueing/scheduling behavior (FEAT-2669); changing runner
  semantics, timeouts, or CLI UX; touching `ll-parallel`/`ll-sprint`.

## Related Key Documentation

| Document | Why Relevant |
|----------|--------------|
| `thoughts/plans/2026-07-17-generic-ll-queue-design.md` | Source design doc — Phase 1 |
| FEAT-2669 | Consumer of this abstraction (generic `ll-queue`) |

## Impact

- **Priority**: P2 — prerequisite for FEAT-2669; independently reduces
  duplication across three CLIs.
- **Effort**: Small-Medium — mostly mechanical, but touches three CLIs with
  existing test surfaces; FSM-loop fit is the main risk.
- **Risk**: Low — behavior-preserving refactor with existing tests as a net.
- **Breaking Change**: No — additive module + internal rewiring.

## Resolution

Extracted `RunnerType`/`ActionSpec`/`RunnerResult`/`run_action()` into new
module `scripts/little_loops/runner_spec.py`. `ll-harness`'s
`cmd_skill`/`cmd_cmd`/`cmd_mcp`/`cmd_prompt` and `ll-action`'s `cmd_invoke`
now build an `ActionSpec` and call `run_action()` instead of each
reimplementing `resolve_host()`/`subprocess`/`call_mcp_tool` dispatch.
`RunnerResult` stays importable from `little_loops.cli.harness` via
re-export. `cmd_dsl` is unchanged (already a batch driver over
`cmd_prompt`, itself now backed by `run_action`).

`RunnerType.LOOP` exists on the enum but is intentionally excluded from
`run_action()`'s dispatch table (raises `ValueError`) — FSM loop execution
is a stateful, resumable multi-state engine, not a one-shot call. Per the
issue's own Proposed Solution step 4 escape hatch, `cli/loop/run.py`'s
`cmd_run()` builds a `RunnerType.LOOP` `ActionSpec` for structural/
observability parity (logged at debug level) but keeps calling
`PersistentExecutor` directly for execution.

New tests in `scripts/tests/test_runner_spec.py`: `ActionSpec` frozen-dataclass
check, `RunnerResult` re-export check, `RunnerType` registry-completeness
check, and per-`RunnerType` dispatch-shape tests for skill/cmd/mcp/prompt.
Updated `test_cli_harness.py`'s `resolve_host`/`call_mcp_tool` mock-patch
targets from `little_loops.cli.harness.*` to `little_loops.runner_spec.*`
(import-path updates only, per AC). `test_action.py` and
`test_cli_loop_lifecycle.py` needed no patch-target changes — their mocked
symbols (`subprocess_utils.run_claude_command`, `subprocess.run`,
`os.getpid`) were already patched at their source module, not at the call
site that moved. Full suite: `python -m pytest scripts/tests/` — 15259
passed, 37 skipped. `ruff check scripts/` and `python -m mypy
scripts/little_loops/` both clean.

## Status

**Open** | Created: 2026-07-18 | Priority: P2

## Session Log
- `/ll:manage-issue` - 2026-07-18T15:36:46Z - `0bf2b2bd-57bb-46b0-8a7d-e1291320e8be.jsonl`
- `/ll:ready-issue` - 2026-07-18T15:25:29 - `227f256e-aab0-4aac-a79a-2aa2de320635.jsonl`
- `/ll:confidence-check` - 2026-07-18T00:00:00Z - `29ebb98a-04bb-4f75-82fb-7e031504071a.jsonl`
- `/ll:wire-issue` - 2026-07-18T15:21:38 - `bfd36d5e-fbfb-4fb9-83b6-f18cb917c5ff.jsonl`
- `/ll:refine-issue` - 2026-07-18T15:14:11 - `a938c9a8-83b0-4e62-850f-06f0e61837f7.jsonl`
- `/ll:capture-issue` - 2026-07-18T00:00:00Z - filed from `thoughts/plans/2026-07-17-generic-ll-queue-design.md` Phase 1 (runner abstraction extraction).
