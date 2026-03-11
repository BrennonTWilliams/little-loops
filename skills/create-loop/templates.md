# Template Path: Loop Type Selection & Customization

## Step 0.1: Loop Type Selection (Template Path)

If "Start from template" was selected, present the available templates:

```yaml
questions:
  - question: "Which template fits your use case?"
    header: "Template"
    multiSelect: false
    options:
      - label: "Python quality (Recommended)"
        description: "Fix lint, type, and format errors for Python projects. Best for: ruff + mypy"
      - label: "JavaScript quality"
        description: "Fix lint and type errors for JS/TS projects. Best for: eslint + tsc"
      - label: "Tests until passing"
        description: "Run tests and fix failures until all pass. Best for: any project with a test suite"
      - label: "Full quality gate"
        description: "Multi-constraint quality gate covering tests, types, and lint. Best for: CI-like validation"
```

**After template selection**: Continue to Step 0.2 (Template Customization), then skip to Step 4 (Preview and Confirm) with template-populated configuration.

---

## Template Definitions

### Template: python-quality

```yaml
name: "python-quality"
initial: check_lint
max_iterations: {{max_iterations}}
states:
  check_lint:
    action: "ruff check {{src_dir}}"
    on_success: check_types
    on_failure: fix_lint
  fix_lint:
    action: "ruff check --fix {{src_dir}}"
    next: check_lint
  check_types:
    action: "mypy {{src_dir}}"
    on_success: check_format
    on_failure: fix_types
  fix_types:
    action: "echo 'Fix type errors manually or use /ll:manage-issue bug fix'"
    next: check_types
  check_format:
    action: "ruff format --check {{src_dir}}"
    on_success: all_valid
    on_failure: fix_format
  fix_format:
    action: "ruff format {{src_dir}}"
    next: check_format
  all_valid:
    terminal: true
```

### Template: javascript-quality

```yaml
name: "javascript-quality"
initial: check_lint
max_iterations: {{max_iterations}}
states:
  check_lint:
    action: "npx eslint {{src_dir}}"
    on_success: check_types
    on_failure: fix_lint
  fix_lint:
    action: "npx eslint --fix {{src_dir}}"
    next: check_lint
  check_types:
    action: "npx tsc --noEmit"
    on_success: all_valid
    on_failure: fix_types
  fix_types:
    action: "echo 'Fix type errors manually'"
    next: check_types
  all_valid:
    terminal: true
```

### Template: tests-until-passing

```yaml
name: "tests-until-passing"
initial: evaluate
max_iterations: {{max_iterations}}
states:
  evaluate:
    action: "{{test_cmd}}"
    on_success: done
    on_failure: fix
    on_error: fix
  fix:
    action: "/ll:manage-issue bug fix"
    next: evaluate
  done:
    terminal: true
```

**Test command by template context:**
- Python projects: `pytest`
- JavaScript projects: `npm test`
- Custom: Ask user for test command

### Template: full-quality-gate

```yaml
name: "full-quality-gate"
initial: check_tests
max_iterations: {{max_iterations}}
states:
  check_tests:
    action: "{{test_cmd}}"
    on_success: check_types
    on_failure: fix_tests
  fix_tests:
    action: "/ll:manage-issue bug fix"
    next: check_tests
  check_types:
    action: "{{type_cmd}}"
    on_success: check_lint
    on_failure: fix_types
  fix_types:
    action: "/ll:manage-issue bug fix"
    next: check_types
  check_lint:
    action: "{{lint_cmd}}"
    on_success: all_valid
    on_failure: fix_lint
  fix_lint:
    action: "{{lint_fix_cmd}}"
    next: check_lint
  all_valid:
    terminal: true
```

**Command defaults for full-quality-gate:**

| Language | test_cmd | type_cmd | lint_cmd | lint_fix_cmd |
|----------|----------|----------|----------|--------------|
| Python | `pytest` | `mypy {{src_dir}}` | `ruff check {{src_dir}}` | `ruff check --fix {{src_dir}}` |
| JavaScript | `npm test` | `npx tsc --noEmit` | `npx eslint {{src_dir}}` | `npx eslint --fix {{src_dir}}` |

---

## Step 0.2: Template Customization

After template selection, ask for customization:

```yaml
questions:
  - question: "What source directory should the loop check?"
    header: "Source dir"
    multiSelect: false
    options:
      - label: "src/ (Recommended)"
        description: "Standard source directory"
      - label: "."
        description: "Project root"
      - label: "lib/"
        description: "Library directory"
      - label: "Custom path"
        description: "Specify your own directory"

  - question: "What's the maximum number of fix attempts?"
    header: "Max iterations"
    multiSelect: false
    options:
      - label: "20 (Recommended)"
        description: "Good for most use cases"
      - label: "10"
        description: "Quick fixes only"
      - label: "50"
        description: "For complex issues"

> **Note**: Your selection will be explicitly set in the generated YAML. If omitted later, the default is 50.
```

**If "Custom path" selected for source dir**: Ask for path via Other option.

**Apply substitutions to selected template:**
- Replace `{{src_dir}}` with selected source directory
- Replace `{{max_iterations}}` with selected max iterations
- Replace `{{test_cmd}}`, `{{type_cmd}}`, `{{lint_cmd}}`, `{{lint_fix_cmd}}` with language-appropriate defaults

**Flow after template customization:**
- The generated FSM YAML and auto-suggested loop name are ready
- Continue directly to Step 4 (Preview and Confirm) with the template-populated configuration
- Skip Step 1 (Loop Type Selection), Step 2 (Type-Specific Questions), and Step 3 (Loop Name) since the template provides all configuration
