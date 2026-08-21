---
discovered_commit: fb5673902939bbf5a17bc7afe61317982d40bfd2
discovered_branch: main
discovered_date: 2026-07-24T23:13:40Z
discovered_by: deep-audit-session
status: done
completed_at: 2026-07-24T23:13:40Z
relates_to:
- BUG-2484
- BUG-2523
- BUG-2540
labels:
- tests
- performance
- macos
priority: P1
---

# BUG-2788: Full-suite filesystem churn starves macOS services → beachball (post cap+renice)

## Summary

`python -m pytest scripts/tests/` (~16k tests, M4 14-core) still beachballed the
machine despite the July 5 conftest defenses (xdist worker cap to `cpus//2` +
`os.nice(10)`). A deep audit showed the pytest workers were fine (~3.8 cores,
preemptible); the freeze came from **macOS system services running at nice=0
reacting to the suite's filesystem-event storm** — `launchservicesd` sampled at
a sustained ~220% CPU during a full run, plus `fseventsd`/`mds`. Those services
cannot be reniced from the repo, and total demand exceeded 14 cores, starving
WindowServer.

An A/B experiment isolated the driver: **file-creation volume**, not process
spawning. A strictly in-process test slice (no subprocesses) still pushed
`launchservicesd` to ~200%, while the most subprocess-heavy file alone
(`test_hooks_integration.py`, 103 unmocked spawns) only reached 5–33%.

## Steps to Reproduce

1. On macOS (Apple Silicon), run `python -m pytest scripts/tests/` (or
   `/ll:run-tests all`, or let an agent run the suite) while other apps are
   open.
2. Sample services during the run:
   `top -l 15 -s 3 -stats command,cpu | grep -Ei "launchservicesd|fseventsd|WindowServer"`.
3. Pre-fix: `launchservicesd` sustains ~220% CPU for the duration; combined
   demand exceeds core count and the UI beachballs.

## Current Behavior

(Pre-fix.) A full run forced a per-test `tmp_path` + extra mkdir for all
~13.7k tests (×7 workers), ran ~3,600 fuzz examples, and spawned
`git init`+config per repo fixture; `launchservicesd` sustained ~220% CPU and
the machine beachballed. Nested verify-gate suites ran unbudgeted, and bare
`pytest` from the repo root ran with no worker cap or timeout at all.

## Expected Behavior

A full suite run stays within the machine's headroom: temp directories are
created only for tests that use them, fuzz depth is a knob (`LL_FUZZ=full`),
worker counts are capped/clamped on every invocation path (including nested
gates and bare `pytest`), and the UI remains responsive throughout.

## Impact

Every full-suite run (interactive, `/ll:run-tests`, agent-driven, and each
concurrent ll-parallel/ll-sprint verify gate) degraded or froze the whole
machine, making the project's only CI gate hostile to run and encouraging
skipped verification.

## Status

Fixed and verified this session (2026-07-24): full suite green
(16,125 passed / 38 skipped) in ~73s vs ~112s baseline, temp-dir churn down
~3.4×, guardrails in place. Residual `launchservicesd` load from genuine test
file I/O is documented with optional system-level mitigations in
`docs/development/TROUBLESHOOTING.md`.

## Root Cause

Ranked churn sources (all verified):

1. **Two autouse conftest fixtures forced a fresh `tmp_path` for every test.**
   `_isolate_history_db` requested `tmp_path` solely to compute a path string
   for `LL_HISTORY_DB`; `_isolate_session_log_dir` requested it AND ran an
   unconditional `fake_home.mkdir()`. Net: ~13.7k tmp roots + ~13.7k extra
   mkdirs per run (×7 workers), plus pytest's startup rmtree of 3 retained
   `pytest-of-<user>` session trees.
2. ~3,600 hypothesis fuzz examples per run with no throttle knob (one test
   wrote a file per example).
3. 918 subprocess call sites incl. 13 real `git init` fixture sites across 9
   files (each: init + 2× config spawns per test).
4. `--dist load` (per-test scheduler round-trips on a 16k-test suite).
5. Unbounded multiplier: ll-parallel/ll-sprint verify gates each spawned a full
   `cpus//2`-worker nested suite concurrently, with no global budget.
6. Bypass holes: explicit `-n N` skipped the cap; `PYTEST_XDIST_AUTO_NUM_WORKERS`
   had no upper clamp; bare `pytest` from the repo root found **no ini at all**
   (no root pyproject.toml) so no cap/timeout applied; `/ll:run-tests` expanded
   an unset `{{config.project.test_dir}}` token and forced `-v`.

## Resolution

Landed in four phases (this session, uncommitted at time of writing):

- **Phase 1 — fixture rework** (`scripts/tests/conftest.py`,
  `scripts/pyproject.toml`): `_isolate_history_db` is now request-aware — when
  the test itself requests `tmp_path` it reuses that path (many tests construct
  `tmp_path/.ll/history.db` and rely on the env override coinciding via
  `_resolve_db_path`'s default-shape rule); otherwise it hands out a
  non-materialized path string under one session-scoped base
  (`tmp_path_factory.mktemp` once per worker + `itertools.count()`).
  `_isolate_session_log_dir` points `Path.home` at one shared session-scoped
  empty dir (production `Path.home()` consumers only read/glob). Added
  `tmp_path_retention_count = 1` / `tmp_path_retention_policy = "failed"`.
  Temp-dir count per run: ~13.7k+ → **4,027**.
- **Phase 2 — fuzz throttle + dist mode**: `tests/helpers.py::fuzz_max_examples`
  + conftest hypothesis profiles; fast by default (~25 examples/test, ~450
  total), `LL_FUZZ=full` restores each test's full depth (schema-fuzz file:
  0.9s fast vs 8.9s full). `--dist loadfile` added to addopts.
- **Phase 4 — guardrails**: env-override clamp `max(1, min(N, cpus-2))` in
  `pytest_xdist_auto_num_workers` (verified: `99` → 12 workers);
  `verify_epic_branch_before_merge` (`scripts/little_loops/worktree_utils.py`)
  now `setdefault`s `PYTEST_XDIST_AUTO_NUM_WORKERS=cpus//4` and `LL_FUZZ=full`
  into the gate env; new root `pytest.ini` stub closes the bare-`pytest` hole
  (bare run now collects `scripts/tests` with cap+timeout);
  `commands/run-tests.md` fixed (dead token removed, `-v` dropped from full
  runs, unit/integration scopes converted to `-m` marker expressions); optional
  system-level mitigations (Spotlight-privacy exclusion of the pytest temp
  root, `taskpolicy -b`) documented in
  `docs/development/TROUBLESHOOTING.md` § "Full-suite run makes macOS sluggish".
- **Phase 3 — git fixture consolidation**: `tests/helpers.py::copy_git_template`
  (per-process cached commitless template repo, `shutil.copytree` per test)
  replaced init+config spawns in `test_merge_coordinator.py`,
  `test_issue_lifecycle.py`, `test_worktree_concurrency.py`,
  `test_worktree_utils.py`, `test_codequery_codegraph.py`,
  `test_codequery_fallback.py`, `test_cli_code.py`,
  `test_manage_issue_changelog_gate.py`, `test_session_store.py`.

Incidental fixes made during verification:

- Stale doc-wiring pin updated in `scripts/tests/test_wiring_guides_and_meta.py`
  ("39 typed CLI tools" → "44"; README had moved on — pre-existing failure on
  main).
- Three continuity-compaction tests (`scripts/tests/test_fsm_continuity.py`,
  `scripts/tests/spike/fsm_continuity_compaction/test_continuity_pipeline.py`)
  now pin `LL_HOST_CLI=claude-code`: they inspect `-p` prompt args of the
  mocked summarizer CLI, but `resolve_host()` reads worker env/PATH, which a
  co-resident xdist test can leave in a state that routes to a non-claude host
  (no `-p`) or to the fail-soft level-3 truncation path (no CLI call). Flaked
  1–2 tests per run under the new `loadfile` sharding before hardening.

## Verification

- Full suite green ×1 post-hardening: **16,125 passed, 38 skipped in 73.4s**
  (baseline ~112s; ~35% faster).
- `top` sampling during runs: `launchservicesd` still spikes with legitimate
  test file I/O (inherent; Spotlight exclusion is the documented next lever),
  but with the shorter run, capped/niced workers, and ~7 cores of headroom,
  WindowServer no longer starves.
- Guardrails: `PYTEST_XDIST_AUTO_NUM_WORKERS=99` clamps to 12; bare `pytest`
  from repo root collects 16,163 tests under the new root `pytest.ini`.
- `ruff check` / `ruff format --check` / `mypy scripts/little_loops/` all clean.

## Known Residuals

- The worker-env pollution class that flaked the continuity tests still exists
  in the suite (same family as the event-bus leak in
  `test_issue_lifecycle` and the `test_ll_logs.py` TestEvalExport isolation
  failures); worth its own BUG if it resurfaces on other tests.
- `launchservicesd` load during runs is now proportional to genuine test file
  I/O (3,120 `write_text` calls in test bodies); further reduction requires
  either the documented system-level Spotlight exclusion or bulk test
  refactors that were explicitly descoped.


## Session Log
- `hook:posttooluse-status-done` - 2026-07-24T23:14:23 - `16c799a6-5ff5-423f-b842-dcdb0fc751f1.jsonl`
