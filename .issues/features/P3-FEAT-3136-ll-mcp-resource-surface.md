---
id: 3136
title: 'll-mcp: ll:// resource surface'
type: FEAT
priority: P3
status: open
labels:
- multi-host
- mcp
parent: EPIC-3127
blocked_by:
- FEAT-3135
learning_tests_required:
- mcp
relates_to:
- FEAT-3132
---

# FEAT-3136: ll-mcp: ll:// resource surface

## Summary

The MCP resources surface for the `ll-mcp` server: issue files,
`ll-goals.md`, and docs, exposed under an `ll://` scheme (e.g.
`ll://issues/FEAT-042`, `ll://docs/…`). This builds on the running server
and dispatch loop from FEAT-3135 — it adds `resources/list` and
`resources/read` handling to the same server, resolved against a
discovery-time enumeration rather than arbitrary filesystem reads.

## Parent Issue

Decomposed from FEAT-3132: ll-mcp: core read-only server (tools, resources,
prompts-from-skills). This child covers the `ll://` resource surface; the
server skeleton, entry point, and tools surface are in FEAT-3135 (must land
first — this child registers its handlers on that server). Prompts-from-
skills is a separate sibling, FEAT-3137.

## Bind resource resolution at discovery, not at call time

The design does not yet say how a resource path is resolved. Because this
server exposes resources to arbitrary MCP clients, `little-loops` is the
loader and the trust boundary is external — unlike host-CLI-owned skill
loading elsewhere in the project, where the caller is already inside the
trust boundary.

- **Pre-enumerate supporting files at discovery time.** Walk the resource
  set once during startup and record the exact set of readable paths. A
  resource request then accepts a path that was enumerated, and is rejected
  otherwise. The server must never perform an arbitrary filesystem read
  derived from client-supplied input at call time — the enumeration, not
  path sanitization, is what makes traversal impossible.
- **Parse frontmatter only when listing.** `resources/list` needs name and
  description; reading full resource bodies at list time is both a context
  cost and an unnecessary widening of what is loaded. Fetch bodies on
  demand in `resources/read`.

This boundary must carry forward to the future mutation tier, where it
widens.

## Spec assumptions (MCP 2026-07-28)

- **Caching metadata is part of the contract.** `resources/list` and
  `resources/read` responses MUST include `ttlMs` and `cacheScope` per
  SEP-2549.
- **No `initialize` handshake.** Consistent with the server's existing
  dispatch loop from FEAT-3135 (protocol version + capabilities arrive in
  `_meta`).

## Integration Map

### Files to Modify
- The server module registered in FEAT-3135 (exact path depends on the
  module-placement decision made there) — add `resources/list` and
  `resources/read` handlers
- `docs/reference/CLI.md` — extend the `ll-mcp` section added by FEAT-3135
  with the resource surface

### Dependent Files (Callers/Importers)
- Depends on the server/dispatch-loop scaffolding registered by FEAT-3135;
  no other existing callers.

### Conventions in Force
- **No existing convention in this codebase pre-enumerates an allowlist at
  discovery time and rejects requests outside it** —
  `skill_expander.py:_resolve_content_path()` (lines 38-52) only does
  existence-checking, and `verify_package_data.py`'s escape lint is a
  build-time source lint, not a runtime request-path validator. The
  resource-resolution boundary this issue requires is new territory in this
  codebase, not a pattern to mirror.
- CLI tests import CLI module internals directly (not via subprocess) and
  isolate fixtures under `tmp_path` — evidence: `test_cli_ctx_stats.py`,
  `test_mcp_call.py:TestLoadMcpConfig` (lines 43-60).

### Tests
- New tests for the resource enumeration/resolution boundary: verify a
  request for a path outside the discovery-time enumeration is rejected
  without a filesystem read, and that `resources/list`/`resources/read`
  include `ttlMs`/`cacheScope`.
- `test_goals_parser.py:106-183,392` (`TestProductGoals`) — full error-path
  matrix for the `ll-goals.md` resource: missing/malformed/empty
  frontmatter, unreadable file. Reuse these fixtures for the resource
  handler's own tests rather than re-deriving them.

### Documentation
- `docs/reference/CLI.md` — extend the `ll-mcp` section (added by
  FEAT-3135) with the resource surface's `ll://` scheme and examples.

## Program Design

### Types
- `little_loops.goals_parser.ProductGoals` (`.from_file(path: Path) ->
  ProductGoals | None`, `goals_parser.py:92`) — dataclass with `version`,
  `persona`, `priorities`, `raw_content`; `raw_content` is the full
  markdown, usable directly as the body of an `ll://goals` resource. No
  caller in this module resolves the default `.ll/ll-goals.md` path — the
  resource handler must construct it itself.

### Call Path
- `ll://goals` resource → `little_loops.goals_parser.ProductGoals.from_file()`
- `ll://issues/<ID>` resource → issue file read, resolved against the
  discovery-time enumeration of `.issues/` files
- `ll://docs/...` resource → docs file read, resolved against the
  discovery-time enumeration of `docs/` files

### Decision Rules
N/A — no new gap kind, gate, keyword list, or threshold.

## Implementation Steps

1. The `ll://` resource surface's discovery-time enumeration (issue files,
   `ll-goals.md`, docs) is built once at startup on the server registered
   in FEAT-3135; `resources/read` is verified to reject any path outside
   that enumeration without performing a filesystem read. `resources/list`
   and `resources/read` responses include `ttlMs`/`cacheScope`.
2. `python -m pytest scripts/tests/` passes, including new coverage for the
   resource enumeration/resolution boundary.

## Acceptance criteria

- Issue files, `ll-goals.md`, and docs are listed and readable as MCP
  resources under the `ll://` scheme.
- `resources/read` resolves only against the discovery-time enumeration; a
  request for a path outside it is rejected without a filesystem read.
- `resources/list` and `resources/read` responses include `ttlMs` and
  `cacheScope`.
- `python -m pytest scripts/tests/` passes.

## Session Log
- `/ll:issue-size-review` - 2026-08-09T07:40:09 - `153550d2-faf1-4350-b263-1aaa047c80e3.jsonl`
