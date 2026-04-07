---
id: BUG-982
discovered_date: 2026-04-07
discovered_by: capture-issue
confidence_score: 88
outcome_confidence: 64
---

# BUG-982: Handoff Reminder Silenced by Stale Continue-Prompt File

## Summary

`/ll:handoff` does not trigger consistently in target projects: it fires correctly the first time, then never again. Three stacked root causes were identified — one is a genuine bug in `context-monitor.sh`, the other two are configuration/UX gaps.

## Current Behavior

1. **BUG**: After running `/ll:handoff` in session A, `.ll/ll-continue-prompt.md` is written. In session B, `context-monitor.sh:read_state()` sees the file exists and immediately sets `handoff_complete=true`. The hook exits at the threshold check without ever sending a reminder. Handoff reminders are silenced permanently until the file is manually deleted.
2. **Config gap**: All 9 project templates ship with `"context_monitor": { "enabled": false }`. Unless the user explicitly enables it during `/ll:init --interactive` or `/ll:configure context`, the hook exits at line 21–23 before doing anything.
3. **UX gap**: `/ll:init` does not install hooks — users must separately run `/ll:configure hooks install`, a step that is easy to miss.

## Expected Behavior

1. A new session should always start with `handoff_complete=false`, regardless of whether `.ll/ll-continue-prompt.md` exists from a prior session. The mid-session mtime check (lines 335–350) is correct and handles marking complete within a session.
2. Newly initialized projects should have `context_monitor.enabled: true` so monitoring is active by default.
3. `/ll:init` should offer to install hooks (optional step), similar to how it already prompts for allowed-tools.

## Motivation

The context monitor exists specifically to prevent context loss at compaction boundaries. If it silently stops working after the first successful handoff, users lose the protection the feature was designed to provide — without any indication that something is wrong.

## Root Cause

### Root Cause 1 (BUG — Primary)

- **File**: `hooks/scripts/context-monitor.sh`
- **Anchor**: `in function read_state()`, lines 142–168
- **Cause**: `read_state()` initializes `handoff_complete=true` whenever `.ll/ll-continue-prompt.md` exists, but that file is written by `session-cleanup.sh` and is never deleted between sessions. This bypasses the correct post-threshold mtime check entirely.

```bash
# CURRENT (buggy):
local handoff_complete="false"
if [ -f ".ll/ll-continue-prompt.md" ]; then
    handoff_complete="true"   # ← silences ALL future sessions
fi
```

### Root Cause 2 (Config)

- **Files**: `templates/*.json` (all 9 files), `skills/init/SKILL.md:300`
- **Cause**: No project template contains a `context_monitor` section at all — they rely on the schema default of `false` (`config-schema.json:454`). Init wizard instruction says to omit the section when user selects "No", confirming `false` is the intended default.

### Root Cause 3 (UX)

- **Files**: `skills/init/SKILL.md`, `skills/configure/areas.md`
- **Cause**: `/ll:init` sets up config, issue dirs, `.gitignore`, and allowed tools — but does not install hooks. Hook installation is a separate manual step.

## Proposed Solution

### Fix 1: Remove file-existence check in `read_state()`

```bash
# AFTER:
local handoff_complete="false"
# Note: do NOT pre-set based on file existence — the file persists across
# sessions and must not suppress reminders in new sessions. The post-threshold
# mtime check in main() handles marking complete mid-session.
```

### Fix 2: Change default to `true` in all templates and `config-schema.json`

Add `"context_monitor": { "enabled": true }` to all 9 project templates (the section is currently absent in every template — they inherit the schema default). Update `config-schema.json:454` `"default": false` → `true`.

### Fix 3: Add Step 10.5 to `/ll:init`

After Step 10 (Update Allowed Tools), add an optional **Install Hooks** step using the same pattern — ask which settings file, merge plugin hooks from `hooks/hooks.json`, resolve `${CLAUDE_PLUGIN_ROOT}`. Update the dry-run preview in Step 8 to include the hook entry.

## Integration Map

### Files to Modify

- `hooks/scripts/context-monitor.sh` — lines 151–153 (`read_state` function), remove file-existence if-block (line 150 `local handoff_complete="false"` stays; lines 154–155 are unrelated)
- `config-schema.json:454` — add `context_monitor.enabled: true` (section currently absent) default value (property at line 451, default `false` at line 454)
- `templates/generic.json` — add `context_monitor.enabled: true` (section currently absent)
- `templates/python-generic.json` — add `context_monitor.enabled: true` (section currently absent)
- `templates/typescript.json` — add `context_monitor.enabled: true` (section currently absent)
- `templates/javascript.json` — add `context_monitor.enabled: true` (section currently absent)
- `templates/go.json` — add `context_monitor.enabled: true` (section currently absent)
- `templates/rust.json` — add `context_monitor.enabled: true` (section currently absent)
- `templates/dotnet.json` — add `context_monitor.enabled: true` (section currently absent)
- `templates/java-maven.json` — add `context_monitor.enabled: true` (section currently absent)
- `templates/java-gradle.json` — add `context_monitor.enabled: true` (section currently absent)
- `skills/init/SKILL.md` — add Step 10.5 after line ~445

### Dependent Files (Callers/Importers)

- `scripts/tests/test_hooks_integration.py:531` — `test_fresh_state_with_handoff_file_sets_handoff_complete_true` (docstring at line 534): asserts the now-incorrect behavior (`handoff_complete=True`) when a leftover file exists; must be updated to assert `False`
- `commands/handoff.md:122` — writes `.ll/ll-continue-prompt.md` (the actual source of the persistent file); no change needed
- `hooks/scripts/session-cleanup.sh` — deletes `.ll/.ll-lock` and `.ll/ll-context-state.json` on cleanup; does NOT write the continue-prompt file; no change needed

### Similar Patterns

- `skills/init/SKILL.md` Step 10 (Update Allowed Tools) — Step 10.5 should mirror this pattern exactly
- `skills/configure/areas.md:877` — `install` sub-command (`/ll:configure hooks install`), lines 877–941; reuse this pattern for Step 10.5

### Tests

- `scripts/tests/test_hooks_integration.py` — update/remove test at line 531 that asserts buggy behavior
- Add new test: fresh session with existing `.ll/ll-continue-prompt.md` → `handoff_complete` starts as `false`
- Add new test: mid-session handoff sets `handoff_complete=true` via mtime check, hook does not re-remind in same session

## Implementation Steps

1. Fix `read_state()` in `context-monitor.sh` — remove lines 151–153 (the `if [ -f ".ll/ll-continue-prompt.md" ]` block); line 150 stays
2. Update test at `test_hooks_integration.py:531` (`test_fresh_state_with_handoff_file_sets_handoff_complete_true`) to assert `handoff_complete=false` (not `true`) on fresh state
3. Change `context_monitor.enabled` default to `true` in `config-schema.json`
4. Add `"context_monitor": { "enabled": true }` to all 9 project templates (`templates/*.json`) — section is currently absent in all templates
5. Add Step 10.5 to `skills/init/SKILL.md`
6. Manual verification: create test project → run init → run session to threshold → run `/ll:handoff` → start new session → confirm monitor fires normally

## Impact

- **Priority**: P2 — Core session-protection workflow broken for all users who have ever run `/ll:handoff`
- **Effort**: Small — bug fix is a 3-line deletion; template changes are mechanical; init step follows existing pattern
- **Risk**: Low — removal of the existence check restores the behavior the mtime check already handles correctly
- **Breaking Change**: No

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| [docs/ARCHITECTURE.md](../../docs/ARCHITECTURE.md) | Context monitor architecture and hook lifecycle |
| [CONTRIBUTING.md](../../CONTRIBUTING.md) | Development setup and testing guidelines |

## Labels

`bug`, `hooks`, `context-monitor`, `handoff`, `captured`

## Status

**Resolved** | Created: 2026-04-07 | Resolved: 2026-04-07 | Priority: P2

## Resolution

All three root causes addressed:

1. **BUG fixed** (`hooks/scripts/context-monitor.sh`): Removed the `if [ -f ".ll/ll-continue-prompt.md" ]` block from `read_state()` (lines 151–153). New sessions always initialize `handoff_complete=false`; the existing post-threshold mtime check in `main()` handles mid-session completion correctly.

2. **Config default updated** (`config-schema.json`, all 9 project templates): Changed `context_monitor.enabled` default from `false` to `true` in the schema. Added `"context_monitor": { "enabled": true }` to all 9 project templates (`generic`, `python-generic`, `typescript`, `javascript`, `go`, `rust`, `dotnet`, `java-maven`, `java-gradle`).

3. **UX gap closed** (`skills/init/SKILL.md`): Added Step 10.5 "Install Hooks" between Step 10 (Update Allowed Tools) and Step 11 (Update CLAUDE.md), following the same pattern as `/ll:configure hooks install`.

**Test updated**: `test_fresh_state_with_handoff_file_sets_handoff_complete_true` renamed and inverted to `test_fresh_state_with_handoff_file_sets_handoff_complete_false` to assert the now-correct behavior.

---

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-04-07_

**Readiness Score**: 88/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 64/100 → MODERATE

### Concerns
- Root Cause 2 description is slightly inaccurate: the 9 project templates do NOT currently contain a `context_monitor` section at all — they inherit the schema default of `false`. Fix 2 should **add** `"context_monitor": { "enabled": true }` to each template (not change an existing `false` to `true`). Only `config-schema.json` needs its `default` changed from `false` to `true`.

## Session Log
- `/ll:manage-issue` - 2026-04-07T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/abe81a48-a273-4e2f-a3a9-b810a4e39861.jsonl`
- `/ll:ready-issue` - 2026-04-07T19:35:27 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/bf8f51e0-e38e-4de5-9384-4face842c9bd.jsonl`
- `/ll:ready-issue` - 2026-04-07T19:35:22 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/bf8f51e0-e38e-4de5-9384-4face842c9bd.jsonl`
- `/ll:refine-issue` - 2026-04-07T19:30:08 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5c9a2724-b9e4-42d4-b1b4-4bc2c2c47b3f.jsonl`
- `/ll:verify-issues` - 2026-04-07T19:17:56 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/653d74f3-fee7-47f3-a22d-96f6bc8e8e29.jsonl`
- `/ll:capture-issue` - 2026-04-07T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/7c6be417-02b7-4fc4-ae0c-cb10fe731c0a.jsonl`
- `/ll:confidence-check` - 2026-04-07T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1b0e46d1-c897-4b85-b262-b49829bd8c4f.jsonl`
