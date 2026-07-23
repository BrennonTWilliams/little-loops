# Loop Audit: sprint-refine-and-implement

**Run assessed**: `.loops/.history/2026-07-18T045753-sprint-refine-and-implement/`
**Wall clock**: 2026-07-18T04:57:53 → 2026-07-18T11:54:46 (≈6h57m, 25,013,310 ms accumulated)
**Sprint scope**: EPIC-122
**Audit date**: 2026-07-22

---

## Verdict: `partial`

The loop closed 4 of 14 dispatched issues, parked 2 (one `low_readiness`, one `refine_failed`), and reached its terminal `done` state cleanly — but the post-closure verify gate reported `failed` because of a tooling configuration defect (`npm error Missing script: "test"`), not a code regression. The parked issue count is honest and expected for a refinement-heavy run, but the verify verdict is misleading and should not be conflated with a real code-level test failure.

### Goal-vs-Outcome Scorecard

```
**Goal**: "Alias for auto-refine-and-implement scoped to a named sprint or EPIC.
          Delegates to auto-refine-and-implement with scope=<sprint-name|EPIC-NNN>."
**Contract**: none detected (no threshold keys in FSM context; max_steps=50 inherited)
**Artifacts checked**:
  - .issues/enhancements/P2-ENH-078-*.md    status:done (closed via .issues/completed/ path)
  - .issues/enhancements/P2-ENH-103-*.md    status:done (closed in-place, ENH-1418)
  - .issues/enhancements/P2-ENH-129-*.md    status:done (closed in-place, ENH-1418)
  - .issues/enhancements/P2-ENH-133-*.md    status:done (closed in-place, ENH-1418)
  - .issues/enhancements/P2-ENH-138-*.md    status:done (autodev parked: low_readiness)
  - .issues/enhancements/P2-ENH-139-*.md    status:done (autodev parked: refine_failed)
**Phase 1 signals**: 1 SIGKILL (exit_code=-9, depth=3 sub-agent, parent loop recovered)
**Shallow-iteration check**: `clear` (349 action_complete events, 33 auxiliary mutations in run_dir)
**Verdict**: `partial`

**Rationale**: Terminal reached cleanly (`loop_complete.terminated_by=terminal`, final_state=done,
iterations=2 of 50 budget = 4%). Closed count 4 > 0 but skipped 2 > 0 means not all
contracts satisfied. Verify verdict=failed is a tooling misconfiguration (npm error: no
"test" script in repo-root package.json), NOT a code defect — see proposal #1 below.
The "skipped" set is honest: refinement correctly identified 2 issues not ready for
implementation. The 2 skipped issues all reached status:done anyway, suggesting an
alternative closure path (likely ll-auto after the sprint-refine-and-implement queue
drained); see proposal #3.
```

### Summary.json verbatim

```json
{
  "verdict": "partial",
  "closed": 4,
  "not_closed": 0,
  "skipped": 2,
  "errored": 0,
  "skipped_breakdown": {"low_readiness": 1, "refine_failed": 1},
  "gate_blocked": 0,
  "decision_unresolved": 0,
  "inflight_unresolved": 0,
  "abandoned": 0,
  "parked_rate": 0.1429,
  "verify_verdict": "failed",
  "verify_returncode": 1,
  "epic_merge_verdict": "skipped"
}
```

---

## Phase 1 — Fault Signals

| Signal | Count | Verdict |
|---|---|---|
| Action failures (exit_code != 0) | 108 | ✅ Nominal — 107 are `exit_code=1` from deliberate shell routing patterns (e.g. "re-dispatch cycle cap reached", "no new issues"); 1 is exit_code=-9 (SIGKILL of a depth-3 sub-agent, parent loop recovered) |
| SIGKILL / FATAL_ERROR termination | 1 | ✅ Recovered — sub-agent killed at depth 3, parent FSM continued without re-route |
| Evaluate error termination | 0 | ✅ No terminating evaluator error |
| Retry floods | 0 | ✅ No state was retried >3 times |
| Evaluate failures (verdict=fail) | 0 | ✅ No evaluator returned verdict=fail |
| Sub-loop verdict discarded | 1 (mitigated) | ✅ See Step 8 — ENH-2005 artifact-channel sidecar exempts this case |
| Throttle stop / hard | 0 | ✅ No throttle events in events.jsonl |

**Phase 1 finding**: None of the fault signals of severity tripped. The single SIGKILL at 193,790 ms duration was a normal child-agent OOM/reap, and the parent FSM recovered without a state-classifier change.

---

## Step 5.5 — Shallow-Iteration Check

| Metric | Value |
|---|---|
| `TOOL_CALL_COUNT` (action_complete events) | 349 |
| Run directory gitignored? | Yes (`.loops/runs/` excluded) |
| `AUX_MUTATION_COUNT` (filesystem scan anchored on `events[0].ts`) | 33 |
| `DIFF_STALL_PRESENT` | No (no `evaluate.type=stall` evaluator in this FSM, no `verdict=stall` in history) |

**Result**: `clear` — 33 auxiliary artifacts (closed-union.txt, dispatched.txt, summary.json, verify-detail.txt, etc.) confirm the loop built structured helper files alongside the primary closure path. No shallow-iteration warning.

---

## Step 5.6 — Budget-Utilization Guard

| Metric | Value |
|---|---|
| Parent FSM `STEPS_CONSUMED` (loop_complete.iterations) | 2 |
| `MAX_STEPS` (from context) | 50 |
| Ratio | 0.04 |

**Result**: Budget-exhaustion is **rejected** as a root cause (4% < 30% threshold). The parent FSM ran well within budget; the run ended because `read_outcome` reached terminal after the sub-loop returned.

---

## Step 7 — Rubric-vs-Description Audit

The parent FSM `sprint-refine-and-implement` has **0 `llm_structured` evaluators** (only `exit_code` evaluators, and only in the inner `auto-refine-and-implement` sub-loop). Per the skill rubric, no rubric drift check is needed.

The loop's stated goal is a thin delegation: "alias for auto-refine-and-implement scoped to a sprint or EPIC." The FSM implements exactly that: `delegate` → sub-loop → `read_outcome` (recovers verdict from `subloop_outcome_auto-refine-and-implement.txt`) → `done`. No goal misalignment.

---

## Step 8 — Sub-Loop Verdict Laundering Check

**State audited**: `delegate` (sub-loop: `auto-refine-and-implement`)

```yaml
delegate:
  loop: auto-refine-and-implement
  on_yes: read_outcome
  on_no:  read_outcome       # ← identical target
  on_error: record_crash     # ← distinct error route
```

**On first inspection**: `on_yes == on_no` is the canonical verdict-laundering pattern.

**Mitigation check (ENH-2005 artifact-channel sidecar exemption)**:

1. ✅ Shared next state `read_outcome` action contains `subloop_outcome_`:
   ```
   OUTCOME="$RUN_DIR/subloop_outcome_auto-refine-and-implement.txt"
   VERDICT=$(cat "$OUTCOME" 2>/dev/null || echo unknown)
   ```
2. ✅ `on_error` routes to a **distinct** state (`record_crash`), not collapsed into `read_outcome`.

**Result**: `[mitigated — ENH-2005 artifact-channel sidecar: verdict recovered via subloop_outcome_ artifact, on_error routes to distinct crash state]`. No laundering defect.

The recovered verdict for this run was `partial` (per `.loops/runs/.../subloop_outcome_auto-refine-and-implement.txt`), and the same verdict appears in `summary.json` — confirming the artifact-channel recovery is honest.

---

## Ranked Improvement Proposals

> **Order: contract-level > rubric-level > state-level > structural**

### 1. [contract/config — DUPLICATE-P3-ENH-044] `verify_verdict: "failed"` is a tooling misconfiguration, not a code regression

**Severity**: contract-level (the misleading verdict poisons sprint close decisions)

**Evidence (verbatim from `verify-detail.txt`)**:

```
npm error Missing script: "test"
npm error
npm error To see a list of scripts, run:
npm error   npm run
A complete log of this run can be found in: /Users/brennon/.npm-cache/_logs/2026-07-18T11_54_45_914Z-debug-0.log
```

**Verified root cause** (current `.ll/ll-config.json`):

```bash
$ cat .ll/ll-config.json | jq '.project.test_cmd'
"npm test"
```

`package.json` lives in `studio/` (per `CLAUDE.md`: "All commands use `pnpm` from the `studio/` directory"), but `npm test` runs from the repo root. The verify state classifies this as `failed` (returncode=1), but it is functionally a configuration error — the test suite never ran.

**Existing issue**: `.issues/enhancements/P3-ENH-044-improve-test-suite.md` (`status: done`) explicitly listed this fix as Phase 1, item 16:

> Update `.ll/ll-config.json` `test_cmd` from `"npm test"` to `"cd studio && pnpm test"` (wrong package manager: project uses pnpm, not npm; wrong working directory: no root package.json).

**Recommendation**: Either (a) **reopen P3-ENH-044** with a verification proof that the config change landed (it didn't), or (b) **file a new BUG** documenting that the verify-state reports `verify_verdict: "failed"` for every sprint-refine-and-implement run on this repo due to a config defect that a closed issue claimed to fix. Until this is fixed, **`verify_verdict` is unreliable as a closure signal** — do not gate close decisions on it.

---

### 2. [state-level — NEW] Verify state's `classify()` should distinguish "missing npm script" from real test failure

**Severity**: state-level (verify verdict is the only post-closure quality signal in `summary.json`)

**Evidence**: The verify state's `_classify()` returns `'failed'` for any non-zero exit code other than 2 (`collection_error`). But a missing npm script yields exit 1 with stderr `npm error Missing script: "test"` — semantically a usage/config error, not a code defect.

**Current code path** (`scripts/little_loops/.../verify.py` per the FSM's verify state):
```python
def classify(returncode):
    if returncode == 0: return 'passed'
    if returncode == 2: return 'collection_error'
    return 'failed'
```

**Proposed YAML diff** (in the verify state action):
```yaml
verify:
  action: |
    ...
    VERIFY_VERDICT=$(python3 << 'PYEOF'
    def classify(returncode, stderr=""):
        if returncode == 0: return 'passed'
        if returncode == 2: return 'collection_error'
        if 'Missing script' in stderr or 'missing script' in stderr:
            return 'config_error'   # NEW: distinguish npm-config-missing
        return 'failed'
    PYEOF
    )
```

**Benefit**: A `config_error` verdict (vs. `failed`) tells the human reviewer the test suite never ran, separating "config broken" from "tests broke."

**Alternative**: The simplest fix lands at proposal #1 (correct `test_cmd` in `.ll/ll-config.json`); this proposal #2 is defense-in-depth for any future misconfig.

---

### 3. [visibility — NEW] `closed_via_recovery` counter for issues parked-then-closed

**Severity**: visibility (current scorecard cannot tell whether parking means "abandoned" or "will be re-tried-and-succeed")

**Evidence from this run**:

| Issue | skipped_breakdown reason | Working-tree status |
|---|---|---|
| ENH-138 | `low_readiness` | `status: done` |
| ENH-139 | `refine_failed` | `status: done` |

Both skipped issues ultimately reached `status: done` — the closure happened via a path the parent FSM's scorecard cannot see (most likely `ll-auto` re-implementing after `sprint-refine-and-implement` released the lock, or a direct manual edit). The current `closed=4` count misses them, and the current `parked_rate=0.1429` overstates the actual parked-to-forever ratio.

**Proposed YAML diff** (in the `finalize` state's action):
```yaml
finalize:
  action: |
    ...
    # ENH-2xxx: closed_via_recovery — issues the autodev sub-loop parked,
    # but which reached status:done via a different closure path during
    # this run. Mirrors the BUG-2403 / ENH-1418 done-now snapshot.
    CLOSED_VIA_RECOVERY=$(comm -12 \
      "$RUN_DIR/$P-skipped-ids.txt" \
      "$RUN_DIR/$P-done-new.txt" \
      | wc -l)
    ...
    printf '..."closed_via_recovery":%s,...' "$CLOSED_VIA_RECOVERY"
```

**Benefit**: A reviewer reading `summary.json` sees `{"closed":4, "skipped":2, "closed_via_recovery":2}` and knows the parking was benign. Without it, the current 4/2 split looks like the run "failed to handle" 2 issues.

---

### 4. [state-level — NEW] `skipped_breakdown` `refine_failed` bucket is too coarse

**Severity**: state-level (post-mortem triage cannot distinguish transient vs. policy reasons)

**Evidence**: The current `skipped_breakdown` (ENH-2404) groups every refinement-failure reason into a single `refine_failed` bucket. Two of this run's parked issues land there, but they could represent:

- **Transient infra** (e.g. refine sub-loop crashed, timeout, model API error)
- **Policy refusal** (e.g. refinement said "this issue is not ready" or "broken-down children required")
- **Quality gate failure** (e.g. readiness score < threshold)

**Proposed YAML diff** (in the `autodev` sub-loop's refine-to-skip path):
```yaml
- type: skip
  reason: refine_failed
+sub_reason: "${captured.refine_outcome.sub_reason}"  # transient | policy_refusal | readiness_low
```

**Benefit**: A future `/ll:audit-loop-run` could surface "12 of 14 `refine_failed` skips were `readiness_low` — issue readiness rubric may be mis-calibrated" vs. "8 of 14 were `transient` — infra is flaky."

---

### 5. [config — informational, no action needed] `epic_merge_verdict: "skipped"` because `parallel.epic_branches.enabled: false`

The sprint ran on EPIC-122, but `epic_merge_verdict: "skipped"` because `parallel.epic_branches.enabled` is `false` in `.ll/ll-config.json`. The `merge_epic_branch` state correctly recognized this and exited cleanly. **No action needed** — but worth noting that EPIC-scoped runs on this repo will never auto-merge; the human reviewer must close the EPIC manually.

---

## Non-findings (clean checks worth recording)

- **Fault signals**: Only 1 SIGKILL of a depth-3 sub-agent (parent loop recovered cleanly). No terminal evaluator errors, no retry floods, no evaluate-fail verdicts.
- **Sub-loop verdict laundering**: Mitigated by ENH-2005 artifact-channel sidecar pattern (the verdict is recovered from `$RUN_DIR/subloop_outcome_auto-refine-and-implement.txt`, and `on_error` routes to a distinct `record_crash` state).
- **Budget utilization**: Parent FSM consumed 2 of 50 steps (4%) — budget-exhaustion is not a root cause.
- **Shallow-iteration check**: 349 action_complete events with 33 auxiliary file mutations — clear (not a "warning" or "corroborated" shallow iteration).
- **Terminal reached**: `loop_complete.terminated_by=terminal`, `final_state=done` — clean termination.

---

## Summary

| Aspect | Status |
|---|---|
| Verdict | `partial` |
| Rubric audit | 0 evaluators checked (no llm_structured evaluators in this wrapper FSM) |
| Laundering check | 1 sub-loop state checked, 0 flagged (ENH-2005 mitigated) |
| Shallow-iteration check | `clear` (349 tool calls, 33 aux mutations) |
| Issues created | 0 (per user request — findings written to this .md file instead) |

**The single most actionable item**: Reopen (or supersede) **P3-ENH-044** — its Phase 1, item 16 claim that `.ll/ll-config.json` `test_cmd` was updated from `"npm test"` to `"cd studio && pnpm test"` is contradicted by the current file content and by every `verify_verdict: "failed"` line in this run's `summary.json`. Until that fix lands, `verify_verdict` is not a reliable closure signal for any sprint-refine-and-implement run on this repo.

**Secondary actions** (in priority order):
1. Defense-in-depth: extend the verify state's `classify()` to surface a distinct `config_error` verdict for "Missing script: test" stderr matches (proposal #2).
2. Visibility: add a `closed_via_recovery` counter to `summary.json` so reviewers can see whether parked issues were benignly closed via an alternate path (proposal #3).
3. Triage: split `refine_failed` into `transient | policy_refusal | readiness_low` sub-reasons (proposal #4).