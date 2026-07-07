---
id: BUG-2501
title: "Beachball persists despite conftest cap+nice \u2014 root cause: macOS launchservicesd/mds\
  \ re-indexing spike"
type: BUG
priority: P2
status: done
discovered_date: '2026-07-06'
discovered_by: investigation
captured_at: '2026-07-07T02:17:42Z'
completed_at: '2026-07-07T04:02:14Z'
labels:
- testing
- performance
- macos
- beachball
- system-services
decision_needed: false
confidence_score: 97
outcome_confidence: 67
score_complexity: 13
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 18
---

# BUG-2501: Beachball persists despite conftest cap+nice — root cause: macOS launchservicesd/mds re-indexing spike

## Summary

Running `python -m pytest scripts/tests/` still produces a macOS "beachball of
death" on the 14-core M4 host, **even though** the
[`scripts/tests/conftest.py`](../../scripts/tests/conftest.py) cap+nice fix from
the BUG-2484 / orphan-worker remediation is in place and working as designed.
Investigation on 2026-07-06 confirmed:

- The conftest fix is **active and correct**: controller at `nice=10`, all 7
  xdist workers at `nice=19`, capped to `cpus // 2` = 7 (not 14).
- The full suite **completes cleanly**: 13,828 tests in 111.59s, 4 unrelated
  `test_ll_logs.py::TestEvalExport` isolation failures, 27 skipped.
- Workers peaked at 40-100% CPU each (~3.8 cores total during peak) — within
  budget.
- **The beachball is caused by macOS system services spiking to 200%+ CPU
  during the run.** `launchservicesd` (PID 394) hit **229.9% CPU** (~2.3
  cores), with `mds` (Spotlight metadata) at 42%, `AppSSODaemon` at 44%,
  `ShortcutsViewService` at 41%, `CursorUIViewService` at 35%. All five
  services dropped to <1% within seconds of the test run completing.
- System services run at `nice=0` and **cannot be reniced from inside a
  conftest**. The conftest fix correctly handles the pytest-worker half of
  the problem; the system-services half is outside Python's control.

**The conftest fix is not a regression and is not the cause.** The cause is
the test suite's heavy temp-file I/O (13,828 `tmp_path` creations + 790
`os.chdir` calls per run) triggering `launchservicesd` to re-index files in
the macOS per-user temp dir.

## Root Cause

`launchservicesd` re-evaluates file associations and `mds` re-indexes
Spotlight metadata whenever files are created, modified, or the CWD changes.
The test suite does all three extensively:

- **13,828 `tmp_path` fixture creations** — every test gets a fresh
  `tempfile.TemporaryDirectory()` and writes at least one config / JSONL
  fixture file into it. `test_hooks_integration.py` alone has 96 unpatched
  `subprocess.run(...)` calls spawning real hook scripts that create their own
  files.
- **790 `os.chdir(tmp_path)` calls** across `scripts/tests/test_*.py` (grep
  count). The `os.chdir(tmp_path); ... ; os.chdir(original_dir)` idiom
  changes the cwd twice per call, doubling the file-association churn.
- **Spotlight/launchservicesd re-indexing is not instant**: it accumulates as
  files are created, then bursts CPU when the indexing daemon catches up.
  During the test run this sustained 200%+ CPU on the daemon for the full
  ~111s of the run.

The conftest cap+nice fix correctly nices the pytest workers, but it cannot
nice the macOS indexing daemons. With 3.5+ cores of system service work
running at normal priority plus 3.8 cores of (niced) pytest work, the system
periodically starves `WindowServer`, producing the beachball.

### Why the conftest fix doesn't help (and can't)

1. `os.nice()` only affects the calling process and its subprocesses (nice
   value is inherited). `launchservicesd`, `mds`, `AppSSODaemon`,
   `ShortcutsViewService`, and `CursorUIViewService` are all macOS system
   services started by `launchd` at `nice=0` (default).
2. macOS does not expose a per-process way to tell `launchservicesd` to
   ignore a path. The only options are to (a) keep the per-user temp dir
   out of its watch list via `mdutil -i off`, or (b) reduce the rate of
   file-system events the daemon must process.

## Current Behavior

A clean, uninterrupted `python -m pytest scripts/tests/` run on the 14-core
M4 host:

- Completes in ~111.59s.
- Workers run niced at `nice=19` and consume ~3.8 cores peak.
- **`launchservicesd` runs at 200%+ CPU for the duration of the run.**
- The Mac becomes intermittently unresponsive: brief beachballs, sluggish
  window dragging, delayed keystrokes in Claude Code.
- After the run finishes, system services drop to <1% within ~5s and the
  Mac returns to normal responsiveness.

This is **not** the orphaned-worker failure mode documented in the
[memory file](../../project_test_suite_beachball_fix.md) (that one
reparents to PPID=1 and spins at 100% forever). This is a *system-service
spike during a normal, clean run*.

## Expected Behavior

`python -m pytest scripts/tests/` runs to completion without the host
becoming unresponsive. The conftest cap+nice fix already ensures pytest
workers don't pin cores; the missing piece is preventing system services
from spiking in response to the test suite's file I/O.

## Steps to Reproduce

1. On a 14-core Apple Silicon Mac, ensure no other heavy processes are
   running (close Claude Code, IDE, etc., to isolate the test suite's
   effect).
2. Run `python -m pytest scripts/tests/ -q --tb=line 2>&1 | tail -5`.
3. In another terminal, sample CPU usage:
   ```bash
   while true; do
     ps -eo pid,user,%cpu,command | awk 'NR>1 && $3+0>20' | head -10
     echo "---"
     uptime
     sleep 1
   done
   ```
4. Observe `launchservicesd` (PID 394) and `mds` (PID 380 / `mds_stores`
   PID 567) sustaining 100-230% CPU for the duration of the run.
5. After the run completes, observe both drop to <1% within 5s.

## Proposed Solution

The fix is not in the test runner — it's in reducing the file-I/O churn the
test suite causes. Three options, ranked by leverage:

### Option A — System-level (highest leverage, out-of-project)

Disable Spotlight indexing on the macOS per-user temp dir:

```bash
mdutil -i off /private/var/folders/$(getconf DARWIN_USER_TEMP_DIR | cut -d/ -f4)/
```

This is a one-time, system-level change. It keeps `launchservicesd` and
`mds` from re-indexing `pytest`'s per-test `tmp_path` directories.
**No project code change required.** Trade-off: a side effect is that any
legitimate user file temporarily under the per-user temp dir won't be
indexed, but per-user temp dirs are conventionally excluded from
user-visible search anyway.

This is the highest-leverage mitigation and the **recommended first
action**. It is a developer-machine config change, not a project change.

### Option B — Reduce `os.chdir` pattern (project change, medium leverage)

> **Selected:** Option B — Reduce `os.chdir` pattern — 10/12 score; addresses root cause (leaky `os.chdir + try/finally` idiom triggers `launchservicesd` re-indexing on every CWD change); matches the in-tree `monkeypatch.chdir` default used in 48 other test files.

790 `os.chdir(tmp_path)` calls across test files. The
`os.chdir(tmp_path); ... ; os.chdir(original_dir)` idiom is error-prone
(leaks the original cwd on exception) and causes two CWD changes per call.
Replace with `monkeypatch.chdir(tmp_path)`, which auto-restores on test
teardown. Each replacement halves the CWD-change rate for that test.

Largest offenders (from a quick grep):
- `scripts/tests/test_hooks_integration.py` — many sites
- `scripts/tests/test_cli_e2e.py`
- `scripts/tests/test_subprocess_utils.py`
- `scripts/tests/test_loop_*.py` files

This is mechanical but high-volume. Could be done via a single
project-wide `grep`+`sed` (or a focused sweep per file). Trade-off: many
tests will need to be re-verified because the original `os.chdir` pattern
silently relied on the post-test cwd-restore happening.

### Option C — Lower the conftest worker cap (smallest change, smallest payoff)

`conftest.py:53` currently returns `max(2, cpus // 2)`. Reducing to
`max(2, cpus // 3)` would cut worker count from 7 to ~4, cutting file-I/O
rate by ~43%. Wall-clock time would increase proportionally (~111s → ~190s
estimated). Trade-off: longer CI loop for partial relief.

Not recommended alone — the leverage is small compared to A and B.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-07-06.

**Selected**: Option B — Reduce `os.chdir` pattern (project change, medium leverage).

**Reasoning**: Option B scores 10/12 across Consistency/Simplicity/Testability/Risk — the highest of the three options. The `monkeypatch.chdir` pattern is the in-tree default (539 usages across 48 test files including `scripts/tests/test_pre_compact.py:32-34`, `scripts/tests/test_sweep_stale_refs.py:23-27`, `scripts/tests/test_loop_cli_defaults.py:23-27`), so the swap is mechanical rather than architectural. Option B also addresses the root cause: the `os.chdir + try/finally` idiom is both error-prone (cwd leak between `os.getcwd()` capture and `try:` entry — the same failure mode `_isolate_session_log_dir` at `scripts/tests/conftest.py:585-611` was created to fix via `monkeypatch.setattr`-with-finalizer) and contributes to `launchservicesd` re-indexing (one CWD change per `os.chdir` call, two per try/finally block). Option A's higher leverage is offset by zero testability (system-level macOS config has no CI-enforceable gate; the `mdutil -i off` command is per-machine only). Option C is already achievable without code change via `PYTEST_XDIST_AUTO_NUM_WORKERS=4` and is the lowest-leverage option per the issue body's own ranking.

**Note**: The issue body recommends running A → B together, with A as a 1-minute developer-machine quick win (`mdutil -i off` + a `docs/development/TROUBLESHOOTING.md` section modeled on the Jetsam recipe at `docs/development/TROUBLESHOOTING.md:335-352`) and B as the project-side cleanup. Option B's selection here is the *project-side decision*. The doc-only Option A should still happen as a complementary developer-machine mitigation but is not the project-side fix and isn't scored against Option B.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| A — `mdutil -i off` (system-level) | 2/3 | 3/3 | 0/3 | 2/3 | 7/12 |
| **B — `os.chdir` → `monkeypatch.chdir` (project change)** | **3/3** | **2/3** | **3/3** | **2/3** | **10/12** |
| C — Worker cap `cpus // 3` | 3/3 | 3/3 | 2/3 | 1/3 | 9/12 |

**Key evidence**:
- **Option A** (Reuse 1/3): Strong doc precedent — `docs/development/TROUBLESHOOTING.md:335-352` (Jetsam) follows identical Symptom/Cause/Solution shape with per-machine shell command + macOS tag. No `mdutil`/`mdls`/`mdfind`/`xattr`/`Spotlight`/`launchservicesd` references anywhere in repo (verified by codebase-pattern-finder). Option A's correctness is verified by inspection (`mdutil -s`), not by CI.
- **Option B** (Reuse 3/3): 539 `monkeypatch.chdir` usages across 48 files (verified). Mechanical swap template is a single-line substitution per site. No test asserts on real cwd post-finally (all 8 `assert.*cwd` hits are subprocess `cwd=` kwargs or `LLHookEvent` payload fields). Special cases bounded: inline `import os` cleanup, `tmp_loops.parent` sites (4 in `test_concurrency.py`), `sys.argv` pairing (7 sites across `test_cli_e2e.py` × 6 + `test_cli_decisions.py` × 1), `in_tmp` wrapper rewrite in `test_hook_session_start.py` (102 tests depend on this fixture), `tempfile.TemporaryDirectory` → `tmp_path` swap in `test_user_messages.py:474-487`.
- **Option C** (Reuse 3/3): Fits existing override architecture — `scripts/tests/conftest.py:42-47` env-var precedence preserved, `LL_TEST_NO_NICE=1` opt-out at `scripts/tests/conftest.py:65-66` is the same env-var pattern. But BUG-2488's verification does NOT recommend a divisor reduction and documents `PYTEST_XDIST_AUTO_NUM_WORKERS=4` as the existing per-run escape hatch that achieves the same effect without code change. Trade-off: ~70s wall-clock cost (~111s → ~190s) for ~43% `launchservicesd` CPU reduction — lowest leverage of the three options.

#### Implementation order (recommended)

1. **Option A first** (1 minute): Run `mdutil -i off /private/var/folders/$(getconf DARWIN_USER_TEMP_DIR | cut -d/ -f4)/` and add a `docs/development/TROUBLESHOOTING.md` "Beachball during test suite" section modeled on the Jetsam recipe. Immediate relief; per-machine only.
2. **Option B** (project-side cleanup, 2-4 hours): Mechanical `os.chdir + try/finally` → `monkeypatch.chdir(tmp_path)` sweep across 9 test files (250 verified sites; issue's "790" overcounts because it includes `patch(...)` mocks of production `os.chdir` callers). Model on `scripts/tests/test_pre_compact.py:32-34`. Update `docs/development/TESTING.md:708-717` to recommend `monkeypatch.chdir` for non-E2E uses.
3. **Option C only if needed**: Try `PYTEST_XDIST_AUTO_NUM_WORKERS=4` env-var override before committing to `cpus // 3` in code.

#### Regression tests to add

- **`scripts/tests/test_conftest_cap.py`** — direct unit tests for `pytest_xdist_auto_num_workers` (env-var precedence + `// N` arithmetic) and `pytest_configure` (`LL_TEST_NO_NICE=1` short-circuit). Pattern: `scripts/tests/test_pytest_history_plugin.py:62-81` (direct hook invocation with `MagicMock` config). Note: `scripts/tests/conftest.py` is not normally importable as a module; load via `importlib.util.spec_from_file_location("conftest", "<abs_path>/conftest.py")`.
- Optional **`scripts/tests/test_bug_2501_wall_clock_budget.py`** — wall-clock regression that spawns `python -m pytest scripts/tests/ -q` as subprocess with bound. Pattern: `scripts/tests/test_policy_builder_node_gate.py:45-71` (subprocess-wrap external gate with `shutil.which` + version probe + `pytest.skip` for graceful absence).

## Impact

- **Priority**: P2 — the suite still completes; the user pain is
  intermittent unresponsiveness, not a correctness failure.
- **Effort**:
  - Option A: ~1 minute (single shell command, no project change).
  - Option B: ~2-4 hours (790 call sites, mostly mechanical, some
    require per-site test re-verification).
  - Option C: ~5 minutes (one-line change to `conftest.py`, requires
    re-running the suite to re-baseline wall-clock time).
- **Risk**:
  - Option A: low; standard developer-machine config.
  - Option B: low-medium; tests that rely on the post-test cwd restore
    could regress if not properly rewritten to `monkeypatch.chdir`.
  - Option C: low; lower cap = slower but functional.
- **Breaking Change**: No.

## Integration Map

### Files to Modify (Option B; project-side change)
- `scripts/tests/conftest.py` — no change required for Option B.
- 790 call sites across `scripts/tests/test_*.py` (specifically the
  `os.chdir(tmp_path); ... ; os.chdir(original_dir)` idiom). A
  project-wide `grep -lE "os\.chdir\(tmp_path\)" scripts/tests/*.py`
  enumerates them.

### Dependent / Related Code
- `scripts/tests/conftest.py:30-74` — the existing cap+nice fix; not
  modified by this issue's mitigations (it's the right fix for the
  pytest-worker half).
- `scripts/little_loops/host_runner.py` — runs `claude` / `codex`
  subprocesses from tests; subprocesses **do** inherit nice from the
  parent worker (verified 2026-07-06), so this is not a contributing
  cause.

### Similar Patterns
- `scripts/tests/conftest.py:505-577` — `_isolate_history_db*` and
  `_guard_real_history_db` — the project's established pattern for
  preventing tests from touching real filesystem state. **Could be
  extended** with an `_isolate_temp_dir_from_spotlight` fixture that
  marks `tmp_path` directories as Spotlight-excluded via xattr
  (`com.apple.metadata:_kMDItemUserTags=hidden`), but that only works
  in userspace — the actual indexing daemon runs as root and respects
  the system-level `mdutil` setting, not per-file xattrs. So the
  in-conftest approach is **not viable**; the system-level `mdutil` is
  the right answer.

### Tests
- The existing test suite is the regression check. No new tests are
  required for Option A (system-level). For Option B, run the suite
  with `time python -m pytest scripts/tests/` and verify wall-clock
  time does not regress (a reduction in `os.chdir` rate should keep it
  the same or improve it, since CWD changes are not free).

### Documentation
- `docs/development/TROUBLESHOOTING.md` — add a "Beachball during test
  suite" section recommending `mdutil -i off` on the per-user temp
  dir and pointing to this issue. No project code change required.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Verified per-file `os.chdir(` call counts (Option B targets):**

| File | `os.chdir(` sites | Notes |
|------|-------------------|-------|
| `scripts/tests/test_hooks_integration.py` | 186 | Largest single offender; 96 `subprocess.run` calls within chdir blocks. |
| `scripts/tests/test_cli.py` | 20 | Class-based integration tests. |
| `scripts/tests/test_concurrency.py` | 16 | 4 sites are `os.chdir(tmp_path)`; rest use `os.chdir(tmp_loops.parent)`. |
| `scripts/tests/test_cli_e2e.py` | 12 | E2E tests; documented pattern in `docs/development/TESTING.md:708-717`. |
| `scripts/tests/test_issue_manager.py` | 8 | Inline `import os` inside test methods. |
| `scripts/tests/test_cli_loop_worktree.py` | 7 | Worktree integration tests. |
| `scripts/tests/test_hook_session_start.py` | 2 | Has an `in_tmp` wrapper fixture at lines 19-27 — can be replaced wholesale by `monkeypatch.chdir`. |
| `scripts/tests/test_user_messages.py` | 2 | Single canonical site at line 477. |
| `scripts/tests/test_cli_messages_save.py` | 2 | E2E save pattern. |
| `scripts/tests/test_cli_decisions.py` | 2 | Decisions CLI tests. |

Total verified: **257 `os.chdir(` calls across 10 test files.** The
issue's stated "790" count likely includes broader grep patterns
(`os.chdir(self.tmp_path)`, `os.chdir(tmp_path.parent)`, etc.) — actual
`os.chdir(tmp_path)` literal occurrences are ~99 across 4 files.

**`monkeypatch.chdir(tmp_path)` exemplars to model Option B on:**
- `scripts/tests/test_pre_compact.py:32-34` — cited in
  `docs/claude-code/write-a-hook.md:207, 225` as the model for new hook tests.
- `scripts/tests/test_pre_compact_handoff.py:74-77` — same shape, with docstring.
- `scripts/tests/test_loop_cli_defaults.py:23-27` — cleanest class-based example
  (config + `monkeypatch.chdir(tmp_path)`).
- `scripts/tests/test_ll_loop_state.py:48` — pairs chdir with state-file setup.

**Why `monkeypatch.chdir` is strictly better (verified gap):**
The `os.chdir + try/finally` form has a hidden failure mode the issue doesn't
flag: if `os.getcwd()` raises *between* the `original_dir = os.getcwd()` line
and the entry to the `try` block (e.g. cwd deleted), cwd leaks to the test
process and never restores. `monkeypatch.chdir` registers the restore as a
fixture finalizer that runs regardless of how the test exits, eliminating this
window. Documented at `scripts/tests/conftest.py:585-611` (`_isolate_session_log_dir`)
which uses the same `monkeypatch.setattr`-with-finalizer pattern.

**Configuration knobs already available (relevant for Option C / verification):**
- `PYTEST_XDIST_AUTO_NUM_WORKERS=<N>` — overrides the `cpus // 2` cap
  (`scripts/tests/conftest.py:42-47`).
- `LL_TEST_NO_NICE=1` — opt out of `os.nice(10)` (`scripts/tests/conftest.py:65-66`).
- `-n <N>` / `-n 0` — explicit worker count; bypasses the conftest cap.

**Pytest config that drives the indexing pressure:**
- `scripts/pyproject.toml:146-177` — `[tool.pytest.ini_options]`. The
  `-n logical` default (line 170-177) sends workers = `psutil.cpu_count(logical=True)`
  through the conftest cap, which currently lands at 7 on a 14-core M4.

## Wiring Findings (added by `/ll:wire-issue`)

The `/ll:wire-issue` pass traced the full codebase coupling surface
(3 parallel agents: caller tracer, side-effect surface tracer, test gap
finder). Findings below supplement the "Codebase Research Findings"
above; the original plan remains the recommended path.

### Misleading claims in the issue (wiring correction)

- **`scripts/tests/test_cli_loop_worktree.py`** — the 7 `os.chdir(` sites
  cited (line 267 of this issue) are
  `patch("little_loops.cli.loop.run.os.chdir", side_effect=...)` mocks,
  **not** direct `os.chdir` callers. They test that production code
  (`scripts/little_loops/cli/loop/run.py:476`, BUG-2386) calls
  `os.chdir(_worktree_path)`. **Option B does NOT touch these sites.**
  The actual `os.chdir + try/finally` count in `test_cli_loop_worktree.py`
  is 0 — total target sites remain 257 across 9 files, not 10.
- **`scripts/tests/test_subprocess_utils.py`** — cited as a "largest
  offender" (line 166-167 of the issue) but grep finds zero
  `os.chdir + try/finally` sites; only `monkeypatch.chdir(tmp_path)` at
  line 174 (already correct).
- **`scripts/tests/test_loop_*.py` files** — cited collectively (line 168)
  but no `scripts/tests/test_loop_*.py` file contains
  `os.chdir(tmp_path)`; they use `monkeypatch.chdir(tmp_path)`
  exclusively. The grep that produced the "790" count used broader
  patterns that don't reflect direct call sites.

### New Dependent / Related Code (not in the issue body)

- `scripts/little_loops/cli/loop/run.py:98, 476` — production-code
  `os.chdir(_worktree_path)` (BUG-2386); tests at
  `scripts/tests/test_cli_loop_worktree.py:733-1102` mock this call
  site. Unaffected by Option B; surfaced only because the issue body
  mentions the worktree test file as a target.
- `scripts/little_loops/hooks/__init__.py:136` — `cwd=os.getcwd()`
  (read-only consumer when constructing the `LLHookEvent` payload). Not
  a target.
- `scripts/little_loops/pytest_history_plugin.py:41-47` — plugin reads
  `Path.cwd() / ".ll"` at load time; load-time cwd is the repo root
  (per-test `tmp_path` chdirs happen after pytest plugin load). No
  coupling.
- `scripts/tests/conftest.py:82-96` — `stable_snapshot_env(monkeypatch)`
  fixture (public surface; referenced from `CONTRIBUTING.md:739`).
- `scripts/tests/conftest.py:631-637` — `_restore_cmd_run_env_vars(monkeypatch)`
  fixture (sibling autouse, no coupling).
- `.ll/learning-tests/pytest.md` — proven claims about pytest fixtures /
  `monkeypatch.setenv` / `conftest.py` visibility (related to the
  fixture patterns this issue relies on).
- `.ll/decisions.yaml:3973` — references `_isolate_history_db*` /
  `_guard_real_history_db` choke-point convention.
- `.issues/bugs/P2-BUG-1995-pytest-opens-real-history-db.md` —
  established the `_isolate_history_db*` / `_guard_real_history_db`
  pattern in `conftest.py:505-577`.
- `.issues/bugs/P2-BUG-2489-event-bus-lifecycle-test-xdist-sharding-isolation-leak.md`
  — established the `_isolate_session_log_dir` `monkeypatch-with-finalizer`
  pattern in `conftest.py:585-611`.

### New canonical exemplar (test pattern to model Option B on)

- **`scripts/tests/test_sweep_stale_refs.py:23-27`** —
  `in_tmp(tmp_path, monkeypatch)` already uses
  `monkeypatch.chdir(tmp_path)`. **This is the cleanest in-tree
  exemplar**; the issue body attributes the `in_tmp` wrapper to
  `scripts/tests/test_hook_session_start.py:19-27` (which has the legacy
  `original = os.getcwd(); os.chdir(tmp_path); try: ... finally:` form)
  — the `test_sweep_stale_refs.py` version is the one to model on.
- `scripts/tests/integration/test_issue_lifecycle_e2e.py:50, 85, 110` —
  `monkeypatch.chdir(temp_project_dir)` (project_dir variant).
- `scripts/tests/integration/test_loop_run_e2e.py:56, 88, 117` —
  `monkeypatch.chdir(tmp_path)` (E2E variant).
- `scripts/tests/test_pytest_history_plugin.py:36, 42, 48, 57, 65, 76,
  167, 174` — additional `monkeypatch.chdir(tmp_path)` exemplars.

**49 additional test files already use `monkeypatch.chdir(tmp_path)`**
across the suite (broad pattern established; key sites:
`test_cli_sprint.py` 24, `test_sprint_integration.py` 18,
`test_cli_loop_dispatch.py` 56, `test_ll_loop_commands.py` 32,
`test_ll_loop_execution.py` 32, `test_hook_post_tool_use.py` 21,
`test_json_output_contracts.py` 5, `test_ll_loop_parsing.py` 10).

### Per-site special handling (Option B)

- **`scripts/tests/test_concurrency.py:105, 116, 130, 219`** — 4 of 16
  sites use `os.chdir(tmp_loops.parent)` (not `tmp_path`). Option B
  replaces with `monkeypatch.chdir(tmp_loops.parent)`; **must add
  `monkeypatch: pytest.MonkeyPatch` to the test signature.**
- **`scripts/tests/test_hook_session_start.py:19-27`** — the `in_tmp`
  wrapper fixture (with the legacy `os.chdir + try/finally` body) is
  **NOT** the canonical model — it's a target. Replace its body
  wholesale using `test_sweep_stale_refs.py:23-27` as the model.
- **`scripts/tests/test_user_messages.py:474-487`** — uses
  `tempfile.TemporaryDirectory()` (not pytest's `tmp_path` fixture).
  Option B: swap to `tmp_path` + `monkeypatch.chdir(tmp_path)`, drop
  the `TemporaryDirectory` block. The other site at lines 111-126 uses
  `monkeypatch.setattr(Path, "home", ...)` and is unaffected.
- **`scripts/tests/test_hooks_integration.py` (186 sites)** and
  **`scripts/tests/test_issue_manager.py` (8 sites)** — many sites have
  inline `import os` inside the test body. After Option B's
  `os.chdir` → `monkeypatch.chdir` swap, these `import os` lines
  become unused (no other `os.*` reference in the same scope).
  **Mechanical cleanup: remove inline `import os` after the swap.**
- **`scripts/tests/test_cli_e2e.py:240-276, 324-360, 371-395, 405-419,
  456-479, 490-513`** — six E2E sites pair `os.chdir(e2e_project_dir)`
  with `sys.argv` rewriting in the same `try/finally` block.
  `monkeypatch.chdir` handles cwd; `sys.argv` still needs explicit
  restore (use `monkeypatch.setattr(sys, "argv", original_argv)`).
- **`scripts/tests/test_cli_decisions.py:1015-1032`** — same pattern:
  chdir + sys.argv rewriting; needs `monkeypatch.setattr(sys, "argv",
  ...)`.

### New tests to add (regression capture)

The codebase has **no `scripts/tests/test_conftest.py`** —
`pytest_xdist_auto_num_workers`, `pytest_configure`, and the
`LL_TEST_NO_NICE=1` short-circuit have no committed regression tests.
BUG-2488 §88-89 references an ad-hoc `os.nice(0) >= 10` probe but it
is not in the suite. To prevent Option C (`cpus // 2` → `cpus // 3`)
and Option A (`mdutil` system config) from regressing silently, add:

- **`scripts/tests/test_conftest_cap.py`** — direct unit tests for
  `pytest_xdist_auto_num_workers` honoring
  `PYTEST_XDIST_AUTO_NUM_WORKERS`, the `// N` arithmetic (Option C
  verification), and the `LL_TEST_NO_NICE=1` short-circuit in
  `pytest_configure`. **Pattern:
  `scripts/tests/test_pytest_history_plugin.py:62-81`** (direct hook
  invocation with `MagicMock` config).
  - Note: `scripts/tests/conftest.py` is not normally importable as a
    module; load via `importlib.util.spec_from_file_location("conftest",
    "<abs_path>/conftest.py")` or place the test outside
    `scripts/tests/`.
- **`scripts/tests/test_bug_2501_wall_clock_budget.py`** (optional) —
  wall-clock regression that spawns `python -m pytest scripts/tests/ -q`
  as a subprocess with a bound. **Pattern:
  `scripts/tests/test_policy_builder_node_gate.py`** (the project's
  "wrap external gate as pytest test" template).

**Tests that may break under Option B**: All 257
`os.chdir + try/finally` sites across 9 files. None assert on
`os.getcwd()` after the finally clause (verified via grep), so semantic
is preserved. The mechanical risk is the inline-`import os` removal,
the `sys.argv + chdir` pair sites, and the `in_tmp` fixture wrapper.

### No coupling to plugin manifests / settings

- `scripts/pyproject.toml:97-100` — `[project.entry-points.pytest11]`
  registers `ll_history` plugin (no `os.chdir`/`monkeypatch` coupling;
  plugin loads at repo-root cwd).
- `.claude-plugin/plugin.json`, `hooks/hooks.json` — do NOT reference
  conftest, beachball, launchservicesd, or pytest.
- `.ll/ll-config.json`, `.claude/settings.local.json`,
  `config-schema.json` — no references to `cpus //`, `nice`,
  `os.chdir`, `monkeypatch.chdir`, `mdutil`, or beachball.
- `commands/run-tests.md` and FSM loops (`general-task.yaml`,
  `fix-quality-and-tests.yaml`) use `{{config.project.test_cmd}}`
  templating; no pytest-flag coupling.
- `scripts/little_loops/cli/loop/run.py:98, 476` — production `os.chdir`
  calls unchanged; no impact.

### Pyproject comment update (if Option C is chosen)

- `scripts/pyproject.toml:156-163` — the comment block explicitly
  documents `PYTEST_XDIST_AUTO_NUM_WORKERS`, `LL_TEST_NO_NICE=1`, and
  `-n 0` as the override knobs. If Option C lands
  (`cpus // 2` → `cpus // 3`), update this comment to mention the new
  `cpus // 3` rationale so the override story stays accurate.

### Test pattern coupling (cross-file imports)

- **No test imports any helper, fixture, or symbol from any of the 9
  affected test files** (verified via `from scripts.tests.test_*` /
  `from .test_*` searches returning no matches). All affected files are
  self-contained test modules.

### Issue template coupling

- `.issues/templates/` does NOT exist. No template references
  `os.chdir`, `monkeypatch.chdir`, `conftest.py`, `cpus //`, `nice`,
  or pytest flags outside issue bodies.

## Implementation Steps

### Option A — System-level (`mdutil -i off`, fastest win)

1. Run on the developer's machine:
   ```bash
   mdutil -i off /private/var/folders/$(getconf DARWIN_USER_TEMP_DIR | cut -d/ -f4)/
   ```
2. Verify with `mdls /tmp/<some-file>` — metadata should not update.
3. Re-run `time python -m pytest scripts/tests/` and confirm:
   - `launchservicesd` peak drops below 50% CPU.
   - No beachballs during the run.
   - Wall-clock time roughly preserved (~111s).
4. Add a section to `docs/development/TROUBLESHOOTING.md` referencing this issue
   and the `mdutil -i off` command.

### Option B — Project-level (`os.chdir` → `monkeypatch.chdir`)

1. **Reference files** (in order of expected ROI):
   - `scripts/tests/test_hooks_integration.py` — 186 sites; replace wholesale
     using the `test_pre_compact.py:32-34` model (single `monkeypatch.chdir(tmp_path)`).
   - `scripts/tests/test_cli.py` — 20 sites.
   - `scripts/tests/test_concurrency.py` — 16 sites; mind the
     `os.chdir(tmp_loops.parent)` non-`tmp_path` calls — `monkeypatch.chdir`
     works for any path.
   - `scripts/tests/test_cli_e2e.py` — 12 sites; documented pattern at
     `docs/development/TESTING.md:708-717` may need updating to recommend
     `monkeypatch.chdir` for non-E2E uses.
   - `scripts/tests/test_issue_manager.py` — 8 sites.
   - Remaining files — small fixes; mechanical.

2. **Mechanical replacement template** (per site):
   ```python
   # Before
   original_dir = os.getcwd()
   try:
       os.chdir(tmp_path)
       ...body...
   finally:
       os.chdir(original_dir)

   # After (model: scripts/tests/test_pre_compact.py:32-34)
   monkeypatch.chdir(tmp_path)
   ...body...
   ```
   Add `monkeypatch: pytest.MonkeyPatch` to the test signature if not present.

3. **Verification**:
   - Run `time python -m pytest scripts/tests/` — wall-clock should not regress
     (a reduction in `os.chdir` rate should keep or improve it).
   - Spot-check the `tmp_path` cwd is restored between tests by running
     `pytest --tb=short scripts/tests/test_hooks_integration.py` and
     confirming no cwd-leak failures.
   - Update `docs/development/TESTING.md` to recommend `monkeypatch.chdir`
     as the default and reserve `os.chdir` for E2E only.

4. **Risk-mitigation note**: Some existing `try/finally` sites may rely on
   side-effects of the explicit restore ordering. Re-run each touched file
   individually before merging to catch subtle behavior differences.

### Option C — Worker cap reduction

1. Edit `scripts/tests/conftest.py:53` from
   `return max(2, cpus // 2)` to `return max(2, cpus // 3)`.
2. Run `time python -m pytest scripts/tests/` and confirm:
   - Workers = 4 (instead of 7) on a 14-core M4.
   - Wall-clock time increases proportionally (~111s → ~190s estimated).
   - `launchservicesd` CPU drops ~43%.
3. If trade-off is acceptable, ship. If not, revert and rely on A + B.

### Recommended sequence

Run Options A → B in that order. Option C is a fallback if A + B together
don't fully eliminate the beachball.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be
included in the implementation:_

1. **Correct the file count claim**: Update `Integration Map` to clarify
   that `test_cli_loop_worktree.py` has 0 direct `os.chdir` callers (the
   7 cited sites are `patch()` mocks for BUG-2386 verification). Total
   `os.chdir + try/finally` sites is **257 across 9 files**, not 10.
2. **Replace inline `import os`**: After Option B's `os.chdir` →
   `monkeypatch.chdir` swap in `scripts/tests/test_hooks_integration.py`
   (186 sites) and `scripts/tests/test_issue_manager.py` (8 sites),
   remove the now-unused inline `import os` lines.
3. **Add `monkeypatch` to test signatures** for sites that swap to
   `monkeypatch.chdir(tmp_loops.parent)` (4 sites in `test_concurrency.py`)
   and `monkeypatch.setattr(sys, "argv", original_argv)`
   (`test_cli_e2e.py` × 6, `test_cli_decisions.py` × 1).
4. **Update `scripts/pyproject.toml:156-163` comment** (Option C only):
   mention the `cpus // 3` rationale alongside the existing
   `PYTEST_XDIST_AUTO_NUM_WORKERS` / `LL_TEST_NO_NICE=1` / `-n 0`
   override docs.
5. **Add regression tests** (recommended for Option C):
   - Create `scripts/tests/test_conftest_cap.py` — direct unit tests
     for `pytest_xdist_auto_num_workers` and `pytest_configure`
     (`LL_TEST_NO_NICE` short-circuit). Pattern:
     `scripts/tests/test_pytest_history_plugin.py:62-81`.
   - Optional: `scripts/tests/test_bug_2501_wall_clock_budget.py` —
     wall-clock bound. Pattern:
     `scripts/tests/test_policy_builder_node_gate.py`.
6. **Update `docs/development/TESTING.md:708-717`** to recommend
   `monkeypatch.chdir(tmp_path)` for non-E2E uses and reserve `os.chdir`
   for E2E only.
7. **Update `docs/development/TROUBLESHOOTING.md`** to add a "Beachball
   during test suite" section recommending `mdutil -i off` (Option A)
   and pointing to BUG-2501.

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-07-07_

**Readiness Score**: 97/100 → PROCEED
**Outcome Confidence**: 67/100 → MODERATE

### Outcome Risk Factors

- **Decision point on three competing options**: A (`mdutil` system config, ~1 min, no project change), B (`os.chdir` → `monkeypatch.chdir` mechanical sweep across 257 sites / 9 files, ~2–4 hr), and C (`conftest.py:53` worker-cap cut, ~5 min, slower wall-clock). Decision was resolved via `/ll:decide-issue` on 2026-07-06 — **Option B** selected (10/12 vs A=7/12, C=9/12); the resolved rationale is documented in the `## Proposed Solution` → `### Decision Rationale` block above. Implementation should follow the A → B recommended sequence (A as 1-minute developer-machine quick win, B as the project-side cleanup), with C as fallback via the existing `PYTEST_XDIST_AUTO_NUM_WORKERS=4` env-var override.
- **Broad enumeration across 257 sites in 9 files**: Option B is a Pattern B fanout (enumerated + verification grep `grep -lE "os\.chdir\(tmp_path\)" scripts/tests/*.py`) but no automated completeness test currently exists; adding `scripts/tests/test_conftest_cap.py` is recommended but optional per the wiring analysis.
- **Per-site special handling complicates the mechanical sweep**: 7 sites pair `chdir + sys.argv` rewriting (`test_cli_e2e.py` × 6, `test_cli_decisions.py` × 1) requiring `monkeypatch.setattr(sys, "argv", original_argv)`; 4 sites in `test_concurrency.py` use `tmp_loops.parent` instead of `tmp_path` (need `monkeypatch` signature); `test_hooks_integration.py` (186) and `test_issue_manager.py` (8) have inline `import os` that becomes unused post-swap and must be removed; `test_hook_session_start.py`'s `in_tmp` fixture wrapper needs whole-body replacement. None break semantics (verified no `os.getcwd()` post-finally assertions), but each requires per-site attention during the sweep.

### Notes
- All Phase 4 flags: `decision_needed` already `false` (resolved via `/ll:decide-issue` 2026-07-06T02:58:50; Option B selected, see `## Proposed Solution` → `### Decision Rationale`); no `missing_artifacts` (the recommended `test_conftest_cap.py` is documented as additive regression coverage, not a pre-condition); not eligible for `mechanical_fanout_suppressed` (the risk factor describes the sweep explicitly rather than as a complaint about file count); no `implementation_order_risk` (the recommended test is described as additive regression coverage, not "implement first").
- Existing `confidence_score: 92` overcounted outcome confidence; fresh assessment under current rubric (max 25/criterion) recalibrates to 67 (MODERATE). Readiness held at 97 — refined + wired issue with verified code references and a clear ranking of options.

## Session Log
- `/ll:ready-issue` - 2026-07-07T03:06:11 - `0c116590-79b9-4fa7-a6dd-b48c7b9bb235.jsonl`
- `/ll:decide-issue` - 2026-07-07T02:58:50 - `c5f1b098-4451-4d62-8201-b8676e96421a.jsonl`
- `/ll:confidence-check` - 2026-07-07T02:55:00 - `c8264ffc-c155-42c0-96e9-da2098af044c.jsonl`
- `/ll:wire-issue` - 2026-07-07T02:46:59 - `2c9198f0-463e-46ea-9701-6e36dc06ef0e.jsonl`
- `/ll:refine-issue` - 2026-07-07T02:31:10 - `a21e4561-de7f-4148-af38-1ce9ed077ffa.jsonl`

- `manual investigation` - 2026-07-07T02:17:42Z - this session
- `/ll:manage-issue bug fix BUG-2501` - 2026-07-07T04:02:14Z - `89b5a911-b033-4d3b-b31a-c2509ac470d1.jsonl` (Option B implementation: 9 test files swept, 134 `monkeypatch.chdir` sites, lint clean, full suite 13843 passed / 4 unrelated failures)

## Related

- [`project_test_suite_beachball_fix.md`](../../project_test_suite_beachball_fix.md)
  — the in-memory knowledge of the conftest cap+nice fix and the
  orphan-worker failure mode. Updated 2026-07-06 with this finding.
- BUG-2484 — trimmed nested ThreadPoolExecutor pools in
  `test_hooks_integration.py`; *not* the cause of this issue (the
  ThreadPoolExecutor pools there run inside the niced worker, so
  they're properly de-prioritized).
- BUG-2489 — fixed an event-bus test isolation leak; *not* related to
  this performance issue.

## Status

**Open** | Created: 2026-07-06 | Priority: P2
