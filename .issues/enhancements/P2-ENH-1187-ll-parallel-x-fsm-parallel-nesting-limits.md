---
discovered_date: "2026-04-20"
discovered_by: parallel-family-review
depends_on: [FEAT-1074, FEAT-1075, FEAT-1076, FEAT-1080]
---

# ENH-1187: Hard-Cap and Validate `ll-parallel` × FSM `parallel:` Nested Concurrency

## Summary

FEAT-1080 emits a soft warning when a loop running under `ll-parallel` contains a `parallel:` state. A soft warning is not enough: the cartesian product of outer-level worktree parallelism (`ll-parallel N`) and inner-level FSM fan-out (`max_workers: M`) silently produces N×M concurrent workers. A user running `ll-parallel 4` over a loop with `max_workers: 4` gets 16 concurrent git/subprocess operations with no hard cap. This is the most likely OOM / subprocess-fork-bomb / git-lock-contention footgun in v1.

## Current Behavior (as of FEAT-1080)

`FEAT-1080` (config wiring) emits a warning when `ll-parallel` detects a loop YAML containing `parallel:` states, but does not enforce a cap. Users are free to run with unlimited nesting. No validation error, no `--force` override, no recorded cap value in `.ll/ll-config.json`.

## Expected Behavior

1. A configurable hard cap `parallel_nesting_product_cap` (default: 8) lives in `.ll/ll-config.json` under a new `parallel` block.
2. `ll-parallel` and `ll-sprint --parallel` detect the product `outer_parallelism × max(inner_max_workers across all parallel states in the target loop)` before dispatch.
3. If the product exceeds the cap, the command fails fast with a validation error naming both factors and the cap, and suggesting either lowering `-j` / `max_workers` or passing `--force-nested-parallel` to override.
4. `--force-nested-parallel` exists and overrides the cap with a logged warning recorded to the session JSONL.
5. `ll-loop run` (no outer `ll-parallel`) is unaffected — this is specifically the nested case.

## Proposed Solution

1. Add `LLConfig.parallel.nesting_product_cap: int = 8` in `.ll/ll-config.json` schema (see `scripts/little_loops/config.py`).
2. In `cli/ll_parallel.py` and `cli/ll_sprint.py`, before dispatch, resolve the target loop(s) and statically walk the FSM for `parallel:` states; compute the product and compare to cap.
3. Shared helper `parallel.check_nesting_product(outer_n: int, loop_configs: list[FSMLoop], cap: int) -> None` raises `NestedParallelismExceeded` on overage.
4. Document the cap and override flag in `docs/generalized-fsm-loop.md` and `docs/reference/parallel-state-v1-scope.md` (ENH-1186).

## Files to Modify

- `scripts/little_loops/config.py` — add `parallel.nesting_product_cap` field
- `scripts/little_loops/parallel/nesting.py` — new module for the check helper
- `scripts/little_loops/cli/ll_parallel.py` — call check before dispatch; expose `--force-nested-parallel`
- `scripts/little_loops/cli/ll_sprint.py` — same check at the `--parallel` path
- `scripts/tests/test_parallel_nesting.py` — new test file
- `docs/generalized-fsm-loop.md`, `docs/reference/parallel-state-v1-scope.md` — document cap + override

## Acceptance Criteria

- Default cap of 8 applies when `parallel.nesting_product_cap` is absent from config
- Running `ll-parallel 4` over a loop with `max_workers: 4` (product 16 > cap 8) exits non-zero with an error naming both factors and the cap
- Passing `--force-nested-parallel` succeeds but logs a WARNING-level line containing both factors
- `ll-loop run` with a `parallel:` state but no outer parallelism runs unchanged (no cap check)
- Test covers: product under cap (pass), product over cap (fail), `--force-nested-parallel` override (pass + warn), multiple `parallel:` states in the same loop (max of inner workers is used)
- Config-schema docs updated; `.ll/ll-config.json` example includes the new field

## Impact

- **Priority**: P2 — Without a hard cap, v1 parallel under `ll-parallel` can silently OOM or exhaust file descriptors on even modest-size laptops. Soft warning from FEAT-1080 is insufficient; user must explicitly opt in to dangerous configurations.
- **Effort**: Small — one helper module + two CLI integration points + tests
- **Risk**: Low — fail-closed default (cap=8 is permissive enough for normal use); explicit override path
- **Breaking Change**: No — new validation that blocks previously-unintentional dangerous configurations

## Labels

`fsm`, `parallel`, `cli`, `safety`, `config`

## Related / See Also

- **FEAT-1080** — the soft-warning version this issue replaces with enforcement
- **ENH-1176** — resource-limit family; this is one specific limit
- **ENH-1186** — v1 scope doc; nesting cap is a documented v1 guarantee

---

## Session Log
- `parallel-family-review` - 2026-04-20T00:00:00Z - Created during issue-set review. FEAT-1080 ships a soft warning but review flagged the cartesian-product risk as the worst unpriced footgun in v1. Hard cap + explicit override is the fix.

---

**Open** | Created: 2026-04-20 | Priority: P2
