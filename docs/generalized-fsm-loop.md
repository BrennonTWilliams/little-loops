# Generalized FSM Loop System

## Overview

The little-loops (`ll`) loop system uses **Finite State Machines (FSM)** as the execution model for all loops. Users author loops directly as FSM YAML — defining states, transitions, and evaluators — and the engine executes them as-is.

This design provides:
- **Consistency** - Single execution engine, predictable behavior
- **Debuggability** - FSM state is always inspectable
- **Composability** - All loops share the same underlying structure
- **Transparency** - What you write is what the engine runs

## Integration with Existing Tools

The FSM loop system complements the existing `ll-auto` and `ll-parallel` CLI tools:

| Tool | Purpose | Relationship to FSM Loops |
|------|---------|---------------------------|
| `ll-auto` | Sequential issue processing | Can be an action in FSM states |
| `ll-parallel` | Parallel issue processing with worktrees | Can be an action in FSM states |
| `ll-loop` | Execute FSM-based automation loops | Orchestrates any CLI tool as states |

Example - using `ll-auto` as a step:

```yaml
states:
  process_issues:
    action: "ll-auto --max-issues 5"
    on_yes: "verify"
    on_no: "done"
```

## Common Loop Patterns

All loops are authored as FSM YAML in `.loops/`. Use `/ll:create-loop` to generate FSM YAML interactively, or write it directly. Common patterns and the FSM structures they produce:

| Loop type | Best For | Mental Model |
|-----------|----------|--------------|
| **Fix until clean** | Outcome-focused tasks | "Run check, fix if fails, repeat" |
| **Drive a metric** | Metric optimization | "Drive metric toward target" |
| **Maintain constraints** | Continuous compliance | "Keep these constraints true" |
| **Run a sequence** | Sequential workflows | "Do X, then Y, until Z" |
| **Sub-loop composition** | Multi-step pipelines | "Chain existing loops into a pipeline" |

---

## Loop Pattern Examples

### 1. Fix Until Clean

Run a check, apply a fix on failure, repeat until the check passes.

```yaml
name: "goal-no-type-errors"
initial: "evaluate"
max_iterations: 20
states:
  evaluate:
    action: "/ll:check-code types"
    on_yes: "done"
    on_no: "fix"
  fix:
    action: "/ll:manage-issue bug fix"
    next: "evaluate"
  done:
    terminal: true
```

---

### 2. Drive a Metric

Measure a numeric value and apply fixes until it reaches a target.

```yaml
name: "reduce-lint-errors"
initial: "measure"
context:
  metric_cmd: "ruff check src/ --output-format=json | jq '.count'"
  target: 0
  tolerance: 0
states:
  measure:
    action: "${context.metric_cmd}"
    capture: "current_value"
    evaluate:
      type: convergence
      toward: "${context.target}"
      tolerance: "${context.tolerance}"
    route:
      target: "done"
      progress: "apply"
      stall: "done"
  apply:
    action: "/ll:check-code fix"
    next: "measure"
  done:
    terminal: true
```

---

### 3. Maintain Constraints

Check multiple independent constraints in order; fix each on failure.

```yaml
name: "code-quality-guardian"
initial: "check_tests"
states:
  check_tests:
    action: "pytest"
    on_yes: "check_lint"
    on_no: "fix_tests"
  fix_tests:
    action: "/ll:manage-issue bug fix"
    next: "check_tests"
  check_lint:
    action: "ruff check src/"
    on_yes: "check_types"
    on_no: "fix_lint"
  fix_lint:
    action: "/ll:check-code fix"
    next: "check_lint"
  check_types:
    action: "mypy src/"
    on_yes: "all_valid"
    on_no: "fix_types"
  fix_types:
    action: "/ll:manage-issue bug fix"
    next: "check_types"
  all_valid:
    # For daemon mode, set next: check_tests instead of terminal: true
    terminal: true
```

---

### 4. Run a Sequence

Execute an ordered list of steps, then check an exit condition.

```yaml
name: "fix-all-types"
initial: "step_0"
max_iterations: 20
backoff: 2
states:
  step_0:
    action: "/ll:check-code types"
    next: "step_1"
  step_1:
    action: "/ll:manage-issue bug fix"
    next: "check_done"
  check_done:
    action: "mypy src/"
    on_yes: "done"
    on_no: "step_0"
  done:
    terminal: true
max_iterations: 20
backoff: 2
```

---

### 5. FSM (Direct)

Full control over states and transitions for complex workflows.

```yaml
name: "lint-fix-cycle"
initial: "check"
states:
  check:
    action: "/ll:check-code lint"
    on_yes: "done"
    on_no: "fix"
  fix:
    action: "/ll:check-code fix"
    next: "check"
  done:
    terminal: true
max_iterations: 10
```

No compilation needed - this is the native format.

---

### 6. Sub-Loop Composition

Invoke another loop as a child FSM from a parent state. The child runs to completion; its terminal verdict (`success` / `failure`) drives the parent's transition.

```yaml
name: "quality-then-commit"
initial: "run_quality"
max_iterations: 5
states:
  run_quality:
    loop: "fix-quality-and-tests"    # Invokes .loops/fix-quality-and-tests.yaml
    context_passthrough: true        # Share parent context vars; merge child captures back
    on_success: "run_git"            # Alias for on_yes
    on_failure: "done"               # Alias for on_no
  run_git:
    loop: "issue-refinement-git"     # No context_passthrough — child runs isolated
    on_success: "done"
    on_failure: "done"
  done:
    terminal: true
```

**Key fields:**
- `loop: <name>` — resolves to `.loops/<name>.yaml` (project) or the built-in catalog.
- `context_passthrough: true` — passes all parent `context` and `captured` variables into the child loop; the child's captured values are merged back into the parent's `captured` namespace on completion.
- `on_success` / `on_failure` — aliases for `on_yes` / `on_no` accepted in all states (not just sub-loop states).

**Without `context_passthrough`** the child loop runs with its own isolated context and its captured values are not available to the parent after it completes.

---

## Universal FSM Schema

All loops compile to this schema. Compilation from paradigm syntax to FSM is handled by a Python module (`little_loops.fsm`).

### Action Types

Actions can be either:
- **Shell commands**: `pytest`, `ruff check src/`, `npm run build`
- **Claude Code slash commands**: `/ll:manage-issue`, `/ll:check-code fix`

The executor detects slash commands by the leading `/` and routes them appropriately.

### Schema Definition

```yaml
# Required
name: string                    # Unique loop identifier
initial: string                 # Starting state name
states:                         # State definitions
  <state_name>:
    action: string              # Command to execute (optional for decision states)
    
    # --- Evaluation Layer ---
    evaluate:                   # How to evaluate the action result
      type: string              # exit_code, output_numeric, output_json,
                                # output_contains, llm_structured, convergence,
                                # diff_stall, mcp_result
      # ... type-specific fields (see Evaluator Types)
    
    # --- Routing Layer ---
    # Option 1: Shorthand for common cases
    on_yes: string          # Next state on success verdict
    on_no: string          # Next state on failure verdict
    on_error: string            # Next state on error verdict
    
    # Option 2: Full routing table (overrides shorthand)
    route:                      # Map verdict strings to next states
      <verdict>: string         # e.g., success: "deploy", blocked: "escalate"
      _: string                 # Default for unmatched verdicts
      _error: string            # Evaluation/execution errors
    
    # --- Other State Properties ---
    next: string                # Unconditional transition (no evaluation)
    terminal: boolean           # True if this is an end state
    capture: string             # Variable name to store output
    timeout: number             # Action-level timeout in seconds

# Optional Loop-Level Settings
context: object                 # Shared variables/config
scope: array[string]            # Paths this loop operates on (for concurrency)
max_iterations: integer         # Safety limit (default: 50)
backoff: number                 # Seconds between iterations
timeout: number                 # Max total runtime in seconds (loop-level)
default_timeout: number         # Default per-state action timeout in seconds (overridden by state-level timeout:)
maintain: boolean               # Restart after completion

# Per-Loop Config Overrides (optional)
config:
  handoff_threshold: integer      # Override LL_HANDOFF_THRESHOLD for this loop (1-100)
  commands:
    confidence_gate:
      readiness_threshold: integer  # Override readiness gate threshold (1-100)
      outcome_threshold: integer    # Override outcome confidence threshold (1-100)
  automation:
    max_continuations: integer    # Override max continuation count (>=1)
  continuation:
    max_continuations: integer    # Alias for automation.max_continuations
# Precedence: CLI flags > YAML config block > global ll-config > schema defaults
# All fields are optional; omitted fields inherit the global ll-config value.

# LLM Evaluation Settings
llm:
  model: string                 # Model for LLM evaluation (default: DEFAULT_LLM_MODEL from schema.py)
  max_tokens: integer           # Max tokens for evaluation (default: 256)
  timeout: number               # Timeout for LLM calls in seconds (default: 1800)
```

---

## Two-Layer Transition System

The FSM executor uses a **two-layer system** that cleanly separates concerns:

```
┌─────────────────────────────────────────────────────────────┐
│                     State Execution                          │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  Layer 1: EVALUATE                                           │
│  "Given the action output, what happened?"                   │
│  → Produces a structured result with verdict string          │
│                                                              │
│  Layer 2: ROUTE                                              │
│  "Given the verdict, where do I go next?"                    │
│  → Maps verdict to next state                                │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### Why Two Layers?

**Single Responsibility**: Each layer does one job well.
- Evaluators answer "what happened?" without knowing about states
- Routing answers "where next?" without knowing how verdicts were produced

**Testable**: Test each layer in isolation.
- Test evaluator: "Given this output, does it produce the right verdict?"
- Test routing: "Given this verdict, does it go to the right state?"

**Extensible**: Add new evaluators without touching routing logic.

### Layer 1: Evaluate

The `evaluate` block defines how to interpret an action's output. Every evaluator produces a **result object**:

```yaml
result:
  verdict: string       # The routing key (e.g., "yes", "no", "target", "blocked")
  details: object       # Evaluator-specific data (available as ${result.*})
```

#### Default Evaluation by Action Type

| Action Type | Default Evaluator | Rationale |
|-------------|-------------------|-----------|
| Shell command | `exit_code` | Standard Unix semantics |
| Slash command | `llm_structured` | Natural language output |

#### Explicit Evaluation

```yaml
states:
  check:
    action: "pytest --tb=short"
    evaluate:
      type: exit_code
    # Result: { verdict: "yes" | "no" | "error", details: { exit_code: 0 } }
```

### Layer 2: Route

The `route` block maps verdicts to next states. It's just a dictionary lookup.

#### Shorthand Syntax

For simple success/failure routing, use the shorthand:

```yaml
states:
  check:
    action: "pytest"
    on_yes: "deploy"
    on_no: "fix"
    on_error: "alert"
```

An additional shorthand, `on_blocked`, routes when the evaluator returns a `blocked` verdict (i.e., the action cannot proceed without external intervention):

```yaml
states:
  fix:
    action: "/ll:manage-issue bug fix"
    on_yes: "verify"
    on_no: "fix"
    on_blocked: "escalate"
```

`on_blocked` is resolved alongside `on_yes`/`on_no`/`on_error` in the shorthand lookup. It is equivalent to adding `blocked: "escalate"` to a full `route` table and is the recommended way to handle blocked states without switching to a full route table. If a `blocked` verdict is returned and no `on_blocked` target is defined, the loop terminates with a fatal routing error — define `on_blocked` on any state whose action can return a `blocked` verdict.

This is equivalent to:

```yaml
states:
  check:
    action: "pytest"
    route:
      yes: "deploy"
      no: "fix"
      error: "alert"
```

#### Full Route Table

When you need more than three outcomes:

```yaml
states:
  fix:
    action: "/ll:manage-issue bug fix"
    evaluate:
      type: llm_structured
    route:
      yes: "verify"
      no: "fix"
      blocked: "escalate"
      partial: "probe"
      _: "fix"              # Default for any other verdict
```

#### Special Route Keys

| Key | Meaning |
|-----|---------|
| `_` | Default route for unmatched verdicts |
| `_error` | Route for evaluation/execution errors (overrides loop-level `on_error`) |

### Resolution Order

1. If `next` is present → unconditional transition (no evaluation)
2. If `route` is present → use full routing table
3. If `on_yes`/`on_no`/`on_error`/`on_blocked` → use shorthand routing
4. If `terminal: true` → end loop
5. Otherwise → error (no valid transition)

---

## Evaluator Types

Evaluators produce verdicts from action output. The executor uses LLM structured output **only** for the `llm_structured` evaluator—all others are deterministic.

### Tier 1: Deterministic Evaluators

No API calls. Fast, free, reproducible.

#### `exit_code` (Default for Shell Commands)

```yaml
evaluate:
  type: exit_code
```

| Exit Code | Verdict |
|-----------|---------|
| 0 | `yes` |
| 1 | `no` |
| 2+ | `error` |

Result details: `{ exit_code: <int> }`

#### `output_numeric`

Parse stdout as a number and compare.

```yaml
evaluate:
  type: output_numeric
  operator: le        # eq, ne, lt, le, gt, ge
  target: 5
```

| Comparison Result | Verdict |
|-------------------|---------|
| Condition met | `yes` |
| Condition not met | `no` |
| Parse error | `error` |

Result details: `{ value: <number>, target: <number>, operator: <string> }`

#### `output_json`

Parse JSON and extract a value.

```yaml
evaluate:
  type: output_json
  path: ".summary.failed"    # jq-style path
  operator: eq
  target: 0
```

Result details: `{ value: <any>, path: <string>, target: <any> }`

#### `output_contains`

Pattern matching on stdout.

```yaml
evaluate:
  type: output_contains
  pattern: "All tests passed"    # Substring or regex
  negate: false                  # If true, success when NOT found
```

| Match Result | Verdict |
|--------------|---------|
| Pattern found (negate=false) | `yes` |
| Pattern not found (negate=false) | `no` |
| Pattern found (negate=true) | `no` |
| Pattern not found (negate=true) | `yes` |

Result details: `{ matched: <bool>, pattern: <string>, negate: <bool> }`

#### `convergence`

Compare current value to previous value and target. Used by the convergence paradigm.

```yaml
evaluate:
  type: convergence
  target: 0
  tolerance: 0              # Optional: success when within tolerance
  previous: "${prev.output}" # Previous measurement
  direction: minimize       # minimize (default) or maximize
```

| Scenario | Verdict |
|----------|---------|
| Value within tolerance of target | `target` |
| Value improved toward target | `progress` |
| Value unchanged or worsened | `stall` |

Result details: `{ current: <number>, previous: <number>, target: <number>, delta: <number> }`

#### `diff_stall`

Detect when a fix loop is spinning without making filesystem changes by comparing `git diff --stat` between iterations.

```yaml
evaluate:
  type: diff_stall
  scope: ["src/", "tests/"]    # Optional: paths to pass to git diff --stat (default: entire repo)
  max_stall: 1                  # Optional: consecutive no-change iterations before `no` verdict
```

| Scenario | Verdict |
|----------|---------|
| First call (no prior snapshot) | `yes` |
| Diff changed since last iteration | `yes` |
| Diff unchanged, stall count < max_stall | `yes` |
| Diff unchanged, stall count >= max_stall | `no` |
| git unavailable or command failed | `error` |

Result details: `{ stall_count: <int>, max_stall: <int>, diff_changed: <bool> }`

---

### Tier 2: LLM Evaluator

Uses a Claude API call with structured output. This is the **only** place in the FSM system that uses LLM structured output.

#### `llm_structured` (Default for Slash Commands)

```yaml
evaluate:
  type: llm_structured
  prompt: "Did this fix attempt succeed?"   # Optional custom prompt
  schema:                                    # Optional custom schema
    type: object
    properties:
      verdict:
        type: string
        enum: ["yes", "no", "blocked", "partial"]
      confidence:
        type: number
      reason:
        type: string
    required: ["verdict", "confidence", "reason"]
  min_confidence: 0.7                        # Threshold for confident verdicts
```

#### Default Schema

When no schema is provided:

```yaml
schema:
  type: object
  properties:
    verdict:
      type: string
      enum: ["yes", "no", "blocked", "partial"]
      description: |
        - yes: The condition/check evaluated to true
        - no: The condition/check evaluated to false
        - blocked: Cannot proceed without external help
        - partial: Made progress but not complete
    confidence:
      type: number
      minimum: 0
      maximum: 1
      description: "Confidence in this verdict (0-1)"
    reason:
      type: string
      description: "Brief explanation"
  required: ["verdict", "confidence", "reason"]
```

#### Confidence Handling

The evaluator adds a `confident` flag to the result:

```yaml
result:
  verdict: "yes"           # From LLM response
  details:
    confidence: 0.85
    confident: true            # confidence >= min_confidence
    reason: "Fixed the type error in handlers.py"
```

You can route on confidence:

```yaml
states:
  fix:
    action: "/ll:manage-issue bug fix"
    evaluate:
      type: llm_structured
      min_confidence: 0.7
    route:
      yes: "verify"
      no: "fix"
      blocked: "escalate"
      partial: "probe"
      _: "fix"
```

Or create compound routing with confidence:

```yaml
states:
  fix:
    action: "/ll:manage-issue bug fix"
    evaluate:
      type: llm_structured
      min_confidence: 0.7
      # When confidence < min_confidence, verdict becomes "<verdict>_uncertain"
      # e.g., "yes" → "yes_uncertain"
      uncertain_suffix: true
    route:
      yes: "verify"
      yes_uncertain: "probe"    # High confidence yes → verify, low → probe
      no: "fix"
      no_uncertain: "probe"
      blocked: "escalate"
      _: "fix"
```

#### Implementation

```python
# little_loops/fsm/evaluators.py

import anthropic

def evaluate_llm_structured(
    output: str,
    prompt: str | None,
    schema: dict,
    min_confidence: float = 0.5,
    uncertain_suffix: bool = False,
    model: str = DEFAULT_LLM_MODEL,  # Default from schema.py
    max_tokens: int = 256,
) -> dict:
    """
    Evaluate action output using LLM with structured output.
    
    This is the ONLY place in the FSM system that uses LLM structured output.
    """
    client = anthropic.Anthropic()
    
    default_prompt = "Evaluate whether this action succeeded based on its output."
    eval_prompt = prompt or default_prompt
    
    # Truncate output to avoid context limits
    truncated = output[-4000:] if len(output) > 4000 else output
    
    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        messages=[{
            "role": "user",
            "content": f"{eval_prompt}\n\n<action_output>\n{truncated}\n</action_output>"
        }],
        tools=[{
            "name": "evaluate",
            "description": "Provide your evaluation of the action result",
            "input_schema": schema
        }],
        tool_choice={"type": "tool", "name": "evaluate"}
    )
    
    # Extract structured result
    for block in response.content:
        if block.type == "tool_use" and block.name == "evaluate":
            llm_result = block.input
            break
    else:
        raise EvaluationError("No evaluation in response")
    
    # Build result with confidence flag
    verdict = llm_result["verdict"]
    confidence = llm_result.get("confidence", 1.0)
    confident = confidence >= min_confidence
    
    # Optionally modify verdict for low confidence
    if uncertain_suffix and not confident:
        verdict = f"{verdict}_uncertain"
    
    return {
        "verdict": verdict,
        "details": {
            "confidence": confidence,
            "confident": confident,
            "reason": llm_result.get("reason", ""),
            "raw": llm_result,
        }
    }
```

#### Cost and Performance

| Metric | Value |
|--------|-------|
| Cost per evaluation | ~$0.001 |
| Latency | 300-800ms |
| Context used | ~4000 tokens max |

---

### Tier 3: MCP Evaluator

Evaluates results from `action_type: mcp_tool` states. Unlike Tier 1 (deterministic) and Tier 2 (LLM-based) evaluators, this evaluator invokes an external MCP process and parses its protocol envelope — it is neither a simple exit-code check nor an LLM call.

#### `mcp_result`

Evaluate an MCP tool call result. All inputs (`output` and `exit_code`) are injected by the executor from the MCP subprocess — `type: mcp_result` is the entire YAML config; there are no user-configurable fields.

```yaml
evaluate:
  type: mcp_result
```

| Scenario | Verdict |
|----------|---------|
| Tool ran successfully (isError: false) | `success` |
| Tool returned an error (isError: true) | `tool_error` |
| Server or tool not in `.mcp.json` (exit 127) | `not_found` |
| Transport-level timeout (exit 124) | `timeout` |

Result details: `{ exit_code: <int>, envelope: <object> }`

> **Important**: `mcp_result` is the only built-in evaluator that returns `success` as a verdict (not `yes`). The `on_yes`/`on_no` shorthand will not match any of its verdicts. A full `route:` table is required:

```yaml
states:
  call_tool:
    action_type: mcp_tool
    # ... mcp_tool config ...
    evaluate:
      type: mcp_result
    route:
      success: "next_state"
      tool_error: "handle_error"
      not_found: "abort"
      timeout: "retry"
```

---

## Evaluation Source

By default, evaluators examine the current action's stdout. Use `source` to evaluate something else:

```yaml
states:
  measure:
    action: "mypy src/ | grep -c error || echo 0"
    capture: "errors"
    next: "decide"

  decide:
    # No action—evaluate captured value from previous state
    evaluate:
      type: output_numeric
      source: "${captured.errors.output}"
      operator: eq
      target: 0
    route:
      yes: "done"
      no: "fix"
```

This enables **decision states** that branch without executing an action.

---

## Variable Interpolation

Actions, evaluators, and routes can reference dynamic values using `${namespace.path}` syntax.

### Available Namespaces

| Namespace | Description | Lifetime |
|-----------|-------------|----------|
| `context` | User-defined variables from `context:` block | Entire loop |
| `captured` | Values stored via `capture:` in previous states | Entire loop |
| `prev` | Shorthand for previous state's result | Current state only |
| `result` | Current evaluation result | Current state only |
| `state` | Current execution metadata | Current state only |
| `loop` | Loop-level metadata | Entire loop |
| `env` | Environment variables | Entire loop |

### Namespace Contents

#### `context` - User-Defined Variables

```yaml
context:
  target_dir: "src/"
  max_errors: 10
  metric_cmd: "mypy ${context.target_dir}"

states:
  check:
    action: "${context.metric_cmd}"
```

#### `captured` - Stored Action Results

When a state uses `capture: "varname"`:

```yaml
captured:
  varname:
    output: "..."       # stdout
    stderr: "..."       # stderr
    exit_code: 0        # exit code
    duration_ms: 1234   # execution time
```

#### `prev` - Previous State Shorthand

```yaml
${prev.output}      # stdout from previous state
${prev.exit_code}   # exit code from previous state
${prev.state}       # name of previous state
```

#### `result` - Current Evaluation Result

After evaluation runs, access the result:

```yaml
${result.verdict}           # The verdict string
${result.details.confidence} # For LLM evaluation
${result.details.reason}     # For LLM evaluation
${result.details.value}      # For numeric evaluation
```

Example - logging evaluation details:

```yaml
states:
  fix:
    action: "/ll:manage-issue bug fix"
    evaluate:
      type: llm_structured
    route:
      yes: "log_success"
      no: "log_failure"
      _: "fix"

  log_success:
    action: "echo 'Fixed: ${result.details.reason}' >> .loops/fix.log"
    next: "verify"

  log_failure:
    action: "echo 'Failed (${result.details.confidence}): ${result.details.reason}' >> .loops/fix.log"
    next: "fix"
```

#### `state` - Current Execution Context

```yaml
${state.name}       # current state name
${state.iteration}  # loop iteration (1-indexed)
```

#### `loop` - Loop Metadata

```yaml
${loop.name}        # loop identifier
${loop.started_at}  # ISO 8601 timestamp
${loop.elapsed_ms}  # milliseconds since start
${loop.elapsed}     # human-readable (e.g., "2m 34s")
```

#### `env` - Environment Variables

```yaml
${env.HOME}
${env.CI}
${env.PATH}
```

### Resolution Rules

| Rule | Behavior |
|------|----------|
| **Timing** | Resolved at runtime, just before use |
| **Undefined variable** | Loop terminates with error |
| **Empty value** | Interpolates as empty string |
| **Escaping** | Use `$${` for literal `${` |
| **Nesting** | Not supported |

---

## Complete Examples

### Example 1: Simple Shell Command Loop

```yaml
# Simplest case - all defaults
name: "test-until-pass"
initial: "test"
states:
  test:
    action: "pytest"
    on_yes: "done"
    on_no: "fix"
  fix:
    action: "git stash pop"    # Try a stashed fix
    next: "test"
  done:
    terminal: true
max_iterations: 5
```

### Example 2: Slash Command with LLM Evaluation

```yaml
name: "fix-types"
initial: "check"
states:
  check:
    action: "mypy src/"
    on_yes: "done"
    on_no: "fix"
  
  fix:
    action: "/ll:manage-issue bug fix"
    # Default: evaluate with llm_structured, route success/failure
    on_yes: "check"
    on_no: "check"    # Retry even on failure (up to max_iterations)
  
  done:
    terminal: true
max_iterations: 10
```

### Example 3: Custom Verdicts with Full Routing

```yaml
name: "smart-fix"
initial: "fix"
states:
  fix:
    action: "/ll:manage-issue bug fix"
    evaluate:
      type: llm_structured
      min_confidence: 0.7
    route:
      yes: "verify"
      no: "fix"
      blocked: "escalate"
      partial: "probe"
      _: "fix"

  probe:
    # Deterministic fallback when LLM is uncertain
    action: "mypy src/ 2>&1 | grep -c 'error:' || echo 0"
    evaluate:
      type: output_numeric
      operator: eq
      target: 0
    route:
      yes: "done"
      no: "fix"

  verify:
    action: "pytest tests/"
    on_yes: "done"
    on_no: "fix"

  escalate:
    action: "echo 'Blocked: ${result.details.reason}' | notify-team"
    terminal: true

  done:
    terminal: true
max_iterations: 15
```

### Example 4: Convergence Loop

```yaml
name: "reduce-errors"
initial: "measure"
context:
  target: 0

states:
  measure:
    action: "mypy src/ 2>&1 | grep -c 'error:' || echo 0"
    capture: "errors"
    evaluate:
      type: convergence
      target: "${context.target}"
      previous: "${prev.output}"
    route:
      target: "done"
      progress: "fix"
      stall: "done"

  fix:
    action: "/ll:manage-issue bug fix"
    next: "measure"

  done:
    action: "echo 'Finished with ${captured.errors.output} errors'"
    terminal: true
max_iterations: 20
```

### Example 5: CI-Friendly (No LLM Evaluation)

```yaml
name: "ci-checks"
initial: "lint"

# Disable LLM evaluation entirely
llm:
  enabled: false

states:
  lint:
    action: "ruff check src/"
    on_yes: "typecheck"
    on_no: "fix_lint"

  fix_lint:
    action: "ruff check src/ --fix"
    next: "lint"

  typecheck:
    action: "mypy src/"
    on_yes: "test"
    on_no: "done"    # Can't auto-fix types

  test:
    action: "pytest --tb=short"
    on_yes: "done"
    on_no: "done"

  done:
    terminal: true
max_iterations: 3
timeout: 600
```

### Example 6: Complex Workflow with Confidence Routing

```yaml
name: "safe-refactor"
initial: "analyze"

llm:
  model: "${DEFAULT_LLM_MODEL}"  # Uses default from schema.py

states:
  analyze:
    action: "/ll:audit-architecture patterns"
    evaluate:
      type: llm_structured
      schema:
        type: object
        properties:
          verdict:
            type: string
            enum: ["found_opportunities", "no_opportunities"]
          opportunities:
            type: array
            items: { type: string }
          confidence:
            type: number
        required: ["verdict", "confidence"]
    route:
      found_opportunities: "refactor"
      no_opportunities: "done"
      _: "done"

  refactor:
    action: "/ll:manage-issue enhancement implement"
    evaluate:
      type: llm_structured
      min_confidence: 0.8
      uncertain_suffix: true
    route:
      yes: "verify"
      yes_uncertain: "manual_check"
      no: "refactor"
      blocked: "rollback"
      _: "refactor"

  verify:
    action: "pytest && mypy src/"
    timeout: 300
    on_yes: "done"
    on_no: "rollback"

  manual_check:
    action: "echo 'Low confidence refactor - needs review: ${result.details.reason}'"
    terminal: true

  rollback:
    action: "git checkout -- src/"
    next: "done"

  done:
    terminal: true

max_iterations: 5
timeout: 1800
```

---

## Error Handling

### Error vs Failure

| Outcome | Trigger | Default Behavior |
|---------|---------|------------------|
| **Success** | Evaluator returns `yes` verdict | Route via `yes` key or `on_yes` |
| **Failure** | Evaluator returns `no` verdict | Route via `no` key or `on_no` |
| **Error** | Execution crash, timeout, eval error | Route via `_error` or terminate loop |

### Customizing Error Handling

```yaml
states:
  check:
    action: "pytest"
    on_yes: "deploy"
    on_no: "fix"
    on_error: "alert"           # Go to recovery state

# Or with full routing
  check:
    action: "pytest"
    route:
      yes: "deploy"
      no: "fix"
      _error: "alert"
```

### Retry Current State

Use the special `$current` token:

```yaml
states:
  flaky_test:
    action: "pytest tests/integration/"
    route:
      yes: "done"
      no: "$current"           # Retry this state
      _error: "$current"       # Also retry on errors
```

Retries respect `max_iterations`.

### LLM Evaluation Errors

When LLM evaluation fails (API error, timeout, invalid response):

1. If `_error` route exists → use it
2. Otherwise → terminate loop with error

```yaml
states:
  fix:
    action: "/ll:manage-issue bug fix"
    evaluate:
      type: llm_structured
    route:
      yes: "verify"
      no: "fix"
      _error: "probe"          # Fall back to deterministic on LLM failure
```

---

## Timeouts

Three levels of timeout protection:

```yaml
# Loop-level: max wall-clock time for entire loop
timeout: 3600                   # 1 hour

# Loop-level: default per-state action timeout (fallback for states without timeout:)
default_timeout: 3600           # 1 hour for each prompt/action state

states:
  build:
    action: "npm run build"
    timeout: 300                # 5 min for this action (overrides default_timeout)
```

- **Action timeout** (`state.timeout`): Per-state override; catches hung processes
- **Default timeout** (`default_timeout`): Loop-level fallback applied to all states that don't set `timeout:`; hardcoded fallback is 3600s for prompt/LLM states and 30s for MCP tool calls when neither is set
- **Loop timeout** (`timeout`): Bounds total wall-clock execution time (independent of per-state timeouts)

LLM evaluation has its own timeout (default 1800s) configured at loop level:

```yaml
llm:
  timeout: 45    # Seconds per LLM evaluation call
```

---

## Concurrency and Locking

Only one loop can run at a time per scope.

### Scope Declaration

```yaml
name: "fix-api-types"
scope:
  - "src/api/"
  - "tests/api/"
```

| Declaration | Behavior |
|-------------|----------|
| Explicit paths | Loop claims those paths |
| No scope | Treated as `["."]` (whole project) |

### Overlap Rules

| Scenario | Behavior |
|----------|----------|
| No other loop running | Start immediately |
| Non-overlapping scopes | Start immediately (parallel OK) |
| Overlapping scopes | Queue or fail |

```bash
# Fail on conflict (default)
ll-loop run .loops/fix-types.yaml

# Wait for conflicting loop
ll-loop run .loops/fix-types.yaml --queue
```

---

## Security Model

### Execution Context

Loops are executed **only** via the `ll-loop` CLI command—never via slash commands. The `/ll:create-loop` command helps author loops, but execution requires explicit CLI invocation.

### Autonomous Execution

All slash command actions use `--dangerously-skip-permissions`. This is **non-negotiable** for autonomous execution. Users accept this trade-off when they run a loop.

| Aspect | Policy |
|--------|--------|
| User approval before loop | None required |
| Permission prompts during loop | Disabled (`--dangerously-skip-permissions`) |
| "Blessing" reviewed loops | Not supported—delete invalid loops |

### Risk Mitigation

- **Review before running**: Users should read loop definitions before execution
- **Iteration limits**: `max_iterations` prevents runaway loops
- **Timeouts**: Action and loop-level timeouts bound execution
- **Scoped operations**: `scope` declaration limits file system impact

---

## File Structure

### Canonical Location

All loop definitions live in `.loops/`:

```
.loops/
├── fix-types.yaml          # User-defined loop
├── lint-cycle.yaml         # User-defined loop
└── .running/               # Runtime state (auto-managed)
    ├── fix-types.state.json
    └── fix-types.events.jsonl
```

### Relationship to `.issues/`

The `.issues/` directory is **separate** and serves a different purpose:

| Directory | Purpose | Used By |
|-----------|---------|---------|
| `.loops/` | FSM loop definitions | `ll-loop` |
| `.issues/` | Issue tracking files | `ll-auto`, `ll-parallel`, `/ll:manage-issue` |

FSM loops can orchestrate tools that consume `.issues/`, but the directories remain independent.

### Templates

No loop templates are provided. All loops are user-defined. Future versions may add templates for common workflows.

---

## CLI Interface

### Command: `ll-loop`

```bash
# Run a loop (primary usage - loop name resolves to .loops/<name>.yaml)
ll-loop test-analyze-fix
ll-loop fix-types --max-iterations 5
ll-loop lint-cycle --background

# Explicit run subcommand (alternative)
ll-loop run fix-types --dry-run
ll-loop run .loops/fix-types.yaml    # Full path also works

# Validate loop definition
ll-loop validate fix-types

# Manage running loops
ll-loop list
ll-loop list --running
ll-loop status fix-types
ll-loop stop fix-types
ll-loop resume fix-types

# History
ll-loop history fix-types
```

### Run Flags

| Flag | Description |
|------|-------------|
| `--background` | Run as daemon |
| `--dry-run` | Show execution plan |
| `--queue` | Wait for conflicting loops |
| `--max-iterations N` | Override limit |
| `--no-llm` | Disable LLM evaluation |
| `--llm-model MODEL` | Override LLM model |

---

## Execution Engine

### Flow

1. Load FSM from YAML
2. Set state to `initial`
3. Execute action (shell or Claude CLI)
4. Evaluate result (deterministic or LLM)
5. Route to next state based on verdict
6. Emit event
7. Repeat until terminal or limits reached

### Action Execution

| Type | Detection | Method |
|------|-----------|--------|
| Shell | No leading `/` | `subprocess.run()` |
| Slash | Leading `/` | `claude --dangerously-skip-permissions -p "..."` |

### State Persistence

```json
// .loops/.running/<name>.state.json
{
  "current_state": "fix",
  "iteration": 3,
  "captured": {
    "errors": { "output": "4", "exit_code": 0 }
  },
  "last_result": {
    "verdict": "no",
    "details": { "confidence": 0.65, "reason": "..." }
  },
  "started_at": "2024-01-15T10:30:00Z"
}
```

---

## Structured Events

Events stream to `.loops/.running/<name>.events.jsonl`:

```jsonl
{"event": "loop_start", "loop": "fix-types", "ts": "..."}
{"event": "state_enter", "state": "check", "iteration": 1, "ts": "..."}
{"event": "action_start", "action": "mypy src/", "ts": "..."}
{"event": "action_complete", "exit_code": 1, "duration_ms": 2340, "ts": "..."}
{"event": "evaluate", "type": "exit_code", "verdict": "no", "ts": "..."}
{"event": "route", "from": "check", "to": "fix", "verdict": "no", "ts": "..."}
{"event": "state_enter", "state": "fix", "iteration": 1, "ts": "..."}
{"event": "action_start", "action": "/ll:manage-issue bug fix", "ts": "..."}
{"event": "action_complete", "duration_ms": 45000, "ts": "..."}
{"event": "evaluate", "type": "llm_structured", "verdict": "yes", "confidence": 0.92, "ts": "..."}
{"event": "route", "from": "fix", "to": "verify", "verdict": "yes", "ts": "..."}
{"event": "loop_complete", "final_state": "done", "iterations": 3, "ts": "..."}
```

### CLI Progress Display

```
$ ll-loop run fix-types.yaml
[1/20] check → mypy src/
       ✗ failure (exit 1)
       → fix
[1/20] fix → /ll:manage-issue bug fix
       ✓ success (confidence: 0.92)
       → verify
[1/20] verify → pytest tests/
       ✓ success (exit 0)
       → done

Loop completed: done (1 iteration, 2m 34s)
```

---

## Design Decisions

### Why Two Layers (Evaluate + Route)?

1. **Single Responsibility** - Evaluators don't know about states; routing doesn't know about output parsing
2. **Testability** - Test each layer in isolation
3. **Extensibility** - Add evaluators without touching routing
4. **Clarity** - When debugging, you can ask "what verdict?" and "where did it route?" separately

### Why LLM Structured Output Only for Evaluation?

1. **Single Point of LLM Usage** - Easy to understand cost model
2. **Deterministic Compilation** - Paradigm → FSM is reproducible
3. **Testable** - Mock one function to test everything else

### Alternatives Considered

**Single-layer with escape hatch**: Simpler concept count, but the escape hatch creates a hidden mode switch. The two-layer model is honest about what's happening.

**Predicate-based routing**: More powerful but requires a predicate language. Verdict strings are simpler and sufficient.

---

## Testing Strategy

The two-layer design (evaluate + route) enables isolated testing of each layer. The single LLM touchpoint means only one mock strategy is needed for all LLM-related tests.

### 1. Unit Tests for Evaluators

Tier 1 evaluators are pure functions—deterministic and fast.

```python
# tests/unit/test_evaluators.py

class TestExitCodeEvaluator:
    @pytest.mark.parametrize("exit_code,expected_verdict", [
        (0, "yes"),
        (1, "no"),
        (2, "error"),
        (127, "error"),
    ])
    def test_exit_code_mapping(self, exit_code, expected_verdict):
        result = evaluate_exit_code(exit_code)
        assert result["verdict"] == expected_verdict
        assert result["details"]["exit_code"] == exit_code


class TestConvergenceEvaluator:
    def test_target_reached(self):
        result = evaluate_convergence(
            current=0, previous=5, target=0, tolerance=0
        )
        assert result["verdict"] == "target"

    def test_progress_made(self):
        result = evaluate_convergence(
            current=3, previous=5, target=0, tolerance=0
        )
        assert result["verdict"] == "progress"
        assert result["details"]["delta"] == -2

    def test_stall_detected(self):
        result = evaluate_convergence(
            current=5, previous=5, target=0, tolerance=0
        )
        assert result["verdict"] == "stall"
```

### 2. Mock Strategy for LLM Evaluation

LLM structured output is used in only one place: `evaluate_llm_structured`. This makes mocking straightforward.

```python
# tests/conftest.py

@pytest.fixture
def mock_llm_evaluator():
    """Factory for LLM evaluation mocks."""
    def _make_mock(verdict: str, confidence: float = 0.9, reason: str = ""):
        return {
            "verdict": verdict,
            "details": {
                "confidence": confidence,
                "confident": confidence >= 0.7,
                "reason": reason,
                "raw": {"verdict": verdict, "confidence": confidence}
            }
        }
    return _make_mock


# tests/unit/test_llm_evaluator.py

class TestLLMEvaluator:
    def test_uncertain_suffix_applied(self, mock_anthropic):
        """Low confidence + uncertain_suffix=True → success_uncertain."""
        mock_anthropic.return_value = {"verdict": "yes", "confidence": 0.5}

        result = evaluate_llm_structured(
            output="Fixed the bug",
            schema=DEFAULT_SCHEMA,
            min_confidence=0.7,
            uncertain_suffix=True
        )

        assert result["verdict"] == "yes_uncertain"
        assert result["details"]["confident"] is False
```

**Mock implementation**: Use `unittest.mock.patch` on the Anthropic client, or inject a client factory for dependency injection.

### 3. Integration Tests for Executor

Test the full state machine execution with mocked externals.

```python
# tests/integration/test_executor.py

class TestExecutor:
    @pytest.fixture
    def mock_action_runner(self):
        """Mock that captures actions and returns configured results."""
        return MockActionRunner()

    def test_simple_success_path(self, mock_action_runner, mock_llm_evaluator):
        """check → done on first success."""
        fsm = load_fsm("test-pass-first.yaml")
        mock_action_runner.set_result("check", exit_code=0)

        executor = FSMExecutor(fsm, action_runner=mock_action_runner)
        result = executor.run()

        assert result.final_state == "done"
        assert result.iterations == 1
        assert mock_action_runner.calls == ["check"]

    def test_fix_retry_loop(self, mock_action_runner, mock_llm_evaluator):
        """check → fix → check → done with retry."""
        mock_action_runner.set_results([
            ("check", {"exit_code": 1}),  # First check fails
            ("fix", {"stdout": "Fixed"}),
            ("check", {"exit_code": 0}),  # Second check passes
        ])
        mock_llm_evaluator.set_verdict("fix", "yes")

        executor = FSMExecutor(fsm, ...)
        result = executor.run()

        assert result.final_state == "done"
        assert result.iterations == 2

    def test_max_iterations_respected(self, mock_action_runner):
        """Loop terminates at max_iterations even if not terminal."""
        fsm = {"max_iterations": 3, ...}
        mock_action_runner.always_fail()

        result = FSMExecutor(fsm, ...).run()

        assert result.iterations == 3
        assert result.terminated_by == "max_iterations"

    def test_variable_interpolation(self, mock_action_runner):
        """${context.*} and ${captured.*} resolve correctly."""
        fsm = {
            "context": {"target_dir": "src/"},
            "states": {
                "check": {
                    "action": "mypy ${context.target_dir}",
                    "capture": "errors",
                    ...
                }
            }
        }

        executor = FSMExecutor(fsm, action_runner=mock_action_runner)
        executor.run()

        assert mock_action_runner.last_action == "mypy src/"
```

### 4. Test File Organization

```
scripts/tests/
├── unit/
│   ├── test_evaluators.py         # All Tier 1 evaluators
│   ├── test_llm_evaluator.py      # LLM evaluator with mocked API
│   ├── test_routing.py            # Verdict → state resolution
│   └── test_interpolation.py      # Variable substitution
├── integration/
│   ├── test_executor.py           # Full FSM execution
│   └── test_state_persistence.py  # Resume from saved state
├── fixtures/
│   ├── loops/                     # Test FSM definitions
│   └── outputs/                   # Sample action outputs
└── conftest.py                    # Shared fixtures, mocks
```

### Summary

| Layer | Test Type | Mock Strategy |
|-------|-----------|---------------|
| Compilers | Unit | None needed (pure functions) |
| Tier 1 Evaluators | Unit | None needed (deterministic) |
| LLM Evaluator | Unit | Mock Anthropic client |
| Routing | Unit | Provide verdict directly |
| Variable Interpolation | Unit | Provide context dict |
| Executor | Integration | Mock action runner + LLM evaluator |

---

## The `/ll:create-loop` Command

Interactive command for creating new loop configurations. Uses Claude to understand user intent and generate paradigm YAML.

### Workflow

```
User invokes /ll:create-loop
        ↓
Claude asks clarifying questions (AskUserQuestion)
        ↓
User provides answers (single/multi-select, free text)
        ↓
Claude generates paradigm YAML
        ↓
User reviews/edits
        ↓
Loop saved to .loops/<name>.yaml
```

### Example Session

```
> /ll:create-loop

What kind of automation loop do you want to create?
  ○ Fix until clean (Recommended)
  ○ Maintain constraints
  ○ Drive a metric toward a target
  ○ Run a sequence of steps
  ○ Other...

> Fix until clean

What should the loop fix?
  ☑ Type errors (mypy)
  ☑ Lint errors (ruff)
  ☐ Test failures (pytest)
  ☐ Other...

> [Type errors, Lint errors selected]

What's the maximum number of fix attempts?
  ○ 10 (Recommended)
  ○ 20
  ○ 50
  ○ Custom...

> 10

Here's the loop configuration:

```yaml
name: "fix-types-and-lint"
initial: check_types
max_iterations: 10
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
    on_yes: all_valid
    on_no: fix_lint
  fix_lint:
    action: "/ll:check-code fix"
    next: check_lint
  all_valid:
    terminal: true
```

Save to .loops/fix-types-and-lint.yaml? [Y/n]
```

### Question Types

The command uses `AskUserQuestion` with various patterns:

| Pattern | Use Case |
|---------|----------|
| Single-select | Loop type choice, iteration limits |
| Multi-select | Which checks to include, which tools to use |
| Free text | Custom loop names, custom commands |

### Implementation Notes

- Command is implemented in `commands/create-loop.md`
- Uses Claude's natural language understanding to map user intent to paradigm
- Validates generated YAML before saving
- Offers to run `ll-loop validate <name>` after creation

---

## Open Questions

### Resolved

1. ✅ **Transition system design** - Two-layer (evaluate + route) with shortcuts for common cases
2. ✅ **LLM usage scope** - Only in `llm_structured` evaluator
3. ✅ **Confidence handling** - Optional `uncertain_suffix` for compound verdicts
4. ✅ **Integration with existing tools** - `ll-auto` and `ll-parallel` are complementary; they become executable actions within FSM states
5. ✅ **Security model** - No user approval; always use `--dangerously-skip-permissions`; no blessing mechanism
6. ✅ **File structure** - `.loops/` is canonical; separate from `.issues/`; no templates for now
7. ✅ **CLI UX** - Primary invocation is `ll-loop <loop-name>` (resolves to `.loops/<name>.yaml`)
8. ✅ **Context handoff integration** - Deferred to future; initial implementation terminates on handoff signal
9. ✅ **`/ll:create-loop` command** - In scope for v1; interactive command using `AskUserQuestion`

### For Implementation

10. **Maintain mode timing** - Configurable delay between cycles? (Can add `maintain_delay` field)

---

## Related Skills

### `/ll:loop-suggester`
Analyzes user message history from `ll-messages` output to automatically suggest FSM loop configurations. Instead of manually identifying patterns and using `/ll:create-loop`, this skill detects repeated workflows and generates ready-to-use loop YAML.

**When to use:**
- You want to discover automation opportunities from your existing work patterns
- You have repetitive check-fix-verify cycles you'd like to automate
- You're unsure which paradigm fits your workflow

**Example workflow:**
```bash
# Extract recent messages with tool usage metadata
ll-messages --include-response-context -n 200 -o messages.jsonl

# Invoke the skill to analyze and suggest loops
/ll:loop-suggester messages.jsonl

# Review suggestions in .ll/loop-suggestions/
# Copy promising yaml_config to .loops/ and validate
```

See `skills/loop-suggester/SKILL.md` for full documentation.

---

## Future Considerations

- **Context handoff integration** - Executor can detect `CONTEXT_HANDOFF:` signals from slash commands and spawn continuation sessions, preserving loop state transparently. Initial implementation may simply terminate.
- **Composition** - Nested loops, sub-FSMs
- **Hooks** - Pre/post state execution
- **Metrics** - Track success rates, durations