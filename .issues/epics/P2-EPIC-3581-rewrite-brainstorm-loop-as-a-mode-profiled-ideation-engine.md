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

### Files to Modify
- TBD - requires codebase analysis

### Dependent Files (Callers/Importers)
- TBD - use grep to find references

### Tests
- TBD - identify shared test infrastructure

### Documentation
- TBD - docs that need updates

## Impact

- **Priority**: [P0-P5] - [Justification]
- **Effort**: [Small/Medium/Large] - [Justification]
- **Risk**: [Low/Medium/High] - [Justification]
- **Breaking Change**: [Yes/No]

## Goal

One engine whose core is **C + B + A** — reframe the problem (true double diamond),
diverge with structural quality-diversity (MAP-Elites-style grid), select via a
script-driven pairwise tournament — with an optional **D** adversarial pre-mortem
finisher. Mode-specific behavior lives in **profiles as data**, not in duplicated
loops, and two gated states (`ground`, `materialize`) cover the gaps the core does
not.

## Scope

In scope:

- Core engine: reframe → grid-tagged diverge → script dedup by cell + cluster →
  per-cell shortlist → pairwise tournament → portfolio output; hard min-idea
  invariant. Replaces difflib novelty and the saturation counter.
- Mode profiles (`artifact`, `visual`, `functional`, `business`, `auto`) as data:
  reframe on/off, grid axes, idea schema, ground source, materialize, tournament
  rubric, pre-mortem on/off, output shape.
- **Auto mode selection** (default `mode: auto`): the first state after `init`
  classifies the brief into a profile and records `{mode, confidence, rationale}`
  in the run dir. Low confidence falls back to the generic `artifact` profile.
  An explicit `mode=<x>` skips classification; individual profile knobs
  (`materialize`, `ground`, `premortem`, …) are overridable per run so mixed
  briefs (e.g. a product concept that also needs a landing-page visual) work.
- `ground` state: none | codebase | web, with non-LLM evidence probes.
- `materialize` state for visual mode: HTML/SVG mockups → Playwright screenshots →
  image-pairwise judging.
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






## Success Metrics

- A run with fewer than the configured minimum ideas routes to `failed`, never `done`.
- Diversity is measured non-LLM: occupied grid cells ≥ a configured floor.
- Finalists are ranked by pairwise matches with position-swapped judging; the
  bracket is built and scored by script.
- Each of the 4 modes has a profile and at least one reference run producing its
  expected output shape (visual mode produces rendered mockups + screenshots).
- `mode: auto` selects the expected profile for one reference brief per mode, and
  an explicit `mode=` override bypasses classification.
- `ll-loop validate` passes (MR rules, per-run artifact isolation under
  `${context.run_dir}/`).

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-25 | Priority: P2

## Session Log
- `/ll:capture-issue` - 2026-09-25T00:33:32 - `f51f0560-5252-48a7-8a81-10d11331e067.jsonl`
