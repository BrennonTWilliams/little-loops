---
id: BUG-3362
type: BUG
title: ll-deps tree --epic leaks sibling EPIC ids via unfiltered relates_to union
priority: P2
status: done
discovered_by: ll-issues-create
discovered_date: '2026-08-30'
captured_at: '2026-08-30T18:53:49Z'
completed_at: '2026-08-30T19:29:00Z'
relates_to:
- BUG-3361
confidence_score: 100
outcome_confidence: 95
score_complexity: 25
score_test_coverage: 20
score_ambiguity: 25
score_change_surface: 25
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

Automation and humans both use `ll-deps tree --epic` to reason about EPIC
decomposition (e.g. `/ll:review-epic`); a sibling EPIC id leaking into the
child listing produces a misleading dependency tree that can misdirect
review/audit tooling into treating an unrelated EPIC as part of this EPIC's
scope. No data corruption, but it erodes trust in the tree output and wastes
review time chasing a phantom parent/child relationship.

## Proposed Solution

In `scripts/little_loops/cli/deps.py`'s `main_deps()`, filter `forward_ids` to exclude EPIC-shaped ids, mirroring BUG-3361's resolution: reuse the case-insensitive `_EPIC_ID_RE` primitive from `scripts/little_loops/sprint.py:14` (or extract it to a shared helper both modules import) rather than a literal `.startswith("EPIC-")` check, for consistency with `relates_to` entries being unnormalized free text with no case guarantee. BUG-3361 has landed (commit `8886bc261`): `sprint.py:343` now applies exactly this filter, so this change makes the two branches identical.

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

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_deps_cli.py` — confirmed gap: no test in this file, `test_cli_deps.py`, or `test_dependency_mapper.py` currently exercises `forward_ids` with an EPIC-shaped `relates_to` entry [Agent 3 finding]. BUG-3361 has since landed (commit `8886bc261`): its regression test `test_load_or_resolve_relates_to_excludes_sibling_epic` (`scripts/tests/test_sprint.py:2774`) is the exact template to mirror for fixture shape and assertion. Closest structural templates in this file: `test_tree_linear_chain` / `test_tree_no_children` (`test_deps_cli.py:77-97`, `:65-75`) [Agent 3 finding, updated post-BUG-3361]
- New test case: an EPIC whose *only* `relates_to` entries are EPIC-shaped (no `parent:`-linked children) will newly hit the `(no children)` sentinel at `deps.py:292-294` after the fix, where it previously rendered the sibling EPIC id — add a case asserting this transition explicitly [Agent 2 finding]

### Documentation
- `docs/reference/CLI.md` — `#### ll-deps tree` section describes this branch's behavior; may need a note once the fix ships

## Implementation Steps

1. Add the `forward_ids` filter in `scripts/little_loops/cli/deps.py`'s `ll-deps tree --epic` branch (lines 288-290), reusing (or extracting to a shared helper) the `_EPIC_ID_RE` primitive from `scripts/little_loops/sprint.py:14`.
2. Add a regression test in `scripts/tests/test_deps_cli.py` covering a sibling-EPIC `relates_to` entry, mirroring BUG-3361's AC.
3. Run `python -m pytest scripts/tests/` to verify the new test and existing `test_deps_cli.py` coverage pass.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Import directly, don't extract: `_EPIC_ID_RE` is private to `scripts/little_loops/sprint.py` (no other production file imports it) — no shared-helper module for EPIC-id-shape detection exists yet in `issue_parser.py` or `cli_args.py`. `scripts/little_loops/cli/deps.py` already imports `from little_loops.sprint import Sprint` at line 335, inside this same `main_deps()` function's sibling "sprint-scoped filtering" branch, and `sprint.py` never imports from `little_loops.cli`/`little_loops.cli.deps` — so `from little_loops.sprint import _EPIC_ID_RE` at the "tree --epic" branch is a proven-safe, non-circular import with an exact precedent already live in this file. Resolves the "reuse ... or extract to a shared helper" ambiguity in Proposed Solution in favor of direct import; no extraction needed for this fix. [Agent 2 finding]
- FYI, out of scope: `scripts/little_loops/recursive_finalize.py:35` defines an identical pattern under a different name (`_EPIC_RE = re.compile(r"^EPIC-\d+$", re.IGNORECASE)`), with no cross-import between it and `sprint.py`. Not a caller of the buggy branch and not required for this fix, but relevant if a future pass consolidates EPIC-id-shape detection into a shared helper. [Agent 1 / Agent 2 finding]

## Program Design

### Signatures

- `main_deps() -> int` — signature unchanged; only the `forward_ids` computation inside the `ll-deps tree --epic` branch changes

### Call Path

`main_deps()` (`ll-deps tree --epic` branch) -> filtered `forward_ids` (excludes `EPIC-`-prefixed ids) -> unioned with `backward_ids` into `all_child_ids` (`deps.py:290`)

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

- [x] `ll-deps tree --epic EPIC-NNN` (text and `-f json` output) never includes an `EPIC-*` id in the rendered child set when that id only appears via a sibling-EPIC `relates_to:` cross-reference
- [x] A regression test in `scripts/tests/test_deps_cli.py` covers a sibling-EPIC `relates_to` entry
- [x] `python -m pytest scripts/tests/` passes

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`bug`, `loops`, `captured`

## Status

**Open** | Created: 2026-08-30 | Priority: P2


## Session Log
- `/ll:manage-issue` - 2026-08-30T19:28:43 - `390f8aaf-8222-4dbe-8e82-f63fc252fee9.jsonl`
- `/ll:confidence-check` - 2026-08-30T19:19:32 - `48d40a53-93a6-4504-86d8-4f8fd5b34143.jsonl`
- `/ll:wire-issue` - 2026-08-30T19:07:21 - `3e336bf1-dd8f-4ab7-b5d8-b5bf4adff8fb.jsonl`
- `/ll:refine-issue` - 2026-08-30T18:58:55 - `12d26f9a-ed28-4a88-a053-f90953905374.jsonl`
- `/ll:format-issue` - 2026-08-30T18:57:02 - `9bc3b2e3-2cf2-4efa-91d3-ec380f6bfaf0.jsonl`
- `/ll:capture-issue` - 2026-08-30T18:54:08 - `00726072-62d6-4f81-b684-ed899628cec1.jsonl`
