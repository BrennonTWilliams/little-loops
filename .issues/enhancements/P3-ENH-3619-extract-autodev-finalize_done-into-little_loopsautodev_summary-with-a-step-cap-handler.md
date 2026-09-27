---
id: ENH-3619
type: ENH
title: Extract autodev finalize_done into little_loops.autodev_summary with a step-cap
  handler
priority: P3
status: done
discovered_by: ll-issues-create
discovered_date: '2026-09-27'
captured_at: '2026-09-27T00:15:46Z'
parent: EPIC-3565
blocks:
- ENH-3600
completed_at: '2026-09-27T00:48:42Z'
---

# ENH-3619: Extract autodev finalize_done into little_loops.autodev_summary with a step-cap handler

## Summary

Move autodev's inline `finalize_done` shell action into a tested Python module,
`little_loops.autodev_summary`, with a behavior-identical thin shell state calling it. Add an
`on_max_steps: finalize_step_capped` handler so the step-cap exit also writes `summary.json`.

This is ENH-3600's former Sequencing step 1 ("behavior-identical extraction"), split out so it
can land before ENH-3606, plus closing the `max_steps` summary gap that ENH-3600 previously
listed as a known limitation. ENH-3600 keeps the record-driven accounting (`record_absent`,
`autodev-prepared.txt`) and marker cleanup, and builds on this module.

## Current Behavior

- `finalize_done` (`scripts/little_loops/loops/autodev.yaml` ~:2949) is ~300 lines of inline
  shell. It promotes `autodev-staged.txt` IDs to `autodev-passed.txt` / `autodev-unverified.txt`,
  counts the skip/stop ledgers, picks the verdict (success → partial → phantom → not_started →
  no-op; `rate_limit` stop reason overrides to `rate_limited`), prints a stdout report, and
  printf's a 16-key `summary.json`. `phantom` exits 1 (`on_no: failed`); errors route
  `on_error: failed`.
- Behavioral coverage runs the action under `bash -c` (`_run_finalize_done`,
  `scripts/tests/test_builtin_loops.py` ~7122–7751;
  `scripts/tests/test_feat3573_quality_gate.py::TestFinalizeDonePromotion`). Once the logic
  moves, those harnesses stop exercising it.
- Issue status is read by parsing `ll-issues show --json`, whose status field is display-cased
  (`Completed` = done).
- `autodev.yaml` declares `max_steps: 500` (~:18) and no `on_max_steps` handler. The executor
  supports one (`little_loops.fsm.executor`, step-limit check ~:664–709), but without it a
  capped run calls `_finish("max_steps")` without passing `finalize_done`: no `summary.json`.

## Expected Behavior

- `finalize_done` is a one-line call:
  `python3 -m little_loops.autodev_summary --run-dir ${context.run_dir} --quality-gate ${context.quality_gate:shell:default=true}`,
  keeping `fragment: shell_exit` and today's `on_yes` / `on_no` / `on_error` routing.
- `summary.json`, the stdout report, the staged → passed/unverified promotion side effects and
  the exit code per verdict are identical to today's shell action on the same inputs.
- A run that hits `max_steps` runs `finalize_step_capped` once, which calls the module with
  `--stop-reason max_steps`, writes `summary.json` with verdict `max_steps` and prints the
  "Stopped early" report line.

## Proposed Solution

TDD order:

1. **Golden fixtures from the current shell action, before any YAML edit.** Script under
   `scripts/tests/fixtures/autodev_summary/<scenario>/` capturing inputs (run_dir ledger
   files, `quality/*.json`, issue-status map, `quality_gate` value), `expected_summary.json`,
   `expected_stdout.txt`, `expected_exit`. Scenarios = every existing `finalize_done` test
   (`test_builtin_loops.py` ~7122–7751 incl. `_run_finalize_done` users: promotion, phantom,
   no-op, rate-limit/pending, mixed, not-started, proof-gate-infra, cancelled split, abandoned
   in-flight) plus `test_feat3573_quality_gate.py::TestFinalizeDonePromotion` (gate on and
   off). Run the shell action with the quality gate substituted explicitly (note the ~7751
   test's bad-substitution quirk).
2. **`scripts/little_loops/autodev_summary.py`**, modeled on `little_loops.fleet_improve`
   (`EXIT_*` constants, `build_parser()`, `main(argv) -> int`, `__main__` guard):
   - `EXIT_OK = 0`, `EXIT_PHANTOM = 1`, `EXIT_ERROR = 2`;
   - `AutodevSummary` dataclass with `to_dict()` preserving today's 16-key order;
   - `promote_staged()` — the passed/unverified append side effects, same guards;
   - `build_summary()`, `render_report()` (line-identical), `write_summary()` via
     `little_loops.file_utils` atomic write;
   - issue status read in-process from frontmatter (lower-cased; `done|completed` /
     `cancelled`), not by parsing `ll-issues show` display case;
   - args: `--run-dir`, `--quality-gate`, `--stop-reason` (overrides `autodev-stop-reason`).
3. **Thin `finalize_done`** as in Expected Behavior.
4. **Step cap**: `on_max_steps: finalize_step_capped` — one state whose single action runs the
   module with `--stop-reason max_steps`. Only one state executes past the cap, so it cannot
   chain through `finalize_rate_limited`. `stop_reason=max_steps` overrides the verdict to
   `max_steps` (mirrors `rate_limit → rate_limited`); the report prints "Stopped early".
   Grep consumers of the `rate_limited` verdict (e.g. `auto-refine-and-implement`,
   `ll-loop audit`, `skills/audit-loop-run`) and treat `max_steps` the same.
5. **Tests** (see Acceptance Criteria).
6. **Docs**: `docs/guides/LOOPS_REFERENCE.md` autodev summary + step-cap behavior;
   `docs/reference/API.md` module entry. `ll-loop validate autodev` passes.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/autodev.yaml` — `finalize_done` (~:2949), new
  `finalize_step_capped`, top-level `on_max_steps`
- New `scripts/little_loops/autodev_summary.py`

### Dependent Files (Callers/Importers)
- `scripts/little_loops/loops/auto-refine-and-implement.yaml` (reads/overwrites the shared
  `summary.json`), `little_loops.cli.loop.audit`, `skills/audit-loop-run/SKILL.md` — verdict
  consumers; check `max_steps` handling

### Similar Patterns
- `little_loops.fleet_improve` (`EXIT_*` ~:75–77, `build_parser`, `main`) and
  `scripts/tests/test_fleet_improve.py` (module tests via `main(argv)`)
- Thin-shell gate: `test_shell_states_call_helper_module_not_inline_logic`
  (~`test_builtin_loops.py:21019`)

### Tests
- New `scripts/tests/test_autodev_summary.py`
- Rewrite `test_builtin_loops.py` `TestAutodevLoop` finalize_done tests (~7122–7751) and
  `test_feat3573_quality_gate.py::TestFinalizeDonePromotion` to the module
- `scripts/tests/test_fsm_topology.py` autodev state count (+1)
- `scripts/tests/data/loop_interpolation_baseline.json` `finalize_done` entry stays valid

### Documentation
- `docs/guides/LOOPS_REFERENCE.md`, `docs/reference/API.md`

### Configuration
- N/A

## Impact

- **Priority**: P3 — unblocks ENH-3600 and closes the last `summary.json`-less autodev exit (EPIC-3565 AC "every autodev exit writes summary.json")
- **Effort**: Medium — mechanical port pinned by golden fixtures
- **Risk**: Low-Medium — autodev is live in every local-editable project; fixture parity bounds it
- **Breaking Change**: No — additive `max_steps` verdict on a path that wrote no summary before

## Scope Boundaries

- **In scope**: the module, golden fixtures, thin `finalize_done`, `finalize_step_capped`,
  the `max_steps` verdict, test migration, docs.
- **Out of scope** (ENH-3600): run-record reads, `record_absent`, `autodev-prepared.txt`,
  `record_ledger_mismatch`, marker removal, removing the `refine-terminal-class` fallback.
- No change to `summary.json` keys or values for any existing verdict; `max_steps` is a new
  verdict value only on the step-cap path.

## Acceptance Criteria

- [ ] Golden fixtures are captured from the pre-change shell action and committed before the YAML edit; the module reproduces every fixture's `summary.json`, stdout and exit code exactly
- [ ] `summary.json` keeps today's 16 keys in today's order for every existing verdict
- [ ] Exit codes: `phantom` → 1, error/unreadable input → 2, every other verdict → 0 (unit test per verdict)
- [ ] The MR-13 `abandoned` key is asserted by the module's unit tests (the printf no longer lives in YAML)
- [ ] `finalize_done` is a thin call to `python3 -m little_loops.autodev_summary`; a structural gate asserts the invocation **and** the absence of inline summary logic
- [ ] Literal-substring pins on the action (`autodev-staged.txt`, `autodev-proof-gate-infra.txt`, `autodev-inflight`) are converted to module-level asserts
- [ ] Issue status is read in-process from frontmatter, lower-cased
- [ ] `autodev.yaml` declares `on_max_steps: finalize_step_capped`; an executor test with a forced low `max_steps` runs that state and writes `summary.json` with `stop_reason: max_steps` and verdict `max_steps`
- [ ] Consumers that special-case `rate_limited` treat `max_steps` the same
- [ ] `ll-loop validate autodev` passes; topology count updated with a delta comment

## Status

**Open** | Created: 2026-09-27 | Priority: P3

## Resolution

Landed in `21eaca8ed` (38 golden fixtures from the legacy shell action), `74657c660` (module, thin
`finalize_done`, `on_max_steps: finalize_step_capped`, test conversions) and `25343f700` (docs).
Intentional non-fixture deltas: literal (not regex) ID matching, byte-order sorting, JSON-escaped string
values, exit 2 on unwritable run_dir/ledgers (was silent 0), new `max_steps` verdict. No consumer branches on
the `rate_limited` verdict, so none needed changes.
