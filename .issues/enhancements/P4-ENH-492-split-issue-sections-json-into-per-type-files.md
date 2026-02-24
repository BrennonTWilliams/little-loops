---
discovered_date: 2026-02-24
discovered_by: capture-issue
---

# ENH-492: Split issue-sections.json into per-type files

## Summary

Split the single unified `templates/issue-sections.json` into three per-type template files (`bug-sections.json`, `feat-sections.json`, `enh-sections.json`) while preserving the same internal JSON structure. Each file would contain only the sections relevant to its type (common + type-specific), making the templates easier to read and maintain by hand.

## Current Behavior

All three issue types (BUG, FEAT, ENH) share a single `templates/issue-sections.json` file that embeds type-specific sections under `type_sections.BUG`, `type_sections.FEAT`, and `type_sections.ENH`. The file is 16KB and growing as new sections are added.

## Expected Behavior

Three smaller, focused template files exist:
- `templates/bug-sections.json` — common sections + BUG-specific sections
- `templates/feat-sections.json` — common sections + FEAT-specific sections
- `templates/enh-sections.json` — common sections + ENH-specific sections

Skills (`format-issue`, `capture-issue`, `manage-issue`, `ready-issue`) load the file corresponding to the issue type being processed.

## Motivation

The single-file approach works well for machine processing but makes it hard to read or update type-specific sections in isolation. As the template grows (more sections, more quality guidance, more inference rules), a single large JSON file becomes a maintenance burden. Per-type files reduce cognitive load when editing templates and make diffs easier to review.

This is an architectural quality-of-life improvement — no new functionality, just better organization.

## Proposed Solution

TBD - requires investigation

Key decisions to make:
- How to handle sections shared across types (copy into each file vs. extract to a `common-sections.json` that the per-type files reference or are merged with at load time)
- Whether all consumer skills need updating or if a thin loader shim (`load_sections(issue_type)`) can centralize the file-selection logic
- Migration strategy for any projects that reference `issue-sections.json` by name in config

## Implementation Steps

1. Audit all consumers of `templates/issue-sections.json` (skills, commands, scripts) to understand the load interface
2. Decide on common-sections strategy (embedded copies vs. shared file)
3. Generate the three per-type files from the existing unified file
4. Update the loader logic in consumer skills to select file by type
5. Remove or deprecate `issue-sections.json` (or leave as a combined compatibility shim)
6. Update docs (`docs/reference/ISSUE_TEMPLATE.md`, `skills/*/templates.md`)

## Integration Map

- `templates/issue-sections.json` → split target
- `skills/format-issue/SKILL.md` + `templates.md` → loads issue-sections.json
- `skills/capture-issue/SKILL.md` + `templates.md` → loads issue-sections.json
- `skills/manage-issue/SKILL.md` + `templates.md` → loads issue-sections.json
- `commands/ready-issue.md` → loads issue-sections.json
- `commands/scan-codebase.md` → may reference template structure
- `docs/reference/ISSUE_TEMPLATE.md` → documents template structure

## Impact

- **Scope**: Templates + 4-5 skill/command files + docs
- **Risk**: Low — purely structural refactor, no behavioral changes if loader shim is correct
- **Benefit**: Easier template maintenance, smaller per-file diffs, clearer type-specific sections

## Labels

`enhancement`, `templates`, `refactor`

## Session Log

- `/ll:capture-issue` - 2026-02-24T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/568ba5fc-d209-4c80-bff7-a8c1237be3b5.jsonl`

---

## Status

`open`
