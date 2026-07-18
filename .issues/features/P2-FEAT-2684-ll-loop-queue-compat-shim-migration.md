---
id: FEAT-2684
title: ll-loop run --queue compat shim and ll-loop queue migration
type: FEAT
priority: P2
status: done
captured_at: '2026-07-18T00:00:00Z'
completed_at: '2026-07-18T22:38:23Z'
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
confidence_score: 100
outcome_confidence: 87
score_complexity: 20
score_test_coverage: 23
score_ambiguity: 22
score_change_surface: 22
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

## Integration Map

### Files to Modify

- `docs/reference/CLI.md` — two queue sections already exist in this file
  but do not cross-link each other: `##### Queue entries (.loops/.queue/)`
  (~line 668, with `#### ll-loop queue list` / `#### ll-loop queue remove
  <id>` subsections) documents the FSM marker mechanism; `### ll-queue`
  (~line 2604) documents the new persisted queue and already contains a
  one-sentence disambiguation ("distinct from `ll-loop queue`'s
  PID-liveness marker mechanism, which FEAT-2684 migrates separately").
  Add the reciprocal cross-link from the `.loops/.queue/` section back to
  `### ll-queue`, and correct the "migrates separately" wording per the
  Codebase Research Findings below (this issue does not migrate the
  marker mechanism — it preserves it as a compat shim).
- `.claude/CLAUDE.md` — the `ll-queue` CLI-tools bullet (~line 234)
  already notes it is "distinct from `ll-loop queue`'s PID-liveness
  marker mechanism" — verify this stays accurate after the CLI.md
  cross-link edit.
- `.issues/completed/P3-ENH-2620-document-ll-loop-queue-subcommands.md`
  — no code change needed; see Codebase Research Findings — ENH-2620 is
  already `status: done`, resolved via decomposition into ENH-2629/ENH-2630
  (both `done`). This issue's AC ("ENH-2620 is explicitly resolved") is
  satisfiable by referencing that existing `## Resolution` block, not by
  reopening or re-closing ENH-2620.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/queue.py` — module docstring (lines 3-6) carries
  the identical stale wording as `queue_store.py`'s docstring ("...which
  FEAT-2684 migrates separately") and needs the same correction. Previously
  listed only under "Dependent / Related Files (not to be touched)" — that
  scoping was for the CLI's behavior/code, not this docstring sentence.
- `docs/ARCHITECTURE.md` — § "Queue DB (ll-queue)" (~line 830) contains the
  same claim in different words: "FEAT-2684 migrates that compat path
  separately, using a distinct id space so the two don't collide during the
  transition." Needs the same "preserved as a separate compat surface"
  correction; the "distinct id space"/"transition" framing implies an
  in-flight migration that this issue's Expected Behavior explicitly
  disclaims.
- `docs/reference/API.md` — § `## little_loops.queue_store` (~line 8251)
  reproduces `queue_store.py`'s module docstring near-verbatim, including
  the stale "which FEAT-2684 migrates separately" sentence. Update in sync
  with the `queue_store.py` docstring fix so source and generated reference
  docs don't diverge.

### Files to Verify Unchanged (compat-shim surface — no code change expected)

- `scripts/little_loops/cli/loop/run.py` — `cmd_run()`'s `--queue`
  marker-write/retry-loop block (~lines 355-427): writes
  `<loops_dir>/.queue/<uuid>.json`, registers `atexit` cleanup, and
  retries `lock_manager.acquire()` in a budget-bounded loop gated by
  `_is_earliest_waiter()` (the BUG-1281 FIFO fix).
- `scripts/little_loops/cli/loop/_helpers.py` — `read_queue_entries()`
  (~lines 172-200, prunes dead-PID entries via `_process_alive()`,
  BUG-1360) and `_is_earliest_waiter()` (FIFO ordering, BUG-1281).
- `scripts/little_loops/cli/loop/queue.py` — `cmd_queue_list()`,
  `cmd_queue_remove()`, `_resolve_queue_entries()` (id/8+-char-prefix
  resolution), `_verify_queue_pid_identity()`.
- `scripts/little_loops/cli/loop/__init__.py` — `queue` subparser
  wiring (~lines 884-919) and dispatch on `args.queue_command` (~lines
  974-980).

### Dependent / Related Files (not to be touched by this issue)

- `scripts/little_loops/queue_store.py` — FEAT-2682's `.ll/queue.db`
  persistence layer; its module docstring currently says the marker
  mechanism "this supersedes is migrated separately by FEAT-2684" —
  language to reconcile per Codebase Research Findings below.
- `scripts/little_loops/cli/queue.py` — the new `ll-queue` CLI
  (`main_queue()`, `cmd_run()` worker); `run_action()` explicitly
  excludes `RunnerType.LOOP` from dispatch, so `.ll/queue.db` cannot
  and does not carry FSM loop work — confirms the two surfaces stay
  non-overlapping by construction.
- `scripts/little_loops/runner_spec.py` — `RunnerType`, `ActionSpec`,
  `run_action()` (the `LOOP` exclusion referenced above).
- `scripts/little_loops/fsm/concurrency.py` — `LockManager.acquire`,
  `find_conflict`, `wait_for_scope` (unchanged locking semantics this
  issue must not touch, per Scope Boundaries).

### Tests

- `scripts/tests/test_cli_loop_queue.py` — existing coverage to keep
  green unchanged: `TestQueueRetryOnRace` (BUG-1281 regression),
  `TestQueueFifoOrdering` (ENH-1332), `TestReadQueueEntries`,
  `TestQueueListCommand`, `TestQueueRemoveCommand`. No new test classes
  expected for the compat-verification AC — running this file
  unmodified is itself the verification.
- `scripts/tests/test_wiring_cli_registry.py` — `DOC_STRINGS_PRESENT`
  parametrized table (~lines 20-155) is this codebase's established
  convention for proving a doc-only change landed (each row is
  `(doc_path, expected_string, issue_id)`); the cross-link edit to
  `docs/reference/CLI.md` should add a row here rather than a new test
  file, following the existing ENH-2629/ENH-2630 rows.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_wiring_cli_registry.py` — add one new
  `DOC_STRINGS_PRESENT` row, `("docs/reference/CLI.md", "<exact cross-link
  substring>", "FEAT-2684")`, once the reciprocal cross-link text is
  written — pins the doc change the same way the ENH-2629/ENH-2630 rows
  (lines 149-154) pin theirs. No test currently asserts on the
  "migrated/migrates separately" wording (grep confirmed zero hits in
  `scripts/tests/`), so the docstring corrections need no other test
  updates and won't break `test_wiring_cli_registry.py`,
  `test_wiring_reference_docs.py`, or `test_wiring_guides_and_meta.py`.

### Documentation

- `docs/reference/CLI.md` — both queue sections (see Files to Modify).
- `.claude/CLAUDE.md` — `ll-queue` CLI bullet (see Files to Modify).

_Wiring pass added by `/ll:wire-issue`:_
- `docs/ARCHITECTURE.md` — § "Queue DB (ll-queue)" wording fix (see Files
  to Modify).
- `docs/reference/API.md` — § `little_loops.queue_store` wording fix,
  synced with the `queue_store.py` docstring correction (see Files to
  Modify).

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Wording tension to reconcile**: `queue_store.py`'s module docstring
  says the marker mechanism "this supersedes is migrated separately by
  FEAT-2684," which reads stronger ("supersedes"/"migrated") than the
  actual design decision. The recorded decision fragment
  (`.ll/decisions.d/973853f1-3b3a-4e2a-906d-55f3465eca05.json`, FEAT-2669)
  states the rule explicitly: **"compat shim for ll-loop run --queue"**,
  with **"breaking change to ll-loop run --queue"** listed under
  `alternatives_rejected`. FEAT-2684's own Expected Behavior section
  already reflects the correct ("preserve unchanged") framing — the
  `queue_store.py` docstring is the one artifact whose wording should be
  tightened (e.g. "preserved as a separate compat surface" instead of
  "migrated separately") as part of this issue's doc pass, to avoid a
  future reader concluding a migration is still pending.
  **Wiring pass update**: the same stale "FEAT-2684 migrates separately"
  claim is replicated in three more places — `scripts/little_loops/cli/queue.py`'s
  module docstring, `docs/ARCHITECTURE.md`'s "Queue DB (ll-queue)" section
  (which additionally implies "a distinct id space" and an in-progress
  "transition" — stronger than even `queue_store.py`'s wording), and
  `docs/reference/API.md`'s generated `queue_store` reference section
  (a near-verbatim reproduction of the source docstring). All four
  occurrences need the identical correction in the same pass, or the
  source docstring and its generated doc will diverge. See the added
  entries in Files to Modify and Documentation above.
- **ENH-2620 is already resolved, not open**: `status: done`, resolved
  2026-07-13 via decomposition (see its `## Resolution` section) into
  ENH-2629 (`ll-loop queue list` docs, done) and ENH-2630 (`ll-loop
  queue remove` docs, done). This issue's AC 4 ("ENH-2620 is explicitly
  resolved") can be satisfied by adding a one-line note to ENH-2620 (or
  to this issue) pointing at that existing decomposition rather than any
  further action on ENH-2620 itself.
- **Non-overlap is structural, not just documented**: `ll-queue run`'s
  worker (`cli/queue.py:cmd_run()`) dispatches every entry through
  `runner_spec.run_action()`, which explicitly excludes
  `RunnerType.LOOP` (per its own docstring/exclusion table) — an FSM
  loop entry pushed into `.ll/queue.db` would raise inside `run_action()`
  and be caught by `cmd_run()`'s `except Exception`, marking it
  `"failed"`. This means the two queue surfaces cannot silently overlap
  even if a user tried to enqueue FSM work into `ll-queue` — worth a
  one-line mention in the doc cross-link so it's not just an assumed
  invariant.
- **Cross-link precedent already exists in this codebase**: the
  `ll-compact-session` doc entry (`docs/reference/CLI.md:7472`) uses the
  identical "Distinct from X, which does Y" one-sentence pattern to
  disambiguate itself from `ll-session compact`. Follow that same
  phrasing convention for the reciprocal `.loops/.queue/` → `ll-queue`
  link.

## Session Log
- `/ll:manage-issue` - 2026-07-18T22:37:45Z - `7221e6f6-c044-4c72-9622-c6f121188002.jsonl`
- `/ll:ready-issue` - 2026-07-18T22:32:02 - `cbe48b8c-5faa-4b62-bcf9-89612ebecdc9.jsonl`
- `/ll:confidence-check` - 2026-07-18T22:30:35 - `8fb00030-3de3-4f36-a92d-280e99ea6deb.jsonl`
- `/ll:wire-issue` - 2026-07-18T22:29:23 - `d5011bec-6035-4482-a20d-ba9924c05e77.jsonl`
- `/ll:refine-issue` - 2026-07-18T22:24:28 - `bcb035ba-8b3b-4be9-a9c8-88c8510f6b0f.jsonl`
- `/ll:issue-size-review` - 2026-07-18T00:00:00Z - `000582b3-d456-48ac-97b3-fcefbd8047d4.jsonl`

---

## Resolution

- **Status**: Done
- **Completed**: 2026-07-18
- `ll-loop run --queue`'s marker-write/retry-loop and `ll-loop queue list`/`remove`
  behavior verified unchanged — no code touched in `cli/loop/run.py`,
  `cli/loop/_helpers.py`, `cli/loop/queue.py`, or `cli/loop/__init__.py`; full
  `test_cli_loop_queue.py` suite (BUG-1281 FIFO regression, `TestQueueFifoOrdering`,
  `TestReadQueueEntries`, `TestQueueListCommand`, `TestQueueRemoveCommand`) passes
  unmodified.
- Corrected the stale "FEAT-2684 migrates separately" wording (which implied an
  in-flight migration) to "preserves unchanged as a compat shim" across all four
  occurrences: `queue_store.py` and `cli/queue.py` module docstrings,
  `docs/ARCHITECTURE.md` § Queue DB, `docs/reference/API.md` §
  `little_loops.queue_store`.
- Added a reciprocal cross-link between `docs/reference/CLI.md`'s
  `##### Queue entries (.loops/.queue/)` section and its `### ll-queue` section,
  following the existing `ll-compact-session`/`ll-session compact`
  "Distinct from X" disambiguation pattern; also noted the structural (not just
  documented) non-overlap via `run_action()`'s `RunnerType.LOOP` exclusion.
  Pinned with a new `DOC_STRINGS_PRESENT` row in `test_wiring_cli_registry.py`.
- ENH-2620 confirmed already resolved (`status: done`, decomposed into
  ENH-2629/ENH-2630, both done) — added a one-line note there pointing to this
  issue's complementary cross-link work rather than reopening it.
- `.claude/CLAUDE.md`'s `ll-queue` bullet updated to match the corrected wording.

---

## Status

**Done** | Created: 2026-07-18 | Priority: P2
