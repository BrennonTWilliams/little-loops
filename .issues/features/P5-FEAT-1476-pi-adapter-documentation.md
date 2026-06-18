---
id: FEAT-1476
title: Pi Adapter Documentation
type: FEAT
priority: P5
status: open
depends_on: [FEAT-1475, FEAT-1478, FEAT-1479, FEAT-1480]
parent: EPIC-1622
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

## Verification Notes

_Added by `/ll:verify-issues` on 2026-06-01_

**Verdict: OUTDATED** — Documentation updates not yet made:
- `docs/reference/HOST_COMPATIBILITY.md` has no Pi rows — only claude-code, opencode, and codex hosts are present
- No Pi sections added to ARCHITECTURE.md, TROUBLESHOOTING.md, API.md, or CONFIGURATION.md
- Issue is blocked on FEAT-1478 (Pi adapter itself) which is also unstarted
- 2026-06-13 (OUTDATED): Documentation updates cannot start until FEAT-1478 creates `hooks/adapters/pi/` and related files. HOST_COMPATIBILITY.md has no Pi rows; ARCHITECTURE.md, TROUBLESHOOTING.md, API.md, CONFIGURATION.md lack Pi sections — all confirmed missing as expected. No changes needed until FEAT-1478 merges.
- 2026-06-18 (OUTDATED): No Pi rows in HOST_COMPATIBILITY.md; ARCHITECTURE.md, TROUBLESHOOTING.md, API.md, CONFIGURATION.md all still lack Pi sections. `hooks/adapters/pi/` does not exist (FEAT-1478 unstarted). Doc updates correctly gated on FEAT-1478. No new findings.

## Status

**Open** | Created: 2026-05-15 | Priority: P5

## Session Log
- `/ll:verify-issues` - 2026-06-14T00:14:14 - `7db6ce0f-4d7c-486d-927d-6804d39ee7b7.jsonl`
- `/ll:verify-issues` - 2026-06-05T21:00:23 - `current-session.jsonl`
- `/ll:audit-issue-conflicts` - 2026-06-03T21:54:23 - `882d6aa0-cbf0-47c3-9d9c-32d8d6c6ef92.jsonl`
- `/ll:verify-issues` - 2026-06-02T22:48:54 - `a5f82118-5be7-4fc3-afac-e29effcffd8b.jsonl`
- `/ll:verify-issues` - 2026-06-01T14:29:19 - `f3a091ba-2869-499e-9de4-7f5c8ca96083.jsonl`
- `/ll:audit-issue-conflicts` - 2026-05-31T21:48:17 - `6805d559-982e-47e7-9513-9c8b17a1c054.jsonl`
- `/ll:verify-issues` - 2026-05-31T05:40:10 - `e9b1fe44-19f3-4b83-9d6b-0194f265fb9a.jsonl`
- `/ll:verify-issues` - 2026-05-31T02:30:15 - `5267cfef-4fe8-420d-9d08-62e8f926a297.jsonl`
- `/ll:audit-issue-conflicts` - 2026-05-24T06:05:46 - `8cdfeedd-6a9f-4683-a41d-9ff3860ac7e0.jsonl`
- `/ll:verify-issues` - 2026-05-23T00:35:44 - `2955f8fa-d24c-40f9-9d2d-3d46811662f9.jsonl`
- `/ll:issue-size-review` - 2026-05-15T00:00:00 - `59179ce1-13d5-40c7-bdca-8b3c6117c43e.jsonl`

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): `hooks/adapters/pi/README.md` is created by FEAT-1478 and covers adapter-local event mapping and install instructions. This issue (FEAT-1476) owns `docs/reference/HOST_COMPATIBILITY.md` — the authoritative host-level parity table. These two documents are complementary: the README is a quick-start reference for adapter users; HOST_COMPATIBILITY.md is the canonical cross-host comparison matrix. The README should cross-reference HOST_COMPATIBILITY.md but not duplicate its content. FEAT-1476's doc updates are NOT in FEAT-1478's scope.
