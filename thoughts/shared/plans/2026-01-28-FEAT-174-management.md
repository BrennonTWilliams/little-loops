# FEAT-174: Automatic Sprint Grouping in create_sprint Command - Implementation Plan

## Issue Reference
- **File**: `.issues/features/P3-FEAT-174-automatic-sprint-grouping-in-create-sprint.md`
- **Type**: feature
- **Priority**: P3
- **Action**: implement

## Current State Analysis

The `/ll:create-sprint` command (`commands/create_sprint.md:1-287`) currently offers three interactive options when the `--issues` argument is omitted:

1. "Select from active issues" - Shows all active issues grouped by category/priority
2. "Enter manually" - User types issue IDs
3. "Select by priority" - "All P0 issues", "All P1-P2 issues", etc.

These options require the user to already know what they want. The command does NOT analyze active issues or suggest natural groupings.

### Key Discoveries
- Issue parsing: `IssueParser.parse_file()` in `scripts/little_loops/issue_parser.py:158-196` extracts priority, type, title, and dependencies
- Issue finding: `find_issues()` in `scripts/little_loops/issue_parser.py:435-487` scans and filters active issues
- Dependency graph: `DependencyGraph.get_execution_waves()` in `scripts/little_loops/dependency_graph.py:119-166` groups parallelizable issues
- AskUserQuestion patterns: Multiple options with descriptions, multi-select support (`commands/capture_issue.md:107-119`)
- Word extraction/matching: `_extract_words()` in `scripts/little_loops/issue_discovery.py:162-202` for keyword analysis

## Desired End State

When `/ll:create-sprint` is run without the `--issues` argument:

1. Analyze all active issues (from bugs/, features/, enhancements/)
2. Identify patterns and generate 2-4 suggested sprint groupings
3. Present suggestions with auto-generated names and issue lists
4. Allow user to select a grouping or proceed with manual selection

### How to Verify
- Run `/ll:create-sprint test-sprint` without `--issues` argument
- Observe suggested sprint groupings before interactive selection
- Verify groupings are sensible (by priority, type, dependencies, or theme)

## What We're NOT Doing

- Not adding new Python modules - keeping all logic in the command markdown file
- Not implementing complex NLP theme detection - using simple keyword matching
- Not changing existing `--issues` argument behavior - suggestions only appear when omitted
- Not requiring dependency graph for all groupings - it's one option among several
- Deferring ML-based clustering to future enhancement

## Problem Analysis

The current command assumes users know exactly what they want in a sprint. However, with many active issues, users benefit from intelligent suggestions that identify natural groupings. The codebase already has:

- Issue parsing to extract metadata (priority, type, dependencies)
- Dependency graph for parallelization analysis
- Pattern matching utilities for keyword extraction

These can be combined to suggest sprint groupings without user effort.

## Solution Approach

Add a new step (Step 1.5) in the command workflow that:
1. Scans all active issues using Glob
2. Parses each issue to extract metadata
3. Generates grouping suggestions using multiple strategies:
   - **Priority clusters**: P0-P1 critical, P2 important, P3-P5 backlog
   - **Type clusters**: All bugs, all features, all enhancements
   - **Dependency waves**: Issues with no blockers (parallelizable)
   - **Theme patterns**: Keyword matching on titles (test, performance, security, etc.)
4. Presents top 3-4 distinct groupings via AskUserQuestion
5. Allows user to select a grouping or skip to manual selection

## Implementation Phases

### Phase 1: Add Auto-Grouping Analysis Section

#### Overview
Add a new section after Step 1 (validation) and before Step 2 (gather issue list) that analyzes active issues and generates grouping suggestions.

#### Changes Required

**File**: `commands/create_sprint.md`
**Changes**: Insert new section "### 1.5 Suggest Sprint Groupings (Optional)" between sections 1 and 2

```markdown
### 1.5 Suggest Sprint Groupings (Optional)

**SKIP this section if:**
- The `issues` argument was provided (user already specified issues)

When no issues are specified, analyze active issues and suggest natural sprint groupings:

#### Step 1.5.1: Scan Active Issues

Use Glob to find all active issues:
- Pattern: `{issues.base_dir}/bugs/*.md`
- Pattern: `{issues.base_dir}/features/*.md`
- Pattern: `{issues.base_dir}/enhancements/*.md`

For each issue file found, extract:
- **Priority**: From filename prefix (P0, P1, P2, P3, P4, P5)
- **Type**: From directory (bugs, features, enhancements)
- **ID**: From filename (e.g., BUG-001, FEAT-042)
- **Title**: From first `# ` heading
- **Blocked By**: From `## Blocked By` section (if exists)

Store parsed issues in a list for analysis.

#### Step 1.5.2: Generate Grouping Suggestions

Analyze the parsed issues and generate 2-4 distinct groupings:

**Grouping Strategy 1: Priority Cluster (Critical)**
- Name: `critical-fixes` or `urgent-[date]`
- Criteria: All P0 and P1 issues
- Only suggest if 2+ issues match

**Grouping Strategy 2: Type Cluster**
- Name: `bug-fixes`, `feature-work`, or `enhancements`
- Criteria: All issues of the most populous type
- Only suggest if 3+ issues match

**Grouping Strategy 3: Parallelizable Issues**
- Name: `parallel-ready` or `unblocked-issues`
- Criteria: Issues with no `Blocked By` entries (or all blockers are completed)
- Only suggest if 3+ issues match

**Grouping Strategy 4: Theme Cluster**
- Name: `test-coverage`, `performance`, `security`, `documentation`, etc.
- Criteria: Issues whose titles contain theme keywords
- Theme keywords to match:
  - "test" → `test-coverage`
  - "performance", "speed", "slow", "fast", "optimize" → `performance`
  - "security", "auth", "permission", "access" → `security`
  - "doc", "readme", "comment" → `documentation`
- Only suggest if 2+ issues match a theme

**Scoring & Selection:**
- Score each grouping by: `size * distinctiveness`
- Distinctiveness = issues in this grouping not in higher-scored groupings
- Select top 3-4 groupings with size >= 2

#### Step 1.5.3: Present Suggestions

If suggestions were generated, present them using AskUserQuestion:

```yaml
questions:
  - question: "Based on ${total_active_issues} active issues, here are suggested sprint groupings. Select one or choose to select manually:"
    header: "Sprint"
    multiSelect: false
    options:
      - label: "${grouping_1_name} (${grouping_1_count} issues)"
        description: "${grouping_1_description}: ${first_3_issue_ids}..."
      - label: "${grouping_2_name} (${grouping_2_count} issues)"
        description: "${grouping_2_description}: ${first_3_issue_ids}..."
      - label: "${grouping_3_name} (${grouping_3_count} issues)"
        description: "${grouping_3_description}: ${first_3_issue_ids}..."
      - label: "Select manually"
        description: "Skip suggestions and choose issues yourself"
```

**Example output:**
```
Based on 23 active issues, here are suggested sprint groupings:

1. critical-fixes (4 issues)
   All P0-P1 priority issues: BUG-001, BUG-015, FEAT-040...

2. bug-fixes (8 issues)
   All active bugs: BUG-001, BUG-015, BUG-023...

3. parallel-ready (12 issues)
   Issues with no blockers: ENH-004, ENH-146, ENH-147...

4. Select manually
   Skip suggestions and choose issues yourself
```

**Based on user response:**
- **Grouping selected**: Set `SPRINT_ISSUES` to the issue IDs in that grouping, update `SPRINT_NAME` to suggested name if still empty, skip to Step 3 (validation)
- **"Select manually"**: Continue to Step 2 (original interactive flow)
```

#### Success Criteria

**Automated Verification**:
- [ ] Lint passes: `ruff check scripts/`
- [ ] Types pass: `python -m mypy scripts/little_loops/`
- [ ] Command file is valid markdown (no syntax errors)

**Manual Verification**:
- [ ] Run `/ll:create-sprint test-sprint` with no `--issues` - see grouping suggestions
- [ ] Selecting a grouping auto-fills issues and suggests sprint name
- [ ] Selecting "manual" proceeds to original interactive flow

---

### Phase 2: Update Original Section 2 to Support Pre-filled Issues

#### Overview
Modify the original "Step 2: Gather Issue List" section to handle cases where issues were pre-filled by the auto-grouping step.

#### Changes Required

**File**: `commands/create_sprint.md`
**Changes**: Update Step 2 to check for pre-filled issues

```markdown
### 2. Gather Issue List

**If `SPRINT_ISSUES` is already populated** (from `--issues` argument OR from grouping selection in Step 1.5):
- Skip this step and proceed to Step 3

If `SPRINT_ISSUES` is NOT provided and no grouping was selected, help the user select issues interactively:

[rest of existing Step 2 content unchanged]
```

#### Success Criteria

**Automated Verification**:
- [ ] Lint passes: `ruff check scripts/`
- [ ] Command file is valid markdown

**Manual Verification**:
- [ ] Selecting a suggested grouping skips the manual selection step
- [ ] `--issues` argument still works as before
- [ ] Manual selection flow still works when choosing "Select manually"

---

### Phase 3: Add Sprint Name Auto-Suggestion

#### Overview
When a user selects a suggested grouping, auto-suggest the grouping's name as the sprint name.

#### Changes Required

**File**: `commands/create_sprint.md`
**Changes**: In Step 1.5.3 response handling, update sprint name

After the AskUserQuestion in Step 1.5.3, add handling:

```markdown
**Based on user response:**
- **Grouping selected**:
  - Set `SPRINT_ISSUES` to the issue IDs in that grouping
  - If `SPRINT_NAME` is empty or was a default value, suggest using the grouping name:
    - Use AskUserQuestion: "Use suggested sprint name '${grouping_name}' or enter your own?"
    - Options: "Use '${grouping_name}'" | "Enter different name"
  - Skip to Step 3 (validation)
- **"Select manually"**: Continue to Step 2 (original interactive flow)
```

#### Success Criteria

**Automated Verification**:
- [ ] Lint passes: `ruff check scripts/`

**Manual Verification**:
- [ ] Selecting a grouping prompts to use the suggested name
- [ ] User can accept suggested name or provide their own
- [ ] If user already provided a valid name, it is preserved

---

## Testing Strategy

### Manual Test Cases

1. **No active issues**: Verify graceful handling when no issues exist
2. **Few active issues (<3)**: Verify suggestions still work or gracefully degrade
3. **Many active issues (20+)**: Verify suggestions are diverse and useful
4. **Mixed priorities**: Verify priority grouping captures P0-P1 correctly
5. **Blocked issues**: Verify parallel-ready grouping excludes blocked issues
6. **Theme matching**: Create issues with "test" in title, verify theme detection

### Test Commands

```bash
# Test with existing issues
/ll:create-sprint test-auto

# Test with explicit issues (should skip suggestions)
/ll:create-sprint test-explicit --issues "BUG-001,FEAT-002"

# Test cancellation
/ll:create-sprint test-cancel  # then select "Select manually" then cancel
```

## References

- Original issue: `.issues/features/P3-FEAT-174-automatic-sprint-grouping-in-create-sprint.md`
- Sprint command: `commands/create_sprint.md`
- Issue parser: `scripts/little_loops/issue_parser.py:158-196` (parse_file method)
- Dependency graph: `scripts/little_loops/dependency_graph.py:119-166` (get_execution_waves)
- AskUserQuestion pattern: `commands/capture_issue.md:107-119`
