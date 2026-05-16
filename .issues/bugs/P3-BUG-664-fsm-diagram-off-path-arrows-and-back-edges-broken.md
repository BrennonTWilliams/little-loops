---
id: BUG-664
priority: P3
status: active
discovered_date: 2026-03-09
discovered_by: capture-issue
confidence_score: 96
outcome_confidence: 93
---

# BUG-664: FSM Diagram Off-Path Arrows and Back-Edges Broken

## Summary

`ll-loop info` renders a broken ASCII diagram for `issue-refinement-git.yaml`. The 5-state off-path chain (`format_issues → score_issues → refine_issues → check_commit → commit`) has three distinct rendering bugs: inter-box arrows have no labels or arrowheads, right-going arrows target box centers instead of left edges, and back-edges to main-path states render as misleading inward-pointing left-arrows at the source box.

## Current Behavior

Running `ll-loop info .loops/issue-refinement-git.yaml` produces a broken ASCII diagram:
- Inter-box arrows between off-path states appear as bare `────` with no labels or arrowheads
- Right-going arrows target box centers instead of left edges (arrowhead lands inside destination box, overwriting its border)
- Back-edges from `check_commit → evaluate` and `commit → evaluate` render as `◄──error─│ check_commit │`, appearing as inward-pointing arrows at the source box rather than routing back to `evaluate`

## Expected Behavior

The FSM diagram should render correctly for off-path chains:
- Bottom row shows `format_issues ──next──▶ score_issues ──next──▶ ... ──success──▶ commit` with labeled arrowheads between each adjacent off-path box
- Right-going arrows hit the left edge of the destination box (not the center)
- Back-edges (`check_commit → evaluate`, `commit → evaluate`) render as U-routes with `▲` at the destination column, visually connecting back to `evaluate`

## Root Cause

**File**: `scripts/little_loops/cli/loop/info.py`, function `_render_2d_diagram`

Three bugs in the off-path rendering logic:

1. **Bug 1 — Hardcoded gap too small (anchor: off-path placement loop ~line 568)**: Off-path box gap is hardcoded to `4`, but labeled arrows need at least `len(label) + 6` characters. Arrows overflow into destination boxes, hiding labels and arrowheads.

2. **Bug 2 — Wrong target column for right-going arrows (anchor: right-going arrow rendering ~line 935)**: `col_center.get(dst, ...)` is used instead of `col_start.get(dst, ...)`. The arrowhead lands inside the destination box, overwriting its border content.

3. **Bug 3 — Back-edges rendered as inward left-arrows (anchor: back-edge rendering ~lines 947–953)**: Left-going back-edges (`check_commit → evaluate`, `commit → evaluate`) are drawn as `◀──label─` immediately left of the source box wall. This looks like an incoming arrow, multiple back-edges from the same state overlap, and there's no visual connection back to `evaluate`.

## Steps to Reproduce

```bash
ll-loop info .loops/issue-refinement-git.yaml
```

Observe:
- Bare `────` between off-path boxes with no arrowheads
- `◄──error─│ check_commit │` appearing as if arrows point into the box

## Proposed Solution

### Fix 1: Dynamic gap for off-path boxes

In the off-path placement loop (`_render_2d_diagram`, ~line 568–588), compute minimum gap per adjacent pair from edge labels:

```python
min_gap_for_label = max(
    (len(lbl) + 6 for s, d, lbl in branches + back_edges
     if s == prev_off and d == off_s),
    default=4
)
gap = max(4, min_gap_for_label)
```

### Fix 2: Use `col_start` as right-going arrow target

In `_render_2d_diagram`, right-going arrow rendering (~line 935), change:
```python
target_col = col_center.get(dst, start_col + len(label) + 4)
```
to:
```python
target_col = col_start.get(dst, start_col + len(label) + 4)
```

### Fix 3: Render off-to-main back-edges as U-routes

Add a new bucket `off_to_main_back` during edge classification in `_render_2d_diagram`. When `src in off_path_set and dst in main_path_set`, route to `off_to_main_back` instead of `off_state_edges[src]`. After the off-path grid, render as below-grid U-routes:
- One row with `│` at src column and `▲` at dst column
- One row with `└─ label ─...─┘` horizontal bar

**Scope boundary**: This fix only addresses `off-path → main-path` left-going edges. Off-path → off-path left-going edges (e.g., a retry back-edge within an off-path chain) still fall through to the broken `◄──label─` rendering and are out of scope for this issue.

**Collision handling required**: When two or more off-path states back-edge to the same main-path destination (e.g., both `check_commit → evaluate` and `commit → evaluate` in this topology), their U-routes share the same destination column. The renderer must not silently overwrite — routes must be rendered in separate row-pairs or the shared destination column handled explicitly. The regression test exercises this exact case (two back-edges to `evaluate`), so a naïve single-pass render will fail the test.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/info.py` — Three targeted fixes within `_render_2d_diagram`
- `scripts/tests/test_ll_loop_display.py` — Add regression test for the 6-state issue-refinement-git topology

### Key Code Locations in `info.py`

| Location | Description |
|---|---|
| `info.py:463–476` | `_render_2d_diagram` function signature — takes `main_path`, `edges`, `branches`, `back_edges`, `bfs_order`, etc. |
| `info.py:549–564` | `col_start`/`col_center` populated for **main-path** states — uses dynamic `gap = len(label) + 6` |
| `info.py:566–588` | `col_start`/`col_center` populated for **off-path** states — Bug 1: `gap = 4` at line 568 |
| `info.py:689–701` | `off_state_edges` and `main_extra` bucketing — off-path edges collected by src/dst membership |
| `info.py:762–775` | Per-off-path-state sub-classification into `down_labels`, `up_labels`, `outgoing` — Bug 3 fix insertion point |
| `info.py:704–731` | `main_extra` U-route rendering — the pattern to follow for Bug 3's U-route fix |
| `info.py:930–957` | Outgoing edge rendering — Bug 2 at line 935 (`col_center` → `col_start`), Bug 3 stub at lines 947–953 |

### Edge Classification Flow (relevant to Bug 3)

1. `_render_fsm_diagram` classifies all transitions into `branches` + `back_edges` (`info.py:426–444`)
2. `_render_2d_diagram` re-buckets: `off_state_edges[src]` gets edges where either endpoint is off-path (`info.py:696–697`)
3. Per-state sub-classification loop (`info.py:762–775`): edges not matching up/down anchor patterns fall to `outgoing`
4. `outgoing` edges hit the Bug 3 left-going stub path at `info.py:947–953`

**Fix 3 insertion point**: Add `off_to_main_back` check in the per-state sub-classification loop (`info.py:762–775`), before appending to `outgoing`. When `src in off_path_set and dst in main_path_set`, route to a new `off_to_main_back` dict keyed by `dst`. After the off-path grid, render `off_to_main_back` as U-routes following the `main_extra` pattern at `info.py:704–731`.

### Test Infrastructure
- Import: `from little_loops.cli.loop.info import _render_fsm_diagram`
- `FSMLoop` and `StateConfig` from `little_loops.models`
- All existing diagram tests use `_render_fsm_diagram(fsm)` (not `_render_2d_diagram` directly)
- Most similar existing test: `test_linear_off_path_chain_all_states_visible` at `test_ll_loop_display.py:857`

## Affected Files

- `scripts/little_loops/cli/loop/info.py` — Three targeted fixes within `_render_2d_diagram`
- `scripts/tests/test_ll_loop_display.py` — Add regression test for the 6-state issue-refinement-git topology

## Regression Test

Add a test that builds the `issue-refinement-git` topology (6 states: `evaluate`, `format_issues`, `score_issues`, `refine_issues`, `check_commit`, `commit` — no `done` state) and asserts:
1. All 6 states appear in boxes with `│` borders
2. A `▶` right-arrow appears between each adjacent off-path state pair
3. A `▲` back-edge indicator appears for both `check_commit → evaluate` and `commit → evaluate` — both must be present without overwriting each other (two separate U-route row-pairs)
4. No `◀` left-arrow appears immediately adjacent to `check_commit` or `commit` left walls

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

Follow the constructor and assertion patterns from `test_ll_loop_display.py:857` (`test_linear_off_path_chain_all_states_visible`):

```python
def test_issue_refinement_git_topology(self) -> None:
    """Regression for BUG-664: off-path chain arrows and back-edges."""
    fsm = self._make_fsm(
        initial="evaluate",
        states={
            "evaluate": StateConfig(
                action="evaluate",
                on_success="done",  # terminal via separate done state or terminal=True
                on_failure="format_issues",
            ),
            "format_issues": StateConfig(action="format", next="score_issues"),
            "score_issues": StateConfig(action="score", next="refine_issues"),
            "refine_issues": StateConfig(action="refine", next="check_commit"),
            "check_commit": StateConfig(action="check", on_success="commit", on_failure="evaluate"),
            "commit": StateConfig(action="commit", next="evaluate"),
        },
    )
    result = _render_fsm_diagram(fsm)
    lines = result.split("\n")

    # 1. All 6 states appear in boxes (line with state name AND │ border)
    for state in ("evaluate", "format_issues", "score_issues", "refine_issues", "check_commit", "commit"):
        box_lines = [ln for ln in lines if state in ln and "\u2502" in ln]
        assert box_lines, f"{state!r} should be rendered in a box with │ borders"

    # 2. ▶ right-arrow appears somewhere in diagram
    assert "\u25b6" in result, "Expected ▶ right-arrow between off-path states"

    # 3. ▲ appears twice (two separate U-route row-pairs, not overwriting each other)
    up_arrow_count = result.count("\u25b2")
    assert up_arrow_count >= 2, (
        f"Expected ▲ for both check_commit→evaluate and commit→evaluate back-edges, "
        f"found {up_arrow_count}. Full diagram:\n{result}"
    )

    # 4. No ◄ immediately adjacent to check_commit or commit left walls
    for state in ("check_commit", "commit"):
        state_rows = [ln for ln in lines if state in ln and "\u2502" in ln]
        for row in state_rows:
            state_pos = row.index(state)
            prefix = row[:state_pos]
            assert "\u25c4" not in prefix[-6:], (
                f"Found ◄ immediately left of {state!r} box — Bug 3 not fixed. Row: {row!r}"
            )
```

Note: Adjust `evaluate` terminal behavior to match the actual `.loops/issue-refinement-git.yaml` topology (the real loop has no explicit `done` state — `evaluate` is the hub). The skeleton above may need `terminal=True` on `evaluate` or the addition of a `done` terminal state to match routing exactly.

## Implementation Steps

1. **Bug 1** — `info.py:568`: Replace `gap = 4` with dynamic per-pair computation:
   ```python
   gap = max(
       4,
       max(
           (len(lbl) + 6 for s, d, lbl in branches + back_edges
            if s == prev_off and d == off_s),
           default=4,
       ),
   )
   ```
   Note: `prev_off` must be tracked as the previously placed off-path state in the loop.

2. **Bug 2** — `info.py:935`: Change `col_center.get(dst, ...)` to `col_start.get(dst, ...)`.

3. **Bug 3** — `info.py:762–775` + `info.py:947–953`:
   - In the per-state sub-classification loop (`info.py:762–775`), before appending to `outgoing`, intercept edges where `src in off_path_set and dst in main_path_set`; collect them into `off_to_main_back: dict[str, list[...]]` keyed by `dst`
   - After the off-path grid is drawn, render each `dst` group as U-route row-pairs (separate row-pair per `dst`) following the `main_extra` U-route pattern at `info.py:704–731`
   - Remove or guard the Bug 3 stub rendering at `info.py:947–953` so it no longer fires for off-path→main-path back-edges

4. **Add regression test** in `test_ll_loop_display.py` following the skeleton in the Regression Test section above, modeled after `test_linear_off_path_chain_all_states_visible` at line 857.

5. **Verify** all existing tests remain green, then visual spot-check with `ll-loop info`.

## Verification

```bash
# Run existing tests (must stay green)
python -m pytest scripts/tests/test_ll_loop_display.py -v

# Visual spot-check
ll-loop info .loops/issue-refinement-git.yaml
```

## Impact

- **Priority**: P3 - FSM diagram rendering is visually broken for complex loops with off-path chains, impacting developer usability when inspecting loop topology; core loop execution is unaffected
- **Effort**: Medium - Three targeted fixes in `_render_2d_diagram` within `info.py`, plus a regression test covering the 7-state topology
- **Risk**: Low - All changes are isolated to ASCII rendering code; no data model, FSM execution, or CLI argument parsing is affected
- **Breaking Change**: No

## Labels

`bug`, `rendering`, `fsm-diagram`, `ll-loop`, `captured`

## Verification Notes

**Verdict**: VALID — All three rendering bugs confirmed in `scripts/little_loops/cli/loop/info.py` (`_render_2d_diagram`):
- Bug 1 (line ~567): `gap = 4` hardcoded — confirmed
- Bug 2 (line ~935): `col_center.get(dst, ...)` instead of `col_start.get(dst, ...)` — confirmed
- Bug 3 (lines ~947–953): Left-going back-edge renders as `◀──label─` left of source box — confirmed

**Minor discrepancy (corrected)**: Issue's Regression Test section references a "7-state topology" including a `done` state, but `.loops/issue-refinement-git.yaml` has 6 states: `evaluate`, `format_issues`, `score_issues`, `refine_issues`, `check_commit`, `commit` (no `done` state). The `commit` state IS present (transitions to `evaluate`). Regression test assertions should be updated to reflect 6 states and remove `done`. Core bugs are unaffected.

## Resolution

**Status**: Fixed
**Completed**: 2026-03-09

Three targeted fixes applied to `scripts/little_loops/cli/loop/info.py` (`_render_2d_diagram`):

1. **Bug 1** (`info.py:568`): Replaced hardcoded `gap = 4` with dynamic per-pair gap computation. Added `prev_off` tracking in the off-path placement loop; gap for each adjacent pair is now `max(4, len(label) + 6)` over all edges between them.

2. **Bug 2** (`info.py:935`): Changed `col_center.get(dst, ...)` to `col_start.get(dst, ...)` in outgoing edge rendering. Right-going arrows now target the left edge of the destination box instead of its center.

3. **Bug 3** (`info.py:780-791`, `info.py:979-1007`): Added `off_to_main_back` interception in the per-state sub-classification loop. Edges where `src in off_path_set and dst in main_path_set` (without a direct vertical up-connector) are now collected and rendered as below-grid U-routes with `▲` at the destination column — separate row-pairs per edge, preventing overwriting.

Added regression test `test_issue_refinement_git_topology` to `scripts/tests/test_ll_loop_display.py` exercising the 6-state topology. Also updated `test_multiple_off_path_states_same_depth` to reflect that off-path→main-path edges now render as U-routes (not `◄` arrows).

## Session Log
- `/ll:capture-issue` - 2026-03-09T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/01f82782-0b8c-4ad7-bf21-b0fbd48b9fa2.jsonl`
- `/ll:format-issue` - 2026-03-09T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/01f82782-0b8c-4ad7-bf21-b0fbd48b9fa2.jsonl`
- `/ll:verify-issues` - 2026-03-09T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/01f82782-0b8c-4ad7-bf21-b0fbd48b9fa2.jsonl`
- `/ll:confidence-check` - 2026-03-09T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/01f82782-0b8c-4ad7-bf21-b0fbd48b9fa2.jsonl`
- `/ll:confidence-check` - 2026-03-09T12:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b0bed9e2-4ea4-433b-ac3a-40c28d5278ee.jsonl`
- `/ll:ready-issue` - 2026-03-09T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/42eb984b-d0b4-43ff-a6f1-33d5fd55e3b6.jsonl`
- `/ll:refine-issue` - 2026-03-09T13:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1e1f6e4e-f38d-45f4-9ef6-5a32d3bbb8d1.jsonl`
- `/ll:manage-issue` - 2026-03-09T14:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/current.jsonl`

---

**Completed** | Created: 2026-03-09 | Resolved: 2026-03-09 | Priority: P3
