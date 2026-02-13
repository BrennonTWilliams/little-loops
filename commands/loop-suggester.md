---
description: |
  Analyze user message history to suggest FSM loop configurations automatically. Uses ll-messages output to identify repeated workflows and generate ready-to-use loop YAML.

  Trigger keywords: "suggest loops", "loop from history", "automate workflow", "create loop from messages", "analyze messages for loops", "ll-messages loop", "suggest automation", "detect patterns for loops"
argument-hint: "[messages.jsonl]"
allowed-tools:
  - Read
  - Write
  - Bash(ll-messages:*)
arguments:
  - name: input
    description: Path to JSONL file from ll-messages (optional - extracts recent messages if omitted)
    required: false
---

# Loop Suggester

Analyze user message history from `ll-messages` output to identify repeated workflows and suggest FSM loop configurations. This command bypasses the interactive `/ll:create_loop` wizard by automatically detecting patterns and generating ready-to-use loop YAML.

## Arguments

$ARGUMENTS

- **input** (optional): Path to existing JSONL file from ll-messages
  - If provided, read and analyze that file
  - If omitted, run `ll-messages --include-response-context -n 200 --stdout` to extract recent messages

## Process

### Step 1: Load Messages

1. If `$ARGUMENTS` is provided, read the JSONL file at that path
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

For each detected pattern, generate the appropriate paradigm configuration. See the full skill documentation at `skills/loop-suggester/SKILL.md` for detailed YAML templates for each paradigm type (goal, invariants, convergence, imperative).

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

Write suggestions to `.claude/loop-suggestions/suggestions-{timestamp}.yaml` using this output schema:

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

suggestions:
  - id: "loop-001"
    name: "[suggested loop name]"
    paradigm: "[goal|invariants|convergence|imperative]"
    confidence: [0.0-1.0]
    rationale: "[2-3 sentences explaining detection]"
    yaml_config: |
      [Complete paradigm YAML]
    usage_instructions: |
      1. Save to {{config.loops.loops_dir}}/[name].yaml
      2. Run: ll-loop validate [name]
      3. Test: ll-loop test [name]
      4. Execute: ll-loop run [name]
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
- **DON'T** suggest for one-time complex tasks
- **DON'T** suggest if no clear exit condition exists

## Comparison with /ll:create_loop

| Aspect | /ll:create_loop | /ll:loop-suggester |
|--------|-----------------|-------------------|
| Input | Interactive questions | Message history analysis |
| Output | Single loop | Multiple suggestions |
| Paradigm selection | User chooses | Auto-detected |
| Best for | Known automation needs | Discovering automation opportunities |

Use `/ll:create_loop` when you know what loop you want. Use `/ll:loop-suggester` when you want to discover what loops might help based on your actual usage patterns.

## Examples

```bash
# Analyze recent messages (extracts last 200 with response context)
/ll:loop-suggester

# Analyze existing JSONL file
/ll:loop-suggester messages.jsonl

# Analyze custom extraction
/ll:loop-suggester ~/.claude/exports/session-analysis.jsonl
```

## See Also

- Full skill documentation: `skills/loop-suggester/SKILL.md`
- Create loops interactively: `/ll:create_loop`
- Workflow analysis: `/ll:analyze-workflows`
