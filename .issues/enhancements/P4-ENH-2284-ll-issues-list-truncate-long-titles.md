---
id: ENH-2284
type: ENH
priority: P4
status: open
title: ll-issues list should truncate long titles to fit one line
captured_at: "2026-06-25T01:44:33Z"
discovered_date: "2026-06-25"
discovered_by: capture-issue
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

## API/Interface

```
ll-issues list [--no-truncate | --full-titles]
```

`--no-truncate` / `--full-titles`: opt out of display truncation; emit full issue titles. The `--flat` and `--json` modes are unaffected (already emit full titles).

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/issues/list_cmd.py` — title assembly at the `group_by=epic` path (~line 214) and default `group_by=type` path (~line 239); extract shared truncation helper

### Dependent Files (Callers/Importers)
- TBD - use grep to find references: `grep -r "list_cmd" scripts/`

### Similar Patterns
- TBD - check other CLI commands that format tabular output for consistency

### Tests
- TBD - add/update tests in `scripts/tests/` covering truncation, `--no-truncate`, piped output, and `--json`

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
- `/ll:format-issue` - 2026-06-25T01:48:28 - `a4646b6c-126e-4f42-b27d-67bef4444089.jsonl`
- `/ll:capture-issue` - 2026-06-25T01:44:33Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f41b0d4e-5528-48c7-8e96-48024115202b.jsonl`
