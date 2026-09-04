---
id: FEAT-3386
type: FEAT
title: "fleet-loop-improve built-in meta-loop \u2014 automate the fleet loop-review\
  \ runbook (harvest \u2192 diagnose \u2192 propose \u2192 apply \u2192 measure-externally)"
priority: P3
status: done
discovered_by: ll-issues-create
discovered_date: '2026-09-04'
captured_at: '2026-09-04T20:21:49Z'
completed_at: '2026-09-04T20:22:38Z'
parent: EPIC-1918
relates_to:
- FEAT-2379
labels:
- ll-loop
- ll-logs
- meta-loop
- loops
- tooling
---

# FEAT-3386: fleet-loop-improve built-in meta-loop — automate the fleet loop-review runbook (harvest → diagnose → propose → apply → measure-externally)

## Summary

FEAT-2379 shipped `ll-logs fleet-review` and `docs/runbooks/FLEET_LOOP_REVIEW.md` as an
on-demand, hand-driven cycle and explicitly deferred (Future extension, Scope decisions) a
built-in `fleet-loop-improve.yaml` meta-loop following `diagnose → propose → apply →
measure-externally`. This issue records that meta-loop, built 2026-09-04: it runs the
runbook's HARVEST → ATTRIBUTE → DIAGNOSE+FIX cycle end-to-end and closes the RE-MEASURE arrow
one invocation late via a durable ledger.

## Current Behavior

The fleet loop-review cycle is manual: an operator runs `ll-logs fleet-review`, reads the
report, `cd`s into each project to run `ll-loop diagnose-evaluators`, invokes the
`loop-specialist` agent by hand, applies and verifies a fix, and re-runs the harvest later to
read the delta table. Nothing records which fix is awaiting which re-measure.

## Expected Behavior

`ll-loop run fleet-loop-improve` (from the little-loops source checkout only) performs one
full cycle per invocation — harvest, measure earlier fixes, select the worst flagged built-in
loop, diagnose it inside the projects that ran it, have `loop-specialist` write a diagnosis
artifact and apply the smallest fix, gate the fix deterministically, commit, and record the fix
as `pending` in a ledger the next run measures.

## Motivation

The built-in loops (~106) are only proven by other projects' run history, which this repo
cannot self-grade. FEAT-2379 made that evidence harvestable but left every later step manual,
so the cycle ran only when someone remembered to run it, and no record tied a landed fix to
the fleet delta that was supposed to prove it. Automating the cycle as a meta-loop that obeys
the repo's own meta-loop rules (diagnosis-first, non-LLM evaluators, external measurement)
makes "use other projects' logs to continuously fix built-in loops" a repeatable command.

## Proposed Solution

A built-in `fleet-loop-improve` loop whose states are thin calls into a new
`little_loops.fleet_improve` module: `preflight → harvest → measure_externally →
select_target → diagnose → propose (loop-specialist, artifact only) → check_proposal →
route_fix/route_dismiss → apply (loop-specialist) → gate → commit → select_target …`, with
`revert` / `dismiss` / `needs_human` side exits, `diagnose_failure → failed`, and `done`.
See Decisions for the design points and `docs/guides/LOOPS_REFERENCE.md#fleet-loop-improve`
for the knob table.

## Integration Map

### Files Modified

- `scripts/little_loops/loops/fleet-loop-improve.yaml` — new built-in meta-loop.
- `scripts/little_loops/fleet_improve.py` — new helper module.
- `scripts/little_loops/cli/logs.py` — `is_flagged()` extracted; `_flag_loops` delegates.
- `scripts/tests/test_fleet_improve.py` — new (ledger, select, measure, check-proposal,
  diagnose, gate, record).
- `scripts/tests/test_ll_logs.py` — `TestIsFlaggedParity`.
- `scripts/tests/test_builtin_loops.py` — expected-loop set entry; `TestFleetLoopImproveLoop`.
- `docs/guides/LOOPS_REFERENCE.md` — catalog row, TOC entry, `## fleet-loop-improve` section.
- `scripts/little_loops/loops/README.md`, `docs/reference/CLI.md` — catalog row / pointer.
- `docs/runbooks/FLEET_LOOP_REVIEW.md` — Cadence, RE-MEASURE, and Baseline contract updated.
- `README.md` + `scripts/README.md` mirror — loop count 105 → 106.
- `.issues/features/P3-FEAT-2379-fleet-loop-review-runbook.md` — Future extension note.

## Implementation Steps

1. Extract `is_flagged()` in `cli/logs.py`; write `fleet_improve.py` (ledger, select,
   diagnose, measure, check-proposal, gate, record) with unit tests.
2. Author `fleet-loop-improve.yaml`; add the expected-loop set entry, `TestFleetLoopImproveLoop`,
   catalog rows, runbook/CLI/reference docs, README count bump + mirror.
3. Verify: `ll-loop validate` (zero warnings), the deterministic states run live against the
   fleet (`preflight`/`harvest` bodies verbatim, then `measure → select → diagnose → record →
   measure → select`), full unit suite, ruff/mypy, `ll-verify-private-refs`.

## Impact

- **Priority**: P3 - maintenance hygiene; the manual runbook still works without it
- **Effort**: Medium - new module (~600 lines), loop YAML, ~60 tests, docs across six files
- **Risk**: Low - additive; the only touched existing code path is `_flag_loops`, now a
  one-line delegate to `is_flagged` with parametrized parity tests. The loop itself refuses to
  run outside the source checkout and commits nothing that fails validate + the loop test gates
- **Breaking Change**: No

## Decisions

1. **One cycle per run + durable ledger, not same-run re-measure.** RE-MEASURE needs fresh
   fleet runs on the fix (FEAT-2379 AC lines 531–533 punted it for this reason). Each run's
   `measure_externally` state compares the new sidecar's `runs`/`converged` against each
   `pending` entry's recorded baseline; once `min_new_runs` (3) fresh runs exist it records
   `improved` / `regressed` / `unchanged`. Ledger: `.loops/diagnostics/fleet-loop-improve-ledger.jsonl`
   (MR-3-exempt, beside the `fleet-review-<stamp>.json` sidecars). `${context.run_dir}` is
   per run *instance* (`cli/loop/run.py:190-198`), so it cannot hold cross-run state.
2. **Regressions are recorded and printed, never auto-reverted.** Reverting a shipped fix is
   the operator's call.
3. **All logic in `little_loops/fleet_improve.py`**, invoked as
   `python3 -m little_loops.fleet_improve {select,diagnose,measure,check-proposal,gate,record}`.
   States hand values through `${context.run_dir}/target.json`; no `${captured.*}` ever
   reaches a shell body (MR-11), no inline `json.load`/`except`/`exit(0)` (MR-10), and no
   this-repo path literal (`test_builtin_loop_hardcode_gate.py`) — `yaml_path`/`tests_dir` are
   derived at runtime from `get_builtin_loops_dir()`.
4. **No LLM self-grading.** Every evaluator is `exit_code` or `output_contains`; MR-1/4/8 are
   moot and no `meta_self_eval_ok` is declared. The specialist's verdict is a deterministic
   token (`VERDICT_FIX` / `VERDICT_NOT_A_LOOP_BUG` / `VERDICT_NEEDS_HUMAN`) parsed from a
   `Verdict:` line in the artifact by `check-proposal`, routed with `output_contains` on
   `${captured.verdict.output}` (which also satisfies MR-2's captured-baseline reference).
5. **Propose and apply are separate agent states.** `propose` writes the artifact only (the
   agent's own rule: never modify a loop without the artifact first); `apply` applies exactly
   the `## Proposed change`. Both forbid `ll-loop run` (child run deadlocks on the project lock
   this loop holds) and forbid other projects' absolute paths in the YAML (pre-commit
   `ll-verify-private-refs` would reject the commit).
6. **Gate = validate + built-in loop tests.** `ll-loop validate <yaml> --json` must be
   error-free with no more warnings than the pre-fix baseline, and
   `test_builtin_loops.py` + `test_builtin_loop_hardcode_gate.py` must pass — `validate` alone
   does not run the warning ratchet, the hardcode gate, or the expected-loop set.
7. **Shared flagging rule.** `is_flagged()` extracted in `cli/logs.py` (public twin of
   `_flag_loops`, attribution not checked because the sidecar's `loops` is builtin-only);
   parity is test-enforced.
8. **`diagnose-evaluators --min-runs 2`.** The default of 10 prints plain "Insufficient
   history" text before the `--json` branch; a fleet-flagged loop rarely has 10 runs in one
   project. Non-JSON output is recorded as evidence, not treated as failure.
9. **Harvest flags pinned** (`--all --existing-only --exclude-project .`, appendices off by
   default) so consecutive sidecars stay comparable; comparability = same `window_days` and
   `excluded_projects` (`since`/`until` are absolute and differ every run).
10. **`rejected` loops get the same TTL as `dismissed`/`needs-human`** so a gate-failed fix is
    not re-attempted in the same run.

## Use Case

A maintainer runs `ll-loop run fleet-loop-improve` from this checkout on Monday. It harvests
the fleet, finds no pending fixes to measure, flags `sprint-build-and-validate` (10 runs, 20%),
runs `diagnose-evaluators` inside the three projects that ran it, and the specialist writes
`.loops/diagnostics/sprint-build-and-validate-<stamp>.md` ending `Verdict: fix`. The fix is
applied, passes validate + the loop test gates, is committed, and the ledger gains a `pending`
line with the 10-run/20% baseline. Two weeks later the maintainer runs it again: the harvest
shows 15 runs / 6 converged, so `measure_externally` prints `20% -> 80% over 5 new run(s)` and
records `improved` — the external acceptance signal — before selecting the next flagged loop.

## Program Design

### Types

- Ledger entry (JSONL line): `{loop, status, recorded_at, commit, artifact, harvest_stamp,
  baseline{runs, converged, success_pct, top_outcome, window_days, excluded_projects},
  measured{harvest_stamp, new_runs, new_converged, post_success_pct, top_outcome}, reason}`;
  latest line per `loop` wins.
- `target.json` (per run): `{loop, projects, runs, converged, success_pct, top_outcome,
  outcomes, yaml_path, tests_dir, artifact, stamp, harvest_stamp, sidecar, baseline}`.

### Signatures

- `little_loops.cli.logs.is_flagged(runs, success_pct, top_outcome, *, threshold, min_runs) -> bool`
- `little_loops.fleet_improve.select_target(sidecar, sidecar_path, ledger_entries, *, threshold, min_runs, dismiss_ttl_days, now, builtin_paths, log) -> dict | None`
- `little_loops.fleet_improve.diagnose(target, run_dir, runner) -> Path`
- `little_loops.fleet_improve.measure_entry(entry, sidecar, *, stamp, min_new_runs, now) -> tuple[dict | None, str]`
- `little_loops.fleet_improve.check_proposal(artifact) -> str`
- `little_loops.fleet_improve.gate(target, run_dir, runner) -> tuple[bool, str]`
- `little_loops.fleet_improve.record(target, *, status, reason, now, head) -> dict`
- `little_loops.fleet_improve.main(argv) -> int` — exit 0 yes / 1 no / 2 error

### Call Path

`ll-loop run fleet-loop-improve` → `harvest` (`ll-logs fleet-review` → `_cmd_fleet_review`
→ `_write_baseline`) → `measure_externally` (`fleet_improve.cmd_measure` → `read_ledger` →
`measure` → `measure_entry` → `comparable` → `append_ledger`) → `select_target`
(`cmd_select` → `flagged_loops` → `is_flagged` → `skip_reason` → `select_target` →
`_builtin_loop_paths`) → `diagnose` (`cmd_diagnose` → `diagnose` → `_tool_report` →
`validate_loop` → `warning_count` → `git_head`) → `propose` (agent) → `check_proposal`
(`cmd_check_proposal` → `check_proposal`) → `apply` (agent) → `gate` (`cmd_gate` → `gate` →
`validate_loop`) → `commit` (`cmd_record` → `record` → `append_ledger` → `read_fixes_count`).

### Decision Rules

- Select: flagged by `is_flagged`; skip `pending`; skip `dismissed`/`needs-human`/`rejected`
  younger than `dismiss_ttl_days`; highest `runs` first; stop at `max_fixes_per_run`.
- Measure: comparable iff same `window_days` and `excluded_projects`; verdict only when
  `new_runs >= min_new_runs`; `post = round(new_conv / new_runs * 100)` vs `baseline.success_pct`.
- Gate: diff exists ∧ YAML parses ∧ validate error-free ∧ warnings ≤ baseline ∧ loop tests pass.

## Acceptance Criteria

- [x] `ll-loop validate scripts/little_loops/loops/fleet-loop-improve.yaml` passes with zero warnings.
- [x] The loop has no `check_semantic`/`llm_structured` state; `propose`/`apply` use `agent: loop-specialist`.
- [x] `python3 -m little_loops.fleet_improve select` against the real 2026-09-03 sidecar picks `sprint-build-and-validate` (10 runs, 20%); `measure` with an empty ledger prints "No pending fixes to measure."
- [x] After `record --status pending`, `measure` on the same sidecar reports "no verdict yet: 0 new run(s), need 3" and `select` skips the loop as "pending re-measure".
- [x] The `preflight` and `harvest` shell bodies run verbatim against the live fleet: preflight passes the editable-install check (its former dir-wide clean-tree refusal was narrowed to a per-target skip in `select_target` after it blocked the first live run on this repo's own in-progress loop edits); harvest writes `harvest.json` from the sidecar path.
- [x] Full unit suite green: 22174 passed, 12 skipped.
- [x] `ruff check`, `mypy`, `ll-verify-private-refs` clean on all new files.
- [ ] A live `ll-loop run fleet-loop-improve` end to end (preflight no longer needs a clean loops dir — only the selected target YAML must be clean; it commits an agent-authored fix — run with `auto_commit: "false"` first). Not run this session by design.

## Resolution

Implemented as designed in the approved plan. One real defect surfaced during live
verification and was fixed before landing: `Logger.success()` prints to **stdout**, so
`ll-logs fleet-review` emits `Wrote <path>` followed by the path; the `harvest` state now
takes `| tail -n 1`. No CHANGELOG entry (added at release prep). Nothing committed this
session.

## Related Key Documentation

- `docs/runbooks/FLEET_LOOP_REVIEW.md` — the manual cycle this loop automates
- `docs/guides/LOOPS_REFERENCE.md#fleet-loop-improve` — states, knobs, artifacts
- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` § The Design Rules (MR-1…MR-14)
- `agents/loop-specialist.md` — artifact contract consumed by `check-proposal`
- `.claude/CLAUDE.md` § Loop Authoring — meta-loop shape rules

## Status

**Done** | Created: 2026-09-04 | Completed: 2026-09-04 | Priority: P3

## Session Log

- Claude Code session - 2026-09-04T20:22:38Z - Planned in plan mode (two Explore agents: meta-loop rules MR-1..MR-14 and FEAT-2379/`fleet-review` internals; one Plan agent stress-test that surfaced the per-instance `run_dir`, MR-11-on-context-knobs, pre-commit-hook, and `diagnose-evaluators --min-runs 10` traps). Implemented module, loop, tests, and docs; ran the deterministic states live against the fleet (found and fixed the stdout `Wrote …` line in `harvest`); full unit suite 22174 passed, 12 skipped. Live `ll-loop run` deferred until the work is committed.
