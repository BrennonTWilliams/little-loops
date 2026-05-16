---
discovered_commit: 3e9beeaf2bbe8608104beb89fbc7e2e2259310d8
discovered_branch: main
discovered_date: 2026-03-13T00:36:53Z
discovered_by: scan-codebase
---

# FEAT-701: Add `--json` output to `ll-issues show` and `ll-issues sequence`

## Summary

The `ll-issues show` and `ll-issues sequence` subcommands lack `--json` output mode, while sibling subcommands (`list`, `count`, `refine-status`) all support it.

## Motivation

Inconsistency across subcommands creates friction for automation: a developer building a tool around `ll-issues` must handle human-formatted output for `show` and `sequence` while other subcommands emit machine-readable JSON. The internal data structures already exist; the only gap is an output path. Both commands already produce structured data internally (`_parse_card_fields` returns a dict, `cmd_sequence` produces `IssueInfo` objects with `blockers`) that could be directly serialized.

## Location

- **File**: `scripts/little_loops/cli/issues/show.py` — `cmd_show`
- **File**: `scripts/little_loops/cli/issues/sequence.py` — `cmd_sequence`
- **File**: `scripts/little_loops/cli/issues/__init__.py` — subparser definitions

## Current Behavior

`show` renders a box-drawing ASCII card. `sequence` renders colored text lines. Neither supports `--json`.

## Expected Behavior

Both subcommands accept `--json` flag and emit structured JSON to stdout when set, consistent with `list`, `count`, and `refine-status`.

## Use Case

A developer building automation around `ll-issues` wants to parse issue details or dependency ordering programmatically. They pipe `ll-issues show --json BUG-685` or `ll-issues sequence --json` to `jq` for processing.

## Proposed Solution

Add `--json` argument to both subparsers and add a JSON output branch in `cmd_show` and `cmd_sequence`. Use `json.dumps(..., indent=2)` with the existing internal data structures (`_parse_card_fields` dict and `IssueInfo` objects).

## Acceptance Criteria

- [ ] `ll-issues show --json <issue-id>` outputs the card fields dict as JSON
- [ ] `ll-issues sequence --json` outputs the ordered list with blockers as JSON
- [ ] JSON output matches the structure of the internal data models
- [ ] Human-readable output remains the default (no `--json` flag)

## Implementation Steps

1. **`__init__.py` (lines 168–175 and 177–180)**: add `--json` to both subparsers:
   ```python
   seq.add_argument("--json", action="store_true", help="Output as JSON array")
   show_p.add_argument("--json", action="store_true", help="Output as JSON")
   ```

2. **`show.py` (`cmd_show`, lines 360–380)**: add JSON branch before `_render_card`. `_parse_card_fields` returns `dict[str, str | None]` which is already JSON-serializable — pass directly to `print_json`. Add `from little_loops.cli.output import print_json` import:
   ```python
   if getattr(args, "json", False):
       print_json(_parse_card_fields(path, config))
       return 0
   ```

3. **`sequence.py` (`cmd_sequence`, lines 14–60)**: add JSON branch after `ordered = ...[:limit]`. **Do not use `dataclasses.asdict`** — `IssueInfo.path` is a `Path` and `product_impact` is a nested dataclass; use inline dict matching the `list_cmd` pattern. Include `blocked_by` from `graph.blocked_by.get(issue.issue_id, set())` (line 46). Add `from little_loops.cli.output import print_json` import:
   ```python
   if getattr(args, "json", False):
       print_json([
           {
               "id": issue.issue_id,
               "priority": issue.priority,
               "title": issue.title,
               "path": str(issue.path),
               "blocked_by": sorted(graph.blocked_by.get(issue.issue_id, set())),
               "blocks": issue.blocks,
           }
           for issue in ordered
       ])
       return 0
   ```

4. **`tests/test_issues_cli.py`**: add `--json` test cases to `TestIssuesCLIShow` (line 565+) and `TestIssuesCLISequence` (line 337+) following the `TestIssuesCLIList` pattern (lines 71+): valid JSON, required fields, no ANSI codes, `return 0`

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/issues/__init__.py` — add `--json` to `show` (lines 177–180) and `sequence` (lines 168–175) subparsers
- `scripts/little_loops/cli/issues/show.py` — add JSON branch in `cmd_show()` (lines 360–380); no new imports needed (`_parse_card_fields` at lines 86–205 already returns `dict[str, str | None]`, directly JSON-serializable)
- `scripts/little_loops/cli/issues/sequence.py` — add JSON branch in `cmd_sequence()` (lines 14–60); needs `from little_loops.cli.output import print_json` import added

### Dependent Files (Reference Patterns)
- `scripts/little_loops/cli/issues/list_cmd.py:36–49` — canonical `--json` branch pattern (inline dict with `str(issue.path)`)
- `scripts/little_loops/cli/issues/count_cmd.py:32–50` — `--json` pattern with early `return 0`
- `scripts/little_loops/cli/output.py:97–99` — `print_json(data)` helper used by all JSON-enabled subcommands
- `scripts/little_loops/issue_parser.py:200–265` — `IssueInfo` dataclass definition and `.to_dict()` method

### Tests
- `scripts/tests/test_issues_cli.py` — `TestIssuesCLIShow` (line 565+) and `TestIssuesCLISequence` (line 337+); add `--json` test cases here following `TestIssuesCLIList` patterns (line 71+)

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `__init__.py:84` — `list` uses `ls.add_argument("--json", action="store_true", help="Output as JSON array")` — minimal form to follow
- `__init__.py:168–175` — `sequence` subparser currently only has `--limit` and `add_config_arg`; `--json` goes after `--limit`
- `__init__.py:177–180` — `show` subparser currently only has `issue_id` positional and `add_config_arg`; `--json` goes before `add_config_arg`
- `output.py:97–99` — `print_json` is a one-liner: `print(json.dumps(data, indent=2))`
- `sequence.py:46` — `graph.blocked_by.get(issue.issue_id, set())` provides blocker data; must be included in JSON output (not present on `IssueInfo` fields directly)
- `issue_parser.py:247–265` — `IssueInfo.to_dict()` exists as a hand-rolled method but no existing `--json` subcommand uses it; inline dict selection is the established pattern

## Impact

- **Priority**: P4 - Consistency improvement across CLI subcommands
- **Effort**: Small - Data structures already exist, just add `--json` arg and `json.dumps` output path
- **Risk**: Low - Additive feature, no change to existing output
- **Breaking Change**: No

## Labels

`feature`, `cli`, `ll-issues`

## Session Log
- `/ll:ready-issue` - 2026-03-15T15:51:55 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/22c491ee-9c66-4e34-98b9-b8404de0886f.jsonl`
- `/ll:verify-issues` - 2026-03-15T15:13:29 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/eaa8d229-0594-4366-bff7-6d5160769e5e.jsonl`
- `/ll:refine-issue` - 2026-03-15T15:11:34 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a8e50bdc-90a5-4bb0-8be1-47f4a3403f55.jsonl`
- `/ll:verify-issues` - 2026-03-13T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4a26704e-7913-498d-addf-8cd6c2ce63ff.jsonl`
- `/ll:scan-codebase` - 2026-03-13T00:36:53Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/44d09b8e-cdcf-4363-844c-3b6dbcf2cf7b.jsonl`
- `/ll:format-issue` - 2026-03-13T01:15:27Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f103ccc2-c870-4de7-a6e4-0320db6d9313.jsonl`

---

**Completed** | Created: 2026-03-13 | Priority: P4

## Resolution

- Added `--json` flag to `sequence` subparser in `__init__.py` (after `--limit`)
- Added `--json` flag to `show` subparser in `__init__.py` (before `add_config_arg`)
- Added JSON branch in `cmd_show` using `_parse_card_fields` dict (already JSON-serializable)
- Added JSON branch in `cmd_sequence` using inline dict with `id`, `priority`, `title`, `path`, `blocked_by`, `blocks`
- Added `print_json` import to both `show.py` and `sequence.py`
- Added 5 new tests: `test_sequence_json_output`, `test_sequence_json_no_color_codes`, `test_show_json_output`, `test_show_json_no_color_codes`, `test_show_json_not_found`
- All 3509 tests pass, lint clean

## Verification Notes

- **Date**: 2026-03-13
- **Verdict**: VALID
- `scripts/little_loops/cli/issues/show.py` and `sequence.py` have no `--json` flag or JSON output branch. `scripts/little_loops/cli/issues/list_cmd.py` already supports `--json` (line 36: `if getattr(args, "json", False)`). The inconsistency described is confirmed. Feature not yet implemented.
