---
discovered_date: 2026-03-18
discovered_by: capture-issue
---

# BUG-806: Route states missing unicode composition badge in FSM diagram

## Summary

After ENH-732 added unicode composition badges to FSM state boxes, "route" states — states where `state.route` is set (e.g., `route_format`, `route_verify`, `route_score`) — render no badge because `_get_state_badge()` only checks `state.loop`, `state.action_type`, and `state.action`, skipping `state.route`. These routing/branching states should have their own distinct badge so they are visually distinguishable from unlabeled states.

## Current Behavior

`_get_state_badge()` returns `""` for route states because the function does not inspect `state.route`:

```python
def _get_state_badge(state: StateConfig | None) -> str:
    if state is None:
        return ""
    if state.loop is not None:
        return _SUB_LOOP_BADGE
    if state.action_type:
        return _ACTION_TYPE_BADGES.get(state.action_type, ...)
    if state.action:
        return _ACTION_TYPE_BADGES["shell"]
    return ""  # <-- route states fall through here
```

Route states render as plain boxes with no badge, indistinguishable from unlabeled states:

```
┌──────────────┐
│ route_format │
└──────────────┘
```

## Expected Behavior

Route states should render with a dedicated badge (e.g., `⇒` or `⤳` or `⊕`) that signals branching/routing behavior:

```
┌────────────────┐
│ route_format ⇒ │
└────────────────┘
```

## Motivation

Without a badge, route states are visually identical to states that have no action configured, making FSM diagrams harder to read. The badge system introduced by ENH-732 is incomplete without coverage for route states.

## Steps to Reproduce

1. Open any FSM loop YAML that includes states using `route:` (e.g., `route_format`, `route_verify`, `route_score`)
2. Run `ll-loop show` to render the diagram
3. Observe that route states render without any badge

## Proposed Solution

Add a `_ROUTE_BADGE` constant and add a route check in `_get_state_badge()`:

```python
_ROUTE_BADGE = "\u21d2"  # ⇒  (or "\u2794" ➔, or "\u29f4" ⧴)

def _get_state_badge(state: StateConfig | None) -> str:
    if state is None:
        return ""
    if state.loop is not None:
        return _SUB_LOOP_BADGE
    if state.action_type:
        return _ACTION_TYPE_BADGES.get(state.action_type, f"[{state.action_type}]")
    if state.action:
        return _ACTION_TYPE_BADGES["shell"]
    if state.route:          # <-- add this
        return _ROUTE_BADGE
    return ""
```

The specific character should be chosen to be visually distinct from the existing badges (`✦`, `❯_`, `↳⟳`, `⚡`, `/━►`) and clearly convey branching/routing semantics.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/layout.py` — `_get_state_badge()` and `_ACTION_TYPE_BADGES` / badge constant section (~lines 69–98)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/layout.py` — `_compute_box_sizes()` calls `_get_state_badge()` for width computation; will automatically pick up the new badge width

### Similar Patterns
- `_SUB_LOOP_BADGE` constant definition pattern (~line 79) for adding `_ROUTE_BADGE`

### Tests
- `scripts/tests/` — search for FSM layout tests; add test case for route state badge rendering

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Choose the route badge character (confirm with user or pick `⇒` as default)
2. Add `_ROUTE_BADGE` constant near `_SUB_LOOP_BADGE` in `layout.py`
3. Add `if state.route: return _ROUTE_BADGE` branch in `_get_state_badge()`
4. Verify box width computation for route state boxes automatically accounts for badge width
5. Run tests and update/add snapshot expectations for route state boxes

## Impact

- **Priority**: P3 — cosmetic completeness; not blocking functionality
- **Effort**: Small — single function change + new constant
- **Risk**: Low — isolated to badge rendering; no logic or data flow changes
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`bug`, `rendering`, `fsm-diagram`, `captured`

## Session Log

- `/ll:capture-issue` - 2026-03-18T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/18f420b1-0c39-4794-9ebd-f0386a21c8dd.jsonl`

---

**Open** | Created: 2026-03-18 | Priority: P3
