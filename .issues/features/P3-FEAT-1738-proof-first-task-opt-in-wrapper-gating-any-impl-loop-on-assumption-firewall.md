---
id: FEAT-1738
type: FEAT
priority: P3
status: open
captured_at: '2026-05-27T18:08:06Z'
discovered_date: '2026-05-27'
discovered_by: capture-issue
parent: EPIC-1694
relates_to:
- EPIC-1694
- FEAT-1696
- FEAT-1695
---

# FEAT-1738: `proof-first-task` — opt-in wrapper that gates any impl loop on assumption-firewall

## Summary

Add `scripts/little_loops/loops/proof-first-task.yaml` — an FSM loop that runs `assumption-firewall` (FEAT-1696) as a pre-phase before delegating to any caller-specified implementation loop. Users who want proof-first behavior run `proof-first-task` instead of `general-task` or `autodev`; the core built-in loops stay unpolluted for projects that don't use the Learning Test Registry.

## Current Behavior

`general-task`, `autodev`, `scan-and-implement`, and other mainstream coding loops have no awareness of the Learning Test Registry. A developer who runs any of these against a task that touches an unfamiliar third-party API will write code based on training-data assumptions rather than proven API behavior, with no automatic prompt to run `/ll:explore-api` first.

`assumption-firewall` and `ready-to-implement-gate` (FEAT-1695, FEAT-1696) exist as opt-in gates, but they are independent loops — a developer must know to run them before their implementation loop. There is no single entry point that combines "prove first, then implement."

## Expected Behavior

```bash
# Prove API assumptions, then implement the task
ll-loop run proof-first-task \
  --context task="Add Stripe webhook signature verification" \
  --context issue_file=".issues/features/P2-FEAT-1234-stripe-webhooks.md" \
  --context impl_loop="general-task"
```

The loop:

1. `gate` (sub-loop) — runs `assumption-firewall` with `input: "${context.issue_file}"`. On `done` (all proven or no external deps) → proceeds to `run_impl`. On `blocked` (refuted) → routes to `blocked` terminal.
2. `run_impl` (sub-loop) — runs the loop named in `context.impl_loop` with `input: "${context.task}"`. On success → `done`. On failure → `impl_failed`.
3. Terminal states: `done`, `blocked` (gate failed), `impl_failed` (impl loop failed after gate passed), `no_issue_file` (issue_file not provided — gate is skipped, loop runs impl directly).

When `issue_file` is empty, the loop skips the gate and routes directly to `run_impl`, so it degrades gracefully to a plain impl-loop runner.

## Motivation

- **Closes the mainstream-loop blindspot without polluting core loops.** The gap identified in the LT registry gap analysis: "The biggest gap is the absence of a pre-implementation gate in `autodev`/`general-task`/`scan-and-implement`." This loop closes that gap as an opt-in alternative entry point rather than a modification to the core loops.
- **Single entry point for proof-first development.** Instead of remembering to run `assumption-firewall` before `general-task`, a developer uses one loop that chains both. The pattern is opt-in by loop choice, not by config flag.
- **Degrades gracefully.** When no `issue_file` is provided, `proof-first-task` acts as a plain wrapper around the specified impl loop — no friction for users who don't need the gate.

## Use Case

A developer wants to implement a Stripe webhook feature. They run:

```bash
ll-loop run proof-first-task \
  --context task="Implement Stripe webhook signature verification" \
  --context issue_file=".issues/features/P2-FEAT-1234-stripe-webhooks.md" \
  --context impl_loop="general-task"
```

The loop extracts API assumptions from the issue file, proves each via the LT registry, then — if all pass — runs `general-task` with the task description. If a surface is refuted, the loop stops with a structured diagnosis before any implementation code is written.

## Proposed Solution

```
check_issue_file (shell)
  → test -n "${context.issue_file}" && test -f "${context.issue_file}"
  evaluate: exit_code
  on_yes: gate
  on_no:  run_impl   # no issue file → skip gate

gate (sub-loop)
  loop: assumption-firewall
  with:
    input: "${context.issue_file}"
  on_success: run_impl        # done or no_external_deps
  on_failure: blocked         # refuted
  on_error:   blocked

run_impl (sub-loop)
  loop: "${context.impl_loop}"
  with:
    input: "${context.task}"
  on_success: done
  on_failure: impl_failed
  on_error:   impl_failed

done (terminal)
blocked (terminal)
impl_failed (terminal)
```

**Context variables:**

| Variable | Default | Description |
|---|---|---|
| `task` | `""` | Natural-language task description passed to the impl loop; required |
| `issue_file` | `""` | Path to issue file for assumption extraction; optional (gate skipped if empty/missing) |
| `impl_loop` | `"general-task"` | Name of the impl loop to run after the gate passes |

## Implementation Steps

1. Draft `scripts/little_loops/loops/proof-first-task.yaml` with the four-state design above.
2. Wire `check_issue_file` as a shell state using `test -n` + `test -f` with `exit_code` evaluator.
3. Wire `gate` as a sub-loop call to `assumption-firewall` — confirm terminal state names (`done`, `blocked`, `no_external_deps`) route correctly via `on_success`.
4. Wire `run_impl` as a dynamic sub-loop call using `loop: "${context.impl_loop}"`.
5. Run `ll-loop validate proof-first-task` and iterate until no ERRORs.
6. Update `scripts/tests/test_builtin_loops.py` — add `"proof-first-task"` to `expected` set and a `TestProofFirstTaskLoop` structural test class.
7. Update numeric loop counts in `README.md` and `CONTRIBUTING.md` (tracked by `ll-verify-docs`).
8. Add a row to `docs/guides/LOOPS_GUIDE.md` built-in loops table under an "API Adoption" or "Proof-First" section.

## Acceptance Criteria

- `scripts/little_loops/loops/proof-first-task.yaml` exists and `ll-loop validate proof-first-task` reports no ERRORs.
- `scripts/tests/test_builtin_loops.py::test_expected_loops_exist` passes with `"proof-first-task"` in `expected`.
- When `issue_file` is provided and gate passes: impl loop runs.
- When `issue_file` is provided and gate blocks: loop terminates at `blocked` without running the impl loop.
- When `issue_file` is empty or missing: gate is skipped, impl loop runs directly.
- `context.impl_loop` defaults to `"general-task"` and is overridable per-run.

## Labels

`feat`, `loop`, `learning-tests`, `fsm`, `gate-consumer`, `proof-first`, `opt-in`

---

**Open** | Created: 2026-05-27 | Priority: P3

## Session Log
- `/ll:capture-issue` - 2026-05-27T18:08:06Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/55979bca-15d7-443c-b4d3-a76d29148106.jsonl`
