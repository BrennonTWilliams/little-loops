# Fix /ll:create-sprint Command Issues from Audit

## Summary

The `/ll:create-sprint` command has several consistency and documentation issues identified during an audit that should be addressed.

## Context

An audit of the `create_sprint.md` command file revealed multiple issues ranging from incorrect file location to missing configuration and unclear syntax in the command instructions.

## Issues to Fix

### 1. Command File Location (Medium Priority)

**Problem**: Command is located at `.claude/commands/create_sprint.md` while 25 other commands are in the root `commands/` directory.

**Fix**: Move the command file to `commands/create_sprint.md` for consistency with other commands.

### 2. Missing `allowed-tools` in Frontmatter (Low Priority)

**Problem**: The frontmatter lacks an `allowed-tools` specification, unlike other commands such as `manage_issue.md`.

**Fix**: Add `allowed-tools` if any privileged tools are needed, or explicitly document that none are required.

### 3. Bash Variable Syntax in Non-Bash Context (Low Priority)

**Problem**: Lines 39-43 use bash variable syntax (`${name}`, `${description:-}`) but this is a Claude Code command prompt, not a bash script.

**Fix**: Use appropriate placeholder syntax consistent with other commands (e.g., direct argument references or `$ARGUMENTS.name` style).

### 4. Incorrect Glob Brace Syntax (Low Priority)

**Problem**: Line 76 uses `.issues/**/*-{issue_id}-*.md` which is incorrect brace expansion syntax for glob patterns.

**Fix**: Document that the actual issue ID should be substituted directly into the pattern.

### 5. Undocumented `max_iterations` Field (Low Priority)

**Problem**: The YAML template shows `max_iterations: 100` but this field is not documented in `config-schema.json` under the `sprints` section.

**Fix**: Either add `max_iterations` to the schema or remove it from the template.

### 6. Missing `sprints` Config in Project (Low Priority)

**Problem**: The command references `sprints.sprints_dir`, `sprints.default_mode`, etc. but `.claude/ll-config.json` doesn't have a `sprints` section.

**Fix**: Add the `sprints` configuration section to `.claude/ll-config.json`.

### 7. No Directory Creation Step (Low Priority)

**Problem**: The command creates files at `.sprints/${SPRINT_NAME}.yaml` but doesn't ensure the `.sprints/` directory exists first.

**Fix**: Add a step to create the `.sprints/` directory if it doesn't exist before writing the YAML file.

## Acceptance Criteria

- [x] Command file moved to `commands/create_sprint.md`
- [x] Frontmatter updated with appropriate `allowed-tools` (or documented as not needed)
- [x] Variable syntax updated to match other command conventions
- [x] Glob pattern examples use correct syntax
- [x] `max_iterations` either documented in schema or removed from template
- [x] `sprints` section added to `.claude/ll-config.json`
- [x] Directory creation step added before YAML file write

## Files to Modify

- `.claude/commands/create_sprint.md` → `commands/create_sprint.md`
- `.claude/ll-config.json`
- `config-schema.json` (if adding `max_iterations`)

## References

- Audit comparison: `commands/manage_issue.md` (frontmatter example)
- Config schema: `config-schema.json` (sprints section at lines 527-556)

---

Created: 2026-01-24 | Priority: P3 | Type: Enhancement

---

## Resolution

- **Action**: implement
- **Completed**: 2026-01-24
- **Status**: Completed

### Changes Made

1. **Moved command file** - `git mv .claude/commands/create_sprint.md commands/create_sprint.md`
2. **Added `allowed-tools`** - Added `Bash(mkdir:*)` to frontmatter for directory creation
3. **Fixed glob syntax** - Changed `{issue_id}` to `[ISSUE-ID]` placeholder notation
4. **Removed `max_iterations`** - Removed from YAML template (not in schema)
5. **Added directory creation step** - New section 4 with `mkdir -p .sprints`
6. **Added `sprints` config** - Added to `.claude/ll-config.json` with schema defaults
7. **Updated config references** - Changed to `{{config.sprints.*}}` template syntax

### Verification Results
- Tests: PASS
- Lint: PASS
- JSON validation: PASS
