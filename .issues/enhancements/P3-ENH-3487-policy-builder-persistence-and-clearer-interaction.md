---
id: ENH-3487
type: ENH
title: Policy builder persistence and clearer interaction
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-16'
captured_at: '2026-09-16T20:54:20Z'
labels:
- policy-builder
- captured
depends_on:
- BUG-3486
- BUG-3489
relates_to:
- FEAT-3474
---

# ENH-3487: Policy builder persistence and clearer interaction

## Summary

Improve policy-builder persistence and interaction so users can safely maintain a policy over multiple sessions and understand what their loop will do. Preserve the self-contained offline HTML experience while adding versioned saved projects, per-mode drafts, undo/redo, and a task-oriented authoring flow.

Captured from the 2026-09-16 review following FEAT-3474, as the second of three requested workstreams.

## Current Behavior

The page holds authoring state only in memory; localStorage stores the theme. Mode changes replace all work with a seed, and refresh loses edits. Only YAML is exported, with no builder-project reopening. The lifecycle page presents nine built-in fields and five verbose action editors before its rules, retains an irrelevant grading-subject input, and describes available verbs like a pipeline even though implementation stops by default. Max steps counts FSM state executions, not whole attempts. The two-column CSS lacks responsive breakpoints; Copy has no success/failure feedback.

Rubric dimensions have no score definitions, skill descriptions are collected but not displayed, and lifecycle defaults hardcode a confidence threshold rather than exposing the project's implementation gate. The verify verb checks issue-file accuracy via verify-issues; it is not inherently an acceptance-test runner.

## Expected Behavior

Edits survive reload and mode exploration. Users can save/reopen a portable versioned project, undo changes, choose a task preset, edit fields/rules before advanced action settings, and inspect an accurate execution summary. Offline authoring remains usable without a server or browser storage permission.

## Motivation

Prevent accidental loss of authoring work and make the builder useful for ongoing policy maintenance. Users should understand stopping, repetition, verification, and export without learning internal state names or inspecting generated YAML.

## Proposed Solution

- Persist independent per-mode drafts with versioned project export/import and undo/redo. Validate imports before replacing a draft; report storage failures and keep explicit file saving available.
- Reorganize lifecycle authoring as Fields, Rules, Try it, and Export; collapse action bindings and budgets under advanced settings. Present task presets for document improvement, condition-based routing, preparation, implementation, and implementation with verification.
- Use friendly type labels and field explanations while retaining exact frontmatter keys. Hide mode-irrelevant inputs and show an accurate graph/summary of the current transitions.
- Add explicit stop-success, skip, and needs-attention destinations for lifecycle policies. Preserve existing five-verb projects when reopening; new presets must distinguish issue validation from acceptance verification and declare the latter's configured command/result contract.
- Show skill descriptions/argument hints, add optional dimension scoring instructions and score anchors, and expose the stamped project confidence gate alongside rule thresholds. Explain state-step budgets and default transitions.
- Provide responsive layout, associated labels, keyboard-operable controls, live feedback, copy success/failure feedback, and exact save/validate/run instructions with required parameters.

## Integration Map

- Files to modify: scripts/little_loops/templates/policy_builder_core.mjs; scripts/little_loops/templates/policy-router-builder.html.tmpl; scripts/little_loops/cli/artifact/policy_builder.py.
- Dependent files: scripts/little_loops/artifact_template_kit.py for shared shell conventions; scripts/tests/fixtures/policy_builder/ for generated fixtures.
- Similar patterns: existing theme storage fallback, flat JSON-friendly builder model, project-derived stamping.
- Tests: scripts/tests/js/policy_validator.test.mjs, scripts/tests/test_policy_builder_emit.py, scripts/tests/test_policy_builder_node_gate.py; browser workflows for reload, switching, import, undo, responsive layout, and keyboard interaction.
- Configuration: read existing confidence-gate settings; do not add a server requirement.

### Dependent Files (Callers/Importers)

- `scripts/little_loops/cli/artifact/__init__.py:197` — `main_artifact` dispatches the `policy-builder` subcommand to `cmd_policy_builder`
- `scripts/tests/test_enh3035_artifact_template_kit.py:65` — `test_policy_builder_renders_byte_identically_to_golden_fixture` calls `cmd_policy_builder` directly
- `scripts/tests/test_policy_builder_emit.py:43,50,83` — `_emit_html`, `test_emit_writes_html`, `test_emitted_grammar_matches_canonical` call `cmd_policy_builder` directly (never the console script)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/fsm/context_seed.py:68` — `seed_confidence_thresholds()` reads `config.commands.confidence_gate` off an already-built `BRConfig`; this is the pattern `cmd_policy_builder` should mirror to read the confidence-gate settings it must stamp — no new import path needed, `cmd_policy_builder` already constructs `config = BRConfig(Path.cwd())` at `policy_builder.py:66` [Agent 2 finding]
- `scripts/little_loops/fsm/frontmatter_scores.py` — `encode_frontmatter_scores()` documents itself as sharing dimension-encoding rules verbatim with `normalizeDimName()`/dim encoding in `policy_builder_core.mjs`; touch if optional scoring instructions/score anchors change `BUILTIN_FRONTMATTER_DIMENSIONS`' shape [Agent 2 finding]

### Behavior Parity

| Artifact | Preserved | Changed | Dropped |
|---|---|---|---|
| policy-router-builder.html.tmpl | Offline use, three modes, theme toggle, YAML export | Persistent drafts, guided layout, explicit execution semantics | Destructive implicit reseeding on mode change |
| policy_builder_core.mjs | Valid rule semantics and YAML generation | Versioned project serialization, terminal destinations, optional scoring instructions | None |

### Configuration

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/config/automation.py:155-170` — `ConfidenceGateConfig` is not currently imported or read by `cmd_policy_builder`. Read it via `config.commands.confidence_gate` off the already-constructed `BRConfig` (mirror `fsm/context_seed.py:68`); do **not** mirror `cli/issues/check_readiness.py:78-115`'s raw-JSON bypass — that workaround exists only because `ConfidenceGateConfig` "cannot express 'absent'" for CLI-flag-override semantics `cmd_policy_builder` doesn't have [Agent 2 finding]
- No `config-schema.json` change is needed for this: `confidence_gate` is already fully defined at `scripts/little_loops/config-schema.json:509` [Agent 2 finding]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md:5079-5095` (`#ll-artifact-policy-builder`) — the Flags table (`:5085-5087`) has only `--output`/`-o`, no Save/Open-project or import flag to document yet; prose at `:5081` describing the five lifecycle verbs as fixed/uneditable goes stale once destinations are extensible [Agent 2 finding]
- `docs/guides/POLICY_ROUTER_GUIDE.md:198-242` ("Visual Builder (greenfield)") and `:244-356` ("Issue Lifecycle Mode") — specific passages that go stale: `:227-229,290-291` (verbs "can't be deleted and no new outcome can be added" — contradicted by stop-success/skip/needs-attention destinations), `:295-301` (Verb Table needs a new-destination column), `:234-235` ("Start blank" data-loss framing this issue's persistence work replaces), `:232-234` (YAML-behind-`<details>` framing superseded by the dedicated Export tab), `:240-242` ("builder is *greenfield-only*" framing needs a Save/Open-project caveat) [Agent 2 finding]

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_policy_builder_corpus.py` — pins `conformance_corpus.json` against canonical Python (`evaluate_rules`/`_detect_shadows`); not in this issue's original Tests line and shares the fixture directory this issue's changes touch [Agent 2 + 3 finding]
- `scripts/tests/test_policy_builder_emit.py::TestFeat2301UsabilityStructural` — `test_seed_and_blank_wiring_present` (`:203-207`), `test_rubric_mode_has_no_dt_only_affordances` (`:209-221`), `test_yaml_is_collapsed_behind_details` (`:169-184`) are at risk of breaking if the task-preset reorg renames/removes the `start-blank-btn`, `rules-fieldset`/`outcomes-fieldset`/`tryit-fieldset`, or `yaml-details`/`yaml-preview`/`yaml-summary` ids [Agent 2 finding]
- `scripts/tests/test_policy_builder_emit.py::test_theme_resolution_order_is_stored_stamped_os_light` (`:186-197`) — asserts `initTheme()`'s `stored → __ACTIVE_THEME__ → matchMedia` source-order; new draft-restore bootstrap logic must not perturb this ordering [Agent 2 finding]
- `scripts/tests/test_enh3035_artifact_template_kit.py::test_policy_builder_renders_byte_identically_to_golden_fixture` — will break on any template/core.mjs change; `scripts/tests/fixtures/policy_builder/golden_policy_router_builder.html` needs regeneration as part of this issue [Agent 2 + 3 finding]
- `scripts/tests/test_policy_builder_node_gate.py::test_round_trip_yaml_validates_for_each_mode` — won't break outright (arbitrary terminal-state names are already schema-legal per `fsm/validation/structural_rules.py:26-35`) but has zero coverage of new stop-success/skip/needs-attention states; needs new `.model.json`/`.yaml` fixture(s) under `scripts/tests/fixtures/policy_builder/` plus a new parametrize entry [Agent 3 finding]
- No browser/DOM interaction test harness exists anywhere in the repo (no Playwright/Selenium/jsdom harness — searched repo-wide, no hits). The closest existing convention for "test the emitted page without a browser" is `TestFeat2301UsabilityStructural`'s static string/regex assertions; automated interaction tests for undo/redo, reload persistence, and keyboard operability (required by this issue's Acceptance Criteria) have no precedent to extend and are greenfield [Agent 3 finding]

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-16 — based on codebase analysis:_

- No persistence exists today beyond the theme key: `localStorage` is used exactly once in the builder (`scripts/little_loops/templates/policy-router-builder.html.tmpl:949` read, `:965-970` write), both wrapped in `try/catch` that silently no-ops on failure — the only browser-storage pattern in this artifact-template family to extend for drafts/undo state.
- Mode switch (`policy-router-builder.html.tmpl:868-878`) and "Start blank" (`:940-945`) both fully reassign `state = seedExample(...)`/`blankModel(...)`, discarding in-progress edits with no snapshot — documented in-code as an intentional FEAT-3474 data-loss contract (comment at `:868-872`).
- No project (builder-state) save/open mechanism exists: no JSON export of `state`, no file importer, no File System Access API usage, no YAML→`state` parser for round-tripping. Only the final YAML text can leave the page, via clipboard copy (`:923-926`, no success/failure feedback — `navigator.clipboard.writeText` has no `.then()`/`.catch()`) or a one-shot `<a download>` Blob (`:927-935`).
- Conventions in Force (codebase-pattern-finder, 2026-09-16):
  - Every `localStorage` access in this codebase wraps get/set in its own try/catch with silent-degrade semantics and a single fixed, project-prefixed key — evidence: `policy-router-builder.html.tmpl:949,965-970` (`"ll-policy-builder-theme"`). This is the only localStorage use anywhere in `scripts/little_loops/templates/`; no other artifact template (including `dashboard.llat`) uses browser storage.
  - The one existing collapsible-section precedent in this template is a native `<details>`/`<summary>` (`policy-router-builder.html.tmpl:222-225`), used to demote raw YAML behind a plain-language summary — not to hide form inputs. No existing "advanced settings" tier over fieldsets exists; every fieldset is always-rendered and toggled only per-mode via `hidden` (`applyModeVisibility`, `:837-853`).
  - The closest existing "take current collection + an edit, return a new collection" pure-function precedent is `moveRule(model, index, direction)` (`policy_builder_core.mjs:308-319`, documented pure/non-mutating at `:287-307`) — the codebase's established shape for that kind of transform, though it is a single-array reorder, not a history/undo stack (no undo/redo or draft-history mechanism exists anywhere in this codebase, confirmed by repo-wide search).
  - No JSON schema-version+migration pattern exists in JS anywhere in this codebase; the only version+migration precedent is SQL (`scripts/little_loops/session_store/schema.py:25,126,1492`, `SCHEMA_VERSION` + `_apply_migrations()`), not directly transferable to a JSON document model.
  - No `@media` responsive breakpoint exists in any authored template in `scripts/little_loops/templates/`; the builder's two-column layout is a fixed CSS grid (`policy-router-builder.html.tmpl:32`, `grid-template-columns: 1fr 1fr;`) with no media query.
  - Test conventions for this artifact: `node:test` unit tests import the shipped `policy_builder_core.mjs` directly (`scripts/tests/js/policy_validator.test.mjs`), a cross-language conformance corpus (`scripts/tests/fixtures/policy_builder/conformance_corpus.json`) pins JS-vs-Python parity, and golden `.model.json`/`.yaml` fixture pairs are asserted byte-equal to `serializeLoopYaml(model)` output both in Node and via a Python subprocess gate (`scripts/tests/test_policy_builder_node_gate.py`) that additionally round-trips generated YAML through `ll-loop validate`.

## Program Design

### Types

Proposed BuilderProject carries schemaVersion, generatorVersion, activeMode, and drafts. DraftHistory carries past, present, and future snapshots.

### Signatures

Proposed new pure JS contracts:
- `serializeBuilderProject(project) -> string`
- `parseBuilderProject(text) -> BuilderProject`
- `applyDraftEdit(history, edit) -> DraftHistory`

### Call Path

`applyStateToForm` -> `applyModeVisibility` -> `updatePreview` -> `serializeLoopYaml`.

`cmd_policy_builder` stamps project metadata and configured confidence-gate settings alongside existing grammar/catalog data. The template restores the active draft before rendering the form.

Confirmed anchors (codebase-analyzer, 2026-09-16): `applyStateToForm` (`scripts/little_loops/templates/policy-router-builder.html.tmpl:858-864`), `applyModeVisibility` (`:837-853`), `updatePreview` (`:809-816`) all live in the generated-HTML template's inline module script, not in `policy_builder_core.mjs` — only `serializeLoopYaml` (`scripts/little_loops/templates/policy_builder_core.mjs:1049`) is in the pure-JS core. Today this chain has no persistence step: `applyStateToForm` is called only from the mode-switch (`:868-878`) and "Start blank" (`:940-945`) handlers, each of which fully reassigns `state = seedExample(...)`/`blankModel(...)` first — there is no draft-restore call anywhere in the current chain, and `cmd_policy_builder` (`scripts/little_loops/cli/artifact/policy_builder.py:56-107`) stamps only theme, CSS vars, grammar spec, and skill catalog — no project metadata or confidence-gate settings are read or stamped today (`ConfidenceGateConfig` exists at `scripts/little_loops/config/automation.py:155-170` but is unread by this command).

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-16 — based on codebase analysis:_

New decision logic, unspecified (codebase-analyzer, 2026-09-16): Proposed Solution asks for explicit stop-success, skip, and needs-attention destinations for lifecycle policies. Today the builder emits exactly a binary terminal model, and it differs by mode:
- `issue_lifecycle` (`_serializeIssueLifecycle`, `scripts/little_loops/templates/policy_builder_core.mjs:974-1041`): hardcodes `on_max_steps: failed` (:1002) and every verb state carries `on_error: failed` (:1031); only two terminal states are ever emitted, `done: {terminal: true}` and `failed: {terminal: true}` (:1034-1039). Reaching `done` goes through `_outcomeStateLines()` (:687-719) / `_doneStateName()` (:733-739) for any outcome whose `transition.kind === "finish"`.
- `decision_table` (`_serializeDecisionTable`, :741-833): uses the same `_outcomeStateLines`/`_doneStateName` machinery but emits no `on_max_steps` line at all.
- `rubric` (`_serializeRubric`, :834-909): a single `done: {terminal: true}` (:906-907) reached only via the high-threshold route (`on_yes: done`, :875); no `on_max_steps` handling either.
- No `stop-success`, `skip`, or `needs-attention` concept exists anywhere in the builder's Python, template, or core JS today (repo-wide search, no hits).
Exact inputs/values not yet pinned down by Proposed Solution: which frontmatter dimension(s) or rule predicates route to `skip` vs `needs-attention` vs the existing `failed`; whether `stop-success` is a new alias for `done` or a distinct terminal state; and whether `on_max_steps`/`on_error` per-mode divergence (decision_table/rubric currently define neither) is intentional or itself a gap. These are implementer decisions, not resolved here.

## Implementation Steps

1. Define and test the versioned project model, import validation, per-mode draft storage, and undo/redo.
2. Reorganize the form with task presets, advanced action settings, and an accurate transition summary.
3. Implement explicit destinations, grading instructions, action metadata, and project gate explanations.
4. Add export/run guidance, accessible feedback, and responsive styling.
5. Exercise offline persistence, round trips, and browser workflows; update fixtures and reference material.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Inject at `scripts/little_loops/cli/artifact/policy_builder.py:66-94` — read `config.commands.confidence_gate` off the already-constructed `BRConfig` (mirror `fsm/context_seed.py:68`) and stamp its `readiness_threshold`/`outcome_threshold` alongside the existing `css_vars`/`spec`/`catalog` stamping; no new import path required
- Update `scripts/tests/fixtures/policy_builder/golden_policy_router_builder.html` — regenerate the byte-exact golden fixture consumed by `test_policy_builder_renders_byte_identically_to_golden_fixture`
- Add `scripts/tests/fixtures/policy_builder/*.model.json`/`.yaml` fixture pair(s) for the new stop-success/skip/needs-attention terminal destinations, plus a matching parametrize entry in `test_policy_builder_node_gate.py::test_round_trip_yaml_validates_for_each_mode`
- Establish (or explicitly scope out in Scope Boundaries) an automated browser/DOM interaction test harness for the reload-persistence, undo/redo, and keyboard-operability Acceptance Criteria — none exists in this codebase today
- Update `docs/reference/CLI.md:5079-5095` (`#ll-artifact-policy-builder`) and `docs/guides/POLICY_ROUTER_GUIDE.md:198-356` (Visual Builder / Issue Lifecycle Mode sections) to replace stale five-verb/binary-terminal/YAML-disclosure/greenfield-only framing
- If a new `parseBuilderProject` import-validation error is added, follow the existing "throw with a matchable message" convention (`scripts/tests/js/policy_validator.test.mjs:327-329`, `parseFrontmatterBlock`'s `Can't read line N` errors) rather than a new error-text shape

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-16 — based on codebase analysis:_

- `issue_lifecycle` mode's built-in field list is `BUILTIN_FRONTMATTER_DIMENSIONS` (`scripts/little_loops/templates/policy_builder_core.mjs:85-95`, 9 fixed dims); the five action editors are a single generic `renderLifecycleOutcomes()` loop (`scripts/little_loops/templates/policy-router-builder.html.tmpl:456-552`) over the fixed `LIFECYCLE_VERBS` list (`policy_builder_core.mjs:104-140`) — not five separately-coded editors, so "collapse under advanced settings" is a layout/visibility change over this existing loop, not a rewrite of it. `renderRules()` (`policy-router-builder.html.tmpl:559-675`) is already shared unchanged across `decision_table` and `issue_lifecycle`.
- The grading-subject field (`#f-subject`, `policy-router-builder.html.tmpl:143-144`) is shown (not hidden by `applyModeVisibility`) but never read by `_serializeIssueLifecycle()` — confirmed inert for this mode, matching the issue's Current Behavior claim.
- `moveRule(model, index, direction)` (`policy_builder_core.mjs:308-319`, pure/non-mutating per its docstring at :287-307) is this codebase's only existing "collection + edit descriptor -> new collection" precedent and the closest analog to the proposed `applyDraftEdit(history, edit) -> DraftHistory`; no undo/redo or history-stack implementation exists anywhere else to model against (repo-wide search, no hits).
- Existing test surfaces to extend rather than duplicate: `scripts/tests/js/policy_validator.test.mjs` (node:test, imports `policy_builder_core.mjs` exports directly, one `test()` per exported function), `scripts/tests/fixtures/policy_builder/conformance_corpus.json` (cross-language JS/Python parity corpus) and golden `.model.json`/`.yaml` fixture pairs asserted byte-equal in both `policy_validator.test.mjs` and `scripts/tests/test_policy_builder_node_gate.py` (which also round-trips generated YAML through `ll-loop validate`). `scripts/tests/test_policy_builder_emit.py` calls `cmd_policy_builder(args, logger)` directly, never the console script.

## Impact

- Priority: P3 — improves repeat use and prevents loss of unsaved authoring work.
- Effort: Large — persistence, interaction design, and backwards-compatible model evolution.
- Risk: Medium — migrations and reset behavior must preserve user work.
- Breaking change: No intended incompatibility for existing valid generated loops.

## API/Interface

Add Save project / Open project with a versioned JSON envelope; YAML remains the execution export. Reject unsupported project versions without overwriting current work. Add optional dimension instructions and explicit terminal destination metadata with backward-compatible defaults for existing models. Arbitrary hand-edited YAML import is not included.

## Acceptance Criteria

- [ ] Edits survive reload and round-trip mode switching; undo/redo restores rules, fields, actions, and transitions in automated interaction tests.
- [ ] Save/Open project round-trips all authoring settings and generates equivalent YAML; corrupt/unsupported imports preserve the existing draft and show an error.
- [ ] Disabled/unavailable browser storage leaves authoring and explicit project-file saving functional, with visible save-state feedback.
- [ ] Lifecycle hides grading-only inputs; rules precede advanced action editors; 375px and desktop viewport tests show no page-level horizontal overflow and keyboard-accessible controls.
- [ ] Summaries reflect actual transitions, distinguish state steps from attempts, and clearly indicate whether implementation is followed by verification.
- [ ] Stop-success, skip, and needs-attention destinations emit valid loops; reopening existing five-verb models preserves their behavior.
- [ ] Project gate thresholds and skill descriptions/argument hints are displayed; optional scoring instructions appear in emitted prompts and persist through project round trips.
- [ ] Copy success/failure is visible, and export guidance includes a concrete destination, validation command, and run command with required issue input.

## Success Metrics

Automated round trips lose zero authored fields. Reload and mode changes preserve every tested draft. Every supported mode has tested save/open and keyboard-driven export paths.

## Scope Boundaries

Includes persistent authoring, terminology/layout, action and scoring explanations, lifecycle presets/destinations, and offline export guidance. Excludes arbitrary YAML round-trip editing, named scenario suites, real issue loading through a server, and run submission. Correctness fixes and consumer discovery are a separate workstream; coordinate shared model changes rather than duplicating those fixes.

## Related Key Documentation

| Category | Document | Relevance |
|---|---|---|
| Architecture | docs/ARCHITECTURE.md | Project context stamping and artifact conventions |
| Reference | docs/reference/CLI.md | Saved artifact generation and usage |
| Guide | docs/guides/POLICY_ROUTER_GUIDE.md | Authoring flow and lifecycle semantics |

## Status

**Open** | Created: 2026-09-16 | Priority: P3


## Session Log
- `/ll:wire-issue` - 2026-09-16T21:29:53 - `0e35d235-ff66-480a-930e-d4d9ddd5eeb9.jsonl`
- `/ll:refine-issue` - 2026-09-16T21:07:15 - `7e302668-e6b7-4dea-830f-330bbfd02fc0.jsonl`
- `/ll:capture-issue` - 2026-09-16T20:55:13 - `64af6deb-56e5-4bde-9534-85751c1782ca.jsonl`
