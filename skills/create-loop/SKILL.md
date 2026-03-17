---
description: Create a new FSM loop configuration interactively. Guides users through loop type selection, parameter gathering, YAML generation, and validation.
allowed-tools:
  - Bash(mkdir:*, test:*, ll-loop:*)
---

# Create Loop

Interactive command for creating new automation loop configurations. This command guides you through:
1. Choosing a structural loop pattern (fix until clean, maintain constraints, drive a metric, run a sequence, or harness a skill/prompt)
2. Gathering type-specific parameters
3. Naming the loop
4. Generating and previewing FSM YAML
5. Saving and validating
6. Optional test iteration to verify the loop works

## Allowed Tools

Use these tools during the workflow:
- `AskUserQuestion` - For interactive prompts
- `Write` - To save the loop configuration
- `Bash` - To run validation and create directories
- `Read` - To check for existing loops

## Workflow

### Step 0: Creation Mode

Use AskUserQuestion to determine whether to use a template or build from scratch:

```yaml
questions:
  - question: "How would you like to create your loop?"
    header: "Creation mode"
    multiSelect: false
    options:
      - label: "Start from template (Recommended)"
        description: "Choose a pre-built loop for common tasks"
      - label: "Build from scratch"
        description: "Configure a new loop from scratch using the guided wizard"
```

**If "Start from template"**: Read [templates.md](templates.md) for template selection and customization flow (Steps 0.1-0.2), then skip to Step 4.
**If "Build from scratch"**: Skip to Step 1 (Loop Type Selection)

---

### Step 1: Loop Type Selection (Custom Mode Only)

If user selected "Build from scratch" in Step 0, use this flow.

Use AskUserQuestion with a single-select to determine the loop type:

```yaml
questions:
  - question: "What kind of automation loop do you want to create?"
    header: "Loop type"
    multiSelect: false
    options:
      - label: "Fix until clean (Recommended)"
        description: "Run a check and fix issues until it passes. Pattern: evaluate → fix → done"
      - label: "Maintain constraints"
        description: "Keep multiple conditions true in a chain. Pattern: check-fix pairs chained to terminal"
      - label: "Drive a metric toward a target"
        description: "Measure a value and apply fixes until it reaches goal. Best for: reducing error counts, coverage"
      - label: "Run a sequence of steps"
        description: "Execute steps in order, repeat until condition met. Best for: multi-stage builds"
      - label: "Harness a skill or prompt"
        description: "Wrap a skill/prompt with plan-evaluate-iterate. Auto-generates evaluation from project context."
      - label: "RL: Bandit (explore vs exploit)"
        description: "Epsilon-greedy bandit loop — alternate explore/exploit rounds, routing on reward convergence. Best for: A/B strategy selection, prompt optimization, hyperparameter search."
      - label: "RL: RLHF-style (generate → score → refine)"
        description: "Generate candidate output, score quality, refine until quality target is met. Best for: iterative content improvement, prompt refinement, answer quality loops."
      - label: "RL: Policy iteration (act → observe → improve)"
        description: "Agent acts, observes reward, improves policy toward a target. Best for: environment interaction, agent training simulations, adaptive automation."
```

**Type Mapping:**
- "Fix until clean" -> `fix-until-clean` type (states: evaluate, fix, done)
- "Maintain constraints" -> `maintain-constraints` type (check/fix pairs + terminal)
- "Drive a metric toward a target" -> `drive-metric` type (states: measure, apply, done)
- "Run a sequence of steps" -> `run-sequence` type (step_0...step_N, check_done, done)
- "Harness a skill or prompt" -> `harness` type (states: discover, execute, check_concrete, check_semantic, check_invariants, advance, done)
- **Sub-loop composition** — not a wizard type; use `loop:` field in YAML to invoke other loops as child FSMs (see [reference.md](reference.md))
- "RL: Bandit (explore vs exploit)" -> `rl-bandit` type (states: explore, exploit, reward, done)
- "RL: RLHF-style (generate → score → refine)" -> `rl-rlhf` type (states: generate, score, refine, done)
- "RL: Policy iteration (act → observe → improve)" -> `rl-policy` type (states: act, observe, score, improve, done)

### Step 2: Type-Specific Questions

Based on the selected loop type, read [loop-types.md](loop-types.md) for the detailed question flow and FSM YAML generation for each type.

---

### Step 3: Loop Name

After gathering type-specific parameters, ask for the loop name:

```yaml
questions:
  - question: "What should this loop be called?"
    header: "Loop name"
    multiSelect: false
    options:
      - label: "<auto-suggested-name>"
        description: "Based on your selections"
      - label: "Custom name"
        description: "Enter your own name"
```

**Auto-suggest names based on loop type:**
- Fix until clean: `fix-<targets>` (e.g., `fix-types-and-lint`)
- Maintain constraints: `<constraint-names>-guardian` (e.g., `tests-types-lint-guardian`)
- Drive a metric: `reduce-<metric>` or `increase-<metric>` (e.g., `reduce-lint-errors`)
- Run a sequence: `<step-summary>-loop` (e.g., `fix-test-check-loop`)
- Harness a skill/prompt: `harness-<skill-name>` or `<skill-name>-loop` (e.g., `harness-refine-issue`)

### Step 4: Preview and Confirm

Generate and display the FSM YAML.

**Generate FSM YAML:**

Read [loop-types.md](loop-types.md) for the FSM YAML template for the selected loop type. Generate the complete FSM YAML based on the parameters gathered in Step 2.

Also generate a summary preview showing:
1. States in execution order (use -> between states)
2. Transitions for each non-terminal state
3. Terminal states marked with `[terminal]`
4. Initial state and max_iterations from the configuration

**Display format:**

```
Here's your loop configuration:

## FSM YAML
```yaml
<generated-yaml>
```

## Summary
States: <state1> -> <state2> -> ... -> <terminal>
Transitions:
  <state1>: <verdict>-><target>, <verdict>-><target>
  <state2>: next-><target>
  ...
  <terminal>: [terminal]
Initial: <initial-state>
Max iterations: <max_iterations>
Evaluator: <type> [<details>]  # Only shown if non-default evaluator configured

This will create: {{config.loops.loops_dir}}/<name>.yaml
```

Use AskUserQuestion:
```yaml
questions:
  - question: "Save this loop configuration?"
    header: "Confirm"
    multiSelect: false
    options:
      - label: "Yes, save and validate"
        description: "Save to {{config.loops.loops_dir}}/<name>.yaml and run validation"
      - label: "No, start over"
        description: "Discard and restart the wizard"
```

### Step 5: Save and Validate

If confirmed:

1. **Create directory if needed:**
   ```bash
   mkdir -p {{config.loops.loops_dir}}
   ```

2. **Check for existing file:**
   ```bash
   test -f {{config.loops.loops_dir}}/<name>.yaml && echo "EXISTS" || echo "OK"
   ```

   If exists, ask:
   ```yaml
   questions:
     - question: "A loop with this name already exists. Overwrite?"
       header: "Overwrite"
       multiSelect: false
       options:
         - label: "Yes, overwrite"
           description: "Replace the existing loop configuration"
         - label: "No, choose different name"
           description: "Go back and pick a new name"
   ```

3. **Write the file** using the Write tool:
   - Path: `{{config.loops.loops_dir}}/<name>.yaml`
   - Content: The generated YAML

4. **Validate** using ll-loop CLI:
   ```bash
   ll-loop validate <name>
   ```

5. **Offer test iteration** (after validation succeeds):

   Use AskUserQuestion:
   ```yaml
   questions:
     - question: "Would you like to run a test iteration to verify the loop works?"
       header: "Test run"
       multiSelect: false
       options:
         - label: "Yes, run one iteration (Recommended)"
           description: "Execute check command and verify evaluation works"
         - label: "No, I'll test manually"
           description: "Skip test iteration"
   ```

   If "Yes, run one iteration":
   ```bash
   ll-loop test <name>
   ```

   Display the test output directly. Example output:

   ```
   ## Test Iteration: my-loop

   State: check
   Action: {{config.project.type_cmd}} {{config.project.src_dir}}

   Exit code: 1
   Output:
   Found 3 errors in 1 file (checked 5 source files)

   Evaluator: exit_code (default)
   Verdict: FAILURE

   Would transition: check -> fix

   Loop appears to be configured correctly
   ```

   The test command validates your loop configuration by running one iteration:
   - Shows the state and action being tested
   - Displays exit code and output (truncated if long)
   - Reports evaluator type and verdict
   - Indicates what transition would occur

   Continue to the success report regardless of test result.

6. **Report results:**

   On success (no test issues):
   ```
   Loop created successfully!

   File: {{config.loops.loops_dir}}/<name>.yaml
   States: <list-of-states>
   Initial: <initial-state>
   Max iterations: <max>

   Run now with: ll-loop <name>
   Tip: Run /ll:review-loop <name> to audit quality and best practices.
   ```

   On success with test issues (test ran but found problems):
   ```
   Loop created successfully!

   File: {{config.loops.loops_dir}}/<name>.yaml
   States: <list-of-states>
   Initial: <initial-state>
   Max iterations: <max>

   Note: Test iteration found issues - see output above.
   You may want to review the configuration before running.

   Run now with: ll-loop <name>
   Tip: Run /ll:review-loop <name> to audit quality and best practices.
   ```

   On validation failure:
   ```
   Loop saved but validation failed:
   <error-message>

   Please fix the configuration at {{config.loops.loops_dir}}/<name>.yaml
   ```

## Additional Resources

- For pre-built loop templates, see [templates.md](templates.md)
- For loop type question flows and FSM YAML generation, see [loop-types.md](loop-types.md)
- For quick reference tables and advanced configuration, see [reference.md](reference.md)

## Examples

```bash
# Start the interactive wizard
/ll:create-loop

# The command will guide you through:
# 1. Selecting a loop type (fix-until-clean, maintain-constraints, drive-metric, run-sequence, harness)
# 2. Configuring type-specific options
# 3. Naming the loop
# 4. Previewing and saving the FSM YAML
```

---

## Integration

This command creates FSM loop configurations that can be executed with the `ll-loop` CLI.

Works well with:
- `ll-loop <name>` - Execute the created loop
- `ll-loop validate <name>` - Validate loop configuration
- `/ll:check-code` - Often used as a fix action in loops
- `/ll:manage-issue` - Used for complex bug fixes in loops
