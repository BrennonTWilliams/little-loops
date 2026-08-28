# little-loops Goals

Product goals for `little-loops`, the public tool this repo plans and designs for. Used by `/ll:scan-product` and `/ll:align-issues` to score backlog alignment.

## 1. Token-cost reduction

Reduce the token cost of running little-loops loops, skills, and agents without losing correctness — via context compression, scratch-pad offload, and cost-aware prompting. See `docs/research/2026-07-02-token-cost-optimal-techniques.md`, `docs/research/token-cost-reduction-arxiv-research-report.md`, `docs/research/token-cost-reduction-gh-research.md`.

## 2. Multi-repo / multi-host generalization

Let a single little-loops installation plan and route work across multiple repos and multiple coding-agent hosts (Claude Code, Codex, others), rather than assuming a single mono-repo / single-host setup. See `docs/design/2026-07-10-multi-repo-support-design.md`, `docs/plans/2026-06-25-multi-host-generalization-sequencing.md`, `docs/design/2026-07-11-host-agnostic-advisor.md`.

## 3. Loop / FSM automation

Grow the FSM-based loop system (`ll-loop`) as the core automation primitive — more reliable state machines, built-in audit loops, and a generic queue for scheduling work across loops. See `docs/design/2026-07-07-audit-loop-design.md`, `docs/plans/built-in-audit-loop.md`, `docs/design/2026-07-17-generic-ll-queue-design.md`.

## 4. Artifact / dashboard UX

Improve how little-loops surfaces its work back to users — artifact templates, dashboards, and next-action recommendations that make automation state legible. See `docs/design/2026-07-10-artifact-templates-design.md`, `docs/design/next-action-recommender-design.md`.

## 5. APO / RL self-improvement

Enable little-loops to improve its own prompts, skills, and loops over time via automated prompt optimization (APO) and reinforcement-style feedback loops. See `docs/plans/2026-07-17-apo-bootstrap.md`, `docs/plans/goals-lifecycle-design.md`.

## 6. Fine-tuning dataset export

Turn the agent trajectories already captured in `.ll/history.db` into exportable, per-Skill / per-FSM-state fine-tuning datasets, so a small model can be specialized to a single skill or loop state. Unlike goal 5 (which optimizes prompts against a fixed frontier model), this goal treats little-loops as a *dataset factory* built on real logged tool-call traces — a stronger starting point than the synthetic-data approach used by comparable tiny-model efforts. See `docs/design/2026-07-24-fine-tuning-dataset-export-design.md`, `docs/research/2026-07-22-fine-tuning-tiny-llms-for-on-device-agents.md`.

## 7. Agent reliability & quality observability

Turn `.ll/history.db` and loop/harness telemetry into evidence a team can act on — longitudinal agent-quality trends, regression detection, cross-repo rollups, and deterministic (non-LLM) verification artifacts. Distinct from goal 3 (build the loops) and goal 5 (self-improvement): this goal is about *knowing whether the agents are any good*. See `docs/design/2026-07-24-agent-quality-observability-design.md`, `business-strategy.md` §2 Path A.
