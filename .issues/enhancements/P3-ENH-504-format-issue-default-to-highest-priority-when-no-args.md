---
discovered_date: 2026-02-24
discovered_by: capture-issue
---

# ENH-504: Format Highest-Priority Issue When No Args Provided

## Summary

When `/ll:format-issue` is run without any arguments, it should automatically select and format the highest-priority active issue, matching the pattern used by `/ll:manage-issue` when invoked without an argument.

## Motivation

Currently, running `/ll:format-issue` without arguments has undefined or unproductive behavior. The `/ll:manage-issue` skill already implements a sensible default — selecting the highest-priority issue from the active backlog — and `/ll:format-issue` should follow the same convention for consistency and usability. This reduces friction when running format passes over the backlog without needing to specify issue IDs manually.

## Acceptance Criteria

- [ ] `/ll:format-issue` with no arguments selects and formats the highest-priority active issue (P0 first, then P1, P2, etc.)
- [ ] Tie-breaking within same priority follows the same logic as `/ll:manage-issue` (e.g., by issue number or filename sort)
- [ ] Skill outputs which issue was selected so the user knows what is being formatted
- [ ] Behavior is documented in the skill's Arguments section

## Implementation Steps

1. Locate the format-issue skill definition (`skills/format-issue/SKILL.md` or similar)
2. Review how `/ll:manage-issue` selects the highest-priority issue when no argument is given
3. Add equivalent default-selection logic to the format-issue skill's argument parsing phase
4. Update the skill's "Arguments" documentation to describe the no-arg behavior
5. Verify the selected issue is printed to the user before formatting begins

## Related

- `/ll:manage-issue` — reference implementation for highest-priority selection logic
- `/ll:format-issue` — the skill being enhanced

## Session Log
- `/ll:capture-issue` - 2026-02-24T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/bc790b97-8457-4261-96c9-b25c3abc9efc.jsonl`

---
## Status

**State**: Open
