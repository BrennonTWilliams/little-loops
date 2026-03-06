---
discovered_commit: c010880ecfc0941e7a5a59cc071248a4b1cbc557
discovered_branch: main
discovered_date: 2026-03-06T04:46:40Z
discovered_by: scan-codebase
confidence_score: 100
outcome_confidence: 79
---

# BUG-602: `--max-iterations 0` silently ignored due to falsy check at 3 sites

## Summary

The `--max-iterations` CLI override uses truthiness checks (`if args.max_iterations:`) which treat `0` as falsy. A user passing `--max-iterations 0` gets the loop's configured default instead of `0`. This pattern appears in 3 locations: `cmd_run`, `cmd_simulate`, and `run_background`.

## Location

- **File**: `scripts/little_loops/cli/loop/run.py`
- **Line(s)**: 90-91 (at scan commit: c010880)
- **Anchor**: `in function cmd_run()`, "Apply overrides" block
- **Permalink**: [View on GitHub](https://github.com/BrennonTWilliams/little-loops/blob/c010880ecfc0941e7a5a59cc071248a4b1cbc557/scripts/little_loops/cli/loop/run.py#L90-L91)
- **Code**:
```python
if args.max_iterations:
    fsm.max_iterations = args.max_iterations
```

Additional locations:
- `scripts/little_loops/cli/loop/testing.py:181` — `cmd_simulate`
- `scripts/little_loops/cli/loop/_helpers.py:171` — `run_background`

## Current Behavior

`--max-iterations 0` is silently ignored because `0` is falsy in Python. The loop runs with its configured `max_iterations` value.

## Expected Behavior

`--max-iterations 0` should override the configured value to `0`. The check should use `if args.max_iterations is not None:` instead of truthiness.

## Steps to Reproduce

1. Run `ll-loop run my-loop --max-iterations 0`
2. Observe: loop runs with configured `max_iterations`, not `0`
3. No error or warning is emitted

## Root Cause

- **File**: `scripts/little_loops/cli/loop/run.py`
- **Anchor**: `in function cmd_run()`
- **Cause**: Truthiness check `if args.max_iterations:` is falsy for integer `0`. Should use `is not None` check.

## Proposed Solution

Replace all 3 sites with explicit `None` checks:

```python
# In run.py cmd_run and testing.py cmd_simulate:
if args.max_iterations is not None:
    fsm.max_iterations = args.max_iterations

# In _helpers.py run_background:
max_iter = getattr(args, "max_iterations", None)
if max_iter is not None:
    cmd.extend(["--max-iterations", str(max_iter)])
```

## Implementation Steps

1. Fix all 3 truthiness checks to use `is not None`
2. Add test cases for `--max-iterations 0`

## Impact

- **Priority**: P3 - Edge case but silent data loss of user intent
- **Effort**: Small - 3 one-line fixes
- **Risk**: Low - Narrowing a conditional check
- **Breaking Change**: No

## Labels

`bug`, `ll-loop`, `cli`

## Status

**Open** | Created: 2026-03-06 | Priority: P3

## Session Log
- `/ll:verify-issues` - 2026-03-06T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/27ebdb5b-fb8e-4a41-92d4-ab0eb38e4a35.jsonl` — VALID: `if args.max_iterations:` confirmed at `run.py:90`, `_helpers.py:171` (`if max_iter:`), `testing.py:180`
- `/ll:format-issue` - 2026-03-06T00:00:00Z - added `## Status` section to satisfy v2.0 template requirements
- `/ll:confidence-check` - 2026-03-06T00:00:00Z - Readiness: 100/100 PROCEED, Outcome: 79/100 MODERATE

---
