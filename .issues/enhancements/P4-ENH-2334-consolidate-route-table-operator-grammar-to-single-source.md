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
- `capture` - 2026-06-26 - Filed from the FEAT-2301 review: the browser re-implementing `policy_rules.py:27-34` surfaced that `route_table.py` already duplicates the operator set in-tree (`:382` `_COND_PATTERN`, `:455` error string). Split out as the Python↔Python consolidation so it isn't lost if FEAT-2301 ships without the optional `route_table` repoint.
