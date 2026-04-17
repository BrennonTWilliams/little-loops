---
description: |
  Use when the user asks to analyze loop execution history, investigate loop failures, find loop issues, or synthesize actionable issues from loop runs.

  Trigger keywords: "analyze loop", "loop issues", "loop failures", "loop history issues", "loop execution", "loop anomalies"
argument-hint: "[loop-name] [--tail N]"
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
- `status` — `"running"`, `"interrupted"`, `"failed"`, `"timed_out"`, `"completed"`, `"awaiting_continuation"`
- `updated_at` — ISO 8601 timestamp of last state update
- `current_state` — last active state
- `iteration` — last iteration count

**Filter** to candidate loops: keep entries where `status` is one of `"running"`, `"interrupted"`, `"failed"`, `"timed_out"`, `"awaiting_continuation"`. Sort by `updated_at` descending.

- **Zero candidates**: Report "No interrupted or running loops found. Specify a loop name explicitly." and stop.
- **One candidate**: Select it automatically. Report: `Auto-selected loop: <loop_name> (status: <status>, last updated: <updated_at>)`.
- **Two or more candidates**: Use `AskUserQuestion` to present the list and ask the user to pick one:
  ```
  Multiple loops found. Select one to analyze:

  [1] <loop_name_1> — <status> — last updated <updated_at>
  [2] <loop_name_2> — <status> — last updated <updated_at>
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
ll-loop show <loop_name> --json 2>/dev/null
```

This outputs a JSON object with a `"states"` key mapping state names to their config (including `evaluate.type` and `on_no`). Parse it into a state config map for use in signal classification. If the command fails, proceed without state config (treat all states as having no config).

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

### Multiple signals on same state
If a state triggers both an action failure and an evaluate failure BUG, emit only the action failure (higher severity signal takes priority). Emit all distinct signals from different states.

If no signals are found, report: "No issue signals detected in loop history." and stop.

---

## Step 4: Deduplicate Against Active Issues

For each proposed signal, check whether a sufficiently similar issue already exists in the active issue directories:

```bash
grep -rl "<loop_name>" .issues/bugs/ .issues/enhancements/ .issues/features/ 2>/dev/null | xargs grep -l "<state_name>" 2>/dev/null
```

- If matching files are found: mark the signal as **DUPLICATE** and note the existing file path(s). Do not propose it.
- If no match: keep it as a **NEW** proposal.

Proceed with only the NEW proposals.

If all signals are duplicates, report: "All <N> signals already have active issues. No new issues to create." and stop.

---

## Step 5: Present Proposals and Confirm

Display a numbered list of proposed issues:

```
Analyzing loop: <loop_name> (last updated: <updated_at>)
Events analyzed: <N> events

Found <M> issue signal(s):

  [1] BUG P2 — <title>
  [2] ENH P3 — <title>
  ...
```

Then use `AskUserQuestion` to ask:

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
discovered_by: analyze-loop
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
/ll:analyze-loop

# Analyze a specific loop
/ll:analyze-loop issue-fixer

# Limit events analyzed to 100 most recent
/ll:analyze-loop issue-fixer --tail 100
```
