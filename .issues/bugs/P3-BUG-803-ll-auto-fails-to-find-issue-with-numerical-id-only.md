---
id: BUG-803
title: "ll-auto fails to find issue with numerical ID only"
priority: P3
status: open
type: BUG
discovered_date: 2026-03-18
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 79
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

**File**: `scripts/little_loops/cli_args.py:179-219`
**Functions**: `parse_issue_ids`, `parse_issue_ids_ordered`

`parse_issue_ids("732")` returns `{"732"}` (uppercased tokens, no normalization). `issue_id` values are always assembled as `"TYPE-NNN"` (e.g., `"ENH-732"`) by `issue_parser.py:_parse_type_and_id`. All filter sites do exact membership tests (`i.issue_id in self.only_ids`), so `"ENH-732" in {"732"}` always evaluates `False`.

Numerical-only inputs are never normalized to include the type prefix, and no filter site does partial/suffix matching.

### All Filter Sites (all require the fix)

| File | Line(s) | Comparison | Path |
|---|---|---|---|
| `issue_manager.py` | 774 | `i.issue_id in self.only_ids` | `_get_next_issue` candidate filter |
| `issue_manager.py` | 789-790 | `remaining & set(self.only_ids)` | blocked-issues path |
| `issue_parser.py` | 667 | `info.issue_id not in only_ids` | `find_issues` filter |
| `issue_parser.py` | 678-679 | `order.get(x.issue_id, ...)` | `find_issues` order sort — numeric tokens won't be found in the dict |
| `sprint/run.py` | 129 | `i in only_ids` | sprint run filter (operates on raw ID strings) |

## Expected Behavior

`--only 732` should match any issue whose numeric portion is `732` (e.g., `ENH-732`, `BUG-732`). If multiple issues share the same number (shouldn't happen with globally unique IDs), process all matches or warn.

## Implementation Steps

**Preferred approach: Option B — add a helper and update all filter sites.**

`parse_issue_ids` stays stateless. A new helper `_id_matches(candidate: str, pattern: str) -> bool` replaces direct `in` checks everywhere:

```python
# cli_args.py — add after parse_issue_ids_ordered
import re as _re
_NUMERIC_RE = _re.compile(r"^\d+$")

def _id_matches(candidate: str, pattern: str) -> bool:
    """Return True if candidate (e.g. 'ENH-732') matches pattern (e.g. '732' or 'ENH-732')."""
    if _NUMERIC_RE.match(pattern):
        return candidate.split("-")[-1] == pattern
    return candidate == pattern
```

Then update each filter site:

1. **`scripts/little_loops/cli_args.py`** — Add `_id_matches` helper (new function, ~6 lines).

2. **`scripts/little_loops/issue_manager.py:774`** — Change:
   ```python
   and (self.only_ids is None or i.issue_id in self.only_ids)
   ```
   to:
   ```python
   and (self.only_ids is None or any(_id_matches(i.issue_id, p) for p in self.only_ids))
   ```

3. **`scripts/little_loops/issue_manager.py:789-790`** — Change:
   ```python
   remaining = remaining & set(self.only_ids)
   ```
   to:
   ```python
   remaining = {r for r in remaining if any(_id_matches(r, p) for p in self.only_ids)}
   ```

4. **`scripts/little_loops/issue_parser.py:667`** — Change:
   ```python
   if only_ids is not None and info.issue_id not in only_ids:
       continue
   ```
   to:
   ```python
   if only_ids is not None and not any(_id_matches(info.issue_id, p) for p in only_ids):
       continue
   ```

5. **`scripts/little_loops/issue_parser.py:678-679`** — The `order` dict is keyed by pattern string; numeric patterns won't match full IDs. Change the sort key to use `_id_matches`:
   ```python
   issues.sort(key=lambda x: next(
       (i for i, p in enumerate(only_ids) if _id_matches(x.issue_id, p)),
       len(only_ids)
   ))
   ```

6. **`scripts/little_loops/cli/sprint/run.py:129`** — Change:
   ```python
   [i for i in issues_to_process if i in only_ids]
   ```
   to:
   ```python
   [i for i in issues_to_process if any(_id_matches(i, p) for p in only_ids)]
   ```

7. **Tests** — Add to `scripts/tests/test_cli_args.py` inside `TestParseIssueIds`:
   - `_id_matches("ENH-732", "732")` → `True`
   - `_id_matches("ENH-732", "ENH-732")` → `True`
   - `_id_matches("ENH-732", "BUG-732")` → `False`
   - `_id_matches("ENH-732", "731")` → `False`
   Add to `scripts/tests/test_issue_manager.py`: `AutoManager(only_ids=["732"])` should process `ENH-732`.

### Reference Implementation

`scripts/little_loops/cli/issues/show.py:17-82` — `_resolve_issue_id` already does filesystem-based numeric-only resolution (glob `*-{numeric_id}-*.md` across all issue dirs). That is the reference for Option A if Option B is ever reconsidered.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli_args.py` — add `_id_matches` helper after `parse_issue_ids_ordered` (~6 lines)
- `scripts/little_loops/issue_manager.py` — update filters at lines 774 and 789-790
- `scripts/little_loops/issue_parser.py` — update filters at lines 667 and 678-679
- `scripts/little_loops/cli/sprint/run.py` — update filter at line 129

### Dependent Files (Callers of `parse_issue_ids` / `parse_issue_ids_ordered`)
- `scripts/little_loops/cli/auto.py:72` — `parse_issue_ids_ordered(args.only)` → `AutoManager(only_ids=...)`
- `scripts/little_loops/cli/parallel.py:167` — `parse_issue_ids(args.only)` → `ParallelOrchestrator(only_ids=...)`
- `scripts/little_loops/cli/sprint/run.py:121` — `parse_issue_ids(getattr(args, "only", None))`
- `scripts/little_loops/cli/sprint/edit.py` — calls `parse_issue_ids`
- `scripts/little_loops/cli/sprint/create.py` — calls `parse_issue_ids`

### Tests
- `scripts/tests/test_cli_args.py:30-62` — `TestParseIssueIds` class (add `_id_matches` tests here)
- `scripts/tests/test_issue_manager.py:1815-1839` — `test_run_with_only_ids_filter` (add numeric-only variant)
- `scripts/tests/test_issues_cli.py:768-857` — `TestIssuesCLIShow` numeric ID tests (reference for test structure)
- `scripts/tests/test_cli.py:1391` — integration test with `only_ids` assertion

### Similar Patterns (Reference)
- `scripts/little_loops/cli/issues/show.py:17-82` — `_resolve_issue_id`: existing numeric-only filesystem resolution (reference for Option A)
- `scripts/little_loops/cli/issues/search.py:116-117` — `re.search(r"-(\d+)$", issue_id)`: extracting numeric suffix from a full ID

## Affected Commands

- `ll-auto --only <number>`
- `ll-parallel --only <number>`
- `ll-sprint run --only <number>`

## Session Log
- `/ll:confidence-check` - 2026-03-18T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6efbf13e-9ad7-4b3c-b086-8e2cc5c01743.jsonl`
- `/ll:refine-issue` - 2026-03-18T21:23:35 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c4bef4a0-8ef2-4791-9ece-23a973e8fe9b.jsonl`
- `/ll:capture-issue` - 2026-03-18T16:10:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fffc83c9-009a-4696-8010-040737bf7247.jsonl`

---

## Status

Open
