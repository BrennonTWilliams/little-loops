---
id: BUG-3228
type: BUG
title: 'uncertain_suffix verdicts are unroutable: X_uncertain matches no route and
  terminates the run'
priority: P2
testable: true
status: done
completed_at: '2026-08-16T00:00:00Z'
discovered_by: ll-issues-create
discovered_date: '2026-08-17'
captured_at: '2026-08-17T01:19:18Z'
parent: EPIC-3217
confidence_score: 100
outcome_confidence: 94
score_complexity: 23
score_test_coverage: 24
score_ambiguity: 24
score_change_surface: 23
---

# BUG-3228: uncertain_suffix verdicts are unroutable: X_uncertain matches no route and terminates the run

## Summary

`uncertain_suffix: true` makes a loop unroutable. `evaluate_llm_structured()` appends
`_uncertain` to *whatever* verdict the judge returned when `confidence < min_confidence`
(`scripts/little_loops/fsm/evaluators.py:1295-1296`), but `FSMExecutor._route()`
(`scripts/little_loops/fsm/executor.py:2699-2752`) has no suffix handling for any verdict —
so `yes_uncertain` matches no shorthand and no `extra_routes` key.

The failure takes two shapes depending on how the state routes:

- **Shorthand-routed states** (`on_yes`/`on_no`/…): `_route()` returns `None` and the run
  terminates via `_finish("error", "No valid transition")`.
- **`route:`-table states carrying a `_` default**: the suffixed verdict is silently
  absorbed by `route.default` (`executor.py:2726-2727`) — so `yes_uncertain` takes the
  *failure* branch without any diagnostic. This is the quieter and worse of the two, and it
  is the shape both worked examples in `docs/generalized-fsm-loop.md` (830-846, 1355-1365)
  actually use.

Either way the setting is unusable as shipped unless the author has declared
`on_yes_uncertain`, `on_no_uncertain`, `on_partial_uncertain`, `on_blocked_uncertain`,
`on_error_uncertain` and `on_cannot_judge_uncertain` by hand. No loop under
`scripts/little_loops/loops/` sets `uncertain_suffix` (grep-confirmed), which is why this
has never surfaced in a run.

## Steps to Reproduce

1. Add `uncertain_suffix: true` and `min_confidence: 0.7` to any `llm_structured` state's
   `evaluate:` block — the configuration `fsm-loop-schema.json:765-769` and
   `docs/generalized-fsm-loop.md:830-846` both advertise.
2. Have the judge return a `yes` at confidence below the threshold, so
   `evaluate_llm_structured()` emits `yes_uncertain` (`evaluators.py:1295-1296`).
3. On a shorthand-routed state, the run terminates with `error="No valid transition"`. On a
   `route:`-table state carrying a `_` default, the verdict is instead absorbed by the
   default branch with no diagnostic.

Both paths are reproducible by calling `FSMExecutor._route()` directly with the suffixed
verdict, as the matrix below records.

## Current Behavior

Against a state declaring `on_yes`/`on_no`/`on_error` (shorthand; verified by direct call):

```
yes                    -> _route='done'
yes_uncertain          -> _route=None        # run dies: "No valid transition"
no_uncertain           -> _route=None
partial_uncertain      -> _route=None
error_uncertain        -> _route=None        # on_error is NOT reached
cannot_judge           -> _route=None        # holds, then _abstention_fallback
cannot_judge_uncertain -> _route=None        # holds, then _abstention_fallback
```

Against a state declaring `route: {yes: verify, no: fix, _: fix}` (the documented shape):

```
yes_uncertain          -> _route='fix'       # silently takes the failure branch
blocked_uncertain      -> _route='fix'       # bypasses the declared `blocked:` route
```

With `on_cannot_judge` declared, `cannot_judge` resolves but `cannot_judge_uncertain` still
returns `None` — `_abstention_declared()` (`executor.py:2656-2667`) matches the literal
verdict string, as its own docstring states.

`uncertain_suffix` is declared in `scripts/little_loops/fsm/fsm-loop-schema.json:765-769`
and `EvaluateConfig` (`scripts/little_loops/fsm/schema.py:103`, default `false`), so a loop
author reading the schema can enable a setting that breaks their loop.

### `error_uncertain` is reachable and is not merely cosmetic

`evaluate_llm_structured()` exempts `"error"` from the grammar check
(`evaluators.py:1270`, `verdict not in DEFAULT_VERDICT_ENUM and verdict != "error"`), so a
judge returning `{"verdict": "error", "confidence": 0.3}` reaches the suffix line and
produces `error_uncertain`. That verdict misses `route.error`/`on_error` in `_route()` *and*
misses the non-retryable-exit-code filter at `executor.py:2055-2066`, which compares
`verdict == "error"` exactly. A custom `schema:` bypasses the grammar check entirely, so any
verdict string the author's schema admits is likewise suffixable — the fix must be generic,
not an enumeration of the five default-grammar verdicts.

## Expected Behavior

`X_uncertain` falls back to `on_X` (or `route.routes["X"]`) when the state declares no
explicit `on_X_uncertain` / `route.routes["X_uncertain"]`. An explicit suffixed route always
wins, so an author who wants distinct handling for a low-confidence verdict still gets it.

This preserves ENH-3185 AC12's position that the two signals are semantically distinct —
`cannot_judge` is "I could not evaluate it", `_uncertain` is "I am unsure" — while making
the combination routable by default instead of fatal.

For the abstention verdicts specifically, the fallback must compose with the existing hold
machinery: `cannot_judge_uncertain` at a state declaring `on_cannot_judge` should count as
*declared* (route immediately, no hold), matching the base verdict's behavior. The
*undeclared* case is unchanged — it still holds and then escalates to the on_error
equivalent.

### Resolution order (the decisive detail)

The fallback must be applied **after the exact-verdict lookup and before `route.default`**,
not "before returning `None`". `_route()`'s route-table branch consults
`state.route.default` at `executor.py:2726-2727`, ahead of every `return None`. A strip
inserted at the end of the method would therefore leave every `route:`-table state with a
`_` default routing `yes_uncertain` to the default branch — converting today's loud failure
into a silent misroute, which is strictly worse.

The intended resolution order for a verdict ending in `_uncertain`:

1. exact match in `route.routes` / `extra_routes` / the typed shorthands (unchanged)
2. **strip the literal trailing `_uncertain` and re-resolve from step 1 with the base
   verdict**
3. `route.default` (`_`)
4. `route.error` / `on_error`
5. `None`

Implementation shape: a guarded recursion at the head of `_route()` — if the verdict ends
with the literal `_uncertain`, is not itself explicitly declared, and the base verdict is
non-empty, return `self._route(state, verdict[: -len("_uncertain")], ctx)`. Strip exactly
one literal `_uncertain` (per the `history_reader.py:3089` precedent — not an arbitrary
trailing token), and do not recurse further, so a pathological
`yes_uncertain_uncertain` resolves at most one level.

### Behavior change to the documented examples

`docs/generalized-fsm-loop.md:1355-1365` declares `yes_uncertain` but not `no_uncertain` or
`blocked_uncertain`, with `_: "refactor"`. Under the fix, `blocked_uncertain` moves from
`refactor` (via `_`) to `rollback` (via `blocked:`). That is the intended correction, but it
is a behavior change to a shipped documented example and belongs in the changelog entry.

## Motivation

Resolves decision (a) of EPIC-3217. The retrofit children (BUG-3218, BUG-3220, and
BUG-3219's successors BUG-3226/BUG-3227) declare `on_cannot_judge` only; without this fix,
each of those gates still has an unroutable `cannot_judge_uncertain` path, and ENH-3222's
validator rule would certify the narrow form as complete.

The alternatives were considered and rejected at the EPIC: declaring both keys at ~22 gate
sites hardens one branch of an already-fatal configuration and doubles routing boilerplate
forever; an abstention-only prefix-match fixes 1 of 6 suffixed verdicts and encodes an
asymmetry that is hard to explain later.

## Proposed Solution

Add the suffix fallback to `_route()` at the resolution position described above, and the
matching declaration check to `_abstention_declared()`, so a declared `on_cannot_judge`
covers `cannot_judge_uncertain` without a hold.

This changes shipped ENH-3185 routing semantics, so it needs its own tests rather than
riding along with a loop-YAML retrofit.
`scripts/tests/test_fsm_executor.py::TestAbstentionRouting` (line 1882) already covers the
undeclared/declared abstention matrix and is the natural home;
`test_cannot_judge_uncertain_undeclared_also_holds_then_falls_to_on_error` (line 2041)
asserts today's behavior for the undeclared case and must keep passing — the fallback
changes the *declared* case, not the undeclared one.

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/executor.py` — `_route()` (2699-2752): add the suffix fallback
  between the exact-verdict lookups and `route.default` (2726-2727). `_abstention_declared()`
  (2656-2667): treat `on_cannot_judge` as declaring `cannot_judge_uncertain` when no explicit
  `on_cannot_judge_uncertain` exists, so the declared path routes immediately instead of
  holding. `_abstention_fallback()` (2669-2681) and `_route_abstention_hold()` (2683-2697)
  need no change.
- `scripts/little_loops/fsm/fsm-loop-schema.json` — `uncertain_suffix` description
  (765-769) currently reads "If true, append _uncertain to low-confidence verdicts" with no
  mention of routing; extend it to state that `X_uncertain` falls back to `X`'s route unless
  explicitly declared.
- `scripts/little_loops/fsm/schema.py` — `EvaluateConfig.uncertain_suffix` docstring (62)
  mirrors the schema description; keep the two in lockstep.
- `docs/generalized-fsm-loop.md` — the `cannot_judge` prose block (547) documents the
  abstention routing contract and should state the `_uncertain` fallback; the two
  `uncertain_suffix` worked examples (830-846, 1355-1365) should note that unlisted
  `X_uncertain` keys now inherit `X`'s route rather than falling to `_`.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/fsm/evaluators.py:1295-1296` — the sole writer of suffixed verdicts;
  unchanged by this issue.
- `scripts/little_loops/fsm/verdicts.py:25-27` — `is_abstention_verdict()` already accepts
  the `_uncertain` suffix (`verdict.startswith(f"{CANNOT_JUDGE}_")`), which is why the hold
  path already sees `cannot_judge_uncertain`; only the *declaration* check disagrees with it
  today. No change needed — this issue brings `_abstention_declared()` into line with it.
- `scripts/little_loops/fsm/executor.py:2055-2066` — the non-retryable-exit-code filter
  matches `verdict == "error"` exactly. Decide deliberately whether `error_uncertain` should
  satisfy it. Recommended: leave it alone (the filter is exit-code-driven and
  `uncertain_suffix` only applies to `llm_structured`, which has no `action_result.exit_code`
  contract) and note the decision in the implementation, rather than leaving it undiscussed.

### Conventions in Force
- Routing precedence changes carry an ENH/BUG citation in an inline comment at the
  precedence site — evidence: `executor.py:2075-2080` (`# ENH-3185 AC7: …`), 2050-2054.
- `_route()` returns `None` rather than guessing; any new branch must preserve "never fall
  back to `on_no`" (`_abstention_fallback()` docstring, 2672-2675).
- Schema JSON descriptions and the mirroring dataclass docstring are kept in lockstep
  (ENH-2896/ENH-2934/ENH-2997 precedent, enforced by `scripts/tests/test_fsm_schema.py`).

### Tests
- `scripts/tests/test_fsm_executor.py::TestAbstentionRouting` (1882) — home for the new
  cases; `test_cannot_judge_uncertain_undeclared_also_holds_then_falls_to_on_error` (2041)
  is the regression anchor for the unchanged undeclared path.
- New coverage required, at minimum:
  - shorthand state: `yes_uncertain` → `on_yes` target; `no_uncertain` → `on_no`;
    `partial_uncertain` → `on_partial`; `blocked_uncertain` → `on_blocked`;
    `error_uncertain` → `on_error`.
  - route-table state **with** a `_` default: `yes_uncertain` → `routes["yes"]`, **not** the
    default — the specific regression the resolution-order decision exists to prevent.
  - explicit `on_yes_uncertain` (and `route.routes["yes_uncertain"]`) still wins over the
    fallback.
  - custom-schema verdict outside the default grammar, e.g. `needs_review_uncertain` →
    `on_needs_review` via `extra_routes`.
  - declared `on_cannot_judge` + `cannot_judge_uncertain` → routes immediately, `_abstention_holds`
    untouched; undeclared → still holds twice then escalates (2041 unchanged).
  - a verdict that is exactly `_uncertain` or `yes_uncertain_uncertain` does not recurse
    unboundedly.
- `scripts/tests/test_fsm_schema.py` — schema/dataclass lockstep for the reworded
  `uncertain_suffix` description.

### Documentation
- `docs/generalized-fsm-loop.md:547` — the canonical abstention-routing prose.
- `docs/reference/API.md` `little_loops.fsm.executor` — `_route()`/`_abstention_declared()`
  semantics.
- `skills/create-loop/reference.md` — routing-key field reference; note that suffixed keys
  are optional overrides, not required declarations, so `/ll:create-loop` does not scaffold
  six extra keys per gate.

## Program Design

### Signatures
- `FSMExecutor._route(state: StateConfig, verdict: str, ctx: InterpolationContext) -> str | None` —
  the routing resolver gaining the suffix fallback; see `scripts/little_loops/fsm/executor.py:2699-2752`.
- `FSMExecutor._abstention_declared(state: StateConfig, verdict: str) -> bool` — the
  dispatch gate deciding hold-vs-route; gains the same suffix-aware lookup so a declared
  `on_cannot_judge` covers `cannot_judge_uncertain`; see `scripts/little_loops/fsm/executor.py:2656-2667`.
- `is_abstention_verdict(verdict: str) -> bool` — already suffix-aware; the asymmetry this
  issue removes is that `_abstention_declared()` is not; see `scripts/little_loops/fsm/verdicts.py:25-27`.

### Types
N/A — no new data shape. No schema change beyond a description reword; `StateConfig`,
`RouteConfig`, and `extra_routes` are unchanged.

### Call Path
Judge returns a low-confidence verdict → `evaluate_llm_structured()` appends `_uncertain`
(`evaluators.py:1295-1296`) → executor dispatch (`executor.py:2080-2084`) →
`is_abstention_verdict()` / `_abstention_declared()` → `_route()`. Today `_route()` finds no
exact match and either returns `None` (shorthand states → `_finish("error", "No valid
transition")` at 758-774) or falls into `route.default` (2726-2727). After the fix, the
suffix is stripped between those two points and the base verdict re-resolves against the
state's declared routes.

### Decision Rules
- Strip exactly one literal trailing `_uncertain`; do not treat an arbitrary trailing
  `_<token>` as a modifier.
- An explicitly declared suffixed route always wins over the fallback, in both the
  `route.routes` and `extra_routes`/shorthand lookups.
- The fallback runs before `route.default` and before `route.error`/`on_error`.
- The fallback never introduces a route where the base verdict has none — if `on_yes` is
  absent, `yes_uncertain` resolves exactly as `yes` would (default, then error, then
  `None`).
- Undeclared-abstention behavior is untouched: the hold cap and `_abstention_fallback()`
  still govern `cannot_judge` / `cannot_judge_uncertain` at states declaring neither route.

## Implementation Steps

1. `_route()` resolves `X_uncertain` to `X`'s route when no explicit `X_uncertain` route
   exists, applied after the exact-verdict lookups and **before** `route.default`.
2. `_abstention_declared()` reports `cannot_judge_uncertain` as declared at a state
   declaring `on_cannot_judge` (or `route.routes["cannot_judge"]`), so it routes without a
   hold; the undeclared path is unchanged.
3. Both changes carry an inline `# BUG-3228:` comment at the precedence site, per the
   ENH-3185 commenting convention already in force in `_route()`/the dispatch block.
4. `uncertain_suffix`'s description in `fsm-loop-schema.json` (765-769) and the mirroring
   `EvaluateConfig` docstring (`schema.py:62`) state the fallback; `test_fsm_schema.py`
   lockstep passes.
5. `docs/generalized-fsm-loop.md` documents the fallback at the abstention prose block (547)
   and both `uncertain_suffix` examples (830-846, 1355-1365) reflect the new inheritance;
   `skills/create-loop/reference.md` notes suffixed keys are optional overrides.
6. The `error_uncertain` / non-retryable-exit-code-filter interaction (`executor.py:2055-2066`)
   is decided explicitly and recorded in the implementation, not left implicit.
7. `TestAbstentionRouting` covers the full matrix listed under Integration Map → Tests,
   including the route-table-with-default case and the unbounded-recursion guard;
   `test_cannot_judge_uncertain_undeclared_also_holds_then_falls_to_on_error` (2041) still
   passes unmodified.
8. `python -m pytest scripts/tests/test_fsm_executor.py scripts/tests/test_fsm_schema.py
   scripts/tests/test_builtin_loops.py -v` passes, and `ll-loop validate` runs clean across
   the built-in corpus.

## Impact

Makes `uncertain_suffix` usable for the first time and closes the `cannot_judge_uncertain`
gap across every gate the EPIC-3217 retrofit touches, without adding routing boilerplate to
any of them. Also closes the silent-misroute path for `route:`-table states, which today
absorbs low-confidence verdicts into the `_` default with no diagnostic.

## Related Key Documentation

- `docs/generalized-fsm-loop.md` — abstention routing contract (547) and the two
  `uncertain_suffix` worked examples (830-846, 1355-1365)
- `docs/reference/API.md` `little_loops.fsm.executor` — `_route()` / `_abstention_declared()`
- EPIC-3217 § Sequencing decision (a) — the resolution this issue implements

## Status

**Done** | Created: 2026-08-17 | Priority: P2


## Session Log
- `/ll:ready-issue` - 2026-08-17T03:05:14 - `d1871d6e-e254-4c9b-b1ed-7df263883c17.jsonl`
- `/ll:confidence-check` - 2026-08-17T03:01:39 - `950fed1e-dcee-4e9e-a142-297b86aebff5.jsonl`
