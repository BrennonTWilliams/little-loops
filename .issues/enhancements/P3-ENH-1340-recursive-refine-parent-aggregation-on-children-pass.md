---
id: ENH-1340
type: ENH
priority: P3
status: completed
discovered_date: 2026-05-02
completed_at: 2026-05-03T19:06:45Z
discovered_by: research-synthesis

- ENH-1342
decision_needed: false
confidence_score: 100
outcome_confidence: 86
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 18
relates_to: ['ENH-1342']
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

- `enqueue_children` (line 243) and `enqueue_or_skip` (line 417) both `git mv` the parent file to `.issues/completed/` immediately upon decomposition.
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

> **Selected:** Option A — Directly extends the established write-during-run/read-at-done idiom already used in `recursive-refine.yaml`; zero risk to completed files; one-edge wiring redirect.

Add the TSV writer to `enqueue_children` and `enqueue_or_skip`; add a final aggregation pre-`done` state (`aggregate_decomposition`) that prints the rollup but does *not* modify the moved-to-`completed/` parent files. Cheapest, no risk to issue files.

### Option B: Lightweight TSV record + parent-file footer rewrite

Same as A, plus the aggregation state appends a `## Parent Aggregation` markdown section to each parent file in `.issues/completed/` listing child outcomes. Higher value for `analyze-history` / `ll-deps` but introduces a write-after-move on `completed/` files (need to confirm policy).

**Default recommendation**: A first, B as a follow-up only if the rollup proves useful in `analyze-history`. The `decision_needed: true` flag is set so `/ll:decide-issue` evaluates this against codebase conventions.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-05-03.

**Selected**: Option A: Lightweight TSV record + summary block only

**Reasoning**: Option A directly extends the write-during-run/read-at-done idiom already established in `recursive-refine.yaml` (`passed.txt`, `skipped.txt`, `queue.txt`), with a direct precedent in `autodev.yaml`'s three-artifact `done` reader. Option B is eliminated because no existing code modifies files in `completed/` after the initial move, and neither `analyze-history` nor `ll-deps` reads completed file bodies in a structured way — the footer would provide no concrete value without additional new infrastructure in `CompletedIssue`/`parse_completed_issue`.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option A | 3/3 | 3/3 | 2/3 | 3/3 | 11/12 |
| Option B | 1/3 | 1/3 | 1/3 | 1/3 | 4/12 |

**Key evidence**:
- **Option A**: `recursive-refine.yaml` already initializes `passed.txt`/`skipped.txt`/`queue.txt` in `parse_input` and reads them in `done`; `dequeue_next`'s `on_no: done` edge is the only wiring change needed; `auto-refine-and-implement.yaml` reads `recursive-refine-passed.txt` confirming the tmp files are a stable inter-loop interface.
- **Option B**: `issue_lifecycle.py:_move_issue_to_completed()` writes content once at move time — no post-move writes exist anywhere; `ll-deps` reads only filenames from `completed/`; `analyze-history` parses only frontmatter fields and undifferentiated body text — a `## Parent Aggregation` section would require new `CompletedIssue` model fields and parsing logic to be useful.

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
- `scripts/little_loops/loops/recursive-refine.yaml` — four touch points:
  1. `parse_input` (L34): add `printf '' > .loops/tmp/recursive-refine-decomposition.tsv` alongside the other `printf ''` initializers.
  2. `enqueue_children` (L243): append TSV row after the depth-map loop (`decomposer=sub-loop`).
  3. `enqueue_or_skip` (L417): append TSV row in the branch where new children exist (`decomposer=size-review`).
  4. `dequeue_next` (L66): change `on_no: done` → `on_no: aggregate_decomposition` (queue-empty edge now routes through the new aggregation state).
- New state `aggregate_decomposition` (insert before `done`): `action_type: shell`, `next: done`, `on_error: done`. Reads `recursive-refine-decomposition.tsv`, cross-references `recursive-refine-passed.txt`, emits `Decomposed (N): parent → [children]` block.
- (Option B only — not in scope) Parent files under `.issues/completed/` — append `## Parent Aggregation` footer.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/ll_loop.py` — loop runner.
- `ll-history` / `ll-deps` (`scripts/little_loops/cli/`) — downstream consumers that benefit from the rollup.
- `/ll:analyze-history` and `/ll:assess-loop` skills — likely future readers of the decomposition record.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/loops/auto-refine-and-implement.yaml` — calls `recursive-refine` as sub-loop; reads `recursive-refine-passed.txt` and `recursive-refine-skipped.txt` in `get_passed_issues` state — no modification needed for Option A, but will benefit from the new `Decomposed (N):` block in the summary [Agent 1 finding]
- `scripts/little_loops/loops/sprint-refine-and-implement.yaml` — same pattern as `auto-refine-and-implement.yaml`; reads `recursive-refine-passed.txt` and `recursive-refine-skipped.txt` in `get_passed_issues` state [Agent 1 finding]
- `scripts/little_loops/loops/sprint-build-and-validate.yaml` — calls `recursive-refine` sub-loop in `refine_unresolved` state; does not read tmp artifacts directly [Agent 1 finding]

### Similar Patterns
- `scripts/little_loops/loops/harness-optimize.yaml:write_trajectory_accepted` (L121) — per-iteration `echo '{"field":...}' >> file.jsonl` pattern; `load_directive` (L24) reads it back. Closest precedent for structured in-state record writing.
- `scripts/little_loops/loops/autodev.yaml:done` (L459) — three-artifact done reader (`autodev-passed.txt`, `autodev-skipped.txt`, `autodev-inflight`); exact model for how `aggregate_decomposition` should read `decomposition.tsv` alongside existing tracking files.
- `scripts/little_loops/loops/auto-refine-and-implement.yaml:get_passed_issues` (L49) — reads `recursive-refine-passed.txt` confirming `.loops/tmp/` files are a stable inter-loop interface; `decomposition.tsv` will be similarly stable.

### Tests
- `scripts/tests/test_loops_recursive_refine.py` — add `TestAggregateDecomposition` following the `TestDoneSummary` pattern: define `_AGGREGATE_SCRIPT` class constant (the `aggregate_decomposition` state's action body), write synthetic `.loops/tmp/recursive-refine-decomposition.tsv` + `recursive-refine-passed.txt` fixtures, call `_bash(self._AGGREGATE_SCRIPT, tmp_path)`, assert `Decomposed (N):` in stdout. Model the 1-parent-3-children fixture after `test_decomposition_tree_three_levels` (L822) which already creates stub issue files with `parent_issue:` frontmatter.
- `scripts/tests/test_enh1341_doc_wiring.py` — doc-wiring style: assert that `recursive-refine-decomposition.tsv` (or `Decomposed`) appears in `docs/guides/LOOPS_GUIDE.md` after the guide is updated.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_builtin_loops.py` — `TestRecursiveRefineLoop` needs updating and new tests: (1) update `test_required_states_exist` (L1612) to include `"aggregate_decomposition"` in the required set; (2) add `test_dequeue_next_on_no_routes_to_aggregate_decomposition` following `test_dequeue_next_routes_to_check_attempt_budget` (L1651) pattern; (3) add `test_aggregate_decomposition_state_exists` and `test_aggregate_decomposition_routes_to_done` — these are the CI gate tests that will catch partial wiring [Agent 3 finding]
- `scripts/tests/test_loops_recursive_refine.py` — optionally add `test_decomposition_tsv_initialized_empty` to `TestDepthMapInit` (following `test_visited_file_created_empty_by_parse_input` at L89) to cover the new `printf '' > .loops/tmp/recursive-refine-decomposition.tsv` in `parse_input` [Agent 3 finding]

### Documentation
- `docs/reference/loops/recursive-refine.md` (if present) — document the decomposition record schema.

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_GUIDE.md` — three specific sections need updating: (1) **FSM flow diagram** — the `dequeue_next` queue-empty branch currently shows `YES → done`; must become `YES → aggregate_decomposition → done`; (2) **Summary output code block** — add `Decomposed (N): parent_id → [child_ids]` line to the `=== Recursive Refine Summary ===` example; (3) **Notes/artifact inventory paragraph** — add `recursive-refine-decomposition.tsv` alongside the existing `.loops/tmp/` artifact list [Agent 2 finding]

### Configuration
- N/A — record file path lives under `.loops/tmp/`; no new config keys.

## Implementation Steps

1. In `recursive-refine.yaml:parse_input` (L34), add `printf '' > .loops/tmp/recursive-refine-decomposition.tsv` alongside the existing `printf ''` initializers.
2. In `enqueue_children` (L243), after the depth-map while-loop and before the `skipped.txt` append, add:
   ```bash
   CHILD_IDS=$(cat .loops/tmp/recursive-refine-new-children.txt | tr '\n' ',' | sed 's/,$//')
   printf '%s\t%s\t%s\t%s\n' "${captured.input.output}" "$CHILD_IDS" "sub-loop" \
     "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >> .loops/tmp/recursive-refine-decomposition.tsv
   ```
3. In `enqueue_or_skip` (L417), in the branch where new children exist (after prepending to queue), add the same snippet with `"size-review"` as the `decomposer` field.
4. Add a new `aggregate_decomposition` state immediately before `done` in the YAML. Structure: `action_type: shell`, `next: done`, `on_error: done`. Body: reads `decomposition.tsv` with `python3 << 'PYEOF'` (following the `read_ids` helper pattern from `done` L528), cross-checks each parent's child_ids against `recursive-refine-passed.txt`, prints `Decomposed (N): parent_id → [child_ids]` blocks.
5. In `dequeue_next` (L66): change `on_no: done` → `on_no: aggregate_decomposition`.
6. Add `TestAggregateDecomposition` to `scripts/tests/test_loops_recursive_refine.py` following the `TestDoneSummary._DONE_SCRIPT` pattern (L602); include a 1-parent-3-children fixture extending `test_decomposition_tree_three_levels` (L822).
7. Update `docs/guides/LOOPS_GUIDE.md` to document the `recursive-refine-decomposition.tsv` artifact schema (`parent_id`, `child_ids`, `decomposer`, `timestamp`). Update three sections: (a) FSM flow diagram — `dequeue_next YES` branch → `aggregate_decomposition → done`; (b) summary output code block — add `Decomposed (N):` line; (c) Notes artifact inventory — append `recursive-refine-decomposition.tsv`.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

8. Update `scripts/tests/test_builtin_loops.py` — `TestRecursiveRefineLoop`: (a) in `test_required_states_exist` (L1612) add `"aggregate_decomposition"` to the required-states set; (b) add `test_dequeue_next_on_no_routes_to_aggregate_decomposition` following the `test_dequeue_next_routes_to_check_attempt_budget` (L1651) pattern; (c) add `test_aggregate_decomposition_state_exists` and `test_aggregate_decomposition_routes_to_done` — these are the CI gate tests enforced by `test_all_validate_as_valid_fsm`

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

- `scripts/little_loops/loops/recursive-refine.yaml`: `parse_input` (L34), `dequeue_next` (L66), `check_attempt_budget` (L90), `check_passed` (L161), `enqueue_children` (L243), `enqueue_or_skip` (L417), `done` (L495).
- 2026 research: [ReCAP Stanford CS224R](https://cs224r.stanford.edu/projects/pdfs/CS224R_RECAP.pdf), [AgentOrchestra](https://arxiv.org/html/2506.12508v1), [The Multi-Agent Trap](https://towardsdatascience.com/the-multi-agent-trap/).

## Resolution

**Implemented Option A** (Lightweight TSV record + summary block only):

1. `parse_input` — added `printf '' > .loops/tmp/recursive-refine-decomposition.tsv` alongside existing initializers
2. `dequeue_next` — changed `on_no: done` → `on_no: aggregate_decomposition`
3. `enqueue_children` — appends TSV row (`parent_id`, `child_ids`, `sub-loop`, timestamp) after the depth-map loop
4. `enqueue_or_skip` — appends TSV row (`parent_id`, `child_ids`, `size-review`, timestamp) in the new-children branch
5. New `aggregate_decomposition` state (before `done`) — reads `decomposition.tsv`, cross-references `passed.txt`, emits `Decomposed (N):` rollup block
6. Tests: `TestAggregateDecomposition` in `test_loops_recursive_refine.py` (6 tests) + 4 structural tests in `test_builtin_loops.py`
7. `docs/guides/LOOPS_GUIDE.md` — updated FSM diagram, summary output block, and Notes artifact inventory

All 5719 existing tests pass; no regressions.

## Session Log
- `/ll:manage-issue` - 2026-05-03T19:06:45Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fff9609e-8a5a-401a-87db-430505c5cf93.jsonl`
- `/ll:ready-issue` - 2026-05-03T18:55:39 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/7da1944d-01d6-4fca-b44a-5775f0f10d9c.jsonl`
- `/ll:confidence-check` - 2026-05-03T19:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b878886c-4bc9-4c7f-95d3-69139a14c562.jsonl`
- `/ll:wire-issue` - 2026-05-03T18:51:01 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8d6eb746-1937-4f45-bb7f-14d33480c49e.jsonl`
- `/ll:refine-issue` - 2026-05-03T18:44:11 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/43e7aad3-fda0-46c1-a704-aaadd35a6011.jsonl`
- `/ll:decide-issue` - 2026-05-03T15:27:53 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/46210245-3b62-4920-b3d0-c0a713e429eb.jsonl`
- `/ll:verify-issues` - 2026-05-03T15:20:54 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8fe967ae-751c-4941-ab43-61b0cce639c5.jsonl`
- `/ll:format-issue` - 2026-05-03T04:41:51 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a41e2fe5-b6da-449b-8d60-6b8ddd06d97c.jsonl`
