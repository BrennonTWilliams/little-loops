---
discovered_commit: 3e9beeaf2bbe8608104beb89fbc7e2e2259310d8
discovered_branch: main
discovered_date: 2026-03-13T00:36:53Z
discovered_by: scan-codebase
---

# FEAT-701: Add `--json` output to `ll-issues show` and `ll-issues sequence`

## Summary

The `ll-issues show` and `ll-issues sequence` subcommands lack `--json` output mode, while sibling subcommands (`list`, `count`, `refine-status`) all support it. Both commands already produce structured data internally (`_parse_card_fields` returns a dict, `cmd_sequence` produces `IssueInfo` objects with `blockers`) that could be directly serialized.

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

## Acceptance Criteria

- [ ] `ll-issues show --json <issue-id>` outputs the card fields dict as JSON
- [ ] `ll-issues sequence --json` outputs the ordered list with blockers as JSON
- [ ] JSON output matches the structure of the internal data models
- [ ] Human-readable output remains the default (no `--json` flag)

## Impact

- **Priority**: P4 - Consistency improvement across CLI subcommands
- **Effort**: Small - Data structures already exist, just add `--json` arg and `json.dumps` output path
- **Risk**: Low - Additive feature, no change to existing output
- **Breaking Change**: No

## Labels

`feature`, `cli`, `ll-issues`

## Session Log
- `/ll:scan-codebase` - 2026-03-13T00:36:53Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/44d09b8e-cdcf-4363-844c-3b6dbcf2cf7b.jsonl`

---

**Open** | Created: 2026-03-13 | Priority: P4
