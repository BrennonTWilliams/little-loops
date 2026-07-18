---
id: FEAT-2684
title: ll-loop run --queue compat shim and ll-loop queue migration
type: FEAT
priority: P2
status: open
captured_at: '2026-07-18T00:00:00Z'
discovered_date: 2026-07-18
discovered_by: issue-size-review
parent: EPIC-2670
depends_on:
- FEAT-2682
relates_to:
- FEAT-2669
- FEAT-2682
- ENH-2620
labels:
- queue
- cli
- scheduling
- compat
---

# FEAT-2684: `ll-loop run --queue` compat shim and `ll-loop queue` migration

## Summary

Preserve `ll-loop run --queue`'s existing lock-conflict/liveness-marker
behavior as a compatibility shim while the new `ll-queue` persistence
(FEAT-2682) becomes the home for non-FSM `ActionSpec` work. Migrate or
retire `read_queue_entries()` (`cli/loop/_helpers.py:172-200`) and
`ll-loop queue list`/`remove` per FEAT-2669's resolved Q2, without
regressing the recently-shipped FEAT-2618/FEAT-2619/ENH-2617 surface or
the BUG-1281 FIFO fix.

## Parent Issue

Decomposed from FEAT-2669: Generic `ll-queue` (heterogeneous work-item
queue). FEAT-2669's Q2 resolution ("preserve as a compatibility shim")
and its Integration Map's `cli/loop/run.py`, `cli/loop/queue.py`,
`cli/loop/__init__.py:884-919`, and `cli/loop/_helpers.py` targets are
scoped to this child.

## Motivation

`ll-loop run --queue`'s marker-write/retry-loop behavior
(`cli/loop/run.py:355-427`) is load-bearing for FSM lock contention and
recently got dedicated `list`/`remove` UX
(FEAT-2618/FEAT-2619/ENH-2617), tested in `test_cli_loop_queue.py` and
fixing BUG-1281's FIFO ordering. Breaking that format regresses shipped
work with no user-facing benefit — but leaving it fully disconnected
from the new `ll-queue` (FEAT-2682) would mean two divergent "queue"
concepts with no documented relationship.

## Expected Behavior

- `ll-loop run --queue`'s marker-write/retry-loop behavior for FSM lock
  contention is preserved unchanged — this child does not touch
  `PersistentExecutor`'s locking semantics.
- `ll-loop queue list`/`remove` continue to operate on
  `.loops/.queue/*.json` liveness markers via `read_queue_entries()` —
  additive, not replaced, by FEAT-2682's persistence (which is for
  non-FSM `ActionSpec` work only, per FEAT-2669's Decision Rationale).
- Document the relationship between the two queue surfaces (FSM
  lock-contention markers vs. general-purpose `ll-queue` entries) so
  users and future issues don't conflate them.
- Resolve whether ENH-2620 (document `ll-loop queue` subcommands) is
  superseded or complementary, and update/close it accordingly.

## Acceptance Criteria

- `ll-loop run --queue` behavior is unchanged and existing
  `test_cli_loop_queue.py` coverage (including the BUG-1281 FIFO
  regression test) still passes.
- `ll-loop queue list`/`remove` continue to function against
  `.loops/.queue/*.json` markers with no behavior change.
- Docs (`docs/reference/API.md` and/or CLI docs) clarify the
  relationship between `ll-loop queue` (FSM lock-contention markers) and
  `ll-queue` (FEAT-2682's general-purpose persisted entries).
- ENH-2620 is explicitly resolved (closed as superseded, or updated to
  reflect the final compat decision).
- `python -m pytest scripts/tests/` exits 0.

## Scope Boundaries

- **In**: compat verification for `ll-loop run --queue` and `ll-loop
  queue list`/`remove`, cross-linking docs between the two queue
  surfaces, resolving ENH-2620.
- **Out**: the new `ll-queue` persistence/commands (FEAT-2682) and
  worker (FEAT-2683) themselves — this child only ensures they coexist
  cleanly with the pre-existing FSM queue surface.

## Related Key Documentation

| Document | Why Relevant |
|----------|--------------|
| FEAT-2669 | Parent issue — full design context, Q2 resolution |
| FEAT-2682 | The new persistence surface this child must coexist with |
| ENH-2620 | Existing `ll-loop queue` docs issue — resolve/close here |

## Session Log
- `/ll:issue-size-review` - 2026-07-18T00:00:00Z - `000582b3-d456-48ac-97b3-fcefbd8047d4.jsonl`

---

## Status

**Open** | Created: 2026-07-18 | Priority: P2
