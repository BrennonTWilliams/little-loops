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
  - [Failure Routing and Clean-Slate Scoring](#failure-routing-and-clean-slate-scoring)
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
    on_error: failed                # nonzero exit / prompt failure never falls through to parsing

  parse_scores:
    fragment: policy_parse_scores   # writes rubric-dim-*.txt to ${context.run_dir}/
    next: policy_dispatch
    on_error: failed                # unparseable scoring output exits nonzero (see below)

  policy_dispatch:
    fragment: policy_table_dispatch # evaluates the table, emits a token
    on_error: failed                # a routable action-runner exception (not an exit code)
    route:
      escalate: escalate
      deep_repair: deep_repair
      light_repair: light_repair
      rethink: rethink
      done: done
      _: deep_repair                # required: catch-all for unmatched / unrecognized tokens
      _error: failed                # the evaluator `error` verdict (nonzero exit / timeout)

  failed:
    terminal: true
    failure: true
```

Two routing safety nets live on the dispatch state's `route:` map: `_:` catches an empty token
(no rule matched and no `* ->` catch-all) or any token not listed as a key, and `_error:`
catches the evaluator's `error` verdict (dispatch exited nonzero or timed out). Always provide
`_:` — without it, a non-matching score set dead-ends. `_error` is consulted **ahead of** `_`
for the `error` verdict, so route it to a dedicated failure terminal (`failed` above) rather than
a user outcome — a nonzero exit means dispatch never evaluated the rule table, so any outcome it
"selected" is baseless. `on_error` is a separate, non-redundant safety net: it catches an
exception raised by the action runner itself (not an exit code), and fires whether or not a
`route:` table is also present. Provide both on every scoring/parsing/dispatch state, as above.

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

### Failure Routing and Clean-Slate Scoring

- **Clean-slate scoring.** `policy_parse_scores` clears `rubric-dim-*.txt` and
  `rubric-aggregate.txt` in `${context.run_dir}/` at the start of every invocation, before
  parsing the new LLM output. A loop that loops back through `score` (e.g. `light_repair`/
  `deep_repair` routing to `next: score`) reuses the same run directory across passes; without
  clearing first, a dimension the LLM emitted on pass one but omitted on pass two would leave
  the stale pass-one score in play. Other run artifacts (e.g. `policy-action.txt`) are
  untouched. `frontmatter_scores` (Issue Lifecycle Mode) already behaves this way.
- **Exactly one clean-slate scorer per pass.** `policy_parse_scores` and `frontmatter_scores`
  both own `rubric-dim-*.txt` / `rubric-aggregate.txt`. If you mix a deterministic shell scorer
  writing those files directly with either fragment in the same pass, whichever writes last
  wins — don't combine them.
- **Partial scoring is valid; wholly unparseable output is not.** An omitted `DIMENSION:` line
  or an omitted `AGGREGATE:` line simply writes no file for that key — the missing-dimension
  `!=` semantics apply, exactly as if a shell scorer never wrote that dimension. But output with
  **neither** a recognized `AGGREGATE:` nor any recognized `DIMENSION:` line is a hard failure:
  `policy_parse_scores` exits nonzero rather than fabricating `AGGREGATE: 0` (a fabricated `0`
  would let an `aggregate:<N` rule fire on evidence the scorer never produced). Route this
  through `on_error` to a failure terminal, as shown above — a single LLM formatting slip then
  ends the run instead of silently limping on into a repair/re-score loop with no real evidence
  behind it. If you want automated tolerance for an occasional bad response, opt in explicitly
  with the executor's per-state `max_retries` / `on_retry_exhausted` on `score` (or
  `parse_scores`) — that bounds the retry visibly instead of hiding it behind fabricated
  evidence.
- **Dispatch aborts on an artifact read failure, not just a missing one.** An entry absent from
  `${context.run_dir}/`'s directory listing (an omitted dimension) is valid missing evidence.
  A file that's *discovered* by the listing but can't be read (permissions error, dangling
  symlink, or the run directory itself vanishing) is an I/O failure — `policy_table_dispatch`
  aborts with a nonzero exit before evaluating any rule or publishing a new `policy-action.txt`,
  rather than matching a catch-all rule against an incomplete score map.
- **`_error` resolves ahead of `_` for the `error` verdict.** `FSMExecutor._route()` checks
  `route.error` (your `_error:` key) before `route.default` (`_:`) whenever the evaluator
  returns `error` — which is what a nonzero dispatch exit or timeout becomes. This means
  `_error:` is genuinely reachable even when `_:` is also declared; point it at a dedicated
  failure terminal, not a user outcome. The one deliberate asymmetry: the `no` verdict's
  shorthand fallback to `route.error` still resolves *after* `route.default` — `no` is an
  ordinary verdict whose ordinary fallback is `_`, unlike the dedicated error path.
- **Reserved names.** The generated decision-table pipeline uses `score`, `parse_scores`,
  `policy_dispatch`, `failed`, `finished`, and `needs_attention` as its own state names
  (issue-lifecycle mode uses `score`, `policy_dispatch`, `done`, `failed`, `issue_id`, `stopped`,
  `skipped`, and `needs_attention`; rubric mode uses `score`, `parse_scores`, `route_high`,
  `route_medium`, `done`, and `needs_attention`); `error` is reserved in all three. `needs_attention`
  is the step-budget-exhaustion terminal in every mode (ENH-3492); in issue-lifecycle mode, `stopped`/
  `skipped`/`needs_attention` are also directly *referenceable* — as a rule target, the fallback, or a
  verb's follow-up — without being redefined as an outcome (a reference-vs-definition distinction:
  reserving the name blocks an authored outcome from shadowing it, not a legal lifecycle reference).
  Every underscore-prefixed token (`_`, `_error`, or any custom `_foo`) is also rejected —
  `RouteConfig.from_dict()` strips underscore-prefixed keys from explicit verdict routes at
  runtime, so an authored outcome or rule target starting with `_` would silently vanish rather
  than route. Separately, `aggregate` is reserved as a **dimension** name (it is the overall
  rubric score `fsm/validation/reachability.py` skips as a predicate LHS) — a custom field that
  normalizes to `aggregate` is rejected the same way. The Visual Builder's `validateBuilderModel`
  rejects all of these before emission with a diagnostic naming the offending token (and disables
  Copy/Download while any error-severity diagnostic exists); hand-written loops should avoid them
  for the same reason.

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

Rules and "Try it" come before action bindings and the step budget, which are collapsed by
default behind an "Advanced" disclosure — it opens itself the moment a diagnostic points at
an outcome or the step budget, and is never auto-closed once you've opened it. A row of task
presets ("Start from:", alongside "Start blank") seeds the whole form for a common shape —
document improvement, condition-based routing, preparation, implementation, or implementation
with verification — switching mode first if the preset needs one; applying a preset is one
undoable edit, the same as any other change. The implementation-with-verification preset routes
`implement` to a `verify` step that runs a shell command you configure (it receives the issue
ID as its first argument, then any args you add) and treats a zero exit as "acceptance checks
passed" — not the same claim as `/ll:verify-issues`'s issue-file validation, which the summary
below is careful to distinguish. Each skill picker (Decision Table's "Run a skill" and Issue
Lifecycle's per-verb skill dropdown) shows that skill's description and argument hint from the
stamped catalog, so you don't have to leave the page to check what a skill expects.

The page validates live (shadowed rules, unreachable outcomes, and unknown actions are flagged
in plain language, referencing the visible rule numbers) and emits loop YAML behind a
collapsed "View generated file" disclosure — the default view is a one-line plain summary
(in Issue Lifecycle mode, also a transition summary: which verbs are reachable, whether
verification is configured, and step budget expressed as attempts rather than a raw step
count) plus Copy/Download, a Save project / Open project pair, and a printed destination path
plus `ll-loop validate`/`ll-loop run` hint. The page seeds with a small runnable example on
load; edits then persist automatically per mode (reload and mode switching restore your draft —
a mode switch never discards work), with Undo/Redo (buttons or Ctrl/Cmd+Z / Ctrl/Cmd+Shift+Z)
walking back through the whole session's edits. On a page served by `ll-artifact serve`, drafts are kept per project workspace, so two projects at the same address never restore each other's work. "Start blank" is the only control that
discards a mode's draft, and even it pushes an Undo entry first. Its grammar, design-token
theme, and skill catalog are **stamped from this project at generation time** (including the
project's configured `active_theme`, which the page honors ahead of OS light/dark preference),
so regenerate the file to pick up new skills or grammar changes.

Both light and dark palettes are embedded, and native controls (selects, inputs) follow the
page's selected theme rather than the OS preference. Status and primary-button colors come from
`color.status.*` and `color.action.primary-text` in your token profile; a token profile that
predates these keys (or a partial `DESIGN.md`, or disabled tokens) still renders readable
built-in defaults, and your own custom token values are never overwritten.

**Builder vs. `edit-routes`:** the builder composes a new loop and exports YAML; "Save project"
/ "Open project" round-trip its own authoring state (all three modes' drafts, in a versioned
JSON envelope) so you can pause and resume a builder session, but that project file is not a
loop YAML and the builder does not read an *existing* loop YAML back in. `ll-loop edit-routes`
(below) is the round-trip editor for a loop that already exists. Use the builder to create
(pausing/resuming with Save/Open project as needed); use `edit-routes` to revise.

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

**Connected authoring & submission (`ll-artifact serve --policy-builder`, FEAT-3504).**
The visual builder can also be served at a same-origin route instead of exported to a file:
a maintainer picks a project issue, reviews the frozen `issue_lifecycle` policy, and submits
it for host approval (`ll-queue run --id ID --approve` runs it, `ll-queue cancel` rejects it)
without leaving the browser. This is a **Level 2 (project-local)** render target per
[ARTIFACT_CONTROL_LEVELS.md](../reference/ARTIFACT_CONTROL_LEVELS.md#declared-levels-by-render-target) —
the page can enqueue a request but never run or drain one itself. It guarantees an immutable
**submitted YAML snapshot** (verified by exact-byte SHA-256 at submission time) executed
against the project's **current** dependencies when the host approves it — not reproducible
execution, and not approval-time byte re-verification of the persisted file. See
[CLI.md § ll-artifact serve](../reference/CLI.md#ll-artifact-serve) for the full connected-route
contract; the served page's own review/submit/status UI is out of this guide's scope.

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
progress from refine to a re-scored `confidence_score`.

**Terminal destinations (ENH-3492).** A rule, the fallback, or a verb's follow-up may also route
straight to one of three built-in destinations instead of a verb: `stopped` and `skipped` are
success terminals (no `failure:` key); `needs_attention` is a failure terminal (`failure: true`).
Unlike verbs, destinations are never actionable and can't carry a skill/action — reaching one via
a verb's follow-up still runs that verb's own action first, then routes to the destination instead
of continuing the verb chain. Hitting the step budget (`on_max_steps`) always lands on
`needs_attention`, whether or not anything else in the loop references it. `implement`'s help text in the builder
calls out that `ll-auto` re-applies your project's own `commands.confidence_gate.readiness_threshold`
and exits non-zero (routing to `failed`) below it; add `--force-implement` to its args to bypass
that gate. Only verbs actually reachable — targeted by a rule, the fallback, or the `goto` target
of an already-reachable verb — are emitted into the saved YAML; the rest are simply left out.

**Structural transition graph (FEAT-3501).** Below the transition summary, a graph panel lists
every dispatch/goto/rescore/terminal edge, one line per node with outgoing edges, driven by the
same `analyzeTransitions(model)` analysis the summary itself is built from — so the two can never
disagree. A `goto` chain that cycles back on itself is flagged as a warning (self-loops included);
a `rescore` route back to scoring is shown as informational, not a warning, since every preset and
the seeded example route this way normally. An outcome verb that's referenced by a `goto` from
elsewhere in the model but still unreachable is flagged as a warning; a verb the model simply never
references at all is not — that's the normal shape of a preset that intentionally leaves verbs
unused (e.g. "Preparation" never reaches `implement`/`verify`). The graph makes **no claim about
what actually happens when the loop runs** — it shows which routes are *authored*, not which ones
execute or terminate, and it deliberately omits the two *implicit* routes every state carries:
`on_max_steps` → `needs_attention` and each state's own `on_error: failed`. A structural cycle is
therefore never evidence that a run will loop forever, and an unreachable outcome is never evidence
of a bug — both are prompts to double-check intent before exporting, nothing stronger. The graph is
a plain text/list rendering, not an SVG/canvas diagram.

**Seeded example** (also the Use Case this mode ships with):

```
status:==done -> verify
severity:==critical & review_status:==approved -> implement
confidence_score:>=85 -> implement
confidence_score:<85 -> refine
* -> gate
```

On an unscored issue this runs gate (writes `confidence_score`) → refine → gate again → implement
once the score clears 85, bounded by `on_max_steps: needs_attention` if the refine/gate cycle
never converges. `status:==done -> verify` only fires on a *later* run against the same issue,
since `implement` stops the current run.

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

### Scenario Suites (offline)

Every builder mode has a **Scenarios** panel below Try it: named, saved test cases you build up
while authoring, then re-run as a batch — offline, with **no skill, shell, LLM, or issue mutation
ever executed**. This is separate from Try it (which shows the live winner for one sample as you
type); a scenario is a persisted, independently authored case with its own expected outcome, so
"did I just break this" survives past the current editing session.

**Authoring a case.** Click **+ Scenario** to add one, name it, and fill in its input — one field
per current dimension in Decision Table mode, a pasted frontmatter block in Issue Lifecycle mode
(the same fence-optional text Try it accepts), or a single integer aggregate score in Rubric mode.
Set an **expected target** from the dropdown (the destinations your current policy can actually
reach); leaving it at "— unasserted —" means the case runs and reports its actual result without
being judged pass/fail. Decision Table and Issue Lifecycle cases can additionally pin an
**expected rule index** (which authored rule, by position, should win) or check **derived
fallback** (asserts the winner is the catch-all your policy falls back to when no rule matches,
not an authored rule) — the two are mutually exclusive. **Reconfirm expectation** adopts whatever
the case currently evaluates to as its new expected result; nothing adopts that automatically, so
an expectation only ever changes when you explicitly ask it to.

**Run all** evaluates every case through the same rule-compiler and evaluator the page's Try it
panel and the emitted loop's dispatch logic share, and reports, per case:

- **pass** / **fail** — the actual result matched (or didn't) the expectation you set.
- **unasserted** — no expected target set; the actual result is shown for inspection only.
- **unasserted (needs review)** — the case pins a rule index, but the rule table has changed
  (reordered or edited) since you last reconfirmed it. The prior expectation is kept, visibly
  marked stale, rather than silently re-pointed at whatever rule now sits at that position.
- **error** — the case's input doesn't match its mode's shape (e.g. a non-numeric decision-table
  value, unsupported frontmatter syntax, a non-integer rubric aggregate), or its expected target
  no longer names a destination your current policy can reach. Errors are never silently treated
  as a pass, a fail, or "no match."

A suite total (passed/failed/unasserted/errors) and a routing-coverage summary appear once you
run: which rule indexes actually won at least one case, which were merely evaluated (visited but
lost — a rule two cases both fail past is "evaluated," never "covered"), which authored rules no
case has ever won, and whether the derived fallback was exercised. Rubric mode reports high/medium/
low branch coverage instead. Coverage counts only cases that routed successfully — an error case
contributes nothing.

**Editing invalidates.** Changing anything about the policy (a rule, a dimension, an outcome) —
or a case's own input or expectation — clears the displayed results back to "not yet run"; a
result is derived from the policy and input at the moment you ran it, never a saved verdict about
the case itself. Re-run after any edit to see current status.

**Persistence** follows the same per-mode draft/undo model as the rest of the page: a suite is
part of its mode's draft, survives Save/Open/reload/mode-switch, and "Start blank" / applying a
preset clears only that mode's suite (one Undo restores it, along with the model it replaced).

#### Suggest cases

**Suggest cases** adds deterministic boundary cases for the active draft in one step — no expected
outcome is invented, so every added case stays *unasserted*. Decision Table and Issue Lifecycle
modes generate, per authored rule (in rule order): one *satisfying* case, one-unit boundary probes
(`t-1`, `t`, `t+1`) for each numeric predicate, and a *missing-field* case per predicate that
omits its field; a trailing *fallback* case is added only when no earlier case already reaches
the derived fallback. Rubric mode adds the integer neighbours of both thresholds. Each case's
name records why it exists and which rule it actually wins — an earlier rule can capture a later
rule's case, and the label says so.

Some rules cannot be solved and are skipped rather than approximated: contradictory or
impossible constraints (`score > 50 AND score < 50`), non-finite numeric literals, and Decision
Table rules on `string` dimensions (scenario input accepts only booleans and numbers there).
Lifecycle boolean and list fields get no missing-field case, because an absent boolean or list
already encodes as `false` / an empty list.

The action is idempotent: cases whose encoded scores already exist in the suite (including empty
inputs) are not added again, formatting differences are ignored, and numeric spellings such as
`85`, `85.0`, and `8.5e1` deliberately count as different cases. Adding cases is one Undo; if
nothing new would be added, no history entry is made.

#### Import an issue file

In Issue Lifecycle mode, **Import issue file** reads a local issue `.md` file and adds it as one
unasserted case. Only the opening `---` frontmatter block is read (a leading BOM and CRLF line
endings are fine); the Markdown body is never inspected. Multi-line values under fields that do
not affect routing — a wrapped `title:` or a `cancelled_reason: |` block — are ignored, but a
multi-line value under a field your policy routes on is rejected with a message naming that field.
A missing or unclosed `---` fence, unsupported frontmatter, or a read failure reports a
diagnostic and leaves the suite unchanged. The case is named from the file's `id`, else its
filename, and the import is one Undo.

An import is bound to the project state when you choose the file: if you edit, undo/redo, switch
modes, apply a preset, or open another project before the read finishes, the result is discarded
with a message. Choosing a second file before the first finishes imports only the second. **Open
project** has the same guard.

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
  that is not listed in `context.rubric_dimensions`, not encoded in
  `context.frontmatter_dimensions` (the Issue Lifecycle Mode / FEAT-3474 `name:type|...`
  source — see below), and not written as `rubric-dim-<name>.txt` by a shell state is
  silently inert at runtime — the dimension never reaches the scores dict, so `==` / `>=` /
  `<=` / `<` / `>` predicates on it can never match and routing falls through to the
  catch-all. All three sources are normalized the same way (lowercase, spaces→hyphens)
  before comparison. Predicate dims must be in **normalized form** to match the score keys
  written by `policy_parse_scores`; `Has Citations` in a predicate is inert even if
  `Has Citations` is listed in `rubric_dimensions` (the score key is `has-citations`). Set
  `policy_dims_scored_ok: true` at the loop top-level to suppress this check when a
  dynamically-named shell scorer makes static detection impossible.

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
   ll-loop run policy-refine --context subject=artifact.md
   ```

## See Also

- [Loops Guide](LOOPS_GUIDE.md) — FSM authoring fundamentals, evaluators, the `/ll:create-loop` wizard
- [Built-in Loops Reference](LOOPS_REFERENCE.md#built-in-fragment-libraries) — the full fragment-library catalog, including `lib/policy-router.yaml` and `lib/rubric-router.yaml`
- [Harness Optimization Guide](HARNESS_OPTIMIZATION_GUIDE.md) — the MR-4 routing rule and other meta-loop guardrails
- [CLI Reference: `ll-loop edit-routes`](../reference/CLI.md) — complete flag and exit-code reference
- [CLI Reference: `ll-loop validate` / `ll-loop run`](../reference/CLI.md) — validate routing before executing the loop
- [API Reference](../reference/API.md) — `little_loops.fsm.policy_rules` (rule grammar) and `little_loops.fsm.route_table` (the edit-routes lens)
