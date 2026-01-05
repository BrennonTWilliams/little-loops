---
description: Run test suites with common patterns
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

This command uses project configuration from `.claude/ll-config.json`:
- **Test command**: `{{config.project.test_cmd}}`
- **Test directory**: `{{config.project.test_dir}}`
- **Source directory**: `{{config.project.src_dir}}`

## Test Scopes

- **unit**: Fast unit tests (no external dependencies)
- **integration**: Integration tests (may require external services)
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
        {{config.project.test_cmd}} {{config.project.test_dir}}/unit/ -v -k "$PATTERN" --tb=short
    else
        {{config.project.test_cmd}} {{config.project.test_dir}}/unit/ -v --tb=short
    fi
fi
```

#### Scope: integration

```bash
if [ "$SCOPE" = "integration" ]; then
    echo "Running integration tests..."

    if [ -n "$PATTERN" ]; then
        {{config.project.test_cmd}} {{config.project.test_dir}}/integration/ -v -k "$PATTERN" --tb=short
    else
        {{config.project.test_cmd}} {{config.project.test_dir}}/integration/ -v --tb=short
    fi
fi
```

#### Scope: all

```bash
if [ "$SCOPE" = "all" ]; then
    echo "Running complete test suite..."

    if [ -n "$PATTERN" ]; then
        {{config.project.test_cmd}} {{config.project.test_dir}}/ -v -k "$PATTERN" --tb=short
    else
        {{config.project.test_cmd}} {{config.project.test_dir}}/ -v --tb=short
    fi
fi
```

#### Scope: affected

```bash
if [ "$SCOPE" = "affected" ]; then
    echo "Finding tests for changed files..."

    # Get changed Python files
    CHANGED_FILES=$(git diff --name-only HEAD~1 -- '*.py' | grep -E '^{{config.project.src_dir}}|^{{config.project.test_dir}}/' || true)

    if [ -z "$CHANGED_FILES" ]; then
        echo "No Python files changed since last commit"
        exit 0
    fi

    echo "Changed files:"
    echo "$CHANGED_FILES"
    echo ""

    # Run tests for changed files
    {{config.project.test_cmd}} {{config.project.test_dir}}/ -v --tb=short
fi
```

### 3. Coverage Report (Optional)

If the user requests coverage, add coverage flags:

```bash
# To run with coverage:
{{config.project.test_cmd}} {{config.project.test_dir}}/ --cov={{config.project.src_dir}} --cov-report=term-missing --cov-report=html

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
/ll:run_tests unit

# Run integration tests
/ll:run_tests integration

# Run tests matching "template"
/ll:run_tests all template

# Run tests for changed files
/ll:run_tests affected

# Run specific test pattern in unit tests
/ll:run_tests unit "test_create"
```
