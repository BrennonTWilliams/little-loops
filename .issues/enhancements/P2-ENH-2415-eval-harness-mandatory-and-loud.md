---
id: ENH-2415
title: "Make rn-build eval harness mandatory and loud (no silent skip to done)"
type: ENH
priority: P2
status: open
parent: EPIC-2412
captured_at: '2026-06-30T00:00:00Z'
discovered_date: 2026-06-30
discovered_by: capture-issue
size: Medium
relates_to:
- EPIC-2412
- FEAT-2413
- FEAT-2414
labels:
- loops
- verification
- greenfield
- rn-build
- eval-harness
---

# ENH-2415: Make rn-build eval harness mandatory and loud (no silent skip to done)

## Summary

`rn-build`'s only real code-execution gate — the eval harness — is optional,
LLM-installed, and **silently degrades to "no verification / done"** on every
absence or error path. Change the routing so a missing or crashed harness routes to a
non-success terminal (`build_failed`), never silently to `done`. The strongest
verification the pipeline has should not be the easiest thing to skip.

## Current Behavior

`eval_harness` is an LLM prompt that installs one of the harness templates. On its
failure or absence:

- `check_harness_name` routes `on_no`/`on_error` → `synthesize_result` (bypasses eval).
- `eval_gate` runs `loop: "${captured.harness_name.output}"`; empty name previously
  crashed (BUG-2013) and now routes `on_error` → `synthesize_result`.
- `resume` without `resume_harness` warns "Eval gate will be SKIPPED" but still
  proceeds to `synthesize_result`.
- `synthesize_result` terminates `done` for all four outcomes.

Net: build results can be reported `done` with zero verification.

## Expected Behavior

- If no harness can be resolved (given `resume_harness` → scan prior
  `.loops/runs/rn-build-*/harness-name.txt` → scan `.loops/*.yaml`), the run
  terminates at a `build_failed` (`success: false`) terminal with a loud reason and a
  `resume_command`, not `done`.
- A harness that crashes routes to `build_failed`, not `synthesize_result`-then-`done`.
- `synthesize_result` reserves `done` for runs where the eval gate (or the FEAT-2414
  acceptance phase) actually passed.
- A deliberate, explicit `--context skip_eval=true` is the ONLY way to bypass, and it
  still terminates non-`done` with `eval_skipped: true` in the JSON.

## Proposed Solution

1. Add a `build_failed` terminal (`success: false`) if not already reachable from all
   verification-bypass paths.
2. Repoint `check_harness_name` `on_no`/`on_error` and `eval_gate` `on_error` to a new
   `harness_missing` state that writes a crash/skip marker and routes to `build_failed`.
3. Gate the only silent-pass path behind an explicit `skip_eval` context flag.
4. Keep the existing loud resume warning but make it terminal-affecting.

## Acceptance Criteria

- A run with no installable harness terminates `build_failed`, surfaced as failed
  (not green), with a resume command.
- `ll-loop run rn-build` on a spec whose harness install fails does not report `done`.
- Existing resume tests (ENH-2016) updated to assert the new terminal.

## Scope Boundaries

- Complementary to FEAT-2414: once the acceptance phase exists, it becomes the primary
  gate and the harness a secondary one; this issue ensures neither can be silently null.

## Impact

- **Priority**: P2 - The pipeline's strongest verification is currently the easiest to
  skip; runs can report `done` with zero verification, which is a correctness hazard.
- **Effort**: Medium - Adds a `build_failed` terminal and repoints existing
  `on_no`/`on_error` routes in `rn-build.yaml`; reuses existing terminals and evaluators.
- **Risk**: Medium - Changes which runs report `done`; existing resume tests (ENH-2016)
  must be updated to assert the new terminal.
- **Breaking Change**: No - Behavior tightens; an explicit `--context skip_eval=true`
  preserves the bypass path (still non-`done`).

## Status

**Open** | Created: 2026-06-30 | Priority: P2
