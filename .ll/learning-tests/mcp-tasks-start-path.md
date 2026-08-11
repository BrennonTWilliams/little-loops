---
target: mcp tasks start path (SEP-2663)
date: '2026-08-11'
status: proven
assertions:
- claim: "SEP-2663 defines no tasks/create method — a task is started by an ordinary\
    \ tools/call whose response carries the CreateTaskResult shape (resultType: \"\
    task\") in lieu of a CallToolResult; the client signals support via per-request\
    \ capabilities and the server decides per-request whether to materialize a task"
  result: pass
- claim: a tools/call handler returning a task-shaped plain Mapping reaches the wire
    unmodified over streamable HTTP - runner._serialize skips the spec-method sieve
    whenever resultType is a modern-era string outside CORE_RESULT_TYPES (frozenset{'input_required',
    'complete'}), so an extension-owned shape is passed through rather than validated
    against CallToolResult
  result: pass
- claim: _dump_result accepts BaseModel, dict, or None, so returning a raw Mapping
    from on_call_tool works at runtime even though the parameter is typed Awaitable[CallToolResult
    | InputRequiredResult]
  result: pass
- claim: Extension.intercept_tool_call short-circuits tools/call with a CreateTaskResult
    and composes onto the LOWLEVEL Server that build_server() uses via the free function
    compose_tool_call_handler(extensions, handler) - no MCPServer(extensions=[...])
    and no extensions= parameter required
  result: pass
- claim: tasks/get, tasks/update, and tasks/cancel each register on the unmodified
    build_server() Server via Server.add_request_handler(method, params_type, handler)
    and dispatch over streamable HTTP, returning the handler's result
  result: pass
- claim: MethodBinding still raises ValueError at construction for the spec method
    tools/call, and the error text itself names the sanctioned alternatives (Extension.intercept_tool_call
    or Server.middleware) - so the additive-only naming rule is not violated by the
    start path, because the start path never registers tools/call
  result: pass
raw_output_path: .ll/learning-tests/raw/mcp-tasks-start-path.txt
proven_package: mcp
proven_version: 2.0.0
---

# Notes

Resolves **Open Question 1 on FEAT-3145** — affirmatively.

The premise the question was built on ("SEP-2663's start path is an augmentation
of `tools/call`, and `MethodBinding` rejects `tools/call`, therefore a
spec-faithful start path is unreachable via `add_request_handler`") contains a
false step. The start path does not *register* `tools/call` at all. It changes
what the **already-owned** `tools/call` handler returns. `ll-mcp` owns that
handler (`on_call_tool=handle_call_tool` in `mcp_server/server.py`), so nothing
needs to be re-registered and the additive-only rule is never engaged.

Three independently sufficient mechanisms exist on the pinned `mcp==2.0.0`:

1. Return a task-shaped `Mapping` directly from `handle_call_tool`.
2. Wrap it with `compose_tool_call_handler([TasksExtension()], handle_call_tool)`
   — the extension-faithful path, usable on the lowlevel `Server`.
3. `Server.middleware`, for wire-level rewriting above params validation.

The `resultType` passthrough is deliberate, not incidental:
`mcp/server/runner.py:364-378` documents it as "a claimed extension `resultType`
shape is the extension's to own". Note the `TODO(L56)` there — a future version
may reject extension `resultType` values unless the matching extension appears in
the request's `_meta.clientCapabilities.extensions`. Emitting `resultType: "task"`
without honoring the client's declared extension capabilities is therefore
forward-incompatible even though it passes today.

See also [[mcp-extension-mechanism]] (the additive-only `MethodBinding` rule and
the absence of a shipped tasks extension) and [[mcp-header-routing]].
