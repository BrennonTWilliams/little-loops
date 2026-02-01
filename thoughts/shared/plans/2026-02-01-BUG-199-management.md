# BUG-199: ll-loop test Output Format Differs from Documentation - Implementation Plan

## Issue Reference
- **File**: `.issues/bugs/P4-BUG-199-test-output-format-mismatch.md`
- **Type**: bug
- **Priority**: P4
- **Action**: fix

## Current State Analysis

The documentation at `commands/create_loop.md:985-990` describes the test output in generic terms:
- Check command and exit code
- Output preview
- Evaluator type and verdict
- Would-transition target
- Success indicator or warning with specific issues

However, the actual CLI implementation (`scripts/little_loops/cli.py:1097-1212`) produces output with specific formatting:
- Uses Unicode symbols (✓, ⚠)
- Uses uppercase "Verdict: FAILURE/SUCCESS/ERROR" (line 1173: `.upper()`)
- Shows truncation indicators with line counts
- Has specific section headers

### Key Discoveries
- `cli.py:1173` - Verdict is displayed using `.upper()` so it's uppercase, not lowercase
- `cli.py:1105, 1122, 1211` - Uses ✓ (U+2713) for success/valid states
- `cli.py:1208` - Uses ⚠ (U+26A0) for error states (NOT ✗ as mentioned in issue)
- `cli.py:1134-1136` - Output truncation: >10 lines shows first 10 + `... (N more lines)`
- `cli.py:1137-1138` - Character truncation: >500 chars shows first 500 + `...`
- `cli.py:1146-1148` - Stderr truncation: >5 lines shows first 5 + `... (N more lines)`

## Desired End State

The documentation should show an actual example output that matches the CLI implementation exactly, so users know what to expect.

### How to Verify
- Compare documentation example with actual `ll-loop test` output
- Ensure Unicode symbols match
- Ensure formatting matches (uppercase Verdict, truncation format)

## What We're NOT Doing
- Not changing the CLI implementation - the documentation needs to match the code
- Not refactoring the test command output format
- Not adding new features to the test command

## Problem Analysis

The documentation was likely written before the implementation was finalized, or was intentionally generic to avoid being tied to implementation details. However, this creates confusion for users who expect the exact format shown in docs.

## Solution Approach

Replace the generic bullet list (lines 985-990) with an actual example output block. This follows Pattern 4 from the codebase documentation patterns, showing real command output examples.

## Implementation Phases

### Phase 1: Update Documentation with Actual Example

#### Overview
Replace the generic test output description with an actual example that matches the CLI implementation.

#### Changes Required

**File**: `commands/create_loop.md`
**Changes**: Replace lines 985-990 with actual example output

```markdown
   Display the test output directly. Example output:

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

   The test command validates your loop configuration by running one iteration:
   - Shows the state and action being tested
   - Displays exit code and output (truncated if long)
   - Reports evaluator type and verdict
   - Indicates what transition would occur
   - Uses ✓ when structure is valid, ⚠ when errors are detected
```

#### Success Criteria

**Automated Verification**:
- [ ] Documentation file is syntactically valid Markdown
- [ ] No unintended changes to surrounding content

**Manual Verification**:
- [ ] Example matches actual `ll-loop test` output format
- [ ] Unicode symbols (✓, ⚠) display correctly
- [ ] "Verdict: FAILURE" is uppercase as in actual output
- [ ] Transition arrow format matches (→)

### Phase 2: Verify Documentation Accuracy

#### Overview
Run the actual test command to verify the documentation example is accurate.

#### Changes Required

No code changes - just verification.

#### Success Criteria

**Manual Verification**:
- [ ] Create a test loop and run `ll-loop test`
- [ ] Compare actual output with documentation example
- [ ] Confirm all formatting elements match

## Testing Strategy

### Manual Testing
- Create a simple loop configuration
- Run `ll-loop test <name>`
- Verify output matches documentation example

### Edge Cases to Document
The documentation example shows a simple case. Consider mentioning:
- Long output truncation behavior
- Empty output handling
- Slash command skip behavior

## References

- Original issue: `.issues/bugs/P4-BUG-199-test-output-format-mismatch.md`
- Implementation: `scripts/little_loops/cli.py:1064-1212`
- Similar documentation pattern: `commands/capture_issue.md:582-598` (uses example output)
- Test coverage: `scripts/tests/test_ll_loop.py:3148+` (TestCmdTest class)
