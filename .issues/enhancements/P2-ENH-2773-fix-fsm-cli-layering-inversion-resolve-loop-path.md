---
id: ENH-2773
status: open
priority: P2
discovered_commit: fb5673902939bbf5a17bc7afe61317982d40bfd2
discovered_branch: main
discovered_date: 2026-07-24T22:31:26Z
discovered_by: audit-architecture
focus_area: integration
labels: [enhancement, architecture, refactoring, auto-generated]
parent: EPIC-2789
---

# ENH-2773: Fix fsm→cli layering inversion (move resolve_loop_path out of cli/loop/_helpers)

## Summary

Architectural issue found by `/ll:audit-architecture`. The core FSM layer
imports from the CLI layer: `fsm/validation.py` reaches up into
`cli/loop/_helpers` for `resolve_loop_path`, inverting the intended dependency
direction (core → cli, never cli ← core).

## Location

- **File**: `scripts/little_loops/fsm/validation.py`
- **Line(s)**: 485, 566 (deferred `from little_loops.cli.loop._helpers import resolve_loop_path`)
- **Module**: `little_loops.fsm.validation`

## Finding

### Current State

```python
# fsm/validation.py:485 and :566 (inside functions, to dodge the cycle)
from little_loops.cli.loop._helpers import resolve_loop_path
```

- `cli/loop/_helpers.py` and `fsm/validation.py` form a module-level 2-cycle,
  currently held apart only by deferred imports on both sides.
- Loop-path resolution is core FSM behavior (static `loop:` reference
  validation depends on it), not a CLI presentation concern.
- Related fragility in the same layering pass: `subprocess_utils.py:23` imports
  `host_runner` at module level while `host_runner` defers its imports of
  `subprocess_utils` — a one-sided cycle that works only by import order and
  will break silently if the deferred imports are ever "cleaned up".

### Impact

- **Development velocity**: contributors must know the unwritten rule that
  these imports stay function-local; refactors keep re-tripping the cycle.
- **Maintainability**: the layer order (core → fsm → parallel → cli) exists by
  convention only; this edge is the clearest violation of it.
- **Risk**: import-order breakage is silent until a specific code path runs.

## Proposed Solution

Move `resolve_loop_path` (and any helpers it depends on) into the `fsm`
layer — e.g. `fsm/loop_paths.py` — and have `cli/loop/_helpers` re-export or
import it from there, reversing the edge to the correct direction.

### Suggested Approach

1. Relocate `resolve_loop_path` to `little_loops/fsm/loop_paths.py` (or an
   existing fsm module if a better home exists); keep a re-export in
   `cli/loop/_helpers` for compatibility.
2. Convert the two deferred imports in `fsm/validation.py` to normal top-level
   imports of the new module; confirm the `cli.loop._helpers ↔ fsm.validation`
   2-cycle is gone.
3. In the same pass, make `host_runner`/`subprocess_utils` symmetric (extract
   the shared piece or document why the one-sided deferral is required).

## Impact Assessment

- **Severity**: High
- **Effort**: Small
- **Risk**: Low
- **Breaking Change**: No

---

## Status

**Open** | Created: 2026-07-24 | Priority: P2
