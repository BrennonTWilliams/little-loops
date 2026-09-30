---
id: FEAT-3561
type: FEAT
title: Next-action arena Phase 1 with deterministic ll-next recommendations
priority: P3
status: open
blocked_by:
- FEAT-3681
- ENH-3678
discovered_date: '2026-09-24'
labels: []
---

# FEAT-3561: Next-action arena Phase 1 with deterministic `ll-next` recommendations

## Summary

Build an advisory `ll-next` CLI that ranks a fixed menu of project actions using auditable, deterministic considerations. FEAT-3681 owns Phase 0's reusable scorer extraction and `next` config surface. This issue owns candidate generation, cross-type selection, a minimal recommendation event stream, and evaluation. The history-table migration lands only after ENH-3678 stops unrelated schema bumps from auto-spawning full rebuilds.

## Current Behavior

`ll-issues next-issue`/`next-issues` rank implementation targets, `ll-issues next-action` recommends refinement for one issue, and `ll-loop next-loop` scores loop runs. No command compares action types. Existing event tables do not identify the start and outcome of every proposed verb, so treating all unmatched recommendations as "ignored" would fabricate feedback.

## Expected Behavior

`ll-next` emits up to N recommendations with an action type, target, copyable invocation/instruction, per-axis evidence, within-type utility, coverage, bucket rank, pressure, and selection reason. It is **advisory only** in this phase; `--execute` is deferred until each verb has a typed, safe dispatcher and required inputs. All four existing `next-*` CLIs keep their behavior. Missing data, unavailable goals, and unobservable acceptance remain explicit rather than becoming guessed scores or negative outcomes.

## Motivation

A user deciding what to do next needs a legible choice across implementation, refinement, loops, scans, and maintenance. Separating deterministic scoring from later execution and learning keeps the first release inspectable and lets real usage reveal which action types are useful.

## Proposed Solution

### Action taxonomy and candidate sources

All nine verbs ship with a generator, but a generator yields no candidate when its source is absent. Each generator specifies its target and a copyable action; it never invents required arguments.

| Verb | Candidate source / required action |
|---|---|
| `implement-issue` | Ready, unblocked issue; show the issue ID and `/ll:manage-issue` invocation. |
| `refine-issue` | Valuable unready issue; show its next verified `ll-issues next-action` refinement step. |
| `run-sprint` | Existing sprint definition only; no automatic clustering. |
| `run-loop` | Existing runnable loop; exclude loops whose required inputs have no deterministic resolver (the current `next-loop` registry resolves only some cases). |
| `capture-issues` | Stale discovery signal with a configured scan scope; no candidate without a known scope. |
| `resolve-blocker` | Dependency graph node blocking active issues, with a concrete issue target. |
| `pay-tech-debt` | Persisted audit finding or captured debt issue; no invented finding. |
| `update-docs` | Persisted docs-drift finding or captured docs issue. |
| `meta` | Persisted harness-audit finding; yield nothing when none exists. |

`generic` is not a verb. Work outside the taxonomy can be captured as an issue. The same issue may appear as both `implement-issue` and `refine-issue`; readiness gates the first and raises the second. Candidate identity is `(action_type, target)`. A display command is copyable text, **not** a shell string executed by `ll-next`.

### Considerations and scoring

- Use FEAT-3681's weighted geometric aggregate for present non-gate axes, with weights renormalized after missing axes are excluded. No make-up term. An ordinary zero curve score uses the documented floor; only an explicit gate vetoes.
- Sources: priority/frontmatter; dependency graph for unblocked-ness and fan-out leverage; effort and confidence frontmatter/history; capture date or historical commit time for staleness; current sprint/recent events for momentum; scan/loop history for information freshness; active decisions/corrections for historical signal; refinement state for readiness. `goal-alignment` uses explicit issue frontmatter overrides when present. A prose `.ll/ll-goals.md` is **not** parsed as an EPIC map until a syntax and parser exist, so the axis is missing otherwise.
- Gate assignments are per `(consideration, action_type)` in keyed `next` config. Unblocked-ness gates `implement-issue` and `run-sprint`; readiness gates `implement-issue`; decision-rule compliance gates all types. If no decision rule applies, compliance is a positive pass. A genuinely missing required gate fails closed and is reported as `gate-missing`.
- Coverage stores `resolved_axes` and `applicable_axes` as integers, plus a display string. The denominator is per action type after excluding inapplicable axes. Apply `resolved_axes / applicable_axes` at **selection**, not inside utility. If no signal resolves, emit a clearly labeled priority fallback; if signals resolve but all candidates are vetoed, return the no-candidate status without mislabeling it as cold start.

### Cross-type selection

Rank within each verb; fill `--top N` slots by bucket pressure with a per-type cap. Pressure rises when a bucket is neglected and resets only on an observed/explicit acceptance, never on display. A filtered `--type` run does not accrue or reset excluded buckets. Store pressure inputs and reasons in the output. A candidate's utility is never compared numerically across different verbs.

### CLI and data contract

- `ll-next [--json] [--top N] [--type VERB ...] [--explain VERB TARGET]` (default N=3). `--explain` requires both verb and target because one target may have multiple candidates. No `--execute` in this issue.
- Exit 0: recommendations or a labeled cold-start fallback emitted; exit 1: no candidate survives gating; exit 2: config/usage error. JSON includes a `fallback`/`gate_missing` reason where applicable.
- Candidate fields: `action_type`, `target`, `display_command`, `axes` (raw, curve, score, gate, source), `utility`, `bucket_rank`, `pressure`, `selection_reason`, `resolved_axes`, `applicable_axes`. Generate and validate its JSON Schema; the existing `ll-generate-schemas` flow only handles event schemas, so extend it deliberately or maintain a separate generated schema with a test.
- Add the CLI entry point, CLI reference, and permission/registry wiring. Every emitted loop action has its required arguments resolved or is excluded; test that invariant rather than assuming `ll-loop run NAME` is always runnable.

### Recommendation events and acceptance

- Add `recommendation_events` at the first `ll-next` release: recommendation ID, timestamp/session, shown rank and candidate identity, viewed marker, acceptance state (`accepted`, `ignored`, or `unknown`), match source, and an outcome field that may be unset. Include the table in local and remote schema/migration paths. Its `SCHEMA_VERSION` bump is blocked by ENH-3678.
- Map each verb to a concrete event producer **before** enabling automatic acceptance. Issue start/completion, loop run, sprint run and scan events may provide matches; for verbs without reliable producer/target/session attribution, keep `unknown` or accept an explicit `ll-next accept REC_ID`. Do not mark an issue recommendation ignored after 72 hours merely because completion occurs later; match the start of work and assess outcome separately.
- The `(action_type, target)` match is stronger than command-string matching but is still observational; it cannot prove the recommendation caused the action. Pressure resets on accepted evidence only. Remote users' events must reach the configured remote store.

### Evaluation

1. Fixed, synthetic project fixtures with a fixed clock cover missing curve axes, missing gates, ordinary zero scores, an unblocked ready issue, and cold start. A scaled synthetic fixture, not this repo's changing live backlog, enforces a generous performance ceiling without network access.
2. Backtest `implement-issue` only, reporting top-3 hit rate and MRR against `next-issue`. Reconstruct **all** signal sources as of each historical commit: issue files, history events (`ts <= as_of`), decisions, pressure state, and staleness from historical commit/capture time rather than fresh checkout mtime. Run it as a reproducible report, not a non-hermetic suite assertion.
3. Report live top-1 acceptance and outcome quality only for verbs with observable or explicit acceptance. Keep unknown recommendations out of the ignored denominator.

## Scope Boundaries

- **In scope:** nine generators with explicit no-candidate cases, scorer integration, bucket selection, advisory CLI/JSON Schema, event recording with honest acceptance states, deterministic fixtures and an as-of backtest report.
- **Out of scope:** scorer extraction/config foundation (FEAT-3681), `--execute` and automatic dispatch, LLM reranking, learned weights, parsing free-form goals prose, auto-clustered sprints, and treating unobservable verbs as ignored.

## Integration Map

### Files to Modify

- A new `little_loops.cli.next` module and candidate-generator/selection modules; `scripts/pyproject.toml` entry point; CLI registration/permissions in `scripts/little_loops/init/writers.py`; `scripts/little_loops/config-schema.json` only for Phase 1 extensions to FEAT-3681's `next` object.
- `scripts/little_loops/session_store/schema.py`, writers/queries, remote schema/migration and API exports for `recommendation_events`; JSON Schema generator or dedicated schema+test; `docs/reference/CLI.md`, `CONFIGURATION.md`, and `API.md`.
- Tests for candidate sources, command-input invariants, selection/coverage/gates, history event matching and remote persistence, CLI registry/permissions, fixed-clock performance, and as-of backtest fixtures.

### Similar Patterns and Configuration

- Reuse FEAT-3681's `utility/` aggregators and keyed config. Existing `next-*` commands remain untouched except shared pure helper imports.

## Program Design

### Types

- `AxisScore(raw, curve, score, gate, source)` and `Candidate(action_type, target, display_command, axes, utility, bucket_rank, pressure, selection_reason, resolved_axes, applicable_axes)` are typed records with deterministic JSON serialization.

### Signatures

- `generate_candidates(state: ProjectState) -> list[Candidate]` — returns only candidates with a named source and copyable action.
- `select_candidates(candidates: list[Candidate], top: int) -> list[Candidate]` — applies gates, coverage and bucket pressure without cross-type utility comparison.

### Call Path

Existing `cmd_next_loop` / `find_issues` source paths → new `generate_candidates` → FEAT-3681's utility scorer → `select_candidates` → human/JSON rendering → viewed recommendation event. Acceptance/outcome matching runs separately from display.

## Implementation Steps

1. Land FEAT-3681 and ENH-3678; define the per-verb source and acceptance-producer table with tests. Add the event schema in local and remote backends.
2. Implement the nine generators as independently testable functions, then score/rank/select with no-candidate and missing-data semantics.
3. Add advisory `ll-next`, JSON Schema, registration/permissions/docs, and honest event recording.
4. Run fixed fixtures, scaled performance test and as-of backtest report; compare `implement-issue` top-3/MRR with `next-issue` and inspect acceptance only where observable.

## Impact

- **Priority:** P3 — useful project-wide decision support with an advisory first release.
- **Effort:** Large — nine generators, new CLI, local/remote event storage, evaluation and docs.
- **Risk:** High — false precision, stale signals, and incorrect acceptance attribution can produce persuasive but wrong rankings.
- **Breaking Change:** No; existing recommenders keep their output.

## Use Case

A user runs `ll-next --top 3`, sees one ready issue, one overdue scan and one loop, and can inspect the evidence for each with `ll-next --explain VERB TARGET`. No action runs automatically.

## Acceptance Criteria

- [ ] FEAT-3681's scorer/config foundation and ENH-3678's rebuild gate are landed before the `recommendation_events` schema bump.
- [ ] All nine verbs have tested candidate sources and explicit empty-source behavior; emitted commands/instructions have required inputs and are copyable. `--execute` is absent.
- [ ] Weighted aggregation, gate/fallback and per-type coverage semantics follow the contracts above; `--explain VERB TARGET` resolves duplicate-target ambiguity.
- [ ] `ll-next` human and JSON modes, exit codes, generated/validated schema, registry/permissions and docs pass focused tests.
- [ ] Local and remote recommendation events record display/viewed state; acceptance is backed by a named producer or explicit action, otherwise `unknown`; pressure resets only on accepted evidence.
- [ ] Fixed-clock synthetic fixtures and scaled performance gate pass; an as-of backtest reports top-3 hit rate and MRR against `next-issue` without future history/mtime leakage.
- [ ] The four existing `next-*` CLIs remain behavior-identical; `python -m pytest scripts/tests/` passes.

## Related

- FEAT-3681 (Phase 0 scorer extraction; prerequisite), ENH-3678 (schema-bump safety prerequisite). Later work may add typed `--execute`, learned weights, richer goal mappings and an LLM reviewer after recommendation and acceptance evidence exists.

## Status

**Open** | Created: 2026-09-24 | Priority: P3
