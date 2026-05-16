---
discovered_date: 2026-03-20
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 93
---

# BUG-836: `ll-issues list` warns on YAML block sequence frontmatter

## Summary

`ll-issues list` emits dozens of `Unsupported YAML list syntax in frontmatter` warnings when run in projects whose issue files use YAML block sequence syntax for list fields (e.g., `related_issues:`, `tags:`). The command still produces correct output, but the warnings obscure real issues and pollute automation logs.

## Context

Identified from plan `~/.claude/plans/wobbly-painting-snowglobe.md`.

The `parse_frontmatter` function in `scripts/little_loops/frontmatter.py` only handles simple `key: value` scalar pairs. Any `- item` line triggers a warning and is discarded. In projects like blender-agents, many issue files use the valid block sequence form:

```yaml
related_issues:
  - P1-BUG-8743
  - P2-ENH-8762
```

Every such item line emits a warning. No downstream code in `ll-issues list` consumes `related_issues` or `tags`, so the values themselves are not needed by the current callers — the fix eliminates spurious warnings while also correctly parsing lists for future use.

## Root Cause

- **File**: `scripts/little_loops/frontmatter.py`
- **Function**: `parse_frontmatter` (line 16)
- **Loop**: `frontmatter_text.split("\n")` loop at line 41
- **Warning branch**: `frontmatter.py:45-47` — `if line.startswith("- ")` fires unconditionally; no state variable tracks whether the preceding `key:` line had an empty value
- **Explanation**: The line-by-line parser has no state to track that a preceding `key:` (empty value) began a list. Each `- item` line falls through to the warning branch unconditionally.

A block sequence input like:
```
tags:
- foo
- bar
```
becomes `["tags:", "- foo", "- bar"]` after split. `"tags:"` correctly sets `result["tags"] = None` (line 56); `"- foo"` and `"- bar"` each hit line 45, emit warning, and are discarded — leaving `result` as `{"tags": None}`.

**Note**: The function docstring at `frontmatter.py:20-22` also states "Lists, block scalars, and nested structures are not supported" — this will need updating to reflect the new behavior.

## Integration Map

### Files to Modify
- `scripts/little_loops/frontmatter.py` — `parse_frontmatter()` lines 41-61 (loop); docstring lines 20-22

### Test Files
- `scripts/tests/test_frontmatter.py` — primary test file; `TestParseFrontmatter` class (lines 10-113); add 4 new tests
  - Existing `test_list_item_emits_warning` at line 89 uses `"---\nkey: value\n- item\n---\n\n"` (orphaned item after scalar key) — **still valid after fix**
  - Existing `test_block_scalar_pipe_emits_warning` (line 97) and `test_block_scalar_folded_emits_warning` (line 106) are unrelated to this fix

### Callers of `parse_frontmatter` (no API changes needed — returns same type)
- `scripts/little_loops/issue_parser.py:336`
- `scripts/little_loops/sync.py` — lines 391, 582, 779, 844, 917
- `scripts/little_loops/issue_history/parsing.py` — lines 49, 367
- `scripts/little_loops/cli/issues/show.py:98`

The fix is backward-compatible: callers receive `None` today for list-valued keys; after the fix they will receive a `list[str]`. None of the current callers consume `related_issues` or `tags`, so no caller updates are required.

## Implementation Steps

1. Modify `scripts/little_loops/frontmatter.py:41-61` — replace the stateless loop with a stateful approach that tracks `current_list_key`:
   - When a `key:` line has an empty value, initialize `result[key] = []` and set `current_list_key = key`.
   - When a `- item` line follows and `current_list_key` is set, append to `result[current_list_key]`.
   - When any non-list, non-empty, non-comment line is encountered, reset `current_list_key = None`.
   - After the loop, if `result[current_list_key] == []` (key declared but no items), set to `None` (preserves existing `test_null_values` behavior).
   - Orphaned `- item` lines with no preceding empty key still emit the warning.

2. Update docstring at `frontmatter.py:20-22` — remove "Lists … are not supported" claim.

3. Update `scripts/tests/test_frontmatter.py` (append after line 113 in `TestParseFrontmatter`):
   - Existing `test_list_item_emits_warning` stays valid — orphaned items still warn.
   - Add `test_block_sequence_parsed_as_list` — two-item list round-trips correctly.
   - Add `test_empty_value_no_items_is_none` — `key:\nnext: value` → `key` is `None`.
   - Add `test_block_sequence_followed_by_scalar` — list followed by scalar parses both correctly.
   - Add `test_orphaned_list_item_still_warns` — warning fires for `- item` after a scalar key.

**Behavioral guarantees after fix:**
- `key: null` / `key: ~` → `None` (unchanged)
- `key:` with no items → `None` (unchanged)
- `key:\n  - item1\n  - item2` → `["item1", "item2"]` (NEW)
- Orphaned `- item` after a scalar value → warning (unchanged)

## Acceptance Criteria

- [ ] `python -m pytest scripts/tests/test_frontmatter.py -v` passes with all new tests green
- [ ] `python -m pytest scripts/tests/ -q` passes with no regressions
- [ ] `ll-issues list 2>&1 | grep "Unsupported YAML"` returns nothing in blender-agents project (or equivalent multi-list issue file)
- [ ] No change to behavior for issue files that don't use block sequences

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| architecture | docs/reference/API.md | Documents `parse_frontmatter` public API |
| guidelines | .claude/CLAUDE.md | Test command: `python -m pytest scripts/tests/` |

## Labels

`bug`, `captured`

---

## Resolution

Fixed by introducing `current_list_key` state variable in `parse_frontmatter`. When a `key:` line has an empty value, the function now initializes `result[key] = []` and tracks `current_list_key`. Subsequent `- item` lines append to that list. Any non-list line finalizes the list (converting empty lists to `None`) and resets tracking. Orphaned `- item` lines (after scalar-valued keys) still emit warnings unchanged.

**Files changed:**
- `scripts/little_loops/frontmatter.py` — stateful loop with `current_list_key`; docstring updated
- `scripts/tests/test_frontmatter.py` — 4 new tests added (27 total, all green)

## Status

**Completed** | Created: 2026-03-20 | Resolved: 2026-03-20 | Priority: P3

## Session Log
- `/ll:ready-issue` - 2026-03-20T17:54:14 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/83af9c4c-754d-49e8-af51-d8124f16f863.jsonl`
- `/ll:confidence-check` - 2026-03-20T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b277321d-2fab-414d-9422-c0873b999ccc.jsonl`
- `/ll:refine-issue` - 2026-03-20T17:46:53 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5d7af86b-c6f6-4ca8-94f0-8b4d69221737.jsonl`
- `/ll:capture-issue` - 2026-03-20T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3395f6a8-0340-4e10-98a3-d300e80733c1.jsonl`
