---
discovered_date: 2026-02-24
discovered_by: capture-issue
confidence_score: 73
outcome_confidence: 61
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

**Consumer Audit Complete** — all consumers are skill/command markdown files (Claude reads the JSON directly); there is no Python code that loads `issue-sections.json` (the planned `issue_template.py` from ENH-491 doesn't exist yet).

**Load interface:** Every consumer uses a natural-language instruction: "Read templates/issue-sections.json". There is no import statement or config reference to migrate.

**Key decisions resolved by audit:**

1. **Shared sections strategy**: Since all consumers are AI agents reading files directly, a `common-sections.json` + loader shim approach is unnecessary overhead. The simplest migration is to copy shared sections into each per-type file. Agents can be instructed to load only the type-appropriate file.

2. **Loader shim not needed**: No Python code reads this file, so no Python shim is required. Each skill's markdown instruction is updated from "Read templates/issue-sections.json" to "Read templates/{type}-sections.json where {type} is the issue type (bug/feat/enh)".

3. **Migration strategy**: Update the instruction text in 5 consumer files (no config migration needed):

| Consumer | File | Lines to update |
|---|---|---|
| `capture-issue` | `skills/capture-issue/SKILL.md:231` | Change filename in read instruction |
| `format-issue` (gap check) | `skills/format-issue/SKILL.md:166,191` | Change filename in read instruction |
| `format-issue` (template) | `skills/format-issue/templates.md:7,54` | Change filename in read instruction |
| `scan-codebase` | `commands/scan-codebase.md:243` | Change filename in read instruction |
| `ready-issue` | `commands/ready-issue.md:123` | Change filename in read instruction |

**Python code (sync.py)**: The `_create_local_issue()` hardcoded template (`sync.py:615-670`) is addressed by ENH-491, which plans to add `issue_template.py`. That new module will need to load the per-type file — coordinate with ENH-491.

## Scope Boundaries

- **In scope**: Splitting `issue-sections.json` into per-type files; updating consumer skills to load by type via a loader shim; documenting the migration
- **Out of scope**: Changing the content or structure of section definitions; adding new sections; modifying consumer skill logic beyond the file-selection step

## Implementation Steps

1. Audit all consumers of `templates/issue-sections.json` (skills, commands, scripts) to understand the load interface
2. Decide on common-sections strategy (embedded copies vs. shared file)
3. Generate the three per-type files from the existing unified file
4. Update the loader logic in consumer skills to select file by type
5. Remove or deprecate `issue-sections.json` (or leave as a combined compatibility shim)
6. Update docs (`docs/reference/ISSUE_TEMPLATE.md`, `skills/*/templates.md`)

## Integration Map

### Files to Modify
- `templates/issue-sections.json` — split into per-type files (or leave as compatibility shim)
- `skills/format-issue/SKILL.md` + `templates.md` — update to load per-type file
- `skills/capture-issue/SKILL.md` + `templates.md` — update to load per-type file
- `skills/manage-issue/SKILL.md` + `templates.md` — update to load per-type file
- `commands/ready-issue.md` — update to load per-type file
- `commands/scan-codebase.md` — update if template structure is referenced

### New Files
- `templates/bug-sections.json` — common + BUG-specific sections
- `templates/feat-sections.json` — common + FEAT-specific sections
- `templates/enh-sections.json` — common + ENH-specific sections

### Similar Patterns
- N/A — novel restructure; establish new pattern

### Tests
- N/A — no Python code changes; validate by exercising each skill against each issue type

### Documentation
- `docs/reference/ISSUE_TEMPLATE.md` — update to describe per-type file structure

### Configuration
- N/A

## Impact

- **Priority**: P4 — Architectural quality-of-life; not blocking
- **Effort**: Medium — Audit + per-type file generation + update 4-5 skill files + docs
- **Risk**: Low — purely structural refactor, no behavioral changes if loader shim is correct
- **Breaking Change**: No

## Labels

`enhancement`, `templates`, `refactor`

## Session Log

- `/ll:capture-issue` - 2026-02-24T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/568ba5fc-d209-4c80-bff7-a8c1237be3b5.jsonl`
- `/ll:format-issue` - 2026-02-24 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/cfefb72b-eeff-42e5-8aa5-7184aca87595.jsonl`
- `/ll:refine-issue` - 2026-02-25 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b0f00b27-06ea-419f-bf8b-cab2ce74db4f.jsonl` - Consumer audit complete: 5 skill/command files reference issue-sections.json; no Python code loads it yet; proposed solution TBD replaced with concrete migration plan

---

## Status

**Open** | Created: 2026-02-24 | Priority: P4

## Blocked By

- ENH-491

- FEAT-441