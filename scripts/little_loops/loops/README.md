# Built-in Loops

Built-in FSM loops shipped with `little-loops`. Run any loop with `ll-loop run <name>`.

Install a loop into your project for customization: `ll-loop install <name>`

> **Finding the right loop.** `ll-loop list` shows only **public** (user-facing) loops by
> default — delegated-only sub-loops (`visibility: internal`, e.g. `oracles/*`) and
> demo/templates (`visibility: example`, e.g. the `harness-*` EXAMPLE loops) are hidden.
> Use `--all`, `--internal`, or `--examples` to see them. Not sure which loop you want?
> Describe the goal and let the router pick:
> `ll-loop run loop-router --input goal="<what you want done>"`.

---

## Routing

| Loop | Description |
|---|---|
| `loop-router` | Natural-language entry point — classifies a goal into the best-fit project or built-in loop (3-way: project / built-in / propose new), scores candidates, dispatches as a sub-loop, and summarises the result. Recommended starting point when you know *what* you want done but not *which loop* to run. |
| `loop-composer-adaptive` | Adaptive loop composer with reassess gate — plans a multi-loop pipeline from a goal, executes each stage, and re-evaluates the remaining plan after each stage to adapt to new information before proceeding. |
| `goal-cluster` | Multi-goal orchestrator for sprint- or EPIC-shaped input. Groups goals into batches by predicted loop, dispatches each batch sequentially with cross-batch context propagation and per-batch reassess gates, and synthesizes a cluster-wide summary. Use when you have multiple related goals that share context. |

## Issue Management

| Loop | Description |
|---|---|
| `issue-discovery-triage` | Scan codebase for new issues, triage and create issue files |
| `issue-refinement` | Progressively refine all active issues to ready-state by delegating each one to the `refine-to-ready-issue` sub-loop; uses `ll-issues next-action` to pick the highest-value action each cycle |
| `issue-staleness-review` | Find old issues, review relevance, and close or reprioritize stale ones |
| `refine-to-ready-issue` | Pick the next issue and run format → refine → wire → confidence-check until ready |
| `recursive-refine` | Refine one or more issues to readiness recursively; when size-review decomposes an issue into children, each child is enqueued and refined before the next sibling |
| `auto-refine-and-implement` | For each issue in priority order: refine to ready, then implement; skips issues that fail refinement. Optional `scope` param (sprint name or EPIC-NNN) limits to that set via SprintManager; omit for full backlog poll. When `scope` is an EPIC-NNN id and `parallel.epic_branches.enabled` is true, ensures the `epic/<EPIC-ID>-<slug>` integration branch exists (create-without-switch) before delegating, and runs a post-implementation `test_cmd`/`lint_cmd` verify pass folded into `summary.json` (ENH-2601) |
| `autodev` | Targeted refine-and-implement for a fixed set of issue IDs; interleaves refinement and implementation — each leaf is implemented via `ll-auto --only` as soon as it passes refinement, before the next leaf is refined. Uses per-instance `${context.run_dir}` for temp files and `scope: ["${context.run_dir}"]` to allow concurrent instances with disjoint issue sets. For implementation isolation, use `--worktree`. |
| `backlog-flow-optimizer` | Iteratively diagnose the primary throughput bottleneck in the issue backlog |
| `prompt-across-issues` | Run an arbitrary prompt against every open/active issue sequentially; use `{issue_id}` placeholder to inject each issue's ID. Optionally constrain to a single issue type via `--context type=BUG` (one of `BUG`, `FEAT`, `ENH`, `EPIC`). Optionally scope to children of an epic via `--context parent=EPIC-NNN`. Both filters may be combined. |

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
| `brainstorm` | Double-diamond ideation loop — diverges under forced lenses (contrarian, first-principles, end-user, ops-cost, invert-the-goal, cross-domain analogy, plus 2–3 brief-derived lenses), deduplicates via difflib, clusters survivors, relative-ranks top-k ideas, and synthesizes a best-of hybrid into brainstorm.md | `brief` (ideation prompt), `sink` (none/file/issue/decision), `top_k` (default 3), `novelty_threshold` (default 0.55), `max_saturation` (default 2) |
| `rn-plan` | Recursive-N planning loop — builds a structured plan from scratch with iterative rubric-driven refinement | `task` (natural language description) |
| `rn-refine` | Recursive-N refinement loop — treats an existing plan as the root of a decomposition tree and refines it recursively to adaptive depth: refine each node to rubric convergence, decide leaf-vs-decompose (ADaPT-style), split coarse nodes into child sub-plans enqueued depth-first, then roll the refined leaves bottom-up into a reassembled plan written back over the source. Per-node refinement + the decompose decision are delegated to `oracles/plan-node-refine`; depth is bounded by `max_depth`/`max_nodes` | `plan_file` (path to `.md`); optional `max_depth` (default 3), `max_node_iters` (default 2), `max_nodes` (default 40) |
| `rn-plan-apo` | Plan-quality gradient optimization for the `rn-plan` recursive planner — refines the planning prompt via text gradient until `target_plan_quality` is reached | `target_plan_quality` |
| `rn-implement` | Queue orchestrator for recursive plan-and-implement — delegates per-issue remediation to rn-remediate and decomposition to rn-decompose | `<issue-id>` (single or comma-separated list) |
| `rn-remediate` | Iterative deepening remediation cycle (diagnose → remediate → re_assess → check_convergence) extracted from rn-implement Phases 2-4; after FEAT-2552, `implement.on_yes` → `run_code_gate` (code-run-gate oracle, FEAT-2551) → `emit_implemented` so a broken build/test/typecheck/lint can no longer earn `IMPLEMENTED` | `issue_id` (issue ID to remediate), `readiness_threshold`, `outcome_threshold`, `max_remediation_passes`, `min_pass_rate` (default 1.0) |
| `rn-decompose` | Issue decomposition pipeline (size review → child detection → enqueue with cycle detection) extracted from rn-implement Phase 5 | `issue_id` (issue ID to decompose), `run_dir` (parent run directory) |

## Research & Knowledge

| Loop | Description | Primary Inputs |
|---|---|---|
| `deep-research` | Iterative web research synthesis loop — generates search queries, performs web searches, evaluates sources, identifies coverage gaps, and produces a structured cited Markdown report. Pass `context.source_filter="site:arxiv.org"` and `context.academic_mode=true` for arxiv-only research (or use the `deep-research-arxiv` alias) | `topic` (research question), `depth` (min rounds, default 3), `coverage_threshold_pct` (default 85), `source_filter` (search constraint, default: web-wide), `academic_mode` (BibTeX + recency scoring, default: false) |
| `deep-research-arxiv` | Alias for `deep-research` with `source_filter=site:arxiv.org` and `academic_mode=true` — hidden from `ll-loop list` (visibility: internal); delegates entirely to deep-research (ENH-2161) | same as deep-research |
| `apply-research` | Document ingestion pipeline for local research files — reads text, Markdown, or PDF files, extracts and scores ideas by relevance to the project, filters below threshold, synthesizes actionable issue descriptions, and captures Issues via `/ll:capture-issue`; produces a summary report of captured IDs and filtered counts | `files` (space-separated file paths), `relevance_threshold` (default 0.5), `max_issues_per_file` (default 10) |

## API Adoption

| Loop | Description |
|---|---|
| `adopt-third-party-api` | Scrape a vendor docs URL via `/ll:scrape-docs`, enumerate up to 7 significant endpoints/features, prove each via `ready-to-implement-gate`, and write a citation-linked integration playbook to `docs/integration-<domain>.md`; partial coverage (some targets refuted/exhausted) still produces a playbook with a top warning block. |
| `integrate-sdk` | Proof-driven SDK integration: branch on existing usage vs. greenfield, enumerate required surfaces (up to 7), prove each via `ready-to-implement-gate`, then scaffold integration code with `# Verified: .ll/learning-tests/<slug>.md` citations; blocks with a structured diagnosis if any surface is refuted or citations don't resolve to proven records. |
| `learning-tests-audit` | Registry health audit — scans the Learning Test Registry for stale records via a three-phase detection pipeline (installed-package enumeration → LLM-assisted package classification → PyPI/npm registry release-date comparison), bulk-marks stale records via `ll-learning-tests mark-stale`, and produces a four-section triage report (newly stale, already stale, refuted, open TODOs). Run at sprint start for registry maintenance. |
| `migrate-sdk-version` | Re-proves stale learning-test records after a dependency bump — iterates the stale queue, re-runs `/ll:explore-api` for each target, classifies each result as `still-valid`, `needs-upgrade`, or `refuted`, updates record status atomically, and produces a triage report. Run after `learning-tests-audit` marks records stale. |
| `proof-first-task` | Opt-in wrapper that gates any implementation loop on the Learning-Test Registry — proves a caller-supplied `targets_csv` (the registered `learning_tests_required` list) directly when given; otherwise falls back to `assumption-firewall`, which extracts external-API assumptions from the issue file, classifies them as testable or untestable, and proves testable claims (recording untestable ones via `--assume`). Either path then delegates to a caller-specified impl loop (default `general-task`). When no `issue_file` is given, skips the gate and runs the impl loop directly. |

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
| `rubric-refine` | Converge loop that scores an artifact on a multi-dimension rubric, routes to tier-specific repair (light or deep), and re-scores until the aggregate meets `threshold_high`. Supply `subject` (path or description) and `rubric_dimensions` (pipe-separated). Demonstrates `lib/rubric-router.yaml` fragment usage. |
| `policy-refine` | Score an artifact on clarity/completeness/feasibility/security, route via a declarative policy rule table to escalate/deep_repair/light_repair/done. Supply `subject` and optionally override `policy_rules`. Demonstrates `lib/policy-router.yaml` conjunctive decision-table routing. |

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
| `apo-feedback-refinement` | Feedback-driven prompt refinement — read target prompt, test, collect failures, refine. Inherits common APO context defaults from lib/apo-shape-a (ENH-2161). |
| `apo-contrastive` | Contrastive prompt optimization — generate variants, compare pairs, advance the winner. Inherits common APO context defaults from lib/apo-shape-a (ENH-2161). |
| `apo-opro` | OPRO-style — history-guided proposal loop until convergence |
| `apo-beam` | Beam search — generate N variants, score all, advance the winner |
| `apo-textgrad` | TextGrad-style — test on examples, compute failure gradient, apply refinement |
| `examples-miner` | Co-evolutionary corpus miner — harvest session logs, quality-gate via three-layer judge, calibrate to 40–80% difficulty band, run apo-textgrad as inner loop, synthesize adversarial examples from gradient signal, enforce diversity, publish fresh examples.json |

## Data & Testing

| Loop | Description |
|---|---|
| `dataset-curation` | Ingest raw data, quality-gate each item, fix or reject, balance distribution, validate schema, and publish |
| `sft-corpus` | Stage session transcripts, enrich with history.db session-quality metadata, filter by opt-in quality predicates, track rejections, and publish SFT training corpus |
| `prompt-regression-test` | CI for prompts: run a prompt suite against an LLM endpoint, score outputs against expected results, compare to baseline, and flag regressions |

## Greenfield & Eval-Driven

| Loop | Description |
|---|---|
| `rn-build` | **(Recommended)** Capstone orchestration loop for the recursive spec-to-project builder: spec validation → tech research → design artifacts → scope EPIC → issue refinement → eval harness → goal-cluster execution (dispatching batches to rn-implement with value_ranked scheduling) → eval gate with bounded re-entry → structured JSON result. |
| `eval-driven-development` | Reusable eval-driven development cycle: implement issues, run eval harness, capture issues from failures, refine, and iterate until the harness passes |

## Harness / Templates

| Loop | Description |
|---|---|
| `harness-single-shot` | EXAMPLE: Single-shot harness demonstrating all evaluation phases (stall detection, concrete, semantic, invariant); `check_mcp` and `check_skill` as commented-out optional gates. Adapt for one-item workflows. |
| `harness-multi-item` | EXAMPLE: Multi-item harness with all five evaluation phases active (`check_concrete`, `check_mcp`, `check_skill`, `check_semantic`, `check_invariants`). Includes discover/advance loop. Adapt for batch workflows. |
| `harness-plan-research-implement-report` | EXAMPLE: Specialist-role pipeline (Variant C) with Plan -> Research -> Implement -> Report decomposition. Full evaluation chain (stall detection, concrete gate, LLM judge, diff invariants). Optional HITL review_plan gate as commented-out block. Adapt for deep refactors and multi-file features. |
| `html-website-generator` | Generator-evaluator harness for single-page HTML website creation — accepts a one-line description and iteratively generates, screenshots, and refines HTML/CSS/JS via Playwright CLI. Canonical demonstration of the GAN-style architecture from Anthropic's harness design article. |
| `html-anything` | Generalized HTML artifact harness — classifies artifact type (email, social card, résumé, dashboard, etc.) from a description, writes platform-specific brief and dynamic scoring rubric, then iteratively generates and refines `index.html` via Playwright CLI. |
| `cli-anything-bootstrap` | Generalized CLI bootstrap meta-loop — given a software target (path or repo URL), delegates 7-phase CLI generation to the `CLI-Anything` plugin's `/cli-anything` skill, classifies the target (desktop-gui / stateful-service / data-lib), bakes a per-target rubric, caches the generated CLI at `.loops/cli-anything/<hash>/`, and emits a project-local task loop to `.loops/generated/<target>-task.yaml` from a matching template under `lib/task-templates/`. Iterates against external evaluators (pip install exit code, `--help` walker, pytest pass-rate) per MR-1; refinement cycles delegate to `/cli-anything:refine`. Requires the CLI-Anything plugin to be installed. |
| `svg-image-generator` | Generator-evaluator harness for SVG icon and illustration creation — accepts a one-line description and iteratively generates, screenshots, and refines a self-contained SVG via Playwright CLI. Direct port of the html-website-generator pattern; no HTTP server required. |
| `openscad-model-generator` | Generator-evaluator harness for parametric OpenSCAD model creation — accepts a natural language part description and iteratively generates and refines a .scad file via multi-angle CLI renders (iso/front/top), scoring against a CAD rubric (correctness, completeness, printability, parametrics). Requires the openscad CLI. Opt-in STL export via export_stl context variable. |
| `interactive-component-generator` | Fan-out generator-evaluator harness for self-contained INTERACTIVE HTML — profiles a natural-language brief or referenced data file, ideates many candidate interactive components (data-viz idioms + widgets), ranks them, builds the best 3–5 each in isolation via `oracles/generator-evaluator`, smoke-tests that each works as advertised, then selects the best 1–3 and composes them into one self-contained `index.html`. Configurable iframe / shadow / scoped isolation; offline (no-CDN) by default. |

## Animation / Generative Art

| Loop | Description |
|---|---|
| `generative-art` | Consolidated base for generative art harnesses — iteratively generates and refines a self-contained HTML sketch via multi-frame screenshots; p5.js by default (`context.framework: p5js`). Use `p5js-sketch-generator` or `pixi-generative-art` aliases, or invoke directly with `context.framework` override (ENH-2161). |
| `p5js-sketch-generator` | p5.js alias for `generative-art` — inherits the full p5.js sketch harness (noLoop/loop frame-exact screenshots, CDN load, randomSeed/noiseSeed seeding). Delegates to generative-art base (ENH-2161). |
| `pixi-generative-art` | PixiJS alias for `generative-art` — overrides plan/generate/evaluate/score states with GPU-specific logic (filters, blend modes, ParticleContainer; ticker.stop/start frame-exact screenshots via window.__pixiApp). Delegates to generative-art base (ENH-2161). |
| `pixi-data-viz` | Generator-evaluator harness for animated PixiJS data visualizations — embeds synthetic dataset as JSON literal; hard-gates `encoding_clarity` at threshold 7; evaluates whether motion aids comprehension; same `window.__pixiApp` ticker-pause contract as `pixi-generative-art`. |
| `adversarial-redesign` | Generator-vs-critic figure refinement demo using AutoFigure — a generator produces an SVG from a text concept, a critic returns structured complaints, the loop regenerates addressing each complaint and exits on score-improvement stall or SVG-diff convergence. Every round is persisted for demo playback. Requires: `pip install -e ./AutoFigure && playwright install chromium` + `OPENROUTER_API_KEY`. Example: `ll-loop run adversarial-redesign --input concept="how a transformer attends"` |
| `svg-textgrad` | TextGrad-style SVG harness; optimizes the brief via structured gradient updates across iterations, with gradient history accumulation for repeated-failure escalation. |
| `rlhf-animated-svg` | RLHF-style generate→score→refine harness for animated SVG artifacts — generates a zero-dependency HTML file with inline SVG animated via anime.js, smoke-tests it in headless Playwright, scores multi-frame screenshots (1000/3000/5000/7000ms) on a correctness/aesthetics/smoothness/completeness rubric via a vision API, and refines until threshold. Adds component-priority ranking, oscillation/score-streak guards, concept-reset escalation, and cumulative optimization summaries. Runs out-of-box with a built-in demo input; override with `--input "<description>"`. Optional gates degrade gracefully when Playwright / `VISION_*` env are absent. |
| `rlhf-svg-evaluate` | Standalone evaluation sub-loop for `rlhf-animated-svg` — handles the `smoke_test → score → track_correlation` pipeline as a child FSM. Accepts `run_dir`, `quality_target`, `smoke_bypass_threshold`, and `exploit_cutoff` as context parameters; returns `VISION_PASS` or `VISION_FAIL` sentinel for parent routing. Invoked via `loop: rlhf-svg-evaluate` with `with:` bindings. |
| `rlhf-svg-refine` | Standalone refinement sub-loop for `rlhf-animated-svg` — handles the `rank_components → review_critique → apply_refinements → self_diagnose → write_summary` pipeline as a child FSM. Accepts `run_dir`, `animation_plan`, `fix_plan`, `component_ranking`, `global_iteration`, `explore_cutoff`, `exploit_cutoff`, `quality_target`, and `design_tokens_context` as context parameters. Uses `${context.global_iteration}` for phase detection to stay consistent with the parent orchestrator's iteration count. Returns `REPLAN_NEEDED` in `review_critique` output for parent routing. Invoked via `loop: rlhf-svg-refine` with `with:` bindings. |
| `rlhf-svg-generate` | Standalone generation sub-loop for `rlhf-animated-svg` — handles the `plan_animation → render_animation → verify_render` pipeline as a child FSM. Accepts `input`, `run_dir`, `global_iteration`, `design_tokens_context`, `quality_target`, `explore_cutoff`, and `exploit_cutoff` as context parameters. Uses `${context.global_iteration}` for phase detection to stay consistent with the parent orchestrator's iteration count. Produces `output.html` in `run_dir` on success (`done`) or terminates at `plan_failed` on retry exhaustion. Invoked via `loop: rlhf-svg-generate` with `with:` bindings. |
| `loop-specialist-eval` | Behavioral eval harness for the loop-specialist agent; drives it against a seeded broken-verify-loop fixture and verifies the full monitor → diagnose → contract → refine → verify round-trip. |
| `hitl-compare` | Human-in-the-loop comparison harness — reads whitespace-separated inputs (file paths or raw text), extracts candidate review items with 2+ options, prunes implementation-level micro-decisions, and generates a single self-contained interactive HTML page with toggle/select controls and an "Export selections" affordance. |
| `hitl-md` | Human-in-the-loop single-document review harness — reads a markdown file (or raw text), decomposes it into GP-TSM saliency-modulated segments with multi-channel saliency (importance/anomaly/claim_type/confidence) and length-normalized credibility flags, and generates a self-contained interactive HTML page with sensemaking enhancements (staged highlighting, density slider, schema-switching, canvas minimap, calibrated friction), keyboard navigation, edit affordances (delete/insert/edit/flag), a "Copy AI prompt" control for flagged segments, and a "Copy updated markdown" reconstruction control. Styles source from design token CSS custom properties. |

## Oracle Sub-loops

Internal sub-loops invoked via `loop:` delegation from parent loops. Not intended for direct `ll-loop run` use — they are always driven by a caller that binds required `parameters:` via `with:`.

| Loop | Description |
|---|---|
| `oracles/generator-evaluator` | Iterative artifact generation with visual evaluation — generate → Playwright screenshot → LLM rubric score until ALL_PASS or max_iterations; used by html-website-generator, html-anything, hitl-md, p5js-sketch-generator, and svg-image-generator. |
| `oracles/generator-evaluator-cli` | CLI-render oracle variant of generator-evaluator (`from: generator-evaluator`) — overrides evaluate (Playwright → parameterized shell render command) and snapshot (single file → multi-file views/*.png). Zero blast radius on existing callers; intended for CLI-rendered artifacts (OpenSCAD, graphviz, etc.). Caller passes render_command via with: bindings. |
| `oracles/oracle-capture-issue` | Capture and classify a single issue from conversation context, write it to `.issues/`, and emit the path; thin wrapper around `/ll:capture-issue` with `context_passthrough: true`. |
| `oracles/enumerate-and-prove` | Parse a tagged ENUMERATE_JSON line from LLM output, validate and flatten the targets list, then prove each target via ready-to-implement-gate; used by adopt-third-party-api and integrate-sdk to eliminate duplicated parse → flatten → prove state chains. |
| `oracles/research-coverage` | Iterative web research synthesis oracle — generate queries → search web → evaluate sources → score coverage until sufficient, then synthesize a report; parameterized for general web research (`source_filter=""`, `academic_mode=false`) and arxiv-only research (`source_filter="site:arxiv.org"`, `academic_mode=true`); used by deep-research and deep-research-arxiv (ENH-1876). |
| `oracles/plan-node-refine` | Per-node refinement oracle for the recursive `rn-refine` planner — refines ONE node of the plan decomposition tree to rubric convergence (reusing `oracles/plan-research-iteration` + the `plan_rubric_score` fragment, scoped to the node's own `nodes/<id>/` working dir), then makes the adaptive-depth decision (LEAF vs DECOMPOSE). On DECOMPOSE it writes child sub-plans, allocates child node ids, and enqueues them depth-first; depth/node-budget caps (`max_depth`, `max_nodes`) keep the tree bounded. Returns an outcome token (`REFINED_LEAF` / `DECOMPOSED` / `REFINED_CAPPED` / `REFINE_FAILED`) for the parent. |
| `oracles/code-run-gate` | Tier-1 deterministic oracle (FEAT-2551) — runs the project's build / test / typecheck / lint / service_health command matrix and emits `GATE_PASS` / `GATE_FAILED` / `GATE_SKIP` via the parent↔sub-loop token channel. Only `exit_code` / `output_numeric` / `classify` evaluators (MR-1 trivial); all artifacts under `${context.run_dir}/` (MR-3 compliant). Self-skips when its command field is null; emits `GATE_SKIP` when ALL six command fields are null (docs-only no-op). Used by FEAT-2552's wiring into `rn-implement`/`rn-remediate`. |

---

## Creating Custom Loops

See `ll-loop --help` and the [FSM Loop documentation](../docs/ARCHITECTURE.md) for loop authoring guidance.

To start from a built-in template: `ll-loop install <name>` copies it to `.loops/<name>.yaml` for local customization.

### Fragment Libraries

Built-in fragment libraries are in `lib/`:

| Library | Purpose |
|---------|---------|
| `lib/common.yaml` | Generic type-pattern fragments (`shell_exit`, `llm_gate`, `retry_counter`, `numeric_gate`, `with_throttle`, `with_rate_limit_handling`, `parse_tagged_json`, `queue_pop`, `queue_track`, `diff_stall_gate`, `score_stall_gate`) |
| `lib/cli.yaml` | Pre-filled ll- CLI tool fragments (`ll_auto`, `ll_check_links`, `ll_issues_list`, `ll_loop_run`, etc.) |
| `lib/benchmark.yaml` | Harbor-format benchmark runner fragment (`run_benchmark`) with `harbor_scorer` evaluator |
| `lib/score-plan-quality.yaml` | Plan-quality scoring fragment (`score_plan_quality`) used by `rn-plan-apo` to score plan trees on four dimensions |
| `lib/prompt-fragments.yaml` | Reusable prompt-construction fragments for building structured LLM inputs |
| `lib/harness.yaml` | Harness evaluation fragments (`playwright_screenshot`, `ll_rubric_score`) — Playwright screenshot capture and LLM rubric scoring; used by `oracles/generator-evaluator` |
| `lib/composer.yaml` | Orchestration fragments for loop-composer and loop-composer-adaptive (`discover_loops`, `validate_plan`, `present_plan`, `reassess`) — shared by loop-composer (FEAT-1808) and loop-composer-adaptive (FEAT-1983) |
| `lib/rubric-router.yaml` | Score-on-rubric → 3-tier route → repair converge-loop fragments (`rubric_score`, `rubric_parse_scores`, `rubric_route_high`, `rubric_route_medium`) — implements the quality-gate pattern: score → parse aggregate → route high/medium/low → repair → re-score until threshold met |
| `lib/policy-router.yaml` | General multi-axis decision-table routing fragments (`policy_parse_scores`, `policy_table_dispatch`) — declarative, priority-ordered rule table maps per-dimension scores to action states via conjunctive (`&`-joined) predicates; emits winning token via `classify` evaluator + `route:` dispatch; source-agnostic (any scorer may write the per-dim score files) |

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
ll-loop fragments lib/prompt-fragments.yaml
```

See [`docs/guides/LOOPS_GUIDE.md`](../docs/guides/LOOPS_GUIDE.md) for fragment authoring and [`docs/guides/LOOPS_REFERENCE.md`](../docs/guides/LOOPS_REFERENCE.md) for the full fragment table.

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
