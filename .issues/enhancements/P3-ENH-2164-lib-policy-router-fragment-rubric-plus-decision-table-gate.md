---
id: ENH-2164
type: ENH
priority: P3
status: open
discovered_date: 2026-06-15
discovered_by: capture-issue
captured_at: '2026-06-15T05:30:52Z'
parent: ENH-2154
---

# ENH-2164: lib/policy-router Fragment — Rubric + Decision Table Gate

## Summary

Add `scripts/little_loops/loops/lib/policy-router.yaml` — a reusable fragment library that extends `lib/rubric-router.yaml` with a **Decision Table** gate: after a rubric scores an artifact, a declarative rule table maps (dimension, tier) → action, enabling multi-axis routing without hand-coding per-dimension branches. Callers supply the rubric dimensions, thresholds, and the decision table; the fragment handles score → parse → table-lookup → dispatch.

## Motivation

`lib/rubric-router.yaml` (ENH-2154) solved the per-loop boilerplate problem for the simple 3-tier (high/medium/low) aggregate-score case. But many real quality gates need to route on **combinations** of dimension scores, not just an aggregate:

- A plan with high *completeness* but low *feasibility* needs a different repair than one with low *completeness* and high *feasibility*.
- A doc with high *clarity* but low *coverage* should trigger a scope-expand repair, not a rewrite.
- A code review with critical *security* findings needs an escalation path regardless of aggregate score.

Today there is no shared primitive for multi-axis conditional routing. Every loop that needs it either (a) fans out into a cascade of single-dimension `exit_code` evaluator states (verbose, hard to maintain) or (b) embeds the logic in an LLM prompt (untestable, non-deterministic). A declarative Decision Table fragment makes multi-axis routing a first-class, auditable, and testable pattern.

## Expected Behavior

A project loop imports the policy-router fragment and declares a decision table in context:

```yaml
name: my-policy-loop
import:
  - lib/rubric-router.yaml
  - lib/policy-router.yaml

context:
  subject: "path/to/artifact.md"
  rubric_dimensions: "clarity|completeness|feasibility|security"
  threshold_high: "85"
  threshold_medium: "60"
  # Decision table: list of rules evaluated top-to-bottom; first match wins
  # Format: "dim:op:value -> action_state"
  # Operators: >=, <=, ==, !=, <, >
  policy_rules: |
    security:<65 -> escalate
    completeness:<60 -> deep_repair
    feasibility:<60 -> rethink
    aggregate:>=85 -> done
    aggregate:>=60 -> light_repair
    * -> deep_repair

states:
  start:
    fragment: rubric_score
    action: |
      Evaluate ${context.subject} on: ${context.rubric_dimensions}.
      For each dimension output: DIMENSION: <score 0-100>
      Final line: AGGREGATE: <int 0-100>
    capture: scores
    next: rubric_parse

  rubric_parse:
    fragment: rubric_parse_scores
    next: policy_dispatch

  policy_dispatch:
    fragment: policy_table_dispatch
    # Routes to the state named in the matching rule's action_state

  escalate:
    action_type: prompt
    action: "Escalate ${context.subject} to security review."
    next: done

  light_repair:
    action_type: prompt
    action: "Apply light refinements to ${context.subject}. Scores: ${captured.scores.output}"
    next: start

  deep_repair:
    action_type: prompt
    action: "Apply comprehensive repairs to ${context.subject}. Scores: ${captured.scores.output}"
    next: start

  rethink:
    action_type: prompt
    action: "Rethink the approach for ${context.subject}. Feasibility is low."
    next: start

  done:
    terminal: true
```

The fragment reads `context.policy_rules`, parses the rule table, evaluates each rule against the per-dimension scores and aggregate written by `rubric_parse_scores`, and `exec`s (or writes) the matching action state name so the FSM router knows where to go next.

## Acceptance Criteria

- [ ] `scripts/little_loops/loops/lib/policy-router.yaml` exists and defines these named fragments:
  - `policy_table_dispatch` — `action_type: shell`; reads `${context.run_dir}/rubric-aggregate.txt` and per-dimension score files written by `rubric_parse_scores`; parses `${context.policy_rules}` rule table (top-to-bottom, first-match); writes the winning action state name to `${context.run_dir}/policy-action.txt`; prints `policy_action=<state>`; exits 0
  - `policy_route` — `action_type: shell` + `evaluate: exit_code`; reads `${context.run_dir}/policy-action.txt`; FSM caller uses `on_yes`/`on_no` or a `route:` table — fragment exports `policy_action.txt` content to allow caller state-based routing via a shell `case` dispatch or via individual `policy_route_<name>` fragments
- [ ] Rule table syntax supports at minimum:
  - `<dim>:<op><value> -> <state>` where `<op>` ∈ `{>=, <=, ==, !=, <, >}` and `<dim>` is any dimension name from `rubric_dimensions` or the special token `aggregate`
  - `* -> <state>` as a catch-all (must appear last)
- [ ] `rubric_parse_scores` (from `lib/rubric-router.yaml`) is extended **or** a parallel `policy_parse_scores` fragment is added that writes per-dimension score files (`rubric-dim-<name>.txt`) to `${context.run_dir}/` in addition to `rubric-aggregate.txt` and `rubric-tier.txt` — required for per-dimension rule evaluation
- [ ] Fragment context variables (`policy_rules`) are documented with defaults and override behavior
- [ ] `ll-loop validate` passes on `lib/policy-router.yaml` with no errors or warnings (MR-1, MR-3, MR-4)
- [ ] At least one runnable example loop (`loops/policy-refine.yaml`) imports both `lib/rubric-router.yaml` and `lib/policy-router.yaml` and exercises a multi-dimension decision table
- [ ] `scripts/tests/test_builtin_loops.py` continues to pass after adding the fragment library and example loop
- [ ] `scripts/tests/test_fsm_fragments.py` gains a `TestPolicyRouterLib` class asserting all fragment names are present and the rule-parser handles the documented operators and catch-all correctly

## Implementation Steps

1. **Decide whether to extend `rubric_parse_scores` or add `policy_parse_scores`** — extending is simpler (one fragment writes both aggregate and per-dim files) but changes the ENH-2154 fragment's contract; adding a parallel fragment keeps backward compatibility. Recommendation: add `policy_parse_scores` in `lib/policy-router.yaml` that wraps `rubric_parse_scores`'s output (or re-parses `captured.scores.output`) and additionally writes per-dimension score files.

2. **Implement `policy_parse_scores` shell action** — regex-extract all `DIMENSION: <score>` lines from `${captured.scores.output}`, write each to `${context.run_dir}/rubric-dim-<name>.txt` (lowercased name, spaces→hyphens). Reuse the `AGGREGATE` extraction from `rubric_parse_scores`.

3. **Implement `policy_table_dispatch` shell action** — parse `${context.policy_rules}` line by line; for each rule parse `dim:op:value -> state`; load the appropriate score file (`rubric-aggregate.txt` for `aggregate`, `rubric-dim-<dim>.txt` for a named dimension); evaluate the condition; on first match write the state name to `${context.run_dir}/policy-action.txt` and exit 0. Handle `* -> <state>` as the default catch-all.

4. **Design routing handoff** — because the FSM executor routes via `on_yes`/`on_no`/`route:`, the fragment cannot dynamically redirect to an arbitrary state name via shell exit code alone. Two options: (a) `policy_table_dispatch` writes the action name and the consuming loop reads it via individual `policy_route_<name>` exit-code fragments; (b) introduce a `dynamic_next` convention where the shell writes a state name to a well-known path and the executor reads it. Evaluate what the FSM executor supports today and pick the cleanest fit. Document the chosen approach in the fragment file header.

5. **Create `loops/policy-refine.yaml`** — multi-dimension example (clarity/completeness/feasibility/security) with a non-trivial policy table covering ≥ 4 rules including a per-dimension rule and a catch-all.

6. **Update `loops/README.md`** — list `lib/policy-router.yaml` and its exported fragments.

7. **Add `TestPolicyRouterLib`** to `scripts/tests/test_fsm_fragments.py` — assert all fragment names present; unit-test the rule parser Python logic extracted into a helper function.

8. **Validate and test** — `ll-loop validate lib/policy-router.yaml`, then `python -m pytest scripts/tests/` passing.

## Scope Boundaries

- **In scope**: `lib/policy-router.yaml` with `policy_parse_scores` and `policy_table_dispatch` fragments; `policy_route` helper; one runnable example loop (`policy-refine.yaml`); `loops/README.md` update; `TestPolicyRouterLib` in `test_fsm_fragments.py`
- **Out of scope**: Migrating existing loops to use the policy router; changes to the FSM executor schema or core; defining domain-specific decision tables; more than two-level rule nesting in v1; probabilistic or weighted rules

## Impact

- **Priority**: P3 — Reduces boilerplate for multi-axis routing; no blocking dependency
- **Effort**: Medium — More complex than ENH-2154 (requires decision-table parser, per-dim score files, routing handoff design); ~1–2 days
- **Risk**: Medium — The routing handoff mechanism (step 4) requires a design decision about FSM executor capabilities; if `dynamic_next` is not supported, per-dimension `policy_route_<name>` fragments generate verbose caller YAML
- **Breaking Change**: No — pure additive; ENH-2154 artifacts unchanged unless `rubric_parse_scores` is extended

## API/Interface

New fragment library: `scripts/little_loops/loops/lib/policy-router.yaml`

Expected context variables (provided by importing loop):
- `context.policy_rules` — newline-separated rule table (see rule syntax above)
- `context.rubric_dimensions` — pipe-separated dimension names (same as `lib/rubric-router.yaml`)
- `context.threshold_high` / `context.threshold_medium` — inherited from `lib/rubric-router.yaml` (default 85 / 65)
- `context.run_dir` — injected by runner

Fragment names exported:
- `policy_parse_scores`
- `policy_table_dispatch`
- `policy_route` (optional helper; design TBD based on executor capabilities)

Per-run artifact files written:
- `${context.run_dir}/rubric-dim-<name>.txt` — per-dimension score (integer)
- `${context.run_dir}/policy-action.txt` — winning action state name

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/lib/policy-router.yaml` (new — fragment library)
- `scripts/little_loops/loops/policy-refine.yaml` (new — runnable example loop)
- `scripts/little_loops/loops/README.md` (update — add policy-router to lib listing)
- `scripts/tests/test_fsm_fragments.py` (update — add `TestPolicyRouterLib`)

### Dependencies
- `scripts/little_loops/loops/lib/rubric-router.yaml` (ENH-2154) — must be imported alongside; `policy_parse_scores` consumes `captured.scores.output` written by `rubric_score`

### Similar Patterns
- `scripts/little_loops/loops/lib/rubric-router.yaml` — direct predecessor; follow same `fragments:` block conventions
- `scripts/little_loops/loops/loop-router.yaml` — reference for `route_branch_*` exit-code evaluator pattern
- `scripts/little_loops/loops/lib/common.yaml` — canonical fragment library structure

### Tests
- `scripts/tests/test_builtin_loops.py` — `policy-refine.yaml` must pass the universal `TestBuiltinLoopFiles` fixture; `lib/policy-router.yaml` excluded by `is_runnable_loop()`
- `scripts/tests/test_fsm_fragments.py` — `TestPolicyRouterLib`: assert fragment names, test rule-parser helper with all operators and catch-all

### Documentation
- `scripts/little_loops/loops/README.md` — list `lib/policy-router.yaml` and its exported fragment names
- `docs/guides/LOOPS_GUIDE.md` — candidate for a "Policy-Based Routing" pattern section once shipped (follow-on)

## Related Key Documentation

- [`scripts/little_loops/loops/lib/rubric-router.yaml`](../../scripts/little_loops/loops/lib/rubric-router.yaml) — direct predecessor (ENH-2154); policy-router imports and builds on it
- [`scripts/little_loops/loops/lib/common.yaml`](../../scripts/little_loops/loops/lib/common.yaml) — canonical fragment library structure to follow
- [`scripts/little_loops/loops/loop-router.yaml`](../../scripts/little_loops/loops/loop-router.yaml) — reference for `parse_*_score` and `route_branch_*` shell patterns
- [`docs/guides/LOOPS_GUIDE.md`](../../docs/guides/LOOPS_GUIDE.md) — loop authoring guide

## Labels

`enh`, `loops`, `fsm`, `dx`, `fragments`

## Status

**Open** | Created: 2026-06-15 | Priority: P3

## Session Log
- `/ll:capture-issue` - 2026-06-15T05:30:52Z - `bcc19f01-efdb-45bc-a50b-ec443da22f83.jsonl`
