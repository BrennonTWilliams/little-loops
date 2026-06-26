# Area-Specific Interactive Configuration

This document defines the interactive configuration flows for each area.

## Area: project

### Current Values

First, display current configuration:

```
Current Project Configuration
-----------------------------
  name:       {{config.project.name}}
  src_dir:    {{config.project.src_dir}}
  test_dir:   {{config.project.test_dir}}
  test_cmd:   {{config.project.test_cmd}}
  lint_cmd:   {{config.project.lint_cmd}}
  type_cmd:   {{config.project.type_cmd}}
  format_cmd: {{config.project.format_cmd}}
  build_cmd:  {{config.project.build_cmd}}
  run_cmd:    {{config.project.run_cmd}}
```

### Round 1: Core Commands (4 questions)

```yaml
questions:
  - header: "Source dir"
    question: "Which source directory contains your code?"
    options:
      - label: "{{current src_dir}} (keep)"
        description: "Keep current setting"
      - label: "src/"
        description: "Standard source directory"
      - label: "lib/"
        description: "Library source directory"
      - label: "."
        description: "Project root"
    multiSelect: false

  - header: "Test cmd"
    question: "Which test command should be used?"
    options:
      - label: "{{current test_cmd}} (keep)"
        description: "Keep current setting"
      - label: "pytest"
        description: "Python pytest"
      - label: "python -m pytest"
        description: "Python module mode"
      - label: "npm test"
        description: "Node.js npm test"
    multiSelect: false

  - header: "Lint cmd"
    question: "Which lint command should be used?"
    options:
      - label: "{{current lint_cmd}} (keep)"
        description: "Keep current setting"
      - label: "ruff check ."
        description: "Ruff linter (Python)"
      - label: "eslint ."
        description: "ESLint (JavaScript)"
      - label: "none"
        description: "No linter configured"
    multiSelect: false

  - header: "Type cmd"
    question: "Which type checker should be used?"
    options:
      - label: "{{current type_cmd}} (keep)"
        description: "Keep current setting"
      - label: "mypy"
        description: "Mypy (Python)"
      - label: "tsc --noEmit"
        description: "TypeScript compiler"
      - label: "none"
        description: "No type checker"
    multiSelect: false
```

### Round 2: Format, Build, and Run (3 questions)

```yaml
questions:
  - header: "Format cmd"
    question: "Which format command should be used?"
    options:
      - label: "{{current format_cmd}} (keep)"
        description: "Keep current setting"
      - label: "ruff format ."
        description: "Ruff formatter (Python)"
      - label: "prettier --write ."
        description: "Prettier (JavaScript)"
      - label: "none"
        description: "No formatter configured"
    multiSelect: false

  - header: "Build cmd"
    question: "Which build command should be used?"
    options:
      - label: "{{current build_cmd}} (keep)"
        description: "Keep current setting"
      - label: "npm run build"
        description: "Node.js npm build"
      - label: "pip install -e ."
        description: "Python editable install"
      - label: "none"
        description: "No build command"
    multiSelect: false

  - header: "Run cmd"
    question: "Which run/start command should be used?"
    options:
      - label: "{{current run_cmd}} (keep)"
        description: "Keep current setting"
      - label: "npm start"
        description: "Node.js start"
      - label: "go run ."
        description: "Go application"
      - label: "none"
        description: "No run command"
    multiSelect: false
```

---

## Area: issues

### Current Values

```
Current Issues Configuration
----------------------------
  base_dir:            {{config.issues.base_dir}}
  completed_dir:       {{config.issues.completed_dir}}
  capture_template:    {{config.issues.capture_template}}
  auto_commit:         {{config.issues.auto_commit}}
  auto_commit_prefix:  {{config.issues.auto_commit_prefix}}
```

### Round 1 (3 questions)

```yaml
questions:
  - header: "Base dir"
    question: "Where should issues be stored?"
    options:
      - label: "{{current base_dir}} (keep)"
        description: "Keep current setting"
      - label: ".issues"
        description: "Hidden issues directory"
      - label: "issues"
        description: "Visible issues directory"
      - label: "docs/issues"
        description: "Under docs directory"
    multiSelect: false

  - header: "Completed"
    question: "Where should completed issues be moved?"
    options:
      - label: "{{current completed_dir}} (keep)"
        description: "Keep current setting"
      - label: "completed"
        description: "Standard completed directory"
      - label: "archive"
        description: "Archive directory"
    multiSelect: false

  - header: "Template"
    question: "Which issue template style for capture?"
    options:
      - label: "{{current capture_template}} (keep)"
        description: "Keep current setting"
      - label: "full"
        description: "Full template with all sections"
      - label: "minimal"
        description: "Minimal template (Summary, Context only)"
    multiSelect: false
```

---

## Area: parallel

### Current Values

```
Current Parallel Configuration
------------------------------
  max_workers:                  {{config.parallel.max_workers}}
  timeout_per_issue:            {{config.parallel.timeout_per_issue}}
  worktree_copy_files:          {{config.parallel.worktree_copy_files}}
  stream_output:                {{config.parallel.stream_subprocess_output}}
  use_feature_branches:         {{config.parallel.use_feature_branches}}
  push_feature_branches:        {{config.parallel.push_feature_branches}}
  open_pr_for_feature_branches: {{config.parallel.open_pr_for_feature_branches}}
```

### Round 1 (4 questions)

```yaml
questions:
  - header: "Workers"
    question: "How many parallel workers for ll-parallel?"
    options:
      - label: "{{current max_workers}} (keep)"
        description: "Keep current setting"
      - label: "2"
        description: "2 workers (Recommended)"
      - label: "3"
        description: "3 workers"
      - label: "4"
        description: "4 workers (high resource usage)"
    multiSelect: false

  - header: "Timeout"
    question: "Timeout per issue (seconds)?"
    options:
      - label: "{{current timeout_per_issue}} (keep)"
        description: "Keep current setting"
      - label: "3600"
        description: "1 hour"
      - label: "7200"
        description: "2 hours (default)"
      - label: "14400"
        description: "4 hours"
    multiSelect: false

  - header: "Copy files"
    question: "Which files to copy to worktrees?"
    options:
      - label: "{{current worktree_copy_files}} (keep)"
        description: "Keep current setting"
      - label: ".env"
        description: "Environment file only"
      - label: ".env, .env.local"
        description: "Environment files"
      - label: "none"
        description: "No additional files"
    multiSelect: false

  - header: "Stream"
    question: "Stream subprocess output to console?"
    options:
      - label: "{{current stream_subprocess_output}} (keep)"
        description: "Keep current setting"
      - label: "true"
        description: "Yes, stream output"
      - label: "false"
        description: "No, capture only (default)"
    multiSelect: false
```

### Round 2 (1 question)

```yaml
questions:
  - header: "Feature branches"
    question: "Enable feature-branch mode for parallel runs (branch-per-issue)?"
    options:
      - label: "{{current use_feature_branches}} (keep)"
        description: "Keep current setting"
      - label: "true"
        description: "Yes — ll-parallel creates a local feature/<id>-<slug> branch per issue and retains it after the run (no push, no PR opened automatically). Applies to parallel waves only; does not affect ll-auto (sequential) or single-issue sprint sub-waves."
      - label: "false"
        description: "No, work in-place on current branch (default)"
    multiSelect: false
```

---

## Area: automation

### Current Values

```
Current Automation Configuration
--------------------------------
  timeout_seconds: {{config.automation.timeout_seconds}}
  max_workers:     {{config.automation.max_workers}}
  stream_output:   {{config.automation.stream_output}}
```

### Round 1 (3 questions)

```yaml
questions:
  - header: "Timeout"
    question: "Timeout per issue for ll-auto (seconds)?"
    options:
      - label: "{{current timeout_seconds}} (keep)"
        description: "Keep current setting"
      - label: "1800"
        description: "30 minutes"
      - label: "3600"
        description: "1 hour (default)"
      - label: "7200"
        description: "2 hours"
    multiSelect: false

  - header: "Workers"
    question: "Maximum workers for ll-auto?"
    options:
      - label: "{{current max_workers}} (keep)"
        description: "Keep current setting"
      - label: "1"
        description: "1 worker (sequential)"
      - label: "2"
        description: "2 workers (default)"
      - label: "4"
        description: "4 workers"
    multiSelect: false

  - header: "Stream"
    question: "Stream subprocess output?"
    options:
      - label: "{{current stream_output}} (keep)"
        description: "Keep current setting"
      - label: "true"
        description: "Yes, stream output (default)"
      - label: "false"
        description: "No, capture only"
    multiSelect: false
```

---

## Area: commands

### Current Values

```
Current Commands Configuration
-------------------------------
  pre_implement:    {{config.commands.pre_implement}}
  post_implement:   {{config.commands.post_implement}}
  confidence_gate:
    enabled:              {{config.commands.confidence_gate.enabled}}
    readiness_threshold:  {{config.commands.confidence_gate.readiness_threshold}}
    outcome_threshold:    {{config.commands.confidence_gate.outcome_threshold}}
  tdd_mode:         {{config.commands.tdd_mode}}
  max_refine_count: {{config.commands.max_refine_count}}
  rate_limits:
    max_wait_seconds:        {{config.commands.rate_limits.max_wait_seconds}}
    long_wait_ladder:        {{config.commands.rate_limits.long_wait_ladder}}
    circuit_breaker_enabled: {{config.commands.rate_limits.circuit_breaker_enabled}}
    circuit_breaker_path:    {{config.commands.rate_limits.circuit_breaker_path}}
```

### Round 1 (4 questions)

```yaml
questions:
  - header: "Pre-implement"
    question: "Run a command before implementation starts?"
    options:
      - label: "{{current pre_implement}} (keep)"
        description: "Keep current setting"
      - label: "none"
        description: "No pre-implement command (default)"
    multiSelect: false

  - header: "Gate"
    question: "Enable confidence score gate for manage-issue?"
    options:
      - label: "{{current confidence_gate.enabled}} (keep)"
        description: "Keep current setting"
      - label: "true"
        description: "Yes, block implementation below thresholds"
      - label: "false"
        description: "No, advisory only (default)"
    multiSelect: false

  - header: "Readiness"
    question: "Minimum readiness score (confidence_score) to proceed with implementation?"
    options:
      - label: "{{current confidence_gate.readiness_threshold}} (keep)"
        description: "Keep current setting"
      - label: "70"
        description: "70 (permissive)"
      - label: "85"
        description: "85 (default)"
      - label: "95"
        description: "95 (strict)"
    multiSelect: false

  - header: "Outcome"
    question: "Minimum outcome confidence score (outcome_confidence) to proceed with implementation?"
    options:
      - label: "{{current confidence_gate.outcome_threshold}} (keep)"
        description: "Keep current setting"
      - label: "60"
        description: "60 (permissive)"
      - label: "70"
        description: "70 (default)"
      - label: "85"
        description: "85 (strict)"
    multiSelect: false
```

### Round 2 (2 questions)

```yaml
questions:
  - header: "TDD"
    question: "Enable TDD mode (test-first) for manage-issue?"
    options:
      - label: "{{current tdd_mode}} (keep)"
        description: "Keep current setting"
      - label: "true"
        description: "Yes, write tests before implementation (Red/Green)"
      - label: "false"
        description: "No, standard implementation flow (default)"
    multiSelect: false

  - header: "Max refines"
    question: "Maximum lifetime /ll:refine-issue calls per issue (enforced by refine-to-ready-issue and by check_attempt_budget in recursive-refine)?"
    options:
      - label: "{{current max_refine_count}} (keep)"
        description: "Keep current setting"
      - label: "3"
        description: "3 (strict)"
      - label: "5"
        description: "5 (default)"
      - label: "10"
        description: "10 (permissive)"
    multiSelect: false
```

### Round 3 (2 questions)

```yaml
questions:
  - header: "Circuit breaker"
    question: "Enable cross-worktree rate-limit circuit breaker?"
    options:
      - label: "{{current rate_limits.circuit_breaker_enabled}} (keep)"
        description: "Keep current setting"
      - label: "true"
        description: "Yes, coordinate rate-limit state across worktrees (default)"
      - label: "false"
        description: "No, disable circuit breaker"
    multiSelect: false

  - header: "Circuit path"
    question: "Path to the shared rate-limit circuit state file (relative to project root)?"
    options:
      - label: "{{current rate_limits.circuit_breaker_path}} (keep)"
        description: "Keep current setting"
      - label: ".loops/tmp/rate-limit-circuit.json"
        description: "Default shared-state location under .loops/tmp/"
    multiSelect: false
```

---

## Area: documents

### Current Values

```
Current Documents Configuration
-------------------------------
  enabled: {{config.documents.enabled}}
  categories: {{config.documents.categories | keys}}
```

### Round 1 (2 questions)

```yaml
questions:
  - header: "Enable"
    question: "Enable document tracking for issue alignment?"
    options:
      - label: "{{current enabled}} (keep)"
        description: "Keep current setting"
      - label: "true"
        description: "Yes, enable document tracking"
      - label: "false"
        description: "No, disable (default)"
    multiSelect: false

  - header: "Manage"
    question: "What would you like to do with document categories?"
    options:
      - label: "Keep current categories"
        description: "No changes to existing categories"
      - label: "Add a category"
        description: "Add a new document category"
      - label: "Reset to empty"
        description: "Clear all categories"
    multiSelect: false
```

If "Add a category" selected, prompt for:
- Category name (free text via "Other")
- Description (free text via "Other")
- Files (comma-separated list via "Other")

---

## Area: continuation

### Current Values

```
Current Continuation Configuration
----------------------------------
  include_todos:       {{config.continuation.include_todos}}
  include_git:         {{config.continuation.include_git_status}}
  include_files:       {{config.continuation.include_recent_files}}
  max_continuations:   {{config.continuation.max_continuations}}
  expiry_hours:        {{config.continuation.prompt_expiry_hours}}
```

### Round 1 (3 questions)

```yaml
questions:
  - header: "Include"
    question: "What should continuation prompts include?"
    options:
      - label: "Todos"
        description: "Include pending todo items"
      - label: "Git status"
        description: "Include current git status"
      - label: "Recent files"
        description: "Include recently modified files"
    multiSelect: true

  - header: "Max retries"
    question: "Maximum automatic session continuations for CLI tools?"
    options:
      - label: "{{current max_continuations}} (keep)"
        description: "Keep current setting"
      - label: "3"
        description: "3 continuations (default)"
      - label: "5"
        description: "5 continuations"
      - label: "10"
        description: "10 continuations (maximum)"
    multiSelect: false

  - header: "Expiry"
    question: "How long should continuation prompts remain valid?"
    options:
      - label: "{{current prompt_expiry_hours}}h (keep)"
        description: "Keep current setting"
      - label: "24"
        description: "24 hours (default)"
      - label: "48"
        description: "48 hours"
      - label: "168"
        description: "1 week (168 hours)"
    multiSelect: false
```

---

## Area: context

### Current Values

```
Current Context Monitor Configuration
-------------------------------------
  enabled:   {{config.context_monitor.enabled}}
  threshold: {{config.context_monitor.auto_handoff_threshold}}%
  limit:     {{config.context_monitor.context_limit_estimate}} tokens
```

### Round 1 (3 questions)

```yaml
questions:
  - header: "Enable"
    question: "Enable context monitoring with auto-handoff?"
    options:
      - label: "{{current enabled}} (keep)"
        description: "Keep current setting"
      - label: "true"
        description: "Yes, enable monitoring"
      - label: "false"
        description: "No, disable (default)"
    multiSelect: false

  - header: "Threshold"
    question: "At what context usage % should auto-handoff trigger?"
    options:
      - label: "{{current auto_handoff_threshold}}% (keep)"
        description: "Keep current setting"
      - label: "70"
        description: "70% (more aggressive)"
      - label: "80"
        description: "80% (default)"
      - label: "90"
        description: "90% (more permissive)"
    multiSelect: false

  - header: "Limit"
    question: "Estimated context window size (tokens)?"
    options:
      - label: "{{current context_limit_estimate}} (keep)"
        description: "Keep current setting"
      - label: "0"
        description: "0 (auto-detect, recommended)"
      - label: "200000"
        description: "200k (standard Claude 4 models)"
      - label: "1000000"
        description: "1M (1M-context models)"
    multiSelect: false
```

---

## Area: prompt

### Current Values

```
Current Prompt Optimization Configuration
-----------------------------------------
  enabled:   {{config.prompt_optimization.enabled}}
  mode:      {{config.prompt_optimization.mode}}
  confirm:   {{config.prompt_optimization.confirm}}
  threshold: {{config.prompt_optimization.clarity_threshold}}
```

### Round 1 (4 questions)

```yaml
questions:
  - header: "Enable"
    question: "Enable automatic prompt optimization?"
    options:
      - label: "{{current enabled}} (keep)"
        description: "Keep current setting"
      - label: "true"
        description: "Yes, enable (default)"
      - label: "false"
        description: "No, disable"
    multiSelect: false

  - header: "Mode"
    question: "Which optimization mode?"
    options:
      - label: "{{current mode}} (keep)"
        description: "Keep current setting"
      - label: "quick"
        description: "Quick: config only (~2s, default)"
      - label: "thorough"
        description: "Thorough: spawns agent (~10-20s)"
    multiSelect: false

  - header: "Confirm"
    question: "Show diff before applying optimization?"
    options:
      - label: "{{current confirm}} (keep)"
        description: "Keep current setting"
      - label: "true"
        description: "Yes, confirm (default)"
      - label: "false"
        description: "No, auto-apply"
    multiSelect: false

  - header: "Threshold"
    question: "Minimum clarity score (1-10) to pass unchanged?"
    options:
      - label: "{{current clarity_threshold}} (keep)"
        description: "Keep current setting"
      - label: "5"
        description: "5 (optimize more prompts)"
      - label: "6"
        description: "6 (default)"
      - label: "7"
        description: "7 (optimize fewer prompts)"
    multiSelect: false
```

---

## Area: scan

### Current Values

```
Current Scan Configuration
--------------------------
  focus_dirs:       {{config.scan.focus_dirs}}
  exclude_patterns: {{config.scan.exclude_patterns}}
```

### Round 1 (2 questions)

```yaml
questions:
  - header: "Focus dirs"
    question: "Which directories should scans focus on?"
    options:
      - label: "{{current focus_dirs}} (keep)"
        description: "Keep current setting"
      - label: "src/, tests/"
        description: "Standard (default)"
      - label: "lib/, tests/"
        description: "Library structure"
      - label: "."
        description: "Entire project"
    multiSelect: false

  - header: "Excludes"
    question: "Which patterns should be excluded from scans?"
    options:
      - label: "{{current exclude_patterns}} (keep)"
        description: "Keep current setting"
      - label: "Standard defaults"
        description: "node_modules, __pycache__, .git"
      - label: "Extended"
        description: "Standard + dist, build, .venv"
    multiSelect: false
```

---

## Area: sync

### Current Values

```
Current Sync Configuration
--------------------------
  enabled:          {{config.sync.enabled}}
  provider:         {{config.sync.provider}}
  repo:             {{config.sync.github.repo}}
  label_mapping:    {{config.sync.github.label_mapping}}
  priority_labels:  {{config.sync.github.priority_labels}}
  sync_completed:   {{config.sync.github.sync_completed}}
```

### Round 1 (4 questions)

```yaml
questions:
  - header: "Enable"
    question: "Enable GitHub Issues synchronization?"
    options:
      - label: "{{current enabled}} (keep)"
        description: "Keep current setting"
      - label: "true"
        description: "Yes, sync with GitHub"
      - label: "false"
        description: "No, disable (default)"
    multiSelect: false

  - header: "Repository"
    question: "GitHub repository (owner/repo format)?"
    options:
      - label: "{{current repo}} (keep)"
        description: "Keep current setting"
      - label: "Auto-detect"
        description: "Detect from git remote (default)"
    multiSelect: false

  - header: "Priority Labels"
    question: "Add priority as GitHub labels (P0-P5)?"
    options:
      - label: "{{current priority_labels}} (keep)"
        description: "Keep current setting"
      - label: "true"
        description: "Yes, add priority labels (default)"
      - label: "false"
        description: "No, omit priority labels"
    multiSelect: false

  - header: "Sync Completed"
    question: "Sync completed issues to GitHub (close them)?"
    options:
      - label: "{{current sync_completed}} (keep)"
        description: "Keep current setting"
      - label: "false"
        description: "No, active only (default)"
      - label: "true"
        description: "Yes, also close completed"
    multiSelect: false
```

---

## Area: allowed-tools

**Note**: This area writes to `.claude/settings.json` or `.claude/settings.local.json` (Claude Code native settings files), not to `ll-config.json`. The `--reset` mode removes all `Bash(ll-` entries from the chosen file rather than resetting a config section.

### Current Values

First, detect and display current state:

```bash
SETTINGS_JSON_EXISTS=false
SETTINGS_LOCAL_EXISTS=false
[ -f ".claude/settings.json" ] && SETTINGS_JSON_EXISTS=true
[ -f ".claude/settings.local.json" ] && SETTINGS_LOCAL_EXISTS=true
```

```
Current Allowed Tools Configuration
------------------------------------
  settings.json:        [EXISTS / not found]
  settings.local.json:  [EXISTS / not found]
  ll- entries in settings.json:        [count, e.g. "12 entries" or "none"]
  ll- entries in settings.local.json:  [count, e.g. "12 entries" or "none"]
```

### Round 1 (2 questions)

```yaml
questions:
  - header: "Target File"
    question: "Which settings file should hold the ll- allowed tool entries?"
    options:
      - label: "settings.local.json (Recommended)"
        description: "Gitignored by default — keeps ll- permissions out of version control"
      - label: "settings.json"
        description: "Tracked in version control — shared with all project contributors"
      - label: "Skip / Remove entries"
        description: "Remove all ll- entries from both files (or skip if none exist)"
    multiSelect: false

  - header: "Entries"
    question: "Which ll- CLI commands should be allowed?"
    options:
      - label: "All ll- commands (Recommended)"
        description: "Authorize all 30 ll- CLI tools and handoff write: ll-action, ll-harness, ll-issues, ll-auto, ll-parallel, ll-sprint, ll-loop, ll-workflows, ll-messages, ll-session, ll-history, ll-history-context, ll-deps, ll-sync, ll-verify-docs, ll-verify-skills, ll-verify-design-tokens, ll-check-links, ll-gitignore, ll-migrate, ll-migrate-relationships, ll-migrate-status, ll-create-extension, ll-learning-tests, ll-logs, ll-generate-skill-descriptions, ll-adapt-skills-for-codex, ll-adapt-agents-for-codex, ll-doctor, ll-ctx-stats, Write(.ll/ll-continue-prompt.md)"
      - label: "Keep current"
        description: "Keep existing entries without changes"
    multiSelect: false
```

**Configuration result**: Perform the merge on the chosen target file using the same logic as SKILL.md Step 10:
1. Read target file (or start with `{"permissions": {"allow": [], "deny": []}}` if absent)
2. Remove all existing `Bash(ll-` entries from `permissions.allow`
3. Remove any existing `Write(.ll/ll-continue-prompt.md)` entry from `permissions.allow`
4. Append the canonical allow entries (if "All ll- commands" selected)
5. Write result back with 2-space indent, preserving all top-level keys

If "Skip / Remove entries" selected, remove all `Bash(ll-` entries and any `Write(.ll/ll-continue-prompt.md)` entry from both files (if they exist) and skip writing.

---

## Area: hooks

**Note**: This area writes to `.claude/settings.json` or `.claude/settings.local.json` (Claude Code native settings files), not to `ll-config.json`. The `--reset` mode removes all ll- hook entries from the chosen file rather than resetting a config section.

### Current Values

First, detect and display current state:

```bash
SETTINGS_JSON_EXISTS=false
SETTINGS_LOCAL_EXISTS=false
[ -f ".claude/settings.json" ] && SETTINGS_JSON_EXISTS=true
[ -f ".claude/settings.local.json" ] && SETTINGS_LOCAL_EXISTS=true
```

Display a unified table of all hooks from both sources:

```
Current Hook Configuration
--------------------------
  Source     Event             Matcher        Script                          Timeout  Status
  [Plugin]   SessionStart      *              adapters/claude-code/session-start.sh   5s    [exists/MISSING]
  [Plugin]   UserPromptSubmit  (no matcher)   user-prompt-check.sh            3s       [exists/MISSING]
  [Plugin]   PreToolUse        Write|Edit     check-duplicate-issue-id.sh     5s       [exists/MISSING]
  [Plugin]   PostToolUse       *              context-monitor.sh              5s       [exists/MISSING]
  [Plugin]   PostToolUse       Write          issue-completion-log.sh         5s       [exists/MISSING]
  [Plugin]   PostToolUse       Write          check-duplicate-issue-id-post.sh 5s      [exists/MISSING]
  [Plugin]   PostToolUse       Write|Edit     issue-auto-commit.sh            5s       [exists/MISSING]
  [Plugin]   Stop              (no matcher)   session-cleanup.sh              15s      [exists/MISSING]
  [Plugin]   PreCompact        *              adapters/claude-code/precompact.sh       5s    [exists/MISSING]
  [Plugin]   PreCompact        *              adapters/claude-code/precompact-handoff.sh  5s    [exists/MISSING]
  [Project]  ...               ...            ...                             ...      [exists/MISSING]
  [Local]    ...               ...            ...                             ...      [exists/MISSING]

  Source key: [Plugin] = hooks/hooks.json  [Project] = .claude/settings.json  [Local] = .claude/settings.local.json
  Status: exists = script path resolves  MISSING = script path not found (⚠ hook will fail)
```

Note: the table above shows Claude Code's `hooks/hooks.json` wiring. Codex
CLI users wire their hooks through the user-project's `.codex/hooks.json`
(written by `ll-init --hosts codex`), which points at the bash adapter scripts
under `scripts/little_loops/hooks/adapters/codex/`. The display layer of `/ll:configure hooks
show` does not currently introspect `.codex/hooks.json` — verify Codex
hooks via `cat .codex/hooks.json` or by checking the Codex startup
hook-trust dialog.

Read `hooks/hooks.json` (plugin hooks, always present) for `[Plugin]` rows. Read `.claude/settings.json` and `.claude/settings.local.json` for `[Project]` and `[Local]` rows (may not exist — show "(none)" if absent or if `hooks` key is absent).

For each hook entry, check whether the script path resolves by expanding `${CLAUDE_PLUGIN_ROOT}` or treating relative paths as relative to the project root.

### Sub-command: show

When `/ll:configure hooks show` is invoked (or `show` mode is entered interactively):
- Display the unified hook table (above)
- Flag any hooks with MISSING status
- Stop here

### Sub-command: validate

When `/ll:configure hooks validate` is invoked:
- For each hook in all sources, check:
  - **ERROR**: Script path does not exist (`[ -f <resolved_path> ]` fails)
  - **WARNING**: Script exists but is not executable (`[ -x <resolved_path> ]` fails)
  - **WARNING**: Timeout exceeds 30s for a blocking hook (UserPromptSubmit, PreToolUse)
- Report findings by severity:

```
Hook Validation Report
----------------------
  ERROR    [Plugin] PostToolUse/context-monitor.sh — script not found at resolved path
  WARNING  [Project] Stop/my-cleanup.sh — script exists but is not executable (chmod +x to fix)
  WARNING  [Project] UserPromptSubmit/slow-check.sh — timeout 60s exceeds 30s recommended for blocking hooks

  1 error, 2 warnings
```

If no issues: `All hooks validated successfully.`

### Sub-command: install

> **Note**: Manual hook installation is not needed. When `ll@little-loops` is globally enabled as a Claude Code plugin, all hooks in `hooks/hooks.json` fire automatically with correct `${CLAUDE_PLUGIN_ROOT}` resolution. Writing hooks to project settings files produces broken paths because `${CLAUDE_PLUGIN_ROOT}` is only set when hooks load from a registered plugin's own `hooks.json`.
>
> To verify hooks are active: `/ll:configure hooks show`

### Interactive Mode

When no sub-command is provided (`/ll:configure hooks`), present options:

```yaml
questions:
  - header: "Hooks"
    question: "What would you like to do with hook configuration?"
    options:
      - label: "show — display current hook configuration"
        description: "Show all hooks from plugin, settings.json, and settings.local.json"
      - label: "validate — check hooks for issues"
        description: "Verify script paths exist, are executable, and timeouts are reasonable"
    multiSelect: false
```

Then execute the chosen sub-command.

---

## Area: learning_tests

### Current Values

```
Current Learning Tests Configuration
-------------------------------------
  enabled:               {{config.learning_tests.enabled}}
  stale_after_days:      {{config.learning_tests.stale_after_days}}
  discoverability.mode:  {{config.learning_tests.discoverability.mode}}
```

### Round 1

```yaml
questions:
  - header: "Learning Tests"
    question: "Enable the Learning Test Registry for proof-first development?"
    options:
      - label: "Enable (turn on)"
        description: "Activate learning-test registry, discoverability nudge, and gate-loop hints"
      - label: "Disable (turn off)"
        description: "Silence all learning-test surfaces — hooks, hints, and audit loops become no-ops"
      - label: "Keep current ({{config.learning_tests.enabled}})"
        description: "No change"
    multiSelect: false

  - header: "Stale Days"
    question: "How many days before a learning test record is considered stale? (current: {{config.learning_tests.stale_after_days}})"
    options:
      - label: "7 (aggressive)"
        description: "Mark tests stale after one week — tight CI feedback"
      - label: "30 (default)"
        description: "Mark tests stale after one month"
      - label: "90 (relaxed)"
        description: "Mark tests stale after three months — long-lived proofs"
      - label: "Keep {{config.learning_tests.stale_after_days}}"
        description: "No change"
    multiSelect: false

  - header: "Discoverability"
    question: "How should learning-test gaps be surfaced during implementation? (current: {{config.learning_tests.discoverability.mode}})"
    options:
      - label: "warn (default)"
        description: "Show a warning when unfamiliar API code is encountered"
      - label: "block"
        description: "Halt implementation until the API is proven via a learning test"
      - label: "off"
        description: "No discoverability nudge — tests run silently"
      - label: "Keep {{config.learning_tests.discoverability.mode}}"
        description: "No change"
    multiSelect: false
```

### Configuration Result

Based on selections, update `.ll/ll-config.json`:

- If "Enable" selected: set `learning_tests.enabled: true`
- If "Disable" selected: set `learning_tests.enabled: false`
- If "Keep current" selected: preserve existing `enabled` value
- Map "Stale Days" choice to `learning_tests.stale_after_days` (omit if default 30)
- Map "Discoverability" choice to `learning_tests.discoverability.mode` (omit if default `warn`)

---

## Area: decisions

### Current Values

```
Current Decisions Configuration
--------------------------------
  enabled:       {{config.decisions.enabled}}
  log_path:      {{config.decisions.log_path}}
  auto_generate: {{config.decisions.auto_generate}}
```

### Round 1

```yaml
questions:
  - header: "Decisions"
    question: "Enable the decisions log for capturing architectural decisions?"
    options:
      - label: "Enable (turn on)"
        description: "Activate decisions log and auto-generation for tracked skill events"
      - label: "Disable (turn off)"
        description: "Disable decisions log — no decisions will be captured or generated"
      - label: "Keep current ({{config.decisions.enabled}})"
        description: "No change"
    multiSelect: false

  - header: "Log Path"
    question: "Where should the decisions log be stored? (current: {{config.decisions.log_path}})"
    options:
      - label: ".ll/decisions.yaml (default)"
        description: "Standard location under .ll/"
      - label: "Keep {{config.decisions.log_path}}"
        description: "No change"
    multiSelect: false

  - header: "Auto Generate"
    question: "Which skill events should trigger automatic decision capture? (current: {{config.decisions.auto_generate}})"
    options:
      - label: "[] (none, default)"
        description: "Do not auto-generate decisions — capture manually only"
      - label: "Keep {{config.decisions.auto_generate}}"
        description: "No change"
    multiSelect: false
```

### Configuration Result

Based on selections, update `.ll/ll-config.json`:

- If "Enable" selected: set `decisions.enabled: true`
- If "Disable" selected: set `decisions.enabled: false`
- If "Keep current" selected: preserve existing `enabled` value
- Map "Log Path" choice to `decisions.log_path` (omit if default `.ll/decisions.yaml`)
- Map "Auto Generate" choice to `decisions.auto_generate` (omit if default `[]`)

---

## Area: design_tokens

### Current Values

```
Current Design Tokens Configuration
------------------------------------
  enabled:         {{config.design_tokens.enabled}}
  path:            {{config.design_tokens.path}}
  primitives_file: {{config.design_tokens.primitives_file}}
  semantic_file:   {{config.design_tokens.semantic_file}}
  themes_dir:      {{config.design_tokens.themes_dir}}
  active_theme:    {{config.design_tokens.active_theme}}
  active:          {{config.design_tokens.active}}
  profiles_dir:    {{config.design_tokens.profiles_dir}}
  installed:       {{installed profiles list from <path>/<profiles_dir or "profiles">/ — list subdirectory names}}
```

Before showing the questions, enumerate installed profiles: list subdirectories of `<config.design_tokens.path>/<config.design_tokens.profiles_dir or "profiles">/`. Show each name in the picker.

### Round 1 (3 questions)

```yaml
questions:
  - header: "Enable"
    question: "Enable design tokens? (current: {{config.design_tokens.enabled}})"
    options:
      - label: "{{current enabled}} (keep)"
        description: "Keep current setting"
      - label: "true"
        description: "Yes, enable design tokens (default)"
      - label: "false"
        description: "No, disable"
    multiSelect: false

  - header: "Active Profile"
    question: "Switch the active profile (current: {{config.design_tokens.active}}). The active profile drives every artifact loop's tokens."
    options:
      - label: "{{current active}} (keep)"
        description: "Keep current profile"
      - label: "default"
        description: "Accessible neutral + blue brand. SaaS-friendly."
      - label: "editorial-mono"
        description: "Editorial serif + grayscale + ink-red accent."
      - label: "warm-paper"
        description: "Cream surfaces + soft brown + terracotta accent."
    multiSelect: false

  - header: "Theme"
    question: "Active theme (current: {{config.design_tokens.active_theme}}):"
    options:
      - label: "{{current active_theme}} (keep)"
        description: "Keep current theme"
      - label: "light"
        description: "Light theme"
      - label: "dark"
        description: "Dark theme"
    multiSelect: false
```

If the user picks a profile name that is NOT in the enumerated installed list (e.g. via "Other"):
  If the name IS one of ["default", "editorial-mono", "warm-paper"]:
    → trigger the materialization sub-step in "Configuration Result — design_tokens" below (do not warn)
  Else (genuinely custom/unknown profile):
    → warn that the profile does not yet exist under `<path>/<profiles_dir or "profiles">/`
      and that the runtime loader will degrade to no tokens until the profile is materialized.
      Write the value anyway — the user may be intentionally pre-configuring for an upcoming profile.

### Configuration Result — design_tokens

After writing the config values, apply materialization logic:

**Case A — Active profile changed to a new value:**

  BUILTIN = ["default", "editorial-mono", "warm-paper"]
  PROFILE_DIR = <config.design_tokens.path>/<profiles_dir or "profiles">/<new_active>
  TEMPLATE_DIR = scripts/little_loops/templates/design-tokens/profiles/<new_active>

  If PROFILE_DIR does not exist:
    If new_active is in BUILTIN AND TEMPLATE_DIR exists:
      If interactive (not DANGEROUSLY_SKIP_PERMISSIONS and not --auto):
        Use AskUserQuestion:
          "Profile '<new_active>' is not yet installed locally. Copy the built-in template now?"
          Options: "Yes, install it (Recommended)" / "No, skip"
        If yes:
          Bash(python3:*): python3 -c "import shutil; shutil.copytree('<TEMPLATE_DIR>', '<PROFILE_DIR>')"
          Report: ✓ Installed profile: <name> → <PROFILE_DIR>/
      Else (non-interactive / DANGEROUSLY_SKIP_PERMISSIONS or --auto):
        Bash(python3:*): python3 -c "import shutil; shutil.copytree('<TEMPLATE_DIR>', '<PROFILE_DIR>')"
        Report: ✓ Auto-installed profile: <name> → <PROFILE_DIR>/
    Else (profile is custom / not a built-in):
      [keep existing warning — user is intentionally pre-configuring]

**Case B — `enabled` changed from false → true AND profiles directory does not exist:**

  PROFILES_ROOT = <config.design_tokens.path>/<profiles_dir or "profiles">
  If PROFILES_ROOT does not exist:
    Bash(python3:*): python3 -c "import shutil; shutil.copytree('scripts/little_loops/templates/design-tokens/profiles', '<PROFILES_ROOT>', dirs_exist_ok=False)"
    Report: ✓ Installed all 3 built-in profiles → <PROFILES_ROOT>/

### Round 2 (3 questions — advanced)

Path and file-name overrides. Most users never touch these.

```yaml
questions:
  - header: "Path"
    question: "Design tokens base directory path (current: {{config.design_tokens.path}}):"
    options:
      - label: "{{current path}} (keep)"
        description: "Keep current path"
      - label: ".ll/design-tokens"
        description: "Default location"
    multiSelect: false

  - header: "Profiles Dir"
    question: "Subdirectory of <path> that holds profile directories (current: {{config.design_tokens.profiles_dir}}):"
    options:
      - label: "{{current profiles_dir}} (keep)"
        description: "Keep current setting"
      - label: "profiles"
        description: "Default subdirectory (used when null)"
    multiSelect: false
```

### Round 3 (3 questions — file names)

```yaml
questions:
  - header: "Primitives"
    question: "Primitives file name (current: {{config.design_tokens.primitives_file}}):"
    options:
      - label: "{{current primitives_file}} (keep)"
        description: "Keep current filename"
      - label: "primitives.json"
        description: "Default filename"
    multiSelect: false

  - header: "Semantic"
    question: "Semantic tokens file name (current: {{config.design_tokens.semantic_file}}):"
    options:
      - label: "{{current semantic_file}} (keep)"
        description: "Keep current filename"
      - label: "semantic.json"
        description: "Default filename"
    multiSelect: false

  - header: "Themes dir"
    question: "Themes subdirectory (current: {{config.design_tokens.themes_dir}}):"
    options:
      - label: "{{current themes_dir}} (keep)"
        description: "Keep current directory name"
      - label: "themes"
        description: "Default subdirectory"
    multiSelect: false
```

---

## Area: analytics

### Current Values

```
Current Analytics Configuration
--------------------------------
  enabled:              {{config.analytics.enabled}}
  capture.skills:       {{config.analytics.capture.skills}}
  capture.cli_commands: {{config.analytics.capture.cli_commands}}
  capture.corrections:  {{config.analytics.capture.corrections}}
  capture.file_events:  {{config.analytics.capture.file_events}}
```

### Round 1

```yaml
questions:
  - header: "Analytics"
    question: "Enable analytics capture for this project?"
    options:
      - label: "Enable (turn on)"
        description: "Track skill events, corrections, and file ops into .ll/history.db"
      - label: "Disable (turn off)"
        description: "Disable all analytics capture — history.db features become inactive"
      - label: "Keep current ({{config.analytics.enabled}})"
        description: "No change"
    multiSelect: false

  - header: "Skills"
    question: "Which skills should be captured? (current: {{config.analytics.capture.skills}})"
    options:
      - label: "["*"] (capture all)"
        description: "Capture events for all skills (default)"
      - label: "Keep {{config.analytics.capture.skills}}"
        description: "No change"
    multiSelect: false

  - header: "Corrections"
    question: "Capture correction events (issue refinements, re-runs)? (current: {{config.analytics.capture.corrections}})"
    options:
      - label: "true (capture)"
        description: "Record correction events in history.db (default)"
      - label: "false (skip)"
        description: "Do not capture correction events"
      - label: "Keep {{config.analytics.capture.corrections}}"
        description: "No change"
    multiSelect: false

  - header: "File Events"
    question: "Capture file operation events? (current: {{config.analytics.capture.file_events}})"
    options:
      - label: "true (capture)"
        description: "Record file create/edit/delete events in history.db (default)"
      - label: "false (skip)"
        description: "Do not capture file events"
      - label: "Keep {{config.analytics.capture.file_events}}"
        description: "No change"
    multiSelect: false
```

### Configuration Result

Based on selections, update `.ll/ll-config.json`:

- If "Enable" selected: set `analytics.enabled: true` and write full `capture` sub-object with all five fields (`skills`, `cli_commands`, `corrections`, `file_events`, `correction_patterns`)
- If "Disable" selected: set `analytics.enabled: false` (omit `capture` sub-object)
- If "Keep current" selected: preserve existing `enabled` value
- Map capture selections to `analytics.capture.*` fields (omit if matching schema defaults)

## Area: history

### Current Values

```
Current History Configuration
------------------------------
  velocity_window:                     {{config.history.velocity_window}}
  effort_fields:                       {{config.history.effort_fields}}
  max_age_days:                        {{config.history.max_age_days}}
  planning_skills:                     {{config.history.planning_skills}}
  session_digest.enabled:              {{config.history.session_digest.enabled}}
  session_digest.days:                 {{config.history.session_digest.days}}
  session_digest.char_cap:             {{config.history.session_digest.char_cap}}
  session_digest.sections:             {{config.history.session_digest.sections}}
  evolution.feedback_min_recurrence:   {{config.history.evolution.feedback_min_recurrence}}
  evolution.bypass_min_count:          {{config.history.evolution.bypass_min_count}}
  go_no_go.correction_penalty:         {{config.history.go_no_go.correction_penalty}}
  capture_issue.dup_overlap_threshold: {{config.history.capture_issue.dup_overlap_threshold}}
```

### Round 1

```yaml
questions:
  - header: "Session Digest"
    question: "Enable session digest injection at session start? (current: {{config.history.session_digest.enabled}})"
    options:
      - label: "Enable (turn on)"
        description: "Prepend a project-context summary to each new session from history.db (ENH-1907)"
      - label: "Disable (turn off)"
        description: "No session digest injection (default)"
      - label: "Keep current ({{config.history.session_digest.enabled}})"
        description: "No change"
    multiSelect: false

  - header: "Velocity Window"
    question: "How many recent issues to include when computing velocity? (current: {{config.history.velocity_window}})"
    options:
      - label: "10 (default)"
        description: "Use last 10 completed issues for velocity computation"
      - label: "Keep {{config.history.velocity_window}}"
        description: "No change"
    multiSelect: false

  - header: "Max Age"
    question: "Maximum age in days for history entries? (current: {{config.history.max_age_days}})"
    options:
      - label: "null (no limit, default)"
        description: "Include all history entries regardless of age"
      - label: "90 days"
        description: "Exclude entries older than 90 days"
      - label: "Keep {{config.history.max_age_days}}"
        description: "No change"
    multiSelect: false

  - header: "Planning Skills"
    question: "Which skill sessions are included in planning context queries? (current: {{config.history.planning_skills}})"
    options:
      - label: "Default (create-sprint, scope-epic, manage-issue, review-epic)"
        description: "Keep default planning skill set"
      - label: "Keep {{config.history.planning_skills}}"
        description: "No change"
    multiSelect: false
```

### Configuration Result

Based on selections, update `.ll/ll-config.json`:
- Map `session_digest.enabled` selection to `history.session_digest.enabled`
- Map `velocity_window` selection to `history.velocity_window`
- Map `max_age_days` selection to `history.max_age_days`
- Map `planning_skills` selection to `history.planning_skills`
- Omit sub-object keys if matching schema defaults

---

## Area: loops.run_defaults

### Current Values

```
Current Loop Run Defaults
--------------------------
  clear:         {{config.loops.run_defaults.clear}}
  show_diagrams: {{config.loops.run_defaults.show_diagrams}}
  mode:          {{config.loops.run_defaults.mode}}
```

### About

`loops.run_defaults` sets persistent CLI defaults for `ll-loop run`. Each field maps to a `ll-loop run` flag; setting a default here saves you from typing it on every invocation.

- **`clear`** (`bool`, default `false`) — clear the terminal before each loop run's output
- **`show_diagrams`** (`string | null`, default `null` = disabled) — render FSM diagrams while the loop runs. Valid values:
  - Topologies: `layered`, `neighborhood`, `inline`
  - Presets: `detailed`, `summary`, `clean`, `local`, `slim`, `oneline`
  - Bare flag sentinel: `default` (enables diagrams with the runner's built-in default style)
- **`mode`** (`string | null`, default `null`) — default execution mode flag passed to `ll-loop run`, e.g. `--dry-run` or `--interactive`

Example config block:

```json
{
  "loops": {
    "run_defaults": {
      "clear": true,
      "show_diagrams": "summary",
      "mode": "--dry-run"
    }
  }
}
```

### Round 1 (3 questions)

```yaml
questions:
  - header: "Clear"
    question: "Clear the terminal before each loop run? (current: {{config.loops.run_defaults.clear}})"
    options:
      - label: "{{current clear}} (keep)"
        description: "Keep current setting"
      - label: "false"
        description: "No — preserve terminal history (default)"
      - label: "true"
        description: "Yes — clear screen before each run"
    multiSelect: false

  - header: "Diagrams"
    question: "Show FSM diagrams during loop runs? (current: {{config.loops.run_defaults.show_diagrams}})"
    options:
      - label: "{{current show_diagrams}} (keep)"
        description: "Keep current setting"
      - label: "null (disabled)"
        description: "No diagrams (default)"
      - label: "summary"
        description: "Summary preset — compact state overview"
      - label: "layered"
        description: "Layered topology — full state graph"
    multiSelect: false

  - header: "Mode"
    question: "Default execution mode flag for ll-loop run? (current: {{config.loops.run_defaults.mode}})"
    options:
      - label: "{{current mode}} (keep)"
        description: "Keep current setting"
      - label: "null (none)"
        description: "No default mode — run normally (default)"
      - label: "--dry-run"
        description: "Preview FSM transitions without executing actions"
      - label: "--interactive"
        description: "Pause at each state for manual confirmation"
    multiSelect: false
```

### Configuration Result

Based on selections, update `.ll/ll-config.json`:

- Map "Clear" choice to `loops.run_defaults.clear` (omit if default `false`)
- Map "Diagrams" choice to `loops.run_defaults.show_diagrams`; use `null` to remove the key
- Map "Mode" choice to `loops.run_defaults.mode`; use `null` to remove the key
- Write the `loops.run_defaults` sub-object only when at least one field differs from its default
