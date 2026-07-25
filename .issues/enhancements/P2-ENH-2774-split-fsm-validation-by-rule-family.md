---
id: ENH-2774
status: open
priority: P2
discovered_commit: fb5673902939bbf5a17bc7afe61317982d40bfd2
discovered_branch: main
discovered_date: 2026-07-24T22:31:26Z
discovered_by: audit-architecture
focus_area: large-files
labels: [enhancement, architecture, refactoring, auto-generated]
parent: EPIC-2789
---

# ENH-2774: Split fsm/validation.py by rule family

## Summary

Architectural issue found by `/ll:audit-architecture`. All loop-validation
lint rules — MR-1 through MR-11 plus the specialty gates (policy-table,
static-loop-ref, haiku-gen, capture-reachability, session-mode-eval) — live in
one 3,126-line module.

## Location

- **File**: `scripts/little_loops/fsm/validation.py`
- **Line(s)**: 1-3126 (entire file)
- **Module**: `little_loops.fsm.validation`

## Finding

### Current State

- 3,126 lines, 59 top-level defs/classes.
- Second-largest file in the codebase.
- Each new lint rule (the table in `.claude/CLAUDE.md` § Loop Authoring keeps
  growing) is appended to the same file; rules with unrelated concerns
  (evaluator pairing, shell-escape safety, capture dominance analysis,
  session-mode checks) share one namespace.

### Impact

- **Development velocity**: adding a rule means navigating a 3k-line file;
  rule-local helpers are hard to distinguish from shared infrastructure.
- **Maintainability**: no structural boundary matches the documented rule
  taxonomy, so the docs and code drift apart.
- **Risk**: medium — cross-rule helper reuse is untracked; a tweak for one rule
  can shift another's behavior.

## Proposed Solution

Convert to a `fsm/validation/` package split by rule family, with a thin
aggregator preserving the current public API (`ll-loop validate` entry points
and suppress-flag registry).

### Suggested Approach

1. Create `fsm/validation/` with modules along the existing families, e.g.
   `meta_rules.py` (MR-1..MR-6), `shell_safety.py` (MR-7, MR-9, MR-11),
   `evaluator_rules.py` (MR-8, MR-10, session-mode-eval, haiku-gen),
   `reachability.py` (capture-reachability, static loop refs, policy-table).
2. Keep shared context (loaded loop model, suppress-flag handling) in a
   `_base.py`; re-export everything from `__init__.py` so importers (including
   `cli/loop/_helpers`) are unchanged.
3. Run the full suite plus `ll-loop validate` against the bundled loops to
   confirm identical findings before/after.

## Impact Assessment

- **Severity**: High
- **Effort**: Medium
- **Risk**: Medium
- **Breaking Change**: No

---

## Status

**Open** | Created: 2026-07-24 | Priority: P2
