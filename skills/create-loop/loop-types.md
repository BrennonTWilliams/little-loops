# Loop Type Questions (Step 2)

Based on the selected loop type, ask follow-up questions.

---

## Fix Until Clean Questions

If user selected "Fix until clean":

**Question Set 1** (single AskUserQuestion call):

```yaml
questions:
  - question: "What should the loop check and fix?"
    header: "Check target"
    multiSelect: true
    options:
      - label: "Type errors (mypy)"
        description: "Check: mypy src/, Fix: auto-fix type issues"
      - label: "Lint errors (ruff)"
        description: "Check: ruff check src/, Fix: ruff check --fix"
      - label: "Test failures (pytest)"
        description: "Check: pytest, Fix: fix failing tests"
      - label: "Custom check"
        description: "Specify your own check and fix commands"

  - question: "What's the maximum number of fix attempts?"
    header: "Max iterations"
    multiSelect: false
    options:
      - label: "10 (Recommended)"
        description: "Good for most fixes"
      - label: "20"
        description: "For more complex issues"
      - label: "50"
        description: "For large codebases"

> **Note**: The runtime default is 50 for all loop types. These options are suggested starting points to explicitly specify in your YAML based on your use case.
```

**If "Custom check" was selected**, ask for the commands:
- "What command checks for errors?" (free text via Other)
- "What command fixes the errors?" (free text via Other)

**Tool Evaluator Defaults:**

> **Note**: This table provides guidance for the AI during the interactive wizard flow. There is no separate code-based automatic tool detection - the AI uses this table to customize question wording based on the check command you provide. You should select the appropriate evaluator type for your specific tools.

When a check command is determined (from presets or custom input), use this table to recommend the appropriate evaluator:

| Tool Pattern | Recommended Evaluator | Rationale |
|--------------|----------------------|-----------|
| `pytest` | exit_code | Well-behaved: 0=all pass, 1=failures, 2+=errors |
| `mypy` | exit_code | Well-behaved: 0=no errors, 1=type errors |
| `ruff check` | exit_code | Well-behaved: 0=clean, 1=violations |
| `ruff format --check` | exit_code | Well-behaved: 0=formatted, 1=needs formatting |
| `npm test` | exit_code | Standard npm behavior |
| `npx tsc` | exit_code | Well-behaved: 0=no errors |
| `npx eslint` | exit_code | Well-behaved: 0=clean, 1=violations |
| `cargo test` | exit_code | Well-behaved: 0=all pass |
| `go test` | exit_code | Well-behaved: 0=all pass |
| `/ll:go-no-go --check` | exit_code | GO/NO-GO gate: 0=GO, 1=NO-GO — requires `--check` flag; always pair with `--auto` in loops |

**Detection Instructions:** (for the AI executing this wizard)

> These instructions guide the AI's behavior during the wizard flow to customize questions based on the detected tool pattern.

1. After the check command is determined, match against the tool patterns above (case-insensitive, partial match)
2. If a match is found, customize the evaluator question to show the matched tool's recommendation
3. Modify the first option label: "Exit code (Recommended for {tool})" where {tool} is the matched pattern
4. Update the description to include the rationale from the table
5. For custom commands with no pattern match, use the generic "Exit code (Recommended)"

**Evaluator Selection** (ask after check command is determined):

Use the Tool Evaluator Defaults table to customize this question based on the detected tool.

```yaml
# Example with mypy detected:
questions:
  - question: "How should success be determined for the mypy check?"
    header: "Evaluator"
    multiSelect: false
    options:
      - label: "Exit code (Recommended for mypy)"
        description: "Well-behaved: 0=no errors, 1=type errors"
      - label: "Output contains pattern"
        description: "Success if output contains specific text"
      - label: "Output is numeric"
        description: "Compare numeric output to threshold"
      - label: "AI interpretation"
        description: "Let Claude analyze the output"

# Generic template (no tool match):
questions:
  - question: "How should success be determined for the check command?"
    header: "Evaluator"
    multiSelect: false
    options:
      - label: "Exit code (Recommended)"
        description: "Success if command exits with code 0"
      - label: "Output contains pattern"
        description: "Success if output contains specific text"
      - label: "Output is numeric"
        description: "Compare numeric output to threshold"
      - label: "AI interpretation"
        description: "Let Claude analyze the output"
```

**If "Output contains pattern" was selected**, ask:
```yaml
questions:
  - question: "What pattern indicates success?"
    header: "Pattern"
    multiSelect: false
    options:
      - label: "Success"
        description: "Match the word 'Success' in output"
      - label: "0 errors"
        description: "Match '0 errors' in output"
      - label: "no issues found"
        description: "Match 'no issues found' in output"
      - label: "Custom pattern"
        description: "Specify your own pattern (via Other)"
```

**If "Output is numeric" was selected**, ask:
```yaml
questions:
  - question: "What numeric condition indicates success?"
    header: "Condition"
    multiSelect: false
    options:
      - label: "Equals 0"
        description: "Success if output equals 0"
      - label: "Less than threshold"
        description: "Success if output is below a value"
      - label: "Greater than threshold"
        description: "Success if output is above a value"
```

If "Less than threshold" or "Greater than threshold" selected, ask for target value via Other.

**Evaluator type mapping:**
- "Exit code" → `type: exit_code` (or omit, as this is the default)
- "Output contains pattern" → `type: output_contains, pattern: "<pattern>"`
- "Output is numeric" + "Equals 0" → `type: output_numeric, operator: eq, target: 0`
- "Output is numeric" + "Less than threshold" → `type: output_numeric, operator: lt, target: <value>`
- "Output is numeric" + "Greater than threshold" → `type: output_numeric, operator: gt, target: <value>`
- "AI interpretation" → `type: llm_structured`

**Generate Fix Until Clean FSM YAML:**

```yaml
name: "<loop-name>"
initial: evaluate
max_iterations: <selected-max>
# scope: ["src/"]          # Optional: declare paths for ll-parallel concurrency control
states:
  evaluate:
    action: "<check-command>"
    on_yes: done
    on_no: fix
    on_error: fix
    # Include evaluate block only if not using default (exit_code):
    # evaluate:             # Optional - omit for exit_code default
    #   type: "<output_contains|output_numeric|llm_structured>"
    #   pattern: "<pattern>"     # For output_contains only
    #   operator: "<eq|lt|gt>"   # For output_numeric only
    #   target: <number>         # For output_numeric only
  fix:
    action: "<fix-command>"
    # action_type: prompt   # Add if fix action is natural language (no leading /)
    next: evaluate
  done:
    terminal: true
```

**Example for "Type errors + Lint errors":**

```yaml
name: "fix-types-and-lint"
initial: evaluate
max_iterations: 10
states:
  evaluate:
    action: "mypy src/ && ruff check src/"
    on_yes: done
    on_no: fix
    on_error: fix
  fix:
    action: "/ll:check-code fix"
    next: evaluate
  done:
    terminal: true
```

---

## Maintain Constraints Questions

If user selected "Maintain constraints":

**Question Set 1:**

```yaml
questions:
  - question: "What constraints should always be true?"
    header: "Constraints"
    multiSelect: true
    options:
      - label: "Tests pass (pytest)"
        description: "Check: pytest, Fix: /ll:manage-issue bug fix"
      - label: "Types valid (mypy)"
        description: "Check: mypy src/, Fix: /ll:manage-issue bug fix"
      - label: "Lint clean (ruff)"
        description: "Check: ruff check src/, Fix: ruff check --fix src/"
      - label: "Build succeeds"
        description: "Check: npm run build (or equivalent)"
      - label: "Custom constraint"
        description: "Define your own check/fix pair"

  - question: "Should the loop restart after all constraints pass?"
    header: "Maintain mode"
    multiSelect: false
    options:
      - label: "No - stop when all pass"
        description: "Loop terminates when all constraints are satisfied"
      - label: "Yes - continuously maintain"
        description: "Restart from first constraint after all pass (daemon mode)"
```

**For each selected constraint, gather check/fix if custom. Otherwise use defaults:**

| Constraint | Check | Fix |
|------------|-------|-----|
| Tests pass | `pytest` | `/ll:manage-issue bug fix` |
| Types valid | `mypy src/` | `/ll:manage-issue bug fix` |
| Lint clean | `ruff check src/` | `ruff check --fix src/` |
| Build succeeds | Ask for build command | Ask for fix command |

**Evaluator Selection** (ask for each constraint if user wants custom evaluation):

Use the Tool Evaluator Defaults table (from Fix Until Clean section) to customize the evaluator question based on each constraint's check command. For example, if the constraint uses `pytest`, show "Exit code (Recommended for pytest)" with the rationale "Well-behaved: 0=all pass, 1=failures, 2+=errors".

```yaml
# Example with pytest constraint:
questions:
  - question: "How should success be determined for 'tests-pass' check?"
    header: "Evaluator"
    multiSelect: false
    options:
      - label: "Exit code (Recommended for pytest)"
        description: "Well-behaved: 0=all pass, 1=failures, 2+=errors"
      - label: "Output contains pattern"
        description: "Success if output contains specific text"
      - label: "Output is numeric"
        description: "Compare numeric output to threshold"
      - label: "AI interpretation"
        description: "Let Claude analyze the output"
```

Follow the same conditional flow as Fix Until Clean for pattern/numeric follow-ups.

**Generate Maintain Constraints FSM YAML:**

For each constraint `{name}` in order, generate a check/fix pair of states. The terminal state is `all_valid`. If `maintain: true`, the `all_valid` state loops back to the first check state instead of terminating.

```yaml
name: "<loop-name>"
initial: check_<name1>
max_iterations: 50
# scope: ["src/"]            # Optional: declare paths for ll-parallel concurrency control
states:
  check_<name1>:
    action: "<check-1-command>"
    on_yes: check_<name2>  # or all_valid if last constraint
    on_no: fix_<name1>
    # evaluate:               # Optional per-constraint
    #   type: "<output_contains|output_numeric|llm_structured>"
  fix_<name1>:
    action: "<fix-1-command>"
    next: check_<name1>
  check_<name2>:
    action: "<check-2-command>"
    on_yes: all_valid      # or next constraint
    on_no: fix_<name2>
  fix_<name2>:
    action: "<fix-2-command>"
    next: check_<name2>
  all_valid:
    terminal: true             # or next: check_<name1> if maintain: true
```

**Example for "Tests + Types + Lint":**

```yaml
name: "code-quality-guardian"
initial: check_tests
max_iterations: 50
states:
  check_tests:
    action: "pytest"
    on_yes: check_types
    on_no: fix_tests
  fix_tests:
    action: "/ll:manage-issue bug fix"
    next: check_tests
  check_types:
    action: "mypy src/"
    on_yes: check_lint
    on_no: fix_types
  fix_types:
    action: "/ll:manage-issue bug fix"
    next: check_types
  check_lint:
    action: "ruff check src/"
    on_yes: all_valid
    on_no: fix_lint
  fix_lint:
    action: "ruff check --fix src/"
    next: check_lint
  all_valid:
    terminal: true
```

---

## Drive a Metric Questions

If user selected "Drive a metric toward a target":

**Question Set 1:**

```yaml
questions:
  - question: "What type of metric do you want to track?"
    header: "Metric type"
    multiSelect: false
    options:
      - label: "Error count"
        description: "Count errors from a command (reduce toward 0)"
      - label: "Test coverage"
        description: "Coverage percentage (increase toward target)"
      - label: "Custom metric"
        description: "Any command that outputs a number"
```

**Based on metric type, gather details:**

For "Error count":
```yaml
questions:
  - question: "What errors should be counted?"
    header: "Error source"
    multiSelect: false
    options:
      - label: "Lint errors (ruff)"
        description: "Count: ruff check src/ --output-format=json | jq '.length'"
      - label: "Type errors (mypy)"
        description: "Count: mypy src/ --output-format=json | jq '.error_count'"
      - label: "Custom command"
        description: "Specify command that outputs a number"
```

**Question for fix action:**
```yaml
questions:
  - question: "What action should reduce the metric?"
    header: "Fix action"
    multiSelect: false
    options:
      - label: "/ll:check-code fix (Recommended)"
        description: "Auto-fix code issues"
      - label: "/ll:manage-issue bug fix"
        description: "Use issue management to fix bugs"
      - label: "Custom command"
        description: "Specify your own fix command"
```

**Generate Drive a Metric FSM YAML:**

```yaml
name: "<loop-name>"
initial: measure
max_iterations: 50
# scope: ["src/"]  # Optional: declare paths for ll-parallel concurrency control
states:
  measure:
    action: "<metric-command>"
    evaluate:
      type: convergence
      toward: <target-value>
      tolerance: 0
    route:
      target: done
      progress: apply
      stall: done
  apply:
    action: "<fix-action>"
    next: measure
  done:
    terminal: true
```

**Example for "Reduce lint errors to 0":**

```yaml
name: "eliminate-lint-errors"
initial: measure
max_iterations: 50
states:
  measure:
    action: "ruff check src/ 2>&1 | grep -c 'error' || echo 0"
    evaluate:
      type: convergence
      toward: 0
      tolerance: 0
    route:
      target: done
      progress: apply
      stall: done
  apply:
    action: "/ll:check-code fix"
    next: measure
  done:
    terminal: true
```

---

## Run a Sequence Questions

If user selected "Run a sequence of steps":

**Question Set 1:**

```yaml
questions:
  - question: "What steps should run in sequence?"
    header: "Steps"
    multiSelect: true
    options:
      - label: "Check types (mypy)"
        description: "Run type checking"
      - label: "Check lint (ruff)"
        description: "Run linting"
      - label: "Run tests (pytest)"
        description: "Execute test suite"
      - label: "Fix issues"
        description: "Apply automatic fixes"
      - label: "Custom step"
        description: "Add your own command"

  - question: "When should the loop stop?"
    header: "Exit condition"
    multiSelect: false
    options:
      - label: "All checks pass"
        description: "Stop when mypy && ruff && pytest all succeed"
      - label: "Tests pass"
        description: "Stop when pytest succeeds"
      - label: "Custom condition"
        description: "Specify your own exit check"
```

**Evaluator Selection** (ask for the exit condition check):

Use the Tool Evaluator Defaults table (from Fix Until Clean section) to customize the evaluator question based on the exit condition check command. For compound commands (e.g., "mypy && ruff && pytest"), show "Exit code (Recommended)" since multiple tools are being combined.

```yaml
# Example with "Tests pass" exit condition (pytest):
questions:
  - question: "How should success be determined for the exit condition?"
    header: "Evaluator"
    multiSelect: false
    options:
      - label: "Exit code (Recommended for pytest)"
        description: "Well-behaved: 0=all pass, 1=failures, 2+=errors"
      - label: "Output contains pattern"
        description: "Success if output contains specific text"
      - label: "Output is numeric"
        description: "Compare numeric output to threshold"
      - label: "AI interpretation"
        description: "Let Claude analyze the output"
```

Follow the same conditional flow as Fix Until Clean for pattern/numeric follow-ups.

**Generate Run a Sequence FSM YAML:**

```yaml
name: "<loop-name>"
initial: step_0
max_iterations: 50
backoff: 2
# scope: ["src/"]            # Optional: declare paths for ll-parallel concurrency control
states:
  step_0:
    action: "<step-1>"
    next: step_1
  step_1:
    action: "<step-2>"
    next: step_2
  step_2:
    action: "<step-3>"
    next: check_done
  check_done:
    action: "<exit-condition-command>"
    on_yes: done
    on_no: step_0
    # evaluate:               # Optional for exit condition
    #   type: "<output_contains|output_numeric|llm_structured>"
    #   pattern: "<pattern>"  # For output_contains only
    #   operator: "<eq|lt|gt>" # For output_numeric only
    #   target: <number>      # For output_numeric only
  done:
    terminal: true
```

**Example for "Fix -> Test -> Check until clean":**

```yaml
name: "fix-test-check"
initial: step_0
max_iterations: 50
backoff: 2
states:
  step_0:
    action: "/ll:check-code fix"
    next: step_1
  step_1:
    action: "pytest"
    next: step_2
  step_2:
    action: "mypy src/"
    next: check_done
  check_done:
    action: "mypy src/ && ruff check src/ && pytest"
    on_yes: done
    on_no: step_0
  done:
    terminal: true
```

---

## Harness Questions

If user selected "Harness a skill or prompt":

### Step H1: Discover Available Skills

Before asking questions, scan the skills directory:

Use the Glob tool with pattern `skills/*/SKILL.md` to list available skills.

For each skill found, read its `SKILL.md` to extract the first line of the `description:` frontmatter field.

**Question H1** (single AskUserQuestion call):

```yaml
questions:
  - question: "What do you want to harness?"
    header: "Target"
    multiSelect: false
    options:
      - label: "<skill-name>"
        description: "<skill description from SKILL.md frontmatter>"
      # ... one entry per discovered skill ...
      - label: "Custom prompt"
        description: "Enter a free-form natural language prompt to repeat"
```

**If "Custom prompt"**: Ask via Other input for the prompt text. Then ask two follow-up questions to derive the LLM-as-judge evaluation prompt:
- "What should be different in the output after the skill runs successfully?"
- "What would indicate the skill failed or made no progress?"

---

### Step H2: Work Item Discovery

```yaml
questions:
  - question: "How are work items discovered?"
    header: "Work items"
    multiSelect: false
    options:
      - label: "Single-shot (no item iteration)"
        description: "Run the skill/prompt once; no discover state needed"
      - label: "Active issues list (Recommended for issue skills)"
        description: "Discover via: ll-issues list --json"
      - label: "File glob pattern"
        description: "Find files matching a pattern (e.g. .issues/**/*.md)"
      - label: "Manual list"
        description: "Hard-code a list of items in the loop"
```

**If "File glob pattern"**: Ask for the pattern via Other.

**If "Manual list"**: Ask for comma-separated items via Other.

---

### Step H3: Evaluation Phases

Read `.ll/ll-config.json` to detect configured tool commands (`test_cmd`, `lint_cmd`, `type_cmd`). Present only phases that are relevant.

**Before presenting the question, show this observability context:**

> Each phase covers a different observational scope:
>
> | Phase | What it can observe | Latency |
> |-------|--------------------|---------|
> | Tool-based gates | Objective regressions — tests, types, lint | < 1s |
> | Stall detection | No-op iterations — detects prompt-based skills that make no file changes | < 1s |
> | Skill-based validation | **Real user behavior** — the only phase that exercises the feature as a real user would | 30–300s |
> | LLM-as-judge | Self-assessed output quality — the LLM evaluates its own output (bias-prone) | 3–10s |
> | Diff invariants | Runaway scope — catches unexpectedly large changes | < 1s |
>
> **Key distinction**: Skill-based validation is *external observation* (a skill acts as a real user); LLM-as-judge is *self-report* (the LLM evaluates its own output). They are not interchangeable — if you can configure a skill evaluator, it is the highest-fidelity gate available.

```yaml
questions:
  - question: "Which evaluation phases should be included?"
    header: "Evaluation phases"
    multiSelect: true
    options:
      - label: "Tool-based gates (Recommended)"
        description: "Shell checks using configured test/lint/type commands"
        # Show only if at least one of test_cmd, lint_cmd, type_cmd is configured
      - label: "Stall detection (Recommended for prompt-based skills)"
        description: "Detects no-op iterations — catches skills that return 'already done' without making file changes"
        # Pre-selected by default: all H1 choices produce prompt-based execution
      - label: "Skill-based validation (Recommended — only phase that validates real user behavior)"
        description: "A skill acts as a real user to verify the feature end-to-end — external observation, not self-report"
      - label: "LLM-as-judge"
        description: "Claude assesses its own output quality — useful for semantic correctness, but bias-prone (self-report)"
      - label: "Diff invariants"
        description: "Check git diff --stat to catch runaway or off-scope changes"
```

**If "Skill-based validation" is selected**, ask:
```
Which skill should act as evaluator?
  (Enter a skill name, e.g. "scrape-docs", or describe what to verify)
```

**If "LLM-as-judge" is selected**, ask (single AskUserQuestion with two questions, following the pattern in Step H4):
```
You selected LLM-as-judge evaluation. Help define the criteria:

What should be different in the output after the skill runs successfully?
> [user input]

What would indicate the skill failed or made no progress?
> [user input]
```

Pre-populate the questions with suggested wording derived from the selected skill's description (already read in Step H1) as option labels to guide the user. For custom prompts, apply the same two-question format (replacing the single "What does 'done' look like?" question).

**Default selection**: All available phases are pre-selected (Recommended). Skill-based validation is unselected by default — add it when a skill can verify something the other phases cannot observe. It is the highest-fidelity gate available: it catches issues that no static analysis or self-report can surface.

---

### Step H4: Iteration Budget

```yaml
questions:
  - question: "How many retries per item before giving up?"
    header: "Per-item retries"
    multiSelect: false
    options:
      - label: "3 retries (Recommended)"
        description: "Good balance for most skills"
      - label: "5 retries"
        description: "For complex or slow-converging skills"
      - label: "1 retry (strict)"
        description: "Fail fast; skip items that don't resolve immediately"

  - question: "What is the total iteration budget?"
    header: "Max iterations"
    multiSelect: false
    options:
      - label: "50 (Recommended)"
        description: "For up to ~15 items with 3 retries each"
      - label: "100"
        description: "For larger item sets"
      - label: "200"
        description: "For long-running batch operations"
```

**Auto-calculate total if omitted**: `max_iterations = estimated_items * per_item_retries * evaluation_states + buffer`

---

### Generate Harness FSM YAML

Use the answers from Steps H1–H4 to generate the YAML. Three structural variants (see Specialist Pipeline Questions below for Variant C):

#### Variant A: Single-Shot (no item discovery)

For "Single-shot" work item mode:

```yaml
name: "<loop-name>"
initial: execute
max_iterations: <per-item-retries>
states:
  execute:
    action: "<skill-or-prompt>"
    action_type: prompt
    timeout: 1500                # ≥1500s when prompt does multiple MCP calls + synthesis; default fallback (3600s) is bypassed by loop-level default_timeout:
    capture: execute_result      # captured as ${captured.execute_result.output}
    next: check_stall            # or check_concrete / check_semantic / check_invariants / done if stall detection omitted
  check_stall:                   # include if stall detection selected (recommended for prompt-based skills)
    action: "echo 'checking stall'"
    action_type: shell
    fragment: diff_stall_gate
    on_yes: check_concrete       # or check_semantic / check_invariants / done if later phases omitted
    on_no: done                  # stalled in single-shot mode → nothing more to do
    on_error: done
  check_concrete:                # include if tool-based gates selected
    action: "<highest-priority configured cmd: test_cmd > lint_cmd > type_cmd>"
    action_type: shell
    evaluate:
      type: exit_code
    on_yes: check_skill      # or check_semantic / check_invariants / done if later phases omitted
    on_no: execute
  check_skill:                   # include if skill-based evaluation selected
    action: "/ll:<skill-name> <task-description>"
    action_type: slash_command
    timeout: 300
    evaluate:
      type: llm_structured
      prompt: >
        Did the skill confirm the feature works as expected from a user perspective?
        Answer YES or NO with what it observed.
    on_yes: check_semantic   # or check_invariants / done if semantic omitted
    on_no: execute
  check_semantic:                # include if LLM-as-judge selected (can omit when check_skill covers quality)
    action: "echo 'Evaluating output quality'"
    action_type: shell
    evaluate:
      type: llm_structured
      source: "${captured.execute_result.output}"
      prompt: >
        Evaluate the previous action on these criteria:
        1. <success-criterion: what should be different after the skill runs successfully>
        2. Absence of failure signals: <failure-criterion: what would indicate the skill failed>
        Answer YES only if all criteria pass. Otherwise NO, stating which criterion failed.
    on_yes: check_invariants # or done if diff invariants omitted
    on_no: execute
  check_invariants:              # include if diff invariants selected
    action: "git diff --stat HEAD | wc -l | tr -d ' '"
    action_type: shell
    evaluate:
      type: output_numeric
      operator: lt
      target: 50
    on_yes: done
    on_no: execute
  done:
    terminal: true
```

#### Variant B: Multi-Item (discover → iterate)

For "Active issues list", "File glob pattern", or "Manual list" work item modes:

```yaml
name: "<loop-name>"
initial: discover
max_iterations: <max-iterations>
states:
  discover:
    action: "<discovery-command>"   # see Discovery Commands table below
    action_type: shell
    capture: "current_item"
    evaluate:
      type: exit_code
    on_yes: execute
    on_no: done
  execute:
    action: "<skill-or-prompt> ${captured.current_item.output}"
    action_type: prompt
    timeout: 1500                # ≥1500s when prompt does multiple MCP calls + synthesis; default fallback (3600s) is bypassed by loop-level default_timeout:
    capture: execute_result      # captured as ${captured.execute_result.output}
    max_retries: <per-item-retries>        # optional: skip stuck items automatically
    on_retry_exhausted: advance            # optional: route here when retries exceeded
    max_rate_limit_retries: 3              # optional: retry in place on HTTP 429 before exhaustion
    on_rate_limit_exhausted: advance       # optional: route here when rate-limit budget exhausted
    rate_limit_backoff_base_seconds: 30    # optional: base for short-tier exponential backoff + jitter (default 30)
    rate_limit_max_wait_seconds: 21600     # optional: total wall-clock budget for long-wait tier (default from commands.rate_limits.max_wait_seconds, 6h)
    rate_limit_long_wait_ladder: [300, 900, 1800, 3600]  # optional: long-wait ladder once short-tier exhausted (defaults from commands.rate_limits.long_wait_ladder)
    circuit_breaker_enabled: true                        # optional: coordinate rate-limit state across worktrees (default from commands.rate_limits.circuit_breaker_enabled, true)
    circuit_breaker_path: .loops/tmp/rate-limit-circuit.json  # optional: shared circuit state file (default from commands.rate_limits.circuit_breaker_path)
    next: check_stall            # or check_concrete / check_semantic / check_invariants / advance if stall detection omitted
  check_stall:                   # include if stall detection selected (recommended for prompt-based skills)
    action: "echo 'checking stall'"
    action_type: shell
    fragment: diff_stall_gate
    on_yes: check_concrete       # or check_semantic / check_invariants / advance if later phases omitted
    on_no: advance               # stalled → skip item, move to next
    on_error: check_concrete
  check_concrete:                # include if tool-based gates selected
    action: "<highest-priority configured cmd>"
    action_type: shell
    evaluate:
      type: exit_code
    on_yes: check_skill      # or check_semantic / check_invariants / advance if later phases omitted
    on_no: execute
  check_skill:                   # include if skill-based evaluation selected
    action: "/ll:<skill-name> <task-description>"
    action_type: slash_command
    timeout: 300
    evaluate:
      type: llm_structured
      prompt: >
        Did the skill confirm the feature works as expected from a user perspective?
        Answer YES or NO with what it observed.
    on_yes: check_semantic   # or check_invariants / advance if semantic omitted
    on_no: execute
  check_semantic:                # include if LLM-as-judge selected (can omit when check_skill covers quality)
    action: "echo 'Evaluating output quality'"
    action_type: shell
    evaluate:
      type: llm_structured
      source: "${captured.execute_result.output}"
      prompt: >
        Evaluate the previous action on these criteria:
        1. <success-criterion: what should be different after the skill runs successfully>
        2. Absence of failure signals: <failure-criterion: what would indicate the skill failed>
        Answer YES only if all criteria pass. Otherwise NO, stating which criterion failed.
    on_yes: check_invariants # or advance
    on_no: execute
  check_invariants:              # include if diff invariants selected
    action: "git diff --stat HEAD | wc -l | tr -d ' '"
    action_type: shell
    evaluate:
      type: output_numeric
      operator: lt
      target: 50
    on_yes: advance
    on_no: execute
  advance:
    action: "echo 'Item complete'"
    action_type: shell
    next: discover
  done:
    terminal: true
```

> **`max_retries` on harness states**: Use `max_retries` + `on_retry_exhausted` on any check state that routes back to `execute` on failure. This prevents a single bad item from exhausting the global `max_iterations` budget. See [reference.md](reference.md) for details.
>
> **`max_rate_limit_retries` on prompt states**: For prompt states that hit a rate-limited LLM upstream (especially under `ll-parallel`), pair `max_rate_limit_retries` with `on_rate_limit_exhausted` so 429s are retried in place with exponential backoff + jitter rather than surfaced as generic action failures. Override `rate_limit_backoff_base_seconds` (default `30`) upward when running wide parallelism — the jitter is load-bearing for avoiding thundering-herd retries. See [reference.md](reference.md) for details.

**Discovery Commands by work item mode:**

| Mode | Discovery Command |
|------|------------------|
| Active issues list | `ll-issues list --json \| python3 -c "import json,sys; issues=json.load(sys.stdin); print(issues[0]['id']) if issues else sys.exit(1)"` |
| File glob pattern | `find . -name '<pattern>' -not -path './.git/*' \| sort \| head -1` |
| Manual list | `python3 -c "import os; os.makedirs('.loops/tmp', exist_ok=True); items='<item1>,<item2>,...'.split(','); [open('.loops/tmp/harness-items.txt','w').write('\n'.join(items))]; print(items[0])"` (first-run seeding) |

**Tool-gate command priority** (use highest-priority configured command):
1. `test_cmd` (most comprehensive)
2. `lint_cmd` (fast feedback)
3. `type_cmd` (type safety)
4. If none configured: omit `check_concrete` state entirely

**Convergence defaults by action type:**

| Skill category | Suggested max_iterations | Per-item retries |
|----------------|--------------------------|------------------|
| Issue refinement/analysis | 200 | 3 |
| Code quality / fix | 50 | 5 |
| Documentation | 100 | 3 |
| Custom prompt | 50 | 3 |

---

**Stall Detection (native `diff_stall` evaluator)**

Use the `diff_stall` evaluator to automatically terminate retries when no code changes are being produced. Unlike `convergence` (which tracks numeric metrics), `diff_stall` works with any action type by comparing `git diff --stat` between iterations.

Add a `check_stall` state after the action that retries — if the working tree is unchanged for `max_stall` consecutive iterations, the loop skips to the next item instead of retrying indefinitely:

```yaml
# In a harness loop, add check_stall between execute and advance:
check_stall:
  action: "echo 'checking stall'"      # action output is ignored by diff_stall
  action_type: shell
  fragment: diff_stall_gate
  on_yes: advance    # progress detected — move on
  on_no: skip_item  # stalled — skip without exhausting max_iterations
```

**When to add stall detection:**
- The action is prompt-based (`action_type: prompt`) and may loop without making changes
- You observe a harness loop exhausting `max_iterations` without commits
- The skill being harnessed sometimes produces no output (e.g., "already done")

**YAML field reference:**

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `scope` | `list[str]` | *(entire repo)* | Paths to limit `git diff --stat` to |
| `max_stall` | `int` | `1` | Consecutive no-change iterations before `failure` verdict |

**Verdicts:** `success` (progress or below threshold), `failure` (stalled at max_stall), `error` (git unavailable)

---

**Partial DoD Satisfaction Threshold (`general-task` loops)**

By default the `general-task` loop requires 100% of all Definition of Done criteria to be checked before routing to `done`. For tasks where some criteria depend on human decisions or environment state (e.g., "Working tree is clean", "PR approved"), add `min_pass_rate` and `hard_criteria_tags` to `context:` to enable a two-tier gate:

```yaml
context:
  min_pass_rate: 0.95        # overall % of criteria that must be checked
  hard_criteria_tags: "hard"  # tag suffix marking mandatory criteria
```

In the DoD file, tag each criterion that must be technically verified with `[hard]`:

```markdown
## Verification Criteria
- [ ] Tests pass [hard]
- [ ] File exists at expected path [hard]
- [ ] Working tree is clean       ← soft (untagged); non-blocking when pass rate is met
```

The `count_done` shell gate applies the following logic:
- **Hard criteria** (tagged `[hard]`) — always blocking; the loop cannot reach `done` until all are `[x]`.
- **Soft criteria** (untagged) — only blocking when the overall pass rate (checked ÷ total) falls below `min_pass_rate`. Once the pass rate threshold is met, remaining soft criteria are logged as non-blocking.
- **`.total` routing field** — `total == 0` routes to `final_verify` (terminal gate); `total > 0` routes to `continue_work`.

Override `min_pass_rate` per run to require 100% satisfaction: `ll-loop run general-task --context min_pass_rate=1.0`. Loops that omit `min_pass_rate` from `context:` default to 0.95.

**Iteration-Cap Summary Hook (`on_max_iterations` — ENH-1631)**

When a `general-task` run exhausts its 100-iteration budget before all DoD criteria are satisfied, the `on_max_iterations: summarize_partial` hook fires. The `summarize_partial` state reads the DoD and plan artifacts, then writes a one-paragraph summary to `.loops/tmp/general-task-summary.md` covering: what was accomplished, which DoD criteria remain unmet, and recommended next actions. The loop then terminates with `terminated_by: max_iterations`.

This field is available on any loop YAML:

```yaml
max_iterations: 100
on_max_iterations: summarize_partial  # state to run once when cap fires
```

The named state runs **exactly once** (the iteration budget is not extended). Use it to write a handoff artifact so the next operator or session can pick up where the run left off without re-reading 100 iterations of JSONL. `/ll:audit-loop-run` surfaces runs with this hook as verdict `partial` (summary written).

---

**Example: Harness `refine-issue` over all active issues**

```yaml
name: "harness-refine-issue"
initial: discover
max_iterations: 200
timeout: 14400
states:
  discover:
    action: |
      ll-issues list --json | python3 -c "
      import json, sys
      issues = json.load(sys.stdin)
      if not issues:
          sys.exit(1)
      print(issues[0]['id'])
      "
    action_type: shell
    capture: "current_item"
    evaluate:
      type: exit_code
    on_yes: execute
    on_no: done
  execute:
    action: /ll:refine-issue ${captured.current_item.output} --auto
    action_type: prompt
    capture: execute_result
    next: check_concrete
  check_concrete:
    action: python -m pytest scripts/tests/ -q --tb=no
    action_type: shell
    evaluate:
      type: exit_code
    on_yes: check_semantic
    on_no: execute
  check_semantic:
    action: echo 'Evaluating refinement quality'
    action_type: shell
    evaluate:
      type: llm_structured
      source: "${captured.execute_result.output}"
      prompt: >
        Did the previous /ll:refine-issue action successfully refine the issue?
        Check that: the issue file was updated with new content, confidence scores
        were added or improved, and no errors occurred. Answer YES or NO.
    on_yes: check_invariants
    on_no: execute
  check_invariants:
    action: "git diff --stat HEAD | wc -l | tr -d ' '"
    action_type: shell
    evaluate:
      type: output_numeric
      operator: lt
      target: 50
    on_yes: advance
    on_no: execute
  advance:
    action: echo 'Issue refined'
    action_type: shell
    next: discover
  done:
    terminal: true

---

**Example: Gate-and-implement (go-no-go before each implementation)**

> **Critical**: Always pass `--check --auto` to `/ll:go-no-go` in FSM loops. Without `--check`, the skill always exits 0 regardless of the verdict — the FSM will route every issue to GO even when the judge says NO-GO. `--auto` suppresses interactive prompts and write-back.

```yaml
name: "gate-and-implement"
initial: discover
max_iterations: 100
states:
  discover:
    action: |
      ll-issues list --json | python3 -c "
      import json, sys
      issues = json.load(sys.stdin)
      if not issues:
          sys.exit(1)
      print(issues[0]['id'])
      "
    action_type: shell
    capture: "current_item"
    evaluate:
      type: exit_code
    on_yes: go_no_go
    on_no: done
  go_no_go:
    action: "/ll:go-no-go ${captured.current_item.output} --check --auto"
    action_type: slash_command
    evaluate:
      type: exit_code
    on_yes: implement   # exit 0 = GO verdict
    on_no: advance      # exit 1 = NO-GO verdict — skip without implementing
  implement:
    action: "/ll:manage-issue ${captured.current_item.output}"
    action_type: slash_command
    next: advance
  advance:
    action: "echo 'Item complete'"
    action_type: shell
    next: discover
  done:
    terminal: true
```

## Specialist Pipeline Questions

If user selected "Specialist role pipeline":

### Step S1: Active Roles

```yaml
questions:
  - question: "Which roles should be active in this specialist pipeline?"
    header: "Roles"
    multiSelect: true
    options:
      - label: "Plan (Recommended)"
        description: "Generate a structured plan for the task before any implementation."
      - label: "Research (Recommended)"
        description: "Investigate the codebase, docs, or web before implementing."
      - label: "Implement (Recommended)"
        description: "Apply the plan using research context. Core role -- always include this."
      - label: "Report (Recommended)"
        description: "Produce a summary of what was done after implementation completes."
```

Default: all four selected. The plan -> research -> implement -> report chain is the primary pipeline.

### Step S2: Target Task

```yaml
questions:
  - question: "How should the task be specified?"
    header: "Task input"
    multiSelect: false
    options:
      - label: "Specify at run time (Recommended)"
        description: "Pass the task description when running: ll-loop run my-loop"
      - label: "Hardcode a fixed task"
        description: "Embed the task description directly in the generated YAML."
```

If "Hardcode a fixed task": ask via Other for the task description text, then embed it in the plan, research, and implement state actions.

### Step S3: Planning Approach

```yaml
questions:
  - question: "How should the Plan role generate the plan?"
    header: "Planner"
    multiSelect: false
    options:
      - label: "/ll:iterate-plan (Recommended)"
        description: "Use the iterate-plan skill to produce a structured implementation plan."
      - label: "Custom prompt"
        description: "Write a free-form planning prompt directly in the state action."
      - label: "Skip planning"
        description: "Omit the plan state; implement role acts directly on the task."
```

### Step S4: Evaluation Phases

Read `.ll/ll-config.json` to detect `test_cmd`, `lint_cmd`, `type_cmd`. Present evaluation phase options (same as H3):

```yaml
questions:
  - question: "Which evaluation phases should guard the implementation?"
    header: "Evaluation"
    multiSelect: true
    options:
      - label: "Tool-based gates (Recommended)"
        description: "Run test_cmd / lint_cmd / type_cmd after implement. Show only if at least one command is configured."
      - label: "Stall detection (Recommended)"
        description: "Detect when implement makes no file changes. Catches no-op runs before any gate cost."
      - label: "LLM-as-judge"
        description: "Ask an LLM to evaluate whether the implementation meets the plan criteria. timeout: 1500 applies to long MCP calls."
      - label: "Diff invariants"
        description: "Gate on diff size to prevent runaway changes."
```

### Step S5: Iteration Budget

```yaml
questions:
  - question: "How many total loop iterations before giving up?"
    header: "Budget"
    multiSelect: false
    options:
      - label: "50 (Recommended)"
        description: "Suitable for most single-task specialist pipelines."
      - label: "100"
        description: "For longer multi-stage tasks."
      - label: "200"
        description: "For extended autonomous runs."
```

---

### Generate Specialist Pipeline YAML

Use the answers from Steps S1-S5 to generate the YAML. Route linearly: plan -> research -> implement -> [evaluation chain] -> report -> done.

```yaml
name: "<loop-name>"
initial: plan                        # or research/implement if earlier roles omitted in S1
max_iterations: <s5-budget>
timeout: 7200
import:
  - lib/common.yaml

states:
  plan:                              # include if "Plan" selected in S1; omit if "Skip planning" in S3
    action: "/ll:iterate-plan <task>" # or custom prompt from S3
    action_type: slash_command       # or prompt if custom prompt selected
    capture: plan
    next: research                   # or implement if Research omitted in S1

  # OPTIONAL: review_plan (HITL gate -- requires FEAT-1794 action_type: human_approval)
  # Uncomment once FEAT-1794 lands. Without it, use a prompt-gate workaround:
  #   see scripts/little_loops/loops/loop-router.yaml for the output_contains pattern.
  #
  # review_plan:
  #   action_type: human_approval
  #   prompt: "Review the plan: ${captured.plan.output}. Reply APPROVE to proceed."
  #   on_yes: research
  #   on_no: plan

  research:                          # include if "Research" selected in S1
    action: "Research the codebase and documentation relevant to the plan."
    action_type: prompt
    capture: research
    next: implement

  implement:
    action: "Implement the plan using the research findings."
    action_type: prompt
    capture: execute_result
    max_retries: 3
    on_retry_exhausted: report
    next: check_stall                # or check_concrete / check_semantic / report if stall detection omitted

  check_stall:                       # include if stall detection selected in S4
    action: "echo 'checking stall'"
    action_type: shell
    fragment: diff_stall_gate
    on_yes: check_concrete           # or check_semantic / check_invariants / report if concrete gate omitted
    on_no: report                    # no changes in specialist mode -> still produce report
    on_error: report

  check_concrete:                    # include if tool-based gates selected in S4
    action: "<test_cmd or lint_cmd from .ll/ll-config.json>"
    action_type: shell
    evaluate:
      type: exit_code
    on_yes: check_semantic           # or check_invariants / report if later phases omitted
    on_no: implement
    on_error: implement

  check_semantic:                    # include if LLM-as-judge selected in S4
    action: "echo 'Evaluating implementation quality'"
    action_type: shell
    evaluate:
      type: llm_structured
      source: "${captured.execute_result.output}"
      prompt: >
        Evaluate the implementation on these criteria:
        1. At least one file was modified and the task appears meaningfully complete
        2. Absence of failure signals: no errors, no incomplete output
        Answer YES only if all criteria pass. Otherwise NO.
    on_yes: check_invariants         # or report if diff invariants omitted
    on_no: implement
    on_partial: check_semantic

  check_invariants:                  # include if diff invariants selected in S4
    action: "git diff --stat HEAD | wc -l | tr -d ' '"
    action_type: shell
    evaluate:
      type: output_numeric
      operator: lt
      target: 50
    on_yes: report
    on_no: implement
    on_error: report

  report:                            # include if "Report" selected in S1
    action: >
      Produce a completion report summarizing: plan summary, research used,
      changes made, test results, and next steps.
    action_type: prompt
    next: done

  done:
    terminal: true
```

**Wiring notes:**
- If "Plan" is omitted: set `initial: research` (or `initial: implement` if Research also omitted)
- If "Research" is omitted: route `plan -> implement`
- All evaluation phases are optional; route each state `on_yes` to the next enabled phase or to `report`
- The `# OPTIONAL: review_plan` block must always appear as a commented-out example between `plan` and `research`

---

## Optimize a Harness (Meta-Loop) Questions

If user selected "Optimize a harness (meta-loop)":

### Step M1: Target Artifact(s)

```yaml
questions:
  - question: "What harness artifact(s) will this loop modify?"
    header: "Targets"
    multiSelect: true
    options:
      - label: "Loop YAML(s)"
        description: "Files under .loops/ or scripts/little_loops/loops/"
      - label: "Skill"
        description: "A skills/<name>/SKILL.md file"
      - label: "Agent"
        description: "An agents/<name>.md file"
      - label: "Command"
        description: "A commands/<name>.md file"
      - label: "Custom paths"
        description: "Specify exact file path(s) via Other"
```

Captured as the `targets` context variable (space-separated file paths).

---

### Step M2: Scorer Command (REQUIRED)

Ask for the scorer command. This field is **required** — the wizard refuses to proceed without it.

```yaml
questions:
  - question: "What scorer command produces a numeric quality signal? (required)"
    header: "Scorer"
    multiSelect: false
    options:
      - label: "./scripts/score.sh"
        description: "Custom scoring script"
      - label: "pytest scripts/tests/test_meta.py -q --tb=no"
        description: "Test suite as scorer (exit code + pass count)"
      - label: "python -m little_loops.bench.score"
        description: "Python bench entry point"
      - label: "Custom command"
        description: "Specify your own scorer command"
```

**Refusal guard**: If the user provides an empty value or skips this question, abort:
```
Error: scorer is required for meta-optimize loops.
  A numeric quality signal is needed to gate commits (convergence evaluation).
  Provide a command that exits 0 on success and prints a numeric score on the last line.
  Re-run /ll:create-loop and enter a scorer command to continue.
```

---

### Step M3: Score Target

```yaml
questions:
  - question: "What is the score target / early-stop threshold?"
    header: "Target score"
    multiSelect: false
    options:
      - label: "1.0 (Recommended)"
        description: "Never early-stop; only commit on improvement"
      - label: "0.9"
        description: "Stop once score reaches 90%"
      - label: "0.8"
        description: "Stop once score reaches 80%"
      - label: "Custom value"
        description: "Enter your own threshold (0.0–1.0)"
```

---

### Step M4: Tasks Directory

```yaml
questions:
  - question: "Where is the task / benchmark directory?"
    header: "Tasks dir"
    multiSelect: false
    options:
      - label: "scripts/tests/"
        description: "Project test suite as benchmark"
      - label: ".loops/tasks/"
        description: "Loop-specific task directory"
      - label: "Custom path"
        description: "Specify your own benchmark directory"
```

If the user provides a non-empty path, validate that it exists. If it does not exist, warn:
```
Warning: tasks_dir '<path>' does not exist. The scorer may fail on the first run.
```
Proceed anyway (do not abort).

---

### Step M5: Diagnose Action (REQUIRED)

```yaml
questions:
  - question: "What is the diagnose action? (required)"
    header: "Diagnose"
    multiSelect: false
    options:
      - label: "Read recent runs from .loops/runs/ and summarize failure modes"
        description: "Shell: cat recent run logs and identify what most needs improvement"
      - label: "Custom shell command"
        description: "A shell command that surfaces what is currently wrong with the artifact"
      - label: "Custom prompt"
        description: "A natural-language prompt that analyzes the artifact and identifies priorities"
```

**Diagnose action type**: Ask a follow-up to determine whether the diagnose action is `shell` or `prompt`.

Captured as the `diagnose_action` variable along with `diagnose_action_type` (`shell` or `prompt`).

---

### Generate YAML — meta-optimize

```yaml
name: <loop-name>
description: |
  <user-provided description>
initial: diagnose
max_iterations: 30
timeout: 7200
context:
  targets: "<user-provided>"
  tasks_dir: "<user-provided>"
  scorer: "<user-provided>"
  target_score: <user-provided>

states:
  diagnose:
    action_type: <shell|prompt>
    action: |
      <user-provided diagnose action>
    capture: diagnosis
    next: baseline

  baseline:
    action_type: shell
    action: "${context.scorer} ${context.tasks_dir}"
    capture: baseline_score
    evaluate:
      type: exit_code
    on_yes: propose
    on_no: done
    on_error: done

  propose:
    action_type: prompt
    timeout: 300
    action: |
      Current harness artifact: ${context.targets}
      Diagnosis from previous step: ${captured.diagnosis.output}
      Baseline score: ${captured.baseline_score.output}

      Propose ONE targeted edit to ${context.targets} that addresses the
      highest-priority issue identified in the diagnosis. Output the revised
      content only — no preamble, no markdown fences.
    capture: candidate
    next: apply

  apply:
    action_type: prompt
    timeout: 120
    action: |
      Apply this proposed change to ${context.targets}:
      ${captured.candidate.output}
      Confirm the change has been applied.
    next: score

  score:
    action_type: shell
    action: "${context.scorer} ${context.tasks_dir}"
    capture: new_score
    evaluate:
      type: exit_code
    on_yes: gate
    on_no: revert
    on_error: revert

  gate:
    action_type: shell
    action: |
      echo "${captured.new_score.output}" | tail -1 | tr -d '[:space:]'
    evaluate:
      type: convergence
      direction: maximize
      target: "${context.target_score}"
      previous: "${captured.baseline_score.output}"
      tolerance: 0.02
    route:
      target: commit
      progress: commit
      stall: revert
      error: revert

  commit:
    action_type: shell
    action: |
      git add ${context.targets}
      git commit -m "${loop.name}: iter ${state.iteration}, score ${captured.new_score.output}"
    next: diagnose

  revert:
    action_type: shell
    action: "git restore ${context.targets}"
    next: done

  done:
    terminal: true
```

Notable properties:
- **`diagnose` is the initial state** — implements SHOR §7.1 priority-identification before committing to an edit.
- **No `check_semantic`** — the non-LLM `convergence` gate is the sole success signal; the generated YAML satisfies ENH-1665 MR-1 (`_validate_meta_loop_evaluation`) by construction.
- **Standalone, not inherited** — no `from:` field; per EPIC-1663 design decision 3.
- **Re-enters at `diagnose` after a successful commit** — each iteration re-prioritizes against the new baseline.

---

### Worked Example — "optimize the docs-sync loop"

User answers:
- Targets: `.loops/docs-sync.yaml`
- Scorer: `pytest scripts/tests/test_docs_sync.py -q --tb=no`
- Target score: `1.0`
- Tasks dir: `scripts/tests/`
- Diagnose action (shell): `cat $(ls -t .loops/runs/docs-sync/*/run.log 2>/dev/null | head -3) 2>/dev/null || echo "No prior runs found."`

Generated loop name suggestion: `optimize-docs-sync`

The generated YAML passes `ll-loop validate` without `meta_self_eval_ok: true` because the `gate` state uses `type: convergence` which is in `NON_LLM_EVALUATOR_TYPES` (`scripts/little_loops/fsm/validation.py:76–94`).

---

## Sub-Loop Composition

Sub-loop composition uses the `loop:` state field to invoke other loop YAMLs as nested child FSMs. This is not a separate loop type in the wizard — it is an advanced state configuration that can be used in any manually authored loop YAML.

**When to use:**
- You have existing, well-tested loops and want to compose them into a higher-level workflow
- You want to avoid duplicating state logic across multiple loop files
- You need to sequence multiple sub-workflows with routing based on their outcomes

**Key fields:**
- `loop: "<name>"` — references `.loops/<name>.yaml` (mutually exclusive with `action`)
- `context_passthrough: true` — pass parent context/captures to child, merge child captures back
- `on_success` / `on_failure` — route based on child loop terminal outcome

**Example — Compose sub-loops into a pipeline:**
```yaml
name: "code-review-pipeline"
initial: fix_lint
max_iterations: 10
states:
  fix_lint:
    loop: lint-fix
    context_passthrough: true
    on_success: run_tests
    on_failure: diagnose_failure
  run_tests:
    loop: test-suite
    on_success: done
    on_failure: diagnose_failure
  diagnose_failure:
    action: "echo 'Sub-loop failed, needs manual attention'"
    action_type: shell
    next: failed
  failed:
    terminal: true
  done:
    terminal: true
```

> **Note**: Sub-loop states cannot be created through the interactive wizard. Author them directly in YAML. See [reference.md](reference.md) for the full `loop:` field specification.

---

## RL Loops

If user selected any of the three RL loop types, follow the steps below for that type.

---

### RL Bandit Questions

If user selected "RL: Bandit (explore vs exploit)":

#### Step R1 — Explore and Exploit Actions

Ask:

```yaml
questions:
  - question: "What shell command or prompt runs an exploration step (try a new option)?"
    header: "Explore action"
    multiSelect: false
    options:
      - label: "Custom shell command"
        description: "Run a shell command that implements exploration"
      - label: "Claude prompt"
        description: "Use a Claude prompt action_type"

  - question: "What shell command or prompt runs an exploitation step (use best known option)?"
    header: "Exploit action"
    multiSelect: false
    options:
      - label: "Custom shell command"
        description: "Run a shell command that implements exploitation"
      - label: "Claude prompt"
        description: "Use a Claude prompt action_type"
```

Both actions must print a numeric reward score between 0.0 and 1.0 as their last output line.

#### Step R2 — Reward Target

Ask:

```yaml
questions:
  - question: "What reward target should terminate the loop (0.0–1.0)?"
    header: "Reward target"
    multiSelect: false
    options:
      - label: "0.8 (Recommended)"
        description: "Stop when reward reaches 0.8"
      - label: "0.9"
        description: "High-quality threshold"
      - label: "0.7"
        description: "Good-enough threshold"
      - label: "Custom"
        description: "Specify your own value"
```

#### Step R3 — Iteration Budget

Ask:

```yaml
questions:
  - question: "What is the maximum number of rounds?"
    header: "Max iterations"
    multiSelect: false
    options:
      - label: "50 (Recommended)"
      - label: "100"
      - label: "20 (fast test)"
```

#### RL Bandit YAML Generation

Generate using these values:
- `explore_action` — shell command or prompt from Step R1
- `explore_action_type` — "shell" or "prompt"
- `exploit_action` — shell command or prompt from Step R1
- `exploit_action_type` — "shell" or "prompt"
- `reward_target` — float from Step R2 (e.g. 0.8)
- `max_iterations` — integer from Step R3

```yaml
name: <loop-name>
description: |
  Epsilon-greedy bandit loop toward reward target <reward_target>.
initial: explore
context:
  reward_target: <reward_target>
  epsilon: 0.1
states:
  explore:
    action: |
      <explore_action>
    action_type: <explore_action_type>
    capture: round_result
    next: reward
  exploit:
    action: |
      <exploit_action>
    action_type: <exploit_action_type>
    capture: round_result
    next: reward
  reward:
    action: |
      echo "${captured.round_result.output}" | tail -1 | tr -d '[:space:]'
    action_type: shell
    evaluate:
      type: convergence
      target: "${context.reward_target}"
      direction: maximize
      tolerance: 0.05
    route:
      target: done
      progress: exploit
      stall: explore
  done:
    terminal: true
max_iterations: <max_iterations>
```

---

### RL RLHF Questions

If user selected "RL: RLHF-style (generate → score → refine)":

#### Step H1 — Generation and Refinement Actions

Ask:

```yaml
questions:
  - question: "What command or prompt generates the initial candidate output?"
    header: "Generate action"
    multiSelect: false
    options:
      - label: "Claude prompt"
        description: "Use a Claude prompt to generate output"
      - label: "Custom shell command"
        description: "Run a shell command that produces output"

  - question: "What command or prompt refines the candidate given feedback?"
    header: "Refine action"
    multiSelect: false
    options:
      - label: "Claude prompt"
        description: "Use a Claude prompt with feedback context"
      - label: "Custom shell command"
        description: "Run a shell command that improves output"
```

#### Step H2 — Scoring Action and Quality Target

Ask:

```yaml
questions:
  - question: "What command scores the candidate output (must print integer 0–10 on last line)?"
    header: "Score action"
    multiSelect: false
    options:
      - label: "Claude prompt evaluation"
        description: "Use a Claude prompt to score quality"
      - label: "Custom shell command"
        description: "Run a deterministic scoring script"

  - question: "What minimum quality score (0–10) should terminate the loop?"
    header: "Quality target"
    multiSelect: false
    options:
      - label: "8 (Recommended)"
        description: "High quality threshold"
      - label: "7"
        description: "Good-enough threshold"
      - label: "9"
        description: "Near-perfect threshold"
```

#### Step H3 — Iteration Budget

Ask:

```yaml
questions:
  - question: "What is the maximum number of refinement rounds?"
    header: "Max iterations"
    multiSelect: false
    options:
      - label: "30 (Recommended)"
      - label: "50"
      - label: "10 (fast test)"
```

#### RL RLHF YAML Generation

Generate using these values:
- `generate_action` / `generate_action_type` — from Step H1
- `refine_action` / `refine_action_type` — from Step H1
- `score_action` / `score_action_type` — from Step H2
- `quality_target` — integer from Step H2 (e.g. 8)
- `max_iterations` — integer from Step H3

```yaml
name: <loop-name>
description: |
  RLHF-style generate-score-refine loop targeting quality score >= <quality_target>.
initial: generate
states:
  generate:
    action: |
      <generate_action>
    action_type: <generate_action_type>
    capture: candidate
    next: score
  score:
    action: |
      <score_action>
    action_type: <score_action_type>
    evaluate:
      type: output_numeric
      operator: ge
      target: <quality_target>
    on_yes: done
    on_no: refine
    on_error: done
  refine:
    action: |
      <refine_action>
    action_type: <refine_action_type>
    capture: candidate
    next: score
  done:
    terminal: true
max_iterations: <max_iterations>
```

---

### RL Policy Questions

If user selected "RL: Policy iteration (act → observe → improve)":

#### Step P1 — Act and Observe Actions

Ask:

```yaml
questions:
  - question: "What command executes the policy action in the environment?"
    header: "Act action"
    multiSelect: false
    options:
      - label: "Custom shell command"
        description: "Run a shell command that acts in the environment"
      - label: "Claude prompt"
        description: "Use a Claude prompt to decide and act"

  - question: "What command observes the environment outcome and prints reward (0.0–1.0) on last line?"
    header: "Observe action"
    multiSelect: false
    options:
      - label: "Custom shell command"
        description: "Run a shell command that measures environment state"
      - label: "Claude prompt"
        description: "Use a Claude prompt to interpret environment state"
```

#### Step P2 — Policy Improvement and Reward Target

Ask:

```yaml
questions:
  - question: "What command updates the policy based on the observed reward?"
    header: "Improve action"
    multiSelect: false
    options:
      - label: "Claude prompt"
        description: "Use a Claude prompt to refine the policy"
      - label: "Custom shell command"
        description: "Run a script that adjusts policy parameters"

  - question: "What reward target should terminate the loop (0.0–1.0)?"
    header: "Reward target"
    multiSelect: false
    options:
      - label: "0.85 (Recommended)"
      - label: "0.9"
      - label: "0.7"
      - label: "Custom"
```

#### Step P3 — Iteration Budget

Ask:

```yaml
questions:
  - question: "What is the maximum number of policy iterations?"
    header: "Max iterations"
    multiSelect: false
    options:
      - label: "100 (Recommended)"
      - label: "50"
      - label: "200"
```

#### RL Policy YAML Generation

Generate using these values:
- `act_action` / `act_action_type` — from Step P1
- `observe_action` / `observe_action_type` — from Step P1
- `improve_action` / `improve_action_type` — from Step P2
- `reward_target` — float from Step P2 (e.g. 0.85)
- `max_iterations` — integer from Step P3

```yaml
name: <loop-name>
description: |
  Policy iteration loop toward reward target <reward_target>.
initial: act
context:
  reward_target: <reward_target>
states:
  act:
    action: |
      <act_action>
    action_type: <act_action_type>
    capture: action_result
    next: observe
  observe:
    action: |
      <observe_action>
    action_type: <observe_action_type>
    capture: observation
    next: score
  score:
    action: |
      echo "${captured.observation.output}" | tail -1 | tr -d '[:space:]'
    action_type: shell
    evaluate:
      type: convergence
      target: "${context.reward_target}"
      direction: maximize
      tolerance: 0.05
    route:
      target: done
      progress: improve
      stall: act
  improve:
    action: |
      <improve_action>
    action_type: <improve_action_type>
    next: act
  done:
    terminal: true
max_iterations: <max_iterations>
```
```
