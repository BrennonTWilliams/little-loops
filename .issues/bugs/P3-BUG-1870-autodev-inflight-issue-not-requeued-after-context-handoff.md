---
id: BUG-1870
title: autodev inflight issue not re-queued after context handoff spawns continuation
type: BUG
status: done
priority: P3
captured_at: '2026-06-02T04:00:00Z'
completed_at: '2026-06-02T23:18:02Z'
discovered_date: '2026-06-02'
discovered_by: audit-loop-run
source_loop: autodev
source_state: implement_current
labels:
- bug
- autodev
- handoff
- fsm
decision_needed: false
confidence_score: 95
outcome_confidence: 82
score_complexity: 21
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 25
---

# BUG-1870: autodev inflight issue not re-queued after context handoff spawns continuation

## Summary

When `implement_current` hits a context limit mid-implementation and the FSM emits `handoff_detected` + `handoff_spawned`, the in-flight issue recorded in `autodev-inflight` is **not re-queued** in `autodev-queue.txt`. The spawned continuation (`ll-loop resume autodev`) resumes from `dequeue_next`, which reads only from `autodev-queue.txt` — so the inflight issue is silently skipped for the rest of the run.

## Steps to Reproduce

1. Configure and start an `autodev` loop run with multiple issues in `autodev-queue.txt`
2. Allow `implement_current` to begin processing an issue and reach a context limit mid-implementation
3. Observe: FSM emits `handoff_detected` → `handoff_spawned`; `ll-loop resume autodev` is spawned as a subprocess
4. Observe: `autodev-inflight` still contains the interrupted issue
5. Observe: The continuation run resumes at `dequeue_next` and reads the next item from `autodev-queue.txt` — the inflight issue is never re-queued and is silently skipped

## Current Behavior

In run `2026-06-02T022609`:
- `implement_current` for ENH-1868 hit a context limit at iter 16 (03:48 UTC)
- `handoff_spawned` fired with PID 162 (`ll-loop resume autodev`)
- `autodev-inflight` = `ENH-1869`; `autodev-queue.txt` = `ENH-1776\nENH-1777`
- Continuation resumed at `refine_current iter=19`, processing ENH-1776 next
- ENH-1869 has partial implementation (code changes made in ENH-1868's session) but docs, commit, and `status=done` are pending — and no further processing will occur

## Root Cause

`implement_current` writes the inflight issue to `autodev-inflight` (set earlier by `dequeue_next`). The handoff mechanism correctly spawns the continuation, but neither the FSM definition nor the resume logic checks `autodev-inflight` to see whether the last processed issue reached a clean terminal state.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **`on_resume` does not exist in the FSM schema**: `FSMLoop` in `scripts/little_loops/fsm/schema.py` defines `on_handoff` (pause/spawn/terminate) and `on_max_iterations`, but has no `on_resume` field. No loop YAML in the codebase uses an `on_resume` key.
- **`init` is bypassed on resume**: `PersistentExecutor.resume()` in `scripts/little_loops/fsm/persistence.py:774` restores `current_state` directly to the state saved at handoff time (typically `"implement_current"`). The `init` state — which resets `autodev-inflight` via `rm -f` at `autodev.yaml:44` — is never re-entered on resume.
- **Resume entry point is `implement_current`**: `_handle_handoff()` in `scripts/little_loops/fsm/executor.py` saves `final_state = self.current_state` (= `"implement_current"`). On `ll-loop resume autodev`, `PersistentExecutor.resume()` calls `run(clear_previous=False)` with `current_state = "implement_current"`, which re-executes `ll-auto --only ${captured.input.output}` immediately — no pre-resume hook runs.
- **`autodev-inflight` write sites**: sole write is `dequeue_next:73` via `printf '%s' "$CURRENT" > autodev-inflight`. Cleared by `init`, `skip_inflight`, `enqueue_children`, `enqueue_or_skip`, and `recheck_after_size_review`. `implement_current` never clears it.
- **`done` state warns but does not re-queue** (`autodev.yaml:566`): prints `"WARNING: in-flight issue not resolved"` but takes no corrective action.

## Expected Behavior

On `handoff_spawned`, if `autodev-inflight` contains an issue whose `status` is not `done`/`cancelled`, that issue should be prepended back to `autodev-queue.txt` so the continuation can process it.

## Motivation

Context-handoff is the primary mechanism for surviving long autodev runs that exceed a single context window. When it silently drops inflight issues:
- Partially-implemented issues accumulate: code changes are written but commits, docs, and `status=done` are never set
- The failure is invisible: no error, no log entry, no retry — discoverable only by manual diff of `autodev-inflight` vs `autodev-queue.txt`
- Compounds across runs: each handoff event in a multi-session sprint silently drops one more issue

## Proposed Solution

_Note: `on_resume` does not exist in the FSM schema and `init` is bypassed on resume (see Root Cause). The two options below work within the current architecture._

### Option A: YAML-only — reconcile inside `implement_current` action

> **Selected:** Option A: YAML-only — reconcile inside `implement_current` action — YAML-only, contained to a single file, reusing existing inflight-read and queue-prepend idioms already in `autodev.yaml`.

Prepend inflight-reconciliation at the top of the `implement_current` action in `scripts/little_loops/loops/autodev.yaml`. Since `current_state = "implement_current"` is saved at handoff time, this block runs naturally on the first iteration of every resumed run. The `$INFLIGHT != $CURRENT` guard makes it a no-op on normal (non-interrupted) runs where inflight equals the issue about to be implemented.

```bash
# BUG-1870: re-queue any stale inflight issue left by a prior handoff.
# On resume, autodev-inflight may hold an issue that was dequeued-but-
# not-yet-implemented when the previous session was interrupted.
# init is bypassed on resume, so this guard runs at implement_current entry.
INFLIGHT=$(cat "${context.run_dir}/autodev-inflight" 2>/dev/null | tr -d '[:space:]')
CURRENT="${captured.input.output}"
if [ -n "$INFLIGHT" ] && [ "$INFLIGHT" != "$CURRENT" ]; then
  STATUS=$(ll-issues show "$INFLIGHT" --json \
    | python3 -c "import json,sys; print(json.load(sys.stdin).get('status','open'))" 2>/dev/null || echo "open")
  if [ "$STATUS" != "done" ] && [ "$STATUS" != "cancelled" ]; then
    echo "$INFLIGHT" | cat - "${context.run_dir}/autodev-queue.txt" \
      > "${context.run_dir}/autodev-queue.tmp" \
      && mv "${context.run_dir}/autodev-queue.tmp" "${context.run_dir}/autodev-queue.txt"
  fi
fi
ll-auto --only "$CURRENT"
```

**Trade-offs**: YAML-only, no Python changes required. Runs on every `implement_current` entry, but the `$INFLIGHT != $CURRENT` guard makes it a no-op for normal runs. Requires that `ll-issues show --json` emits a JSON object with a `status` field — verify this in practice.

### Option B: Python — add `on_resume` shell hook to FSM schema

Add an `on_resume:` shell action field to `FSMLoop` in `scripts/little_loops/fsm/schema.py`, have `PersistentExecutor.resume()` execute it before calling `run()`, then use it in `autodev.yaml`:

```yaml
# In autodev.yaml at the top level (alongside on_handoff):
on_resume: |
  INFLIGHT=$(cat "${context.run_dir}/autodev-inflight" 2>/dev/null | tr -d '[:space:]')
  if [ -n "$INFLIGHT" ]; then
    STATUS=$(ll-issues show "$INFLIGHT" --json \
      | python3 -c "import json,sys; print(json.load(sys.stdin).get('status','open'))" 2>/dev/null || echo "open")
    if [ "$STATUS" != "done" ] && [ "$STATUS" != "cancelled" ]; then
      echo "$INFLIGHT" | cat - "${context.run_dir}/autodev-queue.txt" \
        > "${context.run_dir}/autodev-queue.tmp" \
        && mv "${context.run_dir}/autodev-queue.tmp" "${context.run_dir}/autodev-queue.txt"
    fi
  fi
```

**Python changes required**:
- `scripts/little_loops/fsm/schema.py:FSMLoop` — add `on_resume: str | None = None`
- `scripts/little_loops/fsm/persistence.py:PersistentExecutor.resume()` — execute `on_resume` shell action before calling `self.run(clear_previous=False)`
- `scripts/little_loops/fsm/validation.py` — allow `on_resume` as a valid top-level YAML key

**Trade-offs**: Architecturally cleaner and explicit — runs only on resume, not on every `implement_current` entry. Adds a reusable hook to the FSM framework that other loops could adopt. More invasive — requires touching Python schema, executor, and validation code.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-06-02.

**Selected**: Option A: YAML-only — reconcile inside `implement_current` action

**Reasoning**: Option A reuses three existing patterns already in `autodev.yaml` — the `cat ... 2>/dev/null | tr -d '[:space:]'` inflight-read idiom (from `done:566`), the queue-prepend via `echo "$X" | cat - queue.txt > queue.tmp && mv` (from `enqueue_children`, `enqueue_or_skip`), and the state-entry guard structure (from `decide_current:174`). The test pattern is directly available at `test_skip_inflight_shell_action_writes_skipped_and_clears_inflight` (line 2200). Option B would introduce the first top-level `FSMLoop` field holding a raw shell command string — a semantic with no analog in any existing field — plus changes across 3 Python modules and 4+ new test functions. **Implementation note**: the status check must compare against `"Completed"` and `"Cancelled"` (the display-mapped values emitted by `ll-issues show --json`) rather than the canonical lowercase `"done"` and `"cancelled"`, or read the status directly from frontmatter via `grep`.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option A (YAML-only) | 2/3 | 3/3 | 3/3 | 2/3 | 10/12 |
| Option B (Python on_resume) | 2/3 | 1/3 | 2/3 | 1/3 | 6/12 |

**Key evidence**:
- **Option A**: Inflight-read idiom (`cat ... 2>/dev/null | tr -d '[:space:]'`) exists at `done:566`; queue-prepend exists at `enqueue_children` and `enqueue_or_skip`; state-entry guard exists at `decide_current:174`; shell-action test template at `TestAutodevLoop:2200`. Single-file YAML change.
- **Option B**: `on_max_iterations` (schema.py:912) provides the field lifecycle template, but `on_resume` would be the first FSMLoop field whose value is a raw shell command string, introducing a novel semantic; requires changes to schema.py, persistence.py, validation.py, and 4+ new test functions.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/autodev.yaml` — add reconciliation block to `implement_current` action (Option A) OR add top-level `on_resume:` field (Option B)
- `scripts/little_loops/fsm/schema.py` — Option B only: add `on_resume: str | None = None` to `FSMLoop` dataclass
- `scripts/little_loops/fsm/persistence.py` — Option B only: execute `on_resume` shell action in `PersistentExecutor.resume()` before calling `self.run()`
- `scripts/little_loops/fsm/validation.py` — Option B only: allow `on_resume` as a valid top-level YAML key

### Dependent Files (Callers/Importers)
- `scripts/little_loops/loops/autodev.yaml:init:44` — clears `autodev-inflight` via `rm -f` on fresh start (bypassed on resume)
- `scripts/little_loops/loops/autodev.yaml:dequeue_next:73` — sole write site: `printf '%s' "$CURRENT" > autodev-inflight`
- `scripts/little_loops/loops/autodev.yaml:skip_inflight:120` — clears inflight when refinement fails
- `scripts/little_loops/loops/autodev.yaml:enqueue_children` — clears inflight after parent decomposition (BUG-1226 fix)
- `scripts/little_loops/loops/autodev.yaml:enqueue_or_skip` — clears inflight on decomposition via size-review
- `scripts/little_loops/loops/autodev.yaml:recheck_after_size_review` — clears inflight on explicit skip
- `scripts/little_loops/loops/autodev.yaml:done:566` — reads inflight, warns if non-empty but does not re-queue
- `scripts/little_loops/fsm/executor.py:_handle_handoff()` — saves `final_state = self.current_state` at handoff; this is what is restored as `current_state` on resume
- `scripts/little_loops/fsm/persistence.py:PersistentExecutor.resume()` — restores executor state and calls `run(clear_previous=False)`; no pre-resume hook currently
- `scripts/little_loops/fsm/handoff_handler.py:HandoffHandler._spawn_continuation()` — spawns `ll-loop resume autodev` as a detached subprocess
- `scripts/little_loops/cli/loop/lifecycle.py:cmd_resume()` — re-injects `run_dir` into context before calling `executor.resume()`

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/loop/_helpers.py` — calls `.resume()` method on executor; sits between `cmd_resume()` and `PersistentExecutor.resume()` — verify whether on_resume hook execution is visible here or only inside `persistence.py`
- `scripts/little_loops/cli/loop/run.py` — creates and runs `PersistentExecutor` instances; handles the `mode="resume"` dispatch path via `run_foreground()`

### Similar Patterns
- BUG-1226 (done): autodev in-flight state loss pattern — see its fix for consistency
- BUG-1759 (done): handoff forwarding — the fix is the layer this builds on

### Tests
- `scripts/tests/test_builtin_loops.py:TestAutodevLoop` — structural and routing tests for `autodev.yaml` states; add a test verifying the reconciliation block is present in `implement_current` (Option A) or that `on_resume` fires before `run()` (Option B)
- `scripts/tests/test_handoff_handler.py:TestHandoffHandler` — handoff spawning behavior
- `scripts/tests/test_cli_loop_background.py:test_resume_subcommand_spawns_resume()` — resume command invocation path
- Manual: run autodev with forced mid-implementation interrupt and confirm inflight issue appears at head of queue in the continuation run

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_builtin_loops.py:TestAutodevLoop` — **new shell-action execution test** for the reconciliation block (both options): set up `run_dir/autodev-inflight` = `"ENH-0099"`, `autodev-queue.txt` = `"ENH-0100"`, `CURRENT` = `"ENH-0042"` (different from inflight); run the `implement_current` action via `bash -c` after substituting `${context.run_dir}` / `${captured.input.output}`; assert `ENH-0099` is prepended to queue ahead of `ENH-0100`. Also test the no-op case (inflight == CURRENT). Follow the exact pattern of `test_skip_inflight_shell_action_writes_skipped_and_clears_inflight` (line 2200)
- `scripts/tests/test_builtin_loops.py:TestBuiltinLoopFiles.test_all_pass_validation` — **may break** (Option B only): if `on_resume:` is added to `autodev.yaml` but `KNOWN_TOP_LEVEL_KEYS` in `validation.py` is not updated, this test will surface an "Unknown top-level keys" WARNING; ensure `KNOWN_TOP_LEVEL_KEYS` is updated before adding the YAML field
- `scripts/tests/test_fsm_schema.py:TestFSMLoop` — **new tests to write** (Option B only): `FSMLoop.on_resume` field roundtrip, omit-when-None, and `from_dict` reads it. Follow pattern of `test_roundtrip_on_max_iterations` (line 805) and `test_on_max_iterations_omitted_when_none` (line 824)
- `scripts/tests/test_fsm_validation.py` — **new test to write** (Option B only): `test_on_resume_recognized_as_top_level_key` — follows exact pattern of `test_on_max_iterations_recognized_as_top_level_key` (line 1248)
- `scripts/tests/test_fsm_persistence.py:TestPersistentExecutor` — **new test to write** (Option B only): verify `on_resume` shell action executes before `run()` is called; follow pattern of `test_resume_emits_resume_event` (line 828) — build executor with FSM whose `on_resume` contains a known shell command, call `executor.resume()`, assert the mock runner's call list includes the on_resume action first

### Documentation

_Option A (YAML-only): no doc changes required._

_Wiring pass added by `/ll:wire-issue` — Option B only (if `on_resume` is added to FSM schema):_
- `docs/generalized-fsm-loop.md` — `## Universal FSM Schema` section enumerates all recognized optional loop-level settings (currently lists `on_handoff` but not `on_resume`); add `on_resume` to the field list
- `docs/reference/API.md` — `#### FSMLoop` section (line ~4040) lists all dataclass fields; add `on_resume: str | None = None` entry alongside `on_handoff` and `on_max_iterations`
- `docs/guides/LOOPS_GUIDE.md` — `### Handoff Behavior` section describes the resume lifecycle; update the sentence "On resume, the engine re-enters the state where the handoff occurred" to note that `on_resume` fires first if defined
- `skills/create-loop/reference.md` — `#### on_handoff (Optional)` section (line ~513) in the loop authoring reference; add a new `#### on_resume (Optional)` section after it describing the hook contract (inline shell string, runs before `run(clear_previous=False)`, `${context.run_dir}` is available)
- `docs/reference/EVENT-SCHEMA.md` — `### loop_resume` section (line ~626) notes that the event fires "before execution continues"; optionally clarify that `on_resume` runs in the window between state restoration and execution resumption

### Configuration
- N/A

## Implementation Steps

_Steps below are for Option A (YAML-only). If Option B is selected, adjust steps 1–2 to modify `schema.py`, `persistence.py`, and `validation.py` first, then add the `on_resume:` key to `autodev.yaml` instead of patching `implement_current`._

1. **Verify `ll-issues show --json`** emits a JSON object with a `status` field: run `ll-issues show <any-open-issue-id> --json | python3 -c "import json,sys; print(json.load(sys.stdin).get('status'))"` and confirm it prints the canonical status string
2. **Modify `scripts/little_loops/loops/autodev.yaml:implement_current`** — replace the single-line `action: "ll-auto --only ${captured.input.output}"` with a multi-line shell action that prepends the `$INFLIGHT != $CURRENT` reconciliation block before the `ll-auto` call (see Option A in Proposed Solution)
3. **Validate resume reconciliation**: start `ll-loop run autodev "ID1,ID2"`, force a handoff during `implement_current` for ID1 (e.g., via a short context-limit override or manual `CONTEXT_HANDOFF:` injection), inspect `autodev-inflight` and `autodev-queue.txt` in the run dir, then run `ll-loop resume autodev` and confirm ID1 is prepended to the queue ahead of ID2
4. **Validate no-op on fresh runs**: run `ll-loop run autodev "ID1"` without interruption; confirm the reconciliation block exits cleanly on the `$INFLIGHT == $CURRENT` equality check without prepending anything
5. **Validate done-before-handoff regression**: if an issue is already `done` when reconciliation runs, confirm it is not re-queued (status check returns `"done"` → guard skips the prepend)
6. **Add or update test** in `scripts/tests/test_builtin_loops.py:TestAutodevLoop` verifying that the `implement_current` action contains the reconciliation block and that routing (`on_yes: dequeue_next`, `on_no: dequeue_next`, `on_error: done`) is preserved

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

7. **(Both options) Add shell-action execution test** in `scripts/tests/test_builtin_loops.py:TestAutodevLoop` — write a test that runs the `implement_current` action via `bash -c` with a mock `run_dir`, verifying the reconciliation logic prepends the stale inflight issue and is a no-op when inflight == CURRENT. Follow the pattern of `test_skip_inflight_shell_action_writes_skipped_and_clears_inflight` (line 2200)
8. **(Option B only) Add FSMLoop field tests** in `scripts/tests/test_fsm_schema.py:TestFSMLoop` — roundtrip, omit-when-None, and from_dict reads `on_resume`; follow pattern of `test_roundtrip_on_max_iterations` (line 805)
9. **(Option B only) Add KNOWN_TOP_LEVEL_KEYS test** in `scripts/tests/test_fsm_validation.py` — `test_on_resume_recognized_as_top_level_key` following pattern of `test_on_max_iterations_recognized_as_top_level_key` (line 1248); do this before adding `on_resume:` to autodev.yaml or `TestBuiltinLoopFiles.test_all_pass_validation` will fail
10. **(Option B only) Add pre-run hook test** in `scripts/tests/test_fsm_persistence.py:TestPersistentExecutor` — verify `on_resume` executes before `run()` is called; follow pattern of `test_resume_emits_resume_event` (line 828)
11. **(Option B only) Update docs**: `docs/generalized-fsm-loop.md` (Universal FSM Schema), `docs/reference/API.md` (FSMLoop fields), `docs/guides/LOOPS_GUIDE.md` (Handoff Behavior), `skills/create-loop/reference.md` (on_resume Optional section after on_handoff)

## Impact

Low frequency (only triggered when `implement_current` is interrupted mid-run), but when it occurs the inflight issue is silently left in a partially-implemented state with no follow-up. Discoverable only by manual inspection of `autodev-inflight` vs `autodev-queue.txt` after a run.

- **Priority**: P3 — Low-frequency but silent data loss; no mechanism to detect or recover automatically
- **Effort**: Small — localized change to a single FSM hook or state guard
- **Risk**: Low — reconciliation is additive; if inflight is already `done`, it's a no-op
- **Breaking Change**: No

## Related

- BUG-1759 (done): ll-auto handoff forwarding to outer FSM — the fix made handoff detection work; this bug is the next layer (re-queue on resume)
- BUG-1226 (done): autodev drops breakdown result on timeout between `refine_current` and `copy_broke_down` — similar in-flight state loss pattern

---

**Open** | Created: 2026-06-02 | Priority: P3


## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-06-02_

**Readiness Score**: 95/100 → PROCEED
**Outcome Confidence**: 74/100 → MODERATE

### Outcome Risk Factors
- **Open decision on implementation approach** — Option A (YAML-only, no Python changes) vs Option B (Python schema extension). This is an open decision that should be resolved before implementing; choosing wrong requires undoing schema work or refactoring YAML later.
- **New tests must be authored** — the reconciliation behavior has no existing test coverage; `test_skip_inflight_shell_action_writes_skipped_and_clears_inflight` (line 2200) is the pattern to follow, but the test doesn't exist yet and must be written as part of the implementation.

## Resolution

Fixed by prepending a reconciliation block to the `implement_current` state action in `autodev.yaml`. On resume after a context handoff, `init` is bypassed and `autodev-inflight` may hold a stale issue ID. The block reads `autodev-inflight`, compares it to `CURRENT` (`${captured.input.output}`), and if they differ and the inflight issue's status is not `done`/`cancelled`, prepends the issue to `autodev-queue.txt` before running `ll-auto --only "$CURRENT"`. The `$INFLIGHT != $CURRENT` guard makes this a no-op on normal (non-resumed) runs.

Added 3 shell-action tests in `TestAutodevLoop`: prepend on stale inflight, no-op when inflight equals current, skip if already done.

## Session Log
- `/ll:ready-issue` - 2026-06-02T23:08:06 - `813708df-6857-4ab9-83bf-d7a78ef1c948.jsonl`
- `/ll:confidence-check` - 2026-06-02T23:59:00Z - `813708df-6857-4ab9-83bf-d7a78ef1c948.jsonl`
- `/ll:decide-issue` - 2026-06-02T23:02:28 - `35612592-bad3-4a2e-856d-d8a3b999fd76.jsonl`
- `/ll:confidence-check` - 2026-06-02T23:30:00Z - `7d4253d1-4f98-4f64-bcb2-83f0e4ed7660.jsonl`
- `/ll:wire-issue` - 2026-06-02T22:55:17 - `7d4253d1-4f98-4f64-bcb2-83f0e4ed7660.jsonl`
- `/ll:refine-issue` - 2026-06-02T22:49:42 - `21850d04-bdf9-4e28-bf74-f68eaaaed883.jsonl`
- `/ll:verify-issues` - 2026-06-02T22:48:04 - `21850d04-bdf9-4e28-bf74-f68eaaaed883.jsonl`
- `/ll:format-issue` - 2026-06-02T13:18:33 - `1a1ea335-7acb-47eb-a0a7-9d25c099f34d.jsonl`
