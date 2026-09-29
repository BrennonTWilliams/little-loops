---
id: FEAT-3596
type: FEAT
title: Brainstorm engine integration, reference runs, and evaluation
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-25'
captured_at: '2026-09-25T17:05:42Z'
parent: EPIC-3581
labels:
- loops
- brainstorm
blocked_by:
- FEAT-3582
- FEAT-3583
relates_to:
- FEAT-2248
- FEAT-3584
- FEAT-3585
- FEAT-3586
---

# FEAT-3596: Brainstorm engine integration, reference runs, and evaluation

## Summary

Own the end-to-end integration and evaluation of the rewritten brainstorm engine
(EPIC-3581): the four per-mode reference runs, mixed-profile override runs,
failure-path fixtures, sink compatibility, the combined step/time budget with every
feature enabled, and a lightweight before/after comparison against the old loop.

## Dependency Note

_2026-09-28:_ Hard-blocked only by FEAT-3582 and FEAT-3583. FEAT-3584/3585/3586 are `relates_to` so a P4 child (FEAT-3586) does not gate this P3 issue. Each optional child owns its own failure-path fixtures; this issue owns the **cross-child** interactions, the combined budget, and reference runs. Per-mode reference runs for `ground`, `materialize`, and `premortem` are recorded as each child lands, and this issue cannot be closed until all three are done.

## Baseline (captured 2026-09-29)

The old loop is replaced in place by FEAT-3582, so its baseline is preserved outside the tree: `postmortems/brainstorm-baseline/` (gitignored, local-only) holds verbatim copies of the four historical `.loops/runs/brainstorm-*` dirs plus `BASELINE.md` (per-run ideas, LLM calls, tokens, wall-clock, pairwise difflib). Before FEAT-3582 lands, pin the pre-rewrite commit SHA here (tree HEAD at snapshot: `2fe16824a`) and run the old loop on the 2 fixed briefs from a worktree at that SHA. The historical runs do not record their briefs, and two used different models (`claude-sonnet-4-6` vs `MiniMax-M3`), so token totals are not comparable without the cache columns. "Duplicates retained" and "occupied cells" must use one identical tagging pass over both loops' ideas, not the new loop's own dedup.

## Current Behavior

Each EPIC-3581 child owns only its own slice. Nobody owns the epic's success metrics
(one reference run per mode, `mode: auto` selecting the expected profile), the
combined `max_steps`/`timeout` budget once `ground`, `materialize`, and `premortem`
all add steps on top of the FEAT-3582 core, or evidence that the rewrite beats the
old loop.

## Expected Behavior

- **Reference runs**: one documented run per mode (`artifact`, `visual`,
  `functional`, `business`) via `mode: auto`, each producing its expected output
  shape (visual: ≥ 3 rendered finalists + ranked gallery). Run records live under
  `postmortems/` or the issue's Session Log, not committed run dirs.
- **Mixed-profile overrides**: at least one run with `mode=<x>` plus a knob override
  (e.g. `mode=business materialize=render`) proving the knob wins over the profile
  default (FEAT-3583 precedence rule).
- **Failure-path fixtures** (pytest, stubbed via `MockActionRunner` from
  `scripts/tests/test_fsm_executor.py`, keyed by state name): only **cross-child**
  interactions live here — e.g. ground and materialize both filtering the same run
  below the finalist floor (caught by `check_floors --stage pre_tournament` before any judge
  call), reserve promotion in `finalists.json` followed by materialize drops, and premortem
  fail-open leaving `winners.md` and sink input byte-identical. Single-child fixtures (zero survivors, too few
  cells, per-probe failures, round bound) belong to their owning child. No sink
  fires before `validate_portfolio` passes.
- **Sink compatibility**: `sink_file`, `sink_issue`, `sink_decision` consume the
  new `winners.md` (still `text`/`rationale` keys) unchanged, with or without the
  annotate-only premortem.
- **Combined budget**: pin `max_steps` and `timeout` for the worst case (all
  features on, F framings × L lenses, round-robin pairs + probe, materialize, and the
  fixed premortem cost of 4 parent steps / 2 LLM calls) and update `test_max_steps_is_60` deliberately.
- **Comparison vs old loop** on 2 fixed briefs: duplicates retained, occupied grid
  cells, LLM call count, total input/output tokens, wall-clock runtime, and the
  tournament `tie_rate` (judge position sensitivity on the top-3 head-to-heads; FEAT-3582 — measure it here before revisiting the round-robin format). No LLM-judged "usefulness"
  metric.
- **Cost ceiling**: a default (`mode=artifact`) run makes ≤ 45 LLM calls (old loop
  ≈ 12; estimate for the new core ≈ 1 frame + 1 reframe + 9 diverge + 1 dedup + 1
  shortlist + ≤ 31 judge (28 round-robin pairs + ≤ 3 probes) ≈ 44 — one call under the ceiling, so `max_finalists` must not rise above 8). A run exceeding it fails the comparison and needs
  a documented reason.

## Program Design

### Types

- `FailureFixture`: `{name: str, stub_outputs: dict[str, str], expected_terminal: "done" | "failed", sinks_fired: bool}` — stubbed per-state LLM output keyed by state name
- `ComparisonRow`: `{brief: str, loop: "old" | "new", duplicates_retained: int, occupied_cells: int, input_tokens: int, output_tokens: int, runtime_s: float}`

### Signatures

- `run_failure_fixture(fixture: FailureFixture, tmp_path: Path) -> str` — drives the loop with stubbed outputs, returns the terminal state
- `worst_case_steps(framings: int, lenses: int, finalists: int) -> int` — step arithmetic backing the pinned `max_steps` (premortem is a fixed +4, no rounds)

### Call Path

`init` -> `diverge` -> `route_sink` -> `verify_artifacts` -> `finalize_done` (exercised end-to-end; the new states between them come from FEAT-3582..3586)

## Integration Map

### Files to Modify
- `scripts/tests/test_brainstorm.py` — cross-child failure-path fixtures, combined budget assertion
- `scripts/little_loops/loops/brainstorm.yaml` — `max_steps` / `timeout` final values

### Tests
- `scripts/tests/test_brainstorm.py` — `test_max_steps_is_60` replaced by the pinned worst-case value

## Impact

- **Priority**: P3 - closes the epic; no user-visible feature of its own
- **Effort**: Medium - mostly runs, fixtures, and budget arithmetic
- **Risk**: Low - test and documentation work
- **Breaking Change**: No

## Use Case

**Who**: A little-loops maintainer closing EPIC-3581.

**Context**: Five children each land a piece of the engine; their interactions
(budget, filtering order, sink contract) are only exercised together.

**Goal**: Prove the combined engine meets the epic's success metrics and is not a
regression in cost or duplicate retention.

**Outcome**: Reference-run records for all four modes, passing failure-path
fixtures, a pinned combined budget, and a before/after comparison table.

## Acceptance Criteria

- One reference run per mode recorded; `mode: auto` picks the expected profile for
  each.
- A mixed-profile override run shows the explicit knob overriding the profile
  default.
- Failure-path fixtures pass in `python -m pytest scripts/tests/`; none requires
  Playwright or a live LLM.
- No sink executes on a run that fails `validate_portfolio`.
- `max_steps`/`timeout` pinned for the all-features worst case; `ll-loop validate
  brainstorm` passes.
- Comparison table (duplicates, cells, LLM calls, tokens, runtime, `tie_rate`)
  recorded against the old loop on 2 briefs; default-run LLM calls ≤ 45.
- Issue stays open until FEAT-3584, FEAT-3585, and FEAT-3586 are done and their
  reference runs recorded.

## Status

**Open** | Created: 2026-09-25 | Priority: P3
