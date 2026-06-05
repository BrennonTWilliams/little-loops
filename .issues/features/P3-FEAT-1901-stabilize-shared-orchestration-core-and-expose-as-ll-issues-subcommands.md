---
id: FEAT-1901
title: Stabilize shared orchestration core and expose as ll-issues subcommands
type: FEAT
priority: P3
status: open
captured_at: 2026-06-03T19:12:39Z
discovered_date: 2026-06-03
discovered_by: scope-epic
parent: EPIC-1867
relates_to: []
---

# FEAT-1901: Stabilize shared orchestration core and expose as ll-issues subcommands

## Summary

Wrap the shared orchestration modules — `DependencyGraph.get_ready_issues()`,
`verify_work_was_done()`/`verify_issue_completed()`, and `classify_failure`/`create_issue_from_failure` —
into a documented, test-gated internal library. Expose each as a new `ll-issues` subcommand:

- `ll-issues next --json --respect-deps [--priority …] [--skip …]` wrapping `DependencyGraph.get_ready_issues()` + filters
- `ll-issues verify-work <id> --baseline <sha>` wrapping `verify_work_was_done()` + `verify_issue_completed()`; exit 0 = real work, 1 = none
- `ll-issues classify-failure --rc <n> < err.txt` wrapping `classify_failure`/`create_issue_from_failure`

This is the **behavior-neutral Layer 0 prerequisite** for EPIC-1867. No existing behavioral changes — only wrapping and exposing. Existing tests gate it. The `verify-work` subcommand is the non-LLM evaluator the Layer-1 FSM needs to satisfy CLAUDE.md MR-1.

## Current Behavior

The shared orchestration functions — `DependencyGraph.get_ready_issues()`, `verify_work_was_done()`, `verify_issue_completed()`, and `classify_failure`/`create_issue_from_failure` — exist as internal Python modules. They are only accessible by importing them directly in Python code (e.g., from `ll-auto`, `ll-parallel`, `ll-sprint`). There is no CLI surface for these functions, so FSM loops and shell scripts cannot call them without spawning a Python subprocess with ad-hoc inline code.

## Expected Behavior

After this feature, the three subcommands are available on the `ll-issues` CLI:

- `ll-issues next --json --respect-deps [--priority P0-P5] [--skip ID …]` — returns a JSON array of ready issues respecting dependency order
- `ll-issues verify-work <id> --baseline <sha>` — exits 0 if real work was done since the baseline SHA, exits 1 if none detected
- `ll-issues classify-failure --rc <n> < err.txt` — classifies a failure and optionally creates a new issue from it

FSM loops and automation scripts can use these as non-LLM evaluators and dispatch signals without importing Python.

## Use Case

**Who**: An FSM loop implementing the Layer-1 orchestrator (EPIC-1867)

**Context**: After invoking an agent to implement an issue, the FSM needs to verify that real work was done before advancing state — satisfying CLAUDE.md MR-1 (non-LLM evaluator required).

**Goal**: Call `ll-issues verify-work FEAT-1234 --baseline abc1234` as an `exit_code` evaluator in the loop YAML, getting exit 0 (work done) or 1 (no work done) without any Python import.

**Outcome**: The FSM can route `exit 0 → advance` and `exit 1 → retry/escalate` using standard `exit_code` evaluation, satisfying MR-1 with zero LLM calls.

## Acceptance Criteria

- [ ] `ll-issues next --json --respect-deps` outputs a valid JSON array of ready issues ordered by priority and dependency
- [ ] `ll-issues next --skip <id>` excludes the specified issue from results
- [ ] `ll-issues verify-work <id> --baseline <sha>` exits 0 when commits/file changes exist since baseline, exits 1 when none
- [ ] `ll-issues classify-failure --rc <n>` reads stderr from stdin and classifies the failure type
- [ ] All three subcommands are documented in `docs/reference/API.md` under the `ll-issues` section
- [ ] Existing tests for the wrapped functions continue to pass unchanged
- [ ] At least one integration test per subcommand covering the happy path

## Proposed Solution

Wrap each function in a thin `ll-issues` subcommand handler in `scripts/little_loops/commands/issues.py` (or the equivalent dispatcher):

1. **`next` subcommand**: Call `DependencyGraph(issues).get_ready_issues()`, apply `--priority` filter and `--skip` exclusions, serialize to JSON, and print. No new logic — pure delegation.
2. **`verify-work` subcommand**: Call `verify_work_was_done(issue_id, baseline_sha)` and map its boolean result to `sys.exit(0)` / `sys.exit(1)`. If `verify_issue_completed()` is a better fit for the check, delegate to it instead.
3. **`classify-failure` subcommand**: Read stdin, call `classify_failure(stderr_text, rc)`, optionally call `create_issue_from_failure(result)` if `--create-issue` flag is set.

No behavioral changes to the underlying functions. Existing callers in `ll-auto`/`ll-parallel`/`ll-sprint` continue to import and call the Python functions directly.

## API/Interface

```
ll-issues next [--json] [--respect-deps] [--priority P0|P1|P2|P3|P4|P5] [--skip ID …]
    Outputs: JSON array of issue IDs/paths (--json) or plain text list
    Exit: 0 always

ll-issues verify-work <issue-id> --baseline <git-sha>
    Outputs: nothing (exit code is the signal)
    Exit: 0 = real work detected since baseline, 1 = no work detected

ll-issues classify-failure --rc <int> [--create-issue]
    Reads: stderr text from stdin
    Outputs: JSON classification result to stdout
    Exit: 0 always (classification errors reported in JSON)
```

## Implementation Steps

1. Locate the `ll-issues` subcommand dispatcher (`scripts/little_loops/commands/issues.py` or equivalent) and add argument parser entries for `next`, `verify-work`, and `classify-failure`
2. Implement `next` handler: delegate to `DependencyGraph.get_ready_issues()` with filter/skip options and JSON serialization
3. Implement `verify-work` handler: delegate to `verify_work_was_done()`/`verify_issue_completed()` and map bool → exit code
4. Implement `classify-failure` handler: read stdin, delegate to `classify_failure`/`create_issue_from_failure`
5. Add integration tests for each subcommand (happy path + edge cases)
6. Update `docs/reference/API.md` with the three new subcommands
7. Run existing test suite to confirm no regressions

## Impact

- **Priority**: P3 — prerequisite for Layer 1 but low risk; behavior-neutral
- **Effort**: Small — wrapping existing code, no new logic
- **Risk**: Low — no behavioral changes; existing tests gate it
- **Breaking Change**: No

## Labels

`orchestration`, `automation`, `cli`, `layer-0`

## Status

**Open** | Created: 2026-06-03 | Priority: P3


## Verification Notes

**Verdict**: VALID — 2026-06-05T21:00:23

- Issue describes a planned feature/enhancement that has not yet been implemented
- Referenced files and directories verified to exist (where applicable)
- No claims about current code behavior are contradicted by the codebase
- Dependency references are valid (no broken refs, missing backlinks, or cycles)

- `/ll:verify-issues` - 2026-06-05 - Partially implemented: `next-issue` and `next-issues` subcommands exist in `cli/issues/`. `verify-work` and `classify-failure` subcommands not yet implemented. Body references `commands/issues.py` which doesn't exist — actual dispatcher is `cli/issues/__init__.py`. Update the Implementation Plan to reflect partial completion and correct the file path.

## Session Log
- `/ll:verify-issues` - 2026-06-05T22:34:33 - `1a4d9590-60c8-47b0-9997-b0f543664183.jsonl`
- `/ll:verify-issues` - 2026-06-05T21:00:23 - `current-session.jsonl`
- `/ll:format-issue` - 2026-06-03T19:22:31 - `cf77dd21-97ce-450b-b385-13e81d1a8ae0.jsonl`
- `/ll:scope-epic` - 2026-06-03T19:12:39Z - `87e9f36b-36c2-4e9e-a0c8-3a57aa45d1f5.jsonl`
