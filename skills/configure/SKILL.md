---
description: Interactively configure specific areas in ll-config.json
argument-hint: "[area]"
allowed-tools:
  - Read
  - Edit
  - AskUserQuestion
  - Bash(mkdir:*)
  - Bash(python3:*)
  - Bash(pip:*)
arguments:
  - name: area
    description: "project|issues|commands|parallel|automation|documents|continuation|context|prompt|scan|sync|allowed-tools|hooks (optional - prompts if omitted)"
    required: false
  - name: flags
    description: Optional flags (--list, --show, --reset)
    required: false
---

# Configure

<!-- PLUGIN_VERSION: 1.66.0 -->

Interactively configure specific areas of `.ll/ll-config.json` without re-running the full `/ll:init` wizard.

## Configuration

Settings are stored in `.ll/ll-config.json`. See `config-schema.json` for default values and validation rules.

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

### 1.5. Pip Package Check

**Skip this step if** `LIST_MODE`, `SHOW_MODE`, or `RESET_MODE` is `true` (these modes are informational or destructive, not configuration sessions where a version mismatch matters).

Check whether the installed `little-loops` pip package is aligned with this plugin version. This is a **non-blocking** check — display warnings but always proceed. Since configure has no `--yes` flag, this check is always interactive.

1. Read the `PLUGIN_VERSION` from the `<!-- PLUGIN_VERSION: X.Y.Z -->` comment near the top of this file.

2. Detect the installed package version:
   ```bash
   python3 -c "import importlib.metadata; print(importlib.metadata.version('little-loops'))" 2>/dev/null
   ```

3. Evaluate the result:
   - If the command fails (package not installed):
     ```
     Warning: 'little-loops' pip package not installed — ll-* CLI tools unavailable
     Install: pip install -e "./scripts"
     ```
     Always proceed.
   - If installed and versions match → no output (silent success).
   - If installed and versions differ:
     - Determine install command:
       ```bash
       [ -d "./scripts" ] && INSTALL_CMD="pip install -e './scripts'" || INSTALL_CMD="pip install --upgrade little-loops"
       ```
     - Use `AskUserQuestion`:
       ```
       The installed little-loops package (X.Y.Z) is out of date (plugin: A.B.C).
       Update now?
       Options: Yes / No
       ```
     - If user confirms: run `$INSTALL_CMD` via Bash
       - On success: `✓ little-loops updated to A.B.C`
       - On failure: `Warning: pip package update failed — run manually: $INSTALL_CMD`
     - If user declines: `Warning: pip package version mismatch — run: $INSTALL_CMD`

**Always proceed to Step 2 regardless of results.**

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
| `commands` | `commands` | Command hooks, confidence gate |
| `scan` | `scan` | Focus dirs, exclude patterns |
| `sync` | `sync` | GitHub Issues sync: enabled, label mapping, priorities |
| `allowed-tools` | `permissions.allow` in `.claude/settings.json` or `.claude/settings.local.json` | ll- CLI tool allow entries (Note: writes to Claude Code settings files, not ll-config.json) |
| `hooks` | `hooks` in `.claude/settings.json` or `.claude/settings.local.json` | ll- lifecycle hook configuration (Note: writes to Claude Code settings files, not ll-config.json) |

---

## Mode: --list

If `--list` flag is set, display all configuration areas with their status.

Read `.ll/ll-config.json` and check which sections are configured (vs using defaults).

Output format:

```
Configuration Areas
-------------------
  project       [CONFIGURED]  Test, lint, format, type-check, build commands
  issues        [CONFIGURED]  Base dir, categories, templates, capture style
  parallel      [DEFAULT]     ll-parallel: workers, timeouts, worktree files
  automation    [DEFAULT]     ll-auto: workers, timeouts, streaming
  commands      [DEFAULT]     Command hooks, confidence gate
  documents     [CONFIGURED]  Key document categories for issue alignment
  continuation  [DEFAULT]     Session handoff: auto-detect, includes, expiry
  context       [CONFIGURED]  Context monitoring: threshold, limits
  prompt        [DEFAULT]     Prompt optimization: mode, confirm, bypass
  scan          [CONFIGURED]  Focus dirs, exclude patterns
  sync          [DEFAULT]     GitHub Issues sync: enabled, label mapping, priorities
  allowed-tools [DEFAULT]     ll- CLI tool allow entries in settings.json/settings.local.json
  hooks         [DEFAULT]     ll- hook configuration in settings.json/settings.local.json

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

1. Read `.ll/ll-config.json`
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
        description: "Show commands, parallel, automation, documents, continuation, context, prompt"
```

If "More areas..." selected:

```yaml
questions:
  - question: "Which additional area do you want to configure?"
    header: "Area"
    multiSelect: false
    options:
      - label: "commands"
        description: "Command hooks, confidence gate"
      - label: "parallel"
        description: "ll-parallel: workers, timeouts, worktree files"
      - label: "automation"
        description: "ll-auto: workers, timeouts, streaming"
      - label: "More areas..."
        description: "Show documents, sync, continuation, context, prompt"
```

If "More areas..." selected again:

```yaml
questions:
  - question: "Which area do you want to configure?"
    header: "Area"
    multiSelect: false
    options:
      - label: "documents"
        description: "Key document categories for issue alignment"
      - label: "sync"
        description: "GitHub Issues sync: enabled, label mapping, priorities"
      - label: "continuation"
        description: "Session handoff: auto-detect, includes, expiry"
      - label: "More areas..."
        description: "Show context, prompt, hooks"
```

If "More areas..." selected again:

```yaml
questions:
  - question: "Which area do you want to configure?"
    header: "Area"
    multiSelect: false
    options:
      - label: "context"
        description: "Context monitoring: threshold, limits"
      - label: "prompt"
        description: "Prompt optimization: mode, confirm, bypass"
      - label: "allowed-tools"
        description: "ll- CLI tool allow entries in settings.json/settings.local.json"
      - label: "hooks"
        description: "ll- lifecycle hook configuration in settings.json/settings.local.json"
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

1. Read existing `.ll/ll-config.json`
2. Merge changes into the appropriate section
3. **Minimal write rule**: If a value matches the schema default, remove it from config
4. If a section becomes empty after removing defaults, remove the section
5. Preserve `$schema` reference
6. Write updated config

Output on success:

```
Configuration updated: .ll/ll-config.json

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
  - `commands` - Command hooks, confidence gate
  - `parallel` - ll-parallel: workers, timeouts, worktree files
  - `automation` - ll-auto: workers, timeouts, streaming
  - `documents` - Key document categories for issue alignment
  - `continuation` - Session handoff: auto-detect, includes, expiry
  - `context` - Context monitoring: threshold, limits
  - `prompt` - Prompt optimization: mode, confirm, bypass
  - `scan` - Focus dirs, exclude patterns
  - `sync` - GitHub Issues sync: enabled, label mapping, priorities
  - `allowed-tools` - ll- CLI tool allow entries in settings.json/settings.local.json
  - `hooks` - ll- lifecycle hook configuration in settings.json/settings.local.json

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

Changes take effect immediately. Commands that read from `.ll/ll-config.json` will use the updated values.

Related commands:
- `/ll:init` - Full interactive initialization wizard
- `/ll:toggle-autoprompt` - Quick toggle for prompt optimization settings
