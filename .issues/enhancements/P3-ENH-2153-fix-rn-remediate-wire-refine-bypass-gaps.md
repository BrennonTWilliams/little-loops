---
id: ENH-2153
type: ENH
priority: P3
status: done
title: Fix rn-remediate wire/refine bypass gaps in fast-path and diagnose routing
captured_at: '2026-06-14T23:10:29Z'
completed_at: '2026-06-14T23:10:29Z'
discovered_date: '2026-06-14'
discovered_by: capture-issue
---

# ENH-2153: Fix rn-remediate wire/refine bypass gaps in fast-path and diagnose routing

## Summary

`rn-remediate` had three paths where `/ll:refine-issue` and `/ll:wire-issue` were silently bypassed: (1) the `check_readiness` fast-path routed directly to `implement` even for high-complexity issues with an unmapped change surface; (2) the `check_outcome → refine` path skipped wire entirely when `score_change_surface == 0`; (3) the `diagnose` routing table lacked a WIRE branch for the case where complexity is high but the integration map is absent. All three gaps are now closed.

## Problem

Three code paths in `scripts/little_loops/loops/rn-remediate.yaml` bypassed quality-preparation steps:

**Gap 1 — `check_readiness` fast-path**
When both `confidence_score >= readiness_threshold` and `outcome_confidence >= outcome_threshold`, the loop routed directly to `implement` without checking whether the issue had high complexity (warranting a refine pass) or an unmapped change surface (`score_change_surface == 0`, warranting wire). An issue with manually-set or stale scores would skip all preparation.

**Gap 2 — `check_outcome → refine` path**
When `check_readiness` failed the joint gate but `check_outcome` passed (outcome OK, confidence low), the loop went straight to `refine`. Wire was never considered, even when `score_change_surface == 0` meaning no integration map existed.

**Gap 3 — `diagnose` missing WIRE branch for complexity + no surface**
The priority-ordered routing in `diagnose` handled `COMPLEXITY >= threshold AND CHANGE_SURFACE == 0` as REFINE (falling into the generic complexity branch). Wiring should precede refining when the integration map is absent.

## Fix

**Three targeted changes to `rn-remediate.yaml`:**

### Change 1 — `diagnose` routing (bash action, no new states)

Added a WIRE branch between the existing ambiguity-WIRE branches and the complexity-REFINE branch:

```bash
elif [ "$COMPLEXITY" -ge "${context.diagnose_complexity_threshold}" ] \
    && [ "$CHANGE_SURFACE" -eq 0 ]; then
  # High complexity + no integration map → wire before refining
  echo "WIRE"
```

Priority order after fix:
1. IMPLEMENT (both thresholds met)
2. DECIDE (decision_needed)
3. WIRE (missing_artifacts)
4. WIRE (ambiguity high + no surface map)
5. WIRE (complexity high + no surface map) ← new
6. REFINE (ambiguity high + surface exists)
7. REFINE (complexity high OR confidence low)
8. DECOMPOSE (change_surface high)
9. REFINE (fallthrough)

### Change 2 — Two new states after `check_readiness`

`check_readiness on_yes` changed from `implement` to `check_complexity_pre_implement`.

```yaml
check_complexity_pre_implement:
  fragment: shell_exit
  action: |
    PRE="${context.run_dir}/pre_scores_${context.issue_id}.json"
    COMPLEXITY=$(jq -r '.score_complexity // 0' "$PRE" 2>/dev/null || echo 0)
    THRESHOLD="${context.diagnose_complexity_threshold}"
    [ "$COMPLEXITY" -ge "$THRESHOLD" ] && exit 0 || exit 1
  on_yes: refine
  on_no: check_wire_pre_implement
  on_error: check_wire_pre_implement

check_wire_pre_implement:
  fragment: shell_exit
  action: |
    PRE="${context.run_dir}/pre_scores_${context.issue_id}.json"
    CHANGE_SURFACE=$(jq -r '.score_change_surface // 0' "$PRE" 2>/dev/null || echo 0)
    [ "$CHANGE_SURFACE" -eq 0 ] && exit 0 || exit 1
  on_yes: wire
  on_no: implement
  on_error: implement
```

Both states read `pre_scores_<ID>.json` already written by `verify_scores_persisted` — no extra `ll-issues show` call.

### Change 3 — New state after `check_outcome`

`check_outcome on_yes` changed from `refine` to `check_wire_needed_outcome`.

```yaml
check_wire_needed_outcome:
  fragment: shell_exit
  action: |
    PRE="${context.run_dir}/pre_scores_${context.issue_id}.json"
    CHANGE_SURFACE=$(jq -r '.score_change_surface // 0' "$PRE" 2>/dev/null || echo 0)
    [ "$CHANGE_SURFACE" -eq 0 ] && exit 0 || exit 1
  on_yes: wire
  on_no: refine
  on_error: refine
```

## Key Research Finding

`score_change_surface` is set by `/ll:confidence-check`, **not** `/ll:wire-issue`. Score 0–25 (0 = many callers or unbounded sweep; 25 = few callers, fully bounded). The `// 0` default in jq means `CHANGE_SURFACE == 0` covers both "field absent (confidence-check never run)" and "scored 0 (unbounded surface)" — both warrant wire. This is consistent with the existing `diagnose` branch that already used `CHANGE_SURFACE == 0` as a proxy for "no integration map."

## Verification

- `ll-loop validate rn-remediate` passes clean with 33 states listed.
- Five routing scenarios desk-checked against the updated YAML:
  - confidence=90, outcome=80, complexity=20, CHANGE_SURFACE=0 → `check_complexity_pre_implement` on_yes → `refine` (not direct implement)
  - confidence=90, outcome=80, complexity=5, CHANGE_SURFACE=0 → `check_complexity_pre_implement` on_no → `check_wire_pre_implement` on_yes → `wire`
  - confidence=90, outcome=80, complexity=5, CHANGE_SURFACE=15 → both gates on_no → `implement`
  - outcome=80, confidence=60, CHANGE_SURFACE=0 → `check_wire_needed_outcome` on_yes → `wire`
  - outcome=80, confidence=60, CHANGE_SURFACE=15 → `check_wire_needed_outcome` on_no → `refine`

## Files Changed

- `scripts/little_loops/loops/rn-remediate.yaml` — three edits; net +38 lines

## Session Log
- `hook:posttooluse-status-done` - 2026-06-14T23:11:44 - `01585c46-1423-4b3a-aea6-01a2b3b1a449.jsonl`
- `/ll:capture-issue` - 2026-06-14T23:10:29Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/01585c46-1423-4b3a-aea6-01a2b3b1a449.jsonl`
