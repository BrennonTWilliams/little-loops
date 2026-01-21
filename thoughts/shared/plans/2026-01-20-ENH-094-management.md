# ENH-094: Document /ll:analyze-workflows command - Implementation Plan

## Issue Reference
- **File**: .issues/enhancements/P4-ENH-094-document-analyze-workflows-command.md
- **Type**: enhancement
- **Priority**: P4
- **Action**: improve

## Current State Analysis

### Key Discoveries
- Command definition exists at `commands/analyze-workflows.md:1-394`
- Description in frontmatter (line 2): "Analyze user message history to identify patterns, workflows, and automation opportunities"
- Command has one optional argument `file`: "Path to user-messages JSONL file (auto-detected if omitted)"
- README.md "Documentation & Analysis" section at lines 284-292 - command is missing
- docs/COMMANDS.md "Auditing & Analysis" section at lines 93-111 - command is missing
- docs/COMMANDS.md "Quick Reference" table at lines 161-189 - command is missing

## Desired End State

The `/ll:analyze-workflows` command is documented in:
1. README.md Commands section under "Documentation & Analysis"
2. docs/COMMANDS.md detailed section under "Auditing & Analysis"
3. docs/COMMANDS.md Quick Reference table

### How to Verify
- README.md contains `/ll:analyze-workflows` in the command table
- docs/COMMANDS.md has a `### /ll:analyze-workflows` section with arguments
- docs/COMMANDS.md Quick Reference includes `analyze-workflows`

## What We're NOT Doing

- Not changing the command implementation itself
- Not updating command counts (they already say 25 commands)
- Not modifying any other documentation files

## Solution Approach

Follow existing documentation patterns to add the command to both files in the appropriate sections.

## Implementation Phases

### Phase 1: Update README.md

#### Overview
Add `/ll:analyze-workflows` to the Documentation & Analysis command table.

#### Changes Required

**File**: `README.md`
**Changes**: Add row to the Documentation & Analysis table after line 291

Insert after the `audit_claude_config` row:
```markdown
| `/ll:analyze-workflows [file]` | Analyze user message patterns for automation |
```

#### Success Criteria

**Automated Verification**:
- [ ] File exists and is valid markdown

**Manual Verification**:
- [ ] New row appears in Documentation & Analysis section
- [ ] Description matches frontmatter intent

---

### Phase 2: Update docs/COMMANDS.md

#### Overview
Add detailed command documentation and Quick Reference entry.

#### Changes Required

**File**: `docs/COMMANDS.md`

**Change 1**: Add detailed section after `/ll:audit_claude_config` (around line 111)

```markdown
### `/ll:analyze-workflows`
Analyze user message history to identify patterns, workflows, and automation opportunities.

**Arguments:**
- `file` (optional): Path to user-messages JSONL file (auto-detected if omitted)
```

**Change 2**: Add to Quick Reference table (around line 188)

```markdown
| `analyze-workflows` | Analyze user message patterns for automation |
```

#### Success Criteria

**Automated Verification**:
- [ ] File exists and is valid markdown

**Manual Verification**:
- [ ] `/ll:analyze-workflows` section exists in Auditing & Analysis
- [ ] Quick Reference table includes the command

---

## Testing Strategy

### Manual Verification
- Read both files to confirm entries exist
- Run `/ll:help` to verify command is recognized
- Verify descriptions are consistent across documentation

## References

- Original issue: `.issues/enhancements/P4-ENH-094-document-analyze-workflows-command.md`
- Command definition: `commands/analyze-workflows.md:1-15`
- README pattern: `README.md:284-292`
- COMMANDS.md pattern: `docs/COMMANDS.md:93-111`
