---
description: |
  Use when the user asks to clean up stuck loops, find stale loops, kill dead loop processes, or troubleshoot loop state issues.

  Trigger keywords: "cleanup loops", "stuck loops", "clean loops", "stale loops", "kill stuck loops", "cleanup-loops"
argument-hint: "[--dry-run] [--threshold N]"
model: sonnet
allowed-tools:
  - Bash(ll-loop:*, kill:*, rm:*, python3:*)
  - AskUserQuestion
arguments:
  - name: dry_run
    description: Preview discovered stuck/stale loops without cleaning anything (default false)
    required: false
  - name: threshold
    description: Minutes before a "running" loop's updated_at is considered stale (default 15)
    required: false
---

# Cleanup Loops

Discover stuck or stale `ll-loop` processes, diagnose root causes from their state and events
files, and clean them up after user confirmation.

---

## Step 1: Enumerate All Loops with State Files

```bash
ll-loop list --running --json
```

This returns a JSON array of all loops that have a `.state.json` file in `.loops/.running/`,
regardless of whether they are actually running. Each element contains:

| Field | Type | Description |
|---|---|---|
| `loop_name` | string | Unique loop identifier |
| `status` | string | `"running"`, `"interrupted"`, `"failed"`, `"timed_out"`, `"awaiting_continuation"`, `"completed"` |
| `current_state` | string | Last active FSM state name |
| `updated_at` | string | ISO 8601 UTC timestamp of last state save |
| `accumulated_ms` | integer | Total elapsed milliseconds |
| `iteration` | integer | Last iteration count |
| `last_result` | object\|null | Last evaluation verdict and details |

If the command fails or returns an empty array (`[]`), report:

```
No loop state files found. Nothing to clean.
```

and stop.

---

## Step 2: Gather Detailed Status for Each Loop

For each loop returned in Step 1, run:

```bash
ll-loop status <loop_name> --json 2>/dev/null
```

This produces the same fields as Step 1 plus one additional field:

| Field | Type | Description |
|---|---|---|
| `pid` | integer\|null | PID from `.loops/.running/<loop_name>.pid`; null if no PID file exists |

Also check whether the PID is alive (only when `pid` is non-null):

```bash
kill -0 <pid> 2>/dev/null && echo "alive" || echo "dead"
```

---

## Step 3: Classify Each Loop

Use the current UTC time and the loop's `updated_at` to compute staleness. The staleness
threshold is `${threshold:-15}` minutes.

To compute age in minutes from an ISO 8601 timestamp:

```bash
python3 -c "
from datetime import datetime, timezone
updated = datetime.fromisoformat('$UPDATED_AT'.replace('Z', '+00:00'))
now = datetime.now(timezone.utc)
print(f'{(now - updated).total_seconds() / 60:.1f}')
"
```

Classify each loop into one of the following categories:

### NEEDS CLEANUP — stuck-running

**Condition**: `status == "running"` AND either:
- `pid` is non-null AND the process is dead (`kill -0` returned non-zero), OR
- `updated_at` is older than the threshold

**Action**: Call `ll-loop stop <loop_name>`.
`ll-loop stop` handles all cleanup: sends SIGTERM (then SIGKILL after 10s) if the PID is
still alive, updates `status` to `interrupted`, and deletes the `.pid` file.

### NEEDS CLEANUP — stale-interrupted

**Condition**: `status == "interrupted"` AND `pid` is non-null (orphaned `.pid` file present)

**Action**: Remove the stale `.pid` file:
```bash
rm -f ".loops/.running/<loop_name>.pid"
```
The `.state.json` is preserved for diagnostics.

### NEEDS ATTENTION — abandoned-handoff

**Condition**: `status == "awaiting_continuation"` AND `updated_at` older than the threshold

**Action**: Surface to user in the summary. Do NOT auto-clean; the user may want to resume.

### INFORMATIONAL — terminal

**Condition**: `status` is `"failed"` or `"timed_out"`

**Action**: Report in the summary. These are already in terminal states; their state files
are diagnostic artifacts. Do NOT auto-clean.

### HEALTHY — skip

**Condition**: `status == "running"` AND `pid` alive AND `updated_at` is fresh
**Condition**: `status == "awaiting_continuation"` AND `updated_at` is fresh
**Condition**: `status == "completed"`

**Action**: Skip — leave these loops alone.

---

## Step 4: Display Summary

Print a summary of all discovered loops grouped by category:

```
Loop State Summary
==================

NEEDS CLEANUP (N):
  [1] <loop_name> — stuck-running — status: running — PID: 12345 (dead) — last updated: 47m ago
  [2] <loop_name> — stale-interrupted — status: interrupted — stale PID file — last updated: 2h ago

NEEDS ATTENTION (M):
  [3] <loop_name> — abandoned-handoff — status: awaiting_continuation — last updated: 3h ago

INFORMATIONAL (K):
  [4] <loop_name> — terminal — status: failed — last updated: 1h ago

HEALTHY (J):
  <loop_name> — running — PID 9876 (alive) — last updated: 2m ago
```

If there are no loops in any actionable category (NEEDS CLEANUP or NEEDS ATTENTION), report:

```
No stuck or stale loops found.
<HEALTHY section or "No loops with state files.">
```

and stop.

If `--dry-run` flag is set, stop here — do not proceed to cleanup.

---

## Step 5: Confirm Cleanup

Use `AskUserQuestion` to ask which loops to clean up. Include only loops numbered under
NEEDS CLEANUP in the prompt (NEEDS ATTENTION loops are informational — let the user
address them manually):

```
Clean up N loop(s) marked NEEDS CLEANUP? [Y/n/select]

  Y      — clean up all N loops
  n      — cancel, no changes made
  select — choose which (enter comma-separated numbers from the list above, e.g. 1,2)
```

Handle the response:
- `Y` or empty/enter → clean up all NEEDS CLEANUP loops
- `n` → report "No changes made." and stop
- `select` or comma-separated numbers (e.g. `1,3`) → clean only the listed indices

---

## Step 6: Execute Cleanup

For each loop confirmed for cleanup:

### stuck-running loops

```bash
ll-loop stop <loop_name>
```

If `ll-loop stop` exits with a non-zero code (e.g. the process already died between steps),
report:
```
  [WARN] ll-loop stop exited with error for <loop_name>; loop may have already terminated.
```

### stale-interrupted loops

```bash
rm -f ".loops/.running/<loop_name>.pid"
echo "Removed stale PID file for <loop_name>"
```

---

## Step 7: Inspect Root Cause

For every cleaned loop (both stuck-running and stale-interrupted), tail the events file to
surface what happened just before the failure:

```bash
tail -20 ".loops/.running/<loop_name>.events.jsonl" 2>/dev/null
```

If the events file is missing, note: `(no events file found — loop may not have started)`

Parse and format the last events as a brief timeline. Look for patterns like:
- Last event type (e.g. `state_enter`, `action_complete`, `evaluate`)
- Any `exit_code` != 0 in `action_complete` events
- Any `verdict == "fail"` in `evaluate` events
- Any `terminated_by` values in `loop_complete` events

---

## Step 8: Final Report

For each cleaned loop, display a block:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Loop: <loop_name>   [CLEANED]
  Was stuck in:  <current_state>
  Status:        <status> → interrupted
  Last updated:  <updated_at> (<N> minutes ago)
  Iteration:     <iteration>
  PID:           <pid> (dead) / none

  Last events:
    <ts>  state_enter  state=<state>
    <ts>  action_complete  exit_code=<N>  duration=<N>ms
    ...

  Root cause: <brief interpretation — e.g. "Action exited non-zero in <state> state with
              no further events, suggesting the subprocess crashed or was killed externally.">
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

After all blocks, print a summary line:

```
Cleaned <N> loop(s). <M> loop(s) need attention (see NEEDS ATTENTION above).
```

---

## Usage Examples

```bash
# Discover and clean all stuck/stale loops (with confirmation)
/ll:cleanup-loops

# Preview what would be cleaned without making changes
/ll:cleanup-loops --dry-run

# Use a custom staleness threshold (30 minutes instead of default 15)
/ll:cleanup-loops --threshold 30

# Dry run with custom threshold
/ll:cleanup-loops --dry-run --threshold 60
```
