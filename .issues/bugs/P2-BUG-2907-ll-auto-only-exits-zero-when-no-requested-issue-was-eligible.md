---
id: BUG-2907
type: BUG
priority: P2
status: open
captured_at: "2026-07-29T02:59:11Z"
discovered_date: 2026-07-29
discovered_by: capture-issue
labels:
- ll-auto
- exit-codes
- loops
- autodev
relates_to:
- BUG-2908
---

# BUG-2907: `ll-auto --only` exits 0 when no requested issue was ever eligible

## Summary

`ll-auto --only <ID>` returns exit code 0 when the named issue is never selected
for processing (blocked by unmet dependencies, part of a dependency cycle, or
otherwise filtered out of the work queue). The caller receives a success signal
for a run that did nothing. This is the root cause of the phantom `autodev` run
audited in `audit-loop-run-autodev-2026-07-29T013824.md`.

## Steps to Reproduce

1. Create issue `A` with `blocked_by: [B]` where `B` has `status: open`.
2. Run `ll-auto --only A`.
3. Observe the log reports `A blocked by: B`, `1 issue(s) remain blocked`,
   `No more issues to process!`, and `Issues processed: 0`.
4. `echo $?` → `0`.

Expected `1`. The same reproduces through `ll-loop run autodev A`, where
`implement_current` routes `on_yes: dequeue_next` on the false success.

## Current Behavior

`IssueManager.run()` in `scripts/little_loops/issue_manager.py` gates the
`--only` failure return on `attempted_count > 0`:

```python
attempted_count = 0
...
    info = self._get_next_issue()
    if not info:
        self.logger.success("No more issues to process!")
        break
    attempted_count += 1
    ...
self.logger.success(f"Processed {self.processed_count} issue(s)")
if self.only_ids and attempted_count > 0 and self.processed_count == 0:
    return 1
return 0
```

A blocked issue never comes back from `_get_next_issue()`, so `attempted_count`
stays `0`, the `only_ids` branch is skipped, and the function falls through to
`return 0`.

Observed verbatim (`ll_auto_last.txt` from the audited run, `ll-auto --only FEAT-108`):

```
[21:12:34] Dependency cycle detected: FEAT-108 -> FEAT-123 -> FEAT-122 -> FEAT-108
[21:12:34]   FEAT-108 blocked by: FEAT-122, FEAT-123, FEAT-124
[21:12:34] 1 issue(s) remain blocked - check dependencies
[21:12:34] No more issues to process!
[21:12:34] Issues processed: 0
```

Exit code: `0`.

## Expected Behavior

When `--only` is supplied and **none** of the requested IDs were processed, the
exit code is non-zero regardless of whether any of them were attempted. A caller
that names specific issues and gets none of them back has failed, and the
distinction between "filtered out before attempt" and "attempted and failed" is
not one the caller can observe from the exit code today.

The general-backlog path (no `--only`) keeps its current semantics: an empty or
fully-blocked backlog is exit 0, not an error.

`ll-auto` should also state *why* each requested ID was unreachable — `blocked`
(with the blocker list), `not_found`, or `already_terminal` — so the caller can
route on the reason rather than parsing the human-readable log.

## Motivation

Every automation layer above `ll-auto` treats its exit code as the
implementation contract. `autodev.yaml`'s `implement_current` is `fragment:
shell_exit` with `on_yes: dequeue_next` — a false 0 sends the loop straight to
the next queue entry as though the issue had been implemented, and the run ends
`done` having closed nothing. The audited run burned ~34 minutes on this path.
The same false signal reaches `ll-sprint`, `ll-parallel`, and `ll-queue`'s
`CMD`-runner dispatch.

Fixing the exit contract here is strictly better than teaching each caller to
grep `Issues processed: 0` out of stdout, which is brittle and was explicitly
rejected during triage.

## Root Cause

`IssueManager.run()` (`scripts/little_loops/issue_manager.py`) — the
`attempted_count > 0` conjunct in the `only_ids` failure return. The guard was
added to keep an empty backlog from being an error, but it is over-broad: under
`--only` the backlog being empty *of the requested IDs* is exactly the error
condition.

## Proposed Solution

Drop `attempted_count > 0` from the `only_ids` branch and report the unreachable
IDs:

```python
self.logger.success(f"Processed {self.processed_count} issue(s)")
if self.only_ids:
    unreached = set(self.only_ids) - completed_ids
    if unreached:
        for issue_id in sorted(unreached):
            self.logger.error(f"  {issue_id}: {self._unreachable_reason(issue_id)}")
        if self.processed_count == 0:
            return 1
return 0
```

`_unreachable_reason()` classifies as `blocked_by: <ids>` (reuse
`self.dep_graph.get_blocking_issues()`, already called by `_log_blocked_issues`),
`not_found`, or `already_<status>`.

Open decision for the implementer: whether a *partial* `--only` run (2 of 3 IDs
processed) should exit non-zero. Recommendation is no — keep `processed_count ==
0` as the failure condition and let the per-ID error lines carry the partial
signal — but this should be settled explicitly and documented in the `run()`
docstring, whose current `Returns:` line ("0 = success or empty queue, 1 = all
issues gate-blocked when --only used") is already narrower than the behavior.

## Integration Map

- `scripts/little_loops/issue_manager.py` — `IssueManager.run()`,
  `IssueManager._log_blocked_issues()`, `IssueManager._get_next_issue()`
- `scripts/little_loops/loops/autodev.yaml` — `implement_current`
  (`fragment: shell_exit`), whose `on_no` route becomes reachable once the exit
  code is honest; downstream `check_learning_gate` → `check_impl_auth` →
  `dequeue_next`
- `scripts/little_loops/loops/auto-refine-and-implement.yaml` — same `ll-auto
  --only` dispatch shape
- `scripts/little_loops/loops/lib/` — `shell_exit`, `ll_auto_learning_gate_check`,
  `ll_auto_auth_check` fragments
- `scripts/tests/` — new regression test asserting exit 1 for a blocked `--only`
  target

## Implementation Steps

1. Add a failing test: `ll-auto --only <ID>` against an issue with an unmet
   `blocked_by` asserts exit 1 and that the blocker IDs appear in output.
2. Remove the `attempted_count > 0` conjunct; add per-ID unreachable reporting
   with a reason classification.
3. Confirm the no-`--only` empty-backlog path still exits 0 (existing tests).
4. Update the `run()` docstring `Returns:` contract.
5. Verify `autodev`'s `implement_current` now routes `on_no` on a blocked target
   and that `check_impl_auth` correctly declines to treat it as an auth failure.

## Impact

- **Correctness**: removes a false-success signal from the primary
  implementation entry point used by every orchestration layer.
- **Blast radius**: any caller currently relying on exit 0 for a blocked `--only`
  target will start seeing exit 1. That is the intended change, but
  `auto-refine-and-implement.yaml` and `ll-sprint`'s wave driver should be
  checked for routes that would now treat a blocked issue as an infra failure
  rather than a skip.
- **Does not by itself fix** the `autodev` accounting defect — see BUG-2908.
  Both are needed: this makes the signal honest, BUG-2908 makes the loop act on it.

## Related Key Documentation

| Document | Relevance |
|---|---|
| `.claude/CLAUDE.md` § CLI Tools | `ll-auto` contract and `--skip-learning-gate` parity |
| `docs/ARCHITECTURE.md` § Orchestration Layers | which layers consume `ll-auto`'s exit code |
| `audit-loop-run-autodev-2026-07-29T013824.md` | audit report with verbatim run evidence |

## Session Log
- `/ll:capture-issue` - 2026-07-29T02:59:11Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1a15bf47-b270-4d12-a74c-47b9c005a000.jsonl`

---

## Status

`open`
