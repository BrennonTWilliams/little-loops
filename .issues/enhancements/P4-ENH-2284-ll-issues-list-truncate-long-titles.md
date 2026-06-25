---
id: ENH-2284
type: ENH
priority: P4
status: done
title: ll-issues list should truncate long titles to fit one line
captured_at: '2026-06-25T01:44:33Z'
completed_at: '2026-06-25T02:18:17Z'
discovered_date: '2026-06-25'
discovered_by: capture-issue
confidence_score: 96
outcome_confidence: 86
score_complexity: 22
score_test_coverage: 17
score_ambiguity: 22
score_change_surface: 25
---

# ENH-2284: ll-issues list should truncate long titles to fit one line

## Summary

`ll-issues list` prints each issue as a single formatted row (`priority  ID  title`), but long titles wrap onto a second line, breaking the tabular alignment and making the output hard to scan.

## Current Behavior

`ll-issues list` does not truncate issue titles. When a title exceeds the remaining terminal width it soft-wraps to a second physical line, breaking the tabular layout and making it hard to scan many issues at once.

## Expected Behavior

`ll-issues list` truncates titles that exceed the available width to `max_title - 1` characters and appends `…`, keeping each row to a single physical line. A `--no-truncate` / `--full-titles` flag opts out of truncation. Piped output and `--json` output always emit full, untruncated titles.

## Motivation

The list output is designed to be read quickly as a table — priority, ID, and title in a consistent column layout. When a title exceeds the remaining terminal width, it soft-wraps, making the row span two physical lines. This disrupts the visual cadence and causes readers to lose their place when scanning many issues.

Example of current broken output (terminal ~80 cols):
```
  P2  BUG-2281  Option J guillotine path lacks the already-done guard, causing an unbounded
```

## Scope Boundaries

- **In scope**: Truncating titles in `ll-issues list` interactive terminal display
- **Out of scope**: `--json` output (always emits full title), `--flat` mode (scripting-safe, unaffected), piped output (uses fallback width; truncation skips when `max_title < 20`)

## Implementation Steps

1. In `scripts/little_loops/cli/issues/list_cmd.py`, at the point where the row string is assembled (lines 214 and 239), detect the available terminal width via `shutil.get_terminal_size(fallback=(120, 24)).columns`.
2. Calculate the prefix width: `len("  P2  BUG-2281  ")` (i.e., 2 + priority_len + 2 + id_len + 2). Include the `status_tag` width when present.
3. Compute `max_title = terminal_width - prefix_width`. If `max_title < 20`, skip truncation (too narrow to be useful).
4. Truncate `issue.title` to `max_title - 1` chars and append `…` when the title exceeds the limit:
   ```python
   title = issue.title
   if max_title > 20 and len(title) > max_title:
       title = title[:max_title - 1] + "…"
   ```
5. The same logic applies to both the `group_by=epic` path (line 214) and the default `group_by=type` path (line 239). Extract a helper or apply at the shared row-format level.
6. Add a `--no-truncate` / `--full-titles` flag to `ll-issues list` so automation scripts can opt out. The `--flat` mode already prints full titles for scripting and should remain unaffected.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- Both row-assembly f-strings are structurally identical and already confirmed at **lines 214 and 239** in `list_cmd.py`; the prefix visible width is `2 + len(issue.priority) + 2 + len(issue.issue_id) + 2` — compute on plain strings, not on `colored_priority` / `colored_id` (ANSI codes inflate `len()`)
- `terminal_width()` and `strip_ansi()` already exist in `scripts/little_loops/cli/output.py` (lines 27 and 45); add them to the import line that already imports `colorize`, `PRIORITY_COLOR`, `TYPE_COLOR` from that module
- The `--no-truncate` flag registration belongs in `scripts/little_loops/cli/issues/__init__.py` around line 174, in the `ls` subparser block alongside `--flat` and `--json`; the `cmd_list` function reads flags via `getattr(args, "flat", False)` — follow the same `getattr(args, "no_truncate", False)` pattern
- No existing truncation tests in `TestIssuesCLIList` (`test_issues_cli.py:181`); patch `terminal_width` to a fixed value (e.g. 40 cols) to drive truncation in unit tests without requiring a real TTY
- A reusable `_truncate(text, max_len)` helper already exists at `scripts/little_loops/cli/loop/info.py:319` — same signature and `…` behavior as the issue proposes; consider extracting to `output.py` or importing from `info.py` rather than duplicating
- Best test references: `test_ll_loop_commands.py:1078` (`test_truncate_unit` — unit tests for `_truncate`) and `test_ll_loop_commands.py:1136` (`test_description_truncation_at_narrow_width` — integration test with `patch("...terminal_width", return_value=60)`)
- **API convention note**: the codebase uses `--full` (not `--no-truncate`) to suppress truncation — see `loop/__init__.py:464`; consider aligning with this convention

## API/Interface

```
ll-issues list [--no-truncate | --full-titles]
```

`--no-truncate` / `--full-titles`: opt out of display truncation; emit full issue titles. The `--flat` and `--json` modes are unaffected (already emit full titles).

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/issues/list_cmd.py` — title assembly at the `group_by=epic` path (~line 214) and default `group_by=type` path (~line 239); extract shared truncation helper

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/issues/__init__.py:41` — imports `cmd_list`; also owns the `ls` subparser where the `--no-truncate` / `--full-titles` flag must be registered (around line 174, alongside `--flat` and `--json`)

### Similar Patterns
- `scripts/little_loops/cli/output.py:27` — `terminal_width(default=80)` — wraps `shutil.get_terminal_size`; import and reuse this instead of calling `shutil` directly in `list_cmd.py`
- `scripts/little_loops/cli/output.py:45` — `strip_ansi(text)` — strips ANSI escape sequences; use this to compute the true visible prefix length (since `colored_priority` and `colored_id` contain ANSI codes that inflate `len()`)
- `scripts/little_loops/cli/output.py:238` — `_cell(text, width)` inside `table()` — uses `text[:width - 1] + "…"` — the exact same truncation pattern the issue proposes; extract or duplicate

### Tests
- `scripts/tests/test_issues_cli.py:181` — `TestIssuesCLIList` class — all existing list command tests live here; no truncation tests exist yet
- Follow the mock/patch style of `test_list_grouped_output_line_format` (line 229) for new truncation tests; patch `terminal_width` to a fixed column count
- Follow `test_list_flat_backward_compatibility` (line 250) for `--no-truncate` flag test
- Follow `test_list_json_no_color_codes` (line 474) to verify `--json` emits full untruncated titles

### Documentation
- `docs/reference/API.md` — update `ll-issues list` args section if present

### Configuration
- N/A

## Notes

- `shutil.get_terminal_size` returns `fallback` when stdout is not a TTY (piped), so piped output gets the same 120-col default it uses today — no regressions for scripting workflows.
- ANSI color codes add invisible bytes; the truncation must operate on the *plain* title string before colorization, not on the final colored string.
- `--json` output must always emit the full, untruncated title; this enhancement is display-only.

## Impact

- **Priority**: P4 — cosmetic UX improvement; long titles are an annoyance but not blocking
- **Effort**: Small — localized change to `list_cmd.py`; add a shared truncation helper and one flag
- **Risk**: Low — display-only change; `--no-truncate` provides an opt-out; piped/`--json` paths unchanged
- **Breaking Change**: No

## Labels

`ux`, `cli`, `display`

## Status

**Open** | Created: 2026-06-25 | Priority: P4

## Session Log
- `/ll:ready-issue` - 2026-06-25T02:12:00 - `4efbe94f-4a2f-41d9-95af-26121ad35263.jsonl`
- `/ll:refine-issue` - 2026-06-25T02:01:50 - `0d5cb4ea-213c-4f08-8a5c-e7553bc2a4f7.jsonl`
- `/ll:confidence-check` - 2026-06-25T02:00:00Z - `fffe04a2-92e2-4f19-bafe-0d8c500f9b47.jsonl`
- `/ll:format-issue` - 2026-06-25T01:48:28 - `a4646b6c-126e-4f42-b27d-67bef4444089.jsonl`
- `/ll:capture-issue` - 2026-06-25T01:44:33Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f41b0d4e-5528-48c7-8e96-48024115202b.jsonl`
