---
discovered_date: 2026-01-23
discovered_by: capture_issue
---

# ENH-125: Add test iteration after loop creation

## Summary

After the `/ll:create_loop` wizard saves a new loop, offer to run one test iteration to verify the loop actually works before the user relies on it.

## Context

Identified from conversation analyzing why created loops don't work. Users create loops, assume they work, then discover issues when running them for real. A validation step after creation would catch problems early.

## Current Behavior

After saving, the wizard reports success and shows the run command:

```
Loop created successfully!
Run now with: ll-loop <name>
```

No actual validation that the check command runs, produces parseable output, or that transitions work correctly.

## Expected Behavior

After saving and validating schema, offer:

```yaml
questions:
  - question: "Would you like to run a test iteration to verify the loop works?"
    header: "Test run"
    options:
      - label: "Yes, run one iteration (Recommended)"
        description: "Execute check command and verify evaluation works"
      - label: "No, I'll test manually"
        description: "Skip test iteration"
```

If yes:
1. Run the check command once
2. Show the output
3. Show what the evaluator determined (success/failure/progress)
4. Show which transition would be taken
5. Report any issues (command failed, output not parseable, etc.)

Example output:
```
## Test Iteration Results

Check command: mypy src/
Exit code: 1
Output: Found 3 errors in 2 files

Evaluator: exit_code
Result: FAILURE (exit code != 0)
Would transition: evaluate → fix

✓ Loop appears to be working correctly
```

Or if problems:
```
## Test Iteration Results

Check command: ruff check src/ --output-format=json | jq '.length'
Exit code: 0
Output: [not a number - jq parse error]

Evaluator: output_numeric
Result: ERROR (could not parse numeric value)

⚠ Loop has issues:
- Check command output is not parseable as a number
- Verify jq is installed and the JSON path is correct
```

## Proposed Solution

1. Add optional test iteration step after Step 5 (Save and Validate)
2. Execute just the check action from the initial state
3. Run the evaluator logic on the output
4. Display human-readable results
5. Warn about any issues that would cause the loop to fail

## Impact

- **Priority**: P3 (catches problems early)
- **Effort**: Medium (invoke executor for single step)
- **Risk**: Low (optional, read-only test)

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| commands | commands/create_loop.md | Wizard to extend |
| architecture | scripts/little_loops/fsm/executor.py | Execution logic to leverage |
| architecture | scripts/little_loops/fsm/evaluators.py | Evaluator logic to test |

## Labels

`enhancement`, `create-loop`, `validation`, `ux`, `captured`

---

## Resolution

- **Action**: implement
- **Completed**: 2026-01-23
- **Status**: Completed

### Changes Made
- `scripts/little_loops/cli.py`: Added `cmd_test()` function and `test` subcommand to `ll-loop` CLI
- `commands/create_loop.md`: Added Step 5.5 to offer test iteration after validation
- `scripts/tests/test_ll_loop.py`: Added TestCmdTest class with 7 test cases

### Verification Results
- Tests: PASS (143 tests, including 7 new tests)
- Lint: PASS
- Types: PASS

---

## Status

**Completed** | Created: 2026-01-23 | Priority: P3
