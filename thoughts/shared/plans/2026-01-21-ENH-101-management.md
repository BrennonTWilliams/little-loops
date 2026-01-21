# ENH-101: Add Advanced Setup Rounds to Init Wizard - Implementation Plan

## Issue Reference
- **File**: `.issues/enhancements/P3-ENH-101-init-wizard-advanced-setup-rounds.md`
- **Type**: enhancement
- **Priority**: P3
- **Action**: improve

## Current State Analysis

The init wizard in `commands/init.md` currently has 5 rounds:

| Round | Group | Questions |
|-------|-------|-----------|
| 1 | Core Settings | name, src_dir, test_cmd, lint_cmd |
| 2 | Additional Config | format_cmd, issues, scan_dirs, excludes |
| 3 | Features | features (multi-select: parallel, context_monitor) |
| 4 | Advanced (dynamic) | issues_path?, worktree_files?, threshold? |
| 5 | Document Tracking | docs |

### Key Discoveries
- Wizard structure at `commands/init.md:192-526`
- Round summary table at `commands/init.md:501-526`
- Config schema defines `continuation` at `config-schema.json:369-414`
- Config schema defines `prompt_optimization` at `config-schema.json:334-368`
- Config schema defines `project.test_dir` at `config-schema.json:25-29`
- Config schema defines `project.build_cmd` at `config-schema.json:50-54`

## Desired End State

Add optional advanced rounds (6-8) after Round 5, gated by a single question asking if the user wants to configure advanced settings. The rounds cover:

- **Round 6**: Project Advanced (test_dir, build_cmd)
- **Round 7**: Continuation Behavior (auto_detect, include items, expiry)
- **Round 8**: Prompt Optimization (enabled, mode, confirm)

### How to Verify
- Run `/ll:init --interactive` and verify new rounds appear when "Configure" is selected
- Verify config output includes new fields when non-default values are selected
- Verify rounds are skipped when "Skip (Recommended)" is selected

## What We're NOT Doing

- Not adding `--advanced` flag to jump directly to advanced rounds (can be deferred)
- Not refactoring existing rounds
- Not changing default behaviors

## Solution Approach

1. Add an entry point question after Round 5 to gate advanced rounds
2. Add Rounds 6-8 following existing patterns
3. Update the summary table to reflect new rounds
4. Add configuration mapping instructions for new fields
5. Update display summary to show new configuration sections

## Implementation Phases

### Phase 1: Add Advanced Rounds Entry Gate

#### Overview
Add a question after Round 5 asking if user wants to configure advanced settings.

#### Changes Required

**File**: `commands/init.md`
**Location**: After Step 5e (Document Tracking), before the "Interactive Mode Summary" section (around line 499)

Add new section:

```markdown
#### Step 5f: Advanced Settings Gate

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

If "Skip (Recommended)" is selected, proceed directly to step 6 (Display Summary).
If "Configure" is selected, continue to Rounds 6-8.
```

#### Success Criteria

**Automated Verification**:
- [ ] Lint passes: `ruff check commands/`

**Manual Verification**:
- [ ] Entry gate question appears after Round 5 in interactive mode

---

### Phase 2: Add Round 6 - Project Advanced

#### Overview
Add Round 6 for project.test_dir and project.build_cmd configuration.

#### Changes Required

**File**: `commands/init.md`
**Location**: After Step 5f

Add new section:

```markdown
#### Step 5g: Project Advanced (Round 6)

**Only run if user selected "Configure" in the Advanced Settings Gate.**

Use a SINGLE AskUserQuestion call with 2 questions:

```yaml
questions:
  - header: "Test Dir"
    question: "Do you have a separate test directory?"
    options:
      - label: "tests/"
        description: "Standard tests/ directory (Recommended)"
      - label: "test/"
        description: "Alternative test/ directory"
      - label: "Same as src"
        description: "Tests are alongside source files"
    multiSelect: false

  - header: "Build Cmd"
    question: "Do you have a build command?"
    options:
      - label: "Skip"
        description: "No build step needed (Recommended for scripting languages)"
      - label: "npm run build"
        description: "Node.js build"
      - label: "python -m build"
        description: "Python package build"
      - label: "make build"
        description: "Makefile build"
    multiSelect: false
```

**Populate options based on detected project type:**
- Python: tests/, test/, Same as src | Skip, python -m build, make build
- Node.js: tests/, test/, __tests__/ | npm run build, yarn build, Skip
- Go: *_test.go files in same dir | go build, make build, Skip
- Rust: tests/ | cargo build, cargo build --release, Skip
- Java: src/test/java/ | mvn package, gradle build, Skip
- .NET: tests/ | dotnet build, dotnet publish, Skip

**Configuration from Round 6 responses:**

If user selected a non-default test directory, add to configuration:
```json
{
  "project": {
    "test_dir": "<selected directory>"
  }
}
```

If user selected a build command (not "Skip"), add to configuration:
```json
{
  "project": {
    "build_cmd": "<selected command>"
  }
}
```

**Notes:**
- Only include `test_dir` if different from the schema default ("tests")
- Only include `build_cmd` if user selected a command (not "Skip")
```

#### Success Criteria

**Automated Verification**:
- [ ] Lint passes: `ruff check commands/`

**Manual Verification**:
- [ ] Round 6 appears when "Configure" is selected at the gate
- [ ] Selected values appear in config output

---

### Phase 3: Add Round 7 - Continuation Behavior

#### Overview
Add Round 7 for continuation settings.

#### Changes Required

**File**: `commands/init.md`
**Location**: After Step 5g

Add new section:

```markdown
#### Step 5h: Continuation Behavior (Round 7)

**Only run if user selected "Configure" in the Advanced Settings Gate.**

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

**Configuration from Round 7 responses:**

If continuation settings differ from defaults, add to configuration:
```json
{
  "continuation": {
    "auto_detect_on_session_start": true,
    "include_todos": true,
    "include_git_status": true,
    "include_recent_files": true,
    "prompt_expiry_hours": 24
  }
}
```

**Mapping:**
- "Yes (Recommended)" for auto-detect → `auto_detect_on_session_start: true` (default, can omit)
- "No" for auto-detect → `auto_detect_on_session_start: false`
- "Todos" selected → `include_todos: true` (default)
- "Git status" selected → `include_git_status: true` (default)
- "Recent files" selected → `include_recent_files: true` (default)
- "24 hours" → `prompt_expiry_hours: 24` (default, can omit)
- "48 hours" → `prompt_expiry_hours: 48`
- "No expiry" → `prompt_expiry_hours: 168`

**Notes:**
- Only include `continuation` section if any value differs from schema defaults
- By default, all three include options are true, so only include if user deselects any
```

#### Success Criteria

**Automated Verification**:
- [ ] Lint passes: `ruff check commands/`

**Manual Verification**:
- [ ] Round 7 appears when "Configure" is selected at the gate
- [ ] Multi-select works for "Include" question
- [ ] Selected values appear in config output

---

### Phase 4: Add Round 8 - Prompt Optimization

#### Overview
Add Round 8 for prompt optimization settings.

#### Changes Required

**File**: `commands/init.md`
**Location**: After Step 5h

Add new section:

```markdown
#### Step 5i: Prompt Optimization (Round 8)

**Only run if user selected "Configure" in the Advanced Settings Gate.**

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

**Configuration from Round 8 responses:**

If prompt optimization settings differ from defaults, add to configuration:
```json
{
  "prompt_optimization": {
    "enabled": true,
    "mode": "quick",
    "confirm": true
  }
}
```

**Mapping:**
- "Yes (Recommended)" for enabled → `enabled: true` (default, can omit)
- "No" for enabled → `enabled: false`
- "Quick (Recommended)" → `mode: "quick"` (default, can omit)
- "Thorough" → `mode: "thorough"`
- "Yes (Recommended)" for confirm → `confirm: true` (default, can omit)
- "No" for confirm → `confirm: false`

**Notes:**
- Only include `prompt_optimization` section if any value differs from schema defaults
- If user selects "No" for enabled, skip mode and confirm questions (use defaults)
```

#### Success Criteria

**Automated Verification**:
- [ ] Lint passes: `ruff check commands/`

**Manual Verification**:
- [ ] Round 8 appears when "Configure" is selected at the gate
- [ ] Selected values appear in config output

---

### Phase 5: Update Summary Table and Display

#### Overview
Update the Interactive Mode Summary table and display summary to reflect new rounds.

#### Changes Required

**File**: `commands/init.md`

**Change 1**: Update the summary table at line 501-526

Replace existing table with:

```markdown
### Interactive Mode Summary

**Total interaction rounds: 3-8**

| Round | Group | Questions |
|-------|-------|-----------|
| 1 | Core Settings | name, src_dir, test_cmd, lint_cmd |
| 2 | Additional Config | format_cmd, issues, scan_dirs, excludes |
| 3 | Features | features (multi-select: parallel, context_monitor) |
| 4 | Advanced (dynamic) | issues_path?, worktree_files?, threshold? |
| 5 | Document Tracking | docs |
| 5.5 | Advanced Gate | configure_advanced? |
| 6 | Project Advanced (optional) | test_dir, build_cmd |
| 7 | Continuation (optional) | auto_detect, include, expiry |
| 8 | Prompt Optimization (optional) | enabled, mode, confirm |

**Round 4 conditions:**
- **issues_path**: Only if "custom directory" selected in Round 2
- **worktree_files**: Only if "Parallel processing" selected in Round 3
- **threshold**: Only if "Context monitoring" selected in Round 3
- **If no conditions match**: Round 4 is skipped

**Rounds 6-8 conditions:**
- Only run if user selects "Configure" in Round 5.5 (Advanced Gate)
- If "Skip (Recommended)" is selected, rounds 6-8 are skipped entirely

**Round 5**: Always runs. User can choose "Use defaults", "Custom categories", or "Skip".
```

**Change 2**: Update display summary at line 527-566

Add new sections after DOCUMENTS:

```markdown
  [CONTINUATION]                          # Only show if configured (non-defaults)
  continuation.auto_detect_on_session_start: [true/false]
  continuation.include_todos: [true/false]
  continuation.include_git_status: [true/false]
  continuation.include_recent_files: [true/false]
  continuation.prompt_expiry_hours: [hours]

  [PROMPT OPTIMIZATION]                   # Only show if configured (non-defaults)
  prompt_optimization.enabled: [true/false]
  prompt_optimization.mode: [quick/thorough]
  prompt_optimization.confirm: [true/false]
```

**Change 3**: Update config file template at line 589-606

Add new sections to the config template:

```json
{
  "$schema": "...",
  "project": { ... },
  "issues": { ... },
  "scan": { ... },
  "parallel": { ... },
  "context_monitor": { ... },
  "documents": { ... },
  "continuation": { ... },
  "prompt_optimization": { ... }
}
```

#### Success Criteria

**Automated Verification**:
- [ ] Lint passes: `ruff check commands/`

**Manual Verification**:
- [ ] Summary table shows new rounds
- [ ] Display summary shows new sections when configured
- [ ] Config file includes new sections when non-default values selected

---

## Testing Strategy

### Manual Tests
1. Run `/ll:init --interactive` and select "Skip (Recommended)" at advanced gate - verify rounds 6-8 are skipped
2. Run `/ll:init --interactive` and select "Configure" - verify all new rounds appear
3. Verify multi-select works correctly in Round 7 (continuation includes)
4. Verify generated config only includes non-default values

### Edge Cases
- User selects all defaults in advanced rounds - config should have minimal entries
- User selects "No" for prompt optimization enabled - mode/confirm questions still asked but their values could be ignored

## References

- Original issue: `.issues/enhancements/P3-ENH-101-init-wizard-advanced-setup-rounds.md`
- Config schema: `config-schema.json:334-414` (prompt_optimization, continuation)
- Existing wizard: `commands/init.md:192-526`
- Similar pattern: `commands/init.md:351-400` (dynamic Round 4)
