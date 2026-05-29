---
id: FEAT-1712
title: LCM-style hierarchical summary DAG over session history
type: FEAT
priority: P3
status: open
captured_at: "2026-05-26T01:31:23Z"
discovered_date: "2026-05-26"
discovered_by: capture-issue
relates_to: [ENH-1710, ENH-1711]
parent: EPIC-1707
blocked_by: [ENH-1752]
---

# FEAT-1712: LCM-style hierarchical summary DAG over session history

## Summary

Implement a Lossless Context Management (LCM) layer over `history.db` that maintains a hierarchical DAG of LLM-generated summary nodes over the immutable session JSONL store, enabling month-scale project history navigation without context saturation.

## Motivation

Inspired by the LCM paper (Ehrlich & Blackman, 2026, arXiv:submit/7269166): the immutable session JSONL files already constitute a lossless store, but navigating them for open-ended queries ("what architectural decisions were made on the auth rewrite?") requires the agent to already know what to grep for. A hierarchical DAG of summaries provides multi-resolution access — high-level summaries for orientation, lossless drill-down for verification — without loading the full history into context.

ENH-1710 and ENH-1711 close the cheapest navigation gaps (session→JSONL path, issue→session linkage). This feature is the third and most significant layer: the compaction and retrieval subsystem that makes history queryable at any resolution.

### Why this beats a flat FTS index

- FTS (`search_index`) already exists but returns decontextualized fragments — it lacks the conversational structure (who said what, in response to what, what was decided afterward) needed for meaningful reconstruction.
- Summary nodes provide the multi-resolution map; lossless pointers beneath them allow targeted expansion into originals.
- Matches the LCM paper's result: performance advantage over raw Claude Code emerges above ~32K tokens per query, which is easily reached when spanning multiple sessions.

## Use Case

A user asks: "Show me all the architectural decisions made while implementing the FSM loop runner." The agent:
1. Traverses the summary DAG from the project root summary downward.
2. Identifies summary nodes tagged with relevant issues/loops.
3. Uses `ll_expand` to drill into specific sessions where needed.
4. Returns a structured reconstruction without loading raw JSONL into context.

## Implementation Steps

### Phase 1 — Schema (depends on ENH-1710)

Add two tables to `history.db` migrations:

```sql
CREATE TABLE summary_nodes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,          -- 'leaf' | 'condensed'
    content TEXT NOT NULL,       -- LLM-generated summary text
    tokens INTEGER,
    parent_id INTEGER REFERENCES summary_nodes(id),
    session_id TEXT,             -- for leaf nodes
    ts_start TEXT,
    ts_end TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE summary_spans (
    summary_id INTEGER REFERENCES summary_nodes(id),
    message_event_id INTEGER REFERENCES message_events(id),
    PRIMARY KEY (summary_id, message_event_id)
);
```

### Phase 2 — Compaction loop

Implement `compact_session(session_id)` in `session_store.py`:
- Groups `message_events` for the session into blocks by token budget (default: 4K tokens per leaf).
- For each block, calls a summarization prompt (level 1 / 2 / deterministic truncation per LCM Algorithm 3).
- Inserts a `leaf` summary node and populates `summary_spans`.
- If the session already has ≥ 2 leaf nodes, creates a `condensed` node summarizing them.

Trigger: called by `backfill()` for completed sessions (those in `sessions` table with `completed_at` set) that have no summary nodes yet.

### Phase 3 — Retrieval tools

- `ll_grep(pattern, summary_id?)` — regex search over `message_events` content, results grouped by covering summary node.
- `ll_expand(summary_id)` — returns the full `message_events` covered by a summary node.
- `ll_describe(id)` — metadata for a summary or file ID.
- Expose as `ll-session grep`, `ll-session expand`, `ll-session describe` subcommands.

### Phase 4 — Integration with ll-history

Update `ll-history` to navigate via summary DAG when answering cross-session questions, falling back to direct JSONL for sessions without summaries.

## API / Interface Changes

- New `summary_nodes` and `summary_spans` tables.
- New `compact_session()` public function in `session_store.py`.
- New `ll-session grep / expand / describe` subcommands.
- `ll-history` updated to use DAG traversal.

## Acceptance Criteria

- After `backfill()` on a project with ≥ 2 completed sessions, `summary_nodes` contains at least one `condensed` node.
- `ll-session grep "auth middleware"` returns results grouped by summary node with a lossless reference to the originating message.
- `ll-session expand <summary_id>` returns the original messages covered by that summary.
- Compaction is idempotent: running `backfill()` twice does not create duplicate summary nodes.

## Risks / Open Questions

- **Storage cost**: Summaries are small (text only); the underlying JSONL is never duplicated. Acceptable.
- **LLM compaction cost**: One compaction call per ~4K-token block. Reasonable for background backfill; should be opt-in or rate-limited for large histories.
- **SQLite vs. PostgreSQL**: LCM paper uses embedded PostgreSQL for referential integrity. SQLite with WAL mode and `PRAGMA foreign_keys = ON` should suffice for the project-local scale here.
- **Compaction quality**: Three-level escalation (LCM Algorithm 3) guards against divergent summaries. Deterministic truncation at level 3 guarantees convergence.

## Status

---

open

## Session Log
- `/ll:audit-issue-conflicts` - 2026-05-29T20:48:41 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/53b77908-ee0a-4a6c-bdad-0674c8f94335.jsonl`
- `/ll:capture-issue` - 2026-05-26T01:31:23Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5d0765b0-9906-45d9-a15b-8eadbab154a7.jsonl`
