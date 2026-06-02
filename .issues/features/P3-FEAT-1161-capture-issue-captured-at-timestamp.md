---
id: FEAT-1161
type: FEAT
priority: P3
status: done
discovered_date: 2026-04-18
discovered_by: capture-issue
parent: FEAT-1155
confidence_score: 100
outcome_confidence: 78
score_complexity: 10
score_test_coverage: 18
score_ambiguity: 25
score_change_surface: 25
completed_at: 2026-04-18T00:00:00Z
---

# FEAT-1161: Add `captured_at` Timestamp in capture-issue Skill

## Summary

Record a `captured_at` ISO 8601 UTC timestamp in issue frontmatter when `/ll:capture-issue` creates a new issue.

## Current Behavior

Issues created by `/ll:capture-issue` include a `discovered_date` (date-only, e.g., `2026-04-18`) in frontmatter but no exact timestamp of when the issue was captured.

## Expected Behavior

Issues created by `/ll:capture-issue` include a `captured_at` ISO 8601 UTC timestamp (e.g., `captured_at: "2026-04-18T14:32:07Z"`) in frontmatter alongside `discovered_date`.

## Use Case

An engineering team using `ll-history` to analyze issue capture velocity wants sub-day timing data — e.g., whether issues are captured immediately after discovery or hours later. With only `discovered_date`, daily granularity is the limit. With `captured_at`, they can compute within-day latency and correlate capture patterns with sprint activity.

## Parent Issue

Decomposed from FEAT-1155: Issue Capture and Completion Timestamps in Frontmatter

## Motivation

Issues have `discovered_date` (date-only) but no machine-readable record of the exact moment capture happened. Adding `captured_at` enables sub-day velocity metrics in `ll-history` and other analysis tools without reconstructing times from git blame.

## Implementation Steps

1. **`skills/capture-issue/SKILL.md`** (~line 235): Add instruction mandating `captured_at: <ISO 8601 datetime>` alongside `discovered_date` and `discovered_by: capture-issue`.

2. **`skills/capture-issue/templates.md`** (lines 134-139): Add `captured_at: [ISO timestamp]` to the heredoc template.

Shell format to use: `date -u +"%Y-%m-%dT%H:%M:%SZ"` — consistent with the format already used in `issue_lifecycle.py:730`.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

3. Update `docs/reference/ISSUE_TEMPLATE.md:871-898` — add `captured_at` row to the Frontmatter Fields table and update the example block at lines 892-898
4. Update `scripts/tests/test_frontmatter.py` — add test asserting ISO 8601 datetime string with `T` and colons parses without corruption
5. Update `scripts/tests/test_issue_parser.py` — add test asserting `parse_file` ignores `captured_at` gracefully and still reads `discovered_by`
6. Update `scripts/tests/test_issue_history_parsing.py` — add test asserting `parse_completed_issue` ignores `captured_at` gracefully
7. Update `scripts/tests/fixtures/issues/bug-with-frontmatter.md` — add `captured_at` field to the fixture

## API/Interface

New frontmatter field:

```yaml
captured_at: "2026-04-18T14:32:07Z"   # set by capture-issue
```

## Acceptance Criteria

- [ ] New issues created by `/ll:capture-issue` contain `captured_at` in frontmatter
- [ ] `captured_at` is a valid ISO 8601 UTC string (ends in `Z`)
- [ ] Existing issues without `captured_at` continue to work without errors

## Files to Modify

- `skills/capture-issue/SKILL.md` — add `captured_at` field instruction near line 235 alongside `discovered_date`
- `skills/capture-issue/templates.md` — add `captured_at: [ISO timestamp]` to heredoc template at lines 134-139

## Integration Map

### Files to Modify
- `skills/capture-issue/SKILL.md:235` — sole source of frontmatter field mandates; add `captured_at: <ISO 8601 datetime>` to the instruction line
- `skills/capture-issue/templates.md:134-139` — heredoc template; add `captured_at: [ISO timestamp]` after `discovered_date`

### Dependent Files (Callers/Consumers) — No Changes Required
- `scripts/little_loops/cli/issues/search.py:21-29` — `_parse_discovered_date` regex truncates to `[:10]` before parsing; unaffected by new `captured_at` field
- `scripts/little_loops/issue_history/parsing.py:291-306` — `_parse_discovered_date(fm)` reads dict key `"discovered_date"` only; ignores unknown keys gracefully
- `scripts/little_loops/frontmatter.py:16-78` — pure parser; silently passes through any frontmatter key without validation
- `scripts/little_loops/issue_parser.py:354-356` — reads `discovered_by` into `IssueInfo`; `discovered_date` is not even extracted into the dataclass, so `captured_at` won't affect it

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/ISSUE_TEMPLATE.md:871-898` — authoritative "Frontmatter Fields" table listing `discovered_date` and `discovered_by`; needs a new `captured_at` row and the example block at lines 892-898 needs the new field [Agent 2 finding]

### Similar Patterns (ISO Timestamps in Frontmatter)
- `scripts/little_loops/sync.py:490` — writes `last_synced: datetime.now(UTC).isoformat(timespec="seconds")` (produces `+00:00` suffix)
- `hooks/scripts/context-monitor.sh:155` — uses `date -u +%Y-%m-%dT%H:%M:%SZ` (produces `Z` suffix)

### Tests
- `scripts/tests/test_sync.py:129-235` — `TestFrontmatterUpdating` class; `test_update_preserves_url_value:190` already uses `last_synced: "2026-02-24T20:00:00+00:00"` as a datetime fixture — model after this for a `captured_at` round-trip test
- `scripts/tests/test_sync.py:748` — `test_create_local_issue_body_in_summary` asserts `discovered_date:` is present in `_create_local_issue` output (not `_update_issue_frontmatter`); no change needed here

## Tests

- `scripts/tests/test_sync.py:129-235` (`TestFrontmatterUpdating`) — add a test asserting a `captured_at` ISO datetime value survives `_update_issue_frontmatter` round-trip without mangling (model after `test_update_preserves_url_value:190` which already tests a datetime value)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_frontmatter.py` — new test: `captured_at: 2026-04-18T10:30:00Z` is parsed as the string `"2026-04-18T10:30:00Z"` without colon corruption; the existing `test_colon_in_value` only covers URL colons — an ISO datetime `T10:30:00` is a different pattern [Agent 3 finding]
- `scripts/tests/test_issue_parser.py` — new test: `parse_file` on a fixture with `captured_at:` in frontmatter returns an `IssueInfo` without error and still reads `discovered_by` correctly (model after `test_parse_discovered_by_from_frontmatter:500`) [Agent 3 finding]
- `scripts/tests/test_issue_history_parsing.py` — new test: `parse_completed_issue` on a file with `captured_at:` in frontmatter succeeds and still extracts `discovered_by`/`discovered_date` (model after `TestParseCompletedIssue:23-45`) [Agent 3 finding]
- `scripts/tests/fixtures/issues/bug-with-frontmatter.md` — update fixture: add `captured_at: 2026-04-18T10:30:00Z` so it reflects the new template output; no existing assertion checks for `captured_at` absence, so no tests break [Agent 3 finding]

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **`issue_lifecycle.py:730` reference clarification**: The issue's mention of this line is misleading. Line 730 uses Python `datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")` to build the body of a `## Deferred` section — not frontmatter, and not invoked by `capture-issue`. The shell `Z`-suffix format lives in `hooks/scripts/context-monitor.sh:155` and `hooks/scripts/precompact-state.sh:36`.
- **Timestamp format decision**: Two formats coexist — Python `isoformat(timespec="seconds")` yields `+00:00` suffix (used in `sync.py:490`); shell `date -u +%Y-%m-%dT%H:%M:%SZ` yields `Z` suffix (hook scripts). Since `capture-issue` is model-driven (Claude writes the file), the SKILL.md instruction should specify `Z`-suffix format consistent with hook scripts and the `strftime` pattern; the model will generate the string as text.
- **No schema enforcement**: `config-schema.json` does not enumerate valid frontmatter fields; adding `captured_at` requires only instruction + template changes — no schema update needed.
- **Downstream parse safety**: `_parse_discovered_date` in `search.py:21-29` (regex, truncates `[:10]`) and `issue_history/parsing.py:291-306` (dict `.get()`) both ignore unknown keys; existing issues without `captured_at` will continue working without errors.

## Impact

- **Priority**: P3 — Enhancement to date-only tracking; non-blocking for existing workflows
- **Effort**: Small — Two file changes (SKILL.md + templates.md); no schema update required
- **Risk**: Low — Downstream parsers (`_parse_discovered_date`, `issue_parser.py`) gracefully ignore unknown frontmatter keys
- **Breaking Change**: No

## Labels

`enhancement`, `frontmatter`, `capture-issue`, `captured`

## Resolution

- **Completed**: 2026-04-18
- **Action**: implement
- **Changes**:
  - `skills/capture-issue/SKILL.md`: Added `captured_at` ISO 8601 UTC timestamp instruction alongside `discovered_date`
  - `skills/capture-issue/templates.md`: Added `captured_at` field to heredoc template
  - `docs/reference/ISSUE_TEMPLATE.md`: Added `captured_at` row to Frontmatter Fields table and updated example block
  - `scripts/tests/fixtures/issues/bug-with-frontmatter.md`: Added `captured_at` field to fixture
  - `scripts/tests/test_frontmatter.py`: Added `test_iso_datetime_with_time_colons`
  - `scripts/tests/test_issue_parser.py`: Added `test_parse_file_ignores_captured_at`
  - `scripts/tests/test_issue_history_parsing.py`: Added `test_parse_ignores_captured_at`

## Status

**Completed** | Created: 2026-04-18 | Priority: P3

## Session Log
- `/ll:manage-issue` - 2026-04-18T00:00:00Z - `ffa52965-8df7-4476-a2af-96e098002a6a.jsonl`
- `/ll:ready-issue` - 2026-04-18T19:52:19 - `311b0048-94b7-43ed-8b52-3315bfa9b73c.jsonl`
- `/ll:confidence-check` - 2026-04-18T00:00:00Z - `64160c09-15da-40f5-93c4-7f4763f704b5.jsonl`
- `/ll:wire-issue` - 2026-04-18T19:48:29 - `3bda76dc-404d-4b1b-ba14-222e432841dc.jsonl`
- `/ll:refine-issue` - 2026-04-18T19:44:41 - `f5f8ff13-02e2-402d-a79e-ff1ffa675f42.jsonl`
- `/ll:issue-size-review` - 2026-04-18T00:00:00Z - `a53c2eef-b0c1-4768-8f1f-aa378a05c411.jsonl`
