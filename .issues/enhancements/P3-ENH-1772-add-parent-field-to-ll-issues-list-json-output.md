---
id: ENH-1772
type: ENH
priority: P3
status: done
decision_needed: false
captured_at: '2026-05-28T00:00:00Z'
discovered_date: 2026-05-28
discovered_by: capture-issue
labels:
- enhancement
- cli
confidence_score: 100
outcome_confidence: 95
score_complexity: 25
score_test_coverage: 20
score_ambiguity: 25
score_change_surface: 25
---

# ENH-1772: Add `parent` field to `ll-issues list --json` output

## Summary

`ll-issues list --group-by epic` already reads and understands the `parent:`
frontmatter field, correctly grouping children under their parent EPICs and
listing unparented issues under "Unparented." However, the `--json` output
omits `parent` entirely. Scripted consumers (like `/ll:link-epics`) are forced
to re-read every issue file individually to check parent status — fragile
(prone to the `head -5` class of parsing bug), slow (N+1 file reads), and
redundant since the tool already holds the data in memory.

Add `"parent": "EPIC-1694"` (or `"parent": null` for unparented issues) to
the JSON output.

## Current Behavior

`ll-issues list --json` outputs issue metadata (id, type, priority, status,
title, etc.) but excludes the `parent` field even though the tool already
parses `parent:` from frontmatter for `--group-by epic` grouping. Scripted
consumers must re-read each issue file individually to check parent status,
doing N+1 file reads on already-parsed data.

## Expected Behavior

`ll-issues list --json` includes a `"parent"` key in each issue's JSON object:

- `"parent": "EPIC-1694"` for issues with a `parent:` frontmatter field
- `"parent": null` for unparented issues

## Motivation

Discovered during `/ll:link-epics` execution where a `head -5 | grep parent:`
shortcut missed `parent:` fields sitting at lines 6–11 of longer frontmatter
blocks, causing 35 of 36 issues to be misidentified as orphans. The tool
already parsed these correctly — it just didn't expose the field in JSON.

## Scope Boundaries

- **In scope**: Add `parent` key to `--json` output dict sourced from the
  already-parsed `parent:` frontmatter field; `null` when absent or empty
- **Out of scope**: Changing `--group-by epic` grouping behavior; modifying
  frontmatter parsing itself; adding `parent` to non-JSON output formats;
  recursive parent resolution (grandparent chains); backfilling missing
  `parent:` fields in existing issues

## Success Metrics

- `ll-issues list --json | jq '.[].parent'` — every issue object has the key
  (no `null`-key errors from missing fields)
- All 36 issues in the EPIC-1694 hierarchy correctly report parent status
  without requiring per-file reads
- Existing `--group-by epic` output is unchanged (regression check)
- Existing JSON consumers are unaffected (additive key, ignored by strict
  parsers)

## API/Interface

No new CLI flags or commands. The `--json` output schema gains one optional
key per issue object. Existing consumers that ignore unknown keys are
unaffected.

## Implementation Steps

All steps completed. The feature is already implemented in the current codebase.

1. ~~Locate the JSON serialization path~~ — Found at `list_cmd.py:110-127` (already includes `parent`)
2. ~~Add `"parent"` key~~ — Already present at `list_cmd.py:121`: `"parent": issue.parent`
3. ~~Verify `--group-by epic` is unaffected~~ — `list_cmd.py:146` reads the same `issue.parent` attribute
4. ~~Add a test~~ — `test_list_json_output_contains_parent_key` at `test_issues_cli.py:716-739`

### Codebase Research Findings

_Added by `/ll:refine-issue` — codebase analysis on 2026-05-28:_

- **`list_cmd.py:121`**: `"parent": issue.parent` already in JSON output dict
- **`list_cmd.py:146`**: `--group-by epic` reads same `issue.parent` for grouping
- **`search.py:427`**: `ll-issues search --json` also includes `"parent": issue.parent`
- **`issue_parser.py:491-497`**: `parent` parsed from frontmatter (with `parent_issue:` fallback)
- **`issue_parser.py:251`**: `IssueInfo.parent: str | None = None` dataclass field
- **`test_issues_cli.py:716-739`**: `test_list_json_output_contains_parent_key` validates `"parent" in item` for every JSON item
- **`test_issues_cli.py:364`**: Basic JSON structure test also asserts `"parent"` key presence

The `parent` field is also in `IssueInfo.to_dict()` (`issue_parser.py:296`) for downstream consumers.

Notable gap: `ll-issues search --json` includes `parent` but NOT `milestone` (`search.py:427-428` has 9 keys vs `list_cmd.py:110-127` which has 10). This is a separate concern from ENH-1772.

## Integration Map

### Files to Modify (All Already Done)

- `scripts/little_loops/cli/issues/list_cmd.py:121` — `"parent": issue.parent` in JSON output dict
- `scripts/little_loops/cli/issues/search.py:427` — same field in search JSON output

### Dependent Files (Callers/Importers)

- `scripts/little_loops/cli/issues/list_cmd.py:146` — `--group-by epic` reads same `issue.parent`
- `scripts/little_loops/issue_parser.py:491-497` — parses `parent:` from frontmatter
- `scripts/little_loops/issue_parser.py:251` — `IssueInfo.parent: str | None` dataclass field
- `scripts/little_loops/issue_parser.py:296` — `to_dict()` includes `"parent": self.parent`

### Tests

- `scripts/tests/test_issues_cli.py:716-739` — `test_list_json_output_contains_parent_key`
- `scripts/tests/test_issues_cli.py:364` — basic JSON structure test asserts `"parent" in item`
- `scripts/tests/test_issues_cli.py:82-95` — `issues_dir_with_epic_children` fixture with `parent: EPIC-001`
- `scripts/tests/test_issues_search.py:759-790` — `test_json_output` asserts `"parent" in item` [added by `/ll:wire-issue`]

### Test Coverage Gaps

_Wiring pass added by `/ll:wire-issue` — non-blocking, implementation already done:_

- **Parent value correctness**: No test asserts the actual `parent` string value (e.g., `assert item["parent"] == "EPIC-001"`). Both `test_list_json_output_contains_parent_key` and `test_json_output` only check `"parent" in item`. The `issues_dir_with_epic_children` fixture creates parented issues but no test validates the value.
- **Null parent for unparented issues**: No test explicitly verifies `parent: null` (JSON `null` from Python `None`) for issues without a `parent:` frontmatter field. The `issues_dir` fixture creates such issues but only key presence is asserted, not the null value.
- **Search JSON parent value**: `search_issues_dir` fixture (test_issues_search.py:20) creates issues without `parent:` fields — no search test fixture includes parent-child relationships to validate the value.

## Impact

- **Priority**: P3 — quality improvement; no production blocker
- **Effort**: Small — one field addition in an existing serialization path
- **Risk**: Low — additive; existing JSON consumers ignore unknown keys
- **Breaking Change**: No

## Session Log
- `/ll:wire-issue` - 2026-05-29T00:45:58 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9758e744-69de-430a-84f0-b232214070a2.jsonl`
- `/ll:refine-issue` - 2026-05-29T00:39:42 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f1cd2a48-09ca-45a0-a6fb-8f62f61cdc82.jsonl`
- `/ll:format-issue` - 2026-05-29T00:32:41 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9caaa3f7-2224-4d38-a67a-774a4a2bb3b0.jsonl`

- `/ll:capture-issue` - 2026-05-28T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/`
