# Built-in Loops Reference

> **When to use this**: Look up a specific built-in loop — what it does, its context
> variables, FSM flow, and invocation examples. If you're new to loops, start with the
> [Loops Guide](LOOPS_GUIDE.md) for concepts, authoring, and troubleshooting; use the
> guide's [Choose Your Loop](LOOPS_GUIDE.md#choose-your-loop) decision tree to find the
> right loop for a task.

Run any loop with `ll-loop run <name>`. Copy one into your project to customize it with
`ll-loop install <name>`.

## Contents

- [Built-in Loops](#built-in-loops) — the full catalog, grouped by purpose
  - [Routing](#routing) · [General-Purpose](#general-purpose) · [API Adoption](#api-adoption) · [Research & Knowledge](#research--knowledge) · [Issue Management](#issue-management) · [Code Quality](#code-quality) · [Evaluation](#evaluation) · [Reinforcement Learning (RL)](#reinforcement-learning-rl) · [APO](#automatic-prompt-optimization-apo) · [Harness Examples](#harness-examples)
- [Cluster vs. Composer vs. Router](#cluster-vs-composer-vs-router) — picking an orchestrator
- [Prompt Optimization Loops (APO)](#prompt-optimization-loops-apo)
- [Evaluation Loops](#evaluation-loops)
- [`harness-optimize` with `.ll/program.md`](#harness-optimize-with-llprogrammd)
- [Built-in Fragment Libraries](#built-in-fragment-libraries)

---

## Built-in Loops

These loops ship with little-loops and cover common workflows. Install one to `.loops/` to customize it:

```bash
ll-loop install <name>       # Copies to .loops/ for editing
```

### Routing

*Choose this when you know what you want done but not which loop to run — `loop-router` classifies the goal and dispatches to the best-fit loop.*

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

### General-Purpose

*Choose these for tasks that don't fit a specialist group: definition-of-done driven work, spec-to-project builds, dataset curation, single-issue refinement.*

| Loop | Description |
|------|-------------|
| `dataset-curation` | Scan raw data, quality-gate each item, fix or reject, balance distribution, validate schema, and publish a curated dataset |
| `sft-corpus` | Stage session transcripts, enrich with history.db session-quality metadata, filter by opt-in quality predicates, and publish SFT training corpus |
| `general-task` | Definition-of-done driven task loop — define verifiable criteria first, then execute and verify until all criteria pass |
| `rn-build` | **(Recommended)** Capstone recursive spec-to-project builder: spec validation → tech research → design artifacts → scope EPIC → enumerate children → recursive-refine (depth-first, decomposition-aware) → eval harness → goal-cluster (rn-implement/value_ranked) → eval gate → structured JSON result. |
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

> **Declaring required inputs**: If a loop's `input_key` is mandatory, add `required_inputs: ["<key>"]` to the loop YAML. The runner checks each listed key before starting and exits with code 1 if any key is absent or empty, with a message naming the loop and the missing key. Loops without `required_inputs` behave as before. `ll-loop validate` also emits a WARNING when a loop sets a custom `input_key` but omits `required_inputs`, nudging authors to declare intent explicitly.
>
> ```bash
> # Equivalent: pass multiple context vars as a JSON object (auto-unpacked)
> ll-loop run recursive-refine '{"input": "FEAT-42,FEAT-43"}'
> ll-loop run outer-loop-eval '{"loop_name": "issue-refinement", "input": "some value"}'
> ```

The loop follows a structured cycle:

1. **Define Done** — writes verifiable acceptance criteria to `${context.run_dir}/dod.md`. When the task has a runtime surface (running code, executing tests, installing a service, producing output at runtime), the DoD must include runtime-behavior criteria — static file/import checks alone are insufficient.
2. **Plan** — decomposes the task into discrete steps in `${context.run_dir}/plan.md`
3. **Execute** — five sub-states handle crash recovery, step selection, implementation, verification, and marking:
   - `resume_check` (shell): runs **once after `plan`** to detect an in-flight checkpoint from a previous crashed run. If `${context.run_dir}/checkpoint.json` exists, validates the task fingerprint (`task_hash` in the JSON must match `${context.input_hash}` — cross-task checkpoints are discarded) and checks that `${context.run_dir}/current-step.txt` also exists (inconsistent file sets → `RESUME_CLEAN`). If the output files listed in `${context.run_dir}/last-files.txt` are all present on disk, emits `RESUME_SKIP` and routes to `mark_done` (step completed but never marked). If the checkpoint exists but files are missing, deletes the checkpoint and emits `RESUME_CLEAN`, routing to `select_step` for a clean re-execution. If no checkpoint exists, emits `RESUME_NONE` and routes normally to `select_step`.
   - `select_step` (shell): finds the first unchecked plan step, writes it to `${context.run_dir}/current-step.txt`, writes a crash-recovery checkpoint to `${context.run_dir}/checkpoint.json` (JSON with `in_flight_step`, `timestamp`, and `task_hash` fields), and emits `SELECTED_STEP: <text>`. Routes to `do_work` on success, or directly to `check_done` if no unchecked steps remain.
   - `do_work` (prompt): reads the selected step from the temp file, implements **only** that step (must not modify the plan or DoD files), and writes `LAST_FILES: <paths>` to `${context.run_dir}/last-files.txt`. Has a 900s timeout to bound per-step cost. Captured as `work_result`.
   - `verify_step` (shell): reads `${context.run_dir}/last-files.txt` and runs `python -m pytest` on any Python files listed. Emits `VERIFY_PASS` or `VERIFY_FAIL`; routes to `mark_done` on pass, `continue_work` on fail.
   - `mark_done` (shell): marks the first unchecked step `[x]` in the plan file using a cross-platform `awk` pattern, then removes the current-step temp file and the in-flight checkpoint (if present). Routes to `check_done`.
4. **Verify** — reads both the DoD and the plan, then applies a three-step verification policy:
   1. *Plan-vs-DoD coverage* — for every plan step, confirms at least one DoD criterion covers it; adds new criteria for any uncovered step.
   2. *Delta-scoped criterion verification* — `do_work` captures `LAST_FILES` (every file created or modified) in `captured.work_result.output` and writes it to `${context.run_dir}/last-files.txt`; `select_step` captures the step text in `captured.selected_step.output`. `check_done` reads these and only re-verifies criteria that are plausibly affected by the delta; previously-`[x]` criteria outside the delta are kept without re-running their commands, bounding per-iteration cost to the slice of criteria the latest step could have touched.
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

### API Adoption

*Choose these when integrating an unfamiliar third-party API or SDK and you want each assumption proven against the Learning-Test Registry before code is written.*

> For registry mechanics, record lifecycle, the `type: learning` FSM state reference, and guidance on picking among these loops, see [LEARNING_TESTS_GUIDE.md](LEARNING_TESTS_GUIDE.md).

| Loop | Description |
|------|-------------|
| `adopt-third-party-api` | End-to-end API adoption pipeline — scrapes a vendor docs URL via `/ll:scrape-docs`, enumerates up to 7 significant endpoints/features, proves each via `ready-to-implement-gate`, and writes a citation-linked integration playbook to `docs/integration-<domain>.md`. Partial coverage (some targets refuted or exhausted) still produces a playbook with a top warning block listing unverified sections. |
| `ready-to-implement-gate` | Sub-loop primitive — given a list of external-API targets, proves each against the Learning-Test Registry via `/ll:explore-api`; routes `done` when all targets are proven, `blocked` when any are refuted or exhausted. Used as a child by `adopt-third-party-api` and `assumption-firewall`, but runnable standalone to gate any pre-implementation proof step. |
| `assumption-firewall` | Issue gating loop — extracts up to 7 external-API assumptions from an issue file via LLM, classifies each as testable (proven via `ready-to-implement-gate`) or untestable (recorded via `--assume` flag as `result: untested` in the Learning-Test Registry), and routes `done` (all testable proven), `blocked` (any testable refuted), or `no_external_deps` (no testable assumptions found). Use before starting implementation on issues that touch unfamiliar third-party APIs. |
| `integrate-sdk` | Proof-driven SDK integration — branches on existing usage (code branch) vs. greenfield (docs branch), enumerates up to 7 required API surfaces, proves each via `ready-to-implement-gate`, then scaffolds integration code with `# Verified: .ll/learning-tests/<slug>.md` citations. Blocks with a structured diagnosis if any surface is refuted or citations don't resolve to proven records. |
| `learning-tests-audit` | Registry health audit — scans the Learning Test Registry for stale records via a three-phase detection pipeline (installed-package enumeration → LLM-assisted package classification → PyPI/npm registry release-date comparison), bulk-marks stale records via `ll-learning-tests mark-stale`, and produces a four-section triage report (newly stale, already stale, refuted, open TODOs). Run at sprint start to surface registry maintenance items before they cause integration drift. |
| `proof-first-task` | Opt-in wrapper that gates any implementation loop on `assumption-firewall` — extracts external-API assumptions from an issue file, proves each against the Learning-Test Registry, then delegates to a caller-specified impl loop (default `general-task`). When no `issue_file` is given, skips the gate and runs the impl loop directly. |
| `migrate-sdk-version` | SDK migration helper — re-proves stale learning-test records after a dependency bump, classifying each as still-valid, needs-upgrade, or refuted, and producing a triage report |

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

### Research & Knowledge

*Choose these when the deliverable is knowledge — a cited research report, issues distilled from local documents, or a recursively self-scored plan — rather than a code change.*

| Loop | Description |
|------|-------------|
| `deep-research` | Iterative web research synthesis — generates search queries, performs web searches, evaluates sources, identifies coverage gaps, and produces a structured Markdown report with citations; delegates inner FSM chain to `oracles/research-coverage` (ENH-1876) |
| `deep-research-arxiv` | Arxiv-only sibling of `deep-research` — constrains web search to `site:arxiv.org`, scores sources on relevance + recency (derived from arxiv submission date) instead of credibility, and emits an arxiv-ID-keyed sources table plus a `## BibTeX` section ready to drop into a `.bib` file; delegates inner FSM chain to `oracles/research-coverage` with `academic_mode=true` (ENH-1876) |
| `apply-research` | Document ingestion pipeline — reads local `.txt`, `.md`, or `.pdf` files; scores each extracted idea by relevance to the project (0–1); filters below threshold; synthesizes actionable issue descriptions; and captures Issues via `/ll:capture-issue`. Use when you have research papers, RFCs, or design docs and want them translated into project issues automatically. |
| `rn-plan` | Recursive task planning with self-scoring rubric — accepts a natural language task description, generates a 8-dimension rubric (breadth, depth, complexity, clarity, consistency, logic_strategy, feasibility, testability, risk_mitigation), then iteratively researches and refines the plan until all dimensions reach VERY-HIGH; delegates the per-iteration research chain to `oracles/plan-research-iteration` |
| `rn-refine` | Recursive refinement loop for an existing plan document — accepts a path to a plan `.md` file, calibrates a 9-dimension rubric to the plan's current state, then iteratively researches and refines until all dimensions reach VERY-HIGH; delegates the per-iteration research chain to `oracles/plan-research-iteration` with `overwrite_source=true` for in-place file updates |
| `oracles/plan-research-iteration` | Reusable research-and-synthesize oracle shared by `rn-plan` and `rn-refine` — runs one iteration: classify what research is needed (NEEDS_FILES or NEEDS_WEB) → route to file or web research → synthesize findings into `plan.md`; the `overwrite_source` parameter gates `rn-refine`'s in-place source-file overwrite; invoked via `loop: oracles/plan-research-iteration` with `with:` context passthrough |
| `rn-implement` | Queue orchestrator for recursive plan-and-implement — manages a depth-bounded issue queue, delegating per-issue remediation to `rn-remediate` and decomposition to `rn-decompose` |
| `rn-decompose` | Sub-loop for issue decomposition (size review → child detection → enqueue with cycle detection), extracted from `rn-implement` Phase 5 |
| `rn-remediate` | Sub-loop for iterative deepening remediation cycle (diagnose → remediate → converge), extracted from `rn-implement` |

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

#### `apply-research` — Translating Local Documents into Issues

For translating *local* research files (papers, RFCs, design docs) into project issues, use `apply-research` instead of `deep-research`:

```bash
# Single PDF (converted to Markdown via pandoc before reading)
ll-loop run apply-research "path/to/paper.pdf"

# Multiple files, higher relevance bar
ll-loop run apply-research "paper.pdf notes.md" \
  --context relevance_threshold=0.7 \
  --context max_issues_per_file=5
```

The loop scores each extracted idea (0–1 relevance), drops below-threshold items, synthesizes concrete issue descriptions, and calls `/ll:capture-issue` for each. A summary report lists captured IDs and filtered counts. See [`## apply-research`](../reference/loops.md#apply-research) for the full state graph and output artifacts.

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
    → check_substrate   (llm: validate plan actions against env constraints; ENH-2098)
        on_yes (feasible)   → research_iteration
        on_no/partial       → generate_rubric  (revise plan before iterating)
          → research_iteration (oracle: classify→research→synthesize→score)
              on_yes (ALL_VERY_HIGH) → done
              on_no  (ITERATE)       → research_iteration (next iteration)
```

> **`check_substrate` gate** (ENH-2098): After the initial rubric is generated, an LLM feasibility check validates that every proposed action is achievable in the target execution environment (shell commands, MCP tool access, file write permissions, token budget). Infeasible plans route back to `generate_rubric` for revision before any research is run. See [`HARNESS_OPTIMIZATION_GUIDE.md` § check_substrate](../HARNESS_OPTIMIZATION_GUIDE.md) for configuration details.

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

### `rn-implement` — Queue Orchestrator for Recursive Plan-and-Implement

**Technique**: Queue orchestrator that manages a depth-bounded issue queue. Accepts an issue ID (or comma-separated list), initialises tracking files, then loops: dequeue an issue → depth gate → delegate remediation to `rn-remediate` → on failure, delegate decomposition to `rn-decompose` → enqueue children with cycle detection → repeat until queue is empty or `max_iterations` is exhausted. Domain logic (diagnosis, dimensional routing, convergence detection) lives in the delegated sub-loops — `rn-implement` is a pure orchestrator with no LLM calls of its own.

**When to use**: When an issue is too large for a single implementation pass and needs recursive decomposition — the issue is split into children, each child is independently remediated, and any child that still fails is further decomposed. This replaces the old monolithic implementation approach with a structured divide-and-conquer strategy. Accepts a comma-separated list of issue IDs for multi-issue seed queues.

**Usage:**

```bash
# Single issue
ll-loop run rn-implement "<issue-id>"

# Multiple seed issues
ll-loop run rn-implement "FEAT-1808,ENH-1842"
```

**Sub-loop delegation:**

| Sub-loop | Role | Route | Invoked when |
|----------|------|-------|-------------|
| `rn-remediate` | Diagnose → remediate → converge on a single issue | `on_success→dequeue_next`, `on_failure→run_decomposition` | Every dequeued issue |
| `rn-decompose` | Size review → child detection → enqueue with cycle detection | `on_success→dequeue_next`, `on_failure→skip_issue` | Remediation fails or stalls |

**Context variables:**

| Variable | Default | Description |
|----------|---------|-------------|
| `readiness_threshold` | `85` | Confidence score threshold for readiness gate (int, 0–100) |
| `outcome_threshold` | `75` | Outcome confidence threshold for implementation success (int, 0–100) |
| `max_depth` | `3` | Maximum decomposition depth; issues at or beyond this depth are capped |
| `max_remediation_passes` | `3` | Maximum remediation attempts per issue before escalation to decomposition |
| `schedule_mode` | `"fifo"` | Scheduler: `"fifo"` (default, pop queue head) or `"value_ranked"` (select highest-value ready issue each tick) |
| `run_dir` | runner-injected | Per-run artifact directory (`.loops/runs/rn-implement-{timestamp}/`); created automatically before the `init` state |

**`schedule_mode: value_ranked`**

When set, each tick the scheduler:
1. **Filters** the queue to the *ready set* — issues whose `blocked_by` deps are all `done` and that are not in `blocked.txt`.
2. **Ranks** the ready set by composite score: `priority_weight` (P0=100 … P5=10) + `impact/effort` ratio × 10 (from `ll-issues impact-effort`), tie-broken by depth (deeper/more-recently-decomposed issues win at equal score to preserve subtree-first resolution).
3. **Pops** the highest-score issue, replicating the same post-conditions as FIFO (`captured.input`, `current_depth.txt`, `visited.txt`, `dequeue_count.txt`).

If the ready set is empty (all remaining issues are blocked), the scheduler exits as if the queue were empty and the run terminates with a summary. Use `"fifo"` (the default) to preserve the original unconditional head-pop behaviour.

```bash
# Value-ranked scheduling
ll-loop run rn-implement "FEAT-1808,ENH-1842,BUG-1001" \
  --context schedule_mode=value_ranked
```

**`blocked_by` pre-gate** (ENH-2008)

Before entering the remediation budget, every dequeued issue passes through a lightweight two-state gate:

1. `check_blocked_by` (shell) — parses the issue's frontmatter directly and writes the set of unmet `blocked_by` IDs to `blocked_by_unmet_<ID>.txt`.
2. `route_blocked_by` (output_contains) — if any unmet blockers were found, routes to `mark_deferred` with a message naming the specific blockers; otherwise routes to `check_depth`.

This gate applies to **both** `fifo` and `value_ranked` scheduling — it is not the same as `value_ranked`'s ready-set filter (which also checks `blocked.txt`). The pre-gate catches structural blockers *before* spending the `max_remediation_passes` budget on an issue that prose remediation cannot unblock. Fail-open: if `ll-issues show` cannot parse the frontmatter the gate passes, so a missing or malformed `blocked_by` field never stalls the queue.

**Output artifacts** (written to `${context.run_dir}`):

| File | Description |
|------|-------------|
| `queue.txt` | Active issue queue (one ID per line) |
| `visited.txt` | Set of all enqueued IDs for cycle detection |
| `depth_map.txt` | Per-issue depth assignments (`<ID> <depth>`) |
| `depth_capped.txt` | Issues skipped due to max_depth cap |
| `skipped.txt` | Issues skipped (genuinely atomic/too-large decline, errors) |
| `deferred.txt` | Issues deferred after a remediation stall + no-children decline, with a dependency reason (BUG-2006); the issue's `status` is also set to `deferred` |
| `summary.json` | Final run summary (processed, implemented, decomposed, skipped, deferred, blocked, depth-capped) |

**FSM flow:**

```
init               (shell: seed queue from comma-separated input, init tracking files)
  → dequeue_next   (fragment: queue_pop — pop head of queue, mark visited, increment counter)
    → check_blocked_by  (shell: parse frontmatter, write blocked_by_unmet_<ID>.txt)
      → route_blocked_by  (evaluate: output_contains — any unmet blockers?)
        on_yes → mark_deferred (named blockers) → dequeue_next
        on_no  → check_depth
    → check_depth  (evaluate: output_numeric lt max_depth)
      on_yes → run_remediation
      on_no  → mark_depth_capped → dequeue_next
    → run_remediation   (sub-loop: rn-remediate, max_rate_limit_retries: 3)
      on_success (PASS)             → dequeue_next
      on_failure (FAIL/STALLED)     → run_decomposition
      on_error                      → skip_issue
      on_rate_limit_exhausted       → rate_limit_diagnostic
    → run_decomposition  (sub-loop: rn-decompose, max_rate_limit_retries: 3)
      on_success (children enqueued) → dequeue_next
      on_failure (no children)       → route_dec_stalled_origin
      on_error                       → skip_issue
  → route_dec_stalled_origin  (evaluate: rem_outcome contains STALLED_NEEDS_DECOMPOSE)
      on_yes (stall origin)           → mark_deferred   (BUG-2006)
      on_no  (genuinely atomic/large) → skip_issue
  → mark_deferred            (shell: append reason to deferred.txt, set status=deferred) → dequeue_next
  → skip_issue               (shell: append to skipped.txt) → dequeue_next
  → rate_limit_diagnostic    (shell: log ISO timestamp + ID) → dequeue_next
  → report (shell: write summary.json + human-readable summary) → done
```

**Notes**: The `report` state writes summary JSON before transitioning to the bare `done` terminal anchor (actions on terminal states are skipped by the runner). Sub-loop delegation uses `on_success`/`on_failure` routing (not `on_yes`/`on_no`), matching the composable-sub-loop convention. `max_iterations: 500`, `timeout: 28800`, `on_handoff: spawn`. See individual sub-loop sections below for their context variables and FSM flows.

### `rn-decompose` — Issue Decomposition Sub-Loop

**Technique**: Sub-loop that splits oversized issues into smaller child issues via a snapshot-before/snapshot-after pattern. Snapshots the active issue ID list before `/ll:issue-size-review --auto`, then diffs the post-review list with `comm -13` to detect net-new children. Each candidate is verified to contain an explicit `parent:` frontmatter reference or `"Decomposed from <PARENT_ID>"` body line before acceptance. Children that survive cycle detection are prepended depth-first to the parent orchestrator's queue.

**When to use**: Standalone when you suspect an issue is too large and want to decompose it before implementation. Also invoked automatically by `rn-implement` when remediation fails.

**Usage:**

```bash
# Standalone decomposition
ll-loop run rn-decompose "<issue-id>"

# Invoked by parent rn-implement with context
ll-loop run rn-decompose "<issue-id>" \
  --context parent_depth=1 \
  --context run_dir=.loops/runs/rn-implement-20260604T130000/
```

**Parameters** (populated by parent sub-loop caller via `with:`):

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `issue_id` | yes | — | Issue ID to decompose |
| `parent_depth` | no | `0` | Current recursion depth (inherited from parent's `current_depth`) |
| `run_dir` | yes | — | Parent loop's run directory for queue.txt coupling |

**Context variables:**

| Variable | Default | Description |
|----------|---------|-------------|
| `parent_depth` | `0` | Current recursion depth (overridden by parameter when invoked from parent) |

**Output artifacts** (written within `${context.run_dir}`):

| File | Description |
|------|-------------|
| `issues_before_<ID>.txt` | Pre-review snapshot of active issue IDs (sorted) |
| `issues_after_<ID>.txt` | Post-review snapshot of active issue IDs (sorted) |
| `diff_<ID>.txt` | Net-new IDs from `comm -13` |
| `children_<ID>.txt` | Filtered children (parent-verified, cycle-cleared) |

**FSM flow:**

```
snap_for_size_review  (shell: snapshot current scores and pre-review ID list)
  → run_size_review   (fragment: with_rate_limit_handling, /ll:issue-size-review --auto)
    → detect_children (shell: comm -13 diff pre/post ID lists, filter by parent: reference)
      on_yes (children found) → enqueue_children
      on_no  (no children)    → failed
    → enqueue_children  (shell: cycle detection via visited.txt + queue.txt union, depth-first prepend, write depth_map)
      → done
    → rate_limit_diagnostic → done
  → failed
```

**Notes**: Child detection is a two-step filter: (1) `comm -13` identifies net-new IDs created during size review, (2) each candidate's issue file must contain an explicit `parent:` frontmatter reference or `"Decomposed from <PARENT_ID>"` body line to avoid picking up unrelated concurrently-created issues. Cycle detection checks candidates against the union of `visited.txt` and `queue.txt`; cycle candidates are logged to `cycles.txt` and filtered out. Depth-first prepend means children are inserted at the head of the queue before existing entries, so the tree is explored depth-first. The parent is recorded as skipped (decomposed) in `skipped.txt`. `max_iterations: 100`, `timeout: 3600`, `on_handoff: spawn`.

### `rn-remediate` — Iterative Deepening Remediation Sub-Loop

**Technique**: Sub-loop running a 5-phase iterative deepening remediation cycle on a single issue. (1) **Assessment Bridge** — run confidence check and gate on scores; (2) **Dimensional Diagnosis** — parse all scores via `ll-issues show --json` and emit a diagnosis token routing to the appropriate remediation action; (3) **Remediation Actions** — execute the prescribed action (implement, decide, wire, refine); (4) **Re-Assessment** — re-run confidence check; (5) **Convergence Check** — compute 4-dimension deltas from pre/post score snapshots (confidence, outcome, complexity↓, ambiguity↓) and decide whether to pass, iterate, or stall. Terminates with `done` (issue implemented) or `failed` (escalate to parent for decomposition).

**When to use**: Standalone when you want focused iterative remediation on a single issue. Also invoked automatically by `rn-implement` for each dequeued issue.

**Usage:**

```bash
# Standalone remediation
ll-loop run rn-remediate "<issue-id>"

# With custom thresholds
ll-loop run rn-remediate "<issue-id>" \
  --context readiness_threshold=90 \
  --context max_remediation_passes=5
```

**Parameters** (populated by parent sub-loop caller via `with:`):

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `issue_id` | yes | — | Issue ID to remediate |
| `readiness_threshold` | no | `85` | Confidence score threshold for readiness gate (int, 0–100) |
| `outcome_threshold` | no | `75` | Outcome confidence threshold (int, 0–100) |
| `max_remediation_passes` | no | `3` | Max remediation iterations before escalation to decomposition |

**Dimensional diagnosis routing** — the `diagnose` state parses scores and emits one of five tokens:

| Token | Trigger condition | Routes to | Description |
|-------|-------------------|-----------|-------------|
| `IMPLEMENT` | confidence ≥ readiness AND outcome ≥ outcome | `implement` | Both thresholds met; proceed to implementation |
| `DECIDE` | `decision_needed` flag is true | `decide` | Issue has decision-needed; run `/ll:decide-issue` |
| `WIRE` | `ambiguity ≥ 15` | `wire` | Ambiguity too high; run `/ll:wire-issue` |
| `REFINE` | `complexity ≥ 15` OR `confidence < 50` | `refine` | Complexity or low confidence; run `/ll:refine-issue` |
| `DECOMPOSE` | `change_surface ≥ 15` | `failed` (falls through) | Surface area too large; escalate to parent for decomposition |

**Convergence delta computation** — the `check_convergence` state computes four deltas from pre/post score snapshots:

| Delta | Formula | Direction |
|-------|---------|-----------|
| `delta_confidence` | post − pre | positive = improved |
| `delta_outcome` | post − pre | positive = improved |
| `delta_complexity` | pre − post | inverted (lower complexity = improved) |
| `delta_ambiguity` | pre − post | inverted (lower ambiguity = improved) |

Convergence rules (first match wins): both scores at or above thresholds → `CONVERGED_PASS` → `implement`; `total_delta ≤ 2` + `decision_needed=true` → `NEEDS_MANUAL_REVIEW` → `failed` (parent marks issue blocked); `total_delta ≤ 2` + `decision_needed=false` → `CONVERGED_STALLED` → `check_remediation_budget` (under budget → re-enter `diagnose`; exhausted → `failed`); otherwise → `CONVERGED_IMPROVED` → check remediation budget (under budget → re-enter `diagnose`; exhausted → `failed`).

**Stall vs. too-large outcome tokens (BUG-2006, ENH-2107):** the non-pass terminals emit one of two decompose tokens so the parent can tell a *stall* from a genuinely *too-large* issue. The diagnose-`DECOMPOSE` path (`route_d_refine.on_no`, i.e. `change_surface ≥ 15`) emits plain `NEEDS_DECOMPOSE` — a legitimate "split this" signal. The budget-exhausted stall path (`check_remediation_budget.on_no`) emits `STALLED_NEEDS_DECOMPOSE`. A `CONVERGED_STALLED` result (zero delta, no `decision_needed`) routes to `check_remediation_budget` first (ENH-2107 — budget-gated retry), so `STALLED_NEEDS_DECOMPOSE` is only emitted after all remediation passes are exhausted. Because the stall token is a superstring of `NEEDS_DECOMPOSE`, the parent's substring match still triggers a decomposition attempt; only after `rn-decompose` returns `NO_CHILDREN` does the parent's `route_dec_stalled_origin` disambiguate — a stall → `mark_deferred` (status set to `deferred`, reason logged), a too-large/atomic decline → `skip_issue`.

**FSM flow** (abbreviated — 23 states across 5 phases):

```
Phase 1 — Assessment Bridge:
  assess → verify_scores_persisted → check_readiness → check_outcome → check_decision_needed
    (readiness passes → implement; decision_needed → decide; otherwise → diagnose)

Phase 2 — Dimensional Diagnosis:
  diagnose → route_d_implement → route_d_decide → route_d_wire → route_d_refine
    (first-matching token routes to corresponding action; DECOMPOSE falls through to failed)

Phase 3 — Remediation Actions:
  implement (shell: ll-auto --only) → done
  decide    (slash_command: /ll:decide-issue --auto) → re_assess
  wire      (slash_command: /ll:wire-issue --auto) → refine
  refine    (slash_command: /ll:refine-issue --auto --full-rewrite) → re_assess

Phase 4 — Re-Assessment:
  re_assess → verify_re_assess_scores → check_convergence

Phase 5 — Convergence:
  check_convergence → route_conv_pass → route_conv_improved → route_conv_manual_review → check_remediation_budget
    (PASS → implement; IMPROVED + under budget → diagnose; NEEDS_MANUAL_REVIEW → emit_needs_manual_review → failed;
     STALLED → check_remediation_budget (under budget → diagnose; exhausted → emit_stalled_needs_decompose → failed))
```

**Notes**: The Assessment Bridge short-circuits — if the initial `check_readiness` passes, the issue routes directly to `implement` without entering the diagnosis/remediation cycle. Dimensional diagnosis uses priority-ordered routing (IMPLEMENT > DECIDE > WIRE > REFINE > DECOMPOSE). The `DECOMPOSE` token is a terminal diagnosis — it falls through the routing chain to `failed`, signaling the parent orchestrator to delegate to `rn-decompose`. No bare `PASS` token is used (compound tokens only, guarded by `test_no_bare_pass_token`). The remediation budget counter is per-issue and persists across diagnosis re-entries within the same run. `max_iterations: 100`, `timeout: 14400`, `on_handoff: spawn`.

### `rn-build` — Spec-to-Project Capstone Orchestrator

**Category**: orchestration  
**File**: `scripts/little_loops/loops/rn-build.yaml`

End-to-end spec-to-project pipeline. Accepts a spec Markdown file and drives the full automated build: spec validation → tech research → design artifacts → **check_substrate** (ENH-2098) → commit → scope EPIC + feature stubs → issue refinement → eval harness → goal-cluster (batched `rn-implement`) → eval gate → structured JSON result.

> **`check_substrate` gate** (ENH-2098): After `design_artifacts` completes, an LLM feasibility check validates every proposed action against target environment constraints (shell commands, MCP tool access, file write permissions, token budget). Infeasible designs route back to `design_artifacts` for revision before project scoping begins. See [`HARNESS_OPTIMIZATION_GUIDE.md` § check_substrate](../HARNESS_OPTIMIZATION_GUIDE.md) for configuration details.

Use `rn-build` for all new spec-driven greenfield projects.

**Usage:**

```bash
ll-loop run rn-build --context spec=specs/sample.md
```

**Context variables:**

| Variable | Default | Description |
|----------|---------|-------------|
| `spec` | `""` | **Required.** Path(s) to spec file(s), comma-separated |
| `max_eval_retries` | `"2"` | Max `eval_gate` retry cycles before accepting a partial result |
| `resume_epic` | `""` | **Resume only.** EPIC ID from a prior run; skips the front half and re-enters `cluster_execute` |
| `resume_harness` | `""` | **Resume only.** Harness loop name from a prior run; passed to `eval_gate` when resuming |

#### Resuming a partial build (ENH-2016)

When `rn-build` exhausts `max_eval_retries`, `synthesize_result` emits a `resume_command`
field in its JSON output. Copy and run that command in a new session to re-enter
`cluster_execute` for the same EPIC without repeating the front half:

```bash
# Resume an interrupted build — skips init → tech_research → … → eval_harness
ll-loop run rn-build \
  --context resume_epic=EPIC-042 \
  --context resume_harness=myproject-harness
```

`resume_epic` and `resume_harness` are both required for a full eval-gate cycle on
resume. If `resume_harness` is omitted, `check_harness_name` will route directly to
`synthesize_result` (no eval gate run).

#### Spec file format

`rn-build` accepts any Markdown file as its spec. If the three target sections are present, the spec is used as-is. If any are missing, a `normalize_spec` pre-gate runs automatically before `tech_research` — output quality still scales with spec quality, but you are not required to pre-format the file correctly. Use `specs/SPEC_TEMPLATE.md` as a starting point.

**Target sections** (used by `normalize_spec` as the canonical format):

| Section | Purpose |
|---------|---------|
| `## Overview` | 2–4 sentences describing what the project does and why it exists |
| `## Core Features` | Bulleted list of top-level capabilities (aim for 5–15); each bullet becomes a candidate feature issue after `scope-epic` runs |
| `## Acceptance Criteria` | 2–3 high-level observable outcomes; `rn-build` uses these to configure the eval harness |

**Optional sections**: `## Data Model`, `## Non-Goals`, `## Tech Constraints`. When omitted, `rn-build` infers them from the required sections. Including them narrows the design space and reduces hallucinated constraints.

See `specs/SPEC_TEMPLATE.md` for a fully annotated template and `specs/sample.md` for a worked example.

**Spec normalization pre-gate** (ENH-2017)

When any of the three target sections are missing, `rn-build` runs a normalization pass before `tech_research`:

1. `check_structure` (non-LLM) — counts present sections via `grep`; routes to `llm_normalize` if fewer than 3 are found, or proceeds directly to `tech_research` if all 3 exist.
2. `llm_normalize` — infers and populates missing sections from whatever content is present; writes the normalized spec to `${context.run_dir}/spec_normalized.md`. The original file is never modified.
3. `verify_structure` (non-LLM) — confirms all 3 sections exist in the normalized output; proceeds to `tech_research` on success.

If normalization fails (e.g., the spec file is empty or contains no project description), the loop aborts with a clear error message referencing `specs/SPEC_TEMPLATE.md`. Specs that already contain all three sections skip normalization entirely.

#### Smoke test

Run the built-in integration test to confirm the full pipeline fires without an FSM crash:

```bash
# Manual one-shot run (30–120 min wall time)
ll-loop run rn-build \
    --context spec=specs/sample.md \
    --context max_eval_retries=0

# Automated integration test (requires PYTEST_INTEGRATION=1)
PYTEST_INTEGRATION=1 python -m pytest scripts/tests/test_rn_build.py::TestE2E -v -s
```

**Manual checklist** — after `ll-loop run` completes, verify:

1. Exit code is 0 (no FSM crash)
2. `.loops/runs/rn-build-<timestamp>/epic-id.txt` exists (`scope_project` completed)
3. Dispatch output does **not** contain `eval-driven-development`
4. Dispatch output contains `goal-cluster` (sub-loop header `== loop: goal-cluster …`)
5. Dispatch output contains `rn-implement` (dispatched by `goal-cluster`)
6. Output contains `SYNTHESIS_RESULT:` followed by valid JSON

Pass `--context max_eval_retries=0` to skip the `eval_gate` retry cycle and reduce wall time.

### Issue Management

*Choose these to process the `.issues/` backlog: refine, decompose, and implement issues one at a time, by sprint, or across the whole backlog.*

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
  │           ├─ YES → implement_chain (sub-loop: oracles/implement-issue-chain)
  │           │           └─ [get_passed_issues → implement_next → go_no_go → implement_issue]
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
         │         ├─ YES → implement_chain (sub-loop: oracles/implement-issue-chain)
         │         │         └─ [get_passed_issues → implement_next → go_no_go → implement_issue]
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

### Code Quality

*Choose these for standing code-health maintenance: dead code removal, docs drift, refactoring, coverage gaps, scratch-file pressure, and worktree hygiene.*

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

### `dead-code-cleanup` — Dead Code Removal

**When to use**: When you've accumulated unused imports, functions, or variables and want systematic removal with test-gated safety.

**Usage:**
```bash
ll-loop run dead-code-cleanup
```

**Key context variables:**
| Variable | Default | Description |
|----------|---------|-------------|
| `commit_message` | `refactor: remove dead code identified by scan` | Commit message template for each removal |

### `docs-sync` — Documentation Sync

**When to use**: After code changes that may have drifted from documentation — verifies doc accuracy and fixes broken links.

**Usage:**
```bash
ll-loop run docs-sync
```

**Key context variables:**
| Variable | Default | Description |
|----------|---------|-------------|
| `commit_message` | `docs: sync documentation with codebase state` | Commit message template |

### `incremental-refactor` — Safe Incremental Refactoring

**When to use**: When a refactoring goal is too large for a single pass — decomposes into atomic steps, each test-gated with automatic rollback on failure.

**Usage:**
```bash
ll-loop run incremental-refactor --context refactor_goal="extract auth middleware from request handler"
```

**Key context variables:**
| Variable | Default | Description |
|----------|---------|-------------|
| `refactor_goal` | — | Natural-language description of the refactoring goal |
| `test_cmd` | `python -m pytest scripts/tests/` | Test command to gate each step |
| `commit_message` | `refactor: apply incremental refactoring step` | Commit message template |

### `test-coverage-improvement` — Coverage Gap Closure

**When to use**: When you have a coverage target and want automated gap identification, prioritization by risk, and test generation until the target is met.

**Usage:**
```bash
ll-loop run test-coverage-improvement --context coverage_target=80

# Focus on specific directories
ll-loop run test-coverage-improvement \
  --context coverage_target=85 \
  --context focus_dirs=scripts/little_loops/fsm
```

**Key context variables:**
| Variable | Default | Description |
|----------|---------|-------------|
| `coverage_target` | `80` | Target coverage percentage (0–100) |
| `focus_dirs` | — | Directories to scope coverage analysis to |
| `test_cmd` | — | Test command to run (e.g. `python -m pytest --cov`) |
| `coverage_cmd` | — | Coverage measurement command |

### `worktree-health` — Orphaned Worktree Monitor

**When to use**: After interrupted `ll-parallel` runs or `ll-loop --worktree` sessions — detects orphaned worktrees and stale branches for cleanup.

**Usage:**
```bash
ll-loop run worktree-health
```

### Evaluation

*Choose this when auditing a loop itself — structure, execution behavior, and improvement opportunities — rather than producing a project artifact.*

| Loop | Description |
|------|-------------|
| `outer-loop-eval` | Analyze a target loop by loading its YAML definition, executing it as a sub-loop, then delegating to `/ll:debug-loop-run` and `/ll:audit-loop-run` to produce a structured improvement report |

### Reinforcement Learning (RL)

*Choose these for iterative quality convergence: evaluate, score, and refine an agent, policy, or artifact until a measurable target is reached.*

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

### Automatic Prompt Optimization (APO)

*Choose these to improve a prompt or skill file automatically against examples, history, or a benchmark — see [Choosing Between APO Loops](#choosing-between-apo-loops).*

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

### Harness Examples

*Choose these as starting points for generator-evaluator harnesses (HTML, SVG, p5.js, PixiJS, Vega, canvas-sketch) or as annotated templates for your own harness.*

| Loop | Description |
|------|-------------|
| `harness-single-shot` | Annotated single-shot harness example — all evaluation phases with commented-out optional gates |
| `harness-multi-item` | Annotated multi-item harness example — all five evaluation phases active over a discovered item list |
| `harness-plan-research-implement-report` | Annotated specialist-role pipeline example (Variant C) --- Plan -> Research -> Implement -> Report decomposition with full evaluation chain; optional HITL gate as commented-out block |
| `harness-optimize` | Score-gated hill-climbing on harness artifacts (skills, commands, CLAUDE.md) — proposes edits, benchmarks, commits accepted mutations; stops on first stall. Supports `.ll/program.md` for overnight runs. Also supports **state mode**: set `targets` to a loop YAML with a `targets.states` list to optimize individual state `action:` blocks independently. |
| `html-anything` | Generalized HTML artifact harness — classifies artifact type (email, social card, résumé, dashboard, etc.) from a description, writes a platform-specific brief and dynamic scoring rubric, then iteratively generates and refines `index.html` via Playwright CLI |
| `hitl-compare` | Human-in-the-loop comparison harness — reads whitespace-separated inputs (file paths or raw text), extracts candidate review items with 2+ options, prunes implementation-level micro-decisions, and generates a self-contained interactive HTML page with comparison controls, write-in custom options, and an "Export selections" affordance |
| `hitl-md` | Human-in-the-loop single-document review harness — reads a markdown file (or raw text), decomposes it into GP-TSM saliency-modulated segments with per-segment confidence scores, and generates a self-contained interactive HTML page with natural markdown rendering, inline saliency highlights, a lightweight low-confidence cue (dotted underline + badge), click/focus-triggered popover edit controls (delete / insert-before / insert-after / inline-edit / flag-for-AI), a "Copy AI prompt" control for flagged segments, and a "Copy updated markdown" reconstruction control. Final HTML is copied to `./hitl-md-review.html` in the run directory for quick access. |
| `html-website-generator` | Generator-evaluator harness for single-page HTML website creation — accepts a one-line description and iteratively generates, screenshots, and refines HTML/CSS/JS via Playwright CLI |
| `svg-image-generator` | Generator-evaluator harness for SVG icon and illustration creation — accepts a one-line description and iteratively generates, screenshots, and refines a self-contained SVG via Playwright CLI |
| `svg-textgrad` | TextGrad-style SVG harness — optimizes the visual brief via structured gradient updates (FAILURE_PATTERN → ROOT_CAUSE → GRADIENT) rather than feeding raw critique to the generator; accumulates gradient history for repeated-failure escalation |
| `p5js-sketch-generator` | Generator-evaluator harness for p5.js creative coding sketches — multi-frame screenshots at deterministic frameCounts evaluate motion, not just composition; GAN-style architecture with p5.js loaded from CDN |
| `pixi-data-viz` | Generator-evaluator harness for animated PixiJS data visualizations — embeds synthetic-but-plausible data inline; hard-gates `encoding_clarity` at threshold 7; evaluates whether motion aids comprehension |
| `pixi-generative-art` | Generator-evaluator harness for PixiJS generative art sketches — GPU-accelerated idioms (filters, blend modes, container hierarchies); rewards Pixi-distinctive patterns over p5.js conventions |
| `vega-viz` | Generator-evaluator harness for Vega / Vega-Lite data visualizations — compile-gates broken specs via deterministic exit-code before LLM scoring, supports optional real data (CSV/JSON path), defaults to Vega-Lite and escalates to full Vega only for custom/interactive composition; Playwright captures three interaction states (settled, hover/tooltip, brush/selection) as multimodal PNG input for the judge (ENH-2010) |
| `canvas-sketch-generator` | Generator-evaluator harness for canvas-sketch (Matt DesLauriers) still-image generative art — objective non-blank render gate (parsed pixel statistics) hard-gates blank sketches before the LLM judge runs; per-iteration snapshots with deterministic best-iteration selection; `on_max_iterations: finalize` ensures `best.html` is always published even when the pass threshold is never crossed |
| `rlhf-animated-svg` | RLHF-style generate-score-refine orchestrator for animated SVG artifacts — generates a zero-dependency self-contained HTML file with inline SVG animated via anime.js v3.2.2 (CDN, works under `file://`). Evaluation and refinement phases are delegated to the `rlhf-svg-evaluate` and `rlhf-svg-refine` sub-loops. Includes `explore → exploit → converge` phase gating, replan-on-streak-failure escalation, concept-reset escalation, and per-iteration artifact versioning. Accessibility: `role="img"`, `aria-labelledby`, `prefers-reduced-motion` detection. |
| `rlhf-svg-evaluate` | Sub-loop: smoke-test a rendered SVG artifact via Playwright and score it with an external vision API on a 4-dimension animation rubric (correctness, aesthetics, smoothness, completeness); captures 4 multi-frame screenshots at t=1s/3s/5s/7s for temporal evaluation; emits `VISION_PASS` or `VISION_FAIL` sentinel for parent routing |
| `rlhf-svg-refine` | Sub-loop: rank harness components by improvement impact (Ong et al. arXiv:2605.22505), critique the scored artifact and produce a fix plan, apply targeted refinements, run optimizer self-diagnosis against the 8-error taxonomy, and append a carry-forward lesson entry to `optimization_summary.md`; emits `REPLAN_NEEDED` when a structural replan is required |
| `rlhf-svg-generate` | Sub-loop: handles the `plan_animation → render_animation → verify_render` generation pipeline for `rlhf-animated-svg`; accepts `input`, `run_dir`, `global_iteration`, `design_tokens_context`, `quality_target`, `explore_cutoff`, and `exploit_cutoff` context parameters; produces `output.html` in `run_dir` on success or terminates at `plan_failed` on retry exhaustion (ENH-2051) |
| `loop-specialist-eval` | Behavioral eval harness for the `loop-specialist` agent — drives the agent against a seeded `broken-verify-loop.yaml` fixture (ambiguous-output failure mode) and verifies that the diagnosis artifact is written and the failure mode is correctly classified |
| `adversarial-redesign` | Generator-vs-critic figure refinement demo using AutoFigure — a generator produces an SVG from a text concept, a critic returns structured complaints, the loop regenerates addressing each complaint and exits on score-improvement stall or SVG-diff convergence. Every round is persisted for demo playback. **Requires**: `pip install -e ./AutoFigure && playwright install chromium` + `OPENROUTER_API_KEY`. Example: `ll-loop run adversarial-redesign --input concept="how a transformer attends"` |

For background on the GAN-style generator-evaluator architecture used by `html-website-generator`, `svg-image-generator`, `svg-textgrad`, `p5js-sketch-generator`, `pixi-data-viz`, `pixi-generative-art`, `vega-viz`, `canvas-sketch-generator`, and `rlhf-animated-svg`, see the [Harness Design for Long-Running Apps](../claude-code/harness-design-long-running-apps.md) reference.

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

**Technique**: Implements a `segment → generate → finalize` pipeline before the standard GAN-style `evaluate → score` loop. The `segment` state resolves the input token (file path or raw text) and applies the **GP-TSM (Grammar-Preserving Text Saliency Modulation)** algorithm inline as LLM instructions — no external Python/ML dependencies. It identifies grammar-preserving segment boundaries (sentence/clause level, treating headings, bullets, and code blocks as atomic), assigns saliency scores (0.0–1.0), a per-segment `confidence` score, and an accessible color palette per content type, and writes `segments.json`. The `generate` state then produces a single self-contained HTML review page that renders the document with its natural markdown flow (headings, paragraphs, lists, code blocks in their usual shape), with each segment wrapped in a `<span class="seg">` carrying low-alpha inline background highlights keyed to saliency. The five edit controls (delete / insert-before / insert-after / inline-edit / flag-for-AI) appear as a popover triggered by clicking or focusing a segment — controls overlay the document without causing reflow. The one trust-calibration signal retained is a **lightweight confidence cue**: segments with `confidence < 0.5` get a dotted underline plus a small "low confidence" badge rendered before the text (so the calibration signal is read before fluency biases judgment) — useful for fluent-but-wrong AI prose. A "Copy AI prompt" control aggregates all flagged segments, and a "Copy updated markdown" control reconstructs the full document from the live segment list. The `finalize` state copies the approved HTML to `./hitl-md-review.html` in the cwd. The `score` state evaluates a 7-criterion rubric (`document_readability`, `inline_highlighting`, `affordance_overlay`, `keyboard_reachability`, `inline_constraint`, `markdown_reconstruction`, `confidence_cue`) with per-criterion thresholds; the compound `ALL_PASS` token is the gate.

> **Simplified 2026-06**: the original ENH-1770 "sensemaking layer" (staged `IntersectionObserver` highlighting, an adaptive density slider, multi-channel saliency toggles, a schema-switching toolbar, a canvas minimap + visit heatmap, and full click-to-reveal trust-calibration friction) was removed. Stacking ~10 toolbar controls onto a read-and-edit surface added extraneous cognitive load — contradicting the sensemaking research it cited — and made the 13-gate generator-evaluator rubric near-impossible to converge within `max_iterations`. Only the lightweight confidence cue survived.

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
                     │              │              ├─ SMOKE_PASS → vision_gate
                     │              │              │                ├─ PASS      → done
                     │              │              │                └─ ITERATE   → generate (with critique)
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

- **`vision_gate` — optional external-vision aesthetic scoring** (added 2026-06): After `smoke_test` passes (functional sanity confirmed), the loop can route through `vision_gate`, which sends the screenshot to an independent vision model for aesthetic scoring against the same four criteria. This decouples visual-quality judgment from the host LLM's self-grade — the same anti-self-certification motive behind `smoke_test`, but for aesthetics rather than functionality. The state is a **no-op pass** unless `VISION_BASE_URL`, `VISION_MODEL`, and `VISION_API_KEY` environment variables are all set (graceful degradation). API errors, parse failures, and network issues also pass — the gate never blocks shipping a functionally-sound artifact. A per-run round cap (`.vision_rounds` in the run directory) bounds the refine/re-score ping-pong.

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
| `pass_threshold` | `7` | Weighted-average gate: `(2×visual_clarity + 2×originality + craft + scalability) / 6` must meet or exceed this value (default raised from 6 to 7 to match the tighter discriminating threshold) |
| `min_per_criterion` | `6` | Per-criterion floor: each of the four scores must be ≥ this value before the weighted average is checked; a single weak criterion (e.g. scalability 5/10) forces another gradient iteration |

Override per-run:

```bash
ll-loop run svg-textgrad "lightning bolt icon" \
  --context pass_threshold=7
```

**FSM flow:**

```
init → plan → generate → evaluate
                            ├─ CAPTURED → score → verify_score
                            │                         ├─ SHELL_PASS   → seal_artifacts → done
                            │                         ├─ SHELL_ITERATE → record_scores → compute_gradient → route_convergence
                            │                         │                                                        ├─ CONVERGED → seal_artifacts → done
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
                            │              ├─ ITERATE  → check_stall (diff_stall guard)
                            │              │              ├─ new changes → generate (with critique)
                            │              │              ├─ plateaued  → done (accept best-so-far)
                            │              │              └─ error       → generate
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
- **Stall detection** (ENH-2099): A `check_stall` state (via the `diff_stall_gate` fragment) follows `score`'s ITERATE branch. If no file changes are detected for `max_stall` consecutive iterations (default 3), the loop accepts the best-so-far and exits rather than burning the remaining iteration budget.
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
                            │              ├─ ITERATE  → check_stall (diff_stall guard)
                            │              │              ├─ new changes → generate (with critique)
                            │              │              ├─ plateaued  → done (accept best-so-far)
                            │              │              └─ error       → generate
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
- **Stall detection** (ENH-2099): A `check_stall` state (via `diff_stall_gate` fragment) follows `score`'s ITERATE branch. If no file changes are detected for `max_stall` consecutive iterations (default 3), the loop accepts the best-so-far and exits rather than burning the remaining iteration budget.
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
                            │              ├─ ITERATE  → check_stall (diff_stall guard)
                            │              │              ├─ new changes → generate (with critique)
                            │              │              ├─ plateaued  → done (accept best-so-far)
                            │              │              └─ error       → generate
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
- **Stall detection** (ENH-2099): A `check_stall` state (via `diff_stall_gate` fragment) follows `score`'s ITERATE branch. If no file changes are detected for `max_stall` consecutive iterations (default 3), the loop accepts the best-so-far and exits.
- If Playwright is unavailable, the `evaluate` state's `on_no` route retries with fresh HTML rather than scoring without visual evidence.
- The loop runs up to 20 iterations with a 2-hour timeout (`max_iterations: 20`, `timeout: 7200`).
- Prefer `p5js-sketch-generator` when the p5.js ecosystem (global mode, built-in `noise()`) is the right tool; reach for `pixi-generative-art` when GPU filters, blend modes, or `ParticleContainer` density are central to the aesthetic.

---

### `vega-viz` — Vega / Vega-Lite Visualization Harness

> **Prerequisites**: [Playwright CLI](https://playwright.dev/) must be installed (`npm install -g playwright && npx playwright install chromium`, or `pip install playwright && playwright install chromium`). Node.js must be available in `PATH` with `@playwright/test` in the global npm tree. `vega-cli` and `vega-lite` are installed on first run via `npx -y` — pre-install them to skip the download: `npm install -g vega-cli vega-lite`.

**Technique**: GAN-style generator-evaluator harness for Vega / Vega-Lite data visualizations — sibling of `pixi-data-viz` but with two capabilities the PixiJS loops lack:

1. **Deterministic compile gate.** A Vega-Lite or Vega spec either compiles and renders or it doesn't. The `validate` state runs `vl2vg` + `vg2png` (or `vg2png` directly) and uses an exit-code evaluator as a hard gate before the browser or the LLM judge ever runs. Broken specs route to a dedicated `repair` state that receives compiler stderr verbatim and fixes only the structural break — keeping break-fixing entirely separate from taste-refinement.

2. **Optional real-data binding.** The `resolve_data` state normalises a caller-supplied CSV or JSON file into `data.json` + `schema.txt` (field names, inferred types, row count). The `plan` and `generate` states consume `schema.txt` to bind the spec's encodings to real field names. When no file is supplied, the generator fabricates clearly-labeled synthetic data.

The `plan` state commits to a grammar (Vega-Lite by default, full Vega only when justified) and produces a `brief.md` that specifies mark + encoding with perceptual justification, honesty constraints, annotation text, interaction requirements, and palette. The `capture` state uses Playwright to load the compiled chart headless and capture three interaction states — settled, hover/tooltip, brush-drag selection — as PNGs, which the `score` state reads as multimodal input. `faithfulness` and `honesty` are hard-gated at `hard_gate` (default 7); `effectiveness` and `craft` at `pass_threshold` (default 6). Every scored iteration is versioned to `iter-N/`; `best.html` always points at the highest-scoring version so far.

**When to use**: When you need a data visualization with rigorous faithfulness + honesty evaluation, and especially when you have real data to bind to. Vs `pixi-data-viz`: `vega-viz` gives a deterministic compile gate, optional real-data binding, and three interaction captures; `pixi-data-viz` gives animated GPU-rendered charts with frame-sampled evaluation. Vs `svg-image-generator` / `p5js-sketch-generator`: those are for illustration and generative art, not data visualization.

**Usage:**

```bash
# Natural-language description → synthetic data
ll-loop run vega-viz "grouped bar chart comparing quarterly revenue across product lines"

# Bind to real data (CSV or JSON)
ll-loop run vega-viz "scatter plot of price vs customer rating" \
  --context data_path=/path/to/products.csv

# Raise quality thresholds
ll-loop run vega-viz "choropleth map of sales by region" \
  --context pass_threshold=7 --context hard_gate=8
```

**Context variables:**

| Variable | Default | Description |
|----------|---------|-------------|
| `description` | (from `loop_input`) | Natural language visualization description — passed as the positional argument |
| `data_path` | `""` | Optional path to a CSV or JSON file; empty → generator fabricates labeled synthetic data |
| `pass_threshold` | `6` | Minimum score for `effectiveness` and `craft` (1–10) |
| `hard_gate` | `7` | Hard floor for `faithfulness` and `honesty` — a chart that misrepresents data fails regardless of polish |
| `run_dir` | runner-injected | Per-run artifact directory (`.loops/runs/vega-viz-{timestamp}/`) for `index.html`, `brief.md`, `critique.md`, and interaction-frame PNGs; created automatically. Override with `--context run_dir=path/`. |

Override per-run:

```bash
ll-loop run vega-viz "line chart of weekly active users" \
  --context data_path=metrics.json \
  --context pass_threshold=7 \
  --context hard_gate=8
```

**FSM flow:**

```
init → resolve_data → plan → generate → validate
                                            ├─ COMPILE_OK  → capture
                                            │                  ├─ CAPTURED → score → record
                                            │                  │                        ├─ EVAL_PASS → done
                                            │                  │                        └─ ITERATE   → check_stall (diff_stall guard)
                                            │                  │                                          ├─ new changes → generate (with critique)
                                            │                  │                                          └─ plateaued  → done (accept best-so-far)
                                            │                  └─ ERROR    → failed
                                            └─ COMPILE_FAIL → repair → validate (← re-checks after fix)
```

**Evaluation criteria:**

| Criterion | Threshold | What it checks |
|-----------|-----------|----------------|
| `faithfulness` | `hard_gate` (**hard**) | Right mark + encoding for the brief's question; real field names used when `schema.txt` exists — inspects the spec, not just the picture |
| `honesty` | `hard_gate` (**hard**) | No truncated/non-zero-baseline exaggeration, dual axes, misleading aggregation, rainbow-jet on sequential data, overplotting that hides data |
| `effectiveness` | `pass_threshold` (soft) | Perceptual quality per Cleveland-McGill ranking, legibility at rendered size, tooltip in `frame_hover`, selection filter in `frame_brush` |
| `craft` | `pass_threshold` (soft) | Title and axis titles with units, legend where needed, typography hierarchy, spacing, color contrast |

**Notes:**
- `vega-cli` and `vega-lite` are installed on first run via `npx -y` (requires network). Pre-install to skip: `npm install -g vega-cli vega-lite`.
- `resolve_data` normalises the first list found in a JSON object; CSV rows are coerced to numeric values where possible; field types are inferred and written to `schema.txt` for the `plan` and `score` states to reference.
- The grammar decision (Vega-Lite vs full Vega) lives in `plan`, not `generate`. The brief commits to one; `generate` may escalate on stuck iterations but must justify in a code comment. Vega-Lite is the default — it has a higher first-pass success rate and the compile gate validates it equally.
- The spec is inlined into `index.html` (`vegaEmbed` handles both grammars from the same inline object). File-URI rendering requires this — no fetch, no CORS.
- `window.__vegaReady = true` must be set in the `vegaEmbed` `.then()` callback; the `capture` state polls it before taking screenshots.
- **Stall detection** (ENH-2099): A `check_stall` state (via `diff_stall_gate` fragment) follows `record`'s ITERATE branch. If no file changes are detected for `max_stall` consecutive iterations (default 3), the loop accepts the best-so-far and exits.
- `repair` fixes only the structural break reported in `compile_error.txt` — schema errors, invalid field references, wrong encoding types, malformed transforms. It does not redesign the chart.
- `on_handoff: spawn`, `max_iterations: 20`, `timeout: 7200`.

---

### `canvas-sketch-generator` — canvas-sketch Still-Image Harness

> **Prerequisites**: [Playwright CLI](https://playwright.dev/) must be installed (`npm install -g playwright && npx playwright install chromium`, or `pip install playwright && playwright install chromium`). Node.js must be available in `PATH` with `@playwright/test` in the global npm tree. canvas-sketch itself is loaded at runtime from the esm.sh ESM CDN — no local npm install required.

**Technique**: GAN-style generator-evaluator harness for canvas-sketch (Matt DesLauriers) still-image generative art, implementing the same GAN-inspired pattern as `p5js-sketch-generator` and `pixi-generative-art` with two additions specific to this library:

1. **Objective non-blank render gate.** The `evaluate` state reads the 2D pixel buffer and computes the fraction of pixels that differ from the modal background color (the `min_nonblank_ratio` gate, default 0.03). A sketch that renders nothing exits cleanly with no JavaScript error, so exit-code alone would wave it through. The ratio gate catches blank renders before the LLM judge ever runs.

2. **Infrastructure vs. sketch error split.** Sketch-level failures (JS error thrown by the sketch, no canvas element created, WebGL context used instead of 2D, never-ready, blank render) write an "Issues to Address" `critique.md` and emit `RENDER_BAD`, routing back to `generate` for self-repair. Only true infrastructure failures (browser won't launch, CDN unreachable) exit nonzero → `failed`. This means the generate→refine loop fixes its own bugs without human intervention.

The `plan` state writes `brief.md` committing to a specific generative rule, palette, and composition before the generator writes a single line of code. The `score` state (LLM) assigns four criteria and writes `critique.md`; the `snapshot` state (shell) parses scores deterministically and gates on the minimum — the LLM assigns, a non-LLM state decides (MR-1 compliant). The `finalize` state reads `scores.tsv` and publishes the iteration with the highest minimum-criterion score as `best.html` / `best.png` — because score progression is non-monotonic, a middle iteration is often the strongest. `on_max_iterations: finalize` routes budget-exhausted runs through `finalize` so `best.html` is always published.

**v1 scope:** still images only (no animation), 2D canvas only (WebGL/three/regl would need a different pixel-readback path).

**When to use**: When you want a still-image generative artwork using the canvas-sketch library. Vs `p5js-sketch-generator`: canvas-sketch API (`canvasSketch()`, ESM CDN import, `random.setSeed()`) vs p5.js global mode (`setup()`/`draw()`); still-image vs animated/multi-frame; non-blank pixel gate vs frameCount-based motion evaluation. Vs `pixi-generative-art`: 2D canvas vs GPU/WebGL filters and blend modes.

**Usage:**

```bash
ll-loop run canvas-sketch-generator "a recursive Truchet tiling with a cool monochrome palette"

# Raise quality bar and tighten render gate
ll-loop run canvas-sketch-generator "flow field with particle accumulation along attractor curves" \
  --context pass_threshold=7 --context min_nonblank_ratio=0.05
```

**Context variables:**

| Variable | Default | Description |
|----------|---------|-------------|
| `description` | (from `loop_input`) | Natural language description of the generative artwork — passed as the positional argument |
| `pass_threshold` | `6` | Minimum score per criterion (1–10); **all four** criteria must clear this value |
| `min_nonblank_ratio` | `0.03` | Objective gate: fraction of non-background pixels required to count as "drew something" (spike-confirmed: good sketch ≈ 0.41, blank sketch = 0.00) |
| `design_tokens_context` | runner-injected | Resolved semantic design-token values; empty string when tokens are disabled or the tokens path is missing |
| `run_dir` | runner-injected | Per-run artifact directory (`.loops/runs/canvas-sketch-generator-{timestamp}/`) for `index.html`, `screenshot.png`, `brief.md`, `critique.md`, `scores.tsv`, and `iter-N/` snapshots; created automatically. Override with `--context run_dir=path/`. |

**FSM flow:**

```
init → plan → generate → evaluate
                            ├─ RENDER_OK  → score → snapshot
                            │                           ├─ min score ≥ pass_threshold → finalize → done
                            │                           └─ min score < pass_threshold → check_stall (diff_stall guard)
                            │                                                              ├─ new changes → generate (with critique)
                            │                                                              └─ plateaued  → finalize → done
                            ├─ RENDER_BAD → generate (critique written — self-repair loop)
                            └─ ERROR (infra) → failed

on_max_iterations: finalize → done  (best.html always published)
```

**Evaluation criteria** (all four must meet `pass_threshold`):

| Criterion | Weight | What it checks |
|-----------|--------|----------------|
| `composition` | 2× | Balance, focal point, use of negative space, density gradient. Penalizes empty canvases, centered-blob compositions, no clear focal structure |
| `originality` | 2× | Evidence of a specific generative rule vs tutorial output. Penalizes vanilla Perlin flow fields, rainbow HSL cycling without purpose, anything that looks like the first Google result for "generative art" |
| `fidelity_to_brief` | 1× | Does the image depict what the brief's "Fidelity to brief" sentence specified? An attractive image that ignores the instruction fails |
| `craft` | 1× | Color harmony, edge/anti-alias quality, stroke consistency, compositing, intentional vs accidental artifacts |

**Notes:**
- canvas-sketch and canvas-sketch-util are loaded from the esm.sh ESM CDN inside `<script type="module">` — the only external resource permitted. All sketch code is inline so the file renders correctly under a `file://` URL without a web server.
- Deterministic seeding is required: `random.setSeed('<constant>')` called once before drawing; all randomness via `canvas-sketch-util/random`. Unseeded `Math.random()` or `Date.now()` breaks per-iteration reproducibility.
- The sketch MUST signal readiness for the `evaluate` harness: `canvasSketch(sketch, settings).then(() => { window.__sketchReady = true; }).catch(e => { window.__sketchError = String(e && e.stack || e); })`. The `evaluate` state polls `window.__sketchReady === true` before screenshotting.
- Still images only (v1): do NOT set `settings.animate: true`. Draw the full composition in the single render call.
- `max_iterations: 40` caps **state executions**, not refine cycles. One scored cycle ≈ 4 states (`generate`, `evaluate`, `score`, `snapshot`), plus ~2 extra whenever a blank/broken render triggers the self-repair path, plus `init` + `plan` + `finalize` + `done` overhead. 40 steps ≈ 6–8 scored cycles, matching the 5–15 iterations in Anthropic's harness-design article.
- **Stall detection** (ENH-2099): A `check_stall` state (via `diff_stall_gate` fragment) follows `snapshot`'s below-threshold branch. If no file changes are detected for `max_stall` consecutive iterations (default 3), the loop routes to `finalize` (publishing the best-so-far) instead of burning the remaining iteration budget.
- `on_max_iterations: finalize` ensures `best.html` is always published, even when the pass threshold is never crossed. A run that exhausts its budget without ever scoring above threshold still produces the best artifact it found.
- `finalize` reads `scores.tsv` (one `iteration<tab>min_score` row per `snapshot` call) and copies the highest-scoring iteration's `index.html` and `screenshot.png` to `best.html` and `best.png` at the run-dir root. Ties go to the latest iteration.
- `on_handoff: spawn`, `max_iterations: 40`, `timeout: 7200`.

### `rlhf-animated-svg` — RLHF Animated SVG Generator (ENH-2039)

**Technique**: RLHF-style generate-score-refine harness for animated SVG artifacts. A **planner** decomposes the natural-language description into a motion choreography brief (elements, timing, easing, palette); a **generator** renders a zero-dependency self-contained HTML file with inline SVG and an `anime.js v3.2.2` CDN `<script>` tag (UMD, `file://`-safe with static-SVG `onerror` fallback); a headless browser **smoke gate** verifies the animation runs without JS errors; and an **image-analysis scorer** evaluates the rendered output on four criteria. Refines until the score target is met. Three phases gate the optimization strategy: explore (iterations 0–5, unconstrained), exploit (6–15, brief-anchored), converge (16+, micro-adjustments only).

**File**: `scripts/little_loops/loops/rlhf-animated-svg.yaml`

**When to use**: When you want an animated SVG/HTML artifact and need motion-quality evaluation, not just static composition. The headless smoke gate (checks for JS errors, verifies `window.__animationReady === true`) and animation-specific rubric are the key differentiators from `svg-image-generator`: a static SVG and a broken animation can look identical in a single screenshot; the smoke gate separates them before the LLM scorer runs.

**Invocation**:
```bash
# Default prompt (a bouncing ball with trail)
ll-loop run rlhf-animated-svg

# Custom animation description
ll-loop run rlhf-animated-svg \
  --context input="A particle burst that explodes from center on load, with each particle following a parabolic arc and fading out"

# Raise quality bar
ll-loop run rlhf-animated-svg \
  --context quality_target=9 \
  --context input="A breathing circle that slowly expands and contracts with a soft glow"
```

**Context variables**:

| Variable | Default | Description |
|----------|---------|-------------|
| `input` | "A bouncing red ball with a fading trail…" | Natural-language animation description |
| `quality_target` | `8` | Score threshold (0–10) to exit successfully |
| `explore_cutoff` | `5` | Last iteration of explore phase (unconstrained generation) |
| `exploit_cutoff` | `15` | Last iteration of exploit phase (16+ = converge) |
| `max_replans` | `3` | Full replan cycles before forced termination |
| `smoke_fail_streak_max` | `2` | Consecutive smoke failures before skipping to score |
| `smoke_bypass_threshold` | `5` | Total smoke attempts after which smoke gate is bypassed |
| `score_fail_streak_max` | `3` | Consecutive VISION_FAIL evaluations before triggering replan |
| `run_dir` | runner-injected | Per-run artifact directory (`.loops/runs/rlhf-animated-svg-{timestamp}/`) |

**FSM flow** (orchestration-only; evaluation and refinement are delegated to sub-loops):
```
init → validate_input → plan_animation → render_animation → verify_render
         └─ (empty input) → input_missing [terminal]

verify_render
  ├─ RENDER_EXISTS → run_evaluate [rlhf-svg-evaluate sub-loop]
  └─ RENDER_MISSING → render_animation (retry)

run_evaluate
  ├─ VISION_PASS  → write_final_summary → restore_best → done [terminal]
  └─ VISION_FAIL  → check_oscillation
       ├─ OSCILLATION_DETECTED (smoke streak ≥ max) → plan_animation (replan)
       └─ normal → check_score_streak
            ├─ CONCEPT_RESET (replan cycles exhausted) → concept_reset → render_animation
            ├─ REPLAN (score-fail streak ≥ max) → plan_animation
            └─ normal → run_refine [rlhf-svg-refine sub-loop]
                 ├─ on_success → run_evaluate
                 └─ REPLAN_NEEDED → check_replan_budget
                      ├─ budget exhausted → write_final_summary
                      └─ budget available → plan_animation
```

**Scoring rubric** (all four evaluated; min score gates exit):

| Criterion | What it checks |
|-----------|----------------|
| `correctness` | Does the animation match the description? Elements, colors, motion type |
| `aesthetics` | Visual quality — palette harmony, smooth arcs, pleasing proportions |
| `smoothness` | Frame-rate consistency, easing quality, no jank or stuck states |
| `completeness` | All described elements present; no obvious missing features |

**Output artifacts** (in `run_dir`):
- `index.html` — Current iteration artifact (self-contained, `file://`-safe)
- `best.html` — Highest-scoring iteration (written by `finalize` on `done` or `max_iterations`)
- `optimization_summary.md` — Running log of replan rationale and gradient history

**Notes:**
- anime.js v3.2.2 is loaded from CDN (`unpkg.com`). An `onerror` fallback renders the target element as a static SVG if the CDN is unavailable. All animation JS is inline.
- Accessibility: `role="img"`, `aria-labelledby` pointing to a `<title>` element, and `prefers-reduced-motion` detection that disables animation when the OS preference is set.
- `artifact_versioning: true` — each iteration's output is preserved; the runner will not overwrite previous iterations' artifacts.
- `on_handoff: spawn`, `max_iterations: 30`, `timeout: 7200`.

### `rlhf-svg-evaluate` — RLHF Animated SVG Evaluation Sub-Loop

**Technique**: Sub-loop that handles the evaluation pipeline for `rlhf-animated-svg`: archives the current artifact, optionally bypasses the smoke gate after a configurable number of attempts, captures four screenshots at t=1000ms/3000ms/5000ms/7000ms via Playwright, and scores the multi-frame sequence via an external vision API against a 4-dimension animation rubric. Maintains a `.best_score` regression guard and restores `.best_output.html` when the current score drops below the adaptive tolerance threshold. Emits a `VISION_PASS` or `VISION_FAIL` sentinel in the final state output for parent routing.

**When to use**: Standalone when you want to evaluate an existing animated SVG artifact from a prior `rlhf-animated-svg` run without running the full generate-refine cycle. Also invoked automatically by `rlhf-animated-svg` via `loop: rlhf-svg-evaluate` after each `verify_render` pass.

**Usage:**

```bash
# Standalone evaluation of an existing run artifact
ll-loop run rlhf-svg-evaluate \
  --context run_dir="$(pwd)/.loops/runs/rlhf-animated-svg-20260601T120000"

# With a stricter quality target
ll-loop run rlhf-svg-evaluate \
  --context run_dir="$(pwd)/.loops/runs/rlhf-animated-svg-20260601T120000" \
  --context quality_target=9
```

**Parameters** (populated by parent via `with:`):

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `run_dir` | yes | — | Absolute path to the run directory containing `output.html` |
| `quality_target` | no | `8` | Score threshold (0–10); all four dimensions must meet or exceed this |
| `smoke_bypass_threshold` | no | `5` | Total smoke invocations before the smoke gate is auto-bypassed |
| `exploit_cutoff` | no | `15` | Exploit-phase boundary; controls regression-tolerance scaling (`> exploit_cutoff` → stricter 15%) |

**Context variables:**

| Variable | Default | Description |
|----------|---------|-------------|
| `run_dir` | `""` | Required: absolute path to the run directory |
| `quality_target` | `8` | Pass threshold for all four rubric dimensions |
| `smoke_bypass_threshold` | `5` | Total smoke attempts before automatic bypass |
| `exploit_cutoff` | `15` | Exploit/converge boundary for regression-tolerance scaling |

**Output artifacts** (within `${context.run_dir}`):

| File | Description |
|------|-------------|
| `snapshots/output_iter_N.html` | Per-iteration snapshot of `output.html` |
| `output_frame_1000ms.png` | Screenshot at t=1000ms (early animation state) |
| `output.png` | Screenshot at t=3000ms (storyboard frame; backward-compat alias) |
| `output_frame_5000ms.png` | Screenshot at t=5000ms (mid-animation state) |
| `output_frame_7000ms.png` | Screenshot at t=7000ms (late animation / loop-restart state) |
| `.vision_scores.json` | Latest per-dimension scores, issues list, and regression state |
| `.best_score` | Best minimum score seen across all iterations |
| `.best_output.html` | Copy of `output.html` from the highest-scoring iteration |
| `fix_correlation.jsonl` | Per-iteration fix-category / score-delta correlation entries |
| `fix_strategy_effectiveness.json` | Running per-strategy effectiveness statistics (hit rate, regression rate) |

**FSM flow:**

```
smoke_test → score → track_correlation → done
    └─ (JS error / blank render) → smoke_fail_exit (emits VISION_FAIL) → done
```

**Notes:**
- The `score` state requires `VISION_BASE_URL`, `VISION_MODEL`, and `VISION_API_KEY` environment variables (or a `.env` file in the project root). If any are unset, scoring passes gracefully with `VISION_PASS: skipped`.
- Multi-frame capture (four screenshots) is performed during `smoke_test`. If Playwright is not installed, the smoke gate is skipped with `SMOKE_PASS: skipped (Playwright not installed)` and no frames are captured; the `score` state then falls back to single-frame rubric mode if exactly one frame is available, or passes gracefully if none are present.
- Regression guard: if the current minimum score drops by `≥ max(1.0, best_min * 0.25)` (explore/exploit phase) or `≥ max(0.5, best_min * 0.15)` (converge phase), `SCORE_REGRESSION` is emitted and `.best_output.html` is mechanically restored to `output.html`.
- `category: lib` — this loop is a composable sub-loop fragment, not a standalone harness.

### `rlhf-svg-refine` — RLHF Animated SVG Refinement Sub-Loop

**Technique**: Sub-loop that handles the refinement pipeline for `rlhf-animated-svg`: ranks harness components (prompt, tool, memory, workflow) by expected improvement impact using the priority-ranking framework from Ong et al. (arXiv:2605.22505), produces a phase-aware fix plan via `review_critique`, applies the plan to `output.html` via `apply_refinements`, audits the optimizer's own behavior against an 8-error taxonomy via `self_diagnose`, and appends a structured carry-forward lesson entry to `optimization_summary.md` via `write_summary`. Emits `REPLAN_NEEDED` on `review_critique.on_yes` when a structural replan is required (repeated failure pattern, missing artifact, or score regression detected).

**When to use**: Standalone when you want to apply a targeted fix cycle to an existing animated SVG artifact without running the full orchestration loop. Also invoked automatically by `rlhf-animated-svg` via `loop: rlhf-svg-refine` after a `VISION_FAIL` from `rlhf-svg-evaluate`.

**Usage:**

```bash
# Standalone refinement of an existing run artifact
ll-loop run rlhf-svg-refine \
  --context run_dir="$(pwd)/.loops/runs/rlhf-animated-svg-20260601T120000" \
  --context animation_plan="A bouncing red ball with a fading trail"

# With explicit phase boundary overrides
ll-loop run rlhf-svg-refine \
  --context run_dir="$(pwd)/.loops/runs/rlhf-animated-svg-20260601T120000" \
  --context animation_plan="..." \
  --context global_iteration=8 \
  --context explore_cutoff=5 \
  --context exploit_cutoff=15
```

**Parameters** (populated by parent via `with:`):

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `run_dir` | yes | — | Absolute path to the run directory containing `output.html` and vision scores |
| `animation_plan` | yes | — | Original animation plan from parent's `captured.animation_plan` |
| `fix_plan` | no | `""` | Most recent fix plan from prior refinement cycle (for repeated-pattern detection) |
| `component_ranking` | no | `""` | Prior component ranking output (for focus bias detection) |
| `global_iteration` | yes | — | Parent's `state.iteration` value for phase detection |
| `explore_cutoff` | no | `10` | Last iteration of the explore phase |
| `exploit_cutoff` | no | `20` | Last iteration of the exploit phase (16+ = converge) |
| `quality_target` | no | `8` | Score threshold; used to categorize fix priority (HIGH/MEDIUM/LOW) |
| `design_tokens_context` | no | `""` | Resolved design token values for color palette guidance |

**Context variables:**

| Variable | Default | Description |
|----------|---------|-------------|
| `run_dir` | `""` | Required: absolute path to the run directory |
| `animation_plan` | `""` | Required: original plan from the parent orchestrator |
| `fix_plan` | `""` | Optional: prior fix plan for repeated-pattern detection |
| `component_ranking` | `""` | Optional: prior ranking for focus-bias detection |
| `global_iteration` | `1` | Required: parent's iteration counter for phase detection |
| `explore_cutoff` | `10` | Explore-phase boundary (iterations 1–N = unconstrained) |
| `exploit_cutoff` | `20` | Exploit/converge boundary (16+ = conservative micro-adjustments only) |
| `quality_target` | `8` | Pass threshold; fixes within 1–2 pts = HIGH, 2+ pts below = MEDIUM |
| `design_tokens_context` | `""` | Token palette for color constraint enforcement |

**Output artifacts** (within `${context.run_dir}`):

| File | Description |
|------|-------------|
| `output.html` | Refined artifact (in-place update by `apply_refinements`) |
| `optimization_summary.md` | Running log of carry-forward lessons across refinement cycles |
| `self_diagnosis.jsonl` | Per-iteration optimizer behavior classification (8-error taxonomy, JSONL) |

**FSM flow:**

```
rank_components → review_critique
                     ├─ REPLAN_NEEDED → done (signals parent to replan)
                     └─ normal → apply_refinements → self_diagnose
                                                          ├─ CRITICAL_ERROR → done
                                                          └─ normal → write_summary → done
```

**Dimensional diagnosis routing** (inside `review_critique`):

| Signal | Trigger | Effect |
|--------|---------|--------|
| `REPLAN_NEEDED` (repeated pattern) | Current failure matches a carry-forward lesson from ≤3 iterations ago | Parent routes to `plan_animation` for a fresh plan |
| `REPLAN_NEEDED` (missing artifact) | No `output.html` produced | Parent routes to `plan_animation` |
| `REPLAN_NEEDED` (score regression) | `SCORE_REGRESSION` in prior output | Parent routes to `plan_animation`; best artifact already restored by `rlhf-svg-evaluate` |
| normal | No replan trigger | `apply_refinements` applies the fix plan in-place |

**Self-diagnosis severity levels** (inside `self_diagnose`):

| Severity | Condition | Effect |
|----------|-----------|--------|
| `CRITICAL_ERROR` | Hallucination (#4) or Safety Violation (#8) detected | Sub-loop terminates with `REPLAN_NEEDED`-equivalent signal |
| `MULTI_FLAG` | 3+ non-critical error types detected | Diagnosis surfaced to next `review_critique` for evidence-based re-critique |
| `DIAGNOSIS_NORMAL` | 0–2 non-critical types, no critical | Logged to `self_diagnosis.jsonl`; loop continues normally |

**Notes:**
- Phase detection uses `${context.global_iteration}` (the parent orchestrator's iteration counter), **not** `${state.iteration}`. This ensures explore/exploit/converge phase boundaries remain consistent across sub-loop invocations regardless of how many states the sub-loop itself steps through.
- Component ranking uses the four-component framework from Ong et al. (arXiv:2605.22505, Finding 4): prompt ≻ tool ≻ memory ≻ workflow. If the `rank_components` state detects `BIAS_WARNING` (same component ranked #1 across multiple iterations without score improvement), the `review_critique` state de-prioritizes that component.
- `category: lib` — this loop is a composable sub-loop fragment, not a standalone harness.

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

**Partial-route dead-end guard (MR-4)**: An LLM-judged state (action_type: `prompt` or `slash_command`, or an explicit `llm_structured`/`check_semantic` evaluator) can receive `yes`, `no`, or `partial` verdicts from the default judge. If the state maps `on_yes` but provides no route for `no` or `partial` — and has no `next:` or `route:` table with a `default` — then a `no`/`partial` verdict causes `_route` to return `None`, silently terminating the loop. A parent loop reads this as a failure, discarding any progress made. `ll-loop validate` emits a WARNING (MR-4) for this shape so the dead-end is caught at authoring time. Fix by adding `on_no`/`on_partial`, using `next:` for an unconditional handoff, or providing a `route:` table. Set `partial_route_ok: true` at the loop top-level to suppress when intentional.

**Generator-fix discipline (MR-6)**: A meta-loop must not use a `shell` state to hand-patch the same file path that an LLM-generator state (`prompt`/`slash_command` with `yaml_state_editor` or `replace_action` markers) writes. Hand-patching produces output that diverges from the generator on the next run — the next iteration regenerates the file, overwriting the patch. The stable fix is to update the generator action so every run produces correct output automatically. `ll-loop validate` emits a WARNING (MR-6) when both a shell writer and an LLM generator target the same path. Set `generator_fix_ok: true` at the loop top-level to suppress for intentional post-processing cases.

## Cluster vs. Composer vs. Router

**Quick-pick by input shape:**

| You have… | Use |
|---|---|
| A natural-language goal | `loop-router` (classifies + dispatches to best-fit loop) |
| One decomposable goal (multi-step) | `loop-composer` / `loop-composer-adaptive` |
| A list of goals / EPIC / sprint | `goal-cluster` |
| A single issue to implement | `rn-implement` |
| A spec file, zero-to-project | `rn-build` |

Five orchestration loops address different goal shapes:

| Loop | When to use |
|---|---|
| `loop-router` | Single goal, best-fit single loop. Use as the default entry point. |
| `loop-composer` / `loop-composer-adaptive` | Single decomposable goal that requires multiple loops in sequence (DAG execution). |
| `goal-cluster` | Multiple related goals that share context. Groups goals into batches, executes sequentially with cross-batch hint propagation. |
| `rn-implement` | A single issue (or comma-separated list) to implement recursively — depth-bounded decompose-and-implement until the queue is empty. |
| `rn-build` | Spec file → zero-to-project. Orchestrates the full pipeline: tech research → design → scope EPIC → `goal-cluster` (batched `rn-implement`) → eval gate. Use when you have a spec document and want fully automated spec-to-implementation with no manual handoffs. |

**Decision rule**: Start with `loop-router` for a single goal. If the goal is clearly multi-step and benefits from explicit DAG decomposition, use `loop-composer` (or `loop-composer-adaptive` for failure recovery). If you have multiple goals at once (e.g., all issues in a sprint or all children of an EPIC), use `goal-cluster`. For a single issue that may need recursive decomposition, use `rn-implement`. For spec-driven greenfield projects (you have a spec file and want a full automated build), use `rn-build`.

**Why not loop-router for multiple goals?** loop-router picks one loop for one goal. It cannot propagate context across goals or group related goals into efficient batches.

**Dispatch guard**: loop-router and loop-composer(s) exclude goal-cluster from their catalogs. goal-cluster excludes loop-composer and loop-router from its dispatch suggestions. This prevents recursive orchestration cycles.

---

### `loop-composer` — Multi-Loop DAG Orchestrator

**Category**: orchestration  
**File**: `scripts/little_loops/loops/loop-composer.yaml`

Accepts a natural-language goal too large for a single loop, decomposes it into an ordered DAG of up to 8 loop invocations, presents the plan for HITL approval (unless `auto=true`), then walks the DAG sequentially, returning a JSON summary of all step results.

Use when a goal naturally spans 3–6 existing loops in a fixed sequence and you want structured plan approval before execution begins. For mid-plan failure recovery, use `loop-composer-adaptive` instead.

#### Invocation

```bash
ll-loop run loop-composer --input "your multi-step goal"

# Skip HITL approval
ll-loop run loop-composer --input "your goal" --context auto=true

# Exclude specific loops from the catalog
ll-loop run loop-composer --input "your goal" --context exclude="rn-plan,rn-refine"
```

#### Context Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `goal` | `""` | **Required.** Natural-language goal to decompose. |
| `auto` | `"false"` | When `"true"`, skip HITL plan-approval step. |
| `exclude` | `""` | Comma-separated loop names to exclude from the candidate catalog. |
| `max_plan_nodes` | `"8"` | Maximum steps allowed in a single plan. |

Config knobs: `orchestration.composer.max_plan_nodes`.

#### State Graph (summary)

```
discover_loops → decompose_goal → (auto=true → execute_plan | approve_plan) → execute_plan → summarize → done
                                                                              ↑ (reject) ↓ (revise)
                                                                            revise_plan ←─────────┘
```

---

### `loop-composer-adaptive` — Fault-Tolerant Composer

**Category**: orchestration  
**File**: `scripts/little_loops/loops/loop-composer-adaptive.yaml`

Adaptive variant of `loop-composer`. Decomposes a goal into a DAG the same way, but when a sub-loop fails the adaptive variant invokes a **reassess gate** that decides one of:

- `CONTINUE` — treat the failure as non-blocking and proceed
- `REPLAN_TAIL` — discard the unexecuted tail and re-decompose from the failure point (bounded by `max_replans`)
- `ABORT` — surface the failure and halt

Completed-step checkpoints are preserved on `REPLAN_TAIL` so successful steps are not re-run.

Use when mid-plan failures are likely and you prefer structured recovery over a full restart. For goals where any sub-loop failure should terminate immediately, use `loop-composer`.

#### Invocation

```bash
ll-loop run loop-composer-adaptive --input "your multi-step goal"

# Allow up to 3 replan attempts (default 2)
ll-loop run loop-composer-adaptive --input "your goal" --context max_replans=3
```

#### Context Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `goal` | `""` | **Required.** Natural-language goal to decompose. |
| `auto` | `"false"` | Skip HITL plan-approval when `"true"`. |
| `exclude` | `""` | Comma-separated loop names to exclude from catalog. |
| `max_plan_nodes` | `"8"` | Maximum steps in a single plan. |
| `max_replans` | `"2"` | Maximum tail-replan attempts before `ABORT`. |

Config knobs: `orchestration.composer.max_plan_nodes`, `orchestration.composer.adaptive.*`.

---

### `goal-cluster` — Multi-Goal Batch Orchestrator

**Category**: orchestration  
**File**: `scripts/little_loops/loops/goal-cluster.yaml`

Multi-goal orchestrator for sprint- or EPIC-shaped input. Accepts a list of goals, normalizes them, groups related goals into batches by predicted loop, executes each batch sequentially with per-batch reassess gates on failure, propagates cross-cutting context ("hints") between batches, and synthesizes a cluster-wide summary.

Use when you have **multiple related goals** that share context and benefit from sequential batch execution — rather than `loop-composer` (single decomposable goal) or `loop-router` (single goal routed to one loop).

#### Invocation

```bash
# Multi-line goals (one per line)
ll-loop run goal-cluster --input "Fix auth bug
Add retry logic
Update API docs"

# EPIC ID — goals are the EPIC's open child issues
ll-loop run goal-cluster --input "EPIC-1811"

# Sprint name
ll-loop run goal-cluster --input "sprint-2026-06"

# JSON list
ll-loop run goal-cluster --input '[{"goal_id":"g01","goal_text":"Fix auth bug"},{"goal_id":"g02","goal_text":"Add retry logic"}]'
```

#### Context Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `goals` | `""` | **Required.** Raw multi-line, sprint name, EPIC-NNN, or JSON list of goals. |
| `auto` | `"false"` | Skip HITL plan review when `"true"`. |
| `exclude` | `""` | Comma-separated loop names to exclude from dispatch suggestions. |
| `max_batch_size` | `"5"` | Maximum goals per batch. |
| `enable_dedup` | `"true"` | Merge or skip overlapping goals before batching. |
| `propagate_context` | `"true"` | Extract cross-batch hints from each batch summary for injection into the next. |

Config knobs: `orchestration.cluster.*` (see [CONFIGURATION.md §orchestration.cluster](../reference/CONFIGURATION.md#orchestrationcluster)).

#### State Graph (summary)

```
load_goals → normalize_goals → plan_batches → (auto=false → approve_plan) → execute_batch
                                                                             ↓ (success)
                                                                          extract_hints → (more batches?) → execute_batch
                                                                             ↓ (all done)
                                                                          synthesize → done
                                                                (failure) ↓
                                                                reassess → (CONTINUE/REPLAN → execute_batch | ABORT → failed)
```

---

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

---

## Built-in Fragment Libraries

Seven libraries ship with little-loops, all in `scripts/little_loops/loops/lib/`:

### `lib/common.yaml` — type-pattern fragments

Generic structure fragments (action_type + evaluate combinator) used by all built-in loops:

| Fragment | Description | Provides | Caller must supply |
|----------|-------------|----------|--------------------|
| `shell_exit` | Shell command evaluated by exit code. | `action_type: shell` + `evaluate.type: exit_code` | `action`, routing (`on_yes`, `on_no`) |
| `retry_counter` | Increments a counter file and checks if still below the max retry limit. Declares `parameters: {counter_key, max_retries}` — bind at call site via `with:` for collision-free multi-use. | Shell counter script + `output_numeric` evaluator | `with: {counter_key: ..., max_retries: ...}` (or legacy `context.counter_key` / `context.max_retries`), routing |
| `llm_gate` | LLM prompt state with structured yes/no output. When the prompt performs multiple MCP tool calls followed by synthesis (~10 calls), set `timeout: 1500` or higher at the state level; the 3600s executor fallback is bypassed by any loop-level `default_timeout:`. | `action_type: prompt` + `evaluate.type: llm_structured` | `action`, `evaluate.prompt`, routing (`on_yes`, `on_no`), optionally `timeout` |
| `numeric_gate` | Shell command evaluated by numeric output comparison. | `action_type: shell` + `evaluate.type: output_numeric` | `action`, `evaluate.operator`, `evaluate.target`, routing (`on_yes`, `on_no`) |
| `with_rate_limit_handling` | Applies per-state two-tier rate-limit retry handling: 3 short retries (30 s base backoff) then the default long-wait ladder (5 min → 15 min → 30 min → 1 h) up to a 6 h wall-clock budget. | `max_rate_limit_retries: 3`, `rate_limit_backoff_base_seconds: 30`, plus inherited `rate_limit_long_wait_ladder` and `rate_limit_max_wait_seconds` defaults | `on_rate_limit_exhausted` (target state name) |
| `parse_tagged_json` | Shell state that extracts a tagged JSON line from LLM output. Injects `action_type: shell` only; caller supplies all extraction and normalization logic in `action:`. Nested `${captured.${context.var}.output}` interpolation is NOT supported (single-pass engine) — use the captured variable's literal name directly in `action:`. | `action_type: shell` | `action` (extraction + normalization script referencing captured output by literal name), `capture`, `evaluate` (`output_json` recommended), routing (`on_yes`, `on_no`) |
| `convergence_gate` | Shell state evaluated by the convergence evaluator toward a numeric target. Callers supply only overrides; `type: convergence` and `direction: maximize` are fixed by the fragment. | `action_type: shell` + `evaluate.type: convergence` + `evaluate.direction: maximize` | `action`, `evaluate.target`, `evaluate.tolerance`, routing (`route.target`, `route.progress`, `route.stall`); optionally `evaluate.previous`, `route.error` |
| `queue_pop` | Shell state that atomically pops the head of a queue file (head-1/tail-n+2/mv idiom). Evaluates by exit code: exit 0 = item popped (`on_yes`), exit 1 = queue empty (`on_no`). | `action_type: shell` + `evaluate.type: exit_code` | `action` (pop shell script), routing (`on_yes`, `on_no`); optionally `on_error`, `capture` |
| `queue_track` | Shell state that appends an ID to a skip or visited tracking file (echo >> idiom). No evaluator — always transitions unconditionally. | `action_type: shell` | `action` (echo append script), `next:` |
| `diff_stall_gate` | Shell state evaluated by the `diff_stall` evaluator; yields `on_yes` when a git diff is detected (progress), `on_no` after `max_stall` (default 2) consecutive iterations with no diff change. Used to skip idempotent iterations instead of exhausting `max_iterations`. | `action_type` inherited from caller + `evaluate.type: diff_stall` + `evaluate.max_stall: 2` | `action`, `action_type`, routing (`on_yes`, `on_no`); optionally `on_error`, `evaluate.scope` |
| `plan_rubric_score` | 9-dimension plan scorer for rn-* loops. Evaluates plan.md on breadth/depth/complexity/clarity/consistency/logic_strategy/feasibility/testability/risk_mitigation, rewrites plan-rubric.md, and emits `ALL_VERY_HIGH` on convergence. Distinct from `score_plan_quality` (4-dimension batch scorer in `lib/score-plan-quality.yaml`). | `action_type: prompt` + 9-dimension scoring action + `evaluate.type: output_contains` with `pattern: "ALL_VERY_HIGH"` | routing (`on_yes`, `on_no`, `on_error`) |
| `loop_failure_diagnose` | Terminal failure handler for rn-* planning loops. Prompts for root-cause diagnosis, reads rubric/plan artifacts, writes a one-paragraph diagnostic summary. Declares `parameters: {loop_name, extra_bullets}` — bind at call site via `with:`. Fixed `next: failed`. | `action_type: prompt` + diagnosis action + fixed `next: failed` | `with: {loop_name: <name>}`; optionally `with: {extra_bullets: <bullets>}` |
| `subloop_rate_limit_diagnostic` | Sub-loop terminal handler for rate-limit exhaustion (ENH-1977 GAP A). Writes an outcome token to `${context.run_dir}/subloop_outcome_<ID>.txt` and routes to `failed` so the parent reads exhaustion correctly. Declares `parameters: {operation, outcome_token}` — bind at call site via `with:`. Fixed `next: failed`. | `action_type: shell` + outcome-token write + log line + fixed `next: failed` | `with: {operation: <word>}`; optionally `with: {outcome_token: <token>}` |

### `lib/benchmark.yaml` — Harbor-format benchmark runner

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

### `lib/score-plan-quality.yaml` — plan-quality scoring fragment

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

### `lib/cli.yaml` — ll- CLI tool fragments

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

### `lib/prompt-fragments.yaml` — reusable LLM prompt fragments

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

### `lib/harness.yaml` — Playwright screenshot and rubric scoring fragments

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
| `ll_rubric_score` | Scores a generated artifact against a rubric with a configurable pass threshold. Emits `ALL_PASS` when all criteria pass; otherwise `NEEDS_WORK` with improvement notes. Used in the `generator-evaluator` oracle `score` state. Declares `parameters: {run_dir, rubric, pass_threshold}` — bind at call site via `with:`. | `action_type: prompt` + `evaluate.type: output_contains` (`pattern: "ALL_PASS"`) | `with: {run_dir: ..., rubric: ..., pass_threshold: ...}` (or legacy `context.run_dir` / `context.rubric` / `context.pass_threshold`), routing (`on_yes`, `on_no`, `on_error`) |

### `lib/apo-base.yaml` — APO base loop skeleton

Base skeleton for Automated Prompt Optimization (APO) loops. Unlike the other six libraries (which are fragment collections), this is a **loop template** inherited via `from:` rather than `import:`. Provides the common `category`, `max_iterations`, `timeout`, `on_handoff`, `context.prompt_file`, and a terminal `done` state. Child loops (e.g. `apo-beam`, `apo-textgrad`, `apo-opro`, `apo-contrastive`, `apo-feedback-refinement`) inherit from it and supply their own `initial:` state and operative state graph.

```yaml
from: lib/apo-base

initial: my_custom_init
```

Not runnable directly — kept under `lib/` so it is excluded from non-recursive loop discovery. See [Loop Template Inheritance via `from:`](LOOPS_GUIDE.md#loop-template-inheritance-via-from) for full inheritance semantics and examples.

Built-in loops import the libraries as `import: ["lib/common.yaml"]` or `import: ["lib/cli.yaml"]`. User loops in `.loops/` can do the same — built-in fragment libraries resolve automatically, so no copying or symlinking is required. You can also define your own local fragments in your loop file or a local library.
