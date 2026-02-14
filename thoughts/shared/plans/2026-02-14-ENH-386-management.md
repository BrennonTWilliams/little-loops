# ENH-386: Add command cross-reference validation to audit-claude-config

## Summary

Add a cross-reference validation check to `audit-claude-config` that verifies `/ll:*` command references in skill files match the commands defined in `commands/help.md`.

## Research Findings

- **Main file to modify**: `skills/audit-claude-config/SKILL.md`
- **Supporting agent**: `agents/consistency-checker.md` — already has cross-reference matrix for CLAUDE.md → Commands; needs skill → command check added
- **Data source**: `commands/help.md` — lists all valid commands in structured format
- **Skill files**: 16 skill files in `skills/*/SKILL.md` that may reference `/ll:*` commands
- **Existing pattern**: Wave 2 already checks `CLAUDE.md → Commands` (line 66 of consistency-checker.md), this enhancement adds `Skills → Commands` as a parallel check
- **No Python code changes**: This is entirely skill/agent prompt changes

## Implementation Plan

### Phase 1: Update consistency-checker agent

**File**: `agents/consistency-checker.md`

Add a new row to the Cross-Reference Matrix (after line 66):

```
| skills/*/SKILL.md | commands/*.md | /ll:X referenced → commands/X.md or valid skill |
```

Add to Core Responsibilities section 1 (Internal References):
- Skills → Commands (/ll:X references in skill content resolve to valid commands)

Add to Validation Process Step 1:
- Extract all /ll:X command references from skill file content (below frontmatter)

Add to Output Format, a new validation table section:
```
#### Skills → Commands
| Skill File | Command Referenced | Command File | Status |
|------------|-------------------|--------------|--------|
| issue-workflow/SKILL.md | /ll:scan-codebase | commands/scan-codebase.md | OK |
```

Add to Summary table:
```
| Skills → Commands | X | Y | Z |
```

### Phase 2: Update audit-claude-config skill

**File**: `skills/audit-claude-config/SKILL.md`

**2a.** In Wave 1 Task 2 (Plugin Components Auditor, lines 169-209), add instruction to collect `/ll:*` command references from skill files:

After the existing "Return structured findings with:" section (line 203), add:
```
- List of all /ll:X command references found in skill files for Wave 2
```

**2b.** In Phase 2 (Collect Wave 1 Results, line 251-257), add to the compiled reference list:
```
- All command references (/ll:X) found in skill files
```

**2c.** In Wave 2 Task 1 (Internal Consistency Checker, lines 289-316), add a new check:

After check 8 (line 307), add:
```
9. **Skills → Commands**: /ll:X references in skill files have matching commands/X.md or are valid skill names
```

And add to the Return section:
```
- Skills → Commands validation results
```

### Phase 3: Verify

- [ ] All files are valid markdown (no syntax errors)
- [ ] New checks integrate with existing Wave 2 pattern
- [ ] Cross-reference matrix in consistency-checker is complete

## Success Criteria

- [ ] consistency-checker agent includes Skills → Commands in cross-reference matrix
- [ ] audit-claude-config Wave 1 collects /ll:X references from skill files
- [ ] audit-claude-config Wave 2 validates skill command references
- [ ] Lint/type checks pass (no Python changes, but verify)
