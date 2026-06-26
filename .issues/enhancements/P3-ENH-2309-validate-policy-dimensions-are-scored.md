---
id: ENH-2309
title: ll-loop validate rule — flag policy_rules dimensions that are never scored
type: ENH
priority: P3
status: open
discovered_date: 2026-06-26
discovered_by: capture-issue
relates_to:
- FEAT-2301
- ENH-2164
- ENH-2154
---

# ENH-2309: ll-loop validate rule — flag policy_rules dimensions that are never scored

## Summary

Add a `ll-loop validate` rule that flags any dimension referenced in a
`context.policy_rules` predicate that is **never scored** — i.e. it is neither
listed in `context.rubric_dimensions` nor written by a shell scorer to
`rubric-dim-<name>.txt`. Such a predicate is silently inert at runtime: the
dimension never reaches the scores dict, so `_eval_predicate` matches only `!=`
and the rule falls through to the catch-all. WARNING severity.

## Motivation

The policy-router decision table has a silent-failure class that the current gate
does not catch. A predicate like `has_citations:==true` (or any predicate on a
dimension that nothing scores) passes `ll-loop validate` today because:

- The grammar accepts it — `==` is in `_ALL_OPS` and takes any value
  (`fsm/policy_rules.py:28`).
- The route map can be complete — every action token maps to a state.

…but at runtime the dimension is missing from the scores dict, so
`_eval_predicate` (`fsm/policy_rules.py:188-195`) returns `True` only for `!=`.
A `==`/`>=`/`<=`/`<`/`>` predicate on that dimension can **never match**; the
row is dead and routing silently falls through to `* -> …`. If every rule's
predicates reference unscored dimensions, every run hits the catch-all and the
whole table is inert — with a green validate.

This surfaced via FEAT-2301 (the HTML builder), whose boolean-dimension affordance
generated exactly this dead-predicate shape. FEAT-2301 fixes its own output
(booleans compile to a scored numeric 0/100 encoding), but the gap is general:
a **hand-authored** loop, or `ll-loop edit-routes` output, can reintroduce the
same silent-inert predicate. The gate, not the builder, is the authoritative place
to catch it — the builder's in-browser validation is UX only and can drift.

This is the same "shift the gate left" philosophy as the MR-1…MR-6 meta-loop rules
already in `fsm/validation.py`.

## Current Behavior

`validate_fsm()` runs ~20 validators (`fsm/validation.py:956-1094`). None of them
parse `context.policy_rules` and cross-check the referenced dimensions against the
set of dimensions that are actually scored. A loop whose entire decision table
references unscored dimensions validates clean.

## Expected Behavior

A new validator (`_validate_policy_dimensions_scored`) that, for any loop defining
`context.policy_rules`:

1. Parses the rule table with `fsm/policy_rules.parse_rules()` and collects the set
   of referenced dimension names across all predicates (excluding the reserved
   `aggregate` pseudo-dimension, which is always written by `policy_parse_scores`).
2. Collects the set of **scored** dimensions from:
   - `context.rubric_dimensions` (pipe-separated names, normalized lowercased +
     spaces→hyphens to match the `rubric-dim-<name>.txt` convention written by
     `policy_parse_scores`, `lib/policy-router.yaml:97`), AND
   - any dimension a shell state demonstrably writes — i.e. a `rubric-dim-<name>.txt`
     literal appearing in a `shell` action body (covers the deterministic-scorer
     path, e.g. rn-remediate's `ll-issues show --json` scorer).
3. Emits a **WARNING** for each referenced dimension that is in neither set, naming
   the dimension and the predicate(s) that reference it, with a hint: *"dimension
   `<name>` is referenced in policy_rules but never scored (not in rubric_dimensions
   and no shell state writes rubric-dim-<name>.txt) — the predicate is inert at
   runtime and routing will fall through to the catch-all."*

Suppression: a top-level `policy_dims_scored_ok: true` flag suppresses the check,
mirroring the `*_ok` escape hatches used by MR-1…MR-6.

WARNING (not ERROR) because the shell-scorer detection is necessarily heuristic —
a scorer could compute the dim name dynamically — and we must not block a
legitimate loop on a false positive. (Decided 2026-06-26.)

## Acceptance Criteria

- [ ] A loop with `context.policy_rules` referencing a dimension absent from both
  `rubric_dimensions` and any `rubric-dim-<name>.txt` shell write produces a WARNING
  naming the dimension and the offending predicate(s)
- [ ] The reserved `aggregate` dimension never triggers the warning (it is always
  written by `policy_parse_scores`)
- [ ] A dimension listed in `rubric_dimensions` (after lowercase + spaces→hyphens
  normalization) does NOT trigger the warning
- [ ] A dimension written via a `rubric-dim-<name>.txt` literal in a shell action
  body does NOT trigger the warning (deterministic-scorer path, e.g. rn-remediate)
- [ ] `policy_dims_scored_ok: true` at loop top-level suppresses the check
- [ ] Severity is WARNING; the loop still validates (exit 0 for warnings-only)
- [ ] A malformed/empty `policy_rules` does not crash the validator (it defers to the
  existing grammar validation)
- [ ] `policy-refine.yaml` and `rubric-refine.yaml` (existing canonical loops) pass
  the new check with no new warnings

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/validation.py` — add `_validate_policy_dimensions_scored(fsm)`
  and register it in `validate_fsm()` alongside the existing `errors.extend(...)`
  block (~line 1083, near `_validate_classify_route_default`). Reuse
  `fsm/policy_rules.parse_rules()` for parsing — do NOT re-implement the grammar.

### Dependent Files
- `scripts/little_loops/fsm/policy_rules.py` — `parse_rules()` / `Predicate.dim`
  provide the referenced-dimension set (no change)
- `scripts/little_loops/loops/lib/policy-router.yaml` — `rubric-dim-<name>.txt`
  naming convention the normalization must match (no change)

### Tests
- `scripts/tests/test_fsm_validation.py` (or the file housing the MR-rule tests) —
  cover: unscored dim → warning; scored-via-rubric_dimensions → clean;
  scored-via-shell-write → clean; `aggregate` exempt; suppression flag;
  malformed table no-crash; canonical loops clean.

### Documentation
- `.claude/CLAUDE.md` "Loop Authoring" section — document the new rule alongside
  MR-1…MR-6 (it is a policy-table analogue, not a meta-loop rule; place accordingly).
- `docs/guides/POLICY_ROUTER_GUIDE.md` — note that referenced dimensions must be
  scored, and the `policy_dims_scored_ok` escape hatch.

## Impact

- **Priority**: P3 — correctness/authoring-safety guard; no current loop is known to
  trip it, but it closes a silent-failure class for hand-authored and edit-routes
  output.
- **Effort**: Small — one validator function (~40 lines) + tests + two doc notes.
  Reuses existing `parse_rules`.
- **Risk**: Low — WARNING-only, additive, with a suppression flag. Main risk is
  false positives on dynamically-named shell scorers, mitigated by warn-not-error.
- **Breaking Change**: No

## Labels

`enhancement`, `loops`, `policy-router`, `validation`, `tooling`

## Status

**Open** | Created: 2026-06-26 | Priority: P3
