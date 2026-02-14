# ENH-136: Add overwrite handling to create_sprint command - Implementation Plan

## Issue Reference
- **File**: .issues/enhancements/P4-ENH-136-create-sprint-add-overwrite-handling.md
- **Type**: enhancement
- **Priority**: P4
- **Action**: improve

## Current State Analysis

The `create_sprint` command (`commands/create_sprint.md:85-95`) currently writes sprint files directly to `.sprints/${SPRINT_NAME}.yaml` without checking if a file already exists. This differs from the `create_loop` command which properly checks for existing files and prompts the user before overwriting.

### Key Discoveries
- `commands/create_sprint.md:85-95` - Current Step 4 creates directory with `mkdir -p`, then Step 5 immediately writes the file with no existence check
- `commands/create_loop.md:903-924` - Reference pattern shows: create dir → check with `test -f` → prompt with AskUserQuestion → write
- The `create_loop` command uses two options: "Yes, overwrite" and "No, choose different name"
- The issue proposes three options including "Cancel" which aligns with standard UX patterns

## Desired End State

Before writing the sprint file, the command should:
1. Check if `.sprints/${SPRINT_NAME}.yaml` exists using the Glob tool
2. If it exists, prompt the user with three options:
   - "Overwrite" - Continue and replace existing file
   - "Choose different name" - Return to name input
   - "Cancel" - Exit sprint creation
3. Only proceed to write if the file doesn't exist OR user chose "Overwrite"

### How to Verify
- Create a sprint with name "test-sprint"
- Run command again with same name
- Verify user is prompted before overwriting
- Verify "Choose different name" returns to name input
- Verify "Cancel" exits gracefully

## What We're NOT Doing

- Not modifying the allowed-tools list (Glob tool is a core tool, not a Bash command)
- Not changing the actual file writing logic in Step 5
- Not adding validation for sprint name format (that's ENH-138)
- Not changing config file reading (that's ENH-137)

## Problem Analysis

The issue is a simple omission - the overwrite check step exists in `create_loop` but was not included when `create_sprint` was created. This is a low-risk, focused addition.

## Solution Approach

Add a new "Step 4b" between the current Step 4 (Create Sprint Directory) and Step 5 (Create Sprint YAML File) that:
1. Uses the Glob tool to check for existing sprint file
2. If found, presents AskUserQuestion with overwrite options
3. Routes based on user selection

The pattern from the issue document will be followed, which uses Glob instead of `test -f` (cleaner and doesn't require adding to allowed-tools).

## Implementation Phases

### Phase 1: Add Overwrite Check Step

#### Overview
Insert a new step between Step 4 and Step 5 that checks for existing sprint files and prompts the user.

#### Changes Required

**File**: `commands/create_sprint.md`
**Changes**: Insert new Step 4b after line 91 (end of Step 4) and before line 93 (current Step 5)

The new step (approximately lines 92-115 after insertion):

```markdown
### 4b. Check for Existing Sprint

Before writing, check if a sprint with this name already exists:

Use the Glob tool to check: `.sprints/${SPRINT_NAME}.yaml`

If the file exists, use AskUserQuestion:

```yaml
questions:
  - question: "A sprint named '${SPRINT_NAME}' already exists. What would you like to do?"
    header: "Overwrite"
    multiSelect: false
    options:
      - label: "Overwrite"
        description: "Replace the existing sprint configuration"
      - label: "Choose different name"
        description: "Go back and pick a new name"
      - label: "Cancel"
        description: "Abort sprint creation"
```

**Based on user response:**
- **"Overwrite"**: Continue to Step 5 (write file)
- **"Choose different name"**: Return to Step 1 to input a new name
- **"Cancel"**: Display "Sprint creation cancelled." and stop
```

#### Success Criteria

**Automated Verification**:
- [ ] No Python code changes, so no tests to run for this specific change
- [ ] Lint passes: `ruff check scripts/` (command file is markdown, not Python)
- [ ] File structure is valid markdown

**Manual Verification**:
- [ ] Create a sprint file manually: `.sprints/test-conflict.yaml` with any valid content
- [ ] Run `/ll:create-sprint test-conflict --description "Test"`
- [ ] Verify the overwrite prompt appears with three options
- [ ] Verify "Overwrite" proceeds to write
- [ ] Verify "Choose different name" prompts for new name
- [ ] Verify "Cancel" exits gracefully

---

### Phase 2: Renumber Subsequent Steps

#### Overview
Renumber Step 5 to Step 5 and Step 6 to Step 6 (no changes needed since we're inserting as "4b" not renumbering).

Actually, looking at the current structure:
- Step 4: Create Sprint Directory (lines 85-91)
- Step 5: Create Sprint YAML File (lines 93-121)
- Step 6: Output Confirmation (lines 122-149)

By inserting as "Step 4b", we avoid renumbering entirely. No changes needed for this phase.

#### Changes Required

None - using "4b" numbering scheme avoids renumbering.

#### Success Criteria

**Automated Verification**:
- [ ] N/A - no changes

---

## Testing Strategy

### Manual Testing
This is a command definition (markdown), not Python code. Testing requires:
1. Create a test sprint file at `.sprints/test-conflict.yaml`
2. Run the command with the same name
3. Verify the prompt appears
4. Test each option (Overwrite, Choose different name, Cancel)

### Unit Tests
N/A - this is a command definition file, not Python code. The logic is executed by Claude interpreting the markdown.

## References

- Original issue: `.issues/enhancements/P4-ENH-136-create-sprint-add-overwrite-handling.md`
- Related patterns: `commands/create_loop.md:908-924`
- Target file: `commands/create_sprint.md:91-93` (insertion point)
