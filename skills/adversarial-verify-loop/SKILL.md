---
name: adversarial-verify-loop
description: Use when asked to generate an FSM adversarial verification loop YAML that tries to break a feature via boundary values, malformed inputs, and failure modes.
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
  short-description: Generate an FSM adversarial loop that tries to break a feature via probes
---

# Adversarial Verify Loop

Generate a ready-to-run FSM adversarial verification loop YAML from a single issue ID. The loop tries to *break* the feature via three distinct probe classes — boundary values, malformed/hostile inputs, and failure modes — rather than confirming it works.

This is the adversarial counterpart to `/ll:verify-issue-loop`. Where `verify-issue-loop` asks "does the criterion hold?", `adversarial-verify-loop` asks "can we break it?". **Verdict rule: attempting fewer than 3 genuine probe classes is itself a FAIL**, even if every attempted probe passed.

## Overview

This skill:
1. Resolves the issue ID to a file path using `ll-issues show <ID> --json`
2. Reads the issue file to extract the title and `## Acceptance Criteria` section
3. Synthesizes three probe states — `probe-boundary`, `probe-malformed-hostile`, `probe-failure-mode` — each with an `llm_structured` evaluator
4. Wires routing: each probe's `on_yes` passes to the next probe, `on_no` routes to `failed_with_finding`; final probe routes to `count_probes`
5. Adds a `count_probes` shell state that verifies at least 3 probe-result files were written (filesystem-derived, not LLM-reported)
6. Writes the file to `.loops/adversarial-<ISSUE-ID>-<slug>.yaml`
7. Validates it with `ll-loop validate` and reports the result

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
  echo "Usage: /ll:adversarial-verify-loop FEAT-919"
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

## Step 2: Extract Title and Acceptance Criteria

Read the resolved issue file directly and extract:

1. **Title** — from the YAML frontmatter `title:` field or the first `# ISSUE-NNN:` heading
2. **Acceptance Criteria section** — the `## Acceptance Criteria` section body

Parse the criteria into an ordered list. Accept any bullet style:
- `- [ ] ...` / `- [x] ...` (strip marker)
- `- ...` / `* ...` (plain bullets)
- `1. ...` / `2. ...` (numbered)

The criteria text is used to focus probe prompts on what the feature is supposed to do.

**If the Acceptance Criteria section is missing or empty**, use the issue title and Summary section as the feature description. Do not halt — fall back to the title as the probe target.

## Step 3: Synthesize Probe-State Prompts

Generate three fixed probe states. Each state's `action` prompt instructs the running agent to attempt concrete, hands-on probing — not theorizing. Each probe must write a result file to `${context.run_dir}`.

### probe-boundary

Tell the agent to probe boundary and extreme values.

**Action prompt pattern:**
> "Probe boundary conditions for <ISSUE-ID>: <issue title>.
>
> Try to break the feature using boundary and extreme values: empty inputs, maximum sizes,
> off-by-one values, Unicode edge cases, very large payloads, zero/negative numbers.
> Attempt at least two distinct boundary probes. For each probe, run a real command or
> exercise the feature concretely — do not just theorize.
>
> After probing, write a JSON result to ${context.run_dir}/probe-boundary.json:
>   {"probe_class": "boundary", "probes_attempted": <N>, "break_found": <true|false>, "finding": "<what happened>"}
>
> Report what you tried and what you observed."

**Evaluator prompt pattern:**
> "Did the boundary probe of <ISSUE-ID> survive without exposing a genuine break?
>
> A genuine break is a reproducible bug, crash, error, or wrong output caused by the probe.
> A probe that did NOT break the feature (the feature handled it correctly) is a PASS.
>
> Answer YES if the feature survived all boundary probes (no genuine break found).
> Answer NO if the probe found a genuine break — a reproducible failure, crash, or wrong output.
> Provide a one-sentence reason citing what was tried and what was observed."

### probe-malformed-hostile

Tell the agent to probe malformed and hostile inputs.

**Action prompt pattern:**
> "Probe malformed and hostile inputs for <ISSUE-ID>: <issue title>.
>
> Try to break the feature using: wrong types, injection-shaped strings (shell, path-traversal),
> partial or incomplete state, concurrent or duplicate invocations, null/None values,
> unexpected encoding, negative indices.
> Attempt at least two distinct malformed/hostile probes. Run real commands — do not theorize.
>
> After probing, write a JSON result to ${context.run_dir}/probe-malformed.json:
>   {"probe_class": "malformed_hostile", "probes_attempted": <N>, "break_found": <true|false>, "finding": "<what happened>"}
>
> Report what you tried and what you observed."

**Evaluator prompt pattern:**
> "Did the malformed/hostile-input probe of <ISSUE-ID> survive without exposing a genuine break?
>
> Answer YES if the feature survived (handled all malformed/hostile inputs correctly or gracefully).
> Answer NO if a probe found a genuine break — a reproducible failure, crash, or wrong output.
> Provide a one-sentence reason citing what was tried and what was observed."

### probe-failure-mode

Tell the agent to probe known failure modes.

**Action prompt pattern:**
> "Probe known failure modes for <ISSUE-ID>: <issue title>.
>
> Try to break the feature by simulating failure conditions: missing config files,
> absent required files or directories, interrupted or partial runs, corrupted state,
> unavailable dependencies, missing environment variables, permission errors.
> Attempt at least two distinct failure-mode probes. Run real commands — do not theorize.
>
> After probing, write a JSON result to ${context.run_dir}/probe-failure.json:
>   {"probe_class": "failure_mode", "probes_attempted": <N>, "break_found": <true|false>, "finding": "<what happened>"}
>
> Report what you tried and what you observed."

**Evaluator prompt pattern:**
> "Did the failure-mode probe of <ISSUE-ID> survive without exposing a genuine break?
>
> Answer YES if the feature survived (handled failure modes correctly or raised clean errors).
> Answer NO if a probe found a genuine break — a reproducible failure, crash, or wrong output.
> Provide a one-sentence reason citing what was tried and what was observed."

## Step 4: Wire Transitions

The three probe states chain linearly on `on_yes`, with `on_no` routing to the shared `failed_with_finding` terminal:

```
probe-boundary --on_yes--> probe-malformed-hostile --on_yes--> probe-failure-mode --on_yes--> count_probes --on_yes--> done
     |                              |                                   |                          |
  on_no                          on_no                              on_no                       on_no
     v                              v                                   v                          v
failed_with_finding        failed_with_finding              failed_with_finding             failed_too_few
```

`done`, `failed_with_finding`, and `failed_too_few` are all `terminal: true`.

`initial: probe-boundary`.

### count_probes shell state

After all three probe states pass, `count_probes` uses a shell action to count the probe result files written during the run. This gate is filesystem-derived — the LLM's claim about having probed is irrelevant; what counts is whether the files exist.

```yaml
count_probes:
  # Non-LLM gate: verifies that probe result files were physically written.
  # File count is filesystem-derived (shell wc -l), not LLM-reported.
  # Output ONLY the count — required by output_numeric evaluator.
  action_type: shell
  action: |
    ls "${context.run_dir}"/probe-*.json 2>/dev/null | wc -l | tr -d ' '
  evaluate:
    type: output_numeric
    operator: ge
    target: 3
  on_yes: done
  on_no: failed_too_few
```

## Step 5: Generate Adversarial YAML

### Slug Generation

```bash
ISSUE_LOWER=$(echo "$ISSUE_ID" | tr '[:upper:]' '[:lower:]')
TITLE_SLUG=$(echo "$ISSUE_TITLE" | tr '[:upper:]' '[:lower:]' | tr -cs 'a-z0-9' '-' | sed 's/^-//;s/-$//')
LOOP_NAME="adversarial-${ISSUE_LOWER}-${TITLE_SLUG}"
OUTPUT_FILE=".loops/${LOOP_NAME}.yaml"
```

If the issue title cannot be extracted cleanly, fall back to `LOOP_NAME="adversarial-${ISSUE_LOWER}"`.

### Fully-Expanded YAML

Generate YAML with this structure. All scaffolding and states are inline — no `from:` inheritance.

```yaml
name: "adversarial-<issue-id-lower>-<title-slug>"
category: verification
description: |
  Adversarial verification loop for <ISSUE-ID>: <issue title>.
  Tries to break the feature via boundary values, malformed/hostile inputs, and failure modes.
  FAIL fires when fewer than 3 probe classes are genuinely attempted (count_probes gate).
  Generated by /ll:adversarial-verify-loop on <YYYY-MM-DD>.
initial: probe-boundary
max_iterations: 20
timeout: 2700

states:

  probe-boundary:
    action: >
      Probe boundary conditions for <ISSUE-ID>: <issue title>.

      Try to break the feature using boundary and extreme values: empty inputs, maximum sizes,
      off-by-one values, Unicode edge cases, very large payloads, zero/negative numbers.
      Attempt at least two distinct boundary probes. For each probe, run a real command or
      exercise the feature concretely — do not just theorize.

      After probing, write a JSON result to ${context.run_dir}/probe-boundary.json:
        {"probe_class": "boundary", "probes_attempted": <N>, "break_found": <true|false>, "finding": "<what happened>"}

      Report what you tried and what you observed.
    action_type: prompt
    timeout: 300
    evaluate:
      type: llm_structured
      prompt: >
        Did the boundary probe of <ISSUE-ID> survive without exposing a genuine break?

        A genuine break is a reproducible bug, crash, error, or wrong output caused by the probe.
        A probe that did NOT break the feature (the feature handled it correctly) is a PASS.

        Answer YES if the feature survived all boundary probes (no genuine break found).
        Answer NO if the probe found a genuine break — a reproducible failure, crash, or wrong output.
        Provide a one-sentence reason citing what was tried and what was observed.
    on_yes: probe-malformed-hostile
    on_no: failed_with_finding

  probe-malformed-hostile:
    action: >
      Probe malformed and hostile inputs for <ISSUE-ID>: <issue title>.

      Try to break the feature using: wrong types, injection-shaped strings (shell, path-traversal),
      partial or incomplete state, concurrent or duplicate invocations, null/None values,
      unexpected encoding, negative indices.
      Attempt at least two distinct malformed/hostile probes. Run real commands — do not theorize.

      After probing, write a JSON result to ${context.run_dir}/probe-malformed.json:
        {"probe_class": "malformed_hostile", "probes_attempted": <N>, "break_found": <true|false>, "finding": "<what happened>"}

      Report what you tried and what you observed.
    action_type: prompt
    timeout: 300
    evaluate:
      type: llm_structured
      prompt: >
        Did the malformed/hostile-input probe of <ISSUE-ID> survive without exposing a genuine break?

        Answer YES if the feature survived (handled all malformed/hostile inputs correctly or gracefully).
        Answer NO if a probe found a genuine break — a reproducible failure, crash, or wrong output.
        Provide a one-sentence reason citing what was tried and what was observed.
    on_yes: probe-failure-mode
    on_no: failed_with_finding

  probe-failure-mode:
    action: >
      Probe known failure modes for <ISSUE-ID>: <issue title>.

      Try to break the feature by simulating failure conditions: missing config files,
      absent required files or directories, interrupted or partial runs, corrupted state,
      unavailable dependencies, missing environment variables, permission errors.
      Attempt at least two distinct failure-mode probes. Run real commands — do not theorize.

      After probing, write a JSON result to ${context.run_dir}/probe-failure.json:
        {"probe_class": "failure_mode", "probes_attempted": <N>, "break_found": <true|false>, "finding": "<what happened>"}

      Report what you tried and what you observed.
    action_type: prompt
    timeout: 300
    evaluate:
      type: llm_structured
      prompt: >
        Did the failure-mode probe of <ISSUE-ID> survive without exposing a genuine break?

        Answer YES if the feature survived (handled failure modes correctly or raised clean errors).
        Answer NO if a probe found a genuine break — a reproducible failure, crash, or wrong output.
        Provide a one-sentence reason citing what was tried and what was observed.
    on_yes: count_probes
    on_no: failed_with_finding

  count_probes:
    # Non-LLM gate: verifies that probe result files were physically written.
    # File count is filesystem-derived (shell wc -l), not LLM-reported.
    # Output ONLY the count — required by output_numeric evaluator.
    action_type: shell
    action: |
      ls "${context.run_dir}"/probe-*.json 2>/dev/null | wc -l | tr -d ' '
    evaluate:
      type: output_numeric
      operator: ge
      target: 3
    on_yes: done
    on_no: failed_too_few

  done:
    terminal: true

  failed_with_finding:
    terminal: true

  failed_too_few:
    terminal: true
```

**Important rules:**

- Exactly 3 probe states: `probe-boundary`, `probe-malformed-hostile`, `probe-failure-mode`.
- Each probe state is `action_type: prompt` with an `llm_structured` evaluator.
- `probe-failure-mode`'s `on_yes` routes to `count_probes`, not `done`.
- `count_probes` is `action_type: shell` with an `output_numeric` evaluator (`operator: ge`, `target: 3`).
- Three terminal states: `done`, `failed_with_finding`, `failed_too_few`.

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
✓ Adversarial verification loop generated: .loops/adversarial-<issue-id-lower>-<title-slug>.yaml

Issue: <ISSUE-ID>: <title>
Probe classes: probe-boundary → probe-malformed-hostile → probe-failure-mode → count_probes
Terminals: done (all probes passed + count ≥ 3) | failed_with_finding (break found) | failed_too_few (< 3 probes attempted)

Validation: PASS / FAIL
  [validation output if FAIL]

To run:
  ll-loop run adversarial-<issue-id-lower>-<title-slug>
```

## Example

```
/ll:adversarial-verify-loop FEAT-919
→ Reads issue from .issues/features/P3-FEAT-919-*.md
→ Writes: .loops/adversarial-feat-919-add-json-schema-generation.yaml
→ Loop: initial: probe-boundary, 3 probe states + count_probes → done | failed_with_finding | failed_too_few
→ Validation: PASS
```

**See also:** `/ll:verify-issue-loop` (confirmatory counterpart), `/ll:create-loop`, `/ll:go-no-go`
