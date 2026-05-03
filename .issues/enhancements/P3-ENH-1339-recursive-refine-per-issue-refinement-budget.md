---
id: ENH-1339
type: ENH
priority: P3
status: open
discovered_date: 2026-05-02
discovered_by: research-synthesis
related: [ENH-1337, ENH-1338]
decision_needed: false
---

# ENH-1339: Per-Issue Refinement Budget Cap in `recursive-refine`

## Summary

`recursive-refine` re-routes a single issue through `refine-to-ready-issue → check_passed → detect_children → recheck_scores → run_size_review → enqueue_or_skip → dequeue_next` per attempt, but if size-review produces children that themselves fail and decompose, *the same root issue ID could indirectly consume dozens of iterations through its descendants*. Add a hard per-issue attempt counter so any individual ID that enters the sub-loop more than `max_refine_count` times (canonical config: `commands.max_refine_count`, currently 5) is flagged, skipped with reason `budget-exceeded`, and surfaced in the summary.

## Motivation

2026 research on agent failure modes converges on per-task budget caps as a stop condition independent from global iteration limits:

- "Every agent run needs a hard cap on the number of thought steps … if the goal isn't reached, the agent terminates with an error" ([fixbrokenaiapps 2026](https://www.fixbrokenaiapps.com/blog/ai-agents-infinite-loops)).
- Microsoft's CORPGEN explicitly assigns multi-horizon task budgets and escalates rather than continuing to retry ([MarkTechPost CORPGEN coverage 2026](https://www.marktechpost.com/2026/02/26/microsoft-research-introduces-corpgen-to-manage-multi-horizon-tasks-for-autonomous-ai-agents-using-hierarchical-planning-and-memory/)).
- Anthropic's "Building Effective Agents" emphasizes giving "the smallest amount of freedom that still delivers the outcome" — implying tight per-task ceilings ([Anthropic 2026](https://www.anthropic.com/research/building-effective-agents)).

Our `context.max_refine_count: 5` exists in the YAML but is currently *unused* by `recursive-refine` itself — it is referenced as canonical config but nothing in the loop reads it. This issue makes that ceiling enforced.

## Current Behavior

- `context.max_refine_count: 5` is declared at `recursive-refine.yaml:27` but never consumed by any state in the loop.
- Each issue's path through the FSM is unbounded except by the global `max_iterations: 500`.
- An issue that fails refine, gets decomposed by size-review, and has its children fail and re-decompose can indirectly consume the entire global budget.

## Expected Behavior

- New tracking file: `.loops/tmp/recursive-refine-attempts.txt` with one line per attempt: `issue_id`.
- `dequeue_next` (or the start of `run_refine`) increments a counter for the current ID.
- A new gate state `check_attempt_budget` between `dequeue_next` and `capture_baseline` checks whether the current ID's attempt count has exceeded `max_refine_count`; if so, append to `recursive-refine-skipped-budget.txt` and route to `dequeue_next` (skip this issue's processing entirely).
- `done` summary shows `Skipped (budget N): IDs...` when applicable.
- Configuration honored via `commands.max_refine_count` in `.ll/ll-config.json`.

## Proposed Solution

1. In `parse_input`, add `printf '' > .loops/tmp/recursive-refine-attempts.txt`.
2. Insert `check_attempt_budget` state between `dequeue_next` and `capture_baseline`:
   ```yaml
   check_attempt_budget:
     action: |
       python3 << 'PYEOF'
       import json, sys
       from pathlib import Path
       issue_id = '${captured.input.output}'
       cfg = {}
       p = Path('.ll/ll-config.json')
       if p.exists():
           try: cfg = json.loads(p.read_text()).get('commands', {})
           except Exception: pass
       cap = cfg.get('max_refine_count', ${context.max_refine_count})
       attempts_file = '.loops/tmp/recursive-refine-attempts.txt'
       try:
           lines = Path(attempts_file).read_text().splitlines()
       except FileNotFoundError:
           lines = []
       count = sum(1 for ln in lines if ln.strip() == issue_id)
       if count >= cap:
           Path('.loops/tmp/recursive-refine-skipped-budget.txt').open('a').write(issue_id + '\n')
           sys.exit(1)  # over budget
       with open(attempts_file, 'a') as f:
           f.write(issue_id + '\n')
       sys.exit(0)
       PYEOF
     fragment: shell_exit
     on_yes: capture_baseline
     on_no: dequeue_next
     on_error: dequeue_next
   ```
3. Update `dequeue_next.on_yes` from `capture_baseline` to `check_attempt_budget`.
4. Extend `done` summary to include the budget-skipped list.

## Acceptance Criteria

- [ ] `context.max_refine_count` is actually consumed by the loop (currently unused).
- [ ] Per-issue attempt count is tracked in a file under `.loops/tmp/`.
- [ ] `check_attempt_budget` skips an issue once its attempts ≥ cap and records reason `budget`.
- [ ] `done` summary includes a `Skipped (budget N): IDs...` line when applicable.
- [ ] Test: a synthetic issue that always fails its sub-loop produces exactly `max_refine_count` attempts and then is budget-skipped.

## Scope Boundaries

- **In scope**: per-issue attempt counter, gate state, summary reporting.
- **Out of scope**: total cost/token budget across the run — that belongs in a separate proposal tied to `ll-loop`'s rate-limit infrastructure.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/recursive-refine.yaml` — `parse_input` (init attempts file), insert `check_attempt_budget` state, rewire `dequeue_next.on_yes`, extend `done`.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/ll_loop.py` — loop runner; consumes the YAML.
- `scripts/tests/test_loops_recursive_refine.py` — must verify the budget cap fires.

### Similar Patterns
- Any FSM gate state with `fragment: shell_exit` and `on_yes` / `on_no` / `on_error` routing — see other states in `recursive-refine.yaml` for the exact convention.

### Tests
- `scripts/tests/test_loops_recursive_refine.py` — new test exercising a synthetic issue that always fails its sub-loop, asserting exactly `max_refine_count` attempts and a `budget` skip.

### Documentation
- `docs/reference/loops/recursive-refine.md` (if present) — document the now-enforced `max_refine_count`.

### Configuration
- `.ll/ll-config.json` — `commands.max_refine_count` already canonical; ensure schema documents it.

## Implementation Steps

1. Initialize `.loops/tmp/recursive-refine-attempts.txt` in `parse_input`.
2. Insert the `check_attempt_budget` gate between `dequeue_next` and `capture_baseline`, reading `commands.max_refine_count` with fallback to `context.max_refine_count`.
3. Rewire `dequeue_next.on_yes` from `capture_baseline` to `check_attempt_budget`.
4. Append the current ID to the attempts file each pass; route to skipped with reason `budget` once count ≥ cap.
5. Extend `done` with a `Skipped (budget N): IDs...` line when the budget skip file is non-empty.
6. Add a synthetic test verifying exact `max_refine_count` attempts before budget skip.

## Impact

- **Priority**: P3 — Adds enforcement to an already-declared but unused config knob; defensive rather than urgent.
- **Effort**: Small — One new gate state plus a one-line `parse_input` change and a one-line `dequeue_next` rewire.
- **Risk**: Low — Default cap (5) is unlikely to trip on healthy issues; trips already imply runaway.
- **Breaking Change**: No — Behavior only diverges for issues that would have looped indefinitely.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`enhancement`, `recursive-refine`, `fsm-loops`, `safety`, `config`

## Status

**Open** | Created: 2026-05-02 | Priority: P3

## References

- `scripts/little_loops/loops/recursive-refine.yaml:27` — `max_refine_count` declaration (currently unused).
- `scripts/little_loops/loops/recursive-refine.yaml:56` (`dequeue_next`) and `:77` (`capture_baseline`) — insertion points.
- 2026 research: [Anthropic Building Effective Agents](https://www.anthropic.com/research/building-effective-agents), [Microsoft CORPGEN](https://www.marktechpost.com/2026/02/26/microsoft-research-introduces-corpgen-to-manage-multi-horizon-tasks-for-autonomous-ai-agents-using-hierarchical-planning-and-memory/).


## Session Log
- `/ll:format-issue` - 2026-05-03T04:41:51 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a41e2fe5-b6da-449b-8d60-6b8ddd06d97c.jsonl`
