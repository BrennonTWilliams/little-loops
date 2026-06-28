---
id: ENH-2365
type: ENH
title: Emit summary.json on general-task terminal `done`, not only on max_steps
priority: P3
status: open
captured_at: '2026-06-28T05:12:41Z'
discovered_date: 2026-06-28
discovered_by: capture-issue
labels:
- captured
- fsm
- harness
- loops
- general-task
- observability
relates_to:
- BUG-2351
- ENH-1631
- ENH-1726
parent: EPIC-1744
---

# ENH-2365: Emit summary.json on general-task terminal `done`, not only on max_steps

## Summary

The `general-task` loop (`scripts/little_loops/loops/general-task.yaml`) only writes a
machine-readable run summary when it terminates via the `max_steps` path. ENH-1631 added
the `summarize_partial` state, wired to `on_max_steps`, which writes a `summary.md`/JSON
roll-up for capped runs. A *clean* terminal `done` — the success path through
`count_final → done` — leaves **no** structured summary in the run/history directory.

This is an observability gap with a concrete downstream cost: `skills/audit-loop-run/SKILL.md`
keys its phantom-vs-honest-failure verdict on `summary.json` presence.

## Current Behavior

- `summarize_partial` (the only summary-writing state) is reachable solely via
  `on_max_steps: summarize_partial` at the loop top level.
- The success path `count_final` (`on_yes`) → `done` (terminal) writes nothing
  machine-readable. The verified counts exist at this point in
  `captured.done_counts` and `captured.final_counts`, but are not persisted to a
  roll-up artifact.
- Confirmed empirically: audit of run `2026-06-28T041103` (verdict `met`, terminal
  `done`) recorded `summary.json` as **ABSENT** in
  `.loops/.history/2026-06-28T041103-general-task/`.

## Expected Behavior

A clean terminal `done` writes a `summary.json` to the run/history directory containing
at minimum: verified DoD counts (from `done_counts`), final-verification counts (from
`final_counts`), and the primary artifact delta. The `max_steps` path continues to write
its partial summary as today.

## Motivation

`skills/audit-loop-run/SKILL.md` uses `summary.json` presence as a verdict signal
(lines 258–259):

- **line 258** — `summary.json` *absent* contributes to a **`phantom`** classification
  ("loop provides no failure evidence").
- **line 259** — the **`honest-failure`** verdict *requires* `summary.json` present.

Because the general-task success path never writes `summary.json`, a genuinely
successful run can be **mechanically pushed toward a `phantom` label** by the audit
tool's own heuristics — the same failure class as **BUG-2351** (audit-loop-run mislabels
honest failure as phantom). The human/LLM auditor reading artifacts can still reach the
correct `met` verdict (as it did for `2026-06-28T041103`), but the mechanical signal is
wrong, which is exactly the fragility BUG-2351 is about. Closing this gap makes the
success path legible to downstream tooling, dashboards, and cost reports.

## Proposed Solution

Add a `summarize_success` state between `count_final` and `done`:

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/general-task.yaml` — add `summarize_success` state; repoint `count_final.on_yes`

### Dependent Files (Callers/Importers)
- `skills/audit-loop-run/SKILL.md` — consumes `summary.json` for phantom-vs-honest-failure verdict (lines 258–259); this fix makes the success path legible to its heuristics
- `.loops/.history/<run_id>-general-task/` — destination directory written by the runtime during `_finish`/history export

### Similar Patterns
- `scripts/little_loops/loops/sprint-refine-and-implement.yaml` — also has `summarize_partial`; check if success path has the same gap
- `scripts/little_loops/loops/auto-refine-and-implement.yaml` — same
- `scripts/little_loops/loops/rn-implement.yaml` — same

### Tests
- `scripts/tests/test_general_task_loop.py` — primary test file; add assertion that `summary.json` appears on the `done` path
- `scripts/tests/test_audit_loop_run_skill.py` — verify `honest-failure` verdict logic with and without `summary.json`
- `scripts/tests/test_builtin_loops.py` — may need update if loop topology is validated here

### Documentation
- N/A

### Configuration
- N/A



```yaml
states:
  count_final:
    on_yes: summarize_success   # was: done

  summarize_success:
    action: |
      Run dir: ${context.run_dir}
      Write a one-paragraph summary of completed DoD criteria and the final artifact
      delta to ${context.run_dir}/summary.md, then emit JSON counters to the run's
      history summary.json (derive the .loops/.history/<run_id>/ path from
      ${context.run_dir}). Include verified done_counts / final_counts and the
      primary artifact byte/line delta.
    action_type: prompt   # or shell, if counts can be assembled mechanically
    next: done
    on_error: done        # best-effort: never block terminal on observability
```

Implementation notes / open questions for refinement:

- **Path derivation.** `run_dir` is `.loops/runs/<loop>-<ts>/` while the audit tool reads
  `.loops/.history/<run_id>-<loop>/summary.json`. The state must derive the history path
  from the run, or the runtime should write the artifact into the history dir directly.
  Cross-check how ENH-1726 (unify FSM run artifacts into per-run directory) and the
  `_finish`/history export already map run → history, to avoid hardcoding a fragile path.
- **shell vs prompt.** Prefer a `shell` writer if `done_counts`/`final_counts` JSON is
  sufficient to assemble the summary deterministically — cheaper and not subject to LLM
  drift. Fall back to a `prompt` only if a narrative paragraph is required.
- **Schema alignment.** The emitted JSON should expose whatever key `audit-loop-run`
  reads for `claimed_success` (e.g. an `implemented`/success token) so the
  honest-failure/phantom discrimination works as documented.
- **on_error: done.** Observability must never demote a real success to `failed`.

## Implementation Steps

1. Add `summarize_success` state; repoint `count_final.on_yes` from `done` to it.
2. Decide shell-vs-prompt; assemble counts from `captured.done_counts` /
   `captured.final_counts` and the artifact delta.
3. Resolve run_dir → history-dir path mapping (reuse existing `_finish`/export logic).
4. Confirm the JSON key surface matches what `audit-loop-run` consumes.
5. `ll-loop validate general-task`; run an end-to-end general-task task and assert
   `summary.json` appears on the success path with correct counts.

## Impact

- **Priority**: P3 — observability gap; does not block current functionality but creates a mechanical mislabel vector in `audit-loop-run` for every successful run.
- **Effort**: Small — one new state + one routing edit in `scripts/little_loops/loops/general-task.yaml`, plus possibly a tiny runtime/path helper. No change to the per-step engine.
- **Risk**: Low — `on_error: done` keeps the success path safe; the `max_steps`/`summarize_partial` path is untouched.
- **Breaking Change**: No — additive only; downstream tooling gains a signal it was missing.
- **Benefit**: removes a mechanical mislabel vector in `audit-loop-run`, gives clean runs a machine-readable roll-up for dashboards/cost reports.

## Scope Boundaries

- **In scope**: adding a `summarize_success` state in `general-task.yaml`; resolving run_dir → history-dir path mapping for that state.
- **Out of scope**: unifying run/history directories (ENH-1726); modifying the per-step FSM engine; changing or fixing `audit-loop-run` itself; applying a similar fix to other loops (`sprint-refine-and-implement`, `auto-refine-and-implement`, `rn-implement`) — those are follow-on work if the gap is confirmed there.

## Context

Captured from `general-task-audit-2026-06-28.md` (Proposal 1), an audit of run
`2026-06-28T041103`. The same audit's Proposal 4 (lift the `count_done` `failed_samples`
decoupling rationale to a state `description:`) was applied inline at capture time;
Proposal 2 (token aggregate) was dropped as already shipped by ENH-1797; Proposal 3
(short-circuit `count_done` on plan exhaustion) was dropped as a minor residual of the
already-resolved BUG-1628 / BUG-1766 convergence cluster.

## Status

**Open** | Created: 2026-06-28 | Priority: P3

## Session Log
- `/ll:format-issue` - 2026-06-28T05:17:22 - `21071d73-56f5-470a-b6f2-dd07673d1d0e.jsonl`
- `/ll:capture-issue` - 2026-06-28T05:12:41Z
