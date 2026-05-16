---
id: FEAT-1169
type: FEAT
priority: P3
status: done
discovered_date: 2026-04-18
discovered_by: issue-size-review
parent: FEAT-1162
size: Small
confidence_score: 95
outcome_confidence: 93
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
completed_at: 2026-04-18T00:00:00Z
---

# FEAT-1169: Add `update_frontmatter` Write Utility to `frontmatter.py`

## Summary

Add a `update_frontmatter(content: str, updates: dict[str, str | int]) -> str` function to `scripts/little_loops/frontmatter.py` and a matching test class in `test_frontmatter.py`. This shared utility is the foundation for the `completed_at` injection work in FEAT-1170 and FEAT-1171.

## Parent Issue

Decomposed from FEAT-1162: Add `completed_at` Timestamp in All Completion Paths

## Motivation

`frontmatter.py` is currently read-only (`parse_frontmatter`, `strip_frontmatter` — no write function). The `_update_issue_frontmatter` function in `sync.py:160-182` is private and not importable. A shared write utility in `frontmatter.py` avoids duplication and is needed by both sequential and parallel completion paths.

## Implementation Steps

1. **Add `update_frontmatter` to `scripts/little_loops/frontmatter.py`**:
   - Model implementation after `sync.py:160-182` (`_update_issue_frontmatter`)
   - Signature: `update_frontmatter(content: str, updates: dict[str, str | int]) -> str`
   - If frontmatter block exists: merge `updates` into existing YAML, preserving other fields
   - If no frontmatter block exists: prepend a new `---\n...\n---\n` block
   - If a key in `updates` already exists: overwrite its value
   - **Add `import yaml` to `frontmatter.py`** — the module currently does not import `yaml` (only uses regex); the reference implementation relies on `yaml.safe_load` and `yaml.dump(default_flow_style=False, sort_keys=False)` to preserve key order and quote colon-containing values correctly.

2. **Add test class to `scripts/tests/test_frontmatter.py`**:
   - Model after `TestFrontmatterUpdating` in `scripts/tests/test_sync.py:129-235` (class name is `TestFrontmatterUpdating`, not `TestUpdateIssueFrontmatter`)
   - Extend the existing import at `test_frontmatter.py:7` to include `update_frontmatter`
   - 7 cases, matching existing `test_sync.py` method names:
     - `test_update_existing_frontmatter` — merges into existing block (`test_sync.py:132`)
     - `test_update_creates_frontmatter` — creates block when absent (`test_sync.py:149`)
     - `test_update_overwrites_existing_field` — overwrites existing key (`test_sync.py:159`)
     - `test_update_preserves_body` — preserves body content (`test_sync.py:174`)
     - `test_update_preserves_url_value` — preserves URLs (including round-trip) (`test_sync.py:190`)
     - `test_update_preserves_integer_field` — integer round-trip (`test_sync.py:208`)
     - `test_update_quoted_value_with_colon` — quoted colon values (`test_sync.py:223`)

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

3. Update `docs/reference/API.md:4698-4733` — add `update_frontmatter` to the function table and subsection; update module description from "parsing" to "read/write" (or equivalent); update line 41 top-level index description similarly

## Integration Map

### Files to Modify
- `scripts/little_loops/frontmatter.py` — add `update_frontmatter` function; add `import yaml`
- `scripts/tests/test_frontmatter.py` — add `TestUpdateFrontmatter` class with 7 cases; extend import at line 7

### Reference Source (copy logic from)
- `scripts/little_loops/sync.py:160-182` — `_update_issue_frontmatter` (private, yaml-based implementation)
- `scripts/tests/test_sync.py:129-235` — `TestFrontmatterUpdating` (7 existing tests to mirror)

### Existing Callers of Reference Function (not changed in this issue)
- `scripts/little_loops/sync.py:497` — only internal caller of `_update_issue_frontmatter`; migration to the new public `update_frontmatter` is deferred (FEAT-1170/1171 will consume the new utility first; later cleanup can redirect this call-site).

### Existing Imports of `frontmatter` Module (no changes needed)
- `scripts/little_loops/sync.py:19`
- `scripts/little_loops/issue_parser.py:15`
- `scripts/little_loops/skill_expander.py:19`
- `scripts/little_loops/issue_history/parsing.py:17`
- `scripts/little_loops/cli/issues/show.py:111`

### Tests
- `scripts/tests/test_frontmatter.py` — existing classes: `TestParseFrontmatter`, `TestStripFrontmatter` (177 lines total); new class appends here.

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md:4698-4733` — `little_loops.frontmatter` module section; description says "parsing" only and the function table lists only `parse_frontmatter`; add `update_frontmatter` entry, signature, and update description to reflect write capability [Agent 2 finding]
- `docs/reference/API.md:41` — top-level module index row describes module as `YAML frontmatter parsing`; update to reflect read/write capability [Agent 2 finding]

### Verification
- `python -m pytest scripts/tests/test_frontmatter.py -v`
- `python -m mypy scripts/little_loops/frontmatter.py`

## Reference Pattern

```python
# sync.py:160-182 — model after this
def _update_issue_frontmatter(content: str, updates: dict[str, str | int]) -> str:
    ...
```

## Acceptance Criteria

- [x] `update_frontmatter` is importable from `scripts/little_loops/frontmatter.py`
- [x] Function correctly merges into existing frontmatter block
- [x] Function creates frontmatter block when none exists
- [x] Function overwrites existing keys
- [x] All 7 test cases pass

## Resolution

Added `update_frontmatter(content, updates)` to `scripts/little_loops/frontmatter.py` (module docstring and module-index entry in `docs/reference/API.md` updated from "parsing" to "read/write utilities"). The implementation mirrors `sync.py:_update_issue_frontmatter` — uses `yaml.safe_load` / `yaml.dump(default_flow_style=False, sort_keys=False)` to preserve key order and round-trip colon-containing values (URLs, ISO timestamps, quoted colons) without corruption. Added `TestUpdateFrontmatter` class to `scripts/tests/test_frontmatter.py` with the 7 cases mirroring `test_sync.py::TestFrontmatterUpdating`. All 35 frontmatter tests pass; full suite (4966 tests) passes; ruff and mypy clean. `sync.py:_update_issue_frontmatter` left in place — its migration is deferred per FEAT-1170/1171 plan.

## Session Log
- `hook:posttooluse-git-mv` - 2026-04-18T20:26:08 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/21ab1448-5e0d-47e0-872e-be05c2d909ec.jsonl`
- `/ll:refine-issue` - 2026-04-18T20:15:21 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6a75f89c-6cf6-4de2-95ec-3b3c44d624ac.jsonl`
- `/ll:issue-size-review` - 2026-04-18T21:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f4fec2da-840f-48eb-a5e3-fc86007899b8.jsonl`
- `/ll:wire-issue` - 2026-04-18T20:19:04 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/`
- `/ll:confidence-check` - 2026-04-18T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9ff04500-da95-4337-960b-a7afab63af2c.jsonl`
- `/ll:manage-issue` - 2026-04-18T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/21ab1448-5e0d-47e0-872e-be05c2d909ec.jsonl`
