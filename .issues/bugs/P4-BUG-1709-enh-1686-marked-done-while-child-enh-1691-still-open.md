---
id: BUG-1709
type: BUG
priority: P4
status: open
discovered_date: 2026-05-26
captured_at: '2026-05-26T00:48:43Z'
discovered_by: capture-issue
labels:
- bug
- captured
- process
testable: false
confidence_score: 97
outcome_confidence: 68
score_complexity: 14
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 18
---

# BUG-1709: ENH-1686 Marked Done While Child ENH-1691 Still Open

## Summary

The parent issue `ENH-1686` ("Live-Write Issue Events to history.db") is in `.issues/completed/` with `status: done`, but its child `ENH-1691` ("wire issue lifecycle EventBus to SQLiteTransport") is still `status: open`. This is a tracking inconsistency — the parent's acceptance criteria cannot be satisfied until the child lands, so the parent shouldn't be marked done.

## Steps to Reproduce

```bash
# Verify parent is done
grep -E "^(id|status):" .issues/completed/P2-ENH-1686-*.md
# id: ENH-1686
# status: done

# Verify child is still open
grep -E "^(id|status|parent):" .issues/enhancements/P2-ENH-1691-*.md
# id: ENH-1691
# status: open
# parent: ENH-1686
```

## Observed Behavior

- `ENH-1686` is in the completed directory with `status: done`.
- `ENH-1691` (its declared child via `parent: ENH-1686`) has `status: open`.
- `ENH-1690` (its other child) is correctly `status: done`.
- Independent verification: querying `.ll/history.db` shows all event tables empty, confirming the lifecycle→transport wiring (the work of ENH-1691) has not landed.

## Expected Behavior

A parent issue's `status: done` should imply all children are also `done` (or explicitly `cancelled`/`deferred` with a recorded reason). One of:

1. **Reopen ENH-1686** to `status: open` until ENH-1691 lands, OR
2. **Land ENH-1691** so reality matches the parent's status, OR
3. **Close ENH-1691 as cancelled** with a reason if the work was descoped.

## Root Cause

Unknown — likely a process/tooling gap: there is no automated check that prevents marking an EPIC/parent issue `done` while any child is still `open`. `ll-issues` and `ll-deps` don't appear to gate parent closure on child status.

## Impact

- **Priority**: P4 — Low severity but visible: misleads anyone reading the history-db epic family. Suggests a missing invariant check that, if added, would prevent a class of process bugs.
- **Effort**: Small — one of: 5 min to reopen ENH-1686, or land ENH-1691, or document the descope.
- **Risk**: Low.
- **Breaking Change**: No.

## Fix Proposal

Pick one of the three resolutions in **Expected Behavior** above based on intent. Recommended: reopen `ENH-1686` to `status: open` and move it back to `.issues/enhancements/`, since the producer-side context layer (and EPIC-1707) depends on this wiring actually existing.

**Optional follow-up** (separate ENH): add a check to `ll-issues` (or a hook) that warns/blocks when a parent is marked `done` while any child is non-terminal.

## Acceptance Criteria

- One of: ENH-1686 reopened, ENH-1691 landed, or ENH-1691 cancelled with reason recorded.
- Parent and child statuses are mutually consistent.

## Labels

`bug`, `captured`, `process`

## Session Log

- `/ll:capture-issue` - 2026-05-26T00:48:43Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a2c695cf-9995-4a8f-9ec7-81cdca0d77e5.jsonl`

---

**Open** | Created: 2026-05-26 | Priority: P4
