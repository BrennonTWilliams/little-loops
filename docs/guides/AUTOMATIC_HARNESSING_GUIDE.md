# Automatic Harnessing Guide

A harness loop wraps your skill in a multi-stage quality pipeline — automatically retrying until the output passes your quality bar.

The hard problem in automated iteration isn't running the skill — it's knowing when the output is actually good. A harness loop is a quality evaluation pipeline that applies a skill or prompt to work items, then evaluates the result from multiple angles before advancing: mechanical tests catch regressions, LLM judgment assesses semantic quality, user-simulation skills verify the experience as a real user would, and diff invariants catch runaway changes. The wizard auto-derives this evaluation framework from your project config so you don't write it by hand.

---

## Table of Contents

- [What Is a Harness Loop?](#what-is-a-harness-loop)
  - [The Evaluation Pipeline](#the-evaluation-pipeline)
- [Evaluation Phases Explained](#evaluation-phases-explained)
  - [Tool-Based Gates (`check_concrete`)](#tool-based-gates-check_concrete)
  - [MCP Tool Gates (`check_mcp`)](#mcp-tool-gates-check_mcp)
  - [Skill-as-Judge (`check_skill`)](#skill-as-judge-check_skill)
  - [LLM-as-Judge (`check_semantic`)](#llm-as-judge-check_semantic)
  - [Diff Invariants (`check_invariants`)](#diff-invariants-check_invariants)
  - [Stall Detection (`check_stall`)](#stall-detection-check_stall)
- [When to Use a Harness](#when-to-use-a-harness)
- [Creating a Harness: The 4-Step Wizard](#creating-a-harness-the-4-step-wizard)
  - [Step H1: Choose a Target](#step-h1-choose-a-target)
  - [Step H2: Work Item Discovery](#step-h2-work-item-discovery)
  - [Step H3: Evaluation Phases](#step-h3-evaluation-phases)
  - [Step H4: Iteration Budget](#step-h4-iteration-budget)
- [Generated FSM Structure](#generated-fsm-structure)
  - [Variant A: Single-Shot](#variant-a-single-shot)
  - [Variant B: Multi-Item](#variant-b-multi-item)
- [Using the Example Files](#using-the-example-files)
- [Worked Example: Harness `refine-issue`](#worked-example-harness-refine-issue)
- [Tips](#tips)
- [Troubleshooting](#troubleshooting)
- [See Also](#see-also)

---

## What Is a Harness Loop?

A harness loop is a pre-structured FSM pattern that repeatedly applies a skill or prompt to a list of work items (or once in single-shot mode), evaluating success after each run through a layered quality pipeline.

### The Evaluation Pipeline

Each harness applies up to five evaluation phases in sequence, cheapest first:

| Phase | What it checks |
|-------|----------------|
| `check_concrete` | Exit code from test/lint/type command — objective, fast |
| `check_mcp` | MCP server tool call — deterministic external state |
| `check_skill` | Full agentic user simulation — did it work as a real user would? |
| `check_semantic` | LLM judges output quality — semantic correctness |
| `check_invariants` | Diff line count — catches runaway changes |

Each phase is optional; the wizard pre-selects based on your project config. All five can be active simultaneously, or you can use any subset.

**Conceptual cycle:**

```
            ┌──────────────────────────────────────────────────┐
            │                                                  │
            ▼                                                  │
       ┌─────────┐     items      ┌─────────┐                 │
       │discover │───remaining───►│ execute │                 │
       └─────────┘                └────┬────┘                 │
            │                         │                       │
         no items                   next                      │
            │                         ▼               on_no (retry)
            ▼                  ┌──────────────┐               │
          done ◄── terminal    │check_concrete│───────────────┤
                               └──────┬───────┘               │
                                   on_yes                      │
                                      ▼                        │
                               ┌──────────────┐               │
                               │  check_mcp   │───────────────┤
                               └──────┬───────┘               │
                                   on_yes                      │
                                      ▼                        │
                               ┌──────────────┐               │
                               │ check_skill  │───────────────┤
                               └──────┬───────┘               │
                                   on_yes                      │
                                      ▼                        │
                               ┌──────────────┐               │
                               │check_semantic│───────────────┤
                               └──────┬───────┘               │
                                   on_yes                      │
                                      ▼                        │
                               ┌──────────────────┐           │
                               │check_invariants  │───────────┘
                               └──────┬───────────┘
                                   on_yes
                                      ▼
                                  ┌─────────┐
                                  │ advance │──► discover
                                  └─────────┘
```

---

## Evaluation Phases Explained

### Tool-Based Gates (`check_concrete`)

Runs the highest-priority configured tool command from `ll-config.json` as a shell action with an `exit_code` evaluator. Exit code 0 = pass, non-zero = fail (retry execute).

This phase provides fast, objective feedback. It runs before the LLM judge, so failures are caught cheaply.

### MCP Tool Gates (`check_mcp`)

`action_type: mcp_tool` invokes an MCP server tool directly — not via Claude — yielding deterministic output at ~500ms latency. The `mcp_result` evaluator routes on the MCP response envelope rather than an exit code or LLM judgment. This makes it a good fit for verifying external state that the other evaluation phases cannot observe.

**`mcp_result` verdict table:**

| Verdict | Meaning |
|---------|---------|
| `success` | Tool ran and succeeded (`isError: false`) |
| `tool_error` | Tool ran but reported failure (`isError: true`) |
| `not_found` | Server or tool not registered in `.mcp.json` |
| `timeout` | Transport-level timeout |

**Generic pattern** (`check_mcp` is a naming convention, not a reserved name):

```yaml
check_mcp:
  action_type: mcp_tool
  action: "server/tool-name"              # server_name/tool_name from .mcp.json
  params:
    key: "${captured.current_item.output}"  # ${variable} interpolation supported
  capture: mcp_result
  route:
    success: check_invariants    # or next evaluation state
    tool_error: execute          # retry the execute state
    not_found: check_invariants  # server not configured — skip this gate
    timeout: execute
```

**Example: Browser UI verification** (one application among many)

A harness that implements a UI feature can use a playwright MCP server to check that the rendered page reflects the change before advancing:

```yaml
check_mcp:
  action_type: mcp_tool
  action: "playwright/screenshot"
  params:
    url: "http://localhost:3000"
  capture: ui_result
  route:
    success: check_invariants
    tool_error: execute
    not_found: check_invariants  # playwright not configured — skip
    timeout: execute             # dev server may not be up yet
```

**Other MCP gate applications:**
- `database/query` — verify a record was written
- `github/list_pull_requests` — confirm a PR was created
- `slack/get_messages` — check a notification was sent
- `filesystem/read_file` — verify a file was created at the expected path

**Placement**: `check_mcp` slots after `check_concrete` (cheap shell gates first) and before `check_semantic` / `check_invariants`. If the MCP call is expensive or optional, placing it last (just before `check_invariants`) avoids wasted cost on items that fail earlier checks.

### Skill-as-Judge (`check_skill`)

`check_skill` is the highest-fidelity evaluation mode in the pipeline: it invokes a skill whose job is to *use* the feature as a real user would, then judges whether the user experience actually worked. This is the only phase that evaluates from the perspective that actually matters — a real user completing a real workflow. Browser navigation, form submission, multi-step UX flows, or any end-to-end user simulation all belong here.

The skill runs as a full agentic Claude session and produces natural-language output; an `llm_structured` evaluator parses its verdict (YES/NO with rationale) and routes accordingly.

**How it differs from `check_mcp`:**

| | `check_mcp` | `check_skill` |
|---|---|---|
| Execution | Single deterministic tool call | Full agentic Claude session |
| Latency | ~500ms | 30–300s |
| Output | Structured MCP envelope | Natural-language rationale |
| Best for | Verifying discrete external state | Exercising complex user flows |

**YAML pattern:**

```yaml
check_skill:
  action: "/ll:act-as-user 'Navigate to /dashboard and verify the new filter works'"
  action_type: slash_command
  timeout: 300
  evaluate:
    type: llm_structured
    prompt: >
      Did the skill successfully complete the user flow without errors?
      Did it confirm the expected feature is present and working?
      Answer YES or NO with what it observed.
  on_yes: check_invariants
  on_no: execute
```

**`action_type` values for skill invocations:**

| `action_type` | How it runs | When to use |
|---|---|---|
| `slash_command` | Executes the action string as a named slash command directly | Use when the action is a fixed `/ll:<name>` slash command |
| `prompt` | Sends the action string as a free-form instruction to Claude | Use for natural-language prompts, or when the skill name is dynamic or constructed at runtime |

For skills invoked as free-form prompts (no fixed slash command), use `action_type: prompt`:

```yaml
check_skill:
  action: "Use the scrape-docs skill to fetch /api/users and confirm the new 'role' field appears in the response"
  action_type: prompt
  timeout: 180
  evaluate:
    type: llm_structured
    prompt: >
      Did the skill confirm the 'role' field is present in the API response?
      Answer YES or NO with what it observed.
  on_yes: check_invariants
  on_no: execute
```

**Placement**: `check_skill` slots after `check_concrete` and `check_mcp` (cheap/deterministic gates first) and before `check_semantic` / `check_invariants`. When `check_skill` covers quality assessment, `check_semantic` can be omitted — the skill already provides semantic judgment from a user perspective.

**Cost consideration**: `check_skill` runs a full agentic session (30–300s, proportional cost). Use it when a skill can verify something the other phases cannot observe — actual rendered UI, end-to-end user flow, or external system state that deterministic checks can't reach.

### LLM-as-Judge (`check_semantic`)

Uses an `llm_structured` evaluator where Claude assesses whether the previous action achieved its intent. The wizard collects two criteria from the user — what should change on success and what indicates failure — and generates a numbered multi-criteria evaluation prompt:

> **Why `echo` as the action?** `check_semantic` receives the echo string as `<action_output>` in the LLM prompt — an empty `echo` provides minimal evidence. To evaluate a prior state's output, set `source: "${captured.<var>.output}"` on the `evaluate` block, where `<var>` is the `capture` key on the source state. Note: `${prev.output}` at `check_semantic` resolves to `check_concrete`'s output (pytest results), not `execute`'s skill output — use the `capture` + `source` pattern instead (see production examples in `loops/issue-staleness-review.yaml:36-47`).

```yaml
evaluate:
  type: llm_structured
  prompt: >
    Evaluate the previous action on these criteria:
    1. [success criterion: what should be different after the skill runs successfully]
    2. Absence of failure signals: [failure criterion: what would indicate the skill failed]
    Answer YES only if all criteria pass. Otherwise NO, stating which criterion failed.
```

The wizard asks two follow-up questions when LLM-as-judge is selected: "What should be different in the output after the skill runs successfully?" and "What would indicate the skill failed or made no progress?" The answers populate criteria 1 and 2 respectively. For custom prompts, the same two-question format applies.

### Diff Invariants (`check_invariants`)

Runs `git diff --stat HEAD | wc -l | tr -d ' '` and checks that the line count is less than 50 using an `output_numeric` evaluator. This catches runaway changes — if a skill modifies far more than expected, the loop retries rather than advancing.

Adjust the `target` value for skills that intentionally make large changes.

### Referencing Captured Outputs

Use `${captured.<state_name>.output}` to pass output from one state to a later state:

```yaml
prompt: "Review this output: ${captured.execute.output}"
```

Use `${prev.output}` to reference the immediately preceding state's output.

### Stall Detection (`check_stall`) {#stall-detection-check_stall}

Add a `check_stall` state when a skill might loop without making any code changes. This is especially important for prompt-based skills that sometimes conclude "nothing to do" — without stall detection, they exhaust `max_iterations` silently.

**When to add stall detection:**
- The action uses `action_type: prompt` and may no-op
- You see a harness exhausting `max_iterations` without git commits
- The skill being harnessed sometimes returns "already done"

**Placement**: Insert `check_stall` between `execute` and the first check state (e.g., `check_concrete`). In this position, use `on_yes: check_concrete` (or whichever check state comes first) and `on_no: advance` (multi-item) or `on_no: done` (single-shot). Placing it here avoids making LLM-based quality checks on output from a run that has already stalled.

```yaml
check_stall:
  action: "echo 'checking stall'"     # output ignored by diff_stall
  action_type: shell
  evaluate:
    type: diff_stall
    scope: ["scripts/"]    # optional: limit diff to specific paths
    max_stall: 2           # optional: consecutive no-change iterations before stall
  on_yes: check_concrete   # progress detected — proceed to evaluation chain
  on_no: advance           # stalled — skip item (use on_no: done for single-shot)
  on_error: check_concrete
```

**`diff_stall` field reference:**

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `scope` | `list[str]` | *(entire repo)* | Paths to limit `git diff --stat` to |
| `max_stall` | `int` | `1` | Consecutive no-change iterations before failure verdict |

**Verdicts:**

| Verdict | Meaning |
|---------|---------|
| `yes` | Progress detected (diff changed) |
| `no` | Stalled — no changes for `max_stall` consecutive iterations |
| `error` | git unavailable or command failed |

---

**Full 6-phase ordering (with all phases active):**

```
check_stall      → no-op detection (diff_stall, <1s) — first, before any evaluation cost
check_concrete   → cheapest (exit code, <1s)
check_mcp        → deterministic tool call (~500ms)
check_skill      → agentic user simulation (30–300s)
check_semantic   → LLM text quality judgment (can omit when check_skill covers it)
check_invariants → diff size (cheapest final gate)
```

**Decision guide — when to reach for each phase:**

| Phase | Use when |
|-------|---------|
| `check_stall` (diff_stall) | The action is prompt-based and may no-op silently |
| `check_concrete` (shell) | A CLI tool exit-codes on pass/fail |
| `check_mcp` (mcp_tool) | An MCP server can deterministically verify the result |
| `check_skill` (slash_command + llm_structured) | A skill can exercise the feature end-to-end as a user would |
| `check_semantic` (LLM judge) | You need judgment about output quality |
| `check_invariants` (diff size) | You want to catch runaway changes |

---

## When to Use a Harness

Use a harness loop when you want to:

- **Wrap a skill in quality gates** — ensure tests pass and the LLM confirms success before advancing to the next item
- **Run a skill repeatedly over a list** — refining every open issue, checking every file, processing a batch of items in priority order
- **Set up a single polished iteration** — execute a skill once with full evaluation rather than just calling it manually
- **Run capable skills at scale, unattended** — even for skills that rarely fail, a harness lets you process 50 items unattended with the same confidence you'd have watching 1 item manually; the value isn't just catching failures, it's enabling workflows no single agent call could safely accomplish

As models improve, the harness becomes more ambitious, not less necessary — better skills expand the space of what a well-composed evaluation pipeline can accomplish.

Compare to hand-authoring a loop:

| Approach | Effort | Evaluators | Stall protection |
|----------|--------|------------|-----------------|
| Harness wizard | ~2 min | Auto-derived | Available as add-on |
| Hand-authored YAML | 30–60 min | Manual | Manual |

If your workflow is highly custom (e.g., multi-branch routing, complex captured-variable logic), hand-author using the [FSM reference](../../skills/create-loop/reference.md). Otherwise, use the harness wizard.

---

## Creating a Harness: The 4-Step Wizard

Run `/ll:create-loop` and select **"Harness a skill or prompt"** when prompted for loop type.

### Step H1: Choose a Target

The wizard scans `skills/*/SKILL.md` and presents every available skill with its description. Pick one, or choose **"Custom prompt"** to enter free-form natural language.

```
What do you want to harness?
  ○ refine-issue       — Refine issue files with codebase-driven research
  ○ format-issue       — Format issue files to align with template v2.0
  ○ check-code         — Run code quality checks (lint, format, types, build)
  ○ audit-docs         — Audit documentation for accuracy and completeness
  ○ ...                — (all discovered skills listed)
  ○ Custom prompt      — Enter a free-form natural language prompt to repeat
```

If you pick **Custom prompt**, you'll also be asked: *"What does 'done' look like?"* — this answer drives the LLM-as-judge evaluation prompt.

---

### Step H2: Work Item Discovery

```
How are work items discovered?
  ○ Single-shot (no item iteration)      — Run once; no discover state
  ○ Active issues list (Recommended for issue skills) — ll-issues list --json
  ○ File glob pattern                    — Find files matching a pattern
  ○ Manual list                          — Hard-code items in the loop
```

If you pick **File glob pattern**, you'll be prompted for the glob (e.g., `.issues/**/*.md`).
If you pick **Manual list**, you'll enter comma-separated items.

**Discovery commands generated per mode:**

| Mode | Discovery Command |
|------|------------------|
| Active issues list | `ll-issues list --json \| python3 -c "..."` |
| File glob pattern | `find . -name '<pattern>' -not -path './.git/*' \| sort \| head -1` |
| Manual list | `python3 -c "items='<item1>,<item2>,...'.split(','); print(items[0])"` |

The active issues command filters for `status == 'open'`, prints the first issue ID, and exits 1 when the list is empty. See Variant B below for the full Python snippet.

---

### Step H3: Evaluation Phases

The wizard reads `.claude/ll-config.json` to detect configured tool commands and presents only relevant options. All available phases are pre-selected (default, can be changed); stall detection is pre-selected by default since all H1 choices produce prompt-based execution. (See [Evaluation Phases Explained](#evaluation-phases-explained) above for what each phase does.)

```
Which evaluation phases should be included? (multi-select)
  ☑ Tool-based gates (Recommended)                      — Shell checks using test/lint/type commands
  ☑ Stall detection (Recommended for prompt-based skills) — Detects no-op iterations
  ☑ LLM-as-judge                                        — Claude assesses output against skill description
  ☑ Diff invariants                                     — git diff --stat line count < 50
  ○ Skill-based evaluation (Optional)                   — Invoke a skill to exercise and verify the feature as a user would
```

> **Note**: `check_mcp` is not offered by the wizard. If your harness requires an MCP tool call for evaluation, add a `check_mcp` state manually to the generated YAML after wizard completion. See [`check_mcp`](#mcp-tool-gates-check_mcp) in the Evaluation Phases Explained section for the required fields.

**Tool-gate priority order** (highest-priority configured command wins):
1. `test_cmd` — most comprehensive
2. `lint_cmd` — fast feedback
3. `type_cmd` — type safety
4. If none configured: `check_concrete` state is omitted entirely

---

### Step H4: Iteration Budget

```
How many retries per item before giving up?
  ○ 3 retries (Recommended)   — Good balance for most skills
  ○ 5 retries                 — For complex or slow-converging skills
  ○ 1 retry (strict)          — Fail fast; skip items that don't resolve immediately

What is the total iteration budget?
  ○ 50 (Recommended)    — For up to ~15 items with 3 retries each
  ○ 100                 — For larger item sets
  ○ 200                 — For long-running batch operations
```

**Convergence defaults by skill category:**

| Skill category | Suggested max_iterations | Per-item retries |
|----------------|--------------------------|------------------|
| Issue refinement / analysis | 200 | 3 |
| Code quality / fix | 50 | 5 |
| Documentation | 100 | 3 |
| Custom prompt | 50 | 3 |

---

## Generated FSM Structure

### Variant A: Single-Shot

Generated when work item mode is **"Single-shot"**. Starts directly at `execute` with no discovery loop.

```yaml
name: "harness-check-code"
initial: execute
max_iterations: 5          # = per-item retries
states:

  execute:
    action: /ll:check-code --auto
    action_type: slash_command
    next: check_concrete

  check_concrete:            # present if tool-based gates selected
    action: python -m pytest scripts/tests/ -q --tb=no
    action_type: shell
    evaluate:
      type: exit_code
    on_yes: check_semantic
    on_no: execute

  check_semantic:            # present if LLM-as-judge selected
    action: echo 'Evaluating output quality'
    action_type: shell
    evaluate:
      type: llm_structured
      prompt: >
        Evaluate the previous action on these criteria:
        1. No lint or type errors remain in the modified files
        2. Absence of failure signals: no error output, no unresolved violations reported
        Answer YES only if all criteria pass. Otherwise NO, stating which criterion failed.
    on_yes: check_invariants
    on_no: execute

  check_invariants:          # present if diff invariants selected
    action: "git diff --stat HEAD | wc -l | tr -d ' '"
    action_type: shell
    evaluate:
      type: output_numeric
      operator: lt
      target: 50
    on_yes: done
    on_no: execute

  done:
    terminal: true
```

> **Ready-to-run example**: [`scripts/little_loops/loops/harness-single-shot.yaml`](../../scripts/little_loops/loops/harness-single-shot.yaml) is a fully annotated version of this variant, including commented-out `check_mcp` and `check_skill` optional gates. See [Using the Example Files](#using-the-example-files) below.

---

### Variant B: Multi-Item

Generated for **Active issues list**, **File glob pattern**, or **Manual list**. Adds `discover` and `advance` states around the evaluation chain.

```yaml
name: "harness-refine-issue"
initial: discover
max_iterations: 200        # total budget across all items
states:

  discover:                  # shell command pops the next item
    action: "ll-issues list --json | python3 -c ..."
    action_type: shell
    capture: "current_item"
    evaluate:
      type: exit_code
    on_yes: execute          # item found → process it
    on_no: done              # no items left → finished

  execute:
    action: /ll:refine-issue ${captured.current_item.output} --auto
    action_type: prompt
    max_retries: 3           # prevents a stuck item from exhausting the budget
    on_retry_exhausted: advance
    next: check_concrete

  check_concrete:
    action: python -m pytest scripts/tests/ -q --tb=no
    action_type: shell
    evaluate:
      type: exit_code
    on_yes: check_semantic
    on_no: execute

  check_semantic:
    action: echo 'Evaluating refinement quality'
    action_type: shell
    evaluate:
      type: llm_structured
      prompt: >
        Evaluate the previous action on these criteria:
        1. The issue file was meaningfully updated with new codebase-grounded information
        2. Absence of failure signals: no error output, no unchanged or empty issue content
        Answer YES only if all criteria pass. Otherwise NO, stating which criterion failed.
    on_yes: check_invariants
    on_no: execute

  check_invariants:
    action: "git diff --stat HEAD | wc -l | tr -d ' '"
    action_type: shell
    evaluate:
      type: output_numeric
      operator: lt
      target: 50
    on_yes: advance
    on_no: execute

  advance:                   # mark item done, loop back to discover
    action: echo 'Item complete'
    action_type: shell
    next: discover

  done:
    terminal: true
```

> **`max_retries` + `on_retry_exhausted`**: Adding these to `execute` is the key safeguard in multi-item loops. Without them, one item that never passes evaluation will consume the entire `max_iterations` budget. With them, the loop skips the stuck item and moves on after `max_retries` attempts.

> **Ready-to-run example**: [`scripts/little_loops/loops/harness-multi-item.yaml`](../../scripts/little_loops/loops/harness-multi-item.yaml) is a fully annotated version of this variant with all five evaluation phases active, including `check_mcp` and `check_skill`. See [Using the Example Files](#using-the-example-files) below.

---

## Using the Example Files

Two annotated example harness loops are built in to `loops/`:

| File | Variant | Phases included |
|------|---------|-----------------|
| [`scripts/little_loops/loops/harness-single-shot.yaml`](../../scripts/little_loops/loops/harness-single-shot.yaml) | A — Single-shot | `check_stall`, `check_concrete`, `check_semantic`, `check_invariants`; `check_mcp` and `check_skill` as commented-out optional gates |
| [`scripts/little_loops/loops/harness-multi-item.yaml`](../../scripts/little_loops/loops/harness-multi-item.yaml) | B — Multi-item | All five phases active: `check_concrete`, `check_mcp`, `check_skill`, `check_semantic`, `check_invariants` |

Each state in both files has an `# EXAMPLE:` comment explaining its pedagogical purpose.

### Validate structure

```bash
ll-loop validate harness-single-shot
ll-loop validate harness-multi-item
```

### Run interactively (dry-run)

`ll-loop test` walks through every state and lets you choose simulated verdicts — useful for understanding the FSM transitions without executing the real skill:

```bash
ll-loop test harness-single-shot
```

### Run for real

```bash
ll-loop run harness-single-shot
ll-loop run harness-multi-item
```

The multi-item example discovers open issues via `ll-issues list` and runs `/ll:manage-issue` on each one. Make sure you have open issues before running it.

### Adapt to your own workflow

The recommended approach is to copy, rename, and edit rather than modifying the originals (so they remain usable as references):

```bash
ll-loop install harness-single-shot   # copies to .loops/harness-single-shot.yaml
cp .loops/harness-single-shot.yaml .loops/my-harness.yaml
```

Key fields to change:

| Field | What to change it to |
|-------|----------------------|
| `name` | A descriptive name for your loop |
| `execute.action` | Your skill or prompt (e.g., `/ll:check-code --auto`) |
| `check_concrete.action` | Your test/lint command, or remove the state entirely |
| `check_semantic.evaluate.prompt` | Multi-criteria numbered prompt: criterion 1 (what should change), criterion 2 (absence of failure signals) |
| `check_invariants.evaluate.target` | Increase if your skill makes large diffs legitimately |
| `discover.action` | Your item discovery command (multi-item only) |

After editing, validate with `ll-loop validate <your-file>` before running.

---

## Worked Example: Harness `refine-issue`

The following is a production-ready harness that refines all active issues. It is the canonical output of running the wizard with: target = `refine-issue`, discovery = active issues, all evaluation phases enabled, 3 retries, 200 iterations.

> **See also**: [`scripts/little_loops/loops/harness-multi-item.yaml`](../../scripts/little_loops/loops/harness-multi-item.yaml) is a runnable annotated variant of this pattern with all five evaluation phases active, including `check_mcp` and `check_skill`.

> **Note**: This example includes `check_concrete` and `check_semantic` but omits `check_mcp` and `check_skill`. The `check_mcp` gate is not generated by the wizard (add it manually if needed — see [MCP Tool Gates](#mcp-tool-gates-check_mcp)). The `check_skill` gate is optional and only applies when a user-simulation skill is available for the workflow; it is omitted here to keep the example minimal.

```yaml
name: "harness-refine-issue"
initial: discover
max_iterations: 200
timeout: 14400                    # 4-hour wall clock limit (seconds)
states:

  discover:                       # pop the next open issue ID
    action: |
      ll-issues list --json | python3 -c "
      import json, sys
      issues = json.load(sys.stdin)
      open_issues = [i for i in issues if i.get('status') == 'open']
      if not open_issues:
          sys.exit(1)
      print(open_issues[0]['id'])
      "
    action_type: shell
    capture: "current_item"       # stored as ${captured.current_item.output}
    evaluate:
      type: exit_code
    on_yes: execute
    on_no: done                   # empty list → all issues processed

  execute:                        # invoke the skill with the captured issue ID
    action: /ll:refine-issue ${captured.current_item.output} --auto
    action_type: prompt
    max_retries: 3                # prevents a stuck issue from exhausting max_iterations
    on_retry_exhausted: advance
    next: check_concrete

  check_concrete:                 # run tests to confirm no regressions
    action: python -m pytest scripts/tests/ -q --tb=no
    action_type: shell
    evaluate:
      type: exit_code
    on_yes: check_semantic
    on_no: execute

  check_semantic:                 # LLM confirms the issue was actually refined
    action: echo 'Evaluating refinement quality'
    action_type: shell
    evaluate:
      type: llm_structured
      prompt: >
        Did the previous /ll:refine-issue action successfully refine the issue?
        Check that: the issue file was updated with new content, confidence scores
        were added or improved, and no errors occurred. Answer YES or NO.
    on_yes: check_invariants
    on_no: execute

  check_invariants:               # catch runaway edits (> 50 diff lines)
    action: "git diff --stat HEAD | wc -l | tr -d ' '"
    action_type: shell
    evaluate:
      type: output_numeric
      operator: lt
      target: 50
    on_yes: advance
    on_no: execute

  advance:                        # mark item done, loop back for the next one
    action: echo 'Issue refined'
    action_type: shell
    next: discover

  done:
    terminal: true
```

---

## Tips

- **Route `not_found` to the next phase**, not back to `execute`, in `check_mcp` states. If the MCP server isn't configured in `.mcp.json`, retrying the execute state won't fix it — skip to the next evaluation gate instead.
- **Start with single-shot** to validate the skill works end-to-end before adding discovery. Use `ll-loop run <file>` with a single item to test the evaluation chain.
- **Use `ll-loop validate`** to check the FSM structure before full execution — it validates YAML syntax, transition completeness, and terminal reachability.
- **Add stall detection** for prompt-based skills (especially custom prompts) that may no-op. A skill that says "already done" on every item will silently exhaust your budget without it.
- **Check `ll-config.json`** has at least one tool command (`test_cmd`, `lint_cmd`, or `type_cmd`) to get the concrete `check_concrete` gate. Without it, the wizard omits the tool phase and your loop has no objective quality check.
- **Tune `target: 50`** in `check_invariants` if your skill intentionally makes large changes (e.g., a doc rewrite skill). Increase to 150–200 for documentation-heavy skills.
- **Set `timeout`** on the loop-level (seconds) for long-running batch operations to avoid unbounded runs.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| Loop exhausts `max_iterations` without finishing | No stall detection; one item looping forever | Add `check_stall` state; or add `max_retries` + `on_retry_exhausted` on `execute` |
| LLM-judge always returns NO | Evaluation prompt too strict or vague | Edit `check_semantic.evaluate.prompt` to match actual skill output characteristics |
| `check_concrete` state missing from generated YAML | No tool commands in `ll-config.json` | Run `/ll:configure` to set `test_cmd`, `lint_cmd`, or `type_cmd` |
| `discover` exits immediately with no items | Discovery command filter too narrow | Check that issues have `status: open`; verify `ll-issues list` returns results |
| `check_invariants` always fails | Skill makes large diffs legitimately | Increase `target` from 50 to a value appropriate for the skill |
| Loop runs but nothing changes across iterations | Skill is idempotent / "already done" | Add `check_stall` with `max_stall: 1` to skip no-op items |
| `check_mcp` always routes to `not_found` | Server not registered in `.mcp.json` | Add the MCP server entry to `.mcp.json` or route `not_found` to the next phase to skip gracefully |
| `check_skill` always returns NO | Skill prompt too broad or skill has no browser/nav capability | Narrow the skill instruction; ensure the skill has access to the target system; check timeout is long enough |

---

## See Also

- [LOOPS_GUIDE.md](LOOPS_GUIDE.md) — Full FSM loops reference: evaluators, state fields, CLI commands
- [`skills/create-loop/loop-types.md`](../../skills/create-loop/loop-types.md) — Wizard implementation: Harness Questions section (lines 548–914)
- [`skills/create-loop/reference.md`](../../skills/create-loop/reference.md) — FSM field reference, evaluator catalog, harness state diagrams
- [`scripts/little_loops/loops/issue-refinement.yaml`](../../scripts/little_loops/loops/issue-refinement.yaml) — Real-world harness-like loop: multi-skill pipeline over active issues with commit cadence
- [`scripts/little_loops/loops/harness-single-shot.yaml`](../../scripts/little_loops/loops/harness-single-shot.yaml) — Runnable Variant A example: single-shot harness with all evaluation phases annotated
- [`scripts/little_loops/loops/harness-multi-item.yaml`](../../scripts/little_loops/loops/harness-multi-item.yaml) — Runnable Variant B example: multi-item harness including `check_mcp` and `check_skill` gates
