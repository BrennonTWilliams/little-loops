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
| `--auto` | Non-interactive mode (no prompts) | `commit`, `refine-issue`, `prioritize-issues`, `format-issue`, `confidence-check`, `verify-issues`, `map-dependencies`, `issue-size-review` |
| `--verbose` | Include detailed output | `align-issues` |
| `--all` | Process all items instead of a single item | `align-issues`, `format-issue`, `confidence-check` |

Not all commands support all flags. See individual command documentation for supported flags.

---

## Setup & Configuration

### `/ll:init`
Initialize little-loops configuration for a project.

**Flags:** `--interactive`, `--yes` (non-interactive, accepts all defaults), `--force`

**Interactive wizard:** `--interactive` runs a multi-round setup that covers project type, issue directories, test commands, document tracking, sprint settings, and more. The final round offers to add ll- CLI command documentation to the target project's `.claude/CLAUDE.md` (or root `CLAUDE.md`). If the file already contains a `## little-loops` section, the write is skipped automatically.

**Auto-update:** If the installed `little_loops` package version does not match the plugin version, `init` automatically runs `pip install` to upgrade the package before proceeding.

### `/ll:help`
List all available little-loops commands with descriptions.

### `/ll:configure`
Interactively configure specific areas in ll-config.json.

**Arguments:**
- `area` (optional): `project`, `issues`, `commands`, `parallel`, `automation`, `documents`, `continuation`, `context`, `prompt`, `scan`, `sync`, `allowed-tools`, `hooks`

**Flags:** `--list`, `--show`, `--reset`

**Area notes:**
- `allowed-tools` — writes to `.claude/settings.json` or `.claude/settings.local.json`, not `ll-config.json`
- `hooks` — installs/shows/validates ll- lifecycle hooks in Claude Code settings files (not `ll-config.json`)

**Auto-update:** Like `/ll:init`, `configure` checks the installed package version and auto-upgrades if a mismatch is detected.

### `/ll:update`
Update one or more little-loops components: the plugin marketplace listing, the Claude Code plugin, and the pip package. Consolidates three separate update procedures into a single command.

**Flags:**
- `--marketplace` — Update only the plugin marketplace listing (`.claude-plugin/marketplace.json`)
- `--plugin` — Update only the Claude Code plugin (`claude plugin update ll`)
- `--package` — Update only the pip package (`pip install --upgrade little-loops`)
- `--all` — Update all three components (same as no flag)
- `--dry-run` — Show what would be updated without making changes

**Default behavior:** If no component flag is given, all three components are updated.

**Trigger keywords:** "update little-loops", "update plugin", "update marketplace", "update package", "ll update"

---

## Prompt Optimization

### `/ll:toggle-autoprompt`
Toggle automatic prompt optimization settings.

**Settings:** `enabled`, `mode`, `confirm`, `status` (default: status)

---

## Code Quality

### `/ll:check-code`
Run code quality checks (lint, format, types).

**Modes:** `lint`, `format`, `types`, `build`, `all`, `fix`

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

**Flags:** `--auto` (non-interactive: skips user approval, does not move resolved issues)

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
- `action`: `fix`, `implement`, `improve`, `verify`, `plan`
- `issue_id` (optional)

**Flags:** `--plan-only`, `--dry-run` (alias for --plan-only), `--resume`, `--gates`, `--quick` (skip deep research), `--force-implement` (bypass confidence gate)

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

### `/ll:product-analyzer`
Analyze codebase against product goals to identify feature gaps, user experience improvements, and business value opportunities.

**Prerequisites:**
- Product analysis enabled in config (`product.enabled: true`)
- Goals file exists (`.claude/ll-goals.md` by default)

### `/ll:confidence-check`
Pre-implementation confidence check that validates readiness and estimates outcome confidence before coding begins. Produces dual scores: a Readiness Score (go/no-go) and an Outcome Confidence Score (implementation risk).

**Arguments:**
- `issue_id` (optional): Specific issue to check

**Flags:** `--auto` (non-interactive), `--all` (batch all active issues)

### `/ll:issue-workflow`
Quick reference for the little-loops issue management workflow. Displays the issue lifecycle diagram and command order.

**Trigger keywords:** "issue workflow", "issue lifecycle", "what commands for issues"

### `/ll:issue-size-review`
Evaluate the size and complexity of active issues and propose decomposition for large ones.

**Flags:** `--auto` (non-interactive: auto-decomposes issues scoring >=8 only)

**Trigger keywords:** "issue size review", "decompose issues", "split large issues"

### `/ll:go-no-go`
Evaluate whether one or more issues should be implemented using an adversarial debate format. Launches two isolated background agents concurrently — one arguing for implementation, one against — each grounded in real codebase research. A third judge agent delivers a final GO or NO-GO verdict with structured reasoning, key arguments from both sides, and a deciding factor.

**Arguments:**
- `issue-id` (optional): One or more comma-separated issue IDs, or a sprint name. Defaults to the highest-priority open issue.

**Flags:**
- `--check`: Exit 0 on all GO, exit 1 on any NO-GO — enables FSM loop gating via `evaluate: type: exit_code`
- `--auto`: Non-interactive mode (skips write-back prompt; writes findings directly)

**NO-GO REASON sub-classification:** When the verdict is NO-GO, a structured reason is included indicating the recommended next action:

| Reason | Meaning | Recommended action |
|--------|---------|-------------------|
| `CLOSE` | Issue is invalid, already covered, or misdirected | Close or move to `completed/` |
| `REFINE` | Issue is valid but under-specified or needs more research | Run `/ll:refine-issue` or `/ll:ready-issue` |
| `SKIP` | Good idea but poorly timed or lower priority than active work | Keep open, deprioritize, or remove from sprint |

The reason appears inline in verdict output (`NO-GO ✗ (CLOSE)`), batch summaries, and `--check` mode per-issue lines.

**Findings write-back:** After rendering a verdict, go-no-go checks whether the judge's output references specific files or functions not already in the issue body. If significant new information is found, it offers to insert a `## Go/No-Go Findings` section into the issue file (before `## Session Log`). In `--auto` mode the write happens without prompting; in `--check` mode writes are skipped entirely.

**Trigger keywords:** "go no go", "should I implement", "adversarial review", "worth implementing", "debate this issue"

### `/ll:map-dependencies`
Analyze active issues to discover cross-issue dependencies based on file overlap, validate existing dependency references, and propose new relationships. Delegates to `ll-deps` CLI subcommands.

**Flags:** `--auto` (non-interactive: applies only HIGH-confidence proposals)

**Trigger keywords:** "map dependencies", "dependency mapping", "find dependencies"

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

### `/ll:update-docs`
Identify stale or missing documentation by analyzing git commits and completed issues since a given reference. Detects *coverage gaps* from recent work — complements `/ll:audit-docs` (which validates accuracy of existing content).

**Arguments:**
- `--since` (optional): Change window start — date (`YYYY-MM-DD`) or git ref (commit hash or branch). Defaults to last commit touching a doc file, or the watermark in `.claude/ll-update-docs.watermark` if present.

**Flags:** `--fix` (draft stub documentation sections inline for all gaps rather than prompting)

**Trigger keywords:** "update docs", "stale docs", "missing docs", "docs since sprint", "doc coverage", "documentation gaps"

### `/ll:audit-claude-config`
Comprehensive audit of Claude Code plugin configuration with parallel sub-agents.

**Scope:** `all`, `global`, `project`, `hooks`, `mcp`, `agents`, `commands`, `skills`

**Flags:** `--non-interactive`, `--fix`

### `/ll:analyze-workflows`
Analyze user message history to identify patterns, workflows, and automation opportunities.

**Arguments:**
- `file` (optional): Path to user-messages JSONL file (auto-detected if omitted)

### `/ll:analyze-history`
Analyze issue history to understand project health, trends, and progress. Delegates to `ll-history` CLI subcommands (`summary`, `analyze`, `export`). The `export` subcommand compiles topic-filtered issue excerpts from completed issue history.

**Trigger keywords:** "analyze history", "velocity report", "bug trends", "project health"

---

## Git & Workflow

### `/ll:commit`
Create git commits with user approval (no Claude attribution). Supports `--auto` flag for non-interactive use in automation contexts.

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
1. Select loop type (fix-until-clean, maintain-constraints, drive-metric, run-sequence)
2. Configure type-specific parameters
3. Name and preview the FSM YAML
4. Save to `.loops/<name>.yaml` and validate

**See also:** `docs/generalized-fsm-loop.md` for FSM schema details.

### `/ll:loop-suggester`
Analyze user message history to suggest FSM loop configurations automatically.

**Arguments:**
- `file` (optional): Path to ll-messages JSONL file (runs extraction if omitted)
- `--from-commands` (optional flag): Analyze the command/skill catalog instead of message history — works on fresh installations with no session history

**Features:**
- Detects repeated tool sequences (check-fix cycles, multi-constraint patterns)
- Maps patterns to appropriate loop types (fix-until-clean, maintain-constraints, drive-metric, run-sequence)
- Generates ready-to-use loop YAML with confidence scores
- Outputs to `.claude/loop-suggestions/`

**Usage:**
```bash
# Analyze recent messages (auto-extracts)
/ll:loop-suggester

# Analyze specific JSONL file
/ll:loop-suggester messages.jsonl

# Suggest loops from available commands/skills catalog (no history required)
/ll:loop-suggester --from-commands
```

**Trigger keywords:** "suggest loops", "loop from history", "automate workflow", "suggest loops from commands", "loop from catalog"

### `/ll:review-loop`
Review an existing FSM loop configuration for quality, correctness, consistency, and potential improvements. Analyzes all states and transitions, reports findings by severity (Error/Warning/Suggestion), proposes concrete fixes with before/after diffs, and applies approved changes.

**Arguments:**
- `loop_name` (optional): Name or path of the loop to review. If omitted, lists available loops to pick from.

**Flags:** `--auto` (apply safe fixes automatically), `--dry-run` (report only, no changes)

**See also:** `/ll:create-loop`, `ll-loop validate`, `ll-loop show`

### `/ll:analyze-loop`
Analyze loop execution history to synthesize actionable issues from failure patterns, SIGKILL terminations, retry floods, and performance anomalies. Auto-selects the most recently interrupted/failed loop, or analyzes a named loop when specified.

**Arguments:**
- `loop_name` (optional): Loop name to analyze. If omitted, auto-selects the most recently updated interrupted/failed loop.
- `tail` (optional): Limit history events analyzed to the N most recent (default 200)

**Signal detection rules:**
- Action `exit_code ≠ 0` repeated 3+ times on same state → BUG P2
- `loop_complete.terminated_by == "signal"` (SIGKILL) → BUG P2
- `loop_complete.terminated_by == "error"` (FATAL_ERROR) → BUG P2
- True retry state (has `on_retry`/`max_retries`) entered 5+ times, or `retry_exhausted` event present → ENH P3; intentional cycling state (no retry config) noted informally unless >20 consecutive re-entries → ENH P4
- Avg action duration ≥ 30s across 3+ samples on same state → ENH P4
- `evaluate.verdict == "fail"` 3+ times on same state → BUG P3

**Usage:**
```bash
# Auto-select most recent interrupted loop
/ll:analyze-loop

# Analyze a specific loop
/ll:analyze-loop issue-fixer

# Limit events analyzed
/ll:analyze-loop issue-fixer --tail 100
```

**Trigger keywords:** "analyze loop", "loop issues", "loop failures", "loop history issues"

**See also:** `/ll:review-loop`, `/ll:create-loop`, `ll-loop history`

### `/ll:cleanup-loops`
Find stuck or stale `ll-loop` processes, diagnose root causes from state and events files, and clean them up after user confirmation.

**Arguments:**
- `--dry-run` (flag): Preview discovered stuck/stale loops without making any changes
- `--threshold N` (optional): Minutes before a "running" loop's `updated_at` is considered stale (default: 15)

**What it does:**
1. Runs `ll-loop list --running --json` to enumerate all loops with state files
2. Checks each loop's PID liveness and `updated_at` staleness
3. Classifies loops: stuck-running, stale-interrupted, abandoned-handoff, terminal, or healthy
4. Prompts user to confirm cleanup of actionable loops
5. Calls `ll-loop stop` (stuck-running) or removes orphaned `.pid` files (stale-interrupted)
6. Tails the events file to surface root cause for each cleaned loop

**Usage:**
```bash
# Discover and clean all stuck/stale loops (with confirmation)
/ll:cleanup-loops

# Preview what would be cleaned without making changes
/ll:cleanup-loops --dry-run

# Use a custom staleness threshold (30 minutes)
/ll:cleanup-loops --threshold 30
```

**Trigger keywords:** "cleanup loops", "stuck loops", "clean loops", "stale loops", "kill stuck loops"

**See also:** `/ll:analyze-loop`, `/ll:review-loop`, `ll-loop stop`

### `/ll:workflow-automation-proposer`
Synthesize workflow patterns into concrete automation proposals. Final step (Step 3) of the `/ll:analyze-workflows` pipeline.

**Arguments:**
- `step1_file step2_file` (optional): Paths to step 1 and step 2 YAML files (auto-detected if omitted)

---

## Quick Reference

| Command | Description |
|---------|-------------|
| `init`^ | Initialize project configuration |
| `help` | Show command help |
| `configure`^ | Interactive configuration editor |
| `toggle-autoprompt` | Toggle automatic prompt optimization |
| `check-code` | Run lint, format, type checks |
| `run-tests` | Execute test suites |
| `find-dead-code` | Identify unused code |
| `capture-issue`^ | Capture issues from conversation or description |
| `format-issue`^ | Format issue files (interactive or --auto mode) |
| `scan-codebase` | Find issues in code (technical analysis) |
| `scan-product` | Find issues in code (product-focused analysis) |
| `product-analyzer`^ | Analyze codebase against product goals for feature gaps |
| `prioritize-issues` | Assign P0-P5 priorities |
| `ready-issue` | Validate and fix issue files |
| `verify-issues` | Check issues against code |
| `align-issues` | Validate issues against key documents |
| `normalize-issues` | Fix issue filenames lacking valid IDs |
| `sync-issues` | Sync local issues with GitHub Issues |
| `manage-issue`^ | Full issue lifecycle management |
| `iterate-plan` | Update implementation plans |
| `confidence-check`^ | Pre-implementation confidence check for readiness |
| `refine-issue` | Refine issues with codebase-driven research |
| `tradeoff-review-issues` | Evaluate issues for utility vs complexity |
| `issue-workflow`^ | Quick reference for issue management workflow |
| `issue-size-review`^ | Evaluate issue size/complexity and propose decomposition |
| `map-dependencies`^ | Analyze cross-issue dependencies based on file overlap |
| `go-no-go`^ | Adversarial go/no-go debate for issue implementation decisions |
| `audit-architecture` | Analyze code structure |
| `audit-docs`^ | Check documentation accuracy |
| `update-docs`^ | Identify stale or missing docs from recent commits and completed issues |
| `audit-claude-config`^ | Comprehensive config audit |
| `analyze-workflows` | Analyze user message patterns for automation |
| `analyze-history`^ | Analyze issue history for project health and trends |
| `commit` | Create git commits (supports `--auto` for non-interactive use) |
| `describe-pr` | Generate PR descriptions |
| `open-pr` | Open a pull request for current branch |
| `cleanup-worktrees` | Clean up stale worktrees and branches |
| `manage-release` | Manage releases, tags, and changelogs |
| `update`^ | Update little-loops components (marketplace, plugin, package) |
| `handoff` | Generate session handoff prompt |
| `resume` | Resume from continuation prompt |
| `create-loop`^ | Interactive FSM loop creation |
| `loop-suggester` | Suggest loops from message history |
| `review-loop`^ | Review and improve existing FSM loop configurations |
| `analyze-loop`^ | Analyze loop execution history and synthesize issues from failure patterns |
| `cleanup-loops`^ | Find and clean stuck or stale loop processes |
| `workflow-automation-proposer`^ | Synthesize workflow patterns into automation proposals |
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
