---
id: ENH-2505
title: Link subagent session-tree (parent→child) into history.db
type: ENH
priority: P3
status: open
discovered_date: 2026-07-06
captured_at: "2026-07-06T00:00:00Z"
discovered_by: capture-issue
parent: EPIC-2457
labels:
  - enhancement
  - history-db
  - agents
  - captured
---

# ENH-2505: Link subagent session-tree (parent→child) into history.db

## Summary

Every `Agent` (Task) tool spawn produces a child session_id; the parent →
child relationship is currently invisible because tool_events records the
spawn as a generic `Task` row but never links the spawned session back to
its caller. So "which parent sessions burn budget on subagent retries",
"how often does Task spawn an `Explore` agent", and "which subagents
oscillate the most" — the three questions the kill-analysis
(`autodev-bug2501-kill-analysis.md`) couldn't answer — are unanswerable
without re-parsing JSONL. Add a `subagent_runs` table (or fold as columns
into `sessions`) capturing `(parent_session_id, child_session_id,
agent_type, started_at, ended_at)` so the spawn tree is queryable.

## Motivation

- **The parent→child linkage is the missing join.** ENH-2497 captures
  `agent_type` on `tool_events`, so we know *what* was spawned; this issue
  captures *which session the spawn belongs to* and *what that session
  returned*. Together they answer "parent X spawned N children of type Y,
  P% of which re-spawned children of their own."
- **ENH-2497 covers the spawn event but not the lifecycle.** Without
  `ended_at`, you can't tell a subagent that's still running from one that
  crashed mid-flight. Without the parent linkage, you can't tell which
  parent's budget a subagent burned.
- **The kill-analysis showed the cost.** The autodev-kill analysis had to
  walk three separate session IDs by hand because the tool_events row
  carried the spawn but not the resulting session_id. A single
  `subagent_runs` row would have surfaced the tree in one query.

## Current Behavior

- A `Task` spawn is recorded by `post_tool_use` as a `tool_events` row
  with `tool_name="Task"`, `agent_type=<subagent_type>` (after ENH-2497),
  and the tool response payload — but the *child session_id* returned by
  the spawn is not extracted from the response.
- There is no way to ask "which subagents did session `a21e4561-...`
  spawn?" without reading JSONL.
- `ll-ctx-stats` / `ll-logs dead-skills` cover skill usage; nothing
  covers subagent trees.

## Expected Behavior

- A `subagent_runs` table records one row per subagent spawn with
  `parent_session_id`, `child_session_id`, `agent_type`, `started_at`,
  `ended_at` (nullable while running), and `status` (`running` |
  `completed` | `failed` | `timeout`).
- The Agent tool's `tool_response` payload carries the child session_id;
  extract it in `post_tool_use` and write the row at end-of-spawn
  (best-effort).
- A small SessionEnd/Stop hook updates `ended_at` for any rows whose
  child_session_id has since stopped (best-effort, batched).
- `ll-session recent --kind subagent_run` returns rows; FTS matches
  `child_session_id` / `agent_type`.
- Future `ll-ctx-stats` per-agent block can roll up
  "subagents spawned by this session" alongside the executor tool-count.

## Proposed Solution

### Schema migration

```sql
CREATE TABLE IF NOT EXISTS subagent_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    parent_session_id TEXT,
    child_session_id TEXT,
    agent_type TEXT,              -- "codebase-locator" | "Explore" | "loop-specialist" | ...
    started_at TEXT,
    ended_at TEXT,                -- NULL while running
    status TEXT,                  -- "running" | "completed" | "failed" | "timeout"
    head_sha TEXT,
    branch TEXT,
    UNIQUE(child_session_id)      -- one row per child; INSERT OR IGNORE on replay
);
CREATE INDEX IF NOT EXISTS idx_subagent_parent ON subagent_runs(parent_session_id);
CREATE INDEX IF NOT EXISTS idx_subagent_child ON subagent_runs(child_session_id);
CREATE INDEX IF NOT EXISTS idx_subagent_agent ON subagent_runs(agent_type);
CREATE INDEX IF NOT EXISTS idx_subagent_status ON subagent_runs(status);
```

Bump `SCHEMA_VERSION`. Add `"subagent_run"` to `_VALID_KINDS` and
`"subagent_run": "subagent_runs"` to `_KIND_TABLE`.

### Producer wiring

- In `scripts/little_loops/hooks/post_tool_use.py`, when
  `tool_name == "Agent"` (or `"Task"` for older Claude Code versions),
  extract `child_session_id` from `tool_response` and call
  `record_subagent_run(db_path, parent_session_id=..., child_session_id=...,
  agent_type=..., started_at=..., status="running")`.
- The Stop hook (`scripts/little_loops/hooks/stop.py` or equivalent)
  updates `ended_at` for any rows where `child_session_id IN (this
  session)` and `ended_at IS NULL`. Best-effort, batched.
- Backfill: extend `_backfill_tool_events` (or add a sibling
  `_backfill_subagent_runs`) to walk the assistant block for
  `tool_name="Task"` and the user block for the matching child session
  log; populate rows from historical JSONL.

### Read API

- `history_reader.subagent_tree(session_id)` — returns the parent +
  immediate children + grandchild counts for a session.
- `history_reader.subagent_retries(agent_type, since=None)` — counts of
  same-agent re-spawns by a single parent (the "oscillation" signal).
- `history_reader.subagent_budget(session_id)` — total child-session
  duration rollup (the "burn budget" signal).

### CLI surface

- `ll-session recent --kind subagent_run`.
- `ll-session tree <session_id>` (optional follow-on) — renders the
  spawn tree as ASCII / JSON.

## Acceptance Criteria

- Schema migration lands; `subagent_runs` exists; `SCHEMA_VERSION` bumped.
- An `Agent` spawn writes one row with the correct `parent_session_id`,
  `child_session_id`, `agent_type`, and `started_at`.
- A child session's end updates the parent row's `ended_at` and `status`
  (best-effort).
- `ll-session recent --kind subagent_run` returns rows; FTS matches
  `agent_type`.
- Writes are best-effort: a missing/malformed response payload writes
  `child_session_id=NULL` (or skips), never raises.
- Tests cover: spawn, end, replay idempotency (`INSERT OR IGNORE` on
  `child_session_id`), missing-field graceful handling.

## Sources

- `autodev-bug2501-kill-analysis.md` (2026-07-07) — section "Extract the
  session-store trace" walks three session IDs by hand; the linkage
  would have surfaced the tree
- EPIC-2457 review (third-pass expansion, 2026-07-06)
- ENH-2497 — captures `agent_type` on tool_events; this issue captures
  the lifecycle + parent linkage that ENH-2497 deliberately deferred
- `scripts/little_loops/hooks/post_tool_use.py` — spawn producer site
- `scripts/little_loops/hooks/stop.py` (or equivalent) — end-of-session
  producer site

## Related Key Documentation

| Document | Why Relevant |
|----------|--------------|
| `docs/ARCHITECTURE.md` | Schema versions table |
| `docs/reference/API.md` | `session_store`, `history_reader` modules |
| `docs/reference/CLI.md` | New `ll-session --kind` value |

## Status

**Open** | Created: 2026-07-06 | Priority: P3

## Session Log
- `/ll:capture-issue` - 2026-07-06T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/`