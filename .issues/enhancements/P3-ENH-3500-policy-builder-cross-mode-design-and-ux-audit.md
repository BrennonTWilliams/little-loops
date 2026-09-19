---
id: ENH-3500
type: ENH
title: Policy builder cross-mode design and UX audit
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-17'
captured_at: '2026-09-17T19:57:23Z'
blocked_by: []
relates_to: [EPIC-3493, ENH-3491, ENH-3506, FEAT-3488, FEAT-3498, FEAT-3504, FEAT-3505]
program_design_not_applicable: true
reconcile_attempted: true
---

# ENH-3500: Policy builder cross-mode design and UX audit

## Summary

Holistic visual/UX audit of the policy-router builder across all three authoring modes (`decision_table`, `rubric`, `issue_lifecycle`), plus the scenario-suite surface FEAT-3488 shipped and the connected-page surface FEAT-3505 shipped: information hierarchy, empty/error states, and cross-mode consistency. None of EPIC-3493's children own this — ENH-3491 (done) covered lifecycle-mode layout, responsive CSS, and keyboard/label basics only, scoped to that one mode. The design-token/theme parity half of the original scope was split into ENH-3506 on 2026-09-18 so it can run without waiting on FEAT-3505.

## Current Behavior

Each policy-builder authoring mode (decision-table, rubric, lifecycle) was designed, reviewed, and shipped independently, and no issue has ever checked them against each other. ENH-3491 audited lifecycle-mode layout, responsive CSS, and keyboard/label basics in isolation. There is no audit covering information hierarchy, empty/error states, or visual consistency across modes. (Design-token/theme correctness is tracked separately in ENH-3506.)

## Expected Behavior

With FEAT-3505 and FEAT-3488's scenario-suite surface both shipped, an audit pass reviews information hierarchy, empty/error states, and cross-mode visual consistency across every authoring mode, producing filed follow-up issues for any inconsistency found — this issue's own deliverable is the audit findings, not the fixes themselves.

## Motivation

The builder now spans three modes shipped independently (decision-table, rubric, lifecycle), the scenario-suite surface shipped by FEAT-3488, plus the connected-page surface shipped by FEAT-3505 — FEAT-3498 (done) was narrowed to the queue/loop run-request contracts, and its connected UI was split into FEAT-3504 (server routes) and FEAT-3505 (page controller and UI). Each mode was designed and reviewed in isolation; nothing has checked them together for a consistent look, or consistent empty/error handling. (Dark/light design-token correctness moved to ENH-3506, which now fixes the drift it found; this audit runs after it so dark theme is judged on real token values, not light-valued fallbacks.)

## Proposed Solution

Audit, not a code change in itself. With FEAT-3505 landed, walk every authoring mode side by side against a shared checklist — information hierarchy (heading levels, primary/secondary action placement), empty states (no rules/no decisions yet), error states (validation failure presentation), and terminology/iconography consistency. Run every checklist row in **both themes** and at **three widths**: 375px and 600px (at/below ENH-3491's single `@media (max-width: 600px)` breakpoint, tmpl line 77 — the only one in the template) and 1280px desktop. Add an **accessibility** row for the connected controls, which no issue owns (ENH-3491 covered keyboard/label basics for lifecycle mode only): live-region announcement of status transitions (`#live-status`, `role="status"`), focus placement after Review and Submit, keyboard reachability of issue selection, and how disabled-with-reason is exposed (`aria-disabled` + visible/`aria-describedby` reason vs. bare `disabled`). The checklist must cover FEAT-3505's connected controls (issue selection, review, submit, status) and its new states (unavailable-with-reason, rejected, outcome-unknown); FEAT-3505 establishes the "connected controls unavailable with a reason" convention, which has no prior in-repo precedent, so audit the other modes' disabled/unavailable states against it. Record every finding in a `## Audit Findings` table in this issue (surface, mode, theme/width, observed, expected, follow-up ID). File follow-ups via `ll-issues create` then `ll-issues link <ID> --relates-to ENH-3500`: **one issue per root cause**, grouping findings that share a fix (e.g. one empty-state pattern missing in all three modes is one issue), not one per table row.

FEAT-3505 introduced new design-token references and possibly hardcoded colors; check them here using ENH-3506's method (diff the rendered `:root`/`[data-theme=dark]` blocks against the active profile), since ENH-3506 covers only the pre-FEAT-3505 template. ENH-3506's template-ref parity pytest should already keep new refs resolving; this pass checks the visual result. **Scope bound**: the template carries ~66 hex/`rgba()` literals, most of them pre-FEAT-3505 and already ENH-3506's territory — check only literals on lines FEAT-3505 added (`git diff 1d899c076^ 1d899c076 -- scripts/little_loops/templates/policy-router-builder.html.tmpl`), not the whole file.

No emitted-YAML or runtime-behavior change is in scope for this issue (see Out of Scope) — only presentation.

### Audit Method

The audit is driven by an on-demand Playwright probe, not by reading source and not by a pytest gate. Follow the existing pattern in `.loops/probes/` (`enh-3506-theme-probes.mjs`, `enh-3507-served-page-probes.mjs`, `feat-3488-browser-probes.mjs`, each with a `.loops/verify-*.yaml` loop that ends in `skipped-no-playwright` when Playwright is absent):

- Add `.loops/probes/enh-3500-audit-probes.mjs` + a new `verify-enh-3500-audit` loop YAML (in `.loops/`, beside the existing `verify-*` loops). For each mode (`decision_table`, `rubric`, `issue_lifecycle`, switched via `#mode-switch`) × theme (`data-theme` light/dark) × width (375 / 600 / 1280), capture a full-page screenshot and a JSON dump of: the heading/legend outline, every `disabled` control (with any visible or `aria-describedby` reason), all `aria-*`/`role` attributes, empty-state text per list, and status/error class usage.
- Write artifacts under the run dir; findings are judged from the screenshots + dumps and recorded in `## Audit Findings`.
- If Playwright is unavailable, the audit is **not** done from source alone — record it as blocked rather than closing.

**Reaching the connected states** (connected page = `ll-artifact serve --policy-builder`, lifecycle mode):

| State | How to reproduce |
|---|---|
| unavailable-with-reason (`#conn-unavailable`) | open the offline `ll-artifact policy-builder` render (reason: not served); also the served page in a non-lifecycle mode (reason: "Switch to the issue lifecycle mode…") |
| `rejected` | `page.route("**/run-request", …)` fulfilling the POST with a 4xx error body (pattern: `enh-3507-served-page-probes.mjs`) |
| `outcome_unknown` | `page.route` aborting the POST (`route.abort()`), or killing the server mid-submit; also check the `#conn-again-btn` / disabled-Submit presentation it produces |
| `accepted` (+ warnings / `warningsUnavailable`) | stubbed 200 response with and without `warnings` |

### Baseline Conventions (seed for the checklist)

Observed in the template on 2026-09-19; the audit confirms or refutes each as an inconsistency:

- **Empty states**: only scenarios have one ("No scenarios yet.", `#scenario-summary`); rules, dimensions, and outcomes lists render nothing when empty.
- **Disabled controls**: ~10 bare `.disabled = …` sites (undo/redo, delete-outcome when in use, rule up/down, value input for boolean ops, copy/download on error, expected-rule-index, connected Review/Submit/Refresh) and **zero** `aria-disabled`/`aria-describedby`. Only the connected surface shows a reason (`#conn-unavailable`); e.g. delete-outcome disabled-when-in-use shows none.
- **Hierarchy**: one `h1`, fieldset `<legend>`s for the left column, and two `h2`s ("Result", "Submit to host") with inline `font-size:1rem` styles. "Try it" is used as the legend of two different fieldsets (lines 258, 264).
- **Status/error presentation**: `is-error`/`is-warning`/`is-success` classes (connected status, lines 171-173, 2275) coexist with a separate bare `"error"` class used at ~6 sites (1302, 1657, 1796, 1807, 2211, 2244).
- **Live regions**: two — `#import-diagnostics` and `#live-status` (both `role="status"`, `aria-live="polite"`); check which messages go to which and whether errors should be assertive.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-17 — based on codebase analysis (token-specific findings moved to ENH-3506):_

- Convention for filing follow-up issues from an audit varies across existing audit skills: `commands/audit-architecture.md`/`skills/audit-docs/SKILL.md` hand-`Write` a fixed issue-file template (one issue per finding row); the current post-FEAT-2947 convention (`skills/capture-issue/SKILL.md:266-275`) instead calls `ll-issues create` directly. ENH-3491 (the prior lifecycle-only audit this issue's Scope §2 extends) filed no follow-up issues at all — its findings were implemented directly in that same issue, so it is not a precedent for this issue's "file one follow-up per finding" mechanism.
- No per-mode template fragment files exist. `scripts/little_loops/templates/policy-router-builder.html.tmpl` (one shared HTML template) plus `scripts/little_loops/templates/policy_builder_core.mjs` (one shared, DOM-free JS module) implement all three authoring modes (`decision_table`, `rubric`, `issue_lifecycle`); mode switching happens client-side via `<select id="mode-switch">`, so one `ll-artifact policy-builder` render covers every mode.
- No headless-browser/DOM rendering harness exists in the pytest suite; browser verification of the rendered page is an on-demand Playwright probe loop, not a pytest gate.

## Integration Map

### Files to Audit
- `scripts/little_loops/templates/policy-router-builder.html.tmpl` — the single shared HTML template; primary audit target for hierarchy, empty/error states, and the DOM binding FEAT-3505 added
- `scripts/little_loops/templates/policy_builder_core.mjs` — shared DOM-free module for all modes; source of validation/error message text and, since FEAT-3505, the submission controller's state names
- No source files change for the audit itself; any inconsistency found is filed as a follow-up issue rather than fixed inline here

### Files to Create
- `.loops/probes/enh-3500-audit-probes.mjs` and a new `verify-enh-3500-audit` loop YAML (in `.loops/`, beside the existing `verify-*` loops) — on-demand Playwright audit probe (see Audit Method); dev-only, never a pytest gate

### Similar Patterns
- ENH-3491 (done) — prior lifecycle-mode-only layout/responsive/keyboard audit; this issue extends that pattern across modes rather than re-litigating it
- ENH-3506 — sibling token/theme parity audit split from this issue

### Tests
- N/A — audit-only; follow-up issues own any regression coverage

### Documentation
- N/A — this issue produces an audit report and follow-up issues, not doc changes

## Implementation Steps

1. Render the builder offline (`ll-artifact policy-builder`) and connected (`ll-artifact serve --policy-builder`, FEAT-3504).
2. Build and run the audit probe (see Audit Method): every mode × theme × width, plus the four connected states via stubbed routes.
3. Walk every authoring mode and the connected controls against the shared checklist (information hierarchy, empty states, error states, terminology/iconography), using ENH-3491's shipped lifecycle-mode output as the baseline FEAT-3505's unavailable-with-reason convention as the reference for disabled states, and Baseline Conventions as the seed list.
4. Fill the `## Audit Findings` table; file one follow-up per root cause (`relates_to: [ENH-3500]`). Close this issue once findings are filed — or, if the audit finds nothing, close with the table stating "no findings" per checklist row so the clean result is on record.

## Audit Findings

_Filled during implementation. One row per observation; rows sharing a root cause share a follow-up ID._

| # | Surface | Mode | Theme / width | Observed | Expected | Follow-up |
|---|---------|------|---------------|----------|----------|-----------|

## Impact

- **Priority**: P3 - polish/consistency work, not blocking any shipped functionality
- **Effort**: Medium - FEAT-3505 has landed, so the full set of surfaces is now known
- **Risk**: Low - audit-only, no source changes in this issue itself; any risk lives in the follow-up issues it files
- **Breaking Change**: No

## Scope Boundaries

- **In scope**: holistic hierarchy/empty-state/error-state/cross-mode consistency audit across every authoring mode and FEAT-3505's connected controls, now that FEAT-3505 has landed, so the audit sees every surface once
- **Out of scope**: see Out of Scope below

## Out of Scope

- Re-litigating ENH-3491's lifecycle-mode layout, presets, or execution-summary decisions (already shipped).
- Any change to emitted YAML or runtime behavior — this is presentation/UX only.
- Being made a child of EPIC-3493 — kept separate so it doesn't stall that epic's closure.
- Design-token/theme parity of the already-shipped template — split to ENH-3506.

## Dependencies

No open blockers. FEAT-3505 (done 2026-09-19) was the last one; the half that could run early was split into ENH-3506, also done, so the dark-theme walk sees corrected tokens.

Updated 2026-09-18: the original blockers FEAT-3498 and FEAT-3488 are both done, but FEAT-3498 was narrowed to the queue/loop run-request contracts and its connected UI was split into FEAT-3504 (server routes, no UI) and FEAT-3505 (page controller and UI). FEAT-3505 was the surface Scope §2 needed to see; both are now done.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Verification Notes

_Added by `/ll:verify-issues` — 2026-09-19_

Verdict at time of check: **NEEDS_UPDATE** (the stale `blocked_by` and prose were corrected in a follow-up edit the same day; this section is a record of what was wrong).

- **Blocker resolved**: `blocked_by: [FEAT-3505]` is stale — FEAT-3505 is `status: done` (completed 2026-09-19T06:19:41Z). ENH-3506, FEAT-3504, FEAT-3488, FEAT-3498, ENH-3491 are also done. The issue is unblocked; wording such as "Wait for FEAT-3505 to land", "still landing via FEAT-3505", and "unscored while blocked" no longer holds.
- **Surface now exists**: `policy-router-builder.html.tmpl` already has `#live-status` (`role="status"`, `aria-live="polite"`, line 323), `#conn-unavailable` (unavailable-with-reason, line 333), and `rejected`/`accepted`/warning delivery states (~2255-2282), so the connected-controls checklist rows have a real target.
- **Unchanged and accurate**: template/module file paths, `#mode-switch` select (line 181), single shared template + `policy_builder_core.mjs`, ENH-3491 scope description, ENH-3506 split.
- **Not verified**: `aria-disabled`/`aria-describedby` usage — no matches in the template, which is an audit-time finding rather than an issue-accuracy problem.
- Checks run: evidence quotes (`ll-verify-evidence`: clean), decisions rules (none active/required), proposal-vs-code (no conflict; audit-only). Graph: provider=`codegraph` freshness=`fresh` (not needed for any verdict).

Remaining: none from this pass — `blocked_by` cleared and stale prose refreshed on 2026-09-19. Run `/ll:confidence-check` before implementation.

## Status

**Open** | Created: 2026-09-17 | Priority: P3


## Session Log
- `/ll:verify-issues` - 2026-09-19T15:15:38 - `7ee9c824-60e2-4758-b5c9-b9c5467b1552.jsonl`
- `/ll:wire-issue` - 2026-09-17T20:36:27 - `09ec3a0b-aab2-4bb6-8cae-e9097652c9fa.jsonl`
- `/ll:reconcile-issue` - 2026-09-17T20:19:51 - `6b0d1a07-f3de-4f1f-94c3-b6d1cbb4cbbf.jsonl`
- `/ll:refine-issue` - 2026-09-17T20:12:08 - `661efed9-f2d1-44cc-aba2-5fe939c77557.jsonl`
- `/ll:format-issue` - 2026-09-17T20:03:20 - `7d2e95ae-d922-4199-a105-d094d1bfae74.jsonl`
- `/ll:capture-issue` - 2026-09-17T19:57:56 - `1bf1a777-2967-438b-a3cf-45a0eb0f285a.jsonl`
