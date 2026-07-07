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

## Integration Map

_Added by `/ll:refine-issue` — based on codebase analysis:_

### Files to Modify

| File | Anchor | Change |
|------|--------|--------|
| `scripts/little_loops/session_store.py` | `_MIGRATIONS` list (lines ~208–545), `SCHEMA_VERSION = 18` (line 102), `_VALID_KINDS` (lines 104–118), `_KIND_TABLE` (lines 119–130), `__all__` (lines 60–87), top-of-module docstring (lines 1–38) | Append v19 migration; bump `SCHEMA_VERSION` to 19; add `"session_lifecycle"` to both maps; export `record_session_lifecycle_event` |
| `scripts/little_loops/session_store.py` | after `record_test_run_event` (line 1171) | Add `record_session_lifecycle_event()` best-effort helper modeled on `record_test_run_event` + `record_commit_event` (ENH-2458) |
| `scripts/little_loops/history_reader.py` | top-level docstring (lines 1–42); near `recent_commit_events` (around line 124) | Add `LifecycleEvent` dataclass + `recent_lifecycle_events()` + `handoff_frequency()` |
| `scripts/little_loops/cli/session.py` | `search_parser` choices list (line 92); `recent_parser` choices list (line 113) | Add `"session_lifecycle"` to BOTH `choices=[...]` lists; no further code change (`recent()` is generic over `_KIND_TABLE`) |
| `scripts/little_loops/hooks/sweep_stale_refs.py` | `handle()` lines 174, 194, 201 | Call `record_session_lifecycle_event(..., event="stale_ref_sweep", detail={"findings": N})` before each `return LLHookResult(exit_code=0)` |
| `scripts/little_loops/hooks/pre_compact.py` | `handle()` after `atomic_write_json(state_file, state)` (around line 165), before `return LLHookResult(exit_code=2, ...)` at line 169 | Call `record_session_lifecycle_event(..., event="compaction", detail={"budget_tokens": ..., "compacted_at": ...})` |
| `scripts/little_loops/hooks/pre_compact_handoff.py` | `handle()` after `atomic_write(prompt_path, content)` (line 152 onward) | Optionally emit second `compaction` row (idempotency via shared `compacted_at` timestamp) |
| `scripts/little_loops/hooks/__init__.py` | `_USAGE` banner (lines 50–54); `_dispatch_table()` (lines 74–99) | Update `_USAGE` string to mention `session_lifecycle` if a new intent is added; otherwise no change |
| `hooks/scripts/context-handoff-sentinel.sh` | after sentinel write at lines 76–81 | Shell out to `python -c 'from little_loops.session_store import record_session_lifecycle_event; ...'` with `event="handoff_needed"` and `detail={"threshold_pct": USAGE_PERCENT, "sentinel_threshold": SENTINEL_THRESHOLD, "token_count": TOKEN_COUNT, "context_limit": CONTEXT_LIMIT}` |
| `hooks/scripts/context-monitor.sh` | after crossing-branch at lines 354–362 (PostToolUse threshold-cross) | Optional: emit `event="handoff_needed"` from PostToolUse when threshold first crosses (currently no Python path — would need shell-out helper) |
| `scripts/tests/test_session_store.py` | after `TestRecordTestRunEvent` (line 3549) | Add `TestRecordLifecycleEvent` (roundtrip, event discriminator, detail JSON, FTS) and `TestSchemaV19` (uses `_bootstrap_schema_at(db, 18)` from line ~3075) |
| `scripts/tests/test_ll_session.py` | after the `test_recent_subcommand_commit_accepted` pair (lines 78–95) | Add `test_recent_subcommand_session_lifecycle_accepted` for both `recent` and `search` parsers |
| `scripts/tests/test_history_reader.py` | after `TestRecentCommitEvents` | Add `TestRecentLifecycleEvents` + `TestHandoffFrequency` |
| `scripts/tests/test_sweep_stale_refs.py` | add to existing sweep tests | Add `test_writes_lifecycle_row` verifying `stale_ref_sweep` event lands in DB |
| `scripts/tests/test_pre_compact.py` | add to existing tests | Add `test_writes_compaction_lifecycle_row` |
| `docs/ARCHITECTURE.md` | schema versions table + hook-write-paths note | Document v19 + `session_lifecycle_events` row |
| `docs/reference/API.md` | `session_store` and `history_reader` sections | Document new public functions |
| `docs/reference/CLI.md` | `ll-session recent --kind` table | Add `session_lifecycle` to the kind list |

### Dependent Files (Callers/Importers)

- `scripts/little_loops/hooks/user_prompt_submit.py:83` — pattern for `with contextlib.suppress(Exception):` call-site wrapping (closest precedent for the new hook call sites)
- `scripts/little_loops/hooks/post_tool_use.py:158` — second precedent for call-site suppress wrap
- `scripts/little_loops/hooks/session_start.py:122` — `ensure_db(resolve_history_db(...))` bootstrap precedent
- `scripts/little_loops/cli/backfill_worker.py` — backfill substrate may need updating if `session_lifecycle` is added to `_EXPORT_TABLE_MAP` (lines ~2791–2802) for `export` support

### Similar Patterns

- `scripts/little_loops/session_store.py:record_test_run_event()` (line 1171) — closest structural twin: many optional scalar fields + one JSON-serialized column (`failing_names_json` ↔ `detail`)
- `scripts/little_loops/session_store.py:record_commit_event()` (line 1041) — newer shape with `INSERT OR IGNORE` idempotency + returns `bool`
- `scripts/little_loops/session_store.py:skill_event_context()` (lines 925–1000) — internal `try/except sqlite3.Error: logger.warning(...)` graceful-degradation precedent (the modern post-EPIC-1707 pattern, tighter than caller-side suppress)

### Tests

- `scripts/tests/test_session_store.py` — `TestRecordLifecycleEvent`, `TestSchemaV19` (mirroring `TestSchemaV15SkillCompletionColumns`)
- `scripts/tests/test_ll_session.py` — `test_recent_subcommand_session_lifecycle_accepted`
- `scripts/tests/test_history_reader.py` — `TestRecentLifecycleEvents`, `TestHandoffFrequency`
- `scripts/tests/test_sweep_stale_refs.py` — `test_writes_lifecycle_row` (graceful-degradation: pass a directory as `db_path`)
- `scripts/tests/test_pre_compact.py` — `test_writes_compaction_lifecycle_row`

### Documentation

- `docs/ARCHITECTURE.md` — schema row for `session_lifecycle_events`
- `docs/reference/API.md` — `session_store.record_session_lifecycle_event()`, `history_reader.recent_lifecycle_events()`, `history_reader.handoff_frequency()`
- `docs/reference/CLI.md` — `ll-session recent --kind session_lifecycle`
- `docs/guides/HISTORY_SESSION_GUIDE.md` — user-facing walkthrough (if present)

### Configuration

- `LL_HISTORY_DB` env-var override (already honored by `resolve_history_db()` at line 94) — no new config needed for the recorder itself
- `context_monitor.auto_handoff_threshold` (default **80**, not 50 — see "Threshold correction" in Codebase Research Findings below)
- `context_monitor.sentinel_threshold` (default **50** — this is the sentinel threshold, the one that triggers `.ll/ll-context-handoff-needed`)

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Threshold correction**: The Summary/Expected Behavior states `context_monitor.auto_handoff_threshold: 50` — that value is wrong. The actual default is **80** (see `context-monitor.sh:26`: `LL_HANDOFF_THRESHOLD:-ll_config_value context_monitor.auto_handoff_threshold 80`). The **50** in the issue is the `sentinel_threshold` (line 76 of `context-handoff-sentinel.sh`), which is intentionally lower so the resume turn has headroom. The implementer should pick the appropriate threshold based on which event source they're wiring (PostToolUse crossing → 80; Stop sentinel → 50) and include the relevant threshold in `detail`.
- **Three distinct best-effort patterns** exist in the codebase; the modern post-EPIC-1707 pattern is `try/except sqlite3.Error: logger.warning(...)` *inside* the recorder (see `skill_event_context` at lines 962–963). Older patterns put the suppression at the call site (`with contextlib.suppress(Exception):` in `user_prompt_submit.py:83`). Either works; the internal pattern is preferred because it guarantees the hook call site can't accidentally fail-open.
- **`_VALID_KINDS` is a `frozenset`** validated inside `recent()` at line 1278 (`if kind not in _VALID_KINDS: raise ValueError(...)`). Adding `"session_lifecycle"` to the set is the gate; the parallel `_KIND_TABLE` mapping is what `recent()` uses to compute `SELECT * FROM {table}` (line 1280).
- **Argparse `choices` lists are duplicated** — both `search_parser` and `recent_parser` in `scripts/little_loops/cli/session.py` carry a hard-coded list. Both must be updated; otherwise `ll-session recent --kind session_lifecycle` will reject the kind before reaching the runtime check.
- **Idempotency strategy**: Lifecycle events don't need natural uniqueness (two sweeps per session at the same UTC second is improbable), so plain `INSERT` is fine — but the `_apply_migrations` body MUST use `CREATE TABLE IF NOT EXISTS` so re-runs after a partial migration don't fail (per the v18 precedent at line 525).
- **`__all__` re-export** at `session_store.py:60-87` is the public-API contract. Adding `"record_session_lifecycle_event"` there is required for downstream imports; without it, `from little_loops.session_store import record_session_lifecycle_event` will fail in tests.
- **`_index()` FTS5 helper** at `session_store.py:705-718` is the only path to populate `search_index`; call it with `kind="session_lifecycle"`, `ref=session_id or ""`, `anchor=event`, `content=f"{event} {session_id or ''} {json.dumps(detail or {})}"[:512]` so `ll-session search --fts "<keyword>" --kind session_lifecycle` finds the rows.
- **Hook call sites are doubly safe**: `sweep_stale_refs.handle()` has an outer `except Exception: return LLHookResult(exit_code=0)` (line 202); `pre_compact.handle()` has the same pattern at lines 166–167. Even without the inner `contextlib.suppress`, a recorder exception would be swallowed by the outer catch. The inner wrap is still recommended for explicit intent.
- **`sweep_stale_refs` was re-homed to SessionStart** (per the file's docstring at lines 1–22, because the SessionEnd 1.5s ceiling isn't reliable for the sweep work). The handoff-sentinel remains on Stop. Don't confuse the two paths when wiring.

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

Append the v19 migration to `_MIGRATIONS` in `session_store.py` (one beyond current v18 for `test_run_events`, ENH-2459). Bump `SCHEMA_VERSION = 18` → `SCHEMA_VERSION = 19`. Add `"session_lifecycle"` to `_VALID_KINDS` and `"session_lifecycle": "session_lifecycle_events"` to `_KIND_TABLE`.

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
   - Append a v19 entry to `_MIGRATIONS` in `scripts/little_loops/session_store.py` (after the v18 entry at lines 521–544, the ENH-2459 precedent). Use `CREATE TABLE IF NOT EXISTS session_lifecycle_events (...)` and `CREATE INDEX IF NOT EXISTS idx_lifecycle_event` / `idx_lifecycle_session`.
   - Bump `SCHEMA_VERSION = 18` → `19` at line 102.
   - Update the module docstring (lines 1–38) to mention the new table.
2. Add `"session_lifecycle"` to `_VALID_KINDS` (lines 104–118) and `_KIND_TABLE` (lines 119–130).
3. Implement `record_session_lifecycle_event()` in `session_store.py`; export.
   - Mirror `record_test_run_event` (line 1171) for the keyword-only + JSON-column shape; mirror `skill_event_context` (lines 925–1000) for the internal `try/except sqlite3.Error: logger.warning(...)` graceful-degradation contract.
   - Add to `__all__` at lines 60–87 for public re-export.
   - Use `_now()` (line 548) as `ts` fallback, `connect()` (line 693) for the connection, and `_index(...)` (line 705) with `kind="session_lifecycle"`, `ref=session_id or ""`, `anchor=event`.
4. Wire the handoff-sentinel, stale-ref-sweep, PreCompact, and session-end
   Python hook handlers to call it (best-effort).
   - `sweep_stale_refs.handle()` — add three `with contextlib.suppress(Exception): record_session_lifecycle_event(...)` calls before each return point (lines 174, 194, 201) with `event="stale_ref_sweep", detail={"findings": N}`.
   - `pre_compact.handle()` — add one call after `atomic_write_json(state_file, state)` (line 165) and before `return LLHookResult(exit_code=2, ...)` at line 169; `event="compaction"`, `detail={"budget_tokens": ..., "compacted_at": ...}`.
   - `pre_compact_handoff.handle()` — optional second call after `atomic_write(prompt_path, content)` (line 152 onward); idempotency via shared `compacted_at`.
   - `context-handoff-sentinel.sh` — bash shell-out after the sentinel write at lines 76–81, since this hook has no Python entry point. Enclose in `|| true` to preserve the "never fails" contract.
5. `history_reader.recent_lifecycle_events()` + `handoff_frequency()`.
   - Add `LifecycleEvent` dataclass near `CommitEvent` (line 124); add the two functions near `recent_commit_events`; follow the `_connect_readonly` + `sqlite3.Error → return []` pattern (lines 235–249).
6. CLI: `ll-session recent --kind session_lifecycle`.
   - Update `search_parser` choices list (line 92) AND `recent_parser` choices list (line 113) — both carry hard-coded duplicates.
   - No further code change: `recent()` is generic over `_KIND_TABLE` (line 1280).
7. Tests: `TestRecordLifecycleEvent`, `TestLifecycleSchema`, per-hook wiring
   tests, graceful degradation.
   - `TestRecordLifecycleEvent` in `test_session_store.py` (after `TestRecordTestRunEvent` at line 3549) — roundtrip, event discriminator, detail JSON round-trip, FTS search, multiple-events-distinct.
   - `TestSchemaV19` in `test_session_store.py` — `test_schema_version_is_nineteen`, `test_lifecycle_events_table_exists`, `test_v18_db_upgrades_to_v19` (use `_bootstrap_schema_at(db, 18)` from line ~3075).
   - `TestRecentLifecycleEvents` and `TestHandoffFrequency` in `test_history_reader.py`.
   - `test_recent_subcommand_session_lifecycle_accepted` in `test_ll_session.py` (mirror the `commit` pair at lines 78–95).
   - `test_writes_lifecycle_row` in `test_sweep_stale_refs.py` and `test_writes_compaction_lifecycle_row` in `test_pre_compact.py`.
   - Graceful-degradation: pass `tmp_path` itself (a directory) as `db_path`; sqlite raises `OperationalError`; the hook must still complete its primary job.
8. Docs: `docs/ARCHITECTURE.md` schema row + hook-writes-to-DB note,
   `docs/reference/API.md`, `docs/reference/CLI.md`.
   - `docs/ARCHITECTURE.md` — schema versions table (add v19) + hook-write-paths note listing `session_lifecycle` alongside the existing `tool` / `file` / `correction` / `skill` writes.
   - `docs/reference/API.md` — add `record_session_lifecycle_event`, `recent_lifecycle_events`, `handoff_frequency` to the `session_store` and `history_reader` sections.
   - `docs/reference/CLI.md` — add `session_lifecycle` to the `ll-session recent --kind` choices table.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- The **migration step alone** spans three coordinated edits to `session_store.py`: `_MIGRATIONS`, `SCHEMA_VERSION`, and the module docstring — implementers commonly miss the docstring update.
- The **CLI step** is purely additive to two `choices=[...]` lists — no new dispatch branch in `main_session()` is needed because `recent()` already routes through `_KIND_TABLE`.
- The **bash handoff-sentinel path** has no Python handler today. Two implementation choices: (a) shell out to `python3 -c '...'` (minimal diff, no new entry-point); (b) port `context-handoff-sentinel.sh` to Python and route through the dispatcher. The first matches the issue's "best-effort, never blocking" requirement without enlarging the hook surface.
- The **`session_end` row** is currently unspecified in the issue — consider whether the SessionEnd/SessionStart fallback in `sweep_stale_refs.handle()` should always emit a `session_end` row (even with zero findings) to make session-churn queryable. Defer to implementer.
- **Idempotency**: lifecycle events don't need a UNIQUE key — two sweeps per session at the same UTC second are improbable — so plain `INSERT` (per `record_correction` / `record_skill_event`) is acceptable.

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
- `/ll:refine-issue` - 2026-07-07T00:57:52 - `f072a647-96ed-4b8d-bdc1-936243abf1c4.jsonl`
- audit - 2026-07-06 - Corrected "only post-tool-use writes to history.db": the `user-prompt-check.sh` → `user_prompt_submit.py` path also writes (corrections + skill events). Core claim stands — no session-*lifecycle* hook writes to the DB. Fixed sweep_stale_refs path.
- `/ll:capture-issue` - 2026-07-05T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/`
