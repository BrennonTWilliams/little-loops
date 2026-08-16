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

Live evidence from this repo's `.ll/history.db`:

    completed | 2699
    running   |   40      # oldest started 2026-08-02

Those 40 rows are indistinguishable from a genuinely in-flight agent, which makes any
future consumer of this table (see the companion telemetry-surface issue) report a
false picture.

`_backfill_subagent_runs` (`writers.py:2063`) does not help: it is `INSERT OR IGNORE`,
so it seeds missing rows but never corrects an existing stale one.

Proposed fix: reconcile on read and/or at session end, mirroring the ENH-1669 loop-run
reconciliation that rewrites a `running` loop state to `interrupted` when its PID is
provably dead. Here the liveness signal is the parent session: a `running` row whose
`parent_session_id` has an ended session (or whose `started_at` is older than a
threshold with no matching live session) becomes `orphaned` with a `reconciled_at`
stamp. Keep it best-effort per the EPIC-1707 contract — never raise, never block.

Decide as part of implementation whether `orphaned` is a new status value or whether
the existing `status` column reuses an established term, and whether reconciliation
runs in the SessionEnd handler (mind the hard-ceiling bug noted in
`hooks/subagent_stop.py`'s docstring) or lazily at query time in `history_reader`.


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

Reconcile lazily, on the read path — mirroring `_reconcile_stale_running()`
(`fsm/persistence.py:243`), which is called from `list_running_loops()` on every read
rather than from a scheduled sweep, precisely because (per Current Behavior above)
`subagent_runs` has no reliable session-end-timed hook to hang a write-behind on. Since
there is no `pid` column here, the liveness signal cannot be `os.kill(pid, 0)`
(`_process_alive()`, `fsm/concurrency.py:56`) as ENH-1669 uses — it must be
session-based (a `parent_session_id` with no live session, or a `started_at` age
threshold) as the issue itself proposes. Because `history_reader.py`'s readers all use
`_connect_readonly()` (`:420`, `PRAGMA query_only = ON`), a read-time write-back needs a
second, separate writable connection opened the way `writers.py` opens its own — there
is no existing precedent in `history_reader.py` for that connection-mode split, so this
is new plumbing, not a reuse of an existing helper.

## Integration Map

### Files to Modify
- `scripts/little_loops/history_reader.py` — home for the lazy reconcile-on-read call,
  alongside `subagent_tree()` (:1573), `subagent_retries()` (:1604), `subagent_budget()` (:1638)
- `scripts/little_loops/session_store/writers.py` — needs a new reconciliation writer
  (mirroring `record_subagent_run_start`/`record_subagent_run_stop`'s best-effort shape),
  since `history_reader.py`'s connections are read-only (`_connect_readonly()`, `:420`,
  `PRAGMA query_only = ON`) and cannot issue the UPDATE themselves

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
No new dataclass. If `subagent_tree()`'s existing `SubagentRun` dataclass
(`history_reader.py:289-305`) gains a `reconciled_at` field mirroring
`LoopState.reconciled_at`, it stays `str | None` and is omitted from any dict
serialization when `None`, matching the ENH-1669 precedent.

### Signatures
`_reconcile_stale_running(state: LoopState, persistence: StatePersistence, running_dir: Path, stem: str) -> LoopState`

The mirror target above already establishes the parameter shape (state object,
persistence handle, directory, key) this issue's session-liveness variant would adapt.

### Call Path
`history_reader.py` reader call (e.g. `subagent_tree()`/`subagent_budget()`) `->` new
reconciliation check (session-liveness, since no `pid` column exists) `->` new writer in
`session_store/writers.py` (separate writable connection, `_connect_readonly()`'s
`PRAGMA query_only = ON` cannot issue the UPDATE) `->` `subagent_runs.status` row update.

### Decision Rules
- Gate: a `subagent_runs` row is eligible for reconciliation only when `status ==
  "running"` — mirrors `_reconcile_stale_running()`'s own first guard
  (`if state.status != "running": return state`).
- Liveness signal (session-based, since there's no `pid` column): a `parent_session_id`
  with a provably ended session, **or** `started_at` older than a threshold with no
  matching live session — exact threshold value is an implementation decision, not
  specified by research.
- Escape hatch: no PID/session evidence resolvable at all → leave the row untouched,
  mirroring `_reconcile_stale_running()`'s `if pid is None: return state` ("cannot
  determine liveness, leave alone" is the established failure mode, not an exception).
- Open (per Summary, unresolved by research): whether the new state is a literal
  `"orphaned"` status value or reuses an existing term, and whether the check lives in
  `history_reader.py` (read-path) or a startup-style sweep — both are structurally
  available precedents in this codebase, neither is the established default for this
  table specifically.

## Impact

- **Priority**: [P0-P5] - [Justification]
- **Effort**: [Small/Medium/Large] - [Justification]
- **Risk**: [Low/Medium/High] - [Justification]
- **Breaking Change**: [Yes/No]

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: [YYYY-MM-DD] | Priority: [P0-P5]

## Current Pain Point

40 `subagent_runs` rows in this repo's `.ll/history.db` are stuck `running` (oldest
since 2026-08-02) because their `SubagentStop` hook never fired — the parent process
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

1. A liveness check exists for a `subagent_runs` row's `parent_session_id` (or a
   `started_at`-age fallback when no session-liveness signal resolves) — there is no
   existing session-liveness helper in `session_store`/`history_reader.py` to call, so
   this is new, not reused.
2. A reconciliation write path exists that can flip a stale `running` row without going
   through `history_reader.py`'s read-only connections (`_connect_readonly()`), following
   the two-layer best-effort shape (`try/except sqlite3.Error` in the writer, never
   raise) every other `subagent_runs` writer already uses.
3. A row with no resolvable liveness evidence is left untouched, matching
   `_reconcile_stale_running()`'s own "cannot determine liveness, leave alone" behavior —
   this is a correctness requirement, not an edge case to skip.
4. `python -m pytest scripts/tests/test_enh_2505_subagent_runs.py scripts/tests/test_fsm_persistence.py -v`
   passes, including a negative test asserting a live/recent row is never reconciled.

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-08-15_

**Readiness Score**: 85/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 70/100 → MODERATE

### Concerns
- Format-check flags claim gaps against the codebase: `history_reader` (claimed in
  `subagent_stop.py`), `TEXT` (claimed in `schema.py`), and `subagent_runs` mislocated
  (claimed in `subagent_start.py`) — verify these symbol references before implementing;
  this caps Criterion 4 (Issue Well-Specified) at 10/20 per the Parity/Claim Cap rule.
- Two design decisions are explicitly deferred by the issue itself: whether the new state
  is a literal `"orphaned"` status value or reuses an existing term, and whether the
  reconciliation check lives in `history_reader.py`'s read path or a startup-style sweep.
  Neither is the established default for this table.
- The fix requires new plumbing with no direct precedent: a session-liveness check (no
  `pid` column exists to mirror ENH-1669's `os.kill(pid, 0)` approach) and a second,
  writable connection alongside `history_reader.py`'s read-only-only connections
  (`_connect_readonly()`, `PRAGMA query_only = ON`).

## Session Log
- `/ll:confidence-check` - 2026-08-16T02:38:24 - `b3e5e9f8-dedd-44cd-94d8-d1536fb44209.jsonl`
- `/ll:wire-issue` - 2026-08-16T02:33:16 - `580ae8b9-3bf3-43a4-90b3-d6f005806398.jsonl`
- `/ll:refine-issue` - 2026-08-16T02:22:53 - `8d69c317-1f3a-48ba-9c8b-3d56c7aebd08.jsonl`
- `/ll:capture-issue` - 2026-08-16T02:10:52 - `3b0498bf-ef93-4aa9-88c2-660ecc956b99.jsonl`
