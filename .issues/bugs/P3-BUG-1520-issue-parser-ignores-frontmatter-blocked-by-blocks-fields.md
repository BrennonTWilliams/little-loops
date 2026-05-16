---
captured_at: 2026-04-22T00:00:00Z
discovered_date: 2026-04-22
discovered_by: user-report
status: done
completed_at: 2026-04-22T00:00:00Z
---

# BUG-1520: issue_parser ignores frontmatter blocked_by/blocks fields

## Summary

`ll-issues clusters` (and all dependency-graph features) silently dropped blocking
relationships when issues stored them in YAML frontmatter (`blocked_by: BUG-375`)
instead of `## Blocked By` / `## Blocks` markdown sections. The parser only read
the section form, so the `DependencyGraph` saw no edges and `clusters` reported
"No issue relationships found" even when blocked issues existed.

## Root Cause

`IssueParser.parse_file` (`scripts/little_loops/issue_parser.py`) calls
`_parse_blocked_by(content)` and `_parse_blocks(content)`, which use
`_parse_section_items` to scan for `## Blocked By` / `## Blocks` markdown headers.

The method also calls `parse_frontmatter(content)` and reads many frontmatter
fields (`effort`, `impact`, `discovered_by`, etc.), but never read `blocked_by`
or `blocks` from it. Issues written by `capture-issue` use frontmatter for
dependencies (e.g., `blocked_by: BUG-375` or `blocked_by: [ENH-753, FEAT-1002]`),
so those relationships were silently ignored.

Both little-loops and loop-viz active issues use the frontmatter form exclusively;
the `## Blocked By` section format only appears in older completed issues.

## Fix

Added a frontmatter merge step in `parse_file` immediately after the section-based
parse (`scripts/little_loops/issue_parser.py`, ~line 428):

```python
# Also read blocked_by/blocks from frontmatter (newer issue format)
for fm_key, target in (("blocked_by", blocked_by), ("blocks", blocks)):
    fm_val = frontmatter.get(fm_key)
    if fm_val:
        ids = [fm_val] if isinstance(fm_val, str) else list(fm_val)
        for id_ in ids:
            if id_ not in target:
                target.append(id_)
```

Handles both string (`blocked_by: BUG-375`) and list (`blocked_by: [A, B]`)
frontmatter values, deduplicating against any IDs already found in sections.

## Verification

- `ll-issues clusters` in loop-viz now shows the BUG-375 → FEAT-377 cluster.
- All 362 existing `issue_parser` and `dependency` tests pass.
