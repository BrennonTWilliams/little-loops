---
description: Initialize little-loops configuration for a project
argument-hint: "[flags]"
allowed-tools:
  - Read
  - Glob
  - Write
  - Edit
  - AskUserQuestion
  - Bash(mkdir:*)
  - Bash(which:*)
  - Bash(python3:*)
  - Bash(pip:*)
arguments:
  - name: flags
    description: Optional flags (--interactive, --yes, --force, --dry-run)
    required: false
---

# Initialize Configuration

<!-- PLUGIN_VERSION: 1.66.0 -->

You are tasked with initializing little-loops configuration for a project by creating `.ll/ll-config.json`.

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

Before proceeding, check if `.ll/ll-config.json` already exists:

- If it exists and `--force` was NOT provided:
  - Display warning: "Configuration already exists at .ll/ll-config.json"
  - Suggest: "Use --force to overwrite, or edit the existing file directly"
  - **Stop here** - do not proceed

- If it exists and `--force` WAS provided:
  - Display notice: "Overwriting existing configuration"
  - Continue with initialization

### 3. Detect Project Type

Read all project-type template JSON files from `templates/` (relative to the little-loops plugin directory), excluding `bug-sections.json`, `feat-sections.json`, `enh-sections.json`, and `ll-goals-template.md`. For each template, check `_meta.detect` patterns against files in the project root:

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

If `--interactive` flag is set, follow the interactive wizard flow in [interactive.md](interactive.md) which guides the user through 6–7 rounds of configuration questions, with a progress indicator shown at each step.

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
  sprints.default_max_workers: [workers]  # Only if non-default (not 2)

  [LOOPS]                                 # Only show if "FSM loops" selected in Round 3b
  loops.loops_dir: .loops                 # Always .loops (default)

  [AUTOMATION]                            # Only show if "Sequential automation" selected in Round 3b
  automation.timeout_seconds: [seconds]   # Only if non-default (not 3600)

  [PRODUCT]                               # Only show if enabled
  product.enabled: true
  product.goals_file: .ll/ll-goals.md

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
- Ask: "Create .ll/ll-config.json with these settings? (y/n)"
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

--- Configuration Preview (.ll/ll-config.json) ---
{
  "$schema": "https://raw.githubusercontent.com/BrennonTWilliams/little-loops/main/config-schema.json",
  "project": { ... },
  "issues": { ... },
  "scan": { ... }
}

--- Actions that would be taken ---
  [write]  .ll/ll-config.json
  [mkdir]  {{config.issues.base_dir}}/{bugs,features,enhancements,completed,deferred}
  [update] .gitignore (add state file exclusions)
  [update] .claude/settings.local.json (add ll- CLI tool permissions)  # Only if user opts in
  [write]  .claude/CLAUDE.md (ll- CLI command documentation)        # Only if opted in + no existing file
  [update] .claude/CLAUDE.md (append ## little-loops CLI Commands)  # Only if opted in + existing file

=== END DRY RUN (no changes made) ===
```

Skip all Write, Edit, and Bash(mkdir) tool calls. Skip Steps 9, 10, 11, and 12 — the dry-run output above replaces them.

**Otherwise**, proceed with normal file writes:

1. Create `.ll/` directory if it doesn't exist:
   ```bash
   mkdir -p .ll
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
   mkdir -p {{config.issues.base_dir}}/{bugs,features,enhancements,completed,deferred}
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
.ll/ll-context-state.json
.ll/ll-sync-state.json
```

**Logic:**
- Read existing `.gitignore` content (if file exists)
- Only add entries that aren't already present (exact line match)
- Add a blank line before the comment header if appending to existing content
- Track whether the file was created or updated for the completion message

### 9.5. Hook Dependency Validation

**Skip this step if** `--dry-run` is set.

After config is written, validate that hook script runtime dependencies are available and the pip package is version-aligned with the plugin. This is a **non-blocking** check — display warnings but always proceed to Step 10.

Run the following checks via Bash:

1. **jq available** (required by all hook scripts):
   ```bash
   which jq 2>/dev/null
   ```
   If not found:
   ```
   Warning: 'jq' not found in PATH — hook scripts (context-monitor, session-start, etc.) will fail silently
   Install: https://stedolan.github.io/jq/download/
   ```

2. **python3 available** (required by session-start.sh):
   ```bash
   which python3 2>/dev/null
   ```
   If not found:
   ```
   Warning: 'python3' not found in PATH — session-start.sh will fail silently
   ```

3. **pyyaml installed** (required by session-start.sh config merge):
   ```bash
   python3 -c "import yaml" 2>/dev/null
   ```
   If import fails:
   ```
   Warning: 'pyyaml' not installed — session-start.sh will fail silently
   Install: pip install pyyaml
   ```

4. **little_loops pip package installed and version-aligned**:
   ```bash
   python3 -c "import importlib.metadata; print(importlib.metadata.version('little-loops'))" 2>/dev/null
   ```
   - If the command fails → warn: `'little-loops' pip package not installed — ll-* CLI tools unavailable. Install: pip install -e "./scripts"`
   - If installed → compare returned version against the `PLUGIN_VERSION` embedded in this skill (the `<!-- PLUGIN_VERSION: X.Y.Z -->` comment near the top, updated at each release alongside plugin.json, pyproject.toml, `__init__.py`, and CHANGELOG.md)
   - If versions differ:
     - Determine install command:
       ```bash
       [ -d "./scripts" ] && INSTALL_CMD="pip install -e './scripts'" || INSTALL_CMD="pip install --upgrade little-loops"
       ```
     - If `$YES == true` (auto mode): run `$INSTALL_CMD` via Bash
       - On success: `✓ little-loops updated to A.B.C`
       - On failure: `Warning: pip package update failed — run manually: $INSTALL_CMD`
     - Otherwise (interactive mode): use `AskUserQuestion`:
       ```
       The installed little-loops package (X.Y.Z) is out of date (plugin: A.B.C).
       Update now?
       Options: Yes / No
       ```
       - If user confirms: run `$INSTALL_CMD`; report success/failure as above
       - If user declines: `Warning: pip package version mismatch — run: $INSTALL_CMD`
   - If versions match → no output (silent success)

**Always proceed to Step 10 regardless of results.**

### 10. Update Allowed Tools

Add ll- CLI command allow entries to Claude Code's settings file to pre-authorize them for agent use.

**If `--dry-run` is set, skip this step** (already shown in dry-run preview).

1. Check which settings files exist:

   ```bash
   SETTINGS_JSON_EXISTS=false
   SETTINGS_LOCAL_EXISTS=false
   [ -f ".claude/settings.json" ] && SETTINGS_JSON_EXISTS=true
   [ -f ".claude/settings.local.json" ] && SETTINGS_LOCAL_EXISTS=true
   ```

2. Determine target file:
   - **`--yes` mode**: use `.claude/settings.local.json` (create if absent) without prompting
   - **`--interactive` mode**: use the choice recorded in Round 11 of the wizard
   - **Otherwise**, use `AskUserQuestion` inline:
     - If *neither* exists → ask: "Create `.claude/settings.local.json` (Recommended), `.claude/settings.json`, or Skip?"
     - If only `settings.local.json` exists → ask: "Update `.claude/settings.local.json` with ll- entries? (y/Skip)"
     - If only `settings.json` exists → ask: "Update `.claude/settings.json` with ll- entries, create `settings.local.json`, or Skip?"
     - If *both* exist → ask: "Update `settings.local.json` (Recommended), `settings.json`, or Skip?"

3. If user chose "Skip", proceed to Step 11 without changes.

4. Perform merge into the chosen target file:
   - Read target file, or start with `{"permissions": {"allow": [], "deny": []}}` if absent
   - Remove all existing entries starting with `Bash(ll-` from `permissions.allow` (idempotency)
   - Remove any existing `Write(.ll/ll-continue-prompt.md)` entry from `permissions.allow` (idempotency)
   - Append the canonical allow entries:
     ```json
     "Bash(ll-issues:*)",
     "Bash(ll-auto:*)",
     "Bash(ll-parallel:*)",
     "Bash(ll-sprint:*)",
     "Bash(ll-loop:*)",
     "Bash(ll-workflows:*)",
     "Bash(ll-messages:*)",
     "Bash(ll-history:*)",
     "Bash(ll-deps:*)",
     "Bash(ll-sync:*)",
     "Bash(ll-verify-docs:*)",
     "Bash(ll-check-links:*)",
     "Write(.ll/ll-continue-prompt.md)"
     ```
   - Create `.claude/` directory first if needed
   - Write result back with 2-space indent, preserving all top-level keys (`$schema`, `env`, etc.)

### 11. Update CLAUDE.md

Add ll- CLI command documentation to the target project's `CLAUDE.md`.

**If `--dry-run` is set, skip this step** (already shown in dry-run preview).

**If `--interactive` mode**: use the answer recorded in Round 12 (`CLAUDE_MD_ANSWER`). If the user chose "Skip", proceed to Step 12 without changes.

**Otherwise**: skip this step (Step 11 only runs in interactive mode).

If user opted in:

1. Detect existing file (reuse detection from Round 12, or re-detect):
   ```bash
   CLAUDE_MD_EXISTS=false
   CLAUDE_MD_PATH=""
   [ -f ".claude/CLAUDE.md" ] && CLAUDE_MD_EXISTS=true && CLAUDE_MD_PATH=".claude/CLAUDE.md"
   [ "$CLAUDE_MD_EXISTS" = false ] && [ -f "CLAUDE.md" ] && CLAUDE_MD_EXISTS=true && CLAUDE_MD_PATH="CLAUDE.md"
   ```

2. **Duplicate guard** (if file exists): check whether a `## little-loops` section is already present:
   - Read existing file content
   - If the string `## little-loops` is found anywhere in the file, skip writing (already documented) and log: `Skipped: CLAUDE.md already contains a ## little-loops section`
   - Otherwise, proceed to append

3. **If file exists and no duplicate**: append the commands section:
   ```markdown

   ## little-loops CLI Commands

   - `ll-auto` - Process all backlog issues sequentially in priority order
   - `ll-parallel` - Process issues concurrently using isolated git worktrees
   - `ll-sprint` - Define and execute curated issue sets with dependency-aware ordering
   - `ll-loop` - Execute FSM-based automation loops
   - `ll-workflows` - Identify multi-step workflow patterns from user message history
   - `ll-messages` - Extract user messages from Claude Code logs
   - `ll-history` - View completed issue statistics, analysis, and export topic-filtered excerpts from history
   - `ll-deps` - Cross-issue dependency analysis and validation
   - `ll-sync` - Sync local issues with GitHub Issues
   - `ll-verify-docs` - Verify documented counts match actual file counts
   - `ll-check-links` - Check markdown documentation for broken links
   - `ll-issues` - Issue management and visualization (next-id, list, show, sequence, impact-effort, refine-status)
   - `ll-gitignore` - Suggest and apply `.gitignore` patterns based on untracked files

   Install: `pip install -e "./scripts[dev]"`
   ```
   Track outcome: `CLAUDE_MD_UPDATED=true`

4. **If no file exists**: create `.claude/` directory if needed, then write `.claude/CLAUDE.md`:
   ```markdown
   # Project Configuration

   ## little-loops CLI Commands

   - `ll-auto` - Process all backlog issues sequentially in priority order
   - `ll-parallel` - Process issues concurrently using isolated git worktrees
   - `ll-sprint` - Define and execute curated issue sets with dependency-aware ordering
   - `ll-loop` - Execute FSM-based automation loops
   - `ll-workflows` - Identify multi-step workflow patterns from user message history
   - `ll-messages` - Extract user messages from Claude Code logs
   - `ll-history` - View completed issue statistics, analysis, and export topic-filtered excerpts from history
   - `ll-deps` - Cross-issue dependency analysis and validation
   - `ll-sync` - Sync local issues with GitHub Issues
   - `ll-verify-docs` - Verify documented counts match actual file counts
   - `ll-check-links` - Check markdown documentation for broken links
   - `ll-issues` - Issue management and visualization (next-id, list, show, sequence, impact-effort, refine-status)
   - `ll-gitignore` - Suggest and apply `.gitignore` patterns based on untracked files

   Install: `pip install -e "./scripts[dev]"`
   ```
   Track outcome: `CLAUDE_MD_CREATED=true`

### 12. Display Completion Message

```
================================================================================
INITIALIZATION COMPLETE
================================================================================

Created: .ll/ll-config.json
Created: .ll/ll-goals.md (product goals template)  # Only show if product enabled
Created: {{config.issues.base_dir}}/{bugs,features,enhancements,completed,deferred}
Updated: .gitignore (added state file exclusions)
Updated: .claude/settings.local.json (added ll- CLI tool permissions)  # Only show if user opted in
Created: .claude/CLAUDE.md (ll- CLI command documentation)             # Only show if CLAUDE_MD_CREATED=true
Updated: .claude/CLAUDE.md (appended ## little-loops CLI Commands)     # Only show if CLAUDE_MD_UPDATED=true

Next steps:
  1. Review and customize: .ll/ll-config.json
  2. Try a command: /ll:check-code
  3. Configure product goals: .ll/ll-goals.md      # Only show if product enabled
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
