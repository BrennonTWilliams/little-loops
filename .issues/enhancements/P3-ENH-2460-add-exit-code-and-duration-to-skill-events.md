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

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis. Each is annotated with its landing status — already-wired items document the actual implementation touchpoints the original Implementation Steps did not enumerate; "flagged" items are follow-ups surfaced by the wiring pass._

9. Wire `cmd_invoke` in `scripts/little_loops/cli/action.py:14, 81-84, 113, 148` — wrap skill body in `skill_event_context()` and set `completion.exit_code = exit_code` on both `stream-json` and `blocking-json` branches ✅ (done)
10. Update `scripts/little_loops/observability/schema.py:479-483` `SkillEventVariant` docstring to mention both `record_skill_event` and `skill_event_context` writers ✅ (done)
11. Update `scripts/little_loops/history_reader.py` module docstring (lines 19, 26-27) to add `SkillEvent`, `recent_skill_events`, `summarize_skills` entries ✅ (done)
12. Update `scripts/little_loops/cli/session.py:11` module docstring to add `skill-stats` entry ✅ (done)
13. Document in `docs/guides/HISTORY_SESSION_GUIDE.md:43, 69, 92, 349-353` (quick-reference row, schema history v15 row, table description, "Skill success signal" cookbook section) ✅ (done)
14. **CHANGELOG entry** — flagged as release-prep owner action (per `feedback_changelog_no_unreleased.md`, promote to concrete `[X.Y.Z] - DATE` section during release prep, never `[Unreleased]`)
15. **Decision fragment** — flagged as owner action: record the `user_prompt_submit` stays dispatch-only + `ll-action invoke` is the wrap point + `SkillEventCompletion` mutable-yield design choices in `.ll/decisions.d/<uuid>.json` (currently captured only in this issue's Status section)
16. **End-to-end integration test** — flagged as follow-up: add `test_invoke_records_exit_code_in_skill_events` to `scripts/tests/test_action.py::TestMainAction` mirroring `test_session_store.py:3972` (success path) + 3986 (raise path); conftest's autouse `_isolate_history_db` already routes writes to `tmp_path/.ll/history.db`
17. **Verify-style gate** — flagged as follow-up: add a `PRAGMA table_info(skill_events)`-based gate to `scripts/tests/test_verify_kinds.py` (model on `TestRun::test_flags_unregistered_table` at line 25) asserting `exit_code`/`success`/`duration_ms` are always present regardless of bootstrap path

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

## Integration Map

_Wiring pass added by `/ll:wire-issue`:_

### Files to Modify (verified during implementation)

- `scripts/little_loops/session_store.py` — v15 migration (lines 581-583); `skill_event_context()` + `SkillEventCompletion` mutable-yield (lines 1095, 1109); `__all__` export (lines 88-89); `SCHEMA_VERSION` bump
- `scripts/little_loops/history_reader.py` — `SkillEvent` dataclass; `recent_skill_events()` (line 466); `summarize_skills()` (line 497); module-docstring entry
- `scripts/little_loops/cli/action.py` — wrap `cmd_invoke` body in `skill_event_context()`; set `completion.exit_code` on both branches (lines 14, 81-84, 113, 148)
- `scripts/little_loops/cli/session.py` — `skill-stats` argparse subparser + handler dispatch (lines 11, 284-294, 615-632); `recent` command auto-renders new columns via `SELECT *`
- `scripts/little_loops/observability/schema.py` — `SkillEventVariant` docstring updated to mention both `record_skill_event` and `skill_event_context` writers (lines 479-483)

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_

- `scripts/little_loops/cli/action.py:14` — imports `skill_event_context` from `session_store`; the sole production wrap site
- `scripts/little_loops/cli/session.py:616` — lazy-imports `summarize_skills` inside the `skill-stats` handler dispatch
- `scripts/little_loops/hooks/user_prompt_submit.py:29, 92` — calls `record_skill_event` (dispatch-only path, intentionally NOT migrated per design — wrapping would fabricate ~0ms success rows because the hook returns before the skill body runs)
- `scripts/little_loops/cli/logs.py:779` — reads `skill_events` via `SELECT ts, session_id, skill_name FROM skill_events` (no change needed; `ll-logs stats --kind skill` does not consume the new columns)
- `scripts/little_loops/cli/ctx_stats.py:20` — drives skill-health section via `_aggregate_skill_stats` import (no change needed)
- `scripts/little_loops/issue_history/evolution.py:235` — reads `skill_events` directly for the `_MIN_BYPASS_KEYWORDS` check (no change needed)

### Registration / Manifest Files

_Wiring pass added by `/ll:wire-issue`:_

- `scripts/little_loops/session_store.py` `__all__` (lines 88-89) — adds `"skill_event_context"` and `"SkillEventCompletion"`
- `scripts/little_loops/cli/session.py` `skill_stats_parser` (lines 284-294) — registers the `skill-stats` subcommand with `--since` and `--json` flags
- `scripts/little_loops/__init__.py` — NOT modified (matches existing pattern: `record_issue_snapshot` is also only surfaced via `little_loops.session_store.*`)
- `scripts/little_loops/hooks/__init__.py` — NOT modified (CLI subcommands dispatch from `scripts/little_loops/cli/`, not the hook intent layer)
- `.claude-plugin/plugin.json` — NOT modified (CLI subcommands are not plugin commands)

### Documentation

_Wiring pass added by `/ll:wire-issue`:_

- `docs/ARCHITECTURE.md:673` — schema versions table v15 row
- `docs/ARCHITECTURE.md:726` — producer diagram mentions `record_skill_event()` (intentionally unchanged for dispatch-only path)
- `docs/reference/API.md:54, 6845-6846, 7026-7049, 7284-7285, 7331-7344` — `skill_event_context`, `recent_skill_events`, `summarize_skills`, `SkillEvent`, v15 ALTERs
- `docs/reference/CLI.md:2386, 2435, 2512` — `ll-session` subcommand table, `--kind skill` columns, `skill-stats` example
- `docs/guides/HISTORY_SESSION_GUIDE.md:43, 69, 92, 349-353` — quick-reference row, schema history v15 row, table description, "Skill success signal" cookbook section

### Tests

_Wiring pass added by `/ll:wire-issue`:_

- `scripts/tests/test_session_store.py:3914-3966` — `TestSchemaV15SkillCompletionColumns` (PRAGMA verification, v14→v15 migration via `_bootstrap_schema_at(db, 14)` helper at line 3891, NULL-on-dispatch contract)
- `scripts/tests/test_session_store.py:3969-4034` — `TestSkillEventContext` (success/raise/host-exit-code/args-truncate/FTS/best-effort paths)
- `scripts/tests/test_history_reader.py:1398-1410` — `test_recent_skill_events_includes_completion_columns`
- `scripts/tests/test_history_reader.py:1415-1436` — `test_summarize_skills_success_rate`
- `scripts/tests/test_history_reader.py:1530-1545` — `test_readers_return_empty_on_missing_db` (covers both `recent_skill_events` and `summarize_skills`)
- `scripts/tests/test_ll_session.py:109-112` — `test_skill_stats_subcommand_parses`
- `scripts/tests/test_ll_session.py:1041-1067` — `TestSkillStatsEndToEnd` (text + JSON output)
- `scripts/tests/test_hook_user_prompt_submit.py:229-275` — pins the dispatch-only contract (intentional design boundary)
- `scripts/tests/test_evolution_triggers.py:327` — fixture row insertion (no schema change needed)

### Configuration

_Wiring pass added by `/ll:wire-issue`:_

- `scripts/little_loops/config-schema.json` — no new knobs (existing `analytics.capture.skills` glob patterns at lines 1621-1625 are the upstream gate, unchanged)
- `.ll/ll-config.json` — no change (analytics.capture.skills: ["*"] is upstream gate)
- `scripts/little_loops/session_store.py:1114` — `config` parameter on `skill_event_context()` is a forward-compatibility stub for ENH-1835, accepted but not yet used

### Outstanding Gaps (Flagged for Owner Action)

_Wiring pass added by `/ll:wire-issue`:_

- **`CHANGELOG.md`** — no ENH-2460 entry yet. Prior schema-migration cycles (ENH-1833, ENH-1848, ENH-2151, ENH-2458, ENH-2459) all landed entries. Per project convention (`feedback_changelog_no_unreleased.md`), promote to a concrete `[X.Y.Z] - DATE` section during release prep, not `[Unreleased]`.
- **`.ll/decisions.d/`** — no ENH-2460 decision fragment. The three design choices captured in this issue's Status section (`user_prompt_submit` stays dispatch-only; `ll-action invoke` is the wrap point; `SkillEventCompletion` mutable yield) live only in the issue body, not the structured decisions log.
- **`scripts/tests/test_action.py::TestMainAction`** — no integration test asserting that `ll-action invoke` actually populates `exit_code`/`success`/`duration_ms` end-to-end. Mirror `test_session_store.py:3972` (success path) + 3986 (raise path); conftest's autouse `_isolate_history_db` already routes writes to `tmp_path/.ll/history.db`.
- **`scripts/tests/test_verify_kinds.py`** — no gate-style test asserting `skill_events` carries the new columns regardless of bootstrap path. A verify-style check modeled on `TestRun::test_flags_unregistered_table` (line 25) would enforce schema column presence.

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
- `/ll:wire-issue` - 2026-07-16T22:42:30 - `d1b2ea44-51af-41c6-8062-952a8b4f56b7.jsonl`
- `/ll:capture-issue` - 2026-07-02T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/`
