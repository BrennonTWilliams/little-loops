---
id: BUG-3317
type: BUG
title: "Orphaned 'running' state with no resolvable PID never reconciles \u2014 dead\
  \ runs show as live indefinitely in ll-loop list --running and dashboards"
priority: P3
status: done
discovered_by: ci-agent-report
discovered_date: '2026-08-24'
captured_at: '2026-08-24T00:00:00Z'
completed_at: '2026-08-25T02:49:39Z'
labels:
- fsm
- persistence
- observability
testable: true
confidence_score: 100
outcome_confidence: 97
score_complexity: 25
score_test_coverage: 22
score_ambiguity: 25
score_change_surface: 25
---

# BUG-3317: Orphaned 'running' state with no resolvable PID never reconciles

## Summary

A `.loops/.running/*.state.json` entry with `status: "running"` whose PID cannot be
resolved from any source (`.pid` file gone, `.lock` file gone, `state.pid` null) is
left as `running` forever. Both reconciliation paths —
`_reconcile_stale_running()` (`scripts/little_loops/fsm/persistence.py`, read path,
called from `list_running_loops` and the `ll-loop status` command path) and
`_reconcile_stale_runs()`
(startup path) — deliberately bail when liveness cannot be proven, so the entry
never self-heals. The run then appears as an active loop in `ll-loop list --running`
indefinitely, and as a `running` state in every consumer that filters that list on
status.

> Scope of the visible fix: `cmd_list` is the only in-repo consumer that filters on
> `ACTIVE_RUN_STATUSES` (`cli/loop/info.py:122`). `list_running_loops()` itself is
> unfiltered *by documented contract*, and `transport.py`'s dashboard-seed callback
> forwards everything it returns. After this fix these entries still reach every
> seeded dashboard client — they just carry `status: "interrupted"` instead of
> `"running"`. Consumers that render by status are fixed; consumers that render every
> seeded entry see no reduction in row count.

Observed live in a downstream consuming project: an
`.loops/.running/<loop>.state.json` has been `status: "running"` since **2026-04-26**
(last `updated_at` 44m52s after its `started_at`, `pid: null`, `reconciled_at: null`)
— four months of a dead process reported as running.

## Context

Filed from a CI-agent bug report that misdiagnosed the symptom as "`started_at` is
stale after resume." That diagnosis was **wrong** and its proposed fix is rejected —
see [Rejected Diagnosis](#rejected-diagnosis-do-not-implement) below. The real
defect is the liveness gap described here.

## Current Behavior

`_reconcile_stale_running()` flips `running` → `interrupted` only when
`_resolve_live_pid()` returns a PID **and** `_process_alive()` says it is dead:

```python
pid = _resolve_live_pid(running_dir, stem, state)
if pid is None:
    return state  # no PID resolvable — cannot determine liveness, leave alone
if _process_alive(pid):
    return state
```

`_reconcile_stale_runs()` has the mirrored guard on the startup path: "No `.pid`
file → leave alone (can't confirm)."

Two differences between the paths matter for the fix and are easy to miss:

1. **Different terminals.** `_reconcile_stale_running()` flips to `interrupted` and
   saves, leaving the file in `.running/`. `_reconcile_stale_runs()` *archives* —
   `persistence.clear_all()` moves state to `.history/` and unlinks the `.pid`. It
   never writes `interrupted`; its own docstring says `interrupted` files are left
   alone so the user can resume them.
2. **Different PID resolution.** The read path calls `_resolve_live_pid()`
   (`.pid` → `.lock` → `state.pid`). The startup path reads **only** the sibling
   `.pid` file (`persistence.py:645-652`) and ignores `.lock` and `state.pid`
   entirely. "No PID resolvable" is therefore a strictly wider condition on the
   startup path than on the read path.

PID resolution fails permanently for any state written before PID tracking existed,
and for any run whose `.pid`/`.lock` files were cleaned up (or removed by
`ll-loop stop`) while the state file kept `status: "running"`. Once in that
condition the entry is unreachable by both reconcilers and only manual deletion or
`/ll:cleanup-loops` clears it.

Because `ACTIVE_RUN_STATUSES = {"running", "starting"}`, `cmd_list` in
`scripts/little_loops/cli/loop/info.py` keeps rendering these entries under
`--running`, with a duration derived from the state's accumulated-elapsed field
(correct for the run, but presented as if the run were live).

## Expected Behavior

When no PID is resolvable, reconciliation falls back to an `updated_at` staleness
check: a `running` state whose last write is older than a threshold (default 6h) is
treated as not-live and flipped to `interrupted` with `reconciled_at` stamped.

**Both paths flip to `interrupted`; neither archives.** On the read path this already
matches the dead-PID behavior. On the startup path it does *not* — see
[Startup-path terminal](#startup-path-terminal-flip-do-not-archive) below, which
resolves what was a contradiction in an earlier revision of this issue.

### Why `updated_at` age is a valid liveness proxy — and its one limit

`PersistentFSM._handle_event()` (`fsm/persistence.py:892-894`) saves state on
`state_enter`, i.e. at the *start* of each state's action. So `now − updated_at`
measures **time spent inside the currently-executing action**, not idle time. The
threshold must therefore exceed the longest plausible single action, not the longest
plausible run.

- Human-in-the-loop waits are **not** exposed to this. `hitl-md.yaml` does not block
  in-process on a human — it emits a review artifact and terminates. Waits for a
  human go through handoff, which parks the state as `awaiting_continuation`, a
  distinct status this fallback never touches (`running` only).
- Residual exposure: `ActionSpec.timeout` defaults to `None` (`fsm/schema.py:708`),
  so a `shell` action has no universal ceiling. An unbounded action running >6h under
  a run whose `.pid`/`.lock` were both removed would be falsely flipped.
- That false positive is **self-healing on both paths as specified**: the live FSM
  rewrites `status: "running"` on its next `state_enter`. This is the load-bearing
  reason the startup path must flip rather than archive — an archive of a live run is
  not recoverable.

## Steps to Reproduce

1. Start any loop so `.loops/.running/<loop>.state.json` is written with
   `status: "running"`.
2. Kill the process without a clean shutdown, then delete the sibling `.pid` and
   `.lock` files (any state file predating PID tracking has `pid: null` and
   reproduces this directly).
3. Wait any amount of time — days or months.
4. Run `ll-loop list --running`.
5. Observe: the dead run is still listed as `[running]`, and re-reading its state
   file shows `status: "running"`, `reconciled_at: null`. It never reconciles.

## Root Cause

- **File**: `scripts/little_loops/fsm/persistence.py`
- **Anchor**: `in function _reconcile_stale_running()` (read path) and
  `in function _reconcile_stale_runs()` (startup path)
- **Cause**: Both treat "PID unresolvable" as "liveness unknown → leave alone."
  `_resolve_live_pid()` returns `None` whenever `.pid`, `.lock`, and `state.pid` are
  all absent, which is a permanent condition for legacy and cleaned-up entries. With
  no secondary liveness signal, the `running` status is a terminal trap.

## Proposed Solution

Add an `updated_at`-age fallback used only when `_resolve_live_pid()` returns `None`.
Keep the existing PID logic first — a resolvable, alive PID must still win regardless
of `updated_at` age.

```python
STALE_RUNNING_THRESHOLD_S: int = 6 * 3600  # no state write in 6h ⇒ not a live loop

def _running_state_is_stale(state: LoopState, threshold_s: int = STALE_RUNNING_THRESHOLD_S) -> bool:
    """True when a running state's last write is older than threshold_s."""
    if not state.updated_at:
        return False  # never saved — cannot judge; leave alone
    try:
        ts = datetime.fromisoformat(state.updated_at.replace("Z", "+00:00"))
    except ValueError:
        return False
    if ts.tzinfo is None:
        return False  # naive timestamp — provenance unknown, cannot judge; leave alone
    return (datetime.now(UTC) - ts).total_seconds() > threshold_s
```

#### Naive timestamps must abstain, not be assumed UTC

An earlier revision of this helper did `ts.replace(tzinfo=UTC)` to "tolerate legacy
naive timestamps." That is wrong and is a live false-positive source:
`StatePersistence.save_state()` writes `updated_at` via `_iso_now()`
(`fsm/persistence.py:117-119`), which is **always** `datetime.now(UTC).isoformat()` —
tz-aware, no exceptions. So a naive `updated_at` cannot have come from this codebase;
it can only come from a legacy or foreign writer, and the most likely such writer
emits **local** time. Reading a local timestamp as UTC inflates the computed age by
the writer's UTC offset — 7h in US/Pacific — which flips a run that is barely an hour
old. Abstaining (`return False`) matches the malformed-timestamp branch directly
above it and costs nothing: the entry stays `running` and is still reachable by
`/ll:cleanup-loops`. (`.astimezone()` is an acceptable alternative only if the local
zone is genuinely the writer's zone, which is not knowable here.)

#### `save_state()` rewrites `updated_at` — the flip is not evidence-preserving

`StatePersistence.save_state()` unconditionally sets `state.updated_at = _iso_now()`
before writing (`fsm/persistence.py:482`). The flip therefore **destroys the last-real-
activity timestamp**, which for these orphans is the only record of when the process
actually died. Two consequences the implementer must not be surprised by:

- The death time is still reconstructible from `started_at + accumulated_ms`, and
  `reconciled_at` records when the flip happened. Nothing is unrecoverable, but
  `updated_at` stops meaning "last activity" for a reconciled entry.
- `/ll:cleanup-loops`'s independent 15-minute `updated_at` heuristic (see the
  Documentation section below) will see a freshly-flipped entry as **fresh**. This is
  harmless in practice — that heuristic only applies to `running` loops and the entry
  is now `interrupted` — but it is the reason the two thresholds must not later be
  "unified" by keying both off `updated_at` alone.

This behavior is inherited from the existing dead-PID flip, which has the same
property; consistency is the reason to accept it rather than hand-write the file to
preserve `updated_at`. Accepted deliberately — do not "fix" it as part of this issue.

#### Orphaned `.lock` files are left in place — deliberately

The fallback only fires when `_resolve_live_pid()` returns `None`, which by definition
means there is no `.pid` file to unlink. A `.lock` file *can* still survive the flip:
one that is malformed, unreadable, or missing its `pid` key falls through
`_resolve_live_pid()`'s `except` clause to `state.pid` (`persistence.py:240-250`) and
yields `None`. Do **not** add speculative `.lock`/`.pid` unlinks to the flip —
`LockManager.find_conflict()` already owns stale-lock cleanup, and `cmd_stop` has its
own orphaned-lock branch. The flip's job is the status field only.

In `_reconcile_stale_running()`, replace the bare `if pid is None: return state`
with: if `pid is None` and `_running_state_is_stale(state)` → flip to `interrupted`,
stamp `reconciled_at`, `persistence.save_state(state)`; otherwise return unchanged.

### Startup-path terminal: flip, do not archive

`_reconcile_stale_runs()`'s new fallback **flips the state to `interrupted` in place
and leaves the file in `.running/`** — it does *not* call `clear_all()`. Rationale:

- It matches AC 1 and the read path, so one rule describes both.
- It matches that function's existing policy of leaving `interrupted` files resumable.
- It is the only variant that survives a false positive. An archive of a
  still-live-but-quiet run destroys the state file out from under the process; a flip
  is overwritten by the process's next `state_enter` save.

The entry stops polluting `ll-loop list --running` immediately, because `interrupted`
is not in `ACTIVE_RUN_STATUSES`.

**Accepted cost: a flipped orphan stays in `.running/` permanently.** An earlier
revision claimed it "is archived later by the ordinary path once it reaches a terminal
status" — that is false for exactly the entries this fix targets. The process is dead,
so it will never reach a terminal status, and `_reconcile_stale_runs()` deliberately
skips `interrupted` files so users can resume them. Nothing will ever sweep these; the
only removal path is a human running `/ll:cleanup-loops` (or deleting the file).

This is accepted rather than solved: the population is bounded by the number of runs
that ever died with no resolvable PID, the entries are invisible to
`ll-loop list --running`, and any automatic archive would reintroduce the
false-positive hazard that flip-not-archive exists to avoid. Do **not** add a
second-stage "archive once `reconciled_at` is old enough" sweep under this issue —
file it separately if `.running/` growth is ever observed to matter.

> Note for the implementer: `_reconcile_stale_runs()` returns a count of **archived**
> files, and `TestReconcileStaleRuns` asserts on it. A flip is not an archive — do not
> increment `archived` for it. Add a separate counter (and, if useful, include it in
> the existing summary log line) rather than conflating the two.

### Startup path must adopt `_resolve_live_pid()`

Before adding the age fallback there, change that branch's PID lookup from the bare
`.pid`-file read to `_resolve_live_pid(running_dir, stem, state)`. Without this, "no
`.pid` file" would trigger the age fallback on a run whose `.lock` or `state.pid`
still names a **live** process. This is a real behavior change to
`_reconcile_stale_runs()`, not just an added branch, and it also fixes a
pre-existing narrowness in that path.

Alternative considered and rejected: deleting/archiving unresolvable entries outright
— `interrupted` is the correct terminal here because it stays resumable, matching how
the read path's dead-PID branch already behaves.

### Not in scope: `accumulated_ms` vs `started_at`

The reporting consumer (`ll-console`) computes elapsed as `now − started_at`. That is
its own bug and its own repo — `ll-console` has no source in this codebase (no
`ll-console` entry point in `scripts/pyproject.toml`, no `/api/projects` handler).
The authoritative duration is `LoopState.accumulated_ms`, already emitted by
`LoopState.to_dict()` and already what `cmd_list` reads. No change needed here;
notify that consumer separately.

### Rejected diagnosis (do not implement)

The originating report proposed "reset `started_at` on resume so it stays
authoritative." This must **not** be done:

- `started_at` is intentionally the first-ever start; `PersistentFSM.resume()`
  restores it verbatim and carries prior elapsed forward via
  `self._executor.elapsed_offset_ms = state.accumulated_ms`.
- It is load-bearing identity: the archive `run_id` is derived from it
  (`StatePersistence.archive_run()`), and `list_run_history()` sorts on it.
  Rewriting it mid-run would rename archive directories and break run identity.
- The two-field split is already correct and consistent: `started_at` = when the run
  began; `accumulated_ms` = active elapsed across all segments, excluding paused gaps.

The report's headline evidence ("resumed ~45 min ago, shown as 4 months") does not
hold: the observed state file was never resumed. It ran once for 44m52s
(`accumulated_ms: 2692855`, matching `updated_at − started_at`) and the process died.
Both numbers were correct; only the *liveness* claim was false.

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/persistence.py` — `_reconcile_stale_running()`,
  `_reconcile_stale_runs()` (age fallback **plus** switching its PID lookup to
  `_resolve_live_pid()` and flipping rather than archiving), new
  `_running_state_is_stale()` + `STALE_RUNNING_THRESHOLD_S`

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/info.py` — `cmd_list` (via `list_running_loops`);
  no code change expected, behavior change only
  > ⚠ Superseded — `cmd_status` lives in `lifecycle.py`, not here
- `scripts/little_loops/cli/loop/lifecycle.py` — `cmd_status` (calls
  `_reconcile_stale_running` at lines ~161, ~223, ~312, ~348 via
  `_build_status_dict`/`_status_single`); no code change expected, behavior change
  only [Agent 1 finding, graph-confirmed]
- `scripts/little_loops/cli/loop/run.py` — `cmd_run` (line ~347, function-local
  import) calls `_reconcile_stale_runs` — this is the actual startup sweep call
  site [Agent 1 finding, graph-confirmed]
  > ⚠ Superseded — was misattributed to `fsm/executor.py`, which has zero
  > references to any reconciliation symbol (confirmed by grep)
- `scripts/little_loops/fsm/__init__.py` — re-exports `list_running_loops` in
  `__all__` (line ~247) [Agent 1 finding]
- `scripts/little_loops/mcp_server/tasks.py` — `handle_tasks_get()` reads
  `accumulated_ms`/status via `read_run_status()` (`lifecycle.py`), which calls
  `_build_status_dict()` → `_reconcile_stale_running()` — a documented transitive
  dependency (`lifecycle.py`'s `read_run_status` docstring cites Decision 1:
  PID-liveness reconciliation); benefits from correct statuses [Agent 1/2 finding]
- `scripts/little_loops/transport.py` — `_make_seed_callback()` (line ~591) calls
  `list_running_loops()` directly to seed dashboard clients on connect; genuine
  direct dependency, no code change expected [Agent 1 finding, graph-confirmed]

### Similar Patterns
- `LockManager.find_conflict()` stale-lock cleanup in
  `scripts/little_loops/fsm/concurrency.py` — same "prove it's dead" shape; consider
  whether it needs the same age fallback (out of scope unless it shares the trap)

### Tests
- `scripts/tests/` FSM persistence tests — add cases: (a) unresolvable PID + fresh
  `updated_at` → left `running`; (b) unresolvable PID + `updated_at` older than
  threshold → flipped to `interrupted` with `reconciled_at` set; (c) resolvable live
  PID + old `updated_at` → left `running`; (d) empty `updated_at`, malformed
  `updated_at`, and **naive (tz-less) `updated_at` older than the threshold** → all
  left alone (three assertions; the naive case guards the abstain rule above).

> **Correction — the synthetic `starting` entries are not a test case here.** An
> earlier revision asked case (d) to assert against the `status: "starting"` entries
> `list_running_loops()` fabricates for PID-file-only instances, on the theory that
> their `updated_at=""` reaches the staleness guard by a second route. It does not,
> for three independent reasons: those entries are constructed *after* the
> reconcile loop, from `.pid` files only, and are appended directly to `states`
> without ever being passed to `_reconcile_stale_running()`
> (`fsm/persistence.py:1262-1280`); they are only built at all when
> `_process_alive(pid)` is **true**, so they are by construction live; and
> `"starting"` is never persisted to a state file anywhere in the codebase (the only
> producers are `cli/loop/lifecycle.py:515` and `mcp_server/tasks.py:155`, both
> synthesizing it for a response payload). The scenario is unconstructible — do not
> write a test for it. The empty-`updated_at` assertion in case (d) should use an
> ordinary `status: "running"` state file.

Additional cases required by the clarifications above:
(e) startup path, unresolvable PID + stale `updated_at` → flipped to `interrupted`,
**still present in `.running/`** (not archived), and not counted in the function's
archived return value; (f) startup path, no `.pid` file but a live PID in `.lock` or
`state.pid` + stale `updated_at` → left `running` (regression guard for the
`_resolve_live_pid()` adoption); (g) read path, non-stale state → `save_state` is
**not** called (no write amplification — `list_running_loops()` runs on every
dashboard client connect).

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_fsm_persistence.py` `TestReconcileStaleRuns` (startup path,
  **line 3226**, not ~3009-3121 as originally recorded) — extend `_write_state()`
  (**line 3228**; `updated_at` hardcoded to `""` at line 3239) with an `updated_at`
  param and add cases (a)-(g) above. This class has no direct unit test for
  `_reconcile_stale_running()` (the read path) at all [Agent 3 finding — confirmed
  gap]. Its existing `count == N` assertions bound the archived total — flips must
  not perturb them.
- `scripts/tests/test_cli_loop_lifecycle.py` `TestReconcileStaleRunning` (line
  2734) — an existing class already exercising `_reconcile_stale_running()`
  indirectly via `cmd_status`, not previously listed in this issue. Its
  `_make_state()` helper (line 2737) currently takes only `(status, pid)`; extend it
  with an `updated_at` param. [Agent 3 finding — confirmed]
- `scripts/tests/test_cli_loop_lifecycle.py::TestReconcileStaleRunning::test_no_reconcile_no_pid_anywhere`
  (line 2852) — **will break** under this fix: its fixture hardcodes
  `updated_at="2026-05-24T10:05:00Z"`, which is now >6h stale, so the state will
  flip to `interrupted` and its `assert state.status == "running"` /
  `assert state.reconciled_at is None` assertions will fail. [Agent 3 finding —
  confirmed breaking test, verified against the current file]
  **Preferred fix**: default `_make_state()`'s new `updated_at` param to a *fresh*
  relative timestamp and add an explicit stale-case variant test. No other test in
  the class depends on the fixture's `updated_at` age (the dead-PID cases short-
  circuit before the fallback), so this repairs the break without touching them.
- No `freezegun`/`freeze_time` dependency exists in this repo. Follow the
  relative-timestamp pattern from `scripts/tests/test_cli_loop_next.py` (lines
  ~127-178): `(datetime.now(UTC) - timedelta(hours=7)).isoformat()` for stale,
  `timedelta(minutes=5)` for fresh — no `datetime` monkeypatching needed for
  ordinary threshold cases. [Agent 3 finding]
- `scripts/tests/test_transport.py`, `test_json_output_contracts.py`,
  `test_ll_loop_commands.py` all mock `list_running_loops` directly and bypass
  `_reconcile_stale_running()`'s internal logic entirely — unaffected by this
  change, no update needed. [Agent 1/3 finding, informational]

### Documentation
- `docs/reference/CLI.md` — `ll-loop list --running` reconciliation note, if it
  documents the current PID-only rule

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md:924` — confirmed: the `ll-loop status` note describes only
  the PID-dead rewrite ("If a state file claims `status: running` but its PID … is
  provably dead …"); needs an additive sentence for the new `updated_at`-age
  fallback. [Agent 2 finding]
- `docs/reference/CLI.md:4812-4816` — the `tasks/get` MCP doc's "reconciles PID
  liveness before ever reporting `working`" line is accurate but incomplete after
  this fix (reconciliation now also covers no-PID/stale-`updated_at`). [Agent 2
  finding]
- `docs/guides/MCP_SERVER_GUIDE.md:550` — same wording duplicated from CLI.md's MCP
  section; same additive update needed. [Agent 2 finding]
- `skills/cleanup-loops/SKILL.md:69` — Note documents only the PID-dead rewrite,
  same incompleteness. Also worth flagging to skill authors: the skill implements
  its own independent 15-minute `updated_at` staleness check (lines ~91-114) for
  no-PID `running` loops, which now partially overlaps with the new 6h fallback for
  loops stuck 15min-6h without a resolvable PID (the skill's tighter threshold
  still does non-redundant work outside that window, so no behavior change is
  required — informational only). [Agent 2 finding]
  **Record the rationale for the two thresholds** so a later reader does not try to
  unify them: the skill's 15-minute rule is user-initiated and advisory (it proposes
  `ll-loop stop` for a human to approve), so it can afford to be aggressive; the
  reconciler's 6h rule fires automatically with no confirmation and must be
  conservative enough that it never pre-empts a long single action. Same condition,
  different blast radius, deliberately different numbers.

### Configuration
- N/A (threshold is a module constant; promote to `.ll/ll-config.json` only if a real
  need appears)

_Wiring pass added by `/ll:wire-issue`:_
- Precedent confirmed for the "module constant, not config" choice:
  `scripts/little_loops/session_store/writers.py:2000` —
  `STALE_SUBAGENT_MIN_AGE_SECONDS = 6 * 3600`, the *same* 6-hour value, used as the
  identical age-fallback threshold shape for `reconcile_stale_subagent_runs()` in a
  sibling subsystem, also kept as a bare constant rather than config-schema-exposed.
  [Agent 2 finding — supports the existing N/A decision, no action needed]

## Program Design

### Types

- `STALE_RUNNING_THRESHOLD_S: int`

### Signatures

- `_running_state_is_stale(state: LoopState, threshold_s: int = STALE_RUNNING_THRESHOLD_S) -> bool`
- `_reconcile_stale_running(state: LoopState, persistence: StatePersistence, running_dir: Path, stem: str) -> LoopState` — unchanged signature, new fallback branch
- `_reconcile_stale_runs(loops_dir: Path) -> int` — unchanged signature; new fallback branch, PID lookup switched to `_resolve_live_pid()`, and a flip-in-place terminal that does not count toward the archived total

### Call Path

`list_running_loops` -> `_reconcile_stale_running` -> `_running_state_is_stale` -> `StatePersistence.save_state`

## Implementation Steps

1. Add `STALE_RUNNING_THRESHOLD_S` and `_running_state_is_stale()` to
   `fsm/persistence.py`.
2. Wire the fallback into `_reconcile_stale_running()`'s `pid is None` branch.
   Confirm `save_state()` is still reached only on an actual flip.
3. In `_reconcile_stale_runs()`'s `status == "running"` branch, switch the PID lookup
   from the bare `.pid`-file read to `_resolve_live_pid(running_dir, stem, state)`.
4. Add the age fallback to that same branch, with a **flip-in-place** terminal
   (`status = "interrupted"`, `reconciled_at` stamped, `save_state()`) rather than
   `clear_all()`, tracked in a counter separate from `archived`.

   > **Structural warning — this is not another `is_stale = True`.**
   > `_reconcile_stale_runs()` currently funnels every stale case through a single
   > `is_stale` boolean into one archive block (`fsm/persistence.py:642-670`, ending
   > in `persistence.clear_all()` + `.pid` unlink + `archived += 1`). Setting
   > `is_stale = True` for the age-fallback case would archive the entry — the exact
   > outcome AC 2 forbids. The flip must be its own branch that performs the
   > save and then `continue`s, placed **before** the `if not is_stale: continue`
   > guard so control never reaches the archive block. Getting this wrong is silent:
   > the tests that would catch it are case (e) and the `count == N` assertions.
5. Repair `test_no_reconcile_no_pid_anywhere` and add the regression tests (a)-(g)
   above.
6. Verify against a real orphaned artifact: a months-old `pid: null` running entry
   read via `ll-loop list --running` now flips to `interrupted` and drops off the
   running list.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Update `scripts/tests/test_cli_loop_lifecycle.py::TestReconcileStaleRunning::test_no_reconcile_no_pid_anywhere` — its fixture's hardcoded `updated_at` is now stale under the new threshold and the test will fail without a fix
- Extend `scripts/tests/test_fsm_persistence.py::TestReconcileStaleRuns._write_state()` with an `updated_at` parameter to support the new fresh/stale/malformed test cases
- Extend `scripts/tests/test_cli_loop_lifecycle.py::TestReconcileStaleRunning._make_state()` with an `updated_at` parameter for the same reason
- Add a direct unit test for `_reconcile_stale_running()` (read path) — no such test exists today; coverage is only indirect via `cmd_status`
- Update `docs/reference/CLI.md` (both the `ll-loop status` note at ~line 924 and the `tasks/get` MCP section at ~lines 4812-4816) and `docs/guides/MCP_SERVER_GUIDE.md:550` to describe the new age-fallback path, not just the PID-dead rewrite
- Update `skills/cleanup-loops/SKILL.md:69`'s reconciliation Note for the same reason
- Switch `_reconcile_stale_runs()`'s running-branch PID lookup to `_resolve_live_pid()` — it currently reads only the sibling `.pid` file and would otherwise apply the age fallback to runs with a live PID in `.lock`/`state.pid`
- Give the startup path a flip-in-place terminal (not `clear_all()`) and keep it out of the function's `archived` count, which `TestReconcileStaleRuns` asserts on

## Impact

- **Priority**: P3 — Misleading observability only. No data loss, no execution
  impact; the state file stays resumable either way (`running` is already in
  `RESUMABLE_STATUSES`, so the flip does not change what `ll-loop resume` can select).
  Visible because dead runs pollute `--running` and any consumer that filters on
  status, and the entries accumulate permanently. The fix corrects the *status* those
  entries report; it does not remove them from `.running/` or from the unfiltered
  dashboard seed (see the Summary note and the flip-in-place rationale).
- **Effort**: Small-to-medium — one helper plus two call-site branches, all inside a
  single module and reusing the existing flip-and-save path, but the startup path
  additionally needs its PID lookup widened to `_resolve_live_pid()` and a new
  flip-in-place terminal alongside its existing archive terminal.
- **Risk**: Low — the change only widens reconciliation for entries that today are
  provably unreachable. A resolvable live PID still short-circuits on both paths
  after the `_resolve_live_pid()` adoption. The threshold exceeds any plausible
  single action but is not formally bounded by one (`ActionSpec.timeout` defaults to
  `None`), so a >6h unbounded action on a PID-less run can be flipped early; because
  both paths flip rather than archive, the live FSM simply rewrites `running` on its
  next `state_enter`, and the state is resumable regardless.
- **Breaking Change**: No

## Acceptance Criteria

- [x] A `running` state with no resolvable PID and `updated_at` older than the
      threshold is flipped to `interrupted` with `reconciled_at` set, on both the
      read path and the startup sweep.
- [x] The startup sweep **flips such an entry in place and leaves it in
      `.running/`** — it does not archive it — and does not count it toward the
      function's archived return value.
- [x] A `running` state with no resolvable PID but a recent `updated_at` is left
      untouched.
- [x] A `running` state with a resolvable, live PID is left untouched regardless of
      `updated_at` age, on both paths — including a startup-path entry whose PID is
      resolvable only from `.lock` or `state.pid` with no `.pid` file present.
- [x] The read path calls `save_state()` only when a flip actually occurs; a
      non-stale entry causes no disk write (`list_running_loops()` runs on every
      dashboard client connect via `transport.py`'s seed callback).
- [x] A `running` state with no resolvable PID and a **naive (tz-less)**
      `updated_at`, however old, is left untouched — the helper abstains rather than
      assuming UTC.
- [x] Regression tests covering cases (a)-(g) — including the empty, malformed, and
      naive `updated_at` guards — pass under `python -m pytest scripts/tests/`.
- [x] `started_at` semantics are unchanged; no test asserts it advances on resume.

---

## Resolution

- **Action**: fix
- **Completed**: 2026-08-25
- **Status**: Completed

### Changes Made
- `scripts/little_loops/fsm/persistence.py`: added `STALE_RUNNING_THRESHOLD_S` and `_running_state_is_stale()`; `_reconcile_stale_running()` (read path) falls back to the age check when no PID is resolvable, flipping to `interrupted` with `reconciled_at` set; `_reconcile_stale_runs()` (startup path) switched its PID lookup to `_resolve_live_pid()` and gained a flip-in-place terminal (not archived, not counted in the `archived` return value) for the same fallback.
- `scripts/tests/test_fsm_persistence.py`: added `TestRunningStateIsStale`, `TestReconcileStaleRunningReadPath` (direct read-path coverage, cases a-d/g), and startup-path cases (e)-(f) on `TestReconcileStaleRuns`; extended `_write_state()` with an `updated_at` param; repaired a stale-fixture false failure in `test_list_running_loops_does_not_reconcile_no_pid`.
- `scripts/tests/test_cli_loop_lifecycle.py`: extended `TestReconcileStaleRunning._make_state()` with an `updated_at` param (defaulting fresh); added `test_reconciles_no_pid_anywhere_when_updated_at_stale`; repaired `test_no_reconcile_no_pid_anywhere`'s now-stale hardcoded fixture timestamp and one multi-instance list fixture.
- `scripts/tests/test_ll_loop_errors.py`, `scripts/tests/test_ll_loop_integration.py`: repaired hardcoded `updated_at` fixtures that had aged past the new 6h threshold and were incidentally flipping to `interrupted` under the fix.
- `docs/reference/CLI.md`, `docs/guides/MCP_SERVER_GUIDE.md`, `skills/cleanup-loops/SKILL.md`: documented the `updated_at`-age fallback alongside the existing PID-dead rewrite note.

### Deviations
- `_running_state_is_stale()`'s malformed-timestamp guard was widened from `except ValueError` to `except (ValueError, AttributeError, TypeError)`. The Program Design's helper only anticipated a string `updated_at` that fails `datetime.fromisoformat()` parsing; several existing tests pass `LoopState.updated_at` as a `MagicMock` attribute, and `state.updated_at.replace(...)` on a non-string raises `TypeError`/`AttributeError` rather than `ValueError`, which the fallback must also abstain on rather than propagate.

### Verification Results
- Tests: PASS (`python -m pytest scripts/tests/ -m "not integration and not conformance"` — 20624 passed, 20 skipped, 2 pre-existing unrelated failures confirmed present on `main` before this change: `test_doc_counts_all_match`, `test_no_new_unverifiable_evidence`)
- Lint: PASS (`ruff check`)
- Format: PASS (`ruff format`)
- Types: PASS (`mypy scripts/little_loops/fsm/persistence.py`)
- Integration: PASS (touchpoints in `cli/loop/lifecycle.py`, `cli/loop/run.py`, `cli/loop/info.py`, `transport.py`, `mcp_server/tasks.py` are all unchanged-signature callers; behavior-only change, exercised via existing indirect tests)

## Status

**Open** | Created: 2026-08-24 | Priority: P3


## Session Log
- `/ll:manage-issue` - 2026-08-25T02:49:33 - `a28bb905-d21d-485a-a69c-9a948a7fec63.jsonl`
- `/ll:ready-issue` - 2026-08-25T02:24:22 - `e0929c60-f5f4-42fa-aa3c-c4c8800c580b.jsonl`
- `/ll:confidence-check` - 2026-08-25T02:16:13 - `61734527-3e26-4ea8-812d-93186175aab9.jsonl`
- `/ll:confidence-check` - 2026-08-25T01:07:07 - `c0b9fe69-0e8b-4aa4-850b-b9fc74a99fe4.jsonl`
- `/ll:wire-issue` - 2026-08-25T00:59:30 - `35df48ee-1624-44f3-9b90-d443ec0fa011.jsonl`
- `/ll:refine-issue` - 2026-08-25T00:27:16 - `b31fdb34-d45a-44b4-81b6-d5f34a9cf389.jsonl`
