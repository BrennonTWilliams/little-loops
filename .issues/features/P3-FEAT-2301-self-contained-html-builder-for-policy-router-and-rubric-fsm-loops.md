---
id: FEAT-2301
title: Visual builder for policy-router and rubric FSM loops (UX shell)
type: FEAT
priority: P3
status: open
discovered_date: 2026-06-26
discovered_by: capture-issue
captured_at: '2026-06-26T00:35:41Z'
relates_to:
- FEAT-2390
- ENH-2299
- ENH-2309
- FEAT-1023
blocked_by:
- FEAT-2390
confidence_score: 90
outcome_confidence: 76
score_complexity: 10
score_test_coverage: 5
score_ambiguity: 15
score_change_surface: 10
decision_needed: false
---

# FEAT-2301: Visual builder for policy-router and rubric FSM loops (UX shell)

## Prototype mockup

Static UX mockup (open over `file://`):
[`thoughts/feat-2301-ui-mockup.html`](../../thoughts/feat-2301-ui-mockup.html). A **single
header toggle is the sole mode switch** (no duplicate in-form mode picker); it flips between
Decision Table (ordered rule sentences, visible/reorderable precedence, shadow nudge, pinned
"Otherwise") and Rubric (the minimal two-threshold / three-tier surface). Also shows the
demoted-YAML summary rail, seeded example, and config-honoring theme. Non-functional shell
only; the emit/validate engine is FEAT-2390. See § Mode asymmetry.

## Rescope (2026-06-28)

A first implementation shipped on branch `feat-2301-self-contained-html-builder` and was
**sub-par as an authoring tool**: confusing layout, internal jargon leaked into the UI
(`Action (Axis A)` / `Then (Axis B)`), no visible rule precedence and no way to reorder
rules, the catch-all rendered as a stray text input, raw YAML occupying half the viewport,
and a theme toggle that ignores the project's configured default. It failed several of its
own acceptance criteria (sequence badges, drag-reorder, fallback footer, human wording)
and was treated as done because **nothing verified the artifact against the experience.**

Root cause of the planning miss: the old spec (830 lines) measured *technical
completeness* — YAML correctness, grammar single-sourcing, drift guards, normalization —
and had no acceptance criterion a confusing-but-valid form could fail. Readiness hit 98/100
on the legible half while the actual point (can a non-expert use this?) was never designed
or gated. Two different problems — "emit correct YAML" and "be a pleasant authoring
surface" — were bundled, and the engineer-legible half crowded out the design half.

This rewrite fixes that by:

1. **Splitting the engine out to FEAT-2390** (the testable emit/validate core — keep all of
   it, it is genuinely good). This issue is now *only* the human-facing shell.
2. **Leading with the UX model**, not the YAML.
3. **Adding usability acceptance criteria that can fail**, plus a required walkthrough gate.
4. **Cutting scope** to the smallest thing that is actually pleasant (this is a P3 nicety,
   not a platform).

## Summary

A single self-contained `.html` page (no install, no server, works over `file://`) that
lets someone author a valid `policy-router` (Decision Table) or `rubric-router` (Rubric)
FSM loop and download YAML that passes `ll-loop validate` — **without** hand-writing the
`import:` block, `route:` map, catch-alls, or per-state transitions. The correctness engine
that produces and validates that YAML lives in FEAT-2390; this issue is the interface that
drives it.

## Capability to preserve

Unchanged from the original intent: a real grid/list fits the decision table's shape
better than the linear `/ll:create-loop` wizard (ENH-2299), and authoring affordances can
make error classes — missing catch-all, MR-4 dead-ends, numeric-coercion, dead predicates —
**structurally unrepresentable** rather than validated after the fact. Greenfield only;
round-trip editing of existing loops stays with `ll-loop edit-routes`.

## The UX model

Core reframe: **a policy router is one sentence** — "WHEN conditions THEN do X and go to Y …
OTHERWISE fallback." The interface should *be* that sentence, ordered top-to-bottom, where
the on-screen order **is** the precedence.

1. **One primary surface: an ordered, numbered rule list that reads as sentences.**
   Example row: "①  When `quality ≥ 80` and `has-citations is true` → **light-repair**:
   re-prompt, then re-score." The visible number is the precedence (first-match-wins, top
   to bottom). A fixed, dashed "**Otherwise →** `deep-repair`" is pinned last and cannot be
   deleted or moved. Precedence is **reorderable** (drag, or ↑/↓ buttons — see Non-goals).
2. **Progressive disclosure, not a flat fieldset dump.** Mode (Rubric vs Decision Table) is
   chosen by a **single persistent toggle** in the header — the *only* mode control, never
   duplicated by an in-form picker. Step 1: what you're grading, with the active mode
   explained in one plain sentence (Rubric = one aggregate score; Decision Table = per-signal
   rules) — never "Lite/Full". Step 2: the signals you score (dimensions). Step 3: the rule
   list + per-outcome action. Don't show everything at once.
3. **Plain-language action authoring, each outcome named once.** An outcome's action
   ("re-prompt with this text" / "run `/ll:<skill>`" / "do nothing") and its follow-up
   ("score again" / "go to `<outcome>`" / "stop here") are two human-labeled dropdowns. The
   follow-up is a forced choice (keeps MR-4 dead-ends unrepresentable) — labeled
   "And then:", **not** "Axis B". No internal token (`context.subject`, `policy_rules`,
   `predicate`, `Axis A/B`) appears as a primary label.
4. **Validation as gentle inline nudges tied to the visible numbers.** "Rule ③ can never
   run — rule ① above already matches everything it would." Because rows are visibly
   ordered, "rule ① above" now means something. A small status chip reads "✓ Ready to
   export" or "2 things to fix".
5. **Demote the raw YAML.** The default right-hand view is a one-line plain summary
   ("Scores `artifact.md` on 2 signals, runs ≤20×, stops at `done`") plus **Download** and
   the `ll-loop validate <name>` hint. The YAML itself sits behind a collapsed "View
   generated file" disclosure — present, not in your face.
6. **Never a blank form.** The page seeds with a small runnable example; a "Start blank"
   affordance clears it.
7. **Theme that honors the project.** The page opens in the project's configured
   `active_theme` (stamped by FEAT-2390), the toggle flips light/dark and persists, and
   neither the configured default nor an explicit user toggle is silently overridden by OS
   preference.

## Mode asymmetry (2026-06-28)

The two modes are **not** symmetric surfaces, and the UX model above (ordered
first-match rule sentences, visible + reorderable precedence, shadow nudges, the
pinned "Otherwise →" footer) describes **Decision Table only**. That maps onto
`lib/policy-router.yaml`'s `context.policy_rules` table — ordered, conjunctive
(`&`), per-dimension predicates with a `*` catch-all dispatched through a generated
`route:` map.

The Rubric grammar (`lib/rubric-router.yaml`) is far smaller: **pipe-separated
dimension names with no weights**, a fixed two-threshold ladder
(`threshold_high` / `threshold_medium`) routed by two `on_yes`/`on_no` exit-code
gates → exactly **three tiers** (high / medium / low). There is no rule ordering,
no per-dimension predicate, no arbitrary band count, and nothing to reorder.

**Decision: keep both modes, but build Rubric as a deliberately minimal,
grammar-faithful surface** — dimension *names* only (no weight inputs), exactly two
threshold fields, three tier outcomes with the same plain "Do / And then" action
authoring, and a pinned low-tier "Otherwise". The DT-specific affordances (reorder,
add-rule, shadow detection, conjunctions) are **not** shown in Rubric mode, because
the UI must not let the author express structure the grammar can't emit (the inverse
of the "make invalid states unrepresentable" principle). "Decision Table" already
*is* "rubric + policy" (it imports the rubric fragment to produce the scores it then
routes on); there is no third "both" mode. The earlier worktree mockup that showed
weighted dimensions and reorderable "bands" in Rubric mode was fabricating capability
and has been corrected.

## Acceptance Criteria

### Capability (functional — most delegated to FEAT-2390)

- [ ] Loads over `file://` with no external dependency; mode switch (Rubric ⇄ Decision
  Table) renders without reload.
- [ ] Downloaded YAML for either mode passes `ll-loop validate` with zero errors. (Engine:
  FEAT-2390.)
- [ ] Decision Table: dimension type (numeric/boolean) restricts the operator choices to
  valid ops only. (Engine grammar: FEAT-2390.)
- [ ] Skill dropdown for "run a skill" is populated from the emit-time-stamped project
  catalog. (Engine: FEAT-2390.)

### Usability (must be able to fail — verified against the *generated* page)

- [ ] **Task gate:** a person familiar with the loop concept but not the YAML produces a
  valid Decision Table loop that passes `ll-loop validate` in **≤5 minutes without opening
  `POLICY_ROUTER_GUIDE.md`.** (See Verification.)
- [ ] **Precedence is visible and reorderable:** rules show an explicit top-to-bottom number;
  reordering (drag or ↑/↓) changes which rule wins in the live preview. *(Worktree build
  fails this.)*
- [ ] **No internal jargon in the UI:** no `Axis A/B`, `context.subject`, `policy_rules`,
  `predicate`, or raw normalized identifiers as primary labels. *(Worktree build fails.)*
- [ ] **Catch-all is a pinned, non-deletable "Otherwise →" footer**, visually distinct from
  rules — not a free text input among the rule fields. *(Worktree build fails.)*
- [ ] **YAML is secondary:** the default view is the plain summary + Download; raw YAML is
  collapsed. *(Worktree build fails — YAML takes ~50% of the viewport.)*
- [ ] **Theme honors config:** the page opens in `active_theme`; toggle flips + persists;
  OS preference does not silently override either. *(Worktree build fails — opens light
  despite `active_theme: dark`; emit path never stamps `active_theme`.)*
- [ ] **Single mode control:** mode (Rubric ⇄ Decision Table) is selected by exactly one
  persistent toggle; no second in-form mode picker duplicates it. *(Original mockup paired
  the header toggle with a redundant Step-1 mode-card selector — removed for clarity.)*
- [ ] **Seeded example** present on load; "Start blank" clears it.
- [ ] **Inline messages reference visible rule numbers** and update live.
- [ ] **Rubric mode is grammar-faithful, not a DT clone:** dimensions show names only
  (no weight inputs), exactly two threshold fields / three fixed tiers, and the DT-only
  affordances (reorder, add-rule, shadow nudges, conjunctions) are absent. The UI never
  offers structure `lib/rubric-router.yaml` cannot emit. *(See Mode asymmetry.)*

## Verification (the gate that can fail)

Before this issue is `done`, a reviewer **who did not build it** performs the task gate
above against the generated `policy-router-builder.html` and confirms each Usability AC,
capturing screenshots of: (a) the rule list with visible precedence, (b) a reorder changing
the winning outcome in the preview, (c) the collapsed-YAML default view, (d) the correct
initial theme. **A build with valid YAML but sub-par UX fails this gate.** Prefer a second
person or a subagent review over self-review — the original failure was the absence of any
external check on the experience.

## Non-goals (scope cut for v1)

- No new public API, CLI namespace, design-token function, or config keys beyond what
  FEAT-2390 already owns. This issue adds only the template + interaction layer + the
  usability harness.
- No round-trip editing of existing loops (`ll-loop edit-routes` owns it).
- No nested/chained policy tables — one flat `context.policy_rules`.
- **No in-page profile picker** (the optional 3-profiles × 2-themes inlining). v1 stamps the
  single active profile, light + dark only.
- **No advanced action types** (shell / MCP-tool / raw) in v1 — Prompt / Run-a-skill /
  Nothing only.
- Reorder may ship as ↑/↓ buttons if drag-and-drop proves expensive; the requirement is
  *visible + reorderable precedence*, not drag specifically.

## Architecture note (so the affordances don't get cut again)

The single-file `file://` output is an **output** constraint, not a **source** constraint.
The worktree build hand-rolled the UI in raw `createElement` vanilla JS, which made
reorder, the pinned footer, and progressive disclosure expensive — so they were dropped. If
they prove expensive again, use a **dev-time build step** that bundles a small component
layer into one inlined HTML file: the output stays self-contained and CDN-free; the source
stops being raw DOM scripting. Budget for this explicitly rather than letting the portability
rule silently veto the interaction design.

## Layer split

- **FEAT-2390 (engine, blocks this):** model → YAML serializer, grammar stamping, boolean
  encoding, dimension normalization, MR-4 unrepresentability, in-browser validator module,
  conformance corpus + node test + drift guard, themed CSS vars, the `ll-artifact
  policy-builder` emit/stamp path. Gated by tests.
- **FEAT-2301 (this issue, shell):** the HTML template, CSS, and interaction/UX that builds
  the model object and calls the engine. Gated by the usability walkthrough.

## Impact

- **Priority**: P3 — authoring quality-of-life; the pattern already works via hand-authoring
  and `edit-routes`. No urgent unblock.
- **Effort**: Medium — one self-contained HTML artifact + interaction layer + a usability
  harness; engine is FEAT-2390. Budget for a small build step if needed.
- **Risk**: Low to runtime (additive); the real risk is UX quality, now caught by the
  walkthrough gate rather than after release.
- **Breaking Change**: No

## Labels

`feature`, `loops`, `policy-router`, `design-tokens`, `html`, `tooling`, `ux`

## Session Log
- `single-toggle mode control` - 2026-06-28 - Removed the duplicate Step-1 mode-card picker
  from `thoughts/feat-2301-ui-mockup.html` so the header toggle is the sole Decision Table ⇄
  Rubric switch. Two competing mode selectors were cluttering the surface and obscuring which
  one drives the form; Step 1 is now just "what you're grading" plus a one-line plain-language
  explainer of the active mode. Also pruned the now-dead `.mode-card` CSS and the `setMode`
  JS that toggled the cards. Propagated to the spec: rewrote UX-model §2, updated the
  Prototype-mockup blurb, and added a "Single mode control" usability AC. Simplicity-first per
  user direction ("the toggle must be the only expression of mode").
- `mode-asymmetry decision` - 2026-06-28 - While mocking up the UI, checked the emitted
  grammar against the canonical `lib/policy-router.yaml` / `lib/rubric-router.yaml` and
  `loops/{policy,rubric}-refine.yaml`. Found the ordered-reorderable-rule-list UX model is
  Decision-Table-specific; Rubric is only dimension names + two thresholds → three tiers
  (no weights, no reorder, no extra bands). Decided to keep both modes but make Rubric a
  minimal grammar-faithful surface; added the "Mode asymmetry" section + a usability AC, and
  corrected the working mockup (`thoughts/feat-2301-ui-mockup.html`), which had been showing
  fabricated weighted-dimensions and reorderable bands in Rubric mode.
- `rescope (UX-first rewrite)` - 2026-06-28 - Rewrote around the UX after the worktree
  build shipped sub-par. Split the testable engine to FEAT-2390; led with the
  ordered-sentence rule-list model (visible + reorderable precedence, progressive
  disclosure, plain language, demoted YAML, seeded example, config-honoring theme); replaced
  the testing-shaped ACs with usability ACs that can fail + a required external walkthrough
  gate; cut scope (no profile picker, no advanced action types, no new platform surface).
  Migrated the engine-layer decision records (boolean encoding, grammar single-source, JS
  test runner, emit naming) to FEAT-2390.
- `target-state authoring decision` - 2026-06-26 - Action cards author the full target
  state along two axes (action + transition); routed-to names are author-invented and play
  three roles (rule token / `route:` entry / state name). [Retained; UI wording now plain
  per this rewrite. Engine contract in FEAT-2390.]
- `UI design decision` - 2026-06-26 - Action-grouped rule cards + "Everything else →"
  fallback footer + plain-language inline validation; rejected card-drag for action
  reassignment. [Superseded in part by the ordered-sentence-list model above; the
  fallback-footer and plain-language decisions are now enforced ACs.]
- `boolean-dim` / `grammar single-source` - 2026-06-26 - [Moved to FEAT-2390.]
- `/ll:confidence-check` (×4, 2026-06-25..27) - prior runs scored 98/100 readiness / 68
  outcome on the monolith; superseded by this split. The 68 gap (JS test coverage) is now a
  required AC in FEAT-2390.
- `/ll:capture-issue` - 2026-06-26T00:35:41Z - original capture.
