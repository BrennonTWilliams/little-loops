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
| V-12 | `max_steps <= 0` | Error |
| V-13 | `backoff < 0` | Error |
| V-14 | `timeout <= 0` | Error |
| V-15 | `llm.max_tokens <= 0` | Error |
| V-16 | `llm.timeout <= 0` | Error |
| V-17 | Missing top-level `description:` field | Warning |
| MR-1 | Meta-loop (writes harness artifacts or imports `lib/benchmark.yaml`) has no non-LLM evaluator; suppress with `meta_self_eval_ok: true` (ENH-1665) | Error |
| MR-2 | Meta-loop lacks measure→propose→apply→re-measure spine: no captured baseline referenced in any evaluator; suppress with `meta_self_eval_ok: true` (ENH-1665) | Warning |
| MR-3 | Loop writes intermediate artifacts to shared `.loops/tmp/` instead of `${context.run_dir}/`; suppress with `shared_state_ok: true` | Warning |
| MR-4 | LLM-judged state maps `on_yes` but has no route for `no`/`partial` verdicts — dead-ends the loop (parent reads as failed); suppress with `partial_route_ok: true` (ENH-1917) | Warning |
| MR-5 | Harness loop writes artifacts to flat paths in iterative cycles without per-iteration versioning; suppress with `artifact_versioning: true` (snapshot artifacts) or `artifact_versioning_ok: true` (intentional overwrite) (ENH-1957) | Warning |
| MR-6 | Meta-loop has a `shell` state writing to the same file path as an LLM-generator state — hand-patching anti-pattern; fix the generator action, or suppress with `generator_fix_ok: true` (ENH-2079) | Warning |
| MR-7 | FSM action string contains unescaped `${ns.path:-default}` (bash `:-` default); runtime crash. Use `${ns.path:default=value}` or `$${VAR:-value}`; suppress with `bash_default_ok: true` (ENH-2348) | Error |
| MR-8 | `check_semantic`/`llm_structured` state prompt omits evidence-contract keywords (`verbatim`, `quote`, `evidence`) — verdicts may default to optimism (SHOR Table 1: 33–55% accuracy); suppress with `evidence_contract_ok: true` (ENH-2342) | Warning |
| V-18 | State's `loop:` reference does not resolve to any file (typo, renamed loop, missing sibling) — fails at runtime after expensive setup; caught at definition time (BUG-2305) | Warning |

---

## Skill-Side Quality Check Procedures (Step 2b)

These are the step-by-step procedures the skill runs in Step 2b against the raw
YAML dict. QC-1 through QC-7 emit their own check_ids; QC-8 through QC-14 are the
skill's pass that *produces* the FA-* and PR-1 findings whose definitions and fix
templates appear later in this file. Run them in order.

### QC-1: max_steps Range

Read `max_steps` from the YAML dict (absent = 50 default).

- If value < 3: add Warning finding at path `max_steps`
- If value > 100: add Warning finding at path `max_steps`
- If key is absent: add Suggestion finding at path `max_steps`

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

Read top-level `on_handoff`. Read `max_steps` (use 50 if absent).
- If `max_steps > 20` AND `on_handoff` is absent: add Suggestion finding at path `on_handoff`

### QC-7: `capture` Usage Opportunity

Collect all state action texts. Check if any downstream state action contains `$captured` or `{{captured}}`.
- For each upstream state that has `evaluate.type` in `["output_contains", "output_numeric", "output_json"]` and lacks `capture:`: add Suggestion finding at path `states.<name>`

Before running QC-8 through QC-13, build the FSM mental model from the YAML dict: record terminal states (where `terminal: true`), the transition map (all routing targets per non-terminal state), the inbound map (which states reach each state), and the happy path (trace `on_yes`/`next` from `initial` to terminal). Use this model in the checks below.

### QC-8: Spin Detection

For each non-terminal state, check whether ALL of its `on_error` and `on_partial` transitions route back to itself (or form a tight cycle of ≤ 2 states) with no counter or escape condition:
- If yes: add Warning finding at path `states.<name>` (check_id: FA-1)

### QC-9: Missing Failure Terminal

Scan all terminal states. If none has a name suggesting failure (`failed`, `error`, `aborted`, `bail`, `halt`, or similar), and `max_steps` is the only stop condition for failure cases:
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
2. Check the literal text against the **Heuristic Groups** defined below (PR-1): file/path existence (Group A), counting (Group B), simple formatting (Group C), yes/no decision on structured data (Group D), pure template substitution (Group E), and simple string/path operations (Group F).
3. Check for **Exemption Keywords** defined below (PR-1): if any exemption keyword is present in the action text, skip this state.
4. Also skip if the action text exceeds 50 words.
5. If a heuristic group matches and no exemption applies: add a Suggestion finding at path `states.<name>` with check_id `PR-1`, naming the detected pattern group and providing an example alternative.

---

## Quality Checks (QC — skill-specific)

### QC-1: max_steps Range

**Severity**: Warning
**Breaking**: false
**When to auto-apply**: Never (judgment call)

| Condition | Finding |
|-----------|---------|
| `max_steps < 3` | Warning: Value `N` is suspiciously low — may not allow convergence. Consider 5–20 for simple loops. |
| `max_steps > 100` | Warning: Value `N` is suspiciously high — a broken loop could run for a long time. Consider capping at 50 unless intentional. |
| Key absent (uses default 50) | Suggestion: `max_steps` not set; defaulting to 50. Consider setting explicitly for clarity. |

**Fix template** (for high value):
```yaml
# Before
max_steps: 200

# After (example — suggest based on loop complexity)
max_steps: 50
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

**Finding**: `Warning: states.<name>: Convergence evaluator without on_maintain. If the metric stalls, the loop will retry indefinitely until max_steps. Consider adding on_maintain: <stall-state> or on_maintain: $current.`

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
action: "/Users/you/scripts/run_checks.sh"

# After
action: "./scripts/run_checks.sh"   # or: "$HOME/scripts/run_checks.sh"
```

---

### QC-6: `on_handoff` Recommendation for Long Loops

**Severity**: Suggestion
**Breaking**: false
**When to auto-apply**: No

If `max_steps > 20` (explicit) and `on_handoff` is absent from the top-level spec:

**Finding**: `Suggestion: on_handoff not set. With max_steps > 20, the loop may outlast a Claude session. Consider setting on_handoff: pause (default) or on_handoff: spawn explicitly.`

**Fix template**:
```yaml
# Before
name: my-loop
max_steps: 50
# on_handoff absent

# After
name: my-loop
max_steps: 50
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

**Finding**: `Warning: states.<name>: Spin risk — on_error and on_partial both route back to <name> with no escape. A persistent LLM error or ambiguous output will loop indefinitely until max_steps.`

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

If no terminal state has a name suggesting failure (`failed`, `error`, `aborted`, `bail`, `halt`, or similar), and `max_steps` is the only stop condition for failure cases:

**Finding**: `Warning: No explicit failure terminal state. When the loop hits max_steps on a failure path, it stops silently with no signal of failure. Consider adding a terminal state named 'failed' or 'error' for explicit failure signaling.`

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

## Semantic Flow Checks (SR — goal alignment and semantic coherence)

These checks are run during Step 2c (Semantic Flow Review sub-step). They evaluate whether the FSM's states and transitions make semantic sense relative to the loop's declared purpose — questions a structural linter cannot answer. All are performed by LLM reasoning over the parsed YAML, not by the validator.

| Check ID | Description | Severity |
|----------|-------------|----------|
| SR-1 | Happy-path goal alignment — happy path does not plausibly achieve declared purpose | Warning |
| SR-2 | State name vs. action coherence — name implies gate/check but action is broad analysis (or vice versa) | Suggestion |
| SR-3 | Semantically backwards transition — `on_yes` routes to an earlier happy-path state | Warning |
| SR-4 | Goal coverage gap — declared goal names an activity with no corresponding state | Warning |

---

### SR-1: Happy-Path Goal Alignment

**Severity**: Warning
**Breaking**: false
**When to auto-apply**: Never

Trace `on_yes`/`next` from `initial` to terminal (the happy path). Compare the names and action texts of states along that path to the loop's declared `description:`. If the path does not plausibly accomplish the declared purpose — for example, state names and actions describe unrelated work, or the path terminates before the goal is met — this signals that the FSM's main flow has drifted from its stated intent.

Skip if `description:` is absent or too generic (fewer than 5 words).

**Finding**: `Warning: (loop): Happy path (<path>) does not appear to accomplish the declared goal: "<description>". State names and actions along the path do not relate to the key activities described.`

---

### SR-2: State Name vs. Action Coherence

**Severity**: Suggestion
**Breaking**: false
**When to auto-apply**: Never

For each state on or adjacent to the happy path: compare the state name to its action text. Flag a mismatch if:
- The name implies a narrow gate or decision (`check_*`, `verify_*`, `validate_*`) but the action is broad, open-ended analysis (more than ~15 words with no clear criterion for "done"); or
- The name implies active, multi-step work but the action is a simple yes/no decision with a specific criterion.

A well-designed state should have a name that accurately reflects what its action does.

**Finding**: `Suggestion: states.<name>: State name implies <gate/analysis> but action text describes <analysis/gate>. Consider renaming the state or refocusing its action to reduce ambiguity.`

---

### SR-3: Semantically Backwards Transition

**Severity**: Warning
**Breaking**: false
**When to auto-apply**: Never

For each non-terminal state in the loop: if its `on_yes` transition routes to a state that appears *earlier* in the happy path (i.e., success routes backward to a previous step), this is almost always a logic error. A "yes" outcome should signal progress and route forward; backward routing on success typically means the transition condition is inverted or the routing targets are swapped.

**Finding**: `Warning: states.<name>: on_yes routes to '<target>', which precedes '<name>' in the happy path. A success outcome routing backward is likely a logic error — on_yes should route forward toward the terminal state.`

---

### SR-4: Goal Coverage Gap

**Severity**: Warning
**Breaking**: false
**When to auto-apply**: Never

Extract 2–4 key activity phrases from the declared `description:` (e.g., "commit changes", "run tests", "send notification"). For each distinct named activity (verb + object): check whether any state's name or action text corresponds to that activity. If a named activity has no corresponding state, the FSM cannot fulfill its declared goal.

Skip if `description:` is absent or too generic (fewer than 5 words). Skip individual activities if they are implicit side effects rather than explicit steps (e.g., "until done", "as needed").

**Finding**: `Warning: (loop): Goal mentions "<activity>" but no state appears to perform this action. The FSM may not fully accomplish its declared purpose.`

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
| 3 | QC-1  | max_steps | Value 200 is suspiciously high (>100) |
| 4 | FA-1  | states.evaluate | Spin risk — on_error and on_partial both loop back |
| 5 | FA-2  | (loop)   | No explicit failure terminal state |
| 6 | SR-1  | (loop)   | Happy path does not accomplish declared goal |
| 7 | SR-3  | states.verify | on_yes routes backward to an earlier happy-path state |
| 8 | SR-4  | (loop)   | Goal mentions "commit and push" but no state covers this |

### Suggestions (N)
| # | Check | Location | Issue |
|---|-------|----------|-------|
| 1 | QC-3  | states.fix | action_type absent; action looks like a natural-language prompt |
| 2 | QC-6  | on_handoff | max_steps=50 but on_handoff not set explicitly |
| 3 | SR-2  | states.check_done | State name implies gate but action is broad open-ended analysis |

### FSM Flow Review: <loop-name>

  <One-sentence overall assessment of whether the flow achieves its declared purpose>

  **What works well**
  - <specific strength — e.g., "evaluate → done/fix split is clean: exits only when all issues pass">
  - <specific strength>

  **Issues to consider**
  1. <Plain-English description of FA-N or SR-N finding with concrete actionable suggestion>
  2. <Next finding if any>
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
- **QC-6**: Add explicit `on_handoff: pause` if `max_steps > 20` and `on_handoff` is absent — safe since `pause` is already the default

Everything else requires user approval, including all **PR-*** findings (structural change to state type; cannot be applied without user confirmation).

After auto-applying, report:
```
Auto-applied N fixes (--auto mode):
  ✓ QC-6  on_handoff: pause added (was default, now explicit)
```

---

## Simulation Checks (SIM — behavioral verification)

These checks are run during Step 2.5 (Behavioral Verification). They evaluate whether the loop behaves correctly when `ll-loop simulate` runs its FSM. Parse the `=== Summary ===` block at the end of simulate stdout.

| Check ID | Phase | Severity | Trigger |
|----------|-------|----------|---------|
| SIM-1 | 2.5 | Warning | Simulation stalls before reaching any terminal state (cycle detected in `States visited:`) |
| SIM-2 | 2.5 | Warning | Terminal reached in <2 iterations when `max_steps > 5` (no-op happy path) |
| SIM-3 | 2.5 | Error | Simulation exceeds `max_steps` without reaching a terminal state |

### Parsing `ll-loop simulate` stdout

The `=== Summary ===` block always appears at end of stdout. Key lines to parse:

| Signal | Pattern | Notes |
|--------|---------|-------|
| SIM-1 (stall) | `States visited:` contains a repeated state name AND `Terminated by: max_steps` | Check for a cycle in the `→`-separated list |
| SIM-2 (premature terminal) | `Iterations: 1` or `Iterations: 2` AND `Terminated by: terminal` | Only flag when `max_steps > 5` |
| SIM-3 (exceeds max_steps) | `Terminated by: max_steps` (parse stdout regardless of exit code) | Exit code 1 is non-unique; must parse stdout |

**Exit code note**: `scripts/little_loops/cli/loop/_helpers.py:EXIT_CODES` — exit code 1 covers `max_steps`, `timeout`, and `cycle_detected`. Do not use exit code alone to distinguish SIM-3; always parse stdout.

### SIM-1: Simulation Stall

**Severity**: Warning
**When to auto-apply**: Never

**Finding**: `Warning: (loop): Simulation stalls — verify state loops back on on_no with no escape condition. A persistent failure will reach max_steps without terminating. Check on_no routing or add a failure terminal state.`

---

### SIM-2: Premature Terminal

**Severity**: Warning
**When to auto-apply**: Never

**Finding**: `Warning: (loop): Simulation terminated in <N> iteration(s) on a max_steps=<M> loop. The happy path may be a no-op (actions complete immediately with no meaningful work). Verify that the loop exercises its intended behavior before terminating.`

---

### SIM-3: Exceeds max_steps

**Severity**: Error
**When to auto-apply**: Never

**Finding**: `Error: (loop): Simulation hit max_steps (<N>) without reaching a terminal state. The loop has no viable exit path on the default scenario. Review routing conditions and ensure a terminal state is reachable.`

---

## Post-Fix Regression Check (RT)

This check is run during Step 4.5 (Post-Fix Iteration). It surfaces new issues that were introduced by applied fixes.

| Check ID | Phase | Severity | Trigger |
|----------|-------|----------|---------|
| RT-1 | 4.5 | Warning | Post-fix pass surfaces a new finding not present before fixes were applied |

### RT-1: Regression After Fix

**Severity**: Warning
**When to auto-apply**: Never

For each finding present in the post-fix re-check that was NOT present in the original findings list (same check_id AND same location):

**Finding**: `Warning: <location>: New finding after fix — <check_id>: <message>. A previously applied fix may have introduced this issue. Review before proceeding.`

---

## Rubric Dimensions (Step 3 Scorecard)

Rate each dimension 1–5 and compute composite score /30. Include trend arrows (↑/↓/→) when a prior `.loops/reviews/<name>-*.md` artifact exists and has a `scorecard:` frontmatter field.

| Score | Meaning |
|-------|---------|
| 5 | Exemplary — no issues, actively well-designed |
| 4 | Good — minor gaps only |
| 3 | Adequate — works but has notable weaknesses |
| 2 | Weak — significant issues affecting reliability |
| 1 | Poor — severe problems; loop likely fails or misleads |

### Dimension 1: Clarity of Intent

Does `description:` concisely state a testable, specific goal? Does the happy path match the description?

- **5**: Description is specific and testable ("Fix type errors until mypy exits 0"); happy path directly implements it
- **4**: Description is clear but happy path has minor deviations
- **3**: Description is vague or generic; path plausibly relates but isn't tight
- **2**: Description and path are loosely related at best
- **1**: `description:` absent, or path has no relationship to declared goal

### Dimension 2: Decomposition

Are states focused single-purpose units? (FA-4 inverse)

- **5**: Each state does exactly one thing; no state has ≥4 numbered steps
- **4**: States are mostly focused; one borderline monolithic state
- **3**: One or two states are doing multiple things
- **2**: Several states are monolithic or mixed-concern
- **1**: Most states are monolithic prompt-walls

### Dimension 3: Resilience

Are `on_error`, `on_partial`, failure terminals, and handoff all explicitly handled?

- **5**: Every non-terminal state has `on_error`; explicit failure terminal; `on_handoff` set
- **4**: Most error paths handled; one gap
- **3**: Some error handling; no failure terminal
- **2**: Minimal error handling; spin risk present (FA-1)
- **1**: No error routing; guaranteed to hang on any failure

### Dimension 4: Observability

Do state names, capture fields, and evaluators enable debugging from logs alone?

- **5**: Descriptive state names; captures named meaningfully; evaluators use structured output
- **4**: Mostly clear; one or two opaque names
- **3**: Some state names are generic (`check`, `step1`); minimal captures
- **2**: State names are cryptic; no captures; evaluator output not preserved
- **1**: Cannot determine what happened from logs

### Dimension 5: Idempotence

Is shared state reset on loop restart? Does the loop tolerate mid-run interruption?

- **5**: No shared state; or all `/tmp`/`.loops/tmp/` writes are reset in initial state
- **4**: Shared state reset for most paths; one edge case
- **3**: Shared state present but only partially reset
- **2**: FA-3 flagged; stale state on restart produces incorrect results
- **1**: Loop is non-restartable; shared state guaranteed to corrupt on retry

### Dimension 6: Cost-Efficiency

Are deterministic operations programmatic (not LLM prompts)? Is `max_steps` proportionate?

- **5**: All deterministic ops are shell states; `max_steps` is tight and justified
- **4**: Mostly efficient; one PR-1 candidate
- **3**: A few replaceable prompt states; `max_steps` somewhat generous
- **2**: Several PR-1 findings; `max_steps` high relative to loop complexity
- **1**: Loop uses LLM for work that bash could do; `max_steps` excessive

### Scorecard Display Format

```
### Quality Scorecard: <loop-name>

| Dimension           | Score | <trend> | Notes |
|---------------------|-------|---------|-------|
| Clarity of Intent   |  N/5  |   ↑     | <one-line rationale> |
| Decomposition       |  N/5  |   →     | <one-line rationale> |
| Resilience          |  N/5  |   ↓     | <one-line rationale> |
| Observability       |  N/5  |         | <one-line rationale> |
| Idempotence         |  N/5  |         | <one-line rationale> |
| Cost-Efficiency     |  N/5  |         | <one-line rationale> |
| **Composite**       | **N/30** |      | |

<Trend column present only when prior artifact exists. Omit entire column if no prior.>
```

---

## Calibration Examples (SR-* Checks)

Each SR-* check includes one good and one bad example from real little-loops built-in loops to anchor LLM judgment.

### SR-1: Happy-Path Goal Alignment

**Good example** — `harness-optimize.yaml`
```
description: "Iteratively optimize the harness eval loop until score reaches 85/100"
Happy path: score → apply → verify → done
```
Every state name directly relates to the declared goal ("optimize", "score", "apply").

**Bad example** — `broken-verify-loop.yaml`
```
description: "Seeded broken fixture: verify state self-loops via on_no (ambiguous-output failure mode)"
Happy path: verify → done
```
The happy path does not accomplish the declared goal of demonstrating the broken behavior (it terminates on yes without triggering the loop stall).

---

### SR-2: State Name vs. Action Coherence

**Good example** — `outer-loop-eval.yaml`
State `check_score` has action `python scripts/score.py --output json` — narrow gate name, narrow targeted action.

**Bad example** — `semantic-incoherent-state.yaml`
State `check_quality` has action that is a 20-word open-ended analysis prompt — gate name implies a specific pass/fail criterion but action performs broad free-form review.

---

### SR-3: Semantically Backwards Transition

**Good example** — `loop-specialist-eval.yaml`
`on_yes` from `evaluate` routes to `done` (terminal) — success progresses forward.

**Bad example** — `semantic-backwards-transition.yaml`
`on_yes` from a mid-path state routes back to an earlier state — success regresses to a state already passed, almost always a logic inversion.

---

### SR-4: Goal Coverage Gap

**Good example** — `outer-loop-eval.yaml`
Description says "score → apply → verify"; states `score`, `apply`, `verify` all exist.

**Bad example** — `semantic-goal-gap.yaml`
Description mentions "commit and push changes" but no state name or action contains "commit" or "push" — the FSM cannot fulfill its declared goal.

---

## Review Artifact Schema (Step 6.5)

Artifacts are persisted to `.loops/reviews/<name>-<YYYYMMDD-HHMMSS>.md`.

Use `%Y%m%d-%H%M%S` timestamp format (e.g., `loop-name-20260517-143207.md`), matching the convention in `scripts/little_loops/cli/loop/run.py`.

### Frontmatter

```yaml
---
loop: <name>
reviewed_at: <ISO 8601 UTC timestamp, e.g. 2026-05-17T14:32:07Z>
scorecard:
  clarity: <1-5>
  decomposition: <1-5>
  resilience: <1-5>
  observability: <1-5>
  idempotence: <1-5>
  cost_efficiency: <1-5>
  composite: <6-30>
findings_count:
  errors: <N>
  warnings: <N>
  suggestions: <N>
simulation_result: <"terminal" | "max_steps" | "skipped" | "error">
fixes_applied: <N>
---
```

### Body

```markdown
# Review: <loop-name> — <YYYYMMDD-HHMMSS>

## Findings Table
<paste findings table from Step 3>

## Rubric Justifications
<paste scorecard table from Step 3>

## Simulation Summary
<paste simulation output summary from Step 2.5, or "Simulation skipped (--no-simulate)">

## Fixes Applied
<before/after diffs for each applied fix, or "No fixes applied">
```

---

## Description Draft Template (Step 1.5)

When `description:` is absent or fewer than 5 words, draft a description from the FSM structure using this template:

```
<verb phrase based on initial state action> until <terminal state condition>
```

Examples:
- Initial state runs `pytest`, terminal is `done` → `"Run pytest until all tests pass"`
- Initial state runs `ruff check`, on_no loops back → `"Fix lint errors until ruff check exits 0"`
- Initial state is `score` with `evaluate.type: convergence` → `"Iteratively improve score until convergence target is met"`

Propose the draft as a fix in Step 1.5 before proceeding to Step 2c. Do NOT silently inject it into the YAML — always propose it as a fix with the standard approval flow.
