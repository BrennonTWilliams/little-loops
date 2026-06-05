---
id: FEAT-1158
type: FEAT
priority: P3
status: deferred
discovered_date: 2026-04-18
discovered_by: issue-size-review
blocked_by: [FEAT-1112, FEAT-1156]
parent: FEAT-1113

relates_to: ['FEAT-1156', 'FEAT-1157']
---

# FEAT-1158: PreCompact Handoff Hook — Docs & Configuration

## Summary

Update all documentation, configuration schema, templates, and peripheral config files to reflect the new `precompact-handoff.sh` hook introduced by FEAT-1156.

## Parent Issue

Decomposed from FEAT-1113: PreCompact Auto-Handoff Hook

## Acceptance Criteria

- `docs/guides/SESSION_HANDOFF.md` describes automatic PreCompact trigger alongside manual `/ll:handoff`
- `docs/ARCHITECTURE.md:85-98` lists `precompact-handoff.sh` in the scripts directory
- `docs/ARCHITECTURE.md:888-955` flow diagram shows PreCompact as a second handoff trigger path (not PostToolUse-only)
- `docs/development/TROUBLESHOOTING.md:753` chmod list includes `precompact-handoff.sh`
- `docs/development/TROUBLESHOOTING.md:939-942` manual test invocation block has parallel entry for `precompact-handoff.sh`
- `docs/development/TROUBLESHOOTING.md:972` timeout list includes `precompact-handoff.sh`
- `skills/configure/areas.md:867` hook audit table has a row for `precompact-handoff.sh`
- If feature flag introduced: `config-schema.json` has a new top-level `precompact_handoff` section (NOT under `context_monitor` — it has `additionalProperties: false`)
- If feature flag introduced: all 9 `templates/*.json` have `"precompact_handoff": {"enabled": true}` alongside `context_monitor`
- `docs/reference/CONFIGURATION.md` `context_monitor` table updated (or new `precompact_handoff` section added) if config keys are introduced

## Implementation

### Decision Required First

Decide whether `precompact_handoff` is opt-in (feature flag in config) or always-on. This determines whether `config-schema.json` and `templates/*.json` need updating.

- **Always-on** (preferred unless users report noise): no config changes needed; just docs.
- **Opt-in**: add `"precompact_handoff": {"type": "object", ...}` to `config-schema.json` at top level; add `"precompact_handoff": {"enabled": true}` to all 9 template files.

### Documentation Updates

1. `docs/guides/SESSION_HANDOFF.md` — add section explaining PreCompact auto-trigger; clarify `/ll:handoff` is now a manual override for the richer version
2. `docs/ARCHITECTURE.md:85-98` — add `precompact-handoff.sh` line in hooks/scripts/ directory listing
3. `docs/ARCHITECTURE.md:888-955` — update context-monitor flow diagram to show two handoff trigger paths: PostToolUse (existing) + PreCompact (new)
4. `docs/development/TROUBLESHOOTING.md:753` — add `chmod +x hooks/scripts/precompact-handoff.sh`
5. `docs/development/TROUBLESHOOTING.md:939-942` — add manual invocation example parallel to `precompact-state.sh` block
6. `docs/development/TROUBLESHOOTING.md:972` — add `precompact-handoff.sh` to the timeout reference list

### Configuration (if opt-in)

7. `config-schema.json` — new top-level section `precompact_handoff`
8. `templates/generic.json` + 8 other templates — add `"precompact_handoff": {"enabled": true}`
9. `docs/reference/CONFIGURATION.md` — document the new config key

### Skill Config Audit Display

10. `skills/configure/areas.md:867` — add row: `[Plugin] PreCompact * precompact-handoff.sh 5s` (or whatever timeout is configured)

## Files to Modify

- `docs/guides/SESSION_HANDOFF.md`
- `docs/ARCHITECTURE.md` (lines 85-98 and 888-955)
- `docs/development/TROUBLESHOOTING.md` (lines 753, 939-942, 972)
- `skills/configure/areas.md` (line 867)
- `config-schema.json` (if opt-in)
- `templates/*.json` — all 9 files (if opt-in)
- `docs/reference/CONFIGURATION.md` (if opt-in)

## References

- Depends on: FEAT-1156 (hook must exist before docs can be accurate)
- Tests: FEAT-1157

## Verification Notes

**Verdict**: VALID — Verified 2026-04-23

- `docs/guides/SESSION_HANDOFF.md` has no automatic PreCompact trigger section ✓
- `docs/ARCHITECTURE.md:85-98` does not list `precompact-handoff.sh` ✓
- `skills/configure/areas.md:867` has no row for `precompact-handoff.sh` ✓
- Blocked by FEAT-1156 (hook must exist before docs can be accurate) ✓
- Feature not yet implemented ✓

## Session Log
- `/ll:verify-issues` - 2026-05-14T20:42:05 - `08e4ebf6-4da6-445a-91f6-ae578f565978.jsonl`
- `/ll:audit-issue-conflicts` - 2026-05-10T14:27:59 - `87aa3665-7b97-4854-8ebd-2e34e4875ba6.jsonl`
- `/ll:verify-issues` - 2026-05-03T15:21:15 - `8fe967ae-751c-4941-ab43-61b0cce639c5.jsonl`
- `/ll:verify-issues` - 2026-04-26T19:34:07 - `316256f6-01c2-468b-8efc-2db79aff6b29.jsonl`
- `/ll:verify-issues` - 2026-04-24T03:02:16 - `1faa7404-23ae-4397-94a1-06150dae54dd.jsonl`

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): This issue edits `docs/ARCHITECTURE.md`, `docs/guides/SESSION_HANDOFF.md`, and `skills/configure/areas.md` for the precompact handoff feature. These same files are also modified by the session-start inject doc family: FEAT-1317 (`docs/ARCHITECTURE.md`), FEAT-1318 (`docs/guides/SESSION_HANDOFF.md`), FEAT-1319 (`skills/configure/areas.md`). No ordering dependency exists between these two doc families. If worked concurrently, coordinate to avoid git merge conflicts in these three shared files.
