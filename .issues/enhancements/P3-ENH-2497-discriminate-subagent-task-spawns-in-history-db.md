---
id: ENH-2497
title: Discriminate sub-agent / Task spawns in history.db
type: ENH
priority: P3
status: open
discovered_date: 2026-07-05
captured_at: "2026-07-05T00:00:00Z"
discovered_by: capture-issue
parent: EPIC-2457
labels:
  - enhancement
  - history-db
  - agents
  - captured
---

# ENH-2497: Discriminate sub-agent / Task spawns in history.db

## Summary

Sub-agent spawns (the `Task` tool dispatching `codebase-locator`,
`loop-specialist`, `Explore`, etc.) land in the DB as **generic `tool_events`
rows** with `tool_name="Task"` and no `agent_type` — so "which subagents actually
get used, and how often?" can't be answered without parsing the opaque `args_hash`.
That's a real blind spot for the same skill-health story `ll-logs dead-skills` and
`ll-ctx-stats` already serve for skills. Add an `agent_type` discriminator for
Task-tool events (a nullable column on `tool_events`, or a dedicated
`agent_spawn` kind) captured at `post_tool_use` time, so subagent usage is
first-class and joinable.

## Motivation

- **Subagent usage is invisible.** The plugin ships 9 agents
  (`agents/*.md`); nothing tells you which are dead weight vs. load-bearing.
- **Symmetry with the skill-health tooling.** ENH-2460 gave skills exit_code /
  duration; `dead-skills` / `ctx-stats` surface skill usage. Agents deserve the
  same, and the hook already fires on every `Task` call.
- **Cheap, additive, hook-side.** The `post_tool_use` handler already sees the
  `Task` tool invocation and its input (which carries `subagent_type`); it just
  isn't extracted.

## Current Behavior

- A `Task` spawn is recorded by `post_tool_use` as a `tool_events` row with
  `tool_name="Task"`, `args_hash`, byte accounting — no `agent_type`.
- There is no way to `GROUP BY agent_type` or to FTS-search by agent.
- `ll-ctx-stats` / `ll-logs dead-skills` cover skills, not agents.

## Expected Behavior

- Task-tool events carry the dispatched `agent_type` (e.g. `codebase-locator`,
  `Explore`, `loop-specialist`).
- `ll-session recent --kind agent_spawn` (or a filter on `tool_events`) returns
  per-agent rows; agent usage is groupable.
- `ll-ctx-stats` (or a small new surface) can report per-agent invocation counts.

## Proposed Solution

Two viable shapes; **prefer (A)** for minimal schema churn.

### (A) Nullable `agent_type` column on `tool_events`

```sql
ALTER TABLE tool_events ADD COLUMN agent_type TEXT;  -- NULL for non-Task tools
CREATE INDEX IF NOT EXISTS idx_tool_events_agent ON tool_events(agent_type);
```

- Populate `agent_type` in the `post_tool_use` handler when
  `tool_name == "Task"`, reading `subagent_type` from the tool input.
- FTS-index the agent name (`kind="tool"`, anchor=agent_type) so
  `ll-session search --fts "loop-specialist"` surfaces spawns.

### (B) Dedicated `agent_spawn` kind (if richer per-spawn fields are wanted)

A separate row with `agent_type`, `prompt_preview`, `result_size`, `duration_ms`.
Heavier; only worth it if we want per-spawn outcome beyond what `tool_events`
already accounts. Start with (A); (B) can follow if needed.

For (A): bump `SCHEMA_VERSION` for the additive column (existing rows get
`NULL`). No new `_VALID_KINDS`/`_KIND_TABLE` entry required (reuses `"tool"`); add
`"agent_spawn"` only if pursuing (B).

### Producer wiring

- In the `post_tool_use` Python handler (`scripts/little_loops/hooks/`), when the
  recorded tool is `Task`, extract `subagent_type` from the tool-input payload and
  pass it through to the `tool_events` insert as `agent_type`.
- Best-effort per the EPIC-1707 contract; a missing field just writes `NULL`.

### Read API

- `history_reader.agent_usage(since=None)` — counts per `agent_type`.
- Extend `recent_tool_events()` (if present) with an `agent_type` filter.

### CLI surface

- `ll-ctx-stats`: add a per-agent usage line (optional, follow-on).
- `ll-session search --fts "<agent>"` already works once indexed.

## Acceptance Criteria

- Additive `agent_type` column lands on `tool_events`; `SCHEMA_VERSION` bumped;
  existing rows read back with `agent_type=NULL` (no migration breakage).
- A `Task` spawn of `codebase-locator` records a `tool_events` row with
  `agent_type="codebase-locator"`.
- Non-Task tool events keep `agent_type=NULL`.
- `history_reader.agent_usage()` returns correct per-agent counts.
- `ll-session search --fts "loop-specialist"` surfaces the spawn.
- Writes are best-effort: a malformed/absent `subagent_type` writes `NULL`, never
  raises.
- Tests cover: Task spawn populates agent_type, non-Task stays NULL, usage
  aggregation, missing-field graceful handling.

## Implementation Steps

1. Additive migration: `agent_type` column + index on `tool_events`; bump
   `SCHEMA_VERSION`.
2. Extract `subagent_type` in the `post_tool_use` handler for `Task` tools and
   thread it into the `tool_events` insert.
3. FTS-index the agent name.
4. `history_reader.agent_usage()` + `recent_tool_events(agent_type=...)` filter.
5. Optional: `ll-ctx-stats` per-agent usage line.
6. Tests: `TestTaskSpawnAgentType`, `TestNonTaskNullAgent`,
   `TestAgentUsageAggregation`, graceful missing-field test.
7. Docs: `docs/ARCHITECTURE.md` schema note, `docs/reference/API.md`.

## Sources

- `thoughts/history-db-expand-wiring.md` — §2 (tool-event granularity)
- EPIC-2457 review (2026-07-05) — item #7
- `scripts/little_loops/hooks/post_tool_use.py` — tool_events write-point
- ENH-2460 — sibling success-signal work (skills); this is its agent analog
- `agents/*.md` — the agent catalog whose usage this makes observable
- `reference_dispatch_table_usage_banner` (memory) — hook intent list to update

## Related Key Documentation

| Document | Why Relevant |
|----------|--------------|
| `docs/ARCHITECTURE.md` | Schema versions table |
| `docs/reference/API.md` | `session_store`, `history_reader`, hooks |

## Status

**Open** | Created: 2026-07-05 | Priority: P3

## Session Log
- audit - 2026-07-06 - Corrected agent count: `agents/*.md` contains 9 agent definitions, not ~15.
- `/ll:capture-issue` - 2026-07-05T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/`
