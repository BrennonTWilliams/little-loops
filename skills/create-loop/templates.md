# Template Path: Loop Type Selection & Customization

## Step 0.1: Loop Type Selection (Template Path)

If "Start from template" was selected, present the available templates:

```yaml
questions:
  - question: "Which structural pattern fits your loop?"
    header: "Template"
    multiSelect: false
    options:
      - label: "Fix until clean (Recommended)"
        description: "Run a check; fix issues until it passes. Pattern: evaluate → fix → done"
      - label: "Maintain constraints"
        description: "Keep multiple conditions true in a chain. Pattern: check-fix pairs chained to terminal"
      - label: "Run a sequence of steps"
        description: "Execute ordered steps until a done-check passes. Pattern: step_0 → step_1 → … → done"
      - label: "Harness a skill or prompt"
        description: "Wrap any skill with evaluate-iterate. Pattern: execute → check → advance → done"
      - label: "Optimize a harness (meta-loop)"
        description: "Score-gated hill-climbing on a harness artifact. Pattern: diagnose → baseline → propose → apply → score → gate → commit/revert → done"
```

**After template selection**: Continue to Step 0.2 (Template Customization), then skip to Step 4 (Preview and Confirm) with template-populated configuration.

---

## Template Definitions

### Template: fix-until-clean

```yaml
name: "fix-until-clean"
initial: evaluate
max_iterations: {{max_iterations}}
states:
  evaluate:
    action: "{{check_cmd}}"
    on_yes: done
    on_no: fix
    on_error: fix
  fix:
    action: "{{fix_cmd}}"
    next: evaluate
  done:
    terminal: true
```

### Template: maintain-constraints

```yaml
name: "maintain-constraints"
initial: check_tests
max_iterations: {{max_iterations}}
states:
  check_tests:
    action: "{{test_cmd}}"
    on_yes: check_types
    on_no: fix_tests
  fix_tests:
    action: "{{fix_tests_cmd}}"
    next: check_tests
  check_types:
    action: "{{type_cmd}}"
    on_yes: check_lint
    on_no: fix_types
  fix_types:
    action: "{{fix_types_cmd}}"
    next: check_types
  check_lint:
    action: "{{lint_cmd}}"
    on_yes: all_valid
    on_no: fix_lint
  fix_lint:
    action: "{{lint_fix_cmd}}"
    next: check_lint
  all_valid:
    terminal: true
```

### Template: run-sequence

```yaml
name: "run-sequence"
initial: step_0
max_iterations: {{max_iterations}}
states:
  step_0:
    action: "{{step_0_cmd}}"
    next: step_1
  step_1:
    action: "{{step_1_cmd}}"
    next: check_done
  check_done:
    action: "{{done_check_cmd}}"
    on_yes: done
    on_no: step_0
  done:
    terminal: true
```

### Template: meta-optimize

```yaml
name: "{{loop_name}}"
description: |
  {{description}}
initial: diagnose
max_iterations: {{max_iterations}}
timeout: 7200
context:
  targets: "{{targets}}"
  tasks_dir: "{{tasks_dir}}"
  scorer: "{{scorer}}"
  target_score: {{target_score}}

states:
  diagnose:
    action_type: {{diagnose_action_type}}
    action: |
      {{diagnose_action}}
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

**Placeholders**: `{{loop_name}}`, `{{description}}`, `{{max_iterations}}`, `{{targets}}`, `{{tasks_dir}}`, `{{scorer}}`, `{{target_score}}`, `{{diagnose_action_type}}`, `{{diagnose_action}}`.

---

### Template: harness-skill

```yaml
name: "harness-{{skill_name}}"
initial: execute
max_iterations: {{max_iterations}}
states:
  execute:
    action: "/ll:{{skill_name}}"
    action_type: slash_command
    next: check_concrete
  check_concrete:
    action: "{{check_cmd}}"
    action_type: shell
    evaluate:
      type: exit_code
    on_yes: done
    on_no: execute
  done:
    terminal: true
```

---

## Step 0.2: Template Customization

After template selection, ask for template-specific parameters:

### For "Fix until clean"

```yaml
questions:
  - question: "What command checks for the problem?"
    header: "Check command"
    multiSelect: false
    options:
      - label: "pytest (Recommended)"
        description: "Run test suite"
      - label: "ruff check src/"
        description: "Lint check"
      - label: "mypy src/"
        description: "Type check"
      - label: "Custom command"
        description: "Specify your own check command"

  - question: "What command fixes the problem?"
    header: "Fix command"
    multiSelect: false
    options:
      - label: "/ll:manage-issue bug fix (Recommended)"
        description: "Let Claude fix it autonomously"
      - label: "ruff check --fix src/"
        description: "Auto-fix lint errors"
      - label: "Custom command"
        description: "Specify your own fix command"

  - question: "What's the maximum number of fix attempts?"
    header: "Max iterations"
    multiSelect: false
    options:
      - label: "20 (Recommended)"
        description: "Good for most use cases"
      - label: "10"
        description: "Quick fixes only"
      - label: "50"
        description: "For complex issues"
```

**Apply substitutions:** Replace `{{check_cmd}}`, `{{fix_cmd}}`, `{{max_iterations}}`.

### For "Maintain constraints"

```yaml
questions:
  - question: "What source directory should the loop check?"
    header: "Source dir"
    multiSelect: false
    options:
      - label: "src/ (Recommended)"
        description: "Standard source directory"
      - label: "."
        description: "Project root"
      - label: "lib/"
        description: "Library directory"
      - label: "Custom path"
        description: "Specify your own directory"

  - question: "What's the maximum number of fix attempts?"
    header: "Max iterations"
    multiSelect: false
    options:
      - label: "20 (Recommended)"
        description: "Good for most use cases"
      - label: "10"
        description: "Quick fixes only"
      - label: "50"
        description: "For complex issues"
```

**Apply substitutions:** Replace `{{src_dir}}`, `{{max_iterations}}`, `{{test_cmd}}`, `{{type_cmd}}`, `{{lint_cmd}}`, `{{lint_fix_cmd}}`, `{{fix_tests_cmd}}`, `{{fix_types_cmd}}` with language-appropriate defaults (Python: `pytest`, `mypy {{src_dir}}`, `ruff check {{src_dir}}`, `ruff check --fix {{src_dir}}`, `/ll:manage-issue bug fix`; JavaScript: `npm test`, `npx tsc --noEmit`, `npx eslint {{src_dir}}`, `npx eslint --fix {{src_dir}}`, `echo 'Fix manually'`).

**If "Custom path" selected for source dir**: Ask for path via Other option.

### For "Run a sequence of steps"

```yaml
questions:
  - question: "What command runs in step 0?"
    header: "Step 0 command"
    multiSelect: false
    options:
      - label: "Custom command"
        description: "Specify the first step command"

  - question: "What command runs in step 1?"
    header: "Step 1 command"
    multiSelect: false
    options:
      - label: "Custom command"
        description: "Specify the second step command"

  - question: "What command checks if the sequence is done?"
    header: "Done-check command"
    multiSelect: false
    options:
      - label: "Custom command"
        description: "Returns exit 0 when done, non-zero to repeat"

  - question: "What's the maximum number of iterations?"
    header: "Max iterations"
    multiSelect: false
    options:
      - label: "20 (Recommended)"
        description: "Good for most use cases"
      - label: "10"
        description: "Quick sequences"
      - label: "50"
        description: "For complex pipelines"
```

**Apply substitutions:** Replace `{{step_0_cmd}}`, `{{step_1_cmd}}`, `{{done_check_cmd}}`, `{{max_iterations}}`.

### For "Harness a skill or prompt"

```yaml
questions:
  - question: "Which skill do you want to harness?"
    header: "Skill name"
    multiSelect: false
    options:
      - label: "<auto-discovered skills from skills/*/SKILL.md>"
        description: "<skill description>"
      - label: "Custom prompt"
        description: "Specify a free-form prompt instead"

  - question: "What command verifies the skill succeeded?"
    header: "Check command"
    multiSelect: false
    options:
      - label: "pytest (Recommended)"
        description: "Run tests to verify"
      - label: "ruff check src/"
        description: "Check lint passes"
      - label: "Custom command"
        description: "Specify your own verification command"

  - question: "What's the maximum number of iterations?"
    header: "Max iterations"
    multiSelect: false
    options:
      - label: "20 (Recommended)"
        description: "Good for most skills"
      - label: "50"
        description: "For complex or slow-converging skills"
```

**Apply substitutions:** Replace `{{skill_name}}`, `{{check_cmd}}`, `{{max_iterations}}`.

### For "Optimize a harness (meta-loop)"

```yaml
questions:
  - question: "What harness artifact(s) will this loop modify? (space-separated paths)"
    header: "Targets"
    multiSelect: false
    options:
      - label: "Custom paths"
        description: "Enter the file path(s) to modify, e.g. .loops/my-loop.yaml"

  - question: "What scorer command produces a numeric quality signal? (required)"
    header: "Scorer"
    multiSelect: false
    options:
      - label: "./scripts/score.sh"
        description: "Custom scoring script"
      - label: "pytest scripts/tests/ -q --tb=no"
        description: "Test suite as scorer"
      - label: "Custom command"
        description: "Specify your own scorer command"

  - question: "What is the score target / early-stop threshold?"
    header: "Target score"
    multiSelect: false
    options:
      - label: "1.0 (Recommended)"
        description: "Never early-stop; only commit on improvement"
      - label: "0.9"
        description: "Stop once score reaches 90%"
      - label: "Custom value"
        description: "Enter your own threshold (0.0–1.0)"

  - question: "Where is the task / benchmark directory?"
    header: "Tasks dir"
    multiSelect: false
    options:
      - label: "scripts/tests/"
        description: "Project test suite"
      - label: ".loops/tasks/"
        description: "Loop-specific task directory"
      - label: "Custom path"
        description: "Specify your own directory"

  - question: "What is the diagnose action? (required)"
    header: "Diagnose"
    multiSelect: false
    options:
      - label: "Shell: read recent runs from .loops/runs/ and summarize failures"
        description: "Uses shell to surface current failure modes"
      - label: "Custom shell command"
        description: "A command that prints what most needs improvement"
      - label: "Custom prompt"
        description: "Natural-language prompt that analyzes the artifact"
```

**Scorer refusal guard**: If scorer is empty, abort with:
```
Error: scorer is required for meta-optimize loops.
  A numeric quality signal is needed to gate commits (convergence evaluation).
  Provide a command that exits 0 on success and prints a numeric score on the last line.
  Re-run /ll:create-loop and enter a scorer command to continue.
```

**Apply substitutions:** Replace `{{targets}}`, `{{scorer}}`, `{{target_score}}`, `{{tasks_dir}}`, `{{diagnose_action_type}}` (`shell` or `prompt`), `{{diagnose_action}}`, `{{max_iterations}}` (default 30), `{{loop_name}}` (auto-suggest: `optimize-<artifact-basename>`), `{{description}}`.

---

**Flow after template customization:**
- The generated FSM YAML and auto-suggested loop name are ready
- Continue directly to Step 4 (Preview and Confirm) with the template-populated configuration
- Skip Step 1 (Loop Type Selection), Step 2 (Type-Specific Questions), and Step 3 (Loop Name) since the template provides all configuration
