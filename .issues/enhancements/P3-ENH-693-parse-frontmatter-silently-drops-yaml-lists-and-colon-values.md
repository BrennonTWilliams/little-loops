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

1. In `parse_frontmatter` (`frontmatter.py:36-51`), add detection for list-item lines (`line.startswith("- ")`) and call `warnings.warn(f"Unsupported YAML list syntax in frontmatter: {line!r}", stacklevel=2)` — do not parse the line further
2. Add detection for multi-line block scalars (`value.startswith("|")` or `value.startswith(">")`) and emit the same warning
3. Split on first `:` is already correct via `split(":", 1)` (line 42) — verify edge cases in existing tests pass unchanged
4. Add a docstring to `parse_frontmatter` stating: "Parses a subset of YAML: simple `key: value` pairs only. Lists, block scalars, and nested structures are not supported and will emit a warning."
5. Run `python -m pytest scripts/tests/test_frontmatter.py -v` to verify all tests pass

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

## Verification Notes

**Verdict**: NEEDS_UPDATE — 2026-03-12

- Parser correctly splits on first `:` via `split(":", 1)` (line 42) — "misparses values containing colons" claim is partially incorrect for simple cases
- YAML list items genuinely dropped (no `:` means `if ":" in line` fails) — this is the primary issue
- Multi-line block scalar limitation is accurate

## Session Log
- `/ll:scan-codebase` - 2026-03-13T00:36:53Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/44d09b8e-cdcf-4363-844c-3b6dbcf2cf7b.jsonl`
- `/ll:format-issue` - 2026-03-13T01:15:27Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f103ccc2-c870-4de7-a6e4-0320db6d9313.jsonl`
- `/ll:verify-issues` - 2026-03-12T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9511adcf-591f-4199-b7c1-7ff5d368c8f0.jsonl`
- `/ll:confidence-check` - 2026-03-14T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/337af39a-dc8b-48d6-9e2a-cd244f708584.jsonl`

---

**Open** | Created: 2026-03-13 | Priority: P3
