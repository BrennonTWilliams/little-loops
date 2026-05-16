---
discovered_commit: a8f4144ebd05e95833281bd95506da984ba5d118
discovered_branch: main
discovered_date: 2026-02-06T03:41:30Z
discovered_by: scan_codebase
resolution: wont-fix
closed_date: 2026-02-05
closing_note: "test and simulate subcommands don't invoke LLM calls — cmd_test() and cmd_simulate() never call an LLM. A --no-llm flag would be a no-op that misleads users."
---

# ENH-254: Add --no-llm override to ll-loop test and simulate

## Summary

The `ll-loop run` subcommand supports `--no-llm` and `--llm-model` flags, but neither `test` nor `simulate` offer these flags. The `test` subcommand executes real actions and evaluations, meaning it will make LLM API calls for loops with `llm_structured` evaluation. Users testing loop configuration may not want to incur API costs.

## Location

- **File**: `scripts/little_loops/cli.py`
- **Line(s)**: 608-629 (at scan commit: a8f4144)
- **Anchor**: `test_parser and simulate_parser argument definitions`
- **Permalink**: [View on GitHub](https://github.com/BrennonTWilliams/little-loops/blob/a8f4144ebd05e95833281bd95506da984ba5d118/scripts/little_loops/cli.py#L608-L629)

## Current Behavior

`ll-loop test` and `ll-loop simulate` have no way to disable LLM evaluation.

## Expected Behavior

Both should accept `--no-llm` to skip LLM API calls during testing/simulation.

## Proposed Solution

Add `--no-llm` argument to both `test_parser` and `simulate_parser`, and pass the flag through to the executor.

## Impact

- **Severity**: Low
- **Effort**: Small
- **Risk**: Low

## Labels

`enhancement`, `priority-p4`

---

## Status
**Closed (won't-fix)** | Created: 2026-02-06T03:41:30Z | Closed: 2026-02-05 | Priority: P4
