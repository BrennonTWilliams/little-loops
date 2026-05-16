# ll-loop test Output Format Differs from Documentation

## Type
BUG

## Priority
P4

## Status
COMPLETED

## Anchor
cmd_test in cli.py

## Description

The `/ll:create-loop` command documentation describes the `ll-loop test` output format in one way, but the actual CLI implementation produces different output.

**Documentation describes (lines 985-990):**
- Check command and exit code
- Output preview
- Evaluator type and verdict
- Would-transition target
- Success indicator or warning with specific issues

**Actual CLI implementation (`cli.py:1097-1212`):**
- Uses unicode symbols (✓, ✗, ⚠)
- Has different formatting
- Shows more technical details (truncated output, stderr preview)
- Return code is 0 for success, 1 for issues

**Actual output example:**
```
## Test Iteration: my-loop

State: check
Action: mypy src/

Exit code: 1
Output:
Found 3 errors in 1 file (checked 5 source files)

Evaluator: exit_code (default)
Verdict: FAILURE

Would transition: check → fix

✓ Loop appears to be configured correctly
```

**Evidence:**
- `commands/create_loop.md:985-990` - Documented test output format
- `scripts/little_loops/cli.py:1097-1212` - Actual test implementation

**Impact:**
Minor. Users expecting the exact documented format may see different output. However, all the key information is present.

## Files Affected
- `commands/create_loop.md`
- `scripts/little_loops/cli.py`

## Expected Behavior
Documentation should accurately reflect the actual output format, including:
- Unicode symbols
- "Verdict: FAILURE" (uppercase) vs "verdict: failure"
- Actual truncation behavior

## Actual Behavior
Documentation describes the output generically without the specific formatting details.

## Recommendation
Update the documentation to show an actual example output, or remove the detailed format description since it's subject to change.

## Related Issues
None

---

## Resolution

- **Action**: fix
- **Completed**: 2026-02-01
- **Status**: Completed

### Changes Made
- `commands/create_loop.md`: Replaced generic bullet list description (lines 985-990) with actual example output matching CLI implementation
- Added example code block showing real `ll-loop test` output format
- Updated description to clarify Unicode symbols (✓, ⚠) and truncation behavior

### Verification Results
- Tests: PASS (7/7 test_test tests passed)
- Documentation: Updated to match actual CLI output format at `cli.py:1097-1212`
