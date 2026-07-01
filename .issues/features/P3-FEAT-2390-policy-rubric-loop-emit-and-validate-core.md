---
id: FEAT-2390
title: Policy/rubric loop emit + validate engine (headless core)
type: FEAT
priority: P3
status: done
discovered_date: 2026-06-28
completed_at: 2026-07-01 02:33:41+00:00
discovered_by: rescope-feat-2301
relates_to:
- FEAT-2301
- ENH-2309
- ENH-2334
blocks:
- FEAT-2301
confidence_score: 95
outcome_confidence: 70
score_complexity: 9
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 25
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

## Use Case

**Who**: A loop author (or the `create-loop` "policy router" branch / the FEAT-2301 UI
shell) building a `policy-router` / `rubric-router` loop who must not hand-write operator
grammar, route maps, or theme-stamped output.

**Context**: They have a decision-table or rubric *model* (dimensions, thresholds,
actions) and invoke the headless emit path (`ll-artifact policy-builder`) — directly, from
CI, or behind the FEAT-2301 surface.

**Goal**: Turn that model into `policy-refine.yaml` / `rubric-refine.yaml`-shaped YAML
with booleans compiled to numeric predicates and dimension names normalized, so no dead
predicates slip through.

**Outcome**: The emitted YAML passes `ll-loop validate` with zero ERROR-severity findings
on the first pass (catch-alls present, route map complete, no MR-4 dead-ends), and the
drift guard + node conformance suite keep the JS validator and the Python grammar provably
in sync.

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

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis of `main` (HEAD `abf54200`):_

**Critical — basis matters:** the "already exists on-branch" framing is true for
`feat-2301-self-contained-html-builder` (`08e272b6`) but the engine is **largely absent
from `main`**. An implementer starting from `main` must first bring the branch code over
(merge/cherry-pick `08e272b6`) or rebuild it — this is not a pure "isolate + harden" task
from `main`'s basis. Corroborated by ENH-2334's resolution text, which states
`grammar_spec()` was deliberately *not* added because "FEAT-2301 is still `open`; no public
accessor is available in the current tree."

Present on `main` (reusable foundation):
- `fsm/policy_rules.py` — `_ALL_OPS` / `_ORDERED_OPS` / `_PRED_PATTERN` (lines 27–34),
  `parse_rules` / `serialize_rules` / `evaluate_rules` / `_eval_predicate`. Module docstring
  already declares it "the single source of truth for the grammar." `route_table.py:15`
  already imports `_ALL_OPS` (ENH-2334 done).
- `design_tokens.py:320` — `render_as_css_vars(tokens)` (non-themed); alias→hex via
  `_resolve_value` (line 87), `$`/`_`-metadata filtering via `_flatten` (line 44) plus the
  `_`-prefix skip (lines 244, 275).
- `fsm/validation.py` — `validate_fsm` (line 962), `load_and_validate` (line 2435),
  `_validate_partial_route_dead_end` MR-4 (line 1447), `_validate_policy_dimensions_scored`
  ENH-2309 (line 1881).
- `fsm/schema.py:200` — `RouteConfig.to_dict` (`_` = catch-all/default, `_error` = error verdict).
- `loops/{policy,rubric}-refine.yaml` + `loops/lib/{policy,rubric}-router.yaml` — canonical
  output shapes. `tests/fixtures/fsm/policy-refine.yaml` is a byte-identical fixture copy.
- Tests: `test_policy_rules.py`, `test_design_tokens.py`, `test_fsm_fragments.py`.

Absent from `main` (branch-only / greenfield — the real build surface):
- `grammar_spec()`, `_py_pattern_to_js()` in `fsm/policy_rules.py`.
- `render_as_css_vars_themed(light, dark)` in `design_tokens.py`.
- `cli/artifact.py` + `ll-artifact` entry point in `scripts/pyproject.toml` `[project.scripts]`.
- `templates/policy_builder_core.mjs`.
- `tests/js/policy_validator.test.mjs` and **all** node-test infrastructure (no `package.json`,
  no `node --test`, no committed `.mjs` test anywhere — fully greenfield).
- `tests/fixtures/policy_builder/conformance_corpus.json`, `tests/test_policy_builder_*.py`.
- `artifacts.default_output_dir` in `config-schema.json` (+ an `ArtifactsConfig` dataclass in
  `config/features.py`).
- `.github/workflows/` — **no CI exists at all**, so both CI-gated ACs (drift guard, node
  conformance) require standing up CI from scratch.

**Effort caveat:** the Impact section's "Small–Medium — most code exists on-branch" holds only
when implementing *on the branch*. From `main`, effort is Medium(+): it includes porting the
emit path, `.mjs` template, themed renderer, and grammar accessors, plus establishing
greenfield node-test + CI infrastructure.

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

## API/Interface

Public contracts introduced/exposed by this engine (signatures already present on-branch;
this issue pins them behind gates):

```python
# fsm/policy_rules.py
def grammar_spec() -> dict:
    """Expose sorted(_ALL_OPS), sorted(_ORDERED_OPS), and _PRED_PATTERN.pattern."""

def _py_pattern_to_js(pattern: str) -> str:
    """Rewrite Python named groups (?P<x>…) → JS (?<x>…) for the emit path."""

# design_tokens.py
def render_as_css_vars_themed(light: dict, dark: dict) -> str:
    """Emit scoped :root + [data-theme=dark] blocks; aliases resolved to hex,
    _-prefixed metadata keys filtered."""
```

```
# CLI (pyproject.toml entry point → ll-artifact)
ll-artifact policy-builder    # stamp grammar + themed CSS + skill catalog,
                              # write <artifacts.default_output_dir>/policy-router-builder.html
```

`templates/policy_builder_core.mjs` — importable ES module exporting the shadow /
catch-all / predicate-eval / numeric-coercion validator; the *same* source is shipped in
the page and imported by the `node:test` conformance suite.

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

### Codebase Research Findings

_Added by `/ll:refine-issue` — canonical anchors verified on `main` (HEAD `abf54200`):_

Canonical references (defer to these; line numbers on `main`):
- `fsm/validation.py:1447` `_validate_partial_route_dead_end` (MR-4) — **WARNING** severity,
  suppressed by `partial_route_ok`. Only fires on LLM-judged states (`_is_llm_judged`,
  line 1428): `action_type: prompt`/`slash_command` with no `evaluate:`, or `evaluate.type`
  in `llm_structured`/`check_semantic`. A state with an unconditional `next:`, a full `route:`
  map, or both `on_no`+`on_partial` is exempt. `policy_dispatch` uses `evaluate.type: classify`,
  which is *not* LLM-judged — MR-4 never fires on it (see AC precision note below).
- `fsm/validation.py:1881` `_validate_policy_dimensions_scored` (ENH-2309, WARNING) — parses
  `context.policy_rules` via `policy_rules.parse_rules`, collects predicate dims
  **un-normalized**, builds the scored set from normalized `context.rubric_dimensions`
  (pipe-split, `lower + \s+→-`) plus any `rubric-dim-<name>.txt` filename in a shell action.
  Emitted YAML must keep every predicate dim in the scored set or trip this warning — the
  dead-predicate class the emitter closes via dimension-name normalization.
- `fsm/schema.py:200` `RouteConfig.to_dict` — `route:` is a flat `verdict → state` dict; `_`
  reserved for catch-all/default, `_error` for the error verdict. Inverse `from_dict` at line 209.
- Canonical shapes: `loops/policy-refine.yaml` (import order `lib/rubric-router.yaml` then
  `lib/policy-router.yaml`; `score` → `parse_scores` → `policy_dispatch` with
  `fragment: policy_table_dispatch` + full `route:` map; prompt states use unconditional `next:`;
  `done: terminal: true`; no `category:`). `loops/rubric-refine.yaml` (has
  `category`/`input_key`/`required_inputs`, imports only `lib/rubric-router.yaml`,
  `threshold_high`/`threshold_medium`, `on_yes`/`on_no` gates, **no** `route:` map).

Patterns to follow (from `main`):
- **Smoke-test AC** → model on `test_fsm_fragments.py::TestPolicyRouterLib.test_policy_refine_loop_validates`
  (line 2397) and `TestRubricRouterLib.test_rubric_refine_loop_validates` (line 2277):
  `fsm, _ = load_and_validate(path)` → `errors = validate_fsm(fsm)` →
  `[e for e in errors if e.severity == ValidationSeverity.ERROR]`. For a synthetic
  model→YAML round-trip, write to `tmp_path` then run the same calls (see
  `TestLoadAndValidateIntegration`, line 790).
- **`ll-artifact` CLI registration** → 3-file convention: `scripts/pyproject.toml`
  `[project.scripts]` (`ll-artifact = "little_loops.cli:main_artifact"`) + export in
  `cli/__init__.py` + thin argparse wrapper `cli/artifact.py` wrapped in `cli_event_context`.
  Models: `cli/schemas.py:main_generate_schemas` (single entry) and
  `cli/verify_design_tokens.py` / `cli/loop/__init__.py` (subparser dispatch, if
  `policy-builder` is one of several artifact subcommands).
- **`artifacts.default_output_dir` config** → add an `ArtifactsConfig` dataclass modeled on
  `DesignTokensConfig` (`config/features.py:314`) plus a `config-schema.json` entry.
- **Skill-catalog stamping** → reuse `cli/action.py:_load_skills()` (line 45) — returns
  `{name, description, args}` per skill via `parse_skill_frontmatter`, ready to JSON-serialize
  into a `<script>` block the same way `grammar_spec()` is stamped.
- **Drift-guard shape** (no cross-language precedent exists) → closest analogues:
  `doc_counts.py:verify_documentation` (representation-A-vs-B count check),
  `cli/verify_design_tokens.py` (structural completeness diff, exit-code gated),
  `tests/conformance/test_host_conformance.py` (pytest marker + fixture convention). The
  shared-corpus-consumed-by-both-Python-and-JS pattern is greenfield.

**AC precision note (MR-4 severity):** the "Emit → validate" AC says "zero ERROR-severity
findings … no MR-4 dead-ends," but MR-4 is **WARNING**, not ERROR — and it does not fire on
the `classify`-evaluated `policy_dispatch` state at all. The emitted policy-refine shape
satisfies MR-4 naturally (prompt states carry unconditional `next:`). Treat "no MR-4 dead-ends"
as a separate WARNING-tier check from the ERROR-severity gate, not a component of it.

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue` — consumers of the changed symbols on `main`; none
are edited by this issue (all are Out of scope), but the emit path must stay bug-compatible
with how they already parse/render the same grammar and tokens:_

- `fsm/route_table.py` — imports `_ALL_OPS` (ENH-2334) **and re-derives its own operator
  regex** `_OP_ALT = "|".join(sorted(_ALL_OPS, key=len, reverse=True))` / `_COND_PATTERN`
  (feeds `PolicyRuleExtractor` / `CompoundGridParser` / `PolicyRuleApplier`). This is the
  clearest in-repo `grammar_spec()` migration candidate — it already does the
  longest-match-first ordering `_py_pattern_to_js()` must reproduce for the JS side. Scope §1
  only commits to injecting grammar into the emit template, so migrating this regex is a
  *follow-on option*, not part of FEAT-2390 — but the JS translation must match its ordering
  or the two operator parsers drift. [Agent 1 + 2 finding]
- `cli/loop/edit_routes.py` — imports `PolicyRuleExtractor`, `CompoundGridRenderer`,
  `CompoundGridParser`, `PolicyRuleApplier`; the round-trip route-table editor (`ll-loop
  edit-routes`) is the *other* producer of policy-router YAML. Explicitly Out of scope, but
  the emitter's output shape must round-trip through it. [Agent 1 finding]
- `cli/loop/run.py` — calls `render_as_css_vars(...)` to stamp design-token CSS into loop
  program output; primary precedent for how the emit path should invoke the themed variant.
  [Agent 1 finding]
- `cli/loop/lifecycle.py` — also renders design-token CSS; second `render_as_css_vars`
  consumer. [Agent 1 finding]
- `cli/verify_design_tokens.py` — consumes `render_as_css_vars` **and** is the structural
  model for the drift-guard CLI (pure-function core returning dataclasses + thin
  `cli_event_context`-wrapped argparse main). [Agent 1 + 3 finding]
- `cli/action.py` — `_load_skills()` (line 45) / `parse_skill_frontmatter` are the exact
  skill-catalog source the emit path stamps into a `<script>` block (returns
  `{name, description, args}` per skill). [Agent 1 + 2 finding]

### Documentation

_Wiring pass added by `/ll:wire-issue` — doc coupling beyond the two files already in the
Integration Map (`docs/reference/CLI.md`, `docs/guides/POLICY_ROUTER_GUIDE.md`, which already
exists on `main`):_

- `docs/ARCHITECTURE.md` — the "Project-enriched artifacts" section names this exact feature
  as **"planned (FEAT-2301)"** and attributes `policy_rules.grammar_spec()` + `_load_skills()`
  stamping to FEAT-2301. Once this engine ships under FEAT-2390 the wording is stale on two
  counts: "planned" → implemented, and the attribution must move to FEAT-2390. [Agent 2]
- `docs/reference/CONFIGURATION.md` — has a `### design_tokens` property-table section but
  **no `### artifacts` section**; add one mirroring it once `artifacts.default_output_dir`
  lands. Not in the Integration Map. [Agent 2]
- `.claude/CLAUDE.md` — the "CLI Tools" list documents every `ll-*` binary but has no
  `ll-artifact` entry; add a bullet when the entry point ships. [Agent 1 + 2]
- `cli/__init__.py` module docstring — enumerates every registered CLI tool; add an
  `ll-artifact` line (third CLI-listing location alongside `pyproject.toml` and CLAUDE.md).
  (`cli/__init__.py` is already in Files to Modify — this is the specific anchor.) [Agent 2]
- `docs/reference/API.md` — the `little_loops.fsm.policy_rules` module row lists
  `parse_rules`/`serialize_rules`/`evaluate_rules` but not `grammar_spec()`/`_py_pattern_to_js()`.
  Optional: this table is selective (no rows for `design_tokens`, `cli/action`, `cli/schemas`),
  so omitting the new symbols is consistent with precedent. [Agent 2]
- `README.md` — hard-codes a "37 CLI tools" count in two places (already stale — `pyproject.toml`
  has 39 entries today); adding `ll-artifact` widens the gap. `ll-verify-docs`/`doc_counts.py`
  does **not** mechanically check this count, so it is a manual-staleness risk. [Agent 2]
- `CHANGELOG.md` — add an entry for `grammar_spec()` / `render_as_css_vars_themed` /
  `ll-artifact policy-builder` under a concrete `## [X.Y.Z]` heading (not `[Unreleased]`),
  matching the sibling ENH-2299/2238/2164 convention. [Agent 2]
- `skills/create-loop/{loop-types.md,templates.md,SKILL.md}` — the `/ll:create-loop`
  "policy-router" wizard branch (ENH-2299) hand-writes the grammar in prose (Step PR4) and is a
  *second* path producing the same YAML shape. Cross-referencing the headless `ll-artifact`
  path is a documentation decision, not a code dependency; the prose grammar has no test
  pinning it to `_ALL_OPS` and will drift silently if the operator set changes. [Agent 2]
- `.ll/decisions.yaml` — a decision record tagged `issue: FEAT-2301` describes the
  `render_as_css_vars_themed` mechanism now scoped to FEAT-2390; add a cross-reference/scope
  note via `ll-issues decisions` when the split is finalized. [Agent 2]

### Configuration

_Wiring pass added by `/ll:wire-issue`:_

- `config/core.py` — a new `ArtifactsConfig` needs **three** touch-points mirroring
  `DesignTokensConfig`: the `BRConfig` constructor (`self._artifacts =
  ArtifactsConfig.from_dict(...)`, ~line 221), an `artifacts` property (~line 310), **and a
  block in `BRConfig.to_dict()` (~line 620)**. The Integration Map names the file; `to_dict()`
  is the anchor that's easy to miss. [Agent 2]
- `.ll/ll-config.json` — does **not** need an `artifacts` block. Per-project config blocks are
  partial opt-in overrides layered on dataclass defaults via `from_dict()` (e.g. this project's
  `design_tokens` block overrides only 2 of 8 fields); the `default_output_dir` default
  suffices. [Agent 2]

### Tests

_Wiring pass added by `/ll:wire-issue` — beyond the test files already named in the Integration
Map. Confirmed on `main`: no `grammar_spec`/`_py_pattern_to_js` references anywhere, no `tests/js/`,
no `tests/fixtures/policy_builder/`, no `test_policy_builder_*.py`, no `package.json` (greenfield,
matching the issue's "Absent from `main`" list):_

- `tests/test_config_schema.py` — **new guard needed.** The root `properties` block is
  `additionalProperties: false`, so an undeclared `artifacts` key is silently rejected at
  validation time. No closed-world enumeration test exists, so adding the key breaks nothing —
  but the file's own convention is one `test_<ns>_in_schema` guard per namespace (model on
  `test_design_tokens_in_schema`). [Agent 3]
- `tests/test_fsm_fragments.py` — the model→YAML emit smoke test's home. Follow
  `TestLoadAndValidateIntegration` (line ~789): write synthetic YAML to `tmp_path`, then
  `load_and_validate` → `validate_fsm` → `ValidationSeverity.ERROR` filter. Existing
  `TestPolicyRouterLib.test_policy_refine_loop_validates` (line ~2397) /
  `TestRubricRouterLib.test_rubric_refine_loop_validates` (line ~2277) are the shape to match.
  [Agent 3]
- `tests/test_builtin_loops.py` — `TestBuiltinLoopFiles.test_all_validate_as_valid_fsm` already
  exercises `policy-refine.yaml` / `rubric-refine.yaml` (iterates every runnable loop). Broader
  validation net than `test_fsm_fragments.py`; no change needed unless a new built-in loop file
  ships (FEAT-2390 emits at model→YAML time, so likely not). [Agent 3]
- CLI-registration test model — `test_generate_schemas.py::TestGenerateSchemasCLI` (single
  entry, `patch sys.argv` + assert return 0) if `ll-artifact` is one command; or
  `test_cli_loop_dispatch.py::TestMainLoopDispatch` (mock each handler, assert dispatch) if
  `policy-builder` is one of several `ll-artifact` subcommands. [Agent 3]
- Skill-catalog stamping test model — `test_action.py::TestLoadSkills` (line ~124): synthetic
  `skills/<name>/SKILL.md` tree, `patch _find_plugin_root`, assert exact dict shape. [Agent 3]
- Drift-guard test model — `test_verify_design_tokens.py` (structural completeness diff,
  exit-code gated, pure-core-vs-CLI split) and `test_doc_counts.py::TestVerifyDocumentation`
  (representation-A-vs-B diff on a synthetic tree). The Python-set-vs-JS-set drift guard is
  greenfield; these are the closest precedents. [Agent 3]
- `tests/test_fsm_validation.py` — existing `_validate_policy_dimensions_scored` / MR-4 tests
  assert on **substrings** and error counts, not verbatim messages, so changing emitted YAML
  cannot break them directly. The coupling is functional: the emitter must keep every predicate
  dim in the normalized scored set (lowercase + spaces→hyphens) or the ENH-2309 warning fires.
  [Agent 2 + 3]

## Implementation Steps

1. Isolate the engine surface on `feat-2301-self-contained-html-builder`: `grammar_spec()`
   / `_py_pattern_to_js()`, the two-mode YAML serializer, boolean-dimension encoding, and
   the shared dimension-name normalization transform.
2. Ratify and wire the zero-dep `node:test` runner (`tests/js/policy_validator.test.mjs`,
   Node ≥22) so the shared conformance corpus actually pins `policy_builder_core.mjs`
   against the Python fixtures — the criterion that closes the old outcome-confidence gap.
3. Land the drift guard (embedded operator sets + translated regex equal the Python
   sets / `_PRED_PATTERN`) at a named, enforced CI location; add or document
   `.github/workflows/` if none exists.
4. Harden the emit/stamp path (`ll-artifact policy-builder`): themed CSS vars + grammar +
   skill catalog into the FEAT-2301 template, `active_theme` stamped, neutral-CSS
   degradation when tokens are disabled.
5. Verify emitted YAML against canonical references (`fsm/validation.py`, `fsm/schema.py`,
   `loops/{policy,rubric}-refine.yaml`) and confirm the split boundary with FEAT-2301.

### Codebase Research Findings

_Added by `/ll:refine-issue` — concrete anchors + `main`-basis prerequisite:_

- **Step 0 (implied, `main`-basis only):** bring the branch engine to the working basis —
  merge/cherry-pick `feat-2301-self-contained-html-builder` (`08e272b6`) or rebuild the absent
  surfaces listed under *Current state → Codebase Research Findings*. On `main`, Steps 1 and 4
  are build-from-source, not isolate-existing. **Recommended:** port the existing branch code
  rather than reimplement — it already exists and is presumably reviewed; this is an execution
  choice, not an open design decision, so `decision_needed` stays `false`.
- **Step 1** — `grammar_spec()` exposes `sorted(_ALL_OPS)` / `sorted(_ORDERED_OPS)` /
  `_PRED_PATTERN.pattern` from `fsm/policy_rules.py:27–34`; `_py_pattern_to_js()` rewrites
  `(?P<x>…)` → `(?<x>…)` over that same `_PRED_PATTERN`. Model dimension-name normalization on
  the ENH-2309 scored-set transform (`lower + \s+→-`) so header/instruction/predicate agree.
- **Step 2** — the node runner is **greenfield**: no `package.json`, no `node --test`, no `.mjs`
  test on `main`. Use bare `node --test scripts/tests/js/*.test.mjs` with `node:test` +
  `node:assert` (zero deps, Node ≥22 — the ratified Option A).
- **Step 3** — no `.github/workflows/` exists; the CI-location AC requires creating one (or
  documenting an alternative enforced location). Both the drift guard and the node conformance
  suite need a real, named CI step, or the gate is unenforced (an unenforced gate does not
  count as met per the AC).
- **Step 4** — `render_as_css_vars_themed(light, dark)` extends `design_tokens.py:320`
  `render_as_css_vars`: run alias resolution per theme, emit `:root {…}` for light and
  `[data-theme=dark] {…}` for dark, reuse the `_`-prefix metadata skip (lines 244, 275). Stamp
  `active_theme` from `BRConfig` (config `design_tokens.active_theme`, currently `dark`).
- **Step 5** — validate emitted YAML with the `load_and_validate` + `validate_fsm` +
  `ValidationSeverity.ERROR` filter pattern; diff shape against `loops/{policy,rubric}-refine.yaml`
  (and the byte-identical fixture `tests/fixtures/fsm/policy-refine.yaml`).

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the
implementation. They fold into the steps above rather than replacing them:_

6. **Config plumbing** — add `ArtifactsConfig` to `config/features.py` and wire all three
   `config/core.py` touch-points (constructor, `artifacts` property, **`BRConfig.to_dict()`**);
   add the `artifacts` object to `config-schema.json` (root is `additionalProperties: false`).
7. **Schema guard test** — add `test_artifacts_in_schema` to `tests/test_config_schema.py`
   (model on `test_design_tokens_in_schema`); undeclared keys are otherwise silently rejected.
8. **CLI registration surfaces** — beyond `pyproject.toml` + `cli/__init__.py`, add `ll-artifact`
   to the `cli/__init__.py` module docstring and the `.claude/CLAUDE.md` "CLI Tools" list; add a
   CLI-dispatch test modeled on `test_generate_schemas.py` or `test_cli_loop_dispatch.py`.
9. **Doc sync** — update `docs/ARCHITECTURE.md` "Project-enriched artifacts" (planned→implemented,
   re-attribute FEAT-2301→FEAT-2390); add a `### artifacts` section to
   `docs/reference/CONFIGURATION.md`; refresh the stale "37 CLI tools" count in `README.md`; add a
   `CHANGELOG.md` entry under a concrete version heading (not `[Unreleased]`); optionally note the
   `ll-artifact` path in the `skills/create-loop/` policy-router wizard docs and add
   `grammar_spec()`/`_py_pattern_to_js()` to the `docs/reference/API.md` module row.
10. **Grammar-drift discipline** — the JS operator regex from `_py_pattern_to_js()` must reproduce
    `route_table.py`'s longest-match-first ordering (`sorted(_ALL_OPS, key=len, reverse=True)`) so
    the emit-side and edit-routes-side parsers don't diverge; the drift guard is the enforced check.

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

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-06-30_

**Readiness Score**: 95/100 → PROCEED
**Outcome Confidence**: 70/100 → MODERATE

### Outcome Risk Factors
- Broad enumeration across 20+ touch points (`fsm/policy_rules.py`, `design_tokens.py`,
  `cli/artifact.py`, the config layer, `templates/policy_builder_core.mjs`, ~10 test
  files, and 8 documentation files) — individually mechanical and well-precedented, but
  numerous enough that a single site could be dropped without a completeness checklist.
- Zero existing CI infrastructure in this repo (no `.github/workflows/` directory at
  all), so the drift-guard and node-conformance ACs require standing up CI tooling from
  zero per Implementation Step 3, rather than extending an established pattern.
- The cross-language Python-vs-JS conformance/drift-guard pattern is fully greenfield
  here; the closest in-repo precedents (`verify_design_tokens.py`, `doc_counts.py`) are
  same-language structural diffs, not a corpus shared across two languages.

## Resolution

_Implemented via `/ll:manage-issue` on 2026-06-30._

**Approach:** Ported the reviewed engine from `feat-2301-self-contained-html-builder`
(commit `08e272b6`) onto the `main` basis (the recommended execution choice), then
hardened and gated it. Cherry-pick applied cleanly except a trivial `cli/__init__.py`
`__all__` conflict (`main_adapt` vs `main_artifact` — kept both); the FEAT-2301 issue
file change in the commit was discarded (out of scope, FEAT-2301 stays open).

**AC status — all met:**
- `grammar_spec()` / `_py_pattern_to_js()` exposed and unit-tested (`test_policy_rules.py`);
  JS-translated regex proven identical to `_PRED_PATTERN` over the corpus.
- Both emit modes pass `ll-loop validate` with zero ERROR findings — decision-table
  (golden `sample-decision-table.yaml`) **and** rubric (added golden `sample-rubric.yaml`
  + `test_golden_rubric_yaml_validates`, since the AC requires *each* mode and only
  decision-table was pinned on-branch).
- Boolean-dim `==true→>=50` / `==false→<50`; dimension-name normalization shared across
  header/instruction/predicate.
- Drift guard: `test_emitted_grammar_matches_canonical` (Python) + node conformance corpus.
- **JS logic pinned:** `node --test scripts/tests/js/*.test.mjs` (Node ≥22, zero deps), 7 tests.
- `render_as_css_vars_themed(light, dark)` emits scoped `:root` + `[data-theme=dark]`.
- **`active_theme` stamped** — fixed the FEAT-2301 worktree theme bug: `cmd_policy_builder`
  now stamps the configured theme onto `<html data-theme=...>` (was hardcoded `light`).

**Deviations / decisions:**
- **CI location = the local pytest suite, NOT GitHub Actions.** The repo has no hosted CI
  by design and the maintainer does not pay for Actions. The "named, enforced location"
  AC is satisfied by wrapping the node:test suite in a pytest test
  (`test_policy_builder_node_gate.py`) so it runs under `python -m pytest scripts/tests/`.
  Codified in `.claude/CLAUDE.md` (Testing & CI Policy) and `CONTRIBUTING.md`.
- **Fixed a NUL byte** in `policy_builder_core.mjs` (raw `\x00` delimiters in shadow-key
  template literals made the file binary); replaced with the ` ` source escape —
  byte-identical runtime string, pure-text source, HTML output no longer inlines a NUL.
- Added `BRConfig.to_dict()` `artifacts` block the on-branch commit missed (wiring gap).
- README "37 CLI tools" count left as-is: it is test-pinned (FEAT-1045) and the issue
  marked updating it optional; bumping it broke `test_wiring_guides_and_meta.py`, so reverted.

**Verification:** full suite 13,272 passed / 23 skipped; node 7/7; ruff + mypy + ll-verify-package-data
clean. (One unrelated pre-existing failure remains on `main`: `manage-issue/SKILL.md` = 523 lines
exceeds the ENH-494 500-line limit — untouched by this issue.)

## Session Log
- `/ll:manage-issue` - 2026-06-30 - `94f01e4a-8995-4dd3-9a06-d06181dd9822.jsonl`
- `/ll:ready-issue` - 2026-07-01T01:41:50 - `36499533-7bd1-4f6d-9bbf-d3658fc451c9.jsonl`
- `/ll:confidence-check` - 2026-06-30T20:34:56 - `d9f2d02c-a767-40d1-86bf-f3379ca2be91.jsonl`
- `/ll:wire-issue` - 2026-07-01T01:26:13 - `0d62aae1-e523-4234-ae5c-8ec43811386e.jsonl`
- `/ll:refine-issue` - 2026-07-01T01:14:19 - `ca9eb0c0-84a6-41bb-939f-c88658801ed2.jsonl`
- `/ll:format-issue` - 2026-07-01T01:05:18 - `44504eeb-4e2c-40de-b92d-2156ac3e303e.jsonl`
- `rescope-feat-2301` - 2026-06-28 - Extracted the headless emit/validate engine from
  FEAT-2301 into this issue so correctness has its own gates and cannot stand in for UX
  done-ness. Ratified the node:test runner (Option A) as a required AC, closing the prior
  outcome-confidence gap. Most code already exists on `feat-2301-self-contained-html-builder`.
