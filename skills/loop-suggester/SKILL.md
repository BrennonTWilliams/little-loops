---
description: |
  Analyze user message history to suggest FSM loop configurations.
  Uses ll-messages output to identify repeated workflows and generate
  ready-to-use loop YAML files, bypassing the interactive /ll:create_loop wizard.

  Trigger keywords: "suggest loops", "loop from history", "automate workflow",
  "create loop from messages", "analyze messages for loops", "ll-messages loop",
  "suggest automation", "detect patterns for loops"
---

# Loop Suggester

Analyze user message history from `ll-messages` output to identify repeated workflows and suggest FSM loop configurations. This skill bypasses the interactive `/ll:create_loop` wizard by automatically detecting patterns and generating ready-to-use loop YAML.

## Arguments

$ARGUMENTS

## Input Resolution

| Scenario | Behavior |
|----------|----------|
| `$ARGUMENTS` provided | Treat as path to existing JSONL file from ll-messages |
| `$ARGUMENTS` empty | Run `ll-messages --include-response-context -n 200 --stdout` to extract recent messages |

**Important**: For best results, the JSONL should include response context (tool usage metadata). If running ll-messages manually, use:

```bash
ll-messages --include-response-context -n 200 -o messages.jsonl
```

## Analysis Process

Follow these steps to analyze messages and generate loop suggestions:

### Step 1: Load Messages

1. If `$ARGUMENTS` is provided, read the JSONL file
2. If empty, use Bash to run: `ll-messages --include-response-context -n 200 --stdout`
3. Parse each line as JSON, extracting:
   - `content`: The user's message text
   - `timestamp`: When the message was sent
   - `session_id`: Session identifier for grouping
   - `response_metadata.tools_used`: List of tools used in response (critical for pattern detection)
   - `response_metadata.files_modified`: Files that were changed

### Step 2: Build Tool Sequences

For each message with `response_metadata`:

1. Extract the `tools_used` array (e.g., `[{tool: "Bash", count: 2}, {tool: "Edit", count: 1}]`)
2. Create a normalized tool sequence: `["Bash", "Edit"]`
3. Group by session_id to identify within-session patterns
4. Track file types modified to understand domain (Python, JS, etc.)

### Step 3: Detect Loop-Worthy Patterns

Apply these detection rules:

#### Pattern: Check-Fix Cycle (→ Goal Paradigm)

Look for sequences where:
- Same check tool appears before AND after Edit/Write
- Pattern: `Bash(check) → Edit → Bash(check)`
- Common checks: `pytest`, `mypy`, `ruff`, `eslint`, `tsc`

**Confidence boost**: +0.2 if pattern appears in 5+ messages

#### Pattern: Multi-Constraint Sequence (→ Invariants Paradigm)

Look for sequences where:
- Multiple different checks run in succession
- All checks must pass before proceeding
- Pattern: `Bash(check1) → Bash(check2) → Bash(check3)`

**Indicators**:
- Different check tools in same session
- Consistent ordering across sessions

#### Pattern: Metric Tracking (→ Convergence Paradigm)

Look for:
- Numeric output comparison (test count, coverage %, error count)
- Repeated measurement with changes in between
- User messages mentioning "reduce", "increase", "target", "goal"

**Note**: This pattern is harder to detect from tool usage alone; rely on message content keywords.

#### Pattern: Step Sequence (→ Imperative Paradigm)

Look for:
- Consistent ordered steps without branching
- Pattern: `tool1 → tool2 → tool3 → check → repeat`
- Multi-stage builds or deployments

### Step 4: Map Patterns to Paradigms

| Pattern Type | Paradigm | Min Frequency | Confidence Base |
|--------------|----------|---------------|-----------------|
| Single check-fix-verify cycle | `goal` | 3 | 0.70 |
| Multiple sequential constraints | `invariants` | 3 | 0.65 |
| Metric improvement tracking | `convergence` | 2 | 0.55 |
| Ordered step sequence | `imperative` | 3 | 0.60 |

**Confidence adjustments**:
- +0.15 if pattern appears in 5+ messages
- +0.10 if pattern spans multiple sessions
- +0.05 if tool commands are identical (not just tool type)
- -0.10 if pattern has high variance in tool count

### Step 5: Generate Paradigm YAML

For each detected pattern, generate the appropriate paradigm configuration:

#### Goal Paradigm Template

```yaml
paradigm: goal
name: "[descriptive-name]"
goal: "[What the loop achieves]"
tools:
  - "[check command]"
  - "[fix command or /ll:manage_issue bug fix]"
max_iterations: [10-50 based on complexity]
evaluator:
  type: exit_code  # or output_contains for grep-like checks
```

#### Invariants Paradigm Template

```yaml
paradigm: invariants
name: "[descriptive-name]"
constraints:
  - name: "[constraint1]"
    check: "[check command]"
    fix: "[fix command]"
  - name: "[constraint2]"
    check: "[check command]"
    fix: "[fix command]"
maintain: false
max_iterations: [20-50]
```

#### Convergence Paradigm Template

```yaml
paradigm: convergence
name: "[descriptive-name]"
check: "[measurement command]"
toward: [target value]
tolerance: [acceptable range]
using: "[fix command]"
max_iterations: [30-50]
```

#### Imperative Paradigm Template

```yaml
paradigm: imperative
name: "[descriptive-name]"
steps:
  - "[step1 command]"
  - "[step2 command]"
  - "[step3 command]"
until:
  check: "[completion check]"
  passes: true
max_iterations: [20-50]
```

### Step 6: Calculate Confidence Score

```
confidence = base_confidence
           + (frequency_bonus if count >= 5)
           + (session_bonus if multi_session)
           + (consistency_bonus if identical_commands)
           - (variance_penalty if high_variance)

Clamp to range [0.0, 1.0]
```

### Step 7: Generate Output

Write suggestions to `.claude/loop-suggestions/suggestions-{timestamp}.yaml` using the output schema below.

## Output Schema

```yaml
analysis_metadata:
  source_file: "[path to JSONL or 'live extraction']"
  messages_analyzed: [count]
  analysis_timestamp: "[ISO 8601]"
  skill: loop-suggester
  version: "1.0"

summary:
  total_suggestions: [count]
  by_paradigm:
    goal: [count]
    invariants: [count]
    convergence: [count]
    imperative: [count]
  message_time_range:
    start: "[ISO 8601]"
    end: "[ISO 8601]"

suggestions:
  - id: "loop-001"
    name: "[suggested loop name]"
    paradigm: "[goal|invariants|convergence|imperative]"
    confidence: [0.0-1.0]
    rationale: |
      [2-3 sentences explaining why this pattern was detected,
      including message count and session information]
    source_patterns:
      - tool_sequence: ["tool1", "tool2", "tool3"]
        frequency: [count]
        sessions: [count]
    yaml_config: |
      [Complete, valid paradigm YAML ready for ll-loop]
    usage_instructions: |
      1. Save to .loops/[name].yaml
      2. Run: ll-loop validate [name]
      3. Test: ll-loop test [name]
      4. Execute: ll-loop run [name]
    customization_notes: |
      [Any suggestions for customizing paths, commands, or parameters]
```

## Example Suggestions

### Example 1: Goal Paradigm (Type Error Fix Loop)

```yaml
- id: "loop-001"
  name: "type-error-fixer"
  paradigm: goal
  confidence: 0.85
  rationale: |
    Detected 7 occurrences of: Bash(mypy) → Edit → Bash(mypy) cycle
    across 3 sessions. User repeatedly checks for type errors, fixes
    them manually, and re-checks until clean.
  source_patterns:
    - tool_sequence: ["Bash", "Edit", "Bash"]
      frequency: 7
      sessions: 3
  yaml_config: |
    paradigm: goal
    name: "type-error-fixer"
    goal: "No type errors in source"
    tools:
      - "mypy scripts/"
      - "/ll:manage_issue bug fix"
    max_iterations: 20
    evaluator:
      type: exit_code
  usage_instructions: |
    1. Save to .loops/type-error-fixer.yaml
    2. Run: ll-loop validate type-error-fixer
    3. Test: ll-loop test type-error-fixer
    4. Execute: ll-loop run type-error-fixer
  customization_notes: |
    - Adjust "mypy scripts/" path to match your source directory
    - Consider adding --ignore-missing-imports if using third-party libs
```

### Example 2: Invariants Paradigm (Quality Gate)

```yaml
- id: "loop-002"
  name: "quality-gate"
  paradigm: invariants
  confidence: 0.72
  rationale: |
    Detected sequential pattern: Bash(ruff) → Bash(mypy) → Bash(pytest)
    appearing in 4 sessions. User maintains multiple quality constraints
    in consistent order before considering work complete.
  source_patterns:
    - tool_sequence: ["Bash", "Bash", "Bash"]
      frequency: 4
      sessions: 4
  yaml_config: |
    paradigm: invariants
    name: "quality-gate"
    constraints:
      - name: "lint"
        check: "ruff check scripts/"
        fix: "ruff check --fix scripts/"
      - name: "types"
        check: "mypy scripts/"
        fix: "/ll:manage_issue bug fix"
      - name: "tests"
        check: "pytest scripts/tests/"
        fix: "/ll:manage_issue bug fix"
    maintain: false
    max_iterations: 30
  usage_instructions: |
    1. Save to .loops/quality-gate.yaml
    2. Run: ll-loop validate quality-gate
    3. Test: ll-loop test quality-gate
    4. Execute: ll-loop run quality-gate
  customization_notes: |
    - Adjust source paths for your project structure
    - Set maintain: true if you want continuous monitoring
    - Add additional constraints as needed (format, security, etc.)
```

### Example 3: Imperative Paradigm (Build-Test-Deploy)

```yaml
- id: "loop-003"
  name: "build-test-deploy"
  paradigm: imperative
  confidence: 0.68
  rationale: |
    Detected consistent 4-step sequence: build → test → lint → deploy
    appearing 5 times. User follows a specific release workflow.
  source_patterns:
    - tool_sequence: ["Bash", "Bash", "Bash", "Bash"]
      frequency: 5
      sessions: 2
  yaml_config: |
    paradigm: imperative
    name: "build-test-deploy"
    steps:
      - "npm run build"
      - "npm test"
      - "npm run lint"
    until:
      check: "npm run deploy:check"
      passes: true
    max_iterations: 10
  usage_instructions: |
    1. Save to .loops/build-test-deploy.yaml
    2. Run: ll-loop validate build-test-deploy
    3. Test: ll-loop test build-test-deploy
    4. Execute: ll-loop run build-test-deploy
  customization_notes: |
    - Replace npm commands with your project's equivalents
    - The until.check should verify deployment readiness
```

## Guidelines

### When to Suggest Loops

- **DO** suggest when pattern appears 3+ times
- **DO** suggest when pattern spans multiple sessions (indicates habitual workflow)
- **DO** prefer simpler paradigms (`goal` over `invariants` when both fit)
- **DO** include realistic confidence scores (rarely above 0.9)

### When NOT to Suggest Loops

- **DON'T** suggest for patterns appearing fewer than 3 times
- **DON'T** suggest for highly variable tool sequences
- **DON'T** suggest for one-time complex tasks (even if many tools used)
- **DON'T** suggest if no clear exit condition exists

### Customization Notes

Always include customization notes that mention:
- Path adjustments for different project structures
- Tool alternatives (ruff vs black, pytest vs unittest)
- Optional parameters users might want to change
- Warnings about project-specific assumptions

## Limitations

1. **Tool patterns only**: Cannot detect semantic intent, only tool usage sequences
2. **No response content**: Does not analyze Claude's responses, only user messages and tool metadata
3. **Heuristic confidence**: Confidence scores are rule-based estimates, not probabilistic
4. **Requires response context**: Works best with `--include-response-context` flag; without it, only message text is available
5. **May over-suggest**: Complex debugging sessions may look like patterns; use judgment when reviewing

## Comparison with /ll:create_loop

| Aspect | /ll:create_loop | /ll:loop-suggester |
|--------|-----------------|-------------------|
| Input | Interactive questions | Message history analysis |
| Output | Single loop | Multiple suggestions |
| Paradigm selection | User chooses | Auto-detected |
| Customization | During creation | Post-suggestion |
| Best for | Known automation needs | Discovering automation opportunities |

Use `/ll:create_loop` when you know what loop you want. Use `/ll:loop-suggester` when you want to discover what loops might help based on your actual usage patterns.

## Workflow Integration

This skill integrates with the existing workflow analysis pipeline:

1. **ll-messages** extracts user message history
2. **loop-suggester** (this skill) analyzes for loop patterns
3. **ll-loop validate** verifies generated YAML
4. **ll-loop run** executes the loop

Alternatively, use alongside `/ll:analyze-workflows` for comprehensive automation discovery:
- `/ll:analyze-workflows` finds general automation opportunities (commands, hooks, scripts)
- `/ll:loop-suggester` specifically finds FSM loop patterns

## Output Location

Suggestions are written to:
```
.claude/loop-suggestions/suggestions-YYYYMMDD-HHMMSS.yaml
```

Create this directory if it doesn't exist.
