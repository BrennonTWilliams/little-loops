---
id: ENH-2334
title: Consolidate route_table operator grammar to the single policy_rules source
type: ENH
priority: P4
status: open
discovered_date: 2026-06-26
discovered_by: manual
relates_to:
- FEAT-2301
- ENH-2233
---

# ENH-2334: Consolidate route_table operator grammar to the single policy_rules source

## Summary

`fsm/route_table.py` independently re-lists the canonical comparison-operator set
in two places, duplicating `fsm/policy_rules._ALL_OPS`. Source both from a single
place — the `grammar_spec()` accessor proposed in FEAT-2301 (or a direct import of
`_ALL_OPS`) — so the operator grammar has exactly one definition. Pure
maintainability refactor; no behavior change.

## Motivation

`policy_rules.py` is documented as "the single source of truth for the grammar so
that lib/policy-router.yaml's `policy_table_dispatch` fragment and ENH-2233's
`edit-routes` lens both import the same parse / serialize logic"
(`fsm/policy_rules.py:8-11`). `route_table.py` is the `edit-routes` lens — yet it
does **not** import the canonical operator set; it hard-codes its own copy. The
six operators (`>=`, `<=`, `==`, `!=`, `<`, `>`) are therefore declared in three
independent locations, so a future grammar change (adding `~=`, etc.) silently
leaves `route_table.py` behind. This is the same drift class FEAT-2301 addresses
for the browser builder, but Python↔Python and already live in-tree.

## Current Behavior

Two hard-coded copies of the operator set in `route_table.py`:

- `route_table.py:382` — the grid-cell condition parser:
  ```python
  _COND_PATTERN = re.compile(r"^(>=|<=|==|!=|<|>)(.+)$")
  ```
- `route_table.py:455` — the parse-failure error message:
  ```python
  f"expected operator prefix (>=, <=, ==, !=, <, >)"
  ```

Both restate the operators in `policy_rules._ALL_OPS` (`fsm/policy_rules.py:28`).
Nothing connects them to the canonical set, so they can drift out of sync.

> **Scope note:** `_COND_PATTERN` is a *different shape* from `_PRED_PATTERN` — it
> parses a grid cell (`<op><value>`, no dim, no colon; the column header supplies the
> dim), whereas `_PRED_PATTERN` parses a full `<dim>:<op><value>` predicate. This ENH
> is **not** about merging the two regexes — only about sourcing the shared *operator
> alternation* and the error-string list from one definition.

## Expected Behavior

After this refactor, `route_table.py` has no hard-coded operator list:
- `_COND_PATTERN` is built dynamically from the canonical `policy_rules._ALL_OPS` (or `grammar_spec()["all_ops"]` if FEAT-2301 has landed), with multi-char operators sorted before single-char prefixes to preserve longest-match
- The parse-failure error string in the grid-cell condition parser is derived from the same set
- No behavior change: all existing `edit-routes` / `route_table` round-trip tests pass unchanged; a regression test verifies the derived operator set matches `_ALL_OPS`

## Proposed Solution

1. Build `_COND_PATTERN`'s operator alternation from the canonical set rather than a
   literal. Prefer FEAT-2301's `grammar_spec()` if it has landed; otherwise import
   `_ALL_OPS` directly:
   ```python
   from little_loops.fsm.policy_rules import _ALL_OPS  # or grammar_spec()["all_ops"]

   # Multi-char ops MUST precede their single-char prefixes so ">=" is tried
   # before ">". Sort by length descending; alphabetical order is NOT safe here.
   _OP_ALT = "|".join(sorted(_ALL_OPS, key=len, reverse=True))
   _COND_PATTERN = re.compile(rf"^({_OP_ALT})(.+)$")
   ```
2. Derive the error-message operator list from the same set instead of a hand-typed
   string (e.g. `", ".join(sorted(_ALL_OPS, key=len, reverse=True))`).
3. If `_ALL_OPS` stays private, consider promoting the accessor in step 1 to
   `grammar_spec()` (FEAT-2301) so external consumers don't reach into a private name.

**Ordering gotcha (applies to any alternation built from the set):** `sorted(_ALL_OPS)`
is alphabetical — `['!=', '<', '<=', '==', '>', '>=']` — which puts single-char `<`
before `<=` and breaks longest-match. Always sort by length descending when building a
regex alternation or the error list. Worth a one-line comment wherever this is done
(including FEAT-2301's stamped JS regex, if `grammar_spec()` exposes the raw set).

## Acceptance Criteria

- [ ] `route_table.py` contains no hand-typed operator list; both `_COND_PATTERN` and
  the parse-failure error string derive from the canonical `policy_rules` operator set
- [ ] The alternation is built with multi-char operators before single-char prefixes
  (longest-match preserved); a test covers a `>=` cell parsing as `>=` (not `>` + `=…`)
- [ ] No behavior change: existing `edit-routes` / `route_table` round-trip tests pass
  unchanged; a regression test asserts the derived operator set equals `sorted(_ALL_OPS)`
- [ ] (If applicable) the canonical set is exposed via a public accessor, not a private
  `_ALL_OPS` import

## Scope Boundaries

- **In scope**: removing the duplicated operator declarations in `route_table.py`;
  optionally introducing/using the `grammar_spec()` public accessor.
- **Out of scope**: merging `_COND_PATTERN` and `_PRED_PATTERN` (different shapes);
  any change to the operator set itself or to evaluation/serialization behavior.
- **Out of scope**: the browser-side grammar stamping — that is FEAT-2301. This ENH
  is the Python↔Python half of the same single-source goal.

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/route_table.py` — repoint `_COND_PATTERN` regex alternation and parse-failure error string to import from `policy_rules`

### Dependent Files (Callers/Importers)
- `scripts/little_loops/fsm/policy_rules.py` — provides `_ALL_OPS`; if FEAT-2301 lands first, `grammar_spec()` is the public accessor to prefer

### Similar Patterns
- FEAT-2301 — browser-side half of the same single-source goal; coordinate accessor promotion (`grammar_spec()`) if worked in parallel

### Tests
- `scripts/tests/test_ll_loop_edit_routes.py` — primary test file; key relevant classes:
  - `TestCompoundGridParser.test_parse_markdown_round_trip` — in-memory round-trip; passes unchanged after this refactor
  - `TestPolicyRuleApplier.test_apply_round_trip` — file-write round-trip through `load_and_validate`; passes unchanged
  - `test_parse_markdown_raises_invalid_cell` (line 874) — asserts `"Cannot parse condition cell"` in the `ValueError` message; does **not** assert the operator list portion, so the error string can be rephrased freely
- `scripts/tests/test_policy_rules.py` — `test_all_operators_parsed`, `test_parse_serialize_parse_stability` — reference patterns for new regression test structure
- **New tests to add** (in `TestCompoundGridParser` in `test_ll_loop_edit_routes.py`):
  - `test_cond_pattern_ops_match_all_ops` — assert that the operator set derivable from `_COND_PATTERN` equals `_ALL_OPS` (regression gate: catches drift if `_ALL_OPS` is later extended)
  - `test_parse_cond_cell_longest_match_gte` — assert that cell value `">=85"` parses as operator `">="` + value `"85"`, not `">"` + `"=85"` (longest-match ordering guard)

### Documentation
- N/A — pure refactor; no public API or user-visible behavior change

### Configuration
- N/A

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Full call chain into `_COND_PATTERN`**: `edit_routes.py:cmd_edit_routes()` → `CompoundGridParser.parse_markdown()`/`parse_csv()` → `_parse_rule_cells()` (lines 460–486) → `_parse_cond_cell()` (lines 447–457) → `_COND_PATTERN.match()`; `_parse_cond_cell` is the **only** consumer of `_COND_PATTERN`
- **`grammar_spec()` does not exist** — FEAT-2301 is still `open`; no public accessor is available in the current tree; the implementation must import `_ALL_OPS` directly (`from little_loops.fsm.policy_rules import _ALL_OPS`)
- **`_PRED_PATTERN`** at `policy_rules.py:32–34` also hardcodes the same six operators — out of scope per the issue scope note, but a natural follow-on once `grammar_spec()` lands in FEAT-2301
- **No external file currently imports `_ALL_OPS`** — `route_table.py` would be the first cross-module consumer; importing a private name is the only viable path until FEAT-2301 ships
- **`test_parse_markdown_raises_invalid_cell` (line 874) asserts only on `"Cannot parse condition cell"`** — it does not pin the operator list text, so the error string in `_parse_cond_cell()` can be freely rephrased to derive from `_ALL_OPS` without breaking that test

## Impact

- **Priority**: P4 — pure maintainability; no functional bug today, only latent drift
  risk. Cheap to do alongside FEAT-2301's `grammar_spec()` work, independently viable.
- **Effort**: Small — two declarations repointed at one source + an ordering-safety test.
- **Risk**: Low — refactor guarded by existing round-trip tests; the only real hazard is
  the alternation ordering, which the acceptance criteria pin.
- **Breaking Change**: No.

## Labels

`enhancement`, `refactor`, `policy-router`, `fsm`, `tech-debt`

## Status

**Open** | Created: 2026-06-26 | Priority: P4

## Session Log
- `/ll:refine-issue` - 2026-06-27T03:22:24 - `b57d4d23-0b03-479a-8de4-c2edac01f6ff.jsonl`
- `/ll:format-issue` - 2026-06-27T03:17:02 - `e931fe1e-b945-4c66-a5c8-cba8fbf6e4d4.jsonl`
- `capture` - 2026-06-26 - Filed from the FEAT-2301 review: the browser re-implementing `policy_rules.py:27-34` surfaced that `route_table.py` already duplicates the operator set in-tree (`:382` `_COND_PATTERN`, `:455` error string). Split out as the Python↔Python consolidation so it isn't lost if FEAT-2301 ships without the optional `route_table` repoint.
