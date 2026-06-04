---
id: FEAT-1902
title: Author loops/ll-auto.yaml FSM + ll-auto shim + A/B parity harness
type: FEAT
priority: P2
status: open
captured_at: 2026-06-03T19:12:39Z
discovered_date: 2026-06-03
discovered_by: scope-epic
parent: EPIC-1867
relates_to: [FEAT-1901, FEAT-1899]
---

# FEAT-1902: Author loops/ll-auto.yaml FSM + ll-auto shim + A/B parity harness

## Summary

Write `loops/ll-auto.yaml` as the FSM that replaces `AutoManager.run()` control
flow. The FSM calls Layer-0 CLIs (`ll-issues next`, `ll-issues verify-work`,
`ll-issues classify-failure`) as shell actions. Key requirements:

- Mandatory `verify_work` state backed by an `exit_code` evaluator calling
  `ll-issues verify-work <id> --baseline <sha>` — never trust the implement step's
  exit code alone. This satisfies CLAUDE.md MR-1.
- `max_iterations` derived from backlog size (not hard-coded 50, which halts after
  ~10 issues).
- Convert `ll-auto` CLI to a thin shim over `ll-loop run ll-auto`.
- Pass `ll-loop validate ll-auto` (MR-1/MR-3 clean).
- Pass `ll-loop diagnose-evaluators ll-auto` with `verify_work` verdict variance
  `p(1-p) ≥ 0.05` over ≥10 runs.
- Pass `ll-loop run ll-auto --baseline` showing the harness ≥ unguided baseline.
- **A/B parity harness**: run the same fixed backlog through legacy `ll-auto`
  (`AutoManager.run()`) and the new FSM loop; assert identical `completed/failed`
  sets and matching `history.db` event payloads. This gates merging to main.

Soft-deprecate `AutoManager.run()` for one release (do not delete yet).

Depends on FEAT-1901 (Layer 0 CLI subcommands).

## Use Case

**Who**: Developer or CI automation running `ll-auto` to process a prioritized issue backlog

**Context**: Running automated sequential issue processing against a real codebase, expecting verified outcomes — not just "Claude said done"

**Goal**: Replace brittle `AutoManager.run()` control flow with a testable FSM that provides mandatory post-implementation verification and behavioral parity guarantees vs. the legacy path

**Outcome**: `ll-auto` reliably processes all backlog issues through a validated FSM with a non-LLM `verify_work` gate, `max_iterations` derived from actual backlog size, and A/B-confirmed parity with the legacy runner

## Current Behavior

`ll-auto` invokes `AutoManager.run()` directly — hard-coded Python control flow with no FSM abstraction. The loop halts after ~10 issues due to a `max_iterations=50` that does not account for per-issue overhead, and there is no mandatory post-implementation verification step independent of the implement state's own exit code.

## Expected Behavior

`ll-auto` becomes a thin CLI shim over `ll-loop run ll-auto`. Control flow is defined in `loops/ll-auto.yaml` as an FSM with a mandatory `verify_work` state backed by a non-LLM `exit_code` evaluator. `max_iterations` is derived from backlog size. Legacy `AutoManager.run()` is soft-deprecated (warning added, not deleted). An A/B parity harness confirms behavioral equivalence before merge.

## Motivation

This feature would:
- **Fix run truncation**: Hard-coded `max_iterations=50` halts `ll-auto` mid-backlog; dynamic sizing unblocks long-running automated sessions
- **Enforce verification**: The current path trusts the implement step's own exit code — the FSM's `verify_work` state adds an independent non-LLM gate (satisfies CLAUDE.md MR-1)
- **Unlock FSM testability**: Moving control flow into `loops/ll-auto.yaml` enables `ll-loop validate`, `diagnose-evaluators`, and `--baseline` quality checks impossible against `AutoManager.run()`
- **Gate-safe migration**: A/B parity harness ensures the new FSM is behaviorally equivalent before the legacy path is deprecated

## Acceptance Criteria

- [ ] `loops/ll-auto.yaml` exists and passes `ll-loop validate ll-auto` (MR-1 and MR-3 clean)
- [ ] `verify_work` state uses an `exit_code` evaluator calling `ll-issues verify-work <id> --baseline <sha>` — does not rely on the implement step's exit code alone
- [ ] `max_iterations` is derived from backlog size, not hard-coded
- [ ] `ll-auto` CLI is a thin shim over `ll-loop run ll-auto` (CLI interface preserved)
- [ ] `ll-loop diagnose-evaluators ll-auto` reports `verify_work` verdict variance `p(1-p) ≥ 0.05` over ≥10 runs
- [ ] `ll-loop run ll-auto --baseline` confirms harness performance ≥ unguided baseline
- [ ] A/B parity harness asserts identical `completed/failed` sets and matching `history.db` event payloads between legacy `AutoManager.run()` and the new FSM loop
- [ ] `AutoManager.run()` is soft-deprecated (deprecation warning added; class not deleted)

## Integration Map

### Files to Modify
- `loops/ll-auto.yaml` — new FSM loop definition (create)
- `scripts/little_loops/issue_manager.py` — add deprecation notice to `AutoManager.run()` (class at L988, `run()` at L1165; `auto_manager.py` does not exist)
- `scripts/little_loops/cli/` (ll-auto entrypoint) — convert to thin shim over `ll-loop run ll-auto`

### Dependent Files (Callers/Importers)
- TBD — use `grep -r "AutoManager" scripts/` to find all direct callers that need auditing

### Similar Patterns
- Other FSM loop YAMLs under `loops/` — reference for state/transition/evaluator conventions
- `ll-parallel` CLI shim (if exists) — follow same shim pattern for consistency

### Tests
- New: A/B parity harness — run same fixed backlog through legacy and FSM, assert identical `completed/failed` sets and `history.db` payloads
- `scripts/tests/` — add unit tests for shim behavior and dynamic `max_iterations` derivation

### Documentation
- `docs/` — update any references to `AutoManager.run()` to note soft-deprecation

### Configuration
- N/A — no new config keys; `max_iterations` derived programmatically from backlog size

## Implementation Steps

1. Confirm FEAT-1901 Layer-0 CLI subcommands are available (`ll-issues next`, `ll-issues verify-work`, `ll-issues classify-failure`)
2. Author `loops/ll-auto.yaml` FSM: states for select, implement, verify_work, classify_failure, and done; `verify_work` uses `exit_code` evaluator; `max_iterations` reads backlog count
3. Convert `ll-auto` CLI to thin shim over `ll-loop run ll-auto` (preserve existing CLI interface)
4. Run `ll-loop validate ll-auto` — fix MR-1/MR-3 violations until clean
5. Run `ll-loop diagnose-evaluators ll-auto` over ≥10 runs — confirm `verify_work` variance `p(1-p) ≥ 0.05`
6. Run `ll-loop run ll-auto --baseline` — confirm harness ≥ unguided baseline
7. Build and run A/B parity harness against a fixed backlog — assert `completed/failed` sets and `history.db` payloads match legacy `AutoManager.run()`
8. Add deprecation notice to `AutoManager.run()` (do not delete)

## Impact

- **Priority**: P2 — critical path; the core deliverable of Layer 1
- **Effort**: Large — new FSM YAML, CLI shim refactor, parity test harness
- **Risk**: High — risk concentrated in the verify/parity gates
- **Breaking Change**: No (shim preserves CLI interface)

## Labels

`automation`, `fsm`, `ll-auto`, `layer-1`, `orchestration`

## Status

**Open** | Created: 2026-06-03 | Priority: P2

## Verification Notes

_Added by `/ll:verify-issues` on 2026-06-03_

**Verdict: NEEDS_UPDATE** — Integration Map referenced `scripts/little_loops/auto_manager.py` which does not exist. `AutoManager` lives in `scripts/little_loops/issue_manager.py` (class at L988, `run()` at L1165). This has been corrected in the Integration Map. Also: FEAT-1901 prerequisite (Layer-0 CLI subcommands) is still open and unimplemented.

## Session Log
- `/ll:verify-issues` - 2026-06-04T04:21:13 - `94e89e68-ddb3-448e-a123-eae4ee9ba582.jsonl`
- `/ll:verify-issues` - 2026-06-03T22:42:45 - `25083174-f806-4589-a206-0f8b53978497.jsonl`
- `/ll:audit-issue-conflicts` - 2026-06-03T22:04:03 - `882d6aa0-cbf0-47c3-9d9c-32d8d6c6ef92.jsonl`
- `/ll:format-issue` - 2026-06-03T19:22:56 - `1489a8f1-014d-4d2b-9f62-365c703f374a.jsonl`
- `/ll:scope-epic` - 2026-06-03T19:12:39Z - `87e9f36b-36c2-4e9e-a0c8-3a57aa45d1f5.jsonl`
