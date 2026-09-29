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
| `scripts/little_loops/loops/brainstorm.yaml` | listwise `cluster`/`rank`/`converge` hybrid | changed — Swiss tournament + portfolio |
| `scripts/little_loops/loops/brainstorm.yaml` | sinks run before `verify_artifacts` | changed — `validate_portfolio` gates sinks |
| `scripts/little_loops/loops/brainstorm.yaml` | sink contract (`none`/`file`/`issue`/`decision`, `winners.md` `text`/`rationale`) | preserved |

### Files to Modify
- `scripts/little_loops/loops/brainstorm.yaml` — every child rewrites or adds states here
- Profile data files (FEAT-3583; `.json` preferred to avoid loop-discovery `rglob` scanners)
- `scripts/little_loops/fsm/fence.py` — `FENCE_ROLES` / `KNOWN_UNFENCED_PROMPT_SITES` for new and removed prompt states
- `README.md` + `scripts/README.md`, `CHANGELOG.md` (breaking change, FEAT-3582)

### Dependent Files (Callers/Importers)
- Sinks inside the loop (`route_sink`, `sink_file`, `sink_issue`, `sink_decision`) — contract preserved, read `winners.md` with `text`/`rationale` keys
- `scripts/little_loops/loops/lib/common.yaml` — `parse_tagged_json`, `queue_pop`
- No loop, skill, command, or Python module outside `brainstorm.yaml` consumes its artifacts

### Tests
- `scripts/tests/test_brainstorm.py` (rewritten per FEAT-3582), `scripts/tests/test_builtin_loops.py` (fence, MR-11 allowlist, warning budget), `scripts/tests/data/loop_interpolation_baseline.json`, `scripts/tests/test_builtin_loop_hardcode_gate.py`
- Cross-child failure-path fixtures and the combined step budget: FEAT-3596

### Documentation
- `scripts/little_loops/loops/README.md`, `docs/guides/LOOPS_GUIDE.md`, `docs/guides/LOOPS_REFERENCE.md`

### Cross-Child Contracts (Astra review, 2026-09-25)
- **Data contract** (stable IDs, common fields, enumerated axis bins, canonical `portfolio.json`, generation vs. finalist floors) is owned by FEAT-3582; other children extend it only.
- **Validation before sinks**: `validate_portfolio` gates `route_sink`; no sink fires on an invalid run.
- **Profile precedence**: mode selects the base profile, explicit knobs override it, `""` means inherit (FEAT-3583).
- **Ordering**: FEAT-3582 → FEAT-3583 → {FEAT-3584, FEAT-3585, FEAT-3586}; FEAT-3596 is hard-blocked only by FEAT-3582/3583 (so P4 FEAT-3586 does not gate it) but cannot close until all optional children are done.
- **Profile plumbing** (2026-09-28 review): FEAT-3582 owns `resolve_profile`, the `profile.json` schema, and the `artifact` profile; FEAT-3583 extends them (presets, classifier, overrides).
- **Tournament runs as a sub-loop** (one parent `max_steps` step; finalists ≤ 8, rounds `ceil(log2 N)`); `diverge` runs once per lens with round-robin framings. `top_k` is removed; `winners.md` = portfolio members.
- **Grounding shape** (FEAT-3584): `touchpoints` (must exist) vs `creates` (must not collide); `shortlist` keeps a reserve so no back-edge into `ground`/`materialize`.
- **Concession is script-determined** (FEAT-3586): fatal risk with no mitigation. `winner: null` is legal only for all-conceded.

## Impact

- **Priority**: P2 - brainstorm is a shipped built-in loop whose core machinery is inert in every observed run
- **Effort**: Large - six children; full rewrite of a ~460-line loop plus profiles, grounding, rendering, and pre-mortem
- **Risk**: Medium - replaces a shipped loop's behavior; mitigated by `ll-loop validate`, deterministic script-side scoring, and FEAT-3596 fixtures
- **Breaking Change**: Yes - removed context keys (`novelty_threshold`, `max_saturation`, `novelty_backend`) and portfolio output shape

## Goal

One engine whose core is **C + B + A** — reframe the problem (true double diamond),
diverge with structural quality-diversity (MAP-Elites-style grid), select via a
script-driven pairwise tournament — with an optional **D** adversarial pre-mortem
finisher. Mode-specific behavior lives in **profiles as data**, not in duplicated
loops, and two gated states (`ground`, `materialize`) cover the gaps the core does
not.

## Scope

In scope:

- Core engine: reframe → grid-tagged diverge (enumerated axis bins) → duplicate-group
  dedup → per-cell shortlist → Swiss pairwise tournament → portfolio →
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
- `ground` state: none | codebase | web, with non-LLM evidence probes (anchor
  existence; cited-URL fetch + quote match).
- `materialize` state for visual mode: HTML/SVG mockups → Playwright screenshots →
  image-capability canary → image-pairwise judging.
- Integration and evaluation (FEAT-3596): reference runs, failure-path fixtures,
  combined step budget, comparison against the old loop.
- Optional `premortem` finisher.

Out of scope:

- Changing the sink adapters' contract (`none|file|issue|decision`) beyond reading
  the new portfolio shape. Core must stay decoupled from the Issue system.
- Human-in-the-loop steering states.
- Embedding-based novelty (the `novelty_backend` placeholder is removed, not built).

## Children
- **FEAT-3582** — Brainstorm engine core: reframe, grid diverge, pairwise tournament, portfolio (open)
- **FEAT-3583** — Brainstorm mode profiles with automatic mode selection (open)
- **FEAT-3584** — Brainstorm ground state with codebase and web evidence probes (open)
- **FEAT-3585** — Brainstorm materialize state: rendered mockups judged visually (open)
- **FEAT-3586** — Brainstorm optional pre-mortem finisher (open)
- **FEAT-3596** — Brainstorm engine integration, reference runs, and evaluation (open)







## Success Metrics

- A run with fewer than the configured minimum ideas routes to `failed`, never `done`,
  and no sink executes on a failed run.
- Diversity is measured non-LLM: occupied grid cells ≥ a configured floor.
- Finalists are ranked by pairwise matches with position-swapped judging in
  independent calls; the Swiss bracket is built and scored by script.
- Versus the old loop on 2 fixed briefs (FEAT-3596): fewer retained duplicates, more
  occupied cells, token/runtime cost recorded.
- Each of the 4 modes has a profile and at least one reference run producing its
  expected output shape (visual mode produces rendered mockups + screenshots).
- `mode: auto` selects the expected profile for one reference brief per mode, and
  an explicit `mode=` override bypasses classification.
- `ll-loop validate` passes (MR rules, per-run artifact isolation under
  `${context.run_dir}/`).
- Cost ceiling: a default `mode=artifact` run makes ≤ 45 LLM calls (old loop ≈ 12).
- Judge reliability is observable: tournament `tie_rate` is recorded and the report
  flags `low_confidence` rankings.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-25 | Priority: P2

## Session Log
- `/ll:capture-issue` - 2026-09-25T00:33:32 - `f51f0560-5252-48a7-8a81-10d11331e067.jsonl`