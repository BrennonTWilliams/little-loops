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

If `--interactive` flag is set, you MUST use the `AskUserQuestion` tool to gather user preferences step by step. Do NOT just display prompts as text - actually prompt the user interactively.

**IMPORTANT**: Use AskUserQuestion for each section to get real user input:

#### Step 5a: Project Settings

Use AskUserQuestion with these questions:
1. **Project name**: Ask if detected name is correct or provide custom name
2. **Source directory**: Offer detected dir or common alternatives (src/, lib/, app/, .)
3. **Test command**: Offer detected default or "Other" for custom command
4. **Lint command**: Offer detected default or common alternatives
5. **Format command**: Offer detected default or common alternatives

Example AskUserQuestion call for test command:
```
header: "Test Command"
question: "Which test command should be used?"
options:
  - label: "pytest" (detected default)
  - label: "pytest -v"
  - label: "python -m pytest"
multiSelect: false
```

#### Step 5b: Issue Management

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

**Then use AskUserQuestion based on detection:**

**If existing directory found** - ask whether to use it:
```
header: "Issues Dir"
question: "Found existing '[EXISTING_ISSUES_DIR]/' directory. Use it for issue tracking?"
options:
  - label: "Yes, use [EXISTING_ISSUES_DIR]/"
    description: "Keep existing directory and configure little-loops to use it"
  - label: "No, use different directory"
    description: "Specify a different directory for issues"
  - label: "Disable issue tracking"
    description: "Don't configure issue management"
multiSelect: false
```

**If no existing directory found** - ask whether to enable:
```
header: "Issues"
question: "Enable issue management features?"
options:
  - label: "Yes, use .issues/"
    description: "Create .issues/ directory for tracking bugs, features, enhancements"
  - label: "Yes, custom directory"
    description: "Specify a custom directory name"
  - label: "No"
    description: "Skip issue management configuration"
multiSelect: false
```

**If user chose custom directory** - ask for the name:
```
header: "Issues Path"
question: "What directory name should be used for issues?"
options:
  - label: ".issues"
    description: "Hidden directory (recommended)"
  - label: "issues"
    description: "Visible directory"
  - label: ".tasks"
    description: "Alternative naming"
multiSelect: false
```

#### Step 5c: Scan Settings

Use AskUserQuestion:
1. **Focus directories**: Offer detected dirs or custom selection
2. **Exclude patterns**: Offer adding custom patterns beyond defaults

#### Step 5d: Parallel Processing (ll-parallel)

Use AskUserQuestion to ask about parallel issue processing:

1. **Enable parallel processing**: Ask if user wants to configure `ll-parallel` for processing multiple issues concurrently using git worktrees.

```
header: "Parallel"
question: "Enable parallel issue processing with git worktrees (ll-parallel)?"
options:
  - label: "Yes"
    description: "Configure ll-parallel for concurrent issue processing"
  - label: "No"
    description: "Skip parallel config (can add later)"
multiSelect: false
```

2. **Worktree file copying** (only if parallel enabled): Ask which files should be copied from the main repo to each worktree. Use multi-select since users often need multiple files.

```
header: "Worktree Files"
question: "Which files should be copied to each git worktree?"
options:
  - label: ".env"
    description: "Environment variables (API keys, secrets)"
  - label: ".claude/settings.local.json"
    description: "Local Claude Code settings"
  - label: ".env.local"
    description: "Local environment overrides"
  - label: ".secrets"
    description: "Secrets file"
multiSelect: true
```

If parallel is enabled, add to configuration:
```json
{
  "parallel": {
    "worktree_copy_files": ["<selected files>"]
  }
}
```

Only include non-default values. If user selects exactly `[".env", ".claude/settings.local.json"]` (the defaults), the `worktree_copy_files` key can be omitted.

**Key behavior**:
- Wait for each AskUserQuestion response before proceeding
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

================================================================================
```

### 7. Confirm and Create

If `--yes` flag is NOT set:
- Ask: "Create .claude/ll-config.json with these settings? (y/n)"
- Wait for confirmation
- If user declines, abort without changes

If `--yes` flag IS set:
- Skip confirmation and proceed

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
     "parallel": { ... }
   }
   ```

3. Only include sections with non-default values to keep the file minimal
   - Omit `parallel` section entirely if not configured in interactive mode
   - Omit `parallel.worktree_copy_files` if user selected exactly the defaults

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
