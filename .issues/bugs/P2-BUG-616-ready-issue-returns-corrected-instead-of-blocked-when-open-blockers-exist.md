---
discovered_date: 2026-03-06
discovered_by: capture-issue
---

# BUG-616: `ready-issue` returns `CORRECTED` instead of `BLOCKED` when open blockers exist

## Summary

When `ready-issue` validates an issue that has an open blocker in its `## Blocked By` section, it returns verdict `CORRECTED` (if it also made line-drift fixes) instead of a dedicated `BLOCKED` verdict. Downstream automation (sprint runner, `ll-auto`) interprets `CORRECTED` as "ready to implement" and proceeds with implementation, ignoring the blocker.

## Steps to Reproduce

1. Have an issue (e.g. ENH-552) with an active blocker (FEAT-555) listed in `## Blocked By`
2. Run `/ll:ready-issue ENH-552` (or trigger it via `ll-sprint run`)
3. Observe: verdict is `CORRECTED` because line numbers were also updated
4. Sprint runner sees `CORRECTED` → proceeds to Phase 2 implementation
5. Implementation runs on the same files as the open blocker → potential merge conflict

## Actual Behavior

`ready-issue` returns `CORRECTED` (or `PASS`) even when the issue has an unresolved blocking dependency. The `READY_FOR` section may contain a caveat like "Implementation: Yes (after FEAT-555 lands)" but the top-level verdict does not reflect the blocked state.

Observed in `ll-sprint-cli-polish.log` at lines 380–416:
- Blocker check row: `WARN | **FEAT-555 is still open**`
- READY_FOR: `Implementation: Yes (after FEAT-555 lands)`
- Verdict: `CORRECTED` ← should be `BLOCKED`

## Expected Behavior

When any issue listed in `## Blocked By` is still active (exists in `.issues/` outside `completed/` or `deferred/`), `ready-issue` should return verdict `BLOCKED` regardless of other corrections made. The `BLOCKED` verdict must be the top-level signal so that all callers (sprint runner, `ll-auto`) can detect it without parsing the prose body.

The existing `CORRECTIONS_MADE` content should still be recorded in the output but the verdict must be `BLOCKED`.

## Root Cause

`ready-issue` skill (`commands/ready-issue.md` or equivalent) does not check whether active blockers exist before choosing its verdict. It only distinguishes between `PASS`, `CORRECTED`, and `CLOSE`. There is no `BLOCKED` verdict in the taxonomy.

**File**: `commands/ready-issue.md` (verdict selection logic)
**Anchor**: verdict taxonomy / `## VERDICT` section

## Proposed Fix

1. Add `BLOCKED` to the verdict taxonomy in `ready-issue`
2. After validating blocker references: if any `## Blocked By` entry resolves to an active issue file, set verdict `BLOCKED` (overrides `CORRECTED`)
3. Document the new verdict in `ready-issue` output format docs

## Impact

- **Priority**: P2 — causes incorrect automation behavior; blocked issues get implemented prematurely
- **Effort**: Low — verdict taxonomy change + one new check in ready-issue logic
- **Risk**: Low — additive change; no existing callers handle `BLOCKED` yet (see BUG-617 for the companion fix)
- **Breaking Change**: No (new verdict; callers that don't handle `BLOCKED` will treat it as unknown, which is a safe no-op if BUG-617 is also fixed)

## Labels

`bug`, `ready-issue`, `sprint`, `automation`

## Status

Open

## Blocked By

- BUG-617 should be fixed in the same release (companion fix — sprint runner must handle `BLOCKED` verdict)

## Session Log
- `/ll:capture-issue` - 2026-03-06T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ec3d1ef8-aeec-4ccb-bd08-ffea1f74e5ef.jsonl`
