---
id: ENH-3487
parent: EPIC-3493
epic: EPIC-3493
type: ENH
title: Policy builder persistence, undo/redo, and saved projects
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-16'
captured_at: '2026-09-16T20:54:20Z'
labels:
- policy-builder
- captured
decision_needed: false
depends_on:
- BUG-3486
relates_to:
- FEAT-3474
- ENH-3491
- ENH-3492
blocks:
- FEAT-3488
- ENH-3491
confidence_score: 100
outcome_confidence: 75
score_complexity: 14
score_test_coverage: 18
score_ambiguity: 25
score_change_surface: 18
---

# ENH-3487: Policy builder persistence, undo/redo, and saved projects

## Summary

Improve policy-builder persistence so users can safely maintain a policy over multiple sessions. Preserve the self-contained offline HTML experience while adding per-mode drafts, versioned saved projects, undo/redo, and copy/save feedback.

Captured from the 2026-09-16 review following FEAT-3474, as the second of three requested workstreams. Split on 2026-09-16: layout, presets, responsive CSS, and execution summary moved to ENH-3491; terminal destinations, scoring instructions, and confidence-gate stamping moved to ENH-3492. This issue is the first of the three to land because BUG-3486 touches the same editing-state code.

## Current Behavior

The page holds authoring state only in memory; localStorage stores the theme. Mode changes replace all work with a seed, and refresh loses edits. Only YAML is exported, with no builder-project reopening. Copy has no success/failure feedback.

## Expected Behavior

Edits survive reload and mode exploration. Users can save/reopen a portable versioned project and undo/redo changes. Copy and save report success or failure. Offline authoring remains usable without a server or browser storage permission.

## Motivation

Prevent accidental loss of authoring work and make the builder useful for ongoing policy maintenance.

## Proposed Solution

- Persist independent per-mode drafts in localStorage under the existing `ll-policy-builder-` key prefix (one key per mode), each get/set wrapped in its own try/catch with silent-degrade semantics, matching the theme-key precedent. Mode switch restores that mode's draft instead of reseeding; "Start blank" still reseeds but pushes a history entry first. Update the in-code comment at the mode-switch handler (tmpl `:916-920`) that documents reseeding as an intentional data-loss contract. On load, structurally valid drafts are restored even when `validateBuilderModel` reports export-readiness errors. An unfinished predicate, empty action body, missing reference, or invalid budget is editable work, not corruption. Only malformed JSON or an invalid project/draft structure falls back to `seedExample(mode)` with a live-region diagnostic; a failed file import instead preserves the current project. Keep the rejected stored payload available for recovery until an explicit replacement edit.
- **Draft envelope (review 2026-09-17)**: `drafts[mode]` is a wrapper `{model}` — not the bare model — so FEAT-3488 can add sibling keys (`scenarios: []`) without polluting the object `validateBuilderModel` checks or forcing a `schemaVersion` bump. `parseBuilderProject` structurally validates `drafts[mode].model`; localStorage stores the same wrapper. Require supported mode keys, matching `model.mode`, object/array field shapes, and a draft for `activeMode`. Do not mistake the semantic diagnostics from `validateBuilderModel` for structural validation. Preserve unknown JSON-compatible draft metadata on save/open and history snapshots so later scenario fields are not silently dropped.
- Undo/redo as a pure history stack in `policy_builder_core.mjs`: `applyDraftEdit(history, edit) -> DraftHistory` with `{past, present, future}`. **History scope is the whole project**: `present` is `{activeMode, drafts}`, not a single draft, because mode switch is itself a history entry — undo across a mode switch restores the previous `activeMode` and re-renders that draft. Granularity: one history entry per committed field change (`change` event, rule add/move/delete, mode switch, start-blank, and any preset applied by ENH-3491), never per keystroke. Cap `past` at 100 entries. Snapshots are deep copies (same discipline as `_cloneDims`/`_cloneOutcomes`, `:694-699`).
- **Keyboard shortcuts**: the document-level Ctrl/Cmd+Z and Ctrl/Cmd+Shift+Z handler ignores events whose target is an `input`, `textarea`, `select`, or contenteditable element, so native per-keystroke undo inside a field is untouched; the Undo/Redo buttons always act on the project history.
- Save project / Open project as a versioned JSON envelope `BuilderProject {schemaVersion, generatorVersion, projectId, activeMode, drafts}` via pure `serializeBuilderProject(project) -> string` and `parseBuilderProject(text) -> BuilderProject` in core.mjs. **`generatorVersion` source (review 2026-09-17)**: nothing stamps a version into the page today (`cmd_policy_builder` stamps only theme, CSS vars, grammar, catalog, core JS — `scripts/little_loops/cli/artifact/policy_builder.py:92-95`). Add a `window.__GENERATOR_VERSION__` stamp from `little_loops.__version__` in `cmd_policy_builder` (one `html.replace` next to the existing ones); this is the one `policy_builder.py` change in this issue. Version policy: `schemaVersion` starts at 1; reject a newer `schemaVersion` with a matchable error without touching the current draft; older versions are migrated in `parseBuilderProject` (no migrations exist at v1, but the hook is the place they go). Missing or non-object `drafts`, unknown `activeMode`, missing/invalid `projectId`, a draft without a `model` key, mismatched draft-key/model modes, or structurally malformed models are import errors. Semantic errors remain visible and block YAML Copy/Download, but never project Save/Open or draft persistence. `generatorVersion` is informational only (never gates import).
- **Project identity**: create an opaque UUID `projectId` once for a new project; inject ID generation at the UI boundary so core serialization stays pure. Save/Open, reload, preset changes, and undo/redo preserve it. It identifies the builder document, not a filesystem project root. Persist project metadata (`projectId`, `activeMode`, schema/generator versions) alongside the per-mode wrappers; a fresh project gets a new ID. FEAT-3498 binds this document to the server-selected repository separately. Tests cover stable IDs across all these operations.
- Save uses the existing `<a download>` Blob path; Open uses `<input type=file>` + `FileReader`. No File System Access API, no server.
- Copy reports success/failure by attaching `.then/.catch` to `navigator.clipboard.writeText` and surfacing it in a live region; the same live region shows draft-saved / storage-unavailable state.
- Export guidance under the YAML preview gives a concrete destination path (`loops/<name>.yaml`), the `ll-loop validate loops/<name>.yaml` command, and the run command. For `issue_lifecycle` the loop self-declares `parameters.issue_id` (required); `ll-loop run` binds a positional input to `fsm.input_key` or, when the input is a JSON object, to matching context keys (`scripts/little_loops/cli/loop/run.py:172-185`), so the guidance shows `ll-loop run loops/<name>.yaml '{"issue_id": "BUG-123"}'`. Rubric emits `input_key: subject` and `required_inputs: ["subject"]`, so show `ll-loop run loops/<name>.yaml "Subject to evaluate"`. Decision-table guidance follows its generated input declarations and must not copy the lifecycle issue-ID example.

Regression coverage without a DOM harness (mitigates the Option B cost below): every new contract above lives in `policy_builder_core.mjs`, not the template, and gets `node:test` cases in `scripts/tests/js/policy_validator.test.mjs` plus a golden `.project.json` fixture under `scripts/tests/fixtures/policy_builder/` asserted to round-trip byte-equal. Only the DOM wiring (event handlers, localStorage, file input) stays manually verified.

### Option A: Adopt a browser/DOM interaction test harness

Add a jsdom (or Playwright) DOM harness to automate the reload-persistence,
undo/redo, and keyboard-operability Acceptance Criteria against the emitted
`policy-router-builder.html`, driven by the existing Node test runner rather than
introducing a new one.
- **Tradeoff**: Gives the ACs real automated coverage and a reusable harness for
  future artifact-template interaction tests. Adds a new third-party dependency
  (jsdom or Playwright) to `scripts/pyproject.toml`/Node tooling, which the
  project's "minimize third-party dependencies" policy requires justifying; a
  browser-driving harness (Playwright) is heavier to install and run in CI/local
  test loops than jsdom's DOM-only emulation.

### Option B: Scope automated interaction testing out; verify manually

> **Selected:** Option B — no repo precedent for a pinned Node/browser-automation dependency exists to extend; manual-verification-on-close is the repo's established pattern for this kind of gap.

Amend `## Scope Boundaries` to explicitly exclude automated interaction-test
coverage for undo/redo, reload-persistence, and keyboard operability from this
issue's Acceptance Criteria; reword those ACs to describe the required behavior
without mandating "automated interaction tests," and rely on manual
browser verification (documented steps) before closing the issue.
- **Tradeoff**: No new dependency, no new test infrastructure to build and
  maintain; ships faster. Leaves these behaviors without regression protection —
  a future template/core.mjs change could silently break undo/redo or keyboard
  access with no test to catch it.

### Decision Rationale

**Selected:** Option B — Scope automated interaction testing out; verify manually.

**Reasoning:** No `package.json` (or any pinned-Node-dependency mechanism) exists anywhere in the repo outside vendored third-party tool trees — jsdom/Playwright would be a first-of-its-kind infrastructure addition, conflicting with the project's "minimize third-party dependencies" policy. By contrast, accepting manual verification for a behavioral-testing gap on a generated-HTML artifact is a well-worn, repeatedly-accepted repo pattern (`.issues/enhancements/P3-ENH-1770-...md:115` is the directly analogous same-artifact-family precedent), and CLAUDE.md's Testing & CI Policy does not require every Acceptance Criterion to carry automated coverage. Option B's main cost — no regression protection for the new undo/redo subsystem — is real but is partially mitigated by extending the existing `TestFeat2301UsabilityStructural` string-assertion style, and is outweighed by Option A's larger, unproven infrastructure lift.

| Dimension | Option A (harness) | Option B (manual) |
|---|---|---|
| Consistency | 1 | 3 |
| Simplicity | 1 | 3 |
| Testability | 2 | 1 |
| Risk | 1 | 1 |
| **Total** | **5/12** | **8/12** |

**Key evidence:**
- No `package.json` or pinned Node dependency exists anywhere in the repo (only vendored `node_modules/` in unrelated adapter tooling) — Option A would introduce new dependency-management infrastructure, not just a new pin.
- `scripts/tests/test_policy_builder_node_gate.py:53-79` shows a new `.mjs` test file is auto-picked up with zero CI-wiring changes — the only point favoring Option A.
- Dozens of prior issues (e.g. `.issues/bugs/P1-BUG-076-...md:95`, `.issues/enhancements/P3-ENH-1770-...md:115`) accept manual verification as sufficient to close, including one directly analogous generated-HTML-artifact case.
- The undo/redo/persistence surface (`policy_builder_core.mjs` 1237 lines, `policy-router-builder.html.tmpl` 979 lines) is larger than prior manual-fallback precedents, so the regression-risk tradeoff is real, not negligible.

## Integration Map

- Files to modify: scripts/little_loops/templates/policy_builder_core.mjs; scripts/little_loops/templates/policy-router-builder.html.tmpl; scripts/little_loops/cli/artifact/policy_builder.py (one added `__GENERATOR_VERSION__` stamp only; gate stamping stays in ENH-3492).
- Dependent files: scripts/little_loops/artifact_template_kit.py for shared shell conventions; scripts/tests/fixtures/policy_builder/ for generated fixtures.
- Similar patterns: existing theme storage fallback, flat JSON-friendly builder model, project-derived stamping.
- Tests: scripts/tests/js/policy_validator.test.mjs, scripts/tests/test_policy_builder_emit.py, scripts/tests/test_policy_builder_node_gate.py; manual browser workflows for reload, switching, import, undo.
- Configuration: none; do not add a server requirement.

### Dependent Files (Callers/Importers)

- `scripts/little_loops/cli/artifact/__init__.py:197` — `main_artifact` dispatches the `policy-builder` subcommand to `cmd_policy_builder`
- `scripts/tests/test_enh3035_artifact_template_kit.py:65` — `test_policy_builder_renders_byte_identically_to_golden_fixture` calls `cmd_policy_builder` directly
- `scripts/tests/test_policy_builder_emit.py:43,50,83` — `_emit_html`, `test_emit_writes_html`, `test_emitted_grammar_matches_canonical` call `cmd_policy_builder` directly (never the console script)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/fsm/frontmatter_scores.py` — unaffected: this issue does not change `BUILTIN_FRONTMATTER_DIMENSIONS`' shape (scoring instructions moved to ENH-3492) [Agent 2 finding]

### Behavior Parity

| Artifact | Preserved | Changed | Dropped |
|---|---|---|---|
| policy-router-builder.html.tmpl | Offline use, three modes, theme toggle, YAML export, all element ids asserted by `TestFeat2301UsabilityStructural` | Persistent drafts, undo/redo, Save/Open project, copy/save feedback | Destructive implicit reseeding on mode change |
| policy_builder_core.mjs | Valid rule semantics and YAML generation (emitted YAML unchanged for every existing model) | New pure exports: `applyDraftEdit`, `serializeBuilderProject`, `parseBuilderProject` | None |

### Configuration

No configuration changes. Confidence-gate stamping moved to ENH-3492.

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md:5079-5095` (`#ll-artifact-policy-builder`) — the Flags table (`:5085-5087`) has only `--output`/`-o`, no Save/Open-project or import flag to document yet; prose at `:5081` describing the five lifecycle verbs as fixed/uneditable goes stale once destinations are extensible [Agent 2 finding]
- `docs/guides/POLICY_ROUTER_GUIDE.md:258-303` ("Visual Builder (greenfield)") and `:304-416` ("Issue Lifecycle Mode") — specific passages that go stale: `:300` ("Start blank" data-loss framing this issue's persistence work replaces), `:305` ("builder is *greenfield-only*" framing needs a Save/Open-project caveat) (re-verified 2026-09-17). Verb-table and YAML-disclosure passages (`:287-294,350-361`) move to ENH-3491/ENH-3492 [Agent 2 finding] (line numbers re-verified `/ll:verify-issues` 2026-09-16: a new "Failure Routing and Clean-Slate Scoring" subsection was inserted earlier in the doc, shifting everything from "Visual Builder" onward by +60 lines)

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_policy_builder_corpus.py` — pins `conformance_corpus.json` against canonical Python (`evaluate_rules`/`_detect_shadows`); not in this issue's original Tests line and shares the fixture directory this issue's changes touch [Agent 2 + 3 finding]
- `scripts/tests/test_policy_builder_emit.py::TestFeat2301UsabilityStructural` — `test_seed_and_blank_wiring_present` (`:203-207`), `test_rubric_mode_has_no_dt_only_affordances` (`:209-221`), `test_yaml_is_collapsed_behind_details` (`:169-184`) are at risk of breaking if the task-preset reorg renames/removes the `start-blank-btn`, `rules-fieldset`/`outcomes-fieldset`/`tryit-fieldset`, or `yaml-details`/`yaml-preview`/`yaml-summary` ids [Agent 2 finding]
- `scripts/tests/test_policy_builder_emit.py::test_theme_resolution_order_is_stored_stamped_os_light` (`:186-197`) — asserts `initTheme()`'s `stored → __ACTIVE_THEME__ → matchMedia` source-order; new draft-restore bootstrap logic must not perturb this ordering [Agent 2 finding]
- `scripts/tests/test_enh3035_artifact_template_kit.py::test_policy_builder_renders_byte_identically_to_golden_fixture` — will break on any template/core.mjs change; `scripts/tests/fixtures/policy_builder/golden_policy_router_builder.html` needs regeneration as part of this issue [Agent 2 + 3 finding]
- No browser/DOM interaction test harness exists anywhere in the repo (no Playwright/Selenium/jsdom harness — searched repo-wide, no hits). The closest existing convention for "test the emitted page without a browser" is `TestFeat2301UsabilityStructural`'s static string/regex assertions; automated interaction tests for undo/redo and reload persistence have no precedent to extend; resolved by Option B (manual DOM verification) plus pure-function `node:test` coverage of the history/serialization contracts in core.mjs [Agent 3 finding]

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-16 — based on codebase analysis:_

- No persistence exists today beyond the theme key: `localStorage` is used exactly once in the builder (`scripts/little_loops/templates/policy-router-builder.html.tmpl:959` read, `:980` write), both wrapped in `try/catch` that silently no-ops on failure — the only browser-storage pattern in this artifact-template family to extend for drafts/undo state.
- Mode switch (`policy-router-builder.html.tmpl:878-887`) and "Start blank" (`:945-953`) both fully reassign `state = seedExample(...)`/`blankModel(...)`, discarding in-progress edits with no snapshot — documented in-code as an intentional FEAT-3474 data-loss contract (comment at `:878-882`).
- No project (builder-state) save/open mechanism exists: no JSON export of `state`, no file importer, no File System Access API usage, no YAML→`state` parser for round-tripping. Only the final YAML text can leave the page, via clipboard copy (`:933-936`, no success/failure feedback — `navigator.clipboard.writeText` has no `.then()`/`.catch()`) or a one-shot `<a download>` Blob (`:937-944`).
- Conventions in Force (codebase-pattern-finder, 2026-09-16):
  - Every `localStorage` access in this codebase wraps get/set in its own try/catch with silent-degrade semantics and a single fixed, project-prefixed key — evidence: `policy-router-builder.html.tmpl:949,965-970` (`"ll-policy-builder-theme"`). This is the only localStorage use anywhere in `scripts/little_loops/templates/`; no other artifact template (including `dashboard.llat`) uses browser storage.
  - The one existing collapsible-section precedent in this template is a native `<details>`/`<summary>` (`policy-router-builder.html.tmpl:222-225`), used to demote raw YAML behind a plain-language summary — not to hide form inputs. No existing "advanced settings" tier over fieldsets exists; every fieldset is always-rendered and toggled only per-mode via `hidden` (`applyModeVisibility`, `:837-853`).
  - The closest existing "take current collection + an edit, return a new collection" pure-function precedent is `moveRule(model, index, direction)` (`policy_builder_core.mjs:678-689`, docstring above it; anchors post-`8faffee5a`) — the codebase's established shape for that kind of transform, though it is a single-array reorder, not a history/undo stack (no undo/redo or draft-history mechanism exists anywhere in this codebase, confirmed by repo-wide search).
  - No JSON schema-version+migration pattern exists in JS anywhere in this codebase; the only version+migration precedent is SQL (`scripts/little_loops/session_store/schema.py:25,126,1492`, `SCHEMA_VERSION` + `_apply_migrations()`), not directly transferable to a JSON document model.
  - No `@media` responsive breakpoint exists in any authored template in `scripts/little_loops/templates/`; the builder's two-column layout is a fixed CSS grid (`policy-router-builder.html.tmpl:32`, `grid-template-columns: 1fr 1fr;`) with no media query.
  - Test conventions for this artifact: `node:test` unit tests import the shipped `policy_builder_core.mjs` directly (`scripts/tests/js/policy_validator.test.mjs`), a cross-language conformance corpus (`scripts/tests/fixtures/policy_builder/conformance_corpus.json`) pins JS-vs-Python parity, and golden `.model.json`/`.yaml` fixture pairs are asserted byte-equal to `serializeLoopYaml(model)` output both in Node and via a Python subprocess gate (`scripts/tests/test_policy_builder_node_gate.py`) that additionally round-trips generated YAML through `ll-loop validate`.

## Program Design

### Types

`BuilderProject {schemaVersion: 1, generatorVersion: string, projectId: string, activeMode: Mode, drafts: {[mode]: Draft}}`; `Draft {model: Model}` (wrapper, so later issues add sibling keys such as FEAT-3488's `scenarios`). `DraftHistory {past: ProjectSnapshot[], present: ProjectSnapshot, future: ProjectSnapshot[]}` where `ProjectSnapshot = {activeMode, drafts}` (whole-project scope).

### Signatures

Proposed new pure JS contracts:
- `serializeBuilderProject(project) -> string`
- `parseBuilderProject(text) -> BuilderProject` — structural validation/migration only; semantic errors do not reject an editable project
- `validateProjectStructure(project) -> diagnostics[]` — validates the envelope, draft shapes, and mode agreement without testing export readiness
- `applyDraftEdit(history, edit) -> DraftHistory`

### Call Path

`applyStateToForm` -> `applyModeVisibility` -> `updatePreview` -> `serializeLoopYaml`.

The template restores the active draft (after `initTheme()`) before rendering the form, checking its structural shape and preserving semantic errors for `validateBuilderModel` to display (only corrupt structures fall back to the seed); every committed edit goes through `applyDraftEdit` and then persists the draft. `cmd_policy_builder` gains only the `__GENERATOR_VERSION__` stamp.

Confirmed anchors (codebase-analyzer, 2026-09-16; re-verified `/ll:verify-issues` 2026-09-16 against BUG-3489/BUG-3486 working-tree edits): `applyStateToForm` (`scripts/little_loops/templates/policy-router-builder.html.tmpl:868-875`), `applyModeVisibility` (`:847-862`), `updatePreview` (`:808-824`, now wraps `serializeLoopYaml` in try/catch per the in-progress BUG-3489 fix) all live in the generated-HTML template's inline module script, not in `policy_builder_core.mjs` — only `serializeLoopYaml` (`scripts/little_loops/templates/policy_builder_core.mjs:1130`) is in the pure-JS core. Today this chain has no persistence step: `applyStateToForm` is called only from the mode-switch (`:878-887`) and "Start blank" (`:945-953`) handlers, each of which fully reassigns `state = seedExample(...)`/`blankModel(...)` first — there is no draft-restore call anywhere in the current chain, and `cmd_policy_builder` (`scripts/little_loops/cli/artifact/policy_builder.py:61-112`) stamps only theme, CSS vars, grammar spec, and skill catalog — no project metadata or confidence-gate settings are read or stamped today (`ConfidenceGateConfig` exists at `scripts/little_loops/config/automation.py:155-170` but is unread by this command).

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-16 — based on codebase analysis:_

Terminal-destination analysis (binary `done`/`failed` model, per-mode `on_max_steps`/`on_error` divergence) moved to ENH-3492 with the open decision questions.

_Added by `/ll:refine-issue` — 2026-09-17 — based on codebase analysis:_

- Anchor re-verification (codebase-analyzer, 2026-09-17): commit `8faffee5a` ("fix(policy-builder): unify model validation, compiled Try-it evaluation, and parser parity", 2026-09-16 22:03:30-05:00) landed after the prior `/ll:verify-issues` pass (2026-09-17T02:36:58) and shifted every anchor this issue's Program Design/Root Cause sections cite. `policy-router-builder.html.tmpl` grew from 979 to 1037 lines; `policy_builder_core.mjs` grew from 1237 to 1711 lines. Corrected anchors (all confirmed by direct read): `updatePreview` `840-864`, `renderAll` `866-883`, `applyModeVisibility` `885-901`, `applyStateToForm` `906-912`, mode-switch `onchange` handler `921-926` (reseed comment `916-920`), clipboard copy `981-984`, download-blob handler `985-993`, "Start blank" handler `998-1003` (comment `994-997`), theme localStorage read `1007` inside `initTheme()` `1006-1022`, theme localStorage write `1028` inside the theme-toggle handler `1023-1029`; in `policy_builder_core.mjs`: `validateBuilderModel` `640-655`, `moveRule` `678-689` (was cited at `374-384`), `seedExample` `782-846`, `blankModel` `857-887`, `serializeLoopYaml` `1448-1456` (was cited at `1130`), the `window.PolicyBuilderCore` export bridge `1679-1711`.
- New anchors not previously cited, relevant to the proposed `applyDraftEdit`/`serializeBuilderProject`/`parseBuilderProject` additions: `buildModel()` (`policy-router-builder.html.tmpl:248-268`) is the template's sole translation point from the live `state` object into the flat model shape `serializeLoopYaml`/`validateBuilderModel` expect — described in-code as "close to identity" (`:240-245`). `_cloneDims`/`_cloneOutcomes` (`policy_builder_core.mjs:694-699`) deep-copy `BUILTIN_FRONTMATTER_DIMENSIONS`/`LIFECYCLE_VERBS` before every reseed so no session mutates the shared constants — the same deep-copy discipline a `DraftHistory` snapshot would need for its `past`/`future` entries.
- Repo-wide search confirms none of `applyDraftEdit`, `serializeBuilderProject`, `parseBuilderProject`, `DraftHistory`, `BuilderProject` exist in code today (hits only in this issue's and FEAT-3488's `.issues/` prose) — the proposed exports are net-new, not renames of existing symbols.

## Implementation Steps

1. Add `applyDraftEdit`, `serializeBuilderProject`, `parseBuilderProject` to core.mjs (with the `{model}` draft wrapper and whole-project history scope) plus `node:test` cases and a golden `.project.json` fixture; add the `__GENERATOR_VERSION__` stamp to `cmd_policy_builder`.
2. Wire per-mode localStorage drafts, draft restore on load (after `initTheme()`, preserving the stored → stamped → OS theme order; structural restore validation, preservation of unfinished drafts, then export-readiness diagnostics), and history push on committed edits in the template.
3. Add Save/Open project controls, undo/redo buttons and keyboard shortcuts (ignored when focus is in an editable element), the live-region feedback, and copy success/failure handling.
4. Add export/run guidance text.
5. Regenerate the golden HTML fixture; update CLI.md and POLICY_ROUTER_GUIDE.md passages listed in Documentation; run the documented manual browser checklist and record results in the Resolution.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Update `scripts/tests/fixtures/policy_builder/golden_policy_router_builder.html` — regenerate the byte-exact golden fixture consumed by `test_policy_builder_renders_byte_identically_to_golden_fixture`
- Add a `scripts/tests/fixtures/policy_builder/*.project.json` golden fixture asserted byte-equal through `parseBuilderProject` → `serializeBuilderProject` in `policy_validator.test.mjs`
- Automated browser/DOM interaction testing is scoped out (Option B); manual verification checklist is recorded in the Resolution on close
- Update `docs/reference/CLI.md:5079-5095` (`#ll-artifact-policy-builder`) and `docs/guides/POLICY_ROUTER_GUIDE.md:300,305` ("Start blank" data-loss framing, "greenfield-only" framing) — five-verb/terminal/YAML-disclosure passages belong to ENH-3491/ENH-3492
- If a new `parseBuilderProject` import-validation error is added, follow the existing "throw with a matchable message" convention (`scripts/tests/js/policy_validator.test.mjs:327-329`, `parseFrontmatterBlock`'s `Can't read line N` errors) rather than a new error-text shape

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-16 — based on codebase analysis:_

- `issue_lifecycle` mode's built-in field list is `BUILTIN_FRONTMATTER_DIMENSIONS` (`scripts/little_loops/templates/policy_builder_core.mjs:85-95`, 9 fixed dims); the five action editors are a single generic `renderLifecycleOutcomes()` loop (`scripts/little_loops/templates/policy-router-builder.html.tmpl:456-552`) over the fixed `LIFECYCLE_VERBS` list (`policy_builder_core.mjs:104-140`) — not five separately-coded editors, so "collapse under advanced settings" is a layout/visibility change over this existing loop, not a rewrite of it. `renderRules()` (`policy-router-builder.html.tmpl:559-675`) is already shared unchanged across `decision_table` and `issue_lifecycle`.
- The grading-subject field (`#f-subject`, `policy-router-builder.html.tmpl:143-144`) is shown (not hidden by `applyModeVisibility`) but never read by `_serializeIssueLifecycle()` — confirmed inert for this mode, matching the issue's Current Behavior claim.
- `moveRule(model, index, direction)` (`policy_builder_core.mjs:678-689`, pure/non-mutating per its docstring; anchors post-`8faffee5a`) is this codebase's only existing "collection + edit descriptor -> new collection" precedent and the closest analog to the proposed `applyDraftEdit(history, edit) -> DraftHistory`; no undo/redo or history-stack implementation exists anywhere else to model against (repo-wide search, no hits).
- Existing test surfaces to extend rather than duplicate: `scripts/tests/js/policy_validator.test.mjs` (node:test, imports `policy_builder_core.mjs` exports directly, one `test()` per exported function), `scripts/tests/fixtures/policy_builder/conformance_corpus.json` (cross-language JS/Python parity corpus) and golden `.model.json`/`.yaml` fixture pairs asserted byte-equal in both `policy_validator.test.mjs` and `scripts/tests/test_policy_builder_node_gate.py` (which also round-trips generated YAML through `ll-loop validate`). `scripts/tests/test_policy_builder_emit.py` calls `cmd_policy_builder(args, logger)` directly, never the console script.

## Impact

- Priority: P3 — improves repeat use and prevents loss of unsaved authoring work.
- Effort: Medium — persistence and history stack; no emitted-YAML change.
- Risk: Medium — draft restore and reset behavior must preserve user work.
- Breaking change: No intended incompatibility for existing valid generated loops.

## API/Interface

Add Save project / Open project with a versioned JSON envelope (`schemaVersion: 1`); YAML remains the execution export. Reject newer project versions without overwriting current work. New core.mjs exports: `applyDraftEdit`, `serializeBuilderProject`, `parseBuilderProject`. Arbitrary hand-edited YAML import is not included.

## Acceptance Criteria

- [ ] `applyDraftEdit`, `serializeBuilderProject`, `parseBuilderProject` are exported from `policy_builder_core.mjs` and covered by `node:test` cases (undo/redo restores rules, fields, actions, transitions, and `activeMode` across a mode switch; a golden `.project.json` fixture with `drafts[mode] = {model}` round-trips byte-equal).
- [ ] Edits survive reload and round-trip mode switching in the browser; undo/redo works via buttons and Ctrl/Cmd+Z / Shift+Z, and the shortcuts do not intercept native undo while focus is in a text field — verified by documented manual browser testing (Scope Boundaries: DOM interaction tests are out of scope).
- [ ] Save/Open project round-trips all authoring settings and generates equivalent YAML; corrupt, non-object, missing-`model`, or newer-`schemaVersion` imports preserve the existing draft and show a matchable error; a corrupt localStorage draft falls back to the seed with a live-region message. `generatorVersion` is populated from the stamped `__GENERATOR_VERSION__` (asserted in `test_policy_builder_emit.py`).
- [ ] Structurally valid drafts with unfinished predicates, missing action bodies/references, and invalid budgets survive Save/Open, reload, and undo without losing edits; diagnostics remain visible and YAML export stays blocked. Mismatched modes and malformed shapes fail import without replacing the current project.
- [ ] `projectId` and `activeMode` survive reload/Save/Open; unknown draft metadata survives serialization and history snapshots. New projects receive distinct IDs; presets and undo preserve identity.
- [ ] Disabled/unavailable browser storage leaves authoring and explicit project-file saving functional, with visible save-state feedback in a live region.
- [ ] Copy success/failure is visible, and export guidance includes a concrete destination, validation command, and run command (lifecycle: JSON-object positional `issue_id`; rubric: required `subject` positional input).
- [ ] Emitted YAML for every existing `.model.json` fixture is byte-identical; golden HTML fixture regenerated; `TestFeat2301UsabilityStructural` and theme-order test pass unchanged.
- [ ] Manual browser checklist (reload, mode switch, undo/redo, open corrupt file, storage disabled via private window) recorded in the Resolution.

## Success Metrics

Project round trips lose zero authored fields (node:test). Reload and mode changes preserve every draft in the manual checklist. Every supported mode has a save/open fixture.

## Scope Boundaries

Includes per-mode drafts, undo/redo, Save/Open project, copy/save feedback, and offline export guidance. Excludes layout reorganization, task presets, responsive CSS, execution summary, and skill metadata display (ENH-3491); terminal destinations, scoring instructions, and confidence-gate stamping (ENH-3492); arbitrary YAML round-trip editing, named scenario suites, real issue loading through a server, and run submission. Excludes automated browser/DOM interaction-test coverage for undo/redo and reload-persistence (Decision: Option B, see Proposed Solution § Decision Rationale) — these are verified via documented manual browser testing before closing; the pure-function contracts are still unit-tested in `node:test`. Correctness fixes (BUG-3486) touch the same editing-state code; land BUG-3486 first and coordinate shared model changes.

## Related Key Documentation

| Category | Document | Relevance |
|---|---|---|
| Architecture | docs/ARCHITECTURE.md | Project context stamping and artifact conventions |
| Reference | docs/reference/CLI.md | Saved artifact generation and usage |
| Guide | docs/guides/POLICY_ROUTER_GUIDE.md | Authoring flow and lifecycle semantics |

## Verification Notes

_Added by `/ll:verify-issues` — 2026-09-16:_

Verdict at time of check: **PROPOSAL_UNSOUND** (dependency backlinks below were corrected
in the same pass; the proposal gap is not — it needs an author decision, not a mechanical
fix, so it remains an outstanding action item).

- Graph: provider=`codegraph` freshness=`fresh` (not needed — no anchor relocation or
  negative claim arose; all citations resolved by direct read).
- All ~50 `path:line` citations in this issue (template/core.mjs event handlers, serialize
  functions, terminal-state emission, `cmd_policy_builder`, `ConfidenceGateConfig`,
  `context_seed.py:68`, docs sections, test names) were checked directly against the current
  working tree and are accurate — no drift.
- `ll-verify-evidence --json`: `"ok": true`, 0 findings — no fabricated evidence spans.
- Decisions log: `ll-issues decisions list --type rule --enforcement required --active-only`
  returned no entries — no `DECISIONS_VIOLATION`.
- **PROPOSAL_UNSOUND finding**: the Wiring Phase (added by `/ll:wire-issue`) already flags
  "Establish (or explicitly scope out in Scope Boundaries) an automated browser/DOM
  interaction test harness for the reload-persistence, undo/redo, and keyboard-operability
  Acceptance Criteria — none exists in this codebase today." Neither the Proposed Solution
  nor `## Scope Boundaries` resolves this: Scope Boundaries lists inclusions/exclusions but
  never mentions a test harness, and Implementation Step 5 ("Exercise offline persistence,
  round trips, and browser workflows") does not name a tool or approach. As written, three
  Acceptance Criteria items depend on automated interaction tests with no precedent in this
  repo (confirmed repo-wide: no Playwright/Selenium/jsdom harness exists) and no chosen
  path to build one:
  - "undo/redo restores rules, fields, actions, and transitions in **automated interaction
    tests**"
  - "**keyboard-accessible controls**" (implies automated a11y/interaction testing)
  - "375px and desktop **viewport tests** show no page-level horizontal overflow"

  **Resolved 2026-09-16:** `/ll:decide-issue` selected Option B; `decision_needed` reset to
  `false`. Pure-function contracts additionally get `node:test` coverage (see Proposed Solution).

- **Dependency backlinks (fixed in this pass)**: `BUG-3486` and `BUG-3489` are named in this
  issue's `depends_on:`, but neither had this issue in a `blocks:` frontmatter list (the
  convention used elsewhere in `.issues/`, e.g. `FEAT-2846`). Added
  `blocks: [ENH-3487]` to both `BUG-3486` and `BUG-3489`. (Review 2026-09-16: the BUG-3489
  dependency was dropped again — that bug is runtime policy-router behavior and nothing in
  this issue touches the runtime; backlink removed from BUG-3489.)

_Second `/ll:verify-issues` pass — 2026-09-16 (batch run with ENH-3491/ENH-3492):_

Verdict at time of check: **OUTDATED** (all corrections below applied in the same pass, so
the issue as it now reads is up to date — this section is a record of what was wrong and
fixed, not an outstanding action item).

- BUG-3486 (this issue's `depends_on`) landed real commits between the prior verification
  pass and this one — `22f4ff6ed`, `9f71f86f6` (BUG-3489, a coordinated same-code-area
  dependency of BUG-3486) — which inserted ~66-70 new lines into
  `policy_builder_core.mjs` and ~15 into `policy-router-builder.html.tmpl` ahead of every
  anchor this issue cites in those two files. All citations were re-verified against the
  current (now committed) code and corrected in place: `moveRule` (`308-319`→`374-384`,
  docstring `287-307`→`353-373`), `serializeLoopYaml` (`1049`→`1130`), `applyStateToForm`
  (`858-864`→`868-875`), `applyModeVisibility` (`837-853`→`847-862`), `updatePreview`
  (`809-816`→`808-824`, now wraps `serializeLoopYaml` in try/catch per the BUG-3489 fix),
  the mode-switch reseed comment (`868-872`/`868-878`→`878-882`/`878-887`), "Start blank"
  (`940-945`→`945-953`), localStorage read/write (`949`/`965-970`→`959`/`980`), clipboard
  copy (`923-926`→`933-936`), and the download-blob handler (`927-935`→`937-944`).
  No claim's *substance* changed — only line numbers.
- `docs/guides/POLICY_ROUTER_GUIDE.md` also shifted: a new "Failure Routing and Clean-Slate
  Scoring" subsection was inserted ahead of "Visual Builder (greenfield)", pushing every
  cited passage down by +60 lines (`198-242`→`258-303`, `244-356`→`304-416`,
  `234-235`→`294-295`, `240-242`→`300-302`); corrected in place.
- `ll-verify-evidence --json` on this issue: `"ok": true`, 0 findings.
- Decisions log query (`ll-issues decisions list --type rule --enforcement required
  --active-only`) returned no entries.
- Proposal-vs-code consequence check (B6): no new issue found — the persistence/undo/save-open
  design does not touch the BUG-3489 reserved-token guard or any other code path that changed.

_Third `/ll:verify-issues` pass — 2026-09-17 (batch run with ENH-3491/ENH-3492/FEAT-3488):_

Verdict at time of check: **OUTDATED** (corrections below applied in the same pass, so
the issue as it now reads is up to date — this section is a record of what was wrong and
fixed, not an outstanding action item).

- Commit `25e39fb1d` (BUG-3490, "resolve installed plugin content root for skill/command
  discovery", 2026-09-17T00:12:13) rewrote `policy_builder.py` between the prior verify
  pass and this one, shifting the two `cmd_policy_builder`/stamping citations this issue's
  Proposed Solution and Program Design cite. Corrected: the "stamps only theme, CSS vars,
  grammar, catalog, core JS" citation (`91-99`→`92-95`) and the `cmd_policy_builder`
  function-range citation (`56-107`→`61-112`). Substance unchanged: `cmd_policy_builder`
  still stamps exactly those five things and nothing else — the `__GENERATOR_VERSION__`
  plan (one `html.replace` next to the existing stamps) remains sound at the corrected
  lines.
- `policy_builder_core.mjs`/`policy-router-builder.html.tmpl` anchors are unaffected —
  `25e39fb1d` did not touch either file (confirmed via `git show --stat`); no commit has
  landed against them since the prior pass's post-`8faffee5a` correction.
- Dependency graph checked directly (BUG-3486 `blocks: [ENH-3487, ENH-3491, ENH-3492,
  FEAT-3488]` confirmed done; `blocks:`/`blocked_by:` backlinks across
  ENH-3487→ENH-3491→ENH-3492→FEAT-3488→FEAT-3498 all match in both directions): no
  DEP_ISSUES findings.
- `ll-verify-evidence --json`: `"ok": true`, 0 findings.
- Decisions log query (`ll-issues decisions list --type rule --enforcement required
  --active-only`) returned no entries.
- Graph: provider=`codegraph` freshness=`stale` (dirty working tree) — not relied on; all
  citations above were confirmed by direct read instead.
- Proposal-vs-code consequence check (B6): no new issue found — the `__GENERATOR_VERSION__`
  stamping plan is unaffected by BUG-3490's catalog-dedup rewrite.

## Status

**Open** | Created: 2026-09-16 | Priority: P3


## Session Log
- `/ll:confidence-check` - 2026-09-17T06:33:45 - `848ad701-11e3-43ba-8e5b-b86aa9978421.jsonl`
- `/ll:verify-issues` - 2026-09-17T06:27:20 - `9b9f3eca-ed5d-4fd7-a99d-217cb278def3.jsonl`
- manual review - 2026-09-17 - stale anchors corrected (guide `:300`/`:305`, `moveRule` `678-689`); code claims re-verified (issue-id-then-args ordering, `__version__` source, `evaluateModel` shape)
- manual review - 2026-09-17 - preserve unfinished drafts via structural validation; stable builder projectId and metadata persistence; preserve extension fields; corrected rubric input guidance; added regression criteria
- manual review - 2026-09-17 - `{model}` draft wrapper for FEAT-3488; whole-project history scope; shortcut/native-undo rule; `__GENERATOR_VERSION__` stamp (policy_builder.py now touched); corrupt-draft fallback; concrete `ll-loop run` input syntax; BUG-3486 dependency confirmed done
- `/ll:refine-issue` - 2026-09-17T04:04:46 - `b5a5ae18-560d-4cc6-8aa5-4bcda8471436.jsonl`
- `/ll:verify-issues` - 2026-09-17T02:36:58 - `ed6d999b-26a2-4d77-bbbf-604f7482188a.jsonl`
- `/ll:verify-issues` - 2026-09-17T01:18:50 - `716b78b0-d53f-401a-997f-791cc3ac58be.jsonl`
- manual review - 2026-09-16 - split into ENH-3491 (layout) and ENH-3492 (destinations); dropped BUG-3489 dependency; added node:test coverage requirement and project-envelope version policy
- `/ll:verify-issues` - 2026-09-16T22:52:47 - `56d2686a-f690-474a-8849-1b96c2edbd15.jsonl`
- `/ll:decide-issue` - 2026-09-16T22:44:17 - `764882af-9e40-4a2b-aaa1-9d51e82a0376.jsonl`
- `/ll:verify-issues` - 2026-09-16T22:36:05 - `df96ce10-e8c8-4600-a0c4-0eee757af56b.jsonl`
- `/ll:wire-issue` - 2026-09-16T21:29:53 - `0e35d235-ff66-480a-930e-d4d9ddd5eeb9.jsonl`
- `/ll:refine-issue` - 2026-09-16T21:07:15 - `7e302668-e6b7-4dea-830f-330bbfd02fc0.jsonl`
- `/ll:capture-issue` - 2026-09-16T20:55:13 - `64af6deb-56e5-4bde-9534-85751c1782ca.jsonl`
