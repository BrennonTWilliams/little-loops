# ENH-407: Add Theme-Based Sprint Grouping Options - Implementation Plan

## Issue Reference
- **File**: `.issues/enhancements/P3-ENH-407-create-sprint-theme-based-grouping-options.md`
- **Type**: enhancement
- **Priority**: P3
- **Action**: implement

## Current State Analysis

The `create_sprint` command at `commands/create_sprint.md` has an auto-grouping framework (Step 1.5, lines 120-240) added by FEAT-174. It currently provides four strategies:

1. **Priority Cluster** (lines 148-152) - Groups P0-P1 issues as `critical-fixes`
2. **Type Cluster** (lines 154-158) - Groups by most populous issue type
3. **Parallelizable Issues** (lines 160-164) - Groups unblocked issues as `parallel-ready`
4. **Theme Cluster** (lines 166-173) - Keyword matching on titles only, 4 hardcoded themes, returns only the single largest cluster

### Key Discoveries
- Step 1.5.1 (lines 128-142) extracts only priority, type, ID, title, and blocked-by — does NOT extract summary or file paths
- Strategy 4 matches only against issue titles (not summaries or body content)
- Strategy 4 returns only the largest theme cluster (line 173)
- Only 4 hardcoded keyword themes exist: test, performance, security, documentation
- No component-based or goal-aligned grouping strategies exist
- `ll-goals.md` does not currently exist in the repo; `product.enabled` is not set in config
- Existing Python utilities (`extract_file_paths`, `extract_file_hints`, `GoalsParser`) exist but are not needed since grouping logic is all prompt-based in the command markdown

### Patterns to Follow
- Strategy format: Name, Description, Criteria, Minimum threshold (commands/create_sprint.md:148-173)
- AskUserQuestion format: label with count, description with sample IDs (commands/create_sprint.md:184-196)
- "Select manually" always last option

## Desired End State

When `/ll:create_sprint` is run with no arguments, the auto-grouping section suggests **theme-based groupings** alongside existing mechanical groupings. Specifically:

1. **Expanded keyword themes** (Strategy 4) - More theme keywords, matching against both title AND summary, returning multiple qualifying theme clusters (not just the largest)
2. **Component-based grouping** (new Strategy 5) - Groups issues by which part of the codebase they reference (based on file paths found in issue content)
3. **Goal-aligned grouping** (new Strategy 6) - If `ll-goals.md` exists and `product.enabled` is true, groups issues by which product goal they align to

### How to Verify
- Run `/ll:create_sprint` with no arguments on a repo with active issues
- Verify theme-based groupings appear alongside existing options
- Verify component-based groupings appear if issues reference file paths
- Verify goal-aligned groupings are gracefully skipped when no goals file exists

## What We're NOT Doing

- Not replacing existing strategies 1-3 — this is purely additive
- Not changing the Python code — all changes are in the command prompt markdown
- Not implementing ML/NLP clustering — using simple keyword and file-path matching per scope boundaries
- Not auto-creating sprints — all groupings remain suggestions requiring user selection
- Not adding a `skills/create_sprint.md` wrapper (issue mentioned it but it doesn't exist and isn't needed)

## Solution Approach

Edit `commands/create_sprint.md` to:
1. Extend Step 1.5.1 to extract additional fields from issue content (summary, file paths)
2. Expand Strategy 4 with more keyword themes, broader matching, and multi-cluster output
3. Add Strategy 5 (Component-based grouping) based on file path directory prefixes
4. Add Strategy 6 (Goal-aligned grouping) with graceful skip when unavailable
5. Update scoring/selection to accommodate more potential groupings
6. Update the presentation example to show theme-based groupings

## Code Reuse & Integration

- **Reusable patterns**: Strategy 4 format and AskUserQuestion presentation (reuse as-is)
- **New code justification**: Strategies 5 and 6 are genuinely new grouping approaches with no existing equivalent in the command

## Implementation Phases

### Phase 1: Extend Issue Scanning (Step 1.5.1)

#### Overview
Add extraction of Summary text and file paths from issue content during the scan step.

#### Changes Required

**File**: `commands/create_sprint.md`
**Lines**: 135-142 (Step 1.5.1 extraction list)

Add two new extraction fields after the existing five:
- **Summary**: From `## Summary` section (first paragraph)
- **File Paths**: Backtick-enclosed file paths found in issue content (e.g., from Integration Map sections)

#### Success Criteria

**Automated Verification**:
- [ ] File is valid markdown (no syntax errors)

**Manual Verification**:
- [ ] New extraction fields are clearly described and follow existing format

---

### Phase 2: Expand Strategy 4 (Theme Cluster)

#### Overview
Broaden the keyword themes, match against title + summary, and return multiple qualifying theme clusters.

#### Changes Required

**File**: `commands/create_sprint.md`
**Lines**: 166-173 (Strategy 4)

Replace current Strategy 4 with expanded version:
- Add more keyword theme groups: sprint/workflow, config/settings, hook/lifecycle, CLI/command, error/logging
- Match keywords against both **title** AND **summary** (not just title)
- Return **all qualifying** theme clusters (not just the largest)
- Keep minimum threshold of 2 issues per cluster

#### Success Criteria

**Automated Verification**:
- [ ] File is valid markdown

**Manual Verification**:
- [ ] New keyword themes cover common issue topics in the current backlog
- [ ] Matching against summary is clearly described

---

### Phase 3: Add Strategy 5 (Component-Based Grouping)

#### Overview
Add a new grouping strategy that clusters issues by which codebase component/directory they reference.

#### Changes Required

**File**: `commands/create_sprint.md`
**After**: Strategy 4 (new section)

Add Strategy 5:
- Extract top-level directory from file paths found in issue content
- Group issues by shared directory prefix (e.g., `commands/`, `scripts/`, `hooks/`, `skills/`)
- Name: derived from directory (e.g., `commands-updates`, `scripts-improvements`)
- Minimum threshold: 2 issues referencing the same directory
- Only suggest the top 2 component groupings (by issue count)

#### Success Criteria

**Automated Verification**:
- [ ] File is valid markdown

**Manual Verification**:
- [ ] Component grouping strategy is clearly described
- [ ] Directory prefix extraction logic is unambiguous

---

### Phase 4: Add Strategy 6 (Goal-Aligned Grouping)

#### Overview
Add a new grouping strategy that clusters issues by product goal alignment when goals are available.

#### Changes Required

**File**: `commands/create_sprint.md`
**After**: Strategy 5 (new section)

Add Strategy 6:
- **Skip entirely** if `product.enabled` is not `true` in config or goals file doesn't exist
- Read `product.goals_file` (default `.claude/ll-goals.md`)
- Extract priority names from the goals file YAML frontmatter
- For each issue, check if its `goal_alignment` frontmatter field or title/summary mentions a goal
- Group issues by matching goal
- Name: derived from goal name (kebab-case, e.g., `goal-developer-experience`)
- Minimum threshold: 2 issues per goal

#### Success Criteria

**Automated Verification**:
- [ ] File is valid markdown

**Manual Verification**:
- [ ] Skip condition is clearly documented
- [ ] Graceful fallback when goals are unavailable

---

### Phase 5: Update Scoring, Selection, and Presentation

#### Overview
Update the scoring/selection rules and the presentation format to accommodate theme-based groupings.

#### Changes Required

**File**: `commands/create_sprint.md`
**Lines**: 175-178 (Scoring & Selection) and 180-213 (Step 1.5.3 presentation)

Scoring changes:
- Increase max from "3-4 groupings" to "up to 4 groupings" (AskUserQuestion limit is 4 options including "Select manually", but "Other" is auto-added so we can present up to 4 groupings + "Select manually" = 4 options with Other auto-added)
- When more than 3 groupings qualify, prefer: 1 mechanical (priority/type/parallel) + 2 theme-based + "Select manually"
- Keep distinctiveness prioritization

Presentation changes:
- Update the example output to show a mix of mechanical and theme-based groupings
- Keep same AskUserQuestion YAML format (label + description)

#### Success Criteria

**Automated Verification**:
- [ ] File is valid markdown
- [ ] Lint: `ruff check scripts/` (no Python changes but verify no regressions)

**Manual Verification**:
- [ ] Example output reflects the new grouping variety
- [ ] Selection logic handles edge cases (no themes found, all themes, etc.)

## Testing Strategy

### Manual Testing
- Run `/ll:create_sprint` with no arguments on the current backlog
- Verify theme groupings appear based on actual issue content
- Verify component groupings appear if issues reference files
- Verify goal groupings are skipped (no goals file exists)

## References

- Original issue: `.issues/enhancements/P3-ENH-407-create-sprint-theme-based-grouping-options.md`
- Command file: `commands/create_sprint.md`
- FEAT-174 plan: `thoughts/shared/plans/2026-01-28-FEAT-174-management.md`
- Existing grouping framework: `commands/create_sprint.md:144-178`
