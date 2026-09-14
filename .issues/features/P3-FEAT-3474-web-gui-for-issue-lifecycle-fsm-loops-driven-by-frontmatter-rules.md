---
id: FEAT-3474
type: FEAT
title: Web GUI for issue-lifecycle FSM loops driven by frontmatter rules
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-14'
captured_at: '2026-09-14T17:11:03Z'
parent: EPIC-3299
---

# FEAT-3474: Web GUI for issue-lifecycle FSM loops driven by frontmatter rules

## Summary

A self-contained `.html` GUI (`file://`, no install) that lets a user author their
own simplified issue-lifecycle FSM loop — prepare, refine, gate, implement, verify
— driven by an Issue file's YAML frontmatter, without hand-writing FSM YAML. This
is a **third grammar/mode** alongside FEAT-2301's existing `policy-router` and
`rubric` modes on the same self-contained-HTML builder shell (EPIC-3299), not a
generator for `scripts/little_loops/loops/autodev.yaml` itself.

## Current Behavior

No GUI exists for authoring an issue-lifecycle-shaped loop. Today a user who wants
an autodev-like loop for their own issue conventions must either hand-write FSM
YAML from scratch, or copy and heavily edit `autodev.yaml` (a large, tightly
coupled file with little-loops-specific assumptions throughout).

## Expected Behavior

A `policy-router-builder.html.tmpl`-style page (or a new mode on it) where:

- **Subject** is an Issue file's YAML frontmatter (as in `.issues/*.md`), not an
  arbitrary artifact.
- **Dimensions** in the rule builder are frontmatter fields:
  - little-loops' own built-in fields (`status`, `priority`, `blocked_by`,
    `decision_needed`, `confidence_score`, `outcome_confidence`,
    `deferred_reason`, etc.) as first-class known dimensions with typed operators,
    mirroring FEAT-2301's numeric/boolean dimension-type restriction (`opsForType`).
  - PLUS arbitrary user-declared **generic** frontmatter fields — a consuming
    project with its own custom frontmatter schema should be able to add a field
    name and use it as a rule dimension without little-loops needing to know about
    it in advance. This is the key differentiator from a little-loops-only tool.
- **Actions** per rule/outcome map onto the issue-lifecycle verbs: prepare,
  refine, gate, implement, verify — presumably backed by existing skills/commands
  (`/ll:refine-issue`, `/ll:wire-issue`, `/ll:confidence-check`,
  `/ll:manage-issue`, `/ll:verify-issues`, `ll-issues check-readiness`, `ll-auto
  --only`), the same way FEAT-2301's action authoring already offers "run a
  skill" from an emit-time skill catalog dropdown.
- Reuses FEAT-2301/FEAT-2390's shipped patterns where they fit (self-contained
  `file://` HTML, ordered reorderable rule list, pinned "Otherwise" footer,
  demoted YAML, seeded example, theme handling, pure-function `.mjs` core +
  `node --test` gate, jargon-denylist for on-screen labels) rather than
  reinventing the shell.

## Motivation

`autodev.yaml` (2652 lines) is little-loops' own hand-tuned production loop for
driving issues through prepare → refine → gate → implement → verify. It is not a
realistic target for a rules-GUI to reproduce faithfully — it has bespoke queue
management, decision/blocker/gate pre-flight checks, repair cycles, rate-limit
handling, and infra-vs-quality failure classification built up over dozens of
issues. But its *shape* — route an issue through lifecycle stages based on
frontmatter conditions — is a pattern other users (and other little-loops
consumers with their own issue conventions) plausibly want a smaller, self-service
version of, the same way FEAT-2301 gave non-experts a GUI for the `policy-router`
grammar instead of hand-written `route:` maps.

FEAT-2301/FEAT-2390 already proved the shell: ordered/reorderable first-match rule
list read as plain sentences, pinned non-input catch-all, demoted-YAML view,
seeded example, jargon-denylist, pure-function core + `node --test` conformance
gate. This issue asks: what's the smallest issue-lifecycle-specific grammar that
reuses that shell and engine, without trying to clone autodev's full complexity?

## Proposed Solution

Extend the existing self-contained HTML builder shell rather than building a new
one: `policy_builder_core.mjs` already dispatches on a `mode` field
(`decision_table` in `blankModel()` at `policy_builder_core.mjs:300` and
`seedExample()` at `:247`, both consumed by `serializeLoopYaml()` at `:645`,
which also branches on `mode === "rubric"`). This issue adds a third mode
(working name: `issue_lifecycle`) alongside those two:

- Dimension picker offers little-loops' known frontmatter fields (`status`,
  `priority`, `blocked_by`, `decision_needed`, `confidence_score`,
  `outcome_confidence`, `deferred_reason`) as typed dimensions, mirroring
  FEAT-2301's `opsForType` numeric/boolean operator restriction, plus a
  "custom field" affordance letting the user name an arbitrary frontmatter key
  and declare its type.
- Outcome/action picker offers the five lifecycle verbs (prepare, refine,
  gate, implement, verify) as first-class actions, each backed by an existing
  skill/command slug from the same emit-time skill catalog FEAT-2301 already
  surfaces for its "run a skill" action.
- The emitted-artifact shape (standalone FSM loop YAML vs. a policy config
  consumed by a shared sub-loop) is the open question below and is not decided
  by this section — `/ll:refine-issue` should resolve it before implementation
  starts.

## Integration Map

### Files to Modify
- `scripts/little_loops/templates/policy_builder_core.mjs` — add the
  `issue_lifecycle` mode branch to `blankModel()`, `seedExample()`, and
  `serializeLoopYaml()`
- `scripts/little_loops/templates/policy-router-builder.html.tmpl` — add the
  mode's dimension picker and action picker UI
- `scripts/little_loops/cli/artifact/policy_builder.py` — wire the new mode
  into whatever CLI entry point emits/validates the builder artifact

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/artifact/__init__.py` — re-exports/registers
  `policy_builder.py`; confirm the new mode doesn't need a separate CLI flag
- `docs/guides/POLICY_ROUTER_GUIDE.md` and `docs/reference/CLI.md` — both
  document the existing `policy-router`/`rubric` modes and will need a third
  entry

### Similar Patterns
- `scripts/tests/js/policy_validator.test.mjs` — the `node --test` conformance
  pattern this issue's own "Reuses" list commits to following for the new mode

### Tests
- `scripts/tests/test_policy_builder_emit.py` and
  `scripts/tests/test_enh3035_artifact_template_kit.py` — extend with
  `issue_lifecycle`-mode cases the same way they cover `decision_table`/`rubric`
- `scripts/tests/test_policy_builder_node_gate.py` — the pytest wrapper that
  shells out to `node --test`; already generic across modes, no change
  expected unless new `.mjs` test files are added

### Documentation
- `docs/guides/POLICY_ROUTER_GUIDE.md` — add the new mode alongside
  `policy-router`/`rubric`

### Configuration
- N/A — no `.ll/ll-config.json` schema changes anticipated

## Implementation Steps

1. Resolve the Open Design Question (Option A vs. B) via `/ll:refine-issue`
   before scoping further — the emitted-artifact shape determines the rest of
   this list.
2. Add the `issue_lifecycle` mode to `policy_builder_core.mjs` (model shape,
   `seedExample`, `serializeLoopYaml` branch) with `node --test` coverage.
3. Add the mode's UI to `policy-router-builder.html.tmpl` (frontmatter
   dimension picker with built-in + custom fields, lifecycle-verb action
   picker).
4. Wire the mode into `policy_builder.py`/CLI as needed and update
   `POLICY_ROUTER_GUIDE.md`.
5. Verify by authoring the Use Case scenario's example rules in the GUI and
   confirming the emitted artifact runs (or validates, per the chosen
   architecture) end to end.

## Impact

- **Priority**: P3 - self-service tooling for other little-loops consumers,
  not blocking any in-repo workflow (little-loops itself keeps hand-tuned
  `autodev.yaml`).
- **Effort**: Large - a new grammar/mode on an existing shell, gated on an
  unresolved architecture question (Open Design Question below) plus new
  `node --test` coverage.
- **Risk**: Low - additive third mode alongside `decision_table`/`rubric`;
  does not modify either existing mode's behavior.
- **Breaking Change**: No

## Open Design Question (do not resolve unilaterally — surface for refine-issue / confidence-check)

**What does the GUI actually emit, and how does that map to runnable automation?**

- Option A: a standalone FSM loop YAML (like `policy-router`/`rubric-router` do)
  that the user runs via `ll-loop run <name>`. Given autodev's complexity, safely
  generating a loop that handles queueing, retries, and rate-limits from a flat
  rule table is a much bigger lift than policy-router's flat decision table — this
  may not be achievable at the same "structurally unrepresentable errors" quality
  bar FEAT-2301 held itself to.
- Option B: a smaller, more constrained artifact — e.g. a per-issue-type policy
  config consumed by an existing generic loop (so the GUI authors *policy*, not a
  full bespoke FSM), trading flexibility for safety/correctness.

This issue intentionally does not pick one — refinement should investigate
whether autodev's queue/retry/rate-limit machinery can be factored into a reusable
sub-loop the GUI's output calls into (Option A made safe), or whether Option B is
the right ceiling for a rules-GUI in this domain.

## Acceptance Criteria

- [ ] The GUI is a single self-contained `.html` file that opens over `file://`
  with no install step and no network dependency, matching FEAT-2301's shell.
- [ ] A user can add a rule dimension for any of little-loops' built-in
  frontmatter fields (`status`, `priority`, `blocked_by`, `decision_needed`,
  `confidence_score`, `outcome_confidence`, `deferred_reason`) with typed
  operators appropriate to that field's type.
- [ ] A user can also declare an arbitrary custom frontmatter field name (not
  in the built-in list) and use it as a rule dimension with a chosen type,
  without little-loops needing prior knowledge of that field.
- [ ] Each rule's outcome maps to one of the five lifecycle actions (prepare,
  refine, gate, implement, verify), selectable from an emit-time skill/command
  catalog the same way FEAT-2301's "run a skill" action works.
- [ ] Rules are ordered/reorderable and read as a first-match list with a
  pinned non-input "Otherwise" catch-all, per FEAT-2301/FEAT-2390's shipped
  shell conventions.
- [ ] The new mode's pure-function core logic ships with `node --test`
  conformance coverage, gated into `python -m pytest scripts/tests/` the same
  way `test_policy_builder_node_gate.py` gates the existing modes.
- [ ] The GUI does not attempt to reproduce `autodev.yaml`'s queue/retry/rate-
  limit/repair-cycle machinery (see Non-goals).

## Program Design

The concrete signatures below depend on which side of the Open Design Question
(Option A vs. B) `/ll:refine-issue` resolves; documented here at the level
resolvable without that decision, anchored to existing identifiers.

### Types

- `mode: "issue_lifecycle"` — new literal value for the existing `model.mode`
  field already handled in `blankModel()` (`policy_builder_core.mjs:300`),
  alongside today's `"decision_table"` and `"rubric"`
- `dimension: {field: string, kind: "builtin" | "custom", type: "string" |
  "number" | "boolean"}` — extends the existing dimension shape with a
  `kind` discriminator so custom (`kind: "custom"`) fields skip the
  built-in-field validation `opsForType` applies to known fields

### Signatures

- `blankModel(mode: "issue_lifecycle") -> Model` — new mode branch in the
  existing function (`policy_builder_core.mjs:300`)
- `seedExample(mode: "issue_lifecycle") -> Model` — new mode branch in the
  existing function (`policy_builder_core.mjs:247`)
- `serializeLoopYaml(model: Model) -> string` — extend the existing
  `mode === "rubric"` branch (`policy_builder_core.mjs:645`) with an
  `issue_lifecycle` branch; exact output shape is the Open Design Question

### Call Path

`cmd_policy_builder` -> `_load_skill_catalog` (both
`scripts/little_loops/cli/artifact/policy_builder.py`) -> renders
`policy-router-builder.html.tmpl` with the `issue_lifecycle` mode's
`blankModel`/`seedExample`/`serializeLoopYaml` branches embedded from
`policy_builder_core.mjs` -> emitted artifact consumed by `ll-loop run`
(Option A) or a shared sub-loop (Option B)

## Use Case

A little-loops consumer has their own issue frontmatter conventions (e.g. a
custom `severity` field, or a `review_status` field that isn't part of
little-loops' schema) and wants a lightweight lifecycle loop — "when severity is
critical and review_status is approved, implement immediately; otherwise gate on
confidence_score >= 70" — without hand-writing FSM YAML or understanding
`autodev.yaml`'s internals. They open the GUI over `file://`, add their custom
frontmatter field as a dimension, author 2-3 rules mapping to prepare/refine/gate/
implement/verify actions, and get something runnable.

## Non-goals (initial scope guess — confirm during refinement)

- Not a generator for `autodev.yaml` itself, and not a replacement for it in this
  repo.
- Not attempting to reproduce autodev's repair-cycle/decision-resolution/
  rate-limit-handling machinery in v1 — see Open Design Question.
- No round-trip editing of existing loops (consistent with FEAT-2301's scope cut).

## Related Key Documentation

- `scripts/little_loops/loops/autodev.yaml` — the production loop whose *shape*
  (not implementation) motivates this issue; explicitly out of scope to clone.
- `.issues/features/P3-FEAT-2301-self-contained-html-builder-for-policy-router-and-rubric-fsm-loops.md`
  — shipped sibling grammar/mode on the same builder shell; this issue's
  "Reuses" list is copied from its shipped ACs.
- `scripts/little_loops/templates/policy-router-builder.html.tmpl` /
  `policy_builder_core.mjs` — the existing shell + pure-function core this issue
  should extend or sit alongside.

## Status

**Open** | Created: 2026-09-14 | Priority: P3


## Session Log
- `/ll:format-issue` - 2026-09-14T17:26:12 - `935702d4-fd79-4fcc-b1ed-24d764f51e14.jsonl`
- `/ll:capture-issue` - 2026-09-14T17:11:14 - `b2c42f0a-8e12-495a-9786-d532e21cd8a7.jsonl`
