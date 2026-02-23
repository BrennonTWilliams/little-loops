# Interactive Mode Wizard Rounds

If `--interactive` flag is set, you MUST use the `AskUserQuestion` tool to gather user preferences. Do NOT just display prompts as text - actually prompt the user interactively.

**IMPORTANT**: Group related questions together using AskUserQuestion's multi-question capability (up to 4 questions per call) to reduce interaction rounds.

## Progress Tracking Setup

Before starting the wizard, initialize these counters:

```
STEP = 0      # Current round number (incremented before each round)
TOTAL = 7     # Working total (mandatory rounds: 1, 2, 3a, 3b, 4, 6, 7)
              # Updated after Round 3b (adds 1-2 for Rounds 5a/5b)
              # Updated after Round 7 (adds 3 if "Configure" selected)
```

Before each round's `AskUserQuestion` call, increment STEP and output:

```
**Step [STEP] of [TOTAL]** — [Round Name]
```

Use `~[TOTAL]` (tilde prefix) for Rounds 1–4 to signal the total may grow as conditions are evaluated. Starting with Round 5, the total is known exactly.

## Round 1: Core Project Settings

Increment STEP to 1 and output: **Step 1 of ~7** — Core Settings

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

Populate options based on detected project type - see [presets.md](presets.md) for options by language.

## Round 2: Additional Configuration

Increment STEP to 2 and output: **Step 2 of ~7** — Additional Configuration

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

Use a SINGLE AskUserQuestion call with 4 questions:

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

  - header: "Issues"
    # If EXISTING_ISSUES_DIR is found:
    question: "Found existing '[EXISTING_ISSUES_DIR]/' directory. Use it for issue tracking?"
    # OR if no existing directory:
    # question: "Enable issue management features?"
    options:
      # If existing dir found:
      - label: "Yes, use [EXISTING_ISSUES_DIR]/"
        description: "Keep existing directory for issue tracking"
      # OR if no existing dir:
      # - label: "Yes, use .issues/"
      #   description: "Create .issues/ for tracking bugs, features, enhancements"
      - label: "Yes, custom directory"
        description: "Specify a custom directory name"
      - label: "Disable"
        description: "Skip issue management configuration"
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

Increment STEP to 3 and output: **Step 3 of ~7** — Core Features

Use a SINGLE AskUserQuestion call with the features multi-select:

```yaml
questions:
  - header: "Features"
    question: "Which advanced features do you want to enable?"
    options:
      - label: "Parallel processing"
        description: "Configure ll-parallel for concurrent issue processing with git worktrees"
      - label: "Context monitoring"
        description: "Auto-handoff reminders at 80% context usage (works in all modes)"
      - label: "GitHub sync"
        description: "Sync issues with GitHub Issues via /ll:sync-issues"
      - label: "Confidence gate"
        description: "Block manage-issue implementation when confidence score is below threshold"
    multiSelect: true
```

This round always runs and determines which follow-up questions are needed in Round 5.

## Round 3b: Automation Features Selection

Increment STEP to 4 and output: **Step 4 of ~7** — Automation Features

Use a SINGLE AskUserQuestion call with the automation features multi-select:

```yaml
questions:
  - header: "Automation"
    question: "Which automation tools do you want to configure settings for?"
    options:
      - label: "Sprint management"
        description: "Customize ll-sprint settings for wave-based issue processing"
      - label: "FSM loops"
        description: "Customize ll-loop settings for finite state machine automation"
      - label: "Sequential automation (ll-auto)"
        description: "Customize ll-auto settings for sequential automated processing"
    multiSelect: true
```

This round always runs. If any automation feature is selected, additional questions appear in Round 5.

**After Round 3b responses, recalculate TOTAL:**

```
Count active conditions for Round 5:
  ACTIVE = 0
  if Round 2 → "Yes, custom directory":  ACTIVE += 1
  if Round 3a → "Parallel processing":   ACTIVE += 1
  if Round 3a → "Context monitoring":    ACTIVE += 1
  if Round 3a → "GitHub sync":           ACTIVE += 2  # priority_labels + sync_completed questions
  if Round 3a → "Confidence gate":       ACTIVE += 1
  if Round 3b → "Sprint management":     ACTIVE += 1
  if Round 3b → "Sequential automation": ACTIVE += 1

  if ACTIVE >= 1: TOTAL += 1   # Round 5a will be shown
  if ACTIVE > 4:  TOTAL += 1   # Round 5b will be shown
```

## Round 4: Product Analysis

Increment STEP by 1 and output: **Step [STEP] of [TOTAL]** — Product Analysis

Use a SINGLE AskUserQuestion call:

```yaml
questions:
  - header: "Product"
    question: "Enable product-focused issue analysis? (Optional)"
    options:
      - label: "No, skip (Recommended)"
        description: "Technical analysis only - standard issue tracking"
      - label: "Yes, enable"
        description: "Add product goals, user impact, and business value to issues"
    multiSelect: false
```

**If "Yes, enable" selected:**

### Goals Discovery (Interactive Mode)

In interactive mode, offer auto-discovery from existing documentation:

```yaml
questions:
  - header: "Goals"
    question: "How would you like to set up product goals?"
    options:
      - label: "Auto-discover from docs (Recommended)"
        description: "Extract goals from README.md and other documentation"
      - label: "Start from template"
        description: "Create blank goals file to fill in manually"
    multiSelect: false
```

**If "Auto-discover from docs" selected:**

1. **Scan documentation files** (max 5 by default):
   - README.md (required - warn if missing)
   - CLAUDE.md or .claude/CLAUDE.md
   - docs/README.md
   - CONTRIBUTING.md
   - Any additional .md files in root

2. **Extract product context using LLM analysis**:
   Read the documentation files and extract:
   - Project purpose and vision
   - Target users/audience
   - Key goals or priorities mentioned
   - Explicit non-goals or scope limitations

3. **Generate `.claude/ll-goals.md`**:
   - Populate YAML frontmatter with extracted persona and priorities
   - Fill markdown sections with discovered content
   - Mark uncertain fields with `[NEEDS REVIEW]` placeholder

4. **Present findings for confirmation**:
   ```
   I analyzed your project documentation and extracted these product goals:

   Primary User: [Extracted persona name] - [Role description]

   Priorities I identified:
   1. [Priority 1 name]
   2. [Priority 2 name]

   Does this look correct?
   ```

   Use AskUserQuestion:
   ```yaml
   questions:
     - header: "Confirm"
       question: "I extracted these goals from your docs. Accept them?"
       options:
         - label: "Yes, looks good"
           description: "Save the extracted goals"
         - label: "No, let me edit"
           description: "Open the goals file for manual editing"
       multiSelect: false
   ```

5. **Warn if incomplete**:
   ```
   Product goals auto-generated from documentation.
   Review and update: .claude/ll-goals.md

   Extracted:
   - Primary persona: [Name]
   - Priorities: [N] identified
   - Pain points: Not found in docs (please add manually)
   ```

**If "Start from template" selected:**

1. Create `.claude/ll-goals.md` from the goals template. Read the template content from `templates/ll-goals-template.md` (relative to the little-loops plugin directory) and write it to `.claude/ll-goals.md` in the user's project.

### Goals Discovery (Non-Interactive Mode with --yes)

When `--yes` flag is set (non-interactive), automatically attempt goal discovery:

1. **Scan for README.md** - If missing, warn but continue
2. **Analyze documentation** using LLM to extract:
   - Project purpose
   - Target users
   - Key priorities
3. **Generate `.claude/ll-goals.md`** with extracted content
4. **Mark uncertain sections** with `[NEEDS REVIEW]`
5. **Display warning**:
   ```
   Product goals auto-generated from documentation.
   Review and update: .claude/ll-goals.md
   ```

**Configuration:**

Add to configuration:
```json
{
  "product": {
    "enabled": true,
    "goals_file": ".claude/ll-goals.md"
  }
}
```

**If "No, skip" selected:**
- Omit the `product` section entirely (disabled is the default)

**Configuration notes:**
- Only include `product` section if enabled
- `analyze_user_impact` and `analyze_business_value` default to `true` and can be omitted
- The goals file location can be customized via `goals_file` property
- `goals_discovery.max_files` controls how many docs to scan (default: 5)
- `goals_discovery.required_files` lists files that must exist (default: `["README.md"]`)

**After completing Round 4, proceed to Round 5 (Advanced Settings).**

## Round 5: Advanced Settings (Dynamic)

Build this round dynamically based on previous responses. **Skip entirely if no follow-up questions are needed.**

If Round 5a is presented, increment STEP by 1 and output: **Step [STEP] of [TOTAL]** — Advanced Settings
If Round 5b is presented, increment STEP by 1 and output: **Step [STEP] of [TOTAL]** — Advanced Settings (continued)

**Include questions based on these conditions (ordered list of 8):**

1. **issues_path** - If user selected "Yes, custom directory" in Round 2
2. **worktree_files** - If user selected "Parallel processing" in Round 3a
3. **threshold** - If user selected "Context monitoring" in Round 3a
4. **priority_labels** - If user selected "GitHub sync" in Round 3a
5. **sync_completed** - If user selected "GitHub sync" in Round 3a
6. **gate_threshold** - If user selected "Confidence gate" in Round 3a
7. **sprints_workers** - If user selected "Sprint management" in Round 3b
8. **auto_timeout** - If user selected "Sequential automation (ll-auto)" in Round 3b

If all conditions are false, skip this round entirely and proceed directly to Round 6 (Document Tracking).

**Overflow handling**: Before presenting, count the number of active conditions. `AskUserQuestion` supports a maximum of 4 questions per call. If the active count exceeds 4, split into two sub-rounds using separate `AskUserQuestion` calls:
- **Round 5a** — first 4 active questions (always presented when any condition is true)
- **Round 5b** — remaining active questions, positions 5–8 in the ordered list above (only presented when active count > 4)

### Round 5a: Advanced Settings (first batch)

Use a SINGLE AskUserQuestion call with up to 4 questions (the first 4 active conditions):

```yaml
questions:
  # ONLY include if user selected "Yes, custom directory" in Round 2:
  - header: "Issues Path"
    question: "What directory name should be used for issues?"
    options:
      - label: ".issues"
        description: "Hidden directory (recommended)"
      - label: "issues"
        description: "Visible directory"
      - label: ".tasks"
        description: "Alternative naming"
    multiSelect: false

  # ONLY include if user selected "Parallel processing" in Round 3a:
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

  # ONLY include if user selected "Context monitoring" in Round 3a:
  - header: "Threshold"
    question: "At what context usage percentage should auto-handoff trigger?"
    options:
      - label: "80%"
        description: "Default - balanced for most workloads"
      - label: "70%"
        description: "Conservative - earlier handoff, more headroom"
      - label: "90%"
        description: "Aggressive - maximize context before handoff"
    multiSelect: false

  # ONLY include if user selected "GitHub sync" in Round 3a:
  - header: "Priority Labels"
    question: "Add priority levels (P0-P5) as GitHub labels when syncing?"
    options:
      - label: "Yes (Recommended)"
        description: "Map P0-P5 to GitHub labels for filtering"
      - label: "No"
        description: "Don't add priority labels to GitHub Issues"
    multiSelect: false
```

### Round 5b: Advanced Settings (overflow batch)

**Only present this call when the total active condition count exceeds 4.** Collect the remaining active questions (positions 5–8 in the ordered list):

```yaml
questions:
  # ONLY include if user selected "GitHub sync" in Round 3a:
  - header: "Sync Completed"
    question: "Sync completed issues to GitHub (close them)?"
    options:
      - label: "No (Recommended)"
        description: "Only sync active issues"
      - label: "Yes"
        description: "Also close completed issues on GitHub"
    multiSelect: false

  # ONLY include if user selected "Confidence gate" in Round 3a:
  - header: "Gate Threshold"
    question: "What confidence score threshold should gate implementation?"
    options:
      - label: "85 (Recommended)"
        description: "Enforces solid readiness before implementation"
      - label: "70"
        description: "Allows most issues through"
      - label: "95"
        description: "Strict; only near-perfect issues proceed"
    multiSelect: false

  # ONLY include if user selected "Sprint management" in Round 3b:
  - header: "Sprint Workers"
    question: "How many parallel workers should sprint waves use by default?"
    options:
      - label: "4 (Recommended)"
        description: "Balanced for most systems"
      - label: "2"
        description: "Conservative — fewer concurrent worktrees"
      - label: "6"
        description: "High parallelism"
      - label: "8"
        description: "Maximum parallelism"
    multiSelect: false

  # ONLY include if user selected "Sequential automation (ll-auto)" in Round 3b:
  - header: "Auto Timeout"
    question: "What timeout should ll-auto use per issue (seconds)?"
    options:
      - label: "3600 (Recommended)"
        description: "1 hour per issue — default"
      - label: "1800"
        description: "30 minutes — faster workflows"
      - label: "7200"
        description: "2 hours — complex or long-running issues"
    multiSelect: false
```

**Configuration from Round 5 responses:**

If parallel is enabled and user selected files:
```json
{ "parallel": { "worktree_copy_files": ["<selected files>"] } }
```

If context monitoring is enabled:
```json
{ "context_monitor": { "enabled": true, "auto_handoff_threshold": 80 } }
```

If GitHub sync is enabled:
```json
{ "sync": { "enabled": true, "github": { "priority_labels": true, "sync_completed": false } } }
```

If confidence gate is enabled:
```json
{ "commands": { "confidence_gate": { "enabled": true, "threshold": 85 } } }
```

If sprint management is configured with non-default workers:
```json
{ "sprints": { "default_max_workers": 2 } }
```

If sequential automation is configured with non-default timeout:
```json
{ "automation": { "timeout_seconds": 1800 } }
```

**Notes:**
- Only include `auto_handoff_threshold` if user selected a non-default value (not 80%)
- Only include non-default values. If user selects exactly `[".env"]` (the default), the `worktree_copy_files` key can be omitted
- The `.claude/` directory is always copied automatically regardless of `worktree_copy_files` setting
- Only include `sync.github.priority_labels` if user selected "No" (true is the default)
- Only include `sync.github.sync_completed` if user selected "Yes" (false is the default)
- If both sync sub-settings are defaults, the `sync.github` object can be omitted (just include `sync.enabled: true`)
- Only include `commands.confidence_gate.threshold` if user selected a non-default value (not 85)
- If user selected 85 (the default threshold), just include `commands.confidence_gate.enabled: true`
- Only include `sprints.default_max_workers` if user selected a non-default value (not 4); if 4 is selected, omit the sprints section
- Only include `automation.timeout_seconds` if user selected a non-default value (not 3600); if 3600 is selected, omit the automation section
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
        "files": [".claude/ll-goals.md", "docs/ROADMAP.md"]
      }
    }
  }
}
```

If "Skip" selected or no documents found, omit the `documents` section entirely (disabled is the default).

**After completing Round 6, proceed to Round 7 (Extended Config Gate).**

## Round 7: Extended Configuration Gate

Increment STEP by 1 and output: **Step [STEP] of [TOTAL]** — Extended Configuration

Use a SINGLE AskUserQuestion call:

```yaml
questions:
  - header: "Advanced"
    question: "Would you like to configure additional advanced settings?"
    options:
      - label: "Skip (Recommended)"
        description: "Use sensible defaults for continuation, prompt optimization, and more"
      - label: "Configure"
        description: "Set up test directory, build command, continuation, and prompt optimization"
    multiSelect: false
```

If "Skip (Recommended)" is selected, proceed directly to the Display Summary step.
If "Configure" is selected, continue to Rounds 8-10.

**After Round 7 response, recalculate TOTAL:**

```
if user selected "Configure": TOTAL += 3   # Rounds 8, 9, 10 will be shown
```

## Round 8: Project Advanced (Optional)

**Only run if user selected "Configure" in the Extended Config Gate.**

Increment STEP by 1 and output: **Step [STEP] of [TOTAL]** — Project Advanced

Use a SINGLE AskUserQuestion call with 3 questions:

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
```

**Configuration:** Only include `test_dir`, `build_cmd`, `run_cmd` if non-default values selected.

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

---

## Interactive Mode Summary

**Total interaction rounds: 7-12**

| Round | Group | Questions | Conditions |
|-------|-------|-----------|------------|
| 1 | Core Settings | name, src_dir, test_cmd, lint_cmd | Always |
| 2 | Additional Config | format_cmd, issues, scan_dirs, excludes | Always |
| 3a | Core Features | features (multi-select: parallel, context_monitor, sync, confidence_gate) | Always |
| 3b | Automation Features | automation (multi-select: sprint_management, fsm_loops, sequential_auto) | Always |
| **4** | **Product Analysis** | **product (opt-in for product-focused analysis)** | **Always** |
| 5a | Advanced (dynamic, first batch) | issues_path?, worktree_files?, threshold?, priority_labels? | Conditional (≥1 active) |
| 5b | Advanced (dynamic, overflow) | sync_completed?, gate_threshold?, sprints_workers?, auto_timeout? | Conditional (>4 active total) |
| **6** | **Document Tracking** | **docs (auto-detect or custom categories)** | **Always** |
| 7 | Extended Config Gate | configure_extended? | Always |
| 8 | Project Advanced (optional) | test_dir, build_cmd | If Gate=Configure |
| 9 | Continuation (optional) | auto_detect, include, expiry | If Gate=Configure |
| 10 | Prompt Optimization (optional) | enabled, mode, confirm | If Gate=Configure |

**Key behavior**:
- Wait for each group's AskUserQuestion response before proceeding to the next
- Use the responses to build the final configuration
- Show detected defaults as the first/recommended option
- Allow "Other" for custom values (built-in to AskUserQuestion)
