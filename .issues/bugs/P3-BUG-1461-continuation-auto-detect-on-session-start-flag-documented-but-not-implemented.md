---
id: BUG-1461
title: `continuation.auto_detect_on_session_start` flag is documented but not read by any code
type: BUG
priority: P3
status: open
testable: false
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

## Steps to Reproduce

1. In a little-loops project, set `continuation.auto_detect_on_session_start: false` in `.ll/ll-config.json`.
2. Drop a `.ll/ll-continue-prompt.md` file into the project to simulate a pending continuation prompt.
3. Start a new Claude Code session in the project.
4. Observe: the continuation-detection behavior is unchanged by the flag — code never reads it, so toggling the value has no effect.

## Root Cause

- **File**: `scripts/little_loops/hooks/session_start.py` (and any other SessionStart handler)
- **Anchor**: no reader exists — grep for `auto_detect_on_session_start` returns 0 hits outside `config-schema.json` and the two docs files.
- **Cause**: The flag was added to the schema and documented in advance of (or in parallel with) the SessionStart inject feature work tracked under FEAT-1315/1316/1317, but the corresponding handler code to consult the flag was never wired up. The continuation-detection feature itself is also not implemented today, so the gap went unnoticed until `/ll:verify-issues` cross-checked schema/docs against code.

## Expected Behavior

Either:

1. **Implement the flag**: have the SessionStart hook intent (`scripts/little_loops/hooks/session_start.py`) check the flag before printing the continuation-prompt detection notice — or
2. **Remove the documentation**: delete the flag from `config-schema.json`, both docs files, and the example configs, since it does nothing today.

Option 2 is likely the right move if the SessionStart inject feature stays deferred (FEAT-1315 was deferred by the same verify pass that found this).

## Motivation

Users who read the docs and try to disable continuation auto-detection by setting `continuation.auto_detect_on_session_start: false` get no behavior change, eroding trust in the documented configuration surface. Cleaning this up — by either implementing the flag or removing it — keeps `config-schema.json` and the docs honest about what little-loops actually does, which matters more than the flag itself given the underlying feature is deferred.

## Integration Map

### Files to Modify (Option 2 — remove)
- `config-schema.json` — drop the `continuation.auto_detect_on_session_start` property.
- `docs/reference/CONFIGURATION.md` — remove references at lines 116 and 396.
- `docs/guides/SESSION_HANDOFF.md` — remove references at lines 292, 314, 331.
- `templates/*/ll-config.json` (if any reference the flag in example configs).

### Files to Modify (Option 1 — implement)
- `scripts/little_loops/hooks/session_start.py` — read the flag and gate the continuation-detection notice on it.
- `config-schema.json` — keep as-is (already declared).

### Dependent Files (Callers/Importers)
- N/A — no current readers of this flag (that's the bug).

### Similar Patterns
- Other `continuation.*` settings under `config-schema.json:552` — check whether they are wired up before assuming this is an isolated oversight.

### Tests
- Option 1: add a test in `scripts/tests/hooks/` asserting the SessionStart handler suppresses the continuation-detection notice when the flag is `false`.
- Option 2: no tests needed (text-only change); `ll-verify-docs` should pass afterward.

### Documentation
- `docs/reference/CONFIGURATION.md`, `docs/guides/SESSION_HANDOFF.md` (see above).

### Configuration
- `.ll/ll-config.json` example snippets in templates (if present).

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

**Open** | Created: 2026-05-14 | Priority: P3

## Verification Notes

_Added by `/ll:verify-issues` on 2026-05-30_

**Verdict: VALID** — All claims confirmed:
- `auto_detect_on_session_start` declared in `config-schema.json:552` ✓
- Documented in `docs/guides/SESSION_HANDOFF.md` and `docs/reference/CONFIGURATION.md` ✓
- Zero code references to `auto_detect_on_session_start` in `scripts/` — flag is never read ✓
- Issue still needs a decision (implement or remove) — no progress since 2026-05-14 discovery ✓

## Session Log
- `/ll:verify-issues` - 2026-05-31T02:30:03 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5267cfef-4fe8-420d-9d08-62e8f926a297.jsonl`
- `/ll:format-issue` - 2026-05-23T16:51:53 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a9c6d1a1-0ff3-429d-82ba-98b024c1337c.jsonl`
- `/ll:audit-issue-conflicts` - 2026-05-14T21:23:11 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/75505ad4-6733-4424-b334-3143f412786b.jsonl`
- `/ll:verify-issues` - 2026-05-14T20:42:06 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/08e4ebf6-4da6-445a-91f6-ae578f565978.jsonl`
