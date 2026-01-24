# ENH-137: Make config reading explicit in create_sprint command - Implementation Plan

## Issue Reference
- **File**: .issues/enhancements/P4-ENH-137-create-sprint-explicit-config-reading.md
- **Type**: enhancement
- **Priority**: P4
- **Action**: improve

## Current State Analysis

The `create_sprint.md` command at `commands/create_sprint.md` documents config values using template placeholder syntax (`{{config.sprints.*}}`) in lines 25-32, but:

1. No explicit instruction to read `.claude/ll-config.json` before using values
2. Process steps use hardcoded values instead of referencing configured values:
   - Line 69: Uses `.issues/**/*.md` (hardcoded)
   - Line 90: Uses `.sprints` (hardcoded)
   - Line 97: Uses `.sprints` (hardcoded)
   - Lines 122, 134-136: Uses hardcoded `.sprints` and default values

### Key Discoveries
- `commands/handoff.md:18-23` uses "Read settings from" pattern that is more explicit
- `commands/resume.md:13-16` uses the same "Read settings from" pattern
- `commands/create_loop.md:27-45` uses "Step 0" naming for pre-process initialization
- `commands/configure.md:56-61` uses explicit "Read X and check Y" instructions

## Desired End State

The `create_sprint.md` command should:
1. Have an explicit "Step 0: Load Configuration" before the current Step 1
2. Use descriptive references ("the configured sprints directory") instead of template syntax where appropriate
3. Reference configured defaults in the YAML example

### How to Verify
- Read the modified `create_sprint.md` and confirm:
  - Step 0 exists with explicit config reading instructions
  - References to config values are clear and actionable
  - No template syntax that relies on auto-interpolation

## What We're NOT Doing

- Not changing the overall process flow (just adding Step 0 and updating references)
- Not adding new functionality
- Not modifying other commands
- Not changing the sprint YAML schema

## Problem Analysis

The template syntax `{{config.sprints.sprints_dir}}` does not auto-interpolate in Claude Code commands. Claude must explicitly read the config file to get actual values. The current command documents what values are used but doesn't instruct Claude to read them.

## Solution Approach

Following patterns from `handoff.md` and `create_loop.md`:
1. Add explicit Step 0 with config reading instructions
2. Update Configuration section to use imperative "Read settings from" language
3. Update Process steps to reference "the configured values" instead of hardcoded paths
4. Update YAML example to reference configured defaults

## Implementation Phases

### Phase 1: Update Configuration Section and Add Step 0

#### Overview
Transform the Configuration section to use explicit reading instructions and add Step 0 before current Step 1.

#### Changes Required

**File**: `commands/create_sprint.md`

**Change 1**: Update Configuration section (lines 21-33)

Replace the current Configuration section with explicit reading instructions:

```markdown
## Configuration

Read settings from `.claude/ll-config.json`:

**Issues settings** (under `issues`):
- `base_dir`: Issues directory (default: `.issues`)

**Sprints settings** (under `sprints`):
- `sprints_dir`: Directory for sprint definitions (default: `.sprints`)
- `default_mode`: Default execution mode (default: `auto`)
- `default_timeout`: Default timeout per issue in seconds (default: `3600`)
- `default_max_workers`: Default worker count for parallel mode (default: `4`)
```

**Change 2**: Insert new Step 0 after Configuration section, before current "### 1. Validate and Parse Inputs"

Add:

```markdown
## Process

### 0. Load Configuration

Read the project configuration from `.claude/ll-config.json` to get sprint settings.

Use the Read tool to read `.claude/ll-config.json`, then extract:
- `issues.base_dir` - Issues directory (use default `.issues` if not set)
- `sprints.sprints_dir` - Directory for sprint files (use default `.sprints` if not set)
- `sprints.default_mode` - Default execution mode (use default `auto` if not set)
- `sprints.default_timeout` - Default timeout in seconds (use default `3600` if not set)
- `sprints.default_max_workers` - Default worker count (use default `4` if not set)

Store these values for use in subsequent steps.
```

#### Success Criteria

**Automated Verification**:
- [ ] File exists and is valid markdown: `test -f commands/create_sprint.md`

**Manual Verification**:
- [ ] Step 0 appears before Step 1 in the Process section
- [ ] Configuration section uses "Read settings from" language

---

### Phase 2: Update Hardcoded References Throughout Process

#### Overview
Update all hardcoded paths and values in Process steps to reference configured values.

#### Changes Required

**File**: `commands/create_sprint.md`

**Change 1**: Line 69 in Step 2 - Update pattern to use configured issues directory

```markdown
1. Use the Glob tool to find active issues:
   - Pattern: `{issues.base_dir}/**/*.md` (using the configured issues directory)
   - Then filter results to exclude paths containing `/completed/`
```

**Change 2**: Line 90 in Step 4 - Update mkdir to use configured sprints directory

```bash
mkdir -p {sprints.sprints_dir}  # using the configured sprints directory
```

**Change 3**: Line 97 in Step 4b - Update Glob to use configured sprints directory

```markdown
Use the Glob tool to check: `{sprints.sprints_dir}/${SPRINT_NAME}.yaml` (using the configured sprints directory)
```

**Change 4**: Line 122 in Step 5 - Update path to use configured sprints directory

```markdown
Create the sprint definition at `{sprints.sprints_dir}/${SPRINT_NAME}.yaml` (using the configured sprints directory):
```

**Change 5**: Lines 134-136 in Step 5 - Update YAML example to reference configured defaults

```yaml
options:
  mode: auto  # or use the configured default_mode
  timeout: 3600  # or use the configured default_timeout
  max_workers: 4  # or use the configured default_max_workers
```

#### Success Criteria

**Automated Verification**:
- [ ] File exists and is valid markdown: `test -f commands/create_sprint.md`

**Manual Verification**:
- [ ] All paths reference "configured" values instead of hardcoded ones
- [ ] YAML example mentions configured defaults

---

### Phase 3: Update Output and Examples Sections

#### Overview
Update the confirmation output and examples to use configured paths.

#### Changes Required

**File**: `commands/create_sprint.md`

**Change 1**: Line 156 in Step 6 - Update output to reference configured directory

```markdown
**File**: `{sprints.sprints_dir}/${SPRINT_NAME}.yaml` (in the configured sprints directory)
```

#### Success Criteria

**Automated Verification**:
- [ ] File exists: `test -f commands/create_sprint.md`
- [ ] Lint passes: `ruff check scripts/`
- [ ] Types pass: `python -m mypy scripts/little_loops/`

**Manual Verification**:
- [ ] Output section references configured directory

---

## Testing Strategy

### Unit Tests
- No Python code is being modified, so no unit tests needed

### Integration Tests
- N/A - this is a command documentation change

## References

- Original issue: `.issues/enhancements/P4-ENH-137-create-sprint-explicit-config-reading.md`
- Pattern from: `commands/handoff.md:18-23` (Read settings from pattern)
- Pattern from: `commands/create_loop.md:27-45` (Step 0 naming)
