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
blocks:
- FEAT-2000
- FEAT-1899
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
- [ ] `ll-issues complete <id>` sets status `done`, writes the Resolution section, commits the issue file, and emits the history.db issue event (scope added 2026-06-12 — required by the reference FSM YAML's `complete_issue` state)
- [ ] `ll-issues mark-failed <id> --reason <text>` records the failure reason and sets an appropriate status (scope added 2026-06-12 — required by the reference FSM YAML's failure-handling states)
- [ ] All three subcommands are documented in `docs/reference/API.md` under the `ll-issues` section
- [ ] Existing tests for the wrapped functions continue to pass unchanged
- [ ] At least one integration test per subcommand covering the happy path

## Proposed Solution

Wrap each function in a thin `ll-issues` subcommand handler in `scripts/little_loops/cli/issues/__init__.py` (or the equivalent dispatcher):

1. **`next` subcommand**: Call `DependencyGraph(issues).get_ready_issues()`, apply `--priority` filter and `--skip` exclusions, serialize to JSON, and print. No new logic — pure delegation.
2. **`verify-work` subcommand**: Call `verify_work_was_done(issue_id, baseline_sha)` and map its boolean result to `sys.exit(0)` / `sys.exit(1)`. If `verify_issue_completed()` is a better fit for the check, delegate to it instead.
3. **`classify-failure` subcommand**: Read stdin, call `classify_failure(stderr_text, rc)`, optionally call `create_issue_from_failure(result)` if `--create-issue` flag is set.
4. **`complete` subcommand** (scope added 2026-06-12 by epic audit): wrap the existing completion path — set status `done`, write Resolution, commit, emit issue event — as one atomic lifecycle transition. The reference FSM YAML in `docs/research/ll-orchestrator-decomposition-plan-v0.2.md` invokes `ll-issues complete <id>` from its `complete_issue` state; without it, FEAT-2000 would need a fragile multi-command shell workaround (`set-status` + git commit + event emit).
5. **`mark-failed` subcommand** (scope added 2026-06-12 by epic audit): record a failure reason on the issue and set status, for the FSM's failure route. Pairs with `classify-failure` (classification) by owning the state transition.

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

ll-issues complete <issue-id>
ll-issues mark-failed <issue-id> --reason <text>
    Reads: stderr text from stdin
    Outputs: JSON classification result to stdout
    Exit: 0 always (classification errors reported in JSON)
```

## Implementation Steps

1. Locate the `ll-issues` subcommand dispatcher (`scripts/little_loops/cli/issues/__init__.py`) and add argument parser entries for `next`, `verify-work`, and `classify-failure`
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
- `/ll:verify-issues` - 2026-06-13 - Stale path `commands/issues.py` still present in Implementation Steps. `verify-work`, `classify-failure`, `complete`, `mark-failed` subcommands not yet implemented. Added FEAT-1899 to `blocks:` (missing backlink). Correct file is `cli/issues/__init__.py`.
- 2026-06-13: Corrected path: `commands/issues.py` → `cli/issues/__init__.py`. Subcommands `verify-work`, `classify-failure`, `complete`, `mark-failed` are not yet implemented. Underlying functions in work_verification.py and issue_lifecycle.py confirmed present.
- `/ll:verify-issues` - 2026-06-17 - Still NEEDS_UPDATE: `commands/issues.py` stale path persists in Implementation Steps. `next-issue`/`next-issues` subcommands exist but differ from the proposed `ll-issues next --respect-deps` API. `verify-work`, `classify-failure`, `complete`, `mark-failed` subcommands remain unimplemented. Correct implementation target is `cli/issues/__init__.py`.

2026-06-19 (NEEDS_UPDATE): `verify-work`, `classify-failure`, `complete`, `mark-failed` subcommands still not implemented. `next-issue`/`next-issues` exist in `cli/issues/` but differ from the proposed `ll-issues next --respect-deps` API. Implementation Steps still reference `commands/issues.py` — correct target is `cli/issues/__init__.py`.

## Session Log
- `/ll:verify-issues` - 2026-06-20T00:34:46 - `fe5ace5b-6f94-43ca-9f1d-09a0705f08c4.jsonl`
- `/ll:verify-issues` - 2026-06-17T00:00:00 - `7473c42a-1313-4587-925f-e177ac5fcc85.jsonl`
- `/ll:verify-issues` - 2026-06-14T00:14:03 - `7db6ce0f-4d7c-486d-927d-6804d39ee7b7.jsonl`
- `/ll:verify-issues` - 2026-06-13T21:13:58 - `cfa3cf65-c671-4bf6-a513-92cc448d76e6.jsonl`
- `/ll:verify-issues` - 2026-06-09T18:30:00 - `fffefcf7-6dbd-438c-bdd1-259bea8d77b7.jsonl`
- `/ll:verify-issues` - 2026-06-09T09:21:00 - `e40557ae-4da3-4ea7-b023-bf5e57e8b61a.jsonl`
- `/ll:verify-issues` - 2026-06-05T22:34:33 - `1a4d9590-60c8-47b0-9997-b0f543664183.jsonl`
- `/ll:verify-issues` - 2026-06-05T21:00:23 - `current-session.jsonl`
- `/ll:format-issue` - 2026-06-03T19:22:31 - `cf77dd21-97ce-450b-b385-13e81d1a8ae0.jsonl`
- `/ll:scope-epic` - 2026-06-03T19:12:39Z - `87e9f36b-36c2-4e9e-a0c8-3a57aa45d1f5.jsonl`
