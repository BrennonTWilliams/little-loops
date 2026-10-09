---
id: BUG-3766
type: BUG
title: Rebuild wipes live skill telemetry and completion fields
priority: P1
status: done
discovered_by: ll-issues-create
discovered_date: '2026-10-06'
captured_at: '2026-10-07T00:53:14Z'
completed_at: '2026-10-07T02:16:18Z'
labels:
- history
- telemetry
- data-loss
testable: true
decision_needed: false
relates_to:
- BUG-3761
- ENH-3747
confidence_score: 95
outcome_confidence: 70
score_complexity: 10
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 10
risk_factors:
- id: bug3761-scaffold-shared-with-enh3747
  domain: readiness
  criterion: duplicate_implementations
  description: BUG-3761 survivor re-index/suppression scaffolding already exists and
    ENH-3747 shares search deletion; later lander must preserve the other's logic.
- id: rebuild-classification-matching-contract
  domain: outcome
  criterion: complexity_depth
  description: Migration plus in-transaction legacy classification and one-to-one
    twin matching change the rebuild contract with shared state.
- id: schema-version-literal-fanout
  domain: outcome
  criterion: complexity_breadth
  description: ~13 change sites incl. 33 SCHEMA_VERSION==60 assertions across four
    test files, manifest, fingerprint and the BUG-3736 downgrade fixture.
- id: skill-reader-consistency
  domain: outcome
  criterion: change_surface
  description: Six dependent readers (session skill stats, doctor_trim, logs, hooks,
    action, worker) must stay consistent with preserved rows and suppressed counts.
---

# BUG-3766: Rebuild wipes live skill telemetry and completion fields

## Summary

`rebuild()` deletes every `skill_events` row and every `search_index` row of kind `skill` before replay. `record_skill_event()` and `skill_event_context()` also write this table directly without `raw_events`. Replay cannot restore completion fields (`exit_code`, `success`, `duration_ms`), and may not recreate the invocation at all. BUG-3761's tool/correction preservation is already implemented in commit `527916699`; skill preservation is still missing on the resulting `bug3761-v1` derivation.

## Current Behavior

- `scripts/little_loops/session_store/lifecycle.py` — `_REBUILD_TABLES` contains the skill-events table; `_REBUILD_TABLE_PREDICATES` has no skill exception; `rebuild()` deletes kind `skill` search entries unconditionally.
- `scripts/little_loops/session_store/writers.py` — `record_skill_event()` writes a live invocation and search entry; `skill_event_context()` writes another live invocation and updates completion fields on exit. Neither writes a raw event.
- `scripts/little_loops/hooks/user_prompt_submit.py` — `handle()` calls `record_skill_event()` for plain `/ll:<name>` prompts. `scripts/little_loops/cli/action.py` calls `skill_event_context()` for executed actions.
- `scripts/little_loops/session_store/writers.py` — `_backfill_skill_events()` mines `<command-name>/ll:...` user transcript text and writes only timestamp/session/name/args. Its search anchor is the source path; live anchors are the skill name. Live hook rows without completion fields otherwise resemble replay rows, so a completion-field-only predicate is insufficient.

## Expected Behavior

Live skill invocations, completion fields, and their existing search evidence survive manual and derive-version-triggered rebuilds. Explicit transcript-origin rows are replaced without accumulating across repeated rebuilds; uncertain historical rows are preserved as legacy with the duplicate limits below. Source deletion/pruning does not destroy live invocation history.

## Motivation

Repeated full rebuilds silently discard skill execution outcomes and invocation history in every local-editable consumer. A derive-version change can trigger the loss automatically; this repair completes the live-telemetry preservation that BUG-3761 established for tools/corrections.

## Proposed Solution

**Selected: Option A — nullable `skill_events.origin` column via an append-only migration, plus replay-twin suppression.**

1. **Durable origin.** Add nullable `origin TEXT`, with no default or CHECK restriction. `record_skill_event()` stamps `'prompt_hook'`, `skill_event_context()` stamps `'skill_host'`, and `_backfill_skill_events()` stamps `'transcript'`. `_REBUILD_TABLE_PREDICATES` gains the literal `"skill_events": "origin IS 'transcript'"`; `_literal()` in `scripts/tests/rebuild_fingerprint.py:134` requires literal-evaluable predicates. Unrecognized origins and NULL must survive; preserve row IDs and never reset `sqlite_sequence`.
2. **Conservative legacy classification.** Before any deletion, classify currently NULL-origin rows using the original skill search entries. Any completion-bearing row is `'skill_host'` regardless of index evidence. An unambiguous single base-row/single path-anchor group may identify transcript provenance. A name anchor alone cannot distinguish a prompt hook from an unfinished legacy skill host: it, conflicting, duplicated, malformed or missing evidence becomes non-NULL `'legacy'`. See Program Design → Decision Rules for exact cases. Explicit origins are never reclassified. This handles stale-process NULL inserts on subsequent rebuilds without a global one-time marker and prevents restored live-style anchors from becoming new provenance. Classification and its index read belong to the rebuild transaction, not connect, migration, or ingest.
3. **Search restoration.** Retain BUG-3761's blanket kind deletion and survivor restoration. Re-index surviving skills with the live-writer convention (`content=skill_name`, `kind='skill'`, `ref=session_id or ''`, `anchor=skill_name`, `ts=row ts`). Explicit transcript rows use their replay source anchor when regenerated. Orphans vanish and missing survivor entries are restored; identical tuples from distinct surviving invocations remain legitimate separate search rows.
4. **Bounded twin suppression.** Replace the proposed session/name Counter with one-to-one matching of eligible hook survivors to replay candidates. Require the same normalized nonempty session ID, skill name, stored arguments, and timezone-aware timestamps within **1 second inclusive**. Consume each survivor at most once and skip both replay INSERT and `_index()`. Known skill hosts, unresolved legacy rows, unknown future origins, and missing/invalid identity fields never suppress. Default `None` retains the helper's unsuppressed replay behavior. The earlier issue probe reported 560/562 hook twins within 1s; outliers are retained as duplicates rather than widening matching to unrelated invocations.

Read relevant FTS evidence once only when NULL-origin rows exist; no per-row full scans of the FTS5 table (`kind`, `ref`, `anchor`, and `ts` are UNINDEXED, `scripts/little_loops/session_store/schema.py:178`). Candidate matching must restrict lookup to the relevant session/name/argument identity rather than scanning every survivor for every raw event. Measure the added classification/matching and write-lock cost on a disposable representative store or copy, with compaction disabled to isolate this change. Existing 5s hook busy-timeout behavior remains relevant; the automatic rebuild must continue running in the background worker. Never rebuild a production store for a review or timing probe.

### Decision Rationale

Option A selected in the initial `/ll:advise` consult (claude-opus-5-5, confidence 0.8), then reviewed again on 2026-10-06 with the same model (confidence 0.75). Skill rows, unlike tool/correction rows, carry no writer-distinguishing column. A real column makes origin a base-row fact and keeps the replay predicate trivial. The second review identified unstable NULL classification, ambiguous index twins, overly broad suppression, and stale rollout instructions as implementation blockers; this revision resolves those contracts.

Rejected Option B (no migration, predicate on search anchor `== skill_name`): it couples base-row provenance to a derived index and cannot classify un-indexed rows. The earlier review reported agreement with timestamp precision on its sampled store; this is not a writer invariant. Splitting all twin suppression into a follow-up remains rejected: newly origin-stamped hooks must not systematically double counts.

The second advisor's dissent proposed marking every old row `'legacy'` and retaining it forever, with no FTS classification. Keep conservative classification so clearly identified historical replay rows can still be replaced. Also reject suppression of unresolved `'legacy'` rows and argument-free matching: the two live writers share an index anchor, and both production hook/replay paths normalize arguments with `.strip()[:200]` (`scripts/little_loops/hooks/user_prompt_submit.py:138`, `scripts/little_loops/session_store/writers.py:4731`). Preserve ambiguous invocations even when this leaves a bounded duplicate. **Tradeoff:** old completionless live rows become `'legacy'`, so their replay twins can increase historical counts on the first fixed rebuild; subsequent rebuilds must not accumulate further copies. No universal pre/post count equality is claimed: replay-only history legitimately adds rows, and legacy uncertainty cannot always be deduplicated safely.

## Integration Map

### Files to Modify

- `scripts/little_loops/session_store/lifecycle.py` — skill deletion and kind `skill` index selection in `rebuild()`.
- `scripts/little_loops/session_store/writers.py` — live/replay skill writer provenance contracts.
- `scripts/little_loops/session_store/schema.py` and `scripts/little_loops/session_store/schema_manifest.json` — append-only migration adding `skill_events.origin`; current `SCHEMA_VERSION` is 60. Regenerate the manifest and update all current-version assertions in `scripts/tests/test_session_store_schema.py`, `scripts/tests/test_session_store_writers.py`, `scripts/tests/test_assistant_messages.py`, and `scripts/tests/test_bug3736_usage_replay_holds.py` (33 `SCHEMA_VERSION == 60` assertions at review time). Historical-version fixtures must retain their historical expectations.
- `scripts/tests/test_bug3736_usage_replay_holds.py:100` — `_downgrade_and_remigrate()` currently removes only the v59/v60 additions before rewinding to v58; the fixture must also account for the new origin column, or bootstrap a genuine historical schema. Otherwise remigration adds an already-existing column. This file also pins `REBUILD_DERIVE_VERSION` at line 492.
- `scripts/tests/test_enh3678_rebuild_derive_gate.py:473` — fingerprint/function-set gate and automatic stale/current transition coverage.
- `scripts/little_loops/session_store/rebuild_fingerprint.json` — regenerate with this repair's new `REBUILD_DERIVE_VERSION` bump after the final derivation edit (see Sequencing). Update the reachable-function pin (currently 23) with an explanation if a helper is added.

### Dependent Files

- `scripts/little_loops/hooks/user_prompt_submit.py`, `scripts/little_loops/cli/action.py`, `scripts/little_loops/cli/backfill_worker.py`.
- `scripts/little_loops/cli/session.py` — `ll-session skill stats` invocation/success-rate reader.
- `scripts/little_loops/cli/doctor_trim.py:267` — `_usage_counts()` reads invocation rows.
- `scripts/little_loops/cli/logs.py` — correction-to-skill attribution reads the skill table ordered by timestamp. These readers must remain consistent with preserved rows and suppressed replay counts.

### Sequencing

BUG-3761 is done; its survivor re-index and tool-suppression scaffolding is present in `scripts/little_loops/session_store/lifecycle.py:1838`. No unresolved dependency remains. Develop the skill repair in an isolated worktree because this checkout is live in all local-editable consumers.

Ship a **new `REBUILD_DERIVE_VERSION` bump from `bug3761-v1`** in the same change as all skill-preservation logic and the regenerated fingerprint. The append-only migration must complete before rebuild reads `origin`; migration alone must not advertise the new derivation as current. Keep `_FROZEN_LEGACY_DERIVE_VERSION`, `_LEGACY_REBUILD_FLOOR`, and `frozen_legacy_digest` unchanged. Test a store already stamped `bug3761-v1` becoming stale, then current only after successful replay. Stores above `REBUILD_AUTO_MAX_BYTES` must still defer automatic replay.

ENH-3747 shares search deletion/re-indexing but has no required landing order with this fix. Whichever lands later must preserve the earlier survivor logic and regenerate its own derivation fingerprint/version together. This fix prevents future loss; it cannot recover skill rows already wiped by an earlier rebuild without a separate backup.

### Similar Patterns

- BUG-3530 preserves live usage via a channel discriminator. BUG-3715 preserves retention summaries via an existing column. BUG-3761 uses byte/source writer signals for tool/correction preservation; that classifier cannot be reused for skills.

### Tests

- `scripts/tests/test_session_store_lifecycle.py` or a focused `test_bug3766_rebuild_preserves_live_skills.py` — real prompt hook and both public writers; snapshot full rows/IDs, completion fields, search tuples and rebuild stamps; exercise replay-only, mixed, absent/pruned raw sources and three successive rebuilds. Existing regression conventions: `scripts/tests/test_bug3761_rebuild_preserves_live_telemetry.py:94` and `:200`.
- Legacy matrix: unique live anchor; unique path anchor; both anchors on the same tuple; duplicate search rows; multiple base rows sharing a tuple; missing index; invalid/NULL skill name or anchor; completion fields equal to zero or nonzero with only a path twin; stale NULL inserts after the first successful classification. `'legacy'` must remain unchanged after re-indexing and later rebuilds.
- Suppression matrix: equivalent fractional/Z/offset timestamps at the 1s boundary; outside-window, missing and naive timestamps; different arguments; normalized session IDs; NULL/empty sessions; N rapid same-key prompts with M<N eligible hook survivors; unmatched survivors whose own source was pruned; unknown origins and ambiguous legacy rows. A real `skill_event_context()` with a non-NULL session must never suppress, even before it finishes. Stored 200-character argument-prefix collisions must be documented as a limit; no additional fuzzy argument matching is permitted.
- In-flight completion: rebuild inside an active `skill_event_context()` and then exit it with success or failure; the original ID must still receive its completion UPDATE (`scripts/little_loops/session_store/writers.py:868`).
- `scripts/tests/test_session_store_writers.py` — origin stamping, existing capture/kill-switch gates, failure behavior and completion contracts. `_backfill_skill_events()` with omitted suppression still stamps transcript origin and reports inserted rows only; suppression does not inflate the count.
- `scripts/tests/test_session_store_schema.py` — real schema-60 upgrade retaining NULL legacy origins until rebuild, new-column nullability/no default, fresh schema/manifest, and repeat `ensure_db()`. Historical bootstrap convention: `scripts/tests/test_session_store_lifecycle.py:3111`. Repair the BUG-3736 downgrade fixture and current-version literals listed above.
- `scripts/tests/test_backfill_worker_auto_rebuild.py:131` and `scripts/tests/test_enh3678_rebuild_derive_gate.py` — actual automatic stale/current transition and full live-skill preservation, with the existing large-store deferral and ingest-only paths unchanged.
- Late rollback after classification/index restoration/replay or during final stamping: original rows, origins, search entries and rebuild/usage stamps return to their pre-rebuild values. The prior successful schema migration is a separate committed transaction and is not rolled back. Existing controls: `scripts/tests/test_bug3761_rebuild_preserves_live_telemetry.py:288` and `scripts/tests/test_session_store_lifecycle.py:2562`.
- Public search and invocation/success-rate rollups must agree with preserved rows; known hook twins do not systematically double counts, unmatched replay rows remain, and accepted legacy duplicates stay stable across repeated rebuilds. Search assertions compare multisets, not sets.

### Documentation

- `docs/reference/API.md` — session-store writer/rebuild contracts.
- `docs/guides/HISTORY_SESSION_GUIDE.md` — preservation limits, explicit legacy uncertainty/duplicate tolerance, 1s matching window and stored-argument-prefix limit. Legacy survivors lose their original replay path anchor when restored in live style; they are preserved rather than refreshed from raw text. Previously deleted rows require a backup; an old-code rebuild remains destructive even against the new schema.

### Configuration

- Existing analytics skill capture and automatic rebuild size gate apply; no new setting proposed.

## Program Design

### Types

- `skill_events` gains nullable `origin TEXT` (no default): new writers use `'prompt_hook'` | `'skill_host'` | `'transcript'`; classification may use `'legacy'`. NULL is an unclassified/stale-writer row; unknown explicit strings are preserved for forward compatibility. Other columns remain `id`, `ts`, `session_id`, `skill_name`, `args`, `exit_code`, `success`, `duration_ms`. `search_index` contains no base-row ID.
- `_REBUILD_TABLE_PREDICATES["skill_events"] = "origin IS 'transcript'"` — wipes only the replay class.
- Proposed private frozen dataclass `SkillReplaySurvivor`: `id: int`, `session_id: str`, `skill_name: str`, `args: str`, `ts: datetime` (timezone-aware UTC). Only eligible `'prompt_hook'` rows enter the candidate collection; the helper maintains consumption by row ID. This retains multiplicity and timestamp evidence that a count-only key would discard.

### Signatures

- `record_skill_event(db_path: Path | str, session_id: str | None, skill_name: str, args: str, config: dict | None = None) -> None`.
- `skill_event_context(db_path: Path | str = DEFAULT_DB_PATH, session_id: str | None = None, skill_name: str = '', args: str = '', config: dict | None = None) -> Generator[SkillEventCompletion, None, None]`.
- `_backfill_skill_events(conn: sqlite3.Connection, source: list[Path] | sqlite3.Cursor, *, skip_live: Sequence[SkillReplaySurvivor] | None = None) -> int` — proposed optional keyword; writes `origin='transcript'` for inserted records. A matched survivor suppresses both INSERT and `_index()`; return value counts actual replay inserts only, excluding survivors and suppressed rows. Direct calls without `skip_live` remain unsuppressed.
- `rebuild(db: Path | str = DEFAULT_DB_PATH, *, config: dict | None = None, max_sessions: int | None = None) -> dict[str, int]`.

### Call Path

`hooks.user_prompt_submit.handle` -> `record_skill_event`; `cli.action` -> `skill_event_context`; background worker/manual CLI -> `lifecycle.rebuild` -> schema-current connection -> `BEGIN IMMEDIATE` -> legacy classification from original FTS evidence -> predicate-scoped wipe -> survivor re-index/candidate collection -> `_backfill_skill_events(skip_live=...)` -> metadata stamp/commit. Any replay failure rolls back everything after `BEGIN IMMEDIATE`.

### Decision Rules

- Explicit non-NULL origin is never reclassified. For each NULL-origin row, any non-NULL `exit_code`, `success`, or `duration_ms` is positive live-host evidence (including zero); set `'skill_host'` before considering search evidence. All-NULL completion fields alone prove nothing.
- Group original NULL-origin base rows and original kind `skill` FTS rows by exact `(session_id or '', ts, skill_name)`, with FTS columns `(ref, ts, content)`. Count every FTS row, including duplicates. Infer `'transcript'` only when the group has exactly **one** base row and **one** matching search row, the base row has no completion evidence and a valid nonempty string name, and the search anchor is a string different from the skill name containing `/` or `\\` and ending in `.jsonl`. No source-file existence check or timestamp-precision heuristic. Every other NULL row becomes `'legacy'`, including name-only anchors, mixed anchors, duplicate evidence, multiple base rows, and absent evidence.
- Classification runs once per NULL row, inside each rebuild attempt; failed attempts roll it back. No global classification marker. A later stale-process NULL insert is still eligible, but an existing `'legacy'` survivor stays legacy after restoration generates a name anchor.
- Suppression requires `origin == 'prompt_hook'`, all completion fields NULL, a nonempty stored session ID/name, known string arguments, and a parseable timezone-aware timestamp. Replay session IDs normalize exactly as insertion does (`str(value)` for truthy IDs, otherwise `None`); empty/NULL IDs are ineligible. Compare stripped stored argument text (already truncated to 200), without rewriting either row or hashing away its identity.
- Normalize valid `Z`/offset/fractional timestamps to UTC and permit absolute difference `<= 1.0` seconds. Naive, missing or malformed timestamps never suppress. For each replay record in source order, choose the unused eligible candidate with smallest timestamp difference, then smallest row ID; consume it once. Identical same-second invocation keys retain multiset counts rather than collapsing to one row. Different stored arguments and outside-window events remain separate.
- The original full arguments and event UUID are unavailable in `skill_events`; equal stored 200-character prefixes within the window can still be indistinguishable. Document this limit, preserve all unmatched records, and avoid broader fuzzy matching. `'skill_host'`, `'legacy'`, unknown explicit origins and NULL never suppress.
- Only origin-classified transcript rows are replaced. Legacy survivors are intentionally frozen; when their raw twin remains, the newly stamped transcript copy is replaced on later rebuilds rather than added again. This bounds duplicate tolerance without treating generated search anchors as source evidence.

## Implementation Steps

1. Regression coverage establishes full-row preservation, safe legacy classification, bounded matching, active-context completion, public search and atomic rollback using the fixtures in Integration Map. Tests precede the repair.
2. The append-only migration and three writers establish durable origin while preserving existing capture gates, signatures and graceful-degradation behavior. Schema-current connections must precede every origin read; historical remigration fixtures and manifest/version assertions agree with the resulting schema.
3. `rebuild()` preserves all non-transcript rows, restores their search evidence, and matches only eligible hook twins under the Decision Rules. Existing tool/correction/usage preservation remains covered; measured classification/matching work avoids per-row FTS scans and unnecessary work on stores without NULL origins.
4. Documentation states legacy duplicate/anchor limits and recovery boundaries. A new derivation bump from the landed baseline, current fingerprint, reachable-function pin and worker regression tests ship together; frozen legacy values stay unchanged. `python -m pytest scripts/tests/` exits 0.

## Impact

- **Priority**: P1 — silent loss of invocation history and completion telemetry on every full rebuild.
- **Effort**: Medium — provenance and legacy classification need design work beyond the tool/correction predicates.
- **Risk**: Medium — conservative legacy preservation can increase historical counts once; automatic replay and matching must not erase unrelated invocations.
- **Breaking Change**: No public interface change intended.

## Steps to Reproduce

1. Create a temporary local store. Call `record_skill_event(db, 's1', 'ready-issue', 'review-target')`.
2. Enter `skill_event_context(db, session_id='s1', skill_name='ready-issue', args='review-target')`, set the yielded completion's `exit_code=7`, and exit the context.
3. Confirm two base rows, one carrying `exit_code=7`, `success=0`, and non-NULL `duration_ms`, and two kind `skill` search entries.
4. Call `rebuild(db)` with no raw events. Both rows and both search entries disappear. This exact sequence was reproduced on 2026-10-06; no production store was rebuilt.

## Root Cause

`scripts/little_loops/session_store/lifecycle.py:1829` — the delete loop has no skill predicate; all skills are wiped even after BUG-3761. `scripts/little_loops/session_store/writers.py:377`, `:759`, and `:4690` — live/replay writers share the table without origin metadata, and replay never reconstructs completion fields. Both live writers use `anchor=skill_name`; that anchor proves live-style indexing but cannot distinguish a prompt hook from an unfinished skill host. A disposable-store probe on 2026-10-06 reproduced an exact-timestamp live/replay collision where both base rows matched both search anchors, demonstrating why classification cannot pick an arbitrary twin.

## Acceptance Criteria

- [x] Both public live writers survive rebuild with the same IDs, invocation and completion fields, including absent/pruned raw sources. A live context can complete after rebuild and update its original row; legacy classification may update origin only.
- [x] Survivor search entries are restored; explicit replay rows/search entries are replaced without dangling rows or accumulation across three rebuilds. Public search and skill rollups reflect the resulting multiset; legacy duplicate/anchor limits are documented.
- [x] Classification follows the exact Decision Rules: completion evidence wins; only a unique path twin permits transcript inference; ambiguous/name-only/no-twin evidence becomes durable `'legacy'`. Rebuild-generated anchors never change that classification. NULL rows inserted later and unknown explicit origins are preserved; no completion-NULL or precision-only replay inference.
- [x] A newly stamped hook and an eligible transcript twin yield one row; replay-only history remains; rapid repeats consume at most one replay row per eligible survivor. Different arguments, outside-window/invalid timestamps, NULL/empty sessions, skill hosts, legacy rows and unknown origins never suppress. Matching/count behavior and 200-character identity limits are verified and documented.
- [x] Automatic replay from a store stamped `bug3761-v1` preserves skills and becomes current only after success; large stores still defer and ordinary ingest remains ingest-only. Forced failures roll back classification, base rows, search entries and rebuild/usage stamps together, while retaining the separately committed schema migration.
- [x] The new migration, complete repair, new derive-version tag, fingerprint/function-set pin, current schema literals and repaired historical downgrade fixture ship together from an isolated worktree. Existing tool/correction/usage preservation and frozen legacy values remain intact. Classification scans FTS at most once per rebuild with NULL origins; representative added lock time is recorded.
- [ ] `python -m pytest scripts/tests/` exits 0.

## Related Key Documentation

- [Session history guide](../../docs/guides/HISTORY_SESSION_GUIDE.md)
- [Python API reference](../../docs/reference/API.md)

## Resolution

**Fixed** 2026-10-07. Schema v61 adds nullable `skill_events.origin`; the three writers stamp `prompt_hook` / `skill_host` / `transcript`. `rebuild()` classifies NULL-origin rows in-transaction (`_classify_legacy_skill_origins`: completion evidence → `skill_host`; unique `.jsonl` path twin → `transcript`; else `legacy`), wipes only `origin IS 'transcript'`, re-indexes survivors (`_reindex_skill_survivors`) and lets each eligible `prompt_hook` survivor suppress one replay twin (session/name/stored args, ±1s). `REBUILD_DERIVE_VERSION` is now `bug3766-v1`; fingerprint (function-set pin 23→28), manifest, schema literals and the BUG-3736 downgrade fixture updated. Tests: `scripts/tests/test_bug3766_rebuild_preserves_live_skills.py` (35).

- Measured on a disposable synthetic store (50k NULL-origin rows with FTS entries): classification 0.12s, survivor re-index 0.11s. One FTS pass, only when NULL-origin rows exist.
- Deviation: developed in the main checkout, not an isolated worktree.
- Full suite: 29267 passed; 2 unrelated environmental failures — `test_next_loop_golden` (float last-digit mismatch, fails identically on a clean stash) and `test_libsql_integration::TestLive` (expired remote JWT).

## Status

**Done** | Created: 2026-10-06 | Priority: P1


## Session Log
- `/ll:manage-issue` - 2026-10-07T02:16:11 - `8d4a0253-e3d0-4bd3-bb4d-902f480b42bc.jsonl`
- `/ll:ready-issue` - 2026-10-07T02:03:41 - `d37d1bda-b8d2-48a2-869c-a65bb6d2d68c.jsonl`
- `/ll:confidence-check` - 2026-10-07T01:54:59 - `7c74451d-fd76-4629-88f0-c83252b1303a.jsonl`
- `/ll:advise` - 2026-10-07T01:47:11 - `a47df9fa-6eb0-42c9-bccf-a5644c5b0d50.jsonl`
- `/ll:refine-issue` - 2026-10-07T01:47:10 - `a47df9fa-6eb0-42c9-bccf-a5644c5b0d50.jsonl`
- `/ll:capture-issue` - 2026-10-07T00:55:44 - `62355c4f-23ba-4c6f-bf44-9fe87ad6e7af.jsonl`
