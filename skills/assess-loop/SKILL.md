---
description: |
  Use when the user asks to assess loop effectiveness, audit loop goal achievement, check whether a loop actually mutated expected artifacts, detect phantom success, or evaluate loop quality before production use.
argument-hint: "[loop-name] [--tail N] [--no-rubric-audit] [--skip-issue-creation] [--auto]"
model: sonnet
allowed-tools:
  - Bash(ll-loop:*, ll-issues:*, git:*)
  - Read
  - Glob
  - Grep
  - Write
  - AskUserQuestion
arguments:
  - name: loop_name
    description: Loop name to assess (optional — auto-selects most recent if omitted)
    required: false
  - name: tail
    description: Limit history events analyzed to the N most recent (default 200)
    required: false
  - name: no_rubric_audit
    description: Skip the LLM rubric-vs-description pass (cost gate)
    required: false
  - name: skip_issue_creation
    description: Skip issue creation entirely and exit cleanly after presenting proposals
    required: false
  - name: auto
    description: Non-interactive mode; suppress all AskUserQuestion calls and default to no for issue creation (implies --skip-issue-creation). Also activates when --dangerously-skip-permissions is in effect.
    required: false
---

# Assess Loop

Audit whether a configured loop's execution actually achieved its stated goal — checking artifact mutations, threshold contracts, structural defects (phantom convergence, degenerate gates, rubric drift, sub-loop verdict laundering), and producing ranked improvement proposals.

---

## Step 1: Resolve Loop Name

If `loop_name` argument is provided, resolve the most recent run folder:

```bash
ls -d .loops/.history/*-<loop_name>/ 2>/dev/null | sort | tail -1
```

- If empty: report "No archived runs found for `<loop_name>`." and stop.
- Otherwise: extract `LATEST_RUN_ID` (the compact timestamp prefix, e.g. `2026-03-19T204149`).

Otherwise, enumerate candidate loops:

```bash
ll-loop list --running --json
```

Filter to `status` one of `"running"`, `"interrupted"`, `"failed"`, `"timed_out"`, `"awaiting_continuation"`. Sort by `updated_at` descending.

Note: `ll-loop list --running --json` output does **not** include `instance_id` — entries with the same `loop_name` are indistinguishable at this level.

- **Zero candidates**: Report "No interrupted or running loops found. Specify a loop name explicitly." and stop.
- **One candidate**: Select automatically and report.
- **Two or more candidates with distinct `loop_name` values**: Use `AskUserQuestion` to let the user pick:
  ```
  Multiple loops found. Select one to assess:

  [1] <loop_name_1> — <status> — last updated <updated_at>
  [2] <loop_name_2> — <status> — last updated <updated_at>
  ...
  ```
- **Two or more candidates sharing the same `loop_name`** (multiple instances): follow up with `ll-loop status <loop_name> --json` to retrieve per-instance detail (`instance_id`, `pid`, `log_file`), then use `AskUserQuestion` to present instance-level disambiguation:
  ```
  Multiple instances of '<loop_name>' found. Select one to assess:

  [1] <instance_id_1> — <status> — PID <pid> — last updated <updated_at>
  [2] <instance_id_2> — <status> — PID <pid> — last updated <updated_at>
  ...
  ```

---

## Step 2: Load Loop Definition and History

Load the fully-materialized FSM:

```bash
ll-loop show <loop_name> --resolved --json
```

This returns `FSMLoop.to_dict()` JSON with always-present keys `name`, `initial`, `states`, and conditionally `description`, `context` (threshold keys live here), `max_iterations`, `parameters`, `commands`.

Load the event history:

```bash
ll-loop history <loop_name> [<LATEST_RUN_ID>] --json --tail <tail_arg_or_200>
```

If either command fails, report the error and stop.

---

## Step 3: Extract Success Contract

From the FSM `context` flat dict, scan for threshold keys:

- `target_pass_rate`, `pass_threshold`, `quality_threshold`, `readiness_threshold`
- `outcome_threshold`, `reward_target`, `target_score`, `min_per_category`, `adversarial_cap`

Also scan each state's `action` text and `evaluate.prompt` text for `${context.<key>}` interpolation patterns to detect threshold references embedded in prompts.

Build the **success contract**: list of `{key, value, source}` entries where `source` is `"context"`, `"action"`, or `"evaluate.prompt"`.

If no contract entries are found, note: "No threshold contract detected — loop uses implicit success criteria."

---

## Step 4: Inspect Artifacts

Identify artifact paths the loop touches. Look in:

1. `context.prompt_file`, `context.system_file`, `context.output_file` and similar path-like context keys
2. State `action` text for file path patterns (`prompts/`, `data/`, `.issues/`, `image.svg`, `manifest.json`, `examples.json`)

For each identified artifact path, check mutation evidence:

```bash
# Check if file was modified in recent git history
git log --oneline -5 -- <artifact_path>

# Check current diff
git diff HEAD -- <artifact_path>
```

For issue-based loops, inspect frontmatter:

```bash
ll-issues show <id> --json
```

Also check in-memory captures in `.loops/.history/<run_id>-<loop_name>/state.json` under `captured` dict (schema: `{state_name: {output, stderr, exit_code, duration_ms}}`).

---

## Step 5: Phase 1 — Fault Signals

Re-use the history loaded in Step 2 to identify fault signals using the **fault-signal subset** of `/ll:analyze-loop` Step 3 (the BUG-class anomalies that broke the run). Note: `/ll:analyze-loop` Step 3 also classifies effectiveness signals (iter-1 convergence without apply, degenerate gate, stub action) — those are **out of scope for assess-loop Phase 1**, since this step only synthesizes fault evidence into the scorecard. Include the verbatim fault signal list in the scorecard output.

Key signals to flag (fault subset only):
- Action failures (`exit_code != 0`, non-intentional)
- SIGKILL / FATAL_ERROR termination
- Retry floods
- Evaluate failures
- Sub-loop verdict discarded

---

## Step 6: Goal-vs-Outcome Scorecard

Determine the verdict using the terminal state from `loop_complete` event (`terminated_by`) and the artifact/contract evidence:

| Verdict | Condition |
|---|---|
| `met` | Terminal reached AND all threshold contracts verified AND all expected artifact mutations occurred |
| `phantom` | Terminal reached AND (artifacts unchanged OR threshold unverified — only model self-reported via `llm_structured` evaluator) |
| `partial` | Terminal reached AND some but not all contracts satisfied |
| `degraded` | Loop completed but metric trended downward vs baseline captured in `state.json` |

Output the structured scorecard block:

```
### Goal-vs-Outcome Scorecard

**Goal**: "<loop description or (no description provided)>"
**Contract**: <threshold keys and values, or "none detected">
**Artifacts checked**: <list of paths and mutation status>
**Phase 1 signals**: <fault signal count from Step 5, or "none">
**Verdict**: `<met | phantom | partial | degraded>`

**Rationale**: <one paragraph explaining the verdict>
```

---

## Step 7: Rubric-vs-Description Audit

**Skip this step if `--no-rubric-audit` flag is set.**

For each state with `evaluate.type: llm_structured`, send a judge call comparing:
- The loop's top-level `description` text
- The evaluator's `prompt` text

Judge prompt (single call per evaluator):

> "Does this evaluator prompt operationalize the loop's stated goal? Loop goal: '<description>'. Evaluator prompt: '<evaluate.prompt>'. Answer YES if the evaluator directly measures progress toward the stated goal, NO if it measures something unrelated or misaligned."

Flag as **rubric drift** if the judge answers NO. Include the evaluator's state name and a brief explanation.

Pattern reference: `outer-loop-eval.yaml:generate_report` state uses `evaluate.type: llm_structured` with `min_confidence: 0.7`.

---

## Step 8: Sub-Loop Verdict Laundering Check

For each state where `loop:` is set (sub-loop invocation), read `on_yes` and `on_no` from the FSM JSON output:

```
state.on_yes  # child reached a terminal state
state.on_no   # child did not reach terminal
```

**Laundering defect**: `state.on_yes == state.on_no` (after any `${context.*}` interpolation). This means the parent loop treats child success and child failure identically — the child verdict is silently discarded.

Flag each laundering defect with:
- State name
- Child loop name (`loop:` value)
- The shared next state (both `on_yes` and `on_no` point to)

---

## Step 9: Ranked Improvement Proposals

Emit ranked proposals from the scorecard, rubric audit, and fault signals. Order: contract-level > rubric-level > state-level > structural.

For each proposal, include a concrete YAML diff where possible:

```
### Improvement Proposals

1. [contract] Add artifact mutation verification for `prompts/test.md`
   Rationale: loop reached terminal without evidence of file mutation — possible phantom success

   YAML diff:
   states:
     optimize:
   +   capture: optimized_prompt
   +   capture_file: "${context.prompt_file}"

2. [rubric] Align evaluator prompt with loop goal in state `refine_answers`
   Rationale: evaluate.prompt checks Python syntax; description says "improve answer quality"

3. [state] Add `on_error` routing to state `check_quality`
   Rationale: shell evaluator with no on_error silently routes failed runs to on_no
```

### Deduplication

Before presenting proposals, check for existing issues:

```bash
grep -rl "<loop_name>" .issues/bugs/ .issues/enhancements/ .issues/features/ 2>/dev/null
```

Mark matches as DUPLICATE. Present only NEW proposals.

**Skip this step if `--skip-issue-creation` or `--auto` flag is set (or if `--dangerously-skip-permissions` is active).** Print: `ℹ️ Issue creation skipped (--skip-issue-creation / --auto)` and stop.

Use `AskUserQuestion` to ask:

```
Create issues for these <N> proposals? [Y/n/select]

  Y — create all
  n — cancel
  select — choose which to create (comma-separated numbers)
```

For each approved proposal, allocate an ID (`ll-issues next-id`) and write the issue file to the appropriate category dir. Stage with `git add .issues/`.

---

## Final Report

```
Assessment complete for loop: <loop_name>

Verdict: `<met | phantom | partial | degraded>`
Rubric audit: <N evaluators checked, M flagged — or "skipped (--no-rubric-audit)">
Laundering check: <N sub-loop states checked, M flagged — or "no sub-loop states">
Issues created: <N>
```

---

## Usage Examples

```bash
# Assess most recent interrupted loop
/ll:assess-loop

# Assess a specific loop
/ll:assess-loop apo-textgrad

# Limit history to 100 events
/ll:assess-loop apo-textgrad --tail 100

# Skip LLM rubric audit (cost gate)
/ll:assess-loop apo-textgrad --no-rubric-audit
```
