---
id: ENH-1341
type: ENH
priority: P3
status: open
discovered_date: 2026-05-02
discovered_by: research-synthesis
related: [ENH-1340]
decision_needed: false
---

# ENH-1341: Render Decomposition Tree in `recursive-refine` `done` Summary

## Summary

`recursive-refine`'s `done` state emits two flat lists (passed, skipped) but no structural view of *how* the work decomposed. With moderately deep runs (root → children → grandchildren), the user has no easy way to see "ENH-1100 was split into ENH-1200/1201, and ENH-1201 further split into ENH-1300/1301." Render an indented tree (or simple `parent → [children]` adjacency block) at the end of the run, sourced from the decomposition record proposed in ENH-1340.

## Motivation

2026 research on long-horizon agents converges on observability — particularly *structured* observability over flat logs — as a precondition for trusting agent autonomy:

- "From Agent Loops to Structured Graphs" argues for explicit structured-graph framing of agent execution to enable post-hoc analysis ([arXiv 2604.11378, 2026](https://arxiv.org/html/2604.11378v1)).
- The 2026 multi-agent failure literature emphasizes that without structural visibility, "loop drift" and "procedural drift" go undetected ([fixbrokenaiapps 2026](https://www.fixbrokenaiapps.com/blog/ai-agents-infinite-loops); [Cogent 2026](https://cogentinfo.com/resources/when-ai-agents-collide-multi-agent-orchestration-failure-playbook-for-2026)).
- This is also the natural input for `/ll:assess-loop` and `/ll:analyze-loop` — they currently operate on event history, not on decomposition shape.

A flat skip list buries the difference between "abandoned" and "successfully decomposed."

## Current Behavior

- `done` (line 350) prints:
  ```
  Passed  (N): ID1,ID2,...
  Skipped (M): ID3,ID4,...
  ```
- No parent-child relationships rendered.
- A reader looking at `Skipped: ENH-1100` cannot tell whether it was abandoned or decomposed into the issues that appear in `Passed`.

## Expected Behavior

- `done` emits an additional block:
  ```
  === Decomposition Tree ===
  ENH-1100 [decomposed by size-review]
    ├── ENH-1200 (passed, conf=92, outcome=78)
    └── ENH-1201 [decomposed by sub-loop]
          ├── ENH-1300 (passed, conf=95, outcome=82)
          └── ENH-1301 (skipped: budget)
  ENH-1102 (passed, conf=91, outcome=80)
  ```
- Roots that were not decomposed appear as single lines.
- Decomposed parents appear with their reason in brackets and an indented child list.
- Final scores pulled from `ll-issues show <id> --json`.
- If ENH-1340 (decomposition record) is not yet implemented, fall back to reconstructing the tree from `recursive-refine-original-queue.txt`, `recursive-refine-passed.txt`, `recursive-refine-skipped.txt`, and a one-pass `find .issues -path '*completed/*' -name '*-<parent>-*'` lookup using the `Decomposed from` annotation.

## Proposed Solution

1. Depend on ENH-1340 ideally — read its `recursive-refine-decomposition.tsv` to drive the tree.
2. Add a python helper inline in `done`'s action body that:
   - Loads the original queue (roots).
   - Loads passed/skipped IDs and their reasons.
   - Loads the decomposition record (or reconstructs from `Decomposed from` annotations).
   - Walks each root depth-first, emitting indented lines.
   - Calls `ll-issues show <id> --json` for each leaf to fetch confidence/outcome scores.
3. Place the tree block *between* the existing `Passed` / `Skipped` summary and the closing newline, gated behind a context flag `tree_summary: true` (default true) so it can be disabled for noisy multi-root runs.

## Acceptance Criteria

- [ ] `done` summary now includes a `=== Decomposition Tree ===` block by default.
- [ ] Roots without children render as a single line with their final scores.
- [ ] Decomposed parents render with their reason and indented children.
- [ ] Leaf entries show `(passed, conf=X, outcome=Y)` or `(skipped: <reason>)`.
- [ ] Falls back gracefully when no decomposition occurred (omits the block, or shows roots-only).
- [ ] `context.tree_summary: false` disables the block.
- [ ] Test: synthetic run with 1 root that decomposes into 2 children (one of which decomposes further) produces a 3-level tree.

## Scope Boundaries

- **In scope**: textual tree rendering at end of run, scoring annotations, on/off flag.
- **Out of scope**: graphical (mermaid) rendering — mermaid output belongs in a follow-up if/when `/ll:assess-loop` consumes the tree.
- **Out of scope**: streaming the tree during the run (only at `done`).

## Depends On

- ENH-1340 — decomposition record file is the cleanest input. Without it the tree can be reconstructed from `Decomposed from` annotations, but with higher cost.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/recursive-refine.yaml` — extend `done` action body with the tree renderer and add `tree_summary` flag to `context:`.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/ll_loop.py` — loop runner; consumes the YAML.
- `ll-issues show <id> --json` (`scripts/little_loops/cli/ll_issues.py`) — used to fetch confidence/outcome scores at render time.
- `/ll:assess-loop` and `/ll:analyze-loop` skills — likely future consumers of the rendered tree.

### Similar Patterns
- Other loop `done`-state renderers under `scripts/little_loops/loops/*.yaml` that emit structured summaries.

### Tests
- `scripts/tests/test_loops_recursive_refine.py` — synthetic 3-level run (1 root → 2 children, one of which decomposes) asserting tree shape and leaf annotations.

### Documentation
- `docs/reference/loops/recursive-refine.md` (if present) — document the tree summary block and `tree_summary` toggle.

### Configuration
- N/A — `tree_summary` lives in the loop's `context:`; no `.ll/ll-config.json` change required.

## Implementation Steps

1. Confirm dependency on ENH-1340's decomposition record (or implement the fallback reconstruction path if not yet available).
2. Add `tree_summary: true` to `recursive-refine.yaml` `context:`.
3. Extend the `done` state's action body with a Python helper that loads roots / passed / skipped / decomposition record and walks each root depth-first.
4. Fetch leaf scores via `ll-issues show <id> --json`.
5. Emit the tree block between the existing `Passed` / `Skipped` lines and the closing newline.
6. Honor `tree_summary: false` to disable the block.
7. Add the synthetic 3-level test fixture.

## Impact

- **Priority**: P3 — Pure observability win; raises the floor for trusting recursive runs.
- **Effort**: Small — One inline Python helper in `done`; reuses existing tracking files.
- **Risk**: Low — Output-only change; flag-gated for noisy runs.
- **Breaking Change**: No — Additive summary block.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`enhancement`, `recursive-refine`, `fsm-loops`, `observability`

## Status

**Open** | Created: 2026-05-02 | Priority: P3

## References

- `scripts/little_loops/loops/recursive-refine.yaml:350` (`done` state).
- 2026 research: [Structured Graphs for Agent Execution](https://arxiv.org/html/2604.11378v1), [AI Agent Loops research](https://www.fixbrokenaiapps.com/blog/ai-agents-infinite-loops).


## Session Log
- `/ll:format-issue` - 2026-05-03T04:41:51 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a41e2fe5-b6da-449b-8d60-6b8ddd06d97c.jsonl`
