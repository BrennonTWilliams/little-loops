---
discovered_commit: 3e9beeaf2bbe8608104beb89fbc7e2e2259310d8
discovered_branch: main
discovered_date: 2026-03-13T00:36:53Z
discovered_by: scan-codebase
---

# ENH-693: `parse_frontmatter` silently drops YAML lists and colon-containing values

## Summary

The custom frontmatter parser in `frontmatter.py` processes line-by-line and splits on the first `:`.

## Motivation

Silent data loss is worse than a clear error. Future frontmatter additions using YAML lists or colon-containing values (e.g., URLs, timestamps) will be silently dropped without any warning, causing hard-to-debug downstream failures. Making the parser either correct or explicitly limited prevents this class of silent bug. It silently drops YAML list items (lines starting with `- `), misparses values containing colons, and ignores multi-line block scalars. There is no validation or warning for unsupported syntax.

## Location

- **File**: `scripts/little_loops/frontmatter.py`
- **Line(s)**: 36-51 (at scan commit: 3e9beea)
- **Anchor**: `in function parse_frontmatter()`

## Current Behavior

- YAML list items (`- item`) are silently skipped because they have no `:`
- Values containing colons (`title: "foo: bar"`) are incorrectly split
- Multi-line block scalars (`|`, `>`) only capture the header line
- No warning or error is raised for unsupported syntax

## Expected Behavior

Either:
1. Document the parser as "simple key: value only" and raise/warn when list-item lines are encountered, OR
2. Use PyYAML for correct YAML parsing

## Implementation Steps

**Option A — Add PyYAML:**
1. Add `pyyaml` to `scripts/pyproject.toml` dependencies
2. Replace line-by-line parsing in `parse_frontmatter` with `yaml.safe_load(frontmatter_block)`
3. Run tests to verify all existing frontmatter parses identically

**Option B — Validate and warn:**
1. In `parse_frontmatter`, detect list-item lines (`line.startswith("- ")`) and log a warning
2. Detect values containing colons and split only on the first `:` (already done — verify edge cases)
3. Document the supported subset in a docstring

## Integration Map

- **Modified**: `scripts/little_loops/frontmatter.py` — `parse_frontmatter()` (lines 36-51)
- **Consumers**: All modules importing `parse_frontmatter` (config, issue_parser, issue_history, etc.)

## Scope Boundaries

- Focus on making the parser either correct or explicit about its limitations
- Do not change the public interface of `parse_frontmatter`

## Impact

- **Priority**: P3 - Currently all frontmatter in the project uses simple key:value pairs, but the silent failure is a trap for future usage
- **Effort**: Medium - Either add PyYAML dependency or add validation logic
- **Risk**: Medium - If switching to PyYAML, need to verify all existing frontmatter parses identically
- **Breaking Change**: No (adding validation) or Potentially (if PyYAML parses edge cases differently)

## Labels

`enhancement`, `frontmatter`, `parser`

## Session Log
- `/ll:scan-codebase` - 2026-03-13T00:36:53Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/44d09b8e-cdcf-4363-844c-3b6dbcf2cf7b.jsonl`
- `/ll:format-issue` - 2026-03-13T01:15:27Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f103ccc2-c870-4de7-a6e4-0320db6d9313.jsonl`

---

**Open** | Created: 2026-03-13 | Priority: P3
