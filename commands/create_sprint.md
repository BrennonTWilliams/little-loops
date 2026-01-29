---
description: Create a sprint definition with a curated list of issues
allowed-tools:
  - Bash(mkdir:*)
arguments:
  - name: name
    description: Sprint name (e.g., "sprint-1", "q1-bug-fixes")
    required: true
  - name: description
    description: Optional description of the sprint's purpose
    required: false
  - name: issues
    description: Comma-separated list of issue IDs to include (e.g., "BUG-001,FEAT-010")
    required: false
---

# Create Sprint

You are tasked with creating sprint definitions for the little-loops project. Sprints are curated lists of issues that can be executed together as a unit using the `ll-sprint` CLI tool.

## Configuration

Read settings from `.claude/ll-config.json`:

**Issues settings** (under `issues`):
- `base_dir`: Issues directory (default: `.issues`)

**Sprints settings** (under `sprints`):
- `sprints_dir`: Directory for sprint definitions (default: `.sprints`)
- `default_timeout`: Default timeout per issue in seconds (default: `3600`)
- `default_max_workers`: Default worker count for parallel execution within waves (default: `4`)

## Process

### 0. Load Configuration

Read the project configuration from `.claude/ll-config.json` to get sprint settings.

Use the Read tool to read `.claude/ll-config.json`, then extract:
- `issues.base_dir` - Issues directory (use default `.issues` if not set)
- `sprints.sprints_dir` - Directory for sprint files (use default `.sprints` if not set)
- `sprints.default_timeout` - Default timeout in seconds (use default `3600` if not set)
- `sprints.default_max_workers` - Default worker count (use default `4` if not set)

Store these values for use in subsequent steps.

### 1. Validate and Parse Inputs

Parse the provided arguments:

```bash
SPRINT_NAME="${name}"
SPRINT_DESC="${description:-}"
SPRINT_ISSUES="${issues:-}"
```

**Validate sprint name:**
- Must be non-empty
- Should use lowercase letters, numbers, and hyphens only
- Suggest format: `sprint-N`, `q1-features`, `bug-fixes-week-1`

**Validation rules:**
1. Must be non-empty
2. Must match pattern: `^[a-z0-9]([a-z0-9-]*[a-z0-9])?$` (or single char `^[a-z0-9]$`)
3. No consecutive hyphens (`--`)
4. No leading or trailing hyphens

**If name is invalid**, auto-generate a suggested correction:
- Convert to lowercase
- Replace spaces and underscores with hyphens
- Remove invalid characters (keep only `a-z`, `0-9`, `-`)
- Collapse consecutive hyphens to single hyphen
- Trim leading/trailing hyphens

**Example corrections:**

| Input | Issue | Suggestion |
|-------|-------|------------|
| `Sprint 1` | Uppercase and space | `sprint-1` |
| `--test--` | Leading/trailing hyphens | `test` |
| `Q1_bugs` | Uppercase and underscore | `q1-bugs` |
| `my..sprint` | Invalid characters | `my-sprint` |
| `` (empty) | Empty name | Prompt user to provide name |

**If name is empty**, use AskUserQuestion to prompt for a name:

```yaml
questions:
  - question: "Sprint name is required. What should the sprint be called?"
    header: "Name"
    multiSelect: false
    options:
      - label: "sprint-1"
        description: "Default sequential name"
      - label: "q1-features"
        description: "Quarterly feature sprint"
      - label: "bug-fixes"
        description: "Bug fix sprint"
```

Then re-validate the provided name.

**If name is invalid (non-empty but fails validation)**, use AskUserQuestion:

```yaml
questions:
  - question: "Sprint name '${SPRINT_NAME}' is invalid: ${REASON}. How would you like to proceed?"
    header: "Fix name"
    multiSelect: false
    options:
      - label: "Use '${SUGGESTED_NAME}' (Recommended)"
        description: "Auto-corrected name following conventions"
      - label: "Enter different name"
        description: "Provide your own valid name"
      - label: "Use original anyway"
        description: "May cause issues with ll-sprint CLI"
```

**Based on user response:**
- **"Use '${SUGGESTED_NAME}'"**: Update `SPRINT_NAME` to the suggested value and continue
- **"Enter different name"**: Prompt for new name and re-validate
- **"Use original anyway"**: Continue with original name (warn about potential issues)

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
- **Title**: From first `# ` heading in file content
- **Blocked By**: From `## Blocked By` section (if exists)

Store parsed issues in a list for analysis.

#### Step 1.5.2: Generate Grouping Suggestions

Analyze the parsed issues and generate 2-4 distinct groupings. Skip any grouping with fewer than 2 issues.

**Grouping Strategy 1: Priority Cluster (Critical)**
- Name: `critical-fixes`
- Description: "All P0-P1 priority issues"
- Criteria: All issues with priority P0 or P1
- Only suggest if 2+ issues match

**Grouping Strategy 2: Type Cluster**
- Name: `bug-fixes`, `feature-work`, or `enhancements`
- Description: "All active [bugs/features/enhancements]"
- Criteria: All issues of the most populous type
- Only suggest if 3+ issues match

**Grouping Strategy 3: Parallelizable Issues**
- Name: `parallel-ready`
- Description: "Issues with no blockers (can run in parallel)"
- Criteria: Issues with no `Blocked By` entries
- Only suggest if 3+ issues match

**Grouping Strategy 4: Theme Cluster**
- Detect themes by matching keywords in issue titles (case-insensitive):
  - Keywords containing "test" → Name: `test-coverage`, Description: "Test coverage improvements"
  - Keywords: "performance", "speed", "slow", "fast", "optimize" → Name: `performance`, Description: "Performance-related issues"
  - Keywords: "security", "auth", "permission", "access" → Name: `security`, Description: "Security-related issues"
  - Keywords: "doc", "readme", "comment" → Name: `documentation`, Description: "Documentation improvements"
- Only suggest if 2+ issues match a theme
- Only include the largest theme cluster

**Scoring & Selection:**
- Prioritize groupings by distinctiveness (issues not in other groupings)
- Select top 3-4 groupings with size >= 2
- Always include "Select manually" as the last option

#### Step 1.5.3: Present Suggestions

If at least one suggestion was generated, present them using AskUserQuestion:

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
- **Grouping selected**:
  - Set `SPRINT_ISSUES` to the comma-separated issue IDs in that grouping
  - If `SPRINT_NAME` is empty or was a default placeholder, prompt to use the grouping name:
    ```yaml
    questions:
      - question: "Use suggested sprint name '${grouping_name}' or enter your own?"
        header: "Name"
        multiSelect: false
        options:
          - label: "Use '${grouping_name}' (Recommended)"
            description: "Auto-generated name based on grouping type"
          - label: "Enter different name"
            description: "Provide your own sprint name"
    ```
  - Skip to Step 3 (Validate Issues Exist)
- **"Select manually"**: Continue to Step 2 (original interactive flow)

**If no suggestions could be generated** (fewer than 2 issues total or no groupings meet minimum size):
- Display: "Not enough active issues for automatic groupings. Proceeding to manual selection."
- Continue to Step 2

---

### 2. Gather Issue List

**If `SPRINT_ISSUES` is already populated** (from `--issues` argument OR from grouping selection in Step 1.5):
- Skip this step and proceed to Step 3

If `SPRINT_ISSUES` is NOT populated and no grouping was selected, help the user select issues interactively:

#### Option A: Scan and Select

Use AskUserQuestion to present selection options:

- **"Select from active issues"** - Show all active issues grouped by category/priority
- **"Enter manually"** - User types issue IDs
- **"Select by priority"** - "All P0 issues", "All P1-P2 issues", etc.

#### Option B: Interactive Category Selection

If selecting from active issues:
1. Use the Glob tool to find active issues:
   - Pattern: `{issues.base_dir}/**/*.md` (using the configured issues directory)
   - Then filter results to exclude paths containing `/completed/`
2. Parse and group by category/priority
3. Present organized list for selection

### 3. Validate Issues Exist

For each issue ID in the list, use the Glob tool to verify it exists:
- Pattern: `{issues.base_dir}/**/*-[ISSUE-ID]-*.md` (substitute the actual issue ID, using the configured issues directory)
- Example: For issue `BUG-001`, use pattern `{issues.base_dir}/**/*-BUG-001-*.md`

If a pattern returns no results, the issue is missing. Report any missing issues and ask if the user wants to:
- Continue without missing issues
- Remove missing issues from list
- Cancel and fix the list

### 4. Create Sprint Directory (if needed)

Ensure the configured sprints directory exists:

```bash
mkdir -p {sprints.sprints_dir}  # using the configured sprints directory
```

### 4b. Check for Existing Sprint

Before writing, check if a sprint with this name already exists:

Use the Glob tool to check: `{sprints.sprints_dir}/${SPRINT_NAME}.yaml` (using the configured sprints directory)

If the file exists, use AskUserQuestion:

```yaml
questions:
  - question: "A sprint named '${SPRINT_NAME}' already exists. What would you like to do?"
    header: "Overwrite"
    multiSelect: false
    options:
      - label: "Overwrite"
        description: "Replace the existing sprint configuration"
      - label: "Choose different name"
        description: "Go back and pick a new name"
      - label: "Cancel"
        description: "Abort sprint creation"
```

**Based on user response:**
- **"Overwrite"**: Continue to Step 5 (write file)
- **"Choose different name"**: Return to Step 1 to input a new name
- **"Cancel"**: Display "Sprint creation cancelled." and stop

### 5. Create Sprint YAML File

Create the sprint definition at `{sprints.sprints_dir}/${SPRINT_NAME}.yaml` (using the configured sprints directory):

```yaml
name: sprint-1
description: "Q1 Performance and Security Improvements"
created: "2026-01-14T00:00:00Z"
issues:
  - BUG-001
  - BUG-002
  - FEAT-010
  - FEAT-015
options:
  timeout: 3600  # use the configured default_timeout
  max_workers: 4  # use the configured default_max_workers
```

**Fields:**
- `name`: Sprint identifier
- `description`: Human-readable purpose (optional, defaults to "")
- `created`: ISO 8601 timestamp
- `issues`: List of issue IDs (validated to exist)
- `options`: Execution defaults (optional)
  - `timeout`: Per-issue timeout in seconds
  - `max_workers`: Worker count for parallel execution within waves

### 6. Output Confirmation

Display the created sprint:

```markdown
## Sprint Created Successfully

**File**: `{sprints.sprints_dir}/${SPRINT_NAME}.yaml`
**Name**: ${SPRINT_NAME}
**Description**: ${SPRINT_DESC}
**Issues**: ${issue_count}

### Issue List
${formatted_issue_list_with_descriptions}

### Next Steps
# Execute the sprint (dependency-aware with parallel waves):
ll-sprint run ${SPRINT_NAME}

# Show sprint details:
ll-sprint show ${SPRINT_NAME}

# List all sprints:
ll-sprint list
```

## Examples

```bash
# Create sprint with explicit issue list
/ll:create_sprint sprint-1 --issues "BUG-001,BUG-002,FEAT-010" --description "Q1 fixes"

# Create sprint interactively (select issues)
/ll:create_sprint q1-features --description "Q1 feature work"
```

## Sprint Execution (Reference)

After creating a sprint, users can execute it via:

```bash
# Execute with dependency-aware wave scheduling
ll-sprint run sprint-1

# With custom max workers
ll-sprint run sprint-1 --max-workers 8

# Dry run to preview execution plan
ll-sprint run sprint-1 --dry-run
```

## Integration

Sprint execution uses `ParallelOrchestrator` from `parallel/orchestrator.py` with dependency-aware wave scheduling. Issues are grouped into waves based on their `blocked_by` dependencies, and each wave is executed in parallel.

Sprint definitions are stored in the configured sprints directory (default: `.sprints/`). Recommended to gitignore for project-specific sprints, or commit for reusable templates.
