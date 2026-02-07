# BUG-273: README has inaccurate counts, wrong skills table, and wrong plugin.json path - Implementation Plan

## Issue Reference
- **File**: `.issues/bugs/P2-BUG-273-readme-inaccurate-counts-skills-table-and-plugin-path.md`
- **Type**: bug
- **Priority**: P2
- **Action**: fix

## Current State Analysis

README.md contains 5 inaccuracies confirmed by filesystem research:

### Key Discoveries
- `README.md:25` — says "34 slash commands", actual count is 35
- `README.md:27` — says "dependency mapping" and "workflow reference", actual skill names are `map-dependencies` and `issue-workflow`
- `README.md:370-377` — skills table lists 4 agents + 1 command; only `product-analyzer` is an actual skill
- `README.md:589` — shows `plugin.json` at root; actual location is `.claude-plugin/plugin.json`
- `README.md:592` — says "34 commands" in directory tree comment; actual count is 35

## Desired End State

README.md accurately reflects the actual codebase state for counts, skill definitions, and file locations.

### How to Verify
- Command count matches `ls commands/*.md | wc -l` = 35
- Skills table lists exactly the 6 skill directories in `skills/`
- plugin.json path matches `.claude-plugin/plugin.json`

## What We're NOT Doing

- Not updating any other documentation files
- Not changing agents table (already correct)
- Not restructuring the README

## Implementation Phases

### Phase 1: Fix all README.md inaccuracies

#### Changes Required

**File**: `README.md`

1. **Line 25**: Change "34 slash commands" → "35 slash commands"

2. **Line 27**: Update skill descriptions to match actual skill names:
   - "workflow reference" → "issue workflow reference"
   - "dependency mapping" → "dependency mapping" (this one is fine, maps to `map-dependencies`)

3. **Lines 370-377**: Replace entire skills table with actual skills:
   - `analyze-history` — Analyze issue history for project health, trends, and progress
   - `issue-size-review` — Evaluate issue size/complexity and propose decomposition
   - `issue-workflow` — Quick reference for issue management workflow
   - `map-dependencies` — Analyze cross-issue dependencies based on file overlap
   - `product-analyzer` — Analyze codebase against product goals for feature gaps and business value
   - `workflow-automation-proposer` — Synthesize workflow patterns into automation proposals

4. **Line 589**: Fix plugin.json path in directory tree:
   ```
   ├── .claude-plugin/
   │   └── plugin.json       # Plugin manifest
   ```

5. **Line 592**: Change "34 commands" → "35 commands"

#### Success Criteria

**Automated Verification**:
- [ ] `ls commands/*.md | wc -l` outputs 35
- [ ] `ls skills/*/SKILL.md | wc -l` outputs 6
- [ ] `ls .claude-plugin/plugin.json` exists
- [ ] grep confirms updated counts in README

## References

- Original issue: `.issues/bugs/P2-BUG-273-readme-inaccurate-counts-skills-table-and-plugin-path.md`
