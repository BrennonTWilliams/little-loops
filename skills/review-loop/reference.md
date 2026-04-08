# Review Loop — Quality Checks Reference

This file catalogs all quality checks run by `/ll:review-loop`, their severity levels, and fix templates. Read this file at the start of Step 2b.

---

## Severity Levels

| Level | Meaning | Action |
|-------|---------|--------|
| **Error** | Correctness issue — loop may fail or behave unexpectedly | Always propose fix |
| **Warning** | Best practice violation — loop may work but is fragile | Propose fix; auto-apply safe ones with `--auto` |
| **Suggestion** | Improvement opportunity — loop works fine but could be better | Propose fix; skip in `--auto` unless `breaking: false` and user opts in |

---

## First-Pass Checks (from `ll-loop validate`)

These are surfaced by running `ll-loop validate <name>`. The review skill presents them in the unified findings table. Do **not** re-implement these — just parse the `ll-loop validate` output.

| Check ID | Description | Severity |
|----------|-------------|----------|
| V-1 | Initial state not defined in `states` | Error |
| V-2 | No state with `terminal: true` | Error |
| V-3 | State references undefined state name | Error |
| V-4 | Evaluator missing required fields | Error |
| V-5 | Invalid `operator` value | Error |
| V-6 | Invalid `direction` for convergence | Error |
| V-7 | `tolerance` is negative | Error |
| V-8 | `min_confidence` out of [0, 1] range | Error |
| V-9 | No transition defined (non-terminal state) | Error |
| V-10 | Routing conflict (shorthand + `route` both set) | Warning |
| V-11 | Unreachable state (BFS from initial) | Warning |
| V-12 | `max_iterations <= 0` | Error |
| V-13 | `backoff < 0` | Error |
| V-14 | `timeout <= 0` | Error |
| V-15 | `llm.max_tokens <= 0` | Error |
| V-16 | `llm.timeout <= 0` | Error |

---

## Quality Checks (QC — skill-specific)

### QC-1: max_iterations Range

**Severity**: Warning
**Breaking**: false
**When to auto-apply**: Never (judgment call)

| Condition | Finding |
|-----------|---------|
| `max_iterations < 3` | Warning: Value `N` is suspiciously low — may not allow convergence. Consider 5–20 for simple loops. |
| `max_iterations > 100` | Warning: Value `N` is suspiciously high — a broken loop could run for a long time. Consider capping at 50 unless intentional. |
| Key absent (uses default 50) | Suggestion: `max_iterations` not set; defaulting to 50. Consider setting explicitly for clarity. |

**Fix template** (for high value):
```yaml
# Before
max_iterations: 200

# After (example — suggest based on loop complexity)
max_iterations: 50
```

---

### QC-2: Missing `on_error` Routing

**Severity**: Warning
**Breaking**: false
**When to auto-apply**: Never (routing change affects behavior)

For each non-terminal state:
- If the state has an `evaluate` block with `type: exit_code`, `output_numeric`, `output_json`, `output_contains`, or `convergence`: shell commands can fail unexpectedly
- If `on_error` is absent AND the state has no `route.error` AND the state is not `terminal: true`

**Finding**: `Warning: states.<name>: Missing on_error routing. A shell evaluator failure will be treated as an unhandled error. Consider adding on_error: <error-state> or on_error: $current.`

**Fix template**:
```yaml
# Before
states:
  check:
    action: "ruff check ."
    evaluate:
      type: exit_code
    on_yes: done
    on_no: fix

# After
states:
  check:
    action: "ruff check ."
    evaluate:
      type: exit_code
    on_yes: done
    on_no: fix
    on_error: fix      # or a dedicated error-handling state
```

---

### QC-3: `action_type` Mismatch

**Severity**: Warning (shell-looks-like-prompt, unknown/contributed type), Suggestion (prompt-looks-like-shell)
**Breaking**: false
**When to auto-apply**: Never (behavior change)

Heuristics for detecting mismatches:

**Action looks like a natural-language prompt but `action_type` is absent or `shell`:**
- Action text is > 10 words with no shell metacharacters (`|`, `&&`, `||`, `$`, `;`, `>`, `<`, backtick)
- No command-like prefix (e.g., does not start with a known binary word or `/`)
- Suggestion: `action_type: prompt` may be more appropriate

**Action looks like a shell command but `action_type` is `prompt` or absent:**
- Action text is short and starts with a shell command keyword (`ruff`, `mypy`, `pytest`, `python`, `npm`, `cargo`, `make`, `git`, etc.) or contains `&&`, `|`, `$`
- Suggestion: `action_type: shell` may be more appropriate

**`action_type` is set to an unknown value (not in built-in list):**
- If `action_type` is set to a value not in `["prompt", "slash_command", "shell", "mcp_tool"]`, treat it as a potential contributed type and emit a Warning (not an error)
- Warning: `states.<name>: action_type '<value>' is not a built-in type; if this is a contributed type, ensure it is registered in the extension registry (_contributed_actions) before the loop runs.`
- Contributed action types are dispatched via the extension registry when a matching key is found in `FSMExecutor._contributed_actions`

**Fix template** (natural language → prompt):
```yaml
# Before
states:
  analyze:
    action: "Review the current test failures and identify the root cause"
    # action_type absent — will be run as shell command

# After
states:
  analyze:
    action: "Review the current test failures and identify the root cause"
    action_type: prompt
```

---

### QC-4: Convergence State Missing `on_maintain`

**Severity**: Warning
**Breaking**: false
**When to auto-apply**: Never (needs a real target state name)

For each state with `evaluate.type: convergence`:
- If `on_maintain` is absent: stalls (metric not changing) are not handled

**Finding**: `Warning: states.<name>: Convergence evaluator without on_maintain. If the metric stalls, the loop will retry indefinitely until max_iterations. Consider adding on_maintain: <stall-state> or on_maintain: $current.`

**Fix template**:
```yaml
# Before
states:
  optimize:
    evaluate:
      type: convergence
      target: 0
    on_yes: done
    on_no: fix

# After
states:
  optimize:
    evaluate:
      type: convergence
      target: 0
    on_yes: done
    on_no: fix
    on_maintain: fix   # treat stall same as failure, or route to a dedicated state
```

---

### QC-5: Hardcoded User Paths

**Severity**: Warning
**Breaking**: false
**When to auto-apply**: Never (cannot infer the correct replacement)

For each state with `action_type: shell` or action that appears to be a shell command:
- If `action` contains `/Users/`, `/home/`, or `~/` as a literal string

**Finding**: `Warning: states.<name>: Shell action contains a hardcoded user path ('/Users/...'). Use relative paths or environment variables for portability.`

**Fix template**:
```yaml
# Before
action: "/Users/brennon/scripts/run_checks.sh"

# After
action: "./scripts/run_checks.sh"   # or: "$HOME/scripts/run_checks.sh"
```

---

### QC-6: `on_handoff` Recommendation for Long Loops

**Severity**: Suggestion
**Breaking**: false
**When to auto-apply**: No

If `max_iterations > 20` (explicit) and `on_handoff` is absent from the top-level spec:

**Finding**: `Suggestion: on_handoff not set. With max_iterations > 20, the loop may outlast a Claude session. Consider setting on_handoff: pause (default) or on_handoff: spawn explicitly.`

**Fix template**:
```yaml
# Before
name: my-loop
max_iterations: 50
# on_handoff absent

# After
name: my-loop
max_iterations: 50
on_handoff: pause   # pause and wait for user to resume (default but explicit)
```

---

### QC-7: `capture` Usage Opportunity

**Severity**: Suggestion
**Breaking**: false
**When to auto-apply**: No

For each state with `evaluate.type` that produces output (`output_contains`, `output_numeric`, `output_json`):
- If no `capture:` key is present on the state
- And a downstream state's `action` references `$captured` or `{{captured}}`

**Finding**: `Suggestion: states.<name>: This state produces evaluated output but doesn't capture it. Add capture: <variable_name> to make the output available to downstream states.`

**Fix template**:
```yaml
# Before
states:
  measure:
    action: "python measure.py"
    evaluate:
      type: output_numeric
      operator: lt
      target: 10
    on_yes: done
    on_no: improve

# After
states:
  measure:
    action: "python measure.py"
    evaluate:
      type: output_numeric
      operator: lt
      target: 10
    capture: current_value    # available as $captured in downstream states
    on_yes: done
    on_no: improve
```

---

## FSM Flow Analysis Checks (FA — logic and design)

These checks are run during Step 2c (FSM Flow Review). They evaluate whether the FSM's logic, flow, and design are correct and well-structured — not just whether the YAML is valid. All are performed by LLM reasoning over the parsed YAML, not by the validator.

| Check ID | Description | Severity |
|----------|-------------|----------|
| FA-1 | Spin risk — all error/partial transitions loop back without escape | Warning |
| FA-2 | Missing failure terminal state | Warning |
| FA-3 | Unresetting `/tmp` shared state | Warning |
| FA-4 | Monolithic prompt state (≥ 4 numbered steps) | Suggestion |
| FA-5 | Unreachable state (skip if V-11 already flagged it) | Warning |
| FA-6 | Dead-end non-terminal state (no outbound transitions) | Error |

---

### FA-1: Spin Detection

**Severity**: Warning
**Breaking**: false
**When to auto-apply**: Never (routing change required)

For each non-terminal state: if ALL of its `on_error` and `on_partial` transitions route back to itself (or form a tight cycle of ≤ 2 states) with no counter, escape condition, or alternative path:

**Finding**: `Warning: states.<name>: Spin risk — on_error and on_partial both route back to <name> with no escape. A persistent LLM error or ambiguous output will loop indefinitely until max_iterations.`

**Fix template**:
```yaml
# Before
states:
  evaluate:
    on_yes: done
    on_no: fix
    on_partial: evaluate   # loops back
    on_error: evaluate     # loops back — no escape

# After
states:
  evaluate:
    on_yes: done
    on_no: fix
    on_partial: evaluate
    on_error: error-terminal   # dedicated escape for persistent errors
```

---

### FA-2: Missing Failure Terminal

**Severity**: Warning
**Breaking**: false
**When to auto-apply**: Never (requires adding a new state)

If no terminal state has a name suggesting failure (`failed`, `error`, `aborted`, `bail`, `halt`, or similar), and `max_iterations` is the only stop condition for failure cases:

**Finding**: `Warning: No explicit failure terminal state. When the loop hits max_iterations on a failure path, it stops silently with no signal of failure. Consider adding a terminal state named 'failed' or 'error' for explicit failure signaling.`

**Fix template**:
```yaml
# After (add a failure terminal state)
states:
  ...
  failed:
    terminal: true
  # Then route appropriate on_error transitions to: failed
```

---

### FA-3a: Bare /tmp/ Path (Cross-Project Collision)

**Severity**: Warning
**Breaking**: false
**When to auto-apply**: Yes (mechanical rename; no behavior change within a single project)

Any state action that writes to a bare `/tmp/<name>` path (not `.loops/tmp/`) risks silent data corruption when two projects using little-loops run concurrently on the same machine — they share the global `/tmp/` namespace.

**Finding**: `Warning: states.<name>.action: Writes to bare /tmp/<file>. Use .loops/tmp/<file> instead to scope state to this project's working directory and avoid cross-project collisions.`

**Fix template**:
```yaml
# Before (bare /tmp/ path — collides across projects)
states:
  check_commit:
    action: |
      COUNT=$(cat /tmp/my-count 2>/dev/null || echo 0)
      echo $((COUNT + 1)) > /tmp/my-count

# After (project-scoped path with mkdir guard)
states:
  check_commit:
    action: |
      mkdir -p .loops/tmp
      COUNT=$(cat .loops/tmp/my-count 2>/dev/null || echo 0)
      echo $((COUNT + 1)) > .loops/tmp/my-count
```

---

### FA-3: Unresetting Shared State

**Severity**: Warning
**Breaking**: false
**When to auto-apply**: Never (requires understanding of loop restart behavior)

For each state action that writes to a path (preferably `.loops/tmp/<name>` after FA-3a is applied): if no state action resets or removes that file before the loop's first action (in the `initial` state or an explicit `start`/`init` state):

**Finding**: `Warning: states.<name>.action: Writes to .loops/tmp/<file> but no state resets this file. Shared state persists across loop restarts, which can cause incorrect counts or stale data on retry.`

**Fix template**:
```yaml
# Before (check_commit state writes counter, never reset)
states:
  check_commit:
    action: |
      mkdir -p .loops/tmp
      COUNT=$(cat .loops/tmp/my-count 2>/dev/null || echo 0)
      echo $((COUNT + 1)) > .loops/tmp/my-count

# After (reset in initial state or add a reset state before the write)
states:
  start:
    action: "rm -f .loops/tmp/my-count"
    action_type: shell
    next: check_commit
  check_commit:
    action: |
      mkdir -p .loops/tmp
      COUNT=$(cat .loops/tmp/my-count 2>/dev/null || echo 0)
      echo $((COUNT + 1)) > .loops/tmp/my-count
```

---

### FA-4: Monolithic Prompt State

**Severity**: Suggestion
**Breaking**: false
**When to auto-apply**: Never (decomposition is a structural change)

For each state with `action_type: prompt`: count distinct numbered steps in the action text (lines matching `Step [N]`, `[N].`, `[N])` patterns). If ≥ 4 distinct steps are found:

**Finding**: `Suggestion: states.<name>: Prompt action contains N numbered steps. Consider decomposing into smaller focused states — each state should do one clear thing. Monolithic prompt states are harder to debug and may exceed LLM context limits.`

---

### FA-5: Unreachable States (FSM Analysis)

**Severity**: Warning
**Breaking**: false
**When to auto-apply**: Never

**Only emit this finding if V-11 has NOT already flagged the same state** (check existing findings list for a `V-11` entry at `states.<name>` before adding an FA-5 finding).

For each state not reachable via BFS from the `initial` state (using all outbound transitions):

**Finding**: `Warning: states.<name>: Unreachable state — no transition path leads here from the initial state. This state is dead code.`

---

### FA-6: Dead-End Non-Terminal State

**Severity**: Error
**Breaking**: false
**When to auto-apply**: Never (cannot safely infer the missing transition target)

For each non-terminal state that has no outbound transitions (`on_yes`, `on_no`, `on_partial`, `on_error`, `next`, or any `route.*` key):

**Finding**: `Error: states.<name>: Non-terminal state with no outbound transitions. The FSM will stall here with no way to proceed.`

---

## Findings Display Format

```
## Review: <loop-name>

Format: FSM
States: N states  |  Initial: <initial-state>  |  Max iterations: <N>

### Errors (N)
| # | Check | Location | Issue |
|---|-------|----------|-------|
| 1 | V-2   | states   | No state with terminal: true |

### Warnings (N)
| # | Check | Location | Issue |
|---|-------|----------|-------|
| 1 | V-11  | states.check | Unreachable state |
| 2 | QC-2  | states.evaluate | Missing on_error for shell evaluator |
| 3 | QC-1  | max_iterations | Value 200 is suspiciously high (>100) |
| 4 | FA-1  | states.evaluate | Spin risk — on_error and on_partial both loop back |
| 5 | FA-2  | (loop)   | No explicit failure terminal state |

### Suggestions (N)
| # | Check | Location | Issue |
|---|-------|----------|-------|
| 1 | QC-3  | states.fix | action_type absent; action looks like a natural-language prompt |
| 2 | QC-6  | on_handoff | max_iterations=50 but on_handoff not set explicitly |

### FSM Flow Review: <loop-name>

  <One-sentence overall assessment of whether the flow achieves its declared purpose>

  **What works well**
  - <specific strength — e.g., "evaluate → done/fix split is clean: exits only when all issues pass">
  - <specific strength>

  **Issues to consider**
  1. <Plain-English description of FA-N finding with concrete actionable suggestion>
  2. <Next finding if any>
  (or "No significant logic issues found." if no FA-* findings)
```

---

## Fix Proposal Format

For each finding with a proposed fix, show a before/after diff:

```
Fix #N: <brief title>
  Check: <Check-ID>
  Severity: Error / Warning / Suggestion
  Location: <path>
  Issue: <one sentence>

  Before:
    <relevant YAML section>

  After:
    <proposed YAML section>

  Breaking: Yes / No
```

---

## Programmatic Replacement Checks (PR — deterministic state detection)

These checks are run during Step 2d. They identify `prompt`-type states that perform
deterministic operations — such as file existence checks, counting, or simple formatting —
that could be replaced with cheaper, faster `bash` or `python` states.

All PR findings are **Suggestion**-severity and are never auto-applied.

---

### PR-1: Replaceable LLM Prompt State

**Severity**: Suggestion
**Breaking**: false
**When to auto-apply**: Never (structural change to state type)

For each state where `action_type: prompt` (or where `action_type` is absent and the action looks like a natural-language prompt — more than 10 words, no shell metacharacters):

1. Strip template variables (e.g. `{{variable}}`, `$var`) from the action text and check the remaining literal text against the heuristic groups below.
2. If the action matches any heuristic group AND does not contain any exemption keyword, add a Suggestion finding with check_id `PR-1`.
3. Include the detected pattern label and a concrete alternative in the finding.

#### Heuristic Groups (any match → flag)

| Group | Pattern signals | Suggested replacement |
|-------|----------------|----------------------|
| **A — File/path existence** | Phrases like "does … exist", "check if file", "is there a file", "does the path", "file exists?" — asking a yes/no factual question about filesystem state | `bash` state: `[ -f path ] && echo yes \|\| echo no` |
| **B — Counting/enumeration** | Phrases like "count the number of", "how many", "count all", "total number of", "number of files/lines/matches/errors" | `bash` state: `grep -c pattern file` or `find . \| wc -l` |
| **C — Simple formatting/transformation** | Phrases like "format X as Y", "convert to JSON/YAML/CSV", "format the output as", "output formatted", "print the value of" with a single deterministic output | `bash` state: `jq`, `printf`, or `python -c "import json; ..."` |
| **D — Yes/no decision on structured data** | Phrases like "is the count greater/less/equal to", "does the value exceed", "if X is true/false based on" a numeric or structured value — binary decision with no free-text judgment | `bash` state: `[ "$value" -gt "$threshold" ] && echo yes \|\| echo no` |
| **E — Pure template substitution** | Action consists almost entirely of template variable references (`{{var}}`, `$var`) with fixed connecting text and no analytical instruction | Any `bash` state: `echo "The value is $count"` |
| **F — Simple string/path operations** | Phrases like "extract the filename from", "get the basename of", "strip the extension from", "split on delimiter" | `bash` state: `basename "$path"`, `"${path%.*}"`, `cut -d: -f1` |

#### Exemption Keywords (do NOT flag if any present)

If the action text contains any of the following words, skip the PR-1 check for that state — these indicate genuine language understanding is required:

`summarize`, `summarise`, `analyze`, `analyse`, `review`, `evaluate`, `assess`, `classify`, `categorize`, `categorise`, `identify`, `determine`, `generate`, `suggest`, `recommend`, `explain`, `describe`, `reason`, `infer`, `diagnose`

Also skip if the action text exceeds 50 words — complex multi-step reasoning is unlikely to be purely deterministic.

#### Finding Format

```
Suggestion: states.<name>: Prompt state appears deterministic and could be replaced
with a programmatic state. Detected pattern: <Group label>. Consider replacing with a
bash state: <example command>.
```

#### Fix Template

```yaml
# Example — Group A (file existence)
# Before:
states:
  check_config:
    action: "Does the file config.json exist in the current directory?"
    action_type: prompt
    on_yes: proceed
    on_no: error

# After:
states:
  check_config:
    action: '[ -f config.json ] && echo yes || echo no'
    action_type: shell
    evaluate:
      type: output_contains
      value: "yes"
    on_yes: proceed
    on_no: error

# Example — Group B (counting)
# Before:
states:
  count_errors:
    action: "Count the number of lines containing ERROR in build.log"
    action_type: prompt
    on_yes: done
    on_no: fix

# After:
states:
  count_errors:
    action: "grep -c 'ERROR' build.log 2>/dev/null || echo 0"
    action_type: shell
    evaluate:
      type: output_numeric
      operator: eq
      target: 0
    on_yes: done
    on_no: fix
```

---

## Auto-Apply Rules (`--auto` mode)

In `--auto` mode, apply only fixes that are:
1. `breaking: false`
2. Pure additions (adding a missing field, not changing an existing value)
3. Not routing changes (do not auto-add `on_error`, `on_maintain`, or change `on_yes`/`on_no`)

Eligible for auto-apply in `--auto` mode:
- **QC-6**: Add explicit `on_handoff: pause` if `max_iterations > 20` and `on_handoff` is absent — safe since `pause` is already the default

Everything else requires user approval, including all **PR-*** findings (structural change to state type; cannot be applied without user confirmation).

After auto-applying, report:
```
Auto-applied N fixes (--auto mode):
  ✓ QC-6  on_handoff: pause added (was default, now explicit)
```
