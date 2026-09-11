---
id: BUG-3452
title: "CI run 34628255906 triage — oversized-test payloads, stale evidence spans, verdict-cache masking"
type: BUG
priority: P1
status: done
captured_at: '2026-09-11T23:35:11Z'
completed_at: '2026-09-11T23:35:11Z'
discovered_date: '2026-09-11'
relates_to:
- BUG-3451
- BUG-3439
- BUG-2111
- BUG-3065
- ENH-1441
- FEAT-959
size: Small
confidence_score: 96
outcome_confidence: 92
score_complexity: 20
score_test_coverage: 25
score_ambiguity: 10
score_change_surface: 20
labels:
- ci
- triage
- evidence-gate
- test-infra
---

# BUG-3452: CI run 34628255906 triage — oversized-test payloads, stale evidence spans, verdict-cache masking

## Summary

CI on `main` (run 34628255906, job 103358506994, commit `6351ac65`) failed with 3 of
23021 tests: two BUG-3439 oversized-spawn pins and the evidence repo gate. Investigation
found three independent root causes, all fixed and verified against the full CI-parity
suite (23255 passed, exit 0).

## Steps to Reproduce

1. Push to `main` at `6351ac65`; the self-hosted unit-tests job fails:
   - `test_fsm_runners.py::TestDefaultActionRunnerShellPath::test_oversized_script_spawns`
   - `test_runner_spec.py::TestRunActionDispatch::test_cmd_oversized_target_spawns`
     (both: `Argument list too long`, exit 126)
   - `test_verify_evidence.py::TestRepoGate::test_no_new_unverifiable_evidence`
     (5 evidence-unverifiable spans beyond baseline)
2. Run the same suite locally — all three pass, making the failure unreproducible
   on a warm dev machine.

## Root Cause

Three independent defects:

1. **Test bug (oversized pins)**: the BUG-3439 tests embedded the 140KB payload as a
   single argv element via `python3 -c "<payload>"`. Linux's MAX_ARG_STRLEN (131072 B)
   applies per-argument at *every* execve, so python3's own spawn failed even with the
   temp-file fix working — `bash` correctly executed `/tmp/ll-action-*.sh` and the
   script's first line was the thing that couldn't exec. The tests were only ever
   validated on darwin's higher per-arg limit; the docstrings' "fails on Linux only
   before the fix" claim was never actually exercised on Linux.
2. **Stale evidence spans**: five quoted spans in done issues no longer existed in
   their attributed sources (README rewrite, `CONFIG_DIR` migration to `.ll`,
   ALLOWLIST restructuring, a transient BUG-3063 flag that survives only in a local
   `refs/ll/abandoned/*` blob).
3. **Masking (BUG-3451)**: the gitignored verdict cache served stale found-verdicts
   unconditionally, so cause 2 passed locally while CI's cold checkout failed. Root-cause
   detail and fix live in BUG-3451.

## Diagnosis Method

Reproduced by checking out the CI commit (`git worktree add /tmp/ll-ci-repro 6351ac65`)
and moving `.ll/evidence-verdict-cache.json` aside: 4 of 5 spans failed there vs 0 on the
warm tree with a byte-identical baseline — isolating the cache as the local/CI divergence.
The 5th span (BUG-3065 → BUG-3063) verified only via `git log --all` reaching the
abandoned ref, unreachable from CI's origin-only refs.

## Fix

- `6dce98d0c` — oversized payloads moved into a bash variable assignment
  (`payload='<140KB>'; echo ${#payload}`): the action string still exceeds
  MAX_ARG_STRLEN (pinning the BUG-3439 temp-file path) but no child argv element does.
- `eb87da070` — VerdictCache found-entry revalidation (BUG-3451), regression test,
  CLI.md semantics correction, and reviewed `ll-evidence-ok` suppressions on the five
  stale spans (all four issues `done`, quoting at-filing state).

## Resolution

Implemented and verified: cold-cache `ll-verify-evidence --all` reports ok with 0
findings; `python -m pytest scripts/tests/ -m "not integration and not conformance"`
passes 23255 / skips 12 / exit 0 — CI parity restored. Known adjacent flake, out of
scope and not observed in this run: `test_cmd_script_tempfile_removed_after_run`
glob-races the shared system tempdir under xdist.


## Session Log
- `hook:posttooluse-status-done` - 2026-09-11T23:35:30 - `ab4f2b86-d6b4-4723-ad9c-ba7889e2e627.jsonl`
