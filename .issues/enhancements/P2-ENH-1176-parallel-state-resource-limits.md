---
discovered_date: "2026-04-18"
discovered_by: parallel-fsm-review
depends_on: [FEAT-1074, FEAT-1075, FEAT-1076]
status: deferred
---

# ENH-1176: Parallel State Resource Limits

## Summary

Add **runtime enforcement** of upper bounds on parallel state resource consumption: runtime checks against `max_items` (oversized-fan-out early rejection), cumulative wall-clock timer against `max_total_seconds`, soft warning thresholds for git worktree count, and a `try/finally` audit of `ParallelRunner.run()` cleanup paths. Without these, a parallel state defined over a very large items list (thousands), a pathological per-worker duration, or deep worktree nesting can degrade the host system or produce unbounded runtime.

**Scope boundary vs. FEAT-1074 (updated 2026-04-20):** the schema fields `max_items: int = 1000` and `max_total_seconds: int | None = None`, plus their basic range validation (`>= 1`) and the cross-field sanity WARN, are owned by **FEAT-1074** — pulled forward so the schema is internally consistent from v1 day one and downstream runner/dispatch issues can read the fields without a schema churn. This issue owns only the **runtime behavior** that enforces those fields.

## Current Behavior (as of FEAT-1074/1075/1076)

- `parallel.items` has no upper bound — an `items` expression resolving to 10,000 entries runs 10,000 sub-loops (albeit `max_workers` at a time)
- `timeout_seconds` is per-worker only. No cumulative cap on total fan-out duration. With `max_workers=4` and 1000 items at 60s each, worst-case wall-clock is 15,000s (4+ hours) with no error surface.
- `isolation: worktree` creates one worktree per concurrent worker (bounded by `max_workers`), but nested parallel states (now forbidden per FEAT-1074 nesting rule) or sequential parallel states in the same loop run can accumulate worktrees. Git performance degrades past roughly 100 worktrees per repo; no warning is emitted.
- No memory/file-handle cap on held subprocesses

## Expected Behavior

### Hard limits (runtime enforcement of FEAT-1074 schema fields)

The schema fields are declared in FEAT-1074 (`max_items: int = 1000`, `max_total_seconds: int | None = None`) with basic range validation and a cross-field sanity WARN. This issue adds the **runtime enforcement**:

- `ParallelRunner.run()` checks `len(items) > config.max_items` **before launching any worker** and raises a `ValueError` with a clear message naming the state and the overage
- `ParallelRunner.run()` wraps the fan-out in a wall-clock timer against `config.max_total_seconds`; when exceeded, cancel pending futures, mark in-flight workers as `terminated_by="timeout"`, aggregate per `fail_mode`

### Soft warnings (log but do not fail)

- Worktree count heuristic: when `ParallelRunner` is about to create worktree N+1 where N is already >= 50 existing worktrees in the repo, log a WARNING event. At >= 100, log an ERROR event but continue (user may have a legitimate reason).
- Items count vs. max_workers: when `len(items) > 100 * max_workers`, log INFO suggesting the user may want to split into batches or raise `max_workers`.

### Resource cleanup guarantees

Document and test:
- `finally` blocks in `ParallelRunner.run()` ensure `ThreadPoolExecutor.shutdown(wait=False)` is always called, even on exception
- Worktree setup failures don't leak half-created worktrees — teardown called in `except`
- Subprocess file handles are closed in worker cleanup paths

## Use Case

**Who**: An engineer authoring a `parallel:` state whose `items:` expression resolves from user input (`captured.queue.output`).

**Context**: A bug in an upstream state produces an items list with 50,000 entries. Today, the fan-out launches — 50,000 sub-loops queued, thousands of worktree operations attempted, host resources exhausted.

**Goal**: Catch the oversized fan-out early with a clear error ("fan-out of 50,000 items exceeds `max_items=1000`; raise the limit explicitly if this is intentional") so the bug is visible and recoverable.

## Proposed Solution

1. ~~Add `max_items` and `max_total_seconds` to `ParallelStateConfig`~~ — **moved to FEAT-1074** on 2026-04-20. Schema fields and basic range validation land there so the dataclass ships complete at v1.
2. In `ParallelRunner.run()`: check `len(items) > config.max_items` before launching; raise `ValueError` with a clear message before any worker is spawned
3. In `ParallelRunner.run()`: wrap the fan-out in a wall-clock timer against `config.max_total_seconds`; on breach, cancel pending + mark in-flight as timed out
4. Add `_check_worktree_count()` helper that counts `git worktree list` entries and emits warnings at thresholds
5. Audit `ParallelRunner.run()` for `try/finally` completeness on shutdown + worktree teardown paths
6. Document all limits in `docs/generalized-fsm-loop.md` and `CREATE_LOOP_SKILL.md`
7. Add tests: oversized items rejected at runtime, cumulative timeout fires and aggregates correctly, worktree warning emitted at threshold, cleanup on exception

## Dependencies

- **Hard blockers**: FEAT-1074 (schema fields `max_items`, `max_total_seconds` — now owned there), FEAT-1075 (runner), FEAT-1076 (dispatch)
- **Related**: ENH-1165 (cancellation) — the cumulative-timeout cancellation path mirrors the signal-based one

## Acceptance Criteria

- Runtime check: `len(items) > config.max_items` rejects oversized fan-outs before any worker spawns; error message names the state and the overage (schema field itself is owned by FEAT-1074)
- Runtime timer: `config.max_total_seconds` fires an aggregate timeout that cancels pending futures and records in-flight workers as `terminated_by="timeout"`
- Worktree count warnings emit at 50 and 100 thresholds; do not fail execution
- `ParallelRunner.run()` has `try/finally` guaranteeing executor shutdown and worktree teardown in all exception paths
- Defaults (declared in FEAT-1074: `max_items: 1000`, `max_total_seconds: None`) do not affect existing loops on small item lists — enforcement path is a no-op until fields are set
- Tests cover: oversized items, cumulative timeout expiration, worktree warnings, cleanup on exception

## Impact

- **Priority**: P2 — Promoted from P3 on 2026-04-20 during parallel-family review. Rationale: accidental oversized fan-outs (thousands of items from a misresolved `${captured...}` expression or a liberal `items:` glob) are too easy to trip into, and the blast radius (host CPU saturation, unbounded subprocess spawn, runaway worktree creation) is large enough that shipping v1 without guardrails is a foot-gun we'd regret the first incident. Must land alongside the parallel-state v1 feature set.
- **Effort**: Small-to-Medium — Schema fields + runner guards + tests; cumulative-timeout path is the trickiest
- **Risk**: Low — Hard limits are additive with conservative defaults; removing them or raising them is a config change
- **Breaking Change**: No — default `max_items: 1000` is above any realistic existing use; if anyone is running >1000-item fan-outs today (unlikely; parallel is new), they can override explicitly

## Labels

`fsm`, `parallel`, `limits`, `resources`, `safety`

---

## Session Log
- `parallel-fsm-review` - 2026-04-18T00:00:00Z - spawned during parallel feature review discussion
- `parallel-family-review` - 2026-04-20T00:00:00Z - promoted from P3 to P2. Rationale recorded in Impact section: oversized fan-outs are a real foot-gun (misresolved context vars, liberal globs) with a blast radius that warrants v1 guardrails rather than post-incident hardening. Cross-referenced from FEAT-1080 CLI-awareness warning and from ENH-1186 v1 scope doc.
- `parallel-family-review` - 2026-04-20T00:00:00Z - schema fields `max_items` and `max_total_seconds` moved to FEAT-1074 (schema issue) to resolve a field-count mismatch that would have forced a mid-implementation schema churn. This issue now owns runtime enforcement only (oversized-items rejection, cumulative wall-clock timer, worktree-count warnings, cleanup audit).

---

**Open** | Created: 2026-04-18 | Priority: P2 (promoted from P3 on 2026-04-20)
