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
  base_dir:         {{config.issues.base_dir}}
  completed_dir:    {{config.issues.completed_dir}}
  capture_template: {{config.issues.capture_template}}
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
  max_workers:        {{config.parallel.max_workers}}
  timeout_per_issue:  {{config.parallel.timeout_per_issue}}
  worktree_copy_files: {{config.parallel.worktree_copy_files}}
  stream_output:      {{config.parallel.stream_subprocess_output}}
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
    enabled:        {{config.commands.confidence_gate.enabled}}
    threshold:      {{config.commands.confidence_gate.threshold}}
  tdd_mode:         {{config.commands.tdd_mode}}
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
        description: "Yes, block implementation below threshold"
      - label: "false"
        description: "No, advisory only (default)"
    multiSelect: false

  - header: "Threshold"
    question: "Minimum confidence score to proceed with implementation?"
    options:
      - label: "{{current confidence_gate.threshold}} (keep)"
        description: "Keep current setting"
      - label: "70"
        description: "70 (permissive)"
      - label: "85"
        description: "85 (default)"
      - label: "95"
        description: "95 (strict)"
    multiSelect: false

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
  auto_detect:         {{config.continuation.auto_detect_on_session_start}}
  include_todos:       {{config.continuation.include_todos}}
  include_git:         {{config.continuation.include_git_status}}
  include_files:       {{config.continuation.include_recent_files}}
  max_continuations:   {{config.continuation.max_continuations}}
  expiry_hours:        {{config.continuation.prompt_expiry_hours}}
```

### Round 1 (4 questions)

```yaml
questions:
  - header: "Auto-detect"
    question: "Auto-detect continuation prompts on session start?"
    options:
      - label: "{{current auto_detect_on_session_start}} (keep)"
        description: "Keep current setting"
      - label: "true"
        description: "Yes, auto-detect (default)"
      - label: "false"
        description: "No, require manual /ll:resume"
    multiSelect: false

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
      - label: "100000"
        description: "100k (conservative)"
      - label: "150000"
        description: "150k (default)"
      - label: "200000"
        description: "200k (permissive)"
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
