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
- BUG-3209
confidence_score: 85
outcome_confidence: 86
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 25
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

Those rows are indistinguishable from a genuinely in-flight agent, which makes any
future consumer of this table (ENH-3211, FEAT-3183) report a false picture.

**Correction 2026-08-16 — the "slow leak" premise is false, and the upstream cause is
BUG-3209.** An earlier draft argued "the leak is slow, not ongoing at volume: `completed`
grew by 18 between two measurements while `running` stayed flat at 40 — which is part of
why this is P3." Re-measured 2026-08-16: **43 `running`** against 2,719 `completed`, i.e.
+3 in roughly one day, and the three newest rows are

    2026-08-16T03:57:21Z  ll:codebase-locator
    2026-08-16T03:57:30Z  ll:codebase-analyzer
    2026-08-16T03:57:38Z  ll:codebase-pattern-finder

— the three-agent fan-out `/ll:wire-issue` ran while wiring *these* issues. "Flat at 40"
was a two-sample artifact taken across a quiet window, not a rate.

Two consequences:

- **BUG-3209 is the generator.** A backgrounded spawn whose parent turn ends is reaped by
  `_kill_process_group()` before `SubagentStop` fires, so the row opened by
  `SubagentStart` never closes. `relates_to: BUG-3209` added both ways. **Sequence
  BUG-3209 first** — it cuts the rate at the source; this issue reconciles the backlog.
  Reconciling against a population still growing underneath is the avoidable ordering.
- **P3 still holds, but on the impact argument only** (nothing reads this table today),
  not on the rate argument. Do not re-cite "the leak is slow" as justification.

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
available. A replacement draft proposed **later activity in the same parent session**:
compare the row's `started_at` against `max(ts)` for that `session_id` in `tool_events`,
and treat later parent activity as proof the row is orphaned.

**That replacement is also wrong. Do not implement it as the primary rule.** The
measurement below (re-run 2026-08-15) shows it is the *weaker* of the two branches, and
that the issue had the primary and the fallback backwards.

**The measurement.** Comparing each row's `started_at` against `max(ts)` in `tool_events`
for its `parent_session_id`, across both statuses:

                          running (40)      completed (2717)
    later activity             16                2629
    no later activity          24                  21
    no tool_events              0                  67

**(1) "Later activity" does not discriminate.** 2629 of 2650 joinable `completed` rows
(99.2%) *also* show later parent activity. "The parent kept working after the spawn" is
simply the normal case for every spawn — live, dead, or finished. It is not positive
evidence of orphaning; it is evidence that a session did more than one thing. Combined
with `status = 'running'` it looks discriminating only because the status filter is
doing all the work.

The concrete failure this causes: a genuinely in-flight background subagent in an
*active* session trips the rule the instant its parent issues one more tool call — and
gets marked `orphaned` while still running. That is precisely the misclassification the
negative test is meant to prevent, produced by the rule itself rather than caught by it.

**(2) The *other* branch is the high-precision signal, and it is the majority case.**
"The parent has **no** `tool_events` after the spawn" — the parent died at the spawn, the
Stop hook never fired, and nothing further was ever recorded — holds for **24 of 40
running rows (60%)** but only **21 of 2650 joinable completed rows (0.8%)**. That is a
~75× enrichment in the orphan population. It needs no quiet-period guard and no age
threshold, because it is not the normal case for a healthy spawn.

**Corrected rule — invert the primary and the fallback.**

**Primary (high precision, 24/40).** A `running` row is reconciled to `orphaned` when
`max(ts)` in `tool_events` for its `parent_session_id` is **not later** than the row's
`started_at`, `parent_session_id` is not the currently-executing session, **and the row's
`started_at` is older than the minimum-age window** (see below).

**Correction 2026-08-16 — the primary branch DOES need an age guard, for a different reason
than the secondary branch does.** An earlier draft asserted "no quiet-period window is
required for this branch — a parent that recorded nothing at all after the spawn is not
'still working alongside a live agent.'" That inference does not survive contact with how
the sweep actually runs.

The 75× enrichment is real, but it is measured over a **historical snapshot in which every
stale row is weeks old**. At sweep time the population is different, because a subagent
spawned *seconds ago* has exactly the primary branch's signature: its parent is blocked
waiting on it and has therefore recorded **no `tool_events` after `started_at`**. "Parent
recorded nothing after the spawn" is indistinguishable between *the parent died at the spawn*
and *the parent is right now waiting on a live subagent*. Age is the only thing separating
them, and the snapshot has age baked in invisibly.

The "not the currently-executing session" condition does **not** close this. `ll-parallel`
and `ll-sprint` run multiple concurrent `claude` sessions against one shared
`.ll/history.db` by design (`sprints.default_max_workers`), and this issue's own Decision 1
puts the sweep at *another* session's `SessionStart`. So the live in-flight rows the sweep
sees belong to sibling sessions, not the current one, and sail past that check. A sweep
firing while a sibling worker is mid-spawn would mark a genuinely running subagent
`orphaned` — violating this issue's own hard requirement ("0 rows that are genuinely still
in flight are misclassified", Success Metrics).

**Fix — a minimum row age on the primary branch, sharing the secondary branch's constant.**
A `running` row is eligible only if `now - started_at` exceeds the same window used by the
secondary branch. Use **one** module-level constant for both branches rather than a
secondary-only guard; the two branches ask different questions of it (row age vs. parent
quiet time) but the same value answers both, and a single constant is one thing to justify
and one thing to tune.

**The value is `6` hours — settled here, not left to the implementer.** Earlier drafts said
only "hours, not minutes", which is not a number the step-5 tests can be written against.
`STALE_SUBAGENT_MIN_AGE_SECONDS = 6 * 3600`. Justification: the ceiling on a plausible live
subagent is the host's own kill path — `post_stream_close_grace_seconds` defaults to 300s
(`config/automation.py:26`), so any spawn still genuinely in flight 6 hours later is
already impossible under the process model. 6h is ~72× that ceiling, well past any
`ll-parallel` worker's runtime, and costs nothing on the measured population: every one of
the 24 primary-branch rows is ≥1 day old. Erring long is the sanctioned direction
(under-reconciling is acceptable, misclassifying a live spawn is not), so a later tuning
change should move it up, not down.

This costs nothing on the measured population: all 24 primary-branch rows date from
2026-07-21 to 2026-08-15, so coverage is unchanged at 24/40. It converts the branch from
"high precision on a historical snapshot" to "high precision at sweep time", which is the
only precision that matters.

**Secondary (low precision, needs the guard, 16/40).** A row whose parent *does* show
later activity is reconciled only when that `max(ts)` is itself older than a quiet-period
window, and `parent_session_id` is not the currently-executing session. The quiet-period
window is what converts a non-discriminating comparison into evidence; pick it well
outside any plausible subagent runtime — hours, not minutes — and state the chosen value
in the implementation. Without the guard this branch actively misclassifies live spawns
and is worse than leaving the rows alone.

**Correction to a factual claim in earlier drafts.** Those drafts said the non-later
rows "have no `tool_events` evidence at all" and must therefore fall through to a bare
`started_at` age threshold. That is false: **0 of 40** running rows lack a joinable
parent with `tool_events` (see the table — the `no tool_events` cell is 0 for `running`).
Every one of the 40 has tool_events; the 24 simply have none *after* the spawn, which is
the positive evidence above rather than an absence of evidence. **A pure-age fallback may
therefore not be needed at all** — if it is kept, it is for rows matching neither branch
(currently none), not for a 57%-of-rows majority case.

The join is viable: 39 of the 40 stale rows have a `parent_session_id` present in
`sessions`; **0** have a null parent.

**Third signal — investigated 2026-08-15, dead. Do not spend the timebox.** An earlier
draft proposed checking `agent_transcript_path` as independent completion evidence.
Measured: it is NULL for **all 40** `running` rows and non-NULL for **all 2717**
`completed` rows. It is written by the Stop hook, so it is an exact proxy for "Stop
fired" and carries zero information beyond `status` itself. Likewise
`ended_at IS NULL` selects exactly the same 40 rows as `status = 'running'`.

Best-effort per the EPIC-1707 contract — never raise, never block. A row with no
resolvable evidence is **left alone**.


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

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-16 — based on codebase analysis:_

- Re-verified 2026-08-16 (codebase-analyzer): `subagent_runs` DDL (schema.py v28), `SubagentRun` dataclass (`history_reader.py:291`), `record_subagent_run_start`/`record_subagent_run_stop` (`writers.py:1800`/`:1855`), `_backfill_subagent_runs` (`writers.py:2063`), `sweep_stale_refs.handle()`'s two early returns (`:173-175`, `:194-196`), `hooks/__init__.py:72`'s `session_end`→`SessionStart` mapping, and `tool_events`'s index set (`idx_tool_events_agent`/`idx_tool_events_mcp_server`/`idx_tool_events_mcp_outcome`, still no `session_id` index) all match this issue's current draft exactly — zero drift despite `schema.py`/`history_reader.py` mtimes postdating the prior refine pass.

## Expected Behavior

A `subagent_runs` row whose parent has demonstrably moved on and gone quiet (or whose
`started_at` is old enough with no evidence either way) no longer reads as
indistinguishable from a genuinely in-flight spawn — it carries the distinct `orphaned`
status. Per Decision 3, no `reconciled_at` stamp is added (that would require a schema
migration this issue excludes); `ended_at` stays `NULL`, correctly recording that no end
was ever observed.

## Motivation

Live evidence from this repo's own `.ll/history.db` (40 stale `running` rows against
2,717 `completed`, oldest from 2026-07-21) shows the problem is not hypothetical. Any
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

**Placement inside `handle()` is load-bearing — put the call near the TOP of the `try`.**
`sweep_stale_refs.handle()` (`:141-208`) has **two early returns** before its tail:

- `:173-175` — `if not done_ids: _record_sweep(...); return LLHookResult(exit_code=0)`
- `:194-196` — `if not all_findings: _record_sweep(...); return LLHookResult(exit_code=0)`

The second is the **normal** case: most sessions find no stale cross-issue references, so
control never reaches the end of the function. A reconciliation call appended at the tail —
the intuitive reading of "add it to the existing sweep" — would therefore almost never run,
and the issue would land looking implemented while reconciling nothing.

Place the call immediately inside the `try`, before the `done_ids` guard, wrapped in its own
`try/except Exception: pass` so a reconciliation failure cannot suppress the stale-ref sweep
(and vice versa — the two features share a hook but must not share a failure mode). The
outer `except Exception` at `:207` is a backstop, not a substitute: it would swallow the
stale-ref sweep along with the reconciliation.

A test asserting reconciliation runs when `done_ids` is empty is the cheap way to pin this.

**Decision 1b — the query runs inside a 15-second hook budget and must not be a
per-row correlated subquery.** Found 2026-08-16, pre-implementation review; Decision 1
picks the host but never states its cost ceiling.

`hooks/hooks.json` runs the `session_end` intent as
`bash ${CLAUDE_PLUGIN_ROOT}/hooks/adapters/claude-code/session-end.sh` under the
`SessionStart` matcher with **`"timeout": 15`**. That budget is already shared with the
full stale-ref sweep, which walks every open issue file — and step 2a deliberately puts
reconciliation at the *front* of it, ahead of both early returns. Anything slow here
delays session start on every session and risks the sweep being killed.

Measured on this repo's live DB (2026-08-16):

- the natural formulation — `WHERE (SELECT max(t.ts) FROM tool_events t WHERE
  t.session_id = r.parent_session_id) <= r.started_at` — costs **0.32s** over 160,247
  `tool_events` rows;
- there is **no index on `tool_events(session_id)`**. The indexes that exist are
  `idx_tool_events_agent`, `idx_tool_events_mcp_server`, `idx_tool_events_mcp_outcome`.
  So each candidate row drives a full scan of the fastest-growing table in the DB.

0.32s fits today and will not fit indefinitely. Two options; pick one and state it:

- **(i) One `GROUP BY` pass, no index — preferred, and needs no schema change.** Compute
  `SELECT session_id, max(ts) FROM tool_events GROUP BY session_id` once (or restricted to
  the parent session IDs of `running` rows), join it against the candidate rows in Python,
  and issue a single `UPDATE ... WHERE id IN (...)`. One scan per sweep instead of one per
  row.
- **(ii) Add `idx_tool_events_session`.** Faster and simpler to write, but it is a
  `CREATE INDEX` migration. Scope Boundaries excludes "the schema" — that was written
  about *columns*, so decide explicitly whether an index counts, rather than letting the
  implementer read it either way.

Either way, add a bound: if the candidate set is empty (the common case once the backlog
is cleared), the sweep must do **no** `tool_events` work at all — check
`SELECT 1 FROM subagent_runs WHERE status='running' LIMIT 1` first, using the existing
`idx_subagent_status`.

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
(`_process_alive()`, `fsm/concurrency.py:56`) as ENH-1669 uses — it is the two-branch
`tool_events` comparison established in the Summary: **no-post-spawn-activity as the
primary (high-precision) branch**, later-activity-plus-quiet-period as the secondary, and
"no evidence → leave alone" as the failure mode.

**Decision 4 — the quiet-period window is a required constant on the secondary branch,
and the secondary branch is optional.** Bare later-parent-activity is non-discriminating
(Summary § (1)); shipping it without the quiet-period guard produces active
misclassification of live subagents, which is strictly worse than the status quo of
leaving rows `running`.

Because the primary branch now carries 24 of 40 rows on its own, the correct response to
"the quiet-period window is hard to choose" is to **ship the primary branch alone and
leave the other 16 rows `running`** — under-reconciling is the sanctioned failure mode.
Dropping the guard while keeping the secondary branch is not an option. This replaces the
earlier instruction to fall back to a bare age rule, which was premised on the (incorrect)
claim that 23 rows had no `tool_events` evidence.

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

**Corrected 2026-08-16.** This section previously gave only
`_reconcile_stale_running(state: LoopState, persistence: StatePersistence, running_dir: Path, stem: str) -> LoopState`
— which is the **FSM mirror target being copied from**, not anything this issue
introduces. Its parameter shape (state object, persistence handle, directory, key) does
not adapt to a SQL sweep and should not be read as a template. The signature this issue
actually adds, in `session_store/writers.py`:

```python
STALE_SUBAGENT_MIN_AGE_SECONDS = 6 * 3600

def reconcile_stale_subagent_runs(
    db: Path | str,
    *,
    current_session_id: str | None,
    min_age_seconds: int = STALE_SUBAGENT_MIN_AGE_SECONDS,
    include_secondary: bool = False,
    dry_run: bool = False,
) -> int:
    """Mark orphaned `running` rows as `orphaned`. Returns rows updated.

    Best-effort per the EPIC-1707 contract: catches `sqlite3.Error`, logs at
    WARNING, never raises. `current_session_id=None` disables the
    current-session exclusion (see Decision Rules § Nullable current-session ID).
    `include_secondary` gates the optional later-activity branch.
    `dry_run=True` runs the full selection and returns the count that *would*
    be updated without issuing the UPDATE (see Decision 5).
    """
```

**Decision 5 — `dry_run` is required, not optional polish.** Step 6's success check is
"run the sweep against this repo's live `.ll/history.db`" — an unguarded, unrepeatable
mutation of real telemetry with no way to preview the selection or re-run it after a
miscount. `dry_run` makes that step safe (inspect the count and the selected rows before
committing), repeatable (re-run freely while tuning `min_age_seconds`), and gives the
step-5 tests a cheaper assertion surface: the negative tests (live sibling-worker row,
current-session row, terminal row) can assert `dry_run=True` returns `0` without needing
to re-read the table to prove nothing changed. Cost is one branch around the UPDATE.

The hook call site always uses the default `dry_run=False`; the flag exists for step 6
and for tests.

`_reconcile_stale_running` (`fsm/persistence.py:243`) remains the **precedent for the
guard structure** — first-guard on non-`running` status, "no signal → leave alone" — and
is listed under Dependent Files (Precedent to Mirror) for that reason only.

### Call Path
`SessionStart` host event `->` `hooks/__init__.py` dispatch of the `session_end` intent
(`:72`) `->` `sweep_stale_refs.handle()` (already writes today) `->` new reconciliation
writer in `session_store/writers.py` `->` `UPDATE subagent_runs SET status='orphaned'`
for rows passing the later-parent-activity (or age-fallback) test.

### Decision Rules
- Gate: a `subagent_runs` row is eligible for reconciliation only when `status ==
  "running"` — mirrors `_reconcile_stale_running()`'s own first guard
  (`if state.status != "running": return state`).
- **Primary signal — no parent activity after the spawn, on a row old enough to be dead.**
  All three must hold: (i) `max(ts)` in `tool_events` for the row's `parent_session_id` is
  **not later** than the row's `started_at`; (ii) `parent_session_id` is not the
  currently-executing session; (iii) **`now - started_at` exceeds the minimum-age window**
  (the shared constant, hours not minutes). Measured enrichment for (i): 24/40 running (60%)
  vs 21/2650 joinable completed (0.8%). This is the majority-case rule and the one to ship
  first.

  Condition (iii) is **not optional** and is not the same guard the secondary branch needs.
  A subagent spawned seconds ago also satisfies (i) — its parent is blocked waiting on it and
  has recorded nothing since — and satisfies (ii) whenever it belongs to a sibling
  `ll-parallel`/`ll-sprint` worker rather than the sweeping session. Without (iii) the
  primary branch marks live in-flight spawns `orphaned` under exactly the concurrency the
  automation stack is built around. See Summary § Correction 2026-08-16.

- **Shared constant.** The minimum-age window (primary, condition iii) and the quiet-period
  window (secondary, condition ii) are one module-level constant, not two — value settled
  at **6 hours** (`STALE_SUBAGENT_MIN_AGE_SECONDS = 6 * 3600`, see Summary § Fix). Both are
  asking "has enough time passed that a live spawn is implausible?"; splitting them doubles
  the tuning surface for no gain.
- **Nullable current-session ID.** `event.session_id` is `str | None`
  (`hooks/types.py:44`; the host does not always supply it). The "not the
  currently-executing session" condition therefore has an undefined case. Rule: when it is
  `None`, apply **no** exclusion and rely on the age guard alone — which is safe, because a
  row young enough for the current-session check to matter is already excluded by the 6h
  window. Do **not** skip the whole sweep on a `None` session ID; that would silently
  disable reconciliation on any host that omits the field.
- **NULL-safe comparison.** `max(ts) <= started_at` evaluates to NULL — i.e. neither branch
  matches — when the parent has **no** `tool_events` at all. That is 0 of 43 `running` rows
  today (though 67 `completed` rows are in that state), so it is latent rather than live,
  but a parent that never recorded a single tool event is the *most* orphaned case, not the
  least. Either `COALESCE` the subquery to `''` so those rows take the primary branch, or
  state deliberately that no-`tool_events` rows are left alone. Do not leave it to SQL's
  NULL semantics by accident.
- **Secondary signal — later parent activity AND a quiet period.** All three must hold:
  (i) `max(ts)` is later than `started_at`; (ii) that `max(ts)` is itself older than the
  quiet-period window; (iii) `parent_session_id` is not the currently-executing session.
  Condition (i) alone is **not** sufficient and must not be implemented as a rule — it
  holds for 2629 of 2650 joinable `completed` rows, so on its own it marks live in-flight
  subagents as orphaned (see Summary § (1)). Conditions (ii) and (iii) are what make it
  evidence. Resolves the remaining 16/40. Omitting this branch entirely is an acceptable
  scope cut; omitting the guard while keeping the branch is not.
- **Age fallback — probably unnecessary; do not build it speculatively.** The claim that
  23 rows have "no `tool_events` evidence at all" was wrong (Summary § Correction): 0 of
  40 running rows lack tool_events. Every row falls into the primary or secondary branch
  today, so there is no population left for a bare `started_at` threshold to serve. Add
  one only if a measured population of neither-branch rows appears, and give it its own
  test if so.
- **Explicitly unavailable:** "parent session has ended." `sessions` has no `ended_at`
  column and `session_lifecycle_events` emits no session-end event (verified — only
  `stale_ref_sweep`). Do not design against this signal.
- **Explicitly uninformative:** `agent_transcript_path` and `ended_at IS NULL`. Both are
  written by (or exactly track) the Stop hook — NULL for all 40 `running`, populated for
  all 2717 `completed` — so neither adds information beyond `status`. Verified
  2026-08-15.
- **Timing consequence of Decision 1.** The sweep runs at `SessionStart` of the *next*
  session, so condition "not the currently-executing session" is near-vacuous (the new
  session has no `subagent_runs` rows yet) and rows orphaned by the session that just
  died are reconciled on a **subsequent** sweep, not the immediately-following one, once
  the secondary branch's quiet window has elapsed. Primary-branch rows reconcile on the
  next sweep. Do not expect same-session reconciliation.
- Escape hatch: no evidence resolvable at all → leave the row untouched, mirroring
  `_reconcile_stale_running()`'s `if pid is None: return state`. "Cannot determine
  liveness, leave alone" is the established failure mode, not an edge case to skip.
- Settled (see Proposed Solution): status value is the literal `"orphaned"`; the check
  runs in the `sweep_stale_refs.py` `SessionStart`-hosted sweep, not the read path; no
  `reconciled_at` column is added.

## Impact

- **Priority**: P3 — telemetry accuracy only; nothing in the product reads this table
  today (ENH-3211 and FEAT-3183 will). **The rating rests on that impact argument alone.**
  The "leak is slow" justification is withdrawn — re-measured 2026-08-16 at 43 `running`
  (from 40), +3 in a day, all three from a single BUG-3209 spawn site. See Summary
  § Correction.
- **Effort**: Small — one writer function plus a call from an existing sweep that already
  writes. No schema migration (Decision 3), no new connection plumbing (Decision 1). The
  one non-obvious constraint is the 15s hook budget and the missing
  `tool_events(session_id)` index (Decision 1b), which shapes how the query is written.
- **Risk**: Medium (raised from Low 2026-08-16). The status value is additive on a
  CHECK-free TEXT column, and "no
  evidence → leave alone" means the intended failure mode is under-reconciling. **Both**
  branches carry a live-spawn misclassification hazard, and both are closed by the same
  shared time window:
  - the *secondary* branch, because bare later-parent-activity holds for 99.2% of
    `completed` rows and is not evidence of anything (Summary § (1)) — its quiet-period
    guard is mandatory or the branch is dropped;
  - the *primary* branch, because a subagent spawned seconds ago in a sibling
    `ll-parallel`/`ll-sprint` worker has the identical signature — blocked parent, no
    post-spawn `tool_events`, not the current session (Summary § Correction 2026-08-16) —
    so its minimum-age guard is equally mandatory. An earlier draft called this branch
    risk-free; that was an artifact of measuring a snapshot in which every stale row was
    already weeks old.

  Get the shared window wrong in the *short* direction and the hard requirement ("0 live
  rows misclassified") breaks under exactly the concurrency the automation stack uses.
  Wrong in the long direction, the sweep merely under-reconciles, which is sanctioned.
  Choose generously. The age-fallback risk noted in earlier drafts no longer applies — no
  bare age *rule* is built (Step 1b); the window here is a guard on other evidence, not a
  signal on its own.
- **Breaking Change**: No — but any reader pattern-matching `status == "running"` as a
  proxy for "not completed" changes meaning; audited in Backwards Compatibility below.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-08-16 | Priority: P3

## Current Pain Point

43 `subagent_runs` rows in this repo's `.ll/history.db` are stuck `running` (oldest since
2026-07-21T02:34:49Z, newest 2026-08-16T03:57:38Z) because their `SubagentStop` hook never
fired — the parent process group was reaped by `_kill_process_group()` first. The spawn
sites that produce them are catalogued in BUG-3209. `_backfill_subagent_runs()`
(`writers.py:2063`) cannot fix this: it is `INSERT OR IGNORE`, so it only seeds rows
that are missing entirely, never corrects one that already exists.

## Success Metrics

Stated as rules, not counts — the snapshot figures drift (17/23 at capture → 16/24 on
2026-08-15) and **"converges toward 0" is not the metric**. Recompute against the live
DB at implementation time.

- **Every row whose parent recorded no `tool_events` after the spawn** is reconciled to
  `orphaned` by the primary rule. On the 2026-08-15 snapshot that is 24 of 40.
- **Rows whose parent shows later activity** are reconciled only if the secondary branch
  ships and their parent's `max(ts)` clears the quiet-period window. On the 2026-08-15
  snapshot that is the remaining 16 of 40, all of whose parents last acted weeks ago.
  Leaving all 16 `running` is an acceptable outcome (Decision 4).
- **0 rows** that are genuinely still in flight are misclassified (see the ENH-1669
  negative-test precedent, `test_no_reconcile_live_background_pid`). This is the
  hard requirement — under-reconciling is acceptable, misclassifying a live spawn is not.
- The `completed` count is unchanged — reconciliation must never touch a terminal row.

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

1. **Primary branch.** A `running` row whose `parent_session_id` has no `tool_events`
   later than the row's `started_at`, which is not the currently-executing session, **and
   whose `started_at` is older than the shared minimum-age window**, is reconciled to
   `orphaned`. There is no existing session-liveness helper in
   `session_store`/`history_reader.py`, so this is new. This branch alone covers 24 of the
   40 known rows (the age guard excludes none of them — all are ≥1 day old) and is the
   minimum shippable unit.

   The age guard is a correctness requirement, not a refinement: without it the branch
   misclassifies a subagent spawned seconds ago in a sibling `ll-parallel` worker, whose
   blocked parent has by definition recorded nothing since the spawn. See Summary
   § Correction 2026-08-16.
1a. **Secondary branch (optional scope).** A `running` row whose parent *does* show later
   activity is reconciled only when that `max(ts)` is older than an explicitly chosen and
   documented quiet-period window (hours, not minutes) and the parent is not the
   currently-executing session. Shipping the later-activity comparison without the guard
   is an explicit defect, not a simplification — it marks live subagents `orphaned`
   (Summary § (1)). If the window cannot be justified, drop this branch and leave those
   16 rows `running`.
1b. No age fallback and no `agent_transcript_path` check are built. Both were
   investigated and closed 2026-08-15: 0 of 40 rows lack `tool_events` (so nothing falls
   through to age), and `agent_transcript_path` is a pure Stop-hook proxy carrying no
   information beyond `status`. See Summary § Third signal.
1c. **The shared window is 6 hours** (`STALE_SUBAGENT_MIN_AGE_SECONDS = 6 * 3600`), not an
   implementer choice — the step-5 negative tests are written against this number. See
   Summary § Fix for the derivation from `post_stream_close_grace_seconds`.
2. A reconciliation writer exists in `session_store/writers.py`
   (`reconcile_stale_subagent_runs`, signature under Program Design), called from
   `hooks/sweep_stale_refs.py`'s existing `session_end`-intent sweep, following the
   two-layer best-effort shape (`try/except sqlite3.Error` in the writer, never raise;
   hook handler returns `LLHookResult(exit_code=0)` regardless) every other
   `subagent_runs` writer already uses.

2b. **It fits the 15-second hook budget.** The `session_end` intent runs under
   `hooks/hooks.json`'s `SessionStart` matcher with `"timeout": 15`, shared with the full
   stale-ref sweep. Per Decision 1b: short-circuit on an empty candidate set before
   touching `tool_events` (using `idx_subagent_status`), and use a single `GROUP BY
   session_id` pass rather than a per-row correlated subquery — there is **no index on
   `tool_events(session_id)`**, so the natural formulation full-scans 160k+ rows per
   candidate (measured 0.32s today, growing). If option (ii) is chosen instead, the
   `CREATE INDEX` must be reconciled against Scope Boundaries explicitly.

2c. `event.session_id` may be `None`; that disables the current-session exclusion and
   nothing else (Decision Rules). The NULL-vs-no-`tool_events` case is resolved explicitly
   rather than left to SQL's NULL semantics.

2a. **The call sits near the top of `handle()`'s `try`, ahead of both early returns**
   (`:173-175` `if not done_ids`, `:194-196` `if not all_findings`), in its own
   `try/except Exception: pass` so the two features cannot suppress each other. Appending it
   at the tail is a silent no-op in the common case — most sessions have no stale refs and
   return at `:196`. Pinned by the test in step 5.
3. A row with no resolvable evidence is left untouched, matching
   `_reconcile_stale_running()`'s own "cannot determine liveness, leave alone" behavior —
   this is a correctness requirement, not an edge case to skip.
4. No schema migration is introduced — `status` takes the new `"orphaned"` value on the
   existing CHECK-free TEXT column, and no `reconciled_at` column is added (Decision 3).

4a. **`docs/guides/HISTORY_SESSION_GUIDE.md:132` is updated** — it is the only doc that
   enumerates this column's vocabulary
   (`` status (`running`/`completed`/`failed`/`timeout`) ``), and ENH-3211 is written
   against that vocabulary being correct. Add `orphaned`, and drop `timeout` in the same
   edit: no writer produces it (the live values are `running`/`completed`/`failed` via the
   Qwen sidecar path), so the enumeration is stale in both directions. This is a required
   step, not the optional doc polish an earlier draft's parenthetical implied.
5. `python -m pytest scripts/tests/test_enh_2505_subagent_runs.py scripts/tests/test_fsm_persistence.py -v`
   passes, including all of:
   - a positive test for the primary branch: a `running` row whose parent recorded no
     `tool_events` after `started_at` is reconciled;
   - a negative test for the **specific** failure mode the bare activity signal causes:
     a `running` row whose parent has later `tool_events` but is *still active* (inside
     the quiet-period window) is **not** reconciled — required whenever the secondary
     branch ships;
   - a negative test that a row in the currently-executing session is never reconciled;
   - **a negative test for the concurrency hazard on the primary branch:** a freshly-created
     `running` row (`started_at` = now) whose parent has **no** `tool_events` after the
     spawn and which belongs to a *different, non-current* session is **not** reconciled,
     because it is inside the minimum-age window. This is the `ll-parallel` sibling-worker
     case (Summary § Correction 2026-08-16) and is the single most important negative test
     in the set — without the age guard it fails;
   - **a placement test:** with `done_ids` empty (so `handle()` returns at `:175`) and with
     no stale findings (so it returns at `:196`), an eligible row is still reconciled —
     proving the call is ahead of both early returns (step 2a);
   - a test that `current_session_id=None` does not disable reconciliation (it only drops
     the current-session exclusion) — the nullable-`event.session_id` case;
   - an idempotency test asserting a second sweep is a no-op;
   - a test that `completed`/terminal rows are never touched;
   - a test that with **zero** `running` rows the sweep issues no `tool_events` query at
     all (step 2b's short-circuit) — the cheap guard on the 15s hook budget;
   - **a `dry_run=True` test:** an eligible primary-branch row yields a return count of
     `1` and the row's `status` is still `running` afterward — proving the flag selects
     without mutating. The negative tests above may assert against `dry_run=True` for the
     cheaper return-count check, but at least one negative case must also run with
     `dry_run=False` so the real UPDATE path is exercised against a non-eligible row.
6. **Dry-run first, then commit.** Call `reconcile_stale_subagent_runs(..., dry_run=True)`
   against this repo's own `.ll/history.db` and confirm the returned count matches the
   primary-branch count recomputed at implementation time; only then re-run with
   `dry_run=False`. Do not make the first execution against real telemetry a blind
   mutation — the table has no undo and no `reconciled_at` stamp (Decision 3) to identify
   which rows a bad run touched.

   The committed run reclassifies **at least the
   primary-branch rows** and leaves `completed` unchanged — the concrete success check.
   Recompute both branch counts at implementation time rather than asserting the
   snapshot figures; they have already drifted once (17/23 at capture → 16/24 on
   2026-08-15). A run that reclassifies all 40 is *not* required; a run that changes the
   `completed` count is a failure.

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-08-16_

**Readiness Score**: 85/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 86/100 → HIGH CONFIDENCE

### Concerns
- Format-check still flags a claim gap against the codebase: `TEXT` (claimed in
  `scripts/little_loops/session_store/schema.py`) resolves to a generic SQL column-type
  token rather than a named symbol — likely a linter false-positive, but per the
  Parity/Claim Cap rule its presence caps Criterion 4 (Issue Well-Specified) at 10/20
  regardless of how complete the rest of the spec is. Re-run `ll-issues format-check
  ENH-3210 --format json` after implementation to confirm it clears.
- `relates_to: BUG-3209` is a **soft, non-blocking** sequencing recommendation ("Sequence
  BUG-3209 first"), not a `blocked_by` dependency — BUG-3209 is still `open`. This issue
  is designed to work standalone (it reconciles the existing backlog regardless of whether
  BUG-3209 has landed), so this does not gate implementation; it only means the backlog
  keeps growing underneath until BUG-3209 ships.
- The secondary branch's quiet-period window is decided only qualitatively ("hours, not
  minutes") — unlike the primary branch's settled `STALE_SUBAGENT_MIN_AGE_SECONDS = 6 *
  3600`, no concrete number is pinned for the optional secondary branch. If that branch is
  implemented, the implementer must choose and justify a specific value (or drop the
  branch per Decision 4, which is explicitly sanctioned).

## Session Log
- `/ll:confidence-check` - 2026-08-16T04:58:36 - `3732fd32-810c-4cb4-9095-7a5a9dac49d5.jsonl`
- `/ll:decide-issue` - 2026-08-16T04:51:02 - `3da23951-99b8-442f-b7db-c8c9c673c9c0.jsonl`
- `/ll:refine-issue` - 2026-08-16T04:49:44 - `3da23951-99b8-442f-b7db-c8c9c673c9c0.jsonl`
- `/ll:confidence-check` - 2026-08-16T02:38:24 - `b3e5e9f8-dedd-44cd-94d8-d1536fb44209.jsonl`
- `/ll:wire-issue` - 2026-08-16T02:33:16 - `580ae8b9-3bf3-43a4-90b3-d6f005806398.jsonl`
- `/ll:refine-issue` - 2026-08-16T02:22:53 - `8d69c317-1f3a-48ba-9c8b-3d56c7aebd08.jsonl`
- `/ll:capture-issue` - 2026-08-16T02:10:52 - `3b0498bf-ef93-4aa9-88c2-660ecc956b99.jsonl`
