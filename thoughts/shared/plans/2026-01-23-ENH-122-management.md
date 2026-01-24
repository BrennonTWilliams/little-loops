# ENH-122: Add evaluator selection to loop creation wizard - Implementation Plan

## Issue Reference
- **File**: `.issues/enhancements/P2-ENH-122-add-evaluator-selection-to-loop-wizard.md`
- **Type**: enhancement
- **Priority**: P2
- **Action**: improve

## Current State Analysis

The `/ll:create_loop` wizard gathers paradigm-specific parameters (check/fix commands, max iterations, etc.) but never asks users HOW success should be determined for check commands. All paradigms except convergence use implicit exit code evaluation.

### Key Discoveries
- Wizard questions are in `commands/create_loop.md:27-344`
- Goal paradigm uses `on_success`/`on_failure` shortcuts at `compilers.py:144-148` with no explicit evaluator
- Invariants paradigm uses shortcuts at `compilers.py:314-317` with no explicit evaluator
- Imperative paradigm uses shortcuts at `compilers.py:401-405` with no explicit evaluator
- Only convergence paradigm has explicit `EvaluateConfig` at `compilers.py:218-223`
- `EvaluateConfig` supports 6 types: `exit_code`, `output_numeric`, `output_json`, `output_contains`, `convergence`, `llm_structured` (schema.py:51-58)
- Default runtime behavior: shell commands → exit_code, slash commands → llm_structured (executor.py:442-470)

### Current Behavior
1. User selects check commands (e.g., "mypy src/")
2. Wizard generates YAML with no evaluator configuration
3. Compilers create StateConfig with on_success/on_failure shortcuts
4. Runtime defaults to exit_code for shell commands

## Desired End State

After each check command is specified, the wizard asks users how to determine success:
1. Exit code (default) - success when exit code is 0
2. Output contains pattern - success when output contains specific text
3. Output numeric comparison - success when numeric output meets threshold
4. AI interpretation - let LLM analyze the output

The evaluator configuration is passed through to paradigm compilers and embedded in the generated YAML.

### How to Verify
- Wizard asks evaluator questions after check commands
- Generated paradigm YAML includes evaluator configuration
- Compilers pass evaluator config to StateConfig
- Tests verify evaluator flow for all paradigms

## What We're NOT Doing

- Not adding output_json or convergence evaluator types to wizard (convergence already has its own paradigm)
- Not changing existing loop files - only affects new loop creation
- Not modifying the FSM executor - it already supports all evaluator types
- Deferring smart per-tool defaults to ENH-124

## Problem Analysis

The gap between wizard and runtime: users specify WHAT to check but not HOW to evaluate results. This causes confusion when:
- Commands exit 0 but have warnings users care about
- Commands exit non-zero for benign reasons
- Success requires parsing output content

## Solution Approach

1. Add evaluator selection questions to the wizard after check commands
2. Add conditional follow-up questions for each evaluator type (pattern for contains, etc.)
3. Extend paradigm YAML schemas to include evaluator configuration
4. Update compilers to accept and use explicit evaluator configs in StateConfig

## Implementation Phases

### Phase 1: Update Wizard to Ask Evaluator Questions

#### Overview
Add evaluator selection questions to `commands/create_loop.md` after each check command is gathered.

#### Changes Required

**File**: `commands/create_loop.md`
**Changes**: Add evaluator question template and conditional follow-ups after check command collection

Insert after each paradigm's check command collection (lines ~92, ~155, ~236, ~302) an evaluator question block:

```markdown
**Evaluator Selection** (ask after each check command is specified):

```yaml
questions:
  - question: "How should success be determined for '[CHECK_COMMAND]'?"
    header: "Evaluator"
    multiSelect: false
    options:
      - label: "Exit code (Recommended)"
        description: "Success if command exits with code 0"
      - label: "Output contains pattern"
        description: "Success if output contains specific text"
      - label: "Output is numeric"
        description: "Compare numeric output to threshold"
      - label: "AI interpretation"
        description: "Let Claude analyze the output"
```

**If "Output contains pattern" was selected**, ask:
```yaml
questions:
  - question: "What pattern indicates success?"
    header: "Pattern"
    multiSelect: false
    options:
      - label: "Success"
        description: "Match the word 'Success' in output"
      - label: "0 errors"
        description: "Match '0 errors' in output"
      - label: "PASSED"
        description: "Match 'PASSED' in output"
      - label: "Custom pattern"
        description: "Specify your own pattern"
```

**If "Output is numeric" was selected**, ask:
```yaml
questions:
  - question: "What numeric condition indicates success?"
    header: "Condition"
    multiSelect: false
    options:
      - label: "Equals 0"
        description: "Success if output equals 0"
      - label: "Less than target"
        description: "Success if output is below a threshold"
      - label: "Greater than target"
        description: "Success if output is above a threshold"
```
If "Less than target" or "Greater than target" selected, ask for target value via Other.
```

Also update the paradigm YAML templates to include optional evaluator field.

#### Success Criteria

**Automated Verification**:
- [ ] Lint passes: `ruff check commands/`

**Manual Verification**:
- [ ] Run `/ll:create_loop` and verify evaluator question appears after check command selection

---

### Phase 2: Update Paradigm YAML Templates

#### Overview
Extend the generated YAML examples to include optional evaluator configuration.

#### Changes Required

**File**: `commands/create_loop.md`
**Changes**: Update YAML generation templates for each paradigm

For **Goal paradigm** (around line 98-118), update template:

```yaml
paradigm: goal
name: "<loop-name>"
goal: "<description of what passes>"
tools:
  - "<check-command>"
  - "<fix-command>"
max_iterations: <selected-max>
evaluator:                    # NEW: Optional evaluator config
  type: "<exit_code|output_contains|output_numeric|llm_structured>"
  pattern: "<pattern>"        # For output_contains
  target: <number>            # For output_numeric
  operator: "<eq|lt|gt>"      # For output_numeric
```

For **Invariants paradigm** (around line 166-197), update template:

```yaml
paradigm: invariants
name: "<loop-name>"
constraints:
  - name: "<constraint-1-name>"
    check: "<check-command>"
    fix: "<fix-command>"
    evaluator:                # NEW: Optional per-constraint evaluator
      type: "<type>"
      # ... type-specific fields
```

For **Imperative paradigm** (around line 316-344), update template:

```yaml
paradigm: imperative
name: "<loop-name>"
steps:
  - "<step-1>"
  - "<step-2>"
until:
  check: "<exit-condition-command>"
  passes: true
  evaluator:                  # NEW: Optional evaluator for exit condition
    type: "<type>"
```

#### Success Criteria

**Automated Verification**:
- [ ] Lint passes: `ruff check commands/`

---

### Phase 3: Update Goal Paradigm Compiler

#### Overview
Modify `compile_goal()` to accept and use evaluator configuration from spec.

#### Changes Required

**File**: `scripts/little_loops/fsm/compilers.py`
**Changes**: Update compile_goal function to extract evaluator from spec and pass to StateConfig

```python
def compile_goal(spec: dict[str, Any]) -> FSMLoop:
    # ... existing validation ...

    goal = spec["goal"]
    tools = spec["tools"]
    check_tool = tools[0]
    fix_tool = tools[1] if len(tools) > 1 else tools[0]

    name = spec.get("name", f"goal-{_slugify(goal)}")

    # NEW: Extract evaluator config if provided
    evaluator_spec = spec.get("evaluator")
    evaluate_config = None
    if evaluator_spec:
        evaluate_config = EvaluateConfig(
            type=evaluator_spec["type"],
            pattern=evaluator_spec.get("pattern"),
            target=evaluator_spec.get("target"),
            operator=evaluator_spec.get("operator"),
        )

    states = {
        "evaluate": StateConfig(
            action=check_tool,
            evaluate=evaluate_config,  # NEW: Pass evaluator
            on_success="done",
            on_failure="fix",
            on_error="fix",
        ),
        # ... rest unchanged ...
    }
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_fsm_compilers.py -v`
- [ ] Types pass: `python -m mypy scripts/little_loops/fsm/compilers.py`
- [ ] Lint passes: `ruff check scripts/little_loops/fsm/compilers.py`

---

### Phase 4: Update Invariants Paradigm Compiler

#### Overview
Modify `compile_invariants()` to accept per-constraint evaluator configuration.

#### Changes Required

**File**: `scripts/little_loops/fsm/compilers.py`
**Changes**: Update compile_invariants to extract evaluator from each constraint

```python
def compile_invariants(spec: dict[str, Any]) -> FSMLoop:
    # ... existing code ...

    for i, constraint in enumerate(constraints):
        check_state = f"check_{constraint['name']}"
        fix_state = f"fix_{constraint['name']}"

        next_check = (
            f"check_{constraints[i + 1]['name']}" if i + 1 < len(constraints) else "all_valid"
        )

        # NEW: Extract evaluator config if provided
        evaluator_spec = constraint.get("evaluator")
        evaluate_config = None
        if evaluator_spec:
            evaluate_config = EvaluateConfig(
                type=evaluator_spec["type"],
                pattern=evaluator_spec.get("pattern"),
                target=evaluator_spec.get("target"),
                operator=evaluator_spec.get("operator"),
            )

        states[check_state] = StateConfig(
            action=constraint["check"],
            evaluate=evaluate_config,  # NEW: Pass evaluator
            on_success=next_check,
            on_failure=fix_state,
        )
        # ... fix state unchanged ...
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_fsm_compilers.py -v`
- [ ] Types pass: `python -m mypy scripts/little_loops/fsm/compilers.py`
- [ ] Lint passes: `ruff check scripts/little_loops/fsm/compilers.py`

---

### Phase 5: Update Imperative Paradigm Compiler

#### Overview
Modify `compile_imperative()` to accept evaluator configuration for the exit condition check.

#### Changes Required

**File**: `scripts/little_loops/fsm/compilers.py`
**Changes**: Update compile_imperative to extract evaluator from until block

```python
def compile_imperative(spec: dict[str, Any]) -> FSMLoop:
    # ... existing code ...

    name = spec["name"]
    steps = spec["steps"]
    until_check = spec["until"]["check"]

    # NEW: Extract evaluator config if provided
    evaluator_spec = spec["until"].get("evaluator")
    evaluate_config = None
    if evaluator_spec:
        evaluate_config = EvaluateConfig(
            type=evaluator_spec["type"],
            pattern=evaluator_spec.get("pattern"),
            target=evaluator_spec.get("target"),
            operator=evaluator_spec.get("operator"),
        )

    # ... step states unchanged ...

    # Create check_done state
    states["check_done"] = StateConfig(
        action=until_check,
        evaluate=evaluate_config,  # NEW: Pass evaluator
        on_success="done",
        on_failure="step_0",
    )
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_fsm_compilers.py -v`
- [ ] Types pass: `python -m mypy scripts/little_loops/fsm/compilers.py`
- [ ] Lint passes: `ruff check scripts/little_loops/fsm/compilers.py`

---

### Phase 6: Add Compiler Tests for Evaluator Support

#### Overview
Add tests to verify evaluator configuration is correctly passed through compilers.

#### Changes Required

**File**: `scripts/tests/test_fsm_compilers.py`
**Changes**: Add test cases for each paradigm with evaluator config

```python
def test_compile_goal_with_evaluator():
    """Goal paradigm passes evaluator config to evaluate state."""
    spec = {
        "paradigm": "goal",
        "goal": "Lint passes",
        "tools": ["ruff check src/", "ruff check --fix src/"],
        "evaluator": {
            "type": "output_contains",
            "pattern": "All checks passed",
        },
    }
    fsm = compile_goal(spec)

    assert fsm.states["evaluate"].evaluate is not None
    assert fsm.states["evaluate"].evaluate.type == "output_contains"
    assert fsm.states["evaluate"].evaluate.pattern == "All checks passed"


def test_compile_invariants_with_evaluator():
    """Invariants paradigm passes per-constraint evaluator config."""
    spec = {
        "paradigm": "invariants",
        "name": "quality-gate",
        "constraints": [
            {
                "name": "lint",
                "check": "ruff check src/",
                "fix": "ruff check --fix src/",
                "evaluator": {
                    "type": "output_contains",
                    "pattern": "0 errors",
                },
            },
        ],
    }
    fsm = compile_invariants(spec)

    assert fsm.states["check_lint"].evaluate is not None
    assert fsm.states["check_lint"].evaluate.type == "output_contains"


def test_compile_imperative_with_evaluator():
    """Imperative paradigm passes evaluator config to check_done state."""
    spec = {
        "paradigm": "imperative",
        "name": "build-loop",
        "steps": ["npm run build"],
        "until": {
            "check": "npm test",
            "evaluator": {
                "type": "output_numeric",
                "operator": "eq",
                "target": 0,
            },
        },
    }
    fsm = compile_imperative(spec)

    assert fsm.states["check_done"].evaluate is not None
    assert fsm.states["check_done"].evaluate.type == "output_numeric"
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_fsm_compilers.py -v -k evaluator`
- [ ] Lint passes: `ruff check scripts/tests/test_fsm_compilers.py`

---

### Phase 7: Update FSM Preview in Wizard

#### Overview
Update the FSM preview section to show evaluator type when configured.

#### Changes Required

**File**: `commands/create_loop.md`
**Changes**: Enhance preview format to include evaluator info

Update the preview format (around line 450-485):

```markdown
**Display format:**

```
Here's your loop configuration:

## Paradigm YAML
```yaml
<generated-yaml>
```

## Compiled FSM Preview
States: <state1> → <state2> → ... → <terminal>
Transitions:
  <state1>: <verdict>→<target>, <verdict>→<target>
  <state2>: next→<target>
  ...
  <terminal>: [terminal]
Initial: <initial-state>
Max iterations: <max_iterations>
Evaluator: <type> [<pattern|target>]  # NEW LINE

This will create: .loops/<name>.yaml
```
```

#### Success Criteria

**Automated Verification**:
- [ ] Lint passes: `ruff check commands/`

---

## Testing Strategy

### Unit Tests
- Test each compiler function with evaluator config present
- Test each compiler function with evaluator config absent (backward compatibility)
- Test various evaluator types: exit_code, output_contains, output_numeric, llm_structured

### Integration Tests
- Create loop via wizard with evaluator selection
- Verify generated YAML contains evaluator config
- Run `ll-loop validate` on generated loop
- Run `ll-loop test` to verify evaluator works at runtime

## References

- Original issue: `.issues/enhancements/P2-ENH-122-add-evaluator-selection-to-loop-wizard.md`
- Related pattern (convergence evaluator): `compilers.py:218-223`
- EvaluateConfig definition: `schema.py:22-125`
- Existing wizard questions: `create_loop.md:27-344`
