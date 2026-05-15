---
id: BUG-1461
type: BUG
priority: P3
status: open
discovered_date: 2026-05-14
discovered_by: verify-issues
relates_to: [FEAT-948]
---

# BUG-1461: `continuation.auto_detect_on_session_start` flag is documented but not read by any code

## Summary

The `continuation.auto_detect_on_session_start` boolean is documented in `docs/guides/SESSION_HANDOFF.md`, `docs/reference/CONFIGURATION.md`, and declared in `config-schema.json` as if it were a working setting, but no code anywhere reads it. Setting it to `false` has no effect.

## Current Behavior

- `config-schema.json:552` defines the property with `type: boolean` and description "Check for continuation prompt when session starts".
- `docs/reference/CONFIGURATION.md:116,396` shows it in example config and the settings table.
- `docs/guides/SESSION_HANDOFF.md:292,314,331` documents the on/off behavior and states: "When `continuation.auto_detect_on_session_start` is `true` (the default), little-loops checks for an existing `.ll/ll-continue-prompt.md` at the beginning of each session."
- A grep across `scripts/`, `hooks/`, and `commands/` for `auto_detect_on_session_start` finds **only** the schema and doc references — no implementation reads the flag.

## Expected Behavior

Either:

1. **Implement the flag**: have the SessionStart hook intent (`scripts/little_loops/hooks/session_start.py`) check the flag before printing the continuation-prompt detection notice — or
2. **Remove the documentation**: delete the flag from `config-schema.json`, both docs files, and the example configs, since it does nothing today.

Option 2 is likely the right move if the SessionStart inject feature stays deferred (FEAT-1315 was deferred by the same verify pass that found this).

## Source

Discovered during `/ll:verify-issues` on 2026-05-14 while verifying the FEAT-1315/1316/1317 session-start-inject series. The hook-verification agent surfaced it as a separate doc-accuracy concern from the architecture supersession.

## Acceptance Criteria

- Pick a direction (implement OR remove) and apply it consistently across `config-schema.json`, `docs/guides/SESSION_HANDOFF.md`, `docs/reference/CONFIGURATION.md`.
- If removing: also remove from example configs and any `ll-config.json` files in `templates/`.
- If implementing: add a test that asserts the flag suppresses the continuation-detection notice when set to `false`.

## Impact

- **Severity**: Low — misleading documentation, but no functional regression (the underlying continuation-detection feature itself is not wired up either).
- **Effort**: Small — text-only change (Option 2) or small handler edit + test (Option 1).
- **Risk**: Low.

## Labels

`bug`, `documentation`, `hooks`, `verify-issues`


## Session Log
- `/ll:audit-issue-conflicts` - 2026-05-14T21:23:11 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/75505ad4-6733-4424-b334-3143f412786b.jsonl`
- `/ll:verify-issues` - 2026-05-14T20:42:06 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/08e4ebf6-4da6-445a-91f6-ae578f565978.jsonl`
