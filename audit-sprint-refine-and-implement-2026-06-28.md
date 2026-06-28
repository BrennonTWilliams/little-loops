# Audit: `sprint-refine-and-implement` run `2026-06-28T172211`

**Audited run**: `.loops/.history/2026-06-28T172211-sprint-refine-and-implement/`
**Scope**: `EPIC-364` (article-publication pipeline with progressive audience ladder)
**Duration**: 17:22:11 → 18:25:56 (~64 min)
**Verifier verdict (per loop summary)**: `partial` — `{"implemented":3,"skipped":3,"errored":0}`
**Auditor verdict**: `partial` (artifactual — see Bug #1)

---

## 1. Goal-vs-Outcome Scorecard

**Goal**: Alias for `auto-refine-and-implement` scoped to a named sprint or EPIC. Delegates to `auto-refine-and-implement` with `scope=<sprint-name|EPIC-NNN>`.

**Contract**: No threshold contract detected in `sprint-refine-and-implement`'s own FSM (only `context.sprint_name` parameter). The success contract lives in the sub-loop's `finalize` state: `success` if `IMPL > 0 && ERR == 0 && SKIP == 0`, else `partial` if `IMPL > 0`.

**Artifacts checked**:

| Path | Status |
|---|---|
| `.loops/runs/sprint-refine-and-implement-20260628T122211/auto-refine-and-implement-implemented.txt` | 3 IDs (FEAT-366, FEAT-368, FEAT-370) — mutated |
| `.loops/runs/sprint-refine-and-implement-20260628T122211/auto-refine-and-implement-skipped.txt` | 3 IDs — artifactual (see Bug #1) |
| `.loops/runs/sprint-refine-and-implement-20260628T122211/summary.json` | `{"verdict":"partial","implemented":3,"skipped":3,"errored":0}` — written |
| `.issues/features/P3-FEAT-366-article-publication-dashboard-note.md` | +240 lines (wiring, decomposition, scope context) |
| `.issues/features/P3-FEAT-368-per-candidate-append-only-journal.md` | +207 lines |
| `.issues/features/P3-FEAT-370-promotion-writes-published-url-to-frontmatter.md` | modified |
| 10 new decomposed children: FEAT-371 through FEAT-380 | created |
| 3 MOC files (article-candidate schema, drift-detection, audience-ladder) | modified |
| Issue frontmatter `status: open → closed` | **NOT done** — see Finding 2 |

**Phase 1 fault signals**: None. 0 SIGKILL, 0 FATAL_ERROR, 0 evaluate errors, 0 throttle stops. The 19 `exit_code=1` actions are all correlated 1:1 with 19 `evaluate verdict=no` (expected non-error negative verifications at depth=2/3 sub-loops).

**Shallow-iteration check**: `clear` (73 action_start events; 10+ auxiliary mutations including decomposed issues and MOC rewrites).

**Budget check**: 15/100 iterations consumed (15%) — well below 30% exhaustion threshold. Budget was not the limiting factor.

**Verdict**: `partial`

**Rationale**: All 3 target issues (FEAT-366, FEAT-368, FEAT-370) were refined, and the umbrella EPIC-364 was decomposed into 10 child issues plus 3 MOC rewrites. The summary's `verdict=partial` is purely a counter pollution artifact caused by Bug #1 below — the loop's actual work output is closer to `success` (3 implemented, 0 errored) but the `SKIP` counter was contaminated, tripping the `IMPL>0 && SKIP>0 → partial` branch.

---

## 2. Rubric-vs-Description Audit

**Skipped** — `sprint-refine-and-implement` FSM contains no `evaluate.type: llm_structured` states. The 4 states are `delegate`, `read_outcome`, `record_crash`, `done` — all shell actions or terminal.

---

## 3. Sub-Loop Verdict Laundering Check

**1 sub-loop state checked, 0 unmitigated.**

- `delegate` (loop: `auto-refine-and-implement`, on_yes: `read_outcome`, on_no: `read_outcome`)

  Verdict-laundering pattern detected (`on_yes == on_no` → child verdict collapsed), **but mitigated by ENH-2005 artifact-channel sidecar**:
  - ✓ Shared next state `read_outcome` reads `subloop_outcome_auto-refine-and-implement.txt`
  - ✓ `on_error` routes to distinct state `record_crash` (not collapsed into the generic failure path)

  No fix needed. `[mitigated — ENH-2005 artifact-channel sidecar: verdict recovered via subloop_outcome_ artifact, on_error routes to distinct crash state]`

---

## 4. Findings & Recommendations

### Finding 1 (CRITICAL) — `implement-issue-chain.yaml:36-39` writes PASSED issues to SKIPPED file, corrupting verdict counter

**Where**: `scripts/little_loops/loops/oracles/implement-issue-chain.yaml` → state `get_passed_issues`, lines 36-39.

**Defect**:
```bash
if [ -n "$PASSED" ]; then
  echo "$PASSED" >> "$SKIP_FILE"     # ← writes passed issues to SKIP file
  echo "$PASSED" > "$IMPL_QUEUE"
  exit 0
fi
```

When `recursive-refine-passed.txt` is non-empty, the loop appends the passed IDs to `${caller_prefix}-skipped.txt`. This contaminates the `SKIP` counter used by the parent's `finalize` state to compute verdict.

**Effect on this run**: 3 issues (FEAT-366, FEAT-368, FEAT-370) were recorded in BOTH `implemented.txt` AND `skipped.txt`. Final verdict was `partial` instead of `success`. The `SKIP_FILE` accumulation pattern was the dominant cause of misleading verdicts.

**Recommended fix** (YAML diff):

```yaml
# scripts/little_loops/loops/oracles/implement-issue-chain.yaml
states:
  get_passed_issues:
    action: |
      SKIP_FILE="${context.run_dir}/${context.caller_prefix}-skipped.txt"
      IMPL_QUEUE="${context.run_dir}/${context.caller_prefix}-impl-queue.txt"

      # Append only the actual refinement-skipped issues (not the passed ones)
      if [ -s ${context.run_dir}/recursive-refine-skipped.txt ]; then
        grep -v '^[[:space:]]*$' ${context.run_dir}/recursive-refine-skipped.txt >> "$SKIP_FILE"
      fi

      PASSED=""
      if [ -s ${context.run_dir}/recursive-refine-passed.txt ]; then
        PASSED=$(grep -v '^[[:space:]]*$' ${context.run_dir}/recursive-refine-passed.txt)
      fi

      if [ -n "$PASSED" ]; then
        # FIX: do not write passed IDs to SKIP_FILE — they are being implemented, not skipped
-       echo "$PASSED" >> "$SKIP_FILE"
        echo "$PASSED" > "$IMPL_QUEUE"
        exit 0
      else
        printf '' > "$IMPL_QUEUE"
        exit 1
      fi
```

**Why this is critical**: The bug will recur on every `sprint-refine-and-implement` invocation that has any successful refinement. The `partial` verdict misleads sprint health, and the duplicate IDs make downstream deduplication (e.g., `ll-issues next-issue --skip`) behave incorrectly.

---

### Finding 2 (HIGH) — `record_implemented` is a misleading name; the loop's "Implemented" message does not match actual issue state

**Where**: `scripts/little_loops/loops/auto-refine-and-implement.yaml` → `record_implemented` action.

**Observation**: All 3 issues claimed as "implemented" (FEAT-366, FEAT-368, FEAT-370) remain `status: open` in their frontmatter after the run. The recent commit that touched them was:

```
3beb69b1 feat(issues): refine EPIC-364 article-candidate pipeline and decompose umbrella features
```

That commit added ~240 lines of context to each umbrella (wiring passes, decomposition children, scope clarification) and **decomposed 10 child issues (FEAT-371 through FEAT-380)**. It was a **refinement commit, not an implementation commit**.

**What `record_implemented` actually does**:
```bash
record_implemented:
  action: |
    echo "Implemented ${captured.input.output}"
    echo "${captured.input.output}" >> ${context.run_dir}/auto-refine-and-implement-implemented.txt
```

- ✅ Echoes "Implemented FEAT-NNN" to the run log
- ✅ Appends the ID to a local tracking file in `.loops/runs/.../`
- ❌ Does **not** update the issue's frontmatter `status: open → closed`
- ❌ Does **not** invoke any closing/shipping ceremony
- ❌ Does **not** produce code, tests, or shipped artifacts

**What the loop actually delivered in this run**:
- ✅ Refined 3 umbrella features (added extensive wiring/context/decomposition plans)
- ✅ Decomposed the umbrella features into 10 actionable child issues (FEAT-371 through FEAT-380)
- ✅ Updated 3 MOCs (article-candidate schema, drift detection, audience ladder)
- ❌ Closed zero issues
- ❌ Shipped zero features
- ❌ Verified zero work via go-no-go → ll-auto (FEAT-370 bypassed entirely; FEAT-366/368 status of actual ll-auto runs unverified in this audit)

**Recommendations** (any of these would help):

1. **Rename the state**. `record_implemented` → `record_processed` or `record_refined`. Rename the tracking file from `*-implemented.txt` to `*-processed.txt`. This is a vocabulary fix that doesn't change behavior.

2. **Add a status transition**. Have the action call `ll-issues set-status FEAT-NNN --to closed` (or whatever the appropriate terminal status is for that issue type) when recording. Only do this when the issue was actually worked, not when it was refined-and-decomposed.

3. **Split the tracking into two files**. `*-refined.txt` (issues whose content was rewritten/refined) and `*-implemented.txt` (issues whose status was transitioned to a terminal state). This makes the difference explicit in the data.

4. **Add a third verdict** to the success contract: `refined-decomposed` (work done but no closure). The current `success / partial / phantom / no-op / crashed` taxonomy doesn't capture "decomposed umbrellas into children."

---

### Finding 3 (HIGH) — Sub-loop terminal ≠ work succeeded in parent's `on_yes` semantics

**Where**: `scripts/little_loops/loops/auto-refine-and-implement.yaml` → state `implement_chain`, transition `on_yes → record_implemented`.

**Observation**: Tracing FEAT-370 specifically:

1. `refine-to-ready-issue` (depth=3) terminated with `final_state=failed` for FEAT-370 (confidence_check failed)
2. `recursive-refine` (depth=2) classified this as `decision_needed` → wrote to `recursive-refine-skipped-decision.txt`
3. `implement-issue-chain` (depth=2) ran `get_passed_issues` → `recursive-refine-passed.txt` was **empty** → exit 1 → `on_no: done`
4. The sub-loop hit its terminal `done` state, so the parent `auto-refine-and-implement`'s `on_yes` fired → `record_implemented`

So FEAT-370 was:
- Refinement **FAILED**
- Marked `decision_needed`
- Never actually queued for `ll-auto` implementation
- Still got written to `auto-refine-and-implement-implemented.txt` and emitted "Implemented FEAT-370" in the run log

**Why this is a defect**: The parent loop treats **sub-loop terminal arrival** as success, regardless of whether the sub-loop's work succeeded. The sub-loop's terminal `done` state is reachable via three paths:
- `get_passed_issues.on_no: done` (no passed issues → nothing to do)
- `implement_next.on_no: done` (queue empty → done)
- normal completion of all queued items

Only the third path represents actual successful work. The first two are "nothing-to-do" exits that should not trigger `record_implemented`.

**Recommended fix**: Have `implement-issue-chain` distinguish "successful completion" from "nothing to do." Options:

1. **Add a capture variable to the sub-loop** that records whether any work happened. Parent checks the capture before recording.
2. **Add a sentinel artifact** (e.g., `${run_dir}/implement-issue-chain-worked.txt`) that the sub-loop writes only when actual work completed. Parent reads the sentinel in `record_implemented` before appending.
3. **Re-architect to use `on_error`** for the nothing-to-do case. Currently `get_passed_issues.on_no: done` is treated as a success by the parent. If the sub-loop used `exit 2` (an error code) for nothing-to-do and the parent mapped that to `on_error → finalize`, the parent would correctly route to finalize rather than `record_implemented`.

---

### Finding 4 (MEDIUM) — `decision_needed` issues still fall through to `record_implemented`

**Where**: `recursive-refine` sub-loop's `decision_needed` branch.

**Defect**: FEAT-370 appears in `recursive-refine-skipped-decision.txt` (indicating `refine-to-ready-issue` classified it as needing human decision), yet the run still went through `record_implemented` for FEAT-370. Either:
- The `decision_needed` path is writing to `skipped-decision` but the issue still proceeds to implementation (silent override)
- Or there's a state-machine bug where the implement path doesn't check the decision flag

**Effect on this run**: An issue that needed human review was treated as successfully implemented without review.

**Recommended fix**: Verify whether `recursive-refine` correctly blocks `implement-issue-chain` when an issue lands in `recursive-refine-skipped-decision.txt`. If `decision_needed` issues should be implemented (e.g., with a `/ll:decide-issue` step in between), make that explicit in the FSM. If they should be paused for human review, the FSM should route them to a `human_review_required` terminal that does NOT write to `implemented.txt`.

---

### Finding 5 (MEDIUM) — `ll-issues list --group-by epic` is not transitive

**Where**: `ll-issues list --group-by epic` rendering.

**Observation**: The `--group-by epic` flag groups by `parent` only when the parent's type is `EPIC`. It does **not** walk the chain transitively (EPIC → umbrella FEAT → child FEAT). The children created during this run:

| Child | parent field |
|---|---|
| FEAT-371 | `parent: FEAT-365` |
| FEAT-372 | `parent: FEAT-365` |
| FEAT-373 | `parent: FEAT-365` |
| FEAT-374 | `parent: FEAT-365` |
| FEAT-375 | `parent: FEAT-367` |
| FEAT-376 | `parent: FEAT-367` |
| FEAT-377 | `parent: FEAT-367` |
| FEAT-378 | `parent: FEAT-369` |
| FEAT-379 | `parent: FEAT-369` |
| FEAT-380 | `parent: FEAT-369` |

These children have `parent: FEAT-NNN` (an umbrella feature), not `parent: EPIC-364`. The umbrella features (FEAT-365, FEAT-367, etc.) have `parent: EPIC-364`, so the chain is:

```
EPIC-364
├── FEAT-365
│   ├── FEAT-371
│   ├── FEAT-372
│   ├── FEAT-373
│   └── FEAT-374
├── FEAT-367
│   ├── FEAT-375
│   ├── FEAT-376
│   └── FEAT-377
└── FEAT-369
    ├── FEAT-378
    ├── FEAT-379
    └── FEAT-380
```

`--group-by epic` only goes one level deep, so FEAT-371 through FEAT-380 fall into the "no epic" bucket.

**Recommendations** (in increasing order of invasiveness):

1. **Make `--group-by epic` transitive** (preferred). Walk `parent` chains up to the nearest EPIC ancestor. Preserves both the FEAT-365 → FEAT-371 link (you can still see "FEAT-371 is a child of FEAT-365, which is under EPIC-364") and the EPIC-364 grouping.

2. **Add `--group-by epic --depth N`** flag for users who want explicit depth control.

3. **Add an `epic:` frontmatter field** in addition to `parent`. The tool could read `epic` directly without traversing. Duplicates the relationship explicitly. More invasive — touches every issue file and the schema.

---

### Finding 6 (MEDIUM) — FEAT-369 file is missing; FEAT-378/379/380 reference an orphan parent

**Where**: `.issues/features/` — expected file `P2-FEAT-369-*.md` or similar.

**Observation**: `ll-issues path FEAT-369` returns empty. Yet the recent commit added three children with `parent: FEAT-369`:
- FEAT-378 (drift-check detection core)
- FEAT-379 (drift-reconcile actions)
- FEAT-380 (schema dashboard wiring)

The umbrella FEAT-369 (presumably "vault-website drift detection and reconcile") is referenced by 3 children but does not exist as a file.

**Possible explanations**:
- FEAT-369 was never created in the original epic authoring commit (`bcfc4bfb feat(issues): add article publication pipeline epic with progressive audience ladder`)
- FEAT-369 was created and then deleted/renamed in a subsequent commit
- The decomposition children were authored before their umbrella and the umbrella creation step was skipped

**Effect**: Any tool that walks `parent` chains will hit a dead end at FEAT-369. `--group-by epic` (even if made transitive per Finding 5) will not be able to associate FEAT-378/379/380 with EPIC-364 because the chain breaks at FEAT-369.

**Recommendation**: Either create the missing FEAT-369 file, or change FEAT-378/379/380's `parent` field to `EPIC-364` directly (skipping the missing umbrella).

---

### Finding 7 (LOW) — `record_error` increments both `errored.txt` AND `skipped.txt`

**Where**: `scripts/little_loops/loops/auto-refine-and-implement.yaml` → `record_error` action.

**Defect**:
```bash
echo "${captured.input.output}" >> ${context.run_dir}/auto-refine-and-implement-errored.txt
echo "${captured.input.output}" >> ${context.run_dir}/auto-refine-and-implement-skipped.txt
```

A crash on refinement increments both `ERR` and `SKIP`. The verdict logic in `finalize`:
```bash
if [ "$IMPL" -gt 0 ] && [ "$ERR" -eq 0 ] && [ "$SKIP" -eq 0 ]; then
  VERDICT=success
elif [ "$IMPL" -gt 0 ]; then
  VERDICT=partial
```

A single crash with no successful implementations triggers `phantom`; a single crash with successful implementations triggers `partial`. But the `ERR > 0 && IMPL > 0` case is also `partial`, which loses the signal that something errored.

**Recommendation**: Add a 5th verdict `partial-with-errors` for the case where `IMPL > 0 && ERR > 0`. This makes crash visibility distinct from skipped-but-no-error visibility.

---

### Finding 8 (LOW) — Loop name and scope-of-work ambiguity

**Where**: Naming of the `sprint-refine-and-implement` / `auto-refine-and-implement` chain.

**Observation**: The names imply these loops will "implement" issues. In practice, for issues that need decomposition, the loop only refines and decomposes — it does not implement the work itself. For issues that don't need decomposition, the loop does invoke `ll-auto` (via `implement-issue-chain`), but the success of that call is implicit (the parent fires `record_implemented` whenever the sub-loop terminates, per Finding 3).

**Recommendation**: Either:
1. Rename the loops to reflect actual behavior (`sprint-refine-and-decompose` / `auto-refine-and-decompose`).
2. Keep the names and clearly document the "decompose umbrella into children" behavior in the loop description and `ll-auto` help text.

---

## 5. Summary of Recommended Actions

| Priority | Finding | Action |
|---|---|---|
| CRITICAL | #1 | Remove `echo "$PASSED" >> "$SKIP_FILE"` line in `implement-issue-chain.yaml:37` |
| HIGH | #2 | Rename `record_implemented` → `record_processed`, or add real status transition |
| HIGH | #3 | Add sentinel artifact or capture variable to distinguish sub-loop "nothing to do" from "work done" |
| MEDIUM | #4 | Make `decision_needed` a true halt path, not a silent skip |
| MEDIUM | #5 | Make `--group-by epic` transitive in `ll-issues` |
| MEDIUM | #6 | Create missing FEAT-369 file or reparent FEAT-378/379/380 to EPIC-364 |
| LOW | #7 | Add `partial-with-errors` verdict in `auto-refine-and-implement.finalize` |
| LOW | #8 | Document the refine-decompose-implement behavior split |

---

## 6. Audit Metadata

- **Auditor**: `/ll:audit-loop-run sprint-refine-and-implement`
- **Run duration**: 64 min (17:22:11 → 18:25:56 UTC)
- **Events analyzed**: 952
- **Sub-loops traversed**: `auto-refine-and-implement`, `recursive-refine`, `implement-issue-chain`, `refine-to-ready-issue`
- **No issue files created** — per user request, all findings consolidated here.