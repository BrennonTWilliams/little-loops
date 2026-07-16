---
id: ENH-2568
title: autodev spike triage routing + spike-gate wrapper loop
type: ENH
priority: P3
status: cancelled
labels: [fsm, loops, autodev, confidence, risk-reduction, captured]
captured_at: "2026-07-10T01:34:59Z"
discovered_date: "2026-07-10"
discovered_by: capture-issue
parent: EPIC-2570
---

# ENH-2568: autodev spike triage routing + spike-gate wrapper loop

## Summary

Integrate `/ll:spike` (FEAT-2567) into the automated development system, consuming the `spike_needed` frontmatter flag set by `/ll:confidence-check` (ENH-2569): (1) `autodev.yaml`'s `triage_outcome_failure` gains a spike branch (`check_spike_needed` → `run_spike` → `rerun_confidence_after_spike`) mirroring the existing decide/wire remediation patterns; (2) a new `spike-gate.yaml` wrapper loop shaped like `proof-first-task.yaml` lets any implementation loop (`rn-*`, `general-task`, `ll-sprint` paths) opt into a spike gate without growing spike states of its own.

## Current Behavior

`triage_outcome_failure` (`scripts/little_loops/loops/autodev.yaml:615-629`) maps an outcome-confidence failure to exactly three remedies:

- `decision_needed` / `score_ambiguity <= 10` → `run_decide`
- `missing_artifacts` → `run_wire` → `run_refine` → `rerun_confidence_after_wire`
- otherwise → `detect_children` / `run_size_review` (decompose)

An issue whose outcome confidence is low because a mechanism has **zero precedent and no test coverage of the risky core** (ENH-2565: 66/100) fits none of these: there is no unresolved Option A/B, nothing pre-existing is absent, and the risk is concentrated rather than broad — decomposition just smears it across children. Under today's autodev such an issue thrashes through size-review and lands in `autodev-skipped.txt`. The correct remedy (prove the core in isolation) exists only as a manual step.

The external-API analogue is already fully automated (`assumption-firewall.yaml` + `proof-first-task.yaml` + Learning-Test Registry gate in `ll-auto`); the internal-mechanism case has no equivalent.

## Expected Behavior

1. In autodev, `triage_outcome_failure` routes a `spike_needed: true` issue (flag set by ENH-2569) to `run_spike` (`/ll:spike <ID> --auto`), then `rerun_confidence_after_spike` re-scores, then the normal `enqueue_or_skip` / recheck path evaluates fresh scores. A completed-or-attempted spike never runs twice (`spike_attempted` guard).
2. `ll-loop run spike-gate --context issue_file=<path> impl_loop=<loop>` gates any impl loop on `/ll:spike --check`, mirroring `proof-first-task`'s shape.

## Motivation

ENH-2565 is the first measured instance: a 4h `rn-refine` wall-clock timeout plus a 66/100 outcome score traced to an unproven concurrency core. The remediation lattice already converts every *other* low-outcome diagnosis into an automated repair; this closes the last unhandled failure mode.

## Proposed Solution

### 1. autodev.yaml triage routing

- `triage_outcome_failure` on_no path: insert `check_spike_needed` between `run_decide` routing and `check_missing_artifacts`. Ordering rationale: an unresolved design decision must be settled before spiking an approach (decide first), and a spike is cheaper to skip than wiring is to misdiagnose — spike check sits after decide, before missing_artifacts.
- `check_spike_needed`: `ll-issues check-flag <ID> spike_needed` AND NOT `spike_attempted` → `run_spike`; else fall through to `check_missing_artifacts`.
- `run_spike`: `fragment: with_rate_limit_handling`, `action: "/ll:spike ${captured.input.output} --auto"`, `action_type: slash_command`, `next: rerun_confidence_after_spike`, `on_error: rerun_confidence_after_spike`, `on_rate_limit_exhausted: done`.
- `rerun_confidence_after_spike`: re-run `/ll:confidence-check` so downstream gates see fresh scores — copy of `rerun_confidence_after_decide` / `rerun_confidence_after_wire` (BUG-1491 precedent), `next: enqueue_or_skip`.
- Budget guards: the spike runs inside autodev's existing per-issue flow; `spike_attempted` (set by the skill even on failure) guarantees at most one spike per issue per backlog lifetime. Consider a dedicated `timeout` on `run_spike` given the rn-refine 4h-cap history.
- Defense-in-depth parity: evaluate whether `check_decision_before_size_review`-style pre-size-review spike check is warranted, or explicitly document why not (keep the lattice auditable).

### 2. spike-gate.yaml wrapper loop

New `scripts/little_loops/loops/spike-gate.yaml`, `category: gate`, shaped on `proof-first-task.yaml`:

- context: `task`, `issue_file`, `impl_loop` (default `general-task`)
- `check_issue_file` → `check_spike_flag` (`ll-issues check-flag ... spike_needed` minus `spike_completed`) → `gate` (`/ll:spike <ID> --check`; on fail, `run_spike_auto` once, re-check) → `run_impl` (delegate to `${context.impl_loop}`) → `done | blocked | impl_failed` terminals
- No issue_file → skip gate, run impl directly (proof-first-task parity)

### 3. rn-* / sprint adoption

No rn-* loop edits in this issue. Adoption = documentation: `sprint-refine-and-implement` / `auto-refine-and-implement` callers can substitute `impl_loop: spike-gate` with `with: impl_loop=<real loop>` composition. Direct state additions to rn-remediate etc. are a future issue if the base rate justifies it.

## Scope Boundaries

- Blocked by FEAT-2567 (the skill, with stable `--auto`/`--check` contracts) AND ENH-2569 (the `spike_needed` flag this routing reads).
- **Sequencing guard**: after ENH-2569 lands, let the flag run across a few backlog passes and record the `spike_needed` fire rate here before starting this routing work. One datum (ENH-2565) justifies the flag; routing complexity should be justified by recurrence.
- The `spike_needed` detection itself is ENH-2569 — no `skills/confidence-check/SKILL.md` changes in this issue.
- No changes to `/ll:explore-api`, Learning-Test Registry, or `proof-first-task.yaml` itself.
- No spike-state additions inside rn-* loop YAMLs.
- Promotion of spike code remains manual (per FEAT-2567).

## API/Interface

- Consumes frontmatter flag `spike_needed` (set by ENH-2569's confidence-check phase; superseded by `spike_completed`).
- New autodev states: `check_spike_needed`, `run_spike`, `rerun_confidence_after_spike` (state-name assertions in `test_builtin_loops.py` must be extended).
- New builtin loop: `spike-gate` (`ll-loop validate spike-gate`, `ll-loop list` visibility).

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/autodev.yaml` — `triage_outcome_failure` routing + 3 new states.
- `scripts/tests/test_builtin_loops.py` — autodev state-name/routing assertions; new spike-gate loop coverage.
- `commands/help.md`, loops `README.md`, docs — register spike-gate; document the extended remediation lattice.

### Files to Create
- `scripts/little_loops/loops/spike-gate.yaml`

### Dependent Files
- `scripts/little_loops/loops/auto-refine-and-implement.yaml`, `sprint-refine-and-implement.yaml` — inherit the new triage behavior via the autodev sub-loop; verify context passthrough (`skip_learning_gate` precedent) needs no spike analogue.
- `ll-issues check-flag` — confirm it handles the new flag generically (it should; flags are schema-free).

### Similar Patterns
- `check_missing_artifacts` → `run_wire` → `rerun_confidence_after_wire` (autodev.yaml:365-401, 631-639) — the exact routing shape to copy.
- `proof-first-task.yaml` — the gate-loop shape.

### Tests
- `test_builtin_loops.py`: triage routes spike_needed→run_spike, spike_attempted suppression, rerun-confidence wiring, spike-gate loop happy/blocked paths.
- Regression: existing triage paths (decide/wire/size-review) unchanged.

### Documentation
- Loops README remediation-lattice section; CHANGELOG.

### Configuration
- Optional `commands.spike_gate.enabled` kill-switch if a config gate is desired; default on.

## Implementation Steps

1. Pre-work: confirm ENH-2569's flag has landed and record its backlog fire rate here.
2. Part 1: autodev states + routing + tests (`ll-loop validate autodev`).
3. Part 2: spike-gate.yaml + tests + docs.
4. Full regression: `python -m pytest scripts/tests/test_builtin_loops.py -v` and existing autodev triage tests.

## Impact

- **Priority**: P3 — high leverage but gated on FEAT-2567 dogfooding and base-rate evidence.
- **Effort**: Medium — 3 FSM states, one small gate loop, tests.
- **Risk**: Medium — touches autodev's triage lattice; mitigated by copying the wire/decide routing shape verbatim and by the spike_attempted one-shot guard.
- **Breaking Change**: No — additive states; existing paths unchanged.

## Blocked By

- **FEAT-2567**: `/ll:spike` skill (provides `--auto`/`--check` contracts and `spike_attempted`/`spike_completed` flags this routing depends on)
- **ENH-2569**: confidence-check phase that sets the `spike_needed` flag this routing reads

## Related Issues

- **FEAT-2567** — the skill this integrates.
- **ENH-2569** — the `spike_needed` flag detection (measurement-first prerequisite).
- **ENH-2565** — motivating instance (rn-refine synth_pop concurrency spike).
- **BUG-1491** — rerun-confidence-after-remediation precedent.
- **ENH-1415 / BUG-1277 / BUG-2513** — prior triage-lattice extensions this mirrors.

## Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis (2026-07-15):_

**This issue's entire proposed scope has already been implemented via its two decomposed children — both `done`. ENH-2568 is effectively superseded and should be closed (`done` or `cancelled: superseded-by-children`), not implemented.**

Decomposition (both `parent: EPIC-2570`, both `status: done`):

- **ENH-2640** — autodev triage spike-branch routing. Commits `e92ed3af` (route unproven-mechanism outcome failures to spike remediation) + `33e6d515` (route decide-path skip through spike gate). Delivered exactly the Proposed Solution §1 states.
- **ENH-2641** — `spike-gate.yaml` wrapper loop. Commit `175f0c00`. Delivered Proposed Solution §2.

Verification of each proposed artifact against current code:

- `scripts/little_loops/loops/autodev.yaml` — the three proposed states **already exist**: `check_spike_needed` (line 683, predicate `spike_needed AND NOT spike_attempted` via `ll-issues show --json`), `run_spike` (line 704, `action: "/ll:spike ${captured.input.output} --auto"`, `next: rerun_confidence_after_spike`), `rerun_confidence_after_spike` (line 720, byte-for-byte mirror of `rerun_confidence_after_wire`). `triage_outcome_failure.on_no → check_spike_needed` is wired (line 680).
- Defense-in-depth parity (Proposed §1 last bullet) was **also delivered**: `check_spike_needed_before_skip` (line 810) interposes a decide-path-specific spike gate on the no-children skip edge (ENH-2640 fix `33e6d515`).
- `scripts/little_loops/loops/spike-gate.yaml` — **exists** (91 lines, `category: gate`); chains `check_issue_file → check_spike_needed → check_spike_completed → gate (/ll:spike --check) → run_spike_auto → recheck → run_impl` (delegates to `${context.impl_loop}`), mirroring `proof-first-task.yaml`.
- Tests — `TestSpikeGateLoop` (13 tests) + autodev spike-state assertions land in `scripts/tests/test_builtin_loops.py`; also covered in `test_autodev_decision_gate.py`, `test_confidence_check_skill.py`, `test_spike_skill.py`, `test_show.py`.
- Docs — spike-gate registered in `scripts/little_loops/loops/README.md`, `docs/guides/LOOPS_REFERENCE.md`, `docs/guides/LOOPS_GUIDE.md`; back-referenced from `skills/spike/SKILL.md`. The `spike_needed`/`spike_attempted`/`spike_completed` flags are set by `skills/confidence-check/SKILL.md` (ENH-2569, landed).

> ⚠ Stale anchors — the line numbers cited in this issue's Current Behavior / Similar Patterns predate the ENH-2640 insertion and no longer resolve:
> - `triage_outcome_failure` — cited `autodev.yaml:615-629`, now **665–681**.
> - `run_wire`/`run_refine`/`rerun_confidence_after_wire` — cited `365-401`, now **406–442**.
> - `check_missing_artifacts` — cited `631-639`, now **733–741**.

**Recommended next step**: `/ll:ready-issue ENH-2568` will likely close this as already-satisfied; alternatively set `status: done` (or `cancelled`) with a note pointing to ENH-2640 + ENH-2641. No implementation work remains.

## Status

**Cancelled: superseded-by-children** | Created: 2026-07-10 | Priority: P3

Superseded by **ENH-2640** (autodev triage spike-branch routing) and **ENH-2641** (spike-gate.yaml wrapper loop), both `done`. Codebase research (`/ll:refine-issue`, 2026-07-15) confirmed every proposed artifact — states, loop file, tests, docs — already exists in the delivered children. No implementation work remains; `/ll:wire-issue` was not run since there is nothing left to wire.

## Session Log
- `/ll:wire-issue` - 2026-07-16 - cancelled as superseded, skipped wiring pass
- `/ll:refine-issue` - 2026-07-16T00:37:18 - `ecf443b9-e4d3-4815-8f02-627ac9461b6d.jsonl`

- `/ll:capture-issue` - 2026-07-10T01:34:59Z - `manual capture via Claude Cowork session`
