---
id: ENH-1727
type: ENH
priority: P3
status: done
captured_at: '2026-05-26T20:32:38Z'
completed_at: '2026-05-27T02:24:25Z'
discovered_date: 2026-05-26
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 93
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
---

# ENH-1727: Add `--group-by epic` option to `ll-issues list`

## Summary

`ll-issues list` currently groups issues by type (BUG / FEAT / ENH / EPIC). Add a `--group-by epic` flag that instead groups child issues under their parent epic, with an "Unparented" bucket for issues that have no `parent:` set. The `parent` field is already parsed on `IssueFile` — this is a display-only change.

## Current Behavior

`ll-issues list` always outputs four fixed type buckets (Bugs, Features, Enhancements, Epics). There is no way to see which issues belong to a given epic without opening each file individually or using `ll-deps`.

## Expected Behavior

`ll-issues list --group-by epic` outputs issues grouped by their parent epic:

```
EPIC-1663: Sprint Runner Improvements (3)
  P3  ENH-1727  Add --group-by epic option to ll-issues list
  ...

Unparented (12)
  P2  BUG-1700  ...
```

## Motivation

Developers working within an epic want a quick way to see the full scope of child issues without switching to `ll-deps`. Grouping by epic gives a natural project-plan view alongside the existing type-grouped view.

## Proposed Solution

1. Add `--group-by {type,epic}` argument to the `list` subparser (default: `type` to preserve existing behaviour).
2. In `cmd_list`, branch on `args.group_by`:
   - `"type"` — existing logic unchanged.
   - `"epic"` — bucket issues by `issue.parent`, with `None` → "Unparented". Sort buckets so named epics come first (alphabetically by EPIC ID), unparented last.
3. For each epic bucket header, optionally resolve the epic title by looking up the matching EPIC issue file.

## API/Interface

New CLI argument added to `ll-issues list`:

```
--group-by {type,epic}
    Group output by issue type (default, existing behaviour preserved)
    or by parent epic ID.
```

No Python API changes — the grouping logic is internal to `cmd_list`.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/issues/list_cmd.py` — add epic-grouping branch at lines 134–155 (after the `--flat` early-return at line 129; before the type-bucket block at line 134)
- `scripts/little_loops/cli/issues/__init__.py` — add `--group-by` argument to the `ls` subparser (lines 118–182, before `add_config_arg(ls)` at line 182)

### Dependent Files (Callers/Importers)
- No callers of `cmd_list` beyond the dispatch block at `__init__.py:634` — changes are internal

### Similar Patterns
- `scripts/little_loops/cli/issues/list_cmd.py:134–155` — exact type-bucket grouping pattern to model the epic-grouping branch after (build a `buckets` dict, fill from issues, render headers with `colorize`, emit rows with `colored_priority` + `colored_id` + title)
- `scripts/tests/test_issues_cli.py:71–79` — `issues_dir_with_epic` fixture (creates `P2-EPIC-001-parent-initiative.md`) shows how to add fixture files for EPIC tests

### Tests
- `scripts/tests/test_issues_cli.py` — `TestIssuesCLIList` class (line 82) — all new tests go here; there is **no** `test_issues_list.py`
- Unit test: issues with `parent: EPIC-NNN` frontmatter appear under the correct epic bucket header
- Unit test: issues with no `parent:` field appear under "Unparented" bucket
- Unit test: `--group-by type` (default, or omitted) still produces identical output to current behaviour

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_cli_output.py` — `TestIssueListNoColor.test_no_color_produces_plain_text` (line 327) — builds a bare `argparse.Namespace(type=None, priority=None, flat=False)` without `group_by`; if `cmd_list` accesses `args.group_by` directly (not via `getattr`), this test will break — add `group_by="type"` to the Namespace [Agent 3 finding]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md` — `ll-issues list` flag table at line 648 (section `#### ll-issues list / ll-issues l`); add `--group-by {type,epic}` row describing the new flag [Agent 2 finding]

### Configuration
- N/A — no config changes required

## Implementation Steps

1. **Add `--group-by` argument** — in `scripts/little_loops/cli/issues/__init__.py`, insert after line 181 (the `--milestone` argument block, before `add_config_arg(ls)`):
   ```python
   ls.add_argument(
       "--group-by",
       choices=["type", "epic"],
       default="type",
       dest="group_by",
       help="Group output by issue type (default) or parent epic ID",
   )
   ```

2. **Add epic-grouping branch in `cmd_list`** — in `scripts/little_loops/cli/issues/list_cmd.py`, after line 132 (`return 0`, end of `--flat` block) and before line 134 (`# Group by type prefix`). After the existing `--json` (line 110) and `--flat` (line 129) early-return blocks, branch on `args.group_by`:
   - `"type"` path: existing lines 135–155 unchanged
   - `"epic"` path: bucket by `issue.parent` (`None` → `"Unparented"`), sort named epics alphabetically by epic ID, append unparented last; for each epic bucket header, resolve title by calling `config.issues_path` to find the matching EPIC file and reading its `# EPIC-NNN: Title` H1 (use `IssueFile.title` if the EPIC is loaded, or regex on the H1 line)

3. **Epic title resolution** — use `_load_issues_with_status` results already in scope: filter for `issue.issue_id.startswith("EPIC-")` to build an `{epic_id: title}` lookup dict before rendering the epic buckets. This avoids extra file reads since EPIC files are already loaded.

4. **Write tests** — add to `scripts/tests/test_issues_cli.py` inside `TestIssuesCLIList`:
   - Extend `issues_dir_with_epic` fixture (line 72) to include child issues with `parent: EPIC-001` in their frontmatter
   - `test_list_group_by_epic_parented`: checks EPIC-001 bucket header and child issue appears beneath it
   - `test_list_group_by_epic_unparented`: checks issues with no `parent:` appear under "Unparented" bucket
   - `test_list_group_by_type_default`: confirms omitting `--group-by` produces same output as `--group-by type`

5. **Verify `--flat` and `--json` unaffected** — both early-return before the grouping branch; no changes needed; covered by existing tests

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

6. Update `docs/reference/CLI.md` — add `--group-by {type,epic}` row to the `ll-issues list` flag table (after the `--priority` row around line 651, before `--label`)
7. Update `scripts/tests/test_cli_output.py` — add `group_by="type"` to the bare `argparse.Namespace` in `TestIssueListNoColor.test_no_color_produces_plain_text` (line 327) to prevent `AttributeError` if `cmd_list` uses direct attribute access

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `scripts/little_loops/cli/issues/list_cmd.py:134–155` — type-bucket grouping pattern: `buckets: dict[str, list] = {"BUG": [], "FEAT": [], "ENH": [], "EPIC": []}` → fill per-issue by `issue.issue_id.split("-", 1)[0]` → render with `colorize(f"{label} ({len(group)})", ...)`. Epic-grouping branch should follow same render signature.
- `scripts/little_loops/cli/issues/__init__.py:118–182` — `ls` subparser block. `--group-by` goes between `--milestone` (line 179) and `add_config_arg(ls)` (line 182).
- `scripts/little_loops/issue_parser.py:251` — `parent: str | None = None` on `IssueFile`; populated at line 334 and 491–497 (with deprecated `parent_issue:` alias handling). **No model changes needed.**
- `scripts/tests/test_issues_cli.py:71–79` — `issues_dir_with_epic` fixture: writes `"# EPIC-001: Parent initiative\n\n## Summary\nTop-level grouping."` — note it does **not** include frontmatter `parent:` on child issues; new test fixture variants must add `parent: EPIC-001` in frontmatter of child issues to exercise `issue.parent`.
- EPIC title resolution: build from `raw` (pre-type-filter list), **not** `issues_with_status` — `--type BUG --group-by epic` would filter out EPICs from `issues_with_status`, breaking header resolution. Use `epic_titles = {i.issue_id: i.title for i, _ in raw if i.issue_id.startswith("EPIC-")}` so headers always resolve regardless of `--type` filter.
- `parent` values are not guaranteed to be EPIC-prefix (e.g., `parent: ENH-1391` is valid). When grouping by epic, bucket by `issue.parent` regardless of the parent's type prefix; render the bucket header as `"{parent_id}: {title}"` if the parent is in `raw`, otherwise just `"{parent_id}"`.

## Scope Boundaries

- No changes to the `IssueFile` data model — the `parent` field already exists
- `--flat` and `--json` output modes are unaffected (they bypass grouping display entirely)
- No filtering by epic — this is grouping-display only
- No changes to `ll-deps` epic relationship commands
- Does not add sorting controls beyond alphabetical-by-EPIC-ID for bucket headers; unparented bucket always last

## Impact

- **Priority**: P3 - Quality-of-life for epic-centric workflows
- **Effort**: Small — data already available, pure display change
- **Risk**: Low — new flag with default preserving existing behaviour
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`cli`, `issues`, `epics`, `captured`

## Session Log
- `/ll:ready-issue` - 2026-05-27T02:18:22 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/01cdd312-a82e-4fc3-9f8d-a582dd91db5b.jsonl`
- `/ll:confidence-check` - 2026-05-27T01:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ca60f941-c956-4861-b798-811fcaf0e874.jsonl`
- `/ll:wire-issue` - 2026-05-27T00:39:56 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8f67938c-cbb3-4914-bee5-0317a112a94e.jsonl`
- `/ll:refine-issue` - 2026-05-27T00:34:09 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/276b0668-a79f-456b-bedc-b6bd95271676.jsonl`
- `/ll:format-issue` - 2026-05-26T20:40:41 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/76dc2061-8005-4612-bcf4-1672e52ae597.jsonl`
- `/ll:capture-issue` - 2026-05-26T20:32:38Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b05a1db1-f9bd-43eb-b427-427c3cdbc0ac.jsonl`

---

## Status

**Open** | Created: 2026-05-26 | Priority: P3
