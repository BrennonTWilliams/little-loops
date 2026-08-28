---
id: ENH-3353
type: ENH
title: Document stdio stdout JSON-RPC frame constraint in MCP server guide
priority: P4
status: open
testable: false
discovered_by: ll-issues-create
discovered_date: '2026-08-28'
captured_at: '2026-08-28T18:42:53Z'
---

# ENH-3353: Document stdio stdout JSON-RPC frame constraint in MCP server guide

## Summary

Document, in `docs/guides/MCP_SERVER_GUIDE.md`, the constraint that an `ll-mcp` tool
handler must never let a `cmd_*` CLI function print: on the stdio transport stdout is
the JSON-RPC frame. The rule is currently stated only in a source comment, where a
contributor adding a tool will not find it.

## Current Behavior

The constraint is recorded at `scripts/little_loops/mcp_server/tools.py:238-241`, in
the tier-2 block comment: `stdout *is* the JSON-RPC frame, so calling them here would
corrupt the protocol.` The two shipped workarounds are both in source only —
FEAT-3149 extracted `apply_status_transition` / `apply_link` so the mutating handlers
wrap non-printing library functions, and `_tool_loop_start` wraps `run_background()`
in `contextlib.redirect_stdout` / `redirect_stderr` because that function prints on
success.

`docs/guides/MCP_SERVER_GUIDE.md` is written for operators and callers: install,
project-root binding, client registration, verifying with `mcp-call`, the mutation
guards, and `tasks/*`. It has no contributor-facing section on adding a tool, and no
mention of the stdout hazard.

Separately, the heading `### The five tools, end to end` (around line 203) is stale
after FEAT-3343 — the tier-1 read surface is now seven tools, and the inventory table
at lines 32-33 already lists all seven. The walkthrough below the heading still covers
five.

## Expected Behavior

A contributor opening `docs/guides/MCP_SERVER_GUIDE.md` to add a tool finds a short
"Adding a tool" section that states the stdout/JSON-RPC-frame constraint up front,
names both mitigations with pointers to the source that demonstrates each, and lists
the registration steps. No heading in the guide reports a stale tool count.

## Motivation

The failure mode is silent and confusing: a handler that wraps a printing `cmd_*`
corrupts the JSON-RPC frame, and the client reports a parse error that points nowhere
near the offending tool. It is the single most likely defect when adding a tool, and
the guidance exists but is not discoverable from the docs.

## Proposed Solution

Promote the existing source comment into a contributor-facing section of the MCP
server guide, and refresh the stale tool-count heading while in the file. Docs-only —
no code change.

### Files to Modify
- `docs/guides/MCP_SERVER_GUIDE.md` — add the "Adding a tool" section; fix the
  `### The five tools, end to end` heading (~line 203)

### Similar Patterns
- `scripts/little_loops/mcp_server/tools.py:236-241` — the tier-2 block comment this
  section promotes
- `_tool_loop_start` in the same file — the `redirect_stdout` / `redirect_stderr`
  mitigation to cite

### Tests
- Docs gates already in `python -m pytest scripts/tests/` (link/anchor checking); no
  new tests.

### Documentation
- This issue is the documentation change.

### Configuration
- N/A

## Implementation Steps

1. Add a short contributor section to `docs/guides/MCP_SERVER_GUIDE.md` — "Adding a
   tool" — covering: the stdout/JSON-RPC-frame rule; prefer extracting a non-printing
   library function (the FEAT-3149 pattern) over wrapping `cmd_*`; use
   `redirect_stdout` / `redirect_stderr` only when extraction is not practical (the
   `_tool_loop_start` precedent); register in both `_TOOL_HANDLERS` and `_TOOLS`; and
   add write tools to `policy.MUTATING_TOOLS`, never `TASK_STARTING_TOOLS`.
2. Fix the stale `### The five tools, end to end` heading and extend or re-scope the
   walkthrough to match the current tier-1 surface.

## Impact

- **Priority**: P4 - Prevents a confusing silent failure for anyone adding a tool, but
  the rule is already recorded in source and the current handlers all follow it.
- **Effort**: Small - Docs-only; the content already exists as a source comment.
- **Risk**: Low - No code paths touched.
- **Breaking Change**: No

## Acceptance Criteria

- [ ] `docs/guides/MCP_SERVER_GUIDE.md` states the stdout/JSON-RPC-frame constraint
      and names both mitigations, with pointers to the `mcp_server/tools.py` call
      sites that demonstrate each.
- [ ] The tool-registration checklist covers `_TOOL_HANDLERS`, `_TOOLS` source order,
      and the `policy.MUTATING_TOOLS` / `TASK_STARTING_TOOLS` split.
- [ ] No heading or walkthrough in the guide reports a stale tool count.
- [ ] `ll-verify-docs` / the docs gates in `python -m pytest scripts/tests/` pass.

## Related Key Documentation

| Document | Relevance |
|---|---|
| `docs/guides/MCP_SERVER_GUIDE.md` | The file this issue edits |
| `docs/reference/API.md` | `little_loops.mcp_server` module reference |

## Status

**Open** | Created: 2026-08-28 | Priority: P4


## Session Log
- `/ll:capture-issue` - 2026-08-28T18:43:17 - `51a7dd65-db46-4ad2-be82-40e74f2445d1.jsonl`
