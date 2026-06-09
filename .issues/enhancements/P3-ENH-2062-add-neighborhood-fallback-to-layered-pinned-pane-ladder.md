---
id: ENH-2062
type: ENH
priority: P3
status: done
title: "Add neighborhood fallback step to layered pinned-pane diagram ladder"
captured_at: "2026-06-09T20:41:52Z"
discovered_date: "2026-06-09"
discovered_by: capture-issue
---

# ENH-2062: Add neighborhood fallback step to layered pinned-pane diagram ladder

## Summary

The pinned-pane fallback ladder for layered presets (`--show-diagrams clean --clear`) jumped directly from the full layered diagram to the single-line `fsm: preds → [active] → succs` status, skipping the neighborhood intermediate. For large loops the full diagram is always too tall for typical terminals, so users saw single-line output regardless of terminal width or height.

## Motivation

When running `ll-loop run --show-diagrams clean --clear`, the pinned-pane height check in `_choose_pinned_layout` selects the most-detailed variant that fits within `rows - min_action_rows`. For large loops (e.g. `rn-build`: 28 states, `rn-implement`: 29 states), the full layered diagram in `clean` mode is 53–93 rows depending on terminal width — always exceeding typical terminal heights. The fallback ladder was:

```python
variants = [_build("full"), _build("single")]
```

The neighborhood diagram (bounded to `max(preds, succs) * 3` rows = 6–9 rows for typical states) was intentionally skipped with the comment "layered→neighborhood looks like a broken diagram and confuses users." In practice this made the fallback far too aggressive: users with any terminal under ~56 rows always saw single-line output for large loops, with no intermediate useful view.

## Root Cause

`_helpers.py`, `_render_pinned_pane()`, lines 433–434:

```python
elif topo_detail == "full":
    variants = [_build("full"), _build("single")]
```

The neighborhood step was omitted from the preset/default layered ladder. The concern about the visual mismatch between layered and neighborhood turned out not to apply in practice with `--show-diagrams clean`.

## Implementation

Single-line change to `scripts/little_loops/cli/loop/_helpers.py`:

```python
# Before
elif topo_detail == "full":
    variants = [_build("full"), _build("single")]

# After
elif topo_detail == "full":
    variants = [_build("full"), _build("neighborhood"), _build("single")]
```

Updated the surrounding comment to remove the "skip neighborhood" rationale.

## Verification

Measured actual diagram heights for the rn-* loop family with the `clean` preset at various terminal widths and confirmed:

| Loop | Full diagram height | Neighborhood height |
|---|---|---|
| `rn-plan` (7 states) | 23 rows (fits ≥30 rows) | 6 rows |
| `rn-refine` (10 states) | 38 rows (needs 41+ rows) | 6 rows |
| `rn-build` (28 states) | 53–83 rows (rarely fits) | 9 rows |
| `rn-implement` (29 states) | 78–93 rows (never fits) | 9 rows |

With the fix, terminals that cannot display the full diagram now show the neighborhood view (6–9 rows) rather than the single-line status. All 223 existing tests pass.

## Session Log
- `hook:posttooluse-status-done` - 2026-06-09T20:42:27 - `b29a10b4-384e-4d61-b102-c66d489dd021.jsonl`
- `/ll:capture-issue` - 2026-06-09T20:41:52Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b29a10b4-384e-4d61-b102-c66d489dd021.jsonl`

---

## Status

**Done** — fixed in this session.
