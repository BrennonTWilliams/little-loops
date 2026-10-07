---
id: BUG-3761
title: rebuild() wipes hook-written tool_events and user_corrections rows that replay cannot regenerate
type: BUG
priority: P1
status: open
discovered_date: '2026-10-06'
labels: []
decision_needed: false
reconcile_attempted: true
verify_verdict: NON_VALID

---

## Summary

`rebuild()` wipes every row in `tool_events` and `user_corrections`, then replays both tables from `raw_events`. Both tables also receive **live writes that never pass through `raw_events`**, so every rebuild permanently deletes those rows. This affects more than a manual `ll-session rebuild`: a `REBUILD_DERIVE_VERSION` mismatch forces one full wipe-and-replay on every store, so each derive-version bump silently drops this telemetry in every project.

This is the same class of defect as BUG-3530 (live `usage_events`) and BUG-3715 (retention `summary_nodes`). Both were fixed by adding a `_REBUILD_TABLE_PREDICATES` entry that spares rows replay cannot regenerate. `tool_events` and `user_corrections` have no such predicate, and no column that could support one.

## Steps to Reproduce

1. Use a store whose PostToolUse hook has been recording for a while (any project with hooks installed). Count the rows: `SELECT count(*) FROM tool_events WHERE length(ts) = 20` (the hook's second-precision timestamps), and the same for `user_corrections WHERE source = 'user_prompt_submit'`.
2. Run `ll-session rebuild`.
3. Re-count. The hook-written rows are gone. Replay re-derives `tool_events` from transcripts, but those rows carry different fields and millisecond timestamps, and only some of them correspond to hook rows.

Observed on a consumer project's 1.1 GB store under v1.167.0: one rebuild deleted 2,396 hook-written `tool_events` rows across 78 sessions (Bash 2,288, Read 78, Edit 44, Agent 43, Write 42, Skill 12) and 2 `user_corrections` rows. Net `tool_events` went from 41,593 to 40,567. The rows were recovered only because a backup had been taken first.

## Current Behavior

- `_REBUILD_TABLES` (`scripts/little_loops/session_store/lifecycle.py:1039`) lists `tool_events` and `user_corrections`. `rebuild()` (`scripts/little_loops/session_store/lifecycle.py:1774`) runs `DELETE FROM {table}` for each, applying `_REBUILD_TABLE_PREDICATES` only where an entry exists (`scripts/little_loops/session_store/lifecycle.py:1817-1819`). Neither table has an entry.
- The PostToolUse hook inserts `tool_events` directly (`scripts/little_loops/hooks/post_tool_use.py:202`), with `ts = _now()` (`session_store/writers.py:234`, second precision, `%Y-%m-%dT%H:%M:%SZ`). It records `latency_ms`, `bytes_in`/`bytes_out`, `cache_hit` and `mcp_outcome`, which replay does not reproduce.
- `record_correction()` (`session_store/writers.py:341`, insert at `:365`) writes `user_corrections` live with `source = 'user_prompt_submit'`.
- The `tool_events` and `user_corrections` schemas (`session_store/schema.py:136`, `:171`) have no channel or source column that tells live rows apart from replayed ones. `usage_events` has `channel`, which is what made the BUG-3530 predicate possible.
- The matching `search_index` rows (kinds `tool` and `correction`) are deleted with them.

## Expected Behavior

A rebuild re-derives only what replay can regenerate. Live-written `tool_events` and `user_corrections` rows, and their search-index entries, survive a manual rebuild and the automatic derive-version rebuild unchanged.

## Proposed Direction

- Add a discriminator to both tables, such as `channel TEXT` (`'live'` vs `'transcript'`), set by every writer. This needs a schema migration that backfills existing rows. A plausible classification heuristic: live hook rows have second-precision `ts` (length 20), while replayed rows have millisecond `ts`. For `user_corrections`, use the `source` value. Verify the heuristic against the writers before relying on it.
- Add `_REBUILD_TABLE_PREDICATES` entries (`channel IS NOT 'live'`) and keep the `search_index` deletion consistent with them.
- Decide how a live row and its replayed counterpart for the same tool call relate (today both exist; about 750 of the 2,396 had a replayed row in the same second). Keep that behavior unchanged unless deduplication is deliberately in scope.
- Bump `REBUILD_DERIVE_VERSION` only if the fix changes replay output.

## Proposed Solution

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-10-07 — based on codebase analysis:_

Proposed Direction (above) names a new `channel` column. Research found the discriminator already exists in both tables, so there are two viable routes:

**Option A**: Add a nullable `channel TEXT` to `tool_events` and `user_corrections` via a new `_MIGRATIONS` entry (v61) that classifies legacy rows in-migration (BUG-3530 / v53 shape, `schema.py:1449-1457`), set `'live'`/`'transcript'` in all four INSERT sites, and add `channel IS NOT 'live'` predicates. Cost: `SCHEMA_VERSION` bump with ~38 literal `== 60` test pins, regenerated `schema_manifest.json`, docs version mirrors, and a `post_tool_use.py` plus two `writers.py` write-path edits. The migration must still classify legacy rows with the same signals Option B reads at rebuild time, so the column stores a label whose derivation is identical to the predicate; v53's classifier already went stale once when `record_usage_event` began writing `session_id` (`writers.py:2073`).

**Option B**: Add predicates keyed on columns that already separate the writers (BUG-3715 shape, `kind = 'retention'`, no migration): `tool_events` live rows are `bytes_in IS NOT NULL` (hook always writes it, `post_tool_use.py:162`; replay always binds `None`, `writers.py:3703`), `user_corrections` replay rows are `source = 'backfill'` (`writers.py:4752`) and every other source is kept. No schema bump, no writer changes, no manifest or `SCHEMA_VERSION` churn; the fingerprint digest and `REBUILD_DERIVE_VERSION` still change (predicates are hashed). Cost: the signal is implicit rather than stored; legacy hook rows written before `bytes_in` was populated by the ctx-stats data layer (commit `6a4c7b5a6`; the column exists since v1) read as replayable and are wiped — those rows are indistinguishable from replay output by any column. Decide whether that tail is acceptable or whether a one-time classification is needed.

> **Selected:** Option B — predicates on columns that already separate live from replay rows; no migration, matches the BUG-3715 shape, and `ctx_stats` already reads `bytes_in IS NOT NULL` as the live signal.

**Recommended**: Option B — the live/replay signal is already structural in both writers, and the migration in Option A would have to derive its backfill from that same signal. `length(ts) = 20` must not be used for either option (see Root Cause).

Either option must also resolve three points the Proposed Direction leaves open: (1) the `search_index` delete at `lifecycle.py:1820-1824` needs an exclusion for the live rows' entries — index rows carry no base-table id, but live tool entries have `anchor` = session id (replay: `source_path`, `writers.py:3716`) and live correction entries have `anchor` = `source` (`'user_prompt_submit'` vs `'backfill'`, `writers.py:4757-4764`); (2) live-vs-replayed duplicate handling for `tool_events` is unchanged by default — no UNIQUE constraint exists, so a surviving live row plus its replayed twin both persist (the ~750 same-second pairs in the issue), while `user_corrections` has `idx_corrections_dedup` UNIQUE on `(session_id, content)` (`schema.py:268-273`), so a surviving live correction makes the replay `INSERT OR IGNORE` a no-op and skips its `search_index` write (`writers.py:4760`, guarded on `rowcount`) — the live row's index entry is therefore the only one, which is another reason (1) is required; (3) `AUTOINCREMENT` ids (`tool_events`) are not reset by `DELETE`, so surviving rows keep ids and replayed rows get higher ones — nothing links by id (no triggers, no FTS id join), so no consumer is affected.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-10-06.

**Selected**: Option B

**Reasoning**: Both options fit existing precedent (Option A = v53/BUG-3530, Option B = BUG-3715), but Option A's stored label must be backfilled from the very signals Option B reads, so it adds a schema bump without adding information for legacy rows. Option B needs no migration, no writer edits and no v61 slot (contended by FEAT-3711/EPIC-3710), and it avoids ~41 literal `== 60` pin edits. Its costs are the implicit signal and the unrecoverable legacy-NULL-`bytes_in` tail, which is the same tail Option A's migration would also misclassify.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option A | 3/3 | 1/3 | 2/3 | 1/3 | 7/12 |
| Option B | 3/3 | 3/3 | 3/3 | 2/3 | 11/12 |

**Key evidence**:

Evidence on A: v53 is an exact precedent (`schema.py:1449-1457`, `test_v53_migration_classifies_legacy_rows`), but 41 literal `== 60` pins (not ~38) plus the `["58","59","60"]` parametrization need editing, hand-listed downgrade helpers need new `DROP COLUMN`s, v61 is contended, and a pre-v61 hook or remote writer inserts `channel` NULL, which `IS NOT 'live'` sends to the wipe side.

Evidence on B: every live hook insert sets integer `bytes_in` (`post_tool_use.py:162,212`, single INSERT site for all hosts, `tool_input=None` still yields `2`); replay binds `None` (`writers.py:3702-3705`) and `'backfill'` (`writers.py:4752-4753`); `ctx_stats.py:166-167` already treats `bytes_in IS NOT NULL` as live. Predicate form for `tool_events` must keep NULL on the wipe side (e.g. `bytes_in IS NULL`), and the `search_index` exclusion must be inline SQL in `rebuild()` (no new helper, to keep the 23-function fingerprint pin) — anchor splits cleanly for corrections (`'backfill'`) but is a session-id-vs-path heuristic for tool entries.

Evidence common to both: the `search_index` exclusion has no precedent, `REBUILD_DERIVE_VERSION` must bump with a regenerated `rebuild_fingerprint.json` in the same commit, and `user_corrections` `IS NOT 'backfill'` keeps legacy NULL-`source` rows.

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-10-07 — based on codebase analysis:_

- **Files to Modify** (constraints, not edit order):
  - `scripts/little_loops/session_store/lifecycle.py` — `_REBUILD_TABLE_PREDICATES` (`:1051`) must stay a plain literal dict (`tests/rebuild_fingerprint.py:_literal` uses `ast.literal_eval`); the `search_index` delete (`:1820-1824`) must stop removing index entries of rows the new predicates keep; the `rebuild()` docstring (`:1782-1785`) already claims the exception exists for predicate-preserved rows and must stay true; the comment block above `_REBUILD_TABLES` (`:1016-1038`) names each preserved class by issue ID.
  - `scripts/little_loops/session_store/schema.py` — only if a discriminator column is added (see Proposed Solution options): a new `_MIGRATIONS` entry (currently 60), `SCHEMA_VERSION` (`:29`), and the regenerated `schema_manifest.json`.
  - `scripts/little_loops/session_store/writers.py` and `scripts/little_loops/hooks/post_tool_use.py` — only if a column is added: the INSERTs at `writers.py:365`, `:3695`, `:4752` and `post_tool_use.py:202` would have to set it.
  - `scripts/little_loops/session_store/rebuild_fingerprint.json` — regenerated in the same change (see Conventions).
- **Dependent Files (Callers/Importers)**:
  - `rebuild()` callers: `lifecycle.py:1983` (`backfill`), `:2048` (`backfill_incremental`), `cli/session.py:957`, `cli/session.py:1154`, `cli/backfill_worker.py:230`. All share one wipe path, so one predicate covers manual and derive-version-triggered rebuilds.
  - Readers that must keep working with live rows surviving alongside replayed rows: `cli/ctx_stats.py:167` (`_aggregate_tool_events`, filters `bytes_in IS NOT NULL OR bytes_out IS NOT NULL` — i.e. it already treats the hook-only columns as the live signal), `history_reader/usage.py` (`recent_tool_events`, `agent_usage`), `history_reader/search.py:55` (`find_user_corrections`), `issue_history/evolution.py:83,114` (`GROUP BY content`), `issue_history/agent_quality.py:283`, `history_reader/digest.py:94`, `cli/logs.py:900`, `writers.py:2715` (`reconcile_stale_subagent_runs` string-compares `MAX(ts)` per session).
  - `SELECT *` readers that would surface a new column: `queries.recent()` (`queries.py:83`) for kinds `tool` and `correction`, `export_history` (`queries.py:631`) for `correction`.
- **Conventions in Force**:
  - A fix that keeps non-replayable rows adds an entry to `_REBUILD_TABLE_PREDICATES`, written in `IS NOT <live-marker>` form so NULL falls on the wipe side — evidence: `lifecycle.py:1052-1058`.
  - The discriminator is either a new column plus an in-migration legacy classifier (BUG-3530, `schema.py:1449-1457`, v53) or an already-existing column (BUG-3715, `kind = 'retention'`, no migration). These two precedents disagree on whether a migration is needed; the choice is the decision recorded under Proposed Solution.
  - A change to non-usage rebuild derivation, `_REBUILD_TABLES`, `_REBUILD_SEARCH_KINDS`, the DDL of a non-usage rebuild table, or a non-usage predicate moves the fingerprint digest (`tests/rebuild_fingerprint.py:compute_fingerprint`), and `TestDeriveFingerprint.test_digest_matches_snapshot` (`test_enh3678_rebuild_derive_gate.py:462`) then requires `REBUILD_DERIVE_VERSION != _FROZEN_LEGACY_DERIVE_VERSION` (both are `"enh3678-v1"` today). So the "bump only if replay output changes" line in Proposed Direction is not what the gate enforces — any option here (new predicate, or new column) forces a bump plus a regenerated `rebuild_fingerprint.json` in the same commit.
  - A derive-version bump marks every store `stale / derive_mismatch` and auto-rebuilds stores up to 2**26 bytes — i.e. it is itself the wipe event this issue fixes. The preservation predicate and (if a column is chosen) its migration backfill must therefore already be live when the bumped version first runs; they ship in the same change, and migrations run at `connect()` before any `rebuild()`.
  - Live-write helpers: timestamps come only from `writers._now()` (`:234`, 20-char second precision); `_index()` (`writers.py:291`) is the single `search_index` writer.
- **Tests**:
  - Preservation-test shape in force: seed through the real writer, run `rebuild(db)` twice, compare selected columns row-for-row (`test_session_store_lifecycle.py:2102` `test_rebuild_preserves_live_usage_rows`; `TestRebuildPreservesRetention` `:2452`). The real hook writer is drivable directly via `post_tool_use.handle(LLHookEvent(...))` with `.ll/ll-config.json` `{"analytics": {"enabled": true}}` and `monkeypatch.chdir` (`test_enh_2511_mcp_telemetry.py:90` `TestMcpToolLiveWrite`).
  - No existing test asserts live `tool_events`/`user_corrections` survive `rebuild()`; `test_rebuild_does_not_touch_out_of_scope_tables` (`:1919`) and `TestPrune` (`:2794-2812`) do not cover it.
  - Must keep passing: `TestRebuild` (`test_session_store_lifecycle.py:1829`), `TestFts5LeakFixed` (`:2595`, `search_index` counts after rebuild), `test_rebuild_derives_codex_tool_events` (`:274`), `test_mine_corrections_idempotent` (`test_session_store_writers.py:942`), `TestDeriveFingerprint` (`:417-481`, function-set count pinned at 23 at `:456`).
  - If a migration is added: `SCHEMA_VERSION == len(_MIGRATIONS)` (`test_session_store_schema.py:2368`), manifest parity (`:3175`, `:3192`), and ~38 literal `SCHEMA_VERSION == 60` pins across `test_session_store_schema.py` (26), `test_session_store_writers.py` (5), `test_assistant_messages.py`, `test_bug3736_usage_replay_holds.py`, `test_hook_session_start.py`, `test_session_store_lifecycle.py`; `test_enh3678_rebuild_derive_gate.py:110` parametrizes `["58","59","60"]`. Migration-upgrade tests use `_bootstrap_schema_at(db, version)` (`test_session_store_lifecycle.py:3111`; `test_v53_migration_classifies_legacy_rows` `:2204` is the end-to-end shape: bootstrap old version, insert legacy rows, `ensure_db`, `rebuild`, assert survivors).
  - About 20 test files insert into these two tables with bare SQL and omit any discriminator column (`test_history_reader_search.py`, `test_evolution_triggers.py`, `test_cli_ctx_stats.py`, ...), so a new column must be nullable with no required value.
- **Documentation**: `docs/reference/CLI.md:4653-4660,4708` (rebuild wipe list), `docs/reference/API.md:13035` (`channel = 'live'`), `:10204`/`:10210` (schema version, no test gate), `docs/guides/HISTORY_SESSION_GUIDE.md:58,114-123,201-220` (schema table and rebuild note; the "Current schema version" sentence already disagrees with the table's v60 row), `docs/ARCHITECTURE.md:677-717,773-774,806-807`, `docs/reference/CONFIGURATION.md:557-595`, and `CHANGELOG.md` (entry goes under a concrete version section at release prep, not `[Unreleased]`).
- **Configuration**: `analytics.enabled` gates the hook `tool_events` write; `analytics.capture.corrections` gates both correction writers; `REBUILD_AUTO_MAX_BYTES = 2**26` gates the automatic derive-version rebuild (`lifecycle.py`, `rebuild_disposition`). Migration SQL also runs against remote stores (`remote_schema.py:50` returns `schema._MIGRATIONS`), and is split on `;` (`schema.py:1597` `_split_sql_statements`), so no `;` inside string literals.

_Added by `/ll:refine-issue` — 2026-10-07 — based on codebase analysis:_

- **Conventions in Force (pattern-finder)**:
  - Wipe predicates are per-table SQL literals in `_REBUILD_TABLE_PREDICATES`, spelled `<col> IS NOT <marker>` so NULL discriminators fall on the wipe side, with the rationale in the comment block tagged by issue ID (`lifecycle.py:1016-1038`, `:1051-1059`); the dict must stay a literal because `tests/rebuild_fingerprint.py:_literal` (`:134-148`) uses `ast.literal_eval`, and `compute_fingerprint` (`:172-179`) hashes every non-usage predicate.
  - Scoped `search_index` deletes elsewhere key on `kind` plus `anchor` or `ref` (`usage_refresh.py:360-363`, `lifecycle.py:1342`, `writers.py:1916-1918`, `:2217-2219`); `rebuild()`'s own delete is the only blanket per-kind one. For `tool` and `correction`, `anchor` is the only column that differs between live and replay entries; `ref` and `ts` match the base row's columns for both.
  - The hook-written/replay-written split is already read this way by `cli/ctx_stats.py:_aggregate_tool_events` (`:165-168`), but with `bytes_in IS NOT NULL OR bytes_out IS NOT NULL`; the selected predicate keys on `bytes_in` alone. No production writer produces `bytes_in` NULL with `bytes_out` non-NULL, so the two agree on real data — a test seeding such a bare-SQL row would see them differ.
  - Preservation tests share one shape: seed live rows via the public writer, replayable rows via `backfill_raw_events` or raw `INSERT`, run `rebuild(db)` twice, compare row snapshots, and add a separate rollback test that injects a failure after the wipe (`test_session_store_lifecycle.py:2102`, `:2162`, `:2178`, `:2562`). Legacy-shaped rows are seeded with bare SQL or `_bootstrap_schema_at` (`:3111`).
  - Version bumps: `REBUILD_DERIVE_VERSION` is a manual literal of the form `<issue-id>-v<N>` (`lifecycle.py:1075`); `_FROZEN_LEGACY_DERIVE_VERSION` (`:1085`) is never bumped; `test_digest_matches_snapshot` (`test_enh3678_rebuild_derive_gate.py:462`) fails first on "version not bumped", then on "fingerprint stale".
  - No existing `rebuild()` test asserts `search_index` survival for `tool`, `correction` or `usage`; the only `search_index` count assertion after rebuild is `kind = 'message'` in `TestFts5LeakFixed` (`:2595`).

### Files to Modify (wiring)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/session_store/lifecycle.py:1073` — comment above `REBUILD_DERIVE_VERSION` names `test_rebuild_derive_fingerprint.py`, which does not exist (real gate: `test_enh3678_rebuild_derive_gate.py`); fix when editing the bump comment, and update the same comment's bump-worthy list (corrections selection) in `REBUILD_DERIVE_VERSION` [Agent 2 finding]
- `scripts/little_loops/session_store/lifecycle.py:1075` — bump the literal in `REBUILD_DERIVE_VERSION`; leave `_FROZEN_LEGACY_DERIVE_VERSION` (`:1085`) at `"enh3678-v1"` — the gate asserts `!=` between them [Agent 1 finding]
- `scripts/little_loops/session_store/lifecycle.py:1816-1824` — wipe loop and `search_index` delete in `rebuild()`; the predicate and the inline exclusion take effect atomically with replay and the stamp (single `BEGIN IMMEDIATE`) [Agent 1 finding]
- `scripts/little_loops/session_store/lifecycle.py` — `rebuild_pending_notice()` text ("derived tables (sessions, tool/skill events, corrections, summaries, search) remain out of date") is asserted by tests; leave unchanged unless the notice is deliberately reworded [Agent 2 finding]
- `scripts/little_loops/session_store/writers.py:3754` — comment above `USAGE_NOT_HELD_SQL` states the "mirrored literally in `_REBUILD_TABLE_PREDICATES`" contract; new predicates are also plain literals, but need no mirror constant, so no writers edit is required in `_backfill_tool_events` or `mine_corrections_from_messages` [Agent 2 finding]
- Regenerate the fingerprint with `python -c "import sys; sys.path.insert(0, 'scripts'); from pathlib import Path; from tests.rebuild_fingerprint import regenerate; regenerate(Path('.'))"` (`scripts/tests/rebuild_fingerprint.py:regenerate`); it rewrites `current_digest` and `function_set` only and never `frozen_legacy_digest` [Agent 2 finding]

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/hooks/session_start.py:210-222` — calls `rebuild_disposition()` in `main()`/session-start handler; after the bump every existing store reports `derive_mismatch`, so small stores auto-rebuild once and stores above `REBUILD_AUTO_MAX_BYTES` get the pending notice [Agent 1 finding]
- `scripts/little_loops/cli/doctor.py:660-664` — `_rebuild_pending_data` calls `rebuild_disposition(DEFAULT_DB_PATH)`; the "Rebuild Pending" section reports every store stale until rebuilt after the bump [Agent 1 finding]
- `scripts/little_loops/session_store/__init__.py:101` — re-exports `REBUILD_DERIVE_VERSION`, `rebuild_disposition`, `rebuild_needed`, `_REBUILD_TABLES`, `_REBUILD_SEARCH_KINDS` (`__all__` `:274-282`, `:381-382`); no export change needed (`_REBUILD_TABLE_PREDICATES` is not exported) [Agent 1 finding]
- `scripts/little_loops/hooks/post_tool_use.py:223-228` — live `_index(kind="tool", anchor=str(session_id or ""))` in `handle()`; this anchor is the live side of the `search_index` exclusion for kind `tool` [Agent 1 finding]
- `scripts/little_loops/hooks/user_prompt_submit.py:128` — sole production caller of `record_correction`, passes `source='user_prompt_submit'` in `handle()` [Agent 1 finding]
- `scripts/little_loops/history_reader/usage.py:152` — `mcp_server_usage` counts `COUNT(*) ... WHERE mcp_server IS NOT NULL`, and `agent_usage` counts `tool_name='Task' AND agent_type IS NOT NULL`; a surviving live row plus its replayed twin both match, so invocation counts double. Note only — dedup is out of scope [Agent 2 finding]
- `scripts/little_loops/history_reader/sessions.py` — per-session `tool_count` (`COUNT(*) FROM tool_events WHERE session_id = ?`) counts both twins; note only [Agent 2 finding]
- `scripts/little_loops/session_store/usage_refresh.py:361` — the only other `search_index` deleter touching these kinds' neighbours (`kind = 'usage' AND anchor IN (...)`); usage-only, no change [Agent 1 finding]
- `.issues/enhancements/P3-ENH-3747-preserve-usage-search-evidence-across-rebuild-for-held-and-retained-usage.md` — edits the same `search_index` delete statement in `rebuild()`; a merge-conflict surface, not a code dependency [Agent 2 finding]

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_bug3736_usage_replay_holds.py:492` — hard-codes `lifecycle.REBUILD_DERIVE_VERSION == "enh3678-v1"` in `test_migration_creates_holds_table_and_keeps_version_constants`; **will break on the bump**, update the literal [Agent 3 finding]
- `scripts/tests/test_enh3678_rebuild_derive_gate.py:110` — `test_unmarked_legacy_store_at_or_above_floor_is_current` (parametrized `["58","59","60"]`) expects `RebuildState("current", "legacy_floor")`; **will break on the bump** (result becomes `stale/derive_mismatch` once `REBUILD_DERIVE_VERSION != _FROZEN_LEGACY_DERIVE_VERSION`) [Agent 2 + Agent 3 finding]
- `scripts/tests/test_enh3678_rebuild_derive_gate.py:127` — `test_null_stamp_is_treated_as_absent` expects `legacy_floor`; **will break on the bump**, same cause. Model the replacement on `test_future_bump_makes_unmarked_legacy_store_stale` (`:135`, expects `("stale", "derive_mismatch")`) [Agent 3 finding]
- `scripts/tests/test_enh3678_rebuild_derive_gate.py:462` — `TestDeriveFingerprint.test_digest_matches_snapshot` fails until `rebuild_fingerprint.json` is regenerated; the digest moves for two reasons: new non-usage predicates (`predicates:` part) and the inline `search_index` SQL in the hashed `rebuild()` body [Agent 3 finding]
- `scripts/tests/test_enh3678_rebuild_derive_gate.py:417` — add a digest-sensitivity test for the new `tool_events` and `user_corrections` predicates in `TestNormalizerStability`, modelled on `test_non_usage_predicate_changes_digest` [Agent 3 finding]
- `scripts/tests/test_session_store_lifecycle.py:2452` — new class beside `TestRebuildPreservesRetention` covering: (a) a hook-written `tool_events` row (via `post_tool_use.handle`) and its `search_index kind='tool'` entry survive `rebuild()`; (b) a replayed `tool_events` row and entry are wiped and re-derived once across two rebuilds; (c) a bare-SQL legacy row with NULL `bytes_in` is wiped (documents the tail); (d) a live correction (`record_correction(..., 'user_prompt_submit')`) and its `kind='correction'` entry survive; (e) a `source='backfill'` correction is wiped and re-mined; (f) a live and a replayed correction with the same `(session_id, content)` yield one row, since `idx_corrections_dedup` makes the replay `INSERT OR IGNORE` a no-op — no behavioural test covers this today; (g) rollback: a failure after the wipe (monkeypatch `lifecycle._stamp_rebuild_derive_version`, shape of `test_late_failure_rolls_back_wipe_and_metadata` `:2562`) leaves live rows and entries intact [Agent 3 finding]
- `scripts/tests/test_bug3736_usage_replay_holds.py:494` — `test_rebuild_predicate_matches_shared_hold_fragment` is the shape for pinning the new `_REBUILD_TABLE_PREDICATES["tool_events"]` / `["user_corrections"]` literals [Agent 3 finding]
- `scripts/tests/test_enh_2511_mcp_telemetry.py:90` — `TestMcpToolLiveWrite` and `scripts/tests/test_hook_post_tool_use.py:103` (`test_writes_row_when_analytics_enabled`, helpers `_event`, `_write_config`) are the live-writer seeding patterns; no existing test combines hook rows, replayed rows and `rebuild()` in one DB [Agent 3 finding]
- `scripts/tests/test_ll_session.py:1204` — `TestRebuildSubcommand` mocks `little_loops.cli.session.rebuild`; no real-DB CLI rebuild test exists (optional addition) [Agent 3 finding]
- Verified unaffected (replay-origin rows have NULL `bytes_in` / `'backfill'` source and are still wiped): `scripts/tests/test_enh_omp_normalizer.py:228`, `scripts/tests/test_enh_3393_gemini_normalizer.py:250`, `scripts/tests/test_enh_3166_qwen_normalizer.py:412`, `test_session_store_lifecycle.py:429` (`test_backfill_populates_corrections_from_correction_message`) and `:469` (`test_backfill_corrections_idempotent`), `test_backfill_worker_auto_rebuild.py:107`, `test_hook_session_start.py:443`, `test_session_store_lifecycle.py:2793` (`test_high_value_tables_never_pruned`, no rebuild call) [Agent 3 finding]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md:10567` — states `rebuild()` "always wipes+re-populates `search_index` from current cache-table state"; stale once live `tool`/`correction` index entries survive, in the `prune()` / FTS5-leak note [Agent 1 finding]
- `docs/reference/API.md:10239` — `rebuild,  # wipe+re-derive ...` import-listing comment in the session_store example [Agent 1 finding]
- `docs/ARCHITECTURE.md:695` — v19 `raw_events` schema row says `ll-session rebuild` wipes the cache tables plus `user_corrections` and the matching `search_index` rows, preserving only `kind='retention'` nodes; add the live-row carve-out; the v53 `usage_events.channel` row (`:723`) is the wording precedent [Agent 2 finding]
- `docs/guides/HISTORY_SESSION_GUIDE.md:211` — "`rebuild` wipes and re-derives those tables" blockquote in the ENH-2581 note, plus the Known limits paragraph on usage search rows, in `Known limits` [Agent 2 finding]
- `docs/reference/CLI.md:4574` — command-table row "Re-derive the JSONL-cache tables" and the `ll-session rebuild` usage example comment "keeps retention summaries" in the `rebuild` subcommand section [Agent 2 finding]
- `docs/guides/BUILTIN_HOOKS_GUIDE.md:153` — SessionStart step 6 describes the derive-version auto-rebuild and deferred notice; no wording change required, but after the bump each store rebuilds once and now preserves live rows [Agent 2 finding]
- `scripts/little_loops/cli/session.py` — module docstring and `rebuild_parser` help text ("Wipe+re-derive the JSONL-derived cache tables from raw_events") enumerate no exceptions; reword only if the doc pass touches the CLI.md row [Agent 2 finding]
- No change needed: `docs/codex/usage.md:139` (usage-only "A rebuild preserves live rows"), `docs/reference/HOST_COMPATIBILITY.md` (usage provenance footnote) [Agent 2 finding]

## Program Design

### Types

- New `tool_events.channel: TEXT`, nullable: `'live'` for hook-written rows, `'transcript'` for replayed rows. Added by a schema migration (current `SCHEMA_VERSION = 60`).
- New `user_corrections.channel: TEXT`, nullable, same values. Live rows are those written by `record_correction`, with `source = 'user_prompt_submit'`.
- Existing `_REBUILD_TABLE_PREDICATES: dict[str, str]`: gains `"tool_events"` and `"user_corrections"` entries, each `"channel IS NOT 'live'"`, mirroring the `usage_events` entry.

### Signatures

- `handle(event: LLHookEvent) -> LLHookResult`: PostToolUse hook; its `tool_events` INSERT sets `channel = 'live'`.
- `record_correction(db_path: Path | str, session_id: str | None, content: str, source: str, config: dict | None = None) -> None`: its `user_corrections` INSERT sets `channel = 'live'`.
- `_backfill_tool_events(conn: sqlite3.Connection, source: list[Path] | sqlite3.Cursor) -> int`: replay path; sets `channel = 'transcript'`.
- `rebuild(db: Path | str = DEFAULT_DB_PATH, *, config: dict | None = None, max_sessions: int | None = None) -> dict[str, int]`: signature unchanged. The `search_index` delete for kinds `tool` and `correction` must exclude the entries of surviving live rows.

### Call Path

`handle` -> `connect` -> `tool_events` INSERT (`channel = 'live'`)

`rebuild` -> `_REBUILD_TABLE_PREDICATES` -> `DELETE FROM tool_events WHERE channel IS NOT 'live'` -> `_backfill_tool_events`

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-10-07 — based on codebase analysis:_

- **Types**: `_REBUILD_TABLE_PREDICATES: dict[str, str]` (`lifecycle.py:1051`) currently holds `"usage_events"` and `"summary_nodes"` only; values are literal SQL strings and the dict is read by `tests/rebuild_fingerprint.py:_literal` via `ast.literal_eval`, so entries cannot be built from f-strings or imported fragments (`USAGE_NOT_HELD_SQL` is mirrored literally for this reason, `writers.py:3754`). `_REBUILD_SEARCH_KINDS: tuple[str, ...]` (`lifecycle.py:1061`) is `("tool", "message", "skill", "correction", "usage")`. `search_index` is FTS5 with columns `content, kind, ref, anchor, ts` (all but `content` UNINDEXED); no base-table id is stored.
- **Signatures** (existing, unchanged): `rebuild(db, *, config, max_sessions) -> dict[str, int]` (`lifecycle.py:1774`); `_backfill_tool_events(conn, source) -> int` (`writers.py:3664`); `mine_corrections_from_messages(conn, config) -> int` (`writers.py:4725`); `record_correction(db_path, session_id, content, source, config=None) -> None` (`writers.py:341`); `_index(conn, *, content, kind, ref, anchor, ts)` (`writers.py:291`); `rebuild_disposition(db) ` / `rebuild_needed(db)` (`lifecycle.py:1200`, `:1106`).
- **Call Path**: `hooks/session_start.py:205-231` → `rebuild_disposition()` → `cli/backfill_worker.py:230` `_rebuild(db_path, config=None)` → `rebuild()` → wipe loop (`:1817`) → `search_index` delete (`:1820`) → `_backfill_tool_events` (`:1839`) → `mine_corrections_from_messages` (`:1844`) → `_stamp_rebuild_derive_version` (`:1855`); the whole sequence is one `BEGIN IMMEDIATE` transaction and rolls back on any exception, wipe included.
- **Decision Rules** (new decision logic: a live-row classifier): inputs available to any classifier are `tool_events.{ts, bytes_in, bytes_out, result_size, cache_hit, latency_ms, mcp_outcome, agent_type}` and `user_corrections.source`, plus `search_index.{kind, ref, anchor, ts}`. Hook-written `tool_events` rows always carry integer `bytes_in`/`bytes_out`; replay rows carry NULL for `result_size`, `bytes_in`, `bytes_out`, `cache_hit`, `mcp_outcome`, `latency_ms`. `user_corrections.source` is `'user_prompt_submit'` (live) or `'backfill'` (replay); tests also seed `'user'`/`'test'`. Ambiguity must resolve toward keeping the row (Risk line in Impact). Escape hatch: none needed — a kept row is never deleted by anything except a manual `DELETE`, and `prune()` touches only `raw_events` (`lifecycle.py:2353`).
- **Constraint on any change to `rebuild()` internals**: `TestDeriveFingerprint` pins 23 reachable functions (`test_enh3678_rebuild_derive_gate.py:453-456`); adding a helper called from `rebuild()` changes that count and the digest.

_Added by `/ll:refine-issue` — 2026-10-07 — based on codebase analysis:_

- **Option B restatement (the Types/Signatures/Call Path bullets above describe rejected Option A and no longer apply)**: no column is added to either table, no migration runs, and none of the four INSERT sites changes. The live-row discriminators are existing columns: `tool_events.bytes_in` (hook binds an integer, `post_tool_use.py:202-221`; replay binds `None`, `writers.py:3694-3711`) and `user_corrections.source` (`record_correction` takes it from the caller, `'backfill'` is hard-coded in `mine_corrections_from_messages`, `writers.py:4752`). `user_corrections` has no `channel` column (`schema.py:171`).
- **Types**: `_REBUILD_TABLE_PREDICATES: dict[str, str]` gains `"tool_events"` and `"user_corrections"` entries as plain string literals (the dict is read by `ast.literal_eval`). Both are *wipe* predicates (rows matching are deleted): the `tool_events` entry must put NULL `bytes_in` on the wipe side (`bytes_in IS NULL`), and the `user_corrections` entry must wipe only `source = 'backfill'` rows, since the Decision Rationale keeps legacy NULL-`source` rows.
- **Signatures**: every signature named above is unchanged. `rebuild(db, *, config, max_sessions) -> dict[str, int]` (`lifecycle.py:1774`) is the only function whose body changes (inline `search_index` delete); no new helper is introduced, because `TestDeriveFingerprint` pins the reachable function set at 23.
- **Call Path**: `rebuild` -> per-table `DELETE FROM <table> WHERE <predicate>` (`lifecycle.py:1817-1819`) -> `DELETE FROM search_index WHERE kind IN (...)` with a live-entry exclusion (`:1820-1824`) -> `_backfill_tool_events` -> `mine_corrections_from_messages`. Live writers (`post_tool_use.handle`, `record_correction`) never enter this path.
- **Decision Rules (search_index exclusion)**: the delete runs *after* the base-table deletes in the same transaction, so at that point `tool_events` and `user_corrections` contain only surviving rows. Index entries carry no base-table id, but each live writer stores values that equal columns of its own row: tool entries have `anchor` = `session_id`, `ref` = `tool_name`, `ts` = row `ts` (`post_tool_use.py:223-228`); correction entries have `ref` = `session_id`, `content` = row `content` (truncated to 512, same as the row), `anchor` = `source`, `ts` = row `ts` (`writers.py:365-368`). Replay entries differ: tool `anchor` is the `raw_events.source_path` (`writers.py:3718`), correction `anchor` is `'backfill'` (`:4762`). The property needed: an entry is kept iff a surviving base row produced it. Keying on `anchor` alone (session id / `'user_prompt_submit'`) is weaker than that for `tool` — see the legacy-row finding under Acceptance Criteria.

## Acceptance Criteria

- [ ] A store holding live-written `tool_events` and `user_corrections` rows keeps every one of them, with all field values intact, across `rebuild()`.
- [ ] The same holds for the automatic wipe-and-replay triggered by a `REBUILD_DERIVE_VERSION` mismatch.
- [ ] Rows that replay derives are still fully wiped and re-derived (no duplicate accumulation across repeated rebuilds).
- [ ] No schema migration is needed (Option B): rows already present are classified at rebuild time by the predicates themselves, so existing hook-written `tool_events` rows (integer `bytes_in`) and non-`'backfill'` `user_corrections` rows survive the first post-upgrade rebuild. Legacy `tool_events` rows with NULL `bytes_in` are wiped and re-derived (the documented tail). Verified by a legacy-shaped bare-SQL row test that asserts the NULL-`bytes_in` row is wiped and the integer-`bytes_in` row is kept.
- [ ] Live rows keep their `search_index` entries across `rebuild()`: `kind='tool'` entries with `anchor` = session id and `kind='correction'` entries with `anchor = 'user_prompt_submit'` remain, while replay-origin entries are wiped and re-derived exactly once. Verified by `search_index` count and anchor assertions after running `rebuild()` twice.
- [ ] A regression test drives the real PostToolUse hook writer and `record_correction()`, runs `rebuild()`, and asserts row-for-row preservation. It fails on the current code.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-10-07 — based on codebase analysis:_

- [ ] **Legacy NULL-`bytes_in` tool_events entry (search_index)**: a hook-written `tool_events` row from before `bytes_in` was populated reads as replayable and its row is wiped, but its `search_index` entry has `anchor` = session id, the same shape as a surviving live row's entry. After `rebuild()`, that wiped row must not leave a surviving index entry (it would duplicate the replayed entry, or be orphaned if replay has no counterpart). Verified by a test that seeds one NULL-`bytes_in` row plus its entry and one integer-`bytes_in` row plus its entry in the same session via bare SQL / `_index`, runs `rebuild()` twice, and asserts exactly the live row's entry remains alongside the replay-derived entries. Whether this is met by a session-id-anchor exclusion or by a row-matched exclusion is open; a session-id-anchor-only exclusion fails this criterion whenever a session mixes legacy and live rows (research basis: `post_tool_use.py:223-228`, `writers.py:3713-3720`, and the surviving-row-only state at the point of the `search_index` delete).
- [ ] **Legacy-source corrections**: a `user_corrections` row with NULL `source` (legacy/test-seeded) and its `kind='correction'` entry are kept by `rebuild()`; a `source='backfill'` row and its `anchor='backfill'` entry are wiped and re-mined exactly once.

## Implementation Steps

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-10-07 — based on codebase analysis:_

1. Live `tool_events` and `user_corrections` rows (and their `search_index` entries) survive `rebuild()` unchanged, both manual and derive-version-triggered; replay-derived rows are still wiped and re-derived without accumulating across repeated rebuilds. Verified by a test beside `test_rebuild_preserves_live_usage_rows` (`test_session_store_lifecycle.py:2102`) that seeds through `post_tool_use.handle` and `record_correction()`, runs `rebuild(db)` twice, and compares rows column-for-column; it must fail on current code.
2. The discriminator decision is recorded (Proposed Solution: Option B selected — predicates on existing columns, no new column); `length(ts)` is not the classifier.
3. `REBUILD_DERIVE_VERSION` is bumped and `rebuild_fingerprint.json` regenerated in the same commit (the digest gate forces this for any option); `TestDeriveFingerprint` passes, and `_FROZEN_LEGACY_DERIVE_VERSION` stays untouched.
4. ~~If Option A: migration, `SCHEMA_VERSION`, manifest and literal-60 pin steps~~ — not applicable (Option B selected; no schema change). Instead: the `tool_events` predicate keeps NULL on the wipe side, the `search_index` exclusion is inline SQL in `rebuild()` (no new helper, keeps the 23-function fingerprint pin), and a test seeds a legacy-shaped live row to document the NULL-`bytes_in` tail.
5. `ll-session rebuild` and the auto-rebuild path produce the same survivor set (both call `rebuild()`); `python -m pytest scripts/tests/test_session_store_lifecycle.py scripts/tests/test_session_store_schema.py scripts/tests/test_enh3678_rebuild_derive_gate.py scripts/tests/test_session_store_writers.py -v` passes, then the full `python -m pytest scripts/tests/`.
6. Docs mirrors (`docs/reference/CLI.md` wipe list, `docs/reference/API.md`, `docs/guides/HISTORY_SESSION_GUIDE.md`, `docs/ARCHITECTURE.md`) describe the preserved rows; they are not test-gated.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Update `scripts/tests/test_bug3736_usage_replay_holds.py` — change the `REBUILD_DERIVE_VERSION == "enh3678-v1"` literal in `test_migration_creates_holds_table_and_keeps_version_constants` to the bumped value
- Update `scripts/tests/test_enh3678_rebuild_derive_gate.py` — rewrite `test_unmarked_legacy_store_at_or_above_floor_is_current` and `test_null_stamp_is_treated_as_absent` to expect `RebuildState("stale", "derive_mismatch")` once `REBUILD_DERIVE_VERSION != _FROZEN_LEGACY_DERIVE_VERSION` (the `legacy_floor` outcome only exists while the two are equal); leave `TestFrozenLegacyPins.test_frozen_legacy_derive_version_literal` untouched
- Add to `scripts/tests/test_enh3678_rebuild_derive_gate.py` — a `TestNormalizerStability` case showing the new `tool_events` / `user_corrections` predicates move the digest
- Add to `scripts/tests/test_session_store_lifecycle.py` — the survivor, wipe, NULL-`bytes_in` tail, same-`(session_id, content)` dedup and rollback cases listed under Integration Map › Tests
- Fix the stale test-file reference in the comment above `REBUILD_DERIVE_VERSION` in `scripts/little_loops/session_store/lifecycle.py` while editing the bump
- Regenerate `rebuild_fingerprint.json` with the `tests.rebuild_fingerprint.regenerate` one-liner after the final `rebuild()` edit, then run `TestDeriveFingerprint` (function-set count stays 23, so no new helper)
- Update the `search_index` wording in `docs/reference/API.md` (`prune()` note), `docs/ARCHITECTURE.md` (v19 row), `docs/guides/HISTORY_SESSION_GUIDE.md` (`rebuild` blockquote), `docs/reference/CLI.md` (`rebuild` row and example comment) to name the preserved live `tool_events` / `user_corrections` rows
- Coordinate with ENH-3747 before merging — it edits the same `search_index` delete statement in `rebuild()`

## Impact

- **Priority**: P1 - silent, permanent loss of live telemetry on every manual rebuild and on every `REBUILD_DERIVE_VERSION` bump, across all projects; observed 2,396 `tool_events` rows and 2 `user_corrections` rows lost in one rebuild.
- **Effort**: Medium - one schema migration with a backfill classifier, two writer changes, two predicate entries and a `search_index` delete adjustment; follows the BUG-3530 pattern.
- **Risk**: Medium - touches the schema migration path and the rebuild wipe; mitigated by the row-for-row regression test and by backfilling existing rows conservatively, so ambiguous rows are preserved rather than wiped.
- **Breaking Change**: No

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-10-07 — based on codebase analysis:_

- **Effort/Risk restated for Option B (selected)**: the Effort and Risk lines above describe Option A (schema migration, backfill classifier, two writer changes) and no longer apply. Option B is two predicate literals in `_REBUILD_TABLE_PREDICATES`, one inline `search_index` exclusion in `rebuild()`, a `REBUILD_DERIVE_VERSION` bump with a regenerated `rebuild_fingerprint.json`, and ~3 test edits for the bump (`test_bug3736_usage_replay_holds.py:492`, `test_enh3678_rebuild_derive_gate.py:110`, `:127`) — Effort: Small-Medium. Residual risk: the unrecoverable legacy NULL-`bytes_in` `tool_events` tail (wiped and re-derived without the hook-only fields) and the `search_index` exclusion's precision for that tail. The bump itself triggers the first automatic rebuild on every store at or below `REBUILD_AUTO_MAX_BYTES`, so the predicates must ship in the same change.

## Status

**Open** | Created: 2026-10-06 | Priority: P1


## Session Log
- `/ll:refine-issue:gap-analysis` - 2026-10-07T00:39:26 - `c822b1e8-eb73-465f-ac83-ee54531a264e.jsonl`
- `/ll:reconcile-issue` - 2026-10-07T00:31:44 - `c0a7447a-de94-4f52-84a5-8f881b60acd9.jsonl`
- `/ll:wire-issue` - 2026-10-07T00:29:12 - `a8216bde-d16f-4810-80e1-dfa40b1fe3ce.jsonl`
- `/ll:decide-issue` - 2026-10-07T00:20:39 - `c562a3b7-7006-4c12-9609-bf1d64934054.jsonl`
- `/ll:refine-issue` - 2026-10-07T00:14:30 - `1bebe889-c22b-4d94-a454-4b6419a82d25.jsonl`
- `/ll:format-issue` - 2026-10-06T23:51:08 - `be24ca19-aef3-4138-b6f0-d60a7d2187c1.jsonl`

## Root Cause

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-10-07 — based on codebase analysis:_

- **File**: `scripts/little_loops/session_store/lifecycle.py` — **Anchor**: `rebuild()` (wipe loop `:1817-1819`, search-index delete `:1820-1824`), `_REBUILD_TABLE_PREDICATES` (`:1051`, only `usage_events` and `summary_nodes` entries).
- **Cause**: the wipe loop emits an unconditional `DELETE FROM <table>` for `tool_events` and `user_corrections`, and the `search_index` delete is `kind IN (_REBUILD_SEARCH_KINDS)` with no predicate of any kind — it is not tied to `_REBUILD_TABLE_PREDICATES`, so even a base-table predicate would leave the live rows' index entries wiped. Live writers (`hooks/post_tool_use.py:201-221`, `session_store/writers.py:365` in `record_correction`) never write `raw_events`, so replay has nothing to regenerate them from. Only four INSERT sites exist for these tables in non-test code: `post_tool_use.py:202`, `writers.py:365`, `writers.py:3695` (`_backfill_tool_events`), `writers.py:4752` (`mine_corrections_from_messages`).
- **The rebuild trigger is the same function**: the derive-version path (`hooks/session_start.py` → `rebuild_disposition()` → `cli/backfill_worker.py:230` `_rebuild(db_path, config=None)`) calls `rebuild()`; there is no separate wipe path. Stores over `REBUILD_AUTO_MAX_BYTES` (2**26) only get a pending notice, so the automatic loss applies to stores at or below that size; manual `ll-session rebuild` (`cli/session.py:1154`) and `ll-session refresh` (`cli/session.py:957`) are unconditional.
- **Correction to the issue's "no column" claim**: `user_corrections.source` already discriminates the writers (`'user_prompt_submit'` from `record_correction`'s only production caller, `hooks/user_prompt_submit.py:128-130`; the literal `'backfill'` from `mine_corrections_from_messages`, `writers.py:4752`). `tool_events` also already carries a writer-exclusive signal: the hook computes `bytes_in`/`bytes_out` as `len(json.dumps(...))` on every write (`post_tool_use.py:162-163`, so never NULL), while `_backfill_tool_events` binds `None` for `result_size`, `bytes_in`, `bytes_out` and `cache_hit` (`writers.py:3702-3705`). `latency_ms` and `mcp_outcome` are likewise hook-only (`schema.py` v25 comment).
- **The `length(ts) = 20` heuristic in Proposed Direction is not a safe classifier**: replay copies the transcript record's `timestamp` verbatim (`writers.py:3679`), real Claude transcripts carry millisecond timestamps (24 chars) but Codex/test fixtures and any second-precision transcript produce 20-char replay rows (`test_session_store_lifecycle.py:137`, `:875`, `:1839`). No code or test uses `length(ts)` anywhere. A migration/predicate keyed on it would misclassify replayed rows as live (they would then never be wiped and would accumulate) — the opposite failure to the one being fixed.
