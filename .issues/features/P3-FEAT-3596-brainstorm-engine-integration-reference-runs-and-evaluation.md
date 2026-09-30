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
- FEAT-3667
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

The old loop is replaced in place by FEAT-3582, so its baseline is preserved outside the tree: `postmortems/brainstorm-baseline/` (gitignored, local-only) holds verbatim copies of the four historical `.loops/runs/brainstorm-*` dirs plus `BASELINE.md` (per-run ideas, LLM calls, tokens, wall-clock, pairwise difflib). **Do this before FEAT-3667/FEAT-3582 merge.** Pin the pre-rewrite commit SHA here (tree HEAD at snapshot: `2fe16824a`, verified to exist 2026-09-29). Because every little-loops project is `local-editable` against this checkout, `ll-loop run brainstorm` from an old-SHA worktree still resolves the **new** loop once FEAT-3582 is on `main`, which would silently spoil the baseline. So run the old loop from an extracted copy: `git show 2fe16824a:scripts/little_loops/loops/brainstorm.yaml > <scratch>/brainstorm-baseline.yaml` (rename `name:` to `brainstorm-baseline`; copy `loops/lib/common.yaml` alongside if `import:` does not resolve). The old loop is pure YAML plus stdlib `python3`, so it has no package dependency on the new module.

**The 2 fixed briefs (pinned 2026-09-29)** — verbatim, reused for old and new:
1. _(artifact-shaped)_ "Suggest names and one-line taglines for an open-source CLI that watches a repository's issue backlog and drafts implementation plans."
2. _(functional-shaped, grounded in this repo)_ "Design how little-loops should let a user pause a running FSM loop, edit its context, and resume it without losing state." The historical runs do not record their briefs, and two used different models (`claude-sonnet-4-6` vs `MiniMax-M3`), so token totals are not comparable without the cache columns. "Duplicates retained" and "occupied cells" must use one identical tagging pass over both loops' ideas, not the new loop's own dedup.

### Old-loop baseline results (recorded 2026-09-29, before FEAT-3667/3582)

Ran the old loop on both pinned briefs from an extracted copy (SHA `2fe16824a`, model `claude-sonnet-5-5`); full table and run dirs are in `postmortems/brainstorm-baseline/BASELINE.md` (§ Fresh old-loop baseline) and `fresh-20260929/`.

| brief | ideas kept | LLM calls | output tok | total context tok (incl. cache) | wall-clock | max / median difflib |
|---|---|---|---|---|---|---|
| 1 artifact | 42 / 45 | 14 | 23,502 | ≈ 879k | 336 s | 0.56 / 0.31 |
| 2 functional | 45 / 45 | 14 | 26,829 | ≈ 889k | 354 s | 0.54 / 0.07 |

Consequences for this issue: (a) the old loop's call count is **14** (13 excluding the `finalize_done` summary), not ≈ 12 — compare new vs old on the same definition; (b) difflib dedup fired once on the short-text brief (3 dropped) — the "never fires" claim is true for prose ideas but not for short names, so report both briefs separately; (c) still to do here: the common tagging pass for "duplicates retained" and "occupied cells" over `fresh-20260929/*/ideas.jsonl`.

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
  features on, L lenses, `classify_mode`, `ground_codebase`, `render_report`, materialize's 4 fixed states, the tournament sub-loop, and the
  fixed premortem cost of 3 parent steps / 2 LLM calls; profile gates cost 0 steps). FEAT-3582's rough worst case is ≈ 55 steps against 60 with no slack on the salvage path, so expect `max_steps` ≈ 75 and update `test_max_steps_is_60` deliberately. _(2026-09-30: each optional child now bumps `max_steps` for its own cost in the change that lands it; this issue verifies and pins the combined total, and owns the final value, rather than being the first to raise it.)_ **Timeout** is derived, not guessed: `parent timeout ≥ PRE_TOURNAMENT_WORST_S + TOURNAMENT_TIMEOUT_S (1800) + JUDGE_CALL_TIMEOUT_S (300) + TAIL_S (600)`, where `PRE_TOURNAMENT_WORST_S` = per-call latency measured in the baseline/reference runs (44–97 s in the 2026-06 runs) × the pre-tournament call count with everything on (9 diverge + classify + frame + reframe + dedup + shortlist + materialize author/canary; `ground_web` is deferred), plus screenshot time. Keep the engine constants (`PARENT_TIMEOUT_S` etc.) and a test asserting they equal `brainstorm.yaml`.
- **Blind A/B (added 2026-09-29, third review)**: the mechanism-driven metrics below (cells, duplicates, call count) can all pass while idea quality gets worse, so a person compares — blind, order randomized — the old loop's top idea against the new winner on both pinned briefs. Pass = the new winner wins or ties on **both** briefs; record the verdicts in the Session Log or `postmortems/`. No LLM-judged usefulness metric replaces this. _2026-09-30 (fourth review): the core A/B is now a **FEAT-3582 merge gate** (a regression would already be on `main` by the time this issue starts), so the baseline and the shared tagging pass are prerequisites of FEAT-3582, not of this issue. Here the A/B is re-run for the four-mode and all-features configurations, rendering old/new ideas in the same neutral title + body format so it stays blind; note that n = 2 briefs with a single rater who designed the loop has little statistical power — record the verdicts as evidence, not proof._
- **Merge-gate evidence for FEAT-3582**: the old-vs-new **core** comparison and the worktree real runs (`PYTHONPATH=<worktree>/scripts`) run *before* FEAT-3582 merges to `main` (every project is `local-editable`); the four-mode and all-features runs stay here. FEAT-3596's baseline (`postmortems/brainstorm-baseline/`) is the input.
- **Comparison vs old loop** on 2 fixed briefs: duplicates retained, occupied grid
  cells, LLM call count, total input/output tokens, wall-clock runtime, and the
  tournament `tie_rate` (judge position sensitivity on the top-3 head-to-heads; FEAT-3582 — measure it here before revisiting the round-robin format). No LLM-judged "usefulness"
  metric.
- **Cost ceiling**: a default run (`mode: auto`, classifier included) makes ≤ 30 LLM calls (old loop
  14 measured 2026-09-29; estimate for the new core ≈ 1 classify + 1 frame + (1 reframe when enabled) + 9 diverge + 1 dedup + 1
  shortlist + ≈ 8 judge (≤ 7 batched round calls + 1 probe call) ≈ 21–22, leaving real slack; `max_finalists` must still not rise above 8). A run exceeding it fails the comparison and needs
  a documented reason. Total input/output tokens and cache columns are **recorded, not gated** (per-session overhead was ≈ 94k tokens per call in the 06-27 run, so call count alone is the wrong cost unit); also record `tie_rate`, `abstention_rate`, and the per-brief wall-clock so the batched-judging trade-off (possible in-round anchoring, FEAT-3582 Review Decision 28) can be evaluated.

## Program Design

### Types

- `FailureFixture`: `{name: str, stub_outputs: dict[str, str], expected_terminal: "done" | "failed", sinks_fired: bool}` — stubbed per-state LLM output keyed by state name
- `ComparisonRow`: `{brief: str, loop: "old" | "new", duplicates_retained: int, occupied_cells: int, input_tokens: int, output_tokens: int, runtime_s: float}`

### Signatures

- `run_failure_fixture(fixture: FailureFixture, tmp_path: Path) -> str` — drives the loop with stubbed outputs, returns the terminal state
- `worst_case_steps(lenses: int, finalists: int) -> int` — step arithmetic backing the pinned `max_steps` (premortem is a fixed +3, materialize a fixed ≈ 5, gates +0)

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
  recorded against the old loop on 2 briefs; default-run LLM calls ≤ 30 (aligned with EPIC-3581 and § Expected Behavior; it previously said 45).
- Issue stays open until FEAT-3584, FEAT-3585, and FEAT-3586 are done and their
  reference runs recorded.

## Status

**Open** | Created: 2026-09-25 | Priority: P3
