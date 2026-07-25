---
discovered_commit: fb5673902939bbf5a17bc7afe61317982d40bfd2
discovered_branch: main
discovered_date: 2026-07-24 22:31:44+00:00
discovered_by: scan-codebase
completed_at: '2026-07-25T07:51:52Z'
confidence_score: 90
outcome_confidence: 73
score_complexity: 16
score_test_coverage: 22
score_ambiguity: 15
score_change_surface: 20
status: done
---

# FEAT-2786: Cycle-breaking strategy for `ll-deps` dependency auto-fix

## Summary

`fix_dependencies()` (invoked by `ll-deps`) auto-repairs broken refs, stale
completed refs, and missing backlinks, but circular `Blocked By` chains are
only detected, counted (`skipped_cycles` in `FixResult`), and left
unmodified. No cycle-breaking strategy exists.

## Location

- **File**: `scripts/little_loops/dependency_mapper/operations.py`
- **Line(s)**: 189-213 (docstring note at 202, at scan commit: fb567390)
- **Anchor**: `in function fix_dependencies()`; companion field `skipped_cycles` in `dependency_mapper/models.py:112`
- **Code**:
```python
def fix_dependencies(
    issues: list[IssueInfo],
    ...
) -> FixResult:
    """Auto-repair broken dependency references.
    ...
    Cycles are explicitly out of scope and are skipped with a count.
```

## Current Behavior

Cyclic dependencies survive every `ll-deps` fix run; affected issues stay
mutually blocked until a human hand-edits an edge.

## Expected Behavior

`ll-deps` offers a cycle-resolution path — at minimum reporting each cycle's
edges with a suggested edge to drop; optionally an interactive or
`--break-cycles` mode that removes the chosen edge and its backlink.

## Use Case

Autodev/`ll-auto` dequeue skips mutually-blocked issues silently; a curated
cycle-breaking pass restores them to the ready pool without manual file
surgery.

## Acceptance Criteria

- Cycles are enumerated with their member edges in fix output (not just a count)
- A suggested minimal edge-cut is proposed per cycle (e.g. lowest-priority edge)
- Opt-in flag applies the cut, maintaining bidirectional consistency
- `dry_run` shows the plan without writing

## Proposed Solution

Detect cycles via the existing `DependencyGraph`, pick a break edge
heuristically (newest edge or lowest-priority blocker), and route removal
through the same backlink-consistent write path the other three fix
categories use.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Cycle detection already exists and is reused directly** — `fix_dependencies()`
(`operations.py:189-258`) calls `validate_dependencies()`
(`dependency_mapper/analysis.py:416-484`), which builds a `DependencyGraph` via
`DependencyGraph.from_issues()` and calls `graph.detect_cycles()`
(`dependency_graph.py:355-407`, standard 3-color WHITE/GRAY/BLACK DFS over the
union of `blocked_by` and `depends_on_edges`). The result is stored as
`ValidationResult.cycles: list[list[str]]` — each entry is a closed walk of
issue IDs, e.g. `["A", "B", "C", "A"]`. `fix_dependencies()`'s only use of this
today is `result.skipped_cycles = len(validation.cycles)` (last line before
`return result`) — the cycle *paths* are discarded after taking the count. This
is the exact hook point for the new logic.

**No date/timestamp field exists on `IssueInfo`** — a "newest edge" heuristic
has no in-model field to read (`issue_parser.py:568-647` enumerates all
`IssueInfo` fields; no `created_date`/`updated_date`). "Newest edge" would need
`issue.path.stat().st_mtime` or another out-of-band signal. `priority_int`
(`issue_parser.py:640-647`, parses `P(\d+)`, lower = higher priority, `99` for
unparseable) is readily available and is the field the codebase's own
tie-break convention already uses (see below) — favor "lowest-priority edge"
over "newest edge" for the heuristic.

**Existing priority tie-break pattern to model the heuristic after** —
`find_file_overlaps()` (`analysis.py:243-413`, tie-break at 360-390) already picks which of two
issues should block the other using `priority_int` as primary signal, with a
deterministic lexicographic-ID fallback (reduced `confidence_modifier`) when
priorities tie. `DependencyGraph.topological_sort()` and `get_ready_issues()`
both sort on the same `(priority_int, issue_id)` tuple — this is the
established convention in this module, not a one-off.

**Backlink-consistent write primitives to reuse** — `operations.py` already has
`_remove_from_section(file_path, section_name, issue_id) -> bool` (132-186,
returns whether a change was made) and `_add_to_section(file_path,
section_name, issue_id) -> None` (66-129). A cycle-cut removing edge `X
blocked_by Y` needs a **paired** two-file removal:
`_remove_from_section(X_path, "Blocked By", Y)` *and*
`_remove_from_section(Y_path, "Blocks", X)`. None of the three existing fix
categories perform this paired removal in one transaction today (broken-ref
and stale-ref removal only touch the source's `Blocked By`; `missing_backlinks`
handles the *addition* side separately). `apply_proposals()` (`operations.py:
21-63`) does show the mirrored-write shape for *adding* an edge
(`_add_to_section` on both source and target) — same pairing pattern, inverse
operation.

**CLI flag convention choice** — `ll-deps fix` currently only has
`--dry-run`/`-n` and `--sprint` (`cli/deps.py:160-176`); dry_run gates every
mutating call but `result.changes` is still populated for reporting. Two
opt-in-flag conventions coexist in this codebase: `ll-deps fix`/`apply` mutate
by default with `--dry-run` as opt-in preview, while `ll-adapt` inverts this
(dry-run default, `--apply` opt-in mutate — see `cli/adapt.py:54-66`). Given
`fix_dependencies()`'s existing default-mutates/`--dry-run`-previews
convention, a new `--break-cycles` flag (opt-in, defaulting off, independent of
`--dry-run`) fits the established `ll-deps fix` pattern better than inverting
to an `--apply`-style flag.

**Reporting path to extend** — `cli/deps.py`'s `fix` handler (510-539) prints
`f"({fix_result.skipped_cycles} cycle(s) detected — resolve manually)"` in two
places (early-return branch and normal-report branch) when `skipped_cycles` is
nonzero. Per-cycle edge enumeration (AC 1) and the suggested-cut line (AC 2)
should be appended to `result.changes` alongside the existing per-category
change strings, so both branches pick it up without duplicating print logic.

**Test patterns to follow** — `test_dependency_mapper.py::TestFixDependencies`
has `test_skips_cycles` (asserts `skipped_cycles > 0` and no `"cycle"` string
in `result.changes` today — this assertion will need updating once cycles
produce change entries) and `test_dry_run_no_file_changes` (asserts
byte-identical file content under `dry_run`). `test_dependency_graph.py::
TestCycleDetection` has fixtures for simple/longer/mixed-edge-type cycles
(`test_simple_cycle`, `test_longer_cycle`,
`test_mixed_blocked_by_depends_on_cycle_detected`) usable directly for
cycle-cut test setup. `TestMainCLIFix._setup_fix_project()` builds a real
`.issues/` tree via `tmp_path` for CLI-level `ll-deps fix` tests — model any
`--break-cycles` CLI test after this.

## Integration Map

### Files to Modify
- `scripts/little_loops/dependency_mapper/operations.py` — extend `fix_dependencies()` (189-258) to act on `validation.cycles` instead of only counting it; add a cycle-cut helper that pairs `_remove_from_section()` calls (132-186) on both endpoints of the chosen edge
- `scripts/little_loops/dependency_mapper/models.py` — `FixResult` (105-118): `skipped_cycles` semantics change (or a new field is added) once cycles can be broken vs. merely reported
- `scripts/little_loops/cli/deps.py` — `fix` subparser (160-176): add `--break-cycles` flag; `fix` handler (510-539): extend/replace the two `"cycle(s) detected — resolve manually"` print sites to surface enumerated edges + suggested cut

### Dependent Files (Callers/Importers)
- `scripts/little_loops/dependency_mapper/analysis.py:480-483` — `validate_dependencies()` is the sole producer of `ValidationResult.cycles`, consumed by `fix_dependencies()`
- `scripts/little_loops/dependency_graph.py` — `DependencyGraph.from_issues()` (55-145) and `detect_cycles()` (355-407) are the reused detection primitives; also called by `topological_sort()` and `get_execution_waves()`, which raise on residual cycles

### Similar Patterns
- `scripts/little_loops/dependency_mapper/analysis.py:243-413` (`find_file_overlaps()`, tie-break at 360-390) — priority-then-ID tie-break heuristic to model the edge-cut selection after
- `scripts/little_loops/dependency_mapper/operations.py:21-63` (`apply_proposals()`) — paired two-file `_add_to_section()` write shape; inverse operation of the paired removal a cycle-cut needs

### Tests
- `scripts/tests/test_dependency_mapper.py::TestFixDependencies` — `test_skips_cycles` (1786-1918 range) needs updating once cycles produce `result.changes` entries; `test_dry_run_no_file_changes` (1871-1890) is the dry-run assertion pattern to extend
- `scripts/tests/test_dependency_graph.py::TestCycleDetection` (443-529) — existing simple/longer/mixed-edge-type cycle fixtures, reusable for cycle-cut setup
- `scripts/tests/test_dependency_mapper.py::TestMainCLIFix` (from 1926) — `_setup_fix_project()` tmp_path helper for CLI-level `ll-deps fix` tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_cli_deps.py` — CLI-layer `ll-deps` subcommand tests (separate file from `test_dependency_mapper.py`'s unit tests); check for stdout assertions on the `"cycle(s) detected — resolve manually"` message that a `--break-cycles` output change would affect
- `scripts/tests/test_deps_cli.py` — CLI-level `ll-deps tree` tests; check for any cycle-related output assertions before changing the fix report format

### Documentation
_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md` — `#### ll-deps fix` flags table only lists `--dry-run`/`-n` and `--sprint` today; add a `--break-cycles` row, plus a `ll-deps fix --break-cycles` line in the command's `Examples:` block (mirrors how `--dry-run` got its own example line)
- `docs/reference/API.md` — `## little_loops.dependency_mapper` currently has no dedicated `### FixResult` doc block for this module's `FixResult` (the only existing `FixResult` anchor in the file documents an unrelated `doc_counts.py` dataclass with the same name) — adding fields here needs a new subsection, not an edit to the existing (wrong) anchor. The `### ValidationResult` block's `cycles: list[list[str]]` row should also be reviewed if cycle representation changes.
- `skills/map-dependencies/SKILL.md` — workflow narrative (~lines 103, 183, 202-206) describes `ll-deps apply` → `ll-deps fix` → `ll-deps validate` but doesn't mention cycle-breaking as a `fix` responsibility; add a step/bullet if `--break-cycles` becomes part of the recommended workflow
- `CHANGELOG.md` — per project convention, land the entry under a concrete `## [X.Y.Z] - DATE` section (never `[Unreleased]`)

## Impact

- **Scope**: Medium

## Status

`done` — implemented by `/ll:manage-issue`.

## Resolution

Extended `fix_dependencies()` (`dependency_mapper/operations.py`) to act on
`validation.cycles` instead of only counting it:

- Every detected cycle is now enumerated in `FixResult.changes` (member edges
  as a `A -> B -> A` walk) with a suggested edge cut, always — regardless of
  `--break-cycles`.
- The cut heuristic (`_select_cycle_cut`) picks the edge whose source issue
  has the lowest priority (`priority_int`, tie-broken lexicographically),
  matching the priority-then-ID tie-break convention already used by
  `find_file_overlaps()`.
- New opt-in `ll-deps fix --break-cycles` flag applies the cut via
  `_cut_cycle_edge()`, which pairs `_remove_from_section()` calls on both
  endpoints for `blocked_by` edges (mirroring `apply_proposals()`'s paired
  write shape) or removes only the source's `## Depends On` entry for
  `depends_on` edges (no reciprocal section exists for those).
- `dry_run` reports the planned cut ("Would cut cycle edge: ...") without
  writing.
- `FixResult` gained a `cycles: list[list[str]]` field for programmatic
  access to the raw cycle paths alongside the human-readable `changes`.
- `ll-deps fix` CLI output and `docs/reference/{CLI,API}.md` /
  `skills/map-dependencies/SKILL.md` updated to document `--break-cycles`.

## Session Log
- `/ll:manage-issue` - 2026-07-25T07:51:06 - `7e403b1f-1510-42d0-83f2-d160714eabf0.jsonl`
- `/ll:ready-issue` - 2026-07-25T07:42:38 - `9676e309-f195-430e-908f-0273f2d13485.jsonl`
- `/ll:wire-issue` - 2026-07-25T07:39:10 - `4cd358c6-8a9c-45eb-bde5-e079a57ec503.jsonl`
- `/ll:refine-issue` - 2026-07-25T07:35:00 - `8ee2b34f-c621-4a0f-bfae-0c771b5e8be4.jsonl`
- `/ll:scan-codebase` - 2026-07-24T22:41:56 - `16c799a6-5ff5-423f-b842-dcdb0fc751f1.jsonl`
