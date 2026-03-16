---
discovered_date: 2026-03-16
discovered_by: /ll:capture-issue
source_loop: issue-refinement
confidence_score: 100
outcome_confidence: 86
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

## Implementation Steps

1. **Fix `parse_session_log`** (`session_log.py:34`): Replace `_SESSION_LOG_SECTION_RE.search(content)` with `finditer` + last-match:
   ```python
   matches = list(_SESSION_LOG_SECTION_RE.finditer(content))
   if not matches:
       return []
   log_match = matches[-1]
   ```

2. **Fix `count_session_commands`** (`session_log.py:53`): Apply the identical last-match change to the `.search()` call there.

3. **Fix `append_session_log_entry`** (`session_log.py:113`): Replace the `content.replace("## Session Log\n", ..., 1)` strategy with a last-occurrence replacement. Use `rfind("## Session Log")` to locate the real section before inserting.

4. **Fix `show.py` inline regex** (`show.py:174-176`): Replace the inline `re.search(...)` with either `re.findall`/`finditer` last-match, or replace the whole block with a call to `parse_session_log` (which will be fixed in step 1).

5. **Add regression test** (`test_session_log.py`): Following the pattern in `TestParseSessionLog` (inline multiline strings, e.g. lines 193-210), add a test with a fenced code block containing a fake `## Session Log` heading before the real section. Assert that the real section's commands are returned. See `test_dependency_mapper.py:70-84` for the triple-quoted fence pattern.

6. **Verify** by running:
   ```bash
   python -m pytest scripts/tests/test_session_log.py scripts/tests/test_refine_status.py -v
   ```
   Then confirm manually:
   ```bash
   ll-issues refine-status --json | jq '.[] | select(.id=="FEAT-638") | {commands, formatted}'
   ```

## Acceptance Criteria

- [ ] `parse_session_log` returns the commands from the real `## Session Log` section for FEAT-638
- [ ] `ll-issues refine-status --json` shows non-empty `commands` for FEAT-638
- [ ] Issues with `## Session Log` examples in their body are not affected
- [ ] Existing tests in `test_refine_status.py` and `test_session_log.py` pass
- [ ] New regression test: issue file with `## Session Log` in body code block still returns real section commands

## Integration Map

### Files to Modify
- `scripts/little_loops/session_log.py:34` — `parse_session_log`: change `.search()` to `.finditer()` + last-match
- `scripts/little_loops/session_log.py:53` — `count_session_commands`: same `.search()` → last-match fix
- `scripts/little_loops/session_log.py:113` — `append_session_log_entry`: uses `"## Session Log" in content` + `.replace(..., count=1)`, which inserts into the first occurrence (fake heading). Needs the same last-occurrence strategy.
- `scripts/little_loops/cli/issues/show.py:174-176` — inline duplicate of `_SESSION_LOG_SECTION_RE` with `re.search()`. Must be updated to last-match as well (or replaced with a call to `parse_session_log`).

### Dependent Files (Callers/Importers)
- `scripts/little_loops/issue_parser.py:61,69` — `is_formatted` calls `parse_session_log`; fix propagates automatically
- `scripts/little_loops/issue_parser.py:355-358` — `IssueParser.parse` calls both `parse_session_log` and `count_session_commands`; fix propagates automatically
- `scripts/little_loops/cli/issues/refine_status.py:230` — `cmd_refine_status` consumes `IssueInfo.session_commands` and `is_formatted`; fix propagates automatically

### Tests
- `scripts/tests/test_session_log.py:153` — `TestParseSessionLog` class: add regression test for fake heading in code block (no existing coverage for this case)
- `scripts/tests/test_refine_status.py` — consider adding a test where the issue file has a fake `## Session Log` in the body; `_make_issue` helper at line 19 can be extended or a raw fixture file used
- `scripts/tests/fixtures/issues/feature-with-code-fence.md` — existing fixture for the "fake heading in fence" pattern; a parallel `session-log-with-fake-heading.md` fixture file would be the canonical regression test file

### Similar Patterns (for implementation reference)
- `scripts/little_loops/text_utils.py:21,77` — `_CODE_FENCE = re.compile(r"```[\s\S]*?```", re.MULTILINE)` + `.sub("", content)` — the strip-code-fences approach used elsewhere
- `scripts/little_loops/dependency_mapper/analysis.py:28,114` — same strip pattern in dependency mapper
- `scripts/little_loops/issue_parser.py:528-551` — `_strip_code_fences()` line-by-line state machine (preserves line counts); could be reused if the strip approach is preferred over last-match
- `scripts/tests/test_dependency_mapper.py:70-84` — test fixture pattern for "fake match inside code fence" using inline triple-quoted string

## Related Issues

- Caused the infinite-loop behavior described in BUG-743 (completed) to persist for FEAT-638 even after that fix was applied
- BUG-640 (completed) added session log checking to `is_formatted` but didn't address the wrong-section match

## Labels

`bug`, `session-log`, `parser`, `captured`

## Status

**Open** | Created: 2026-03-16 | Priority: P3

## Session Log
- `/ll:confidence-check` - 2026-03-16T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/846dd31f-a623-4c2c-a94c-fed5d665b7f6.jsonl`
- `/ll:refine-issue` - 2026-03-16T20:27:40 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6197d55e-7699-4fd1-8daf-6cfcd67f79f2.jsonl`
- `/ll:capture-issue` - 2026-03-16T20:08:11Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fffc83c9-009a-4696-8010-040737bf7247.jsonl`
