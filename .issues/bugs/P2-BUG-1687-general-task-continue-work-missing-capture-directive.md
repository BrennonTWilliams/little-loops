---
captured_at: '2026-05-24T22:52:33Z'
completed_at: '2026-05-25T01:24:00Z'
discovered_date: 2026-05-24
discovered_by: capture-issue
status: done
confidence_score: 100
outcome_confidence: 97
score_complexity: 22
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
---

# BUG-1687: `general-task` `continue_work` missing `capture: execute_result` freezes `check_done` scope

## Summary

In `scripts/little_loops/loops/general-task.yaml`, the `execute` state captures
its output to `execute_result` (line 91), but `continue_work` (lines 259-283)
has no `capture:` directive. `check_done` reads
`${captured.execute_result.output}` to extract `LAST_STEP` / `LAST_FILES` (lines
99-100) and uses those to scope delta verification (lines 112-122). Because
`continue_work` never refreshes the capture, every iteration after the first
`execute` reuses the same iteration-1 `LAST_STEP` / `LAST_FILES` values. Verification
becomes a degenerate gate — `check_done` perpetually re-scopes to the same two
files and the same DoD sections, never touching the criteria that subsequent
`continue_work` iterations actually produced.

Observed in the `2026-05-24T204014` `general-task` run: the loop completed
substantive work (yt-dlp migration, CSV import script, dashboard, index,
directory structure, config cleanup) but terminated at `max_iterations: 100`
with 13/30 DoD criteria still `[ ]` even though on-disk evidence showed many
were satisfied. `check_done` could only ever mark DoD sections 2 and 4 as `[x]`
because LAST_STEP/LAST_FILES pointed exclusively at
`youtube_playlists.yaml` and `Watch-Later-Import/` (the iteration-1 outputs).

## Steps to Reproduce

1. Run a `general-task` invocation whose DoD spans more files than the first
   `execute` step touches:
   `ll-loop run general-task --input "<multi-file task>" --max-iterations 100`
2. Let `execute` complete one plan step (any step that writes to file A).
3. Observe that `check_done` captures `execute_result` with
   `LAST_FILES: A`.
4. Allow the loop to enter `continue_work` and complete plan steps that
   modify files B, C, D.
5. Observe: every subsequent `check_done` still extracts `LAST_FILES: A`
   from the (stale) `captured.execute_result.output`, and per the delta-scope
   prompt (lines 112-122) only marks DoD criteria touching A.
6. `count_done.total` never reaches 0; loop terminates by `max_iterations`.

## Root Cause

- **File**: `scripts/little_loops/loops/general-task.yaml`
- **Anchor**: state `continue_work` (lines 259-283)
- **Cause**: `continue_work` produces fresh work and emits no LAST_STEP /
  LAST_FILES trailing lines, AND has no `capture:` directive to overwrite the
  `execute_result` capture. So `check_done` (which interpolates
  `${captured.execute_result.output}`) reads frozen iteration-1 data forever.
  The loop's design assumes every work-producing state refreshes the capture,
  but only `execute` does.

## Current Behavior

- `execute` runs once and sets `captured.execute_result = <output with LAST_STEP/LAST_FILES>`.
- All subsequent work happens in `continue_work` (no capture, no trailing
  LAST_STEP/LAST_FILES lines).
- `check_done` reads the stale capture every iteration and scopes verification
  to the same iteration-1 step/files.
- `count_done` evaluates `total > 0` indefinitely → routes to `continue_work`
  again → cycle repeats until `max_iterations`.
- Audit of the `2026-05-24T204014` run: 23/23 `count_done` evaluations routed
  to `continue_work`; the gate is effectively dead code under the current
  design.

## Expected Behavior

After every work-producing state, the next `check_done` should see fresh
`LAST_STEP` / `LAST_FILES` reflecting what just happened. The loop should
eventually mark every satisfied DoD criterion `[x]` and route `count_done` to
`final_verify` → `done` once `total == 0`.

## Proposed Solution

Two coordinated changes to `continue_work`:

```yaml
continue_work:
  action: |
    Your task is: ${context.input}

    Read both files: ...
    [existing Case A / B / C body]

    After completing the step, print the following two lines as the very last
    output (fill in the actual step text and all files you created or modified):
    LAST_STEP: <the step text you just completed>
    LAST_FILES: <space-separated list of file paths you created or modified>
  action_type: prompt
  capture: execute_result     # NEW — overwrite stale capture so check_done sees current work
  next: check_done
  on_error: diagnose
```

- Add `capture: execute_result` so `check_done`'s interpolation reads fresh data.
- Add the LAST_STEP / LAST_FILES trailing-output contract (mirrors `execute`
  lines 86-89) so the capture has the keys `check_done` expects.

Alternative: rename the capture key per-state (e.g. `continue_work_result`)
and have `check_done` interpolate `${captured.last_work.output}` via an
alias. Rejected for now — overwriting the single `execute_result` key keeps
`check_done` simple and matches the existing pattern.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/general-task.yaml` — `continue_work` state

### Dependent Files (Callers/Importers)
- N/A — YAML config; no Python imports

### Similar Patterns
- Check whether sibling harness loops have the same "execute captures, follow-up
  state doesn't" gap. Candidates: `loops/recursive-refine.yaml`,
  `loops/rn-refine.yaml`, `loops/rn-plan.yaml`, anywhere `${captured.*}` is
  read by a downstream state.

#### Codebase Research Findings

_Added by `/ll:refine-issue` — sibling loop audit:_

- `scripts/little_loops/loops/recursive-refine.yaml` — `dequeue_next` (line 103) sets `capture: input` each cycle before downstream states; no stale-capture gap.
- `scripts/little_loops/loops/rn-refine.yaml` — `init` sets `capture: run_dir` once (a stable path prefix, never re-read as action output); no analogous pattern.
- `scripts/little_loops/loops/rn-plan.yaml` — no `${captured.*}` interpolation in prompt actions; uses file artifacts for inter-state data; no analogous pattern.
- `scripts/little_loops/loops/harness-single-shot.yaml:36` — `execute` with `capture: execute_result`; reference example of the same key name used correctly by a single-work-state loop.
- **Conclusion**: stale-capture defect is unique to `general-task.yaml` among the candidate loops.

### Tests
- `scripts/tests/test_general_task_loop.py` (or equivalent) — add a regression
  test asserting that a multi-iteration run sees `LAST_FILES` change after
  `continue_work` runs. If no such test file exists, the simplest harness is
  an `ll-loop` integration test that mocks the host.

#### Codebase Research Findings

_Added by `/ll:refine-issue` — test file confirmed to exist:_

- `scripts/tests/test_general_task_loop.py` **exists**. The regression test should mirror `TestChange5ExecuteCapture` (line 198), which asserts `execute` has `capture: execute_result` and prompts for `LAST_STEP`/`LAST_FILES`. A parallel `TestChange_ContinueWorkCapture` class should assert:
  1. `states["continue_work"].get("capture") == "execute_result"`
  2. `"LAST_STEP" in states["continue_work"]["action"]`
  3. `"LAST_FILES" in states["continue_work"]["action"]`
- Pattern reference: `scripts/tests/test_builtin_loops.py:TestHarnessCapture` (line 894) shows parametric `capture: execute_result` assertion style.
- No subprocess mocking needed — pure YAML structural assertions via `yaml.safe_load`.

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_GUIDE.md` — line 338 describes `execute` as the sole producer of `LAST_STEP`/`LAST_FILES` for delta-scoped verification; after the fix `continue_work` becomes a second producer under the same contract. Line 346 (step 5 "Continue") makes no mention of the trailing-output protocol. Both passages require updating to reflect that any work-producing state (not only `execute`) must emit LAST_STEP/LAST_FILES. [Agent 2 finding]

### Configuration
- N/A

## Implementation Steps

1. Edit `scripts/little_loops/loops/general-task.yaml` `continue_work` state (lines 259-283):
   append `capture: execute_result` and add LAST_STEP/LAST_FILES trailing-output
   instructions to the prompt (mirror `execute` lines 86-89).
2. Add `TestChange_ContinueWorkCapture` to `scripts/tests/test_general_task_loop.py`,
   modelled on `TestChange5ExecuteCapture` (line 198): assert `continue_work["capture"] == "execute_result"`,
   `"LAST_STEP" in continue_work["action"]`, and `"LAST_FILES" in continue_work["action"]`.
3. Re-run the same input task that produced the stuck `2026-05-24T204014`
   run; confirm it now terminates at `done` (or at least makes monotonic
   `count_done.total` progress) instead of hitting `max_iterations`.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

4. Update `docs/guides/LOOPS_GUIDE.md` — revise line 338 (step 2 "Delta-scoped criterion verification") to state that any work-producing state (`execute` or `continue_work`) must emit LAST_STEP/LAST_FILES, not only `execute`; add a note on line 346 (step 5 "Continue") explaining the trailing-output contract that `continue_work` now carries.

## Impact

- **Priority**: P2 — Loop is functionally broken for any task whose DoD spans
  more files than the first `execute` step touches. Substantive work succeeds
  but the loop cannot recognize completion; users waste ~85 min and 100
  iterations per stuck run. Not P1 only because the on-disk work is correct
  — the failure is in the verification gate.
- **Effort**: Small — 2-line YAML change plus a regression test.
- **Risk**: Low — change is additive (adds a capture, adds two trailing-output
  lines to a prompt). No state graph changes. The new capture overwrites
  what was a frozen stale value, so worst case is parity with current
  behavior for the iteration-1 scope.
- **Breaking Change**: No

## Related Key Documentation

- [[BUG-1628]] — earlier `general-task` deadlock (plan exhaustion); fixed but
  did not address the capture chain. This issue is the next-discovered
  structural defect in the same state.
- [[BUG-880]] — `check_semantic` evidence wiring (wizard-generated); same
  family of "downstream state reads stale capture" defect but a different
  code path. Solution pattern (`capture:` + `source:`/interpolation) applies
  here.
- [[ENH-1671]] — delta-aware `check_done` prompt; relies on `LAST_STEP` /
  `LAST_FILES` being fresh, which this bug breaks.
- [[BUG-1674]] — stall detector blind to non-eval state progress; explains
  why the existing stall detector did not catch this oscillation (plan file
  was being appended to each iteration, defeating `progress_paths`).

## Labels

`bug`, `captured`, `general-task`, `fsm-loop`, `stale-capture`

## Session Log
- `/ll:manage-issue` - 2026-05-25T01:24:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/bad241f5-ea52-4a30-8eea-f8130567f56b.jsonl`
- `/ll:ready-issue` - 2026-05-25T01:22:34 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/dc4af044-51b8-4531-9236-c902ec2a706e.jsonl`
- `/ll:confidence-check` - 2026-05-24T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3c4298e6-aea0-4a59-b135-36570bb11394.jsonl`
- `/ll:wire-issue` - 2026-05-25T01:19:30 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/779600d2-a095-4582-b268-4bc77de7f312.jsonl`
- `/ll:refine-issue` - 2026-05-25T01:12:46 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1241a0cb-721c-46ef-a789-21d2ae204723.jsonl`
- `/ll:format-issue` - 2026-05-24T23:53:40 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3421ff4b-05fc-4e80-bb1d-cb7ee266a185.jsonl`
- `/ll:capture-issue` - 2026-05-24T22:52:33Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b11535be-d77b-46f8-a622-5a6525775721.jsonl`

---

**Open** | Created: 2026-05-24 | Priority: P2
