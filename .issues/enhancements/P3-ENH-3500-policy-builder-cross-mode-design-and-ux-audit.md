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
relates_to:
- EPIC-3493
- ENH-3491
- ENH-3506
- FEAT-3488
- FEAT-3498
- FEAT-3504
- FEAT-3505
program_design_not_applicable: true
reconcile_attempted: true
confidence_score: 100
outcome_confidence: 82
score_complexity: 21
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 25
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

Audit, not a code change in itself. With FEAT-3505 landed, walk every authoring mode side by side against a shared checklist — information hierarchy (heading levels, primary/secondary action placement), empty states (no rules/no decisions yet), error states (validation failure presentation), and terminology/iconography consistency. Run every applicable fixture/checklist combination in **both themes** and at **three primary widths**: 375px and 600px (at/below ENH-3491's single `@media (max-width: 600px)` breakpoint) and 1280px desktop. Add targeted **601px** comparisons against 600px for each mode's populated and long-content layouts and the connected panel, in both themes, to check the other side of the breakpoint.

Add an **accessibility** row for the connected controls, which no issue owns (ENH-3491 covered keyboard/label basics for lifecycle mode only): status-transition announcement support, focus placement after Review and Submit, keyboard reachability of issue selection and recovery actions, and whether users can understand why a control is unavailable. Assess native `disabled`, `aria-disabled`, visible reasons, and `aria-describedby` in context; absence of ARIA alone is not a finding or a requirement to replace native disabled semantics. The checklist must cover FEAT-3505's connected controls (issue selection, review, submit, status) and its unavailable, rejected, and outcome-unknown states. Use its visible unavailable-with-reason convention as a comparison point, not an assumed gold standard.

Record every finding in `## Audit Findings`, including severity, user impact, and evidence. Search existing issues before filing follow-ups. Reuse an issue that already owns the root cause; otherwise use `ll-issues create`, then `ll-issues link <ID> --relates-to ENH-3500`. File **one issue per root cause**, grouping observations that share a fix (e.g. one empty-state pattern missing in all three modes is one issue), not one per table row. Each follow-up must include reproduction steps, expected presentation, and a link to the relevant audit evidence.

FEAT-3505 introduced new design-token references and possibly hardcoded colors; check them here using ENH-3506's method (diff the rendered `:root`/`[data-theme=dark]` blocks against the active profile), since ENH-3506 covers only the pre-FEAT-3505 template. ENH-3506's template-ref parity pytest should already keep new refs resolving; this pass checks the visual result. **Scope bound**: the template carries roughly 70 hex/`rgba()` literals (a loose grep counts 74), most of them pre-FEAT-3505 and already ENH-3506's territory — check only literals on lines FEAT-3505 added (`git diff 1d899c076^ 1d899c076 -- scripts/little_loops/templates/policy-router-builder.html.tmpl`), not the whole file.

No emitted-YAML or runtime-behavior change is in scope for this issue (see Out of Scope) — only presentation.

### Audit Method

The audit is driven by an on-demand Playwright probe, not by reading source and not by a pytest gate. Follow the existing pattern in `.loops/probes/` (`enh-3506-theme-probes.mjs`, `enh-3507-served-page-probes.mjs`, `feat-3488-browser-probes.mjs`, each with a `.loops/verify-*.yaml` loop that ends in `skipped-no-playwright` when Playwright is absent):

- Add `.loops/probes/enh-3500-audit-probes.mjs` + a new `verify-enh-3500-audit` loop YAML (in `.loops/`, beside the existing `verify-*` loops). Expand the named fixtures below into a case manifest before running: fixture × applicable mode (`decision_table`, `rubric`, `issue_lifecycle`, switched via `#mode-switch`) × theme (light/dark) × primary width (375 / 600 / 1280), plus the targeted 601px cases. Record the offline/served surface explicitly; connected fixtures use the served surface, while shared authoring fixtures use the offline render with a served populated-layout comparison per mode.
- Use a fresh browser context/storage for every independent case. Preserve state only within a case that intentionally tests a transition. Seed fixtures through supported UI/import paths, assert the intended state is reached, and then capture evidence; a default populated page does not count as an empty/error fixture. Stub connected requests and matching readbacks before the action so polling cannot replace the intended state during capture. Reuse the existing probe helpers' approach without running their real-queue mutation cases.
- For each case, capture a full-page screenshot and JSON containing the heading/legend outline, disabled controls and their associated reasons, `aria-*`/`role` attributes, empty-state text per list, status/error class usage, and overflow/clipping measurements. Include long names, issue titles, validation messages, and result text in the long-content fixtures; inspect whether content wraps and actions remain reachable.
- Write screenshots, JSON, the case manifest, and interaction traces under `${context.run_dir}/`. Record the source revision, active token profile, browser/version, and viewport dimensions with the artifacts. Link evidence from `## Audit Coverage` and `## Audit Findings` using stable case IDs and run-relative filenames.
- A successful probe means evidence collection completed, not that the UX passed review. Judge every case against the checklist, record its disposition, and reconcile the coverage ledger with the manifest. Missing evidence or an unreached required state blocks audit completion; observed UX defects become findings and do not themselves prevent completing this audit.
- If Playwright is unavailable, the audit is **not** done from source alone — record it as blocked rather than closing.

### Required Fixtures and Interaction Checks

| Fixture family | Required presentations |
|---|---|
| Authoring, every applicable mode | Populated baseline; separately empty rules, dimensions, outcomes, and scenarios; invalid model with Result diagnostics and disabled export actions; long-content layout. Explicitly mark lists that do not exist in a mode as not applicable. |
| Scenario suite, every applicable mode | Empty; populated/not yet run; pass, fail, error, and unasserted results; needs-review after an edit that stales a rule-index expectation (not applicable to rubric rule-index expectations); coverage summary and explanation presentation. |
| Connected issue selection | Loading; empty issue list; failed issue-list request with Reload recovery; selected issue. |
| Connected review | No review yet; preparing snapshot; refused review (e.g. invalid policy); ready; draft edited since review, including the distinction between the reviewed snapshot and current draft. |
| Connected delivery and status | Offline panel absence; served unavailable reason; rejected; outcome unknown with recovery controls; accepted with no warnings, with warnings, and with warnings unavailable; representative `awaiting_approval`, `done`, and `failed` readbacks, including result details. |

For the connected controls, execute explicit Tab/Shift+Tab and keyboard activation sequences for issue selection, Review, Submit, and each visible recovery action. Record the focused element before and after actions, the focus order, and visible focus screenshots. For asynchronous transitions, record which live-region elements change and their resulting text, including transitions that update only `#conn-status` or `#conn-notices`. Attribute snapshots alone do not verify keyboard behavior or announcements. Label this evidence as DOM announcement support; claim actual screen-reader announcements only if a manual assistive-technology check was performed and its browser/reader and observations are recorded. Manual screen-reader verification is optional and must be reported as not performed when absent.

**Reaching the connected states** (connected page = `ll-artifact serve --policy-builder`, lifecycle mode unless stated otherwise):

| State | How to reproduce |
|---|---|
| Offline panel absence | Open the offline `ll-artifact policy-builder` render and verify `#connected-panel` is hidden. `renderConnected` hides the whole panel when `CONNECTED_CONTEXT` is absent; offline rendering cannot demonstrate a visible unavailable reason. |
| unavailable-with-reason (`#conn-unavailable`) | Open the served page in a non-lifecycle mode with fresh storage (reason: "Switch to the issue lifecycle mode…"). |
| `rejected` | Intercept the POST with `page.route("**/run-request", …)` and fulfill a JSON 400 response with `{ "error": { "code": "validation_failed", "message": "Audit validation failure" } }`. The controller requires a recognized rejection code; a generic 4xx body can leave the outcome unknown. |
| `outcome_unknown` | Abort the POST with `route.abort()`; capture `#conn-again-btn`, disabled Submit, and Refresh status. In a separate recovery case, stub the readback as request-not-found to expose Retry identical request. |
| `accepted`, no warnings / with warnings | Fulfill JSON 200 with a string `queueId`, `created: true`, and `warnings: []` or a nonempty warning array. Omitting `warnings` for a newly created request also yields an empty warning list. |
| `accepted`, `warningsUnavailable` | Fulfill JSON 200 with a string `queueId` and `created: false`, omitting `warnings`. This represents an existing request whose original warnings are unavailable. |
| Accepted status/readback variants | Stub `**/run-request/*` using the existing `stubReadback`/`rbBody` pattern in `enh-3507-served-page-probes.mjs`; echo the submitted issue/revision bindings and vary `status` between `awaiting_approval`, `done`, and `failed`, with result text for terminal cases. |

The response contracts above are grounded in `classifyPost` and the submission view's `warningsUnavailable` calculation in `policy_builder_core.mjs`; use these contracts when building fixtures rather than guessing from HTTP status alone.

### Baseline Conventions (seed for the checklist)

Observed in the template on 2026-09-19; the audit confirms or refutes each as an inconsistency:

- **Empty states**: only scenarios have one ("No scenarios yet.", `#scenario-summary`); rules, dimensions, and outcomes lists render nothing when empty.
- **Disabled controls**: ~13 bare `.disabled = …` sites (undo/redo, delete-outcome when in use, rule up/down, value input for boolean ops, copy/download on error, expected-rule-index, connected Review/Submit/Refresh) and **zero** `aria-disabled`/`aria-describedby`. Only the connected surface shows a reason (`#conn-unavailable`); e.g. delete-outcome disabled-when-in-use shows none.
- **Hierarchy**: one `h1`, fieldset `<legend>`s for the left column, and two `h2`s ("Result", "Submit to host") with inline `font-size:1rem` styles. "Try it" is used as the legend of two different fieldsets (lines 258, 264).
- **Status/error presentation**: two class vocabularies coexist — `is-error`/`is-warning`/`is-success` (connected status only, CSS lines 171-173, applied at 2275) and `msg-error`/`msg-warn`/`msg-ok` (Result diagnostics and scenario results, CSS lines 161-163, applied at e.g. 1302, 1309, 1317, 1320, 1657). No bare `"error"` class exists; lines 1796/1807/2211/2244 only test `severity === "error"`/`status === "error"` and emit no class. Audit whether the split is a real inconsistency.
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
- On-demand browser probe and coverage-manifest reconciliation verify evidence collection; interactive review supplies the UX verdict. No new pytest gate; follow-up issues own regression coverage for fixes.

### Documentation
- N/A — this issue produces an audit report and follow-up issues, not doc changes

## Implementation Steps

1. Render the builder offline (`ll-artifact policy-builder`) and connected (`ll-artifact serve --policy-builder`, FEAT-3504).
2. Build the case manifest and audit probe from Required Fixtures and Interaction Checks. Run the applicable mode × theme × primary-width matrix, targeted 600/601px comparisons, and deterministic connected-state fixtures with isolated storage.
3. Review the screenshots, DOM dumps, and keyboard/focus/live-region traces against the shared checklist. Use ENH-3491's shipped lifecycle-mode output and FEAT-3505's unavailable-with-reason presentation as comparison points, and Baseline Conventions as the seed list.
4. Fill `## Audit Coverage` and `## Audit Findings`, assigning severity and user impact. Search existing issues; link an existing owner or create one follow-up per root cause (`relates_to: [ENH-3500]`).
5. Reconcile the coverage ledger with the manifest and apply the Acceptance Criteria before closure. Record clean cases explicitly; do not infer review completion from a successful probe exit.

## Acceptance Criteria

- [ ] Every required fixture/checklist combination has a stable case ID, explicit applicability, and a coverage-ledger entry for both themes and all primary widths; targeted 601px comparisons cover each mode's populated/long-content layout and the connected panel.
- [ ] Every applicable case reaches its intended state and has linked screenshots and JSON evidence under the run dir. Evidence includes run metadata and fresh-storage isolation between independent cases.
- [ ] Connected-state recipes distinguish offline panel absence, visible served unavailability, recognized rejection, unknown outcome/recovery, accepted warnings variants, and pending/success/failure readbacks.
- [ ] Keyboard activation, focus transitions, and live-region text changes are exercised and recorded. DOM announcement support and any manual screen-reader verification are clearly distinguished.
- [ ] Every planned case has a reviewed disposition: pass, finding, blocked, or not applicable with a reason. No required case remains blocked or missing evidence when this issue closes.
- [ ] Every finding records severity, user impact, expected presentation, reproduction/evidence, and an existing or newly filed follow-up. Observations sharing a root cause share one follow-up; existing issues are checked before creating duplicates.
- [ ] Probe collection success and UX review completion are reported separately. Clean checklist results remain recorded even when other cases have findings; findings need to be filed, not fixed, to close this audit.

## Audit Coverage

_Filled during implementation from the case manifest. One row per case/checklist item; do not omit clean cases. Disposition is pass, finding, blocked, or not applicable (with a reason). Evidence paths are relative to the recorded run dir. This ledger records audit completion independently of probe exit status._

| Case ID | Checklist item | Surface / mode | Fixture / state | Theme / width | Evidence | Disposition / reason | Finding IDs |
|---------|----------------|----------------|-----------------|---------------|----------|----------------------|-------------|

## Audit Findings

_Filled during implementation. One row per observation; rows sharing a root cause share a follow-up ID. Severity uses P0–P5 with user-impact rationale. Case IDs link back to the coverage ledger and its reproduction/evidence artifacts._

| # | Case IDs / evidence | Surface / mode | Theme / width | Observed | Expected | Severity / user impact | Follow-up |
|---|---------------------|----------------|---------------|----------|----------|------------------------|-----------|

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

_Re-verified 2026-09-19 (`/ll:verify-issues --auto`, after the audit-methodology expansion)_

Verdict at time of check: **NEEDS_UPDATE** (corrections below applied in the same pass, so the issue as it now reads is up to date — this section is a record of what was wrong and fixed, not an outstanding action item)

- **Baseline Conventions, status/error classes — inaccurate, fixed**: the "bare `"error"` class at ~6 sites (1302, 1657, 1796, 1807, 2211, 2244)" claim was false. Those sites use `msg-error`/`msg-warn`/`msg-ok` (1302, 1657) or only test severity/status strings (1796, 1807, 2211, 2244). The real inconsistency is two vocabularies (`is-*` vs `msg-*`); rewritten accordingly.
- **Counts refreshed**: `.disabled =` sites are 13 (was "~10"); `aria-disabled`/`aria-describedby` remain 0 (accurate). Hex/`rgba()` literals ~70 (was "~66"; grep is loose).
- **Confirmed accurate**: probe files `enh-3506-theme-probes.mjs`, `enh-3507-served-page-probes.mjs`, `feat-3488-browser-probes.mjs` and their `verify-*.yaml` loops exist; `enh-3500-*` artifacts are correctly not yet created; commit `1d899c076` exists and touches the template; "Try it" legends at 258/264; h1 179, h2 at 311/332 with inline `font-size:1rem`; live regions at 283/323; `#mode-switch` 181, `#conn-unavailable` 333, `#conn-again-btn` 345, `#connected-panel` 331; `classifyPost` and `warningsUnavailable` in `policy_builder_core.mjs`; `stubReadback`/`rbBody` in the 3507 probe; only "No scenarios yet." empty state.
- Checks run: evidence quotes (`ll-verify-evidence`: clean), decisions rules (none active/required), proposal-vs-code (audit-only, no conflict). Graph: provider=`codegraph` freshness=`fresh` (not needed for any verdict).

## Status

**Open** | Created: 2026-09-17 | Priority: P3


## Session Log
- `/ll:confidence-check` - 2026-09-19T19:05:18 - `4be66b2a-8fb6-4f6b-b868-a23d5155ff4b.jsonl`
- `/ll:verify-issues` - 2026-09-19T19:03:47 - `2f3560fe-f5c4-46f3-b647-99fef1b0cd77.jsonl`
- `/ll:confidence-check` - 2026-09-19T18:45:23 - `3835f63e-f729-4db6-8d3d-bc4b71a041a3.jsonl`
- `/ll:verify-issues` - 2026-09-19T15:15:38 - `7ee9c824-60e2-4758-b5c9-b9c5467b1552.jsonl`
- `/ll:wire-issue` - 2026-09-17T20:36:27 - `09ec3a0b-aab2-4bb6-8cae-e9097652c9fa.jsonl`
- `/ll:reconcile-issue` - 2026-09-17T20:19:51 - `6b0d1a07-f3de-4f1f-94c3-b6d1cbb4cbbf.jsonl`
- `/ll:refine-issue` - 2026-09-17T20:12:08 - `661efed9-f2d1-44cc-aba2-5fe939c77557.jsonl`
- `/ll:format-issue` - 2026-09-17T20:03:20 - `7d2e95ae-d922-4199-a105-d094d1bfae74.jsonl`
- `/ll:capture-issue` - 2026-09-17T19:57:56 - `1bf1a777-2967-438b-a3cf-45a0eb0f285a.jsonl`
