---
id: ENH-2288
type: ENH
priority: P3
status: open
parent: ENH-2272
relates_to:
- ENH-2286
captured_at: '2026-06-25T00:00:00Z'
discovered_date: 2026-06-25
discovered_by: issue-size-review
---

# ENH-2288: Callsite rewrites (6 files) + docs updates

## Summary

Replace the prose-based `scripts/little_loops/templates/{type}-sections.json` path
references in 6 skill/command files with `ll-issues sections {type}` CLI calls.
Update all affected documentation. Depends on ENH-2286 (`ll-issues sections` must
exist before callsite rewrites are useful in production).

## Parent Issue

Decomposed from ENH-2272: ll-issues sections accessor + project-local template deploy

## Proposed Solution

Replace each verbatim phrase (confirmed in ENH-2272 pass 5) with the CLI invocation.
For skills that just need the file on disk, use `ll-issues sections {type} --path`
then Read; for skills that need the JSON content, use `ll-issues sections {type}`.

### Verbatim replacement targets

| File | Line | Current phrase | Replacement |
|------|------|----------------|-------------|
| `skills/format-issue/SKILL.md` | 196 | `scripts/little_loops/templates/{type}-sections.json` v2.0 (relative to the little-loops plugin directory) | `ll-issues sections {type}` |
| `skills/format-issue/SKILL.md` | 221 | `the per-type template \`scripts/little_loops/templates/{type}-sections.json\` for the issue's type` | `the per-type template from \`ll-issues sections {type}\`` |
| `skills/format-issue/templates.md` | 7 | `scripts/little_loops/templates/{type}-sections.json` (relative to the little-loops plugin directory) | `ll-issues sections {type}` |
| `skills/format-issue/templates.md` | 52 | `the per-type template \`scripts/little_loops/templates/{type}-sections.json\` v2.0` | `the per-type template from \`ll-issues sections {type}\`` |
| `skills/format-issue/templates.md` | 54 | `Read the per-type template file \`scripts/little_loops/templates/{type}-sections.json\`` | `Run \`ll-issues sections {type}\` to get the per-type template` |
| `skills/capture-issue/SKILL.md` | 276 | `Read the per-type template \`scripts/little_loops/templates/{type}-sections.json\`` | `Run \`ll-issues sections {type}\` to get the per-type template` |
| `skills/scope-epic/SKILL.md` | 296 | `Read \`scripts/little_loops/templates/epic-sections.json\` to get section definitions.` | `Run \`ll-issues sections epic\` to get section definitions.` |
| `skills/scope-epic/SKILL.md` | 358 | `Read \`scripts/little_loops/templates/{type}-sections.json\` for the child's type.` | `Run \`ll-issues sections {type}\` for the child's type.` |
| `commands/ready-issue.md` | 139 | `Read the per-type template \`scripts/little_loops/templates/{type}-sections.json\` v2.0 (relative to the little-loops plugin directory)` | `Run \`ll-issues sections {type}\` to get the per-type template` |
| `commands/scan-codebase.md` | 241 | `using the section structure from per-type template files (relative to the little-loops plugin directory)` | `using the section structure from \`ll-issues sections {type}\`` |
| `commands/scan-codebase.md` | 243 | `Read the per-type template \`scripts/little_loops/templates/{type}-sections.json\`` | `Run \`ll-issues sections {type}\` to get the per-type template` |

Post-implementation verification: Run `grep -r "plugin directory\|scripts/little_loops/templates" skills/ commands/` — must return no matches.

### Documentation updates

- `docs/reference/CLI.md` — document `ll-issues sections <type>` and `--path` flag
- `docs/reference/API.md` — document `resolve_templates_dir(config)` from `issue_template.py`
- `docs/reference/CONFIGURATION.md` — add `deploy_templates` row to `### issues` config table
  (alongside `templates_dir`)
- `.claude/CLAUDE.md` — add `sections` to the parenthetical `ll-issues` subcommand list (line 233)

## Files to Modify

- `skills/format-issue/SKILL.md` — 2 replacements
- `skills/format-issue/templates.md` — 3 replacements
- `skills/capture-issue/SKILL.md` — 1 replacement
- `skills/scope-epic/SKILL.md` — 2 replacements
- `commands/ready-issue.md` — 1 replacement
- `commands/scan-codebase.md` — 2 replacements
- `docs/reference/CLI.md` — add sections subcommand documentation
- `docs/reference/API.md` — document `resolve_templates_dir()`
- `docs/reference/CONFIGURATION.md` — add `deploy_templates` config row
- `.claude/CLAUDE.md` — add `sections` to `ll-issues` subcommand list

## Acceptance Criteria

- `grep -r "plugin directory\|scripts/little_loops/templates" skills/ commands/` returns no matches
- `ll-verify-skills` passes (no skill over 500 lines)
- `ll-verify-skill-budget` passes (description token budget not exceeded)
- `docs/reference/CLI.md` documents the new subcommand
- `.claude/CLAUDE.md` `ll-issues` subcommand list includes `sections`

## Implementation Steps

1. Apply the 11 verbatim replacements across 6 skill/command files using the Edit tool
2. Run `grep -r "plugin directory\|scripts/little_loops/templates" skills/ commands/` to confirm zero matches
3. Update `docs/reference/CLI.md` with `sections` subcommand documentation
4. Update `docs/reference/API.md` with `resolve_templates_dir()` docs
5. Update `docs/reference/CONFIGURATION.md` with `deploy_templates` config table row
6. Add `sections` to the `ll-issues` subcommand list in `.claude/CLAUDE.md` (line ~233)
7. Run `ll-verify-skills && ll-verify-skill-budget`
8. Run `python -m pytest scripts/tests/` to confirm no regressions

## Dependencies

- ENH-2286 must ship first (the `ll-issues sections` CLI must exist)

## Session Log
- `/ll:issue-size-review` - 2026-06-25T00:00:00Z - `fffe04a2-92e2-4f19-bafe-0d8c500f9b47.jsonl`
