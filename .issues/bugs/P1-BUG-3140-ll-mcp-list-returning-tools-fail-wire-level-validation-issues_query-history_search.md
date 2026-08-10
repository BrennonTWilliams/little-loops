---
id: BUG-3140
type: BUG
title: ll-mcp list-returning tools fail wire-level validation (issues_query, history_search)
priority: P1
status: done
discovered_by: ll-issues-create
discovered_date: '2026-08-10'
captured_at: '2026-08-10T01:38:09Z'
testable: true
completed_at: '2026-08-10T01:37:56Z'
labels:
- mcp
- docs
- protocol
relates_to:
- FEAT-3135
- FEAT-3136
- FEAT-3137
---

# BUG-3140: ll-mcp list-returning tools fail wire-level validation (issues_query, history_search)

## Summary

`issues_query` and `history_search` returned JSON-RPC `-32603 "Handler returned an
invalid result"` for every real MCP client, while the other three tools worked.

`handle_call_tool` passed `structured_content=payload` unconditionally
(`mcp_server/tools.py:322`). Those two handlers return a JSON **list**
(`tools.py:77`, `tools.py:125`); the rest return dicts. Per the SDK's own
`CallToolResult` docstring, `structuredContent` is an arbitrary JSON value only on
protocol 2026-07-28 — every earlier version restricts it to a JSON object — and
`mcp==2.0.0` negotiates down to 2025-11-25 even when the client requests 2026-07-28.
The list therefore failed encode validation on every negotiable version.

The 22 existing tests stayed green because they drive the SDK's in-memory
`Client(server)`, which dispatches in-process and never serializes the result. The
defect was reachable only across a real stdio transport.

Found while writing `docs/guides/MCP_SERVER_GUIDE.md`, by exercising all five tools
against a live server rather than trusting the test suite.

## Current Behavior

Two of the five advertised tools were unusable from any MCP client. Reproduced by
spawning `ll-mcp` as a subprocess and speaking framed JSON-RPC at it:

| Requested protocol | Negotiated | `issues_query` / `history_search` | Other three tools |
|---|---|---|---|
| `2024-11-05` | `2024-11-05` | `-32603` | OK |
| `2025-06-18` | `2025-06-18` | `-32603` | OK |
| `2026-07-28` | `2025-11-25` | `-32603` | OK |

`mcp-call ll-mcp/issues_query '{}'` exited `1` with
`tools/call error: {'code': -32603, 'message': 'Handler returned an invalid result'}`.

## Expected Behavior

All five tools return successfully over stdio on every protocol version
`mcp==2.0.0` will negotiate, with the full payload in `content[0].text`.

## Steps to Reproduce

With the fix reverted (`structured_content=payload` unconditional):

```bash
printf '%s\n' \
  '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"repro","version":"1"}}}' \
  '{"jsonrpc":"2.0","method":"notifications/initialized"}' \
  '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"issues_query","arguments":{"limit":5}}}' \
  | ll-mcp
```

Response to `id: 2` is
`{"code": -32603, "message": "Handler returned an invalid result"}`. Substituting
`history_search` reproduces identically; `deps_check` succeeds.

## Root Cause

`structured_content` was attached regardless of payload type. Dict payloads
(`issue_get`, `deps_check`, `capabilities`) satisfy the pre-2026-07-28 object
restriction; list payloads do not, and the SDK rejects them at encode time — after
the handler returns, so no handler-level error handling could see it.

## Program Design

### Signatures

- `handle_call_tool(ctx: ServerRequestContext[Any], params: CallToolRequestParams) -> CallToolResult` — the single dispatch point where the payload is wrapped; the only line changed
- `CallToolResult(content: list[ContentBlock], structured_content: Any = None, is_error: bool = False)` — SDK type; `structured_content` is object-restricted before protocol 2026-07-28
- `_stdio_call(tmp_path: Path, protocol_version: str, tool: str, arguments: dict) -> dict` — test helper spawning `ll-mcp` and returning the parsed `tools/call` response

### Call Path

MCP client -> stdio transport -> SDK dispatch -> `handle_call_tool`
(`mcp_server/tools.py:294`) -> `_TOOL_HANDLERS[name]` -> `types.CallToolResult` ->
**SDK encode/validate** (the failing step) -> stdio transport -> client

### Decision Rules

- `structured_content` is attached only for `dict` payloads. Any other type — list
  today, scalar in future — is omitted rather than coerced or wrapped: wrapping
  (`{"results": [...]}`) would change the documented `content[0].text` shape and
  every caller with it.
- `content[0].text` remains the single guaranteed payload channel for all five
  tools; `structured_content` is a best-effort convenience for clients that read it.
- Test coverage for the tool surface must include at least one case that crosses a
  real transport. In-process dispatch cannot observe encode-time validation.

## Resolution

### Fix

`scripts/little_loops/mcp_server/tools.py:320` — attach `structured_content` only
when the payload is a dict:

```python
structured_content=payload if isinstance(payload, dict) else None,
```

The full payload, list or dict, always travels in `content[0].text`. That is the
shape `docs/reference/CLI.md` documents and every existing test reads, so this is a
pure defect fix with no contract change.

### Regression test

`scripts/tests/test_mcp_server.py` — added `_stdio_call()` plus
`test_list_returning_tools_serialize_over_stdio`, 6 parametrized cases
(2 list-returning tools × 3 protocol versions). Unlike every other test in the file
it crosses the wire: spawns the server as a subprocess and exchanges framed JSON-RPC,
which is the only way to observe an encode-time failure.

Mutation-checked: reverting the one-line fix fails all 6; restoring it passes all 6.

### Documentation

`docs/guides/MCP_SERVER_GUIDE.md` (new) — setup and operations guide for `ll-mcp`,
deliberately restating no schemas (CLI.md § `ll-mcp` stays authoritative):

- the `[mcp]` extra and how its absence presents in a host
- the working-directory requirement — `tools.py:37` resolves the project root as
  `Path.cwd()`, so a client spawning from `$HOME` returns silently empty results from
  every tool with no error
- registration for Claude Code and Codex via `ll-adapt`, plus a hand-written Claude
  Desktop config (absolute binary path: GUI clients don't inherit shell `PATH`)
- `mcp-call` verification recipes for all five tools with captured responses, and the
  `0/1/124/127/2` exit-code ladder as a layer-isolation tool
- startup-enumeration asymmetry: a new issue is visible to `issues_query`/`issue_get`
  immediately but absent from `resources/list` until restart; prompts resolve from
  `$CLAUDE_PLUGIN_ROOT`, so a pip-only install lists zero
- read-only rationale pointing at `ll-issues create` / `/ll:capture-issue`
- troubleshooting table and a copy-pasteable raw JSON-RPC session

Wiring: `mkdocs.yml` nav, `docs/index.md`, and a reverse link from CLI.md's `ll-mcp`
section to the guide.

## Impact

- **Priority**: P1 - Two of five tools on the MCP surface were broken for every
  client, on every negotiable protocol version, since FEAT-3135 shipped.
- **Effort**: Small - One-line fix; the test harness was the real work.
- **Risk**: Low - `content[0].text` unchanged; no contract or schema change.
- **Breaking Change**: No

## Acceptance Criteria

- [x] `issues_query` and `history_search` succeed over real stdio on 2024-11-05,
      2025-06-18, and a 2026-07-28 request (negotiated to 2025-11-25)
- [x] A wire-level regression test exists and fails without the fix
- [x] `docs/guides/MCP_SERVER_GUIDE.md` covers setup, cwd, verification, and
      troubleshooting without duplicating CLI.md schemas
- [x] Guide is reachable from `mkdocs.yml` nav, `docs/index.md`, and CLI.md
- [x] `python -m pytest scripts/tests/` exits 0

## Related Key Documentation

- `docs/guides/MCP_SERVER_GUIDE.md` (added by this issue)
- `docs/reference/CLI.md` § `ll-mcp` — authoritative tool schemas
- `docs/reference/API.md` § `little_loops.mcp_server`

## Context

The in-memory `Client(server)` harness chosen in FEAT-3135 is fast and matches the
2026-07-28 connection model, but it skips serialization entirely. Any future defect
in result *encoding* — not just this one — is invisible to it. The new stdio test is
the standing counterweight; keep at least one wire-level case whenever the tool
surface changes.

## Verification

- `python -m pytest scripts/tests/` — 18,846 passed, 43 skipped (434s)
- `python -m pytest scripts/tests/test_mcp_server.py` — 28 passed (was 22)
- `ruff check` / `ruff format --check` clean on changed files
- `python -m mypy scripts/little_loops/mcp_server/` — no issues in 5 source files
- `ll-verify-private-refs` — PASS on the new and edited docs

## Session Log
- `hook:posttooluse-status-done` - 2026-08-10T01:39:16 - `d15a182b-4ce6-4519-ae5f-daa9fbff863e.jsonl`
- Manual session - 2026-08-10T01:37:56Z - guide design review, defect discovery, fix,
  regression test, documentation

---

## Status

done
