# ENH-458: Handle conflicting flags and add --dry-run to /ll:init

**Date**: 2026-02-23
**Issue**: P4-ENH-458-handle-conflicting-flags-add-dry-run.md
**Action**: implement

## Research Findings

- Single file to modify: `skills/init/SKILL.md`
- Flag parsing uses bash-style pseudocode (substring matching) at lines 33-42
- `--dry-run` pattern well-established across project: `format-issue`, `refine-issue`, `manage-release`, `align-issues`
- Error format convention: `Error: <description>` + `Usage: /ll:<command> <correct-invocation>`
- Flag conflict precedent: `format-issue/SKILL.md:63-68` (`--all` + `issue_id`)

## Changes

### 1. Frontmatter (line 12)
Add `--dry-run` to description: `Optional flags (--interactive, --yes, --force, --dry-run)`

### 2. Arguments section (lines 24-27)
Add `--dry-run` description after `--force`

### 3. Step 1 - Parse Flags (lines 33-42)
- Add `DRY_RUN=false` variable
- Add `--dry-run` substring check
- Add conflict detection: if `INTERACTIVE=true AND YES=true`, error and stop

### 4. Step 7 - Confirm and Create (lines 172-183)
Add: if `DRY_RUN=true`, skip confirmation

### 5. Step 8 - Write Configuration (lines 185-214)
Add dry-run branch: output config JSON to stdout with `[DRY RUN]` prefixed messages instead of writing files/directories

### 6. Step 9 - Update .gitignore (lines 216-238)
Add: skip entirely when `DRY_RUN=true`, show what would happen

### 7. Step 10 - Completion Message (lines 239-267)
Add dry-run variant that shows what would have been created

### 8. Examples section (lines 276-293)
Add `--dry-run` example and flag combinations table

## Success Criteria

- [ ] `--interactive --yes` produces clear error message
- [ ] `--interactive --force` documented as valid
- [ ] `--yes --force` documented as valid
- [ ] `--dry-run` flag parsed in Step 1
- [ ] `--dry-run` skips file writes in Steps 8-9
- [ ] `--dry-run` outputs config preview to stdout
- [ ] Flag combinations documented in table
- [ ] Examples updated
- [ ] Lint/type checks pass
