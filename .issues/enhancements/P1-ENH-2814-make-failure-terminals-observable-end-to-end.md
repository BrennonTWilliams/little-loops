---
id: ENH-2814
type: ENH
priority: P1
status: open
captured_at: '2026-07-25T22:08:07Z'
discovered_date: 2026-07-25
discovered_by: capture-issue
labels: [fsm, loops, persistence, cli, exit-codes]
relates_to: [BUG-2813]
---

# ENH-2814: Make FSM failure terminals observable end-to-end (exit code, persistence, history)

## Summary

A loop that lands on a `failed` terminal exits **0** and is persisted as
`final_status: "completed"`. The `done`-vs-`failed` distinction is a pure naming
convention with no schema backing, honored by some consumers and ignored by
others — including the persistence layer that feeds `.loops/runs` archives and
the session store. Audit §1.2 /
`thoughts/builtin-loops-audit-2026-07-24.md`.

## Motivation

Every external consumer — shell scripts, cron wrappers, the local test gate,
`ll-queue run` — sees exit 0 when a loop fails. Run archives and
`loop_runs` history record failures as successes, corrupting any downstream
analysis of loop health. Production code already carries a workaround for this
footgun (`parallel/worker_pool.py`), which is the clearest evidence the current
design is wrong.

## Current Behavior

`cli/loop/_helpers.py:64-77` maps `terminated_by` → exit code; `"terminal": 0`
for *any* terminal state (applied at `:1905`). `ExecutionResult` records only
`terminated_by="terminal"` (`fsm/types.py:24`); there is no schema-level failure
flag (`StateConfig.terminal` is a plain bool).

Consumer split:

- **Sub-loop routing honors it**: `fsm/executor.py:1012-1018` (child ends on
  `done` → `on_yes`, any other terminal → `on_no`).
- **CLI display color honors it**: `cli/loop/_helpers.py:1829-1836`.
- **History queries re-derive it in SQL**: `history_reader.py:982-990`
  (`terminated_by = 'terminal' AND final_state != 'done'` → failed).
- **Persistence does NOT**: `fsm/persistence.py:891` and `:943` stamp
  `final_status = "completed" if terminated_by == "terminal" else "failed"` — a
  run that lands on `failed` is persisted as `"completed"` into `.loops/runs`
  archives and the session store's `loop_runs` table.
- **`parallel/worker_pool.py:120-133`** carries a written acknowledgment: *"All
  terminal states (done, blocked, impl_failed) exit 0 — distinguish blocked from
  done by reading the state file left after execution"* — a state-file workaround.
- **`ll-queue run`** (`cli/queue.py:246-257`) judges success purely by exit code
  for the kinds it dispatches; loops stay on `PersistentExecutor` and inherit
  persistence's blind `"completed"`.

## Expected Behavior

- A loop ending on a non-`done` terminal exits with a distinct, documented exit
  code.
- `fsm/persistence.py` stamps `final_status: "failed"` for those runs, so
  archives and the session store are truthful.
- Sub-loop routing keys off the same explicit signal rather than re-deriving it
  from the state name.
- `parallel/worker_pool.py`'s state-file workaround can be deleted.

## Proposed Solution

Two viable approaches — prefer (B):

**(A) Name-based:** map non-`done` terminals to a distinct exit code (e.g. 2) in
`EXIT_CODES`, and apply the same name check in `persistence.py`. Cheap, but keeps
the convention implicit and leaves `history_reader`'s SQL duplication.

**(B) Schema flag (recommended):** add an explicit `failure: true` flag to
`StateConfig` and key exit code, sub-loop routing, and `persistence.py`'s
`final_status` off it. Default it from the existing name convention so no loop
YAML must change on day one, then migrate loops to declare it explicitly (pairs
with the audit §2.2 / rec #8 `failed`-terminal sweep, not yet captured).
Collapses three independent re-derivations into one source of truth.

The §1.2 consumer sites are fully enumerated above, so the migration surface is
known.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/_helpers.py` (`EXIT_CODES`, `:64-77`, apply site `:1905`)
- `scripts/little_loops/fsm/persistence.py` (`:891`, `:943`)
- `scripts/little_loops/fsm/schema.py` (`StateConfig` — `failure` flag, approach B)
- `scripts/little_loops/fsm/types.py` (`ExecutionResult`)
- `scripts/little_loops/fsm/executor.py:1012-1018` (sub-loop routing)
- `scripts/little_loops/parallel/worker_pool.py:120-133` (retire workaround)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/history_reader.py:982-990` (SQL re-derivation — simplify)
- `scripts/little_loops/cli/queue.py:246-257`
- `scripts/little_loops/cli/loop/_helpers.py:1829-1836` (display color)

### Similar Patterns
- Existing `EXIT_CODES` entries (`max_steps: 1`) as the precedent for a nonzero mapping

### Tests
- `scripts/tests/test_builtin_loops.py`, FSM executor/persistence tests
- New: a loop landing on `failed` exits nonzero and persists `final_status: "failed"`

### Documentation
- `docs/reference/CLI.md` (`ll-loop run` exit codes)
- `docs/generalized-fsm-loop.md` (schema flag, if B)
- `docs/ARCHITECTURE.md` § Orchestration Layers (worker_pool workaround removal)

### Configuration
- N/A

## Implementation Steps

1. Add the `failure` flag to the schema, defaulted from the name convention.
2. Key `EXIT_CODES`, sub-loop routing, and `persistence.py`'s `final_status` off it.
3. Simplify `history_reader.py`'s SQL to read the persisted status.
4. Delete `worker_pool.py`'s state-file workaround.
5. Audit callers that assume exit-0-means-success for loops (`ll-queue run`, docs, wrappers).
6. Document the new exit code.

## Impact

- **Severity**: High — silent failure across every automation surface.
- Sequenced **before** the audit §2.2 / rec #8 sweep (adding `failed` terminals
  is pointless while they are unobservable), and complements BUG-2813 (dead
  terminal actions).
- Behavior change: scripts currently treating any loop exit as success will begin
  seeing nonzero — intended, but call it out in the changelog.

## Related Key Documentation

| Document | Relevance |
|---|---|
| `thoughts/builtin-loops-audit-2026-07-24.md` §1.2, rec #3 | Source finding, full consumer-site enumeration |
| `docs/ARCHITECTURE.md` § Orchestration Layers | worker_pool context |

## Scope Boundaries

**In scope:**
- Exit-code mapping for non-`done` terminals (`cli/loop/_helpers.py` `EXIT_CODES`).
- `fsm/persistence.py`'s `final_status` stamp (`:891`, `:943`).
- The `failure: true` schema flag and its defaulting from the name convention.
- Sub-loop routing (`executor.py:1012-1018`) and `history_reader.py:982-990`
  keying off the single source of truth.
- Retiring `parallel/worker_pool.py:120-133`'s state-file workaround.

**Out of scope:**
- Adding `failed` terminals to the ~41 loops that lack one (audit §2.2 /
  rec #8) — sequenced *after* this issue.
- Moving dead terminal actions into penultimate states (BUG-2813).
- Backfilling or correcting historical `loop_runs` rows already persisted as
  `"completed"`; this issue fixes forward only.
- Any change to `max_steps` / `error` exit-code semantics, which already work.

## Session Log
- `/ll:audit-issue-conflicts` - 2026-07-26T00:54:34 - `1286c2b1-65d4-4230-b501-25c3ae70b53c.jsonl`
- `/ll:capture-issue` - 2026-07-25T22:08:07Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8a36a68e-d365-4ea1-9394-a9e5904b5739.jsonl`

---

## Status

- **Current**: open
