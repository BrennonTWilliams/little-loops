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
    description: "Limit history events analyzed to the N most recent (default: all events; auto-scaled)"
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
ll-loop list --all-runs --json
```

Filter to `status` one of `"running"`, `"interrupted"`, `"failed"`, `"timed_out"`, `"awaiting_continuation"`. Sort by `updated_at` descending.

Note: `ll-loop list --all-runs --json` output does **not** include `instance_id` — entries with the same `loop_name` are indistinguishable at this level.

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
  the only honest output is the refusal above. Immediately after the refusal
  line, emit `REVIEW_JSON: {"verdict": "refused", "target_kind": "loop",
  "target_id": "<loop_name>", "severity_counts": {"p0": 0, "p1": 0, "p2": 0,
  "info": 0}, "findings_count": 0}` (a single tagged line, per
  `extract_tagged_json`'s convention) so a refused audit is still captured as
  a `review_events` row instead of leaving no trace (ENH-2512).
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

## Step 5.5: Shallow-Iteration Check (ENH-2949: `ll-loop audit --json`)

Run the deterministic counter CLI against the resolved run directory instead of counting events or scanning the filesystem by hand:

```bash
ll-loop audit <LATEST_RUN_ID>-<loop_name> --json
```

(equivalently `ll-loop audit --latest <loop_name> --json` when you don't already have `LATEST_RUN_ID`). This returns a `RunAuditStats` JSON blob with `tool_call_count` (the number of `action_complete` events), `aux_mutation_count` (a filesystem-mtime scan of the run directory scoped to files modified since the run started, excluding the loop's own bookkeeping files — `null` when the run-start timestamp can't be parsed) and `diff_stall_present` (true when an `evaluate` event of `type: diff_stall` recorded `verdict` `"stall"` or `"no"`).

Apply the threshold (default: 30) yourself using those three fields:

```
IF aux_mutation_count is null:
  result = "unknown"          # no filesystem evidence available — skip, don't guess
ELIF tool_call_count > 30 AND aux_mutation_count == 0:
  IF diff_stall_present:
    result = "corroborated"   # both heuristic and diff_stall agree
  ELSE:
    result = "warning"        # heuristic alone
ELSE:
  result = "clear"
```

The default threshold of 30 `action_complete` events is intentionally conservative — most well-structured loops either produce auxiliary artifacts or converge within this budget. Loops that burn more than 30 iterations without creating helper structure are iterating without building.

**Emit finding** when result is `"warning"` or `"corroborated"`:

```
⚠ Shallow-iteration: <tool_call_count> action_complete events with no auxiliary file mutations
  outside the primary artifact path (<primary_paths>).
  [Corroborated by diff_stall evaluator verdict.]
  Remediation: add intermediate artifact-write states; break monolithic iteration into
  smaller sub-tasks that each produce a named helper file.
```

Pass `result` and `tool_call_count` to the scorecard in Step 6.

`ll-loop audit`'s auxiliary-mutation scan is filesystem-only (mtime since run start) — it does not attempt `git diff`/`git check-ignore` correlation, so it works uniformly whether or not the primary artifact path is gitignored. If you need git-history evidence for a specific artifact path, still use the `git log`/`git diff` commands from Step 4 directly; `aux_mutation_count` is a heuristic signal for this step's threshold only.

---

## Step 5.6: Budget-Utilization Guard (ENH-2949: `ll-loop audit --json`)

The same `ll-loop audit --json` call from Step 5.5 also returns `steps_consumed`, `max_steps` (resolved from the loop's FSM definition, or `null` if it couldn't be resolved), and `budget_utilization` (`steps_consumed / max_steps`, or `null` when `max_steps` is unavailable).

If `budget_utilization < 0.3`, reject budget-exhaustion as the primary root cause — the loop consumed less than 30% of its budget, so it did not run out of steps. If `budget_utilization` is `null`, note that budget utilization could not be computed and skip this guard.

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

**ENH-2404 — parked-issue visibility (`auto-refine-and-implement` / `autodev`)**: if present, also read `skipped_breakdown` (an object keyed by reason, e.g. `{"decomposed": 1, "refine_failed": 0, "low_readiness": 4, "oversized_atomic": 1}`), `gate_blocked` (issues parked by the learning-gate, ENH-2402 — previously invisible here), and `parked_rate` (`(skipped + not_closed + gate_blocked) / input_size`). `parked_rate` is a visibility signal, not a pass/fail gate — interpret it via `skipped_breakdown`: a high rate dominated by `decomposed` is healthy (the run is legitimately fanning out into children), while one dominated by `refine_failed` / `low_readiness` is a genuine quality signal worth flagging in the report. **`oversized_atomic` (BUG-2734) is a distinct signal from `low_readiness`**: it means readiness already passed and a Very Large, deliberately-atomic issue's outcome risk failed even after an earn-the-pass remediation attempt — worth flagging as "needs a human risk review / `outcome_gate_waived` decision," not generically low-quality work. **`refine_failed_infra` (ENH-2727) is a re-runnable (non-quality) bucket**: it means the refine sub-loop failed for infrastructure reasons — either killed externally (SIGTERM/OOM/timeout — exit 143/137/124) or, per BUG-2826, failing at the model-invocation layer (rate limit, auth/credentials, network, API 5xx, as classified by `failure_type`) — not that refinement produced a bad result — treat it like a transient and just re-run the issue, distinct from the quality-signal `refine_failed`. These keys are additive; older `summary.json` files (pre-ENH-2404) will lack them — treat their absence as "no breakdown data available" rather than an error, and fall back to the plain `skipped` count. **`notstarted_*` (ENH-2989) is never-attempted, not a quality signal** — the same bucket as `already_*` (ENH-2868) and `blocked_by_unmet` (ENH-2909): the issue was rejected during Phase 1 validation and no implementation was attempted, so it neither indicts refinement quality nor is generally worth blind re-running — except `notstarted_unknown`, which autodev already re-queues once itself (a non-compliant model turn, not a real rejection); if it still shows up here, that retry was exhausted. `autodev` surfaces the same population as a dedicated `not_started` count (and `not_started` verdict) in its own `summary.json`, distinct from `phantom`.

**ENH-2743 — recovered-skip visibility (`auto-refine-and-implement`)**: if present, also read `closed_via_recovery` — a count of `skipped` IDs that nonetheless reached `status: done` by `finalize` time (e.g. `ll-auto` re-implemented a parked issue after the sprint queue released the lock). It does not subtract from `skipped` or `parked_rate`; treat it as a footnote that reduces how alarming a nonzero `skipped` count actually is — a run with `skipped: 2, closed_via_recovery: 2` "failed to handle" nothing, both self-resolved within the run. This key is additive; older `summary.json` files (pre-ENH-2743) will lack it — treat its absence as "no recovery data available," not an error.

**ENH-2533 — per-issue + learning-followup visibility (`rn-implement`)**: if present, also read `per_issue` (an array of `{id, outcome, reason?, pre_scores?, post_scores?, convergence?}` records aggregated from the run's `subloop_outcome_<ID>.txt` sidecars — one per issue the queue touched) and `learning_followups` (an array of `{id, targets, remedy}` records aggregated from `learning_unproven_<ID>.txt` sidecars, where `remedy` is `/ll:explore-api <targets>`). Cite specific parked-issue IDs from `per_issue` in the verdict rationale instead of bucketed counters — e.g. "ENH-400 parked with MANUAL_REVIEW_RECOMMENDED, BUG-401 parked with LEARNING_GATE_BLOCKED" — so the audit reproduces the operator's screen-readable rationale. These are additive; older `summary.json` files (pre-ENH-2533) will lack both keys — fall back to the `learning_gate_blocked` scalar counter and the per-record `subloop_outcome_<ID>.txt` sidecars directly. Malformed per-issue sidecars surface in `summary_warnings.txt` (not `summary.json`); check there only when `per_issue` is shorter than the run's tally of parked IDs.

**ENH-2601 — post-implementation verify verdict (`auto-refine-and-implement` / `sprint-refine-and-implement`)**: if present, also read `verify_verdict` (`"passed"` / `"failed"` / `"collection_error"` / `"config_error"` / `"error"` / `"skipped"` / `"not_run"`) — the result of running `project.test_cmd`/`lint_cmd` once, after `delegate` and before `finalize`. This is **advisory only**: it does not gate the run's own `verdict` (a `closed > 0` run can still report `verify_verdict: "failed"` if a regression slipped through). `"skipped"` means `test_cmd` was unconfigured; `"not_run"` means the verify state never executed (e.g. the resolved issue set was empty, or `delegate` crashed before verify could run). `"config_error"` (ENH-2742) means the failure is a harness/config problem — e.g. a missing npm script from a misconfigured `test_cmd` — **not a code defect**; treat it as an infra issue to fix in `.ll/ll-config.json`, distinct from `"failed"` which indicates a real test/lint regression. `"error"` (BUG-3364) means `verify`'s own python3 heredoc crashed (e.g. an uncaught `ModuleNotFoundError`) before it could run the test/lint suite at all — report it exactly like `"config_error"`: an infra failure to investigate (check the run's stderr for the traceback), not a code regression, and treat the run as if verify never really happened. Flag `verify_verdict: "failed"` (or `"error"`) prominently in the report even when the closure `verdict` itself reads `success` — that combination is exactly the gap this field exists to surface. This key is additive; older `summary.json` files (pre-ENH-2601) will lack it — treat its absence as "no verify data available," not an error.

**BUG-2614 / BUG-3364 — epic-branch merge verdict (`auto-refine-and-implement` / `sprint-refine-and-implement`)**: if present, also read `epic_merge_verdict` (`"merged"` / `"pr_opened"` / `"held_open"` / `"verify_failed"` / `"merge_failed"` / `"error"` / `"skipped"` / `"not_run"`) — the result of `merge_epic_branch`'s attempt to merge (or PR) the EPIC integration branch back to base once all children are `done`. Also advisory only, same non-gating contract as `verify_verdict`. `"skipped"` means the scope wasn't an EPIC, the branch was already merged, or both `merge_to_base_on_complete`/`open_pr` are disabled; `"held_open"` means not all children are `done` yet; `"not_run"` means `merge_epic_branch` never executed (e.g. `record_error`'s crash path routed straight to `finalize`). `"error"` (BUG-3364) means the state's own python3 heredoc crashed before it could even reach a merge decision — report it the same way as `verify_verdict: "error"`: an infra failure, not evidence the merge itself was attempted and failed. This key is additive; older `summary.json` files (pre-BUG-2614) will lack it — treat its absence as "no epic-merge data available," not an error.

### Step 6b: Verdict Table

Determine the verdict using the terminal state from `loop_complete` event (`terminated_by`), the artifact/contract evidence from Step 4, and the claimed-success signal from Step 6a.

"Terminal reached" below means `terminated_by == "terminal"`. Note that this alone does **not** mean the run succeeded: the same `loop_complete` event carries `failure_terminal` (ENH-2814), which is `true` when the loop stopped on a state declared `failure: true`. Read that flag — do not infer failure from the terminal state's name. A run with `failure_terminal: true` is an `honest-failure` when its artifact/claim evidence agrees, and a `phantom` when the loop nonetheless claimed success. The process exit code carries the same signal (`2` = failure terminal).

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

Immediately after the report block, emit a `REVIEW_JSON: {...}` tagged line
(ENH-2512, `extract_tagged_json` convention) so `cmd_invoke()` persists this
run as a `review_events` row: `{"verdict": "<pass|warn|fail|degraded mapped
from met->pass, partial->warn, phantom|honest-failure->fail,
degraded->degraded>", "target_kind": "loop", "target_id": "<loop_name>",
"severity_counts": {"p0": 0, "p1": <rubric-flagged + laundering-flagged
count>, "p2": 0, "info": 0}, "findings_count": <rubric-flagged +
laundering-flagged count>}`.

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
