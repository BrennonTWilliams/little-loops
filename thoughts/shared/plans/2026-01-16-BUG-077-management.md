# BUG-077: Skills Use Wrong Directory Structure - Implementation Plan

## Issue Reference
- **File**: `.issues/bugs/P1-BUG-077-skills-wrong-directory-structure.md`
- **Type**: bug
- **Priority**: P1
- **Action**: fix

## Current State Analysis

The skills directory currently uses flat `.md` files instead of the required subdirectory structure with `SKILL.md` files.

### Key Discoveries
- Three skills exist as flat files: `skills/capture-issue.md`, `skills/create-loop.md`, `skills/issue-workflow.md`
- `plugin.json:18` references `"skills": "./skills/"` for auto-discovery
- Claude Code plugin ecosystem consistently uses subdirectory pattern for skills (verified in `claude-mermaid`, `markdown-linter-fixer`, `backend-development` plugins)
- Commands and agents use flat files (correct for their component type), but skills require subdirectories

### Pattern Reference
From installed plugins (e.g., `claude-mermaid/skills/mermaid-diagrams/SKILL.md`):
```
skills/
└── skill-name/
    └── SKILL.md
```

## Desired End State

```
skills/
├── capture-issue/
│   └── SKILL.md
├── create-loop/
│   └── SKILL.md
└── issue-workflow/
    └── SKILL.md
```

### How to Verify
- No flat `.md` files in `skills/` directory
- Each skill has its own subdirectory with a `SKILL.md` file
- Skills appear in the Skill tool's available skills list
- Skill frontmatter (name, description) is preserved

## What We're NOT Doing

- Not modifying skill content - only restructuring
- Not adding supporting files (templates, scripts) - that's for future enhancement
- Not changing `plugin.json` - it already correctly references `./skills/`
- Not updating documentation references - those can be addressed in follow-up

## Solution Approach

For each of the 3 skills:
1. Create subdirectory with skill name (kebab-case)
2. Move `.md` file into subdirectory
3. Rename file to `SKILL.md`

This is a straightforward file reorganization with no content changes.

## Implementation Phases

### Phase 1: Restructure capture-issue Skill

#### Overview
Create subdirectory and move/rename capture-issue.md to SKILL.md

#### Changes Required

**Action**: Create directory and move file
```bash
mkdir -p skills/capture-issue
git mv skills/capture-issue.md skills/capture-issue/SKILL.md
```

#### Success Criteria

**Automated Verification**:
- [ ] File exists: `skills/capture-issue/SKILL.md`
- [ ] File no longer exists: `skills/capture-issue.md`
- [ ] File content matches original (frontmatter preserved)

---

### Phase 2: Restructure create-loop Skill

#### Overview
Create subdirectory and move/rename create-loop.md to SKILL.md

#### Changes Required

**Action**: Create directory and move file
```bash
mkdir -p skills/create-loop
git mv skills/create-loop.md skills/create-loop/SKILL.md
```

#### Success Criteria

**Automated Verification**:
- [ ] File exists: `skills/create-loop/SKILL.md`
- [ ] File no longer exists: `skills/create-loop.md`
- [ ] File content matches original (frontmatter preserved)

---

### Phase 3: Restructure issue-workflow Skill

#### Overview
Create subdirectory and move/rename issue-workflow.md to SKILL.md

#### Changes Required

**Action**: Create directory and move file
```bash
mkdir -p skills/issue-workflow
git mv skills/issue-workflow.md skills/issue-workflow/SKILL.md
```

#### Success Criteria

**Automated Verification**:
- [ ] File exists: `skills/issue-workflow/SKILL.md`
- [ ] File no longer exists: `skills/issue-workflow.md`
- [ ] File content matches original (frontmatter preserved)

---

### Phase 4: Verify Final Structure

#### Overview
Confirm no flat files remain and directory structure is correct

#### Success Criteria

**Automated Verification**:
- [ ] No `.md` files directly in `skills/` directory: `ls skills/*.md 2>/dev/null | wc -l` returns 0
- [ ] Three skill subdirectories exist
- [ ] Each subdirectory contains exactly one `SKILL.md` file
- [ ] Git status shows clean renames (no deletions/additions)

---

## Testing Strategy

### Verification Commands
```bash
# Check no flat files remain
ls skills/*.md 2>/dev/null && echo "ERROR: flat files exist" || echo "OK: no flat files"

# Check structure
ls -la skills/*/SKILL.md

# Verify content preserved (frontmatter intact)
head -10 skills/capture-issue/SKILL.md
head -10 skills/create-loop/SKILL.md
head -10 skills/issue-workflow/SKILL.md
```

### Post-Restructure Testing
After restructuring, verify in a new Claude Code session that:
1. Skills appear in the Skill tool's available skills list
2. Skill descriptions match the frontmatter

## References

- Original issue: `.issues/bugs/P1-BUG-077-skills-wrong-directory-structure.md`
- Plugin manifest: `plugin.json:18`
- Pattern examples: `~/.claude/plugins/marketplaces/claude-mermaid/skills/mermaid-diagrams/SKILL.md`
