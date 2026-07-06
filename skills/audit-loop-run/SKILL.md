---
name: audit-loop-run
description: Use when asked to assess loop effectiveness, audit goal achievement, or detect phantom success.
disable-model-invocation: true
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
    description: Limit history events analyzed to the N most recent (default: all events; auto-scaled)
    required: false
  - name: no_rubric_audit
    description: Skip the LLM rubric-vs-description pass (cost gate)
    required: false
  - name: skip_issue_creation
    description: Skip issue creation entirely and exit cleanly after presenting proposals
    required: false
  - name: auto
    description: Non-interactive mode; suppress all AskUserQuestion calls and default to no for issue creation (implies --skip-issue-creation). Also activates when LL_NON_INTERACTIVE or DANGEROUSLY_SKIP_PERMISSIONS env vars are set, or when --dangerously-skip-permissions is in effect.
    required: false
metadata:
  short-description: Use when asked to assess loop effectiveness, audit goal achievement, or detect p
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
- **Two or more candidates sharing the same `loop_name`** (multiple instances): follow up with `ll-loop status <loop_name> --json` to retrieve per-instance detail (`instance_id`, `pid`, `log_file`, `events_file`), then use `AskUserQuestion` to present instance-level disambiguation:
  ```
  Multiple instances of '<loop_name>' found. Select one to assess:

  [1] <instance_id_1> — <status> — PID <pid> — last updated <updated_at>
  [2] <instance_id_2> — <status> — PID <pid> — last updated <updated_at>
  ...
  ```

---

## Step 2: Load Loop Definition and History

### Pre-flight: verify the run actually exists (hard gate)

Before loading or analyzing anything, confirm the run artifacts exist and are
non-empty. This applies to **every** path that reaches this step — auto-resolved
runs, directly-supplied run IDs/folders, and running-loop selections alike.

```bash
RUN_DIR=".loops/.history/<LATEST_RUN_ID>-<loop_name>"
if [ ! -s "$RUN_DIR/events.jsonl" ] || [ ! -f "$RUN_DIR/state.json" ]; then
  echo "MISSING_RUN"
fi
```

- If the command prints `MISSING_RUN` (or `RUN_DIR` does not exist): report
  `Run '<LATEST_RUN_ID>-<loop_name>' not found or empty — refusing to audit.`
  and **stop**. Do **not** emit a verdict, state-transition trace, captured
  outputs, improvement proposals, or any other section. An audit of a run whose
  `events.jsonl`/`state.json` cannot be read is a fabrication, not an audit —
  the only honest output is the refusal above.
- Never reconstruct, infer, or assume a trace from the loop's FSM definition
  alone. Every concrete claim in the report (trace, exit codes, captured
  outputs, timings) MUST be backed by a line actually read from
  `events.jsonl`/`state.json`. If a tool call returns empty or errors, treat
  that as absence of evidence, not an invitation to confabulate.

Only once the gate passes, proceed.

Load the fully-materialized FSM:

```bash
ll-loop show <loop_name> --resolved --json
```

This returns `FSMLoop.to_dict()` JSON with always-present keys `name`, `initial`, `states`, and conditionally `description`, `context` (threshold keys live here), `max_steps`, `parameters`, `commands`.

Load the event history. If the user supplied `--tail N`, use that directly. Otherwise, auto-scale to load all events (`--tail 0`):

```bash
# Derive total event count from the archive (line count = event count)
TOTAL_EVENTS=$(wc -l .loops/.history/<LATEST_RUN_ID>-<loop_name>/events.jsonl | awk '{print $1}')

# Use user-supplied tail if provided, else 0 (all events)
EFFECTIVE_TAIL=<tail_arg_or_0>

ll-loop history <loop_name> [<LATEST_RUN_ID>] --json --tail ${EFFECTIVE_TAIL}
```

If `EFFECTIVE_TAIL` is greater than 0 and less than `TOTAL_EVENTS`, emit a truncation notice before proceeding:

```
ℹ️ Loaded last <EFFECTIVE_TAIL> of <TOTAL_EVENTS> events — fault analysis covers a partial window.
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

1. `context.prompt_file`, `context.system_file`, `context.output_file`, `context.run_dir` and similar path-like context keys
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

Also check in-memory captures in `.loops/.history/<run_id>-<loop_name>/state.json` under `captured` dict (schema: `{capture_variable_name: {output, stderr, exit_code, duration_ms}}` — keys are capture *variable names* from `capture:` declarations, not state names). For step-level capture output in `events.jsonl`, read `action_complete.output_preview`.

Quote every `.output` value verbatim when citing it; do not infer `"sentinel"` or `"placeholder"` labels — the interpolation engine emits no numeric markers (only `\x00ESCAPED\x00`, an internal placeholder that is never present in captured output).

---

## Step 5: Phase 1 — Fault Signals

Re-use the history loaded in Step 2 to identify fault signals using the **fault-signal subset** of `/ll:debug-loop-run` Step 3 (the BUG-class anomalies that broke the run). Note: `/ll:debug-loop-run` Step 3 also classifies effectiveness signals (iter-1 convergence without apply, degenerate gate, stub action) — those are **out of scope for audit-loop-run Phase 1**, since this step only synthesizes fault evidence into the scorecard. Include the verbatim fault signal list in the scorecard output.

Key signals to flag (fault subset only):
- Action failures (`exit_code != 0`, non-intentional)
- SIGKILL / FATAL_ERROR termination
- Evaluate error termination (`evaluate.verdict == "error"` on the last evaluate before `loop_complete`) — single-occurrence terminating evaluator error (`eval_error_termination`); distinct from "Evaluate failures" which covers `verdict == "fail"` 3+ times
- Retry floods
- Evaluate failures (`verdict == "fail"`, 3+ occurrences on the same state)
- Sub-loop verdict discarded
- Throttle hard stop / hard transition (`throttle_stop` = loop halted; `throttle_hard` = loop redirected via `on_throttle_hard`)
- Over-escaped shell / PID corruption: when a captured `.output` value matches `^\d{2,7}\b` (a bare PID prefix) *and* the action text for that state contains `$$(` or `$$[A-Za-z_]` (same pattern as `_OVERESCAPED_SHELL_RE` in `validation.py:121`), flag as **over-escaped-shell-pid-corruption** (MR-9) and recommend *removing* the extra `$`, never adding more escaping.

---

## Step 5.5: Shallow-Iteration Check

Using the history loaded in Step 2 and the artifact evidence from Step 4, run the shallow-iteration heuristic:

**1. Count tool calls**: Count the number of `action_complete` events in the loaded history. Call this `TOOL_CALL_COUNT`.

**2. Identify auxiliary mutations**: Before trusting `git diff HEAD`, check whether the primary artifact path (or the run's working directory, e.g. `context.run_dir`) is gitignored:

```bash
git check-ignore <primary_path>
```

- **Not ignored** (exit code 1, or no primary path is under version control at all): use the `git diff HEAD` evidence collected in Step 4 as before — list all files that were created or modified and are **not** in the primary artifact path set (the paths identified in Step 4: `context.prompt_file`, `context.output_file`, `context.run_dir`, and similar path-like context keys). Call this count `AUX_MUTATION_COUNT`.
- **Ignored** (exit code 0): `git diff HEAD` is structurally blind to this path, so a `git`-derived `AUX_MUTATION_COUNT` of `0` cannot be trusted. Fall back to a filesystem mutation scan scoped to the run's working directory, anchored on the run-start timestamp (`events[0].ts` from the history loaded in Step 2):

  ```bash
  # GNU find (Linux) — accepts an ISO timestamp string directly
  find <run_dir> -type f -newermt "<run_start_ts>"

  # BSD find (macOS default) — -newermt is unsupported; use a touched marker file instead
  touch -d "<run_start_ts>" /tmp/run_start_marker && find <run_dir> -type f -newer /tmp/run_start_marker
  ```

  Count the resulting file list as `AUX_MUTATION_COUNT`.
- **Neither signal available** (e.g. the run directory has already been cleaned up): do not default to `0`. Report `AUX_MUTATION_COUNT` as `unknown` and route the heuristic result to `unknown` in step 4 below (skip the warning rather than asserting a false positive).

**3. Check for diff_stall corroboration**: Scan `evaluate` events in the history. For each, check whether the resolved FSM (loaded in Step 2) has `evaluate.type == "diff_stall"` for that state and the recorded `verdict` is `"stall"` or `"no"`. Call this `DIFF_STALL_PRESENT` (true/false).

**4. Apply threshold** (default threshold: 30):

```
IF AUX_MUTATION_COUNT == "unknown":
  result = "unknown"          # no git or filesystem evidence available — skip, don't guess
ELIF TOOL_CALL_COUNT > 30 AND AUX_MUTATION_COUNT == 0:
  IF DIFF_STALL_PRESENT:
    result = "corroborated"   # both heuristic and diff_stall agree
  ELSE:
    result = "warning"        # heuristic alone
ELSE:
  result = "clear"
```

The default threshold of 30 `action_complete` events is intentionally conservative — most well-structured loops either produce auxiliary artifacts or converge within this budget. Loops that burn more than 30 iterations without creating helper structure are iterating without building.

**5. Emit finding** when result is `"warning"` or `"corroborated"`:

```
⚠ Shallow-iteration: <TOOL_CALL_COUNT> action_complete events with no auxiliary file mutations
  outside the primary artifact path (<primary_paths>).
  [Corroborated by diff_stall evaluator verdict in state '<state_name>'.]
  Remediation: add intermediate artifact-write states; break monolithic iteration into
  smaller sub-tasks that each produce a named helper file.
```

Pass `result` and `TOOL_CALL_COUNT` to the scorecard in Step 6.

---

## Step 5.6: Budget-Utilization Guard

Before accepting budget-exhaustion as a root cause, compute the budget utilization ratio:

```bash
STEPS_CONSUMED=$(jq '[.[] | select(.event == "loop_complete")] | last | .iterations // 0' \
  .loops/.history/<LATEST_RUN_ID>-<loop_name>/events.jsonl)
MAX_STEPS=$(ll-loop show <loop_name> --resolved --json | jq '.max_steps // .max_iterations // 100')
```

If `STEPS_CONSUMED / MAX_STEPS < 0.3`, reject budget-exhaustion as the primary root cause — the loop consumed less than 30% of its budget, so it did not run out of steps.

Note: there is no `steps_consumed` field in `state.json`; derive `STEPS_CONSUMED` from `loop_complete.iterations` in `events.jsonl`.

---

## Step 6: Goal-vs-Outcome Scorecard

### Step 6a: Summary Cross-Check

Before determining the verdict, check whether the run wrote a `summary.json` to its run directory:

```bash
SUMMARY_FILE=".loops/.history/<LATEST_RUN_ID>-<loop_name>/summary.json"
```

If the file exists, extract the claimed-outcome counters (`closed`, `implemented`, `failed`, `decomposed`). The success token varies by loop — `auto-refine-and-implement` / `sprint-refine-and-implement` emit `closed` (verified terminal closure, ENH-2385), while `rn-implement` / `general-task` emit `implemented`. Use whichever success counter the loop reports as the **claimed-success signal**:

- **claimed_success > 0**: `closed > 0` / `implemented > 0` (or any equivalent success token) is present
- **claimed_success == 0**: the success counter is `0` (or key absent) — the run honestly reports it produced nothing

**ENH-2404 — parked-issue visibility (`auto-refine-and-implement` / `autodev`)**: if present, also read `skipped_breakdown` (an object keyed by reason, e.g. `{"decomposed": 1, "refine_failed": 0, "low_readiness": 4}`), `gate_blocked` (issues parked by the learning-gate, ENH-2402 — previously invisible here), and `parked_rate` (`(skipped + not_closed + gate_blocked) / input_size`). `parked_rate` is a visibility signal, not a pass/fail gate — interpret it via `skipped_breakdown`: a high rate dominated by `decomposed` is healthy (the run is legitimately fanning out into children), while one dominated by `refine_failed` / `low_readiness` is a genuine quality signal worth flagging in the report. These three keys are additive; older `summary.json` files (pre-ENH-2404) will lack them — treat their absence as "no breakdown data available" rather than an error, and fall back to the plain `skipped` count.

### Step 6b: Verdict Table

Determine the verdict using the terminal state from `loop_complete` event (`terminated_by`), the artifact/contract evidence from Step 4, and the claimed-success signal from Step 6a:

| Verdict | Condition |
|---|---|
| `met` | Terminal reached AND all threshold contracts verified AND all expected artifact mutations occurred |
| `phantom` | Terminal reached AND claimed success > 0 (or `summary.json` absent — loop provides no failure evidence) AND (artifacts unchanged OR threshold unverified — only model self-reported via `llm_structured` evaluator) |
| `honest-failure` | Terminal reached AND `summary.json` present AND claimed success == 0 (`implemented: 0, failed: N`) AND no artifact mutation observed. The loop told the truth about its failure; the root cause is upstream (e.g. environment error, auth failure, misconfiguration). |
| `partial` | Terminal reached AND some but not all contracts satisfied |
| `partial` | `terminated_by == "max_steps"` AND `max_steps_summary` event present in JSONL (summary state ran; artifact written) |
| `degraded` | Loop completed but metric trended downward vs baseline captured in `state.json` |

Output the structured scorecard block:

```
### Goal-vs-Outcome Scorecard

**Goal**: "<loop description or (no description provided)>"
**Contract**: <threshold keys and values, or "none detected">
**Artifacts checked**: <list of paths and mutation status>
**Phase 1 signals**: <fault signal count from Step 5, or "none">
**Shallow-iteration check**: `<warning | corroborated | clear | unknown>` (<TOOL_CALL_COUNT> tool calls, <AUX_MUTATION_COUNT> auxiliary mutations)
**Verdict**: `<met | phantom | honest-failure | partial | degraded>`

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

**ENH-2005 sidecar exemption**: Before flagging, check whether the artifact-channel sidecar pattern is present. A state is exempt when **all** of the following hold:
1. The shared next state's `action` contains `subloop_outcome_` — the child writes its real verdict to this artifact and the parent recovers it downstream.
2. `state.on_error` is set and routes to a **distinct** state (not the shared classifier target) — ensuring an infrastructure crash is attributed separately, not collapsed into the generic failure path.

When both conditions hold, do **not** flag as a laundering defect. Instead, note `[mitigated — ENH-2005 artifact-channel sidecar: verdict recovered via subloop_outcome_ artifact, on_error routes to distinct crash state]`. When `on_error` is also collapsed into the shared target, or the shared target does not read `subloop_outcome_`, flag as before — those cases are genuinely unsafe.

Flag each **unmitigated** laundering defect with:
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
grep -rl "<loop_name>" .issues/bugs/ .issues/enhancements/ .issues/features/ .issues/epics/ 2>/dev/null
```

Mark matches as DUPLICATE. Present only NEW proposals.

**Skip this step if `--skip-issue-creation` or `--auto` flag is set (or if `LL_NON_INTERACTIVE`/`DANGEROUSLY_SKIP_PERMISSIONS` env vars are set, or `--dangerously-skip-permissions` is active).** Print: `ℹ️ Issue creation skipped (--skip-issue-creation / --auto)` and stop.

Use `AskUserQuestion` to ask:

```
Create issues for these <N> proposals? [Y/n/select]

  Y — create all
  n — cancel
  select — choose which to create (comma-separated numbers)
```

For each approved proposal, allocate an ID (`ll-issues next-id`) and write the issue file to the appropriate category dir. Stage each written file by its explicit path (`git add "<issue-file-path>"`) — do **not** `git add .issues/`, which sweeps in unrelated untracked/modified files (BUG-1976).

---

## Final Report

```
Assessment complete for loop: <loop_name>

Verdict: `<met | phantom | honest-failure | partial | degraded>`
Rubric audit: <N evaluators checked, M flagged — or "skipped (--no-rubric-audit)">
Laundering check: <N sub-loop states checked, M flagged — or "no sub-loop states">
Shallow-iteration check: `<warning | corroborated | clear | unknown>` (<N> tool calls, <M> auxiliary mutations — or "below threshold")
Issues created: <N>
```

---

## Usage Examples

```bash
# Assess most recent interrupted loop
/ll:audit-loop-run

# Assess a specific loop
/ll:audit-loop-run apo-textgrad

# Limit history to 100 events
/ll:audit-loop-run apo-textgrad --tail 100

# Skip LLM rubric audit (cost gate)
/ll:audit-loop-run apo-textgrad --no-rubric-audit
```

---

## Output Evidence Contract (verbatim-output rule)

When this skill emits an audit finding, verdict, or scorecard, cite evidence
verbatim rather than re-summarizing — quoting is cheaper than paraphrasing and
keeps the audit auditable:

IMPORTANT: For each condition you evaluate:
1. State your verdict: Yes / No / Partial
2. Provide a VERBATIM quote from the output that supports your verdict (exact text, in quotes)
3. If you cannot quote specific text, your verdict is automatically No (or Partial if context suggests partial progress)

Do not assert a verdict without evidence. "The task appears complete" is not evidence.
