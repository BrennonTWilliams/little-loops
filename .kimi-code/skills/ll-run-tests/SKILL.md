---
name: ll-run-tests
description: Run test suites with common patterns
argument-hint: "[scope]"
allowed-tools:
  - Bash(python:*, pytest:*, npm:*, cargo:*, go:*, make:*, git:*)
arguments:
  - name: scope
    description: Test scope (unit|integration|all|affected)
    required: false
  - name: pattern
    description: Optional test name pattern (-k filter)
    required: false
---

# Run Tests

You are tasked with running the test suite based on the specified scope and options.

## Configuration

This command uses project configuration from `.ll/ll-config.json`:
- **Test command**: `{{config.project.test_cmd}}` (already includes the test path)
- **Source directory**: `{{config.project.src_dir}}`

## Test Scopes

- **unit**: Fast unit tests (excludes tests marked `integration`)
- **integration**: Integration tests (marked `integration`; may require external services)
- **all**: Complete test suite
- **affected**: Tests for files changed since last commit

## Process

### 1. Parse Arguments

```bash
SCOPE="${scope:-all}"
PATTERN="$pattern"

echo "Running tests with scope: $SCOPE"
if [ -n "$PATTERN" ]; then
    echo "Filter pattern: $PATTERN"
fi
```

### 2. Execute Tests by Scope

#### Scope: unit

```bash
if [ "$SCOPE" = "unit" ]; then
    echo "Running unit tests..."

    if [ -n "$PATTERN" ]; then
        {{config.project.test_cmd}} -m "not integration" -k "$PATTERN" --tb=short
    else
        {{config.project.test_cmd}} -m "not integration" --tb=short
    fi
fi
```

#### Scope: integration

```bash
if [ "$SCOPE" = "integration" ]; then
    echo "Running integration tests..."

    if [ -n "$PATTERN" ]; then
        {{config.project.test_cmd}} -m integration -k "$PATTERN" --tb=short
    else
        {{config.project.test_cmd}} -m integration --tb=short
    fi
fi
```

#### Scope: all

```bash
if [ "$SCOPE" = "all" ]; then
    echo "Running complete test suite..."

    # No -v on full runs: per-test result lines for a 10k+-test suite are pure
    # controller I/O and transcript noise under xdist.
    if [ -n "$PATTERN" ]; then
        {{config.project.test_cmd}} -k "$PATTERN" --tb=short
    else
        {{config.project.test_cmd}} --tb=short
    fi
fi
```

#### Scope: affected

```bash
if [ "$SCOPE" = "affected" ]; then
    echo "Finding tests for changed files..."

    # Get changed Python files
    CHANGED_FILES=$(git diff --name-only HEAD~1 -- '*.py' | grep -E '^{{config.project.src_dir}}' || true)

    if [ -z "$CHANGED_FILES" ]; then
        echo "No Python files changed since last commit"
        exit 0
    fi

    echo "Changed files:"
    echo "$CHANGED_FILES"
    echo ""

    # Run tests for changed files
    {{config.project.test_cmd}} --tb=short
fi
```

### 3. Coverage Report (Optional)

If the user requests coverage, add coverage flags:

```bash
# To run with coverage:
{{config.project.test_cmd}} --cov={{config.project.src_dir}} --cov-report=term-missing --cov-report=html

echo "Coverage report generated at htmlcov/index.html"
```

---

## Quick Reference

| Scope | Description |
|-------|-------------|
| unit | Fast, no external deps |
| integration | May need services |
| all | Everything |
| affected | Smart selection |

---

## Arguments

$ARGUMENTS

- **scope** (optional, default: `all`): Test scope to run
  - `unit` - Fast unit tests
  - `integration` - Integration tests
  - `all` - Complete test suite
  - `affected` - Tests for recently changed files

- **pattern** (optional): pytest -k filter pattern to select specific tests

---

## Examples

```bash
# Run all unit tests
/ll:run-tests unit

# Run integration tests
/ll:run-tests integration

# Run tests matching "template"
/ll:run-tests all template

# Run tests for changed files
/ll:run-tests affected

# Run specific test pattern in unit tests
/ll:run-tests unit "test_create"
```
