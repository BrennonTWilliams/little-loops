---
id: BUG-3761
title: rebuild() wipes hook-written tool_events and user_corrections rows that replay
  cannot regenerate
type: BUG
priority: P1
status: done
discovered_date: '2026-10-06'
labels:
- history
- telemetry
- data-loss
testable: true
completed_at: '2026-10-07T01:35:37Z'
decision_needed: false
reconcile_attempted: true
relates_to:
- BUG-3530
- BUG-3715
- BUG-3762
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
  description: Survivor re-indexing and twin suppression extend the BEGIN IMMEDIATE
    window against the 5s hook busy timeout; the forced first auto-rebuild on every
    eligible store can drop a few hook telemetry rows; needs measurement and a check
    that concurrent SessionStart workers cannot both rebuild
- id: shared-rebuild-edit-coordination
  domain: outcome
  criterion: change_surface
  description: ENH-3747 and BUG-3766 edit the same search deletion and derive-version
    bump; patches must be combined without losing exclusions
- id: tool-twin-suppression-new-scope
  domain: outcome
  criterion: complexity
  description: Suppressing replay twins of surviving live tool rows (multiset match
    on session_id, tool_name, args_hash) is a new mechanism beyond the predicate precedent;
    without it tool counts double after the first post-fix rebuild
- id: preserved-correction-outlives-redaction
  domain: outcome
  criterion: change_surface
  description: ll-session redact only rewrites raw_events; preserved live correction
    text and FTS entries now outlive redaction (rebuild used to regenerate them from
    redacted raw text); coordinate with BUG-3762 and document
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

Rebuild preserves byte-bearing tool rows (`bytes_in IS NOT NULL OR bytes_out IS NOT NULL`) and corrections whose source is not `backfill`, including NULL/unknown sources. Preserve every base-row field and ID, and keep them searchable (survivors are re-indexed from their base rows). Delete and rederive the replay-classified rows and search entries without growth across repeated rebuilds. Tool invocation counts must not change because of preservation: a replay row that duplicates a surviving live row is suppressed.

This is a bounded compatibility contract: a tool row with both byte columns NULL is classified as replayable regardless of timestamp or other fields. A correction with source `backfill` is replayable regardless of which API inserted it. Such rows cannot be recovered if their raw source is absent or pruned. Neither previously deleted live rows nor already-missing index entries are restored by this fix.

## Root Cause

**File**: `scripts/little_loops/session_store/lifecycle.py` — **Anchors**: `_REBUILD_TABLE_PREDICATES`, `rebuild()`.

The wipe treats mixed-origin tables as replay-only, and the separate blanket search deletion has no survivor handling. Live writer calls never persist a raw event from which rebuild could restore their measurements or provenance. Both manual and automatic callers reach the same function.

## Proposed Solution

**Selected: Option B — predicates on existing writer signals, no schema migration.**

Add these literal SQL wipe predicates to `_REBUILD_TABLE_PREDICATES`:

```python
"tool_events": "bytes_in IS NULL AND bytes_out IS NULL",
"user_corrections": "source = 'backfill'",
```

The predicates describe rows to delete. Preserve zero-valued byte metrics and output-only tool rows. Use ordinary equality for the reserved correction source so NULL sources survive. Keep the dictionary a literal: `scripts/tests/rebuild_fingerprint.py` — `_literal()` reads it with `ast.literal_eval`.

**Search entries: re-index survivors.** Keep the existing blanket `DELETE FROM search_index WHERE kind IN (...)`, then re-index every surviving `tool_events` and `user_corrections` row with the existing `_index()` helper, using the writer conventions in Decision Rules. No Python code consumes `search_index` rowids, so FTS row identity is not a contract. This replaces the earlier design of matching existing FTS entries against normalized survivor keys: re-indexing needs no NULL-safe/type-normalized key matching, no temp relation, and no query-plan test, and a normalization slip cannot silently delete a live entry. Orphan entries disappear automatically; entries missing before the rebuild are restored as a side effect (acceptable, not a goal). Leave message/skill/usage search selection unchanged in this issue.

**Tool twin suppression.** `_backfill_tool_events()` is called only from `rebuild()`, and only the PostToolUse hook and replay insert into `tool_events`, so replay twins of live rows do not exist in steady state. Preserving live rows without suppression would roughly double every tool count (`ctx_stats`, `history_reader/usage.py`) for hooked sessions after the first post-fix rebuild. Suppress at replay time, not after it (replay indexes each row as it inserts, so post-hoc deletion would leave orphan FTS entries): after the predicate-scoped base deletes, build a multiset (Counter) of surviving live-row keys `(session_id, tool_name, args_hash)` and pass it to `_backfill_tool_events()` through a new optional keyword (default `None` keeps the legacy behavior). For each tool_use block whose key has a remaining count, decrement it and skip both the INSERT and the `_index()` call. Match on this key, not on `ts`: the hook stamps `_now()` while replay copies the transcript timestamp. Replay rows with no live counterpart (hook disabled, analytics off, pre-hook history) are kept. Counts, not a set: N live rows suppress at most N replay rows, so same-key repeated calls are not over-suppressed. Inline in `rebuild()` or a helper; the 23-function pin is updated either way if a helper is added.

Keep all of this inside the replay transaction; no new permanent schema or index is needed. Temporary objects, if any, must be cleaned up, with failure rolling back the entire operation.

### Decision Rationale

Option B was selected on 2026-10-06. The pre-implementation review amends its original `bytes_in`-only classifier to use both byte columns: `_backfill_tool_events()` binds NULL for both, while `scripts/little_loops/cli/ctx_stats.py` — `_aggregate_tool_events()` already treats either populated byte column as telemetry. This deletes fewer rows without preserving replay output and explicitly protects output-only records. Decision amendment: `fdf825a0-00c8-4ee3-a80a-b86be905b0fe`.

Rejected Option A adds a channel column and migration, but its legacy classifier must still infer origin from the same existing signals. It adds no information for ambiguous old rows. The earlier claim of hook rows predating populated byte metrics is unsupported: the parent of commit `6a4c7b5a6` has a no-op `post_tool_use.handle()` and only a replay tool INSERT. Both-NULL imported/custom rows remain a documented compatibility limit, not an established historic hook population.

`/ll:advise` with `claude-opus-5-5` recommended Option B with normalized indexed matching, writer-contract tests, and safe rollout (confidence 0.8). Its dissent: byte-in-only is defensible for today's production hooks, and reindexing survivors could restore missing evidence but would change FTS identity and add tokenization work.

**Amended 2026-10-07** after a second `/ll:advise` consult with `claude-fable-5-1` (confidence 0.85), each point verified against the code: (1) `_backfill_tool_events()` is called only from `rebuild()` and only the hook and replay write `tool_events`, so the "live/replay twins already exist in steady state" premise was false, and preservation alone would double tool counts — twin suppression added; (2) no Python code reads `search_index` rowids and token volume is trivial, so the FTS-identity concern does not hold — full-tuple matching replaced by re-indexing survivors, which removes the normalization hazard; (3) `ll-session redact` only rewrites `raw_events`, so preserved correction text now outlives redaction — documented, coordinated with BUG-3762.

## Program Design

### Types

- `_REBUILD_TABLE_PREDICATES: dict[str, str]` — gains the two literal wipe predicates above.
- Live-tool suppression key: `tuple[str | None, str, str]` = `(session_id, tool_name, args_hash)`; a `collections.Counter` of surviving live rows, passed to replay. No public dataclass, base-table column, or migration is introduced.
- `search_index` is FTS5 with no base-row ID. Survivors are re-indexed from base rows after the blanket delete, so no key matching or type normalization against existing FTS rows is needed; only the writer's own `_index()` arguments must be reproduced.

### Signatures

- `rebuild(db: Path | str = DEFAULT_DB_PATH, *, config: dict | None = None, max_sessions: int | None = None) -> dict[str, int]` — unchanged; add survivor re-indexing and live-tool Counter construction.
- `_backfill_tool_events(conn, source, *, skip_live: Counter[tuple[str | None, str, str]] | None = None) -> int` — new optional keyword; `None` preserves legacy behavior. Mutates the Counter as it suppresses.
- Other writer interfaces stay unchanged: `post_tool_use.handle()`, `record_correction()`, and `mine_corrections_from_messages()`. Add brief provenance-contract comments and regression tests, rather than changing their stored output.

### Call Path

`hooks.session_start.handle` -> `rebuild_disposition()` -> `cli.backfill_worker.main --auto-rebuild` -> committed `backfill_incremental()` -> size/version recheck -> `lifecycle.rebuild()`.

Manual `cli.session.main_session` rebuild/refresh -> `lifecycle.rebuild()`.

Inside `rebuild()`: `BEGIN IMMEDIATE` -> predicate-scoped base deletes -> blanket search deletion -> build live-tool Counter from surviving `tool_events` -> re-index surviving tool/correction rows -> replay (tool replay skips Counter-matched blocks) / mining / compaction passes -> metadata/derive stamps -> commit; any exception rolls everything back.

### Decision Rules

| Search kind | `_index()` arguments for a surviving base row | Replay convention |
|---|---|---|
| `tool` | `ref=tool_name`, `anchor=str(session_id or '')`, `ts=ts`, `content=f"{tool_name} {agent_type or ''}".strip()` | Same ref/preview convention, source-path anchor |
| `correction` | `ref=session_id or ''`, `anchor=source`, `ts=ts`, `content=content` (writer already truncates to 512) | Source/anchor `backfill`; index only if inserted |

Reproduce the writer's arguments exactly, including Python `.strip()` semantics for tool previews. Test NULL and empty session IDs and NULL correction sources explicitly (`anchor=source` with a NULL source needs a defined stored value; match what `record_correction()` would pass).

Live/replay tool twins are suppressed (see Proposed Solution): a surviving live row and its transcript counterpart yield one row and one index entry. Suppression is count-bounded per `(session_id, tool_name, args_hash)`; this cannot tell apart two calls with identical key in one session, which is fine because only the count matters. For non-NULL-session same-content corrections, retain the live row and its sole index entry (the dedup index suppresses the replay twin); NULL-session replay may produce an additional row, but must remain stable across rebuilds.

## Integration Map

### Files to Modify

- `scripts/little_loops/session_store/lifecycle.py` — predicates, survivor re-indexing and live-tool Counter in `rebuild()`, preservation comment/docstring, and `REBUILD_DERIVE_VERSION`. Correct its stale reference to the fingerprint test file while editing the version comment.
- `scripts/little_loops/session_store/writers.py` — `_backfill_tool_events()` gains the optional `skip_live` keyword; short comments documenting the classifier/writer coupling. No INSERT shape changes.
- `scripts/little_loops/hooks/post_tool_use.py` — short coupling comment only.
- `scripts/little_loops/session_store/rebuild_fingerprint.json` — regenerate after the final derivation edit and version bump. Do not regenerate `frozen_legacy_digest`.
- Tests and documentation listed below. `SCHEMA_VERSION`, `_MIGRATIONS`, and `schema_manifest.json` do not change.

### Dependent Files (Callers/Importers)

- `scripts/little_loops/cli/session.py`, `scripts/little_loops/cli/backfill_worker.py`, and `scripts/little_loops/hooks/session_start.py` share the rebuild path; caller interfaces remain compatible.
- `scripts/little_loops/history_reader/search.py` — use public `search()` to verify FTS results. `find_user_corrections()` reads the base table and alone would miss an index-loss regression.
- `scripts/little_loops/cli/ctx_stats.py` and `scripts/little_loops/history_reader/usage.py` — byte aggregation recognizes surviving rows; tool-count readers must see unchanged invocation counts because replay twins of live rows are suppressed (add a count-parity regression test over these readers).
- ENH-3747 edits the same search deletion for usage. Record the relationship in both issues and preserve each other's exclusions when combining patches; neither is a prerequisite of the other.
- BUG-3766 captures confirmed skill-row/completion loss in the same wipe. Coordinate rollout of the shared version bump; this issue's readiness applies to tool/correction preservation, not all live telemetry.

### Similar Patterns

- `scripts/tests/test_session_store_lifecycle.py` — `test_rebuild_preserves_live_usage_rows`, `TestRebuildPreservesRetention`, and late-failure rollback tests.
- `scripts/tests/test_hook_post_tool_use.py` and `scripts/tests/test_enh_2511_mcp_telemetry.py` — drive real hooks in temporary projects with analytics enabled.
- `_REBUILD_TABLE_PREDICATES` usage/retention exceptions are precedents; their differing SQL forms do not mandate NULL-on-wipe semantics for every new table.

### Tests

- `scripts/tests/test_session_store_lifecycle.py` — real live tool/correction writers plus real replay fixtures; preservation, survivor re-indexing, twin suppression (live+transcript pair yields one row; N live rows suppress at most N replay rows; replay rows with no live counterpart are kept), missing/pruned sources, disabled correction mining, output-only rows, NULL keys, idempotence, and rollback. Include corrections whose hook prompt text differs from the transcript rendering, and NULL-session corrections, which bypass the dedup index and may duplicate.
- `scripts/tests/test_backfill_worker_auto_rebuild.py` — real temporary store with a stale derive stamp; run the actual `--auto-rebuild` path, assert survivor fields/search entries and a current stamp afterward. Existing mocked delegation alone does not prove preservation.
- `scripts/tests/test_enh3678_rebuild_derive_gate.py` — update unstamped/null-stamp legacy expectations after the real bump, retaining frozen-baseline behavior coverage via monkeypatch; add predicate/index-selection digest sensitivity and fingerprint checks.
- `scripts/tests/test_bug3736_usage_replay_holds.py` — update the explicit current-version literal in `test_migration_creates_holds_table_and_keeps_version_constants`; keep the schema and usage-hold contracts intact.
- `scripts/tests/test_session_store_writers.py` and `scripts/tests/test_hook_post_tool_use.py` — pin replay NULL byte columns, live populated bytes (empty/MCP/non-JSON-native input), and correction-source contracts.
- Concurrency check (not a unit test): confirm two SessionStart auto-rebuild workers cannot both run `rebuild()` against one store (existing lock/recheck in `backfill_worker`); if they can, record it rather than fix it here.

### Documentation

- `docs/reference/CLI.md` — `ll-session rebuild` wipe list and example.
- `docs/reference/API.md` — `rebuild()` and the `prune()` note claiming all search entries are wiped/repopulated.
- `docs/guides/HISTORY_SESSION_GUIDE.md` and `docs/ARCHITECTURE.md` — preserved tool/correction rows and compatibility/recovery limits. Keep the independent usage-search limitation until ENH-3747 lands. State that preserved live correction text is not rewritten by `ll-session redact` (which only rewrites `raw_events`) and cross-link BUG-3762; state that the first post-bump auto-rebuild holds the write lock and may drop a few hook telemetry rows at the 5 s busy timeout.

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
- [ ] Replay rows are still deleted and rederived. Across at least three rebuilds, base/search row contents and multiplicity are stable; replay AUTOINCREMENT IDs need not be stable. Non-NULL-session same-content corrections keep one live row/index entry. NULL-session cases remain stable without assuming UNIQUE deduplication.
- [ ] Tool invocation counts do not change because of preservation: a session with both live hook rows and a transcript yields one `tool_events` row and one `tool` index entry per invocation (replay twins suppressed, count-bounded per `(session_id, tool_name, args_hash)`), checked through `ctx_stats` and `history_reader/usage.py`. Transcript tool_use blocks with no live counterpart still replay.
- [ ] Zero byte values and output-only tool rows are preserved. Both-NULL tools are wiped; non-`backfill` corrections including NULL/unknown sources are preserved. Real writer contracts pin the signals so a later replay-byte/source change cannot silently accumulate duplicates or erase live rows.
- [ ] Survivor re-indexing reproduces the writer's `_index()` arguments exactly for NULL/empty session IDs, NULL correction sources, and tool preview whitespace (Python `.strip()`); orphan tool/correction entries from before the rebuild do not survive, and mixed surviving/wiped tool rows in the same session and second are handled.
- [ ] A one-off representative lock-duration measurement of the final rebuild delta (re-index plus Counter suppression) is recorded against the 5 s hook busy timeout. No permanent schema churn.
- [ ] Documentation states that preserved correction text outlives `ll-session redact` (cross-linked to BUG-3762) and that the first post-bump auto-rebuild can drop a few hook telemetry rows during its lock window.
- [ ] Failures injected after index deletion and during/late in replay roll back the complete pre-call base rowsets, search rowsets, and metadata stamps. Existing usage/retention/out-of-scope behavior stays covered by its regression tests.
- [ ] The derive bump, current fingerprint, gate expectations, and preservation logic ship together; schema/frozen-baseline constants stay unchanged. Documentation states the bounded classifier and that already-deleted telemetry is unrecoverable without backup.
- [ ] `python -m pytest scripts/tests/` exits 0 for the final implementation.

## Implementation Steps

1. Work in an isolated git worktree: all consumer projects use this checkout through `local-editable`, so partial rebuild/version edits in the shared source would become live immediately. Seed the regressions with real writers/replay and add synthetic compatibility/orphan fixtures where necessary.
2. Add the literal byte/source wipe predicates, survivor re-indexing, and the live-tool Counter passed to `_backfill_tool_events(skip_live=...)` in the existing transaction. Pin writer contracts. Add short provenance comments to the writer sites.
3. Validate source-loss, capture-disabled, NULL/empty key, twin suppression/count parity, repeated-rebuild, public search, auto-worker, and rollback cases. Record representative rebuild overhead and compare against the 5 s database busy timeout; hooks suppress failed telemetry writes, so avoid materially extending that lock window. Check that concurrent SessionStart workers cannot both rebuild.
4. Bump the derive version only after preservation is complete; regenerate the current fingerprint, update current-version/legacy-expectation tests, and run the focused tests then the full local suite. Do not move the frozen legacy baseline.
5. Update the documentation and coordinate shared search/version edits with ENH-3747 and BUG-3766 before rollout. Commit the complete tested implementation together; already-lost rows require backup recovery.

## Impact

- **Priority**: P1 — silent permanent loss of live telemetry/provenance on manual and automatic rebuilds across editable consumers.
- **Effort**: Medium — two literal predicates, survivor re-indexing, replay-time twin suppression, version/fingerprint updates, and regression/documentation work; no schema migration.
- **Risk**: Medium — implicit writer contracts, twin-suppression key correctness, lock duration, and redaction carry-over. Both-NULL tool/source-`backfill` compatibility bounds are explicit; rollback and real-writer tests protect the supported cases.
- **Breaking Change**: No public interface or schema change.

## Verification Notes

Reviewed on `main` in the little-loops source checkout, 2026-10-06. All implementation anchors above were inspected on that branch. Removed the stale `verify_verdict: NON_VALID` after reconciling the rejected channel design; no implementation or automated confidence score is claimed.

Disposable real-writer probe: a live MCP tool had `bytes_in=8`, `bytes_out=12`, `latency_ms=9`; after rebuild only its replay row remained with all three fields NULL. A live `user_prompt_submit` correction became `backfill`. The same loss persisted through a second rebuild after the original JSONL file was deleted. Separate live-skill probe confirmed BUG-3766.

Synthetic lookup probe (from the superseded matching design): 3,000 survivor tool rows and 6,000 FTS entries; correlated full scan took approximately 0.572 s, while a materialized survivor CTE took 0.004 s. Kept only as feasibility evidence; the re-index design performs one INSERT per survivor and has no such lookup. Final lock-duration cost still needs measuring.

Amended 2026-10-07 (second advise consult, claims verified in code): twin suppression added, FTS matching replaced by survivor re-indexing, redaction carry-over documented. The `confidence_score`/`outcome_confidence` values above predate these amendments; re-run `/ll:confidence-check` before implementation.

Required-rule query returned no active required rules; learning-test assessment returned `not_required`; no structured/prose prerequisite was found. The original historical incident totals remain attributed evidence. The standalone skill and usage-search issues remain explicit scope limits.

Focused baseline checks passed: 101 tests across `TestRebuild`, PostToolUse hooks, derive-version gates, and the automatic worker. The real-writer loss probes are evidence for the missing regression coverage, not proof that the bug has been fixed. The full local suite remains the final implementation gate.

## Resolution

**Fixed** 2026-10-06 (Option B, as amended 2026-10-07).

- `lifecycle.py`: `_REBUILD_TABLE_PREDICATES` gains `tool_events: bytes_in IS NULL AND bytes_out IS NULL` and `user_corrections: source = 'backfill'`; `rebuild()` re-indexes surviving tool/correction rows with the writers' own `_index()` arguments and builds a live-tool `Counter`; `REBUILD_DERIVE_VERSION = "bug3761-v1"`; fingerprint regenerated (frozen baseline untouched).
- `writers.py`: `_backfill_tool_events(..., skip_live=Counter | None)` suppresses count-bounded transcript twins of surviving live rows (no INSERT, no index entry); provenance-contract comments on the replay/`record_correction` sites; `post_tool_use.py` coupling comment.
- Tests: new `test_bug3761_rebuild_preserves_live_telemetry.py` (real hook + writer; preservation, FTS, twin suppression, idempotence, NULL keys, rollback, writer contracts), real `--auto-rebuild` worker test, gate/version-literal tests updated (frozen-baseline coverage retained via monkeypatch).
- Docs: CLI.md, API.md, HISTORY_SESSION_GUIDE.md, ARCHITECTURE.md (bounded classifier, redaction carry-over, first-rebuild lock window).
- Lock-duration measurement (one-off, synthetic): 20,000 surviving tool rows + 2,000 corrections rebuild in 0.073 s total, far inside the 5 s hook busy timeout.
- Concurrency check: `rebuild()` serializes on `BEGIN IMMEDIATE`, but the worker's disposition recheck happens before it, so two simultaneous SessionStart workers could each rebuild back to back. Recorded, not fixed here; the rebuild is now idempotent for tools/corrections, so the second pass is wasted work, not data loss.
- Full suite: 29232 passed; the only failures are pre-existing and unrelated (`test_next_loop_golden` float-ulp mismatch, `test_libsql_integration::TestLive` needing a live endpoint), both reproduced on a clean stash.

## Status

**Done** | Created: 2026-10-06 | Completed: 2026-10-06 | Priority: P1

## Session Log
- `/ll:manage-issue` - 2026-10-07T01:35:37 - `0f80487b-9ecd-4599-919e-b780b862172c.jsonl`
- `/ll:ready-issue` - 2026-10-07T01:21:18 - `27d2ae1e-6f7f-4536-988d-2e9430cab455.jsonl`
- `/ll:confidence-check` - 2026-10-07T01:02:00 - `8092456a-7bf3-47b0-86f7-42712002052b.jsonl`
- `/ll:ready-issue` - 2026-10-07T00:55:44 - `62355c4f-23ba-4c6f-bf44-9fe87ad6e7af.jsonl`
- `/ll:refine-issue:gap-analysis` - 2026-10-07T00:39:26 - `c822b1e8-eb73-465f-ac83-ee54531a264e.jsonl`
- `/ll:reconcile-issue` - 2026-10-07T00:31:44 - `c0a7447a-de94-4f52-84a5-8f881b60acd9.jsonl`
- `/ll:wire-issue` - 2026-10-07T00:29:12 - `a8216bde-d16f-4810-80e1-dfa40b1fe3ce.jsonl`
- `/ll:decide-issue` - 2026-10-07T00:20:39 - `c562a3b7-7006-4c12-9609-bf1d64934054.jsonl`
- `/ll:refine-issue` - 2026-10-07T00:14:30 - `1bebe889-c22b-4d94-a454-4b6419a82d25.jsonl`
- `/ll:format-issue` - 2026-10-06T23:51:08 - `be24ca19-aef3-4138-b6f0-d60a7d2187c1.jsonl`
