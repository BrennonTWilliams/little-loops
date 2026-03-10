---
id: ENH-666
type: ENH
priority: P3
status: active
discovered_date: 2026-03-10
discovered_by: capture-issue
---

# ENH-666: FSM Box Diagram Generator Should Prefer Vertical Layout

## Summary

The FSM Box Diagram Generator (`ll-loop s <name>`) currently renders state chains horizontally, producing diagrams that exceed terminal width. Since vertical space is unlimited in a terminal, the generator should lay out sequential state chains vertically (top-to-bottom) instead of horizontally (left-to-right).

## Motivation

The current horizontal layout is only correct when the user's terminal is at maximum width. For typical terminal widths, long chains of states (e.g., `format_issues → score_issues → refine_issues → check_commit → commit`) overflow the visible area, making the diagram unreadable. Vertical layout uses the terminal's unlimited scroll space and keeps each state visible without horizontal scrolling.

## Current Behavior

From `ll-loop s issue-refinement-git`:

```
┌──────────────────────────────────────────┐          ┌──────────────────────────────────────────┐          ┌──────────────────────────────────────────┐          ┌──────────────────────────────────────────┐
│ format_issues  [prompt]                  │───next──▶│ score_issues  [prompt]                   │───next──▶│ refine_issues  [prompt]                  │───next──▶│ check_commit  [shell]                    │
│ Here is the current refinement state of… │          │ Here is the current refinement state of… │          │ Here is the current refinement state of… │          │ FILE="/tmp/issue-refinement-commit-coun… │
└──────────────────────────────────────────┘          └──────────────────────────────────────────┘          └──────────────────────────────────────────┘          └──────────────────────────────────────────┘
```

States in a linear chain are placed side-by-side horizontally with `───next──▶` arrows between them, causing the diagram to be extremely wide.

## Expected Behavior

Sequential states connected by `next` (or similar linear transitions) should be stacked vertically:

```
┌──────────────────────────────────────────┐
│ format_issues  [prompt]                  │
│ Here is the current refinement state of… │
└──────────────────────────────────────────┘
                     │
                   next
                     ▼
┌──────────────────────────────────────────┐
│ score_issues  [prompt]                   │
│ Here is the current refinement state of… │
└──────────────────────────────────────────┘
                     │
                   next
                     ▼
┌──────────────────────────────────────────┐
│ refine_issues  [prompt]                  │
│ Here is the current refinement state of… │
└──────────────────────────────────────────┘
                     │
                   next
                     ▼
┌──────────────────────────────────────────┐
│ check_commit  [shell]                    │
│ FILE="/tmp/issue-refinement-commit-coun… │
└──────────────────────────────────────────┘
```

Arrows connecting vertical states go from the center-bottom of the source box to the center-top of the destination box. Back-edges (e.g., `fail`/`error` returning to an earlier state) are rendered as labeled horizontal arrows to the left side of the target box.

## Proposed Solution

- The FSM Box Diagram Generator lives in `scripts/little_loops/` — locate the rendering module (likely `fsm_diagram.py`, `loop_diagram.py`, or similar in the `fsm/` or `loop/` subpackage).
- The layout algorithm should detect linear chains (states with a single outgoing `next` transition) and render them vertically.
- Branch states (multiple outgoing transitions like `on_success`/`on_failure`) can remain as horizontal branches or use a mixed layout.
- Back-edges should be rendered as labeled arrows on the left or right margin to avoid crossing state boxes.
- Consider terminal width detection (`shutil.get_terminal_size()`) to set a max box width and trigger vertical layout when horizontal layout would exceed it.

## Integration Map

### Files to Modify
- `scripts/little_loops/` — FSM diagram rendering module (likely `fsm_diagram.py`, `loop_diagram.py`, or similar in `fsm/` or `loop/` subpackage)

### Dependent Files (Callers/Importers)
- TBD — use grep to find references: `grep -r "diagram\|show\|render" scripts/little_loops/`

### Similar Patterns
- See P4-ENH-542 (FSM diagram list index) and P4-ENH-654 (active state highlight) for related diagram rendering changes

### Tests
- TBD — identify test files covering `ll-loop s` / FSM diagram output

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Locate the FSM diagram rendering module in `scripts/little_loops/` (search for `fsm_diagram`, `loop_diagram`, or similar)
2. Identify the layout algorithm that places states horizontally; detect linear chains (states with a single outgoing `next` transition)
3. Implement vertical layout: render linear-chain states top-to-bottom with center-bottom → center-top labeled arrows
4. Handle back-edges (e.g., `fail`/`error` returning to an earlier state) as labeled arrows on the left/right margin to avoid overlapping boxes
5. Add/update tests for FSM diagram output; verify `ll-loop s issue-refinement-git` produces expected vertical layout

## Acceptance Criteria

- [ ] `ll-loop s issue-refinement-git` produces a vertical layout for the `format_issues → score_issues → refine_issues → check_commit → commit` chain
- [ ] Arrows between vertically stacked states are labeled and point downward (center-bottom to center-top)
- [ ] Back-edges (`fail`/`error` returning to `evaluate`) are clearly labeled and do not overlap state boxes
- [ ] Layout does not exceed terminal width (or a reasonable default like 120 chars) for typical FSM configs
- [ ] Existing tests for FSM diagram rendering pass or are updated

## Scope Boundaries

- **In scope**: Vertical layout for linear state chains (single outgoing `next` transition); downward arrows between stacked states; back-edge rendering on the margin
- **Out of scope**: Changes to FSM execution logic, YAML config format, other CLI output formats, interactive diagrams, export formats

## Impact

- **Priority**: P3 — Display usability fix; affects all users with non-full-width terminals running `ll-loop s`
- **Effort**: Small — Isolated layout algorithm change in the diagram rendering module; no changes to FSM execution or data model
- **Risk**: Low — Display-only change; no impact on FSM execution, YAML format, or loop behavior
- **Breaking Change**: No

## Labels

`enhancement`, `ux`, `cli-output`

## Related Issues

- P4-ENH-542: Render FSM diagram list index in loop
- P4-ENH-654: FSM diagram active state background fill highlight

## Session Log
- `/ll:capture-issue` - 2026-03-10T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fffc83c9-009a-4696-8010-040737bf7247.jsonl`
- `/ll:format-issue` - 2026-03-10T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fffc83c9-009a-4696-8010-040737bf7247.jsonl`

---

**Open** | Created: 2026-03-10 | Priority: P3
