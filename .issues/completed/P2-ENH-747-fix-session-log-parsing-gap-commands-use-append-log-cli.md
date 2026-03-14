---
id: ENH-747
title: "Fix session log parsing gap: commands use append-log CLI"
type: ENH
priority: P2
status: completed
discovered_date: 2026-03-14
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 85
---

# ENH-747: Fix session log parsing gap: commands use append-log CLI

## Problem Statement

Several commands (`refine-issue`, `verify-issues`, `scan-codebase`, `tradeoff-review-issues`, `ready-issue`) instruct Claude to write session log entries **manually** using the Edit tool. The `count_session_commands()` regex in `session_log.py` requires backtick-quoted command names:

```python
_COMMAND_RE = re.compile(r"`(/[\w:-]+)`")
```

When Claude writes entries manually, it may omit backticks, use prose, or misplace the entry outside `## Session Log`. None of these match `_COMMAND_RE`, so `ll-issues refine-status` shows `refine=0` even after multiple runs.

The `append_session_log_entry()` function already builds correctly-formatted entries — the gap is that commands never call it.

## Motivation

`ll-issues refine-status` is used to gauge how well-researched an issue is before sprint planning. Broken counts undermine trust in the tool and can cause under-refined issues to slip into sprints undetected.

**Why P2:** The bug silently corrupts refinement tracking data across all affected commands, not just `refine-issue`.

## Proposed Fix

### 1. Add `ll-issues append-log` CLI subcommand

**New file**: `scripts/little_loops/cli/issues/append_log.py`

```python
def cmd_append_log(config, args):
    from little_loops.session_log import append_session_log_entry
    success = append_session_log_entry(Path(args.issue_path), args.command)
    if not success:
        print("Warning: could not resolve session JSONL; entry not written.", file=sys.stderr)
        return 1
    return 0
```

Wire into `scripts/little_loops/cli/issues/__init__.py`.

**CLI signature:**
```
ll-issues append-log <issue-path> <command>
# e.g.
ll-issues append-log .issues/bugs/P2-BUG-123-foo.md /ll:refine-issue
```

### 2. Update affected commands

Replace the manual prose instruction with a structured Bash call in the Session Log section of each command:

```markdown
### N. Append Session Log

Use the Bash tool to append a session log entry:

```bash
ll-issues append-log <path-to-issue-file> /ll:<command-name>
```

If `ll-issues` is not available, fall back to manually appending with **exactly** this format (backticks required):

```
- `/ll:<command-name>` - YYYY-MM-DDTHH:MM:SS - `<absolute path to session JSONL>`
```
```

**Commands to update:**
- `commands/refine-issue.md` — also update Bash allowlist from `Bash(git:*)` to `Bash(git:*, ll-issues:*)`
- `commands/verify-issues.md`
- `commands/scan-codebase.md`
- `commands/tradeoff-review-issues.md`
- `commands/ready-issue.md`

## Implementation Steps

1. Create `scripts/little_loops/cli/issues/append_log.py` with `cmd_append_log(config, args)` — takes two positional args: `issue_path` and `command`
2. Wire `append-log` subcommand in `scripts/little_loops/cli/issues/__init__.py` (follow `next_id.py` pattern); also update epilog string at lines 31–54 to list `append-log`
3. Update Section 7 in `commands/refine-issue.md` (lines 384–393) + update Bash allowlist from `Bash(git:*)` to `Bash(git:*, ll-issues:*)`
4. Apply same change to Session Log sections in the 4 other commands:
   - `commands/verify-issues.md` — Section 4.5, lines 146–155
   - `commands/scan-codebase.md` — Section 5.5, lines 315–323
   - `commands/tradeoff-review-issues.md` — **two locations**: lines 251–258 (closures) and lines 285–292 (updates)
   - `commands/ready-issue.md` — Section 5 item 7, lines 246–253
5. Add `TestIssuesAppendLog` class to `scripts/tests/test_issues_cli.py` (follow `TestIssuesCLIShow` pattern); assert `count_session_commands` returns `{"/ll:refine-issue": 1}`
6. Run `python -m pytest scripts/tests/test_refine_status.py` — all existing tests pass

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

### Files to Modify
- `scripts/little_loops/cli/issues/append_log.py` — New file; `cmd_append_log(config, args)` with positional args `issue_path` and `command`
- `scripts/little_loops/cli/issues/__init__.py` — Add subcommand registration (lines 57–162 dispatch block) and update epilog string (lines 31–54)
- `commands/refine-issue.md` — Section 7 at lines 384–393; frontmatter `allowed-tools` at line 9 (`Bash(git:*)` → `Bash(git:*, ll-issues:*)`)
- `commands/verify-issues.md` — Section 4.5 at lines 146–155
- `commands/scan-codebase.md` — Section 5.5 at lines 315–323
- `commands/tradeoff-review-issues.md` — **Two locations**: lines 251–258 (closures block) and lines 285–292 (updates block)
- `commands/ready-issue.md` — Section 5 item 7 at lines 246–253

### Dependent Files (Callers of session_log)
- `scripts/little_loops/cli/issues/refine_status.py` — consumes `session_command_counts` at lines 220, 240, 339 (this is the broken output ENH-747 fixes)
- `scripts/little_loops/cli/issues/show.py` — also imports `session_log`

### Tests
- `scripts/tests/test_issues_cli.py` — add `TestIssuesAppendLog` class; use `patch.object(sys, "argv", [...])` + `main_issues()` invocation pattern (see `TestIssuesCLIShow` at line 565)
- `scripts/tests/test_refine_status.py` — existing tests must still pass; `_make_issue()` helper at line 19
- `scripts/tests/test_session_log.py` — existing `append_session_log_entry` tests at line 56

### Core Dependency
- `scripts/little_loops/session_log.py` — `_COMMAND_RE` at line 20, `count_session_commands()` at line 42, `append_session_log_entry()` at line 85 (auto-detects JSONL via `get_current_session_jsonl()`)

## Existing Utilities to Reuse

- `little_loops.session_log.append_session_log_entry` — already formats entries correctly
- `little_loops.session_log.get_current_session_jsonl` — handles JSONL lookup
- `scripts/little_loops/cli/issues/next_id.py` — pattern to follow for new subcommand

## Acceptance Criteria

- [ ] `ll-issues append-log` subcommand exists and appends a correctly-formatted entry
- [ ] `count_session_commands` returns `{"/ll:refine-issue": 1}` after one `append-log` call
- [ ] `commands/refine-issue.md` uses Bash call instead of prose instruction
- [ ] All 5 affected commands updated
- [ ] `ll-issues refine-status` increments count after `/ll:refine-issue` run
- [ ] Existing `test_refine_status.py` tests pass

## Files to Change

| File | Change |
|------|--------|
| `scripts/little_loops/cli/issues/append_log.py` | New — `cmd_append_log` |
| `scripts/little_loops/cli/issues/__init__.py` | Wire `append-log` subcommand + update epilog string (lines 31–54) |
| `commands/refine-issue.md` | Replace manual log instruction (lines 384–393) + fix Bash allowlist (line 9) |
| `commands/verify-issues.md` | Replace manual log instruction (lines 146–155) |
| `commands/scan-codebase.md` | Replace manual log instruction (lines 315–323) |
| `commands/tradeoff-review-issues.md` | Replace **two** Session Log locations: lines 251–258 (closures) and lines 285–292 (updates) |
| `commands/ready-issue.md` | Replace manual log instruction (lines 246–253) |
| `scripts/tests/test_issues_cli.py` | Add `TestIssuesAppendLog` class |

## Resolution

Added `ll-issues append-log <issue-path> <command>` CLI subcommand that calls `append_session_log_entry()` to write correctly-formatted session log entries. Updated all 5 affected commands to use the Bash call instead of prose instructions, with a fallback format reminder. All acceptance criteria met and existing tests pass.

## Session Log
- `/ll:manage-issue` - 2026-03-14T23:01:41 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/7e5c627d-e423-4c1f-a8cd-744f74433d0a.jsonl`
- `/ll:ready-issue` - 2026-03-14T13:30:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1d28749d-5035-43a2-9e52-bb9032eaedf5.jsonl`
- `/ll:ready-issue` - 2026-03-14T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/33fcb067-47f1-425b-a171-05818ef871c0.jsonl`
- `/ll:refine-issue` - 2026-03-14T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d24d5545-ed0e-442c-bda6-db81c236d356.jsonl`
- `/ll:capture-issue` - 2026-03-14T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/aabfef22-628c-4e03-8fa8-e47f786c142f.jsonl`
- `/ll:confidence-check` - 2026-03-14T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d7e0a0db-64e6-4879-b6c8-794f0df9eb0b.jsonl`
