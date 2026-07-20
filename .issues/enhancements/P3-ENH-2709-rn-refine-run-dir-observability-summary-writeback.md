---
id: ENH-2709
status: open
captured_at: "2026-07-20T19:30:00Z"
discovered_date: 2026-07-20
discovered_by: capture-issue
---

# ENH-2709: rn-refine run-dir observability (summary.json + writeback.json)

## Summary

`rn-refine` (`scripts/little_loops/loops/rn-refine.yaml`) never writes a `summary.json` or a write-back marker to its run dir, unlike sibling loops `rn-implement` and `auto-refine-and-implement` which already emit `summary.json`. This forces anyone auditing a run (success, partial, or timeout) to reconstruct status by parsing `events.jsonl` and diffing files by hand.

## Current Behavior

In the `rn-refine-20260720T002123` audit (`rn-refine-audit-2026-07-20T134636.md`), the investigator could not tell from the run dir alone whether the 6-hour run had succeeded or timed out:

- No `summary.json` anywhere in the run dir — had to infer node counts from `leaves.txt`/`capped.txt`/`failed_nodes.txt`/`queue.txt` and cross-reference `dequeue_count.txt`
- No write-back marker — had to `diff` the source `phase-2-only-plan.md` against the run's `plan.md` and check mtimes to confirm the source was untouched
- `finalize`/`finalize_aborted` and the timeout path all leave the run dir in this same ambiguous state

The audit's own scorecard makes the cost explicit: it could not distinguish a 6-hour timeout from a 6-hour success without parsing `events.jsonl` directly.

## Expected Behavior

`rn-refine` should write, at minimum:

1. **`summary.json`** — written by `finalize`, `finalize_aborted`, and any timeout/deadline-drain exit path. Should include: `nodes_processed`, `leaves`, `capped`, `failed`, `pending_queue`, `wip_nodes`, `source_overwritten`, `terminated_by` (`success`/`timeout`/`aborted`).
2. **`writeback.json`** — written by `finalize` immediately after the source plan file is overwritten (or its absence implied by `summary.json.source_overwritten: false` on non-finalize exits), recording `{written, timestamp, source_path, backup_path}`.

This gives parity with `rn-implement`/`auto-refine-and-implement` and lets `/ll:audit-loop-run` (and any operator) determine run status from the run dir alone, without parsing `events.jsonl`.

## Motivation

Parity with existing harness convention (`rn-implement`, `auto-refine-and-implement` already emit `summary.json`) and directly reduces audit cost — the audit for this exact run had to hand-parse `events.jsonl` and `diff` files to answer "did this succeed."

## Proposed Solution

Fold the audit's proposals 1 and 6 together (needs `/ll:refine-issue` for concrete diffs against the current FSM structure):

- Add a `summary.json` write at the top of `finalize` and `finalize_aborted`, and at the deadline-guard exit in `dequeue_next` (and any other exit path found during investigation) — computed from the same artifacts the audit hand-parsed (`leaves.txt`, `capped.txt`, `failed_nodes.txt`, `queue.txt`, `dequeue_count.txt`).
- Add a `writeback.json` write in `finalize` right after the source file copy, recording whether/when the write-back happened.
- Verify against a real (non-simulated) timeout run, since `ll-loop simulate` returns synthetic strings that won't exercise the artifact-reading logic realistically.

## Scope Boundaries

In scope: `finalize`, `finalize_aborted`, and deadline-guard exit paths in `rn-refine.yaml` writing `summary.json`/`writeback.json`. Out of scope: fixing the underlying sub-loop outcome loss (see companion issue) or the deadline-drain queue-truncation issue.

## Impact

- **Priority**: P3 — observability improvement, not a correctness bug; doesn't lose work, just makes diagnosis slower.
- **Effort**: Small-medium — adding JSON writes to a handful of existing terminal/exit states; no routing changes.
- **Risk**: Low — additive artifact writes, no behavior change to the FSM's decision logic.

## Related Key Documentation

| Document | Relevance |
|---|---|
| .claude/CLAUDE.md | Loop Authoring meta-loop rules (MR-3: intermediate artifacts should live under `${context.run_dir}/`, which `summary.json`/`writeback.json` already satisfy by design) |

## Status

- [ ] Not started

## Session Log
- `/ll:capture-issue` - 2026-07-20T19:30:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e43208e6-cc93-448d-8f8e-8ba33fb2cb7e.jsonl`
