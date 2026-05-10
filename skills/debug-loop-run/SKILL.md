---
description: Use when asked to analyze loop execution history, investigate loop failures, or find loop issues.
argument-hint: "[loop-name] [--tail N] [--skip-issue-creation] [--auto]"
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
    description: Loop name to analyze (optional — auto-selects most recent if omitted)
    required: false
  - name: tail
    description: Limit history events analyzed to the N most recent (default 200)
    required: false
  - name: skip_issue_creation
    description: Skip issue creation entirely and exit cleanly after presenting signals
    required: false
  - name: auto
    description: Non-interactive mode; suppress all AskUserQuestion calls and default to no for issue creation (implies --skip-issue-creation). Also activates when --dangerously-skip-permissions is in effect.
    required: false
---

# Analyze Loop

Inspect loop execution history and synthesize actionable issues (BUG/ENH/FEAT) from failure patterns, SIGKILL terminations, retry floods, and performance anomalies.

---

## Step 1: Resolve Loop Name

If `loop_name` argument is provided, resolve the most recent run folder before proceeding to Step 2:

```bash
ls -d .loops/.history/*-<loop_name>/ 2>/dev/null | sort | tail -1
```

This lists folders matching the flat layout `[TIMESTAMP]-[LOOP-NAME]` for the given loop, sorted lexicographically (ISO timestamps sort chronologically). The last entry is the most recent run.

- If the output is **empty**: report "No archived runs found for `<loop_name>`." and stop.
- Otherwise: extract the folder name (e.g. `.loops/.history/2026-03-19T204149-my-loop/`), strip the leading path and the `-<loop_name>` suffix to obtain `LATEST_RUN_ID` (the compact timestamp, e.g. `2026-03-19T204149`). Proceed to Step 2.

Otherwise, enumerate candidate loops:

```bash
ll-loop list --running --json
```

This outputs a JSON array of `LoopState` objects. Each object contains:
- `loop_name` — unique loop identifier
- `instance_id` — per-instance timestamp stem (e.g. `fix-types-20260503T122306`); **absent from list output** — use `ll-loop status <loop_name> --json` to resolve
- `status` — `"running"`, `"interrupted"`, `"failed"`, `"timed_out"`, `"completed"`, `"awaiting_continuation"`
- `updated_at` — ISO 8601 timestamp of last state update
- `current_state` — last active state
- `iteration` — last iteration count

**Filter** to candidate loops: keep entries where `status` is one of `"running"`, `"interrupted"`, `"failed"`, `"timed_out"`, `"awaiting_continuation"`. Sort by `updated_at` descending.

- **Zero candidates**: Report "No interrupted or running loops found. Specify a loop name explicitly." and stop.
- **One candidate**: Select it automatically. Report: `Auto-selected loop: <loop_name> (status: <status>, last updated: <updated_at>)`.
- **Two or more candidates with distinct `loop_name` values**: Use `AskUserQuestion` to present the list and ask the user to pick one:
  ```
  Multiple loops found. Select one to analyze:

  [1] <loop_name_1> — <status> — last updated <updated_at>
  [2] <loop_name_2> — <status> — last updated <updated_at>
  ...
  ```
- **Two or more candidates sharing the same `loop_name`** (multiple instances): follow up with `ll-loop status <loop_name> --json` to retrieve per-instance detail (`instance_id`, `pid`, `log_file`), then use `AskUserQuestion` to present instance-level disambiguation:
  ```
  Multiple instances of '<loop_name>' found. Select one to analyze:

  [1] <instance_id_1> — <status> — PID <pid> — last updated <updated_at>
  [2] <instance_id_2> — <status> — PID <pid> — last updated <updated_at>
  ...
  ```

---

## Step 2: Load Event History and Loop Config

Load the full event history for the selected loop.

**If `loop_name` was provided** (and `LATEST_RUN_ID` was resolved in Step 1):

```bash
ll-loop history <loop_name> <LATEST_RUN_ID> --json --tail <tail_arg_or_200>
```

**If `loop_name` was auto-selected** (from the running/interrupted list in Step 1):

```bash
ll-loop history <loop_name> --json --tail <tail_arg_or_200>
```

This outputs a JSON array of event dicts. Each event has `"event"` (the type) and `"ts"` (ISO 8601 timestamp) plus type-specific fields. Events are chronological oldest-first.

If the command fails (loop not found), report the error and stop.

Also load the loop configuration to understand state routing:

```bash
ll-loop show <loop_name> --resolved --json 2>/dev/null
```

This outputs a JSON object with a `"states"` key mapping state names to their config (including `evaluate.type` and `on_no`). Parse it into a state config map for use in signal classification. If the command fails, proceed without state config (treat all states as having no config).

States with a `_subloop` key contain the child loop's resolved state map one level deep. These entries are used for sub-loop signal classification and goal alignment analysis (see Step 3 and Step 3b). Sub-loop states do not contribute to parent loop event counts.

### Static Pass: Stub Action Detection (Signal 3)

Before walking the event history, scan the resolved state map for **stub action bodies** — `action` text that ships in the loop YAML but is inert (a literal `echo` placeholder rather than real work). This is a config-time check; results are emitted into a separate `static_issues` list distinct from the history-driven `signals` list of Step 3.

For each state in the resolved state map, read its `action` body and apply these regex patterns:

| Pattern | Scope | Rationale |
|---|---|---|
| `^echo "\d+"$` | states whose name contains `score`, `evaluate`, `judge`, `reward` | constant numeric verdict (e.g. `echo "5"` in `rl-rlhf.yaml::score`) |
| `^echo "Replace.*"$` or `^echo "TODO.*"$` | any state | placeholder text shipped as production code |
| `^echo "[A-Z_]+"$` | states whose `evaluate.type == "output_string"` | hard-coded literal verdict echo |

For each match, emit a Signal 3 entry into `static_issues`:

- **Type/Priority**: `ENH P2`
- **Title**: `"<state> action is a stub (<echo body>) — loop ships unimplemented"`
- **Include**: state name, the matched action body, the loop name

**Note**: this static pass complements (does not replace) the existing config-based `BUG — Sub-loop verdict discarded` rule in Step 3. That rule remains where it is (history-driven `### Signal Rules` bucket) for backward compatibility; only the new Signal 3 results go into `static_issues`. Both static and history-driven effectiveness signals are merged in Step 5 under the `Effectiveness Signals` heading.

(Reference: the closest existing precedent for regex over `state.action` bodies is `_collect_action_text()` + `re.search()` in `scripts/tests/test_builtin_loops.py` — same shape: iterate the state map, read `action`, regex-match.)

**Parse the events** into a structured list for classification. Key fields by event type:

| Event type | Key fields |
|---|---|
| `state_enter` | `state` (str), `iteration` (int) |
| `action_complete` | `exit_code` (int), `duration_ms` (int), `is_prompt` (bool) |
| `evaluate` | `verdict` (str: pass/fail/continue/retry/error), `reason` (str, optional) |
| `route` | `from` (str), `to` (str) |
| `retry_exhausted` | `state` (str), `retries` (int), `next` (str) |
| `rate_limit_exhausted` | `state` (str), `retries` (int, total = short + long), `short_retries` (int), `long_retries` (int), `total_wait_seconds` (number), `next` (str) |
| `rate_limit_waiting` | `state` (str), `elapsed_seconds` (number), `next_attempt_at` (str), `total_waited_seconds` (number), `budget_seconds` (number), `tier` (str: `"short"` or `"long"`) |
| `loop_complete` | `terminated_by` (str), `final_state` (str), `iterations` (int) |
| `loop_resume` | `from_state` (str), `iteration` (int) |

---

## Step 3: Classify Issue Signals

Scan the event list and classify signals using the rules below. Group events by `state` (use the most recent `state_enter.state` before each `action_complete` or `evaluate` to track which state each event belongs to).

### Signal Rules

#### BUG — Action failure (exit_code ≠ 0)
- Trigger: `action_complete` events where `exit_code != 0` AND `is_prompt == false`, grouped by state — **3 or more occurrences** on the same state
- **Exception — intentional `on_no` routing (exit_code=1 only)**: Before counting an `exit_code=1` event as a failure, check the state config loaded in Step 2:
  - If the state has `evaluate.type == "exit_code"` AND `on_no` is defined: **skip** — `exit_code=1` is the expected `on_no` routing signal, not a failure. Do not count these toward the 3-occurrence threshold.
  - If the state has `evaluate.type == "exit_code"` but **no `on_no`**: count `exit_code=1` as a failure (unhandled "no" outcome).
  - If state config is unavailable: count `exit_code=1` as a failure (conservative fallback).
  - `exit_code >= 2` always counts as a failure regardless of evaluator type or routing.
- Priority: P2
- Title: `"<state> action failed <N>x (exit_code=<code>) in <loop_name> loop"`
- Include: timestamps of failures, exit codes

#### BUG — SIGKILL / signal termination
- Trigger: `loop_complete` with `terminated_by == "signal"`
- Priority: P2
- Title: `"<loop_name> loop terminated by signal (SIGKILL) in <final_state> state"`
- Include: `final_state`, `iterations`, last 5 events before termination

#### BUG — FATAL_ERROR termination
- Trigger: `loop_complete` with `terminated_by == "error"`
- Priority: P2
- Title: `"<loop_name> loop terminated with error in <final_state> state"`
- Include: `final_state`, `iterations`, last 5 events before termination

#### ENH — Iteration-1 Convergence Without Apply (Signal 1)
- **Class**: Effectiveness signal (terminal-event handler).
- **Trigger**: `loop_complete` with `iterations == 1` (note: the event payload field is `iterations`, an int — see the Step 2 event-payload table) AND no state matching the apply/refine pattern was visited during the run. The apply-state prefix list is:

  `APPLY_STATE_PREFIXES = ("apply_", "refine_", "update_", "write_", "commit_")`

  (Documented in prose form parallel to the existing `DECISION_PREFIXES` and `GATE_STATE_PREFIXES` tuples in `scripts/tests/test_debug_loop_run_synthesis.py` and `scripts/tests/test_review_loop.py`. Matching is performed by the LLM in-context against `state_enter.state` names; no Python code is added.)

  Track an `apply_state_visit` flag while iterating `state_enter` events: set it true if any visited state name starts with one of the `APPLY_STATE_PREFIXES`. After the walk, evaluate the trigger.
- **Priority**: P3
- **Title**: `"<loop_name> converged on iteration 1 without entering apply/refine state — likely phantom convergence"`
- **Include**: `final_state`, `iterations`, the visited state sequence (compact, deduplicated)
- **Rationale**: a loop that terminates after one iteration without ever visiting an apply/refine/update/write/commit state has likely returned a default verdict from a `check_*`/`evaluate_*` gate without doing the productive work the loop was designed to perform.

#### ENH — Degenerate Gate Route Distribution (Signal 2)
- **Class**: Effectiveness signal (history walker).
- **Trigger**: an `evaluate` state's `route` event distribution shows >95% to a single branch when the per-state evaluation count meets a threshold:
  - **Single-run window**: ≥10 evaluations in the current run with >95% to one branch
  - **Multi-run window**: ≥20 evaluations across the most recent 5 runs with >95% to one branch (when prior-run history is available; otherwise apply only the single-run window)

  Maintain a `route_distribution: {from_state: {to_state: count}}` dict, updated on every `route` event during the Step 3 walk (the `route` event payload exposes `from` and `to`, per the Step 2 event-payload table). After the walk, for each `from_state` whose total count meets the threshold, compute the dominant-branch share; flag if it exceeds 95%.
- **Priority**: P3
- **Title**: `"<state> route fan-out is degenerate (<N>/<M> evaluations took <branch>)"`
- **Include**: state name, total evaluations `<M>`, dominant branch name and count `<N>/<M>`, percentage
- **Rationale**: an `evaluate` state whose route is overwhelmingly one-sided is not adding signal — the gate is either always-pass or always-fail and could be removed or replaced with an unconditional transition.

#### ENH — Capture Vacuum (Signal 4)
- **Class**: Effectiveness signal (history walker).
- **Trigger**: a downstream state's `action` text or `evaluate.source` references `${captured.X.output}` AND the producing state for capture `X` shows empty/whitespace output in **>20% of occurrences** within the analyzed window.

  Maintain a `capture_emptiness: {capture_name: {empty_count: int, total_count: int}}` dict, updated on every `action_complete` event whose state has `capture: X` set in the resolved YAML. There is **no `capture` event** in the JSONL stream — read emptiness from `action_complete.output_preview` (last 2000 chars of the action's stdout, included in every `action_complete` payload). After the walk, for each capture whose `total_count >= 3`, compute `empty_count / total_count`; flag if it exceeds 20%.
- **Priority**: P3
- **Title**: `"<consumer_state> consumes capture <X> that is empty in <N>/<M> runs"`
- **Include**: capture name, producing state, consumer state(s), empty count `<N>/<M>`, percentage
- **Rationale**: a downstream state that interpolates a capture whose producer routinely emits empty output is doing busywork — the consumer either has no input to process or silently treats blanks as valid, both of which suggest dead-weight wiring that should either be guarded with `on_blocked` routing or removed entirely.

#### ENH — Numeric Trajectory Stall (Signal 5)
- **Class**: Effectiveness signal (history walker).
- **Trigger**: `evaluate.type` is `output_numeric` or `convergence`. The captured numeric value across consecutive iterations within one run has **standard deviation < 1% of mean for ≥3 iterations** AND the value has **not crossed its target threshold** (read from `evaluate.target` on the event payload).

  Maintain a `numeric_trajectory: {state: [value, value, ...]}` dict, appending `evaluate.value` (`output_numeric`) or `evaluate.current` (`convergence`) on each `evaluate` event for that state. Both fields are emitted directly via the `**result.details` splat in `executor.py::_evaluate` — there is no preceding `capture` event to consult. After the walk, for each state with ≥3 samples, compute `stddev / mean` and compare against `evaluate.target` to determine whether the value is stalled below threshold.
- **Priority**: P3
- **Title**: `"<state> numeric output stalled at <value> across <N> iterations (target=<threshold>)"`
- **Include**: state name, sample count `<N>`, mean value, stddev, target threshold, evaluator type (`output_numeric` or `convergence`)
- **Rationale**: a numeric evaluator that hovers at a constant value but never crosses its target indicates the loop's optimization mechanism is not making progress — either the gradient/reward signal is broken, the action being scored is not actually mutating the underlying artifact, or the target threshold is unreachable given the current strategy.

#### ENH — Retry flood (true retries only)
- **Classification**: Before emitting this signal, check the loop config (loaded in Step 2) for the flagged state. A state is a **true retry state** if its config has `on_retry` or `max_retries` fields. A state is an **intentional cycling state** if it has neither (uses `on_no`/`on_yes` routing only).
- Trigger: `retry_exhausted` event is present for a state **OR** a true retry state appears in `state_enter` events **5 or more times**
- Priority: P3
- Title: `"<state> retry flood (<N> re-entries) in <loop_name> loop; consider raising retry limit or adding guard"`
- Include: iteration numbers when state was re-entered; include `retry_exhausted` event details if present

#### BUG — Rate-limit exhaustion
- Trigger: `rate_limit_exhausted` event is present for a state (the executor spent its full wall-clock rate-limit budget across both short-burst and long-wait tiers and routed to `on_rate_limit_exhausted`)
- Priority: P3
- Title: `"<state> rate-limit retries exhausted in <loop_name> loop; upstream 429 pressure"`
- Include: `retries` (total), `short_retries`, `long_retries`, `total_wait_seconds`, event timestamps, and any neighbouring `rate_limit_exhausted` events on other states (potential storm)
- **Note:** rate-limit exhaustion is distinct from a generic retry flood — the state is not misconfigured, the upstream service is refusing work. Classify separately from the Retry flood rule above. When `long_retries > 0`, the upstream was down for at least one long-wait ladder step (multi-minute outage).

#### NOTE — Intentional cycling (informational only)
- When an intentional cycling state (no `on_retry`/`max_retries` config) appears in `state_enter` events **5 or more times**, **do not generate an issue signal**.
- Include a brief informational note in the analysis output: `"<state> cycled <N>x (intentional on_no/on_yes routing — no issue signal)"`
- **Exception — stuck loop**: If the same state appears in **20 or more consecutive** `state_enter` events with no intervening different state, emit a signal:
  - Detect by scanning the ordered `state_enter` sequence for runs of identical state names ≥ 20
  - Priority: P4
  - Title: `"<state> cycling without progress (>20 consecutive re-entries) in <loop_name> loop"`
  - Include: timestamp range, iteration numbers of the consecutive run

#### ENH — Consistently slow state
- Trigger: `action_complete` events for a single state where the **average `duration_ms`** is ≥ 30 000 ms and there are **3 or more samples**
- Priority: P4
- Title: `"<state> state avg <X>s in <loop_name> loop; caching or optimization may help"`
- Include: min/max/avg duration, sample count

#### BUG — Evaluate failure
- Trigger: `evaluate` events where `verdict == "fail"` on the same state — **3 or more occurrences**
- Priority: P3
- Title: `"<state> evaluation failed <N>x in <loop_name> loop"`
- Include: `reason` field from last failure, timestamps

#### BUG — Sub-loop verdict discarded
- Trigger: any state in the loop config (from Step 2) has `loop:` set AND `on_yes == on_no` (same destination regardless of child outcome). This is a **config-based** signal detected from FSM structure, not event history — emit regardless of how many times the state was visited.
- Priority: P3
- Title: `"<state> sub-loop verdict discarded in <loop_name> loop — <child_loop> result ignored (<shared_next>)"`
- Include: state name, child loop name (`loop:` value), shared next state (both `on_yes`/`on_no` point to)
- Rationale: when the parent routes child success and child failure identically, the sub-loop's outcome is silently dropped — this is a structural logic error independent of execution frequency.

### Multiple signals on same state
If a state triggers both an action failure and an evaluate failure BUG, emit only the action failure (higher severity signal takes priority). Emit all distinct signals from different states.

Proceed to Step 3b regardless of signal count.

---

## Step 3b: Semantic Synthesis

Using the event data and loop config loaded in Step 2 and the signals classified in Step 3, produce a holistic **Execution Summary** that contextualizes the signal list. This phase is advisory — it does not add or remove signals from Step 3.

### 3b-1: Extract Loop Goal

From the `ll-loop show --json` output parsed in Step 2, read the top-level `"description"` field:
- If present and ≥ 5 words: use as the declared goal
- If absent or shorter: use `"(no description provided)"`

### 3b-2: Reconstruct Observed Execution Path

From the ordered `state_enter` events:

1. Build the **state visit sequence**: list of state names in encounter order (consecutive duplicates appear as separate entries)
2. Compute **per-state visit counts**: count of `state_enter` events per unique state name
3. Identify the **dominant state**: the state with the most `state_enter` occurrences
4. Read `terminated_by` from the `loop_complete` event if present (`"terminal"`, `"signal"`, or `"error"`)
5. Compute the dominant state's **iteration share**: `(dominant_state_count / total_state_enter_count) × 100`

### 3b-3: Goal Alignment Assessment

If a description is available (≥ 5 words):

1. Extract 2–4 key activity phrases from the description (verb + object, e.g., "refine issues", "check completeness")
2. Check whether the dominant state's name or its action text (from the state config loaded in Step 2) corresponds to a described activity
3. If the dominant state accounts for ≥ 50% of iterations and has no clear connection to the declared goal activities: flag as a **goal alignment anomaly**
4. If `terminated_by == "terminal"` (completed successfully) but heavy cycling occurred (total iterations > 3× the number of distinct states visited): note that completion may mask an ambiguous exit criterion
5. If any state has a `_subloop` key (from `--resolved` output), treat its child states as a **separate execution scope** — do not add child state names to the parent loop's dominant state tally. Flag any `_subloop` states that represent a disproportionate share of child work as a cross-boundary note (e.g., "sub-loop `issue-refinement` is invoked from `refine_issues`; child routing is distinct from parent goal alignment").

### 3b-4: Cross-Signal Reasoning

For each pair of states that both have classified signals from Step 3:

1. Check if they are **adjacent** in the execution path: a direct `route` event exists between them, or one state immediately precedes the other in the `state_enter` sequence
2. If adjacent with co-occurring signals, evaluate the signal types for plausible shared root causes:
   - Action failure in state A + evaluate failure in downstream state B → output format mismatch candidate
   - Retry flood in state A + action failure in adjacent state B → upstream dependency failure candidate
3. Emit a **cross-signal note** for each plausible shared root cause identified

### 3b-5: Sub-Threshold Pattern Detection

Check for behavioral fingerprints that no single signal rule captures:

1. **Dominant cycling**: dominant state accounts for ≥ 70% of total `state_enter` events AND it is not the only state visited — flag as a potential design smell (one state disproportionately consuming iterations)
2. **Decision-state dominance**: dominant state name matches a meta-state pattern (`check_*`, `verify_*`, `evaluate_*`, `wait_*`) rather than a work state — loop may be spending most iterations in decision logic rather than productive work

### 3b-6: Produce Synthesis Summary

Assemble the **Execution Summary** block. This block is always produced (even when no signals were found in Step 3) and is displayed as a preamble before the signal list in Step 5.

**Format**:

```
### Execution Summary

**Loop goal**: "<declared description or (no description provided)>"
**Observed path**: <state_1> (×N₁) → <state_2> (×N₂) → ... [<terminated_by or in-progress>]
**Goal alignment**: <one-sentence assessment, or "Insufficient description to assess alignment." if no description>

**Cross-signal note**: <states, their signal types, and shared root cause candidate>
[Omit this line if no adjacent co-occurring signals were found]

**Pattern note**: <sub-threshold behavioral observation>
[Omit this line if no sub-threshold patterns were detected]
```

**Example**:

```
### Execution Summary

**Loop goal**: "Refine open issues with codebase context until all sections are populated"
**Observed path**: start → analyze_issue (×12) → check_completeness (×11) → finalize → done [terminal]
**Goal alignment**: Partial — loop completed but `analyze_issue` re-entered 12× suggests the
  completeness criterion in `check_completeness` is ambiguous or too strict.

**Cross-signal note**: `analyze_issue` action failures (BUG) and `check_completeness`
  evaluate failures (BUG) are adjacent in the execution path — likely share a root cause;
  investigate whether analysis output format matches what the evaluator expects.
```

If **both** conditions are true — (a) no signals from Step 3 and (b) no anomalies from 3b-3 through 3b-5 — output the minimal summary and stop:

```
### Execution Summary

**Loop goal**: <goal>
**Observed path**: <state sequence with counts>
**Goal alignment**: <assessment>

No issue signals detected. Loop execution appears normal.
```

Otherwise proceed to Step 4.

---

## Step 4: Deduplicate Against Active Issues

For each proposed signal, check whether a sufficiently similar issue already exists in the active issue directories:

```bash
grep -rl "<loop_name>" .issues/bugs/ .issues/enhancements/ .issues/features/ .issues/epics/ 2>/dev/null | xargs grep -l "<state_name>" 2>/dev/null
```

- If matching files are found: mark the signal as **DUPLICATE** and note the existing file path(s). Do not propose it.
- If no match: keep it as a **NEW** proposal.

Proceed with only the NEW proposals.

If all signals are duplicates, report: "All <N> signals already have active issues. No new issues to create." and stop.

---

## Step 5: Present Proposals and Confirm

Display the analysis output, always starting with the Execution Summary from Step 3b. Signals are grouped into two markdown-heading buckets — **Fault Signals** (BUG-class anomalies that broke the run: action failure, SIGKILL, FATAL_ERROR, evaluate failure, sub-loop verdict discarded, rate-limit exhaustion) and **Effectiveness Signals** (ENH-class observations that the run completed but did not do useful work: stub action from the Step 2 `static_issues` list, retry flood, slow state, iter-1 convergence without apply, degenerate gate, capture vacuum, numeric trajectory stall). Omit either heading when its count is zero.

```
Analyzing loop: <loop_name> (last updated: <updated_at>)
Events analyzed: <N> events

<Execution Summary block from Step 3b>

### Fault Signals (N)

  [1] BUG P2 — <title>
  [2] BUG P3 — <title>
  ...

### Effectiveness Signals (M)

  [1] ENH P2 — <title>
  [2] ENH P3 — <title>
  ...
```

The total signal count for downstream confirmation is `N + M` (combine both buckets when prompting). If `N + M == 0` (no signals passed deduplication): output the Execution Summary and stop — do not ask for confirmation.

**Skip the issue-creation prompt if `--skip-issue-creation` or `--auto` flag is set (or if `--dangerously-skip-permissions` is active).** Print: `ℹ️ Issue creation skipped (--skip-issue-creation / --auto)` and stop.

Otherwise, use `AskUserQuestion` to ask (where `<M>` is the combined `Fault + Effectiveness` count):

```
Create these <M> issues? [Y/n/select]

  Y — create all
  n — cancel
  select — choose which to create (enter comma-separated numbers, e.g. 1,3)
```

Handle each response:
- `Y` or empty/enter → create all
- `n` → report "No issues created." and stop
- `select` (or comma-separated numbers like `1,3`) → create only the listed indices

---

## Step 6: Create Approved Issues

For each approved issue signal, create an issue file:

### 6a. Allocate ID

```bash
ll-issues next-id
```

This prints a 3-digit zero-padded number, e.g. `728`. Capture it for the filename.

**Important**: Call `ll-issues next-id` once per issue, immediately before writing each file. Do not batch-allocate IDs upfront, as concurrent writes could produce collisions.

### 6b. Determine issue type and category

| Signal type | Issue type | Category dir |
|---|---|---|
| Action failure, SIGKILL, FATAL_ERROR, Evaluate failure | `BUG` | `.issues/bugs/` |
| Retry flood, Slow state | `ENH` | `.issues/enhancements/` |

### 6c. Write the issue file

**Filename format**: `P<priority>-<TYPE>-<NNN>-<slug>.md`

Where `<slug>` is the title lowercased, spaces replaced with `-`, non-alphanumeric characters stripped, max 60 characters.

Example: `P2-BUG-728-verify-action-failed-3x-exit-code-1-in-issue-fixer-loop.md`

**Issue file template**:

```markdown
---
discovered_date: <YYYY-MM-DD>
discovered_by: debug-loop-run
source_loop: <loop_name>
source_state: <state_name>
---

# <TYPE>-<NNN>: <title>

## Summary

<One paragraph description of what was observed in the loop execution history.>

## Loop Context

- **Loop**: `<loop_name>`
- **State**: `<state_name>`
- **Signal type**: <action_failure | sigkill | fatal_error | retry_flood | slow_state | eval_failure>
- **Occurrences**: <N>
- **Last observed**: <ts of most recent relevant event>

## History Excerpt

Events leading to this signal:

```json
<paste the relevant events as a JSON array — up to 10 events max>
```

## Expected Behavior

<What should happen instead>

## Proposed Fix

<Brief proposal based on signal type — e.g., "Investigate exit_code source", "Increase timeout", "Add retry guard">

## Acceptance Criteria

- [ ] <Criterion 1>
- [ ] <Criterion 2>

## Labels

`<bug-or-enhancement>`, `loops`, `captured`

## Status

**Open** | Created: <YYYY-MM-DD> | Priority: P<N>
```

Use the `Write` tool to write the file.

### 6d. Stage the file

After writing all issue files:

```bash
git add .issues/
```

---

## Final Report

After all issues are created, output:

```
Analysis complete for loop: <loop_name>

Created <N> issue(s):
  - <filename> [<TYPE> P<N>]
  ...

Skipped <M> duplicate(s):
  - <signal title> → already tracked in <existing_file>
  ...
```

---

## Usage Examples

```bash
# Auto-select most recently interrupted loop
/ll:debug-loop-run

# Analyze a specific loop
/ll:debug-loop-run issue-fixer

# Limit events analyzed to 100 most recent
/ll:debug-loop-run issue-fixer --tail 100
```
