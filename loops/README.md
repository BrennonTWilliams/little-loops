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
| `backlog-flow-optimizer` | Iteratively diagnose the primary throughput bottleneck in the issue backlog |

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
| `docs-sync` | Verify documentation matches the codebase and fix broken links |

## Reinforcement Learning (RL)

| Loop | Description |
|---|---|
| `rl-policy` | Policy iteration template — act, observe reward, improve strategy until convergence |
| `rl-rlhf` | RLHF-style iterative improvement — generate candidate, score quality (0–10), refine until threshold |
| `rl-bandit` | Epsilon-greedy bandit — alternate between exploring new options and exploiting the best known |
| `rl-coding-agent` | **Policy+RLHF composite for agentic coding** — outer policy adapts strategy, inner RLHF polishes each artifact; reward = test pass rate × 0.5 + lint score × 0.3 + LLM weight × 0.2 |

## Automatic Prompt Optimization (APO)

| Loop | Description |
|---|---|
| `apo-feedback-refinement` | Feedback-driven prompt refinement — read target prompt, test, collect failures, refine |
| `apo-contrastive` | Contrastive prompt optimization — generate variants, compare pairs, advance the winner |
| `apo-opro` | OPRO-style — history-guided proposal loop until convergence |
| `apo-beam` | Beam search — generate N variants, score all, advance the winner |
| `apo-textgrad` | TextGrad-style — test on examples, compute failure gradient, apply refinement |

---

## Creating Custom Loops

See `ll-loop --help` and the [FSM Loop documentation](../docs/ARCHITECTURE.md) for loop authoring guidance.

To start from a built-in template: `ll-loop install <name>` copies it to `.loops/<name>.yaml` for local customization.
