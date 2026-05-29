---
captured_at: "2026-05-29T01:01:55Z"
discovered_date: 2026-05-28
discovered_by: capture-issue
relates_to: [ENH-1774, ENH-1775, ENH-1776, ENH-1777]
---

# EPIC-1773: Audit & Simplify Built-in FSM Loops with Shared Fragments, Sub-loops, and Flows

## Summary

The project has 57 built-in FSM loops with only 5 shared lib fragments and 1 oracle sub-loop. Many loops duplicate state patterns inline rather than composing from shared building blocks. This epic covers three categories of improvement: (1) extracting sub-loops from duplicated inline patterns, (2) creating shared state fragments in `loops/lib/` for repeated task patterns, and (3) defining named flows for sequential task chains used across multiple loops.

## Motivation

Reducing duplication across 57 loops directly reduces maintenance burden, makes loop behavior more consistent (one fix propagates everywhere), and lowers the barrier to creating new loops. The audit identifies ~11 discrete improvements spanning shared CLI fragments, harness evaluators, integration patterns, and queue management. Each extracted fragment or sub-loop eliminates 3-6 copies of the same logic.

## Goal

Eliminate duplicated state patterns across built-in FSM loops by extracting shared fragments, sub-loops, and flows. When complete, the 57 loops should compose from a richer shared library rather than inlining repeated patterns.

## Scope

**In scope:**
- Adding shared lib fragments: `ll_commit`, `playwright_screenshot`, `convergence_gate`, `diff_stall_gate`, `parse_tagged_json`, `ll_rubric_score`, queue management (`queue_pop`, `queue_track`)
- Extracting sub-loops: `generator-evaluator`, `enumerate-and-prove`, `implement-issue-chain`
- Defining flows: gen-eval-flow, enumerate-prove-flow, research-coverage-flow, issue-triage-flow, quality-gate-flow
- Converting existing loops to use new shared components
- Running `ll-loop validate` on all modified loops
- Running the test suite after each wave

**Out of scope:**
- New loop creation (this is refactoring only)
- Loop deletion or renaming
- Changing loop behavior or semantics
- Modifying the FSM runner/engine itself

## Children

- **ENH-1774** — Wave 1: Add `ll_commit` and `playwright_screenshot` shared fragments
- **ENH-1775** — Wave 2: Extract `generator-evaluator` sub-loop and add `parse_tagged_json` fragment
- **ENH-1776** — Wave 3: Add `convergence_gate`, `ll_rubric_score` fragments and extract `enumerate-prove-flow`
- **ENH-1777** — Wave 4: Remaining fragments, sub-loops, and flows

## Integration Map

### Files to Modify
- `loops/*.yaml` — 10-15 existing loops converted to use new fragments/sub-loops
- `loops/lib/cli.yaml` — add `ll_commit` fragment
- `loops/lib/harness.yaml` — new file with `playwright_screenshot` fragment
- `loops/lib/common.yaml` — add `convergence_gate`, `diff_stall_gate`, `parse_tagged_json`, `queue_pop`, `queue_track` fragments
- `loops/oracles/generator-evaluator.yaml` — new sub-loop
- `loops/oracles/enumerate-and-prove.yaml` — new sub-loop
- `loops/oracles/implement-issue-chain.yaml` — new sub-loop

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop_cmd.py` — `ll-loop validate` CLI
- `scripts/little_loops/loop_runner.py` — FSM runner (no changes expected, but validate)

### Tests
- `scripts/tests/` — regression suite; may need fragment/sub-loop tests

### Documentation
- `docs/ARCHITECTURE.md` — update loop architecture section if fragment/sub-loop composition patterns change

## Success Metrics

- All 11 planned improvements implemented across 4 waves
- At least 2 existing loops converted per new fragment (verification requirement)
- All modified loops pass `ll-loop validate`
- `python -m pytest scripts/tests/ -v --tb=short` passes with no regressions
- No loop exceeds its existing iteration/timeout budget after refactoring

## Impact

- **Priority**: P2 — Important strategic cleanup; reduces maintenance burden and inconsistency risk
- **Effort**: Large — 11 discrete items across 4 waves, each requiring fragment creation, loop conversion, validation, and test verification
- **Risk**: Medium — Behavioral regressions possible if fragment semantics don't exactly match inlined originals; mitigated by requiring `ll-loop validate` + test suite pass per wave
- **Breaking Change**: No — existing loops continue to function; fragments are additive

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| architecture | docs/ARCHITECTURE.md | Loop system design and FSM architecture |
| guidelines | .claude/CLAUDE.md | Loop authoring conventions and meta-loop design rules |

## Labels

`epic`, `captured`

## Session Log
- `/ll:capture-issue` - 2026-05-29T01:01:55Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/17b05161-9ff0-48f9-baaf-69470f937b48.jsonl`

---

## Status

**Open** | Created: 2026-05-28 | Priority: P2
