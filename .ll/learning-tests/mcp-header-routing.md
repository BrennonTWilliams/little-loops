---
target: mcp header routing (SEP-2243)
date: '2026-08-11'
status: proven
assertions:
- claim: mcp 2.0.0 implements SEP-2243 in mcp/shared/inbound.py, exporting the canonical
    lowercase header names MCP_METHOD_HEADER ("mcp-method"), MCP_NAME_HEADER ("mcp-name"),
    and MCP_PROTOCOL_VERSION_HEADER, plus NAME_BEARING_METHODS mapping tools/call->name,
    prompts/get->name, resources/read->uri
  result: pass
- claim: "the library exposes NO pre-parse hook keyed on those headers - classify_inbound_request\
    \ takes the DECODED body as its first required positional parameter and headers\
    \ only as an optional keyword used to cross-check the body, so it cannot be invoked\
    \ on headers alone"
  result: pass
- claim: handle_modern_request in mcp/server/_streamable_http_modern.py parses the
    body (json.loads, line 343) BEFORE validating routing headers (classify_inbound_request,
    line 381), confirming header validation is a post-parse consistency check rather
    than a routing gate
  result: pass
- claim: server-side header handling is a mismatch REJECTION only - Mcp-Method must
    equal body.method and Mcp-Name must equal the named body param, else the request
    is rejected with HEADER_MISMATCH (-32020); the headers are never used to dispatch
  result: pass
- claim: ASGI middleware wrapped around Server.streamable_http_app() CAN read Mcp-Method
    and Mcp-Name from the raw scope["headers"] and short-circuit a request with a
    JSON-RPC error response WITHOUT awaiting the request body, so per-method transport
    policy before body parsing is achievable at the ASGI layer
  result: pass
raw_output_path: .ll/learning-tests/raw/mcp-header-routing.txt
proven_package: mcp
proven_version: 2.0.0
---

# Notes

Resolves **Open Question 1 on FEAT-3149** — with a **split verdict**.

EPIC-3127's assertion has two halves, and they do not both hold:

- **True:** SEP-2243 header routing exists in `mcp==2.0.0`, and per-method policy
  *can* run before JSON-RPC body parsing.
- **False:** the `mcp` library does not provide the hook. Its only use of these
  headers is a post-parse consistency check that rejects header/body disagreement
  (`HEADER_MISMATCH`, `-32020`). There is no pre-parse dispatch or policy
  extension point anywhere in the server package.

So FEAT-3149's Guard 2 is achievable, but **only via the ASGI-middleware
fallback already written into the issue** — not via a library hook. This is
proven, not assumed: the spike wraps `streamable_http_app()` in a middleware that
denies `tools/call` for a named tool on headers alone, returns `403` with a
JSON-RPC error body, and never awaits `receive()`.

Two consequences for implementation:

- The guard sits in `run_http()` only. The stdio transport has no HTTP headers,
  so any policy expressed this way is silently absent on stdio — the guard must
  be implemented once at the policy layer and *invoked* from the middleware,
  rather than living inside it.
- Because the server independently enforces header/body agreement, a middleware
  decision made on `Mcp-Method`/`Mcp-Name` cannot be contradicted by the body: a
  spoofed header is rejected downstream rather than silently trusted. The guard
  is therefore sound, which is the non-obvious part worth having proven.

See also [[mcp-http-transport]] and [[mcp-tasks-start-path]].
