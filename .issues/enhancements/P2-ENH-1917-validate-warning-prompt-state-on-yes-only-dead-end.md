---
status: done
discovered_date: 2026-06-04
discovered_by: capture-issue
captured_at: '2026-06-04T00:59:01Z'
completed_at: '2026-06-04T01:48:16Z'
relates_to:
- ENH-1819
labels:
- validation
- loop-authoring
- harness
- captured
confidence_score: 98
outcome_confidence: 84
score_complexity: 17
score_test_coverage: 22
score_ambiguity: 23
score_change_surface: 22
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
- `scripts/little_loops/fsm/schema.py` — register `partial_route_ok: bool = False`
  in the `FSMLoop` dataclass (lines 968–969, next to `meta_self_eval_ok` /
  `shared_state_ok`); also add the `to_dict()` emission guard (~line 1034) and the
  `from_dict()` read (~line 1090), following the identical 3-site pattern of the
  existing flags.
- `scripts/little_loops/fsm/validation.py` — additionally register `partial_route_ok`
  in `KNOWN_TOP_LEVEL_KEYS` (lines 119–153) so the key does not produce an "Unknown
  top-level key" warning on loops that use it.

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

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_fsm_schema.py` — add `TestPartialRouteOk` class (3 round-trip
  serialization tests: `partial_route_ok=True` round-trips in `to_dict()`/`from_dict()`;
  `partial_route_ok=False` omitted from `to_dict()`; `from_dict()` without the key
  defaults to `False`). Mirror the `TestSharedStateOk` pattern at lines 3087–3122.
  Also add `test_partial_route_ok_recognized_as_top_level_key` (YAML round-trip via
  `load_and_validate()`, no "Unknown top-level" warning). [Agent 2 + 3 finding]

### Documentation
- `.claude/CLAUDE.md` § Loop Authoring — add the new rule and `partial_route_ok`
  suppression note, consistent with the existing MR-1/MR-3 entries.
- `skills/review-loop/reference.md` — add MR-4 to the rule-code table (MR-1 and
  MR-2 are listed; MR-3 was added after `reference.md` was last updated and is
  missing; add both MR-3 and MR-4 for completeness).

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md` — `ll-loop validate` section currently lists only MR-1
  and MR-2 bullet entries; add MR-3 (`shared_state_ok: true`) and MR-4
  (`partial_route_ok: true`) bullets; update the suppression sentence to name all
  four flags. [Agent 2 finding]
- `docs/reference/API.md` — two locations: (1) `#### FSMLoop` pseudocode block
  currently lists `meta_self_eval_ok` but omits `shared_state_ok` and
  `partial_route_ok` — add both; (2) `#### validate_fsm` "Checks performed"
  bullet list ends at MR-2 — add MR-3 and MR-4 entries. [Agent 2 finding]
- `docs/guides/LOOPS_GUIDE.md` — `## Beyond the Basics` section documents MR-1
  and MR-3 in paragraph form; add a parallel MR-4 paragraph after the MR-3
  entry (around line 1621). [Agent 2 finding]

### Configuration
- N/A — `partial_route_ok` is a per-loop YAML top-level key (registered in
  `schema.py`), not an `.ll/ll-config.json` setting.

## Implementation Steps

1. In `scripts/little_loops/fsm/validation.py`, add `_validate_partial_route_dead_end(fsm: FSMLoop) -> list[ValidationError]` following the MR-3 pattern (`_validate_artifact_isolation`, lines 1253–1283): early-return on `fsm.partial_route_ok`, iterate per-state, emit `ValidationSeverity.WARNING` at `path=f"states.{state_name}"`.

2. **Default-judge detection** — replicate `_action_mode()` from `executor.py:1390` (do not call it; it is runtime code). A state is LLM-judged when:
   - `state.evaluate is None` AND (`state.action_type in ("prompt", "slash_command")` OR `state.action_type is None and state.action.startswith("/")`)
   - OR `state.evaluate is not None and state.evaluate.type in ("llm_structured", "check_semantic")`

3. **Dead-end condition** — after confirming a state is LLM-judged AND uses shorthand routing (`state.route is None AND state.next is None`), flag it when `state.on_yes is not None and (state.on_no is None or state.on_partial is None)`. States with `on_no` AND `on_partial` both set, or with `state.next`, or with a full `route:` table, are safe.

4. Wire the new rule into `validate_fsm()` (lines 985–1001) with `errors.extend(_validate_partial_route_dead_end(fsm))` after the existing `_validate_harness_multimodal_evaluator_blind_spot` call.

5. Register `partial_route_ok` in `schema.py` `FSMLoop` dataclass (lines 968–969), `to_dict()` (~line 1034), and `from_dict()` (~line 1090); add to `KNOWN_TOP_LEVEL_KEYS` in `validation.py` (lines 119–153).

6. Tests in `scripts/tests/test_fsm_validation.py` — create `TestPartialRouteDeadEnd` using `make_state()` (line 40) and the `TestArtifactIsolation` class as a structural template. Required cases: fires on `prompt` state with `on_yes`-only; does NOT fire when `on_no`+`on_partial` both set; does NOT fire when `next:` present; does NOT fire when full `route:` table present; does NOT fire for a non-LLM evaluator (e.g. `exit_code`); suppressed by `partial_route_ok: true`; wired into `validate_fsm()`.

7. Add a dedicated false-positive test for `generator-evaluator.yaml` in `test_builtin_loops.py` — call `_validate_partial_route_dead_end(fsm)` directly and assert `errors == []` (note: `test_all_validate_as_valid_fsm` only checks ERROR severity and will not catch WARNING false positives).

8. Update `.claude/CLAUDE.md` § Loop Authoring and `skills/review-loop/reference.md` with the MR-4 rule entry.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

9. Add `TestPartialRouteOk` class to `scripts/tests/test_fsm_schema.py` — 3 round-trip serialization tests for `partial_route_ok` (mirror `TestSharedStateOk` at lines 3087–3122); also add `test_partial_route_ok_recognized_as_top_level_key` via `load_and_validate()`.
10. Update `docs/reference/CLI.md` — add MR-3 and MR-4 bullet entries under `ll-loop validate`; update the suppression sentence to include `partial_route_ok: true`.
11. Update `docs/reference/API.md` — (a) add `partial_route_ok: bool = False` and `shared_state_ok: bool = False` to the `FSMLoop` pseudocode block; (b) add MR-3 and MR-4 bullets to the `validate_fsm` "Checks performed" list.
12. Update `docs/guides/LOOPS_GUIDE.md` — add MR-4 paragraph after the MR-3 entry in `## Beyond the Basics`.

## API/Interface

- **Rule code: MR-4** (MR-3 is the most recently added meta-rule; MR-4 is next
  in the series). Surfaced by `ll-loop validate` alongside MR-1 through MR-3.
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
- `/ll:ready-issue` - 2026-06-04T01:36:30 - `2633bc25-92d3-4316-ad8f-a1cc361132fd.jsonl`
- `/ll:wire-issue` - 2026-06-04T01:31:35 - `b13525d6-c98d-4ecb-8272-c015b59a2e9d.jsonl`
- `/ll:refine-issue` - 2026-06-04T01:24:59 - `c4f4893e-57f1-4b73-b183-061e7162680d.jsonl`
- `/ll:format-issue` - 2026-06-04T01:06:14 - `757f3c54-d01d-4dee-a981-dcb7ddf1804c.jsonl`
- `/ll:capture-issue` - 2026-06-04T00:59:01Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/401066ef-7fde-4c47-a6e9-bf52970f6eab.jsonl`

---

## Resolution

- **Implemented**: 2026-06-04
- **Changes**:
  - `scripts/little_loops/fsm/schema.py` — added `partial_route_ok: bool = False` field with `to_dict()`/`from_dict()` round-trip support
  - `scripts/little_loops/fsm/validation.py` — added `_is_llm_judged()` helper, `_validate_partial_route_dead_end()` rule (MR-4, WARNING severity), wired into `validate_fsm()`, added `partial_route_ok` to `KNOWN_TOP_LEVEL_KEYS`
  - `scripts/tests/test_fsm_validation.py` — added `TestPartialRouteDeadEnd` class (14 tests)
  - `scripts/tests/test_fsm_schema.py` — added `TestPartialRouteOk` class (3 round-trip tests)
  - `scripts/tests/test_builtin_loops.py` — added `TestMR4BuiltinFalsePositives` class (regression guard for `generator-evaluator.yaml`)
  - `.claude/CLAUDE.md` — added MR-4 entry to Loop Authoring section
  - `skills/review-loop/reference.md` — added MR-3 and MR-4 to rule-code table
  - `docs/reference/CLI.md` — added MR-3 and MR-4 bullet entries under `ll-loop validate`
  - `docs/reference/API.md` — added `shared_state_ok`/`partial_route_ok` to `FSMLoop` pseudocode; added MR-3 and MR-4 to `validate_fsm` checks list
  - `docs/guides/LOOPS_GUIDE.md` — added MR-4 paragraph after MR-3 entry

## Status

- **Current**: done
