# BUG-194: Inconsistent max_iterations Defaults Between Documentation and Implementation - Implementation Plan

## Issue Reference
- **File**: `.issues/bugs/P3-BUG-194-inconsistent-max_iterations-defaults.md`
- **Type**: bug
- **Priority**: P3
- **Action**: fix

## Current State Analysis

### Key Discoveries
- **Universal default**: All paradigms default to `max_iterations: 50` in code (`scripts/little_loops/fsm/compilers.py:199, 282, 381, 466`)
- **Schema default**: `FSMLoop.max_iterations` defaults to 50 (`scripts/little_loops/fsm/schema.py:357`)
- **Documentation inconsistency**: Command documentation shows different "Recommended" values (10 for goal, 20 for imperative) that don't match actual defaults

### Documentation vs Implementation Mismatch

| Paradigm | Compiler Default | Template/Example | Recommended in UI | Consistent? |
|----------|------------------|------------------|-------------------|-------------|
| Goal | 50 | 10 (example) | 10 (custom mode), 20 (template) | **No** |
| Convergence | 50 | 50 (template) | N/A | **Yes** |
| Invariants | 50 | 50 (template) | N/A | **Yes** |
| Imperative | 50 | 20 (template) | N/A | **No** |

### Root Cause
The `/ll:create_loop` command documentation presents max_iterations options as "Recommended" (e.g., "10 (Recommended)" for goal paradigm), but these are actually **suggested explicit values** based on use case, not **implemented defaults**. When users omit `max_iterations` from their YAML, all paradigms default to 50.

## Desired End State

Documentation should clearly distinguish between:
1. **Implemented default** (50) - used when `max_iterations` is omitted from YAML
2. **Suggested values** (10, 20, 50) - recommended starting points to explicitly specify based on use case

### How to Verify
- Documentation clarifies that "(Recommended)" values are suggestions for explicit specification
- Templates and examples either show the actual default (50) or include explicit values
- Docstring examples align with actual behavior
- Tests continue to pass (verifying default of 50)

## What We're NOT Doing

- **Not changing implementation defaults** - Keeping universal default of 50 for all paradigms
- **Not adding paradigm-specific defaults** - This would require code changes and increase complexity
- **Not modifying schema** - Default of 50 in `FSMLoop` dataclass remains
- **Not breaking backward compatibility** - Existing YAML without max_iterations continues to work

## Problem Analysis

**Why this approach?**
1. **Simpler fix**: Documentation-only change avoids code complexity
2. **Preserves flexibility**: Universal default of 50 works for all paradigms
3. **Follows existing patterns**: Similar to ENH-195 (tool evaluator defaults) - add disclaimer rather than implement auto-detection
4. **User clarity**: Users understand the difference between "default" and "recommended value"

**Alternative considered but rejected**: Implement paradigm-specific defaults (10 for goal, 20 for imperative, 50 for others). This would:
- Require changes to 4 compiler functions
- Update schema defaults
- Break existing YAMLs that rely on universal 50 default
- Add unnecessary complexity for minimal benefit

## Solution Approach

Following the pattern from ENH-195 and P4-ENH-201, update documentation to clarify that:
1. "(Recommended)" options are suggestions for explicit values based on use case
2. The actual runtime default is 50 for all paradigms
3. Users should explicitly specify max_iterations if they want something different

## Implementation Phases

### Phase 1: Update Goal Paradigm Documentation

#### Overview
Add clarifying language to goal paradigm max_iterations question to distinguish between recommended explicit value and actual default.

#### Changes Required

**File**: `commands/create_loop.md`
**Location**: Lines 252-262
**Changes**: Add clarification note after the max_iterations options

```yaml
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

> **Note**: The runtime default is 50 for all paradigms. These options are suggested starting points to explicitly specify in your YAML based on your use case.
```

**Success Criteria**

**Automated Verification**:
- [x] N/A - Documentation-only change, no automated test applicable

**Manual Verification**:
- [ ] Read the goal paradigm section and verify clarification note is present
- [ ] Verify note clearly distinguishes between "(Recommended)" options and actual default
- [ ] Verify YAML examples still render correctly

---

### Phase 2: Update Template Mode Documentation

#### Overview
Add clarification to template mode max_iterations question.

#### Changes Required

**File**: `commands/create_loop.md`
**Location**: Lines 171-181 (template customization question)
**Changes**: Add clarification note

```yaml
  - question: "What's the maximum number of fix attempts?"
    header: "Max iterations"
    options:
      - label: "20 (Recommended)"
        description: "Good balance for most loops"
      - label: "10"
        description: "Quick iterations for focused tasks"
      - label: "50"
        description: "Maximum for long-running loops"

> **Note**: Your selection will be explicitly set in the generated YAML. If omitted later, the default is 50.
```

**Success Criteria**

**Manual Verification**:
- [ ] Verify clarification note is present in template mode section
- [ ] Verify note explains that selection is explicitly set in YAML

---

### Phase 3: Update Imperative Paradigm Template

#### Overview
Update imperative paradigm template to show actual default (50) instead of 20.

#### Changes Required

**File**: `commands/create_loop.md`
**Location**: Lines 670, 685
**Changes**: Change `max_iterations: 20` to `max_iterations: 50` with note

Before (line 670):
```yaml
max_iterations: 20
```

After:
```yaml
max_iterations: 50  # Default if omitted
```

Before (line 685 example):
```yaml
max_iterations: 20
```

After:
```yaml
max_iterations: 50  # Default if omitted
```

**Success Criteria**

**Manual Verification**:
- [ ] Verify imperative template shows 50 as default
- [ ] Verify imperative example shows 50 as default
- [ ] Verify comment explains "Default if omitted"

---

### Phase 4: Update Docstring Examples

#### Overview
Clarify in compiler docstrings that example values (20) are examples, not defaults.

#### Changes Required

**File**: `scripts/little_loops/fsm/compilers.py`
**Location**: Lines 148, 409
**Changes**: Update docstring comments to clarify

Before (line 148):
```python
        max_iterations: 20            # Optional, defaults to 50
```

After:
```python
        max_iterations: 50            # Optional, defaults to 50 (examples show 20 for brevity)
```

Before (line 409):
```python
        max_iterations: 20
```

After:
```python
        max_iterations: 50            # Optional, defaults to 50 (examples show 20 for brevity)
```

**Success Criteria**

**Manual Verification**:
- [ ] Verify goal paradigm docstring clarifies example vs default
- [ ] Verify imperative paradigm docstring clarifies example vs default
- [ ] Verify both explicitly state "defaults to 50"

---

## Testing Strategy

### Unit Tests
- No new tests required - existing tests verify default of 50
- Tests in `test_fsm_compilers.py:613-623` verify default behavior

### Manual Verification
- Review command documentation for clarity
- Verify all clarification notes are present
- Ensure YAML examples are valid and clear

## References

- Original issue: `.issues/bugs/P3-BUG-194-inconsistent-max_iterations-defaults.md`
- Related pattern: `.issues/enhancements/P4-ENH-195-tool-evaluator-defaults-is-docs-only.md`
- Related pattern: `.issues/completed/P4-ENH-186-harmonize-timeout-defaults.md`
- Compiler code: `scripts/little_loops/fsm/compilers.py`
- Schema code: `scripts/little_loops/fsm/schema.py`
- Command documentation: `commands/create_loop.md`
