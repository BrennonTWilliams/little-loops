# BUG-711: Built-in FSM Loop Configuration Audit Fixes

## Summary

Audited all 19 built-in FSM loop configs in `loops/` for logical correctness, FSM design quality, and simplification opportunities. Found and fixed 8 bugs and applied 6 simplifications.

## Bugs Fixed

### 1. Invalid `action_type: decision` (issue-refinement.yaml, sync-and-close.yaml)
`StateConfig.action_type` is `Literal["prompt", "slash_command", "shell"] | None`. The value `"decision"` worked by accident but fails type checking. Removed `action_type: decision` from 3 states — the executor handles decision states correctly via `evaluate` with `source` and no action.

### 2. Undefined captured variable reference (docs-sync.yaml)
`fix_docs` referenced `${captured.link_results.output}` but `link_results` is only set in `check_links`. If `fix_docs` was reached from `verify_docs` failure before `check_links` ran, interpolation would fail. Restructured: both checks always run before routing to `fix_docs` via a new `route_results` decision state.

### 3. Infinite loop on reverted dead code (dead-code-cleanup.yaml)
When dead code removal broke tests and was reverted, the next scan re-discovered the same items indefinitely (only stopped by `max_iterations: 15`). Added exclusion tracking: reverted items are appended to `/tmp/ll-dead-code-excluded.txt` and filtered out in subsequent scans.

### 4. macOS incompatibility (worktree-health.yaml)
`xargs -r` is a GNU extension unavailable on macOS. Replaced with `while read -r b; do git branch -d "$b"; done`.

### 5. Fragile numeric interpolation (issue-discovery-triage.yaml)
Baseline count capture used `echo` which adds a trailing newline, potentially breaking `float()` parsing when used as `target` in `output_numeric`. Changed to `printf '%s'` for clean output.

### 6. Missing decision-state documentation (dependency-audit.yaml)
`analyze_cycles` state had no action and no `action_type`, which works correctly but was undocumented. Added a comment explaining the decision-state pattern.

### 7. Silent secret detection failure (pr-review-cycle.yaml)
`check_no_secrets` had `on_failure: done`, silently terminating without explaining why the PR wasn't opened. Added a `secrets_found` state that reports findings and recommends remediation.

### 8. Missing .env in verify_clean (secret-scan.yaml)
The `verify_clean` grep didn't include `.env` files, but the initial `scan` state counted them. After remediation, `.env` files wouldn't be caught. Added `--include='*.env'` and separate `.env` file counting to match the scan state.

## Simplifications Applied

### S1. Set max_iterations to 1 (issue-throughput-monitor.yaml)
Pure linear pipeline with no loops or branching. `max_iterations: 3` was misleading since it always completes in 1 pass.

### S2. Inverted LLM verdict semantics (6 loops)
Changed prompts so "success" = healthy/no action needed and "failure" = issues found, then swapped routing targets. Affected: `issue-size-split`, `plugin-health-check`, `priority-rebalance`, `readme-freshness`, `sprint-build-and-validate`, `secret-scan`.

### S3. Added verification loop (priority-rebalance.yaml)
After commit, added `verify` and `check_healthy` states that re-check the distribution and loop back to `analyze_balance` if still unhealthy.

### S4. Merged count states (plugin-health-check.yaml)
Combined `count_commands` and `count_skills` into a single `count_assets` state, reducing state count from 11 to 9.

## Test Fix

Updated `test_builtin_loops.py::test_expected_loops_exist` — the expected loop set was hardcoded to 3 loops instead of the actual 19.

## Files Modified

- `loops/issue-refinement.yaml`
- `loops/sync-and-close.yaml`
- `loops/docs-sync.yaml`
- `loops/dead-code-cleanup.yaml`
- `loops/worktree-health.yaml`
- `loops/issue-discovery-triage.yaml`
- `loops/dependency-audit.yaml`
- `loops/pr-review-cycle.yaml`
- `loops/secret-scan.yaml`
- `loops/issue-throughput-monitor.yaml`
- `loops/issue-size-split.yaml`
- `loops/plugin-health-check.yaml`
- `loops/priority-rebalance.yaml`
- `loops/readme-freshness.yaml`
- `loops/sprint-build-and-validate.yaml`
- `scripts/tests/test_builtin_loops.py`

## Verification

- All 15 modified loops pass `ll-loop validate`
- All 3316 tests pass (0 failures)
- mypy passes clean
