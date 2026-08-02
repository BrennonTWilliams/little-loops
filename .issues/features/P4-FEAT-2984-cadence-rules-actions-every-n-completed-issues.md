---
id: FEAT-2984
title: 'cadence.rules: configurable actions triggered every N completed issues'
type: FEAT
priority: P4
status: deferred
discovered_by: design-conversation
discovered_date: 2026-08-01
labels:
- cli
- config
- automation
- issues
testable: true
deferred_by: human
deferred_date: '2026-08-02T01:44:38Z'
---

# FEAT-2984: `cadence.rules` — configurable actions on every N completed issues

## Summary

Backlog-maintenance work (`ll-issues normalize --auto`, `/ll:audit-issue-conflicts`,
`/ll:prioritize-issues`, `ll-verify-docs`, `ll-doctor --full`, `ll-session backfill`) should
run periodically but nobody remembers to. Give users a `cadence.rules` config block that
fires a declared set of actions (CLI command, skill, or FSM loop) every N completed issues,
optionally filtered by issue type/priority.

The counting substrate already exists: `issue_events` in `.ll/history.db` is a durable,
deduped ledger written by **every** completion path. The dispatch substrate exists as
`run_action()`/`RunnerType`. The contention substrate exists as `fsm.concurrency.LockManager`.
This feature is the predicate + firing ledger that ties them together — not a new execution
engine.

## Current Behavior

No periodic-maintenance trigger exists. Users either remember to run hygiene commands
manually or the backlog drifts (duplicate issues, stale priorities, doc-count drift). The
only recurring-execution primitives are host-level (`/loop`, cron routines), which live
outside little-loops and know nothing about issue completions.

## Expected Behavior

A `cadence` block in `.ll/ll-config.json`:

```jsonc
"cadence": {
  "enabled": true,
  "catch_up": "coalesce",
  "rules": [
    {
      "id": "backlog-hygiene",
      "every": 10,
      "dispatch": "notify",
      "actions": [
        { "runner": "cmd",   "target": "ll-issues normalize --auto" },
        { "runner": "skill", "target": "/ll:audit-issue-conflicts" }
      ],
      "scope": [".issues/"]
    },
    {
      "id": "bug-pattern-review",
      "every": 5,
      "when": { "type": ["BUG"] },
      "actions": [{ "runner": "loop", "target": "root-cause-cluster" }]
    }
  ]
}
```

- `ll-cadence status` — per-rule count-since-last-fire, next-fire estimate, pending actions,
  circuit-breaker state. `--json`.
- `ll-cadence check [--dry-run]` — evaluate predicates, record fires, enqueue/dispatch.
- `ll-cadence run` — drain pending cadence actions via `run_action()`.
- `ll-cadence fire <rule_id> --now` — manual trigger, ignoring the predicate.

## Proposed Solution

### 1. Count is derived, never incremented

Do **not** maintain a counter file. Evaluate the predicate as a SQL count against
`issue_events`:

```sql
SELECT COUNT(*) FROM issue_events
WHERE transition = 'done' AND ts > :last_fire_ts   -- + optional issue_type/priority filter
```

Every completion path already converges on this table (see Codebase Research Findings), so a
human typing `ll-issues set-status X done`, an `ll-auto` run, and an `ll-parallel` worktree
worker all feed the same count with no new plumbing. Because the count is re-derived rather
than incremented, a dropped write delays a fire but never causes permanent drift.

### 2. Firing is idempotent, so evaluation can be liberal

A new `cadence_fires(rule_id, fired_at, at_count, outcome)` table records each fire. With
`last_fire_ts` as the query anchor, double-evaluation is a no-op by construction. That
removes the need to find "the one true hook point" — evaluate cheaply from several
touchpoints (post-completion, `ll-cadence status`, SessionStart hook) and let idempotency
sort it out.

### 3. Dispatch is decoupled from execution — and does not depend on `ll-queue`

`ll-queue` is optional and new, so cadence must not require it. Firing writes durable
*pending action* rows; a per-rule `dispatch` mode decides what happens next:

- `notify` (**default**) — pending actions surface in `ll-cadence status` and the SessionStart
  hook. Zero dependency, zero surprise token spend. The human runs `ll-cadence run`.
- `queue` — `ll-queue add <target> --runner <kind>` when `ll-queue` is in use.
- `inline` — opt-in only: `run_action()` at fire time.

Inline execution must never be the default. Running `/ll:scan-codebase` inside `ll-auto`'s
loop burns the orchestrator's context, mutates `.issues/` while it is mid-iteration over that
same backlog, stalls throughput on a slow action, and tangles failures into the issue's own run.

### 4. Filtered predicates, not a global tally

`issue_events` already carries `issue_type` and `priority` columns, so `when: {type: [BUG]}`
costs one WHERE clause. "Five bugs closed → cluster them for a common root cause" is a real
workflow; "ten issues closed → run something" is a cron job with extra steps.

### Codebase Research Findings

_Verified during the design conversation (pre-`/ll:refine-issue`):_

- **`issue_events` is the correct counting substrate and is already universal.**
  `session_store/schema.py:129` defines the table; `:164-168` widens it with
  `issue_type`/`priority`/`completed_at`; `:179` adds
  `CREATE UNIQUE INDEX idx_issue_events_dedup ON issue_events(issue_id, transition)`, making
  writes idempotent. Both completion paths write it: `issue_lifecycle.py:1152` emits
  `issue.completed` on the EventBus (→ `SQLiteTransport.send()`'s `issue.*` branch), and
  `cli/issues/set_status.py:144` calls `record_issue_event()` **directly** (BUG-2770 added
  this precisely because the bus path wasn't exercised by `set-status`). So the human CLI
  path is already covered — no new emit sites needed.
- **Caveat: `set_status.py`'s `record_issue_event` call is wrapped in `except Exception: pass`
  (`:154-155`)**, and history writes are gated by `analytics.enabled`. A missed row means a
  delayed fire, not drift (because the count is derived) — but `ll-cadence status` should
  report when the history DB is unavailable rather than silently reporting a count of zero.
- **A path-scoped, cross-process, stale-cleaning lock already exists**:
  `fsm/concurrency.py:124 LockManager` with `acquire(loop_name, scope, instance_id, *, singleton)`,
  `find_conflict(scope, ...)`, `wait_for_scope(scope, timeout, ...)`, `list_locks()`, and
  `_paths_overlap()` path-prefix comparison. Lock files live in `.loops/.running/<id>.lock` as
  `ScopeLock` JSON (`loop_name`/`scope`/`pid`/`started_at`/`singleton`); dead-PID locks are
  cleaned during `find_conflict`. A `.acquire.lock` sentinel closes the check-and-create TOCTOU
  window. `loop_name` is just a label, so cadence can acquire under e.g. `cadence:<rule_id>`
  with no changes to `LockManager`.
- **But the lock only covers FSM loop runs.** Callers are exclusively `cli/loop/run.py:362-433`
  and `cli/loop/_helpers.py:1535-1544`. **`ll-auto` and `ll-parallel` never acquire a scope
  lock**, so they are invisible to `find_conflict()`. This is the real gap behind the
  contention question: a cadence action declaring `scope: [".issues/"]` will correctly wait
  behind a scope-locked `ll-loop run`, but will happily collide with a live `ll-auto` run.
  Making the Python orchestrators acquire a scope lock is a prerequisite (see Implementation
  Steps 5) — and is independently valuable beyond cadence.
- **`run_action()` (`runner_spec.py:314`) + `RunnerType` (`:50`, `SKILL`/`CMD`/`MCP`/`PROMPT`/
  `DSL`/`LOOP`) is the dispatch layer to reuse.** Note its contract refuses `RunnerType.LOOP`
  — `cli/queue.py` works around this by shelling out to `ll-loop run` per entry. Cadence's
  `loop` runner needs the same treatment; both should ideally share one helper rather than
  duplicating the workaround.
- **`EventBus.register()` supports glob filters** (`events.py:81`, e.g. `"issue.*"`), so an
  in-process observer is available where a bus exists — but it must be treated as an
  optimization, not the source of truth, since `ll-issues set-status` has no bus.
- **`file_utils.py:60 acquire_lock()`** (flock-based, polled, context-managed) is the
  in-process/file-level lock convention if cadence needs to serialize its own ledger writes.

## Implementation Steps

1. `scripts/little_loops/cadence.py` — `CadenceRule`/`CadenceAction`/`PendingAction`
   dataclasses, config parsing, and `evaluate_rules()` (pure: takes counts + last-fire state,
   returns rules to fire). No I/O, so it is trivially unit-testable.
2. `session_store` migration: `cadence_fires` + `cadence_pending` tables, registered in
   `_KIND_TABLE` (or explicitly kindless) so `ll-verify-kinds` passes.
3. `scripts/little_loops/cli/cadence.py` — `ll-cadence` with `status` / `check [--dry-run]` /
   `run` / `fire <id> --now`; register the entry point in `scripts/pyproject.toml`, and add it
   to `skills/configure/areas.md`'s "All ll- commands" preset and `writers._LL_PERMISSIONS`
   so `ll-verify-cli-allowlist` passes (BUG-2764).
4. Config schema: add the `cadence` block to `scripts/little_loops/config-schema.json`.
5. **Prerequisite for scope safety** — make `ll-auto` and `ll-parallel` acquire a
   `LockManager` scope lock for the duration of a run (they currently do not, see findings).
   Cadence's `wait_for_scope()` is meaningless against those orchestrators until this lands.
6. Dispatch sinks: `notify` (default), `queue` (`ll-queue add` shell-out, feature-detected —
   never a hard dependency), `inline` (`run_action()`, opt-in). Per-rule circuit breaker
   disabling a rule after K consecutive failed fires.
7. SessionStart hook surfacing of pending cadence actions, following the `deferred-triage`
   visibility idiom.
8. Tests in `scripts/tests/test_cadence.py` — predicate math (see Design Traps), catch-up
   coalescing, idempotent double-evaluation, `when` filtering, dispatch-mode routing.

## Design Traps (must be covered by tests)

- **Modulo is wrong.** `count % N == 0` breaks the first time two completions land together
  under `ll-parallel`. The predicate must be `count_since_last_fire >= N`.
- **Backfill stampede.** `ll-session backfill` on a repo with 400 historical issues would make
  an `every: 10` rule want to fire 40 times. `catch_up: "coalesce"` (fire once regardless of
  how many thresholds were crossed) must be the default; `"all"` is opt-in.
- **Decomposition double-counts.** An EPIC parent closes via `finalize-decomposition` when its
  children are *enqueued* — that is one `done` that is not delivered work, and each child will
  count again later.
- **`cancelled` vs `done`.** Dedup/prioritize actions care about backlog churn, not delivery.
  Make the counted transition set configurable, defaulting to `["done"]`.
- **Worktree path resolution.** A completion inside an `ll-parallel` worktree must resolve
  `.ll/history.db` and any dispatch target to the **main repo**, not the worktree copy, or
  fires vanish with the worktree.
- **Token furnace.** Every rule needs a destination for its output or nobody reads it. Rules
  should be either idempotent-side-effecting (`normalize --auto`, `backfill`) or produce a
  durable artifact (digest file, filed issues). Per-rule spend ceiling + circuit breaker.

## Use Case

A user sets `backlog-hygiene` at `every: 10`. After their tenth issue completes, `ll-cadence
status` (and the next session's SessionStart output) reports two pending actions. They run
`ll-cadence run`; `ll-issues normalize --auto` fixes three malformed IDs and
`/ll:audit-issue-conflicts` files one conflict issue. No manual bookkeeping, no cron, and
nothing ran unattended inside an orchestrator's context window.

## Program Design

### Types

- `CadenceAction: dataclass` — `runner: RunnerType`, `target: str`, `timeout: int | None`
- `CadenceRule: dataclass` — `id: str`, `every: int`, `when: dict[str, list[str]] | None`,
  `actions: list[CadenceAction]`, `scope: list[str]`, `dispatch: str`, `enabled: bool`
- `FireDecision: dataclass` — `rule_id: str`, `at_count: int`, `times: int` (post-coalesce)
- `PendingAction: dataclass` — `rule_id: str`, `action: CadenceAction`, `queued_at: str`

### Signatures

- `load_rules(config: BRConfig) -> list[CadenceRule]`
- `count_since(db: Path, since_ts: str | None, when: dict | None, transitions: list[str]) -> int`
- `evaluate_rules(rules, counts: dict[str, int], catch_up: str) -> list[FireDecision]` — pure
- `record_fire(db: Path, decision: FireDecision) -> None`
- `dispatch(rule: CadenceRule, mode: str) -> list[RunnerResult]`

### Call Path

- `main_cadence()` -> `load_rules()` -> `count_since()` -> `evaluate_rules()` -> `record_fire()` -> `dispatch()`
- `dispatch()` -> `LockManager.wait_for_scope()` (existing, `fsm/concurrency.py:321`) -> `run_action()` (existing, `runner_spec.py:314`)

## Impact

- **Priority**: P4 — still wanted, but not a current priority; closes a real
  recurring-maintenance gap and all four substrates already exist, so the net-new surface is
  a predicate plus a ledger
- **Effort**: Medium — small core, but step 5 (orchestrator scope locks) touches `ll-auto`/`ll-parallel`
- **Risk**: Medium — the failure mode is unattended token spend or a cadence action colliding
  with a live orchestrator; mitigated by `notify`-by-default dispatch, scope locks, and the
  circuit breaker

## Status

**Deferred** | Created: 2026-08-01 | Priority: P4

## Acceptance Criteria

- [ ] `cadence.rules` config validates against `config-schema.json`
- [ ] Fire predicate is `count_since_last_fire >= every`, derived from `issue_events` — no counter file
- [ ] Repeated `ll-cadence check` calls after a single threshold crossing fire exactly once
- [ ] `catch_up: "coalesce"` (default) fires once when N thresholds are crossed at once; `"all"` fires N times
- [ ] `when: {type: [BUG]}` counts only matching completions
- [ ] Default `dispatch: "notify"` executes nothing; pending actions are visible via `ll-cadence status`
- [ ] Cadence never runs an action inline inside an `ll-auto`/`ll-parallel`/`ll-loop` run
- [ ] A cadence action declaring a `scope` waits behind a conflicting `LockManager` holder
- [ ] `ll-auto` and `ll-parallel` acquire a scope lock for the duration of a run
- [ ] Absent/disabled history DB is reported as unavailable, not as a count of zero
- [ ] `ll-cadence` passes `ll-verify-cli-allowlist`; new tables pass `ll-verify-kinds`
- [ ] pytest coverage in `scripts/tests/test_cadence.py`
