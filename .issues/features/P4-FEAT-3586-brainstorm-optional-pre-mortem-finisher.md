---
id: FEAT-3586
type: FEAT
title: Brainstorm optional pre-mortem finisher
priority: P4
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-25'
captured_at: '2026-09-25T00:33:14Z'
parent: EPIC-3581
labels:
- loops
- brainstorm
- captured
blocked_by:
- FEAT-3582
- FEAT-3583
reconcile_attempted: true
confidence_score: 75
outcome_confidence: 82
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 25
---

# FEAT-3586: Brainstorm optional pre-mortem finisher

## Summary

Add an optional, **annotate-only** `premortem` finisher (approach D from EPIC-3581): a critic
attacks the portfolio **winner and runner-up** (not the wildcard), a defender attaches
mitigations, and the report ships each with its known risks and kill criteria. The idea
`title`/`body`, the ranking, the portfolio slots, and `winners.md` are never changed.

_Scope reduced 2026-09-29 (EPIC-3581 second review, `/ll:advise` with Opus): v1 has **no demotion, promotion, or concession**. See Review Decisions._

## Current Behavior

Brainstorm ships the tournament winner as-is: no step challenges it, and the report carries no known risks or kill criteria.

## Expected Behavior

- Enabled per profile (`functional`, `business` default on) or via `premortem=true`; a false gate routes straight past the finisher with `brainstorm.md`/`winners.md`/`portfolio.json` byte-identical to the no-finisher output.
- **One critic call** covers the winner and the runner-up (both ideas in one prompt): per idea, the top failure modes ("it's 12 months later and this failed because…"), each `{failure_mode, severity: fatal | major | minor, kill_criterion}`. **One defender call** then attaches a `mitigation` string per risk, or leaves it `null`. Mitigations are annotations only — the idea's `title`/`body` are immutable, so the shipped idea is the one that was grounded, rendered, and ranked.
- A script (`annotate`) validates both outputs against the schema, writes `${context.run_dir}/premortem.json` (`{idea_id: [Risk]}`), and adds `unmitigated_fatal` to `portfolio.json` `flags[idea_id]` when any `fatal` risk has `mitigation: null`. That flag is a **report signal, not a gate**: the idea keeps its slot and still reaches sinks.
- The report gains a `Risks & Kill Criteria` section for the winner and the runner-up, marks any `unmitigated_fatal` idea prominently, and states that the wildcard was not critiqued.
- **Fails open**: unparseable critic/defender output, unknown idea IDs, or a defender risk list whose failure modes do not match the critic's skips the annotation, logs to `premortem.log`, adds `premortem_skipped` to the winner's `flags`, and the run continues. Malformed premortem output never drops or alters an idea and never fails the run. A defender output carrying a revised `title`/`body` is rejected the same way (fail-open skip, not a crash).

## Use Case

**Who**: A little-loops user brainstorming a functional design or business opportunity whose winner they may act on.

**Context**: The tournament winner has never been attacked; its weaknesses surface only after work starts.

**Goal**: Have the top two ideas critiqued and defended before they ship in the report.

**Outcome**: The winner and runner-up each appear with a `Risks & Kill Criteria` section; an idea with an unmitigated fatal risk is flagged, not removed.

## Motivation

EPIC-3581 approach D adds an adversarial pre-mortem to reduce false confidence in the winner. Shipping risks and kill criteria alongside each idea makes the report actionable. Demotion was cut from v1: the defender is the same model as the critic and supplies a mitigation for almost every risk, so a "fatal risk with no mitigation" concession rule would rarely fire while adding nullable-winner, `conceded`, and slot-recompute complexity to the P2 core (FEAT-3582) before the finisher has proven itself.

## Proposed Solution

Add an optional `premortem` finisher to `scripts/little_loops/loops/brainstorm.yaml`, after `portfolio` and before `validate_portfolio`:

- No separate gate state (2026-09-29): the `portfolio` engine command prints `premortem` or `render` as its last stdout line from the resolved profile (or `fail`), and `portfolio` routes on it (`evaluate: classify` with both happy tokens listed explicitly and `_: finalize_failed` — a default that reached `validate_portfolio` would break classify safety; `render` routes to `render_report`). A disabled finisher costs **zero** parent steps.
- `premortem_critic` (LLM, one call, winner + runner-up) → `premortem_defender` (LLM, one call) → `annotate` (script: engine command `annotate`). Total **3 parent steps** (critic, defender, `annotate`; the gate is folded into `portfolio`); no rounds, no counter, no `premortem_rounds`, no `retry_counter`, no per-run counter file.
- `annotate` is a command of `little_loops.brainstorm_engine` (FEAT-3582 § Solution): it reads the two LLM outputs from files, validates the schema and idea-body immutability, writes `premortem.json`, updates `portfolio.json` `flags`, and never touches `winners.md`, `ideas.jsonl` idea rows, `ranking`, or slots.
- Report rendering adds the `Risks & Kill Criteria` section from `premortem.json`.

**Out of scope (follow-up candidate):** demotion/promotion of conceded ideas, `winner: null`, and an all-conceded outcome. If added later it must use a concession signal that does not come from the defender (e.g. a rebuttal call where the critic rates each fatal-risk mitigation `holds` or `fails`, script concedes on `fails`), define a "round" as one critic+defender pass over the whole critiqued set, and re-introduce `conceded`/nullable `winner` in FEAT-3582's Data Contract in the same change.

## Program Design

### Types

- `Risk`: `{failure_mode: str, severity: "fatal" | "major" | "minor", kill_criterion: str, mitigation: str | null}`
- `Premortem`: `{idea_id: [Risk]}` — written to `premortem.json`; no field may carry a revised idea body

### Signatures

All in `scripts/little_loops/brainstorm_engine.py` (FEAT-3582), invoked as `python3 -m little_loops.brainstorm_engine annotate --run-dir DIR`:

- `annotate(portfolio: dict, critic_out: str, defender_out: str, ideas: list[IdeaRecord]) -> tuple[dict, Premortem | None]` — validates and merges; returns the updated `flags` and the `Premortem`, or `None` on fail-open skip
- `render_risks(premortem: Premortem, ideas: list[IdeaRecord]) -> str` — the `Risks & Kill Criteria` report section

`critique` and `defend` are LLM states (`premortem_critic`, `premortem_defender`), not functions.

### Call Path

`portfolio` -> (token `premortem`) `premortem_critic` -> `premortem_defender` -> `annotate` -> `render_report` -> `validate_portfolio` -> `route_sink`

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/brainstorm.yaml` — add `premortem_critic`, `premortem_defender`, and the `annotate` module call between `portfolio` and `render_report` (no gate state: `portfolio` prints the routing token); report sections come from `render-report` reading `premortem.json` (FEAT-3667 owns `brainstorm.md`)
- `scripts/little_loops/brainstorm_engine.py` — `annotate`, `render_risks` (module created by FEAT-3582)
- `scripts/little_loops/fsm/fence.py` — `FENCE_ROLES` entries for `premortem_critic`/`premortem_defender` (interpolate `${context.brief}`)
- `scripts/tests/data/loop_interpolation_baseline.json` — new shell-state sites, if any

### Dependent Files (Callers/Importers)
- `ll-loop run brainstorm` callers and the sink adapters (`route_sink`, `sink_file`, `sink_issue`, `sink_decision`) inside the loop — unaffected: `winners.md` is unchanged
- FEAT-3583 — supplies the resolved `premortem` value and the `premortem` context override

### Similar Patterns
- `route_sink` in `brainstorm.yaml` — the gated-routing pattern (here folded into `portfolio`'s stdout token)

### Tests
- `scripts/tests/test_brainstorm_engine.py` — direct unit tests of `annotate`/`render_risks`: valid critic+defender output → `premortem.json` + `unmitigated_fatal` flag; fatal risk with a mitigation → no flag; malformed / unknown-id / mismatched-risk / revised-body output → fail-open skip with `premortem_skipped`; `winners.md`, `ranking`, and slots untouched; wildcard not critiqued
- `scripts/tests/test_brainstorm.py` — wiring: gate routes past when `premortem` is false (output byte-identical), and through critic → defender → `annotate` when true; `annotate` precedes `validate_portfolio`
- `scripts/tests/test_builtin_loops.py` — built-in loop validation; `TestValidatorWarningBudget`

### Documentation
- `scripts/little_loops/loops/README.md`, `docs/guides/LOOPS_GUIDE.md`, `docs/guides/LOOPS_REFERENCE.md` — brainstorm loop descriptions

### Configuration
- Context key: `premortem` (resolved from profile; FEAT-3583 override, default `""`). No `premortem_rounds`.
- Step budget: +3 parent steps when enabled (critic, defender, `annotate`); +0 when disabled. Owned by FEAT-3596's combined budget.

### Codebase Research Findings

_Carried from `/ll:refine-issue` — 2026-09-25, edited 2026-09-29 for the annotate-only scope:_

- `tournament` and `portfolio` do not exist in `brainstorm.yaml` yet — FEAT-3582 dependency. Insertion point is between `portfolio` and `validate_portfolio`, so no sink runs before the finisher.
- Winners live in `winners.md` (JSON lines with `text`/`rationale`); this finisher never rewrites it.
- ~~Per-run round counter (`mechanize-skills.yaml` `diagnosis_retry`), `_validate_zero_retry_counter`, `retry_counter` scope constraint~~ — no longer relevant: there is no counter.
- `scripts/tests/test_brainstorm.py::TestBrainstormYaml::test_max_steps_is_60` pins `max_steps == 60`; the combined budget with this finisher is FEAT-3596's.

## Implementation Steps

1. Add `premortem_critic`, `premortem_defender` between `portfolio` and `render_report` (blocked by FEAT-3582/FEAT-3583); a `render` token from `portfolio` routes straight past the finisher (`render_report` → `validate_portfolio`).
2. Implement `annotate` and `render_risks` in `brainstorm_engine.py` with unit tests first (TDD): schema validation, immutability check, fail-open, `unmitigated_fatal` flag.
3. Extend `render-report` (FEAT-3667) to add `Risks & Kill Criteria` for the winner and runner-up when `premortem.json` exists; output unchanged when it does not.
4. Add `FENCE_ROLES` entries; run `ll-loop validate brainstorm`.

## Impact

- **Priority**: P4 - optional finisher that refines output but is not needed for a working engine
- **Effort**: Small - two LLM states and one small, unit-tested engine command
- **Risk**: Low - off by default for `artifact`/`visual`; annotate-only, fails open, cannot alter an idea or a ranking
- **Breaking Change**: No

## Acceptance Criteria

- Exactly two LLM calls (critic, defender) when enabled; no rounds, no counter.
- The shipped idea's `title`/`body`, `ranking`, portfolio slots, and `winners.md` are byte-identical with and without the finisher; only `portfolio.json` `flags`, `premortem.json`, and the report differ.
- `Risks & Kill Criteria` appears for the winner and runner-up; the wildcard is stated as not critiqued.
- A `fatal` risk with `mitigation: null` adds `unmitigated_fatal` to that idea's `flags` and is highlighted in the report; the idea still reaches sinks.
- Malformed, unknown-id, mismatched, or revised-body critic/defender output fails open (`premortem_skipped`, `premortem.log`) and never fails the run.
- Skipped cleanly when disabled; no change to output shape otherwise.
- **Lands with its own enablement (2026-09-30):** in the same change, widen FEAT-3667's `BUILT_CAPABILITIES` to allow `premortem=true`, flip the `functional` and `business` preset knob to `true` (FEAT-3583 § Shipped vs target), extend the profile-token wiring test, and bump `max_steps` by this finisher's own cost (+3 when enabled) instead of leaving it to FEAT-3596.
- The critic gets the winner/runner-up bodies by a pinned mechanism: either an engine block captured by one extra shell state (+1 step, then 4 parent steps) or `Read` access to `portfolio.json`/`ideas.jsonl` under the loop `scope:` (0 extra); the choice and the resulting step cost are recorded here when implemented (FEAT-3582 § Program Design → LLM-state pairing).

## Review Decisions

_Added 2026-09-28 (EPIC-3581 sub-issue review):_

- Pinned critiqued set: winner + runner-up (wildcard is not critiqued).
- Priority stays P4, but FEAT-3596 no longer hard-blocks on this issue (see FEAT-3596).

_Added 2026-09-29 (EPIC-3581 second review, `/ll:advise` with Opus; nothing here has been measured):_

- **Annotate-only for v1.** Removed demotion/promotion, script-determined concession, `conceded`, `winner: null`, the all-conceded outcome, the sink-skip branch, and `premortem_rounds`. A same-model defender supplies a mitigation for almost every risk, so "fatal with no mitigation" would rarely concede; a P4 optional feature should not add nullable-winner complexity to the P2 core. FEAT-3582 dropped the matching Data Contract fields (its Review Decisions 23–24).
- Replaced the round-bounded critic/defender loop with one critic call and one defender call over both critiqued ideas (4 parent steps including the gate). This also removes the per-run counter, the `retry_counter` hazard, and the missing executable counter test.
- `annotate` is an engine-module command, not an inline script.
- _2026-09-29 third review:_ **resolved** the two Confidence Check concerns — `render-report` (FEAT-3667) is the sole renderer and reads `premortem.json`; the critic/defender match rule is **by index and exact `failure_mode` string after whitespace/case normalization** (a mismatch in count, order or text is a fail-open skip). Stale "4 parent steps including the gate" wording removed: **3 parent steps**, gate folded into `portfolio`. Both prompt states declare `next:` + `on_error:` (no hidden evaluator call).
- The prior Confidence Check scores (75 / 64) were for the demotion design and are void; re-run `/ll:confidence-check` after FEAT-3582/FEAT-3583 land.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-25 | Priority: P4

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-09-29 (first score against the annotate-only design)_

**Readiness Score**: 75/100 → STOP — ADDRESS GAPS (dependency hard override)
**Outcome Confidence**: 82/100 → HIGH CONFIDENCE

### Gaps to Address
- Unresolved dependencies (hard override): `blocked_by` FEAT-3582 and FEAT-3583 are both `Open`. Implement them first, or drop the dependency if it no longer applies. The rest of the issue is otherwise ready.

### Concerns
- The state that renders `brainstorm.md` is not named. Steps say "extend report rendering" and `render_risks` returns a section string, but the caller is left open. Pin which FEAT-3582 state (`portfolio` or `finalize_done`) calls it.
- "A defender risk list whose failure modes do not match the critic's" has no stated match rule (exact string, normalized, or by index). Pin it so the fail-open test is deterministic.
- `annotate` needs `portfolio.json`, `ideas.jsonl`, and the engine module, none of which exist yet. Signatures are pinned only against FEAT-3582's spec, so recheck them once FEAT-3582 lands.

## Session Log
- `/ll:confidence-check` - 2026-09-29T06:02:10 - `1e4b6b11-acbb-4e78-b169-131d9cd93116.jsonl`
- `/ll:confidence-check` - 2026-09-29T02:00:48 - `c90c2478-f308-49d4-930c-8be0a9590776.jsonl`
- `/ll:confidence-check` - 2026-09-25T17:21:40 - `823eec8e-b4aa-4134-9728-fb6281ade224.jsonl`
- `/ll:reconcile-issue` - 2026-09-25T17:15:35 - `fa11583b-aa00-4da8-b0f0-fc89c6cf8f64.jsonl`
- `/ll:wire-issue` - 2026-09-25T02:07:46 - `6e813375-6da8-496a-a222-6bd92b308c4c.jsonl`
- `/ll:refine-issue` - 2026-09-25T01:46:43 - `2ac59930-bb65-4013-a3d3-8f842b856fd9.jsonl`
- `/ll:format-issue` - 2026-09-25T01:01:32 - `825370f4-2bf5-4bb8-a770-49c1a90d8b61.jsonl`
- `/ll:capture-issue` - 2026-09-25T00:33:52 - `ba660a81-2414-4092-808d-95f51543dbb1.jsonl`
