---
id: ENH-3500
type: ENH
title: Policy builder cross-mode design and UX audit
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-17'
captured_at: '2026-09-17T19:57:23Z'
blocked_by: [FEAT-3498, FEAT-3488]
relates_to: [EPIC-3493, ENH-3491]
program_design_not_applicable: true
---

# ENH-3500: Policy builder cross-mode design and UX audit

## Summary

Holistic visual/UX audit of the policy-router builder across all authoring modes (lifecycle, decision-table, and whatever FEAT-3498's connected-execution surface adds): design-token/theme parity (dark/light), information hierarchy, empty/error states, and cross-mode consistency. None of EPIC-3493's 8 children own this — ENH-3491 (done) covered lifecycle-mode layout, responsive CSS, and keyboard/label basics only, scoped to that one mode.

## Current Behavior

Each policy-builder authoring mode (lifecycle, decision-table) was designed, reviewed, and shipped independently, and no issue has ever checked them against each other. ENH-3491 audited lifecycle-mode layout, responsive CSS, and keyboard/label basics in isolation. Design-token and dark/light usage is unverified against real rendering: `test_policy_builder_renders_byte_identically_to_golden_fixture` only catches byte-level drift from a golden fixture, and `scripts/little_loops/worktree_utils.py:687-713` copies `.ll/design-tokens` into epic-verify worktrees as a stopgap so that test doesn't false-fail on a missing token file — it does not verify the templates consume tokens correctly. There is no audit covering information hierarchy, empty/error states, or visual consistency across modes.

## Expected Behavior

Design-token and dark/light theme usage in the already-shipped lifecycle and decision-table modes is confirmed correct (not just passing the golden-fixture byte-match), with any drift filed as follow-up issues. Once FEAT-3498 and FEAT-3488 land, a second audit pass reviews information hierarchy, empty/error states, and cross-mode visual consistency across every authoring mode, producing filed follow-up issues for any inconsistency found — this issue's own deliverable is the audit findings, not the fixes themselves.

## Motivation

The builder now spans multiple modes shipped independently (lifecycle, decision-table, plus connected-execution and scenario-suite surfaces still landing via FEAT-3498/FEAT-3488). Each mode was designed and reviewed in isolation; nothing has checked them together for a consistent look, consistent empty/error handling, or correct dark/light design-token usage. There's already a concrete signal that token usage is fragile: ENH-3491's notes flagged that `test_policy_builder_renders_byte_identically_to_golden_fixture` false-fails on degraded design tokens, and `scripts/little_loops/worktree_utils.py:687-713` copies `.ll/design-tokens` into epic-verify worktrees specifically as a stopgap for that. That's a workaround for a symptom, not a check on the actual token usage in the builder templates.

## Proposed Solution

Two-phase audit (see Scope), not a code change in itself:

1. **Token/theme audit (now)**: for each design token referenced by `scripts/little_loops/templates/policy_builder_core.mjs` and its per-mode templates, render lifecycle mode and decision-table mode under both `dark` and `light` themes (`ll-config.json` → `design_tokens.active_theme`) and diff the rendered CSS custom-property values against `.ll/design-tokens/<theme>.json`. Flag any hardcoded color/spacing value that bypasses a token, and any token referenced in one mode's template but not the other where the two should match. File one follow-up ENH per confirmed drift.
2. **Holistic UX audit (after FEAT-3498/FEAT-3488 land)**: walk every authoring mode side by side against a shared checklist — information hierarchy (heading levels, primary/secondary action placement), empty states (no rules/no decisions yet), error states (validation failure presentation), and terminology/iconography consistency. File one follow-up issue per inconsistency found, tagged `relates_to: [ENH-3500]`.

No emitted-YAML or runtime-behavior change is in scope for this issue (see Out of Scope) — only presentation.

## Integration Map

### Files to Modify
- `scripts/little_loops/templates/policy_builder_core.mjs` — shared builder shell; primary target for token/theme audit
- Per-mode template fragments loaded by `policy_builder_core.mjs` (lifecycle, decision-table; plus whatever FEAT-3498/FEAT-3488 add) — audited individually and cross-checked for consistency
- No source files are expected to change for the audit itself; any drift found is filed as a follow-up ENH rather than fixed inline here

### Dependent Files (Callers/Importers)
- `scripts/little_loops/worktree_utils.py:687-713` — copies `.ll/design-tokens` into epic-verify worktrees as a stopgap for the golden-fixture test's token dependency; this issue determines whether that stopgap is still needed once token usage is verified correct
- `.ll/design-tokens/*.json` — the token source of truth the audit diffs rendered output against

### Similar Patterns
- ENH-3491 (done) — prior lifecycle-mode-only layout/responsive/keyboard audit; this issue's Scope §2 explicitly extends that pattern across modes rather than re-litigating it

### Tests
- `scripts/tests/test_enh3035_artifact_template_kit.py::test_policy_builder_renders_byte_identically_to_golden_fixture` — the existing golden-fixture guard this audit's findings should either confirm covers real token usage or supplement
- `scripts/tests/test_policy_builder_corpus.py`, `scripts/tests/test_policy_builder_emit.py` — existing coverage for builder-emitted output; no changes expected unless the audit finds drift requiring a new regression test

### Documentation
- N/A — this issue produces an audit report and follow-up issues, not doc changes

### Configuration
- N/A or list config files

## Implementation Steps

1. Enumerate the design tokens `policy_builder_core.mjs` and its per-mode templates reference; confirm each resolves through `.ll/design-tokens/<theme>.json` rather than a hardcoded value.
2. Render lifecycle mode and decision-table mode under both `dark` and `light` themes; diff rendered output against expected token values.
3. File one follow-up ENH per confirmed token/theme drift, with the specific file/selector and expected vs. actual value.
4. Once FEAT-3498 and FEAT-3488 land, repeat the process for information hierarchy, empty/error states, and cross-mode consistency, using ENH-3491's shipped lifecycle-mode output as the baseline.
5. File one follow-up issue per inconsistency found; close this issue once both audit passes are complete and findings are filed.

## Impact

- **Priority**: P3 - polish/consistency work, not blocking any shipped functionality; the token-drift stopgap in `worktree_utils.py` already masks the symptom the token half of this audit targets
- **Effort**: Medium - Scope §1 (token/theme audit) is boundable now; Scope §2 (holistic audit) can't be sized until FEAT-3498/FEAT-3488 land and define the full set of modes
- **Risk**: Low - audit-only, no source changes in this issue itself; any risk lives in the follow-up issues it files
- **Breaking Change**: No

## Scope

Two halves with different timing — do not block the whole issue on the later one:

1. **Token/theme parity (can start now, independent of FEAT-3498/FEAT-3488)**: audit current design-token and dark/light usage in the already-shipped lifecycle and decision-table modes against ENH-3491's shipped output. Confirm the builder templates consume tokens correctly rather than relying on the golden-fixture stopgap masking drift.
2. **Holistic hierarchy / empty-state / error-state / cross-mode consistency review**: wait until FEAT-3498 (connected execution) and FEAT-3488 (scenario suites) land, so the audit sees every mode once instead of auditing a surface that's about to change again.

## Scope Boundaries

- **In scope**: token/theme parity audit of shipped modes (now); holistic hierarchy/empty-state/error-state/cross-mode audit once FEAT-3498/FEAT-3488 land (see Scope above for the two-phase breakdown)
- **Out of scope**: see Out of Scope below

## Out of Scope

- Re-litigating ENH-3491's lifecycle-mode layout, presets, or execution-summary decisions (already shipped).
- Any change to emitted YAML or runtime behavior — this is presentation/UX only.
- Being made a child of EPIC-3493 — kept separate so it doesn't stall that epic's closure.

## Dependencies

`blocked_by: [FEAT-3498, FEAT-3488]` applies to the holistic half only (Scope §2). The token/theme parity sub-item (Scope §1) can be picked up early or in parallel without waiting on either.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-17 | Priority: P3


## Session Log
- `/ll:format-issue` - 2026-09-17T20:03:20 - `7d2e95ae-d922-4199-a105-d094d1bfae74.jsonl`
- `/ll:capture-issue` - 2026-09-17T19:57:56 - `1bf1a777-2967-438b-a3cf-45a0eb0f285a.jsonl`
