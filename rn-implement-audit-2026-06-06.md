# rn-implement Loop Audit — 2026-06-06

**Run**: `2026-06-06T015949` | **Status**: `completed` | **Iterations**: 42 | **Duration**: ~67 min (~4,012s accumulated)
**Repository**: loop-viz | **Verdict**: `partial`

---

## Goal-vs-Outcome Scorecard

**Goal**: "Queue orchestrator for recursive plan-and-implement. Manages a depth-bounded issue queue, delegating per-issue remediation to rn-remediate and decomposition to rn-decompose."

**Contract**:
| Key | Value | Source |
|---|---|---|
| `readiness_threshold` | 85 | context |
| `outcome_threshold` | 75 | context |
| `max_depth` | 3 | context |
| `max_remediation_passes` | 3 | context |

**Artifacts checked**:
| Path | Mutation |
|---|---|
| `.loops/runs/rn-implement-20260605T205949/summary.json` | Written (report state) |
| `.loops/runs/rn-implement-20260605T205949/skipped.txt` | 8 entries written |
| `.loops/runs/rn-implement-20260605T205949/implemented_count.txt` | `0` — no implementations |
| `.loops/runs/rn-implement-20260605T205949/decomposed_count.txt` | `1` (FEAT-1716 → FEAT-1718, FEAT-1719) |
| Issue frontmatter (confidence scores) | Updated for FEAT-1708, FEAT-1709, FEAT-1710, FEAT-1713, FEAT-1716, FEAT-1717 |
| `depth_map.txt` | FEAT-1718→1, FEAT-1719→1 |
| `visited.txt` | 10 entries (all issues + children) |

**Verdict**: **`partial`**

**Rationale**: The loop reached its terminal `done` state via `report → done` and wrote a well-formed summary artifact. Queue processing, depth tracking, cycle detection, and report generation all functioned correctly. However, the **primary contract failed**: 0 of 8 issues were implemented. Every remediation attempt hit the same `verify_scores_persisted` context-resolution bug (`Path 'run_dir' not found in context`), causing all `rn-remediate` sub-loops to terminate in `failed` before reaching the `implement` state. The one decomposition (FEAT-1716 → FEAT-1718, FEAT-1719) correctly identified children, but those children were subsequently processed through the same broken remediation path and also skipped. The loop's machinery runs — the pipeline just can't deliver its payload.

### Per-Issue Trace

| Issue | Confidence Check | Remediation Result | Decomposition Result | Final |
|---|---|---|---|---|
| FEAT-1716 | Proceed w/ Caution (83) | verify_scores_persisted → failed | Children found: FEAT-1718, FEAT-1719 | Decomposed (1) |
| FEAT-1718 | Not shown in history* | verify_scores_persisted → failed | No children (score below threshold) | Skipped |
| FEAT-1719 | Not shown in history* | verify_scores_persisted → failed | No children (score below threshold) | Skipped |
| FEAT-1717 | N/A (remediation skipped?) | N/A | Qualitative-skip: Very Large but knowledge-gap | Skipped |
| FEAT-1708 | Proceed (95) | verify_scores_persisted → failed | Medium (4/11), no decomposition | Skipped |
| FEAT-1709 | Proceed w/ Caution (83) | verify_scores_persisted → failed | Large (7/11), qualitative-skip | Skipped |
| FEAT-1710 | Proceed w/ Caution (80) | verify_scores_persisted → failed | Very Large (11/11), verification-only residual | Skipped |
| FEAT-1713 | Proceed w/ Caution (75) | verify_scores_persisted → failed | Medium (4/11), no decomposition | Skipped |

*FEAT-1718 and FEAT-1719 history entries aren't in the tail-200 window but were tracked via depth_map and visited files.

---

## Phase 1 — Fault Signals

### F1: `action_error` (×5) — `verify_scores_persisted`: `Path 'run_dir' not found in context`

- **Occurrences**: FEAT-1716, FEAT-1708, FEAT-1709, FEAT-1710, FEAT-1713
- **Mechanism**: The `with` block on `run_remediation` passes `run_dir: "${captured.run_dir.output}"` to the child loop context. However, `verify_scores_persisted` in the `_subloop` (inline FSM) references `${context.run_dir}` in its shell action — and the resolved FSM runner does not propagate `with` keys into the inline sub-loop's shell action environment.
- **Impact**: Every remediation fails immediately after the confidence check succeeds (exit 0 from `assess`). The confidence check runs correctly, scores are persisted to frontmatter, but the very next state crashes. This is the **single-point failure** responsible for 0/8 implementations.
- **Severity**: CRITICAL — blocks the loop's primary function.

### F2: `detect_children` semantic conflation (×5) — "no children" routes to sub-loop `failed` terminal

- **Occurrences**: FEAT-1708, FEAT-1709, FEAT-1710, FEAT-1717, FEAT-1713
- **Mechanism**: `detect_children` exits 1 to signal "no children found" — a valid and expected outcome (size review correctly determined no decomposition was needed). The state routes `on_no: "failed"` which is the terminal `failed` state in `rn-decompose`. The parent correctly recovers via `run_decomposition.on_no → skip_issue`, but the sub-loop's internal telemetry records these as failures.
- **Impact**: Misleading failure counts in sub-loop runs. No user-facing harm (parent recovers correctly), but degrades debugging signal.
- **Severity**: LOW — cosmetic telemetry defect.

### F3: `run_size_review` evaluator `partial` verdict → `terminated_by: error` (×1)

- **Occurrence**: FEAT-1713's `rn-decompose` iteration
- **Mechanism**: The default LLM evaluator returned `verdict: "partial"` (confidence 0.82) — it caught that the size review action accidentally staged pre-existing unrelated working-tree changes alongside the `size` frontmatter update. The sub-loop terminated with `terminated_by: "error"` because `partial` isn't a routable verdict — only `yes`/`no` paths exist in the FSM routing table.
- **Impact**: The parent recovered via `on_error → skip_issue`, but the evaluator's useful finding (staged unrelated changes) was discarded.
- **Severity**: MEDIUM — rare but exposes a routing gap; evaluator intelligence is lost.

---

## Rubric-vs-Description Audit

**Skipped** — no `evaluate.type: llm_structured` states exist in this loop. All evaluators are programmatic (`exit_code`, `output_numeric`, `output_contains`) or default LLM judges on slash-command actions. No rubric drift to detect.

---

## Sub-Loop Verdict Laundering Check

**2 sub-loop states checked, 0 flagged.**

| Parent State | Child Loop | `on_yes` | `on_no` | Laundering? |
|---|---|---|---|---|
| `run_remediation` | `rn-remediate` | `dequeue_next` | `run_decomposition` | No — routes differ |
| `run_decomposition` | `rn-decompose` | `dequeue_next` | `skip_issue` | No — routes differ |

Both parent states distinguish between child success (`on_yes`) and child failure (`on_no`), so sub-loop verdicts are preserved and acted upon.

---

## Improvement Proposals

### 1. [CRITICAL] [contract] Fix `verify_scores_persisted` context propagation

**Rationale**: The `with` block passes `run_dir` to the child loop, but `verify_scores_persisted` in `_subloop` references `${context.run_dir}` which fails to resolve. This is the single-point failure that caused 0/8 implementations. All 5 confidence checks succeeded (exit 0 from `assess`), but every one crashed on `verify_scores_persisted` before reaching `check_readiness` → `implement`.

**Two fix options**:

*Option A — Reference the captured value directly in `_subloop`* (quick fix):
```yaml
# In rn-implement loop definition, verify_scores_persisted state:
  verify_scores_persisted:
    action: |
      ID="${context.issue_id}"
-     RUN_DIR="${context.run_dir}"
+     RUN_DIR="${captured.run_dir.output}"
      ISSUE_FILE=$(find .issues -name "*-$ID-*" ! -path "*/completed/*" 2>/dev/null | head -1)
```

*Option B — Fix the FSM runner to propagate `with` keys into `_subloop` shell action environments* (correct fix, larger scope):
The `with` block on a parent state should make its keys available as `${context.<key>}` in all child states — including inline `_subloop` definitions. The current behavior suggests `with` values are only available during sub-loop spawn, not during sub-loop state execution.

### 2. [LOW] [state] Route `detect_children` "no children" as success, not failure

**Rationale**: Exit code 1 from `detect_children` means "no children found" — a valid and expected outcome (the size review correctly determined no decomposition was needed). Routing this to the sub-loop's terminal `failed` state produces misleading telemetry (5 "failed" sub-loops that actually succeeded at their job).

```yaml
# In rn-decompose _subloop, detect_children state:
  detect_children:
    action: |
      ...
      if [ -s "$RUN_DIR/children_${ID}.txt" ]; then
        ...
        exit 0
      else
        echo "No children found for $ID"
-       exit 1
+       exit 0
      fi
    evaluate:
      type: exit_code
-   on_yes: enqueue_children
-   on_no: failed
+   on_yes: route_children
+   on_no: failed
+   on_error: failed
+
+ route_children:
+   evaluate:
+     type: output_contains
+     pattern: "Found"
+     source: "${captured.detect_children.output}"
+   on_yes: enqueue_children
+   on_no: done        # "No children found" → success terminal
+   on_error: failed
```

### 3. [MEDIUM] [state] Handle `partial` evaluator verdict in `run_size_review`

**Rationale**: The default LLM evaluator can return `partial` (as it did for FEAT-1713, catching that the size review accidentally staged unrelated working-tree changes). The sub-loop has no routing for this verdict, causing `terminated_by: "error"`. This is a less frequent fault (1 occurrence in 5 sub-loop runs) but exposes a gap: useful evaluator findings are discarded because the FSM can't route a `partial` verdict.

**Fix**: Add an `on_partial` route or treat `partial` as `on_yes` with a warning logged:
```yaml
# In rn-decompose _subloop, run_size_review state:
  run_size_review:
    action: "/ll:issue-size-review ${context.issue_id} --auto"
    action_type: slash_command
    on_yes: detect_children
+   on_partial: detect_children   # Treat partial success as success for routing
    on_error: failed
```

*Note: This requires FSM runner support for `on_partial` routing. If not yet supported, the runner should at minimum treat `partial` as `yes` rather than error-terminating.*

---

## Raw Summary

```json
{
  "total_processed": 8,
  "implemented": 0,
  "decomposed": 1,
  "skipped": 8,
  "depth_capped": 0,
  "failed": 0
}
```

---

## Token Economics (from captured slash-command sessions)

| Sub-loop Run | Input Tokens | Output Tokens | Cache Read | Model |
|---|---|---|---|---|
| ll:issue-size-review FEAT-1717 | 67,234 | 2,323 | 132,480 | deepseek-v4-pro[1m] |
| ll:confidence-check FEAT-1708 | 86,383 | 10,936 | 975,488 | deepseek-v4-pro[1m] |
| ll:issue-size-review FEAT-1708 | 45,710 | 4,550 | 254,592 | deepseek-v4-pro[1m] |
| ll:confidence-check FEAT-1709 | 59,495 | 9,729 | 833,536 | deepseek-v4-pro[1m] |
| ll:issue-size-review FEAT-1709 | 41,014 | 2,919 | 76,672 | deepseek-v4-pro[1m] |
| ll:confidence-check FEAT-1710 | 62,007 | 10,571 | 627,712 | deepseek-v4-pro[1m] |
| ll:issue-size-review FEAT-1710 | 44,648 | 4,399 | 76,928 | deepseek-v4-pro[1m] |
| ll:confidence-check FEAT-1713 | 72,035 | 12,546 | 995,584 | deepseek-v4-pro[1m] |
| ll:issue-size-review FEAT-1713 | 41,928 | 2,911 | 237,568 | deepseek-v4-pro[1m] |

Heavy cache utilization kept per-invocation costs moderate, but the broken remediation path means all confidence-check tokens were effectively wasted — the loop assessed readiness correctly but couldn't act on the assessments.

---

*Audit generated 2026-06-06 via `/ll:audit-loop-run rn-implement`*
