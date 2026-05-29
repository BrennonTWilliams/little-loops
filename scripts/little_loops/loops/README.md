# Built-in Loops

Built-in FSM loops shipped with `little-loops`. Run any loop with `ll-loop run <name>`.

Install a loop into your project for customization: `ll-loop install <name>`

---

## Routing

| Loop | Description |
|---|---|
| `loop-router` | Natural-language entry point — classifies a goal into the best-fit project or built-in loop (3-way: project / built-in / propose new), scores candidates, dispatches as a sub-loop, and summarises the result. Recommended starting point when you know *what* you want done but not *which loop* to run. |

## Issue Management

| Loop | Description |
|---|---|
| `issue-discovery-triage` | Scan codebase for new issues, triage and create issue files |
| `issue-refinement` | Progressively refine all active issues to ready-state by delegating each one to the `refine-to-ready-issue` sub-loop; uses `ll-issues next-action` to pick the highest-value action each cycle |
| `issue-staleness-review` | Find old issues, review relevance, and close or reprioritize stale ones |
| `refine-to-ready-issue` | Pick the next issue and run format → refine → wire → confidence-check until ready |
| `recursive-refine` | Refine one or more issues to readiness recursively; when size-review decomposes an issue into children, each child is enqueued and refined before the next sibling |
| `auto-refine-and-implement` | For each backlog issue in priority order: refine to ready, then implement; skips issues that fail refinement |
| `autodev` | Targeted refine-and-implement for a fixed set of issue IDs; interleaves refinement and implementation — each leaf is implemented via `ll-auto --only` as soon as it passes refinement, before the next leaf is refined. Assumes single-reader access to `.loops/tmp/` (concurrent `recursive-refine` runs can race on the broke-down handshake file). |
| `backlog-flow-optimizer` | Iteratively diagnose the primary throughput bottleneck in the issue backlog |
| `prompt-across-issues` | Run an arbitrary prompt against every open/active issue sequentially; use `{issue_id}` placeholder to inject each issue's ID |

## Sprint & Worktree

| Loop | Description |
|---|---|
| `sprint-build-and-validate` | Create a sprint from the backlog (or reuse an existing one via optional arg), refine issues, and execute |
| `worktree-health` | Continuous monitoring of orphaned worktrees and stale branches |

## Code Quality

| Loop | Description |
|---|---|
| `fix-quality-and-tests` | Sequential quality gate: lint + format + types must be clean before tests run |
| `dead-code-cleanup` | Find dead code, remove high-confidence items, and verify tests pass after each removal |
| `test-coverage-improvement` | Measure coverage, identify highest-risk gaps, write tests, verify, and iterate until target is met |
| `incremental-refactor` | Decompose a refactoring goal into safe atomic steps, execute each with test-gated commits, rollback and re-plan on failure |
| `docs-sync` | Verify documentation matches the codebase and fix broken links |

## Planning

| Loop | Description | Primary Inputs |
|---|---|---|
| `rn-plan` | Recursive-N planning loop — builds a structured plan from scratch with iterative rubric-driven refinement | `task` (natural language description) |
| `rn-refine` | Recursive-N refinement loop — improves an existing plan document using the same rubric cycle | `plan_file` (path to `.md`) |
| `rn-plan-apo` | Plan-quality gradient optimization for the `rn-plan` recursive planner — refines the planning prompt via text gradient until `target_plan_quality` is reached | `target_plan_quality` |

## Research & Knowledge

| Loop | Description | Primary Inputs |
|---|---|---|
| `deep-research` | Iterative web research synthesis loop — generates search queries, performs web searches, evaluates sources, identifies coverage gaps, and produces a structured cited Markdown report | `topic` (research question), `depth` (min rounds, default 3), `coverage_threshold_pct` (default 85) |
| `deep-research-arxiv` | Arxiv-only sibling of `deep-research` — constrains web search to `site:arxiv.org`, scores sources on relevance + recency (from arxiv submission date), and emits an arxiv-ID-keyed sources table plus a `## BibTeX` section in `report.md` | `topic` (research question), `depth` (min rounds, default 3), `coverage_threshold_pct` (default 85) |

## API Adoption

| Loop | Description |
|---|---|
| `adopt-third-party-api` | Scrape a vendor docs URL via `/ll:scrape-docs`, enumerate up to 7 significant endpoints/features, prove each via `ready-to-implement-gate`, and write a citation-linked integration playbook to `docs/integration-<domain>.md`; partial coverage (some targets refuted/exhausted) still produces a playbook with a top warning block. |
| `integrate-sdk` | Proof-driven SDK integration: branch on existing usage vs. greenfield, enumerate required surfaces (up to 7), prove each via `ready-to-implement-gate`, then scaffold integration code with `# Verified: .ll/learning-tests/<slug>.md` citations; blocks with a structured diagnosis if any surface is refuted or citations don't resolve to proven records. |

## General Purpose

| Loop | Description |
|---|---|
| `general-task` | Execute any ad-hoc task with auto-generated definition of done and verification |

## Quality Monitoring

| Loop | Description |
|---|---|
| `evaluation-quality` | Multi-dimensional quality health check across issue quality, code quality, and backlog health; routes to remediation loops when thresholds are breached |
| `context-health-monitor` | Monitor context health via scratch file accumulation and session log size; compact scratch files and archive stale outputs when pressure is detected |
| `outer-loop-eval` | Execute a target loop as a sub-loop, then delegate static and execution analysis to `/ll:debug-loop-run` and scoring/proposals to `/ll:audit-loop-run` to produce an improvement report |

## Reinforcement Learning (RL)

| Loop | Description |
|---|---|
| `rl-policy` | Policy iteration template — act, observe reward, improve strategy until convergence |
| `rl-rlhf` | RLHF-style iterative improvement — generate candidate, score quality (0–10), refine until threshold |
| `rl-bandit` | Epsilon-greedy bandit — alternate between exploring new options and exploiting the best known |
| `rl-coding-agent` | **Policy+RLHF composite for agentic coding** — outer policy adapts strategy, inner RLHF polishes each artifact; reward = test pass rate × 0.5 + lint score × 0.3 + LLM weight × 0.2 |

## Agent Evaluation

| Loop | Description |
|---|---|
| `agent-eval-improve` | Evaluate an AI agent on a task suite, score outputs, identify failure patterns, and iteratively refine agent config/prompts until quality target is reached |

## Automatic Prompt Optimization (APO)

| Loop | Description |
|---|---|
| `apo-feedback-refinement` | Feedback-driven prompt refinement — read target prompt, test, collect failures, refine |
| `apo-contrastive` | Contrastive prompt optimization — generate variants, compare pairs, advance the winner |
| `apo-opro` | OPRO-style — history-guided proposal loop until convergence |
| `apo-beam` | Beam search — generate N variants, score all, advance the winner |
| `apo-textgrad` | TextGrad-style — test on examples, compute failure gradient, apply refinement |
| `examples-miner` | Co-evolutionary corpus miner — harvest session logs, quality-gate via three-layer judge, calibrate to 40–80% difficulty band, run apo-textgrad as inner loop, synthesize adversarial examples from gradient signal, enforce diversity, publish fresh examples.json |

## Data & Testing

| Loop | Description |
|---|---|
| `dataset-curation` | Ingest raw data, quality-gate each item, fix or reject, balance distribution, validate schema, and publish |
| `prompt-regression-test` | CI for prompts: run a prompt suite against an LLM endpoint, score outputs against expected results, compare to baseline, and flag regressions |

## Greenfield & Eval-Driven

| Loop | Description |
|---|---|
| `greenfield-builder` | End-to-end greenfield project builder: spec analysis → tech research → design artifacts → eval harness → issue decomposition → refinement → eval-driven improvement cycle |
| `eval-driven-development` | Reusable eval-driven development cycle: implement issues, run eval harness, capture issues from failures, refine, and iterate until the harness passes |

## Harness / Templates

| Loop | Description |
|---|---|
| `harness-single-shot` | EXAMPLE: Single-shot harness demonstrating all evaluation phases (stall detection, concrete, semantic, invariant); `check_mcp` and `check_skill` as commented-out optional gates. Adapt for one-item workflows. |
| `harness-multi-item` | EXAMPLE: Multi-item harness with all five evaluation phases active (`check_concrete`, `check_mcp`, `check_skill`, `check_semantic`, `check_invariants`). Includes discover/advance loop. Adapt for batch workflows. |
| `html-website-generator` | Generator-evaluator harness for single-page HTML website creation — accepts a one-line description and iteratively generates, screenshots, and refines HTML/CSS/JS via Playwright CLI. Canonical demonstration of the GAN-style architecture from Anthropic's harness design article. |
| `html-anything` | Generalized HTML artifact harness — classifies artifact type (email, social card, résumé, dashboard, etc.) from a description, writes platform-specific brief and dynamic scoring rubric, then iteratively generates and refines `index.html` via Playwright CLI. |
| `cli-anything-bootstrap` | Generalized CLI bootstrap meta-loop — given a software target (path or repo URL), delegates 7-phase CLI generation to the `CLI-Anything` plugin's `/cli-anything` skill, classifies the target (desktop-gui / stateful-service / data-lib), bakes a per-target rubric, caches the generated CLI at `.loops/cli-anything/<hash>/`, and emits a project-local task loop to `.loops/generated/<target>-task.yaml` from a matching template under `lib/task-templates/`. Iterates against external evaluators (pip install exit code, `--help` walker, pytest pass-rate) per MR-1; refinement cycles delegate to `/cli-anything:refine`. Requires the CLI-Anything plugin to be installed. |
| `svg-image-generator` | Generator-evaluator harness for SVG icon and illustration creation — accepts a one-line description and iteratively generates, screenshots, and refines a self-contained SVG via Playwright CLI. Direct port of the html-website-generator pattern; no HTTP server required. |
| `svg-textgrad` | TextGrad-style SVG harness; optimizes the brief via structured gradient updates across iterations, with gradient history accumulation for repeated-failure escalation. |
| `loop-specialist-eval` | Behavioral eval harness for the loop-specialist agent; drives it against a seeded broken-verify-loop fixture and verifies the full monitor → diagnose → contract → refine → verify round-trip. |
| `hitl-compare` | Human-in-the-loop comparison harness — reads whitespace-separated inputs (file paths or raw text), extracts candidate review items with 2+ options, prunes implementation-level micro-decisions, and generates a single self-contained interactive HTML page with toggle/select controls and an "Export selections" affordance. |
| `hitl-md` | Human-in-the-loop single-document review harness — reads a markdown file (or raw text), decomposes it into GP-TSM saliency-modulated segments with multi-channel saliency (importance/anomaly/claim_type/confidence) and length-normalized credibility flags, and generates a self-contained interactive HTML page with sensemaking enhancements (staged highlighting, density slider, schema-switching, canvas minimap, calibrated friction), keyboard navigation, edit affordances (delete/insert/edit/flag), a "Copy AI prompt" control for flagged segments, and a "Copy updated markdown" reconstruction control. Styles source from design token CSS custom properties. |

---

## Creating Custom Loops

See `ll-loop --help` and the [FSM Loop documentation](../docs/ARCHITECTURE.md) for loop authoring guidance.

To start from a built-in template: `ll-loop install <name>` copies it to `.loops/<name>.yaml` for local customization.

### Fragment Libraries

Built-in fragment libraries are in `lib/`:

| Library | Purpose |
|---------|---------|
| `lib/common.yaml` | Generic type-pattern fragments (`shell_exit`, `llm_gate`, `retry_counter`, `numeric_gate`) |
| `lib/cli.yaml` | Pre-filled ll- CLI tool fragments (`ll_auto`, `ll_check_links`, `ll_issues_list`, `ll_loop_run`, etc.) |
| `lib/benchmark.yaml` | Harbor-format benchmark runner fragment (`run_benchmark`) with `harbor_scorer` evaluator |
| `lib/score-plan-quality.yaml` | Plan-quality scoring fragment (`score_plan_quality`) used by `rn-plan-apo` to score plan trees on four dimensions |

Import a library in any loop:

```yaml
import:
  - lib/cli.yaml
```

Each fragment may include an optional `description` field documenting what it provides and what the calling state must supply:

```yaml
fragments:
  shell_exit:
    description: |
      Shell command evaluated by exit code.
      State must supply: action, on_yes, on_no (and optionally on_error, timeout).
    action_type: shell
    evaluate:
      type: exit_code
```

The `description` field is stripped before merge — the FSM engine never sees it. To view fragment names and descriptions without opening the raw YAML, use:

```bash
ll-loop fragments lib/common.yaml
ll-loop fragments lib/cli.yaml
```

See [`docs/guides/LOOPS_GUIDE.md`](../docs/guides/LOOPS_GUIDE.md) for fragment authoring and the full fragment table.

### Composing Loops

Any built-in loop can be used as a **sub-loop** inside another loop via the `loop:` field on a state. This lets you chain existing loops into multi-step pipelines without duplicating their logic:

```yaml
states:
  run_quality:
    loop: "fix-quality-and-tests"   # references .loops/fix-quality-and-tests.yaml
    context_passthrough: true       # optional: share parent context & merge child captures
    on_success: "next_step"
    on_failure: "done"
```

For full sub-loop documentation — including `context_passthrough`, verdict aliases (`on_success`/`on_failure`), and worked examples — see [`skills/create-loop/reference.md`](../skills/create-loop/reference.md).
