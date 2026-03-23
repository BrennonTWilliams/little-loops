---
id: ENH-860
type: ENH
priority: P3
status: open
title: "Update review-loop and create-loop skills to prefer ll- CLI commands"
discovered_date: "2026-03-23"
discovered_by: capture-issue
---

# ENH-860: Update review-loop and create-loop skills to prefer ll- CLI commands

## Summary

The `/ll:review-loop` and `/ll:create-loop` skills should prefer using the project's native `ll-` CLI commands (e.g., `ll-issues`, `ll-sprint`, `ll-loop`) over ad-hoc bash/grep approaches where possible, especially for issue management operations.

## Motivation

The `ll-` CLI tools are purpose-built for this project's data structures and provide consistent, tested behavior. Using them in skills instead of raw bash commands reduces fragility, improves consistency with how users interact with the project, and keeps skill instructions aligned with the documented toolchain described in CLAUDE.md.

Currently, `review-loop` and `create-loop` may instruct the agent to use raw bash/grep for operations like listing issues or inspecting issue state, when commands like `ll-issues list`, `ll-issues next-id`, or `ll-sprint show` already do this reliably.

## Scope

- `skills/review-loop/SKILL.md` — audit for any issue management steps that should use `ll-issues`, `ll-sprint`, or `ll-loop` CLI commands instead of manual file inspection
- `skills/create-loop/SKILL.md` — same audit; also check `reference.md` and `templates.md` for issue-related steps
- Focus specifically on: listing issues, getting next IDs, checking issue status, interacting with sprints or loops

## Implementation Steps

1. Read `skills/review-loop/SKILL.md` and `skills/create-loop/SKILL.md` (and their reference/templates files)
2. Identify any steps that perform manual issue file inspection that `ll-` CLI commands could replace
3. Update instructions to call the appropriate `ll-` CLI command with correct flags
4. Verify the referenced CLI commands exist and support the needed operations (`ll-issues --help`, `ll-loop --help`)
5. Ensure fallback behavior is documented if a CLI command is unavailable

## Acceptance Criteria

- [ ] Both skills explicitly prefer `ll-` CLI commands for issue-related operations
- [ ] No raw `ls .issues/` or manual grep for issue state where a CLI equivalent exists
- [ ] CLI command usage is consistent with documented interface in CLAUDE.md and `docs/reference/API.md`

## Session Log
- `/ll:capture-issue` - 2026-03-23T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/06fdc033-986b-4b59-b280-3505ad02d65c.jsonl`
