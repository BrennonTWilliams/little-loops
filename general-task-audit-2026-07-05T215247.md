# Loop Audit — `general-task` run `2026-07-05T215247`

**Audited:** 2026-07-05
**Run dir:** `.loops/.history/2026-07-05T215247-general-task/`
**Working repo:** `ai-workspaces/ll-labs/cards`
**Verdict:** `phantom` (phantom convergence — success terminal reached with the task ~half done)

---

## TL;DR

The loop routed to its **success** terminal (`summarize_success → done`, `verdict:"success"`)
after completing only **Steps 1–14 of 30** (16 plan steps + 19 hard DoD criteria still
unchecked; achieved pass rate ≈ **39%** against a `min_pass_rate` contract of **0.95**).
It did so not because the Definition-of-Done was satisfied but because **two independent
gates were fooled**, plus a **third cosmetic corruption** in the success summary.

---

## State-transition trace (23 iterations — all from `events.jsonl`)

```
check_baseline_tests → define_done → plan → resume_check → select_step
 → do_work → do_work(retry, exit 124→0) → verify_step(PASS) → mark_done → check_done
 → count_done(total=35, on_no) → continue_work(WORK_COMPLETE=no) → select_step
 → do_work → verify_step(PASS) → mark_done → check_done
 → count_done(total=35, on_no) → continue_work(WORK_COMPLETE=YES) ⚑ FALSE MATCH
 → final_verify → run_final_tests(exit ok) → count_final(failed=0) → summarize_success → done
```

`loop_complete`: `{"final_state":"done","iterations":23,"terminated_by":"terminal"}`

---

## Success contract vs. outcome

| Contract (from FSM `context`) | Target | Actual | Status |
|---|---|---|---|
| `min_pass_rate` | 0.95 | 12/31 ≈ 0.39 | ❌ VIOLATED |
| all `[hard]` DoD criteria checked | 0 unchecked | 19 unchecked | ❌ VIOLATED |
| plan steps complete | 30/30 | 14/30 (16 unchecked) | ❌ VIOLATED |

Artifacts (`.loops/runs/general-task-20260705T165247/`):
- `plan.md` — mutated; 14 `[x]` / 16 `[ ]`
- `dod.md` — mutated; 12 `[x]` / 19 `[ ]` in Verification Criteria. Its own
  `## Final Verification` section **honestly** records Steps 15–27 as
  "NOT implemented / confirmed genuinely incomplete."
- Real source mutated for Steps 1–14: `src/lineage/treeShape.ts`,
  `src/components/LineageLane.tsx`, `src/store/slices/table.ts`,
  `src/store/slices/pinned-verbs.ts`, plus new test files. (Work was real; the
  problem is the loop *stopped early and called it success*.)

---

## Phase 1 fault signals

None terminating. One `do_work` exit `124` (timeout) at iteration 6→7 was **retried to
success** (design behavior: `retryable_exit_codes:[124]`, `max_retries:2`). No
SIGKILL/FATAL, no evaluate-error termination, no retry flood.

## Shallow-iteration check

`clear` — 23 `action_complete` events (below the 30 threshold) with substantial
auxiliary + source-file mutations.

## Budget-utilization guard

`STEPS_CONSUMED / MAX_STEPS = 23 / 500 = 4.6%` (< 0.3). Budget exhaustion **rejected** as
a root cause — the loop exited *early via a false gate*, it did not run out of steps.

## Rubric-vs-description audit

Skipped — this FSM has **0** `evaluate.type: llm_structured` states (only
`output_contains`, `output_json`, `exit_code`).

## Sub-loop verdict-laundering check

N/A — no states declare `loop:`.

---

## Goal-vs-Outcome Scorecard

- **Goal**: "General-purpose task loop: writes a Definition of Done, decomposes the task
  into steps, executes one step at a time, and loops until all DoD criteria are verified."
- **Contract**: `min_pass_rate=0.95`, all `[hard]` criteria — **both violated**
- **Artifacts checked**: plan.md 14/30 ✓mutated; dod.md 12/31 ✓mutated; Steps 1–14 source ✓mutated
- **Phase 1 signals**: none terminating (1 handled timeout)
- **Shallow-iteration check**: `clear` (23 tool calls, ample auxiliary mutations)
- **Verdict**: `phantom`

### Rationale

Terminal-success was reached because two gates failed independently:

**Defect 1 — Degenerate sentinel gate (the smoking gun).**
`continue_work` evaluates `output_contains` pattern `WORK_COMPLETE` against the worker's
free-form output. On iteration 19 the worker wrote:

> "Not printing **WORK_COMPLETE** because Steps 15–27 (plus 26b–26d) and their DoD
> criteria remain unresolved."

The naive substring match fired `verdict:yes` on the sentinel **inside its own negation**,
routing `on_yes → final_verify` and bypassing all remaining `select_step` work.
Confirmed by the two `WORK_COMPLETE` evaluate events: iteration 12 → `no`, iteration 19 → `yes`.

**Defect 2 — `count_final` trusts free-form prose, not the criterion marks.**
`final_verify` behaved *correctly*: it left 19 criteria `[ ]` and wrote prose
"NOT implemented / genuinely incomplete." But `count_final`'s awk counts only lines
matching `/FAILED/` in the `## Final Verification` section. Because `final_verify` never
emitted that exact token, `failed_finals=0 → on_yes → summarize_success`. The gate never
checks how many criteria are still `[ ]`, so an honest "not done" sails through as success.

**Defect 3 (cosmetic) — corrupted success counter.**
`summary.json` reads `{"verdict":"success","implemented":0,"failed_finals":0}`.
`implemented:0` is *not* an honest "produced nothing": `summarize_success` interpolates the
raw JSON string `done_counts.output` (`{"total":35,...}`) directly into a **single-quoted
Python literal**, the embedded double-quotes break `json.loads`, and it falls back to `0`.
Worse, even when it parses, it sources `implemented` from `done_counts.total` — which counts
*unresolved* items, not implemented ones. This is why the verdict is `phantom`
(loop took the success terminal + wrote `verdict:"success"`), not `honest-failure`.

---

## Ranked Improvement Proposals

### 1. [structural, P1] `continue_work` sentinel matched inside its own negation

Highest-impact defect and the direct cause of the phantom exit. `output_contains` on a bare
token cannot distinguish assertion from negation.

```yaml
continue_work:
  evaluate:
    type: output_contains
-   pattern: "WORK_COMPLETE"
+   # Sentinel must be the entire final line — not a substring inside prose like
+   # "Not printing WORK_COMPLETE because Steps 15-27 remain unresolved."
+   pattern: "(?m)^WORK_COMPLETE$"
    source: "${captured.continue_result.output}"
```

Also tighten the escape-hatch instruction: print `WORK_COMPLETE` on its **own line with
nothing else**, and forbid emitting the token anywhere it is being negated/quoted.

*Note:* this same sentinel-negation trap applies to any `output_contains` gate whose
pattern is a natural-language token the worker might mention while negating it
(`RESUME_SKIP`, `VERIFY_PASS`, `SELECTED_STEP:` are lower-risk because they're
machine-emitted by shell states, but the pattern is worth a lint rule across all loops).

### 2. [contract, P1] `count_final` must enforce completion, not trust prose

Even with #1 fixed, `final_verify` can honestly leave criteria `[ ]` and still pass because
`count_final` only greps `FAILED`. Gate on the *actual unchecked-criteria count* the way
`count_done` already does, plus any `FAILED` lines.

```yaml
count_final:
  action: |
    DOD="${context.run_dir}/dod.md"
    # count remaining unchecked [hard] criteria in Verification Criteria ...
    HARD_UNCHECKED=$(awk '/^## Verification Criteria/{s=1;next} /^## /{s=0}
      s && /^[[:space:]]*-[[:space:]]*\[[[:space:]]\]/ && /\[hard\]/ {c++} END{print c+0}' "$DOD")
    # ... AND any FAILED lines in Final Verification
    FAILED=$(awk '/^## Final Verification/{s=1;next} s && /FAILED/{c++} END{print c+0}' "$DOD")
    printf '{"blocking": %d}\n' "$((HARD_UNCHECKED + FAILED))"
  evaluate:
    type: output_json
    operator: eq
    target: 0
    path: ".blocking"
```

### 3. [state, P2] `summarize_success` mislabels and corrupts its counter

`DONE_TOTAL` is sourced from `done_counts.total` (the count of *unresolved* items) and
labeled `implemented`; and the raw-JSON→single-quoted-Python interpolation breaks
`json.loads`. Pass the value safely (write capture to a file and `jq`/`--argjson` it) and
report *checked* criteria, not `total`. Until fixed, `summary.json.implemented` is not a
trustworthy claimed-success signal for downstream audits.

---

## Evidence index (verbatim, from run artifacts)

- `summary.json`: `{"verdict":"success","implemented":0,"failed_finals":0}`
- `state.json` → `captured.done_counts.output`:
  `{"hard_unchecked_dod": 19, "soft_unchecked_dod": 0, "unchecked_plan": 16, "failed_samples": 0, "total": 35}`
- `state.json` → `captured.continue_result.output` (iteration 19):
  "…Not printing `WORK_COMPLETE` because Steps 15–27 (plus 26b–26d) and their DoD criteria remain unresolved."
- `events.jsonl` evaluate events: `WORK_COMPLETE` → `no` (iter 12), `WORK_COMPLETE` → `yes` (iter 19)
- `dod.md` → `## Final Verification`: Steps 15–23, 26b–26d each listed `[ ]` "NOT implemented"

---

*Generated by `/ll:audit-loop-run general-task`. Issue creation was declined in favor of
this single report.*
