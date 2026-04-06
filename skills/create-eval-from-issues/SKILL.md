---
description: |
  Use when the user wants to generate an FSM eval harness YAML from one or more issue IDs. Reads issue context (Expected Behavior, Use Case, Acceptance Criteria) and synthesizes a ready-to-run harness that exercises the feature as a real user would, then validates it with ll-loop validate.

  Trigger keywords: "create eval from issues", "generate eval harness", "eval harness from issue", "create harness from FEAT", "issue to harness", "eval harness FEAT-NNN"
argument-hint: "<issue-id> [issue-id...]"
allowed-tools:
  - Bash(ll-issues:*, ll-loop:*, mkdir:*)
  - Read
  - Write
arguments:
  - name: issue_ids
    description: One or more issue IDs (e.g., FEAT-919, ENH-950, BUG-347). Accepts open or completed issues.
    required: true
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
for token in $ARGUMENTS; do
  case "$token" in
    --*) ;;  # skip flags (reserved for future use)
    *) ISSUE_IDS+=("$token") ;;
  esac
done

if [ ${#ISSUE_IDS[@]} -eq 0 ]; then
  echo "Error: at least one issue ID is required."
  echo "Usage: /ll:create-eval-from-issues FEAT-919 [ENH-950 ...]"
  exit 1
fi
```

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
max_iterations: 5
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
max_iterations: 50
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
