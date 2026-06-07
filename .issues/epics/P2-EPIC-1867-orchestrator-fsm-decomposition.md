---
id: EPIC-1867
title: Orchestrator FSM Decomposition (ll-auto / ll-sprint / ll-parallel)
type: EPIC
priority: P2
captured_at: '2026-06-02T02:18:04Z'
discovered_date: 2026-06-02
discovered_by: capture-issue
status: open
relates_to:
- FEAT-1901
- FEAT-1899
- ENH-1903
- FEAT-2000
- FEAT-2001
- FEAT-2002
---

# EPIC-1867: Orchestrator FSM Decomposition (ll-auto / ll-sprint / ll-parallel)

## Summary

Decompose the three Python orchestrators (`ll-auto`, `ll-sprint`, `ll-parallel`)
into a layered architecture where the **FSM owns orchestration control flow** and
**Python owns domain algorithms and the parallel substrate**. Replace `ll-auto`'s
hand-rolled `while`/`if-else` loop with an `loops/ll-auto.yaml` FSM that shells out
to a stabilized internal library, convert `ll-sprint` into an FSM wave driver, and
explicitly **keep `ll-parallel` as Python** (the FSM engine has no concurrency
primitive).

Tracks the v0.2 decomposition plan at
`docs/research/ll-orchestrator-decomposition-plan-v0.2.md`, which supersedes the
v0.1 "deprecate all three tools" framing after grounding it against the actual code.

## Motivation

v0.1 proposed deprecating all three orchestrators in favor of FSM loop states,
concluding "the only Python that survives is `failure_classifier.py`." Verified
against the code, that claim was off by ~an order of magnitude:
`process_issue_inplace()` also does dependency-gated selection, 6-strategy verdict
parsing, git-diff **work verification**, lifecycle commits, failure classification,
and event emission to `history.db`. And `ll-parallel` is **not FSM-replaceable** —
the executor is a single-threaded `while` loop with no scheduler.

The value is real but narrower than v0.1 claimed: let the FSM own the genuine
control-flow glue (loop, state persistence, signal handling) while preserving every
battle-hardened domain path (BUG-1377/1759/007/579 fixes) as a stable Python
library called from shell actions.

## Goal

When this epic is done:
- `ll-auto` is a thin shim over `ll-loop run ll-auto`, with the FSM calling
  Layer-0 CLIs for selection, verification, and failure classification.
- `ll-sprint` is a thin shim over an FSM wave driver that reuses the per-issue states.
- `ll-parallel` is documented as the canonical parallel substrate (unchanged CLI),
  shared by `ll-sprint` multi-issue waves.
- The shared core (`process_issue_inplace`, `DependencyGraph`,
  `run_with_continuation`, `worktree_utils`, `ParallelOrchestrator`) is a documented,
  test-gated internal library.
- An A/B parity gate proves the loop produces identical `completed/failed` sets and
  `history.db` events as the old `ll-auto` on a real backlog.

## Scope

### In scope

- **Layer 0 (prerequisite, behavior-neutral):** Stabilize the shared modules as a
  documented internal library and expose them as CLI subcommands for shell actions:
  - `ll-issues next --json --respect-deps --priority … --skip …` (wraps
    `DependencyGraph.get_ready_issues()` + filters).
  - `ll-issues verify-work <id> --baseline <sha>` (wraps `verify_work_was_done()` +
    `verify_issue_completed()`; exit 0 = real work, 1 = none). **This is the non-LLM
    evaluator the FSM needs to satisfy CLAUDE.md MR-1.**
  - `ll-issues classify-failure --rc <n> < err.txt` (wraps
    `classify_failure`/`create_issue_from_failure`).
  - Keep `run_with_continuation()` (Options E/G/J) as-is.
- **Layer 1:** `loops/ll-auto.yaml` FSM replacing `AutoManager.run()` control flow.
  Mandatory `verify_work` state (`exit_code` evaluator) gates marking `done` — never
  trust the implement step's exit code alone. `max_iterations` set from backlog size
  (default 50 would halt after ~10 issues).
- **Layer 2:** `ll-sprint plan <name> --json` emitting ordered waves + an FSM wave
  driver. Single/contention sub-waves reuse the Layer-1 per-issue states; multi-issue
  waves shell out to `ParallelOrchestrator`.
- Migration shims, deprecation (not deletion) of `AutoManager.run()` for one release,
  and docs updates (`CLAUDE.md` CLI Tools, `docs/ARCHITECTURE.md`).

### Out of scope

- Replacing `run_with_continuation()` (E/G/J) with `on_handoff` — rejected;
  `on_handoff` is loop-level and a strict subset.
- Expressing `ll-parallel`'s worker pool as an FSM — rejected; no FSM concurrency
  primitive (Layer 3 = keep as-is).
- A single mega-loop covering all three tools — rejected; different execution models
  (sequential vs wave vs concurrent).
- Rewriting the battle-hardened continuation/merge code.

## Children

- **FEAT-1901** — Stabilize shared orchestration core and expose as ll-issues subcommands (Layer 0)
- **FEAT-1902** — Author loops/ll-auto.yaml FSM + ll-auto shim + A/B parity harness (Layer 1)
- **FEAT-1899** — Implement ll-sprint FSM wave driver and shim (Layer 2)
- **ENH-1903** — Document ll-parallel as canonical parallel substrate (Layer 3)

## Verification Notes

Acceptance gates from the plan:
- `ll-loop validate ll-auto` passes (MR-1, MR-3).
- `ll-loop run ll-auto --baseline` shows the harness ≥ unguided baseline on a fixed set.
- A/B parity: same backlog through old `ll-auto` vs the loop → identical
  `completed/failed` sets and `history.db` events.
- `ll-loop diagnose-evaluators ll-auto` shows `verify_work` verdict variance
  `p(1-p) ≥ 0.05` over ≥10 runs.

## Open Questions

1. Should the per-issue states be a reusable sub-loop (`ll-loop` composition) so
   Layers 1 and 2 share one definition rather than duplicating states?
2. Does `ll-issues next --respect-deps` need the full `DependencyGraph`, or is the
   lighter `get_ready_issues()` path sufficient for the `ll-auto` case?
3. Keep `.auto-manage-state.json` semantics anywhere, or fully delegate resume to
   `ll-loop` persistence (preferred)?

## Related Key Documentation

| Document | Relevance |
|---|---|
| `docs/research/ll-orchestrator-decomposition-plan-v0.2.md` | Source plan (this EPIC tracks it) |
| `.claude/CLAUDE.md` § Loop Authoring (MR-1/MR-3) | Meta-loop gate the `ll-auto` loop must pass |
| `docs/ARCHITECTURE.md` | Target for orchestration architecture updates |

## Session Log
- `/ll:verify-issues` - 2026-06-05T21:00:23 - `current-session.jsonl`
- `/ll:verify-issues` - 2026-06-02T22:49:02 - `21850d04-bdf9-4e28-bf74-f68eaaaed883.jsonl`
- `/ll:capture-issue` - 2026-06-02T02:18:04Z - `1758d419-8959-4946-ab38-e7f9cbf959a8.jsonl`

---

## Status

open
