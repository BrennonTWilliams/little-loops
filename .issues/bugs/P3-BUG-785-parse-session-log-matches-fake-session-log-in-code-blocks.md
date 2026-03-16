---
discovered_date: 2026-03-16
discovered_by: /ll:capture-issue
source_loop: issue-refinement
---

# BUG-785: `parse_session_log` matches fake `## Session Log` headings inside fenced code blocks

## Summary

`parse_session_log` uses `re.search()` against `_SESSION_LOG_SECTION_RE`, which finds the **first** occurrence of `^## Session Log` in the file. For issues whose body contains a fenced code block that documents the session log format (like FEAT-638), the fake heading appears earlier in the file than the real one and is matched instead. The real section is never read, so the function returns `[]` and the issue appears to have no session log commands.

## Current Behavior

For FEAT-638, `parse_session_log` returns `[]` despite the file having 10+ real session log entries at line 498. Two `## Session Log` occurrences exist:
- Line 40: inside a markdown code block example (fake — part of the issue description)
- Line 498: the real section with actual `/ll:*` command entries

`re.search()` matches line 40 first. The content between it and the next `##`/`---` is the code block continuation, which contains no `/ll:*` backtick-quoted entries, so `_COMMAND_RE` finds nothing.

**Confirmed today:**
```
ll-issues refine-status --json | jq '.[] | select(.id=="FEAT-638") | {commands, formatted}'
→ { "commands": [], "formatted": true }
```

## Root Cause

`scripts/little_loops/session_log.py:16-18`:
```python
_SESSION_LOG_SECTION_RE = re.compile(
    r"^## Session Log\s*\n+(.*?)(?:\n##|\n---|\Z)", re.MULTILINE | re.DOTALL
)
```

The regex uses `.search()` (not `.findall()` or a last-match strategy) and has no awareness of fenced code block context (```` ``` ````). Any `## Session Log` at column 0 — even inside a code fence — is matched.

## Impact

- `ll-issues refine-status` shows `commands: []` and the wrong session depth for affected issues
- The `issue-refinement` loop's `evaluate` state sees `has_verify=False` for these issues, triggering `NEEDS_FORMAT` indefinitely even after format and verify have run successfully
- Caused FEAT-638 to be re-processed 9+ times across multiple loop runs

## Proposed Fix

Use `re.findall()` or `re.finditer()` and select the **last** match instead of the first, since the real `## Session Log` is always at the bottom of issue files and the fake ones appear earlier in the body.

Alternatively, pre-strip fenced code blocks before applying the regex.

The last-match approach is simpler and consistent with the section placement convention:

```python
matches = list(_SESSION_LOG_SECTION_RE.finditer(content))
if not matches:
    return []
log_match = matches[-1]  # real section is always last
```

## Acceptance Criteria

- [ ] `parse_session_log` returns the commands from the real `## Session Log` section for FEAT-638
- [ ] `ll-issues refine-status --json` shows non-empty `commands` for FEAT-638
- [ ] Issues with `## Session Log` examples in their body are not affected
- [ ] Existing tests in `test_refine_status.py` and `test_session_log.py` pass
- [ ] New regression test: issue file with `## Session Log` in body code block still returns real section commands

## Related Issues

- Caused the infinite-loop behavior described in BUG-743 (completed) to persist for FEAT-638 even after that fix was applied
- BUG-640 (completed) added session log checking to `is_formatted` but didn't address the wrong-section match

## Labels

`bug`, `session-log`, `parser`, `captured`

## Status

**Open** | Created: 2026-03-16 | Priority: P3

## Session Log
- `/ll:capture-issue` - 2026-03-16T20:08:11Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fffc83c9-009a-4696-8010-040737bf7247.jsonl`
