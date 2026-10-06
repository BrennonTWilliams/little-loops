---
id: EPIC-3581
type: EPIC
title: Rewrite brainstorm loop as a mode-profiled ideation engine
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-25'
captured_at: '2026-09-25T00:32:23Z'
labels:
- epic
- loops
- brainstorm
- captured
relates_to:
- FEAT-2248
---

# EPIC-3581: Rewrite brainstorm loop as a mode-profiled ideation engine

## Summary

Rewrite the built-in brainstorm loop as a mode-profiled ideation engine: occupancy-aware grid divergence, blind re-tag/duplicate-group dedup, per-cell shortlist, deterministic round-robin ranking and a portfolio of distinct options. Profiles differentiate artifact, visual, functional and business briefs; auto classification is added only after preset tuning. This epic closes on the **core engine**. Reframe and web grounding remain deferred; grounding, rendered mockups and annotate-only pre-mortem belong to EPIC-3687.

## Motivation

Historical runs showed ineffective character-level dedup, divergence blind to prior ideas, listwise judgment, forced hybrid output, and silent success on zero ideas. The preserved fresh baseline/spike adds nuance: difflib did remove three short-name ideas on one brief; grid steering and batched judging have measured support on two briefs, with functional-axis and same-model-label limitations. FEAT-3686 is done/GO, not an uncompleted prerequisite.

## Goal

A bounded engine with mode-specific lenses, bin definitions, duplicate criteria, extra fields and rubric, delivering a validated winner/runner-up/wildcard portfolio and compatibility with existing sinks. The v1 core has one solution diamond; the former default-on reframe/double-diamond goal is deferred to v2, not an implementation requirement.

## Scope

In scope: deterministic engine/CLI, four JSON presets with unbuilt knobs off, lens ledger/monotonic idea IDs, grid divergence/dedup/shortlist, generation and pre-tournament floors, round-robin child with salvage, deterministic report and validation before sinks, auto-mode/override wiring and comparable integration evidence.

Out of scope: reframe, unjudged hybrid synthesis, web evidence/reserve promotion, browser rendering, anchor probes, pre-mortem, human steering states and embedding-based novelty. Optional capabilities are EPIC-3687; v1 visual mode here is text judged.

## Cross-Child Contracts

- FEAT-3667 owns engine types, CLI/evaluator contracts, the four preset files, resolver validation/preflight, crash-safe publication and deterministic report. FEAT-3582 owns YAML orchestration/tournament and its merge gate; FEAT-3583 owns opt-in classifier/override plumbing and bounded preset tuning; FEAT-3596 owns core integration/closeout and the gated default switch to auto.
- Order: completed FEAT-3686 -> FEAT-3667 -> FEAT-3582 -> FEAT-3583 -> FEAT-3596. Optional children can proceed after FEAT-3583 independently of one another; they do not block this epic.
- pop_lens calls the engine's peek-lens without consuming; ingest durably records completion before acknowledging its matching head after idea/divergence-state publication (also on zero valid rows). Equal-input replay preserves acknowledged IDs and repairs an outstanding acknowledgement; stale/changed lens input fails without consuming the next head. Frame replay reuses the original ledger rather than applying a fresh LLM answer.
- IDs are reserved before publication, never reused, and ideas persist lens_index from an immutable lenses.json ledger. Init is non-destructive on re-entry, and one writer per run is supported. Separate replacements are not a transaction. Committed round/probe batches are write-once; a judging-input digest pins bodies/cells/profile/assets as well as IDs, and a stable probe plan pins its committed main verdicts. Conflicting replay fails without replacing results.
- Generation is bounded to 1–10 ideas per lens (at most nine lenses/90 current rows), with typed/nonempty bounded title/body/extra fields and visible rejection counts. Valid blind re-tags recompute off_grid eligibility; invalid ones preserve it. Explicit inputs fail preflight before the classifier/generation. BUILT_CAPABILITIES prohibits missing-state tokens. Profiles choose base values; nonempty explicit knobs override; empty inherits; false/none disables. reframe and synthesize=true remain unavailable in v1.
- Canonical portfolio slots are distinct eligible tournament finalists; reserve/dropped IDs cannot leak to sinks. Reports are deterministic; successful validation precedes every sink. Generation diversity and surviving finalist coverage are separate metrics; post-filter finalist floor is two.
- Main tournament and reversed probe batches are atomic; the rate definitions and thresholds are pinned in FEAT-3667. Odd-finalist partial rounds do not guarantee equal games, so salvage is low-confidence. Child failures have explicit failure terminals and all failure routes reach salvage.
- Budgets come from actual executor paths, including captured blocks, empty queue peek, classifier, sink/finalization, retries and backoffs. Every prompt has a finite action timeout; FEAT-3582 owns the retry arithmetic (ordinary prompt visit: at most five dispatches, 5*timeout + 70 s backoff) and executor-constant mirror fixture. The child-overrun term remains one last action plus one handler sleep. Nominal core paths fit max_steps60; retry-induced parent cap exhaustion runs deterministic finalize_failed, while child cap exhaustion reaches salvage. Outer loop timeout can bypass finalization; no executor changes are part of this epic. Disable six-hour rate-limit defaults; preserve the child/judge/core tail plus retry-sleep reserve. Optional children own their own step/time increments; ENH-3734 verifies their cumulative values.
- Classifier host-error paths pass a fixed decision-error to the resolver and never read saved successful captures. Core fixtures explicitly disable the three optional knobs; negative capability tests use the core allowlist while shipped-preset compatibility uses the actual built set.
- FEAT-3582's real worktree runs and comparable core A/B gate occur before the live rewrite reaches main. FEAT-3596 repeats the final-core comparison with matched model/settings, actual usage and identical blind tagging of old/new ideas. Changed axes require re-tagging both sets; human A/B judgments must be actually recorded.

## Comparable token gate

One accounting definition is shared by FEAT-3582's pre-main gate and FEAT-3596's final-core gate: `gate_tokens = uncached_input + cache_read + cache_creation + output`, summed over all actual dispatches, including classifier, finalization and retries. Do not add an adapter's already-inclusive input total to its cache columns again. Missing usage/components make the gate unverified. Evaluation-only tagging/consult calls are recorded separately from the brainstorm run's dispatches.

The preserved fresh baseline uses claude-sonnet-5-5 with its recorded host/settings. Its exact denominators are **902,745 artifact tokens** (879,243 input context + 23,502 output) and **915,457 functional tokens** (888,628 input context + 26,829 output). The former approximately 879k/889k values excluded output and cannot be denominators for this formula. These corrections reuse recorded columns; they are not new measurements and do not rewrite the preserved baseline.

Test `2 * new_gate_tokens <= 3 * matching_baseline_tokens` in integers: ceilings **1,354,117** (artifact) and **1,373,185** (functional). A different model/host/settings is incomparable until a matching baseline exists. Preserve complete per-component usage, import origin and comparison inputs; both children reference this definition rather than redefining it.

## Default-mode release gate

FEAT-3582 ships artifact by default. FEAT-3583 adds opt-in auto and completes bounded preset tuning, retaining that default. FEAT-3596 explicitly requests auto for its four already-planned live mode runs; only after every expected mode is selected with confidence >=0.6/no fallback and all tuning/core gates pass does it flip the default to auto. A miss leaves artifact as default and closure pending. No additional calibration corpus or child issue is required.

## Integration Map

### Behavior Parity

| Artifact | Behavior | Disposition |
|---|---|---|
| brainstorm.yaml | Lens queue, optional sinks and handoff | Preserved; immutable lens ledger added |
| brainstorm.yaml | difflib/saturation | Dropped; duplicate-group dedup and floors |
| brainstorm.yaml | listwise cluster/rank/converge hybrid | Changed to round-robin and distinct portfolio |
| brainstorm.yaml | Sinks before validation | Changed; canonical validation gates all sinks |
| brainstorm.yaml | Removed keys and synthesize=true | Document migration and reject unavailable synthesis explicitly |

### Files to Modify
- scripts/little_loops/brainstorm_engine.py and scripts/little_loops/loops/brainstorm-profiles/*.json — FEAT-3667, then tuned by FEAT-3583.
- scripts/little_loops/loops/brainstorm.yaml and brainstorm-tournament.yaml — FEAT-3582/3583.
- scripts/little_loops/fsm/fence.py, scripts/little_loops/package_data.py, tests/baselines, README.md + scripts/README.md and CHANGELOG.md — owning child wiring.

### Tests
- scripts/tests/test_brainstorm_engine.py — deterministic contracts; scripts/tests/test_brainstorm.py — real-executor/wiring/failure/sink fixtures.
- Built-in validation/fence/interpolation/warning/packaging checks; full local pytest is authoritative.

### Documentation
- docs/reference/API.md; scripts/little_loops/loops/README.md; docs/guides/LOOPS_GUIDE.md and LOOPS_REFERENCE.md.

## Children

- **FEAT-3667** — Brainstorm engine module: deterministic core, CLI contract, and artifact profile (open).
- **FEAT-3582** — Brainstorm engine core: grid diverge, pairwise tournament, portfolio (open; after FEAT-3667).
- **FEAT-3583** — Brainstorm mode profiles with automatic mode selection (open; after FEAT-3582).
- **FEAT-3596** — Brainstorm engine integration, reference runs, and evaluation (open; core closeout).
- **FEAT-3686** — Brainstorm design spike: measure grid, dedup and batched-judge claims on baseline ideas (done, 2026-09-30; GO with amendments).

## Success Metrics

- Zero/insufficient ideas/cells/finalists fail before judging or sinks; no dropped/reserve candidate can win.
- All four core modes produce their expected text-judged portfolio/report layouts; auto classification and explicit built-knob overrides are visibly recorded.
- Full deterministic round-robin N<=8, counterbalanced order, independent reversed probe, observable tie/abstention/partial flags, and working failure salvage.
- On the two pinned briefs with matched evaluation definitions/settings: cells >= old, duplicates <= old, actual calls <=30 (including classifier/finalization/retries), total context tokens <=1.5x the matching old baseline; human blind A/B win-or-tie on both. Two-brief evidence is a regression smoke check, not proof of improvement.
- Both loops validate; all artifacts stay under run_dir; packaging and full local pytest pass; exact step/time/retry bounds fit shipped budgets.
- All five child statuses resolve to done/cancelled; no optional P3/P4 capability or deferred v2 scope gates this epic.

## Impact

- **Priority**: P2 — replaces a shipped loop used by local-editable projects.
- **Effort**: Large — engine, orchestration, presets/classifier and core evidence; spike already completed.
- **Risk**: Medium — mitigated by isolated worktree real runs, regression gates and a coherent single-commit YAML rewrite/rollback.
- **Breaking Change**: Yes — removed novelty/saturation/top_k context and portfolio report output; document migration.

## Composition Review

Reviewed 2026-10-06 against the current executor/runner/issue contracts, with `/ll:advise` using claude-opus-5-5 (confidence 0.74). **Disposition: KEEP.** All four open children are on-theme, recently active and cover the core deliverables; FEAT-3686 is already done/GO. No additional child, reparenting or dependency reversal is needed. Start with FEAT-3667; the live YAML rewrite still requires FEAT-3582's worktree comparison before main, and FEAT-3596's later default switch concerns artifact-to-auto selection.

Active child directives now cover the missing lens-completion/acknowledgement handoff, stale classifier captures, independent core fixtures and the unowned budget-helper reference. Preserve reservation-before-publication and the existing queue; the advisor's suggested metadata-last cursor shortcut would violate the monotonic-ID requirement. Implementation evidence, human A/B and refreshed readiness scores remain pending their owners.

## Review History

_2026-10-05 implementation-boundary review; `/ll:advise` with claude-opus-5-5, confidence 0.78:_ Reviewed all four open children against executor/persistence/interpolation code and preserved baseline counters. Updated ownership for durable lens handoff, safe shell arguments, derived pre-tournament bounds/local failure terminals, exact shared token accounting and the final-integration auto-default gate. No new child/dependency change, live quality measurement or human A/B verdict.

Historical design evolution; the reconciled scope/contracts above are authoritative. No new live measurements or human A/B judgments were made in the 2026-10-05 issue reviews. The earlier consult was budget-blocked; the follow-up consult with claude-opus-5-5 succeeded (confidence 0.72). Its accepted changes are reflected in active directives/children: write-once verdicts/judging fingerprints, bounded generation, re-tag eligibility, non-destructive init and enforcement of the matched token cap before the YAML rewrite reaches main. No new children or dependency reversal were needed. Expanded live classifier calibration and concurrent-writer/exactly-once-sink mechanisms were left outside this review.

### Earlier cross-child reviews
- **Data contract** (stable IDs, common fields incl. top-level optional `grounded`, enumerated axis bins, canonical `portfolio.json`, generation vs. finalist floors) is specified in FEAT-3582 and implemented by FEAT-3667; other children extend it only.
- **Validation before sinks**: `validate_portfolio` gates `route_sink`; no sink fires on an invalid run.
- **Profile precedence**: mode selects the base profile, explicit knobs override it, `""` means inherit (FEAT-3583).
- **Ordering**: FEAT-3667 (engine module) → FEAT-3582 (loop rewrite) → FEAT-3583 → {FEAT-3584, FEAT-3585, FEAT-3586}; FEAT-3686 (spike, 2026-09-30) gates FEAT-3582 and the grid-dependent parts of FEAT-3667; FEAT-3596 is hard-blocked by FEAT-3667/3582/3583/3686 and closes on the core engine only — the optional capabilities (FEAT-3584/3585/3586) moved to EPIC-3687 and record their own reference runs.
- **Profile plumbing** (2026-09-28 review): FEAT-3582 owns `resolve_profile`, the `profile.json` schema, and the `artifact` profile; FEAT-3583 extends them (presets, classifier, overrides).
- **Tournament runs as a sub-loop** (one parent `max_steps` step; finalists ≤ 8, full round-robin judged **one call per round** — ≈ 7 round calls + 1 batched probe call; child `max_steps: 45`, `timeout: 1800`; parent `timeout: 5400` keeps a 600 s tail so salvage/portfolio/finalize always run, and `check_floors --stage pre_tournament` fails `insufficient_time` early); `diverge` runs once per lens with round-robin framings. `top_k` is removed; `winners.md` = portfolio members.
- **Grounding shape** (FEAT-3584): `touchpoints` (must exist) vs `creates` (must not collide); `shortlist` keeps a reserve so no back-edge into `ground`/`materialize`.
- **Pre-mortem is annotate-only in v1** (FEAT-3586, 2026-09-29): one critic call + one defender call over winner and runner-up; no demotion, concession, or `winner: null`. `winner` is always non-null; an unmitigated `fatal` risk is a report flag (`unmitigated_fatal`), not a gate. Demotion is a follow-up that must bring its own concession signal and Data Contract change.
- **Engine module** (2026-09-29): deterministic logic lives in `scripts/little_loops/brainstorm_engine.py` (FEAT-3667, split out of FEAT-3582; CLI contract table lives there), called from thin YAML states via `"$${LL_PYTHON:-python3}" -m little_loops.brainstorm_engine <cmd>`; later children add commands (`resolve-profile`, probes, `annotate`), not inline scripts.
- **Filter pipeline** (2026-09-29): `finalists.json` (`{finalists, reserve, dropped, judge_mode, assets}`) is rewritten in place by every filtering state; order `dedup → ground_codebase → shortlist → check_floors(generation) → ground_web → materialize → check_floors(pre_tournament) → tournament`. Floors count `grounded != false` ideas and are enforced before any judge call.
- **Knob defaults live in profiles** (2026-09-29): floor, `max_finalists`, and `ideas_per_round` context keys default to `""` (inherit); the pinned numbers are profile data, so a profile can lower them and an explicit context value still wins.

- **Pre-implementation review** (2026-09-29, `/ll:advise` with Opus; nothing measured): profile gates fold into engine routing tokens (no gate states); `dedup` re-tags cells blind to the generator's tags; `reframe` is a forced ranking; cap tie-break by generation order; `abstention_rate` recorded (`> 0.25` low confidence, `> 0.5` fails validation); `materialize` is 4 fixed batched states (FEAT-3585); `classify_mode` reports the chosen mode in the report header so a wrong auto-selection is visible and rerunnable with `mode=`.

- **Third pre-implementation review** (2026-09-29, `/ll:advise` with Opus; nothing measured) — applied across all children:
  - **Tournament failure routing**: the parent `tournament` state routes `on_yes` → `portfolio` and `on_no`/`on_error`/`on_timeout` → `salvage_tournament` (a judge-call error otherwise discards every completed round). Judge states carry `timeout: 300`; the time guard is `TOURNAMENT_TIMEOUT_S + JUDGE_CALL_TIMEOUT_S + TAIL_S`. Confirm the action-timeout path with a `MockActionRunner` test before writing the routing (FEAT-3582).
  - **Report owner**: a deterministic `render-report` engine command and a `render_report` state (after `portfolio`/`premortem` and **before** `validate_portfolio`, which requires a non-empty `brainstorm.md`; corrected 2026-09-30) are the only writers of `brainstorm.md`; `init` originally emptied it; the follow-up now requires create-if-absent without truncation (FEAT-3667/3582).
  - **Clock**: the time guard takes `--elapsed-ms ${loop.elapsed_ms}` (active time incl. resume offset), never wall-clock `run_started_epoch`.
  - **Routing safety**: every classify-routed engine command prints a `fail` token on exit 1; happy tokens are listed explicitly; every classify state sets `_: finalize_failed`.
  - **Idempotent appends**: `record-round` (keyed by round+pair), `next-round` (skips recorded rounds), `ingest` (replaces by lens index; `lenses.txt` holds indices) so a re-run never double-counts; framings are sanitized of `|` and newlines.
  - **Prompt parameterisation**: engine commands print prompt blocks (axes/bins, extra fields, rubric, occupancy, round pairs) to stdout; states capture them and interpolate inside `<<<…>>>` nonce fences. No `round_prompt.txt`. Profiles gain a `lenses` key.
  - **Hidden LLM calls**: every prompt state uses `next:` + `on_error:` (or an explicit `evaluate:`) so the default `llm_structured` evaluator adds no call.
  - **FEAT-3582 merge gate**: `MockActionRunner` end-to-end runs (happy, floor-fail, child-timeout salvage, child-error salvage), one real run per pinned brief from the worktree with `PYTHONPATH=<worktree>/scripts` (the editable install otherwise resolves `main`), and the old-vs-new core comparison. The loop keeps the name `brainstorm` (fence/baseline/README keys are filename-keyed).
  - **Scope cuts**: `ground=web` and FEAT-3585's `fallback_html` mid-tournament restart are out of v1.
  - **Quality metric**: a blind human A/B on the two pinned briefs (old top idea vs new winner; pass = win or tie on both). _Moved 2026-09-30 (fourth review): the core A/B is a **FEAT-3582 merge gate**, not a FEAT-3596 close-out — every project is `local-editable`, so a quality regression lands with the rewrite. FEAT-3596 re-runs it for the four-mode and all-features configurations._

- **Fourth pre-implementation review** (2026-09-30, `/ll:advise` with Opus; nothing measured; mechanism claims spot-checked against `executor.py`/`evaluators.py`) — applied across FEAT-3667/3582/3583/3584/3585/3586/3596:
  - **Capability allowlist**: `resolve-profile` rejects knob values naming unbuilt features (`BUILT_CAPABILITIES`, FEAT-3667); FEAT-3583 ships presets with `ground`/`materialize`/`premortem` off; each optional child widens the allowlist and flips its own preset knob when it lands. Without this, `visual`/`functional`/`business` runs would route into missing states and fail after ~13 calls or after the full tournament.
  - **Routing gaps closed**: `frame-apply` owns the default reframe-skip path (`reframe|pop_lens`); `collapse` emits `ground_codebase|shortlist`; `portfolio` emits `premortem|render|fail`; `lenses.txt` = `lens_index|framing|lens`; `render-report --failed` keeps a single `brainstorm.md` writer.
  - **Step count enumerated**, not asserted: FEAT-3582 § LLM-state pairing pairs each LLM state with the shell state that captures its data block; expect ≈ 47–50 of 60, asserted in the merge-gate end-to-end test.
  - **Merge gate has a pass criterion** (blind A/B win-or-tie on both briefs, cells ≥ old, duplicates ≤ old, ≤ 30 calls).
  - **Kept, on evidence**: the `insufficient_time` guard (judge calls are not clamped to remaining budget; every judge state must set `timeout: 300`) and the 3×3 grid contract (wildcard both-axes rule holds from ≥ 6 occupied cells).
  - **Process note**: four review rounds have now added contract rules without a single measured run. **Freeze the spec here** — the next information comes from implementing FEAT-3667 (with its executor smoke test), not from another review.

- **Fifth pre-implementation review** (2026-09-30, `/ll:advise` with Opus, structural/process pass; nothing measured):
  - **Spike first (FEAT-3686)**: a ≈ 1-day, ≈ 75-call offline replay of `postmortems/brainstorm-baseline/fresh-20260929/*/ideas.jsonl` measures tagger self-agreement, old-loop grid headroom, occupancy-steering lift, LLM dedup precision/recall and batched-round judge consistency, with go/no-go thresholds. It also produces the shared consensus tags that FEAT-3582's merge gate and FEAT-3596's comparison read, which removes the FEAT-3582 ↔ FEAT-3596 ownership circle. A failing grid result drops the grid/re-tag/wildcard-on-both-axes machinery (`cell` is nullable meanwhile); a failing batched-judge result falls back to per-pair judging with `max_finalists` 6.
  - **Epic closes on the core**: FEAT-3584/3585/3586 moved to EPIC-3687 so an optional P3/P4 child cannot hold this epic open.
  - **Presets ship in FEAT-3667**: all four profile JSONs (unbuilt knobs off) so FEAT-3582's brief-2 (functional) gate runs `mode=functional` rather than the artifact axes.
  - **`reframe` deferred to v2**: `BUILT_CAPABILITIES` allows `reframe: {False}` in v1 (the `artifact`/`visual` default is already off); `reframe-select` and the `reframe` state are not built until a follow-up brings measurements. `functional`/`business` presets ship `reframe: false`; the "true double diamond" goal item is deferred with it.
  - **Token ceiling**: total context tokens are gated at ≤ 1.5× the old loop's ≈ 880k per brief (≈ 22 calls × ≈ 63k ≈ 1.4M is the estimate), because the rewrite otherwise contradicts its own token-bloat motivation.
  - **Import origin**: run records and the FEAT-3667 smoke test assert `little_loops.__file__` lives in the checkout under test; verify gates already inject the worktree `PYTHONPATH`, so the FEAT-3667 hazard is loud (`ModuleNotFoundError`), but once the module is on `main` a worktree run without `PYTHONPATH` silently imports `main`'s copy (FEAT-3582/3583).
  - **Rollback**: a clean `git revert` of FEAT-3582's single commit is the kill switch; breaking-change CHANGELOG entry plus a warning when a removed context key is passed. BUG-3688 hotfixes the old loop's zero-idea silent success now.
  - **Blind A/B is a smoke check**: single rater on n = 2 briefs has little statistical power.
  - **Spike result (FEAT-3686, 2026-09-30, 160 calls): GO with amendments.** Steering lifts occupied cells +2 vs a control; generator self-tags overstate occupancy so the blind re-tag is load-bearing; dedup needs a per-profile `duplicate_criterion` (precision 0.63 → 1.0 on names); axis bins need definitions and the `functional` `approach` axis needs sharpening (agreement 0.72); batched round judging with 8 finalists matches per-pair judging (τ 0.71, swap-consistency 0.82). Grid-dependent FEAT-3667 commands are no longer held. Details: `postmortems/brainstorm-spike/RESULTS.md`.


## Status

**Open** | Created: 2026-09-25 | Priority: P2

## Session Log
- Implementation-readiness review (Codex; `/ll:advise` with claude-opus-5-5, confidence 0.74; issue revisions only) - 2026-10-06
- Implementation-boundary review (Codex; `/ll:advise` with claude-opus-5-5, confidence 0.78; issue updates only) - 2026-10-05
- Follow-up pre-implementation review (Codex; `/ll:advise` with claude-opus-5-5, confidence 0.72; no new live measurements) - 2026-10-05
- Pre-implementation review and directive reconciliation (Codex; Opus consult unavailable: advisor task budget exhausted) - 2026-10-05
- `/ll:audit-issue-conflicts` - 2026-10-05T03:38:24 - `a86cd5e0-6077-4ee6-8374-60b76cefc32b.jsonl`
- `/ll:audit-issue-conflicts` - 2026-10-01T20:26:27 - `b32e58bb-e3b8-4048-9c71-1c2f63665ce9.jsonl`
- `/ll:capture-issue` - 2026-09-25T00:33:32 - `f51f0560-5252-48a7-8a81-10d11331e067.jsonl`
