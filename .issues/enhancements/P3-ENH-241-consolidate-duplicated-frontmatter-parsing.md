---
discovered_commit: a8f4144ebd05e95833281bd95506da984ba5d118
discovered_branch: main
discovered_date: 2026-02-06T03:41:30Z
discovered_by: scan_codebase
---

# ENH-241: Consolidate duplicated frontmatter parsing logic

## Summary

Near-identical YAML frontmatter parsing implementations exist in `issue_parser.py` (`IssueParser._parse_frontmatter`) and `sync.py` (`_parse_issue_frontmatter`). The sync version adds integer coercion, but the core logic is duplicated. A bug fix to parsing would need to be applied in two places.

## Location

- **File**: `scripts/little_loops/issue_parser.py`
- **Line(s)**: 338-376 (at scan commit: a8f4144)
- **Anchor**: `in method IssueParser._parse_frontmatter`
- **Permalink**: [View on GitHub](https://github.com/BrennonTWilliams/little-loops/blob/a8f4144ebd05e95833281bd95506da984ba5d118/scripts/little_loops/issue_parser.py#L338-L376)

- **File**: `scripts/little_loops/sync.py`
- **Line(s)**: 151-185 (at scan commit: a8f4144)
- **Anchor**: `function _parse_issue_frontmatter`
- **Permalink**: [View on GitHub](https://github.com/BrennonTWilliams/little-loops/blob/a8f4144ebd05e95833281bd95506da984ba5d118/scripts/little_loops/sync.py#L151-L185)

## Current Behavior

Two near-identical implementations. The `sync.py` version has integer coercion (`value.isdigit()`), the `issue_parser.py` version does not.

## Expected Behavior

A single shared `parse_frontmatter()` utility function with optional type coercion that both modules use.

## Proposed Solution

Extract a module-level `parse_frontmatter(content: str, coerce_types: bool = False) -> dict[str, Any]` into `issue_parser.py` and have `sync.py` call it with `coerce_types=True`.

## Impact

- **Severity**: Medium
- **Effort**: Small
- **Risk**: Low

## Labels

`enhancement`, `priority-p3`

---

## Status
**Open** | Created: 2026-02-06T03:41:30Z | Priority: P3
