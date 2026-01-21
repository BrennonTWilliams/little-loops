# FEAT-102: Add /ll:configure command - Implementation Plan

## Issue Reference
- **File**: `.issues/features/P3-FEAT-102-configure-command-interactive-config.md`
- **Type**: feature
- **Priority**: P3
- **Action**: implement

## Current State Analysis

### Key Discoveries
- `toggle_autoprompt.md:1-7` - Command frontmatter pattern with setting argument
- `init.md:200-247` - AskUserQuestion grouped questions pattern (up to 4 per call)
- `config-schema.json:12-499` - All 10 configurable areas with defaults and validation
- `.claude/ll-config.json` - Example of minimal config (only non-defaults stored)

### Existing Patterns
- Commands use `${var:-default}` for argument parsing
- Config sections map directly to schema sections
- `AskUserQuestion` supports `multiSelect: true` for multi-select options
- Config writes should only include non-default values

## Desired End State

A `/ll:configure` command that allows targeted interactive configuration of any config area without re-running the full init wizard.

### How to Verify
- `/ll:configure` prompts for area selection
- `/ll:configure project` runs interactive config for project settings
- `/ll:configure --list` shows all areas with their status
- `/ll:configure project --show` displays current project settings
- `/ll:configure project --reset` removes the project section

## What We're NOT Doing

- Not modifying the init command - that remains the full wizard
- Not adding new config sections - only exposing existing ones
- Not changing config-schema.json - using existing schema
- Not adding Python code - this is a pure command file

## Solution Approach

Create `commands/configure.md` following the patterns from `toggle_autoprompt.md` (argument parsing, config modification) and `init.md` (AskUserQuestion for interactive input).

The command will:
1. Parse arguments to determine mode (area/flags)
2. For `--list`: Display all areas with configured status
3. For `--show`: Display current settings for an area
4. For `--reset`: Remove the section from config
5. For area selection: Use AskUserQuestion for interactive configuration

## Implementation Phases

### Phase 1: Command Frontmatter and Argument Parsing

#### Overview
Create the command file with proper frontmatter and argument parsing logic.

#### Changes Required

**File**: `commands/configure.md` (NEW)
**Changes**: Create file with frontmatter and parsing

```yaml
---
description: Interactively configure specific areas in ll-config.json
arguments:
  - name: area
    description: "project|issues|parallel|automation|documents|continuation|context|prompt|scan|workflow (optional - prompts if omitted)"
    required: false
  - name: flags
    description: Optional flags (--list, --show, --reset)
    required: false
---
```

Argument parsing:
```bash
AREA="${area:-}"
FLAGS="${flags:-}"

LIST_MODE=false
SHOW_MODE=false
RESET_MODE=false

if [[ "$FLAGS" == *"--list"* ]]; then LIST_MODE=true; fi
if [[ "$FLAGS" == *"--show"* ]]; then SHOW_MODE=true; fi
if [[ "$FLAGS" == *"--reset"* ]]; then RESET_MODE=true; fi
```

#### Success Criteria

**Automated Verification**:
- [ ] File exists at `commands/configure.md`
- [ ] Lint passes: `ruff check scripts/`

---

### Phase 2: Area Mapping and --list Mode

#### Overview
Define the mapping between argument names and config sections, implement `--list` mode.

#### Changes Required

**File**: `commands/configure.md`
**Changes**: Add area mapping and list display

Area mapping table:
| Argument | Config Section | Description |
|----------|----------------|-------------|
| `project` | `project` | Test, lint, format, type-check, build commands |
| `issues` | `issues` | Base dir, categories, templates, capture style |
| `parallel` | `parallel` | ll-parallel: workers, timeouts, worktree files |
| `automation` | `automation` | ll-auto: workers, timeouts, streaming |
| `documents` | `documents` | Key document categories for issue alignment |
| `continuation` | `continuation` | Session handoff: auto-detect, includes, expiry |
| `context` | `context_monitor` | Context monitoring: threshold, limits |
| `prompt` | `prompt_optimization` | Prompt optimization: mode, confirm, bypass |
| `scan` | `scan` | Focus dirs, exclude patterns |
| `workflow` | `workflow` | Phase gates, deep research settings |

`--list` output format:
```
Configuration Areas
-------------------
  project       [CONFIGURED]  Test, lint, format, type-check, build commands
  issues        [CONFIGURED]  Base dir, categories, templates, capture style
  parallel      [DEFAULT]     ll-parallel: workers, timeouts, worktree files
  automation    [DEFAULT]     ll-auto: workers, timeouts, streaming
  documents     [CONFIGURED]  Key document categories for issue alignment
  continuation  [DEFAULT]     Session handoff: auto-detect, includes, expiry
  context       [CONFIGURED]  Context monitoring: threshold, limits
  prompt        [DEFAULT]     Prompt optimization: mode, confirm, bypass
  scan          [CONFIGURED]  Focus dirs, exclude patterns
  workflow      [DEFAULT]     Phase gates, deep research settings

Configure: /ll:configure <area>
Show:      /ll:configure <area> --show
Reset:     /ll:configure <area> --reset
```

#### Success Criteria

**Automated Verification**:
- [ ] Command handles `--list` flag correctly

---

### Phase 3: --show Mode

#### Overview
Display current configuration values for a specific area.

#### Changes Required

**File**: `commands/configure.md`
**Changes**: Add show mode logic

For each area, display current values using template syntax `{{config.section.key}}` or indicate if using defaults:

Example output for `project`:
```
Project Configuration
---------------------
  name:       {{config.project.name}} (or directory name)
  src_dir:    {{config.project.src_dir}} (default: src/)
  test_dir:   {{config.project.test_dir}} (default: tests)
  test_cmd:   {{config.project.test_cmd}} (default: pytest)
  lint_cmd:   {{config.project.lint_cmd}} (default: ruff check .)
  type_cmd:   {{config.project.type_cmd}} (default: mypy)
  format_cmd: {{config.project.format_cmd}} (default: ruff format .)
  build_cmd:  {{config.project.build_cmd}} (default: none)

Edit: /ll:configure project
```

#### Success Criteria

**Automated Verification**:
- [ ] Command handles `--show` flag with area argument

---

### Phase 4: --reset Mode

#### Overview
Remove a configuration section to revert to defaults.

#### Changes Required

**File**: `commands/configure.md`
**Changes**: Add reset mode logic

Reset behavior:
1. Read current `.claude/ll-config.json`
2. Remove the specified section
3. Write updated config back
4. Display confirmation

Output format:
```
Reset: [area] section removed from configuration
       Now using schema defaults

View defaults: /ll:configure [area] --show
```

#### Success Criteria

**Automated Verification**:
- [ ] Command handles `--reset` flag with area argument

---

### Phase 5: Interactive Area Selection (No Args)

#### Overview
When no area is specified, use AskUserQuestion to let user select an area.

#### Changes Required

**File**: `commands/configure.md`
**Changes**: Add interactive area selection

Group areas into 4+4+2 for manageable selection:

```yaml
questions:
  - question: "Which configuration area do you want to modify?"
    header: "Area"
    multiSelect: false
    options:
      - label: "project"
        description: "Test, lint, format, type-check, build commands"
      - label: "issues"
        description: "Base dir, categories, templates, capture style"
      - label: "scan"
        description: "Focus dirs, exclude patterns"
      - label: "More options..."
        description: "Show additional configuration areas"
```

If "More options..." selected, show second question with remaining areas.

#### Success Criteria

**Automated Verification**:
- [ ] Command prompts for area when none specified

---

### Phase 6: Interactive Configuration for Each Area

#### Overview
Implement interactive configuration flows for each of the 10 areas.

#### Changes Required

**File**: `commands/configure.md`
**Changes**: Add per-area interactive flows

Each area will have:
1. Current value display (from config or defaults)
2. 1-2 question rounds using AskUserQuestion
3. Preview of changes before writing
4. Config file update with only non-default values

Example for `project` area:
```yaml
questions:
  - header: "Test cmd"
    question: "Which test command should be used?"
    options:
      - label: "{{current_value}}"
        description: "Keep current setting"
      - label: "pytest"
        description: "Python pytest"
      - label: "python -m pytest"
        description: "Python module mode"
    multiSelect: false

  - header: "Lint cmd"
    question: "Which lint command should be used?"
    options:
      - label: "{{current_value}}"
        description: "Keep current setting"
      - label: "ruff check ."
        description: "Ruff linter"
      - label: "flake8"
        description: "Flake8 linter"
    multiSelect: false
```

#### Area-Specific Questions

**project** (2 rounds):
- Round 1: name, src_dir, test_dir, test_cmd
- Round 2: lint_cmd, type_cmd, format_cmd, build_cmd

**issues** (1 round):
- base_dir, completed_dir, capture_template (3 questions)

**parallel** (1 round):
- max_workers, timeout_per_issue, worktree_copy_files, stream_subprocess_output (4 questions)

**automation** (1 round):
- timeout_seconds, max_workers, stream_output (3 questions)

**documents** (1-2 rounds):
- enabled, then if enabled: category management

**continuation** (1 round):
- auto_detect, include_todos/git_status/recent_files (multi-select), prompt_expiry_hours (3 questions)

**context** (1 round):
- enabled, auto_handoff_threshold, context_limit_estimate (3 questions)

**prompt** (1 round):
- enabled, mode, confirm, clarity_threshold (4 questions)

**scan** (1 round):
- focus_dirs, exclude_patterns (2 questions)

**workflow** (1 round):
- phase_gates.enabled, deep_research.enabled, deep_research.agents (3 questions)

#### Success Criteria

**Automated Verification**:
- [ ] Lint passes: `ruff check scripts/`
- [ ] Types pass: `python -m mypy scripts/little_loops/`

**Manual Verification**:
- [ ] `/ll:configure project` shows current values and allows changes
- [ ] Changes are correctly written to config file

---

### Phase 7: Config Writing and Diff Display

#### Overview
Show what will change before writing and implement minimal writes.

#### Changes Required

**File**: `commands/configure.md`
**Changes**: Add diff display and write logic

Before writing, display diff:
```
Changes to apply:
-----------------
  project.test_cmd: "pytest" -> "python -m pytest"
  project.lint_cmd: (unchanged)

Apply changes? [Y/n]
```

Write rules:
1. Read existing config
2. Merge changes into the section
3. If all values in section match defaults, remove section
4. Write updated config preserving other sections
5. Preserve `$schema` reference

#### Success Criteria

**Automated Verification**:
- [ ] Config file is valid JSON after write
- [ ] Other sections are preserved during write

---

## Testing Strategy

### Manual Tests
1. `/ll:configure --list` - Shows all areas with status
2. `/ll:configure project --show` - Shows project settings
3. `/ll:configure project` - Runs interactive project config
4. `/ll:configure context --reset` - Resets context_monitor section
5. `/ll:configure` (no args) - Prompts for area selection

### Verification Commands
- `ruff check scripts/` - Lint
- `python -m mypy scripts/little_loops/` - Type check
- Manual review of config file after changes

## References

- Original issue: `.issues/features/P3-FEAT-102-configure-command-interactive-config.md`
- Pattern reference: `commands/toggle_autoprompt.md:1-157`
- AskUserQuestion pattern: `commands/init.md:200-247`
- Config schema: `config-schema.json:1-502`
