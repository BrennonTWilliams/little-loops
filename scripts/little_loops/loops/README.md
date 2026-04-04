# Built-in Loops

Built-in FSM loops shipped with `little-loops`. Run any loop with `ll-loop run <name>`.

Install a loop into your project for customization: `ll-loop install <name>`

---

## Issue Management

| Loop | Description |
|---|---|
| `issue-discovery-triage` | Scan codebase for new issues, triage and create issue files |
| `issue-refinement` | Progressively refine active issues through format → score → refine pipeline |
| `issue-size-split` | Review issues for sizing, identify oversized ones, and split into smaller tasks |
| `issue-staleness-review` | Find old issues, review relevance, and close or reprioritize stale ones |
| `refine-to-ready-issue` | Pick the next issue and run format → refine → verify → confidence-check until ready |
| `backlog-flow-optimizer` | Iteratively diagnose the primary throughput bottleneck in the issue backlog |
| `prompt-across-issues` | Run an arbitrary prompt against every open/active issue sequentially; use `{issue_id}` placeholder to inject each issue's ID |

## Sprint & Worktree

| Loop | Description |
|---|---|
| `sprint-build-and-validate` | Create a sprint from the backlog, validate included issues, and execute |
| `worktree-health` | Continuous monitoring of orphaned worktrees and stale branches |

## Code Quality

| Loop | Description |
|---|---|
| `fix-quality-and-tests` | Sequential quality gate: lint + format + types must be clean before tests run |
| `dead-code-cleanup` | Find dead code, remove high-confidence items, and verify tests pass after each removal |
| `test-coverage-improvement` | Measure coverage, identify highest-risk gaps, write tests, verify, and iterate until target is met |
| `incremental-refactor` | Decompose a refactoring goal into safe atomic steps, execute each with test-gated commits, rollback and re-plan on failure |
| `docs-sync` | Verify documentation matches the codebase and fix broken links |

## General Purpose

| Loop | Description |
|---|---|
| `general-task` | Execute any ad-hoc task with auto-generated definition of done and verification |

## Quality Monitoring

| Loop | Description |
|---|---|
| `evaluation-quality` | Multi-dimensional quality health check across issue quality, code quality, and backlog health; routes to remediation loops when thresholds are breached |
| `context-health-monitor` | Monitor context health via scratch file accumulation and session log size; compact scratch files and archive stale outputs when pressure is detected |
| `outer-loop-eval` | Execute a target loop as a sub-loop, analyze its definition and execution trace, and produce a structured improvement report covering structural, logic, flow, and component issues |

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

---

## Creating Custom Loops

See `ll-loop --help` and the [FSM Loop documentation](../docs/ARCHITECTURE.md) for loop authoring guidance.

To start from a built-in template: `ll-loop install <name>` copies it to `.loops/<name>.yaml` for local customization.

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
