---
id: ENH-2164
type: ENH
priority: P3
status: done
discovered_date: 2026-06-15
discovered_by: capture-issue
captured_at: '2026-06-15T05:30:52Z'
completed_at: '2026-06-19T23:01:54Z'
parent: EPIC-2167
blocked_by: []
decision_needed: false
blocks:
- ENH-2166
- ENH-2233
- ENH-2234
relates_to:
- ENH-2165
- ENH-2166
- ENH-2154
- ENH-2233
- ENH-2234
confidence_score: 99
outcome_confidence: 80
score_complexity: 17
score_test_coverage: 20
score_ambiguity: 20
score_change_surface: 23
---

# ENH-2164: lib/policy-router Fragment — Rubric + Decision Table Gate

## Summary

Add `scripts/little_loops/loops/lib/policy-router.yaml` — a reusable fragment library implementing a **general decision-table router**: a declarative, priority-ordered rule table maps per-dimension scores → action state, enabling multi-axis routing without hand-coding per-dimension branches. Callers supply the dimensions, thresholds, and the decision table; the fragment handles parse → table-lookup → dispatch.

Per the resolved 2-layer design (see "Layering" below), this fragment is the
**general engine**, not merely a rubric extension: its rule grammar supports
**conjunctive (`&`-joined) predicates** and it accepts per-dimension scores from
**any scorer** (not only `lib/rubric-router`'s LLM `rubric_score`). `lib/rubric-router.yaml`
(ENH-2154) remains the thin single-aggregate preset. Routing handoff is done via
ENH-2165's `classify` evaluator + a `route:` table (the dispatch fragment emits the
winning action-state token; `classify` lifts it to the verdict; `route:` dispatches),
so this issue is **`blocked_by` ENH-2165**.

## Current Behavior

There is no shared primitive for multi-axis conditional routing in FSM-based automation loops. When a quality gate needs to route on **combinations** of dimension scores rather than a single aggregate, loops must choose between two inadequate options:

- Fan out into a cascade of single-dimension `exit_code` evaluator states per dimension — verbose and hard to maintain as the number of dimensions grows.
- Embed the routing logic in an LLM prompt — untestable and non-deterministic (the LLM may interpret the same scores differently across runs).

`lib/rubric-router.yaml` (ENH-2154) provides a 3-tier aggregate-score path (`high`/`medium`/`low`) but has no mechanism for routing on individual dimension combinations.

## Motivation

`lib/rubric-router.yaml` (ENH-2154) solved the per-loop boilerplate problem for the simple 3-tier (high/medium/low) aggregate-score case. But many real quality gates need to route on **combinations** of dimension scores, not just an aggregate:

- A plan with high *completeness* but low *feasibility* needs a different repair than one with low *completeness* and high *feasibility*.
- A doc with high *clarity* but low *coverage* should trigger a scope-expand repair, not a rewrite.
- A code review with critical *security* findings needs an escalation path regardless of aggregate score.

Today there is no shared primitive for multi-axis conditional routing. Every loop that needs it either (a) fans out into a cascade of single-dimension `exit_code` evaluator states (verbose, hard to maintain) or (b) embeds the logic in an LLM prompt (untestable, non-deterministic). A declarative Decision Table fragment makes multi-axis routing a first-class, auditable, and testable pattern.

**The concrete driver is extraction, not cascade-collapse.** ENH-2166 already collapsed `rn-remediate`'s multi-state `route_d_*` cascade onto a single `classify` + `route:` state — that consolidation is *done*. But the routing *decision* still lives as a hard-coded shell `if/elif` chain inside `diagnose` (`rn-remediate.yaml:241–266`): it cannot be unit-tested in isolation, cannot be reused by another loop, and cannot be inspected or edited as data. This engine's value is to **extract that inline `if/elif` into a reusable, auditable rule table** — a declarative `policy_rules` block parsed by a shared, independently-tested grammar module (`fsm/policy_rules.py`) that any loop can import and that ENH-2233's `edit-routes` lens can render and round-trip. The win is testability + reuse + data-level auditability of the routing logic, not collapsing states (that already happened).

## Relationship to ENH-2165, rn-remediate, and Conjunctive Rules

This issue's routing handoff (Implementation Step 4) is **blocked on ENH-2165**
(the `classify` evaluator). ENH-2165 adds a non-LLM evaluator whose verdict is the
action's trimmed stdout token, which — paired with the existing `route:` table
(`_route()` in `fsm/executor.py`) — lets `policy_table_dispatch` emit a winning
state name and dispatch to it in a single state. This is the clean third option
beyond Step 4's two alternatives:
- **(a) per-dimension `policy_route_<name>` exit-code fragments** — the verbose
  cascade; generates one routing state per action and is order-fragile.
- **(b) a `dynamic_next` executor convention** — underspecified; would require a
  bespoke executor change.
- **(c) `classify` + `route:` (ENH-2165)** — chosen direction; reuses machinery
  that already exists and keeps dispatch in one auditable state.

Adopt option (c) once ENH-2165 lands. Until then, this issue should not be
implemented with option (a)/(b), to avoid shipping a routing mechanism we intend
to replace.

### Grounding the rule grammar in a real router

`rn-remediate.yaml`'s `diagnose` state is a **shipping, battle-tested instance** of
exactly this decision-table pattern (priority-ordered, first-match-wins, multi-axis
routing over `confidence`/`outcome`/`complexity`/`ambiguity`/`change_surface`). It
should drive the v1 rule grammar so the abstraction is validated against a real
caller rather than the hypothetical security/clarity/feasibility examples above.
Two requirements it surfaces that the current v1 grammar does **not** yet cover:

1. **Conjunctive predicates.** Several `diagnose` rules AND multiple conditions —
   e.g. `confidence>=85 & outcome>=75 -> IMPLEMENT`, or
   `ambiguity>=15 & change_surface==0 -> WIRE`. The v1 `dim:op:value -> state`
   grammar is single-predicate. v1 must either support an `&`-joined conjunction
   per rule, or this issue must explicitly defer conjunctions and accept that
   `rn-remediate` cannot be migrated onto it yet.
2. **Score-source-agnosticism.** `diagnose` routes on **deterministic** scores read
   from `ll-issues show --json` (issue frontmatter), not an LLM-emitted `AGGREGATE`
   line. The policy-router as scoped is welded to `lib/rubric-router`'s LLM
   `rubric_score`. Consider whether `policy_table_dispatch` should accept
   pre-written per-dimension score files from **any** scorer (rubric, shell, or
   external) rather than only the rubric path.

### Layering: resolved to 2-layer (this issue IS the engine)

The layering fork was resolved in favor of a **2-layer stack** — no separate
`lib/decision-router` fragment is created. This issue **absorbs the general engine
role directly** (conjunctive rules + score-source-agnosticism, see below), and
`lib/rubric-router.yaml` (ENH-2154) remains the thin single-aggregate preset:

- **L0** — ENH-2165 `classify` evaluator (executor primitive; **blocks** this issue).
- **L1 (this issue)** — `lib/policy-router.yaml` as the general decision-table
  engine: source-agnostic per-dimension input, conjunctive (`&`-joined) rules,
  emits a token, routes via L0's `classify` + `route:`.
- **Preset** — `lib/rubric-router.yaml` (ENH-2154) = the degenerate single-aggregate
  / fixed-tier case; left unchanged.

Rationale: only one strong concrete driver (`rn-remediate`) plus this fragment
itself need the general grammar today, so extracting a separate L1 fragment would
be speculative (YAGNI). Collapsing the engine into `policy-router` keeps the stack
to two layers and one decision-table implementation. The `rn-remediate` migration
that exercises this engine is tracked separately (ENH-2166).

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

- [x] `scripts/little_loops/loops/lib/policy-router.yaml` exists and defines these named fragments:
  - `policy_table_dispatch` — `action_type: shell`; reads `${context.run_dir}/rubric-aggregate.txt` and per-dimension score files written by `rubric_parse_scores`; parses `${context.policy_rules}` rule table (top-to-bottom, first-match); writes the winning action state name to `${context.run_dir}/policy-action.txt`; prints `policy_action=<state>`; exits 0
  - `policy_table_dispatch` emits the winning action-state token on its final stdout line; the consuming state uses `evaluate: {type: classify}` (ENH-2165) + a `route:` table to dispatch to that state in one hop. No `policy_route_<name>` cascade and no `dynamic_next` executor convention (see "Layering" / ENH-2165). A `default:` route covers an unmatched/empty token.
- [x] Rule table syntax supports at minimum:
  - `<dim>:<op><value> -> <state>` where `<op>` ∈ `{>=, <=, ==, !=, <, >}` and `<dim>` is any dimension name from `rubric_dimensions` or the special token `aggregate`
  - **Conjunctive predicates** — multiple conditions joined with `&` in one rule, all of which must hold for the rule to match, e.g. `confidence:>=85 & outcome:>=75 -> implement`. This is required to express `rn-remediate`'s `diagnose` rules (ENH-2166) and is **in scope for v1**.
  - `* -> <state>` as a catch-all (must appear last)
  - **Numeric coercion** — comparison operators coerce both operands to numbers before comparing, so `"9" < "10"` evaluates `True` (numeric), not `False` (lexical). Non-numeric operands fall back to string comparison for `==` / `!=` only; ordered operators (`<`, `<=`, `>`, `>=`) on a non-numeric operand are a parse-time error.
- [x] **Shared grammar module** — the rule grammar's parse / serialize / evaluate logic lives in a **single importable module** `scripts/little_loops/fsm/policy_rules.py` (pure functions: `parse_rules(text) -> list[Rule]`, `serialize_rules(rules) -> str`, `evaluate_rules(rules, scores) -> str | None`), **not** inline in the fragment heredoc. The `policy_table_dispatch` fragment shells into it (using the `python3 << 'PYEOF'` heredoc pattern, the established convention). ENH-2233's `edit-routes` lens imports the same module, so the grammar has one source of truth and round-trips losslessly (`parse → serialize → parse` is stable).
- [x] **Score-source-agnostic input** — `policy_table_dispatch` reads per-dimension score files (`rubric-dim-<name>.txt`) and `rubric-aggregate.txt` from `${context.run_dir}/` regardless of which scorer wrote them. The rubric path (`policy_parse_scores` over `rubric_score` output) is one supported source; a caller may instead write those files from a shell/deterministic scorer (e.g. `rn-remediate`'s `ll-issues show --json`). The dispatch fragment does NOT hard-depend on `lib/rubric-router`'s LLM scoring path.
- [x] A parallel `policy_parse_scores` fragment is added in `lib/policy-router.yaml` that writes per-dimension score files (`rubric-dim-<name>.txt`) to `${context.run_dir}/` in addition to `rubric-aggregate.txt` — required for per-dimension rule evaluation. `lib/rubric-router.yaml` is left unchanged.
- [x] Fragment context variables (`policy_rules`) are documented with defaults and override behavior
- [x] `ll-loop validate policy-refine` passes with no errors or warnings (MR-1, MR-3, MR-4)
- [x] At least one runnable example loop (`loops/policy-refine.yaml`) imports both `lib/rubric-router.yaml` and `lib/policy-router.yaml` and exercises a multi-dimension decision table
- [x] `scripts/tests/test_builtin_loops.py` continues to pass after adding the fragment library and example loop
- [x] `scripts/tests/test_fsm_fragments.py` gains a `TestPolicyRouterLib` class asserting all fragment names are present and structured correctly; `scripts/tests/test_policy_rules.py` unit-tests the module functions — all documented operators, conjunctive `&`, catch-all `*`, **numeric-vs-lexical coercion** (`"9" < "10"` is `True`), and **`parse → serialize → parse` round-trip stability**

## Implementation Steps

1. **Decide whether to extend `rubric_parse_scores` or add `policy_parse_scores`** — extending is simpler (one fragment writes both aggregate and per-dim files) but changes the ENH-2154 fragment's contract; adding a parallel fragment keeps backward compatibility. Recommendation: add `policy_parse_scores` in `lib/policy-router.yaml` that wraps `rubric_parse_scores`'s output (or re-parses `captured.scores.output`) and additionally writes per-dimension score files.

2. **Implement `policy_parse_scores` shell action** — regex-extract all `DIMENSION: <score>` lines from `${captured.scores.output}`, write each to `${context.run_dir}/rubric-dim-<name>.txt` (lowercased name, spaces→hyphens). Reuse the `AGGREGATE` extraction from `rubric_parse_scores`.

3. **Implement the rule grammar as a shared module** — create `scripts/little_loops/fsm/policy_rules.py` with pure functions: `parse_rules(text) -> list[Rule]` (each `Rule` carries an ordered list of `(dim, op, value)` predicates + target state, or a catch-all marker; preserves source order), `serialize_rules(rules) -> str` (lossless inverse), and `evaluate_rules(rules, scores: dict[str, float]) -> str | None` (first-match-wins; numeric coercion per operator). Then **`policy_table_dispatch` shell action** loads the score files (`rubric-aggregate.txt` → `aggregate`, `rubric-dim-<dim>.txt` → named dims) into a dict and calls `python3 -c "from little_loops.fsm.policy_rules import parse_rules, evaluate_rules; ..."` — **no parsing/evaluation logic in the heredoc.** On match, write the state name to `${context.run_dir}/policy-action.txt` and print it as the final stdout line; unmatched + no `*` → empty line (falls to `route.default`). Rationale: ENH-2233's `edit-routes` imports this exact module, so the grammar is defined, parsed, and serialized in one place.

4. **Design routing handoff** — because the FSM executor routes via `on_yes`/`on_no`/`route:`, the fragment cannot dynamically redirect to an arbitrary state name via shell exit code alone. Two options: (a) `policy_table_dispatch` writes the action name and the consuming loop reads it via individual `policy_route_<name>` exit-code fragments; (b) introduce a `dynamic_next` convention where the shell writes a state name to a well-known path and the executor reads it. Evaluate what the FSM executor supports today and pick the cleanest fit. Document the chosen approach in the fragment file header.

5. **Create `loops/policy-refine.yaml`** — multi-dimension example (clarity/completeness/feasibility/security) with a non-trivial policy table covering ≥ 4 rules including a per-dimension rule and a catch-all.

6. **Update `loops/README.md`** — list `lib/policy-router.yaml` and its exported fragments.

7. **Add tests** — `TestPolicyRouterLib` in `scripts/tests/test_fsm_fragments.py` (fragment-name + structure assertions, `${context.run_dir}` usage, `resolve_fragments()` integration); plus `scripts/tests/test_policy_rules.py` covering the module directly: `parse_rules` / `serialize_rules` / `evaluate_rules` across all operators, conjunctive `&`, catch-all, numeric coercion (`"9" < "10"`), ordered-op-on-non-numeric parse error, and round-trip stability.

8. **Validate and test** — `ll-loop validate lib/policy-router.yaml`, then `python -m pytest scripts/tests/` passing.

### Codebase Research Findings

_Added by `/ll:refine-issue` — concrete implementation guidance:_

**Step 1 (parse fragment decision):** Add `policy_parse_scores` as a new fragment in `lib/policy-router.yaml`. Do NOT extend `rubric_parse_scores` in `lib/rubric-router.yaml` (ENH-2154) — extending breaks the predecessor's contract. `policy_parse_scores` re-parses `${captured.scores.output}` (same source as `rubric_parse_scores`) and additionally writes per-dimension files.

**Step 2 (policy_parse_scores shell action):** Follow the Python heredoc pattern from `lib/rubric-router.yaml:rubric_parse_scores`. Regex pattern for aggregate: `re.search(r'AGGREGATE:\s*(\d+)', output)`. Per-dimension: iterate lines matching `r'(\w[\w\s]+):\s*(\d+)'`, exclude `AGGREGATE`, lowercaseify name + replace spaces with hyphens → write to `${context.run_dir}/rubric-dim-<name>.txt`. The `rubric_parse_scores` aggregate extraction + file write is the exact template; extend it.

**Step 3 (shared module + policy_table_dispatch):** Put parse/serialize/evaluate in `scripts/little_loops/fsm/policy_rules.py` — NOT in a heredoc — so ENH-2233's `edit-routes` can import the same grammar. Functions: `parse_rules(text)` skips blank/comment lines; rule = `<dim>:<op><value> -> <state>` (single) or `<dim>:<op><value> & <dim2>:<op2><value2> -> <state>` (conjunctive), with `* -> <state>` catch-all; `serialize_rules` is the lossless inverse (preserves order); `evaluate_rules(rules, scores)` coerces operands to `float` for `<`,`<=`,`>`,`>=` (numeric, so `"9" < "10"`), falls back to string compare for `==`/`!=` only, first-match-wins. The fragment's shell action loads score files (`${context.run_dir}/rubric-aggregate.txt` → `aggregate`, `rubric-dim-<dim>.txt` → named dims) into a dict and shells `python3 -c "from little_loops.fsm.policy_rules import parse_rules, evaluate_rules; ..."` (cf. `auto-refine-and-implement.yaml:33` for the import-from-package precedent). On first match: `print(state_name)` on last stdout line, exit 0; no match + no catch-all → empty line (falls to `route.default`).

**Step 4 (routing handoff — RESOLVED):** ENH-2165 is `done`. `classify` evaluator is live at `evaluators.py:evaluate_classify()` (line 416). Use option (c): `policy_table_dispatch` prints the winning state token as its last stdout line; the consuming loop state uses `evaluate: {type: classify}` + `route:` table to dispatch. Required: include `default:` in the `route:` table or `ll-loop validate` will emit WARNING (`validation.py:_validate_classify_route_default()` line 1564). The `route.routes[verdict]` lookup in `executor.py:_route()` (line 1367) handles dispatch.

**Step 7 (tests):** `TestPolicyRouterLib` models directly after `test_fsm_fragments.py:TestRubricRouterLib` (line 2178) — fragment name assertions (`policy_parse_scores`, `policy_table_dispatch`); `action_type: shell` for both; `description` presence; `${context.run_dir}` in action text; `resolve_fragments()` integration test using real `loops_dir`. Separately, `scripts/tests/test_policy_rules.py` unit-tests the module: operators `>=`,`<=`,`==`,`!=`,`<`,`>`, catch-all `*`, conjunctive `&`, numeric coercion (`"9" < "10"` → True), ordered-op-on-non-numeric raises at parse time, and `parse → serialize → parse` round-trip stability.

**rn-remediate.yaml migration path (ENH-2166 — done; reframed as extraction):** ENH-2166 is complete and the 5-state `route_d_*` cascade no longer exists — `diagnose` (now `rn-remediate.yaml:208`) already dispatches in one hop via `evaluate: {type: classify}` + a `route:` table (lines 267–277). The state-collapse this fragment was framed to deliver has therefore already happened *inline*. What remains, and what this engine actually delivers, is **extracting `diagnose`'s hard-coded `if/elif` token-emit chain (lines 241–266) into a declarative, caller-supplied `policy_rules` table** parsed by `fsm/policy_rules.py`. That extraction is the future migration step (out of scope here; tracked as a follow-on) — and it is precisely why the v1 grammar must support conjunctive `&` predicates and score-source-agnostic input, since `diagnose`'s rules use both (`confidence:>=N & outcome:>=M`, scores from `ll-issues show --json`).

## Scope Boundaries

- **In scope**: `lib/policy-router.yaml` as the general decision-table engine — `policy_parse_scores` and `policy_table_dispatch` fragments; **conjunctive (`&`) rules**; **score-source-agnostic** per-dimension input; `classify`-based routing handoff (consumes ENH-2165); one runnable example loop (`policy-refine.yaml`); `loops/README.md` update; `TestPolicyRouterLib` in `test_fsm_fragments.py`
- **Out of scope**: the `classify` evaluator itself (ENH-2165 — a dependency, not part of this issue); migrating existing loops onto the engine (`rn-remediate` migration is ENH-2166; other loops are separate follow-ons); a separate `lib/decision-router` fragment (the 2-layer decision folds the engine into this issue); changes to the FSM executor schema or core beyond what ENH-2165 provides; defining domain-specific decision tables; nested/parenthesized boolean rules or `|`-disjunction within a single rule (use multiple rows for OR) in v1; probabilistic or weighted rules

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
- `scripts/little_loops/fsm/policy_rules.py` (new — shared rule grammar: `parse_rules` / `serialize_rules` / `evaluate_rules`; single source of truth imported by both the fragment and ENH-2233's edit-routes)
- `scripts/little_loops/loops/lib/policy-router.yaml` (new — fragment library; `policy_table_dispatch` shells into `policy_rules`)
- `scripts/little_loops/loops/policy-refine.yaml` (new — runnable example loop)
- `scripts/little_loops/loops/README.md` (update — add policy-router to lib listing)
- `scripts/tests/test_fsm_fragments.py` (update — add `TestPolicyRouterLib`)
- `scripts/tests/test_policy_rules.py` (new — unit tests for the grammar module)

### Dependencies
- `scripts/little_loops/loops/lib/rubric-router.yaml` (ENH-2154) — must be imported alongside; `policy_parse_scores` consumes `captured.scores.output` written by `rubric_score`

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/edit_routes.py` + `fsm/route_table.py` — **future** (ENH-2233) importers of `fsm/policy_rules.py`; this issue must expose the grammar as an importable module, not heredoc-local logic, to unblock that lens

### Similar Patterns
- `scripts/little_loops/loops/lib/rubric-router.yaml` — direct predecessor; follow same `fragments:` block conventions
- `scripts/little_loops/loops/loop-router.yaml` — reference for `route_branch_*` exit-code evaluator pattern
- `scripts/little_loops/loops/lib/common.yaml` — canonical fragment library structure

### Tests
- `scripts/tests/test_builtin_loops.py` — `policy-refine.yaml` must pass the universal `TestBuiltinLoopFiles` fixture; `lib/policy-router.yaml` excluded by `is_runnable_loop()`
- `scripts/tests/test_fsm_fragments.py` — `TestPolicyRouterLib`: assert fragment names + structure
- `scripts/tests/test_policy_rules.py` — grammar module: all operators, conjunctive `&`, catch-all, numeric coercion (`"9" < "10"`), round-trip stability

### Documentation
- `scripts/little_loops/loops/README.md` — list `lib/policy-router.yaml` and its exported fragment names
- `docs/guides/LOOPS_GUIDE.md` — candidate for a "Policy-Based Routing" pattern section once shipped (follow-on)

### Configuration
- N/A — no config files changed; fragment context variables are caller-supplied

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**FSM executor anchor references:**
- `scripts/little_loops/fsm/evaluators.py:evaluate_classify()` (line 416) — `classify` evaluator is fully implemented; filters to non-empty lines, selects by `config.line` (`"last"` default), returns trimmed token as verdict
- `scripts/little_loops/fsm/schema.py:EvaluateConfig` (line 94) — `line: str | int | None = None` field controls which line `classify` reads (`"last"`, `"first"`, or integer index)
- `scripts/little_loops/fsm/executor.py:_route()` (line 1367) — `route:` table lookup order: `routes[verdict]` → `route.default` → `route.error`; empty-string verdict falls to `default`
- `scripts/little_loops/fsm/validation.py:_validate_classify_route_default()` (line 1564) — emits WARNING when a `classify` state's `route:` table has no `default:` fallback; must satisfy this to pass `ll-loop validate`
- `scripts/little_loops/fsm/validation.py:is_runnable_loop()` (line 1999) — lib/ files (which have only `fragments:`, no `name:`/`initial:`/`states:`) return `False` automatically; no special-casing needed

**Test pattern anchor:**
- `scripts/tests/test_fsm_fragments.py:TestRubricRouterLib` (line 2178) — exact model for `TestPolicyRouterLib`; covers fragment name assertions, `action_type` checks, evaluator type checks, `description` presence, `${context.run_dir}` usage in action, `resolve_fragments()` integration test

**Real-world caller (rn-remediate.yaml) anchor:**
- `scripts/little_loops/loops/rn-remediate.yaml:diagnose` (line 204) — the shipping multi-axis decision-table pattern; emits one token (`IMPLEMENT`/`DECIDE`/`WIRE`/`REFINE`/`DECOMPOSE`) via priority-ordered `if/elif` chain reading `ll-issues show --json` scores; followed by a cascade of 5 `route_d_*` `output_contains` states (lines ~270–320) that `policy_table_dispatch` + `classify` would collapse to 1 state

**ENH-2165 blocker resolved:**
- `classify` evaluator (ENH-2165) status is `done`; `evaluate_classify()` is live at `evaluators.py:416` — this issue is no longer blocked

### Codebase Research Findings (2026-06-19 refine pass)

_Added by `/ll:refine-issue --auto` — re-validated anchors against current `main` and folded in the now-`done` ENH-2166:_

**Greenfield confirmed.** None of the target artifacts exist yet — `scripts/little_loops/fsm/policy_rules.py`, `scripts/little_loops/loops/lib/policy-router.yaml`, `scripts/little_loops/loops/policy-refine.yaml`, `scripts/tests/test_policy_rules.py` are all absent. `lib/rubric-router.yaml` (ENH-2154) is present (`loops/lib/rubric-router.yaml`). The issue is correctly unimplemented; this is a clean build.

**Anchor drift — line numbers moved since the 2026-06-16 pass; corrected references:**
- `_route()` — `executor.py:1367` → now **`executor.py:1469`** (the route-table lookup logic is unchanged; only the line moved).
- `_validate_classify_route_default()` — `validation.py:1564` → now **`validation.py:1574`** (called from `validation.py:1055`).
- `is_runnable_loop()` — `validation.py:1999` → now **`validation.py:2032`**.
- Shell-action capture `{"output": <str>}` — the reopening note cited `executor.py:713`, but line 713/714 captures *child-events*. The shell-action stdout capture relevant to `policy_table_dispatch` is **`executor.py:1268`** (`"output": result.output.rstrip("\n\r")`). Confirms `classify` reads from the trimmed shell stdout.
- Still accurate (no change): `evaluate_classify()` @ `evaluators.py:416`; `EvaluateConfig.line` field @ `schema.py:94`; `TestRubricRouterLib` @ `test_fsm_fragments.py:2178`.

**ENH-2166 is `done`, but it did NOT extract a shared engine — it inlined `classify` + `route:`.** This supersedes the "5-state cascade this fragment replaces" framing in the Implementation Steps findings above (line ~246) and in the reopening narrative. Current state of `rn-remediate.yaml`:
- The 5-state `route_d_implement → route_d_decide → route_d_wire → route_d_refine → …` cascade **no longer exists** — grep for `route_d_` returns nothing.
- `diagnose` (now **line 208**, not 204) emits a token via an inline shell `if/elif` chain (lines 241–266) and dispatches in a single state via `evaluate: {type: classify}` (line 267) + a `route:` table (lines 269–277, with `_:` and `_error:` fallbacks → `emit_implement_failed`). The cascade-collapse this issue promised is therefore already realized inline by ENH-2166.

**The live value of this issue for rn-remediate is now extraction, not collapse.** `diagnose`'s inline `if/elif` chain is exactly the rule table `policy_rules` should express declaratively. Its rules map 1:1 onto the conjunctive v1 grammar and are the concrete proof the in-scope features are required:
- `confidence >= READINESS & outcome >= OUTCOME -> IMPLEMENT` → `confidence:>=85 & outcome:>=75 -> IMPLEMENT` (validates **conjunctive `&`**).
- `ambiguity >= N & change_surface == 0 -> WIRE`, and `complexity >= N & change_surface == 0 -> WIRE` (more conjunctions).
- Scores come from `ll-issues show --json` parsed in shell (lines 217–233) — **not** an LLM `AGGREGATE` line — validating the **score-source-agnostic** AC: `policy_table_dispatch` must read per-dimension files written by *any* scorer, not hard-depend on `rubric_score`. (Note rn-remediate routes on `decision_needed`/`missing_artifacts` string flags too; the v1 `==`/`!=` string-compare fallback covers these.)
- The future migration that swaps this inline chain for an imported `policy_rules` table is a follow-on (the issue already scopes the rn-remediate migration as out-of-scope here); ENH-2166 having shipped the inline form does not block building the reusable engine.

**`auto-refine-and-implement.yaml` import precedent** — the cited "import-from-package" pattern (issue line 205/220) is at `auto-refine-and-implement.yaml:30–33`, which uses a `python3 << 'PYEOF'` heredoc importing `from little_loops.config import BRConfig`, not a `python3 -c` one-liner. Either form works for shelling into `little_loops.fsm.policy_rules`; the heredoc form is the established convention for multi-line logic.

## Related Key Documentation

- [`scripts/little_loops/loops/lib/rubric-router.yaml`](../../scripts/little_loops/loops/lib/rubric-router.yaml) — direct predecessor (ENH-2154); policy-router imports and builds on it
- [`scripts/little_loops/loops/lib/common.yaml`](../../scripts/little_loops/loops/lib/common.yaml) — canonical fragment library structure to follow
- [`scripts/little_loops/loops/loop-router.yaml`](../../scripts/little_loops/loops/loop-router.yaml) — reference for `parse_*_score` and `route_branch_*` shell patterns
- [`docs/guides/LOOPS_GUIDE.md`](../../docs/guides/LOOPS_GUIDE.md) — loop authoring guide

## Labels

`enh`, `loops`, `fsm`, `dx`, `fragments`

## Status

**Open** | Created: 2026-06-15 | Priority: P3

---

## Reopened

- **Date**: 2026-06-19
- **By**: capture-issue
- **Reason**: Un-deferred — EPIC-2167's "prove before mandate" gate is now met.

### New Findings

EPIC-2167 deliberately deferred this general engine until the pattern was validated
on a real loop. That gate is now satisfied: **ENH-2166** (migrate `rn-remediate`'s
routing cascades onto `classify` + decision-table) is `done`, and the `classify`
evaluator (ENH-2165) is live (`evaluators.py:416`). The general conjunctive engine is
therefore ripe to build.

Two considerations surfaced in a design discussion that this issue should fold in:

1. **Typed inputs / coercion.** Captured values are stored stringified
   (`executor.py:713` stores `{"output": <str>}`). The rule matcher should treat
   numeric comparisons as numeric (not lexical string) comparisons — the parser
   already coerces `value` per-operator, but document this explicitly and add a test
   for `"9" < "10"` numeric-vs-string correctness.
2. **Optional `expr:` escape hatch (consider, not required for v1).** The locked
   grammar is conjunctive (`&`-joined) predicates, first-match-wins. A future
   extension could allow a single per-rule free expression for predicates the
   `dim:op:value` grammar can't express — opt-in, kept off the common path. Track
   under the operator-registry follow-on (ENH-2234) if pursued.

**Companion issue:** ENH-2233 covers surfacing/authoring these compound tables
through `ll-loop edit-routes` (rendering, round-trip, dimension columns) — the engine
here is the backend; ENH-2233 is the editing lens. ENH-2234 (deferred) tracks a
pluggable operator registry layered on this engine's matcher vocabulary.

## Session Log
- `/ll:ready-issue` - 2026-06-19T22:47:15 - `afb38a86-6126-4fbd-862c-920c11753052.jsonl`
- `/ll:confidence-check` - 2026-06-19T00:00:00Z - `9a628d90-212b-42dc-822d-72440bfc7b5b.jsonl`
- `/ll:refine-issue` - 2026-06-19T22:39:52 - `2b7e645d-a1c7-4882-a697-d45ec064bbac.jsonl`
- `/ll:confidence-check` - 2026-06-19T00:00:00Z - `ff830b15-e3cc-4c8e-b1f0-0192a42c6323.jsonl`
- `/ll:capture-issue` - 2026-06-19T21:56:31Z - `7ad4c299-a78e-4069-93e8-64dd478cf18b.jsonl`
- `/ll:confidence-check` - 2026-06-15T00:00:00Z - `36f09c2f-8598-41e8-8022-29d032bf584b.jsonl`
- `/ll:refine-issue` - 2026-06-16T01:05:37 - `4868c01f-d653-4e88-92f4-0dfdaf0947d0.jsonl`
- `/ll:confidence-check` - 2026-06-15T00:00:00Z - `534b43f7-8b8b-4649-8a48-fd91433994bd.jsonl`
- `/ll:format-issue` - 2026-06-15T05:36:08 - `812e5bd7-abf8-4165-8311-64bd345e60ff.jsonl`
- `/ll:capture-issue` - 2026-06-15T05:30:52Z - `bcc19f01-efdb-45bc-a50b-ec443da22f83.jsonl`
