---
id: BUG-3715
type: BUG
title: rebuild() unconditionally wipes summary_nodes including irreplaceable retention
  summaries
priority: P3
status: open
relates_to:
- ENH-3698
- ENH-3666
- ENH-3678
discovered_by: ll-issues-create
discovered_date: '2026-10-03'
captured_at: '2026-10-03T17:46:14Z'
verify_verdict: VALID
confidence_score: 100
outcome_confidence: 75
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 18
---

# BUG-3715: rebuild() unconditionally wipes summary_nodes including irreplaceable retention summaries

## Summary

`rebuild()` (`little_loops.session_store.lifecycle`) wipes every table in `_REBUILD_TABLES` with an unconditional `DELETE`; only `usage_events` has a row predicate in `_REBUILD_TABLE_PREDICATES`. `summary_nodes` (and `summary_spans`) are therefore fully deleted, including `kind='retention'` rows written by `compact()` whose source `raw_events` rows `prune()` already deleted. Those rows cannot be re-derived, so any rebuild on a pruned store silently loses them. Derived rows for pruned periods are likewise deleted and never replayed.

## Current Behavior

- Any rebuild (SessionStart auto-rebuild after a `REBUILD_DERIVE_VERSION` bump, or manual `ll-session rebuild`) deletes all `summary_nodes`/`summary_spans`, including irreplaceable `kind='retention'` summaries.
- The hook worker passes `config=None`: summaries are wiped and never regenerated.
- `ll-session rebuild` loads the project config, so with `history.compaction.enabled` it re-summarizes every session via blocking host-LLM calls inside the single `BEGIN IMMEDIATE` transaction (lock hold scales with LLM latency x sessions; one failure rolls everything back). The two paths produce different results.

## Expected Behavior

- `rebuild()` preserves `kind='retention'` summary rows (and their spans, handled consistently) whose source `raw_events` were pruned; only re-derivable kinds are wiped and replayed.
- Hook and manual rebuild paths agree on what happens to summaries, and LLM summarization does not run inside the write transaction (or the divergence is explicitly documented).

## Acceptance Criteria

- [ ] After `compact(db, config, and_prune=True)` on a store with old `raw_events`, `rebuild(db)` leaves every `summary_nodes` row with `kind='retention'` intact (same count and `content`).
- [ ] After that rebuild, no `summary_spans` row that referenced a retained node is lost, and no orphan `summary_spans` row is left for a wiped node.
- [ ] Re-derivable kinds (`kind='condensed'` and other non-retention rows) are still wiped and replayed, so `rebuild()` stays idempotent (two consecutive runs yield identical `summary_nodes`).
- [ ] `ll-session rebuild` (config loaded) and the hook-spawned `--rebuild` worker (`config=None`) leave the same retention rows; any remaining difference for re-derivable summaries is documented in `docs/reference/CLI.md`.
- [ ] No host-LLM call runs while the `BEGIN IMMEDIATE` transaction in `rebuild()` is held, or the divergence is explicitly documented in the `rebuild()` docstring.
- [ ] A regression test in `scripts/tests/test_session_store_lifecycle.py` (`TestRebuild`) covers a pruned+compacted store surviving `rebuild()`.
- [ ] If ENH-3698 has landed, remove its temporary derive-version equality pin citing BUG-3715 only in the change that proves summary preservation; retain the permanent frozen legacy literal/digest pins and follow the derivation fingerprint bump rule.
- [ ] Remove ENH-3698's interim retention-loss caveat from SessionStart feedback, doctor guidance, and end-user docs once preservation is proven. Keep the separate write-lock and applicable LLM compaction warnings while those behaviors remain.

## Motivation

`REBUILD_DERIVE_VERSION` bumps make every store rebuild once at the next SessionStart, so this wipe is a hard precondition for any future bump: on a store that has run `compact(and_prune=True)`, the source `raw_events` for retention summaries no longer exist, so the loss is permanent and silent. No derive bump has landed yet, so the bug is latent today.

## Proposed Solution

Add a predicate to `_REBUILD_TABLE_PREDICATES` excluding `kind='retention'` from the `summary_nodes` wipe, with `summary_spans` handled consistently; add tests for a pruned+compacted store surviving `rebuild()`.

## Program Design

### Types

- `_REBUILD_TABLE_PREDICATES: dict[str, str]` — extended with `summary_nodes` and `summary_spans` row predicates alongside the existing `usage_events` entry

### Signatures

- `rebuild(db: Path | str = DEFAULT_DB_PATH, *, config: dict | None = None, max_sessions: int | None = None) -> dict[str, int]` — unchanged signature; wipe loop honors the new predicates
- `_compact_sessions(conn, config, *, max_sessions, db)` — existing summarizer, called from `rebuild()`; its LLM calls must move out of the write transaction or the divergence gets documented

### Call Path

`session_start` hook -> `rebuild_needed` -> spawned `--rebuild` worker -> `rebuild` -> `_compact_sessions`

`ll-session rebuild` -> `little_loops.cli.session.rebuild` -> `rebuild` -> `_compact_sessions`

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-10-03 — based on codebase analysis:_

- **Call Path correction**: the hook path is `hooks/session_start.py:handle` → `rebuild_needed` → detached `cli/backfill_worker.py:main` → `lifecycle.backfill_incremental(also_rebuild=True)` → `lifecycle.rebuild(config=None)` → `_compact_sessions` (returns 0 when compaction disabled). The manual path is `cli/session.py` `rebuild` branch → `lifecycle.rebuild(config=<loaded>)`.
- **Decision Rules**: the discriminator for "irreplaceable" is `summary_nodes.kind`; `kind` is `NOT NULL`. Existing predicate convention is a NULL-safe `IS NOT` fragment (`channel IS NOT 'live'`, BUG-3530). Table order in `_REBUILD_TABLES` puts `summary_nodes` before `summary_spans`, so any `summary_spans` predicate evaluates against an already-narrowed `summary_nodes`. Retention nodes have no spans, so the `summary_spans` requirement is that no span row survives pointing at a wiped node.

## Integration Map

### Files to Modify
- `scripts/little_loops/session_store/lifecycle.py` — `_REBUILD_TABLE_PREDICATES` (add `summary_nodes` / `summary_spans` predicates excluding `kind='retention'`), `rebuild()` docstring and wipe loop, comment above `_REBUILD_TABLES`

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/session.py` — `ll-session rebuild` and `backfill --rebuild` call `rebuild()`
- `scripts/little_loops/hooks/session_start.py` — appends `--rebuild` to the worker argv when `rebuild_needed()` reports `stale`
- `scripts/little_loops/session_store/usage_refresh.py`, `sessions.py`, `qwen.py`, `schema.py` — reference `rebuild`

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/session_store/lifecycle.py` — `backfill()` and `backfill_incremental()` tails call `rebuild(..., also_rebuild=True)` then `counts.update(rebuild(...))`; both inherit the new wipe predicates with no edit, and a new key in `rebuild()`'s `counts` would change their "Backfilled N rows" sums, so add none [Agent 1/2 finding]
- `scripts/little_loops/session_store/lifecycle.py` — `compact()` writes `kind='retention'` rows and sets `raw_events.summary_node_id` in `compact()`; `compacted=1` rows keep `summary_node_id` pointing at ids the current wipe deletes (the dangling-pointer symptom the fix must close) [Agent 1/2 finding]
- `scripts/little_loops/session_store/__init__.py` — re-exports `rebuild`, `_REBUILD_TABLES`, `_compact_sessions`; `_REBUILD_TABLE_PREDICATES` is NOT re-exported and has no importer outside `lifecycle.py`, so extending the dict needs no export change [Agent 1 finding]
- `scripts/little_loops/cli/session.py` — `main_session()` `refresh` branch calls `rebuild(args.db)` with no config (follows the hook path, `config=None`); `backfill --rebuild` passes the loaded config (follows the manual path) — both fall under the hook-vs-manual parity criterion [Agent 1/2 finding]
- `scripts/little_loops/cli/session.py` — `_parse_args()` `rebuild_parser` help (`Wipe+re-derive the JSONL-derived cache tables from raw_events`) and its `--config` help; neither mentions retention summaries or the config-dependent summary regeneration, so update if the divergence is documented there [Agent 2 finding]
- `scripts/little_loops/cli/history.py` — `main_history()` `root` branch selects `summary_nodes WHERE session_id IS NULL AND parent_id IS NULL ORDER BY level DESC LIMIT 1` with no `kind` filter; `compact()` inserts retention rows with the raw event's `session_id`, which can be NULL, so a surviving NULL-session retention node is a candidate "root" when no condensed root exists (advisory: confirm no behavior change in practice) [Agent 2 finding]
- `scripts/little_loops/history_reader/formatting.py`, `history_reader/summary_dag.py`, `compaction/result.py` — read the summary tables; they filter on `kind` or traverse from leaf/condensed nodes, so surviving childless retention rows do not reach them; `session_store/queries.py` only lists the summary tables in its export map (no edit) [Agent 1/2 finding]
- `scripts/little_loops/session_store/usage_refresh.py` — `refresh_raw_events` skips a source whose `raw_events` row has `compacted` or `summary_node_id` set (`compacted_source`); reads the same column the fix keeps valid, no edit [Agent 2 finding]

### Similar Patterns
- `_REBUILD_TABLE_PREDICATES["usage_events"] = "channel IS NOT 'live'"` (BUG-3530) — same pattern: preserve rows that cannot be replayed from `raw_events`

### Tests
- `scripts/tests/test_session_store_lifecycle.py` — `TestRebuild` (add the pruned+compacted-store case); compact/retention tests near `_RETENTION_CFG`
- `scripts/tests/test_ll_session.py` — `ll-session rebuild` CLI tests
- `scripts/little_loops/session_store/rebuild_fingerprint.json` — derivation fingerprint guarded by a fingerprint test (named in the `REBUILD_DERIVE_VERSION` comment; locate it before editing); check whether this change requires a `REBUILD_DERIVE_VERSION` bump (do not bump before ENH-3698)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_session_store_lifecycle.py` — add the new case to `TestRebuild`; closest templates: `test_rebuild_does_not_touch_out_of_scope_tables` (preserve a table), `TestBackfillUsageEvents.test_rebuild_preserves_live_usage_rows` (run `rebuild(db)` twice, compare for idempotence), `test_rebuild_replaces_rollout_channel_rows` (non-preserved rows still wiped — analogue: seed a `kind='leaf'`/`'condensed'` node and assert it is wiped), `test_rebuild_failure_rolls_back_usage_delete` (patch `lifecycle._backfill_sessions` to raise; assert the retention node and a leaf node both survive the rollback) [Agent 3 finding]
- `scripts/tests/test_session_store_lifecycle.py` — `TestCompact` seeding: `_RETENTION_CFG` plus `min_project_age_days: 0` / `min_db_size_mb: 0` (or `TestPrune._GATES_OPEN`) and `_insert_old_raw_event` for `compact(and_prune=True)`; `compact()` is deterministic, so no LLM stub is needed unless the test calls `rebuild(db, config=...)` with `history.compaction.enabled`, which requires patching `little_loops.session_store.subprocess.run` with `_make_completed`/`_llm_response` [Agent 3 finding]
- `scripts/tests/test_session_store_schema.py` — `_insert_summary_node(conn, kind, session_id, ts_start, ts_end)` and `_insert_raw_event(conn, session_id, summary_node_id)` are the only existing helpers that build a retention node linked from `raw_events.summary_node_id`; the dangling-pointer assertion in the BUG-3241 repair test (`summary_node_id NOT IN (SELECT id FROM summary_nodes)` returns 0) is the template for the post-rebuild check. Copy the helpers (the lifecycle file's `TestCompact._insert_old_raw_event` sets no `summary_node_id`) [Agent 3 finding]
- `scripts/tests/test_enh3678_rebuild_derive_gate.py` — `TestDeriveFingerprint::test_digest_matches_snapshot` fails on any non-comment edit to the `rebuild()` body or `_compact_sessions`/`_compact_session_conn`; a `_REBUILD_TABLE_PREDICATES`-only edit does not change the digest (the dict is not in `_CONSTANTS`), but the wipe loop edit will. `TestDeriveFingerprint::test_resolved_function_set_matches_snapshot` asserts `len(resolved) == 23`, so do not add a module-level helper called from `rebuild()` (use the dict entry or inline SQL). `TestFrozenLegacyPins::test_lockstep_derive_version_not_bumped_before_enh_3698` forbids a `REBUILD_DERIVE_VERSION` bump [Agent 2/3 finding]
- `scripts/tests/test_ll_session.py` — `TestRebuildSubcommand` tests patch `little_loops.cli.session.rebuild` and are insulated from the lifecycle change; they assert only `"messages=3"` / `'"tools"'`. Update only if the `rebuild` success line or `counts` keys change (they should not) [Agent 2/3 finding]
- `scripts/tests/test_session_store_lifecycle.py` — `TestCompactSession::test_backfill_compaction_disabled_by_default` (asserts `counts["summaries"] == 0` and empty `summary_nodes` after a fresh rebuild) and `test_backfill_with_compaction_enabled` stay valid; re-run to confirm no regression [Agent 3 finding]
- Test gaps to cover in the new tests (no existing coverage): no `compact(and_prune=True)` → `rebuild()` → read `summary_nodes` test; no orphan-`summary_spans` check (hand-insert a span row pointing at a retention id, since real retention nodes have none); no dangling `raw_events.summary_node_id` check after `rebuild()`; no hook (`config=None`, via `backfill_incremental(..., also_rebuild=True)`) vs CLI (`config`) retention parity test; a second `compact()` after `rebuild()` must not duplicate retention rows (`idx_summary_nodes_retention_dedup`) [Agent 3 finding]

### Documentation
- `docs/reference/CLI.md` — `ll-session rebuild` entry: note that retention summaries survive a rebuild

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md` — `ll-session rebuild` entry, paragraph after the "`rebuild` flags" list: "Wipes and re-derives ... `summary_nodes`/`summary_spans`" must gain the retention exception (mirror the `usage_events` live-row wording) and the hook-vs-manual summary divergence in `ll-session rebuild` [Agent 2 finding]
- `docs/reference/API.md` — `### raw_events / rebuild / compact` section, in the `rebuild` paragraph ("Wipes `tool_events`, ... `summary_nodes`, `summary_spans`, and the `search_index` rows"): add the retention exception; the adjacent `compact` paragraph (`kind='retention'` nodes, `summary_node_id`) should state they survive `rebuild()` [Agent 2 finding]
- `docs/reference/API.md` — `ll-session` subcommand bullet list, `rebuild` bullet ("Wipe+re-derive the JSONL-derived cache tables"): optional one-clause note [Agent 2 finding]
- `docs/ARCHITECTURE.md` — schema table v19 `raw_events` row: "`ll-session rebuild` wipes and re-derives ... `summary_nodes`/`summary_spans`" (the v53 row's `usage_events` live-row exception is the wording precedent) [Agent 2 finding]
- `docs/guides/HISTORY_SESSION_GUIDE.md` — the "Since ENH-2581, session JSONL lands in `raw_events`" callout in `Session JSONL storage`: "`rebuild` wipes and re-derives those tables" lists `summary_nodes`/`summary_spans`; the table row for `summary_nodes` / `summary_spans` ("Populated when `history.compaction.enabled: true`") should note retention rows are preserved [Agent 2 finding]

### Configuration
- N/A (`history.compaction.enabled` and `analytics.retention.raw_event_max_age_days` are read, not changed)

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-10-03 — based on codebase analysis:_

- **Callers of `lifecycle.rebuild` (verified, config passed)**: `cli/session.py` `rebuild` branch (loaded config); `cli/session.py` `refresh --rebuild` (none); `lifecycle.backfill(also_rebuild=True)` and `lifecycle.backfill_incremental(also_rebuild=True)` tails (caller's config); `ll-session backfill --rebuild` (loaded config); hook worker `cli/backfill_worker.py:main` via `hooks/session_start.py:handle` (none). `rebuild_needed()`, `RebuildState`, and `usage_refresh.py` mentions are not callers.
- **Other readers of the summary tables that a partial wipe must leave consistent**: `history_reader/formatting.py` (recursive CTEs over `parent_id`, joins `summary_spans`), `history_reader/summary_dag.py:condensed_nodes_for_issue`, `compaction/result.py`, `cli/history.py` root lookup (no `kind` filter), `session_store/queries.py` export map (all kinds). No FTS kind and no triggers exist for the summary tables (`_KINDLESS_TABLES` in `schema.py`).
- **Dedup index**: `idx_summary_nodes_retention_dedup` is unique on `(session_id, ts_start, ts_end)` where `kind='retention'`; preserved retention rows keep `compact()` idempotent.
- **Fingerprint guard (constraint)**: `scripts/tests/rebuild_fingerprint.py:compute_fingerprint` hashes the normalized body of `rebuild()` and the other 22 reachable functions, but not `_REBUILD_TABLE_PREDICATES` (only `_REBUILD_TABLES` and `_REBUILD_SEARCH_KINDS`). Any non-comment edit to `rebuild()` or `_compact_sessions` therefore changes the digest and fails `test_enh3678_rebuild_derive_gate.py::TestDeriveFingerprint::test_digest_matches_snapshot`; while `REBUILD_DERIVE_VERSION` equals `_FROZEN_LEGACY_DERIVE_VERSION` (`enh3678-v1`), the permitted response is regenerating `rebuild_fingerprint.json` without a bump (`TestFrozenLegacyPins.test_lockstep_derive_version_not_bumped_before_enh_3698` enforces the lockstep). ENH-3698 names this bug as a precondition on any bump.
- **Docs repeating the wipe list** (all state `summary_nodes`/`summary_spans` are wiped and re-derived): `docs/reference/CLI.md` `ll-session rebuild` entry, `docs/reference/API.md` (rebuild section), `docs/ARCHITECTURE.md` v19 row, `docs/guides/HISTORY_SESSION_GUIDE.md`. The `usage_events` live-row exception is already documented in API.md, ARCHITECTURE.md (v53 row), and HISTORY_SESSION_GUIDE.md but not in the CLI.md rebuild entry.

_Added by `/ll:refine-issue` — 2026-10-03 — based on codebase analysis:_

- **Test conventions in force**: regression tests for a rebuild wipe rule live inside the existing class with a `BUG-NNNN:` docstring (evidence: `TestBackfillUsageEvents.test_rebuild_preserves_live_usage_rows`, which runs `rebuild(db)` twice and compares for idempotence, and `test_rebuild_failure_rolls_back_usage_delete`, which patches `lifecycle._backfill_sessions` to raise and asserts rollback). Retention compaction is deterministic and needs no LLM stub (`TestCompact`: `_RETENTION_CFG`, `_insert_old_raw_event`, and the `min_project_age_days`/`min_db_size_mb` gates set to 0 for `and_prune=True`). `rebuild(db)` with no config skips `_compact_sessions`; a test calling `rebuild(db, config=...)` with compaction enabled must patch `little_loops.session_store.subprocess.run` (the live-spawn guard in `scripts/tests/conftest.py` fails real host spawns).
- **Coverage gap confirmed**: no existing test runs `compact()`/`prune()` then `rebuild()` while reading `summary_nodes` (nearest is `TestFts5LeakFixed`, which checks only message and search counts), and none seeds retention plus leaf/condensed nodes before a rebuild.

## Implementation Steps

1. Add predicates to `_REBUILD_TABLE_PREDICATES` so `summary_nodes` keeps `kind='retention'` rows and `summary_spans` keeps spans of retained nodes.
2. Decide and implement (or document) the hook vs. manual summary divergence and LLM-in-transaction behavior in `rebuild()`.
3. Add a `TestRebuild` regression test: build store, `compact(and_prune=True)`, `rebuild(db)`, assert retention rows survive and rebuild is idempotent.
4. Update `rebuild()` docstring and `docs/reference/CLI.md`; run `python -m pytest scripts/tests/test_session_store_lifecycle.py`.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Regenerate `scripts/little_loops/session_store/rebuild_fingerprint.json` in the same commit as any `rebuild()` body / `_compact_sessions` edit, WITHOUT bumping `REBUILD_DERIVE_VERSION`: `python -c "import sys; sys.path.insert(0, 'scripts'); from pathlib import Path; from tests.rebuild_fingerprint import regenerate; regenerate(Path('.'))"` (use the interpreter that runs pytest); `current_digest` then differs from `frozen_legacy_digest`, which is the intended recorded gap
- Keep the resolved function set at 23: express the retention exception as a `_REBUILD_TABLE_PREDICATES` entry (or inline SQL in the wipe loop), not a new helper called from `rebuild()`, or `test_resolved_function_set_matches_snapshot` fails
- Do not add a key to `rebuild()`'s `counts` dict — `cli/session.py` `rebuild` and `backfill` branches `sum(counts.values())` for the "Rebuilt/Backfilled N rows" totals and `refresh` emits it as `rebuild_counts`
- Handle the dangling `raw_events.summary_node_id` for `compacted = 1` rows in the same wipe: preserving retention rows covers retention-linked pointers; confirm no pointer targets a wiped `leaf`/`condensed` node
- Update `docs/reference/CLI.md`, `docs/reference/API.md` (rebuild + compact paragraphs), `docs/ARCHITECTURE.md` (v19 row), `docs/guides/HISTORY_SESSION_GUIDE.md` (callout + table row) so none still says `rebuild` wipes all `summary_nodes`/`summary_spans`
- Update `cli/session.py` `rebuild_parser` help only if the hook-vs-manual divergence is documented in CLI help text
- Run the fingerprint gate with the lifecycle tests: `python -m pytest scripts/tests/test_session_store_lifecycle.py scripts/tests/test_enh3678_rebuild_derive_gate.py scripts/tests/test_session_store_schema.py scripts/tests/test_ll_session.py`

## Impact

- **Priority**: P3 - latent: no derive bump has landed yet, but it is a hard precondition on any `REBUILD_DERIVE_VERSION` bump (data loss on pruned stores)
- **Effort**: Small-Medium
- **Risk**: Low-Medium

## Steps to Reproduce

1. Build a store with `raw_events`, run `compact(and_prune=True)` so `kind='retention'` rows exist and the source rows are pruned.
2. Run `rebuild(db)`.
3. Observe the `kind='retention'` rows are gone and cannot be recovered.

## Related

ENH-3698 (size gate; its review surfaced this), ENH-3666 (restructuring `rebuild()`), ENH-3678.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-10-03 | Priority: P3


## Session Log
- `/ll:confidence-check` - 2026-10-03T18:18:32 - `3953e906-c2cf-43f6-92f4-86a32eec7a1b.jsonl`
- `/ll:verify-issues` - 2026-10-03T18:17:24 - `d567e7da-49d1-4d07-b0d8-a9ed32fbd7f3.jsonl`
- `/ll:wire-issue` - 2026-10-03T18:14:21 - `ec3229f4-6ba4-4dad-bae3-1bd17c071032.jsonl`
- `/ll:refine-issue` - 2026-10-03T18:07:17 - `a59b3881-619f-461a-a4fb-79f07d2aebe7.jsonl`
- `/ll:format-issue` - 2026-10-03T18:01:26 - `6b27c7de-5d33-4c17-b3b7-3a7c6b15361b.jsonl`
- `/ll:capture-issue` - 2026-10-03T17:46:28 - `32f52444-a659-4ef8-933a-2361ae6c6aff.jsonl`

## Root Cause

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-10-03 — based on codebase analysis:_

- **File**: `scripts/little_loops/session_store/lifecycle.py` — `rebuild()` wipe loop plus `_REBUILD_TABLE_PREDICATES` (only `usage_events` is keyed; defined near `_REBUILD_TABLES`) and the comment above `_REBUILD_TABLES`.
- **Cause**: `_REBUILD_TABLES` lists `summary_nodes` then `summary_spans`; the loop issues a bare `DELETE FROM <table>` for any table without a predicate, so both are emptied unconditionally inside the single `BEGIN IMMEDIATE` transaction. `_compact_sessions` (same transaction) re-creates only `leaf`/`condensed` nodes, and only when `history.compaction.enabled` is true (default false). No code path in `rebuild()` writes `kind='retention'` — only `compact()` does, from `raw_events` rows that `prune()` later deletes.
- **`kind` values and re-derivability**: `leaf` and `condensed` (level 0 per session, level 1+ cross-session with `session_id` NULL) are re-derivable from replayed `message_events`; `retention` is not.
- **`summary_spans` facts that bound the fix**: rows are written only for `leaf` nodes (`_compact_session_conn`); retention nodes never have span rows. The only live reference into a retention node is `raw_events.summary_node_id`. FKs on both summary tables are decorative (no `ON DELETE`, `PRAGMA foreign_keys` never enabled), so nothing cascades — orphan handling is entirely the wipe's responsibility.
- **Second symptom of the same wipe**: `compact()` selects only `compacted = 0` rows, so `raw_events` rows already marked `compacted = 1` keep a `summary_node_id` that dangles after the wipe, even on stores that have not been pruned. Ids come from an `AUTOINCREMENT` column, so a re-created row would not reuse the old id.
- **Hook vs manual divergence is conditional**: the SessionStart worker reaches `rebuild()` via `cli/backfill_worker.py:main` → `backfill_incremental(..., also_rebuild=True)` with no config, so `_compact_sessions` returns 0. `ll-session rebuild` loads config (falling back to `None` on read/parse error), and `ll-session refresh --rebuild` passes none. The two paths differ only for stores with `history.compaction.enabled` true.
- **Latent hazard inside the transaction**: `_compact_sessions` calls `_maybe_soft_threshold_summary`, which starts a background thread with its own connection while the rebuild transaction is open.
