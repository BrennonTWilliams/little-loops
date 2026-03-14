---
id: ENH-739
type: ENH
priority: P3
status: active
discovered_date: 2026-03-13
discovered_by: capture-issue
---

# ENH-739: create-sprint Should Surface Issue Refinement Status

## Summary

`/ll:create-sprint` has no awareness of issue refinement metadata (confidence scores, format version, normalization status) when suggesting or selecting issues for a sprint. Issues that are unformatted, unscored, or poorly refined are treated identically to fully-refined, implementation-ready ones. The `ll-issues refine-status` CLI is never consulted.

## Current Behavior

`/ll:create-sprint` scans active issues and groups them by priority, type, theme, component, and goal alignment (Step 1.5). It reads only: priority, type, ID, title, summary, file paths, goal alignment, and blocked-by. No refinement metadata is read or surfaced.

## Expected Behavior

When presenting grouping suggestions or the interactive issue list, `/ll:create-sprint` should:

1. **Flag unrefined issues** — issues missing `confidence_score`, `outcome_confidence`, or with un-formatted frontmatter should be visually marked (e.g., `⚠ unscored`) in the selection UI
2. **Offer a `refined-only` grouping strategy** — a grouping that filters to issues with `confidence_score >= threshold` (e.g., 60), surfaced as a grouping option alongside the existing strategies
3. **Warn on selection** — if the user selects a grouping or manually picks issues that include unrefined ones, show a summary warning before writing the sprint YAML: "3 of 7 selected issues have no confidence score — run `/ll:confidence-check` first"

`ll-issues refine-status` (or the equivalent Python API) should be used to determine refinement state.

## Motivation

A sprint is meant to be a curated, execution-ready list. Including issues that haven't been normalized, formatted, or confidence-checked undermines the quality guarantee that sprints provide and can lead to poor outcomes during `ll-sprint run`.

## Implementation Steps

1. **Add `Bash(ll-issues:*)` to allowed-tools** (`create-sprint.md:4`): without this, Step 5 cannot call `ll-issues refine-status`. Add alongside existing `Bash(mkdir:*)`.

2. **Extend the issue-parsing loop** (`create-sprint.md:129-146`): add `confidence_score` and `outcome_confidence` to the frontmatter fields extracted per issue. `is_normalized` can be derived from the filename pattern alone (no read needed). Follow the existing `goal_alignment` extraction pattern at line 142.

3. **Add Grouping Strategy 7** after `create-sprint.md:200` (end of Strategy 6):
   - Name: `refined-ready`
   - Description: "Issues with confidence score ≥ threshold (implementation-ready)"
   - Criteria: Issues where `confidence_score >= config.commands.confidence_gate.threshold` (default 60, from `config-schema.json`)
   - Minimum: Only suggest if 3+ issues match
   - Follow the four-field format of Strategies 1–6 (see `create-sprint.md:152-200`)

4. **Annotate issue IDs in Step 1.5.3** (`create-sprint.md:208-263`): in the `description` field of each `AskUserQuestion` option, append `⚠ unscored` after issue IDs where `confidence_score` is null. Follow the `⚠` glyph conventions from `manage-issue/SKILL.md:158-185`.

5. **Add post-validation refinement warning in Step 4** (`create-sprint.md:334-342`): after issue existence is confirmed, call `ll-issues refine-status --json` via Bash (JSON array output at `refine_status.py:207-225`), filter to selected issue IDs, count those with `confidence_score: null` or `normalized: false`, and emit:
   ```
   ⚠ X of Y selected issues have no confidence score — run /ll:confidence-check first
   ⚠ Z of Y selected issues are not normalized — run /ll:normalize-issues first
   ```
   Only emit each line if the count is > 0. Do not block sprint creation — this is a warning only.

## Success Metrics

- Sprint creation warns when unrefined issues are included
- A `refined-ready` grouping strategy appears when enough scored issues exist
- No regression to existing grouping strategies or sprint YAML output format

## Integration Map

### Files to Modify
- `commands/create-sprint.md:4` — add `Bash(ll-issues:*)` to `allowed-tools` frontmatter (prerequisite for any `ll-issues refine-status` Bash call)
- `commands/create-sprint.md:129-146` — Step 1.5.1 issue-parsing loop: extend to also extract `confidence_score` and `outcome_confidence` from frontmatter, and compute `is_normalized` from filename
- `commands/create-sprint.md:200` — append Grouping Strategy 7 (`refined-ready`) after Strategy 6 ends here; follow four-field structure: Name / Description / Criteria / Minimum
- `commands/create-sprint.md:208-263` — Step 1.5.3 AskUserQuestion template: annotate issue IDs with `⚠ unscored` when `confidence_score` is `null`
- `commands/create-sprint.md:334-342` — Step 4 validation: add post-existence check that calls `ll-issues refine-status --json`, counts unscored/unformatted issues among selected, and emits a warning block

### Data Source
- `scripts/little_loops/cli/issues/refine_status.py:155-377` — `cmd_refine_status`; invokable via `ll-issues refine-status --json` to get per-issue `confidence_score`, `outcome_confidence`, `normalized`, `formatted`, `refine_count`; `--json` output at lines 207-225
- `scripts/little_loops/issue_parser.py:200-236` — `IssueInfo` dataclass with `confidence_score: int | None` (line 233) and `outcome_confidence: int | None` (line 234)
- `scripts/little_loops/issue_parser.py:32-95` — `is_normalized(filename)` (regex check) and `is_formatted(path)` (checks for `/ll:format-issue` in Session Log or required section headings); **note**: there is no `format_version` frontmatter field — format status is determined programmatically by `is_formatted()`
- `scripts/little_loops/cli/issues/__init__.py:108-133` — `refine-status` subparser with `--json` and `--format json` flags
- `config-schema.json` — `confidence_threshold` key; read for the configurable threshold used in Strategy 7 criteria

### Existing Pattern to Follow
- `commands/create-sprint.md:350-376` — existing `python -c` Bash block in Step 4.5 invoking `find_issues()` + `analyze_dependencies()`; the same inline-Python approach can be used for refinement checking if `ll-issues refine-status --json` is insufficient

### Related Commands
- `commands/confidence-check.md` — referenced in the warning message as the remediation step when unscored issues are selected

### Tests
- `scripts/tests/test_refine_status.py` — existing tests for `refine-status`; add tests for `--json` output fields consumed by `create-sprint`
- `scripts/tests/test_sprint.py` — existing sprint unit tests; add tests for refinement-aware grouping logic if any Python sprint module is modified

## Session Log
- `/ll:capture-issue` - 2026-03-13T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d8e28361-4391-4bff-b45e-f80ac3adb2ce.jsonl`
- `/ll:refine-issue` - 2026-03-13T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3777c8ff-1714-43df-b4e3-5fada0728038.jsonl`
