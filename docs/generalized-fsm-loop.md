# Generalized FSM Loop System

## Overview

The little-loops (`ll`) loop system uses **Finite State Machines (FSM)** as the universal internal representation for all loops. Users can author loops using multiple paradigms that feel natural for their use case, and each paradigm compiles down to the same FSM-based YAML schema.

This design provides:
- **Flexibility** - Express loops in whatever mental model fits the problem
- **Consistency** - Single execution engine, predictable behavior
- **Debuggability** - FSM state is always inspectable
- **Composability** - All loops share the same underlying structure

## Authoring Paradigms

Users can create loops using any of these five paradigms:

| Paradigm | Best For | Mental Model |
|----------|----------|--------------|
| **Goal-Oriented** | Outcome-focused tasks | "I want X to be true" |
| **Convergence** | Metric optimization | "Drive metric toward target" |
| **Invariant Maintenance** | Continuous compliance | "Keep these constraints true" |
| **Imperative** | Sequential workflows | "Do X, then Y, until Z" |
| **FSM (Direct)** | Complex branching logic | "States and transitions" |

---

## Paradigm Definitions

### 1. Goal-Oriented

Declare the desired end state. The system determines how to get there.

```yaml
paradigm: goal
goal: "No type errors in src/"
tools:
  - /ll:check_code types
  - /ll:manage_issue bug fix
max_iterations: 20
```

**Compiles to FSM:**
```yaml
name: "goal-no-type-errors"
initial: "evaluate"
states:
  evaluate:
    action: "/ll:check_code types"
    on_pass: "done"
    on_fail: "fix"
  fix:
    action: "/ll:manage_issue bug fix"
    next: "evaluate"
  done:
    terminal: true
max_iterations: 20
```

---

### 2. Convergence

Drive a metric toward a target value using a specified action.

```yaml
paradigm: convergence
name: "reduce-lint-errors"
check: "ruff check src/ --output-format=json | jq '.count'"
toward: 0
using: "/ll:check_code fix"
tolerance: 0  # optional: stop when within tolerance of target
```

**Compiles to FSM:**
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
    on_target: "done"      # current_value within tolerance of target
    on_progress: "apply"   # value improved
    on_stall: "done"       # no progress (fixed point reached)
  apply:
    action: "/ll:check_code fix"
    next: "measure"
  done:
    terminal: true
```

---

### 3. Invariant Maintenance

Continuously maintain a set of constraints. When any breaks, fix it.

```yaml
paradigm: invariants
name: "code-quality-guardian"
constraints:
  - name: "tests-pass"
    check: "pytest"
    fix: "/ll:manage_issue bug fix"
  - name: "lint-clean"
    check: "ruff check src/"
    fix: "/ll:check_code fix"
  - name: "types-valid"
    check: "mypy src/"
    fix: "/ll:manage_issue bug fix"
maintain: true  # continuous mode
```

**Compiles to FSM:**
```yaml
name: "code-quality-guardian"
initial: "check_tests"
states:
  check_tests:
    action: "pytest"
    on_pass: "check_lint"
    on_fail: "fix_tests"
  fix_tests:
    action: "/ll:manage_issue bug fix"
    next: "check_tests"
  check_lint:
    action: "ruff check src/"
    on_pass: "check_types"
    on_fail: "fix_lint"
  fix_lint:
    action: "/ll:check_code fix"
    next: "check_lint"
  check_types:
    action: "mypy src/"
    on_pass: "all_valid"
    on_fail: "fix_types"
  fix_types:
    action: "/ll:manage_issue bug fix"
    next: "check_types"
  all_valid:
    terminal: true
    on_maintain: "check_tests"  # restart if maintain=true
maintain: true
```

---

### 4. Imperative

Sequential steps with explicit condition and iteration control.

```yaml
paradigm: imperative
name: "fix-all-types"
steps:
  - /ll:check_code types
  - /ll:manage_issue bug fix
condition:
  type: "exit_code"
  target: 0
max_iterations: 20
backoff: 2  # seconds between iterations
```

**Compiles to FSM:**
```yaml
name: "fix-all-types"
initial: "step_0"
states:
  step_0:
    action: "/ll:check_code types"
    next: "step_1"
    capture_exit: true
  step_1:
    action: "/ll:manage_issue bug fix"
    next: "evaluate"
  evaluate:
    check_condition:
      type: "exit_code"
      source: "step_0"
      target: 0
    on_met: "done"
    on_unmet: "step_0"
  done:
    terminal: true
max_iterations: 20
backoff: 2
```

---

### 5. FSM (Direct)

Full control over states and transitions for complex workflows.

```yaml
paradigm: fsm
name: "lint-fix-cycle"
initial: "check"
states:
  check:
    action: "/ll:check_code lint"
    on_fail: "fix"
    on_pass: "done"
  fix:
    action: "/ll:check_code fix"
    next: "check"
  done:
    terminal: true
max_iterations: 10
```

No compilation needed - this is the native format.

---

## Universal FSM Schema

All loops compile to this schema. Compilation from paradigm syntax to FSM is handled by a Python module (`little_loops.fsm`).

### Action Types

Actions can be either:
- **Shell commands**: `pytest`, `ruff check src/`, `npm run build`
- **Claude Code slash commands**: `/ll:manage_issue`, `/ll:check_code fix`

The executor detects slash commands by the leading `/` and routes them appropriately.

### Schema Definition

```yaml
# Required
name: string                    # Unique loop identifier
initial: string                 # Starting state name
states:                         # State definitions
  <state_name>:
    action: string              # Command/skill to execute (optional for decision states)
    next: string                # Default next state (unconditional)
    on_pass: string             # Next state if action succeeds
    on_fail: string             # Next state if action fails
    on_target: string           # Next state if metric hits target
    on_progress: string         # Next state if metric improved
    on_stall: string            # Next state if no progress
    on_error: string            # Next state on execution error (default: terminate loop)
    on_timeout: string          # Next state on action timeout
    terminal: boolean           # True if this is an end state
    capture: string             # Variable name to store output
    capture_exit: boolean       # Store exit code
    timeout: number             # Action-level timeout in seconds
    condition:                  # How to evaluate pass/fail (see Condition Types)
      type: string              # exit_code, output_contains, output_json, output_numeric
      source: string            # Value to evaluate (default: current action's stdout)
      # ... type-specific fields

# Optional
paradigm: string                # Source paradigm (for reference)
context: object                 # Shared variables/config
scope: array[string]            # Paths this loop operates on (for concurrency)
max_iterations: integer         # Safety limit (default: 50)
backoff: number                 # Seconds between iterations
timeout: number                 # Max total runtime in seconds (loop-level)
maintain: boolean               # Restart after completion
on_error: string                # Global error handling state
on_timeout: string              # Global timeout handling state
```

---

## Condition Types

By default, pass/fail is determined by exit code. For richer evaluation, use the `condition` field.

### Source Field (All Condition Types)

By default, conditions evaluate the current action's output. Use the optional `source` field to evaluate a different value—such as a captured variable from a previous state:

```yaml
# Evaluate current action's stdout (default behavior)
condition:
  type: "output_numeric"
  operator: "eq"
  target: 0

# Evaluate a captured value instead
condition:
  type: "output_numeric"
  source: "${captured.error_count.output}"
  operator: "eq"
  target: 0
```

This enables **decision states** that branch based on previously captured data without executing an action:

```yaml
states:
  measure:
    action: "wc -l < error.log"
    capture: "error_count"
    next: "decide"

  decide:
    # No action—just evaluates condition on captured value
    condition:
      type: output_numeric
      source: "${captured.error_count.output}"
      operator: "le"
      target: 5
    on_pass: "minor_fix"
    on_fail: "major_fix"
```

The `source` field accepts any valid interpolation expression (see Variable Interpolation).

### Exit Code (Default)

```yaml
condition:
  type: "exit_code"    # This is the default, can be omitted
# Exit 0 → on_pass
# Exit 1 → on_fail
# Exit 2+ → on_error
```

Standard Unix convention: exit 0 is success, exit 1 is failure, exit 2+ indicates errors.

### Output Contains

```yaml
condition:
  type: "output_contains"
  pattern: "All tests passed"    # Substring or regex
  negate: false                  # If true, pass when pattern NOT found
```

Useful when commands exit 0 but indicate failure in output.

### Output JSON

```yaml
condition:
  type: "output_json"
  path: ".summary.failed"        # jq-style path
  operator: "eq"                 # eq, ne, lt, le, gt, ge
  target: 0
```

For commands that output structured JSON (test frameworks, API responses).

### Output Numeric

```yaml
condition:
  type: "output_numeric"
  operator: "le"
  target: 5
```

Parse stdout as a number and compare. Useful with `wc -l`, `grep -c`, etc.

---

## Variable Interpolation

Actions and conditions can reference dynamic values using `${namespace.path}` syntax. Variables are resolved at runtime, just before each action executes.

### Available Namespaces

| Namespace | Description | Lifetime |
|-----------|-------------|----------|
| `context` | User-defined variables from `context:` block | Entire loop |
| `captured` | Values stored via `capture:` in previous states | Entire loop |
| `prev` | Shorthand for previous state's result | Current state only |
| `state` | Current execution metadata | Current state only |
| `loop` | Loop-level metadata | Entire loop |
| `env` | Environment variables | Entire loop |

### Namespace Contents

#### `context` - User-Defined Variables

Defined in the loop's `context:` block:

```yaml
context:
  target_dir: "src/"
  max_errors: 10
  metric_cmd: "mypy ${context.target_dir}"  # Can self-reference

states:
  check:
    action: "${context.metric_cmd}"
```

#### `captured` - Stored Action Results

When a state uses `capture: "varname"`, the result is stored with this structure:

```yaml
captured:
  varname:
    output: "..."       # stdout (string)
    stderr: "..."       # stderr (string)
    exit_code: 0        # exit code (integer)
    duration_ms: 1234   # execution time (integer)
```

Access fields via dot notation:

```yaml
states:
  count_errors:
    action: "mypy src/ 2>&1 | grep -c 'error:' || echo 0"
    capture: "error_count"
    next: "report"

  report:
    action: "echo 'Found ${captured.error_count.output} errors'"
    next: "fix"

  fix:
    action: "/ll:manage_issue bug fix"
    # Captured values persist—can still access error_count here
    next: "count_errors"
```

#### `prev` - Previous State Shorthand

Quick access to the immediately preceding state's result:

```yaml
${prev.output}      # stdout from previous state
${prev.stderr}      # stderr from previous state
${prev.exit_code}   # exit code from previous state
${prev.duration_ms} # execution time from previous state
${prev.state}       # name of previous state
```

Equivalent to `${captured.<previous_state_name>.*}` but doesn't require knowing the state name.

#### `state` - Current Execution Context

```yaml
${state.name}       # current state name (e.g., "check")
${state.iteration}  # current loop iteration (1-indexed)
${state.attempt}    # retry attempt within state (1-indexed, for $current retries)
```

#### `loop` - Loop Metadata

```yaml
${loop.name}        # loop identifier
${loop.started_at}  # ISO 8601 timestamp
${loop.elapsed_ms}  # milliseconds since loop started
${loop.elapsed}     # human-readable duration (e.g., "2m 34s")
```

#### `env` - Environment Variables

```yaml
${env.HOME}         # user home directory
${env.CI}           # CI environment flag
${env.PATH}         # system PATH
```

### Resolution Rules

| Rule | Behavior |
|------|----------|
| **Timing** | Resolved at runtime, just before action execution |
| **Undefined variable** | Loop terminates with error (fail-fast) |
| **Undefined namespace** | Loop terminates with error |
| **Empty value** | Interpolates as empty string (not an error) |
| **Escaping** | Use `$${` for literal `${` in output |
| **Nesting** | Not supported—`${context.${key}}` is invalid |
| **Type coercion** | All values interpolated as strings |

### Examples

#### Cross-State Data Flow

```yaml
name: "analyze-and-fix"
initial: "analyze"

states:
  analyze:
    action: "mypy src/ --json 2>/dev/null | jq '.error_count'"
    capture: "analysis"
    on_pass: "done"
    on_fail: "fix"
    condition:
      type: output_numeric
      operator: eq
      target: 0

  fix:
    action: "/ll:manage_issue bug fix"
    context:
      # Provide captured data as context for Claude
      error_count: "${captured.analysis.output}"
      iteration: "${state.iteration}"
      elapsed: "${loop.elapsed}"
    next: "analyze"

  done:
    action: "echo 'Fixed all errors in ${loop.elapsed}'"
    terminal: true
```

#### Conditional Logic with Captured Values

```yaml
name: "graduated-response"
initial: "check"
context:
  threshold: 5

states:
  check:
    action: "ruff check src/ --output-format=json | jq '.count'"
    capture: "lint_count"
    next: "decide"

  decide:
    # Use captured value in condition
    condition:
      type: output_numeric
      source: "${captured.lint_count.output}"
      operator: "le"
      target: "${context.threshold}"
    on_pass: "minor_fix"
    on_fail: "major_fix"

  minor_fix:
    action: "ruff check src/ --fix"
    next: "check"

  major_fix:
    action: "/ll:manage_issue enhancement fix"
    next: "check"
```

#### Using Environment Variables

```yaml
name: "ci-aware-loop"
initial: "check"

states:
  check:
    action: "pytest"
    on_pass: "done"
    on_fail: "fix"

  fix:
    # Different behavior in CI vs local
    action: |
      if [ "${env.CI}" = "true" ]; then
        echo "CI mode: creating issue instead of fixing"
        # Would transition to create_issue state
      else
        /ll:manage_issue bug fix
      fi
    next: "check"

  done:
    terminal: true
```

---

## Error Handling

Errors are distinct from failures:

| Outcome | Trigger | Default Behavior |
|---------|---------|------------------|
| **Pass** | Exit 0 (or condition met) | Transition via `on_pass` |
| **Fail** | Exit 1 (or condition unmet) | Transition via `on_fail` |
| **Error** | Exit 2+, crash, exception | Terminate loop with error status |
| **Timeout** | Action exceeds `timeout` | Terminate loop with error status |

### Customizing Error Handling

```yaml
states:
  check:
    action: "pytest"
    on_pass: "deploy"
    on_fail: "fix"
    on_error: "alert"           # Go to recovery state
    # OR
    on_error: "$current"        # Retry this state (with backoff)
    # OR omit for default (terminate loop)
```

The special token `$current` retries the current state, respecting `max_iterations`.

### Timeouts

Two levels of timeout protection:

```yaml
# Loop-level: total wall-clock time for entire execution
timeout: 3600                   # 1 hour max for the whole loop

states:
  build:
    action: "npm run build"
    timeout: 300                # 5 min max for this action
    on_timeout: "notify"        # Custom handling

  quick_lint:
    action: "ruff check ."
    timeout: 30                 # 30 sec expected
    # on_timeout omitted → terminates loop
```

- **Action timeout**: Catches hung processes, enables per-action limits
- **Loop timeout**: Catches infinite loops, bounds total execution time

---

## Concurrency and Locking

Only one loop can run at a time per scope. This prevents file corruption and conflicting modifications.

### Scope Declaration

Loops can declare which paths they operate on:

```yaml
name: "fix-api-types"
scope:
  - "src/api/"
  - "tests/api/"
```

| Scope Declaration | Behavior |
|-------------------|----------|
| Explicit paths | Loop claims those paths exclusively |
| No scope declared | Treated as `scope: ["."]` (whole project) |

### Concurrency Rules

| Scenario | Behavior |
|----------|----------|
| No other loop running | Start immediately |
| Another loop running, **non-overlapping** scopes | Start immediately (parallel execution) |
| Another loop running, **overlapping** scopes | Queue (wait) or fail with error |

### Implementation

The executor uses a global mutex with optional queuing:

1. **Check** `.loops/.running/*.pid` for active loops
2. **Compare** scopes for overlap
3. **If overlap detected**:
   - `--queue` flag: Wait for conflicting loop to finish, then start
   - Default: Fail with clear error message listing the conflicting loop
4. **If no overlap**: Start immediately, write own `.pid` file

```bash
# Default: fail if conflicting loop is running
ll-loop run .loops/fix-types.yaml
# Error: Cannot start 'fix-types' - loop 'quality-guard' is running with overlapping scope

# Queue mode: wait for conflicting loop to finish
ll-loop run .loops/fix-types.yaml --queue
# Waiting for 'quality-guard' to complete...
```

### Scope Overlap Detection

Two scopes overlap if any path in one is a prefix of (or equal to) any path in the other:

| Scope A | Scope B | Overlap? |
|---------|---------|----------|
| `src/` | `tests/` | No |
| `src/api/` | `src/api/handlers/` | Yes |
| `src/` | `src/api/` | Yes |
| `.` | anything | Yes |

---

## CLI Interface

### Command: `ll-loop`

Run and manage loops from the command line.

```bash
# Run a loop from file
ll-loop run .loops/fix-types.yaml

# Run with overrides
ll-loop run .loops/fix-types.yaml --max-iterations 5

# Run in background (daemon mode)
ll-loop run .loops/fix-types.yaml --background

# Dry-run (show what would happen without executing)
ll-loop run .loops/fix-types.yaml --dry-run

# Compile paradigm to FSM (for debugging/inspection)
ll-loop compile .loops/my-goal.yaml --output .loops/my-goal.fsm.yaml

# Validate loop definition
ll-loop validate .loops/fix-types.yaml

# List running/saved loops
ll-loop list
ll-loop list --running

# Show live status of a running loop
ll-loop status <loop-id>

# Resume a paused/failed loop
ll-loop resume <loop-id>

# Stop a running loop
ll-loop stop <loop-id>

# Show loop execution history
ll-loop history <loop-name>
```

### Subcommand Summary

| Subcommand | Description |
|------------|-------------|
| `run` | Execute a loop from YAML definition |
| `compile` | Convert paradigm syntax to FSM |
| `validate` | Check loop definition for errors |
| `list` | Show saved/running loops |
| `status` | Show live progress of a running loop |
| `resume` | Continue a paused loop |
| `stop` | Terminate a running loop |
| `history` | View past executions |

### Run Flags

| Flag | Description |
|------|-------------|
| `--background` | Run as daemon process |
| `--dry-run` | Show planned execution without running |
| `--queue` | Wait for conflicting loops instead of failing |
| `--max-iterations N` | Override max_iterations from definition |

### Loop Creation

Loops are created by:
1. **Manual authoring** - Edit YAML files directly in `.loops/`
2. **Claude Code** - Use `/ll:create-loop` slash command (see Claude Code Integration)

**Safety note**: When Claude generates loop definitions, the user reviews and approves before saving. This human-in-the-loop review is the primary safeguard against LLM mistakes or hallucinations in generated configs.

---

## Loop Storage

Loops are stored in the project's `.loops/` directory:

```
.loops/
  fix-types.yaml          # User-defined loops
  lint-guard.yaml
  .running/               # Currently executing loops
    fix-types.pid         # Process ID (for mutex/concurrency)
    fix-types.state.json  # Execution state (for resume)
    fix-types.events.jsonl # Event stream
  .history/               # Execution logs
    fix-types/
      2024-01-15T10-30-00.log
```

The `.pid` files enable concurrency control—the executor checks these before starting to detect scope conflicts.

---

## Execution Engine

The FSM executor is a headless Python process that runs loops independently of any Claude session.

### Execution Flow

1. **Loads** the FSM definition from YAML
2. **Initializes** state to `initial`
3. **Executes** the current state's action (see Action Execution below)
4. **Evaluates** condition to determine outcome (pass/fail/error)
5. **Emits** structured event (see Events below)
6. **Transitions** based on outcome and transition rules
7. **Repeats** until terminal state or limits reached

### Action Execution

Actions are executed differently based on type:

| Action Type | Detection | Execution Method |
|-------------|-----------|------------------|
| **Shell command** | No leading `/` | Direct subprocess execution |
| **Slash command** | Leading `/` | Invoke `claude` CLI programmatically |

**Shell commands** run directly via subprocess:
```python
result = subprocess.run(action, shell=True, capture_output=True)
```

**Slash commands** invoke the Claude CLI:
```bash
claude --dangerously-skip-permissions -p "/ll:manage_issue bug fix"
```

The `--dangerously-skip-permissions` flag is required for autonomous execution without user confirmation prompts.

### Claude CLI Integration Details

#### CLI Flags Reference

| Flag | Purpose | Required |
|------|---------|----------|
| `--dangerously-skip-permissions` | Skip interactive permission prompts for autonomous execution | Yes (for automation) |
| `-p` / `--print` | Print mode - executes command and prints response without interactive session | Yes |
| `--output-format json` | Return structured JSON output | Optional |
| `--output-format stream-json` | Streaming NDJSON for real-time processing | Optional |
| `--output-format text` | Plain text output (default) | Optional |

#### Environment Configuration

```python
env["CLAUDE_BASH_MAINTAIN_PROJECT_WORKING_DIR"] = "1"
```

This prevents Claude from changing directories during execution, ensuring worktree isolation.

#### Multi-Turn Interaction Handling

Slash commands may trigger multi-turn interactions. The executor handles this through complementary strategies:

| Strategy | Mechanism | Use Case |
|----------|-----------|----------|
| **Phase gates** | `--gates` flag pauses after each phase for user review | Supervised automation |
| **Resume capability** | `--resume` flag continues from checkmarks in plan files | Long-running tasks across sessions |
| **Context handoff** | Detects `CONTEXT_HANDOFF:` signal, spawns fresh session | Context limit recovery |
| **State persistence** | JSON files maintain progress across sessions | Crash recovery, audit trails |

For FSM loops, the executor monitors stdout for the `CONTEXT_HANDOFF: Ready for fresh session` signal. When detected, it:
1. Reads the continuation prompt from `.claude/ll-continue-prompt.md`
2. Spawns a new Claude session with the continuation context
3. Resumes execution from the saved state

#### Output Capture

The executor uses a three-tier approach for capturing Claude session output:

1. **Real-time streaming** - Line-buffered subprocess with `selectors.DefaultSelector()` for non-blocking I/O
2. **Structured parsing** - Regex-based extraction of verdicts, sections, and tables from natural language output
3. **JSON format** - `--output-format json` for deterministic structured output when needed

```python
process = subprocess.Popen(
    cmd_args,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    text=True,
    bufsize=1,  # Line buffered for immediate output
    cwd=working_dir,
    env=env,
)
```

Output is captured to `captured.<state_name>.output` for use in subsequent states via variable interpolation.

### Background Daemon

For background/long-running loops, the executor runs as a daemon process:

- Spawned via `ll-loop run --background`
- Writes PID to `.loops/.running/<name>.pid`
- Continues execution independent of terminal/session
- Calls Claude CLI when slash commands are needed
- Can be monitored via `ll-loop status` or event stream

### State Persistence

For resumability, the executor saves state to `.loops/.running/<name>.state.json`:
```json
{
  "current_state": "fix",
  "iteration": 3,
  "scope": ["src/", "tests/"],
  "context": {},
  "captured": {"error_count": 4},
  "started_at": "2024-01-15T10:30:00Z",
  "updated_at": "2024-01-15T10:32:15Z"
}
```

---

## Structured Events

Loops emit a stream of JSONL events for progress tracking, logging, and external tool integration.

### Event Stream

Events are written to `.loops/.running/<name>.events.jsonl`:

```jsonl
{"event": "loop_start", "loop": "fix-types", "ts": "2024-01-15T10:30:00Z"}
{"event": "state_enter", "state": "check", "iteration": 1, "ts": "..."}
{"event": "action_start", "action": "mypy src/", "ts": "..."}
{"event": "action_complete", "exit_code": 1, "duration_ms": 2340, "ts": "..."}
{"event": "transition", "from": "check", "to": "fix", "reason": "on_fail", "ts": "..."}
{"event": "state_enter", "state": "fix", "iteration": 1, "ts": "..."}
{"event": "action_start", "action": "/ll:manage_issue bug fix", "ts": "..."}
{"event": "action_complete", "exit_code": 0, "duration_ms": 45000, "ts": "..."}
{"event": "transition", "from": "fix", "to": "check", "reason": "next", "ts": "..."}
{"event": "loop_complete", "final_state": "done", "iterations": 3, "duration_ms": 154000, "ts": "..."}
```

### Event Types

| Event | Fields | Description |
|-------|--------|-------------|
| `loop_start` | loop, ts | Loop execution begins |
| `state_enter` | state, iteration, ts | Entering a state |
| `action_start` | action, ts | Action execution begins |
| `action_complete` | exit_code, duration_ms, output?, ts | Action finished |
| `condition_eval` | type, result, ts | Condition evaluated |
| `transition` | from, to, reason, ts | State transition |
| `loop_complete` | final_state, iterations, duration_ms, ts | Loop finished successfully |
| `loop_error` | state, error, ts | Loop terminated due to error |
| `loop_timeout` | state, elapsed_ms, ts | Loop exceeded timeout |

### CLI Progress Rendering

The CLI renders events as a live progress display:

```
$ ll-loop run fix-types.yaml
[1/20] check → running mypy src/...
       ✗ 12 errors (exit 1)
       → fix (on_fail)
[1/20] fix → running /ll:manage_issue...
       ✓ fixed 8 errors
       → check
[2/20] check → running mypy src/...
       ✗ 4 errors (exit 1)
       → fix (on_fail)
[2/20] fix → running /ll:manage_issue...
       ✓ fixed 4 errors
       → check
[3/20] check → running mypy src/...
       ✓ 0 errors (exit 0)
       → done (on_pass)

Loop completed: done (3 iterations, 2m 34s)
```

### External Consumption

Events enable integration with:
- **CI dashboards** - Stream events to build status
- **Monitoring** - Alert on `loop_error` or `loop_timeout`
- **Analytics** - Track loop success rates, durations

---

## Examples

### Example 1: Fix all type errors

```yaml
# .loops/fix-types.yaml
paradigm: convergence
name: "fix-types"
scope:
  - "src/"
check: "mypy src/ 2>&1 | grep -c 'error:' || echo 0"
toward: 0
using: "/ll:manage_issue bug fix"
```

```bash
ll-loop run .loops/fix-types.yaml
```

### Example 2: Maintain code quality

```yaml
# .loops/quality-guard.yaml
paradigm: invariants
name: "quality-guard"
constraints:
  - name: "tests"
    check: "pytest"
    fix: "/ll:manage_issue bug fix"
  - name: "lint"
    check: "ruff check ."
    fix: "/ll:check_code fix"
maintain: false  # run once, don't loop continuously
```

```bash
ll-loop run .loops/quality-guard.yaml
```

### Example 3: Complex deployment workflow

```yaml
# .loops/deploy.yaml
paradigm: fsm
name: "safe-deploy"
initial: "test"
states:
  test:
    action: "pytest"
    timeout: 300
    on_pass: "build"
    on_fail: "notify_fail"
  build:
    action: "npm run build"
    timeout: 120
    on_pass: "deploy_staging"
    on_fail: "notify_fail"
  deploy_staging:
    action: "./scripts/deploy.sh staging"
    on_pass: "smoke_test"
    on_fail: "rollback"
  smoke_test:
    action: "./scripts/smoke-test.sh"
    timeout: 60
    on_pass: "deploy_prod"
    on_fail: "rollback"
  deploy_prod:
    action: "./scripts/deploy.sh prod"
    on_pass: "done"
    on_fail: "rollback"
  rollback:
    action: "./scripts/rollback.sh"
    next: "notify_fail"
  notify_fail:
    action: "echo 'Deployment failed' | slack-notify"
    terminal: true
  done:
    action: "echo 'Deployment successful' | slack-notify"
    terminal: true
timeout: 1800  # 30 min max for entire deployment
```

```bash
ll-loop run .loops/deploy.yaml
```

---

## Claude Code Integration

Claude Code slash commands enable loop creation and management within conversations.

### Commands

| Command | Description |
|---------|-------------|
| `/ll:create-loop` | Interactive loop creation wizard |
| `/ll:run-loop <name>` | Execute a saved loop |
| `/ll:loop-status` | Show status of running loops |
| `/ll:stop-loop <id>` | Stop a running loop |

### `/ll:create-loop`

Guided loop creation within Claude Code:

```
User: /ll:create-loop

Claude: I'll help you create a loop. What would you like to accomplish?

User: Fix all type errors in src/

Claude: I'll create a convergence loop targeting zero type errors.

[Generates .loops/fix-type-errors.yaml]

paradigm: convergence
name: "fix-type-errors"
check: "mypy src/ 2>&1 | grep -c 'error:' || echo 0"
toward: 0
using: "/ll:manage_issue bug fix"

Would you like to run this loop now?
```

### Natural Language Loop Creation

Claude can recognize loop-like requests and offer to create loops:

```
User: "Keep fixing type errors until mypy passes"

Claude: This sounds like a good candidate for a loop. Should I create one?

User: Yes

Claude: [Creates .loops/fix-types.yaml and offers to run it]
```

### Execution Modes

| Mode | Flag | Description |
|------|------|-------------|
| **Foreground** | (default) | Blocks conversation, shows live progress |
| **Background** | `--background` | Daemon process, check with `/ll:loop-status` |
| **Dry-run** | `--dry-run` | Show planned execution without running |

```
/ll:run-loop fix-types --background
/ll:run-loop fix-types --dry-run
```

### How It Works

When Claude Code runs a loop:
1. The loop executor spawns as a headless process
2. Shell commands run via subprocess
3. Slash commands invoke `claude --dangerously-skip-permissions -p "..."`
4. Events stream to `.loops/.running/<name>.events.jsonl`
5. Claude Code can tail events to show progress

---

## Open Questions

Questions to resolve before implementation begins.

### Critical (Block Issue Breakdown)

1. **Paradigm Compilation Algorithms** - The examples show input/output, but:
   - Is a formal spec needed for the compiler (e.g., how does Goal → FSM work for edge cases)?
   - Or is "Claude generates reasonable FSM" the implementation?

2. **Slash Command Output Parsing** - The execution engine mentions "regex-based extraction of verdicts, sections, and tables":
   - What are the actual patterns?
   - Should this use `--output-format json` instead for reliability?

3. **MVP Scope** - The "Future Considerations" lists 6 items. Are any actually required?
   - Specifically: Is loop composition/nesting needed for v1?
   - Is the visual editor in scope?

4. **Installation Model** - Is `ll-loop` a new CLI entry point in `scripts/`? Or a Claude Code command?

### Important (Resolve During Implementation)

5. **Context Handoff** - The document describes detecting `CONTEXT_HANDOFF:` and spawning fresh sessions:
   - How does this interact with loop state persistence?
   - Is this mechanism already implemented in `ll-parallel`/`ll-auto` to reference?

6. **Maintain Mode Timing** - For `maintain: true` loops:
   - Is there a configurable delay between complete cycles?
   - Or does it restart immediately?

7. **Security Review** - Using `--dangerously-skip-permissions` for all slash commands:
   - Should there be a first-run consent mechanism?
   - Is this documented as a known trade-off?

---

## Future Considerations

- **Visual editor** - Web UI for FSM authoring with drag-and-drop states
- **Loop templates** - Pre-built loops for common workflows
- **Composition** - Nested loops, sub-FSMs as states
- **Parallel states** - Execute multiple states concurrently
- **Hooks** - Pre/post state execution hooks
- **Metrics** - Track loop performance, success rates
