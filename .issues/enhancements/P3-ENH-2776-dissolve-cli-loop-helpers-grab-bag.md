---
id: ENH-2776
status: open
priority: P3
discovered_commit: fb5673902939bbf5a17bc7afe61317982d40bfd2
discovered_branch: main
discovered_date: 2026-07-24 22:31:26+00:00
discovered_by: audit-architecture
focus_area: organization
labels:
- enhancement
- architecture
- refactoring
- auto-generated
parent: EPIC-2789
verify_verdict: VALID
depends_on:
- EPIC-2938
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

## Related Key Documentation

- `docs/reference/API.md` — catalogs `cli/*` entry points module-by-module; splitting `_helpers.py` into named modules changes what that catalog should list.
- `docs/ARCHITECTURE.md` — covers module placement/decomposition questions directly; this issue is exactly that kind of "where should this code live" call.

## Verification Notes

**2026-08-10** (`/ll:verify-issues`): Verified 2026-08-10: `_helpers.py` still
exists at ~2,183 lines (grown from 2,156). `resolve_loop_path` has already
moved to fsm/loop_paths.py per ENH-2773 (status: done) — that specific
sub-step is complete; remaining decomposition work is still open.

## Session Log
- `/ll:audit-issue-conflicts` - 2026-08-28T20:02:57 - `4c46442f-f29f-4ed0-a178-b65ed74c4dc1.jsonl`
- `/ll:verify-issues` - 2026-08-13T03:04:57 - `10ce6a50-a4a8-4b29-a122-e05a925e303c.jsonl`
- `/ll:verify-issues` - 2026-08-10T16:26:27 - `50b69f30-8ca9-4ab9-8b06-6ee21c203b10.jsonl`

---

## Status

**Open** | Created: 2026-07-24 | Priority: P3

## Relationships

relates_to: ENH-2773
