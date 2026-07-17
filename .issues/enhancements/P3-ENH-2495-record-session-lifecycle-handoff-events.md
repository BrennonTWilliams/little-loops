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

### Wiring Additions (added by `/ll:wire-issue`)

_Files and coupling surfaces identified by the wiring pass that are not on the Integration Map above. These must be touched alongside the primary implementation._

#### Additional Files to Modify

| File | Anchor | Change | Source |
|------|--------|--------|--------|
| `scripts/little_loops/__init__.py` | line 44 (`__all__` re-export block) | Re-export `record_session_lifecycle_event` for `from little_loops import *` parity with `record_issue_snapshot` | Agent 1 (caller tracer) |
| `scripts/tests/test_assistant_messages.py` | line 88 (`assert SCHEMA_VERSION == 20`) | Bump to 21 when v21 migration lands | Agent 1 + Agent 3 |
| `scripts/tests/test_hook_session_start.py` | lines 307, 332, 341 (`TestRebuildFlagOnlyWhenSchemaVersionAdvanced`, `TestFreshMigrationTriggersRebuild`) | Bump `SCHEMA_VERSION == 20` literals to 21 | Agent 1 + Agent 3 |
| `scripts/tests/test_session_store.py` | lines 1371–1372, 1817, 1932, 1984, 2080, 3658, 3699 | Multiple `assert SCHEMA_VERSION == 20` literals across `TestRecord*` classes — bump to 21 | Agent 3 (test gap finder) |
| `scripts/tests/test_hooks_integration.py` | `TestContextHandoffSentinel` (lines 2740–2905) | Add `test_writes_lifecycle_row_on_threshold_crossing` (asserts `session_lifecycle_events` row landed in DB after bash script runs) and `test_python_failure_does_not_flip_exit_code` (DB write failure → `returncode == 0` AND sentinel still written — verifies `\|\| true` semantics) | Agent 3 |
| `scripts/tests/test_sweep_stale_refs.py` | add to `TestSweepStaleRefsGracefulDegradation` (line 255) | Add `test_writes_lifecycle_row_silently_with_broken_db` — call `handle(_event(cwd=tmp_path))` after pointing `LL_HISTORY_DB` at the tmp directory; assert sweep primary job completes AND no `session_lifecycle_events` row is written (graceful drop) | Agent 3 |
| `scripts/tests/test_pre_compact.py` | add to existing precompact tests | Add `test_writes_compaction_lifecycle_row_silently_with_broken_db` — same shape as sweep; verify compaction primary job completes AND DB write fails silently | Agent 3 |
| `docs/guides/HISTORY_SESSION_GUIDE.md` | lines 51, 60–75 (schema versions table), 32–43 (task→command table), 80–100 ("What Gets Recorded" table), 170 (`--kind` enumeration) | Add v21 row; add `session_lifecycle_events` to "What Gets Recorded"; add `ll-session recent --kind session_lifecycle` row to task→command table; append `session_lifecycle` to brace-enumerated kind list | Agent 1 + Agent 2 |
| `docs/guides/BUILTIN_HOOKS_GUIDE.md` | line 59 ("PostToolUse records tool & file events"), line 94 (flow diagram), line 434 (`analytics.capture.file_events` config row) | Add `session_lifecycle` companion line to PostToolUse writers list; add `sweep_stale_refs`/`pre_compact`/`context-handoff-sentinel` producers to flow diagram; consider `analytics.capture.session_lifecycle_events` flag (precedent: `usage_events`) | Agent 1 |
| `docs/reference/CONFIGURATION.md` | lines 1162–1178 (`hooks.pre_compact.rubric.*` block) | Mention that compaction events from this hook flow into `session_lifecycle_events` (cross-reference ENH-2507 if present) | Agent 1 |
| `.claude/CLAUDE.md` | lines 141–142, 186, 196, 203, 218 (multiple `ll-session` prose references) | Add `session_lifecycle` to kind listings where `recent`/`search`/`compact` are documented; mirror the table updates in `HISTORY_SESSION_GUIDE.md` | Agent 1 |
| `docs/reference/API.md` | line 81 (history.db prose), lines 4102–4103 (`--kind` brace list — already drifted, no `snapshot`/`usage`), line 7275 ("Current schema version: 19" — already stale by 1), line 7279 (`SCHEMA_VERSION` import snippet), lines 6847–6848 (history_reader imports block), 7051–7077 (recent_commit_events/recent_test_runs sections), 7286–7287 + 7346–7389 (record_commit_event/record_test_run_event API reference sections) | Add `session_lifecycle` to prose enumeration (line 81); fix brace-list drift at 4102–4103; bump "Current schema version" to 21; add `LifecycleEvent`, `recent_lifecycle_events`, `handoff_frequency` to imports block; add API reference sections for the new functions | Agent 1 + Agent 2 |
| `docs/reference/CLI.md` | lines 2427 (`search --kind` choices list — ends at `test_run`), 2435 (`recent --kind` choices list — ends at `test_run`), 2501 (`export --tables` choices table), 2510–2512 (worked examples block) | Add `session_lifecycle` to `search` and `recent` `--kind` brace lists; add `session_lifecycle_event` to `export --tables` choices IF `_EXPORT_TABLE_MAP` extended; add `ll-session recent --kind session_lifecycle` example | Agent 1 + Agent 2 |
| `docs/ARCHITECTURE.md` | lines 670–678 (schema versions table ends at v20), lines 714–729 (mermaid sequence diagram `v1–v20`), lines 753–754 (Components table — only `post_tool_use` and `user_prompt_submit` listed as hook writers) | Add v21 row mirroring v17/v18/v19/v20 format; extend sequence diagram to show `sweep_stale_refs`/`pre_compact`/`context-handoff-sentinel` as DB writers; add Components table rows for the new producers | Agent 1 + Agent 2 |

#### Additional Dependent Files (Callers/Importers) — Awareness Only (no edit required)

- `scripts/little_loops/cli/verify_kinds.py:40` — iterates `_KIND_TABLE.values()` against `_MIGRATIONS` CREATE TABLEs; the ENH-2581 gate enforces that `session_lifecycle_events` is in `_KIND_TABLE` OR `_KINDLESS_TABLES`. No edit, but failure mode if forgotten: `ll-verify-kinds` exits 1.
- `scripts/little_loops/cli/session.py:228–230` — `export --tables` help text lists `session, issue_event, ...`; only edit if `_EXPORT_TABLE_MAP` is extended for parity with `commit_event`/`test_run_event`.
- `scripts/little_loops/hooks/types.py:44` — `LLHookEvent.session_id: str | None = None`; this is the data source for `session_id=event.session_id` on every new `record_session_lifecycle_event(...)` call (per the Integration Map's Stale Reference Audit item at line 262).
- `scripts/little_loops/cli/history.py:297,314`, `scripts/little_loops/cli/logs.py:1644`, `scripts/little_loops/cli/history_context.py:31,331`, `scripts/little_loops/loops/sft-corpus.yaml:67`, `scripts/tests/test_loops_sft_corpus.py:42,101` — transitive importers of `history_reader`; the new `recent_lifecycle_events`/`handoff_frequency` functions will be available to these automatically once added.
- `scripts/little_loops/pytest_history_plugin.py:126,130` — direct importer of `record_test_run_event` from `session_store`; serves as the import-shape precedent for `record_session_lifecycle_event` (no edit).
- `scripts/little_loops/__init__.py:44` — package-level `from little_loops.session_store import (..., record_issue_snapshot)` (overlaps with Files to Modify above).

#### Additional Codebase Research Findings

_Added by `/ll:wire-issue` — based on wiring research:_

- **`_EXPORT_DEFAULT_TABLES` ALSO needs the entry** — not just `_EXPORT_TABLE_MAP`. The Integration Map mentions `_EXPORT_TABLE_MAP` (per `cli/backfill_worker.py` coupling at line 104), but Agent 2 confirmed `_EXPORT_DEFAULT_TABLES` at `session_store.py:3318–3329` is a SEPARATE constant that gates which tables `ll-session export` writes without `--tables`. Without both entries, `ll-session export` silently skips `session_lifecycle_events` unless the user passes `--tables session_lifecycle_event` explicitly. ENH-2461 documented this two-map pattern at `.issues/enhancements/P3-ENH-2461-...md:378`.
- **Recorder should use `connect()` (not `ensure_db()` + raw INSERT)** — Agent 3 flagged that `record_skill_event` uses `connect()` which calls `ensure_db()` internally and swallows migration errors more aggressively. The new `record_session_lifecycle_event` should mirror `record_skill_event`'s shape (call `connect()`), NOT `cli_event_context`'s (call `ensure_db()` explicitly). This affects the graceful-degradation contract because `connect()`-based call sites never block the hook even on partial migration state.
- **`_EXPORT_TABLE_MAP` lives in `session_store.py:3304–3316`, NOT in `cli/backfill_worker.py`** — the Integration Map's "Dependent Files" note (`cli/backfill_worker.py` line 2791–2802) is incorrect. The actual map is in `session_store.py:3304`. `backfill_worker.py` is the consumer but doesn't define it.
- **Bash shell-out needs explicit `|| true` verification test** — the proposed bash shell-out pattern `python3 -c '...'` followed by `|| true` is necessary because the hook host (Claude Code `Stop` event) treats any non-zero exit as a stop-blocking error. The new test `test_python_failure_does_not_flip_exit_code` (Agent 3 finding) verifies this contract by triggering a DB write failure (e.g., `LL_HISTORY_DB=/some/dir/`) and asserting `returncode == 0` AND the sentinel file was still written.
- **`docs/reference/API.md:7275` is already drifted** — currently says "Current schema version: **19**" while live is 20. The implementer should bump to 21 (or the next open slot) AND fix the drift. Same for line 7279 (`SCHEMA_VERSION,        # 19` in the import snippet).
- **`docs/reference/API.md:4102–4103` brace-list is already drifted** — the `--kind {tool,file,issue,loop,correction,message,skill,cli,commit,test_run}` brace list omits `snapshot` and `usage` despite being valid kinds per `VALID_KINDS`. The new entry should NOT inherit this drift — update the brace list to the full `VALID_KINDS` (or link to it) so future additions don't require a doc re-touch.
- **`docs/reference/CLI.md:2427, 2435` brace lists are also drifted** — same observation as above; both lists end at `test_run`.
- **`test_assistant_messages.py:88` AND `test_hook_session_start.py:307,332,341` ALSO hardcode `SCHEMA_VERSION == 20`** — alongside `test_session_store.py`'s multiple literals. The implementer must grep for `SCHEMA_VERSION == ` across the whole `scripts/tests/` tree when bumping.
- **Codex/OpenCode adapters don't register `pre_compact_handoff`** — `hooks/adapters/codex/hooks.json:17–28` and `hooks/adapters/opencode/index.ts:64–72` only register `pre_compact`, not `pre_compact_handoff`. This is an intentional adapter gap (the handoff variant is Claude-Code-only), NOT a fix-required observation for ENH-2495. Codex/OpenCode users simply won't get `compaction` lifecycle events from the handoff path — the regular `pre_compact` path still emits them.
- **`ENH-2509` coordination anchor confirmed** — `ENH-2509:142` records the `/ll:decide-issue` decision for Option A (Co-implement): both issues land in a single PR sharing the `session_lifecycle_events` table. The shared schema (`(ts, session_id, event, detail JSON, head_sha, branch)` per ENH-2495 line 152–162) is canonical; `ENH-2509`'s `worktree_create`/`worktree_merge`/`worktree_delete` event discriminators are added as additional `event` TEXT values (no CHECK constraint). The shared recorder signature is `record_session_lifecycle_event(db_path, *, ts, session_id, event, detail=None, head_sha=None, branch=None)` — confirmed identical at `ENH-2509:241–246`.

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

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation. Numbering continues from Step 8 above._

9. Package re-export for `from little_loops import *` parity.
   - Add `"record_session_lifecycle_event"` to `scripts/little_loops/__init__.py:44` next to `record_issue_snapshot`. Required so downstream callers (CLI subcommands, hooks) can use the helper without a fully-qualified import path.

10. Extend `_EXPORT_TABLE_MAP` AND `_EXPORT_DEFAULT_TABLES` (BOTH, not just one).
    - `_EXPORT_TABLE_MAP` at `scripts/little_loops/session_store.py:3304–3316` — add `"session_lifecycle_event": ("session_lifecycle_events", "ts")`.
    - `_EXPORT_DEFAULT_TABLES` at `scripts/little_loops/session_store.py:3318–3329` — add the matching default-table entry.
    - Without BOTH, `ll-session export` silently skips `session_lifecycle_events` unless `--tables session_lifecycle_event` is passed explicitly. ENH-2461 documented the two-map pattern at `.issues/enhancements/P3-ENH-2461-...md:378`.

11. Bump `SCHEMA_VERSION == 20` assertions across the test suite.
    - `scripts/tests/test_session_store.py:1371–1372, 1817, 1932, 1984, 2080, 3658, 3699` — multiple `assert SCHEMA_VERSION == 20` literals across `TestRecord*` classes.
    - `scripts/tests/test_assistant_messages.py:88` — single `assert SCHEMA_VERSION == 20`.
    - `scripts/tests/test_hook_session_start.py:307, 332, 341` — `TestRebuildFlagOnlyWhenSchemaVersionAdvanced`, `TestFreshMigrationTriggersRebuild`.
    - Use `grep -rn "SCHEMA_VERSION ==" scripts/tests/` to verify completeness before merging.

12. Update `docs/guides/BUILTIN_HOOKS_GUIDE.md` hook writers list and flow diagram.
    - Line 59 (PostToolUse records line) — add `session_lifecycle` companion row.
    - Line 94 (flow diagram) — add `sweep_stale_refs`/`pre_compact`/`context-handoff-sentinel` as DB writers.
    - Line 434 — consider `analytics.capture.session_lifecycle_events` flag (precedent: `usage_events`).

13. Update `docs/reference/CONFIGURATION.md` `hooks.pre_compact.rubric.*` block.
    - Lines 1162–1178 — mention that compaction events from this hook flow into `session_lifecycle_events`. Cross-reference ENH-2507 if present.

14. Update `.claude/CLAUDE.md` `ll-session` prose references.
    - Lines 141–142, 186, 196, 203, 218 — add `session_lifecycle` to kind listings where `recent`/`search`/`compact` are documented. Mirror the table updates in `HISTORY_SESSION_GUIDE.md`.

15. Update `docs/reference/API.md` schema version drift + new API sections.
    - Line 7275 — bump "Current schema version: 19" (already drifted by 1) → 21 (or next open slot).
    - Line 7279 — bump `SCHEMA_VERSION,        # 19` import snippet.
    - Lines 6847–6848 — add `LifecycleEvent`, `recent_lifecycle_events`, `handoff_frequency` to the `from little_loops.history_reader import (...)` block.
    - Lines 7051–7077 — add API reference sections for `recent_lifecycle_events` and `handoff_frequency` next to `recent_commit_events`/`recent_test_runs`.
    - Lines 7286–7287 — add `record_session_lifecycle_event` to the public-API docstring excerpts (alongside `record_commit_event`/`record_test_run_event`).
    - Lines 7346–7389 — add a `record_session_lifecycle_event` API reference section.
    - Lines 4102–4103 — fix brace-list drift (`{tool,file,issue,loop,correction,message,skill,cli,commit,test_run}` is missing `snapshot` and `usage`); either enumerate the full `VALID_KINDS` set or link to it.

16. Update `docs/reference/CLI.md` `--kind` choices lists + worked examples.
    - Line 2427 — `search --kind` brace list — add `session_lifecycle` (and fix drift).
    - Line 2435 — `recent --kind` brace list — add `session_lifecycle` (and fix drift).
    - Line 2501 — `export --tables` choices table — add `session_lifecycle_event` IF `_EXPORT_TABLE_MAP` extended.
    - Lines 2510–2512 — worked examples block — add `ll-session recent --kind session_lifecycle` example.

17. Update `docs/ARCHITECTURE.md` schema versions table + sequence diagram + Components table.
    - Lines 670–678 — schema versions table (currently ends at v20/usage_events); add v21 row mirroring v17/v18/v19/v20 format (`session_lifecycle_events` + ENH-2495 + producer wiring description).
    - Lines 714–729 — mermaid sequence diagram `v1–v20`; extend to v21 and add `sweep_stale_refs`/`pre_compact`/`context-handoff-sentinel` as DB-writer arrows.
    - Lines 753–754 — Components table; currently only lists `post_tool_use` and `user_prompt_submit` as hook writers — add rows for the new producers.

18. Update `docs/guides/HISTORY_SESSION_GUIDE.md` (full coverage).
    - Lines 51, 60–75 — schema versions table — add v21 row.
    - Lines 32–43 — task→command table — add `ll-session recent --kind session_lifecycle` row mirroring `--kind commit`/`--kind test_run`.
    - Lines 80–100 — "What Gets Recorded" reference table — add `session_lifecycle_events` row.
    - Line 170 — `--kind` enumeration list — append `session_lifecycle`.

19. Extend `scripts/tests/test_hooks_integration.py:TestContextHandoffSentinel` with DB-row assertions + `|| true` semantics test.
    - Add `test_writes_lifecycle_row_on_threshold_crossing` — invoke the modified sentinel script via `subprocess.run`, then open the resulting DB and assert a `session_lifecycle_events` row with `event="handoff_needed"` and the threshold detail landed.
    - Add `test_python_failure_does_not_flip_exit_code` — point `LL_HISTORY_DB` at a directory (sqlite raises `OperationalError`), run the script, assert `returncode == 0` AND the sentinel file was still written.

20. Add graceful-degradation hook-handler tests.
    - `scripts/tests/test_sweep_stale_refs.py` — add `test_writes_lifecycle_row_silently_with_broken_db` (mirror the precedent at `TestSweepStaleRefsGracefulDegradation:255`).
    - `scripts/tests/test_pre_compact.py` — add `test_writes_compaction_lifecycle_row_silently_with_broken_db`.
    - Both call `handle(_event(cwd=tmp_path))` after pointing `LL_HISTORY_DB` at the tmp directory; assert the hook's primary job completes AND no `session_lifecycle_events` row is written (graceful drop, not exception).

21. Coordinate with `ENH-2509` (worktree lifecycle events) before merging.
    - `ENH-2509:142` records the `/ll:decide-issue` Option A (Co-implement) decision: both issues land in a single PR sharing the `session_lifecycle_events` table.
    - The shared recorder signature is `record_session_lifecycle_event(db_path, *, ts, session_id, event, detail=None, head_sha=None, branch=None)` — confirmed identical at `ENH-2509:241–246`.
    - The shared schema is `(ts, session_id, event TEXT, detail TEXT JSON, head_sha, branch)` — no CHECK constraint on `event`; `ENH-2509`'s `worktree_create`/`worktree_merge`/`worktree_delete` are added as additional `event` discriminators per `ENH-2509:84–101`.
    - Confirm the v21 migration SQL is identical in both issues before merging.

### Stale Reference Audit

_Added by `/ll:refine-issue` — verifying the Integration Map's anchors against the current codebase (post-2026-07-07 baseline):_

- **`VALID_KINDS` is a `tuple`, not a `frozenset`** — the existing "Codebase Research Findings" item stating "**_VALID_KINDS is a `frozenset`** validated inside `recent()` at line 1278" is wrong. At line 209 it's `VALID_KINDS: tuple[str, ...] = (...)` (no leading underscore, no `frozenset`). `recent()` validates it via `if kind not in VALID_KINDS: raise ValueError(...)` and indexes `_KIND_TABLE[kind]` for the SQL — so adding `"session_lifecycle"` to both `VALID_KINDS` and `_KIND_TABLE` is still the gate, but the constant is `VALID_KINDS` (no underscore) and the type is `tuple`.
- **`record_commit_event` is at line 1222** (not line 1041 as the Integration Map says); **`record_test_run_event` is at line 1352** (not line 1171). The function bodies are unchanged in shape but the anchors in the Integration Map and Implementation Steps (e.g., "after `record_test_run_event` (line 1171)") have drifted. The implementer should grep for the actual line at implementation time, not trust the literal anchor.
- **CLI `choices` lists are NOT duplicated** — both `search_parser.add_argument("--kind", choices=list(VALID_KINDS), ...)` (line 103) and `recent_parser.add_argument("--kind", choices=list(VALID_KINDS), ...)` (line 115) call `list(VALID_KINDS)` directly. There is exactly **one** update point: `VALID_KINDS` in `session_store.py`. The earlier refine-pass note that "both must be updated; otherwise `ll-session recent --kind session_lifecycle` will reject the kind" overstates the work — adding to `VALID_KINDS` once propagates to both parsers automatically.
- **`__all__` block ends at line 93** (29 entries; "SkillEventCompletion", "resolve_history_db", "record_retirement", "list_retirements" are the last three, added since the prior refine pass). Add `"record_session_lifecycle_event"` after `"record_test_run_event"` at line 86 — that anchor is still accurate.
- **`session_id` is available on `LLHookEvent`** (see `scripts/little_loops/hooks/types.py:44`, `session_id: str | None = None`). The handlers `sweep_stale_refs.handle()` and `pre_compact.handle()` don't currently extract it from `event.session_id`; the implementer should add `session_id=event.session_id` to each `record_session_lifecycle_event(...)` call. This is what makes the rows correlate to the `issue_sessions` / ENH-2462 linkage — without it, the new table is row-isolated from session attribution.

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

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): This issue's Integration Map
assumes it is the sole claimant of the next schema-version slot ("bump
`SCHEMA_VERSION = 18` → `19`"). At least ten other active EPIC-2457 siblings
(ENH-2463, ENH-2464, ENH-2465, ENH-2492, ENH-2493, ENH-2494, ENH-2496,
ENH-2497, ENH-2498, ENH-2511) independently make the same "18→19" claim in
their own Integration Maps — they cannot all be v19. Verified against current
code (`scripts/little_loops/session_store.py`): `SCHEMA_VERSION` is now **20**
(v17=`commit_events`/ENH-2458 done, v18=`test_run_events`/ENH-2459 done,
v19=`raw_events`/ENH-2581 done, v20=`usage_events`/ENH-2461 done). At
implementation time, read the live `SCHEMA_VERSION` constant to determine the
actual next-available slot rather than trusting this issue's stale "19"
literal; each child lands its own migration at whatever version is open when
it is implemented (no coordinated release; per EPIC-2457's own "no shared
helper module is required" scope note). Note also that **ENH-2509** (worktree
lifecycle events) is an intentional, already-coordinated widening of this
issue's `session_lifecycle_events` table — not a conflict.

## Session Log
- `/ll:wire-issue` - 2026-07-16T23:33:29 - `93c7c3d0-7fc2-409d-9882-227ad5f6e063.jsonl`
- `/ll:refine-issue` - 2026-07-16T15:15:18 - `165a14ee-791b-4c16-a333-4b3b4da4a314.jsonl`
- `/ll:audit-issue-conflicts` - 2026-07-14T00:23:48 - `bf6876a0-2fb4-4626-99a4-da1569d51511.jsonl`
- `/ll:refine-issue` - 2026-07-07T00:57:52 - `f072a647-96ed-4b8d-bdc1-936243abf1c4.jsonl`
- audit - 2026-07-06 - Corrected "only post-tool-use writes to history.db": the `user-prompt-check.sh` → `user_prompt_submit.py` path also writes (corrections + skill events). Core claim stands — no session-*lifecycle* hook writes to the DB. Fixed sweep_stale_refs path.
- `/ll:capture-issue` - 2026-07-05T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/`
