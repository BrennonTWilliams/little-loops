---
description: Initialize little-loops configuration for a project
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

Based on detected project type, use these presets:

#### Python
```json
{
  "project": {
    "src_dir": "src/",
    "test_cmd": "pytest",
    "lint_cmd": "ruff check .",
    "type_cmd": "mypy",
    "format_cmd": "ruff format ."
  },
  "scan": {
    "focus_dirs": ["src/", "tests/"],
    "exclude_patterns": ["**/__pycache__/**", "**/.venv/**", "**/dist/**"]
  }
}
```

#### Node.js
```json
{
  "project": {
    "src_dir": "src/",
    "test_cmd": "npm test",
    "lint_cmd": "npm run lint",
    "type_cmd": null,
    "format_cmd": "npm run format"
  },
  "scan": {
    "focus_dirs": ["src/", "tests/", "lib/"],
    "exclude_patterns": ["**/node_modules/**", "**/dist/**", "**/build/**"]
  }
}
```

#### Go
```json
{
  "project": {
    "src_dir": ".",
    "test_cmd": "go test ./...",
    "lint_cmd": "golangci-lint run",
    "type_cmd": null,
    "format_cmd": "gofmt -w ."
  },
  "scan": {
    "focus_dirs": ["cmd/", "pkg/", "internal/"],
    "exclude_patterns": ["**/vendor/**"]
  }
}
```

#### Rust
```json
{
  "project": {
    "src_dir": "src/",
    "test_cmd": "cargo test",
    "lint_cmd": "cargo clippy",
    "type_cmd": null,
    "format_cmd": "cargo fmt"
  },
  "scan": {
    "focus_dirs": ["src/"],
    "exclude_patterns": ["**/target/**"]
  }
}
```

#### Java
```json
{
  "project": {
    "src_dir": "src/main/java/",
    "test_cmd": "mvn test",
    "lint_cmd": null,
    "type_cmd": null,
    "format_cmd": null,
    "build_cmd": "mvn package"
  },
  "scan": {
    "focus_dirs": ["src/main/java/", "src/test/java/"],
    "exclude_patterns": ["**/target/**", "**/.idea/**"]
  }
}
```

#### .NET
```json
{
  "project": {
    "src_dir": "src/",
    "test_cmd": "dotnet test",
    "lint_cmd": "dotnet format --verify-no-changes",
    "type_cmd": null,
    "format_cmd": "dotnet format"
  },
  "scan": {
    "focus_dirs": ["src/"],
    "exclude_patterns": ["**/bin/**", "**/obj/**"]
  }
}
```

#### General (fallback)
```json
{
  "project": {
    "src_dir": "src/",
    "test_cmd": null,
    "lint_cmd": null,
    "type_cmd": null,
    "format_cmd": null
  },
  "scan": {
    "focus_dirs": ["src/"],
    "exclude_patterns": ["**/node_modules/**", "**/__pycache__/**", "**/.git/**"]
  }
}
```

### 5. Interactive Mode (if --interactive)

If `--interactive` flag is set, you MUST use the `AskUserQuestion` tool to gather user preferences. Do NOT just display prompts as text - actually prompt the user interactively.

**IMPORTANT**: Group related questions together using AskUserQuestion's multi-question capability (up to 4 questions per call) to reduce interaction rounds.

#### Step 5a: Core Project Settings (Group 1)

Use a SINGLE AskUserQuestion call with 4 questions:

```yaml
questions:
  - header: "Name"
    question: "Is '[DETECTED_NAME]' the correct project name?"
    options:
      - label: "Yes, use [DETECTED_NAME]"
        description: "Keep the detected project name"
      - label: "No, different name"
        description: "Specify a custom project name"
    multiSelect: false

  - header: "Source Dir"
    question: "Which source directory contains your code?"
    options:
      - label: "[DETECTED_DIR]"
        description: "Detected from project structure"
      - label: "src/"
        description: "Standard source directory"
      - label: "lib/"
        description: "Library source directory"
      - label: "."
        description: "Project root"
    multiSelect: false

  - header: "Test Cmd"
    question: "Which test command should be used?"
    options:
      - label: "[DETECTED_TEST_CMD]"
        description: "Detected from project type"
      - label: "[ALT_TEST_CMD_1]"
        description: "Alternative test command"
      - label: "[ALT_TEST_CMD_2]"
        description: "Alternative test command"
    multiSelect: false

  - header: "Lint Cmd"
    question: "Which lint command should be used?"
    options:
      - label: "[DETECTED_LINT_CMD]"
        description: "Detected from project type"
      - label: "[ALT_LINT_CMD_1]"
        description: "Alternative lint command"
      - label: "[ALT_LINT_CMD_2]"
        description: "Alternative lint command"
    multiSelect: false
```

**Populate options based on detected project type:**
- Python: pytest, pytest -v, python -m pytest | ruff check ., flake8, pylint
- Node.js: npm test, yarn test, jest | npm run lint, eslint .
- Go: go test ./..., go test -v ./... | golangci-lint run, go vet ./...
- Rust: cargo test, cargo test --verbose | cargo clippy, cargo check
- Java: mvn test, gradle test | (no common lint)
- .NET: dotnet test | dotnet format --verify-no-changes

#### Step 5b: Additional Configuration (Group 2)

**First, detect existing issues directory:**
```bash
# Check for existing .issues/ folder
if [ -d ".issues" ]; then
  EXISTING_ISSUES_DIR=".issues"
elif [ -d "issues" ]; then
  EXISTING_ISSUES_DIR="issues"
else
  EXISTING_ISSUES_DIR=""
fi
```

Use a SINGLE AskUserQuestion call with 4 questions:

```yaml
questions:
  - header: "Format Cmd"
    question: "Which format command should be used?"
    options:
      - label: "[DETECTED_FORMAT_CMD]"
        description: "Detected from project type"
      - label: "[ALT_FORMAT_CMD_1]"
        description: "Alternative format command"
      - label: "None"
        description: "No formatting command"
    multiSelect: false

  - header: "Issues"
    # If EXISTING_ISSUES_DIR is found:
    question: "Found existing '[EXISTING_ISSUES_DIR]/' directory. Use it for issue tracking?"
    # OR if no existing directory:
    # question: "Enable issue management features?"
    options:
      # If existing dir found:
      - label: "Yes, use [EXISTING_ISSUES_DIR]/"
        description: "Keep existing directory for issue tracking"
      # OR if no existing dir:
      # - label: "Yes, use .issues/"
      #   description: "Create .issues/ for tracking bugs, features, enhancements"
      - label: "Yes, custom directory"
        description: "Specify a custom directory name"
      - label: "Disable"
        description: "Skip issue management configuration"
    multiSelect: false

  - header: "Scan Dirs"
    question: "Which directories should be scanned for code issues?"
    options:
      - label: "[DETECTED_FOCUS_DIRS]"
        description: "Detected from project structure"
      - label: "src/, tests/"
        description: "Standard source and test directories"
      - label: "Custom selection"
        description: "Specify custom directories"
    multiSelect: false

  - header: "Excludes"
    question: "Add custom exclude patterns beyond defaults?"
    options:
      - label: "Use defaults only"
        description: "Standard excludes for project type (node_modules, __pycache__, etc.)"
      - label: "Add custom patterns"
        description: "Specify additional patterns to exclude"
    multiSelect: false
```

**Populate format options based on detected project type:**
- Python: ruff format ., black ., autopep8
- Node.js: npm run format, prettier --write ., eslint --fix
- Go: gofmt -w ., go fmt ./...
- Rust: cargo fmt
- Java: (none common)
- .NET: dotnet format

#### Step 5c: Advanced Settings (Conditional Group 3)

Build this AskUserQuestion dynamically based on Group 2 responses. Include 1-2 questions:

**If user selected "custom directory" for issues in Group 2**, include custom dir question.
**Always include** the advanced features multi-select question.

```yaml
questions:
  # ONLY include if user selected "Yes, custom directory" in Group 2:
  - header: "Issues Path"
    question: "What directory name should be used for issues?"
    options:
      - label: ".issues"
        description: "Hidden directory (recommended)"
      - label: "issues"
        description: "Visible directory"
      - label: ".tasks"
        description: "Alternative naming"
    multiSelect: false

  # ALWAYS include:
  - header: "Features"
    question: "Which advanced features do you want to enable?"
    options:
      - label: "Parallel processing"
        description: "Configure ll-parallel for concurrent issue processing with git worktrees"
      - label: "Context monitoring"
        description: "Auto-handoff reminders at 80% context usage (works in all modes)"
    multiSelect: true
```

#### Step 5d: Worktree Files (Conditional Group 4)

**Only ask if user selected "Parallel processing" in the Features question (Group 3).**

**Note**: The `.claude/` directory is always copied automatically to worktrees (required for Claude Code project root detection). Only ask about additional files outside `.claude/`.

```yaml
questions:
  - header: "Worktree Files"
    question: "Which additional files should be copied to each git worktree? (Note: .claude/ is always copied automatically)"
    options:
      - label: ".env"
        description: "Environment variables (API keys, secrets)"
      - label: ".env.local"
        description: "Local environment overrides"
      - label: ".secrets"
        description: "Secrets file"
    multiSelect: true
```

If parallel is enabled and user selected files, add to configuration:
```json
{
  "parallel": {
    "worktree_copy_files": ["<selected files>"]
  }
}
```

#### Step 5e: Context Monitor Settings (Conditional Group 5)

**Only ask if user selected "Context monitoring" in the Features question (Group 3).**

```yaml
questions:
  - header: "Threshold"
    question: "At what context usage percentage should auto-handoff trigger?"
    options:
      - label: "80%"
        description: "Default - balanced for most workloads"
      - label: "70%"
        description: "Conservative - earlier handoff, more headroom"
      - label: "90%"
        description: "Aggressive - maximize context before handoff"
    multiSelect: false
```

If context monitoring is enabled, add to configuration:
```json
{
  "context_monitor": {
    "enabled": true,
    "auto_handoff_threshold": 80
  }
}
```

Only include `auto_handoff_threshold` if user selected a non-default value (not 80%).

Only include non-default values. If user selects exactly `[".env"]` (the default), the `worktree_copy_files` key can be omitted. Note: `.claude/` directory is always copied automatically regardless of this setting.

---

### Interactive Mode Summary

**Total interaction rounds: 3-5** (reduced from 9-11)

| Round | Group | Questions |
|-------|-------|-----------|
| 1 | Core Settings | name, src_dir, test_cmd, lint_cmd |
| 2 | Additional Config | format_cmd, issues, scan_dirs, excludes |
| 3 | Advanced (conditional) | custom_issue_dir?, features (multi-select: parallel, context_monitor) |
| 4 | Parallel Files (conditional) | worktree_files (only if "Parallel processing" selected) |
| 5 | Context Settings (conditional) | threshold (only if "Context monitoring" selected) |

**Key behavior**:
- Wait for each group's AskUserQuestion response before proceeding to the next
- Use the responses to build the final configuration
- Show detected defaults as the first/recommended option
- Allow "Other" for custom values (built-in to AskUserQuestion)

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
  project.test_cmd:   [test_cmd]
  project.lint_cmd:   [lint_cmd]
  project.type_cmd:   [type_cmd]
  project.format_cmd: [format_cmd]
  project.build_cmd:  [build_cmd]

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
     "scan": { ... },
     "parallel": { ... },
     "context_monitor": { ... }
   }
   ```

3. Only include sections with non-default values to keep the file minimal
   - Omit `parallel` section entirely if not configured in interactive mode
   - Omit `parallel.worktree_copy_files` if user selected exactly the defaults
   - Omit `context_monitor` section if user selected "No" (disabled is the default)

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

 ╭╮      ╭╮
 ╰┼──────┼╯
  little loops

Created: .claude/ll-config.json
Updated: .gitignore (added state file exclusions)

Next steps:
  1. Review and customize: .claude/ll-config.json
  2. Try a command: /ll:check_code
  3. Set up issue tracking: mkdir -p .issues/{bugs,features,enhancements}
  4. Run parallel processing: ll-parallel      # Only show if parallel configured

Documentation: https://github.com/BrennonTWilliams/little-loops

================================================================================
```

---

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
