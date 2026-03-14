---
discovered_date: 2026-03-14
discovered_by: analyze-loop
source_loop: issue-refinement
source_state: evaluate
formatted: true
confidence_score: 93
outcome_confidence: 79
---

# BUG-743: format-issue --auto never sets `formatted` flag, causing infinite loop in issue-refinement

## Summary

The `issue-refinement` loop exhausted all 200 iterations without completing because `/ll:format-issue FEAT-638 --auto` consistently reports success ("No changes needed, fully v2.0 compliant") but never writes the `formatted: true` field into the issue's frontmatter. On every cycle through `evaluate`, `ll-issues refine-status --json` checks `issue.get('formatted', False)` and finds `False`, emitting `NEEDS_FORMAT FEAT-638` and routing back to `format_issues`. The loop processed FEAT-638 8 times, committed twice, and never advanced past this check.

## Current Behavior

`/ll:format-issue <id> --auto` runs successfully (exit 0) and may report "No changes needed, issue is fully v2.0 compliant" or apply structural changes — but in either case, it never writes `formatted: true` into the issue file's YAML frontmatter. The `issue-refinement` loop's `evaluate` state runs `ll-issues refine-status --json`, which checks `issue.get('formatted', False)` and finds `False` because the field is absent. This causes `NEEDS_FORMAT <id>` to be emitted on every iteration, routing back to `format_issues` indefinitely until `max_iterations` (200) is reached.

## Loop Context

- **Loop**: `issue-refinement`
- **State**: `evaluate`
- **Signal type**: action_failure
- **Occurrences**: 9 (9/9 — 100% failure rate)
- **Last observed**: `2026-03-14T10:25:58+00:00`

## History Excerpt

Events leading to this signal:

```json
[
  {"event": "state_enter", "ts": "2026-03-14T10:23:21.520054+00:00", "state": "evaluate", "iteration": 193},
  {"event": "action_start", "ts": "2026-03-14T10:23:21.520499+00:00", "action": "ll-issues refine-status --json | python3 -c \"...\"", "is_prompt": false},
  {"event": "action_complete", "ts": "2026-03-14T10:23:21.629344+00:00", "exit_code": 1, "duration_ms": 109, "output_preview": "NEEDS_FORMAT FEAT-638", "is_prompt": false},
  {"event": "evaluate", "ts": "2026-03-14T10:23:21.629486+00:00", "type": "exit_code", "verdict": "failure", "exit_code": 1},
  {"event": "route", "ts": "2026-03-14T10:23:21.629563+00:00", "from": "evaluate", "to": "parse_id"},
  {"event": "state_enter", "ts": "2026-03-14T10:25:58.499113+00:00", "state": "evaluate", "iteration": 198},
  {"event": "action_complete", "ts": "2026-03-14T10:25:58.597454+00:00", "exit_code": 1, "duration_ms": 98, "output_preview": "NEEDS_FORMAT FEAT-638", "is_prompt": false},
  {"event": "loop_complete", "ts": "2026-03-14T10:25:58.608765+00:00", "final_state": "format_issues", "iterations": 200, "terminated_by": "max_iterations"}
]
```

Meanwhile, the `format_issues` state reported success each time:
- Iteration 156: `"verify-issues result: VALID"`
- Iteration 161: `"0 structural gaps, 0 missing fields"`
- Iteration 187: `"No changes needed. Issue is fully v2.0 compliant"`

## Expected Behavior

After `/ll:format-issue FEAT-638 --auto` runs successfully, the `formatted` field in FEAT-638's frontmatter should be set to `true` (or equivalent), so that `ll-issues refine-status --json` no longer reports `NEEDS_FORMAT` for that issue.

## Steps to Reproduce

1. Have an active issue being processed by the `issue-refinement` loop (or run manually)
2. Run `/ll:format-issue <id> --auto` on any issue (compliant or not)
3. Observe the skill completes with exit 0 (reports success or "no changes needed")
4. Inspect the issue's YAML frontmatter — `formatted` field is absent
5. Run `ll-issues refine-status --json` — output includes `NEEDS_FORMAT <id>` (exit 1)
6. In the loop context: `evaluate` routes back to `format_issues`, repeating indefinitely

## Root Cause

- **File**: `skills/format-issue/SKILL.md` (format-issue skill definition, Step 5 "Update Issue File")
- **Anchor**: Auto-mode finalization logic in Step 5 / Step 6 "Finalize"
- **Cause**: The skill's auto-mode completion path does not include a step to write `formatted: true` into the issue's YAML frontmatter. The skill considers its job complete after structural gap-filling and section inference, but the `issue-refinement` loop's evaluator depends on a separate `formatted` frontmatter field (checked by `ll-issues refine-status`) that is never set. The issue occurs regardless of whether changes were made or the issue was already compliant.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

The proposed mechanism above is **incorrect about the check mechanism**: `is_formatted()` (`scripts/little_loops/issue_parser.py:44-95`) does **not** read a `formatted:` YAML frontmatter key. The actual check uses two heuristics:

1. **Session log check** (`issue_parser.py:68-70`): returns `True` if `` `/ll:format-issue` `` (backtick-quoted) appears in the `## Session Log` section, matched by `_COMMAND_RE = re.compile(r"\`(/[\w:-]+)\`")` in `session_log.py:16`
2. **Structural check** (`issue_parser.py:73-95`): returns `True` if all required template sections are present as `##` headings

The `refine-status` subcommand (`cli/issues/refine_status.py:219`) calls `is_formatted(issue.path)` directly — it does not read a `formatted:` frontmatter key from anywhere.

The root bug is that `format-issue` SKILL.md Step 5 (`skills/format-issue/SKILL.md:291-309`) only gives the LLM a **prose instruction** to append a session log entry. In `--auto` mode, the LLM may not produce output exactly matching `_COMMAND_RE`, or may skip the write entirely when reporting "no changes needed." A programmatic write via `append_session_log_entry()` (`session_log.py:85-131`) would guarantee the entry is present and correctly formatted in all paths.

## Proposed Solution

Fix the `format-issue` skill: replace the prose session log instruction in Step 5 with a programmatic `python3 -c` one-liner that calls `append_session_log_entry('/ll:format-issue')` from `session_log.py`. This guarantees the session log entry is always written with the exact format that `_COMMAND_RE` matches — in both the "changes made" and "no changes needed" code paths.

A new `ll-issues append-session-log` CLI subcommand is **not** needed; a `python3 -c` inline call is simpler and avoids scope creep. Changing `refine-status` logic is also not needed — `is_formatted()` correctly reads the session log; the skill just needs to write it reliably.

## Implementation Steps

1. In `skills/format-issue/SKILL.md:291-309` (Step 5 "Update Issue File and Append Session Log"): replace the prose-only session log instruction with a **programmatic** `python3 -c` step invoking `append_session_log_entry('/ll:format-issue')` from `scripts/little_loops/session_log.py:85-131`. Signature: `append_session_log_entry(issue_path: Path, command: str, session_jsonl: Path | None = None) -> bool` — pass the issue path and `'/ll:format-issue'`; `session_jsonl` can be omitted (auto-detected).
2. The programmatic write must fire in **both** auto-mode code paths — do not gate it on whether changes were made:
   - "Changes made" path: after `Edit` tool writes structural changes
   - "No changes needed" path: even when the issue is already compliant, append the entry unconditionally
3. Add regression test in `scripts/tests/test_refine_status.py` in the `TestRefineStatusFormatColumn` class at line 874: construct a test issue with `_make_issue()` (line 19-46), call `append_session_log_entry(path, '/ll:format-issue', mock_jsonl)`, then assert `is_formatted(path)` returns `True`

## Integration Map

### Files to Modify
- `skills/format-issue/SKILL.md:291-309` — Step 5 "Update Issue File and Append Session Log": replace prose instruction with a programmatic `append_session_log_entry()` call so the session log is written in all code paths (changes made AND no-changes-needed)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/issue_parser.py:44-95` — `is_formatted()`: checks session log for `` `/ll:format-issue` `` via `_COMMAND_RE`, OR checks all required sections present; does NOT read frontmatter
- `scripts/little_loops/session_log.py:85-131` — `append_session_log_entry()`: utility to programmatically write a correctly-formatted session log entry; this is the function to call
- `scripts/little_loops/session_log.py:20` — `_COMMAND_RE = re.compile(r"\`(/[\w:-]+)\`")`: the regex the session log entry must match
- `scripts/little_loops/cli/issues/refine_status.py:219` — calls `is_formatted(issue.path)` directly; reads no frontmatter
- `loops/issue-refinement.yaml:13-45` — `evaluate` state: pipes `ll-issues refine-status --json` into Python that checks `issue.get('formatted', False)` and exits 1 with `NEEDS_FORMAT` if False, routing to `parse_id` → `route_format` → `format_issues`
- `loops/issue-refinement.yaml:70-76` — `format_issues` state: `action_type: prompt` instructing LLM to run `/ll:format-issue ${captured.issue_id.output} --auto`

### Similar Patterns
- `skills/confidence-check/SKILL.md:362-394` — only existing skill that writes a frontmatter field (uses `Edit` tool to replace frontmatter block); not applicable here since we need session log, but shows the Edit-tool pattern

### Tests
- `scripts/tests/test_refine_status.py:874` — `TestRefineStatusFormatColumn`: existing tests for `is_formatted()` via `refine-status`; add a test case asserting that an issue with a session log entry written by `append_session_log_entry()` is reported as formatted
- `scripts/tests/test_refine_status.py:19-46` — `_make_issue()` helper: established pattern for constructing test issue files with frontmatter

### Documentation
- N/A

### Configuration
- N/A

## Acceptance Criteria

- [x] `/ll:format-issue <id> --auto` appends a `` `/ll:format-issue` `` session log entry to the issue file on successful completion — in both the "changes made" and "no changes needed" paths
- [x] `ll-issues refine-status --json` reports `"formatted": true` for the issue after the skill runs
- [x] The `issue-refinement` loop can advance past `evaluate` for a fully formatted issue
- [x] A regression test in `TestRefineStatusFormatColumn` verifies that `is_formatted()` returns `True` after `append_session_log_entry()` writes the entry

## Impact

- **Priority**: P2 — blocks `issue-refinement` loop from completing; causes 200-iteration exhaustion on every run with any issue
- **Effort**: Small — add one `python3 -c` programmatic step to `SKILL.md:291-309`; `append_session_log_entry()` already exists and is ready to call
- **Risk**: Low — writing a single frontmatter field is non-destructive; no breaking API changes
- **Breaking Change**: No

## Labels

`bug`, `loops`, `format-issue`, `captured`

## Resolution

**Fixed** in `skills/format-issue/SKILL.md` Step 5: replaced the prose session log append instruction with a mandatory `python3 -c` programmatic step that calls `append_session_log_entry(Path('ISSUE_FILE_PATH'), '/ll:format-issue')`. This guarantees the session log entry is written in all auto-mode code paths (both "changes made" and "no changes needed"), so `is_formatted()` returns `True` on subsequent `ll-issues refine-status` calls.

Regression test added: `TestRefineStatusFormatColumn::test_fmt_checkmark_after_append_session_log_entry` in `scripts/tests/test_refine_status.py`.

## Session Log
- `/ll:ready-issue` - 2026-03-14T00:00:00+00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/86422cd6-ac6a-4b1c-b13b-fae2af2adb05.jsonl`
- `/ll:confidence-check` - 2026-03-14T20:03:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f16e4a20-5873-4d7d-9a4a-82d5a5d37c9a.jsonl`
- `/ll:ready-issue` - 2026-03-14T00:00:00+00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f16e4a20-5873-4d7d-9a4a-82d5a5d37c9a.jsonl`
- `/ll:format-issue` - 2026-03-14T00:00:00+00:00 - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0663da45-6636-4175-96f3-89f820bfc0cb.jsonl`
- `/ll:refine-issue` - 2026-03-14T00:00:00+00:00 - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fffc83c9-009a-4696-8010-040737bf7247.jsonl`
- `/ll:manage-issue` - 2026-03-14T00:00:00+00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/current.jsonl`

## Status

**Completed** | Created: 2026-03-14 | Priority: P2
