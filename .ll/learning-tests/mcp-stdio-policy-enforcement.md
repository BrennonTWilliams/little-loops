---
target: raised MCPError reaching the wire from on_call_tool, both transports (FEAT-3168)
date: '2026-08-14'
status: proven
assertions:
- claim: a raised mcp.shared.exceptions.MCPError with a custom implementation-defined
    code (POLICY_DENIED_CODE, -32001) reaches the wire intact from the on_call_tool
    handler on the stdio transport, as a JSON-RPC error object with that exact code
  result: pass
- claim: the same raised MCPError reaches the wire intact from on_call_tool on the HTTP
    transport when the ASGI middleware layer is bypassed and the handler is reached
    directly, confirming handler_exception_to_error_data returns exc.error verbatim for
    MCPError on both transports rather than only one
  result: pass
- claim: a policy raise placed inside handle_call_tool's existing try/except block (Guard
    1's dry-run wrapper) would be caught by its catch-all and turned into
    CallToolResult(is_error=True, ...) instead of propagating as a protocol error - the
    guard-0 raise must sit before that try block, not inside it
  result: pass
raw_output_path: .ll/learning-tests/raw/mcp-stdio-policy-enforcement.txt
proven_package: mcp
proven_version: 2.0.0
---

# Notes

Closes FEAT-3168's Decision D3. `TransportPolicyMiddleware` (`policy.py`) already proved
the ASGI-layer half of this (`[[mcp-header-routing]]`): a JSON-RPC error dict written
directly to `send()`. What was unverified before this issue is the *handler-level* half —
whether `raise MCPError(code=POLICY_DENIED_CODE, ...)` from inside `on_call_tool` produces
the identical `-32001` shape on the wire, on both transports, given the pinned SDK's
dispatch machinery (`mcp/shared/jsonrpc_dispatcher.py::handler_exception_to_error_data`,
`mcp/server/runner.py::modern_error_data`).

Confirmed via `test_feat_3168_stdio_policy_enforcement.py`'s `_stdio_roundtrip()` (real
subprocess, real stdin/stdout) and the in-memory `Client` against `build_server()` with the
ASGI wrapper omitted. Both return `error.code == -32001` for a denied call, matching what
the middleware already returns over HTTP — the two mechanisms produce byte-identical
denial shapes despite one hand-building JSON and the other going through the SDK's own
exception-to-error-data ladder.

The insertion-point finding (guard 0 must precede the `try:` block, not sit inside it) is
the operationally load-bearing half: `tools.py`'s existing catch-all (`except Exception as
exc: return CallToolResult(is_error=True, ...)`) exists to turn tool-handler failures into
MCP's tool-result-error contract, and would silently swallow a policy denial into that same
shape if the raise were placed inside it — turning AC 1/3's `-32001` JSON-RPC error into an
ordinary tool result instead.

See also [[mcp-header-routing]] and [[mcp-tasks-start-path]].
