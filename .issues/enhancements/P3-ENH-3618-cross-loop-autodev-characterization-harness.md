---
id: ENH-3618
type: ENH
title: Cross-loop autodev characterization harness
priority: P3
status: done
discovered_by: ll-issues-create
discovered_date: '2026-09-27'
captured_at: '2026-09-27T00:15:46Z'
parent: EPIC-3565
blocks:
- ENH-3606
- ENH-3621
completed_at: '2026-09-27T00:48:41Z'
---

# ENH-3618: Cross-loop autodev characterization harness

## Summary

Build a shared test harness that drives the real `autodev.yaml` into the real
`prepare-issue.yaml` end to end (stub inner `refine-to-ready-issue`, scripted slash commands),
and commit characterization tests of today's behavior for every ENH-3606 terminal-table
scenario plus a mid-ladder resume.

Extracted from ENH-3606 (Tests, first bullet "Cross-loop harness"; Implementation Step 2) so
it can land first and serve two consumers: ENH-3606's before/after comparison, and the
preparation-policy spike, which re-runs the same scenarios against a replacement
`prepare-issue.yaml`.

## Current Behavior

No harness runs from the wrapper into autodev. Existing tests either drive a small hand-built
FSM with a scripted action runner (`scripts/tests/test_autodev_decision_gate.py`) or run one
state's bash in isolation (`scripts/tests/test_prepare_issue.py::_run_state`,
`scripts/tests/test_autodev_ladder_run_records.py`). Nothing pins today's end-to-end ledger
rows, queue, staging, record token and `summary.json` per scenario, and nothing pins resume
behavior mid-ladder.

## Expected Behavior

`python -m pytest scripts/tests/test_autodev_characterization.py` runs one scenario per
ENH-3606 terminal-table row against the current `autodev.yaml` and asserts the exact
artifacts each produces today. Scenarios are data, so the same table can run against a
different `prepare-issue.yaml` and a transformed `autodev.yaml`.

## Proposed Solution

- **Helper** `scripts/tests/autodev_harness.py`:
  - project: conftest `make_project` (`scripts/tests/conftest.py` ~:668) + `.issues/` tree +
    `.ll/ll-config.json` (thresholds, no test/lint cmds) + `git init` + initial commit;
    `monkeypatch.chdir(project)` and `working_dir=project`.
  - context seeding: `input`, `run_dir` (mkdir), thresholds via `little_loops.fsm.context_seed`
    helpers, `quality_gate=false` by default.
  - `loops_dir=tmp` holding only a **stub `refine-to-ready-issue.yaml`**, scenario-driven via
    run_dir files: which `--writer refine-to-ready-issue` record / legacy class to write,
    `refine-broke-down`, child issues to create with `parent:`, `done` / `failed` terminal.
    The real `prepare-issue` and `lib/common.yaml` resolve from builtins.
  - `ScriptedRunner`: `is_slash_command` → per-scenario canned `ActionResult` keyed by command
    substring, plus an optional side-effect callback (confidence-check writes or omits scores;
    go-no-go stamps `outcome_gate_waived`; size-review prints the guard-2 line / creates child
    files). Shell → delegate to `little_loops.fsm.runners.DefaultActionRunner`. Never return a
    non-zero rate-limit-classified result (per-state wait ladders would sleep).
  - PATH shim fake `ll-auto` (writes `ll_auto_last.txt`, sets status `done`).
  - assertions: exact `autodev-skipped.txt` rows, `autodev-queue.txt`, `autodev-staged.txt`,
    `prepare-issue` record token, `summary.json`, visited-state path (from `state_enter`
    events).
- **`scripts/tests/test_autodev_characterization.py`**, `@pytest.mark.slow`, per-test
  `@pytest.mark.timeout(300)`. One scenario per terminal-table row: ready → implement,
  `design_gate_failed`, `oversized_atomic` NO-GO, `oversized_atomic` GO → reopen → implement,
  `readiness_stagnated`, `low_readiness`, decision re-entry exhausted, size-review
  decomposition (children enqueued), resolved parent, scores absent, `on_error` drop.
- **Resume characterization**: persist mid-ladder, resume via
  `little_loops.fsm.persistence.PersistentExecutor`, and record the resumed path and the
  repair-cycle counter value (documents today's behavior; ENH-3606's "Resume and handoff"
  section depends on it).
- **Requirements from the preparation-policy spike** (build them in now):
  - scenarios parametrizable by a replacement `prepare-issue.yaml` and an autodev-YAML
    transform (e.g. ENH-3606's boundary-edge retargets plus a `prep-pass-$CURRENT` write in
    `dequeue_next`);
  - `ScriptedRunner` crash injection at step N, then resume via `PersistentExecutor`;
  - stubs reproduce side effects faithfully: scores written/omitted, `reconcile_attempted`,
    superseded markers cleared, child files with `parent:`, go/no-go stamp.
- If a scenario cannot be driven hermetically, record it as `xfail(strict=True)` with the
  reason rather than dropping it.

## Integration Map

### Files to Modify
- New `scripts/tests/autodev_harness.py`
- New `scripts/tests/test_autodev_characterization.py`

### Dependent Files (Callers/Importers)
- `little_loops.fsm.executor` (`loops_dir` resolution), `little_loops.fsm.persistence`
  (`PersistentExecutor` ~:984, `resume` ~:1388), `little_loops.fsm.runners`
  (`DefaultActionRunner` ~:109), `little_loops.fsm.context_seed`

### Similar Patterns
- `scripts/tests/test_autodev_decision_gate.py` (scripted `ActionRunner`)
- `scripts/tests/test_auto_refine_closure_accounting.py` (`_make_project` real mini project)

### Tests
- This issue is the tests

### Documentation
- N/A (test-only)

### Configuration
- `slow` marker; per-test timeout

## Impact

- **Priority**: P3 — prerequisite for ENH-3606 and the preparation-policy spike
- **Effort**: Medium
- **Risk**: Low — test-only
- **Breaking Change**: No

## Scope Boundaries

- **In scope**: the helper module, the characterization suite, the resume characterization,
  the parametrization and crash-injection hooks.
- **Out of scope**: any change to `autodev.yaml`, `prepare-issue.yaml` or
  `refine-to-ready-issue.yaml`; fixing behavior the characterization exposes (capture those as
  their own issues).

## Acceptance Criteria

- [ ] One characterization scenario per ENH-3606 terminal-table row, green against current `autodev.yaml`, each asserting skipped rows (order), queue, staged, record token, `summary.json` and visited states
- [ ] A resume characterization persists mid-ladder, resumes via `PersistentExecutor`, and pins the resumed path and counter value
- [ ] Scenarios are a data table runnable against a replacement `prepare-issue.yaml` and an autodev-YAML transform
- [ ] `ScriptedRunner` supports crash injection at step N
- [ ] Stub side effects cover scores written/omitted, `reconcile_attempted`, superseded markers, child files with `parent:`, and the go/no-go stamp
- [ ] No scenario sleeps on a rate-limit ladder; any scenario that cannot be driven hermetically is `xfail(strict=True)` with a reason
- [ ] The slow file's runtime is recorded (target < 2 min under xdist)

## Status

**Open** | Created: 2026-09-27 | Priority: P3

## Resolution

Landed in `8a79afb16`: `scripts/tests/autodev_harness.py` + `scripts/tests/test_autodev_characterization.py`
(19 terminal scenarios, 3 resume cases, 1 parametrization smoke test; ~50 s). `run_autodev()` takes
`prepare_issue_yaml=` and `autodev_transform=`, supports crash injection + `PersistentExecutor.resume()`.
Limitations: slash responses queue per skill name (`run_wire` and `remediate_oversized_atomic` share
`wire-issue`); injected faults fire on first visit only; stub refine count is always 0; quality gate off.
Bug-like current behaviors are pinned and marked `BUG-LIKE` in the table (see BUG-3622, ENH-3606,
ENH-3600 notes).
