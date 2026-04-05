# Interactive Mode Wizard Rounds

If `--interactive` flag is set, you MUST use the `AskUserQuestion` tool to gather user preferences. Do NOT just display prompts as text - actually prompt the user interactively.

**IMPORTANT**: Group related questions together using AskUserQuestion's multi-question capability (up to 4 questions per call) to reduce interaction rounds.

## Progress Tracking Setup

Before starting the wizard, initialize these counters:

```
STEP = 0      # Current round number (incremented before each round)
TOTAL = 6     # Working total (mandatory rounds: 1, 2, 3a, 6, 11, 12)
              # Round 3b is silent (automation always enabled, no user prompt)
              # Round 5a is conditional (only if parallel processing selected)
              # Round 7 is silent (advanced settings always skipped)
              # Hooks are always active via the plugin system — no installation round needed
```

Before each round's `AskUserQuestion` call, increment STEP and output:

```
**Step [STEP] of [TOTAL]** — [Round Name]
```

Use `~[TOTAL]` (tilde prefix) for Rounds 1–3a to signal the total may grow (Round 5a adds 1 if parallel processing is selected). Starting with Round 6, the total is known exactly.

## Wizard Introduction

Before starting Round 1, display the following introduction:

> **Welcome to little-loops setup!**
> This wizard creates `.ll/ll-config.json` — the configuration file that controls how little-loops manages your project's issues, code quality checks, and automation tools.

## Round 1: Core Project Settings

Increment STEP to 1 and output: **Step 1 of ~4** — Core Settings

Use a SINGLE AskUserQuestion call with 4 questions:

```yaml
questions:
  - header: "Name"
    question: "Is '[DETECTED_NAME]' the correct project name?"
    options:
      - label: "Yes, use [DETECTED_NAME]"
        description: "Keep the detected project name"
      - label: "No, different name"
        description: "Specify a custom project name"
    multiSelect: false

  - header: "Source Dir"
    question: "Which source directory contains your code?"
    options:
      - label: "[DETECTED_DIR]"
        description: "Detected from project structure"
      - label: "src/"
        description: "Standard source directory"
      - label: "lib/"
        description: "Library source directory"
      - label: "."
        description: "Project root"
    multiSelect: false

  - header: "Test Cmd"
    question: "Which test command should be used?"
    options:
      - label: "[DETECTED_TEST_CMD]"
        description: "Detected from project type"
      - label: "[ALT_TEST_CMD_1]"
        description: "Alternative test command"
      - label: "[ALT_TEST_CMD_2]"
        description: "Alternative test command"
    multiSelect: false

  - header: "Lint Cmd"
    question: "Which lint command should be used?"
    options:
      - label: "[DETECTED_LINT_CMD]"
        description: "Detected from project type"
      - label: "[ALT_LINT_CMD_1]"
        description: "Alternative lint command"
      - label: "[ALT_LINT_CMD_2]"
        description: "Alternative lint command"
    multiSelect: false
```

Populate options based on detected project type. Use these alternatives by language:

**Test commands:**
- Python: pytest, pytest -v, python -m pytest
- TypeScript: npm test, jest, vitest
- Node.js: npm test, yarn test, jest
- Go: go test ./..., go test -v ./...
- Rust: cargo test, cargo test --verbose
- Java (Maven): mvn test
- Java (Gradle): gradle test, ./gradlew test
- .NET: dotnet test

**Lint commands:**
- Python: ruff check ., flake8, pylint
- TypeScript: npm run lint, eslint .
- Node.js: npm run lint, eslint .
- Go: golangci-lint run, go vet ./...
- Rust: cargo clippy -- -D warnings, cargo check
- Java (Maven): mvn checkstyle:check
- Java (Gradle): ./gradlew checkstyleMain
- .NET: dotnet format --verify-no-changes

**Format commands:**
- Python: ruff format ., black ., autopep8
- TypeScript: npm run format, prettier --write .
- Node.js: npm run format, prettier --write ., eslint --fix
- Go: gofmt -w ., go fmt ./...
- Rust: cargo fmt
- Java: (none common)
- .NET: dotnet format

**Build/Run/Test dir options:**
- Python: tests/, test/, Same as src | Skip, python -m build, make build | Skip, python app.py, python -m flask run
- TypeScript: tests/, test/, \_\_tests\_\_/ | npm run build, yarn build, Skip | npm start, node server.js, Skip
- Node.js: tests/, test/, \_\_tests\_\_/ | npm run build, yarn build, Skip | npm start, node server.js, Skip
- Go: \*\_test.go files in same dir | go build, make build, Skip | go run ., go run cmd/main.go, Skip
- Rust: tests/ | cargo build, cargo build --release, Skip | cargo run, Skip
- Java (Maven): src/test/java/ | mvn package, Skip | mvn exec:java, Skip
- Java (Gradle): src/test/java/ | gradle build, ./gradlew build, Skip | gradle run, Skip
- .NET: tests/ | dotnet build, dotnet publish, Skip | dotnet run, Skip

## Round 2: Additional Configuration

Increment STEP to 2 and output: **Step 2 of ~4** — Additional Configuration

**First, detect existing issues directory:**
```bash
# Check for existing .issues/ folder
if [ -d ".issues" ]; then
  EXISTING_ISSUES_DIR=".issues"
elif [ -d "issues" ]; then
  EXISTING_ISSUES_DIR="issues"
else
  EXISTING_ISSUES_DIR=""
fi
```

**Issues directory (silent)**: If `EXISTING_ISSUES_DIR` is found, use it automatically. Otherwise, use `.issues` as the default. No prompting — users can change this value later by editing `.ll/ll-config.json` directly or via `/ll:configure`.

Use a SINGLE AskUserQuestion call with 3 questions:

```yaml
questions:
  - header: "Format Cmd"
    question: "Which format command should be used?"
    options:
      - label: "[DETECTED_FORMAT_CMD]"
        description: "Detected from project type"
      - label: "[ALT_FORMAT_CMD_1]"
        description: "Alternative format command"
      - label: "None"
        description: "No formatting command"
    multiSelect: false

  - header: "Scan Dirs"
    question: "Which directories should be scanned for code issues?"
    options:
      - label: "[DETECTED_FOCUS_DIRS]"
        description: "Detected from project structure"
      - label: "src/, tests/"
        description: "Standard source and test directories"
      - label: "Custom selection"
        description: "Specify custom directories"
    multiSelect: false

  - header: "Excludes"
    question: "Add custom exclude patterns beyond defaults?"
    options:
      - label: "Use defaults only"
        description: "Standard excludes for project type (node_modules, __pycache__, etc.)"
      - label: "Add custom patterns"
        description: "Specify additional patterns to exclude"
    multiSelect: false
```

## Round 3a: Core Features Selection

Increment STEP to 3 and output: **Step 3 of ~4** — Core Features

Use a SINGLE AskUserQuestion call with the features multi-select:

```yaml
questions:
  - header: "Features"
    question: "Which advanced features do you want to enable?"
    options:
      - label: "Parallel processing"
        description: "Process multiple issues in parallel using isolated git worktrees (requires ll-parallel CLI)"
      - label: "Context monitoring"
        description: "Get automatic reminders to save progress when a session is running low on context"
      - label: "GitHub sync"
        description: "Keep local issue files and GitHub Issues in sync (two-way push/pull)"
      - label: "Confidence gate"
        description: "Require a minimum readiness score before automated implementation proceeds"
      - label: "Test-Driven Development (TDD)"
        description: "Write failing tests before implementation — manage-issue will create tests first, then implement to pass them"
    multiSelect: true
```

This round always runs and determines which follow-up questions are needed in Round 5.

## Round 3b: Automation Features (Auto-Enabled)

All automation tools are always enabled — no user input required. Do NOT increment STEP or prompt the user.

# Always enable automation tools — configurable via /ll:configure
Treat all automation features as selected:
- Sprint management: always enabled
- FSM loops: always enabled
- Sequential automation (ll-auto): always enabled

**After Round 3b, recalculate TOTAL:**

```
Count active conditions for Round 5:
  ACTIVE = 0
  if Round 3a → "Parallel processing":     ACTIVE += 2  # worktree_files + parallel_workers (ll-parallel)

  if ACTIVE > 0: TOTAL += 1   # Round 5a only runs if parallel processing selected; max ACTIVE = 2
  # Round 5b and 5c are never shown (max ACTIVE never exceeds 2)
  # Rounds 11 (Allowed Tools) and 12 (CLAUDE.md Docs) are always shown — already counted in TOTAL = 6
```

## Round 5: Advanced Settings (Dynamic)

Build this round dynamically based on previous responses. **Skip entirely if no follow-up questions are needed.**

If Round 5a is presented, increment STEP by 1 and output: **Step [STEP] of [TOTAL]** — Advanced Settings
If Round 5b is presented, increment STEP by 1 and output: **Step [STEP] of [TOTAL]** — Advanced Settings (continued)
If Round 5c is presented, increment STEP by 1 and output: **Step [STEP] of [TOTAL]** — Advanced Settings (continued)

**Include questions based on these conditions (ordered list, max 2 active):**

1. **worktree_files** - If user selected "Parallel processing" in Round 3a
2. **parallel_workers** - If user selected "Parallel processing" in Round 3a

**Skip Round 5 entirely if neither condition is active** (i.e., user did not select "Parallel processing").

The following questions have been removed and their defaults applied silently:
- `issues_path` — not applicable (Round 2 no longer offers "custom directory"; existing dir or `.issues` used automatically)
- `completed_dir` → always "completed" (# Default: issues.completed_dir = "completed")
- `parallel_timeout` → always 3600 (# Default: parallel.timeout_per_issue = 3600)
- `threshold` → always 80% (# Default: context_monitor.auto_handoff_threshold = 80)
- `priority_labels` → always Yes (# Default: sync.github.priority_labels = true)
- `sync_completed` → always No (# Default: sync.github.sync_completed = false)
- `gate_readiness` → always 85 (# Default: commands.confidence_gate.readiness_threshold = 85)
- `gate_outcome` → always 70 (# Default: commands.confidence_gate.outcome_threshold = 70)
- `max_refine_count` → always 5 (# Default: commands.max_refine_count = 5; configurable via /ll:configure commands)
- `sprints_workers` → always 2 (# Default: sprints.default_max_workers = 2)
- `auto_timeout` → always 3600 (# Default: automation.timeout_seconds = 3600)

Round 5a only runs if parallel processing was selected. Maximum 2 conditions can be active simultaneously, so Round 5b and 5c are never shown.

**Overflow handling**: Not applicable — active conditions never exceed 2. All questions fit in a single Round 5a call.

### Round 5a: Advanced Settings

**Only run if user selected "Parallel processing" in Round 3a.** If parallel processing was not selected, skip Round 5 entirely and proceed to Round 6.

Use a SINGLE AskUserQuestion call with 2 questions:

```yaml
questions:
  - header: "Worktree"
    question: "Which additional files should be copied to each git worktree? (Note: .claude/ is always copied automatically)"
    options:
      - label: ".env"
        description: "Environment variables (API keys, secrets)"
      - label: ".env.local"
        description: "Local environment overrides"
      - label: ".secrets"
        description: "Secrets file"
    multiSelect: true

  - header: "Workers"
    question: "How many parallel workers should ll-parallel use?"
    options:
      - label: "2 (Recommended)"
        description: "Conservative — safe default for most systems"
      - label: "3"
        description: "Moderate parallelism"
      - label: "4"
        description: "Higher parallelism — needs more CPU/memory"
    multiSelect: false
```

### Round 5b and 5c

**Not used.** The maximum active condition count is 2 (worktree_files + parallel_workers). All questions fit in Round 5a. Rounds 5b and 5c are never shown.

**Configuration from Round 5 responses:**

If parallel is enabled and user selected files:
```json
{ "parallel": { "worktree_copy_files": ["<selected files>"] } }
```

If parallel is enabled and user selected non-default workers:
```json
{ "parallel": { "max_workers": 3 } }
```

If context monitoring is enabled (silently, from Round 3a selection):
```json
{ "context_monitor": { "enabled": true } }
```
- `auto_handoff_threshold` defaults to 80 — omit from config (schema default)

If GitHub sync is enabled (silently, from Round 3a selection):
```json
{ "sync": { "enabled": true } }
```
- `sync.github.priority_labels` defaults to true — omit from config (schema default)
- `sync.github.sync_completed` defaults to false — omit from config (schema default)

If confidence gate is enabled (silently, from Round 3a selection):
```json
{ "commands": { "confidence_gate": { "enabled": true } } }
```
- `readiness_threshold` defaults to 85 — omit from config (schema default)
- `outcome_threshold` defaults to 70 — omit from config (schema default)

If TDD Mode is selected in Round 3a:
```json
{ "commands": { "tdd_mode": true } }
```

Sprint management is always enabled — always include:
```json
{ "sprints": { "default_max_workers": 2 } }
```
- `sprints.default_max_workers` is hardcoded to 2, which differs from schema default (4); always include this key

**Notes:**
- Omit `issues.completed_dir` — "completed" is the schema default
- Omit `auto_handoff_threshold` — 80 is the schema default
- Only include non-default values. If user selects exactly `[".env"]` (the default), the `worktree_copy_files` key can be omitted
- The `.claude/` directory is always copied automatically regardless of `worktree_copy_files` setting
- Only include `parallel.max_workers` if user selected a non-default value (not 2); if 2 is selected, omit the key
- Omit `parallel.timeout_per_issue` — 3600 is the schema default
- Omit `automation.timeout_seconds` — 3600 is the schema default; always omit (hardcoded)
- Omit `sync.github.priority_labels` — true is the schema default
- Omit `sync.github.sync_completed` — false is the schema default
- Omit `commands.confidence_gate.readiness_threshold` — 85 is the schema default
- Omit `commands.confidence_gate.outcome_threshold` — 70 is the schema default
- Always include `sprints.default_max_workers: 2` (differs from schema default of 4); if user selected a non-default value (not 2), use their value instead
- FSM loops (`loops_dir` default is `.loops`) has no non-default settings to configure via init; the `.loops` directory is used automatically

**MANDATORY NEXT STEP - DO NOT SKIP:**
After completing Round 5 (or if Round 5 was skipped because no conditions matched), you MUST immediately proceed to **Round 6 (Document Tracking)** below. Round 6 is NOT optional. Do NOT display the summary yet. Do NOT say "All rounds complete." Continue reading and execute Round 6.

---

## Round 6: Document Tracking - MANDATORY, ALWAYS RUNS

**CRITICAL**: You MUST execute this round. This is Round 6 of the wizard. The wizard is NOT complete until you have asked the user about document tracking. If you skipped here without asking the Document Tracking question, GO BACK and ask it now.

Increment STEP by 1 and output: **Step [STEP] of [TOTAL]** — Document Tracking

**First, scan for markdown documents:**
```bash
# Find markdown files that might be key documents
find . -name "*.md" -not -path "*/.git/*" -not -path "*/node_modules/*" -not -path "*/{{config.issues.base_dir}}/*" -not -path "*/{{config.parallel.worktree_base}}/*" -not -path "*/thoughts/*" | head -30
```

Use a SINGLE AskUserQuestion call:

```yaml
questions:
  - header: "Docs"
    question: "Would you like to track key documents by category for issue alignment?"
    options:
      - label: "Use defaults (Recommended)"
        description: "Auto-detect architecture and product documents"
      - label: "Custom categories"
        description: "Define your own document categories"
      - label: "Skip"
        description: "Don't track documents"
    multiSelect: false
```

**If "Use defaults" selected:**
1. Scan codebase for .md files
2. Auto-detect architecture docs: files matching `**/architecture*.md`, `**/design*.md`, `**/api*.md`, `docs/*.md`
3. Auto-detect product docs: files matching `**/goal*.md`, `**/roadmap*.md`, `**/vision*.md`, `**/requirements*.md`
4. Present discovered files for confirmation:

```yaml
questions:
  - header: "Confirm"
    question: "Found these key documents. Include them all?"
    options:
      - label: "Yes, use all found"
        description: "[list architecture and product docs found]"
      - label: "Select specific files"
        description: "Choose which files to include"
      - label: "Skip document tracking"
        description: "Don't configure document tracking"
    multiSelect: false
```

**If "Custom categories" selected:**
1. Ask user to name their categories (comma-separated)
2. For each category, ask which files to include

**Configuration from Round 6 responses:**

If document tracking is enabled with defaults:
```json
{
  "documents": {
    "enabled": true,
    "categories": {
      "architecture": {
        "description": "System design and technical decisions",
        "files": ["docs/ARCHITECTURE.md", "docs/API.md"]
      },
      "product": {
        "description": "Product goals and requirements",
        "files": [".ll/ll-goals.md", "docs/ROADMAP.md"]
      }
    }
  }
}
```

If "Skip" selected or no documents found, omit the `documents` section entirely (disabled is the default).

**After completing Round 6, proceed to Round 7 (Extended Config Gate).**

## Round 7: Extended Configuration Gate (Auto-Skipped)

Advanced settings are always skipped during init — no user input required. Do NOT increment STEP or prompt the user.

# Always skip advanced settings — configurable via /ll:configure
Proceed to Round 11 (Allowed Tools). Rounds 8–10 are never shown during init.
Users can access test directory, build command, continuation, and prompt optimization settings via `/ll:configure`.

## Round 8: Project Advanced (Optional)

**Only run if user selected "Configure" in the Extended Config Gate.**

Increment STEP by 1 and output: **Step [STEP] of [TOTAL]** — Project Advanced

Use a SINGLE AskUserQuestion call with 4 questions:

```yaml
questions:
  - header: "Test Dir"
    question: "Do you have a separate test directory?"
    options:
      - label: "tests/ (Recommended)"
        description: "Standard tests/ directory"
      - label: "test/"
        description: "Alternative test/ directory"
      - label: "Same as src"
        description: "Tests are alongside source files"
    multiSelect: false

  - header: "Build Cmd"
    question: "Do you have a build command?"
    options:
      - label: "Skip (Recommended)"
        description: "No build step needed (common for scripting languages)"
      - label: "npm run build"
        description: "Node.js build"
      - label: "python -m build"
        description: "Python package build"
      - label: "make build"
        description: "Makefile build"
    multiSelect: false

  - header: "Run Cmd"
    question: "Do you have a run/start command?"
    options:
      - label: "Skip (Recommended)"
        description: "No run command needed"
      - label: "npm start"
        description: "Node.js start"
      - label: "python app.py"
        description: "Python application"
      - label: "go run ."
        description: "Go application"
    multiSelect: false

  - header: "Impl Hooks"
    question: "Run commands before or after issue implementation? (manage-issue hooks)"
    options:
      - label: "Skip (Recommended)"
        description: "No hooks — standard implementation flow"
      - label: "Post: run tests"
        description: "Run test suite after each implementation"
      - label: "Pre: lint, Post: tests"
        description: "Lint before starting, run tests after"
    multiSelect: false
```

**Configuration:** Only include `test_dir`, `build_cmd`, `run_cmd` if non-default values selected.

**Impl Hooks mapping:**
- "Skip" → omit `commands.pre_implement` and `commands.post_implement`
- "Post: run tests" → `{ "commands": { "post_implement": "<test_cmd from Round 1>" } }`
- "Pre: lint, Post: tests" → `{ "commands": { "pre_implement": "<lint_cmd from Round 1>", "post_implement": "<test_cmd from Round 1>" } }`

Use the actual `test_cmd` and `lint_cmd` values selected in Round 1 for these commands.

## Round 9: Continuation Behavior (Optional)

**Only run if user selected "Configure" in the Extended Config Gate.**

Increment STEP by 1 and output: **Step [STEP] of [TOTAL]** — Continuation Behavior

Use a SINGLE AskUserQuestion call with 3 questions:

```yaml
questions:
  - header: "Auto-detect"
    question: "Enable automatic session continuation detection?"
    options:
      - label: "Yes (Recommended)"
        description: "Auto-detect continuation prompts on session start"
      - label: "No"
        description: "Manual /ll:resume required"
    multiSelect: false

  - header: "Include"
    question: "What should continuation prompts include?"
    options:
      - label: "Todos"
        description: "Include pending todo list items"
      - label: "Git status"
        description: "Include current git status"
      - label: "Recent files"
        description: "Include recently modified files"
    multiSelect: true

  - header: "Expiry"
    question: "How long should continuation prompts remain valid?"
    options:
      - label: "24 hours (Recommended)"
        description: "Prompts expire after one day"
      - label: "48 hours"
        description: "Prompts expire after two days"
      - label: "No expiry (168 hours)"
        description: "Prompts remain valid for one week"
    multiSelect: false
```

**Configuration:** Only include `continuation` section if any value differs from schema defaults.

**Mapping:**
- "Yes (Recommended)" for auto-detect -> `auto_detect_on_session_start: true` (default, can omit)
- "No" for auto-detect -> `auto_detect_on_session_start: false`
- "24 hours" -> `prompt_expiry_hours: 24` (default, can omit)
- "48 hours" -> `prompt_expiry_hours: 48`
- "No expiry" -> `prompt_expiry_hours: 168`

## Round 10: Prompt Optimization (Optional)

**Only run if user selected "Configure" in the Extended Config Gate.**

Increment STEP by 1 and output: **Step [STEP] of [TOTAL]** — Prompt Optimization

Use a SINGLE AskUserQuestion call with 3 questions:

```yaml
questions:
  - header: "Optimize"
    question: "Enable automatic prompt optimization?"
    options:
      - label: "Yes (Recommended)"
        description: "Enhance prompts with codebase context"
      - label: "No"
        description: "Use prompts as-is"
    multiSelect: false

  - header: "Mode"
    question: "Optimization mode?"
    options:
      - label: "Quick (Recommended)"
        description: "Fast optimization using config patterns"
      - label: "Thorough"
        description: "Full codebase analysis via sub-agent"
    multiSelect: false

  - header: "Confirm"
    question: "Require confirmation before applying optimized prompts?"
    options:
      - label: "Yes (Recommended)"
        description: "Show optimized prompt for approval"
      - label: "No"
        description: "Apply optimization automatically"
    multiSelect: false
```

**Configuration:** Only include `prompt_optimization` section if any value differs from schema defaults.

## Round 11: Allowed Tools — ALWAYS RUNS

**CRITICAL**: You MUST execute this round. The wizard is NOT complete until you have asked the user about allowed tools.

Increment STEP by 1 and output: **Step [STEP] of [TOTAL]** — Allowed Tools

**First, detect existing settings files:**

```bash
SETTINGS_JSON_EXISTS=false
SETTINGS_LOCAL_EXISTS=false
[ -f ".claude/settings.json" ] && SETTINGS_JSON_EXISTS=true
[ -f ".claude/settings.local.json" ] && SETTINGS_LOCAL_EXISTS=true
```

**Build options based on detected files and present a SINGLE AskUserQuestion call:**

If **neither** file exists:

```yaml
questions:
  - header: "Allowed Tools"
    question: "Add ll- CLI commands to Claude Code's allowed tools list? (Recommended for agent workflows)"
    options:
      - label: "Yes, create settings.local.json (Recommended)"
        description: "Create .claude/settings.local.json with ll- command entries (gitignored by default)"
      - label: "Yes, create settings.json"
        description: "Create .claude/settings.json with ll- command entries (tracked in version control)"
      - label: "Skip"
        description: "Don't add allowed tools entries"
    multiSelect: false
```

If **settings.local.json** exists (whether or not settings.json also exists):

```yaml
questions:
  - header: "Allowed Tools"
    question: "Add ll- CLI commands to Claude Code's allowed tools list?"
    options:
      - label: "Yes, update settings.local.json (Recommended)"
        description: "Update .claude/settings.local.json with ll- command entries"
      - label: "Yes, update settings.json"
        description: "Update .claude/settings.json with ll- command entries"
      - label: "Skip"
        description: "Don't add allowed tools entries"
    multiSelect: false
```

If **only settings.json** exists:

```yaml
questions:
  - header: "Allowed Tools"
    question: "Add ll- CLI commands to Claude Code's allowed tools list?"
    options:
      - label: "Yes, update settings.json"
        description: "Update .claude/settings.json with ll- command entries"
      - label: "Yes, create settings.local.json (Recommended)"
        description: "Create .claude/settings.local.json with ll- command entries (gitignored by default)"
      - label: "Skip"
        description: "Don't add allowed tools entries"
    multiSelect: false
```

**Record the result** (chosen target file or "skip") — used by SKILL.md Step 10 to perform the actual merge.

## Round 12: CLAUDE.md Documentation — ALWAYS RUNS

**CRITICAL**: You MUST execute this round. The wizard is NOT complete until you have asked the user about CLAUDE.md documentation.

Increment STEP by 1 and output: **Step [STEP] of [TOTAL]** — CLAUDE.md Documentation

**First, detect existing CLAUDE.md files:**

```bash
CLAUDE_MD_EXISTS=false
CLAUDE_MD_PATH=""
[ -f ".claude/CLAUDE.md" ] && CLAUDE_MD_EXISTS=true && CLAUDE_MD_PATH=".claude/CLAUDE.md"
[ "$CLAUDE_MD_EXISTS" = false ] && [ -f "CLAUDE.md" ] && CLAUDE_MD_EXISTS=true && CLAUDE_MD_PATH="CLAUDE.md"
```

**Build options based on detected files and present a SINGLE AskUserQuestion call:**

If **`.claude/CLAUDE.md` or `CLAUDE.md` exists** (`CLAUDE_MD_EXISTS=true`):

```yaml
questions:
  - header: "CLAUDE.md Documentation"
    question: "Add ll- CLI command documentation to your project's CLAUDE.md?"
    options:
      - label: "Yes, append to existing CLAUDE.md (Recommended)"
        description: "Append a ## little-loops CLI Commands section to the existing file"
      - label: "Skip"
        description: "Don't modify CLAUDE.md"
    multiSelect: false
```

If **neither exists** (`CLAUDE_MD_EXISTS=false`):

```yaml
questions:
  - header: "CLAUDE.md Documentation"
    question: "Add ll- CLI command documentation to your project's CLAUDE.md? (Improves discoverability)"
    options:
      - label: "Yes, create .claude/CLAUDE.md (Recommended)"
        description: "Create .claude/CLAUDE.md with a minimal header and ## little-loops CLI Commands section"
      - label: "Skip"
        description: "Don't create a CLAUDE.md file"
    multiSelect: false
```

**Record the result** (`CLAUDE_MD_ANSWER`) — used by SKILL.md Step 11.5 to perform the actual file write/append.

---

## Interactive Mode Summary

**Total interaction rounds: 6–7 (7 only if parallel processing selected)**

| Round | Group | Questions | Conditions |
|-------|-------|-----------|------------|
| 1 | Core Settings | name, src_dir, test_cmd, lint_cmd | Always |
| 2 | Additional Config | format_cmd, scan_dirs, excludes (issues dir: silent) | Always |
| 3a | Core Features | features (multi-select: parallel, context_monitor, sync, confidence_gate, tdd_mode) | Always |
| 3b | Automation Features | **Silent** — sprint_management, fsm_loops, sequential_auto always enabled | Always (no prompt) |
| 5a | Advanced (dynamic) | worktree_files, parallel_workers | Only if "Parallel processing" selected in Round 3a |
| **6** | **Document Tracking** | **docs (auto-detect or custom categories)** | **Always** |
| 7 | Extended Config Gate | **Silent** — always skips; Rounds 8–10 never shown | Always (no prompt) |
| 8 | Project Advanced (optional) | test_dir, build_cmd, run_cmd, impl_hooks | Never shown (use /ll:configure) |
| 9 | Continuation (optional) | auto_detect, include, expiry | Never shown (use /ll:configure) |
| 10 | Prompt Optimization (optional) | enabled, mode, confirm | Never shown (use /ll:configure) |
| **11** | **Allowed Tools** | **target settings file (settings.local.json / settings.json / skip)** | **Always** |
| **12** | **CLAUDE.md Docs** | **add ll- CLI commands to CLAUDE.md (yes/skip)** | **Always in --interactive** |

**Key behavior**:
- Wait for each group's AskUserQuestion response before proceeding to the next
- Use the responses to build the final configuration
- Show detected defaults as the first/recommended option
- Allow "Other" for custom values (built-in to AskUserQuestion)
