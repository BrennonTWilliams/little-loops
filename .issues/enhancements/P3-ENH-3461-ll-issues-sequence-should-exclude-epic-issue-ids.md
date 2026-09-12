---
id: ENH-3461
type: ENH
title: ll-issues sequence should exclude EPIC issue IDs
priority: P3
status: done
discovered_by: ll-issues-create
discovered_date: '2026-09-12'
captured_at: '2026-09-12T18:38:08Z'
completed_at: '2026-09-12T21:32:03Z'
confidence_score: 100
outcome_confidence: 100
score_complexity: 25
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
---

# ENH-3461: ll-issues sequence should exclude EPIC issue IDs

## Summary

`ll-issues sequence` lists EPIC issues alongside BUG/FEAT/ENH in its
dependency-ordered output, even though EPICs are coordination containers,
not directly-implementable units. They clutter the suggested sequence and
consume a slot under `--limit`.

## Current Behavior

`ll-issues sequence` (no `--type` flag) includes open `EPIC-*` issues in its
dependency-ordered output, interleaved with BUG/FEAT/ENH rows and counted
against `--limit`, in both the human-readable and `--json` output paths.

## Expected Behavior

The default (no `--type`) `ll-issues sequence` output excludes `EPIC-*`
issues, showing only directly-implementable BUG/FEAT/ENH rows. Passing
`--type EPIC` explicitly still returns EPIC rows, unchanged from today.

## Motivation

The display filter in `cmd_sequence` (`scripts/little_loops/cli/issues/sequence.py:110-112`)
only filters on `_OPEN_STATUSES` and an optional `--type` prefix:

```python
display = [i for i in ordered if i.status in _OPEN_STATUSES]
if type_prefix:
    display = [i for i in display if i.issue_id.split("-", 1)[0] == type_prefix]
```

There is no exclusion for `EPIC-*` IDs, so an open EPIC appears in the
suggested sequence next to concrete BUG/FEAT/ENH issues a user would
actually pick up next. A user running `ll-issues sequence` to decide what
to implement next has to manually skip EPIC rows.

## Proposed Solution

In `cmd_sequence` (`scripts/little_loops/cli/issues/sequence.py:110-112`), add
an `EPIC` exclusion to the `display` filter that only applies when no
`--type` was requested, so `--type EPIC` still opts back in:

```python
display = [i for i in ordered if i.status in _OPEN_STATUSES]
if type_prefix:
    display = [i for i in display if i.issue_id.split("-", 1)[0] == type_prefix]
else:
    display = [i for i in display if i.issue_id.split("-", 1)[0] != "EPIC"]
```

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/issues/sequence.py` — `cmd_sequence`'s `display`
  filter construction (lines 110-112)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/issues/__init__.py` (or wherever `sequence`'s
  argparse subcommand is registered) — no changes needed, just wires
  `cmd_sequence` in; grep for `cmd_sequence` to confirm no other caller
  depends on EPICs being present in `display`/`shown`

### Similar Patterns
- `find_highest_priority_issue` and other issue-selection helpers already
  treat EPICs as non-selectable coordination containers rather than
  implementable units — this brings `sequence` in line with that convention

### Tests
- `scripts/tests/test_issues_cli.py` — `TestIssuesCLISequence`, alongside
  `test_sequence_type_filter_epic` (asserts `--type EPIC` still works when no
  epics exist): add a case with an open EPIC plus open BUG/FEAT/ENH issues,
  asserting the EPIC is absent from default `sequence` output (both
  human-readable and `--json`) and present under `--type EPIC`

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_issue_parser.py:1636-1640` — a `callsite_shapes` table
  entry (`"sequence:28"`) mirrors `cmd_sequence`'s current `find_issues()`
  call-site shape as part of a cross-callsite consistency check; this fix
  only changes the downstream `display` filter, not the `find_issues()` call
  itself, so no edit is expected here — verify it still passes, don't skip
  the check [Agent 1 finding]
- Follow the `TestNextIssueEpicExclusion` / `TestNextIssuesEpicExclusion`
  convention (`scripts/tests/test_next_issue.py:1056-1122`,
  `scripts/tests/test_next_issues.py:879-965`, both citing BUG-2638) for the
  new sequence test case: a highest-priority/highest-confidence EPIC
  deliberately ranked first (to prove active filtering, not just absence by
  construction), paired with a surviving child issue, plus a JSON assertion
  in the `ids = [row["id"] for row in data]; assert "EPIC-xxx" not in ids`
  style used by `test_epic_excluded_from_json_and_include_blocked`
  (`test_next_issues.py:925-965`) [Agent 3 finding]

### Documentation
- N/A — no CLI flag or documented contract changes; `docs/reference/CLI.md`'s
  `sequence` entry describes default output as "active issues", which stays
  accurate

### Configuration
- N/A

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-12 — based on codebase analysis:_

- **Correction to "Similar Patterns" claim**: `find_highest_priority_issue` (`scripts/little_loops/issue_parser.py:4523-4543`) has no EPIC-specific logic — it is a thin wrapper over `find_issues()` and returns whatever sorts first, EPICs included when no `type_prefixes` filter is passed. The actual EPIC-exclusion convention this issue's Motivation points at lives in `cmd_next_issue` (`scripts/little_loops/cli/issues/next_issue.py:46-62,90-103`) and `cmd_next_issues` (`scripts/little_loops/cli/issues/next_issues.py:43-53,82-86`), both of which unconditionally exclude EPICs via `not issue_id.startswith("EPIC-")` and cite BUG-2638 in a comment ("EPICs are umbrella containers meant to be decomposed via scope resolution, never ranked as implementable leaves").
- **Contested prefix-check convention**: two styles coexist for identifying an EPIC ID. `next_issue.py`/`next_issues.py` use `issue_id.startswith("EPIC-")` for unconditional exclusion; `list_cmd.py::_find_epic_ancestor` and `issue_progress.py::find_nearest_epic_ancestor` use `issue_id.split("-", 1)[0] == "EPIC"` for ancestor-walk/grouping (a different use case — bucketing, not exclusion) — and `sequence.py`'s own existing `--type` comparison at line 112 already uses this same split form. No shared `is_epic()` helper or `IssueType` enum exists anywhere in the codebase (searched repo-wide for both) — every check inlines one of the two forms at its call site.
- **Cross-reference behavior preserved by design, not by accident**: excluding EPICs from `display`/`shown` does not remove them from `graph` (`DependencyGraph.from_issues`, built from the unfiltered `graph_issues`). Per-issue `blocked_by`/`depends_on`/prerequisite lookups (`sequence.py:150,156,157,182,183,190,193`) query `graph` directly by ID for every issue still in `shown`, so a non-EPIC issue whose blocker is an EPIC will continue to show that EPIC's ID inside its own `blocked_by`/`depends_on` list in both JSON and human-readable output, even though the EPIC no longer gets its own row. This matches the issue's Scope Boundaries ("DependencyGraph... still needs to consider EPICs as graph nodes for correct blocker resolution") and is confirmed by direct trace of `cmd_sequence` (`sequence.py:57-206`).
- **Test fixture to reuse**: `issues_dir_with_epic` (`scripts/tests/test_issues_cli.py:157-165`) extends the base `issues_dir` fixture with an open `EPIC-001`. It is already used for `list --type EPIC` and `epic-progress` tests but is not currently combined with any `sequence` test. The existing `test_sequence_type_filter_epic` (`test_issues_cli.py:1617-1639`) uses the plain `issues_dir` fixture (no EPIC present) and only asserts `"No active issues"` for `--type EPIC` — it does not exercise a scenario with an actual open EPIC mixed among BUG/FEAT/ENH issues, so the new test case this issue's Implementation Steps calls for has no existing fixture pairing to extend from; it will need `issues_dir_with_epic` plus additional open BUG/FEAT/ENH issues alongside the EPIC.

## Implementation Steps

- In `cmd_sequence` (`scripts/little_loops/cli/issues/sequence.py`), exclude
  `issue.issue_id.split("-", 1)[0] == "EPIC"` from the `display` list unless
  `type_prefix == "EPIC"` is explicitly requested (mirror the existing
  `--type` opt-in pattern so `ll-issues sequence --type EPIC` still works if
  a user wants epic-only sequencing).
- Apply the same exclusion to both the `--json` and human-readable output
  paths (they share the `display`/`shown` lists, so one change covers both).
- Add/update a test asserting an open EPIC is absent from default `sequence`
  output but present when `--type EPIC` is passed.

## Program Design

### Signatures

- `cmd_sequence(config: BRConfig, args: argparse.Namespace) -> int` — unchanged
  signature; the `display` list-comprehension gains an `else` branch

### Call Path

`main_issues` (argparse `sequence` subcommand) -> `cmd_sequence` -> the
`display` filter (lines 110-112) -> both `--json` (`print_json`) and
human-readable (`print`) output loops, which already share `display`/`shown`

## Scope Boundaries

Out of scope: changing how EPICs are ranked or displayed elsewhere (e.g.
`ll-issues list`, `ll-issues show`, `review-epic`); changing
`DependencyGraph.topological_sort()` or the cycle-fallback ordering, which
still needs to consider EPICs as graph nodes for correct blocker resolution
even though they're excluded from the final `display` list; adding a new CLI
flag — `--type EPIC` already provides the opt-in path.

## Impact

- **Priority**: P3 - Cosmetic/workflow-clarity issue; doesn't block any
  implementation, just clutters a suggestion list
- **Effort**: Small - One conditional branch in an existing list
  comprehension, plus one new test case
- **Risk**: Low - Additive filter change; `--type EPIC` preserves prior
  behavior exactly, and no other caller consumes `cmd_sequence`'s internal
  `display` list
- **Breaking Change**: No - `ll-issues sequence --type EPIC` is unaffected;
  only the default (no `--type`) output changes, and only by omission of
  rows a user would skip past anyway

## API/Interface

No CLI flag changes — behavior-only fix to the default (no `--type`) output
of `ll-issues sequence`.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-12 | Priority: P3


## Session Log
- `/ll:manage-issue` - 2026-09-12T21:31:42 - `eac40fef-b607-438b-bff6-67566b84f34a.jsonl`
- `/ll:ready-issue` - 2026-09-12T21:24:18 - `b44b9bd9-4763-4d6e-8f4e-ed8dabe39256.jsonl`
- `/ll:confidence-check` - 2026-09-12T19:17:22 - `6d577656-0598-43c3-917d-9dbaf7adf2b8.jsonl`
- `/ll:wire-issue` - 2026-09-12T19:08:49 - `6d577656-0598-43c3-917d-9dbaf7adf2b8.jsonl`
- `/ll:refine-issue` - 2026-09-12T18:51:58 - `cc741d48-cdac-4b5c-92b2-ee728ea0acac.jsonl`
- `/ll:format-issue` - 2026-09-12T18:43:43 - `3edf35b2-2e6f-4e1e-b1ac-43a234fbc175.jsonl`
- `/ll:capture-issue` - 2026-09-12T18:38:17 - `4cb9b3dd-b2a1-4370-87e3-0787c2fe0ed2.jsonl`
