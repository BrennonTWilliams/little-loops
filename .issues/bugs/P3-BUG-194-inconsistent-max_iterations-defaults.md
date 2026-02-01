# Inconsistent max_iterations Defaults Between Documentation and Implementation

## Type
BUG

## Priority
P3

## Status
OPEN

## Description

The `/ll:create_loop` command documentation suggests paradigm-specific default values for `max_iterations`, but the actual implementation uses a universal default of 50 for all paradigms.

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
1. Run `/ll:create_loop`
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
