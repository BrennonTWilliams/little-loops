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

If `--interactive` flag is set, prompt for each configuration option:

#### Section: Project Settings
```
Project name [detected-name]:
Source directory [src/]:
Test command [pytest]:
Lint command [ruff check .]:
Type check command [mypy]:
Format command [ruff format .]:
Build command [null]:
```

#### Section: Issue Management
```
Use issue management? [Y/n]:
Issues base directory [.issues]:
```

#### Section: Scan Settings
```
Focus directories (comma-separated) [src/, tests/]:
Additional exclude patterns (comma-separated) []:
```

For each prompt:
- Show the default value in brackets
- Accept Enter to use the default
- Accept user input to override

### 6. Display Summary

```
================================================================================
BRENTECH-TOOLKIT INITIALIZATION
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
     "$schema": "https://raw.githubusercontent.com/little-loops/little-loops/main/config-schema.json",
     "project": { ... },
     "issues": { ... },
     "scan": { ... }
   }
   ```

3. Only include sections with non-default values to keep the file minimal

### 9. Display Completion Message

```
================================================================================
INITIALIZATION COMPLETE
================================================================================

Created: .claude/ll-config.json

Next steps:
  1. Review and customize: .claude/ll-config.json
  2. Try a command: /ll:check_code
  3. Set up issue tracking: mkdir -p .issues/{bugs,features,enhancements}

Documentation: https://github.com/little-loops/little-loops

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
