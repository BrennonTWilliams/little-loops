---
id: FEAT-3561
type: FEAT
title: ll-next core with deterministic cross-verb recommendations
priority: P3
status: open
blocked_by:
- FEAT-3681
discovered_date: '2026-09-24'
labels: []
blocks:
- FEAT-3711
- FEAT-3712
- FEAT-3713
relates_to:
- FEAT-3714
- ENH-3678
parent: EPIC-3710
---

# FEAT-3561: ll-next core with deterministic cross-verb recommendations

## Summary

Build the stateless, advisory `ll-next` CLI: four candidate generators (`implement-issue`, `refine-issue`, `resolve-blocker`, `run-loop`), deterministic per-verb scoring on FEAT-3681's scorer, gates and coverage, a fixed round-robin cross-type fill, and a generated JSON Schema. This is part (a) of EPIC-3710 after an Opus pre-implementation review (2026-10-03) split the original nine-verb scope. It writes **no** history events and bumps **no** schema version. Events, acceptance and pressure are FEAT-3711; the backtest is FEAT-3712; `capture-issues`/`run-sprint` are FEAT-3713; the finding-backed verbs are deferred as FEAT-3714.

## Current Behavior

`ll-issues next-issue`/`next-issues` rank implementation targets, `ll-issues next-action` selects the first refinement step across the active backlog, and `ll-loop next-loop` scores loop runs. No command compares action types. `next-action` has no per-issue target argument; the arena needs a pure per-issue adapter rather than calling that CLI for every candidate.

## Expected Behavior

`ll-next` emits up to N recommendations with an action type, target, copyable invocation/instruction, per-axis evidence, within-type utility, coverage, bucket rank and selection reason. It is **advisory only**; `--execute` is deferred until each verb has a typed, safe dispatcher. All four existing `next-*` CLIs keep their behavior. Missing data, unavailable goals and missing gates stay explicit rather than becoming guessed scores or negative outcomes. The command reads project files and git only: no `history.db` access, no writes.

## Motivation

A user deciding what to do next needs a legible choice across implementation, refinement, blockers and loops. Shipping the deterministic, stateless core first keeps the release inspectable, avoids the schema-bump and acceptance-attribution risk, and lets FEAT-3711/3712/3713 build on a stable candidate/score contract.

## Proposed Solution

### Action taxonomy and candidate sources

Each generator specifies its target and a copyable action; it yields no candidate when its source is absent and never invents required arguments. Candidate identity is `(action_type, target_key)`, where `target_key` is namespaced (`issue:FEAT-123`, `loop:NAME`; follow-ups add `sprint:NAME` and `scan:SCOPE_HASH`). `target` remains the readable issue ID/name. A display command is copyable text, **not** a shell string executed by `ll-next`. Store the exact intended operation in `action_key` (e.g. `format-issue`, `confidence-check`, or `manage-issue:implement`) for subsequent acceptance attribution.

Keep target deduplication separate from invocation matching. Preserve a typed action specification (slash arguments or shell argv) and an `action_fingerprint` from canonical semantic arguments, including a loop's resolved input/context. Canonicalize keyed context in sorted key order while retaining meaningful positional/list argument order. Exclude display quoting, ephemeral run IDs and timestamps from that fingerprint. Define one pure action grammar/parser/canonicalization module here, with render/parse round-trip fixtures for declared slash argument syntax and shell argv; FEAT-3711 and FEAT-3712 import it rather than inventing incompatible telemetry parsers. FEAT-3711 can match an offer only when evidence proves the required arguments; running the same loop name with different or unrecorded inputs is not exact acceptance. No new execution telemetry is required by this core.

| Verb | Candidate source / required action |
|---|---|
| `implement-issue` | Ready, unblocked leaf issue; emit all required `/ll:manage-issue TYPE ACTION ID` arguments (`BUG` → `bug fix`, `FEAT` → `feature implement`, `ENH` → `enhancement improve`). |
| `refine-issue` | Leaf issue needing formatting, verification, scoring or further refinement; reuse the existing ordered checks through a pure per-issue adapter. Missing readiness scores lead to `confidence-check`, never implementation. Record exhausted refinement caps as a diagnostic; do not silently repeat a capped step. |
| `resolve-blocker` | Root blocker of remaining active leaf issues. The target itself must have no unresolved dependencies. Recommend its per-issue refinement step if unready, otherwise the complete implementation invocation; label which dependent issues it would unlock. |
| `run-loop` | Existing valid runnable definition from configured loop sources, including never-run loops; history alone cannot resurrect deleted definitions. Resolve and validate every `required_inputs`/required-context value before emission; unresolved inputs exclude the candidate with a diagnostic. |

`generic` is not a verb; work outside the taxonomy can be captured as an issue. `pay-tech-debt`, `update-docs` and `meta` are deferred (FEAT-3714); `capture-issues` and `run-sprint` are FEAT-3713.

### Axes × verbs matrix (initial defaults)

Weights are initial defaults pinned by fixtures and overridable only through keyed `next` config (FEAT-3681 owns the config foundation; this issue adds consumed per-verb entries). They need not sum to 1: the geometric aggregate renormalizes present weights, including the implement column's intentional `0.95` total. `—` means inapplicable, excluded from that verb's coverage denominator.

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

### Snapshot and axis adapters

Capture one timezone-aware UTC `as_of` and load project state once. `ProjectState` contains parsed issue content/frontmatter, the full dependency graph, validated loop definitions, filesystem loop history, effective merged config and source diagnostics. Generators/scorers accept this state without reading the clock, cwd, live files or database themselves. This same seam permits FEAT-3712 to supply historical content. Avoid helpers such as the current autodev resolver that reload cwd/config or `is_formatted(path)` unless adapted to the injected content.

Assess each source-valid target once before filtering eligibility. An assessment retains gates, unresolved inputs and exclusion reasons, even when no runnable action can be constructed. Normal selection projects only eligible, fully resolved candidates; `--explain` renders the same assessment, including a source-valid loop with missing inputs or a rejected implementation gate. Do not discard rejected targets during generation and then implement a separate explain policy. A nonexistent target remains distinct from an existing but excluded target; explain may have `display_command=null`, while every selected recommendation must have a complete command.

The geometric helper in FEAT-3681 accepts only finite scores in `[0, 1]`. Its legacy next-loop curves are uncapped; **do not pass their values directly to the geometric scorer or change the old command to fix the arena**. Pin these arena-only defaults:

| Axis | Raw value and bounded curve |
|---|---|
| priority | `P0..P5` → `(5 - priority_int) / 5`; invalid/missing priority stays missing. |
| confidence / outcome | `outcome_confidence / 100` for a valid `0..100` value. `confidence_score` is the separate readiness gate, not an interchangeable score. |
| readiness-gap | Maximum normalized shortfall against readiness and outcome thresholds, each `max(0, (threshold - score) / max(threshold, 1))`; both valid scores required, otherwise missing. A valid outcome waiver removes the outcome shortfall. |
| leverage / fan-out | Number of distinct downstream `open`/`blocked` leaf issues through `blocked_by`, one-sided `blocks` and `depends_on`; `min(1, log1p(count) / log1p(10))`. Count each dependent once; report cycle/missing-node diagnostics separately. |
| effort, inverse | Explicit effort `1/2/3` → `1 / effort`; absent/invalid is missing. Do not infer effort from priority. |
| staleness | `min(1, age_days / 30)` from `captured_at`, then `discovered_date`, then git introduction time at the snapshot; never checkout mtime. |
| momentum | `exp(-log(2) * age_days / 7)` from the latest valid Session Log timestamp at/before `as_of`. |
| goal-alignment | New explicit numeric `next_goal_alignment` frontmatter override in `[0,1]`. Existing `product_impact.goal_alignment`/`goal_alignment` is a strategic-priority **string ID** and must not be coerced into this score. |
| loop frequency | `min(1, log1p(run_count) / log1p(50))` from valid filesystem run records. |
| loop recency | `exp(-log(2) * age_days / 7)` for the latest valid run start at/before `as_of`. |
| loop success | Fraction of recognized terminal runs (`completed`, `failed`, `timed_out`) with `status == completed`; unknown/in-flight/resumable (`interrupted`, `awaiting_continuation`) statuses do not count as failures. No recognized terminal runs means missing. |

Dates must have a documented UTC normalization (date-only capture/Session Log values mean midnight UTC; timestamp values without an offset use documented UTC interpretation with provenance). Malformed/future-only dates and absent history remain missing, with their reason; no fake zero recency or success `1.0` for unseen loops. Curves are fixed defaults in this slice; expose consumed per-verb weights/caps and the existing confidence thresholds, not unused configurable-curve/gate frameworks.

### Scoring, gates and coverage

- Use FEAT-3681's weighted geometric aggregate over present non-gate axes, weights renormalized after missing axes are excluded. No make-up term. An ordinary zero curve score uses the documented floor; only an explicit gate vetoes.
- Eligibility is explicit: issue action targets are `open` or `blocked` leaf issues; exclude `done`, `cancelled`, `deferred`, `in_progress` and EPIC containers. Build dependencies from **all** nonterminal statuses, including deferred, and resolve edges only against known `done`/`cancelled` issues. Unknown dependency IDs fail closed here, even though `DependencyGraph.from_issues` currently warns and drops them. Cycles yield diagnostics rather than an invented root blocker.
- Required gate results are `pass`, `fail` or `missing`, separate from numeric axes. `implement-issue` requires satisfied hard blockers **and** `depends_on`, and valid readiness/outcome scores against the effective merged confidence thresholds (defaults `85/65`); honor `outcome_gate_waived` for the outcome comparison only. Both score fields must still be present. This is the conservative arena policy, aligned with `check-readiness --honor-waiver`, not the readiness-only manage-issue/ll-auto gate. `commands.confidence_gate.enabled: false` does not make an unassessed issue ready for the arena. `resolve-blocker` requires satisfied dependencies; its displayed implementation step also requires these readiness checks. Non-negotiable eligibility/input checks cannot be disabled by weight `0` or a gate override.
- An explicit `status: blocked` independently vetoes implementation even if no dependency edge remains; expose that status instead of assuming its unspecified blocker vanished. A blocked issue can still be refined. A root-blocker implementation with this status is rejected until its blocking reason/status is resolved.
- Coverage stores `resolved_axes` and `applicable_axes` as integers plus a display string; count only applicable **positive-weight nongate** axes. The numeric coverage multiplier is `resolved_axes / applicable_axes`; effective positive-weight applicability must be nonempty after config validation. Within each verb, order scored candidates by `selection_score = utility × coverage`, then valid priority (where applicable, missing/invalid after valid priorities), then `target_key` ascending. `utility` is unmodified. An all-zero effective weight set is a config error, not cold start.
- Cold start is **per verb**: gate-passing candidates with no resolved scoring axes have `utility=null` and `selection_score=null`, sort after scored candidates in their bucket, and use priority/target-key fallback. This allows never-run loops even when issue buckets have data. Gates run first and are never bypassed by fallback. Exit 1 means no eligible candidate across the requested buckets, with distinct empty-source, gate-failed and gate-missing diagnostics.

### Cross-type fill (stateless)

Rank within each verb by `selection_score`; fill `--top N` slots by **round-robin in fixed canonical verb order** (`implement-issue`, `refine-issue`, `resolve-blocker`, `run-loop`), taking each verb's best remaining candidate per round, with a per-type cap (default 2, keyed config). A namespaced `target_key` appears at most once (first by round-robin order). On a duplicate, continue down that bucket without consuming a slot or its cap; stop only at N or exhaustion. Preserve alternate verbs/actions and the blocker fan-out reason on the selected target so deduplication does not hide its leverage. `--explain VERB TARGET` describes that candidate and the alternate candidates for the same target. Utility is never compared numerically across verbs. `pressure` is `null` here; FEAT-3711 can substitute a bucket order without changing candidate ranks or dedup semantics.

When `--top` is omitted, N is the number of requested buckets with eligible candidates (at least 1 for internal selection). This gives each available verb a first-round opportunity and prevents a hardcoded top-3 from starving `run-loop` and the two later verbs. An explicit `--top 3` retains a short list; canonical-order bias under an explicit limit is documented. Target dedup can make a verb unavailable; use its alternate-action annotation rather than duplicate a recommendation merely to fill every verb.

### CLI and data contract

- `ll-next [--json] [--top N] [--type VERB ...] [--explain VERB TARGET]` (default N=available requested buckets). Validate positive explicit N and caps, known verbs, and incompatible explain/top/type combinations at the CLI boundary. Explain evaluates the named source even if gates reject it; absent target exits 1 with a diagnostic. No `--execute`.
- Exit 0: recommendations/fallback or an existing candidate explanation emitted; exit 1: no eligible candidate or absent explain target; exit 2: config/usage error (concise stderr, empty stdout, no traceback). JSON is an envelope with `schema_version`, `as_of`, `selection_policy`, `recommendations`, and structured `diagnostics`; valid empty results still validate against the schema.
- Candidate fields: `action_type`, `action_key`, `action_fingerprint`, typed `action_spec`, `target`, `target_key`, `display_command`, `axes` (raw, curve, score, source, missing reason), `gates`, `utility`, `selection_score`, `bucket_rank`, `pressure` (null), `selection_reason`, `resolved_axes`, `applicable_axes`, alternate actions. Explain also exposes eligibility and exclusion reasons. Missing values serialize as `null`, never NaN/Infinity. The existing `ll-generate-schemas` flow only handles event schemas, so maintain a dedicated generated JSON Schema file with a drift test and package it for installed users.
- Render shell CLI actions from argv with `shlex.join`; render slash actions with their declared argument syntax. Do not copy next-loop's `json.dumps`/unquoted-context shell builder. Test spaces, quotes, dollar signs and backticks in targets/inputs as literal arguments.
- Add the CLI entry point, CLI reference, and permission/registry wiring. Every emitted loop action has its required arguments resolved or is excluded; test that invariant rather than assuming `ll-loop run NAME` is always runnable.
- This slice must avoid `cli_event_context`, write-capable history helpers and constructors that create directories. `--help`, text, JSON, explain and error paths perform no history access and no project writes. Read-only means no incidental telemetry or initialization.
- Extend FEAT-3681's deferred config resolver, typed config/property/export/serialization wiring and schema together for consumed `next.verbs`/selection settings. Unknown keys, nonfinite/negative/bool weights, invalid caps or all-zero effective weights exit 2 at the consumer; unrelated CLIs still construct config successfully. Preserve keyed local merges and leaf-null reset semantics.

Pin the consumed shape: `next.verbs.<verb>.weights.<axis>` uses the matrix above, `next.verbs.<verb>.cap=2` is a positive integer, and `next.verbs.refine-issue.refine_cap=5` is a positive integer also used for root-blocker refinement. Hard gates are fixed policy; readiness/outcome thresholds come from effective merged `commands.confidence_gate` and must be valid integers in `0..100`, excluding booleans. Do not add unspecified per-verb gate-disable switches. The legacy `next.loop_history.weights` remains independent. FEAT-3711/3713 extend this keyed shape only when their settings have consumers.

## Scope Boundaries

- **In scope:** four generators with explicit no-candidate cases, scorer integration, round-robin selection, advisory CLI/JSON Schema, deterministic fixed-clock fixtures, scaled performance gate, docs.
- **Out of scope:** scorer extraction/config foundation (FEAT-3681), history events/acceptance/pressure and the schema bump (FEAT-3711), the backtest (FEAT-3712), `capture-issues`/`run-sprint` (FEAT-3713), `pay-tech-debt`/`update-docs`/`meta` (FEAT-3714), `--execute`, LLM reranking, learned weights, parsing goals prose, the decision-rule gate, auto-clustered sprints.

## Integration Map

### Files to Modify

- New `little_loops.cli.next` module and pure snapshot/candidate-generator/selection modules; `scripts/pyproject.toml` entry point; CLI registration/permissions in `scripts/little_loops/init/writers.py`; `scripts/little_loops/config-schema.json` and `config/{features,core,__init__}.py` for consumed extensions to FEAT-3681's `next` object.
- Shared content-based refinement/formatting and source adapters around `cli/issues/next_action.py`, `issue_parser.py`, `session_log.py`, dependency graph and `cli/loop/next_loop.py`; adapt new consumers without changing the old commands' policy or output.
- Generated JSON Schema file for the output contract; `docs/reference/CLI.md`, `CONFIGURATION.md`, `API.md`.
- Tests for candidate sources, command-input invariants, gates/coverage/selection, schema drift, CLI registry/permissions, fixed-clock fixtures and the scaled performance ceiling.
- CLI-only: the skills/`ll-adapt` mirror gates do not apply; the CLI registry, permissions and `CLI.md` do.

### Similar Patterns and Configuration

- Reuse FEAT-3681's `utility/` aggregators and keyed config. Existing `next-*` commands remain untouched except shared pure helper imports.

## Program Design

### Types

- Immutable `ProjectState(as_of, config, issues, issue_contents, graph, loop_definitions, loop_history, diagnostics)`; no live I/O hidden in scoring/generation.
- `AxisScore(raw, curve, score, source, missing_reason)`, `GateResult(status, reason, source)`, typed action specifications, target assessments and `Candidate` with the exact fields in the CLI contract above are typed records with deterministic JSON serialization.

### Signatures

- `assess_candidates(state: ProjectState) -> list[CandidateAssessment]` — retains source-valid targets and their gate/input/exclusion evidence for both selection and explain.
- `generate_candidates(state: ProjectState) -> list[Candidate]` — projects eligible, fully resolved assessments; does not duplicate assessment logic.
- `select_candidates(candidates: list[Candidate], *, top: int | None, bucket_order: Sequence[str], caps: Mapping[str, int]) -> list[Candidate]` — applies gates, coverage ordering, omitted-top policy and round-robin fill without cross-type utility comparison; later pressure changes only `bucket_order`.

### Call Path

Existing `cmd_next_loop` / `find_issues` source paths → new `generate_candidates` → FEAT-3681's utility scorer → `select_candidates` → human/JSON rendering. No event is written.

## Implementation Steps

1. Land FEAT-3681; pin the snapshot, axis adapters, eligibility/readiness policy, matrix and consumed config. Schema/rebuild safety belongs to the events slice; ENH-3678 is related background here.
2. Implement the four generators as independently testable functions, then score/rank/select with no-candidate and missing-data semantics.
3. Add advisory `ll-next`, generated JSON Schema, registration/permissions/docs.
4. Run fixed fixtures and a serial synthetic performance gate: 10,000 issues, 20,000 dependency edges, 200 loop definitions and 10,000 filesystem run records, ≤30 seconds excluding fixture construction on the test runner. Also assert one parse per issue and O(1) git subprocess calls (≤4 regardless of issue count); batch metadata reads rather than per-file git calls. Perform no network/database access. Confirm the four `next-*` CLIs are unchanged.

## Impact

- **Priority:** P3 — useful project-wide decision support with an advisory first release.
- **Effort:** Medium–Large — four generators, new CLI, schema, docs.
- **Risk:** Medium — false precision and stale signals can yield persuasive but wrong rankings; mitigated by explicit missing-data states and no persisted state.
- **Breaking Change:** No; existing recommenders keep their output.

## Use Case

A user runs `ll-next` and each available action bucket gets a first-round opportunity; `--top 3` requests a shorter list. They inspect evidence with `ll-next --explain VERB TARGET`. No action runs automatically and nothing is written.

## Acceptance Criteria

- [ ] FEAT-3681's scorer/config foundation is landed; the four verbs' per-verb `next` config entries and the axes × verbs matrix defaults are in `config-schema.json` and pinned by fixtures.
- [ ] All four verbs have tested candidate sources and explicit empty-source behavior; complete slash arguments and shell quoting are verified. Deleted/invalid loops and unresolved inputs never emit runnable commands; never-run valid loops use per-bucket fallback. `--execute` is absent.
- [ ] Bounded axis adapters, separate tri-state gates and positive-weight coverage follow the contracts above; missing/zero/invalid/future inputs differ explicitly, all-zero weights fail at the consumer, and legacy curves remain unchanged.
- [ ] Eligibility/readiness tests cover EPICs, in-progress/deferred targets, deferred/missing/external dependencies, depends_on, one-sided blocks, cycles, absent versus zero scores, local threshold overrides and outcome waiver. Fallback never bypasses a veto/missing gate.
- [ ] Round-robin fill follows the canonical verb order with the per-type cap and at-most-once-per-target rule; no cross-verb utility comparison.
- [ ] Namespaced dedup refills past duplicates without spending caps; alternate actions/blocker reasons survive. Injected snapshots, shuffled source order and a fixed UTC clock yield deterministic ranks/output in live and reconstructed states.
- [ ] Human/JSON/explain/empty/error modes, installed output Schema (with drift test), config root/export/merge/reset/serialization, registry/permissions and docs pass focused tests. All paths perform no `history.db` access and no writes, including incidental CLI telemetry.
- [ ] Explain uses the shared assessment path for rejected gates, unresolved loop inputs and capped refinement; selected recommendations always have complete actions. Typed action/fingerprint tests distinguish parameter changes from display-quoting changes, and pin consumed caps/refinement limits/threshold validation.
- [ ] Fixed-clock missing-gate/zero-score/mixed-bucket cold-start fixtures and the quantified scaled performance gate pass without network access.
- [ ] The four existing `next-*` CLIs remain behavior-identical; `python -m pytest scripts/tests/` passes.

## Related

- EPIC-3710 (parent). FEAT-3681 (scorer extraction; prerequisite), ENH-3678 (done; schema-bump safety, relevant to FEAT-3711). FEAT-3711, FEAT-3712, FEAT-3713 (follow-on slices); FEAT-3714 (deferred finding-backed verbs).

## Review Notes

- 2026-10-03: Pre-implementation review corrected the `next-action` source contract, bounded all arena curves, separated gates from axes, defined snapshot/target/action identity, per-bucket cold start, exact invocations and read-only/config/performance gates. Kept the advisory four-verb slice and legacy CLI compatibility.
- 2026-10-03: Follow-up review separated source assessment from eligibility so explain retains rejected targets, pinned argument-aware action identity and the numeric coverage multiplier, and specified consumed cap/refinement settings without an unused gate-disable framework.

## Status

**Open** | Created: 2026-09-24 | Priority: P3
