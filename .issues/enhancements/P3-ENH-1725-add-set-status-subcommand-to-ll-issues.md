---
id: ENH-1725
title: Add set-status subcommand to ll-issues
type: ENH
status: done
priority: P3
captured_at: '2026-05-26T20:15:32Z'
completed_at: '2026-05-26T21:02:11Z'
discovered_date: '2026-05-26'
discovered_by: capture-issue
confidence_score: 95
outcome_confidence: 86
score_complexity: 18
score_test_coverage: 18
score_ambiguity: 25
score_change_surface: 25
---

# ENH-1725: Add set-status subcommand to ll-issues

## Summary

`ll-issues` currently has no CLI subcommand to change the `status:` frontmatter field of an issue file. Users must edit frontmatter manually or use a `sed` one-liner. Adding a `set-status` subcommand would provide a first-class, safe way to transition issue status from the command line.

## Current Behavior

There is no `ll-issues set-status` command. Changing status requires either:
- Direct file edit
- `sed -i '' 's/^status: open/status: in_progress/' "$(ll-issues path FEAT-123)"`

## Expected Behavior

```bash
ll-issues set-status ENH-1725 in_progress
ll-issues set-status BUG-042 done
ll-issues ss ENH-1725 blocked   # short alias
```

The command should:
1. Resolve the issue file path via the existing `path` logic
2. Validate the new status value against the canonical enum (`open`, `in_progress`, `blocked`, `deferred`, `done`, `cancelled`)
3. Edit the `status:` frontmatter field in-place
4. Print the result (e.g., `ENH-1725: open → in_progress`)
5. Exit non-zero on invalid status or unknown issue ID

## Motivation

Status changes are frequent during sprint execution and issue triage. Today they require knowing the file path and using shell incantations. A `set-status` subcommand makes the operation scriptable, safe (validated enum), and consistent with the rest of the `ll-issues` surface area. It would also enable automation loops and hooks to update status without fragile sed calls.

## Proposed Solution

Create `scripts/little_loops/cli/issues/set_status.py` with `cmd_set_status()`, then register it in `scripts/little_loops/cli/issues/__init__.py` (import + subparser + dispatch). Use `_resolve_issue_id` from `show.py` for path resolution and `update_frontmatter` from `frontmatter.py` for the in-place write — the same two utilities used by `cmd_set_scores()`. Note: the `ss` alias is already taken by `set-scores`; use `sst` or no alias.

## Integration Map

### Files to Create
- `scripts/little_loops/cli/issues/set_status.py` — new `cmd_set_status()` function; the CLI submodule pattern requires a new file per subcommand

### Files to Modify
- `scripts/little_loops/cli/issues/__init__.py` — **four separate locations**:
  1. Import block (top): add `from little_loops.cli.issues.set_status import cmd_set_status`
  2. Subparser registration block (middle): register `set-status` parser with alias `ss` — note `set-scores` already uses `ss`, so this alias will conflict; use `sst` or none
  3. Dispatch chain (bottom): add `if args.command == "set-status": return cmd_set_status(config, args)`
  4. `epilog` text block — the hand-maintained "Sub-commands:" list (lines 50–64) and "Examples:" block (lines 65–104) are **not** auto-generated from registered subparsers; add a `set-status` entry to both sections
- `commands/help.md` — line ~251 ll-issues summary line; add `set-status` to the subcommand list shown by `/ll:help`
- `docs/reference/CLI.md` — insert a new `#### ll-issues set-status / ll-issues sst` H4 entry after the existing `#### ll-issues set-scores` entry; also add example invocations to the consolidated examples block

_Wiring pass added by `/ll:wire-issue`:_

### Dependent Files (Callers/Importers)
- Any automation loops or hooks that currently use `sed` to change status can be updated to use `ll-issues set-status`
- `scripts/little_loops/frontmatter.py` — `update_frontmatter()` (the actual write helper; `issue_utils.py` does not exist)
- `scripts/little_loops/cli/issues/show.py` — `_resolve_issue_id()` (shared path resolver used by all subcommands)

### Similar Patterns
- `scripts/little_loops/cli/issues/set_scores.py` — `cmd_set_scores()`: exact `_resolve_issue_id` + `update_frontmatter` write pattern; no `VALID_STATUSES` constant exists, use `argparse choices=` for validation
- `scripts/little_loops/cli/issues/skip.py` — `cmd_skip()`: shows stderr error format and stdout confirmation pattern

### Tests
- `scripts/tests/test_set_status_cli.py` — new test file following `scripts/tests/test_set_scores_cli.py` pattern; use `TestIssuesCLISetStatus` class with `temp_project_dir`, `sample_config`, `issues_dir` fixtures from `conftest.py`
- Test cases: valid transition (happy path), invalid status value (exit 1), unknown ID (exit 1)

### Documentation
- `.claude/CLAUDE.md` CLI Tools section — add `set-status` to `ll-issues` description (around line 61)

### Configuration
- No single `VALID_STATUSES` constant exists; use inline `choices=["open", "in_progress", "blocked", "deferred", "done", "cancelled"]` in argparse (same pattern as `--status` in `list`/`search`/`count` subparsers in `__init__.py` lines 128, 208, 280)

## Implementation Steps

1. Create `scripts/little_loops/cli/issues/set_status.py` with `cmd_set_status(config, args)` following `set_scores.py` exactly:
   - `from little_loops.cli.issues.show import _resolve_issue_id`
   - `from little_loops.frontmatter import update_frontmatter`
   - Resolve path via `_resolve_issue_id(config, args.issue_id)`; print `Error: Issue '...' not found.` to `sys.stderr`, return `1` on miss
   - Validate `args.status` against canonical list (argparse `choices=` handles this before handler runs)
   - Read current status via `parse_frontmatter(path.read_text()).get("status", "unknown")` to build the `old → new` output
   - `content = path.read_text(); new_content = update_frontmatter(content, {"status": args.status}); path.write_text(new_content)`
   - Print `{args.issue_id}: {old_status} → {args.status}` to stdout; return `0`
2. Edit `scripts/little_loops/cli/issues/__init__.py` in three locations:
   - Add import near other subcommand imports
   - Register subparser: `st = subs.add_parser("set-status", aliases=["sst"], help="Set issue status")` with positional `issue_id`, positional `status` with `choices=[...]`, `set_defaults(command="set-status")`, `add_config_arg(st)` — **check `ss` alias conflict with `set-scores`**
   - Add dispatch: `if args.command == "set-status": return cmd_set_status(config, args)`
3. Create `scripts/tests/test_set_status_cli.py` with `TestIssuesCLISetStatus` class using `temp_project_dir`/`sample_config`/`issues_dir` fixtures; test: valid transition writes frontmatter and prints `old → new`, invalid status rejected by argparse (exit 2), unknown ID returns 1
4. Update `.claude/CLAUDE.md` `ll-issues` description to include `set-status`
5. Update `commands/help.md` ll-issues summary line (~line 251) to include `set-status`
6. Add `#### ll-issues set-status / ll-issues sst` H4 entry to `docs/reference/CLI.md` after the `set-scores` section; add example invocations to the consolidated examples block in the same file
7. Run `python -m pytest scripts/tests/test_set_status_cli.py -v`

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

8. Update `__init__.py` epilog text block — the "Sub-commands:" list and "Examples:" section are hand-maintained strings, not auto-generated; add `set-status` entry to both
9. Update `commands/help.md` line ~251 — ll-issues one-line summary used by `/ll:help`
10. Update `docs/reference/CLI.md` — new H4 section for `set-status` + examples in the consolidated block

## Impact

- **Priority**: P3 - Quality-of-life; frequent friction point during sprint work
- **Effort**: Small - ~1 hour; follows established `set-scores` pattern exactly
- **Risk**: Low - isolated frontmatter write, no side effects
- **Breaking Change**: No

## Scope Boundaries

**In scope:**
- `ll-issues set-status <ID> <status>` (and optionally `ll-issues sst ...` alias — `ss` is taken by `set-scores`)
- Validation against the canonical status enum
- In-place frontmatter update of the `status:` field only
- Printed confirmation of the transition (e.g., `ENH-1725: open → in_progress`)
- Non-zero exit on invalid status value or unknown issue ID

**Out of scope:**
- Batch status changes (multiple issues in one invocation)
- Status transition validation / workflow enforcement (e.g., blocking `done → open`)
- Status history or audit trail
- Updating other frontmatter fields (priority, labels, etc.)
- Triggering GitHub Issues sync on status change
- Hooks or event-bus notifications on status change

## API/Interface

```python
# Proposed CLI surface
ll-issues set-status <ISSUE_ID> <status>
ll-issues ss <ISSUE_ID> <status>

# Output
ENH-1725: open → in_progress

# Error cases
Error: unknown status 'wip'. Valid values: open, in_progress, blocked, deferred, done, cancelled
Error: issue not found: ENH-9999
```

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`cli`, `captured`

## Resolution

Implemented `ll-issues set-status <ID> <status>` (alias: `sst`) following the `set-scores` pattern exactly. Created `scripts/little_loops/cli/issues/set_status.py` with `cmd_set_status()`, registered the subparser with `choices=` validation in `__init__.py`, and added 5 tests covering happy path, transition output, field preservation, unknown ID, and invalid status rejection. Updated `docs/reference/CLI.md`, `commands/help.md`, and `.claude/CLAUDE.md`.

## Status

**Done** | Created: 2026-05-26 | Completed: 2026-05-26 | Priority: P3

## Session Log
- `/ll:ready-issue` - 2026-05-26T20:56:18 - `08569b32-e98a-481e-bbd9-087eb6d434d7.jsonl`
- `/ll:confidence-check` - 2026-05-26T21:00:00Z - `dc7968db-3e9d-4d3f-9e5f-c474581ec628.jsonl`
- `/ll:wire-issue` - 2026-05-26T20:52:18 - `2a278fd8-3fcf-49da-87b1-0e71e703408d.jsonl`
- `/ll:refine-issue` - 2026-05-26T20:47:46 - `b3848533-ceeb-4ba0-a2a3-728158b97567.jsonl`
- `/ll:format-issue` - 2026-05-26T20:18:01 - `67bf951e-1315-435e-b229-24894f754149.jsonl`
- `/ll:capture-issue` - 2026-05-26T20:15:32Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/`
- `/ll:manage-issue` - 2026-05-26T21:02:11Z