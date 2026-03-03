---
discovered_date: 2026-03-03
discovered_by: capture-issue
---

# ENH-524: Add Session Log Steps to Issue-Modifying Commands and Skills

## Summary

Five commands and skills make meaningful changes to issue files (content edits, frontmatter updates, file moves to `completed/`) but do not append a Session Log entry. This leaves gaps in the audit trail for issues processed by `ready-issue`, `verify-issues`, `confidence-check`, `tradeoff-review-issues`, and `issue-size-review`.

## Current Behavior

The following commands/skills write to issue files with no Session Log step:

| Command/Skill | Action on Issue Files |
|---|---|
| `ready-issue` | Auto-corrects content; closes to `completed/` |
| `verify-issues` | Updates verification notes; closes to `completed/` |
| `confidence-check` (skill) | Writes `confidence_score` + `outcome_confidence` to YAML frontmatter |
| `tradeoff-review-issues` | Appends review notes; closes to `completed/` |
| `issue-size-review` (skill) | Creates child issues; closes parent to `completed/` |

These contrast with `format-issue`, `manage-issue`, `capture-issue`, `scan-codebase`, and `refine-issue`, which all append Session Log entries after modifying issues.

## Expected Behavior

Each of the five commands/skills above should append a Session Log entry immediately after modifying the issue file, following the same pattern used by the commands that already implement it:

```markdown
## Session Log
- `/ll:<command>` - [ISO timestamp] - `[path to current session JSONL]`
```

The entry should be added before the `---` / `## Status` footer. If `## Session Log` already exists, the new entry is appended below the header.

## Acceptance Criteria

- [ ] `ready-issue` appends a Session Log entry after auto-correcting issue content
- [ ] `ready-issue` appends a Session Log entry after closing an issue to `completed/`
- [ ] `verify-issues` appends a Session Log entry after updating verification notes
- [ ] `confidence-check` appends a Session Log entry after writing `confidence_score` and `outcome_confidence` to frontmatter
- [ ] `tradeoff-review-issues` appends a Session Log entry after appending review notes
- [ ] `tradeoff-review-issues` appends a Session Log entry after closing an issue to `completed/`
- [ ] `issue-size-review` appends a Session Log entry for each child issue created
- [ ] `issue-size-review` appends a Session Log entry when closing the parent issue to `completed/`
- [ ] All entries follow the standard format: `- /ll:<command> - [ISO timestamp] - [session JSONL path]`

## Motivation

Without Session Log entries, there is no record of which session last touched an issue or what command caused a change. This makes it difficult to trace why an issue was closed, when a confidence score was set, or which session flagged a size decomposition. Consistent Session Log coverage across all issue-writing commands enables complete auditability.

## Success Metrics

- Session Log coverage: 5 of 10 issue-modifying commands → 10 of 10 (100%)
- Zero issue modifications by the 5 affected commands leave the Session Log empty

## Affected Files

- `commands/ready-issue.md` — add Session Log step after autocorrect/close actions
- `commands/verify-issues.md` — add Session Log step after updating verification notes
- `skills/confidence-check/SKILL.md` — add Session Log step after frontmatter write
- `commands/tradeoff-review-issues.md` — add Session Log step after appending review/closing
- `skills/issue-size-review/SKILL.md` — add Session Log step for each created child issue and the closed parent

## Scope Boundaries

- **In scope**: Adding Session Log steps to the 5 commands/skills listed in Affected Files
- **Out of scope**: Changing the Session Log format; modifying `scripts/little_loops/session_log.py`; adding Session Log to commands that don't write issue files

## API/Interface

N/A - No public API changes. The Session Log step writes markdown to existing issue files using the same format already implemented in `commands/refine-issue.md` and `skills/format-issue/SKILL.md`.

## Implementation Steps

1. For each affected file, locate the step that writes/edits the issue file
2. Add a new step immediately after: "Append Session Log Entry"
3. Use the standard Session Log format (same as in `commands/refine-issue.md:384` or `skills/format-issue/SKILL.md:264`)
4. Ensure the step covers all branch paths (e.g., `ready-issue` has both autocorrect and close paths — both need a log entry)
5. For `issue-size-review`, log entries on both the new child issue files and the parent being closed

## Related Key Documentation

| Document | Relevance |
|---|---|
| `commands/refine-issue.md:384` | Reference implementation of Session Log step |
| `skills/format-issue/SKILL.md:264` | Reference implementation in skill context |
| `skills/manage-issue/templates.md:331` | Canonical Session Log entry format template |
| `scripts/little_loops/session_log.py` | Python module for session log operations |

## Session Log
- `/ll:capture-issue` - 2026-03-03T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f3f89019-8d96-425f-80aa-cd975bd7521c.jsonl`
- `/ll:format-issue` - 2026-03-03T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d89e72fb-8a73-4022-8536-d2864de87a77.jsonl`

---
