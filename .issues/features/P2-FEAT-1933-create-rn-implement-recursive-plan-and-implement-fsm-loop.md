---
id: FEAT-1933
title: Create rn-implement recursive plan-and-implement FSM loop
type: FEAT
priority: P2
status: open
captured_at: "2026-06-04T05:36:57Z"
discovered_date: 2026-06-04
discovered_by: capture-issue
labels: [loops, fsm, orchestration, recursion, planning]
---

# FEAT-1933: Create rn-implement recursive plan-and-implement FSM loop

## Summary

Create a new built-in FSM loop (`loops/rn-implement.yaml`) that combines the best patterns
from `recursive-refine` (depth tracking, cycle detection, decomposition trees), `rn-refine`
(iterative deepening, dimensional analysis, convergence detection), and `autodev` (interleaved
implementation, inflight tracking, run isolation) into a single n-depth recursive
planning-and-implementation FSM.

The loop addresses four gaps in the existing `autodev` loop:

1. **No iterative deepening** — single-pass refine→wire→confidence-check, decomposition as the only fallback
2. **No dimensional reactivity** — confidence-check produces per-dimension scores (Complexity, Ambiguity,
   Test Coverage, Change Surface, all 0–25) but only binary flags are read
3. **No multi-pass wire↔refine feedback** — wire runs once, no loop where wiring reveals gaps needing refinement
4. **Decision may never get resolved** — edge cases where `decision_needed` surfaces but routing misses it,
   or decide runs but the issue isn't re-refined with the selected option

## Current Behavior

The `autodev` loop is structurally recursive (decomposes issues into children, re-queues depth-first)
but operationally linear — each issue gets exactly one pass through `refine → wire → confidence-check`,
with decomposition as the only fallback when thresholds aren't met. The dimensional scores from
confidence-check are unused for routing decisions.

## Expected Behavior

A 25-state FSM loop (22 active + 2 terminal + 1 diagnostic) with:

- **Iterative deepening**: `diagnose → remediate → re_assess → check_convergence` loop that re-enters
  the remediation cycle until PASS, budget exhaustion, or STALLED
- **Dimensional diagnosis**: Token-based routing (IMPLEMENT/DECIDE/WIRE/REFINE/DECOMPOSE) driven by
  readiness, outcome, complexity, ambiguity, and change_surface scores
- **Multi-pass wire↔refine**: Wire always chains into refine, which chains into re_assess, creating
  a closed feedback loop
- **Convergence check**: PASS/IMPROVED/STALLED routing with remediation budget gating
- **Depth-bounded recursion**: `max_depth` cap (default 3), depth-first child enqueuing, cycle detection
- **Run isolation**: All temp files under `${context.run_dir}/` (MR-3 compliant)
- **Non-LLM gates**: `check_convergence` and `check_remediation_budget` use shell/output_numeric evaluators
  paired with LLM semantic checks (MR-1 compliant)

## Motivation

Single-pass refinement often leaves issues under-specified, and the existing confidence-check
dimensional scores are underutilized — the autodev loop reads only `decision_needed` and
`missing_artifacts` binary flags as proxies. By combining proven patterns from three existing
loops, `rn-implement` provides a measurable quality improvement over `autodev` for complex
issues that need multiple refinement passes, and gives the FSM access to the full dimensional
signal that confidence-check already produces.

This loop also serves as a reference architecture for meta-loops that need iterative deepening
with dimensional routing — a pattern that can be extracted into shared fragments later
(EPIC-1773 scope).

## Proposed Solution

Follow the detailed plan at `~/.claude/plans/yes-plan-as-a-elegant-thacker.md`. Key design
decisions:

**State machine** (25 states):

```
init → dequeue_next → assess → diagnose
  ├─ IMPLEMENT → implement → dequeue_next
  ├─ DECIDE → decide → re_assess
  ├─ WIRE → wire → refine → re_assess
  ├─ REFINE → refine → re_assess
  └─ DECOMPOSE → snap_for_size_review → run_size_review → detect_children
       ├─ [children] → enqueue_children → dequeue_next
       └─ [none] → skip_issue → dequeue_next

re_assess → check_convergence
  ├─ PASS → implement → dequeue_next
  ├─ IMPROVED → check_remediation_budget
  │    ├─ [under budget] → diagnose
  │    └─ [exhausted] → snap_for_size_review
  └─ STALLED → snap_for_size_review
```

**Dimensional diagnosis** (state 4): Reads scores from `ll-issues show --json`, applies
thresholds from `.ll/ll-config.json` (readiness_threshold, outcome_threshold), outputs
a routing token.

**Convergence check** (state 14): Shell script compares pre/post scores, increments
remediation counter, outputs PASS/IMPROVED/STALLED. Non-LLM `output_contains` evaluator.

**Edge case handling**: Empty input → failed; empty queue → done; max depth reached →
skip as depth-capped; all remediation exhausted → try decomposition; diagnose outputs
no token → fallthrough to decomposition; rate limit exhausted → advance queue.

## Use Case

**Who**: A developer or CI automation running `ll-loop run rn-implement "EPIC-1811"`
to process a complex epic with issues that need multi-pass refinement before they're
ready to implement.

**Context**: The developer has a set of issues that `autodev` keeps skipping or
decomposing because confidence-check scores are below threshold. Single-pass refinement
isn't enough — these issues need iterative deepening.

**Goal**: Run `rn-implement` which diagnoses each issue dimensionally, applies targeted
remediation (refine, wire, decide), re-assesses, and converges only when scores cross
thresholds — implementing immediately when ready, decomposing only when remediation
is exhausted.

**Outcome**: More issues reach IMPLEMENT-ready state without unnecessary decomposition,
and those that truly need decomposition are correctly identified after systematic
remediation attempts.

## Acceptance Criteria

- [ ] `loops/rn-implement.yaml` passes `ll-loop validate` (MR-1 and MR-3 clean)
- [ ] All 25 states have correct routing (verified by `TestRoutingStructure`)
- [ ] `diagnose` state correctly outputs all 5 tokens for their respective score combinations
- [ ] `check_convergence` correctly outputs PASS/IMPROVED/STALLED for score delta scenarios
- [ ] `check_remediation_budget` gates at `max_remediation_passes` (default 3)
- [ ] Depth tracking: child depth = parent+1, max_depth cap enforced
- [ ] Cycle detection: visited set prevents re-processing
- [ ] All temp files written under `${context.run_dir}/` (MR-3)
- [ ] `test_rn_implement.py` passes with ≥90% coverage on loop-specific logic
- [ ] `test_builtin_loops.py` parametrized sweep passes with `rn-implement` registered
- [ ] Dry run `ll-loop run rn-implement "FEAT-9999"` loads FSM and executes init state
- [ ] Full test suite passes with no regressions

## API/Interface

```yaml
# Loop invocation
ll-loop run rn-implement "<issue-id-or-epic-id>"

# Context variables injected by runner
context.run_dir          # .loops/runs/rn-implement-<timestamp>/
context.issue_id         # Seed issue ID(s)
context.max_depth        # From ll-config.json → commands.recursive_refine.max_depth (default 3)
context.max_remediation_passes  # Loop parameter (default 3)

# Config reads
# commands.confidence_gate.readiness_threshold (default 85)
# commands.confidence_gate.outcome_threshold (default 75)
```

State actions call existing skills/shell commands:
- `/ll:confidence-check <id>` (assess, re_assess)
- `/ll:decide-issue <id> --auto` (decide)
- `/ll:wire-issue <id> --auto` (wire)
- `/ll:refine-issue <id> --auto --full-rewrite` (refine)
- `/ll:issue-size-review <id> --auto` (run_size_review)
- `ll-auto --only <id>` (implement)

## Integration Map

### Files to Modify
- **CREATE** `scripts/little_loops/loops/rn-implement.yaml` — ~500 lines, imports `lib/common.yaml`
- **CREATE** `scripts/tests/test_rn_implement.py` — ~600 lines, 11 test classes
- **EDIT** `scripts/tests/test_builtin_loops.py` — add `rn-implement` to expected set (~line 72)
- **EDIT** `docs/guides/LOOPS_GUIDE.md` — add row to Planning table, full section after autodev

### Dependent Files (Callers/Importers)
- N/A (new loop, no existing callers)

### Similar Patterns
- `scripts/little_loops/loops/recursive-refine.yaml` — depth tracking, decomposition tree pattern
- `scripts/little_loops/loops/rn-refine.yaml` — iterative deepening, convergence check pattern
- `scripts/little_loops/loops/autodev.yaml` — inflight tracking, `ll-auto --only` integration
- `scripts/little_loops/loops/lib/common.yaml` — shared fragments (queue_pop, queue_track, with_rate_limit_handling)

### Tests
- **CREATE** `scripts/tests/test_rn_implement.py` — 11 test classes covering all states, routing, and edge cases
- **EDIT** `scripts/tests/test_builtin_loops.py` — register in `test_expected_loops_exist`

### Documentation
- **EDIT** `docs/guides/LOOPS_GUIDE.md` — add rn-implement entry

### Configuration
- Reads existing config keys: `commands.confidence_gate.readiness_threshold`, `commands.confidence_gate.outcome_threshold`, `commands.recursive_refine.max_depth`
- No new config keys required

## Implementation Steps

1. Author `scripts/little_loops/loops/rn-implement.yaml` with all 25 states, importing shared fragments from `lib/common.yaml`, following conventions from `autodev.yaml` and `recursive-refine.yaml`
2. Author `scripts/tests/test_rn_implement.py` with 11 test classes covering init, dequeue, diagnose logic, convergence check, router chain, depth tracking, remediation budget, child enqueuing, visited set filtering, done summary, and routing structure
3. Register `rn-implement` in `test_builtin_loops.py` expected set and update `docs/guides/LOOPS_GUIDE.md`
4. Validate: `ll-loop validate rn-implement` (MR-1 and MR-3 clean)
5. Run unit tests: `python -m pytest scripts/tests/test_rn_implement.py scripts/tests/test_builtin_loops.py -v`
6. Dry-run against non-existent issue to confirm FSM loads and init executes
7. Run full test suite to confirm no regressions

## Impact

- **Priority**: P2 — Significant new capability filling a proven gap in the loop catalog; the four gaps are well-documented from extensive use of autodev
- **Effort**: Large — ~1,100 lines of new code across YAML and test files, plus docs; however, it composes proven patterns from three existing loops rather than inventing new primitives
- **Risk**: Medium — New loop, no existing callers to break; risk is in getting the routing logic correct (25 states with dimensional token routing). Mitigated by comprehensive test coverage and dry-run validation
- **Breaking Change**: No — entirely new artifact, no existing APIs modified

## Related Key Documentation

| Document | Relevance | Key Topics |
|---|---|---|
| `docs/ARCHITECTURE.md` | HIGH — Covers loop system design and FSM architecture | Loop catalog structure, FSM execution model, built-in loop conventions |
| `.claude/CLAUDE.md` § Loop Authoring | HIGH — Meta-loop rules govern this implementation | MR-1 (non-LLM evaluator pairing), MR-3 (run_dir isolation), meta-loop design patterns |
| `docs/reference/API.md` | MEDIUM — Loop infrastructure and CLI reference | `ll-loop` CLI, FSM schema, evaluator types, context variable injection |

## Labels

`loops`, `fsm`, `orchestration`, `recursion`, `planning`

## Session Log
- `/ll:capture-issue` - 2026-06-04T05:36:57Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0e0ae204-dee8-4424-b3cd-529179a61766.jsonl`

---

## Status

**Open** | Created: 2026-06-04 | Priority: P2
