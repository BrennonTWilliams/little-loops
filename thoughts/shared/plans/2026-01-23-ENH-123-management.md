# ENH-123: Preview compiled FSM before saving - Implementation Plan

## Issue Reference
- **File**: `.issues/enhancements/P3-ENH-123-preview-compiled-fsm-before-saving.md`
- **Type**: enhancement
- **Priority**: P3
- **Action**: implement

## Current State Analysis

The `/ll:create_loop` wizard at `commands/create_loop.md:369-394` shows only paradigm YAML before saving:

```
Here's your loop configuration:

```yaml
<generated-yaml>
```

This will create: .loops/<name>.yaml
```

Users cannot see the compiled FSM states and transitions that will be generated from this paradigm.

### Key Discoveries
- `print_execution_plan()` at `cli.py:557-591` shows FSM structure for dry-run mode
- Each paradigm compiler generates specific state patterns:
  - **Goal**: evaluate → fix → done (3 states)
  - **Convergence**: measure → apply → done (3 states)
  - **Invariants**: check_{name}/fix_{name} pairs → all_valid (variable states)
  - **Imperative**: step_0 → step_1 → ... → check_done → done (variable states)
- `commands/create_loop.md` is a Claude Code command file that instructs Claude - it doesn't execute Python directly

## Desired End State

Step 4 of the wizard shows both paradigm YAML AND a human-readable FSM preview:

```
Here's your loop configuration:

## Paradigm YAML
```yaml
<generated-yaml>
```

## Compiled FSM Preview
States: evaluate → fix → done
Transitions:
  evaluate: success→done, failure→fix, error→fix
  fix: (unconditional)→evaluate
  done: [terminal]
Initial: evaluate
Max iterations: 50

This will create: .loops/<name>.yaml
```

### How to Verify
- Run `/ll:create_loop` and complete the wizard
- At Step 4, FSM preview should appear alongside paradigm YAML
- Preview should accurately reflect the states/transitions for the chosen paradigm

## What We're NOT Doing

- Not adding Python functions - the command file instructs Claude what to display
- Not changing the actual compilation logic
- Not adding CLI integration - this is purely a wizard UX improvement

## Problem Analysis

The wizard generates paradigm YAML but doesn't show the resulting FSM structure. Since `create_loop.md` is a Claude Code command (markdown instructions), the solution must provide Claude with:
1. Rules for what FSM states each paradigm generates
2. Format template for displaying the FSM preview
3. Integration point in Step 4 to show the preview

## Solution Approach

Add a new section to `commands/create_loop.md` that:
1. Documents the FSM structure each paradigm generates (reference for Claude)
2. Provides a preview format template
3. Updates Step 4 to include FSM preview generation before confirmation

This is a documentation/instruction update, not code change.

## Implementation Phases

### Phase 1: Add FSM Structure Reference

#### Overview
Add a reference section documenting the FSM states and transitions each paradigm generates.

#### Changes Required

**File**: `commands/create_loop.md`
**Location**: After paradigm configuration sections, before Step 4
**Changes**: Add new section "FSM Compilation Reference"

```markdown
---

## FSM Compilation Reference

Each paradigm compiles to a specific FSM structure. Use this reference when generating the FSM preview.

### Goal Paradigm FSM
```
States: evaluate, fix, done
Initial: evaluate

Transitions:
  evaluate:
    - on_success → done
    - on_failure → fix
    - on_error → fix
  fix:
    - next → evaluate
  done: [terminal]
```

### Convergence Paradigm FSM
```
States: measure, apply, done
Initial: measure

Transitions:
  measure:
    - route[target] → done
    - route[progress] → apply
    - route[stall] → done
  apply:
    - next → measure
  done: [terminal]
```

### Invariants Paradigm FSM
For each constraint `{name}` in order:
```
States: check_{name1}, fix_{name1}, check_{name2}, fix_{name2}, ..., all_valid
Initial: check_{first_constraint}

Transitions:
  check_{name}:
    - on_success → check_{next} (or all_valid if last)
    - on_failure → fix_{name}
  fix_{name}:
    - next → check_{name}
  all_valid: [terminal]
    - on_maintain → check_{first} (if maintain: true)
```

### Imperative Paradigm FSM
For each step in order:
```
States: step_0, step_1, ..., step_N, check_done, done
Initial: step_0

Transitions:
  step_N:
    - next → step_{N+1} (or check_done if last)
  check_done:
    - on_success → done
    - on_failure → step_0
  done: [terminal]
```
```

#### Success Criteria

**Automated Verification**:
- [ ] Lint passes: `ruff check commands/`
- [ ] File is valid markdown (no syntax errors)

**Manual Verification**:
- [ ] Reference section is clear and matches actual compiler behavior

---

### Phase 2: Update Step 4 Preview Format

#### Overview
Modify Step 4 to include FSM preview generation instructions.

#### Changes Required

**File**: `commands/create_loop.md`
**Location**: Step 4: Preview and Confirm section (lines 369-394)
**Changes**: Replace current preview with dual-section preview

```markdown
### Step 4: Preview and Confirm

Generate and display both the paradigm YAML and the compiled FSM preview.

**Generate FSM Preview:**

Based on the paradigm selected, generate the FSM preview using the reference above:

1. List states in execution order (use → between states)
2. Show transitions for each non-terminal state
3. Mark terminal states with `[terminal]`
4. Note unconditional transitions as `(unconditional)→target`
5. Include initial state and max_iterations

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
  <state2>: (unconditional)→<target>
  ...
  <terminal>: [terminal]
Initial: <initial-state>
Max iterations: <max_iterations or 50>

This will create: .loops/<name>.yaml
```

Use AskUserQuestion:
```yaml
questions:
  - question: "Save this loop configuration?"
    header: "Confirm"
    multiSelect: false
    options:
      - label: "Yes, save and validate"
        description: "Save to .loops/<name>.yaml and run validation"
      - label: "No, start over"
        description: "Discard and restart the wizard"
```
```

#### Success Criteria

**Automated Verification**:
- [ ] Lint passes: `ruff check commands/`
- [ ] File is valid markdown

**Manual Verification**:
- [ ] Running `/ll:create_loop` and completing wizard shows FSM preview at Step 4
- [ ] Preview accurately reflects paradigm-specific states and transitions
- [ ] Goal paradigm shows: evaluate → fix → done
- [ ] Convergence paradigm shows: measure → apply → done with route verdicts
- [ ] Invariants paradigm shows constraint check/fix pairs
- [ ] Imperative paradigm shows step sequence

---

## Testing Strategy

### Manual Tests
1. Run `/ll:create_loop` with goal paradigm - verify preview shows evaluate/fix/done
2. Run `/ll:create_loop` with convergence paradigm - verify preview shows measure/apply/done
3. Run `/ll:create_loop` with invariants paradigm - verify preview shows constraint chain
4. Run `/ll:create_loop` with imperative paradigm - verify preview shows step sequence

### Verification
- Compare preview output to actual compiled FSM (run `ll-loop compile` on saved file)

## References

- Original issue: `.issues/enhancements/P3-ENH-123-preview-compiled-fsm-before-saving.md`
- CLI execution plan display: `scripts/little_loops/cli.py:557-591`
- Paradigm compilers: `scripts/little_loops/fsm/compilers.py`
- Wizard implementation: `commands/create_loop.md:369-394`
