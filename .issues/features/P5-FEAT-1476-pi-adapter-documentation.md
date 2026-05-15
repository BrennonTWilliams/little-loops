---
id: FEAT-1476
type: FEAT
priority: P5
status: open
parent: FEAT-992
size: Small
---

# FEAT-1476: Pi Adapter Documentation

## Summary

Update all reference documentation to reflect Pi Coding Agent support: add Pi rows to `HOST_COMPATIBILITY.md`, update the architecture component table, remove Pi from the stub-runner troubleshooting note, and add Pi to the API and configuration references. Coordinate with FEAT-1474 (core adapter) for accurate implementation details.

## Parent Issue

Decomposed from FEAT-992: Add Pi Coding Agent Plugin Compatibility

## Acceptance Criteria

- `docs/reference/HOST_COMPATIBILITY.md` has Pi rows in the hook-intents table (`session_start ✓`, `pre_compact ✓`) and the config-probe-paths table (`.pi/ll-config.json` → `.ll/ll-config.json`)
- `docs/ARCHITECTURE.md` has Pi's `PiRunner` row updated (remove "research deferred") and `pi/` added to the `hooks/adapters/` directory listing
- `docs/development/TROUBLESHOOTING.md` has Pi removed from the stub-runner list in the `HostNotConfigured` section
- `docs/reference/API.md` has `PiRunner` status updated from `stub` to `✓ wired` in the `little_loops.host_runner` runner table
- `docs/reference/CONFIGURATION.md` has a Pi config probe-order note under `hooks.host` enum (`.pi/ll-config.json` probe path), analogous to Codex coverage

## Implementation Steps

1. **`docs/reference/HOST_COMPATIBILITY.md`** — add Pi column/rows to:
   - Hook-intents table: `session_start ✓`, `pre_compact ✓`
   - Config-probe-paths table: `.pi/ll-config.json` → `.ll/ll-config.json`
   - Adapter-locations list: `hooks/adapters/pi/`

2. **`docs/ARCHITECTURE.md`** — update `PiRunner` component table row (~line 570): remove "research deferred" annotation; add `pi/` entry to the `hooks/adapters/` directory tree listing (~line 89)

3. **`docs/development/TROUBLESHOOTING.md`** — remove Pi from the stub-runner note in the `HostNotConfigured` section (~line 308) once `PiRunner.build_*` methods ship from FEAT-1474

4. **`docs/reference/API.md`** — change `PiRunner` status from `stub` to `✓ wired` in the `little_loops.host_runner` runner table

5. **`docs/reference/CONFIGURATION.md`** — add Pi-specific config probe-order documentation under the `hooks.host` enum description (`.pi/ll-config.json` candidate path)

## Files to Modify

- `docs/reference/HOST_COMPATIBILITY.md`
- `docs/ARCHITECTURE.md`
- `docs/development/TROUBLESHOOTING.md`
- `docs/reference/API.md`
- `docs/reference/CONFIGURATION.md`

## Notes

- This child can be written largely in parallel with FEAT-1474 (core adapter) and FEAT-1475 (init skill), but the adapter files from FEAT-1474 should exist before finalizing exact file references in README.
- `docs/development/TROUBLESHOOTING.md` step 3 depends on FEAT-1474 completing the `PiRunner.build_*` implementation; if those methods are deferred, note Pi as still-gated in the troubleshooting doc rather than removing the note prematurely.

## Impact

- **Priority**: P5
- **Effort**: Small
- **Risk**: Very low — documentation only

## Status

**Open** | Created: 2026-05-15 | Priority: P5

## Session Log
- `/ll:issue-size-review` - 2026-05-15T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/59179ce1-13d5-40c7-bdca-8b3c6117c43e.jsonl`
