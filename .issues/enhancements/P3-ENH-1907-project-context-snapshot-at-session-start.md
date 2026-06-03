---
id: ENH-1907
type: ENH
priority: P3
status: open
discovered_date: 2026-06-03
captured_at: "2026-06-03T19:54:05Z"
discovered_by: capture-issue
parent: EPIC-1707
relates_to: [ENH-1752, ENH-1846, ENH-1847, FEAT-1263, ENH-1830]
labels:
  - captured
  - history-db
---

# ENH-1907: Project-Context Snapshot at Session Start

## Summary

Inject a small, project-level "recent state" digest into Claude's context at
session start, sourced from `.ll/history.db`. The digest answers *"what has been
happening in this project lately?"* — recently touched files (last ~7 days),
recently completed/closed issues, and recurring `user_corrections` themes — as
distinct from the per-session *personal handoff* of "what I was doing" that
FEAT-1263 already injects.

This is a new **consumer** under EPIC-1707 (history.db as Agent Context Layer):
the producer side and the read primitives already exist; the missing pieces are
a project-wide aggregation query and the `session_start` wiring.

## Current Behavior

`scripts/little_loops/hooks/session_start.py` (`handle()`) injects the merged
`ll-config.json` as `additionalContext` and kicks off a background
`backfill_incremental` (ENH-1830). It does **not** surface any project-state
summary. The only history-derived context an agent sees today is:

- **Personal handoff** (FEAT-1263, done): `ll-continue-prompt.md` → "what *I*
  was doing last session" (continuation of in-flight work).
- **Issue-scoped lookups** (ENH-1846/ENH-1847, done): `ll-history-context
  <ISSUE_ID>` renders corrections + FTS matches for *one issue the agent is
  already working on* — pulled on demand by `refine-issue` / `ready-issue` /
  `confidence-check`, not at session start.

Neither gives a fresh session a project-wide "here's the recent state" picture,
so `history.db`'s `file_events`, `issue_events`, and `user_corrections` tables go
unused for ambient session framing.

## Expected Behavior

On session start (for initialized projects with a non-empty `history.db`), Claude
receives a compact `<project_context>` block, e.g.:

```
<project_context>
## Recently touched (last 7 days)
- scripts/little_loops/host_runner.py (12 edits)
- scripts/little_loops/session_store.py (5 edits)
...
## Recently completed issues
- ENH-1847 — Wire ll-history-context into refine/ready/confidence (2d ago)
- BUG-1881 — post_tool_use python handler not wired (4d ago)
## Recurring corrections
- "don't add Co-Authored-By trailers" (seen 3x)
- "commands/*.md are commands, not docs" (seen 2x)
</project_context>
```

When the DB is missing, empty, or all rows are stale, the hook injects nothing
(no empty block, no error) and session start is unaffected.

## Motivation

EPIC-1707's goal is for ll components to read `history.db` so prior context
informs outputs "without the user having to manually surface that context." A
session-start project digest is the single highest-leverage *ambient* consumer:
it benefits **every** session (not just issue-scoped skills), it reuses the
already-built read API (ENH-1752), and it directly exercises the
`user_corrections` → fewer-repeated-corrections success metric the EPIC tracks.

## Proposed Solution

1. **Add a project-digest query to `history_reader.py`** — a new
   `project_digest(db_path, *, days=7, max_files=N, max_issues=N,
   max_corrections=N)` that aggregates across all paths/issues (the existing
   `recent_file_events` / `find_user_corrections` / `related_issue_events` are
   per-path / per-topic / per-issue and don't roll up). Returns a typed
   dataclass; returns an empty/sentinel result on missing/empty/stale DB, mirroring
   the degradation contract the other readers already follow.

2. **Render a bounded block** — a small formatter (in `history_reader.py` or a
   thin helper) that turns the digest into the `<project_context>` markdown,
   enforcing a **hard character cap** so the block can never bloat the
   every-session hot path.

3. **Wire into `session_start.py`** — behind an **opt-in config gate**, call the
   digest + formatter and emit the block via `additionalContext`
   (`hookSpecificOutput.additionalContext` envelope — see FEAT-1263's format
   correction note). All errors suppressed; never blocks startup. Note the
   ordering subtlety: `backfill_incremental` runs in a background daemon thread,
   so the digest reflects the *previous* session's already-persisted rows, not
   this session's backfill — acceptable, but document it.

4. **Config + schema** — add a gate flag (proposed:
   `history.session_digest.enabled`, default `false` while it bakes) plus the
   tunables (`days`, caps) to `config-schema.json`
   (`additionalProperties: false`, so the schema MUST be updated).

### Critical design constraints

EPIC-1707 names its **primary risk** as prompt bloat + stale context misleading
agents, and `session_start` is on the hot path of *every* session. Therefore:

- **Opt-in gate** (default off until validated).
- **Hard size cap** on the injected block (truncate with a "+N more" tail).
- **Recency/freshness window** (default 7 days; stale rows excluded).
- **Graceful degradation** on missing/empty/stale DB — inject nothing, never
  error, never block startup.

## Integration Map

### Files to Modify

- `scripts/little_loops/history_reader.py` — add `project_digest()` aggregation +
  bounded markdown formatter; reuse the `_connect_readonly` / `_stale_cutoff`
  helpers.
- `scripts/little_loops/hooks/session_start.py` — in `handle()`, after config
  composition, append the rendered block to the stdout/`additionalContext`
  payload behind the gate (best-effort, suppressed).
- `config-schema.json` — add `history.session_digest` object
  (`enabled` + tunables); schema is `additionalProperties: false`.

### Tests

- `scripts/tests/test_history_reader.py` — `project_digest` cases: populated DB,
  empty tables, stale-only rows (>window), and size-cap truncation.
- `scripts/tests/test_hooks_integration.py` — extend session-start coverage:
  gate off → no block; gate on + populated DB → `<project_context>` present and
  under the cap; gate on + missing/empty DB → no block, exit 0.

### Documentation

- `docs/ARCHITECTURE.md` — add the session-start digest to the history.db
  producer→consumer flow (coordinate with ENH-1753).
- `docs/reference/API.md` — document `project_digest`.
- `docs/reference/CONFIGURATION.md` — document `history.session_digest.*`.

## Implementation Steps

1. Implement `project_digest()` + formatter in `history_reader.py` with
   degradation + cap; unit-test in isolation.
2. Add the `history.session_digest` config block to `config-schema.json`.
3. Wire the gated call into `session_start.py::handle()`; suppress all errors.
4. Add session-start integration tests (gate on/off, populated/empty/stale).
5. Doc sweep (ARCHITECTURE / API / CONFIGURATION).

## Impact

- **Priority**: P3 — high-leverage ambient consumer, but not blocking; default-off
  gate means zero risk to existing sessions until explicitly enabled.
- **Effort**: Medium — one aggregation query + formatter + a guarded wiring point;
  read API and degradation pattern already exist.
- **Risk**: Medium — prompt bloat / stale-context on the every-session hot path is
  the explicit EPIC-1707 risk; mitigated by opt-in gate, hard cap, and freshness
  window.
- **Breaking Change**: No — additive, gated, degrades to no-op.

## Related Key Documentation

- EPIC-1707 — history.db as Agent Context Layer (parent)
- ENH-1752 — `history_reader.py` read API + graceful degradation (foundation)
- ENH-1846 / ENH-1847 — `ll-history-context` (issue-scoped sibling consumer)
- FEAT-1263 — SessionStart Context Injector (personal handoff; distinct concern)
- ENH-1830 — background backfill at session start (ordering interaction)

## Labels

`captured`, `history-db`

## Session Log
- `/ll:capture-issue` - 2026-06-03T19:54:05Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ada31840-370b-4650-bda9-261f3422cc4a.jsonl`

---

**Open** | Created: 2026-06-03 | Priority: P3
