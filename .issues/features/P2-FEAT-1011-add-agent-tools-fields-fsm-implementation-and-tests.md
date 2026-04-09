---
id: FEAT-1011
type: FEAT
priority: P2
status: active
title: "Add `agent:` and `tools:` FSM state fields — implementation and tests"
discovered_date: 2026-04-09
discovered_by: issue-size-review
confidence_score: 100
outcome_confidence: 90
---

# FEAT-1011: Add `agent:` and `tools:` FSM state fields — implementation and tests

## Summary

Implement the core code changes to add `agent:` and `tools:` as optional state-level fields to the ll-loop FSM, thread them through to the claude CLI subprocess invocation, and update all test mock signatures + write new test coverage.

Decomposed from FEAT-1010: "Add `agent:` and `tools:` state-level fields to ll-loop FSM"

## Current Behavior

`ll-loop` FSM prompt-mode states invoke `claude --dangerously-skip-permissions --verbose --output-format stream-json -p "<prompt>"` with no `--agent` or `--tools` flag. MCP tools present in `.mcp.json` arrive as deferred tools in the subprocess context, but the ToolSearch mechanism fails to resolve them, causing loops that require MCP tools to stall indefinitely.

## Expected Behavior

FSM YAML state configs support optional `agent:` and `tools:` fields. When set on a prompt-mode state, the subprocess invocation includes `--agent <name>` and/or `--tools <csv>`, enabling MCP tools to load and resolve correctly in that state's subprocess.

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

Update the `ActionRunner` Protocol signature (line 31–37):
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

Add same params to `DefaultActionRunner.run()` signature (line 58) and pass them in the `run_claude_command()` call (near line 94).

Also add `agent: str | None = None` and `tools: list[str] | None = None` to `SimulationActionRunner.run()` signature.

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

### 5. `scripts/little_loops/fsm/fsm-loop-schema.json` — Add schema fields

Add `agent` (type: string, optional) and `tools` (type: array of string items, optional) to `stateConfig.properties`. This is required since `"additionalProperties": false` is set.

### 6. Update all Protocol implementors in tests

**`scripts/tests/test_fsm_executor.py`** — add `agent: str | None = None, tools: list[str] | None = None` to:
- `MockActionRunner.run()` (line 43)
- `FailingRunner.run()` (line 1834)
- `ShutdownAfterFirstActionRunner.run()` (line 2108)
- `CaptureAndShutdownRunner.run()` (line 2189)
- `TimeoutCapturingRunner.run()` (line 3342)

**`scripts/tests/test_fsm_persistence.py`** — add same params to:
- `MockActionRunner.run()` (line 536)
- `CaptureAndShutdownRunner.run()` (line 1525)
- `ShutdownAfterFirstRunner.run()` (line 1582)
- `ProgressTrackingRunner.run()` (line 1669)

### 7. Write new tests

- `test_fsm_schema.py`: `agent`/`tools` field round-trips — follow `TestSubLoopStateConfig` pattern (lines 1626–1673)
- `test_subprocess_utils.py`: `--agent`/`--tools` appended to `cmd_args` — follow pattern at lines 216–245
- `test_fsm_executor.py`: `_run_action()` passes `agent`/`tools` only for prompt-mode states; shell-mode receives `None`
- `test_fsm_executor.py`: `DefaultActionRunner.run(agent=..., tools=...)` → `run_claude_command()` called with correct kwargs (extend `fake_run_claude_command` fixture at line 3011)
- Verify `test_fsm_schema_fuzz.py` and `test_builtin_loops.py` still pass after schema update

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
- [ ] `SimulationActionRunner.run()` updated to match Protocol signature
- [ ] `run_claude_command()` accepts and appends `--agent` / `--tools` flags to the invocation
- [ ] `DefaultActionRunner.run()` accepts and passes through both params
- [ ] `executor.py` extracts `state.agent` / `state.tools` and passes them only for prompt-mode states
- [ ] `fsm-loop-schema.json` updated with `agent` and `tools` in `stateConfig.properties`
- [ ] All Protocol implementors in `test_fsm_executor.py` and `test_fsm_persistence.py` updated
- [ ] New tests in `test_fsm_schema.py`, `test_subprocess_utils.py`, `test_fsm_executor.py`
- [ ] Existing tests pass: `python -m pytest scripts/tests/ -v`
- [ ] Manual smoke test: minimal loop YAML with `agent: some-agent` on a prompt state confirms `--agent some-agent` in logged claude invocation

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/schema.py` — `StateConfig` dataclass
- `scripts/little_loops/subprocess_utils.py` — `run_claude_command()`
- `scripts/little_loops/fsm/runners.py` — `ActionRunner` Protocol, `DefaultActionRunner.run()`, `SimulationActionRunner.run()`
- `scripts/little_loops/fsm/executor.py` — `_run_action()`
- `scripts/little_loops/fsm/fsm-loop-schema.json` — `stateConfig.properties`
- `scripts/tests/test_fsm_executor.py` — 5 Protocol implementors + 2 new tests
- `scripts/tests/test_fsm_persistence.py` — 4 Protocol implementors
- `scripts/tests/test_fsm_schema.py` — new round-trip tests
- `scripts/tests/test_subprocess_utils.py` — new CLI flag tests

### Similar Patterns
- `scripts/little_loops/fsm/schema.py:79,113–114,138` — `EvaluateConfig.scope: list[str] | None` for `tools`
- `scripts/little_loops/fsm/schema.py:226,264–265,304` — `StateConfig.timeout: int | None` for `agent`

## Impact

- **Priority**: P2 - Blocks eval harnesses that need MCP tools
- **Effort**: Small - Additive changes across well-understood files; no new patterns required
- **Risk**: Low - Fields are optional; no existing behavior changes; shell-mode states unaffected
- **Breaking Change**: No

## Labels

`feature`, `fsm`, `ll-loop`, `subprocess`, `mcp`

## Related

- Parent: FEAT-1010 (decomposed)
- Sibling: ENH-1012 (documentation updates)

---

## Status

Active

## Session Log
- `/ll:issue-size-review` - 2026-04-09T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b4b4a844-219d-40e6-8201-677dabfe574c.jsonl`
