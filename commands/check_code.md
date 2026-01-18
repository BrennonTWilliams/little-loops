---
description: Run code quality checks (lint, format, types)
allowed-tools:
  - Bash(ruff:*, mypy:*, python:*)
arguments:
  - name: mode
    description: Check mode (lint|format|types|all|fix)
    required: false
---

# Check Code

You are tasked with running code quality checks on the codebase.

## Configuration

This command uses project configuration from `.claude/ll-config.json`:
- **Source directory**: `{{config.project.src_dir}}`
- **Lint command**: `{{config.project.lint_cmd}}`
- **Format command**: `{{config.project.format_cmd}}`
- **Type command**: `{{config.project.type_cmd}}`

## Check Modes

- **lint**: Run linter to find code issues
- **format**: Check code formatting
- **types**: Run type checking
- **all**: Run all checks (default)
- **fix**: Auto-fix issues where possible

## Process

### 1. Parse Mode

```bash
MODE="${mode:-all}"
echo "Running code checks in mode: $MODE"
```

### 2. Execute Checks by Mode

**IMPORTANT**: When running `lint`, `format`, or `all` modes, if any issues are detected, you MUST automatically proceed to fix them using the fix commands below. Do NOT just report the issues and suggest running fix - actually run the fixes immediately.

#### Mode: lint

```bash
if [ "$MODE" = "lint" ] || [ "$MODE" = "all" ]; then
    echo ""
    echo "========================================"
    echo "LINTING"
    echo "========================================"

    {{config.project.lint_cmd}} {{config.project.src_dir}}

    if [ $? -eq 0 ]; then
        echo "[PASS] No linting errors found"
    fi
fi
```

If lint errors are detected, immediately run the lint fix command:
```bash
{{config.project.lint_cmd}} --fix {{config.project.src_dir}}
```

#### Mode: format

```bash
if [ "$MODE" = "format" ] || [ "$MODE" = "all" ]; then
    echo ""
    echo "========================================"
    echo "FORMAT CHECK"
    echo "========================================"

    {{config.project.format_cmd}} --check {{config.project.src_dir}}

    if [ $? -eq 0 ]; then
        echo "[PASS] All files properly formatted"
    fi
fi
```

If formatting issues are detected, immediately run the format fix command:
```bash
{{config.project.format_cmd}} {{config.project.src_dir}}
```

#### Mode: types

```bash
if [ "$MODE" = "types" ] || [ "$MODE" = "all" ]; then
    echo ""
    echo "========================================"
    echo "TYPE CHECK"
    echo "========================================"

    {{config.project.type_cmd}} {{config.project.src_dir}} --ignore-missing-imports

    if [ $? -eq 0 ]; then
        echo "[PASS] No type errors found"
    else
        echo "[FAIL] Type errors detected"
    fi
fi
```

#### Mode: fix

```bash
if [ "$MODE" = "fix" ]; then
    echo ""
    echo "========================================"
    echo "AUTO-FIXING ISSUES"
    echo "========================================"

    echo "Step 1: Fixing lint issues..."
    {{config.project.lint_cmd}} --fix {{config.project.src_dir}}

    echo ""
    echo "Step 2: Formatting code..."
    {{config.project.format_cmd}} {{config.project.src_dir}}

    echo ""
    echo "========================================"
    echo "AUTO-FIX COMPLETE"
    echo "========================================"
    echo ""
    echo "Run '/ll:check_code all' to verify all issues are resolved"
    echo "Note: Type errors cannot be auto-fixed"
fi
```

### 3. Summary Report

After running all checks (and auto-fixes if needed), provide a summary:

```
================================================================================
CODE QUALITY CHECK COMPLETE
================================================================================

Mode: $MODE

Results:
  Linting:    [PASS/FIXED/FAIL]
  Formatting: [PASS/FIXED/FAIL]
  Types:      [PASS/FAIL]

Status:
- PASS: No issues found
- FIXED: Issues were found and automatically fixed
- FAIL: Issues remain (type errors cannot be auto-fixed)

================================================================================
```

---

## Arguments

$ARGUMENTS

- **mode** (optional, default: `all`): Check mode to run
  - `lint` - Run linter only
  - `format` - Check formatting only
  - `types` - Run type checking only
  - `all` - Run all checks
  - `fix` - Auto-fix lint and format issues

---

## Examples

```bash
# Run all checks
/ll:check_code

# Just check linting
/ll:check_code lint

# Just check formatting
/ll:check_code format

# Just type checking
/ll:check_code types

# Auto-fix issues
/ll:check_code fix
```
