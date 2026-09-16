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
- `/ll:capture-issue` - 2026-09-16T20:55:13 - `64af6deb-56e5-4bde-9534-85751c1782ca.jsonl`
