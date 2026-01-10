---
discovered_commit: 1fd4b0e
discovered_branch: main
discovered_date: 2026-01-10T00:00:00Z
discovered_by: audit_docs
doc_file: README.md
---

# BUG-014: Incorrect command counts and missing command documentation

## Summary

Documentation claims 18 slash commands across multiple files, but there are actually 20 commands. Two commands (`handoff` and `resume`) are implemented but not documented in command tables or listed in the changelog.

## Location

- **Files**:
  - README.md (lines 13, 229-275, 446)
  - scripts/README.md (line 9)
  - docs/ARCHITECTURE.md (line 24)
  - docs/COMMANDS.md (entire file)
  - CHANGELOG.md (line 12)

## Current Content

README.md (line 13):
```markdown
- **18 slash commands** for development workflows
```

Commands tables in README.md and docs/COMMANDS.md list 18 commands, missing:
- `/ll:handoff`
- `/ll:resume`

## Problem

The actual command count is **20**, not 18. The following commands exist in `commands/` but are undocumented:

| Command | Description |
|---------|-------------|
| `/ll:handoff` | Generate continuation prompt for session handoff |
| `/ll:resume` | Resume from a previous session's continuation prompt |

These commands were added as part of the continuation/handoff feature (FEAT-006) but the documentation counts were not updated.

### Additional Issue

docs/ARCHITECTURE.md (lines 82-88) references 5 hook prompt files in the directory structure:
- `hooks/prompts/context-monitor.md`
- `hooks/prompts/post-tool-state-tracking.md`
- `hooks/prompts/pre-compact-state.md`
- `hooks/prompts/session-start-resume.md`
- `hooks/prompts/continuation-prompt-template.md`

Only `continuation-prompt-template.md` actually exists. The other 4 files are missing.

## Expected Content

README.md:
```markdown
- **20 slash commands** for development workflows
```

Add to Session Management section in command tables:
```markdown
| `/ll:handoff` | Generate continuation prompt for session handoff |
| `/ll:resume` | Resume from previous session's continuation prompt |
```

## Files to Update

1. **README.md**
   - Line 13: Change "18" to "20"
   - Line 446: Update count in structure comment
   - Lines 269-275: Add Session Management section with handoff and resume

2. **scripts/README.md**
   - Line 9: Change "18" to "20"

3. **docs/ARCHITECTURE.md**
   - Line 24: Change "18" to "20"
   - Lines 82-88: Remove or correct references to non-existent hook prompt files

4. **docs/COMMANDS.md**
   - Add Session Management section with handoff and resume commands

5. **CHANGELOG.md**
   - Line 12: Change "18" to "20"
   - Add handoff and resume to the command list

## Impact

- **Severity**: Medium (misleading documentation)
- **Effort**: Small (text updates)
- **Risk**: Low

## Labels

`bug`, `documentation`, `auto-generated`

---

## Resolution

- **Action**: fix
- **Completed**: 2026-01-10
- **Status**: Completed

### Changes Made
- README.md: Updated count from 18 to 20, updated structure comment, added Session Management section with handoff and resume commands
- scripts/README.md: Updated count from 18 to 20
- docs/ARCHITECTURE.md: Updated count from 18 to 20, removed references to non-existent hook prompt files
- docs/COMMANDS.md: Added Session Management section with handoff and resume commands, added to quick reference table
- CHANGELOG.md: Updated count from 18 to 20, added handoff and resume to command list

### Verification Results
- All documentation files now reference "20 slash commands"
- No references to non-existent hook prompt files remain
- Commands directory contains 20 command files as documented

---

## Status

**Completed** | Created: 2026-01-10 | Resolved: 2026-01-10 | Priority: P2
