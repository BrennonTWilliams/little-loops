---
id: BUG-2526
title: "`ll-auto --only` race in autodev implementation phase \u2014 concurrent runs\
  \ corrupt `.auto-manage-state.json` and git state"
type: BUG
status: done
priority: P2
captured_at: '2026-07-07T18:27:32Z'
completed_at: 2026-07-07 20:00:22+00:00
discovered_date: '2026-07-07'
discovered_by: capture-issue
labels:
- bug
- autodev
- ll-auto
- ll-loop
- concurrency
decision_needed: false
learning_tests_required:
- fcntl
confidence_score: 95
outcome_confidence: 79
score_complexity: 17
score_test_coverage: 19
score_ambiguity: 22
score_change_surface: 21
---

# BUG-2526: `ll-auto --only` race in autodev implementation phase — concurrent runs corrupt `.auto-manage-state.json` and git state

## Summary

When two `ll-loop run autodev` invocations (or one autodev run alongside a terminal-launched `ll-auto`) reach the `implement_current` state concurrently, both shell out to `ll-auto --only <issue>` on the **main working tree** with no inter-process coordination. Both processes read and write `.auto-manage-state.json` (atomic rename prevents corruption, but does not prevent logical races on `processed_count`, `--resume`, and concurrent git commits), and both invoke `git commit` / `git push` against the same ref.

FEAT-1789 made autodev.yaml's scope `["${context.run_dir}"]` specifically to **allow** concurrent refinement-phase runs, but explicitly punted on implementation-phase coordination unless the user passes `--worktree` at invocation. Default invocation (no `--worktree`) has no protection at the implementation-phase boundary, and `ll-auto` itself acquires no cross-process lock.

## Current Behavior

- Two concurrent `ll-loop run autodev` instances (e.g., `autodev BUG-031` and `autodev ENH-1699`) pass `LockManager.acquire()` because their `${context.run_dir}` scopes are disjoint siblings under `.loops/runs/`.
- Both instances reach `implement_current` and shell to `ll-auto --only ${captured.input.output}` on the main working tree.
- Both `ll-auto --only` processes load `.auto-manage-state.json`, both increment `processed_count`, both mark the issue as in-flight, both run refinement + implementation sub-skills, both commit to git, both write state back. The atomic `os.replace` in `StateManager.save` (`scripts/little_loops/state.py:134`) prevents filesystem corruption but not logical races.
- The same hazard exists when a developer runs `ll-auto` from a terminal while an FSM-driven autodev is in implementation — `ll-auto` has no PID-file or `fcntl.flock` on the state file or git index.

## Expected Behavior

Only one `ll-auto` may execute against `.auto-manage-state.json` and the main working tree at a time. A second invocation should either (a) wait, (b) refuse with a clear error, or (c) be redirected to `--worktree` isolation automatically. The chosen behavior must also cover the terminal-launched `ll-auto` vs FSM-driven `ll-auto --only` case.

## Motivation

Concurrent runs can:
- Double-process an issue (both `ll-auto` instances mark it as their current; whichever commits second wins on the issue body but the first's state lives on in `.auto-manage-state.json`).
- Lose completion history — `--resume` after either finishes may resurrect work the other just completed (since both writes use `os.replace` and the later write wins entirely).
- Tangle git history — interleaved `git commit`s in the same branch leave the working tree in a state that requires `git rebase` or `git reset` to recover.
- Incur token-cost waste — each duplicate run spends full LLM budget refining and implementing the issue a second time.

## Steps to Reproduce

1. Start a long-running autodev session: `ll-loop run autodev BUG-031` (no `--worktree` flag).
2. While that session is processing issue BUG-031 (or while another autodev is, on a disjoint issue set), start a second concurrent invocation: `ll-loop run autodev ENH-1699,ENH-1700`.
3. Wait for both to reach their `implement_current` state (the shell-out to `ll-auto --only`).
4. Observe: both `ll-auto --only` processes run simultaneously. Both update `.auto-manage-state.json`. Both commit to git on the main branch.
5. Observe: terminal-launched `ll-auto --resume` started mid-flight sees a partial / inconsistent `.auto-manage-state.json` (one write clobbers the other).

Reproduction requires no shell errors and no crash; the failure mode is silent logical corruption rather than a visible error.

## Root Cause

- **File**: `scripts/little_loops/loops/autodev.yaml`
- **Anchor**: `implement_current` state (line 362; bare shell-out at line 394) — shells to `ll-auto --only "$CURRENT" $SKIP_FLAG` on the main working tree.
- **File**: `scripts/little_loops/cli/auto.py`
- **Anchor**: `main_auto()` → `AutoManager.run()` (`scripts/little_loops/issue_manager.py:1282`) — never acquires a cross-process lock; `StateManager.save()` (`state.py:134`) is atomic at the file level but has no flock / PID guard; the finally-block at line 1332 calls `self.state_manager.cleanup()` unconditionally, which can delete the state file a concurrent process is still writing.
- **Cause**: `LockManager` (`scripts/little_loops/fsm/concurrency.py:130` for `acquire()`; class definition at line 76) protects FSM-vs-FSM scope overlaps but is scoped to filesystem paths under `${context.run_dir}` — `ll-auto --only` shells out from inside `implement_current` and runs against `.` (the main working tree). FEAT-1789 made this worse intentionally to allow concurrent refinement, but did not plug the implementation-phase hole in the non-`--worktree` default.

### Codebase Research Findings (Root Cause)

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Adjacent race that Option A does NOT close.** `AutoManager.cleanup()` at `scripts/little_loops/issue_manager.py:1332` is invoked unconditionally on every clean shutdown via `if not self._shutdown_requested: self.state_manager.cleanup()` inside a `finally`-equivalent path. `StateManager.cleanup()` removes `.auto-manage-state.json`. **Two concurrent `ll-auto --only` processes that both reach shutdown will each delete the state file the other is still updating.** This is independent of the FSM-vs-FSM lock layer that Option A plugs; it sits inside `ll-auto` itself. Option A closes the inter-FSM race at `acquire()` time but if a `ll-auto` invocation escapes Option A's protection (e.g., a future loop that does *not* opt into `singleton`), the cleanup race remains. Out of scope for this issue but worth filing as a follow-on BUG. Mention in the CHANGELOG entry; do **not** conflate with this issue's fix.

**Verification of FEAT-1789's documented deferral.** FEAT-1789's decision rationale (`.issues/features/P3-FEAT-1789-parallel-safe-autodev-disjoint-issues.md:162-167`) reads (verbatim): "Refinement phases can run in parallel; implementation phase retains `["."]` or uses `--worktree`." The "implementation phase retains `["."]`" explicitly admits the implementation-phase coordination gap. BUG-2526 is the race FEAT-1789 punted on — the gap was identified in 2026-05-31 and left for a follow-on, which this issue now picks up.

**`autodev.yaml` `implement_current` exact location.** The state declaration is at `autodev.yaml:362`, the bare shell-out `ll-auto --only "$CURRENT" $SKIP_FLAG` is at `autodev.yaml:394` (NOT "around line 290" as the Root Cause section above states). The in-flight staleness handling for *resumed* sessions (`autodev-inflight` repair) is at lines 374-387 (BUG-1870) — it does not protect against a *parallel* live session, only against a crashed prior session.

**`_get_ancestry` carve-out must be co-extended (concurrency.py:223-229).** The current `find_conflict` skips ancestor PIDs to permit nested `ll-loop run` invocations. The Option A singleton predicate must replicate this carve-out, otherwise a parent loop spawning nested `ll-loop run autodev` self-conflicts on singleton. The carve-out pattern at lines 223-228 (`if lock.pid in self._get_ancestry(): logger.debug(...); continue`) is the model — clone it after the singleton-overlap check, not before (so ancestor locks do not falsely trip the singleton filter).

**No `O_CREAT | O_EXCL` PID-file pattern exists anywhere.** Greps across `scripts/` confirm three distinct `fcntl.flock` usages (`file_utils.py:60-96`, `concurrency.py:155-156`, `fsm/rate_limit_circuit.py:44-75`) but none use atomic-create. Option B would have introduced the project's first such usage — out of step with the existing convention, which is one of the structural reasons Option A scores higher on reuse.

## Proposed Solution

Two viable approaches (pick one; the second is recommended for its smaller surface):

**Option A — `singleton: true` on autodev.yaml** (recommended)

> **Selected:** Option A — `singleton: true` on autodev.yaml — single-line YAML + ~10-line `concurrency.py` change, reuses existing `LockManager` machinery (reuse score 3/3) without introducing a parallel locking layer; closes the FSM-vs-CLI race that Option B's PID file cannot, with ~5× less surface than Option C.

The BUG-1760 Option B plan, not the Option A plan (which was based on the misread cancellation). Add `singleton: bool = False` to `FSMLoop` schema (`scripts/little_loops/fsm/schema.py:874`) and `ScopeLock` dataclass (`fsm/concurrency.py:46`). When `singleton: true`, `LockManager.find_conflict()` blocks ANY concurrent instance of the same loop name regardless of scope overlap. Apply `singleton: true` to `autodev.yaml` so two `ll-loop run autodev` calls serialize on the lock layer. Implementation phase then runs strictly one-at-a-time, matching what `--worktree` provides via filesystem isolation without the worktree overhead.

This is the single-line fix: a YAML field on autodev.yaml plus a `~10-line` change to `concurrency.py`. It also retroactively fixes the parallel-autodev goal of FEAT-1789's cancellation rationale — if you actually want concurrent refinement, use a different loop name (e.g., a future `autodev-parallel.yaml` that DOES opt out of singleton via `singleton: false` plus per-issue-scope refactor).

**Option B — PID-file guard in `ll-auto`**

`AutoManager.__init__` writes `.ll/ll-auto.pid` (atomic `O_CREAT | O_EXCL`); refuses to start if a live PID owns it. `--force` flag for recovery. Cheap and Unix-conventional but does not solve the FSM-driven case (autodev shelling to `ll-auto --only` doesn't know about the PID guard unless we add it). Two layers needed: state-file lock + FSM serialization, so Option A is cleaner.

**Option C — Auto-detach to `--worktree` when concurrency detected**

`LockManager.acquire()` returns a "scope conflict but different instance_id" sentinel; on detection, autodev spawns a worktree for the implementation phase. Most complex; saves on tokens vs wall-clock but adds significant orchestration surface. Not recommended for P2 bug-fix scope.

```yaml
# Option A — autodev.yaml (one-line addition):
singleton: true
```

```python
# Option A — concurrency.py (sketch):
class ScopeLock:
    singleton: bool = False
    ...

# In LockManager.find_conflict(), after the scope-overlap check:
if not conflict and candidate_lock.singleton and lock.singleton and lock.loop_name == candidate_lock.loop_name:
    return candidate_lock
```

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-07-07.

**Selected**: Option A — `singleton: true` on autodev.yaml

**Reasoning**: Option A reuses the existing `LockManager` machinery at `scripts/little_loops/fsm/concurrency.py` without introducing a parallel locking layer. The codebase's additive `data.get("key", default)` migration pattern (`FSMLoop.from_dict`, `ScopeLock.to_dict`/`from_dict`) accommodates a new boolean field with no schema version bump. Option B's PID-file guard fundamentally cannot close the FSM-vs-CLI race (load-bearing objection from the agent evidence: the `implement_current` shell-out sees `exit 1` indistinguishable from a learning-gate block, and `LockManager` does not serialize concurrent autodev runs since their `${context.run_dir}` scopes are disjoint). Option C is explicitly flagged in the issue as "Not recommended for P2 bug-fix scope" and adds the largest orchestration surface (new sentinel return value, new worktree-spawn path, new merge-coordinator integration).

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option A — `singleton: true` on autodev.yaml | 3/3 | 3/3 | 3/3 | 2/3 | 11/12 |
| Option B — PID-file guard in `ll-auto` | 1/3 | 1/3 | 2/3 | 1/3 | 5/12 |
| Option C — Auto-detach to `--worktree` when concurrency detected | 2/3 | 1/3 | 2/3 | 2/3 | 7/12 |

**Key evidence**:
- **Option A** (reuse 3/3): `ScopeLock` dataclass at `fsm/concurrency.py:76-109` is the clean add-point; `LockManager.acquire()` signature is kwarg-clean for `singleton=False` default; `cmd_run` callsite at `run.py:329-330` is a one-line insertion; existing `TestMultiInstanceSameName` test class (`test_concurrency.py:504-624`) anticipates the new singleton predicate; `autodev.yaml:21-22` `scope:` block is the documented insertion site. Caveats from agent evidence: stale line-number references in the issue (FSMLoop cited at 874, actually 1057; ScopeLock at 46, actually 76) require grep-based verification during implementation; the `_get_ancestry` self-reference carve-out must extend to the new singleton predicate; `find_conflict()` must thread the caller's `singleton` flag rather than read it from the not-yet-written lock (the issue's sketch is imprecise on this point).
- **Option B** (reuse 1/3): `fcntl.flock` convention exists at `file_utils.py:60-96` and `concurrency.py:156`, but no `O_CREAT | O_EXCL` atomic-create pattern exists anywhere in `scripts/`. PID-file guard alone does not close the FSM-vs-CLI race because two autodev runs reach `implement_current` on disjoint scopes (so `LockManager` does not serialize them), and the shell-out's `exit 1` is indistinguishable from a learning-gate block at `autodev.yaml:362-398`. `--force` flag does not exist on `ll-auto` (would need new plumbing through `cli_args.py` and `AutoManager.__init__`). `_get_ancestry` carve-out needed or nested `ll-loop run autodev` invocations false-positive. Reuse score 1/3.
- **Option C** (reuse 2/3): `worktree_utils.py` provides `setup_worktree` (line 63) and `cleanup_worktree` (line 161), and `wait_for_scope` exists at `test_concurrency.py:348`, but `LockManager.acquire()` does not return a "scope conflict but different instance_id" sentinel today — would require restructuring or new return shape. Issue itself acknowledges "Most complex... Not recommended for P2 bug-fix scope." Reuse score 2/3.

**Breaking-change note**: This decision inverts FEAT-1789's parallel-refinement goal for users who relied on it. Mitigation documented in the issue's `## Impact` section: users who want concurrent refinement can keep using `--worktree` (whole-loop isolation) or fork to a separate loop name.

## Implementation Steps

1. Add `singleton: bool = False` field to `FSMLoop` dataclass at `scripts/little_loops/fsm/schema.py:874`; update `from_dict()` at line 989 to read `data.get("singleton", False)`.
2. Add `singleton: bool = False` field to `ScopeLock` dataclass at `scripts/little_loops/fsm/concurrency.py:46`; include in `to_dict()` / `from_dict()`.
3. In `LockManager.find_conflict()` at `concurrency.py:154`, after the existing scope-overlap check, add: if both `lock.singleton` and the candidate `lock.singleton` are True and `loop_name` matches, return the candidate as a conflict.
4. In `LockManager.acquire()` at `concurrency.py:130`, accept and forward `singleton` to the new `ScopeLock`.
5. In `cmd_run()` at `scripts/little_loops/cli/loop/run.py:271`, pass `fsm.singleton` to `acquire()`.
6. Add `singleton: true` to `scripts/little_loops/loops/autodev.yaml` (between `scope:` and `context:`).
7. Add tests at `scripts/tests/test_concurrency.py` `TestMultiInstanceSameName` class:
   - `test_singleton_loop_conflicts_on_name_regardless_of_scope`: two singleton locks with disjoint scopes → second acquires fail.
   - `test_non_singleton_same_name_disjoint_scopes_still_both_acquire` (regression — preserves ENH-1354).
8. Add structural assertion in `scripts/tests/test_builtin_loops.py` `TestAutodevInterleavedLoop` class that `autodev.yaml` declares `singleton: true`.
9. Update `docs/guides/LOOPS_GUIDE.md` "Scope-Based Concurrency" section (line 1697-1721) to document the `singleton:` field.
10. Update `docs/reference/API.md` `ScopeLock` (line 4803-4837) with the new field.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation. The first is BLOCKING — omitting it makes `autodev.yaml` warn on every validate and breaks several allowlist-contract tests:_

11. **BLOCKING** — Add `"singleton"` to `KNOWN_TOP_LEVEL_KEYS` in `scripts/little_loops/fsm/validation.py` (frozenset at line 174-219, alongside `"scope"` on line 182). Verified: without this, `load_and_validate()` (line 2743-2748) emits `Unknown top-level keys: singleton` as a WARNING, failing `test_fsm_flow.py::test_no_spurious_unknown_key_warnings` and `test_fsm_schema.py::test_known_keys_no_warning`.
12. Forward the caller-aware args to **both** in-module `find_conflict()` callers in `concurrency.py`: `LockManager.acquire()` (line 159, forward the candidate's `loop_name`/`singleton`) and `LockManager.wait_for_scope()` (line 278 polling loop — accept `loop_name`/`singleton` params so the predicate fires on `--queue` retry).
13. Update the **second** `find_conflict()` callsite in `cmd_run()` at `run.py:331` (the post-`acquire()`-failure conflict lookup that feeds `waitingFor`/log lines) to forward `caller_loop_name=fsm.name, caller_singleton=fsm.singleton` — distinct from the `acquire()` callsite in step 5.
14. (Advisory) Add a `singleton` property to `scripts/little_loops/fsm/fsm-loop-schema.json` so the loop-YAML spec schema stays consistent with the runtime field.
15. Add regression assertions to the end-to-end acquire/find_conflict tests that will now exercise the new kwargs: `test_cli_loop_background.py::TestRunBackground` (pre-flight branch), `test_cli_loop_lifecycle.py::TestCmdRunHandoffThreshold`/`TestCmdRunYAMLConfigOverrides` (real `cmd_run` acquire path), and the `singleton=` kwarg assertion in `test_cli_loop_queue.py::test_retries_acquire_after_losing_race`.

### Codebase Research Findings (Implementation Steps)

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Line-number audit (verified against current `main`).** Use the **corrected** anchor when implementing; original line numbers below are stale as of 2026-07-07. The issue itself flagged two of these (FSMLoop @ 874→1057, ScopeLock @ 46→76); the codebase-locator agent caught more.

| Step | Reference | Status | Corrected anchor |
|------|-----------|--------|------------------|
| 1 | `schema.py:874` (FSMLoop); `:989` (from_dict) | STALE | `schema.py:1057` (FSMLoop dataclass); `:1231` (`from_dict` `@classmethod`) |
| 2 | `concurrency.py:46` (ScopeLock) | STALE | `concurrency.py:76` (already flagged in issue) |
| 3 | `concurrency.py:154` (find_conflict) | STALE | `concurrency.py:187` |
| 4 | `concurrency.py:130` (acquire) | RESOLVES (off by 2) | keep `concurrency.py:130` |
| 5 | `run.py:271` (cmd_run) | STALE | `cmd_run()` is defined at `run.py:90`; the `lock_manager.acquire()` callsite is at `run.py:330`, with a queue-retry at `run.py:366`. Pass `fsm.singleton` to **both** callsites. |
| 7 | `TestMultiInstanceSameName` "504-624" | RESOLVES (off by 4) | keep `504-628` |
| 8 | `TestAutodevInterleavedLoop` at `test_builtin_loops.py:1270` | **DOES NOT EXIST** | Use `TestAutodevLoop` at `test_builtin_loops.py:2330`; model the new structural assertion on `test_scope_field_uses_run_dir_template` at `test_builtin_loops.py:3387-3397` (same class, established `data.get("scope")` pattern) |
| 9 | `LOOPS_GUIDE.md:1697-1721` | STALE | `LOOPS_GUIDE.md:637` (the `### Scope-Based Concurrency` heading is there now) |
| 10 | `API.md:4803-4837` | STALE | `API.md:5439` (`#### ScopeLock` heading; dataclass on 5443; `#### LockManager` on 5452) |

**Step 3 sketch precision — REQUIRED fixes.** The issue's pseudocode reads "if both `lock.singleton` and the candidate `lock.singleton` are True and `loop_name` matches." Inside `find_conflict`, `lock` is the on-disk candidate, **not** the in-progress caller. Either:
- (a) Extend `find_conflict()` signature to `find_conflict(self, scope: list[str], *, caller_loop_name: str | None = None, caller_singleton: bool = False) -> ScopeLock | None` and compare `lock.loop_name == caller_loop_name and lock.singleton and caller_singleton`; or
- (b) Accept a candidate `ScopeLock` and reuse its fields.

Option (a) is the smallest change. `wait_for_scope` (concurrency.py:266-283) currently calls `find_conflict(scope)` without `loop_name` — it needs to accept a `loop_name` parameter (or be made loop-aware) so the singleton predicate fires inside its polling loop.

**Missing step — pre-flight `find_conflict` callsite.** `cli/loop/_helpers.py:1328` runs a pre-flight `find_conflict(scope)` before any fork/spawn; it **must** also forward the singleton flag, otherwise the pre-flight passes, the queue retry fires, the actual `acquire()` fails with `find_conflict` returning a same-loop-name lock that the user was not warned about. Add as a separate step (e.g., `5b`): "Update pre-flight `find_conflict` at `_helpers.py:1328` to accept and forward `caller_loop_name` + `caller_singleton`."

**Missing step — `_get_ancestry` carve-out extension.** `find_conflict()`'s ancestor self-reference carve-out at `concurrency.py:223-229` MUST extend to the new singleton predicate. A parent `ll-loop run` process that shells to nested `ll-loop run autodev` would otherwise self-conflict on singleton. Mirror the existing carve-out pattern: after the new singleton-overlap check, add `if lock.pid in self._get_ancestry(): continue` (same `logger.debug` shape as lines 224-228).

**`fcntl.flock` reentrance — already covered.** `LockManager.acquire()` holds `fcntl.flock(LOCK_EX)` on `.acquire.lock` (concurrency.py:155-157) around the `find_conflict` + write pair. Adding the singleton check inside the existing `find_conflict` call (line 160) inherits this atomicity automatically; **no new lock layer is needed**. The lock file is written at `acquire()` lines 172-173 *while still holding* `.acquire.lock`, so a second acquirer's `find_conflict` at line 160 always sees the first acquirer's freshly-written `.lock` file.

**Test pattern to model after (Step 7).** `TestMultiInstanceSameName.test_concurrent_same_name_non_overlapping_scopes_both_acquire` (lines 504-628) uses `threading.Barrier(2)` to coordinate two `LockManager.acquire` calls. Use the same `try_acquire` + `barrier.wait()` + `results.count(True)` shape for the new singleton tests. For the `wait_for_scope` interaction, model on the existing `TestLockManagerWait` class at `test_concurrency.py:387-435` (the helper is at `concurrency.py:266-283`, not at line 348 as the issue states — close, but stale).

**`FSMLoop` field-shape template.** The closest existing precedent for the new `singleton: bool = False` field is `maintain: bool = False` at `schema.py:1095`. `to_dict()` already follows `if self.maintain: result["maintain"] = self.maintain` (lines 1159-1160) — append the same shape for `singleton`. `from_dict()` reads `data.get("singleton", False)` alongside the existing `_ok` block at lines 1276-1318.

**`ScopeLock.from_dict` migration.** Unlike `FSMLoop.from_dict`, `ScopeLock.from_dict` at `concurrency.py:101-109` currently **requires every key** (no `data.get()` defaults). Adding `singleton` must use `data.get("singleton", False)` so that legacy lock files (no `singleton` key) parse without `KeyError`. Also include `singleton` in `to_dict()` (currently returns only `loop_name`, `scope`, `pid`, `started_at`).

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/schema.py` — add `singleton` field to `FSMLoop`
- `scripts/little_loops/fsm/concurrency.py` — add `singleton` to `ScopeLock`, propagate through `acquire()`/`find_conflict()`
- `scripts/little_loops/cli/loop/run.py` — pass `fsm.singleton` to `acquire()`
- `scripts/little_loops/loops/autodev.yaml` — set `singleton: true`

_Wiring pass added by `/ll:wire-issue`:_
- **`scripts/little_loops/fsm/validation.py` — add `"singleton"` to `KNOWN_TOP_LEVEL_KEYS` frozenset (line 174–219).** ⚠️ **BLOCKING / VERIFIED.** `load_and_validate()` computes `unknown = set(data.keys()) - KNOWN_TOP_LEVEL_KEYS` at line 2743 and emits a `ValidationError(severity=WARNING)` "`Unknown top-level keys: {…}`" at line 2748 for any key not in the set. Verified against `main`: `scope` IS in the set (line 182) so autodev's existing field passes, but `singleton` is NOT. Without this addition, `ll-loop validate autodev.yaml` warns on every load (loads succeed since it's a WARNING, but the several `test_no_*unknown*` tests that assert zero unknown-key warnings will fail). This file is absent from the issue's plan; it is the load-bearing side-effect of adding a new top-level loop field. [Agent 2 finding — confirmed by direct grep]
- `scripts/little_loops/fsm/fsm-loop-schema.json` — spec JSON Schema documenting loop-YAML top-level fields (includes `scope`, `max_steps`, `maintain`, `on_handoff`, …). Add `singleton` for docs consistency. NOT runtime-enforced (no Python code calls `jsonschema.validate()` against it — grep-confirmed), so this is advisory (`fyi` tier), not blocking. [Agent 2 finding]

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/_helpers.py:22` — imports `LockManager`; `lock_manager.acquire()` callsite at line 1306 needs the new field
- `scripts/little_loops/fsm/persistence.py:38` — imports `_process_alive` from `concurrency`; lock-file format changes need version bump
- `scripts/little_loops/fsm/__init__.py:69-78` — re-exports `LockManager`, `ScopeLock`; signature changes propagate
- `scripts/little_loops/cli/loop/lifecycle.py:21` — same import chain

### Codebase Research Findings (Dependent Files)

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `cli/loop/_helpers.py:22` — the `LockManager` import is at line **21** (off by 1). More importantly, **the cited `lock_manager.acquire()` callsite at line 1306 does not exist** in this file. The file uses `LockManager(loops_dir)` (line 1319) and a *pre-flight* `find_conflict(scope)` (line 1328) — **no** `.acquire()` call. Pre-flight is the only site in `_helpers.py` that needs the singleton flag; forward as `find_conflict(scope, caller_loop_name=loop_name, caller_singleton=fsm.singleton)` (see Implementation Steps "Missing step — pre-flight" above).
- `fsm/persistence.py:38` — RESOLVES (`from little_loops.fsm.concurrency import _process_alive`). The new `singleton` field is additive via `data.get("singleton", False)` on `ScopeLock.from_dict` — **no version bump** is needed for legacy lock files (the current `from_dict` requires every key today; `singleton` must migrate to `data.get()` to avoid `KeyError` on pre-fix lock files; see Implementation Steps "ScopeLock.from_dict migration" above).
- `fsm/__init__.py:69-78` — the re-export block is now at lines **77-81** (off by 8). The `LockManager`/`ScopeLock` re-exports (`from little_loops.fsm.concurrency import (LockManager, ScopeLock, resolve_scope,)`) require no functional change; the public-API docs should be regenerated (`ll-generate-schemas`).
- `cli/loop/lifecycle.py:21` — RESOLVES (`from little_loops.fsm.concurrency import _process_alive`). No functional change required; the import reads `_process_alive` only, not `LockManager`/`ScopeLock`.

_Wiring pass added by `/ll:wire-issue`:_
- **`scripts/little_loops/cli/loop/run.py:331` — second `find_conflict()` callsite (distinct from the `acquire()` callsite at step 5).** After a failed `acquire()`, `cmd_run()` calls `conflict = lock_manager.find_conflict(scope)` to populate the queue-entry `waitingFor` field (line 342) and the "Scope conflict with running loop" log line (line 376). Once `find_conflict()` gains `caller_loop_name`/`caller_singleton` kwargs, this call must forward `caller_loop_name=fsm.name, caller_singleton=fsm.singleton` — otherwise the queued/blocked message never reflects the singleton conflict. [Agent 2 finding]
- **`scripts/little_loops/fsm/concurrency.py` internal `find_conflict()` callers (same file, but easy to miss).** Two in-module callsites reuse `find_conflict(scope)` and must forward the new caller-aware args or the singleton predicate never fires: (a) `LockManager.acquire()` at `concurrency.py:159` — forward the candidate's `loop_name`/`singleton` (the candidate `ScopeLock` is built at line 166); (b) `LockManager.wait_for_scope()` at `concurrency.py:278` — its polling loop calls `find_conflict(scope)` without loop context, so a `--queue` retry waiting on a singleton conflict would loop forever. The issue's Step 3 already flags `wait_for_scope`; the `acquire()` internal forward is the newly-surfaced half. [Agent 2 finding]
- `scripts/little_loops/fsm/fsm-loop-schema.json` — documents loop-YAML top-level fields; drifts from runtime if `singleton` is omitted, but is not imported/validated by any code (advisory only). [Agent 2 finding]

### Similar Patterns
- `scripts/little_loops/loops/dead-code-cleanup.yaml` — only the other loop with explicit `scope:`; singleton would be orthogonal
- `scripts/little_loops/loops/docs-sync.yaml` — multi-path scope; singleton would also apply
- `scripts/little_loops/loops/rn-refine.yaml` — uses `${context.plan_file}` scope; could opt into singleton for plan-implement coordination

### Tests
- `scripts/tests/test_concurrency.py:452-514` — `TestPathOverlap`; add singleton-on-name-conflict case
- `scripts/tests/test_concurrency.py:517-581` — `TestMultiInstanceSameName`; add singleton regression tests
- `scripts/tests/test_concurrency.py:60-255` — `TestLockManager`; verify singleton field roundtrips through to_dict/from_dict
- `scripts/tests/test_builtin_loops.py:1270` — `TestAutodevInterleavedLoop`; add structural singleton assertion
- `scripts/tests/test_cli_loop_queue.py:61` — `test_retries_acquire_after_losing_race`; verify singleton retry behavior

### Codebase Research Findings (Tests)

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `test_concurrency.py:452-514` — `TestPathOverlap` is now at lines **439-502** (STALE; off by ~13). Path-vs-singleton interaction tests fit here (e.g., `test_singleton_paths_overlap_still_conflicts` — two singleton locks with overlapping file paths, even on same loop_name, must still produce a conflict).
- `test_concurrency.py:517-581` — `TestMultiInstanceSameName` is at lines **504-628** (RESOLVES; off by ~4). Use the existing `try_acquire` + `barrier.wait()` + `results.count(True)` shape (see `test_concurrent_same_name_non_overlapping_scopes_both_acquire` at ~504-624) for the two new singleton tests.
- `test_concurrency.py:60-255` — `TestLockManager` is at lines **59-252** (RESOLVES; off by ~1). Extend `TestScopeLock.test_to_dict` / `test_from_dict` / `test_roundtrip` (lines 17-56) to verify `singleton=True` roundtrips through `to_dict()`/`from_dict()` without losing the field; add a `test_singleton_defaults_to_false` to lock in the migration contract (legacy lock files deserialize with `singleton=False`).
- `test_builtin_loops.py:1270` — `TestAutodevInterleavedLoop` **DOES NOT EXIST** in this file. Closest matches: `TestAutodevLoop` at line 2330 (which contains `test_scope_field_uses_run_dir_template` at lines 3387-3397, the model for this assertion) and `TestAutodevAuthGuard` at line 8910. Add the new `test_autodev_yaml_declares_singleton_true` structural assertion under `TestAutodevLoop`, modeled on `test_scope_field_uses_run_dir_template`.
- `test_cli_loop_queue.py:61` — `test_retries_acquire_after_losing_race` is at line **62** (RESOLVES; off by 1). When the new kwarg is threaded, verify `mock_lm.acquire.call_args_list[*].kwargs["singleton"] == True` (or `False` for non-singleton loops) — the existing mock at lines 71-73 currently does not inspect `kwargs`, only the return value. The same fix applies to the queue-retry path's `.acquire` calls.

**Existing test class to extend for the `_get_ancestry` carve-out.** Add `test_singleton_ancestor_does_not_self_conflict` to `TestLockManager` (or a new `TestSingletonLock` class) — a parent PID forks, the child runs `ll-loop run autodev`, both have singleton on the same loop_name; the child's `find_conflict()` must skip the parent's lock via `_get_ancestry()` (concurrency.py:223-229).

### Tests (Wiring Pass)

_Wiring pass added by `/ll:wire-issue` — test files NOT already listed above:_

**Regression gates (must stay green — these will catch the `validation.py` gap):**
- `scripts/tests/test_fsm_flow.py::TestBuiltinLoopRegression.test_all_builtin_loops_still_load` (line 325) — globs every builtin `*.yaml` and calls `load_and_validate()`. **This is the load-bearing gate for the `autodev.yaml` change** — it will surface the `Unknown top-level keys: singleton` warning if `KNOWN_TOP_LEVEL_KEYS` is not updated. [Agent 3 finding]
- `scripts/tests/test_fsm_flow.py::test_no_spurious_unknown_key_warnings` (line 264) — asserts zero unknown-top-level-key warnings; fails until `singleton` is added to the allowlist. [Agent 2 finding]
- `scripts/tests/test_fsm_schema.py::test_known_keys_no_warning` (1715-1728) and `test_unknown_top_level_keys_warn` (1689-1714) — pin the `KNOWN_TOP_LEVEL_KEYS` contract directly; add `singleton` to the known-keys fixture. [Agent 2 finding]
- `scripts/tests/test_fsm_fragments.py` (791-858) — multiple tests asserting `KNOWN_TOP_LEVEL_KEYS` membership for `import`/`fragments`; mirror for `singleton` if a membership assertion is added. [Agent 2 finding]
- `scripts/tests/test_fsm_inheritance.py::test_no_unknown_key_warning_for_from` (line 369) — same allowlist contract via the `from:` field. [Agent 2 finding]

**End-to-end acquire/find_conflict paths that transparently exercise the new kwargs (add regression assertions):**
- `scripts/tests/test_cli_loop_background.py::TestRunBackground` — the 5 tests at lines 675, 710, 737, 804, 859 are the ONLY tests driving the `_helpers.py:1328` pre-flight `find_conflict()` branch end-to-end; three patch `LockManager._get_ancestry` (lines 697, 727, 759, 906), the exact carve-out the singleton predicate must mirror. Must stay green after the signature change; add a singleton-preflight case here. [Agent 1 + Agent 3 finding]
- `scripts/tests/test_cli_loop_lifecycle.py::TestCmdRunHandoffThreshold` (1302, 1324, 1342) and `TestCmdRunYAMLConfigOverrides` (1397, 1418, 1436) — call real `cmd_run()`, walking `acquire()`→`release()`; will exercise the threaded `singleton` kwarg automatically. Regression-guard candidates. [Agent 3 finding]
- `scripts/tests/test_autodev_decision_gate.py` — entire file structurally asserts against `autodev.yaml` via `load_and_validate()` (lines 282-295); a good home for `singleton: true` structural verification alongside the new-field load check. [Agent 1 finding]

**New-field round-trip / migration coverage (new tests to write):**
- `scripts/tests/test_fsm_schema.py` — model a new `TestSingleton` class on `TestBashDefaultOk` (line 3627): `*_true_round_trips` / `*_false_omitted_from_dict` / `*_defaults_false`. Locks in `FSMLoop.singleton` `to_dict`/`from_dict` symmetry. [Agent 3 finding]
- `scripts/tests/test_fsm_schema_fuzz.py::TestFSMLoopFuzz.test_from_dict_handles_malformed` (line 422) — exercises the new field against arbitrary dicts; verify it defaults safely. [Agent 1 finding]
- `scripts/tests/test_fsm_validation.py:1024` — roundtrip assertion pattern (`visibility` field) to mirror for `singleton`. [Agent 1 finding]
- `scripts/tests/test_cli_loop_queue.py::TestQueueRetryOnRace.test_retries_acquire_after_losing_race` (line 62, already listed) — add `call.kwargs["singleton"]` assertion parallel to the existing `instance_id` assertion (lines 96-103) to validate kwarg threading through the queue-retry path. [Agent 3 finding]
- `scripts/tests/test_cross_host_baseline.py` (patches `LockManager` at 173, 203) — MagicMock-based, tolerant to the new kwarg; verify no `spec=` brittleness. [Agent 1 finding]

### Documentation
- `docs/guides/LOOPS_GUIDE.md:1697-1721` — "Scope-Based Concurrency" section
- `docs/reference/API.md:4803-4837` — `ScopeLock` dataclass API
- `docs/reference/CLI.md:399-407` — `--no-lock` flag description should mention `singleton` semantics
- `CHANGELOG.md` — add entry under next release (user-visible behavior change for concurrent autodev users)

### Codebase Research Findings (Documentation)

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `docs/guides/LOOPS_GUIDE.md:1697-1721` — `### Scope-Based Concurrency` heading is now at line **637** (STALE; the section spans roughly 637-647). Add a new `### Singleton (one-instance-per-name)` subsection immediately after, with the same example-driven format. Mention: (a) the new field's effect on lock acquisition, (b) the interaction with `--worktree` (mutually exclusive — singleton prevents the conflict that `--worktree` would otherwise bypass), (c) the `_get_ancestry` carve-out so nested loops don't self-conflict.
- `docs/reference/API.md:4803-4837` — `#### ScopeLock` heading is now at line **5439** (dataclass at 5443); `#### LockManager` at line **5452** (STALE). Add the `singleton:` field to the `ScopeLock` dataclass signature, and a paragraph describing the predicate behavior (loop-name match takes precedence over scope overlap when both sides declare singleton).
- `docs/reference/CLI.md:399-407` — the `ll-loop run` flag table is now around line **552** (STALE). The `--no-lock` row at line 552 should mention singleton semantics: "Bypasses both scope-based and singleton (one-instance-per-name) locks; intended for emergency diagnostics only — concurrent runs may still corrupt shared state."
- `CHANGELOG.md` — RESOLVES. Add the entry **under the next released version section, NOT `[Unreleased]`** (per project convention recorded in `feedback_changelog_no_unreleased.md`). The entry should describe: (a) the user-visible behavior change for concurrent autodev, (b) the migration path for users who relied on FEAT-1789's parallel refinement (use `--worktree` for whole-loop isolation, or fork to a new loop name with `singleton: false`).

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/fsm/fsm-loop-schema.json` — the loop-YAML spec JSON Schema (documents `scope`, `max_steps`, `maintain`, `on_handoff`, …). Add a `singleton` property so the spec stays consistent with the runtime `FSMLoop` field. Advisory only — grep-confirmed that no code imports this file or runs `jsonschema.validate()` against it; it is a documentation artifact. [Agent 2 finding]

### Configuration
- N/A — `singleton` is a YAML field on the loop, not a config key

## Impact

- **Priority**: P2 — concurrent runs produce silent logical corruption (no crash, no error); developers may notice only via `--resume` resurrecting completed work, doubled token spend, or tangled git history. Recovery requires manual `git reset` / state file deletion. Not a P0 (no data loss beyond reprocessable state) and not a P3 (the symptom is real and the fix is small).
- **Effort**: Small — ~50 lines of code change across 4 files plus ~80 lines of tests. The schema field, dataclass field, one-line `find_conflict()` predicate, and a one-line YAML addition. No new dependencies.
- **Risk**: Low — `singleton: false` is the default, so existing loops are unaffected. The autodev change moves behavior from "parallel refinement, serial implementation via --worktree opt-in" to "serial everything". This breaks FEAT-1789's parallel-refinement use case for users who relied on it. Mitigation: document the change in CHANGELOG; users who actually want parallel refinement can keep using `--worktree` (whole-loop isolation) or fork to a new loop name.
- **Breaking Change**: Yes, for users who relied on FEAT-1789's parallel refinement to run multiple `ll-loop run autodev` concurrently. No breaking change for the standard serial autodev workflow.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Related Issues

- BUG-1760 (cancelled): related but cancelled on misdiagnosis — claimed `autodev.yaml` defaults to `["."]`; it actually declares `scope: ["${context.run_dir}"]`. The bug premise (concurrent autodev passes LockManager) is correct under current code; the cancellation rationale is wrong but the issue itself was mis-scoped to `.loops/.running/` state files rather than `.auto-manage-state.json`.
- FEAT-1789 (done): introduced the per-instance scope pattern that creates this race; the implementation-phase coordination gap was identified but explicitly deferred.
- ENH-1726 (done): scoped temp files under `${context.run_dir}`; this is the prerequisite that makes Option A feasible.
- ENH-1787 (done): added scope template variable support; the same prerequisite.
- ENH-1354 (done): same-name concurrent instances with non-overlapping scopes are intentional design; `singleton: false` preserves this.

## Labels

`bug`, `autodev`, `ll-auto`, `concurrency`, `captured`

## Status

**Done** | Created: 2026-07-07 | Completed: 2026-07-07 | Priority: P2

## Resolution

Implemented Option A (`singleton: true` on `autodev.yaml`) as decided on 2026-07-07.

**Code changes:**
- `scripts/little_loops/fsm/concurrency.py` — added `singleton: bool = False` to `ScopeLock` (with `.get()` migration for legacy lock files); extended `LockManager.acquire()` / `find_conflict()` / `wait_for_scope()` signatures to thread the singleton kwarg; new singleton predicate in `find_conflict()` mirrors the existing `_get_ancestry` carve-out.
- `scripts/little_loops/fsm/schema.py` — added `singleton: bool = False` to `FSMLoop`; `to_dict()` conditionally emits; `from_dict()` reads via `data.get("singleton", False)`.
- `scripts/little_loops/fsm/validation.py` — added `"singleton"` to `KNOWN_TOP_LEVEL_KEYS` (BLOCKING — required so `load_and_validate()` does not emit "Unknown top-level keys" warning).
- `scripts/little_loops/cli/loop/run.py` — threaded `fsm.singleton` through both `acquire()` callsites, the `find_conflict()` callsite, and `wait_for_scope()`.
- `scripts/little_loops/cli/loop/_helpers.py` — pre-flight `find_conflict()` forwards `caller_loop_name` + `caller_singleton`.
- `scripts/little_loops/loops/autodev.yaml` — set `singleton: true` between `scope:` and `context:`.

**Tests added (12, all RED-then-GREEN via TDD):**
- `test_concurrency.py::TestScopeLock` — 3 round-trip / migration tests.
- `test_concurrency.py::TestSingletonLock` — 4 conflict semantics tests (singleton-on-name, non-singleton regression for ENH-1354, paths-overlap-still-conflicts, ancestor carve-out).
- `test_builtin_loops.py::TestAutodevLoop::test_autodev_yaml_declares_singleton_true` — structural YAML assertion.
- `test_fsm_schema.py::TestSingleton` — 3 FSMLoop round-trip tests (modeled on `TestBashDefaultOk`).
- `test_cli_loop_queue.py::test_retries_acquire_after_losing_race` — singleton kwarg threading assertion.

**Verification:** full suite `python -m pytest scripts/tests/` — 14,161 passed, 35 skipped, 0 failures. No new lint or mypy errors introduced (2 pre-existing ruff + 3 pre-existing mypy errors on `main` are unrelated to this issue).

**Documentation:**
- `docs/guides/LOOPS_GUIDE.md` — added `### Singleton (one-instance-per-name)` subsection after `### Scope-Based Concurrency`, covering `singleton:` semantics, `--worktree` interaction, and nested-loop carve-out.
- `docs/reference/API.md` — updated `ScopeLock` dataclass to include `singleton: bool = False`; updated `LockManager` method table to document the new kwargs on `acquire` / `find_conflict` / `wait_for_scope`.
- `CHANGELOG.md` — added entry under `## [1.140.0] - 2026-07-07` (NOT `[Unreleased]` per `feedback_changelog_no_unreleased.md`).

**Breaking change for users relying on FEAT-1789:** users who relied on concurrent autodev refinement can use `--worktree` (whole-loop filesystem isolation) or fork to a new loop name with `singleton: false`. Documented in CHANGELOG.

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-07-07 (re-evaluation: pass 3 — Learning Test Hard Override cleared)_

**Readiness Score**: 95/100 → **PROCEED** (cleared `readiness_threshold=85`; was STOP — Hard Override in pass 2)
**Outcome Confidence**: 79/100 → above `commands.confidence_gate.outcome_threshold=75` (unchanged from pass 2)

**Hard Override clearance.** `ll-learning-tests check fcntl` now returns `status: proven` (4 pass / 1 fail / 1 untested — the `fail` confirms `flock` is per-open-file-description, which is the load-bearing fact Option A relies on since `LockManager.acquire()` holds `LOCK_EX` on a shared `.acquire.lock` fd across `find_conflict` + lock-file write). The Hard Override is cleared. Criterion 1 modifier (−10) removed; readiness rises from 85 → 95.

### Criterion 1 modifier

Cleared. `fcntl` status went `missing` → `proven` between pass 2 and pass 3. Criterion 1 base 20/20 restored.

### Concerns
_(none — readiness tier PROCEED, no concerns subsection emitted by Phase 4.5)_

### Gaps to Address
_(none — readiness 95 ≥ 70)_

### Outcome Risk Factors
_(none — outcome 79 ≥ 75, no risk-factor subsection emitted by Phase 4.5)_

### Pass 2 (superseded by pass 3)

_Added by `/ll:confidence-check` on 2026-07-07 (re-evaluation: pass 2)_

**Readiness Score**: 85/100 → PROCEED WITH CAUTION (at threshold band 70–89; **Hard Override** forces STOP — ADDRESS GAPS — see below)
**Outcome Confidence**: 79/100 → above `commands.confidence_gate.outcome_threshold=75`

**⚠ Learning Test Hard Override (Phase 3) — STOP — ADDRESS GAPS**

The issue's `learning_tests_required: [fcntl]` frontmatter field is **still not
satisfied**. Confirmed via `ll-learning-tests check fcntl` (exit 1, "no record
found") and `ll-learning-tests list` (registered: anthropic, hypothesis,
phoenix, pytest-xdist, pytest, questionary, ruamel.yaml — **no fcntl**). Per
the rubric, this fires the Learning Test Hard Override and the recommendation
must be **STOP — ADDRESS GAPS** regardless of the aggregate readiness score.

The fix is narrow: run `/ll:explore-api fcntl` and prove the claims Option A
actually depends on (e.g. "existing `fcntl.flock(LOCK_EX)` calls in
`concurrency.py:155-157` provide atomicity around `find_conflict` + lock-file
write"). The issue does not introduce new `fcntl` semantics — it reuses the
existing `LockManager.acquire()` machinery — so the proof surface is narrow
but it must exist before the gate clears. After the learning-test record is
created, the Hard Override clears and the issue re-evaluates at PROCEED WITH
CAUTION (85 ≥ 70, but still below `readiness_threshold=85`).

### Criterion 1 modifier

Per the rubric's Phase 1.5 modifier table, a `missing` learning-test target
applies a **−10** modifier to Criterion 1. Base score 20 − 10 = **10/20** for
Criterion 1.

### Concerns

- **Line-number audit risk** — the Implementation Steps audit table flags
  several STALE anchors (FSMLoop @874→1057, ScopeLock @46→76, find_conflict
  @154→187, `cmd_run()` @271→90, `LOOPS_GUIDE.md` Scope section @1697-1721→637,
  API.md ScopeLock @4803-4837→5439). Each step requires grep-verification
  before editing; the surface is broad enough that one missed anchor will cause
  a broken reference. The **BLOCKING** `KNOWN_TOP_LEVEL_KEYS` allowlist at
  `validation.py:174-219` is correctly flagged by the issue's wiring pass as
  load-bearing for `test_fsm_flow.py::test_all_builtin_loops_still_load`.
- **Stale `ScopeLock.from_dict` migration contract** — `from_dict` at
  `concurrency.py:101-109` currently requires every key. Adding `singleton`
  via `data.get("singleton", False)` is the correct migration, but it is
  implicit in the implementation steps, not a numbered item. Easy to miss;
  easy to introduce a `KeyError` on pre-fix lock files.
- **`_get_ancestry` carve-out extension** — the new singleton predicate at
  `find_conflict()` must mirror the existing carve-out at
  `concurrency.py:223-229` to avoid parent-loop self-conflict on nested
  invocations. Implementation steps mention this; ranked Concern because it is
  the most-likely-to-be-skipped item on a wide-fanout edit.
- **`find_conflict` signature change ripples further than the numbered steps**
  — the pre-flight call at `_helpers.py:1328`, the second `cmd_run()` callsite
  at `run.py:331`, and the internal `wait_for_scope` polling at
  `concurrency.py:278` all consume `find_conflict(scope)` and must forward the
  new `caller_loop_name` / `caller_singleton` kwargs. The wiring pass flags
  these but the numbered steps only mention `acquire()` — easy to miss.

### Outcome Risk Factors
_(none — outcome 79 ≥ 75, above outcome threshold; no risk-factor subsection
emitted by Phase 4.5. Implementation-order risk remains captured in the
Concerns above as `_get_ancestry` carve-out extension.)_

## Session Log
- `/ll:ready-issue` - 2026-07-07T19:48:48 - `0ba35bf3-d5e4-4bb6-b3f6-d1b101d406bd.jsonl`
- `/ll:wire-issue` - 2026-07-07T19:28:29 - `542eb67c-7bf6-4187-abaf-7c6119b6c576.jsonl`
- `/ll:refine-issue` - 2026-07-07T19:12:49 - `40d0e78c-df7f-4cb7-921b-8d5096a48b4a.jsonl`
- `/ll:decide-issue` - 2026-07-07T18:42:17 - `aa4ef9c3-2d91-4260-ab4d-ee3eaafe7a78.jsonl`

- `/ll:capture-issue` - 2026-07-07T18:27:32Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f0f210d3-d26f-4d18-afdc-42b125ba76df.jsonl`
- `/ll:confidence-check` - 2026-07-07T19:45:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/af8238c5-578f-4710-abe9-3af6a759509e.jsonl`
- `/ll:confidence-check` - 2026-07-07T20:05:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/df07e22c-8871-48e3-b1d7-04bfa2aeef84.jsonl`
- `/ll:confidence-check` - 2026-07-07T20:30:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f1919be3-bdc6-4734-85ed-fcb625677d85.jsonl`
- `/ll:manage-issue` - 2026-07-07T20:00:22Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d1a8a2e8-66f8-4c39-b389-903081f75283.jsonl`