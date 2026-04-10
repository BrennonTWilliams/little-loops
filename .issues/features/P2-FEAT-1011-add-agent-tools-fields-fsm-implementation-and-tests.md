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

## Use Case

A developer writes an FSM loop YAML with a prompt state that requires an MCP tool (e.g., `ToolSearch`). They add `agent: my-agent` and/or `tools: ["ToolSearch"]` to that state. When `ll-loop` executes the FSM, the subprocess invocation includes `--agent my-agent --tools ToolSearch`, the MCP tool resolves correctly in the subprocess context, and the loop proceeds without stalling.

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

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

8. Update `docs/reference/API.md` — add `agent: str | None = None` and `tools: list[str] | None = None` to the `ActionRunner Protocol` code block (line ~4047), and add `agent`/`tools` to the `StateConfig` field table (line ~3770). (May be owned by sibling ENH-1012.)
9. Update `docs/development/TESTING.md` — add `agent`/`tools` params to the `MockActionRunner.run()` example signature (line ~533).
10. Verify `scripts/tests/test_create_eval_from_issues.py` passes after `fsm-loop-schema.json` update — run as part of `python -m pytest scripts/tests/`.

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

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/extension.py:79-87` — `ActionProviderExtension.provided_actions()` returns `dict[str, ActionRunner]`; external extensions implementing the old 4-param `run()` will break at runtime when the Protocol gains `agent`/`tools` [Agent 1 finding]
- `scripts/little_loops/fsm/__init__.py` — re-exports `StateConfig` and `ActionRunner` in `__all__`; no code change needed, but is the public API surface downstream consumers rely on [Agent 1 finding]
- `scripts/little_loops/issue_manager.py:41-42` — imports `run_claude_command` as `_run_claude_base` but wraps it with a fixed param set — **insulated, no update needed** [Agent 1 finding]
- `scripts/little_loops/parallel/worker_pool.py:29-30` — same aliased import pattern as `issue_manager.py` — **insulated, no update needed** [Agent 1 finding]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md:4044-4055` — `ActionRunner Protocol` code block shows old 4-param signature (no `agent`/`tools`); must be updated to match new Protocol (sibling ENH-1012 may own this) [Agent 2 finding]
- `docs/reference/API.md:3766-3786` — `StateConfig` code block missing `agent` and `tools` fields [Agent 2 finding]
- `docs/development/TESTING.md:533-548` — `MockActionRunner` example shows 3-param signature (even more stale than current Protocol); needs `agent`/`tools` added [Agent 2 finding]
- Note: `docs/guides/LOOPS_GUIDE.md` and `docs/generalized-fsm-loop.md` **already have** `agent:`/`tools:` documentation from the parent FEAT-1010 doc commit — no change needed [Agent 2 finding]

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_create_eval_from_issues.py` — validates generated harness YAMLs through the full `load_and_validate` + `validate_fsm` stack; verify still passes after `fsm-loop-schema.json` update [Agent 3 finding]

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

#### Verified Exact Line Numbers (corrected from estimates)

| Touch Point | Actual Location |
|---|---|
| `StateConfig` dataclass fields | `schema.py:213–231` (`context_passthrough` at line 231) |
| `StateConfig.to_dict()` | `schema.py:233–276` |
| `StateConfig.from_dict()` return block | `schema.py:289` (method start; `timeout=data.get("timeout")` at line 303) |
| `ActionRunner` Protocol `run()` | `runners.py:28–49` |
| `DefaultActionRunner.run()` signature | `runners.py:58–64` |
| `run_claude_command()` call in `DefaultActionRunner` | `runners.py:94–100` |
| `SimulationActionRunner.run()` | `runners.py:181–187` |
| `_run_action()` else branch | `executor.py:512–518` |
| `stateConfig.properties` block | `fsm-loop-schema.json:169–265`, `additionalProperties: false` at line 266 |
| `MockActionRunner.run()` (executor tests) | `test_fsm_executor.py:43–52` |
| `FailingRunner.run()` | `test_fsm_executor.py:1833–1838` |
| `ShutdownAfterFirstActionRunner.run()` | `test_fsm_executor.py:2105–2123` |
| `CaptureAndShutdownRunner.run()` | `test_fsm_executor.py:2186–2208` |
| `TimeoutCapturingRunner.run()` | `test_fsm_executor.py:3336–3350` |
| `fake_run_claude_command` fixture | `test_fsm_executor.py:3011–3028` |
| `MockActionRunner.run()` (persistence tests) | `test_fsm_persistence.py:528–549` |
| `CaptureAndShutdownRunner.run()` | `test_fsm_persistence.py:1522–1544` |
| `ShutdownAfterFirstRunner.run()` | `test_fsm_persistence.py:1579–1597` |
| `ProgressTrackingRunner.run()` | `test_fsm_persistence.py:1666–1687` |

#### `del` Statement Pattern in Mock Runners

Most mock runners suppress "unused variable" warnings via a `del` statement. When adding `agent`/`tools` to their signatures, the `del` must be extended too. Example for `MockActionRunner` (`test_fsm_executor.py:52`):

```python
# Before
del timeout, is_slash_command, on_output_line

# After
del timeout, is_slash_command, on_output_line, agent, tools
```

Not all runners use `del` — `TimeoutCapturingRunner` does not (it silently ignores `action` and `is_slash_command`). Check each runner individually.

#### Confirmed: No Additional Protocol Implementors in Other Test Files

`test_ll_loop_execution.py`, `test_ll_loop_state.py`, `test_ll_loop_integration.py`, `test_ll_loop_errors.py`, `test_ll_loop_display.py`, `test_ll_loop_commands.py`, `test_ll_loop_parsing.py`, and `test_review_loop.py` do **not** contain `ActionRunner` Protocol implementors. The `def run()` occurrences in `test_ll_loop_display.py` are for a `MockExecutor` (returns `ExecutionResult`), not `ActionRunner`.

#### `testing.py` Call Sites — No Update Needed

`scripts/little_loops/cli/loop/testing.py` calls `runner.run()` and `sim_runner.run()` at lines 72 and 85. Since `agent` and `tools` will be optional with `None` defaults, these call sites don't need to pass the new params.

#### `contributed` Branch in `executor.py`

The `elif action_mode == "contributed":` branch at `executor.py:492–502` calls `runner.run()` but should NOT pass `agent`/`tools` — contributed action runners are plugin-supplied and handle their own tool selection. Only the `else` branch (default prompt/shell mode) passes the new fields.

#### `cmd_args` Construction Pattern in `subprocess_utils.py`

The `cmd_args` list (lines 95–103) is built as a complete literal with no existing conditional appends. The new `--agent`/`--tools` appends should be added after the list literal and before the env setup block (line 105). Pattern to follow: `evaluators.py:565–577` where `--model` is conditionally appended to a `cmd` list.

#### Testing `--agent`/`--tools` in `test_subprocess_utils.py`

Use the `capture_popen` idiom from `test_subprocess_utils.py:216–245` — capture `args` positionally and assert the full list. For `--agent some-agent`, the expected list would append `["--agent", "some-agent"]` after `-p <command>`. For `--tools`, it would append `["--tools", "Bash,Edit"]`.

#### Testing `DefaultActionRunner` Pass-Through via `fake_run_claude_command`

The fixture at `test_fsm_executor.py:3011–3028` uses `**kwargs` to capture all keyword args to `run_claude_command()`. To test `agent`/`tools` pass-through, assert `kwargs["agent"] == "some-agent"` and `kwargs["tools"] == ["Bash"]` after calling `runner.run(..., agent="some-agent", tools=["Bash"])`. The patch target is `"little_loops.fsm.runners.run_claude_command"`.

#### `cmd_args` Build — Current Structure (lines 95–103)

```python
cmd_args = [
    "claude",
    "--dangerously-skip-permissions",
    "--verbose",
    "--output-format",
    "stream-json",
    "-p",
    command,
]
# No existing conditional flag appends exist here
# subprocess.Popen called at line 122 directly with cmd_args
```

Insert conditional appends after line 103 (before env setup at line 105):
```python
if agent:
    cmd_args += ["--agent", agent]
if tools:
    cmd_args += ["--tools", ",".join(tools)]
```

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
- `/ll:ready-issue` - 2026-04-10T22:59:18 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/afd0bcd6-194a-4a67-9623-1c31aebd634d.jsonl`
- `/ll:ready-issue` - 2026-04-09T16:32:10 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/15e78a6b-ed74-4ba8-b288-d99d5bfebd5f.jsonl`
- `/ll:wire-issue` - 2026-04-09T16:29:50 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2b46853f-0880-4875-afe9-7909cbb09d0d.jsonl`
- `/ll:refine-issue` - 2026-04-09T16:19:46 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/93b983eb-cf4b-4c20-b900-2e51d71a33c1.jsonl`
- `/ll:issue-size-review` - 2026-04-09T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b4b4a844-219d-40e6-8201-677dabfe574c.jsonl`
