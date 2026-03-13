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

1. In `scripts/little_loops/cli/issues/__init__.py`, add `--json` flag to the `show` and `sequence` subparsers
2. In `show.py`, add `if args.json: print(json.dumps(_parse_card_fields(content), indent=2)); return` branch in `cmd_show`
3. In `sequence.py`, add `if args.json: print(json.dumps([dataclasses.asdict(i) for i in ordered], indent=2)); return` branch in `cmd_sequence`
4. Add tests covering `--json` output for both subcommands

## Integration Map

- **Modified**: `scripts/little_loops/cli/issues/__init__.py` — subparser definitions (add `--json` to `show` and `sequence`)
- **Modified**: `scripts/little_loops/cli/issues/show.py` — `cmd_show()` (add JSON branch using `_parse_card_fields`)
- **Modified**: `scripts/little_loops/cli/issues/sequence.py` — `cmd_sequence()` (add JSON branch using `IssueInfo` objects)

## Impact

- **Priority**: P4 - Consistency improvement across CLI subcommands
- **Effort**: Small - Data structures already exist, just add `--json` arg and `json.dumps` output path
- **Risk**: Low - Additive feature, no change to existing output
- **Breaking Change**: No

## Labels

`feature`, `cli`, `ll-issues`

## Session Log
- `/ll:verify-issues` - 2026-03-13T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4a26704e-7913-498d-addf-8cd6c2ce63ff.jsonl`
- `/ll:scan-codebase` - 2026-03-13T00:36:53Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/44d09b8e-cdcf-4363-844c-3b6dbcf2cf7b.jsonl`
- `/ll:format-issue` - 2026-03-13T01:15:27Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f103ccc2-c870-4de7-a6e4-0320db6d9313.jsonl`

---

**Open** | Created: 2026-03-13 | Priority: P4

## Verification Notes

- **Date**: 2026-03-13
- **Verdict**: VALID
- `scripts/little_loops/cli/issues/show.py` and `sequence.py` have no `--json` flag or JSON output branch. `scripts/little_loops/cli/issues/list_cmd.py` already supports `--json` (line 36: `if getattr(args, "json", False)`). The inconsistency described is confirmed. Feature not yet implemented.
