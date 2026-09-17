---
id: ENH-3492
parent: EPIC-3493
epic: EPIC-3493
type: ENH
title: Policy builder explicit terminal destinations, scoring instructions, and gate
  stamping
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-16'
captured_at: '2026-09-16T22:49:50Z'
labels:
- policy-builder
decision_needed: false
depends_on:
- BUG-3486
- BUG-3499
relates_to:
- ENH-3487
- ENH-3491
- BUG-3489
- FEAT-3474
blocks:
- FEAT-3488
blocked_by:
- ENH-3491
confidence_score: 80
outcome_confidence: 75
score_complexity: 10
score_test_coverage: 25
score_ambiguity: 22
score_change_surface: 18
---

# ENH-3492: Policy builder explicit terminal destinations, scoring instructions, and gate stamping

## Summary

Add explicit stop-success, skip, and needs-attention terminal destinations to lifecycle policies, optional per-dimension scoring instructions and score anchors, and stamp the project's confidence-gate thresholds into the builder. Split out of ENH-3487 (workstream c: emitted-YAML semantics). Design decisions are resolved below, including the 2026-09-17 review corrections.

## Current Behavior

The builder emits a binary terminal model, differing by mode:

- `issue_lifecycle` (`_serializeIssueLifecycle`, `scripts/little_loops/templates/policy_builder_core.mjs:1052-1122`) hardcodes `on_max_steps: failed` (`:1081`), every verb state carries `on_error: failed` (`:1111`), and only `done`/`failed` terminals are emitted (`:1114-1120`).

- `decision_table` (`_serializeDecisionTable`, `:807-910`) now unconditionally emits `on_max_steps: failed` (added by the BUG-3489 fix, committed `22f4ff6ed`; see `scripts/tests/fixtures/policy_builder/sample-decision-table.yaml:7`) — no model flag, and existing golden fixtures were regenerated (not kept byte-equal) as part of that change.

- `rubric` (`_serializeRubric`, `:912-987`) has a single `done` terminal and no `on_max_steps`.
No `stop-success`, `skip`, or `needs-attention` concept exists anywhere in the builder. Rubric dimensions have no score definitions. `cmd_policy_builder` (`scripts/little_loops/cli/artifact/policy_builder.py:61-112`) stamps only theme, CSS vars, grammar spec, and catalog; lifecycle defaults hardcode a confidence threshold. `ConfidenceGateConfig` (`scripts/little_loops/config/automation.py:155-170`) is unread by this command.

## Expected Behavior

Lifecycle rules can route to `stopped`, `skipped`, and `needs_attention` destinations, each emitting a valid loop. Reopening existing five-verb models emits YAML that differs from today's only by the `on_max_steps` line and the new terminal blocks (no verb, route, or action changes). Dimensions accept optional scoring instructions and score anchors that appear in emitted prompts. The builder displays the project's configured readiness/outcome thresholds alongside rule thresholds.

## Proposed Solution

1. Add lifecycle-only built-in destinations `stopped`, `skipped`, and `needs_attention` in `LIFECYCLE_DESTINATIONS`, separate from the five `LIFECYCLE_VERBS`. Rules and fallback may reference these terminals directly; verb transitions gain `stop`, `skip`, and `attention`. Keep `_emittedVerbs` restricted to verb states and use `_emittedDestinations` for terminal references. The serializer emits dispatch routes for referenced destinations and each terminal block once.

2. `stopped` and `skipped` are successful terminals (no `failure` key). `needs_attention` and existing `failed` emit `failure: true`. `on_error` stays `failed`; `on_max_steps` becomes `needs_attention` in all three modes (rubric emits no `on_max_steps` today, so there it is an added line rather than a changed one). This budget route is the explicit automatic exception; stop/skip remain author-selected. Preserve existing model fixtures; regenerate their YAML with changes limited to the budget route and added terminal blocks. No preservation flag is introduced.

   **Runtime prerequisite (review 2026-09-17)**: `FSMExecutor._finish` (`scripts/little_loops/fsm/executor.py:4337`) sets `failure_terminal` only when `terminated_by == "terminal"`. A cap-routed handler finishes with `terminated_by == "max_steps"`, so today `needs_attention` reached via `on_max_steps` reports `failure_terminal == False` even with `failure: true` (probe confirmed: `final_state needs_attention / terminated_by max_steps / failure_terminal False`). BUG-3499 fixes that in the executor and is in `depends_on`. Until it lands, the max-steps executor test below asserts `terminated_by == "max_steps"` and `final_state == "needs_attention"`; the `failure_terminal is True` assertion is added when BUG-3499 is done.

3. Register generated names in the shared per-mode reserved-name map: all three in lifecycle, `needs_attention` in rubric/decision-table. Reservation forbids an authored outcome from shadowing a generated state; it does **not** forbid an allowed lifecycle reference to that built-in destination. Update `_checkReservedTokens`, `_checkMissingReferences`, and the serializer's `_assertNoReservedTokens` defense together. Lifecycle target/fallback selectors offer verbs plus destinations; other modes keep their existing target rules and collision guards. Unknown names remain errors.

4. Optional dimension `instructions` and `anchors` affect LLM grading in rubric/decision-table modes via `_scoreActionBody`. Keep `_serializeDimensions` and `serializeFrontmatterDimensions` wire formats unchanged: the latter is `name:type|...` for deterministic frontmatter extraction, not a prompt. Lifecycle hides these editing controls and does not use their contents at runtime; imported metadata is retained on Save/Open. Validate anchors as unique finite numeric scores in [0,100] with nonempty meanings; boolean dimensions accept only 0/100 anchors. Emit multiline instructions safely through the existing YAML block-scalar helper and test delimiters/quotes/newlines. Absent metadata preserves existing prompts byte-for-byte.

5. Read `config.commands.confidence_gate` from the existing `BRConfig`; stamp enabled/readiness/outcome values and display them as project configuration alongside authored rule thresholds. Display disabled gates explicitly. Stamping is informational: never silently rewrite saved rule predicates or treat it as runtime enforcement. No config-schema change is required.

6. Extend ENH-3491's transition summary for the destinations (including unresolved budget exhaustion); no summary may classify `needs_attention` as a successful finish.

### Decision Rationale

The prior terminal decision is retained with explicit reference-vs-definition validation. Separate destinations prevent action editors from acquiring fake verbs. A failed budget terminal prevents unresolved loops reporting success. Scoring descriptions belong in LLM prompts, while lifecycle scoring remains deterministic frontmatter extraction. Saved-project round trips, not nonexistent YAML import, preserve the authoring metadata.

## Integration Map

- Files: `policy_builder_core.mjs`, `policy-router-builder.html.tmpl`, `cli/artifact/policy_builder.py`, `fsm/frontmatter_scores.py` is a compatibility surface only and remains unchanged.

- Tests: new `.model.json`/`.yaml` fixture pairs under `scripts/tests/fixtures/policy_builder/` for each new destination plus parametrize entries in `test_policy_builder_node_gate.py::test_round_trip_yaml_validates_for_each_mode` (arbitrary terminal names are schema-legal per `fsm/validation/structural_rules.py:1160-1168`); `scripts/tests/js/policy_validator.test.mjs`; `test_policy_builder_corpus.py`; regenerate the golden HTML fixture.

- Docs: `docs/reference/CLI.md:5079-5095` prose at `:5081` (five fixed verbs); `docs/guides/POLICY_ROUTER_GUIDE.md:287-289,355-356` ("can't be deleted and no new outcome can be added") and `:355-361` (Verb Table needs a destination column). (Line numbers re-verified `/ll:verify-issues` 2026-09-16: a new "Failure Routing and Clean-Slate Scoring" subsection inserted earlier in the doc shifted this section by +60 lines from its originally-cited location.)

### Dependent Files (Callers/Importers)
_Wiring pass added by `/ll:wire-issue`:_

- `scripts/little_loops/loops/lib/policy-router.yaml:154` — the `frontmatter_scores` fragment's action body invokes `from little_loops.fsm.frontmatter_scores import main`; a live runtime caller (via a heredoc-invoked subprocess at loop execution time), distinct from `test_frontmatter_scores.py`'s unit-test import. Assert its `context.frontmatter_dimensions` env-passing contract stays unchanged when metadata is present.

### Tests
_Wiring pass added by `/ll:wire-issue`:_

- `scripts/tests/test_fsm_executor.py::TestGeneratedPolicyRouterFailureRouting` (~2810-2917) — loads the real `sample-decision-table.yaml`/`sample-issue-lifecycle.yaml` golden fixtures via `resolve_fragments` and runs them through a live `FSMExecutor`, asserting hardcoded terminal literals (`final_state == "failed"`/`"done"`, `failure_terminal`); must be updated in lockstep with any change to `on_max_steps` routing or terminal names.

- `scripts/tests/test_fsm_fragments.py` (~2408-2454) — pins the `frontmatter_scores` fragment's shell-env contract (`context.frontmatter_dimensions`) in `loops/lib/policy-router.yaml`; assert metadata does not alter the emitted dimension string format.

- `scripts/tests/js/policy_validator.test.mjs:227-236` — `RESERVED_STATE_NAMES` exact sorted-array `deepEqual` assertions will fail as soon as `stopped`/`skipped`/`needs_attention` are added to either mode's set; update the literal arrays.

- `scripts/tests/js/policy_validator.test.mjs:274` — literal `assert.match(yaml, /on_max_steps: failed/)`; update if `on_max_steps` routes to `needs_attention` instead.

- `scripts/tests/js/policy_validator.test.mjs:375-378` — exact-string assertion on `serializeFrontmatterDimensions` output (`"Review Status:string|confidence_score:numeric"`); add a companion case asserting metadata leaves that string unchanged; separately assert generated grading prompts contain the metadata.

- `scripts/tests/fixtures/policy_builder/sample-decision-table.yaml:7` and `sample-issue-lifecycle.yaml:29` — literal `on_max_steps: failed` lines; update alongside the routing change and regenerate.

- No existing test covers the transition-kind `<select>` options list in `policy-router-builder.html.tmpl:420,524` (currently only `rescore`/`goto`/`finish`); add coverage in `test_policy_builder_emit.py` for the new destination entries.

- No existing test covers confidence-gate stamping in `cmd_policy_builder`; add `test_emitted_confidence_gate_matches_config` to `test_policy_builder_emit.py` following the `test_emitted_grammar_matches_canonical` regex-extract-and-compare pattern (`test_policy_builder_emit.py:68-71`), asserting against `BRConfig(Path.cwd()).commands.confidence_gate`.

### Documentation
_Wiring pass added by `/ll:wire-issue`:_

- `docs/guides/POLICY_ROUTER_GUIDE.md:249-256` ("Reserved names" section) — literally enumerates the current `RESERVED_STATE_NAMES` token sets per mode (e.g. "the generated decision-table pipeline uses `score`, `parse_scores`, `policy_dispatch`, and `failed`..."); must be updated alongside the already-listed `:287-289`/`:350-351`/`:355-361` passages.

## Impact

- **Priority**: P3 - richer lifecycle semantics; design decisions resolved 2026-09-16/17

- **Effort**: Medium - new transition kinds, rule-target destinations, dimension metadata, config stamping

- **Risk**: Medium - changes emitted YAML for every mode (`on_max_steps`); all golden `.yaml` fixtures regenerate

- **Breaking Change**: No

## Program Design

### Types

Outcome `transition.kind` gains `"stop" | "skip" | "attention"` alongside existing `"finish"`/`"rescore"`/`"goto"`. Lifecycle rule `target` and `fallback` additionally accept the built-in destination names `stopped` | `skipped` | `needs_attention` (a `LIFECYCLE_DESTINATIONS` constant in core.mjs, distinct from `LIFECYCLE_VERBS`; each is `{name, failure: boolean}`). Dimension entries gain optional `instructions: string` and `anchors: {score: number, meaning: string}[]`. Stamped `__CONFIDENCE_GATE__ {enabled, readiness_threshold, outcome_threshold}` in the template.

### Signatures

- `_outcomeStateLines(outcome, {doneState, issueArg}) -> string[]` (`policy_builder_core.mjs:1071`) — extended so `transition.kind` `stop`/`skip`/`attention` emit `next: stopped`/`next: skipped`/`next: needs_attention`; the terminal blocks themselves are emitted by `_serializeIssueLifecycle` (`:1370`), not here

- `_emittedVerbs(model) -> string[]` (`:1336`) — a companion `_emittedDestinations(model)` returns which of the three built-in destinations are referenced (rule target, fallback, verb transition, `on_max_steps`) so `_serializeIssueLifecycle` can emit route entries and terminal blocks only for those

- `_doneStateName(model) -> string` (`:1117`) — unchanged

- `_scoreActionBody(model) -> string` — emits optional instructions/anchors in rubric and decision-table grading prompts

- `serializeFrontmatterDimensions(model) -> string` and `_serializeDimensions(model) -> string` — unchanged wire formats

- `_checkReservedTokens` / `_checkMissingReferences` / `_assertNoReservedTokens` — accept built-in lifecycle references but reject definitions that shadow generated states

- `cmd_policy_builder(args, logger) -> int` — reads `config.commands.confidence_gate` and stamps it

### Call Path

`serializeLoopYaml` (`policy_builder_core.mjs:1448`) -> `_serializeIssueLifecycle` (`:1370`) -> `_emittedVerbs`/`_emittedDestinations` -> `_outcomeStateLines` (`:1071`) -> terminal-state emission (currently the fixed `done`/`failed` blocks at `:1432-1437`; `on_max_steps: failed` literal at `:1399`). `cmd_policy_builder` -> `BRConfig` -> template stamping; the builder displays thresholds beside rule thresholds.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Update `policy-router-builder.html.tmpl:420,524` — add entries for the new terminal destinations to the transition-kind `<select>` options list (currently only `rescore`/`goto`/`finish`)

- Update `scripts/tests/js/policy_validator.test.mjs:227-236` — extend the `RESERVED_STATE_NAMES` sorted-array assertions with `stopped`/`skipped`/`needs_attention`, per mode

- Update `scripts/tests/js/policy_validator.test.mjs:274` — adjust the `on_max_steps: failed` literal match if routing changes to `needs_attention`

- Update `scripts/tests/js/policy_validator.test.mjs:375-378` — assert metadata leaves the joined string unchanged and appears only in grading prompts

- Update `scripts/tests/test_fsm_executor.py::TestGeneratedPolicyRouterFailureRouting` — adjust hardcoded terminal-literal assertions (`final_state`, `failure_terminal`) to match the new fixture shape

- Update `scripts/tests/fixtures/policy_builder/sample-decision-table.yaml` and `sample-issue-lifecycle.yaml` — update the `on_max_steps` line and regenerate

- Add `test_emitted_confidence_gate_matches_config` to `scripts/tests/test_policy_builder_emit.py` — verify the stamped `confidence_gate` JSON matches `BRConfig(Path.cwd()).commands.confidence_gate`

- Add coverage for the new transition-kind destinations in `scripts/tests/test_policy_builder_emit.py` (no existing test asserts on the `rescore`/`goto`/`finish` `<select>` list)

- Update `docs/guides/POLICY_ROUTER_GUIDE.md:249-256` ("Reserved names" section) — reflect the three new reserved tokens

- Verify `scripts/tests/test_fsm_fragments.py`'s `frontmatter_scores` fragment env-contract assertions to prove `instructions`/`anchors` leave the emitted dimension string format unchanged

## Acceptance Criteria

- [x] Decision questions 1-3 resolved and recorded in this issue before implementation (`/ll:decide-issue` 2026-09-16; questions 4-5 added and resolved in review 2026-09-17).

- [ ] `stopped`, `skipped`, and `needs_attention` each emit YAML that passes `ll-loop validate`, reachable both as a rule target/fallback and as a verb `transition.kind`, covered by fixture pairs in the Node gate.

- [ ] `needs_attention` emits `failure: true`; `stopped`/`skipped` do not. `TestGeneratedPolicyRouterFailureRouting` gains a max-steps case asserting `final_state == "needs_attention"` and `terminated_by == "max_steps"`; it additionally asserts `failure_terminal is True` once BUG-3499 (`depends_on`) has landed (see Proposed Solution §2).

- [ ] For every existing `.model.json` fixture, the regenerated `.yaml` differs from the pre-change golden only by the added or changed `on_max_steps` line and the added terminal blocks (asserted by a diff-shape test, not byte equality).

- [ ] Generated names are reserved per mode. Authored outcomes shadowing them fail both UI validation and serializer guards; valid lifecycle rule/fallback references succeed, unknown references fail, and each referenced terminal is emitted once. Tests cover all three reference mechanisms and every mode.

- [ ] Optional scoring instructions/anchors survive project Save/Open and appear in rubric/decision-table grading prompts. Tests cover invalid/duplicate/out-of-range anchors, boolean anchors, multiline escaping, and absent-metadata prompt compatibility. Lifecycle hides these controls and preserves imported metadata without changing frontmatter extraction or its wire format.

- [ ] Builder displays stamped enabled/readiness/outcome values from `BRConfig`; tests cover disabled gates and confirm saved predicates are not overwritten by stamped thresholds.

- [ ] Transition summaries distinguish successful stop/skip from failed `needs_attention`, including the automatic max-steps route.

- [ ] CLI.md and POLICY_ROUTER_GUIDE.md passages listed above are updated.

## Scope Boundaries

Includes destination semantics, scoring metadata, gate stamping, and their docs. Excludes persistence (ENH-3487), layout/presets (ENH-3491), and runtime policy-router fixes. The one runtime change the chosen semantics require — `failure_terminal` honoring the `failure:` flag for cap-routed finishes — is BUG-3499, now in `depends_on`; this issue does not modify `fsm/executor.py`.

## Verification Notes

Historical observations below describe earlier drafts; the current Proposed Solution and Acceptance Criteria supersede their open-question and preservation-flag language.

_Added by `/ll:verify-issues` — 2026-09-16 (batch run with ENH-3487/ENH-3491):_

Verdict at time of check: **PROPOSAL_UNSOUND** (the citation and Current-Behavior corrections
below were applied in the same pass; the RESERVED_STATE_NAMES gap was not — it needs an
author/implementer decision alongside the three already-open decision questions, not a
mechanical fix, so it remains an outstanding action item).

- **PROPOSAL_UNSOUND finding (check B6)**: BUG-3489 (committed `22f4ff6ed`, landed after this
  issue was captured) added `RESERVED_STATE_NAMES`/`isReservedOutcomeToken`
  (`policy_builder_core.mjs:152-172`) specifically so an authored outcome name, rule target,
  or fallback can never silently collide with a generated state key — its own issue text says
  BUG-3486 must extend this shared map for new generated names rather than define a parallel
  list. This issue's Proposed Solution adds three new generated terminal names
  (`stopped`/`skipped`/`needs_attention`) but never mentions `RESERVED_STATE_NAMES` or the
  guard; implemented as written, an author could name an outcome or rule target
  `needs_attention` (or `stopped`/`skipped`) and it would collide with the generated terminal
  at emission — the exact bug class BUG-3489 just fixed for `done`/`failed`/`error`. Added an
  explicit "also add each new terminal to `RESERVED_STATE_NAMES`" line to the Proposed
  Solution and a matching Acceptance Criterion; the decision questions and implementation
  still need to account for it once `/ll:decide-issue ENH-3492` resolves the exact terminal
  names (the reserved-name entries depend on those exact names).
- **Current Behavior correction**: this issue's claim "`decision_table` ... emits no
  `on_max_steps`" is now false — the same BUG-3489 commit unconditionally added
  `on_max_steps: failed` to `_serializeDecisionTable` (confirmed in
  `scripts/tests/fixtures/policy_builder/sample-decision-table.yaml:7`), with no model flag,
  and the golden fixtures were already regenerated (not kept byte-equal). Corrected in place,
  and Decision Question 3's premise ("existing golden fixtures must stay byte-equal") no
  longer applies to `decision_table` — only to `rubric`, which still emits no `on_max_steps`.
  The remaining open question for `decision_table` narrows to whether its existing `failed`
  terminal should become `needs-attention` instead.
- **Anchor drift (fixed in this pass)**: BUG-3489/BUG-3486 work inserted ~66-70 new lines into
  `policy_builder_core.mjs` ahead of every function this issue cites. Corrected:
  `_serializeIssueLifecycle` (`974-1041`→`1052-1122`), its `on_max_steps: failed`
  (`1002`→`1081`), per-verb `on_error: failed` (`1031`→`1111`), `done`/`failed` terminals
  (`1034-1039`→`1114-1120`); `_serializeDecisionTable` (`741-833`→`807-910`); `_serializeRubric`
  (`834-909`→`912-987`); `_outcomeStateLines`/`_doneStateName` (`687-739`→`753-805`);
  `serializeFrontmatterDimensions` (`925`→`1003`). `context_seed.py:68`,
  `check_readiness.py:78-115`, `cli/artifact/policy_builder.py:56-107`, and
  `config/automation.py:155-170` (all unmodified files) were re-verified and remain accurate.
- **Citation error (unrelated to the drift above, fixed in this pass)**:
  `fsm/validation/structural_rules.py:26-35` (cited for "arbitrary terminal names are
  schema-legal") is an import block, not a terminal-name check, in both the working tree and
  HEAD before BUG-3489 — the citation was simply wrong. The actual check is
  `validate_fsm`'s "at least one terminal state" logic (no name constraint) at
  `structural_rules.py:1160-1168`; corrected in place.
- `docs/guides/POLICY_ROUTER_GUIDE.md` also shifted +60 lines (new "Failure Routing and
  Clean-Slate Scoring" subsection inserted ahead of "Visual Builder"): `227-229,290-291`→
  `287-289,350-351`, `295-301`→`355-361`; corrected in place. `docs/reference/CLI.md:5079-5095`
  (unmodified) re-verified accurate.
- Dependency backlink (fixed in this pass): this issue's `depends_on: BUG-3486` had no
  matching entry in `BUG-3486`'s `blocks:` list. Added `ENH-3491`/`ENH-3492` to `BUG-3486`'s
  `blocks:`. This issue's own `blocked_by: [ENH-3491]` already has a correct backlink now that
  `ENH-3491` declares `blocks: [ENH-3492]`.
- `ll-verify-evidence --json`: `"ok": true`, 0 findings.
- Decisions log query (`ll-issues decisions list --type rule --enforcement required
  --active-only`) returned no entries.
- `decision_needed: true` remains correct — Acceptance Criterion 1 explicitly requires the
  three decision questions resolved before implementation; that gate is unaffected by the
  findings above (it gains a fourth de-facto sub-question: reserved-name registration for
  whatever terminal names the decision settles on).

_Manual review — 2026-09-17:_

- `depends_on: BUG-3486` is satisfied (status `done`); BUG-3489 is also `done`.
- Anchor drift from commit `8faffee5a` (post-dates the last verify pass) corrected in place: `_serializeIssueLifecycle` `1052-1122`→`1370-1440`, its `on_max_steps` literal `1081`→`1399`, `done`/`failed` terminals `1114-1120`→`1432-1437`, `_outcomeStateLines`/`_doneStateName` `753-805`→`1071-1123`, `serializeFrontmatterDimensions` `1003`→`1321`, `RESERVED_STATE_NAMES`/`isReservedOutcomeToken` `152-172`→`157-186`, `serializeLoopYaml`→`1448`. `_serializeDecisionTable` is now `1125` and `_serializeRubric` `1230`. `policy_validator.test.mjs` anchors: `RESERVED_STATE_NAMES` assertions `231-243`, `on_max_steps: failed` match `282`.
- Resolved three gaps: (1) Expected Behavior/AC contradicted decisions 2-3 on byte-identical fixtures; (2) the failure flag on new terminals was undefined; (3) "rule routes to destination" vs "`transition.kind`" were two different mechanisms — both are now in scope with one shared terminal set.
- `_outcomeStateLines` signature corrected (takes an outcome, not the model).

_Third `/ll:verify-issues` pass — 2026-09-17 (batch run with ENH-3487/ENH-3491/FEAT-3488):_

Verdict at time of check: **OUTDATED** (corrections below applied in the same pass, so
the issue as it now reads is up to date — this section is a record of what was wrong and
fixed, not an outstanding action item).

- Commit `25e39fb1d` (BUG-3490, "resolve installed plugin content root for skill/command
  discovery", 2026-09-17T00:12:13) rewrote `policy_builder.py` between the prior verify
  pass and this one, shifting the `cmd_policy_builder` citation in Current Behavior
  (`56-107`→`61-112`). No substance change: it still stamps only theme/CSS/grammar/catalog,
  still doesn't read `config.commands.confidence_gate` — the proposed gate-stamping addition
  is unaffected.
- `FSMExecutor._finish` line `4337` (the `failure_terminal` gate this issue's §2 runtime
  prerequisite depends on) re-confirmed by direct read — `terminated_by == "terminal"`
  precondition is exactly as cited; BUG-3499 remains open (untracked, not yet committed),
  so `depends_on: BUG-3499` is still accurate and unresolved.
- Doc citation correction (unrelated to the `25e39fb1d` commit, which touched
  `docs/reference/CLI.md:3757`/`docs/reference/API.md:11912` only — both above this issue's
  cited ranges with no net line-count change before line 5079): the Integration Map's second
  citation for "can't be deleted and no new outcome can be added" (`350-351`) pointed at
  unrelated custom-field-type prose; the phrase is actually at `docs/guides/
  POLICY_ROUTER_GUIDE.md:355-356`. Corrected in place; the companion `:355-361` citation
  (Verb Table) was already accurate.
- `policy_builder_core.mjs`/`policy-router-builder.html.tmpl` anchors (all cited in Program
  Design) unaffected by `25e39fb1d`; re-confirmed unchanged since the prior pass's
  post-`8faffee5a` correction.
- Dependency backlinks checked directly: `blocked_by: [ENH-3491]` / `ENH-3491.blocks:
  [ENH-3492]` match; `depends_on: [BUG-3486, BUG-3499]` — BUG-3486 done with a matching
  `blocks:` backlink, BUG-3499 open (no backlink needed pending completion); `blocks:
  [FEAT-3488]` / `FEAT-3488.blocked_by` includes `ENH-3492` — consistent. No DEP_ISSUES
  findings.
- `ll-verify-evidence --json`: `"ok": true`, 0 findings.
- Decisions log query returned no entries.
- Proposal-vs-code consequence check (B6): no new issue found.

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-09-17_

**Readiness Score**: 80/100 → STOP — ADDRESS GAPS (dependencies hard override)
**Outcome Confidence**: 75/100 → MODERATE

### Gaps to Address
- `blocked_by: ENH-3491` is unresolved (status `Open`, not `done`/`cancelled`) — the BUG-3051 Dependencies Hard Override forces this verdict regardless of the otherwise-80/100 aggregate. Wait for ENH-3491 to land, or drop it from `blocked_by` if the layout/preset work it depends on is no longer a prerequisite.

## Status

**Open** | Created: 2026-09-16 | Priority: P3

## Session Log
- `/ll:verify-issues` - 2026-09-17T06:28:31 - `9b9f3eca-ed5d-4fd7-a99d-217cb278def3.jsonl`
- manual review - 2026-09-17 - executor probe showed cap-routed `failure_terminal` is False; filed BUG-3499 and added to `depends_on`; max-steps AC asserts `terminated_by` now, `failure_terminal` after BUG-3499; rubric `on_max_steps` is an added line in the diff-shape AC
- manual review - 2026-09-17 - resolved terminal-reference reservation contradiction; moved scoring metadata to grading prompts; fixed project-round-trip criteria; preserved wire protocols; clarified gate display and terminal summaries
- manual review - 2026-09-17 - resolved byte-identical contradiction, defined failure flags and rule-target vs transition mechanisms, corrected anchors post-8faffee5a
- `/ll:verify-issues` - 2026-09-17T02:36:59 - `ed6d999b-26a2-4d77-bbbf-604f7482188a.jsonl`
- `/ll:wire-issue` - 2026-09-17T02:03:58 - `5caaeb95-8e3b-4dc5-9258-679a7e06d4cd.jsonl`
- `/ll:decide-issue` - 2026-09-17T01:33:55 - `be9c9d04-b7b3-40fa-a6b2-8aa383887a4c.jsonl`
- `/ll:verify-issues` - 2026-09-17T01:18:51 - `716b78b0-d53f-401a-997f-791cc3ac58be.jsonl`
- `/ll:audit-issue-conflicts` - 2026-09-16T23:13:05 - `e4d4d311-3a45-427a-958f-7960765e8da2.jsonl`
