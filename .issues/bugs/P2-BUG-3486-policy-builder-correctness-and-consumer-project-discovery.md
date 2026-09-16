---
id: BUG-3486
type: BUG
title: Policy builder correctness and consumer project discovery
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-16'
captured_at: '2026-09-16T20:54:20Z'
labels:
- policy-builder
- captured
relates_to:
- FEAT-3474
---

# BUG-3486: Policy builder correctness and consumer project discovery

## Summary

Fix policy-builder correctness and consumer-project discovery across Decision Table, Rubric, and Issue Lifecycle modes. Preview, validation, generated YAML, and runtime routing must agree, and installed little-loops skills must be discoverable outside this source checkout.

Captured from the 2026-09-16 whole-builder review following FEAT-3474. The focused Python/Node gate suite passed 126 tests, but direct core/runtime probes reproduced the defects below. Browser policy prevented opening local HTML; UI findings are source-derived, not a completed visual browser test.

## Current Behavior

- Decision-table Try it evaluates uncompiled boolean operators. In the seeded example, quality 99 and has-citations false previews done while compiled rules select light-repair.
- Both previews recover the winning row by its target name. Lifecycle confidence 90 matches rule 3 but highlights rule 2, which also targets implement; fallback matches lack explicit feedback.
- JavaScript accepts nonnumeric ordered comparisons and malformed targets rejected by Python. Model validation misses duplicate/reserved outcome names, missing references, unsupported mode/type combinations, incomplete actions, invalid step budgets, and inverted rubric thresholds. A user outcome named score produces duplicate YAML state keys. The shared completion-name helper only checks done before selecting finished.
- Changing a rule's field does not reconcile its stored operator with the new field type. Invalid string edits remain visible while the model retains the previous value. Adding an incomplete lifecycle rule can throw during preview compilation.
- Frontmatter Try it misreads inline comments and quoted commas in lists; the derived priority_rank handling can also disagree with Python. These yield different routing inputs.
- The LLM policy_parse_scores fragment retains dimension files omitted on subsequent passes. A previous citation score of 100 survives a second pass without citations. The lifecycle scorer already clears stale files.
- Decision-table dispatch errors route to the first outcome, which may represent success.
- Catalog discovery only scans project-root skills and commands directories, leaving ordinary consuming projects with empty skill menus despite an installed plugin.

## Expected Behavior

Every supported input has identical browser/runtime parsing and evaluation semantics; unsupported inputs produce explicit diagnostics. Invalid or incomplete models cannot be exported, and editing never silently substitutes stale values. Rule identity and fallback matches are reported accurately. Fresh scoring cannot use previous-pass evidence. Consumer projects resolve the installed plugin catalog plus supported project overrides.

## Motivation

Users cannot trust policy decisions when the preview disagrees with execution or reports healthy output for malformed models. These are existing behavior defects and must be resolved before richer scenario testing or execution handoff relies on them.

## Proposed Solution

Add a pure model-validation pipeline shared by preview/export and a compiled evaluation result that preserves winning rule identity and per-condition results. Reconcile field/operator changes and represent invalid draft inputs explicitly. Match the Python parser/encoder for the supported frontmatter subset; reject unsupported syntax rather than guessing. Validate/generated-name allocation must prevent all state collisions. Clear stale scores and route evaluation failures to a failure terminal. Resolve installed plugin content using the shared collector and plugin-root resolution, with deterministic deduplication and project override precedence.

## Integration Map

- Files to modify: scripts/little_loops/templates/policy_builder_core.mjs; scripts/little_loops/templates/policy-router-builder.html.tmpl; scripts/little_loops/cli/artifact/policy_builder.py; scripts/little_loops/loops/lib/policy-router.yaml.
- Dependent contracts: scripts/little_loops/fsm/policy_rules.py and scripts/little_loops/fsm/frontmatter_scores.py; generated fixtures in scripts/tests/fixtures/policy_builder/.
- Similar patterns: frontmatter_scores clean-slate behavior; shared collect_entries and plugin-root discovery.
- Tests: scripts/tests/test_policy_builder_emit.py, scripts/tests/test_policy_builder_corpus.py, scripts/tests/test_policy_builder_node_gate.py, scripts/tests/test_frontmatter_scores.py, scripts/tests/js/policy_validator.test.mjs; add browser-editing coverage under the local pytest gate.
- Configuration: preserve existing project configuration and offline artifact behavior.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-16 — based on codebase analysis:_

Fixture/corpus files backing the differential Python/JS parity convention already in force (`scripts/tests/fixtures/policy_builder/`):
- `conformance_corpus.json` — `evaluate_cases`/`shadow_cases`, pinning JS `evaluateRules`/`detectShadows` against Python `evaluate_rules`/`_detect_shadows`, consumed by `scripts/tests/js/policy_validator.test.mjs` and `scripts/tests/test_policy_builder_corpus.py`.
- `frontmatter_encoding_corpus.json` — pins JS `encodeFrontmatterScores`/`parseFrontmatterBlock` against Python `encode_frontmatter_scores` (`fsm/frontmatter_scores.py`).
- `sample-*.model.json` + `sample-*.yaml` — golden model-to-YAML pairs (decision-table, rubric, issue-lifecycle) asserted byte-for-byte equal from both languages.
- `golden_policy_router_builder.html` — structural/markup golden for the generated page.

Conventions in force (codebase-pattern-finder, evidence cited per rule):
- **Differential parity, not shared validation**: this codebase's established pattern for keeping Python and JS in sync is corpus-pinned parity tests (above), not a single shared validator called from both a preview and an export path — no example of the latter shape exists anywhere in the repo (searched `^def validate` plus every `validate_fsm`/`_detect_shadows`/`renderMessages` call site, no path filter). `frontmatter_scores.py:10-14` and `policy_builder_core.mjs:1-7` both carry explicit "mirrors" docstrings stating the two implementations are pinned against the same conformance corpus so they can't silently drift — the proposed `validateBuilderModel` would be new in kind, not an extension of an existing shared-validator shape.
- **FSM failure routing**: the established convention across ~80 loop YAML files (e.g. `general-task.yaml:1326-1328`, `rn-build.yaml:1394-1403`) is a dedicated failure terminal (typically named `failed`), driven by `on_error:`/`on_max_steps:` and marked via `schema.py`'s `FAILURE_TERMINAL_NAMES` frozenset (implicit `failure: true` for legacy names `failed`/`error`/`aborted`/`finalize_aborted`) or an explicit `failure: true` field for other names. `_serializeIssueLifecycle()` (mjs 974-1041) already follows this convention (explicit `failed:` terminal, `on_error: failed`); `_serializeDecisionTable()` (mjs 800-804) does not — it has no dedicated failure terminal at all.
- **Reserved/generated-name collision avoidance**: the only *dynamic* used-name-set-and-fallback example in the codebase is `_doneStateName()` itself (mjs 733-739) — the file this issue already touches. Elsewhere the codebase uses *fixed* reserved tokens instead (`_RESERVED = {"aggregate"}` in `fsm/validation/reachability.py:170`; `FAILURE_TERMINAL_NAMES` in `schema.py:26-35`), a different shape (static exemption vs. dynamic collision detection) — no second dynamic-collision example exists to generalize from.
- **JS test harness**: `scripts/tests/js/policy_validator.test.mjs` is the only `.test.mjs` file in the repo; it uses Node's built-in `node:test` + `node:assert/strict` with zero npm dependencies, gated into the local suite via `scripts/tests/test_policy_builder_node_gate.py` (skips gracefully below Node 22 or when absent).

## Program Design

### Types

Proposed MatchResult carries ruleIndex, target, isFallback, and conditionResults; Diagnostic carries severity, field path, and message.

### Signatures

Proposed new JS core contracts:
- `validateBuilderModel(model) -> DiagnosticList`
- `evaluateModel(model, scores) -> MatchResult`

Keep evaluateRules' existing target-returning API compatible.

### Call Path

`updatePreview` -> `buildModel` -> `validateBuilderModel` -> `serializeLoopYaml`.

`cmd_policy_builder` -> `_load_skill_catalog` -> `collect_entries`.

Use installed-plugin resolution behind scripts/little_loops/cli/action.py::_find_plugin_root when collecting the catalog.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-16 — based on codebase analysis:_

Current (pre-fix) signatures, confirmed by direct code reading:

- `evaluateRules(rules, scores) -> string | null` (`policy_builder_core.mjs:239-245`) — returns only the matched rule's `target` string today; no rule index or identity is returned. This is the gap the proposed `MatchResult` type closes.
- `parseRuleTable(text, grammar?) -> Array<{predicates, target, isCatchall}>` (`policy_builder_core.mjs:544-575`) — `grammar` is optional, falling back to `DEFAULT_PRED_RE`.
- `_load_skill_catalog(project_root: Path) -> list[dict[str, str]]` (`cli/artifact/policy_builder.py:21-53`) — flat `{"name", "description"}` list from one root only.
- `_find_plugin_root() -> Path` (`cli/action.py:179-182`, thin wrapper over `skill_expander.py:25-35`) — no arguments; checks `CLAUDE_PLUGIN_ROOT` env var, else falls back to the package's installed location.
- `validateBuilderModel` has no definition anywhere in the codebase today (repo-wide search, no hits outside this issue file) — confirms it is genuinely new code, not a rename/refactor of an existing function.

Corrected current call path (the issue's proposed `updatePreview -> buildModel -> validateBuilderModel -> serializeLoopYaml` describes target-state wiring; `validateBuilderModel` is not yet implemented, so today's actual path is different): `updatePreview()` (tmpl 809-816) calls `buildModel()` (tmpl 248-268), then independently and in fixed but unordered-relative-to-each-other sequence calls `serializeLoopYaml(model)` (writing to the YAML preview unconditionally), `computeSummary(model)`, `renderMessages(model)` (tmpl 780-807 — today's only in-page validation-like surface, combining the exported `detectShadows()` from `policy_builder_core.mjs` with ad hoc inline checks that live only in the `.html.tmpl` file and are therefore untested by the Node gate), and `updateTryIt()`. None of these gate each other today — YAML serialization is never blocked on what `renderMessages` finds.

Reuse anchor for the policy_parse_scores fix: `_clean_slate(run_dir: Path)` in `fsm/frontmatter_scores.py:158-169`, called from `main()` at `frontmatter_scores.py:200` before writing new score files — the existing, already-working clear-stale-files mechanism referenced in Current Behavior.

Catalog-merge precedent search (capability search, not name search): searched every catalog-collection call site in `scripts/little_loops/**/*.py` for a merge of an installed-plugin root with a project-root override plus dedup (`collect_entries` in `cli/help.py:212`, `_load_skills` in `cli/action.py:197-214`, `assemble_tool_catalog` in `tool_catalog.py:152-162`, `_load_skill_catalog` itself, plus `doctor.py`/`logs.py`/`adapt.py`/`verify_skill_prose.py`/`doc_counts.py`/`generate_skill_descriptions.py`/`adapt_skills_for_codex.py`). Every existing collector resolves exactly one root and globs `commands/*.md` + `skills/*/SKILL.md`; none merges two roots, applies override precedence, or deduplicates by name. The "shared collector" `_find_plugin_root()` resolves a single plugin root only — it has no project-root-merge behavior to reuse as-is; that merge/precedence/dedup logic has no existing convention in this codebase to follow and will be new.

## Implementation Steps

1. Capture each reproduced mismatch in targeted regressions, including consumer fixtures and two-pass score parsing.
2. Unify model validation, compiled evaluation, parser parity, and generated state allocation.
3. Repair editing-state synchronization, fallback feedback, export gating, and dispatch failure handling.
4. Resolve installed catalog content and override precedence.
5. Update fixtures and user-facing behavior descriptions; run focused gates and the required local suite.

## Impact

- Priority: P2 — routing decisions and generated loops can be wrong despite a healthy preview.
- Effort: Large — coordinated browser/core/runtime/discovery fixes with differential tests.
- Risk: Medium — preserve valid existing rules while tightening malformed-input behavior.
- Breaking change: No intended change to valid rule semantics; invalid exports become blocked.

## Steps to Reproduce

1. Import seedExample, evaluateRules, parseRuleTable, and _serializeRulesText from scripts/little_loops/templates/policy_builder_core.mjs in Node. Evaluate the default seed with quality 99 and has-citations 0 using raw rules and compiled rules; compare done versus light-repair.
2. Evaluate the lifecycle seed with status open and confidence_score 90. Compare the actual matching rule index with the template's first matching target-name lookup.
3. Compare JavaScript/Python parsing of confidence_score:>=high -> implement and quality:>=90 -> bad/target; only Python rejects both.
4. Compare encoders on confidence_score with an inline comment, a flow-list item containing a quoted comma, and priority high accompanied by priority_rank 1.
5. Run the policy_parse_scores fragment twice in one temporary run directory, omitting a dimension on pass two; inspect the retained score file.
6. Call _load_skill_catalog with a temporary consumer root lacking root-level skills/commands; observe an empty catalog.

## Root Cause

The template's updateTryIt and updateFrontmatterTryIt use different evaluation paths and infer row identity from a nonunique target. Core parseRuleTable does not enforce the full Python parser contract. renderMessages is a small hint collector rather than model validation. Generated state names share a namespace with user outcomes. The LLM score parser lacks clean-slate handling. _load_skill_catalog does not resolve the installed plugin root.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-16 — based on codebase analysis:_

Per-defect file:line anchors, confirmed by direct code reading:

- **(a) Decision-table Try-it uses uncompiled boolean ops** — `policy-router-builder.html.tmpl` `updateTryIt()` (~line 730) calls `evaluateRules(model.rules, scores)` on the **raw** rules, whose boolean predicates still carry literal ops `"==true"`/`"==false"`. In `policy_builder_core.mjs` `evalPredicate()` (lines 193-231), `"==true"`/`"==false"` are absent from `ORDERED_OPS`, fall to the string-compare branch, and because `op` is literally `"==true"` (not `"=="`) the code takes the `!=` arm — `==true` predicates evaluate as `!=`. Contrast: `updateFrontmatterTryIt()` (tmpl lines 754-778) compiles first via `parseRuleTable(_serializeRulesText(model))` before evaluating — the raw-rules path is not used there.
- **(b) Both previews recover winner by target name** — `evaluateRules()` (mjs lines 232-245) returns `string | null` only — no rule index/identity. Both `updateTryIt()` (tmpl line 733) and `updateFrontmatterTryIt()` (tmpl line 775) recover the row via `model.rules.findIndex(r => r.target === winnerTarget)`, which returns the *first* rule with that target, not the rule actually matched. Both also silently no-op (no fallback indicator) when `winnerTarget` doesn't match any `model.rules` entry (catch-all fired).
- **(c) Validation gaps** — Python `_parse_predicate()` (`fsm/policy_rules.py:72-95`) rejects non-numeric values for ordered ops via `float(value)`; JS `parsePredicate()` (mjs lines 525-535) never performs this check. Python's `_TARGET_PATTERN = re.compile(r"^[\w][\w\-]*$")` (`policy_rules.py:37`, enforced 140-144) rejects malformed targets; JS `parseRuleTable()` (mjs 544-575) only checks for an empty string (557-559). `$("add-outcome").onclick` (tmpl 906-913) has no duplicate/reserved-name check, unlike `$("add-dim").onclick` (tmpl 886-905) which does check duplicates (898). `_doneStateName()` (mjs 733-739) returns `"finished"` if `"done"` is used, but never checks whether `"finished"` is *also* already used. `$("f-maxsteps").oninput` (tmpl 881) only guards falsy values (`Number(...) || 1`), so negative step budgets pass through.
- **(d) Editing reconciliation** — `dimSel.onchange` in `renderRules()` (tmpl line 604) sets `p.dim` but never resets/validates `p.op` against the new dimension's type. The string-value `oninput` handler in `renderRules()` (tmpl 609-619) returns early on invalid input without resetting `valInput.value`, leaving the DOM and model showing different values. `updateFrontmatterTryIt()`'s call to `parseRuleTable(_serializeRulesText(model))` (tmpl ~758) has no try/catch (unlike the `parseFrontmatterBlock` call just above it, tmpl 762-767); a freshly-added predicate has `value: ""` (tmpl line 919 / 637), which fails `_PRED_PATTERN` in `parsePredicate()` (mjs 525-535) and throws uncaught.
- **(e) Frontmatter Try-it parser divergence** — `parseFrontmatterBlock()` (mjs 1094-1148) has no `#`-comment stripping, unlike Python's real `yaml.load`-based `parse_frontmatter()` (`frontmatter.py`). The flow-list branch (mjs 1133-1136) splits on every comma via `.split(",")`, breaking on a quoted element containing a literal comma. `encodeFrontmatterScores()` (mjs 1198-1209) derives `priority_rank` when a dimension is *named* `"priority"`; Python's `encode_frontmatter_scores()` (`frontmatter_scores.py:106-115`) derives it when a dimension's `raw_key == "priority_rank"` — different trigger keys that only coincide because `BUILTIN_FRONTMATTER_DIMENSIONS` (mjs 85-95) always ships both together.
- **(f) Stale score files** — the reusable clean-slate pattern is `_clean_slate(run_dir: Path)` in `fsm/frontmatter_scores.py:158-169` (globs and unlinks `rubric-dim-*.txt` and `rubric-aggregate.txt`), called from `main()` (`frontmatter_scores.py:200`) before writing new scores. The `policy_parse_scores` fragment (`loops/lib/policy-router.yaml`, lines 84-116) has no equivalent — it only writes files for `DIMENSION:` lines found in the current pass and never deletes pre-existing `rubric-dim-*.txt` files, which `policy_table_dispatch` (same file, 197-208) then reads indiscriminately via `os.listdir(run_dir)`.
- **(g) Dispatch errors route to first outcome** — `_serializeDecisionTable()` (mjs 800-804): `errorState = tokens[0] || fallbackState` — `tokens[0]` is whichever outcome the first authored rule targets, with no dedicated failure terminal ever emitted for decision-table mode. Contrast: `_serializeIssueLifecycle()` (mjs 974-1041) emits an explicit `failed:` terminal (line 1037) and routes `_error: failed` unconditionally (line 1022).
- **(h) Catalog discovery** — confirmed: `_load_skill_catalog()` (`cli/artifact/policy_builder.py:21-53`) globs only `project_root/"skills"` and `project_root/"commands"`, and does not call `_find_plugin_root()` (`cli/action.py:179-182` → `skill_expander.py:25-35`) anywhere in that file — the only caller of `_load_skill_catalog` is `cmd_policy_builder()` (line 79).

## Acceptance Criteria

- [ ] Python/JS differential cases agree for boolean rules, missing fields, supported frontmatter comments/lists/quoting, derived priority, malformed targets, and nonnumeric ordered comparisons.
- [ ] Regression tests assert actual winning row identity for repeated targets and explicit fallback matches.
- [ ] Invalid/incomplete models show diagnostics and disable export; field changes, field removal, and rejected draft edits cannot silently export previous or incompatible values.
- [ ] Duplicate/reserved state names and completion-name collisions cannot produce duplicate YAML keys or broken transitions; valid models in all three modes pass runtime validation.
- [ ] Two-pass scorer tests prove omitted fields cannot retain prior scores; dispatch/scoring failures cannot report successful completion.
- [ ] Consumer-root fixtures with installed plugin content produce known lifecycle skills without requiring root skills/commands directories; override/deduplication behavior is tested.
- [ ] Existing offline generation, theme behavior, and valid model semantics remain covered by the local Python/Node suite.

## Scope Boundaries

Includes correctness, validation feedback, and installed catalog discovery. Excludes saved projects, UI reorganization, named scenario suites, and connected execution. These are separately captured follow-up workstreams.

## Related Key Documentation

| Category | Document | Relevance |
|---|---|---|
| Architecture | docs/ARCHITECTURE.md | Project-enriched artifacts and shared generator architecture |
| Reference | docs/reference/CLI.md | Policy-builder generation and validation contract |
| Guide | docs/guides/POLICY_ROUTER_GUIDE.md | Rule grammar, preview semantics, and lifecycle mode |

## Status

**Open** | Created: 2026-09-16 | Priority: P2


## Session Log
- `/ll:refine-issue` - 2026-09-16T21:10:28 - `23738f99-b471-4d7b-a1d6-399ffa424bef.jsonl`
- `/ll:capture-issue` - 2026-09-16T20:55:13 - `64af6deb-56e5-4bde-9534-85751c1782ca.jsonl`
