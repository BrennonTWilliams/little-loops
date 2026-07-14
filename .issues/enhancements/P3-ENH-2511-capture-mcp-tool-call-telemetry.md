---
id: ENH-2511
title: Capture MCP tool-call telemetry in tool_events
type: ENH
priority: P3
status: open
discovered_date: 2026-07-06
captured_at: "2026-07-06T00:00:00Z"
discovered_by: capture-issue
parent: EPIC-2457
depends_on: [ENH-2497]
labels:
  - enhancement
  - history-db
  - mcp
  - widening
  - captured
---

# ENH-2511: Capture MCP tool-call telemetry in tool_events

## Summary

Every MCP server call (e.g., `mcp__pencil__batch_design`,
`mcp__zai-mcp-server__analyze_image`) produces a tool invocation with
its own server/tool/outcome semantics — but the live `tool_events`
write records it as `tool_name="mcp__pencil__batch_design"` (the full
prefixed name), with no clean breakdown of `server` vs. `tool`, no
`outcome_class` (`success` | `error` | `timeout`), and no `args` /
`result_size` / `latency_ms`. So "how often does pencil fail" or "which
MCP server burns the most tool_events rows" can't be answered without
string parsing the tool_name. Add three nullable columns to
`tool_events` — `mcp_server`, `mcp_tool`, `mcp_outcome` — and widen
ENH-2497's migration so the same v19 migration carries both changes.
Overlaps ENH-2497 explicitly noted in the user's gap list.

## Motivation

- **MCP calls are first-class tool uses but second-class in tool_events.**
  The full `mcp__pencil__batch_design` name lives in `tool_name`, but
  the server/tool breakdown requires string parsing. A column for each
  is one ALTER TABLE away.
- **Outcome classification is missing.** `tool_events` has
  `bytes_out` (proxy for response size) but no
  `success`/`error`/`timeout` discriminator. The `tool_response`
  payload carries the outcome (MCP results return `{isError: true}` or
  the equivalent), but it's not extracted.
- **Latency_ms is missing.** Other event tables (test_run_events at
  v18, commit_events at v17) carry `duration_ms`; tool_events has
  `bytes_in/out` and `cache_hit` but not elapsed time. Adding
  `latency_ms` to `tool_events` is the natural symmetry.
- **Widens ENH-2497 rather than spawning a new table.** ENH-2497 adds
  `agent_type` to `tool_events` (also nullable, same migration target
  v19). Adding `mcp_server`, `mcp_tool`, `mcp_outcome`, `latency_ms`
  to the same migration is one version bump, multiple additive
  columns. Same pattern ENH-2498 used to widen ENH-2494.

## Current Behavior

- A `mcp__pencil__batch_design` call writes a `tool_events` row with
  `tool_name="mcp__pencil__batch_design"` (full prefixed string) and
  the usual byte accounting. No server/tool breakdown, no outcome
  discriminator.
- `_backfill_tool_events` (`session_store.py:1620-1664`) extracts
  `subagent_type` from Task calls (after ENH-2497) but not MCP
  breakdown.
- There is no way to ask `SELECT COUNT(*) FROM tool_events WHERE
  mcp_server='pencil' AND mcp_outcome='error'` — the columns don't
  exist.

## Expected Behavior

- `tool_events` gains four nullable columns: `mcp_server TEXT`,
  `mcp_tool TEXT`, `mcp_outcome TEXT` (`success` | `error` |
  `timeout`), and `latency_ms INTEGER` (elapsed time of the MCP /
  tool call).
- The live `post_tool_use` write at `post_tool_use.py:163-177`
  extracts `server` and `tool` from the `mcp__<server>__<tool>` prefix
  when present, and reads `tool_response.isError` (or the
  MCP-shape equivalent) for `outcome`.
- `latency_ms` is computed from the tool-call wallclock — available
  from the Claude Code host via `tool_call.started_at` /
  `tool_call.completed_at`, or measured by the hook handler with
  `time.monotonic()` around the dispatch.
- Non-MCP tool calls leave the new columns NULL.
- `ll-session recent --kind tool --server pencil --outcome error` (or
  equivalent filter via the existing `--kind tool` plus new flags)
  returns the MCP failure subset.

## Proposed Solution

### Schema migration (v19, batched with ENH-2497)

```sql
ALTER TABLE tool_events ADD COLUMN mcp_server TEXT;
ALTER TABLE tool_events ADD COLUMN mcp_tool TEXT;
ALTER TABLE tool_events ADD COLUMN mcp_outcome TEXT;
ALTER TABLE tool_events ADD COLUMN latency_ms INTEGER;
CREATE INDEX IF NOT EXISTS idx_tool_events_mcp_server ON tool_events(mcp_server);
CREATE INDEX IF NOT EXISTS idx_tool_events_mcp_outcome ON tool_events(mcp_outcome);
```

Bump `SCHEMA_VERSION = 18` → `19`. Coordinate with ENH-2497's
`agent_type` column (also a `tool_events` ALTER) — single migration
batch. Pre-migration rows read back with `mcp_server=NULL,
mcp_tool=NULL, mcp_outcome=NULL, latency_ms=NULL`.

### Producer wiring

- In `scripts/little_loops/hooks/post_tool_use.py:handle()`, inside
  the existing `contextlib.suppress(Exception)` block:
  - Compute `mcp_server`, `mcp_tool` by parsing `tool_name` when it
    matches `^mcp__(.+?)__(.+)$`.
  - Compute `mcp_outcome` by inspecting `tool_response.isError` (MCP
    standard) or `tool_response.error` (legacy); default to `success`
    when the response is non-empty and `error` is absent.
  - Compute `latency_ms` from `tool_call.started_at` /
    `tool_call.completed_at` if present in the payload; else leave
    NULL (don't measure from the hook handler — that measures only
    the hook itself, not the tool).
- Extend `_backfill_tool_events` (`session_store.py:1620-1664`) to
  extract the same fields from historical JSONL assistant blocks.

### Read API

- `history_reader.mcp_server_usage(server=None, since=None)` —
  call counts and average latency per server.
- `history_reader.mcp_failure_rate(server=None, tool=None, since=None)`
  — fraction of MCP calls with `mcp_outcome='error'`.
- Extend `agent_usage` (ENH-2497) to roll up MCP servers alongside
  subagent types.

### CLI surface

- `ll-session recent --kind tool --mcp-server pencil` (optional flag).
- `ll-ctx-stats`: add an "MCP server health" block (per-server
  success/latency rollup).

## Acceptance Criteria

- Schema migration lands; the four new columns exist on `tool_events`;
  `SCHEMA_VERSION` bumped.
- An `mcp__pencil__batch_design` call writes a row with
  `mcp_server="pencil"`, `mcp_tool="batch_design"`,
  `mcp_outcome="success"` (or `"error"` on failure), and
  `latency_ms=<elapsed>`.
- A non-MCP tool call (`Read`, `Write`, `Edit`) leaves all four new
  columns NULL.
- Pre-migration rows read back with all four columns NULL (no data
  fix required).
- Writes are best-effort: a malformed MCP response payload leaves the
  columns NULL, never raises.
- `ll-session recent --kind tool` returns rows with the new columns
  populated for MCP entries; the MCP failure rate query works.
- Tests cover: success/error/timeout outcomes, non-MCP NULL handling,
  pre-migration NULL handling, DB-absent graceful degradation.

## Sources

- EPIC-2457 review (third-pass expansion, 2026-07-06) — item from the
  user-reported gap list (explicitly noted as "Overlaps ENH-2497")
- ENH-2497 — sibling `agent_type` column on `tool_events`; this issue
  shares the migration
- `scripts/little_loops/hooks/post_tool_use.py` — live producer
- `.mcp.json` / `~/.claude/.mcp.json` — MCP server catalog whose usage
  this makes observable
- ENH-2493 — sibling executor telemetry work

## Related Key Documentation

| Document | Why Relevant |
|----------|--------------|
| `docs/ARCHITECTURE.md` | Schema versions table |
| `docs/reference/API.md` | `session_store`, `history_reader` modules |
| `docs/reference/CLI.md` | `ll-session --kind tool` extensions |

## Status

**Open** | Created: 2026-07-06 | Priority: P3

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): This issue and **ENH-2497**
both propose additive `ALTER TABLE tool_events ADD COLUMN ...` migrations
against the *same* target schema version and explicitly plan to land as one
batched migration (this issue's own text: "Overlaps ENH-2497 explicitly noted
in the user's gap list" / "Coordinate with ENH-2497's `agent_type` column
... single migration batch"). Verified against current code
(`scripts/little_loops/session_store.py`): `SCHEMA_VERSION` is now **20**
(v17=`commit_events`/ENH-2458 done, v18=`test_run_events`/ENH-2459 done,
v19=`raw_events`/ENH-2581 done, v20=`usage_events`/ENH-2461 done) — neither
issue's stale "bump 18→19" Integration Map text is current. `depends_on:
[ENH-2497]` has been added to this issue's frontmatter so ENH-2497 is
implemented first (its `agent_type` column lands), and this issue's migration
is authored as an *addition to that same migration block* rather than a
second independent `tool_events` ALTER — avoiding two competing migrations
racing for the same next-available schema version.

## Session Log
- `/ll:audit-issue-conflicts` - 2026-07-14T00:21:42 - `33e15d2a-429d-48f8-8998-aca5080acdd5.jsonl`
- `/ll:capture-issue` - 2026-07-06T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/`