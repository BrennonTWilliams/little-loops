# ENH-093: Convert create-loop Skill to Slash Command - Implementation Plan

## Issue Reference
- **File**: `.issues/enhancements/P3-ENH-093-convert-create-loop-skill-to-command.md`
- **Type**: enhancement
- **Priority**: P3
- **Action**: improve

## Current State Analysis

The `/ll:create-loop` functionality exists as a Skill at `skills/create-loop/SKILL.md` (516 lines). It's an interactive wizard that guides users through creating FSM loop configurations.

### Key Discoveries
- Current location: `skills/create-loop/SKILL.md` (only file in directory)
- Uses `AskUserQuestion` for multi-step wizard flow
- Supports four paradigms: goal, invariants, convergence, imperative
- Generates YAML configurations for `.loops/<name>.yaml`
- No external file references (all content inline)

### Pattern Comparison
Commands in the codebase:
- Use simple frontmatter with `description` and `arguments` array
- Longest commands are 600+ lines (inline content)
- Interactive commands (`init.md`, `capture_issue.md`) use same `AskUserQuestion` pattern
- No commands currently use `@${CLAUDE_PLUGIN_ROOT}` for external references

Skills vs Commands (per plugin-dev documentation):
| Aspect | Skills | Commands |
|--------|--------|----------|
| Triggering | Auto-triggered by keywords OR user-invoked | User-invoked only |
| Purpose | Domain knowledge/expertise | Specific workflows/tasks |

The create-loop wizard is only manually invoked and executes a specific workflow, making it a better fit as a Command.

## Desired End State

- `commands/create_loop.md` - New command file with wizard workflow
- `skills/create-loop/` - Directory removed
- Documentation updated to reflect it's a command (not skill)

### How to Verify
- `/ll:create-loop` works as a command
- Interactive wizard flow preserved (all 5 steps work)
- All four paradigms supported
- Skill directory removed
- Documentation references updated

## What We're NOT Doing

- Not changing the wizard flow or paradigm options
- Not extracting content to external reference files (no current commands do this, and 516 lines is within typical command length)
- Not modifying the underlying FSM compilers or schema
- Not changing how `ll-loop` validates or runs loops

## Solution Approach

1. Create new command file with converted frontmatter and workflow content
2. Remove skill directory
3. Update documentation references

## Implementation Phases

### Phase 1: Create Command File

#### Overview
Create `commands/create_loop.md` by converting the skill to command format.

#### Changes Required

**File**: `commands/create_loop.md`
**Changes**: New file - convert skill to command format

Frontmatter transformation:
```yaml
# FROM (skill):
---
description: |
  Create a new FSM loop configuration interactively...
  Trigger keywords: "create loop", "new loop", ...
---

# TO (command):
---
description: Create a new FSM loop configuration interactively. Guides users through paradigm selection, parameter gathering, YAML generation, and validation.
allowed-tools:
  - Bash(mkdir:*, test:*, ll-loop:*)
---
```

Content adjustments:
- Update title from `# /ll:create-loop` to `# Create Loop`
- Update intro text (remove "skill" references, say "command")
- Remove "Trigger keywords" from description
- Add `## Arguments` section (no required args)
- Add `## Examples` section
- Add `## Integration` section

#### Success Criteria

**Automated Verification**:
- [ ] File exists at `commands/create_loop.md`
- [ ] Frontmatter is valid YAML

**Manual Verification**:
- [ ] `/ll:create-loop` loads and starts the wizard
- [ ] All four paradigm paths work

---

### Phase 2: Remove Skill Directory

#### Overview
Delete the old skill directory now that the command exists.

#### Changes Required

**Directory**: `skills/create-loop/`
**Changes**: Delete entire directory

```bash
rm -rf skills/create-loop/
```

#### Success Criteria

**Automated Verification**:
- [ ] Directory `skills/create-loop/` does not exist

**Manual Verification**:
- [ ] No skill appears in `/ll:help` for create-loop

---

### Phase 3: Update Documentation

#### Overview
Update references in documentation to reflect the change from skill to command.

#### Changes Required

**File**: `docs/generalized-fsm-loop.md`
**Changes**: Update references to "skill" → "command"

Line 1830 currently says:
```
- Command is a skill in `skills/create-loop.md`
```
Change to:
```
- Command is implemented in `commands/create_loop.md`
```

Line 1849 currently says:
```
9. ✅ **`/ll:create-loop` command** - In scope for v1; interactive skill using `AskUserQuestion`
```
Change to:
```
9. ✅ **`/ll:create-loop` command** - In scope for v1; interactive command using `AskUserQuestion`
```

No changes needed to README.md (already says "create loops with `/ll:create-loop`" - generic reference)

#### Success Criteria

**Automated Verification**:
- [ ] Grep for "skill" in docs/generalized-fsm-loop.md near create-loop returns no matches
- [ ] Grep for "create_loop.md" in docs/generalized-fsm-loop.md finds the updated reference

**Manual Verification**:
- [ ] Documentation accurately describes create-loop as a command

---

## Testing Strategy

### Functional Testing
- Invoke `/ll:create-loop` and verify wizard starts
- Test each paradigm selection path
- Verify YAML generation and file save

### Regression Testing
- Existing tests in `scripts/tests/test_fsm_compilers.py` should still pass (unchanged)
- Existing tests in `scripts/tests/test_fsm_schema.py` should still pass (unchanged)

## References

- Original issue: `.issues/enhancements/P3-ENH-093-convert-create-loop-skill-to-command.md`
- Current skill: `skills/create-loop/SKILL.md`
- Example command: `commands/init.md` (interactive wizard pattern)
- Example command: `commands/capture_issue.md` (interactive flow)
- FSM documentation: `docs/generalized-fsm-loop.md:1750-1833`
