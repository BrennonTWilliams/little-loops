---
id: FEAT-1010
type: FEAT
priority: P2
status: active
title: "Add `agent:` and `tools:` state-level fields to ll-loop FSM"
discovered_date: 2026-04-09
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 78
---

# FEAT-1010: Add `agent:` and `tools:` state-level fields to ll-loop FSM

## Summary

`ll-loop` prompt-mode states invoke `claude --dangerously-skip-permissions --verbose --output-format stream-json -p "<prompt>"` with no `--agent` or `--tools` flag. MCP tools present in `.mcp.json` arrive as deferred tools in the subprocess, and Claude's ToolSearch mechanism fails to resolve them in that context, causing the harness to stall.

Add `agent:` and `tools:` as optional state-level fields to the FSM YAML schema and thread them through to the claude CLI invocation.

## Current Behavior

`ll-loop` FSM prompt-mode states invoke `claude --dangerously-skip-permissions --verbose --output-format stream-json -p "<prompt>"` with no `--agent` or `--tools` flag. MCP tools present in `.mcp.json` arrive as deferred tools in the subprocess context, but the ToolSearch mechanism fails to resolve them, causing loops that require MCP tools (e.g., Playwright for browser-based evals) to stall indefinitely.

## Expected Behavior

FSM YAML state configs support optional `agent:` and `tools:` fields. When set on a prompt-mode state, the subprocess invocation includes `--agent <name>` and/or `--tools <csv>`, enabling MCP tools to load and resolve correctly in that state's subprocess.

## Motivation

Without these fields, FSM loops that need MCP tools (e.g., Playwright for browser-based evals) cannot wire up those tools in subprocess-spawned claude invocations. The harness stalls waiting for ToolSearch to resolve deferred tools that never fully load.

**Why both fields?**
- `agent: <name>` → passes `--agent <name>` → loads `.claude/agents/<name>.md`, picking up its system prompt and `tools:` frontmatter. DRY — no duplication. Best for harnesses that already define an agent file.
- `tools: [...]` → passes `--tools "Bash,Edit,mcp__playwright__*"` → explicitly scopes tools without needing a full agent file. Best for one-off state scoping.

## Use Case

An eval harness `execute` state that needs to run as the `exploratory-user-eval` agent (which has Playwright in its tools frontmatter):

```yaml
execute:
  action: |
    Act as the exploratory-user-eval agent defined in .claude/agents/exploratory-user-eval.md.
    Read that file and follow its instructions exactly.
  action_type: prompt
  agent: exploratory-user-eval    # NEW: loads --agent flag
```

Without this, the subprocess cannot access Playwright tools.

## Implementation Steps

### 1. `scripts/little_loops/fsm/schema.py` — Add fields to `StateConfig`

In the `StateConfig` dataclass (line 179), add after `context_passthrough`:
```python
agent: str | None = None
tools: list[str] | None = None
```

In `from_dict()` (line 289 block):
```python
agent=data.get("agent"),
tools=data.get("tools"),
```

In `to_dict()`:
```python
if self.agent is not None:
    result["agent"] = self.agent
if self.tools is not None:
    result["tools"] = self.tools
```

### 2. `scripts/little_loops/subprocess_utils.py` — Accept flags in `run_claude_command()`

Add params to signature (near line 62):
```python
agent: str | None = None,
tools: list[str] | None = None,
```

After building `cmd_args` (near line 103), before `Popen`:
```python
if agent:
    cmd_args += ["--agent", agent]
if tools:
    cmd_args += ["--tools", ",".join(tools)]
```

### 3. `scripts/little_loops/fsm/runners.py` — Thread through `ActionRunner` Protocol and `DefaultActionRunner.run()`

**Also update the `ActionRunner` Protocol signature (line 31–37)** — the Protocol and concrete class must stay in sync:
```python
def run(
    self,
    action: str,
    timeout: int,
    is_slash_command: bool,
    on_output_line: Callable[[str], None] | None = None,
    agent: str | None = None,
    tools: list[str] | None = None,
) -> ActionResult:
```

Add same params to `DefaultActionRunner.run()` signature (line 58):
```python
agent: str | None = None,
tools: list[str] | None = None,
```

Pass them in the `run_claude_command()` call (near line 94).

### 4. `scripts/little_loops/fsm/executor.py` — Extract from state and pass to runner

In `_run_action()`, the `else` branch (near line 504):
```python
result = self.action_runner.run(
    action,
    timeout=state.timeout or self.fsm.default_timeout or 3600,
    is_slash_command=action_mode == "prompt",
    on_output_line=_on_line,
    agent=state.agent if action_mode == "prompt" else None,
    tools=state.tools if action_mode == "prompt" else None,
)
```

(Only pass `agent`/`tools` for prompt-mode states — shell commands don't use claude CLI.)

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

5. Update `scripts/little_loops/fsm/fsm-loop-schema.json` — add `agent` (type: string, optional) and `tools` (type: array of string items, optional) to `stateConfig.properties`; `additionalProperties: false` is already set so this is required for YAML files using the new fields to pass schema validation
6. Update `scripts/little_loops/fsm/runners.py` `SimulationActionRunner.run()` — add `agent: str | None = None` and `tools: list[str] | None = None` to its signature (it also implements the `ActionRunner` Protocol alongside `DefaultActionRunner`)
7. Update all Protocol implementors in `scripts/tests/test_fsm_executor.py` — `MockActionRunner.run()` (line 43), `FailingRunner.run()` (line 1834), `ShutdownAfterFirstActionRunner.run()` (line 2108), `CaptureAndShutdownRunner.run()` (line 2189), `TimeoutCapturingRunner.run()` (line 3342) — add `agent`/`tools` keyword params with `None` defaults
8. Update all Protocol implementors in `scripts/tests/test_fsm_persistence.py` — `MockActionRunner.run()` (line 536), `CaptureAndShutdownRunner.run()` (line 1525), `ShutdownAfterFirstRunner.run()` (line 1582), `ProgressTrackingRunner.run()` (line 1669)
9. Write new test: `executor._run_action()` passes `agent`/`tools` only for prompt-mode states (shell-mode receives `None`) — follow `test_action_type_prompt_runs_action` at `test_fsm_executor.py:241`
10. Write new test: `DefaultActionRunner.run(agent=..., tools=...)` → `run_claude_command()` called with correct kwargs — extend `fake_run_claude_command` fixture at `test_fsm_executor.py:3011`
11. Update `docs/reference/CLI.md:236–260` — add state-level `agent:`/`tools:` YAML field documentation or reference to state config guide

## API/Interface

New optional fields in FSM YAML `StateConfig`:

```yaml
states:
  my_state:
    action: "..."
    action_type: prompt
    agent: some-agent-name        # optional: passes --agent to subprocess
    tools: ["Bash", "Edit"]       # optional: passes --tools csv to subprocess
```

Both fields are ignored for `action_type: shell` states.

## Acceptance Criteria

- [ ] `StateConfig` dataclass has `agent: str | None` and `tools: list[str] | None` fields (with `to_dict`/`from_dict` following `scope`/`timeout` patterns in `schema.py`)
- [ ] `ActionRunner` Protocol signature updated to include `agent`/`tools` params (runners.py:31–37)
- [ ] `run_claude_command()` accepts and appends `--agent` / `--tools` flags to the invocation
- [ ] `DefaultActionRunner.run()` accepts and passes through both params
- [ ] `executor.py` extracts `state.agent` / `state.tools` and passes them only for prompt-mode states
- [ ] `MockActionRunner.run()` in `test_fsm_executor.py` updated to accept new params (to satisfy Protocol)
- [ ] New tests in `test_fsm_schema.py` cover `agent`/`tools` field round-trips (following `TestSubLoopStateConfig` pattern at lines 1626–1673)
- [ ] New tests in `test_subprocess_utils.py` cover `--agent`/`--tools` appended to `cmd_args` (following pattern at lines 216–245)
- [ ] Existing tests pass: `python -m pytest scripts/tests/ -v`
- [ ] Manual smoke test: minimal loop YAML with `agent: some-agent` on a prompt state confirms `--agent some-agent` in logged claude invocation

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/schema.py` — `StateConfig` dataclass
- `scripts/little_loops/subprocess_utils.py` — `run_claude_command()`
- `scripts/little_loops/fsm/runners.py` — `DefaultActionRunner.run()`
- `scripts/little_loops/fsm/executor.py` — `_run_action()`

### Dependent Files (Callers/Importers)
- `scripts/little_loops/issue_manager.py:190,355,411` — calls `run_claude_command` via its own `_run_claude_base` alias; new `agent`/`tools` params are optional with `None` defaults, so no changes needed here
- `scripts/little_loops/parallel/worker_pool.py:626` — calls `run_claude_command` via `_run_claude_command` method; same — optional params, no changes needed
- `scripts/little_loops/cli/loop/testing.py` — references `DefaultActionRunner`; may need signature update if it instantiates directly
- Built-in loop YAMLs under `scripts/little_loops/loops/` that use `action_type: prompt` — will benefit from the new `agent:`/`tools:` fields (no code changes required; they're additive YAML fields)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/fsm/__init__.py` — re-exports `StateConfig` (line 119) and `ActionRunner` (line 88); the primary fan-out point for consumers; verify no new re-exports are needed for `agent`/`tools` handling
- `scripts/little_loops/fsm/validation.py:183–215` — `_validate_state_action()` validates state-level field constraints (e.g., `params` only valid for `mcp_tool`); if `agent`/`tools` should be constrained to prompt-mode states, this is where that logic goes
- `scripts/little_loops/extension.py:27` — imports `ActionRunner` for `ActionProviderExtension.provided_actions()`; external extension authors returning custom runners will be affected by the Protocol signature change (informational — no code change required in this repo)
- `scripts/little_loops/cli/loop/testing.py:72,85` — direct calls to `SimulationActionRunner.run()` (line 72) and `DefaultActionRunner.run()` (line 85) bypass the executor entirely; if a state has `agent:`/`tools:` set and goes through `cmd_test`, the values will be silently ignored since these call sites do not forward the new params

### Similar Patterns
- `scripts/little_loops/fsm/schema.py:79,113–114,138` — `EvaluateConfig.scope: list[str] | None` is the exact pattern for `tools: list[str] | None` (same type, same `to_dict`/`from_dict` idiom)
- `scripts/little_loops/fsm/schema.py:226,264–265,304` — `StateConfig.timeout: int | None` pattern for `agent: str | None`
- No existing `--agent` or `--tools` flags anywhere in the FSM subprocess path — this is the first conditional extension to `cmd_args` in `run_claude_command()`

### Tests
- `scripts/tests/test_subprocess_utils.py:216–245` — `test_constructs_correct_command_args` is the exact skeleton to extend for `--agent`/`--tools`; uses `capture_popen` side-effect pattern with `assert captured_args[0] == [...]`
- `scripts/tests/test_subprocess_utils.py:67–75` — `_patch_selector_cm` helper required in all `run_claude_command` tests
- `scripts/tests/test_fsm_schema.py:1626–1673` — `TestSubLoopStateConfig` (round-trip tests for `loop`/`context_passthrough`) is the exact template for `agent`/`tools` field tests
- `scripts/tests/test_fsm_schema.py:342–398` — `on_blocked` tests show the 4-test pattern for each `str | None` field
- `scripts/tests/test_fsm_executor.py:30–90` — `MockActionRunner` dataclass must have its `run()` signature extended to accept `agent`/`tools` (currently only `action`, `timeout`, `is_slash_command`, `on_output_line`)
- `scripts/tests/test_fsm_executor.py:241–268` — `test_action_type_prompt_runs_action` is the pattern for testing that prompt-mode states pass `agent`/`tools` through to the runner
- `scripts/tests/test_ll_loop_execution.py`, `scripts/tests/test_ll_loop_integration.py` — integration tests; verify these still pass after changes

_Wiring pass added by `/ll:wire-issue`:_

**Additional Protocol implementors requiring `run()` signature updates (agent/tools params):**
- `scripts/tests/test_fsm_executor.py:1834` — `FailingRunner.run()` — inline Protocol implementor, will fail type checks when Protocol signature changes
- `scripts/tests/test_fsm_executor.py:2108–2115` — `ShutdownAfterFirstActionRunner.run()` — same
- `scripts/tests/test_fsm_executor.py:2189–2196` — `CaptureAndShutdownRunner.run()` — same
- `scripts/tests/test_fsm_executor.py:3342–3350` — `TimeoutCapturingRunner.run()` (inside `TestDefaultTimeout`) — same
- `scripts/tests/test_fsm_persistence.py:536–549` — separate `MockActionRunner.run()` (not imported from executor tests) — same 4-param signature, used across ~30 persistence tests
- `scripts/tests/test_fsm_persistence.py:1525–1532` — `CaptureAndShutdownRunner.run()` — same
- `scripts/tests/test_fsm_persistence.py:1582–1589` — `ShutdownAfterFirstRunner.run()` — same
- `scripts/tests/test_fsm_persistence.py:1669–1676` — `ProgressTrackingRunner.run()` — same

**New tests to write (coverage gaps not in existing plan):**
- New test: `executor._run_action()` passes `agent`/`tools` only for prompt-mode states; shell-mode states receive `agent=None, tools=None` even when set on `StateConfig` — follow `test_action_type_prompt_runs_action` at line 241
- New test: `DefaultActionRunner.run(agent="x", tools=["Bash"])` → `run_claude_command` called with `agent="x"`, `tools=["Bash"]` — extend `fake_run_claude_command` at `test_fsm_executor.py:3011` to assert `kwargs.get("agent")` and `kwargs.get("tools")`
- `scripts/tests/test_fsm_schema_fuzz.py` — fuzz tests for `StateConfig.from_dict()`; verify `agent`/`tools` deserialization does not break fuzz harness
- `scripts/tests/test_builtin_loops.py` — validates all 40 built-in YAML loop files load cleanly; runs after `fsm-loop-schema.json` update to confirm new schema fields don't break existing loops

### Documentation
- `docs/guides/LOOPS_GUIDE.md:603–697` and `1556–1681` — state field reference sections; add `agent:` and `tools:` entries
- `docs/reference/API.md:3766–3786` — `StateConfig` dataclass reference block; add new fields
- `docs/reference/API.md:4044–4057` — `ActionRunner` Protocol signature documentation block; update to reflect `agent`/`tools` params
- `docs/reference/API.md:1923–1942` — `run_claude_command` function signature documentation; add `agent`/`tools` params
- `docs/generalized-fsm-loop.md` — FSM design doc; may reference state-level fields

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md:236–260` — `ll-loop run` flag table; does not currently describe state-level YAML fields `agent:`/`tools:` — add a note or reference pointing to the state config YAML reference

### Configuration

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/fsm/fsm-loop-schema.json:166–266` — **CRITICAL**: `stateConfig` definition has `"additionalProperties": false`; any loop YAML using `agent:` or `tools:` at the state level will fail JSON Schema validation until these properties are added. Must add `agent` (type: string) and `tools` (type: array of strings) to the `stateConfig.properties` object.

## Impact

- **Priority**: P2 - Blocks eval harnesses that need MCP tools (e.g., Playwright-based loop evals)
- **Effort**: Small - Additive changes across 4 well-understood files; no new patterns required
- **Risk**: Low - Fields are optional; no existing behavior changes; shell-mode states unaffected
- **Breaking Change**: No

## Labels

`feature`, `fsm`, `ll-loop`, `subprocess`, `mcp`

## Related

- Plan: `~/.claude/plans/enumerated-crunching-graham.md`

---

## Resolution

- **Status**: Decomposed
- **Completed**: 2026-04-09
- **Reason**: Issue scored 9/11 (Very Large) — thorough wiring pass expanded scope beyond single-session size

### Decomposed Into
- FEAT-1011: Core FSM implementation + test coverage
- ENH-1012: Documentation updates (LOOPS_GUIDE, API.md, CLI.md)

---

## Status

Active

## Session Log
- `/ll:issue-size-review` - 2026-04-09T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b4b4a844-219d-40e6-8201-677dabfe574c.jsonl`
- `/ll:confidence-check` - 2026-04-09T15:30:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/098f36a8-7767-4ff0-b011-6d7b78fa79ba.jsonl`
- `/ll:wire-issue` - 2026-04-09T14:58:05 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/45d73860-dae2-47a6-b5cb-e57b80446e48.jsonl`
- `/ll:refine-issue` - 2026-04-09T14:51:22 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/04e6f4ba-791b-42d9-a99c-a76459669f0b.jsonl`
- `/ll:format-issue` - 2026-04-09T14:47:29 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/67a0fca2-19be-4d7a-8417-535d5b6b00ce.jsonl`
- `/ll:capture-issue` - 2026-04-09T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/558a9634-84fa-40e4-affe-1b6719f5a039.jsonl`
