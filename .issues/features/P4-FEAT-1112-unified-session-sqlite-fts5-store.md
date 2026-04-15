---
id: FEAT-1112
type: FEAT
priority: P4
status: open
discovered_date: 2026-04-15
discovered_by: capture-issue
related: [FEAT-1113, ENH-1114]
---

# FEAT-1112: Unified Session Store (SQLite + FTS5)

## Summary

Replace the scattered JSON/markdown stores behind `analyze-loop`, `analyze-history`, and `analyze-workflows` with a single per-project SQLite + FTS5 database that indexes tool events, file modifications, git operations, issue transitions, and user corrections.

## Motivation

Today little-loops persists session/loop/history state in multiple disconnected places: FSM loop state JSON, issue frontmatter, session JSONLs under `~/.claude/projects/`, and ad-hoc files under `.ll/`. Each `/ll:analyze-*` skill re-parses these from scratch, which is slow, expensive on context, and makes cross-cutting queries ("which loops failed on issues touching file X?") impractical.

Context-mode (github.com/mksglu/context-mode) uses a per-project SQLite + FTS5 database with BM25 ranking and Reciprocal Rank Fusion to answer queries like this in milliseconds, and makes compaction-time reconstruction of working state feasible.

## Current Behavior

- Loop runs: JSON under `.ll/loops/` per-run
- Issue history: markdown frontmatter + `ll-history` scrapes completed/ dir
- Workflow patterns: one-shot extraction via `ll-messages` + `ll-workflows`
- Analysis skills each re-parse their source data every invocation
- No cross-index between loops, issues, messages, and git operations

## Expected Behavior

- New per-project SQLite DB at `.ll/session.db` (gitignored) with FTS5 tables for:
  - `tool_events` (tool name, args hash, result size, timestamp, session id)
  - `file_events` (path, op, session id, issue id, git sha)
  - `issue_events` (issue id, transition, discovered_by, timestamp)
  - `loop_events` (loop name, state, transition, rate-limit retries)
  - `user_corrections` (captured from feedback memory + explicit markers)
- Ingestion via a lightweight daemon or SessionStart/PostToolUse hook that writes events as they happen
- New `ll-session` CLI wraps queries (`ll-session search`, `ll-session recent --kind=loop`)
- `/ll:analyze-loop`, `/ll:analyze-history`, `/ll:analyze-workflows` refactored to query the DB instead of re-parsing source files
- Schema documented in `docs/reference/`; migrations via a version column

## Acceptance Criteria

- `.ll/session.db` created on first run; schema migration framework in place
- Backfill script populates from existing `.ll/loops/`, `.issues/completed/`, and session JSONLs
- At least two analyze-* skills migrated to query the DB
- `ll-session search --fts "<query>"` returns ranked results with file:line anchors
- `.gitignore` updated
- Unit tests for ingestion, migration, and query paths

## Risks / Notes

- Runtime selection: match context-mode's pattern — `bun:sqlite` on Bun, `node:sqlite` on Node ≥22.13, fallback to stdlib `sqlite3` in Python (we're Python-first, so this is simpler for us)
- Privacy: all local, no telemetry — consistent with ll defaults
- This is the larger bet in the context-mode cluster; consider `/ll:iterate-plan` before implementation

## References

- Inspiration: context-mode SQLite FTS5 session database
- Depends on / unblocks: FEAT-1113 (PreCompact auto-handoff), ENH-1114 (intent filtering)
