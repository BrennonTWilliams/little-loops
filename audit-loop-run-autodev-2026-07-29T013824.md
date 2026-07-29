# Audit Report: `autodev` loop run `2026-07-29T013824`

**Audit skill**: `/ll:audit-loop-run`
**Run target**: `.loops/.history/2026-07-29T013824-autodev/`
**Audit date**: 2026-07-28
**Verdict**: `phantom`

> **Note on path supplied to the skill**. The user's initial argument
> `.loops/runs/autodev-20260728T203824/` is an `ll-auto` working directory
> (gitignored), not an FSM loop history archive. The two systems share a name
> prefix but live in different locations and produce different artifacts.
> `audit-loop-run` reads `events.jsonl` + `state.json`, which only exist under
> `.loops/.history/`. The audit was run against the most recent archive,
> `.loops/.history/2026-07-29T013824-autodev/`. The run-dir
> `.loops/runs/autodev-20260728T203824/` IS this loop's `context.run_dir` (the
> loop wrote to it), but the FSM trace lives next to it under `.loops/.history/`.

---

## Summary

| Item | Value |
|---|---|
| Loop name | `autodev` |
| Run id | `2026-07-29T013824` |
| Issue input | `FEAT-108` |
| Loop iterations (parent, depth=0) | 12 |
| Sub-loop iterations (`refine-to-ready-issue`, depth=1) | 12 |
| Sub-loop iterations (`verify-confidence-scores`, depth=2) | 2 |
| Wall-clock | 2026-07-29T01:38:24 → 2026-07-29T02:12:35 (≈34 min) |
| `terminated_by` | `terminal` |
| `failure_terminal` | `false` |
| Final state | `done` |
| Action complete events | 24 |
| Threshold contract — `readiness_threshold` | 85 (default), FEAT-108 confidence=87 ✓ |
| Threshold contract — `outcome_threshold` | 65 (default), FEAT-108 outcome=78 ✓ |
| Issue artifact mutated? | Yes — `.issues/features/P2-FEAT-108-lock-protected-promotion-transaction.md` (+174 / -1) |
| Issue status after run | `open` (UNCHANGED — implementation did not close) |
| Phase 1 fault signals | 0 |
| Shallow-iteration check | `clear` (24 tool calls, threshold 30) |
| Rubric audit | 0 evaluators with `llm_structured` → no-op |
| Laundering check | 1 sub-loop state, 3 distinct `on_yes`/`on_no`/`on_error` targets → no defect |
| Issues created | 0 (report-only deliverable per user instruction) |

---

## Goal-vs-Outcome Scorecard

### Goal (verbatim from FSM `description`)

> "Targeted refine-and-implement for a specific set of issues. Accepts a single
> issue ID or a comma-separated list. Interleaves refinement and implementation:
> refines one issue; on threshold pass, implements it immediately via
> `ll-auto --only`; on decomposition into children, prepends children to the
> queue depth-first and refines them before the next sibling. First
> implementation runs as soon as the first leaf passes refinement."

### Contract

The FSM has only one top-level context key, `skip_learning_gate`. Thresholds
`readiness_threshold` and `outcome_threshold` are referenced via
`${context.*}` interpolation in action bodies and resolved at runtime from
`.ll/ll-config.json` `commands.confidence_gate` block, falling back to
`ll-issues check-readiness` defaults (85 / 65) when unset.

| Key | Source | Value | Verified? |
|---|---|---|---|
| `readiness_threshold` | `${context.readiness_threshold}` in `check_passed.action`, `check_reconcile_needed.action`, `check_readiness_for_atomic_remediation.action`, `recheck_*.action`, `regate_after_atomic_remediation.action` | 85 (default) | ✓ FEAT-108 confidence=87 |
| `outcome_threshold` | `${context.outcome_threshold}` in `check_passed.action`, `recheck_*.action`, `regate_after_atomic_remediation.action` | 65 (default) | ✓ FEAT-108 outcome=78 |
| Implementation contract | `implement_current.action`: `set -o pipefail; ll-auto --only "$CURRENT" $SKIP_FLAG 2>&1 \| tee "${context.run_dir}/ll_auto_last.txt"` | expected closure | ✗ `ll-auto` processed 0 issues (dep cycle); issue status unchanged |

### Artifacts checked

| Path | Expected mutation | Observed | Verdict |
|---|---|---|---|
| `.loops/runs/autodev-20260728T203824/autodev-passed.txt` | contains `FEAT-108` after threshold pass | `FEAT-108` ✓ | matches contract |
| `.loops/runs/autodev-20260728T203824/autodev-skipped.txt` | issue IDs that could not be processed | empty | matches contract |
| `.loops/runs/autodev-20260728T203824/ll_auto_last.txt` | `ll-auto --only FEAT-108` stdout | written, but content is `Issues processed: 0` due to dep cycle | contract violated |
| `.issues/features/P2-FEAT-108-lock-protected-promotion-transaction.md` | refine output mutates file (additive); implement closes status to `done` | refined (+174/-1: confidence 80→87, `blocked_by` added, `learning_tests_required` added, Wiring Phase 3 added); **status remains `open`** | refine partial, implement missing |

### Phase 1 fault signals (verbatim-output rule)

Per the skill's fault-signal subset, every claim below is backed by a line
actually read from `events.jsonl` / `state.json` for this run.

- **Action failures (`exit_code != 0`)** — 6 events, ALL are evaluator
  conditions returning false (e.g. `output_contains` against `SKIP_CLOSED`
  with `matched: false`; `exit_code` evaluator with `exit_code: 1`). These
  are normal control-flow fallthroughs (verdict=no → `on_no` route), not
  infrastructure failures. **None qualify as fault signals.**
- **SIGKILL / FATAL_ERROR termination** — `grep` for `SIGKILL|FATAL|OOM|max_steps_summary`
  across all 122 events returned `0` matches. **None.**
- **Evaluate error termination (`verdict == "error"`)** — 0 events. **None.**
- **Evaluate failures (`verdict == "fail"`, 3+ on the same state)** —
  `verdict=fail` count: 0. **None.**
- **Retry floods** — no `rate_limit_retries` exhaustion events; the parent FSM
  has `max_rate_limit_retries: 3` on `refine_current` only and that branch
  was never entered. **None.**
- **Sub-loop verdict discarded** — see Laundering section. **None.**
- **Throttle hard stop / hard transition** — no `throttle_stop` /
  `throttle_hard` events in JSONL. **None.**
- **Over-escaped shell / PID corruption (MR-9)** — scanned all
  `output_preview` values for `^\d{2,7}\b` and cross-referenced `action_start`
  text for `$$(` / `$$[A-Za-z_]`. **None.**

### Shallow-iteration check

```
TOOL_CALL_COUNT = 24  (action_complete events)
AUX_MUTATION_COUNT = 1  (.issues/features/P2-FEAT-108-lock-protected-promotion-transaction.md)
DIFF_STALL_PRESENT = false  (no diff_stall evaluators in this FSM)
threshold = 30 (default)
→ result = clear
```

24 < 30, so the shallow-iteration heuristic does not fire. The single
auxiliary mutation (the issue file itself) confirms the loop produced
non-trivial work.

### Verdict: `phantom`

**Rationale**: The FSM reached terminal `done` after 12 iterations and ~34
minutes. Threshold contracts WERE satisfied — FEAT-108 scored confidence 87
(≥85) and outcome 78 (≥65), both above the `ll-issues check-readiness`
defaults — and the refine step materially mutated the issue file (+174/-1
lines, including Wiring Phase 3, `blocked_by`, and `learning_tests_required`).
However, the implementation step silently failed: `ll-auto --only FEAT-108`
discovered a dependency cycle (`FEAT-108 → FEAT-123 → FEAT-122 → FEAT-108`)
and reported `Issues processed: 0`, while the action's captured `exit_code`
remained 0 (because `ll-auto` itself returned 0 — pre-flight block detection
is not a fatal error in `ll-auto`'s exit semantics). The issue's status
remains `open`. The loop's `finalize_done` still wrote `Passed (1): FEAT-108`
because `check_passed` writes to `passed.txt` BEFORE `implement_current`
runs, and the warning `WARNING: in-flight issue not resolved: FEAT-108 (re-queue to retry)` was informational, not a verdict override.

Per the audit rubric: threshold verification is genuine (a CLI tool, not an
`llm_structured` judge), but the primary deliverable — issue closure — was not
achieved, and the success signal is ungrounded: it was emitted at
threshold-pass time, not at verified-closure time.

### Verbatim evidence (the Output Evidence Contract)

**Threshold-pass artifact** (`/Users/brennon/AIProjects/animation/sketch-storyboards/.loops/runs/autodev-20260728T203824/autodev-passed.txt`):

> ```
> FEAT-108
> ```

**Finalize summary** (captured `output_preview` of `finalize_done` action):

> ```
> === Autodev Summary ===
>
> Passed       (1): FEAT-108
> Skipped      (0): none
> WARNING: in-flight issue not resolved: FEAT-108 (re-queue to retry)
> ```

**Implement step output** (captured `output_preview` of `implement_current`
action — full `ll-auto` output as it appeared in `ll_auto_last.txt`):

> ```
> [21:12:34] Dependency cycle detected: FEAT-108 -> FEAT-123 -> FEAT-122 -> FEAT-108
> [21:12:34] Starting automated issue management...
> [21:12:34] Uncommitted staged changes detected
> [21:12:34] Proceeding anyway...
> [21:12:34]   FEAT-108 blocked by: FEAT-122, FEAT-123, FEAT-124
> [21:12:34] 1 issue(s) remain blocked - check dependencies
> [21:12:34] No more issues to process!
>
> ============================================================
> PROCESSING SUMMARY
> ============================================================
> [21:12:34] Total run time: 0.0 seconds
> [21:12:34] Issues processed: 0
> ```

**Issue status after run** (verbatim from `ll-issues show FEAT-108 --json`):

> ```
> id: None
> status: Open
> confidence: 87
> outcome: 78
> title: Lock-protected promotion transaction + concurrency matrix
> priority: P2
> blocked_by: FEAT-122, FEAT-123, FEAT-124
> blocks: None
> depends_on: None
> decision_needed: false
> ```

**Refine-side artifact** (excerpt of `git diff HEAD -- .issues/features/P2-FEAT-108-...md`):

> ```
> -confidence_score: 80
> +confidence_score: 87
> +blocked_by:
> +- FEAT-122
> +- FEAT-123
> +- FEAT-124
> +learning_tests_required:
> +- pytest
> +- ruff
> ```

The refine step landed cleanly; the implement step did not move the issue
from `open` to `done`.

---

## State trace (parent loop, depth=0)

```
init
  → dequeue_next
  → check_status_at_dequeue
  → check_decision_at_dequeue
  → refine_current                    (sub-loop: refine-to-ready-issue)
  → count_repair_cycle_refine
  → copy_broke_down
  → check_decision_after_refine
  → check_passed                      (writes FEAT-108 → autodev-passed.txt)
  → implement_current                 (ll-auto --only FEAT-108 — silent no-op)
  → dequeue_next                      (queue empty)
  → finalize_done
  → done
```

The `refine_current` sub-loop ran the full refine → wire → confidence_check
→ readiness → outcome chain (12 iterations at depth=1) and reached its own
`done`. The nested `verify-confidence-scores` ran 2 iterations at depth=2.
All three loop-completion events report `terminated_by: terminal` and
`failure_terminal: false`.

---

## Rubric Audit (Step 7)

The autodev FSM contains **no `evaluate.type: llm_structured`** evaluators.
Every evaluator is `exit_code`, `output_contains`, or `output_numeric`, all
of which are deterministic gate predicates over captured stdout. No rubric
drift is possible; the rubric audit is a no-op for this loop.

---

## Sub-Loop Verdict Laundering Check (Step 8)

One sub-loop state in the parent FSM:

| State | `loop` | `on_yes` | `on_no` | `on_error` | Verdict |
|---|---|---|---|---|---|
| `refine_current` | `refine-to-ready-issue` | `count_repair_cycle_refine` | `skip_inflight` | `skip_inflight_infra` | 3 distinct targets → not laundering |

The `refine-to-ready-issue` sub-loop has its own sub-loop invocation
(`confidence_check → oracles/verify-confidence-scores`) and that state also
routes `on_yes`/`on_no`/`on_error` to three distinct downstream states. No
ENH-2005 artifact-channel sidecar exemption is needed; no laundering defect
exists in this run.

---

## Improvement Proposals

Ordered: contract > rubric > state > structural.

### 1. [contract] Move `passed.txt` write to AFTER verified closure, not at threshold pass

**Rationale**: `check_passed` writes to `autodev-passed.txt` when
readiness+outcome thresholds pass, but `implement_current` runs *after* and
may silently fail (dep cycles, `ll-auto` returning 0 with `Issues
processed: 0`). The success counter is incremented at a pre-implementation
check, so a failed implement never decrements it. The loop's own
`finalize_done` even emits `WARNING: in-flight issue not resolved: FEAT-108
(re-queue to retry)` but does not act on it. This is the root cause of the
phantom verdict.

**YAML diff** (the `check_passed` write moves to a transient staging file;
only `finalize_done` promotes to `passed.txt` once per-issue closure is
verified):

```yaml
states:
  check_passed:
    # Was: writes to autodev-passed.txt unconditionally when thresholds pass
    # Now: writes to a staging file; finalize_done promotes after closure verify
    action: |
      ll-issues check-readiness ${captured.input.output} \
        --readiness ${context.readiness_threshold} \
        --outcome ${context.outcome_threshold} \
        && echo "${captured.input.output}" >> ${context.run_dir}/autodev-staged.txt
```

```yaml
states:
  finalize_done:
    action: |
      # ENH-NEW: promote staged → passed only for issues whose status moved to
      # done/cancelled. Anything still in-flight at finalize is an unverified
      # closure and must NOT be counted as passed.
      STAGED=$(cat ${context.run_dir}/autodev-staged.txt 2>/dev/null \
        | grep -v '^[[:space:]]*$' | sort -u || true)
      VERIFIED=""
      for ID in $STAGED; do
        STATUS=$(ll-issues show "$ID" --json 2>/dev/null \
          | python3 -c "import json,sys; print((json.load(sys.stdin).get('status') or '').lower())" \
          2>/dev/null || echo "")
        case "$STATUS" in
          done|completed|cancelled) VERIFIED="$VERIFIED $ID" ;;
          *) echo "$ID  implement_silent_failure" \
               >> ${context.run_dir}/autodev-skipped.txt ;;
        esac
      done
      printf '%s\n' $VERIFIED >> ${context.run_dir}/autodev-passed.txt

      # … rest of existing finalize_done logic …
```

### 2. [state] Have `implement_current` detect `ll-auto` "Issues processed: 0" and fail the action

**Rationale**: With `set -o pipefail; ll-auto --only … 2>&1 | tee
ll_auto_last.txt`, the pipefail propagates `ll-auto`'s exit, but `ll-auto`
returned 0 even when 0 issues were processed (because pre-flight block
detection is not a fatal error in `ll-auto`'s exit semantics). The action
then routes `on_yes → dequeue_next`, never surfacing that the implement
step no-op'd. The captured output in `ll_auto_last.txt` includes the line
`Issues processed: 0`, which is a clear signal the implementation did not
happen.

**YAML diff**:

```yaml
states:
  implement_current:
    action: |
      # … existing INFLIGHT guard …

      # ENH-NEW: post-process the captured output for "Issues processed: 0"
      # and surface a non-zero exit so on_yes does not fire on silent no-op.
      set -o pipefail
      ll-auto --only "$CURRENT" $SKIP_FLAG 2>&1 | tee "${context.run_dir}/ll_auto_last.txt"
      LL_AUTO_RC=${PIPESTATUS[0]}
      if [ "$LL_AUTO_RC" -ne 0 ]; then
        echo "ll-auto exited $LL_AUTO_RC for $CURRENT" >&2
        exit "$LL_AUTO_RC"
      fi
      if grep -qE 'Issues processed:[[:space:]]*0\b' "${context.run_dir}/ll_auto_last.txt"; then
        echo "BLOCKED_OR_CYCLED: ll-auto processed 0 issues for $CURRENT" >&2
        exit 2
      fi
```

### 3. [state] Surface implement-side stdout markers via `output_contains` evaluator

**Rationale**: `implement_current` evaluates on `exit_code` only; the `2>&1`
is captured into `ll_auto_last.txt` but not into the FSM evaluator. If
`ll-auto` ever returns a non-zero in a future run (post-fix), the operator
only sees the captured file. Surfacing a key marker (`Issues processed: N`
where N ≥ 1) via `output_contains` would let the FSM distinguish a real
implement from a no-op at the route level.

**YAML diff**:

```yaml
states:
  implement_current:
    evaluate:
      # Was: { type: exit_code }
      # Now: require the captured output to show >=1 issue processed.
      type: output_contains
      pattern: "Issues processed: [^0]"
      on_yes: dequeue_next
      on_no: skip_inflight_infra   # treat silent-no-op as infra-class re-runnable skip
      on_error: skip_inflight_infra
```

### 4. [state] Have `finalize_done` cross-check `autodev-inflight` against the staging set and downgrade

**Rationale**: The loop already records the warning `WARNING: in-flight
issue not resolved: FEAT-108 (re-queue to retry)` at finalize time but still
reports `Passed (1)`. `finalize_done` should diff `autodev-inflight` against
the staged set and either (a) move unresolved issues to
`autodev-skipped.txt` with reason `implement_silent_failure`, or (b)
suppress the success count when inflight remains. This is partially
subsumed by proposal #1's `finalize_done` change but is worth flagging
separately because it also fixes the case where `inflight` is set but the
issue is genuinely open (e.g., the queue was being drained).

**YAML diff** (additional guard in `finalize_done`):

```yaml
states:
  finalize_done:
    action: |
      # ENH-NEW: any inflight at finalize is an unverified closure — surface it.
      INFLIGHT=$(cat ${context.run_dir}/autodev-inflight 2>/dev/null | tr -d '[:space:]')
      if [ -n "$INFLIGHT" ]; then
        echo "$INFLIGHT  inflight_at_finalize" >> ${context.run_dir}/autodev-skipped.txt
      fi

      # … rest of existing finalize …
```

### 5. [structural] Pre-flight dep-cycle detection in `dequeue_next`

**Rationale**: `dequeue_next` already writes `autodev-pre-ids.txt` (the
current backlog snapshot) for reconciliation but does not check for cycles
on the dequeued issue. The cycle was visible from `blocked_by`
(FEAT-122, FEAT-123, FEAT-124 form a ring back to FEAT-108), and
`ll-issues show FEAT-108 --json` exposes `blocked_by`. A pre-flight that
checks "is any blocker of this issue also in the same cycle, and is any
blocker itself open" would let the loop park the issue in
`autodev-skipped.txt` (reason: `blocked_by_cycle`) rather than burn a
refine pass on a doomed implementation. The refine pass did succeed
(productively adding `blocked_by` annotations), but the implementation
contract was unachievable from the start.

**YAML diff**:

```yaml
states:
  dequeue_next:
    action: |
      # … existing logic …

      # ENH-NEW: detect self-blocking / transitive cycles before refining.
      CURRENT="${captured.input.output}"
      HAS_BLOCKERS=$(ll-issues show "$CURRENT" --json 2>/dev/null \
        | python3 -c "
      import json,sys
      try:
          d=json.load(sys.stdin)
          print('1' if (d.get('blocked_by') or []) else '0')
      except Exception:
          print('0')
      " 2>/dev/null || echo 0)
      if [ "$HAS_BLOCKERS" = "1" ]; then
        echo "$CURRENT  blocked_by_open_siblings" \
          >> ${context.run_dir}/autodev-skipped.txt
        rm -f ${context.run_dir}/autodev-inflight
        # fall through (continue to next dequeue without refining)
      fi
```

---

## Dedup status (existing issues searched)

```
grep -rl "autodev" .issues/bugs/ .issues/enhancements/ .issues/features/ .issues/epics/
  .issues/enhancements/P3-ENH-010-rn-refine-converged-iteration-1-without-entering.md  (different loop: rn-refine)
  .issues/features/P3-FEAT-047-batch-apo-driver-across-slugs.md                        (different scope)
  .issues/features/P3-FEAT-161-config-files-and-doc-namespace.md                       (different scope)
  .issues/features/P2-FEAT-108-lock-protected-promotion-transaction.md                  (the issue being audited, not an improvement)
grep -l "phantom" …                                                                            (no matches in improvement issues)
grep -l "passed.txt\|implement_current\|finalize_done\|inflight" …                          (no matches)
```

All 5 proposals are **NEW** — no existing issue captures the
phantom-convergence defect for autodev. Per the user's instruction, no
issues were created; this report is the deliverable.

---

## Artifacts cited

- `/Users/brennon/AIProjects/animation/sketch-storyboards/.loops/.history/2026-07-29T013824-autodev/events.jsonl` (122 events, 318 KB)
- `/Users/brennon/AIProjects/animation/sketch-storyboards/.loops/.history/2026-07-29T013824-autodev/state.json` (98 KB)
- `/Users/brennon/AIProjects/animation/sketch-storyboards/.loops/runs/autodev-20260728T203824/autodev-passed.txt`
- `/Users/brennon/AIProjects/animation/sketch-storyboards/.loops/runs/autodev-20260728T203824/autodev-skipped.txt`
- `/Users/brennon/AIProjects/animation/sketch-storyboards/.loops/runs/autodev-20260728T203824/autodev-inflight`
- `/Users/brennon/AIProjects/animation/sketch-storyboards/.loops/runs/autodev-20260728T203824/ll_auto_last.txt`
- `/Users/brennon/AIProjects/animation/sketch-storyboards/.issues/features/P2-FEAT-108-lock-protected-promotion-transaction.md`
- `/Users/brennon/AIProjects/animation/sketch-storyboards/.ll/ll-config.json` (thresholds)
- FSM definition via `ll-loop show autodev --resolved --json`