---
id: BUG-3761
title: rebuild() wipes hook-written tool_events and user_corrections rows that replay
  cannot regenerate
type: BUG
priority: P1
status: open
discovered_date: '2026-10-06'
labels:
- history
- telemetry
- data-loss
testable: true
decision_needed: false
reconcile_attempted: true
relates_to:
- BUG-3530
- BUG-3715
- BUG-3766
- ENH-3747
confidence_score: 95
outcome_confidence: 71
score_complexity: 10
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 18
risk_factors:
- id: minor-open-impl-choices
  domain: outcome
  criterion: ambiguity
  description: Temp relation vs materialized CTE and inline vs helper (23-function
    pin) left to implementation
- id: rebuild-lock-window
  domain: outcome
  criterion: complexity
  description: Survivor-key materialization extends the BEGIN IMMEDIATE window against
    the 5s hook busy timeout; needs measurement
- id: shared-rebuild-edit-coordination
  domain: outcome
  criterion: change_surface
  description: ENH-3747 and BUG-3766 edit the same search deletion and derive-version
    bump; patches must be combined without losing exclusions
- id: survivor-deletion-novel-pattern
  domain: readiness
  criterion: architecture_compliance
  description: Survivor-aware search deletion deviates from simple predicate precedent
    used for usage/retention rows
- id: survivor-search-key-normalization
  domain: outcome
  criterion: complexity
  description: NULL-safe, type-normalized FTS survivor-key matching (strip semantics,
    NULL/empty session, affinity) is new mechanism beyond predicate precedent
- id: wide-test-doc-fanout
  domain: outcome
  criterion: complexity
  description: About 17 change sites across source, fingerprint JSON, six test files
    and four docs
---

## Summary

`rebuild()` deletes every row in `tool_events` and `user_corrections`, then replays them from `raw_events`. Live hooks also write both tables directly without a raw event. Rebuild therefore permanently discards live byte/cache/latency/MCP measurements and live correction provenance, even when replay recreates a superficially similar invocation or correction.

Manual `ll-session rebuild`/refresh and the automatic derive-version path share this wipe. A `REBUILD_DERIVE_VERSION` mismatch schedules replay automatically for eligible stores at or below `REBUILD_AUTO_MAX_BYTES` (64 MiB); larger stores receive a pending notice. BUG-3530 and BUG-3715 already preserve non-replayable usage/retention rows with `_REBUILD_TABLE_PREDICATES`; this issue applies that pattern to tools and corrections and their existing search entries.

## Steps to Reproduce

Use a disposable local store; rebuilding a production store on the affected code destroys live telemetry.

1. Enable analytics in a temporary project's `.ll/ll-config.json`. Drive `scripts/little_loops/hooks/post_tool_use.py` — `handle()` with a tool payload carrying `session_id`, input/response, and started/completed timing. Call `record_correction(db, session_id, 'no, actually use pytest', 'user_prompt_submit')`.
2. Optionally ingest assistant tool-use and user-correction transcripts through `backfill_raw_events()`. Remove the source JSONL after ingestion to confirm replay uses stored raw events.
3. Snapshot base rows, including IDs and every telemetry field, and existing kind `tool`/`correction` `search_index` rows. Run `rebuild(db)` twice.
4. The live tools and corrections disappear. Replay may create rows with NULL byte/latency/cache/outcome fields and `source='backfill'`; existing live search anchors disappear as well. Without raw counterparts, no replacement is produced.

The original incident report describes 2,396 hook tool rows and two corrections lost in one rebuild of a 1.1 GB store, recovered from a backup. Its per-tool breakdown did not sum to the stated total and has been removed; those historical counts are reported evidence, not independently remeasured here. The disposable reproduction above independently confirms the defect.

## Current Behavior

- `scripts/little_loops/session_store/lifecycle.py` — `_REBUILD_TABLES` includes both tables. `rebuild()` applies a wipe predicate only when `_REBUILD_TABLE_PREDICATES` has an entry; neither table has one.
- `scripts/little_loops/hooks/post_tool_use.py` — `handle()` writes integer `bytes_in` and `bytes_out` on every successful live write, including empty inputs. It also records result size, cache status, MCP outcome, and latency. It inserts its search entry with `anchor=str(session_id or '')`.
- `scripts/little_loops/session_store/writers.py` — `_backfill_tool_events()` always writes NULL byte columns and other live-only telemetry fields. Its tool search anchor is the raw source path. Replay copies timestamps from normalized transcript records; second precision is possible, so timestamp length does not identify provenance.
- `scripts/little_loops/session_store/writers.py` — `record_correction()` writes a caller-supplied source; `scripts/little_loops/hooks/user_prompt_submit.py` — `handle()` passes the source string "user_prompt_submit". `mine_corrections_from_messages()` reserves the source string "backfill" for replay and indexes only successful `INSERT OR IGNORE` writes.
- `scripts/little_loops/session_store/schema.py` — `idx_corrections_dedup` is UNIQUE on `(session_id, content)`. A retained live correction with a non-NULL session suppresses its replay twin and therefore cannot regain a deleted search entry. SQLite does not enforce that deduplication when `session_id` is NULL.
- `rebuild()` deletes all indexed rebuild kinds after the base deletes, inside the same `BEGIN IMMEDIATE` transaction. Existing base-row preservation does not automatically protect search evidence.

## Expected Behavior

Rebuild preserves byte-bearing tool rows (`bytes_in IS NOT NULL OR bytes_out IS NOT NULL`) and corrections whose source is not `backfill`, including NULL/unknown sources. Preserve every base-row field and ID, and retain their existing searchable evidence. Delete and rederive the replay-classified rows and search entries without growth across repeated rebuilds.

This is a bounded compatibility contract: a tool row with both byte columns NULL is classified as replayable regardless of timestamp or other fields. A correction with source `backfill` is replayable regardless of which API inserted it. Such rows cannot be recovered if their raw source is absent or pruned. Neither previously deleted live rows nor already-missing index entries are restored by this fix.

## Root Cause

**File**: `scripts/little_loops/session_store/lifecycle.py` — **Anchors**: `_REBUILD_TABLE_PREDICATES`, `rebuild()`.

The wipe treats mixed-origin tables as replay-only, and the separate blanket search deletion has no survivor exclusion. Live writer calls never persist a raw event from which rebuild could restore their measurements or provenance. Both manual and automatic callers reach the same function.

## Proposed Solution

**Selected: Option B — predicates on existing writer signals, no schema migration.**

Add these literal SQL wipe predicates to `_REBUILD_TABLE_PREDICATES`:

```python
"tool_events": "bytes_in IS NULL AND bytes_out IS NULL",
"user_corrections": "source = 'backfill'",
```

The predicates describe rows to delete. Preserve zero-valued byte metrics and output-only tool rows. Use ordinary equality for the reserved correction source so NULL sources survive. Keep the dictionary a literal: `scripts/tests/rebuild_fingerprint.py` — `_literal()` reads it with `ast.literal_eval`.

After the base deletes, match existing tool/correction search entries against normalized keys of the surviving rows. Match the full available `(kind, ref, anchor, ts, content)` tuple; a session-wide or anchor-only exclusion would preserve unrelated/orphan entries. Retain matching entries in place and delete unmatched entries. Leave message/skill/usage search selection unchanged in this issue.

Materialize normalized survivor keys once and use indexed probes, via an indexed temporary relation or a materialized CTE with a verified indexed query plan. Keep the work inside the replay transaction; no new permanent schema or index is needed. Avoid a correlated full scan of `tool_events` for every FTS entry. Temporary objects must be cleaned up, with failure rolling back the entire operation.

### Decision Rationale

Option B was selected on 2026-10-06. The pre-implementation review amends its original `bytes_in`-only classifier to use both byte columns: `_backfill_tool_events()` binds NULL for both, while `scripts/little_loops/cli/ctx_stats.py` — `_aggregate_tool_events()` already treats either populated byte column as telemetry. This deletes fewer rows without preserving replay output and explicitly protects output-only records. Decision amendment: `fdf825a0-00c8-4ee3-a80a-b86be905b0fe`.

Rejected Option A adds a channel column and migration, but its legacy classifier must still infer origin from the same existing signals. It adds no information for ambiguous old rows. The earlier claim of hook rows predating populated byte metrics is unsupported: the parent of commit `6a4c7b5a6` has a no-op `post_tool_use.handle()` and only a replay tool INSERT. Both-NULL imported/custom rows remain a documented compatibility limit, not an established historic hook population.

`/ll:advise` with `claude-opus-5-5` recommended Option B with normalized indexed matching, writer-contract tests, and safe rollout (confidence 0.8). Its dissent: byte-in-only is defensible for today's production hooks, and reindexing survivors could restore missing evidence but would change FTS identity and add tokenization work. Preserve existing entries here; count-bounded collision repair or restoring absent entries is outside this repair.

## Program Design

### Types

- `_REBUILD_TABLE_PREDICATES: dict[str, str]` — gains the two literal wipe predicates above.
- Survivor search key: `(kind: str, ref: str | None, anchor: str | None, ts: str, content: str | None)`; materialize after the base deletes. No public dataclass, base-table column, or migration is introduced.
- `search_index` is FTS5 with no base-row ID and no type affinity. Text-normalize non-NULL keys consistently on both sides and compare NULL keys safely; ordinary `=` must not discard an existing NULL-source correction entry.

### Signatures

- `rebuild(db: Path | str = DEFAULT_DB_PATH, *, config: dict | None = None, max_sessions: int | None = None) -> dict[str, int]` — unchanged; add atomic survivor-aware search deletion.
- Existing writer interfaces stay unchanged: `post_tool_use.handle()`, `record_correction()`, `_backfill_tool_events()`, and `mine_corrections_from_messages()`. Add brief provenance-contract comments and regression tests, rather than changing their stored output.

### Call Path

`hooks.session_start.handle` -> `rebuild_disposition()` -> `cli.backfill_worker.main --auto-rebuild` -> committed `backfill_incremental()` -> size/version recheck -> `lifecycle.rebuild()`.

Manual `cli.session.main_session` rebuild/refresh -> `lifecycle.rebuild()`.

Inside `rebuild()`: `BEGIN IMMEDIATE` -> predicate-scoped base deletes -> normalized survivor-key materialization -> scoped search deletion -> existing replay/mining/compaction passes -> metadata/derive stamps -> commit; any exception rolls everything back.

### Decision Rules

| Search kind | Key of a surviving base row | Replay convention |
|---|---|---|
| `tool` | `ref=tool_name`, `anchor=str(session_id or '')`, `ts=ts`, `content=f"{tool_name} {agent_type or ''}".strip()` | Same ref/preview convention, source-path anchor |
| `correction` | `ref=session_id or ''`, `anchor=source`, `ts=ts`, `content=content` (writer already truncates to 512) | Source/anchor `backfill`; index only if inserted |

Normalize to the actual writer representation, including Python `.strip()` semantics for tool previews; SQL `trim()` with its default space-only behavior is insufficient. Supported session identifiers are strings or NULL; test NULL and empty IDs explicitly. Normalize numeric values in real-writer fixtures where SQLite base-column affinity and FTS storage differ, rather than assuming `IS` equates unlike storage types.

Keep live/replay tool twins: there is no tool UNIQUE constraint, and deduplicating invocation counts is outside scope. Match only the observable index tuple; it cannot prove unique origin or distinguish existing identical entries for same-second/same-tool calls. Preserve their existing multiplicity; reject orphan entries with no matching surviving full key, without promising repair of indistinguishable pre-existing duplicates. For non-NULL-session same-content corrections, retain the live row and its sole existing live index entry; NULL-session replay may produce an additional row, but must remain stable across rebuilds.

## Integration Map

### Files to Modify

- `scripts/little_loops/session_store/lifecycle.py` — predicates, survivor-aware deletion in `rebuild()`, preservation comment/docstring, and `REBUILD_DERIVE_VERSION`. Correct its stale reference to the fingerprint test file while editing the version comment.
- `scripts/little_loops/session_store/writers.py` and `scripts/little_loops/hooks/post_tool_use.py` — short comments documenting the classifier/writer coupling; no INSERT shape or signature changes.
- `scripts/little_loops/session_store/rebuild_fingerprint.json` — regenerate after the final derivation edit and version bump. Do not regenerate `frozen_legacy_digest`.
- Tests and documentation listed below. `SCHEMA_VERSION`, `_MIGRATIONS`, and `schema_manifest.json` do not change.

### Dependent Files (Callers/Importers)

- `scripts/little_loops/cli/session.py`, `scripts/little_loops/cli/backfill_worker.py`, and `scripts/little_loops/hooks/session_start.py` share the rebuild path; caller interfaces remain compatible.
- `scripts/little_loops/history_reader/search.py` — use public `search()` to verify FTS results. `find_user_corrections()` reads the base table and alone would miss an index-loss regression.
- `scripts/little_loops/cli/ctx_stats.py` and `scripts/little_loops/history_reader/usage.py` — byte aggregation recognizes surviving rows; existing tool-count readers may count live/replay twins as they did before rebuild.
- ENH-3747 edits the same search deletion for usage. Record the relationship in both issues and preserve each other's exclusions when combining patches; neither is a prerequisite of the other.
- BUG-3766 captures confirmed skill-row/completion loss in the same wipe. Coordinate rollout of the shared version bump; this issue's readiness applies to tool/correction preservation, not all live telemetry.

### Similar Patterns

- `scripts/tests/test_session_store_lifecycle.py` — `test_rebuild_preserves_live_usage_rows`, `TestRebuildPreservesRetention`, and late-failure rollback tests.
- `scripts/tests/test_hook_post_tool_use.py` and `scripts/tests/test_enh_2511_mcp_telemetry.py` — drive real hooks in temporary projects with analytics enabled.
- `_REBUILD_TABLE_PREDICATES` usage/retention exceptions are precedents; their differing SQL forms do not mandate NULL-on-wipe semantics for every new table.

### Tests

- `scripts/tests/test_session_store_lifecycle.py` — real live tool/correction writers plus real replay fixtures; preservation, mixed-origin index matching, missing/pruned sources, disabled correction mining, output-only rows, NULL keys, idempotence, and rollback.
- `scripts/tests/test_backfill_worker_auto_rebuild.py` — real temporary store with a stale derive stamp; run the actual `--auto-rebuild` path, assert survivor fields/search entries and a current stamp afterward. Existing mocked delegation alone does not prove preservation.
- `scripts/tests/test_enh3678_rebuild_derive_gate.py` — update unstamped/null-stamp legacy expectations after the real bump, retaining frozen-baseline behavior coverage via monkeypatch; add predicate/index-selection digest sensitivity and fingerprint checks.
- `scripts/tests/test_bug3736_usage_replay_holds.py` — update the explicit current-version literal in `test_migration_creates_holds_table_and_keeps_version_constants`; keep the schema and usage-hold contracts intact.
- `scripts/tests/test_session_store_writers.py` and `scripts/tests/test_hook_post_tool_use.py` — pin replay NULL byte columns, live populated bytes (empty/MCP/non-JSON-native input), and correction-source contracts.
- Query-plan test for the survivor-key probe must verify indexed lookup rather than repeated base-table scans; use a representative fixture, not a wall-clock assertion.

### Documentation

- `docs/reference/CLI.md` — `ll-session rebuild` wipe list and example.
- `docs/reference/API.md` — `rebuild()` and the `prune()` note claiming all search entries are wiped/repopulated.
- `docs/guides/HISTORY_SESSION_GUIDE.md` and `docs/ARCHITECTURE.md` — preserved tool/correction rows and compatibility/recovery limits. Keep the independent usage-search limitation until ENH-3747 lands.

### Configuration and Versioning

No new setting. Live tools are analytics-enabled; correction capture gates writing/mining but never justifies deleting preserved live evidence. Remote rebuild remains unsupported.

Non-usage selection changes move the rebuild fingerprint. Ship `REBUILD_DERIVE_VERSION = "bug3761-v1"` with the complete preservation logic and regenerated current fingerprint. Leave `_FROZEN_LEGACY_DERIVE_VERSION = "enh3678-v1"`, `_LEGACY_REBUILD_FLOOR`, and frozen digest unchanged. Prefer the simple inline change; the existing reachable-function count of 23 is a test pin to update with an explanation if a helper is justified, not an architectural ban on helpers.

Regenerate from the implementation worktree root:

```bash
python -c "import sys; sys.path.insert(0, 'scripts'); from pathlib import Path; from tests.rebuild_fingerprint import regenerate; regenerate(Path('.'))"
```

### Audit of Indexed Rebuild Kinds

| Kind | Production provenance found on `main` | Disposition |
|---|---|---|
| `tool` | Live PostToolUse and transcript replay | This issue |
| `correction` | Live prompt hook and mined messages | This issue |
| `message` | `_backfill_messages()` and `_backfill_assistant_messages()` only | Continue wipe/replay |
| `skill` | `record_skill_event()`, `skill_event_context()`, and replay | Separate confirmed BUG-3766; no blanket live-preservation claim |
| `usage` | `_write_host_usage_observation()` indexes transcript observations; `record_usage_event()` writes live base rows without an index entry | Held/retained search preservation remains ENH-3747; do not introduce new indexed channels here |

## Acceptance Criteria

- [ ] Real PostToolUse rows with non-NULL byte metrics and real prompt-hook corrections survive manual rebuild with every base field and ID unchanged, even with no raw counterpart or a deleted source file. Existing live search entries remain searchable through public `history_reader.search()`.
- [ ] Real automatic-worker replay on a derive mismatch preserves the same rows/index evidence and stamps the store current. An enabled or disabled correction-mining config cannot remove preserved live corrections.
- [ ] Replay rows are still deleted and rederived. Across at least three rebuilds, base/search row contents and multiplicity are stable; replay AUTOINCREMENT IDs need not be stable. Live/replay tool twins remain, and non-NULL-session same-content corrections keep one live row/index entry. NULL-session cases remain stable without assuming UNIQUE deduplication.
- [ ] Zero byte values and output-only tool rows are preserved. Both-NULL tools are wiped; non-`backfill` corrections including NULL/unknown sources are preserved. Real writer contracts pin the signals so a later replay-byte/source change cannot silently accumulate duplicates or erase live rows.
- [ ] Survivor matching covers NULL/empty session IDs, NULL correction sources, normalized FTS/base storage types, and exact preview whitespace rules. Unmatched entries are removed, including mixed surviving/wiped tool rows in the same session and second. Include a full-key-distinct same-tool preview case and document indistinguishable duplicate limits.
- [ ] The preservation lookup uses indexed normalized survivor keys, with query-plan evidence and a one-off representative lock-duration comparison. Do not introduce an FTS-row-by-tool-row scan or permanent schema churn.
- [ ] Failures injected after index deletion and during/late in replay roll back the complete pre-call base rowsets, search rowsets, and metadata stamps. Existing usage/retention/out-of-scope behavior stays covered by its regression tests.
- [ ] The derive bump, current fingerprint, gate expectations, and preservation logic ship together; schema/frozen-baseline constants stay unchanged. Documentation states the bounded classifier and that already-deleted telemetry is unrecoverable without backup.
- [ ] `python -m pytest scripts/tests/` exits 0 for the final implementation.

## Implementation Steps

1. Work in an isolated git worktree: all consumer projects use this checkout through `local-editable`, so partial rebuild/version edits in the shared source would become live immediately. Seed the regressions with real writers/replay and add synthetic compatibility/orphan fixtures where necessary.
2. Add the literal byte/source wipe predicates and normalized survivor-index selection in the existing transaction. Pin writer contracts and verify indexed lookup. Add short provenance comments to the writer sites.
3. Validate source-loss, capture-disabled, NULL/empty key, mixed-origin/collision, repeated-rebuild, public search, auto-worker, and rollback cases. Record representative preservation overhead and compare against the 5 s database busy timeout; hooks suppress failed telemetry writes, so avoid materially extending that lock window.
4. Bump the derive version only after preservation is complete; regenerate the current fingerprint, update current-version/legacy-expectation tests, and run the focused tests then the full local suite. Do not move the frozen legacy baseline.
5. Update the documentation and coordinate shared search/version edits with ENH-3747 and BUG-3766 before rollout. Commit the complete tested implementation together; already-lost rows require backup recovery.

## Impact

- **Priority**: P1 — silent permanent loss of live telemetry/provenance on manual and automatic rebuilds across editable consumers.
- **Effort**: Medium — two literal predicates, normalized indexed search matching, version/fingerprint updates, and regression/documentation work; no schema migration.
- **Risk**: Medium — implicit writer contracts, nullable/type-sensitive FTS keys, indistinguishable existing index tuples, and lock duration. Both-NULL tool/source-`backfill` compatibility bounds are explicit; rollback and real-writer tests protect the supported cases.
- **Breaking Change**: No public interface or schema change.

## Verification Notes

Reviewed on `main` in the little-loops source checkout, 2026-10-06. All implementation anchors above were inspected on that branch. Removed the stale `verify_verdict: NON_VALID` after reconciling the rejected channel design; no implementation or automated confidence score is claimed.

Disposable real-writer probe: a live MCP tool had `bytes_in=8`, `bytes_out=12`, `latency_ms=9`; after rebuild only its replay row remained with all three fields NULL. A live `user_prompt_submit` correction became `backfill`. The same loss persisted through a second rebuild after the original JSONL file was deleted. Separate live-skill probe confirmed BUG-3766.

Synthetic lookup probe: 3,000 survivor tool rows and 6,000 FTS entries; correlated full scan took approximately 0.572 s, while a materialized survivor CTE with an automatic covering index took 0.004 s on this machine. This checks feasibility, not final lock-duration performance or a timing test threshold. The implementation must measure its final SQL/key normalization cost and inspect its plan.

Required-rule query returned no active required rules; learning-test assessment returned `not_required`; no structured/prose prerequisite was found. The original historical incident totals remain attributed evidence. The standalone skill and usage-search issues remain explicit scope limits.

Focused baseline checks passed: 101 tests across `TestRebuild`, PostToolUse hooks, derive-version gates, and the automatic worker. The real-writer loss probes are evidence for the missing regression coverage, not proof that the bug has been fixed. The full local suite remains the final implementation gate.

## Status

**Open** | Created: 2026-10-06 | Priority: P1

## Session Log
- `/ll:confidence-check` - 2026-10-07T01:02:00 - `8092456a-7bf3-47b0-86f7-42712002052b.jsonl`
- `/ll:ready-issue` - 2026-10-07T00:55:44 - `62355c4f-23ba-4c6f-bf44-9fe87ad6e7af.jsonl`
- `/ll:refine-issue:gap-analysis` - 2026-10-07T00:39:26 - `c822b1e8-eb73-465f-ac83-ee54531a264e.jsonl`
- `/ll:reconcile-issue` - 2026-10-07T00:31:44 - `c0a7447a-de94-4f52-84a5-8f881b60acd9.jsonl`
- `/ll:wire-issue` - 2026-10-07T00:29:12 - `a8216bde-d16f-4810-80e1-dfa40b1fe3ce.jsonl`
- `/ll:decide-issue` - 2026-10-07T00:20:39 - `c562a3b7-7006-4c12-9609-bf1d64934054.jsonl`
- `/ll:refine-issue` - 2026-10-07T00:14:30 - `1bebe889-c22b-4d94-a454-4b6419a82d25.jsonl`
- `/ll:format-issue` - 2026-10-06T23:51:08 - `be24ca19-aef3-4138-b6f0-d60a7d2187c1.jsonl`
