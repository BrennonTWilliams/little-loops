# FSM Quick Reference & Advanced Configuration

## Loop Type State Structures

Reference for the state structures each loop type generates. Use this when generating the Summary preview in Step 4.

> **Notation Legend:**
> - `->` (arrow) means "transitions to" (conceptual representation)
> - `on_yes -> done` is equivalent to YAML: `on_yes: done`
> - `route[target] -> done` represents a routing table entry: `route: { target: done }`
> - `[terminal]` marks a state that ends the loop
>
> **Two YAML syntaxes for routing:**
> 1. **Shorthand** (for standard success/failure/error verdicts):
>    ```yaml
>    on_yes: "done"
>    on_no: "fix"
>    ```
> 2. **Full routing table** (for custom verdicts):
>    ```yaml
>    route:
>      target: "done"
>      progress: "apply"
>      _: "done"      # default for unmatched verdicts
>      _error: "error" # fallback for evaluation errors
>    ```

### Fix Until Clean
```
States: evaluate, fix, done
Initial: evaluate

Transitions:
  evaluate:
    - on_yes -> done
    - on_no -> fix
    - on_error -> fix
  fix:
    - next -> evaluate
  done: [terminal]
```

### Drive a Metric
```
States: measure, apply, done
Initial: measure

Transitions:
  measure:
    - route[target] -> done
    - route[progress] -> apply
    - route[stall] -> done
  apply:
    - next -> measure
  done: [terminal]
```

### Maintain Constraints
For each constraint `{name}` in order:
```
States: check_{name1}, fix_{name1}, check_{name2}, fix_{name2}, ..., all_valid
Initial: check_{first_constraint}

Transitions:
  check_{name}:
    - on_yes -> check_{next} (or all_valid if last)
    - on_no -> fix_{name}
  fix_{name}:
    - next -> check_{name}
  all_valid: [terminal]
    - next -> check_{first} (if daemon/maintain mode)
```

### Run a Sequence
For each step in order:
```
States: step_0, step_1, ..., step_N, check_done, done
Initial: step_0

Transitions:
  step_N:
    - next -> step_{N+1} (or check_done if last)
  check_done:
    - on_yes -> done
    - on_no -> step_0
  done: [terminal]
```

### Harness (Multi-Item variant)
```
States: discover, execute, [check_concrete], [check_mcp], [check_skill], [check_semantic], [check_invariants], advance, done
Initial: discover

Transitions:
  discover:
    - on_yes -> execute
    - on_no -> done
  execute:
    - next -> check_concrete (or check_mcp / check_skill / check_semantic / check_invariants / advance if earlier phases omitted)
  check_concrete:          (present if tool-based gates enabled)
    - on_yes -> check_mcp (or check_skill / check_semantic / check_invariants / advance)
    - on_no -> execute
  check_mcp:               (present if MCP tool gates enabled)
    - route[success] -> check_skill (or check_semantic / check_invariants / advance)
    - route[tool_error] -> execute
    - route[not_found] -> check_skill (skip gate — server not configured)
    - route[timeout] -> execute
  check_skill:             (present if skill-based evaluation enabled)
    action: "/ll:<skill-name> <task-description>"
    action_type: slash_command
    timeout: 300
    evaluate.type: llm_structured
    - on_yes -> check_semantic (or check_invariants / advance; omit check_semantic when check_skill covers quality)
    - on_no -> execute
  check_semantic:          (present if LLM-as-judge enabled; can omit when check_skill covers quality)
    - on_yes -> check_invariants (or advance / done)
    - on_no -> execute
  check_invariants:        (present if diff invariants enabled)
    - on_yes -> advance
    - on_no -> execute
  advance:
    - next -> discover
  done: [terminal]
```

**`check_skill` field reference:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `action` | `str` | yes | Slash command (e.g. `/ll:act-as-user 'verify ...'`) or plain prompt |
| `action_type` | `slash_command \| prompt` | recommended | `slash_command` for `/ll:*` commands; `prompt` for free-form instructions |
| `timeout` | `int` | no | Seconds before abort. Recommended: 120–300 |
| `evaluate.type` | `llm_structured` | yes | Parses natural-language skill output for YES/NO verdict |
| `evaluate.prompt` | `str` | yes | Question posed to the LLM evaluator about the skill's output |
| `on_yes` | `str` | yes | State to transition to on pass |
| `on_no` | `str` | yes | State to transition to on fail (typically `execute` for retry) |

**`check_skill` vs `check_mcp` comparison:**

| | `check_mcp` | `check_skill` |
|---|---|---|
| `action_type` | `mcp_tool` | `slash_command` or `prompt` |
| Evaluator | `mcp_result` (envelope routing) | `llm_structured` (YES/NO text) |
| Latency | ~500ms | 30–300s |
| Capability | Single deterministic tool call | Full agentic Claude session |
| Best for | External state verification | End-to-end user flow simulation |

### Harness (Single-Shot variant)
```
States: execute, [check_concrete], [check_mcp], [check_skill], [check_semantic], [check_invariants], done
Initial: execute

Transitions:
  execute:
    - next -> check_concrete (or check_mcp / check_skill / check_semantic / check_invariants / done)
  check_concrete:          (present if tool-based gates enabled)
    - on_yes -> check_mcp (or check_skill / check_semantic / check_invariants / done)
    - on_no -> execute
  check_mcp:               (present if MCP tool gates enabled)
    - route[success] -> check_skill (or check_semantic / check_invariants / done)
    - route[tool_error] -> execute
    - route[not_found] -> check_skill (skip gate)
    - route[timeout] -> execute
  check_skill:             (present if skill-based evaluation enabled)
    - on_yes -> check_semantic (or check_invariants / done)
    - on_no -> execute
  check_semantic:          (present if LLM-as-judge enabled; can omit when check_skill covers quality)
    - on_yes -> check_invariants (or done)
    - on_no -> execute
  check_invariants:        (present if diff invariants enabled)
    - on_yes -> done
    - on_no -> execute
  done: [terminal]
```

---

## FSM Summary Examples

**Example summaries by loop type:**

Fix until clean (with output_contains evaluator):
```
## Summary
States: evaluate -> fix -> done
Transitions:
  evaluate: success->done, failure->fix, error->fix
  fix: next->evaluate
  done: [terminal]
Initial: evaluate
Max iterations: 10
Evaluator: output_contains [pattern: "0 errors"]
```

Fix until clean (default exit_code):
```
## Summary
States: evaluate -> fix -> done
Transitions:
  evaluate: success->done, failure->fix, error->fix
  fix: next->evaluate
  done: [terminal]
Initial: evaluate
Max iterations: 10
Evaluator: exit_code (default)
```

Drive a metric:
```
## Summary
States: measure -> apply -> done
Transitions:
  measure: target->done, progress->apply, stall->done
  apply: next->measure
  done: [terminal]
Initial: measure
Max iterations: 50
Evaluator: convergence [toward: 0, tolerance: 0]
```

Maintain constraints (with per-constraint evaluators):
```
## Summary
States: check_tests -> fix_tests -> check_types -> fix_types -> check_lint -> fix_lint -> all_valid
Transitions:
  check_tests: success->check_types, failure->fix_tests
  fix_tests: next->check_tests
  check_types: success->check_lint, failure->fix_types
  fix_types: next->check_types
  check_lint: success->all_valid, failure->fix_lint
  fix_lint: next->check_lint
  all_valid: [terminal]
Initial: check_tests
Max iterations: 50
Evaluators:
  check_tests: exit_code (default)
  check_types: output_contains [pattern: "Success"]
  check_lint: exit_code (default)
```

Run a sequence (with 3 steps):
```
## Summary
States: step_0 -> step_1 -> step_2 -> check_done -> done
Transitions:
  step_0: next->step_1
  step_1: next->step_2
  step_2: next->check_done
  check_done: success->done, failure->step_0
  done: [terminal]
Initial: step_0
Max iterations: 20
Evaluator: output_numeric [operator: eq, target: 0]
```

---

## Quick Reference

### Template Quick Reference

| Template | Loop Type | Best For |
|----------|-----------|----------|
| Fix until clean | Fix until clean | Any check+fix cycle: tests, lint, type errors |
| Maintain constraints | Maintain constraints | CI-like multi-check validation |
| Run a sequence of steps | Run a sequence | Multi-stage pipelines and ordered workflows |
| Harness a skill or prompt | Harness | Recurring quality improvements with a skill |

**When to use templates:**
- You want a working loop quickly
- Your use case matches a common pattern
- You're new to loop creation

**When to build custom:**
- You have unique check/fix commands
- You need metric-based loops (drive a metric)
- You need step-sequence loops (run a sequence)

### Loop Type Decision Tree

```
What are you trying to do?
|
|- Fix a specific problem -> Fix until clean
|   "Run check, if fails run fix, repeat until passes"
|
|- Maintain multiple standards -> Maintain constraints
|   "Check A, fix A if needed, check B, fix B if needed, ..."
|
|- Reduce/increase a metric -> Drive a metric
|   "Measure value, if not at target, apply fix, measure again"
|
'- Run ordered steps -> Run a sequence
    "Do step 1, do step 2, check if done, repeat if not"
```

### Common Configurations

**Quick lint fix:**
```yaml
name: "quick-lint-fix"
initial: evaluate
max_iterations: 5
states:
  evaluate:
    action: "ruff check src/"
    on_yes: done
    on_no: fix
    on_error: fix
  fix:
    action: "ruff check --fix src/"
    next: evaluate
  done:
    terminal: true
```

**Full quality gate:**
```yaml
name: "full-quality-gate"
initial: check_types
max_iterations: 30
states:
  check_types:
    action: "mypy src/"
    on_yes: check_lint
    on_no: fix_types
  fix_types:
    action: "/ll:manage-issue bug fix"
    next: check_types
  check_lint:
    action: "ruff check src/"
    on_yes: check_tests
    on_no: fix_lint
  fix_lint:
    action: "ruff check --fix src/"
    next: check_lint
  check_tests:
    action: "pytest"
    on_yes: all_valid
    on_no: fix_tests
  fix_tests:
    action: "/ll:manage-issue bug fix"
    next: check_tests
  all_valid:
    terminal: true
```

**Coverage improvement:**
```yaml
name: "improve-coverage"
initial: measure
max_iterations: 20
states:
  measure:
    action: "pytest --cov=src --cov-report=term | grep TOTAL | awk '{print $4}' | tr -d '%'"
    evaluate:
      type: convergence
      toward: 80
      tolerance: 1
    route:
      target: done
      progress: apply
      stall: done
  apply:
    action: "/ll:manage-issue feature implement"
    next: measure
  done:
    terminal: true
```

**Stall detection (diff_stall evaluator):**
```yaml
# Add to any harness loop to skip items that produce no code changes
check_stall:
  action: "echo checking"
  action_type: shell
  evaluate:
    type: diff_stall
    scope: ["scripts/"]  # optional: limit to specific paths
    max_stall: 2         # optional: default 1
  on_yes: advance
  on_no: skip_item  # stalled — move to next item
```

| Verdict | Meaning |
|---------|---------|
| `success` | Diff changed since last call, or below max_stall threshold |
| `failure` | Diff identical for max_stall consecutive iterations (stalled) |
| `error` | `git` command unavailable or returned non-zero |

---

### Advanced State Configuration

#### action_type (Optional)

The `action_type` field explicitly controls how an action is executed. In most cases, you can omit this field and the default heuristic works correctly.

**Values:**
- `prompt` - Execute action as a Claude prompt via Claude CLI
- `slash_command` - Execute action as a Claude slash command via Claude CLI
- `shell` - Execute action as a bash shell command
- (omit) - Uses heuristic: actions starting with `/` are slash commands, others are shell commands

**When to use:**
- **Plain prompts**: You want to send a plain prompt to Claude (not a slash command) that doesn't start with `/`
- **Explicit shell commands**: You have a command starting with `/` that should run in shell (not via Claude CLI)
- **Clarity**: You want to explicitly document the execution type in the YAML

**Example - Plain prompt (no leading `/`):**
```yaml
name: "fix-with-plain-prompt"
initial: evaluate
max_iterations: 10
states:
  evaluate:
    action: "ruff check src/"
    on_yes: done
    on_no: fix
    on_error: fix
  fix:
    action: "Please fix all lint errors in the src/ directory"
    action_type: prompt  # Explicitly mark as prompt since it doesn't start with /
    next: evaluate
  done:
    terminal: true
```

**Example - Shell command starting with `/`:**
```yaml
name: "run-specific-script"
initial: evaluate
max_iterations: 5
states:
  evaluate:
    action: "/usr/local/bin/check.sh"
    action_type: shell  # Run via shell, not Claude CLI, despite leading /
    on_yes: done
    on_no: fix
    on_error: fix
  fix:
    action: "/usr/local/bin/fix.sh"
    action_type: shell
    next: evaluate
  done:
    terminal: true
```

**Most users can omit this field** - the default heuristic covers the common case where slash commands start with `/` and shell commands don't.

#### agent (Optional)

The `agent:` field passes `--agent <name>` to the Claude subprocess for `action_type: prompt` states. It loads `.claude/agents/<name>.md`, picking up that agent's system prompt and tool set (including any MCP tools listed in its `allowed-tools` frontmatter).

**Type:** string

**When to use:** When a state needs to run under a specialized agent file — e.g., an eval state that requires Playwright via an `exploratory-user-eval` agent, or a research state scoped to read-only tools via a dedicated agent definition.

**Example:**
```yaml
execute:
  action: |
    Run the exploratory evaluation as defined in the agent file.
  action_type: prompt
  agent: exploratory-user-eval    # loads --agent flag → picks up Playwright tools
  next: validate
```

> **Note:** `agent:` is ignored for `action_type: shell` states.

#### tools (Optional)

The `tools:` field passes `--tools <csv>` to the Claude subprocess for `action_type: prompt` states. It explicitly scopes the available tools without requiring a full agent file.

**Type:** list of strings

**When to use:** When you want to restrict a state to a minimal tool set (e.g., `["Read", "Bash"]`) without creating a dedicated agent file. Also useful for granting specific MCP tool patterns (e.g., `["Read", "mcp__playwright__*"]`).

**Example:**
```yaml
validate:
  action: |
    Check the output file for correctness.
  action_type: prompt
  tools: ["Read", "Bash"]          # scopes to Read + Bash only
  on_yes: done
  on_no: fix
```

> **Note:** `tools:` is ignored for `action_type: shell` states. For full agent file loading, prefer `agent:` instead.

#### on_handoff (Optional)

The `on_handoff` field configures loop behavior when context handoff signals are detected during execution. Context handoff occurs when a slash command needs more context than available in the current session.

**Values:**
- `pause` (default) - Pause loop execution when handoff detected, requiring manual resume
- `spawn` - Automatically spawn a new continuation session to continue loop execution
- `terminate` - Terminate the loop when handoff detected

**When to use:**
- **pause** (default): For loops where you want manual control before continuing after a context handoff
- **spawn**: For automated loops that should continue seamlessly across context boundaries (e.g., long-running quality gates)
- **terminate**: For loops where context handoff indicates an unrecoverable state

**Example - Spawn continuation sessions:**
```yaml
name: "automated-quality-fix"
initial: evaluate
max_iterations: 20
on_handoff: "spawn"  # Automatically continue in new session if context runs out
states:
  evaluate:
    action: "pytest && mypy src/ && ruff check src/"
    on_yes: done
    on_no: fix
    on_error: fix
  fix:
    action: "/ll:manage-issue bug fix"
    next: evaluate
  done:
    terminal: true
```

**Example - Terminate on handoff:**
```yaml
name: "quick-check-guardian"
initial: check_types
max_iterations: 10
on_handoff: "terminate"  # Stop if we run out of context
states:
  check_types:
    action: "mypy src/"
    on_yes: all_valid
    on_no: fix_types
  fix_types:
    action: "/ll:manage-issue bug fix"
    next: check_types
  all_valid:
    terminal: true
```

**Most users can omit this field** - the default `pause` behavior is appropriate for most interactive use cases.

#### scope (Optional)

The `scope` field declares which files or directories a loop operates on. It is a **loop-level** field (not per-state) used by `ll-parallel` to prevent concurrent loops from conflicting over the same resources.

**Type:** `list[str]` — file or directory paths relative to the project root

**How it works:**
- When `ll-parallel` starts a loop, it acquires a lock for the declared scope paths
- If another loop's scope overlaps, the second loop waits until the first releases its lock
- An empty `scope` (or omitting it) is treated as the whole project — it will conflict with any other scoped loop
- Paths are compared by prefix overlap, so `scope: ["src/"]` conflicts with `scope: ["src/utils/"]`

**When to use:**
- You run multiple loops concurrently via `ll-parallel` and each loop touches distinct areas of the codebase
- A loop modifies specific directories and you want to prevent file conflicts with sibling loops
- You are building a loop that should be safely parallelizable

**Example - Loop scoped to a subdirectory:**
```yaml
name: "fix-api-types"
initial: evaluate
max_iterations: 10
scope:
  - "src/api/"
states:
  evaluate:
    action: "mypy src/api/"
    on_yes: done
    on_no: fix
    on_error: fix
  fix:
    action: "/ll:manage-issue bug fix"
    next: evaluate
  done:
    terminal: true
```

**Example - Multiple paths:**
```yaml
name: "frontend-quality"
initial: check_lint
max_iterations: 20
scope:
  - "src/frontend/"
  - "tests/frontend/"
states:
  check_lint:
    action: "npx eslint src/frontend/"
    on_yes: check_types
    on_no: fix_lint
  fix_lint:
    action: "npx eslint --fix src/frontend/"
    next: check_lint
  check_types:
    action: "npx tsc --noEmit"
    on_yes: all_valid
    on_no: fix_types
  fix_types:
    action: "/ll:manage-issue bug fix"
    next: check_types
  all_valid:
    terminal: true
```

**Most users can omit this field** — it is only needed when running loops in parallel via `ll-parallel`. Single-loop use cases do not require scope declaration.

#### import (Optional)

The `import` field lists fragment library YAML files to load before states are parsed. Paths are resolved relative to the loop file's directory.

**Type:** `list[str]` — library file paths (e.g. `["lib/common.yaml"]`)

**When to use:**
- You want to reference shared state fragments defined in a separate library file
- Multiple loops should share the same canonical fragment definitions

**Example:**
```yaml
name: "my-loop"
initial: lint
import:
  - lib/common.yaml       # loads shell_exit, retry_counter, etc.
states:
  lint:
    fragment: shell_exit
    action: "ruff check ."
    on_yes: done
    on_no: fix
  fix:
    action: "/ll:check-code fix"
    next: lint
  done:
    terminal: true
```

Import paths are resolved relative to the importing loop file's directory. For built-in loops in `scripts/little_loops/loops/`, `lib/common.yaml` resolves to `scripts/little_loops/loops/lib/common.yaml`.

#### fragments (Optional)

The `fragments` field defines named partial state definitions inline in the loop file, without a separate library file.

**Type:** `object` — keys are fragment names; values are partial state dicts

**Precedence:** Local `fragments:` overrides any imported fragment with the same name.

**When to use:**
- The fragment is specific to one loop and not worth sharing across files
- You want to keep everything in a single YAML file

**Example:**
```yaml
name: "my-loop"
initial: check
fragments:
  my_gate:
    action_type: shell
    evaluate:
      type: exit_code
states:
  check:
    fragment: my_gate
    action: "npm test"
    on_yes: done
    on_no: fix
  fix:
    action: "/ll:manage-issue bug fix"
    next: check
  done:
    terminal: true
```

#### loop (Optional)

The `loop` field declares a state as a **sub-loop invocation** — instead of running an action, the executor loads and runs another loop YAML as a child FSM. The parent routes based on the child's terminal outcome.

**Type:** `str` — name of a loop YAML file (resolved via `.loops/<name>.yaml`)

**Mutually exclusive with:** `action` — a state cannot have both `loop` and `action` set.

**Related field:** `context_passthrough` (boolean, default `false`) — when `true`, parent context variables and captured data are passed to the child loop, and child captures are merged back into the parent under the state name.

**When to use:**
- You have well-tested sub-loops and want to compose them into a higher-level workflow
- You want to avoid duplicating state logic across multiple loop YAMLs
- You need shared context between parent and child loops

**Example — Compose lint-fix and test-suite sub-loops:**
```yaml
name: "code-review"
initial: fix_lint
max_iterations: 10
states:
  fix_lint:
    loop: lint-fix                # runs .loops/lint-fix.yaml
    context_passthrough: true
    on_success: run_tests
    on_failure: escalate
  run_tests:
    loop: test-suite              # runs .loops/test-suite.yaml
    on_success: done
    on_failure: escalate
  escalate:
    action: "echo 'Sub-loop failed'"
    action_type: shell
    terminal: true
    verdict: failure
  done:
    terminal: true
```

**Routing:**
- `on_success` (alias for `on_yes`): child reached a terminal state **named `done`** (`terminated_by: "terminal"` and `final_state: "done"`)
- `on_failure` (alias for `on_no`): child reached a non-`done` terminal (e.g. `final_state: "failed"`), or terminated by max_iterations, timeout, or signal; also fires for `terminated_by: "error"` when `on_error` is not set
- `on_error`: child loop YAML not found or invalid, **or** child terminated with `terminated_by: "error"` (runtime failure) when `on_error` is defined

**Context passthrough details:**
- Parent `context` + `captured` are merged into child's `context` before execution
- After child completes, child `captured` values are stored in parent's `captured[<state_name>]`

#### fragment (Optional)

The `fragment` field references a named partial state definition from an imported library (`import:`) or the loop's own `fragments:` block. Fragment fields are merged into the state at **parse time** — state-level keys win at every nesting level, including nested objects like `evaluate`.

**Type:** `str` — name of a fragment defined in `import:` libraries or the local `fragments:` block.

**Related top-level keys:** `import:` (load library files) and `fragments:` (define inline fragments).

**Mutually exclusive with:** nothing — `fragment:` composes freely with `action`, `capture`, `on_yes`, `timeout`, and any other state field.

**When to use:**
- The same `action_type` + `evaluate` combination appears in many states
- You want a single canonical definition that multiple loops can share
- You need to vary only one sub-field (e.g. `evaluate.target`) while inheriting the rest

**Example — import and use a fragment:**
```yaml
import:
  - lib/common.yaml       # provides shell_exit

states:
  check_tests:
    fragment: shell_exit  # inherits action_type: shell + evaluate.type: exit_code
    action: "pytest"
    timeout: 600
    on_yes: done
    on_no: fix_tests
```

**Deep-merge example — override only one nested field:**
```yaml
fragments:
  numeric_gate:
    action_type: shell
    evaluate:
      type: output_numeric
      operator: lt
      target: 3

states:
  strict_check:
    fragment: numeric_gate
    action: "wc -l errors.txt"
    evaluate:
      target: 1            # overrides only target; type and operator from fragment
    on_yes: done
    on_no: fail
```

#### on_partial (Optional)

The `on_partial` field is a **state-level** shorthand for routing when an action returns a `partial` verdict. It works alongside `on_yes`, `on_no`, and `on_error` as a one-line alternative to a full `route:` block.

**Type:** `str` — name of the state to transition to on a `partial` verdict

**When is `partial` returned?**

The `partial` verdict is returned by the `llm_structured` evaluator when Claude reports that progress was made but the goal is not yet complete. It is distinct from `failure` (no progress) and `success` (goal met).

**When to use:**
- Your loop uses `llm_structured` evaluation and you want different behavior for partial progress vs. outright failure
- You want to route partial progress to a different fix state than full failure (e.g., a lighter-weight fix action)
- You want to count partial iterations separately or transition to a reporting state

**Example A — FSM YAML without `on_partial` (partial routes to fix):**
```yaml
name: "refine-issues"
initial: evaluate
max_iterations: 15
states:
  evaluate:
    action: "/ll:verify-issues"
    on_yes: done
    on_no: fix
    on_error: fix
    evaluate:
      type: llm_structured
  fix:
    action: "/ll:refine-issue"
    next: evaluate
  done:
    terminal: true
```

**Example B — FSM YAML with `on_partial` for finer routing:**
```yaml
states:
  evaluate:
    action: "/ll:verify-issues"
    on_yes: done
    on_no: deep_fix
    on_partial: quick_fix   # partial progress → lighter fix
  quick_fix:
    action: "/ll:refine-issue"
    next: evaluate
  deep_fix:
    action: "/ll:manage-issue feature implement"
    next: evaluate
  done:
    terminal: true
initial: evaluate
max_iterations: 15
```

**Most users can omit this field** — if you do not need distinct routing for partial progress, use `on_no` to handle both failure and partial outcomes, or use a full `route:` block for fine-grained control.

#### capture (Optional)

The `capture` field stores a state's action output in a named variable that later states can reference via `${captured.<name>.output}` interpolation. It is a **state-level** field that enables data passing between states without external files.

**Type:** `str` — variable name to store the output under

**What is captured:**

When `capture: <varname>` is set on a state, the following are stored after the action runs:
- `${captured.<varname>.output}` — stdout from the action
- `${captured.<varname>.stderr}` — stderr from the action
- `${captured.<varname>.exit_code}` — exit code as a string
- `${captured.<varname>.duration_ms}` — execution time in milliseconds

**When to use:**
- A later state's action needs the output of an earlier state (e.g., pass a list of files, an error summary, or a computed value)
- You want to pass dynamic data between states without writing to temp files
- Your loop has a measure → act → report flow where the act and report states need the measure output

**Example - Capture metric output and use it in the fix action:**
```yaml
states:
  measure:
    action: "ruff check src/ 2>&1 | grep -c 'error' || echo 0"
    capture: lint_result
    on_yes: done
    on_no: fix
  fix:
    action: "echo 'Found ${captured.lint_result.output} errors, fixing...' && ruff check --fix src/"
    next: measure
  done:
    terminal: true
initial: measure
max_iterations: 20
```

**Example - Capture issue list for targeted fix:**
```yaml
states:
  scan:
    action: "ll-issues list --json"
    capture: open_issues
  apply:
    action: "/ll:manage-issue feature implement ${captured.open_issues.output}"
    next: scan
  done:
    terminal: true
initial: scan
max_iterations: 10
```

**Most users can omit this field** — capture is needed only when states must share dynamic data. For static configuration, use the `context:` block at the loop level instead.

#### max_retries and on_retry_exhausted (Optional, paired)

The `max_retries` and `on_retry_exhausted` fields provide first-class per-state retry limiting. When a state is entered consecutively more than `max_retries` times (i.e., it keeps routing back to itself), the executor automatically transitions to `on_retry_exhausted` instead of executing the state again.

**Fields:**
- `max_retries` (integer, minimum 1) — max number of retries allowed after the initial execution. A value of N means the state executes at most N+1 times consecutively before exhaustion.
- `on_retry_exhausted` (string) — state to transition to when retry limit is exceeded. Required when `max_retries` is set.

Both fields must be set together (one without the other is a validation error).

**When to use:**
- Your loop processes multiple items and one bad item might loop indefinitely
- You want to skip a stuck item and move on rather than burning the global `max_iterations` budget
- You are building a harness loop where each item gets a fixed number of attempts

**How it works:**
- The executor tracks consecutive re-entries per state in an internal counter
- On each entry to a state, if the previous state was the same, the counter increments
- If the counter exceeds `max_retries`, the state is skipped and `on_retry_exhausted` is used instead
- The counter resets when a different state is entered

**Example — Multi-item loop with per-item retry limit:**
```yaml
name: "refine-with-retry-limit"
initial: execute
max_iterations: 100
states:
  execute:
    action: "/ll:refine-issue ${current_item}"
    action_type: prompt
    max_retries: 3
    on_retry_exhausted: skip_item
    on_yes: evaluate
    on_no: execute   # retries up to 3 times before skip
  evaluate:
    action: "/ll:confidence-check ${current_item}"
    on_yes: done
    on_no: execute
  skip_item:
    action: echo "Skipping ${current_item} after 3 failed retries"
    action_type: shell
    next: done
  done:
    terminal: true
```

**Most users can omit these fields** — they are useful only when a state might loop indefinitely on bad input and you want automatic skip behavior instead of exhausting the global iteration budget.

---

### Sub-Loop Composition
```
States: <sub_loop_state_1>, <sub_loop_state_2>, ..., done
Initial: <sub_loop_state_1>

Transitions:
  <sub_loop_state_1>:
    - on_success -> <sub_loop_state_2> (or done if last)
    - on_failure -> escalate (or error handler)
  <sub_loop_state_2>:
    - on_success -> done
    - on_failure -> escalate
  escalate: [terminal, verdict: failure]
  done: [terminal]
```

Sub-loop composition summary example:
```
## Summary
States: fix_lint -> run_tests -> done
Transitions:
  fix_lint: success->run_tests, failure->escalate
  run_tests: success->done, failure->escalate
  escalate: [terminal, verdict: failure]
  done: [terminal]
Initial: fix_lint
Max iterations: 10
Sub-loops: lint-fix, test-suite
```

---

## RL Loop State Structures

### rl-bandit — Epsilon-Greedy Bandit

```
States: explore, exploit, reward, done
Initial: explore

Transitions:
  explore:  next -> reward
  exploit:  next -> reward
  reward:   route[target] -> done
            route[progress] -> exploit
            route[stall] -> explore
  done:     [terminal]
```

Key fields:
- `explore` / `exploit`: `action_type: shell`, `capture: round_result`, `next: reward`
- `reward`: `action_type: shell`, `evaluate.type: convergence`, `direction: maximize`, `route: {target, progress, stall}`
- `context.reward_target`: convergence target (0.0–1.0)

---

### rl-rlhf — Generate → Score → Refine

```
States: generate, score, refine, done
Initial: generate

Transitions:
  generate: next -> score
  score:    on_yes -> done
            on_no -> refine
            on_error -> done
  refine:   next -> score
  done:     [terminal]
```

Key fields:
- `generate` / `refine`: `capture: candidate`, `next: score`
- `score`: `evaluate.type: output_numeric`, `operator: ge`, `target: <quality_target>` (integer 0–10)
- `on_yes` / `on_no` / `on_error` at state level for routing (not inside `route:`)

---

### rl-policy — Act → Observe → Score → Improve

```
States: act, observe, score, improve, done
Initial: act

Transitions:
  act:      next -> observe
  observe:  next -> score
  score:    route[target] -> done
            route[progress] -> improve
            route[stall] -> act
  improve:  next -> act
  done:     [terminal]
```

Key fields:
- `act`: `capture: action_result`, `next: observe`
- `observe`: `capture: observation`, `next: score`
- `score`: `action_type: shell` (extracts numeric reward), `evaluate.type: convergence`, `direction: maximize`, `route: {target, progress, stall}`
- `improve`: `next: act`
- `context.reward_target`: convergence target (0.0–1.0)
