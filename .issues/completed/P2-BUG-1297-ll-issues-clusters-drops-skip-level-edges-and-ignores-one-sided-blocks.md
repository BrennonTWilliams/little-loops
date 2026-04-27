---
captured_at: "2026-04-26T23:28:16Z"
completed_at: "2026-04-27T00:39:27Z"
discovered_date: 2026-04-26
discovered_by: capture-issue
decision_needed: false
confidence_score: 100
outcome_confidence: 82
score_complexity: 25
score_test_coverage: 22
score_ambiguity: 25
score_change_surface: 10
---

# BUG-1297: `ll-issues clusters` drops skip-level edges and ignores one-sided `blocks:` declarations

## Summary

Two bugs in `ll-issues clusters` produce incomplete dependency diagrams. First, `_render_cluster_diagram()` only inspects consecutive node pairs in topological order, silently omitting any edge where the source and target are non-adjacent (fan-out, fan-in, diamond). Second, `DependencyGraph.from_issues()` only processes `issue.blocked_by`, so edges declared only via `blocks:` frontmatter (without a matching `blocked_by:` on the target) are never added to the graph.

## Current Behavior

Two defects in `ll-issues clusters` produce incomplete dependency diagrams:

1. **Skip-level edges silently omitted**: `_render_cluster_diagram()` iterates only consecutive node pairs in topological order via `range(n-1)`, checking `(ordered_ids[i], ordered_ids[i+1])`. Edges in `edge_map` between non-adjacent nodes (fan-out, fan-in, diamond patterns) exist in the map but are never rendered.

2. **One-sided `blocks:` declarations ignored**: `DependencyGraph.from_issues()` only processes `issue.blocked_by`. If issue A declares `blocks: [B]` without a matching `blocked_by: [A]` on issue B, the A→B edge is never added to `graph.blocks` and is absent from both text and JSON output.

## Expected Behavior

1. All edges in `edge_map` appear in the cluster diagram. Non-consecutive (skip-level) edges are rendered with clear annotations below the existing grid diagram.

2. `blocks:` declarations are treated as the symmetric counterpart of `blocked_by:` — if issue A declares `blocks: [B]`, the A→B edge is added to the dependency graph regardless of whether B has a corresponding `blocked_by: [A]`.

## Context

Identified from plan `~/.claude/plans/ll-issues-clusters-cli-output-synthetic-parasol.md`, which provides detailed root cause analysis, worked examples, and a complete fix specification.

## Root Cause

### Root Cause 1 — Rendering drops non-consecutive edges (`clusters.py:143-155`)

`_render_cluster_diagram()` iterates `range(n - 1)` and checks only the pair `(ordered_ids[i], ordered_ids[i+1])`. Edges between non-adjacent nodes exist in `edge_map` but are never rendered.

**Example (fan-out):**
- Issues: A, B, C; edges: A→B, A→C; topo order: [A, B, C]
- `edge_map`: `{(A,B): "blocks", (A,C): "blocks"}`
- Loop checks (A,B) → renders ✓; checks (B,C) → no edge (correct); A→C silently omitted ✗

Affects any cluster with branching: fan-out, fan-in, or diamond shapes.

**File:** `scripts/little_loops/cli/issues/clusters.py:143-155`

### Root Cause 2 — `from_issues()` ignores `issue.blocks` (`dependency_graph.py:93-108`)

`DependencyGraph.from_issues()` only iterates `issue.blocked_by`. If an issue declares a relationship via `blocks:` without a corresponding `blocked_by:` on the target, the edge is never added to `graph.blocks`. Since `_cluster_edges()` only reads `graph.blocks`, those edges are completely absent from both text and JSON output.

**File:** `scripts/little_loops/dependency_graph.py:93-108`

## Steps to Reproduce

**Bug 1 (skip-level edges):** Create three issues where A blocks both B and C. Run `ll-issues clusters`. The A→C edge is absent from the diagram even though it exists in `edge_map`.

**Bug 2 (one-sided `blocks:`):** Create issue A with `blocks: [B]` in frontmatter but no `blocked_by:` on issue B. Run `ll-issues clusters`. The A→B edge is missing entirely from both text and JSON output.

## Proposed Solution

### Fix 1 — Append skip-edge annotations below the diagram

After the existing grid rendering in `_render_cluster_diagram()`, compute a `pos` mapping from id → sorted index. Find all edges in `edge_map` where `pos[t] - pos[f] > 1` (skip edges). Append them as annotated lines:

```python
# After: while lines and not lines[-1].strip(): lines.pop()
pos = {id_: i for i, id_ in enumerate(ordered_ids)}
skip_edges = [
    (f, t, r)
    for (f, t), r in sorted(edge_map.items())
    if pos[t] - pos[f] > 1
]
if skip_edges:
    lines.append("")
    for f, t, r in skip_edges:
        color = EDGE_COLOR.get(r, "37")
        lines.append(f"  {f} {colorize('→', color)} {t}  ({r})")
```

The existing consecutive-arrow grid is unchanged; skip-level edges get a clear text listing below the diagram.

### Fix 2 — Process `issue.blocks` in `from_issues()`

After the existing `blocked_by` loop (line 108), add a second loop over `issue.blocks` with a guard to avoid double-adding symmetrically declared edges:

```python
for issue in issues:
    for blocked_id in issue.blocks:
        if blocked_id in completed:
            continue
        if blocked_id not in all_issue_ids:
            if all_known_ids is None or blocked_id not in all_known_ids:
                logger.warning(
                    f"Issue {issue.issue_id} blocks unknown issue {blocked_id}"
                )
            continue
        if issue.issue_id not in graph.blocked_by.get(blocked_id, set()):
            graph.blocked_by[blocked_id].add(issue.issue_id)
            graph.blocks[issue.issue_id].add(blocked_id)
```

### Fix 3 — Add fan-out rendering test

Add a test in `scripts/tests/test_issues_cli.py` (after `test_clusters_no_arrows_between_independent_roots`, line 3438) asserting that a fan-out cluster (A blocks B and A blocks C) shows both edge annotations in text output.

**Important**: A new fixture is required — do NOT reuse `issues_dir_multi_root`. That fixture models a fan-IN topology (BUG-010→BUG-012 and BUG-011→BUG-012: two independent roots both blocking one child). The skip-level edge bug only occurs with a single source that has multiple targets (fan-OUT). The new fixture should create:
- Issue A declaring `## Blocks\n- B\n- C\n` (or `## Blocks` for both B and C)
- Issues B and C with no further `blocks:` / `blocked_by:` between them

The test should assert that both the A→B and A→C annotations appear in the rendered text output after the fix.

**Codebase Research Findings**

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `EDGE_COLOR` and `colorize` are both in scope inside `_render_cluster_diagram()` — `EDGE_COLOR` at `clusters.py:17-22`, `colorize` imported at `clusters.py:9`
- Fix 1 insertion anchor: insert the `pos`/`skip_edges` block after `lines.pop()` at `clusters.py:166`, immediately before `return lines` at `clusters.py:168`
- `graph.blocked_by` is a plain `dict[str, set[str]]` (not `defaultdict`), but it IS pre-populated for all input issues in lines 86-89 — the `.get(blocked_id, set())` guard in Fix 2 handles IDs that might not be pre-populated (e.g., cross-worktree references)
- Fix 2 variable `blocked_id` refers to the *blockee* (the issue being blocked by `issue`); this is the inverse of the outer `blocker_id` loop's semantics — naming is consistent within each loop

## Implementation Steps

1. Apply Fix 1 in `scripts/little_loops/cli/issues/clusters.py:165-168` — insert `pos`/`skip_edges` block after `lines.pop()` on line 166, before `return lines`
2. Apply Fix 2 in `scripts/little_loops/dependency_graph.py:108-110` — add second `issue.blocks` loop after the `blocked_by` loop ending at line 108, before `return graph`
3. Add fan-out rendering test in `scripts/tests/test_issues_cli.py` after line 3438 — requires a new fixture with single-source-multi-target topology (NOT `issues_dir_multi_root`, which is fan-IN)
4. Add `from_issues()` unit test in `scripts/tests/test_dependency_graph.py` — one-sided `blocks:` produces edge in `graph.blocks` without a matching `blocked_by:` on the target
5. Run `python -m pytest scripts/tests/test_issues_cli.py -k "clusters" -v` and `python -m pytest scripts/tests/test_dependency_graph.py -v` — all must pass
6. Manual smoke: `ll-issues clusters` on a project with fan-out cluster; verify A→C edge appears

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

7. Update `docs/reference/API.md:820` — update `from_issues()` parameter description to reflect that `issue.blocks` is now also consumed (not just `issue.blocked_by`)

## Affected Files

| File | Change |
|------|--------|
| `scripts/little_loops/cli/issues/clusters.py` | Fix 1: append skip-edges after diagram (`clusters.py:165-168`) |
| `scripts/little_loops/dependency_graph.py` | Fix 2: also process `issue.blocks` (`dependency_graph.py:108-110`) |
| `scripts/tests/test_issues_cli.py` | Fix 3: add fan-out rendering test (new fixture, after line 3438) |
| `scripts/tests/test_dependency_graph.py` | Fix 4: add unit test for one-sided `blocks:` in `from_issues()` |

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/issues/clusters.py` — Fix 1: append skip-edge annotations after diagram grid in `_render_cluster_diagram()`
- `scripts/little_loops/dependency_graph.py` — Fix 2: add `issue.blocks` second-pass loop in `DependencyGraph.from_issues()`

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/issues/__init__.py` — imports clusters subcommand
- `scripts/little_loops/cli/deps.py` — calls `DependencyGraph.from_issues()` for `ll-deps`
- `scripts/little_loops/cli/issues/clusters.py` — calls `DependencyGraph.from_issues()` internally

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/issue_manager.py:824` — calls `DependencyGraph.from_issues()` for ll-auto/ll-parallel; Fix 2 makes `issue.blocks`-only edges visible to the ready-issue queue
- `scripts/little_loops/cli/issues/sequence.py:34` — calls `DependencyGraph.from_issues()`; Fix 2 makes topological sort and sequence display reflect `blocks:`-only edges
- `scripts/little_loops/cli/sprint/manage.py:99` — calls `DependencyGraph.from_issues()`; Fix 2 makes wave calculation and cycle detection include `blocks:`-only edges
- `scripts/little_loops/cli/sprint/run.py:217` — calls `DependencyGraph.from_issues()`; Fix 2 makes parallel execution waves include `blocks:`-only edges
- `scripts/little_loops/cli/sprint/show.py:181` — calls `DependencyGraph.from_issues()`; Fix 2 makes sprint wave display include `blocks:`-only edges
- `scripts/little_loops/dependency_mapper/analysis.py:468` — calls `DependencyGraph.from_issues()` inside `validate_dependencies()`; Fix 2 makes cycle detection include `blocks:`-only edges

### Similar Patterns
- Other `DependencyGraph` consumers that iterate `graph.blocks` may benefit from the same `issue.blocks` fix if they display dependency direction

### Tests
- `scripts/tests/test_issues_cli.py` — add fan-out cluster rendering test after `test_clusters_no_arrows_between_independent_roots` (line 3438)
- `scripts/tests/test_dependency_graph.py` — add unit test for `from_issues()` one-sided `blocks:` handling (Fix 2)
- Existing tests: `test_clusters_*` in `test_issues_cli.py` (class `TestIssuesCLIClusters`, starts line 3072)

### Documentation

- N/A

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md:820` — `from_issues()` parameter description lists only `blocked_by` as a consumed field; update to reflect that `issue.blocks` is also consumed after Fix 2

### Configuration
- N/A

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| architecture | docs/ARCHITECTURE.md | Dependency graph and cluster rendering architecture |
| architecture | docs/reference/API.md | `DependencyGraph.from_issues()` public API |

## Impact

- **Priority**: P2 — Correctness bug: users relying on `ll-issues clusters` for dependency visualization receive incomplete graphs; fan-out/fan-in/diamond cluster shapes and one-sided `blocks:` declarations are silently dropped with no warning.
- **Effort**: Small — Two targeted additive code changes in well-scoped functions, plus one new test case.
- **Risk**: Low — Changes are purely additive (append skip-edge annotations below existing grid; add a second-pass loop for `blocks:`); the existing consecutive-arrow grid rendering is unchanged.
- **Breaking Change**: No

## Labels

`bug`, `ll-issues`, `clusters`, `rendering`, `dependency-graph`, `captured`

---

## Resolution

**Fixed** in `scripts/little_loops/cli/issues/clusters.py` and `scripts/little_loops/dependency_graph.py`.

- **Fix 1** (`clusters.py`): After the existing consecutive-arrow grid, compute `pos` mapping and append skip-edge annotations for all `edge_map` entries where `pos[t] - pos[f] > 1`.
- **Fix 2** (`dependency_graph.py`): Added a second-pass loop over `issue.blocks` in `from_issues()` that adds any A→B edge not already present from the `blocked_by` pass, with a dedup guard.
- **Fix 3/4**: New tests in `test_issues_cli.py` (fan-out fixture + rendering test) and `test_dependency_graph.py` (three one-sided `blocks:` unit tests).
- **Docs**: Updated `docs/reference/API.md` `from_issues()` parameter description.

## Status

**Completed** | Created: 2026-04-26 | Completed: 2026-04-27 | Priority: P2

## Session Log
- `/ll:manage-issue` - 2026-04-27T00:39:27Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fff9609e-8a5a-401a-87db-430505c5cf93.jsonl`
- `/ll:ready-issue` - 2026-04-27T00:33:33 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f4290412-ac19-4eb0-b486-2e9c478b536b.jsonl`
- `/ll:confidence-check` - 2026-04-26T23:50:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/43d5201f-0023-4202-9e9a-7dee9f90cdd8.jsonl`
- `/ll:wire-issue` - 2026-04-27T00:30:24 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f52e86c7-580e-4b6f-b558-5da3d4577274.jsonl`
- `/ll:refine-issue` - 2026-04-27T00:25:28 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/109b4df2-e313-49ad-85c0-72bbfa1e3631.jsonl`
- `/ll:format-issue` - 2026-04-27T00:10:25 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e2703aa3-7e30-410f-9743-2d1ca735cd06.jsonl`
- `/ll:capture-issue` - 2026-04-26T23:28:16Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e50c6bce-0407-46f5-8b96-1044f97de9cd.jsonl`
