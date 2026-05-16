---
discovered_date: "2026-04-20"
discovered_by: parallel-family-review
depends_on: [FEAT-1174]
---

# ENH-1195: `ll-loop resume` CLI-Side Navigation for Per-Worker Parallel Checkpoints

## Summary

FEAT-1174 adds per-worker checkpointing inside a parallel state — `parallel_progress[state].completed` records which workers finished before interrupt. The resume *machinery* is in scope of FEAT-1174, but the CLI UX for inspecting and driving that resume is not. Add `ll-loop resume` subcommand surface so operators can see which workers already completed, which remain, and decide how to proceed — without reading raw JSON out of the checkpoint file.

## Current Behavior (as of FEAT-1174)

`ll-loop resume <run-id>` (command referenced in FEAT-1174, flags TBD) simply re-enters the executor. If `parallel_progress[state]` is present and `items_hash` matches, the runner silently filters out completed workers and re-runs only the remainder. If `items_hash` mismatches, a WARNING log fires and the state re-runs from scratch (all prior completions discarded).

An operator has no pre-resume visibility into which workers completed. To decide whether a partial resume is safe, they have to `cat <run-dir>/<run-id>.json | jq .parallel_progress` and interpret it manually.

## Expected Behavior

1. **`ll-loop resume --status <run-id>`** (or `ll-loop status <run-id>`) — print a summary of checkpoint state without executing:
   ```
   Run: recursive-refine-2026-04-20T14:23:01
   Current state: fan_out (parallel, in progress)
     Items:     20 total
     Completed: 12 (indices 0,1,2,4,5,6,7,10,11,14,15,19)
     Pending:   8  (indices 3,8,9,12,13,16,17,18)
     Items hash: a3f2c1b5... (matches current items)
   ```
2. **`ll-loop resume --from-scratch <run-id>`** — explicit opt-in to discard `parallel_progress` and re-run the parallel state from scratch. Useful when the operator knows the inputs drifted in a way that hash-matches but is semantically different.
3. **`ll-loop resume --dry-run <run-id>`** — print what would be re-run (the filtered items list), without starting execution.
4. **items_hash mismatch prompt** — when the hash mismatches, `ll-loop resume` (without flags) prints the WARN (per FEAT-1174) AND refuses to proceed unless `--from-scratch` is passed OR `--force` is passed. Default behavior is NOT to silently discard N completed workers.

The `--force` flag is distinct from `--from-scratch` because "from scratch" means the operator wants a full re-run regardless; "force" means "I acknowledge the hash mismatch, proceed with discarding and re-running anyway."

## Use Case

**Who**: An operator resuming a long parallel run the morning after a crash.

**Context**: `recursive-refine` was fanning out over 20 issues at `max_workers: 4`; crashed at 12 done, 8 remaining. The operator wants to confirm the remaining 8 are the right 8 before spending compute.

**Outcome**: `ll-loop resume --status <run-id>` shows the split; operator runs `ll-loop resume <run-id>` and only 8 workers fire.

## Proposed Solution

1. Extend `scripts/little_loops/cli/loop/run.py` (or wherever `ll-loop resume` lives) with `--status`, `--dry-run`, `--from-scratch`, and `--force` flags.
2. Load the checkpoint file, parse `parallel_progress`, render a human-readable summary. Reuse the same item-hash computation used by FEAT-1174 so "matches current items" is accurate.
3. Gate silent hash-mismatch discards behind `--force` / `--from-scratch`. This protects operators from accidentally nuking prior work.

## Files to Modify

- `scripts/little_loops/cli/loop/run.py` (or `resume.py`) — new flags, status rendering
- `scripts/little_loops/fsm/persistence.py` — expose a `read_only_snapshot()` or similar that doesn't mutate state
- `scripts/tests/test_cli_loop_resume.py` — new tests for each flag, including hash-mismatch gated behind `--force`
- `docs/generalized-fsm-loop.md` — document the resume flags in the parallel-state chapter

## Dependencies

- **Hard blockers**: FEAT-1174 (the `parallel_progress` schema this reads)
- **Soft**: ENH-1192 (partial checkpoint-write recovery) — status output should indicate if the checkpoint is mid-write corrupted

## Acceptance Criteria

- `ll-loop resume --status <run-id>` prints completed/pending/hash summary without executing
- `ll-loop resume --dry-run <run-id>` prints the filtered items list without executing
- Without `--force` / `--from-scratch`, an items_hash mismatch causes resume to exit non-zero with a clear message instead of silently discarding prior completions
- `--from-scratch` explicitly clears `parallel_progress` and runs the parallel state fresh
- Tests cover all four flag combinations including hash-mismatch gating

## Impact

- **Priority**: P4 — UX polish on top of FEAT-1174. Not required for v1 parallel ship, but the "silent discard on hash mismatch" behavior is a footgun that should be removed before heavy parallel adoption.
- **Effort**: Small-Medium — CLI flags + status rendering + 4-5 tests
- **Risk**: Low-Medium — the hash-mismatch gating is a **behavior change** from FEAT-1174 as currently specified (today: silent discard with WARN; proposed: require explicit flag). If this ships after FEAT-1174 hits production, existing scripts relying on unattended resume may break.
- **Breaking Change**: Potentially — if FEAT-1174 shipped and operators scripted `ll-loop resume` to run unattended, gating hash-mismatch would break those scripts. Mitigation: mention in CHANGELOG, provide `--force` as the opt-out.

## Labels

`fsm`, `parallel`, `cli`, `resume`, `ux`

## Related / See Also

- **FEAT-1174** — per-worker checkpointing (machinery this CLI drives)
- **ENH-1192** — partial checkpoint-write recovery (affects status-rendering correctness)
- **ENH-1173** — unresolved-context variable pre-scan (related resume-time validation)

---

## Session Log
- `parallel-family-review` - 2026-04-20T00:00:00Z - Filed as follow-up from parallel-family review. User requested tracking even though deferred.

---

**Open** | Created: 2026-04-20 | Priority: P4
