# Command Reference

Complete reference for all `/ll:` commands. Run `/ll:help` in Claude Code for an interactive version.

## Flag Conventions

Commands and skills support optional `--flag` modifiers passed after arguments. These are standard flags used across the project:

| Flag | Behavior | Used by |
|------|----------|---------|
| `--quick` | Reduce analysis depth for faster results | `scan-codebase`, `manage-issue`, `capture-issue` |
| `--deep` | Increase thoroughness, accept longer execution | `scan-codebase`, `audit-architecture`, `handoff`, `ready-issue` |
| `--focus [area]` | Narrow scope to a specific area | `scan-codebase` |
| `--dry-run` | Show what would happen without making changes | `manage-issue`, `align-issues`, `refine-issue`, `format-issue`, `manage-release`, `audit-issue-conflicts` |
| `--auto` | Non-interactive mode (no prompts) | `commit`, `refine-issue`, `prioritize-issues`, `format-issue`, `confidence-check`, `verify-issues`, `map-dependencies`, `issue-size-review`, `audit-issue-conflicts` |
| `--verbose` | Include detailed output | `align-issues` |
| `--all` | Process all items instead of a single item | `align-issues`, `format-issue`, `confidence-check` |
| `--sprint <name>` | Scope to issues in a named sprint definition | `map-dependencies`, `confidence-check`, `issue-size-review` |

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
Update the little-loops Claude Code plugin and pip package to the latest version. Consumer-first: works in any project.

**Flags:**
- `--plugin` — Update only the Claude Code plugin (`claude plugin update ll@little-loops`)
- `--package` — Update only the pip package (`pip install --upgrade little-loops`)
- `--all` — Update both components (same as no flag)
- `--dry-run` — Show what would be updated without making changes

**Default behavior:** If no component flag is given, both components are updated.

**Trigger keywords:** "update little-loops", "update plugin", "update package", "ll update"

### `/ll:publish` *(maintainers only — project-local, not shipped in plugin)*
Bump version in all source files (`plugin.json`, `marketplace.json`, `pyproject.toml`, `__init__.py`) and commit. Available only in the little-loops source repo via `.claude/commands/publish.md` — not distributed to consumer projects.

**Arguments:**
- `version` — New version string (e.g., `1.67.0`) or bump level (`patch`, `minor`, `major`)
- `--dry-run` — Preview changes without applying

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
- Goals file exists (`.ll/ll-goals.md` by default)

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

### `/ll:wire-issue`
Post-refinement wiring pass that completes an issue's **Integration Map** — the structured record of every file that must change when the issue is implemented. Where `/ll:refine-issue` fills in the _what_ and _why_, `wire-issue` traces the _where_: every caller, importer, config entry, doc section, test file, and side-effect file that the implementation will touch.

**The Integration Map** lives in the issue file under `## Integration Map`. A thin map might list 3–5 files; a wired map covers 10–20+, including non-obvious side effects like `__init__.py` exports, CLI registration hooks, and plugin manifests. Thin maps are the primary cause of incomplete implementations.

**When to run**: After `/ll:refine-issue` when the Integration Map section looks sparse — few files listed, no test files, no doc sections. Also before `/ll:confidence-check` to ensure the readiness score reflects full scope.

**Wiring categories searched**:
- **Callers**: functions/classes in other modules that call the target code
- **Config**: keys in `ll-config.json`, `config-schema.json`, `plugin.json`
- **Tests**: existing test files that cover the area, test files that should be created/updated
- **Docs**: sections in `docs/` that describe the changed behavior
- **Side effects**: `__init__.py` exports, CLI entry points, hook registrations, marketplace entries

**Arguments:**
- `issue_id` (optional): Issue ID to wire (e.g., `FEAT-948`, `ENH-277`). Reads most recent active issue if omitted.

**Flags:** `--auto` (non-interactive), `--dry-run` (preview without writing)

**Trigger keywords:** "wire issue", "missing integration points", "complete the wiring", "trace dependencies", "wiring pass"

### `/ll:tradeoff-review-issues`
Evaluate active issues for utility vs complexity trade-offs and recommend which to implement, update, or close.

**Trigger keywords:** "tradeoff review", "review issues", "prune backlog", "sense check issues"

### `/ll:audit-issue-conflicts`
Scan all open issues for conflicting requirements, objectives, or architectural decisions — outputs a ranked conflict report (high/medium/low severity) with recommended resolutions. Conflict types: requirement contradictions, conflicting objectives, architectural disagreements, scope overlaps.

**Flags:** `--auto` (apply all recommendations without prompting), `--dry-run` (report only, no changes written)

**Trigger keywords:** "audit conflicts", "conflicting issues", "requirement conflicts", "check for contradictions"

### `/ll:product-analyzer`
Analyze codebase against product goals to identify feature gaps, user experience improvements, and business value opportunities.

**Prerequisites:**
- Product analysis enabled in config (`product.enabled: true`)
- Goals file exists (`.ll/ll-goals.md` by default)

### `/ll:confidence-check`
Pre-implementation confidence check that validates readiness and estimates outcome confidence before coding begins. Produces dual scores: a Readiness Score (go/no-go) and an Outcome Confidence Score (implementation risk).

**Arguments:**
- `issue_id` (optional): Specific issue to check

**Flags:** `--auto` (non-interactive), `--all` (batch all active issues), `--sprint <name>` (scope to sprint issues only)

### `/ll:issue-workflow`
Quick reference for the little-loops issue management workflow. Displays the issue lifecycle diagram and command order.

**Trigger keywords:** "issue workflow", "issue lifecycle", "what commands for issues"

### `/ll:issue-size-review`
Evaluate the size and complexity of active issues and propose decomposition for large ones. Assigns a complexity score (1–10) based on file count, section count, scope of changes, and estimated session time. Issues scoring **8 or above** are flagged as candidates for decomposition.

**When to use**: After refinement, before sprint planning. Signals that an issue may be too large: the Integration Map touches >8 files, the Proposed Solution has >5 distinct steps, or the issue spans multiple unrelated subsystems.

**Scoring scale**: 1–4 = small (implement directly); 5–7 = medium (review scope before implementing); 8–10 = large (decompose before implementing).

**Decomposition output**: For each oversized issue, proposes 2–4 smaller child issues with independent scopes, clear dependencies between them, and a suggested execution order. Child issues can be created directly from the output.

**Flags:**
- `--auto`: Non-interactive; auto-decomposes issues scoring ≥8 without prompting
- `--sprint <name>`: Scope to issues in a named sprint definition only

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
- `--since` (optional): Change window start — date (`YYYY-MM-DD`) or git ref (commit hash or branch). Defaults to last commit touching a doc file, or the watermark in `.ll/ll-update-docs.watermark` if present.

**Flags:** `--fix` (draft stub documentation sections inline for all gaps rather than prompting)

**Trigger keywords:** "update docs", "stale docs", "missing docs", "docs since sprint", "doc coverage", "documentation gaps"

### `/ll:audit-claude-config`
Comprehensive audit of Claude Code plugin configuration with parallel sub-agents.

**Scope:** `all`, `global`, `project`, `hooks`, `mcp`, `agents`, `commands`, `skills`

**Flags:** `--non-interactive`, `--fix`

### `/ll:improve-claude-md`
Rewrite a project's CLAUDE.md using `<important if="condition">` XML blocks. Applies the 9-step
rewrite algorithm: leave foundational context (project identity, directory map, tech stack) bare;
wrap commands in one block; break apart rules into individual narrow-condition blocks; wrap domain
sections; delete linter-territory, code snippets, and vague instructions.

**Flags:**
- `--dry-run` — Preview the rewrite plan without modifying any file
- `--file <path>` — Target a specific file (default: `.claude/CLAUDE.md` or `./CLAUDE.md`)

**Trigger keywords:** "improve claude md", "rewrite claude md", "important if blocks", "instruction adherence", "restructure claude md"

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
- `prompt_file` (optional): Path to continuation prompt (default: `.ll/ll-continue-prompt.md`)

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

### `/ll:create-eval-from-issues`
Generate a ready-to-run FSM eval harness YAML from one or more issue IDs. Reads each issue's Expected Behavior, Use Case, and Acceptance Criteria sections to synthesize a natural-language execute prompt and `llm_structured` evaluation criteria — no hand-authoring required.

**Arguments:**
- `issue_ids` (required): One or more issue IDs (e.g., `FEAT-919`, `ENH-950`). Accepts open and completed issues.

**Output:** `.loops/eval-harness-<slug>.yaml` (validated with `ll-loop validate` before writing)

**Variants:**
- Single issue → Variant A: `initial: execute`, states: `execute → check_skill → done`
- 2+ issues → Variant B: `initial: discover`, states: `discover → execute → check_skill → advance → done`

**No `check_invariants`**: eval harnesses measure user experience quality, not code diff size.

**Usage:**
```bash
/ll:create-eval-from-issues FEAT-919
/ll:create-eval-from-issues FEAT-919 ENH-950
```

**See also:** `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md`, `/ll:create-loop`

### `/ll:loop-suggester`
Analyze user message history to suggest FSM loop configurations automatically.

**Arguments:**
- `file` (optional): Path to ll-messages JSONL file (runs extraction if omitted)
- `--from-commands` (optional flag): Analyze the command/skill catalog instead of message history — works on fresh installations with no session history

**Features:**
- Detects repeated tool sequences (check-fix cycles, multi-constraint patterns)
- Maps patterns to appropriate loop types (fix-until-clean, maintain-constraints, drive-metric, run-sequence)
- Generates ready-to-use loop YAML with confidence scores
- Outputs to `.ll/loop-suggestions/`

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

### `/ll:rename-loop`
Rename a loop (built-in or project-level) and update every reference to it so the loop system remains fully functional.

**Arguments:**
- `old_name` (required): Current loop name (bare identifier, no `.yaml` extension)
- `new_name` (required): New loop name (kebab-case identifier; may include a sub-directory prefix like `oracles/name`)
- `--dry-run` (flag): Preview all changes without applying them
- `--yes` (flag): Skip the confirmation prompt

**What it does:**
1. Locates the loop file in `.loops/` (project) or `scripts/little_loops/loops/` (built-in)
2. Renames the YAML file and updates its internal `name:` field
3. Updates all `loop:` sub-loop references in other YAML files
4. For built-in loops, updates tests and docs references
5. Confirms the change plan before applying (unless `--yes` is set)

**Usage:**
```bash
/ll:rename-loop fix-types fix-quality-and-tests
/ll:rename-loop old-loop-name new-loop-name --dry-run   # preview only
/ll:rename-loop old-name new-name --yes                 # skip confirmation
```

**Trigger keywords:** "rename loop", "rename a loop", "change loop name"

**See also:** `/ll:create-loop`, `/ll:review-loop`, `ll-loop show`

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
| `wire-issue`^ | Complete integration map — trace callers, config, docs, tests |
| `tradeoff-review-issues` | Evaluate issues for utility vs complexity |
| `issue-workflow`^ | Quick reference for issue management workflow |
| `issue-size-review`^ | Evaluate issue size/complexity and propose decomposition |
| `map-dependencies`^ | Analyze cross-issue dependencies based on file overlap |
| `go-no-go`^ | Adversarial go/no-go debate for issue implementation decisions |
| `audit-architecture` | Analyze code structure |
| `audit-docs`^ | Check documentation accuracy |
| `update-docs`^ | Identify stale or missing docs from recent commits and completed issues |
| `audit-claude-config`^ | Comprehensive config audit |
| `improve-claude-md`^ | Rewrite CLAUDE.md with `<important if>` blocks for scoped instruction attention |
| `analyze-workflows` | Analyze user message patterns for automation |
| `analyze-history`^ | Analyze issue history for project health and trends |
| `commit` | Create git commits (supports `--auto` for non-interactive use) |
| `describe-pr` | Generate PR descriptions |
| `open-pr` | Open a pull request for current branch |
| `cleanup-worktrees` | Clean up stale worktrees and branches |
| `manage-release` | Manage releases, tags, and changelogs |
| `update`^ | Update little-loops plugin and package (consumer-first) |
| `publish` *(project-local)* | Bump version in all source files (maintainers only — `.claude/commands/publish.md`, not shipped) |
| `handoff` | Generate session handoff prompt |
| `resume` | Resume from continuation prompt |
| `create-loop`^ | Interactive FSM loop creation |
| `create-eval-from-issues`^ | Generate eval harness YAML from issue IDs |
| `loop-suggester` | Suggest loops from message history |
| `review-loop`^ | Review and improve existing FSM loop configurations |
| `analyze-loop`^ | Analyze loop execution history and synthesize issues from failure patterns |
| `cleanup-loops`^ | Find and clean stuck or stale loop processes |
| `rename-loop`^ | Rename a loop and update all references |
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
