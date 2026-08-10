---
target: mcp extension mechanism
date: '2026-08-10'
status: proven
assertions:
- claim: MethodBinding accepts a non-spec method name such as tasks/get and rejects
    a spec method name such as tools/list with ValueError at construction, so extension
    methods are additive-only
  result: pass
- claim: "no io.modelcontextprotocol/tasks extension ships in mcp 2.0.0 \u2014 the\
    \ only EXTENSION_ID defined in the package is io.modelcontextprotocol/ui in server/apps.py,\
    \ no tasks/* method appears in SPEC_CLIENT_METHODS, and no module has task in\
    \ its name"
  result: pass
- claim: Extension attaches via MCPServer(extensions=[...]) and the lowlevel Server
    used by little-loops' build_server() has no extensions parameter
  result: pass
- claim: Server.add_request_handler registers a custom tasks/get method on the unmodified
    build_server() Server and the method dispatches over streamable HTTP, returning
    the handler's result with wire params validated through the camelCase alias
  result: pass
- claim: MethodBinding.protocol_versions restricts a method to specific wire versions
    and an empty frozenset raises ValueError at construction
  result: pass
- claim: INPUT_REQUIRED_METHODS covers prompts/get, resources/read, and tools/call,
    and is_input_required is a TypeGuard over the MRTR input_required interim result
  result: pass
raw_output_path: .ll/learning-tests/raw/mcp-extension-mechanism.txt
proven_package: mcp
proven_version: 2.0.0
---
