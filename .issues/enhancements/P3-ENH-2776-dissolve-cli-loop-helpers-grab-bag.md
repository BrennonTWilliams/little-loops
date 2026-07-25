---
id: ENH-2776
status: open
priority: P3
discovered_commit: fb5673902939bbf5a17bc7afe61317982d40bfd2
discovered_branch: main
discovered_date: 2026-07-24T22:31:26Z
discovered_by: audit-architecture
focus_area: organization
labels: [enhancement, architecture, refactoring, auto-generated]
parent: EPIC-2789
---

# ENH-2776: Dissolve cli/loop/_helpers.py grab-bag into named modules

## Summary

Architectural issue found by `/ll:audit-architecture`. A 2,156-line module
named `_helpers.py` is a grab-bag hiding several real modules; its contents
are depended on well beyond the CLI layer.

## Location

- **File**: `scripts/little_loops/cli/loop/_helpers.py`
- **Line(s)**: 1-2156 (entire file)
- **Module**: `little_loops.cli.loop._helpers`

## Finding

### Current State

- 2,156 lines, 37 top-level defs behind an underscore-private "helpers" name.
- Imported by core code (`fsm/validation.py:485,566` — see ENH-2773) and by
  `cli/loop/info.py` in a 2-cycle (`_helpers.py:1768` ↔ `info.py:20,1566`)
  held apart by deferred imports.
- The name gives no signal about ownership, so unrelated functionality keeps
  landing here by default.

### Impact

- **Development velocity**: "where does this go?" defaults to `_helpers.py`,
  compounding the problem.
- **Maintainability**: an underscore-prefixed module with external importers is
  a false-privacy signal.
- **Risk**: low-medium — mostly navigational cost plus the cycle fragility.

## Proposed Solution

Split by actual responsibility into named modules (e.g. loop-path resolution —
moving to `fsm/` per ENH-2773 — run inspection, output formatting), leaving
`_helpers.py` as a temporary re-export shim before deleting it.

### Suggested Approach

1. Inventory the 37 defs and cluster by concern; land `resolve_loop_path`'s
   move with ENH-2773 first.
2. Create named modules under `cli/loop/` for the remaining clusters; update
   importers (`__init__.py`, `info.py`, `lifecycle.py`, `layout.py`).
3. Break the `_helpers ↔ info` 2-cycle as part of the split; delete the shim
   once no importers remain.

## Impact Assessment

- **Severity**: Medium
- **Effort**: Medium
- **Risk**: Low
- **Breaking Change**: No

---

## Status

**Open** | Created: 2026-07-24 | Priority: P3

## Relationships

relates_to: ENH-2773
