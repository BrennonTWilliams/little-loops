---
discovered_commit: 3e9beeaf2bbe8608104beb89fbc7e2e2259310d8
discovered_branch: main
discovered_date: 2026-03-13T00:36:53Z
discovered_by: scan-codebase
confidence_score: 88
outcome_confidence: 70
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
- Values containing colons are handled correctly for simple cases (parser splits on first `:` only via `split(":", 1)`)
- Multi-line block scalars (`|`, `>`) only capture the header line
- No warning or error is raised for unsupported syntax

## Expected Behavior

The parser documents its "simple key: value only" limitation and warns when unsupported syntax is encountered (list-item lines, multi-line block scalars). All current project frontmatter is simple `key: value` pairs — no existing consumer uses lists or block scalars — so adding warnings is sufficient without the risk of a PyYAML migration.

**Selected approach: Option B — Validate and warn** (lower risk; no new dependency; all current frontmatter is simple key:value).

PyYAML (Option A) is deferred — only warranted if a future frontmatter field needs list or block-scalar support.

## Implementation Steps

1. Add `import logging` and `logger = logging.getLogger(__name__)` at module level in `frontmatter.py` (no `warnings` import — codebase uses `logging.getLogger`, not `warnings.warn`)
2. In the parse loop (`frontmatter.py:37-50`), add before the `if ":" in line` check:
   ```python
   if line.startswith("- "):
       logger.warning("Unsupported YAML list syntax in frontmatter: %r", line)
       continue
   ```
3. After splitting on `:` and obtaining the value string, add block-scalar detection:
   ```python
   if value.startswith("|") or value.startswith(">"):
       logger.warning("Unsupported YAML block scalar in frontmatter: %r", line)
       result[key] = None
       continue
   ```
4. Update the `parse_frontmatter` docstring (currently lines 14-26) to add: "Parses a subset of YAML: simple `key: value` pairs only. Lists, block scalars, and nested structures are not supported and will emit a `logging.WARNING`."
5. Add test cases to `scripts/tests/test_frontmatter.py` following the `caplog` pattern from `test_dependency_graph.py:82-116`:
   - Test that a list-item line emits `logger.warning` (assert `"Unsupported YAML list syntax" in caplog.text`)
   - Test that a block-scalar line emits `logger.warning` (assert `"Unsupported YAML block scalar" in caplog.text`)
   - Use `caplog.at_level("WARNING", logger="little_loops.frontmatter")` to scope the capture
6. Run `python -m pytest scripts/tests/test_frontmatter.py -v` to verify all tests pass

## Integration Map

### Files to Modify
- `scripts/little_loops/frontmatter.py` — `parse_frontmatter()` (lines 36-51); add `logger = logging.getLogger(__name__)` at module level

### Dependent Files (Callers/Importers)
- `scripts/little_loops/issue_parser.py` — calls `parse_frontmatter(content)` (no coerce); reads `discovered_by`, `effort`, `impact`, `confidence_score`, `outcome_confidence`, `product_area`
- `scripts/little_loops/sync.py` — calls `parse_frontmatter(content, coerce_types=True)` at lines 391, 582, 779, 844, 917; reads `github_issue` int field
- `scripts/little_loops/issue_history/parsing.py` — calls `parse_frontmatter(content)` at lines 49, 367 (line 367 wrapped in `except Exception: pass`)
- `scripts/little_loops/cli/issues/show.py:98` — calls `parse_frontmatter(content, coerce_types=True)` for CLI card display

### Similar Patterns
- `scripts/little_loops/dependency_graph.py:102-104` — `logger.warning(f"Issue {issue.issue_id} blocked by unknown issue {blocker_id}")` followed by `continue` — model for warning-and-skip during parsing
- `scripts/little_loops/sprint.py:372` — `logger.warning("Failed to parse issue file %s: %s", path, e)` — model for parse-loop warning

### Tests
- `scripts/tests/test_frontmatter.py` — existing test coverage (13 tests, no list/block-scalar/warning cases yet)
- `scripts/tests/test_dependency_graph.py:82-116` — `caplog` warning assertion pattern to follow for new warning tests

### Documentation
- `docs/reference/API.md` — documents `little_loops.frontmatter` and `parse_frontmatter` signature; update docstring description there if docstring changes

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

## Verification Notes

**Verdict**: NEEDS_UPDATE — 2026-03-12

- Parser correctly splits on first `:` via `split(":", 1)` (line 42) — "misparses values containing colons" claim is partially incorrect for simple cases
- YAML list items genuinely dropped (no `:` means `if ":" in line` fails) — this is the primary issue
- Multi-line block scalar limitation is accurate

## Session Log
- `/ll:refine-issue` - 2026-03-18T01:38:01 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5ca63274-28df-4554-ae7c-5366e4614ee5.jsonl`
- `/ll:scan-codebase` - 2026-03-13T00:36:53Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/44d09b8e-cdcf-4363-844c-3b6dbcf2cf7b.jsonl`
- `/ll:format-issue` - 2026-03-13T01:15:27Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f103ccc2-c870-4de7-a6e4-0320db6d9313.jsonl`
- `/ll:verify-issues` - 2026-03-12T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9511adcf-591f-4199-b7c1-7ff5d368c8f0.jsonl`
- `/ll:confidence-check` - 2026-03-14T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/337af39a-dc8b-48d6-9e2a-cd244f708584.jsonl`

---

**Open** | Created: 2026-03-13 | Priority: P3
