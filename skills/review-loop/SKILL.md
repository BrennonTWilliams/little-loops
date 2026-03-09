---
description: Review an existing FSM loop configuration for quality, correctness, consistency, and potential improvements. Analyzes all states and transitions, reports findings by severity (Error/Warning/Suggestion), proposes concrete fixes with before/after diffs, and applies approved changes.
allowed-tools:
  - Bash(ll-loop:*)
  - Read
  - Write
  - AskUserQuestion
---

# Review Loop

You are a loop quality reviewer for FSM loop configurations in little-loops. Your job is to audit an existing loop YAML file, surface issues by severity, and help the user improve it with explicit approval before any change.

## Allowed Tools

- `AskUserQuestion` - For interactive prompts (loop selection, fix approvals)
- `Read` - To load loop YAML files and this reference document
- `Write` - To save approved changes back to the loop file
- `Bash` - To run `ll-loop validate`, `ll-loop list`, and `ll-loop show`

## Arguments

- `[name]` (optional): Loop name to review. If omitted, show a list to pick from.
- `--auto`: Non-interactive mode — apply all eligible non-breaking fixes automatically (see `reference.md` Auto-Apply Rules). Still prints the full findings report.
- `--dry-run`: Report findings only. Make no changes, ask no approval questions.

---

## Step 0: Resolve Loop Name

If a loop name was provided as an argument, use it directly and proceed to Step 1.

Otherwise, list available loops:

```bash
ll-loop list
```

Parse the output to get loop names, paradigms, and descriptions. Then ask the user to pick one:

```yaml
questions:
  - question: "Which loop would you like to review?"
    header: "Select Loop"
    multiSelect: false
    options:
      - label: "<name1>"
        description: "<paradigm> — <description first line>"
      - label: "<name2>"
        description: "<paradigm> — <description first line>"
      # one entry per available loop
```

If `ll-loop list` returns no loops, output:

```
No loops found. Create one with /ll:create-loop.
```

And stop.

---

## Step 1: Load and Parse

Read `reference.md` (this companion file) now. You will need the check definitions in Step 2b.

Locate the loop file. Try in order:
1. `{{config.loops.loops_dir}}/<name>.fsm.yaml` (compiled)
2. `{{config.loops.loops_dir}}/<name>.yaml`
3. `loops/<name>.yaml` (built-in)

If no file found, output an error and stop.

Use `Read` to load the YAML. Parse as a raw dict (you do not need to invoke Python — read the YAML text and inspect the keys).

**Format detection**:
- **Paradigm format**: YAML has `paradigm:` key AND lacks `initial:` key
- **Raw FSM format**: YAML has `initial:` key (regardless of whether `paradigm:` is also present)

Record:
- `loop_name`: the `name` field
- `format`: `"paradigm"` or `"raw_fsm"`
- `initial`: the `initial` field (raw FSM only)
- `states`: dict of state names → state configs
- `max_iterations`: numeric value or absent
- `on_handoff`: string value or absent

---

## Step 2a: First-Pass Validation

Run the built-in validator:

```bash
ll-loop validate <name>
```

Parse stdout/stderr:
- Lines containing `[ERROR]` → record as **Error** findings (Check IDs: V-1 through V-16 from `reference.md`)
- Lines containing `[WARNING]` or `⚠` → record as **Warning** findings
- Lines containing `✓` with no errors → record as zero first-pass findings

Each finding: `{ check_id: "V-N", severity: "Error"|"Warning", location: "<path>", message: "<text>" }`

---

## Step 2b: Quality Checks

Run each quality check from `reference.md` against the raw YAML dict. Record findings in the same list.

### QC-1: max_iterations Range

Read `max_iterations` from the YAML dict (absent = 50 default).

- If value < 3: add Warning finding at path `max_iterations`
- If value > 100: add Warning finding at path `max_iterations`
- If key is absent: add Suggestion finding at path `max_iterations`

### QC-2: Missing `on_error` Routing

For each state in `states`:
- Skip if `terminal: true`
- If the state has an `evaluate` block: check for `on_error` at the state level and for `route.error` in a `route` block
- If neither is present: add Warning finding at path `states.<name>`

### QC-3: `action_type` Mismatch

For each state with an `action` field:

**Looks like natural-language prompt** (action text > 10 words, no shell metacharacters: `|`, `&&`, `||`, `$`, `;`, `>`, `<`, backtick, and does not start with a known shell binary):
- If `action_type` is absent or `action_type: shell`: add Suggestion finding

**Looks like shell command** (starts with a known binary or contains `&&`, `|`, `$`):
- If `action_type: prompt`: add Warning finding

### QC-4: Convergence State Missing `on_maintain`

For each state where `evaluate.type == "convergence"`:
- If `on_maintain` is absent at the state level: add Warning finding at path `states.<name>`

### QC-5: Hardcoded User Paths

For each state with an `action` field:
- If `action` contains `/Users/`, `/home/`, or `~/` as a literal string: add Warning finding at path `states.<name>.action`

### QC-6: `on_handoff` Recommendation

Read top-level `on_handoff`. Read `max_iterations` (use 50 if absent).
- If `max_iterations > 20` AND `on_handoff` is absent: add Suggestion finding at path `on_handoff`

### QC-7: `capture` Usage Opportunity

Collect all state action texts. Check if any downstream state action contains `$captured` or `{{captured}}`.
- For each upstream state that has `evaluate.type` in `["output_contains", "output_numeric", "output_json"]` and lacks `capture:`: add Suggestion finding at path `states.<name>`

---

## Step 2c: FSM Flow Review

**Skip this step if**: `--dry-run` flag is set and you want faster output. Otherwise always run after Step 2b.

Read the FA-* check definitions from `reference.md` now. Then perform the following LLM-driven analysis of the FSM's logic and flow.

### 2c-1: Extract Intent

Read the loop's declared purpose:
1. Check for a `description:` YAML key — use its value if present
2. If absent, look for leading YAML comments (lines starting with `#` before the first non-comment key) and parse those as the description
3. If neither found, use `"(no description provided)"` as the intent

### 2c-2: Build FSM Mental Model

From the parsed YAML dict, extract:
- **States list**: all keys in `states`
- **Terminal states**: states where `terminal: true`
- **Non-terminal states**: all states not terminal
- **Initial state**: the `initial` field value
- **Transition map**: for each non-terminal state, collect all routing targets (`on_success`, `on_failure`, `on_partial`, `on_error`, `next`, and any `route.*` values)
- **Inbound map**: for each state, which states transition into it

### 2c-3: Trace Happy Path

Starting from the `initial` state, trace the primary (success) path through `on_success` (or `next`) transitions until reaching a terminal state. If the path forks or loops, note both branches.

Evaluate: does the happy path correctly implement what the `description:` says the loop should do? Note any misalignments.

### 2c-4: Run FSM Anti-Pattern Checks

Run each check from FA-1 through FA-6 in `reference.md`. For each finding, append to the shared findings list using the same format: `{ check_id: "FA-N", severity: "Error"|"Warning"|"Suggestion", location: "<path>", message: "<text>" }`.

**FA-1 — Spin Detection**: For each non-terminal state, check whether ALL of its error/partial transitions route back to itself (or form a tight cycle of ≤ 2 states) with no counter or escape condition. If yes: Warning.

**FA-2 — Missing Failure Terminal**: Scan all terminal states. If none has a name suggesting failure (`failed`, `error`, `aborted`, `bail`, `halt`, or similar), and `max_iterations` is the only stop condition: Warning. Note: a loop with a well-named non-terminal error-handling state (that eventually reaches a failure terminal) does NOT trigger this.

**FA-3 — Unresetting Shared State**: Scan all state `action` texts for writes to `/tmp/` files or shell variables (e.g., `echo ... > /tmp/foo`, `N=0`, `count=0`). For each `/tmp/` path written, check whether any state action resets or removes it at loop start. If a `/tmp` file is written but never reset: Warning at the writing state.

**FA-4 — Monolithic Prompt State**: For each state with `action_type: prompt`, count the number of distinct numbered steps (e.g., "Step 1", "Step 2", or "1.", "2.") in the action text. If ≥ 4 distinct steps: Suggestion that the state may benefit from decomposition into smaller focused states.

**FA-5 — Unreachable States**: For each state not reachable via BFS from `initial`: Warning. **Skip if V-11 already flagged this state** (check existing findings for `V-11` at the same state location to avoid duplicates).

**FA-6 — Dead-End Non-Terminal States**: For each non-terminal state that has no outbound transitions (no `on_success`, `on_failure`, `on_partial`, `on_error`, `next`, or `route`): Error.

### 2c-5: Build Narrative Summary

After running the anti-pattern checks, compose two lists:

**What works well**: List 2–4 specific strengths of the FSM design. Examples:
- Clean evaluate → done/fix split
- Proper use of `on_partial` for ambiguous LLM output
- Ceiling-acceptance in action states that prevents runaway iteration
- `on_handoff: spawn` is appropriate for long-running loops
- Happy path directly matches the declared purpose

**Issues to consider**: List any FA-* findings in plain English with actionable suggestions. If no FA-* findings exist, write `"No significant logic issues found."`

### 2c-6: Output FSM Flow Review

After Step 3 displays the findings table and before Step 4, output this block:

```
### FSM Flow Review: <loop-name>

  <One-sentence overall assessment of whether the flow achieves its declared purpose>

  **What works well**
  - <strength 1>
  - <strength 2>
  ...

  **Issues to consider**
  <N>. <plain-English description of FA-N finding with concrete suggestion>
  ...
  (or "No significant logic issues found." if no FA-* findings)
```

---

## Step 3: Display Findings

Output the full findings report using the format from `reference.md`:

```
## Review: <loop-name>

Format: <Raw FSM | Paradigm (<paradigm>)>
States: <N> states  |  Initial: <initial>  |  Max iterations: <N>

### Errors (N)
| # | Check | Location | Issue |
|---|-------|----------|-------|
...

### Warnings (N)
| # | Check | Location | Issue |
|---|-------|----------|-------|
...

### Suggestions (N)
| # | Check | Location | Issue |
|---|-------|----------|-------|
...
```

If there are zero findings in a severity group, omit that group's section entirely.

After the findings table, output the FSM Flow Review narrative block from Step 2c-6.

If `--dry-run` flag was given: stop here. Output:

```
Dry run complete. No changes made.
```

---

## Step 4: Propose and Apply Fixes

Build a list of proposed fixes — one per actionable finding. Not all findings need a fix proposal (e.g., unreachable states detected by validate have no safe auto-fix without knowing user intent).

For each fix:

### Interactive Mode (default)

Use `AskUserQuestion` for each proposed fix in severity order (Errors first, then Warnings, then Suggestions):

```yaml
questions:
  - question: "Apply fix for [LOCATION]: [brief issue]?"
    header: "Fix #N of M"
    multiSelect: false
    options:
      - label: "Yes, apply"
        description: "<brief before → after description>"
      - label: "No, skip"
        description: "Leave this unchanged"
      - label: "Skip remaining"
        description: "Stop reviewing fixes and go to validation"
```

If user selects "Skip remaining", stop iterating and proceed to Step 5 with changes applied so far.

### `--auto` Mode

Apply all fixes that meet the Auto-Apply Rules from `reference.md` (currently only QC-6: add explicit `on_handoff: pause`). Skip everything else.

Report:
```
Auto-applied N fix(es) (--auto mode):
  ✓ QC-6: on_handoff: pause added
```

---

## Step 5: Validate and Save

**If no fixes were applied**: skip write and validation. Output:

```
No changes made.
```

Then proceed to summary.

**If fixes were applied**:

1. Save the original YAML text as a backup (in memory — do not write to disk).
2. Apply all approved changes to the YAML dict. Preserve comments where possible (write as clean YAML if comments cannot be preserved).
3. Write the updated YAML to the loop file using `Write`.
4. Run validation:

```bash
ll-loop validate <name>
```

**If validation passes**:
```
✓ Validation passed after fixes.
```

**If validation fails**:

```
⚠ Validation failed after applying fixes:
<error message>

Restoring original file...
```

Restore the original YAML using `Write`. Then output:

```
Original file restored. Please review the proposed changes manually.
```

---

## Step 6: Summary Report

```
## Review Complete: <loop-name>

Findings:    <N> error(s), <N> warning(s), <N> suggestion(s)  (includes V-*, QC-*, and FA-* checks)
Fixes applied:  <N> of <M> proposed
Skipped:     <N>

<If all clear:>
✓ Loop passes validation.

<If errors remain unfixed:>
⚠ N error(s) still present. Run /ll:review-loop <name> again to address them.
```

---

## Examples

```bash
# Interactive review — pick from list
/ll:review-loop

# Interactive review of a specific loop
/ll:review-loop fix-types

# Non-interactive: apply safe fixes automatically
/ll:review-loop fix-types --auto

# Report only, no changes
/ll:review-loop fix-types --dry-run
```

---

## Integration

Works well with:
- `/ll:create-loop` — Create new loop configurations (run review after creation to catch issues)
- `ll-loop validate <name>` — Quick schema validation without quality checks
- `ll-loop show <name>` — Inspect states and transitions visually
- `ll-loop simulate <name>` — Trace execution without running actions
