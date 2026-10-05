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
- FEAT-3713
- FEAT-3721
relates_to:
- FEAT-3714
- FEAT-3722
- ENH-3678
parent: EPIC-3710
---

# FEAT-3561: ll-next core with deterministic cross-verb recommendations

## Summary

Build the stateless, advisory `ll-next` CLI: four candidate generators (`implement-issue`, `refine-issue`, `resolve-blocker`, `run-loop`), deterministic per-verb scoring on FEAT-3681's scorer, gates and coverage, a fixed round-robin cross-type fill, and a generated JSON Schema. This is part (a) of EPIC-3710 after an Opus pre-implementation review (2026-10-03) split the original nine-verb scope. It writes **no** history events and bumps **no** schema version. Events/explicit acceptance are FEAT-3711; pressure is deferred as FEAT-3722; the backtest FEAT-3712 was cancelled after a source-audit no-go; `capture-issues`/`run-sprint` are FEAT-3713; the finding-backed verbs are deferred as FEAT-3714.

## Current Behavior

`ll-issues next-issue`/`next-issues` rank implementation targets, `ll-issues next-action` selects the first refinement step across the active backlog, and `ll-loop next-loop` scores loop runs. No command compares action types. `next-action` has no per-issue target argument; the arena needs a pure per-issue adapter rather than calling that CLI for every candidate.

## Expected Behavior

`ll-next` emits up to N recommendations with an action type, target, copyable invocation/instruction, per-axis evidence, within-type utility, coverage, bucket rank and selection reason. It is **advisory only**; `--execute` is deferred until each verb has a typed, safe dispatcher. All four existing `next-*` CLIs keep their behavior. Missing data, unavailable goals and missing gates stay explicit rather than becoming guessed scores or negative outcomes. The command reads project files and git only: no `history.db` access, no writes.

## Motivation

A user deciding what to do next needs a legible choice across implementation, refinement, blockers and loops. Shipping the deterministic, stateless core first keeps the release inspectable, avoids the schema-bump and acceptance-attribution risk, and lets FEAT-3721/3711/3713 build on a stable candidate/score contract.

## Proposed Solution

### Action taxonomy and candidate sources

Each generator specifies its target and a copyable action; it yields no candidate when its source is absent and never invents required arguments. Candidate identity is `(action_type, target_key)`, where `target_key` is namespaced (`issue:FEAT-123`, `loop:NAME`; follow-ups add `sprint:NAME` and `scan:SCOPE_HASH`). `target` remains the readable issue ID/name. A display command is copyable text, **not** a shell string executed by `ll-next`. Store the exact intended operation in `action_key` (e.g. `format-issue`, `confidence-check`, or `manage-issue:implement`) for subsequent acceptance attribution.

Keep target deduplication separate from invocation matching. Preserve a typed action specification (slash arguments or shell argv, plus `working_directory`) and an `action_fingerprint` from canonical semantic arguments, including a loop's resolved input/context, effective definition source and SHA-256 content digest. Canonicalize keyed context in sorted key order while retaining meaningful positional/list argument order. Exclude display quoting, ephemeral run IDs and timestamps from that fingerprint. Define one pure action grammar/parser/canonicalization module here, with render/parse round-trip fixtures for declared slash argument syntax and shell argv; FEAT-3711 preserves this identity. The cancelled FEAT-3712 would reuse it for label parsing if revisited, but requires no additional core work. Automatic invocation matching belongs to deferred FEAT-3722 and requires evidence of all semantic arguments; running the same loop name with different or unrecorded inputs is not exact acceptance. No new execution telemetry is required by this core.

Fingerprint a registered semantic projection of the action specification rather than every serialized assessment field. Source/scope identity is supplied by the injected snapshot; parsing a displayed command does not recover the historical definition bytes or ambient config and must perform no hidden I/O. Mutable assessment provenance can accompany the immutable offer without becoming fingerprint material. FEAT-3713 extends this seam with sprint source/digest identity and scan scope identity; assessed member-status snapshots remain provenance. Core render/parse fixtures pin literal command arguments and core loop identity, while the consuming child owns fixtures for its new action variant.

Resolve the project root once at the CLI boundary using the existing `paths.find_project_root` lookup before constructing config/state; with no configured root, return exit 2 with a concise diagnostic and no initialization. Root/subdirectory invocations must see the same project/config/sources, while a nested repository must not inherit an outer project's root. Include `project_root` in the envelope and the canonical root as every action's `working_directory`. Human output states that copied actions run from that directory: existing `ll-loop`/`ll-sprint` commands do not uniformly resolve an ancestor project from cwd. Do not invent a shared project-root flag or change those executors in this issue.

| Verb | Candidate source / required action |
|---|---|
| `implement-issue` | Ready, unblocked leaf issue; emit all required `/ll:manage-issue TYPE ACTION ID` arguments (`BUG` → `bug fix`, `FEAT` → `feature implement`, `ENH` → `enhancement improve`). |
| `refine-issue` | Leaf issue needing formatting, verification, scoring or further refinement; reuse the existing ordered checks through a pure per-issue adapter. Missing readiness scores lead to `confidence-check`, never implementation. Apply the arena's outcome-waiver policy to the score comparison so a valid waived outcome does not cause endless refinement. Record exhausted refinement caps as a diagnostic; do not silently repeat a capped step. |
| `resolve-blocker` | Root blocker of remaining active leaf issues. The target itself must have no unresolved dependencies. Recommend its per-issue refinement step if unready, otherwise the complete implementation invocation; distinguish direct prerequisite satisfaction from downstream reachability; report bounded affected-dependent samples and saturated counts. |
| `run-loop` | Existing valid runnable definition from configured loop sources, including never-run loops; history alone cannot resurrect deleted definitions. Resolve and validate every `required_inputs`/required-context value before emission; unresolved inputs exclude the candidate with a diagnostic. |

For loops, snapshot the runtime's actual resolution order (`fsm.loop_paths.resolve_loop_path`: direct path, compiled `.fsm.yaml`, project YAML, built-in, then generator draft). Assess at most one effective definition per command target and report shadowed definitions; never validate one source and emit a name that invokes another. Use the effective command target selected by that resolver and retain its resolved path/digest as provenance. Do not emit a shadowed definition or invent a source-selection flag; unsupported/unrepresentable targets remain excluded. Resolve effective context in the runner's order (parameter defaults, positional input, injected `program.md`, explicit context, config/runtime defaults); share/adapt pure helpers rather than launching `cmd_run` or its write-capable loaders. Required context with interpolation fallback/nullable suffixes is optional under the existing parser. Fixture a project/built-in collision, compiled/project collision, duplicate drafts and a direct-path collision from the stated working directory. v1 does not match archived run records to a definition content version; name-based historical evidence is labeled as such, not proof of the current definition's success.

`generic` is not a verb; work outside the taxonomy can be captured as an issue. `pay-tech-debt`, `update-docs` and `meta` are deferred (FEAT-3714); `capture-issues` and `run-sprint` are FEAT-3713.

### Axes × verbs matrix (initial defaults)

Weights are initial defaults pinned by fixtures and overridable only through keyed `next` config (FEAT-3681 owns the config foundation; this issue adds consumed per-verb entries). Each verb's default weights **sum to 1.0** (the geometric aggregate still renormalizes present weights when an axis is missing). `—` means inapplicable.

| Axis (source) | implement-issue | refine-issue | resolve-blocker | run-loop |
|---|---|---|---|---|
| priority (canonical filename, then frontmatter) | 0.30 | 0.30 | 0.25 | — |
| confidence / outcome (frontmatter scores) | 0.30 | — | — | — |
| readiness-gap (frontmatter scores vs `commands.confidence_gate`) | — | 0.30 | — | — |
| leverage / fan-out (dependency graph) | 0.20 | 0.15 | 0.50 | — |
| effort, inverse (Impact-section `**Effort**:` field, strict map) | 0.10 | — | 0.15 | — |
| staleness (capture date) | — | 0.15 | 0.05 | — |
| momentum (Session Log timestamps in the issue file) | 0.10 | 0.10 | 0.05 | — |
| frequency / recency / success (`next-loop` history) | — | — | — | 0.50 / 0.30 / 0.20 |

**No goal-alignment axis in v1.** A repo scan (2026-10-03) found `next_goal_alignment` in 0 of 3622 issues and a prose `.ll/ll-goals.md` has no parser, so the axis would be missing for every candidate. Do not add the `next_goal_alignment` frontmatter field; revisit when a goals/EPIC-map syntax and parser exist. The decision-rule compliance gate and the decisions-based historical-signal axis are **out of scope**: decision rules carry only issue-scoped structure today, so compliance cannot be evaluated deterministically. Revisit once rules have machine-evaluable scope.

### Snapshot and axis adapters

Capture one timezone-aware UTC `as_of` and load project state once. `ProjectState` contains parsed issue content/frontmatter, the full dependency graph, validated loop definitions, filesystem loop history, effective merged config and source diagnostics. Generators/scorers accept this state without reading the clock, cwd, live files or database themselves. This seam also supports injected/historical fixtures without implementing the cancelled backtest. Avoid helpers such as the current autodev resolver that reload cwd/config or `is_formatted(path)` unless adapted to the injected content.

Resolve priority with the shared `issue_parser.resolve_priority` authority: a valid canonical filename prefix wins over frontmatter, then valid frontmatter is the fallback. Pass `default=None` in the arena adapter; do not trust `IssueInfo.priority_int` after its parser has substituted the lowest configured priority for missing/invalid metadata. Record the chosen source and any filename/frontmatter disagreement. Use this same resolved value for priority axes, tie-breaking, minimum evidence and sprint mean priority; a missing value stays missing rather than becoming a present P5. The axis table does not introduce a frontmatter-only policy.

Assess each source-valid target once before filtering eligibility. An assessment retains gates, unresolved inputs and exclusion reasons, even when no runnable action can be constructed. Normal selection projects only eligible, fully resolved candidates; `--explain` renders the same assessment, including a source-valid loop with missing inputs or a rejected implementation gate. Do not discard rejected targets during generation and then implement a separate explain policy. A nonexistent target remains distinct from an existing but excluded target; explain may have `display_command=null`, while every selected recommendation must have a complete command.

The geometric helper in FEAT-3681 accepts only finite scores in `[0, 1]`. Its legacy next-loop curves are uncapped; **do not pass their values directly to the geometric scorer or change the old command to fix the arena**. Pin these arena-only defaults:

**Lower-bounded curves (Opus review, 2026-10-03).** The geometric mean floors a zero axis at `1e-6`, so a raw curve that reaches 0 acts as a near-veto: with the old curves a leaf with no dependents took a 6.6× penalty on leverage (`1e-6^0.15 = 0.126` vs `0.83` at one dependent), P5 took `0.016` vs P4 `0.617`, and a fresh issue took `0.126` on staleness. Every non-gate curve below is therefore mapped into `[lo, 1]` (`lerp(lo, 1, x)` = `lo + (1 - lo)·x`) so a worst-case value never collapses the score; the `1e-6` floor remains only a guard for degenerate input. **Policy at nominal default weights on a complete axis set:** for every non-gate axis with weight `w`, `(score_at_worst / score_at_best)^w ≥ 0.6`; pin this with a property test over the default weights, and record the `lo` values. If P5 should be excluded from recommendations, that must be an explicit gate, not a curve side effect.

| Axis | Raw value and bounded curve |
|---|---|
| priority | `x = (5 - priority_int) / 5` for `P0..P5`; score `lerp(0.2, 1, x)`. Invalid/missing priority stays missing. |
| confidence / outcome | `x = outcome_confidence / 100` for a valid `0..100` value; score `lerp(0.2, 1, x)`. `confidence_score` is the separate readiness gate, not an interchangeable score. |
| readiness-gap | `x` = maximum normalized shortfall against readiness and outcome thresholds, each `max(0, (threshold - score) / max(threshold, 1))`; score `lerp(0.2, 1, x)`. Both valid scores required, otherwise missing. A valid outcome waiver removes the outcome shortfall. |
| leverage / fan-out | `x = min(1, log1p(count) / log1p(10))` over distinct downstream `open`/`blocked` leaf issues through `blocked_by`, one-sided `blocks` and `depends_on`; score `lerp(0.5, 1, x)`. Traverse only nonterminal nodes. Count exactly below 10; at saturation report `count_lower_bound=10`, `saturated=true` and `≥10` with a bounded sample, never an invented exact total. Count each dependent once; report cycle/missing-node diagnostics separately. Zero dependents is a valid present value (score 0.5), not missing. |
| effort, inverse | Parse the Impact-section `- **Effort**:` field (present in ~2742 of 3622 issues; the numeric/`effort` frontmatter is effectively absent) by a **strict leading-token map**, case-insensitive: `trivial`/`small`/`low`/`s` → 1, `medium`/`m` → 2, `large`/`high`/`l` → 3 (a range such as `small-medium` or `Medium–Large` takes its first token; anything else is missing, with the raw text retained as the missing reason). Score `1 / effort`. Never infer effort from priority, and do not use `IssueInfo.effort`'s priority-inferred fallback. If the adapter proves unreliable in fixtures, cut the axis rather than widen the map. |
| staleness | `x = min(1, age_days / 30)` from `captured_at`, then `discovered_date`, then git introduction time at the snapshot; never checkout mtime. Score `lerp(0.3, 1, x)`. |
| momentum | `x = exp(-log(2) * age_days / 7)` from the latest valid Session Log timestamp at/before `as_of`; score `lerp(0.3, 1, x)`. |
| loop frequency | `x = min(1, log1p(run_count) / log1p(50))` from valid filesystem run records; score `lerp(0.4, 1, x)`. A loop with no valid run records has **all three loop axes missing** (cold start), never a present zero. |
| loop recency | `x = exp(-log(2) * age_days / 7)` for the latest valid run start at/before `as_of`; score `lerp(0.2, 1, x)`. |
| loop success | `x` = fraction of recognized terminal runs (`completed`, `failed`, `timed_out`) with `status == completed`; score `lerp(0.2, 1, x)`. Unknown/in-flight/resumable (`interrupted`, `awaiting_continuation`) statuses do not count as failures. No recognized terminal runs means missing. |

The run-loop verb **reuses FEAT-3681's pure curve primitives** as a thin adapter, then applies the bounded mapping above; it must not become a second independent curve/scorer implementation. Its input qualification is intentionally arena-specific: legacy `_score_loop` counts every run in its success denominator and selects dates lexically, whereas the arena normalizes dates, filters at `as_of`, and uses recognized terminal runs only. Do not reuse that legacy aggregate or its precomputed success rate as arena evidence. Retain the raw run records in ProjectState and test the two policies side by side without changing legacy behavior.

The worst/best-factor property uses the **nominal default weights on a complete axis set**, including loop frequency's `0.4` floor (`0.4^0.5 ≈ 0.632`). Missing-axis renormalization and user weight overrides can increase an axis's effective influence; report the effective weights in explain rather than claiming the `0.6` factor holds for those cases. All non-gate curves still have a positive floor.

The pure refinement adapter uses the arena readiness result for its score-driven step. A ready issue with a valid outcome waiver gets no repeated confidence/refinement action merely because its waived outcome is below threshold; formatting/verification checks remain independently applicable. Preserve this intentional arena policy difference from legacy next-action in a fixed fixture.

Dates must have a documented UTC normalization (date-only capture/Session Log values mean midnight UTC; timestamp values without an offset use documented UTC interpretation with provenance). Malformed/future-only dates and absent history remain missing, with their reason; no fake zero recency or success `1.0` for unseen loops. Curves are fixed defaults in this slice; expose consumed per-verb weights/caps and the existing confidence thresholds, not unused configurable-curve/gate frameworks.

### Scoring, gates and coverage

- Use FEAT-3681's weighted geometric aggregate over present non-gate axes, weights renormalized after missing axes are excluded. No make-up term. An ordinary zero curve score uses the documented floor; only an explicit gate vetoes.
- Eligibility is explicit: issue action targets are `open` or `blocked` leaf issues; exclude `done`, `cancelled`, `deferred`, `in_progress` and EPIC containers. Build dependencies from **all** nonterminal statuses, including deferred, and resolve edges only against known `done`/`cancelled` issues. Unknown dependency IDs fail closed here, even though `DependencyGraph.from_issues` currently warns and drops them. Cycles yield diagnostics rather than an invented root blocker.
- Required gate results are `pass`, `fail` or `missing`, separate from numeric axes. `implement-issue` requires satisfied hard blockers **and** `depends_on`, and valid readiness/outcome scores against the effective merged confidence thresholds (defaults `85/65`); honor `outcome_gate_waived` for the outcome comparison only. Both score fields must still be present. This is the conservative arena policy, aligned with `check-readiness --honor-waiver`, not the readiness-only manage-issue/ll-auto gate. `commands.confidence_gate.enabled: false` does not make an unassessed issue ready for the arena. `resolve-blocker` requires satisfied dependencies; its displayed implementation step also requires these readiness checks. Non-negotiable eligibility/input checks cannot be disabled by weight `0` or a gate override.
- Validate the raw readiness/outcome domains once for both gates and axes: integers or digit strings representing `0..100`, excluding booleans, floats, negatives, values above 100 and nonfinite values. Preserve absent versus invalid reasons; an invalid high score cannot pass a gate or be clamped into valid evidence. A waiver is only boolean true or the case-insensitive string `true`; other truthy values do not waive anything. Invalid/missing scores request `confidence-check` and never reach numeric scoring as trusted values. Do not rely on existing coercers, which accept out-of-range digit values.
- An explicit `status: blocked` independently vetoes implementation even if no dependency edge remains; expose that status instead of assuming its unspecified blocker vanished. A blocked issue can still be refined. A root-blocker implementation with this status is rejected until its blocking reason/status is resolved.
- Coverage is **reported, not multiplied**. Store `resolved_axes` and `applicable_axes` as integers plus a display string (counting only applicable **positive-weight nongate** axes) for output and `--explain`. There is **no coverage multiplier**: renormalization already handles missing axes, and a multiplier would penalize the same gap twice and rank issues down for metadata hygiene (e.g. ~half of issues lack `captured_at`). Instead the **per-verb minimum-coverage table below** applies. A candidate below the minimum is treated as cold start (below), not excluded. Within each verb, order scored candidates by `selection_score = utility` (kept as a distinct field equal to `utility` for contract stability, so later slices can adjust it without a schema change), then valid priority (where applicable, missing/invalid after valid priorities), then `target_key` ascending. For these scored verbs, effective positive-weight applicability must be nonempty after config validation; an all-zero effective weight set is a config error, not cold start. FEAT-3713's evidence-only scan singleton has no weights and is an explicit extension of this contract.
- Cold start is **per verb**: gate-passing candidates with no resolved scoring axes, or below the minimum-coverage rule, have `utility=null` and `selection_score=null`, sort after scored candidates in their bucket, and use priority/target-key fallback. This allows never-run loops even when issue buckets have data. Gates run first and are never bypassed by fallback. Exit 1 means no eligible candidate across the requested buckets, with distinct empty-source, gate-failed and gate-missing diagnostics.

| Verb | Minimum evidence for numeric utility after eligibility gates |
|---|---|
| implement-issue / refine-issue / resolve-blocker | Valid priority metadata plus at least one resolved **positive-weight** non-priority axis. Priority counts in coverage only when its weight is positive; disabling that weight does not disable the metadata prerequisite or force an otherwise scorable issue into fallback. |
| run-loop | At least one resolved positive-weight history axis. |

Missing minimum evidence yields the documented null-utility fallback, not an eligibility veto. Later verbs declare their own rows; do not apply the issue-priority requirement to every future action type.

### Cross-type fill (stateless)

Rank within each verb by `selection_score`; fill `--top N` slots by **round-robin in fixed canonical verb order** (`implement-issue`, `refine-issue`, `resolve-blocker`, `run-loop`), taking each verb's best remaining candidate per round, with a per-type cap (default 2, keyed config). A namespaced `target_key` appears at most once (first by round-robin order). On a duplicate, continue down that bucket without consuming a slot or its cap; stop only at N or exhaustion. Preserve alternate verbs/actions and the blocker fan-out reason on the selected target so deduplication does not hide its leverage. `--explain VERB TARGET` describes that candidate and the alternate candidates for the same target. Utility is never compared numerically across verbs. `pressure` is `null` here; `bucket_order` is an input so a later slice could substitute an order without changing candidate ranks or dedup semantics (the pressure feature itself is deferred as FEAT-3722).

When `--top` is omitted, perform exactly one pass through requested buckets: each contributes its best remaining nonduplicate target, or nothing. Continue within that bucket past duplicates, but do not start a second round to pad a dedup-exhausted bucket with another implementation target. An empty pass exits 1. This gives each available verb a first-round opportunity and prevents a hardcoded top-3 from starving `run-loop` and the two later verbs. Explicit `--top N` uses multi-round fill/caps up to N or exhaustion; canonical-order bias under an explicit short limit is documented. Target dedup can make a verb unavailable; preserve its alternate-action annotation.

### CLI and data contract

- `ll-next [--json] [--top N] [--type VERB ...] [--explain VERB TARGET]` (default: one pass through requested buckets). Validate positive explicit N and caps, known verbs, and incompatible explain/top/type combinations at the CLI boundary. Explain evaluates the named source even if gates reject it; absent target exits 1 with a diagnostic. No `--execute`.
- Exit 0: recommendations/fallback or an existing candidate explanation emitted; exit 1: no eligible candidate or absent explain target; exit 2: config/usage error (concise stderr, empty stdout, no traceback). JSON is an envelope with `schema_version`, `project_root`, `as_of`, `selection_policy`, `recommendations`, and structured `diagnostics`; valid empty results still validate against the schema.
- Candidate fields: `action_type`, `action_key`, `action_fingerprint`, typed `action_spec`, `target`, `target_key`, `display_command`, `axes` (raw, curve, score, configured weight, effective renormalized weight, source, missing reason), `gates`, `utility`, `selection_score`, `bucket_rank`, `pressure` (null), `selection_reason`, `resolved_axes`, `applicable_axes`, alternate actions and a per-verb `evidence` object (already consumed by blocker fan-out and loop-source/input evidence). Explain also exposes eligibility and exclusion reasons. Missing values serialize as `null`, never NaN/Infinity. The existing `ll-generate-schemas` flow only handles event schemas, so maintain a dedicated generated JSON Schema file with a drift test and package it for installed users.
- Render shell CLI actions from argv with `shlex.join`; render slash actions with their declared argument syntax. Do not copy next-loop's `json.dumps`/unquoted-context shell builder. Test spaces, quotes, dollar signs and backticks in targets/inputs as literal arguments. Quoting alone does not prevent option parsing: place modeled options before a supported `--` terminator and positional operands after it, or exclude an operand that cannot be represented faithfully. Parser fixtures must prove leading-dash names/inputs cannot become flags and recover the intended target/inputs without executing the action.
- Add the CLI entry point, CLI reference, and permission/registry wiring. Every emitted loop action has its required arguments resolved or is excluded; test that invariant rather than assuming `ll-loop run NAME` is always runnable.
- This slice must avoid `cli_event_context`, write-capable history helpers and constructors that create directories. `--help`, text, JSON, explain and error paths perform no history access and no project writes. Read-only means no incidental telemetry or initialization.
- Extend FEAT-3681's deferred config resolver, typed config/property/export/serialization wiring and schema together for consumed `next.verbs`/selection settings. Unknown keys, nonfinite/negative/bool weights, invalid caps or all-zero effective weights exit 2 at the consumer; unrelated CLIs still construct config successfully. Preserve keyed local merges and leaf-null reset semantics.

Pin the consumed shape: `next.verbs.<verb>.weights.<axis>` uses the matrix above, `next.verbs.<verb>.cap=2` is a positive integer, and `next.verbs.refine-issue.refine_cap=5` is a positive integer also used for root-blocker refinement. Hard gates are fixed policy; readiness/outcome thresholds come from effective merged `commands.confidence_gate` and must be valid integers in `0..100`, excluding booleans. Do not add unspecified per-verb gate-disable switches. The legacy `next.loop_history.weights` remains independent. FEAT-3711/3713 extend this keyed shape only when their settings have consumers.

The core owns one verb registry from which CLI type/explain choices, output-schema action enums and consumed config keys are derived; follow-ons extend this registry rather than duplicating closed verb lists. Build the bare recommendation invocation and future accept/feedback dispatch seam here without implementing those subcommands. `schema_version` is a positive integer; each published contract change (including added verbs) claims the next output version, independent of the history DB schema. FEAT-3711/3713 extend the current generated schema and fixtures after rebasing; do not overwrite a sibling's fields. Reserve no unused recording settings or pressure implementation. The core itself remains history-free; follow-ons own the paths that add reads/writes.

Fan-out is affected downstream reachability, not proof that completing the target immediately makes every descendant implementable. Report direct dependents whose entire pending prerequisite set is this target separately; retain independent status/readiness vetoes. Alternate-action/blocker annotations must not call a multi-blocked or transitive descendant immediately unlocked.

## Scope Boundaries

- **In scope:** four generators with explicit no-candidate cases, scorer integration, round-robin selection, advisory CLI/JSON Schema, deterministic fixed-clock fixtures, scaled performance gate, docs.
- **Out of scope:** scorer extraction/config foundation (FEAT-3681), history events/explicit acceptance and the schema bump (FEAT-3711), the shared history reader (FEAT-3721), pressure/automatic attribution (FEAT-3722, deferred), the backtest (FEAT-3712), `capture-issues`/`run-sprint` (FEAT-3713), `pay-tech-debt`/`update-docs`/`meta` (FEAT-3714), `--execute`, LLM reranking, learned weights, parsing goals prose, the decision-rule gate, auto-clustered sprints.

## Integration Map

### Files to Modify

- New `little_loops.cli.next` module and pure snapshot/candidate-generator/selection modules; `scripts/pyproject.toml` entry point; CLI registration/permissions in `scripts/little_loops/init/writers.py`; `scripts/little_loops/config-schema.json` and `config/{features,core,__init__}.py` for consumed extensions to FEAT-3681's `next` object.
- Shared content-based refinement/formatting and source adapters around `cli/issues/next_action.py`, `issue_parser.py`, `session_log.py`, dependency graph and `cli/loop/next_loop.py`; adapt new consumers without changing the old commands' policy or output.
- Generated JSON Schema file for the output contract; `docs/reference/CLI.md`, `CONFIGURATION.md`, `API.md`.
- Tests for candidate sources, command-input invariants, gates/coverage/selection, schema drift, CLI registry/permissions, fixed-clock fixtures and the structural performance checks and the `perf`-marked scaled gate.
- CLI-only: the skills/`ll-adapt` mirror gates do not apply; the CLI registry, permissions and `CLI.md` do.

### Similar Patterns and Configuration

- Reuse FEAT-3681's `utility/` aggregators and keyed config. Existing `next-*` commands remain untouched except shared pure helper imports.

## Program Design

### Types

- Immutable `ProjectState(project_root, as_of, config, issues, issue_contents, graph, loop_definitions, loop_history, diagnostics)`; no live I/O hidden in scoring/generation.
- `AxisScore(raw, curve, score, configured_weight, effective_weight, source, missing_reason)`, `GateResult(status, reason, source)`, typed action specifications, target assessments and `Candidate` with the exact fields in the CLI contract above are typed records with deterministic JSON serialization.

### Signatures

- `assess_candidates(state: ProjectState) -> list[CandidateAssessment]` — retains source-valid targets and their gate/input/exclusion evidence for both selection and explain.
- `generate_candidates(state: ProjectState) -> list[Candidate]` — projects eligible, fully resolved assessments; does not duplicate assessment logic.
- `select_candidates(candidates: list[Candidate], *, top: int | None, bucket_order: Sequence[str], caps: Mapping[str, int]) -> list[Candidate]` — uses the shared eligibility assessment and applies coverage ordering, one-pass omitted-top policy and explicit-N round-robin fill without cross-type utility comparison; a later slice may change only `bucket_order`.

### Call Path

Existing `cmd_next_loop` / `find_issues` source paths → new `generate_candidates` → FEAT-3681's utility scorer → `select_candidates` → human/JSON rendering. No event is written.

## Implementation Steps

1. Land FEAT-3681; pin the snapshot, axis adapters, eligibility/readiness policy, matrix and consumed config. Schema/rebuild safety belongs to the events slice; ENH-3678 is related background here.
2. Implement the four generators as independently testable functions, then score/rank/select with no-candidate and missing-data semantics. Include one shared verb registry and the command dispatch/schema extension seam for follow-ons.
3. Add advisory `ll-next`, generated JSON Schema, registration/permissions/docs.
4. Run fixed fixtures and the performance checks. **Default suite** (no wall-clock limit; the repo's file-creation volume previously beach-balled the Mac and a 30 s limit would be flaky on GitHub runners): (a) assert one parse per issue by counting parse calls, (b) assert ≤4 batched git subprocess calls for the core regardless of issue count by monkeypatching `subprocess`, (c) deterministic operation-count checks on injected issues/graph at ~500 vs ~5,000, covering chains, shared-descendant DAGs, fan-out and cycles rather than a timing ratio; compute saturated distinct reachability with bounded sets over an SCC-condensed DAG instead of one unbounded DFS per candidate. Exclude the source itself, preserve cycle diagnostics, and prove a constant-size reachability summary suffices for the curve (allow one extra retained ID when excluding self). Cache graph analysis once. The linear-work claim applies to these capped summaries, not arbitrary exact transitive counts/lists; (d) a small filesystem smoke test of ~200 files. **`@pytest.mark.perf`**: register the currently absent marker and add an explicit opt-in collection gate such as `--run-perf`; marking alone does not exclude a test. The opt-in full 10,000 issues / 20,000 edges / 200 loop definitions / 10,000 run records ≤30 s gate excludes fixture construction and is run manually before release. Batch git metadata reads rather than per-file calls; perform no network/database access. Confirm the four `next-*` CLIs are unchanged.
5. **Walking-skeleton usefulness checkpoint** before FEAT-3721/3711/3713 start: with implement-issue, refine-issue and `--explain` working, compare `ll-next --type implement-issue --top 3` with `ll-issues next-issues 3` on one recorded backlog snapshot/config/as_of. Report eligibility/population differences separately and also compare both ranking rules on the core's common eligible population, so stricter gates are not mistaken for better ranking. Inspect mixed implement/refine output and fixed scenarios with ready, unready, blocked and cold-start targets for usable complete actions, per-verb counts, availability and explanations. Record the comparison and a maintainer go/pause decision in Resolution notes. Agreement within the implementation bucket alone is not evidence the cross-verb arena lacks value, and next-issue has no refinement ranking to compare. The cancelled FEAT-3712 requires no implementation or checkpoint. Do not silently proceed with active follow-ons before recording the checkpoint decision.

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
- [ ] Lower-bounded axis adapters, separate tri-state gates and the minimum-coverage rule (no coverage multiplier; coverage reported) follow the contracts above; missing/zero/invalid/future inputs differ explicitly, all-zero weights fail at the consumer, and legacy curves remain unchanged. A property test over the default weights asserts `(worst/best)^w ≥ 0.6` for every non-gate axis and that per-verb default weights sum to 1.0; zero-dependent leaves and P5 issues are not silently vetoed. The Impact-section effort adapter has fixtures for `small — …`, `small-medium`, `Medium–Large`, unknown text (missing) and absence (missing); there is no `next_goal_alignment` field.
- [ ] Priority fixtures pin filename-over-frontmatter authority, valid frontmatter fallback and genuinely missing/invalid metadata without the parser's P5 default; axes, minimum evidence, tie-breaking and later sprint aggregation consume the same resolved priority/source.
- [ ] Eligibility/readiness tests cover EPICs, in-progress/deferred targets, deferred/missing/external dependencies, depends_on, one-sided blocks, cycles, absent versus zero scores, local threshold overrides and outcome waiver. Fallback never bypasses a veto/missing gate.
- [ ] Omitted-top selection performs one canonical pass without second-round padding after dedup; explicit-N selection refills across rounds with per-type caps and at-most-once-per-target identity. There is no cross-verb utility comparison.
- [ ] Namespaced dedup refills past duplicates without spending caps; alternate actions/blocker reasons survive. Injected snapshots, shuffled source order and a fixed UTC clock yield deterministic ranks/output in live and reconstructed states.
- [ ] Human/JSON/explain/empty/error modes, installed output Schema (with drift test), config root/export/merge/reset/serialization, registry/permissions and docs pass focused tests. All paths perform no `history.db` access and no writes, including incidental CLI telemetry.
- [ ] Explain uses the shared assessment path for rejected gates, unresolved loop inputs and capped refinement; selected recommendations always have complete actions. Typed action/fingerprint tests distinguish parameter/source/digest changes from display-quoting changes, reject option reinterpretation, and pin consumed caps/refinement limits/threshold validation. Root/subdirectory/nested-repository tests preserve source identity and document the actions’ required working directory; invalid score/waiver domains never become trusted gates or axes.
- [ ] Fixed-clock missing-gate/zero-score/mixed-bucket cold-start fixtures and the default-suite structural performance checks (parse count, ≤4 git subprocesses, bounded saturated-reachability operation counts, ~200-file smoke) pass without network access; the full 10k wall-clock gate exists behind an off-by-default `perf` marker.
- [ ] Walking-skeleton checkpoint records implement-only top-3 comparison with `ll-issues next-issues 3`, common-population ranking comparison with eligibility differences separate, mixed implement/refine usability/counts and scenario evidence, snapshot/config/as_of, and a maintainer go/pause decision for the three active follow-on children. Baseline agreement alone does not decide the epic's value.
- [ ] Single `next` config block settled with FEAT-3681's `next.loop_history.weights` (no second loop scorer; `next.verbs.*` is separate); wiring checklist done: pyproject entry point, `docs/reference/CLI.md` plus its docs test, docs-audience gate, README CLI/loop counts and `scripts/README.md` mirror, `ll-adapt` mirrors only if a skill is touched.
- [ ] The four existing `next-*` CLIs remain behavior-identical; `python -m pytest scripts/tests/` passes.

## Related

- EPIC-3710 (parent). FEAT-3681 (scorer extraction; prerequisite), ENH-3678 (done; schema-bump safety, relevant to FEAT-3711). FEAT-3711, FEAT-3713, FEAT-3721 (active follow-on slices); FEAT-3712 (cancelled source-audit no-go), FEAT-3714 and FEAT-3722 (deferred).

## Review Notes

- 2026-10-03: Pre-implementation review corrected the `next-action` source contract, bounded all arena curves, separated gates from axes, defined snapshot/target/action identity, per-bucket cold start, exact invocations and read-only/config/performance gates. Kept the advisory four-verb slice and legacy CLI compatibility.
- 2026-10-03: Follow-up review separated source assessment from eligibility so explain retains rejected targets, pinned argument-aware action identity and the (since removed, see 2026-10-04) coverage multiplier, and specified consumed cap/refinement settings without an unused gate-disable framework.

- 2026-10-04: Opus epic review (confidence 0.78) plus repo data checks: lower-bounded all non-gate curves (zero-valued axes were near-vetoes under the 1e-6 geometric floor), normalized weights to 1.0, removed the coverage multiplier in favor of a minimum-coverage rule, cut the goal-alignment axis (0/3622 issues carry the field), re-sourced effort from the Impact-section field via a strict map, replaced the default-suite 10k wall-clock gate with structural counters plus a `perf`-marked run, added a walking-skeleton usefulness check, and pinned run-loop as a thin adapter over FEAT-3681's scorer. Dissent noted: weighted arithmetic would be simpler but reopens FEAT-3681.
- 2026-10-04: Follow-up contract audit corrected the loop-frequency floor to satisfy the nominal-weight property, distinguished arena input qualification from legacy loop aggregation, aligned refinement with outcome waivers, made perf opt-in concrete, and expanded the usefulness checkpoint to test the cross-verb benefit and cover FEAT-3721.

- 2026-10-05: Review with `/ll:advise --signal user_requested --host claude-code --model opus` (confidence 0.72) pinned one-pass default selection, bounded/saturated graph evidence, raw score/waiver validation, project-root/working-directory identity, exact loop resolution/context, option-safe command parsing and shared registry/schema extension ownership. Retained geometric scoring and the four-verb history-free slice.

- 2026-10-05 (additional review): Source audit corrected the frontmatter-only priority wording to the shared filename-first authority, with missing metadata kept distinct from the parser's P5 default. Opus critique (0.76) corroborated the source/scope identity seam; clarified that mutable assessment provenance is excluded from the fingerprint and command parsing cannot recover historical ambient files/config. Follow-on identity/work-budget corrections remain in their consuming slices; core scope and checkpoint are unchanged.

## Status

**Open** | Created: 2026-09-24 | Priority: P3
