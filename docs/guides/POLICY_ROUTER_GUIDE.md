# Policy Router Guide

> **When to use this**: Your loop needs to branch on a *combination* of scored dimensions
> — `confidence >= 85 AND outcome >= 75 → implement`, `security < 65 → escalate` — rather
> than a single yes/no verdict or one aggregate number. This guide covers authoring
> score-driven routing with the `lib/policy-router.yaml` fragment and editing the rule
> table visually with `ll-loop edit-routes`. For general FSM authoring (states, evaluators,
> the `/ll:create-loop` wizard), start with the [Loops Guide](LOOPS_GUIDE.md).

## Contents

- [What Is the Policy Router?](#what-is-the-policy-router)
- [The Rule Table Syntax](#the-rule-table-syntax)
- [Wiring a Loop with `lib/policy-router.yaml`](#wiring-a-loop-with-libpolicy-routeryaml)
- [Editing the Table with `ll-loop edit-routes`](#editing-the-table-with-ll-loop-edit-routes)
- [Adding and Removing Rows](#adding-and-removing-rows)
- [Warnings: Gaps, Shadows, and Catch-alls](#warnings-gaps-shadows-and-catch-alls)
- [Worked Example](#worked-example)
- [See Also](#see-also)

---

## What Is the Policy Router?

A plain FSM state routes on a single verdict — `on_yes`, `on_no`, or a `route:` map keyed by
one classification token. That works when one signal decides the next step. It breaks down
when the decision depends on *several* scores at once: "ship it only if both confidence and
outcome are high," "escalate the moment security dips, regardless of everything else."

The **policy router** replaces those hand-coded branches with a declarative **decision
table**: a priority-ordered list of rules, each mapping a conjunction of per-dimension
predicates to a target state. Rules are evaluated top-to-bottom and **first match wins**:

```
security:<65 -> escalate
confidence:>=85 & outcome:>=75 -> implement
* -> repair
```

The router reads per-dimension scores, walks the table in order, and emits the target state
of the first rule whose predicates all hold. Because evaluation is data-driven, you tune
routing by editing a table — not by rewiring states.

It ships as a reusable FSM fragment, `lib/policy-router.yaml`, which sits in a small layered
stack:

| Layer | Artifact | Role |
|-------|----------|------|
| L0 | `classify` evaluator | Reads the emitted token as a verdict and dispatches via `route:` |
| L1 | **`lib/policy-router.yaml`** | Conjunctive multi-axis rules, source-agnostic input |
| Preset | `lib/rubric-router.yaml` | Single-aggregate 3-tier shortcut for the common case |

**Source-agnostic input.** The router evaluates rules against per-dimension score *files*
written to `${context.run_dir}/`, not against any particular scorer's output. The rubric path
(an LLM scoring an artifact) is one supported source; a deterministic shell scorer that writes
the same `rubric-dim-<name>.txt` files works identically. Whoever writes the scores, the table
reads them the same way.

## The Rule Table Syntax

Rules live in the `context.policy_rules` field as a newline-separated block. The grammar
(implemented in `little_loops.fsm.policy_rules`) is:

```
<dim>:<op><value>                                          -> <state>   single predicate
<dim>:<op><value> & <dim2>:<op2><value2>                   -> <state>   conjunctive (AND)
<dim>:<op><val> & <dim2>:<op2><val2> & <dim3>:<op3><val3>  -> <state>   3-way AND
* -> <state>                                                            catch-all (must be last)
# comment lines and blank lines are skipped
```

- **Operators**: `>=`, `<=`, `==`, `!=`, `<`, `>`.
- **Conjunction**: join predicates with ` & ` — *all* must hold for the rule to match. There
  is no `OR`; express alternatives as separate rules.
- **Catch-all**: `* -> <state>` matches unconditionally. Put it last — anything after it is
  unreachable. Omit it and an unmatched score set emits an empty token, which falls through to
  the dispatch state's `_:` route (see below).
- **Numeric coercion**: ordered operators (`>=`, `<=`, `<`, `>`) require numeric values and
  raise a parse-time error otherwise. Comparison is numeric, so `"9" < "10"` is `True` (not the
  lexical `False`). For `==` / `!=`, the router tries numeric first and falls back to string
  comparison when both sides are non-numeric.
- **The `aggregate` dimension** is reserved: it refers to the overall rubric score
  (`rubric-aggregate.txt`), distinct from any named dimension.

## Wiring a Loop with `lib/policy-router.yaml`

A policy-routed loop is a three-state pipeline: **score → parse → dispatch**. The fragment
exports the two states you need:

| Fragment | Does |
|----------|------|
| `policy_parse_scores` | Re-parses rubric output, writes `rubric-aggregate.txt` + `rubric-dim-<name>.txt` to `${context.run_dir}/` |
| `policy_table_dispatch` | Evaluates `context.policy_rules` against those files, emits the winning token via a `classify` evaluator |

The built-in `policy-refine` loop is the canonical example. Its setup:

```yaml
import:
  - lib/rubric-router.yaml   # provides rubric_score (LLM scoring)
  - lib/policy-router.yaml   # provides policy_parse_scores + policy_table_dispatch

context:
  subject: "artifact.md"
  rubric_dimensions: "clarity|completeness|feasibility|security"
  # Decision table: evaluated top-to-bottom; first match wins.
  policy_rules: |
    security:<65 -> escalate
    completeness:<60 -> deep_repair
    feasibility:<60 -> rethink
    clarity:>=85 & completeness:>=85 & feasibility:>=85 -> done
    aggregate:>=85 -> done
    aggregate:>=60 -> light_repair
    * -> deep_repair
```

And the state flow:

```yaml
initial: score

states:
  score:
    fragment: rubric_score          # LLM scores the subject on each dimension
    capture: scores
    next: parse_scores

  parse_scores:
    fragment: policy_parse_scores   # writes rubric-dim-*.txt to ${context.run_dir}/
    next: policy_dispatch

  policy_dispatch:
    fragment: policy_table_dispatch # evaluates the table, emits a token
    route:
      escalate: escalate
      deep_repair: deep_repair
      light_repair: light_repair
      rethink: rethink
      done: done
      _: deep_repair                # required: catch-all for unmatched / unrecognized tokens
      _error: done                  # optional: error fallback
```

Two routing safety nets live on the dispatch state's `route:` map: `_:` catches an empty token
(no rule matched and no `* ->` catch-all) or any token not listed as a key, and `_error:`
catches an evaluator failure. Always provide `_:` — without it, a non-matching score set
dead-ends.

**Tracing a match.** Suppose `score` produces `clarity=92, completeness=78, feasibility=85,
security=88, aggregate=86`. The dispatcher walks the table:

1. `security:<65` → no (88 ≥ 65)
2. `completeness:<60` → no (78 ≥ 60)
3. `feasibility:<60` → no (85 ≥ 60)
4. `clarity:>=85 & completeness:>=85 & feasibility:>=85` → no (completeness 78 fails the AND)
5. `aggregate:>=85` → **yes** (86 ≥ 85) → emits `done`

The `classify` evaluator reads `done` and the `route:` map sends the loop to the `done` state.

You don't have to trace the table by hand — `ll-loop simulate policy-refine` walks FSM
execution interactively without invoking real commands, so you can confirm which rule fires
for a given score set before committing to a real run.

## Editing the Table with `ll-loop edit-routes`

`ll-loop edit-routes` renders a loop's routing as a table, opens it in `$EDITOR`, and writes
your edits back to the YAML on save — preserving all non-route fields, comments, and structure.
The YAML stays the single source of truth; the table is a transient editing lens. Use
`--dry-run` to print the table without opening an editor.

It has **two rendering modes**:

### State × verdict matrix (default)

For standard loops, each row is a state and each column is a verdict; cells hold the target
state, and `—` marks an unrouted verdict:

```
| state             | yes  | no                | error             | next              |
|-------------------|------|-------------------|-------------------|-------------------|
| generate_variants | —    | —                 | —                 | score_and_select  |
| score_and_select  | —    | —                 | —                 | route_convergence |
| route_convergence | done | generate_variants | generate_variants | —                 |
| done              | —    | —                 | —                 | —                 |
```

Editing a cell rewrites the corresponding field — `on_<verdict>` shorthand, or a key inside a
`route:` block, whichever the state already uses. `--format csv` renders the same matrix as CSV
(empty cells are blank rather than `—`).

### Compound decision table (policy-router)

For loops that import `lib/policy-router.yaml` and have a `context.policy_rules` block, the
command **auto-detects** the compound lens (force it anywhere with `--decision-table`). Each
row is one rule, the condition columns are the scored dimensions, and the final `→ action`
column is the target state. Running it on `policy-refine`:

```
| # | aggregate | clarity | completeness | feasibility | security | → action     |
|---|-----------|---------|--------------|-------------|----------|--------------|
| 1 | —         | —       | —            | —           | <65      | escalate     |
| 2 | —         | —       | <60          | —           | —        | deep_repair  |
| 3 | —         | —       | —            | <60         | —        | rethink      |
| 4 | —         | >=85    | >=85         | >=85        | —        | done         |
| 5 | >=85      | —       | —            | —           | —        | done         |
| 6 | >=60      | —       | —            | —           | —        | light_repair |
| 7 | *         | *       | *            | *           | *        | deep_repair  |
```

Each condition cell is an operator+value (`>=85`, `<65`, `==true`); `—` means the dimension is
unconstrained in that rule; `*` in every condition column marks the catch-all. Dimension
columns are sorted alphabetically. Edit cells or reorder rows, save, and the changes
round-trip back into `context.policy_rules` as canonical `dim:op value` text.

Common flags:

| Flag | Effect |
|------|--------|
| `--dry-run` | Print the table to stdout; don't open the editor or write YAML |
| `--format csv` | Render (and parse) CSV instead of markdown |
| `--decision-table` | Force compound mode (otherwise auto-detected for policy-router loops) |
| `--no-warnings` | Skip the gap/conflict report printed before the editor opens |
| `--allow-delete` | Apply row deletions instead of ignoring them (see below) |

Exit codes: `0` success or no changes, `1` parse error or an unknown state name in the edited
table, `2` loop not found.

## Adding and Removing Rows

**In verdict-matrix mode:**

- **Add a terminal stub** — add a row whose state name doesn't exist yet and leave every
  verdict cell empty. On save it's inserted as `terminal: true`, a placeholder you can flesh out
  later. (A row with a new name *and* non-empty verdicts is rejected as an unknown state — exit
  `1` — since the router can't guess the rest of the block.)
- **Delete a state** — remove the row entirely, then re-run with `--allow-delete`. The state
  block is removed and any remaining routes that still point at it are flagged as dangling.
  Without `--allow-delete`, removed rows are silently ignored — a deliberate guard so an
  accidental deletion in the editor never drops a state.

**In compound decision-table mode**, add or remove rules by adding or deleting grid rows; on
save the rule list is re-serialized into `context.policy_rules` in the new order. Because
evaluation is first-match-wins, row order is significant — reorder rows to change precedence.

## Warnings: Gaps, Shadows, and Catch-alls

Before opening the editor, `edit-routes` prints a gap/conflict report (suppress with
`--no-warnings`):

- **Verdict-matrix mode** warns on **unreachable states** (no route leads there), **dead-end
  states** (non-terminal with no outbound routes), and **missing verdict arms** (e.g. `on_yes`
  with no `on_no` or `default` — the [MR-4 dead-end pitfall](HARNESS_OPTIMIZATION_GUIDE.md)).
- **Compound mode** warns on **shadowed rules** (an earlier rule's conditions subsume a later
  rule's, so the later one never fires), a **missing catch-all** (no `* ->` rule, so some score
  sets produce no route), and **unknown action states** (the `→ action` column names a state the
  loop doesn't define).

The recurring lesson across both modes: **always provide a catch-all.** In a decision table
that's a final `* -> <state>` rule; on a dispatch state it's the `_:` route. A table without one
silently dead-ends on any input the explicit rules don't cover.

## Worked Example

Tune `policy-refine` to be stricter — require a high security score before declaring `done`.

1. **View the current table:**

   ```bash
   ll-loop edit-routes policy-refine --dry-run
   ```

   This prints the 7-rule grid shown above (decision-table mode auto-detected).

2. **Add a stricter rule.** Open it for real and insert a rule *above* the `aggregate:>=85`
   row so it takes precedence — only call it `done` when both the aggregate and security clear
   85:

   ```bash
   ll-loop edit-routes policy-refine
   ```

   Add the row:

   ```
   | 5 | >=85 | — | — | — | >=85 | done |
   ```

   On save, `edit-routes` re-serializes the table back into `context.policy_rules` as
   `aggregate:>=85 & security:>=85 -> done`, and re-numbers the rows.

3. **Confirm the round-trip:**

   ```bash
   ll-loop edit-routes policy-refine --dry-run
   ```

   The new conjunctive rule appears in the grid with `>=85` in both the `aggregate` and
   `security` columns. The loop now routes a high-aggregate-but-low-security artifact to repair
   instead of `done`, with no state rewiring — only a table edit.

4. **Validate, then run.** Before executing, validate the loop — `ll-loop validate` enforces
   the [MR-4 dead-end rule](HARNESS_OPTIMIZATION_GUIDE.md) and warns on missing catch-alls and
   shadowed rules, catching the routing gaps the table edit might have introduced:

   ```bash
   ll-loop validate policy-refine
   ll-loop run policy-refine
   ```

## See Also

- [Loops Guide](LOOPS_GUIDE.md) — FSM authoring fundamentals, evaluators, the `/ll:create-loop` wizard
- [Built-in Loops Reference](LOOPS_REFERENCE.md#built-in-fragment-libraries) — the full fragment-library catalog, including `lib/policy-router.yaml` and `lib/rubric-router.yaml`
- [Harness Optimization Guide](HARNESS_OPTIMIZATION_GUIDE.md) — the MR-4 routing rule and other meta-loop guardrails
- [CLI Reference: `ll-loop edit-routes`](../reference/CLI.md) — complete flag and exit-code reference
- [CLI Reference: `ll-loop validate` / `ll-loop run`](../reference/CLI.md) — validate routing before executing the loop
- [API Reference](../reference/API.md) — `little_loops.fsm.policy_rules` (rule grammar) and `little_loops.fsm.route_table` (the edit-routes lens)
