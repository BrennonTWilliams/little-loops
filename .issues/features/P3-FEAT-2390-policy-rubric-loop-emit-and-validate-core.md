---
id: FEAT-2390
title: Policy/rubric loop emit + validate engine (headless core)
type: FEAT
priority: P3
status: open
discovered_date: 2026-06-28
discovered_by: rescope-feat-2301
relates_to:
- FEAT-2301
- ENH-2309
- ENH-2334
blocks:
- FEAT-2301
confidence_score: 95
outcome_confidence: 88
score_complexity: 10
score_test_coverage: 6
score_ambiguity: 6
score_change_surface: 14
decision_needed: false
---

# FEAT-2390: Policy/rubric loop emit + validate engine (headless core)

## Summary

The **testable half** of the policy-router builder: a headless engine that turns a
structured loop *model* into valid `policy-router` / `rubric-router` FSM YAML, validates
a rule table (shadow / catch-all / unknown-action / numeric-coercion), and stamps
project-derived data (design-token CSS vars, the canonical predicate grammar, the skill
catalog) into a template. **No interaction design, no DOM, no UX judgement** — every
deliverable here is provable by a unit test or a `ll-loop validate` exit code.

This is split out of FEAT-2301 so the correctness work has its own success criteria and
cannot be used to declare the *UI* done (the failure mode that shipped the sub-par
worktree build — see FEAT-2301 § Rescope). FEAT-2301 is the human-facing shell that
consumes this engine.

## Why a separate issue

"Emit correct YAML" is compiler work: tractable, fully testable, engineer-legible. "Be a
pleasant authoring surface" is interaction design: fuzzy, needs iteration against real
use. Bundled, the legible half reaches 98% readiness while the fuzzy half is never
designed. Split, each half is gated by criteria it can actually fail. This issue owns the
half a test can prove; FEAT-2301 owns the half a person has to feel.

## Current state

Most of this engine already exists on branch `feat-2301-self-contained-html-builder`
(commit `08e272b6`). This issue's job is to **isolate, harden, and gate** it — not to
build it from scratch. Already present on that branch:

- `fsm/policy_rules.py: grammar_spec()` + `_py_pattern_to_js()` (ENH-2334 single-sourced
  the operator grammar; this exposes it).
- `design_tokens.py: render_as_css_vars_themed(light, dark)`.
- `templates/policy_builder_core.mjs` — the JS serializer + validator engine.
- `cli/artifact.py` — the `ll-artifact policy-builder` emit/stamping path.
- `tests/fixtures/policy_builder/conformance_corpus.json`, `tests/js/policy_validator.test.mjs`,
  `tests/test_policy_builder_*.py`, `tests/test_policy_rules.py`.

What is **not** done and is the real remaining work: ratifying + wiring the node test
runner so the JS logic half is actually pinned (it is currently "pinned in principle"),
and confirming where the drift-guard/corpus tests execute.

## Scope

In scope (the engine + its gates):

1. **Grammar as single source.** `grammar_spec()` exposes `sorted(_ALL_OPS)` /
   `sorted(_ORDERED_OPS)` / `_PRED_PATTERN.pattern`; `_py_pattern_to_js()` rewrites Python
   named groups `(?P<x>…)` → JS `(?<x>…)`. The emit path injects these as a JSON `<script>`
   block; no operator literal or regex is hand-written in any template.
2. **YAML serializer** (both modes). Decision Table → `policy-refine.yaml` shape
   (`import:` rubric-then-policy, `context.policy_rules`, `score → parse_scores →
   policy_dispatch`, generated `route:` map with `_:` / `_error:`). Rubric → `rubric-refine.yaml`
   shape (`category`/`input_key`/`required_inputs`, two thresholds, no `route:` map). Omit
   `visibility:`.
3. **Boolean-dimension encoding.** Booleans emit into `rubric_dimensions` with a 0/100
   scoring instruction; predicate compiles `==true → >=50`, `==false → <50`. No literal
   `==true` in output; no fragment-runtime change.
4. **Dimension-name normalization.** Header, injected scoring instruction, and emitted
   predicate share one `lowercase + whitespace→hyphens` transform (or the model layer
   restricts names to `[a-z0-9-]`) — closing the dead-predicate class.
5. **MR-4 unrepresentability.** The model requires every action state to declare
   `terminal: true` or a `next:`/`route:` target, so emitted YAML never triggers
   `_validate_partial_route_dead_end()`.
6. **In-browser validator as an importable ES module** (`policy_builder_core.mjs`): shadow
   detection, catch-all detection, predicate eval, numeric-coercion branch — same source
   shipped in the page and imported by the node test.
7. **Emit/stamp path** (`ll-artifact policy-builder`): load `BRConfig`, stamp themed CSS
   vars + grammar + skill catalog into the FEAT-2301 template, write
   `<artifacts.default_output_dir>/policy-router-builder.html`. Degrade to neutral CSS
   blocks when tokens are disabled. **Stamp `active_theme` so the page can honor it** (the
   worktree build omitted this — see FEAT-2301 § Rescope, theme bug).

Out of scope: the HTML template, CSS, and all interaction/UX (FEAT-2301); fragment-runtime
changes to `lib/policy-router.yaml` / `lib/rubric-router.yaml`; round-trip editing of
existing loops (`ll-loop edit-routes`); nested/chained policy tables.

## Acceptance Criteria

- [ ] `grammar_spec()` returns `sorted(_ALL_OPS)`, `sorted(_ORDERED_OPS)`, and
  `_PRED_PATTERN.pattern`; `_py_pattern_to_js()` round-trips a predicate corpus identically
  to `_PRED_PATTERN` (unit-tested).
- [ ] A model → YAML emit for each mode passes `ll-loop validate` with zero ERROR-severity
  findings (catch-alls present, route map complete, no MR-4 dead-ends). Smoke test follows
  `test_fsm_fragments.py` (`load_and_validate` + `validate_fsm`, ERROR filter).
- [ ] A boolean dimension is emitted into `rubric_dimensions` with a 0/100 instruction and
  compiles to `>=50` / `<50`; no literal `==true` appears in output.
- [ ] A mixed-case / spaced dimension name is normalized identically across header, scoring
  instruction, and predicate (regression test for the dead-predicate class).
- [ ] **Drift guard (CI-gated):** operator sets embedded in generated HTML equal the Python
  sets, and the translated regex accepts/rejects the corpus identically to `_PRED_PATTERN`.
- [ ] **JS logic pinned (CI-gated):** a `node:test` suite
  (`tests/js/policy_validator.test.mjs`, zero new deps, Node ≥22) runs the shared
  conformance corpus against `policy_builder_core.mjs` and asserts target selection +
  shadow warnings match the Python fixtures. *This is the criterion that closes the old
  68 outcome-confidence gap — it must actually execute, not be aspirational.*
- [ ] **CI location is real, not aspirational:** the drift-guard + corpus tests (Python and
  node) run on each change at a named location. If no `.github/workflows/` exists, add one
  or document where they run; an unenforced gate does not count as met.
- [ ] `render_as_css_vars_themed(light, dark)` emits scoped `:root` + `[data-theme=dark]`
  blocks, all aliases resolved to hex, `_`-prefixed metadata keys filtered.
- [ ] The emit path stamps `active_theme` from config into the generated page (so FEAT-2301
  can open in the configured default theme).

## Integration Map

Files (already touched on the branch — confirm against canonical references):
`fsm/policy_rules.py`, `design_tokens.py`, `cli/artifact.py`, `cli/__init__.py`,
`pyproject.toml` (`ll-artifact`), `config/{core,features}.py`, `config-schema.json`
(`artifacts.default_output_dir`), `templates/policy_builder_core.mjs`,
`tests/{test_policy_builder_*,test_policy_rules,test_design_tokens}.py`,
`tests/fixtures/policy_builder/*`, `tests/js/policy_validator.test.mjs`,
`docs/reference/CLI.md`, `docs/guides/POLICY_ROUTER_GUIDE.md`.

Canonical references the engine must defer to: `fsm/validation.py`
(`_validate_partial_route_dead_end`), `fsm/schema.py` (`RouteConfig.to_dict` →
`_`/`_error`), `loops/policy-refine.yaml`, `loops/rubric-refine.yaml`. `ll-loop validate`
remains the authoritative backstop.

## Impact

- **Priority**: P3 — foundation for the FEAT-2301 nicety; mostly built, needs isolation +
  the node gate.
- **Effort**: Small–Medium — most code exists on-branch; remaining work is the node test
  runner, the CI location decision, and confirming the split boundary.
- **Risk**: Low — additive; no fragment-runtime changes.
- **Breaking Change**: No

## Labels

`feature`, `loops`, `policy-router`, `design-tokens`, `tooling`, `engine`

## Decision History (migrated from FEAT-2301)

These engine-layer decisions were made under FEAT-2301 and moved here because they belong
to the testable half:

- **boolean-dim (2026-06-26)** — compile booleans to numeric 0/100 (`==true→>=50`); emit
  into `rubric_dimensions`; spun off ENH-2309 (gate flagging unscored policy dims).
- **grammar single-source (2026-06-26)** — stamp `grammar_spec()` + `_py_pattern_to_js`,
  drift-guard, shared conformance corpus; flagged `route_table.py` duplication → ENH-2334
  (done).
- **JS test runner (proposed 2026-06-26 → ratify here)** — Option A: zero-dep `node:test`
  on Node 22 consuming the shared corpus. This issue **ratifies and requires** Option A as
  an AC; that is the change that genuinely pins the JS logic half.
- **emit naming (2026-06-25)** — `ll-artifact policy-builder`, durable namespace for
  human-facing artifact generators.

## Session Log
- `rescope-feat-2301` - 2026-06-28 - Extracted the headless emit/validate engine from
  FEAT-2301 into this issue so correctness has its own gates and cannot stand in for UX
  done-ness. Ratified the node:test runner (Option A) as a required AC, closing the prior
  outcome-confidence gap. Most code already exists on `feat-2301-self-contained-html-builder`.
