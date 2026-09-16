# Policy Router Guide

> **When to use this**: Your loop needs to branch on a *combination* of scored dimensions
> — `confidence >= 85 AND outcome >= 75 → implement`, `security < 65 → escalate` — rather
> than a single yes/no verdict or one aggregate number. This guide covers authoring
> score-driven routing with the `lib/policy-router.yaml` fragment and editing the rule
> table visually with `ll-loop edit-routes`. For general FSM authoring (states, evaluators,
> the `/ll:create-loop` wizard), start with the [Loops Guide](LOOPS_GUIDE.md).

## Contents

- [Using the Wizard](#using-the-wizard)
- [What Is the Policy Router?](#what-is-the-policy-router)
- [The Rule Table Syntax](#the-rule-table-syntax)
- [Wiring a Loop with `lib/policy-router.yaml`](#wiring-a-loop-with-libpolicy-routeryaml)
- [Visual Builder (greenfield)](#visual-builder-greenfield)
  - [Issue Lifecycle Mode](#issue-lifecycle-mode)
- [Editing the Table with `ll-loop edit-routes`](#editing-the-table-with-ll-loop-edit-routes)
- [Adding and Removing Rows](#adding-and-removing-rows)
- [Warnings: Gaps, Shadows, and Catch-alls](#warnings-gaps-shadows-and-catch-alls)
- [Worked Example](#worked-example)
- [See Also](#see-also)

---

## Using the Wizard

The fastest way to create a policy-router loop is the `/ll:create-loop` wizard:

```bash
/ll:create-loop
# → Step 1: select "Policy router (decision table)"
# → Step PR1: choose LLM rubric scorer or custom shell scorer
# → Step PR2: enter scored dimensions (e.g. quality,feasibility,security)
# → Step PR3: specify the subject artifact path
# → Step PR4: edit the starter decision table
# → Step PR5: name the action states (e.g. done,repair,escalate)
# → Step PR6: set max iterations
# → Preview, save, and validate
```

Or via natural language shortcut:

```bash
/ll:create-loop score my proposal on quality, feasibility, and security and route via a policy table
```

After creation, re-edit the decision table at any time without touching the YAML directly:

```bash
ll-loop edit-routes <name>
```

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

Tracing the table by hand, as above, is currently the only way to predict which rule
fires for a given score set. `ll-loop simulate policy-refine` can trace FSM state
connectivity without running real LLM calls, but it cannot evaluate policy rules (shell
actions are not executed in simulation) — to confirm a match for real, run the loop with
a real or mocked artifact.

## Visual Builder (greenfield)

When you are authoring a **new** policy-router or rubric loop from scratch — rather than
editing one that already exists — generate the self-contained HTML builder:

```bash
ll-artifact policy-builder            # writes ./policy-router-builder.html
ll-artifact policy-builder -o ~/tmp   # custom output directory
```

Open the generated `policy-router-builder.html` in any browser (no install, no server — it
works over `file://`). It presents a one-page form with three modes:

- **Decision Table** — an ordered, numbered rule list that reads as plain-language sentences
  ("When `quality ≥ 80` → **light-repair**"). The on-screen number *is* precedence
  (first-match-wins, top to bottom); ↑/↓ buttons reorder rules, and reordering re-runs shadow
  detection and the live preview immediately. A pinned "Otherwise → `<outcome>`" footer is a
  structured dropdown over the outcomes you've named — not a free-text field, and it can't be
  deleted. Dimensions are typed (numeric vs boolean), so the operator dropdown only offers
  valid operators and the numeric-coercion parse-error class is unrepresentable. Each outcome
  is named once and authors its action/transition in plain language — **Do:** (a prompt, a
  skill/command from this project's stamped catalog, or nothing) and **And then:** (score
  again, go to another outcome, or stop here) — so dead-end states (the MR-4 pitfall — see
  the [Harness Optimization Guide](HARNESS_OPTIMIZATION_GUIDE.md)) cannot be expressed. A
  "Try it" panel lets you enter sample values per dimension and highlights the rule that would
  win, making the effect of reordering visible immediately.
- **Rubric** — one aggregate score with two threshold sliders feeding a fixed high/medium/low
  table (mirrors `lib/rubric-router.yaml`); none of the Decision Table's reorder/add-rule
  affordances are shown, since the rubric grammar has no rule ordering to express.
- **Issue Lifecycle** — routes a single `.issues/*.md` file through prepare → refine → gate →
  implement → verify, driven by its YAML frontmatter. See
  [Issue Lifecycle Mode](#issue-lifecycle-mode) below.

The page validates live (shadowed rules, unreachable outcomes, and unknown actions are flagged
in plain language, referencing the visible rule numbers) and emits loop YAML behind a
collapsed "View generated file" disclosure — the default view is a one-line plain summary plus
Copy/Download and a printed `ll-loop validate <name>` hint. The page seeds with a small
runnable example on load; "Start blank" clears it. Its grammar, design-token theme, and skill
catalog are **stamped from this project at generation time** (including the project's
configured `active_theme`, which the page honors ahead of OS light/dark preference), so
regenerate the file to pick up new skills or grammar changes.

**Builder vs. `edit-routes`:** the builder is *greenfield-only* — it composes a new loop and
exports YAML. `ll-loop edit-routes` (below) is the round-trip editor for a loop that *already
exists*. Use the builder to create; use `edit-routes` to revise.

### Issue Lifecycle Mode

`issue_lifecycle` is a third builder mode for a narrower, very common case: driving a single
Issue file (`.issues/*.md`) through **prepare → refine → gate → implement → verify** based on
its own YAML frontmatter, without hand-writing FSM YAML or adopting little-loops' own
hand-tuned `autodev.yaml` (2650+ lines, not a realistic template to copy). It's the
self-service version of `autodev.yaml`'s *shape* — route an issue through lifecycle stages
based on frontmatter conditions — for consumers with their own issue conventions (a custom
`severity` field, a `review_status` field, anything not part of little-loops' own schema).

The emitted loop is the same thin shape `decision_table` mode emits (imports
`lib/policy-router.yaml`, carries the rule table in `context.policy_rules`, dispatches via
`policy_table_dispatch`), with one substitution: the LLM `rubric_score` + `policy_parse_scores`
pair is replaced by a single deterministic **`frontmatter_scores`** fragment that reads the
issue file's frontmatter directly (via `little_loops.frontmatter.parse_frontmatter`) and writes
the same `rubric-dim-<name>.txt` score files `policy_table_dispatch` already consumes. One issue
per run — no queue, retry, or rate-limit machinery; run it with:

```bash
ll-loop run <name> --context issue_id=<ID>
```

**Dimensions are frontmatter fields.** little-loops' own built-in fields are pre-typed and
pre-populated (locked — they can't be deleted, since a rule may reference the derived
`priority_rank`); you add your own on top by naming any frontmatter key and picking a type.
No little-loops code needs to know your custom field ahead of time.

| Frontmatter key | Type | Scorer encoding |
|---|---|---|
| `status` | string | verbatim; absent → no file |
| `priority` | string | verbatim (`P0`..`P5`); absent → no file |
| `priority_rank` | numeric | **derived** from `priority`: leading `P` stripped → `0`..`5` (so `priority_rank:<=2` works); absent or non-`P<digit>` → no file |
| `confidence_score` | numeric | verbatim; absent → no file |
| `outcome_confidence` | numeric | verbatim; absent → no file |
| `decision_needed` | boolean | `100` / `0` (string-truthiness — see below); always written |
| `spike_needed` | boolean | `100` / `0`; always written |
| `blocked_by` | list | count; always written, `0` when absent/empty/`null` |
| `deferred_reason` | string | verbatim; absent/`null` → no file |

Custom fields pick one of four types: `numeric` and `list` offer all six operators; `boolean`
offers `==true`/`==false`; `string` offers `==`/`!=` only (the rule-value input for a `string`
dim rejects empty values and values containing `&` or `->`, since those characters are the rule
grammar's own predicate/target separators). A custom field name can't contain `:` or `|` (they
break the `name:type|name:type` encoding of `context.frontmatter_dimensions`), and can't
normalize to an existing dimension's name (including `priority_rank`).

**Actions are the five fixed lifecycle verbs.** Every rule (and the "Otherwise" fallback) routes
to one of them; verbs can't be deleted and no new outcome can be added. Each is pre-bound to a
default skill and args, overridable from the same skill-catalog dropdown the other two modes use,
plus a free-text args field:

| Verb | Default action | Default args | Default transition |
|---|---|---|---|
| prepare | `/ll:format-issue` | `--auto` | Score again |
| refine | `/ll:refine-issue` | `--auto` | Go to → gate |
| gate | `/ll:confidence-check` | `--auto` | Score again |
| implement | `ll-auto --only` (shell, not `/ll:manage-issue` — it requires `<type> <action>` positionals unknowable at emit time) | *(none)* | Stop here |
| verify | `/ll:verify-issues` | `--auto` | Stop here |

`--auto` runs each skill unattended; when you override a verb with a catalog skill that doesn't
accept `--auto`, clear the args field. `refine` defaults to **Go to → gate** rather than
rescoring directly, because `/ll:refine-issue` doesn't write `confidence_score` (only
`/ll:confidence-check` does) — routing through `gate` first is what lets a single run make
progress from refine to a re-scored `confidence_score`. `implement`'s help text in the builder
calls out that `ll-auto` re-applies your project's own `commands.confidence_gate.readiness_threshold`
and exits non-zero (routing to `failed`) below it; add `--force-implement` to its args to bypass
that gate. Only verbs actually reachable — targeted by a rule, the fallback, or the `goto` target
of an already-reachable verb — are emitted into the saved YAML; the rest are simply left out.

**Seeded example** (also the Use Case this mode ships with):

```
status:==done -> verify
severity:==critical & review_status:==approved -> implement
confidence_score:>=85 -> implement
confidence_score:<85 -> refine
* -> gate
```

On an unscored issue this runs gate (writes `confidence_score`) → refine → gate again → implement
once the score clears 85, bounded by `on_max_steps: failed` if the refine/gate cycle never
converges. `status:==done -> verify` only fires on a *later* run against the same issue, since
`implement` stops the current run.

**Try it** accepts a pasted frontmatter block (a minimal YAML-subset reader — scalars, flow/dash
lists, no nested maps) and highlights the winning rule using the same rule-table evaluator the
emitted loop runs, so what you see in the builder is what the loop will do. A hint line under
the textarea shows the encoded scores as `key=value` pairs.

**Encoding rules**, shared verbatim between the Python `frontmatter_scores` fragment and the
builder's Try-it encoder:

- **boolean** → `100` when the value, lowercased and stripped, is one of `true`/`yes`/`on`/`1`;
  otherwise `0`. Always written (an absent boolean field still scores `0`).
- **numeric** → the scalar verbatim (a non-numeric value like `confidence_score: high` is written
  as-is; ordered operators then evaluate `False` against it); a list value scores its length.
  Absent/`null` → no file (the router's missing-dimension semantics: `!=` matches, everything
  else does not).
- **list** → count semantics: a list scores its length, a non-empty scalar scores `1`,
  absent/`null`/empty scores `0`. Always written — this is what makes `blocked_by:==0` /
  `blocked_by:<1` match the common "not blocked" case for an issue that has no `blocked_by` key
  at all.
- **string** → the value, trimmed, verbatim. Absent/`null`/empty → no file.
- Frontmatter values are always strings (`parse_frontmatter` loads with PyYAML's `BaseLoader`,
  so `decision_needed: true` arrives as the string `"true"`, not a Python `bool`) — every rule
  above is defined on string/list/`None` inputs.
- `status` synonyms are canonicalized before scoring (e.g. `completed` → `done`), matching
  `little_loops.frontmatter.STATUS_SYNONYMS`.
- Every score pass first deletes every `rubric-dim-*.txt` / `rubric-aggregate.txt` in
  `${context.run_dir}/` before writing — otherwise a field present on one pass and cleared on the
  next (e.g. `deferred_reason` cleared by `/ll:refine-issue`) would keep stale missing-dimension
  semantics from firing.

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
| `--no-warnings` | Skip the gap/conflict warnings (verdict-matrix: pre-editor; compound-mode: post-save) |
| `--allow-delete` | Apply state-row deletions instead of ignoring them (verdict-matrix mode only — `PolicyRuleApplier` for compound mode does not consume this flag) |

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

In verdict-matrix mode, `edit-routes` prints a gap/conflict report **before** opening the
editor. In compound mode, warnings are reported after you save and close the editor — they
reflect validation of the edited table. Either way, suppress with `--no-warnings`.

- **Verdict-matrix mode** warns on **unreachable states** (no route leads there), **dead-end
  states** (non-terminal with no outbound routes), and **missing verdict arms** (e.g. `on_yes`
  with no `on_no` or `default` — the [MR-4 dead-end pitfall](HARNESS_OPTIMIZATION_GUIDE.md)).
- **Compound mode** warns on **shadowed rules** (an earlier rule's conditions subsume a later
  rule's, so the later one never fires), a **missing catch-all** (no `* ->` rule, so some score
  sets produce no route), and **unknown action states** (the `→ action` column names a state the
  loop doesn't define).
- **`ll-loop validate`** additionally warns on **unscored dimensions**: any predicate dim
  that is not listed in `context.rubric_dimensions` (after normalization: lowercase +
  spaces→hyphens) and is not written as `rubric-dim-<name>.txt` by a shell state is
  silently inert at runtime — the dimension never reaches the scores dict, so `==` / `>=` /
  `<=` / `<` / `>` predicates on it can never match and routing falls through to the
  catch-all. Predicate dims must be in **normalized form** (lowercase, spaces replaced by
  hyphens) to match the score keys written by `policy_parse_scores`; `Has Citations` in a
  predicate is inert even if `Has Citations` is listed in `rubric_dimensions` (the score key
  is `has-citations`). Set `policy_dims_scored_ok: true` at the loop top-level to suppress
  this check when a dynamically-named shell scorer makes static detection impossible.

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
   the [MR-4 dead-end rule](HARNESS_OPTIMIZATION_GUIDE.md) and warns on missing catch-alls,
   shadowed rules, and predicates that reference a dimension never scored (the policy-table
   rule — see the `policy-table` row in [HARNESS_OPTIMIZATION_GUIDE.md](HARNESS_OPTIMIZATION_GUIDE.md#the-design-rules-mr-1mr-14)), catching the routing gaps
   the table edit might have introduced:

   ```bash
   ll-loop validate policy-refine
   ll-loop run policy-refine "artifact.md"
   ```

## See Also

- [Loops Guide](LOOPS_GUIDE.md) — FSM authoring fundamentals, evaluators, the `/ll:create-loop` wizard
- [Built-in Loops Reference](LOOPS_REFERENCE.md#built-in-fragment-libraries) — the full fragment-library catalog, including `lib/policy-router.yaml` and `lib/rubric-router.yaml`
- [Harness Optimization Guide](HARNESS_OPTIMIZATION_GUIDE.md) — the MR-4 routing rule and other meta-loop guardrails
- [CLI Reference: `ll-loop edit-routes`](../reference/CLI.md) — complete flag and exit-code reference
- [CLI Reference: `ll-loop validate` / `ll-loop run`](../reference/CLI.md) — validate routing before executing the loop
- [API Reference](../reference/API.md) — `little_loops.fsm.policy_rules` (rule grammar) and `little_loops.fsm.route_table` (the edit-routes lens)
