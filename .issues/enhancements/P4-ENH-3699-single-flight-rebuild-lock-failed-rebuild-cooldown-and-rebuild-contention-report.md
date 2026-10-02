---
id: ENH-3699
type: ENH
title: Single-flight rebuild lock, failed-rebuild cooldown, and rebuild contention
  report
priority: P4
status: deferred
discovered_by: ll-issues-create
discovered_date: '2026-10-02'
captured_at: '2026-10-02T17:56:06Z'
blocked_by:
- ENH-3678
- ENH-3698
blocks:
- ENH-3666
relates_to:
- ENH-3678
- ENH-3698
deferred_by: human
deferred_date: '2026-10-02T17:59:01Z'
---

# ENH-3699: Single-flight rebuild lock, failed-rebuild cooldown, and rebuild contention report

## Summary

Slice 3678c (split from ENH-3678, 2026-10-02). Add a single-flight `fcntl.flock` around `--rebuild` so concurrent workers perform one replay, a failed-rebuild cooldown so a persistently failing rebuild is not retried on every session start, and a contention report for a direct `ll-session rebuild`. **Deferred and spike-gated:** with derive gating (ENH-3678) and the size gate (ENH-3698) auto-rebuilds become rare, so urgency is low. Run `/ll:spike` on the lock protocol and record the outcome here before implementing.

## Current Behavior

There is no single-flight guard: every SessionStart during a multi-minute rebuild spawns another `--rebuild`. `rebuild()` runs its whole wipe-and-replay in one `BEGIN IMMEDIATE` transaction, so a concurrent worker's incremental ingest cannot write until it commits (it hits the 5000 ms busy timeout and fails), and the local ingest watermark is one global wall-clock `last_raw_event_ts`, so an early-exiting worker can lose its transcript. No rebuild cooldown exists. `ll-session rebuild` has no contention handling.

## Expected Behavior

- **Lock file.** A dedicated `<db>.rebuild.lock`. Do **not** reuse `<db>.usage-refresh.lock`: Stop workers take it with blocking `LOCK_EX` and store throttle state in it. The `.lock` suffix is already gitignored (`.ll/*.lock` in `init/writers.py:_GITIGNORE_ENTRIES` for consuming projects and in this repo's `.gitignore`); `.ll/history.db*` covers the DB-adjacent names too. `usage_stop.py`'s `--usage-trigger` already rejects `--rebuild`; keep that and do not share the rebuild lock with it.
- **Lock protocol (unproven; spike required).** Ingest polls `LOCK_SH | LOCK_NB` up to a bounded wait. On timeout, a durable deferred-transcript identity or a proven watermark-safe retry protocol must preserve the work: merely leaving the source file for a later scan is insufficient because another worker can advance global `last_raw_event_ts` past it. The spike chooses and records the recovery mechanism before implementation. Avoid accumulating one blocked detached worker per hook. Replay takes `LOCK_EX`, re-checks `rebuild_needed()` and skips if another worker completed it. Direct `ll-session rebuild` uses non-blocking exclusive acquisition and reports contention.
- **Failed-rebuild cooldown.** Record the last failed attempt and skip auto-spawn for a cooldown. Keep the state in a **sidecar next to the rebuild lock** (the lock file's own contents, or a `.lock`-suffixed sibling such as `<db>.rebuild-state.lock`; a bare `.rebuild-state.json` would match no ignore rule in this repo), **not in `meta`**: `rebuild()` is one `BEGIN IMMEDIATE` transaction that rolls back on failure, so a `meta` write from the failing worker is a second contended write on a store that is already the problem. Follow the `UNREACHABLE_TTL_S` / `_now()` clock-seam precedent (`session_store/remote_telemetry.py:38`, use at `:130`).
- **Remote stores** never rebuild from a hook: the refusal in `backfill_worker.main` (`except HistoryUnsupported`) and `session_start.handle` must happen **before** the lock file is opened or created.

## Motivation

Without single-flight, overlapping SessionStart hooks can run duplicate multi-minute rebuilds and drop telemetry. With ENH-3678/ENH-3698 in place this only matters when a rebuild is slow *and* a second worker starts during it, so it is deferred until measured need or until ENH-3666 is reactivated.

## Open Questions

- **The lock protocol is unproven. Tracked task: run `/ll:spike` (or a test that holds a real replay open while a second worker ingests); do not start implementation until the outcome is recorded here.** Confirm: the second worker's ingest completes after the replay commits; the re-check skips a second replay; the watermark advances only on commit. Also confirm the premise that a hook worker usually carries a single transcript (so exiting early would lose it).
- **Lock placement (decide explicitly).** `rebuild()` is reached by the worker, by `backfill(also_rebuild=True)` (~`lifecycle.py:1744`), `backfill_incremental(also_rebuild=True)` (~`:1680`) and `ll-session backfill --rebuild` / `refresh --rebuild` (`cli/session.py` ~`:819`, `:883`, `:959`, `:982`, `:995`). A lock placed *inside* `rebuild()` covers all of them; one placed only in `backfill_worker.main` or the `rebuild` CLI arm does not.
- **Primitive.** No `LOCK_SH` use exists anywhere in `scripts/little_loops`; `file_utils.acquire_lock` (`:122`) is exclusive-only (polled `LOCK_EX|LOCK_NB`, callers `hooks/drift_check.py`, `hooks/pre_compact.py`). Bounded `LOCK_SH` is new primitive code; decide extending `acquire_lock` vs a new helper. Darwin flock contention semantics: `test_file_utils.py` (~`:183-240`) and `.ll/learning-tests/fcntl.md`.
- **Required timeout recovery experiment:** hold replay A open; let transcript B's ingest wait expire; ingest newer transcript C and commit a watermark newer than B; release A and retry B in a fresh process. B must be ingested exactly once even if its mtime is older than the watermark. Repeat across worker crash/restart and duplicate retries. Record how deferred work survives, how it is drained, and how worker accumulation remains bounded. A happy-path waiter that succeeds before its timeout does not prove this property.

## Scope Boundaries

- **In scope**: the flock protocol, cooldown sidecar, `ll-session rebuild` contention report, and their tests/docs.
- **Out of scope**: `REBUILD_DERIVE_VERSION`/`rebuild_needed` (ENH-3678), size gate/notice/doctor (ENH-3698), restructuring `rebuild()` (ENH-3666, which this blocks), telemetry-writer resilience (ENH-3679).

## Integration Map

### Files to Modify

- `scripts/little_loops/cli/backfill_worker.py` — separate incremental ingest from the replay lock so a contending `--rebuild` worker does not discard its transcript. `main` has no argparse (ad hoc `"--rebuild" in args` + `skip_next` loop, ~`:120-206`), so any new flag is hand-added. Existing blocking-`LOCK_EX` + JSON throttle idiom at `:48` (`_run_usage_trigger`).
- `scripts/little_loops/session_store/lifecycle.py` — lock/re-check wrapper per the placement decision; update the `rebuild()` docstring.
- `scripts/little_loops/cli/session.py` — `main_session`, `command == "rebuild"` arm (`rebuild(args.db, config=config)`, ~`:1016`) is where the contention report attaches; it has no `HistoryError` handler on this arm today (only `_main_migrate` and `refresh` catch it), so a contention path needs a new exit/return shape. Also `rebuild_parser` help/epilog (`_build_parser`, ~`:270`) and the `refresh` hint (~`:840`) if wording changes.
- `scripts/little_loops/file_utils.py` — only if `acquire_lock` is extended for shared mode.
- `scripts/little_loops/session_store/usage_refresh.py` — docstring (`:109`, "a failed rebuild must be retried explicitly") must stay consistent with the cooldown semantics; it never touches the rebuild lock.

### Tests

- Existing to keep green: `test_remote_hooks.py::TestBackfillWorker::test_a_rebuild_is_refused_with_a_message_and_no_traceback` (remote refusal before the lock file exists); `test_remote_hooks.py::TestSessionStart::test_does_not_migrate_a_remote_store_on_start` (no `begin immediate` reaches the stub); `test_remote_operation_matrix.py::TestRejectedOperations` (`rebuild()` raises `HistoryUnsupported(operation="rebuild")`); `test_enh_3166_qwen_normalizer.py::TestBackfillWorkerHost::test_flags_are_position_insensitive` (real `--rebuild` argv over a real DB, `sessions == 1`); `test_backfill_worker_usage_trigger.py::test_cli_requires_explicit_supported_trigger` (`--usage-trigger` + `--rebuild` returns 1); `test_enh3184_spawn_site_guard.py`.
- `test_ll_session.py::TestRebuildSubcommand` (`:1204`; `test_rebuild_parsed_from_argv`, `test_rebuild_invokes_session_store_rebuild`, `test_rebuild_json_flag`) patch `little_loops.cli.session.rebuild` with a plain counts dict; a contention path with a different call shape needs these updated.
- New: bounded `LOCK_SH` ingest vs `LOCK_EX` replay using same-process threads (Darwin separate `open()`s contend) with `Event`/`Barrier` as in `test_file_utils.py::test_timeout_raises_when_held` and `test_exclusive_acquisition_one_wins`; two concurrent `--rebuild` workers perform exactly one replay and each transcript is ingested; cooldown sidecar via a `_Clock` (as in `test_backfill_worker_usage_trigger.py`) asserting the sidecar contents; a `--rebuild` argv test through `backfill_worker.main`; `ll-session rebuild` contention report with the lock held; failed-rebuild leaves `rebuild_derive_version` unstamped. No `LOCK_SH` test exists today.
- The hook → `backfill_worker --rebuild` → `rebuild()` chain is only tested in pieces; a replay-duration measurement on a real DB belongs in the spike/PR, not a unit test.

### Documentation (end-user shape)

- `docs/reference/CLI.md` — `ll-session rebuild` table row (~`:4397`) and flags block (~`:4514`) for the contention report; `docs/guides/HISTORY_SESSION_GUIDE.md` rebuild callout (~`:190-204`), `--json` note (~`:226`).

## Program Design

### Types

- Lock file `<db>.rebuild.lock` (flock; shared for ingest, exclusive for replay) and a `.lock`-suffixed cooldown sidecar with a module-level TTL constant and `_now()` seam.

### Signatures

- Indicative; final shapes are chosen after the spike.
- `acquire_rebuild_lock(db: Path | str, *, shared: bool, timeout_s: float = 0.0) -> RebuildLock | None` — `shared=True` polls `LOCK_SH|LOCK_NB` up to `timeout_s`; `shared=False` is a non-blocking `LOCK_EX`; `None` means contention (never raises into the caller).
- `record_rebuild_failure(db: Path | str) -> None` and `rebuild_cooldown_active(db: Path | str) -> bool` — cooldown sidecar read/write, never touching `meta`.

### Call Path

- `handle` (`little_loops.hooks.session_start`) → `rebuild_needed` (ENH-3678) → size gate (ENH-3698) → detached `little_loops.cli.backfill_worker --rebuild` → bounded shared lock → incremental ingest → exclusive lock → re-check `rebuild_needed()` → `rebuild()` (or a named pending/contended outcome).

## Implementation Steps

1. Run `/ll:spike` on the protocol; record the outcome in Open Questions. Do not proceed otherwise.
2. Decide lock placement and the shared-lock primitive; implement the remote-refusal-before-lock ordering.
3. Implement bounded ingest/replay locks and the re-check; implement the cooldown sidecar; implement the `ll-session rebuild` contention report with its exit shape.
4. Tests and docs per above; run `python -m pytest scripts/tests/`, `ruff check scripts/`, `python -m mypy scripts/little_loops/`.

## Impact

- **Priority**: P4 - deferred; rebuilds become rare once ENH-3678 and ENH-3698 land
- **Effort**: Medium - new lock primitive, protocol across `backfill_worker.py`/`lifecycle.py` with shared watermark state, and tests built from scratch
- **Risk**: Medium - an unproven lock protocol; a wrong ingest/replay interleaving can lose a transcript
- **Breaking Change**: No

**Interim risk accepted until this lands:** stores under the ENH-3698 size threshold can still see duplicate concurrent `--rebuild` workers. That is acceptable only if those replays are short, which is unmeasured; record a replay-duration measurement on a sub-1 GiB store in the ENH-3698 PR.

## Acceptance Criteria

- [ ] The lock-protocol open question is resolved by a spike or test **before implementation starts**, and the outcome is recorded here.
- [ ] The spike proves timed-out transcript B is recovered after newer transcript C advances the global watermark, including process restart and duplicate retry. The chosen durable retry/watermark protocol is recorded; leaving a file without a recoverable identity is not accepted evidence.
- [ ] Two concurrent `--rebuild` workers perform exactly one replay (the second re-checks `rebuild_needed()` under the exclusive lock and skips); each worker's transcript is ingested. Ingest workers use a bounded `LOCK_SH` wait (no unbounded pile-up of blocked workers).
- [ ] A direct `ll-session rebuild` reports contention rather than silently claiming success, with an explicit exit shape.
- [ ] A failed rebuild is not retried until its cooldown expires; the state lives in a `.lock`-suffixed sidecar, not `meta`.
- [ ] Stop usage-refresh workers keep using their existing lock without sharing the rebuild lock file; remote stores are refused before the lock file is created.
- [ ] Docs updated in end-user shape; `python -m pytest scripts/tests/` passes.

## Related

- ENH-3678 (blocked_by; gate and `rebuild_needed`), ENH-3698 (size gate), ENH-3666 (blocked by this issue), ENH-3679.

## Status

**Deferred** | Created: 2026-10-02 | Priority: P4 | Spike-gated
