---
discovered_date: 2026-01-23
discovered_by: capture_issue
---

# ENH-126: Pre-built working loop templates

## Summary

Instead of only offering abstract paradigms (goal, invariants, convergence, imperative), the `/ll:create-loop` wizard should offer pre-built, tested loop configurations for common scenarios that users can select and customize.

## Context

Identified from conversation analyzing why created loops don't work. The current paradigm-based approach requires users to understand FSM concepts and correctly specify commands/evaluators. Pre-built templates that are known to work would reduce friction and errors.

## Current Behavior

The wizard offers 4 paradigm choices:
- Fix errors until clean (goal)
- Maintain code quality continuously (invariants)
- Drive a metric toward a target (convergence)
- Run a sequence of steps (imperative)

Users must then configure each from scratch, often making mistakes in command syntax, evaluator selection, or transition logic.

## Expected Behavior

Add a "Use template" option that offers complete, tested configurations:

```yaml
questions:
  - question: "How would you like to create your loop?"
    header: "Creation mode"
    options:
      - label: "Start from template (Recommended)"
        description: "Choose a pre-built loop for common tasks"
      - label: "Build from paradigm"
        description: "Configure a new loop from scratch"
```

If template mode selected:

```yaml
questions:
  - question: "Which template would you like to use?"
    header: "Template"
    options:
      - label: "Fix Python types and lint"
        description: "mypy + ruff check → auto-fix → repeat until clean"
      - label: "Fix JavaScript lint"
        description: "eslint → auto-fix → repeat until clean"
      - label: "Run tests until passing"
        description: "pytest/jest → fix failures → repeat"
      - label: "Quality gate (types + lint + tests)"
        description: "Check all, fix each failure, ensure all pass"
```

Each template would include:
- Working check commands with correct evaluators
- Appropriate fix actions
- Sensible max_iterations and timeouts
- Comments explaining customization points

## Proposed Solution

1. Create a templates directory or embed in the command: `.loops/templates/` or inline in `create_loop.md`

2. Define 5-10 common templates:

```yaml
# Template: fix-python-quality
paradigm: invariants
name: "fix-python-quality"
constraints:
  - name: "types"
    check: "mypy src/"
    fix: "# Manual fix required - mypy errors need human review"
  - name: "lint"
    check: "ruff check src/"
    fix: "ruff check --fix src/"
  - name: "format"
    check: "ruff format --check src/"
    fix: "ruff format src/"
maintain: false
max_iterations: 20
# Customization: Change 'src/' to your source directory
```

3. After template selection, show the config and ask for customizations:
   - Source directory path
   - Max iterations
   - Any commands to swap out

4. Templates should be tested as part of CI to ensure they remain valid.

## Template Ideas

| Template | Paradigm | Use Case |
|----------|----------|----------|
| fix-python-quality | invariants | Python lint + types + format |
| fix-js-quality | invariants | ESLint + Prettier + TypeScript |
| tests-until-pass | goal | Run tests, fix failures |
| reduce-type-errors | convergence | Drive mypy error count to 0 |
| ci-pipeline | imperative | lint → test → build sequence |
| coverage-improvement | convergence | Increase test coverage to target |

## Impact

- **Priority**: P3 (significantly reduces barrier to entry)
- **Effort**: Medium (create and test templates)
- **Risk**: Low (additive, templates are optional)

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| commands | commands/create_loop.md | Wizard to extend |
| architecture | docs/generalized-fsm-loop.md | Loop system documentation |

## Labels

`enhancement`, `create-loop`, `templates`, `ux`, `captured`

---

## Status

**Open** | Created: 2026-01-23 | Priority: P3

---

## Resolution

- **Action**: implement
- **Completed**: 2026-01-23
- **Status**: Completed

### Changes Made
- `commands/create_loop.md`: Added Step 0 (Creation Mode) with template vs custom selection
- `commands/create_loop.md`: Added Step 0.1 (Template Selection) with 4 pre-built templates:
  - Python quality (lint + types + format)
  - JavaScript quality (lint + types)
  - Tests until passing
  - Full quality gate
- `commands/create_loop.md`: Added Step 0.2 (Template Customization) for source dir and max iterations
- `commands/create_loop.md`: Added Template Quick Reference section with guidance on when to use templates vs custom

### Verification Results
- Lint: PASS
- Tests: 1694 passed, 1 pre-existing failure unrelated to changes

### Commits
- See git log for commit
