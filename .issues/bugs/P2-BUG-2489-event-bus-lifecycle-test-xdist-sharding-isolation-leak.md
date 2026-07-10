---
id: BUG-2489
title: Event-bus lifecycle test fails under some xdist shardings (test-isolation leak)
type: BUG
priority: P2
status: done
discovered_date: '2026-07-05'
discovered_by: capture-issue
captured_at: '2026-07-05T23:16:24Z'
labels:
- testing
- pytest
- flaky
- test-isolation
decision_needed: false
confidence_score: 98
outcome_confidence: 84
score_complexity: 19
score_test_coverage: 22
score_ambiguity: 23
score_change_surface: 20
completed_at: '2026-07-06T02:43:05Z'
relates_to:
- BUG-2586
---

# BUG-2489: Event-bus lifecycle test fails under some xdist shardings (test-isolation leak)

## Summary

`scripts/tests/test_issue_lifecycle.py::TestEventBusEmission::test_complete_issue_lifecycle_emits_event`
fails **nondeterministically** in a full-suite run depending on how pytest-xdist
shards tests across workers. It **passes 100% in isolation** (3/3) and under
serial `-n 0`. Because the full suite is the project's literal CI gate
(`python -m pytest scripts/tests/`), an intermittent failure here poisons the
green-suite signal developers rely on.

The failure was surfaced (not caused) while tuning the xdist worker count to fix
the macOS "beachball" freeze: the suite passed at 10 workers and at 4 workers,
then this test failed once at 7 workers. Changing the worker count only reshards
which tests co-locate in a worker — so a different worker layout exposes a
pre-existing cross-test state leak.

## Root Cause

Not yet fully isolated — to be pinned during the fix. The signature is a classic
**test-isolation leak**: the test constructs its **own** local `EventBus()` (see
`test_issue_lifecycle.py:1320` `TestEventBusEmission`), so the defect is not in
`little_loops.events.EventBus` itself. The likely culprits, in order:

- An **unrestored patch / monkeypatch** from another test file that lands in the
  same xdist worker (e.g. a `patch("subprocess.run", ...)` or a module attribute
  left mutated), altering `close_issue` / `complete_issue` behavior or the
  emitted payload.
- A **frozen/fixed-time or env leak**: the sibling test
  `test_close_issue_emits_event` asserts `event["captured_at"] == "2026-05-20T10:00:00Z"`,
  implying a pinned timestamp source that another test could perturb.
- A leaked global consumed by `state.py:106-107` (`self._event_bus.emit(...)`)
  or the lifecycle helpers.

Confirm by reproducing with a fixed shard layout, e.g.
`pytest scripts/tests/ -p xdist -n 7` repeatedly, or
`pytest --dist=loadfile ...` vs `--dist=load ...`, and by bisecting which sibling
test file, when co-located, triggers the failure.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis (findings verified by
direct code inspection; the three hypotheses above were investigated and **ruled
out**):_

The failure is **not** a cross-test sibling leak, and **not** in
`little_loops.events.EventBus`. `EventBus.__init__`
(`scripts/little_loops/events.py:77-79`) allocates fresh per-instance
`_observers`/`_transports` lists — there is no module-level singleton or shared
registry a sibling `EventBus()` could pollute. The asserted `captured_at ==
"2026-05-20T10:00:00Z"` is **not** a mocked clock either: it is read verbatim
from the fixture's frontmatter (`sample_issue_info`,
`test_issue_lifecycle.py:53-67`) via
`parse_frontmatter(...).get("captured_at")` at `issue_lifecycle.py:722-724`.
No `freezegun`/`freeze_time` fixture exists anywhere in `scripts/tests/`.

**Verified root cause — an unmocked real-filesystem probe racing the live host
process, unique to this one lifecycle function:**

1. `complete_issue_lifecycle()` is the **only** lifecycle emitter that calls
   `append_session_log_entry(original_path, "ll-auto")` — at
   `scripts/little_loops/issue_lifecycle.py:734` (confirmed: single call site in
   the module). Its siblings `close_issue()` (593-689) and `defer_issue()`
   (794+) do **not** — which is exactly why only
   `test_complete_issue_lifecycle_emits_event` flakes and the other
   `TestEventBusEmission` tests never do.
2. That call runs with `session_jsonl=None`, so it invokes
   `get_current_session_jsonl()` (`session_log.py:122-123`) →
   `get_project_folder(None)` (`user_messages.py:356-398`), which falls back to
   the **real** `Path.cwd()` and `Path.home() / ".claude" / "projects" /
   <encoded-cwd>` — the live Claude Code session-log directory for this checkout,
   **not** `tmp_path`. No conftest fixture redirects `get_project_folder` /
   `Path.home` / `Path.cwd` (grep of `scripts/tests/conftest.py` confirms).
3. `get_current_session_jsonl` (`session_log.py:79-83`) does a glob-then-stat
   with **no exception guard**: `jsonl_files = [... project_folder.glob("*.jsonl")
   ...]` then `max(jsonl_files, key=lambda f: f.stat().st_mtime)`. When the live
   host process rotates/deletes a listed `.jsonl` between the `glob()` and the
   `.stat()`, `FileNotFoundError` is raised here, uncaught.
4. That exception propagates into `complete_issue_lifecycle`'s broad
   `except Exception as e` (`issue_lifecycle.py:760`), which logs and returns
   `False` **before** reaching `event_bus.emit(...)` at line 748 — failing both
   `assert result is True` and `assert len(received) == 1`
   (`test_issue_lifecycle.py:1386-1387`).

**Implication for the xdist framing:** the mechanism is a race against an
*external* process (the live host writing session JSONL), not xdist worker
co-location. Higher worker counts widen the TOCTOU window under load and make it
surface more often, which is why it correlated loosely with `-n 7`, yet passes in
isolation (small window, low concurrent load). This is also a latent production
bug: real `ll-auto` runs hit the same unguarded `.stat()` path.

_Prior art for the fix:_ `scripts/tests/test_session_log.py` (e.g.
`TestGetCurrentSessionJsonl` L30, `TestAppendSessionLogEntry` L69) already patches
`little_loops.session_log.get_project_folder` (or passes an explicit
`session_jsonl=`) per-call — `TestEventBusEmission` does not. Existing autouse
isolation fixtures in `conftest.py` (`_isolate_history_db*` L505/L519,
`_restore_cmd_run_env_vars` L597) are the structural template for a suite-wide
session-log isolation fixture.

## Current Behavior

Full-suite run intermittently reports:
```
FAILED scripts/tests/test_issue_lifecycle.py::TestEventBusEmission::test_complete_issue_lifecycle_emits_event
1 failed, 13738 passed, 27 skipped
```
The same test passes deterministically when run alone or serially.

## Expected Behavior

The test passes deterministically regardless of xdist worker count or which
tests share its worker. Each test fully sets up and tears down its own state
(patches restored, time/env pinned locally) with no dependence on execution
order or co-location.

## Motivation

The full suite is the sole CI gate for this project (no hosted CI, per
`.claude/CLAUDE.md`). A sharding-dependent flake means a clean branch can go
red purely from a worker-count change, eroding trust in the gate and forcing
re-runs. Fixing the leak also hardens the suite against future `-n` retuning
(the beachball fix now defaults to `cpus // 2` workers, so shard layouts will
differ from historical `-n logical`).

## Integration Map

_Added by `/ll:refine-issue` — based on codebase analysis:_

### Files to Modify (candidates — depends on chosen option below)
- `scripts/little_loops/session_log.py:79-83` — `get_current_session_jsonl()`
  glob-then-stat; wrap `.stat()` in a guard that skips vanished files (production
  hardening).
- `scripts/tests/conftest.py` — add an autouse fixture redirecting
  `get_project_folder` / session-log resolution to `tmp_path` (test isolation),
  alongside existing `_isolate_history_db*` (L505/L519) and
  `_restore_cmd_run_env_vars` (L597).
- `scripts/tests/test_issue_lifecycle.py:1361-1393` —
  `test_complete_issue_lifecycle_emits_event`; optionally patch
  `little_loops.session_log.get_project_folder` per-test if not solved suite-wide.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/ctx_stats.py:199` — `_compute_cache_rate_from_jsonl()`
  contains a **byte-for-byte duplicate** of the unguarded glob-then-stat
  (`max(jsonl_files, key=lambda f: f.stat().st_mtime)`, ctx_stats.py:195-199)
  that **inlines** the logic rather than calling `get_current_session_jsonl`.
  Guarding `session_log.py:79-83` does **not** cover this path — `ll-ctx-stats`
  hits the identical TOCTOU race against the live host session dir. Apply the same
  vanished-file guard here for consistency (the decision rationale, line 262, flags
  this duplication; wiring confirms `ctx_stats.py` is a real second site, but
  `cli/logs.py` is **not** — its per-file `open()` is already wrapped in
  `except OSError: continue`, so it is not a duplicate of the bug shape). [Agent 1+2 finding]

### Dependent / Related Code (Callers)
- `scripts/little_loops/issue_lifecycle.py:734` — the sole
  `append_session_log_entry(...)` call inside `complete_issue_lifecycle`.
- `scripts/little_loops/session_log.py:122-123` — `append_session_log_entry` →
  `get_current_session_jsonl()`.
- `scripts/little_loops/user_messages.py:356-398` — `get_project_folder` /
  `_get_claude_project_folder` (resolves the real `~/.claude/projects/...` dir).

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/fsm/executor.py:1407` — **second unguarded caller** of
  `get_current_session_jsonl()` (imported at executor.py:61), in the
  `action_mode == "prompt"` branch that builds `payload["session_jsonl"]`. Not
  wrapped in a local try/except, so it shares the exact TOCTOU raise fixed by
  Option B; hardening `get_current_session_jsonl` fixes this call site for free
  (no local change needed) — confirms the guard benefits a real FSM path, not just
  `ll-auto`. [Agent 1+2 finding]
- `scripts/little_loops/session_log.py:99` — `get_current_session_id()` calls
  `get_current_session_jsonl()` and is itself **not** try/except-wrapped, so it
  currently re-raises. Hardening the callee resolves this too. [Agent 2 finding]
- `scripts/little_loops/issue_lifecycle.py:33-38` — `_session_id_or_none()`
  already wraps `get_current_session_id()` in `try/except Exception: return None`
  (the *safe* pattern); the flaking call at line 734 is the one that isn't
  independently guarded. [Agent 2 finding]

**Fixture patch-target correction (Option A/C) — important:** `get_project_folder`
is defined once in `user_messages.py` but imported **by reference** into 6 module
namespaces (`session_log.py:14`, `cli/session.py:52`, `cli/logs.py:26`,
`cli/ctx_stats.py:34`, `cli/messages.py`, `hooks/session_start.py:138`).
Monkeypatching only `little_loops.session_log.get_project_folder` (as the issue
text loosely suggests) will **not** isolate the other five modules from the real
`~/.claude/projects/...` dir. The suite-wide fixture should instead patch the single
true choke point they all share — `pathlib.Path.home` (via
`_get_claude_project_folder`, `user_messages.py:397`) — mirroring the
`_guard_real_history_db` design (which patches `sqlite3.connect`, not every DB call
site). Strong existing precedent: `test_session_log.py:285`, `test_ll_logs.py`
(50+ `Path.home` patch sites), `test_cli.py:2986/3001/3016`. [Agent 2+3 finding]

### Similar Patterns
- `scripts/tests/test_session_log.py:30,69` — correct per-call
  `patch("...get_project_folder", ...)` idiom to model after.
- `scripts/tests/conftest.py:537-577` — `_guard_real_history_db` choke-point
  guard: template for an optional "assert no test touches the real session-log
  dir" regression guard.

### Tests
- `scripts/tests/test_issue_lifecycle.py::TestEventBusEmission` — the affected
  class (8 tests; only `test_complete_issue_lifecycle_emits_event` flakes).
- New: a regression test that `complete_issue_lifecycle` still emits
  `issue.completed` when `get_current_session_jsonl` would raise (simulate a
  vanished-file race), asserting the emit is not swallowed.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_session_log.py::TestSessionLogHostAware`
  (`test_session_log.py:269-328`: `test_get_current_session_jsonl_auto_detects_codex`,
  `test_get_current_session_jsonl_returns_none_for_missing_codex_dir`,
  `test_append_session_log_entry_works_with_codex_host`) — **may break** under an
  *unconditional* suite-wide autouse `Path.home`/`get_project_folder` override:
  these three tests deliberately exercise the **real** resolution chain via
  `monkeypatch.setattr(Path, "home", ...)` + `LL_HOOK_HOST=codex`. The new fixture
  must **compose** with (yield to) per-test `Path.home`/env overrides, or opt these
  out — precedent for a non-autouse, explicitly-applied fixture is
  `stable_snapshot_env` (`conftest.py:82-96`). [Agent 3 finding]
- New regression test — no existing vanished-file/TOCTOU analog exists in
  `scripts/tests/` (grep of `FileNotFoundError` / `side_effect` near glob/stat
  found none). Model the new test after `test_append_uses_os_replace`
  (`test_session_log.py:157-173`): patch `Path.stat` with a `side_effect` that
  raises `FileNotFoundError` for one glob-returned file and assert
  `get_current_session_jsonl()` returns the surviving most-recent file (or `None`)
  instead of propagating. [Agent 3 finding]
- If `ctx_stats.py:199` is also hardened (see Files to Modify), add a parallel
  vanished-file regression test for `_compute_cache_rate_from_jsonl` in
  `scripts/tests/test_cli_ctx_stats.py` (existing coverage patches
  `little_loops.cli.ctx_stats.get_project_folder`). [Agent 1+3 finding]
- Per-call `with patch("little_loops.session_log.get_project_folder", ...)` blocks
  in `TestGetCurrentSessionJsonl`/`TestAppendSessionLogEntry` are **not** expected
  to break — `unittest.mock.patch` save/restores whatever the autouse fixture set,
  so nesting composes. Verify the new fixture actually redirects the whole suite
  (net-new guard; there is no existing `get_project_folder` choke-point test to
  reuse, unlike `_guard_real_history_db` for the DB case). [Agent 3 finding]

### Documentation

_Wiring pass added by `/ll:wire-issue` — verified, no doc edits required:_
- `docs/reference/API.md` (`### get_current_session_jsonl`, ~L6056-6067) already
  documents the contract as "Returns: `Path` ... or `None` if not found" with **no**
  `FileNotFoundError` caveat. The Option B guard (return `None`/skip vanished files
  instead of raising) brings the implementation **into conformance** with the
  existing doc — no doc change needed. [Agent 2 finding]
- `docs/ARCHITECTURE.md` § "Session Log Auto-Linking" (~L1254-1270) — the
  `issue-completion-log.sh` hook path supplies `session_jsonl` explicitly and
  bypasses `get_current_session_jsonl()` auto-detection, so it is unaffected. No
  change needed. [Agent 2 finding]
- No `docs/` file mentions `_isolate_history_db` / `_guard_real_history_db` — the
  isolation-fixture convention is conftest-internal, so adding the new fixture
  couples to no external doc. [Agent 2 finding]

## Proposed Solution

1. Reproduce deterministically: run the full suite (or the offending file plus
   suspected siblings) under a fixed shard layout until it fails; capture the
   co-located file set.
2. Bisect to the leaking sibling test/file (`-p no:randomly` if applicable;
   `--dist=loadfile` groups a file onto one worker, which may make the leak
   reproducible or disappear — a useful signal).
3. Fix the leak at its source — prefer an `autouse` teardown / `monkeypatch`
   (auto-reverted) over manual `patch()` in the offending test, and pin any
   time source via a fixture rather than a module global.
4. Add a regression guard: assert the relevant global/module state is clean at
   the offending test's entry, or mark the emission tests to run isolated if a
   shared resource is genuinely required.

### Codebase Research Findings

_Added by `/ll:refine-issue` — steps 1–2 above are superseded by the verified
root cause (no bisection needed; the offending call is pinned). Concrete options:_

**Option A — Test isolation only (narrowest).** Add a `conftest.py` autouse
fixture that redirects `little_loops.session_log.get_project_folder` (or the
session-log directory) to `tmp_path` for the suite, so
`append_session_log_entry` never touches the real `~/.claude/projects/...` dir.
Fixes the flake; leaves the production TOCTOU intact.

**Option B — Production hardening only.** Guard the glob-then-stat in
`get_current_session_jsonl` (`session_log.py:83`) so a file that vanishes between
`glob()` and `.stat()` is skipped rather than raising (e.g. filter with a
`try/except FileNotFoundError` around `f.stat()`, or catch and drop stale
entries). Fixes both the test flake **and** the latent real-`ll-auto` race. Add a
regression test simulating the vanished-file race.

**Option C — Both (recommended).** Harden `get_current_session_jsonl` (Option B,
the real bug) *and* add the suite-wide session-log isolation fixture (Option A, so
no test ever depends on the host's live session dir). Belt-and-suspenders; matches
the project's existing `_isolate_history_db*` + `_guard_real_history_db`
choke-point convention.

> **Selected:** Option C — Both — directly reuses the BUG-1995 isolate+guard
> choke-point convention (`conftest.py:505-577`) and fixes the real production
> TOCTOU as well as the test flake.

Note: Options B and C require editing production code
(`scripts/little_loops/session_log.py`), so this cannot be resolved as a
test-only change if the latent production race is to be fixed.

### Wiring Phase (added by `/ll:wire-issue`)

_Touchpoints identified by wiring analysis that must be folded into the Option C
implementation:_

1. Guard the glob-then-stat in `session_log.py:79-83` (Option B) — this
   automatically fixes the **second** production caller
   `fsm/executor.py:1407` and `get_current_session_id()` (`session_log.py:99`),
   both of which call the hardened function unguarded.
2. Apply the **same** vanished-file guard to the byte-for-byte duplicate at
   `cli/ctx_stats.py:195-199` (`_compute_cache_rate_from_jsonl`) — it inlines the
   idiom instead of calling `get_current_session_jsonl`, so step 1 does not cover
   it; `ll-ctx-stats` shares the identical TOCTOU race. (Skip `cli/logs.py` — its
   per-file `open()` is already `except OSError`-guarded.)
3. For the suite-wide isolation fixture (Option A), patch **`pathlib.Path.home`**,
   not `little_loops.session_log.get_project_folder` — the latter is imported
   by-reference into 6 modules and would leave 5 of them touching the real host
   dir. Follow the `_guard_real_history_db` single-choke-point shape
   (`conftest.py:537-577`).
4. Make the new fixture **compose** with per-test `Path.home`/`LL_HOOK_HOST`
   overrides so the three `TestSessionLogHostAware` tests
   (`test_session_log.py:269-328`) that exercise the real resolution chain do not
   break — or make it explicitly-applied (non-autouse) like `stable_snapshot_env`.
5. Add the vanished-file regression test(s) modeled on `test_append_uses_os_replace`
   (`test_session_log.py:157-173`): one for `get_current_session_jsonl`, and — if
   step 2 is done — one for `_compute_cache_rate_from_jsonl` in
   `test_cli_ctx_stats.py`.
6. No documentation edits required (verified — see Integration Map §
   Documentation).

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-07-05.

**Selected**: Option C — Both (harden `get_current_session_jsonl` + suite-wide
session-log isolation fixture).

**Reasoning**: Option C scores highest (10/12) because it is the only option that
fixes the *verified root cause* — the unguarded glob-then-stat TOCTOU at
`session_log.py:79-83`, which is a latent production bug hitting real `ll-auto`
runs — while also matching the project's own established remediation template for
this exact "test touches real filesystem state" class: the BUG-1995
`_isolate_history_db*` isolation fixtures paired with the `_guard_real_history_db`
choke-point assertion (`conftest.py:505-577`). Options A and B each fix only half
the problem (A leaves the production race live; B leaves the suite reading the real
`~/.claude/projects/...` dir with no guard against future leaks), so the modestly
larger surface of C buys both a real bug fix and a regression guard.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| A — Test isolation only | 2/3 | 3/3 | 2/3 | 2/3 | 9/12 |
| B — Production hardening only | 1/3 | 3/3 | 2/3 | 2/3 | 8/12 |
| C — Both (recommended) | 3/3 | 1/3 | 3/3 | 3/3 | 10/12 |

**Key evidence**:
- Option A: autouse-fixture shape is copy-paste from `_isolate_history_db*`
  (`conftest.py:505-534`) and `get_project_folder` is already patched in 5 call
  sites (`test_session_log.py:23,27,37,48,55`), but per the issue's own root-cause
  research it leaves the confirmed production TOCTOU at `session_log.py:79-83`
  unfixed.
- Option B: fixes the real race at a single choke point benefiting all 3 callers
  (`session_log.py:99`, `session_log.py:123`, `fsm/executor.py:1379`), but there
  is no existing TOCTOU-guard idiom to reuse (reuse score 1), the identical
  unguarded pattern is duplicated in `ctx_stats.py`/`cli/logs.py`, and it bypasses
  the `_guard_real_history_db` convention — the suite still reads real host state.
- Option C: directly mirrors the documented BUG-1995 isolate+guard convention
  (`conftest.py:505-577`); the only piece with no literal precedent is the
  `FileNotFoundError` glob-then-stat guard, which follows the shape of
  `_guard_real_history_db` rather than reusing its code.

## Steps to Reproduce

1. `python -m pytest scripts/tests/ -q` on a 14-core host (default cap now 7
   workers via `tests/conftest.py`).
2. Observe intermittent failure of
   `TestEventBusEmission::test_complete_issue_lifecycle_emits_event`.
3. Confirm it passes in isolation: `pytest ".../test_complete_issue_lifecycle_emits_event" -n 0` → passes 3/3.

## Impact

- **Priority**: P2 — intermittently red CI gate; no production/runtime impact.
- **Effort**: Small–Medium — confined to test setup/teardown once the leaking
  sibling is identified; no production code expected to change.
- **Risk**: Low.
- **Breaking Change**: No.

## Related

- Follows the beachball fix (worker cap `cpus // 2` + `os.nice` renice in
  `scripts/tests/conftest.py`) that changed the default shard layout and exposed
  this flake.
- Related test-isolation work: BUG-1995 (pytest opened the real history DB).

## Session Log
- `ll-auto` - 2026-07-06T02:43:05 - `6569d1c1-3096-44a0-8cd8-af9267063742.jsonl`
- `/ll:confidence-check` - 2026-07-06T02:30:07 - `b5480c51-410f-42f8-982c-72e64a202d8f.jsonl`
- `/ll:wire-issue` - 2026-07-06T00:21:22 - `598c77c5-730f-4dd7-b84a-7f8aa9f712de.jsonl`
- `/ll:decide-issue` - 2026-07-06T00:11:45 - `b4be5a1b-62e5-48f9-aaf8-49197ad39072.jsonl`
- `/ll:refine-issue` - 2026-07-05T23:24:57 - `6b27fe05-3797-415c-84da-adca0ebea01e.jsonl`
- `/ll:capture-issue` - 2026-07-05T23:16:24Z - `2245c1db-2bf4-4e02-8b9e-f6247f6790e2.jsonl`

## Status

**Open** | Created: 2026-07-05 | Priority: P2


---

## Resolution

- **Action**: fix
- **Completed**: 2026-07-05
- **Status**: Completed (automated fallback)
- **Implementation**: Command exited early but issue was addressed


### Files Changed
- See git history for details

### Verification Results
- Automated verification passed

### Commits
- See git log for details
