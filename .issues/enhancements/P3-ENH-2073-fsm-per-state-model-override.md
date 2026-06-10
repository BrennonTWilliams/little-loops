---
id: ENH-2073
title: FSM per-state model override for prompt and slash_command states
type: ENH
priority: P3
status: open
captured_at: '2026-06-10T16:02:38Z'
discovered_date: '2026-06-10'
discovered_by: capture-issue
decision_needed: false
confidence_score: 100
outcome_confidence: 63
score_complexity: 13
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 0
---

# ENH-2073: FSM per-state model override for prompt and slash_command states

## Summary

Add a `model:` field to individual FSM state definitions that overrides the host CLI's default model for that state's execution. The override applies only to non-bash states (`action_type: prompt` or `slash_command`); bash/shell states are unaffected.

## Motivation

Loop authors today can only set one model for the entire run (via `--model` CLI flag or host default). Some loops contain states with very different cost/quality profiles:

- A lightweight **triage** or **routing** state benefits from a fast, cheap model (e.g. Haiku).
- A **code generation** or **semantic evaluation** state needs a high-quality model (e.g. Sonnet or Opus).
- A **vision-based** scoring state already routes through `VISION_MODEL` env vars at the prompt level, but there's no first-class harness support for it.

Allowing per-state model overrides makes this cost/quality tradeoff explicit and portable, without requiring callers to splice `--model` into prompt text or manage env vars manually.

## Success Metrics

- `ll-loop validate` exits 0 on a loop YAML that uses per-state `model:` overrides
- Integration test confirms `--model <id>` is passed to the host runner for overridden states and absent for states without `model:`
- No regression in the existing loop test suite (`python -m pytest scripts/tests/`)

## Scope Boundaries

- **In scope**: `model:` field for `action_type: prompt` and `slash_command` states; schema validation WARNING for `model:` on shell/mcp_tool/contract states; JSON Schema update (`docs/reference/schemas/`); `LOOPS_GUIDE.md` state-definition reference table entry
- **Out of scope**: `shell`, `mcp_tool`, and `contract` states (host CLI not invoked — field is ignored with a WARNING, not blocked); global `--model` CLI flag behavior (unchanged); new CLI flags or config keys

## Proposed API

In a loop YAML state definition, add an optional `model:` key:

```yaml
states:
  triage:
    action: /ll:some-quick-check
    model: claude-haiku-4-5-20251001   # cheap routing state
    on_yes: generate
    on_no: done

  generate:
    action: /ll:generate-code
    # no model: key → inherits host default (or --model flag)
    on_success: evaluate

  evaluate:
    action: /ll:semantic-review
    model: claude-opus-4-8              # expensive but high-quality
    on_yes: done
    on_no: generate
```

The `model:` key is **ignored** for `action_type: shell`, `mcp_tool`, and `contract` states, since those don't invoke the host CLI. A validation warning should be emitted if `model:` is set on a shell state.

## Implementation Steps

### 1. Schema — `scripts/little_loops/fsm/schema.py`

- Add `model: str | None = None` to `StateConfig` dataclass (around line 416 where `action_type` lives).
- Update `StateConfig.to_dict()` to emit `model` when set.
- Update `StateConfig.from_dict()` to read `model` from raw data.

### 2. Executor — `scripts/little_loops/fsm/executor.py`

- In `_run_action()` (around line 1095–1105), when dispatching to `action_runner.run()` for `action_mode == "prompt"`, pass `model=state.model` alongside `agent` and `tools`.
- `ActionRunner.run()` in `runners.py` already accepts keyword args threaded through to `host_runner`; verify signature and add `model: str | None = None` if missing.
- `host_runner.build_streaming()` already emits `--model <value>` when `model` is set (line 288–289 in `host_runner.py`); no change needed there.

### 3. Validation — `scripts/little_loops/fsm/validation.py`

- Add a validation rule: if `state.model` is set and `_action_mode(state)` is not `"prompt"`, emit a `WARNING` with message: `"model: override is ignored for shell/mcp_tool/contract states"`.

### 4. Schema doc / YAML schema

- Add `model` to the JSON Schema for state definitions in `docs/reference/schemas/` (regenerate via `ll-generate-schemas`).
- Document the field in `docs/guides/LOOPS_GUIDE.md` under the state-definition reference table.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**⚠ Correction to Step 2**: `build_streaming()` (`host_runner.py:233`) does **not** currently accept a `model` parameter — only `build_blocking_json()` (line 274) does. The change requires threading `model` through **four layers** before it reaches the CLI args: `executor._run_action()` → `action_runner.run()` → `subprocess_utils.run_claude_command()` → `host_runner.build_streaming()`. See Integration Map for per-file guidance.

**Additional file required**: `scripts/little_loops/subprocess_utils.py:252` (`run_claude_command()`) must also accept `model: str | None = None` and forward it to `resolve_host().build_streaming(...)` at lines 298–304.

**`MockActionRunner` in executor tests**: `test_fsm_executor.py:46` — this mock's `run()` signature (lines 46–59) must be updated to accept `model=None` (same `del` disposal pattern as `agent`/`tools`) to remain Protocol-compliant after the Protocol update.

### 5. Tests

- Unit test: `StateConfig.from_dict` round-trips `model` field.
- Integration test: a loop YAML with `model: claude-haiku-4-5-20251001` on one state causes `--model claude-haiku-4-5-20251001` to be passed to the host runner for that state and not for others.
- Validation test: `model:` on a shell state emits WARNING.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

6. Update `scripts/little_loops/fsm/runners.py` — add `model` to `SimulationActionRunner.run()` `del` statement alongside `agent`, `tools`
7. Update `scripts/tests/test_fsm_persistence.py:636` — add `model: str | None = None` to its local `MockActionRunner.run()` signature (lines 636–661) and `del` list (**HIGH BREAK RISK** if missed)
8. Update `scripts/tests/test_fsm_executor.py:5015,5055` — add `model: str | None = None` to two inline `CapturingRunner.run()` definitions in `TestAgentToolsPassThrough`
9. Update `scripts/little_loops/fsm/fsm-loop-schema.json` — add `model` property to state-level schema properties alongside `agent` and `tools`
10. Update `docs/reference/API.md` — add `model: str | None = None` to StateConfig dataclass listing, ActionRunner Protocol signature, and `build_streaming()` signature
11. Update `docs/generalized-fsm-loop.md` — add `model: string` row to state-field reference table (line ~348, alongside `agent:` and `tools:`)
12. Update `docs/reference/HOST_COMPATIBILITY.md` — add `model` to `build_streaming` parameter docs in orchestration CLI section
13. Add `test_model_kwarg_forwarded` to `TestDefaultActionRunnerSlashPath` in `scripts/tests/test_fsm_runners.py`
14. Add model flag test to `scripts/tests/test_subprocess_utils.py` `TestRunClaudeCommandAgentToolsFlags` class
15. Confirm contributed-runner dispatch in `executor._run_action()` does NOT forward `model` (extension runners don't invoke host CLI)
16. Update `scripts/tests/test_fsm_persistence.py:1950,2010,2095` — add `model: str | None = None` to `CaptureAndShutdownRunner`, `ShutdownAfterFirstRunner`, `ProgressTrackingRunner` signatures and their `del` statements (**HIGH BREAK RISK**)
17. Update `scripts/tests/test_fsm_executor.py:4254` — add `model: str | None = None` to `TimeoutCapturingRunner.run()` in `TestDefaultTimeout`
18. Update `scripts/tests/test_usage_journal.py` — add `model: str | None = None` to `MockActionRunner.run()` signature and `del` statement
19. Update `scripts/tests/helpers.py:17` — add `model: str | None = None` to `make_test_state()` factory signature and pass through to `StateConfig()`
20. Add `TestPerStateModelForwarding` to `scripts/tests/test_ll_loop_execution.py` — end-to-end test asserting `state.model` threads through `PersistentExecutor` to subprocess argv
21. Update `docs/development/TESTING.md` — add `model: str | None = None` to `MockActionRunner.run()` example in `#### Custom Mock Classes` section
22. Update `CHANGELOG.md` — add entry for the `model:` field addition

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/schema.py` — add `model: str | None = None` to `StateConfig` (line 354 dataclass; insert after `tools: list[str] | None = None` at line 446); update `to_dict()` guards (lines 513–516) and `from_dict()` reads (lines 596–597) following `agent`/`tools` pattern
- `scripts/little_loops/fsm/executor.py` — in `_run_action()` (line 1047), extend the `action_runner.run()` call at line 1103 with `model=state.model if action_mode == "prompt" else None`
- `scripts/little_loops/fsm/runners.py` — add `model: str | None = None` to `ActionRunner` Protocol `run()` (line 33, signature at lines 36–62) and `DefaultActionRunner.run()` (line 71); thread `model` through to `run_claude_command()`
- `scripts/little_loops/subprocess_utils.py` — add `model: str | None = None` to `run_claude_command()` (line 252); pass it to `resolve_host().build_streaming(...)` at lines 298–304
- `scripts/little_loops/host_runner.py` — add `model: str | None = None` to `build_streaming()` in the `HostRunner` Protocol (class at line 153; `build_streaming()` at line 173) and all concrete runners: `ClaudeCodeRunner` (line 233), `CodexRunner` (line 463), `OpenCodeRunner` (line 637), `PIRunner` (line 708); emit `--model <value>` when set (follow the pattern in `build_blocking_json()` at line 289: `if model: args += ["--model", model]`)
- `scripts/little_loops/fsm/validation.py` — add WARNING rule in `_validate_state_action()` (line 482): if `state.model` is set and `_action_mode(state) != "prompt"`, emit `ValidationError(message="model: override is ignored for shell/mcp_tool/contract states", path=f"{path}.model", severity=ValidationSeverity.WARNING)`
- `docs/guides/LOOPS_GUIDE.md` — add `model:` row to state-definition reference table
- `docs/reference/schemas/` — regenerate via `ll-generate-schemas` after schema.py change

### Dependent Files (Callers/Importers)
- `scripts/tests/test_fsm_executor.py:46` — `MockActionRunner.run()` signature (lines 46–59) must add `model: str | None = None` to remain Protocol-compliant; uses `del` to discard kwargs, so same pattern applies
- `scripts/tests/test_host_runner.py` — existing `TestClaudeCodeRunner.test_build_streaming_includes_agent_and_tools` (line 145) is the reference for adding a `build_streaming` + `model` assertion test

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/extension.py` — `ActionProviderExtension.provided_actions()` returns `dict[str, ActionRunner]`; contributed runners registered via `wire_extensions` → `FSMExecutor._contributed_actions` must match the updated Protocol; verify whether the contributed-runner dispatch in `_run_action()` (currently omits `agent`/`tools`) should also forward `model`
- `scripts/little_loops/cli/loop/testing.py` — `cmd_test()` constructs `DefaultActionRunner` and calls `runner.run()` directly; safe if `model` has `None` default, but should be verified post-change
- `scripts/tests/test_fsm_persistence.py:636` — second independent `MockActionRunner.run()` (lines 636–661) implementing the `ActionRunner` Protocol; must add `model: str | None = None` and `model` to its `del` statement — **HIGH BREAK RISK** if omitted
- `scripts/tests/test_fsm_executor.py:5015,5055` — `TestAgentToolsPassThrough` has two inline `CapturingRunner.run()` definitions that mirror the Protocol; both need `model: str | None = None` added
- `scripts/tests/test_fsm_persistence.py:1950,2010,2095` — `CaptureAndShutdownRunner` (line 1950), `ShutdownAfterFirstRunner` (line 2010), `ProgressTrackingRunner` (line 2095): all implement `ActionRunner` Protocol with explicit `del` pattern; need `model: str | None = None` added to signature and `del` statement — **HIGH BREAK RISK** if omitted
- `scripts/tests/test_fsm_executor.py:4254` — `TimeoutCapturingRunner` in `TestDefaultTimeout`: explicit Protocol implementation needing `model: str | None = None`
- `scripts/tests/test_usage_journal.py` — `MockActionRunner` implements the `ActionRunner` Protocol; needs `model: str | None = None` added to signature and `del` statement

### Similar Patterns
- `scripts/little_loops/fsm/schema.py:445` — `agent: str | None = None` and `tools: list[str] | None = None` are the exact precedent for the new `model` field declaration, `to_dict()` guard, and `from_dict()` read
- `scripts/little_loops/host_runner.py:274` — `build_blocking_json()` already accepts `model` and emits `--model`; `build_streaming()` follows the same arg-building pattern

### Tests
- `scripts/tests/test_fsm_schema.py` — add `TestModelStateConfig` class after `TestAgentToolsStateConfig` (line 2277), mirroring its 11-method structure (defaults None, accepts value, `to_dict` includes/excludes, `from_dict` reads/defaults, round-trip, and edge cases)
- `scripts/tests/test_fsm_executor.py` — add integration test with a capturing mock that records the `model` kwarg and asserts it is passed only for prompt states
- `scripts/tests/test_fsm_validation.py` — add WARNING assertion test for `model:` on a shell state, following `TestArtifactIsolation` pattern (call `validate_fsm(fsm)`, filter for `ValidationSeverity.WARNING`, assert message contains "model")
- `scripts/tests/test_host_runner.py` — add `test_build_streaming_with_model` following `test_build_blocking_json_argv` at line 297 (assert `"--model"` and model ID in `invocation.args`)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_fsm_runners.py` — add `test_model_kwarg_forwarded` to `TestDefaultActionRunnerSlashPath` (line ~295), mirroring the existing `test_agent_kwarg_forwarded` pattern; patches `run_claude_command` and asserts `model` kwarg is forwarded
- `scripts/tests/test_subprocess_utils.py` — add to `TestRunClaudeCommandAgentToolsFlags` (line ~1761): test asserting `--model <id>` appears in argv when `model=` is passed and is absent when `model=None`
- `scripts/tests/helpers.py:17` — `make_test_state()` factory missing `model: str | None = None` parameter; add it to the signature and pass through to `StateConfig()`; used by 6 test files (`test_ll_loop_display.py`, `test_cli_loop_layout.py`, `test_state_feed_renderer.py`, `test_review_loop.py`, `test_ll_loop_execution.py`, `test_snapshot_loop_layout.py`)
- `scripts/tests/test_ll_loop_execution.py` — `TestEndToEndExecution` class covers global `fsm.llm.model` but not per-state `state.model`; add `TestPerStateModelForwarding` class asserting `state.model` threads through `PersistentExecutor` to subprocess argv

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md` — add `model: str | None = None` to: (1) `#### StateConfig` dataclass field listing; (2) `#### ActionRunner Protocol` `run()` signature; (3) `## little_loops.host_runner` → `build_streaming()` signature for all runner classes
- `docs/generalized-fsm-loop.md` — add `model: string` row to state-field reference table alongside existing `agent:` and `tools:` entries (line ~348)
- `docs/reference/HOST_COMPATIBILITY.md` — update `build_streaming` parameter documentation in the orchestration CLI section to include `model`
- `docs/development/TESTING.md` — `#### Custom Mock Classes` section shows `MockActionRunner.run()` with explicit `agent`/`tools` but missing `model: str | None = None`; will document incorrect Protocol signature after change
- `CHANGELOG.md` — add entry documenting `model:` field addition to `StateConfig`, `ActionRunner.run()`, `run_claude_command()`, and `build_streaming()`

### Configuration / Schema

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/fsm/fsm-loop-schema.json` — add `model` property to state-level JSON Schema properties alongside `agent` and `tools`; this schema drives loop YAML validation tooling

## Root Cause

`StateConfig` (schema.py) and `executor._run_action()` have no mechanism to thread a per-state model through to the `action_runner.run()` call. The host runner already supports `--model`; it's purely a missing data-flow connection from YAML → schema → executor → runner.

## API / Interface Changes

- **YAML loop files**: new optional `model:` key at state level (non-breaking; absent = existing behaviour).
- **`StateConfig` dataclass**: new `model: str | None` field.
- **`ActionRunner.run()`**: needs `model: str | None = None` added (confirmed missing from Protocol at `runners.py:33` and `DefaultActionRunner.run()` at line 71).
- **`subprocess_utils.run_claude_command()`** (`subprocess_utils.py:252`): needs `model: str | None = None` to thread through to `build_streaming()`.
- **`host_runner.build_streaming()`** (`host_runner.py:233`): needs `model: str | None = None` in all runner implementations (`ClaudeCodeRunner`, `CodexRunner`, `OpenCodeRunner`, `PIRunner`) and the `HostRunner` Protocol (line 173). Currently only `build_blocking_json()` emits `--model`.
- No CLI changes required.

## Acceptance Criteria

- [ ] A loop YAML with `model: <id>` on a prompt state invokes the host CLI with `--model <id>` for that state only.
- [ ] States without `model:` continue using the default/flag-provided model.
- [ ] Shell/mcp_tool/contract states with `model:` emit a validation WARNING (not ERROR) and run normally.
- [ ] `ll-loop validate` passes on a loop using per-state `model:` overrides.
- [ ] Existing loops without `model:` are unaffected (backwards-compatible).

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| [docs/ARCHITECTURE.md](../../docs/ARCHITECTURE.md) | FSM executor and runner design |
| [docs/reference/API.md](../../docs/reference/API.md) | `host_runner` API — `build_streaming` model param |
| [docs/guides/LOOPS_GUIDE.md](../../docs/guides/LOOPS_GUIDE.md) | State definition reference |

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-06-10_

**Readiness Score**: 100/100 → PROCEED
**Outcome Confidence**: 63/100 → MODERATE

### Outcome Risk Factors
- Wide Protocol implementation surface — 11 ActionRunner.run() implementations need `model: str | None = None` added; 4 marked HIGH BREAK RISK in wiring analysis (test_fsm_persistence.py:636, 1950, 2010, 2095). Mitigation: test suite raises TypeError on any missed update — run tests incrementally.
- Large change breadth (24+ files) with entirely mechanical depth — follow the enumerated wiring list step-by-step.

## Session Log
- `/ll:confidence-check` - 2026-06-10T00:00:00Z - `8869adca-05cd-442c-8558-9f490ec707af.jsonl`
- `/ll:wire-issue` - 2026-06-10T18:55:43 - `c8a2bd06-34eb-4c38-8e58-366d997f06c6.jsonl`
- `/ll:refine-issue` - 2026-06-10T18:43:45 - `a812e6de-569b-4295-94fb-0ab38cecaff0.jsonl`
- `/ll:refine-issue` - 2026-06-10T18:43:26 - `a812e6de-569b-4295-94fb-0ab38cecaff0.jsonl`
- `/ll:confidence-check` - 2026-06-10T00:00:00Z - `91904165-ee53-4778-a299-73d67da0c4b5.jsonl`
- `/ll:wire-issue` - 2026-06-10T18:29:52 - `9de33298-3da0-44eb-8a7b-15b8da33a768.jsonl`
- `/ll:refine-issue` - 2026-06-10T18:16:21 - `88c91679-4f83-4187-96a0-385cb4afe8c1.jsonl`
- `/ll:format-issue` - 2026-06-10T16:07:29 - `44235a11-96b5-42bf-a8ef-bffe384cdaf0.jsonl`
- `/ll:capture-issue` - 2026-06-10T16:02:38Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/dae493a0-2705-496d-9f16-5c7e9a05de45.jsonl`

---
## Status

**Current**: open
