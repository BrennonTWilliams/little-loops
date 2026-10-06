---
id: BUG-3755
title: 'FSM events stamp ''loop'' but the SQLite and OTel transports read ''loop_name'':
  live loop telemetry loses its loop identity'
type: BUG
priority: P0
status: open
discovered_date: '2026-10-05'
verify_verdict: VALID
labels:
- telemetry
- transport
- history-db
learning_tests_required:
- opentelemetry-sdk
confidence_score: 95
outcome_confidence: 86
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 18
---

## Summary

FSM events carry the loop's name under `loop`, but two of the event transports read `loop_name`. Any user who enables the sqlite or otel transport gets loop telemetry with no loop identity.

ENH-3345 (done) made `FSMExecutor._emit` stamp `run_id` and `loop` on every event (`scripts/little_loops/fsm/executor.py`, `_emit`, around line 4175). `PersistentExecutor._handle_event` forwards events to the bus unchanged (`fsm/persistence.py`, the `event_bus.emit(event)` call). But:

- `SQLiteTransport.send` reads `event.get("loop_name")` (`session_store/writers.py`, around line 3087), so every live row inserted into the `loop_events` table (defined in `session_store/schema.py`) is written with `loop_name` NULL.
- `OTelTransport._handle_loop_start` and `_handle_loop_resume` read `event.get("loop_name", "ll-loop")` (`transport.py`, around lines 1784 and 1791), so every OTel loop span is named `ll-loop`.
- The sqlite writer also stores only `event.get("state")`, and a `route` event carries `from`/`to`, so route rows lose their transition entirely.

The transport tests hand-feed `{"loop_name": ...}` (for example `test_transport.py` and `test_session_store_writers.py`), a shape the executor never emits, so the suites stay green. Consumers that group live rows by `loop_name` (ll-logs, agent_quality, quality_regressions) undercount live runs, which skews the longitudinal quality metrics and regression attribution built on `history.db`.

The transports are the egress contract every quality layer above them trusts for event shape; a key mismatch between producer and transport is exactly the drift a conformance test against real executor output should catch.

## Steps to Reproduce

1. Enable the sqlite transport (and/or otel transport) for `ll-loop`.
2. Run any loop to completion, e.g. `ll-loop run <loop-name>`.
3. Query the history DB: `SELECT loop_name, state, transition FROM loop_events ORDER BY ts DESC LIMIT 20;`
4. Observe `loop_name` is NULL on every live row, and `route` rows carry no `from`/`to` transition.
5. For otel, inspect the exported spans: the loop span is named `ll-loop`, not the loop's name.

## Current Behavior

`FSMExecutor._emit` stamps `run_id` and `loop` on every event, but `SQLiteTransport.send` reads `event.get("loop_name")` and `OTelTransport._handle_loop_start`/`_handle_loop_resume` read `event.get("loop_name", "ll-loop")`. Live `loop_events` rows therefore have `loop_name` NULL, OTel loop spans are all named `ll-loop`, and `route` rows store only `state` (the `from`/`to` pair is dropped).

## Expected Behavior

Both transports take the loop name from the `loop` key (falling back to `loop_name` for older payloads): live `loop_events` rows carry a non-null `loop_name`, OTel loop spans are named after the loop, and sqlite `route` rows keep `from` as `state` and record `to` in a new nullable column.

## Root Cause

- **File**: `scripts/little_loops/fsm/executor.py` (producer) vs `scripts/little_loops/session_store/writers.py` and `scripts/little_loops/transport.py` (consumers)
- **Anchor**: `FSMExecutor._emit` stamps `"loop"`; `SQLiteTransport.send`, `OTelTransport._handle_loop_start`, `OTelTransport._handle_loop_resume` read `"loop_name"`
- **Cause**: ENH-3345 added `loop` stamping to `_emit` without updating the transports that predate it and still read `loop_name`; transport tests hand-feed `{"loop_name": ...}` dicts the executor never emits, so the key mismatch went undetected.

## Acceptance Criteria

Acceptance: (a) the sqlite and otel transports take the loop name from `loop`, falling back to `loop_name` for older payloads; (b) a test drives a real FSMExecutor/PersistentExecutor through the event bus into each transport and asserts a non-null loop name and a span named after the loop, replacing reliance on hand-built dicts; (c) sqlite `route` rows keep `from` as `state` and record `to`, as an additive nullable column through `_MIGRATIONS`; (d) existing transport and session-store suites pass.

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-10-06 — based on codebase analysis:_

- **Producer/consumer key split (verified)**: `FSMExecutor._emit` (`scripts/little_loops/fsm/executor.py:4168`) builds `{"event","ts","run_id","loop": self.fsm.name, **data}`; `loop_resume` stamps `"loop"` separately at `fsm/persistence.py:1469`. The only event-dict readers of `loop_name` are `SQLiteTransport.send` (`session_store/writers.py:3087`, `str(event.get("loop_name", "")) or None`) and `OTelTransport._handle_loop_start`/`_handle_loop_resume` (`transport.py:1784`, `:1791`). `cli/loop/feed.py:1056` already reads `event.get("loop", "")`, so there is no repo-wide `loop_name` event-key convention to preserve. No shared helper resolves the loop name from an event; `JsonlTransport`/`UnixSocketTransport`/`WebhookTransport` do not read the key.
- **Files to modify**: `scripts/little_loops/session_store/writers.py` (`SQLiteTransport.send` loop branch, `:3086-3112`), `scripts/little_loops/transport.py` (`OTelTransport` `:1783-1792`), `scripts/little_loops/session_store/schema.py` (`SCHEMA_VERSION = 59` at `:29`; `_MIGRATIONS` at `:134`; `loop_events` is created in v1 at `:163` as `id, ts, loop_name, state, transition, retries` and no `ALTER TABLE loop_events` exists yet).
- **Route payload shape (verified)**: `route` events are emitted with `{"from", "to", "reason"}` and no `state` key (`executor.py:869-874`, `:948-953`, `:1055`, and `:1070`). `SQLiteTransport.send` stores `event.get("state")`, so today `route` rows get `state` NULL. The loop-branch `INSERT` writes `transition=event_type`, and the FTS `_index` content is built from `(loop_name, state, event_type)`.
- **Schema-bump blast radius** (a new `_MIGRATIONS` entry makes `SCHEMA_VERSION` 60, and `test_schema_version_matches_migrations_length` in `test_session_store_schema.py` asserts `SCHEMA_VERSION == len(_MIGRATIONS)`): about 25 hard-coded `SCHEMA_VERSION == 59` / `int(version[0]) == 59` assertions across `test_session_store_schema.py`, `test_session_store_writers.py`, `test_assistant_messages.py`, `test_bug3736_usage_replay_holds.py`; `scripts/little_loops/session_store/schema_manifest.json` (`"loop_events"` at `:1631`; `TestSchemaManifest.test_schema_manifest_matches_checked_in_file` and `test_manifest_schema_version_matches_live_schema_version` fail until it is regenerated); `test_cli_doctor_install_checks.py:458-593` (`SCHEMA_VERSION`-relative checks); `docs/guides/HISTORY_SESSION_GUIDE.md` (`:57` current version, `:78-119` version-to-issue table, `:134` `loop_events` description). `loop_events` is not in `_REBUILD_TABLES` (`session_store/lifecycle.py` ~`:1028`), so no rebuild-replay path needs the new column.
- **Downstream readers are unaffected by the fallback**: ll-logs (`cli/logs.py:2279`), agent_quality (`issue_history/agent_quality.py:440`), quality_regressions (`issue_history/quality_regressions.py:301`), `history_reader/usage.py:694`, `history_reader/runs.py:401`, `cli/ctx_stats.py:941` all read `loop_name` from DB rows, not event dicts. Fixing the writer is what repairs them; none of those modules needs a change. Pre-fix live rows stay NULL (no backfill is specified by the issue; `_backfill_loops` at `writers.py:3547-3572` only seeds from state snapshots).
- **Tests**: hand-fed `loop_name` dicts are in `scripts/tests/test_session_store_writers.py:58-231` (`TestSQLiteTransport`), `test_transport.py:1336-1538` (`TestOTelTransport`), `:287`, `:335` (`wire_transports` via `EventBus`), plus `test_ll_session.py:233-470`, `test_remote_callers_bug3652.py:291-312`, `test_session_store_queries.py:48-98`, `test_history_reader_search.py:242-253`, `test_mcp_server.py:247`, `test_enh_3171_mcp_project_root.py:195`. All must keep passing, which is what the `loop_name` fallback guarantees. `test_fsm_executor.py:3112` (ENH-3345) is the existing proof that the executor stamps `loop`.
- **Documentation**: `docs/reference/EVENT-SCHEMA.md:2066-2067` currently documents the defect ("`loop_name` (falls through to default `"ll-loop"` — real payload key is `loop`)") and must change with the fix; `docs/reference/API.md:11937`, `:11968`, `:11993` show an OTel `loop_start` sample with `"loop_name"` and "Name = `event["loop_name"]`"; `docs/reference/EVENT-SCHEMA.md:2076` and `:2088` describe the `loop_complete` and backfill row mappings and may need the `route` mapping added alongside.

### Conventions in Force
- **Additive nullable column = one appended `_MIGRATIONS` string** holding only `ALTER TABLE <t> ADD COLUMN <c> <TYPE>;`, no `DEFAULT`, no backfill, with a `# vN (ISSUE-ID): ...` comment stating legacy rows stay NULL — evidence: v48 (`ll_version`), v52 (`channels_json`), v54/v55/v57 in `schema.py`. `SCHEMA_VERSION` is a hand-maintained int, not derived. `_apply_migrations` (`schema.py:1620`) splits scripts with `_split_sql_statements`, a plain `;` split, so the SQL and its comment must not contain a `;` inside a literal or comment.
- **Migration tests have three shapes**: fresh-DB `PRAGMA table_info` column check (`TestSchemaV48LlVersionColumns`, `TestSchemaV52ChannelsColumn`), upgrade test via the per-file copy of `_bootstrap_schema_at(db, N-1)` (`test_v51_db_upgrades_gains_channels_column`), and an `ensure_db`-twice idempotency check (`test_v55_host_basis_migration_idempotent_and_null_on_legacy`). `_bootstrap_schema_at` is copy-pasted per file (`test_session_store_schema.py:1203`, `test_session_store_writers.py:1305`, `test_session_store_lifecycle.py:3111`), not shared.
- **Primary-key-then-alternate-key fallbacks are written as `a or b`** with a comment naming why both spellings are accepted — evidence: `writers.py:3127` (`session_id`/`sessionId`), `writers.py:3119` (`file_path`/`issue_file`), `hooks/subagent_stop.py:34`. There is no shared helper; an `or` fallback treats an empty-string `loop` as absent, which the current `str(...) or None` already does for `loop_name`.
- **OTel tests build `TracerProvider` + `SimpleSpanProcessor(InMemorySpanExporter())`**, pass it via `OTelTransport(_tracer_provider=...)`, and look spans up by `.name` — evidence: `TestOTelTransport` fixtures in `test_transport.py`; the class is `skipif(not _HAS_OTEL_SDK)`, so any OTel conformance test must skip the same way. SQLite tests read rows back via `recent(db, kind="loop")` and pin the DB with `LL_HISTORY_DB`/`monkeypatch.setenv`.
- **No existing test drives a real executor into a transport** (contested/absent convention): `FSMExecutor` tests capture events with `event_callback=events.append` (`test_fsm_executor.py:3112`, `test_loop_run_e2e.py`), `test_model_hints.py:931` registers a list sink on `PersistentExecutor.event_bus`, and the CLI loop tests patch `wire_transports` out. Production wiring is `PersistentExecutor.event_bus` + `wire_transports(executor.event_bus, config.events)` (`cli/loop/run.py:683`, `cli/loop/lifecycle.py:752`), with `PersistentExecutor._handle_event` ending in `self.event_bus.emit(event)` (`persistence.py:1182`). A conformance test must also respect the autouse `_guard_real_history_db` / `_guard_real_socket_transport` fixtures in `conftest.py`.
- **Prior art for this defect class**: BUG-3066's docstring on `test_loop_complete_records_mapped_final_status_as_state` ("not a phantom 'outcome' key production never emits") is the same hand-fed-dict failure; `map_final_status` (`persistence.py:147`) was shared precisely so the two transports "cannot drift".

### Files to Modify

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/session_store/writers.py` — `SQLiteTransport.send` loop branch: besides the `loop_name` read, the `_index(...)` call builds `ref=loop_name or ""` and `anchor=f".loops/{loop_name}.yaml"`, so live rows get `ref=""`/`anchor=""` today; reading `loop` makes the FTS `ref`/`anchor` populate too (no code change beyond the key fix) [Agent 2 finding]
- `scripts/little_loops/session_store/schema_manifest.json` — regenerate (do not hand-edit): `loop_events` gains the new column and top-level `schema_version` becomes 60; recipe is the `python -c` snippet in the `TestSchemaManifest` docstring of `scripts/tests/test_session_store_schema.py`, run from `scripts/` [Agent 1/3 finding]
- `docs/guides/HISTORY_SESSION_GUIDE.md` — bump "Current schema version: 59" (`:57`) and append a `| v60 | BUG-3755 |` row to the version table (`:119`); no test enforces it, so it is manual [Agent 3 finding]

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/session_store/queries.py` — `_EXPORT_TABLE_MAP["loop_event"]` projects `*`, so the new column surfaces automatically in `ll-session export` and local-mode `ll-artifact dashboard` snapshots; `_SHAREABLE_COLUMNS` has no `loop_events` key, so the shareable allowlist is untouched [Agent 1/2 finding]
- `scripts/little_loops/session_store/schema.py` — `recent()` via `_KIND_TABLE["loop"]` is `SELECT * FROM loop_events`, so the column also appears in `recent(kind="loop")` rows [Agent 2 finding]
- `scripts/little_loops/session_store/remote_schema.py` — `check_access(write=True)` raises `HistoryUnsupported` when a remote libSQL store is behind `len(_migrations())`, so after the v60 bump remote `SQLiteTransport.send` writes are refused (surfaced via `remote_telemetry.warn_once` in `SQLiteTransport._log_failure`) until `ll-session migrate` runs; the new entry must stay valid under `_split_sql_statements` (Hrana batch) [Agent 2 finding]
- `scripts/little_loops/cli/doctor.py` — structural-drift check uses `_schema_manifest(conn)` / `_reference_manifest_at(len(_MIGRATIONS))`, both derived from `_MIGRATIONS`; no edit needed, verify the doctor passes after regeneration [Agent 1/2 finding]
- `scripts/little_loops/session_store/lifecycle.py` — `_REBUILD_TABLES` excludes `loop_events` and `_REBUILD_SEARCH_KINDS` excludes `"loop"`, so no `REBUILD_DERIVE_VERSION` bump is needed and pre-fix `search_index` rows of kind `loop` (empty `ref`/`anchor`) are left untouched [Agent 2/3 finding]
- `scripts/little_loops/fsm/executor.py` — `FSMExecutor._sub_event_callback` tags child events with `depth` and the child's `loop`; `OTelTransport.send` drops `depth > 0` events but `SQLiteTransport.send` does not, so after the key fix child-loop-named rows land in `loop_events`, which has no `run_id`/`depth` column to tell them apart. Pre-existing, not widened by the new column, but note it so it is not mistaken for a regression [Agent 2 finding]

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- New conformance test module for BUG-3755 (to be created under the tests directory; not yet tracked on main). A draft already exists on branch `fix/BUG-3755-transport-loop-key` (worktree `.claude/worktrees/bug-3755`): `_run_loop` builds a one-state `FSMLoop` with `PersistentExecutor(..., action_runner=_Runner())` and attaches transports with `executor.event_bus.add_transport(...)`, plus `TestSQLiteTransportLiveLoop` and `TestOTelTransportLiveLoop` (the latter `skipif(not _HAS_OTEL_SDK)`). Model on `test_bug3724_mixed_model_pricing.py` in `_run()` [Agent 3 finding]
- `scripts/tests/test_session_store_schema.py` — add `TestSchemaV60...` beside `TestSchemaV52ChannelsColumn`: fresh-DB `PRAGMA table_info(loop_events)` check, upgrade test in `test_v51_db_upgrades_gains_channels_column` shape using `_bootstrap_schema_at(db, 59)`, and an `ensure_db`-twice idempotency check modelled on `test_v55_host_basis_migration_idempotent_and_null_on_legacy` [Agent 3 finding]
- `scripts/tests/test_session_store_schema.py` — about 35 hard-coded `assert SCHEMA_VERSION == 59` / `int(row[0]) == 59` / `int(version[0]) == 59` sites in the `TestSchemaVNN` classes (e.g. `TestSchemaV52ChannelsColumn::test_v51_db_upgrades_gains_channels_column`) must move to 60; `test_schema_version_matches_migrations_length`, `TestSchemaManifest::test_schema_manifest_matches_checked_in_file` and `test_manifest_schema_version_matches_live_schema_version` fail until the bump and regeneration land [Agent 2/3 finding]
- `scripts/tests/test_session_store_writers.py` — `SCHEMA_VERSION == 59` at five sites plus `int(row[0]) == 59` in the first; add a route-row case to `TestSQLiteTransport` (none exists today: no test sends a `route` event or inspects `state` on route rows) [Agent 2/3 finding]
- `scripts/tests/test_assistant_messages.py` — `test_schema_version_is_12` carries a literal `== 59` [Agent 3 finding]
- `scripts/tests/test_bug3736_usage_replay_holds.py` — `TestLegacySeeding::test_migration_creates_holds_table_and_keeps_version_constants` carries a literal `== 59` [Agent 3 finding]
- `scripts/tests/test_session_store_lifecycle.py` — `test_backfill_loops_all_layouts_idempotent` selects `loop_name, state` from `loop_events` and counts `search_index WHERE kind='loop'`; reads existing columns only, should not break, and is the only FTS check for loop events (no test covers live `SQLiteTransport` loop FTS rows, so add `ref`/`anchor` assertions to the conformance test) [Agent 1/3 finding]
- `scripts/tests/test_transport.py` — `TestOTelTransport` and the `wire_transports` tests hand-feed `loop_name` (loop starts at `:1377`-`:1463`, `:287`, `:335`, `:696`); keep passing via the fallback. No test asserts the `"ll-loop"` default span name, so add one for the neither-key case [Agent 2/3 finding]
- `scripts/tests/test_enh3678_rebuild_derive_gate.py` — `TestDeriveFingerprint` should not trip (`loop_events` is outside `_REBUILD_TABLES`, `SQLiteTransport` is a class not a module function), but a new module-level helper in `writers.py` reachable from `rebuild()` would change the digest; keep any name-resolution helper off that path [Agent 3 finding]
- `scripts/tests/test_history_store_chokepoint_gate.py` — bans raw `sqlite3.connect(` outside `session_store/backend.py`; new conformance and migration tests must read rows via `recent(...)`/`connect` helpers, not raw `sqlite3.connect` [Agent 3 finding]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/EVENT-SCHEMA.md` — section `### SQLiteTransport` ("Recognises a closed set of event types only") says nothing about which payload key supplies loop identity; add the `loop`-then-`loop_name` rule and the `route` mapping (`from` → `state`, `to` → new column) in `OTel Transport Field Mapping` alongside the existing `loop_complete` row [Agent 2 finding]
- `docs/ARCHITECTURE.md` — "history.db schema versions" table ends at v54 (v55-v59 already absent), so v60 is a gap-fill not an append; the `ensure_db()` rows (`v1–v34`, `:771`, `:796`, `:867`) and the "`PRAGMA user_version` migrations" intro line are already stale. Pre-existing drift, update only if the pass touches this table [Agent 2 finding]
- `docs/reference/API.md` — `little_loops.session_store` header says "Current schema version: **45**" (`:10198`) and the code-block comment `SCHEMA_VERSION, # 45` is stale (actual 59); touch alongside the OTel `loop_start` sample fix [Agent 2 finding]

### Configuration

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/package_data.py` — already lists `("session_store", "schema_manifest.json")` for `ll-verify-package-data`; no edit needed, listed so the regenerated file is not assumed unregistered [Agent 1/2 finding]

## Program Design

### Types

- `event["loop"]: str` — loop name stamped by `FSMExecutor._emit` (fallback key: `event["loop_name"]`)
- `loop_events.to_state: TEXT NULL` — new nullable column recording the `to` of `route` events

### Signatures

- `SQLiteTransport.send(self, event: dict[str, Any]) -> None` — read name via `event.get("loop") or event.get("loop_name")`; for `route` events store `from` as `state` and `to` in the new column
- `OTelTransport._handle_loop_start(self, event: dict[str, Any]) -> None` — span named from `loop`, falling back to `loop_name`, then `"ll-loop"`
- `OTelTransport._handle_loop_resume(self, event: dict[str, Any]) -> None` — same name resolution

### Call Path

`FSMExecutor._emit` -> `PersistentExecutor._handle_event` -> `EventBus.emit` -> `SQLiteTransport.send` / `OTelTransport.send`; schema change via `_MIGRATIONS` in `session_store/schema.py` applied by `_apply_migrations`.

## Implementation Steps

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-10-06 — based on codebase analysis:_

1. Both transports resolve the loop name from `loop`, falling back to `loop_name`, so `loop_events.loop_name` is non-NULL for executor-emitted events and OTel loop spans carry the loop's name (the `"ll-loop"` default remains only when neither key is present). Verified by tests in `test_session_store_writers.py` and `test_transport.py` using `loop`-keyed events while the existing `loop_name`-keyed tests still pass unchanged.
2. `route` events persist `from` as `state` and `to` in a new nullable `loop_events` column added as one appended `_MIGRATIONS` entry (no DEFAULT, no backfill; legacy rows read NULL). Non-`route` events leave the new column NULL. Verified by fresh-DB column, upgrade-from-previous-version, and idempotency tests in the three shapes above.
   > ⚠ Superseded — about 42 `== 59` sites, not ~25; see Tests
3. Everything pinned to the schema version moves together: `SCHEMA_VERSION`, the ~25 hard-coded `== 59` assertions, `schema_manifest.json` (regenerated, not hand-edited), and `HISTORY_SESSION_GUIDE.md`. Verified by `python -m pytest scripts/tests/test_session_store_schema.py scripts/tests/test_cli_doctor_install_checks.py -q`.
4. A conformance test drives a real `PersistentExecutor` (with `MockActionRunner`) whose `event_bus` is wired to `SQLiteTransport` and, when `opentelemetry-sdk` is present, `OTelTransport` with an in-memory exporter, then asserts non-NULL `loop_name`, a span named after the FSM, and a `route` row carrying both ends of the transition; hand-built `{"loop_name": ...}` dicts are not the input. It must pin the history DB (`LL_HISTORY_DB`) and not touch the real `.ll/` socket/DB.
5. `EVENT-SCHEMA.md:2066-2067` and `API.md:11937-11993` stop describing the `loop_name`-default behavior as current; the `route` → `state`/new-column mapping is documented. Verified by `test_wiring_reference_docs.py` and the docs-audience gate still passing.
6. Full gate: `python -m pytest scripts/tests/test_transport.py scripts/tests/test_session_store_writers.py scripts/tests/test_fsm_persistence.py -q`, then `python -m pytest scripts/tests/` exits 0.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Start from branch `fix/BUG-3755-transport-loop-key` (worktree `.claude/worktrees/bug-3755`, commits `256ab0ad1` and `b37b20a05`): it already carries a `loop`-key fix, a `loop_events.to_state` column (schema v60), and a draft `test_bug3755_transport_loop_identity.py`. Settle the column name as `to_state` (the issue only says "a new nullable column") and reconcile that branch's diff against this issue's acceptance criteria rather than re-deriving it
- Update `scripts/little_loops/session_store/schema_manifest.json` — regenerate with the `TestSchemaManifest` docstring recipe, run from `scripts/`
- Update `scripts/tests/test_session_store_schema.py`, `test_session_store_writers.py`, `test_assistant_messages.py`, `test_bug3736_usage_replay_holds.py` — move the hard-coded `== 59` assertions (about 42 sites) to 60
- Add `TestSchemaV60...` to `scripts/tests/test_session_store_schema.py` — fresh-DB column, upgrade-from-59, and idempotency shapes
- Add a `route`-row test to `TestSQLiteTransport` in `scripts/tests/test_session_store_writers.py` and a neither-key `"ll-loop"` span-name test to `TestOTelTransport` in `scripts/tests/test_transport.py`
- Update `docs/guides/HISTORY_SESSION_GUIDE.md` — `:57` version and a `v60` table row
- Update `docs/reference/EVENT-SCHEMA.md` (`### SQLiteTransport`, `OTel Transport Field Mapping`) and `docs/reference/API.md` (OTel `loop_start` sample)
- Verify `ll-session migrate` guidance for remote libSQL stores is surfaced in the release notes, since `remote_schema.check_access(write=True)` refuses writes until a remote store is migrated

## Impact

- **Priority**: P0 - every live loop telemetry row/span loses its loop identity, skewing ll-logs, agent_quality, and quality_regressions metrics built on `history.db`
- **Effort**: Small - key lookup change in two transports plus one additive nullable column migration and a conformance test
- **Risk**: Low - additive column, fallback to `loop_name` preserves older-payload behavior
- **Breaking Change**: No

## Related

- ENH-2463 (done) noted that `loop_complete` once lacked `loop_name`; that predates ENH-3345's stamping and is a different gap.

Verified against main 4c6be4c26 on 2026-10-05.

## Verification Notes

Verdict at time of check: **CLAIMS_OUTDATED** (correction below applied in the same pass, so the issue as it now reads is up to date — this section is a record of what was wrong and fixed, not an outstanding action item)

- Tests section: the new conformance test module was cited by a repo-relative path as if it already existed. It is not git-tracked on main (the draft lives only on the fix branch), so the entry now describes it as a module to be created.

Scope: `--from-evidence` pass, only the claim listed in `verify_evidence` was re-checked.

## Status

**Open** | Created: 2026-10-05 | Priority: P0


## Session Log
- `/ll:confidence-check` - 2026-10-06T07:13:09 - `7e8c728c-f090-4a58-949a-dd0ab4ad88f5.jsonl`
- `/ll:verify-issues` - 2026-10-06T07:11:16 - `c174406e-cc5e-42ca-bfb0-9612775f49e7.jsonl`
- `/ll:verify-issues` - 2026-10-06T07:09:49 - `646dfd23-77c6-4244-9c3b-15d7fa5df5f7.jsonl`
- `/ll:verify-issues` - 2026-10-06T07:08:28 - `01c29346-c7cf-4f83-901e-c969db0c4749.jsonl`
- `/ll:wire-issue` - 2026-10-06T07:06:46 - `e48af9aa-f26d-410f-b026-8068420e9af9.jsonl`
- `/ll:refine-issue` - 2026-10-06T06:57:45 - `57aa3271-f5d2-4032-bf1b-9f6c15c97341.jsonl`
- `/ll:format-issue` - 2026-10-06T06:51:20 - `6c502106-ed87-456c-821b-ba3029111722.jsonl`
