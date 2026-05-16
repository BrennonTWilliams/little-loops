---
id: ENH-739
type: ENH
priority: P3
status: completed
discovered_date: 2026-03-13
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 78
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
   - Criteria: Issues where `confidence_score >= config.commands.confidence_gate.readiness_threshold` (default 85, from `config-schema.json:278-283`)
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

## Scope Boundaries

- **In scope**: Surfacing `confidence_score`, `outcome_confidence`, and normalized status in the `/ll:create-sprint` selection UI; adding `refined-ready` grouping strategy (Strategy 7); emitting a warning block after issue selection if unscored or unnormalized issues are included
- **Out of scope**: Blocking sprint creation based on refinement status (warning-only); auto-invoking `/ll:confidence-check` on behalf of the user; modifying sprint YAML format or `ll-sprint run` execution behavior; enforcing refinement thresholds retroactively on existing sprints

## API/Interface

N/A — No public API changes. This enhancement modifies only the behavior of the `commands/create-sprint.md` command. No Python module interfaces, CLI flags, or YAML schema fields are added or changed.

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
- `config-schema.json:269-293` — `commands.confidence_gate` object with `readiness_threshold` (default 85) and `outcome_threshold` (default 70); Strategy 7 should use `readiness_threshold` for filtering. Note: there is no single `confidence_threshold` or `threshold` key — the gate uses two distinct thresholds.

### Existing Pattern to Follow
- `commands/create-sprint.md:350-376` — existing `python -c` Bash block in Step 4.5 invoking `find_issues()` + `analyze_dependencies()`; the same inline-Python approach can be used for refinement checking if `ll-issues refine-status --json` is insufficient

### Related Commands
- `commands/confidence-check.md` — referenced in the warning message as the remediation step when unscored issues are selected

### Tests
- `scripts/tests/test_refine_status.py` — existing tests for `refine-status`; add tests for `--json` output fields consumed by `create-sprint`
- `scripts/tests/test_sprint.py` — existing sprint unit tests; add tests for refinement-aware grouping logic if any Python sprint module is modified

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis (2026-03-14):_

**Verified accurate:**
- `create-sprint.md:4-5` — `allowed-tools: - Bash(mkdir:*)` only; no `ll-issues` allowed
- `create-sprint.md:129-146` — loop extracts Priority, Type, ID, Title, Summary, File Paths (line 142), Goal Alignment (line 143), Blocked By (line 144); no confidence fields
- `create-sprint.md:200` — Strategy 6 ends here; Strategy 7 insertion point confirmed
- `create-sprint.md:208-263` — AskUserQuestion format: `description: "${grouping_description}: ${first_3_issue_ids}..."` pattern confirmed
- `create-sprint.md:334-342` — Step 4 Glob-only issue validation; no refinement check
- `create-sprint.md:350-376` — `python -c` inline Bash pattern confirmed (dependency analysis block)
- `refine_status.py:206-225` — `--json` flag outputs a single JSON **array** (not NDJSON); `--format json` (lines 227-243) outputs NDJSON. Recommend using `--json` for step 5 implementation.
- `refine_status.py` JSON fields: `id`, `priority`, `title`, `source`, `commands`, `confidence_score`, `outcome_confidence`, `total`, `normalized`, `formatted`, `refine_count`
- `issue_parser.py:201-234` — `IssueInfo` dataclass confirmed; `confidence_score: int | None = None` (line 233), `outcome_confidence: int | None = None` (line 234)
- `issue_parser.py:32-41` — `is_normalized(filename: str)` checks regex `^P[0-5]-(BUG|FEAT|ENH)-[0-9]{3,}-[a-z0-9-]+\.md$`
- `issue_parser.py:44-95` — `is_formatted(issue_path, templates_dir)` checks session log OR required section headings
- `cli/issues/__init__.py:108-133` — `refine-status` subparser: `--type`, `--format table|json`, `--no-key`, `--json` flags confirmed

**Corrected (factual error fixed above):**
- Config threshold key is `commands.confidence_gate.readiness_threshold` (default **85**), NOT `confidence_gate.threshold` (default 60). The gate object at `config-schema.json:269` has `readiness_threshold` and `outcome_threshold` as separate keys.

## Verification Notes

_Added by `/ll:verify-issues` — 2026-03-13:_

**Verdict: VALID** — All file/line references verified against current codebase.

**All references confirmed accurate:**
- `create-sprint.md:4` allowed-tools; lines 129-146 parse loop (no confidence fields); line 200 Strategy 6 end; lines 208-263 AskUserQuestion format; lines 334-342 Glob-only validation; lines 350-376 python -c pattern
- `refine_status.py:155` cmd_refine_status; lines 206-225 --json array output with all 11 JSON fields
- `issue_parser.py:200-236` IssueInfo (confidence_score line 233, outcome_confidence line 234); lines 32-41 is_normalized; lines 44-95 is_formatted
- `cli/issues/__init__.py:108-133` refine-status subparser flags
- `config-schema.json:269-293` confidence_gate (readiness_threshold=85, outcome_threshold=70)
- `manage-issue/SKILL.md:158-185` ⚠/✓/✗ glyph conventions

**Minor inconsistency (low impact):**
- Implementation Step 2 says "goal_alignment extraction pattern at line 142" — but line 142 is `File Paths`; Goal Alignment is at line 143. Codebase Research Findings already has the correct value (143).

## Resolution

**Status**: Completed
**Resolved**: 2026-03-13

### Changes Made

- `commands/create-sprint.md:4-5` — Added `Bash(ll-issues:*)` to `allowed-tools` frontmatter
- `commands/create-sprint.md` (Step 1.5.1) — Extended issue-parsing loop to extract `confidence_score`, `outcome_confidence`, and `is_normalized` (derived from filename regex)
- `commands/create-sprint.md` (Strategy 7) — Added **Grouping Strategy 7: Refined-Ready** filtering to issues with `confidence_score >= readiness_threshold` (default 85), minimum 3 issues
- `commands/create-sprint.md` (Step 1.5.3) — Issue IDs with `confidence_score: null` are now annotated with `⚠ unscored` in the AskUserQuestion description field
- `commands/create-sprint.md` (Step 4) — Added post-validation refinement warning block using `ll-issues refine-status --json`; emits count-based warnings for unscored/unnormalized issues (warning-only, non-blocking)

### Verification

- All 5 implementation steps completed per issue spec
- 100 tests pass with no regressions (`test_refine_status.py`, `test_sprint.py`, full suite)
- No Python module changes required (command-only modification)

## Session Log
- `/ll:verify-issues` - 2026-03-13T22:35:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/16895bc4-60f4-4b6e-a29f-644e32561c70.jsonl`
- `/ll:format-issue` - 2026-03-13T22:35:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/16895bc4-60f4-4b6e-a29f-644e32561c70.jsonl`
- `/ll:confidence-check` - 2026-03-13T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/16895bc4-60f4-4b6e-a29f-644e32561c70.jsonl`
- `/ll:capture-issue` - 2026-03-13T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d8e28361-4391-4bff-b45e-f80ac3adb2ce.jsonl`
- `/ll:refine-issue` - 2026-03-13T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3777c8ff-1714-43df-b4e3-5fada0728038.jsonl`
- `/ll:refine-issue` - 2026-03-14T03:28:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d69664f2-c580-4a55-b04c-9cddea5b7fc0.jsonl`
- `/ll:ready-issue` - 2026-03-13T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/79db2260-5c88-444e-ae14-972851796d53.jsonl`
- `/ll:manage-issue` - 2026-03-13T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fffc83c9-009a-4696-8010-040737bf7247.jsonl`
