---
captured_at: "2026-05-23T16:40:11Z"
discovered_date: 2026-05-23
discovered_by: capture-issue
status: open
depends_on: [BUG-1628, ENH-1629]
---

# ENH-1631: Add `on_max_iterations` summary hook to FSM runtime + general-task loop

## Summary

When an FSM loop hits `max_iterations`, the runtime silently terminates in whatever state was last executing — leaving the operator with no structured account of what was accomplished vs. what remains. Add an `on_max_iterations: <state>` field at the loop top level (parallel to `on_retry_exhausted` on individual states) and wire `general-task.yaml` to use it for writing a partial-run summary to disk.

## Current Behavior

When `FSMExecutor.run()` exhausts its `max_iterations` budget, it terminates in whatever state was last executing and emits a generic `failed`/cap-reached outcome. No structured summary artifact is written, no distinct event signals partial completion to audit tooling, and the operator must reconstruct progress by hand from the JSONL transcript. Individual states already support `on_retry_exhausted` (`scripts/little_loops/fsm/schema.py:785`), but there is no loop-level equivalent for the iteration-cap case.

## Expected Behavior

The loop YAML schema accepts a top-level `on_max_iterations: <state>` field. When the iteration cap fires and this field is set, the runtime transitions to the named state for exactly one additional action+evaluate cycle, then terminates. The runtime emits an event (e.g., `max_iterations_summary` or an extended `_finish` payload) that audit tooling can use to distinguish "terminated with summary" from "terminated cold." `general-task.yaml` ships with a `summarize_partial` state that writes `${env.PWD}/.loops/tmp/general-task-summary.md` describing what was accomplished, remaining DoD gaps, and recommended next actions.

## Motivation

A recent `general-task` run (`2026-05-23T113819`) terminated at iteration 100 with 10/18 DoD criteria passing and a fully-checked plan. The only artifact left behind was the DoD file with mixed `[x]`/`[ ]` markers — no narrative summary of what was attempted, what failed, or what an operator should do next. For the harness's most generic loop, this is the difference between "the run produced something I can pick up" and "I have to reread 100 iterations of JSONL to understand the state."

This is structurally similar to `on_retry_exhausted` on `StateConfig` (already supported in `scripts/little_loops/fsm/schema.py:785`), just lifted to the loop level for the iteration-cap case.

## Proposed Solution

### Runtime change (`scripts/little_loops/fsm/`)

1. Add `on_max_iterations: str | None = None` to the loop-level schema (alongside `max_iterations: int = 50`) in `scripts/little_loops/fsm/schema.py`.
2. In `FSMExecutor.run()`, when the iteration cap fires, if `on_max_iterations` is set, transition to that state for one final action+evaluate cycle before terminating. Cap the post-budget execution at 1 extra iteration to prevent runaway.
3. Emit a new event (`max_iterations_summary` or extend `_finish` payload) so audit tooling can detect partial-completion termination distinctly from `failed` or `done`.

### Loop change (`scripts/little_loops/loops/general-task.yaml`)

```yaml
max_iterations: 100
on_max_iterations: summarize_partial

states:
  summarize_partial:
    action: |
      Read ${env.PWD}/.loops/tmp/general-task-dod.md and
      ${env.PWD}/.loops/tmp/general-task-plan.md. Write a one-paragraph
      summary to ${env.PWD}/.loops/tmp/general-task-summary.md covering:
      (1) what was accomplished, (2) which DoD criteria remain unmet,
      (3) recommended next actions for a human operator.
    action_type: prompt
    next: done
```

### Tests / docs

- `scripts/tests/test_fsm_executor.py` — add a regression test for a loop that hits `max_iterations` and verify the summary state runs exactly once.
- `docs/guides/LOOPS_GUIDE.md` — document the new top-level field.
- `docs/reference/API.md` — update FSM schema reference.

## Acceptance Criteria

- [ ] `on_max_iterations` accepted by the loop YAML schema and validated by `LoopConfig.from_dict`.
- [ ] Runtime executes the target state exactly once when the iteration cap fires, then terminates.
- [ ] `general-task.yaml` defines `summarize_partial` and writes a summary file on partial runs.
- [ ] Audit tooling (`/ll:audit-loop-run`) can distinguish "terminated with summary" from "terminated cold."
- [ ] Regression test covers the cap-firing + summary-state path.

## Scope Boundaries

Out of scope:

- Continuing iteration past the cap (the summary state runs exactly once; no loop resumption or budget extension).
- Chaining multiple summary states or arbitrary post-budget FSM flows.
- Automatic re-invocation of the loop with the partial summary as new context.
- Backporting `on_max_iterations` semantics to per-state `on_retry_exhausted` (they remain independent mechanisms).
- Changes to the JSONL transcript format beyond the new termination event.

## Impact

- **Priority**: P3 — operator ergonomics for the most generic loop; not blocking but high leverage once `general-task` is used regularly.
- **Effort**: Small — schema field + one branch in `FSMExecutor.run()` + one YAML state + regression test. Reuses the existing `on_retry_exhausted` pattern as a model.
- **Risk**: Low — additive field with `None` default preserves current behavior for all existing loops; post-budget execution is capped at 1 iteration to prevent runaway.
- **Breaking Change**: No.

## Related

- [[BUG-1628]] — partial fix overlaps: with replan + oscillation guard in place, `max_iterations` will fire less often, but the summary hook is still useful for genuinely large tasks.
- [[ENH-1629]] — pairs naturally with explicit threshold keys; the summary can report against `target_pass_rate`.

## Source

`general-task-audit-proposals.md` (Proposal 3) — derived from a partial run audit on 2026-05-23. Proposals file is transient; this issue is the durable record.

## Labels

`enhancement`, `fsm-runtime`, `general-task`, `captured`

## Session Log
- `/ll:audit-issue-conflicts` - 2026-05-23T20:59:17 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/53f5ce8a-8802-4e4f-a82f-cb8f836c6b67.jsonl`
- `/ll:format-issue` - 2026-05-23T16:43:14 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3b5c3569-1967-4199-ba4f-ccf461e65ff0.jsonl`
- `/ll:capture-issue` - 2026-05-23T16:40:11Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/001d2505-0292-435c-bc36-5f2f000ffd72.jsonl`

---

**Open** | Created: 2026-05-23 | Priority: P3

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): This issue modifies general-task.yaml FSM structure (adding `on_max_iterations: summarize_partial` + `summarize_partial` state) and schema.py (adding the top-level `on_max_iterations` field). BUG-1628 makes overlapping structural changes to the same files (replan state, execute/continue_work differentiation). This issue `depends_on: BUG-1628` — let the P2 bug fix land and settle the general-task.yaml structure before adding the on_max_iterations hook to avoid merge conflicts.
