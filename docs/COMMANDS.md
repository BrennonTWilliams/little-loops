# Command Reference

Complete reference for all `/ll:` commands. Run `/ll:help` in Claude Code for an interactive version.

## Setup & Configuration

### `/ll:init`
Initialize little-loops configuration for a project.

**Flags:** `--interactive`, `--yes`, `--force`

### `/ll:help`
List all available little-loops commands with descriptions.

### `/ll:configure`
Interactively configure specific areas in ll-config.json.

**Arguments:**
- `area` (optional): `project`, `issues`, `parallel`, `automation`, `documents`, `continuation`, `context`, `prompt`, `scan`, `workflow`

**Flags:** `--list`, `--show`, `--reset`

---

## Prompt Optimization

### `/ll:toggle_autoprompt`
Toggle automatic prompt optimization settings.

**Settings:** `enabled`, `mode`, `confirm`, `status` (default: status)

---

## Code Quality

### `/ll:check_code`
Run code quality checks (lint, format, types).

**Modes:** `lint`, `format`, `types`, `all`, `fix`

### `/ll:run_tests`
Run test suites with common patterns.

**Arguments:**
- `scope`: `unit`, `integration`, `all`, `affected`
- `pattern`: optional pytest -k filter

### `/ll:find_dead_code`
Analyze codebase for deprecated, unused, or dead code.

---

## Issue Management

### `/ll:capture_issue`
Capture issues from conversation or natural language description.

**Arguments:** `input` (optional) - natural language description

### `/ll:refine_issue`
Refine issue files through interactive Q&A to improve quality before validation or implementation. Interactive by default, with optional `--auto` mode for non-interactive refinement.

**Arguments:**
- `issue_id` (optional): Issue ID to refine (e.g., BUG-071, FEAT-225)
- `flags` (optional):
  - `--auto` - Non-interactive auto-refinement mode
  - `--all` - Process all active issues
  - `--dry-run` - Preview changes without applying
  - `--template-align-only` - Only rename deprecated v1.0 sections to v2.0

### `/ll:scan_codebase`
Scan codebase to identify bugs, enhancements, and features (technical analysis).

### `/ll:scan_product`
Scan codebase for product-focused issues based on goals document (requires `product.enabled: true`).

**Prerequisites:**
- Product analysis enabled in config
- Goals file exists (`.claude/ll-goals.md` by default)

### `/ll:prioritize_issues`
Analyze issues and assign priority levels (P0-P5).

### `/ll:ready_issue`
Validate issue file for accuracy and auto-correct problems.

**Arguments:** `issue_id` (optional)

### `/ll:verify_issues`
Verify all issue files against current codebase state.

### `/ll:align_issues`
Validate active issues against key documents for relevance and alignment.

**Arguments:**
- `category`: Document category (`architecture`, `product`, or `--all`)
- `flags` (optional): `--verbose` (detailed analysis), `--dry-run` (report only, no auto-fixing)

**Prerequisites:** Configure document tracking via `/ll:init --interactive`

### `/ll:normalize_issues`
Find and fix issue filenames lacking valid IDs (BUG-001, etc.).

### `/ll:sync_issues`
Sync local issues with GitHub Issues (push/pull/status).

**Arguments:** `mode` (optional) - `push`, `pull`, or `status`

### `/ll:manage_issue`
Autonomously manage issues - plan, implement, verify, complete.

**Arguments:**
- `type`: `bug`, `feature`, `enhancement`
- `action`: `fix`, `implement`, `improve`, `verify`
- `issue_id` (optional)

### `/ll:iterate_plan`
Iterate on existing implementation plans with updates.

**Arguments:** `plan_path` (optional)

### `/ll:tradeoff_review_issues`
Evaluate active issues for utility vs complexity trade-offs and recommend which to implement, update, or close.

**Trigger keywords:** "tradeoff review", "review issues", "prune backlog", "sense check issues"

---

## Sprint Management

### `/ll:create_sprint`
Create a sprint definition with a curated list of issues.

**Arguments:**
- `name` (required): Sprint name (e.g., "sprint-1", "q1-bug-fixes")
- `description` (optional): Description of the sprint's purpose
- `issues` (optional): Comma-separated list of issue IDs (e.g., "BUG-001,FEAT-010")

**Modes:**
- **Explicit**: Pass `--issues "BUG-001,FEAT-010"` to create a sprint with specific issues
- **Auto-Grouping**: When `issues` is omitted, suggests natural sprint groupings:
  - Priority cluster (P0-P1 critical), type cluster (bugs/features/enhancements)
  - Parallelizable (no blockers), theme cluster (test, performance, security)
- **Manual Selection**: Choose "Select manually" to pick issues interactively

**Output:** Creates `.sprints/<name>.yaml` with issue list and execution options.

---

## Auditing & Analysis

### `/ll:audit_architecture`
Analyze codebase architecture for patterns and improvements.

**Focus:** `large-files`, `integration`, `patterns`, `organization`, `all`

### `/ll:audit_docs`
Audit documentation for accuracy and completeness. Auto-fixable findings (wrong counts, outdated paths, broken links) can be fixed directly during the audit.

**Scope:** `full`, `readme`, `file:<path>`

**Flags:** `--fix` (auto-apply fixable corrections without prompting)

### `/ll:audit_claude_config`
Comprehensive audit of Claude Code plugin configuration with parallel sub-agents.

**Scope:** `all`, `global`, `project`, `hooks`, `mcp`, `agents`, `commands`, `skills`

**Flags:** `--non-interactive`, `--fix`

### `/ll:analyze-workflows`
Analyze user message history to identify patterns, workflows, and automation opportunities.

**Arguments:**
- `file` (optional): Path to user-messages JSONL file (auto-detected if omitted)

---

## Git & Workflow

### `/ll:commit`
Create git commits with user approval (no Claude attribution).

### `/ll:describe_pr`
Generate comprehensive PR descriptions from branch changes.

### `/ll:open_pr`
Open a pull request for the current branch.

**Arguments:**
- `target_branch` (optional): Target branch for the PR (default: auto-detect)

**Flags:** `--draft` (create as draft PR)

### `/ll:cleanup_worktrees`
Clean up stale git worktrees and branches from parallel processing.

**Arguments:**
- `mode`: `run` (default), `dry-run`

### `/ll:manage_release`
Manage releases — create git tags, generate changelogs, and create GitHub releases.

**Arguments:**
- `action` (optional): `tag`, `changelog`, `release`, `bump`, `full` (interactive if omitted)
- `version` (optional): `vX.Y.Z`, `patch`, `minor`, `major` (auto-detects if omitted)

**Flags:** `--dry-run`, `--push`, `--draft`

---

## Session Management

### `/ll:handoff`
Generate continuation prompt for session handoff.

**Arguments:**
- `context` (optional): Description of current work context

### `/ll:resume`
Resume from a previous session's continuation prompt.

**Arguments:**
- `prompt_file` (optional): Path to continuation prompt (default: `.claude/ll-continue-prompt.md`)

---

## Automation Loops

### `/ll:create_loop`
Create FSM loop configurations interactively.

**Workflow:**
1. Select paradigm (goal, convergence, invariants, imperative)
2. Configure paradigm-specific parameters
3. Name and preview the loop
4. Save to `.loops/<name>.yaml` and validate

**See also:** `docs/generalized-fsm-loop.md` for paradigm details.

### `/ll:loop-suggester`
Analyze user message history to suggest FSM loop configurations automatically.

**Arguments:**
- `file` (optional): Path to ll-messages JSONL file (runs extraction if omitted)

**Features:**
- Detects repeated tool sequences (check-fix cycles, multi-constraint patterns)
- Maps patterns to appropriate paradigms (goal, invariants, convergence, imperative)
- Generates ready-to-use loop YAML with confidence scores
- Outputs to `.claude/loop-suggestions/`

**Usage:**
```bash
# Analyze recent messages (auto-extracts)
/ll:loop-suggester

# Analyze specific JSONL file
/ll:loop-suggester messages.jsonl
```

**Trigger keywords:** "suggest loops", "loop from history", "automate workflow"

---

## Quick Reference

| Command | Description |
|---------|-------------|
| `init` | Initialize project configuration |
| `help` | Show command help |
| `configure` | Interactive configuration editor |
| `toggle_autoprompt` | Toggle automatic prompt optimization |
| `check_code` | Run lint, format, type checks |
| `run_tests` | Execute test suites |
| `find_dead_code` | Identify unused code |
| `capture_issue` | Capture issues from conversation or description |
| `refine_issue` | Refine issue files (interactive or --auto mode) |
| `scan_codebase` | Find issues in code (technical analysis) |
| `scan_product` | Find issues in code (product-focused analysis) |
| `prioritize_issues` | Assign P0-P5 priorities |
| `ready_issue` | Validate and fix issue files |
| `verify_issues` | Check issues against code |
| `align_issues` | Validate issues against key documents |
| `normalize_issues` | Fix issue filenames lacking valid IDs |
| `sync_issues` | Sync local issues with GitHub Issues |
| `manage_issue` | Full issue lifecycle management |
| `iterate_plan` | Update implementation plans |
| `tradeoff_review_issues` | Evaluate issues for utility vs complexity |
| `audit_architecture` | Analyze code structure |
| `audit_docs` | Check documentation accuracy |
| `audit_claude_config` | Comprehensive config audit |
| `analyze-workflows` | Analyze user message patterns for automation |
| `commit` | Create git commits |
| `describe_pr` | Generate PR descriptions |
| `open_pr` | Open a pull request for current branch |
| `cleanup_worktrees` | Clean up stale worktrees and branches |
| `manage_release` | Manage releases, tags, and changelogs |
| `handoff` | Generate session handoff prompt |
| `resume` | Resume from continuation prompt |
| `create_loop` | Interactive FSM loop creation |
| `loop-suggester` | Suggest loops from message history |
| `create_sprint` | Create sprint with curated issue list |

---

## Common Workflows

```bash
# Get started with a new project
/ll:init

# Run all code quality checks
/ll:check_code

# Find and fix issues automatically
/ll:scan_codebase            # Technical analysis
/ll:scan_product             # Product analysis (if enabled)
/ll:normalize_issues
/ll:prioritize_issues
/ll:refine_issue --all --auto  # Auto-refine all issues (template v2.0 alignment)
/ll:manage_issue bug fix

# Prepare for a pull request
/ll:run_tests all
/ll:check_code
/ll:commit
/ll:open_pr
```
