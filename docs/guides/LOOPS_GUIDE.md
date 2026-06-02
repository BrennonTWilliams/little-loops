# Loops Guide

## Contents

- [What Is a Loop?](#what-is-a-loop)
- [Quick Start](#quick-start)
- [How Loops Work](#how-loops-work)
- [Common Loop Patterns](#common-loop-patterns)
- [Walkthrough: Creating and Running a Loop](#walkthrough-creating-and-running-a-loop)
- [Built-in Loops](#built-in-loops)
- [Beyond the Basics](#beyond-the-basics)
- [Background Mode](#background-mode)
- [Prompt Optimization Loops (APO)](#prompt-optimization-loops-apo)
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

## Quick Start

The fastest way to create and run a loop:

1. **Create**: `/ll:create-loop` — answer the wizard prompts, or pass a description to skip them (e.g., `/ll:create-loop run mypy until it passes`)
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
4. Repeats until reaching a **terminal state**, hitting `max_iterations`, or triggering `max_edge_revisits` (see below)

Use `/ll:create-loop` for an interactive wizard that guides you through creating loops, or write FSM YAML directly (see the [FSM Loop System Design](../generalized-fsm-loop.md) for the schema).

**Safety limits:**

Three loop-level fields guard against runaway loops:

| Field | Default | Behavior |
|-------|---------|----------|
| `max_iterations` | `50` | Total state executions before the loop terminates with `terminated_by="max_iterations"` |
| `on_max_iterations` | `null` | State to execute exactly once when the iteration cap fires. If set, the named state runs before the loop terminates. Emits `max_iterations_summary` event. `terminated_by` remains `"max_iterations"`. See [ENH-1631](#on_max_iterations-summary-hook). |
| `max_edge_revisits` | `100` | Maximum times any single state→state edge may fire; terminates with `terminated_by="cycle_detected"` (exit code 1) when exceeded. Edge counts survive `--resume`. |
| `circuit.repeated_failure` | unset | When configured, observes consecutive identical `(state, exit_code, verdict)` triples across iterations. Fires after `window` consecutive matches (default `3`) and either terminates with `terminated_by="stall_detected"` or routes to `on_repeated_failure: <state>`. See [stall detector](#stall-detector-circuit-repeated-failure) below. |

`max_edge_revisits` catches tight two-state oscillations that would otherwise drain the entire `max_iterations` budget. Lower it (e.g., `max_edge_revisits: 5`) on short focused loops to surface regressions faster.

`circuit.repeated_failure` catches a complementary failure mode: a *single* state that fails the same way every iteration (e.g. a quality gate whose action times out with `exit_code=124` and whose evaluator returns `"error"` deterministically). Such a state never re-traverses an edge, so `max_edge_revisits` cannot catch it — but the stall detector compares the full `(state, exit_code, verdict)` triple across iterations and aborts (or routes to a recovery state) once the streak hits `window` consecutive matches. One non-matching iteration resets the streak.

```yaml
circuit:
  repeated_failure:
    window: 3                  # consecutive iterations with identical triple (default 3)
    on_repeated_failure: abort # "abort" terminates, or name of a declared recovery state
```

**False-positive stalls in check↔work loops (BUG-1674):** States with `next:` (no `evaluate:`) are invisible to the stall detector — only eval-bearing states record triples. If your loop has a `check`→`work`→`check` ping-pong where `work` uses `next:`, the detector sees three consecutive `(check, exit_code, "no")` triples and fires even though `work` made real file-level progress.

Fix: add `progress_paths` under `repeated_failure`. When any listed path's `(mtime, size)` changes between two consecutive `check` records, the rolling window resets. Supports `${env.PWD}` interpolation.

```yaml
circuit:
  repeated_failure:
    window: 3
    on_repeated_failure: diagnose
    progress_paths:
      - "${env.PWD}/.loops/tmp/plan.md"
      - "${env.PWD}/.loops/tmp/dod.md"
```

Loops that do not set `progress_paths` are unaffected — existing semantics are preserved.
<!-- END TODO stub -->

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

Use `/ll:create-loop` to build any of these. Pass a natural language description to skip the wizard (e.g., `/ll:create-loop reduce lint errors to zero`), or run it with no args for the interactive guided flow. Either way the output is FSM YAML ready to run.

## Walkthrough: Creating and Running a Loop

Here's a complete example: a loop that fixes test failures until all tests pass.

### 1. Create

Run `/ll:create-loop` to use the interactive wizard, or pass a description directly — `/ll:create-loop fix tests until they pass` — to skip most questions. Or write the FSM YAML directly:

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

### 8. A/B Comparison (--baseline)

Validate that a harness loop improves output quality over an unguided LLM call:

```bash
ll-loop run harness-single-shot --baseline
```

This runs the loop in two parallel arms: the **harness arm** executes the full loop
with all evaluation gates active, while the **baseline arm** runs an ungated
single-shot invocation. A blind LLM judge evaluates both outputs without knowing
which arm produced which, then de-anonymizes the verdicts.

After completion, `ab.json` is written to the run directory and a summary prints:

```
A/B Summary (n=10)
  Harness pass-rate:  90%
  Baseline pass-rate: 60%
  Delta:              +30%

  Median tokens:      harness=84k  baseline=42k  (+100%)
  Median duration:    harness=3.0m  baseline=1.0m  (+200%)
  Verdict:            harness wins on quality, costs ~100% more tokens
```

Use `--baseline-skill` to override the baseline arm skill, and `--items` to set
the number of compare cycles. See
[AUTOMATIC_HARNESSING_GUIDE.md § Validating Your Harness](AUTOMATIC_HARNESSING_GUIDE.md)
for interpretation guidance.

### 9. Monitor

```bash
ll-loop status fix-tests     # Current state and iteration count
ll-loop history fix-tests    # Full execution history
```

## Built-in Loops

These loops ship with little-loops and cover common workflows. Install one to `.loops/` to customize it:

```bash
ll-loop install <name>       # Copies to .loops/ for editing
```

**Routing**

| Loop | Description |
|------|-------------|
| `loop-router` | Natural-language entry point — classifies a goal into the best-fit project or built-in loop (3-way branch: project / built-in / propose new), scores candidates, dispatches as a sub-loop, and summarises the result |

`loop-router` is the recommended starting point when you know *what you want done* but not *which loop to run*:

```bash
ll-loop run loop-router "research how our auth middleware handles refresh tokens"
# Router classifies → scores candidates → dispatches deep-research → summarises report

ll-loop run loop-router "refine FEAT-1654 to ready" --context auto=false
# auto=false → shows top candidates for human selection before dispatching

ll-loop run loop-router "every Friday generate a PR digest and post it to Slack" --context auto_create=true
# No existing loop fits → drafts a new project loop spec and invokes /ll:create-loop
```

Context knobs:

| Variable | Default | Effect |
|----------|---------|--------|
| `auto` | `"true"` | Skip HITL confirmation when top candidate meets threshold |
| `auto_create` | `"false"` | When branch C fires (propose_new), invoke `/ll:create-loop` immediately |
| `confidence_threshold` | `"0.7"` | Minimum score to auto-dispatch without HITL |
| `exclude` | `""` | Comma-separated loop names to omit from the catalog |

**Three routing branches:**
- **A — project**: goal matches a project-specific loop in `.loops/*.yaml` (preferred)
- **B — built-in**: goal matches a general-purpose built-in loop
- **C — propose_new**: no loop fits; router drafts a structured spec for a new project loop

**General-Purpose**

| Loop | Description |
|------|-------------|
| `dataset-curation` | Scan raw data, quality-gate each item, fix or reject, balance distribution, validate schema, and publish a curated dataset |
| `general-task` | Definition-of-done driven task loop — define verifiable criteria first, then execute and verify until all criteria pass |
| `greenfield-builder` | End-to-end greenfield project builder: spec analysis → tech research → design artifacts → eval harness → issue decomposition → refinement → eval-driven improvement cycle |
| `eval-driven-development` | Reusable eval-driven development cycle: implement issues, run eval harness, capture issues from failures, refine, and iterate until the harness passes |
| `refine-to-ready-issue` | Single-issue refinement pipeline — refine → wire → confidence-check until the issue reaches ready status |
| `cli-anything-bootstrap` | Meta-loop that bootstraps an agent-native CLI for target software (local path or repo URL), bakes a per-target rubric, caches the result, and emits a project-local task loop to `.loops/generated/` that downstream loops invoke to drive the target toward user goals |

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

1. **Define Done** — writes verifiable acceptance criteria to `.loops/tmp/general-task-dod.md`. When the task has a runtime surface (running code, executing tests, installing a service, producing output at runtime), the DoD must include runtime-behavior criteria — static file/import checks alone are insufficient.
2. **Plan** — decomposes the task into discrete steps in `.loops/tmp/general-task-plan.md`
3. **Execute** — five sub-states handle crash recovery, step selection, implementation, verification, and marking:
   - `resume_check` (shell): runs **once after `plan`** to detect an in-flight checkpoint from a previous crashed run. If `.loops/tmp/general-task-checkpoint.json` exists and the output files listed in `general-task-last-files.txt` are all present on disk, emits `RESUME_SKIP` and routes to `mark_done` (step completed but never marked). If the checkpoint exists but files are missing, deletes the checkpoint and emits `RESUME_CLEAN`, routing to `select_step` for a clean re-execution. If no checkpoint exists, emits `RESUME_NONE` and routes normally to `select_step`.
   - `select_step` (shell): finds the first unchecked plan step, writes it to `.loops/tmp/general-task-current-step.txt`, writes a crash-recovery checkpoint to `.loops/tmp/general-task-checkpoint.json` (JSON with `in_flight_step` and `timestamp` fields), and emits `SELECTED_STEP: <text>`. Routes to `do_work` on success, or directly to `check_done` if no unchecked steps remain.
   - `do_work` (prompt): reads the selected step from the temp file, implements **only** that step (must not modify the plan or DoD files), and writes `LAST_FILES: <paths>` to `.loops/tmp/general-task-last-files.txt`. Has a 900s timeout to bound per-step cost. Captured as `work_result`.
   - `verify_step` (shell): reads `general-task-last-files.txt` and runs `python -m pytest` on any Python files listed. Emits `VERIFY_PASS` or `VERIFY_FAIL`; routes to `mark_done` on pass, `continue_work` on fail.
   - `mark_done` (shell): marks the first unchecked step `[x]` in the plan file using a cross-platform `awk` pattern, then removes the current-step temp file and the in-flight checkpoint (if present). Routes to `check_done`.
4. **Verify** — reads both the DoD and the plan, then applies a three-step verification policy:
   1. *Plan-vs-DoD coverage* — for every plan step, confirms at least one DoD criterion covers it; adds new criteria for any uncovered step.
   2. *Delta-scoped criterion verification* — `do_work` captures `LAST_FILES` (every file created or modified) in `captured.work_result.output` and writes it to `.loops/tmp/general-task-last-files.txt`; `select_step` captures the step text in `captured.selected_step.output`. `check_done` reads these and only re-verifies criteria that are plausibly affected by the delta; previously-`[x]` criteria outside the delta are kept without re-running their commands, bounding per-iteration cost to the slice of criteria the latest step could have touched.
   3. *Sample re-verification* — picks up to `min(3, total_checked)` already-`[x]` criteria at random and independently re-verifies each, appending a `## Sample Verification` section to the DoD. This safety net catches regressions in criteria outside the delta's scope regardless of which step just ran.

   After writing the verification report, `check_done` routes unconditionally to a `count_done` shell state. `count_done` parses both files and emits a JSON object `{"hard_unchecked_dod": N, "soft_unchecked_dod": N, "unchecked_plan": N, "failed_samples": N, "total": N}`, then uses an `output_json` evaluator to route deterministically: `total == 0` → `final_verify`, `total > 0` → `continue_work`, missing file → `diagnose`. The `.total` field applies a two-tier gate: hard criteria (tagged `[hard]` at the end of the criterion line) always block; soft criteria (untagged) only block when the overall DoD pass rate falls below `context.min_pass_rate` (default 0.95). This means a loop reaches the terminal gate when all hard criteria are verified and ≥95% of all criteria are checked, even if soft (human-decision) criteria remain unchecked. This removes LLM judgment from the per-iteration termination decision and makes the success contract machine-readable.

   When `count_done` routes to `final_verify`, the loop enters a two-state terminal gate that runs exactly once per successful completion. `final_verify` (prompt) re-verifies **every** DoD criterion independently from evidence — not just the sample — and appends a `## Final Verification` section to the DoD file with per-criterion pass/fail results. Any criterion that fails re-verification is flipped back to `[ ]` in the Verification Criteria list. `count_final` (shell) then counts `FAILED` entries in the most-recent `## Final Verification` section (resetting on each new section header, so only the latest pass is evaluated): zero failures → `done`; any failures → `continue_work`. This structurally prevents false-positive completion: reaching terminal `done` always implies every DoD criterion was independently re-verified in the same iteration.

   **Hard vs. soft criteria**: Tag each criterion that must be technically verified with `[hard]` at the end of the line (e.g., `- [ ] Tests pass [hard]`). Leave criteria that depend on human decisions or environment state (e.g., "Working tree is clean", "PR approved") untagged — they are non-blocking once the pass rate threshold is met. Override `context.min_pass_rate` per run: `ll-loop run general-task --context min_pass_rate=1.0` to require 100% satisfaction.
5. **Continue** — `continue_work` handles only DoD remediation: when the plan is fully `[x]` but a DoD criterion remains unchecked, it appends a new remediation step to the plan, then routes to `select_step` so the new step goes through the full `select_step → do_work → verify_step → mark_done` chain normally. `continue_work` does not implement steps directly.

The loop runs up to 200 iterations and uses `on_handoff: spawn` to continue across session boundaries. Each plan step consumes approximately 6 iterations minimum (`select_step` + `do_work` + `verify_step` + `mark_done` + `check_done` + `count_done`), plus a one-time `resume_check` iteration at startup, supporting ~33 plan steps before the cap fires.

The `refine-to-ready-issue` loop uses configurable confidence thresholds (default: readiness > 90, outcome confidence > 75). Override per-run:

```bash
ll-loop run refine-to-ready-issue --context readiness_threshold=85 --context outcome_threshold=70
```

To apply project-wide defaults, set `commands.confidence_gate.readiness_threshold` / `outcome_threshold` in `ll-config.json`, then install the loop locally (`ll-loop install refine-to-ready-issue`) and update its `context:` block defaults.

**Three-stage threshold check**: After `confidence_check` runs, the loop evaluates scores in three sequential shell states rather than one combined check. This split lets the loop route failures differently depending on what went wrong:

1. `verify_scores_persisted` — asserts that `confidence_score` and `outcome_confidence` are non-null in frontmatter (i.e., `/ll:confidence-check` Phase 4 actually wrote scores via `ll-issues set-scores`). Failure routes to `failed` with a clear error message — a missing-score condition is a tool failure, not a refinement signal, and must not silently route to `breakdown_issue`.
2. `check_readiness` — compares `confidence_score` against `readiness_threshold`. Failure routes to `check_refine_limit` (more refinement can close a technical gap).
3. `check_outcome` — compares `outcome_confidence` against `outcome_threshold`. Failure routes through `check_decision_needed` → `check_missing_artifacts` → `breakdown_issue` (conditionally). `check_decision_needed` exits early (`done`) when `decision_needed: true` so the outer loop can invoke `/ll:decide-issue`. `check_missing_artifacts` exits early (`done`) when `missing_artifacts: true` so the outer loop's `triage_outcome_failure → check_missing_artifacts → run_wire` path can repair the gap — size-review solves scope, not specification completeness. Only when both flags are false does failure route to `breakdown_issue` (scope genuinely too large).

**Timeout recovery**: If `check_readiness` encounters an unexpected Python error, the loop falls back to `check_scores_from_file` — a deterministic recovery state that reads `confidence_score` and `outcome_confidence` directly from the issue's frontmatter via `ll-issues show --json`. If both scores meet the thresholds, the loop routes to `done`; otherwise it routes to `breakdown_issue`.

**Refine limit guard**: The loop enforces a **lifetime cap** on total `/ll:refine-issue` calls per issue across all loop runs. At the start of each run, the `check_lifetime_limit` state reads the issue's cumulative `refine_count` from `ll-issues refine-status --json` and compares it against `commands.max_refine_count` in `ll-config.json` (default: **5**, range: 1–20). If the cap is reached, the loop routes to `breakdown_issue` (invoking `/ll:issue-size-review`) rather than failing — a persistent readiness gap after multiple refinement passes signals a scope problem, not a content problem. To raise the limit, set `commands.max_refine_count` in your `ll-config.json`.

**API Adoption**

| Loop | Description |
|------|-------------|
| `adopt-third-party-api` | End-to-end API adoption pipeline — scrapes a vendor docs URL via `/ll:scrape-docs`, enumerates up to 7 significant endpoints/features, proves each via `ready-to-implement-gate`, and writes a citation-linked integration playbook to `docs/integration-<domain>.md`. Partial coverage (some targets refuted or exhausted) still produces a playbook with a top warning block listing unverified sections. |
| `ready-to-implement-gate` | Sub-loop primitive — given a list of external-API targets, proves each against the Learning-Test Registry via `/ll:explore-api`; routes `done` when all targets are proven, `blocked` when any are refuted or exhausted. Used as a child by `adopt-third-party-api` and `assumption-firewall`, but runnable standalone to gate any pre-implementation proof step. |
| `assumption-firewall` | Issue gating loop — extracts up to 7 external-API assumptions from an issue file via LLM, classifies each as testable (proven via `ready-to-implement-gate`) or untestable (recorded via `--assume` flag as `result: untested` in the Learning-Test Registry), and routes `done` (all testable proven), `blocked` (any testable refuted), or `no_external_deps` (no testable assumptions found). Use before starting implementation on issues that touch unfamiliar third-party APIs. |
| `integrate-sdk` | Proof-driven SDK integration — branches on existing usage (code branch) vs. greenfield (docs branch), enumerates up to 7 required API surfaces, proves each via `ready-to-implement-gate`, then scaffolds integration code with `# Verified: .ll/learning-tests/<slug>.md` citations. Blocks with a structured diagnosis if any surface is refuted or citations don't resolve to proven records. |
| `learning-tests-audit` | Registry health audit — scans the Learning Test Registry for stale records via a three-phase detection pipeline (installed-package enumeration → LLM-assisted package classification → PyPI/npm registry release-date comparison), bulk-marks stale records via `ll-learning-tests mark-stale`, and produces a four-section triage report (newly stale, already stale, refuted, open TODOs). Run at sprint start to surface registry maintenance items before they cause integration drift. |
| `proof-first-task` | Opt-in wrapper that gates any implementation loop on `assumption-firewall` — extracts external-API assumptions from an issue file, proves each against the Learning-Test Registry, then delegates to a caller-specified impl loop (default `general-task`). When no `issue_file` is given, skips the gate and runs the impl loop directly. |

Run:
```bash
ll-loop run adopt-third-party-api "https://manual.raycast.com/extensions"
# Scrapes docs → enumerates targets → proves each → writes docs/integration-manual-raycast-com.md

# Gate an issue against the LT registry before implementing
ll-loop run assumption-firewall --context issue_file=".issues/features/P2-FEAT-1234-my-feature.md"
# Extracts API assumptions → classifies testable/untestable → proves testable, records untestable via --assume → routes done/blocked/no_external_deps

# Prove a specific list of targets standalone
ll-loop run ready-to-implement-gate --context targets="stripe.PaymentIntent stripe.Webhook"
# Iterates targets → proves each via /ll:explore-api → routes done or blocked

# Scaffold a proof-backed SDK integration (auto-detects existing usage vs. greenfield)
ll-loop run integrate-sdk --context target="anthropic" --context goal="streaming completions with tool use"
# Scans for existing imports → enumerates surfaces → proves each → scaffolds src/integrations/anthropic.py
```

**Research & Knowledge**

| Loop | Description |
|------|-------------|
| `deep-research` | Iterative web research synthesis — generates search queries, performs web searches, evaluates sources, identifies coverage gaps, and produces a structured Markdown report with citations |
| `deep-research-arxiv` | Arxiv-only sibling of `deep-research` — constrains web search to `site:arxiv.org`, scores sources on relevance + recency (derived from arxiv submission date) instead of credibility, and emits an arxiv-ID-keyed sources table plus a `## BibTeX` section ready to drop into a `.bib` file |
| `rn-plan` | Recursive task planning with self-scoring rubric — accepts a natural language task description, generates a 8-dimension rubric (breadth, depth, complexity, clarity, consistency, logic_strategy, feasibility, testability, risk_mitigation), then iteratively researches and refines the plan until all dimensions reach VERY-HIGH |
| `rn-refine` | Recursive refinement loop for an existing plan document — accepts a path to a plan `.md` file, calibrates a 9-dimension rubric to the plan's current state, then iteratively researches and refines until all dimensions reach VERY-HIGH |

Run:
```bash
ll-loop run deep-research "What are the trade-offs of CRDT vs OT for collaborative editing?"

# Adjust depth (minimum search rounds) and coverage threshold:
ll-loop run deep-research "your research topic" \
  --context depth=5 \
  --context coverage_threshold_pct=90
```

The loop writes all artifacts to `.loops/research/<slug>/`:
- `report.md` — structured research report with executive summary, key findings, source table, and conclusion
- `knowledge-base.md` — accumulated findings with inline `[Source: <url>]` citations
- `coverage.md` — per-facet coverage scores (1–5 scale) updated each iteration
- `query-log.md` — all search queries issued, grouped by iteration

See [`## deep-research`](../reference/loops.md#deep-research) in the loop reference for context variables, state graph, and invocation details.

### `rn-plan` — Recursive Task Planning with Self-Scoring Rubric

**Technique**: Accepts a natural language task description, generates an initial plan outline and an 8-dimension rubric (breadth, depth, complexity, clarity, consistency, logic_strategy, feasibility, testability, risk_mitigation), then iterates: classify the most needed research type (NEEDS_FILES or NEEDS_WEB) → research → synthesize findings into the plan → score all 8 dimensions → loop until all dimensions reach VERY-HIGH or `max_iterations` is exhausted.

**When to use**: When you need a fully elaborated, implementable plan for a complex task before execution — especially when the task touches multiple files, external APIs, or requires tradeoff analysis. Produces `plan.md` (the refined plan) and `plan-rubric.md` (dimension scores) as primary artifacts. Use [`rn-plan-apo`](#rn-plan-apo--plan-quality-gradient-optimization) to iteratively improve the *planning prompt itself* using accumulated plan trees.

**Usage:**

```bash
ll-loop run rn-plan "build a rate-limiting middleware for the API"
```

**Context variables:**

| Variable | Default | Description |
|----------|---------|-------------|
| `task` | `""` | Task description (populated from positional CLI arg via `input_key: task`) |
| `run_dir` | runner-injected | Per-run artifact directory (`.loops/runs/rn-plan-{timestamp}/`); created automatically before the `init` state. Override with `--context run_dir=path/` to write to a fixed location. |

**Output artifacts** (written to `${context.run_dir}`):

| File | Description |
|------|-------------|
| `plan.md` | Primary output — the refined, multi-phase implementation plan |
| `plan-rubric.md` | 8-dimension scores (LOW/MEDIUM/HIGH/VERY-HIGH) with aggregate verdict |
| `research.md` | Accumulated file and web research findings |

**FSM flow:**

```
init             (shell: mkdir run_dir, touch plan.md / plan-rubric.md / research.md)
  → generate_rubric     (prompt: write initial outline + 8-dim rubric at LOW)
    → classify_research (prompt: emit NEEDS_FILES or NEEDS_WEB token)
      → route_files / route_web  (router: dispatch to file or web research branch)
        → research_files  (prompt: Read/Grep/Glob to inspect local code and files)
        → research_web    (prompt: WebSearch/WebFetch to gather external facts)
          → synthesize   (prompt: merge research.md findings into plan.md)
            → score      (prompt: rate all 8 dims; emit ALL_VERY_HIGH or ITERATE)
              on_yes (ALL_VERY_HIGH) → verify_score → report → done
              on_no  (ITERATE)       → classify_research  (next iteration)
```

### `rn-refine` — Recursive Refinement of an Existing Plan

**Technique**: Accepts a path to an existing plan `.md` file, copies it into a run directory, and calibrates a 9-dimension scoring rubric to the plan's **current** state (unlike `rn-plan`, which always initialises all dimensions at LOW). Then iterates: classify the most needed research type (NEEDS_FILES or NEEDS_WEB) → research → synthesize findings into the plan → score all 9 dimensions → loop until all reach VERY-HIGH or `max_iterations` is exhausted. A `verify_score` shell state reads the rubric file after the LLM emits `ALL_VERY_HIGH` to guard against hallucinated convergence signals.

**When to use**: When you already have a draft plan (from `rn-plan`, `/ll:iterate-plan`, or written manually) and want to iteratively improve it without starting from scratch. Produces an in-place improved `plan.md` alongside a `plan-rubric.md` and `research.md` in the per-run artifact directory (`${context.run_dir}`).

**Usage:**

```bash
ll-loop run rn-refine ".loops/runs/rn-plan-20260526T143022/plan.md"
```

**Context variables:**

| Variable | Default | Description |
|----------|---------|-------------|
| `plan_file` | `""` | Path to the existing plan `.md` file (populated from positional CLI arg via `input_key: plan_file`) |
| `run_dir` | runner-injected | Per-run artifact directory (`.loops/runs/rn-refine-{timestamp}/`); created automatically before the `init` state. Override with `--context run_dir=path/` to write to a fixed location. |

**Output artifacts** (written to `${context.run_dir}`):

| File | Description |
|------|-------------|
| `plan.md` | Working copy of the refined plan (kept for reference; the original file is updated in-place) |
| `plan-rubric.md` | 9-dimension scores (LOW/MEDIUM/HIGH/VERY-HIGH) with aggregate verdict |
| `research.md` | Accumulated file and web research findings |

**FSM flow:**

```
init             (shell: validate plan_file exists, copy to run_dir/plan.md)
  → assess_existing     (prompt: infer goal, score all 9 dims at ACTUAL current level)
    → classify_research (prompt: emit NEEDS_FILES or NEEDS_WEB token)
      → route_files / route_web  (router: dispatch to file or web research branch)
        → research_files  (prompt: Read/Grep/Glob to inspect local code and files)
        → research_web    (prompt: WebSearch/WebFetch to gather external facts)
          → synthesize   (prompt: merge research.md findings into plan.md)
            → score      (prompt: rate all 9 dims; emit ALL_VERY_HIGH or ITERATE)
              on_yes (ALL_VERY_HIGH) → verify_score → report → done
              on_no  (ITERATE)       → classify_research  (next iteration)
              on_error               → diagnose → failed
```

**Notes**: The key difference from `rn-plan` is `assess_existing` — it reads the plan and scores dimensions at their *actual* current level rather than defaulting all to LOW. This avoids wasting iterations refining dimensions that are already HIGH or VERY-HIGH. `verify_score` is a deterministic shell check that confirms `ALL_VERY_HIGH` appears in the rubric file before accepting convergence — guarding against hallucinated convergence where the LLM emits the sentinel but writes `ITERATE` to disk.

- **In-place update**: On completion, the loop overwrites the **original** plan file (the path passed to `ll-loop run rn-refine`) with the refined content. No manual copy from `.loops/` is needed. The `plan.md` under the run directory is kept as a working-copy reference you can diff against or delete.
- **Report state**: Prints `diff` commands comparing the original file against the working copy, so you can review changes before discarding the reference copy.

**Issue Management**

| Loop | Description |
|------|-------------|
| `backlog-flow-optimizer` | Iteratively diagnose the primary throughput bottleneck in the issue backlog |
| `evaluation-quality` | Multi-dimensional quality health check across issue quality, code quality, and backlog health; routes to remediation loops when thresholds are breached |
| `issue-discovery-triage` | Automated issue discovery and triage cycle |
| `scan-and-implement` | Full discovery → triage → implement pipeline. Snapshots active issue IDs, runs `issue-discovery-triage` as a sub-loop, then delegates to `autodev` scoped to **only** the net-new IDs that survived triage (issues that were created during scan but closed by tradeoff-review are excluded automatically via the pre/post snapshot diff) |
| `auto-refine-and-implement` | For each backlog issue in priority order: recursively refine via `recursive-refine` (which handles decomposition into child issues), run an adversarial go/no-go gate, then implement all passed issues; issues that fail the gate are skipped; loops until backlog is exhausted |
| `issue-refinement` | Progressively refine all active issues — delegates per-issue refinement to the `refine-to-ready-issue` sub-loop with commit cadence |
| `recursive-refine` | Refine one or more issues to readiness recursively; when size-review decomposes an issue into children, each child is enqueued and refined before the next sibling; accepts a single ID or comma-separated list |
| `autodev` | Targeted refine-and-implement for a specific set of issues; accepts a single ID or comma-separated list and interleaves refinement and implementation — as soon as a leaf passes refinement it is implemented via `ll-auto --only` before the next leaf is refined; decomposed children are prepended depth-first; terminates when the input queue drains |
| `prompt-across-issues` | Run an arbitrary prompt against every open/active issue sequentially; use `{issue_id}` placeholder in your prompt to inject each issue's ID. Optionally constrain to a single issue type via `--context type=BUG` (one of `BUG`, `FEAT`, `ENH`, `EPIC`). Optionally scope to children of an epic via `--context parent=EPIC-NNN`. Both filters may be combined. |
| `issue-staleness-review` | Find old issues, review relevance, and close or reprioritize stale ones |
| `sprint-build-and-validate` | Create a sprint from the backlog (or reuse an existing one via optional arg), refine, and execute |
| `sprint-refine-and-implement` | Like `auto-refine-and-implement` but scoped to a named sprint; processes issues in sprint YAML order, refining each recursively, running a go/no-go gate, then implementing |

### `sprint-build-and-validate` — Automated Sprint Creation and Validation

**Technique**: Selects up to `max_issues` open/active issues (P0–P1 first, then issues with no blocking dependencies), creates a sprint definition via `/ll:create-sprint --auto`, recursively refines all issues to confidence threshold, runs dependency mapping and conflict auditing, commits the validated sprint, executes it via `ll-sprint run`, and — on non-zero exit — reads `.sprint-state.json` to feed blocked/failed issues into `recursive-refine` for recovery.

**When to use**: When you want to go from a backlog to a running sprint in one automated pass, with dependency and conflict checks baked in. Pass an existing sprint name to skip creation and go straight to refinement. Prefer `ll-sprint run` directly if you already have a sprint defined, refined, and validated.

**Context variables:**

| Variable | Default | Description |
|----------|---------|-------------|
| `max_issues` | `8` | Maximum number of issues to include in the sprint |
| `sprint_name` | `""` | Optional: name of an existing sprint to reuse (skips creation) |

**Invocation:**
```bash
# Create a new sprint from the backlog
ll-loop run sprint-build-and-validate

# Reuse an existing sprint (skips creation, goes straight to refinement)
ll-loop run sprint-build-and-validate my-sprint-2026-05-05

# Limit new sprint to 5 issues
ll-loop run sprint-build-and-validate --context max_issues=5
```

**FSM flow:**
```
route_input → [sprint_name provided?]
  ├─ YES (name given, file found) → extract_sprint_issues → refine_issues → map_dependencies → …
  ├─ NO  (no name given)         → create_sprint → route_create → [sprint exists?]
  │                                   ├─ YES → extract_sprint_issues → refine_issues
  │                                   │           → map_dependencies → audit_conflicts
  │                                   │           → commit → run_sprint → [exit code?]
  │                                   │                       ├─ 0 (clean) → done
  │                                   │                       └─ non-zero  → extract_unresolved → refine_unresolved → done
  │                                   └─ NO  → create_sprint (retry)
  └─ ERROR (name given, file missing) → failed
```

**State timeouts:**

| State | Timeout | Notes |
|-------|---------|-------|
| `route_input` | — | Shell routing: if `sprint_name` is set, validates `.sprints/<name>.yaml` and jumps to `extract_sprint_issues`; if empty, routes to `create_sprint`; file-not-found routes to `failed` |
| `failed` | — | Terminal state; reached when a named sprint file does not exist |
| `create_sprint` | 300s | Headless `/ll:create-sprint --auto`; captures sprint name |
| `route_create` | — | Shell check: `ll-sprint list \| grep -q .`; retries if no sprint found; routes to `extract_sprint_issues` on success |
| `extract_sprint_issues` | 30s | Reads sprint YAML and emits comma-separated issue IDs; routes to `refine_issues` if issues found |
| `refine_issues` | — | Delegates to `recursive-refine` sub-loop via `context_passthrough: true` |
| `map_dependencies` | 300s | `/ll:map-dependencies --auto` grouped across all sprint issues |
| `audit_conflicts` | 300s | `/ll:audit-issue-conflicts --auto` grouped across all sprint issues |
| `commit` | 120s | `/ll:commit --auto` with standard sprint commit message |
| `run_sprint` | 21600s (6h) | `ll-sprint run <name>` — parallelized wave execution; routes on exit code |
| `extract_unresolved` | 30s | Reads `.sprint-state.json`; merges `failed_issues` + `skipped_blocked_issues`; emits comma-separated IDs |
| `refine_unresolved` | — | Delegates to `recursive-refine` sub-loop via `context_passthrough: true` |

**Notes**: The sprint YAML is committed before `ll-sprint run` begins, so it's durable if the session is interrupted. Global FSM timeout is 25200s (7h); `max_iterations: 16`; `on_handoff: spawn` continues across session boundaries during the sprint execution phase. Clean sprint exits (exit 0) route directly to `done`; non-zero exits trigger the `extract_unresolved` → `refine_unresolved` recovery path.

### `sprint-refine-and-implement` — Sprint-Scoped Refine-and-Implement Loop

**Technique**: Like `auto-refine-and-implement` but bounded to a named sprint. Reads `.sprints/<sprint_name>.yaml` and processes each issue in sprint YAML order: delegates `format → refine → wire → confidence-check` to the `recursive-refine` sub-loop (with automatic decomposition of oversized issues), runs `/ll:go-no-go` as an adversarial gate before implementation, then implements each issue that passed both refinement and the gate via `ll-auto --only`. Issues that fail refinement or are decomposed are recorded in a skip file; issues that receive a NO-GO verdict are skipped back to the queue without being implemented. Both categories are excluded from re-processing on resume.

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
  │           │           ├─ YES → implement_next → go_no_go (/ll:go-no-go --check --auto) → [GO?]
  │           │           │           ├─ YES → implement_issue (ll-auto --only) → implement_next (loop)
  │           │           │           └─ NO  → implement_next (skip, loop)
  │           │           └─ NO  → get_next_issue
  │           └─ NO  → skip_and_continue → get_next_issue
  └─ NO  → done
```

**Notes**: All tmp files are prefixed `sprint-refine-and-implement-*` to avoid state collision with `auto-refine-and-implement` when both loops are used in the same project. The loop uses `on_handoff: spawn` and `max_iterations: 500` with an 8-hour global timeout, so it can survive session boundaries for long sprints.

**Skip tracking**: When `recursive-refine` marks an issue as skipped (refinement failure or decomposition), it is written to `.loops/tmp/sprint-refine-and-implement-skipped.txt` — both for the current run and for any future resume of the same sprint. Decomposed parents are additionally marked `status: done` in frontmatter so they never re-appear as active candidates after a skip-file reset. On resume, `get_next_issue` reads the skip file and advances past any previously processed issues.

### `auto-refine-and-implement` — Full-Backlog Refine-and-Implement Loop

**Technique**: For each backlog issue in priority order, run `recursive-refine` as a sub-loop to bring it to ready status (with automatic decomposition of oversized issues into child issues). After refinement, all issues that passed are queued for sequential implementation; before each implementation, `/ll:go-no-go` runs as an adversarial gate — issues that receive a NO-GO verdict are skipped without being implemented. Decomposed parents are marked `status: done` in frontmatter and recorded in a skip list; failed or NO-GO issues are recorded in a skip list — all are excluded from subsequent `ll-issues next-issue` calls so the loop never retries a persistently failing issue.

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
         │         │         ├─ YES → implement_next → go_no_go (/ll:go-no-go --check --auto) → [GO?]
         │         │         │         ├─ YES → implement_issue (ll-auto --only) → implement_next (loop)
         │         │         │         └─ NO  → implement_next (skip, loop)
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
                    ├─ on_success → copy_broke_down → check_passed → [thresholds met?]
                    ├─ on_failure/on_error → skip_inflight → dequeue_next  (ENH-1679: sub-loop failed terminal or crash)
                    └─ on_no → dequeue_next  (sub-loop queue empty)
                    [on_success path continued below:]
                    → copy_broke_down → check_passed → [thresholds met?]
                         ├─ YES → decide_current → [decision_needed?]
                         │                            ├─ YES → run_decide (/ll:decide-issue --auto) → mark_decide_ran → rerun_confidence_after_decide → recheck_after_decide → [thresholds met?] → implement_current (ll-auto --only) → dequeue_next (on fail → snap_and_size_review → run_size_review → enqueue_or_skip)
                         │                            └─ NO  → implement_current (ll-auto --only) → dequeue_next
                         └─ NO  → triage_outcome_failure → [score_ambiguity ≤ 10?]
                                    ├─ YES → run_decide → mark_decide_ran → rerun_confidence_after_decide → recheck_after_decide → [thresholds met?] → implement_current → dequeue_next (on fail → snap_and_size_review → run_size_review → enqueue_or_skip)
                                    ├─ ERR → detect_children → [children found?]
                                    └─ NO  → check_missing_artifacts → [missing_artifacts=true?]
                                               ├─ YES → run_wire → run_refine → rerun_confidence_after_wire → enqueue_or_skip → dequeue_next
                                               └─ NO  → detect_children → [children found?]
                                                   ├─ YES → enqueue_children (prepend depth-first) → dequeue_next
                                                   └─ NO  → size_review_snap → check_broke_down → [broke_down AND children exist?]
                                                              ├─ YES → enqueue_or_skip → dequeue_next
                                                              └─ NO  → recheck_scores → [passed now?]
                                                                         ├─ YES → decide_current → [decision_needed?]
                                                                         │                            ├─ YES → run_decide → mark_decide_ran → rerun_confidence_after_decide → recheck_after_decide → [thresholds met?] → implement_current → dequeue_next (on fail → snap_and_size_review → run_size_review → enqueue_or_skip)
                                                                         │                            └─ NO  → implement_current → dequeue_next
                                                                         └─ NO  → check_decision_before_size_review → [decision_needed?]
                                                                                                                        ├─ YES → run_decide → mark_decide_ran → rerun_confidence_after_decide → recheck_after_decide → [thresholds met?] → implement_current → dequeue_next (on fail → snap_and_size_review → run_size_review → enqueue_or_skip)
                                                                                                                        └─ NO  → run_size_review → enqueue_or_skip → [children found?]
                                                                                                                         ├─ YES → dequeue_next
                                                                                                                         └─ NO  → recheck_after_size_review → [passed now?]
                                                                                                                                     ├─ YES → decide_current → [decision_needed?]
                                                                                                                                     │                            ├─ YES → run_decide → mark_decide_ran → rerun_confidence_after_decide → recheck_after_decide → [thresholds met?] → implement_current → dequeue_next (on fail → snap_and_size_review → run_size_review → enqueue_or_skip)
                                                                                                                                     │                            └─ NO  → implement_current → dequeue_next
                                                                                                                                     └─ NO  → dequeue_next
```

**Notes**: The loop runs up to 500 iterations with an 8-hour timeout and uses `on_handoff: spawn` to continue across session boundaries. Both `refine_current` (sub-loop) and `implement_current` (shell `ll-auto`) use the `with_rate_limit_handling` fragment (3 retries, 30s base backoff); `refine_current` on rate-limit exhaustion dequeues and continues, while `implement_current` on exhaustion terminates the loop via `done`. The broke-down handshake flag (written by `refine-to-ready-issue` to `.loops/tmp/recursive-refine-broke-down`) is copied into `.loops/tmp/autodev-broke-down` only on the `on_success` path (via `copy_broke_down`), so the rest of autodev's state machine reads only the `autodev-*` namespace. When `refine_current` exits via `on_failure` or `on_error`, the sub-loop's `failed` terminal or a signal/crash routes to `skip_inflight` instead — the issue is recorded in `.loops/tmp/autodev-skipped.txt` and the queue advances without passing an unrefined issue to `implement_current` (ENH-1679). This interleaved design also means partial forward progress is preserved if the run is interrupted — any leaves that already passed refinement have already been implemented.

**In-flight tracking** (BUG-1226): `dequeue_next` writes the popped issue ID to `.loops/tmp/autodev-inflight`; `enqueue_or_skip` clears it in the children-found branch; `recheck_after_size_review` clears it on the skip path (BUG-1230); `enqueue_children` clears it after decomposition; `init` resets it at loop start. On natural termination, `done` reads this flag and, if non-empty, prints a warning naming the issue that did not reach a clean resolution so the user knows to re-queue it. Pairs with the executor's pending-shell-state flush (see `docs/reference/EVENT-SCHEMA.md` `loop_complete` / `state_enter.flushed`) — between them, autodev no longer silently drops a breakdown result when the wall-clock timeout fires between `refine_current` returning and `copy_broke_down` executing.

**Outcome failure triage** (BUG-1277, ENH-1291, ENH-1415): When `check_passed` fails (confidence thresholds not met), the loop enters `triage_outcome_failure` rather than immediately routing to size-review. This state reads `score_ambiguity` from the issue frontmatter and branches: if `score_ambiguity ≤ 10`, the issue is well-scoped but has an unresolved design decision causing low outcome confidence — the loop routes to `run_decide` (invoking `/ll:decide-issue --auto`) → `mark_decide_ran` (sets `.loops/tmp/autodev-decide-ran` so decide does not re-fire later in the same iteration) → `rerun_confidence_after_decide` (invoking `/ll:confidence-check` to refresh stale pre-decision scores, BUG-1378) → `recheck_after_decide` (threshold gate). On gate pass, the loop proceeds to `implement_current` without decomposition. On gate fail (ENH-1415), the loop routes to `snap_and_size_review` (refreshes the pre-ids baseline) → `run_size_review` rather than dropping the issue, since the only outcome dimensions that can still drag the score below threshold after decide are Complexity and Change Surface — both decomposable. The decide-ran flag means that if size-review fails to decompose and `recheck_after_size_review` re-enters `decide_current`, that state short-circuits to `implement_current` rather than firing decide a second time. On parse error, the loop falls back safely to `detect_children`. Otherwise, the loop enters `check_missing_artifacts`, which reads the `missing_artifacts` frontmatter flag (set by `/ll:confidence-check` Phase 4.7 when Outcome Risk Factors mention absent files or unwired components): if `true`, the loop routes to `run_wire` (invoking `/ll:wire-issue --auto`) → `run_refine` (invoking `/ll:refine-issue --auto`) → `rerun_confidence_after_wire` (invoking `/ll:confidence-check` to refresh stale pre-repair scores, BUG-1491) → `enqueue_or_skip`; if `false`, the loop falls through to `detect_children → size_review`. This three-branch triage prevents incorrect decomposition of issues whose low outcome confidence stems from an unresolved design decision or a wiring gap rather than excessive scope.

### `scan-and-implement` — Discover, Triage, then Implement Net-New Issues

**Technique**: Full discovery-to-implementation pipeline composed from two existing sub-loops. Before discovery, snapshots the IDs of all currently-active issues to `.loops/tmp/scan-and-implement-pre-ids.txt`. Runs `issue-discovery-triage` as a sub-loop. After discovery, snapshots the post-discovery active-issue IDs and computes `comm -13` against the pre-snapshot — yielding only issues that are **net-new and still active** (i.e., they were created during scan **and** survived triage; issues that were created and then closed by tradeoff-review move to `.issues/completed/` and so naturally drop out of the diff). Passes the resulting ID list as `input` to the `autodev` sub-loop, which then refines and implements each one.

**When to use**: When you want to go from "scan the codebase for new work" to "implement everything that's worth doing" in a single hands-off pass. Pairs the breadth of `/ll:scan-codebase` / `issue-discovery-triage` with the depth-first implementation of `autodev`, but without `autodev`'s requirement that you already know the issue IDs.

**Invocation**:

```bash
ll-loop run scan-and-implement
```

Takes no `input` — discovery is the input.

**State graph**:

```
snapshot_pre → discover (sub-loop: issue-discovery-triage)
            → diff_issues (captures net-new IDs as ${captured.input.output})
                ├─ YES (new IDs) → implement (sub-loop: autodev with input=<id-list>) → done
                └─ NO (empty diff) → done
```

**Notes**: The loop runs up to 5 outer iterations with a 10-hour timeout and uses `on_handoff: spawn` to continue across session boundaries. Because both sub-loops (`issue-discovery-triage` and `autodev`) have their own iteration budgets, the outer cap of 5 mostly exists as a safety net — a typical run completes in a single outer iteration. If `diff_issues` returns an empty list (no new work survived triage), the loop short-circuits to `done` with a "nothing to implement" message rather than invoking `autodev` with an empty queue.
<!-- END TODO stub -->

### `recursive-refine` — Depth-First Issue Refinement with Decomposition

**Technique**: Accepts a single issue ID or a comma-separated list. For each issue, delegates `refine → wire → confidence-check` to the `refine-to-ready-issue` sub-loop. If the sub-loop exits without meeting thresholds, the loop checks whether `breakdown_issue` already ran inside the sub-loop (via the `recursive-refine-broke-down` flag). If so, `/ll:issue-size-review` is skipped and the loop proceeds directly to `enqueue_or_skip`; otherwise it runs `/ll:issue-size-review` explicitly. When child issues are detected, they are prepended to the queue depth-first and refined before the next sibling. Issues that cannot be decomposed further are recorded as skipped.

**Child detection**: Uses a two-step parent-verification filter to avoid picking up unrelated issues created concurrently. First, `comm -13` of the pre- and post-refinement ID snapshots is written to `recursive-refine-diff-ids.txt`. Each candidate ID is then checked: its issue file must contain `Decomposed from <PARENT_ID>` (the line written by `/ll:issue-size-review` when it creates child issues) before it is accepted into `recursive-refine-new-children.txt`. Issues that appear in the diff but lack this parent reference are silently ignored.

**When to use**: When you have one or more issues you want refined to ready status, including any children that get split off along the way. Prefer `issue-refinement` for full-backlog refinement; use `recursive-refine` when you want targeted, tree-aware refinement of a specific set of issues.

**Breakdown guard**: After `detect_children` finds no children from the sub-loop, a `check_broke_down` state reads the `.loops/tmp/recursive-refine-broke-down` flag **AND** checks that `.loops/tmp/recursive-refine-new-children.txt` is non-empty. If the flag is set **and** the children file is non-empty (meaning `breakdown_issue` ran and actually produced child issues), the loop skips `recheck_scores` and `run_size_review` and goes directly to `enqueue_or_skip`, preventing a duplicate size-review call. If the flag is set but no children were created (sub-loop's `/ll:issue-size-review --auto` returned analysis only), the loop falls through to `recheck_scores` / `run_size_review` so the outer loop gets its own chance to decompose — avoiding the silent-skip regression from BUG-1183.

**Score gate**: When `check_broke_down` passes (flag not set), a `recheck_scores` state checks whether the issue's current `confidence` and `outcome` scores already meet project thresholds. If both pass, the issue is recorded as passed and size-review is skipped entirely — avoiding unnecessary LLM cycles on already-ready issues.

**Required context variables**:

| Variable | Default | Description |
|----------|---------|-------------|
| `readiness_threshold` | `90` | Minimum confidence score for an issue to be considered ready (override via `commands.confidence_gate.readiness_threshold` in `ll-config.json`) |
| `outcome_threshold` | `75` | Minimum outcome confidence score (override via `commands.confidence_gate.outcome_threshold` in `ll-config.json`) |
| `max_refine_count` | `5` | Maximum `/ll:refine-issue` calls per issue lifetime; enforced directly by `check_attempt_budget` before each sub-loop entry — issues that reach this cap are skipped with reason `budget` (override via `commands.max_refine_count` in `ll-config.json`) |
| `max_depth` | `3` | Maximum decomposition depth per subtree; issues at or beyond this depth are skipped with reason `depth-cap` instead of being passed to size-review (override via `commands.recursive_refine.max_depth` in `ll-config.json`) |
| `tree_summary` | `true` | When `true` (default), the `done` state renders an indented decomposition tree after the flat summary; set to `false` to suppress the block for noisy multi-root runs |

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
  ├─ YES → aggregate_decomposition → done (prints summary)
  └─ NO  → check_attempt_budget → [budget ok?]
              ├─ NO  (budget exceeded) → dequeue_next (skip)
              └─ YES → capture_baseline → run_refine (sub-loop: refine-to-ready-issue)
              ├─ on_success → check_passed → [thresholds met?]
              │                ├─ YES → dequeue_next (loop)
              │                └─ NO  → detect_children
              └─ on_failure/on_error → detect_children → [children found from sub-loop?]
                                        ├─ YES → enqueue_children → dequeue_next (depth-first)
                                        └─ NO  → size_review_snap → check_broke_down → [broke_down AND children exist?]
                                                                                        ├─ YES (flag=1 AND children) → enqueue_or_skip → dequeue_next
                                                                                        └─ NO  (flag=0 OR no children) → recheck_scores → [scores pass?]
                                                                                                                            ├─ YES → dequeue_next
                                                                                                                            └─ NO  → check_depth → [depth >= max_depth?]
                                                                                                                                        ├─ YES (depth-cap) → dequeue_next
                                                                                                                                        └─ NO  → check_decision_needed → [decision_needed?]
                                                                                                                                                      ├─ YES → dequeue_next (skipped: decision-needed)
                                                                                                                                                      └─ NO  → run_size_review → enqueue_or_skip → dequeue_next
```

**Summary output**: When the queue is exhausted, `aggregate_decomposition` emits the parent→children rollup (if any decompositions occurred), then `done` emits a structured summary followed (by default) by an indented decomposition tree:
```
Decomposed (1):
  ENH-99 → [FEAT-42, BUG-17] (1 passed, 1 not passed)

=== Recursive Refine Summary ===

Passed       (2): FEAT-42, FEAT-43
Decomposed   (1): ENH-99
Dead-ends    (1): BUG-17
Depth-cap    (0): none
Cycle        (1): ENH-100
Budget       (1): ENH-101
Decision     (0): none

=== Decomposition Tree ===

ENH-99 [decomposed]
  ├── FEAT-42 (passed, conf=92, outcome=78)
  └── BUG-17 [decomposed]
      ├── FEAT-43 (passed, conf=95, outcome=82)
      └── ENH-100 (skipped: cycle)
ENH-101 (skipped: budget)
```
Set `tree_summary: false` in context to suppress the tree block.

**Progress output**: On every dequeue, `dequeue_next` emits a real-time progress line to stderr:
```
[3/9] → ENH-1234 (depth: 0) | passed: 2 | queued: 5 | skipped: 1
```
The counters reflect cumulative totals at the moment of dequeue: position `N/total-enqueued`, the issue ID and depth, and running passed/queued/skipped tallies. After every `enqueue_children` or `enqueue_or_skip` enqueue, a queue-peek line shows the next 3–5 IDs waiting in the queue so you can see what the loop will process next without waiting for individual dequeue lines.

**Notes**: The loop runs up to 500 iterations with an 8-hour timeout and uses `on_handoff: spawn` to continue across session boundaries. All non-passing issue IDs are aggregated in `.loops/tmp/recursive-refine-skipped.txt` (read by outer-loop callers); decomposed parents are also marked `status: done` in frontmatter so they never re-appear as active candidates after a skip-file reset; issues that passed thresholds are in `.loops/tmp/recursive-refine-passed.txt`; the per-issue breakdown guard flag is in `.loops/tmp/recursive-refine-broke-down`; per-issue depth tracking is in `.loops/tmp/recursive-refine-depth-map.txt` (`<ID> <depth>` pairs for all enqueued issues); the depth of the currently-processing issue is in `.loops/tmp/recursive-refine-current-depth.txt`; issues skipped due to the depth cap are recorded separately in `.loops/tmp/recursive-refine-skipped-depth.txt`; every dequeued ID is appended to `.loops/tmp/recursive-refine-visited.txt` (cycle-detection guard); issues skipped because all proposed children were already visited are additionally recorded in `.loops/tmp/recursive-refine-skipped-cycle.txt`; per-issue attempt counts are tracked in `.loops/tmp/recursive-refine-attempts.txt` (one ID per line, appended each pass); issues skipped due to the per-issue budget cap are recorded in `.loops/tmp/recursive-refine-skipped-budget.txt`; parents that were decomposed into children (by either `enqueue_children` or the `enqueue_or_skip` children branch) are recorded in `.loops/tmp/recursive-refine-skipped-decomposed.txt`; issues with no further decomposition possible are recorded in `.loops/tmp/recursive-refine-skipped-deadend.txt`; issues skipped because `decision_needed: true` was set are recorded in `.loops/tmp/recursive-refine-skipped-decision.txt` (also merged into the shared `recursive-refine-skipped.txt`) and labeled `(skipped: decision-needed)` in the decomposition tree — run `/ll:decide-issue` on each to resolve the ambiguity, then re-run `recursive-refine`; every decomposition event (from either the `enqueue_children` or `enqueue_or_skip` path) is appended to `.loops/tmp/recursive-refine-decomposition.tsv` (columns: `parent_id`, `child_ids` (comma-joined), `decomposer` (`sub-loop` | `size-review`), `timestamp`) so the `aggregate_decomposition` state can produce a parent→children rollup at the end of each run.

**Code Quality**

| Loop | Description |
|------|-------------|
| `context-health-monitor` | Monitor context health via scratch file accumulation and session log size; compacts scratch files and archives stale outputs when pressure is detected |
| `dead-code-cleanup` | Find dead code, remove high-confidence items, and verify tests pass |
| `docs-sync` | Verify documentation matches the codebase and check for broken links |
| `fix-quality-and-tests` | Sequential quality gate: lint + format + types must be clean before tests run |
| `incremental-refactor` | Decompose a refactoring goal into safe atomic steps, execute each with test-gated commits, rollback and re-plan on failure |
| `test-coverage-improvement` | Measure test coverage, identify uncovered code paths, write tests for highest-risk gaps, and converge when coverage target is met |
| `worktree-health` | Continuous monitoring of orphaned worktrees and stale branches from both `ll-parallel` workers and `ll-loop --worktree` runs |

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
  --context scratch_dir=.loops/tmp
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
| `outer-loop-eval` | Analyze a target loop by loading its YAML definition, executing it as a sub-loop, then delegating to `/ll:debug-loop-run` and `/ll:audit-loop-run` to produce a structured improvement report |

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

**Notes**: Each state has `max_retries: 2` with `on_retry_exhausted: diagnose`. Use `ll-loop install agent-eval-improve` to copy the YAML to `.loops/` and customize scoring logic or add domain-specific evaluation steps.

**Benchmark scoring opt-in (FEAT-1245)**: `agent-eval-improve` ships with optional `run_benchmark` states from `lib/benchmark.yaml` that can replace the default LLM-scored `score_results` step with a Harbor-format scorer command. Install the loop (`ll-loop install agent-eval-improve`) and set `use_benchmark: true` with a `benchmark_scorer` context variable pointing to your scorer command to activate the numeric score path. This is useful when you have a deterministic evaluation harness (e.g., unit tests, exact-match checks) rather than LLM-graded task results.

**Automatic Prompt Optimization (APO)**

| Loop | Description |
|------|-------------|
| `apo-beam` | Beam search prompt optimization — generate N variants, score all, advance the winner |
| `apo-contrastive` | Contrastive APO — generate N variants → score comparatively → select best → repeat |
| `apo-feedback-refinement` | Feedback-driven APO — generate → evaluate → refine until convergence |
| `apo-opro` | OPRO-style prompt optimization — history-guided proposal until convergence |
| `apo-textgrad` | TextGrad-style prompt optimization — test on examples, compute failure gradient, apply refinement |
| `rn-plan-apo` | Plan-quality gradient optimization for the `rn-plan` recursive planner — scores plan trees on four plan-quality dimensions and refines the planning prompt via text gradient until `target_plan_quality` is reached |
| `examples-miner` | Co-evolutionary corpus mining — harvest completed issue sessions, quality-gate, calibrate difficulty band, synthesize adversarial examples; runs `apo-textgrad` as a child loop |
| `prompt-regression-test` | CI for prompts — run a prompt suite, score against baseline, flag regressions, and trigger APO repair when quality drops |

**Harness Examples**

| Loop | Description |
|------|-------------|
| `harness-single-shot` | Annotated single-shot harness example — all evaluation phases with commented-out optional gates |
| `harness-multi-item` | Annotated multi-item harness example — all five evaluation phases active over a discovered item list |
| `harness-optimize` | Score-gated hill-climbing on harness artifacts (skills, commands, CLAUDE.md) — proposes edits, benchmarks, commits accepted mutations; stops on first stall. Supports `.ll/program.md` for overnight runs. Also supports **state mode**: set `targets` to a loop YAML with a `targets.states` list to optimize individual state `action:` blocks independently. |
| `html-anything` | Generalized HTML artifact harness — classifies artifact type (email, social card, résumé, dashboard, etc.) from a description, writes a platform-specific brief and dynamic scoring rubric, then iteratively generates and refines `index.html` via Playwright CLI |
| `hitl-compare` | Human-in-the-loop comparison harness — reads whitespace-separated inputs (file paths or raw text), extracts candidate review items with 2+ options, prunes implementation-level micro-decisions, and generates a self-contained interactive HTML page with comparison controls, write-in custom options, and an "Export selections" affordance |
| `hitl-md` | Human-in-the-loop single-document review harness — reads a markdown file (or raw text), decomposes it into GP-TSM saliency-modulated segments enriched with multi-channel saliency (importance / anomaly / claim_type / confidence) and length-normalized credibility flags, and generates a self-contained interactive HTML page with sensemaking enhancements (staged highlighting, density slider, schema-switching, canvas minimap, calibrated friction), click/focus-triggered popover edit controls (delete / insert-before / insert-after / inline-edit / flag-for-AI), a "Copy AI prompt" control for flagged segments, and a "Copy updated markdown" reconstruction control. All styles source from design token CSS custom properties. Final HTML is copied to `./hitl-md-review.html` in the run directory for quick access. |
| `html-website-generator` | Generator-evaluator harness for single-page HTML website creation — accepts a one-line description and iteratively generates, screenshots, and refines HTML/CSS/JS via Playwright CLI |
| `svg-image-generator` | Generator-evaluator harness for SVG icon and illustration creation — accepts a one-line description and iteratively generates, screenshots, and refines a self-contained SVG via Playwright CLI |
| `svg-textgrad` | TextGrad-style SVG harness — optimizes the visual brief via structured gradient updates (FAILURE_PATTERN → ROOT_CAUSE → GRADIENT) rather than feeding raw critique to the generator; accumulates gradient history for repeated-failure escalation |
| `p5js-sketch-generator` | Generator-evaluator harness for p5.js creative coding sketches — multi-frame screenshots at deterministic frameCounts evaluate motion, not just composition; GAN-style architecture with p5.js loaded from CDN |
| `pixi-data-viz` | Generator-evaluator harness for animated PixiJS data visualizations — embeds synthetic-but-plausible data inline; hard-gates `encoding_clarity` at threshold 7; evaluates whether motion aids comprehension |
| `pixi-generative-art` | Generator-evaluator harness for PixiJS generative art sketches — GPU-accelerated idioms (filters, blend modes, container hierarchies); rewards Pixi-distinctive patterns over p5.js conventions |
| `loop-specialist-eval` | Behavioral eval harness for the `loop-specialist` agent — drives the agent against a seeded `broken-verify-loop.yaml` fixture (ambiguous-output failure mode) and verifies that the diagnosis artifact is written and the failure mode is correctly classified |
| `adversarial-redesign` | Generator-vs-critic figure refinement demo using AutoFigure — a generator produces an SVG from a text concept, a critic returns structured complaints, the loop regenerates addressing each complaint and exits on score-improvement stall or SVG-diff convergence. Every round is persisted for demo playback. **Requires**: `pip install -e ./AutoFigure && playwright install chromium` + `OPENROUTER_API_KEY`. Example: `ll-loop run adversarial-redesign --input concept="how a transformer attends"` |

For background on the GAN-style generator-evaluator architecture used by `html-website-generator`, `svg-image-generator`, `svg-textgrad`, `p5js-sketch-generator`, `pixi-data-viz`, and `pixi-generative-art`, see the [Harness Design for Long-Running Apps](../claude-code/harness-design-long-running-apps.md) reference.

> **Design rule: Playwright failure routing.** In any harness that uses Playwright for screenshot capture, route the `evaluate` state's `on_no` and `on_error` to the `score` state (LLM-only evaluation) — never back to `generate`. Routing to `generate` creates an infinite cycle: `generate` routes unconditionally back to `evaluate`, which fails again, repeating until `max_iterations` is exhausted with zero useful output. Routing forward to `score` lets the evaluator assess the HTML source directly and produce actionable critique even when no screenshot is available. After ENH-1869, these states (`evaluate`, `score`) live inside `oracles/generator-evaluator`; the rule applies to the oracle's internal state machine, not the calling thin-wrapper loops.

### `html-anything` — Generalized HTML Artifact Harness

> **Prerequisites**: [Playwright CLI](https://playwright.dev/) must be installed (`npm install -g playwright && npx playwright install chromium`, or `pip install playwright && playwright install chromium`).

**Technique**: Extends the GAN-style pattern from `html-website-generator` by treating artifact type as a runtime variable rather than a hardcoded assumption. The `plan` state atomically classifies the artifact type from the natural language description, writes a platform-specific `brief.md`, and writes a dynamic `rubric.md` with 4–6 artifact-appropriate criteria and per-criterion thresholds. The `score` state reads `rubric.md` at runtime to load those thresholds — preventing strong aesthetic scores from masking broken platform constraints (e.g. an HTML email with beautiful design but CSS classes instead of inline styles still fails). `pass_threshold` is set to 7 (vs SVG's 6) because platform constraints are binary.

**Supported artifact types**: `html-email`, `html-social-card`, `html-presentation`, `html-resume`, `html-invoice`, `html-dashboard`, `html-component`, `html-poster`, `html-website`

**When to use**: When you need a polished HTML artifact other than a generic website — especially when platform constraints are binary (inline styles for email clients, exact dimensions for social cards, print safety for résumés). For a plain website, `html-website-generator` is simpler; `html-anything` is the right choice when the artifact type determines the evaluation criteria.

**Usage:**

```bash
ll-loop run html-anything "a transactional email confirming a SaaS subscription"
ll-loop run html-anything "a 1200x630 open graph card for a developer tool"
ll-loop run html-anything "a single-page résumé for a senior software engineer"
ll-loop run html-anything "a dashboard showing real-time server metrics"
```

**Context variables:**

| Variable | Default | Description |
|----------|---------|-------------|
| `description` | (from `loop_input`) | Natural language artifact description — passed as the positional argument |
| `run_dir` | runner-injected | Per-run artifact directory (`.loops/runs/html-anything-{timestamp}/`) containing `index.html`, `brief.md`, `rubric.md`, `critique.md`, and `screenshot.png`; created automatically. Override with `--context run_dir=path/`. |
| `design_tokens_context` | runner-injected | Resolved semantic design-token values (empty string when `design_tokens.enabled: false` or tokens path is missing). |
| `pass_threshold` | `7` | Minimum score per criterion (1–10); **all criteria** must meet their individual rubric thresholds |

Override per-run:

```bash
ll-loop run html-anything "SaaS subscription email" \
  --context pass_threshold=8
```

**FSM flow:**

```
init → plan → generate → evaluate
                            ├─ CAPTURED → score
                            │              ├─ ALL_PASS → done
                            │              ├─ ITERATE  → generate (with critique)
                            │              └─ ERROR    → diagnose → failed
                            └─ FAILED  → score (Playwright unavailable — LLM-only scoring)
```

**Dynamic rubric examples:**

For `html-email`:

| Criterion | Weight | Threshold | What it checks |
|-----------|--------|-----------|----------------|
| `inline_styles` | 2× | 8 | All styles inline on elements — no `<style>` blocks or external CSS |
| `table_layout` | 2× | 7 | Table-based layout compatible with major email clients (no flexbox/grid) |
| `visual_identity` | 1× | 6 | Distinctive color palette, readable typography, branded feel |
| `content_clarity` | 1× | 6 | Key information (amount, action, details) immediately visible |

For `html-social-card`:

| Criterion | Weight | Threshold | What it checks |
|-----------|--------|-----------|----------------|
| `dimensional_accuracy` | 2× | 8 | Renders at exactly 1200×630px (or 1080×1080px square) with all content in safe zone |
| `visual_hierarchy` | 2× | 7 | Title/subtitle/CTA hierarchy, readable at thumbnail scale |
| `brand_identity` | 1× | 6 | Distinctive color palette, consistent with described brand |
| `craft` | 1× | 6 | Typography, spacing, color harmony, contrast ratios |

**Notes:**
- The `plan` state classifies artifact type atomically with brief + rubric — all three are written in one state to ensure the rubric always matches the classification.
- Per-criterion thresholds (not a weighted average) are enforced in `score`: a platform constraint at threshold 8 can't be masked by a high aesthetic score at threshold 6.
- If Playwright is unavailable, the `evaluate` state's `on_error` route falls back to `score` directly for LLM-only evaluation of the HTML source.
- The loop runs up to 20 iterations with a 2-hour timeout (`max_iterations: 20`, `timeout: 7200`).
- For a plain website, `html-website-generator` is simpler (no artifact classification step). Use `html-anything` when the artifact type determines which platform constraints to enforce.
- To customize criteria for a specific artifact type, install locally (`ll-loop install html-anything`) and edit the `plan` state's rubric design rules.

### `hitl-compare` — Human-in-the-Loop Comparison Harness

> **Prerequisites**: [Playwright CLI](https://playwright.dev/) must be installed (`npm install -g playwright && npx playwright install chromium`, or `pip install playwright && playwright install chromium`). Playwright is used for screenshot evaluation but is optional — the loop degrades gracefully to LLM-only scoring when Playwright is unavailable.

**Technique**: Implements a novel `identify → prune → generate` pipeline before the standard GAN-style `evaluate → score` loop. The `identify` state resolves each whitespace-separated input token (file path or raw text) and extracts all candidate review items (decisions, design choices, requirement variants, document versions). The `prune` state filters out implementation-level micro-decisions that the normal planning pipeline (`/ll:refine-issue`, `/ll:wire-issue`, `/ll:decide-issue`) should resolve, surfacing only items where human taste or strategic preference is the appropriate deciding signal. The `generate` state then produces a single self-contained HTML page with per-item comparison controls, a write-in custom option field for each item (so reviewers can enter a choice not listed), and an "Export selections" affordance. The `score` state evaluates a 5-criterion rubric (clarity, scannability, comparison_ergonomics, export_affordance, inline_constraint) with per-criterion thresholds.

**When to use**: After running `/ll:refine-issue` on a batch of issues where several emerge with `decision_needed: true` and 2–3 viable options each. Also useful for design review (plan markdown + raw-text design alternatives) or any situation where multiple open choices need a focused human review surface rather than a long back-and-forth chat thread.

**Usage:**

```bash
# Review issues with decision_needed: true
ll-loop run hitl-compare ".issues/features/P2-FEAT-A.md .issues/features/P2-FEAT-B.md"

# Mixed input: a plan plus raw text describing design alternatives
ll-loop run hitl-compare "thoughts/shared/plans/2026-05-17-auth-plan.md 'Option A: JWT tokens stored in httpOnly cookie. Option B: Opaque tokens stored server-side.'"

# Pruning check: implementation-heavy input should reduce to zero or few items
ll-loop run hitl-compare ".issues/bugs/P1-BUG-100-implementation-details.md"
```

**Context variables:**

| Variable | Default | Description |
|----------|---------|-------------|
| `inputs` | (from `loop_input`) | Whitespace-separated file paths or raw text tokens — passed as the positional argument |
| `run_dir` | runner-injected | Per-run artifact directory (`.loops/runs/hitl-compare-{timestamp}/`) containing `index.html`, `items.md`, `review.md`, `critique.md`, and `screenshot.png`; created automatically. Override with `--context run_dir=path/`. |
| `design_tokens_context` | runner-injected | Resolved semantic design-token values (empty string when `design_tokens.enabled: false` or tokens path is missing). |

**FSM flow:**

```
init → identify → prune → generate → evaluate
                                         ├─ CAPTURED → score
                                         │              ├─ ALL_PASS → done
                                         │              ├─ ITERATE  → generate (with critique)
                                         │              └─ ERROR    → failed
                                         └─ FAILED  → score (Playwright unavailable — LLM-only scoring)
```

**Using the generated page:**

1. Open `<run_dir>/index.html` in your browser (`file://` URL — no server needed).
2. Toggle through the comparison controls to select your preferred option for each item.
3. Click **Export Selections** to generate a copy-pasteable markdown block.
4. Paste the block into your coding agent chat: `"Apply these review selections: [paste]"`.

**Notes:**
- The `prune` state logs every pruned item and its reason in `review.md` for traceability — you can audit what was excluded and why.
- If all items are pruned (nothing to review), the generated HTML page reports this clearly; no human selections are needed.
- The `evaluate` state's `on_no`/`on_error: score` routing means Playwright absence falls back to LLM-only `score` judgment — the loop runs end-to-end even without a browser installed.
- The loop runs up to 20 iterations with a 2-hour timeout (`max_iterations: 20`, `timeout: 7200`).
- To customize the scoring rubric, install locally (`ll-loop install hitl-compare`) and edit the `score` state's criteria and thresholds.
- **Image embedding**: When an option's `source_path` points to an image file (`.png`, `.jpg`, `.gif`, `.webp`, `.svg`), the `generate` state converts it to a base64 data URI and embeds it inline in the HTML. This avoids broken-image icons under `file://` URLs (browsers block `file://` paths in `<img src>`). The `evaluate` rubric's `inline_constraint` criterion treats external `src=` attributes as a violation. Text-only items render without images — no broken `<img>` tags are emitted.

### `hitl-md` — Human-in-the-Loop Single-Document Review Harness

> **Prerequisites**: [Playwright CLI](https://playwright.dev/) must be installed (`npm install -g playwright && npx playwright install chromium`, or `pip install playwright && playwright install chromium`). Playwright is used for screenshot evaluation but is optional — the loop degrades gracefully to LLM-only scoring when Playwright is unavailable.

**Technique**: Implements a `segment → generate → finalize` pipeline before the standard GAN-style `evaluate → score` loop. The `segment` state resolves the input token (file path or raw text) and applies the **GP-TSM (Grammar-Preserving Text Saliency Modulation)** algorithm inline as LLM instructions — no external Python/ML dependencies. It identifies grammar-preserving segment boundaries (sentence/clause level, treating headings, bullets, and code blocks as atomic), assigns saliency scores (0.0–1.0), a per-segment `channels` object (importance / anomaly / claim_type / confidence), a `length_normalized` flag, and an accessible color palette per content type, and writes `segments.json`. The `generate` state then produces a single self-contained HTML review page that renders the document with its natural markdown flow (headings, paragraphs, lists, code blocks in their usual shape), with each segment wrapped in a `<span class="seg">` carrying low-alpha inline background highlights keyed to saliency. On top of the base review surface, the page layers six **sensemaking enhancements** (ENH-1770): **staged dynamic highlighting** (top 3–5 segments highlighted immediately, the rest fade in via `IntersectionObserver` as the user scrolls), an **adaptive density slider** that filters which segments receive the highlight tint, **multi-channel saliency** with toggle controls for importance / anomaly / claim_type / confidence channels, a **schema-switching toolbar** that re-groups content by saliency tier or claim type or anomaly score, a fixed-position **canvas minimap + State Rail** with `localStorage`-backed visit heatmap, and **calibrated friction** (confidence badges rendered before segment content, click-to-reveal gating on high-saliency low-confidence claims, length-normalized credibility markers) gated by a "Trust calibration" toggle. All feature styles are sourced from design token CSS custom properties (`var(--…)`) injected via `${context.design_tokens_context}`. The five edit controls (delete / insert-before / insert-after / inline-edit / flag-for-AI) appear as a popover triggered by clicking or focusing a segment — controls overlay the document without causing reflow. A "Copy AI prompt" control aggregates all flagged segments, and a "Copy updated markdown" control reconstructs the full document from the live segment list. The `finalize` state copies the approved HTML to `./hitl-md-review.html` in the cwd. The `score` state evaluates a 13-criterion rubric (`document_readability`, `inline_highlighting`, `affordance_overlay`, `keyboard_reachability`, `inline_constraint`, `markdown_reconstruction`, `staged_highlighting`, `density_control`, `multi_channel_saliency`, `schema_switching`, `minimap_state_rail`, `trust_calibration`, `design_token_consistency`) with per-criterion thresholds; the compound `ALL_PASS` token is the gate.

> **Evaluate routing note**: The `evaluate` state's `on_error` routes to `generate` (not `score`), deliberately diverging from the standard LOOPS_GUIDE.md design rule at line 897 ("never back to generate"). Playwright errors here typically indicate the HTML itself is malformed — regenerating is preferable to scoring a broken page. This follows the `svg-image-generator.yaml` precedent. The `on_no` route (Playwright unavailable) still goes to `score` for LLM-only fallback per the standard pattern.

**When to use**: After running `/ll:recursive-refine` or a planning skill to produce a long PRD or implementation plan markdown file. Rather than reviewing linearly in an editor, run `hitl-md` to get a focused segment-level review surface. Also useful for reviewing AI-generated research notes, design documents, or refined issues where you want to flag specific spans for targeted AI revision without losing positional context.

**Usage:**

```bash
# Review a plan or PRD file
ll-loop run hitl-md "thoughts/shared/plans/2026-05-18-FEAT-1613-management.md"

# Review raw markdown text
ll-loop run hitl-md "# My Plan\n\nThis is the first paragraph..."

```

**Context variables:**

| Variable | Default | Description |
|----------|---------|-------------|
| `input` | (from `loop_input`) | File path or raw markdown text — passed as the positional argument |
| `run_dir` | runner-injected | Per-run artifact directory (`.loops/runs/hitl-md-{timestamp}/`) containing `index.html`, `segments.json`, `critique.md`, and `screenshot.png`. The final approved `index.html` is also copied to `./hitl-md-review.html` in the cwd. Override with `--context run_dir=path/`. |
| `design_tokens_context` | runner-injected | Resolved semantic design-token values (empty string when `design_tokens.enabled: false` or tokens path is missing). |

**FSM flow:**

```
init → segment → generate → evaluate
                                ├─ CAPTURED → score
                                │              ├─ ALL_PASS → finalize → done
                                │              ├─ ITERATE  → generate (with critique)
                                │              └─ ERROR    → failed
                                ├─ FAILED  → score (Playwright unavailable — LLM-only scoring)
                                └─ ERROR   → generate (HTML malformed — regenerate)
```

**Using the generated page:**

1. Open `./hitl-md-review.html` (copied to your cwd) or `<run_dir>/index.html` in your browser (`file://` URL — no server needed).
2. Navigate segment by segment using Tab, arrow keys, or mouse click. Segments render with inline saliency highlights in the natural document flow.
3. Click or focus a segment to reveal the popover edit controls: 🗑 Delete, ↑+ Insert before, +↓ Insert after, ✏ Edit, 🚩 Flag for AI. Controls appear as an overlay and dismiss without document reflow.
4. When 1+ segments are flagged, click **Copy AI prompt** at the top — paste the copied prompt into your coding agent chat for targeted revision of those specific spans.
5. After all edits and AI-assisted revisions, click **Copy updated markdown** at the bottom to reconstruct the full document and paste it back over the source file.

**Notes:**
- GP-TSM segmentation is implemented as LLM-in-prompt instructions — no PyPI or subprocess dependencies required, consistent with all other built-in loops.
- The `segment` state enforces lossless reconstruction: every character of the original document must appear in exactly one segment's `markdown_source`, so "Copy updated markdown" is always lossless for unmodified segments.
- The `evaluate` state's `on_error: generate` routing means Playwright crashes or malformed-HTML errors trigger an HTML regeneration pass rather than scoring a broken artifact.
- The loop runs up to 20 iterations with a 2-hour timeout (`max_iterations: 20`, `timeout: 7200`).
- To customize the scoring rubric, install locally (`ll-loop install hitl-md`) and edit the `score` state's criteria and thresholds.

### `html-website-generator` — GAN-Style Website Design Loop

> **Prerequisites**: [Playwright CLI](https://playwright.dev/) must be installed (`npm install -g playwright && npx playwright install chromium`, or `pip install playwright && playwright install chromium`).

**Technique**: Implements the generator-evaluator architecture described in Anthropic's [harness design article](../claude-code/harness-design-long-running-apps.md). The loop runs four states in sequence: a **planner** expands the one-line description into an opinionated design brief (color palette, layout, unique angle, anti-patterns to avoid); a **generator** writes a self-contained HTML/CSS/JS file; an **evaluator** uses Playwright CLI to screenshot the rendered page via `file://` URL (no HTTP server required); and a **scorer** judges the screenshot against four weighted criteria, routing back to the generator with structured critique until all scores clear `pass_threshold`; and a **smoke test** state runs Playwright-powered functional checks (JS console errors, content presence) to verify the artifact before accepting it.

**When to use**: When you want rapid, fully-automated iterations on a single-page design without setting up a build pipeline. The `file://` approach means the loop works offline with no server lifecycle to manage. For multi-page apps or server-side rendering, adapt the `evaluate` state to use a local HTTP server instead.

**Usage:**

```bash
ll-loop run html-website-generator "a landing page for a Dutch art museum"
```

**Context variables:**

| Variable | Default | Description |
|----------|---------|-------------|
| `description` | (from `loop_input`) | Natural language website description — passed as the positional argument |
| `run_dir` | runner-injected | Per-run artifact directory (`.loops/runs/html-website-generator-{timestamp}/`) for `index.html`, `brief.md`, `critique.md`, and `screenshot.png`; created automatically. Override with `--context run_dir=path/`. |
| `design_tokens_context` | runner-injected | Resolved semantic design-token values (empty string when `design_tokens.enabled: false` or tokens path is missing). |
| `pass_threshold` | `6` | Minimum score per criterion (1–10); **all four** criteria must clear this value |

Override per-run:

```bash
ll-loop run html-website-generator "museum landing page" \
  --context pass_threshold=7
```

**FSM flow:**

```
plan → generate → capture
                     ├─ CAPTURED → score
                     │              ├─ ALL_PASS → smoke_test
                     │              │              ├─ SMOKE_PASS → done
                     │              │              └─ FAIL      → generate (with critique)
                     │              └─ ITERATE  → generate (with critique)
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
| `run_dir` | runner-injected | Per-run artifact directory (`.loops/runs/svg-image-generator-{timestamp}/`) for `image.svg`, `brief.md`, `critique.md`, and `screenshot.png`; created automatically. Override with `--context run_dir=path/`. |
| `design_tokens_context` | runner-injected | Resolved semantic design-token values (empty string when `design_tokens.enabled: false` or tokens path is missing). |
| `pass_threshold` | `6` | Minimum score per criterion (1–10); **all four** criteria must clear this value |

Override per-run:

```bash
ll-loop run svg-image-generator "lightning bolt icon" \
  --context pass_threshold=7
```

**FSM flow:**

```
init → plan → generate → evaluate
                            ├─ CAPTURED → score
                            │              ├─ ALL_PASS → done
                            │              ├─ ITERATE  → generate (with critique)
                            │              └─ ERROR    → diagnose → failed
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
| `run_dir` | runner-injected | Per-run artifact directory (`.loops/runs/svg-textgrad-{timestamp}/`) for `image.svg`, `brief.md`, `critique.md`, `gradients.md`, `scores.md`, `screenshot.png`, `best.svg`, and `best-brief.md`; created automatically. Override with `--context run_dir=path/`. |
| `design_tokens_context` | runner-injected | Resolved semantic design-token values (empty string when `design_tokens.enabled: false` or tokens path is missing). |
| `pass_threshold` | `6` | Minimum score per criterion (1–10); **weighted average** `(2×visual_clarity + 2×originality + craft + scalability) / 6` must meet or exceed this value |

Override per-run:

```bash
ll-loop run svg-textgrad "lightning bolt icon" \
  --context pass_threshold=7
```

**FSM flow:**

```
init → plan → generate → evaluate
                            ├─ CAPTURED → score → verify_score
                            │                         ├─ SHELL_PASS   → done
                            │                         ├─ SHELL_ITERATE → record_scores → compute_gradient → route_convergence
                            │                         │                                                        ├─ CONVERGED → done
                            │                         │                                                        └─ continue  → append_gradient → apply_gradient → generate
                            │                         └─ ERROR        → record_scores → compute_gradient → …
                            │              score ERROR → diagnose → failed
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
- The loop runs up to 40 iterations with a 2-hour timeout (`max_iterations: 40`, `timeout: 7200`). The convergence guard in `compute_gradient` (3-iteration score plateau) is the intended primary exit; the iteration cap is a safety backstop.
- To customize scoring criteria, install the loop locally (`ll-loop install svg-textgrad`) and edit the `score` state's prompt (writes `critique.md`) and the `verify_score` state's shell arithmetic (controls the pass threshold computation and routing). To customize gradient computation, edit the `compute_gradient` state's prompt.
- The generator enforces a strict 250-line SVG size limit — use `<circle>`, `<path>`, and `<text>` with `<g transform="">` for repeated elements rather than verbose repeated markup.
- Prefer `svg-image-generator` for quick iterations; reach for `svg-textgrad` when you see the same failure pattern repeating across iterations.

### `p5js-sketch-generator` — GAN-Style p5.js Sketch Loop

> **Prerequisites**: [Playwright CLI](https://playwright.dev/) must be installed (`npm install -g playwright && npx playwright install chromium`, or `pip install playwright && playwright install chromium`). Node.js must be available in `PATH` with `@playwright/test` in the global npm tree.

**Technique**: GAN-style generator-evaluator harness adapted for time-based generative work. A **planner** expands the one-line description into a visual brief (generative concept, palette, motion behavior, anti-patterns to avoid); a **generator** writes a fully self-contained HTML file that loads p5.js from CDN and embeds the sketch in global mode with deterministic `randomSeed`/`noiseSeed` and all motion driven by `frameCount`; a multi-frame **evaluator** uses Playwright's JS API to wait for each target `window.frameCount`, calls `noLoop()` to freeze the animation, captures a PNG, then calls `loop()` to resume — ensuring each frame PNG is byte-identical for the same input regardless of system load; and a **scorer** judges the frame strip against four sketch-specific criteria, routing back to the generator with structured critique until all scores clear `pass_threshold`.

**When to use**: When you want an animated p5.js generative sketch and need motion evaluated, not just composition. The multi-frame sampling (default frames 0, 90, 240) is the key differentiator from `svg-image-generator`: a static composition and a vibrantly-evolving system look identical at frame 0; sampling across time makes motion a first-class evaluation criterion. Use `pixi-generative-art` instead when GPU-accelerated idioms (filters, blend modes, particle containers) are central to the aesthetic.

**Usage:**

```bash
ll-loop run p5js-sketch-generator "a particle accumulation field that blooms outward from a center attractor"
```

**Context variables:**

| Variable | Default | Description |
|----------|---------|-------------|
| `description` | (from `loop_input`) | Natural language sketch description — passed as the positional argument |
| `run_dir` | runner-injected | Per-run artifact directory (`.loops/runs/p5js-sketch-generator-{timestamp}/`) for `index.html`, `brief.md`, `critique.md`, and `frame_*.png`; created automatically. Override with `--context run_dir=path/`. |
| `design_tokens_context` | runner-injected | Resolved semantic design-token values (empty string when `design_tokens.enabled: false` or tokens path is missing). |
| `pass_threshold` | `6` | Minimum score per criterion (1–10); **all four** criteria must clear this value |
| `sample_frames` | `"0,90,240"` | Comma-separated `frameCount` values to screenshot; controls which animation moments the evaluator judges |

Override per-run:

```bash
ll-loop run p5js-sketch-generator "recursive subdivision bloom" \
  --context pass_threshold=7 \
  --context sample_frames="0,60,180,360"
```

**FSM flow:**

```
init → plan → generate → evaluate
                            ├─ CAPTURED → score
                            │              ├─ ALL_PASS → done
                            │              ├─ ITERATE  → generate (with critique)
                            │              └─ ERROR    → failed
                            ├─ FAILED   → generate (retry transient render)
                            └─ ERROR    → failed
```

**Evaluation criteria** (all four must meet `pass_threshold`):

| Criterion | Weight | What it checks |
|-----------|--------|----------------|
| `visual_impact` | 2× | Composition, palette, density across the frame strip — does the sketch hold the eye? Penalizes muddy palettes, empty canvases, default p5 styling. |
| `originality` | 2× | Evidence of a specific generative idea vs tutorial output. Penalizes vanilla Perlin flow fields with rainbow HSL cycling, unmodified Shiffman-tutorial aesthetics, anything that could be the first Google result for "p5.js sketch". |
| `motion_quality` | 1× | Does the sketch meaningfully evolve between frame 0, 90, and 240? Frames that look interchangeable score ≤3. Jittery-without-direction is failure; look for accumulation, decay, drift, growth, or collapse. |
| `craft` | 1× | Blend modes, sub-pixel rendering, edge handling, color harmony, stroke weights, intentional use of negative space. |

**Notes:**
- p5.js is loaded from CDN (`https://cdnjs.cloudflare.com/ajax/libs/p5.js/1.9.4/p5.min.js`) — the only external resource permitted. All other code (sketch, helpers, CSS) is inline so the file renders correctly under a `file://` URL without a web server.
- The sketch uses p5.js global mode (`function setup()` / `function draw()` at the top level), which exposes `window.frameCount` — the value the screenshot harness polls when waiting for each frame.
- Deterministic seeding is required: `randomSeed(SEED)` and `noiseSeed(SEED)` called once in `setup()`, all motion driven by `frameCount`. Without seeding, screenshots at the same `frameCount` would differ run-to-run and the critique would chase noise.
- The `evaluate` state calls `noLoop()` immediately after `waitForFunction` reaches the target frame and before `page.screenshot()`, then calls `loop()` after the screenshot. This freezes the animation for the duration of the capture, preventing the ticker from advancing to frame N+1 or N+2 during the ~50–100 ms screenshot call. Both functions are p5.js globals exposed by global-mode sketches — generated sketches must not override or shadow them.
- Canvas size defaults to `createCanvas(1200, 800)` — override in the brief if the concept needs a different aspect ratio.
- If Playwright is unavailable, the `evaluate` state's `on_no` route retries with fresh HTML rather than scoring without visual evidence.
- The loop runs up to 20 iterations with a 2-hour timeout (`max_iterations: 20`, `timeout: 7200`).
- To customize scoring criteria, install the loop locally (`ll-loop install p5js-sketch-generator`) and edit the `score` state's prompt.

---

### `pixi-data-viz` — PixiJS Data Visualization Loop

> **Prerequisites**: [Playwright CLI](https://playwright.dev/) must be installed (`npm install -g playwright && npx playwright install chromium`, or `pip install playwright && playwright install chromium`). Node.js must be available in `PATH` with `@playwright/test` in the global npm tree.

**Technique**: GAN-style generator-evaluator harness for animated data visualizations rendered with PixiJS v8. A **planner** writes a detailed viz brief that commits to concrete data semantics — dataset shape, a synthetic-but-plausible dataset spec, encoding choices with perceptual justification (citing the Cleveland-McGill accuracy ranking), animation purpose, required annotations, and palette type; a **generator** writes a self-contained HTML file with the synthetic dataset embedded as a JSON literal, `window.__pixiApp = app` assigned after initialization, and chart chrome (axes, title, legend) rendered at frame 0 before any data animation begins; a multi-frame **evaluator** uses `page.waitForFunction` to reach the target `__loopFrame`, calls `window.__pixiApp.ticker.stop()` to freeze the animation, captures the PNG, then resumes with `ticker.start()` — ensuring byte-identical output for the same input regardless of system load; and a **scorer** applies per-criterion thresholds with `encoding_clarity` hard-gated at 7 regardless of `pass_threshold` — mirroring how `html-anything` gates platform constraints above aesthetic criteria.

**When to use**: When you need an animated, GPU-rendered data visualization with rigorous evaluation of encoding clarity, not just aesthetics. The hard gate on `encoding_clarity` is the key differentiator from `pixi-generative-art`: a beautiful chart with unlabeled axes still fails. Use `pixi-generative-art` when aesthetic impact matters more than data fidelity; use `p5js-sketch-generator` when the p5.js API (built-in `noise()`, global mode) is preferred over PixiJS.

**Usage:**

```bash
ll-loop run pixi-data-viz "animated bar chart showing monthly revenue by product category over 12 months"
```

**Context variables:**

| Variable | Default | Description |
|----------|---------|-------------|
| `description` | (from `loop_input`) | Natural language visualization description — passed as the positional argument |
| `run_dir` | runner-injected | Per-run artifact directory (`.loops/runs/pixi-data-viz-{timestamp}/`) for `index.html`, `brief.md`, `critique.md`, and `frame_*.png`; created automatically. Override with `--context run_dir=path/`. |
| `design_tokens_context` | runner-injected | Resolved semantic design-token values (empty string when `design_tokens.enabled: false` or tokens path is missing). |
| `pass_threshold` | `6` | Minimum score for non-gated criteria (1–10); `encoding_clarity` is hard-gated at 7 regardless of this value |
| `sample_frames` | `"0,120,240"` | Comma-separated `__loopFrame` values to screenshot; defaults capture initial chrome, mid-transition, and settled state |

**FSM flow:**

```
init → plan → generate → evaluate
                            ├─ CAPTURED → score
                            │              ├─ ALL_PASS → done
                            │              ├─ ITERATE  → generate (with critique)
                            │              └─ ERROR    → failed
                            ├─ FAILED   → generate (retry transient render)
                            └─ ERROR    → failed
```

**Evaluation criteria:**

| Criterion | Threshold | What it checks |
|-----------|-----------|----------------|
| `encoding_clarity` | **7** (hard-gated) | Axes labeled with units, legend present for multi-series data, scale appropriate, no truncated y-axes, no rainbow-jet on sequential data, encoding from brief implemented literally — the platform constraint for any data visualization |
| `animation_legibility` | `pass_threshold` | Does motion aid comprehension? Compares frames at 0, 120, and 240; penalizes decorative bounce/easing that doesn't encode information and animation that out-paces reading speed |
| `visual_design` | `pass_threshold` | Aesthetic coherence; palette type matches data type — sequential for ordered scalars, diverging for data with a meaningful midpoint, categorical for unordered groups |
| `craft` | `pass_threshold` | Typography hierarchy (title > axis labels > tick labels), spacing consistency, alignment, anti-aliasing of axes and strokes |

**Notes:**
- PixiJS v8 is loaded from CDN (`https://pixijs.download/release/pixi.js`) — the only external resource. The sketch body must be wrapped in an IIFE async function because `app.init({...})` is asynchronous in PixiJS v8.
- The synthetic dataset is embedded as a JSON literal at the top of the inline script — never generated with `Math.random()` at runtime. This ensures the same description always produces the same data across runs.
- Frame 0 must show complete chart chrome (axes with tick labels and units, title, legend) before any data animation begins. The `evaluate` state's frame-0 screenshot is a direct test of this requirement.
- The sketch exposes `window.__loopFrame` (not p5's `window.frameCount`) as the harness polling target; it must be incremented inside the PixiJS ticker. All animation is driven from `window.__loopFrame`.
- The sketch must assign `window.__pixiApp = app` immediately after `await app.init(...)`. The harness calls `window.__pixiApp?.ticker?.stop()` before each `page.screenshot()` and `ticker?.start()` after, freezing the animation at the exact target frame. The optional-chaining access (`?.`) means sketches that omit the assignment degrade silently (PRNG seeding alone is insufficient for byte-level reproducibility), but newly-generated sketches must include it.
- A seeded deterministic PRNG (e.g. mulberry32 with a constant integer seed) is used for any runtime jitter — never unseeded `Math.random()` inside the ticker. PRNG seeding alone is insufficient for byte-exact reproducibility; ticker pause is also required.
- If Playwright is unavailable, the `evaluate` state's `on_no` route retries with fresh HTML rather than scoring without visual evidence.
- The loop runs up to 20 iterations with a 2-hour timeout (`max_iterations: 20`, `timeout: 7200`).
- To customize scoring thresholds or criteria, install the loop locally (`ll-loop install pixi-data-viz`) and edit the `score` state's prompt and threshold logic.

---

### `pixi-generative-art` — PixiJS Generative Art Loop

> **Prerequisites**: [Playwright CLI](https://playwright.dev/) must be installed (`npm install -g playwright && npx playwright install chromium`, or `pip install playwright && playwright install chromium`). Node.js must be available in `PATH` with `@playwright/test` in the global npm tree.

**Technique**: GAN-style generator-evaluator harness for GPU-accelerated generative art, mirroring `p5js-sketch-generator` but targeting PixiJS idioms. A **planner** writes a sketch brief that explicitly commits to a **GPU strategy** — which PixiJS filter (`BlurFilter`, `DisplacementFilter`, `ColorMatrixFilter`, custom GLSL via `Filter.from`), blend mode (`'add'`, `'multiply'`, `'screen'`), container hierarchy, or `ParticleContainer` does the aesthetic heavy lifting; a **generator** writes a self-contained HTML file with PixiJS v8 loaded from CDN, a seeded deterministic PRNG, `window.__pixiApp = app` assigned after initialization, and all motion driven by `window.__loopFrame`; a multi-frame **evaluator** uses `page.waitForFunction` to reach each target frame, calls `window.__pixiApp?.ticker?.stop()` to freeze the animation, captures the PNG, then resumes with `ticker?.start()` — pinning each capture to the exact frame regardless of system load; and a **scorer** applies a `gpu_craft` criterion that inspects the generated HTML source for evidence of PixiJS-native features — a sketch that could have been drawn with a plain 2D canvas context scores ≤4.

**When to use**: When you want GPU-accelerated generative art and care that the result uses PixiJS-distinctive features rather than just canvas drawing calls in a PixiJS wrapper. Use `p5js-sketch-generator` when the p5.js ecosystem (built-in `noise()`, `random()`, global mode, the Processing community's idioms) is a better fit. Use `pixi-data-viz` when encoding data accurately is the goal rather than aesthetic impact.

**Usage:**

```bash
ll-loop run pixi-generative-art "a bioluminescent deep-sea particle system with displacement filter bloom"
```

**Context variables:**

| Variable | Default | Description |
|----------|---------|-------------|
| `description` | (from `loop_input`) | Natural language sketch description — passed as the positional argument |
| `run_dir` | runner-injected | Per-run artifact directory (`.loops/runs/pixi-generative-art-{timestamp}/`) for `index.html`, `brief.md`, `critique.md`, and `frame_*.png`; created automatically. Override with `--context run_dir=path/`. |
| `design_tokens_context` | runner-injected | Resolved semantic design-token values (empty string when `design_tokens.enabled: false` or tokens path is missing). |
| `pass_threshold` | `6` | Minimum score per criterion (1–10); **all four** criteria must clear this value |
| `sample_frames` | `"0,90,240"` | Comma-separated `__loopFrame` values to screenshot |

**FSM flow:**

```
init → plan → generate → evaluate
                            ├─ CAPTURED → score
                            │              ├─ ALL_PASS → done
                            │              ├─ ITERATE  → generate (with critique)
                            │              └─ ERROR    → failed
                            ├─ FAILED   → generate (retry transient render)
                            └─ ERROR    → failed
```

**Evaluation criteria** (all four must meet `pass_threshold`):

| Criterion | Weight | What it checks |
|-----------|--------|----------------|
| `visual_impact` | 2× | Composition, palette, density across the frame strip. Penalizes muddy palettes, empty canvases, default Pixi styling. |
| `originality` | 2× | Evidence of a specific generative idea vs tutorial output. Penalizes Pixi demo clones (bunny, fish-pond, spinning logo) and anything that could be the first Google result for "pixijs example". |
| `motion_quality` | 1× | Does the sketch meaningfully evolve between frame 0, 90, and 240? Frames that look interchangeable score ≤3. Look for accumulation, decay, drift, growth, or collapse. |
| `gpu_craft` | 1× | Visible use of PixiJS GPU strengths — `Filter` instances (BlurFilter, DisplacementFilter, custom GLSL via `Filter.from`), explicit blend modes (`'add'`, `'multiply'`, `'screen'`), `Container` hierarchies with per-layer transforms, or `ParticleContainer` for dense agent counts. The evaluator **inspects `index.html`** to verify a PixiJS-native feature is actually used. A sketch that could have been drawn with a plain `<canvas>` 2D context scores ≤4 on this criterion. |

**Notes:**
- PixiJS v8 is loaded from CDN (`https://pixijs.download/release/pixi.js`) — the only external resource. The sketch body must be wrapped in an IIFE async function because `app.init({...})` is asynchronous.
- The sketch exposes `window.__loopFrame` (not p5's `window.frameCount`) as the harness polling target; increment it inside the PixiJS ticker. All motion must be driven from `window.__loopFrame`, never from `Date.now()` or unseeded `Math.random()`.
- The sketch must assign `window.__pixiApp = app` immediately after `await app.init(...)`. The harness calls `window.__pixiApp?.ticker?.stop()` before each `page.screenshot()` and `ticker?.start()` after, freezing the animation at the exact target frame. PRNG seeding alone is insufficient for byte-exact reproducibility — `window.__pixiApp` exposure and ticker pause are also required. The optional-chaining access (`?.`) means old sketches degrade silently; newly-generated sketches must include the assignment.
- A seeded deterministic PRNG (e.g. mulberry32 with a constant integer seed) is required for all randomness so screenshots at the same `__loopFrame` value are reproducible across iterations.
- The `gpu_craft` criterion explicitly reads `index.html` source code — the evaluator verifies that a PixiJS-native feature is present in the code, not just claimed in the brief.
- If Playwright is unavailable, the `evaluate` state's `on_no` route retries with fresh HTML rather than scoring without visual evidence.
- The loop runs up to 20 iterations with a 2-hour timeout (`max_iterations: 20`, `timeout: 7200`).
- Prefer `p5js-sketch-generator` when the p5.js ecosystem (global mode, built-in `noise()`) is the right tool; reach for `pixi-generative-art` when GPU filters, blend modes, or `ParticleContainer` density are central to the aesthetic.

### `cli-anything-bootstrap` — Agent-Native CLI Bootstrapper

**Technique**: Meta-loop that bootstraps an agent-native CLI wrapper for target software (local path or repo URL) by delegating to CLI-Anything's `/cli-anything` skill, baking a per-target rubric with non-LLM evaluators (pip install exit code, `--help` coverage, pytest pass rate), caching the CLI, and emitting a project-local task loop to `.loops/generated/<target>-task.yaml`.

**When to use**: When you need a repeatable, agent-drivable CLI interface for a third-party tool or library. The generated task loop can be invoked by downstream loops to drive the target software toward user goals without re-bootstrapping.

**Prerequisites**:
- CLI-Anything plugin installed (provides `/cli-anything` and `/cli-anything:refine` skills)
- Target software accessible at the given path or repo URL
- Python 3.10+ available for venv install

**Usage:**

```bash
ll-loop run cli-anything-bootstrap --context target="https://github.com/user/repo"
# Bootstraps CLI → bakes rubric → caches to .loops/cli-anything/
# → emits .loops/generated/repo-task.yaml
```

**Two outputs per successful run:**
1. Cached CLI at `.loops/cli-anything/<target-hash>/`
2. Generated task loop at `.loops/generated/<target-name>-task.yaml`

**Task templates:** Three bundled `.tmpl` templates in `loops/lib/task-templates/` are selected by the loop based on target classification:
- `data-lib-task.yaml.tmpl` — for data-processing libraries
- `desktop-gui-task.yaml.tmpl` — for GUI applications
- `stateful-service-task.yaml.tmpl` — for servers and daemons

**Meta-loop discipline (MR-1)**: Every LLM-proposed artifact is paired with a non-LLM external evaluator — the LLM score-bootstrap state judges measured numbers, not its own generated artifacts.

**Per-run artifact isolation (MR-3)**: Loops must write intermediate artifacts under `${context.run_dir}/`, not bare `.loops/tmp/`. The runner injects `run_dir` as `.loops/runs/<loop>-<timestamp>/` and creates the folder before execution. Writing to shared `.loops/tmp/` causes state corruption when two instances of the same loop run concurrently. Set `shared_state_ok: true` at the loop top-level to suppress this validation warning when cross-run sharing is intentional.

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
| `action_stall` | `yes` / `no` | — | Detect when the same action string or context values repeat for N consecutive iterations (file-backed, no git required) |
| `llm_structured` | `yes` / `no` / `blocked` / `partial` | slash commands | Natural-language judgment via LLM |
| `mcp_result` | `success` / `tool_error` / `not_found` / `timeout` | `mcp_tool` actions | Evaluate MCP server tool call results; see [MCP Tool Actions](#mcp-tool-actions) for verdict details |
| `comparator` | `yes` / `no` / `tie` / `no_baseline` | — | Blind A/B comparison of current output against a stored baseline via LLM judge; requires `baseline_path` |
| `contract` | `yes` / `no` / `error` | — | Read producer/consumer file pairs and assert contract alignment via LLM judge; requires `pairs` in `evaluate:` block |

**Exit-code short-circuit**: When an action exits with a non-zero code, evaluators that don't intrinsically handle exit codes (`output_numeric`, `output_json`, `output_contains`, `convergence`, `comparator`) immediately return `error` without running their normal logic. Exit-code-aware evaluators (`exit_code`, `mcp_result`, `harbor_scorer`, `diff_stall`, `action_stall`, `llm_structured`, `contract`) are exempt — they process the exit code through their own evaluation path.

Override the default by adding an `evaluate:` block to a state:

```yaml
evaluate:
  type: output_contains
  pattern: "All checks passed"
```

**Action-level timeouts (`exit_code=124`)**: When a `prompt`, `mcp`, or `shell` action is killed at its `timeout:` budget, the runner returns `exit_code=124` (often with truncated stdout). All evaluator types (except `mcp_result`, which has its own `timeout` verdict) short-circuit to `verdict="error"`, so loop authors should use `on_error:` as the canonical recovery branch for action timeouts. This prevents truncated output from being misread as a deliberate `no` verdict.

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

Escape literal `${` with `$${`. Bash parameter expansion operators (`:-`, `:+`, `[@]`, etc.) inside `$${...}` blocks are supported and pass through unchanged — e.g., `$${DEPTH:-0}` reaches the shell as `${DEPTH:-0}`.

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

> **`on_no` → `on_error` fallthrough**: When a `no` verdict is returned and the state defines `on_error` but not `on_no`, the executor routes to `on_error`. This applies to both shorthand (`on_no`/`on_error` keys) and full `route` tables (`no:`/`error:` keys). Use this to share a single error-recovery branch for both evaluator failures and hard-`no` verdicts when they require the same remediation.

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
| `retryable_exit_codes:` | list of integers | Restrict retry to only these exit codes. When set, non-matching non-zero exits skip retry and route directly to `on_error` immediately (no retry consumed). Useful for distinguishing transient failures (e.g. exit 1 for API socket disconnect, exit 137 for OOM) from permanent ones (e.g. config errors). Requires `on_error` to be set. |
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

If a conflicting loop is already running, `ll-loop run` will error. Use `--queue` to wait for the conflict to resolve instead. The maximum wait is controlled by `loops.queue_wait_timeout_seconds` in `.ll/ll-config.json` (default: 86400 s / 24 h). Decrease it for fail-fast CI environments; increase it for multi-day batch processing. When multiple loops queue for the same lock, they acquire it in FIFO (arrival) order.

## Background Mode

The `-b` / `--background` flag detaches a loop from the terminal so it runs as an independent daemon process. The parent command returns immediately (exit 0) and the loop continues in a new process group, surviving terminal close.

### When to use it

| Situation | Recommendation |
|-----------|---------------|
| Loop runs for minutes or hours and you need your terminal back | `--background` |
| Running multiple non-overlapping loops concurrently | `--background` each one |
| Unattended execution (CI/CD, scheduled jobs, post-handoff restart) | `--background` |
| Short loop you want to watch live | Foreground (default) |
| Loop that blocks on scope conflict and you want to wait interactively | Foreground + `--queue` |

### Starting a background loop

```bash
ll-loop run my-scan --background
# or shorthand
ll-loop my-scan -b
```

Output:

```
Loop my-scan started in background (PID: 12345)
  Log:    .loops/.running/my-scan-20260503T122306.log
  Status: ll-loop status my-scan
  Stop:   ll-loop stop my-scan
```

### Monitoring progress

```bash
# Check whether the process is alive and what state the loop is in
ll-loop status my-scan

# Attach and render FSM state in realtime (read-only; Ctrl-C detaches)
ll-loop monitor my-scan
ll-loop monitor my-scan --show-diagrams --clear   # pinned FSM diagram view

# Stream live output (works for both foreground and background runs)
tail -f $(ll-loop status my-scan --json | python3 -c "import sys,json; print(json.load(sys.stdin).get('log_file') or '')")

# For foreground runs, inspect the always-present events file instead
ll-loop status my-scan --json | python3 -c "import sys,json; print(json.load(sys.stdin).get('events_file') or '')"
```

`ll-loop monitor` tails `.events.jsonl` and forwards events to the same renderer used by foreground runs, so a background loop becomes visually inspectable without restarting it. Ctrl-C detaches from the rendered stream without signaling the loop process — use `ll-loop stop` to terminate.

Both foreground and background runs write stdout and stderr to `.loops/.running/<instance-id>.log` (ANSI escape sequences stripped). `log_file` in `--json` output is the path to this file for all run modes; `null` only for background-spawned child processes (`--foreground-internal`) or pre-ENH-1703 state files. All runs also write structured events to `.loops/.running/<instance-id>.events.jsonl`; use the `events_file` field from `--json` output to locate it. The PID may be stored in `.loops/.running/<instance-id>.pid` (background-mode processes) or in `.loops/.running/<instance-id>.lock` (foreground runs); `ll-loop status` checks both, preferring the `.pid` file and falling back to the `.lock` file. The `pid_source` field in `--json` output indicates which file the PID came from. The `instance-id` is `<loop-name>-<YYYYMMDDTHHMMSS>` (e.g. `my-scan-20260503T122306`); use `ll-loop status <loop-name> --json` to retrieve the exact log or events path for a running instance.

**Note**: `ll-loop status` may transparently rewrite orphaned state files. When a state file claims `status: running` but the PID (resolved via `.pid` → `.lock` → embedded `state.pid`) is provably dead, the file is updated in-place to `status: interrupted` and a `reconciled_at` timestamp is recorded. This is a no-op for live processes.

### Stopping a background loop

```bash
ll-loop stop my-scan
```

The first signal (`SIGTERM`) triggers a graceful shutdown — the loop finishes its current action and exits cleanly. A second `SIGTERM` (or sending `SIGKILL` manually) forces immediate exit.

### Combining `--background` with `--queue`

```bash
ll-loop my-scan --background --queue
```

**Important:** `--background` causes the *parent* to return immediately. Queue waiting happens inside the detached child process. The parent does not block or report whether the child is queued — use `ll-loop status my-scan` or retrieve the log path via `ll-loop status my-scan --json` to check. The same `loops.queue_wait_timeout_seconds` config value applies; the background child exits with code 1 if the timeout is reached.

### Running multiple loops concurrently

Loops with non-overlapping scopes can run at the same time:

```bash
ll-loop fix-types --background   # claims src/
ll-loop run-docs --background    # claims docs/ — starts immediately, no conflict
ll-loop list --running           # shows both
```

Loops with overlapping scopes conflict. Add `--queue` so the second waits for the first:

```bash
ll-loop refactor-api --background --queue
```

### `maintain: true` vs `--background`

These are orthogonal — they control different things:

| Setting | What it controls |
|---------|-----------------|
| `maintain: true` (YAML) | Loop *restarts itself* after reaching a terminal state — inner restart logic |
| `--background` (CLI flag) | Loop *process detaches* from the terminal — outer execution mode |

You can combine them: a `maintain: true` loop running with `--background` is a long-lived daemon that auto-restarts and never occupies a terminal.

### Resuming a background loop

If a background loop paused due to a context handoff (`on_handoff: pause`), resume it as a background process:

```bash
ll-loop resume my-scan --background
```

The resumed loop inherits the saved state (current FSM state, iteration count, captured variables) and runs detached, writing output to the same log file.

## Prompt Optimization Loops (APO)

> **Advanced** — APO loops tune prompts automatically. Most users won't need these.
> Start with standard loops and return here when you have a specific prompt quality problem.

Automatic Prompt Optimization (APO) loops apply iterative improvement techniques to refine prompts using LLM-driven evaluation. They are a practical alternative to manual prompt engineering: instead of tweaking prompts by hand, you describe your criteria and let the loop drive convergence.

Eight built-in APO loops ship with little-loops:

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

### `rn-plan-apo` — Plan-Quality Gradient Optimization

**Technique**: Run `rn-plan` over a benchmark task set with the current planning prompt → score the resulting plan trees on four plan-quality dimensions (subtask success rate, depth/complexity ratio, redundancy, coverage gaps) → compute a text gradient (FAILURE_PATTERN / ROOT_CAUSE / GRADIENT) over the aggregate plan-quality score → overwrite the planning prompt → repeat until `target_plan_quality` is reached.

**When to use**: You have shipped [`rn-plan`](#rn-plan--recursive-task-planning-with-self-scoring-rubric) and want its decomposition prompt to improve as plan trees accumulate. Unlike `apo-textgrad` (labeled I/O pairs) and `harness-optimize` (single-score hill-climb), `rn-plan-apo`'s gradient is computed over structured plan-quality signals derived from `rn-plan`'s output directory shape (`plan.md` + `plan-rubric.md` per task). Use when systematic plan-quality issues — over-splitting trivial tasks, skipping dependency analysis, recurring coverage gaps — are visible across plans and you want a targeted gradient rather than free-form feedback.

**Required context variables**:

| Variable | Default | Description |
|----------|---------|-------------|
| `plan_prompt_file` | `.ll/prompts/rn-plan-planning.md` | Path to the planning prompt that this loop iteratively refines |
| `tasks_file` | `benchmarks/rn-plan-tasks.json` | Path to a JSON array of task strings (one task per element) or a plain-text file (one task per line) |
| `target_plan_quality` | `80` | Aggregate plan-quality score (0–100) at which the loop considers the prompt converged |

**`tasks_file` format** — either a JSON array of strings:

```json
[
  "Add a feature flag system to the API",
  "Migrate the auth middleware to async",
  "Document the webhook retry strategy"
]
```

Or a plain text file with one task per line. The `run_planner` state auto-detects the format.

**Invocation**:

```bash
# Run with default planning prompt and benchmark task set
ll-loop run rn-plan-apo

# Point at a custom planning prompt and benchmark
ll-loop run rn-plan-apo \
  --context plan_prompt_file=.ll/prompts/rn-plan-planning.md \
  --context tasks_file=benchmarks/rn-plan-tasks.json \
  --context target_plan_quality=85
```

**FSM flow**:
```
run_planner ──→ score_plans ──→ compute_gradient ──→ route_convergence
                                                     ├─ CONVERGED ──→ done
                                                     └─ CONTINUE ──→ apply_gradient ──→ run_planner
```

**Persistence guarantee**: `apply_gradient` overwrites `plan_prompt_file` only on accepted refinements — the state is structurally unreachable from `route_convergence`'s `on_yes` (CONVERGED) branch. The planning prompt is never touched when the loop has already converged.

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
  --context prompt_file=commands/refine-issue.md

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
| Optimizing the `rn-plan` planning prompt | `rn-plan-apo` |
| Building a training example corpus | `examples-miner` |
| Prompt quality has regressed vs. baseline | `prompt-regression-test` |

| | `apo-feedback-refinement` | `apo-contrastive` | `apo-opro` | `apo-beam` | `apo-textgrad` | `rn-plan-apo` | `prompt-regression-test` |
|---|---|---|---|---|---|---|---|
| Exploration per iteration | Low (single candidate) | Medium (N candidates, comparative) | Low (history-guided single candidate) | High (N parallel candidates, independent) | Low (single targeted refinement) | Low (single targeted refinement over plan-quality scores) | Low (one repair pass via apo-textgrad) |
| Convergence speed | Fastest when feedback is precise | Moderate | Moderate | Slowest (most LLM calls) | Fast when examples have clear correct answers | Moderate (one `rn-plan` execution per task per iteration) | Fast when regression has concrete failing examples |
| Local optima risk | High | Moderate | Moderate | Low | Low (example failures provide precise signal) | Low (4-dimension structural signal from plan trees) | Low (triggered only by concrete regressions) |
| Best for | Targeted improvement with clear criteria | Broad style exploration | Long runs where history improves proposals | Escaping plateaus, high-variance search spaces | Prompts with measurable pass/fail examples (classification, extraction) | The `rn-plan` planning prompt; plans scored on subtask success rate, depth/complexity, redundancy, coverage gaps | CI integration; defending a known-good quality baseline |

### Tips for APO Loops

- **Start with a concrete `eval_criteria`**: vague criteria produce vague scores. Instead of `"good"`, try `"responds only with valid JSON, handles edge cases, and explains its reasoning"`.
- **Set `quality_threshold` conservatively**: start at 80 and raise once the loop reaches it. Overly strict thresholds burn iterations without improvement.
- **Check the prompt file after each run**: the loop writes back to the file in-place. Use `git diff` to review the evolution across iterations.
- **Install to customize**: run `ll-loop install apo-feedback-refinement` to copy the YAML to `.loops/` and edit state actions or add custom evaluation logic.

## Evaluation Loops

Loops in this category analyze other loops — auditing their YAML definitions, running them as sub-loops, and producing structured improvement reports.

### `outer-loop-eval` — Loop Structure & Execution Auditor

**Technique**: Load a target loop's YAML definition, execute it as a sub-loop against an optional input, then delegate to `/ll:debug-loop-run` (static definition analysis + execution trace analysis) and `/ll:audit-loop-run` (scorecard and improvement proposals). Improvements to either skill are automatically available to `outer-loop-eval` without YAML edits.

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
analyze_definition (/ll:debug-loop-run --auto) → run_sub_loop → analyze_execution (/ll:debug-loop-run --auto) → generate_report (/ll:audit-loop-run --auto)
                                                                                                                  ├─ YES (has findings) → done
                                                                                                                  └─ NO (all "None identified.") → refine_analysis (/ll:audit-loop-run --auto) → generate_report
```

**Execution failure handling**: If `loop_name` is empty, `validate_input` exits immediately with a clear error message before any analysis begins — preventing hallucinated reports. If the target loop is found but fails to start (not found after validation, crashes on launch), `outer-loop-eval` delegates to `/ll:debug-loop-run` and `/ll:audit-loop-run` as-is — the skills surface whatever can be inferred from available context.

**Skill delegation**: `analyze_definition` and `analyze_execution` both invoke `/ll:debug-loop-run ${loop_name} --auto`; `generate_report` and `refine_analysis` invoke `/ll:audit-loop-run ${loop_name} --auto`. Improvements to either skill (new signals, richer scoring, updated heuristics) flow through to `outer-loop-eval` automatically.

**Report content**: The improvement report is produced by `/ll:audit-loop-run` and includes its standard scorecard sections. Use `ll-loop install outer-loop-eval` to copy the YAML and customize which skills are invoked or how their output is evaluated.

---

## `harness-optimize` with `.ll/program.md`

For long-horizon overnight runs, populate `.ll/program.md` once and run with no context flags:

```bash
# .ll/program.md
## Directive
Improve the refine-issue skill to produce more actionable integration maps.

## Targets
- commands/refine-issue.md

## Benchmark
task_dir: evals/refine-issue
scorer: ./scripts/score.sh

## Budget
wall_clock: 8h
```

```bash
ll-loop run harness-optimize
```

The loop reads `.ll/program.md` automatically, injects `directive`, `targets`, `task_dir`, and `scorer` into context, and includes the Directive prose in each LLM proposal step so the model knows the optimization goal.

**Precedence**: `--context KEY=VALUE` CLI flags override `.ll/program.md` values; `.ll/program.md` values override YAML defaults.

See [`.ll/program.md` reference](../reference/program-md.md) for the full section reference and examples.

### State Mode

State mode activates when `context.targets` points to a loop YAML file whose `targets:` block contains `states:` entries. Instead of proposing edits to arbitrary file contents, the loop mutates and scores each state's `action:` block independently via `yaml_state_editor.replace_action()`.

**Activation** — add a `targets:` block to `.ll/program.md` (or pass via `--context targets=<path>`):

```yaml
# .ll/program.md
## Targets
- file: scripts/little_loops/loops/my-loop.yaml
  states:
    - name: propose
      examples_file: .ll/examples/propose.jsonl
      eval: score >= 7
    - name: apply
      examples_file: .ll/examples/apply.jsonl
      eval: score >= 6
```

**Behavior**:

- States are processed in declaration order via a runtime queue (`check_queue` / `dequeue_state` cycle)
- Each state's `action:` block is mutated and benchmarked independently — accepting or reverting one state does not affect any other state's accepted mutation
- Per-state scoring: each state's `eval` threshold is evaluated against that state's benchmark result only
- Trajectories are written per-state to `.ll/runs/harness-optimize/<run-id>/states/<state-name>/trajectory.jsonl`

See [harness-optimize reference](../reference/loops.md#harness-optimize) for the full state graph showing the `check_queue` / `dequeue_state` dispatch.

---

## Harness Loops

> **Advanced** — See [AUTOMATIC_HARNESSING_GUIDE.md](AUTOMATIC_HARNESSING_GUIDE.md) for the
> full harness guide. This section is a brief overview.
> **Meta-loops** (loops that modify other harness artifacts) must follow the design rules in
> [CLAUDE.md § Loop Authoring](../../.claude/CLAUDE.md) — diagnosis-first scaffolding and a
> non-LLM evaluator paired with every `check_semantic` state.

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

Run `/ll:create-loop` and select **"Harness a skill or prompt"**, or pass a description directly — `/ll:create-loop harness the refine-issue skill and iterate until the issue is implementation-ready` — to skip straight to YAML preview. The 4-step wizard asks:

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

#### Progressive tool-call throttling

A per-state safeguard that detects and halts runaway action loops — for example, a `prompt` state that keeps calling a tool in a tight LLM-driven loop without making forward progress.

Add a `throttle:` block to any state that could loop internally:

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

All three fields are optional; the defaults (`normal_max=3`, `warn_max=8`, `hard_max=12`) are inherited from the executor module constants.

**`type: learning`** — Learning states (FEAT-1283) prove external-API/SDK assumptions against the learning-tests registry (ENH-1282) before advancing. They legitimately make N tool calls per visit (one `/ll:explore-api` invocation per unproven target), so they are exempt from `hard_max` enforcement. The dispatch handler iterates `learning.targets` in order: proven targets pass through immediately; missing or stale records trigger `/ll:explore-api <target>` (up to `learning.max_retries` times); refuted records or exhausted retries route to `on_blocked` (preferred) or `on_no`.

```yaml
states:
  learn:
    type: learning
    learning:
      targets:
        - "Anthropic SDK streaming"
        - "GitHub API rate limits"
      max_retries: 2
    on_yes: planning      # all targets proven → continue
    on_blocked: blocked   # any target refuted, or retries exhausted
```

Required fields for `type: learning` states: `learning.targets` (non-empty), `on_yes`, and one of `on_blocked` / `on_no`. The dispatch emits `learning_target_proven`, `learning_target_stale`, `learning_explore_invoked`, `learning_target_refuted`, `learning_complete`, and `learning_blocked` events for observability — see `docs/reference/EVENT-SCHEMA.md` for full payloads.

> Legacy `type: learning` states without a `learning:` sub-object fall through to normal action execution (preserving the pre-FEAT-1283 throttle-exemption-only behavior). Mixing `type: learning` with `action:` is supported only for that legacy path; new learning gates should always declare `learning.targets`.

**Call-count telemetry** — On every action execution inside a state, the executor increments a `tool_call_count` field in the per-state record persisted to `LoopState`. `ll-loop show` surfaces this as part of the state history, making runaway states visible after the fact even when the loop was not terminated by `hard_max`.

#### Server-error automatic retry

API 5xx errors (overload, 529, "server had an error") are automatically retried at the executor level — no per-loop YAML config required.

- **Retry limit**: up to `max_api_error_retries` attempts (default: 2)
- **Backoff**: flat 30s between attempts
- **Scope**: `action_type: prompt` and `action_type: slash_command` actions
- **Fallthrough**: after retries exhausted, normal FSM routing resumes

This prevents transient infrastructure events from triggering incorrect FSM branching (e.g. autodev treating a server error as a failed confidence check and routing to decomposition instead of continuing).

#### Sub-loop budget forwarding

When a parent FSM spawns a child FSM via `_execute_sub_loop`, the child's `timeout` is clamped to the parent's remaining wall-clock budget. This ensures the child terminates cleanly before the parent's deadline, allowing the parent to route via `on_no`/`dequeue_next` rather than hitting a hard timeout with no recourse.

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
| `ll-loop show <name>` | Display states, transitions, and ASCII diagram (`--json` for raw FSM config; `--resolved` to expand sub-loop states inline under `_subloop`) |
| `ll-loop test <name>` | Run a single iteration to verify configuration |
| `ll-loop simulate <name>` | Trace execution interactively without running actions |
| `ll-loop list` | List available loops; `--running` for active only, `--builtin` for built-ins, `--category <cat>` / `--label <tag>` to filter by category or label |
| `ll-loop status <name>` | Show current state and iteration count (`--json` for machine-readable output) |
| `ll-loop stop <name>` | Stop a running loop |
| `ll-loop resume <name>` | Resume an interrupted loop from saved state |
| `ll-loop history <name>` | Show history; pass `run_id` to view a specific archived run |
| `ll-loop install <name>` | Copy a built-in loop to `.loops/` for customization |
| `ll-loop next-loop` | Suggest next loop(s) from execution history; `--count N` for top N, `--execute` to run top suggestion immediately, `--exclude <name>` to skip specific loops |

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
| `--dry-run` | Show execution plan without running actions. Diagram rendering is not suppressed — combine with `--show-diagrams` to preview both the FSM diagram and the execution plan before running. |
| `--no-llm` | Disable LLM-based evaluation (use deterministic evaluators only) |
| `--llm-model <model>` | Override the LLM model for evaluation |
| `-n <N>` | Override `max_iterations` |
| `--queue` | Wait for conflicting scoped loops instead of erroring |
| `-q` / `--queue` | Wait for conflicting scoped loops instead of erroring (shorthand for `--queue`) |
| `--quiet` | Suppress progress output |
| `-f` / `--follow` | Stream FSM state transitions to stdout as they fire, in `ll-loop history` format. Combine with `--quiet` to see only the structured history output. Cannot be combined with `--background`. |
| `-v` / `--verbose` | Show full prompt content at action start; default shows a single-line truncated preview |
| `-b` / `--background` | Run as a background daemon |
| `--show-diagrams[=MODE]` | Display FSM diagram after each step. `MODE` is a **topology** (`layered`\|`neighborhood`\|`inline`) or a **preset** (`detailed`\|`summary`\|`clean`\|`local`\|`slim`\|`oneline`). Bare flag selects the `summary` preset (layered, main-path scope). Use `--diagram-edge-labels=on\|off`, `--diagram-state-detail=title\|full`, and `--diagram-scope=main\|full` to override individual preset facets. **Breaking:** `main`/`full`/`mini` are no longer valid — use `summary`/`detailed`/`clean` respectively. Also works with `--dry-run`: the diagram is rendered above the execution plan. |
| `--clear` | Clear terminal before each iteration; combine with `--show-diagrams` for a live in-place dashboard. When combined on a tty, the screen splits into a pinned FSM diagram (top) and a scrolling action-output region (bottom). On terminals too short for the full diagram, the pinned pane falls back to a 1-hop neighborhood view, then to a single-line `fsm:` status. When a parent loop spawns child loops, the pinned pane shows only the **deepest active child loop** — keeping the display focused regardless of nesting depth. |
| `--delay <SECONDS>` | Sleep N seconds between iterations; overrides `backoff:` from YAML |
| `--context KEY=VALUE` | Override a context variable at runtime (repeatable) |
| `--program-md PATH` | Load steering directive from a Markdown file (default: `.ll/program.md` when present); parsed fields are injected into loop context before `--context` overrides. See [`.ll/program.md` convention](../reference/program-md.md). |

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
- **Loop run state, event logs, and meta-eval telemetry are automatically archived** to `.loops/.history/<timestamp>-<loop-name>/` immediately on completion. Meta-loops also archive `meta-eval.jsonl` alongside `state.json` and `events.jsonl`. Use `ll-loop history <name>` without a `run_id` to list archived runs, or `ll-loop history <name> <run_id>` to inspect a specific one.
- **Foreground runs always write a log file** to `.loops/.running/<instance-id>.log` (same path as background runs). Output is ANSI-stripped plain text; use `tail -f` or `grep` for post-hoc inspection. `ll-loop status <loop>` shows the path in the `Log:` line.

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

### Typed Parameter Bindings (`parameters:` / `with:`)

Instead of leaking the entire parent context via `context_passthrough`, a child loop can declare a typed input contract and callers bind only the values the child needs:

**Child loop — declare the contract:**

```yaml
name: "recursive-refine"
parameters:
  input:
    type: string
    required: true
    description: Issue ID(s) to refine (comma-separated list accepted)
initial: parse_input
...
```

**Parent loop — bind values explicitly:**

```yaml
states:
  refine_issue:
    loop: "recursive-refine"
    with:
      input: "${captured.input.output}"   # bind parent capture to child parameter
    on_success: "get_passed_issues"
    on_failure: "skip_and_continue"
```

The child's context is seeded with only the declared `with:` values (plus any declared defaults). The parent context does not leak into the child — a rename in the parent cannot silently break the child.

**Parameter types**: `string`, `integer`, `number`, `boolean`, `enum`, `path`

**`with:` field rules:**
- `with:` is mutually exclusive with `context_passthrough` on the same state
- `required: true` parameters must appear in `with:` (the validator raises an error at load time if missing)
- `with:` keys must match names declared in the child's `parameters:` block (unknown keys are rejected)
- Values support `${variable}` interpolation — type validation runs after interpolation

**When to use `with:` vs. `context_passthrough`:**

| Approach | Best for |
|----------|----------|
| `with:` | Reusable child loops with a stable input contract; avoids context coupling |
| `context_passthrough: true` | Legacy loops or when the child genuinely needs the full parent context |

For full schema details and the `ParameterSpec` dataclass API, see [`scripts/little_loops/fsm/schema.py`](../../scripts/little_loops/fsm/schema.py) and [`scripts/little_loops/loops/recursive-refine.yaml`](../../scripts/little_loops/loops/recursive-refine.yaml) for a real-world example.

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

Six libraries ship with little-loops, all in `scripts/little_loops/loops/lib/`:

#### `lib/common.yaml` — type-pattern fragments

Generic structure fragments (action_type + evaluate combinator) used by all built-in loops:

| Fragment | Description | Provides | Caller must supply |
|----------|-------------|----------|--------------------|
| `shell_exit` | Shell command evaluated by exit code. | `action_type: shell` + `evaluate.type: exit_code` | `action`, routing (`on_yes`, `on_no`) |
| `retry_counter` | Increments a counter file and checks if still below `context.max_retries`. | Shell counter script + `output_numeric` evaluator | `context.counter_key`, `context.max_retries`, routing |
| `llm_gate` | LLM prompt state with structured yes/no output. When the prompt performs multiple MCP tool calls followed by synthesis (~10 calls), set `timeout: 1500` or higher at the state level; the 3600s executor fallback is bypassed by any loop-level `default_timeout:`. | `action_type: prompt` + `evaluate.type: llm_structured` | `action`, `evaluate.prompt`, routing (`on_yes`, `on_no`), optionally `timeout` |
| `numeric_gate` | Shell command evaluated by numeric output comparison. | `action_type: shell` + `evaluate.type: output_numeric` | `action`, `evaluate.operator`, `evaluate.target`, routing (`on_yes`, `on_no`) |
| `with_rate_limit_handling` | Applies per-state two-tier rate-limit retry handling: 3 short retries (30 s base backoff) then the default long-wait ladder (5 min → 15 min → 30 min → 1 h) up to a 6 h wall-clock budget. | `max_rate_limit_retries: 3`, `rate_limit_backoff_base_seconds: 30`, plus inherited `rate_limit_long_wait_ladder` and `rate_limit_max_wait_seconds` defaults | `on_rate_limit_exhausted` (target state name) |
| `parse_tagged_json` | Shell state that extracts a tagged JSON line from LLM output. Injects `action_type: shell` only; caller supplies all extraction and normalization logic in `action:`. Nested `${captured.${context.var}.output}` interpolation is NOT supported (single-pass engine) — use the captured variable's literal name directly in `action:`. | `action_type: shell` | `action` (extraction + normalization script referencing captured output by literal name), `capture`, `evaluate` (`output_json` recommended), routing (`on_yes`, `on_no`) |
| `convergence_gate` | Shell state evaluated by the convergence evaluator toward a numeric target. Callers supply only overrides; `type: convergence` and `direction: maximize` are fixed by the fragment. | `action_type: shell` + `evaluate.type: convergence` + `evaluate.direction: maximize` | `action`, `evaluate.target`, `evaluate.tolerance`, routing (`route.target`, `route.progress`, `route.stall`); optionally `evaluate.previous`, `route.error` |

#### `lib/benchmark.yaml` — Harbor-format benchmark runner

Single `run_benchmark` fragment that evaluates a scorer command's exit code and float stdout:

| Fragment | Description | Provides | Caller must supply |
|----------|-------------|----------|--------------------|
| `run_benchmark` | Run a Harbor-format benchmark task directory and evaluate by scorer result. | `action_type: shell` + `evaluate.type: harbor_scorer` | `action` (scorer command), routing (`on_yes`, `on_no`) |

Scorer contract: the `action` command must print a bare float (e.g. `0.85`) to stdout and exit 0 on success. The `harbor_scorer` evaluator maps the result to verdicts: `yes` (exit 0 + float), `no` (exit non-zero), `error` (exit 0 + non-float stdout).

```yaml
import:
  - lib/benchmark.yaml

states:
  score:
    fragment: run_benchmark
    action: "my-scorer ${context.tasks_dir}"
    capture: benchmark_score   # stores the float score in captured.benchmark_score
    on_yes: pass
    on_no: fail
```

#### `lib/score-plan-quality.yaml` — plan-quality scoring fragment

Single `score_plan_quality` fragment for scoring `rn-plan` plan trees on four plan-quality dimensions (subtask success rate, depth/complexity ratio, redundancy, coverage gaps). Used by `rn-plan-apo`:

| Fragment | Description | Provides | Caller must supply |
|----------|-------------|----------|--------------------|
| `score_plan_quality` | Score a set of `rn-plan` plan trees on four plan-quality dimensions and emit an aggregate `PLAN_QUALITY=<integer 0-100>` line. | `action_type: prompt` + default `timeout: 300` | `action` (scoring prompt body), `capture` |

```yaml
import:
  - lib/score-plan-quality.yaml

states:
  score_plans:
    fragment: score_plan_quality
    action: |
      (scoring prompt body — see rn-plan-apo.yaml for the canonical example)
    capture: plan_scores
    next: compute_gradient
```

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
| `ll_issues_next_issue` | `ll-issues next-issue` | Get next-priority issue file path. Selection order is config-driven via `issues.next_issue.strategy` (default: `confidence_first`). |
| `ll_history_summary` | `ll-history summary` | Print completed issue history summary. Override `action` to add `2>/dev/null` fallback. |
| `ll_check_links` | `ll-check-links 2>&1` | Check markdown docs for broken links. |
| `ll_messages` | `ll-messages --stdout` | Extract user messages from session logs. Override `action` to add `--skill`, `--examples-format`, etc. |
| `ll_deps` | `ll-deps check` | Validate cross-issue dependency references. |
| `ll_sprint_list` | `ll-sprint list` | List all defined sprint files. |
| `ll_parallel` | `ll-parallel` | Process issues concurrently using isolated worktrees. |
| `ll_workflows` | `ll-workflows` | Identify workflow patterns from user message history. |
| `ll_loop_run` | `ll-loop run ${context.loop_name}` | Run a named FSM loop as a sub-process. Requires `context.loop_name`. |

All `lib/cli.yaml` fragments use `action_type: shell` + `evaluate.type: exit_code`.

#### `lib/prompt-fragments.yaml` — reusable LLM prompt fragments

Pre-built prompt-type fragments for common LLM-driven commit and authoring tasks. Import with `lib/prompt-fragments.yaml`:

```yaml
import:
  - lib/prompt-fragments.yaml

context:
  commit_message: "refactor: apply changes"

states:
  commit_changes:
    fragment: ll_commit
    next: done
```

| Fragment | Description | Provides | Caller must supply |
|----------|-------------|----------|--------------------|
| `ll_commit` | Prompt state that invokes `/ll:commit ${context.commit_message}`. No evaluate block — it's a fire-and-forget prompt state. | `action_type: prompt` + `action: /ll:commit ${context.commit_message}` | `context.commit_message` (in the loop's `context:` block), `next:` |

#### `lib/harness.yaml` — Playwright screenshot fragment

Shell fragment for capturing screenshots of generated HTML/SVG artifacts. Used by the `generator-evaluator` oracle sub-loop and the five harness loops (`html-website-generator`, `html-anything`, `hitl-md`, `p5js-sketch-generator`, `svg-image-generator`).

```yaml
import:
  - lib/harness.yaml

states:
  capture_screenshot:
    fragment: playwright_screenshot
    # Variant B (default): caller supplies context.file_url and context.screenshot_path
    on_yes: score
    on_no: score
    on_error: score
```

| Fragment | Description | Provides | Caller must supply |
|----------|-------------|----------|--------------------|
| `playwright_screenshot` | Runs `playwright screenshot` and emits `CAPTURED` on success. Default action uses `context.file_url` and `context.screenshot_path` with `2>&1` stderr capture (Variant B). Variant A callers needing `$(pwd)/` expansion must override `action:` at the call site. | `action_type: shell` + `evaluate.type: output_contains` (`pattern: "CAPTURED"`) | `context.file_url`, `context.screenshot_path` (or override `action:`), routing (`on_yes`, `on_no`, `on_error`) |

Built-in loops import the libraries as `import: ["lib/common.yaml"]` or `import: ["lib/cli.yaml"]`. User loops in `.loops/` can do the same — built-in fragment libraries resolve automatically, so no copying or symlinking is required. You can also define your own local fragments in your loop file or a local library.

### When to Use Fragments vs. Sub-Loops

| Approach | Best for |
|----------|----------|
| Fragment (`fragment:`) | Sharing a state *structure* (action_type + evaluate) across many states in one or more loops |
| Sub-loop (`loop:`) | Reusing a complete, well-tested loop as a pipeline stage with its own execution context |
| Inline states | Custom logic that doesn't map to any reuse pattern |

Fragment resolution is parse-time only — the engine never sees `fragment:` keys and there is no runtime overhead.

---

## Loop Template Inheritance via `from:`

When fragment-level reuse isn't enough — e.g., several variants of the same loop share a category, an iteration cap, default context, and a `done:` terminal state — the `from:` field inherits an entire loop template. The child YAML overrides only the deltas; everything else is taken from the parent.

### Syntax

```yaml
name: my-scan-refine
from: issue-refinement       # parent loop name (resolved like sub-loop calls)
states:
  execute:
    prompt: "/ll:scan-codebase"
```

The `from:` value is resolved by `resolve_loop_path()` — the same lookup used everywhere else: project `loops/` first, built-in `scripts/little_loops/loops/` as a fallback. A name (no extension) finds `<name>.yaml` or `<name>.fsm.yaml`; a relative path like `lib/apo-base` finds `loops/lib/apo-base.yaml`.

### Merge Rules

The loader deep-merges parent and child *before* validation:

- **Scalars** (`name`, `initial`, `description`, `category`, `max_iterations`, `timeout`, `on_handoff`, single-string `on_*` fields, etc.) — child wins.
- **Lists** (`labels`) — child replaces parent's list outright (no append).
- **Dicts** (`context`, `states`, `route`, nested `evaluate`) — recursive merge: child keys override the same parent keys; parent keys the child does not redefine are preserved.

The child must declare its own `name:`. Everything else is optional — a child can omit `initial:`, `states:`, etc. when the parent already provides them.

The `from:` key is stripped from the merged result, so it never reaches the FSM engine.

### Inheriting Fragments

A parent loop's `import:`/`fragments:` blocks are merged into the child first, *then* `resolve_fragments` runs on the merged result. So a child can reference any fragment its parent imports without re-importing the library.

### Cycle Detection

`A → B → A` (or any longer chain that loops back) raises `ValueError` with the full chain path:

```
Circular `from:` chain: a -> b -> a
```

A missing parent raises `FileNotFoundError` from `resolve_loop_path`.

### Discovery: `lib/` is Hidden

Inheritance-only base templates live under `loops/lib/` and are excluded from `ll-loop list` because they aren't runnable FSMs on their own. Discovery recurses into subdirectories of `loops/` (so nested runnable loops like `oracles/oracle-capture-issue` show up) but filters every candidate through `is_runnable_loop()` — a YAML must have `name`, `initial`, and either `states` or `flow` to be listed. `lib/` files omit `initial:`, so they're filtered out by the predicate, not by a directory-name check. Use a `lib/<name>` path in `from:` to point at them:

```yaml
name: apo-beam
from: lib/apo-base
initial: generate_variants
states:
  generate_variants: { ... }
```

### Worked Example: APO Variants

`scripts/little_loops/loops/lib/apo-base.yaml` (not runnable directly):

```yaml
name: apo-base
category: apo
description: |
  Base skeleton for Automated Prompt Optimization (APO) loops. Inherited via
  `from: lib/apo-base`.
max_iterations: 20
timeout: 3600
on_handoff: spawn
context:
  prompt_file: system.md
states:
  done:
    terminal: true
```

`scripts/little_loops/loops/apo-beam.yaml`:

```yaml
name: apo-beam
from: lib/apo-base
description: |
  Beam search prompt optimization (APO technique): ...
initial: generate_variants
context:
  eval_criteria: ""
  beam_width: 4
  target_score: 90
states:
  generate_variants: { ... }
  score_variants: { ... }
  select_best: { ... }
  route_convergence: { ... }
  # `done` inherited from apo-base
```

The merged loop has every field from `apo-base` — `category`, `max_iterations`, `timeout`, `on_handoff`, `context.prompt_file`, the `done` state — plus everything `apo-beam` declares on top, with the `apo-beam` `name:` and `description:` winning the scalar-override.

### Validation, Diagrams, and `/ll:review-loop`

`ll-loop validate`, `ll-loop info`, and `/ll:review-loop` all consume the *materialized* loop returned by `load_and_validate`, so they see the merged graph. The raw YAML in `ll-loop info --raw` displays what the author wrote, not the merged form — useful for understanding *why* a state behaves a certain way.

### When to Use `from:` vs. Fragments vs. Sub-Loops

| Approach | Best for |
|----------|----------|
| `from:` | Sharing the *whole loop skeleton* across multiple variants (same category, iteration cap, terminal state, default context, etc.) |
| Fragment (`fragment:`) | Sharing a single *state structure* (action_type + evaluate) across many states |
| Sub-loop (`loop:`) | Reusing a complete loop as a pipeline stage with its own execution context |

`from:` resolution, like fragment resolution, is parse-time only — the engine never sees the `from:` key and there is no runtime overhead.

---

## Linear Flow Shorthand via `flow:`

For simple linear pipelines where each state proceeds unconditionally to the next, the `flow:` key replaces the verbose `states:` map with an ordered list:

```yaml
name: lint-and-test
description: "Run lint, then tests"
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

`initial:` must be set explicitly to the first state's name — it is not inferred from the `flow:` list. The last entry in `flow:` is implicitly `terminal: true`. Every non-terminal entry generates a `next:` transition, which routes all outcomes (success **and** error) forward to the next state unless you override error handling in `state_defs:` (see below).

### Conditional branching in `flow:`

Use the `name?yes_target:no_target` ternary syntax for states that need to branch:

```yaml
name: check-and-run
initial: check_ready
flow:
  - check_ready?run_impl:done
  - run_impl
  - done

state_defs:
  check_ready:
    action: "ll-issues show FEAT-42 --json | jq -e '.status == \"open\"'"
    fragment: shell_exit
  run_impl:
    action: "/ll:manage-issue FEAT-42"
```

`check_ready` receives `on_yes: run_impl` and `on_no: done`; `run_impl` receives `next: done`. Ternary entries only control routing — add the state body in `state_defs:`.

### Error handling in `flow:` states

Non-branching states use `next:` (not `on_yes`/`on_no`/`on_error`), so by default all outcomes — including non-zero exit codes — advance to the next state. To add error recovery for a specific state, add `on_error:` to its `state_defs:` entry:

```yaml
state_defs:
  run_tests:
    action: "python -m pytest scripts/tests/"
    on_error: diagnose       # overrides the unconditional next: for error cases
```

When `on_error` is present on a `next:`-based state, a non-zero exit routes to `on_error` and a zero exit routes to `next`.

### Relationship to `states:`

`flow:` and `states:` are mutually exclusive — the validator rejects a YAML that defines both. When a child loop (via `from:`) supplies its own `flow:`, it overrides the parent's `states:` entirely.

`state_defs:` supplies optional action/evaluate bodies that are deep-merged into the generated state skeletons. Omit it when a state inherits its body from a fragment.

### When to use `flow:` vs. `states:`

| Approach | Best for |
|----------|----------|
| `flow:` | Simple linear pipelines or pipelines with one or two conditional branches |
| `states:` | Complex graphs with multiple convergent paths, retry loops, or multi-branch routing |

---

## Troubleshooting

| Problem | Cause | Fix |
|---------|-------|-----|
| Loop stuck in a cycle | Fix action isn't changing the result the evaluator sees | Check `ll-loop history` — if the same verdict repeats, adjust the fix action. The executor also terminates automatically when any single edge is traversed more than `max_edge_revisits` times (default 100) with `terminated_by="cycle_detected"` |
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
