---
id: ENH-3678
type: ENH
title: Gate the auto-spawned history rebuild on a derive version instead of SCHEMA_VERSION
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-30'
captured_at: '2026-09-30T00:31:00Z'
---

# ENH-3678: Gate the auto-spawned history rebuild on a derive version instead of SCHEMA_VERSION

## Summary

Stop the SessionStart hook from spawning a full `backfill_worker --rebuild` on every `SCHEMA_VERSION` bump. Gate the auto-rebuild on a dedicated derive version that changes only when parser or `_REBUILD_TABLES` derivation semantics change, add a single-flight guard, and make the auto-spawn opt-in above a store-size threshold. Split out of ENH-3666 after its 2026-09-29 pre-implementation Opus review.

## Current Behavior

`hooks/session_start.py` (~`:213`) adds `--rebuild` whenever `meta.last_rebuild_version < SCHEMA_VERSION` (currently 58). About 20 bumps since June, several of which (e.g. the `harness_events` and harness-column bumps) change no `_REBUILD_TABLES` derivation, each force a full wipe-and-replay of a multi-GB store. There is no single-flight guard: every SessionStart during a multi-minute rebuild spawns another `--rebuild`. A ~9.6 GB store held the write lock for minutes and dropped concurrent `ll-*` telemetry rows.

## Expected Behavior

- A `REBUILD_DERIVE_VERSION` constant in `session_store/lifecycle.py` plus a `rebuild_derive_version` meta key (inline upsert, not in the `usage_derive_` namespace); the hook compares against it instead of `SCHEMA_VERSION`. `rebuild()` stamps it on success alongside `last_rebuild_version`.
- Migration: if `last_rebuild_version >= 58` stamp the current derive version without rebuilding; otherwise rebuild once. Record the risk that a store whose last rebuild predates a real derivation change could skip a needed rebuild, and choose the stamp threshold deliberately.
- A flock so only one `--rebuild` runs at a time (a second spawn exits immediately).
- Above a size threshold (e.g. 1 GB, configurable) the hook does not auto-spawn `--rebuild`; it reports "rebuild pending" (SessionStart output / `ll-doctor`) and the user runs `ll-session rebuild` explicitly.

## Impact

- **Priority**: [P0-P5] - [Justification]
- **Effort**: [Small/Medium/Large] - [Justification]
- **Risk**: [Low/Medium/High] - [Justification]
- **Breaking Change**: [Yes/No]

## Acceptance Criteria

- [ ] A `SCHEMA_VERSION` bump that does not change derivation does not trigger a rebuild; a `REBUILD_DERIVE_VERSION` bump does.
- [ ] Two concurrent `--rebuild` workers: the second exits without touching the DB.
- [ ] Above the size threshold the hook spawns no `--rebuild` and surfaces a pending notice.
- [ ] `test_hook_session_start.py::TestSessionStartRebuild` updated to the new gate; remote stores still never rebuild from a hook.
- [ ] Docs (`HISTORY_SESSION_GUIDE.md`, `CLI.md`, `API.md`, `ARCHITECTURE.md` `last_rebuild_version` wording) updated in end-user shape.

## Related

- ENH-3666 (structural fix; now blocked by this issue), ENH-3678 (telemetry writer resilience).

## Status

**Open** | Created: 2026-09-30 | Priority: P2
