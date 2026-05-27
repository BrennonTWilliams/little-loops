---
id: EPIC-1707
type: EPIC
priority: P2
status: open
discovered_date: 2026-05-26
captured_at: "2026-05-26T00:48:43Z"
discovered_by: capture-issue
labels:
  - epic
  - captured
relates_to: [ENH-1708, ENH-1710, ENH-1711, FEAT-1712, ENH-1752, ENH-1753]
---

# EPIC-1707: history.db as Agent Context Layer

## Summary

Turn `.ll/history.db` from a write-only telemetry sink into a queryable context layer that ll skills, commands, and agents read from to make better decisions. The producer side (6 event tables + FTS5 `search_index`, writer hooks, `SQLiteTransport`) is largely built; the consumer side has zero references across `skills/`, `commands/`, and `agents/`.

## Goal

When this epic is done, a meaningful subset of ll skills/agents/commands query `.ll/history.db` (via FTS5 or anchor lookups) as part of their normal operation, so that prior `user_corrections`, recently touched files, related issue events, and tool-use patterns inform their outputs — without the user having to manually surface that context.

## Motivation

Discovered by inspection during a discussion of whether `.ll/history.db` is under-utilized:

- Schema is rich: `tool_events`, `file_events`, `issue_events`, `loop_events`, `message_events`, `user_corrections`, and an FTS5 `search_index` over (`content`, `kind`, `ref`, `anchor`, `ts`).
- Producer infrastructure exists: `SQLiteTransport`, `EventBus`, `session_store.py`, writer hooks (`post_tool_use.py`, `session_start.py`).
- Consumer infrastructure is absent: `grep -rln "session_store\|history\.db\|search_index" skills/ commands/ agents/` returns **zero** matches.
- Existing readers are CLI-only and human-facing (`ll-session`, `ll-history`, `ll-ctx-stats`) — agents don't benefit.

Without a consumer surface, the DB is dead weight: writers cost overhead, the schema costs migrations, and the value proposition ("better agent decisions over time") never lands.

## Scope

### In scope

- A small, well-typed read API in `little_loops/session_store.py` (or a thin `history_reader.py`) for the common queries agents need: `find_user_corrections(topic)`, `recent_file_events(path)`, `search(query, kind=...)`, `related_issue_events(issue_id)`.
- Wiring read calls into a curated set of high-leverage skills (see child issues) — not every skill.
- A guard pattern for graceful degradation when `.ll/history.db` is missing, empty, or stale (so skills don't hard-fail in fresh checkouts).
- Documentation in `docs/ARCHITECTURE.md` describing the producer→consumer flow and the read API.

### Out of scope

- Schema changes to existing event tables (those are owned by ENH-1686 family).
- Wiring reads into every skill — over-broad rollout risks stale-context bugs and prompt bloat. Children pick specific high-leverage targets.
- Cross-project / global history aggregation — single-project scope only.
- A general-purpose "memory" system (separate effort).
- Dashboard / UI work.

## Children

- **ENH-1752** — Add `history_reader.py` read API with graceful degradation + CLI wrapper for skill invocation (foundational prerequisite for all consumer work).
- **ENH-1753** — Document the producer→consumer flow in `docs/ARCHITECTURE.md` and the read API surface in `docs/reference/API.md` (required by success metrics; depends on ENH-1752).
- **ENH-1708** — Wire `user_corrections` + FTS5 reads into `refine-issue` / `ready-issue` / `confidence-check` (initial narrow slice; depends on ENH-1752).
- **ENH-1710** — Map session IDs to JSONL file paths in history.db (producer-side navigation gap).
- **ENH-1711** — Add issue-to-session cross-reference queries to history.db (depends on ENH-1710).
- **FEAT-1712** — LCM-style hierarchical summary DAG over session history (depends on ENH-1710, ENH-1711).

## Integration Map

### Files to Modify

- `scripts/little_loops/session_store.py` — add read API methods, or
- `scripts/little_loops/history_reader.py` — new module exposing read-only queries

### Dependent Files (Callers/Importers)

- TBD per child — each child issue identifies its own consumer skill(s).

### Tests

- `scripts/tests/test_session_store.py` — extend with read-API coverage
- New: `scripts/tests/test_history_reader.py` (if module split)

### Documentation

- `docs/ARCHITECTURE.md` — add producer→consumer diagram and read-path section
- `docs/reference/API.md` — document the read API

## Impact

- **Priority**: P2 — High-leverage but not blocking; once the writer side stabilizes (ENH-1691 lands), the consumer side becomes the next bottleneck for value.
- **Effort**: Large — small per-child slice, but cumulative wiring across multiple skills + read API design + degradation behavior.
- **Risk**: Medium — stale/wrong history actively misleads agents; we need a clear staleness/fallback story. Prompt bloat is a real cost if reads are added indiscriminately.
- **Breaking Change**: No — additive read paths; skills function normally if DB is empty.

## Success Metrics

- At least 3 skills query `.ll/history.db` as part of normal operation.
- Read API has graceful-degradation tests covering missing DB, empty tables, and stale (>30d) rows.
- `docs/ARCHITECTURE.md` documents the producer→consumer flow.
- A measurable reduction in repeated user_corrections on the same topic (qualitative — capture via `ll-history` before/after).

## Dependencies / Sequencing

- **Soft blocker**: ENH-1691 (wire issue lifecycle EventBus → SQLiteTransport) should land first so the producer side is reliable; otherwise consumers read empty tables.
- Each child issue can land independently once the read API is in place.

## Labels

`epic`, `captured`

## Session Log

- `/ll:capture-issue` - 2026-05-26T00:48:43Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a2c695cf-9995-4a8f-9ec7-81cdca0d77e5.jsonl`

---

**Open** | Created: 2026-05-26 | Priority: P2
