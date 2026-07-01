# Loops Guide

> **When to use this**: You want to automate a recurring or multi-step task — fix tests
> until they pass, refine a backlog overnight, keep docs in sync — without prompting each
> step yourself. This guide covers loop concepts, authoring, and troubleshooting. To look
> up a specific built-in loop, see the [Built-in Loops Reference](LOOPS_REFERENCE.md).

## Contents

- [What Is a Loop?](#what-is-a-loop)
- [Quick Start](#quick-start)
- [Choose Your Loop](#choose-your-loop)
- [How Loops Work](#how-loops-work)
- [Common Loop Patterns](#common-loop-patterns)
- [Walkthrough: Creating and Running a Loop](#walkthrough-creating-and-running-a-loop)
- [Built-in Loops](#built-in-loops)
- [Beyond the Basics](#beyond-the-basics)
- [Background Mode](#background-mode)
- [Harness Loops](#harness-loops)
- [CLI Quick Reference](#cli-quick-reference)
- [Pattern: Using --check with Exit Code Evaluators](#pattern-using---check-with-exit-code-evaluators)
- [Tips](#tips)
- [Composable Sub-Loops](#composable-sub-loops)
- [Loop Discovery: category and labels](#loop-discovery-category-and-labels)
- [Reusable State Fragments](#reusable-state-fragments)
- [Loop Template Inheritance via `from:`](#loop-template-inheritance-via-from)
- [Linear Flow Shorthand via `flow:`](#linear-flow-shorthand-via-flow)
- [Troubleshooting](#troubleshooting)
- [Further Reading](#further-reading)

---

## What Is a Loop?

A loop is a YAML-defined automation workflow that runs commands, evaluates results, and decides what to do next — without you prompting each step. Under the hood, each loop is a **Finite State Machine (FSM)**: a set of states connected by transitions, with a clear start and end.

Why does this matter? LLMs are stateless — they don't remember what happened two prompts ago. The FSM gives them persistent memory of what was tried, what worked, and when to stop.

```
You write:    FSM YAML (or use /ll:create-loop)
You run:      ll-loop run <name>
```

**Why a loop instead of a sprint or doing it by hand?**

| Approach | Shape | Use when |
|----------|-------|----------|
| Manual prompting | You drive every step | One-off task, exploratory work, no retry needed |
| Sprint (`ll-sprint`) | Batch: a curated issue list processed once | A known set of issues to implement this week |
| Loop (`ll-loop`) | Recurring: check → act → re-check until a condition holds | Automatic retry on failure, quality gates, scheduled or autonomous work |

## Quick Start

1. **Create**: `/ll:create-loop` — answer the wizard prompts, or pass a description to skip them (e.g., `/ll:create-loop run mypy until it passes`)
2. **Validate**: `ll-loop validate <name>` — check your YAML for errors
3. **Run**: `ll-loop run <name>` — start the loop

For a complete example, see the [Walkthrough](#walkthrough-creating-and-running-a-loop) below.

### When NOT to Use a Loop

Loops add overhead — a YAML file, state management, and retry logic. For a one-off task,
just run the command directly. Use a loop when you need: automatic retry on failure,
repeated execution on a schedule, or quality gates that must pass before moving forward.

## Choose Your Loop

Before writing a new loop, check whether an existing one fits:

```
What do you need?
│
├─ One-off task with verifiable done-criteria ──→ general-task
│     ll-loop run general-task "refactor auth to use DI"
│
├─ Fix something until a check passes ──────────→ /ll:create-loop (fix-until-clean pattern)
│     "run mypy, fix errors, repeat"
│
├─ Nightly / recurring quality scan ────────────→ /ll:create-loop (maintain-constraints pattern)
│     pair with --background and maintain: true
│
├─ Brainstorm ideas under multiple lenses ───────→ brainstorm
│     ll-loop run brainstorm "ways to reduce flaky tests"
│
├─ Refine or implement backlog issues ──────────→ rn-implement, recursive-refine, autodev
│
├─ Build a project from a spec file ────────────→ rn-build
│
├─ Improve a prompt or skill automatically ─────→ apo-* loops
│
└─ Not sure which loop fits ────────────────────→ loop-router
      ll-loop run loop-router "describe your goal"
```

Every loop named above is documented in the [Built-in Loops Reference](LOOPS_REFERENCE.md). `loop-router` is the universal entry point: it classifies a natural-language goal, scores candidate loops, and dispatches to the winner.

## How Loops Work

Loops live in `.loops/` as YAML files. Each loop has:

- **States** — units of work (run a check, apply a fix, etc.)
- **Transitions** — edges between states (on success go here, on failure go there)

When a loop runs, the engine:

1. Enters the **initial state** and runs its action
2. Evaluates the result (exit code, output pattern, metric, etc.)
3. Follows the matching **transition** to the next state
4. Repeats until reaching a **terminal state** or hitting a safety limit

Use `/ll:create-loop` for an interactive wizard, or write FSM YAML directly (see the [FSM Loop System Design](../generalized-fsm-loop.md) for the schema).

### Safety Limits

A loop whose fix never works would run forever. Picture a two-state loop: `check` fails, `fix` edits the wrong file, `check` fails again — nothing stops it, and every cycle costs tokens. Four loop-level guards exist to stop exactly this:

| Field | Default | What it stops |
|-------|---------|---------------|
| `max_steps` | `50` | Runaway total work. Counts every state execution; when spent, the loop terminates with `terminated_by="max_steps"`. |
| `on_max_steps` | unset | Silent budget exhaustion. Names a state to run exactly once when the step cap fires (e.g., publish the best result so far) before terminating. |
| `max_iterations` | unset | Full-pass cap. Counts complete loop cycles (maintain-mode restarts); terminates with `terminated_by="max_iterations_reached"` when reached. |
| `on_max_iterations` | unset | Names a state to run exactly once when the full-pass cap fires before terminating. |
| `max_edge_revisits` | `100` | Tight ping-pong cycles. If any single state→state edge fires more than this, the loop terminates with `terminated_by="cycle_detected"` — long before `max_steps` would notice. Lower it (e.g., `5`) on short loops to surface regressions faster. |
| `circuit.repeated_failure` | unset | A single state failing the same way every iteration. See the stall detector below. |

### Stall Detector (circuit-repeated-failure)

`max_edge_revisits` can't catch a state that fails identically without re-traversing an edge — for example, a quality gate whose action times out every iteration. The stall detector compares the full `(state, exit_code, verdict)` triple across iterations and fires after `window` consecutive matches (default 3). One non-matching iteration resets the streak.

```yaml
circuit:
  repeated_failure:
    window: 3                  # consecutive iterations with identical triple
    on_repeated_failure: abort # "abort" terminates, or name a recovery state
```

**False-positive stalls in check↔work loops (BUG-1674):** States with `next:` (no `evaluate:`) are invisible to the stall detector — only eval-bearing states record triples. In a `check`→`work`→`check` ping-pong where `work` uses `next:`, the detector sees three identical `check` triples and fires even though `work` made real progress on disk. Fix: list the files `work` writes under `progress_paths` — when any listed path's `(mtime, size)` changes between consecutive `check` records, the rolling window resets:

```yaml
circuit:
  repeated_failure:
    window: 3
    on_repeated_failure: diagnose
    progress_paths:
      - "${env.PWD}/.loops/tmp/plan.md"
```

## Common Loop Patterns

```
What are you trying to do?
│
├─ Fix a specific problem ──────────→ Fix until clean
│   "Run check, if fails run fix, repeat"
│
├─ Maintain multiple standards ─────→ Maintain constraints
│   "Check A, fix A, check B, fix B, ..."
│
├─ Reduce/increase a metric ────────→ Drive a metric
│   "Measure, if not at target, fix, measure again"
│
├─ Run ordered steps ───────────────→ Run a sequence
│   "Do step 1, do step 2, check if done, repeat"
│
├─ Apply a skill to many items ─────→ Harness a skill
│   "Discover items, run skill, pass evaluation pipeline, advance"
│
├─ Chain existing loops together ───→ Composable sub-loops
│   "Run loop A, then loop B, using the same context"
│
└─ Route goal to the right loop ────→ Orchestration (router)
    "Classify goal, score candidate loops, dispatch to winner"
```

| Loop type | States | Branching | Best for |
|-----------|--------|-----------|----------|
| Fix until clean | evaluate, fix, done | Binary (pass/fail) | Single check + fix |
| Drive a metric | measure, apply, done | Three-way (target/progress/stall) | Metric optimization |
| Maintain constraints | 2 per constraint + 1 | Binary per constraint | Multi-gate quality |
| Run a sequence | 1 per step + 2 | Binary exit check | Ordered workflows |
| Harness a skill | discover, execute, check_*, advance, done | Multi-phase evaluation | Batch processing with layered quality gates |
| Composable sub-loops | 1 per child loop + done | Binary per child | Multi-stage pipelines from existing loops |
| Orchestration | classify, score, dispatch, review, done | Multi-way | Dynamic dispatch to the best-fit loop; see `loop-router`, `loop-composer`, and `goal-cluster` in the [reference](LOOPS_REFERENCE.md#cluster-vs-composer-vs-router) |

Use `/ll:create-loop` to build any of these. Pass a natural-language description to skip the wizard (e.g., `/ll:create-loop reduce lint errors to zero`).

## Walkthrough: Creating and Running a Loop

A complete example: a loop that fixes test failures until all tests pass.

### 1. Create

Run `/ll:create-loop fix tests until they pass`, or write the YAML directly and save it to `.loops/fix-tests.yaml`:

```yaml
name: fix-tests
initial: evaluate
max_steps: 10
states:
  evaluate:
    action: "pytest tests/"
    on_yes: done
    on_no: fix
    on_error: fix
  fix:
    action: "Fix failing tests based on the pytest output"
    action_type: prompt
    next: evaluate
  done:
    terminal: true
```

### 2. Validate and Preview

```bash
ll-loop validate fix-tests    # schema errors, unreachable states, meta-loop rules
ll-loop show fix-tests        # states, transitions, and an ASCII diagram
```

### 3. Test Before Committing to a Full Run

```bash
ll-loop test fix-tests                          # run ONE iteration for real, then stop
ll-loop simulate fix-tests                      # trace paths interactively, no actions run
ll-loop simulate fix-tests --scenario all-fail  # auto-select verdicts to trace a path
```

`test` executes the initial state's action and shows the routing decision — use it to confirm wiring. `simulate` never runs actions — use it to trace paths through complex FSMs.

### 4. Run

```bash
ll-loop run fix-tests
```

The engine enters `evaluate`, runs `pytest tests/`, checks the exit code, and follows the transition. If tests fail, it enters `fix`, sends the fix prompt to Claude, then returns to `evaluate` — until tests pass or `max_steps` is reached.

### 5. Monitor

```bash
ll-loop status fix-tests     # current state and iteration count
ll-loop history fix-tests    # full execution history
```

### 6. A/B Comparison (--baseline)

To validate that a harness loop actually improves output quality over an unguided LLM call, run it with `--baseline`:

```bash
ll-loop run harness-single-shot --baseline
```

This runs two arms in parallel — the full loop versus an ungated single-shot invocation — and a blind LLM judge scores both outputs. A summary (`ab.json` plus a printed pass-rate delta) tells you whether the harness earns its token cost. Use `--baseline-skill` to override the baseline arm and `--items` to set the number of compare cycles. See [AUTOMATIC_HARNESSING_GUIDE.md § Validating Your Harness](AUTOMATIC_HARNESSING_GUIDE.md) for interpretation guidance.

## Built-in Loops

Dozens of loops ship with little-loops, grouped by purpose:

| Group | Examples |
|-------|----------|
| Routing & orchestration | `loop-router`, `loop-composer`, `goal-cluster` |
| General-purpose | `general-task`, `rn-build`, `dataset-curation` |
| API adoption | `adopt-third-party-api`, `assumption-firewall`, `integrate-sdk` |
| Research & knowledge | `deep-research`, `apply-research`, `rn-plan` |
| Issue management | `rn-implement`, `recursive-refine`, `autodev`, `auto-refine-and-implement` |
| Code quality | `dead-code-cleanup`, `docs-sync`, `test-coverage-improvement` |
| Evaluation & RL | `outer-loop-eval`, `agent-eval-improve`, `rl-rlhf` |
| Prompt optimization (APO) | `apo-textgrad`, `apo-beam`, `examples-miner` |
| Harness examples | `harness-single-shot`, `html-anything`, `svg-image-generator` |

The full catalog — context variables, FSM flows, and invocation examples for every loop — lives in the **[Built-in Loops Reference](LOOPS_REFERENCE.md)**. Install any built-in to `.loops/` to customize it: `ll-loop install <name>`.

## Beyond the Basics

The sections below cover features you'll meet as you move past simple loops. For full technical details — schema definitions, compiler internals, and advanced examples — see the [FSM Loop System Design](../generalized-fsm-loop.md).

### Evaluators

Evaluators interpret action output and produce a **verdict** string used for routing. Every state gets a default evaluator based on its action type.

| Evaluator | Verdicts | Default for | When to use |
|-----------|----------|-------------|-------------|
| `exit_code` | `yes` / `no` / `error` | shell commands | CLI tools that report pass/fail via exit code |
| `output_numeric` | `yes` / `no` / `error` | — | Compare parsed numeric output to a target |
| `output_json` | `yes` / `no` / `error` | — | Extract a JSON path value and compare |
| `output_contains` | `yes` / `no` / `error` (with `error_patterns`) | — | Regex or substring match on stdout; add `error_patterns` to route auth/error output via `on_error` |
| `convergence` | `target` / `progress` / `stall` | metric-tracking states | Track a metric toward a goal value |
| `diff_stall` | `yes` / `no` / `error` | — | Detect when consecutive iterations produce no git diff changes (see [Stall Detection](#stall-detection)) |
| `action_stall` | `yes` / `no` | — | Detect when the same action string or context values repeat for N iterations (file-backed, no git required) |
| `llm_structured` | `yes` / `no` / `blocked` / `partial` | slash commands, prompts | Natural-language judgment via LLM |
| `mcp_result` | `success` / `tool_error` / `not_found` / `timeout` | `mcp_tool` actions | Evaluate MCP server tool call results |
| `comparator` | `yes` / `no` / `tie` / `no_baseline` | — | Blind A/B comparison against a stored baseline via LLM judge; requires `baseline_path` |
| `contract` | `yes` / `no` / `error` | — | Assert producer/consumer file pairs align via LLM judge; requires `pairs` |
| `classify` | *(token from stdout)* | — | Returns the last non-empty line of stdout as the verdict; pair with a `route:` table for single-state multi-way routing |

Override the default by adding an `evaluate:` block to a state:

```yaml
evaluate:
  type: output_contains
  pattern: "All checks passed"
```

**Exit-code short-circuit**: When an action exits non-zero, evaluators that don't intrinsically handle exit codes (`output_numeric`, `output_json`, `output_contains`, `convergence`, `comparator`, `classify`) immediately return `error` without running their normal logic. For `classify`, this means a crashing classifier routes via `route.error`/`route.default` rather than emitting a potentially mis-read token.

**Action timeouts (`exit_code=124`)**: When an action is killed at its `timeout:` budget, evaluators short-circuit to `verdict="error"` — so use `on_error:` as the canonical recovery branch for timeouts. This prevents truncated output from being misread as a deliberate `no`.

#### `classify` — Single-State Multi-Way Routing

The `classify` evaluator collapses verbose `output_contains` routing cascades into a single state. The action prints exactly one token to stdout; `classify` lifts that token to the verdict; a `route:` table dispatches to the matching state in one hop.

```yaml
diagnose:
  action_type: shell
  action: |
    # ... compute scores, print exactly one token on the final line ...
    echo "WIRE"
  evaluate:
    type: classify
    # optional: line: last (default) | first | <int index>
    # optional: source: "${captured.other_state.output}"  # defaults to this action's stdout
  route:
    IMPLEMENT: gate_implement
    DECIDE:    decide
    WIRE:      wire
    REFINE:    refine
    DECOMPOSE: emit_needs_decompose
    _:         emit_implement_failed    # unknown/empty token → default
    _error:    emit_implement_failed    # non-zero exit → error
```

- **Verdict** = trimmed last non-empty line of stdout (configurable via `line: first | last | <int>`).
- **Empty stdout** → empty token → resolves to `_` (default) route.
- **Non-zero exit** → `error` verdict (routes via `_error` / `_` — token is ignored, same as all non-exit-code-aware evaluators).
- **Validation**: `ll-loop validate` warns when a `classify` state has a `route:` table with no `_:` default entry — unknown tokens would dead-end the loop. Suppressed by `partial_route_ok: true` when intentional.

### Variable Interpolation

Use `${namespace.path}` in action strings, evaluator configs, and routing targets. Variables resolve at runtime.

| Namespace | Description | Example |
|-----------|-------------|---------|
| `context` | User-defined variables from the `context:` block | `${context.src_dir}` |
| `captured` | Values stored by `capture:` in earlier states | `${captured.lint.output}` |
| `prev` | Previous state's result | `${prev.output}` |
| `result` | Current evaluation result | `${result.verdict}` |
| `state` | Current state metadata | `${state.iteration}` |
| `loop` | Loop-level metadata | `${loop.name}` |
| `env` | Environment variables | `${env.HOME}` |

Escape literal `${` as `$${` — bash parameter expansion like `$${DEPTH:-0}` passes through to the shell unchanged.

**Safe interpolation** prevents crashes when referencing variables from potentially-skipped states: `${captured.step.output:default=none}` returns the default when the path is missing; `${captured.step.output?}` returns an empty string. Unsuffixed references raise `InterpolationError` on missing paths.

### Capture

Store a state's action output for use in later states:

```yaml
states:
  measure:
    action: "ruff check src/ 2>&1 | grep -c 'error' || echo 0"
    capture: lint_count
    next: apply
```

The captured value is then available as `${captured.lint_count.output}` (also `.stderr`, `.exit_code`, `.duration_ms`).

### Routing

States use **shorthand** (`on_yes`, `on_no`, `on_error`, `on_partial`, `on_blocked`, or any custom `on_<verdict>`) or a full **route table**:

```yaml
route:
  success: done
  failure: fix
  _: retry        # default for unmatched verdicts
  _error: error   # fallback for evaluation errors
```

Use `$current` as a target to retry the current state. Define `on_blocked` on any state whose action can return a `blocked` verdict (cannot proceed without external intervention) — an unrouted `blocked` verdict is a fatal error.

> **`on_no` → `on_error` fallthrough**: When a `no` verdict arrives and the state defines `on_error` but not `on_no`, the executor routes to `on_error`. Use this to share one recovery branch for both evaluator failures and hard-`no` verdicts.

### Action Types

| Type | Syntax hint | Default evaluator | Behavior |
|------|-------------|-------------------|----------|
| `shell` | No `/` prefix | `exit_code` | Run as shell command |
| `slash_command` | Starts with `/` | `llm_structured` | Execute a Claude Code slash command |
| `prompt` | Set explicitly | `llm_structured` | Send text to Claude as a prompt |
| `mcp_tool` | Set explicitly | `mcp_result` | Call an MCP server tool with structured params |

The engine auto-detects type: `/` prefix → `slash_command`, otherwise → `shell`. Set `action_type: prompt` explicitly for natural-language fix instructions. Contributed action types can be registered via `ActionProviderExtension` plugins.

#### Skills as Actions

Skills (invoked via `/ll:`) default to LLM-judged evaluation. When the skill supports `--check`, override the evaluator to `exit_code` for deterministic routing without an LLM call:

```yaml
check-format:
  action: "/ll:format-issue --all --check"
  action_type: slash_command
  evaluate:
    type: exit_code
  on_yes: next-step
  on_no: fix-format
```

To compose multiple skill calls in one state, use `action_type: prompt` and describe the sequence in natural language. See [Pattern: Using `--check`](#pattern-using---check-with-exit-code-evaluators) for a worked example.

#### MCP Tool Actions

MCP tool actions call a registered MCP server tool directly. The type is never auto-detected — set `action_type: mcp_tool` explicitly:

```yaml
get-issue-details:
  action: "github/get_issue"        # server_name/tool_name from .mcp.json
  action_type: mcp_tool
  params:                            # JSON object, supports ${...} interpolation
    issue_number: "${captured.current_item.output}"
  capture: issue_data
  route:
    success: process-issue
    tool_error: log-error
    not_found: abort
    timeout: retry-fetch
```

The `mcp_result` evaluator maps results to verdicts: `success` (tool returned a result), `tool_error` (tool ran but errored), `not_found` (server or tool not in `.mcp.json`), `timeout` (transport timeout, default 30 s).

### Retry and Timing Fields

Optional fields on any state:

| Field | Description |
|-------|-------------|
| `backoff:` | Seconds to wait before executing this state's action. Overridden at runtime by `--delay`. |
| `max_retries:` | Times the engine re-enters this state before routing to `on_retry_exhausted`. |
| `on_retry_exhausted:` | Target state when retries run out. Common in harnesses: `on_retry_exhausted: advance` to skip a stuck item. |
| `retryable_exit_codes:` | Restrict retry to these exit codes; other non-zero exits route directly to `on_error`. |
| `max_rate_limit_retries:` | Max short-burst 429 retries before the long-wait tier. Requires `on_rate_limit_exhausted`. |
| `on_rate_limit_exhausted:` | Target state when the total rate-limit wait budget (`rate_limit_max_wait_seconds`, default 6 h) is spent. |
| `rate_limit_backoff_base_seconds:` | Base for exponential backoff + jitter in the short-burst tier (default 30). |
| `rate_limit_long_wait_ladder:` | Long-wait tier sleep ladder in seconds (default `[300, 900, 1800, 3600]`). |

Example — skip an item after 3 failed attempts:

```yaml
execute:
  action: /ll:refine-issue ${captured.current_item.output} --auto
  action_type: prompt
  max_retries: 3
  on_retry_exhausted: advance
  next: check_concrete
```

### Subprocess Agent and Tool Scoping

These fields apply to `action_type: prompt` states only:

| Field | Description |
|-------|-------------|
| `agent:` | Passes `--agent <name>` to the Claude subprocess — loads `.claude/agents/<name>.md` with its system prompt and tool set. |
| `tools:` | Passes `--tools <csv>` — scopes available tools without a full agent file (e.g. `["Read", "Bash"]`). |
| `model:` | Passes `--model <id>` for this state only — use a cheap model for routing states, an expensive one for evaluation states. |

### Handoff Behavior

When a loop detects that Claude's context window is approaching its limit, it triggers a **handoff**. Set `on_handoff` at the loop level (not per state):

- **`spawn`** — save state and launch a fresh Claude session that continues automatically. Use for unattended long-running loops: nightly runs, backlog pipelines, APO loops.
- **`pause`** (default) — save state to disk and stop; you resume manually with `ll-loop resume <name>`. Use for interactive sessions where you want to review state between legs.
- **`terminate`** — stop immediately without saving. Use when partial execution is worse than none (e.g., a loop that must rewrite a file atomically) or in CI where resumption is meaningless.

```yaml
name: issue-refinement
on_handoff: spawn        # loop-level field
max_steps: 20
states:
  discover:
    action: "ll-issues list --status open"
    capture: active_issues
    next: refine
  refine:
    action: "/ll:refine-issue ${captured.active_issues.output}"
    action_type: slash_command
    next: discover
  done:
    terminal: true
```

A pause or spawn handoff preserves the current state name, iteration count, all `captured` values, and loop-level `context` variables. On resume, the engine re-enters the state where the handoff occurred with full variable context restored. For interactive session handoff details see [Session Handoff](SESSION_HANDOFF.md).

### Per-Loop Config Overrides

A top-level `config:` block embeds per-loop overrides for `ll-config.json` values:

```yaml
name: exploratory-refactor
config:
  handoff_threshold: 60
  commands:
    confidence_gate:
      readiness_threshold: 70
  automation:
    max_continuations: 5
```

Precedence, highest first: CLI flags → loop `config:` block → global `ll-config.json` → schema defaults. Supported keys: `handoff_threshold`, `commands.confidence_gate.readiness_threshold`, `commands.confidence_gate.outcome_threshold`, `automation.max_continuations` (alias `continuation.max_continuations`). Use `ll-loop show <name>` to see which overrides are active.

### Project-Wide Run Defaults

The `loops.run_defaults` block in `.ll/ll-config.json` lets you declare persistent defaults for `ll-loop run` flags so you don't have to retype them every invocation:

```json
{
  "loops": {
    "run_defaults": {
      "clear": true,
      "show_diagrams": "clean"
    }
  }
}
```

After adding this block, `ll-loop run my-loop` behaves identically to `ll-loop run my-loop --clear --show-diagrams clean`. Explicit CLI flags still take precedence — they are never overridden by config values.

**Fields:**
- `clear` (`boolean`, default `false`) — if `true`, inject `--clear` automatically
- `show_diagrams` (`string | null`, default `null`) — inject `--show-diagrams <value>`. Valid values: topologies (`layered`, `neighborhood`, `inline`, `window`), presets (`detailed`, `summary`, `clean`, `local`, `slim`, `oneline`), or `"default"` for bare `--show-diagrams` (summary preset). The `window` topology crops the real layered diagram to ±K layers around the active state (K sized to the viewport) with `▲ N layers above`/`▼ M layers below` overflow banners — it is also one rung in the pinned-pane auto-degrade ladder (ENH-2410). When a layered preset/default diagram is too big for the pinned pane, the auto-degrade ladder is **topology-aware** (ENH-2411): it branches on the FSM's classified shape (`linear`/`tree`/`general`, via `TopologyDetector`) and the failing viewport dimension. Linear and tree loops (tall but narrow) first shed box detail — title-only, then title-only with edge labels dropped — so every state stays visible before falling to the windowed crop or the synthetic neighborhood; wide fan-outs likewise prefer narrower title-only boxes before the window; hub-heavy general graphs prefer the windowed crop first. Every ladder still terminates in the single-line `fsm:` floor, and an **explicit** topology (`--show-diagrams neighborhood|window|inline|layered`) renders exactly once with no auto-degradation.
- `mode` (`string | null`, default `null`) — reserved for a future `--mode` flag; no effect currently
- `include` (`string`, default `""`) — default loop allowlist injected into `fsm.context["include"]`; empty string = all loops visible. Accepts comma-separated selectors: `loop-name`, `builtin:*`, `project:*`, `category:<label>`. Override per-invocation with `--context include=VALUE`

Only `ll-loop run` reads `run_defaults`. Other subcommands (`validate`, `list`, etc.) are unaffected.

> **Tip**: Run `/ll:configure loops.run_defaults` to set these fields interactively instead of editing the JSON directly.

### Scope-Based Concurrency

The `scope:` field declares which paths a loop operates on; the engine uses file-based locking so two loops never modify the same files at once:

```yaml
scope:
  - "src/"
  - "tests/"
```

If a conflicting loop is already running, `ll-loop run` errors. Use `--queue` to wait instead — the maximum wait is `loops.queue_wait_timeout_seconds` in `.ll/ll-config.json` (default 24 h), and queued loops acquire the lock in arrival order.

## Background Mode

The `-b` / `--background` flag detaches a loop from the terminal so it runs as an independent daemon. The parent command returns immediately and the loop survives terminal close. Use it for loops that run minutes-to-hours, for running several non-overlapping loops at once, or for unattended execution; stay in the foreground for short loops you want to watch.

```bash
ll-loop run my-scan --background       # or: ll-loop my-scan -b
```

### Monitoring progress

```bash
ll-loop status my-scan               # process alive? which state?
ll-loop monitor my-scan              # attach and render FSM state live (Ctrl-C detaches)

# Stream live output (works for both foreground and background runs)
tail -f $(ll-loop status my-scan --json | python3 -c "import sys,json; print(json.load(sys.stdin).get('log_file') or '')")
```

All runs — foreground and background — write ANSI-stripped output to `.loops/.running/<instance-id>.log` and structured events to `.loops/.running/<instance-id>.events.jsonl`; `ll-loop status <name> --json` returns both paths (`log_file`, `events_file`). The `instance-id` is `<loop-name>-<YYYYMMDDTHHMMSS>`. `ll-loop status` also reconciles orphaned state files: when a state file claims `running` but the PID is provably dead, it's rewritten to `interrupted` in place.

### Stopping and resuming

```bash
ll-loop stop my-scan                 # SIGTERM → graceful; second signal forces exit
ll-loop resume my-scan --background  # continue a paused loop, detached
```

### Notes

- `--background --queue` works, but queue-waiting happens inside the detached child — the parent returns immediately. Check progress with `ll-loop status`.
- Loops with non-overlapping scopes run concurrently; overlapping scopes conflict (add `--queue` to wait).
- `maintain: true` (YAML) and `--background` (CLI) are orthogonal: `maintain` makes a loop restart itself after reaching a terminal state; `--background` detaches the process. Combine them for a long-lived self-restarting daemon.

## Harness Loops

> **Advanced** — see [AUTOMATIC_HARNESSING_GUIDE.md](AUTOMATIC_HARNESSING_GUIDE.md) for the full
> harness guide. **Meta-loops** (loops that modify other harness artifacts) follow stricter
> design rules — see [HARNESS_OPTIMIZATION_GUIDE.md](HARNESS_OPTIMIZATION_GUIDE.md) and
> [CLAUDE.md § Loop Authoring](../../.claude/CLAUDE.md).

A **harness loop** wraps a skill or prompt in a layered quality evaluation pipeline, then repeats over a list of work items (or runs once in single-shot mode). The core idea: running a skill is easy; knowing the output is actually good is hard. Each result passes through up to five evaluation phases, cheapest first, so expensive LLM calls only happen when objective gates already pass:

| Phase | What it checks | Evaluator | Approx. latency |
|-------|----------------|-----------|-----------------|
| `check_concrete` | Exit code from test/lint/type command | `exit_code` | < 1s |
| `check_mcp` | MCP server tool call — deterministic external state | `mcp_result` | ~500ms |
| `check_skill` | Full agentic user simulation | `llm_structured` | 30–300s |
| `check_semantic` | LLM judges output quality | `llm_structured` | 3–10s |
| `check_invariants` | Diff line count — catches runaway changes | `output_numeric` | < 1s |

Run `/ll:create-loop` and select **"Harness a skill or prompt"** — the wizard derives the evaluation phases from your project config. Multi-item harnesses add `discover` and `advance` states around the evaluation chain.

The critical safeguard in multi-item loops is `max_retries` + `on_retry_exhausted: advance` on the `execute` state — without it, one item that never passes evaluation consumes the entire `max_steps` budget.

### Rate-Limit Resilience

HTTP 429 failures are handled by a two-tier retry ladder: short in-place retries with exponential backoff + jitter, then a long-wait ladder (5 min → 1 h) until a total wall-clock budget (default 6 h) is spent — designed to ride out multi-hour upstream outages. The jitter is load-bearing under `ll-parallel`: it prevents many worktrees from re-stampeding the API on the same tick.

A shared **cross-worktree circuit breaker** lets concurrent `ll-parallel` workers skip doomed calls when a peer has already observed a 429: the first worker to hit one writes a recovery timestamp to a sidecar file, and every other worker pre-sleeps until it passes. Entries older than 1 hour are ignored, so a crashed process can't wedge its peers. Configure under `commands.rate_limits`:

- `circuit_breaker_enabled` (default `true`) — set `false` to disable gating and sidecar writes.
- `circuit_breaker_path` (default `.loops/tmp/rate-limit-circuit.json`) — relocate the shared file.

API 5xx errors are retried automatically at the executor level (default 2 attempts, 30 s apart) — no YAML config needed.

#### Progressive tool-call throttling

A per-state safeguard that halts runaway action loops — e.g., a `prompt` state calling a tool in a tight loop without progress. Add a `throttle:` block to any state that could loop internally:

```yaml
fix_issue:
  action: "/ll:manage-issue"
  action_type: slash_command
  throttle:
    normal_max: 3    # expected call count per visit (informational)
    warn_max: 8      # emits throttle_warn event; loop continues
    hard_max: 12     # transitions to on_throttle_hard (or on_error)
  on_throttle_hard: escalate
  on_yes: verify
  on_error: escalate
```

**`type: learning`** states prove external-API assumptions against the Learning-Test Registry before advancing — proven targets pass through; missing or stale records trigger `/ll:explore-api` (up to `learning.max_retries` times); refuted records route to `on_blocked`. They legitimately make several tool calls per visit, so they're exempt from `hard_max`. Required fields: `learning.targets` (non-empty), `on_yes`, and one of `on_blocked` / `on_no`. See [LEARNING_TESTS_GUIDE.md](LEARNING_TESTS_GUIDE.md).

```yaml
states:
  learn:
    type: learning
    learning:
      targets:
        - "Anthropic SDK streaming"
      max_retries: 2
    on_yes: planning
    on_blocked: blocked
```

### Stall Detection

For prompt-based skills that may produce no-ops ("already done"), add a `check_stall` state using the `diff_stall` evaluator between `execute` and the first check state. Without it, idempotent skills silently exhaust `max_steps`:

```yaml
check_stall:
  action: "echo 'checking stall'"
  action_type: shell
  fragment: diff_stall_gate
  on_yes: check_concrete    # progress detected — continue evaluation
  on_no: advance            # stalled — skip this item
```

### When to Use a Harness vs. Hand-Authored Loop

| Approach | Effort | Best for |
|----------|--------|----------|
| Harness wizard | ~2 min | Wrapping a skill in quality gates; batch processing with standard evaluation |
| Hand-authored YAML | 30–60 min | Multi-branch routing, complex captured-variable logic, non-standard evaluation |

## CLI Quick Reference

| Command | Description |
|---------|-------------|
| `ll-loop run <name>` | Run a loop (also: `ll-loop <name>`); `--worktree` for isolated branch execution |
| `ll-loop validate <name>` | Check YAML for schema errors and unreachable states |
| `ll-loop show <name>` | Display states, transitions, and ASCII diagram (`--resolved` expands sub-loops) |
| `ll-loop test <name>` | Run a single iteration to verify configuration |
| `ll-loop simulate <name>` | Trace execution interactively without running actions (`--scenario all-pass\|all-fail\|all-error\|first-fail\|alternating`) |
| `ll-loop list` | List loops (public tier only by default); `--all`, `--internal`, `--examples`, `--running`, `--builtin`, `--category <cat>`, `--label <tag>` |
| `ll-loop status <name>` | Current state and iteration count (`--json` for paths and PIDs) |
| `ll-loop stop <name>` | Stop a running loop |
| `ll-loop resume <name>` | Resume an interrupted loop from saved state |
| `ll-loop history <name>` | Show history; pass `run_id` for a specific archived run; `--tail`, `--event`, `--state`, `--since`, `--verbose`, `--full`, `--json` |
| `ll-loop install <name>` | Copy a built-in loop to `.loops/` for customization |
| `ll-loop monitor <name>` | Attach to a running loop and render FSM state live |
| `ll-loop next-loop` | Suggest next loop(s) from execution history |
| `ll-loop diagnose-evaluators <name>` | Scan evaluator history for non-discriminating states (Bernoulli variance `p*(1-p)` below 0.05); exits 1 if any flagged |
| `ll-loop calibrate-budget <name>` | Check whether raising `max_steps` will earn its token cost; reports `⚠ WARN` when evaluator variance is too low |
| `ll-loop audit-meta <name>` | Summarize meta-eval agreement stats for a harness loop; `--json` for structured output |
| `ll-loop edit-routes <name>` | Render routing as a decision table and open in `$EDITOR`; `--dry-run` to print only; `--format csv` for CSV output; `--decision-table` to render compound policy-router condition×action grid (auto-detected for loops importing `lib/policy-router.yaml`); `--no-warnings` to skip gap/conflict output; `--allow-delete` to permit removal of states deleted from the table |

Common run flags: `--dry-run` (plan only), `-n <N>` (override `max_steps`), `--queue` (wait on scope conflicts), `-b` (background), `-f` (stream transitions), `--show-diagrams` (live FSM diagram; add `--clear` for a pinned dashboard), `--delay <s>` (sleep between iterations), `--context KEY=VALUE` (override context, repeatable), `--no-llm` (deterministic evaluators only), `--program-md PATH` (load a steering directive; see [program.md convention](../reference/program-md.md)). Run `ll-loop run --help` for the full list.

## Pattern: Using `--check` with Exit Code Evaluators

Issue prep skills (`format-issue`, `verify-issues`, `ready-issue`, `confidence-check`, `issue-size-review`, `map-dependencies`, `normalize-issues`, `prioritize-issues`) support a `--check` flag that runs analysis without side effects and exits non-zero when work remains. This makes them deterministic FSM evaluators — but since `/ll:` commands default to LLM-judged evaluation, each `--check` state must explicitly set `evaluate: type: exit_code`:

```yaml
name: prep-sprint
initial: check-format
max_steps: 20
states:
  check-format:
    action: "/ll:format-issue --all --check"
    action_type: slash_command
    evaluate:
      type: exit_code
    on_yes: check-verify
    on_no: fix-format
  fix-format:
    action: "/ll:format-issue --all --auto"
    action_type: slash_command
    next: check-format
  check-verify:
    action: "/ll:verify-issues --check"
    action_type: slash_command
    evaluate:
      type: exit_code
    on_yes: done
    on_no: fix-verify
  fix-verify:
    action: "Run /ll:verify-issues --auto to fix verification issues."
    action_type: prompt
    next: check-verify
  done:
    terminal: true
```

Each `check-*` state routes on the skill's exit code (0 = clean, 1 = work remains); the paired `fix-*` state remediates in auto mode and loops back. Chain as many check/fix pairs as you have gates.

## Tips

- **Start with low `max_steps`** (5-10) while developing a loop. Increase once the logic is proven.
- **State is persisted to disk** after every transition. If a loop is interrupted, `ll-loop resume` picks up where it left off.
- **Bind checkpoints to their task** with `${context.input_hash}` (a 12-char digest of the loop's input, auto-injected by the runner) so stale checkpoint files from an unrelated prior run can't trigger false crash-recovery skips.
- **Convergence loops** use `direction:` to control whether the metric should go down (`minimize`, default) or up (`maximize`).
- **Runs are archived automatically** to `.loops/.history/<timestamp>-<loop-name>/` on completion (state, events, and meta-eval telemetry). `ll-loop history <name>` lists archived runs.
- **Foreground runs always write a log file** to `.loops/.running/<instance-id>.log` (same path as background runs). Output is ANSI-stripped plain text; use `tail -f` or `grep` for post-hoc inspection. `ll-loop status <loop>` shows the path in the `Log:` line.

## Composable Sub-Loops

Any loop can invoke another loop as a **child FSM** using the `loop:` field on a state. The child runs to completion; its result (`success` or `failure`) drives the parent's transition:

```yaml
name: "quality-then-ship"
initial: "run_quality"
max_steps: 3
states:
  run_quality:
    loop: "fix-quality-and-tests"   # runs the built-in loop as a child
    on_success: "run_git"
    on_failure: "done"
  run_git:
    loop: "issue-refinement-git"
    on_success: "done"
    on_failure: "done"
  done:
    terminal: true
```

(`on_success` / `on_failure` are aliases for `on_yes` / `on_no`, accepted on all states.)

**Sharing context** — two options:

- `context_passthrough: true` on the sub-loop state shares the parent's full `context` and `captured` variables with the child, and merges the child's captures back on completion. Simple, but couples the child to parent variable names.
- **Typed parameter bindings** — the child declares a `parameters:` block (types: `string`, `integer`, `number`, `boolean`, `enum`, `path`), and the parent binds only what the child needs via `with:`:

```yaml
# Child declares the contract:
name: "recursive-refine"
parameters:
  input:
    type: string
    required: true

# Parent binds explicitly:
states:
  refine_issue:
    loop: "recursive-refine"
    with:
      input: "${captured.input.output}"
    on_success: "next_step"
    on_failure: "skip_and_continue"
```

`with:` and `context_passthrough` are mutually exclusive on the same state; missing `required: true` parameters and unknown `with:` keys are validation errors. Prefer `with:` for reusable children — a rename in the parent can't silently break the child.

<!-- TODO: update-docs stub — BUG-2305 — drafted 2026-06-25 -->
**`loop:` references are validated at definition time.** `ll-loop validate` (and `load_and_validate`) now checks that every `loop:` field resolves to an actual file on disk, reporting a `WARNING`-severity error if the referenced loop is missing. This catches typos and stale sub-loop names before a run starts rather than at runtime. Dynamically interpolated names (`loop: "${context.child_name}"`) are skipped — they can only be checked at runtime. If you see a warning like `Loop reference 'fix-quality-and-tests' does not resolve to any file.`, either correct the loop name or ensure the target YAML exists in your loops directory.
<!-- END TODO stub -->

When `--show-diagrams` is active, parent and child FSM diagrams render together, with the parent state highlighted throughout child execution — at any nesting depth.

| Approach | Best for |
|----------|----------|
| Sub-loop (`loop:`) | Reusing an existing, well-tested loop as a pipeline stage |
| Inline states | Custom logic that doesn't map cleanly to any existing loop |

For full sub-loop schema details see the [FSM Loop System Design](../generalized-fsm-loop.md#6-sub-loop-composition).

## Loop Discovery: category, labels, and visibility

Every loop YAML can declare a `category` string (grouping header in `ll-loop list`) and a `labels` list (arbitrary tags). Both are optional and have no effect on execution:

```bash
ll-loop list --category code-quality          # loops in one category
ll-loop list --label tests --label lint       # OR-match on labels
ll-loop list --builtin --category evaluation  # built-ins only
```

A loop can also declare a `visibility` tier — the *audience* axis, orthogonal to the topical `category`:

| `visibility` | Meaning | Shown in default `ll-loop list`? |
|---|---|---|
| `public` (default) | User-facing entry point | ✅ Yes |
| `internal` | Delegated-only sub-loop, never run directly (e.g. `oracles/*`) | ❌ No — `--internal` or `--all` |
| `example` | Demo or copy-me template (e.g. the `harness-*` EXAMPLE loops) | ❌ No — `--examples` or `--all` |

`ll-loop list` shows only `public` loops by default and prints a footer summarizing the hidden count plus a pointer to `loop-router` (the natural-language "which loop?" entry point). Resolution by name is unaffected — `ll-loop run <name>` still finds internal/example loops regardless of tier. Set the tier in frontmatter:

```yaml
name: my-sub-loop
visibility: internal   # public | internal | example
```

```bash
ll-loop list             # public only (the default, scannable view)
ll-loop list --all       # every tier
ll-loop list --internal  # only delegated-only sub-loops
ll-loop list --examples  # only demo/template loops
```

## Reusable State Fragments

A **fragment** is a named partial state definition stored in a library file. Any loop can import a library and reference a fragment by name — the fragment's fields merge into the state at parse time, with state-level fields winning. Fragments eliminate copy-pasted state structure (the same `action_type` + `evaluate` combination repeated across states) without a separate execution context.

Define a library as a YAML file with a top-level `fragments:` dict, then import it:

```yaml
# .loops/lib/common.yaml
fragments:
  shell_exit:
    description: |
      Shell command evaluated by exit code.
      State must supply: action, on_yes, on_no.
    action_type: shell
    evaluate:
      type: exit_code
```

```yaml
# your loop
import:
  - lib/common.yaml

states:
  check_tests:
    fragment: shell_exit    # inherits action_type + evaluate
    action: "pytest"
    on_yes: done
    on_no: fix_tests
```

State fields override fragment fields at every nesting level — to change one sub-field of `evaluate`, supply just that sub-field. You can also define `fragments:` inline in the loop file (local definitions shadow imported ones with the same name). Parameterized fragments declare a `parameters:` block and are bound at the call site via `with:` — so the same counter fragment can run in multiple states with different keys.

Browse a library without opening the YAML:

```bash
ll-loop fragments lib/common.yaml
```

**Mine fragments from history instead of hand-writing them**: the `/ll:distill-traces` skill mines `.loops/.history/` for a named loop and writes ranked state templates, transition patterns, and a human-readable catalogue to `scripts/little_loops/loops/lib/<loop-name>/`. Use its output as the starting point for a new library.

Built-in libraries ship in `scripts/little_loops/loops/lib/` — `common.yaml` (type-pattern gates), `cli.yaml` (pre-filled ll- CLI states), `benchmark.yaml`, `score-plan-quality.yaml`, `prompt-fragments.yaml`, `harness.yaml` (Playwright screenshot + rubric scoring), `composer.yaml`, `policy-router.yaml`, `rubric-router.yaml`, `apo-base.yaml` (a `from:` template, not a fragment collection), and `apo-shape-a.yaml`. They resolve automatically from user loops — no copying needed. Full fragment tables: [Built-in Fragment Libraries](LOOPS_REFERENCE.md#built-in-fragment-libraries).

| Approach | Best for |
|----------|----------|
| Fragment (`fragment:`) | Sharing a state *structure* across many states |
| Sub-loop (`loop:`) | Reusing a complete loop as a pipeline stage |
| `from:` inheritance | Sharing a whole loop skeleton across variants (next section) |

## Loop Template Inheritance via `from:`

When several variants of a loop share a category, iteration cap, default context, and terminal state, declare a parent template once and inherit it with `from:`. The child overrides only the deltas.

**Before** — every APO variant repeats the same skeleton:

```yaml
name: apo-beam
category: apo
max_steps: 20
timeout: 3600
on_handoff: spawn
context:
  prompt_file: system.md
  beam_width: 4
initial: generate_variants
states:
  generate_variants: { ... }
  done:
    terminal: true
```

**After** — the skeleton lives in one parent (`loops/lib/apo-base.yaml`):

```yaml
name: apo-base
category: apo
max_steps: 20
timeout: 3600
on_handoff: spawn
context:
  prompt_file: system.md
states:
  done:
    terminal: true
```

…and each variant declares only what differs:

```yaml
name: apo-beam
from: lib/apo-base
initial: generate_variants
context:
  beam_width: 4
states:
  generate_variants: { ... }
  # `done`, max_steps, timeout, on_handoff all inherited
```

The `from:` value resolves like any loop name — project `.loops/` first, then built-ins; a `lib/<name>` path reaches inheritance-only templates, which are hidden from `ll-loop list` because their parent chain also omits `initial:` and `states:` (they remain library-only fragments, not runnable loops). Pure context-override stubs outside `lib/` — stubs that inherit a full FSM from a parent and only override `context:` or metadata — are recognized as runnable after inheritance resolution and appear under `ll-loop list --internal` when they declare `visibility: internal`. The child must declare its own `name:`; everything else is optional.

> **Merge rules**: the loader deep-merges parent and child *before* validation. Scalars (`name`, `initial`, `max_steps`, …) — child wins. Lists (`labels`) — child replaces outright. Dicts (`context`, `states`, `route`, nested `evaluate`) — recursive merge, child keys override. A parent's `import:`/`fragments:` are merged in first, so a child can use any fragment its parent imports. Circular chains (`A → B → A`) raise an error naming the full chain. The `from:` key is stripped from the merged result — there is no runtime overhead.

`ll-loop validate`, `ll-loop show`, and `/ll:review-loop` all see the *materialized* (merged) loop; `ll-loop show --json` shows what the author wrote. `ll-loop list` also resolves inheritance before extracting the loop description, so loops that inherit their `description:` from a parent template display correctly in the list view (fixed in ENH-2101; previously showed a blank description).

## Linear Flow Shorthand via `flow:`

For simple linear pipelines, the `flow:` key replaces the `states:` map with an ordered list (the last entry is implicitly terminal; `initial:` must still name the first state):

```yaml
name: lint-and-test
initial: run_lint
flow:
  - run_lint
  - run_tests

state_defs:
  run_lint:
    action: "ruff check scripts/"
    fragment: shell_exit
  run_tests:
    action: "python -m pytest scripts/tests/"
    fragment: shell_exit
```

Branch with ternary syntax — `check_ready?run_impl:done` gives `check_ready` an `on_yes: run_impl` and `on_no: done`. Non-branching entries get an unconditional `next:` that advances on success *and* error; add `on_error:` to a `state_defs:` entry to route failures elsewhere.

`flow:` and `states:` are mutually exclusive. Use `flow:` for linear pipelines with at most a couple of branches; use `states:` for graphs with convergent paths, retry loops, or multi-branch routing.

## Troubleshooting

**Loop terminated with `terminated_by="error"` but no reason shown.** Open the run's `events.jsonl` (`ll-loop history <name> <run_id>`) and find the `loop_complete` event — it now includes an `error` field with the crash reason (e.g., `"Loop file not found: cua-fix-verify"`). For sub-loops that crash, the parent loop also captures the child's error string under `${captured.<state_name>.error}` so `on_error` handlers can log or surface it.

**Loop stuck repeating the same states.** Check `ll-loop history <name>` — if the same verdict repeats, the fix action isn't changing what the evaluator sees. Adjust the fix action, or rely on the automatic guards: `max_edge_revisits` (default 100) terminates tight cycles with `terminated_by="cycle_detected"`.

**`max_steps` hit unexpectedly.** Usually one work item (or one state) consuming the whole budget. Run `ll-loop history <name> --event route` to see where iterations went. Fixes: add `max_retries` + `on_retry_exhausted: advance` to the execute state (multi-item loops), or add a `diff_stall` gate so no-op iterations skip forward instead of repeating ([Stall Detection](#stall-detection)).

**Loop exits on the first iteration.** The initial state's evaluator probably returned `yes` immediately (nothing to do) or `error` with no `on_error` route. Run `ll-loop test <name>` to see the action output, verdict, and routing decision for a single iteration. If the action's exit code isn't what you expect, check that the command actually fails when work remains.

**Stall detector fires even though the loop is making progress.** This is the BUG-1674 false positive: a `check`→`work` ping-pong where `work` has no evaluator is invisible to the detector. Add `progress_paths` under `circuit.repeated_failure` listing the files `work` writes — see [Stall Detector](#stall-detector-circuit-repeated-failure).

**Scope conflict error.** Another loop holds a lock on overlapping paths. Find it with `ll-loop list --running` and stop it, or re-run with `--queue` to wait.

**LLM evaluator errors.** Claude CLI auth or network issue. Ensure the `claude` CLI is authenticated, or use `--no-llm` to fall back to deterministic evaluators.

<!-- TODO: update-docs stub — BUG-2302 — drafted 2026-06-25 -->
**Auth/credential failure aborts the loop immediately.** When a loop action outputs authentication or credential error text (e.g., `"Not logged in"`, `"Authentication required"`), the executor classifies the failure as `NON_RECOVERABLE` and routes directly to `on_error` — without retrying. Unlike `TRANSIENT` failures (network blips, timeouts), credential failures cannot be resolved by re-running the same action, so the executor bypasses any `max_retries` or `retryable_exit_codes` config and aborts. To handle this cleanly, add an `on_error:` route to your auth-sensitive state and point it to a recovery or abort state:

```yaml
cua_observe:
  action_type: shell
  action: "agent-desktop screenshot"
  evaluate:
    type: output_contains
    pattern: "screenshot captured"
    error_patterns:
      - "Not logged in"
      - "Authentication required"
  on_yes: cua_plan
  on_no: cua_observe
  on_error: auth_failed   # error_patterns match → verdict="error" → routes here

auth_failed:
  terminal: true
```

The `error_patterns` list on `output_contains` yields `verdict="error"` when any listed pattern is found in the output — this routes to `on_error` without raising an exception or incrementing the retry counter. Without `on_error:`, the loop terminates with `terminated_by="error"`. `error_patterns` do not trigger a `NON_RECOVERABLE` signal; they are a shorthand for verdict-routing, not an exception path.
<!-- END TODO stub -->

**"No state found" on resume.** The loop already completed or was never started — completed loops have no resumable state. Check `ll-loop status <name>`.

**Inspecting a run after the fact.** Every run archives state, events, and telemetry to `.loops/.history/<timestamp>-<loop-name>/`. Use `ll-loop history <name>` to list runs, `ll-loop history <name> <run_id> --verbose` for LLM call details, and `ll-loop status <name> --json` for live log/event file paths.

### Evaluator Health

Passing `ll-loop validate` (MR-1) confirms a non-LLM evaluator is _present_ — it does not confirm the evaluator is _discriminating_. An evaluator that always returns the same verdict (e.g., always `yes`) satisfies MR-1 but provides no useful signal.

**`ll-loop diagnose-evaluators <name>`** — run this after MR-1 passes to validate that each evaluator actually discriminates across run history. The command computes Bernoulli variance `p*(1-p)` over ≥10 runs per evaluator state. Variance below 0.05 flags the evaluator as toothless — it is not measuring anything useful, and the per-state output includes a recommendation for how to fix it (broaden the judge prompt, tighten the exit-code command, etc.). See the [CLI reference](../reference/CLI.md) for full flag and exit-code documentation.

**`ll-loop calibrate-budget <name>`** — run this before raising `max_steps` to check whether additional iterations will actually earn their token cost. The command reports `⚠ WARN` for evaluators with low variance and `✓ OK` for healthy ones:

```
Evaluator: check_quality (llm_structured)
  Variance p*(1-p): 0.02   ⚠ WARN: below 0.05 threshold — fix evaluator before increasing max_steps
Evaluator: check_exit (exit_code)
  Variance p*(1-p): 0.23   ✓ OK
```

`check_quality` nearly always returns the same verdict, so the loop cannot learn from its signal regardless of iteration count. `check_exit` discriminates well — more iterations here earn their cost. See the [CLI reference](../reference/CLI.md) for full output format documentation.

Fix toothless evaluators _before_ raising `max_steps`, or the extra budget is wasted.

## Further Reading

- [Built-in Loops Reference](LOOPS_REFERENCE.md) — full catalog: every built-in loop's context variables, FSM flow, and invocation examples
- [Recursive Loops Guide](RECURSIVE_LOOPS_GUIDE.md) — how the `rn-*` family (`rn-plan`, `rn-refine`, `rn-implement`, `rn-remediate`, `rn-decompose`) works and hands off between loops
- [FSM Loop System Design](../generalized-fsm-loop.md) — FSM schema, evaluators, variable interpolation, and full YAML reference
- [Automatic Harnessing Guide](AUTOMATIC_HARNESSING_GUIDE.md) — harness evaluation pipeline deep-dive, MCP gates, skill-as-judge, worked examples
- [Harness Optimization Guide](HARNESS_OPTIMIZATION_GUIDE.md) — meta-loop design rules and the optimizer error taxonomy
- [Configuration Reference](../reference/CONFIGURATION.md) — project-wide settings used by loop actions
- `/ll:create-loop` — interactive loop creation wizard (includes harness mode)
- `/ll:review-loop` — audit an existing loop for quality, correctness, and best practices
- `ll-loop --help` — full CLI reference for all loop subcommands
