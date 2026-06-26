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
   of referenced dimension names across all predicates **as raw `Predicate.dim`
   strings — do NOT normalize them** (excluding the reserved `aggregate`
   pseudo-dimension, which is always written by `policy_parse_scores`).

   > **Asymmetry is intentional (do not "fix" it).** The referenced set stays raw
   > while the scored set (step 2) is normalized. This is deliberate: at runtime
   > `evaluate_rules` matches the raw `Predicate.dim` by exact string against score
   > keys that `policy_parse_scores` wrote in normalized form (lowercase,
   > spaces→hyphens). So a predicate dim is live **only if it is already in
   > normalized form**. Comparing raw-referenced against normalized-scored therefore
   > flags exactly the predicates that are inert at runtime — including a
   > `Has Citations` predicate whose dimension *is* listed (un-normalized) in
   > `rubric_dimensions`. Normalizing *both* sides for a "fair" comparison would hide
   > this real runtime bug. (Surfaced reviewing FEAT-2301; the builder prevents it in
   > builder output by normalizing predicates at emit time, but hand-authored and
   > `edit-routes` loops still need this gate.)
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
- [ ] A predicate dim that matches a `rubric_dimensions` entry only *after*
  normalization (e.g. predicate `Has Citations` vs. `rubric_dimensions` entry
  `Has Citations`, score key `has-citations`) **DOES** trigger the warning — the raw
  predicate dim is inert at runtime, so the referenced set must stay un-normalized
  (guards the intentional step-1-raw / step-2-normalized asymmetry)
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

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis (2026-06-26). All cited anchors verified against current source._

**Suppression-flag plumbing requires two more edit sites not listed above.** The
`policy_dims_scored_ok` escape hatch is a top-level FSM flag; every existing `*_ok`
flag lives in three places, so this one must too:
- `scripts/little_loops/fsm/schema.py` — add `policy_dims_scored_ok: bool = False` to the
  `FSMLoop` dataclass (beside `generator_fix_ok`, `schema.py:1007`); serialize-when-true in
  `to_dict()` (beside `schema.py:1088`); bind in `from_dict()` with
  `data.get("policy_dims_scored_ok", False)` (beside `schema.py:1163`). Omitting the
  dataclass field makes `fsm.policy_dims_scored_ok` raise `AttributeError`.
- `scripts/little_loops/fsm/validation.py` — add `"policy_dims_scored_ok"` to
  `KNOWN_TOP_LEVEL_KEYS` (`validation.py:178-183`) so a loop setting the flag does not also
  trip the "Unknown top-level key" warning. Add a YAML round-trip test asserting no
  Unknown-top-level warning (model: `TestArtifactIsolation.test_shared_state_ok_recognized_as_top_level_key`).

**Read `policy_rules` via the existing accessor — do not re-implement.**
`route_table.py:PolicyRuleExtractor.extract(fsm)` already wraps
`parse_rules(str(fsm.context.get("policy_rules", "")))`; reuse it or copy the one-liner.
Collect the referenced set raw (per Expected Behavior step 1):
`{pred.dim for rule in rules for pred in rule.predicates}`. Guard malformed tables with
`if not text.strip(): return []` and a `try/except (ValueError)` around `parse_rules` — the
grammar validator owns syntax errors (satisfies the "malformed table no-crash" criterion).

**`rubric_dimensions` is never pipe-split by any Python code — the validator must split it
itself.** Confirmed: `context.rubric_dimensions` (e.g. `policy-refine.yaml:16`,
`"clarity|completeness|feasibility|security"`) is consumed only as prompt-interpolation text
(`lib/rubric-router.yaml:8` documents the `|` convention; the LLM emits `DIMENSION: <name>:
<score>` lines that `lib/policy-router.yaml:96` parses). No `.split("|")` on the context value
exists anywhere. The new validator owns split + normalization, mirroring `policy-router.yaml:97`
exactly so the scored set matches the `rubric-dim-<name>.txt` keys:
`re.sub(r"\s+", "-", name.strip().lower())`.

**Shell-scorer detection (Expected Behavior step 2, second bullet).** Scan `state.action` for
states where `state.action_type in ("shell", None)`; match the literal
`r"rubric-dim-([\w-]+)\.txt"` (write site: `policy-router.yaml:99`,
`f"rubric-dim-{dim_name}.txt"`). Skip states with no `action`. Pattern to model:
`_validate_generator_fix_discipline` (`validation.py:1543+`) iterates states and inspects
shell action bodies the same way.

**Verified anchors (current line numbers).**

| Reference | Issue cites | Actual | Status |
|-----------|-------------|--------|--------|
| `validate_fsm()` span | `validation.py:956-1094` | `def` at **923**, `return` at **1096** | ⚠ start stale — use **923** |
| register beside `_validate_classify_route_default` | `~1083` | **1083** | ✓ exact |
| `_ALL_OPS` | `policy_rules.py:28` | **28** | ✓ |
| `_eval_predicate` missing-dim → `!=`-only | `policy_rules.py:188-195` | def **188**, missing-dim block **192-195** | ✓ |
| `rubric-dim-<name>.txt` normalization | `policy-router.yaml:97` | **97** | ✓ |
| `aggregate` always written | (Expected Behavior) | `policy-router.yaml:89-91`, unconditional | ✓ exempt confirmed |

**Test scaffolding.** Model the new tests on `TestClassifyRouteDefault`
(`scripts/tests/test_fsm_validation.py`): a private `_*_fsm(...)` builder with keyword flags,
`make_state(...)` / `EvaluateConfig` helpers, and the fires / does-not-fire / suppression /
`validate_fsm()`-wiring quartet. Import `_validate_policy_dimensions_scored` in the test file's
private-validator import block. `_validate_classify_route_default` itself is defined at
`validation.py:1602` — a complete, current model for the new validator's shape and WARNING
construction (`ValidationError(..., severity=ValidationSeverity.WARNING)`).

## Scope Boundaries

**In scope:**
- A single read-only `ll-loop validate` validator (`_validate_policy_dimensions_scored`)
  that cross-checks `policy_rules`-referenced dimensions against scored dimensions and
  emits WARNING-severity findings.

**Out of scope:**
- **Auto-fixing or normalizing predicates.** The validator detects and warns only; it
  does not rewrite predicates, scores, or `rubric_dimensions`. Emit-time predicate
  normalization stays FEAT-2301's builder responsibility.
- **Changing the `policy_rules` grammar or runtime evaluation.** `fsm/policy_rules.py`
  (`parse_rules`, `_eval_predicate`, `evaluate_rules`) is reused unchanged — no new
  operators, no change to runtime matching behavior.
- **ERROR severity or hard gating.** WARNING-only by design, because shell-scorer
  detection is heuristic; promoting to ERROR or a blocking gate is explicitly excluded.
- **Detecting dynamically-named shell scorers.** A scorer that computes the
  `rubric-dim-<name>.txt` filename at runtime cannot be matched statically; such cases
  are accepted as known false negatives, mitigated by warn-not-error and the
  `policy_dims_scored_ok` escape hatch.
- **Loops without `context.policy_rules`.** The validator is a no-op for any loop that
  does not define a policy-router decision table.

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


## Session Log
- `/ll:refine-issue` - 2026-06-26T23:21:11 - `80f7e865-5668-4056-97f7-9794b7b8c70e.jsonl`
- `/ll:format-issue` - 2026-06-26T23:01:07 - `11019421-7a7f-4973-a715-6797eeed3a7c.jsonl`
