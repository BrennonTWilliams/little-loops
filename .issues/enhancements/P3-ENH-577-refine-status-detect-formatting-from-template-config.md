---
discovered_date: 2026-03-04
discovered_by: capture-issue
---

# ENH-577: Detect issue formatting from template config instead of session log

## Summary

The `refine-status` command currently marks an issue as "formatted" only if `/ll:format-issue` appears in its session log. Change this to detect formatting by inspecting the issue file's actual content against the Issue template configuration.

## Current Behavior

`ll-issues refine-status` derives the `format` column value from `issue.session_commands` — specifically, whether `/ll:format-issue` appears in the issue's `## Session Log` section. An issue that is correctly structured per the v2.0 template will show ✗ in the `format` column if the user never explicitly ran `/ll:format-issue` on it (e.g., it was hand-written or captured via a future tool that already emits v2.0 structure).

## Expected Behavior

The `format` column (or a new structural-check signal) reflects whether the issue file actually conforms to the expected template structure as defined by the template configuration — regardless of which command created or modified it.

Detection should use the section definitions from the per-type template files (e.g., `templates/bug-sections.json`, `templates/feat-sections.json`, `templates/enh-sections.json`) or equivalent configuration in `.claude/ll-config.json` to determine required sections, then verify they are present in the issue file's markdown headings.

## Motivation

Session log entries record *process*, not *state*. Coupling a structural quality signal to a specific command run makes the metric fragile and misleading — it punishes correctly-formatted issues that arrived via a different path, and rewards badly-formatted ones that happened to have the command run on them.

## Implementation Steps

1. Locate where `format` column data is populated in `refine_status.py` (currently via `session_commands` set membership check on `/ll:format-issue`).
2. Add a helper `is_formatted(issue_path, config)` in `issue_parser.py` (or `refine_status.py`) that:
   - Loads the appropriate type-template (`templates/{type}-sections.json`) for the issue.
   - Extracts the required section heading names from the template (e.g., `common_sections` keys + `type_sections` keys where the section is non-optional).
   - Parses the issue file's markdown `##` headings.
   - Returns `True` if all required headings are present.
3. Replace the session-log-based format check in `refine_status.py` with a call to `is_formatted(...)`.
4. Update `test_refine_status.py` with fixtures covering: a hand-written v2.0 file (expect ✓), a v1.x file missing required sections (expect ✗), and a file that has the session log entry but missing sections (expect ✗).

## Related Key Documentation

- ENH-561: Add column key section to `ll-issues refine-status` output (separate concern)
- `scripts/little_loops/cli/issues/refine_status.py` — current `/ll:format-issue` session-log check
- `templates/bug-sections.json`, `templates/feat-sections.json`, `templates/enh-sections.json` — template definitions to read from

## Scope Boundaries

- No changes to template JSON files (`templates/bug-sections.json`, etc.) — detection reads from templates, does not modify them
- No new columns added to `ll-issues refine-status` output — only changes how the existing `format` column is populated
- Scoped to `refine-status` subcommand only — no changes to `ll-issues show` or other subcommands
- No UI/display format changes — `✓`/`✗` rendering is unchanged, only the detection logic changes

## Impact

- **Priority**: P3 — Non-critical enhancement; current behavior is confusing but doesn't block workflows
- **Effort**: Small — Changes isolated to ~3 files (`refine_status.py`, `issue_parser.py`, `test_refine_status.py`); reuses existing template-loading infrastructure
- **Risk**: Low — Replaces one session-log check with a structural check; no API or output format changes; well-tested path
- **Breaking Change**: No

## Labels

`enhancement`, `cli`, `issue-management`, `refine-status`

## Status

**Open** | Created: 2026-03-04 | Priority: P3

---

## Session Log
- `/ll:capture-issue` - 2026-03-04T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0c867334-8723-481e-ab0c-6699be487fb7.jsonl`
- `/ll:format-issue` - 2026-03-04T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b7eb1c0c-cf36-4cd9-b49f-3ccc1518217f.jsonl`
