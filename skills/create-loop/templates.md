# Template Path: Paradigm Selection & Customization

## Step 0.1: Paradigm Selection (Template Path)

If "Start from template" was selected, present the loop paradigms:

```yaml
questions:
  - question: "Which loop paradigm fits your use case?"
    header: "Paradigm"
    multiSelect: false
    options:
      - label: "Goal (Recommended)"
        description: "Define an end state and let the loop work toward it. Best for: fixing errors until clean"
      - label: "Invariants"
        description: "Define conditions that must always hold; loop checks and fixes violations. Best for: quality gates"
      - label: "Convergence"
        description: "Measure a metric and apply fixes until it reaches a target. Best for: reducing error counts"
      - label: "Imperative"
        description: "Execute an ordered list of steps sequentially. Best for: multi-stage builds"
```

**After paradigm selection**: Continue to Step 0.2 (Template Customization) with the selected paradigm, then skip to Step 4 (Preview and Confirm) with template-populated configuration. The template definitions below provide pre-built configurations for each paradigm.

---

## Template Definitions

### Template: python-quality

```yaml
paradigm: invariants
name: "python-quality"
constraints:
  - name: "lint"
    check: "ruff check {{src_dir}}"
    fix: "ruff check --fix {{src_dir}}"
  - name: "types"
    check: "mypy {{src_dir}}"
    fix: "echo 'Fix type errors manually or use /ll:manage-issue bug fix'"
  - name: "format"
    check: "ruff format --check {{src_dir}}"
    fix: "ruff format {{src_dir}}"
maintain: false
max_iterations: {{max_iterations}}
```

### Template: javascript-quality

```yaml
paradigm: invariants
name: "javascript-quality"
constraints:
  - name: "lint"
    check: "npx eslint {{src_dir}}"
    fix: "npx eslint --fix {{src_dir}}"
  - name: "types"
    check: "npx tsc --noEmit"
    fix: "echo 'Fix type errors manually'"
maintain: false
max_iterations: {{max_iterations}}
```

### Template: tests-until-passing

```yaml
paradigm: goal
name: "tests-until-passing"
goal: "All tests pass"
tools:
  - "{{test_cmd}}"
  - "/ll:manage-issue bug fix"
max_iterations: {{max_iterations}}
```

**Test command by template context:**
- Python projects: `pytest`
- JavaScript projects: `npm test`
- Custom: Ask user for test command

### Template: full-quality-gate

```yaml
paradigm: invariants
name: "full-quality-gate"
constraints:
  - name: "tests"
    check: "{{test_cmd}}"
    fix: "/ll:manage-issue bug fix"
  - name: "types"
    check: "{{type_cmd}}"
    fix: "/ll:manage-issue bug fix"
  - name: "lint"
    check: "{{lint_cmd}}"
    fix: "{{lint_fix_cmd}}"
maintain: false
max_iterations: {{max_iterations}}
```

**Command defaults for full-quality-gate:**

| Language | test_cmd | type_cmd | lint_cmd | lint_fix_cmd |
|----------|----------|----------|----------|--------------|
| Python | `pytest` | `mypy {{src_dir}}` | `ruff check {{src_dir}}` | `ruff check --fix {{src_dir}}` |
| JavaScript | `npm test` | `npx tsc --noEmit` | `npx eslint {{src_dir}}` | `npx eslint --fix {{src_dir}}` |

---

## Step 0.2: Template Customization

After paradigm selection, ask for customization:

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
- Use the selected paradigm to pick the matching template definition below
- The generated YAML and auto-suggested loop name are ready
- Continue directly to Step 4 (Preview and Confirm) with the template-populated configuration
- Skip Step 1 (Paradigm Selection), Step 2 (Paradigm-Specific Questions), and Step 3 (Loop Name) since paradigm + template provides all configuration
