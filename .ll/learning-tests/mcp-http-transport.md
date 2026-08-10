---
target: mcp HTTP transport
date: '2026-08-10'
status: proven
assertions:
- claim: NAME_BEARING_METHODS maps exactly tools/call->name, prompts/get->name, and
    resources/read->uri, so Mcp-Name is required only for those three methods
  result: pass
- claim: a body with method tools/list and no Mcp-Method header is rejected with JSON-RPC
    HEADER_MISMATCH (-32020), while the same body with the header is accepted
  result: pass
- claim: the params._meta envelope rung runs before the header rung, so a body missing
    the protocolVersion/clientCapabilities keys fails INVALID_PARAMS (-32602) even
    when every header is correct
  result: pass
- claim: a tools/call whose Mcp-Name header disagrees with params.name is rejected
    HEADER_MISMATCH (-32020), and a matching pair is accepted
  result: pass
- claim: the unmodified Server from little_loops.mcp_server.server.build_server()
    serves tools/list over streamable HTTP via StreamableHTTPSessionManager and returns
    the same five-tool catalog as the stdio handler, with no handler changes
  result: pass
- claim: subscriptions/listen is served by mcp.server.subscriptions.ListenHandler
    and its response is itself the event stream, with no standing GET stream on the
    2026-07-28 wire
  result: pass
raw_output_path: .ll/learning-tests/raw/mcp-http-transport.txt
proven_package: mcp
proven_version: 2.0.0
---
