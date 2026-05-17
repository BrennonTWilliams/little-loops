---
name: review-loop
description: Use when asked to review loop config quality, validate loop YAML, or audit a loop definition.
disable-model-invocation: true
allowed-tools:
  - Bash(ll-loop:*)
  - Read
  - Write
  - AskUserQuestion
metadata:
  short-description: Review loop quality: validate YAML, behavioral verification, rubric scorecard, artifact persistence
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
- `--exercise`: In addition to `ll-loop simulate`, also run `ll-loop run --max-iterations 1` for behavioral verification (Step 2.5).
- `--no-simulate`: Skip Step 2.5 entirely (no simulation checks).
- `--rubric-only`: Stop after displaying the rubric scorecard in Step 3. No fix proposals, no artifact persistence.
- `--strict-semantic`: In Step 2c, prompt SR-* evaluations as a fresh context using only calibration examples from `reference.md` as anchors — prevents static-check findings from biasing semantic judgment.

---

## Step 0: Resolve Loop Name

If a loop name was provided as an argument, use it directly and proceed to Step 1.

Otherwise, list available loops:

```bash
ll-loop list
```

Parse the output to get loop names and descriptions. Then ask the user to pick one:

```yaml
questions:
  - question: "Which loop would you like to review?"
    header: "Select Loop"
    multiSelect: false
    options:
      - label: "<name1>"
        description: "<description first line>"
      - label: "<name2>"
        description: "<description first line>"
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
- **FSM format**: YAML has `initial:` key — this is the only supported format

**Note on `from:` inheritance**: If the YAML has a top-level `from:` field, the loop inherits its skeleton from another loop. The validator (`ll-loop validate`) and FSM diagram see the *materialized* loop after inheritance and fragment resolution, so quality checks below operate on the merged graph. When reviewing the raw YAML directly (without invoking the loader), keep in mind that `initial:`, `states:`, etc. may be inherited from the parent referenced in `from:`.

Record:
- `loop_name`: the `name` field
- `initial`: the `initial` field
- `states`: dict of state names → state configs
- `max_iterations`: numeric value or absent
- `on_handoff`: string value or absent

---

## Step 1.5: Description Completeness Gate

Check the loop's `description:` field:

1. If `description:` is absent OR fewer than 5 words: draft a description from the FSM structure using the **Description Draft Template** from `reference.md`.
2. Propose the draft as the first fix using the standard fix proposal format. Do NOT silently inject it — always ask for approval (or auto-apply in `--auto` mode, since this is a pure addition).
3. If the draft is accepted, update the in-memory YAML dict for use in Steps 2c and 2.5.

This gate unblocks SR-1 and SR-4, which otherwise skip when `description:` is absent or too short.

If `description:` is already present and 5+ words: skip this step silently.

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

**Unknown/contributed `action_type`** (value not in `["prompt", "slash_command", "shell", "mcp_tool"]`):
- If `action_type` is explicitly set to a value outside the built-in list: add Warning finding at path `states.<name>`
- Warning text: `action_type '<value>' is not a built-in type; if this is a contributed type, ensure it is registered in the extension registry (_contributed_actions) before the loop runs.`
- Do NOT emit an Error; contributed types are valid after schema widening (FEAT-990)

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

Before running QC-8 through QC-13, build the FSM mental model from the YAML dict: record terminal states (where `terminal: true`), the transition map (all routing targets per non-terminal state), the inbound map (which states reach each state), and the happy path (trace `on_yes`/`next` from `initial` to terminal). Use this model in the checks below.

### QC-8: Spin Detection

For each non-terminal state, check whether ALL of its `on_error` and `on_partial` transitions route back to itself (or form a tight cycle of ≤ 2 states) with no counter or escape condition:
- If yes: add Warning finding at path `states.<name>` (check_id: FA-1)

### QC-9: Missing Failure Terminal

Scan all terminal states. If none has a name suggesting failure (`failed`, `error`, `aborted`, `bail`, `halt`, or similar), and `max_iterations` is the only stop condition for failure cases:
- Add Warning finding at path `(loop)` (check_id: FA-2)
- Note: a non-terminal error-handling state that eventually routes to a failure terminal does NOT trigger this

### QC-10: Unresetting Shared State

Scan all state `action` texts for writes to `/tmp/` paths (e.g., `echo ... > /tmp/foo`, `tee /tmp/foo`). For each `/tmp/` path written:

**Cross-project path check (FA-3a)**: If the path matches bare `/tmp/<name>` (i.e., not `.loops/tmp/`), add Warning finding at path `states.<name>.action` (check_id: FA-3a). Bare `/tmp/` paths are shared globally across all projects on the machine — when two projects run concurrently, they collide silently. Use `.loops/tmp/<name>` (project-scoped by CWD) instead.

**Unresetting state check (FA-3)**: Check whether any state action resets or removes the path at loop start (in the `initial` state or an explicit `start`/`init` state):
- If a file is written but never reset: add Warning finding at path `states.<name>.action` (check_id: FA-3)

### QC-11: Monolithic Prompt State

For each state with `action_type: prompt`, count distinct numbered steps in the action text (lines matching `Step [N]`, `[N].`, `[N])`):
- If ≥ 4 distinct steps: add Suggestion finding at path `states.<name>` (check_id: FA-4)

### QC-12: Unreachable States

For each state not reachable via BFS from `initial` using all outbound transitions:
- Skip if V-11 already flagged this state (check existing findings for `V-11` at the same location)
- Otherwise: add Warning finding at path `states.<name>` (check_id: FA-5)

### QC-13: Dead-End Non-Terminal States

For each non-terminal state that has no outbound transitions (`on_yes`, `on_no`, `on_partial`, `on_blocked`, `on_error`, `next`, any `route.*`, or any custom `on_<verdict>` in `extra_routes`):
- Add Error finding at path `states.<name>` (check_id: FA-6)

### QC-14: Replaceable Prompt State Detection

For each state where `action_type: prompt` OR where `action_type` is absent and the action looks like a natural-language prompt (more than 10 words, no shell metacharacters: `|`, `&&`, `||`, `$`, `;`, `>`, `<`, backtick):

1. Strip template variable references (`{{...}}`, `$identifier`) from the action text, leaving only literal words.
2. Check the literal text against the **Heuristic Groups** defined in `reference.md` (PR-1): file/path existence (Group A), counting (Group B), simple formatting (Group C), yes/no decision on structured data (Group D), pure template substitution (Group E), and simple string/path operations (Group F).
3. Check for **Exemption Keywords** defined in `reference.md` (PR-1): if any exemption keyword is present in the action text, skip this state.
4. Also skip if the action text exceeds 50 words.
5. If a heuristic group matches and no exemption applies: add a Suggestion finding at path `states.<name>` with check_id `PR-1`, naming the detected pattern group and providing an example alternative.

**Do not output any findings yet.** Proceed to Step 2c to build the narrative, then Step 2.5 for behavioral verification, then Step 3 to display everything.

---

## Step 2c: FSM Flow Review Narrative

Build the narrative summary using the FA findings and mental model from Step 2b. This step always runs — even when FA findings count is zero, the narrative must be written.

### 2c-1: Extract Intent

Read the loop's declared purpose:
1. Check for a `description:` YAML key — use its value if present
2. If absent, look for leading YAML comments (lines starting with `#` before the first non-comment key)
3. If neither found, use `"(no description provided)"` as the intent

### 2c-2: Build Narrative Summary

Compose two lists:

**What works well**: List 2–4 specific strengths of the FSM design. Examples:
- Clean evaluate → done/fix split
- Proper use of `on_partial` for ambiguous LLM output
- Ceiling-acceptance in action states that prevents runaway iteration
- `on_handoff: spawn` is appropriate for long-running loops
- Happy path directly matches the declared purpose

**Issues to consider**: List any FA-* and SR-* findings in plain English with actionable suggestions. If no FA-* or SR-* findings exist, write `"No significant logic issues found."`

### 2c-3: Semantic Flow Review Checks

Using the FSM mental model built before QC-8 and the declared intent from 2c-1, perform semantic analysis. Produce SR-* findings using the same `{ check_id, severity, location, message }` schema as other findings. Reuse the already-traced happy path.

**SR-1: Happy-Path Goal Alignment**
Trace `on_yes`/`next` from `initial` to terminal (already computed for QC-12). Compare the names and action texts of states along this path to the declared goal. If the path does not plausibly accomplish the declared purpose (e.g., state names and actions describe unrelated work, or the path terminates before the goal is met), add a Warning finding at path `(loop)` with check_id `SR-1`. Skip if `description:` is absent or fewer than 5 words.

**SR-2: State Name vs. Action Coherence**
For each state on or adjacent to the happy path: compare the state name to its action text. If the name implies a narrow gate (`check_*`, `verify_*`, `validate_*`) but the action is broad, open-ended analysis (more than ~15 words with no specific criterion), or the name implies active multi-step work but the action is a simple yes/no decision — add a Suggestion finding at path `states.<name>` with check_id `SR-2`.

**SR-3: Semantically Backwards Transition**
For each non-terminal state: if its `on_yes` transition routes to a state that appears earlier in the happy path (success routing backward), add a Warning finding at path `states.<name>` with check_id `SR-3`. A success outcome routing backward is almost always a logic error.

**SR-4: Goal Coverage Gap**
Extract 2–4 key activity phrases from the declared goal (skip if goal is absent or fewer than 5 words). For each distinct named activity (verb + object, e.g., "commit changes", "run tests"): if no state's name or action text corresponds to it, add a Warning finding at path `(loop)` with check_id `SR-4`.

### 2c-4: Output FSM Flow Review

After Step 3 displays the findings table and before Step 4, output both blocks:

```
### FSM Flow Review: <loop-name>

  <One-sentence overall assessment of whether the flow achieves its declared purpose>

  **What works well**
  - <strength 1>
  - <strength 2>
  ...

  **Issues to consider**
  <N>. <plain-English description of FA-N or SR-N finding with concrete suggestion>
  ...
  (or "No significant logic issues found." if no FA-* or SR-* findings)

### Semantic Flow Review: <loop-name>

  **Loop goal**: "<declared description or (no description provided)>"
  **Happy path**: <state-1> → <state-2> → ... → <terminal>
    <✓ or ⚠> <one-line assessment of whether path achieves the declared goal>

  **State analysis**:
    <For each state on the happy path:>
    <✓ or ⚠> `<name>` — <brief assessment of name/action coherence>

  **Transition analysis**:
    <For each significant routing decision:>
    <✓ or ⚠> <transition description> — <semantic assessment>

  **Goal alignment**: <one-sentence overall verdict>
```

---

## Step 2.5: Behavioral Verification

**Skip this step if `--no-simulate` flag is set.** Record `simulation_result: "skipped"` in the artifact.

Run the simulator to check behavioral correctness:

```bash
ll-loop simulate <name>
```

Parse the `=== Summary ===` block at the end of stdout for these signals (see `reference.md` Simulation Checks for full patterns):

**SIM-1 (Stall)**: `States visited:` contains a repeated state AND `Terminated by: max_iterations`
- Add Warning finding at path `(loop)` with check_id `SIM-1`

**SIM-2 (Premature terminal)**: `Iterations:` value is 1 or 2 AND `Terminated by: terminal` AND loop `max_iterations > 5`
- Add Warning finding at path `(loop)` with check_id `SIM-2`

**SIM-3 (Exceeds max_iterations)**: `Terminated by: max_iterations` (regardless of states visited — this is not SIM-1 which requires a stall cycle)
- Add Error finding at path `(loop)` with check_id `SIM-3`

Record `simulation_result` for the artifact:
- `"terminal"` — simulation reached a terminal state
- `"max_iterations"` — simulation hit max_iterations
- `"error"` — simulate command failed with an unexpected error

**If `--exercise` flag is set**, also run:
```bash
ll-loop run --max-iterations 1 <name>
```
Report any unexpected errors from the real run in findings with check_id `SIM-3` (reuse the same Error severity).

---

## Step 3: Display Findings

Output the full findings report using the format from `reference.md`:

```
## Review: <loop-name>

Format: FSM
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

If there are zero findings in a severity group, omit that group's section entirely. If all three groups are empty, output:

```
No V-*, QC-*, or SR-* findings.
```

**Then always output the FSM Flow Review and Semantic Flow Review blocks from Step 2c-4.** These blocks are required even when all findings counts are zero — they may surface FA-* and SR-* findings and always include the narrative summary.

**After the findings table and FSM Flow Review blocks, always output the rubric scorecard:**

Rate each of the 6 dimensions from `reference.md` Rubric Dimensions (1–5). Check if `.loops/reviews/<name>-*.md` exists — if so, read the most recent artifact's `scorecard:` frontmatter and add trend arrows (↑ if score improved, ↓ if decreased, → if unchanged). Output the scorecard using the Scorecard Display Format from `reference.md`.

If `--rubric-only` flag was given: stop here after outputting the scorecard. Output:

```
Rubric-only mode. No fixes proposed.
```

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

Apply all fixes that meet the Auto-Apply Rules from `reference.md` (currently only QC-6: add explicit `on_handoff: pause`). Skip everything else, including all PR-1 (replaceable prompt state) suggestions — these require structural changes that need user approval.

Report:
```
Auto-applied N fix(es) (--auto mode):
  ✓ QC-6: on_handoff: pause added
```

---

## Step 4.5: Post-Fix Iteration

**Skip this step if no fixes were applied in Step 4.**

After fixes are applied, re-run a lightweight check pass (Steps 2a and 2b only — skip Step 2c and Step 2.5 to control cost) and compare results against the original findings.

For each finding in the post-fix pass that was NOT present in the original findings (same `check_id` AND same `location`):
- Add a Warning finding with check_id `RT-1` at that location (see `reference.md` RT-1 for finding format)

Repeat up to **3 rounds** maximum. Stop when:
- No new RT-1 findings are detected in the post-fix pass, OR
- Round 3 is complete (even if RT-1 findings remain)

Report rounds:
```
Post-fix iteration round N/3:
  <N new findings / "No regressions detected">
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

Findings:    <N> error(s), <N> warning(s), <N> suggestion(s)  (includes V-*, QC-*, FA-*, and SR-* checks)
Fixes applied:  <N> of <M> proposed
Skipped:     <N>

<If all clear:>
✓ Loop passes validation.

<If errors remain unfixed:>
⚠ N error(s) still present. Run /ll:review-loop <name> again to address them.
```

---

## Step 6.5: Persist Review Artifact

**Skip this step if `--dry-run` or `--rubric-only` flag was given.**

Persist the review results to `.loops/reviews/<name>-<YYYYMMDD-HHMMSS>.md`.

Use `%Y%m%d-%H%M%S` timestamp format (e.g., `loop-specialist-eval-20260517-143207.md`).

Build the artifact using the **Review Artifact Schema** from `reference.md`:
- Frontmatter: `loop`, `reviewed_at`, `scorecard` (all 6 dims + composite), `findings_count`, `simulation_result`, `fixes_applied`
- Body: findings table, rubric justifications, simulation summary, before/after fix diffs

Create the `.loops/reviews/` directory if it does not exist.

Write the artifact using `Write`. Report:
```
Review artifact saved: .loops/reviews/<name>-<timestamp>.md
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

# Rubric scorecard only (no fix proposals)
/ll:review-loop fix-types --rubric-only

# Include real execution (1 iteration) in behavioral verification
/ll:review-loop fix-types --exercise

# Skip simulation entirely
/ll:review-loop fix-types --no-simulate

# Strict semantic mode (fresh context for SR-* evaluations)
/ll:review-loop fix-types --strict-semantic
```

---

## Integration

Works well with:
- `/ll:create-loop` — Create new loop configurations (run review after creation to catch issues)
- `ll-loop validate <name>` — Quick schema validation without quality checks
- `ll-loop show <name>` — Inspect states and transitions visually
- `ll-loop simulate <name>` — Trace execution without running actions
