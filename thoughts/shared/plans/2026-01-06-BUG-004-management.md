# BUG-004: Incorrect command and agent counts in documentation - Implementation Plan

## Issue Reference
- **File**: .issues/bugs/P1-BUG-004-incorrect-command-agent-counts-in-docs.md
- **Type**: bug
- **Priority**: P1
- **Action**: fix

## Current State Analysis

### Key Discoveries
- README.md:13-14 shows "16 slash commands" and "4 specialized agents" (incorrect)
- README.md:446-447 shows "(16 commands)" and "(4 agents)" in directory structure comments
- README.md:277-284 agents table only lists 4 agents, missing 3
- scripts/README.md:9-10 shows "15 slash commands" and "4 specialized agents"
- docs/ARCHITECTURE.md:23-24 Mermaid diagram shows "16 slash commands" and "4 specialized agents"
- docs/ARCHITECTURE.md:63,71 directory structure comments show wrong counts
- CHANGELOG.md:12 shows "15 slash commands"
- CHANGELOG.md:29-33 lists only 4 agents

### Actual Counts
- **Commands**: 18 slash commands in `commands/` directory
- **Agents**: 7 specialized agents in `agents/` directory

### Missing Agents from Documentation
- `consistency-checker` - Cross-component consistency validation
- `plugin-config-auditor` - Plugin configuration auditing
- `prompt-optimizer` - Codebase context for prompt enhancement

## Desired End State

All documentation files should reflect:
- **18 slash commands** for development workflows
- **7 specialized agents** for codebase analysis

The agents table in README.md and scripts/README.md should include all 7 agents.

### How to Verify
- Grep for "slash commands" and "agents" counts in documentation files
- Verify agents table has 7 rows (plus header)
- Counts match actual file counts in commands/ and agents/ directories

## What We're NOT Doing

- Not changing any functionality
- Not updating command or agent implementations
- Not modifying config files

## Problem Analysis

Documentation contains manually maintained counts that became stale as new commands and agents were added. The discrepancy is:
- Commands: stated 15-16, actual 18 (3 added without doc update)
- Agents: stated 4, actual 7 (3 added without doc update)

## Solution Approach

Simple text replacement in 4 documentation files. No code changes required.

## Implementation Phases

### Phase 1: Update README.md

#### Overview
Fix counts and expand agents table in main README.

#### Changes Required

**File**: `README.md`

1. Line 13: Change "16 slash commands" to "18 slash commands"
2. Line 14: Change "4 specialized agents" to "7 specialized agents"
3. Lines 277-284: Add 3 missing agents to table
4. Line 446: Change "(16 commands)" to "(18 commands)"
5. Line 447: Change "(4 agents)" to "(7 agents)"

New agents table (lines 276-287):
```markdown
## Agents

| Agent | Description |
|-------|-------------|
| `codebase-analyzer` | Analyze implementation details |
| `codebase-locator` | Find files by feature/topic |
| `codebase-pattern-finder` | Find code patterns and examples |
| `consistency-checker` | Cross-component consistency validation |
| `plugin-config-auditor` | Plugin configuration auditing |
| `prompt-optimizer` | Codebase context for prompt enhancement |
| `web-search-researcher` | Research web information |
```

#### Success Criteria

**Automated Verification**:
- [ ] `grep -n "18 slash commands" README.md` finds line 13
- [ ] `grep -n "7 specialized agents" README.md` finds line 14
- [ ] `grep -c "^\| \`" README.md | grep "7"` confirms 7 agent rows in table

---

### Phase 2: Update scripts/README.md

#### Overview
Fix counts and expand agents table in scripts README.

#### Changes Required

**File**: `scripts/README.md`

1. Line 9: Change "15 slash commands" to "18 slash commands"
2. Line 10: Change "4 specialized agents" to "7 specialized agents"
3. Lines 222-229: Add 3 missing agents to table (same as README.md)

#### Success Criteria

**Automated Verification**:
- [ ] `grep -n "18 slash commands" scripts/README.md` finds line 9
- [ ] `grep -n "7 specialized agents" scripts/README.md` finds line 10

---

### Phase 3: Update docs/ARCHITECTURE.md

#### Overview
Fix counts in Mermaid diagram and directory structure comments.

#### Changes Required

**File**: `docs/ARCHITECTURE.md`

1. Line 23: Change "16 slash commands" to "18 slash commands" in Mermaid
2. Line 24: Change "4 specialized agents" to "7 specialized agents" in Mermaid
3. Line 63: Change "16 slash command templates" to "18 slash command templates"
4. Line 71: Change "4 specialized agents" to "7 specialized agents"

#### Success Criteria

**Automated Verification**:
- [ ] `grep -c "18" docs/ARCHITECTURE.md` shows correct occurrences
- [ ] `grep -c "7 specialized" docs/ARCHITECTURE.md` shows correct occurrences

---

### Phase 4: Update CHANGELOG.md

#### Overview
Fix counts in v1.0.0 release notes.

#### Changes Required

**File**: `CHANGELOG.md`

1. Line 12: Change "15 slash commands" to "18 slash commands"
2. Lines 29-33: Add 3 missing agents to list

Updated agents list:
```markdown
- **7 specialized agents**:
  - `codebase-analyzer` - Implementation details analysis
  - `codebase-locator` - File and feature discovery
  - `codebase-pattern-finder` - Code pattern identification
  - `consistency-checker` - Cross-component consistency validation
  - `plugin-config-auditor` - Plugin configuration auditing
  - `prompt-optimizer` - Codebase context for prompt enhancement
  - `web-search-researcher` - Web research capability
```

#### Success Criteria

**Automated Verification**:
- [ ] `grep -n "18 slash commands" CHANGELOG.md` finds line 12
- [ ] `grep -n "7 specialized agents" CHANGELOG.md` finds line 29
- [ ] `grep -c "codebase-\|consistency-\|plugin-config-\|prompt-\|web-search-" CHANGELOG.md` shows 7

---

## Testing Strategy

### Verification Commands
```bash
# Verify command count matches actual files
ls commands/*.md | wc -l  # Should be 18

# Verify agent count matches actual files
ls agents/*.md | wc -l  # Should be 7

# Verify all docs updated
grep "18 slash commands" README.md scripts/README.md CHANGELOG.md
grep "7 specialized agents" README.md scripts/README.md CHANGELOG.md
```

## References

- Original issue: `.issues/bugs/P1-BUG-004-incorrect-command-agent-counts-in-docs.md`
- Commands directory: `commands/` (18 files)
- Agents directory: `agents/` (7 files)
