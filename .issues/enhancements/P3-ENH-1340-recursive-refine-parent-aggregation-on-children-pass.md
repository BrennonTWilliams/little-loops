---
id: ENH-1340
type: ENH
priority: P3
status: open
discovered_date: 2026-05-02
discovered_by: research-synthesis
related: [ENH-1342]
decision_needed: true
---

# ENH-1340: Aggregate Children's Outcomes Back to Parent in `recursive-refine`

## Summary

When `recursive-refine` decomposes a parent issue, today it moves the parent file to `.issues/completed/` and never revisits it. Once the children pass refinement, there is no rollup step that records "parent X was successfully decomposed into children {A, B, C}, all of which reached ready." The result: future runs (or `analyze-history`, `ll-deps`) cannot easily distinguish "parent decomposed and resolved through children" from "parent abandoned." Add a parent-aggregation step that, when all of a parent's enqueued children later pass, writes a summary record (and optionally re-enriches the completed parent file with a child-outcome footer) so the relationship survives in artifacts.

## Motivation

2026 research on recursive planning explicitly calls out backtracking and aggregation:

- ReCAP: "When a subtask is completed, systems backtrack to its parent task to allow the LLM to refine the higher-level plan based on updated observations" ([ReCAP, Stanford CS224R 2026](https://cs224r.stanford.edu/projects/pdfs/CS224R_RECAP.pdf)).
- Hierarchical agent frameworks (AgentOrchestra) emphasize coordination of specialized sub-agents whose results are unified back at the planner ([AgentOrchestra arXiv 2026](https://arxiv.org/html/2506.12508v1)).
- The "Multi-Agent Trap" failure mode highlights handoffs where parent tasks lose track of child outcomes ([Towards Data Science 2026](https://towardsdatascience.com/the-multi-agent-trap/)).

Today our loop is "fire and forget" at the parent boundary — it loses the parent→children outcome mapping the moment the parent file moves to `completed/`.

## Current Behavior

- `enqueue_children` (line 190) and `enqueue_or_skip` (line 301) both `git mv` the parent file to `.issues/completed/` immediately upon decomposition.
- The parent file already records "Decomposed from $PARENT_ID" in each child via the size-review skill, so the *child→parent* edge survives.
- The reverse edge (parent→children) is not written anywhere durable; it lives only in `.loops/tmp/recursive-refine-new-children.txt` and is overwritten on the next decomposition.
- The `done` summary lists parents under "Skipped" with no annotation of *why* they were skipped or *which* children replaced them.

## Expected Behavior

- A new tracking file `.loops/tmp/recursive-refine-decomposition.tsv` (or `.json`) records every parent→children mapping created during the run, with columns: `parent_id`, `child_ids` (comma-joined), `decomposer` (`sub-loop` | `size-review`), `timestamp`.
- After each `dequeue_next` that exits via `done`, a final aggregation step walks the decomposition file and:
  - For each parent, checks whether *all* of its children appear in `recursive-refine-passed.txt`.
  - If yes: appends a `Parent Aggregation` section to the parent's file in `completed/` listing the child IDs and their final scores.
  - If partial: notes which children passed and which were skipped (with reason).
- `done` summary gains a `Decomposed (N): parent → [children]` block that visually shows the rollup, distinct from leaf passes/skips.

## Proposed Solution — Two Options (decision needed)

### Option A: Lightweight TSV record + summary block only

Add the TSV writer to `enqueue_children` and `enqueue_or_skip`; add a final aggregation pre-`done` state (`aggregate_decomposition`) that prints the rollup but does *not* modify the moved-to-`completed/` parent files. Cheapest, no risk to issue files.

### Option B: Lightweight TSV record + parent-file footer rewrite

Same as A, plus the aggregation state appends a `## Parent Aggregation` markdown section to each parent file in `.issues/completed/` listing child outcomes. Higher value for `analyze-history` / `ll-deps` but introduces a write-after-move on `completed/` files (need to confirm policy).

**Default recommendation**: A first, B as a follow-up only if the rollup proves useful in `analyze-history`. The `decision_needed: true` flag is set so `/ll:decide-issue` evaluates this against codebase conventions.

## Acceptance Criteria

- [ ] `recursive-refine` writes a parent→children record to `.loops/tmp/recursive-refine-decomposition.tsv` (or `.json`) on every decomposition (sub-loop *and* size-review paths).
- [ ] A new `aggregate_decomposition` state runs before `done` and emits a `Decomposed (N)` block in the summary.
- [ ] (Option B only) Each parent file in `completed/` gains a `## Parent Aggregation` section when all children pass.
- [ ] Test: synthetic 1-parent-3-children fixture produces the expected rollup line in `done`.
- [ ] No regression in existing recursive-refine tests.

## Scope Boundaries

- **In scope**: parent→children edge persistence, aggregation pre-summary, summary rollup.
- **Out of scope**: re-evaluating the *parent's* original confidence score after children pass (treating the parent like a meta-issue) — that is a deeper ReCAP-style backtrack and belongs in a future proposal.
- **Out of scope**: cycle detection (ENH-1338), depth caps (ENH-1337), budget caps (ENH-1339) — orthogonal.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/recursive-refine.yaml` — `enqueue_children` and `enqueue_or_skip` (write decomposition record), new `aggregate_decomposition` state pre-`done`, `done` summary block.
- (Option B only) Parent files under `.issues/completed/` — append `## Parent Aggregation` footer.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/ll_loop.py` — loop runner.
- `ll-history` / `ll-deps` (`scripts/little_loops/cli/`) — downstream consumers that benefit from the rollup.
- `/ll:analyze-history` and `/ll:assess-loop` skills — likely future readers of the decomposition record.

### Similar Patterns
- Other loops that write `.loops/tmp/` artifacts during run and consume them at `done` (e.g., other queue-based FSMs).

### Tests
- `scripts/tests/test_loops_recursive_refine.py` — synthetic 1-parent-3-children fixture asserting the `Decomposed (N)` line and (Option B) the parent footer.

### Documentation
- `docs/reference/loops/recursive-refine.md` (if present) — document the decomposition record schema.

### Configuration
- N/A — record file path lives under `.loops/tmp/`; no new config keys.

## Implementation Steps

1. Decide between Option A (TSV + summary only) and Option B (TSV + parent-file footer rewrite) via `/ll:decide-issue`.
2. Add a TSV/JSON writer to `enqueue_children` and `enqueue_or_skip` capturing `parent_id`, `child_ids`, `decomposer`, `timestamp`.
3. Add a new `aggregate_decomposition` state run before `done` that walks the record file and computes the rollup.
4. Extend `done` summary with the `Decomposed (N): parent → [children]` block.
5. (Option B only) Append `## Parent Aggregation` to the parent file under `.issues/completed/` when all children pass.
6. Add the synthetic 1-parent-3-children test fixture.

## Impact

- **Priority**: P3 — Improves observability and downstream tooling but no current outage; valuable for `analyze-history` once adopted.
- **Effort**: Medium — Option A is small; Option B adds write-after-move semantics on `completed/` files which need a policy check.
- **Risk**: Low (Option A) / Medium (Option B) — Option B mutates committed-history files; mitigation is to gate with a config flag and stage atomically.
- **Breaking Change**: No — Additive record file plus new summary block.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`enhancement`, `recursive-refine`, `fsm-loops`, `observability`

## Status

**Open** | Created: 2026-05-02 | Priority: P3

## References

- `scripts/little_loops/loops/recursive-refine.yaml`: `enqueue_children` (line 190), `enqueue_or_skip` (line 301), `done` (line 350).
- 2026 research: [ReCAP Stanford CS224R](https://cs224r.stanford.edu/projects/pdfs/CS224R_RECAP.pdf), [AgentOrchestra](https://arxiv.org/html/2506.12508v1), [The Multi-Agent Trap](https://towardsdatascience.com/the-multi-agent-trap/).


## Session Log
- `/ll:format-issue` - 2026-05-03T04:41:51 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a41e2fe5-b6da-449b-8d60-6b8ddd06d97c.jsonl`
