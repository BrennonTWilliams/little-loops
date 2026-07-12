---
id: EPIC-2616
type: EPIC
priority: P2
status: open
captured_at: 2026-07-12T19:49:49Z
discovered_date: 2026-07-12
discovered_by: scope-epic
relates_to: []
---

# ll-loop queue management CLI (list / remove)

## Summary

Add an `ll-loop queue` subcommand family (`list`, `remove`) so operators and
future tooling can inspect and cancel entries in the process-backed FSM run
queue without hand-editing files or killing PIDs manually.

## Motivation

`ll-loop run --queue` already lets a caller wait for a scope lock, but the
queue itself has no management surface. `list`/`remove` are the only
genuinely new CLI design work identified in
`thoughts/2026-07-12 HTMX FSM Dashboard — Event Bus Capability Assessment.md`
and are a hard prerequisite for the later dashboard bridge phases described
in that document (queue *show*/*add* already work today via the raw queue
files and `--queue`; *remove* has no primitive). This EPIC is scoped to the
CLI only — no HTTP bridge, no HTMX dashboard.

## Goal

Ship `ll-loop queue list` and `ll-loop queue remove <id>` as first-class,
tested CLI subcommands that operate safely against the live, process-backed
queue directory (`.loops/.queue/*.json`).

## Scope

**In scope:**
- Shared helper for reading/pruning `.loops/.queue/*.json` entries (dead-PID
  detection already exists inline in `_is_earliest_waiter()` in
  `cli/loop/_helpers.py` — extract/reuse rather than reimplement).
- `ll-loop queue list` — show pending queue entries (id, loop name, PID,
  liveness, enqueued time), `--json` output.
- `ll-loop queue remove <id>` — safely terminate the waiting process and
  delete its queue entry file.
- Docs for the new subcommand family.

**Explicitly out of scope (deferred):**
- `ll-loop queue reorder` — no priority field exists on queue entries today;
  ordering is strict `enqueuedAt` FIFO, and rewriting timestamps under live
  pollers is a race. Needs its own design pass — not part of this EPIC.
- The HTTP bridge / HTMX dashboard (`dashboard.py`, SSE relay, FSM diagram
  rendering) — later phases of the same effort, tracked separately once this
  EPIC ships.

## Children

- **ENH-2617** — Shared queue entry read/prune helper
- **FEAT-2618** — `ll-loop queue list` subcommand
- **FEAT-2619** — `ll-loop queue remove <id>` subcommand
- **ENH-2620** — Document `ll-loop queue` subcommand family

## Success Metrics

- `ll-loop queue list` and `ll-loop queue remove <id>` exist, are documented
  in `docs/reference/API.md`, and are covered by `scripts/tests/`.
- `ll-loop queue remove <id>` reliably terminates the waiting process (no
  orphaned PID) and removes the queue entry file, verified against a live
  `--queue` waiter in a test.
- `python -m pytest scripts/tests/` passes with the new subcommands covered.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/_helpers.py` — extract queue-entry
  read/prune helper for reuse across `list`/`remove`/`_is_earliest_waiter`.
- `scripts/little_loops/cli/loop/` — new `queue` subcommand module wired
  into the `ll-loop` argparse subparser tree.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/run.py` — existing `--queue` write path;
  must stay compatible with any queue-entry schema/helper changes.

### Tests
- `scripts/tests/` — new tests for `queue list` / `queue remove`, including
  a live-waiter dead-PID pruning case.

### Documentation
- `docs/reference/API.md` — new `ll-loop queue` subcommand entries.
- `.claude/CLAUDE.md` — add `queue` to the `ll-loop` CLI Tools bullet.

## Impact

**Priority**: P2 — no user-facing urgency, but blocks the dashboard phases
of the HTMX FSM Dashboard effort from starting.
**Effort**: Small-to-medium — helper extraction plus two subcommands, all
pure CLI/stdlib (no new dependencies).
**Risk**: Low. `remove` sends a signal to a live process, so it needs care
(never SIGKILL a process that isn't actually the tracked waiter — verify PID
identity, not just liveness, before terminating).

## Labels

`fsm`, `cli`, `loops`

## Status

open

## Session Log
- `/ll:scope-epic` - 2026-07-12T19:49:49Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8999ce06-5d43-4dd5-bc03-841f57c28bf2.jsonl`
