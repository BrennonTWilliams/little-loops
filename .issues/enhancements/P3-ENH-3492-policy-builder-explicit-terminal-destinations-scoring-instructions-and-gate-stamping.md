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
relates_to:
- ENH-3487
- ENH-3491
- BUG-3489
- FEAT-3474
blocked_by:
- ENH-3491
---

# ENH-3492: Policy builder explicit terminal destinations, scoring instructions, and gate stamping

## Summary

Add explicit stop-success, skip, and needs-attention terminal destinations to lifecycle policies, optional per-dimension scoring instructions and score anchors, and stamp the project's confidence-gate thresholds into the builder. Split out of ENH-3487 (workstream c: emitted-YAML semantics). Needs a design decision before implementation.

## Current Behavior

The builder emits a binary terminal model, differing by mode:
- `issue_lifecycle` (`_serializeIssueLifecycle`, `scripts/little_loops/templates/policy_builder_core.mjs:1052-1122`) hardcodes `on_max_steps: failed` (`:1081`), every verb state carries `on_error: failed` (`:1111`), and only `done`/`failed` terminals are emitted (`:1114-1120`).
- `decision_table` (`_serializeDecisionTable`, `:807-910`) now unconditionally emits `on_max_steps: failed` (added by the BUG-3489 fix, committed `22f4ff6ed`; see `scripts/tests/fixtures/policy_builder/sample-decision-table.yaml:7`) — no model flag, and existing golden fixtures were regenerated (not kept byte-equal) as part of that change.
- `rubric` (`_serializeRubric`, `:912-987`) has a single `done` terminal and no `on_max_steps`.
No `stop-success`, `skip`, or `needs-attention` concept exists anywhere in the builder. Rubric dimensions have no score definitions. `cmd_policy_builder` (`scripts/little_loops/cli/artifact/policy_builder.py:56-107`) stamps only theme, CSS vars, grammar spec, and catalog; lifecycle defaults hardcode a confidence threshold. `ConfidenceGateConfig` (`scripts/little_loops/config/automation.py:155-170`) is unread by this command.

## Expected Behavior

Lifecycle rules can route to stop-success, skip, and needs-attention destinations, each emitting a valid loop. Reopening existing five-verb models preserves their behavior byte-for-byte. Dimensions accept optional scoring instructions and score anchors that appear in emitted prompts. The builder displays the project's configured readiness/outcome thresholds alongside rule thresholds.

## Proposed Solution

Decided (per `/ll:decide-issue ENH-3492`; see `### Decision Rationale` below):
1. **Decided**: `stop-success` is a distinct terminal state `stopped` (with `terminal: true`), not an alias for `done` — so postmortems can tell "finished the pipeline" from "rule said stop here".
2. **Decided**: `skip` and `needs-attention` are rule-selectable destinations only (never automatic); `on_error` stays `failed`; `on_max_steps` becomes `needs-attention` for lifecycle.
3. **Decided**: both `decision_table` and `rubric` gain a `needs-attention` `on_max_steps` terminal (matching lifecycle's treatment), unchanged otherwise. **Partly overtaken by BUG-3489** (committed `22f4ff6ed`, found by `/ll:verify-issues` 2026-09-16): `decision_table` now unconditionally emits `on_max_steps: failed` (no model flag, golden fixtures already regenerated) — the byte-equal-preservation premise no longer holds for `decision_table`, only for `rubric`'s new addition (see Decision Rationale).

Then:
- Extend `LIFECYCLE_VERBS`/outcome transition kinds in core.mjs with the new destinations; `_outcomeStateLines`/`_doneStateName` (`:753-805`) route to them. Backward-compatible defaults for models lacking the new fields. **Also add each new generated terminal name (`stopped`/`skipped`/`needs_attention`, exact names per the decision above) to `RESERVED_STATE_NAMES`/`isReservedOutcomeToken` (`policy_builder_core.mjs:152-172`)** — BUG-3489 (committed `22f4ff6ed`) established this guard specifically so a user-authored outcome name, rule target, or fallback can never collide with a generated state key, and its own issue text says BUG-3486 (and, by the same logic, this issue) must extend the shared map rather than leave new generated terminals unregistered; skipping this reintroduces the exact silent-collision bug class BUG-3489 just fixed, for the three terminal names this issue adds.
- Add optional `instructions`/`anchors` to dimension entries; `serializeFrontmatterDimensions` (`:1003`) emits them into prompts. Touch `scripts/little_loops/fsm/frontmatter_scores.py` (`encode_frontmatter_scores` mirrors `normalizeDimName` rules) only if `BUILTIN_FRONTMATTER_DIMENSIONS` shape changes, and extend `conformance_corpus.json` accordingly.
- In `cmd_policy_builder` read `config.commands.confidence_gate` off the already-built `BRConfig` (mirror `scripts/little_loops/fsm/context_seed.py:68`; do not copy `cli/issues/check_readiness.py:78-115`'s raw-JSON bypass) and stamp `readiness_threshold`/`outcome_threshold`. No `config-schema.json` change needed (`confidence_gate` defined at `:509`).

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-09-16.

**Selected**: distinct `stopped` terminal; rule-selectable `skip`/`needs-attention`; `needs-attention` `on_max_steps` for both `decision_table` and `rubric`.

**Reasoning**: Each of the three questions already carried the issue author's own stated recommendation with no competing alternative under active consideration, so no codebase-evidence scoring pass was needed — `/ll:decide-issue` converted the provisional "Recommendation:" wrappers into decided, declarative statements (Phase 3b Pattern D lock-in). A distinct `stopped` terminal keeps postmortems able to distinguish "pipeline finished" from "rule said stop"; making `skip`/`needs-attention` rule-selectable-only (never automatic) keeps `on_error`/`on_max_steps` semantics unambiguous; and routing both `decision_table` and `rubric` `on_max_steps` to `needs-attention` keeps all three serialization modes consistent now that BUG-3489 already moved `decision_table` off byte-equal preservation.

**Key evidence**:
- Terminal naming: BUG-3489 (`22f4ff6ed`) already added `RESERVED_STATE_NAMES`/`isReservedOutcomeToken` (`policy_builder_core.mjs:152-172`) as the collision guard this issue's new terminals must extend — no alternative naming scheme was proposed.
- Byte-equal scope: `decision_table`'s golden fixtures were already regenerated by BUG-3489 (`scripts/tests/fixtures/policy_builder/sample-decision-table.yaml:7`), so only `rubric`'s new `on_max_steps` addition still needs the preservation flag; this was the issue's own verification-pass finding, not a competing option.

## Integration Map

- Files: `policy_builder_core.mjs`, `policy-router-builder.html.tmpl`, `cli/artifact/policy_builder.py`, possibly `fsm/frontmatter_scores.py`.
- Tests: new `.model.json`/`.yaml` fixture pairs under `scripts/tests/fixtures/policy_builder/` for each new destination plus parametrize entries in `test_policy_builder_node_gate.py::test_round_trip_yaml_validates_for_each_mode` (arbitrary terminal names are schema-legal per `fsm/validation/structural_rules.py:1160-1168`); `scripts/tests/js/policy_validator.test.mjs`; `test_policy_builder_corpus.py`; regenerate the golden HTML fixture.
- Docs: `docs/reference/CLI.md:5079-5095` prose at `:5081` (five fixed verbs); `docs/guides/POLICY_ROUTER_GUIDE.md:287-289,350-351` ("can't be deleted and no new outcome can be added") and `:355-361` (Verb Table needs a destination column). (Line numbers re-verified `/ll:verify-issues` 2026-09-16: a new "Failure Routing and Clean-Slate Scoring" subsection inserted earlier in the doc shifted this section by +60 lines from its originally-cited location.)

## Impact

- **Priority**: P3 - richer lifecycle semantics; blocked on a design decision
- **Effort**: Medium - new transition kinds, dimension metadata, config stamping
- **Risk**: Medium - changes emitted YAML; existing fixtures must stay byte-identical
- **Breaking Change**: No

## Program Design

### Types

Outcome `transition.kind` gains `"stop" | "skip" | "attention"` alongside existing `"finish"`/verb targets. Dimension entries gain optional `instructions: string` and `anchors: {score: number, meaning: string}[]`. Stamped `__CONFIDENCE_GATE__ {readiness_threshold, outcome_threshold}` in the template.

### Signatures

- `_outcomeStateLines(model) -> string[]` — extended to emit `stopped`, `skipped`, `needs_attention` terminals (exact names per the decision above)
- `_doneStateName(model) -> string` — unchanged for `finish`; returns the new terminal for `stop`
- `serializeFrontmatterDimensions(model) -> string` — emits `instructions`/`anchors` into the grading prompt when present
- `cmd_policy_builder(args, logger) -> int` — reads `config.commands.confidence_gate` and stamps it

### Call Path

`serializeLoopYaml` -> `_serializeIssueLifecycle` -> `_outcomeStateLines` -> terminal-state emission. `cmd_policy_builder` -> `BRConfig` -> template stamping; the builder displays thresholds beside rule thresholds.

## Acceptance Criteria

- [ ] Decision questions 1-3 resolved and recorded in this issue before implementation.
- [ ] Stop-success, skip, and needs-attention destinations each emit YAML that passes `ll-loop validate`, covered by fixture pairs in the Node gate.
- [ ] Existing `.model.json` fixtures serialize byte-identically (no behavior change for five-verb models).
- [ ] Every new generated terminal name (`stopped`/`skipped`/`needs_attention`) is added to `RESERVED_STATE_NAMES` so an authored outcome, rule target, or fallback colliding with it is rejected before emission, exactly like the existing `done`/`failed`/`error` protections (BUG-3489).
- [ ] Optional scoring instructions and anchors appear in emitted prompts and survive `serializeLoopYaml` round trips; unit-tested in `node:test`.
- [ ] Builder displays stamped readiness/outcome thresholds; `test_policy_builder_emit.py` asserts they are read from `BRConfig`.
- [ ] CLI.md and POLICY_ROUTER_GUIDE.md passages listed above are updated.

## Scope Boundaries

Includes destination semantics, scoring metadata, gate stamping, and their docs. Excludes persistence (ENH-3487), layout/presets (ENH-3491), runtime policy-router fixes (see the related runtime issue in frontmatter). If the chosen semantics change how the runtime treats terminal outcomes, promote that related issue to `depends_on`.

## Verification Notes

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

## Status

**Open** | Created: 2026-09-16 | Priority: P3


## Session Log
- `/ll:decide-issue` - 2026-09-17T01:33:55 - `be9c9d04-b7b3-40fa-a6b2-8aa383887a4c.jsonl`
- `/ll:verify-issues` - 2026-09-17T01:18:51 - `716b78b0-d53f-401a-997f-791cc3ac58be.jsonl`
- `/ll:audit-issue-conflicts` - 2026-09-16T23:13:05 - `e4d4d311-3a45-427a-958f-7960765e8da2.jsonl`
