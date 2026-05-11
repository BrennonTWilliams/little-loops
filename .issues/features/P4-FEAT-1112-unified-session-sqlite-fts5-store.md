---
id: FEAT-1112
type: FEAT
priority: P4
status: open
discovered_date: 2026-04-15
discovered_by: capture-issue

relates_to: ['FEAT-1113', 'ENH-1114']
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

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): `ll-logs` (FEAT-1002) is a downstream consumer that ships in Phase 1 reading JSONL directly from `~/.claude/projects/`. Once this store lands, a follow-up refactor will migrate `ll-logs` internals to query the SQLite database while preserving its CLI interface. Plan the schema to accommodate the fields ll-logs currently extracts from JSONL (see FEAT-1002 for field list).

## Verification Notes

**Verdict**: VALID — Verified 2026-04-26

- Frontmatter `blocked_by: [FEAT-918]` is accurate — FEAT-1002 reference already cleared ✓
- FEAT-918 (cross-process event streaming) is still open — block is real ✓
- No `.ll/session.db` exists — feature not implemented ✓
- No `ll-session` CLI entry point in `scripts/pyproject.toml` ✓

## Session Log
- `/ll:verify-issues` - 2026-05-03T15:21:16 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8fe967ae-751c-4941-ab43-61b0cce639c5.jsonl`
- `/ll:audit-issue-conflicts` - 2026-05-01T18:01:01 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4d834804-46cc-43b7-960e-ebc6a9a495da.jsonl`
- `/ll:audit-issue-conflicts` - 2026-04-26T19:43:56 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b0a12d96-c315-4bf8-b507-7ba3c926702a.jsonl`
- `/ll:verify-issues` - 2026-04-26T19:34:07 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/316256f6-01c2-468b-8efc-2db79aff6b29.jsonl`
- `/ll:audit-issue-conflicts` - 2026-04-26T17:22:36 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/83033e3d-e46b-42e3-9b93-f788f6f5fee1.jsonl`
- `/ll:verify-issues` - 2026-04-24T03:02:17 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1faa7404-23ae-4397-94a1-06150dae54dd.jsonl`
- `/ll:audit-issue-conflicts` - 2026-04-22T20:04:15 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/82d256a6-9a99-40f5-8866-377a208de262.jsonl`
- `/ll:audit-issue-conflicts` - 2026-04-19T01:16:14 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9c7ed14d-9621-459d-9f93-384968b2e6f6.jsonl`

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): Three scope clarifications from a 2026-05-01 cross-issue audit:

1. **Event capture is FEAT-1262's job, not this one's.** Drop "Ingestion via a lightweight daemon or SessionStart/PostToolUse hook" framing where it implies installing a parallel hook. This issue subscribes to FEAT-1262's event log via FEAT-918's Transport sink — no new PostToolUse hook is added by FEAT-1112.
2. **PreCompact summary reconstruction is FEAT-1264's MVP.** FEAT-1264 (JSONL/jq) is the MVP path for PreCompact handoff snapshots; FEAT-1112's SQLite-backed reconstruction is a future replacement that swaps in via the same stable snapshot-builder API. Don't ship parallel summary builders.
3. **SessionStart slot is shared.** FEAT-1112 owns SessionStart *ingestion* only; FEAT-1263 owns SessionStart *context injection*. `hooks/hooks.json` supports multiple SessionStart entries — the two are co-existing consumers, not competitors for the slot.

## Blocks

- FEAT-1156
- FEAT-1157
- FEAT-1158
- FEAT-1262
- ENH-1114
- FEAT-1160
