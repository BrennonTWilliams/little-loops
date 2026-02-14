# BUG-096: README.md missing 6 commands in command tables - Implementation Plan

## Issue Reference
- **File**: `.issues/bugs/P3-BUG-096-readme-missing-6-commands-in-tables.md`
- **Type**: bug
- **Priority**: P3
- **Action**: fix

## Current State Analysis

The README.md Commands section (lines 249-303) documents 18 commands across 6 sections:
- Setup & Help (2 commands): `/ll:init`, `/ll:help`
- Code Quality (3 commands): `/ll:check-code`, `/ll:run-tests`, `/ll:find-dead-code`
- Issue Management (6 commands): `/ll:manage-issue`, `/ll:ready-issue`, `/ll:prioritize-issues`, `/ll:verify-issues`, `/ll:normalize-issues`, `/ll:scan-codebase`
- Documentation & Analysis (3 commands): `/ll:audit-docs`, `/ll:audit-architecture`, `/ll:describe-pr`
- Git & Workflow (2 commands): `/ll:commit`, `/ll:iterate-plan`
- Session Management (2 commands): `/ll:handoff`, `/ll:resume`

### Key Discoveries
- 6 commands exist in `commands/` but are not in README tables: `README.md:249-303`
- Existing table format uses: `| Command | Description |` with backticks around commands
- Arguments shown as `<required>` or `[optional]`
- Commands without arguments have no suffix

## Desired End State

All 24 commands in `commands/` directory should be documented in the README.md Commands section with consistent formatting.

### How to Verify
- Count commands in README tables: `grep -E '^\| \`/ll:' README.md | wc -l` should equal 24
- Count command files: `ls commands/*.md | wc -l` should equal 24
- Both counts should match

## What We're NOT Doing

- Not changing command file content - this is a documentation-only fix
- Not reorganizing existing sections unless needed to add new commands
- Not adding a new "Automation" section - `/ll:create-loop` fits better in Git & Workflow since it creates workflow configurations

## Problem Analysis

Six commands are missing from the README command tables:
1. `/ll:capture-issue` - Issue Management (captures issues from conversation)
2. `/ll:align-issues` - Issue Management (validates issues against documents)
3. `/ll:audit-claude-config` - Documentation & Analysis (audits plugin config)
4. `/ll:cleanup-worktrees` - Git & Workflow (cleans orphaned worktrees)
5. `/ll:create-loop` - Git & Workflow (creates FSM loop configurations)
6. `/ll:toggle-autoprompt` - Session Management (toggles prompt optimization)

## Solution Approach

Add entries for each missing command to the appropriate existing section, following the established table format pattern.

## Implementation Phases

### Phase 1: Add Missing Issue Management Commands

#### Overview
Add `/ll:capture-issue` and `/ll:align-issues` to the Issue Management section.

#### Changes Required

**File**: `README.md`
**Changes**: Add two rows to Issue Management table after line 280 (after `/ll:scan-codebase`)

```markdown
| `/ll:capture-issue [input]` | Capture issues from conversation |
| `/ll:align-issues <category>` | Validate issues against key documents |
```

#### Success Criteria

**Automated Verification**:
- [ ] `grep -c '^\| \`/ll:capture-issue' README.md` returns 1
- [ ] `grep -c '^\| \`/ll:align-issues' README.md` returns 1

---

### Phase 2: Add Missing Documentation & Analysis Command

#### Overview
Add `/ll:audit-claude-config` to the Documentation & Analysis section.

#### Changes Required

**File**: `README.md`
**Changes**: Add one row to Documentation & Analysis table after line 288 (after `/ll:describe-pr`)

```markdown
| `/ll:audit-claude-config [scope]` | Audit Claude Code plugin configuration |
```

#### Success Criteria

**Automated Verification**:
- [ ] `grep -c '^\| \`/ll:audit-claude-config' README.md` returns 1

---

### Phase 3: Add Missing Git & Workflow Commands

#### Overview
Add `/ll:cleanup-worktrees` and `/ll:create-loop` to the Git & Workflow section.

#### Changes Required

**File**: `README.md`
**Changes**: Add two rows to Git & Workflow table after line 295 (after `/ll:iterate-plan`)

```markdown
| `/ll:cleanup-worktrees [mode]` | Clean orphaned git worktrees |
| `/ll:create-loop` | Interactive FSM loop creation |
```

#### Success Criteria

**Automated Verification**:
- [ ] `grep -c '^\| \`/ll:cleanup-worktrees' README.md` returns 1
- [ ] `grep -c '^\| \`/ll:create-loop' README.md` returns 1

---

### Phase 4: Add Missing Session Management Command

#### Overview
Add `/ll:toggle-autoprompt` to the Session Management section.

#### Changes Required

**File**: `README.md`
**Changes**: Add one row to Session Management table after line 302 (after `/ll:resume`)

```markdown
| `/ll:toggle-autoprompt [setting]` | Toggle automatic prompt optimization |
```

#### Success Criteria

**Automated Verification**:
- [ ] `grep -c '^\| \`/ll:toggle-autoprompt' README.md` returns 1

---

### Phase 5: Verification

#### Overview
Verify all 24 commands are documented correctly.

#### Success Criteria

**Automated Verification**:
- [ ] `grep -E '^\| \`/ll:' README.md | wc -l` returns 24
- [ ] `ls commands/*.md | wc -l` returns 24

## Testing Strategy

### Verification Commands
```bash
# Count documented commands
grep -E '^\| \`/ll:' README.md | wc -l
# Expected: 24

# Count actual command files
ls commands/*.md | wc -l
# Expected: 24

# List documented commands (for review)
grep -E '^\| \`/ll:' README.md | sed 's/|.*|$//'
```

## References

- Original issue: `.issues/bugs/P3-BUG-096-readme-missing-6-commands-in-tables.md`
- Existing command table pattern: `README.md:253-256`
- Command files: `commands/*.md`
