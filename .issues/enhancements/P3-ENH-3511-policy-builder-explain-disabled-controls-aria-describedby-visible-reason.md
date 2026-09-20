---
id: ENH-3511
type: ENH
title: 'Policy builder: explain disabled controls (aria-describedby / visible reason)'
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-19'
captured_at: '2026-09-19T20:00:57Z'
relates_to:
- ENH-3500
blocked_by:
- ENH-3513
- BUG-3512
parent: EPIC-3493
epic: EPIC-3493
confidence_score: 100
outcome_confidence: 56
score_complexity: 10
score_test_coverage: 10
score_ambiguity: 18
score_change_surface: 18
size: Large
---

# ENH-3511: Policy builder: explain disabled controls (aria-describedby / visible reason)

## Summary

Found by ENH-3500 audit. ~13 bare .disabled sites and zero aria-disabled/aria-describedby; only #conn-unavailable gives a reason. Disabled Submit before review, delete-outcome-in-use, rule up/down at ends, and Copy/Download on invalid models give no reason (title only on some). Repro: any mode with invalid model -> Copy/Download disabled with no explanation next to them; connected panel before review -> Submit disabled. Expected: visible/associated reason. Native disabled semantics may stay. Evidence: auth-invalid-model-*, conn-issue-selected-*, conn-review-none-*.

## Current Behavior

About 13 sites set `.disabled` with no `aria-disabled`/`aria-describedby` anywhere; only `#conn-unavailable` explains a disabled state. Submit before review, delete-outcome-in-use, rule up/down at list ends, and Copy/Download on an invalid model give no reason (a `title` on some only).

## Expected Behavior

Each in-scope disabled control has a **visible** reason next to it, also associated via `aria-describedby`. Native `disabled` semantics stay. Because natively disabled buttons are not focusable, `aria-describedby` on them is only reached through a screen reader's browse/virtual cursor — the visible text is the deliverable; the attribute is supplementary and is not sufficient on its own.

## Motivation

This enhancement would:
- Users, and assistive-tech users especially, cannot tell why an action is unavailable or how to enable it.
- ENH-3500 audit evidence: `auth-invalid-model-*`, `conn-issue-selected-*`, `conn-review-none-*`.

## Scope Boundaries

- **In scope**: visible reason + `aria-describedby` for Copy/Download (invalid model), connected Submit **and Review** (shared reason element), and `#conn-issue` (`aria-describedby="conn-unavailable"` only — the visible reason already exists); delete-outcome-in-use (keeps its dynamic `title`, gains a per-row visible reason); rule up/down at list ends get a **dynamic `title` only** ("Already first" / "Already last") — no per-row hint elements, which would need unique IDs and add clutter for a self-evident state.
- **Out of scope**: replacing native `disabled` with `aria-disabled`; undo/redo (:517-518); rule `valInput` for `==true`/`==false` (:1077) and scenario `idxInput` when `expectedFallback` (:1542) — self-evident from the adjacent control; `#conn-refresh-btn` while busy (:2256) — transient; announcing validation diagnostics (ENH-3513).

## Integration Map

### Files to Modify
- `scripts/little_loops/templates/policy-router-builder.html.tmpl`

### Tests
- Template/probe tests for the policy builder (locate via `grep -rl policy-router-builder scripts/tests/`)

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-19 — based on codebase analysis:_

- Named functions exist in `policy-router-builder.html.tmpl`: `updatePreview` (:1778), `renderConnected` (:2217), `renderOutcomes` (:776), `renderRules` (:1029). None of `aria-describedby`, `aria-disabled`, `aria-invalid`, `role="alert"` appears anywhere in the template; only `aria-label` and two `role="status" aria-live="polite"` regions exist.
- Complete `.disabled` inventory (14 assignments; issue says ~13): undo/redo (:517-518, out of scope); `delOc` in `renderOutcomes` (:789, `inUse = state.fallback === oc.name || state.rules.some(r => r.target === oc.name)`, already sets a dynamic `title` at :790-792 — the only disabled control with any reason); rule value input `valInput` for `==true`/`==false` ops (:1077); rule up/down at ends (:1154 `i === 0`, :1159 `i === state.rules.length-1`, titles are static and do not explain the disabled state); scenario `idxInput` when `expectedFallback` (:1542); Copy/Download (:1797-1798, `hasError`); connected `#conn-issue` (:2241), review (:2250), submit (:2251), refresh (:2256); static `disabled` on `#conn-submit-btn` markup (:344).
- Submit's disabled condition (:2251) is a disjunction: `!av.ok || rv.status !== "ready" || st.busy || outcome_unknown` — a single static reason cannot describe it; a reason must be derived from whichever clause holds. Review (:2250) has no title/reason at all.
- The one existing reason element: `#conn-unavailable` (:333), `<p class="hint" hidden>` toggled in `renderConnected` (:2220-2221); it carries no role/aria. It is the only precedent for "visible reason next to a disabled connected control".
- The issue's scope lists `valInput`, `idxInput`, and the `#conn-issue`/review/refresh sites as neither in nor out of scope; the Scope Boundaries only name Copy/Download, connected Submit, delete-outcome-in-use, and rule up/down. Those unlisted sites (:1077, :1542, :2241, :2250, :2256) need an explicit in/out decision so the "~13 sites" claim can be checked.
- `updatePreview` runs on every render (via `renderAll`), so any reason element for Copy/Download must be updated there, and cleared when the model is valid (the AC's "absent when enabled").

### Conventions in Force
- Hint elements are `<p class="hint">`/`small.help` filled through `.textContent` (:165, :168); JS assigns classes via `el.className = …`.
- Interaction with ENH-3513 / BUG-3512: an `aria-describedby` target that is also a live region would double-announce; ENH-3513 explicitly owns diagnostics announcements and BUG-3512 (done) owns `#conn-status`/`#conn-notices`/`#conn-review-info` live regions, both editing `renderConnected`.
- Golden byte-comparison (`test_enh3035_artifact_template_kit.py:93-103`) and `test_policy_builder_emit.py` string-greps constrain how tests are written; there is no rendered-DOM pytest harness — assertions about "present while disabled, absent when enabled" are only checkable via the on-demand ENH-3500 probe (`.loops/probes/enh-3500-audit-probes.mjs`, which already records `aria-describedby`/`aria-disabled` per element at :75-77) or a vm-sandbox test in the style of `policy_validator.test.mjs:1574` (`_newBug3502Sandbox`).

**Tests (research)**
- `scripts/tests/test_policy_builder_emit.py` (static markup only); golden `scripts/tests/fixtures/policy_builder/golden_policy_router_builder.html` must be regenerated; probe cases `auth-invalid-model-*`, `conn-issue-selected-*`, `conn-review-none-*` to rerun via `CASE_ONLY`.

### Dependent Files (Callers/Importers)
_Wiring pass added by `/ll:wire-issue`:_
- BUG-3512 (done) and ENH-3513 both edit `renderConnected`/live regions — a reason element used as an `aria-describedby` target must not itself be `role=status`/`aria-live` (double announce) [Agent 2 finding]
- ENH-3510 also edits `renderOutcomes`/`renderRules` (delete-outcome, rule up/down sites) — sequence to avoid conflicts [Agent 2 finding]
- `.loops/probes/enh-3500-audit-probes.mjs` — already records `aria-describedby`/`aria-disabled` per element (:75-77); add present-while-disabled / absent-when-enabled assertions for `auth-invalid-model-*`, `conn-issue-selected-*`, `conn-review-none-*` [Agent 3 finding]

### Wiring: Tests
_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/fixtures/policy_builder/golden_policy_router_builder.html` — regenerate by hand after reviewing the diff (byte-compared in `test_enh3035_artifact_template_kit.py`) [Agent 3 finding]
- `scripts/tests/js/policy_validator.test.mjs` — `_newBug3502Sandbox` executes the template slices `let state = seedExample();`…`function buildModel() {` (incl. `commit()`) and the Open handler `$("open-project-input").onchange`…`$("undo-btn").onclick`; any new DOM call added inside those slices needs a stub in the sandbox's `elements`/`$` [Agent 3 finding]
- `scripts/tests/test_policy_builder_emit.py` — static asserts that reason elements and `aria-describedby` wiring exist in the markup [Agent 3 finding]

## Program Design

### Types

- None — DOM/markup only; no new persisted shapes.

### Signatures

- `updatePreview() -> void`
- `renderConnected(st) -> void`
- `renderOutcomes() -> void`
- `renderRules() -> void`

### Call Path

`cmd_policy_builder` -> `render_policy_builder_html` (stamps the template) -> in-page `updatePreview` / `renderConnected` -> new `aria-describedby` reason element

## Design Decisions

> **Context refresh (2026-09-19)**: BUG-3512 is **done** (2f5bdb89a). `:NNNN` line references in this issue predate it — roughly +4 up to `updatePreview` (now :1782) and +75 in the connected code (`renderConnected` now :2292). Function-name anchors remain correct; resolve by name, not line.

- **Copy/Download** reuse `#validate-hint` (:324) as the reason element. Today it shows the Save to / Validate / Run guidance whenever `serializeLoopYaml` succeeds — including when export is disabled by validation errors — and is blanked only on a serializer throw (:1790). New behavior in `updatePreview`: when `hasError`, `#validate-hint` reads `EXPORT_DISABLED_REASON` — the constant ENH-3513 defines ("Copy and Download are disabled until the errors above are fixed."); do not re-declare the literal — (replacing the guidance, which is misleading while export is off) and both buttons get `aria-describedby="validate-hint"`; when `!hasError` the guidance returns and the attribute is removed. The `hasError` computation (:1795-1796) must move above the `#validate-hint` assignment.
- **Submit/Review** share one new static `<p class="hint" id="conn-action-reason" hidden>` after the button row. Its text is derived from the first true clause, in order: `!av.ok` → hidden (already explained by `#conn-unavailable`; point `aria-describedby` there instead); `st.busy` → "Working…" (Review is `aria-disabled`, not `disabled`, in this state since BUG-3512 — it stays focusable, so this is the one case where `aria-describedby` is reached by focus; wire it on Review as well as Submit); `outcome_unknown` → explain the unknown delivery state and derive next steps from the actual available controls: Refresh status when idle, Retry only when `sub.canRetry`, and Run again only when `av.ok && rv.status === "ready"`. When review is not ready, direct the user to Review (or to correct the refusal reason and review again) before suggesting Run again. Never name a hidden or disabled action as an available next step. Otherwise, `rv.status === "refused"` → explain the review refusal using `rv.reason` and request correction/review; other non-ready review states → "Review the snapshot before submitting." Hide the shared reason when Submit is enabled. Associate it with Submit while disabled, and with Review only while Review is unavailable/busy; an enabled Review must not retain a stale disabled-reason association.
- **Reason elements are never live regions** (no `role=status`/`aria-live`) — BUG-3512 and ENH-3513 own announcements; a describedby target that is also live double-announces.
- **Delete-outcome-in-use**: per-row `<small class="help">` with an ID derived from the outcome index (`oc-del-reason-${oi}`), rendered only while `inUse`.

## Acceptance Criteria

- [ ] Rendered HTML contains exactly one `id="conn-action-reason"` (a `<p class="hint"` with `hidden`) and no `role=`/`aria-live` on it or on `#validate-hint` (pytest: `test_policy_builder_emit.py`).
- [ ] Invalid model: `#validate-hint` shows the disabled reason and Copy/Download carry `aria-describedby="validate-hint"`; valid model: guidance text is back and the attribute is absent (probe: `auth-invalid-model-*`).
- [ ] Connected, issue selected, not yet reviewed: `#conn-action-reason` visible with the review-first text and Submit is described by it; after a successful review it is hidden and the attribute is absent (probe: `conn-issue-selected-*`, `conn-review-none-*`).
- [ ] While busy, Review carries `aria-disabled="true"` **and** `aria-describedby="conn-action-reason"` with the "Working…" text; both are removed when idle (probe).
- [ ] `#validate-hint`'s disabled text comes from `EXPORT_DISABLED_REASON` — the literal appears once in the rendered HTML (pytest).
- [ ] Connected but unavailable: `#conn-issue`, Review and Submit are described by `#conn-unavailable`; `#conn-action-reason` stays hidden (probe).
- [ ] Outcome-unknown cases cover ready/not-ready review and `canRetry` true/false, including neither Retry nor Run again available. Guidance names only visible, enabled next steps and updates after refresh/review. Refused review includes its actionable reason (browser).
- [ ] Busy-to-idle transitions restore the appropriate reason for the resulting state and remove stale Review associations; becoming available/enabled clears prior unavailable-state associations. Assert computed visibility and `aria-describedby` targets, not just markup (browser).
- [ ] An in-use outcome shows its visible reason; rule ↑ on the first rule and ↓ on the last have the "Already first/last" `title` (probe).
- [ ] `_newBug3502Sandbox` stubs cover any new DOM call inside the sliced regions; golden regenerated; `python -m pytest scripts/tests/` exits 0.

## Implementation Steps

1. Add `#conn-action-reason` markup; move the `hasError` computation above the `#validate-hint` write in `updatePreview` and wire text + `aria-describedby` there.
2. Derive the Submit/Review reason in `renderConnected` per the clause order and available-action conditions above, including refused review and busy-to-idle cleanup; wire `#conn-issue`/Review/Submit to `#conn-unavailable` when `!av.ok`.
3. Add the per-row delete-outcome reason in `renderOutcomes` and dynamic titles in `renderRules`.
4. Static asserts in `test_policy_builder_emit.py`; present-while-disabled / absent-when-enabled assertions in the ENH-3500 probe.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- In/out for the unlisted `.disabled` sites is **decided** — see Scope Boundaries; Submit reason derivation is specified in Design Decisions
- Sequenced via `blocked_by`: BUG-3512 → ENH-3513 → **ENH-3511** → ENH-3510 → ENH-3514 → BUG-3516 (shared template + byte-compared golden — never run in parallel)
- Update `.loops/probes/enh-3500-audit-probes.mjs` and rerun the three named cases via `CASE_ONLY`; regenerate the golden

## Impact

- **Priority**: P3 - accessibility polish
- **Effort**: Small-Medium - ~13 sites, mostly hint wiring
- **Risk**: Low - additive attributes and text
- **Breaking Change**: No

## Status

**Open** | Created: 2026-09-19 | Priority: P3


## Confidence Check Notes

_Updated by `/ll:confidence-check` on 2026-09-19_

**Readiness Score**: 100/100 → PROCEED
**Outcome Confidence**: 56/100 → LOW

### Concerns
- Prior Dependencies Hard Override is cleared: ENH-3513 and BUG-3512 are both completed. `EXPORT_DISABLED_REASON` now exists in the template and `_describedTokens` (:529) is available for token-list `aria-describedby` handling.
- No format-check, parity, claim, decision, or Program Design gaps.

### Outcome Risk Factors
- Deep per-site complexity in `renderConnected`: the Submit/Review reason is a clause-ordered derivation with busy-to-idle cleanup and outcome-unknown branching.
- Weak automated coverage: no rendered-DOM pytest harness; the key ACs are verified only by the on-demand ENH-3500 probe or a browser check.
- Shared byte-compared golden template is edited by ENH-3510 and ENH-3514; sequencing is required.

## Verification Notes

_Added by `/ll:verify-issues` — 2026-09-19 (`--auto`)_

Verdict at time of check: **NEEDS_UPDATE** (corrections below applied in the same pass, so the issue as it now reads is up to date — this section is a record of what was wrong and fixed, not an outstanding action item)

- **Stale blocker**: ENH-3513 is `done` (frontmatter `status: done`), so the `blocked_by: ENH-3513` edge is satisfied. The `## Confidence Check Notes` "Gaps to Address" line ("ENH-3513 (open)") and the concern "`EXPORT_DISABLED_REASON` … not yet in the template (0 occurrences)" are outdated: the constant now exists at `EXPORT_DISABLED_REASON` (template :442) and is used in `_errorCountText`-based summary text (:518). Re-run `/ll:confidence-check` to refresh the score. The literal still appears once, so the AC "appears once in rendered HTML" remains checkable.
- **Line numbers shifted again** (ENH-3513 landed): `updatePreview` :1909, `renderConnected` :2431, `renderOutcomes` :903, `renderRules` :1156, `#validate-hint` markup :329, `#conn-unavailable` :338. Resolve by function name.
- **Design Decisions still accurate**: `hasError` is computed *after* the `#validate-hint` write (:1926 vs :1918) so the "move above" step is still required; `#validate-hint` is still blanked only on a serializer throw; Review already toggles `aria-disabled` while busy (:2467).
- **New reusable helpers from ENH-3513**: `_describedTokens(input)` (:529) plus the add/remove token pattern in `_showAddError`/`_clearAddError` (:533-553) manage `aria-describedby` as a token list. Use that pattern (do not overwrite the attribute) so ENH-3511's `aria-describedby` on `#conn-issue`/Copy/Download/Review/Submit composes with any existing tokens.
- **Disabled-site inventory verified** (current lines): undo/redo :642-643, `delOc` :916, `valInput` :1204, up/down :1280/:1285, `idxInput` :1671, Copy/Download :1928-1929, `#conn-issue` :2456, Review :2466, Submit :2469, Refresh :2474 — matches Scope Boundaries.
- Evidence-quote check (`ll-verify-evidence`): clean. Decisions rules: none active. Graph: provider=codegraph freshness=fresh (not needed; all anchors resolved by grep).
- `PROPOSAL_UNSOUND` check: no defect found; note the `_newBug3502Sandbox` stub requirement already in ACs.

## Session Log
- `/ll:confidence-check` - 2026-09-20T01:50:50 - `ac2baf4a-172c-47a9-b6de-52a871f58f17.jsonl`
- `/ll:verify-issues` - 2026-09-20T01:49:34 - `7073c4c9-52a5-4dc1-bc72-f507fdf9043b.jsonl`
- `/ll:confidence-check` - 2026-09-20T00:50:23 - `b1e66617-7ca3-4c73-8eef-611558ec10fe.jsonl`
- `/ll:verify-issues` - 2026-09-20T00:42:35 - `87477791-8eac-4eaa-a6b5-62a48362f015.jsonl`
- `/ll:audit-issue-conflicts` - 2026-09-19T21:30:33 - `6b9c88d3-074c-4681-b7c9-240fc332f147.jsonl`
- `/ll:wire-issue` - 2026-09-19T21:05:52 - `39128071-49a7-41ee-a288-c86d0c6aa6ea.jsonl`
- `/ll:refine-issue` - 2026-09-19T20:57:40 - `7ba3809c-e334-468e-81b6-cf0bbfd0f90c.jsonl`
- `/ll:format-issue` - 2026-09-19T20:40:32 - `62ea2c42-153a-4077-bc55-dc91a943784a.jsonl`

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): Transient-busy Review/Refresh buttons use `aria-disabled="true"` per BUG-3512 (which owns `#conn-*` announcers and that change); every other disabled condition stays native `disabled`. `#conn-action-reason` and its `aria-describedby` wiring must apply to both forms. ~~Reuse the connected-state summary BUG-3512 introduces~~ — **withdrawn after BUG-3512 landed**: `_connSummary(st)` describes submission *delivery* state only (`{text, alert, key}`, `null` without a submission) and exposes no `busy` / `rv.status` clauses, so the clause-order derivation in Design Decisions stands. The Copy/Download disabled reason in `#validate-hint` uses ENH-3513's `EXPORT_DISABLED_REASON` constant; `#validate-hint` is a non-live describedby target.
