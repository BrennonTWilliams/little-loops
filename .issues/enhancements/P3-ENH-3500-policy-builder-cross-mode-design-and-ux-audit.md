---
id: ENH-3500
type: ENH
title: Policy builder cross-mode design and UX audit
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-17'
captured_at: '2026-09-17T19:57:23Z'
blocked_by: [FEAT-3505]
relates_to: [EPIC-3493, ENH-3491, ENH-3506, FEAT-3488, FEAT-3498, FEAT-3504]
program_design_not_applicable: true
reconcile_attempted: true
---

# ENH-3500: Policy builder cross-mode design and UX audit

## Summary

Holistic visual/UX audit of the policy-router builder across all three authoring modes (`decision_table`, `rubric`, `issue_lifecycle`), plus the scenario-suite surface FEAT-3488 shipped and the connected-page surface FEAT-3505 adds: information hierarchy, empty/error states, and cross-mode consistency. None of EPIC-3493's children own this — ENH-3491 (done) covered lifecycle-mode layout, responsive CSS, and keyboard/label basics only, scoped to that one mode. The design-token/theme parity half of the original scope was split into ENH-3506 on 2026-09-18 so it can run without waiting on FEAT-3505.

## Current Behavior

Each policy-builder authoring mode (decision-table, rubric, lifecycle) was designed, reviewed, and shipped independently, and no issue has ever checked them against each other. ENH-3491 audited lifecycle-mode layout, responsive CSS, and keyboard/label basics in isolation. There is no audit covering information hierarchy, empty/error states, or visual consistency across modes. (Design-token/theme correctness is tracked separately in ENH-3506.)

## Expected Behavior

Once FEAT-3505 lands (FEAT-3488's scenario-suite surface has already shipped), an audit pass reviews information hierarchy, empty/error states, and cross-mode visual consistency across every authoring mode, producing filed follow-up issues for any inconsistency found — this issue's own deliverable is the audit findings, not the fixes themselves.

## Motivation

The builder now spans three modes shipped independently (decision-table, rubric, lifecycle), the scenario-suite surface shipped by FEAT-3488, plus the connected-page surface still landing via FEAT-3505 — FEAT-3498 (done) was narrowed to the queue/loop run-request contracts, and its connected UI was split into FEAT-3504 (server routes) and FEAT-3505 (page controller and UI)). Each mode was designed and reviewed in isolation; nothing has checked them together for a consistent look, or consistent empty/error handling. (Dark/light design-token correctness moved to ENH-3506, which now fixes the drift it found; this audit runs after it so dark theme is judged on real token values, not light-valued fallbacks.)

## Proposed Solution

Audit, not a code change in itself. After FEAT-3505 lands, walk every authoring mode side by side against a shared checklist — information hierarchy (heading levels, primary/secondary action placement), empty states (no rules/no decisions yet), error states (validation failure presentation), and terminology/iconography consistency. Run every checklist row in **both themes** and at **narrow width** (ENH-3491's responsive breakpoints). Add an **accessibility** row for the connected controls, which no issue owns (ENH-3491 covered keyboard/label basics for lifecycle mode only): live-region announcement of status transitions (`#live-status`, `role="status"`), focus placement after Review and Submit, keyboard reachability of issue selection, and how disabled-with-reason is exposed (`aria-disabled` + visible/`aria-describedby` reason vs. bare `disabled`). The checklist must cover FEAT-3505's connected controls (issue selection, review, submit, status) and its new states (unavailable-with-reason, rejected, outcome-unknown); FEAT-3505 establishes the "connected controls unavailable with a reason" convention, which has no prior in-repo precedent, so audit the other modes' disabled/unavailable states against it. Record every finding in a `## Audit Findings` table in this issue (surface, mode, theme/width, observed, expected, follow-up ID). File follow-ups via `ll-issues create` then `ll-issues link <ID> --relates-to ENH-3500`: **one issue per root cause**, grouping findings that share a fix (e.g. one empty-state pattern missing in all three modes is one issue), not one per table row.

If FEAT-3505 introduces new design-token references or hardcoded colors, check them here using ENH-3506's method (diff the rendered `:root`/`[data-theme=dark]` blocks against the active profile), since ENH-3506 covers only the pre-FEAT-3505 template. ENH-3506's template-ref parity pytest should already keep new refs resolving; this pass checks the visual result.

No emitted-YAML or runtime-behavior change is in scope for this issue (see Out of Scope) — only presentation.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-17 — based on codebase analysis (token-specific findings moved to ENH-3506):_

- Convention for filing follow-up issues from an audit varies across existing audit skills: `commands/audit-architecture.md`/`skills/audit-docs/SKILL.md` hand-`Write` a fixed issue-file template (one issue per finding row); the current post-FEAT-2947 convention (`skills/capture-issue/SKILL.md:266-275`) instead calls `ll-issues create` directly. ENH-3491 (the prior lifecycle-only audit this issue's Scope §2 extends) filed no follow-up issues at all — its findings were implemented directly in that same issue, so it is not a precedent for this issue's "file one follow-up per finding" mechanism.
- No per-mode template fragment files exist. `scripts/little_loops/templates/policy-router-builder.html.tmpl` (one shared HTML template) plus `scripts/little_loops/templates/policy_builder_core.mjs` (one shared, DOM-free JS module) implement all three authoring modes (`decision_table`, `rubric`, `issue_lifecycle`); mode switching happens client-side via `<select id="mode-switch">`, so one `ll-artifact policy-builder` render covers every mode.
- No headless-browser/DOM rendering harness exists in the pytest suite; browser verification of the rendered page is an on-demand Playwright probe loop, not a pytest gate.

## Integration Map

### Files to Modify
- `scripts/little_loops/templates/policy-router-builder.html.tmpl` — the single shared HTML template; primary audit target for hierarchy, empty/error states, and the DOM binding FEAT-3505 adds
- `scripts/little_loops/templates/policy_builder_core.mjs` — shared DOM-free module for all modes; source of validation/error message text and, after FEAT-3505, the submission controller's state names
- No source files are expected to change for the audit itself; any inconsistency found is filed as a follow-up issue rather than fixed inline here

### Similar Patterns
- ENH-3491 (done) — prior lifecycle-mode-only layout/responsive/keyboard audit; this issue extends that pattern across modes rather than re-litigating it
- ENH-3506 — sibling token/theme parity audit split from this issue

### Tests
- N/A — audit-only; follow-up issues own any regression coverage

### Documentation
- N/A — this issue produces an audit report and follow-up issues, not doc changes

## Implementation Steps

1. Wait for FEAT-3505 to land; render the builder offline (`ll-artifact policy-builder`) and connected (via the `ll-artifact serve` policy-builder flag FEAT-3504 adds).
2. Walk every authoring mode and the connected controls against the shared checklist (information hierarchy, empty states, error states, terminology/iconography), using ENH-3491's shipped lifecycle-mode output as the baseline and FEAT-3505's unavailable-with-reason convention as the reference for disabled states.
3. Fill the `## Audit Findings` table; file one follow-up per root cause (`relates_to: [ENH-3500]`); close this issue once findings are filed.
4. Run `/ll:confidence-check` once FEAT-3505 lands and the surface set is fixed (unscored while blocked).

## Impact

- **Priority**: P3 - polish/consistency work, not blocking any shipped functionality
- **Effort**: Medium - can't be sized until FEAT-3505 lands and defines the full set of surfaces
- **Risk**: Low - audit-only, no source changes in this issue itself; any risk lives in the follow-up issues it files
- **Breaking Change**: No

## Scope Boundaries

- **In scope**: holistic hierarchy/empty-state/error-state/cross-mode consistency audit across every authoring mode and FEAT-3505's connected controls, once FEAT-3505 lands — waiting so the audit sees every surface once instead of auditing one that's about to change
- **Out of scope**: see Out of Scope below

## Out of Scope

- Re-litigating ENH-3491's lifecycle-mode layout, presets, or execution-summary decisions (already shipped).
- Any change to emitted YAML or runtime behavior — this is presentation/UX only.
- Being made a child of EPIC-3493 — kept separate so it doesn't stall that epic's closure.
- Design-token/theme parity of the already-shipped template — split to ENH-3506.

## Dependencies

`blocked_by: [FEAT-3505]` — the whole issue now waits on it; the half that could run early was split into ENH-3506. ENH-3506 is covered transitively (it blocks FEAT-3505 as of 2026-09-19), so the dark-theme walk sees corrected tokens.

Updated 2026-09-18: the original blockers FEAT-3498 and FEAT-3488 are both done, but FEAT-3498 was narrowed to the queue/loop run-request contracts and its connected UI was split into FEAT-3504 (server routes, no UI) and FEAT-3505 (page controller and UI). FEAT-3505 is the surface Scope §2 needs to see; FEAT-3504 is covered transitively (it blocks FEAT-3505).

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-17 | Priority: P3


## Session Log
- `/ll:wire-issue` - 2026-09-17T20:36:27 - `09ec3a0b-aab2-4bb6-8cae-e9097652c9fa.jsonl`
- `/ll:reconcile-issue` - 2026-09-17T20:19:51 - `6b0d1a07-f3de-4f1f-94c3-b6d1cbb4cbbf.jsonl`
- `/ll:refine-issue` - 2026-09-17T20:12:08 - `661efed9-f2d1-44cc-aba2-5fe939c77557.jsonl`
- `/ll:format-issue` - 2026-09-17T20:03:20 - `7d2e95ae-d922-4199-a105-d094d1bfae74.jsonl`
- `/ll:capture-issue` - 2026-09-17T19:57:56 - `1bf1a777-2967-438b-a3cf-45a0eb0f285a.jsonl`
