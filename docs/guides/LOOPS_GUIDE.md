# Loops Guide

## Contents

- [What Is a Loop?](#what-is-a-loop)
- [Quick Start](#quick-start)
- [How Loops Work](#how-loops-work)
- [Common Loop Patterns](#common-loop-patterns)
- [Walkthrough: Creating and Running a Loop](#walkthrough-creating-and-running-a-loop)
- [Built-in Loops](#built-in-loops)
- [Beyond the Basics](#beyond-the-basics)
- [Prompt Optimization Loops (APO)](#prompt-optimization-loops-apo)
- [Harness Loops](#harness-loops)
- [CLI Quick Reference](#cli-quick-reference)
- [Pattern: Using --check with Exit Code Evaluators](#pattern-using---check-with-exit-code-evaluators)
- [Tips](#tips)
- [Composable Sub-Loops](#composable-sub-loops)
- [Loop Discovery: category and labels](#loop-discovery-category-and-labels)
- [Reusable State Fragments](#reusable-state-fragments)
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

## Quick Start

The fastest way to create and run a loop:

1. **Create**: `/ll:create-loop` — answer the wizard prompts
2. **Validate**: `ll-loop validate <name>` — check your YAML for errors
3. **Run**: `ll-loop run <name>` — start the loop

For a walkthrough of a real example, see [Walkthrough: Creating and Running a Loop](#walkthrough-creating-and-running-a-loop) below.

### When NOT to Use a Loop

Loops add overhead — a YAML file, state management, and retry logic. For a one-off task,
just run the command directly. Use a loop when you need: automatic retry on failure,
repeated execution on a schedule, or quality gates that must pass before moving forward.

## How Loops Work

Loops live in `.loops/` as YAML files. Each loop has:

- **States** — units of work (run a check, apply a fix, etc.)
- **Transitions** — edges between states (on success go here, on failure go there)

When a loop runs, the engine:

1. Enters the **initial state** and runs its action
2. Evaluates the result (exit code, output pattern, metric, etc.)
3. Follows the matching **transition** to the next state
4. Repeats until reaching a **terminal state** or hitting `max_iterations`

Use `/ll:create-loop` for an interactive wizard that guides you through creating loops, or write FSM YAML directly (see the [FSM Loop System Design](../generalized-fsm-loop.md) for the schema).

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
└─ Chain existing loops together ───→ Composable sub-loops
    "Run loop A, then loop B, using the same context"
```

| Loop type | States | Branching | Best for |
|-----------|--------|-----------|----------|
| Fix until clean | evaluate, fix, done | Binary (pass/fail) | Single check + fix |
| Drive a metric | measure, apply, done | Three-way (target/progress/stall) | Metric optimization |
| Maintain constraints | 2 per constraint + 1 | Binary per constraint | Multi-gate quality |
| Run a sequence | 1 per step + 2 | Binary exit check | Ordered workflows |
| Harness a skill | discover, execute, check_*, advance, done | Multi-phase evaluation (exit code → MCP → skill → LLM → diff) | Batch processing with layered quality gates |
| Composable sub-loops | 1 per child loop + done | Binary (success/failure) per child | Multi-stage pipelines from existing loops |

Use `/ll:create-loop` to build any of these interactively. The wizard generates FSM YAML ready to run.

## Walkthrough: Creating and Running a Loop

Here's a complete example: a loop that fixes test failures until all tests pass.

### 1. Create

Run `/ll:create-loop` to use the interactive wizard. Or write the FSM YAML directly:

```yaml
name: fix-tests
initial: evaluate
max_iterations: 10
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

Save this to `.loops/fix-tests.yaml`.

### 2. Validate

```bash
ll-loop validate fix-tests
```

The validator checks your YAML for schema errors, unreachable states, and missing transitions.

### 3. Test (Dry Run)

Run a single iteration to verify the loop configuration without a full execution:

```bash
ll-loop test fix-tests
```

This executes one iteration from the initial state, prints the action, result, and routing decision, then stops. Use it to confirm the YAML is wired correctly before committing to a full run.

### 4. Simulate

Step through the loop interactively without running any actions — useful for tracing paths through complex FSMs:

```bash
ll-loop simulate fix-tests
```

The simulator prompts you to choose a verdict at each state, then follows the transition and shows you the next state. Use `--scenario all-pass` or `--scenario all-fail` to auto-select verdicts and trace a path without interactive prompts:

```bash
ll-loop simulate fix-tests --scenario all-pass
```

### 5. Inspect

```bash
ll-loop show fix-tests
```

Output:

```
Loop: fix-tests
Description: All tests pass
Max iterations: 10
Source: .loops/fix-tests.yaml

States:
  [evaluate] [INITIAL]
    action: pytest tests/
    on_yes ──→ done
    on_no ──→ fix
    on_error ──→ fix
  [fix]
    action: Fix failing tests based on the pytest output
    type: prompt
    next ──→ evaluate
  [done] [TERMINAL]

Diagram:
  ┌──────────┐             ┌──────┐
  │ evaluate │───success──→│ done │
  └──────────┘             └──────┘
       │ ▲
  fail │ │ next
       ▼ │
     ┌─────┐
     │ fix │
     └─────┘

Run command:
  ll-loop run fix-tests
```

### 6. Run

```bash
ll-loop run fix-tests
```

The engine enters `evaluate`, runs `pytest tests/`, checks the exit code, and follows the transition. If tests fail, it enters `fix`, sends the fix prompt to Claude, then returns to `evaluate`. This continues until tests pass or `max_iterations` is reached.

### 7. Monitor

```bash
ll-loop status fix-tests     # Current state and iteration count
ll-loop history fix-tests    # Full execution history
```

## Built-in Loops

These loops ship with little-loops and cover common workflows. Install one to `.loops/` to customize it:

```bash
ll-loop install <name>       # Copies to .loops/ for editing
```

**General-Purpose**

| Loop | Description |
|------|-------------|
| `dataset-curation` | Scan raw data, quality-gate each item, fix or reject, balance distribution, validate schema, and publish a curated dataset |
| `general-task` | Definition-of-done driven task loop — define verifiable criteria first, then execute and verify until all criteria pass |
| `greenfield-builder` | End-to-end greenfield project builder: spec analysis → tech research → design artifacts → eval harness → issue decomposition → refinement → eval-driven improvement cycle |
| `eval-driven-development` | Reusable eval-driven development cycle: implement issues, run eval harness, capture issues from failures, refine, and iterate until the harness passes |
| `refine-to-ready-issue` | Single-issue refinement pipeline — refine → wire → confidence-check until the issue reaches ready status |

The `general-task` loop requires the `input` context variable — a natural-language description of the task to complete:

```bash
ll-loop run general-task --context input="Refactor the auth module to use dependency injection"
# Shorthand: plain string positional is equivalent (non-JSON fallback)
ll-loop run general-task "Refactor the auth module to use dependency injection"
```

> **JSON input shorthand**: Any loop that accepts context variables can receive them as a single JSON object positional argument. If the object's keys match defined context variables, each key is unpacked directly into context. If the JSON is invalid or keys don't match, the value is stored as a string in `context[input_key]` (the loop's configured input variable, usually `input`).
>
> ```bash
> # Equivalent: pass multiple context vars as a JSON object (auto-unpacked)
> ll-loop run recursive-refine '{"input": "FEAT-42,FEAT-43"}'
> ll-loop run outer-loop-eval '{"loop_name": "issue-refinement", "input": "some value"}'
> ```

The loop follows a structured cycle:

1. **Define Done** — writes verifiable acceptance criteria to `.loops/tmp/general-task-dod.md`
2. **Plan** — decomposes the task into discrete steps in `.loops/tmp/general-task-plan.md`
3. **Execute** — completes the first unchecked step and marks it done in the plan
4. **Verify** — checks each DoD criterion against actual filesystem/command output (uses `llm_structured` evaluation)
5. **Continue** — if any criteria remain unchecked, loops back to execute the next step

The loop runs up to 100 iterations and uses `on_handoff: spawn` to continue across session boundaries. Each execution step is deliberately scoped to a single plan item to keep changes small and verifiable.

The `refine-to-ready-issue` loop uses configurable confidence thresholds (default: readiness > 90, outcome confidence > 75). Override per-run:

```bash
ll-loop run refine-to-ready-issue --context readiness_threshold=85 --context outcome_threshold=70
```

To apply project-wide defaults, set `commands.confidence_gate.readiness_threshold` / `outcome_threshold` in `ll-config.json`, then install the loop locally (`ll-loop install refine-to-ready-issue`) and update its `context:` block defaults.

**Two-stage threshold check**: After `confidence_check` runs, the loop evaluates readiness and outcome confidence in two sequential shell states rather than one combined check. This split lets the loop route failures differently depending on which threshold was missed:

1. `check_readiness` — compares `confidence_score` against `readiness_threshold`. Failure routes to `check_refine_limit` (more refinement can close a technical gap).
2. `check_outcome` — compares `outcome_confidence` against `outcome_threshold`. Failure routes to `breakdown_issue` (low outcome confidence signals a scope problem; additional refinement won't fix it).

**Timeout recovery**: If `check_readiness` encounters an unexpected Python error, the loop falls back to `check_scores_from_file` — a deterministic recovery state that reads `confidence_score` and `outcome_confidence` directly from the issue's frontmatter via `ll-issues show --json`. If both scores meet the thresholds, the loop routes to `done`; otherwise it routes to `breakdown_issue`.

**Refine limit guard**: The loop enforces a **lifetime cap** on total `/ll:refine-issue` calls per issue across all loop runs. At the start of each run, the `check_lifetime_limit` state reads the issue's cumulative `refine_count` from `ll-issues refine-status --json` and compares it against `commands.max_refine_count` in `ll-config.json` (default: **5**, range: 1–20). If the cap is reached, the loop routes to `breakdown_issue` (invoking `/ll:issue-size-review`) rather than failing — a persistent readiness gap after multiple refinement passes signals a scope problem, not a content problem. To raise the limit, set `commands.max_refine_count` in your `ll-config.json`.

**Issue Management**

| Loop | Description |
|------|-------------|
| `backlog-flow-optimizer` | Iteratively diagnose the primary throughput bottleneck in the issue backlog |
| `evaluation-quality` | Multi-dimensional quality health check across issue quality, code quality, and backlog health; routes to remediation loops when thresholds are breached |
| `issue-discovery-triage` | Automated issue discovery and triage cycle |
| `auto-refine-and-implement` | For each backlog issue in priority order: recursively refine via `recursive-refine` (which handles decomposition into child issues), then implement all passed issues; skips issues that fail refinement or are decomposed, tracking them to avoid retrying; loops until backlog is exhausted |
| `issue-refinement` | Progressively refine all active issues — delegates per-issue refinement to the `refine-to-ready-issue` sub-loop with commit cadence |
| `recursive-refine` | Refine one or more issues to readiness recursively; when size-review decomposes an issue into children, each child is enqueued and refined before the next sibling; accepts a single ID or comma-separated list |
| `autodev` | Targeted refine-and-implement for a specific set of issues; accepts a single ID or comma-separated list and interleaves refinement and implementation — as soon as a leaf passes refinement it is implemented via `ll-auto --only` before the next leaf is refined; decomposed children are prepended depth-first; terminates when the input queue drains |
| `issue-size-split` | Review issues for sizing and split oversized ones |
| `prompt-across-issues` | Run an arbitrary prompt against every open/active issue sequentially; use `{issue_id}` placeholder in your prompt to inject each issue's ID |
| `issue-staleness-review` | Find old issues, review relevance, and close or reprioritize stale ones |
| `sprint-build-and-validate` | Create a sprint from the backlog and validate all included issues |
| `sprint-refine-and-implement` | Like `auto-refine-and-implement` but scoped to a named sprint; processes issues in sprint YAML order, refining each recursively before implementing |

### `sprint-build-and-validate` — Automated Sprint Creation and Validation

**Technique**: Selects up to `max_issues` open/active issues (P0–P1 first, then issues with no blocking dependencies), creates a sprint definition via `/ll:create-sprint --auto`, runs a size review to decompose oversized issues, then a linear quality-check pipeline (dependency mapping → conflict auditing → issue verification), commits the validated sprint, executes it via `ll-sprint run`, and — on non-zero exit — reads `.sprint-state.json` to feed blocked/failed issues into `recursive-refine` for recovery.

**When to use**: When you want to go from a backlog to a running sprint in one automated pass, with dependency and conflict checks baked in. Prefer `ll-sprint run` directly if you already have a sprint defined and validated.

**Required context variables:**

| Variable | Default | Description |
|----------|---------|-------------|
| `max_issues` | `8` | Maximum number of issues to include in the sprint |

**Invocation:**
```bash
ll-loop run sprint-build-and-validate

# Limit sprint to 5 issues
ll-loop run sprint-build-and-validate --context max_issues=5
```

**FSM flow:**
```
create_sprint → route_create → [sprint exists?]
  ├─ YES → size_review → map_dependencies → audit_conflicts → verify_issues → route_validation → [verified?]
  │           ├─ YES → commit → run_sprint → [exit code?]
  │           │                   ├─ 0 (clean) → done
  │           │                   └─ non-zero  → extract_unresolved → refine_unresolved → done
  │           └─ NO  → fix_issues → done
  └─ NO  → create_sprint (retry)
```

**State timeouts:**

| State | Timeout | Notes |
|-------|---------|-------|
| `create_sprint` | 300s | Headless `/ll:create-sprint --auto`; captures sprint name |
| `route_create` | — | Shell check: `ll-sprint list \| grep -q .`; retries if no sprint found; routes to `size_review` on success |
| `size_review` | 300s | `/ll:issue-size-review --auto` grouped across all sprint issues; Very Large issues (score ≥ 8) are decomposed before the sprint runs |
| `map_dependencies` | 300s | `/ll:map-dependencies --auto` grouped across all sprint issues |
| `audit_conflicts` | 300s | `/ll:audit-issue-conflicts --auto` grouped across all sprint issues |
| `verify_issues` | 600s | `/ll:verify-issues --auto` grouped across all sprint issues |
| `route_validation` | — | LLM-structured evaluation of verification results; routes to `commit` or `fix_issues` |
| `commit` | 120s | `/ll:commit --auto` with standard sprint commit message |
| `run_sprint` | 21600s (6h) | `ll-sprint run <name>` — parallelized wave execution; routes on exit code |
| `extract_unresolved` | 30s | Reads `.sprint-state.json`; merges `failed_issues` + `skipped_blocked_issues`; emits comma-separated IDs |
| `refine_unresolved` | — | Delegates to `recursive-refine` sub-loop via `context_passthrough: true` |
| `fix_issues` | 600s | `/ll:refine-issue --auto` for issues that failed verification; routes to `done` |

**Notes**: Each quality-check step runs once as a grouped call against all sprint issues — not per-issue. The sprint YAML is committed before `ll-sprint run` begins, so it's durable if the session is interrupted. Global FSM timeout is 25200s (7h); `max_iterations: 16`; `on_handoff: spawn` continues across session boundaries during the sprint execution phase. Clean sprint exits (exit 0) route directly to `done`; non-zero exits trigger the `extract_unresolved` → `refine_unresolved` recovery path.

Prior to the ENH-1051 refactor, this loop ran `/ll:confidence-check` per issue and could loop through a `fix_issues` remediation cycle many times before committing — and never actually executed the sprint. The current design runs each check once, then executes the sprint with automatic recovery for blocked or failed issues.

### `sprint-refine-and-implement` — Sprint-Scoped Refine-and-Implement Loop

**Technique**: Like `auto-refine-and-implement` but bounded to a named sprint. Reads `.sprints/<sprint_name>.yaml` and processes each issue in sprint YAML order: delegates `format → refine → wire → confidence-check` to the `recursive-refine` sub-loop (with automatic decomposition of oversized issues), then implements each issue that passed via `ll-auto --only`. Issues that fail refinement or are decomposed are recorded in a skip file and excluded from re-processing on resume.

**When to use**: When you have a defined sprint and want to run the full refine-and-implement pipeline over exactly those issues, in sprint order, rather than the confidence-ranking order that `auto-refine-and-implement` uses. Prefer `auto-refine-and-implement` for open-ended backlog processing.

**Invocation:**
```bash
ll-loop run sprint-refine-and-implement <sprint-name>

# Example
ll-loop run sprint-refine-and-implement sprint-1
```

Sprint file must exist at `.sprints/<sprint-name>.yaml` (standard sprint location). The sprint name is passed as a positional argument and stored as `context.sprint_name`.

**Required context variables:**

| Variable | Default | Description |
|----------|---------|-------------|
| `sprint_name` | *(positional)* | Name of the sprint to process; set automatically from the positional argument |
| `max_issues` | `100` | Maximum number of issues to process per run; guards against runaway iteration |

**Error behavior:**
- Missing sprint name → prints `Usage: ll-loop run sprint-refine-and-implement <sprint-name>` and exits to `done`
- Sprint file not found → prints `Sprint '<name>' not found at .sprints/<name>.yaml` and exits to `done`

**FSM flow:**
```
get_next_issue → [issue found?]
  ├─ YES → refine_issue (sub-loop: recursive-refine) → [success?]
  │           ├─ YES → get_passed_issues → [passed issues?]
  │           │           ├─ YES → implement_next → implement_issue → implement_next (loop)
  │           │           └─ NO  → get_next_issue
  │           └─ NO  → skip_and_continue → get_next_issue
  └─ NO  → done
```

**Notes**: All tmp files are prefixed `sprint-refine-and-implement-*` to avoid state collision with `auto-refine-and-implement` when both loops are used in the same project. The loop uses `on_handoff: spawn` and `max_iterations: 500` with an 8-hour global timeout, so it can survive session boundaries for long sprints.

**Skip tracking**: When `recursive-refine` marks an issue as skipped (refinement failure or decomposition), it is written to `.loops/tmp/sprint-refine-and-implement-skipped.txt` — both for the current run and for any future resume of the same sprint. Decomposed parents are additionally moved to `.issues/completed/` so they never re-appear as active candidates after a skip-file reset. On resume, `get_next_issue` reads the skip file and advances past any previously processed issues.

### `auto-refine-and-implement` — Full-Backlog Refine-and-Implement Loop

**Technique**: For each backlog issue in priority order, run `recursive-refine` as a sub-loop to bring it to ready status (with automatic decomposition of oversized issues into child issues). After refinement, all issues that passed are queued for implementation via `ll-auto --only`; decomposed parents are moved to `.issues/completed/` and recorded in a skip list; failed issues are recorded in a skip list — both are excluded from subsequent `ll-issues next-issue` calls so the loop never retries a persistently failing issue.

**When to use**: When you want fully-automated end-to-end issue processing — from raw backlog to committed implementation — without manual intervention between refinement and implementation. Prefer `issue-refinement` if you only want to refine issues without implementing them, or `ll-auto` for direct implementation without the refinement pass.

**Required context variables**:

| Variable | Default | Description |
|----------|---------|-------------|
| `max_issues` | `100` | Maximum number of issues to process before exiting |

**Invocation**:
```bash
# Process entire backlog
ll-loop run auto-refine-and-implement

# Limit to first 10 issues
ll-loop run auto-refine-and-implement --context max_issues=10
```

**FSM flow**:
```
init → get_next_issue → [issue found?]
         ├─ YES → refine_issue (sub-loop: recursive-refine) → [success?]
         │         ├─ YES → get_passed_issues → [any passed?]
         │         │         ├─ YES → implement_next → implement_issue (ll-auto --only) → implement_next (loop)
         │         │         └─ NO  → get_next_issue (loop)
         │         └─ NO  → skip_and_continue → get_next_issue (loop)
         └─ NO → done
```

**Skip tracking**: The `init` state runs at the start of each `ll-loop run auto-refine-and-implement` invocation and truncates both `.loops/tmp/auto-refine-and-implement-skipped.txt` and `.loops/tmp/auto-refine-and-implement-impl-queue.txt`, ensuring every run starts with a clean slate. After `recursive-refine` completes, `get_passed_issues` merges its skipped output (`.loops/tmp/recursive-refine-skipped.txt`) into `.loops/tmp/auto-refine-and-implement-skipped.txt`, and queues passed issues in `.loops/tmp/auto-refine-and-implement-impl-queue.txt` for sequential implementation. Each `get_next_issue` reads the skip file and passes the IDs as `--skip` to `ll-issues next-issue`, preventing infinite retry loops for persistently-unrefineable or decomposed issues within the current run.

**Notes**: The loop runs up to 100 iterations with an 8-hour timeout and uses `on_handoff: spawn` to continue across session boundaries. Use `ll-loop install auto-refine-and-implement` to copy the YAML to `.loops/` and customize the refinement thresholds or post-implementation steps.

### `autodev` — Targeted Refine-and-Implement for Specific Issues

**Technique**: Accepts a single issue ID or a comma-separated list. Drives a **single unified queue** through an interleaved refine-then-implement loop: delegates per-issue `format → refine → wire → confidence-check` to the `refine-to-ready-issue` sub-loop, and on threshold pass immediately runs `ll-auto --only` against that issue before dequeuing the next one. When `/ll:issue-size-review` decomposes an issue, the new children are prepended depth-first to the same queue and each child is refined-and-implemented before the next sibling. First implementation runs as soon as the first leaf passes refinement — no "refine-all-then-implement-all" gap. Terminates when the queue drains.

**When to use**: When you have a specific set of issues you want refined and implemented end-to-end. Unlike `auto-refine-and-implement`, this loop does not poll the backlog and does not maintain a skip list — the input set is finite and fixed. Prefer `auto-refine-and-implement` for full-backlog processing.

**Invocation**:
```bash
# Single issue
ll-loop run autodev "FEAT-42"

# Multiple issues (processed in order)
ll-loop run autodev "FEAT-42,BUG-17,ENH-99"
```

**FSM flow**:
```
init → dequeue_next → [queue empty?]
         ├─ YES → done
         └─ NO  → refine_current (sub-loop: refine-to-ready-issue)
                    → copy_broke_down → check_passed → [thresholds met?]
                         ├─ YES → implement_current (ll-auto --only) → dequeue_next
                         └─ NO  → detect_children → [children found?]
                                    ├─ YES → enqueue_children (prepend depth-first) → dequeue_next
                                    └─ NO  → size_review_snap → check_broke_down → [already size-reviewed?]
                                               ├─ YES → enqueue_or_skip → dequeue_next
                                               └─ NO  → recheck_scores → [passed now?]
                                                          ├─ YES → implement_current → dequeue_next
                                                          └─ NO  → run_size_review → enqueue_or_skip → dequeue_next
```

**Notes**: The loop runs up to 500 iterations with an 8-hour timeout and uses `on_handoff: spawn` to continue across session boundaries. Both `refine_current` (sub-loop) and `implement_current` (shell `ll-auto`) use the `with_rate_limit_handling` fragment (3 retries, 30s base backoff); `refine_current` on rate-limit exhaustion dequeues and continues, while `implement_current` on exhaustion terminates the loop via `done`. The broke-down handshake flag (written by `refine-to-ready-issue` to `.loops/tmp/recursive-refine-broke-down`) is copied after each sub-loop return into `.loops/tmp/autodev-broke-down`, so the rest of autodev's state machine reads only the `autodev-*` namespace. This interleaved design also means partial forward progress is preserved if the run is interrupted — any leaves that already passed refinement have already been implemented.

### `recursive-refine` — Depth-First Issue Refinement with Decomposition

**Technique**: Accepts a single issue ID or a comma-separated list. For each issue, delegates `refine → wire → confidence-check` to the `refine-to-ready-issue` sub-loop. If the sub-loop exits without meeting thresholds, the loop checks whether `breakdown_issue` already ran inside the sub-loop (via the `recursive-refine-broke-down` flag). If so, `/ll:issue-size-review` is skipped and the loop proceeds directly to `enqueue_or_skip`; otherwise it runs `/ll:issue-size-review` explicitly. When child issues are detected, they are prepended to the queue depth-first and refined before the next sibling. Issues that cannot be decomposed further are recorded as skipped.

**Child detection**: Uses a two-step parent-verification filter to avoid picking up unrelated issues created concurrently. First, `comm -13` of the pre- and post-refinement ID snapshots is written to `recursive-refine-diff-ids.txt`. Each candidate ID is then checked: its issue file must contain `Decomposed from <PARENT_ID>` (the line written by `/ll:issue-size-review` when it creates child issues) before it is accepted into `recursive-refine-new-children.txt`. Issues that appear in the diff but lack this parent reference are silently ignored.

**When to use**: When you have one or more issues you want refined to ready status, including any children that get split off along the way. Prefer `issue-refinement` for full-backlog refinement; use `recursive-refine` when you want targeted, tree-aware refinement of a specific set of issues.

**Breakdown guard**: After `detect_children` finds no children from the sub-loop, a `check_broke_down` state reads the `.loops/tmp/recursive-refine-broke-down` flag. If the flag is set (meaning `breakdown_issue` ran and already invoked `/ll:issue-size-review` inside the sub-loop), the loop skips `recheck_scores` and `run_size_review` and goes directly to `enqueue_or_skip`, preventing a duplicate size-review call.

**Score gate**: When `check_broke_down` passes (flag not set), a `recheck_scores` state checks whether the issue's current `confidence` and `outcome` scores already meet project thresholds. If both pass, the issue is recorded as passed and size-review is skipped entirely — avoiding unnecessary LLM cycles on already-ready issues.

**Required context variables**:

| Variable | Default | Description |
|----------|---------|-------------|
| `readiness_threshold` | `90` | Minimum confidence score for an issue to be considered ready (override via `commands.confidence_gate.readiness_threshold` in `ll-config.json`) |
| `outcome_threshold` | `75` | Minimum outcome confidence score (override via `commands.confidence_gate.outcome_threshold` in `ll-config.json`) |
| `max_refine_count` | `5` | Maximum `/ll:refine-issue` calls per issue lifetime; issues that exhaust this cap are routed to size-review instead of failing (override via `commands.max_refine_count` in `ll-config.json`) |

**Invocation**:
```bash
# Refine a single issue (positional input)
ll-loop run recursive-refine "FEAT-42"

# Refine multiple issues (depth-first: children of FEAT-42 resolved before FEAT-43)
ll-loop run recursive-refine "FEAT-42,FEAT-43,BUG-17"

# JSON shorthand: pass as a JSON object — keys auto-unpacked into context variables
ll-loop run recursive-refine '{"input": "FEAT-42,FEAT-43"}'

# Alternatively, set via --context flag
ll-loop run recursive-refine --context input="FEAT-42"
```

**FSM flow**:
```
parse_input → dequeue_next → [queue empty?]
  ├─ YES → done (prints summary)
  └─ NO  → capture_baseline → run_refine (sub-loop: refine-to-ready-issue)
              ├─ on_success → check_passed → [thresholds met?]
              │                ├─ YES → dequeue_next (loop)
              │                └─ NO  → detect_children
              └─ on_failure/on_error → detect_children → [children found from sub-loop?]
                                        ├─ YES → enqueue_children → dequeue_next (depth-first)
                                        └─ NO  → size_review_snap → check_broke_down → [breakdown_issue already ran?]
                                                                                        ├─ YES (flag=1) → enqueue_or_skip → dequeue_next
                                                                                        └─ NO  (flag=0) → recheck_scores → [scores pass?]
                                                                                                                            ├─ YES → dequeue_next
                                                                                                                            └─ NO  → run_size_review → enqueue_or_skip → dequeue_next
```

**Summary output**: When the queue is exhausted, `done` emits a structured summary:
```
=== Recursive Refine Summary ===

Passed  (2): FEAT-42, FEAT-43
Skipped (1): BUG-17
```

**Notes**: The loop runs up to 500 iterations with an 8-hour timeout and uses `on_handoff: spawn` to continue across session boundaries. Skipped issues are tracked in `.loops/tmp/recursive-refine-skipped.txt`; decomposed parents are also moved to `.issues/completed/` so they never re-appear as active candidates after a skip-file reset; issues that passed thresholds are in `.loops/tmp/recursive-refine-passed.txt`; the per-issue breakdown guard flag is in `.loops/tmp/recursive-refine-broke-down`.

**Code Quality**

| Loop | Description |
|------|-------------|
| `context-health-monitor` | Monitor context health via scratch file accumulation and session log size; compacts scratch files and archives stale outputs when pressure is detected |
| `dead-code-cleanup` | Find dead code, remove high-confidence items, and verify tests pass |
| `docs-sync` | Verify documentation matches the codebase and check for broken links |
| `fix-quality-and-tests` | Sequential quality gate: lint + format + types must be clean before tests run |
| `incremental-refactor` | Decompose a refactoring goal into safe atomic steps, execute each with test-gated commits, rollback and re-plan on failure |
| `test-coverage-improvement` | Measure test coverage, identify uncovered code paths, write tests for highest-risk gaps, and converge when coverage target is met |
| `worktree-health` | Continuous monitoring of orphaned worktrees and stale branches |

### `context-health-monitor` — Scratch File Pressure Monitor

**Technique**: Measure scratch directory size and session log age, emit a diagnosis tag (`PRESSURE_SCRATCH`, `PRESSURE_OUTPUTS`, or `CONTEXT_HEALTHY`), then compact or archive based on the diagnosis. Runs until healthy or until `max_iterations` is reached.

**When to use**: During long automation runs (`ll-auto`, `ll-parallel`) where scratch files accumulate. Symptoms that warrant a run: scratch dir >500 KB, per-file summaries growing stale, or loop reasoning speed degrading due to context bloat.

**Required context variables**:

| Variable | Default | Description |
|----------|---------|-------------|
| `scratch_size_kb_warn` | `500` | Scratch dir size (KB) above which pressure is flagged |
| `log_age_days_warn` | `7` | Age in days above which output files are eligible for archiving |
| `scratch_dir` | `.loops/tmp` | Directory to monitor and compact |

**Invocation**:
```bash
# Run with defaults
ll-loop run context-health-monitor

# Lower threshold for aggressive compaction
ll-loop run context-health-monitor \
  --context scratch_size_kb_warn=200 \
  --context scratch_dir=/tmp/ll-scratch
```

**FSM flow**:
```
assess_context → self_assess → route
                                 ├─ CONTEXT_HEALTHY → done
                                 ├─ PRESSURE_SCRATCH → compact_scratch → verify → done
                                 └─ PRESSURE_OUTPUTS → archive_outputs → done
```

**Diagnosis tags**:
- `CONTEXT_HEALTHY` — No action needed; scratch dir is below threshold
- `PRESSURE_SCRATCH` — Scratch files are large; Claude compacts them by summarizing to essential findings
- `PRESSURE_OUTPUTS` — Output files are stale; archived to `{scratch_dir}/archive/`

**Notes**: `compact_scratch` summarizes large files in-place rather than deleting them — files referenced in active issues are preserved. Use `ll-loop install context-health-monitor` to add a pre-run hook that triggers it automatically before long sprints.

**Evaluation**

| Loop | Description |
|------|-------------|
| `outer-loop-eval` | Analyze a target loop by loading its YAML definition, executing it as a sub-loop, and producing a structured improvement report covering state coverage, missing routes, evaluator types, context variable hygiene, and cycle risks |

**Reinforcement Learning (RL)**

| Loop | Description |
|------|-------------|
| `agent-eval-improve` | Evaluate an AI agent on a task suite, score outputs, identify failure patterns, and iteratively refine agent config/prompts until quality target is reached. Exits `done` on convergence or no actionable patterns; exits `failed` when any state exhausts its `max_retries` |
| `rl-bandit` | Epsilon-greedy bandit loop — explore vs exploit rounds routing on reward convergence |
| `rl-coding-agent` | Policy+RLHF composite loop for agentic coding — outer policy loop adapts coding strategy while inner RLHF loop polishes each artifact to a quality threshold |
| `rl-policy` | Policy iteration loop — act, observe reward, improve policy toward a target |
| `rl-rlhf` | RLHF-style loop — generate candidate output, score quality, refine until target met |

### `agent-eval-improve` — Agent Quality Improvement Loop

**Technique**: Run an agent against a task suite, score pass/fail per task, identify failure patterns, and apply targeted config/prompt refinements — iterating until quality converges at the target threshold or no actionable patterns remain.

**When to use**: When an agent or prompt consistently fails on a subset of tasks and the failure mode is unclear. Useful for: refining tool-calling agents, tightening classification prompts, and diagnosing agents that succeed on simple cases but fail on edge cases.

**Required context variables**:

| Variable | Default | Description |
|----------|---------|-------------|
| `agent_config` | _(required)_ | Path to the agent config file to evaluate |
| `task_suite` | _(required)_ | Path to the task suite file or directory |
| `quality_threshold` | `0.85` | Target pass rate (0.0–1.0) to converge and exit |

**Invocation**:
```bash
# Basic evaluation loop
ll-loop run agent-eval-improve \
  --context agent_config=.loops/my-agent.yaml \
  --context task_suite=evals/tasks.json

# With a lower quality bar (early development)
ll-loop run agent-eval-improve \
  --context agent_config=.loops/my-agent.yaml \
  --context task_suite=evals/tasks.json \
  --context quality_threshold=0.70
```

**FSM flow**:
```
run_eval → score_results → analyze_failures
                               ├─ YES (patterns found) → route_quality
                               └─ NO (no actionable patterns) → done
                                        │
                             ┌──────────┴──────────┐
                         done (converged)    refine_config → run_eval
```

**Exit states**:
- `done` — Quality converged at or above `quality_threshold`, or no actionable failure patterns were found
- `failed` — Any state exhausted `max_retries` (2 retries). Check `captured.eval_results` via `ll-loop history agent-eval-improve` to diagnose

**Notes**: Each state has `max_retries: 2` with `on_retry_exhausted: failed`. Use `ll-loop install agent-eval-improve` to copy the YAML to `.loops/` and customize scoring logic or add domain-specific evaluation steps.

**Automatic Prompt Optimization (APO)**

| Loop | Description |
|------|-------------|
| `apo-beam` | Beam search prompt optimization — generate N variants, score all, advance the winner |
| `apo-contrastive` | Contrastive APO — generate N variants → score comparatively → select best → repeat |
| `apo-feedback-refinement` | Feedback-driven APO — generate → evaluate → refine until convergence |
| `apo-opro` | OPRO-style prompt optimization — history-guided proposal until convergence |
| `apo-textgrad` | TextGrad-style prompt optimization — test on examples, compute failure gradient, apply refinement |
| `examples-miner` | Co-evolutionary corpus mining — harvest completed issue sessions, quality-gate, calibrate difficulty band, synthesize adversarial examples; runs `apo-textgrad` as a child loop |
| `prompt-regression-test` | CI for prompts — run a prompt suite, score against baseline, flag regressions, and trigger APO repair when quality drops |

**Harness Examples**

| Loop | Description |
|------|-------------|
| `harness-single-shot` | Annotated single-shot harness example — all evaluation phases with commented-out optional gates |
| `harness-multi-item` | Annotated multi-item harness example — all five evaluation phases active over a discovered item list |
| `html-website-generator` | Generator-evaluator harness for single-page HTML website creation — accepts a one-line description and iteratively generates, screenshots, and refines HTML/CSS/JS via Playwright CLI |
| `svg-image-generator` | Generator-evaluator harness for SVG icon and illustration creation — accepts a one-line description and iteratively generates, screenshots, and refines a self-contained SVG via Playwright CLI |
| `svg-textgrad` | TextGrad-style SVG harness — optimizes the visual brief via structured gradient updates (FAILURE_PATTERN → ROOT_CAUSE → GRADIENT) rather than feeding raw critique to the generator; accumulates gradient history for repeated-failure escalation |

For background on the GAN-style generator-evaluator architecture used by `html-website-generator`, `svg-image-generator`, and `svg-textgrad`, see the [Harness Design for Long-Running Apps](../claude-code/harness-design-long-running-apps.md) reference.

### `html-website-generator` — GAN-Style Website Design Loop

> **Prerequisites**: [Playwright CLI](https://playwright.dev/) must be installed (`npm install -g playwright && npx playwright install chromium`, or `pip install playwright && playwright install chromium`).

**Technique**: Implements the generator-evaluator architecture described in Anthropic's [harness design article](../claude-code/harness-design-long-running-apps.md). The loop runs four states in sequence: a **planner** expands the one-line description into an opinionated design brief (color palette, layout, unique angle, anti-patterns to avoid); a **generator** writes a self-contained HTML/CSS/JS file; an **evaluator** uses Playwright CLI to screenshot the rendered page via `file://` URL (no HTTP server required); and a **scorer** judges the screenshot against four weighted criteria, routing back to the generator with structured critique until all scores clear `pass_threshold`.

**When to use**: When you want rapid, fully-automated iterations on a single-page design without setting up a build pipeline. The `file://` approach means the loop works offline with no server lifecycle to manage. For multi-page apps or server-side rendering, adapt the `evaluate` state to use a local HTTP server instead.

**Usage:**

```bash
ll-loop run html-website-generator "a landing page for a Dutch art museum"
```

**Context variables:**

| Variable | Default | Description |
|----------|---------|-------------|
| `description` | (from `loop_input`) | Natural language website description — passed as the positional argument |
| `output_dir` | `/tmp/ll-html-generator` | Output directory for `index.html`, `brief.md`, `critique.md`, and `screenshot.png` |
| `pass_threshold` | `6` | Minimum score per criterion (1–10); **all four** criteria must clear this value |

Override per-run:

```bash
ll-loop run html-website-generator "museum landing page" \
  --context output_dir=/tmp/my-site \
  --context pass_threshold=7
```

**FSM flow:**

```
plan → generate → evaluate
                     ├─ CAPTURED → score
                     │              ├─ PASS    → done
                     │              └─ ITERATE → generate (with critique)
                     └─ FAILED  → generate (Playwright unavailable — LLM-only scoring)
```

**Evaluation criteria** (all four must meet `pass_threshold`):

| Criterion | Weight | What it checks |
|-----------|--------|----------------|
| `design_quality` | 2× | Does the design feel like a coherent whole with a distinct mood and identity? |
| `originality` | 2× | Evidence of custom creative decisions? Penalizes purple gradients on white, unmodified stock components, AI-slop fill patterns. |
| `craft` | 1× | Typography hierarchy, spacing consistency, color harmony, contrast ratios |
| `functionality` | 1× | Can a user understand the site's purpose and complete the primary task within 5 seconds? |

**Notes:**
- The HTML file embeds all CSS and JavaScript inline so it renders correctly under a `file://` URL without a web server.
- If Playwright is unavailable (missing binary, permission error), the `evaluate` state's `on_no` route falls back to `generate`, which then proceeds to `score` using LLM-only judgment of the HTML source rather than a screenshot.
- The loop runs up to 30 iterations with a 4-hour timeout (`max_iterations: 30`, `timeout: 14400`).
- To customize the design criteria or scoring weights, install the loop locally (`ll-loop install html-website-generator`) and edit the `score` state's prompt.

### `svg-image-generator` — GAN-Style SVG Creation Loop

> **Prerequisites**: [Playwright CLI](https://playwright.dev/) must be installed (`npm install -g playwright && npx playwright install chromium`, or `pip install playwright && playwright install chromium`).

**Technique**: Direct port of the `html-website-generator` pattern adapted for SVG. The loop runs four states in sequence: a **planner** expands the one-line description into a visual brief (shape language, color palette, mood, anti-patterns to avoid); a **generator** writes a fully self-contained SVG file with a proper `viewBox` and no external dependencies; an **evaluator** uses Playwright CLI to screenshot the rendered SVG via `file://` URL (no HTTP server required — SVGs render natively in browsers); and a **scorer** judges the screenshot against four SVG-specific weighted criteria, routing back to the generator with structured critique until all scores clear `pass_threshold`.

**When to use**: When you want rapid, automated iterations on a custom icon or illustration without manual refinement. The self-contained SVG structure (no external fonts, no image hrefs) makes convergence faster than HTML — there are fewer variables and no layout engine complexity.

**Usage:**

```bash
ll-loop run svg-image-generator "a minimalist coffee cup icon"
```

**Context variables:**

| Variable | Default | Description |
|----------|---------|-------------|
| `description` | (from `loop_input`) | Natural language SVG description — passed as the positional argument |
| `output_dir` | `.loops/tmp/svg-image-generator` | Base directory; each run creates a timestamped subfolder (e.g. `.loops/tmp/svg-image-generator/20260413-143022/`) for `image.svg`, `brief.md`, `critique.md`, and `screenshot.png` |
| `pass_threshold` | `6` | Minimum score per criterion (1–10); **all four** criteria must clear this value |

Override per-run:

```bash
ll-loop run svg-image-generator "lightning bolt icon" \
  --context output_dir=/tmp/my-icon \
  --context pass_threshold=7
```

**FSM flow:**

```
init → plan → generate → evaluate
                            ├─ CAPTURED → score
                            │              ├─ PASS    → done
                            │              └─ ITERATE → generate (with critique)
                            └─ FAILED  → generate (Playwright unavailable — LLM-only scoring)
```

**Evaluation criteria** (all four must meet `pass_threshold`):

| Criterion | Weight | What it checks |
|-----------|--------|----------------|
| `visual_clarity` | 2× | Is the concept immediately readable at icon scale? Can you identify it within 2 seconds? |
| `originality` | 2× | Evidence of custom creative decisions? Penalizes default clip-art silhouettes and generic geometric shapes. |
| `craft` | 1× | Clean paths, consistent stroke weights, deliberate proportions, effective use of negative space |
| `scalability` | 1× | Does the level of detail hold up at small sizes (≤32px)? Penalizes excessive complexity. |

**Notes:**
- The SVG file embeds all shapes as paths and uses only inline colors — no external image hrefs, no external fonts — so it renders correctly under a `file://` URL without a web server.
- If Playwright is unavailable, the `evaluate` state's `on_no` route falls back to `generate`, which then proceeds to `score` using LLM-only judgment of the SVG source rather than a screenshot.
- The loop runs up to 20 iterations with a 2-hour timeout (`max_iterations: 20`, `timeout: 7200`).
- To customize the scoring criteria, install the loop locally (`ll-loop install svg-image-generator`) and edit the `score` state's prompt.

### `svg-textgrad` — TextGrad-Style SVG Optimization Loop

> **Prerequisites**: [Playwright CLI](https://playwright.dev/) must be installed (`npm install -g playwright && npx playwright install chromium`, or `pip install playwright && playwright install chromium`).

**Technique**: A TextGrad-style adaptation of `svg-image-generator`. Instead of feeding raw critique directly back to the generator, the loop treats the **visual brief** as the optimizable artifact. After each failed evaluation, a `compute_gradient` state analyzes `critique.md` against `brief.md` to produce a structured gradient — three labeled lines: `FAILURE_PATTERN`, `ROOT_CAUSE`, and `GRADIENT`. The gradient is appended to `gradients.md` (a running history), and `apply_gradient` rewrites `brief.md` to address the root cause. The generator then works from the improved brief rather than reconciling conflicting signals from brief + raw critique simultaneously.

**Gradient escalation**: `compute_gradient` reads the full `gradients.md` history. If the same `ROOT_CAUSE` appears two or more times, the loop escalates the gradient — demanding a stronger structural change to `brief.md` rather than a minor tweak. This prevents the loop from stalling on a persistent failure pattern. For example: where a first-time gradient might adjust a specific hex color, an escalated gradient for a repeated `ROOT_CAUSE` of "vague color palette" might demand rewriting the entire palette section with precise rationale for each choice.

**When to use**: When `svg-image-generator` converges to a local optimum — producing SVGs that are technically valid but aesthetically wrong in a repeatable way. The TextGrad approach is better at fixing systematic brief problems (vague color specs, missing scale constraints, contradictory requirements) because it optimizes the *specification* rather than reacting to each failure in isolation.

**Usage:**

```bash
ll-loop run svg-textgrad "a minimalist coffee cup icon"
```

**Context variables:**

| Variable | Default | Description |
|----------|---------|-------------|
| `description` | (from `loop_input`) | Natural language SVG description — passed as the positional argument |
| `output_dir` | `.loops/tmp/svg-textgrad` | Base directory; each run creates a timestamped subfolder (e.g. `.loops/tmp/svg-textgrad/20260413-143022/`) for `image.svg`, `brief.md`, `critique.md`, `gradients.md`, `scores.md`, `screenshot.png`, `best.svg`, and `best-brief.md` |
| `pass_threshold` | `6` | Minimum score per criterion (1–10); **weighted average** `(2×visual_clarity + 2×originality + craft + scalability) / 6` must meet or exceed this value |

Override per-run:

```bash
ll-loop run svg-textgrad "lightning bolt icon" \
  --context output_dir=/tmp/my-icon \
  --context pass_threshold=7
```

**FSM flow:**

```
init → plan → generate → evaluate
                            ├─ CAPTURED → score
                            │              ├─ PASS    → done
                            │              ├─ ITERATE → record_scores → compute_gradient → route_convergence
                            │              │                                                   ├─ CONVERGED → done
                            │              │                                                   └─ continue  → append_gradient → apply_gradient → generate
                            │              └─ ERROR   → failed
                            ├─ FAILED  → generate
                            └─ ERROR   → generate
```

**Evaluation criteria** (same four as `svg-image-generator`; weighted average must meet `pass_threshold`):

| Criterion | Weight | What it checks |
|-----------|--------|----------------|
| `visual_clarity` | 2× | Is the concept immediately readable at icon scale? Can you identify it within 2 seconds? |
| `originality` | 2× | Evidence of custom creative decisions? Penalizes default clip-art silhouettes and generic geometric shapes. |
| `craft` | 1× | Clean paths, consistent stroke weights, deliberate proportions, effective use of negative space |
| `scalability` | 1× | Does the level of detail hold up at small sizes (≤32px)? Penalizes excessive complexity. |

**Output files** (written to the timestamped run folder):

| File | Description |
|------|-------------|
| `image.svg` | The generated SVG (primary output) |
| `brief.md` | The final gradient-optimized visual brief |
| `critique.md` | The last evaluation scores and per-criterion notes |
| `gradients.md` | Full gradient history: one entry per iteration, with `FAILURE_PATTERN`, `ROOT_CAUSE`, and `GRADIENT` lines |
| `scores.md` | Per-iteration score history used by `compute_gradient` to detect plateaus and regressions |
| `screenshot.png` | The last Playwright-captured render |
| `best.svg` | Best-scoring iteration SVG (present if at least one score was recorded) |
| `best-brief.md` | Brief from the best-scoring iteration (present if at least one score was recorded) |
| `best.txt` | Weighted score of the best iteration (internal; used for comparison across iterations) |

**Notes:**
- Unlike `svg-image-generator`, the generator receives only `brief.md` and never sees `critique.md`. Critique is consumed exclusively by `compute_gradient`, which distills it into a structured gradient before the brief is updated — keeping the generator working from a coherent specification rather than reconciling conflicting signals.
- If Playwright is unavailable, the `evaluate` state's `on_no` route falls back to `generate` — no scoring occurs and the loop continues with the unchanged brief. Playwright is required to produce the screenshot that `score` reads; without it the loop re-generates rather than scoring without visual evidence.
- The loop runs up to 20 iterations with a 2-hour timeout (`max_iterations: 20`, `timeout: 7200`).
- To customize scoring criteria or gradient computation, install the loop locally (`ll-loop install svg-textgrad`) and edit the `score` or `compute_gradient` state's prompt.
- The generator enforces a strict 250-line SVG size limit — use `<circle>`, `<path>`, and `<text>` with `<g transform="">` for repeated elements rather than verbose repeated markup.
- Prefer `svg-image-generator` for quick iterations; reach for `svg-textgrad` when you see the same failure pattern repeating across iterations.

## Beyond the Basics

The sections below cover features you'll encounter as you move past simple loops: evaluators, variable interpolation, capture, routing, action types, retry and timing fields, handoff behavior, and scope-based concurrency. For full technical details — schema definitions, compiler internals, and advanced examples — see the [FSM Loop System Design](../generalized-fsm-loop.md).

### Evaluators

Evaluators interpret action output and produce a **verdict** string used for routing. Every state gets a default evaluator based on its action type.

| Evaluator | Verdicts | Default for | When to use |
|-----------|----------|-------------|-------------|
| `exit_code` | `yes` / `no` / `error` | shell commands | CLI tools that report pass/fail via exit code |
| `output_numeric` | `yes` / `no` / `error` | — | Compare parsed numeric output to a target |
| `output_json` | `yes` / `no` / `error` | — | Extract a JSON path value and compare |
| `output_contains` | `yes` / `no` | — | Regex or substring match on stdout |
| `convergence` | `target` / `progress` / `stall` | metric-tracking states | Track a metric toward a goal value |
| `diff_stall` | `yes` / `no` / `error` | — | Detect when consecutive iterations produce no git diff changes (see [Stall Detection](#stall-detection)) |
| `llm_structured` | `yes` / `no` / `blocked` / `partial` | slash commands | Natural-language judgment via LLM |
| `mcp_result` | `success` / `tool_error` / `not_found` / `timeout` | `mcp_tool` actions | Evaluate MCP server tool call results; see [MCP Tool Actions](#mcp-tool-actions) for verdict details |

Override the default by adding an `evaluate:` block to a state:

```yaml
evaluate:
  type: output_contains
  pattern: "All checks passed"
```

### Variable Interpolation

Use `${namespace.path}` in action strings, evaluator configs, and routing targets. Variables are resolved at runtime.

| Namespace | Description | Example |
|-----------|-------------|---------|
| `context` | User-defined variables from the `context:` block | `${context.src_dir}` |
| `captured` | Values stored by `capture:` in earlier states | `${captured.lint.output}` |
| `prev` | Previous state's result (output, exit_code) | `${prev.output}` |
| `result` | Current evaluation result | `${result.verdict}` |
| `state` | Current state metadata | `${state.name}`, `${state.iteration}` |
| `loop` | Loop-level metadata | `${loop.name}`, `${loop.elapsed}` |
| `env` | Environment variables | `${env.HOME}` |

Escape literal `${` with `$${`.

### Capture

Store a state's action output for use in later states:

```yaml
states:
  measure:
    action: "ruff check src/ 2>&1 | grep -c 'error' || echo 0"
    capture: lint_count
    next: apply
```

The captured value is accessible as `${captured.lint_count.output}`, `${captured.lint_count.stderr}`, `${captured.lint_count.exit_code}`, and `${captured.lint_count.duration_ms}`.

### Routing

States use **shorthand** (`on_yes`, `on_no`, `on_partial`, `on_blocked`, or any custom `on_<verdict>`) or a **route table** for verdict-to-state mapping:

```yaml
route:
  success: done
  failure: fix
  _: retry        # default for unmatched verdicts
  _error: error   # fallback for evaluation errors
```

Use `$current` as a target to retry the current state. Use `_` for a default route when no other verdict matches.

An additional shorthand, `on_blocked`, routes when the evaluator returns a `blocked` verdict (i.e., the action cannot proceed without external intervention):

```yaml
states:
  fix:
    action: "/ll:manage-issue bug fix"
    on_yes: "verify"
    on_no: "fix"
    on_blocked: "escalate"
```

`on_blocked` is resolved alongside `on_yes`/`on_no`/`on_error` in the shorthand lookup. It is equivalent to adding `blocked: "escalate"` to a full `route` table. If a `blocked` verdict is returned and no `on_blocked` target is defined, the loop terminates with a fatal routing error — define `on_blocked` on any state whose action can return a `blocked` verdict.

### Action Types

Each state's action is executed in one of four built-in modes, with an optional fifth mode for contributed types registered via the extension system:

| Type | Syntax hint | Default evaluator | Behavior |
|------|-------------|-------------------|----------|
| `shell` | No `/` prefix | `exit_code` | Run as shell command, capture stdout/stderr/exit code |
| `slash_command` | Starts with `/` | `llm_structured` | Execute a Claude Code slash command |
| `prompt` | Natural language | `llm_structured` | Send text to Claude as a prompt |
| `mcp_tool` | Must be set explicitly | `mcp_result` | Call an MCP server tool with structured params |
| *(contributed)* | Any custom string | Depends on runner | Dispatched via `FSMExecutor._contributed_actions` registry; registered by `ActionProviderExtension` plugins |

The engine auto-detects type: `/` prefix → `slash_command`, otherwise → `shell`. Set `action_type: prompt` explicitly for natural-language fix instructions.

#### Skills as Actions

Skills (invoked via `/ll:`) are auto-detected as `slash_command` actions. Their default evaluator is `llm_structured`, which uses an LLM to judge whether the skill's output meets the expected quality criteria.

For deterministic routing — when the skill supports `--check` — override the evaluator to `exit_code` so the FSM routes on pass/fail without an LLM call:

```yaml
check-format:
  action: "/ll:format-issue --all --check"
  action_type: slash_command
  evaluate:
    type: exit_code
  on_yes: next-step
  on_no: fix-format
```

To compose multiple skill calls in a single state (e.g., run format then verify in sequence), use `action_type: prompt`:

```yaml
refine-and-score:
  action: "Run /ll:refine-issue on ${captured.current_item.output}, then run /ll:format-issue --check on the same file."
  action_type: prompt
  next: advance
```

See [Pattern: Using `--check` with Exit Code Evaluators](#pattern-using---check-with-exit-code-evaluators) for a worked multi-skill loop example.

#### MCP Tool Actions

MCP tool actions call a registered MCP server tool directly from a loop state. Unlike shell and slash commands, the type is **not** auto-detected — you must set `action_type: mcp_tool` explicitly.

```yaml
get-issue-details:
  action: "github/get_issue"
  action_type: mcp_tool
  params:
    owner: "${context.repo_owner}"
    repo: "${context.repo_name}"
    issue_number: "${captured.current_item.output}"
  capture: issue_data
  next: process-issue
```

Key fields:
- `action`: `"server_name/tool_name"` — must match a tool registered in `.mcp.json`
- `params`: JSON object passed to the tool; supports `${variable}` interpolation
- `capture`: optional — stores the tool's response for use in later states

The default evaluator for `mcp_tool` states is `mcp_result` (no need to specify it). Verdict table:

| Verdict | Meaning | Exit code analogue |
|---------|---------|-------------------|
| `success` | Tool returned a result | 0 |
| `tool_error` | Tool ran but returned an error response | 1 |
| `not_found` | Server or tool not registered in `.mcp.json` | 127 |
| `timeout` | Transport-level timeout (default 30 s) | 124 |

Route on these verdicts using a route table:

```yaml
get-issue-details:
  action: "github/get_issue"
  action_type: mcp_tool
  params:
    owner: "${context.repo_owner}"
    repo: "${context.repo_name}"
    issue_number: "${captured.current_item.output}"
  capture: issue_data
  route:
    success: process-issue
    tool_error: log-error
    not_found: abort
    timeout: retry-fetch
```

MCP tools also appear as `check_mcp` evaluation gates in harness loops — a deterministic external-state check that runs before the more expensive LLM phases. See [Automatic Harnessing Guide](AUTOMATIC_HARNESSING_GUIDE.md) for details.

### Retry and Timing Fields

These optional fields can be added to any state:

| Field | Type | Description |
|-------|------|-------------|
| `backoff:` | number (seconds) | Delay before executing this state's action. Useful for rate-limited APIs or CI systems. Overridden at runtime by `--delay <SECONDS>`. |
| `max_retries:` | integer | Maximum number of times the engine re-enters this state before triggering `on_retry_exhausted`. |
| `on_retry_exhausted:` | state name | Target state when `max_retries` is reached. Common pattern in harness loops: `on_retry_exhausted: advance` to skip a stuck item and continue processing. |
| `max_rate_limit_retries:` | integer | Max consecutive 429/rate-limit retries in the **short-burst tier** before advancing to the long-wait tier. Requires `on_rate_limit_exhausted`. |
| `on_rate_limit_exhausted:` | state name | Target state routed to when the total wall-clock rate-limit budget (`rate_limit_max_wait_seconds`) is spent. Required when `max_rate_limit_retries` is set. |
| `rate_limit_backoff_base_seconds:` | integer | Base seconds for exponential backoff in the short-burst tier; actual sleep = base * 2^(attempt-1) + uniform(0, base). Defaults to 30. |
| `rate_limit_max_wait_seconds:` | integer | Total wall-clock budget (seconds) across both tiers before routing to `on_rate_limit_exhausted`. Defaults to 21600 (6h). Overrides global `commands.rate_limits.max_wait_seconds`. |
| `rate_limit_long_wait_ladder:` | list of integers | Long-wait tier ladder (seconds), walked once the short-burst tier is spent. Defaults to `[300, 900, 1800, 3600]`. Index caps at the last entry. Overrides global `commands.rate_limits.long_wait_ladder`. |

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

These optional fields apply to `action_type: prompt` states only. They are ignored for `action_type: shell` states.

| Field | Type | Description |
|-------|------|-------------|
| `agent:` | string | Passes `--agent <name>` to the Claude subprocess. Loads `.claude/agents/<name>.md`, picking up its system prompt and tool set. |
| `tools:` | list of strings | Passes `--tools <csv>` to the Claude subprocess. Explicitly scopes available tools without needing a full agent file (e.g. `["Read", "Bash"]`). |

Example — run a state under a specialized agent, and another with restricted tools:

```yaml
explore:
  action: |
    Run the exploratory eval as defined in the agent file.
  action_type: prompt
  agent: exploratory-user-eval    # loads --agent flag → picks up Playwright tools
  next: validate

validate:
  action: |
    Check the output file for correctness.
  action_type: prompt
  tools: ["Read", "Bash"]          # scopes to Read + Bash only
  on_yes: done
  on_no: fix
```

### Handoff Behavior

When a loop detects that Claude's context window is approaching its limit, it triggers a **handoff**:

| Mode | `on_handoff:` value | Behavior |
|------|---------------------|----------|
| Pause | `pause` (default) | Save state to disk, resume later with `ll-loop resume` |
| Spawn | `spawn` | Save state and launch a fresh Claude session to continue |
| Terminate | `terminate` | Stop the loop immediately (state is not saved) |

Set `on_handoff` at the **loop level** (not per state):

```yaml
name: issue-refinement
on_handoff: spawn        # loop-level field
max_iterations: 20
states:
  discover:
    action: "ll-issues list --status active"
    capture: active_issues
    next: refine
  refine:
    action: "/ll:refine-issue ${captured.active_issues.output}"
    action_type: slash_command
    next: discover
  done:
    terminal: true
```

**Choosing a mode:**

- **`spawn`** — best for long-running automated loops that should continue without human intervention: issue processing pipelines, APO loops, sprint workflows. A fresh session picks up exactly where the previous one left off.
- **`pause`** (default) — best for metric-tracking or monitoring loops where reviewing state between sessions is desirable: RL loops, worktree health checks. Requires manual `ll-loop resume <name>` to continue.
- **`terminate`** — use when partial execution is worse than none. For example, if the loop rewrites a file atomically and a partial run would leave it in a corrupt intermediate state.

**What is preserved** across a pause or spawn handoff:

- Current state name and iteration count
- All `captured` variable values from completed states
- Loop-level `context` variables

On resume (manual or automatic), the engine re-enters the state where the handoff occurred and re-runs its action with full variable context restored.

For interactive session handoff details see [Session Handoff](SESSION_HANDOFF.md).

### Per-Loop Config Overrides

Loop YAML files support an optional top-level `config:` block that embeds per-loop overrides for `ll-config` values. When `ll-loop run <loop-name>` is invoked, the `config:` block overrides the global `ll-config.json` for the session.

```yaml
name: exploratory-refactor
initial: analyze
on_handoff: spawn
config:
  handoff_threshold: 60            # overrides LL_HANDOFF_THRESHOLD
  commands:
    confidence_gate:
      readiness_threshold: 70
      outcome_threshold: 55
  automation:
    max_continuations: 5

states:
  analyze:
    # ...
```

**Precedence** (highest to lowest):
1. CLI flags (`--handoff-threshold`)
2. Loop YAML `config:` block
3. Global `ll-config.json`
4. Schema defaults

**Supported override keys:**

| Key | Description |
|-----|-------------|
| `handoff_threshold` | Override auto-handoff context threshold (1-100) |
| `commands.confidence_gate.readiness_threshold` | Override readiness gate threshold (1-100) |
| `commands.confidence_gate.outcome_threshold` | Override outcome confidence threshold (1-100) |
| `automation.max_continuations` | Override max continuation count (≥1) |
| `continuation.max_continuations` | Alias for `automation.max_continuations` — either key is accepted |

Config overrides apply equally to `ll-loop run` and `ll-loop resume`. CLI flags always take highest precedence and override both the YAML config block and global settings.

Use `ll-loop show <loop-name>` to verify which overrides are active — the header line displays any non-default config values.

### Scope-Based Concurrency

The `scope:` field declares which paths a loop operates on. The engine uses file-based locking to prevent two loops from modifying the same files simultaneously.

```yaml
scope:
  - "src/"
  - "tests/"
```

If a conflicting loop is already running, `ll-loop run` will error. Use `--queue` to wait for the conflict to resolve instead.

## Prompt Optimization Loops (APO)

> **Advanced** — APO loops tune prompts automatically. Most users won't need these.
> Start with standard loops and return here when you have a specific prompt quality problem.

Automatic Prompt Optimization (APO) loops apply iterative improvement techniques to refine prompts using LLM-driven evaluation. They are a practical alternative to manual prompt engineering: instead of tweaking prompts by hand, you describe your criteria and let the loop drive convergence.

Seven built-in APO loops ship with little-loops:

---

### `apo-feedback-refinement` — Feedback-Driven Refinement

**Technique**: Generate one improved candidate → evaluate against criteria → apply feedback → repeat until convergence.

**When to use**: You have a single target prompt and a clear quality rubric. Good for system prompts that produce inconsistent outputs — the evaluator diagnoses what's wrong and the refinement step fixes it.

**Required context variables**:

| Variable | Default | Description |
|----------|---------|-------------|
| `prompt_file` | `system.md` | Path to the prompt file to improve |
| `eval_criteria` | `"clarity, specificity, and effectiveness"` | Criteria the evaluator uses to score candidates |
| `quality_threshold` | `85` | Score (0–100) at which the loop considers the prompt converged |

**Invocation**:

```bash
# Run with defaults (improves system.md in the current directory)
ll-loop apo-feedback-refinement

# Override context variables
ll-loop apo-feedback-refinement \
  --context prompt_file=prompts/classifier.md \
  --context eval_criteria="accuracy and conciseness" \
  --context quality_threshold=90

# Load explicitly from built-ins (bypasses project .loops/)
ll-loop run --builtin apo-feedback-refinement --context prompt_file=system.md
```

**FSM flow**:
```
generate_candidate ──→ evaluate_candidate ──→ route_convergence
                                               ├─ CONVERGED ──→ apply_candidate ──→ done
                                               └─ NEEDS_REFINE ──→ refine ──→ generate_candidate
```

---

### `apo-contrastive` — Contrastive Optimization

**Technique**: Generate N diverse variants → score comparatively → select the best → update the file → repeat until convergence.

**When to use**: You want broader exploration of the prompt space per iteration. Each round explores N distinct directions and keeps the winner, so the loop avoids local optima that single-candidate refinement can get stuck in.

**Required context variables**:

| Variable | Default | Description |
|----------|---------|-------------|
| `prompt_file` | `system.md` | Path to the prompt file to improve |
| `eval_criteria` | `"clarity, specificity, and effectiveness"` | Criteria used to score each variant |
| `num_variants` | `3` | Number of distinct variants to generate per iteration |
| `quality_threshold` | `90` | Score (0–100) at which the loop considers the prompt converged |

**Invocation**:

```bash
# Run with defaults
ll-loop apo-contrastive

# Tune for deeper search
ll-loop apo-contrastive \
  --context prompt_file=prompts/system.md \
  --context num_variants=5 \
  --context quality_threshold=95
```

**FSM flow**:
```
generate_variants ──→ score_and_select ──→ route_convergence
                                           ├─ CONVERGED ──→ done
                                           └─ CONTINUE ──→ generate_variants
```

---

### `apo-opro` — OPRO-Style History-Guided Optimization

**Technique**: Maintain a running history of scored candidates → propose a new candidate informed by past successes and failures → evaluate and score it → append to history → repeat until convergence. Inspired by the OPRO (Optimization by PROmpting) approach: the accumulated score history acts as in-context gradient information, steering each new proposal away from previously observed weaknesses.

**When to use**: You want the optimizer to learn from its own history across iterations. Each proposal is explicitly conditioned on what was tried before and how it scored, so the loop avoids re-proposing variants with known weaknesses. This makes it better than `apo-feedback-refinement` (single candidate, no memory) for runs where early proposals reveal recurring failure patterns that need to be systematically avoided.

**Required context variables**:

| Variable | Default | Description |
|----------|---------|-------------|
| `prompt_file` | `system.md` | Path to the prompt file to improve |
| `eval_criteria` | `"clarity, specificity, and effectiveness"` | Criteria the evaluator uses to score candidates |
| `target_score` | `90` | Score (0–100) at which the loop considers the prompt converged |

**Invocation**:

```bash
# Run with defaults (improves system.md in the current directory)
ll-loop apo-opro

# Customize prompt file and criteria
ll-loop apo-opro \
  --context prompt_file=prompts/classifier.md \
  --context eval_criteria="accuracy and conciseness" \
  --context target_score=85

# Install to project for customization
ll-loop install apo-opro
```

**FSM flow**:
```
init_history ──→ propose_candidate ──→ evaluate_candidate ──→ update_history ──→ route_convergence
                       ↑                                                                  │
                       └────────────────────── CONTINUE ───────────────────────────────────┘
                                                                                           │
                                                                          CONVERGED ──→ done
```

---

### `apo-beam` — Beam Search Optimization

**Technique**: Generate N variants in parallel → score all → advance the highest-scoring winner → repeat until convergence.

**When to use**: You have already tried linear refinement (`apo-feedback-refinement` or `apo-contrastive`) and hit a plateau. Beam search explores `beam_width` directions simultaneously each iteration rather than following a single candidate forward. This makes it less likely to stay trapped in a local optimum and more likely to find a qualitatively different high-scoring prompt region.

**Required context variables**:

| Variable | Default | Description |
|----------|---------|-------------|
| `prompt_file` | `system.md` | Path to the prompt file to improve |
| `eval_criteria` | `"clarity, specificity, and effectiveness"` | Criteria used to score each variant |
| `beam_width` | `4` | Number of distinct variants generated per iteration |
| `target_score` | `90` | Score (0–100) at which the loop emits `CONVERGED` and terminates |

**Invocation**:

```bash
# Run with defaults (beam_width=4)
ll-loop apo-beam

# Wider beam for higher-stakes optimization
ll-loop apo-beam \
  --context prompt_file=prompts/triage.md \
  --context eval_criteria="correctly triage support tickets by severity" \
  --context beam_width=6 \
  --context target_score=88

# Install to project for customization
ll-loop install apo-beam
```

**FSM flow**:
```
generate_variants ──→ score_variants ──→ select_best ──→ route_convergence
                                                          ├─ CONVERGED ──→ done
                                                          └─ CONTINUE ──→ generate_variants
```

---

### `apo-textgrad` — TextGrad (Example-Driven Gradient Descent)

**Technique**: Test the current prompt against a batch of input/output example pairs → compute a structured "text gradient" (failure pattern, root cause, and fix instruction) → apply the gradient to the prompt → repeat until the pass rate reaches the target.

**When to use**: You have a prompt and a concrete set of input/output examples where the prompt fails on a predictable subset. This is the most targeted APO strategy: failures on specific examples produce specific signals, driving faster convergence than holistic feedback for prompts with clear success criteria (classification, extraction, structured generation).

**Required context variables**:

| Variable | Default | Description |
|----------|---------|-------------|
| `prompt_file` | `system.md` | Path to the prompt file to improve |
| `examples_file` | `examples.json` | Path to a JSON array of `{"input": ..., "expected": ...}` pairs |
| `target_pass_rate` | `90` | Pass rate (0–100) at which the loop considers the prompt converged |

**`examples_file` format**:

```json
[
  { "input": "Support ticket text...", "expected": "HIGH" },
  { "input": "Another ticket...", "expected": "LOW" }
]
```

Each object must have an `input` field (the text to pass to the prompt) and an `expected` field (the correct output). Arrays of 10–20 examples are typical; larger sets increase signal quality at the cost of more LLM calls per iteration.

**Invocation**:

```bash
# Run with defaults (system.md + examples.json in current directory)
ll-loop apo-textgrad

# Point at specific prompt and examples files
ll-loop apo-textgrad \
  --context prompt_file=prompts/extractor.md \
  --context examples_file=tests/extraction-examples.json \
  --context target_pass_rate=95

# Install to project for customization
ll-loop install apo-textgrad
```

**FSM flow**:
```
test_on_examples ──→ compute_gradient ──→ route_convergence
                                          ├─ CONVERGED ──→ done
                                          └─ CONTINUE ──→ apply_gradient ──→ test_on_examples
```

---

### `examples-miner` — Co-evolutionary Corpus Mining

**Technique**: Harvest skill invocations from completed issue session logs → quality-gate via a three-layer judge (code persistence, revision distance, oracle scoring) → calibrate to the 40–80% difficulty band → run `apo-textgrad` as a child loop to obtain a gradient signal → synthesize adversarial examples targeting the failure pattern → enforce diversity → publish a fresh `examples.json`.

**When to use**: After `apo-textgrad` has plateaued on hand-crafted examples, or after skill conventions have evolved and the static corpus is stale. The miner automatically harvests the project's own completed issues (800+ issues = implicit human approvals) and synthesizes adversarial examples from the current gradient's failure pattern.

**Required context variables**:

| Variable | Default | Description |
|----------|---------|-------------|
| `examples_file` | `examples.json` | Path where the fresh corpus is published |
| `prompt_file` | `system.md` | Prompt file passed to the inner apo-textgrad loop |
| `skill_name` | `capture-issue` | Skill to mine (e.g., `capture-issue`, `refine-issue`) |
| `corpus_state_file` | `corpus.json` | Optional: persisted calibration state for freshness decay |
| `target_pass_rate` | `0.6` | Center of the 40–80% difficulty band (fraction, 0–1) |

**Invocation**:

```bash
# Run with defaults (mines capture-issue sessions, publishes to examples.json)
ll-loop run examples-miner

# Mine a different skill with a custom examples file
ll-loop run examples-miner \
  --context skill_name=refine-issue \
  --context examples_file=tests/refine-examples.json \
  --context prompt_file=skills/refine-issue/SKILL.md

# Install to project for customization (hardcode oracle path for v2 sub-loop promotion)
ll-loop install examples-miner
```

**FSM flow**:
```
harvest ──→ judge ──→ calibrate ──→ write_examples ──→ run_optimizer (sub-loop: apo-textgrad)
                                                         ├─ SUCCESS ──→ synthesize ──→ screen_adversarial ──→ score_adversarial ──→ merge ──→ diversify ──→ publish ──→ done
                                                         └─ FAILURE ──→ diversify ──→ publish ──→ done
```

**Three-layer quality judge**:

| Layer | Mechanism | What it checks |
|-------|-----------|----------------|
| 1. Code persistence | `git log --follow` via Bash | `files_modified` still present in HEAD; persistence age (commit count without revert) |
| 2. Revision distance | Session log entry count | Low session count → output accepted quickly (low distance); many refinement sessions → high distance |
| 3. Oracle rubric | Inline LLM scoring | Tool selection quality, file path relevance, completion status (0–100 pts per candidate) |

Only candidates that survive all three layers and fall in the 40–80% pass-rate band enter the active calibrated set.

**Adversarial synthesis perturbation taxonomy** (gradient `FAILURE_PATTERN` selects type):

| Type | What it does |
|------|-------------|
| `complexity_injection` | Adds a second symptom that may or may not belong in the same issue — tests scope boundary judgment |
| `ambiguity_injection` | Strips specific file/function names, forcing discovery rather than copying references |
| `domain_shift` | Reproduces the same failure pattern in a different subsystem — tests generalization |
| `priority_boundary` | Edge case sitting between two adjacent priority levels |
| `type_confusion` | Description that looks like FEAT but is BUG (or vice versa) |

**Adversarial cap**: `source: adversarial` examples are capped at ≤ 30% of the final corpus at all times.

**Sentinel-based incremental harvest**: The `publish` state writes `corpus.last_harvested` with the current UTC timestamp. On the next run, `harvest` passes `--since <timestamp>` to `ll-messages` so only new sessions are re-processed. On the first run the sentinel file is absent and all sessions are harvested.

**Pairing with apo-textgrad** (recommended workflow):

```bash
# Step 1: Build a fresh corpus from project history
ll-loop run examples-miner --context skill_name=capture-issue

# Step 2: Run apo-textgrad against the mined corpus
ll-loop run apo-textgrad \
  --context prompt_file=skills/capture-issue/SKILL.md \
  --context examples_file=examples.json

# Or: run examples-miner once — it calls apo-textgrad internally as run_optimizer
ll-loop run examples-miner \
  --context skill_name=capture-issue \
  --context prompt_file=skills/capture-issue/SKILL.md
```

**Oracle sub-loop (v2)**: The `scripts/little_loops/loops/oracles/oracle-capture-issue.yaml` file provides a two-phase oracle (mechanical checks + semantic LLM scoring) that can be promoted to a sub-loop in a customized `examples-miner.yaml` via `loop: oracles/oracle-capture-issue` + `context_passthrough: true` on the `judge` state. The built-in `examples-miner.yaml` uses inline oracle scoring (v1 approach) — install and customize to enable sub-loop promotion.

---

### `prompt-regression-test` — Prompt CI / Regression Detection

**Technique**: Run a prompt suite against an LLM endpoint, score outputs against expected results, compare scores to a stored baseline, flag regressions, and optionally trigger an `apo-textgrad` sub-loop to repair the regressed prompt before updating the baseline.

**When to use**: Continuous integration for prompts — detect quality regressions when you change the model, system configuration, or surrounding code that a prompt depends on. Unlike other APO loops that optimize a prompt toward a target, `prompt-regression-test` defends a known-good baseline and only triggers optimization when a regression is detected.

**Required context variables**:

| Variable | Default | Description |
|----------|---------|-------------|
| `prompt_suite` | `prompts/` | Directory containing prompt files to test |
| `baseline_file` | `.loops/tmp/prompt-baseline.json` | Stored baseline scores (created on first run) |
| `pass_threshold` | `90` | Pass rate (0–100) at which the loop considers the suite healthy |

**Invocation**:

```bash
# Run with defaults (tests all prompts in prompts/ directory)
ll-loop run prompt-regression-test

# Point at a specific prompt directory and threshold
ll-loop run prompt-regression-test \
  --context prompt_suite=tests/prompts/ \
  --context pass_threshold=85

# Install to project for customization
ll-loop install prompt-regression-test
```

**FSM flow**:
```
run_suite ──→ score_outputs ──→ compare_baseline ──→ route_regression
                                                       ├─ NO_REGRESSION ──→ report ──→ done
                                                       └─ REGRESSION ──→ trigger_apo (sub-loop: apo-textgrad)
                                                                              ├─ SUCCESS ──→ update_baseline ──→ done
                                                                              └─ FAILURE/ERROR ──→ report ──→ done
```

**First run baseline**: On the first run `baseline_file` does not exist — the loop creates it from the initial suite results and exits with a clean report. Subsequent runs compare against this stored baseline. To reset: delete `baseline_file` before the next run.

**Pairing with `examples-miner`** (recommended workflow for persistent regressions):

```bash
# Step 1: Mine a fresh example corpus for the regressed prompt
ll-loop run examples-miner --context skill_name=my-prompt

# Step 2: Run regression test — triggers apo-textgrad automatically on failure
ll-loop run prompt-regression-test \
  --context prompt_suite=prompts/ \
  --context pass_threshold=90
```

---

### Choosing Between APO Loops

| Trigger | Recommended loop |
|---------|-----------------|
| Output quality varies run-to-run | `apo-feedback-refinement` |
| Need to compare two prompt versions | `apo-contrastive` |
| Optimizing a prompt against a fixed metric | `apo-opro` |
| Want to explore multiple prompt candidates | `apo-beam` |
| Have gradient-like feedback signals | `apo-textgrad` |
| Building a training example corpus | `examples-miner` |
| Prompt quality has regressed vs. baseline | `prompt-regression-test` |

| | `apo-feedback-refinement` | `apo-contrastive` | `apo-opro` | `apo-beam` | `apo-textgrad` | `prompt-regression-test` |
|---|---|---|---|---|---|---|
| Exploration per iteration | Low (single candidate) | Medium (N candidates, comparative) | Low (history-guided single candidate) | High (N parallel candidates, independent) | Low (single targeted refinement) | Low (one repair pass via apo-textgrad) |
| Convergence speed | Fastest when feedback is precise | Moderate | Moderate | Slowest (most LLM calls) | Fast when examples have clear correct answers | Fast when regression has concrete failing examples |
| Local optima risk | High | Moderate | Moderate | Low | Low (example failures provide precise signal) | Low (triggered only by concrete regressions) |
| Best for | Targeted improvement with clear criteria | Broad style exploration | Long runs where history improves proposals | Escaping plateaus, high-variance search spaces | Prompts with measurable pass/fail examples (classification, extraction) | CI integration; defending a known-good quality baseline |

### Tips for APO Loops

- **Start with a concrete `eval_criteria`**: vague criteria produce vague scores. Instead of `"good"`, try `"responds only with valid JSON, handles edge cases, and explains its reasoning"`.
- **Set `quality_threshold` conservatively**: start at 80 and raise once the loop reaches it. Overly strict thresholds burn iterations without improvement.
- **Check the prompt file after each run**: the loop writes back to the file in-place. Use `git diff` to review the evolution across iterations.
- **Install to customize**: run `ll-loop install apo-feedback-refinement` to copy the YAML to `.loops/` and edit state actions or add custom evaluation logic.

## Evaluation Loops

Loops in this category analyze other loops — auditing their YAML definitions, running them as sub-loops, and producing structured improvement reports.

### `outer-loop-eval` — Loop Structure & Execution Auditor

**Technique**: Load a target loop's YAML definition, execute it as a sub-loop against an optional input, then combine a static definition analysis with a live execution trace to produce a structured improvement report covering five dimensions: Structural Issues, Logic Issues, Flow Issues, Component Improvements, and Suggested YAML Changes.

**When to use**: After writing or significantly modifying a loop — or before sharing it. `outer-loop-eval` catches missing `on_error` routes, cycle risks, uninitialized context variables, evaluator type mismatches, and redundant state hops that manual review often misses.

**Required context variables**:

| Variable | Default | Description |
|----------|---------|-------------|
| `loop_name` | _(required)_ | Target loop name — built-in (`outer-loop-eval`) or project-level (`.loops/my-loop`) |
| `input` | `""` | Optional input value passed to the sub-loop when it runs |

**Invocation**:

```bash
# Audit a built-in loop
ll-loop run outer-loop-eval --context loop_name=issue-refinement

# Audit a project-level loop with an input
ll-loop run outer-loop-eval \
  --context loop_name=my-custom-loop \
  --context input="some context value"

# JSON shorthand: pass both context variables as a single JSON object (auto-unpacked into context)
ll-loop run outer-loop-eval '{"loop_name": "my-custom-loop", "input": "some context value"}'

# Install to project for customization
ll-loop install outer-loop-eval
```

**FSM flow**:
```
validate_input ──(on_error)──→ done
     │
     ↓
analyze_definition → run_sub_loop → analyze_execution → generate_report
                                                             ├─ YES (has findings) → done
                                                             └─ NO (all "None identified.") → refine_analysis → generate_report
```

**Execution failure handling**: If `loop_name` is empty, `validate_input` exits immediately with a clear error message before any analysis begins — preventing hallucinated reports. If the target loop is found but fails to start (not found after validation, crashes on launch), `outer-loop-eval` captures the error output and feeds it to `analyze_execution` as-is. The final report will still include structural findings derived from the definition analysis — making the audit useful even when the sub-loop cannot run.

**Report sections**: The improvement report always includes these exact headings:
- **Structural Issues** — unreachable states, undefined routes, orphaned states
- **Logic Issues** — incorrect evaluator types, wrong routing, context variable misuse
- **Flow Issues** — redundant hops, timeout risks, missing `on_error` routes
- **Component Improvements** — state-level suggestions: better prompts, tighter evaluators, clearer capture keys
- **Suggested YAML Changes** — concrete diff-style or annotated edits ready to copy into the YAML file

---

## Harness Loops

> **Advanced** — See [AUTOMATIC_HARNESSING_GUIDE.md](AUTOMATIC_HARNESSING_GUIDE.md) for the
> full harness guide. This section is a brief overview.

A **harness loop** is a pre-structured FSM pattern that wraps a skill or prompt in a layered quality evaluation pipeline, then repeats over a list of work items — or runs once in single-shot mode. The `/ll:create-loop` wizard auto-derives the evaluation framework from your project config so you don't write it by hand.

The core idea: running a skill is easy; knowing the output is actually good is hard. A harness solves this by passing each result through up to five evaluation phases before advancing.

### The Evaluation Pipeline

Each harness applies phases in sequence, cheapest first:

| Phase | What it checks | Evaluator | Approx. latency |
|-------|----------------|-----------|-----------------|
| `check_concrete` | Exit code from test/lint/type command — objective, fast | `exit_code` | < 1s |
| `check_mcp` | MCP server tool call — deterministic external state | `mcp_result` | ~500ms |
| `check_skill` | Full agentic user simulation — did it work as a real user would? | `llm_structured` | 30–300s |
| `check_semantic` | LLM judges output quality — semantic correctness | `llm_structured` | 3–10s |
| `check_invariants` | Diff line count — catches runaway changes | `output_numeric` | < 1s |

All phases are optional; the wizard pre-selects based on your project config and what tools are registered. Running cheapest first means expensive LLM calls only happen when objective gates already pass.

### Creating a Harness

Run `/ll:create-loop` and select **"Harness a skill or prompt"**. The 4-step wizard asks:

1. **Target** — pick a discovered skill or enter a custom prompt (plus a "done looks like" criterion for the LLM judge)
2. **Work items** — single-shot, active issues list, file glob, or manual list
3. **Evaluation phases** — which of the five phases to include (pre-selected from config)
4. **Iteration budget** — retries per item and total `max_iterations`

### FSM Structure

**Single-shot** (no discovery): starts directly at `execute`, runs the evaluation chain once, reaches `done`.

**Multi-item** (issues list / glob / manual): adds `discover` and `advance` states around the evaluation chain:

```
discover ──→ execute ──→ check_concrete ──→ check_semantic ──→ check_invariants ──→ advance ──→ discover
               ↑              │ on_no              │ on_no              │ on_no
               └──────────────┴────────────────────┘
no items remaining ──→ done
```

_(simplified — omits optional `check_mcp` and `check_skill` phases)_

The critical safeguard in multi-item loops is `max_retries` + `on_retry_exhausted: advance` on the `execute` state — without it, one item that never passes evaluation consumes the entire `max_iterations` budget:

```yaml
execute:
  action: /ll:refine-issue ${captured.current_item.output} --auto
  action_type: prompt
  max_retries: 3
  on_retry_exhausted: advance
  next: check_concrete
```

A parallel safeguard exists for HTTP 429 rate-limit failures and is structured as a **two-tier retry ladder**:

1. **Short-burst tier** — up to `max_rate_limit_retries` in-place retries with exponential backoff + jitter (`rate_limit_backoff_base_seconds * 2^n + uniform(0, base)`, default base `30`). Handles transient 429s from brief quota dips.
2. **Long-wait tier** — once the short-burst tier is spent, the executor walks `rate_limit_long_wait_ladder` (default `[300, 900, 1800, 3600]` — 5 min → 15 min → 30 min → 1 h). Each 429 advances the ladder index, capped at the last entry.

The FSM only routes to `on_rate_limit_exhausted` once `total_wait_seconds >= rate_limit_max_wait_seconds` (default 21600 = 6h). This is designed to ride out multi-hour upstream outages without giving up prematurely:

```yaml
execute:
  action: /ll:refine-issue ${captured.current_item.output} --auto
  action_type: prompt
  max_rate_limit_retries: 3           # short-burst budget
  rate_limit_backoff_base_seconds: 30
  rate_limit_long_wait_ladder: [300, 900, 1800, 3600]
  rate_limit_max_wait_seconds: 21600  # total budget (short + long)
  on_rate_limit_exhausted: parked
  next: check_concrete
```

Shutdown requests (`SIGTERM`) are observed promptly during long-wait sleeps — the executor checks the shutdown flag every 100 ms. Resume across process restarts is durable: the per-state record (`short_retries`, `long_retries`, `total_wait_seconds`, `first_seen_at`) and the storm counter are persisted in `LoopState`.

> **Thundering-herd note for `ll-parallel`:** when many worktrees hit the same shared 429 at once, a fixed backoff would re-stampede the upstream service on the same tick. The added jitter is load-bearing — don't override it away, and prefer a larger `rate_limit_backoff_base_seconds` over a smaller one when you know you're running wide parallelism.

#### Cross-worktree circuit breaker

Layered on top of the two-tier retry ladder is a shared **circuit breaker** that lets concurrent `ll-parallel` workers skip redundant LLM calls when one of their peers has already observed a 429. It is intentionally coarse-grained — a single recovery timestamp, shared via a file on disk — so its correctness does not depend on any message bus or coordinator process.

- **Pre-action check (prompt-mode only).** Before each `execute` step, the FSM consults the shared circuit state. If a recovery timestamp is in the future, the executor pre-sleeps until `estimated_recovery_at` instead of issuing an API call that would almost certainly 429. This gating applies **only** to `action_type: prompt` (Claude SDK LLM calls). Shell-based `action_type: slash_command` actions are not gated and run unthrottled, since they don't consume the rate-limited upstream quota.
- **Cross-worktree coordination.** When any worker receives a 429, it writes a sidecar record to `.loops/tmp/rate-limit-circuit.json` (path configurable). Every other worker reads that file at the start of its next `execute` and honors the open circuit — a single 429 observation suppresses a wave of doomed calls from sibling worktrees.
- **Stale auto-ignore.** Circuit-breaker entries older than 1 hour are silently ignored on read, so a process that crashes mid-retry cannot wedge peers indefinitely. No manual reset is required; the circuit simply expires.
- **Atomicity.** Writes use `fcntl.flock` on a sidecar lock, plus `tempfile.mkstemp` + `os.replace` for crash-safe content swaps. The recovery timestamp advances **monotonically** (`max(current, proposed)`), so a late writer with a shorter window can never shrink an in-flight cooldown set by an earlier writer.
- **Configuration.** Controlled by two keys under `commands.rate_limits`:
  - `circuit_breaker_enabled` (default `true`) — set to `false` to disable pre-action gating and sidecar writes entirely.
  - `circuit_breaker_path` (default `.loops/tmp/rate-limit-circuit.json`) — override to relocate the shared file (e.g. onto a tmpfs or a path shared across multiple checkouts).

### Stall Detection

For prompt-based skills that may produce no-ops ("already done"), add a `check_stall` state using the `diff_stall` evaluator between `execute` and the first check state. Without it, idempotent skills silently exhaust `max_iterations` without progress:

```yaml
check_stall:
  action: "echo 'checking stall'"
  action_type: shell
  evaluate:
    type: diff_stall
    max_stall: 2
  on_yes: check_concrete    # progress detected — continue evaluation
  on_no: advance            # stalled — skip this item
```

### When to Use a Harness vs. Hand-Authored Loop

| Approach | Effort | Best for |
|----------|--------|----------|
| Harness wizard | ~2 min | Wrapping a skill in quality gates; batch processing with standard evaluation |
| Hand-authored YAML | 30–60 min | Multi-branch routing, complex captured-variable logic, non-standard evaluation |

For full details on evaluation phases, MCP gates, skill-as-judge, stall detection, and worked examples, see the **[Automatic Harnessing Guide](AUTOMATIC_HARNESSING_GUIDE.md)**.

---

## CLI Quick Reference

### Subcommands

| Command | Description |
|---------|-------------|
| `ll-loop run <name>` | Run a loop (also: `ll-loop <name>`); use `--worktree` for isolated branch execution |
| `ll-loop validate <name>` | Check YAML for schema errors and unreachable states |
| `ll-loop show <name>` | Display states, transitions, and ASCII diagram (`--json` for raw FSM config) |
| `ll-loop test <name>` | Run a single iteration to verify configuration |
| `ll-loop simulate <name>` | Trace execution interactively without running actions |
| `ll-loop list` | List available loops; `--running` for active only, `--builtin` for built-ins, `--category <cat>` / `--label <tag>` to filter by category or label |
| `ll-loop status <name>` | Show current state and iteration count (`--json` for machine-readable output) |
| `ll-loop stop <name>` | Stop a running loop |
| `ll-loop resume <name>` | Resume an interrupted loop from saved state |
| `ll-loop history <name>` | Show history; pass `run_id` to view a specific archived run |
| `ll-loop install <name>` | Copy a built-in loop to `.loops/` for customization |

### History Flags

| Flag | Effect |
|------|--------|
| `--tail` / `-n` | Limit output to last N events (default: 50) |
| `--event` / `-e` | Filter by event type (e.g. `evaluate`, `route`, `state_enter`) |
| `--state` / `-s` | Filter by state name (matches `state`, `from`, or `to` fields) |
| `--since` | Filter to events within a time window (e.g. `1h`, `30m`, `2d`) |
| `--verbose` / `-v` | Show action output preview and LLM call details (model, latency, prompt, response) |
| `--full` | Show untruncated prompts and output (implies --verbose) |
| `--json` | Output events as JSON array |

### Run Flags

| Flag | Effect |
|------|--------|
| `--dry-run` | Show execution plan without running actions |
| `--no-llm` | Disable LLM-based evaluation (use deterministic evaluators only) |
| `--llm-model <model>` | Override the LLM model for evaluation |
| `-n <N>` | Override `max_iterations` |
| `--queue` | Wait for conflicting scoped loops instead of erroring |
| `-q` / `--quiet` | Suppress progress output |
| `-v` / `--verbose` | Stream all action output live; default shows a short response head preview |
| `-b` / `--background` | Run as a background daemon |
| `--show-diagrams` | Display FSM box diagram with active state highlighted after each step |
| `--clear` | Clear terminal before each iteration; combine with `--show-diagrams` for a live in-place dashboard |
| `--delay <SECONDS>` | Sleep N seconds between iterations; overrides `backoff:` from YAML |
| `--context KEY=VALUE` | Override a context variable at runtime (repeatable) |

### Simulate Scenarios

The `simulate` command accepts `--scenario` to auto-select verdicts instead of prompting:

| Scenario | Behavior |
|----------|----------|
| `all-pass` | Every evaluation returns success/target |
| `all-fail` | Every evaluation returns failure/stall |
| `all-error` | Every evaluation returns error |
| `first-fail` | First evaluation fails, rest succeed |
| `alternating` | Alternates between success and failure |

## Pattern: Using `--check` with Exit Code Evaluators

Issue prep skills (`format-issue`, `verify-issues`, `ready-issue`, `confidence-check`, `issue-size-review`, `map-dependencies`, `normalize-issues`, `prioritize-issues`) support a `--check` flag that runs analysis without side effects and exits non-zero when work remains. This makes them usable as FSM loop evaluators with `evaluate: type: exit_code`.

**Important**: Since `/ll:` commands are auto-detected as prompt actions by the executor, states using `--check` must explicitly set `evaluate: type: exit_code` to bypass LLM-structured evaluation.

### Example: Prep-Sprint Invariants Loop

```yaml
name: prep-sprint
description: |
  Ensure all active issues pass prep gates before sprint planning.
  Checks format compliance, verification, sizing, dependencies, and readiness.
initial: check-format
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
    on_yes: check-size
    on_no: fix-verify
  fix-verify:
    action: "Run /ll:verify-issues --auto to fix verification issues."
    action_type: prompt
    next: check-verify
  check-size:
    action: "/ll:issue-size-review --check"
    action_type: slash_command
    evaluate:
      type: exit_code
    on_yes: check-deps
    on_no: fix-size
  fix-size:
    action: "Run /ll:issue-size-review --auto to decompose oversized issues."
    action_type: prompt
    next: check-size
  check-deps:
    action: "/ll:map-dependencies --check"
    action_type: slash_command
    evaluate:
      type: exit_code
    on_yes: done
    on_no: fix-deps
  fix-deps:
    action: "/ll:map-dependencies --auto"
    action_type: slash_command
    next: check-deps
  done:
    terminal: true
max_iterations: 20
timeout: 3600
```

Each `check-*` state uses `evaluate: type: exit_code` to route on the skill's exit code (0=success, 1=failure). The corresponding `fix-*` states run the skill in auto mode to remediate, then loop back to re-check.

## Tips

- **Start with low `max_iterations`** (5-10) while developing a loop. Increase once the logic is proven.
- **Use `backoff:`** to add a delay before a state's action executes — useful for rate-limited APIs or CI systems.
- **State is persisted to disk** after every transition. If a loop is interrupted, `ll-loop resume` picks up where it left off.
- **Convergence loops** use `direction:` to control whether the metric should go down (`minimize`, default) or up (`maximize`).
- **Loop run state and event logs are automatically archived** to `.loops/.history/<timestamp>-<loop-name>/` immediately on completion. Use `ll-loop history <name>` without a `run_id` to list archived runs, or `ll-loop history <name> <run_id>` to inspect a specific one.

## Composable Sub-Loops

Any loop can invoke another loop as a **child FSM** using the `loop:` field on a state. The child runs to completion; its result (`success` or `failure`) drives the parent's transition. This lets you build multi-stage pipelines from loops that already exist — without duplicating logic.

### Minimal Example

```yaml
name: "quality-then-ship"
initial: "run_quality"
max_iterations: 3
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

### Sharing Context Between Parent and Child

Add `context_passthrough: true` to share the parent's `context` and `captured` variables with the child loop, and merge the child's captures back into the parent when it completes:

```yaml
states:
  run_quality:
    loop: "fix-quality-and-tests"
    context_passthrough: true       # child sees parent context; parent gets child captures
    on_success: "run_git"
    on_failure: "done"
```

Without `context_passthrough`, the child runs with its own isolated context and its captured values are discarded after it exits.

### Routing Aliases

`on_success` and `on_failure` are accepted as aliases for `on_yes` and `on_no` in all states (not just sub-loop states). Use whichever reads more clearly for your use case.

### When to Use Sub-Loops vs. Inline States

| Approach | Best for |
|----------|----------|
| Sub-loop (`loop:`) | Reusing an existing, well-tested loop as a pipeline stage |
| Inline states | Custom logic that doesn't map cleanly to any existing loop |

For full sub-loop schema details — `context_passthrough`, verdict handling, and advanced examples — see the [FSM Loop System Design](../generalized-fsm-loop.md#6-sub-loop-composition) and [`skills/create-loop/reference.md`](../../skills/create-loop/reference.md).

### Visualizing Sub-Loop Execution

When `--show-diagrams` is active and a state invokes a child loop, both FSM diagrams are rendered after each child step:

```
== loop: my-loop ====...
[parent diagram — parent state highlighted]
── sub-loop: fix-quality-and-tests ──
[child diagram — current child state highlighted]
```

The parent state remains highlighted throughout child execution so you can track where you are in the outer pipeline. Sub-loop diagram display supports arbitrary nesting depth — each active sub-loop is shown below its parent with a separator, from depth-1 children down to depth-N grandchildren.

---

## Loop Discovery: category and labels

Every loop YAML can declare a `category` string and a `labels` list for filtering with `ll-loop list`:

```yaml
name: fix-quality-and-tests
category: code-quality
labels: [quality, lint, tests]
```

`ll-loop list` groups output by `category`. Loops without a category appear under `uncategorized`. Filter at the command line with:

```bash
ll-loop list --category code-quality          # loops in the code-quality category
ll-loop list --label tests                    # loops carrying the "tests" label
ll-loop list --builtin --category evaluation  # built-in evaluation loops only
```

`--label` can be repeated for an OR match: `--label tests --label lint` returns loops with either tag.

| Field | Type | Description |
|-------|------|-------------|
| `category` | `string` | Grouping label shown as a header in `ll-loop list` output |
| `labels` | `array[string]` | Arbitrary tags for finer-grained filtering |

Both fields are optional and have no effect on loop execution.

---

## Reusable State Fragments

A **fragment** is a named partial state definition stored in a library file. Any loop can import a library and reference a fragment by name — the fragment's fields are merged into the state at parse time, with state-level fields taking precedence. Fragments eliminate copy-pasted state structure (the same `action_type` + `evaluate` combination duplicated across states) without the overhead of a separate execution context.

### Defining a Fragment Library

Create a YAML file with a top-level `fragments:` dict. Each key is a fragment name; the value is a partial state dict. An optional `description` field documents what the fragment provides and what the calling state must supply — it is stripped at parse time and never reaches the FSM engine:

```yaml
# .loops/lib/common.yaml
fragments:
  shell_exit:
    description: |
      Shell command evaluated by exit code.
      State must supply: action, on_yes, on_no (and optionally on_error, timeout).
    action_type: shell
    evaluate:
      type: exit_code
```

To browse fragment names and descriptions without opening the raw YAML file:

```bash
ll-loop fragments lib/common.yaml
ll-loop fragments lib/cli.yaml
```

### Importing and Using Fragments

Add `import:` at the loop root with the library path (relative to the loop file's directory), then reference a fragment with `fragment: <name>` in any state:

```yaml
import:
  - lib/common.yaml

states:
  check_tests:
    fragment: shell_exit    # inherits action_type: shell + evaluate.type: exit_code
    action: "pytest"
    timeout: 600
    on_yes: done
    on_no: fix_tests
```

State-level fields override fragment fields at every nesting level, including nested objects. To change only one sub-field of `evaluate`, supply just that sub-field — the rest carry over from the fragment:

```yaml
states:
  check_count:
    fragment: retry_counter       # provides action_type, action script, evaluate.type/operator
    evaluate:
      target: 5                   # override only the target; type/operator from fragment
    on_yes: keep_going
    on_no: give_up
```

### Inline Fragments

Define fragments directly in the loop file without an `import:` line:

```yaml
fragments:
  my_gate:
    action_type: shell
    evaluate:
      type: exit_code

states:
  lint:
    fragment: my_gate
    action: "ruff check ."
    on_yes: done
    on_no: fix
```

Local `fragments:` definitions override any imported fragment with the same name.

### Built-in Libraries

Two libraries ship with little-loops, both in `scripts/little_loops/loops/lib/`:

#### `lib/common.yaml` — type-pattern fragments

Generic structure fragments (action_type + evaluate combinator) used by all built-in loops:

| Fragment | Description | Provides | Caller must supply |
|----------|-------------|----------|--------------------|
| `shell_exit` | Shell command evaluated by exit code. | `action_type: shell` + `evaluate.type: exit_code` | `action`, routing (`on_yes`, `on_no`) |
| `retry_counter` | Increments a counter file and checks if still below `context.max_retries`. | Shell counter script + `output_numeric` evaluator | `context.counter_key`, `context.max_retries`, routing |
| `llm_gate` | LLM prompt state with structured yes/no output. | `action_type: prompt` + `evaluate.type: llm_structured` | `action`, `evaluate.prompt`, routing (`on_yes`, `on_no`) |
| `numeric_gate` | Shell command evaluated by numeric output comparison. | `action_type: shell` + `evaluate.type: output_numeric` | `action`, `evaluate.operator`, `evaluate.target`, routing (`on_yes`, `on_no`) |
| `with_rate_limit_handling` | Applies per-state two-tier rate-limit retry handling: 3 short retries (30 s base backoff) then the default long-wait ladder (5 min → 15 min → 30 min → 1 h) up to a 6 h wall-clock budget. | `max_rate_limit_retries: 3`, `rate_limit_backoff_base_seconds: 30`, plus inherited `rate_limit_long_wait_ladder` and `rate_limit_max_wait_seconds` defaults | `on_rate_limit_exhausted` (target state name) |

#### `lib/cli.yaml` — ll- CLI tool fragments

Tool-specific fragments with pre-filled `action` fields for every major ll- CLI tool. Import with `lib/cli.yaml`; override `action` to add flags:

```yaml
import:
  - lib/cli.yaml

states:
  check_links:
    fragment: ll_check_links     # provides action_type, action, evaluate
    capture: link_results
    on_yes: done
    on_no: fix_links

  run_auto:
    fragment: ll_auto
    action: "ll-auto --priority P1,P2 --quiet"   # override action to add flags
    on_yes: done
    on_no: retry
```

| Fragment | Default `action` | Notes |
|----------|-----------------|-------|
| `ll_auto` | `ll-auto` | Run ll-auto sequentially. Override `action` to add `--priority`, `--quiet`, etc. |
| `ll_issues_list` | `ll-issues list --json` | List all active issues as JSON. |
| `ll_issues_next` | `ll-issues next-action` | Get next recommended action. Override `action` to add `--skip "..."`. |
| `ll_issues_next_issue` | `ll-issues next-issue` | Get next-priority issue file path. |
| `ll_history_summary` | `ll-history summary` | Print completed issue history summary. Override `action` to add `2>/dev/null` fallback. |
| `ll_check_links` | `ll-check-links 2>&1` | Check markdown docs for broken links. |
| `ll_messages` | `ll-messages --stdout` | Extract user messages from session logs. Override `action` to add `--skill`, `--examples-format`, etc. |
| `ll_deps` | `ll-deps check` | Validate cross-issue dependency references. |
| `ll_sprint_list` | `ll-sprint list` | List all defined sprint files. |
| `ll_parallel` | `ll-parallel` | Process issues concurrently using isolated worktrees. |
| `ll_workflows` | `ll-workflows` | Identify workflow patterns from user message history. |
| `ll_loop_run` | `ll-loop run ${context.loop_name}` | Run a named FSM loop as a sub-process. Requires `context.loop_name`. |

All `lib/cli.yaml` fragments use `action_type: shell` + `evaluate.type: exit_code`.

Built-in loops import the libraries as `import: ["lib/common.yaml"]` or `import: ["lib/cli.yaml"]`. User loops in `.loops/` can do the same — built-in fragment libraries resolve automatically, so no copying or symlinking is required. You can also define your own local fragments in your loop file or a local library.

### When to Use Fragments vs. Sub-Loops

| Approach | Best for |
|----------|----------|
| Fragment (`fragment:`) | Sharing a state *structure* (action_type + evaluate) across many states in one or more loops |
| Sub-loop (`loop:`) | Reusing a complete, well-tested loop as a pipeline stage with its own execution context |
| Inline states | Custom logic that doesn't map to any reuse pattern |

Fragment resolution is parse-time only — the engine never sees `fragment:` keys and there is no runtime overhead.

---

## Troubleshooting

| Problem | Cause | Fix |
|---------|-------|-----|
| Loop stuck in a cycle | Fix action isn't changing the result the evaluator sees | Check `ll-loop history` — if the same verdict repeats, adjust the fix action |
| Scope conflict error | Another loop holds a lock on overlapping paths | Find it with `ll-loop list --running` and stop it, or use `--queue` to wait |
| LLM evaluator errors | Claude CLI auth or network issue | Ensure `claude` CLI is authenticated (`claude auth`), or use `--no-llm` to fall back to deterministic evaluators |
| "No state found" on resume | Loop already completed or was never started | Check `ll-loop status` — completed loops have no resumable state |

## Further Reading

- [FSM Loop System Design](../generalized-fsm-loop.md) — FSM schema, evaluators, variable interpolation, and full YAML reference
- [Automatic Harnessing Guide](AUTOMATIC_HARNESSING_GUIDE.md) — Harness evaluation pipeline deep-dive, MCP gates, skill-as-judge, stall detection, and worked examples
- [Configuration Reference](../reference/CONFIGURATION.md) — Project-wide settings (test commands, paths, etc.) used by loop actions
- `/ll:create-loop` — Interactive loop creation wizard (includes harness mode)
- `/ll:review-loop` — Audit an existing loop for quality, correctness, and best practices
- `/ll:rename-loop` — Rename a loop (built-in or project-level) and update all references in other YAMLs, tests, and docs
- `ll-loop --help` — Full CLI reference for all loop subcommands
