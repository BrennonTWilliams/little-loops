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
| `--auto` | Non-interactive mode (no prompts) | `commit`, `refine-issue`, `prioritize-issues`, `format-issue`, `confidence-check`, `verify-issues`, `map-dependencies`, `issue-size-review`, `audit-issue-conflicts`, `link-epics` |
| `--gap-analysis` | Additive-only enrichment: fill gaps, never remove content; exempt from `max_refine_count` | `refine-issue` |
| `--full-rewrite` | Full-rewrite mode (legacy): overwrites sections with research findings | `refine-issue` |
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
- `area` (optional): `project`, `issues`, `commands`, `parallel`, `automation`, `documents`, `continuation`, `context`, `prompt`, `scan`, `sync`, `allowed-tools`, `hooks`, `design-tokens`

**Flags:** `--list`, `--show`, `--reset`

**Area notes:**
- `allowed-tools` — writes to `.claude/settings.json` or `.claude/settings.local.json`, not `ll-config.json`
- `hooks` — shows/validates ll- lifecycle hooks (not `ll-config.json`; hooks are automatic via plugin)

**Auto-update:** Like `/ll:init`, `configure` checks the installed package version and auto-upgrades if a mismatch is detected.

### `/ll:update`
Update the little-loops Claude Code plugin and pip package to the latest version. Consumer-first: works in any project.

**Flags:**
- `--plugin` — Update only the Claude Code plugin (`claude plugin update ll@little-loops`)
- `--package` — Update only the pip package (`pip install --upgrade little-loops`)
- `--all` — Update both components (same as no flag)
- `--dry-run` — Show what would be updated without making changes

**Default behavior:** If no component flag is given, both components are updated.

**Post-update config health check:** After a successful update, the skill validates `.ll/ll-config.json` against the current `config-schema.json` and reports any unknown or invalid top-level keys. Prints `[PASS] ll-config.json is valid` or `[WARN] Config issues detected` with the offending keys. Non-blocking — a check failure does not fail the overall update. Silently skips when `.ll/ll-config.json` is not present.

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

### `/ll:explore-api`
Guide the agent through the four-phase **Feathers Learning Test** lifecycle for an external API, SDK, or library — Ingest → Hypothesize → Execute → Refine — and persist a `LearnTestRecord` to the Learning Test Registry (`.ll/learning-tests/<slug>.md`).

Use before writing production code that depends on a third-party system: verifying event shapes, response structures, or return types with a real proof script rather than guessing.

**Arguments:**
- `target` (required): Free-text description of the system (e.g., `"Anthropic SDK streaming"`)
- `--assume "<claim>"` (repeatable): Pre-seed a claim as assumed-true without running a proof

**Outputs:** `.ll/learning-tests/<slug>.md` (YAML frontmatter record) and `.ll/learning-tests/raw/<slug>.txt` (proof script output)

**Registry CLI:** `ll-learning-tests check "<target>"` — returns the saved record (exit 0) or signals a miss (exit 1)

**Examples:**
```bash
/ll:explore-api "Anthropic SDK streaming"
/ll:explore-api "Claude API tool use" --assume "tools is a list" --assume "stop_reason is tool_use"
```

**Trigger keywords:** "explore API", "learning test", "prove API behavior", "feathers test"

---

## Issue Management

### `/ll:capture-issue`
Capture issues from conversation or natural language description.

**Arguments:** `input` (optional) - natural language description

**Flags:**
- `--quick` - Use minimal issue template (Summary, Behavior, Impact, Status only)
- `--parent EPIC-NNN` - Wire the new issue as a child of the given EPIC: sets `parent:` in the child's frontmatter and updates the EPIC's `relates_to:` list and `## Children` section

**Examples:**
```
/ll:capture-issue "retry logic fails on network timeout"
/ll:capture-issue "Add retry logic to sprint runner" --parent EPIC-1663
/ll:capture-issue "Fix log output truncation" --parent EPIC-1626 --quick
```

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
- Goals file (`.ll/ll-goals.md`) if present; otherwise goals are discovered automatically from project docs

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
- `issues` (optional): Comma-separated issue IDs to limit processing (e.g., `ENH-1362,BUG-123`). When omitted, all active issues are processed.
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
- `flags` (optional): `--auto` (non-interactive), `--dry-run` (preview), `--gap-analysis` (additive-only gap fill, does not count toward `max_refine_count`), `--full-rewrite` (legacy full-rewrite mode)

**Frontmatter write-back**: After detecting 2+ implementation options deposited into `Proposed Solution` in `--auto` mode, the command sets `decision_needed: true` in the issue's YAML frontmatter. If fewer than 2 options are deposited, the flag is cleared to `false` (or left absent if never set). This is skipped in `--dry-run` mode. Note: `/ll:confidence-check` can also set `decision_needed: true` independently when it detects an unresolved decision in Outcome Risk Factors.

### `/ll:decide-issue`
Resolve multi-option implementation decisions by gathering codebase evidence for each option and selecting the best fit. Where `/ll:refine-issue --auto` deposits competing approaches and sets `decision_needed: true` (or `/ll:confidence-check` detects an unresolved decision), this skill closes the loop — scoring every option and annotating the winner directly in the issue file.

**Arguments:**
- `issue_id` (required): Issue ID to decide on (e.g., FEAT-948, ENH-277)
- `flags` (optional): `--auto` (non-interactive), `--dry-run` (preview decision without writing)

**When to run**: After `/ll:refine-issue --auto` or `/ll:confidence-check` sets `decision_needed: true` in the issue frontmatter. Automated pipelines (`ll-auto`, `ll-parallel`) invoke this step automatically via the `decide_command` config template.

**Frontmatter write-back**: Sets `decision_needed: false` after annotating the winning option. In `--auto` mode when no formal `Option A / Option B` blocks are found (Phase 3b), also scans all sections for inline provisional decision language (`(e.g., ...)`, `TBD`, `"must be replaced with"`) and, if a single clear approach is identifiable, locks it in and sets `decision_needed: false` without user interaction. If no clear winner can be inferred, exits cleanly without prompting. Idempotent — skips annotation write if a `### Decision Rationale` section already exists.

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

**Arguments:**
- `issues` (optional): Comma-separated issue IDs to filter (e.g., `BUG-123,FEAT-456`). If omitted, scans all active issues.

**Trigger keywords:** "tradeoff review", "review issues", "prune backlog", "sense check issues"

### `/ll:audit-issue-conflicts`
Scan all open issues for conflicting requirements, objectives, or architectural decisions — outputs a ranked conflict report (high/medium/low severity) with recommended resolutions. Conflict types: requirement contradictions, conflicting objectives, architectural disagreements, scope overlaps.

**Flags:** `--auto` (apply all recommendations without prompting), `--dry-run` (report only, no changes written), `--cross-theme` (add Phase 2b cross-batch fingerprint sweep to catch conflicts between issues in different thematic groups — uses `ll-issues fingerprint` to find file-overlap pairs across batch boundaries without an LLM call, then dispatches targeted single-pair agents only for overlapping pairs)

**Trigger keywords:** "audit conflicts", "conflicting issues", "requirement conflicts", "check for contradictions"

### `/ll:product-analyzer`
Analyze codebase against product goals to identify feature gaps, user experience improvements, and business value opportunities. Returns raw YAML findings; use `/ll:scan-product` for full workflow with issue file creation.

**Arguments:**
- `focus-area` (optional): Limit analysis to a specific goal ID, persona, or one of `gaps|ux|opportunities`

**Prerequisites:**
- Product analysis enabled in config (`product.enabled: true`)
- Goals file (`.ll/ll-goals.md`) if present; otherwise goals are discovered automatically from project docs

### `/ll:confidence-check`
Pre-implementation confidence check that validates readiness and estimates outcome confidence before coding begins. Produces dual scores: a Readiness Score (go/no-go) and an Outcome Confidence Score (implementation risk).

**Arguments:**
- `issue_id` (optional): Specific issue to check

**Flags:** `--auto` (non-interactive), `--all` (batch all active issues), `--sprint <name>` (scope to sprint issues only), `--check` (check-only mode: run scoring without writes, print `[ID] check: score N/100` per issue, exit 1 if any fail)

**Findings write-back**: When concerns, gaps, or outcome risk factors are found (and `--check` is not set), the skill automatically appends a `## Confidence Check Notes` section to the issue file and stages it with `git add` — no confirmation prompt. This fires in both interactive and `--auto` modes. If all scores are clean, no write occurs.

**`decision_needed` write-back**: After writing Outcome Risk Factors, the skill scans the generated content for signal phrases ("open decision", "unresolved decision", "resolve before implementing", "decision point", "either/or", "either...or", "resolve before starting", "open question", "Option A/B", "Option A or"). If any are found, it sets `decision_needed: true` in the issue frontmatter (idempotent; skipped in `--check` mode). This ensures the autodev loop's decision gate fires automatically for issues where `confidence-check` identified an unresolved blocking decision.

**`missing_artifacts` write-back** (Phase 4.7): After writing Outcome Risk Factors, the skill scans for signal phrases indicating absent files or unwired components ("not yet created", "does not exist", "needs wiring", "missing artifact", "absent", "unwired component"). Before setting the flag, it checks the issue's `### Files to Create` section — if the absent file is listed there, it is a co-deliverable of this issue and the flag is suppressed. Only genuine pre-condition gaps (files that must exist before implementation starts) set `missing_artifacts: true`. Idempotent; skipped in `--check` mode.

**`implementation_order_risk` write-back** (Phase 4.9): After writing Outcome Risk Factors, the skill scans for signal phrases indicating implementation ordering advice rather than a true wiring gap ("co-deliverable", "implement tests first", "write tests before", "test-first", "tests are co-deliverables", "implement first so"). If any are found, it sets `implementation_order_risk: true` in the issue frontmatter. This flag captures ordering concerns that should NOT trigger the `run_wire` repair path in autodev — they belong in the Implementation Steps body text. Idempotent; skipped in `--check` mode.

### `/ll:issue-workflow`
Quick reference for the little-loops issue management workflow. Displays the issue lifecycle diagram and command order.

**Trigger keywords:** "issue workflow", "issue lifecycle", "what commands for issues"

### `/ll:issue-size-review`
Evaluate the size and complexity of active issues and propose decomposition for large ones. Assigns a complexity score (1–10) based on file count, section count, scope of changes, and estimated session time. Issues scoring **8 or above** are flagged as candidates for decomposition.

**When to use**: After refinement, before sprint planning. Signals that an issue may be too large: the Integration Map touches >8 files, the Proposed Solution has >5 distinct steps, or the issue spans multiple unrelated subsystems.

**Scoring scale**: 1–4 = small (implement directly); 5–7 = medium (review scope before implementing); 8–10 = large (decompose before implementing).

**Decomposition output**: For each oversized issue, proposes 2–4 smaller child issues with independent scopes, clear dependencies between them, and a suggested execution order. Child issues can be created directly from the output.

**Frontmatter write-back**: After assessing each issue, the skill writes `size: <label>` to the issue's YAML frontmatter (one of: `Small`, `Medium`, `Large`, `Very Large`). This is skipped when `--check` mode is active.

**TDD awareness**: The skill respects `config.commands.tdd_mode`. When `true`, decomposition proposals must not split wiring from the implementation that introduces it — wiring is part of the TDD cycle and belongs in the same child (see `skills/issue-size-review/SKILL.md` Phase 4 for the full rule and the "independently shippable" exception).

**Flags:**
- `--auto`: Non-interactive; auto-decomposes issues scoring ≥8 without prompting. Exception: if the issue has `score_ambiguity ≥ 18`, `score_complexity ≥ 18`, and a non-zero `outcome_confidence` in its frontmatter, decomposition is skipped — the confidence failure is qualitative, not a scope problem (see qualitative-skip guard)
- `--check`: Check-only mode; runs scoring without decomposition or frontmatter write-back; exits 1 if any issues score ≥5
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
| `CLOSE` | Issue is invalid, already covered, or misdirected | Close (set `status: done` in frontmatter) |
| `REFINE` | Issue is valid but under-specified or needs more research | Run `/ll:refine-issue` or `/ll:ready-issue` |
| `SKIP` | Good idea but poorly timed or lower priority than active work | Keep open, deprioritize, or remove from sprint |

The reason appears inline in verdict output (`NO-GO ✗ (CLOSE)`), batch summaries, and `--check` mode per-issue lines.

**Findings write-back:** After rendering a verdict, go-no-go checks whether the judge's output references specific files or functions not already in the issue body. If significant new information is found, it offers to insert a `## Go/No-Go Findings` section into the issue file (before `## Session Log`). In `--auto` mode the write happens without prompting; in `--check` mode writes are skipped entirely.

**Trigger keywords:** "go no go", "should I implement", "adversarial review", "worth implementing", "debate this issue"

### `/ll:map-dependencies`
Analyze active issues to discover cross-issue dependencies based on file overlap, validate existing dependency references, and propose new relationships. Delegates to `ll-deps` CLI subcommands.

**Flags:** `--auto` (non-interactive: applies only HIGH-confidence proposals)

**Trigger keywords:** "map dependencies", "dependency mapping", "find dependencies"

### `/ll:link-epics`
Discover parentless open issues and propose parent assignments to open epics using Jaccard similarity scoring on title and summary text. Groups proposals into HIGH/MEDIUM/LOW confidence tiers and confirms interactively (or applies HIGH-tier links automatically in `--auto` mode).

**Flags:**
- `--auto` — apply all HIGH-confidence proposals without prompting
- `--min-score MEDIUM|HIGH` — filter proposals to this confidence tier or above (default: MEDIUM)

**Output:** For each accepted link, writes `parent: <EPIC-NNN>` to the child issue frontmatter and appends the child to the epic's `relates_to:` list and `## Children` section.

**Trigger keywords:** "link epics", "assign to epic", "parentless issues", "orphan issues"

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

**Output:** Recommendations for removing stale issues, adding related backlog issues, and resolving dependency or contention problems. When any sprint member has a `parent:` referencing an EPIC, the output also includes an **EPIC Context** section that flags critical-path blocker gaps — EPIC children not in the sprint whose absence would stall a sprint member — with a concrete `ll-sprint edit --add` fix command for each gap.

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
Create FSM loop configurations — interactively or from a natural language description.

**Arguments (optional):**
- `description` — Natural language description of the loop. When provided, the skill infers loop type and parameters, shows a confirmation summary, and jumps directly to YAML preview — skipping the guided wizard.

**Workflow (no args — interactive):**
1. Select loop type (fix-until-clean, maintain-constraints, drive-metric, run-sequence, harness, RL variants, meta-optimize)
2. Configure type-specific parameters
3. Name and preview the FSM YAML
4. Save to `.loops/<name>.yaml` and validate

**Workflow (with args — fast path):**
1. Infer loop type and parameters from description
2. Confirm inferred values (or fall back to guided wizard with pre-filled defaults)
3. Preview, save, and validate

**Usage:**
```bash
/ll:create-loop
/ll:create-loop run mypy and ruff until they both pass
/ll:create-loop reduce lint errors to zero using ruff check, max 8 iterations
/ll:create-loop harness the refine-issue skill and iterate until the issue is implementation-ready
/ll:create-loop maintain tests passing and types clean, call it quality-guardian
```

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

### `/ll:verify-issue-loop`
Generate a ready-to-run FSM verification loop YAML from a single issue ID. Walks each acceptance criterion in order and asks an LLM whether the implementation satisfies it — failing fast on any criterion that fails. Verification counterpart to `/ll:create-eval-from-issues`: where `create-eval-from-issues` exercises a feature as a user would, `verify-issue-loop` checks that the implementation meets each acceptance criterion.

**Arguments:**
- `issue_id` (required): A single issue ID (e.g., `FEAT-919`, `ENH-950`, `BUG-347`). Accepts open or completed issues.

**Output:** `.loops/verify-<ISSUE-ID>-<slug>.yaml` (validated with `ll-loop validate` before writing)

**Structure:** One `verify-criterion-N` state per acceptance criterion with an `llm_structured` pass/fail evaluator; linear pass-routing (`on_yes: verify-criterion-<N+1>` or `done`; `on_no: failed`).

**Usage:**
```bash
/ll:verify-issue-loop FEAT-919
```

**See also:** `/ll:create-eval-from-issues`, `/ll:create-loop`

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
Review an existing FSM loop configuration for quality, correctness, consistency, and potential improvements. Analyzes all states and transitions, runs behavioral verification via `ll-loop simulate`, reports findings by severity (Error/Warning/Suggestion), proposes concrete fixes with before/after diffs, applies approved changes, and persists a review artifact to `.loops/reviews/<name>-<YYYYMMDD-HHMMSS>.md`.

**Arguments:**
- `loop_name` (optional): Name or path of the loop to review. If omitted, lists available loops to pick from.

**Flags:**
- `--auto`: Apply all eligible non-breaking fixes automatically. Still prints the full report.
- `--dry-run`: Report findings and scorecard only. Make no changes, skip artifact persistence.
- `--exercise`: In Step 2.5, also run `ll-loop run --max-iterations 1` in addition to `ll-loop simulate`.
- `--no-simulate`: Skip behavioral verification (Step 2.5) entirely.
- `--rubric-only`: Stop after displaying the rubric scorecard. No fix proposals, no artifact persistence.
- `--strict-semantic`: Run SR-* semantic checks in a fresh context seeded only with calibration examples from `reference.md` to prevent static-check findings from biasing judgment.

**Workflow phases:**

| Step | Phase | Description |
|------|-------|-------------|
| 1.5 | Description gate | Draft `description:` from FSM structure if absent/< 5 words; unblocks SR-1/SR-4 |
| 2a | Validation | Run `ll-loop validate`; surface V-* findings |
| 2b | Quality checks | QC-1 through QC-14, FA-1 through FA-6 |
| 2c | Semantic review | SR-1 through SR-4, FSM Flow Review narrative |
| 2.5 | Behavioral verification | `ll-loop simulate` → SIM-1/SIM-2/SIM-3 checks |
| 3 | Display findings | Findings table + FSM Flow Review + 6-dimension rubric scorecard |
| 4 | Propose fixes | Interactive or `--auto` fix application |
| 4.5 | Post-fix iteration | Re-run checks after fixes; surface RT-1 for regressions; max 3 rounds |
| 5 | Validate and save | `ll-loop validate` after changes; restore on failure |
| 6 | Summary | Findings count, fixes applied, pass/fail status |
| 6.5 | Persist artifact | Write `.loops/reviews/<name>-<timestamp>.md` with frontmatter + diffs |

**Simulation checks (SIM-*):**

| Check | Severity | Trigger |
|-------|----------|---------|
| SIM-1 | Warning | Simulation stalls — repeated state in `States visited:` before `max_iterations` |
| SIM-2 | Warning | Terminal reached in <2 iterations on a `max_iterations > 5` loop (no-op happy path) |
| SIM-3 | Error | Simulation hit `max_iterations` without reaching a terminal state |

**Semantic flow checks (SR-*):** In addition to structural (V-*, QC-*) and flow (FA-*) checks, the skill performs four semantic checks against the declared loop goal:

| Check | Severity | Description |
|-------|----------|-------------|
| SR-1 | Warning | Happy-path does not plausibly accomplish the declared goal (skipped if goal is absent or < 5 words) |
| SR-2 | Suggestion | State name implies a narrow gate (`check_*`, `verify_*`) but action text is broad analysis, or vice versa |
| SR-3 | Warning | `on_yes` routes backward to an earlier happy-path state (success routing backward is almost always a logic error) |
| SR-4 | Warning | A key activity phrase from the declared goal has no corresponding state name or action text |

SR-* findings are listed alongside FA-* findings in the Issues section of the output. The FSM Flow Review and Semantic Flow Review output blocks are always emitted, even when all finding counts are zero.

**Rubric scorecard:** After findings, the skill rates 6 dimensions (Clarity, Decomposition, Resilience, Observability, Idempotence, Cost-Efficiency) on a 1–5 scale for a composite score /30. When a prior `.loops/reviews/<name>-*.md` artifact exists, trend arrows (↑/↓/→) are shown. See `skills/review-loop/reference.md` Rubric Dimensions for full scoring criteria.

**Review artifact:** Persisted to `.loops/reviews/<name>-<YYYYMMDD-HHMMSS>.md` with YAML frontmatter (`loop`, `reviewed_at`, `scorecard`, `findings_count`, `simulation_result`, `fixes_applied`) and body sections (findings table, rubric justifications, simulation summary, fix diffs). See `skills/review-loop/reference.md` Review Artifact Schema.

**See also:** `/ll:create-loop`, `ll-loop validate`, `ll-loop show`, `ll-loop simulate`

### `/ll:debug-loop-run`
Analyze loop execution history to synthesize actionable issues from fault signals (BUG-class anomalies that broke the run) and effectiveness signals (ENH-class observations that the run completed but did not do useful work). Auto-selects the most recently interrupted/failed loop, or analyzes a named loop when specified.

**Arguments:**
- `loop_name` (optional): Loop name to analyze. If omitted, auto-selects the most recently updated interrupted/failed loop.
- `tail` (optional): Limit history events analyzed to the N most recent (default 200)
- `--skip-issue-creation` (flag): Skip issue creation entirely and exit cleanly after presenting signals
- `--auto` (flag): Non-interactive mode; suppress all `AskUserQuestion` calls and default to no for issue creation (implies `--skip-issue-creation`). Also activates when `--dangerously-skip-permissions` is in effect.

**Signal detection rules:**

_Fault Signals (BUG-class — broke the run):_
- Action `exit_code ≠ 0` repeated 3+ times on same state → BUG P2
- `loop_complete.terminated_by == "signal"` (SIGKILL) → BUG P2
- `loop_complete.terminated_by == "error"` AND no `evaluate.verdict == "error"` in run (FATAL_ERROR catch-all) → BUG P2
- Last `evaluate` before `loop_complete` has `verdict == "error"` (single occurrence — no threshold) → `BUG — Evaluate error terminated the loop` P2; uses `error` field (falls back to `reason`) from the failing evaluate event; de-duplicates against FATAL_ERROR when both hold (this signal supersedes)
- `evaluate.verdict == "fail"` 3+ times on same state → BUG P3
- State has `loop:` set AND `on_yes == on_no` (config-based, detected from FSM structure) → `BUG — Sub-loop verdict discarded` P3; child loop result is silently dropped regardless of outcome
- `rate_limit_exhausted` event present on a state (max rate-limit retries burned through) → BUG P3; surfaces upstream rate-limit pressure separate from generic retry loops. `rate_limit_waiting` heartbeat events in the same window indicate in-progress sleeps contributing to the budget.
- `throttle_hard` or `throttle_stop` event present on a state → BUG P2; state exceeded tool-call `hard_max` threshold — add `on_throttle_hard` routing or reduce scope to prevent hard stops. `throttle_warn` events in the same window signal the state was already near the limit.

_Effectiveness Signals (ENH-class — completed but did not do useful work):_
- Stub action body in resolved state map (e.g. `echo "5"` in a `score`/`evaluate` state, `echo "TODO …"`, `echo "Replace …"`) → ENH P2; surfaces unimplemented action stubs as a static `static_issues` entry distinct from the history-driven signal list
- `loop_complete.iterations == 1` AND no apply/refine/update/write/commit-prefixed state was visited → ENH P3 — likely phantom convergence (Signal 1 — iter-1 convergence without apply)
- `evaluate` state route distribution >95% to a single branch (≥10 evaluations single-run, or ≥20 across 5 most recent runs) → ENH P3 (Signal 2 — degenerate gate)
- Downstream state references `${captured.X.output}` AND producing state for capture `X` emits empty/whitespace output in >20% of occurrences (≥3 samples) → ENH P3 (Signal 4 — capture vacuum)
- `evaluate.type` is `output_numeric` or `convergence` AND captured value has stddev <1% of mean across ≥3 iterations AND has not crossed `evaluate.target` → ENH P3 (Signal 5 — numeric trajectory stall)
- True retry state (has `on_retry`/`max_retries`) entered 5+ times, or `retry_exhausted` event present → ENH P3; intentional cycling state (no retry config) noted informally unless >20 consecutive re-entries → ENH P4
- Avg action duration ≥ 30s across 3+ samples on same state → ENH P4

**Sub-loop visibility:** Step 2 uses `--resolved --json` so states with a `_subloop` key expose the child loop's resolved state map one level deep. Sub-loop states are classified separately and do not contribute to parent loop event counts.

**Output format:** Each run begins with an Execution Summary preamble before two grouped signal lists (`Fault Signals` and `Effectiveness Signals`); either heading is omitted when its count is zero:

```
### Execution Summary

**Loop goal**: "<loop description or (no description provided)>"
**Observed path**: <state_1> (×N₁) → <state_2> (×N₂) → ... [terminal | in-progress]
**Goal alignment**: <one-sentence assessment, or "Insufficient description to assess alignment.">

**Cross-signal note**: <adjacent states, signal types, and shared root-cause candidate>
(omitted when no co-occurring adjacent signals are found)

**Pattern note**: <sub-threshold behavioral observation>
(omitted when no sub-threshold patterns are detected)

### Fault Signals (N)

  [1] BUG P2 — <title>
  [2] BUG P3 — <title>
  ...

### Effectiveness Signals (M)

  [1] ENH P2 — <title>
  [2] ENH P3 — <title>
  ...
```

**Usage:**
```bash
# Auto-select most recent interrupted loop
/ll:debug-loop-run

# Analyze a specific loop
/ll:debug-loop-run issue-fixer

# Limit events analyzed
/ll:debug-loop-run issue-fixer --tail 100

# Headless: skip issue-creation prompt (for loop automation)
/ll:debug-loop-run issue-fixer --skip-issue-creation

# Non-interactive: suppress all prompts (for slash_command invocation)
/ll:debug-loop-run issue-fixer --auto
```

**Trigger keywords:** "analyze loop", "loop issues", "loop failures", "loop history issues"

**See also:** `/ll:review-loop`, `/ll:create-loop`, `/ll:audit-loop-run`, `ll-loop history`

### `/ll:audit-loop-run`
Audit whether a loop's execution actually achieved its stated goal — checking artifact mutations, threshold contracts, structural defects (phantom convergence, degenerate gates, rubric drift, sub-loop verdict laundering), and producing ranked improvement proposals. Auto-selects the most recent loop if no name is given.

**Arguments:**
- `loop_name` (optional): Loop name to assess. If omitted, auto-selects the most recently updated loop.
- `tail` (optional): Limit history events analyzed to the N most recent (default 200)
- `--no-rubric-audit` (flag): Skip the LLM rubric-vs-description pass (cost gate)
- `--skip-issue-creation` (flag): Skip issue creation entirely and exit cleanly after presenting proposals
- `--auto` (flag): Non-interactive mode; suppress all `AskUserQuestion` calls and default to no for issue creation (implies `--skip-issue-creation`). Also activates when `--dangerously-skip-permissions` is in effect.

**Sub-loop visibility:** Step 2 uses `--resolved --json`, making sub-loop states visible under `_subloop` keys in the FSM output. The Step 8 laundering check (`on_yes == on_no` on any sub-loop state) now operates on the fully-resolved state map.

**Verdict values:**
| Verdict | Condition |
|---------|-----------|
| `met` | Terminal reached AND all threshold contracts verified AND all expected artifact mutations occurred |
| `phantom` | Terminal reached AND (artifacts unchanged OR threshold unverified — only model self-reported) |
| `partial` | Terminal reached AND some but not all contracts satisfied |
| `degraded` | Loop completed but metric trended downward vs baseline |

**Output format:** Each assessment emits a Goal-vs-Outcome Scorecard followed by ranked improvement proposals:

```
### Goal-vs-Outcome Scorecard

**Goal**: "<loop description or (no description provided)>"
**Contract**: <threshold keys and values, or "none detected">
**Artifacts checked**: <list of paths and mutation status>
**Phase 1 signals**: <fault signal count, or "none">
**Verdict**: `<met | phantom | partial | degraded>`

**Rationale**: <one paragraph explaining the verdict>
```

**Usage:**
```bash
# Assess most recent loop
/ll:audit-loop-run

# Assess a specific loop
/ll:audit-loop-run issue-fixer

# Skip rubric audit (faster, lower cost)
/ll:audit-loop-run issue-fixer --no-rubric-audit

# Headless: skip issue-creation prompt (for loop automation)
/ll:audit-loop-run issue-fixer --skip-issue-creation

# Non-interactive: suppress all prompts (for slash_command invocation)
/ll:audit-loop-run issue-fixer --auto
```

**Trigger keywords:** "assess loop", "audit loop", "loop effectiveness", "loop goal", "phantom success", "loop artifacts", "did the loop work"

**See also:** `/ll:debug-loop-run`, `/ll:review-loop`, `/ll:create-loop`

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
5. Calls `ll-loop stop` for stuck-running loops and for stale-interrupted loops whose lock-file PID is still alive (orphaned lock holder blocking scope); removes the artifact file directly for stale-interrupted loops with a dead PID
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

**See also:** `/ll:debug-loop-run`, `/ll:review-loop`, `ll-loop stop`, `ll-loop monitor`

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

> **CLI fallback:** `ll-workflows propose --patterns step1.yaml --workflows step2.yaml` runs the same Step 3 logic directly from the command line, making the full pipeline scriptable end-to-end without an interactive Claude Code session. See [CLI reference](CLI.md#ll-workflows) for flags.

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
| `explore-api`^ | Explore external API/library behavior and record proof to Learning Test Registry |
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
| `decide-issue`^ | Resolve competing implementation options via codebase evidence scoring |
| `wire-issue`^ | Complete integration map — trace callers, config, docs, tests |
| `tradeoff-review-issues` | Evaluate issues for utility vs complexity |
| `issue-workflow`^ | Quick reference for issue management workflow |
| `issue-size-review`^ | Evaluate issue size/complexity and propose decomposition |
| `map-dependencies`^ | Analyze cross-issue dependencies based on file overlap |
| `audit-issue-conflicts`^ | Scan open issues for conflicting requirements and architectural decisions |
| `link-epics`^ | Assign parentless open issues to open epics via similarity scoring |
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
| `verify-issue-loop`^ | Generate verification loop YAML from a single issue's acceptance criteria |
| `loop-suggester` | Suggest loops from message history |
| `review-loop`^ | Review and improve existing FSM loop configurations |
| `debug-loop-run`^ | Analyze loop execution history: synthesizes an Execution Summary (goal alignment, observed path) and extracts actionable issues from fault and effectiveness signals |
| `audit-loop-run`^ | Audit loop goal achievement: checks artifact mutations, threshold contracts, phantom convergence, and produces ranked improvement proposals |
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
