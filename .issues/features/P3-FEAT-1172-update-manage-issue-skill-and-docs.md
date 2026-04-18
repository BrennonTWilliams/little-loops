---
id: FEAT-1172
type: FEAT
priority: P3
status: open
discovered_date: 2026-04-18
discovered_by: issue-size-review
parent: FEAT-1162
size: Small
---

# FEAT-1172: Update `manage-issue` Skill and Documentation for `completed_at`

## Summary

Add an Edit-tool step for `completed_at` injection to `skills/manage-issue/SKILL.md`, add a `completed_at` row to the frontmatter fields table in `docs/reference/ISSUE_TEMPLATE.md`, and document `update_frontmatter` in `docs/reference/API.md`.

## Parent Issue

Decomposed from FEAT-1162: Add `completed_at` Timestamp in All Completion Paths

## Motivation

The interactive completion path (manage-issue skill) runs `git mv` directly via LLM instruction. Without an explicit step in the skill instructions, the LLM will not inject `completed_at`. The documentation also needs updating so `completed_at` is a recognized, documented field.

## Implementation Steps

1. **`skills/manage-issue/SKILL.md` (near lines 408-418)**:
   - Before the `git mv` command that moves an issue to `completed/`, add an explicit Edit-tool step to inject `completed_at` into frontmatter
   - Follow the `captured_at` precedent in `skills/capture-issue/SKILL.md:235`
   - Use shell: `date -u +"%Y-%m-%dT%H:%M:%SZ"` for the timestamp value
   - Instruction should read: "Before running git mv, use the Edit tool to add `completed_at: <ISO timestamp>` to the issue frontmatter"

2. **`docs/reference/ISSUE_TEMPLATE.md:875`**:
   - Add `completed_at` row to the Frontmatter Fields table after the `captured_at` row
   - Pattern: `| \`completed_at\` | ISO 8601 UTC datetime | — | Set when issue is moved to \`completed/\` |`
   - Update the YAML example block at lines 893-900 to include `completed_at`

3. **`docs/reference/API.md:4700-4732`**:
   - Add `update_frontmatter` entry to the `little_loops.frontmatter` module docs section
   - Document signature, parameters, return value, and behavior

## Files to Modify

- `skills/manage-issue/SKILL.md` — add completed_at injection step before git mv
- `docs/reference/ISSUE_TEMPLATE.md` — add completed_at field to frontmatter table and YAML example
- `docs/reference/API.md` — add update_frontmatter entry to frontmatter module docs

## Acceptance Criteria

- [ ] `manage-issue` skill instructs LLM to inject `completed_at` before `git mv`
- [ ] `ISSUE_TEMPLATE.md` frontmatter table includes `completed_at` row
- [ ] `ISSUE_TEMPLATE.md` YAML example includes `completed_at`
- [ ] `API.md` documents `update_frontmatter` function

## Session Log
- `/ll:issue-size-review` - 2026-04-18T21:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f4fec2da-840f-48eb-a5e3-fc86007899b8.jsonl`
