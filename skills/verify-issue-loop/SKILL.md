---
name: verify-issue-loop
description: Use when asked to generate an FSM verification loop YAML from a single issue's acceptance criteria.
argument-hint: "<issue-id>"
allowed-tools:
  - Bash(ll-issues:*, ll-loop:*, mkdir:*)
  - Read
  - Write
arguments:
  - name: issue_id
    description: A single issue ID (e.g., FEAT-919, ENH-950, BUG-347). Accepts open or completed issues.
    required: true
metadata:
  short-description: Use when asked to generate an FSM verification loop YAML from a single issue's a
---

# Verify Issue Loop

Generate a ready-to-run FSM verification loop YAML from a single issue ID. The loop walks each acceptance criterion in order and asks an LLM whether the implementation satisfies it — failing fast on any criterion that fails.

This is the verification counterpart to `/ll:create-eval-from-issues`. Where `create-eval-from-issues` exercises a feature *as a user would* and judges experience quality, `verify-issue-loop` checks that the *implementation* meets each acceptance criterion.

## Overview

This skill:
1. Resolves the issue ID to a file path using `ll-issues show <ID> --json`
2. Reads the issue file to extract the `## Acceptance Criteria` section
3. Synthesizes one `verify-criterion-N` state per criterion, each with an `llm_structured` pass/fail evaluator
4. Wires linear pass-routing: `on_yes: verify-criterion-<N+1>` (or `done` for the final), `on_no: failed`
5. Writes the file to `.loops/verify-<ISSUE-ID>-<slug>.yaml`
6. Validates it with `ll-loop validate` and reports the result

## Arguments

$ARGUMENTS

Parse arguments:

```bash
ISSUE_ID=""
for token in $ARGUMENTS; do
  case "$token" in
    --*) ;;  # skip flags (reserved for future use)
    *) ISSUE_ID="$token"; break ;;
  esac
done

if [ -z "$ISSUE_ID" ]; then
  echo "Error: an issue ID is required."
  echo "Usage: /ll:verify-issue-loop FEAT-919"
  exit 1
fi
```

## Step 1: Resolve Issue File

Resolve the issue file path:

```bash
ll-issues show "$ISSUE_ID" --json
```

Use the `path` field from the JSON result. If `ll-issues show` fails, report the error and stop.

**Both open and completed issues are accepted.** The `ll-issues show` command searches all categories including `completed/` and `deferred/`.

## Step 2: Extract Acceptance Criteria

Read the resolved issue file directly and extract:

1. **Title** — from the YAML frontmatter `title:` field or the first `# ISSUE-NNN:` heading
2. **Acceptance Criteria section** — the `## Acceptance Criteria` section body (checkboxes or bullet items describing observable conditions)

Parse the acceptance criteria into an ordered list. Accept any of these bullet styles:

- `- [ ] ...` / `- [x] ...` (checkbox style — strip the leading `- [ ] ` / `- [x] `)
- `- ...` / `* ...` (plain bullets)
- `1. ...` / `2. ...` (numbered list)

Strip the marker and whitespace; keep the criterion text. Skip blank lines and sub-bullets (indented items belong to their parent criterion).

**If the section is missing or empty, halt with a clear error:**

```
Error: issue <ISSUE-ID> has no Acceptance Criteria section (or it is empty).
Run /ll:refine-issue <ISSUE-ID> to add criteria, or /ll:format-issue <ISSUE-ID>
to fix the section heading. No file was written.
```

Do **not** write a YAML file in this case.

## Step 3: Synthesize Verify-State Prompts

For each criterion (1-indexed), synthesize a single verify-state. The state's `action` (prompt) and its evaluator (`llm_structured`) both reference the criterion text.

### State action (prompt)

Tell the running agent to inspect the implementation and gather evidence specifically for this criterion. Pattern:

> "Verify acceptance criterion <N> for <ISSUE-ID>: <criterion text>. Inspect the implementation, run any commands needed, and gather concrete evidence about whether the criterion holds. Report what you observed."

### Evaluator prompt (llm_structured)

Ask the evaluator to decide pass/fail with a short reason. Pattern:

> "Does the implementation satisfy criterion <N> of <ISSUE-ID>?
>
> Criterion: <criterion text>
>
> Answer YES only if the evidence clearly shows the criterion is met.
> Answer NO if the criterion is not met or evidence is missing/ambiguous.
> Provide a one-sentence reason citing the observed evidence."

## Step 4: Wire Transitions

Generate N states named `verify-criterion-1`, `verify-criterion-2`, …, `verify-criterion-N`.

For each state at position `i` (1-indexed):

- `on_yes: verify-criterion-<i+1>` for `i < N`
- `on_yes: done` for `i == N`
- `on_no: failed` for every state

`done` and `failed` are both `terminal: true`.

`initial: verify-criterion-1`.

## Step 5: Generate Verification YAML

### Slug Generation

```bash
ISSUE_LOWER=$(echo "$ISSUE_ID" | tr '[:upper:]' '[:lower:]')
# Slug uses the issue ID + a kebab-cased title slug from the issue file
TITLE_SLUG=$(echo "$ISSUE_TITLE" | tr '[:upper:]' '[:lower:]' | tr -cs 'a-z0-9' '-' | sed 's/^-//;s/-$//')
LOOP_NAME="verify-${ISSUE_LOWER}-${TITLE_SLUG}"
OUTPUT_FILE=".loops/${LOOP_NAME}.yaml"
```

If the issue title cannot be extracted cleanly, fall back to `LOOP_NAME="verify-${ISSUE_LOWER}"`.

### Fully-Expanded YAML (self-contained, no `from:` inheritance)

Generate YAML with this structure. All scaffolding and states are inline — there is no `from:` field. (Rationale: matches `create-eval-from-issues` and 40/42 existing loops.)

```yaml
name: "verify-<issue-id-lower>-<title-slug>"
category: verification
description: |
  Verification loop for <ISSUE-ID>: <issue title>.
  Walks each acceptance criterion in order; fails fast on any criterion that fails.
  Generated by /ll:verify-issue-loop on <YYYY-MM-DD>.
initial: verify-criterion-1
max_steps: 20
timeout: 1800

states:

  verify-criterion-1:
    action: >
      Verify acceptance criterion 1 for <ISSUE-ID>: <criterion-1 text>.
      Inspect the implementation, run any commands needed, and gather concrete
      evidence about whether the criterion holds. Report what you observed.
    action_type: prompt
    timeout: 300
    evaluate:
      type: llm_structured
      prompt: >
        Does the implementation satisfy criterion 1 of <ISSUE-ID>?

        Criterion: <criterion-1 text>

        Answer YES only if the evidence clearly shows the criterion is met.
        Answer NO if the criterion is not met or evidence is missing/ambiguous.
        Provide a one-sentence reason citing the observed evidence.
    on_yes: verify-criterion-2
    on_no: failed

  verify-criterion-2:
    action: >
      Verify acceptance criterion 2 for <ISSUE-ID>: <criterion-2 text>.
      Inspect the implementation, run any commands needed, and gather concrete
      evidence about whether the criterion holds. Report what you observed.
    action_type: prompt
    timeout: 300
    evaluate:
      type: llm_structured
      prompt: >
        Does the implementation satisfy criterion 2 of <ISSUE-ID>?

        Criterion: <criterion-2 text>

        Answer YES only if the evidence clearly shows the criterion is met.
        Answer NO if the criterion is not met or evidence is missing/ambiguous.
        Provide a one-sentence reason citing the observed evidence.
    on_yes: done   # or verify-criterion-3 if more criteria remain
    on_no: failed

  # ... repeat verify-criterion-N for each remaining criterion ...

  done:
    terminal: true

  failed:
    terminal: true
```

**Important rules:**

- Exactly N `verify-criterion-N` states for N criteria.
- The final verify state's `on_yes` is `done` (not `verify-criterion-<N+1>`).
- Every verify state's `on_no` is `failed`.
- Both `done` and `failed` have `terminal: true`.
- No `discover` or `advance` states — this is single-issue scope.
- No `check_invariants`, `check_stall`, or `check_concrete` — those belong in code-quality loops, not verification loops.

## Step 6: Write and Validate

```bash
mkdir -p .loops/
```

Use the Write tool to write the YAML to `.loops/<loop-name>.yaml`.

Then validate:

```bash
ll-loop validate <loop-name>
```

Report the validation result. If validation fails, show the errors and explain what needs to be fixed.

## Output Format

After completion, output:

```
✓ Verification loop generated: .loops/verify-<issue-id-lower>-<title-slug>.yaml

Issue: <ISSUE-ID>: <title>
Criteria verified: N
States: verify-criterion-1 → ... → verify-criterion-N → done (with failed terminal on any miss)

Validation: PASS / FAIL
  [validation output if FAIL]

To run:
  ll-loop run verify-<issue-id-lower>-<title-slug>
```

## Example

```
/ll:verify-issue-loop FEAT-919
→ Reads acceptance criteria from .issues/features/P3-FEAT-919-*.md
→ Writes: .loops/verify-feat-919-add-json-schema-generation.yaml
→ Loop: initial: verify-criterion-1, N states ending in done (or failed)
→ Validation: PASS
```
