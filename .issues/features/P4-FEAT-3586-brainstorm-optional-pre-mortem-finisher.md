---
id: FEAT-3586
type: FEAT
title: Brainstorm optional pre-mortem finisher
priority: P4
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-25'
captured_at: '2026-09-25T00:33:14Z'
parent: EPIC-3687
labels:
- loops
- brainstorm
- captured
blocked_by:
- FEAT-3582
- FEAT-3583
- FEAT-3667
reconcile_attempted: true
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

- Enabled per profile (`functional`, `business` default on) or via `premortem=true`; a false gate routes straight to render_report with no extra visits and no finisher artifacts/flags. Rendered output, winners.md and portfolio data are byte-identical to the no-finisher path.
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
- `premortem_critic` (LLM, one call, winner + runner-up) → `premortem_defender` (LLM, one call) → `annotate` (script: engine command `annotate`). Total **3 successful-path parent visits** (critic, defender, `annotate`; the gate is folded into `portfolio`); no rounds, no counter, no `premortem_rounds`, no `retry_counter`, no per-run counter file.
- `annotate` is a command of `little_loops.brainstorm_engine` (FEAT-3582 § Solution): it reads the two LLM outputs from files, validates the schema and idea-body immutability, writes `premortem.json`, updates `portfolio.json` `flags`, and never touches `winners.md`, `ideas.jsonl` idea rows, `ranking`, or slots.
- Read-only means explicit Read tool declarations where the host supports them, plus prompt instructions; the executor has no per-state filesystem jail and some hosts ignore tool allowlists with a warning. In this feature's enablement change, extend the existing portfolio command to publish premortem_input.json before emitting the premortem token. It pins canonical ideas/profile, the current judging-input digest, immutable ranked portfolio fields/unrelated flags and winners.md. Create once and verify on replay before replacing any portfolio/finisher input; do not re-snapshot after a resumed prompt. Annotate verifies that persisted digest before annotation and on fixed-error skip paths. Actual canonical-file mutation is an integrity failure; a revised body merely present in model output is still a fail-open schema skip. Record unsupported tool-scope limitations honestly. This capability-gated extension adds no state/call and creates no finisher artifact when disabled.
- Report rendering adds the `Risks & Kill Criteria` section from `premortem.json`.

**Out of scope (follow-up candidate):** demotion/promotion of conceded ideas, `winner: null`, and an all-conceded outcome. If added later it must use a concession signal that does not come from the defender (e.g. a rebuttal call where the critic rates each fatal-risk mitigation `holds` or `fails`, script concedes on `fails`), define a "round" as one critic+defender pass over the whole critiqued set, and re-introduce `conceded`/nullable `winner` in FEAT-3582's Data Contract in the same change.

## Program Design

### Types

- `Risk`: `{failure_mode: str, severity: "fatal" | "major" | "minor", kill_criterion: str, mitigation: str | null}`
- `Premortem`: `{idea_id: [Risk]}` — written to `premortem.json`; no field may carry a revised idea body

### Signatures

All in the FEAT-3667 engine, invoked in YAML as `$${LL_PYTHON:-python3} -m little_loops.brainstorm_engine annotate --run-dir DIR --critic-file F --defender-file F [--skip-reason REASON]`:

- `annotate(portfolio: dict, critic_out: str, defender_out: str, ideas: list[IdeaRecord]) -> tuple[dict, Premortem | None]` — validates and merges; returns the updated `flags` and the `Premortem`, or `None` on fail-open skip
- `render_risks(premortem: Premortem, ideas: list[IdeaRecord]) -> str` — the `Risks & Kill Criteria` report section

This child owns the named additive portfolio-command extension: publish/verify premortem_input.json when premortem is enabled, and preserve existing annotation flags on equal-input portfolio replay. Fingerprints exclude only this child's own mutable annotation flags; all other pinned fields must match. Update CLI reads/writes/conformance documentation in the enablement change. FEAT-3667's disabled/core semantics remain unchanged.

`critique` and `defend` are LLM states (`premortem_critic`, `premortem_defender`), not functions.

### Call Path

`portfolio` -> (token `premortem`) `premortem_critic` -> `premortem_defender` -> `annotate` -> `render_report` -> `validate_portfolio` -> `route_sink`

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/brainstorm.yaml` — add `premortem_critic`, `premortem_defender`, and the `annotate` module call between `portfolio` and `render_report` (no gate state: `portfolio` prints the routing token); report sections come from `render-report` reading `premortem.json` (FEAT-3667 owns `brainstorm.md`)
- `scripts/little_loops/brainstorm_engine.py` — `annotate`, `render_risks`, immutable-input verification, and the `BUILT_CAPABILITIES` enablement (module created by FEAT-3667)
- `scripts/little_loops/loops/brainstorm-profiles/functional.json` and `business.json` — enable this feature's premortem knob only, preserving earlier optional flips
- `scripts/little_loops/fsm/fence.py` — `FENCE_ROLES` entries for brief input and `UNTRUSTED_OUTPUT_ROLES` for the defender's captured critic payload; these are separate registries
- `scripts/tests/data/loop_interpolation_baseline.json` — new shell-state sites, if any

### Dependent Files (Callers/Importers)
- `ll-loop run brainstorm` callers and the sink adapters (`route_sink`, `sink_file`, `sink_issue`, `sink_decision`) inside the loop — unaffected: `winners.md` is unchanged
- FEAT-3583 — supplies the resolved `premortem` value and the `premortem` context override
- FEAT-3667 supplies the engine/renderer/artifact contracts; FEAT-3582 supplies portfolio/tournament wiring; FEAT-3583 supplies preset/override resolution. All three implementations are required before this feature can work. Engine/profile/test paths above are planned prerequisite artifacts.

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
- Step budget: +3 parent visits on the no-retry enabled path (critic, defender, `annotate`); +0 when disabled. This finisher updates `max_steps`/time bounds in its own enablement change; ENH-3734 verifies the cumulative optional total and retry/cap behavior.

### Codebase Research Findings

_Carried from `/ll:refine-issue` — 2026-09-25, edited 2026-09-29 for the annotate-only scope:_

- `tournament` and `portfolio` do not exist in `brainstorm.yaml` yet — FEAT-3582 dependency. Insertion point is between `portfolio` and `validate_portfolio`, so no sink runs before the finisher.
- Winners live in `winners.md` (JSON lines with `text`/`rationale`); this finisher never rewrites it.
- ~~Per-run round counter (`mechanize-skills.yaml` `diagnosis_retry`), `_validate_zero_retry_counter`, `retry_counter` scope constraint~~ — no longer relevant: there is no counter.
- `scripts/tests/test_brainstorm.py::TestBrainstormYaml::test_max_steps_is_60` pins `max_steps == 60`; ENH-3734 verifies the combined optional budget; this issue owns its increment.

### Failure, data and time contract (2026-10-05)

`premortem_critic` success -> premortem_defender; host error/timeout/rate-limit exhaustion -> a fixed-error annotation shell branch with critic_failed, skipping defender. `premortem_defender` success -> annotate; error -> a fixed-error annotation shell branch with defender_failed. Each error branch invokes `annotate --skip-reason` with its literal reason and never reads critic/defender captures. The executor can preserve an earlier successful capture when a runner raises, including after resume; defaulted output/prev_result alone does not establish freshness. An alternative fresh-attempt status mechanism is acceptable only with the same executor/resume proof. Error branches replace the normal annotate visit and preserve the +3 happy-path cost. Annotate logs the skip/flag then next -> render_report; an engine write/crash -> finalize_failed. An exit-0 critic whose payload is malformed can still reach defender before annotate rejects it; the one-call skip promise concerns host failure, not an unimplemented intermediate schema gate.

Both prompt states set finite timeouts, `max_rate_limit_retries: 0`, `rate_limit_max_wait_seconds: 0`, and **`rate_limit_long_wait_ladder: [0]`**. The ladder is checked before the ordinary wait budget, so the first two settings alone still permit a 300 s wait. API and infra retries are separate: without a stricter ordinary retry cap, the current executor permits up to five dispatches per state (initial plus two API plus two infra retries), with up to 70 s total backoff. Include each dispatch's action timeout, backoff and state visit in this feature's step/time bound; the +3 count describes the successful no-retry route. A stricter cap requires an explicit on_retry_exhausted skip route and fixtures. No hidden evaluator call is allowed.

Critic input format: `RISKS_JSON: {"<idea_id>": [{"failure_mode":str,"severity":"fatal|major|minor","kill_criterion":str}]}`. Defender format: `MITIGATIONS_JSON: {"<idea_id>": [{"failure_mode":str,"mitigation":str|null}]}`. IDs must equal the non-null winner/runner-up set; no wildcard/other IDs or revised title/body keys. Match by index and exact failure_mode after whitespace/case normalization; count/order/text mismatch skips the whole annotation. Annotate atomically replaces its own premortem record and **upserts only its own** flags; a repeated call cannot duplicate flags or leave a stale successful premortem.json after a skip. Preserve all unrelated portfolio flags.

Annotation input limits are 64 KiB UTF-8 per raw capture, exactly one tagged JSON record of each expected kind, and 1–5 risks per critiqued idea. failure_mode is a nonempty string <=200 Unicode code points; kill_criterion and a non-null mitigation are nonempty strings <=500 code points. Empty/oversized/duplicate-conflicting/schema-invalid input skips the whole annotation with a specific reason, never truncates it into different advice. Read raw files with the cap enforced during collection. These are unmeasured design limits. In the three-visit v1 route, validation occurs in annotate: an exit-0 malformed or oversized critic can cost a wasted, time-bounded defender call. The existing prompt-size warning is not a hard capture/forwarding limit; do not claim otherwise. Escape model text in the report rather than allowing it to inject report markup.

Publication spans premortem.json and portfolio flags, so separate atomic replacements are not a transaction. Replaying annotate from the same saved captures must repair either interruption boundary to the same result, preserve unrelated flags and remove stale success on an explicit skip. Inject failures between both writes and verify replay before report/validation/sinks; successful annotation replay cannot introduce duplicate flags.

The tail600 core reserve cannot guarantee two post-tournament calls plus retries. In the enablement change, add the critic+defender action time with one retry allowance per prompt (EPIC-3581 § Budget sizing rule, `2*T + 30` each; the all-retries bound is informational), plus annotate/render/validation/finalization overhead, to TAIL_S and the parent's timeout/engine guard. Assert the longest finisher/error/salvage path fits with a fake clock. Do not budget only +3 visits: elapsed time and invocations are separate. ENH-3734 later verifies the combined optional value, and earlier children may already have raised the timeout.

## Implementation Steps

1. Pin data delivery and finite per-call/retry bounds above, then add `premortem_critic`, `premortem_defender` between `portfolio` and `render_report` (blocked by FEAT-3582/FEAT-3583); a `render` token from `portfolio` routes straight past the finisher (`render_report` → `validate_portfolio`).
2. Implement `annotate` and `render_risks` in `brainstorm_engine.py` with unit tests first (TDD): schema validation, immutability check, fail-open, `unmitigated_fatal` flag.
3. Extend `render-report` (FEAT-3667) to add `Risks & Kill Criteria` for the winner and runner-up when `premortem.json` exists; output unchanged when it does not.
4. Add `FENCE_ROLES` entries, safe raw-file capture, enablement/preset flips and the derived step/time bump; record the reference run and run loop validation plus the local suite.

## Impact

- **Priority**: P4 - optional finisher that refines output but is not needed for a working engine
- **Effort**: Medium - two LLM states, bounded schema/annotation publication, persistent input checks, replay/error fixtures and derived post-tournament budgets
- **Risk**: Low - off by default for `artifact`/`visual`; annotate-only, fails open, cannot alter an idea or a ranking
- **Breaking Change**: No

## Acceptance Criteria

- Exactly two successful prompt calls on the enabled happy path (critic, defender); failed critic skips defender; retries/host failures are recorded honestly. No rounds/counter/hidden evaluator calls.
- The shipped idea's `title`/`body`, `ranking`, portfolio slots, and `winners.md` are byte-identical with and without the finisher; only `portfolio.json` `flags`, `premortem.json`, and the report differ.
- `Risks & Kill Criteria` appears for the winner and runner-up; the wildcard is stated as not critiqued.
- A `fatal` risk with `mitigation: null` adds `unmitigated_fatal` to that idea's `flags` and is highlighted in the report; the idea still reaches sinks.
- Malformed, unknown-id, mismatched, or revised-body critic/defender output fails open (`premortem_skipped`, `premortem.log`) and never fails the run.
- Skipped cleanly when disabled; no change to output shape otherwise.
- **Lands with its own enablement (2026-09-30):** in the same change, widen FEAT-3667's `BUILT_CAPABILITIES` to allow `premortem=true`, flip the `functional` and `business` preset knob to `true` (FEAT-3583 § Pinned Preset Contents), extend the profile-token wiring test, and bump `max_steps` by this finisher's own cost (+3 when enabled) instead of leaving it to FEAT-3596.
- Critic declares Read-only tool names and reads portfolio.json/ideas.jsonl, without an additional block state. Defender receives captured critic output inside its registered untrusted-output nonce fence and declares Read-only tools. Successful captures reach raw files via builtin printf with `:shell` quoting, preserving delimiter lines/metacharacters/newlines as data; quote interpreter/path arguments. Host-error branches use fixed --skip-reason values and never consume prior captures. Exactly three additional visits on the successful no-retry path; at most two successful LLM responses, with actual retry dispatches recorded separately.
- Real executor/resume fixtures seed old successful captures then raise critic/defender errors; critic failure never dispatches defender and neither failure reuses old annotations. Transport fixtures include literal heredoc terminators and shell metacharacters. Zero-wait-ladder and mixed API/infra retry fixtures account for all dispatches/backoff with a fake clock. Actual canonical-file mutation fails integrity before sinks; malformed output alone still skips annotations.
- Unit fixtures cover the 1/5/6/0-risk boundaries, 200/500-code-point boundaries, 64-KiB raw limit, empty/oversized strings, duplicate tagged records, report escaping and both annotation/flag publication interruption boundaries. Oversized or malformed advice is logged/skipped rather than truncated or treated as a run failure.
- Persistent input fixtures interrupt after the portfolio snapshot/before either prompt, mutate canonical data, then resume through success and fixed-error skip paths: integrity fails before sinks. Equal-input portfolio/annotate replay preserves existing annotations/unrelated flags; changed judging inputs cannot inherit old annotations. The disabled path creates no snapshot and keeps its existing bytes/visits.
- Whichever optional feature lands first replaces the literal max_steps==60 assertion with one derived from built capability paths; this child's own increment and retry visits remain its responsibility.
- Timeout, host error, rate-limit exhaustion and missing/malformed critic/defender captures produce premortem_skipped and proceed to render_report. Deterministic annotate/I/O errors still fail the run. A disabled finisher adds zero visits.
- This issue records its own functional/business reference run with annotations, import origin, actual call/token cost and an honest report; FEAT-3596 does not own it.


## Review Decisions

_2026-10-07 pre-implementation review, `/ll:advise` with claude-opus-5-5 (confidence 0.78):_ provisional until the core lands (EPIC-3687 § Provisional); re-evaluate value against core results before starting, and cancellation is an allowed outcome (this P4 child otherwise gates its P3 epic). Tail sizing now follows EPIC-3581 § Budget sizing rule. The snapshot/replay machinery is kept as specified; no contract change.

_2026-10-05 executor review and `/ll:advise` with Opus (confidence 0.70):_ corrected the long-wait ladder, stale-capture error branches, printf/:shell transport, separate output-fence registration, bounded annotation input/publication replay, host scope limitations and preset integration map. The core evidence issue does not verify the all-optional budget; ENH-3734 owns that work. Historical four-step and heredoc statements below are superseded by the active three-visit contract. Kept the three-visit route rather than adding an intermediate critic validator; a malformed exit-0 critic may waste the bounded defender call. Numeric limits are design choices, not measured quality thresholds.

_2026-10-05:_ pinned the three-state Read/capture data delivery and tagged risk formats; fail-open now includes host errors/timeouts, explicit skip routes and idempotent flag/file replacement. This issue must increase the post-tournament time reserve for its bounded actual calls, not merely add three steps. ENH-3734 owns cumulative optional verification. Historical confidence scores have not been rerun.

_Added 2026-09-30 (EPIC-3581 fifth review, `/ll:advise` with Opus):_ this issue moved to **EPIC-3687** (optional capabilities) so it no longer gates EPIC-3581 or FEAT-3596. Re-run `/ll:reconcile-issue` and `/ll:confidence-check` after FEAT-3667 lands (scores are missing or stale). Its own enablement change (widen `BUILT_CAPABILITIES`, flip the preset knob, wiring test, `max_steps`) and its own reference run stay in scope.

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

Historical score; not re-run after this review. The renderer/match-rule concerns below were resolved by earlier decisions; the new failure/retry/time contracts require verification after prerequisites land.

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
- Pre-implementation review (`/ll:advise` with claude-opus-5-5, confidence 0.78; issue edits only) - 2026-10-07
- Implementation-readiness review (Codex; `/ll:advise` with claude-opus-5-5, confidence 0.74; issue revisions only) - 2026-10-06
- `/ll:refine-issue` - 2026-10-05T17:31:36-06:00 - `EPIC-3687 pre-implementation review`
- Pre-implementation review and directive reconciliation (Codex; Opus consult unavailable: advisor task budget exhausted) - 2026-10-05
- `/ll:audit-issue-conflicts` - 2026-10-05T03:38:25 - `a86cd5e0-6077-4ee6-8374-60b76cefc32b.jsonl`
- `/ll:audit-issue-conflicts` - 2026-10-01T20:26:28 - `b32e58bb-e3b8-4048-9c71-1c2f63665ce9.jsonl`
- `/ll:confidence-check` - 2026-09-29T06:02:10 - `1e4b6b11-acbb-4e78-b169-131d9cd93116.jsonl`
- `/ll:confidence-check` - 2026-09-29T02:00:48 - `c90c2478-f308-49d4-930c-8be0a9590776.jsonl`
- `/ll:confidence-check` - 2026-09-25T17:21:40 - `823eec8e-b4aa-4134-9728-fb6281ade224.jsonl`
- `/ll:reconcile-issue` - 2026-09-25T17:15:35 - `fa11583b-aa00-4da8-b0f0-fc89c6cf8f64.jsonl`
- `/ll:wire-issue` - 2026-09-25T02:07:46 - `6e813375-6da8-496a-a222-6bd92b308c4c.jsonl`
- `/ll:refine-issue` - 2026-09-25T01:46:43 - `2ac59930-bb65-4013-a3d3-8f842b856fd9.jsonl`
- `/ll:format-issue` - 2026-09-25T01:01:32 - `825370f4-2bf5-4bb8-a770-49c1a90d8b61.jsonl`
- `/ll:capture-issue` - 2026-09-25T00:33:52 - `ba660a81-2414-4092-808d-95f51543dbb1.jsonl`

---

## Scope Boundary

**Note** (reconciled 2026-10-05): This finisher owns its step/time increment (+3 visits on the no-retry enabled path, with retries counted separately). The first optional child to land converts `test_max_steps_is_60` into a derived-from-built-capabilities assertion; **ENH-3734** verifies the all-optional total. FEAT-3596 owns core evidence only; earlier all-features budget assignments to it are superseded.
