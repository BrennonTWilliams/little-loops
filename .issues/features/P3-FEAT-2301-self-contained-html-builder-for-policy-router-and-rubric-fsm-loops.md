---
id: FEAT-2301
title: Self-contained HTML builder for policy-router and rubric FSM loops
type: FEAT
priority: P3
status: open
discovered_date: 2026-06-26
discovered_by: capture-issue
captured_at: '2026-06-26T00:35:41Z'
relates_to:
- ENH-2299
- FEAT-1023
confidence_score: 94
outcome_confidence: 69
score_complexity: 14
score_test_coverage: 15
score_ambiguity: 20
score_change_surface: 20
---

# FEAT-2301: Self-contained HTML builder for policy-router and rubric FSM loops

## Summary

Generate a single, self-contained `.html` artifact that lets a user visually
configure a Policy Router + Decision Table FSM loop (`lib/policy-router.yaml`)
or a Rubric 3-tier loop (`lib/rubric-router.yaml`) and export valid loop YAML.
The page is a one-page minimalist form built around the decision table's natural
2-D shape (rules × dimensions), with live validation, a light/dark theme toggle,
an optional design-token profile picker, and a downloadable YAML output. It is
the *visual, greenfield* sibling of ENH-2299 (the conversational `/ll:create-loop`
wizard branch) and `ll-loop edit-routes` (the round-trip table editor for
*existing* loops).

## Motivation

The policy-router decision table is the one little-loops authoring artifact that
fights both of its current surfaces:

- The `/ll:create-loop` wizard (ENH-2299) is linear `AskUserQuestion` prose — bad
  at a grid where row *order* encodes precedence and columns appear/disappear as
  the dimension set changes.
- `ll-loop edit-routes` renders the compound table as markdown and round-trips it
  to YAML, but only for a loop that *already exists*, with no live validation.

A real HTML grid fits the table's shape natively and can make the error classes
the guide and ENH-2299 call out — missing catch-all, unmatched `route:` keys,
MR-4 dead-ends, numeric-coercion parse errors — **structurally unrepresentable**
rather than merely validated after the fact. It also matches the project's
"portable, self-contained artifact" philosophy (cf. FEAT-1023's
`html-website-generator`, which already emits self-contained HTML with an
embedded light/dark toggle).

## Use Case

A little-loops author wants to design a new `policy-router` loop from scratch. They open
`policy-router-builder.html` in their browser (no install, no server), fill in the loop name
and dimensions (e.g. `overall_quality` numeric, `has_citations` boolean), drag the priority
rows into order, verify the pinned catch-all fires last, then download `refine-quality.yaml`.
They run `ll-loop validate refine-quality.yaml` and it passes with no MR-4 dead-ends and no
unmatched route keys — without hand-writing the `import:` block, `route:` map, or catch-all
arms.

## Current Behavior

To author a policy-router loop today a user must hand-write the FSM YAML: the
`import:` block, `context.policy_rules` decision table, the `score → parse_scores
→ policy_dispatch` pipeline, the `route:` map (with `_:` / `_error:` catch-alls),
and a terminal/`next:` arm for every action state. The guide
(`docs/guides/POLICY_ROUTER_GUIDE.md`) documents the pattern and `ll-loop
edit-routes` can edit an existing table, but there is no visual, greenfield
composer and no live validation while authoring.

## Expected Behavior

A generated, self-contained `.html` file (no external dependencies; works over
`file://`) presents a one-page form:

1. **Mode switch** at the top: **Rubric** (one aggregate score, 3 tiers) vs
   **Decision Table** (per-dimension conjunctive rules). Names map 1:1 to the two
   lib fragments and the guide's vocabulary — *not* "Lite/Full", which implies one
   is a diminished version of the other.
2. **Identity / scaffolding**: loop `name`, `subject`, `max_steps`, scoring source
   (LLM rubric via `lib/rubric-router.yaml`, or custom shell scorer that writes
   `rubric-dim-<name>.txt`).
3. **Dimensions as chips** that reactively define the decision-table columns; each
   dimension typed numeric vs boolean/string so the operator dropdown only offers
   valid ops (ordered ops `>= <= < >` for numeric; `==true/==false` for boolean) —
   preventing the parse-time numeric-coercion error class. The reserved
   `aggregate` pseudo-dimension is always available.
4. **Reactive decision grid** (Decision Table mode): rows = rules in priority
   order with a drag handle (reorder = precedence), columns = dimensions, each
   cell either empty (`—`, unconstrained) or op+value; a **pinned, non-deletable
   catch-all row** (`* → action`). Rubric mode replaces the grid with two
   threshold sliders (`threshold_high`, `threshold_medium`) feeding a fixed
   3-row high/medium/low table.
5. **Derived action states**: the set of `→ action` targets is auto-listed; each
   gets a forced `terminal` vs `next:` choice (+ optional prompt body). This is
   what makes MR-4 dead-ends unrepresentable. The `route:` map and `_:` / `_error:`
   arms are *generated*, never hand-typed (no unmatched keys).
6. **Live validation**, colored from the active design-token semantics: shadowed
   rule (warning), missing catch-all / unknown action (danger), clean table
   (success).
7. **Theming**: stamped from the active design-token profile in
   `.ll/ll-config.json` (e.g. `warm-paper`), with **both** light and dark CSS
   variable blocks inlined and an embedded sun/moon toggle. Theme precedence:
   `prefers-color-scheme` (fallback) → config `active_theme` (default) →
   `localStorage` (user override, wins). Optionally inline all 3 profiles × 2
   themes to make the **profile** switchable in-page too.
8. **Output**: live YAML preview + Copy + Download `<name>.yaml`, with a printed
   `ll-loop validate <name>` line underneath so the Python gate stays authoritative.

## Acceptance Criteria

- [ ] The generated `.html` file loads without errors over `file://` with no external
  dependencies (no CDN, no fetch at runtime)
- [ ] Mode switch between **Rubric** and **Decision Table** renders without a page reload
- [ ] Decision Table mode: dimension chip type (numeric vs boolean) restricts operator
  dropdown to valid ops only (`>= <= < >` for numeric; `==true/==false` for boolean),
  preventing the numeric-coercion parse-error class
- [ ] Decision Table mode: catch-all row is always present and non-deletable; it is
  always last in the output YAML's rule list
- [ ] Decision Table mode: row drag-reorder is reflected in the output YAML's rule precedence
- [ ] Rubric mode: two threshold sliders produce a fixed high/medium/low 3-row table in YAML
- [ ] Action-state list auto-populates from grid `→ action` targets; each requires an
  explicit `terminal` or `next:` choice (MR-4 dead-ends are structurally unrepresentable)
- [ ] Live validation colors the table using the active design-token semantic palette:
  shadowed rule → warning, missing catch-all or unknown action → danger, clean table → success
- [ ] Theme toggle follows correct precedence: `prefers-color-scheme` → config `active_theme`
  → `localStorage` user override
- [ ] Generated `.html` stamps the active profile's resolved token values inline at generation
  time; no runtime token fetch is required
- [ ] A builder-generated YAML passes `ll-loop validate` with no errors (catch-alls present,
  route map complete, no MR-4 dead-ends)
- [ ] `render_as_css_vars_themed(light, dark)` emits two scoped CSS blocks — `:root { … }`
  for light and `[data-theme=dark] { … }` for dark — with all alias chains resolved to
  concrete hex values

## Scope Boundaries

- **In scope**: the generated single-file HTML builder (Rubric + Decision Table
  modes); a small `render_as_css_vars_themed(light, dark)` helper in
  `design_tokens.py` that emits scoped `:root` + `[data-theme=dark]` blocks; an
  emit path that stamps the active profile into the file.
- **Out of scope**: changes to `lib/policy-router.yaml` / `lib/rubric-router.yaml`
  runtime logic (no fragment changes).
- **Out of scope**: round-trip *editing of existing* loop YAML in the browser —
  `ll-loop edit-routes` owns that; this builder is greenfield-only.
- **Out of scope**: nested/chained policy tables; the builder produces one flat
  `context.policy_rules` table.
- **Out of scope**: re-implementing the canonical rule grammar / MR validation in
  a way that can drift from `fsm/policy_rules.py` / `fsm/route_table.py` — the
  builder validates for UX, but `ll-loop validate` remains the source of truth.

## Proposed Solution

### Theming: reuse existing token machinery

`design_tokens.py` already does the hard part:

- `load_design_tokens(base_path, theme=...)` reads the active profile from
  `.ll/ll-config.json`, layers `semantic → typography → spacing → theme`, and
  resolves `{color.paper.900}` alias chains to concrete hex.
- `render_as_css_vars(tokens)` emits a single `:root { --color-...: #...; }` block.

The only gap: `render_as_css_vars` emits **one** theme. A live in-browser toggle
needs both inlined and scoped:

```css
:root             { --color-surface-primary: #fdfbf6; /* light */ }
[data-theme=dark] { --color-surface-primary: #0d0b08; /* dark  */ }
```

Add `render_as_css_vars_themed(light_tokens, dark_tokens)` (~15 lines) that calls
`load_design_tokens(theme="light")` and `load_design_tokens(theme="dark")` and
emits the two scoped blocks. Typography tokens ride along, so the builder's font
system follows the profile for free (warm-paper handcrafted vs editorial-mono
mono). For an in-page profile picker, emit `:root[data-profile=…][data-theme=…]`
blocks for all 3 profiles × 2 themes.

### Self-containment

All CSS (resolved token vars for the stamped profile(s)), the validation JS, and
the YAML serializer are inlined — no fetch, works over `file://`, mirroring
FEAT-1023's `html-website-generator` self-contained output. The light/dark toggle
(and optional profile picker) are fully client-side; nothing requires
regeneration. Only *which profile palette(s)* are inlined is decided at stamp time.

### Generated YAML shape (Decision Table mode)

Matches `policy-refine.yaml`: `import:` (`lib/policy-router.yaml` + optionally
`lib/rubric-router.yaml`), `context` (`subject`, `rubric_dimensions`,
`policy_rules`), `initial: score`, and the `score → parse_scores → policy_dispatch`
pipeline with a `route:` map covering every action token plus `_:` and `_error:`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**API correction — `load_design_tokens` actual signature** (`design_tokens.py:160`):
```python
def load_design_tokens(config: BRConfig, theme: str | None = None) -> DesignTokens | None:
```
`base_path` is not a parameter — it is derived internally as `config.project_root / config.design_tokens.path`. The emit path must pass a `BRConfig` instance (from `little_loops.config.core`), not a raw path. Returns `None` when tokens are disabled or the profile directory is missing.

**`_`-prefix filter required in `render_as_css_vars_themed`**: `render_as_css_vars` (line 320) does NOT filter `_wcag_spot_check.*` and `_note` metadata keys — they land in the `:root` block as `--_wcag_spot_check-...` properties. The themed variant must skip keys where `name.startswith("_")`.

**Implementation sketch for `render_as_css_vars_themed`** (extending `render_as_css_vars` at `design_tokens.py:320`):
```python
def render_as_css_vars_themed(light: DesignTokens, dark: DesignTokens) -> str:
    def _block(scope: str, tokens: DesignTokens) -> str:
        lines = [f"{scope} {{"]
        for name, value in sorted(tokens.resolved.items()):
            if name.startswith("_"):
                continue
            lines.append(f"  --{name.replace('.', '-')}: {value};")
        lines.append("}")
        return "\n".join(lines)
    return _block(":root", light) + "\n" + _block("[data-theme=dark]", dark)
```

**Rubric mode required form fields** (from `lib/rubric-router.yaml` public interface):
- `context.subject` — what is being evaluated
- `context.rubric_dimensions` — pipe-separated names (e.g. `"clarity|completeness|feasibility"`)
- `context.threshold_high` — integer string (default `"85"`)
- `context.threshold_medium` — integer string (default `"65"`)

**Import order for generated YAML**: `lib/rubric-router.yaml` MUST appear before `lib/policy-router.yaml` in the `import:` block (verified from `policy-refine.yaml`).

**`RouteConfig` serialization** (`fsm/schema.py`, `RouteConfig.to_dict()`): writes `default → "_"` and `error → "_error"`. The YAML serializer must follow this convention — these sentinel keys are not arbitrary strings.

**JS validation grammar** — exact constants to re-implement from `fsm/policy_rules.py:27–34`:
- Ordered ops (require `float(value)` parse, raise on non-numeric): `>=, <=, <, >`
- String-value ops (accept any string): `==, !=`
- Predicate regex: `/^([\w][\w\s\-]*?)\s*:\s*(>=|<=|==|!=|<|>)\s*(\S.*?)$/`
- Grid cell format (compound grid, `route_table.py`): `<op><value>` with no dim or colon — the column header supplies the dim
- Catch-all row (grid): ALL dim cells ∈ `{"*", "", "—", "-"}` AND at least one equals `"*"`
- Shadow rule detection: rule `i` is shadowed when earlier rule `j` has predicate-set ⊆ rule `i`'s predicate-set (and `j`'s set is non-empty); OR when `j` is a catch-all
- Do NOT confuse with evaluator operators (`eq/ne/lt/le/gt/ge` word-form in `fsm/evaluators.py`) — entirely separate namespace

**MR-4 dead-end detection** (`fsm/validation.py`, `_validate_partial_route_dead_end()`): flagged when `action_type` is `"prompt"` or `"slash_command"`, AND `next == null`, AND `route == null`, AND `on_yes != null`, AND (`on_no == null` OR `on_partial == null`). The builder makes this unrepresentable by requiring each action state to declare either `terminal: true` or a `next:` target — so builder output should never trigger this warning.

## Integration Map

### Files to Modify
- `scripts/little_loops/design_tokens.py` — add `render_as_css_vars_themed(light, dark)` (scoped two-theme emit; optional multi-profile variant)

### New Files
- `scripts/little_loops/cli/artifact.py` (or `cli/artifact/__init__.py`) — top-level `main_artifact` dispatcher with argparse subparsers; routes `policy-builder` to `artifact/policy_builder.py`
- `scripts/little_loops/cli/artifact/policy_builder.py` — core emit logic for the policy-builder subcommand; stamps the active design-token profile into the generated file. Modeled on `cli/schemas.py` `main_generate_schemas` (~49 lines).
- The generated/template HTML builder (e.g. `docs/tools/policy-router-builder.html` as a checked-in stamped artifact, and/or a `templates/` source the emitter fills)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/loops/lib/policy-router.yaml` — consumed by generated loops (no change)
- `scripts/little_loops/loops/lib/rubric-router.yaml` — consumed in Rubric mode (no change)
- `scripts/little_loops/loops/policy-refine.yaml` — canonical reference for the generated YAML shape (Decision Table mode)
- `scripts/little_loops/loops/rubric-refine.yaml` — reference implementation for Rubric mode output shape (parallel to `policy-refine.yaml`; use as the pattern for Rubric mode YAML generation)
- `scripts/little_loops/fsm/policy_rules.py`, `scripts/little_loops/fsm/route_table.py` — canonical grammar/validation the builder's JS must mirror (and defer to via `ll-loop validate`)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/loop/lifecycle.py` — second existing caller of `load_design_tokens` + `render_as_prompt_context` (~line 523/531), alongside `run.py`; both follow the `BRConfig`-based load convention the emit path must reuse [Agent 1/2]
- `scripts/little_loops/config/features.py` — `DesignTokensConfig` dataclass defines the `active` / `active_theme` keys the loader resolves; the emit path reads the profile through this [Agent 1]
- `scripts/little_loops/config/core.py` — `BRConfig` aggregator loads `design_tokens` from `.ll/ll-config.json`; `load_design_tokens(config)` requires a `BRConfig` instance, not a raw path [Agent 1]
- NOTE (negative finding): the runner callers (`run.py`, `lifecycle.py`) only call `render_as_prompt_context`, never `render_as_css_vars`. The FEAT-2301 emit path is the **first executed caller of the CSS-var render path** — there is no precedent caller for `render_as_css_vars` / `render_as_css_vars_themed` to copy. [Agent 2]

### Registration / Manifest

> **Selected:** `ll-artifact policy-builder` — first subcommand of a new `ll-artifact` top-level CLI. `ll-artifact` becomes the durable namespace for all little-loops artifact generation (HTML builders, diagrams, exporters, etc.). Supersedes the earlier `ll-emit-builder` standalone decision (2026-06-25); updated 2026-06-25.

**Registration touchpoints for `ll-artifact`:**
- `scripts/pyproject.toml` — `ll-artifact = "little_loops.cli:main_artifact"` in `[project.scripts]` [Agent 2]
- `scripts/little_loops/cli/artifact.py` (or `cli/artifact/__init__.py`) — top-level argparse dispatcher with `subparsers`; delegates `policy-builder` to `artifact/policy_builder.py` [Agent 2]
- `scripts/little_loops/cli/__init__.py` — new import + `__all__` entry for `main_artifact` [Agent 2]
- `docs/reference/CLI.md` — new `### ll-artifact` section with `#### ll-artifact policy-builder` subsection [Agent 2]
- `.claude/CLAUDE.md` — new "CLI Tools" bullet for `ll-artifact` [Agent 2]

_Future subcommands (e.g. `ll-artifact loop-diagram`, `ll-artifact decision-table`) add only a new `artifact/` module + a dispatch arm — no new pyproject entries or `__all__` exports needed._

_Note: `ll-generate-schemas` / `ll-generate-skill-descriptions` remain as-is (release/maintainer utilities); `ll-artifact` owns interactive/visual artifact generation. The distinction: `ll-generate-*` produces machine-consumed artifacts (JSON schemas, description strings); `ll-artifact *` produces human-facing artifacts (HTML builders, diagrams)._

### Similar Patterns
- `scripts/little_loops/loops/html-website-generator.yaml` (FEAT-1023) — precedent for self-contained inline-CSS/JS HTML with an embedded light/dark toggle and design-token injection
- `render_as_css_vars` / `render_as_prompt_context` in `design_tokens.py` — existing render helpers to follow

### Tests
- `scripts/tests/` — unit test for `render_as_css_vars_themed` (both scoped blocks present, references resolved to hex)
- Smoke test that a builder-generated YAML passes `ll-loop validate` (catch-alls present, route map complete, no MR-4 dead-ends)

_Wiring pass added by `/ll:wire-issue` — concrete files + patterns to follow:_
- `scripts/tests/test_design_tokens.py` — UPDATE: add `render_as_css_vars_themed` to the named import block (~line 10), add a `TestRenderAsCssVarsThemed` class modeled on the existing `TestRenderAsCssVars` (reuse its `_write_tokens` / `_make_config` helpers; assert `:root {` AND `[data-theme=dark] {` blocks, hex-resolved values, distinct light vs dark values). No `__all__` / snapshot exists, so the new export breaks nothing. [Agent 3]
- For an integration-level themed test against a real bundled profile, follow `test_enh1768_profile_system.py`'s `_copy_templates()` pattern (`shutil.copytree(TEMPLATES_DIR, …)` then `load_design_tokens(config, theme="light"|"dark")`). [Agent 3]
- Smoke test pattern for builder YAML → `ll-loop validate`: lowest-level is `test_fsm_fragments.py` (`load_and_validate` + filter `ValidationSeverity.ERROR`, cf. `test_policy_refine_loop_validates`); mid-level is `test_ll_loop_commands.py`'s `cmd_validate(...)` returning `0`. [Agent 3]
- If an emit subcommand is added, test it via the `cmd_<name>(loop, argparse.Namespace(), loops_dir, Logger(use_color=False))` + `capsys` pattern in `test_ll_loop_commands.py`. [Agent 3]
- Tests that patch `little_loops.design_tokens.load_design_tokens` by module path (`test_ll_loop_program_md.py:323`, `test_cli_loop_lifecycle.py:832`) are UNAFFECTED by the new function — no update needed. [Agent 2]

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **`TestRenderAsCssVarsThemed` — two-theme file setup**: `_write_tokens` writes only one theme file (`themes/<theme_name>.json`) and returns the `token_dir` path. The test must write the second theme file manually before loading:
  ```python
  token_dir = _write_tokens(tmp_path, primitives={"color": {"bg": {"light": "#FFF"}}}, theme_name="light", theme={"color": {"bg": "#FFF"}})
  (token_dir / "themes" / "dark.json").write_text(json.dumps({"color": {"bg": "#000"}}))
  config = _make_config(tmp_path)
  light = load_design_tokens(config, theme="light")
  dark = load_design_tokens(config, theme="dark")
  assert light is not None and dark is not None
  output = render_as_css_vars_themed(light, dark)
  assert ":root {" in output
  assert "[data-theme=dark] {" in output
  ```
- **Smoke test — `validate_fsm` is a required second step**: Step 12's wiring note says "`load_and_validate` + filter `ValidationSeverity.ERROR`" but `load_and_validate` returns `(fsm, fragment_warnings)`; the rule-checking violations come from a **separate** `validate_fsm(fsm)` call. All three imports are needed (exact pattern from `test_fsm_fragments.py:2397` `test_policy_refine_loop_validates` and `:2277` `test_rubric_refine_loop_validates`):
  ```python
  from little_loops.fsm.validation import ValidationSeverity, load_and_validate, validate_fsm

  fsm, _ = load_and_validate(builder_yaml_path)
  errors = validate_fsm(fsm)
  error_list = [e for e in errors if e.severity == ValidationSeverity.ERROR]
  assert not error_list, f"builder YAML validation errors: {[str(e) for e in error_list]}"
  ```

### Documentation
- `docs/guides/POLICY_ROUTER_GUIDE.md` — add a "Visual builder" section cross-linking the artifact and contrasting it with `ll-loop edit-routes` (greenfield vs round-trip)

_Wiring pass added by `/ll:wire-issue`:_
- `docs/ARCHITECTURE.md` (~line 846, the `DesignTokensConfig` "cross-cutting input to artifact-generating loops" paragraph) — add a note about the CSS-var themed render path / HTML builder artifact, if the builder is described architecturally [Agent 2]
- `docs/reference/API.md` (`DesignTokensConfig` section, ~lines 176–189) — NEGATIVE finding: documents config keys only, no function-level entries for `design_tokens` render helpers; under the existing pattern no update is required for `render_as_css_vars_themed` [Agent 2]
- (Emit-path docs — `CLI.md`, `LOOPS_GUIDE.md`, `LOOPS_REFERENCE.md`, `.claude/CLAUDE.md` — are listed under "Registration / Manifest" above, gated on the emit-path choice.)

### Configuration
- Reads `design_tokens.active` / `design_tokens.active_theme` from `.ll/ll-config.json`; no new config keys

_Wiring pass added by `/ll:wire-issue` — NEGATIVE confirmation:_
- `config-schema.json` (`"design_tokens"` block, ~lines 1440–1486) — both `active` (default `"default"`) and `active_theme` (default `"dark"`) are already defined; `additionalProperties: false` is set. No schema change is needed, confirming the issue's "no new config keys" claim. [Agent 1/2]

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Additional files to reference**:
- `scripts/little_loops/cli/loop/run.py` (~line 195) — canonical token-injection pattern: `load_design_tokens(_config)` → `render_as_prompt_context` stamped into `context["design_tokens_context"]`. The emit path for the HTML builder should follow the same `BRConfig`-based loading pattern but call `render_as_css_vars_themed` instead.
- `scripts/little_loops/cli/loop/edit_routes.py` — `cmd_edit_routes()`, `CompoundGridRenderer`, `PolicyRuleExtractor`, `PolicyRuleApplier` — the existing round-trip text editor; the greenfield builder must not overlap with it.
- `scripts/little_loops/fsm/validation.py` — `_validate_partial_route_dead_end()` + `_is_llm_judged()` — MR-4 logic the builder makes structurally unrepresentable.
- `scripts/little_loops/fsm/schema.py` — `RouteConfig` dataclass with `routes`, `default`, `error` fields and `from_dict()` / `to_dict()` — canonical `route:` map serialization.

**Test files to pattern after for `render_as_css_vars_themed`**:
- `scripts/tests/test_design_tokens.py` — existing unit tests for `render_as_css_vars`, `render_as_prompt_context`, `load_design_tokens`
- `scripts/tests/test_enh1768_profile_system.py` — multi-profile loading tests (`warm-paper`, `editorial-mono`)

**FEAT-1023 precedent clarification**: `html-website-generator.yaml` generates HTML via LLM prompt states (the LLM writes `index.html`). `design_tokens_context` injection at `run.py:195` feeds the LLM semantic names. FEAT-2301's builder is a **Python-generated** static artifact — a different architectural pattern; no LLM state writes the HTML.

### Decision Rationale

Initial decision by `/ll:decide-issue` on 2026-06-25: **standalone CLI `ll-emit-builder`**.

**Superseded 2026-06-25**: Renamed to `ll-artifact policy-builder` — first subcommand of a new `ll-artifact` top-level CLI.

**Revised Reasoning**: Artifact generation is a broad, recurring concern in little-loops (HTML builders, diagrams, exporters, etc.). Rather than proliferating `ll-generate-*` / `ll-emit-*` / `ll-build-*` standalone commands, `ll-artifact` establishes a durable namespace where all human-facing artifact generators live as subcommands. The registration cost is one more level of argparse dispatch compared to a standalone tool, but future artifact generators (`ll-artifact loop-diagram`, etc.) cost only a new module + dispatch arm — no additional `pyproject.toml` entries. The distinction from existing `ll-generate-*` tools: those produce machine-consumed artifacts (JSON schemas, description strings); `ll-artifact *` produces human-facing, interactive artifacts (HTML builders, visual tools).

The original scoring across `ll-loop` subcommand / standalone / built-in-loop-YAML still holds — the `ll-artifact` shape is the standalone option with a thin dispatcher layered on top. `cli/schemas.py` `main_generate_schemas` (~49 lines) remains the template for the `policy_builder.py` core module; only the top-level entry point changes from `main_emit_builder` to `main_artifact`.

**Decision impact on the rest of the issue**: Implementation Steps 9–10 resolve to the **`ll-artifact` subcommand** registration arm. See Registration / Manifest section above for the full touchpoint list.

## Implementation Steps

1. Add `render_as_css_vars_themed(light, dark)` to `design_tokens.py` (+ optional multi-profile variant); unit-test resolution and scoping.
2. Build the one-page HTML: mode switch (Rubric / Decision Table), identity fields, dimension chips (typed), reactive decision grid with pinned catch-all + drag-reorder, derived action-state list with forced terminal/next.
3. Implement client-side validation mirroring `fsm/policy_rules.py` semantics (shadow, gap, missing catch-all, unknown action, numeric-coercion), colored from token semantics.
4. Implement the YAML serializer + live preview + Copy/Download + printed `ll-loop validate <name>` hint.
5. Wire the embedded theme toggle (precedence: prefers-color-scheme → config active_theme → localStorage) and optional profile picker.
6. Add the emit/stamp path (inline the active profile's resolved tokens at generation time).
7. Smoke-test a generated YAML through `ll-loop validate`.
8. Document in `POLICY_ROUTER_GUIDE.md`; cross-link from ENH-2299's wizard completion message as an alternative table-authoring surface.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

9. **Emit-path shape: DECIDED — `ll-artifact policy-builder`** (supersedes `ll-emit-builder` standalone decision; 2026-06-25). Implement `scripts/little_loops/cli/artifact/policy_builder.py` (core emit logic) + `scripts/little_loops/cli/artifact.py` (top-level `main_artifact` dispatcher with argparse subparsers). Core module modeled on `cli/schemas.py` `main_generate_schemas` (~49 lines).
10. **Register `ll-artifact`**: add `ll-artifact = "little_loops.cli:main_artifact"` to `scripts/pyproject.toml` `[project.scripts]` + `from little_loops.cli.artifact import main_artifact` import and `"main_artifact"` entry in `scripts/little_loops/cli/__init__.py` `__all__` + a `### ll-artifact` section (with `#### ll-artifact policy-builder` subsection) in `docs/reference/CLI.md` + a "CLI Tools" bullet in `.claude/CLAUDE.md`.
11. **Update `scripts/tests/test_design_tokens.py`** — add `render_as_css_vars_themed` to the import block and a `TestRenderAsCssVarsThemed` class (model on `TestRenderAsCssVars`, reuse `_write_tokens`/`_make_config`).
12. **Add the `ll-loop validate` smoke test** following `test_fsm_fragments.py` (`load_and_validate` + ERROR-severity filter) or `test_ll_loop_commands.py` (`cmd_validate(...) == 0`).
13. **(If a subcommand is added)** add a `cmd_<name>` test in `test_ll_loop_commands.py` using the `argparse.Namespace()` + `Logger(use_color=False)` + `capsys` pattern.
14. **Update `docs/ARCHITECTURE.md`** (~line 846) if the builder is described as an architectural artifact.

## Impact

- **Priority**: P3 — discoverability/authoring quality-of-life; the pattern already works via hand-authoring and `edit-routes`. No urgent unblock.
- **Effort**: Medium — one self-contained HTML artifact + a ~15-line token helper + an emit path + tests/docs. No FSM runtime changes.
- **Risk**: Low — purely additive; runtime, fragments, and existing wizard/edit-routes paths are untouched. Main risk is JS validation drifting from the canonical Python grammar — mitigated by deferring to `ll-loop validate` as the authoritative gate.
- **Breaking Change**: No

## Labels

`feature`, `loops`, `policy-router`, `design-tokens`, `html`, `tooling`

## Status

**Open** | Created: 2026-06-26 | Priority: P3

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-06-25_

**Readiness Score**: 94/100 → PROCEED
**Outcome Confidence**: 69/100 → below threshold

### Outcome Risk Factors
- **JS grammar drift risk**: The in-browser validation mirrors Python logic from `fsm/policy_rules.py:27–34` (shadow detection, numeric-coercion ops, catch-all rules) but has no automated cross-validation path — the grammar can drift silently from the canonical Python source. Mitigated by deferring to `ll-loop validate` as the authoritative gate; still a maintenance risk.
- **No automated JS test coverage**: Interactive browser behavior (drag-reorder, reactive decision grid, YAML serializer, theme toggle, live validation) requires manual browser verification; pytest covers only the Python emit path and the generated YAML smoke test. The JS layer is the primary complexity locus and has no programmatic coverage.
- **Output artifact path not finalized**: The HTML output location uses "e.g." framing (`docs/tools/policy-router-builder.html`) — lock down the exact path before writing `CLI.md`, `CLAUDE.md`, and `POLICY_ROUTER_GUIDE.md` registration entries to avoid rework.

## Session Log
- `/ll:confidence-check` - 2026-06-25 - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/`
- `/ll:refine-issue` - 2026-06-26T01:31:25 - `af981b92-c03e-478c-b61b-511a0b83ff43.jsonl`
- `naming decision` - 2026-06-25 - Renamed emit path from `ll-emit-builder` (standalone) to `ll-artifact policy-builder` (subcommand of new `ll-artifact` CLI); `ll-artifact` established as the durable namespace for all human-facing artifact generation
- `/ll:decide-issue` - 2026-06-26T01:11:10 - `81cb10d8-c7ce-4642-bb0e-3ecbdb6e258a.jsonl`
- `/ll:wire-issue` - 2026-06-26T01:01:02 - `f9198542-abe8-4adb-a324-052b78ba3060.jsonl`
- `/ll:refine-issue` - 2026-06-26T00:51:56 - `d6038229-795a-45ee-8ef3-49cfaf152cac.jsonl`
- `/ll:format-issue` - 2026-06-26T00:42:29 - `dace4845-a459-498c-a40e-691d358094f6.jsonl`
- `/ll:capture-issue` - 2026-06-26T00:35:41Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/7ac50ab5-0773-4ba5-b0ed-58ad5b368658.jsonl`
