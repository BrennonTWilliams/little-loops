---
id: FEAT-2301
title: Visual builder for policy-router and rubric FSM loops (UX shell)
type: FEAT
priority: P3
status: open
discovered_date: 2026-06-26
discovered_by: capture-issue
parent: EPIC-2087
captured_at: '2026-06-26T00:35:41Z'
relates_to:
- FEAT-2390
- ENH-2299
- ENH-2309
- FEAT-1023
blocked_by: []
confidence_score: 90
outcome_confidence: 76
score_complexity: 10
score_test_coverage: 5
score_ambiguity: 15
score_change_surface: 10
decision_needed: false
---

# FEAT-2301: Visual builder for policy-router and rubric FSM loops (UX shell)

## Re-verification (2026-07-03)

Blocker **FEAT-2390 shipped (1.136)** — `blocked_by` cleared. FEAT-2390's
`ll-artifact policy-builder` already emits a working visual builder
(`scripts/little_loops/templates/policy-router-builder.html.tmpl`, 510 lines, stamps
design tokens + grammar spec + skill catalog). **Do not build a second shell from
scratch.** Bring `policy-router-builder.html.tmpl` up to the § The UX model spec
below, keeping the FEAT-2390 emit/validate core (`policy_builder_core.mjs`, JS
conformance suite via `test_policy_builder_node_gate.py`) as-is.

**Mockup-copy guard:** `thoughts/feat-2301-ui-mockup.html` is a visual/interaction
reference **only** — do not replace the template with it. The template's stamping
placeholders (`{{...}}`), its `policy_builder_core.mjs` wiring, and the themed CSS
vars must survive the rework unchanged; the existing node gate must keep passing
throughout.

## AC re-baseline (2026-07-25)

Re-verified every AC directly against the shipped template
(`policy-router-builder.html.tmpl`) and `cli/artifact.py`'s emit path, replacing the
stale "(Worktree build fails)" annotations below (those described a dead branch,
not what's actually shipped). Status key: ✅ shipped / ❌ missing / ⚠️ partial.

**Capability**
- ✅ Loads over `file://`, mode switch renders without reload (`#mode-switch`
  onchange, no `<script src>`/CDN refs).
- ⚠️ Downloaded YAML passes `ll-loop validate` — `serializeLoopYaml` looks
  structurally complete but wasn't executed against a live sample as part of this
  pass; still needs an actual `ll-loop validate` run to confirm zero errors.
- ✅ Dimension type restricts operator choices (`opsForType()` maps
  boolean → `==true/==false`, else `GRAMMAR.all_ops`).
- ✅ Skill dropdown populated from emit-time catalog (`artifact.py` globs
  `skills/*/SKILL.md`, stamps `window.__SKILL_CATALOG__`).

**Usability**
- ⚠️ Task gate (≤5 min, no docs) — full DT rule-authoring UI exists but the flow
  (add dimension → add outcome → add condition → pick action/transition per
  outcome) is verbose with no guided/wizard path; untimed.
- ❌ **Precedence visible/reorderable** — messages cite `Rule N` internally but the
  form UI has no visible numbered rule list and no reorder control (no drag
  handles, no ↑/↓). Rule order is implicit insertion order, not user-movable.
  **Still the core UX gap this issue exists to close.**
- ❌ **No internal jargon** — template literally labels fields `Subject
  (context.subject)`, `Action (Axis A)`, `Then (Axis B)` as on-screen text, not just
  in comments. **Still open.**
- ⚠️ **Pinned catch-all footer** — a non-deletable `.fallback-row` ("Everything
  else →") exists and is visually distinct (italic), but it's still a free-text
  `<input>` (`f-fallback`), which is exactly what the AC says it must not be.
- ❌ **YAML secondary** — the right panel shows raw `<pre>` YAML directly as the
  only/default view; no plain-summary line, no collapsed `<details>` wrapper.
  **Still open.**
- ⚠️ **Theme honors config** — `active_theme` IS stamped into `data-theme` /
  `window.__ACTIVE_THEME__` by `artifact.py` (contradicts the old AC text claiming
  "emit path never stamps active_theme" — that line is stale and removed below).
  But `initTheme()` checks `prefers-color-scheme` *before* falling back to the
  stamped config value, so OS preference still silently overrides the configured
  default — the AC's actual complaint ("OS pref does not silently override")
  survives, just for a different reason than originally written. Toggle persistence
  via `localStorage` does work.
- ✅ Single mode toggle, no duplicate in-form picker.
- ⚠️ Seeded example exists on load; no "Start blank" control exists to clear it.
- ⚠️ Inline messages reference rule numbers for shadow warnings only (other
  message types don't), and since there's no visible numbered rule list (see
  above), "Rule 3" isn't traceable by the user anyway.
- ✅ Rubric mode is grammar-faithful (names-only dimensions, two thresholds, three
  hardcoded tiers, no DT affordances leak in).

**Net effect on scope**: 4 of 9 usability ACs are genuine remaining gaps (reorder,
jargon, YAML-secondary, catch-all-as-input-not-footer); the rest are already
shipped or partial-with-a-small-fix (theme OS-precedence order, add Start-blank).
This is smaller than "build the UX layer" — it's four targeted UI fixes to an
existing, working template plus one ordering fix in `initTheme()`.

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

## Current Behavior

The shipped `policy-router-builder.html.tmpl` (FEAT-2390's emit path) already
produces valid YAML and covers all four Capability ACs, but as an authoring
surface it still fails 4 of 9 usability ACs per the 2026-07-25 re-baseline:
internal jargon leaks into on-screen labels (`Action (Axis A)`, `Then (Axis
B)`, `Subject (context.subject)`); rule precedence has no visible numbered
list and no reorder control (implicit insertion order only); the catch-all
footer is non-deletable but still a free-text `<input>`; and raw YAML is the
only/default right-panel view with no collapsed summary. `initTheme()` also
lets OS `prefers-color-scheme` silently override the stamped project theme.

## Expected Behavior

Per § The UX model: an ordered, numbered rule list reads as plain-language
sentences ("When … then …") with visible, reorderable precedence (drag or
↑/↓); no internal token names appear as on-screen labels; the catch-all is a
pinned, non-deletable, non-input "Otherwise →" footer; the YAML is demoted
behind a collapsed disclosure with a plain-summary default view; the seeded
example ships with a "Start blank" control; and theme resolution is stored
toggle → stamped `active_theme` → OS preference → light (the configured
default is never silently overridden by OS preference).

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
   preference. Resolution order in `initTheme()`: stored user toggle → stamped
   `window.__ACTIVE_THEME__` → OS `prefers-color-scheme` → `light`.
8. **A minimal "Try it" tester makes precedence *felt*, not just visible.** A small
   panel (DT mode only) with one input per dimension; entering sample values
   highlights the first matching rule row — the winner — live. This is the "live
   preview" the precedence AC refers to: reordering rules visibly changes which row
   lights up for the same sample values. Scope guard: it is a highlight-the-winner
   evaluator over the already-built rule model (the predicate-match logic mirrors
   `policy_builder_core.mjs`'s rule semantics), **not** a loop simulator — no state
   execution, no actions run, no multi-step traces. If even this proves expensive,
   the fallback that still satisfies the AC is: reordering renumbers the rows and
   re-runs shadow detection so nudges update live.

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

## Use Case

A developer authoring a new quality-gate loop opens
`policy-router-builder.html` over `file://`, picks Decision Table mode, adds
two dimensions (`quality` numeric, `has-citations` boolean), writes three
rules as plain sentences with visible precedence numbers, uses the "Try it"
tester to confirm reordering changes which rule wins for a sample input, and
downloads YAML that passes `ll-loop validate` with zero errors — without
reading any documentation or hand-editing a `route:` map.

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

### Usability — structurally gated (automated; add assertions to the node
### conformance suite run by `test_policy_builder_node_gate.py`)

These can and must be checked by machine against the generated page, so they cannot
silently regress after the one-time walkthrough. Each becomes a `node --test`
assertion over the emitted HTML/DOM:

- [ ] **No internal jargon in the UI:** denylist assertion — no `Axis A`, `Axis B`,
  `context.subject`, `policy_rules`, `predicate`, or raw normalized identifiers appear
  in visible markup (element text content / labels; code comments exempt). *(Still
  present verbatim in the shipped template as on-screen labels — "Subject
  (context.subject)", "Action (Axis A)", "Then (Axis B)" — confirmed 2026-07-25.)*
- [ ] **Catch-all is a pinned, non-deletable "Otherwise →" footer**, visually distinct
  from rules — a structured element with no delete control and no free-text target
  input among the rule fields (target chosen from existing outcomes). *(Partially
  shipped: `.fallback-row` is non-deletable and visually distinct, but is still a
  free-text `<input>` — confirmed 2026-07-25.)* Assert: footer element exists, has no
  remove button, no free-text `<input>` for the target.
- [ ] **YAML is secondary:** raw YAML sits inside a `<details>` (or equivalent)
  that is collapsed by default; the default view is the plain summary + Download.
  *(Still missing: shipped template shows raw `<pre>` YAML as the only/default view —
  confirmed 2026-07-25.)* Assert: YAML container collapsed on load; summary element
  present.
- [ ] **Theme honors config:** `initTheme()` resolution order is stored toggle →
  stamped `window.__ACTIVE_THEME__` → OS preference → light. *(Emit path already
  stamps `active_theme` (`artifact.py:105-112`); the gap is that `initTheme()`
  checks `prefers-color-scheme` first, so OS preference silently beats the config —
  confirmed 2026-07-25. Fix is a precedence reorder, not stamping.)* Assert: with a
  stamped theme and no stored value, `data-theme` equals the stamped theme.
- [ ] **Single mode control:** exactly one mode toggle in the DOM; no in-form
  duplicate. *(Shipped — keep as a regression assertion.)*
- [ ] **Seeded example** present on load; a "Start blank" control clears it. Assert:
  initial model non-empty; blank control exists.
- [ ] **Rubric mode is grammar-faithful, not a DT clone:** in Rubric mode the DOM
  contains no weight inputs, no add-rule/reorder/conjunction affordances, exactly two
  threshold fields and three fixed tiers. The UI never offers structure
  `lib/rubric-router.yaml` cannot emit. *(See Mode asymmetry.)* Assert on the
  rubric-mode DOM.

### Usability — walkthrough gated (experiential; cannot be asserted by machine)

- [ ] **Task gate:** a fresh reviewer produces a valid Decision Table loop without
  docs — protocol pinned in § Verification.
- [ ] **Precedence is visible and reorderable:** rules show an explicit top-to-bottom
  number; reordering (drag or ↑/↓) changes which rule wins in the "Try it" tester
  (UX model §8) for the same sample values, live. *(Still missing in the shipped
  template: `Rule N` appears in warning text but there is no visible numbered rule
  list or reorder control — confirmed 2026-07-25.)* The mechanical halves (numbers
  render, ↑/↓ mutate rule order in the model, tester highlights first match) also get
  node-suite assertions; the walkthrough judges whether it *feels* legible.
- [ ] **Inline messages reference visible rule numbers** and update live — shadow
  engine already returns numbered messages (`policy_builder_core.mjs:168-198`); this
  AC is about surfacing them next to the rows they name.

## Verification (the gate that can fail)

Two layers, in order:

1. **Automated:** the node conformance suite (extended with the structural
   assertions listed above) passes under `python -m pytest scripts/tests/` via
   `test_policy_builder_node_gate.py`. These assertions outlive the walkthrough and
   catch regressions after this issue closes.

2. **Walkthrough (task gate), pinned protocol** — an unpinned "someone tries it"
   check degrades into self-review, which is the exact failure the 2026-06-28
   rescope diagnosed. The gate is:

   - A **fresh reviewer who did not build it** — a second person, or a freshly
     spawned subagent with an empty context.
   - Given **only** the generated `policy-router-builder.html` (emitted by
     `ll-artifact policy-builder` against this repo's config) — no
     `POLICY_ROUTER_GUIDE.md`, no issue file, no template source, no builder
     conversation history.
   - Task: *"Author a Decision Table loop with 3 rules routing on two signals
     (`quality`, numeric; `has-citations`, boolean) to outcomes `done`,
     `light-repair`, `deep-repair`, with `deep-repair` as the fallback. Download the
     YAML."*
   - Pass: the downloaded YAML passes `ll-loop validate` with zero errors, achieved
     **without consulting any documentation**. Time bound: ≤5 minutes for a human;
     for a subagent, ≤15 interaction turns with the page (wall-clock time is
     meaningless for an agent).
   - The reviewer's transcript (or notes) is saved as the verification artifact,
     alongside screenshots of: (a) the numbered rule list, (b) a reorder changing
     the highlighted winner in the "Try it" tester for the same sample values,
     (c) the collapsed-YAML default view, (d) the correct initial theme with
     `active_theme: dark` stamped and OS preference set to light.

**A build with valid YAML but sub-par UX fails this gate.**

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
- **No loop simulator.** The "Try it" tester (UX model §8) is a single-step
  first-match highlighter over the rule model — no state execution, actions, or
  multi-step traces.

## Architecture note (so the affordances don't get cut again)

The single-file `file://` output is an **output** constraint, not a **source** constraint.
The worktree build hand-rolled the UI in raw `createElement` vanilla JS, which made
reorder, the pinned footer, and progressive disclosure expensive — so they were dropped. If
they prove expensive again, use a **dev-time build step** that bundles a small component
layer into one inlined HTML file: the output stays self-contained and CDN-free; the source
stops being raw DOM scripting. Budget for this explicitly rather than letting the portability
rule silently veto the interaction design.

**Build-step boundary:** if a dev-time build step is added, it uses Node ≥ 22
stdlib only — **no npm dependencies, no bundler package** (project policy: minimize
third-party deps; no hosted CI). A small hand-rolled inline script that concatenates
component files into the template, run and gated from the existing
`test_policy_builder_node_gate.py` pytest wrapper, is the ceiling.

## Layer split

- **FEAT-2390 (engine, blocks this):** model → YAML serializer, grammar stamping, boolean
  encoding, dimension normalization, MR-4 unrepresentability, in-browser validator module,
  conformance corpus + node test + drift guard, themed CSS vars, the `ll-artifact
  policy-builder` emit/stamp path. Gated by tests.
- **FEAT-2301 (this issue, shell):** the HTML template, CSS, and interaction/UX that builds
  the model object and calls the engine. Gated by the automated structural
  assertions plus the pinned-protocol walkthrough (§ Verification).

Related issues: FEAT-2390 (the emit/validate engine this shell drives), ENH-2299
(the linear `/ll:create-loop` wizard whose shape mismatch motivated a grid/list
builder), ENH-2309 (design-token theming the page consumes), FEAT-1023 (the
original `ll-artifact` self-contained-HTML substrate).

## Impact

- **Priority**: P3 — authoring quality-of-life; the pattern already works via hand-authoring
  and `edit-routes`. No urgent unblock.
- **Effort**: Small — the 2026-07-25 re-baseline found 5 of 9 usability ACs already shipped
  or trivially fixable (single toggle, rubric-faithful, seeded example, theme stamping now
  works). Remaining work is four targeted UI changes to the existing template: a visible
  reorderable rule list, de-jargoning three labels, a structured non-input catch-all footer,
  collapsing YAML behind a summary, plus a one-line fix to `initTheme()`'s precedence order.
  No new shell needed.
- **Risk**: Low to runtime (additive); the real risk is UX quality, now caught by the
  walkthrough gate rather than after release.
- **Breaking Change**: No

## Labels

`feature`, `loops`, `policy-router`, `design-tokens`, `html`, `tooling`, `ux`

## Session Log
- `/ll:format-issue` - 2026-07-25T16:15:53 - `ed6813fd-6bdd-41e8-88cc-99233de55ac7.jsonl`
- `review hardening` - 2026-07-25 - Applied review recommendations on top of the AC
  re-baseline: (1) added a mockup-copy guard (the `thoughts/` mockup is reference
  only; template stamping/core wiring must survive); (2) specced the previously
  implicit "live preview which rule wins" as a minimal "Try it" first-match
  highlighter (UX model §8) with an explicit no-simulator non-goal, since the
  precedence AC depended on an undesigned surface; (3) split the usability ACs into
  structurally-gated (automated `node --test` DOM assertions in the existing
  conformance suite, so they can't regress after close) vs walkthrough-gated
  (experiential); (4) pinned the task-gate protocol (fresh reviewer/subagent, page
  only, concrete 3-rule task, validate-clean pass condition, ≤5 min human / ≤15
  turns agent, transcript saved) so the gate can't degrade into self-review;
  (5) bounded the optional dev-time build step to Node ≥22 stdlib, no npm deps;
  (6) recorded why each `relates_to` entry is related.
- `AC re-baseline` - 2026-07-25 - Re-verified every AC against the shipped
  `policy-router-builder.html.tmpl` and `cli/artifact.py` emit path instead of
  deferring to implementation time. Found the stale AC claiming "emit path never
  stamps active_theme" is false (FEAT-2390 already stamps it) — the real remaining
  theme gap is `initTheme()`'s precedence order (OS preference checked before the
  stamped config value). Confirmed 4 genuine remaining usability gaps (reorder,
  jargon, YAML-secondary, catch-all-as-input) and downgraded effort from Medium to
  Small since 5 of 9 usability ACs are shipped or trivial.
- backlog-grooming - 2026-07-03T00:00:00Z - Parented to EPIC-2087 (was unparented; assigned per /ll:create-epics-from-unparented sweep).
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
