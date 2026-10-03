---
id: FEAT-3561
type: FEAT
title: ll-next core with deterministic cross-verb recommendations
priority: P3
status: open
blocked_by:
- FEAT-3681
- ENH-3678
discovered_date: '2026-09-24'
labels: []
blocks:
- FEAT-3711
- FEAT-3712
- FEAT-3713
relates_to:
- FEAT-3714
parent: EPIC-3710
---

# FEAT-3561: ll-next core with deterministic cross-verb recommendations

## Summary

Build the stateless, advisory `ll-next` CLI: four candidate generators (`implement-issue`, `refine-issue`, `resolve-blocker`, `run-loop`), deterministic per-verb scoring on FEAT-3681's scorer, gates and coverage, a fixed round-robin cross-type fill, and a generated JSON Schema. This is part (a) of EPIC-3710 after an Opus pre-implementation review (2026-10-03) split the original nine-verb scope. It writes **no** history events and bumps **no** schema version. Events, acceptance and pressure are FEAT-3711; the backtest is FEAT-3712; `capture-issues`/`run-sprint` are FEAT-3713; the finding-backed verbs are deferred as FEAT-3714.

## Current Behavior

`ll-issues next-issue`/`next-issues` rank implementation targets, `ll-issues next-action` recommends refinement for one issue, and `ll-loop next-loop` scores loop runs. No command compares action types.

## Expected Behavior

`ll-next` emits up to N recommendations with an action type, target, copyable invocation/instruction, per-axis evidence, within-type utility, coverage, bucket rank and selection reason. It is **advisory only**; `--execute` is deferred until each verb has a typed, safe dispatcher. All four existing `next-*` CLIs keep their behavior. Missing data, unavailable goals and missing gates stay explicit rather than becoming guessed scores or negative outcomes. The command reads project files and git only: no `history.db` access, no writes.

## Motivation

A user deciding what to do next needs a legible choice across implementation, refinement, blockers and loops. Shipping the deterministic, stateless core first keeps the release inspectable, avoids the schema-bump and acceptance-attribution risk, and lets FEAT-3711/3712/3713 build on a stable candidate/score contract.

## Proposed Solution

### Action taxonomy and candidate sources

Each generator specifies its target and a copyable action; it yields no candidate when its source is absent and never invents required arguments. Candidate identity is `(action_type, target)`. A display command is copyable text, **not** a shell string executed by `ll-next`.

| Verb | Candidate source / required action |
|---|---|
| `implement-issue` | Ready, unblocked issue; show the issue ID and `/ll:manage-issue` invocation. |
| `refine-issue` | Valuable unready issue; show its next verified `ll-issues next-action` refinement step. An issue with missing readiness scores is eligible here, not for `implement-issue`. |
| `resolve-blocker` | Root blocker (an issue that is itself unblocked) of active issues, with a concrete issue target. |
| `run-loop` | Existing runnable loop; exclude loops whose required inputs have no deterministic resolver (the current `next-loop` registry resolves only some cases). |

`generic` is not a verb; work outside the taxonomy can be captured as an issue. `pay-tech-debt`, `update-docs` and `meta` are deferred (FEAT-3714); `capture-issues` and `run-sprint` are FEAT-3713.

### Axes × verbs matrix (initial defaults)

Weights are initial defaults pinned by fixtures and overridable only through keyed `next` config (FEAT-3681 owns the config surface; this issue adds the per-verb entries to `config-schema.json`). `—` means the axis is inapplicable and is excluded from that verb's coverage denominator.

| Axis (source) | implement-issue | refine-issue | resolve-blocker | run-loop |
|---|---|---|---|---|
| priority (frontmatter) | 0.30 | 0.30 | 0.25 | — |
| confidence / outcome (frontmatter scores) | 0.25 | — | — | — |
| readiness-gap (frontmatter scores vs `commands.confidence_gate`) | — | 0.25 | — | — |
| leverage / fan-out (dependency graph) | 0.15 | 0.15 | 0.45 | — |
| effort, inverse (frontmatter) | 0.10 | — | 0.15 | — |
| staleness (capture date) | — | 0.15 | 0.05 | — |
| momentum (Session Log timestamps in the issue file) | 0.10 | 0.10 | 0.05 | — |
| goal-alignment (explicit frontmatter override only) | 0.05 | 0.05 | 0.05 | — |
| frequency / recency / success (`next-loop` history) | — | — | — | 0.50 / 0.30 / 0.20 |

A prose `.ll/ll-goals.md` is **not** parsed as an EPIC map until a syntax and parser exist, so `goal-alignment` is missing (excluded, weights renormalized) without a frontmatter override. The decision-rule compliance gate and the decisions-based historical-signal axis are **out of scope**: decision rules carry only issue-scoped structure today, so compliance cannot be evaluated deterministically. Revisit once rules have machine-evaluable scope.

### Scoring, gates and coverage

- Use FEAT-3681's weighted geometric aggregate over present non-gate axes, weights renormalized after missing axes are excluded. No make-up term. An ordinary zero curve score uses the documented floor; only an explicit gate vetoes.
- Gates per `(consideration, action_type)` in keyed `next` config: unblocked-ness gates `implement-issue` and `resolve-blocker` (the blocker target must itself be unblocked); readiness gates `implement-issue`. A genuinely missing required gate fails closed and is reported as `gate-missing`.
- Coverage stores `resolved_axes` and `applicable_axes` as integers plus a display string; the denominator is per action type after excluding inapplicable axes. **Coverage-at-selection mechanism:** within a verb, candidates are ordered by `selection_score = utility × (resolved_axes / applicable_axes)`, ties broken by priority then issue ID ascending. `utility` itself is reported unmodified. A candidate with `resolved_axes == 0` has no utility and appears only in the priority fallback. If no signal resolves for any candidate, emit a clearly labeled priority fallback (exit 0); if signals resolve but all candidates are vetoed, return the no-candidate status (exit 1) without mislabeling it as cold start.

### Cross-type fill (stateless)

Rank within each verb by `selection_score`; fill `--top N` slots by **round-robin in fixed canonical verb order** (`implement-issue`, `refine-issue`, `resolve-blocker`, `run-loop`), taking each verb's best remaining candidate per round, with a per-type cap (default 2, keyed config). A target appears at most once in the output (first by round-robin order); `--explain` still shows every candidate for it. Utility is never compared numerically across verbs. `pressure` is part of the schema and `null` here; FEAT-3711 replaces round-robin with pressure-ordered fill.

### CLI and data contract

- `ll-next [--json] [--top N] [--type VERB ...] [--explain VERB TARGET]` (default N=3). `--explain` requires both verb and target. No `--execute`.
- Exit 0: recommendations or a labeled cold-start fallback emitted; exit 1: no candidate survives gating; exit 2: config/usage error. JSON includes a `fallback`/`gate_missing` reason where applicable.
- Candidate fields: `action_type`, `target`, `display_command`, `axes` (raw, curve, score, gate, source), `utility`, `bucket_rank`, `pressure` (null), `selection_reason`, `resolved_axes`, `applicable_axes`. The existing `ll-generate-schemas` flow only handles event schemas, so maintain a dedicated generated JSON Schema file with a drift test.
- Add the CLI entry point, CLI reference, and permission/registry wiring. Every emitted loop action has its required arguments resolved or is excluded; test that invariant rather than assuming `ll-loop run NAME` is always runnable.

## Scope Boundaries

- **In scope:** four generators with explicit no-candidate cases, scorer integration, round-robin selection, advisory CLI/JSON Schema, deterministic fixed-clock fixtures, scaled performance gate, docs.
- **Out of scope:** scorer extraction/config foundation (FEAT-3681), history events/acceptance/pressure and the schema bump (FEAT-3711), the backtest (FEAT-3712), `capture-issues`/`run-sprint` (FEAT-3713), `pay-tech-debt`/`update-docs`/`meta` (FEAT-3714), `--execute`, LLM reranking, learned weights, parsing goals prose, the decision-rule gate, auto-clustered sprints.

## Integration Map

### Files to Modify

- New `little_loops.cli.next` module and candidate-generator/selection modules; `scripts/pyproject.toml` entry point (no `ll-next` exists yet); CLI registration/permissions in `scripts/little_loops/init/writers.py`; `scripts/little_loops/config-schema.json` only for per-verb extensions to FEAT-3681's `next` object.
- Generated JSON Schema file for the output contract; `docs/reference/CLI.md`, `CONFIGURATION.md`, `API.md`.
- Tests for candidate sources, command-input invariants, gates/coverage/selection, schema drift, CLI registry/permissions, fixed-clock fixtures and the scaled performance ceiling.
- CLI-only: the skills/`ll-adapt` mirror gates do not apply; the CLI registry, permissions and `CLI.md` do.

### Similar Patterns and Configuration

- Reuse FEAT-3681's `utility/` aggregators and keyed config. Existing `next-*` commands remain untouched except shared pure helper imports.

## Program Design

### Types

- `AxisScore(raw, curve, score, gate, source)` and `Candidate(action_type, target, display_command, axes, utility, bucket_rank, pressure, selection_reason, resolved_axes, applicable_axes)` are typed records with deterministic JSON serialization.

### Signatures

- `generate_candidates(state: ProjectState) -> list[Candidate]` — returns only candidates with a named source and copyable action.
- `select_candidates(candidates: list[Candidate], top: int) -> list[Candidate]` — applies gates, coverage ordering and round-robin fill without cross-type utility comparison.

### Call Path

Existing `cmd_next_loop` / `find_issues` source paths → new `generate_candidates` → FEAT-3681's utility scorer → `select_candidates` → human/JSON rendering. No event is written.

## Implementation Steps

1. Land FEAT-3681 (ENH-3678 is already done); fix the axes × verbs matrix and the per-verb `next` config entries.
2. Implement the four generators as independently testable functions, then score/rank/select with no-candidate and missing-data semantics.
3. Add advisory `ll-next`, generated JSON Schema, registration/permissions/docs.
4. Run fixed fixtures and the scaled performance test; confirm the four `next-*` CLIs are unchanged.

## Impact

- **Priority:** P3 — useful project-wide decision support with an advisory first release.
- **Effort:** Medium–Large — four generators, new CLI, schema, docs.
- **Risk:** Medium — false precision and stale signals can yield persuasive but wrong rankings; mitigated by explicit missing-data states and no persisted state.
- **Breaking Change:** No; existing recommenders keep their output.

## Use Case

A user runs `ll-next --top 3`, sees one ready issue, one refinement target and one loop, and can inspect the evidence for each with `ll-next --explain VERB TARGET`. No action runs automatically and nothing is written.

## Acceptance Criteria

- [ ] FEAT-3681's scorer/config foundation is landed; the four verbs' per-verb `next` config entries and the axes × verbs matrix defaults are in `config-schema.json` and pinned by fixtures.
- [ ] All four verbs have tested candidate sources and explicit empty-source behavior; emitted commands/instructions have required inputs resolved and are copyable. `--execute` is absent.
- [ ] Weighted aggregation, gate/fallback and per-type coverage semantics follow the contracts above, including `selection_score` ordering and the `gate-missing` fail-closed case; `--explain VERB TARGET` resolves duplicate-target ambiguity.
- [ ] Round-robin fill follows the canonical verb order with the per-type cap and at-most-once-per-target rule; no cross-verb utility comparison.
- [ ] `ll-next` human and JSON modes, exit codes, generated/validated JSON Schema (with drift test), registry/permissions and docs pass focused tests; the command performs no `history.db` access and no writes.
- [ ] Fixed-clock synthetic fixtures (missing curve axes, missing gates, ordinary zero scores, an unblocked ready issue, cold start) and a scaled synthetic performance ceiling pass without network access.
- [ ] The four existing `next-*` CLIs remain behavior-identical; `python -m pytest scripts/tests/` passes.

## Related

- EPIC-3710 (parent). FEAT-3681 (scorer extraction; prerequisite), ENH-3678 (done; schema-bump safety, relevant to FEAT-3711). FEAT-3711, FEAT-3712, FEAT-3713 (follow-on slices); FEAT-3714 (deferred finding-backed verbs).

## Status

**Open** | Created: 2026-09-24 | Priority: P3
