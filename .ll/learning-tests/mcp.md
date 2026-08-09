---
target: mcp
date: '2026-08-09'
status: proven
assertions:
- claim: The official `mcp` Python SDK ships version 2.0.0 on PyPI, the "SDK v2" FEAT-3135
    requires pinning for 2026-07-28-spec behavior (installed 1.21.0 does not implement
    it)
  result: pass
- claim: The stdio server transport frames messages as newline-delimited JSON via
    a `readline`-style loop and `model_dump_json`, not LSP-style `Content-Length:`
    header framing
  result: pass
- claim: On a 2026-07-28 ("modern") connection, the server rejects an `initialize`
    request with `UNSUPPORTED_PROTOCOL_VERSION` rather than performing the legacy
    handshake
  result: pass
- claim: ttlMs/cacheScope are a first-class server-side caching contract (`mcp.server.caching`),
    not just a client-side convenience
  result: pass
- claim: The lowlevel `Server` runner auto-fills `ttlMs`/`cacheScope` onto spec-method
    results a handler leaves unset
  result: pass
- claim: The lowlevel `Server`'s tool-registration API is documented via handler registration
    (list_tools/call_tool) rather than requiring hand-rolled JSON-RPC method dispatch
  result: pass
raw_output_path: .ll/learning-tests/raw/mcp.txt
proven_package: mcp
proven_version: 2.0.0
---
