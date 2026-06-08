# goal-cluster → loop-router dispatch bugs

Two blocking bugs discovered via `/ll:audit-loop-run rn-build` (run `2026-06-08T204657`). Together they cause `goal-cluster` to silently route every EPIC to `propose_new_loop` and abort with zero implementation work.

---

## BUG-015 — goal-cluster `load_goals` uses `--format json` (invalid flag), silently skipping EPIC child enumeration

**Type**: bug · **Priority**: P2

### Summary

`goal-cluster`'s `load_goals` state calls `ll-issues list --parent <epic_id> --format json`, but `--format json` is not a valid `ll-issues list` flag. The subprocess silently fails (empty stdout, non-zero exit), the JSON parse falls back to `'[]'`, and the code falls through to the raw-text fallback — yielding `goal_text: "<epic_id>"` as a literal string instead of enumerating the actual child issues.

**Observed**: `goals.json` contains `[{"goal_id": "g01", "goal_text": "EPIC-001", "hints": ""}]` instead of the 12 child feature issues.

### Root Cause

```python
result = subprocess.run(
    ['ll-issues', 'list', '--parent', epic_id, '--format', 'json'],  # BUG: --format json
    capture_output=True, text=True, timeout=30
)
```

The valid flag is `--json` (or `-j`). The failure is silently swallowed by the `except Exception: pass` clause.

### Fix

Change `'--format', 'json'` to `'--json'` in the `load_goals` shell action in `goal-cluster`:

```python
result = subprocess.run(
    ['ll-issues', 'list', '--parent', epic_id, '--json'],
    capture_output=True, text=True, timeout=30
)
```

### Acceptance Criteria

- [ ] `goal-cluster` invoked with `goals=EPIC-001` enumerates child issues into `goals.json`
- [ ] Each goal entry has `goal_id` = child issue ID and `goal_text` = child issue title
- [ ] Empty child list (new EPIC) is handled gracefully with a warning, not a silent fallback

---

## BUG-016 — dispatch_cluster passes context key `input` but loop-router expects context key `goal` → empty GOAL in classify_goal

**Type**: bug · **Priority**: P2

### Summary

`goal-cluster`'s `dispatch_cluster` state passes the goal text to sub-loops via `with: {input: "..."}`. However `loop-router` declares its primary input variable as `goal` (FSM context default: `{"goal": "", ...}`). The variable name mismatch causes `loop-router`'s `classify_goal` action to see `GOAL: ` (empty string), which makes the LLM conclude "no goal provided" and unconditionally route to `propose_new_loop`.

**Observed**: `classify_goal` action preview shows `"GOAL: \n\n"` (empty). LLM output: "No goal was provided — the GOAL field is empty. BRANCH:propose_new".

### Root Cause

In `goal-cluster`'s `dispatch_cluster` state:
```yaml
with:
  input: "${captured.cluster_batch_input.output}"   # BUG: key is 'input'
  schedule_mode: "${context.schedule_mode}"
```

`loop-router` uses `${context.goal}` throughout its action templates, not `${context.input}`. The two loops share no documented protocol contract for the goal variable name.

### Fix

Change the `with` key from `input` to `goal` in `goal-cluster`'s `dispatch_cluster` state:

```yaml
with:
  goal: "${captured.cluster_batch_input.output}"    # FIXED
  schedule_mode: "${context.schedule_mode}"
```

### Acceptance Criteria

- [ ] `loop-router` receives a non-empty `${context.goal}` when dispatched from `goal-cluster`
- [ ] `classify_goal` routes to `score_project_loops` or `score_builtin_loops`, not `propose_new_loop`, for a valid EPIC goal
- [ ] The batch for EPIC-001 dispatches to an appropriate implementation loop (e.g. `autodev` or `auto-refine-and-implement`)

---

_Discovered by `/ll:audit-loop-run rn-build` — run `2026-06-08T204657`._
