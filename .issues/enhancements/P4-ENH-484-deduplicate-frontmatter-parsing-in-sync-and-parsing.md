---
discovered_commit: 95d4139206f3659159b727db57578ffb2930085b
discovered_branch: main
discovered_date: 2026-02-24T20:18:21Z
discovered_by: scan-codebase
---

# ENH-484: Deduplicate frontmatter parsing in sync.py and parsing.py

## Summary

Frontmatter stripping/parsing logic is duplicated in multiple locations: `sync.py` (`_parse_issue_title` and `_get_issue_body` each re-implement frontmatter boundary detection), and `issue_history/parsing.py` (`_parse_discovered_by` and `_parse_discovered_date` each call `parse_frontmatter` independently on the same content).

## Current Behavior

- `sync.py:221-225` and `sync.py:251-256` — identical 4-line frontmatter skip blocks in `_parse_issue_title` and `_get_issue_body`, duplicating logic already in `frontmatter.py:parse_frontmatter`
- `issue_history/parsing.py:74` and `parsing.py:230` — `_parse_discovered_by` and `_parse_discovered_date` each call `parse_frontmatter(content)` independently, resulting in double-parsing when both are called from `parse_completed_issue`

## Expected Behavior

- `sync.py`: A single `_strip_frontmatter` helper (or reuse from `frontmatter.py`) replaces both duplicated blocks
- `parsing.py`: `parse_completed_issue` calls `parse_frontmatter` once and extracts both `discovered_by` and `discovered_date` from the result

## Motivation

Reduces maintenance surface and eliminates risk of the copies drifting out of sync.

## Proposed Solution

1. In `sync.py`: Add `_strip_frontmatter(content: str) -> str` or use `frontmatter.parse_frontmatter` directly
2. In `parsing.py`: In `parse_completed_issue`, call `fm = parse_frontmatter(content)` once, then extract both values from `fm`

## Scope Boundaries

- **In scope**: Deduplicating frontmatter parsing calls; no functional changes
- **Out of scope**: Refactoring frontmatter.py itself, changing public APIs

## Implementation Steps

1. Add `_strip_frontmatter` helper to `sync.py` or reuse `parse_frontmatter` from `frontmatter.py`
2. Deduplicate frontmatter skip blocks in `_parse_issue_title` and `_get_issue_body`
3. Refactor `parse_completed_issue` in `parsing.py` to call `parse_frontmatter` once
4. Verify existing tests pass unchanged

## Integration Map

### Files to Modify
- `scripts/little_loops/sync.py` — deduplicate frontmatter skip in `_parse_issue_title` and `_get_issue_body`
- `scripts/little_loops/issue_history/parsing.py` — parse frontmatter once in `parse_completed_issue`

### Dependent Files (Callers/Importers)
- N/A — internal refactor

### Similar Patterns
- `scripts/little_loops/frontmatter.py` — canonical `parse_frontmatter` implementation

### Tests
- Existing tests should pass unchanged

### Documentation
- N/A

### Configuration
- N/A

## Impact

- **Priority**: P4 — Code duplication cleanup, low urgency
- **Effort**: Small — Straightforward refactor
- **Risk**: Low — Internal restructuring only
- **Breaking Change**: No

## Labels

`enhancement`, `refactoring`, `code-duplication`, `auto-generated`

## Session Log
- `/ll:scan-codebase` - 2026-02-24T20:18:21Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fa9f831f-f3b0-4da5-b93f-5e81ab16ac12.jsonl`
- `/ll:format-issue` - 2026-02-24 - auto-format batch

---

## Status

**Open** | Created: 2026-02-24 | Priority: P4
