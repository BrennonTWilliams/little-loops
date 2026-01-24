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

This command uses project configuration from `.claude/ll-config.json`:

**Issues settings** (under `issues`):
- `base_dir`: Issues directory - `{{config.issues.base_dir}}`

**Sprints settings** (under `sprints`):
- `sprints_dir`: Directory for sprint definitions - `{{config.sprints.sprints_dir}}`
- `default_mode`: Default execution mode - `{{config.sprints.default_mode}}`
- `default_timeout`: Default timeout per issue in seconds - `{{config.sprints.default_timeout}}`
- `default_max_workers`: Default worker count for parallel mode - `{{config.sprints.default_max_workers}}`

## Process

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

### 2. Gather Issue List

If `issues` argument was provided, use it directly.

If `issues` was NOT provided, help the user select issues interactively:

#### Option A: Scan and Select

Use AskUserQuestion to present selection options:

- **"Select from active issues"** - Show all active issues grouped by category/priority
- **"Enter manually"** - User types issue IDs
- **"Select by priority"** - "All P0 issues", "All P1-P2 issues", etc.

#### Option B: Interactive Category Selection

If selecting from active issues:
1. Use the Glob tool to find active issues:
   - Pattern: `.issues/**/*.md`
   - Then filter results to exclude paths containing `/completed/`
2. Parse and group by category/priority
3. Present organized list for selection

### 3. Validate Issues Exist

For each issue ID in the list, use the Glob tool to verify it exists:
- Pattern: `.issues/**/*-[ISSUE-ID]-*.md` (substitute the actual issue ID)
- Example: For issue `BUG-001`, use pattern `.issues/**/*-BUG-001-*.md`

If a pattern returns no results, the issue is missing. Report any missing issues and ask if the user wants to:
- Continue without missing issues
- Remove missing issues from list
- Cancel and fix the list

### 4. Create Sprint Directory (if needed)

Ensure the sprints directory exists:

```bash
mkdir -p .sprints
```

### 5. Create Sprint YAML File

Create the sprint definition at `.sprints/${SPRINT_NAME}.yaml`:

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
  mode: auto  # auto (sequential) or parallel
  timeout: 3600
  max_workers: 4  # for parallel mode
```

**Fields:**
- `name`: Sprint identifier
- `description`: Human-readable purpose (optional, defaults to "")
- `created`: ISO 8601 timestamp
- `issues`: List of issue IDs (validated to exist)
- `options`: Execution defaults (optional)
  - `mode`: "auto" for sequential, "parallel" for concurrent
  - `timeout`: Per-issue timeout in seconds
  - `max_workers`: Worker count for parallel mode

### 6. Output Confirmation

Display the created sprint:

```markdown
## Sprint Created Successfully

**File**: `.sprints/${SPRINT_NAME}.yaml`
**Name**: ${SPRINT_NAME}
**Description**: ${SPRINT_DESC}
**Issues**: ${issue_count}

### Issue List
${formatted_issue_list_with_descriptions}

### Next Steps
# Execute the sprint sequentially:
ll-sprint run ${SPRINT_NAME}

# Execute the sprint in parallel:
ll-sprint run ${SPRINT_NAME} --parallel

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
# Sequential execution (uses ll-auto components)
ll-sprint run sprint-1

# Parallel execution (uses ll-parallel components)
ll-sprint run sprint-1 --parallel

# With custom options
ll-sprint run sprint-1 --parallel --workers 8

# Dry run to preview
ll-sprint run sprint-1 --dry-run
```

## Integration

The `ll-sprint` tool reuses existing components:
- **Sequential mode**: Uses `AutoManager` from `issue_manager.py`
- **Parallel mode**: Uses `ParallelOrchestrator` from `parallel/orchestrator.py`

Sprint definitions are stored in `.sprints/` directory (recommended to gitignore for project-specific sprints, or commit for reusable templates).
