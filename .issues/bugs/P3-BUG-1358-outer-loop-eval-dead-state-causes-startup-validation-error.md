---
id: BUG-1358
type: BUG
priority: P3
decision_needed: false
confidence_score: 99
status: done
completed_at: 2026-05-03T00:00:00Z
---

# BUG-1358: outer-loop-eval dead state causes startup context-variable validation error

## Summary

`ll-loop run outer-loop-eval <sub-loop-name>` failed at startup with:

```
[WARNING] states.run_benchmark_opt_in: State is not reachable from initial state
Missing required context variable: 'scorer'. Run with: ll-loop run outer-loop-eval --context scorer=VALUE
Missing required context variable: 'tasks_dir'. Run with: ll-loop run outer-loop-eval --context tasks_dir=VALUE
```

The loop was completely unusable without passing dummy values for `scorer` and `tasks_dir` — context variables that were never needed by any reachable state.

## Root Cause

`outer-loop-eval.yaml` imported `lib/benchmark.yaml` via:

```yaml
import:
  - lib/benchmark.yaml
```

This materialized a `run_benchmark_opt_in` fragment state into the loop definition:

```yaml
run_benchmark_opt_in:
  fragment: run_benchmark
  action: "${context.scorer} ${context.tasks_dir}"
  capture: benchmark_score
  on_yes: done
  on_no: done
  on_error: done
```

The state was never wired to any reachable state (hence the WARNING), but `ll-loop`'s startup validator scanned all states — including unreachable ones — and required `scorer` and `tasks_dir` to be present in the context block. Since they were absent, the loop refused to start.

## Additional Issues Found

During the fix, five more problems were identified and corrected:

1. **`ll-loop show` embedded in a prompt action** — `analyze_definition` asked Claude to run the shell command inline, which is unreliable and produces uncapturable output. Replaced with a dedicated `load_definition` shell state that captures the output for downstream use.

2. **Empty `input` passed as positional arg** — `run_sub_loop` ran `ll-loop run "${context.loop_name}" ""` when `input` was blank, potentially confusing the sub-loop runner. Added a guard: only pass `$INPUT` when non-empty.

3. **No `on_error` on prompt states** — `analyze_definition`, `analyze_execution`, `generate_report`, and `refine_analysis` all lacked `on_error` routes. Added graceful fallback routes to the next logical state or `done`.

4. **No timeout on `run_sub_loop`** — sub-loops can run for hours; without a state-level timeout the only safety net was the outer loop's global budget (3600s), which is insufficient for loops like `eval-specfile-gold` (12h budget). Added `timeout: 1800` with a note in the description to pass `--timeout` for longer sub-loops.

5. **Global timeout too low** — 3600s (1h) leaves no headroom for a 30-min sub-loop run plus analysis states. Increased to 7200s (2h).

## Fix

Rewrote `scripts/little_loops/loops/outer-loop-eval.yaml`:

- Removed `import: lib/benchmark.yaml` and the dead `run_benchmark_opt_in` state entirely
- Added `load_definition` shell state (`ll-loop show` → captured output)
- Updated `analyze_definition` to read `${captured.loop_definition.output}` instead of issuing inline shell commands
- Added empty-input guard in `run_sub_loop`
- Added `timeout: 1800` to `run_sub_loop`
- Added `on_error` to all prompt states
- Increased global `timeout` from 3600 → 7200
- Increased `max_iterations` from 10 → 15 (the `refine_analysis → generate_report` cycle needs room; 15 allows ~7 cycles)

## Verification

Loop now starts without any `--context` flags:

```
ll-loop run outer-loop-eval eval-specfile-gold -v
```
