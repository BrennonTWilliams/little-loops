---
id: EPIC-2790
title: Subprocess and MCP Robustness
type: EPIC
priority: P1
status: done
captured_at: "2026-07-25T02:35:31Z"
discovered_date: 2026-07-25
discovered_by: create-epics-from-unparented
relates_to:
- BUG-2777
- BUG-2778
- BUG-2779
---

# EPIC-2790: Subprocess and MCP Robustness

## Summary

Group of 3 related issues concerning subprocess and MCP client lifecycle
correctness — timeouts that fail to bound blocking I/O, and process cleanup that
leaves zombies. Includes: BUG-2777 (`_run_cmd` per-command timeout not enforced
while subprocess holds stdout open), BUG-2778 (`_send_jsonrpc` deadline does not
bound blocking `readline()`), BUG-2779 (`call_mcp_tool` cleanup issues `kill()`
without a follow-up `wait()`).

## Children

- **BUG-2777** — `_run_cmd` per-command timeout not enforced while subprocess holds stdout open
- **BUG-2778** — `_send_jsonrpc` deadline does not bound blocking `readline()`; unresponsive MCP server hangs `call_mcp_tool` indefinitely
- **BUG-2779** — `call_mcp_tool` cleanup issues `kill()` without a follow-up `wait()`, leaving a zombie process

## Related Key Documentation

- `docs/reference/API.md` — documents the transport/subprocess-invocation
  layer (`_run_cmd`, `_send_jsonrpc`, `call_mcp_tool`) these three children
  fix the lifecycle correctness of.

## Verification Notes

- 2026-08-10: Verified 2026-08-10 via /ll:verify-issues: all child issues confirmed done — closing epic.


## Session Log
- `/ll:verify-issues` - 2026-08-10T16:25:22 - `50b69f30-8ca9-4ab9-8b06-6ee21c203b10.jsonl`
