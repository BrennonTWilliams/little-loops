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

### Executor: New execution branch in `FSMExecutor._run_action()`

> **Protocol decision** (`executor.py:98–119`): The `ActionRunner` Protocol's `is_slash_command: bool` is a binary gate (Claude CLI vs bash). **Do not extend the Protocol.** Instead, intercept `mcp_tool` states in `FSMExecutor._run_action()` (line 597) **before** delegating to `action_runner.run()` — parallel to how signal detection is handled post-run. This keeps `ActionRunner`, `MockActionRunner`, and `SimulationActionRunner` unchanged. The `_is_prompt_action()` → `_action_mode()` rename (Step 7 below) gives `_run_action()` and `_evaluate()` the signal they need to branch — without touching the Protocol.

**Implementation approach options** (in order of complexity):

1. **Shell wrapper** (near-term, recommended): A thin `mcp-call` Python script with this interface:
   ```
   mcp-call server/tool-name '{"param": "value"}'
   # Reads .mcp.json from CWD, spawns server subprocess, JSON-RPC handshake, calls tools/call
   # stdout: MCP envelope JSON — {"content": [...], "isError": false/true}
   # exit 0   → success (isError: false)
   # exit 1   → tool_error (isError: true)
   # exit 124 → timeout (transport-level)
   # exit 127 → not_found (server/tool missing from .mcp.json)
   ```
   In `_run_action()`, when `_action_mode(state) == "mcp_tool"`, build `cmd = ["mcp-call", state.action, json.dumps(interpolated_params)]` and call `subprocess.Popen` directly (same pattern as shell branch in `DefaultActionRunner.run()`). `mcp_result` evaluator then parses stdout as JSON and maps `isError` + exit code to verdicts.

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
4. Implement `mcp_result` evaluator in `evaluators.py` (parses MCP response envelope; maps `isError` + exit code to `success`/`tool_error`/`not_found`/`timeout`)
5. Implement `mcp-call` wrapper script (see interface spec above)
6. Update `_is_prompt_action()` (executor.py:808) to `_action_mode()` returning `"prompt"`, `"shell"`, or `"mcp_tool"`. Update both callers: `_run_action()` (line 616) and `_evaluate()` (line 684). **Protocol signature unchanged — no updates needed to `MockActionRunner` or `SimulationActionRunner`.**
7. Add `mcp_tool` execution branch in `FSMExecutor._run_action()` (line 597) — intercept when `_action_mode(state) == "mcp_tool"`, build `mcp-call` subprocess command with interpolated params, call `subprocess.Popen` directly, return `ActionResult`. Do NOT delegate to `action_runner.run()`.
8. In `_evaluate()` (line 680), add `elif action_mode == "mcp_tool": result = evaluate_mcp_result(action_result.output, action_result.exit_code)` as the third default-evaluator branch.
9. Add interpolation support for `params` dict values — `interpolate_dict(state.params, ctx)` at `interpolation.py:209` already exists and handles this; just call it
10. Update validation in `validation.py` to check `params` requires `action_type: mcp_tool` — note: `validation.py` currently does NOT validate `action_type` values at all (unknown values silently fall through `_is_prompt_action`); add explicit `action_type` enum validation here too
11. Add tests: unit tests for `mcp_result` evaluator, integration test with mock MCP server
12. Update `ll-loop` docs and loop YAML examples

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
- `scripts/little_loops/fsm/executor.py` — `FSMExecutor._run_action()`, `FSMExecutor._evaluate()`, `_is_prompt_action` → `_action_mode()`
- `scripts/little_loops/fsm/evaluators.py` — `mcp_result` evaluator
- `scripts/little_loops/fsm/interpolation.py` — `params` dict interpolation
- `scripts/little_loops/fsm/validation.py` — schema validation updates
- `scripts/tests/` — new unit and integration tests
- `docs/` — FSM loop documentation

### Dependent Files (Callers/Importers)

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `scripts/little_loops/cli/loop/testing.py` — references `StateConfig`/`action_type`; may need display updates for `mcp_tool` states
- `scripts/little_loops/cli/loop/info.py` — references `StateConfig`/`action_type`; loop info display
- `scripts/little_loops/cli/loop/layout.py` — references `StateConfig`/`action_type`; TUI layout
- `scripts/little_loops/cli/loop/_helpers.py` — references `StateConfig`/`action_type`; helper utilities
- `scripts/tests/test_fsm_executor.py` — covers `DefaultActionRunner`, `_is_prompt_action`, `TestActionType` class; all must be updated for `mcp_tool`
- `scripts/tests/test_fsm_schema.py` — covers `StateConfig`/`EvaluateConfig` deserialization; must test new `"mcp_tool"` and `"mcp_result"` values
- `scripts/tests/test_fsm_evaluators.py` — covers evaluator dispatch; must add `mcp_result` tests

### Similar Patterns

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `scripts/little_loops/fsm/executor.py:128–204` — `DefaultActionRunner.run()` shell branch (`is_slash_command=False` → `cmd = ["bash", "-c", action]`); the `mcp_tool` branch follows the same `subprocess.Popen` + stderr-drain-thread pattern
- `scripts/little_loops/fsm/executor.py:808–812` — `_is_prompt_action()`: returns `True` for `"prompt"`/`"slash_command"`, `False` otherwise; must become `_action_mode()` returning `"prompt"`, `"shell"`, or `"mcp_tool"` to avoid treating `mcp_tool` as a shell command
- `scripts/little_loops/fsm/executor.py:597–662` — `_run_action()`: where `is_slash_command = self._is_prompt_action(state)` is set (line 616); new `mcp_tool` branch would intercept here before calling `action_runner.run()`
- `scripts/little_loops/fsm/executor.py:664+` — `_evaluate()`: when `state.evaluate is None`, default evaluator is chosen via `_is_prompt_action(state)` at line 684; must be updated to choose `mcp_result` as default for `mcp_tool` states
- `scripts/little_loops/fsm/evaluators.py:93–112` — `evaluate_exit_code()`: maps exit code to `"yes"`/`"no"`/`"error"`; direct structural analog for `evaluate_mcp_result()` which maps MCP envelope fields to `"success"`/`"tool_error"`/`"not_found"`/`"timeout"`
- `scripts/little_loops/fsm/evaluators.py:629+` — `evaluate()` dispatcher: adds one `elif eval_type == "mcp_result":` branch calling `evaluate_mcp_result(output)`
- `scripts/tests/test_fsm_executor.py:25–84` — `MockActionRunner` class: the primary test harness; inject it via `FSMExecutor(fsm, action_runner=mock_runner)`; `mock_runner.always_return(exit_code=0, output='{"isError":false,...}')` for mcp_tool state tests
- `scripts/tests/test_fsm_executor.py:233–365` — `TestActionType` class: model new `test_action_type_mcp_tool_*` tests here
- `scripts/tests/test_fsm_evaluators.py:46–69` — `TestExitCodeEvaluator` parametrize pattern: model `TestMcpResultEvaluator` with `@pytest.mark.parametrize(("output", "expected"), [...])`

### Tests
- `scripts/tests/test_fsm_executor.py` — add `test_action_type_mcp_tool_*` cases to existing `TestActionType` class; use `MockActionRunner` returning MCP envelope JSON in `output`
- `scripts/tests/test_fsm_evaluators.py` — add `TestMcpResultEvaluator` parametrized over `isError: false/true`, missing server, timeout exit code
- `scripts/tests/test_fsm_schema.py` — add tests that `"mcp_tool"` is valid for `action_type` and `"mcp_result"` is valid for `EvaluateConfig.type`; that `params` round-trips through `to_dict()`/`from_dict()`
- New integration test: FSM end-to-end with a mock MCP server subprocess (follows `test_subprocess_mocks.py` Popen fixture pattern)

### Documentation
- `docs/generalized-fsm-loop.md` — primary FSM loop documentation; must add `mcp_tool` action type and `mcp_result` evaluator
- `docs/guides/LOOPS_GUIDE.md` — references `action_type`; update with `mcp_tool` examples
- `skills/create-loop/loop-types.md` — loop type definitions including action types; update for `mcp_tool`
- `skills/create-loop/reference.md` — reference material used during loop creation; update

### Configuration
- `scripts/little_loops/fsm/fsm-loop-schema.json` — JSON Schema updates (new `action_type` enum value and `params` field)

## Impact

- **Priority**: P3 - Meaningful optimization for MCP-integrated loops; reduces per-state cost from 10–30s to ~500ms, but existing `prompt` approach remains functional
- **Effort**: Medium - New action type, evaluator, executor branch, and wrapper script; `shell` action type provides a clear analog; near-term shell wrapper keeps scope contained
- **Risk**: Medium - New execution path requiring subprocess management and JSON-RPC handling; existing `prompt` behavior is entirely unchanged
- **Breaking Change**: No

## Labels

`fsm-loops`, `mcp`, `feature`, `performance`

## Design Boundary with FEAT-712 Harness

FEAT-712 added "Harness a skill or prompt" to create-loop, which wraps skills and prompts with **quality iteration**: run a skill → LLM-judge output quality → retry until good. The evaluation question is "is this good enough?"

`mcp_tool` serves a different concern: **deterministic invocation + error recovery**. The evaluation question is "did this call succeed?" You would not run `browser/navigate` in a quality loop asking the LLM whether the navigation was "good" — you route on `isError`/`timeout`/`not_found`.

**The right layering:**
- `action_type: mcp_tool` is the primitive (this issue)
- A future enhancement extends create-loop's harness wizard to support "Harness an MCP tool" — listing available tools from `.mcp.json`, generating FSMs with `mcp_tool` states + `mcp_result` evaluation, for **work-item looping** (crawl a URL list, process DB rows, poll until ready). Same discover→execute→advance skeleton as the skill harness, different evaluation semantics.

Track as a follow-on: `FEAT: Extend create-loop harness wizard to support MCP tools as harness targets`.

## Related Issues

- P3-ENH-713: per-item retry limits (would benefit from `tool_error`/`timeout` routing)
- P3-ENH-717: detect replaceable LLM prompt states (could flag prompt states calling specific tools)
- P3-FEAT-659: hierarchical FSM loops
- P2-FEAT-712: Harness loop type (completed) — see Design Boundary section above

---

## Status

Active — not started.

## Verification Notes

- **Date**: 2026-03-14
- **Verdict**: VALID
- `action_type: mcp_tool` does not exist in `scripts/little_loops/fsm/schema.py`. The executor handles `prompt`, `slash_command`, and `shell` action types only. Feature not yet implemented.

## Session Log
- `/ll:refine-issue` - 2026-03-15T03:13:34 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/855ff716-46a0-4225-82ec-c048ef094860.jsonl`
- `/ll:verify-issues` - 2026-03-15T00:11:18 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/623195d5-5e50-40d6-b2b9-5b105ad77689.jsonl`
- `/ll:capture-issue` - 2026-03-13T21:15:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fffc83c9-009a-4696-8010-040737bf7247.jsonl`
- `/ll:format-issue` - 2026-03-13T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9b17321b-fc43-48b2-a2d7-478ef2d7ba48.jsonl`
- `/ll:verify-issues` - 2026-03-13T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9b17321b-fc43-48b2-a2d7-478ef2d7ba48.jsonl`
- `/ll:confidence-check` - 2026-03-13T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2acb782e-c208-43f1-8534-96bfd95ced6e.jsonl`
