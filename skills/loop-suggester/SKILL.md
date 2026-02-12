---
description: |
  Analyze user message history to suggest FSM loop configurations automatically. Uses ll-messages output to identify repeated workflows and generate ready-to-use loop YAML.

  Trigger keywords: "suggest loops", "loop from history", "automate workflow", "create loop from messages", "analyze messages for loops", "ll-messages loop", "suggest automation", "detect patterns for loops"
---

# Loop Suggester Skill

Detailed YAML templates and paradigm mapping guidance for the `/ll:loop-suggester` command. This skill provides the complete loop configuration templates referenced during suggestion generation.

## When to Activate

- Called by `/ll:loop-suggester` command during Step 5 (Generate Paradigm YAML)
- When a user asks about automating workflows discovered from message history
- When choosing the right loop paradigm for a detected pattern

## Arguments

$ARGUMENTS

Optional path to a JSONL file from `ll-messages`. If omitted, the command extracts recent messages automatically. See `/ll:loop-suggester` for the full analysis process.

## YAML Templates by Paradigm

### Goal Paradigm (Check-Fix Cycle)

Use when a single condition must be satisfied through iterative check-fix rounds.

```yaml
name: "{name}"
paradigm: goal
description: "{description}"

goal:
  check_cmd: "{command that returns exit 0 on success, non-zero on failure}"
  fix_prompt: |
    The check command failed with the above output.
    Analyze the errors and fix them.
  max_iterations: 10

options:
  stop_on_first_error: false
  working_dir: "."
```

**Detected from**: `Bash(check) → Edit → Bash(check)` sequences where the same check tool appears before and after edits.

**Common check commands**:
- `python -m pytest scripts/tests/ -x`
- `python -m mypy scripts/little_loops/`
- `ruff check scripts/`
- `npm test`
- `tsc --noEmit`

### Invariants Paradigm (Multi-Constraint)

Use when multiple independent constraints must all pass simultaneously.

```yaml
name: "{name}"
paradigm: invariants
description: "{description}"

invariants:
  checks:
    - name: "{check_1_name}"
      cmd: "{command_1}"
    - name: "{check_2_name}"
      cmd: "{command_2}"
    - name: "{check_3_name}"
      cmd: "{command_3}"
  fix_prompt: |
    One or more invariant checks failed. Review each failure above
    and fix the underlying issues without breaking passing checks.
  max_iterations: 15

options:
  stop_on_first_error: false
  working_dir: "."
```

**Detected from**: Multiple different check tools running in succession within the same session, with consistent ordering across sessions.

**Example invariant sets**:
- Lint + type-check + tests: `ruff check`, `mypy`, `pytest`
- Format + lint + build: `prettier --check`, `eslint`, `tsc`

### Convergence Paradigm (Metric Tracking)

Use when a numeric metric must reach a target value through iterative improvement.

```yaml
name: "{name}"
paradigm: convergence
description: "{description}"

convergence:
  metric_cmd: "{command that outputs a numeric value}"
  metric_pattern: "([0-9]+\\.?[0-9]*)"
  direction: "{higher_is_better|lower_is_better}"
  target: {target_value}
  threshold: {acceptable_delta}
  improve_prompt: |
    The current metric value is {current}. The target is {target}.
    Analyze the codebase and make changes to move the metric
    toward the target.
  max_iterations: 20

options:
  working_dir: "."
```

**Detected from**: Repeated numeric output comparisons with changes in between. User messages mentioning "reduce", "increase", "target", or "goal".

**Example metrics**:
- Test coverage: `pytest --cov --cov-report=term | grep TOTAL`
- Error count: `ruff check scripts/ 2>&1 | tail -1`
- Type coverage: `mypy scripts/ | grep -oP '\d+\.\d+%'`

### Imperative Paradigm (Step Sequence)

Use when a fixed sequence of steps must execute in order, optionally repeating.

```yaml
name: "{name}"
paradigm: imperative
description: "{description}"

imperative:
  steps:
    - name: "{step_1_name}"
      prompt: |
        {instruction for step 1}
    - name: "{step_2_name}"
      prompt: |
        {instruction for step 2}
    - name: "{step_3_name}"
      prompt: |
        {instruction for step 3}
  verify_cmd: "{optional final verification command}"
  max_iterations: 5

options:
  working_dir: "."
```

**Detected from**: Consistent ordered steps without branching — `tool1 → tool2 → tool3 → check → repeat`. Multi-stage builds or deployments.

**Example step sequences**:
- Generate → validate → deploy
- Scan → triage → fix → verify
- Extract → transform → load → check

## Pattern-to-Paradigm Mapping

Use this decision guide when a detected pattern could map to multiple paradigms:

| Signal | Paradigm | Why |
|--------|----------|-----|
| Single pass/fail check repeated | **goal** | One exit condition, simple cycle |
| Multiple independent checks must all pass | **invariants** | Fixing one check may break another |
| Numeric output being optimized | **convergence** | Needs target tracking and direction |
| Ordered steps, no branching | **imperative** | Sequence matters, not conditions |
| Single check + metric output | **goal** (not convergence) | If pass/fail is sufficient, prefer simpler paradigm |
| Two checks, one depends on other | **goal** with combined check | Avoid invariants if checks aren't independent |

**General rule**: prefer simpler paradigms. `goal` > `invariants` > `convergence` > `imperative` when multiple fit.

## Integration

- **`/ll:loop-suggester`**: The command that invokes this skill. Handles message loading, pattern detection, confidence scoring, and output generation. Defers to this skill for YAML template details.
- **`/ll:create_loop`**: Interactive loop creation wizard. Use when the user already knows what loop they want. Loop-suggester discovers opportunities; create_loop builds them.
- **`/ll:analyze-workflows`**: Broader workflow analysis pipeline. Loop-suggester focuses specifically on FSM loop opportunities from that analysis.

## Examples

| Detected Pattern | Paradigm | Template Key |
|-----------------|----------|--------------|
| User runs `pytest` → edits → runs `pytest` (7 times) | goal | `check_cmd: "python -m pytest ..."` |
| User runs `ruff check` then `mypy` then `pytest` each session | invariants | 3 checks in `invariants.checks` |
| User tracks test count going from 40 → 55 → 70 | convergence | `direction: higher_is_better, target: 100` |
| User follows scan → triage → fix → verify sequence | imperative | 4 entries in `imperative.steps` |
