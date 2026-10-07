---
id: BUG-3766
type: BUG
title: Rebuild wipes live skill telemetry and completion fields
priority: P1
status: open
discovered_by: ll-issues-create
discovered_date: '2026-10-06'
captured_at: '2026-10-07T00:53:14Z'
labels:
- history
- telemetry
- data-loss
testable: true
decision_needed: false
depends_on:
- BUG-3761
relates_to:
- ENH-3747
---

# BUG-3766: Rebuild wipes live skill telemetry and completion fields

## Summary

`rebuild()` deletes every `skill_events` row and every `search_index` row of kind `skill` before replay. `record_skill_event()` and `skill_event_context()` also write this table directly without `raw_events`. Replay cannot restore completion fields (`exit_code`, `success`, `duration_ms`), and may not recreate the invocation at all. Confirmed while reviewing BUG-3761 on branch `main`; keep the tool/correction repair and this skill-specific provenance repair coordinated.

## Current Behavior

- `scripts/little_loops/session_store/lifecycle.py` — `_REBUILD_TABLES` contains the skill-events table; `_REBUILD_TABLE_PREDICATES` has no skill exception; `rebuild()` deletes kind `skill` search entries unconditionally.
- `scripts/little_loops/session_store/writers.py` — `record_skill_event()` writes a live invocation and search entry; `skill_event_context()` writes another live invocation and updates completion fields on exit. Neither writes a raw event.
- `scripts/little_loops/hooks/user_prompt_submit.py` — `handle()` calls `record_skill_event()` for plain `/ll:<name>` prompts. `scripts/little_loops/cli/action.py` calls `skill_event_context()` for executed actions.
- `scripts/little_loops/session_store/writers.py` — `_backfill_skill_events()` mines `<command-name>/ll:...` user transcript text and writes only timestamp/session/name/args. Its search anchor is the source path; live anchors are the skill name. Live hook rows without completion fields otherwise resemble replay rows, so a completion-field-only predicate is insufficient.

## Expected Behavior

Live skill invocations, completion fields, and their existing search evidence survive manual and derive-version-triggered rebuilds. Replay-derived skill rows are replaced without accumulating across repeated rebuilds. Source deletion/pruning does not destroy live invocation history.

## Motivation

Repeated full rebuilds silently discard skill execution outcomes and invocation history in every local-editable consumer. A derive-version change can trigger the loss automatically, so this provenance gap must remain visible while coordinating the tool/correction repair in BUG-3761.

## Proposed Solution

**Selected: Option A — nullable `skill_events.origin` column via an append-only migration, plus replay-twin suppression.**

1. **Provenance column.** Add `origin TEXT` (no default). `record_skill_event()` writes `'prompt_hook'`, `skill_event_context()` writes `'skill_host'`, `_backfill_skill_events()` writes `'transcript'`. Add `"skill_events": "origin IS 'transcript'"` to `_REBUILD_TABLE_PREDICATES` (a literal; `_literal()` reads it with `ast.literal_eval`). The predicate names the replay class, so NULL origin (legacy rows, stale pre-migration processes still writing) is always preserved. Never invert it to `origin IS NOT <live>`.
2. **Legacy classification.** Classify only NULL-origin rows, once, using the existing search twin `(kind='skill', ref=session_id or '', ts, content=skill_name)`: anchor `== skill_name` → `'prompt_hook'`; anchor looks like a source path → `'transcript'`; no twin → leave NULL (preserved as live). Never classify by completion fields or timestamp precision. Prefer running this lazily at the start of `rebuild()` (same transaction) over inside the migration: the migration runs on every connect, including hook writes, and a full `search_index` scan (about 0.6s on 2.1M rows) would blow the hook budget.
3. **Search entries.** Follow BUG-3761: keep the blanket `kind IN (...)` delete, then re-index every surviving `skill_events` row with `_index()` using the live-writer convention (`content=skill_name`, `kind='skill'`, `ref=session_id or ''`, `anchor=skill_name`, `ts=row ts`). Orphans vanish; entries missing before the rebuild are restored as a side effect.
4. **Twin suppression.** Preserving live rows without suppression doubles skill counts after the first post-fix rebuild: the hook row and the replayed `<command-name>/ll:x</command-name>` record describe the same prompt. A live-store probe found 560 of 562 hook rows with a replay twin within 1s. Mirror BUG-3761's mechanism: after the predicate-scoped deletes, build a multiset (Counter) of surviving `prompt_hook`/legacy-NULL rows keyed `(session_id, skill_name)` with non-NULL `session_id`, pass it to `_backfill_skill_events()` through a new optional keyword (default `None` keeps legacy behavior), and skip both the INSERT and `_index()` for a record whose key has a remaining count (decrement it). Match on the key, not on `ts`: the hook stamps second-precision `_now()` while replay copies the transcript timestamp. `skill_host` rows (`ll-action`, usually NULL session, no transcript tag) never suppress and are never replayed.

### Decision Rationale

Option A selected 2026-10-07 after `/ll:advise` (claude-opus-5-5, confidence 0.8). Skill rows, unlike tool/correction rows, carry no writer-distinguishing column, so a pure predicate must borrow provenance from the derived FTS index. A real column makes origin a base-row fact and keeps the replay predicate trivial; legacy ambiguity is handled by preserve-by-default.

Rejected Option B (no migration, predicate on search anchor `== skill_name`): consistent with BUG-3761's precedent and currently 100% consistent with timestamp precision on the live store, but it couples base-row provenance to a derived index and cannot classify un-indexed rows. Advisor dissent also noted twin suppression could split into a follow-up ENH; rejected, because the fix itself would otherwise ship a systematic 2x skill-count regression.

## Integration Map

### Files to Modify

- `scripts/little_loops/session_store/lifecycle.py` — skill deletion and kind `skill` index selection in `rebuild()`.
- `scripts/little_loops/session_store/writers.py` — live/replay skill writer provenance contracts.
- `scripts/little_loops/session_store/schema.py` and `schema_manifest.json` — append-only migration adding `skill_events.origin`; bump `SCHEMA_VERSION`; update the explicit version literal in `scripts/tests/test_bug3736_usage_replay_holds.py::test_migration_creates_holds_table_and_keeps_version_constants`.
- `scripts/little_loops/session_store/rebuild_fingerprint.json` — regenerate after the final derivation edit and the single shared `REBUILD_DERIVE_VERSION` bump (see Sequencing). Update the reachable-function pin (currently 23) with an explanation if a helper is added.

### Dependent Files

- `scripts/little_loops/hooks/user_prompt_submit.py`, `scripts/little_loops/cli/action.py`, `scripts/little_loops/cli/backfill_worker.py`.
- Readers whose counts change when replay twins are suppressed or live rows survive: `ll-session skill stats` (`scripts/little_loops/cli/session.py`), `scripts/little_loops/cli/doctor_trim.py` (`skill_events` usage rows), and `scripts/little_loops/cli/logs.py` (correction-to-skill attribution reads `skill_events ORDER BY ts`).

### Sequencing

BUG-3766 `depends_on` BUG-3761: it reuses BUG-3761's survivor re-index step and replay-suppression pattern, adding `skill_events`/`kind='skill'` to them. Land both on one branch with **a single `REBUILD_DERIVE_VERSION` bump**. Shipping BUG-3761's bump alone auto-rebuilds stores at or below `REBUILD_AUTO_MAX_BYTES` and wipes live skill rows before this fix exists. The migration must run before the first rebuild. ENH-3747 shares the same deletion path; it bumps afterward and must not drop the skill exclusions.

### Similar Patterns

- BUG-3530 preserves live usage via a channel discriminator. BUG-3715 preserves retention summaries via an existing column. BUG-3761 uses byte/source writer signals for tool/correction preservation; that classifier cannot be reused for skills.

### Tests

- Extend `scripts/tests/test_session_store_lifecycle.py` using both real live skill writers, replayed command-name fixtures, missing/pruned raw sources, legacy classification (anchor == name, anchor == path, no twin), repeated rebuilds, NULL session IDs, and rollback.
- Twin suppression: hook row + transcript twin yields one row after rebuild; replay-only session (no hook row) keeps its replay row; N rapid same-skill prompts with M<N hook rows suppress exactly M replay rows; `skill_host`/NULL-session rows never suppress; counts stable across repeated rebuilds.
- Writer contracts in `scripts/tests/test_session_store_writers.py`: each writer stamps its `origin`; stale NULL-origin insert survives rebuild.
- A repeatable twin-delta probe (skill counts before/after a rebuild on a fixture store) asserts no 2x regression.
- Exercise public FTS search and the automatic worker through `scripts/tests/test_backfill_worker_auto_rebuild.py`; update version/migration gates appropriate to the selected design.

### Documentation

- `docs/reference/API.md` — session-store writer/rebuild contracts.
- `docs/guides/HISTORY_SESSION_GUIDE.md` — rebuild preservation limits, including legacy NULL-origin rows and that ambiguous rows are preserved, not replayed.

### Configuration

- Existing analytics skill capture and automatic rebuild size gate apply; no new setting proposed.

## Program Design

### Types

- `skill_events` gains `origin TEXT` (nullable, no default): `'prompt_hook'` | `'skill_host'` | `'transcript'` | NULL (legacy/unclassified, preserved). Other columns: `ts`, `session_id`, `skill_name`, `args`, `exit_code`, `success`, `duration_ms`. `search_index` contains no base-row ID.
- `_REBUILD_TABLE_PREDICATES["skill_events"] = "origin IS 'transcript'"` — wipes only the replay class.
- Survivor suppression key: `Counter[tuple[str, str]]` of `(session_id, skill_name)` for surviving non-`skill_host` rows with non-NULL `session_id`.

### Signatures

- `record_skill_event(db_path: Path | str, session_id: str | None, skill_name: str, args: str, config: dict | None = None) -> None`.
- `skill_event_context(db_path: Path | str = DEFAULT_DB_PATH, session_id: str | None = None, skill_name: str = '', args: str = '', config: dict | None = None) -> Generator[SkillEventCompletion, None, None]`.
- `_backfill_skill_events(conn: sqlite3.Connection, source: list[Path] | sqlite3.Cursor, *, suppress: Counter[tuple[str, str]] | None = None) -> int` — writes `origin='transcript'`; a record whose key has a remaining count in `suppress` decrements it and skips INSERT and `_index()`.
- `rebuild(db: Path | str = DEFAULT_DB_PATH, *, config: dict | None = None, max_sessions: int | None = None) -> dict[str, int]`.

### Call Path

`hooks.user_prompt_submit.handle` -> `record_skill_event`; `cli.action` -> `skill_event_context`; `lifecycle.rebuild` -> legacy origin classification -> predicate-scoped skill wipe -> survivor re-index -> `_backfill_skill_events(suppress=...)` -> metadata stamp.

## Implementation Steps

1. Land (or branch from) BUG-3761's survivor re-index and suppression scaffolding.
2. Add regression cases (tests first) for hook-only and completion-bearing live skills, replay, twin suppression, legacy classification, missing sources, and transaction rollback.
3. Add the `origin` migration; stamp `origin` in all three writers; add the predicate, lazy legacy classification, skill survivor re-index, and `_backfill_skill_events(suppress=...)`.
4. Update docs, regenerate the fingerprint with the single shared version bump, update the migration version-literal test, and run the full local suite.

## Impact

- **Priority**: P1 — silent loss of invocation history and completion telemetry on every full rebuild.
- **Effort**: Medium — provenance and legacy classification need design work beyond the tool/correction predicates.
- **Risk**: Medium — origin ambiguity and automatic replay make preservation and rollout ordering critical.
- **Breaking Change**: No public interface change intended.

## Steps to Reproduce

1. Create a temporary local store. Call `record_skill_event(db, 's1', 'ready-issue', 'review-target')`.
2. Enter `skill_event_context(db, session_id='s1', skill_name='ready-issue', args='review-target')`, set the yielded completion's `exit_code=7`, and exit the context.
3. Confirm two base rows, one carrying `exit_code=7`, `success=0`, and non-NULL `duration_ms`, and two kind `skill` search entries.
4. Call `rebuild(db)` with no raw events. Both rows and both search entries disappear. This exact sequence was reproduced on 2026-10-06; no production store was rebuilt.

## Root Cause

`scripts/little_loops/session_store/lifecycle.py` — `rebuild()` assumes all skill rows are replay-derived. `scripts/little_loops/session_store/writers.py` — live and replay skill writers share the table without durable origin metadata. Replay never reconstructs completion fields.

## Acceptance Criteria

- [ ] Both `record_skill_event()` and `skill_event_context()` rows survive rebuild unchanged, including IDs and completion fields, with no replay source available.
- [ ] Existing indexed live skills remain searchable (re-indexed from surviving rows); replay entries are replaced without duplicate growth or dangling entries across repeated rebuilds.
- [ ] Legacy origin classification is explicit and verified: anchor == skill name → live, path anchor → replay, no search twin → preserved. Completion columns alone never classify hook rows. NULL-origin rows are always preserved.
- [ ] A live hook row and its transcript twin yield exactly one row after rebuild; replay-only sessions keep their replay rows; rapid same-skill repeats suppress no more replay rows than surviving live rows; `skill_host` and NULL-session rows never suppress. Skill counts do not double versus the pre-rebuild store (twin-delta probe).
- [ ] Automatic derive-version rebuilds use the same preservation semantics; forced failures roll back base rows, search entries, and stamps together.
- [ ] The derive-version bump ships once, together with BUG-3761's and this issue's preservation logic, from an isolated worktree; the migration runs before the first rebuild; fingerprint, manifest, and version-literal gates are updated.
- [ ] `python -m pytest scripts/tests/` exits 0.

## Related Key Documentation

- [Session history guide](../../docs/guides/HISTORY_SESSION_GUIDE.md)
- [Python API reference](../../docs/reference/API.md)

## Status

**Open** | Created: 2026-10-06 | Priority: P1


## Session Log
- `/ll:capture-issue` - 2026-10-07T00:55:44 - `62355c4f-23ba-4c6f-bf44-9fe87ad6e7af.jsonl`
