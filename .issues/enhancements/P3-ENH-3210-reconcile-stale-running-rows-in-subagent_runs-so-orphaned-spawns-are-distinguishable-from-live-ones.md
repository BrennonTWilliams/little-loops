---
id: ENH-3210
type: ENH
title: Reconcile stale running rows in subagent_runs so orphaned spawns are distinguishable
  from live ones
priority: P3
status: open
testable: true
discovered_by: ll-issues-create
discovered_date: '2026-08-16'
captured_at: '2026-08-16T02:10:41Z'
relates_to:
- ENH-3211
confidence_score: 85
outcome_confidence: 70
score_complexity: 17
score_test_coverage: 25
score_ambiguity: 10
score_change_surface: 18
---

# ENH-3210: Reconcile stale running rows in subagent_runs so orphaned spawns are distinguishable from live ones

## Summary

`subagent_runs` rows are opened `running` by the SubagentStart hook
(`scripts/little_loops/hooks/subagent_start.py` -> `session_store/writers.py:1800`) and
closed by SubagentStop (`hooks/subagent_stop.py` -> `writers.py:1855`). When the Stop
hook never fires — the common case when the parent `claude -p` turn ends and
`_kill_process_group` reaps the process group (`subprocess_utils.py:630-645`) — the row
stays `running` forever.

Live evidence from this repo's `.ll/history.db` (re-measured 2026-08-15):

    completed | 2717
    running   |   40      # oldest started 2026-07-21T02:34:49Z
                          # newest  started 2026-08-15T03:48:55Z

Those 40 rows are indistinguishable from a genuinely in-flight agent, which makes any
future consumer of this table (ENH-3211, FEAT-3183) report a false picture. Note the
leak is slow, not ongoing at volume: `completed` grew by 18 between two measurements
while `running` stayed flat at 40 — which is part of why this is P3.

`_backfill_subagent_runs` (`writers.py:2063`) does not help: it is `INSERT OR IGNORE`,
so it seeds missing rows but never corrects an existing stale one.

**Liveness signal — corrected.** An earlier draft of this issue proposed "a
`parent_session_id` whose session has provably ended." **That signal does not exist.**
Verified against the live DB:

- `sessions` is `(session_id, jsonl_path, started_at, project_path)` — there is **no
  `ended_at` column**.
- `session_lifecycle_events` contains exactly one event kind, `stale_ref_sweep` (4,021
  rows) — **zero** session-end events.

As written that rule collapses to a bare `started_at` age threshold, the weakest option
available. Use instead a signal that does exist and carries positive evidence:
**later activity in the same parent session**. Compare the row's `started_at` against
`max(ts)` for that `session_id` in `tool_events` — if the parent kept working after the
spawn but no `SubagentStop` ever landed, the row is provably orphaned rather than
in-flight. Verified on the newest stale row (`b9fd5a8c…`, started `2026-08-15T03:48:55Z`,
parent's last tool event `2026-08-15T03:49:22Z`) — 27s of subsequent parent activity.

The join is viable: 39 of the 40 stale rows have a `parent_session_id` present in
`sessions`; **0** have a null parent.

Proposed fix, mirroring ENH-1669's loop-run reconciliation: a `running` row with
later-parent-activity evidence (primary) or an old `started_at` with no live parent
(fallback) becomes `orphaned`; a row with no resolvable evidence is **left alone**.
Best-effort per the EPIC-1707 contract — never raise, never block.


## Current Behavior

`subagent_runs.status` (`scripts/little_loops/session_store/schema.py`, v28 DDL) is a
bare `TEXT` column with no CHECK constraint, `UNIQUE(parent_session_id, agent_id)`, and
**no `pid` column** — unlike `LoopState.pid` in the FSM persistence model this issue
proposes mirroring, there is no OS PID recorded per subagent spawn to test liveness
against directly. `record_subagent_run_start()` (`writers.py:1800`) always writes
`status="running"`; `record_subagent_run_stop()` (`writers.py:1855`) is the only writer
that ever changes it, matched via `UPDATE ... WHERE agent_id = ? AND parent_session_id
IS ?`. When `_kill_process_group()` (`subprocess_utils.py:307`, called from the
stream-close loop at `subprocess_utils.py:640`) SIGKILLs the process group before the
host's `SubagentStop` event can fire, the row never transitions. There is currently no
reconciliation code path for `subagent_runs` at all — the ENH-1669 pattern this issue
names as its model exists only for FSM loop-run state files (`fsm/persistence.py`), not
for this table.

**Correction — no true `SessionEnd` binding exists to hang reconciliation on.** The
"SessionEnd handler" the Summary asks about is not bound to the host's actual
`SessionEnd` event. `sweep_stale_refs.py`'s module docstring records why: Claude Code
enforces a hard ~1.5s ceiling on `SessionEnd` hooks before killing them on any exit path
(anthropics/claude-code#32712, #41577), so the `session_end` *intent* is dispatched from
`SessionStart` instead (`hooks/__init__.py:72`, `_INTENT_EVENT_NAME["session_end"] =
"SessionStart"`) — it runs at the start of the *next* session, not the end of the
crashed one. `sweep_stale_refs.handle()`'s own telemetry write confirms this
(`trigger: "session_start"`). Any reconciliation hung off this intent inherits the same
timing, not true session-end timing.

## Expected Behavior

A `subagent_runs` row whose parent session has provably ended (or whose `started_at` is
old enough with no live parent) no longer reads as indistinguishable from a genuinely
in-flight spawn — it carries a distinct status and a `reconciled_at` stamp, mirroring
`LoopState.reconciled_at` in the ENH-1669 precedent.

## Motivation

Live evidence from this repo's own `.ll/history.db` (40 stale `running` rows against
2,699 `completed`, oldest from 2026-08-02) shows the problem is not hypothetical. Any
future consumer of this table — including the companion CLI-surface issue ENH-3211 —
would otherwise report orphaned spawns as if they were still running.

## Proposed Solution

**Decision 1 — where it runs: the existing `SessionStart`-hosted sweep, not the read
path.** `hooks/sweep_stale_refs.py` already runs on the `session_end` intent (re-homed to
`SessionStart`, `hooks/__init__.py:72`) and **already writes** to `history.db`. That is a
real precedent with working plumbing. The read-path alternative requires inventing a
second, writable connection inside `history_reader.py` — against `_connect_readonly()`'s
`PRAGMA query_only = ON` (`:420`), for which there is no precedent in that module — and
puts an UPDATE in the path of every reader call, contending on the same DB with live hook
writers. The two options are not equal-cost; take the sweep.

**Decision 2 — the status value: the literal `"orphaned"`.** `status` is a bare `TEXT`
column with no CHECK constraint, matching the `session_lifecycle_events.event`
open-discriminator convention (schema.py v27 comment), so a new value needs no migration.
ENH-3211 depends on this vocabulary being fixed, so it is settled here rather than
deferred to the implementer.

**Decision 3 — `reconciled_at` is a schema change; drop it.** `subagent_runs` has **no**
`reconciled_at` column, so mirroring `LoopState.reconciled_at` would mean a new v3x
migration — which contradicts this issue's own Scope Boundaries ("does not change... the
schema"). The `orphaned` status alone is sufficient to distinguish the state, and
`ended_at` stays `NULL` (correctly: no end was ever observed). If an audit stamp is later
judged necessary, raise it as a separate schema issue.

Since there is no `pid` column, the liveness signal cannot be `os.kill(pid, 0)`
(`_process_alive()`, `fsm/concurrency.py:56`) as ENH-1669 uses — it is the
later-parent-activity comparison established in the Summary, with an age threshold as
fallback and "no evidence → leave alone" as the failure mode.

## Integration Map

### Files to Modify
- `scripts/little_loops/session_store/writers.py` — new reconciliation writer, mirroring
  `record_subagent_run_start`/`record_subagent_run_stop`'s best-effort shape
  (`try/except sqlite3.Error`, log at WARNING, return `bool`, never raise)
- `scripts/little_loops/hooks/sweep_stale_refs.py` — the chosen host (Decision 1); already
  runs on the `session_end` intent and already writes, so the reconciliation call is an
  addition to an existing sweep, not new plumbing
- `scripts/little_loops/history_reader.py` — **not** modified for the write path (Decision
  1 rejects read-path write-back). Touch only if `SubagentRun`/reader output needs to
  surface the new `orphaned` value distinctly for ENH-3211.

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/hooks/subagent_start.py:37` — calls `record_subagent_run_start()`
  [Agent 1 finding]
- `scripts/little_loops/hooks/subagent_stop.py:42` — calls `record_subagent_run_stop()`
  [Agent 1 finding]
- `scripts/little_loops/session_store/lifecycle.py:1083` — calls
  `_backfill_subagent_runs()`; the `INSERT OR IGNORE` writer the issue already names as
  not helping — this is its one caller [Agent 1 finding]
- `.issues/features/P1-FEAT-3183-local-agent-quality-report-over-history-db.md` (~line 130)
  — names `subagent_runs.status`/`started_at`/`ended_at` as a planned "secondary signal"
  for a retry-inflation metric; not yet implemented, but a sibling consumer that will need
  to treat a new `orphaned` status distinctly from `running`/`completed` once it lands
  [Agent 2 finding]

### Dependent Files (Precedent to Mirror)
- `scripts/little_loops/fsm/persistence.py` — `_reconcile_stale_running()` (:243, the
  read-path mirror target), `_resolve_live_pid()` (:222), `list_running_loops()` (:1109,
  call site :1135), sibling startup-sweep `_reconcile_stale_runs()` (:605)
- `scripts/little_loops/fsm/concurrency.py` — `_process_alive()` (:56); not directly
  reusable here since `subagent_runs` has no `pid` column, but the "no proof of death ==
  leave alone" convention it embodies is the one to preserve
- `scripts/little_loops/hooks/sweep_stale_refs.py` — module docstring documents the
  SessionEnd hard-ceiling bug and the `session_end`→`SessionStart` re-homing; read before
  choosing a session-end-timed design
- `scripts/little_loops/hooks/__init__.py:72` — `_INTENT_EVENT_NAME["session_end"] =
  "SessionStart"`, confirming the intent's actual trigger point
- `scripts/little_loops/session_store/schema.py` — `subagent_runs` DDL (~:644),
  `session_lifecycle_events.event`'s open-TEXT-discriminator convention (v27 comment,
  ~:619-624) as the precedent for adding a new status value without a migration

### Conventions in Force
- Every producer touching `subagent_runs` follows a two-layer best-effort shape (EPIC-1707
  contract): the writer function catches `sqlite3.Error` narrowly, logs at `WARNING`, and
  returns `bool` (never raises); the hook handler wraps the whole call in
  `try/except Exception: pass` and always returns `LLHookResult(exit_code=0)` — evidence:
  `record_subagent_run_start`/`writers.py:1824-1852`, `subagent_start.py::handle()`.
- Two competing "when does reconciliation run" conventions coexist in this codebase for
  the FSM precedent (read-path in `cmd_status`/`list_running_loops`, and a separate
  startup sweep in `cli/loop/run.py`) — they are not presented as alternatives to pick
  one of, both exist for different call sites. `subagent_runs` has no startup-sweep
  equivalent entry point today.
- PID-liveness in this codebase is `os.kill(pid, 0)` + `ESRCH`/`EPERM` disambiguation
  (`_process_alive()`), never re-derived per caller — but there is no session-liveness
  counterpart anywhere in `session_store`/`history_reader.py` to reuse; whatever
  `parent_session_id`-liveness check this issue needs is new.

### Tests
- `scripts/tests/test_cli_loop_lifecycle.py::TestReconcileStaleRunning` (:2612) and
  `scripts/tests/test_fsm_persistence.py::TestReconcileStaleRuns` (:2941) — the coverage
  shape to mirror: dead-signal-per-source cases, an explicit **negative** test for a live
  case that must not reconcile (`test_no_reconcile_live_background_pid`), and an
  already-reconciled idempotency/no-op case
- `scripts/tests/test_enh_2505_subagent_runs.py` — existing direct-reader test convention
  (`tmp_path`-scoped sqlite db, writer calls to seed rows, direct reader-function calls)

_Wiring pass added by `/ll:wire-issue`:_
- Exact test methods to mirror the four-shape skeleton from: `TestReconcileStaleRuns`'s
  `test_terminal_status_file_is_archived` (:2963), `test_dead_pid_file_is_archived`
  (:2993), `test_live_pid_file_is_left_alone` (:3011, the negative case),
  `test_missing_pid_file_running_left_alone` (:3029, no-signal-available case); and
  `TestReconcileStaleRunning`'s `test_reconciles_dead_state_pid_no_pid_file` (:2639),
  `test_no_reconcile_live_lock_pid` (:2685, negative case),
  `test_no_reconcile_already_interrupted` (:2709), `test_no_reconcile_no_pid_anywhere`
  (:2730) — each asserts both the status field and a `reconciled_at`-style audit marker
  [Agent 3 finding]
- `scripts/tests/test_session_store_lifecycle.py:127` — asserts
  `counts["subagent_runs"] == 0` in a base counts-dict fixture for `_backfill_subagent_runs`'s
  return contract; only needs a new key if reconciliation is wired into the shared
  `rebuild()`/backfill counts dict (`session_store/lifecycle.py:1061-1083`) rather than
  kept as an independent read-path check [Agent 2 finding]
- Confirmed no existing test enumerates `subagent_runs.status` as a closed set — all
  status assertions are point-checks (`row["status"] == "..."`) against a specific
  writer's output, not a scan over all rows, so a new status value does not break any
  existing assertion by itself [Agent 3 finding]
- No existing test simulates a hook process killed mid-run (start written, stop never
  called) — the direct integration-level analog of the reconciliation gap this issue
  fixes; `TestSubagentStartStopHookHandlers` (`test_enh_2505_subagent_runs.py:196`) is
  the closest fixture to build a new one from [Agent 3 finding]

### Documentation
- N/A — no doc currently describes `subagent_runs` reconciliation semantics

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/HISTORY_SESSION_GUIDE.md:132` — literally enumerates the schema as
  `` status (`running`/`completed`/`failed`/`timeout`) `` — needs the new status value
  added (and this enumeration is itself stale today: no writer currently produces
  `"timeout"`, only `"running"`/`"completed"`/`"failed"` via the Qwen sidecar path)
  [Agent 2 finding]
- `docs/guides/BUILTIN_HOOKS_GUIDE.md:490-496` — describes SubagentStart writing a
  `running` row and SubagentStop updating to `completed`; natural place to add a sentence
  documenting reconciliation as a third status-mutation path [Agent 2 finding]
- `docs/ARCHITECTURE.md` — v28 schema-history row (~line 652); the established pattern
  (per v27's own entry) is to append a new dated note rather than edit the v28 entry in
  place [Agent 2 finding]

### Configuration
- N/A — per Scope Boundaries below, no config knob (mirrors ENH-1669's own decision)

## Program Design

### Types
No new dataclass and no new field. Per Decision 3, `SubagentRun`
(`history_reader.py:289-305`) does **not** gain a `reconciled_at` field — that would
require a `subagent_runs` schema migration this issue's Scope Boundaries excludes. The
`orphaned` value in the existing `status` field carries the whole signal.

### Signatures
`_reconcile_stale_running(state: LoopState, persistence: StatePersistence, running_dir: Path, stem: str) -> LoopState`

The mirror target above already establishes the parameter shape (state object,
persistence handle, directory, key) this issue's session-liveness variant would adapt.

### Call Path
`SessionStart` host event `->` `hooks/__init__.py` dispatch of the `session_end` intent
(`:72`) `->` `sweep_stale_refs.handle()` (already writes today) `->` new reconciliation
writer in `session_store/writers.py` `->` `UPDATE subagent_runs SET status='orphaned'`
for rows passing the later-parent-activity (or age-fallback) test.

### Decision Rules
- Gate: a `subagent_runs` row is eligible for reconciliation only when `status ==
  "running"` — mirrors `_reconcile_stale_running()`'s own first guard
  (`if state.status != "running": return state`).
- **Primary signal — later parent activity.** `max(ts)` in `tool_events` for the row's
  `parent_session_id` is later than the row's `started_at` ⇒ the parent kept working past
  the spawn and no `SubagentStop` ever landed ⇒ `orphaned`. This is positive evidence, not
  a timeout, and it is the rule to implement first.
- Fallback signal — age. `started_at` older than a threshold with no later-activity
  evidence either way ⇒ `orphaned`. Threshold is an implementation choice; pick
  generously (days, not minutes) since the primary signal already covers the common case.
- **Explicitly unavailable:** "parent session has ended." `sessions` has no `ended_at`
  column and `session_lifecycle_events` emits no session-end event (verified — only
  `stale_ref_sweep`). Do not design against this signal.
- Escape hatch: no evidence resolvable at all → leave the row untouched, mirroring
  `_reconcile_stale_running()`'s `if pid is None: return state`. "Cannot determine
  liveness, leave alone" is the established failure mode, not an edge case to skip.
- Settled (see Proposed Solution): status value is the literal `"orphaned"`; the check
  runs in the `sweep_stale_refs.py` `SessionStart`-hosted sweep, not the read path; no
  `reconciled_at` column is added.

## Impact

- **Priority**: P3 — telemetry accuracy only; nothing in the product reads this table
  today (ENH-3211 and FEAT-3183 will). The leak is slow: 40 stale rows accumulated since
  2026-07-21 and did not grow across two measurements while `completed` gained 18.
- **Effort**: Small — one writer function plus a call from an existing sweep that already
  writes. No schema migration (Decision 3), no new connection plumbing (Decision 1).
- **Risk**: Low — additive status value on a CHECK-free TEXT column; the "no evidence →
  leave alone" rule means the failure mode is under-reconciling, not misclassifying a
  live spawn. Main risk is a too-aggressive age fallback, covered by a negative test.
- **Breaking Change**: No — but any reader pattern-matching `status == "running"` as a
  proxy for "not completed" changes meaning; audited in Backwards Compatibility below.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-08-16 | Priority: P3

## Current Pain Point

40 `subagent_runs` rows in this repo's `.ll/history.db` are stuck `running` (oldest
since 2026-07-21T02:34:49Z) because their `SubagentStop` hook never fired — the parent process
group was reaped by `_kill_process_group()` first. `_backfill_subagent_runs()`
(`writers.py:2063`) cannot fix this: it is `INSERT OR IGNORE`, so it only seeds rows
that are missing entirely, never corrects one that already exists.

## Success Metrics

The 40/2,699 stale-row count in this repo's own history.db converges toward 0 stale
rows after reconciliation runs, without any row that is genuinely still in flight being
misclassified (see the ENH-1669 negative-test precedent,
`test_no_reconcile_live_background_pid`).

## Scope Boundaries

Mirrors ENH-1669's own explicit boundary: reconciliation is unconditional, no config
knob (`.issues/enhancements/P3-ENH-1669-reconcile-orphaned-running-state-files-with-dead-pids.md`, Key Decision section — "knob is
YAGNI"). Does not change the write path (`record_subagent_run_start`/
`record_subagent_run_stop`) or the schema beyond whatever status value/column the
implementer chooses for the orphaned state.

## Backwards Compatibility

`status TEXT` has no CHECK constraint (consistent with `session_lifecycle_events.event`,
schema.py v27 comment: "an open TEXT discriminator... so new values can share this
table"), so introducing a new status value requires no migration — existing rows and
readers that pattern-match on `"running"`/`"completed"` are the only backward-compat
surface to check (`history_reader.py`'s `subagent_budget()` already special-cases
`ended_at IS NULL` rows out of its duration sum, so it already tolerates non-`completed`
statuses without a code change).

## API/Interface

`record_subagent_run_start(agent_id: str, agent_type: str) -> bool`

## Implementation Steps

1. A later-parent-activity check exists: for a `running` row, `max(ts)` in `tool_events`
   for its `parent_session_id` compared against the row's `started_at`. There is no
   existing session-liveness helper in `session_store`/`history_reader.py`, so this is
   new. An `started_at`-age fallback covers rows with no `tool_events` evidence.
2. A reconciliation writer exists in `session_store/writers.py`, called from
   `hooks/sweep_stale_refs.py`'s existing `session_end`-intent sweep, following the
   two-layer best-effort shape (`try/except sqlite3.Error` in the writer, never raise;
   hook handler returns `LLHookResult(exit_code=0)` regardless) every other
   `subagent_runs` writer already uses.
3. A row with no resolvable evidence is left untouched, matching
   `_reconcile_stale_running()`'s own "cannot determine liveness, leave alone" behavior —
   this is a correctness requirement, not an edge case to skip.
4. No schema migration is introduced — `status` takes the new `"orphaned"` value on the
   existing CHECK-free TEXT column, and no `reconciled_at` column is added (Decision 3).
5. `python -m pytest scripts/tests/test_enh_2505_subagent_runs.py scripts/tests/test_fsm_persistence.py -v`
   passes, including a negative test asserting a live/recent row is never reconciled and
   an idempotency test asserting a second sweep is a no-op.
6. Running the sweep against this repo's own `.ll/history.db` reclassifies the 40 stale
   rows and leaves `completed` at 2717 — the concrete success check.

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-08-15_

**Readiness Score**: 85/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 70/100 → MODERATE

### Concerns
- Format-check flags claim gaps against the codebase: `history_reader` (claimed in
  `subagent_stop.py`), `TEXT` (claimed in `schema.py`), and `subagent_runs` mislocated
  (claimed in `subagent_start.py`) — verify these symbol references before implementing;
  this caps Criterion 4 (Issue Well-Specified) at 10/20 per the Parity/Claim Cap rule.
- ~~Two design decisions are explicitly deferred~~ — **resolved 2026-08-15** (see Proposed
  Solution): status value is `"orphaned"`; the check runs in `sweep_stale_refs.py`'s
  existing `SessionStart`-hosted sweep; no `reconciled_at` column.
- ~~The fix requires a second writable connection alongside `history_reader.py`'s
  read-only connections~~ — **no longer applicable**: Decision 1 moves the write to
  `sweep_stale_refs.py`, which already holds a writable connection. The remaining new
  work is the liveness comparison itself.
- **New concern (2026-08-15, blocking at capture, now corrected):** the issue's original
  primary liveness signal — "parent session has provably ended" — had no data behind it.
  `sessions` has no `ended_at` column and `session_lifecycle_events` contains only
  `stale_ref_sweep` rows. Replaced with the later-parent-activity signal, verified against
  the live DB. Re-verify this holds before implementing if the schema has moved since.

## Session Log
- `/ll:confidence-check` - 2026-08-16T02:38:24 - `b3e5e9f8-dedd-44cd-94d8-d1536fb44209.jsonl`
- `/ll:wire-issue` - 2026-08-16T02:33:16 - `580ae8b9-3bf3-43a4-90b3-d6f005806398.jsonl`
- `/ll:refine-issue` - 2026-08-16T02:22:53 - `8d69c317-1f3a-48ba-9c8b-3d56c7aebd08.jsonl`
- `/ll:capture-issue` - 2026-08-16T02:10:52 - `3b0498bf-ef93-4aa9-88c2-660ecc956b99.jsonl`
