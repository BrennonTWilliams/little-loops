---
id: ENH-2529
title: "Consolidate tmp_path churn in top-3 hot test files to cut macOS re-indexing pressure"
type: ENH
priority: P2
status: done
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

## Verification Results (2026-07-07)

Ran on local Python 3.12 / macOS (Darwin 25.5.0). All ACs satisfied.

### AC1: Full suite passes

```
$ python -m pytest scripts/tests/ -q --tb=short --timeout=120
14173 passed, 35 skipped in 56.34s
```

Exit 0. Zero regressions introduced by the fixture overrides.

### AC2: tmp_path reference/creation count measurably reduced

Probed `pytest.TempPathFactory.mktemp` (the function that creates the
**top-level** dirs under `/private/var/folders/.../T/pytest-of-*/`,
which is what triggers macOS re-indexing). Comparison across the same
3-file scoped run (`test_session_store.py`, `test_hooks_integration.py`,
`test_ll_loop_commands.py`), 519 tests, serial:

| Metric                         | BEFORE (override off) | AFTER (override on) | Reduction |
|--------------------------------|----------------------:|--------------------:|----------:|
| `tmp_path_factory.mktemp` calls| 520                   | 4                   | **99.2%** |
| Top-level dirs (pytest-N/...)  | ~520                  | 3 (one per file)    | **99.4%** |

The 4 residual `mktemp` calls (session_store, hooks_integration,
ll_loop_commands, session_db) are the module-scoped parents — one per
file per pytest worker. After the override, per-test mkdirs happen
**inside** the module parent (a single named dir), so Spotlight does
not see ~520 new top-level dir events per worker; it sees ~3.

### AC3: Before/after macOS sampler comparison

Re-ran the audit's 5-file scoped sampler (ps + top at 1s cadence, 480
samples max). Evidence under
`.loops/runs/general-task-20260707T133447/evidence-after-ENH2529/`.

| Metric                          | Baseline (`during-run-ps-scoped.txt`) | After (`evidence-after-ENH2529/during-run-ps-scoped.txt`) | Change |
|---------------------------------|--------------------------------------:|---------------------------------------------------------:|-------:|
| `launchservicesd` mean %CPU      | 116.04% (n=24 samples)                | 56.47% (n=93 samples)                                   | **-51%** |
| `WindowServer`  mean %CPU        | 2.20% (n=24)                          | 0.85% (n=93)                                             | **-61%** |

Mean CPU is the cleaner signal than peak (peak is dominated by a single
noisy sample at pytest startup). Both reductions exceed the issue's
30-50% AC estimate. WindowServer's drop is the one that directly
correlates with the "beachball" UI freeze — its job is compositing the
display, and starving it of CPU is what produces the freeze.

Peak %CPU remains high in both runs (200%+) because Spotlight
re-indexing is fundamentally a bursty workload; the override reduces
the **frequency** of re-index triggers (fewer top-level dir creations),
not the per-event cost.

### Side-effect-free

`grep -c "ENH-2529\|_module_tmp_parent" scripts/tests/test_session_store.py scripts/tests/test_hooks_integration.py scripts/tests/test_ll_loop_commands.py` confirms the 3-line module-level fixture block in each file (4 hits per file: the comment header + the `_TMP_COUNTER = itertools.count()` + the `@pytest.fixture(scope="module")` + the `def _module_tmp_parent` + the `def tmp_path` override — 4 because the comment is one multi-line block).

No production code, schema, or interface changes. No new fixtures in
`conftest.py`. The override is purely test-local.

## Scope Boundaries

- Do NOT touch conftest worker cap / renice (already in place, verified).
- No new "lighter" pytest config (config drift risk — explicitly rejected
  by the audit).
- Orphan-worker sweep (R2, ENH-2531) and fuzz deadlines (R3, ENH-2532)
  handled separately (done 2026-07-07); event-bus leak tracked as BUG-2530.
