---
description: Initialize little-loops configuration for a project
argument-hint: "[flags]"
allowed-tools:
  - Read
  - Glob
  - Write
  - Edit
  - Bash(mkdir:*)
  - Bash(which:*)
arguments:
  - name: flags
    description: Optional flags (--interactive, --yes, --force, --dry-run)
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
  - `--dry-run` - Preview generated configuration without writing files

## Process

### 1. Parse Flags

```bash
FLAGS="${flags:-}"
INTERACTIVE=false
YES=false
FORCE=false
DRY_RUN=false

if [[ "$FLAGS" == *"--interactive"* ]]; then INTERACTIVE=true; fi
if [[ "$FLAGS" == *"--yes"* ]]; then YES=true; fi
if [[ "$FLAGS" == *"--force"* ]]; then FORCE=true; fi
if [[ "$FLAGS" == *"--dry-run"* ]]; then DRY_RUN=true; fi

# Validate: --interactive and --yes are mutually exclusive
if [[ "$INTERACTIVE" == true ]] && [[ "$YES" == true ]]; then
    echo "Error: Cannot combine --interactive and --yes"
    echo "Usage: /ll:init [--interactive | --yes] [--force] [--dry-run]"
    exit 1
fi
```

**Valid flag combinations:**

| Combination | Behavior |
|-------------|----------|
| `--interactive` | Full guided wizard |
| `--yes` | Accept all defaults, no confirmation |
| `--force` | Overwrite existing config |
| `--dry-run` | Preview config without writing files |
| `--interactive --force` | Full wizard, allow overwriting existing config |
| `--yes --force` | Accept defaults, overwrite existing config |
| `--dry-run --force` | Preview what overwrite would produce |
| `--interactive --yes` | **Error** — mutually exclusive |

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

Read all project-type template JSON files from `templates/` (relative to the little-loops plugin directory), excluding `issue-sections.json` and `ll-goals-template.md`. For each template, check `_meta.detect` patterns against files in the project root:

1. For each template file, read its `_meta.detect` array
2. Check if ANY listed indicator file exists in the project root
3. If `_meta.detect_exclude` is present, skip this template if any excluded file also exists
4. If `_meta.detect` is empty (e.g., `generic.json`), this is the fallback template
5. If multiple templates match, prefer the one without `priority: -1`

**Template files** (9 project-type templates):

| Template File | Detect Files | Notes |
|---------------|-------------|-------|
| `python-generic.json` | `pyproject.toml`, `setup.py`, `requirements.txt` | |
| `typescript.json` | `tsconfig.json` | |
| `javascript.json` | `package.json` | exclude: `tsconfig.json` |
| `go.json` | `go.mod` | |
| `rust.json` | `Cargo.toml` | |
| `java-maven.json` | `pom.xml` | |
| `java-gradle.json` | `build.gradle`, `build.gradle.kts` | |
| `dotnet.json` | `*.csproj`, `*.sln`, `*.fsproj` | |
| `generic.json` | _(none — fallback)_ | `priority: -1` |

Also detect:
- **Project name**: Use the directory name
- **Source directory**: Look for `src/`, `lib/`, or `app/` directories

### 4. Generate Configuration

Read the matched template JSON file from Step 3. Extract the `project` and `scan` sections as the initial configuration presets. Also apply the `issues` section as the default issue tracking configuration.

Strip the `_meta`, `$schema`, and `product` sections (product is configured separately in interactive mode).

### 5. Interactive Mode (if --interactive)

If `--interactive` flag is set, follow the interactive wizard flow in [interactive.md](interactive.md) which guides the user through 7-13 rounds of configuration questions, with a progress indicator shown at each step.

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
  issues.completed_dir: [completed_dir]          # Only show if non-default (not "completed")

  [SCAN]
  scan.focus_dirs:    [focus_dirs]
  scan.exclude_patterns: [exclude_patterns]

  [PARALLEL]                              # Only show if configured
  parallel.max_workers: [workers]          # Only show if non-default (not 2)
  parallel.timeout_per_issue: [seconds]    # Only show if non-default (not 3600)
  parallel.worktree_copy_files: [files]

  [CONTEXT MONITOR]                       # Only show if enabled
  context_monitor.enabled: true
  context_monitor.auto_handoff_threshold: [threshold]  # Only if non-default

  [SYNC]                                  # Only show if enabled
  sync.enabled: true
  sync.github.priority_labels: [true/false]    # Only if non-default
  sync.github.sync_completed: [true/false]     # Only if non-default

  [COMMANDS]                              # Only show if pre/post implement configured in Round 8
  commands.pre_implement: [command]        # Only show if configured
  commands.post_implement: [command]       # Only show if configured

  [SPRINTS]                               # Only show if "Sprint management" selected in Round 3b
  sprints.default_max_workers: [workers]  # Only if non-default (not 4)

  [LOOPS]                                 # Only show if "FSM loops" selected in Round 3b
  loops.loops_dir: .loops                 # Always .loops (default)

  [AUTOMATION]                            # Only show if "Sequential automation" selected in Round 3b
  automation.timeout_seconds: [seconds]   # Only if non-default (not 3600)

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

If `--dry-run` flag IS set:
- Skip confirmation (no files will be written)

If `--interactive` flag IS set:
- Skip confirmation and proceed immediately (user has already approved settings through the interactive workflow)

If `--yes` flag IS set:
- Skip confirmation and proceed

Otherwise (neither `--interactive`, `--yes`, nor `--dry-run`):
- Ask: "Create .claude/ll-config.json with these settings? (y/n)"
- Wait for confirmation
- If user declines, abort without changes

### 7.5. Command Availability Check

**Skip this step if** `--yes` or `--dry-run` is set.

After the user confirms, check whether the configured tool commands are available in PATH. This is a **non-blocking** check — display warnings but always proceed to Step 8.

1. Collect configured command values: `test_cmd`, `lint_cmd`, `type_cmd`, `format_cmd`
2. For each non-null command, extract the **base command** (first word). For example:
   - `ruff check .` → `ruff`
   - `python -m pytest` → `python`
   - `go test ./...` → `go`
3. **Deduplicate** base commands (e.g., if `ruff` is used for both lint and format, check it only once)
4. For each unique base command, run via Bash:
   ```bash
   which <base_command> 2>/dev/null
   ```
5. For any command **not found**, display a warning:
   ```
   Warning: '<base_command>' not found in PATH — install it before running /ll:check-code
   ```

   Use this mapping for the warning message:
   | Source field | Suggested skill |
   |-------------|----------------|
   | `test_cmd` | `/ll:run-tests` |
   | `lint_cmd` | `/ll:check-code` |
   | `type_cmd` | `/ll:check-code` |
   | `format_cmd` | `/ll:check-code` |

   If a base command is shared across multiple fields, mention the first matching skill only.

6. **Always proceed** to Step 8 regardless of results.

### 8. Write Configuration

**If `--dry-run` is set**, output a preview instead of writing files:

```
=== DRY RUN: /ll:init ===

--- Configuration Preview (.claude/ll-config.json) ---
{
  "$schema": "https://raw.githubusercontent.com/BrennonTWilliams/little-loops/main/config-schema.json",
  "project": { ... },
  "issues": { ... },
  "scan": { ... }
}

--- Actions that would be taken ---
  [write]  .claude/ll-config.json
  [mkdir]  {{config.issues.base_dir}}/{bugs,features,enhancements,completed}
  [update] .gitignore (add state file exclusions)

=== END DRY RUN (no changes made) ===
```

Skip all Write, Edit, and Bash(mkdir) tool calls. Skip Steps 9 and 10 — the dry-run output above replaces them.

**Otherwise**, proceed with normal file writes:

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

4. Create issue tracking directories:
   ```bash
   mkdir -p {{config.issues.base_dir}}/{bugs,features,enhancements,completed}
   ```

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
.claude/ll-context-state.json
.claude/ll-sync-state.json
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
Created: {{config.issues.base_dir}}/{bugs,features,enhancements,completed}
Updated: .gitignore (added state file exclusions)

Next steps:
  1. Review and customize: .claude/ll-config.json
  2. Try a command: /ll:check-code
  3. Configure product goals: .claude/ll-goals.md      # Only show if product enabled
  4. Run parallel processing: ll-parallel      # Only show if parallel configured
  5. Sync with GitHub: /ll:sync-issues push   # Only show if sync enabled
  6. Run sprint processing: ll-sprint run [sprint-file]   # Only show if sprint management selected
  7. Run FSM loop: ll-loop run [loop-file]               # Only show if FSM loops selected
  8. Run sequential automation: ll-auto                  # Only show if sequential automation selected

Additional settings for sprints, loops, and automation can be customized via:
  /ll:configure                                          # Only show if any automation feature selected

Documentation: https://github.com/BrennonTWilliams/little-loops

================================================================================
```

---

## Additional Resources

- For project type configuration presets, see `templates/*.json` (relative to the little-loops plugin directory)
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

# Preview what init would generate without writing files
/ll:init --dry-run

# Combine flags
/ll:init --yes --force
/ll:init --interactive --force
/ll:init --dry-run --force

# Invalid: --interactive and --yes are mutually exclusive
# /ll:init --interactive --yes  → Error
```
