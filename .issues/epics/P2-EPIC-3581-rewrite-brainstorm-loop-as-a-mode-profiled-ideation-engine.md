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

Rewrite the built-in `brainstorm` loop (`scripts/little_loops/loops/brainstorm.yaml`,
originally FEAT-2248) as a **mode-profiled ideation engine**. The current loop is
structurally sound (lenses → diverge → cluster → rank → converge, sinks as optional
adapters) but behaves as a fixed pipeline: its novelty/saturation machinery never
fires, and all judgment collapses into three single-shot LLM calls. It also assumes
every idea is one sentence of text judged the same way, which fails for the distinct
brainstorming modes the user actually needs: **artifacts** (names, copy, concepts),
**visual designs**, **functional designs** (features, architecture, APIs), and
**business/product opportunities**.

## Motivation

Evidence from the 4 historical runs in `.loops/runs/brainstorm-*` (transient run
state, 2026-06-27 … 2026-07-02, not committed):

- **Dedup/saturation inert** — across 45 ideas in the 07-02 run, max pairwise difflib
  ratio was 0.44 (median 0.05) vs the `novelty_threshold: "0.55"` default;
  `saturation.txt` stayed 0 in all 4 runs. Character-level similarity cannot catch
  paraphrase duplicates (three "name the load-bearing assumption" variants survived).
  In practice the loop is always 9 lenses × 5 ideas.
- **Diverge rounds are blind to prior ideas** — each `diverge` sees only the brief,
  so cross-lens anti-anchoring pressure is absent.
- **Judgment is unstructured** — `cluster`, `rank`, `converge` are each one listwise
  LLM pass; "pairwise narrative" is a prompt style, not a structure. `converge` read
  ~319k input tokens in the 07-02 run.
- **Forced hybrid** — the synthesized top idea is a Frankenstein of three asks;
  brainstorm output should usually be a portfolio of distinct options.
- **Not actually double-diamond** — `frame` selects lenses; it never reframes the
  problem, so only the solution diamond exists.
- **Silent success on zero ideas** — the 07-01 run produced 0 ideas (`lenses.txt`
  still held all 9 lenses, no `diverge` calls); `converge` wrote an honest
  "No synthesis produced" report that passes `verify_artifacts`, which only checks
  `brainstorm.md` is non-empty.
- **Mode mismatch** — visual designs need rendered candidates judged visually;
  functional designs need codebase grounding; business opportunities need market
  grounding and reframing; artifacts need breadth more than a single winner.

## Integration Map

### Behavior Parity

Per-state dispositions are itemized in FEAT-3582 § Behavior Parity; epic-level summary:

| Artifact | Behavior | Disposition |
|----------|----------|-------------|
| `scripts/little_loops/loops/brainstorm.yaml` | lens queue (`frame`/`pop_lens`) feeding `diverge` | preserved |
| `scripts/little_loops/loops/brainstorm.yaml` | difflib novelty dedup + saturation early exit | dropped — duplicate-group dedup |
| `scripts/little_loops/loops/brainstorm.yaml` | listwise `cluster`/`rank`/`converge` hybrid | changed — round-robin tournament + portfolio |
| `scripts/little_loops/loops/brainstorm.yaml` | sinks run before `verify_artifacts` | changed — `validate_portfolio` gates sinks |
| `scripts/little_loops/loops/brainstorm.yaml` | sink contract (`none`/`file`/`issue`/`decision`, `winners.md` `text`/`rationale`) | preserved |

### Files to Modify
- `scripts/little_loops/loops/brainstorm.yaml` — every child rewrites or adds states here
- `scripts/little_loops/brainstorm_engine.py` — new (FEAT-3667); every later child adds commands here
- Profile data files (FEAT-3583; `.json` preferred to avoid loop-discovery `rglob` scanners)
- `scripts/little_loops/fsm/fence.py` — `FENCE_ROLES` / `KNOWN_UNFENCED_PROMPT_SITES` for new and removed prompt states
- `README.md` + `scripts/README.md`, `CHANGELOG.md` (breaking change, FEAT-3582)

### Dependent Files (Callers/Importers)
- Sinks inside the loop (`route_sink`, `sink_file`, `sink_issue`, `sink_decision`) — contract preserved, read `winners.md` with `text`/`rationale` keys
- `scripts/little_loops/loops/lib/common.yaml` — `parse_tagged_json`, `queue_pop`
- No loop, skill, command, or Python module outside `brainstorm.yaml` consumes its artifacts

### Tests
- `scripts/tests/test_brainstorm.py` (rewritten per FEAT-3582, wiring only), `scripts/tests/test_brainstorm_engine.py` (new; engine logic by direct import), `scripts/tests/test_builtin_loops.py` (fence, MR-11 allowlist, warning budget), `scripts/tests/data/loop_interpolation_baseline.json`, `scripts/tests/test_builtin_loop_hardcode_gate.py`
- Cross-child failure-path fixtures and the combined step budget: FEAT-3596

### Documentation
- `scripts/little_loops/loops/README.md`, `docs/guides/LOOPS_GUIDE.md`, `docs/guides/LOOPS_REFERENCE.md`

### Cross-Child Contracts (Astra review, 2026-09-25)
- **Data contract** (stable IDs, common fields incl. top-level optional `grounded`, enumerated axis bins, canonical `portfolio.json`, generation vs. finalist floors) is specified in FEAT-3582 and implemented by FEAT-3667; other children extend it only.
- **Validation before sinks**: `validate_portfolio` gates `route_sink`; no sink fires on an invalid run.
- **Profile precedence**: mode selects the base profile, explicit knobs override it, `""` means inherit (FEAT-3583).
- **Ordering**: FEAT-3667 (engine module) → FEAT-3582 (loop rewrite) → FEAT-3583 → {FEAT-3584, FEAT-3585, FEAT-3586}; FEAT-3686 (spike, 2026-09-30) gates FEAT-3582 and the grid-dependent parts of FEAT-3667; FEAT-3596 is hard-blocked by FEAT-3667/3582/3583/3686 and closes on the core engine only — the optional capabilities (FEAT-3584/3585/3586) moved to EPIC-3687 and record their own reference runs.
- **Profile plumbing** (2026-09-28 review): FEAT-3582 owns `resolve_profile`, the `profile.json` schema, and the `artifact` profile; FEAT-3583 extends them (presets, classifier, overrides).
- **Tournament runs as a sub-loop** (one parent `max_steps` step; finalists ≤ 8, full round-robin judged **one call per round** — ≈ 7 round calls + 1 batched probe call; child `max_steps: 45`, `timeout: 1800`; parent `timeout: 5400` keeps a 600 s tail so salvage/portfolio/finalize always run, and `check_floors --stage pre_tournament` fails `insufficient_time` early); `diverge` runs once per lens with round-robin framings. `top_k` is removed; `winners.md` = portfolio members.
- **Grounding shape** (FEAT-3584): `touchpoints` (must exist) vs `creates` (must not collide); `shortlist` keeps a reserve so no back-edge into `ground`/`materialize`.
- **Pre-mortem is annotate-only in v1** (FEAT-3586, 2026-09-29): one critic call + one defender call over winner and runner-up; no demotion, concession, or `winner: null`. `winner` is always non-null; an unmitigated `fatal` risk is a report flag (`unmitigated_fatal`), not a gate. Demotion is a follow-up that must bring its own concession signal and Data Contract change.
- **Engine module** (2026-09-29): deterministic logic lives in `scripts/little_loops/brainstorm_engine.py` (FEAT-3667, split out of FEAT-3582; CLI contract table lives there), called from thin YAML states via `$${LL_PYTHON:-python3} -m little_loops.brainstorm_engine <cmd>`; later children add commands (`resolve-profile`, probes, `annotate`), not inline scripts.
- **Filter pipeline** (2026-09-29): `finalists.json` (`{finalists, reserve, dropped, judge_mode, assets}`) is rewritten in place by every filtering state; order `dedup → ground_codebase → shortlist → check_floors(generation) → ground_web → materialize → check_floors(pre_tournament) → tournament`. Floors count `grounded != false` ideas and are enforced before any judge call.
- **Knob defaults live in profiles** (2026-09-29): floor, `max_finalists`, and `ideas_per_round` context keys default to `""` (inherit); the pinned numbers are profile data, so a profile can lower them and an explicit context value still wins.

- **Pre-implementation review** (2026-09-29, `/ll:advise` with Opus; nothing measured): profile gates fold into engine routing tokens (no gate states); `dedup` re-tags cells blind to the generator's tags; `reframe` is a forced ranking; cap tie-break by generation order; `abstention_rate` recorded (`> 0.25` low confidence, `> 0.5` fails validation); `materialize` is 4 fixed batched states (FEAT-3585); `classify_mode` reports the chosen mode in the report header so a wrong auto-selection is visible and rerunnable with `mode=`.

- **Third pre-implementation review** (2026-09-29, `/ll:advise` with Opus; nothing measured) — applied across all children:
  - **Tournament failure routing**: the parent `tournament` state routes `on_yes` → `portfolio` and `on_no`/`on_error`/`on_timeout` → `salvage_tournament` (a judge-call error otherwise discards every completed round). Judge states carry `timeout: 300`; the time guard is `TOURNAMENT_TIMEOUT_S + JUDGE_CALL_TIMEOUT_S + TAIL_S`. Confirm the action-timeout path with a `MockActionRunner` test before writing the routing (FEAT-3582).
  - **Report owner**: a deterministic `render-report` engine command and a `render_report` state (after `portfolio`/`premortem` and **before** `validate_portfolio`, which requires a non-empty `brainstorm.md`; corrected 2026-09-30) are the only writers of `brainstorm.md`; `init` still empties it (FEAT-3667/3582).
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

## Impact

- **Priority**: P2 - brainstorm is a shipped built-in loop whose core machinery is inert in every observed run
- **Effort**: Large - seven children; full rewrite of a ~460-line loop plus profiles, grounding, rendering, and pre-mortem
- **Risk**: Medium - replaces a shipped loop's behavior; mitigated by `ll-loop validate`, deterministic script-side scoring, and FEAT-3596 fixtures
- **Breaking Change**: Yes - removed context keys (`novelty_threshold`, `max_saturation`, `novelty_backend`) and portfolio output shape

## Goal

One engine whose core is **C + B + A** — reframe the problem (true double diamond; on by default for `functional`/`business`, off by default for `artifact`/`visual`, overridable with `reframe=`),
diverge with structural quality-diversity (MAP-Elites-style grid), select via a
script-driven pairwise tournament — with an optional **D** adversarial pre-mortem
finisher. Mode-specific behavior lives in **profiles as data**, not in duplicated
loops, and two gated states (`ground`, `materialize`) cover the gaps the core does
not.

## Scope

In scope:

- Core engine: reframe → grid-tagged diverge (enumerated axis bins) → duplicate-group
  dedup → per-cell shortlist → floor gate → round-robin pairwise tournament → portfolio →
  `validate_portfolio` before sinks; hard generation and finalist floors. Replaces
  difflib novelty and the saturation counter.
- Mode profiles (`artifact`, `visual`, `functional`, `business`, `auto`) as data:
  reframe on/off, grid axes, idea schema, ground source, materialize, tournament
  rubric, pre-mortem on/off, output shape.
- **Auto mode selection** (default `mode: auto`): the first state after `init`
  classifies the brief into a profile and records `{mode, confidence, rationale}`
  in the run dir. Low confidence falls back to the generic `artifact` profile.
  An explicit `mode=<x>` skips classification; individual profile knobs
  (`materialize`, `ground`, `premortem`, …) are overridable per run so mixed
  briefs (e.g. a product concept that also needs a landing-page visual) work.
- `ground` state: none | codebase, with non-LLM anchor-existence probes. **`ground=web`
  (cited-URL fetch + quote match) is deferred to a follow-up** (2026-09-29 third review):
  v1 ships codebase grounding only; the `business` profile defaults to `ground: none`.
- `materialize` state for visual mode: HTML/SVG mockups → Playwright screenshots →
  image-capability canary → image-pairwise judging (no mid-tournament HTML restart in v1).
- Integration and evaluation (FEAT-3596): reference runs, failure-path fixtures,
  combined step budget, comparison against the old loop.
- Optional annotate-only `premortem` finisher (risks and kill criteria for winner and runner-up).

Out of scope:

- Changing the sink adapters' contract (`none|file|issue|decision`) beyond reading
  the new portfolio shape. Core must stay decoupled from the Issue system.
- Human-in-the-loop steering states.
- Embedding-based novelty (the `novelty_backend` placeholder is removed, not built).

## Children
_FEAT-3584 / FEAT-3585 / FEAT-3586 (grounding, materialize, pre-mortem) moved to **EPIC-3687** on 2026-09-30 so this epic can close on the core engine._
- **FEAT-3667** — Brainstorm engine module: deterministic core, CLI contract, and artifact profile (open)
- **FEAT-3582** — Brainstorm engine core: reframe, grid diverge, pairwise tournament, portfolio (open; loop side, blocked by FEAT-3667)
- **FEAT-3583** — Brainstorm mode profiles with automatic mode selection (open)
- **FEAT-3596** — Brainstorm engine integration, reference runs, and evaluation (open)
- **FEAT-3686** — Brainstorm design spike: measure grid, dedup and batched-judge claims on baseline ideas (open)


## Success Metrics

- A run with fewer than the configured minimum ideas routes to `failed`, never `done`,
  and no sink executes on a failed run.
- Diversity is measured non-LLM: occupied grid cells ≥ a configured floor.
- Finalists are ranked by a full round-robin of pairwise matches, judged one round per call, with
  counterbalanced presentation order (top-3 head-to-heads re-judged reversed in
  an independent call); the schedule is built and scored by script.
- Versus the old loop on 2 fixed briefs (FEAT-3596): fewer retained duplicates, more
  occupied cells, token/runtime cost recorded.
- Each of the 4 modes has a profile and at least one reference run producing its
  expected output shape (visual mode produces rendered mockups + screenshots).
- `mode: auto` selects the expected profile for one reference brief per mode, and
  an explicit `mode=` override bypasses classification.
- `ll-loop validate` passes (MR rules, per-run artifact isolation under
  `${context.run_dir}/`).
- Cost ceiling: a default run (`mode: auto`, classifier included) makes ≤ 30 LLM calls (old loop 14 measured 2026-09-29, 13 without the finalize summary; expected ≈ 22 = 1 classify + 1 frame + 9 diverge + 1 dedup + 1 shortlist + ≈ 8 judge, +1 reframe when the profile enables it). Total input/output tokens are **recorded, not gated**, until the baseline exists — per-session overhead (≈ 94k tokens per call in the 2026-06-27 run) makes call count the wrong unit for cost.
- Blind A/B (FEAT-3596): a person compares old-loop top idea vs new winner on both pinned briefs, blind; pass = win or tie on both.
- Judge reliability is observable: tournament `tie_rate` and `abstention_rate` are recorded and the report
  flags `low_confidence` rankings.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-25 | Priority: P2

## Session Log
- `/ll:audit-issue-conflicts` - 2026-10-01T20:26:27 - `b32e58bb-e3b8-4048-9c71-1c2f63665ce9.jsonl`
- `/ll:capture-issue` - 2026-09-25T00:33:32 - `f51f0560-5252-48a7-8a81-10d11331e067.jsonl`

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): `reframe` is deferred to v2 (`BUILT_CAPABILITIES` allows `reframe: {False}` in v1), so the Goal's default-on reframe for `functional`/`business` is a v2 target. Rendered mockups/screenshots, `ground`, `materialize`, and `premortem` are owned by EPIC-3687; v1 visual mode covers axes, lenses and rubric (text judging) only. FEAT-3667 owns the profile schema, presets, and `resolve_profile`.
