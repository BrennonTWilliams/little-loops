---
id: ENH-2495
title: Record session-lifecycle / handoff events into history.db
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
  - hooks
  - captured
---

# ENH-2495: Record session-lifecycle / handoff events into history.db

## Summary

Of all registered hooks, **only the `post-tool-use.sh` and `user-prompt-check.sh`
paths write to history.db** (tool/skill events, and corrections + `/ll:` skill
dispatches via `user_prompt_submit.py`). The session-lifecycle hooks — `context-monitor.sh`
(threshold tracking, `context_monitor.auto_handoff_threshold: 50`),
`context-handoff-sentinel.sh` (Stop hook, writes the
`.ll/ll-context-handoff-needed` sentinel), the stale-ref sweep
(`scripts/little_loops/hooks/sweep_stale_refs.py`), and PreCompact handoff —
produce **sentinel/state files and advisory feedback only; nothing is persisted
as an event.** So the DB
can't answer "how often does this project hit the context-handoff threshold?" or
"how many stale cross-issue refs get swept per session?" Add a
`session_lifecycle_events` table capturing these transitions
(`handoff_needed`, `compaction`, `stale_ref_sweep`, `session_end`) so context
pressure and session churn become queryable and correlatable with issue/loop
activity.

## Motivation

- **Context pressure is a first-order workflow signal, entirely unrecorded.** The
  auto-handoff threshold crossing is exactly the moment work fragments across
  sessions — precisely what `issue_sessions` / ENH-2462 exist to reconstruct, yet
  the trigger itself is never logged.
- **Sweep findings evaporate.** `sweep_stale_refs.py` computes a findings count
  (stale cross-issue status refs) and emits it as advisory hook feedback; it's
  never persisted, so "is stale-ref churn getting better or worse?" is
  unanswerable.
- **Compaction events are implicit.** Compaction writes `summary_nodes`, but the
  compaction *event* (trigger, when) has no row, so summary provenance can't be
  tied to a moment.

## Current Behavior

- `context-monitor.sh` (PostToolUse) tracks usage into a state file; no DB write.
- `context-handoff-sentinel.sh` (Stop) writes `.ll/ll-context-handoff-needed`;
  no DB write.
- `sweep_stale_refs.py` (SessionStart/session-end path) emits an advisory count;
  no DB write.
- PreCompact hooks run `precompact.sh` / `precompact-handoff.sh`; no lifecycle row.
- There is no `--kind session_lifecycle` in `ll-session`.

## Expected Behavior

- A `session_lifecycle_events` table records rows keyed by session with an
  `event` discriminator (`handoff_needed`, `compaction`, `stale_ref_sweep`,
  `session_end`) plus an event-specific `detail` (JSON), e.g. sweep findings
  count, threshold percent at handoff, compaction token budget.
- The relevant hooks call a new `record_session_lifecycle_event()` (best-effort,
  never blocking the hook) at their existing fire points.
- `ll-session recent --kind session_lifecycle` returns rows.

## Proposed Solution

### Schema migration

```sql
CREATE TABLE IF NOT EXISTS session_lifecycle_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    session_id TEXT,
    event TEXT NOT NULL,        -- handoff_needed | compaction | stale_ref_sweep | session_end
    detail TEXT,                -- JSON: {"threshold_pct":52} | {"findings":3} | ...
    head_sha TEXT,
    branch TEXT
);
CREATE INDEX IF NOT EXISTS idx_lifecycle_event ON session_lifecycle_events(event);
CREATE INDEX IF NOT EXISTS idx_lifecycle_session ON session_lifecycle_events(session_id);
```

Bump `SCHEMA_VERSION`. Add `"session_lifecycle"` to `_VALID_KINDS` and
`"session_lifecycle": "session_lifecycle_events"` to `_KIND_TABLE`.

### Producer wiring

- Add `record_session_lifecycle_event(db_path, *, ts, session_id, event,
  detail=None, head_sha=None, branch=None)` to `session_store.py`, best-effort
  guarded, FTS-indexing `event` (`kind="session_lifecycle"`).
- Wire via the host-agnostic Python hook handlers under
  `scripts/little_loops/hooks/` (not the bash adapters), consistent with how
  other hooks dispatch:
  - `context-handoff-sentinel` path → `event="handoff_needed"` with the threshold
    percent that tripped it, when it writes `.ll/ll-context-handoff-needed`.
  - `sweep_stale_refs.handle()` → `event="stale_ref_sweep"` with
    `detail={"findings": N}`.
  - PreCompact handler → `event="compaction"` with the token budget.
  - Session-end handler → `event="session_end"`.
- All writes best-effort per the EPIC-1707 contract — a hook must never fail
  because the DB is absent/locked.

### Read API

- `history_reader.recent_lifecycle_events(event=None, since=None, limit=50)`.
- `history_reader.handoff_frequency(since=None)` — count of `handoff_needed`.

### CLI surface

- `ll-session recent --kind session_lifecycle`.

## Acceptance Criteria

- Schema migration lands; `session_lifecycle_events` exists; `SCHEMA_VERSION`
  bumped.
- Crossing the auto-handoff threshold writes a `handoff_needed` row with the
  threshold percent in `detail`.
- A session-end stale-ref sweep writes a `stale_ref_sweep` row with the findings
  count.
- A compaction writes a `compaction` row.
- Every write is best-effort: with the DB absent/locked, each hook still
  completes its primary job (sentinel written, sweep advisory emitted) unchanged.
- `ll-session recent --kind session_lifecycle` returns rows.
- Tests cover: each event type, DB-absent graceful degradation, detail JSON
  round-trip.

## Implementation Steps

1. Schema migration for `session_lifecycle_events`; bump `SCHEMA_VERSION`.
2. Add `"session_lifecycle"` to `_VALID_KINDS` and `_KIND_TABLE`.
3. Implement `record_session_lifecycle_event()` in `session_store.py`; export.
4. Wire the handoff-sentinel, stale-ref-sweep, PreCompact, and session-end
   Python hook handlers to call it (best-effort).
5. `history_reader.recent_lifecycle_events()` + `handoff_frequency()`.
6. CLI: `ll-session recent --kind session_lifecycle`.
7. Tests: `TestRecordLifecycleEvent`, `TestLifecycleSchema`, per-hook wiring
   tests, graceful degradation.
8. Docs: `docs/ARCHITECTURE.md` schema row + hook-writes-to-DB note,
   `docs/reference/API.md`, `docs/reference/CLI.md`.

## Sources

- `thoughts/history-db-expand-wiring.md` — §2 (issue↔session linkage / lifecycle)
- EPIC-2457 review (2026-07-05) — item #4
- `hooks/hooks.json` — hook registrations (only `post-tool-use` and `user-prompt-check` write to DB; no lifecycle hook does)
- `hooks/scripts/context-handoff-sentinel.sh`, `hooks/scripts/context-monitor.sh`
- `scripts/little_loops/hooks/sweep_stale_refs.py` — sweep findings count
- `reference_loop_handoff_mechanics` (memory) — CONTEXT_HANDOFF marker semantics
- ENH-2462 — explicit `session_id` on issue_events (the linkage this complements)

## Related Key Documentation

| Document | Why Relevant |
|----------|--------------|
| `docs/ARCHITECTURE.md` | Schema versions; hook write-paths |
| `docs/reference/API.md` | `session_store`, hooks handlers |
| `docs/reference/CLI.md` | New `ll-session --kind` value |

## Status

**Open** | Created: 2026-07-05 | Priority: P3

## Session Log
- audit - 2026-07-06 - Corrected "only post-tool-use writes to history.db": the `user-prompt-check.sh` → `user_prompt_submit.py` path also writes (corrections + skill events). Core claim stands — no session-*lifecycle* hook writes to the DB. Fixed sweep_stale_refs path.
- `/ll:capture-issue` - 2026-07-05T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/`
