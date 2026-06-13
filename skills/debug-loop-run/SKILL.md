---
name: debug-loop-run
description: Use when asked to analyze loop execution history, investigate loop failures, or find loop issues.
disable-model-invocation: true
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
    description: Non-interactive mode; suppress all AskUserQuestion calls and default to no for issue creation (implies --skip-issue-creation). Also activates when LL_NON_INTERACTIVE or DANGEROUSLY_SKIP_PERMISSIONS env vars are set, or when --dangerously-skip-permissions is in effect.
    required: false
metadata:
  short-description: Use when asked to analyze loop execution history, investigate loop failures, or 
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
- **Two or more candidates sharing the same `loop_name`** (multiple instances): follow up with `ll-loop status <loop_name> --json` to retrieve per-instance detail (`instance_id`, `pid`, `log_file`, `events_file`), then use `AskUserQuestion` to present instance-level disambiguation:
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

**Parse the events** into a structured list for classification. Each event has
`"event"` (the type) and `"ts"` (timestamp) plus type-specific fields — e.g.
`state_enter` carries `state`/`iteration`, `action_complete` carries
`exit_code`/`duration_ms`/`is_prompt`, `loop_complete` carries
`terminated_by`/`final_state`/`iterations`, and `rate_limit_waiting` carries
`state`/`elapsed_seconds`/`budget_seconds`/`tier`. See [reference.md](reference.md)
for the full event-type field table (all event types and their key fields).

---

## Step 3: Classify Issue Signals

Scan the event list and classify signals using the rules below. Group events by `state` (use the most recent `state_enter.state` before each `action_complete` or `evaluate` to track which state each event belongs to).

### Signal Rules

Apply the full signal-rule catalog in [reference.md](reference.md) (each rule
lists its trigger condition, priority, title format, and include-list). The
catalog covers two classes:

- **Fault signals (BUG):** action failure (exit_code ≠ 0, with the `on_no`
  exit_code=1 exception), SIGKILL/signal termination, FATAL_ERROR termination,
  evaluate-error termination, stall-detector abort, rate-limit exhaustion,
  throttle hard-stop, and evaluate failure (verdict=fail ≥3x), plus the
  config-based sub-loop verdict-discarded rule.
- **Effectiveness signals (ENH):** iteration-1 convergence without apply
  (Signal 1), degenerate gate route distribution (Signal 2), capture vacuum
  (Signal 4), numeric trajectory stall (Signal 5), retry flood (true retries
  only), throttle hard transition, and consistently slow state. Informational
  NOTE-only patterns (throttle warnings, intentional cycling) emit notes, not
  issues.

While walking the events, maintain the running dicts the reference rules
require (`route_distribution`, `capture_emptiness`, `numeric_trajectory`, the
`apply_state_visit` flag, per-state counts) and evaluate each rule's trigger
after the walk.

### Multiple signals on same state
If a state triggers both an action failure and an evaluate failure BUG, emit only the action failure (higher severity signal takes priority). Emit all distinct signals from different states.

When both `BUG — Evaluate error terminated the loop` and `BUG — FATAL_ERROR termination` would fire on the same `loop_complete` (i.e. `terminated_by == "error"` AND `evaluate.verdict == "error"` both hold), emit only `BUG — Evaluate error terminated the loop` — it is strictly more informative and supersedes the generic FATAL_ERROR signal.

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

Display the analysis output, always starting with the Execution Summary from Step 3b. Signals are grouped into two markdown-heading buckets — **Fault Signals** (BUG-class anomalies that broke the run: action failure, SIGKILL, FATAL_ERROR, evaluate error termination, evaluate failure, sub-loop verdict discarded, rate-limit exhaustion) and **Effectiveness Signals** (ENH-class observations that the run completed but did not do useful work: stub action from the Step 2 `static_issues` list, retry flood, slow state, iter-1 convergence without apply, degenerate gate, capture vacuum, numeric trajectory stall). Omit either heading when its count is zero.

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

**Skip the issue-creation prompt if `--skip-issue-creation` or `--auto` flag is set (or if `LL_NON_INTERACTIVE`/`DANGEROUSLY_SKIP_PERMISSIONS` env vars are set, or `--dangerously-skip-permissions` is active).** Print: `ℹ️ Issue creation skipped (--skip-issue-creation / --auto)` and stop.

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
| Action failure, SIGKILL, FATAL_ERROR, Evaluate error termination, Evaluate failure | `BUG` | `.issues/bugs/` |
| Retry flood, Slow state | `ENH` | `.issues/enhancements/` |

### 6c. Write the issue file

**Filename format**: `P<priority>-<TYPE>-<NNN>-<slug>.md`, where `<slug>` is the
title lowercased, spaces replaced with `-`, non-alphanumeric characters
stripped, max 60 characters (e.g.
`P2-BUG-728-verify-action-failed-3x-exit-code-1-in-issue-fixer-loop.md`).

Populate the issue file from the full markdown template in
[reference.md](reference.md) (frontmatter with `discovered_by: debug-loop-run` /
`source_loop` / `source_state`, plus `## Summary`, `## Loop Context`,
`## History Excerpt`, `## Expected Behavior`, `## Proposed Fix`,
`## Acceptance Criteria`, `## Labels`, and `## Status` sections). Use the
`Write` tool to write the file.

### 6d. Stage the file

After writing all issue files, stage each one by its explicit path. Do **not**
`git add .issues/` — a directory-level stage sweeps in unrelated untracked/modified
files (BUG-1976).

```bash
git add "<each written issue-file-path>"   # repeat per file written above
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

---

## Additional Resources

- [reference.md](reference.md) — full event-type field table (Step 2), the
  complete signal-rule catalog with triggers/priorities/title formats (Step 3),
  and the issue-file markdown template (Step 6c).
