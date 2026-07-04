---
id: ENH-2460
title: Add exit_code, success, and duration_ms columns to skill_events
type: ENH
priority: P3
status: done
discovered_date: 2026-07-02
captured_at: "2026-07-02T00:00:00Z"
discovered_by: capture-issue
parent: EPIC-2457
labels:
  - enhancement
  - history-db
  - skills
  - captured
---

# ENH-2460: Add exit_code, success, and duration_ms columns to skill_events

## Summary

`skill_events` (added by ENH-1833, schema v7) records `ts, session_id, skill_name, args` at skill dispatch time but carries no completion-side signal — whether the skill succeeded, what its exit code was, how long it took. `cli_events` (added by ENH-1834) *does* carry `exit_code` and `duration_ms` via its insert-then-update `cli_event_context()` mechanism. This is an inconsistency: skills look like they have no completion data, even though the host can provide it. Add `exit_code INTEGER, success INTEGER, duration_ms INTEGER` columns via a schema migration, and a `cli_event_context`-style `@contextmanager` (call it `skill_event_context()`) that skill hosts can wrap their handlers in to insert-then-update the same way. Per `thoughts/history-db-expand-wiring.md` §3 ranked recommendation #3: *"cheap, since the hook already fires at invocation; needs a completion-side write too."*

## Motivation

Without a completion signal, `skill_events` rows are half a story — agents can answer "which skills were invoked recently" but not "which of those succeeded." That asymmetry is especially awkward given that `cli_events` already records both. The skill/CLI symmetry is implicit in the project's analytics convention (per `analytics.capture.skills` and `analytics.capture.cli_commands` running side-by-side in `.ll/ll-config.json`).

Concretely:

- **Skill effectiveness metrics** — "What's the success rate of `/ll:refine-issue` over the last 30 days?" cannot be answered.
- **Failure clustering** — repeated failures of the same skill are not surfaced because there's no failure column to group on.
- **Loop health correlation** — `loop_events` records state transitions; pairing them with the skill that ran in each state requires the success signal to be inferable.

## Current Behavior

- `record_skill_event(db_path, session_id, skill_name, args)` inserts a row on dispatch; no update path exists.
- `cli_event_context(db_path, binary, args)` (per ENH-1834) inserts on enter, updates `exit_code` and `duration_ms` on exit. Skills have no parallel.
- `ll-session recent --kind skill` returns rows with no completion metadata.
- FTS5 search over `kind="skill"` rows surfaces no failure cluster (because no signal).

## Expected Behavior

- `skill_events` table gains `exit_code INTEGER, success INTEGER (0/1), duration_ms INTEGER` columns via a schema migration (additive; backfill-safe by virtue of `NULL` default).
- `skill_event_context(db_path, session_id, skill_name, args)` (analogous to `cli_event_context`) is exported from `session_store`; it inserts on enter, updates on exit with `exit_code`, `success`, `duration_ms`.
- Skill hosts (the `user_prompt_submit` hook at ENH-1833's recording site, and any future skill handler) wrap their bodies in `skill_event_context()`.
- `ll-session recent --kind skill` rows include exit_code/success/duration_ms when populated.
- Rollup: a new `ll-session skill-stats --since YYYY-MM-DD` subcommand or an `ll-logs stats --kind skill` extension shows per-skill success-rate over time.
- Existing pre-migration rows preserve `NULL` in the new columns — backward compatible.

## Proposed Solution

### Schema migration (append to `_MIGRATIONS` in `session_store.py`)

```sql
ALTER TABLE skill_events ADD COLUMN exit_code INTEGER;
ALTER TABLE skill_events ADD COLUMN success INTEGER;
ALTER TABLE skill_events ADD COLUMN duration_ms INTEGER;
```

These columns are nullable so pre-migration rows remain valid. Bump `SCHEMA_VERSION`.

### Producer wiring

- Add `skill_event_context(db_path, session_id, skill_name, args)` context manager to `session_store.py` mirroring `cli_event_context()` (line ~462):
  ```python
  @contextmanager
  def skill_event_context(db_path, session_id, skill_name, args, config=None):
      cursor = conn.execute("INSERT INTO skill_events(ts, session_id, skill_name, args) VALUES (...)")
      row_id = cursor.lastrowid
      start = time.time()
      success_val = 0
      exit_code_val = 0
      try:
          yield
          success_val = 1
      except BaseException:
          exit_code_val = 1
          raise
      finally:
          conn.execute(
              "UPDATE skill_events SET exit_code=?, success=?, duration_ms=? WHERE id=?",
              (exit_code_val, success_val, int((time.time() - start) * 1000), row_id),
          )
  ```
- Update `scripts/little_loops/hooks/user_prompt_submit.py` to wrap the existing `record_skill_event()` site in `skill_event_context()`. Today this hook writes at dispatch only; the upgrade is to wrap the skill body's downstream caller, but for `user_prompt_submit`-triggered skills the simplest signal is "the host CLI ran the skill to completion without aborting." A pragmatic cut: also log success on the next `loop_complete` / session exit event correlated by `session_id + skill_name` order.

### Read API

Extend `history_reader.recent_skill_events(...)` to return rows including exit_code, success, duration_ms when present. Optional: a `summarize_skills(since: datetime)` helper that returns per-skill `(invocations, successes, success_rate, p50_duration_ms, p95_duration_ms)`.

### CLI surface

- `ll-session recent --kind skill` — columns now include exit_code/success/duration_ms.
- New `ll-logs stats --kind skill` extension or new `ll-session skill-stats [--since]` subcommand — surfaces top-failing skills.

## Acceptance Criteria

- Schema migration adds the three columns without dropping or altering existing data.
- Pre-migration `skill_events` rows continue to load; new columns are `NULL`.
- `skill_event_context()` exists as exported public API.
- A skill invocation recorded via `skill_event_context()` (success or raise path) results in a row with `exit_code`/`success`/`duration_ms` populated.
- A raise inside the `with` block results in `exit_code=1`, `success=0`.
- `ll-session recent --kind skill` includes the new columns in output.
- Tests cover: success path, raise path, pre-migration row NULL-compatibility.

## Implementation Steps

1. Add `ALTER TABLE` migration for the three columns; bump `SCHEMA_VERSION`.
2. Implement `skill_event_context()` in `session_store.py`; export in `__all__`.
3. Update `scripts/little_loops/hooks/user_prompt_submit.py` to wrap the existing skill-recording site in `skill_event_context()` (best-effort — failures during hook dispatch must not block the hook).
4. Extend `history_reader.recent_skill_events()` to expose the new columns.
5. Optional: implement `summarize_skills()` in `history_reader.py`.
6. CLI: ensure `--kind skill` path serializes new columns.
7. Tests: `TestSkillEventContext`, `TestSchemaV15` (or higher), `TestRecentSkillEventsWithCompletion`.
8. Docs: `docs/ARCHITECTURE.md` schema row; `docs/reference/API.md` for `skill_event_context`; `docs/reference/CLI.md` `--kind skill` columns.

## Sources

- `thoughts/history-db-expand-wiring.md` — recommendations §2 row 3 ("Skill/CLI success-failure"), §3 ranked recommendation #3
- `scripts/little_loops/session_store.py:cli_event_context()` — direct template (~line 462)
- `.issues/enhancements/P4-ENH-1833-track-ll-skill-invocations-as-discrete-db-events.md` — established `skill_events` write path
- `.issues/enhancements/P5-ENH-1834-record-ll-cli-invocations-in-history-db.md` — `cli_event_context()` reference (asymmetric cousin)

## Related Key Documentation

| Document | Why Relevant |
|----------|--------------|
| `docs/ARCHITECTURE.md` | Schema versions table; producer/consumer flow |
| `docs/reference/API.md` | `session_store` module reference |
| `docs/reference/CLI.md` | `ll-session recent --kind skill` columns |

## Status

**Done** | Created: 2026-07-02 | Completed: 2026-07-03 | Priority: P3

Implemented as schema v15: `ALTER TABLE skill_events ADD COLUMN exit_code/success/duration_ms`
plus `skill_event_context()` (yields a mutable `SkillEventCompletion` so hosts with a concrete
exit code can set it; best-effort per EPIC-1707). Wired into the completion-side skill host
`ll-action invoke` (`cli/action.py`). The `user_prompt_submit` hook intentionally stays
dispatch-only (`record_skill_event`, NULL completion columns): the hook returns before the
skill body runs, so wrapping it would fabricate ~0ms success rows. Read side:
`history_reader.recent_skill_events()` + `summarize_skills()`; CLI: `ll-session skill-stats
[--since]` and `recent --kind skill` (columns serialize automatically). Tests:
`TestSchemaV15SkillCompletionColumns`, `TestSkillEventContext` (test_session_store.py),
reader tests in test_history_reader.py, CLI tests in test_ll_session.py.

## Session Log
- `/ll:capture-issue` - 2026-07-02T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/`
