# Automatic Harnessing Guide

## When to Use This Guide

Use a harness when you want to run a skill over multiple work items and automatically gate quality — catching regressions, retrying on failure, and advancing only when the output passes your criteria. Skip this if you just want to run a skill once; a harness adds overhead (typically 3–5× the token cost of a single call) in exchange for automated quality assurance.

> **Why bother?** A single skill call on a novel task fails ~30% of the time. A harness with two evaluation phases catches most of those failures automatically, retries, and only declares success when the result passes. For batch work (10+ issues), that 30% saved from manual review compounds quickly.

---

A harness loop wraps your skill in a multi-stage quality pipeline — automatically retrying until the output passes your quality bar.

The hard problem in automated iteration isn't running the skill — it's knowing when the output is actually good. A harness loop is a quality evaluation pipeline that applies a skill or prompt to work items, then evaluates the result from multiple angles before advancing: mechanical tests catch regressions, LLM judgment assesses semantic quality, user-simulation skills verify the experience as a real user would, and diff invariants catch runaway changes. The wizard auto-derives this evaluation framework from your project config so you don't write it by hand.

> **Harnessing a skill ≠ optimizing a harness.** This guide is about wrapping a skill in a quality pipeline — the *harness stays fixed* while the skill runs over your work. If instead you want to iteratively rewrite the *harness artifact itself* (a skill, command, agent, loop YAML, or `CLAUDE.md`) against a benchmark, see [HARNESS_OPTIMIZATION_GUIDE.md](HARNESS_OPTIMIZATION_GUIDE.md).

---

## Table of Contents

- [What Is a Harness Loop?](#what-is-a-harness-loop)
  - [The Evaluation Pipeline](#the-evaluation-pipeline)
- [Evaluation Phases Explained](#evaluation-phases-explained)
  - [Tool-Based Gates (`check_concrete`)](#tool-based-gates-check_concrete)
  - [MCP Tool Gates (`check_mcp`)](#mcp-tool-gates-check_mcp)
  - [Contract Gates (`check_contract`)](#contract-gates-check_contract)
  - [Skill-as-Judge (`check_skill`)](#skill-as-judge-check_skill)
  - [LLM-as-Judge (`check_semantic`)](#llm-as-judge-check_semantic)
  - [Baseline Regression Guard (`check_comparator`)](#baseline-regression-guard-check_comparator)
  - [Diff Invariants (`check_invariants`)](#diff-invariants-check_invariants)
  - [Referencing Captured Outputs](#referencing-captured-outputs)
  - [Shared Messages Log (`append_to_messages`)](#shared-messages-log-append_to_messages)
  - [Stall Detection (`check_stall`)](#stall-detection-check_stall)
- [When to Use a Harness](#when-to-use-a-harness)
- [Creating a Harness: The 5-Step Wizard](#creating-a-harness-the-5-step-wizard)
  - [Step H1: Choose a Target](#step-h1-choose-a-target)
  - [Step H2: Work Item Discovery](#step-h2-work-item-discovery)
  - [Step H3: Evaluation Phases](#step-h3-evaluation-phases)
  - [Step H4: Iteration Budget](#step-h4-iteration-budget)
  - [Step H5: External API Gate](#step-h5-external-api-gate)
- [Generated FSM Structure](#generated-fsm-structure)
  - [Variant A: Single-Shot](#variant-a-single-shot)
  - [Variant B: Multi-Item](#variant-b-multi-item)
  - [Variant C: Specialist-Role Pipeline](#variant-c-specialist-role-pipeline)
- [Using the Example Files](#using-the-example-files)
- [Worked Example: Harness `refine-issue`](#worked-example-harness-refine-issue)
- [Tips](#tips)
- [Troubleshooting](#troubleshooting)
- [Validating Your Harness](#validating-your-harness)
- [Signal Handling (`ll-loop run`)](#signal-handling-ll-loop-run)
- [See Also](#see-also)

---

## What Is a Harness Loop?

A harness loop is a pre-structured finite-state machine (FSM) pattern that repeatedly applies a skill or prompt to a list of work items (or once in single-shot mode), evaluating success after each run through a layered quality pipeline.

### The Evaluation Pipeline

Each harness applies up to five evaluation phases in sequence, cheapest first:

| Phase | What it checks |
|-------|----------------|
| `check_concrete` | Exit code from test/lint/type command — objective, fast |
| `check_mcp` | MCP server tool call — deterministic external state |
| `check_skill` | Full agentic user simulation — did it work as a real user would? |
| `check_semantic` | LLM judges output quality — semantic correctness |
| `check_invariants` | Diff line count — catches runaway changes |

Each phase is optional; the wizard pre-selects based on your project config. All five can be active simultaneously, or you can use any subset. Additional optional gates — `check_contract`, `check_comparator`, and `check_stall` — are covered below alongside these five.

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

### Contract Gates (`check_contract`)

`check_contract` is a deterministic-input + LLM-judged evaluator that reads *two related artifacts simultaneously* and asserts alignment at the integration seam between a producer and a consumer. It targets the boundary-mismatch failure class: two components each correctly implemented but disagreeing at their interface.

**When to use**: Use when a PR implements both a producer (API endpoint, exported function, config file) and a consumer (front-end hook, import, downstream reader) and you need to gate on shape alignment — field names, casing, type structure — rather than just existence.

**How it differs from `check_semantic`:**

| | `check_semantic` | `check_contract` |
|---|---|---|
| Input | Single action output blob | Two file paths (producer + consumer) |
| Reads files | No — evaluates action stdout | Yes — reads both files directly |
| Cost | ~1 LLM call | 1 LLM call per pair |
| Best for | Did this action succeed? | Do these two artifacts agree at their boundary? |

**YAML pattern:**

```yaml
check_contract:
  action_type: contract          # self-contained: no shell action runs
  evaluate:
    type: contract
    pairs:
      - producer: "src/app/api/projects/route.ts"
        producer_pattern: "NextResponse\\.json\\((.+?)\\)"   # optional — extract the relevant slice
        consumer: "src/hooks/useProjects.ts"
        consumer_pattern: "fetchJson<(.+?)>"
        contract: "shape and field names must align (camelCase on both sides, no wrapping mismatch)"
  on_yes: check_invariants
  on_no: execute
```

**Pair fields:**

| Field | Required | Description |
|-------|----------|-------------|
| `producer` | Yes | Path to the producer file |
| `consumer` | Yes | Path to the consumer file |
| `contract` | Yes | Alignment rule the LLM judge enforces |
| `producer_pattern` | No | Regex to extract just the relevant slice from the producer |
| `consumer_pattern` | No | Regex to extract just the relevant slice from the consumer |

**Verdicts:**

| Verdict | Meaning |
|---------|---------|
| `yes` | All pairs aligned |
| `no` | Any pair fails alignment |
| `error` | File unreadable or regex pattern matched nothing |

**Placement**: `check_contract` slots after `check_concrete` (cheap shell gates first) and before `check_skill` / `check_semantic`. It reads files directly — no shell action needed — and runs at LLM-judge latency (~2–5s per pair). Use it when your harness implements both sides of an interface in the same session and you want an explicit integration gate before the full user-simulation phase.

**MR-1 note**: MR-1 is the meta-loop design rule requiring every LLM-judged state to be paired with a non-LLM evaluator (see [HARNESS_OPTIMIZATION_GUIDE.md](HARNESS_OPTIMIZATION_GUIDE.md#the-design-rules-mr-1mr-10)). `check_contract` uses an LLM judge and does **not** satisfy MR-1 in meta-loops. Pair it with a non-LLM evaluator (e.g., `diff_stall` or `exit_code`) when `modifies_harness: true`.

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
  # /ll:act-as-user is illustrative, not a built-in — substitute your own user-simulation skill
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
  action: "Use the explore-api skill to fetch /api/users and confirm the new 'role' field appears in the response"
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

#### Evidence Contract (ENH-2342 / MR-8)

LLM self-grades average 33–55% accuracy without grounding (Table 1 of the SHOR study — the harness-optimizer research cited in [HARNESS_OPTIMIZATION_GUIDE.md](HARNESS_OPTIMIZATION_GUIDE.md#see-also); Sonnet 4.6 = 33.4%). The evidence contract addresses this by requiring the judge to cite verbatim output text for every verdict.

**Runtime enforcement** (always on): `evaluate_llm_structured()` injects `CHECK_SEMANTIC_EVIDENCE_CONTRACT` into every prompt and coerces any verdict with an empty `evidence` field to `"no"` at the parsing layer — verdicts cannot pass through without a citation. Custom schemas (explicit `schema:` parameter) bypass coercion; callers who supply their own schema control the contract.

**Static lint** (MR-8 WARNING): `ll-loop validate` flags `check_semantic` states whose `evaluate.prompt` omits evidence-contract keywords (`verbatim`, `quote`, `evidence`). States with no `evaluate.prompt` (inheriting `DEFAULT_LLM_PROMPT`) are not flagged — the contract is injected automatically. Suppress with `evidence_contract_ok: true` when justified.

To satisfy MR-8, add one sentence to your `evaluate.prompt`:

```yaml
evaluate:
  type: llm_structured
  prompt: >
    Evaluate the previous action on these criteria:
    1. [success criterion]
    2. Absence of failure signals: [failure criterion]
    Answer YES only if all criteria pass. Otherwise NO, stating which criterion failed.
    Quote the EXACT line(s) from the output supporting your verdict (verbatim, in quotes).
    If you cannot find a verbatim quote, your verdict MUST be No.
```

This pairs with MR-1 (non-LLM evaluator required alongside LLM judges): MR-1 ensures the gate can't be gamed; the evidence contract ensures the LLM side is meaningfully discriminating rather than defaulting to optimism.

### Baseline Regression Guard (`check_comparator`)

Uses a `comparator` evaluator to run one or more blind A/B comparisons between the current output and a stored baseline, then takes a majority vote. This prevents harness regressions: if a recent change makes outputs worse than a known-good baseline, the loop routes to retry rather than advancing.

Baselines are stored under `.loops/baselines/<loop-name>/output.txt` — a sibling to `runs/` in the `.loops/` directory. The first successful run bootstraps the baseline automatically when `auto_promote: true` is set. To manually promote a run as the new baseline after inspecting its output, use `ll-loop promote-baseline <loop>`.

**When to use instead of `check_semantic`**: Use `check_comparator` when you have a known-good output and want to detect regressions; use `check_semantic` when you want a general LLM quality judgment without a reference baseline.

```yaml
check_comparator:
  action: "echo ${captured.execute.output}"
  action_type: shell
  evaluate:
    type: comparator
    baseline_path: ".loops/baselines/my-loop/"
    auto_promote: true    # on first run (no baseline), bootstrap and route yes
    min_pairs: 1          # increase for higher confidence (majority vote)
  on_yes: check_invariants
  on_no: execute
  on_tie: execute         # tie counts as no regression — route to retry
  on_no_baseline: check_invariants  # baseline missing without auto_promote
```

**Verdict table:**

| Verdict | Meaning |
|---------|---------|
| `yes` | Harness output wins majority of comparisons |
| `no` | Baseline wins majority |
| `tie` | Equal wins across `min_pairs` comparisons |
| `no_baseline` | No baseline file and `auto_promote` is false |

**Note**: `comparator` calls the LLM (via `evaluate_blind_comparator`) and does **not** satisfy MR-1 in meta-loops. Pair it with a non-LLM evaluator (e.g., `diff_stall` or `exit_code`) when `modifies_harness: true`.

### Diff Invariants (`check_invariants`)

Runs `git diff --stat HEAD | wc -l | tr -d ' '` and checks that the line count is less than 50 using an `output_numeric` evaluator. This catches runaway changes — if a skill modifies far more than expected, the loop retries rather than advancing.

Adjust the `target` value for skills that intentionally make large changes.

### Referencing Captured Outputs

Use `${captured.<state_name>.output}` to pass output from one state to a later state:

```yaml
prompt: "Review this output: ${captured.execute.output}"
```

Use `${prev.output}` to reference the immediately preceding state's output.

### Shared Messages Log (`append_to_messages`)

For pipelines where **every later state needs the accumulated prior reasoning** (not just the immediately-preceding output), use `append_to_messages` to build a run-scoped log:

```yaml
states:
  plan:
    action: "/ll:iterate-plan ${context.issue_id}"
    capture: plan_out
    append_to_messages: "${captured.plan_out.output}"
    next: execute

  execute:
    action: "/ll:manage-issue enh implement ${context.issue_id}\n\nContext:\n${messages}"
    capture: exec_out
    append_to_messages: "${captured.exec_out.output}"
    next: report

  report:
    action: "echo 'Full run log:\n${messages.last(5)}'"
    terminal: true
```

**Available template variables:**
- `${messages}` — full log (all appended strings, newline-separated)
- `${messages.last(N)}` — last N entries (windowed view)
- `${messages.summary}` — pre-computed summary (when summarization middleware is active)

**When to prefer `append_to_messages` over `captured.*` chains:**
- 3+ states all need the same accumulated context
- You find yourself writing `${captured.A.output}\n${captured.B.output}\n${captured.C.output}` in prompts
- Specialist-role pipelines (Plan → Research → Implement → Report) where each stage builds on all prior reasoning

The two mechanisms are complementary: keep `capture:` for structured per-field access (`${captured.X.exit_code}`, `${captured.X.stderr}`); add `append_to_messages` when later states need the narrative history.

### Stall Detection (`check_stall`) {#stall-detection-check_stall}

Add a `check_stall` state when a skill might loop without making any code changes. This is especially important for prompt-based skills that sometimes conclude "nothing to do" — without stall detection, they exhaust `max_steps` silently.

**When to add stall detection:**
- The action uses `action_type: prompt` and may no-op
- You see a harness exhausting `max_steps` without git commits
- The skill being harnessed sometimes returns "already done"

**Placement**: Insert `check_stall` between `execute` and the first check state (e.g., `check_concrete`). In this position, use `on_yes: check_concrete` (or whichever check state comes first) and `on_no: advance` (multi-item) or `on_no: done` (single-shot). Placing it here avoids making LLM-based quality checks on output from a run that has already stalled.

```yaml
check_stall:
  action: "echo 'checking stall'"     # output ignored by diff_stall
  action_type: shell
  fragment: diff_stall_gate
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

#### `action_stall` — Action/Output Repeat Detection

Use `action_stall` when you want to detect a loop that keeps emitting the same action or captured output without git changes (e.g., a skill that repeatedly proposes the same fix). Unlike `diff_stall`, it does not require a git repository and works against any context values.

```yaml
check_stall:
  action: "echo 'checking action stall'"
  action_type: shell
  evaluate:
    type: action_stall
    track: ["action"]      # context keys to hash (default: ["action"])
    max_repeat: 2          # consecutive identical hashes before stall verdict
  on_yes: check_concrete
  on_no: advance
```

**`action_stall` field reference:**

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `track` | `list[str]` | `["action"]` | Context keys to hash for repeat detection |
| `max_repeat` | `int` | `2` | Consecutive identical-hash iterations before failure verdict |

**Verdicts:**

| Verdict | Meaning |
|---------|---------|
| `yes` | Tracked values changed (progress) |
| `no` | Stalled — identical hash for `max_repeat` consecutive iterations |

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

### Deviating From the Wizard

The wizard generates a complete harness that covers the most common cases. Here's when and how to modify it:

| You want to... | How |
|---------------|-----|
| Add an MCP verification gate | Add a `check_mcp` state after `check_concrete` (see [MCP Tool Gates](#mcp-tool-gates-check_mcp)). The wizard never generates this state — add it manually after generation. |
| Drop a phase that's too expensive | Remove the state and update any `on_yes` transitions that pointed to it to skip directly to the next state. |
| Add a phase after generation | Install the loop locally with `ll-loop install <name>`, edit the YAML, and re-validate with `ll-loop validate`. |
| Raise the retry cap | Increase `max_retries` on the `execute` state. Default is 3; raise for skills that occasionally time out. |
| Stop retrying a stuck item instead of looping forever | Add `on_retry_exhausted: advance` to the `execute` state — the item is skipped after `max_retries` attempts. |

---

## Creating a Harness: The 5-Step Wizard

Run `/ll:create-loop` and select **"Harness a skill or prompt"** when prompted for loop type, or pass a description directly to skip the wizard — e.g., `/ll:create-loop harness the refine-issue skill and iterate until the issue is implementation-ready`.

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

The wizard reads `.ll/ll-config.json` to detect configured tool commands and presents only relevant options. All phases except skill-based evaluation are pre-selected (defaults, can be changed); stall detection is pre-selected by default since all H1 choices produce prompt-based execution. (See [Evaluation Phases Explained](#evaluation-phases-explained) above for what each phase does.)

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

| Skill category | Suggested max_steps | Per-item retries |
|----------------|--------------------------|------------------|
| Issue refinement / analysis | 200 | 3 |
| Code quality / fix | 50 | 5 |
| Documentation | 100 | 3 |
| Custom prompt | 50 | 3 |

---

### Step H5: External API Gate

The wizard checks `learning_tests.enabled` in `.ll/ll-config.json` before presenting this question. If the flag is `false`, this step is skipped entirely.

When enabled, the wizard also checks whether `learning_tests_required` is already set in the target issue's frontmatter (populated by `/ll:scope-epic` or `/ll:wire-issue`). If so, the gate is auto-inserted without asking.

Otherwise, the wizard asks:

```
Does this loop invoke external packages or third-party APIs
(e.g., Anthropic SDK, HTTP APIs, database drivers)?
  ○ No (Recommended)              — Skip the assumption firewall gate
  ○ Yes — add assumption-firewall gate  — Inject an assumption_gate state
```

**If "Yes"**: An `assumption_gate` sub-loop state is inserted before `execute`. The initial state becomes `assumption_gate`, and a required `context.issue_file` variable is added. The gate invokes the `assumption-firewall` built-in loop, which extracts and validates external-API assumptions before any implementation work runs.

**If "No"**: The `initial` state remains `execute` (Variant A) or `discover` (Variant B), and no gate states are added.

See [loop-types.md — Step H5](../../skills/create-loop/loop-types.md) for the full question flow and the generated YAML pattern.

---

## Generated FSM Structure

### Variant A: Single-Shot

Generated when work item mode is **"Single-shot"**. Starts directly at `execute` with no discovery loop.

```yaml
name: "harness-check-code"
initial: execute
max_steps: 5          # = per-item retries
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
max_steps: 200        # total budget across all items
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

> **`max_retries` + `on_retry_exhausted`**: Adding these to `execute` is the key safeguard in multi-item loops. Without them, one item that never passes evaluation will consume the entire `max_steps` budget. With them, the loop skips the stuck item and moves on after `max_retries` attempts.

> **Ready-to-run example**: [`scripts/little_loops/loops/harness-multi-item.yaml`](../../scripts/little_loops/loops/harness-multi-item.yaml) is a fully annotated version of this variant with all five evaluation phases active, including `check_mcp` and `check_skill`. See [Using the Example Files](#using-the-example-files) below.

---

### Variant C: Specialist-Role Pipeline

Variant C decomposes a task into four specialist roles — Plan, Research, Implement, and Report — each as a distinct FSM state. Use it when the task benefits from explicit phase separation: deep refactors, multi-file features, or cross-cutting changes where a single `execute` state is too coarse-grained.

```
plan -> research -> implement -> check_stall -> check_concrete -> check_semantic -> check_invariants -> report -> done
```

**Role responsibilities:**

| Role | State | Purpose |
|------|-------|---------|
| Planner | `plan` | Generate a structured plan for the task before any implementation |
| Researcher | `research` | Investigate codebase, docs, or web for relevant context |
| Implementer | `implement` | Apply the plan using research context; equivalent to `execute` in Variants A/B |
| Reporter | `report` | Summarize what was done after the evaluation chain passes |

**Human-in-the-loop (HITL) gate pattern (FEAT-1794 dependency):** Between `plan` and `research`, an optional `review_plan` gate can pause the loop for human approval. Until `action_type: human_approval` (FEAT-1794) is available, use the workaround pattern from `scripts/little_loops/loops/loop-router.yaml` (a prompt state with `output_contains` routing). The ready-to-run example includes the HITL gate as a commented-out `# OPTIONAL: review_plan` block.

**Evaluation chain:** Variants A and B evaluation phases (`check_stall`, `check_concrete`, `check_semantic`, `check_invariants`) apply between `implement` and `report`, identical to Variant A. The stall route goes to `report` rather than `done`, so the earlier planning and research context is always surfaced in the final report even when implementation stalls.

> **Ready-to-run example**: [`scripts/little_loops/loops/harness-plan-research-implement-report.yaml`](../../scripts/little_loops/loops/harness-plan-research-implement-report.yaml) is a fully annotated version of this variant. See [Using the Example Files](#using-the-example-files) below.

---

## Using the Example Files

Three annotated example harness loops are built in to `loops/`:

| File | Variant | Phases included |
|------|---------|-----------------|
| [`scripts/little_loops/loops/harness-single-shot.yaml`](../../scripts/little_loops/loops/harness-single-shot.yaml) | A — Single-shot | `check_stall`, `check_concrete`, `check_semantic`, `check_invariants`; `check_mcp` and `check_skill` as commented-out optional gates |
| [`scripts/little_loops/loops/harness-multi-item.yaml`](../../scripts/little_loops/loops/harness-multi-item.yaml) | B — Multi-item | All five phases active: `check_concrete`, `check_mcp`, `check_skill`, `check_semantic`, `check_invariants` |
| [`scripts/little_loops/loops/harness-plan-research-implement-report.yaml`](../../scripts/little_loops/loops/harness-plan-research-implement-report.yaml) | C — Specialist-role pipeline | `plan`, `research`, `implement` roles with full evaluation chain; `review_plan` HITL gate as commented-out `# OPTIONAL:` block |

Each state in all three files has an `# EXAMPLE:` comment explaining its pedagogical purpose.

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
max_steps: 200
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
    max_retries: 3                # prevents a stuck issue from exhausting max_steps
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
- **MCP-heavy `execute` states** (e.g. ~10 Playwright or vision-agent calls + synthesis) need `timeout: 1500` or higher at the state level. The 3600s executor fallback is bypassed by any loop-level `default_timeout:` — a low value will kill the prompt mid-synthesis.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| Loop exhausts `max_steps` without finishing | No stall detection; one item looping forever | Add `check_stall` state; or add `max_retries` + `on_retry_exhausted` on `execute` |
| LLM-judge always returns NO | Evaluation prompt too strict or vague | Edit `check_semantic.evaluate.prompt` to match actual skill output characteristics |
| `check_concrete` state missing from generated YAML | No tool commands in `ll-config.json` | Run `/ll:configure` to set `test_cmd`, `lint_cmd`, or `type_cmd` |
| `discover` exits immediately with no items | Discovery command filter too narrow | Check that issues have `status: open`; verify `ll-issues list` returns results |
| `check_invariants` always fails | Skill makes large diffs legitimately | Increase `target` from 50 to a value appropriate for the skill |
| Loop runs but nothing changes across iterations | Skill is idempotent / "already done" | Add `check_stall` with `max_stall: 1` to skip no-op items |
| `check_mcp` always routes to `not_found` | Server not registered in `.mcp.json` | Add the MCP server entry to `.mcp.json` or route `not_found` to the next phase to skip gracefully |
| `check_skill` always returns NO | Skill prompt too broad or skill has no browser/nav capability | Narrow the skill instruction; ensure the skill has access to the target system; check timeout is long enough |
| Evaluator passes too consistently (always YES or always NO) | Evaluator verdict has near-zero variance across runs; the gate isn't actually measuring anything | Run `ll-loop diagnose-evaluators <loop>` to identify non-discriminating states; tighten judge prompt, adjust numeric target, or replace `exit_code` evaluator with one that exercises the feature |

---

## Validating Your Harness

A harness adds evaluation gates and retry logic that cost tokens and time. Before committing to it, verify it actually earns that cost by improving output quality over an unguided baseline call. The `--baseline` flag runs a blind A/B comparison in a single `ll-loop run` invocation.

### Quick Start

```bash
ll-loop run harness-single-shot --baseline
```

This executes two arms concurrently and prints a summary when both finish.

### Flags

| Flag | Purpose |
|------|---------|
| `--baseline` | Enable A/B mode |
| `--baseline-skill SKILL` | Override the inferred baseline skill (see below) |
| `--items N` | Limit sample size when the harness processes a large backlog |

`--baseline` cannot be combined with `--worktree` or `--resume`.

### How It Works

**Parallel arms.** A `ThreadPoolExecutor(max_workers=2)` runs both arms concurrently:

- **Harness arm** — full gated execution: all `check_*` evaluators, retries, and routing active. Drives FSM state transitions as normal.
- **Baseline arm** — single-shot skill invocation, no evaluation gates, no retries. Data-collection only; it does not affect loop routing.

The harness arm is what advances the loop. The baseline arm exists solely to give the judge something to compare against.

**Blind evaluation.** Before the judge sees the outputs, they are randomly labeled "Output A" and "Output B" — the judge never knows which arm produced which. Verdicts are de-anonymized after the judge responds. This prevents the judge from being biased toward the arm it perceives as "the better system."

**Token and duration capture.** Both arms independently accumulate `(input + output)` token counts and wall-clock duration. These appear in the summary and per-item records.

### Reading the Output

```
A/B Summary (n=10)
  Harness pass-rate:  90%   Baseline pass-rate: 60%   Delta: +30%

  Median tokens:      harness=84k  baseline=42k  (+100%)
  Median duration:    harness=3.0s  baseline=1.0s  (+200%)
  Verdict:            harness wins on quality, costs ~100% more tokens

Per-item: .loops/runs/<run-id>/ab.json
```

**Interpreting the delta:** A positive delta means the harness produces better output. Treat deltas below ~10pp with caution — judge variance at small sample sizes can produce noise at that level. Run with a larger `--items` count if you need a tighter confidence interval.

**Interpreting the cost ratio:** A +30pp quality delta at +100% token cost is generally worth it for high-stakes automation (code changes, architecture decisions). It's likely not worth it for low-stakes batch tasks where "good enough" output is acceptable.

### `ab.json` Schema

Per-item records are written to `.loops/runs/<run-id>/ab.json`:

```json
{
  "summary": {
    "harness_pass_rate": 0.9,
    "baseline_pass_rate": 0.6,
    "delta": 0.3,
    "median_tokens_harness": 84000,
    "median_tokens_baseline": 42000,
    "median_duration_harness": 3000,
    "median_duration_baseline": 1000
  },
  "items": [
    {
      "index": 0,
      "harness_pass": true,
      "baseline_pass": false,
      "harness_tokens": 91000,
      "baseline_tokens": 38000,
      "harness_duration_ms": 3200,
      "baseline_duration_ms": 950,
      "confidence": 0.85,
      "reason": "Output A clearly addressed the edge case; Output B ignored it."
    }
  ]
}
```

Use per-item records to audit individual comparisons — a harness that wins on aggregate but loses on specific item types may have a targeted gap in its evaluation chain.

### `--baseline-skill` Override

By default, the baseline skill is extracted by parsing the harness's `execute.action` for a `/ll:some-skill` pattern. When the action is a shell script, a compound command, or uses flags that change behavior, the extraction may fail or produce the wrong skill.

Override it explicitly:

```bash
# Harness action is a shell script — tell it which skill to invoke as the baseline
ll-loop run my-harness --baseline --baseline-skill "/ll:refine-issue"

# Compare a flagged variant against the unflagged baseline
ll-loop run my-harness --baseline --baseline-skill "/ll:refine-issue"
# harness runs: /ll:refine-issue --with-context
# baseline runs: /ll:refine-issue
```

### From A/B to Regression Detection: `promote-baseline`

Once you've validated that the harness wins, promote the winning run as the permanent baseline for ongoing regression detection:

```bash
ll-loop promote-baseline harness-single-shot
# → Promoted baseline for harness-single-shot: .loops/baselines/harness-single-shot/output.txt
```

From here, add a `check_comparator` evaluator state to the harness. Future runs compare each output against this stored baseline and route `no` if the output regresses:

```yaml
check_comparator:
  action: "echo ${captured.execute.output}"
  action_type: shell
  evaluate:
    type: comparator
    baseline_path: ".loops/baselines/harness-single-shot/"
    auto_promote: true    # bootstrap baseline on first run if missing
    min_pairs: 1
  on_yes: check_invariants
  on_no: execute          # retry if baseline wins
  on_tie: check_invariants
  on_no_baseline: check_invariants
```

**The two modes are complementary, not the same:**

| Mode | When to use |
|------|------------|
| `--baseline` | One-time empirical validation: does this harness earn its cost? |
| `check_comparator` | Continuous regression guard: did a recent change make outputs worse? |

Both use `.loops/baselines/<loop>/output.txt` as the reference file.

**Testing without full integration:**
While developing harnesses, test the blind evaluator in isolation by importing
`evaluate_blind_comparator()` from `little_loops.fsm.evaluators` and feeding it
two output strings.

---

## Signal Handling (`ll-loop run`)

When validating or running a harness under `ll-loop run`, know how the
loop reacts to POSIX signals — the audit trail's durability depends on
it. The signal handlers live at
`scripts/little_loops/cli/loop/_helpers.py:78-173` and are registered
for both `SIGINT` and `SIGTERM`.

### First Ctrl-C (or `SIGTERM`) — graceful shutdown

The handler sets an internal shutdown flag and calls
`executor.request_shutdown()`. Any child subprocess currently blocking
in the action runner (e.g. a long-running `sleep`, shell pipeline, or
MCP call) is killed via `proc.kill()` so the loop does not wait for it
to finish naturally (BUG-592 / BUG-818). The executor completes its
current state, then `PersistentExecutor.run`'s post-block calls
`archive_run()`, copying `state.json` and `events.jsonl` into
`.loops/.history/<run_id>-<loop_name>/`. Exit code: `0`.

### Second Ctrl-C — force-exit with audit trail

If a second `SIGINT` arrives while the loop is still shutting down, the
handler takes a force-exit branch (ENH-2516,
`scripts/little_loops/cli/loop/_helpers.py:103-107`) that calls
`PersistentExecutor.archive_run_only(terminated_by="interrupted_force")`
*before* `sys.exit(1)`. The `.history/<run_id>-<loop_name>/` archive
still lands. Exit code: `1`. This is the user-visible contract that
`scripts/tests/test_fsm_signal_integration.py::test_second_signal_force_exit_archives`
locks in CI.

### `SIGKILL` (`kill -9`) — cannot be trapped

POSIX `SIGKILL` cannot be intercepted by a Python signal handler. If a
supervisor, CI runner, or OOM killer issues `SIGKILL`, the loop dies
without invoking any handler code. Rows already appended to
`events.jsonl` survive (ENH-2515, `scripts/little_loops/fsm/persistence.py:129-145` —
every append is `flush()` + `os.fsync()`-d before returning), but the
`.history/<run_id>-<loop_name>/` archive and the final `state.json`
snapshot may not land.

**Mitigation:** run `ll-loop run` under a layer that sends `SIGTERM`
on shutdown rather than `SIGKILL`:

| Layer | What to use |
|-------|-------------|
| CI runner | Set the job's `killSignal` to `SIGTERM` (not `SIGKILL`); most CI systems default to one or the other |
| Local terminal | Use `tmux` or `screen` — the multiplexer receives the terminal's `SIGHUP` and forwards `SIGTERM` to its child processes |
| Detached session | `nohup ll-loop run … &` — survives shell exit; the parent shell's exit sends `SIGHUP` which `nohup` ignores, then the loop continues until the next signal |
| Long-running service | `systemd` unit with `KillSignal=SIGTERM` (the default), `TimeoutStopSec=30` |

The end-to-end SIGINT contract is verified by
`scripts/tests/test_fsm_signal_integration.py`. When in doubt, prefer
to inspect the audit trail (`events.jsonl` and the `.history/...`
archive) instead of assuming the latest state was captured.

---

## See Also

- [LOOPS_GUIDE.md](LOOPS_GUIDE.md) — Full FSM loops reference: evaluators, state fields, CLI commands
- [`skills/create-loop/loop-types.md`](../../skills/create-loop/loop-types.md) — Wizard implementation: Harness Questions section (lines 548–914)
- [`skills/create-loop/reference.md`](../../skills/create-loop/reference.md) — FSM field reference, evaluator catalog, harness state diagrams
- [`scripts/little_loops/loops/issue-refinement.yaml`](../../scripts/little_loops/loops/issue-refinement.yaml) — Real-world harness-like loop: multi-skill pipeline over active issues with commit cadence
- [`scripts/little_loops/loops/harness-single-shot.yaml`](../../scripts/little_loops/loops/harness-single-shot.yaml) — Runnable Variant A example: single-shot harness with all evaluation phases annotated
- [`scripts/little_loops/loops/harness-multi-item.yaml`](../../scripts/little_loops/loops/harness-multi-item.yaml) — Runnable Variant B example: multi-item harness including `check_mcp` and `check_skill` gates
- [`scripts/little_loops/loops/html-anything.yaml`](../../scripts/little_loops/loops/html-anything.yaml) — Real-world generator-evaluator harness: generalized HTML artifact generator with runtime artifact classification, dynamic rubric, and per-criterion thresholds across 9 surface types
- [`scripts/little_loops/loops/hitl-compare.yaml`](../../scripts/little_loops/loops/hitl-compare.yaml) — Human-in-the-loop comparison harness: identify → prune → oracle delegation to `oracles/generator-evaluator` producing an interactive HTML comparison page with an "Export selections" affordance
- [`scripts/little_loops/loops/hitl-md.yaml`](../../scripts/little_loops/loops/hitl-md.yaml) — Human-in-the-loop single-document review harness: GP-TSM segment (with multi-channel saliency + length-normalized credibility) → oracle delegation to `oracles/generator-evaluator` producing an interactive HTML page with sensemaking enhancements (staged highlighting, density slider, schema-switching, canvas minimap, calibrated friction), edit affordances, and "Copy AI prompt" / "Copy updated markdown" controls. Styles source from design token CSS custom properties.
- [`scripts/little_loops/loops/html-website-generator.yaml`](../../scripts/little_loops/loops/html-website-generator.yaml) — Real-world generator-evaluator harness: generator-evaluator loop for single-page website design with Playwright screenshot evaluation
- [`scripts/little_loops/loops/svg-image-generator.yaml`](../../scripts/little_loops/loops/svg-image-generator.yaml) — Real-world generator-evaluator harness: generator-evaluator loop for SVG icon and illustration creation with Playwright screenshot evaluation
- `/ll:create-eval-from-issues` — Generate a `check_skill`-only eval harness from one or more issue IDs; translates Expected Behavior and Acceptance Criteria into synthesized execute and evaluation prompts automatically
