# `rn-implement` Loop Assessment — Run `2026-06-27T210732`

**Generated**: 2026-06-27
**Skill**: `/ll:audit-loop-run`
**Loop**: `rn-implement`
**Run ID**: `2026-06-27T210732`
**Source project**: `/Users/brennon/AIProjects/ai-workspaces/ll-labs/cards`

---

## Goal-vs-Outcome Scorecard

**Goal**: "Queue orchestrator for recursive plan-and-implement. Manages a depth-bounded issue queue, delegating per-issue remediation to `rn-remediate` and decomposition to `rn-decompose`."

**Contract**: `readiness_threshold=85`, `outcome_threshold=75`, `max_depth=3`, `max_remediation_passes=3` (all from FSM `context`)

**Artifacts checked**:
- `.loops/runs/rn-implement-20260627T160732/summary.json` → `{implemented: 0, decomposed: 0, failed: 5}`
- `.loops/runs/.../failures.txt` → 5 entries (one per issue, ts 21:24 → 21:40)
- `.issues/bugs/P0-BUG-366…` through `P1-BUG-375…` → **no `git log` entries from this run; no source code mutations; no status flips**
- Per-issue pre/post scores: BUG-366 (88/77 ✓) and BUG-373 (96/87 ✓) — all issues crossed both thresholds in pre-scores

**Phase 1 signals**:
- 19 non-zero `action_complete` exits — but most are shell-predicate exits (`check_wire_pre_implement`, `check_readiness`, `check_outcome`) which are valid FSM routing, not faults
- 5 genuine action failures, all in `implement` state (exit=1, durations 41–103s):
  - **BUG-366**: `ready-issue verdict: BLOCKED` — open dependency on BUG-367 (declared-order serialization)
  - **BUG-372, BUG-373, BUG-374, BUG-375**: `ready-issue verdict: READY|CORRECTED` → followed by `Fatal error: "Could not resolve authentication method. Expected one of api_key, auth_token, or credentials to be set."`
- 0 throttle_stop, 0 SIGKILL, 0 FATAL_ERROR, 0 sub-loop crashes (sub-loop ran to terminal; auth failure is in the subsequent `ll-auto` call from parent's `implement` state)

**Shallow-iteration check**: `clear` (91 tool calls, 39 auxiliary run_dir files written — diagnosis, convergence, scores, complexity_band, subloop_outcome per issue)

**Verdict**: **`phantom`**

**Rationale**: The loop reached terminal (`loop_complete: done, iterations: 74`) with all readiness/outcome threshold contracts met for every dequeued issue — BUG-366 (88/77), BUG-372 (97/93), BUG-373 (96/87), BUG-374 (99/88), BUG-375 (97/95). However, **zero source-code or issue-status mutations** occurred in the repo. The summary honestly records `implemented: 0, failed: 5`, but the structural pattern is phantom-like: the orchestration gates passed cleanly, the artifacts (scores, diagnosis, convergence) were written, the loop walked a happy path through readiness checks, then hit a hard wall at the only state that actually mutates the codebase (`implement` → `ll-auto --only $ID`). Of 5 failures, 4 share an identical root cause: `ll-auto` requires Anthropic API auth that is not configured in this environment. The 5th (BUG-366) failed for a separate but predictable reason: the queue didn't include its declared dependency BUG-367, so `ready-issue` correctly refused it. The loop's metric is honest, but its outcome is the same as a phantom run — nothing got built.

---

## Rubric-vs-Description Audit

**0 `llm_structured` evaluators** in `rn-implement` (all parent evaluators are `output_contains` / `exit_code` / `output_numeric` / `classify`). **0 flagged.** Audit trivially passes.

---

## Sub-Loop Verdict Laundering Check

2 sub-loop states flagged — but with a structural mitigation caveat:

| State | Loop | `on_yes` | `on_no` | Mitigation |
|---|---|---|---|---|
| `run_remediation` | `rn-remediate` | `classify_remediation` | `classify_remediation` | `classify_remediation` reads `${run_dir}/subloop_outcome_<ID>.txt` and falls back to `IMPLEMENT_FAILED` if absent — verdict preserved via artifact channel |
| `run_decomposition` | `rn-decompose` | `classify_decomposition` | `classify_decomposition` | Same artifact-channel pattern |

**Pattern match**: technically `on_yes == on_no` (literal definition flags it). **Practical verdict**: NOT laundering in effect — the parent always lands in a classifier that reads the sub-loop's outcome file. **However**, this means `on_error` is the only signal distinguishing "child crashed" from "child ran to terminal" — and `on_error` routes to `record_sub_loop_crash`, which is never triggered in this run because `rn-remediate` always terminates cleanly. The integrity here depends entirely on the classifier's fallback (`|| echo "IMPLEMENT_FAILED"`) — a brittle contract.

---

## Improvement Proposals (ranked)

### 1. [contract, structural] Loop has an unmet hard dependency on `ANTHROPIC_API_KEY` / equivalent auth, but no pre-flight check

**Rationale**: 4 of 5 issues failed with the exact same `Fatal error: Could not resolve authentication method` error from `ll-auto`. The loop burned 52–103 seconds per issue (Phase 1 `ready-issue`) before hitting the auth wall at Phase 2 (`ll-auto`). Readiness scoring was correct (all 5 above thresholds), but the loop never verified that the implementation environment was capable of actually implementing. This is the single highest-impact fix.

**YAML diff**:

```yaml
# Add pre-flight check at the start of init (or as a new first state)
states:
  init:
    action: |
      INPUT="${context.input}"
      ...
      # NEW: pre-flight auth check before seeding the queue
      if ! command -v ll-auto >/dev/null 2>&1; then
        echo "ERROR: ll-auto not on PATH"
        exit 1
      fi
      # Probe whether ll-auto can authenticate by checking required env
      # (exact env var depends on the harness — typically ANTHROPIC_API_KEY
      # or a Claude Code login state)
      if [ -z "$ANTHROPIC_API_KEY" ] && [ -z "$CLAUDE_CODE_OAUTH_TOKEN" ]; then
        echo "ERROR: No Anthropic auth configured (set ANTHROPIC_API_KEY or run 'claude login')"
        exit 1
      fi
      ...
```

### 2. [contract] Add artifact mutation verification to the `implement` state

**Rationale**: Currently `implement` succeeds/fails based on `ll-auto --only "$ID"` exit code, but doesn't verify that the implementation actually committed changes. If `ll-auto` ever silently no-ops (e.g., dry-run mode, transient API issues that get swallowed), the loop will report success with no mutation.

**YAML diff**:

```yaml
states:
  implement:
    on_yes: classify_remediation  # already routes via artifact
    on_no: emit_implement_failed
    on_error: emit_implement_failed
    # NEW: capture git status before/after
    capture: implement_artifact_check
  verify_implement:
    action: |
      # Compare git status before/after to detect phantom-success
      ...
    evaluate:
      type: diff_present
```

### 3. [state] `BUG-366` BLOCKED by missing dependency — queue pre-flight should validate dependency closure

**Rationale**: BUG-366's `ready-issue verdict: BLOCKED` came from an open dependency on BUG-367, which was not in the queue. The loop detected this correctly at the `ll-auto` stage (5+ minutes later), but `check_blocked_by` exists in the parent and could have caught it earlier. Currently `check_blocked_by` checks `done` status only, not declared dependencies in the queue itself.

**YAML diff**:

```yaml
states:
  check_blocked_by:
    action: |
      ...
      # ENH: also check if deps are queued/decomposable in this run
      queue_ids = set(open(QUEUE).read().split())
      unmet_in_queue = [d for d in deps if d not in done_ids and d not in queue_ids]
      ...
```

### 4. [structural] Sub-loop verdict laundering pattern — make `on_yes != on_no` explicit even if both flow into the same classifier

**Rationale**: `run_remediation.on_yes == on_no == classify_remediation` matches the laundering signature. The artifact-channel mitigation works, but the audit flags it because the parent doesn't structurally distinguish "child reached terminal" from "child failed mid-loop". Refactor to:

```yaml
states:
  run_remediation:
    loop: rn-remediate
    on_yes: classify_remediation   # child reached terminal
    on_no: re_run_remediation      # child did NOT reach terminal — retry path
    on_error: record_sub_loop_crash
```

### 5. [rubric, observation] No `llm_structured` evaluators in the parent — quality gates rely on shell-test predicates

**Rationale**: All readiness/outcome gating in `rn-implement` uses shell-test exits (`check_readiness` calls `ll-issues check-readiness`). The LLM-evaluator layer is inside `rn-remediate`'s sub-loop. This is fine architecturally, but means the parent cannot catch semantic regressions like "score improved but quality degraded". Not actionable for this audit, but worth noting for future rubric-vs-description work.

---

## Deduplication check

```
$ grep -rl "rn-implement" .issues/   → no matches
$ grep -rl "rn-remediate" .issues/   → no matches
$ grep -rl "ANTHROPIC_API_KEY|authentication" .issues/bugs/   → no matches
```

**0 duplicate issues.** All 5 proposals above are net-new.

---

## Final Report

```
Assessment complete for loop: rn-implement (run 2026-06-27T210732)

Verdict: `phantom`
Rubric audit: 0 evaluators checked, 0 flagged
Laundering check: 2 sub-loop states checked, 2 flagged (mitigated via artifact-channel)
Shallow-iteration check: `clear` (91 tool calls, 39 auxiliary mutations)
Issues created: 0 (no duplicates; output written to file per user request)
```

**Headline finding**: The loop ran for 33 minutes (21:07–21:40), correctly identified all 5 issues as ready for implementation (confidence ≥ 85, outcome ≥ 75 for every issue), wrote 39 auxiliary artifacts (diagnosis, convergence, scores, complexity_band, subloop_outcome per issue), and recorded every failure honestly — but **zero issues were implemented** because the `implement` state invokes `ll-auto`, which requires `ANTHROPIC_API_KEY` (or equivalent OAuth state) and none was configured. This is a structural defect in the loop's pre-flight checks, not a logic bug in remediation or routing.

---

## Recommendations

1. **Before re-running `rn-implement`**: configure `ANTHROPIC_API_KEY` (or run `claude login`) in the host environment. Without this, the loop will always fail at the `implement` state regardless of how well remediation scores.

2. **For loop authors**: implement the pre-flight auth check from Proposal #1 directly in the `init` state of `rn-implement.yaml`. This converts silent failure to explicit, fast-fail behavior — saves ~5 minutes per issue in failed `ready-issue` calls.

3. **For users**: when batching issues with declared dependencies (`blocked_by`), include all transitive deps in the input. The current `BUG-366` failure (open dep on `BUG-367`) could have been prevented by invoking `ll-loop run rn-implement "BUG-366,BUG-367"` or running `rn-decompose` first.

4. **For loop authors**: consider Proposal #4's refactor to make `on_yes != on_no` structurally explicit, even though the current artifact-channel pattern works. This makes the FSM self-documenting and removes a class of audit false-positives.

5. **For future audits**: the audit correctly distinguished "honest failure with no artifact mutations" (phantom) from "self-deception" (also phantom, but via `llm_structured` evaluator). Both share the verdict but for different reasons — track this in future skill improvements.