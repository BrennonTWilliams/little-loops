---
id: ENH-2366
type: ENH
title: interactive-component-generator — diagnose root-cause access and empty-vs-drained queue disambiguation
priority: P3
status: open
captured_at: '2026-06-28T06:30:00Z'
discovered_date: 2026-06-28
discovered_by: audit-loop-run
labels:
- captured
- fsm
- harness
- loops
- interactive-component-generator
- observability
relates_to:
- ENH-2365
decision_needed: false
confidence_score: 90
---

# ENH-2366: interactive-component-generator — diagnose root-cause access and empty-vs-drained queue disambiguation

## Summary

The `2026-06-28T054140` audit of `interactive-component-generator`
(`scripts/little_loops/loops/interactive-component-generator.yaml`) raised five
proposals. The P0 (`init` captured an unparseable `run_dir`) has been **fixed**
separately — it was an over-escaped-shell `$$` PID-expansion bug, now corrected in
all three generator loops and gated by `ll-loop validate` rule MR-9
(`shell_pid_ok`). This issue captures the two remaining **valid, loop-local**
proposals. Audit proposal #5 (no `summary.json` on terminal) is tracked
generically by [[ENH-2365]]; proposal #2 ("verdict laundering") was assessed and
is **not a defect** — see below.

## Motivation

Accurate failure diagnosis in the `interactive-component-generator` loop is blocked by two missing context signals: the `diagnose` state lacks `run_dir` access (leading to misattributed root causes) and `check_any_built` cannot distinguish planning failures from build failures, producing generic operator guidance that forces manual log inspection to determine the actual cause.

## Current Behavior

- The `diagnose` state re-reads `scoreboard.jsonl` / `comp-*/critique.md` but has no access to the captured `run_dir` value or the failed-state/exit-code events. In the audited run it correctly observed "zero comp-* directories" but misattributed the cause to "iteration/step budget exhausted" when only 7 of 120 steps were consumed.
- `check_any_built` routes both (a) empty-queue-from-start (planning failure) and (b) drained-queue-without-passes (build failure) through the same `check_any_built → diagnose` path, making the failure type ambiguous for operators.

## Expected Behavior

- The `diagnose` state receives the captured `run_dir` value and a short failure summary (failed state names + exit codes), and verifies whether `run_dir` resolves to an existing writable directory before attributing blame to budget exhaustion.
- A `failure_reason` discriminator set by `pop_next`/`check_any_built` allows `diagnose` to give targeted recommendations: planning-failure guidance when the queue was empty from the start, build-failure guidance when it drained without any component passing smoke.

## Proposal A (audit #3) — `diagnose` cannot see the real failure cause

The `diagnose` state is reachable when the build phase produced no components. Its
prompt re-reads `scoreboard.jsonl` / `comp-*/critique.md` but has **no access** to
the captured `run_dir` value or the failed-state/exit-code events. In the audited
run it correctly observed "zero comp-* directories" but misattributed the cause to
"iteration/step budget exhausted" when only 7 of 120 steps were consumed.

**Expected:** the diagnose prompt should be given the captured run_dir value and a
short failure summary (failed state names + exit codes), and should verify whether
the captured run_dir resolves to an existing writable directory before blaming
budget exhaustion.

## Proposal B (audit #4) — `check_any_built` collapses empty-queue and drained-queue

After the run_dir fix, `pop_next` can exit non-zero for two distinct reasons:
(a) the queue was empty from the start (a planning failure), (b) the queue drained
without any component passing smoke (a build failure). Both route to the same
`check_any_built → diagnose` path, so the operator cannot tell a planning failure
from a build failure. Distinguish them (e.g. a `failure_reason` param) so diagnose
can give a targeted recommendation.

## Non-defect note (audit #2) — verdict laundering is a false positive

The audit flagged `build_component.on_yes == on_no == on_error == smoke_component`
as silent sub-loop verdict laundering. It is not: `smoke_component` does
`page.goto('file://…/index.html')`, which **throws** when the child produced no
`index.html` → caught by the `.catch()` → writes `SMOKE_FAIL:harness:…` to
`smoke.txt`, which `record` then logs as `smoke=SMOKE_FAIL`. A failed/crashed child
is recorded as a FAIL, not laundered. No routing change is warranted. (A
`subloop_outcome_<id>` sidecar marker could be added purely to quiet the
audit-loop-run laundering checker, but it is cosmetic.)

## Proposed Solution

Two targeted changes to `interactive-component-generator.yaml`:

**A — Enrich `diagnose` with failure context:** Extend the `diagnose` action prompt to include the captured `run_dir` value and a failure summary (failed state names + exit codes). Add a "verify the path resolves" instruction so the state can distinguish a missing `run_dir` from budget exhaustion. See `general-task.yaml` `diagnose` for the existing pattern (enumerates terminal states).

**B — Add `failure_reason` discriminator:** Set a `failure_reason` context variable in `pop_next`/`check_any_built` to distinguish empty-queue (planning failure) from drained-queue (build failure). Thread this into the `diagnose` routing so each failure mode receives a targeted recommendation.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/interactive-component-generator.yaml` — extend
  `diagnose` action with captured run_dir + failure summary and a "verify the path
  resolves" instruction; add a `failure_reason` discriminator feeding
  `check_any_built`/`diagnose`.

### Similar Patterns
- `scripts/little_loops/loops/general-task.yaml` `diagnose` — enumerates terminal
  states; same pattern for surfacing failure context.
- `scripts/little_loops/loops/rn-refine.yaml` `route_decomposed` / `route_leaf` / `route_capped` (lines 146–171) — three chained `output_contains` routing states reading the same `captured` variable with different `pattern:` values; canonical pattern for multi-branch discrimination from a single captured output.
- `scripts/little_loops/loops/context-health-monitor.yaml` `route` / `route_scratch` (lines 46–62) — two chained routing states reading `${captured.diagnosis.output}`; simpler two-branch version of the same pattern.

### Tests
- N/A — YAML loop definition change; validated via `ll-loop validate interactive-component-generator`

### Documentation
- N/A

### Configuration
- `scripts/little_loops/loops/lib/common.yaml` — defines the `shell_exit` fragment used by both `pop_next` and `check_any_built`; adding `capture:` to a `shell_exit` fragment state is valid (capture is independent of evaluate).
- N/A

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**State anchors in `interactive-component-generator.yaml`:**
- `pop_next` — `shell_exit` fragment; exits non-zero for BOTH "queue empty from start" AND "queue fully drained after build"; `capture: current_id`; `on_no: check_any_built`. Single `exit 1` path — no side-effect records which case fired.
- `check_any_built` — `shell_exit` fragment; tests `-s scoreboard.jsonl`; routes `on_no: diagnose` (currently ambiguous between the two failure modes).
- `diagnose` — `action_type: prompt`; references `${captured.run_dir.output}` only; unconditional `next: failed`. Currently has no access to failed-state names, exit codes, or `failure_reason`.

**Key structural fact — `${context.run_dir}` is always available:**
The FSM runner injects `run_dir` into `fsm.context` before execution begins (`scripts/little_loops/cli/loop/run.py`). Even though `interactive-component-generator.yaml` also captures `run_dir` via its `init` shell state (accessible as `${captured.run_dir.output}`), `${context.run_dir}` is available regardless of whether `init` captured successfully. Adding `${context.run_dir}` to the `diagnose` prompt provides a reliable always-present fallback for path resolution.

**Current `diagnose` prompt (verbatim):**
```
The loop could not produce a combined artifact.

Diagnose: read ${captured.run_dir.output}/scoreboard.jsonl (if present) and any
${captured.run_dir.output}/comp-<id>/critique.md to summarize why each candidate
failed. Identify the most likely root cause and write a one-paragraph diagnostic
the operator can act on (e.g. re-run, widen n_build, or relax the brief).
```

**`general-task.yaml` `diagnose` pattern (the reference):** References `${context.run_dir}`, explicitly lists all state names where failure could occur, and adds path-resolution artifact checks (`plan.md`, `dod.md`).

**Exhaustive state list for `diagnose` prompt enumeration:**
`init, rank, pop_next, prep_component, build_component, smoke_component, record, check_any_built, select_best, compose, verify_final, revise`

**Concrete `failure_reason` discriminator approach (marker-file pattern):**
- Modify `pop_next` action: after the `tail -n +2 ... mv` step (on the successful-pop path, before `printf`), add `touch "${captured.run_dir.output}/.any_popped"`. This marker is only written when exit is 0 (a real item was popped). Keeps `shell_exit` fragment and exit-code evaluation unchanged.
- Add a new `classify_failure` plain shell state (no evaluate, unconditional `next: diagnose`): checks for `.any_popped` marker and captures `failure_reason` token (`PLANNING_FAILURE` or `BUILD_FAILURE`).
- Update `check_any_built` routing: `on_no: classify_failure` and `on_error: classify_failure` instead of `diagnose`.
- The `diagnose` prompt reads `${captured.failure_reason.output}` for targeted guidance.

## Scope Boundaries

- **Audit proposal #2 (verdict laundering)** — assessed as not a defect; `smoke_component` correctly records failed children as FAIL via the `.catch()` path. No routing change warranted.
- **Audit proposal #5 (`summary.json` on terminal done)** — tracked separately as ENH-2365; generic across all generator loops.
- **MR-9 `$$`/`$$(` over-escape fix** — already applied to all three generator loops and gated by `ll-loop validate`; not part of this issue.
- **JS under-escape in shell heredocs** (inside `smoke_component`/`verify_final`) — flagged in `## Notes` for follow-up but explicitly out of scope here.

## Implementation Steps

1. Extend `diagnose` action in `interactive-component-generator.yaml`: add captured `run_dir` and failure summary (failed state names + exit codes) to the prompt context; add path-resolution verification instruction.
2. Add a `failure_reason` context variable set by `pop_next`/`check_any_built` to discriminate empty-queue vs. drained-queue outcomes.
3. Update `diagnose` routing to branch on `failure_reason` for targeted recommendations.
4. Validate with `ll-loop validate interactive-component-generator` (MR-1 through MR-9 checks).

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

Concrete step sequence:

1. **Enrich `diagnose` action prompt** (`diagnose` state):
   - Add `${context.run_dir}` as a reliable path reference alongside `${captured.run_dir.output}` (runner-injected; always present even if `init` failed — addresses the audited misattribution).
   - Enumerate all states where failures can occur: `init, rank, pop_next, prep_component, build_component, smoke_component, record, check_any_built, select_best, compose, verify_final, revise` (following the `general-task.yaml` `diagnose` pattern).
   - Add path-resolution verification: "verify whether `${captured.run_dir.output}` resolves to an existing directory before attributing blame to budget exhaustion."
   - Add conditional guidance: "if `${captured.failure_reason.output}` is `PLANNING_FAILURE`, provide planning-failure guidance (check `rank` prompt, widen search); if `BUILD_FAILURE`, provide build-failure guidance (re-run, widen `n_build`, relax the brief)."

2. **Modify `pop_next` action** to write a marker on successful pop:
   - After `tail -n +2 "$QUEUE" > "$QUEUE.tmp" && mv "$QUEUE.tmp" "$QUEUE"` and before `printf '%s\n' "$CID"`, add: `touch "${captured.run_dir.output}/.any_popped"`
   - Marker is only written on exit-0 (successful pop). Keeps `shell_exit` fragment and exit-code routing unchanged.

3. **Add new `classify_failure` shell state** (plain shell, `next: diagnose`, `capture: failure_reason`):
   ```yaml
   classify_failure:
     action_type: shell
     action: |
       if [ -f "${captured.run_dir.output}/.any_popped" ]; then
         echo "BUILD_FAILURE"
       else
         echo "PLANNING_FAILURE"
       fi
     capture: failure_reason
     next: diagnose
     on_error: diagnose
   ```
   Both outcomes route to `diagnose`; the discriminator value lives in `${captured.failure_reason.output}`.

4. **Update `check_any_built` routing**: change `on_no: diagnose` → `on_no: classify_failure` and `on_error: diagnose` → `on_error: classify_failure`.

5. **Validate**: `ll-loop validate interactive-component-generator` (MR-1 through MR-9 checks).

## Impact

- **Priority**: P3 — Quality-of-life improvement for loop operators; failures remain diagnosable via manual log inspection, so this is not blocking.
- **Effort**: Small — Localized to `interactive-component-generator.yaml`; the `diagnose` enrichment pattern already exists in `general-task.yaml`.
- **Risk**: Low — No behavioral change to the happy path; all changes are confined to failure-branch routing.
- **Breaking Change**: No

## Notes

Separately observed during the MR-9 fix (out of scope here, flag for follow-up):
inside the `node -e "…"` heredocs in `smoke_component`/`verify_final`, JS like
`page.$('…')` uses a single `$(` that the surrounding shell double-quote will
command-substitute. That is the **inverse** of the MR-9 over-escape (under-escaped
JS in a shell heredoc) and is not covered by MR-9.

## Status

**Open** | Created: 2026-06-28 | Priority: P3


## Session Log
- `/ll:refine-issue` - 2026-06-28T06:32:17 - `bab668b9-d0cc-4b46-ae13-209d6d4c3d49.jsonl`
- `/ll:format-issue` - 2026-06-28T06:23:29 - `99f877ea-375e-4379-8117-c031f3ed85dd.jsonl`
