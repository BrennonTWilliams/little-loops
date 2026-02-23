# Command Reference

Complete reference for all `/ll:` commands. Run `/ll:help` in Claude Code for an interactive version.

## Flag Conventions

Commands and skills support optional `--flag` modifiers passed after arguments. These are standard flags used across the project:

| Flag | Behavior | Used by |
|------|----------|---------|
| `--quick` | Reduce analysis depth for faster results | `scan-codebase`, `manage-issue`, `capture-issue` |
| `--deep` | Increase thoroughness, accept longer execution | `scan-codebase`, `audit-architecture`, `handoff`, `ready-issue` |
| `--focus [area]` | Narrow scope to a specific area | `scan-codebase` |
| `--dry-run` | Show what would happen without making changes | `manage-issue`, `align-issues`, `refine-issue`, `format-issue`, `manage-release` |
| `--auto` | Non-interactive mode (no prompts) | `refine-issue`, `prioritize-issues`, `format-issue`, `confidence-check` |
| `--verbose` | Include detailed output | `align-issues` |
| `--all` | Process all items instead of a single item | `align-issues`, `format-issue`, `confidence-check` |

Not all commands support all flags. See individual command documentation for supported flags.

---

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

### `/ll:toggle-autoprompt`
Toggle automatic prompt optimization settings.

**Settings:** `enabled`, `mode`, `confirm`, `status` (default: status)

---

## Code Quality

### `/ll:check-code`
Run code quality checks (lint, format, types).

**Modes:** `lint`, `format`, `types`, `all`, `fix`

### `/ll:run-tests`
Run test suites with common patterns.

**Arguments:**
- `scope`: `unit`, `integration`, `all`, `affected`
- `pattern`: optional pytest -k filter

### `/ll:find-dead-code`
Analyze codebase for deprecated, unused, or dead code.

---

## Issue Management

### `/ll:capture-issue`
Capture issues from conversation or natural language description.

**Arguments:** `input` (optional) - natural language description

### `/ll:format-issue`
Format issue files to align with template v2.0 structure through section renaming, structural gap-filling, and boilerplate inference. Interactive by default, with optional `--auto` mode for non-interactive formatting.

**Arguments:**
- `issue_id` (optional): Issue ID to format (e.g., BUG-071, FEAT-225)
- `flags` (optional):
  - `--auto` - Non-interactive auto-format mode
  - `--all` - Process all active issues
  - `--dry-run` - Preview changes without applying

### `/ll:scan-codebase`
Scan codebase to identify bugs, enhancements, and features (technical analysis).

**Flags:** `--quick` (single-agent scan), `--deep` (extra verification), `--focus [area]` (narrow scope)

### `/ll:scan-product`
Scan codebase for product-focused issues based on goals document (requires `product.enabled: true`).

**Prerequisites:**
- Product analysis enabled in config
- Goals file exists (`.claude/ll-goals.md` by default)

### `/ll:prioritize-issues`
Analyze issues and assign priority levels (P0-P5).

### `/ll:ready-issue`
Validate issue file for accuracy and auto-correct problems.

**Arguments:** `issue_id` (optional)

### `/ll:verify-issues`
Verify all issue files against current codebase state.

### `/ll:align-issues`
Validate active issues against key documents for relevance and alignment.

**Arguments:**
- `category`: Document category (`architecture`, `product`, or `--all`)
- `flags` (optional): `--verbose` (detailed analysis), `--dry-run` (report only, no auto-fixing)

**Prerequisites:** Configure document tracking via `/ll:init --interactive`

### `/ll:normalize-issues`
Find and fix issue filenames lacking valid IDs (BUG-001, etc.).

### `/ll:sync-issues`
Sync local issues with GitHub Issues (push/pull/status).

**Arguments:** `mode` (optional) - `push`, `pull`, or `status`

### `/ll:manage-issue`
Autonomously manage issues - plan, implement, verify, complete.

**Arguments:**
- `type`: `bug`, `feature`, `enhancement`
- `action`: `fix`, `implement`, `improve`, `verify`
- `issue_id` (optional)

**Flags:** `--plan-only`, `--dry-run` (alias for --plan-only), `--resume`, `--gates`, `--quick` (skip deep research)

### `/ll:iterate-plan`
Iterate on existing implementation plans with updates.

**Arguments:** `plan_path` (optional)

### `/ll:refine-issue`
Refine issue files with codebase-driven research to fill knowledge gaps needed for implementation. Unlike `/ll:format-issue` (which aligns structure) or `/ll:ready-issue` (which validates accuracy), this command researches the codebase to identify and fill knowledge gaps.

**Arguments:**
- `issue_id` (required): Issue ID to refine (e.g., BUG-071, FEAT-225, ENH-042)
- `flags` (optional): `--auto` (non-interactive), `--dry-run` (preview)

### `/ll:tradeoff-review-issues`
Evaluate active issues for utility vs complexity trade-offs and recommend which to implement, update, or close.

**Trigger keywords:** "tradeoff review", "review issues", "prune backlog", "sense check issues"

---

## Sprint Management

### `/ll:create-sprint`
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

### `/ll:review-sprint`
AI-guided sprint health check that analyzes a sprint's current state and suggests improvements.

**Arguments:**
- `sprint_name` (optional): Sprint name to review (e.g., "my-sprint"). If omitted, lists available sprints.

**Trigger keywords:** "review sprint", "sprint health", "sprint review", "check sprint", "sprint suggestions", "optimize sprint"

**Output:** Recommendations for removing stale issues, adding related backlog issues, and resolving dependency or contention problems.

---

## Auditing & Analysis

### `/ll:audit-architecture`
Analyze codebase architecture for patterns and improvements.

**Focus:** `large-files`, `integration`, `patterns`, `organization`, `all`

**Flags:** `--deep` (spawn sub-agents for thorough analysis)

### `/ll:audit-docs`
Audit documentation for accuracy and completeness. Auto-fixable findings (wrong counts, outdated paths, broken links) can be fixed directly during the audit.

**Scope:** `full`, `readme`, `file:<path>`

**Flags:** `--fix` (auto-apply fixable corrections without prompting)

### `/ll:audit-claude-config`
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

### `/ll:describe-pr`
Generate comprehensive PR descriptions from branch changes.

### `/ll:open-pr`
Open a pull request for the current branch.

**Arguments:**
- `target_branch` (optional): Target branch for the PR (default: auto-detect)

**Flags:** `--draft` (create as draft PR)

### `/ll:cleanup-worktrees`
Clean up stale git worktrees and branches from parallel processing.

**Arguments:**
- `mode`: `run` (default), `dry-run`

### `/ll:manage-release`
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

### `/ll:create-loop`
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
| `toggle-autoprompt` | Toggle automatic prompt optimization |
| `check-code` | Run lint, format, type checks |
| `run-tests` | Execute test suites |
| `find-dead-code` | Identify unused code |
| `capture-issue` | Capture issues from conversation or description |
| `format-issue` | Format issue files (interactive or --auto mode) |
| `scan-codebase` | Find issues in code (technical analysis) |
| `scan-product` | Find issues in code (product-focused analysis) |
| `product-analyzer` | Analyze codebase against product goals for feature gaps |
| `prioritize-issues` | Assign P0-P5 priorities |
| `ready-issue` | Validate and fix issue files |
| `verify-issues` | Check issues against code |
| `align-issues` | Validate issues against key documents |
| `normalize-issues` | Fix issue filenames lacking valid IDs |
| `sync-issues` | Sync local issues with GitHub Issues |
| `manage-issue` | Full issue lifecycle management |
| `iterate-plan` | Update implementation plans |
| `confidence-check` | Pre-implementation confidence check for readiness |
| `refine-issue` | Refine issues with codebase-driven research |
| `tradeoff-review-issues` | Evaluate issues for utility vs complexity |
| `issue-workflow` | Quick reference for issue management workflow |
| `issue-size-review` | Evaluate issue size/complexity and propose decomposition |
| `map-dependencies` | Analyze cross-issue dependencies based on file overlap |
| `audit-architecture` | Analyze code structure |
| `audit-docs` | Check documentation accuracy |
| `audit-claude-config` | Comprehensive config audit |
| `analyze-workflows` | Analyze user message patterns for automation |
| `analyze-history` | Analyze issue history for project health and trends |
| `commit` | Create git commits |
| `describe-pr` | Generate PR descriptions |
| `open-pr` | Open a pull request for current branch |
| `cleanup-worktrees` | Clean up stale worktrees and branches |
| `manage-release` | Manage releases, tags, and changelogs |
| `handoff` | Generate session handoff prompt |
| `resume` | Resume from continuation prompt |
| `create-loop` | Interactive FSM loop creation |
| `loop-suggester` | Suggest loops from message history |
| `workflow-automation-proposer` | Synthesize workflow patterns into automation proposals |
| `create-sprint` | Create sprint with curated issue list |
| `review-sprint` | Review sprint health and suggest improvements |

---

## Common Workflows

```bash
# Get started with a new project
/ll:init

# Run all code quality checks
/ll:check-code

# Find and fix issues automatically
/ll:scan-codebase            # Technical analysis
/ll:scan-product             # Product analysis (if enabled)
/ll:normalize-issues
/ll:prioritize-issues
/ll:format-issue --all --auto  # Auto-format all issues (template v2.0 alignment)
/ll:manage-issue bug fix

# Prepare for a pull request
/ll:run-tests all
/ll:check-code
/ll:commit
/ll:open-pr
```
