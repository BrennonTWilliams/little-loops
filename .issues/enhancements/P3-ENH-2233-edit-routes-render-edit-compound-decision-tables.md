---
id: ENH-2233
type: ENH
priority: P3
status: open
discovered_date: '2026-06-19'
discovered_by: capture-issue
captured_at: '2026-06-19T21:56:31Z'
decision_needed: false
depends_on:
- ENH-2164
relates_to:
- ENH-2164
- ENH-2227
- ENH-2228
- EPIC-2167
confidence_score: 98
outcome_confidence: 85
score_complexity: 18
score_test_coverage: 23
score_ambiguity: 22
score_change_surface: 22
---

# ENH-2233: edit-routes — render and edit compound (multi-dimension) decision tables

## Summary

`ll-loop edit-routes` renders routing as a **state × verdict** matrix only. It cannot
show or edit the **compound, multi-dimension decision tables** that `lib/policy-router`
(ENH-2164) expresses — where a routing decision depends on a *conjunction of scored
dimensions* (e.g. `confidence>=85 & outcome>=75 -> implement`). This issue adds a
decision-table lens to `edit-routes` that renders a policy-router rule table as a true
condition-columns × action grid and round-trips edits back to the loop's
`context.policy_rules`.

## Motivation

The original framing that surfaced this: a user wanted `edit-routes` to express
"if readiness is in range X **and** complexity is above threshold Y, route to refine."
That capability is exactly what ENH-2164's engine provides — but `edit-routes` is the
**only authoring surface most users touch**, and it deliberately scoped compound
conditions *out* (ENH-2227 § Scope Boundaries; ENH-2228 likewise). So today the
generalized engine, once built, has **no editing lens** — its rule table lives as a
newline-separated `context.policy_rules` string that must be hand-edited in raw YAML.

A decision-table view collapses an N-dimension policy table into one readable grid
(condition columns = dimensions, each row = one conjunctive rule, first-match-wins,
final column = action state). This makes gaps, shadowed rules (an earlier row that
masks a later one), and missing catch-alls visible at a glance — the same value
ENH-2227 delivered for the simpler verdict matrix.

## Current Behavior

- `ll-loop edit-routes <loop>` (shipped via ENH-2227, extended by ENH-2228) extracts
  `route:` / `on_*` / `extra_routes` across states and renders a state × verdict
  matrix. It has no awareness of `context.policy_rules` or the policy-router fragment.
- A loop using `lib/policy-router` (ENH-2164) carries its decision logic in a
  `context.policy_rules` string (`dim:op:value [& dim:op:value] -> state`, `* -> state`
  catch-all). `edit-routes` shows only the single `classify` dispatch state's verdict
  arms — not the rule table that actually drives the decision.

## Expected Behavior

When a loop imports `lib/policy-router` and defines `context.policy_rules`,
`ll-loop edit-routes <loop> --decision-table` (or auto-detected) renders a compound grid:

```
| #  | confidence | outcome | security | aggregate | → action     |
|----|------------|---------|----------|-----------|--------------|
| 1  | —          | —       | <65      | —         | escalate     |
| 2  | >=85       | >=75    | —        | —         | implement    |
| 3  | —          | —       | —        | >=85      | done         |
| 4  | —          | —       | —        | >=60      | light_repair |
| 5  | *          | *       | *        | *         | deep_repair  |
```

1. Parse `context.policy_rules` into rows; the column set is the union of dimensions
   referenced across all rules (plus `aggregate`). Empty cell = dimension unconstrained
   in that rule (rendered `—`); `*` row = catch-all.
2. Edit in `$EDITOR` / CSV / markdown, mirroring ENH-2227's flow.
3. On save, serialize the grid back to the `dim:op:value & ... -> state` rule syntax and
   write it to `context.policy_rules`, preserving rule order (first-match-wins is
   order-sensitive — order must round-trip exactly).
4. Validation: every action-state column value must name a real state; warn on
   shadowed rows (a row whose conditions are a superset-match of an earlier row → never
   reached) and on a missing catch-all.

### Numeric/typed cells

Condition cells carry an operator + value (`>=85`, `<65`, `in[hot,warm]`). Rendering
and parsing must treat numeric comparisons numerically (see ENH-2164 typed-coercion
note) so a column sorts/validates correctly rather than lexically.

## Scope Boundaries

- **In scope**: detect/parse `context.policy_rules` for loops importing
  `lib/policy-router`; render compound condition-columns × action grid (markdown + CSV);
  `$EDITOR` round-trip back to `context.policy_rules` preserving rule order; shadowed-row
  + missing-catch-all + unknown-action-state warnings; reuse ENH-2227's extractor/
  renderer/parser/applier scaffolding in `route_table.py`
- **Out of scope**: the engine itself (ENH-2164); changes to the rule grammar
  (`|`-disjunction, nested booleans — still author multiple rows for OR); the simple
  state × verdict matrix path (unchanged, this is an additional mode); a visual/TUI
  diagram; runtime route injection (cancelled ENH-2226); pluggable operators (ENH-2234)

## API/Interface

```
ll-loop edit-routes <loop-name> [--decision-table] [--format markdown|csv] [--dry-run]
```

- `--decision-table` forces the compound-table lens; without it, auto-detect when the
  loop imports `lib/policy-router` and defines `context.policy_rules`, else fall back to
  the existing state × verdict matrix.
- Reuses `RouteTableExtractor` / `RouteTableRenderer` / `RouteTableParser` /
  `RouteTableApplier` in `scripts/little_loops/cli/loop/edit_routes.py` +
  `fsm/route_table.py`, adding a policy-rule extractor/serializer alongside them.

## Implementation Steps

1. Add policy-rule parser to `route_table.py` — convert `dim:op:value [& ...] -> state` strings into row objects
2. Add compound-grid renderer — build condition-columns × action table (markdown + CSV), column set = union of dimensions across all rules
3. Add grid serializer — convert edited table back to rule syntax, preserving row order (first-match-wins)
4. Add validators — shadowed rows, missing catch-all, unknown action state
5. Wire `--decision-table` flag and auto-detect logic into `edit_routes.py`
6. Add round-trip tests to `test_ll_loop_edit_routes.py`

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

7. Add `--decision-table` argument to `edit_routes_parser` in `scripts/little_loops/cli/loop/__init__.py` (lines 768–795) — `edit_routes_parser.add_argument("--decision-table", action="store_true", default=False, help="Render compound policy-router decision table instead of state × verdict matrix.")`
8. Add `test_decision_table_forwarded` to `TestMainLoopEditRoutesFlagForwarding` in `scripts/tests/test_cli_loop_dispatch.py` — mirrors `test_allow_delete_forwarded` pattern, verifies `args.decision_table` is forwarded correctly
9. Update `docs/reference/CLI.md` `#### ll-loop edit-routes` section — add `--decision-table` row to flag table and compound-table prose/examples
10. Update `docs/guides/LOOPS_GUIDE.md` quick-reference table row for `ll-loop edit-routes` — mention `--decision-table` flag

### Codebase Research Findings

_Added by `/ll:refine-issue` — concrete file/function references:_

1. **`route_table.py` — new classes to add** (alongside existing `RouteTableExtractor` etc.):
   - `PolicyRuleExtractor` — reads `fsm.context["policy_rules"]`, calls `parse_rules()` from `policy_rules.py`, returns `list[Rule]`
   - `CompoundGridRenderer` — takes `list[Rule]`, builds condition-columns × action table: columns = `["#"] + sorted(union of dims) + ["→ action"]`; catch-all row rendered as `*` in all condition cells. Mirrors `RouteTableRenderer.to_markdown/to_csv()` structure.
   - `CompoundGridParser` — parses edited markdown/CSV back to `list[Rule]`; validates all action-column values are real states (`known_states`); emits shadow warnings and missing-catch-all warnings. Returns a `ParsedDecisionTable(rules, warnings)` dataclass.
   - `PolicyRuleApplier` — writes serialized rules back via `serialize_rules(rules)` into `data["context"]["policy_rules"]` using `YAML(typ="rt")` + `atomic_write`; same round-trip-preserving pattern as `RouteTableApplier.apply()`.
   - Import: `from little_loops.fsm.policy_rules import parse_rules, serialize_rules, Rule, Predicate`

2. **`edit_routes.py` — branch in `cmd_edit_routes()`**: after `load_and_validate(path)` returns `fsm`, check `decision_table = getattr(args, "decision_table", False) or ("lib/policy-router" in fsm.imports and "policy_rules" in fsm.context)`. When `True`, route to `PolicyRuleExtractor` / `CompoundGridRenderer` / `CompoundGridParser` / `PolicyRuleApplier`; otherwise keep existing `RouteTableExtractor` path unchanged.

3. **`__init__.py` lines 768–795** — add one line: `edit_routes_parser.add_argument("--decision-table", action="store_true", default=False, help="Render compound policy-router decision table instead of state × verdict matrix.")`

4. **Tests in `test_ll_loop_edit_routes.py`**:
   - New fixture: copy or inline the `policy-refine.yaml` content (7-rule `context.policy_rules` with 4 dimensions) into a fixture under `scripts/tests/fixtures/fsm/`
   - `TestPolicyRuleExtractor` — round-trip: `PolicyRuleExtractor.extract(fsm)` against the fixture → verify rule count and catch-all
   - `TestCompoundGridRenderer` — markdown and CSV rendering of a `list[Rule]`; verify column headers and `—` empty cells
   - `TestCompoundGridParser` — parse rendered markdown back to `list[Rule]`; verify rule order preserved
   - `TestPolicyRuleApplier` — write to a temp fixture YAML, reload, verify `context.policy_rules` round-trips
   - `TestCmdEditRoutesDecisionTable` — end-to-end with `decision_table=True` and monkeypatched `subprocess.call`; also test auto-detect (no `--decision-table` flag, loop imports `lib/policy-router`)

5. **Operator grammar note**: `policy_rules.py` supports `>=`, `<=`, `==`, `!=`, `<`, `>` only. The `in[hot,warm]` example in the "Numeric/typed cells" section below does **not** match the actual grammar — `in[...]` is not implemented. Cells with `==` or `!=` handle string-equality comparisons; `in`-style matching would require a future operator extension (ENH-2234 territory).

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/edit_routes.py` — add `--decision-table` mode + auto-detect
- `scripts/little_loops/fsm/route_table.py` — policy-rule extractor + grid renderer + serializer
- `scripts/little_loops/cli/loop/__init__.py` — add `--decision-table` argument to `edit_routes_parser` (lines 768–795); also imports `cmd_edit_routes` at line 26 and dispatches at line 845

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md` — `#### ll-loop edit-routes` section (line 872): add `--decision-table` flag row to the flag table and compound-table prose + examples alongside the existing verdict-matrix examples
- `docs/guides/LOOPS_GUIDE.md` — `ll-loop edit-routes <name>` row in quick-reference table (~line 683): update cell to mention `--decision-table` and compound-table mode

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- (No new callers — `__init__.py` moved to Files to Modify since it requires `--decision-table` arg addition)

### Similar Patterns
- ENH-2227 / ENH-2228 — the existing `edit-routes` extractor/renderer/parser/applier to extend

### Tests
- `scripts/tests/test_ll_loop_edit_routes.py` — round-trip tests for compound tables (new tests)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_cli_loop_dispatch.py` — `TestMainLoopEditRoutesFlagForwarding`: add `test_decision_table_forwarded` following the same pattern as `test_allow_delete_forwarded` / `test_no_warnings_forwarded` / `test_format_csv_forwarded` (lines 934–970); verifies `--decision-table` is correctly forwarded through `main_loop()` to `cmd_edit_routes`

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md` — add `--decision-table` flag documentation (see Files to Modify above)
- `docs/guides/LOOPS_GUIDE.md` — update `edit-routes` quick-reference row (see Files to Modify above)

### Configuration
- N/A

### Issue Dependencies
- **ENH-2164** (`lib/policy-router.yaml`) — defines the `context.policy_rules` grammar this lens reads/writes; must land first (this issue is its authoring surface)

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `scripts/little_loops/fsm/policy_rules.py` — **already exists** (ENH-2164 partially implemented). Public API: `parse_rules(text: str) -> list[Rule]`, `serialize_rules(rules: list[Rule]) -> str`, `evaluate_rules(rules, scores) -> str | None`; dataclasses `Predicate(dim, op, value)` and `Rule(predicates, target, is_catchall)`. Import this module — do not reimplement the grammar.
- `scripts/little_loops/loops/lib/policy-router.yaml` — **already exists**. The fragment library this issue builds the editing lens for; fragments: `policy_parse_scores`, `policy_table_dispatch`.
- `scripts/little_loops/loops/policy-refine.yaml` — **already exists**. Concrete example loop importing `lib/policy-router.yaml` with a multi-rule `context.policy_rules` block (7 rules covering 4 dimensions). Use as round-trip test fixture input.
- `scripts/tests/test_policy_rules.py` — **already exists**. Unit tests for `policy_rules.py`; reference for test scope and structure of new compound-table tests.
- `scripts/little_loops/cli/loop/__init__.py` lines 768–795 — `edit-routes` subparser. Add `--decision-table` flag here: `edit_routes_parser.add_argument("--decision-table", action="store_true", ...)`. Dispatch unchanged; `cmd_edit_routes` reads via `getattr(args, "decision_table", False)`.
- `scripts/little_loops/fsm/schema.py` — `FSMLoop.imports: list[str]` holds the raw `import:` list; `FSMLoop.context: dict[str, Any]` holds the `context:` block. Auto-detect predicate: `"lib/policy-router" in fsm.imports and "policy_rules" in fsm.context`.
- `scripts/tests/test_fsm_fragments.py:TestRubricRouterLib` — exact structural model for a new `TestPolicyRouterLib` test class (fragment presence, description required, `${context.run_dir}` artifact path, and `resolve_fragments()` integration).

## Impact

- **Priority**: P3 — unlocks the user-facing value of ENH-2164 (most users only touch `edit-routes`)
- **Effort**: Medium — extends an existing round-trip tool; main work is the grid serializer + order-preserving write-back
- **Risk**: Low-Medium — round-trip fidelity of an order-sensitive rule list is the main correctness concern
- **Breaking Change**: No — additive mode; existing verdict-matrix behavior unchanged

## Labels

`enh`, `loops`, `fsm`, `dx`, `routing`, `decision-table`

## Status

**Open** | Created: 2026-06-19 | Priority: P3

## Session Log
- `/ll:confidence-check` - 2026-06-19T23:30:00 - `a6f4ecd1-513b-4c76-aa79-8da3db5a3650.jsonl`
- `/ll:wire-issue` - 2026-06-19T23:07:46 - `8ba0a80d-abe6-4c81-a1b3-b63381bfdc55.jsonl`
- `/ll:refine-issue` - 2026-06-19T23:00:08 - `f41f18ea-05b2-4083-8bb7-09cec8e247f5.jsonl`
- `/ll:format-issue` - 2026-06-19T22:52:50 - `f4c05632-020f-46ec-9644-de932e72069a.jsonl`
- `/ll:capture-issue` - 2026-06-19T21:56:31Z - `7ad4c299-a78e-4069-93e8-64dd478cf18b.jsonl`
