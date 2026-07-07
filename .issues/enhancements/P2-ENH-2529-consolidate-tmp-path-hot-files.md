---
id: ENH-2529
title: "Consolidate tmp_path churn in top-3 hot test files to cut macOS re-indexing pressure"
type: ENH
priority: P2
status: in_progress
captured_at: '2026-07-07T00:00:00Z'
discovered_date: 2026-07-07
discovered_by: audit
size: Medium
labels:
- tests
- performance
- developer-experience
---

# ENH-2529: Consolidate tmp_path churn in top-3 hot test files to cut macOS re-indexing pressure

## Summary

The full pytest suite creates ~9,140 `tmp_path` dirs across 173 test files.
On macOS this churn under `/private/var/folders/<user>/T/` triggers
`launchservicesd`/`mds` re-indexing spikes (observed 229.9% CPU full-suite;
149.9% empirically reproduced during a scoped run), which starve
`WindowServer` and produce the "beachball" UI freeze during full runs.
Consolidate per-test temp dirs into module/session-scoped fixtures in the
three heaviest files where tests do not depend on parent-path uniqueness.

Source: audit run `.loops/runs/general-task-20260707T133447/audit-report.md`
(Finding #1 / Recommendation R1; evidence under that run's `evidence/` dir).

## Current Behavior

Top tmp_path reference counts:

- `scripts/tests/test_session_store.py` — 433
- `scripts/tests/test_hooks_integration.py` — 403
- `scripts/tests/test_ll_loop_commands.py` — 396

Each test gets its own function-scoped `tmp_path`; at 7 xdist workers that is
~1,300 dir creations per worker per run.

## Expected Behavior

Where a test does not require a unique parent dir, tests draw unique
sub-paths from a module- or session-scoped parent fixture
(`tmp_path_factory`), consolidating dir creation. Estimated 60-70% reduction
in tmp_path churn from these 3 files; estimated 30-50% reduction in
system-service re-indexing peaks.

## Proposed Solution

1. `test_session_store.py`: session-scoped parent fixture possible.
2. `test_hooks_integration.py`: class-scoped per-CLI-call.
3. `test_ll_loop_commands.py`: one parent per subcommand test class.

Tests still get unique sub-paths; only the parent consolidates. Pure test
refactor — no production code, schema, or interface changes.

## Acceptance Criteria

- Full suite still passes (`python -m pytest scripts/tests/`).
- tmp_path reference/creation count in the 3 files measurably reduced.
- **Before/after measurement required** — the 30-50% estimate rests on a
  16s scoped run; re-run the scoped 5-file sampler
  (`ps -axo pid,ppid,pcpu,nice,command` at 1s + `top -l N -s 1 -o cpu`)
  from the audit's Step 18 and compare `launchservicesd`/`WindowServer`
  peak %CPU against `evidence/during-run-ps-scoped.txt` (peak 149.9% / 8.0%).

## Implementation (2026-07-07)

Added a module-level `tmp_path` override in each of the 3 hot files: a
module-scoped `_module_tmp_parent` fixture (`tmp_path_factory.mktemp(...)`,
one top-level dir per module per worker instead of one per test) plus a
function-scoped `tmp_path` override that mkdirs a unique, fresh subdir named
`<sanitized-node-name>_<counter>`. Zero changes to test bodies; built-in
`tmp_path` semantics (fresh empty dir, unique per test) preserved.

Verified in sandbox: `py_compile` on all 3 files; standalone pytest run of
the override pattern (fresh/unique/shared-parent/parametrize/chdir) 5/5 pass.

**Pending local verification (sandbox lacks Python 3.11):**

- `python -m pytest scripts/tests/` full-suite pass.
- Before/after macOS sampler comparison per Acceptance Criteria.

## Scope Boundaries

- Do NOT touch conftest worker cap / renice (already in place, verified).
- No new "lighter" pytest config (config drift risk — explicitly rejected
  by the audit).
- Orphan-worker sweep (R2, ENH-2531) and fuzz deadlines (R3, ENH-2532)
  handled separately (done 2026-07-07); event-bus leak tracked as BUG-2530.
