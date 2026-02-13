---
description: Toggle automatic prompt optimization settings
allowed-tools:
  - Read
  - Edit
arguments:
  - name: setting
    description: "enabled|mode|confirm|status (default: status)"
    required: false
---

# Toggle Autoprompt

Configure automatic prompt optimization behavior. The optimization hook analyzes prompts for clarity and enhances vague prompts with codebase-aware context.

## Configuration

Settings are stored in `.claude/ll-config.json` under `prompt_optimization`:

| Setting | Values | Description |
|---------|--------|-------------|
| `enabled` | ON/OFF | Enable/disable auto-optimization |
| `mode` | quick/thorough | Quick uses config only; thorough spawns agent |
| `confirm` | ON/OFF | Show diff before applying vs auto-apply |

## Process

### 1. Parse Argument

```bash
SETTING="${setting:-status}"
```

### 2. Handle Setting

#### status (default)
Display current settings from config:

```
Autoprompt Settings
-------------------
  enabled:  [ON|OFF]   (auto-optimize vague prompts)
  mode:     [quick|thorough]
  confirm:  [ON|OFF]   (show diff before applying)

Bypass: Start prompt with '*' to skip optimization
Toggle: /ll:toggle_autoprompt [enabled|mode|confirm]
```

#### enabled
Toggle `prompt_optimization.enabled` between true/false.

Output: `Autoprompt: [ENABLED|DISABLED]`

#### mode
Toggle `prompt_optimization.mode` between "quick" and "thorough".

Output: `Mode: [quick|thorough] - [description]`

#### confirm
Toggle `prompt_optimization.confirm` between true/false.

Output: `Confirm: [ON|OFF] - [description]`

### 3. Update Config

When toggling, update `.claude/ll-config.json` with the new value.

---

## Settings Details

### enabled (ON/OFF)

- **ON**: Hook analyzes every prompt for clarity
- **OFF**: All prompts pass through unchanged

When disabled, prompts are never optimized automatically. Users can always re-enable with `/ll:toggle_autoprompt enabled`.

### mode (quick/thorough)

- **quick** (default): Uses project config and reference files only (~2s)
  - Reads `.claude/ll-config.json` for project settings
  - Checks CLAUDE.md, CONTRIBUTING.md, README.md
  - Fast, suitable for most prompts

- **thorough**: Spawns `prompt-optimizer` agent for deep analysis (~10-20s)
  - Searches codebase for relevant files
  - Identifies patterns and conventions
  - Adds specific file:line references
  - Best for complex implementation tasks

### confirm (ON/OFF)

- **ON** (default): Show interactive diff before applying
  ```
  ORIGINAL: fix the bug
  OPTIMIZED: Fix the authentication bug in src/auth/...

  Apply? [Y/n/edit]:
  ```

- **OFF**: Auto-apply optimized prompt without confirmation
  - Faster workflow
  - Trust the optimization
  - Still shows what was applied

---

## Bypass

Start any prompt with `*` to skip optimization entirely:

```
* just quickly add a console.log
```

Other automatic bypasses:
- `/` - Slash commands
- `#` - Memory/note mode
- `?` - Questions
- Short prompts (<10 chars)

---

## Arguments

$ARGUMENTS

- **setting** (optional, default: `status`): Setting to toggle
  - `status` - Display current settings
  - `enabled` - Toggle auto-optimization on/off
  - `mode` - Toggle between quick and thorough mode
  - `confirm` - Toggle confirmation prompts on/off

---

## Examples

```bash
# Show current status
/ll:toggle_autoprompt

# Disable auto-optimization
/ll:toggle_autoprompt enabled
# Output: Autoprompt: DISABLED

# Enable again
/ll:toggle_autoprompt enabled
# Output: Autoprompt: ENABLED

# Switch to thorough mode (uses agent)
/ll:toggle_autoprompt mode
# Output: Mode: thorough (spawns agent for deep codebase analysis)

# Switch back to quick mode
/ll:toggle_autoprompt mode
# Output: Mode: quick (uses config only)

# Disable confirmation prompts
/ll:toggle_autoprompt confirm
# Output: Confirm: OFF (auto-apply optimized prompts)
```

---

## Integration

This command modifies `.claude/ll-config.json`. Changes take effect immediately for all subsequent prompts in the session.

The optimization hook (`optimize-prompt-hook.md`) reads these settings on every prompt submission.
