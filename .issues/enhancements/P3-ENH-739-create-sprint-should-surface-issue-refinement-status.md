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

1. In Step 1.5.1 of `commands/create-sprint.md`, extend the issue-parsing loop to also extract from frontmatter: `confidence_score`, `outcome_confidence`, and whether required v2.0 fields are present
2. Add a **Grouping Strategy 7: Refined Issues** — filter to issues where `confidence_score >= 60` (or configurable threshold); name: `refined-ready`
3. In Step 1.5.3 (Present Suggestions), annotate each issue ID with a warning glyph if it lacks a confidence score
4. In Step 4 (Validate Issues Exist), after validation, check refinement status of selected issues and emit a warning block if any are unscored/unformatted
5. Consider calling `ll-issues refine-status` via Bash to get a structured summary rather than parsing frontmatter manually

## Success Metrics

- Sprint creation warns when unrefined issues are included
- A `refined-ready` grouping strategy appears when enough scored issues exist
- No regression to existing grouping strategies or sprint YAML output format

## Integration Map

- `commands/create-sprint.md` — primary change location (Steps 1.5.1, 1.5.2, 1.5.3, Step 4)
- `scripts/little_loops/` — `ll-issues refine-status` CLI for refinement data
- `commands/confidence-check.md` — referenced in warning message as remediation step

## Session Log
- `/ll:capture-issue` - 2026-03-13T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d8e28361-4391-4bff-b45e-f80ac3adb2ce.jsonl`
