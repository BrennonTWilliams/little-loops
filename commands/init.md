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

#### Step 5c: Features Selection (Round 3)

Use a SINGLE AskUserQuestion call with the features multi-select:

```yaml
questions:
  - header: "Features"
    question: "Which advanced features do you want to enable?"
    options:
      - label: "Parallel processing"
        description: "Configure ll-parallel for concurrent issue processing with git worktrees"
      - label: "Context monitoring"
        description: "Auto-handoff reminders at 80% context usage (works in all modes)"
    multiSelect: true
```

This round always runs and determines which follow-up questions are needed in Round 5.

#### Step 5d: Product Analysis (Round 4)

Use a SINGLE AskUserQuestion call:

```yaml
questions:
  - header: "Product"
    question: "Enable product-focused issue analysis? (Optional)"
    options:
      - label: "No, skip (Recommended)"
        description: "Technical analysis only - standard issue tracking"
      - label: "Yes, enable"
        description: "Add product goals, user impact, and business value to issues"
    multiSelect: false
```

**If "Yes, enable" selected:**
1. Create `.claude/ll-goals.md` from the goals template. Read the template content from `templates/ll-goals-template.md` (relative to the little-loops plugin directory) and write it to `.claude/ll-goals.md` in the user's project.

2. Add to configuration:
```json
{
  "product": {
    "enabled": true,
    "goals_file": ".claude/ll-goals.md"
  }
}
```

**If "No, skip" selected:**
- Omit the `product` section entirely (disabled is the default)

**Configuration notes:**
- Only include `product` section if enabled
- `analyze_user_impact` and `analyze_business_value` default to `true` and can be omitted
- The goals file location can be customized via `goals_file` property

**After completing Round 4, proceed to Round 5 (Advanced Settings).**

#### Step 5e: Advanced Settings (Dynamic Round 5)

Build this round dynamically based on previous responses. **Skip entirely if no follow-up questions are needed.**

**Include questions based on these conditions:**

1. **issues_path** - If user selected "Yes, custom directory" in Round 2
2. **worktree_files** - If user selected "Parallel processing" in Round 3
3. **threshold** - If user selected "Context monitoring" in Round 3

If all conditions are false, skip this round entirely and proceed directly to Round 6 (Document Tracking).

```yaml
questions:
  # ONLY include if user selected "Yes, custom directory" in Round 2:
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

  # ONLY include if user selected "Parallel processing" in Round 3:
  - header: "Worktree"
    question: "Which additional files should be copied to each git worktree? (Note: .claude/ is always copied automatically)"
    options:
      - label: ".env"
        description: "Environment variables (API keys, secrets)"
      - label: ".env.local"
        description: "Local environment overrides"
      - label: ".secrets"
        description: "Secrets file"
    multiSelect: true

  # ONLY include if user selected "Context monitoring" in Round 3:
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

**Configuration from Round 4 responses:**

If parallel is enabled and user selected files, add to configuration:
```json
{
  "parallel": {
    "worktree_copy_files": ["<selected files>"]
  }
}
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

**Notes:**
- Only include `auto_handoff_threshold` if user selected a non-default value (not 80%)
- Only include non-default values. If user selects exactly `[".env"]` (the default), the `worktree_copy_files` key can be omitted
- The `.claude/` directory is always copied automatically regardless of `worktree_copy_files` setting

**⚠️ MANDATORY NEXT STEP - DO NOT SKIP:**
After completing Round 5 (or if Round 5 was skipped because no conditions matched), you MUST immediately proceed to **Round 6 (Document Tracking)** below. Round 6 is NOT optional. Do NOT display the summary yet. Do NOT say "All rounds complete." Continue reading and execute Round 6.

---

#### Step 5f: Document Tracking (Round 6) - MANDATORY, ALWAYS RUNS

**⚠️ CRITICAL**: You MUST execute this round. This is Round 6 of the wizard. The wizard is NOT complete until you have asked the user about document tracking. If you skipped here without asking the Document Tracking question, GO BACK and ask it now.

**First, scan for markdown documents:**
```bash
# Find markdown files that might be key documents
find . -name "*.md" -not -path "*/.git/*" -not -path "*/node_modules/*" -not -path "*/.issues/*" -not -path "*/.worktrees/*" -not -path "*/thoughts/*" | head -30
```

Use a SINGLE AskUserQuestion call:

```yaml
questions:
  - header: "Docs"
    question: "Would you like to track key documents by category for issue alignment?"
    options:
      - label: "Use defaults (Recommended)"
        description: "Auto-detect architecture and product documents"
      - label: "Custom categories"
        description: "Define your own document categories"
      - label: "Skip"
        description: "Don't track documents"
    multiSelect: false
```

**If "Use defaults" selected:**
1. Scan codebase for .md files
2. Auto-detect architecture docs: files matching `**/architecture*.md`, `**/design*.md`, `**/api*.md`, `docs/*.md`
3. Auto-detect product docs: files matching `**/goal*.md`, `**/roadmap*.md`, `**/vision*.md`, `**/requirements*.md`
4. Present discovered files for confirmation:

```yaml
questions:
  - header: "Confirm"
    question: "Found these key documents. Include them all?"
    options:
      - label: "Yes, use all found"
        description: "[list architecture and product docs found]"
      - label: "Select specific files"
        description: "Choose which files to include"
      - label: "Skip document tracking"
        description: "Don't configure document tracking"
    multiSelect: false
```

**If "Custom categories" selected:**
1. Ask user to name their categories (comma-separated)
2. For each category, ask which files to include

**Configuration from Round 5 responses:**

If document tracking is enabled with defaults, add to configuration:
```json
{
  "documents": {
    "enabled": true,
    "categories": {
      "architecture": {
        "description": "System design and technical decisions",
        "files": ["docs/ARCHITECTURE.md", "docs/API.md"]
      },
      "product": {
        "description": "Product goals and requirements",
        "files": [".claude/ll-goals.md", "docs/ROADMAP.md"]
      }
    }
  }
}
```

If "Skip" selected or no documents found, omit the `documents` section entirely (disabled is the default).

**After completing Round 6, proceed to Step 5g (Extended Config Gate).**

#### Step 5g: Extended Configuration Gate (Round 6.5)

**After completing Round 6 (Document Tracking), proceed here.**

Use a SINGLE AskUserQuestion call:

```yaml
questions:
  - header: "Advanced"
    question: "Would you like to configure additional advanced settings?"
    options:
      - label: "Skip (Recommended)"
        description: "Use sensible defaults for continuation, prompt optimization, and more"
      - label: "Configure"
        description: "Set up test directory, build command, continuation, and prompt optimization"
    multiSelect: false
```

If "Skip (Recommended)" is selected, proceed directly to step 7 (Display Summary).
If "Configure" is selected, continue to Rounds 7-9.

#### Step 5h: Project Advanced (Round 7)

**Only run if user selected "Configure" in the Extended Config Gate.**

Use a SINGLE AskUserQuestion call with 2 questions:

```yaml
questions:
  - header: "Test Dir"
    question: "Do you have a separate test directory?"
    options:
      - label: "tests/ (Recommended)"
        description: "Standard tests/ directory"
      - label: "test/"
        description: "Alternative test/ directory"
      - label: "Same as src"
        description: "Tests are alongside source files"
    multiSelect: false

  - header: "Build Cmd"
    question: "Do you have a build command?"
    options:
      - label: "Skip (Recommended)"
        description: "No build step needed (common for scripting languages)"
      - label: "npm run build"
        description: "Node.js build"
      - label: "python -m build"
        description: "Python package build"
      - label: "make build"
        description: "Makefile build"
    multiSelect: false
```

**Populate options based on detected project type:**
- Python: tests/, test/, Same as src | Skip, python -m build, make build
- Node.js: tests/, test/, __tests__/ | npm run build, yarn build, Skip
- Go: *_test.go files in same dir | go build, make build, Skip
- Rust: tests/ | cargo build, cargo build --release, Skip
- Java: src/test/java/ | mvn package, gradle build, Skip
- .NET: tests/ | dotnet build, dotnet publish, Skip

**Configuration from Round 6 responses:**

If user selected a non-default test directory, add to configuration:
```json
{
  "project": {
    "test_dir": "<selected directory>"
  }
}
```

If user selected a build command (not "Skip"), add to configuration:
```json
{
  "project": {
    "build_cmd": "<selected command>"
  }
}
```

**Notes:**
- Only include `test_dir` if different from the schema default ("tests")
- Only include `build_cmd` if user selected a command (not "Skip")

#### Step 5i: Continuation Behavior (Round 8)

**Only run if user selected "Configure" in the Extended Config Gate.**

Use a SINGLE AskUserQuestion call with 3 questions:

```yaml
questions:
  - header: "Auto-detect"
    question: "Enable automatic session continuation detection?"
    options:
      - label: "Yes (Recommended)"
        description: "Auto-detect continuation prompts on session start"
      - label: "No"
        description: "Manual /ll:resume required"
    multiSelect: false

  - header: "Include"
    question: "What should continuation prompts include?"
    options:
      - label: "Todos"
        description: "Include pending todo list items"
      - label: "Git status"
        description: "Include current git status"
      - label: "Recent files"
        description: "Include recently modified files"
    multiSelect: true

  - header: "Expiry"
    question: "How long should continuation prompts remain valid?"
    options:
      - label: "24 hours (Recommended)"
        description: "Prompts expire after one day"
      - label: "48 hours"
        description: "Prompts expire after two days"
      - label: "No expiry (168 hours)"
        description: "Prompts remain valid for one week"
    multiSelect: false
```

**Configuration from Round 7 responses:**

If continuation settings differ from defaults, add to configuration:
```json
{
  "continuation": {
    "auto_detect_on_session_start": true,
    "include_todos": true,
    "include_git_status": true,
    "include_recent_files": true,
    "prompt_expiry_hours": 24
  }
}
```

**Mapping:**
- "Yes (Recommended)" for auto-detect → `auto_detect_on_session_start: true` (default, can omit)
- "No" for auto-detect → `auto_detect_on_session_start: false`
- "Todos" selected → `include_todos: true` (default)
- "Git status" selected → `include_git_status: true` (default)
- "Recent files" selected → `include_recent_files: true` (default)
- "24 hours" → `prompt_expiry_hours: 24` (default, can omit)
- "48 hours" → `prompt_expiry_hours: 48`
- "No expiry" → `prompt_expiry_hours: 168`

**Notes:**
- Only include `continuation` section if any value differs from schema defaults
- By default, all three include options are true, so only include if user deselects any

#### Step 5j: Prompt Optimization (Round 9)

**Only run if user selected "Configure" in the Extended Config Gate.**

Use a SINGLE AskUserQuestion call with 3 questions:

```yaml
questions:
  - header: "Optimize"
    question: "Enable automatic prompt optimization?"
    options:
      - label: "Yes (Recommended)"
        description: "Enhance prompts with codebase context"
      - label: "No"
        description: "Use prompts as-is"
    multiSelect: false

  - header: "Mode"
    question: "Optimization mode?"
    options:
      - label: "Quick (Recommended)"
        description: "Fast optimization using config patterns"
      - label: "Thorough"
        description: "Full codebase analysis via sub-agent"
    multiSelect: false

  - header: "Confirm"
    question: "Require confirmation before applying optimized prompts?"
    options:
      - label: "Yes (Recommended)"
        description: "Show optimized prompt for approval"
      - label: "No"
        description: "Apply optimization automatically"
    multiSelect: false
```

**Configuration from Round 8 responses:**

If prompt optimization settings differ from defaults, add to configuration:
```json
{
  "prompt_optimization": {
    "enabled": true,
    "mode": "quick",
    "confirm": true
  }
}
```

**Mapping:**
- "Yes (Recommended)" for enabled → `enabled: true` (default, can omit)
- "No" for enabled → `enabled: false`
- "Quick (Recommended)" → `mode: "quick"` (default, can omit)
- "Thorough" → `mode: "thorough"`
- "Yes (Recommended)" for confirm → `confirm: true` (default, can omit)
- "No" for confirm → `confirm: false`

**Notes:**
- Only include `prompt_optimization` section if any value differs from schema defaults
- If user selects "No" for enabled, the mode and confirm settings are still recorded but have no effect

---

### Interactive Mode Summary

**Total interaction rounds: 6-10**

| Round | Group | Questions | Conditions |
|-------|-------|-----------|------------|
| 1 | Core Settings | name, src_dir, test_cmd, lint_cmd | Always |
| 2 | Additional Config | format_cmd, issues, scan_dirs, excludes | Always |
| 3 | Features | features (multi-select: parallel, context_monitor) | Always |
| **4** | **Product Analysis** | **product (opt-in for product-focused analysis)** | **Always** |
| 5 | Advanced (dynamic) | issues_path?, worktree_files?, threshold? | Conditional |
| **6** | **Document Tracking** | **docs (auto-detect or custom categories)** | **Always** |
| 6.5 | Extended Config Gate | configure_extended? | Always |
| 7 | Project Advanced (optional) | test_dir, build_cmd | If Gate=Configure |
| 8 | Continuation (optional) | auto_detect, include, expiry | If Gate=Configure |
| 9 | Prompt Optimization (optional) | enabled, mode, confirm | If Gate=Configure |

**Round 4**: Always runs. User can enable product-focused issue analysis (disabled by default).

**Round 5 conditions:**
- **issues_path**: Only if "custom directory" selected in Round 2
- **worktree_files**: Only if "Parallel processing" selected in Round 3
- **threshold**: Only if "Context monitoring" selected in Round 3
- **If no conditions match**: Round 5 is skipped

**Round 6**: Always runs. User can choose "Use defaults", "Custom categories", or "Skip".

**Rounds 7-9 conditions:**
- Only run if user selects "Configure" in Round 6.5 (Extended Config Gate)
- If "Skip (Recommended)" is selected, rounds 7-9 are skipped entirely

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
  project.test_dir:   [test_dir]                # Only show if configured
  project.test_cmd:   [test_cmd]
  project.lint_cmd:   [lint_cmd]
  project.type_cmd:   [type_cmd]
  project.format_cmd: [format_cmd]
  project.build_cmd:  [build_cmd]               # Only show if configured

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

  [PRODUCT]                               # Only show if enabled
  product.enabled: true
  product.goals_file: .claude/ll-goals.md

  [DOCUMENTS]                             # Only show if enabled
  documents.enabled: true
  documents.categories: [architecture, product]  # List category names

  [CONTINUATION]                          # Only show if configured (non-defaults)
  continuation.auto_detect_on_session_start: [true/false]
  continuation.include_todos: [true/false]
  continuation.include_git_status: [true/false]
  continuation.include_recent_files: [true/false]
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
     "scan": { ... },
     "parallel": { ... },
     "context_monitor": { ... },
     "product": { ... },
     "documents": { ... },
     "continuation": { ... },
     "prompt_optimization": { ... }
   }
   ```

3. Only include sections with non-default values to keep the file minimal
   - Omit `parallel` section entirely if not configured in interactive mode
   - Omit `parallel.worktree_copy_files` if user selected exactly the defaults
   - Omit `context_monitor` section if user selected "No" (disabled is the default)
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

 ╭╮      ╭╮
 ╰┼──────┼╯
  little loops

Created: .claude/ll-config.json
Created: .claude/ll-goals.md (product goals template)  # Only show if product enabled
Updated: .gitignore (added state file exclusions)

Next steps:
  1. Review and customize: .claude/ll-config.json
  2. Try a command: /ll:check_code
  3. Set up issue tracking: mkdir -p .issues/{bugs,features,enhancements}
  4. Configure product goals: .claude/ll-goals.md      # Only show if product enabled
  5. Run parallel processing: ll-parallel      # Only show if parallel configured

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
