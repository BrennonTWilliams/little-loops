---
id: BUG-803
title: "ll-auto fails to find issue with numerical ID only"
priority: P3
status: open
type: BUG
discovered_date: 2026-03-18
discovered_by: capture-issue
---

# BUG-803: ll-auto fails to find issue with numerical ID only

## Problem

`ll-auto --only 732` silently finds no issues and exits with 0 processed, while `ll-auto --only ENH-732` correctly identifies and processes the issue.

## Symptoms

```
$ ll-auto --only 732
[16:06:42] Starting automated issue management...
[16:06:42] No more issues to process!
[16:06:42] Issues processed: 0
```

vs.

```
$ ll-auto --only ENH-732
[16:06:48] Processing: ENH-732 - Replace FSM State Box Badges with Unicode Compositions
```

## Root Cause

**File**: `scripts/little_loops/cli_args.py:196`
**Function**: `parse_issue_ids`

`parse_issue_ids("732")` returns `{"732"}`. The filter in `issue_manager.py:774` checks `i.issue_id in self.only_ids`, comparing full IDs like `"ENH-732"` against `{"732"}`, which always fails.

Numerical-only inputs are never normalized to include the type prefix, and the filter does no partial/suffix matching.

## Expected Behavior

`--only 732` should match any issue whose numeric portion is `732` (e.g., `ENH-732`, `BUG-732`). If multiple issues share the same number (shouldn't happen with globally unique IDs), process all matches or warn.

## Implementation Steps

1. In `parse_issue_ids` (and `parse_issue_ids_ordered`), detect when a token is purely numeric (e.g., `^\d+$`).
2. Either:
   - **Option A**: Expand numeric-only tokens by searching the issues directory for any file whose ID ends in that number, resolving to the full ID at parse time. Requires access to the issues directory.
   - **Option B**: Store numeric tokens as-is and update the filter in `IssueManager` (around `issue_manager.py:774`) to also check `i.issue_id.split("-")[-1] == token` for purely numeric tokens.
3. Option B is simpler and keeps `parse_issue_ids` stateless. Prefer Option B.
4. Apply the same fix to `ll-parallel --only` and `ll-sprint run --only` which share the same `parse_issue_ids` utility.
5. Add a test: `parse_issue_ids("732")` should eventually match `"ENH-732"` in the manager filter.

## Affected Commands

- `ll-auto --only <number>`
- `ll-parallel --only <number>`
- `ll-sprint run --only <number>`

## Session Log
- `/ll:capture-issue` - 2026-03-18T16:10:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fffc83c9-009a-4696-8010-040737bf7247.jsonl`

---

## Status

Open
