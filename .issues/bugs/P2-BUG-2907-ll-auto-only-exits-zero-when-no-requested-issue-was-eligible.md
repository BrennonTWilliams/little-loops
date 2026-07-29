---
id: BUG-2907
type: BUG
priority: P2
status: done
captured_at: '2026-07-29T02:59:11Z'
completed_at: '2026-07-29T04:26:24Z'
discovered_date: 2026-07-29
discovered_by: capture-issue
labels:
- ll-auto
- exit-codes
- loops
- autodev
relates_to:
- BUG-2908
confidence_score: 96
outcome_confidence: 88
score_complexity: 20
score_test_coverage: 22
score_ambiguity: 18
score_change_surface: 25
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

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Naming correction**: the class referenced throughout this issue as
  `IssueManager` is actually `AutoManager`
  (`scripts/little_loops/issue_manager.py:1155`) — there is no separate
  `IssueManager` class in this file. All line references below are against
  `AutoManager`.
- **Exact anchors**: `AutoManager.run()` (`issue_manager.py:1342`),
  `_get_next_issue()` (`issue_manager.py:1258`), `_log_blocked_issues()`
  (`issue_manager.py:1325`). `attempted_count` is declared at line 1369,
  incremented at line 1381 immediately before `_process_issue(info)` (line
  1382) — i.e. it counts "issue objects `_get_next_issue()` actually
  returned," not "requested `--only` IDs." `self.processed_count` increments
  only on a successful `_process_issue` (line 1384). The failure gate itself
  is `if self.only_ids and attempted_count > 0 and self.processed_count == 0:
  return 1` / `return 0` at lines 1397-1399. There is no `completed_ids`
  variable in this class (only `self.state_manager.state.completed_issues`,
  read at lines 1269/1364) — the proposed solution snippet's `completed_ids`
  reference will need to resolve to that field or be built locally.
- **A fourth ineligibility case with zero signal today**: not-found `--only`
  IDs. `_get_next_issue()`'s `remaining` set (line 1303:
  `all_in_graph = set(self.dep_graph.issues.keys())`) is built strictly from
  `DependencyGraph` membership (`dependency_graph.py:56`,
  `DependencyGraph.from_issues`). An ID that never appears in `.issues/` at
  all is absent from `all_in_graph`, so it's silently absent from both
  `candidates` and `remaining` — `_log_blocked_issues()` (line 1325, guarded
  by `if remaining:` at line 1320) never even runs for it, producing **no log
  line whatsoever**, not just a missing reason code. The same silent-drop
  applies to an already-`done`/`cancelled`/skipped `--only` ID: it's
  subtracted out of `remaining` at lines 1269-1272/1281/1304 identically to a
  genuinely blocked issue, so today's logging can't distinguish "already
  finished" from "blocked" from "never existed." `_unreachable_reason()` must
  check graph membership *before* delegating to `get_blocking_issues()`, or
  the not-found/already-terminal cases will keep silently falling through.
- **Cycle detection is decoupled from per-ID classification**: cycles are
  detected once at `AutoManager.__init__` via `self.dep_graph.has_cycles()` /
  `detect_cycles()` (`issue_manager.py:1242-1245`, DFS coloring at
  `dependency_graph.py:380-432`) and only logged as a startup warning — it's
  never correlated back to a specific `--only` ID's ineligibility at dequeue
  time. `_unreachable_reason()` needs its own call to `detect_cycles()` (or a
  cached result from `__init__`) to report "in a dependency cycle" instead of
  a generic "blocked" for a cyclic ID.

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

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Reason-classifier precedent**: `scripts/little_loops/issue_lifecycle.py`
  already has two shapes to model `_unreachable_reason()` on — a plain `Enum`
  (`DeferReason`, lines 58-81, e.g. `BLOCKED_BY_UNMET = "blocked_by_unmet"`)
  for when the reason needs to be persisted to state/frontmatter, and a
  `classify_failure(...) -> tuple[FailureType, str]` function
  (line 107, paired with `FailureType` enum at lines 89-104) for a
  classify-and-explain shape. A lighter-weight, already-established
  alternative for a purely log-facing reason is the `already_<status>`
  string-stem convention in `scripts/little_loops/loops/autodev.yaml:194-205`
  (`already_done`, `already_cancelled`, `already_deferred`), used where the
  consumer is a shell/grep pipeline rather than Python — any of the three is
  consistent with codebase conventions.
- **Blocker-list format precedent**: keep the existing
  `"{issue_id} blocked by: {comma-joined sorted blocker ids}"` shape from
  `_log_blocked_issues()` (`issue_manager.py:1337`) for the `blocked_by`
  reason case, rather than `ll-deps`'s terser inline variants
  (`cli/deps.py:485,501,604`, e.g. `"blocked by X"` without the list) — no
  single formatter is shared between the two call sites today, so matching
  `issue_manager.py`'s own existing convention avoids introducing a third
  style.
- `_log_blocked_issues()` itself doesn't return data, only logs — a
  `_unreachable_reason()` helper will need its own call to
  `self.dep_graph.get_blocking_issues(issue_id, completed)`
  (`dependency_graph.py:283-295`, returns `blocked_by.get(issue_id, set()) -
  completed`) rather than trying to extract it from the logging method.

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

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/loops/rn-remediate.yaml` — `implement` state
  (lines 499-527) runs `ll-auto --only "$ID" $SKIP_FLAG` under the same
  `set -o pipefail`/`exit $?` idiom as `autodev.yaml`'s `implement_current`,
  routing `on_yes: run_code_gate` / `on_no: check_learning_gate` /
  `on_error: check_learning_gate`. Same blast radius as `autodev.yaml`: a
  never-eligible `--only` target currently takes `on_yes` as if implemented.
  Not previously listed in this Integration Map alongside `autodev.yaml` and
  `auto-refine-and-implement.yaml`, which have the identical dispatch shape.

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_REFERENCE.md` (lines ~659, ~812, ~1009-1010) — prose
  describing `autodev`/`auto-refine-and-implement`'s `ll-auto --only` →
  `on_yes`/`on_no` routing implicitly documents the current (buggy) exit
  contract; review once the exit code becomes honest.
- `.ll/decisions.yaml` (`ARCH-131`, `EPIC-2386`) — standing rule that
  sub-process exit codes must not be used as a completion proxy; this fix
  makes the exit code itself honest but does not by itself satisfy
  ARCH-131's ground-truth-state-diff requirement (BUG-2908's scope).

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_dependency_graph.py` — closest existing fixture pattern
  for constructing a minimal `blocked_by`/cycle graph
  (`TestCycleDetection`, `test_blocked_with_deps`,
  `test_not_blocked_after_completion`); use this shape for a unit-level test
  of the new `_unreachable_reason()` helper directly, rather than only
  exercising it through the full `full_project`-fixture integration test in
  `test_issue_manager.py`.

## Implementation Steps

1. Add a failing test: `ll-auto --only <ID>` against an issue with an unmet
   `blocked_by` asserts exit 1 and that the blocker IDs appear in output.
2. Remove the `attempted_count > 0` conjunct; add per-ID unreachable reporting
   with a reason classification.
3. Confirm the no-`--only` empty-backlog path still exits 0 (existing tests).
4. Update the `run()` docstring `Returns:` contract.
5. Verify `autodev`'s `implement_current` now routes `on_no` on a blocked target
   and that `check_impl_auth` correctly declines to treat it as an auth failure.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

6. Verify `rn-remediate.yaml`'s `implement` state (same `ll-auto --only` /
   `shell_exit` dispatch shape as `autodev.yaml`) now routes `on_no` on a
   blocked target instead of falsely taking `on_yes: run_code_gate`.
7. Add a unit test for `_unreachable_reason()` using the minimal graph-fixture
   pattern in `test_dependency_graph.py` (`TestCycleDetection`,
   `test_blocked_with_deps`), not just an integration-level assertion.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **No existing test covers the `attempted_count == 0` path.**
  `scripts/tests/test_issue_manager.py` has
  `test_run_returns_one_when_only_ids_all_gate_blocked` (line 3235), whose
  name suggests it's this exact regression case, but it isn't: it mocks
  `process_issue_inplace` to return `success=False` — i.e. `_get_next_issue()`
  *does* return the issue, `_process_issue` is attempted and fails, and
  `attempted_count > 0` is already true. That's the already-working half of
  today's gate. The new test (e.g.
  `test_run_returns_one_when_only_ids_never_eligible`) needs a scenario where
  `_get_next_issue()` never returns the requested ID at all — an unmet
  `blocked_by`, an ID absent from `.issues/`, or an already-`done` ID — with
  no `process_issue_inplace` call expected, asserting `result == 1` once
  fixed. Follow the same fixture shape as
  `test_run_with_only_ids_filter`/`test_run_returns_one_when_only_ids_all_gate_blocked`
  (`full_project` fixture, `AutoManager(config, dry_run=False,
  only_ids={...}, db_path=...)`).
- **`autodev.yaml`'s exact routing**: `implement_current`
  (`scripts/little_loops/loops/autodev.yaml:665-706`, `fragment: shell_exit`)
  runs `ll-auto --only "$CURRENT" $SKIP_FLAG` through `tee` under `set -o
  pipefail` (lines 701-702), so the real exit code does survive the pipe.
  `on_yes: dequeue_next` (line 704) fires on exit 0; `on_no:
  check_learning_gate` / `on_error: check_learning_gate` (lines 705-706) fire
  on nonzero — confirming the fix's blast radius exactly as described: today
  a never-eligible `--only` target takes `on_yes` and is silently treated as
  implemented.

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

## Resolution

Dropped the `attempted_count > 0` conjunct from `AutoManager.run()`'s `only_ids`
exit gate — `--only` now returns 1 whenever `processed_count == 0`, regardless
of whether the requested ID was ever dequeued. Added
`AutoManager._unreachable_reason()` to classify why each unreached `--only` ID
never came back: `not_found` (absent from `.issues/` entirely, resolved via an
unfiltered `find_issues()` pass since `find_issues_for_graph()` excludes
terminal issues from the graph), `already_<status>` (done/cancelled/deferred,
or in the run's completed set), `in a dependency cycle`, or `blocked by:
<comma-joined blocker ids>` (falling back to `filtered out` if none of those
apply). Each unreached ID's reason is logged as an error line before the exit.

The no-`--only` empty/fully-blocked backlog path is unchanged (still exit 0).

Added three regression tests to `TestAutoManagerRun` in `test_issue_manager.py`:
a never-eligible `blocked_by` target (the exact BUG-2907 repro shape,
`process_issue_inplace` asserted never called), a not-found `--only` ID, and a
direct unit test of `_unreachable_reason()`'s three classification branches.

`autodev.yaml`'s `implement_current` and `rn-remediate.yaml`'s `implement`
state both already route on the real subprocess exit code via `set -o
pipefail` — no loop YAML changes were needed; they now correctly take
`on_no`/`on_error` instead of `on_yes` for a never-eligible `--only` target.

Does not address the `autodev` accounting defect (BUG-2908) — that is separate
scope.

## Session Log
- `/ll:manage-issue` - 2026-07-29T04:25:53Z - fix BUG-2907
- `/ll:ready-issue` - 2026-07-29T04:18:31 - `67ba6b01-17d9-451f-b4e4-48f9d3a8ff87.jsonl`
- `/ll:wire-issue` - 2026-07-29T04:16:14 - `4fe4da6e-871f-4528-9261-d31efa5e3e1d.jsonl`
- `/ll:refine-issue` - 2026-07-29T04:10:35 - `048abc2a-e902-4c20-9b24-dd78b07c7a6d.jsonl`
- `/ll:capture-issue` - 2026-07-29T02:59:11Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1a15bf47-b270-4d12-a74c-47b9c005a000.jsonl`

---

## Status

`open`
