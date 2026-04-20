---
discovered_date: "2026-04-18"
discovered_by: parallel-fsm-review
depends_on: [FEAT-1074, FEAT-1075, FEAT-1076]
---

# ENH-1176: Parallel State Resource Limits

## Summary

Add enforced upper bounds on parallel state resource consumption: maximum items per fan-out, cumulative timeout across all workers, and a soft warning threshold for git worktree count. Without these, a parallel state defined over a very large items list (thousands), a pathological per-worker duration, or deep worktree nesting can degrade the host system or produce unbounded runtime.

## Current Behavior (as of FEAT-1074/1075/1076)

- `parallel.items` has no upper bound — an `items` expression resolving to 10,000 entries runs 10,000 sub-loops (albeit `max_workers` at a time)
- `timeout_seconds` is per-worker only. No cumulative cap on total fan-out duration. With `max_workers=4` and 1000 items at 60s each, worst-case wall-clock is 15,000s (4+ hours) with no error surface.
- `isolation: worktree` creates one worktree per concurrent worker (bounded by `max_workers`), but nested parallel states (now forbidden per FEAT-1074 nesting rule) or sequential parallel states in the same loop run can accumulate worktrees. Git performance degrades past roughly 100 worktrees per repo; no warning is emitted.
- No memory/file-handle cap on held subprocesses

## Expected Behavior

### Hard limits (fail validation or fail-fast at execution)

Add to `ParallelStateConfig` (schema):
- `max_items: int = 1000` — reject fan-outs larger than this at runtime with a clear error; configurable per-state
- `max_total_seconds: int | None = None` — cumulative wall-clock timeout across the entire parallel state; when exceeded, cancel pending futures, mark in-flight workers as timed-out, aggregate per `fail_mode`
- Validation: `max_items >= 1`, `max_total_seconds is None or max_total_seconds >= 1`, `max_total_seconds > (max_workers * timeout_seconds)` if both set (otherwise the cumulative cap is meaningless)

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

1. Add `max_items` and `max_total_seconds` to `ParallelStateConfig` with sensible defaults (`max_items: 1000`, `max_total_seconds: None`)
2. In `ParallelRunner.run()`: check `len(items) > max_items` before launching; raise `ValueError` with a clear message before any worker is spawned
3. In `ParallelRunner.run()`: wrap the fan-out in a wall-clock timer; on breach, cancel pending + mark in-flight as timed out
4. Add `_check_worktree_count()` helper that counts `git worktree list` entries and emits warnings at thresholds
5. Audit `ParallelRunner.run()` for `try/finally` completeness on shutdown + worktree teardown paths
6. Document all limits in `docs/generalized-fsm-loop.md` and `CREATE_LOOP_SKILL.md`
7. Add tests: oversized items rejected, cumulative timeout fires and aggregates correctly, worktree warning emitted at threshold, cleanup on exception

## Dependencies

- **Hard blockers**: FEAT-1074 (schema fields), FEAT-1075 (runner), FEAT-1076 (dispatch)
- **Related**: ENH-1165 (cancellation) — the cumulative-timeout cancellation path mirrors the signal-based one

## Acceptance Criteria

- `max_items` rejects oversized fan-outs before any worker spawns; error message names the state and the overage
- `max_total_seconds` fires an aggregate timeout that cancels pending futures and records in-flight workers as timed out
- Worktree count warnings emit at 50 and 100 thresholds; do not fail execution
- `ParallelRunner.run()` has `try/finally` guaranteeing executor shutdown and worktree teardown in all exception paths
- Defaults (`max_items: 1000`, `max_total_seconds: None`) do not affect existing loops on small item lists
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

---

**Open** | Created: 2026-04-18 | Priority: P2 (promoted from P3 on 2026-04-20)
