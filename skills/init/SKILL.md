---
description: Initialize little-loops configuration for a project
allowed-tools:
  - Read
  - Glob
  - Write
  - Edit
  - Bash(mkdir:*)
arguments:
  - name: flags
    description: Optional flags (--interactive, --yes, --force)
    required: false
---

# Initialize Configuration

You are tasked with initializing little-loops configuration for a project by creating `.claude/ll-config.json`.

## Arguments

$ARGUMENTS

- **flags** (optional): Command flags
  - `--interactive` - Full guided wizard mode with prompts for each option
  - `--yes` - Accept all defaults without confirmation
  - `--force` - Overwrite existing configuration file

## Process

### 1. Parse Flags

```bash
FLAGS="${flags:-}"
INTERACTIVE=false
YES=false
FORCE=false

if [[ "$FLAGS" == *"--interactive"* ]]; then INTERACTIVE=true; fi
if [[ "$FLAGS" == *"--yes"* ]]; then YES=true; fi
if [[ "$FLAGS" == *"--force"* ]]; then FORCE=true; fi
```

### 2. Check Existing Configuration

Before proceeding, check if `.claude/ll-config.json` already exists:

- If it exists and `--force` was NOT provided:
  - Display warning: "Configuration already exists at .claude/ll-config.json"
  - Suggest: "Use --force to overwrite, or edit the existing file directly"
  - **Stop here** - do not proceed

- If it exists and `--force` WAS provided:
  - Display notice: "Overwriting existing configuration"
  - Continue with initialization

### 3. Detect Project Type

Examine the project root for indicator files:

| File(s) Present | Project Type |
|-----------------|--------------|
| `pyproject.toml`, `setup.py`, or `requirements.txt` | Python |
| `package.json` | Node.js |
| `go.mod` | Go |
| `Cargo.toml` | Rust |
| `pom.xml` or `build.gradle` | Java |
| `*.csproj` or `*.sln` | .NET |
| None of the above | General |

Also detect:
- **Project name**: Use the directory name
- **Source directory**: Look for `src/`, `lib/`, or `app/` directories

### 4. Generate Configuration

Based on detected project type, use the presets from [presets.md](presets.md) to generate the initial configuration.

### 5. Interactive Mode (if --interactive)

If `--interactive` flag is set, follow the interactive wizard flow in [interactive.md](interactive.md) which guides the user through 6-10 rounds of configuration questions.

### 6. Display Summary

```
================================================================================
LITTLE-LOOPS INITIALIZATION
================================================================================

Detected project type: [TYPE]

Configuration Summary:

  [PROJECT]
  project.name:       [name]
  project.src_dir:    [src_dir]
  project.test_dir:   [test_dir]                # Only show if configured
  project.test_cmd:   [test_cmd]
  project.lint_cmd:   [lint_cmd]
  project.type_cmd:   [type_cmd]
  project.format_cmd: [format_cmd]
  project.build_cmd:  [build_cmd]               # Only show if configured
  project.run_cmd:    [run_cmd]                  # Only show if configured

  [ISSUES]
  issues.base_dir:    [base_dir]

  [SCAN]
  scan.focus_dirs:    [focus_dirs]
  scan.exclude_patterns: [exclude_patterns]

  [PARALLEL]                              # Only show if configured
  parallel.worktree_copy_files: [files]

  [CONTEXT MONITOR]                       # Only show if enabled
  context_monitor.enabled: true
  context_monitor.auto_handoff_threshold: [threshold]  # Only if non-default

  [SYNC]                                  # Only show if enabled
  sync.enabled: true
  sync.github.priority_labels: [true/false]    # Only if non-default
  sync.github.sync_completed: [true/false]     # Only if non-default

  [PRODUCT]                               # Only show if enabled
  product.enabled: true
  product.goals_file: .claude/ll-goals.md

  [DOCUMENTS]                             # Only show if enabled
  documents.enabled: true
  documents.categories: [architecture, product]  # List category names

  [CONTINUATION]                          # Only show if configured (non-defaults)
  continuation.auto_detect_on_session_start: [true/false]
  continuation.prompt_expiry_hours: [hours]

  [PROMPT OPTIMIZATION]                   # Only show if configured (non-defaults)
  prompt_optimization.enabled: [true/false]
  prompt_optimization.mode: [quick/thorough]
  prompt_optimization.confirm: [true/false]

================================================================================
```

### 7. Confirm and Create

If `--interactive` flag IS set:
- Skip confirmation and proceed immediately (user has already approved settings through the interactive workflow)

If `--yes` flag IS set:
- Skip confirmation and proceed

Otherwise (neither `--interactive` nor `--yes`):
- Ask: "Create .claude/ll-config.json with these settings? (y/n)"
- Wait for confirmation
- If user declines, abort without changes

### 8. Write Configuration

1. Create `.claude/` directory if it doesn't exist:
   ```bash
   mkdir -p .claude
   ```

2. Write the configuration file with the `$schema` reference:
   ```json
   {
     "$schema": "https://raw.githubusercontent.com/BrennonTWilliams/little-loops/main/config-schema.json",
     "project": { ... },
     "issues": { ... },
     "scan": { ... }
   }
   ```

3. Only include sections with non-default values to keep the file minimal
   - Omit `parallel` section entirely if not configured in interactive mode
   - Omit `context_monitor` section if user selected "No" (disabled is the default)
   - Omit `sync` section entirely if user did not select "GitHub sync" (disabled is the default)
   - Omit `product` section if user selected "No, skip" (disabled is the default)
   - Omit `documents` section if user selected "Skip" (disabled is the default)
   - Omit `continuation` section if all values match schema defaults
   - Omit `prompt_optimization` section if all values match schema defaults

### 9. Update .gitignore

Add little-loops state files to `.gitignore` to prevent committing runtime state:

1. Check if `.gitignore` exists at project root
2. If it doesn't exist, create it with the entries below
3. If it exists, check if entries are already present (to avoid duplicates)
4. Append the following if not already present:

```
# little-loops state files
.auto-manage-state.json
.parallel-manage-state.json
```

**Logic:**
- Read existing `.gitignore` content (if file exists)
- Only add entries that aren't already present (exact line match)
- Add a blank line before the comment header if appending to existing content
- Track whether the file was created or updated for the completion message

### 10. Display Completion Message

```
================================================================================
INITIALIZATION COMPLETE
================================================================================

Created: .claude/ll-config.json
Created: .claude/ll-goals.md (product goals template)  # Only show if product enabled
Updated: .gitignore (added state file exclusions)

Next steps:
  1. Review and customize: .claude/ll-config.json
  2. Try a command: /ll:check_code
  3. Set up issue tracking: mkdir -p {{config.issues.base_dir}}/{bugs,features,enhancements}
  4. Configure product goals: .claude/ll-goals.md      # Only show if product enabled
  5. Run parallel processing: ll-parallel      # Only show if parallel configured
  6. Sync with GitHub: /ll:sync_issues push   # Only show if sync enabled

Documentation: https://github.com/BrennonTWilliams/little-loops

================================================================================
```

---

## Additional Resources

- For project type configuration presets, see [presets.md](presets.md)
- For interactive wizard question flows, see [interactive.md](interactive.md)

## Examples

```bash
# Initialize with smart defaults (detect project type, confirm)
/ll:init

# Initialize with full interactive wizard
/ll:init --interactive

# Initialize accepting all defaults without confirmation
/ll:init --yes

# Overwrite existing configuration
/ll:init --force

# Combine flags
/ll:init --yes --force
```
