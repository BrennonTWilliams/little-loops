# Audit Report — `sprint-refine-and-implement` Run 2026-06-28

**Generated**: 2026-06-28
**Audited loop**: `sprint-refine-and-implement`
**Run folder**: `.loops/.history/2026-06-28T172211-sprint-refine-and-implement/`
**Scope (input)**: `EPIC-364` — article publication pipeline
**Duration**: 17:22:11 → 18:25:56 UTC (~64 min)
**Loop description**: Alias for `auto-refine-and-implement` scoped to a named sprint or EPIC. Delegates to `auto-refine-and-implement` with `scope=<sprint-name|EPIC-NNN>`. Preserved for backward compatibility.

---

## TL;DR

The loop **did its job** — refined 3 issues (FEAT-366, FEAT-368, FEAT-370), decomposed the umbrella EPIC into 10+ child issues (FEAT-371 through FEAT-380), and rewired 3 MOC files. However, the summary's `verdict=partial` is **artifactual**: a bug in a sub-loop (`implement-issue-chain.yaml:36-39`) writes passed issues into the SKIP file, contaminating the verdict counter. All three processed issues were both refined AND implemented successfully; the actual outcome is closer to `success` than `partial`.

**One critical bug, two minor improvements recommended.**

---

## 1. Goal-vs-Outcome Scorecard

| Field | Value |
|---|---|
| **Goal** | Delegate to `auto-refine-and-implement` for `EPIC-364` |
| **Contract** | None in audited loop's FSM (only `context.sprint_name` param). Sub-loop's `finalize` defines: `success` iff `IMPL>0 && ERR==0 && SKIP==0` |
| **Artifacts checked** | `.loops/runs/.../summary.json`, `auto-refine-and-implement-implemented.txt`, `auto-refine-and-implement-skipped.txt`, 3× `.issues/features/P3-FEAT-36{6,8,70}-*.md`, 10+ new child issue files, 3 MOC files |
| **Phase 1 fault signals** | None (0 SIGKILL, 0 fatal, 0 eval errors; 19 exit_code=1 are all paired with evaluate verdict=no — expected non-error negative verifications) |
| **Shallow-iteration check** | `clear` (73 action_start events, 10+ auxiliary mutations) |
| **Budget utilization** | 15/100 iterations (15%) — budget was not exhausted |
| **Verdict** | `partial` (per loop's own summary) |

### Verdict rationale

The `partial` verdict in `summary.json` is the loop's own classification, computed by `auto-refine-and-implement.finalize`:

```bash
if   [ "$ERR" -gt 0 ] && [ "$IMPL" -eq 0 ]; then VERDICT=phantom
elif [ "$IMPL" -gt 0 ] && [ "$ERR" -eq 0 ] && [ "$SKIP" -eq 0 ]; then VERDICT=success
elif [ "$IMPL" -gt 0 ]; then VERDICT=partial
else VERDICT=no-op
fi
```

With `IMPL=3, ERR=0, SKIP=3`, the verdict falls into the `IMPL>0` branch, which is `partial`. But `SKIP=3` is an **artifact** (see Bug #1 below) — the 3 "skipped" IDs are identical to the 3 "implemented" IDs because the same loop wrote them to both files. Excluding the bug, the run is `success`-class.

### Artifacts

```
.lops/runs/sprint-refine-and-implement-20260628T122211/auto-refine-and-implement-implemented.txt
FEAT-366
FEAT-368
FEAT-370

.lops/runs/sprint-refine-and-implement-20260628T122211/auto-refine-and-implement-skipped.txt
FEAT-366     ← same as implemented!
FEAT-368     ← same as implemented!
FEAT-370     ← same as implemented!

.lops/runs/sprint-refine-and-implement-20260628T122211/auto-refine-and-implement-errored.txt
(empty)
```

**Real work done** (verified via git):
- 3 implementation issue files modified (FEAT-366, FEAT-368, FEAT-370) — totaling ~640 lines added
- 10 new child issues created (FEAT-371 through FEAT-380) as decomposition children
- 3 MOC files rewritten (article-candidate schema, drift-detection, audience-ladder)
- Commit: `3beb69b1 feat(issues): refine EPIC-364 article-candidate pipeline and decompose umbrella features`

---

## 2. Rubric-vs-Description Audit

**Skipped** — the audited FSM (`sprint-refine-and-implement`) contains no `evaluate.type: llm_structured` states. Its 4 states (`delegate`, `read_outcome`, `record_crash`, `done`) are all shell actions or terminals. Evaluators live in sub-loops (`recursive-refine`, `implement-issue-chain`, `refine-to-ready-issue`), not in the audited loop.

---

## 3. Sub-Loop Verdict Laundering Check

**1 sub-loop state checked, 0 unmitigated defects.**

### `delegate` (loop: `auto-refine-and-implement`)

```
on_yes:  read_outcome
on_no:   read_outcome    ← identical, candidate laundering pattern
on_error: record_crash  ← distinct error path
```

This matches the textbook verdict-laundering signature (`on_yes == on_no` → child verdict collapsed). However, **ENH-2005 artifact-channel sidecar exemption applies**:

1. ✓ Shared next state `read_outcome`'s action reads `subloop_outcome_auto-refine-and-implement.txt`:
   ```bash
   OUTCOME="$RUN_DIR/subloop_outcome_auto-refine-and-implement.txt"
   VERDICT=$(cat "$OUTCOME" 2>/dev/null || echo unknown)
   ```
2. ✓ `on_error` routes to **distinct** state `record_crash` (not collapsed into the generic failure path)

Both ENH-2005 conditions hold — the child verdict is recovered via artifact, not collapsed. **No fix needed.**

---

## 4. Findings & Recommendations

### Finding #1 — CRITICAL: `implement-issue-chain.yaml:36-39` writes PASSED issues to SKIPPED file

**Location**: `scripts/little_loops/loops/oracles/implement-issue-chain.yaml`, state `get_passed_issues`, lines 23-44.

**Defective code**:
```bash
if [ -s ${context.run_dir}/recursive-refine-skipped.txt ]; then
  grep -v '^[[:space:]]*$' ${context.run_dir}/recursive-refine-skipped.txt >> "$SKIP_FILE"
fi

PASSED=""
if [ -s ${context.run_dir}/recursive-refine-passed.txt ]; then
  PASSED=$(grep -v '^[[:space:]]*$' ${context.run_dir}/recursive-refine-passed.txt)
fi

if [ -n "$PASSED" ]; then
  echo "$PASSED" >> "$SKIP_FILE"          # ← BUG: writes PASSED IDs to SKIP file
  echo "$PASSED" > "$IMPL_QUEUE"
  exit 0
else
  printf '' > "$IMPL_QUEUE"
  exit 1
fi
```

**Bug summary**: When `recursive-refine-passed.txt` is non-empty, the loop appends the passed IDs to `${caller_prefix}-skipped.txt`. This is a counter pollution: a passed issue is recorded as both implemented AND skipped.

**Effect on this run**:
- 3 issues (FEAT-366, FEAT-368, FEAT-370) ended up in BOTH `auto-refine-and-implement-implemented.txt` AND `auto-refine-and-implement-skipped.txt`
- `SKIP=3, IMPL=3, ERR=0` → verdict fell into the `IMPL>0` branch of the verdict logic → `partial` instead of `success`
- The summary mis-reports a successful run as partial

**Impact**: Every invocation of `sprint-refine-and-implement` (or `auto-refine-and-implement`) that processes at least one passed issue will be misclassified as `partial` regardless of actual outcome. The verdict metric is unusable until fixed.

**Recommended fix**:

```yaml
# scripts/little_loops/loops/oracles/implement-issue-chain.yaml
states:
  get_passed_issues:
    action: |
      SKIP_FILE="${context.run_dir}/${context.caller_prefix}-skipped.txt"
      IMPL_QUEUE="${context.run_dir}/${context.caller_prefix}-impl-queue.txt"

      # Append ONLY actual refinement-skipped issues (not the passed ones).
      if [ -s ${context.run_dir}/recursive-refine-skipped.txt ]; then
        grep -v '^[[:space:]]*$' ${context.run_dir}/recursive-refine-skipped.txt >> "$SKIP_FILE"
      fi

      PASSED=""
      if [ -s ${context.run_dir}/recursive-refine-passed.txt ]; then
        PASSED=$(grep -v '^[[:space:]]*$' ${context.run_dir}/recursive-refine-passed.txt)
      fi

      if [ -n "$PASSED" ]; then
        # FIX: passed IDs go to IMPL_QUEUE only. They are NOT skipped — they proceed to implementation.
        echo "$PASSED" > "$IMPL_QUEUE"
        exit 0
      else
        printf '' > "$IMPL_QUEUE"
        exit 1
      fi
    fragment: shell_exit
    on_yes: implement_next
    on_no: done
    on_error: done
```

**Regression test recommendation**: Add a unit test that verifies, given a populated `recursive-refine-passed.txt` and empty `recursive-refine-skipped.txt`, that:
- `IMPL_QUEUE` contains the passed IDs
- `SKIP_FILE` is empty (or remains unchanged)

---

### Finding #2 — MEDIUM: Decision-needed issues may proceed to implementation without review

**Location**: `recursive-refine` → `decision_needed` branch (state names not present in this audit's events since `state` field is null in evaluate events; investigate `recursive-refine.yaml`).

**Defect evidence**: 
- `recursive-refine-skipped-decision.txt` contains `FEAT-370` (indicating `refine-to-ready-issue` classified FEAT-370 as needing human decision via its `confidence_check` failed → `diagnose` step)
- Yet `record_implemented` was still called for FEAT-370 at 18:25:56.180689

**Two possible root causes**:
1. The `decision_needed` path is *expected* to fall through to implementation (e.g., via `/ll:decide-issue`), but the FSM doesn't make this explicit. In that case, the path is fine — but it should be documented and the `skipped-decision.txt` naming is misleading.
2. There's a state-machine bug where the implement path doesn't check the decision flag. In that case, FEAT-370 was implemented without any human review.

**Recommended investigation**:
- Read `recursive-refine.yaml` and `refine-to-ready-issue.yaml` to determine which of the two scenarios applies
- If the path is intentional, rename `skipped-decision.txt` to `decision-needed.txt` and document the policy
- If unintentional, add a guard in `implement-issue-chain.yaml` (or upstream) that blocks issues present in `recursive-refine-skipped-decision.txt`

---

### Finding #3 — LOW: `record_error` increments both ERR and SKIP, conflating crashes with refinement-failures

**Location**: `scripts/little_loops/loops/auto-refine-and-implement.yaml` → state `record_error`.

**Defective code**:
```bash
echo "${captured.input.output}" >> ${context.run_dir}/auto-refine-and-implement-errored.txt
echo "${captured.input.output}" >> ${context.run_dir}/auto-refine-and-implement-skipped.txt
```

A crash on refinement increments both `ERR` and `SKIP`. The verdict logic in `finalize` treats `ERR > 0` as a hard failure mode (`phantom` if `IMPL==0`), but `SKIP > 0` is checked independently for `success`. A single crash + 3 successes would yield `IMPL>0 && ERR>0` → currently classified as `partial`, but is really a degraded outcome.

**Recommended**: Add a 5th verdict `partial-with-errors` (or `degraded`) for the case `IMPL > 0 && ERR > 0`:

```bash
# In auto-refine-and-implement.yaml finalize state:
if   [ "$ERR" -gt 0 ] && [ "$IMPL" -eq 0 ]; then VERDICT=phantom
elif [ "$IMPL" -gt 0 ] && [ "$ERR" -gt 0 ]; then VERDICT=partial-with-errors   # NEW
elif [ "$IMPL" -gt 0 ] && [ "$SKIP" -eq 0 ]; then VERDICT=success
elif [ "$IMPL" -gt 0 ]; then VERDICT=partial
else VERDICT=no-op
fi
```

This is a minor cosmetic improvement — current `partial` is technically correct but loses signal about whether ERR > 0.

---

## 5. Recommendations Summary (prioritized)

| # | Severity | File | Change | Effort |
|---|---|---|---|---|
| 1 | CRITICAL | `scripts/little_loops/loops/oracles/implement-issue-chain.yaml` | Remove `echo "$PASSED" >> "$SKIP_FILE"` from `get_passed_issues` (line 37) | 5 min |
| 2 | MEDIUM | `scripts/little_loops/loops/recursive-refine.yaml` + `refine-to-ready-issue.yaml` | Audit `decision_needed` path to confirm intent; either rename file or add guard | 1-2 hr |
| 3 | LOW | `scripts/little_loops/loops/auto-refine-and-implement.yaml` | Add `partial-with-errors` verdict case | 15 min |

### Suggested verification

After applying Fix #1:
```bash
# Replay the run scenario with manual fixture
mkdir -p /tmp/audit-fix-test
cd /tmp/audit-fix-test
echo "FEAT-366" > recursive-refine-passed.txt
echo "FEAT-368" >> recursive-refine-passed.txt
# Run implement-issue-chain get_passed_issues action
# Verify SKIP_FILE is empty and IMPL_QUEUE has both IDs
```

After applying all fixes, re-run:
```bash
ll-loop run sprint-refine-and-implement --input scope=EPIC-364
# Expect verdict=success (or whatever EPIC-364's actual outcome is)
```

---

## 6. Audit Methodology Notes

- **Pre-flight gate**: events.jsonl (240,580 bytes) and state.json (1,097 bytes) both non-empty. Gate passed.
- **History loaded**: 952 events (full run, no `--tail` truncation)
- **Event type distribution**: 569 action_output, 86 state_enter, 86 route, 73 action_start, 73 action_complete, 43 evaluate, 11 loop_start, 11 loop_complete
- **Loop nesting depth observed**: 3 (sprint-refine-and-implement → auto-refine-and-implement → recursive-refine / implement-issue-chain → refine-to-ready-issue)
- **Sub-loop terminations**: 10 loop_complete events, all `terminated_by=terminal` (no SIGKILL/fatal)
  - 3× depth=3 `refine-to-ready-issue` final_state=`failed` (confidence_check failures — see Finding #2)
  - 7× depth≤2 final_state=`done`

---

## 7. Files Referenced

- `.loops/.history/2026-06-28T172211-sprint-refine-and-implement/events.jsonl` — 952 events
- `.loops/.history/2026-06-28T172211-sprint-refine-and-implement/state.json` — final captures
- `.loops/.history/2026-06-28T172211-sprint-refine-and-implement/summary.json` — `{"verdict":"partial","implemented":3,"skipped":3,"errored":0}`
- `.loops/runs/sprint-refine-and-implement-20260628T122211/` — run artifacts
- `scripts/little_loops/loops/oracles/implement-issue-chain.yaml` — bug source (line 37)
- `scripts/little_loops/loops/auto-refine-and-implement.yaml` — verdict logic (Finding #3)
- `scripts/little_loops/loops/recursive-refine.yaml` — needs investigation (Finding #2)
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` — needs investigation (Finding #2)
- `.issues/features/P3-FEAT-366-article-publication-dashboard-note.md` — modified
- `.issues/features/P3-FEAT-368-per-candidate-append-only-journal.md` — modified
- `.issues/features/P3-FEAT-370-promotion-writes-published-url-to-frontmatter.md` — modified