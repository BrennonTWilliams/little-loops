---
id: ENH-747
title: "Fix session log parsing gap: commands use append-log CLI"
type: ENH
priority: P2
status: active
discovered_date: 2026-03-14
discovered_by: capture-issue
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

1. Create `scripts/little_loops/cli/issues/append_log.py` with `cmd_append_log`
2. Wire `append-log` subcommand in `scripts/little_loops/cli/issues/__init__.py` (follow pattern from `next_id.py`)
3. Update Section 7 in `commands/refine-issue.md` + update Bash allowlist
4. Apply same change to Session Log sections in the 4 other commands
5. Add unit test: call `ll-issues append-log`, assert `count_session_commands` returns `{"/ll:refine-issue": 1}`
6. Run `python -m pytest scripts/tests/test_refine_status.py` — all existing tests pass

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
| `scripts/little_loops/cli/issues/__init__.py` | Wire `append-log` subcommand |
| `commands/refine-issue.md` | Replace manual log instruction + fix Bash allowlist |
| `commands/verify-issues.md` | Replace manual log instruction |
| `commands/scan-codebase.md` | Replace manual log instruction |
| `commands/tradeoff-review-issues.md` | Replace manual log instruction |
| `commands/ready-issue.md` | Replace manual log instruction |
| `scripts/tests/` | New unit test |

## Session Log
- `/ll:capture-issue` - 2026-03-14T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/aabfef22-628c-4e03-8fa8-e47f786c142f.jsonl`
