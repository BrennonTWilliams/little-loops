---
status: open
discovered_date: 2026-06-04
discovered_by: capture-issue
captured_at: '2026-06-04T00:59:01Z'
relates_to: [ENH-1819]
labels:
- validation
- loop-authoring
- harness
- captured
---

# P2-ENH-1917: ll-loop validate warning for prompt states that route only on_yes (silent partial/no dead-end)

## Summary

A `prompt` (or otherwise LLM-judged) state that declares only `on_yes` — with
no `on_no`, `on_partial`, `next`, or full `route` table — silently dead-ends
when the default LLM judge returns `partial` or `no`. `_route` finds no matching
shorthand and returns `None`; the loop terminates with no route, and (in a
sub-loop) the parent treats the non-`done` exit as `failed`. `ll-loop validate`
should warn on this shape so the dead-end is caught at authoring time, not in a
post-mortem.

## Motivation

This is the root cause of the `site-generator-20260603T191934` failure
(html-website-generator via `oracles/generator-evaluator`). The `generate`
state declared:

```yaml
generate:
  action_type: prompt
  action: ${context.generate_prompt}
  on_yes: evaluate
  on_error: failed
```

A bare `prompt` action is gated by the default "did this action succeed?" LLM
judge, which returns `yes`/`no`/`partial`. On the first pass the agent's output
asserted concrete file claims → `yes` → routed to `evaluate`. On a later pass
the agent *narrated* its fixes ("here's what I changed") without re-asserting
them → `partial`. `partial` had no route (`on_partial` unset) → `_route`
returned `None` → the sub-loop dead-ended → the parent routed
`run_gen_eval → failed`, **discarding a fully-corrected artifact**.

The failure was:
- **Nondeterministic** — identical state and routing; only the judge verdict
  differed, driven by how the agent phrased its output.
- **Silent** — no diagnostic; required manual event-log tracing to find.
- **Widespread** — every thin wrapper over `generator-evaluator` (html-anything,
  hitl-md, p5js-sketch-generator, svg-image-generator) inherited the same
  dead-end.

The instance is fixed (generate now maps yes/no/partial → evaluate), but the
*class* of footgun is unguarded. This sits in the same family as ENH-1819
(multimodal evaluator blind-spot warning) — a static check that shifts a known
harness failure mode left.

## Current Behavior

`ll-loop validate` requires `on_error` on route/evaluate states
(test_builtin_loops.py: "All route/evaluate states must define on_error to
prevent hangs"), but nothing flags a state whose evaluator can emit `no`/
`partial` while only `on_yes` is mapped. The `partial`/`no` paths fall through
`_route` (executor.py `_route`, ~line 1294–1347) and return `None`.

## Proposed Behavior

Add a validation rule (WARNING severity) that flags any state where:
1. The state will be graded by an LLM judge that can return `partial`/`no` —
   i.e. `action_type: prompt`/`slash_command` with no explicit deterministic
   `evaluate:` block, OR an explicit `check_semantic`/`llm_structured`
   evaluator — AND
2. The state uses shorthand routing (no `next`, no full `route` table) — AND
3. `on_yes` is set but at least one of `on_no` / `on_partial` is missing (and
   no `route.default` / catch-all exists).

Message should name the state and the unrouted verdict(s), e.g.:

```
WARNING [state: generate] LLM-judged prompt routes only on_yes; a `partial`
or `no` verdict has no route and will dead-end the loop (parent reads this as
failed). Add on_no/on_partial, use `next:` for unconditional handoff, or a
`route:` table with a default. (ENH-1917)
```

Provide a top-level suppression flag consistent with existing meta-rules (e.g.
`partial_route_ok: true`) for the rare case where dead-ending on a non-yes
verdict is intentional.

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/validation.py` — add the new per-state predicate.
  The existing shorthand-vs-route check lives here (~line 598, `has_shorthand`/
  `has_route`); the MR-1/MR-3 meta-rule checks and their suppression handling
  live in the same module (~lines 1037–1276). The new rule sits alongside them.
- `scripts/little_loops/fsm/schema.py` — register the `partial_route_ok`
  top-level loop key next to the existing `meta_self_eval_ok` / `shared_state_ok`
  flags (line 145–146).

### Dependent Files (Callers/Importers)
- `scripts/little_loops/fsm/executor.py` — `_route` (line 1294). No change, but
  the new predicate must reuse the same determination this method uses to decide
  whether a state is gated by the default LLM judge (Implementation Step 2),
  rather than re-deriving it.

### Similar Patterns
- Existing meta-rules MR-1 (`validation.py` ~line 1037) and MR-3 (~line 1262),
  including their `*_ok: true` top-level suppression flags, are the template for
  this rule's severity wiring and suppression behavior.

### Tests
- `scripts/tests/test_fsm_validation.py` — new fixtures: fires on an `on_yes`-only
  prompt state; does not fire for `next:`, full `route:` with `default`, or
  `on_no`+`on_partial`; suppressed by `partial_route_ok: true`.
- `scripts/tests/test_builtin_loops.py` — assert no new false positives across
  all built-in loops (the `generator-evaluator` fix should pass clean).

### Documentation
- `.claude/CLAUDE.md` § Loop Authoring — add the new rule and `partial_route_ok`
  suppression note, consistent with the existing MR-1/MR-3 entries.

### Configuration
- N/A — `partial_route_ok` is a per-loop YAML top-level key (registered in
  `schema.py`), not an `.ll/ll-config.json` setting.

## Implementation Steps

1. Locate the validator that owns the existing route/`on_error` and MR-1/MR-3
   checks (`scripts/little_loops/fsm/validation.py`, the module feeding
   `ll-loop validate`).
2. Add a per-state predicate implementing the 3 conditions above. Reuse the
   existing logic that decides whether a state gets the default LLM judge (the
   same determination `_route`/executor uses) rather than re-deriving it.
3. Emit a WARNING-severity finding naming the state and missing verdict routes;
   wire the `partial_route_ok` top-level suppression.
4. Tests: add a fixture loop with an `on_yes`-only prompt state and assert the
   warning fires; assert it does NOT fire when `next:`, a full `route:` with
   default, or `on_no`+`on_partial` are present, and when suppressed.
5. Run `ll-loop validate` across all built-in loops and confirm no false
   positives on existing well-formed loops (the generator-evaluator fix should
   now pass clean).

## API/Interface

- New validation rule code (e.g. `VR-?`/`MR-?` per the existing scheme) surfaced
  by `ll-loop validate`.
- New optional top-level loop key `partial_route_ok: true` to suppress.
- No change to FSM runtime routing semantics (this is static validation only).
  Runtime diagnostics for unmapped verdicts were considered and deferred (not
  captured this session).

## Scope Boundaries

- **Static validation only.** No change to FSM runtime routing semantics; this
  rule fires at `ll-loop validate` time, never during execution.
- **WARNING severity, not ERROR.** The rule flags the dead-end but does not fail
  validation or block the loop from running — consistent with MR-3, unlike MR-1
  (ERROR).
- **Flag, don't auto-fix.** The rule names the unrouted verdict(s); it does not
  rewrite routes or inject a default. Authoring the fix stays with the user.
- **Runtime diagnostics are out of scope.** Logging/surfacing a `None`-route at
  execution time (when `_route` returns `None`) was considered and explicitly
  deferred — not captured this session.
- **Scope is LLM-judged + shorthand-routed states.** States with a deterministic
  `evaluate:` block, a full `route:` table with a `default`, or `next:` are
  correctly routed and out of scope (no warning).

## Acceptance Criteria

- [ ] `ll-loop validate` emits a WARNING for an LLM-judged state that maps only
      `on_yes` (no `on_no`/`on_partial`/`next`/`route.default`).
- [ ] The warning names the state and the unrouted verdict(s).
- [ ] No warning when `next:`, a `route:` table with `default`, or both
      `on_no` and `on_partial` are present.
- [ ] `partial_route_ok: true` suppresses the warning.
- [ ] All existing built-in loops pass `ll-loop validate` with no new false
      positives.
- [ ] Tests cover: fires, each non-firing case, and suppression.

## Impact

- **Priority**: P2 — root cause of a real silent failure
  (`site-generator-20260603T191934`) that discarded a fully-corrected artifact,
  and the dead-end shape is inherited by every thin wrapper over
  `generator-evaluator` (html-anything, hitl-md, p5js-sketch-generator,
  svg-image-generator). Not P0/P1 because the triggering instance is already
  fixed; this guards the latent *class* at authoring time.
- **Effort**: Small — one per-state predicate added to an existing validator
  (`validation.py`) that already houses the shorthand/route and MR-1/MR-3 checks;
  reuses the executor's existing default-judge determination; tests mirror the
  existing meta-rule fixtures.
- **Risk**: Low — WARNING severity, static validation only, no FSM runtime
  change. The main risk is false positives, gated by the acceptance criterion
  requiring all built-in loops to pass clean.
- **Breaking Change**: No.

## Session Log
- `/ll:format-issue` - 2026-06-04T01:06:14 - `757f3c54-d01d-4dee-a981-dcb7ddf1804c.jsonl`
- `/ll:capture-issue` - 2026-06-04T00:59:01Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/401066ef-7fde-4c47-a6e9-bf52970f6eab.jsonl`

---

## Status

- **Current**: open
