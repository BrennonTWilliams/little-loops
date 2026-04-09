---
id: FEAT-1010
type: FEAT
priority: P2
status: active
title: "Add `agent:` and `tools:` state-level fields to ll-loop FSM"
discovered_date: 2026-04-09
discovered_by: capture-issue
---

# FEAT-1010: Add `agent:` and `tools:` state-level fields to ll-loop FSM

## Summary

`ll-loop` prompt-mode states invoke `claude --dangerously-skip-permissions --verbose --output-format stream-json -p "<prompt>"` with no `--agent` or `--tools` flag. MCP tools present in `.mcp.json` arrive as deferred tools in the subprocess, and Claude's ToolSearch mechanism fails to resolve them in that context, causing the harness to stall.

Add `agent:` and `tools:` as optional state-level fields to the FSM YAML schema and thread them through to the claude CLI invocation.

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

### 3. `scripts/little_loops/fsm/runners.py` — Thread through `DefaultActionRunner.run()`

Add params to `run()` signature (line 58):
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

## API/Interface Changes

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

- [ ] `StateConfig` dataclass has `agent: str | None` and `tools: list[str] | None` fields
- [ ] `run_claude_command()` accepts and appends `--agent` / `--tools` flags to the invocation
- [ ] `DefaultActionRunner.run()` accepts and passes through both params
- [ ] `executor.py` extracts `state.agent` / `state.tools` and passes them only for prompt-mode states
- [ ] Existing tests pass: `python -m pytest scripts/tests/ -v`
- [ ] Manual smoke test: minimal loop YAML with `agent: some-agent` on a prompt state confirms `--agent some-agent` in logged claude invocation

## Integration Points

- `scripts/little_loops/fsm/schema.py` — `StateConfig` dataclass
- `scripts/little_loops/subprocess_utils.py` — `run_claude_command()`
- `scripts/little_loops/fsm/runners.py` — `DefaultActionRunner.run()`
- `scripts/little_loops/fsm/executor.py` — `_run_action()`
- FSM YAML schema (documented in `docs/`)
- Built-in loop YAMLs that use `action_type: prompt` (may benefit from `agent:` field)

## Related

- Plan: `~/.claude/plans/enumerated-crunching-graham.md`

---

## Status

Active

## Session Log
- `/ll:capture-issue` - 2026-04-09T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/558a9634-84fa-40e4-affe-1b6719f5a039.jsonl`
