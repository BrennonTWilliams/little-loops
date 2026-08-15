---
id: ENH-3172
type: ENH
title: "ll-mcp: resource and prompt indices go stale \u2014 enumerated once at startup,\
  \ never invalidated"
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-08-15'
captured_at: '2026-08-15T00:26:15Z'
parent: EPIC-3127
labels:
- mcp
relates_to:
- FEAT-3136
- FEAT-3137
depends_on:
- ENH-3171
---

# ENH-3172: ll-mcp: resource and prompt indices go stale — enumerated once at startup, never invalidated

## Summary

The `ll://` resource surface (FEAT-3136) and the prompts-from-skills surface (FEAT-3137)
are both enumerated exactly once, in `server.py::build_server()`, and the handlers close
over that frozen index for the life of the process. The tool surface is not — every tool
handler re-resolves `Path.cwd()` and re-reads the filesystem per call (the deliberate
statelessness invariant in `tools.py`).

The two halves therefore disagree about the same project, and the disagreement grows for
as long as the session lasts:

> An issue created via `issue_capture` (or by any `ll-*` CLI, or by a `loop_start`ed run)
> is immediately returned by `issues_query`/`issue_get`, but `resources/list` does not
> show `ll://issues/<ID>` and `resources/read` on that URI errors `Unknown resource` —
> until the server is restarted from the host.

Deleted or renamed issues fail the other way: the index still advertises a URI whose file
is gone, and the read path degrades it into an `INVALID_PARAMS` "unreadable" error at read
time (`_read_issue_body`'s OSError guard exists precisely because this window is real).
Newly added skills are invisible to `prompts/list` on the same terms.

This is currently documented as expected behavior in `docs/guides/MCP_SERVER_GUIDE.md` and
in the troubleshooting table ("Restart/reconnect the server"). That is an acceptable
description of a tier-1 read-only server; it is a poor fit now that the same process can
*create* issues (`issue_capture`, tier 2) and *start runs that create issues*
(`loop_start`, tier 3). The server invalidates its own cache and does not notice.

## Options

1. **Re-enumerate on demand with a freshness check.** Rebuild the index in
   `resources/list` / `prompts/list` when a cheap staleness signal fires (directory mtime
   on the issue category dirs, `skills/`, and `docs/`). Preserves the "the index is the
   allowlist" access-control property, since the rebuilt dict is still the only thing
   `resources/read` resolves against.
2. **Invalidate on known writes.** The four mutating tools and `loop_start` know they
   changed the tree; have them mark the index dirty. Cheaper, but misses every
   out-of-band change (a CLI in another terminal, a detached run) — which is most of them.
3. **Emit `notifications/resources/list_changed` / `notifications/prompts/list_changed`**
   after a rebuild, so a client re-fetches rather than serving its cached list. Note the
   server currently declares a 5-minute `public` `CacheHint` on `resources/list`,
   `resources/read`, and `prompts/list`, so a well-behaved client is *entitled* to serve a
   stale list for 5 minutes regardless — whatever is chosen here has to be reconciled with
   that hint, not layered on top of it.

Option 1 plus 3 is the shape that actually fixes the observable behavior; 2 alone does
not. The interaction with the existing `CacheHint` values is the real design question and
should be settled before implementation.


## Current Behavior

`build_resource_index()` and `build_prompt_index()` run once per `Server` instance. Every
subsequent `resources/list`, `resources/read`, `prompts/list`, and `prompts/get` resolves
against that snapshot. Issues and skills created, deleted, or renamed after startup are
invisible (or dangling) until the host restarts the server.

## Expected Behavior

An issue created by `issue_capture` — or by a `loop_start`ed run, or by a CLI in another
terminal — becomes readable as `ll://issues/<ID>` within the same server session, and a
deleted one stops being advertised. Same for `SKILL.md` files and `prompts/list`. Clients
are told when the list changed rather than being expected to guess.

## Impact

- **Priority**: P2 - The server now writes to the tree it serves (tier 2 and tier 3), so
  the read surface contradicts the write surface within one session. Documented as
  expected behavior today, which understates it.
- **Effort**: Medium - The rebuild itself is small; reconciling it with the existing
  5-minute `public` `CacheHint` on the same methods, and choosing between mtime polling
  and write-triggered invalidation, is the real work.
- **Risk**: Medium - The index is the access-control boundary for `resources/read`; any
  rebuild path must keep "membership in the dict is the rejection mechanism" true.
- **Breaking Change**: No

## Status

**Open** | Created: 2026-08-15 | Priority: P2


## Session Log
- `/ll:audit-issue-conflicts` - 2026-08-15T01:18:59 - `6343db1a-2326-4ea0-a5fc-0b0d7d522516.jsonl`
