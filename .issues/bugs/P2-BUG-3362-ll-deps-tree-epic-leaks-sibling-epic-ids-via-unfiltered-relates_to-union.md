---
id: BUG-3362
type: BUG
title: ll-deps tree --epic leaks sibling EPIC ids via unfiltered relates_to union
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-08-30'
captured_at: '2026-08-30T18:53:49Z'
relates_to:
- BUG-3361
---

# BUG-3362: ll-deps tree --epic leaks sibling EPIC ids via unfiltered relates_to union

## Summary

Discovered via `/ll:wire-issue` while wiring BUG-3361 (SprintManager.load_or_resolve unions relates_to sibling-EPIC ids into an EPIC's dispatch set). The wiring agent traced the same `forward_ids | backward_ids` pattern into `cli/deps.py`'s `main_deps()` and confirmed it is a wholly separate code path — BUG-3361's `sprint.py`-only fix (adding an `_EPIC_ID_RE` filter to `SprintManager.load_or_resolve()`) leaves this branch unaffected.

After BUG-3361 ships, `ll-deps tree --epic EPIC-NNN` (both default text box-drawing output and `-f json` output) will still render a sibling EPIC listed in `relates_to:` as a child node of the EPIC being queried, even though it is not a decomposition child.

## Current Behavior

`main_deps()` in `scripts/little_loops/cli/deps.py` (the `ll-deps tree --epic` branch, lines 288-290) builds an EPIC's child set exactly like the code being fixed by BUG-3361, but as an independent reimplementation that BUG-3361's fix does not touch:

```python
# scripts/little_loops/cli/deps.py:288-290
forward_ids: set[str] = set(epic_info.relates_to)
backward_ids: set[str] = {i.issue_id for i in all_issues if i.parent == epic_id}
all_child_ids = forward_ids | backward_ids
```

`relates_to:` is also used as a documentation cross-reference between sibling EPICs (not a decomposition edge). This branch unions it into the child set with no EPIC-shape filter and no call into `sprint.py`, so it does not benefit from `_EPIC_ID_RE` or any equivalent guard.

## Expected Behavior

`ll-deps tree --epic` should never place an EPIC-type id into an EPIC's own child set. `relates_to:` on an EPIC is a documentation cross-reference to sibling/related epics, not a decomposition edge.

## Motivation

[Why this issue matters - business value, user impact, technical debt cost]

## Proposed Solution

In `scripts/little_loops/cli/deps.py`'s `main_deps()`, filter `forward_ids` to exclude EPIC-shaped ids, mirroring BUG-3361's resolution: reuse the case-insensitive `_EPIC_ID_RE` primitive from `scripts/little_loops/sprint.py:14` (or extract it to a shared helper both modules import) rather than a literal `.startswith("EPIC-")` check, for consistency with `relates_to` entries being unnormalized free text with no case guarantee.

```python
forward_ids: set[str] = {
    i for i in epic_info.relates_to if not _EPIC_ID_RE.match(i)
}
```

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/deps.py` — `forward_ids` construction at lines 288-290 inside `main_deps()`'s `ll-deps tree --epic` branch

### Tests
- `scripts/tests/test_deps_cli.py` — has `relates_to` fixtures (`FEAT-001`, `FEAT-002`) but none EPIC-shaped; needs a new regression test mirroring BUG-3361's AC (sibling-EPIC `relates_to` entry never appears in `ll-deps tree --epic` output)

### Documentation
- `docs/reference/CLI.md` — `#### ll-deps tree` section describes this branch's behavior; may need a note once the fix ships

## Implementation Steps

1. [Major phase 1]
2. [Major phase 2]
3. [Verification approach]

## Impact

- **Priority**: P2 - Same bug class and blast radius as BUG-3361: `ll-deps tree --epic` renders an incorrect dependency tree (misleading child listing), used by humans and automation (e.g. `/ll:review-epic`) to reason about EPIC decomposition. No data corruption.
- **Effort**: Small - single-line filter change, mirrors BUG-3361's fix exactly.
- **Risk**: Low - additive filter, only removes ids that were never valid children.
- **Breaking Change**: No.

## Steps to Reproduce

1. Create `EPIC-A` and `EPIC-B` as separate, independently-decomposed epics.
2. Add `relates_to: [EPIC-B]` to `EPIC-A`'s frontmatter as a documentation cross-reference (not a `parent:` decomposition edge).
3. Give `EPIC-A` its own real leaf children via `parent: EPIC-A` on their frontmatter.
4. Run `ll-deps tree --epic EPIC-A` (or `ll-deps tree --epic EPIC-A -f json`).
5. Observe: `EPIC-B` appears as a child node alongside `EPIC-A`'s real children — `EPIC-B` is not a child of `EPIC-A` and should not be rendered as one.

## Acceptance Criteria

- [ ] `ll-deps tree --epic EPIC-NNN` (text and `-f json` output) never includes an `EPIC-*` id in the rendered child set when that id only appears via a sibling-EPIC `relates_to:` cross-reference
- [ ] A regression test in `scripts/tests/test_deps_cli.py` covers a sibling-EPIC `relates_to` entry
- [ ] `python -m pytest scripts/tests/` passes

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`bug`, `loops`, `captured`

## Status

**Open** | Created: 2026-08-30 | Priority: P2


## Session Log
- `/ll:capture-issue` - 2026-08-30T18:54:08 - `00726072-62d6-4f81-b684-ed899628cec1.jsonl`
