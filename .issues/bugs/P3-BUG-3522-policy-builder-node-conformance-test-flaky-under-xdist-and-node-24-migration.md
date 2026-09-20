---
id: BUG-3522
type: BUG
title: policy-builder node conformance test flakes under xdist + Node 24 migration
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-20'
captured_at: '2026-09-20T05:20:00Z'
labels:
- policy-builder
- node
- xdist
- flake
- test-stability
relates_to:
- ENH-3453
- BUG-3486
- BUG-3502
---

# BUG-3522: policy-builder node conformance test flakes under xdist + Node 24 migration

## Summary

`scripts/tests/test_policy_builder_node_gate.py::test_node_conformance_suite_passes` runs `node --test scripts/tests/js/*.test.mjs` against a 180s timeout. Under full-suite xdist CPU contention, the suite intermittently fails — observed as a 2-fail / 1-pass pattern across three runs on `main @ fdf6773d2`. The Node runner was forcibly migrated from 20 to 24 by GitHub Actions during v1.165.0 integration; the conformance suite appears to interact with both xdist scheduling and the Node version transition.

## Current Behavior

The test runs `node --test` against `*.test.mjs` files (per `JS_TEST_DIR`). Under xdist CI load, the suite can fail intermittently — exit code != 0 with a subtest failure listing the specific assertion. The test passes when xdist workers happen to have lower load.

Observed pattern on `main @ fdf6773d2`:
- `35490420257` (main): FAIL
- `35490447772` (PR #29 rebased on `fdf6773d2`): pass
- `35490782202` (PR #32 rebased on `fdf6773d2`): FAIL

2-fail / 1-pass is the smoking-gun signature for a flake under contention, not a deterministic code regression. If Node 24 were a deterministic break, #29 wouldn't have passed.

## Expected Behavior

The node:test conformance suite passes reliably regardless of xdist worker contention. A flaky assertion under load is a CI flake, not a real bug — the suite exists precisely to prove the JS core matches canonical Python, so it must be stable.

## Steps to Reproduce

1. Push to a branch that triggers the `unit-tests` workflow
2. Watch xdist workers run the full unit suite under contention
3. Observe `test_node_conformance_suite_passes` fail intermittently (most visible during a fast push cadence)

## Likely Root Cause

The test launches `node --test` as a subprocess with a 180-second timeout. Under xdist CPU contention, the Node process's V8 JIT compilation or test orchestration may exceed time budgets or hit timing-sensitive assertions. The Node 20 to 24 migration (GitHub Actions' deprecation cycle) may have introduced subtle timing changes in the conformance suite.

The structural fix is `BUG-2523`'s established pattern: `@pytest.mark.no_parallel` — skip on xdist workers, run on the controller (or in serial `-n 0`). The 180-second budget is safe in that mode where there's no CPU contention.

## Proposed Solution

Add `@pytest.mark.no_parallel` to `test_node_conformance_suite_passes` — same pattern PR #30 used for `test_two_producers_reach_one_client_with_distinct_producer_pid`. Run on the controller or in serial `-n 0` where CPU contention is absent and the 180s budget is safe.

## Acceptance Criteria

- `test_node_conformance_suite_passes` passes reliably across 5+ consecutive CI runs on `main`
- The test runs on the controller or serial `-n 0` (not on xdist workers) — same pattern as BUG-3484's `test_two_producers_reach_one_client_with_distinct_producer_pid` no_parallel fix
- No regression in other JS conformance tests (`test_node_22plus_runs_ok`, `test_node_test_runner_emits_tap_v13`, etc.) — these presumably don't have the contention issue
- If a Node-version pin is also needed, add `actions/setup-node@v4` with `node-version: '22.x.y'` to the CI workflow — cheapest first probe before bisecting

## Notes

The Node 20 to 24 runner migration is documented as "Node.js 20 deprecated... forced onto Node.js 24" by the GitHub Actions runner announcement. Pinning to a specific Node 24.x.y version in `ci.yml` is a cheaper first probe than bisecting; if pinning fixes it, the issue reduces to "CI drift"; if not, the flake is contention-driven and `no_parallel` is the right fix.

If both pinning and `no_parallel` are needed, do both — pinning reduces CI maintenance burden (Node version control), `no_parallel` eliminates xdist contention.
