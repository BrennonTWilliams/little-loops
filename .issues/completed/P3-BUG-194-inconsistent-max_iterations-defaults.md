# Inconsistent max_iterations Defaults Between Documentation and Implementation

## Type
BUG

## Priority
P3

## Status
OPEN

## Description

The `/ll:create-loop` command documentation suggests paradigm-specific default values for `max_iterations`, but the actual implementation uses a universal default of 50 for all paradigms.

**Documentation suggests:**
- Goal paradigm: "10 (Recommended)"
- Imperative paradigm: "20"
- Convergence/Invariants: Examples show 50

**Implementation actual:**
- All paradigms default to 50 in `compilers.py`

**Evidence:**
- `commands/create_loop.md:256-261` - Goal shows "10 (Recommended)"
- `commands/create_loop.md:659` - Imperative shows `max_iterations: 20`
- `scripts/little_loops/fsm/compilers.py:199` - Goal defaults to 50
- `scripts/little_loops/fsm/compilers.py:282` - Convergence defaults to 50
- `scripts/little_loops/fsm/compilers.py:381` - Invariants defaults to 50
- `scripts/little_loops/fsm/compilers.py:466` - Imperative defaults to 50

**Impact:**
User confusion. Users selecting "10 (Recommended)" for goal paradigm will get 50 as the default if they don't explicitly specify a value.

## Files Affected
- `commands/create_loop.md`
- `scripts/little_loops/fsm/compilers.py`

## Steps to Reproduce
1. Run `/ll:create-loop`
2. Select "Fix errors until clean" (goal paradigm)
3. Select "10 (Recommended)" for max iterations
4. Skip to preview - the generated YAML may not include the explicit value
5. The loop will execute with 50 as the default

## Expected Behavior
Either:
1. **Fix documentation** - Show 50 as the universal default for all paradigms
2. **Fix implementation** - Use paradigm-specific defaults (10 for goal, 20 for imperative, 50 for others)

## Actual Behavior
Documentation implies different defaults per paradigm, but code uses universal 50.

## Recommendation
Approach 1 (simpler): Update documentation to clarify 50 is the universal default, and the recommendations are just suggestions for explicit values based on use case.

## Related Issues
None

---

## Resolution

- **Action**: fix
- **Completed**: 2026-02-01
- **Status**: Completed

### Changes Made
- `commands/create_loop.md`: Added clarification notes to goal paradigm and template mode max_iterations questions, explaining that "(Recommended)" values are suggestions for explicit specification and the actual runtime default is 50
- `commands/create_loop.md`: Updated imperative paradigm template and examples to show `max_iterations: 50  # Default if omitted` instead of 20
- `scripts/little_loops/fsm/compilers.py`: Updated docstring examples in `compile_goal()` and `compile_imperative()` to clarify that example values (20) are for brevity and actual default is 50

### Verification Results
- Tests: PASS (2124 passed)
- Lint: PASS (no new errors in modified files)
