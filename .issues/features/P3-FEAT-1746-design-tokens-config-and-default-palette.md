---
id: FEAT-1746
title: Design tokens config field with default palette, wired into built-in artifact-generating
  loops
status: done
priority: P3
type: FEAT
captured_at: '2026-05-27T19:33:11Z'
discovered_date: 2026-05-27
discovered_by: capture-issue
labels:
- feat
- config
- design-system
- loops
- init
relates_to: []
decision_needed: false
confidence_score: 98
outcome_confidence: 55
score_complexity: 9
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 10
size: Very Large
---

# FEAT-1746: Design tokens config field with default palette, wired into built-in artifact-generating loops

## Summary

Add a `design_tokens` configuration section to `ll-config.json` (and `config-schema.json`) that points at a directory of semantically layered JSON token files. Ship a default high-contrast palette at `.ll/design-tokens/` and consume it from the built-in artifact-generating FSM loops (`hitl-compare`, `hitl-md`, `html-website-generator`, `html-anything`, `svg-image-generator`, `svg-textgrad`) so generated artifacts match the project's design system instead of inventing ad-hoc colors per run.

## Current Behavior

- `ll-config.json` has no notion of a project design system. `config-schema.json` (lines 711–741) defines `documents.categories` for tracking key documents, but nothing for design tokens.
- The artifact-generating loops in `scripts/little_loops/loops/` (`hitl-compare.yaml`, `hitl-md.yaml`, `html-website-generator.yaml`, `html-anything.yaml`, `svg-image-generator.yaml`, `svg-textgrad.yaml`) pick colors/typography ad hoc per run. Two runs of the same loop produce visually unrelated artifacts; runs across loops in the same project share no palette.
- `/ll:init` (skill at `skills/init/`) does not prompt about design system setup.

## Expected Behavior

1. `ll-config.json` supports a `design_tokens` section, default-enabled, pointing at `.ll/design-tokens/` with the semantically layered file set below.
2. `/ll:init` (and `/ll:configure`) offer an interactive prompt:
   - "Use the built-in high-contrast design tokens? [Y/n]"
   - "Or point at an existing design-tokens directory (path)?"
   - On accept, materialize `.ll/design-tokens/{primitives.json, semantic.json, themes/light.json, themes/dark.json}` from a bundled template.
3. The six listed built-in loops read `design_tokens.path` from project config at run time and inject the resolved tokens (or a derived CSS-vars snippet) into their generation prompts so emitted HTML/SVG/Markdown uses semantic token names (`color.surface.primary`, `color.text.primary`, etc.) and resolves them via the project's primitives/theme.
4. Default palette is high-contrast, aesthetically appealing, and meets WCAG AA contrast for body text on surface tokens.

## Motivation

- **Visual coherence across artifacts.** Today every run of `html-anything` / `svg-image-generator` is a fresh aesthetic guess. Users want their generated assets to look like *their project* without having to paste a style guide into every prompt.
- **Single source of truth for design.** Once a project sets `design_tokens.path`, future built-in loops (and user-authored loops) get a clean injection point — no per-loop palette duplication, no drift between `hitl-md` styling and `html-website-generator` output.
- **Lower friction for new projects.** `ll init` produces a working, attractive default palette with zero design effort from the user; they can override later by editing four small JSON files.
- **Theme-switching cheap.** Semantic layering means a `dark.json` theme is ~20 lines that remap semantic tokens, not a full duplicate of primitives.

## Proposed Solution

### 1. Schema addition (`config-schema.json`)

Add a top-level `design_tokens` property, sibling to `documents`:

```jsonc
"design_tokens": {
  "type": "object",
  "description": "Design system tokens consumed by built-in artifact-generating loops",
  "properties": {
    "enabled":   { "type": "boolean", "default": true },
    "path":      { "type": "string",  "default": ".ll/design-tokens",
                   "description": "Directory containing semantically layered token JSON files" },
    "primitives_file": { "type": "string", "default": "primitives.json" },
    "semantic_file":   { "type": "string", "default": "semantic.json" },
    "themes_dir":      { "type": "string", "default": "themes" },
    "active_theme":    { "type": "string", "default": "light",
                         "description": "Theme file (without .json) under themes_dir to use as default" }
  },
  "additionalProperties": false
}
```

### 2. Default token files (bundled under `templates/design-tokens/`)

Semantic layering — see https://www.designtokens.org/tr/drafts/format/ for the W3C draft format. Style Dictionary / Theo can transform these to CSS vars / JS constants later, but for now we keep them as plain JSON.

```
templates/design-tokens/
  primitives.json   # raw colors, spacing scale, type scale, radii, shadows
  semantic.json     # purpose-mapped: color.surface.primary -> {color.neutral.50}
  themes/
    light.json      # overrides for light theme (default)
    dark.json       # overrides for dark theme
```

Default palette target: high-contrast, accessible. Sketch:

- **Primitives**: neutral 0–950 (true black-to-white), brand (saturated blue, e.g. `#1d4ed8`), accent (warm orange, e.g. `#f97316`), success/warning/danger.
- **Semantic**: `color.surface.{primary,secondary,raised}`, `color.text.{primary,secondary,muted,inverse}`, `color.border.{subtle,strong}`, `color.action.{primary,primary-hover,destructive}`.
- All combinations must clear WCAG AA (4.5:1 body, 3:1 large) — verified at template-author time, not runtime.

`/ll:init` copies `templates/design-tokens/` → `.ll/design-tokens/` on accept.

### 3. Token loader (`scripts/little_loops/design_tokens.py`)

New module exposing:

```python
def load_design_tokens(config: LLConfig, theme: str | None = None) -> DesignTokens: ...
def render_as_prompt_context(tokens: DesignTokens) -> str: ...
def render_as_css_vars(tokens: DesignTokens) -> str: ...
```

- `load_design_tokens` reads `primitives.json` + `semantic.json` + the active theme override, resolves token references (`{color.brand.500}` → `#1d4ed8`), and returns a flat resolved view plus the raw layered view.
- `render_as_prompt_context` produces a compact markdown/JSON snippet suitable for injecting into LLM prompts: lists semantic tokens with their resolved values and a one-line rule ("Use semantic token names in generated output; do not invent new colors.").
- `render_as_css_vars` emits `:root { --color-surface-primary: #...; ... }` for HTML loops.

### 4. Loop wiring

Each of the six built-in loops gets a `prepare` (or equivalent setup) state that calls the loader and stashes the rendered context into FSM working state. Subsequent `llm_*` states reference it via a templated `{{design_tokens_context}}` variable in their prompt body. Loops to update:

- `scripts/little_loops/loops/hitl-compare.yaml`
- `scripts/little_loops/loops/hitl-md.yaml`
- `scripts/little_loops/loops/html-website-generator.yaml`
- `scripts/little_loops/loops/html-anything.yaml`
- `scripts/little_loops/loops/svg-image-generator.yaml`
- `scripts/little_loops/loops/svg-textgrad.yaml`

If `design_tokens.enabled: false` or the path doesn't exist, the loader returns an empty context and prompts fall back to today's behavior — no regression for projects that opt out.

### 5. `/ll:init` and `/ll:configure` UX

- `init`: after the test/lint/format prompts, ask "Initialize default design tokens at `.ll/design-tokens/`? (Y/n)". On `n`, ask for an alternate path or skip the feature.
- `configure`: expose a `design_tokens` subcommand that re-runs the same prompt and writes/overwrites the config block.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-05-27.

**Selected**: Option 3 — Pre-inject into fsm.context from ll-loop run

**Reasoning**: Option 3 scores 11/12, leading on both Simplicity and Testability. It slots directly into the established `run_dir` injection pattern at `cli/loop/run.py:162` — `BRConfig()` is already instantiated in scope, the `if "key" not in fsm.context` guard provides `--context` override for free, and `str(value)` interpolation passes multi-line strings through without modification. The six target loop YAMLs need only a `${context.design_tokens_context}` reference in their generation prompts with no new setup state; the only downside is two injection sites (`run.py` + `lifecycle.py:cmd_resume`) instead of one.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| 1 (shell heredoc) | 3/3 | 2/3 | 2/3 | 2/3 | 9/12 |
| 2 (contributed action) | 2/3 | 1/3 | 3/3 | 2/3 | 8/12 |
| 3 (pre-inject context) | 3/3 | 3/3 | 3/3 | 2/3 | 11/12 |

**Key evidence**:
- **Option 1**: `action_type: shell` + `capture:` used in 5 of 6 target loops; Python heredocs in 6 sibling loops — strong consistency, but adds a `prepare_tokens` state to all 6 loops and changes `html-website-generator.yaml`'s `initial:` field; quoting fragility if rendered context contains `"""`.
- **Option 2**: Full `ActionRunner`/`_contributed_actions` infrastructure exists with zero production users; `ll-parallel` and `ll-sprint` don't wire the executor, leaving those orchestration modes without the feature.
- **Option 3**: `run_dir` injection at `run.py:162` is a direct structural precedent; `TestCmdRunProgramMdInjection` in `test_ll_loop_program_md.py` provides a ready-made test pattern; no loop YAML setup state required.

## Integration Map

### Files to Modify
- `config-schema.json` — add `design_tokens` property block (insert before `analytics` ~line 1203; root has `additionalProperties: false` at line 1216, so the new key must be declared here or configs containing it will be rejected).
- `scripts/little_loops/config/features.py` — add `DesignTokensConfig` dataclass with `from_dict()` classmethod, following the `ScanConfig` / `LoopsConfig` pattern (lines 150–198 et al.).
- `scripts/little_loops/config/core.py` — in `BRConfig._parse_config()` (lines ~188–215), add `self._design_tokens = DesignTokensConfig.from_dict(self._raw_config.get("design_tokens", {}))`; add matching `@property design_tokens`; include in `BRConfig.to_dict()` so `{{config.design_tokens.path}}` placeholder substitution works via `skill_expander._substitute_config`.
- `scripts/little_loops/config/__init__.py` — import `DesignTokensConfig` and add to `__all__`.
- `scripts/little_loops/hooks/session_start.py` — `_validate_features()` (~lines 170–177) currently warns when `documents.enabled: true` but the configured paths are missing; mirror this for `design_tokens.enabled: true` + missing `path`.
- `scripts/little_loops/loops/hitl-compare.yaml`
- `scripts/little_loops/loops/hitl-md.yaml`
- `scripts/little_loops/loops/html-website-generator.yaml`
- `scripts/little_loops/loops/html-anything.yaml`
- `scripts/little_loops/loops/svg-image-generator.yaml`
- `scripts/little_loops/loops/svg-textgrad.yaml`
- `skills/init/SKILL.md` — new sub-step in Step 8 (mirrors the `ll-goals-template.md` materialization at Step 8 item 5: Read template, Write to `.ll/`).
- `skills/init/interactive.md` — new round (becomes Round 7, between current Round 6 "Document Tracking" and current Round 7 "Extended Config Gate"); bump TOTAL counter.
- `skills/configure/SKILL.md` — add `design_tokens` area. Note: five distinct places within this file need updating: (1) frontmatter `arguments[0].description` pipe-separated list, (2) Step 2 Area Mapping table, (3) `--list` output display block, (4) Step 1 interactive menu chain (paginated, add to one group), (5) `## Arguments` area description bullet list.
- `skills/configure/areas.md` — add `## Area: design_tokens` section with Current Values block + Round questions, following the `## Area: documents` precedent (closest structural match).

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/loop/lifecycle.py` — **second injection site**: `cmd_resume()` at lines 446–447 re-injects `run_dir` into `fsm.context` for resumed loops. Must also inject `design_tokens_context` here immediately after line 476 where `config = BRConfig(Path.cwd())` is already instantiated — follow the identical `if "design_tokens_context" not in fsm.context:` guard pattern. Without this, resumed loops referencing `${context.design_tokens_context}` produce empty interpolation at runtime.
- `docs/reference/API.md` — `#### Properties` table under the `BRConfig` section lists each typed property with its class (e.g., `scan | ScanConfig`, `loops | LoopsConfig`). Add row `design_tokens | DesignTokensConfig`.

### New Files
- `scripts/little_loops/design_tokens.py` — loader and renderers.
- `templates/design-tokens/primitives.json`
- `templates/design-tokens/semantic.json`
- `templates/design-tokens/themes/light.json`
- `templates/design-tokens/themes/dark.json`
- `scripts/tests/test_design_tokens.py` — loader tests, reference-resolution tests, render-shape tests.

### Dependent Files (Callers/Importers)
- `ll-init` and `ll-configure` CLI entry points.
- Any future user-authored loop that wants the tokens — pattern is `from little_loops.design_tokens import load_design_tokens`.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/loop/lifecycle.py` — `cmd_resume()` (lines 444–447) re-injects `run_dir` into `fsm.context` for resumed loops; **must also inject `design_tokens_context`** here using the `BRConfig` instance already in scope at line 476. Without this, any resumed loop referencing `${context.design_tokens_context}` will produce an empty interpolation or fail pre-run context validation. This is a **required second injection site** alongside `run.py:162`.
- `scripts/little_loops/cli/loop/run.py` — `cmd_run` also calls `BRConfig(Path.cwd())` at line 178 (after the `run_dir` injection at 162); the `design_tokens_context` injection must occur between lines 162 and 178 using the existing `BRConfig` instantiation pattern confirmed in `lifecycle.py`.

### Similar Patterns
- **Best precedent for dataclass shape**: `OrchestrationConfig` (`scripts/little_loops/config/orchestration.py`) — minimal single-module config class — and `ScanConfig` (`scripts/little_loops/config/features.py:ScanConfig`) for the multi-field + `field(default_factory=...)` variant.
- **Note**: `documents` block (config-schema.json:711) was cited as a precedent but actually has **no Python dataclass**; it's read directly from `_raw_config` in `hooks/session_start.py:_validate_features()` (lines 170–177). It is *not* a good model for the typed-config path this feature needs. Use the orchestration/scan precedent instead.
- **Setup → generate state pattern**: `scripts/little_loops/loops/greenfield-builder.yaml` (`init` → `tech_research` → `design_artifacts`) and `scripts/little_loops/loops/docs-sync.yaml` (`verify_docs` → `fix_docs`) — both use `capture: <name>` to bind stdout and `${captured.<name>.output}` to reference it downstream.
- **Inline Python in a shell state**: `scripts/little_loops/loops/integrate-sdk.yaml:parse_enumeration` and `:flatten_surfaces` — `action_type: shell` with `python3 << 'PYEOF' ... PYEOF` heredoc — this is the existing way to call Python from a loop until/unless a true `python_call` state is added.
- **Reference-resolution analogues for `{color.brand.500}` aliases**: `BRConfig.resolve_variable` (`config/core.py`) for dot-path traversal returning `None` on miss; `InterpolationContext._get_nested` (`fsm/interpolation.py`) for the same traversal raising `InterpolationError`. Pick the config-style (None on miss) or FSM-style (raise) convention; both are established.
- Template materialization on init mirrors how `templates/ll-goals-template.md` is copied at `skills/init/SKILL.md` Step 8 item 5: Read template via the Read tool, Write to `.ll/<dest>` via the Write tool, skip-if-exists. There is **no existing pattern for copying a directory subtree** — the four design-token files will each need an enumerated Read+Write, or a Bash `cp -r` from the plugin root.

### Tests
- New `scripts/tests/test_design_tokens.py`: token-reference resolution, theme override layering, missing-file fallback, unknown-token error path.
- Existing loop tests (if any) get a fixture project with tokens enabled to assert prompt context contains the expected semantic names.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_config.py` — **update (existing)**: add `TestDesignTokensConfig` class (testing `from_dict({})` defaults and `from_dict(full_data)` all fields) and `TestBRConfigDesignTokensIntegration` class (testing property access when key absent, key present in JSON, and round-trip `to_dict()`). Follow pattern of `TestLearningTestsConfig` / `TestBRConfigLearningTestsIntegration` (lines 2097–2127). Also add `DesignTokensConfig` to the import block at top of file.
- `scripts/tests/test_config_schema.py` — **update (existing)**: add `TestConfigSchema.test_design_tokens_in_schema`, following the `test_analytics_in_schema` pattern exactly (lines 136–155): assert top-level key exists, `type == "object"`, `additionalProperties == False`, enumerate each sub-property with its type and default.
- `scripts/tests/test_hook_session_start.py` — **update (existing, BREAKING RISK)**: `TestSessionStartFeatureValidation.test_no_warnings_when_features_disabled` and `test_no_product_warning_even_when_enabled` assert `"Warning:" not in fb` with configs that have no `design_tokens` key. If `design_tokens.enabled` defaults to `True` and `_validate_features` warns on missing path, both tests will fail. Fix: add `"design_tokens": {"enabled": False}` to their fixture configs (or choose a default of `enabled: false`). Also add `test_warns_design_tokens_enabled_without_path` following the `test_warns_sync_enabled_without_github` pattern.
- `scripts/tests/test_hooks_integration.py` — **update (existing, BREAKING RISK)**: `TestSessionStartValidation.test_no_warnings_when_features_disabled` and `test_no_warnings_when_properly_configured` assert `"Warning:" not in result.stderr`. Same failure mode as `test_hook_session_start.py` above — fixture configs must include `design_tokens: {enabled: false}` or a valid path.
- `scripts/tests/test_ll_loop_program_md.py` — **update (existing)**: add `test_design_tokens_context_injected_into_context` to `TestCmdRunProgramMdInjection`, following the exact `test_run_dir_injected_into_context` pattern (lines 252+). The fixture loop YAML must declare `design_tokens_context: ""` in its `context:` block; assert `fsm.context.get("design_tokens_context")` is not None after `cmd_run`.
- `scripts/tests/test_builtin_loops.py` — **update (existing)**: add `test_context_has_design_tokens_context` to each of: `TestHtmlWebsiteGeneratorLoop`, `TestSvgImageGeneratorLoop`, `TestSvgTextgradLoop`, `TestHtmlAnythingLoop`, `TestHitlCompareLoop`, `TestHitlMdLoop`. Pattern: `assert "design_tokens_context" in data.get("context", {})`, mirroring the existing `test_context_has_description` at line 2701.

### Documentation
- `docs/reference/CONFIGURATION.md` — new "Design tokens" section (follow `### documents` or `### loops` heading + key table pattern); also add `design_tokens` block to the "Full Configuration Example" JSON at the top of the file.
- `docs/ARCHITECTURE.md` — note design tokens as a cross-cutting input to artifact-generating loops.
- README — single-line mention in feature list.

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md` — `#### Properties` table under the `BRConfig` class section lists each typed property paired with its class (`scan | ScanConfig`, `loops | LoopsConfig`, etc.). Add row: `design_tokens | DesignTokensConfig`.

### Configuration
- Default `.ll/ll-config.json` produced by `ll-init` gains a `design_tokens` block.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Class name correction.** The root config class is `BRConfig` (`scripts/little_loops/config/core.py`), not `LLConfig`. All references in the Proposed Solution and API/Interface sections below that say `LLConfig` should read `BRConfig`. The package is split across `scripts/little_loops/config/{core,features,orchestration,automation}.py` with `__init__.py` controlling exports — there is no flat `scripts/little_loops/config.py`.

**No schema validation at config load.** `BRConfig._load_config()` calls `json.load()` but does not invoke any JSON-Schema validator — `config-schema.json` is consumed by IDE tooling and the `/ll:init` dry-run, not at runtime. Acceptance criterion "`ll-loop validate` (or equivalent config validator) accepts a config containing the block" requires verifying which entry point actually validates against the schema (or adding one). The deep-merge logic for `ll.local.md` overlay lives in `config/core.py:deep_merge()` — nested dicts merge, arrays/scalars replace, explicit `null` removes; design-tokens overlay behavior will inherit this for free.

**Critical gap: `python_call` state type does NOT exist.** The Proposed Solution §4 and API/Interface "Loop YAML reference" snippet use `type: python_call` and a `call:` field — neither is in the FSM schema (`scripts/little_loops/fsm/schema.py:StateConfig`) or executor (`scripts/little_loops/fsm/executor.py:_action_mode` at line 1280). Existing `action_type` values: `prompt` / `slash_command`, `shell`, `mcp_tool`, plus extension-registered "contributed" actions. Options for the loop-wiring step:
1. **Inline-Python heredoc** (lowest cost; matches existing pattern in `loops/integrate-sdk.yaml`): use `action_type: shell` with `python3 << 'PYEOF' ... PYEOF`, `capture: design_tokens_context`, then reference `${captured.design_tokens_context.output}` in downstream prompts.
2. **Contributed action** via `ActionRunner` protocol (`fsm/runners.py`) registered through `extension.py:wire_extensions` → `_contributed_actions` dict on the executor. Heavier — only worth it if other features will also benefit from native Python state calls.
3. **Pre-loop prompt-text builder**: have `ll-loop run` resolve `design_tokens_context` into the loop's `context:` block before execution starts (similar to how `run.py:162` injects `run_dir`), then prompts reference `${context.design_tokens_context}`. Cleanest for read-only resolved tokens.

> **Selected:** Option 3 — Pre-inject into fsm.context from ll-loop run — highest-scoring option (11/12); slots into the established run_dir pattern with no new setup states needed in loop YAMLs

Option 1 or 3 is recommended; **Option 1 ships with zero runner-code changes**.

**Interpolation syntax correction.** The Proposed Solution and API/Interface use Jinja-style `{{design_tokens_context}}` in YAML prompt bodies. The actual FSM interpolation engine (`scripts/little_loops/fsm/interpolation.py:VARIABLE_PATTERN`) is `\$\{([^}]+)\}` — i.e. `${namespace.path}`. Valid namespaces: `context`, `captured`, `prev`, `result`, `state`, `loop`, `env`. Correct forms for this feature:
- `${captured.prepare_tokens.output}` if a setup state captures the rendered context
- `${context.design_tokens_context}` if pre-injected via `fsm.context` (Option 3 above)
- `${config.design_tokens.path}` is **not** supported in FSM YAMLs — `{{config.…}}` substitution only happens in skill expansion (`skill_expander._substitute_config`), not at FSM run time.

**Templates copy mechanics.** `skills/init/SKILL.md` Step 8 item 5 is the existing template-materialization pattern, but it only handles a single file (`ll-goals-template.md` → `.ll/ll-goals.md`). The four design-token files will need either four enumerated Read+Write pairs in the skill prose, or a `Bash mkdir -p .ll/design-tokens/themes && cp -r <plugin-root>/templates/design-tokens/* .ll/design-tokens/` invocation. Resolving the plugin root path follows the precedent in Step 8.5 (Codex hook adapter install).

**Init skill round placement.** `skills/init/interactive.md` already has 12 rounds; the design-tokens prompt slots most naturally as a new Round 7 between Round 6 (Document Tracking, always shown) and the current Round 7 (Extended Config Gate, silent). The `TOTAL` counter and round numbering after it must be updated.

**FSM evaluator/state-type compliance note.** Loops being modified are artifact-generating, not meta-loops, so the meta-loop rules in `.claude/CLAUDE.md` (non-LLM evaluator required for `check_semantic`) do not apply. The new injection point does not introduce any new evaluator.

**Test fixtures already exist.** `scripts/tests/conftest.py:temp_project_dir` and `:sample_config` cover the integration-test surface. The new test file `scripts/tests/test_design_tokens.py` should also include a schema-guard test in `scripts/tests/test_config_schema.py` asserting `design_tokens` is declared at root with `additionalProperties: false` (precedent: `TestConfigSchema.test_analytics_in_schema`).

## Implementation Steps

1. **Schema + dataclass.** Add `design_tokens` block to `config-schema.json` (sibling of `documents`/`orchestration`, root has `additionalProperties: false` so this is required). Add `DesignTokensConfig` to `scripts/little_loops/config/features.py` modeled on `ScanConfig` (multi-field + `from_dict` classmethod). Wire into `BRConfig._parse_config()` in `scripts/little_loops/config/core.py` (~line 188–215) plus `@property design_tokens` and inclusion in `to_dict()`. Export from `config/__init__.py`. No behavior change yet.
2. **Default template files.** Author the four-file default palette under `templates/design-tokens/{primitives.json, semantic.json, themes/light.json, themes/dark.json}`. Verify WCAG AA at author time (no runtime check).
3. **Loader module + tests.** Implement `scripts/little_loops/design_tokens.py` exposing `load_design_tokens(config: BRConfig, theme: str | None = None) -> DesignTokens | None`, plus `render_as_prompt_context` and `render_as_css_vars`. Reference-resolution can follow `BRConfig.resolve_variable` (return None on miss) or `InterpolationContext._get_nested` (raise) — pick one. Cover with `scripts/tests/test_design_tokens.py` + schema-guard test in `scripts/tests/test_config_schema.py`.
4. **Pick the FSM injection mechanism.** Choose between (a) shell heredoc that prints the rendered context and captures it, (b) new contributed `ActionRunner` for native Python calls, or (c) pre-injecting into `fsm.context` from `ll-loop run` (mirrors how `run_dir` is set in `run.py:162`). Option (c) is cleanest for a read-only value; option (a) ships fastest with zero runner-code changes. **This is a decision point — pick one before step 5.**
5. **`/ll:init` prompt + materialization.** Add a new Round 7 to `skills/init/interactive.md` (between current Document Tracking and Extended Config Gate; bump TOTAL). Add a Step 8 sub-step to `skills/init/SKILL.md` that reads each of the four template files and writes them under `.ll/design-tokens/` (or runs `cp -r` via Bash for the subtree).
6. **Loop wiring.** Update the six built-in loops with the mechanism chosen in step 4. **Use `${captured.<name>.output}` or `${context.design_tokens_context}` — not `{{design_tokens_context}}`** (that Jinja-style syntax is not implemented in the FSM interpolator). Run each loop once on a fresh project with tokens enabled to confirm output uses semantic token names, and once with `design_tokens.enabled: false` to confirm no regression.
7. **`/ll:configure` integration.** Add `design_tokens` area to `skills/configure/SKILL.md` and `skills/configure/areas.md`.
8. **Docs + changelog entry.** Add `docs/reference/CONFIGURATION.md` "Design tokens" section, update `docs/ARCHITECTURE.md` cross-cutting input note, single-line README mention. Also add `design_tokens | DesignTokensConfig` row to the `BRConfig #### Properties` table in `docs/reference/API.md`.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

9. **Second injection site: `lifecycle.py:cmd_resume`.** After `config = BRConfig(Path.cwd())` at line 476, inject `design_tokens_context` into `fsm.context` using the same guard pattern as `run.py:162` (`if "design_tokens_context" not in fsm.context:`). Without this, `ll-loop resume` on loops referencing `${context.design_tokens_context}` produces empty interpolation.
10. **Fix no-warning test fixtures** before adding `_validate_features` validation. `TestSessionStartFeatureValidation.test_no_warnings_when_features_disabled` and `test_no_product_warning_even_when_enabled` in `test_hook_session_start.py` assert `"Warning:" not in fb` with configs that omit `design_tokens`. `TestSessionStartValidation.test_no_warnings_when_features_disabled` and `test_no_warnings_when_properly_configured` in `test_hooks_integration.py` have the same issue. Add `"design_tokens": {"enabled": False}` to those fixture configs — or set `enabled` default to `False` to avoid the trigger entirely.
11. **Config dataclass tests.** Add `TestDesignTokensConfig` and `TestBRConfigDesignTokensIntegration` to `scripts/tests/test_config.py` (follow `TestLearningTestsConfig`/`TestBRConfigLearningTestsIntegration` pattern at lines 2097–2127). Add `DesignTokensConfig` to the import block.
12. **Context injection test.** Add `test_design_tokens_context_injected_into_context` to `TestCmdRunProgramMdInjection` in `test_ll_loop_program_md.py`; fixture loop YAML must declare `design_tokens_context: ""` in its `context:` block.
13. **Loop context-key tests.** Add `test_context_has_design_tokens_context` to each of the 6 per-loop test classes in `test_builtin_loops.py` (`TestHtmlWebsiteGeneratorLoop`, `TestSvgImageGeneratorLoop`, `TestSvgTextgradLoop`, `TestHtmlAnythingLoop`, `TestHitlCompareLoop`, `TestHitlMdLoop`) asserting `"design_tokens_context" in data.get("context", {})`, mirroring `test_context_has_description` at line 2701.

## Impact

- **Priority**: P3 — quality-of-life and visual coherence, no user is blocked.
- **Effort**: Large — touches schema, six loops, init skill, new module + tests, four template files, docs. Plausibly decomposable into an EPIC (schema/loader, default palette, init UX, per-loop wiring × 6).
- **Risk**: Low — feature is opt-out via `enabled: false`; loops fall back to current behavior when tokens are absent.
- **Breaking Change**: No.

## Use Case

A solo developer runs `ll init` in a new product repo and accepts the default design tokens. Later that week they run `/ll:loop-run html-website-generator` to scaffold a landing page and `/ll:loop-run svg-image-generator` to produce a hero illustration. Both artifacts come out using the same surface/text/action colors — the landing page and the SVG visually belong to the same product without the developer having ever opened a design tool or pasted a hex code into a prompt. When they decide the brand should be green instead of blue, they edit one entry in `primitives.json` and re-run; every subsequent artifact updates.

## Acceptance Criteria

- [ ] `config-schema.json` defines `design_tokens` with the fields above; `ll-loop validate` (or equivalent config validator) accepts a config containing the block.
- [ ] `templates/design-tokens/{primitives.json, semantic.json, themes/light.json, themes/dark.json}` exist and pass WCAG AA contrast checks for every semantic text-on-surface pairing the template defines.
- [ ] `/ll:init` prompts about design tokens, and on accept materializes `.ll/design-tokens/` and writes a `design_tokens` block to the project config.
- [ ] `little_loops.design_tokens.load_design_tokens` resolves references across primitives/semantic/theme and returns a flat resolved map; reference cycles raise a clear error.
- [ ] Each of the six listed loops references the rendered tokens (via `${captured.<name>.output}` or `${context.design_tokens_context}` — actual FSM syntax, not `{{var}}`) in at least one generation prompt and, when run against a project with tokens enabled, produces output that uses the project's semantic token names/values.
- [ ] When `design_tokens.enabled` is `false` or the path is missing, every loop runs end-to-end with no errors and behaves as it does today.
- [ ] New tests in `scripts/tests/test_design_tokens.py` cover: happy path, theme override, missing primitive reference, disabled feature, alternate `active_theme`.

## API/Interface

```python
# scripts/little_loops/design_tokens.py

@dataclass(frozen=True)
class DesignTokens:
    primitives: dict
    semantic:   dict
    theme:      dict
    resolved:   dict          # flat name -> concrete value, post reference-resolution
    source_path: Path

def load_design_tokens(
    config: BRConfig,                 # NOTE: actual root class is BRConfig, not LLConfig
    theme: str | None = None,        # overrides config.design_tokens.active_theme
) -> DesignTokens | None: ...        # None when disabled or path missing

def render_as_prompt_context(tokens: DesignTokens) -> str: ...
def render_as_css_vars(tokens: DesignTokens) -> str: ...
```

Loop YAML reference — **corrected to match actual FSM schema** (the original `type: python_call` + `{{var}}` snippet does not match implemented state types or interpolation syntax; see Codebase Research Findings above):

```yaml
states:

  # Option A: shell heredoc (existing pattern, e.g. loops/integrate-sdk.yaml)
  prepare_tokens:
    action_type: shell
    action: |
      python3 << 'PYEOF'
      from little_loops.config import BRConfig
      from little_loops.design_tokens import load_design_tokens, render_as_prompt_context
      cfg = BRConfig()
      tokens = load_design_tokens(cfg)
      print(render_as_prompt_context(tokens) if tokens else "")
      PYEOF
    capture: design_tokens_context
    next: generate

  generate:
    action_type: prompt
    action: |
      You are generating an HTML page. Use these design tokens — do not
      invent new colors:

      ${captured.design_tokens_context.output}

      ...
    capture: html_output
    next: ...
```

Alternative (Option C from Codebase Research Findings): have `ll-loop run` resolve the context into `fsm.context["design_tokens_context"]` before execution (mirroring how `run_dir` is injected in `scripts/little_loops/loops/run.py:162`), then prompts reference `${context.design_tokens_context}` directly with no setup state.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`feat`, `config`, `design-system`, `loops`, `init`, `captured`

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-05-27_

**Readiness Score**: 98/100 → PROCEED
**Outcome Confidence**: 55/100 → LOW

### Outcome Risk Factors
- **Wide change surface — 26+ distinct files** across schema, Python, loops, skills, tests, and docs. Per-site changes are mostly mechanical or local, but broad surface area means integration errors (e.g., forgetting the lifecycle.py second injection site) won't surface until end-to-end testing.
- **4 existing tests have BREAKING RISK** — `test_hook_session_start.py` and `test_hooks_integration.py` have tests asserting `"Warning:" not in` output that will fail if `design_tokens.enabled` defaults to `True`. Fix these fixtures (add `"design_tokens": {"enabled": False}`) before wiring `_validate_features` validation.
- **`design_tokens.py` reference-resolution** is the highest-complexity new code — token aliasing across primitives/semantic/theme JSON with cycle detection. Allocate disproportionate test time here; the rest of the implementation is mechanical.

## Resolution

- **Status**: Decomposed
- **Completed**: 2026-05-27
- **Reason**: Issue too large for single session (score 9/11 — Very Large)

### Decomposed Into
- FEAT-1747: Design-tokens core infrastructure — schema, dataclass, loader, baseline tests
- FEAT-1748: Design-tokens default palette — four-file high-contrast template set
- FEAT-1749: Design-tokens loop wiring — pre-inject context into 6 built-in artifact loops
- FEAT-1750: Design-tokens init / configure UX and docs integration

## Session Log
- `/ll:issue-size-review` - 2026-05-27T20:30:00Z - `5f94f108-c36b-4b4d-b486-f41734145a41.jsonl`
- `/ll:confidence-check` - 2026-05-27T20:15:00 - `dd6015c6-5423-4f5a-ab43-a71886585d8e.jsonl`
- `/ll:wire-issue` - 2026-05-27T20:02:18 - `b4eba37b-b3bf-4a96-972f-bbe67dbe0da7.jsonl`
- `/ll:decide-issue` - 2026-05-27T19:55:11 - `614e310a-d6fa-4090-87bf-d57cbef9850f.jsonl`
- `/ll:refine-issue` - 2026-05-27T19:46:55 - `3b9a31fa-8f28-4e80-99b7-e50b99d1783d.jsonl`
- `/ll:format-issue` - 2026-05-27T19:36:07 - `c01056f4-277e-40ac-883a-9aff665c99c3.jsonl`
- `/ll:capture-issue` - 2026-05-27T19:33:11Z - (current Claude Code session)

---

## Status

**Open** | Created: 2026-05-27 | Priority: P3
