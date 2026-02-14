---
description: Interactively configure specific areas in ll-config.json
disable-model-invocation: true
argument-hint: "[area]"
allowed-tools:
  - Read
  - Edit
  - Bash(mkdir:*)
arguments:
  - name: area
    description: "project|issues|parallel|automation|documents|continuation|context|prompt|scan|sync (optional - prompts if omitted)"
    required: false
  - name: flags
    description: Optional flags (--list, --show, --reset)
    required: false
---

# Configure

Interactively configure specific areas of `.claude/ll-config.json` without re-running the full `/ll:init` wizard.

## Configuration

Settings are stored in `.claude/ll-config.json`. See `config-schema.json` for default values and validation rules.

## Process

### 1. Parse Arguments

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

### 2. Area Mapping

Map argument names to config sections:

| Argument | Config Section | Description |
|----------|----------------|-------------|
| `project` | `project` | Test, lint, format, type-check, build, run commands |
| `issues` | `issues` | Base dir, categories, templates, capture style |
| `parallel` | `parallel` | ll-parallel: workers, timeouts, worktree files |
| `automation` | `automation` | ll-auto: workers, timeouts, streaming |
| `documents` | `documents` | Key document categories for issue alignment |
| `continuation` | `continuation` | Session handoff: auto-detect, includes, expiry |
| `context` | `context_monitor` | Context monitoring: threshold, limits |
| `prompt` | `prompt_optimization` | Prompt optimization: mode, confirm, bypass |
| `scan` | `scan` | Focus dirs, exclude patterns |
| `sync` | `sync` | GitHub Issues sync: enabled, label mapping, priorities |

---

## Mode: --list

If `--list` flag is set, display all configuration areas with their status.

Read `.claude/ll-config.json` and check which sections are configured (vs using defaults).

Output format:

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
  sync          [DEFAULT]     GitHub Issues sync: enabled, label mapping, priorities

Configure: /ll:configure <area>
Show:      /ll:configure <area> --show
Reset:     /ll:configure <area> --reset
```

Mark as `[CONFIGURED]` if the section exists in the config file with any keys.
Mark as `[DEFAULT]` if the section is absent (using schema defaults).

**Stop here if --list mode.**

---

## Mode: --show

If `--show` flag is set with an area, display current values for that area.

Validate area argument - if invalid, show error and list valid areas.

For detailed output formats for each area, see [show-output.md](show-output.md).

**Stop here if --show mode.**

---

## Mode: --reset

If `--reset` flag is set with an area, remove the section from config.

1. Read `.claude/ll-config.json`
2. Delete the mapped config section (e.g., `context` → delete `context_monitor`)
3. Write updated config back (preserving `$schema` and other sections)
4. Display confirmation

Output:

```
Reset: [area] section removed from configuration
       Now using schema defaults

View defaults: /ll:configure [area] --show
```

**Stop here if --reset mode.**

---

## Mode: Interactive (No Flags)

### Step 1: Area Selection

If no area argument provided, use AskUserQuestion to let user select.

**IMPORTANT**: Group areas logically. Show 4 at a time with "More..." option.

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
      - label: "More areas..."
        description: "Show parallel, automation, documents, continuation, context, prompt"
```

If "More areas..." selected:

```yaml
questions:
  - question: "Which additional area do you want to configure?"
    header: "Area"
    multiSelect: false
    options:
      - label: "parallel"
        description: "ll-parallel: workers, timeouts, worktree files"
      - label: "automation"
        description: "ll-auto: workers, timeouts, streaming"
      - label: "documents"
        description: "Key document categories for issue alignment"
      - label: "More areas..."
        description: "Show sync, continuation, context, prompt"
```

If "More areas..." selected again:

```yaml
questions:
  - question: "Which area do you want to configure?"
    header: "Area"
    multiSelect: false
    options:
      - label: "sync"
        description: "GitHub Issues sync: enabled, label mapping, priorities"
      - label: "continuation"
        description: "Session handoff: auto-detect, includes, expiry"
      - label: "context"
        description: "Context monitoring: threshold, limits"
      - label: "prompt"
        description: "Prompt optimization: mode, confirm, bypass"
```

### Step 2: Interactive Configuration

Based on selected area, run the appropriate interactive flow.

For detailed area-specific configuration flows, see [areas.md](areas.md).

### Step 3: Show Changes

After collecting responses, display what will change:

```
Changes to apply:
-----------------
  [section].[key]: "[old_value]" -> "[new_value]"
  [section].[key]: "[old_value]" -> "[new_value]"
  ...

Apply changes? [Y/n]
```

If no changes selected (all "keep" options), display:

```
No changes selected. Configuration unchanged.
```

### Step 4: Update Config

1. Read existing `.claude/ll-config.json`
2. Merge changes into the appropriate section
3. **Minimal write rule**: If a value matches the schema default, remove it from config
4. If a section becomes empty after removing defaults, remove the section
5. Preserve `$schema` reference
6. Write updated config

Output on success:

```
Configuration updated: .claude/ll-config.json

Changes applied:
  [section].[key]: [new_value]

View: /ll:configure [area] --show
```

---

## Arguments

$ARGUMENTS

- **area** (optional): Configuration area to modify
  - `project` - Test, lint, format, type-check, build commands
  - `issues` - Base dir, categories, templates, capture style
  - `parallel` - ll-parallel: workers, timeouts, worktree files
  - `automation` - ll-auto: workers, timeouts, streaming
  - `documents` - Key document categories for issue alignment
  - `continuation` - Session handoff: auto-detect, includes, expiry
  - `context` - Context monitoring: threshold, limits
  - `prompt` - Prompt optimization: mode, confirm, bypass
  - `scan` - Focus dirs, exclude patterns
  - `sync` - GitHub Issues sync: enabled, label mapping, priorities

- **flags** (optional): Command behavior flags
  - `--list` - Display all configuration areas with status
  - `--show` - Display current values for specified area
  - `--reset` - Remove section from config, reverting to defaults

---

## Examples

```bash
# List all configuration areas with status
/ll:configure --list

# Show current project configuration
/ll:configure project --show

# Interactively configure project settings
/ll:configure project

# Reset context_monitor to defaults
/ll:configure context --reset

# No args - select area interactively
/ll:configure
```

---

## Integration

Changes take effect immediately. Commands that read from `.claude/ll-config.json` will use the updated values.

Related commands:
- `/ll:init` - Full interactive initialization wizard
- `/ll:toggle-autoprompt` - Quick toggle for prompt optimization settings
