---
id: ENH-3692
type: ENH
title: 'code-run-gate: fail only on test failures new relative to the base SHA (baseline-aware
  gate)'
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-10-02'
captured_at: '2026-10-02T17:24:32Z'
relates_to:
- BUG-3689
---

# ENH-3692: code-run-gate: fail only on test failures new relative to the base SHA (baseline-aware gate)

## Summary

Make the `code-run-gate` oracle (`scripts/little_loops/loops/oracles/code-run-gate.yaml`, states `run_test` / `aggregate`) fail an issue only on test failures that are **new relative to the base SHA**. Split out of BUG-3689 (item 3) after pre-implementation review: BUG-3689 now covers only the cheap env/hermeticity fixes; this is the baseline-comparison design, which carries the loop-shape, timeout and masking risk.

**Go/no-go first.** Before implementing, decide whether to build this at all. The honest fix for red-on-`main` is keeping `main` green (the two motivating corpus failures are already tracked), and the existing `--context quality_gate=false` escape hatch is cheap. The mechanism may not even rescue the motivating case: `test_prose_dep_sweep_gate.py::test_no_prose_dependency_drift_in_repo` and `test_verify_evidence.py::TestRepoGate::test_no_new_unverifiable_evidence` read `.issues/`, which autodev itself mutates — BUG-3688's `<ID>.base-dirty` listed ~20 uncommitted `.issues` files that a clean base-SHA worktree lacks, so the base side is unfaithful and the message-compare guard below would fail closed. If red-on-`main` episodes are rare, close this as won't-do.

## Current Behavior

`aggregate` treats the `test` stage as binary: any `exit_code=[1-9]` in `test-results.txt` (or `pass_rate < min_pass_rate`) yields `GATE_FAILED`. One pre-existing failure on `main` therefore fails every issue gated against it, and per the autodev summary a `quality_failed` issue is not re-gated on rerun, so it needs manual `--context quality_gate=false`.

## Expected Behavior

A gate run whose failing test ids all also fail on the base SHA (same failure message) yields a passing verdict with the tolerated ids listed; any new failing id yields `GATE_FAILED`. Anything the baseline cannot establish faithfully falls back to today's binary behavior — it never turns a red run green by accident.

## Motivation

See BUG-3689 (13 false failures on BUG-3688, 2 of them pre-existing red on base). Items 1–2 of BUG-3689 remove the 11 env-driven failures; this issue removes the remainder class.

## Proposed Solution

- **Id extraction**: parse `^FAILED ` / `^ERROR ` lines from the already-captured `test-results.txt` (pytest's default short summary), or reuse `prepatch_check._parse_junit` (returns `{nodeid: (category, error_kind)}`). **Do not use `pytest-json-report`** — it is not a declared dependency, nothing emits `--json-report`, and the existing `[ -f pytest.json ]` branch in `run_test` never fires for this repo.
- **Lazy baseline**: run only when the current run is red. Create a detached worktree at `<ID>.base` (autodev writes `QDIR/<ID>.base` before `implement_current`; `history_reader.runs.read_base_sha` is an advisory alternative) and re-run **only the failing node ids** there, not the full suite. Reuse `prepatch_check`'s worktree setup, `_run_pytest` and `_parse_junit`. Prepend the worktree `src_dir` to `PYTHONPATH` (editable installs otherwise shadow it; `run_test` already does this in a linked worktree) and apply the same xdist worker cap as `verify_epic_branch_before_merge`.
- **Symmetric subset re-run**: run the same id subset on HEAD under the identical invocation. An id that does not reproduce on HEAD (order-dependent / flaky) counts as NEW — fail-closed, labeled.
- **Masking guard**: compare node id **and** normalized failure message. The default short summary carries no message, so use junit for the message. Node-id-only comparison would hide a new finding in a repo-wide corpus test.
- **Fail closed (fall back to binary FAIL)** when: rc != 1; parsed ids do not reconcile with pytest's final `N failed, M errors` count; the id count exceeds a cap; `test_cmd` is not recognizably pytest (reuse its interpreter token); base worktree setup or base run hits an infra error; or `<ID>.base-dirty` shows divergence the base worktree cannot reproduce. An id that passes **or is missing / collection-errors** on base is NEW.
- **Where the code lives**: a unit-tested Python module (extract + compare + worktree orchestration with a Python-enforced subprocess timeout), invoked via `$LL_PYTHON` (not bare `python3`, which may be a different interpreter than `test_cmd`'s — pyenv vs miniforge locally, pipx/uv in consumers). Do not embed it in YAML heredocs: new `python3 -c` bodies interpolating `context.*` add unbaselined sites to `loop_interpolation_baseline.json`. Share the env-scrub list with `worktree_utils` as one constant.
- **Fold into existing states** — no new state (`CODE_RUN_GATE_STATES` is frozen by `test_code_run_gate_state_set_unchanged`; `max_steps: 10` is nearly exhausted). Raise `run_test` timeout (~900s) and loop `timeout:` (~2400s; today 1800 vs a 1770s state-timeout sum). Write a per-ID `test-baseline` sidecar that `aggregate` reads; never rewrite `exit_code=` in `test-results.txt`. The base worktree lives outside `tamper_guard` scope and is cleaned in a `finally` (file-creation churn has caused macOS launchservicesd beachballs).
- **Backward compatibility**: new **optional** oracle parameter carrying the base SHA/file. Absent = unchanged binary behavior (`rn-remediate`, `rn-refine`, direct `ll-loop run oracles/code-run-gate` have no base). Keep the `GATE_PASS` token. `aggregate` bypasses both the `exit_code` and `pass_rate` checks **only** for a tolerated `test` stage (reconcile with `min_pass_rate: 1.0` in `autodev.run_quality_gate`). Name sidecars per ID (`rn-remediate` shares one un-ID'd `run_dir`).
- **Surfacing**: `autodev.yaml` `run_quality_gate` `with:` passes the base; `record_quality_evidence` gets a `pass_preexisting` test-stage value plus tolerated ids (today it derives `"test": "fail"` from the last `exit_code=`); `autodev_summary.format_report` lists tolerated ids and shows the `quality_gate=false` hint only when the baseline was ineligible (regenerate `scripts/tests/fixtures/autodev_summary` goldens via `_generate.py`). Tolerated red must never be silent.

## Program Design

### Types

- `BaselineVerdict` — dataclass: `tolerated: dict[str, str]` (nodeid -> normalized message, red on base with the same message), `new: dict[str, str]` (everything else), `eligible: bool` (False -> fall back to binary behavior)

### Signatures

- `extract_failing_ids(test_output: str) -> dict[str, str]` — nodeid -> failure message from pytest's `FAILED`/`ERROR` summary lines
- `compare_to_base(current: dict[str, str], base: dict[str, str]) -> BaselineVerdict` — tolerate only ids red on base with the same normalized message
- `run_baseline(base_sha: str, failing_ids: list[str], timeout_s: int) -> BaselineVerdict` — detached worktree at `base_sha`, subset re-run on base and HEAD, cleanup in `finally`; infra failure returns `eligible=False`

### Call Path

`autodev` `run_quality_gate` (passes the base SHA) -> `code-run-gate` `run_test` (red run -> `run_baseline` via `$LL_PYTHON -m`) -> per-ID `test-baseline` sidecar -> `aggregate` (tolerated-only -> `GATE_PASS`; otherwise `GATE_FAILED`) -> `record_quality_evidence` (`pass_preexisting`)

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/oracles/code-run-gate.yaml` — optional base parameter; `run_test` (baseline orchestration call) and `aggregate` (tolerated-stage verdict)
- `scripts/little_loops/loops/autodev.yaml` — `run_quality_gate` `with:`; `record_quality_evidence`; `context:` header comment (~lines 56-62)
- `scripts/little_loops/autodev_summary.py` — `format_report` strings and hint
- new module under `scripts/little_loops/` — extract / compare / base-run orchestration

### Dependent / Related
- `scripts/little_loops/prepatch_check.py` — `_run_pytest`, `_parse_junit` reuse
- `scripts/little_loops/worktree_utils.py` — worker-cap and env-scrub precedent
- `scripts/little_loops/loops/rn-remediate.yaml`, `rn-refine.yaml`, `rn-implement.yaml`, `auto-refine-and-implement.yaml` — callers / token consumers; no-baseline fallback must stay identical

### Tests
- `scripts/tests/test_feat3573_quality_gate.py` — `TestOracleAggregate` (must pass with no baseline present; add: all-failing-on-base -> `GATE_PASS`, one new id -> `GATE_FAILED`, message mismatch, unreproduced-on-HEAD, count mismatch, rc != 1, infra fail-closed, worktree cleanup, `tamper_guard` non-trip); `TestOracleFormatStage.test_state_timeout_and_budget` (state-timeout sum must stay `< ORACLE["timeout"]`); `TestRecordQualityEvidence`
- `scripts/tests/test_builtin_loops.py` — `TestPrePatchCheckReachability` (state set / `guarded == {"run_test": "fail"}`), `TestCodeRunGateOracle` literals, `MR11_MARKER_ALLOWLIST`, `TestInterpSweepBaseline.test_completeness_guard`, `TestNoContextParameterKeyDuplication`
- `scripts/tests/test_autodev_summary.py` + `fixtures/autodev_summary/*`; `test_rn_remediate.py`, `test_rn_refine.py`, `test_rn_implement.py` (regression only)
- `scripts/tests/test_prepatch_check.py` `TestJunitParsing` is the pattern for the new module's tests

### Documentation
- `docs/reference/loops.md` (`## oracles/code-run-gate`: verdict paragraph, Parameters table, state-machine diagram, MR-3 artifact bullet), `docs/guides/LOOPS_REFERENCE.md` (autodev quality-gate paragraph ~1090; `rn-remediate` row; `on_failure (GATE_FAILED)` comment), `docs/guides/RECURSIVE_LOOPS_GUIDE.md` (`GATE_FAILED` token rows), `scripts/little_loops/loops/README.md` (`oracles/code-run-gate` row). Do NOT add CHANGELOG entries under `[Unreleased]`.

## Impact

- **Priority**: P3 - the env fixes in BUG-3689 remove most false failures; this only addresses red-on-`main`, which `quality_gate=false` already works around
- **Effort**: Large - base-SHA worktree run, failing-id extraction with message compare, timeout/loop-shape changes, `autodev` evidence and summary wiring, many pinned tests and docs
- **Risk**: High - a loose baseline match could mask a real regression; the base worktree lacks the dirty working-tree state corpus tests read
- **Breaking Change**: No

## Acceptance Criteria

- A run where every failing test id also fails on the base SHA with the same normalized message yields a passing verdict with the tolerated ids listed in the sidecar, evidence and summary.
- A run with at least one new failing id — including one whose message differs from base, one missing on base, or one that does not reproduce on HEAD — yields `GATE_FAILED`.
- Each fail-closed condition (rc != 1, id/count mismatch, over cap, non-pytest `test_cmd`, base setup/run infra failure, un-reproducible dirty base) yields `GATE_FAILED`, never a pass.
- With no base parameter, behavior is identical to today (regression tests for `rn-remediate` / `rn-refine`).
- The base worktree is always cleaned up, including on timeout, and does not trip `tamper_guard`.
- Loop `timeout:` exceeds the sum of state timeouts.

## Scope Boundaries

### Out of Scope

Fixing the two pre-existing corpus failures themselves (FEAT-3582 / EPIC-3687 prose-dependency drift; the ENH-3684 unverifiable quote) — track separately. Env/hermeticity fixes live in BUG-3689.

## Status

**Open** | Created: 2026-10-02 | Priority: P3
