# BUG-014: Incorrect command counts and missing documentation - Implementation Plan

## Issue Reference
- **File**: .issues/bugs/P2-BUG-014-incorrect-command-counts-missing-docs.md
- **Type**: bug
- **Priority**: P2
- **Action**: fix

## Current State Analysis

Documentation across 5 files claims 18 slash commands exist, but there are actually 20 commands in the `commands/` directory. The two undocumented commands are `/ll:handoff` and `/ll:resume`, which were added as part of FEAT-006 (continuation prompt handoff integration).

### Key Discoveries
- README.md:13 - Claims "18 slash commands"
- README.md:449 - Structure comment claims "(18 commands)"
- scripts/README.md:9 - Claims "18 slash commands"
- docs/ARCHITECTURE.md:24 - Mermaid diagram shows "18 slash commands"
- docs/ARCHITECTURE.md:64 - Comment shows "# 18 slash command templates"
- docs/ARCHITECTURE.md:80-88 - References 5 hook prompt files, only 1 exists
- docs/COMMANDS.md - Lists 18 commands, missing handoff/resume
- CHANGELOG.md:12 - Claims "18 slash commands"

### Patterns Found
- Command tables use 2-column format: `Command | Description`
- Commands are grouped by category with h3 headers
- Categories: Setup & Help, Code Quality, Issue Management, Documentation & Analysis, Git & Workflow
- Session Management should be added as a new category for handoff/resume

## Desired End State

All documentation files accurately reflect 20 slash commands, with handoff and resume properly documented in command tables and the changelog.

### How to Verify
- Count command files: `ls commands/*.md | wc -l` should show 20
- All documentation files reference "20" instead of "18"
- Session Management section exists in README.md and docs/COMMANDS.md
- Hook prompt file references in ARCHITECTURE.md are corrected

## What We're NOT Doing

- Not creating the 4 missing hook prompt files (that's a separate issue)
- Not modifying any Python code
- Not changing command implementations

## Solution Approach

Update documentation files to:
1. Change "18" to "20" in all command count references
2. Add Session Management section with handoff and resume commands
3. Fix hook prompt file references in ARCHITECTURE.md (remove non-existent files)

## Implementation Phases

### Phase 1: Update README.md

#### Overview
Fix command count and add Session Management section to command tables.

#### Changes Required

**File**: `README.md`

**Change 1**: Line 13 - Update count
```markdown
- **20 slash commands** for development workflows
```

**Change 2**: Line 449 - Update structure comment
```markdown
├── commands/             # Slash command templates (20 commands)
```

**Change 3**: After "Git & Workflow" section (around line 275), add Session Management:
```markdown

### Session Management

| Command | Description |
|---------|-------------|
| `/ll:handoff [context]` | Generate continuation prompt for session handoff |
| `/ll:resume [prompt_file]` | Resume from previous session's continuation prompt |
```

#### Success Criteria

**Automated Verification**:
- [ ] File contains "20 slash commands"
- [ ] File contains "(20 commands)"
- [ ] File contains "Session Management" section

---

### Phase 2: Update scripts/README.md

#### Overview
Fix command count in Python package documentation.

#### Changes Required

**File**: `scripts/README.md`

**Change 1**: Line 9 - Update count
```markdown
- **20 slash commands** for development workflows
```

#### Success Criteria

**Automated Verification**:
- [ ] File contains "20 slash commands"

---

### Phase 3: Update docs/ARCHITECTURE.md

#### Overview
Fix command count and remove references to non-existent hook prompt files.

#### Changes Required

**File**: `docs/ARCHITECTURE.md`

**Change 1**: Line 24 - Update Mermaid diagram count
```markdown
        CMD[Commands<br/>20 slash commands]
```

**Change 2**: Line 64 - Update directory comment
```markdown
├── commands/                # 20 slash command templates
```

**Change 3**: Lines 80-88 - Fix hook prompt file listing to only show existing file:
```markdown
├── hooks/                   # Lifecycle hooks and validation scripts
│   ├── hooks.json           # Hook configuration
│   ├── check-duplicate-issue-id.sh  # Validation script
│   └── prompts/
│       └── continuation-prompt-template.md  # Handoff prompt template
```

**Change 4**: Line 606 area - Update context monitoring section to remove reference to non-existent context-monitor.md

#### Success Criteria

**Automated Verification**:
- [ ] File contains "20 slash commands"
- [ ] File contains "# 20 slash command templates"
- [ ] File does NOT contain "context-monitor.md" (except as removed)
- [ ] File does NOT contain "post-tool-state-tracking.md"
- [ ] File does NOT contain "pre-compact-state.md"
- [ ] File does NOT contain "session-start-resume.md"

---

### Phase 4: Update docs/COMMANDS.md

#### Overview
Add Session Management section with handoff and resume commands.

#### Changes Required

**File**: `docs/COMMANDS.md`

**Change 1**: Add new section after Git & Workflow (around line 107):
```markdown

## Session Management

### `/ll:handoff`
Generate continuation prompt for session handoff.

**Arguments:**
- `context` (optional): Description of current work context

### `/ll:resume`
Resume from a previous session's continuation prompt.

**Arguments:**
- `prompt_file` (optional): Path to continuation prompt (default: `.claude/ll-continue-prompt.md`)
```

**Change 2**: Add to Quick Reference table (around line 132):
```markdown
| `/ll:handoff` | Generate session handoff prompt |
| `/ll:resume` | Resume from continuation prompt |
```

#### Success Criteria

**Automated Verification**:
- [ ] File contains "## Session Management" section
- [ ] File contains "/ll:handoff" documentation
- [ ] File contains "/ll:resume" documentation
- [ ] Quick reference table includes both commands

---

### Phase 5: Update CHANGELOG.md

#### Overview
Fix command count and add handoff/resume to command list.

#### Changes Required

**File**: `CHANGELOG.md`

**Change 1**: Line 12 - Update count
```markdown
- **20 slash commands** for development workflows:
```

**Change 2**: Add to command list (around line 29-30):
```markdown
  - `/ll:handoff` - Generate continuation prompt for session handoff
  - `/ll:resume` - Resume from previous session's continuation prompt
```

#### Success Criteria

**Automated Verification**:
- [ ] File contains "20 slash commands"
- [ ] File contains "/ll:handoff" entry
- [ ] File contains "/ll:resume" entry

---

## Testing Strategy

### Verification
- Grep for "18 slash commands" - should return 0 matches
- Grep for "20 slash commands" - should match 4 files
- Count commands in commands/ directory - should be 20
- Lint check passes

## References

- Original issue: `.issues/bugs/P2-BUG-014-incorrect-command-counts-missing-docs.md`
- Similar previous bug: `.issues/completed/P1-BUG-004-incorrect-command-agent-counts-in-docs.md`
- Feature that added commands: `.issues/completed/P2-FEAT-006-continuation-prompt-handoff-integration.md`
