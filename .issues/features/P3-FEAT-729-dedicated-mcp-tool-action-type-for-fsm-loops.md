---
id: FEAT-729
priority: P3
type: FEAT
status: active
discovered_date: 2026-03-13
discovered_by: capture-issue
confidence_score: 95
outcome_confidence: 71
---

# FEAT-729: Dedicated mcp_tool Action Type for FSM Loops

## Summary

Add `action_type: mcp_tool` to the FSM loop schema for direct, parameterized MCP tool invocation — bypassing the Claude CLI entirely and enabling deterministic, structured tool calls with MCP-aware evaluation and routing.

## Current Behavior

MCP tools can only be used in FSM loops via `action_type: prompt`, which runs a full Claude CLI session — conflating tool invocation semantics with agentic reasoning semantics. This carries significant costs: 10–30s latency per state, LLM overhead (two model calls for a deterministic function call), nondeterminism (Claude may rephrase, call a different tool, or decline), unstructured output, and no tool-specific error routing (`rate_limited`, `auth_error`, `tool_not_found` all collapse into generic `failure`).

## Expected Behavior

FSM loops support `action_type: mcp_tool` to invoke specific MCP tools directly with structured parameters, yielding: deterministic execution (~500ms latency), structured MCP response envelope output, evaluation via the new `mcp_result` evaluator, and granular error routing (`success`, `tool_error`, `not_found`, `timeout`). The `action` field holds `"server/tool-name"` and `params` holds tool arguments with `${variable}` interpolation.

## Motivation

Currently, MCP tools can only be used in FSM loops via `action_type: prompt`, which runs a full Claude CLI session. This conflates two distinct semantics:

- **`prompt`**: "Give Claude a goal; let it reason and use tools as it sees fit."
- **`mcp_tool`** (proposed): "Call this specific tool with these exact parameters; give me the raw structured result."

Using `prompt` for direct tool calls carries significant costs:
- **LLM overhead**: Two model calls (one to invoke the tool, one for `llm_structured` evaluation) for what is a deterministic function call.
- **Latency**: 10–30s per state vs. ~500ms for a direct tool call.
- **Nondeterminism**: Claude may rephrase, add caveats, call a different tool, or decline.
- **Unstructured output**: Claude's prose wraps the raw tool result, making evaluation fragile.
- **No tool-specific error routing**: `rate_limited`, `auth_error`, `tool_not_found` all collapse into generic `failure`.

## Use Case

A loop that monitors a website for content changes, browses for competitive intelligence, queries a database MCP server, or interacts with a Slack MCP tool — where the tool, parameters, and expected output shape are all known ahead of time:

```yaml
states:
  fetch:
    action_type: mcp_tool
    action: "browser/navigate"
    params:
      url: "${context.target_url}"
    capture: page_result
    evaluate:
      type: mcp_result
    route:
      success: extract_data
      tool_error: log_and_retry
      not_found: terminal_error
      timeout: retry
```

vs. the current workaround:

```yaml
states:
  fetch:
    action_type: prompt
    action: "Use the browser MCP tool to navigate to ${context.target_url} and return the page title"
    # Runs full Claude session + llm_structured eval — slow, costly, nondeterministic
```

## Acceptance Criteria

- [ ] `action_type: mcp_tool` is a valid value in `StateConfig` (Python dataclass + JSON Schema)
- [ ] `params` field on states supports `${variable}` interpolation for MCP tool arguments
- [ ] `mcp_result` evaluator routes to `success`, `tool_error`, `not_found`, `timeout` based on MCP response envelope (`isError`, transport errors, missing server)
- [ ] `mcp-call` wrapper script reads `.mcp.json`, performs JSON-RPC handshake, calls `tools/call`, and writes MCP envelope to stdout
- [ ] `DefaultActionRunner` executes `mcp_tool` states without invoking the Claude CLI
- [ ] Validation rejects `params` field on states where `action_type != mcp_tool`
- [ ] Unit tests cover all `mcp_result` evaluator routing branches
- [ ] Integration test verifies end-to-end `mcp_tool` state execution with a mock MCP server
- [ ] FSM loop documentation and YAML examples updated

## Proposed Solution

### Schema: New `action_type` value

Add `"mcp_tool"` to the `action_type` enum in `StateConfig`:

```python
# schema.py
action_type: Literal["prompt", "slash_command", "shell", "mcp_tool"] | None = None
params: dict[str, Any] = field(default_factory=dict)  # MCP tool arguments
```

- `action` field holds `"server/tool-name"` (e.g., `"browser/navigate"`)
- `params` field holds the tool arguments dict (supports `${variable}` interpolation)

### Schema: New `mcp_result` evaluator type

Add `"mcp_result"` to `EvaluateConfig.type`. MCP tool responses follow a standard envelope:

```json
{"content": [{"type": "text", "text": "..."}], "isError": false}
```

The `mcp_result` evaluator routes to:
- `success` — `isError: false`
- `tool_error` — `isError: true` (tool ran but reported failure)
- `not_found` — server/tool not present in `.mcp.json`
- `timeout` — transport-level timeout

Default evaluator for `mcp_tool` states: `mcp_result` (parallel to `shell` → `exit_code`, `prompt` → `llm_structured`).

### Executor: New execution branch in `DefaultActionRunner`

**Implementation approach options** (in order of complexity):

1. **Shell wrapper** (near-term): A thin `mcp-call` Python script that reads `.mcp.json`, spawns the server subprocess, performs JSON-RPC handshake, calls `tools/call`, and writes the MCP response envelope to stdout. Works within existing subprocess infrastructure.

2. **Persistent connection pool** (long-term): An `MCPConnectionPool` in the executor that keeps MCP server processes alive across state transitions — critical for expensive-to-spawn servers (browsers, DB connections). This avoids per-state server startup overhead.

### JSON Schema update

```json
"action_type": {
  "enum": ["prompt", "slash_command", "shell", "mcp_tool"]
},
"params": {
  "type": "object",
  "description": "MCP tool arguments (only used with action_type: mcp_tool)",
  "additionalProperties": true
}
```

## Implementation Steps

1. Add `params: dict[str, Any]` field to `StateConfig` dataclass and JSON schema
2. Add `"mcp_tool"` to `action_type` enum in both `schema.py` and `fsm-loop-schema.json`
3. Add `"mcp_result"` to `EvaluateConfig.type` enum in both files
4. Implement `mcp_result` evaluator in `evaluators.py` (parses MCP response envelope)
5. Implement `mcp-call` wrapper script (shell-based near-term approach)
6. Add `mcp_tool` execution branch in `DefaultActionRunner.run()`
7. Update `_is_prompt_action()` to `_action_mode()` returning the execution mode
8. Add interpolation support for `params` dict values
9. Update validation in `validation.py` to check `params` requires `action_type: mcp_tool`
10. Add tests: unit tests for `mcp_result` evaluator, integration test with mock MCP server
11. Update `ll-loop` docs and loop YAML examples

## API/Interface

**New YAML fields on a state:**

```yaml
states:
  my_state:
    action_type: mcp_tool         # new enum value
    action: "server/tool-name"    # server_name/tool_name
    params:                       # new field — tool arguments
      key: "${context.value}"
    evaluate:
      type: mcp_result            # new evaluator type
    route:
      success: next_state
      tool_error: handle_error
      not_found: terminal_error
      timeout: retry
```

**Decision guide:**
- Use `action_type: prompt` when Claude should *decide how to use* tools (reasoning, judgment required)
- Use `action_type: mcp_tool` when tool, server, and parameters are all known at loop-author time

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/schema.py` — `StateConfig`, `EvaluateConfig`
- `scripts/little_loops/fsm/fsm-loop-schema.json` — JSON Schema
- `scripts/little_loops/fsm/executor.py` — `DefaultActionRunner`, `_is_prompt_action`
- `scripts/little_loops/fsm/evaluators.py` — `mcp_result` evaluator
- `scripts/little_loops/fsm/interpolation.py` — `params` dict interpolation
- `scripts/little_loops/fsm/validation.py` — schema validation updates
- `scripts/tests/` — new unit and integration tests
- `docs/` — FSM loop documentation

### Dependent Files (Callers/Importers)
- TBD - use grep to find references: `grep -r "action_type\|DefaultActionRunner\|_is_prompt_action" scripts/`

### Similar Patterns
- TBD - check how `shell` action type is implemented as the nearest analog: `grep -r "shell" scripts/little_loops/fsm/`

### Tests
- `scripts/tests/` — unit tests for `mcp_result` evaluator branches; integration test with mock MCP server

### Documentation
- `docs/` — FSM loop documentation and loop YAML examples with `mcp_tool` states

### Configuration
- `scripts/little_loops/fsm/fsm-loop-schema.json` — JSON Schema updates (new `action_type` enum value and `params` field)

## Impact

- **Priority**: P3 - Meaningful optimization for MCP-integrated loops; reduces per-state cost from 10–30s to ~500ms, but existing `prompt` approach remains functional
- **Effort**: Medium - New action type, evaluator, executor branch, and wrapper script; `shell` action type provides a clear analog; near-term shell wrapper keeps scope contained
- **Risk**: Medium - New execution path requiring subprocess management and JSON-RPC handling; existing `prompt` behavior is entirely unchanged
- **Breaking Change**: No

## Labels

`fsm-loops`, `mcp`, `feature`, `performance`

## Related Issues

- P3-ENH-713: per-item retry limits (would benefit from `tool_error`/`timeout` routing)
- P3-ENH-717: detect replaceable LLM prompt states (could flag prompt states calling specific tools)
- P3-FEAT-659: hierarchical FSM loops

---

## Status

Active — not started.

## Session Log
- `/ll:capture-issue` - 2026-03-13T21:15:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fffc83c9-009a-4696-8010-040737bf7247.jsonl`
- `/ll:format-issue` - 2026-03-13T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9b17321b-fc43-48b2-a2d7-478ef2d7ba48.jsonl`
- `/ll:verify-issues` - 2026-03-13T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9b17321b-fc43-48b2-a2d7-478ef2d7ba48.jsonl`
- `/ll:confidence-check` - 2026-03-13T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2acb782e-c208-43f1-8534-96bfd95ced6e.jsonl`
