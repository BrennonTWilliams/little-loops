---
discovered_date: "2026-04-16"
discovered_by: capture-issue
source: ~/.claude/plans/review-this-open-source-cosmic-galaxy.md
---

# FEAT-1120: Harness-Optimize Loop (Score-Gated Hill-Climbing on Skills/Commands/CLAUDE.md)

## Summary

Add a new built-in loop `harness-optimize.yaml` that treats a configured target file set (e.g., an agent definition, a skill, a command prompt, or `CLAUDE.md`) as the mutable surface and iteratively improves it against a benchmark. Each iteration proposes an edit, runs a benchmark via `lib/benchmark.yaml` (FEAT-1119), accepts the change if score rises and reverts otherwise, and commits accepted mutations to a branch.

## Current Behavior

- little-loops has 45 FSM loops including `apo-textgrad`, `apo-beam`, `apo-opro`, `apo-contrastive`, `apo-feedback-refinement` — these optimize prompts.
- No loop mutates skills, commands, or `CLAUDE.md` and gates acceptance on a numeric benchmark score.
- No loop implements the "propose → score → accept-if-rise / revert-if-not" pattern over a declared mutable target set.

This is the gap autoagent fills with its `agent.py` + `program.md` core loop. little-loops has the pieces (apo mutation patterns, git integration, worktrees) but no loop that composes them into score-gated hill-climbing on harness artifacts.

## Expected Behavior

- `scripts/little_loops/loops/harness-optimize.yaml` runs the loop: read directive → propose mutation → run benchmark fragment → accept/revert → commit.
- Targets are declared via a `targets:` list (file paths or globs). Mutations only touch those files.
- Each iteration produces one git commit on a dedicated branch when accepted; rejected mutations leave no trace.
- Score trajectory persists to `.ll/runs/harness-optimize/<run-id>/trajectory.jsonl` so runs are resumable to best state, not last state.
- Reuses existing primitives: `apo-feedback-refinement.yaml` mutation pattern, `lib/benchmark.yaml` for scoring, worktree isolation for crash safety.

## Motivation

This feature would:
- Give little-loops the single capability that sets autoagent apart — score-gated self-improvement on harness artifacts. Without this, little-loops can optimize prompts but not skills/commands/CLAUDE.md.
- Reuse (not duplicate) the existing 45-loop library. Mutation proposal rides on `apo-feedback-refinement`; scoring rides on FEAT-1119; git revert rides on existing integration.
- Enable long-horizon overnight runs that materially improve the harness the user ships.

## Use Case

**Who**: Power user / maintainer improving a specific skill, agent, or CLAUDE.md against a held-out benchmark

**Context**: Has a task set (internal `.issues/completed/` reproduced as tasks, or external Harbor suite) and wants the harness tuned against it

**Goal**: Run `ll-loop run harness-optimize --targets skills/foo/SKILL.md --tasks-dir ./benchmarks/foo` and walk away

**Outcome**: A branch with N commits, each raising the score; a `trajectory.jsonl` showing accept/reject history; the best-scoring version at HEAD

## Proposed Solution

### New: `scripts/little_loops/loops/harness-optimize.yaml`

States:
- `load_directive` — read `.ll/program.md` if present (FEAT-1121) or CLI args
- `baseline_score` — run `lib/benchmark.yaml` on the pristine target set; store as baseline
- `propose` — invoke an LLM state (pattern from `apo-feedback-refinement`) to propose an edit to one target file, conditioned on the directive, current target contents, and last failure diagnosis
- `apply` — write the proposed edit (to worktree)
- `score` — run `lib/benchmark.yaml`
- `gate` — if `score > best_score`: commit, update `best_score`, write `trajectory.jsonl` entry (accepted); else: revert via `git restore`, write trajectory entry (rejected)
- `loop back to propose` until budget exhausted or score plateaus

### `scripts/little_loops/fsm/schema.py`

Likely no new schema — declare `targets:` via loop-level `context:` / parametrization. If follow-up shows a first-class `targets:` field is cleaner, add then.

### `scripts/little_loops/cli/loop.py`

Accept `--targets` and `--tasks-dir` pass-through for `harness-optimize` runs. If FEAT-1121 lands first, default these from `.ll/program.md`.

### Reuse

- Mutation proposal: copy the LLM-state shape from `loops/apo-feedback-refinement.yaml`
- Parallel proposal evaluation: reuse `parallel:` state (FEAT-1072 family) once available, for concurrent proposals
- Git integration: worktree-per-run, commit on accept, `git restore` on reject

## Related Key Documentation

| Document | Relevance |
|---|---|
| `docs/ARCHITECTURE.md` | FSM executor, worktree isolation |
| `docs/reference/API.md` | Loop APIs, evaluator registration |
| `loops/apo-feedback-refinement.yaml` | Mutation proposal state pattern to reuse |

## Acceptance Criteria

- [ ] `loops/harness-optimize.yaml` parses, validates, and lists in `ll-loop list`
- [ ] Integration test: run against a 3-task fixture; assert score monotonically non-decreases across accepted iterations
- [ ] Rejected mutation leaves working tree clean (`git status` empty after revert)
- [ ] `trajectory.jsonl` written with one row per iteration (fields: iter, proposed_file, score, accepted, commit_sha)
- [ ] Resume: killing mid-run and re-running resumes at best-score HEAD, not last-attempted HEAD
- [ ] Docs: `docs/reference/loops.md` documents the loop; `/ll:help` includes it
- [ ] No regression: existing `apo-*` loops still pass

## Dependencies

Blocked by: FEAT-1119 (benchmark adapter fragment) — this loop's `score` state depends on it.

Related: FEAT-1121 (program.md convention) — nice-to-have entry point; not a hard blocker.
Related: ENH-1122 (frozen-boundary markers) — guardrail that becomes useful once this loop exists.

## Session Log
- `/ll:capture-issue` - 2026-04-16T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2fb1a4ee-5512-43ed-b858-2a21a4738fb8.jsonl`

---

## Status

Open
