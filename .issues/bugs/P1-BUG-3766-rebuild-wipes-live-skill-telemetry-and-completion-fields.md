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
decision_needed: true
relates_to:
- BUG-3761
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

Establish a reliable live/replay discriminator for all three skill writers, with a legacy-row preservation policy. Consider an append-only provenance migration or a proven existing signal; do not classify by timestamp precision or completion fields alone. Retain or reconstruct search evidence against surviving rows in the same transaction. Inspect whether legacy rows without an index entry can be classified before selecting the implementation; do not silently treat them as proven replay data.

## Integration Map

### Files to Modify

- `scripts/little_loops/session_store/lifecycle.py` — skill deletion and kind `skill` index selection in `rebuild()`.
- `scripts/little_loops/session_store/writers.py` — live/replay skill writer provenance contracts.
- `scripts/little_loops/session_store/schema.py` and `schema_manifest.json` — only if the selected design requires a migration.
- `scripts/little_loops/session_store/rebuild_fingerprint.json` — regenerate with any non-usage derivation change and version bump.

### Dependent Files

- `scripts/little_loops/hooks/user_prompt_submit.py`, `scripts/little_loops/cli/action.py`, `scripts/little_loops/cli/backfill_worker.py`.
- BUG-3761 and ENH-3747 share the `rebuild()` index deletion path. Coordinate predicates and version bumps; these are related work, not prerequisite edges.

### Similar Patterns

- BUG-3530 preserves live usage via a channel discriminator. BUG-3715 preserves retention summaries via an existing column. BUG-3761 uses byte/source writer signals for tool/correction preservation; that classifier cannot be reused for skills.

### Tests

- Extend `scripts/tests/test_session_store_lifecycle.py` using both real live skill writers, replayed command-name fixtures, missing/pruned raw sources, legacy classification, repeated rebuilds, NULL session IDs, and rollback.
- Exercise public FTS search and the automatic worker through `scripts/tests/test_backfill_worker_auto_rebuild.py`; update version/migration gates appropriate to the selected design.

### Documentation

- `docs/reference/API.md` — session-store writer/rebuild contracts.
- `docs/guides/HISTORY_SESSION_GUIDE.md` — rebuild preservation limits.

### Configuration

- Existing analytics skill capture and automatic rebuild size gate apply; no new setting proposed.

## Program Design

### Types

- `skill_events` includes `ts`, `session_id`, `skill_name`, `args`, `exit_code`, `success`, and `duration_ms`; `search_index` contains no base-row ID.
- `_REBUILD_TABLE_PREDICATES: dict[str, str]` — eventual skill wipe predicate must preserve both live writer classes. Origin representation requires refinement before implementation.

### Signatures

- `record_skill_event(db_path: Path | str, session_id: str | None, skill_name: str, args: str, config: dict | None = None) -> None`.
- `skill_event_context(db_path: Path | str = DEFAULT_DB_PATH, session_id: str | None = None, skill_name: str = '', args: str = '', config: dict | None = None) -> Generator[SkillEventCompletion, None, None]`.
- `_backfill_skill_events(conn: sqlite3.Connection, source: list[Path] | sqlite3.Cursor) -> int`.
- `rebuild(db: Path | str = DEFAULT_DB_PATH, *, config: dict | None = None, max_sessions: int | None = None) -> dict[str, int]`.

### Call Path

`hooks.user_prompt_submit.handle` -> `record_skill_event`; `cli.action` -> `skill_event_context`; `lifecycle.rebuild` -> skill wipe -> `_backfill_skill_events` -> metadata stamp.

## Implementation Steps

1. Refine and choose the provenance/legacy classification design using all three writers and their index conventions.
2. Add regression cases for hook-only and completion-bearing live skills, replay, missing sources, and transaction rollback.
3. Implement atomic base/index preservation and any required migration; coordinate the shared deletion code with BUG-3761 and ENH-3747.
4. Update documentation, derive fingerprint/version gates, and run the full local suite.

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
- [ ] Existing indexed live skills remain searchable; replay entries are replaced without duplicate growth or dangling entries across repeated rebuilds.
- [ ] Legacy origin classification is explicit, verified, and preserves ambiguous live evidence; completion columns alone do not classify hook rows.
- [ ] Automatic derive-version rebuilds use the same preservation semantics; forced failures roll back base rows, search entries, and stamps together.
- [ ] The derive-version bump and preservation logic ship together from an isolated worktree; any migration runs before the first rebuild.
- [ ] `python -m pytest scripts/tests/` exits 0.

## Related Key Documentation

- [Session history guide](../../docs/guides/HISTORY_SESSION_GUIDE.md)
- [Python API reference](../../docs/reference/API.md)

## Status

**Open** | Created: 2026-10-06 | Priority: P1


## Session Log
- `/ll:capture-issue` - 2026-10-07T00:55:44 - `62355c4f-23ba-4c6f-bf44-9fe87ad6e7af.jsonl`
