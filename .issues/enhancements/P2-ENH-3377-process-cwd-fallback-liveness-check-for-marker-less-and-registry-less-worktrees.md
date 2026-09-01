---
id: ENH-3377
type: ENH
title: process-cwd fallback liveness check for marker-less and registry-less worktrees
priority: P2
status: done
parent: ENH-3374
depends_on:
- ENH-3376
learning_tests_required:
- psutil
confidence_score: 90
outcome_confidence: 89
score_complexity: 20
score_test_coverage: 23
score_ambiguity: 24
score_change_surface: 22
completed_at: '2026-09-01T20:24:28Z'
---

# ENH-3377: process-cwd fallback liveness check for marker-less and registry-less worktrees

## Summary

For worktrees with neither a live registry entry (ENH-3376)
nor a live in-tree marker, add a conservative fallback liveness check — a live
process whose cwd is inside the worktree path — before deleting it as
orphaned. When the check is unavailable (e.g. `psutil` not installed), skip
the worktree with a warning rather than deleting it.

## Parent Issue

Decomposed from ENH-3374: make worktree liveness marker resilient so active
worktrees cannot be classified orphaned. Covers Proposed Solution step 3 and
the third Phase-4 test bullet ("marker-less + registry-less worktree still
cleaned" — this issue changes that path to consult the fallback first, so the
regression test moves here). The parent flagged this exact mechanism
`unproven_mechanism: true` with `learning_tests_required: psutil`. That spike
has since been run and is **proven** —
`.ll/learning-tests/psutil-process-cwd-liveness-check.md` (2026-09-01) — so
the flag is cleared and the mechanism's findings are folded into Proposed
Solution step 1. No cwd-based liveness precedent exists in the codebase (the
closest prior art, `scripts/little_loops/cli/queue.py::_verify_owner_alive`,
is cmdline-identity based, not cwd based).

## Current Behavior

After ENH-3376 lands: a worktree with no live registry entry
and no live in-tree marker is deleted immediately by
`_cleanup_orphaned_worktrees()` — no further check is performed.

## Expected Behavior

Before deleting a worktree with neither a live registry entry nor a live
marker, check whether any live process has its cwd inside the worktree path.
If such a process exists, skip the worktree with a warning instead of
deleting it. The warning must name the blocking process (pid and name, e.g.
`zsh`), because an idle user shell parked in a genuinely dead worktree will
block cleanup indefinitely under this rule and the user needs enough
information to act. If the check cannot be performed (e.g. `psutil`
unavailable, or `process_iter` itself raising), also skip with a warning
rather than deleting — absence of a marker/registry is never, by itself,
treated as proof of orphanhood.

"Neither signal" is defined as *no live* signal: a worktree whose registry
entry exists but whose pid is dead or recycled (ENH-3376's `create_time`
mismatch) still reaches this fallback tier and gets the cwd sweep before
deletion. This is deliberately more conservative than ENH-3378's bash hook,
which treats a dead registry/marker pid as positive evidence and deletes
without a cwd check (bash has no `psutil` equivalent). The asymmetry is
intended: the Python path is the one that can afford the extra check, and it
covers the case where the owning `ll-loop`/`ll-parallel` process was
SIGKILLed but a dispatched host-CLI child is still running inside the
worktree.

The scan runs **once per cleanup pass**, not once per candidate worktree, and
its result is tri-state: a set of live process cwds, or "scan failed". A
plain `bool` cannot express "could not check", which is why the Program
Design signature below is not `-> bool`.

## Motivation

The registry (ENH-3376) covers worktrees created after this
feature ships. Worktrees whose registry entry was itself lost (e.g. process
crash during a non-atomic partial write, or a worktree created by
older/external tooling) still rely on marker-or-nothing. This fallback is a
last-resort safety net for that residual gap — lower priority than the
registry fix since it only matters when both prior signals are already
absent.

## Proposed Solution

1. **Mechanism (proven — no further spike needed):** the learning test
   `.ll/learning-tests/psutil-process-cwd-liveness-check.md` (`status:
   proven`, raw output in `.ll/learning-tests/raw/`) establishes the rules
   the implementation must follow. `psutil` is already a **required**
   dependency (`scripts/pyproject.toml:58`, FEAT-2930), so the "psutil
   unavailable" branch is defensive-only.
   - **macOS path aliasing** (proven): `cwd()` returns `/private/tmp/...`
     where the worktree path may read `/tmp/...`. `Path.resolve()` both
     sides and compare with `is_relative_to()`, or live processes produce
     false negatives (i.e. deletions).
   - **`AccessDenied` handling** (proven, and it corrects the parent's
     assumption): `psutil.process_iter(['pid', 'name', 'cwd'])` does **not**
     raise `AccessDenied` per process — it yields `cwd=None` for rows it
     cannot read (psutil's `ad_value` substitution). Only a direct
     `psutil.Process(pid).cwd()` raises. So the sweep loop treats
     `info['cwd'] is None` as "unknown, skip this row and continue"; there
     is no per-process `except AccessDenied` to write. Catch
     `psutil.NoSuchProcess`/`psutil.ZombieProcess` around the row anyway
     for the race where a process exits mid-iteration. Only `process_iter`
     itself raising counts as a wholesale scan failure.
   - **Cost**: iterate once per cleanup pass, collect every readable cwd
     into a set, then check each candidate worktree against that set.
     Measure the sweep on macOS during implementation; if it exceeds ~1s on
     a busy machine, note it in the log line, but do not add caching.
2. Add the fallback check to `_cleanup_orphaned_worktrees()`
   (`scripts/little_loops/parallel/orchestrator.py:321`), gated after the
   registry and marker checks from ENH-3376. Call
   `_collect_live_process_cwds()` once, lazily, the first time a candidate
   reaches this tier (so passes where every worktree is registry- or
   marker-live never pay for the sweep). For each candidate with neither
   signal, skip if any collected cwd `is_relative_to` the resolved worktree
   path.
3. If `_collect_live_process_cwds()` returns `None` (psutil import failed or
   `process_iter` raised), skip **every** candidate that reached this tier
   with one warning naming the failure, matching the "never delete when
   liveness cannot be positively excluded" principle — do not fall through
   to deletion on error.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Update `commands/cleanup-worktrees.md` (line 16, 38) and
  `docs/reference/COMMANDS.md` § `/ll:cleanup-worktrees` (lines 609-613) —
  both describe the full orphan-cleanup liveness algorithm in a single
  sentence ("skips worktrees owned by live processes..."). ENH-3376 already
  commits to editing these same lines, but scoped narrowly to mentioning the
  registry as the primary signal — its edit does not cover this issue's
  process-cwd fallback tier. Add a clause for the third tier when this issue
  lands (after ENH-3376's registry edit is in place).

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `commands/cleanup-worktrees.md` and `docs/reference/COMMANDS.md` §
  `/ll:cleanup-worktrees` — see Wiring Phase above. Re-mirror the
  host-adapter copies of `commands/cleanup-worktrees.md` in the same change
  (verbatim mirrors, no drift test — ENH-2968):
  `.qwen/commands/ll/cleanup-worktrees.md`,
  `.gemini/commands/cleanup-worktrees.toml`,
  `.kimi-code/skills/ll-cleanup-worktrees/SKILL.md`. No other doc describes
  the orphan-cleanup liveness algorithm (`docs/reference/API.md` has no
  algorithm-level prose for `ParallelOrchestrator`, only a one-row methods
  table).

### Tests

- A live process with cwd inside a marker-less, registry-less worktree ->
  worktree is skipped with a warning that names the pid and process name,
  not deleted. Use a real `subprocess.Popen(["sleep", "30"], cwd=worktree)`
  child for one end-to-end case (exercises the `/tmp` → `/private/tmp`
  resolve on macOS), and mocked `process_iter` for the rest.
- A `process_iter` row with `cwd=None` (the AccessDenied shape) is ignored
  and does not by itself cause a skip.
- The check being unavailable (`process_iter` raising; psutil import
  failing) -> every candidate at this tier is skipped with a warning, none
  deleted.
- The sweep runs at most once per `_cleanup_orphaned_worktrees()` call even
  with several candidates, and not at all when no candidate reaches the
  fallback tier.
- A marker-less, registry-less worktree with no live process anywhere inside
  it -> still deleted (this is the BUG-579 regression test, moved from the
  parent's Phase-4 test list to reflect the new gating).
- **Keep the existing suite hermetic:** every marker-less-deletion test in
  `test_orchestrator.py::TestOrphanedWorktreeCleanup` (line 544) now reaches
  the fallback tier and would otherwise run a real full-machine
  `process_iter` sweep per test. Add an autouse fixture on that class (and
  any other class that drives `_cleanup_orphaned_worktrees()` to the
  deletion path) patching
  `little_loops.parallel.orchestrator.psutil.process_iter` to return an
  empty iterator, so those tests keep asserting deletion without depending
  on what happens to be running on the host. Only this issue's own
  end-to-end `subprocess.Popen(["sleep", "30"], cwd=worktree)` case uses the
  real sweep.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-01 — based on codebase analysis:_

- Contested convention — the two existing pid-liveness checks in this codebase disagree on how to treat an ambiguous/errored probe, and this issue's own "never delete when liveness cannot be positively excluded" rule matches neither precedent exactly: `_verify_owner_alive` (`scripts/little_loops/cli/queue.py:514-539`) wraps everything in a broad `except Exception: return False` — any error, including a genuine `AccessDenied`, collapses to "not alive". The existing marker-based `os.kill(pid, 0)` check this issue's fallback sits behind (`orchestrator.py:348-363`) does the opposite: it treats `PermissionError` as "alive" (process exists, just unsignalable). Implementer should treat this issue's stricter "skip on any inability to positively exclude liveness" rule as a deliberate new synthesis, not an extension of either existing convention.
- A second existing psutil-cmdline-identity precedent exists beyond `_verify_owner_alive`: `scripts/little_loops/cli/loop/queue.py::_verify_queue_pid_identity` (~line 88-100), same shape (`psutil.Process(pid)` construction, broad exception handling), tested via `scripts/tests/test_cli_loop_queue.py` (patches `little_loops.cli.loop.queue.psutil.Process`). Neither this nor `_verify_owner_alive` does cwd-based matching or `Path.resolve()`-based comparison — both remain cmdline/create_time identity checks only.
- No shared/reusable process-liveness helper exists anywhere in this codebase (`_verify_owner_alive` is module-private and not imported elsewhere; the `os.kill(pid, 0)` probe is inlined directly in `_cleanup_orphaned_worktrees`) — there is no established convention either way on whether to extract `_process_cwd_liveness_check` into a shared utility.
- Every existing psutil test in this codebase mocks `psutil.Process` directly at the consuming module's import path (e.g. `patch("little_loops.cli.queue.psutil.Process", ...)`, `scripts/tests/test_cli_queue_run.py:609-692`); none mock `psutil.process_iter`. Since this issue's design uses `process_iter`, its test suite will need to establish a `psutil.process_iter` mocking shape not previously present in this codebase's tests.

## Program Design

### Types

- None new — consumes `psutil.Process.cwd()` (existing third-party API).

### Signatures

- `_collect_live_process_cwds() -> dict[Path, tuple[int, str]] | None` — one
  `psutil.process_iter(['pid', 'name', 'cwd'])` sweep; maps each
  readable, `Path.resolve()`d cwd to `(pid, name)` for the warning text;
  rows with `cwd=None` are skipped; `NoSuchProcess`/`ZombieProcess` per row
  are skipped; returns `None` only when psutil is unavailable or
  `process_iter` itself raises (wholesale failure)
- `_worktree_has_live_cwd(worktree_path: Path, live_cwds: LiveCwds) -> tuple[int, str] | None` — pure
  helper (`LiveCwds = dict[Path, tuple[int, str]]`): `worktree_path.resolve()` then
  `any(cwd.is_relative_to(resolved) ...)`; returns the first matching
  `(pid, name)` or `None`

(The earlier `_process_cwd_liveness_check(worktree_path) -> bool` shape was
dropped: a bool cannot distinguish "no live process found" from "could not
check", and a per-worktree signature cannot implement the single-sweep
design.)

### Call Path

`ParallelOrchestrator.run` -> `_cleanup_orphaned_worktrees` -> (registry check,
marker check — ENH-3376) -> `_collect_live_process_cwds` (once, lazily) ->
`_worktree_has_live_cwd` per candidate -> skip-with-warning or delete;
`None` from the sweep -> skip all fallback-tier candidates with one warning

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-01 — based on codebase analysis:_

- A learning-test spike for this exact mechanism already exists and is `proven`: `.ll/learning-tests/psutil-process-cwd-liveness-check.md` (dated 2026-09-01, same day as this issue). It confirms `psutil.Process(pid).cwd()` works, that `Path.resolve()` is required on both sides for the macOS `/tmp` → `/private/tmp` symlink, and that `psutil.AccessDenied`/`NoSuchProcess` are both subclasses of `psutil.Error`. _(Folded into Proposed Solution step 1 and the frontmatter on 2026-09-01; `unproven_mechanism` cleared.)_
- Correction to the stated mechanism: the spike's raw output (`.ll/learning-tests/raw/psutil-process-cwd-liveness-check.txt`, `CLAIM3-refined`) found that `psutil.process_iter(['pid', 'cwd'])` does **not** raise `AccessDenied` per-process during iteration — it silently returns `cwd=None` for those rows (via psutil's internal `ad_value` substitution). Only a *direct* `psutil.Process(pid).cwd()` call raises `AccessDenied`. The implementation must treat `cwd is None` as "cannot determine, skip this row", not catch an exception that `process_iter` never raises. _(Now reflected in Proposed Solution step 1 and the Signatures.)_

## Scope Boundaries

- The registry itself (write/remove/consult) is out of scope — that's
  ENH-3376, a hard dependency of this issue (this issue's fallback only fires
  when ENH-3376's checks find no live entry).
- `hooks/scripts/session-cleanup.sh` hardening is out of scope — bash has no
  `psutil` equivalent; that path is handled independently in ENH-3378.
- An `lsof`-based fallback is out of scope; the spike found `psutil`
  suitable.
- Caching or throttling the process sweep across passes is out of scope.
- Liveness checking for worktrees outside `_cleanup_orphaned_worktrees()`'s
  existing candidate enumeration is out of scope.

## Files to Modify

- `scripts/little_loops/parallel/orchestrator.py` (`_cleanup_orphaned_worktrees`)

## Dependent Files / Precedent

- `scripts/little_loops/cli/queue.py::_verify_owner_alive` and
  `scripts/tests/test_cli_queue_run.py:609-692` — closest existing shape
  (`patch("<module>.psutil.Process", ...)`) for mocking a `psutil`-based
  liveness check in tests, though it checks cmdline identity, not cwd.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/parallel.py:224` — `main_parallel`'s
  `--cleanup-orphans` CLI handler calls `_cleanup_orphaned_worktrees()`
  directly (a second call path alongside the auto-invocation from
  `ParallelOrchestrator.run()`). No edit needed — the fallback check is gated
  inside `_cleanup_orphaned_worktrees()` itself, so both callers get it for
  free. Confirms `scripts/tests/test_cli.py:548,568,592`
  (`test_main_parallel_cleanup_orphans_mode*`) already mock
  `_cleanup_orphaned_worktrees` at the boundary and are unaffected.
- No shared process-liveness utility module exists anywhere in this codebase
  (confirmed repo-wide) — `_collect_live_process_cwds` /
  `_worktree_has_live_cwd` have no existing home to be extracted into; they
  are net-new module-level helpers in `orchestrator.py`.
- Mocking `psutil.process_iter` in tests has no existing precedent to copy
  verbatim (only `psutil.Process` mocking precedent exists, at
  `<module>.psutil.Process`) — the new test suite establishes
  `patch("little_loops.parallel.orchestrator.psutil.process_iter", ...)` as a
  new shape.

## Impact

Closes the residual liveness gap for worktrees whose registry entry is itself
missing or lost, without weakening ENH-3376's registry-based
fix (which already closes the primary BUG-3373 mechanism on its own).

## Related Key Documentation

- `scripts/little_loops/parallel/orchestrator.py` (orphan detection)
- `scripts/little_loops/cli/queue.py` (`_verify_owner_alive`, closest psutil precedent)

---

## Resolution

- **Action**: improve
- **Completed**: 2026-09-01
- **Status**: Completed

### Changes Made
- `scripts/little_loops/parallel/orchestrator.py`: added `_collect_live_process_cwds()` / `_worktree_has_live_cwd()` module-level helpers and wired the process-cwd fallback tier into `_cleanup_orphaned_worktrees()`, gated after the ENH-3376 registry and in-tree marker checks. A scan failure (or psutil unavailable) skips every candidate reaching the tier with a warning rather than falling through to deletion.
- `scripts/tests/test_orchestrator.py`: added `TestProcessCwdFallbackLiveness` (real-subprocess e2e case, `cwd=None` handling, scan-failure skip, once-per-pass sweep, no-sweep-when-unneeded, and the moved BUG-579 regression test); added an autouse `psutil.process_iter` patch to `TestOrphanedWorktreeCleanup` and `TestRegistryBasedOrphanCleanup` so their existing deletion-path tests stay hermetic.
- `commands/cleanup-worktrees.md`, `docs/reference/COMMANDS.md`, and the host-adapter mirrors (`.qwen/commands/ll/cleanup-worktrees.md`, `.gemini/commands/cleanup-worktrees.toml`, `.kimi-code/skills/ll-cleanup-worktrees/SKILL.md`): documented the third liveness tier.

### Verification Results
- Tests: PASS (`python -m pytest scripts/tests/` — 22321 passed, 2 pre-existing unrelated failures confirmed present on `main` before this change, 42 skipped)
- Lint: PASS
- Types: PASS

## Status

**Open** | Created: 2026-09-01 | Priority: P2


## Session Log
- `/ll:manage-issue` - 2026-09-01T20:24:11 - `7ae98572-e410-45fd-a4d7-76b25bbe5586.jsonl`
- `/ll:ready-issue` - 2026-09-01T20:12:56 - `31bbcd29-be68-46cb-8e1b-72702886c96f.jsonl`
- Pre-implementation review (2nd pass) - 2026-09-01 - made explicit that dead/recycled registry pids still reach the cwd sweep (intended asymmetry vs ENH-3378's hook), added the autouse `process_iter` patch for the existing `TestOrphanedWorktreeCleanup` suite, added the command-doc mirror obligation.
- `/ll:confidence-check` - 2026-09-01T19:10:49 - `9df9cefa-f639-494c-867c-39fd1ac3ff91.jsonl`
- Pre-implementation review - 2026-09-01 - cleared `unproven_mechanism` (spike proven), replaced the `-> bool` signature with a tri-state single-sweep design, folded the `cwd=None` AccessDenied correction into step 1, required the skip warning to name the blocking pid/process.
- `/ll:wire-issue` - 2026-09-01T18:47:09 - `79009b58-7363-45db-90f1-4e47ed1282ba.jsonl`
- `/ll:refine-issue` - 2026-09-01T18:27:46 - `f0c0abcb-9bb0-4011-99a7-b965b2d4e8f5.jsonl`
- `/ll:format-issue` - 2026-09-01T18:11:45 - `a022c67c-3828-4e2e-96d1-3bcdf7adfc60.jsonl`
- `/ll:issue-size-review` - 2026-09-01T15:20:22 - `9c0fcbc0-a053-4d0e-b64f-70b69247e895.jsonl`
