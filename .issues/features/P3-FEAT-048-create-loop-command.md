# FEAT-048: /ll:create-loop Command

## Summary

Implement an interactive skill that guides users through creating new loop configurations using `AskUserQuestion` for paradigm selection and parameter gathering.

## Priority

P3 - User experience enhancement

## Dependencies

- FEAT-040: FSM Schema Definition and Validation
- FEAT-041: Paradigm Compilers
- FEAT-047: ll-loop CLI Tool

## Blocked By

- FEAT-040, FEAT-041

## Description

The `/ll:create-loop` command provides an interactive workflow for creating loops:

1. Ask which paradigm the user wants
2. Gather paradigm-specific parameters via multi-step questions
3. Generate paradigm YAML
4. Show preview and confirm
5. Save to `.loops/<name>.yaml`
6. Optionally validate with `ll-loop validate`

### Files to Create

```
skills/create-loop.md
```

## Technical Details

### Skill Definition

```markdown
---
description: Create a new FSM loop configuration interactively
allowed_tools:
  - AskUserQuestion
  - Write
  - Bash
  - Read
---

# /ll:create-loop

Guide the user through creating a new automation loop.

## Workflow

1. **Choose Paradigm**
   Ask which type of loop using AskUserQuestion:
   - "Fix errors until clean" → goal or invariants
   - "Drive a metric toward a target" → convergence
   - "Run a sequence of steps" → imperative
   - "Define custom states" → fsm

2. **Gather Parameters**
   Based on paradigm, ask follow-up questions...

3. **Generate YAML**
   Create the paradigm YAML based on answers

4. **Preview and Save**
   Show the generated YAML, confirm, save to .loops/
```

### Question Flow

#### Step 1: Paradigm Selection

```yaml
# AskUserQuestion call
questions:
  - question: "What kind of automation loop do you want to create?"
    header: "Loop type"
    multiSelect: false
    options:
      - label: "Fix errors until clean (Recommended)"
        description: "Run checks and fix issues until all pass"
      - label: "Maintain code quality continuously"
        description: "Keep multiple constraints true, restart after all pass"
      - label: "Drive a metric toward a target"
        description: "Measure a value and apply fixes until it reaches goal"
      - label: "Run a sequence of steps"
        description: "Execute steps in order, repeat until condition met"
```

#### Step 2: Paradigm-Specific Questions

**Goal Paradigm:**
```yaml
questions:
  - question: "What should the loop fix?"
    header: "Fix targets"
    multiSelect: true
    options:
      - label: "Type errors (mypy)"
        description: "Run mypy and fix type errors"
      - label: "Lint errors (ruff)"
        description: "Run ruff and fix lint issues"
      - label: "Test failures (pytest)"
        description: "Run pytest and fix failing tests"
      - label: "Custom check"
        description: "Specify your own check command"

  - question: "What's the maximum number of fix attempts?"
    header: "Max iterations"
    multiSelect: false
    options:
      - label: "10 (Recommended)"
        description: "Good for most fixes"
      - label: "20"
        description: "For more complex issues"
      - label: "50"
        description: "For large codebases"
```

**Convergence Paradigm:**
```yaml
questions:
  - question: "What command outputs the metric to track?"
    header: "Metric command"
    # Free text via "Other" option

  - question: "What is the target value?"
    header: "Target"
    # Free text

  - question: "What action should reduce the metric?"
    header: "Fix action"
    multiSelect: false
    options:
      - label: "/ll:manage_issue bug fix"
        description: "Use issue management to fix bugs"
      - label: "/ll:check_code fix"
        description: "Auto-fix code issues"
      - label: "Custom command"
        description: "Specify your own fix command"
```

### Example Session

```
> /ll:create-loop

What kind of automation loop do you want to create?
  ○ Fix errors until clean (Recommended)
  ○ Maintain code quality continuously
  ○ Drive a metric toward a target
  ○ Run a sequence of steps
  ○ Other...

> Fix errors until clean

What should the loop fix?
  ☑ Type errors (mypy)
  ☑ Lint errors (ruff)
  ☐ Test failures (pytest)
  ☐ Custom check

> [Type errors, Lint errors selected]

What's the maximum number of fix attempts?
  ○ 10 (Recommended)
  ○ 20
  ○ 50
  ○ Custom...

> 10

What should the loop be called?
> fix-types-and-lint

Here's the loop configuration:

```yaml
paradigm: invariants
name: "fix-types-and-lint"
constraints:
  - name: "types-valid"
    check: "mypy src/"
    fix: "/ll:manage_issue bug fix"
  - name: "lint-clean"
    check: "ruff check src/"
    fix: "/ll:check_code fix"
max_iterations: 10
```

Save to .loops/fix-types-and-lint.yaml? [Y/n]

> Y

✓ Saved to .loops/fix-types-and-lint.yaml
✓ Validation passed

Run now with: ll-loop fix-types-and-lint
```

### YAML Generation Templates

```python
# Embedded in skill instructions or separate module
def generate_goal_yaml(checks: list[str], fix_tool: str, max_iter: int, name: str) -> str:
    tools = []
    for check in checks:
        if check == "types":
            tools.append("/ll:check_code types")
        elif check == "lint":
            tools.append("ruff check src/")
        elif check == "tests":
            tools.append("pytest")

    return f"""paradigm: goal
name: "{name}"
goal: "{' and '.join(checks)} pass"
tools:
  - {tools[0]}
  - {fix_tool}
max_iterations: {max_iter}
"""

def generate_invariants_yaml(constraints: list[dict], maintain: bool, max_iter: int, name: str) -> str:
    constraint_yaml = "\n".join([
        f"""  - name: "{c['name']}"
    check: "{c['check']}"
    fix: "{c['fix']}" """
        for c in constraints
    ])

    return f"""paradigm: invariants
name: "{name}"
constraints:
{constraint_yaml}
maintain: {str(maintain).lower()}
max_iterations: {max_iter}
"""
```

## Acceptance Criteria

- [ ] Skill file created at `skills/create-loop.md`
- [ ] Paradigm selection via `AskUserQuestion` with 4 options
- [ ] Goal paradigm: asks for checks, fix tool, max iterations
- [ ] Convergence paradigm: asks for metric command, target, fix action
- [ ] Invariants paradigm: asks for constraints, maintain mode
- [ ] Imperative paradigm: asks for steps, until condition
- [ ] Loop name prompt with auto-suggestion based on selections
- [ ] YAML preview shown before saving
- [ ] Confirmation before write
- [ ] File saved to `.loops/<name>.yaml`
- [ ] Runs `ll-loop validate <name>` after save
- [ ] Shows "Run now with: ll-loop <name>" on success

## Testing Requirements

Manual testing with various paradigm selections:

1. **Goal paradigm flow**
   - Select "Fix errors until clean"
   - Choose type errors + lint errors
   - Verify generated YAML has correct tools

2. **Convergence paradigm flow**
   - Select "Drive a metric toward a target"
   - Enter custom metric command
   - Verify convergence FSM structure

3. **Invariants paradigm flow**
   - Select "Maintain code quality"
   - Add multiple constraints
   - Verify constraint chain in FSM

4. **Error handling**
   - Cancel mid-flow
   - Invalid custom commands
   - Name conflicts with existing loops

## Reference

- Design doc: `docs/generalized-fsm-loop.md` section "The /ll:create-loop Command"
