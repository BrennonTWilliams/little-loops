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
trigger_fixtures:
  should_fire:
    - "generate an FSM eval harness yaml from one or more issue ids"
    - "generate DSL eval tasks from this loop yaml file"
  should_not_fire:
    - "generate an adversarial verification loop that tries to break a feature"
    - "generate a verification loop from acceptance criteria"
---

# Create Eval From Issues

Generate a ready-to-run FSM eval harness YAML from one or more issue IDs via
`ll-loop scaffold-eval` (FEAT-2948). The harness exercises each feature **as a
real user would** and evaluates the quality of that experience — not whether
the issue was implemented.

## Overview

This skill:
1. Resolves each issue ID to a file path using `ll-issues show <ID> --json`
2. Reads the issue file to extract Expected Behavior, Use Case, and Acceptance Criteria sections
3. Synthesizes a natural-language `execute` prompt and `llm_structured` evaluation criteria (genuine LLM authoring)
4. Runs `ll-loop scaffold-eval` to generate a schema-valid, in-process-validated harness YAML (Variant A for 1 issue, Variant B for 2+, proof-state chaining included) with `<EXECUTE_PROMPT>`/`<EVALUATION_CRITERIA_PROMPT>` placeholder slots
5. Fills the placeholders with the Step 3 text and writes the file to `.loops/eval-harness-<slug>.yaml`

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

`ll-harness dsl` grades each task against its own `expected:` mapping — that's what makes the
DSL pass rate meaningful (BUG-3196). A task that omits `expected:` is graded only if the run
is invoked with `--semantic`; with neither, it is excluded from the pass-rate denominator and
reported as ungraded rather than counted as a pass. Always populate `expected:` for
`fill-in-the-blank` and `correction` task types.

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

**Both open and completed issues are accepted.** The `ll-issues show` command finds an issue by ID regardless of its `status:` frontmatter (open, done, deferred, etc.) — there is no `completed/` or `deferred/` directory.

## Step 2: Extract Evaluation Context

For each resolved issue file, read the file directly and extract:

1. **Title** — from the YAML frontmatter `title:` field or the first `# FEAT-NNN:` heading
2. **Expected Behavior section** — the `## Expected Behavior` section body (steps describing what happens)
3. **Use Case section** — the `## Use Case` section body (who the user is, workflow, goal, outcome)
4. **Acceptance Criteria section** — the `## Acceptance Criteria` section body (checkboxes with observable conditions)
5. **Learning test targets** — the `learning_tests_required:` list from YAML frontmatter (may be absent or empty)

If a section is absent, note it and proceed with what is available. Prioritize Acceptance Criteria for evaluation criteria synthesis; prioritize Expected Behavior + Use Case for execute prompt synthesis.

Proof-First Gate injection (whether `learning_tests.enabled` in `.ll/ll-config.json`
is true and the issue(s) declare `learning_tests_required` targets) is handled by
`ll-loop scaffold-eval` itself in Step 4 — no need to check it here.

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

End the evaluation criteria prompt with an evidence-contract clause requiring a verbatim quote, e.g.: "Provide a VERBATIM quote from the observed output that supports your verdict. Do not assert a verdict without evidence." (matches `scripts/little_loops/fsm/evaluators.py`'s `CHECK_SEMANTIC_EVIDENCE_CONTRACT`; satisfies MR-8's `VERBATIM`/`quote`/`evidence` keyword check).

## Step 4: Generate the Harness

`ll-loop scaffold-eval` picks Variant A (1 issue, `initial: execute`) vs. Variant B
(2+ issues, `initial: discover`/`advance`), generates and chains any Proof-First
Gate `check_proof_<slug>` states (reading `learning_tests.enabled` and each issue's
`learning_tests_required` itself), validates the resulting `FSMLoop` in-process, and
emits the completed YAML with `<EXECUTE_PROMPT>`/`<EVALUATION_CRITERIA_PROMPT>`
placeholder slots standing in for the Step 3 text:

```bash
IDS=$(IFS=,; echo "${ISSUE_IDS[*]}")
mkdir -p .loops/
ll-loop scaffold-eval --issues "$IDS" --json > /tmp/scaffold-eval-result.json
```

Read the JSON result (`yaml_text`, `placeholders`, `validated`, `errors`). If any
issue ID failed to resolve, `yaml_text` is empty — report the `errors` and stop.

**No `check_invariants`**: eval harnesses measure user experience quality, not code
diff size; the scaffold never emits `check_stall`, `check_concrete`, `check_semantic`,
or `check_invariants` states.

## Step 5: Fill Placeholders and Write

Replace each `<EXECUTE_PROMPT>` occurrence with the Step 3 execute prompt and each
`<EVALUATION_CRITERIA_PROMPT>` occurrence with the Step 3 evaluation criteria prompt
(Variant B embeds one combined prompt per placeholder — write it so the running
agent can select the right per-issue content via `${captured.current_item.output}`).
Use the `name:` field inside the returned YAML for the exact output slug, then use
the Write tool to write the filled YAML to `.loops/<name>.yaml`.

`ll-loop scaffold-eval` already ran `validate_fsm()` in-process (`validated` in the
JSON result), so no separate `ll-loop validate` call is required — but the
placeholder substitution above happens *after* that check, so re-run
`ll-loop validate <name>` once the file is written as a final sanity check on the
filled-in prompt text.

## Output Format

After completion, output:

```
✓ Eval harness generated: .loops/eval-harness-<slug>.yaml

Issues included:
  - <ISSUE-ID>: <title>
  [...]

Variant: <A (single-shot) | B (multi-item)>
Proof-First Gates: <N proof states injected, or "none">

Validation: PASS / FAIL
  [errors if FAIL]

To run:
  ll-loop run eval-harness-<slug>
```

## Example

**Single issue:**
```
/ll:create-eval-from-issues FEAT-919
→ ll-loop scaffold-eval --issues FEAT-919 --json
→ Writes: .loops/eval-harness-feat-919.yaml
```

**Multiple issues:**
```
/ll:create-eval-from-issues FEAT-919 ENH-950
→ ll-loop scaffold-eval --issues FEAT-919,ENH-950 --json
→ Writes: .loops/eval-harness-feat-919-enh-950.yaml
```
