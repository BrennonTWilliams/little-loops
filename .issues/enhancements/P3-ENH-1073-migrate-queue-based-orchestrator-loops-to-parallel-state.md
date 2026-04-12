---
discovered_date: "2026-04-12"
discovered_by: capture-issue
depends_on: [FEAT-1072]
---

# ENH-1073: Migrate Queue-Based Orchestrator Loops to `parallel:` State

## Summary

Restructure the 6 queue-based orchestrator loops to replace their sequential dequeue→sub-loop→loop-back patterns with wave-based concurrent fan-out using the `parallel:` state type (FEAT-1072). Each loop processes its current generation of items in parallel, collects children or results, then fans out the next generation until the queue is empty.

## Current Behavior

Six orchestrator loops process items one at a time using a sequential queue pattern:

1. **recursive-refine**: dequeue one issue → run `refine-to-ready-issue` sub-loop → detect children → enqueue children → repeat
2. **sprint-refine-and-implement**: dequeue sprint issue → run `recursive-refine` → run implementation sub-loop → repeat
3. **auto-refine-and-implement**: dequeue backlog issue → run `recursive-refine` → implement → repeat
4. **harness-multi-item**: dequeue eval item → run through evaluation gates → repeat
5. **prompt-across-issues**: dequeue issue → run prompt → repeat
6. **outer-loop-eval**: sequential evaluation passes over loop definitions

Each loop pays full serial cost: N items × average item duration = total wall-clock time.

## Expected Behavior

Each loop is restructured to use a wave-based model:

```yaml
# recursive-refine (restructured)
states:
  parse_input:
    # unchanged — builds initial generation queue
    next: fan_out

  fan_out:
    parallel:
      items: "${captured.current_gen.output}"
      loop: refine-to-ready-issue
      max_workers: 4
      isolation: worktree
      fail_mode: collect
      context_passthrough: true
    route:
      on_yes: collect_children
      on_partial: collect_children
      on_no: done

  collect_children:
    # shell: diff issue IDs pre/post, gather children from all workers
    # exit 0 if next generation exists, 1 if done
    on_yes: fan_out    # next generation
    on_no: done

  done:
    terminal: true
```

Wall-clock time becomes: ceil(N / max_workers) × average_item_duration instead of N × duration.

## Motivation

Queue-based loops are the slowest operations in the ll system. `recursive-refine` over 10 issues with 4 workers runs in ~3 serial issue durations instead of 10. `sprint-refine-and-implement` over a 6-issue sprint drops proportionally. The `parallel:` state type (FEAT-1072) makes this restructuring straightforward — each loop's queue management becomes a wave counter rather than a serial cursor. Without this migration, FEAT-1072 provides infrastructure with no loops using it.

## Proposed Solution

For each loop, the migration follows a consistent pattern:

1. Rename/repurpose the queue management states: `parse_input` stays, `dequeue_next` → `fan_out` (parallel state), `loop_back` removed
2. Replace the `loop:` sub-loop delegation state with a `parallel:` state pointing at the same sub-loop
3. Add a `collect_children` (or `collect_results`) state that aggregates all worker outputs and determines whether a next generation exists
4. The `detect_children` / `enqueue_children` states in recursive-refine collapse into `collect_children` since all workers' outputs are available simultaneously

**Isolation mode by loop:**
- `recursive-refine`, `sprint-refine-and-implement`, `auto-refine-and-implement`: `isolation: worktree` (write issue files)
- `harness-multi-item`: `isolation: worktree` (writes test reports)
- `prompt-across-issues`: `isolation: thread` (read-only — only loop confirmed as non-writing in survey)
- `outer-loop-eval`: `isolation: thread` (analysis/read-heavy)

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/recursive-refine.yaml`
- `scripts/little_loops/loops/sprint-refine-and-implement.yaml`
- `scripts/little_loops/loops/auto-refine-and-implement.yaml`
- `scripts/little_loops/loops/harness-multi-item.yaml`
- `scripts/little_loops/loops/prompt-across-issues.yaml`
- `scripts/little_loops/loops/outer-loop-eval.yaml`

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/run.py` — No changes; loops run via standard `ll-loop` CLI
- Any loop YAML that uses these as sub-loops (e.g., `sprint-refine-and-implement` calls `recursive-refine`) — may need `context_passthrough` review

### Similar Patterns
- All 6 loops share the same sequential dequeue pattern — one refactor template applies to all
- `harness-single-shot.yaml` — leaf loop used by `harness-multi-item`; no changes needed

### Tests
- Integration tests for each restructured loop (if any exist in `scripts/tests/loops/`)
- Manual validation: run each restructured loop on a small input set and verify wave-based execution in event logs

### Documentation
- `docs/ARCHITECTURE.md` — Update loop examples to show `parallel:` state usage
- Loop YAML files are self-documenting via state names and comments

### Configuration
- N/A

## Implementation Steps

1. Implement and validate FEAT-1072 (`parallel:` state type) — prerequisite
2. Restructure `recursive-refine.yaml` first (most complex; establishes the wave-based pattern)
3. Restructure `sprint-refine-and-implement.yaml` and `auto-refine-and-implement.yaml` (similar queue patterns)
4. Restructure `harness-multi-item.yaml` (eval-focused, slightly different child collection logic)
5. Restructure `prompt-across-issues.yaml` and `outer-loop-eval.yaml` (simpler — thread isolation, no child collection)
6. Validate each restructured loop with a small input set; confirm event logs show parallel worker dispatch

## Success Metrics

- `recursive-refine` over N issues completes in ≤ ceil(N / max_workers) × single-issue duration (±10% for merge overhead)
- All 6 loops produce identical output to their sequential predecessors on the same inputs
- No regressions in child issue discovery (recursive-refine's decomposition tree must be fully explored)

## Scope Boundaries

- Does not restructure sequential pipeline orchestrators (backlog-flow-optimizer, issue-discovery-triage, greenfield-builder) — these have inter-stage dependencies that prevent fan-out
- Does not change leaf loops (refine-to-ready-issue, fix-quality-and-tests, etc.) — they are the sub-loops being fanned out
- Does not add `max_workers` to `ll-config.json` at this stage — loops use hardcoded defaults initially; config wiring is a follow-on

## Impact

- **Priority**: P3 — High value but blocked on FEAT-1072; no user-visible benefit until the primitive exists
- **Effort**: Medium — Each loop follows the same restructuring template; `recursive-refine` is the hardest; others are mechanical
- **Risk**: Low — YAML-only changes to loop configs; FSM engine is unchanged; rollback is trivial (revert YAML files)
- **Breaking Change**: No — same loop names and interfaces; behavioral change is faster execution, not different outcomes

## Related Key Documentation

| Document | Relevance |
|---|---|
| [docs/ARCHITECTURE.md](../../docs/ARCHITECTURE.md) | FSM loop execution model and orchestrator loop patterns |

`fsm`, `loops`, `parallel`, `orchestrator`, `recursive-refine`, `sprint`

---

## Session Log
- `/ll:capture-issue` - 2026-04-12T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c305cac4-c25e-482f-86f7-9adf26df1b0e.jsonl`

---

**Open** | Created: 2026-04-12 | Priority: P3
