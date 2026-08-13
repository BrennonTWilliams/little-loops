---
id: ENH-3153
type: ENH
title: Close ENH-2997 registry and teardown gaps left by the ll-auto timeout
priority: P2
status: done
completed_at: '2026-08-13T00:26:10Z'
discovered_by: ll-issues-create
discovered_date: '2026-08-13'
captured_at: '2026-08-13T00:26:30Z'
labels:
- prepatch-check
- observability
- session-store
---

# ENH-3153: Close ENH-2997 registry and teardown gaps left by the ll-auto timeout

## Summary

Close the three residual gaps left in the ENH-2997 working tree when its `ll-auto` implementation session was killed by the 3600s `automation.timeout_seconds` wall clock mid-verification. Two are omissions from enforcement registries that the new pre-patch-check surfaces were never added to; the third is an error-handling defect in the executor's worktree teardown.

## Current Behavior

An `ll-auto --only ENH-2997` run on 2026-08-12 landed ~1,164 insertions across 26 files — effectively the complete 8-task implementation plan — then was SIGTERM'd at exactly 3600s during its Phase 4 full-suite verification pass. `ll-auto` handled the kill correctly: it did not auto-complete, left `status: open`, and preserved the working tree.

The killed session had just diagnosed one of its own failures (`prepatch_evidence` needs a kind registration) and died before writing the fix. A full-suite run afterward surfaced a second, alphabetically earlier failure the timeout never reached:

- `scripts/tests/test_verify_kinds.py` — 2 failures. The migration added at `SCHEMA_VERSION = 40` in `session_store/schema.py` creates a SQL table named prepatch_evidence that is neither registered in `_KIND_TABLE` nor listed in `_KINDLESS_TABLES`, so `ll-verify-kinds` exits 1.
- `scripts/tests/test_des_audit.py::TestAuditWalker::test_real_tree_passes` — 1 failure. The executor's `self._emit("prepatch_check_flagged", ...)` under a `warn` policy has no registered DES variant, so the audit walker reports it as an uncovered event type.

Separately, `_check_prepatch_check` in `fsm/executor.py` wrapped its worktree teardown in `try/finally`:

```python
try:
    if evidence.worktree_path is not None:
        cleanup_worktree(...)
finally:
    self._prepatch_check_memo[memo_key] = evidence
```

A raise from `cleanup_worktree` propagates out of the guarded window and aborts the run, even though the check had already reached a verdict and both evidence writes below it already swallow their own errors.

## Expected Behavior

Both enforcement gates pass against the real source tree, and a teardown failure degrades to a leaked worktree rather than a failed run.

- `prepatch_evidence` is explicitly kindless. It is keyed by `issue_id`, not `session_id`, and readers take the most recent row for an issue — there is no "recent by kind" concept to register.
- `prepatch_check_flagged` is a declared DES variant. `DES_VARIANT_TYPES` is derived from the `type: Literal[...]` defaults of the dataclasses in `DES_VARIANTS`, so this requires an actual variant class, not a string appended to a list.
- Worktree teardown is best-effort and cannot abort a guarded window.

## Impact

- **Priority**: P2 - Blocks ENH-2997 from reaching a green suite; the underlying implementation is otherwise complete.
- **Effort**: Small - Two registry entries and one exception-handling change.
- **Risk**: Low - No behavior change on the success path; the teardown change only widens what is tolerated on an already-failing path.
- **Breaking Change**: No

## Program Design

### Signatures

- `_KINDLESS_TABLES: frozenset[str]` — the explicit allow-list of tables with no "recent by kind" concept, at `session_store/schema.py:75`. `prepatch_evidence` joins `meta`, `sessions`, `raw_events`, and the other support tables here. No signature change; one set member added.
- `type: Literal[prepatch_check_flagged]` — the discriminator default on the new frozen dataclass `PrePatchCheckFlaggedVariant(DESVariant)` in `observability/schema.py`. Registered in `DES_VARIANTS`, from which `_extract_type_defaults()` derives `DES_VARIANT_TYPES`, the audit walker's allow-list.
- `def _check_prepatch_check(self, state, ctx, prepatch_policy, repo_root, action_succeeded) -> str | None` — unchanged signature and unchanged success-path behavior in `fsm/executor.py`. Only the teardown block's exception posture changes.

### Call Path

`FSMExecutor._execute_state` → `_check_prepatch_check` → `run_prepatch_check` → `cleanup_worktree`. The teardown sits at the tail of that chain: `finally` becomes `except Exception: pass`, and the `self._prepatch_check_memo[memo_key]` write moves after the block so it runs on the normal path rather than as an unwinding side-effect. `_emit("prepatch_check_flagged", ...)` fires downstream of the memo write on the `warn` policy branch, which is what makes it an audited DES surface.

## Scope Boundaries

**In scope:** the three defects that block ENH-2997's working tree from reaching a green suite.

**Out of scope:**

- ENH-2997's feature work itself, which remains uncommitted and `status: open`. This issue neither commits it nor completes it.
- The pre-existing `mypy` error in `cli/loop/testing.py` — outside this diff, untouched by either issue.
- The pre-existing `ruff format` drift hunk in `tests/test_session_store_schema.py` — an unrelated `harness_events` line already drifted on `main`.
- Raising `automation.timeout_seconds`, the lever that would have let the original run finish. Config change, user's call.

## Resolution

- **Status**: Completed
- **Completed**: 2026-08-13

### Changes

- `scripts/little_loops/session_store/schema.py` — added `prepatch_evidence` to `_KINDLESS_TABLES` with a comment recording why it is kindless (issue-keyed, not session-keyed).
- `scripts/little_loops/observability/schema.py` — added `PrePatchCheckFlaggedVariant` (`type: Literal["prepatch_check_flagged"]`) and registered it in `DES_VARIANTS` alongside the other `FSMExecutor._emit` Channel B variants.
- `scripts/little_loops/fsm/executor.py` — `_check_prepatch_check` worktree teardown changed from `try/finally` to `try/except Exception: pass`, with the memo write moved out of the exception path; stale "finally-block teardown" comment corrected.

### Incidental

- `ruff format` had regressed three files under ENH-2997 (`fsm/executor.py`, `prepatch_check.py`, `tests/test_fsm_executor.py`) — reformatted. One pre-existing drift hunk in `tests/test_session_store_schema.py` was left alone: it is an unrelated `harness_events` line already drifted on `main`, and reformatting it would be scope creep.

### Verification

- `ll-verify-kinds` exits 0.
- `python -m pytest scripts/tests/test_verify_kinds.py scripts/tests/test_des_audit.py` — 14 passed.
- `python -m pytest scripts/tests/` — **19053 passed, 43 skipped, 0 failed** in 14m32s. Run without `-x`, so this is the whole suite, not a prefix. The prior run had halted at the first failure with 18,681 passing and the tail unverified.
- `ruff check` — clean across all changed files.
- `python -m mypy scripts/little_loops/` — one pre-existing error in `cli/loop/testing.py` (`SimulationActionRunner` vs the `ActionRunner` protocol, over `timeout_kill_grace_seconds`). Outside this diff; neither file is touched by ENH-2997 or ENH-3153.

### Notes

ENH-2997 itself remains `status: open` with its implementation uncommitted in the working tree. This issue covers only the remediation of the gaps its killed session left behind, not the feature work.

The root cause of the timeout was a scope-vs-budget mismatch, not a code defect: a 21-acceptance-criteria issue spanning six subsystems against the stock 1-hour `automation.timeout_seconds` (`issue_manager.py:263`), where the full suite alone costs ~14 minutes per verification pass and Phase 4 needs at least two passes. Raising `automation.timeout_seconds` in `.ll/ll-config.json` is the lever for issues of this size.

Both registry gaps are the same class of mistake — a new persisted surface added without registering it in the gate that enforces coverage — and both gates exist precisely to catch it. They did.

## Status

**Completed** | Created: 2026-08-13 | Priority: P2


## Session Log
- `hook:posttooluse-status-done` - 2026-08-13T00:27:15 - `dd0f8de6-574b-4c6d-8dc0-81adbca41dc3.jsonl`
