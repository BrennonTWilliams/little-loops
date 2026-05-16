---
id: ENH-736
type: ENH
priority: P3
status: completed
discovered_date: 2026-03-13
discovered_by: manual
confidence_score: 100
outcome_confidence: 100
---

# ENH-736: Replace `issue-throughput-monitor` with `backlog-flow-optimizer` loop

## Summary

`loops/issue-throughput-monitor.yaml` was a one-shot report disguised as a loop: `max_iterations: 1`, no conditional branching, no actions taken, no way to cycle back. It duplicated what `/ll:analyze-history` already does via a skill. It was replaced with a genuine FSM loop, `backlog-flow-optimizer`, that measures backlog health, diagnoses the primary bottleneck, takes targeted action, commits, and loops back until the backlog is healthy.

## Problem

`issue-throughput-monitor` violated the FSM loop contract:
- `max_iterations: 1` — not iterative by design
- All states executed unconditionally (no routing, no branching)
- Final state was `suggest_improvements` with no action taken — just text output
- Identical in output to running `/ll:analyze-history` manually

## Solution

Created `loops/backlog-flow-optimizer.yaml` with a real FSM cycle:

```
measure (shell)
  └─► diagnose (prompt)
        └─► route_bloat ─── BLOAT ──► close_dead_weight ──► commit ──► measure
                └─ else ─► route_size ── SIZE ──► fix_oversized ────────► commit ──► measure
                              └─ else ─► route_priority ── PRIORITY ──► promote_quick_wins ► commit ──► measure
                                            └─ else ─► done
```

### Design Decisions

- **Routing via `output_contains` chain** — proven pattern from `issue-refinement.yaml`; deterministic, no LLM judge needed for routing
- **3 bottleneck types** — BLOAT, SIZE, PRIORITY cover independent root causes; HEALTHY is the termination condition
- **Delegates to existing skills** — `/ll:tradeoff-review-issues --auto`, `/ll:issue-size-review`, `/ll:normalize-issues`, `/ll:commit`
- **`max_iterations: 15`** — ~5 cycles per bottleneck type; enough to drain a bloated backlog
- **`timeout: 7200`** — 15 × ~8 min/cycle (measure + diagnose + act + commit)
- **`ll-history summary` in measure** — provides real velocity data alongside count metrics

## Files Changed

- **Created**: `loops/backlog-flow-optimizer.yaml`
- **Deleted**: `loops/issue-throughput-monitor.yaml`
- **Updated**: `scripts/tests/test_builtin_loops.py` — swapped `issue-throughput-monitor` → `backlog-flow-optimizer` in the expected loop set

## Verification

```
ll-loop validate loops/backlog-flow-optimizer.yaml
# → valid; 10 states: measure, diagnose, route_bloat, route_size, route_priority,
#            close_dead_weight, fix_oversized, promote_quick_wins, commit, done

python -m pytest scripts/tests/test_builtin_loops.py -v
# → 11 passed
```

## Impact

- **Priority**: P3 — Removes a misleading built-in loop that set wrong expectations about FSM behavior
- **Effort**: Small — New YAML file + test update; no Python changes
- **Risk**: Low — Additive replacement; no runtime code modified
- **Breaking Change**: No (loop name changed, but no automation references `issue-throughput-monitor` by name)

## Labels

`enhancement`, `loops`, `fsm`, `backlog`

---

**Completed** | 2026-03-13 | Priority: P3

## Resolution

- Designed FSM state graph modeled after `issue-refinement.yaml` (routing chain) and `priority-rebalance.yaml` (measure → act → commit → loop)
- Created `loops/backlog-flow-optimizer.yaml` with 10 states, `max_iterations: 15`, `timeout: 7200`
- Removed `loops/issue-throughput-monitor.yaml` via `git rm`
- Updated expected loop set in `scripts/tests/test_builtin_loops.py`
- All 11 builtin loop tests pass

## Session Log
- Manual session - 2026-03-13 - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3df021b3-32a6-4be6-a43e-73862b6684c6.jsonl`
