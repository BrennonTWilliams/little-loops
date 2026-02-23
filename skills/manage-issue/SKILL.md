---
description: Autonomously manage issues - plan, implement, verify, and complete
argument-hint: "[type] [action] [issue-id]"
allowed-tools:
  - Bash(git:*)
arguments:
  - name: issue_type
    description: Type of issue (bug|feature|enhancement)
    required: true
  - name: action
    description: Action to perform (fix|implement|improve|verify|plan)
    required: true
  - name: issue_id
    description: Specific issue ID (e.g., BUG-004). If empty, finds highest priority.
    required: false
  - name: flags
    description: "Optional flags: --plan-only (stop after planning), --resume (continue from checkpoint), --gates (enable phase gates for manual verification), --dry-run (alias for --plan-only), --quick (skip deep research and confidence check), --force-implement (bypass confidence gate)"
    required: false
---

# Manage Issue

You are tasked with autonomously managing issues across the project. This command handles the full lifecycle: planning, implementation, verification, and completion.

## Configuration

This command uses project configuration from `.claude/ll-config.json`:
- **Issues base**: `{{config.issues.base_dir}}`
- **Categories**: `{{config.issues.categories}}`
- **Completed dir**: `{{config.issues.completed_dir}}`
- **Source dir**: `{{config.project.src_dir}}`
- **Test command**: `{{config.project.test_cmd}}`
- **Lint command**: `{{config.project.lint_cmd}}`
- **Custom verification**: `{{config.commands.custom_verification}}`

### Workflow Settings
- **Phase gates**: Disabled by default (enable with `--gates` flag)
- **Deep research**: Always enabled (Phase 1.5 spawns codebase-locator, codebase-analyzer, codebase-pattern-finder)

### Directory Structure

**IMPORTANT**: The `completed/` directory is a SIBLING to category directories, NOT a child:

```
{{config.issues.base_dir}}/
├── bugs/           # Active bugs (NEVER create completed/ here)
├── features/       # Active features (NEVER create completed/ here)
├── enhancements/   # Active enhancements (NEVER create completed/ here)
└── completed/      # ALL completed issues go here (sibling to categories)
```

---

## Phase 1: Find Issue

If issue_id is provided, locate that specific issue. Otherwise, find the highest priority issue of the specified type.

```bash
ISSUE_TYPE="${issue_type}"
ISSUE_ID="${issue_id}"
ISSUE_DIR="{{config.issues.base_dir}}"

# Map issue_type to directory
case "$ISSUE_TYPE" in
    bug) SEARCH_DIR="$ISSUE_DIR/bugs" ;;
    feature) SEARCH_DIR="$ISSUE_DIR/features" ;;
    enhancement) SEARCH_DIR="$ISSUE_DIR/enhancements" ;;
esac

# Find issue file
# Use strict matching: ID must be bounded by delimiters (-, _, .) to avoid
# matching BUG-1 against BUG-10 or ENH-1 against issue-enh-01-...
if [ -n "$ISSUE_ID" ]; then
    ISSUE_FILE=$(find "$SEARCH_DIR" -maxdepth 1 -name "*.md" 2>/dev/null | grep -E "[-_]${ISSUE_ID}[-_.]" | head -1)
else
    # Find highest priority (P0 > P1 > P2 > ...)
    for P in P0 P1 P2 P3 P4 P5; do
        ISSUE_FILE=$(ls "$SEARCH_DIR"/$P-*.md 2>/dev/null | sort | head -1)
        if [ -n "$ISSUE_FILE" ]; then
            break
        fi
    done
fi
```

---

## Phase 1.5: Deep Research

Before creating an implementation plan, spawn parallel sub-agents to gather comprehensive context about the issue.

**Skip this phase if**: Action is `verify` (verification doesn't need deep research), or `--quick` flag is set (proceed directly to planning with issue file context only)

### Research Tasks

Spawn these agents in parallel using the Task tool:
1. **codebase-locator** - Find all related files
2. **codebase-analyzer** - Understand current implementation
3. **codebase-pattern-finder** - Find similar patterns and reusable code

**CRITICAL**: Wait for ALL sub-agent tasks to complete before proceeding to planning.

See [templates.md](templates.md) for detailed agent prompts and research findings template.

---

## Phase 2: Create Implementation Plan

After reading the issue and completing research, create a comprehensive plan.

**If `--plan-only` or `--dry-run` flag is set**: Stop after writing the plan (do not implement).

### Recommended: Pre-Implementation Confidence Check

Before creating the plan, consider running the `confidence-check` skill to validate implementation readiness. This is advisory (non-blocking) and uses the research findings from Phase 1.5:

```
Use Skill tool with:
  skill: "ll:confidence-check"
  args: "[ISSUE-ID]"
```

- **Score >=70**: Proceed to plan creation
- **Score <70**: Review the gaps identified and consider addressing them before planning
- **Skip if**: Action is `verify`, `--quick` flag is set, or time constraints require proceeding immediately

### No Open Questions Rule

**CRITICAL**: Before writing the plan, resolve ALL open questions:

1. **Unclear Requirements** → Ask for clarification or research further
2. **Technical Uncertainty** → Spawn additional research tasks
3. **Design Decisions** → Present options to user, get explicit approval (**only with `--gates` flag**; without `--gates`, make the best autonomous decision and document the rationale in the plan)

**The plan must be complete and actionable with no unresolved questions.**

If questions arise that cannot be resolved, mark the issue as `NOT_READY` rather than proceeding with assumptions.

### Plan Creation Steps

1. **Read the issue file** completely
2. **Incorporate research findings** from Phase 1.5
3. **Resolve any remaining questions** before proceeding
4. **Design the solution** with specific changes
5. **Write plan** to `thoughts/shared/plans/YYYY-MM-DD-[ISSUE-ID]-management.md`

### Enhanced Plan Template

See [templates.md](templates.md) for the full Enhanced Plan Template structure.

---

## Phase 2.5: Confidence Gate Check

**Skip this phase if**: Action is `verify` or `plan`, `--quick` flag is set, or `config.commands.confidence_gate.enabled` is `false` (default).

When `config.commands.confidence_gate.enabled` is `true`, check the issue's `confidence_score` frontmatter before proceeding to implementation:

```
READ confidence_score from issue YAML frontmatter

IF confidence_score is absent:
  IF --force-implement flag is set:
    WARN: "⚠ Confidence gate: no confidence_score found. Proceeding due to --force-implement."
    PROCEED to Phase 3
  ELSE:
    HALT with message:
    "✗ Confidence gate: no confidence_score on file.
     Run /ll:confidence-check [ID] to evaluate readiness, or use --force-implement to bypass."
    STOP (do not proceed to Phase 3)

ELSE IF confidence_score < config.commands.confidence_gate.threshold:
  IF --force-implement flag is set:
    WARN: "⚠ Confidence gate: score [SCORE]/100 is below threshold [THRESHOLD]. Proceeding due to --force-implement."
    PROCEED to Phase 3
  ELSE:
    HALT with message:
    "✗ Confidence gate: score [SCORE]/100 is below threshold [THRESHOLD].
     Run /ll:confidence-check [ID] to evaluate readiness, or use --force-implement to override."
    STOP (do not proceed to Phase 3)

ELSE:
  LOG: "✓ Confidence gate: score [SCORE]/100 meets threshold [THRESHOLD]."
  PROCEED to Phase 3
```

---

## Phase 3: Implement

### Resuming Work (--resume flag)

If `--resume` flag is specified:

1. **Read continuation prompt** from `.claude/ll-continue-prompt.md` (if exists)
2. **Locate existing plan** matching the issue ID pattern
3. **Scan for progress** - look for `[x]` checkmarks in success criteria
4. **Present resume status** and verify previous work
5. **Continue from first unchecked item**

See [templates.md](templates.md) for the resume status display format.

### Implementation Process

1. **Create todo list** with TodoWrite
2. **Follow the plan** phase by phase
3. **Make atomic changes** - focused and minimal
4. **Mark todos complete** as you finish
5. **Update checkboxes in plan** as you complete each section

### Documentation Implementation Guidance

**IMPORTANT**: The `improve` action requires implementation, not just verification:

- For **documentation issues**: Edit or create the documentation files described in the issue
  - "Improve docs.md" means edit the file to add/update content, not review it for correctness
  - Make actual changes to improve clarity, completeness, or accuracy
  - Do not skip to verification without making file changes

- For **code issues**: Follow the same implementation process as `fix` and `implement` actions

- **All issue types**: The `improve` action is NOT a verification-only action (unlike `verify`)

### Context Monitoring & Proactive Handoff

**IMPORTANT**: Monitor context usage throughout implementation. When context is running low:

See [templates.md](templates.md) for the Session Continuation (handoff) template.

**Handoff Protocol**:

1. **Detect low context** - If you notice context approaching limits (conversation getting long, many files read), find a natural stopping point at a phase boundary.

2. **Generate handoff** - Before context exhaustion, write a continuation prompt to `.claude/ll-continue-prompt.md` using the Session Continuation template.

3. **Signal handoff** - Output a clear message:
```
CONTEXT_HANDOFF: Ready for fresh session
Continuation prompt written to: .claude/ll-continue-prompt.md
To continue: Start new session with content from that file
```

4. **Stop cleanly** - Do not attempt further work after signaling handoff.

This ensures work can continue with fresh context quality rather than degraded post-compaction context.

### Implementation Guidelines
- Follow existing code patterns
- Add/update tests for changed behavior
- Keep changes focused on the issue
- Include type hints for new code
- Add docstrings for public interfaces

### Phase Gate Protocol (requires --gates)

After completing each implementation phase:

1. **Run automated verification** - Execute all automated success criteria from the plan
2. **Present pause message** - List automated checks passed and manual steps to verify
3. **Wait for human confirmation** - Do NOT proceed until confirmation received

See [templates.md](templates.md) for the phase gate pause message format.

### Default Behavior

By default (no `--gates` flag):
- Skip all phase gate pauses
- Execute all phases sequentially
- Report all results in final output
- If critical errors occur, mark as INCOMPLETE
- **Do NOT use `AskUserQuestion` or any interactive tools** — all decisions must be made autonomously

> **Note**: The `improve` action requires full implementation (Plan → Implement → Verify → Complete). Do not interpret `improve` as a verification-only action or skip the Implementation phase. For all issue types including documentation, `improve` means make changes to files, not just review or verify them.

### Mismatch Handling Protocol

When reality diverges from the plan during implementation:

1. **Detect mismatch** - File doesn't exist, code structure differs, dependencies changed
2. **Present issue clearly** - Show expected vs. actual situation
3. **With `--gates` flag**: Use AskUserQuestion with options (Adapt/Update plan/Stop)
4. **Without `--gates` flag (default)**: Do NOT use `AskUserQuestion`. Adapt if minor, mark `INCOMPLETE` if significant

See [templates.md](templates.md) for mismatch detection and reporting formats.

---

## Phase 4: Verify

Run each verification command if configured (non-null). Skip silently if not configured, reporting SKIP status.

```bash
# Run tests if test_cmd is configured (non-null)
{{config.project.test_cmd}} tests/ -v

# Run linting if lint_cmd is configured (non-null)
{{config.project.lint_cmd}} {{config.project.src_dir}}

# Run type checking if type_cmd is configured (non-null)
{{config.project.type_cmd}} {{config.project.src_dir}}

# Run build if build_cmd is configured (non-null)
{{config.project.build_cmd}}

# Run smoke test if run_cmd is configured (non-null). For long-running processes (servers), start in background, wait briefly for startup, then terminate.
{{config.project.run_cmd}}

# Run custom verification (if configured)
# {{config.commands.custom_verification}}
```

All configured checks must pass before proceeding. Unconfigured (null) checks are skipped.

---

## Phase 4.5: Integration Review

After verification passes, review new/modified code for integration quality before completing the issue.

**Skip this phase if**: Action is `verify` (verification-only mode)

### Review Checklist

For each file created or substantially modified:
1. **Duplication check** - Flag any new code duplicating existing utilities
2. **Shared module usage** - Verify imports from existing shared modules
3. **Pattern conformance** - Confirm follows project patterns
4. **Integration points** - Verify connects to existing architecture

See [templates.md](templates.md) for the Integration Report template and handling warnings guidance.

---

## Phase 5: Complete Issue Lifecycle

### 1. Update Issue File

See [templates.md](templates.md) for the Resolution section template.

### 1.5. Append Session Log Entry

Append a session log entry to the issue file before moving it. Find the current session JSONL path in `~/.claude/projects/` and add an entry.

See [templates.md](templates.md) for the Session Log entry format.

### 2. Move to Completed

**CRITICAL**: Move to `{{config.issues.base_dir}}/{{config.issues.completed_dir}}/` - this is a SIBLING directory to bugs/features/enhancements, NOT a subdirectory within them.

```bash
# ✅ CORRECT: Move to sibling completed/ directory
git mv "{{config.issues.base_dir}}/[type]/[file].md" \
       "{{config.issues.base_dir}}/{{config.issues.completed_dir}}/"

# ❌ WRONG - NEVER do this (creates nested directory):
# git mv "{{config.issues.base_dir}}/bugs/P1-BUG-001.md" "{{config.issues.base_dir}}/bugs/completed/"
```

### 3. Commit All Changes

Commit source changes and moved issue file together in a single commit:

```bash
git add [modified files] "{{config.issues.base_dir}}/{{config.issues.completed_dir}}/[file].md"
git commit -m "[action]([component]): [description]

[issue_type] [ISSUE-ID]: [title]

- [change 1]
- [change 2]

Closes [ISSUE-ID]
"
```

---

## Final Report

See [templates.md](templates.md) for the Final Report template.

---

## Arguments

$ARGUMENTS

- **issue_type** (required): Type of issue
  - `bug` - Search in bugs directory
  - `feature` - Search in features directory
  - `enhancement` - Search in enhancements directory

- **action** (required): Action to perform
  - `fix` - Fix a bug
  - `implement` - Implement a feature
  - `improve` - Improve/enhance existing functionality or documentation
  - **IMPORTANT**: Requires full implementation (Plan → Implement → Verify → Complete)
  - For documentation: Must edit/create files, not just verify content
  - For code: Follow same implementation process as fix/implement
  - Behaves identically to fix/implement actions across all issue types
  - `verify` - Verify issue status only
  - `plan` - Create plan only (equivalent to --plan-only flag)

- **issue_id** (optional): Specific issue ID
  - If provided, work on that issue
  - If omitted, find highest priority

- **flags** (optional): Modify command behavior
  - `--plan-only` - Stop after creating the implementation plan
  - `--dry-run` - Alias for `--plan-only`
  - `--resume` - Resume from existing plan checkpoint
  - `--gates` - Enable phase gates for manual verification between phases
  - `--quick` - Skip deep research (Phase 1.5) and confidence check for faster planning
  - `--force-implement` - Bypass confidence gate (when `commands.confidence_gate.enabled` is true)

---

## Examples

```bash
# Fix highest priority bug
/ll:manage-issue bug fix

# Implement specific feature
/ll:manage-issue feature implement FEAT-042

# Create plan only, don't implement
/ll:manage-issue feature implement FEAT-042 --plan-only

# Dry run (alias for --plan-only)
/ll:manage-issue enhancement improve ENH-100 --dry-run

# Quick mode: skip deep research for faster planning
/ll:manage-issue bug fix BUG-050 --quick

# Resume interrupted work from checkpoint
/ll:manage-issue bug fix BUG-123 --resume

# Enable phase gates for careful manual verification
/ll:manage-issue feature implement FEAT-042 --gates

# Just verify an issue (no implementation)
/ll:manage-issue bug verify BUG-123

# Bypass confidence gate for a specific issue
/ll:manage-issue enhancement improve ENH-100 --force-implement
```
