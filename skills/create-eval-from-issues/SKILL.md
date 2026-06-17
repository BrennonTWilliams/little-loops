---
name: create-eval-from-issues
description: Use when asked to generate an FSM eval harness YAML from one or more issue IDs, or DSL eval tasks from a loop/issue file with --dsl.
argument-hint: "<issue-id> [issue-id...] | --dsl <loop-yaml-or-issue-file>"
allowed-tools:
  - Bash(ll-issues:*, ll-loop:*, mkdir:*)
  - Read
  - Write
arguments:
  - name: issue_ids
    description: One or more issue IDs (e.g., FEAT-919, ENH-950, BUG-347). Accepts open or completed issues.
    required: false
  - name: --dsl
    description: Path to a loop YAML or issue file. Generates DSL-native fill-in-the-blank/transform/correction tasks under evals/dsl/<source-name>/ instead of an FSM eval harness.
    required: false
metadata:
  short-description: Generate FSM eval harness YAML from issue IDs, or DSL eval tasks with --dsl.
---

# Create Eval From Issues

Generate a ready-to-run FSM eval harness YAML from one or more issue IDs. The harness exercises each feature **as a real user would** and evaluates the quality of that experience — not whether the issue was implemented.

## Overview

This skill:
1. Resolves each issue ID to a file path using `ll-issues show <ID> --json`
2. Reads the issue file to extract Expected Behavior, Use Case, and Acceptance Criteria sections
3. Synthesizes a natural-language `execute` prompt describing how a user exercises the feature
4. Synthesizes `llm_structured` evaluation criteria describing what a successful user experience looks like
5. Generates a harness YAML (Variant A for 1 issue, Variant B for 2+ issues)
6. Writes the file to `.loops/eval-harness-<slug>.yaml`
7. Validates it with `ll-loop validate` and reports the result

## Arguments

$ARGUMENTS

Parse arguments:

```bash
ISSUE_IDS=()
DSL_SOURCE=""
for token in $ARGUMENTS; do
  case "$token" in
    --dsl) DSL_MODE=true ;;
    --dsl=*) DSL_SOURCE="${token#--dsl=}"; DSL_MODE=true ;;
    *)
      if [ "${DSL_MODE_NEXT:-}" = "true" ]; then
        DSL_SOURCE="$token"
        DSL_MODE_NEXT=false
      elif [ "${DSL_MODE:-}" = "true" ] && [ -z "$DSL_SOURCE" ]; then
        DSL_SOURCE="$token"
      else
        ISSUE_IDS+=("$token")
      fi
      ;;
  esac
  [ "${token}" = "--dsl" ] && DSL_MODE_NEXT=true
done

if [ "${DSL_MODE:-false}" = "true" ]; then
  # Route to DSL task generation mode (see DSL Mode section below)
  if [ -z "$DSL_SOURCE" ]; then
    echo "Error: --dsl requires a source file path."
    echo "Usage: /ll:create-eval-from-issues --dsl <loop-yaml-or-issue-file>"
    exit 1
  fi
  # Continue to DSL Mode section below
else
  if [ ${#ISSUE_IDS[@]} -eq 0 ]; then
    echo "Error: at least one issue ID is required."
    echo "Usage: /ll:create-eval-from-issues FEAT-919 [ENH-950 ...]"
    echo "       /ll:create-eval-from-issues --dsl <loop-yaml-or-issue-file>"
    exit 1
  fi
fi
```

## DSL Mode (`--dsl <source-file>`)

When `DSL_MODE=true`, skip Steps 1–7 below and follow these instructions instead.

### DSL Step 1: Identify Source Type

```bash
SOURCE_FILE="$DSL_SOURCE"
# Determine source type from extension or content
if echo "$SOURCE_FILE" | grep -qE '\.issues/|frontmatter|\.md$'; then
  SOURCE_TYPE="issue"
else
  SOURCE_TYPE="loop"
fi
SOURCE_NAME=$(basename "$SOURCE_FILE" | sed 's/\.[^.]*$//' | tr '[:upper:]' '[:lower:]' | tr '_' '-')
OUTPUT_DIR="evals/dsl/${SOURCE_NAME}"
mkdir -p "$OUTPUT_DIR"
```

### DSL Step 2: Extract DSL Content

**For loop YAML sources** (`SOURCE_TYPE=loop`):

```bash
ll-loop show -j "$SOURCE_NAME" 2>/dev/null || cat "$SOURCE_FILE"
```

Extract all states and their routing fields (`on_yes`, `on_no`, `on_partial`, `on_error`, `next`, `route` tables). These are the fill-in-the-blank targets.

**For issue file sources** (`SOURCE_TYPE=issue`):

Read the frontmatter fields using the Read tool. Focus on:
- `status:` field (common malformation: `completed`, `wip`, `done` → canonical values)
- `priority:` format (P0–P5)
- Required fields: `id`, `title`, `type`, `priority`, `status`

### DSL Step 3: Generate Task Files

Generate 3–5 DSL task YAML files in `$OUTPUT_DIR/`. Each file follows the Option B schema:

```yaml
prompt: |
  <natural-language instruction describing what to fill in or correct>
blanks:
  - <field_name_1>
  - <field_name_2>
expected:
  <field_name_1>: <correct_value>
  <field_name_2>: <correct_value>
source_dsl: <loop|issue>
source_file: <relative-path-to-SOURCE_FILE>
task_type: <fill-in-the-blank|transform|correction>
generated_at: '<ISO-8601-timestamp>'
```

**Task types to generate:**

For **loop YAML** sources:
1. `fill-in-the-blank`: Remove one `on_yes` or `on_no` field from a state and ask the model to complete it
2. `fill-in-the-blank`: Remove a `next:` field from a non-evaluating state and ask the model to complete the transition
3. `correction`: Introduce a malformed routing value (e.g., `on_yes: invalid_state`) and ask the model to fix it
4. `transform`: Given a state definition with missing `evaluate:` block, ask the model to add the correct evaluator type for the action

For **issue file** sources:
1. `correction`: Show `status: completed` and ask model to correct to canonical value
2. `correction`: Show a missing required field and ask model to supply it with correct format
3. `fill-in-the-blank`: Show partial frontmatter with `priority:` missing and ask model to assign based on severity description

Name files sequentially: `task-01.yaml`, `task-02.yaml`, etc.

### DSL Step 4: Report

After writing all task files:

```
✓ DSL eval tasks generated: evals/dsl/<source-name>/

Source: <SOURCE_FILE> (<loop|issue>)
Tasks generated:
  - task-01.yaml  (fill-in-the-blank: on_yes transition)
  - task-02.yaml  (correction: malformed routing)
  ...

To run:
  ll-harness dsl evals/dsl/<source-name>/
  ll-harness dsl evals/dsl/<source-name>/ --model claude-haiku-4-5-20251001
```

**Stop here.** Do not proceed to Steps 1–7 below.

---

## Step 1: Resolve Issue Files

For each ID in `$ISSUE_IDS`, resolve the issue file path:

```bash
for ID in "${ISSUE_IDS[@]}"; do
  ll-issues show "$ID" --json
done
```

Use the `path` field from each JSON result. If `ll-issues show` fails for an ID, report the error and skip that ID (do not halt).

**Both open and completed issues are accepted.** The `ll-issues show` command searches all categories including `completed/` and `deferred/`.

## Step 2: Extract Evaluation Context

For each resolved issue file, read the file directly and extract:

1. **Title** — from the YAML frontmatter `title:` field or the first `# FEAT-NNN:` heading
2. **Expected Behavior section** — the `## Expected Behavior` section body (steps describing what happens)
3. **Use Case section** — the `## Use Case` section body (who the user is, workflow, goal, outcome)
4. **Acceptance Criteria section** — the `## Acceptance Criteria` section body (checkboxes with observable conditions)

If a section is absent, note it and proceed with what is available. Prioritize Acceptance Criteria for evaluation criteria synthesis; prioritize Expected Behavior + Use Case for execute prompt synthesis.

## Step 3: Synthesize Harness Prompts

For **each issue**, synthesize two prompts:

### Execute Prompt (natural-language user action)

Source: Expected Behavior steps + Use Case workflow

Produce a paragraph describing what a real user does to exercise this feature. Write it as a user instruction, not as a test assertion. The executing agent (Claude or a browser tool like Playwright MCP) will carry it out using whatever tools are available in the loop context.

Example pattern:
> "Use [feature name] as a real user would. [What does the user do? Where do they go? What input do they provide?] Observe what happens — note any errors, delays, or unexpected behavior in the output."

### Evaluation Criteria (llm_structured prompt)

Source: Acceptance Criteria + Use Case outcome

Produce a numbered-condition prompt asking whether the user experience met the issue's success signals. Each condition must be directly observable by an LLM reviewing the interaction output.

Example pattern:
> "Did [feature name] ([ISSUE-ID]) deliver a satisfying user experience? Assess all of the following:
> (1) [Condition from Acceptance Criteria 1]
> (2) [Condition from Acceptance Criteria 2]
> ...
> Answer YES only if all conditions were clearly met. Answer NO and specify which condition(s) failed and what was observed."

Include both a success signal (what YES looks like) and a failure signal (what NO looks like, drawn from any "should not" or negative conditions in the issue).

## Step 4: Select Harness Variant

- **1 issue → Variant A**: single-shot harness, `initial: execute`
- **2+ issues → Variant B**: multi-item harness with `discover` state, `initial: discover`

## Step 5: Generate Harness YAML

### Slug Generation

```bash
SLUG=$(echo "${ISSUE_IDS[*]}" | tr '[:upper:]' '[:lower:]' | tr ' ' '-')
# e.g., "FEAT-919 ENH-950" → "feat-919-enh-950"
HARNESS_NAME="eval-harness-${SLUG}"
OUTPUT_FILE=".loops/${HARNESS_NAME}.yaml"
```

### Variant A (single issue)

Generate YAML with this structure:

```yaml
name: "eval-harness-<slug>"
category: harness
description: |
  Eval harness for <ISSUE-ID>: <issue title>.
  Exercises the feature as a real user would and evaluates the quality of the experience.
  Generated by /ll:create-eval-from-issues on <YYYY-MM-DD>.
initial: execute
max_steps: 5
timeout: 1800

states:

  execute:
    action: >
      <synthesized execute prompt from Step 3>
    action_type: prompt
    timeout: 300
    next: check_skill

  check_skill:
    action: >
      Evaluate the <feature name> feature from a real user's perspective.
    action_type: prompt
    timeout: 180
    evaluate:
      type: llm_structured
      prompt: >
        <synthesized evaluation criteria from Step 3>
    on_yes: done
    on_no: execute

  done:
    terminal: true
```

### Variant B (multiple issues)

Generate YAML with a `discover` state that iterates over the hardcoded issue IDs using a temp file to track progress:

```yaml
name: "eval-harness-<slug>"
category: harness
description: |
  Eval harness for <ISSUE-ID-1>, <ISSUE-ID-2>, ...: multi-item user-perspective evaluation.
  Exercises each feature as a real user would and evaluates the quality of the experience.
  Generated by /ll:create-eval-from-issues on <YYYY-MM-DD>.
initial: discover
max_steps: 50
timeout: 7200

states:

  discover:
    action: |
      python3 -c "
      import sys
      ids = [<quoted list of issue IDs>]
      pf = '/tmp/<harness-name>-processed.txt'
      try: processed = open(pf).read().split()
      except FileNotFoundError: processed = []
      remaining = [i for i in ids if i not in processed]
      if not remaining: sys.exit(1)
      print(remaining[0])
      "
    fragment: shell_exit
    capture: current_item
    on_yes: execute
    on_no: done
    on_error: done

  execute:
    action: >
      <Combined execute prompt for all issues, referencing ${captured.current_item.output} for which issue is being evaluated.>
      
      The current issue being evaluated is: ${captured.current_item.output}
      
      <Per-issue execute prompts: look up which prompt applies based on the current item ID and exercise that feature as described.>
    action_type: prompt
    timeout: 300
    max_retries: 3
    on_retry_exhausted: advance
    next: check_skill

  check_skill:
    action: >
      Evaluate the feature described in issue ${captured.current_item.output} from a real user's perspective.
    action_type: prompt
    timeout: 180
    evaluate:
      type: llm_structured
      prompt: >
        <Combined evaluation criteria prompt — look up which criteria apply to ${captured.current_item.output} and assess those conditions.>
        
        The issue being evaluated is: ${captured.current_item.output}
        
        <Per-issue criteria: for each issue ID, list its numbered conditions. Apply only the conditions for the current issue.>
    on_yes: advance
    on_no: execute

  advance:
    action: |
      echo "${captured.current_item.output}" >> /tmp/<harness-name>-processed.txt
    action_type: shell
    next: discover

  done:
    terminal: true
```

**For Variant B**: in the `discover` action, embed the actual issue IDs at generation time (e.g., `ids = ['FEAT-919', 'ENH-950']`). In the `execute` and `check_skill` prompts, include all per-issue prompts/criteria in the action text so the running agent can select the right one based on `${captured.current_item.output}`.

**No `check_invariants`**: eval harnesses measure user experience quality, not code diff size. Do not include `check_stall`, `check_concrete`, `check_semantic`, or `check_invariants` states.

## Step 6: Write and Validate

```bash
mkdir -p .loops/
```

Use the Write tool to write the harness YAML to `.loops/<harness-name>.yaml`.

Then validate:

```bash
ll-loop validate <harness-name>
```

Report the validation result. If validation fails, show the errors and explain what needs to be fixed.

## Output Format

After completion, output:

```
✓ Eval harness generated: .loops/eval-harness-<slug>.yaml

Issues included:
  - <ISSUE-ID>: <title>
  [...]

Variant: <A (single-shot) | B (multi-item)>
States: execute → check_skill → done [→ discover + advance (Variant B)]

Validation: PASS / FAIL
  [validation output if FAIL]

To run:
  ll-loop run eval-harness-<slug>
```

## Example

**Single issue:**
```
/ll:create-eval-from-issues FEAT-919
→ Writes: .loops/eval-harness-feat-919.yaml
→ Harness: initial: execute, states: execute → check_skill → done
```

**Multiple issues:**
```
/ll:create-eval-from-issues FEAT-919 ENH-950
→ Writes: .loops/eval-harness-feat-919-enh-950.yaml
→ Harness: initial: discover, states: discover → execute → check_skill → advance → done
```
