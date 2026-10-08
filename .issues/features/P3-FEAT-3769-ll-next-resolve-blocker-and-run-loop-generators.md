---
id: FEAT-3769
type: FEAT
title: ll-next resolve-blocker and run-loop generators
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-10-07'
captured_at: '2026-10-07T08:36:16Z'
parent: EPIC-3710
blocked_by:
- FEAT-3561
blocks:
- FEAT-3711
- FEAT-3713
relates_to:
- FEAT-3681
- FEAT-3714
- FEAT-3722
confidence_score: 90
outcome_confidence: 63
score_complexity: 10
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 10
risk_factors:
- id: action-union-contract-change
  domain: outcome
  criterion: complexity
  description: Generalizing ActionSpec union, serializers, fingerprint projection
    and output Schema is a contract change across shared consumers.
- id: helper-extraction-judgment
  domain: outcome
  criterion: ambiguity
  description: Preflight helper extraction is conditional ('if needed') and new module
    boundaries are left to implementation judgment.
- id: legacy-next-loop-overlap
  domain: readiness
  criterion: no_duplicate_implementations
  description: Legacy cmd_next_loop/_scan_history already scores loop runs; arena
    must reuse FEAT-3681 primitives, not become a second scorer.
- id: loader-seam-fanout
  domain: outcome
  criterion: change_surface
  description: load_and_validate is referenced by 14 modules; the captured-content
    seam must leave the legacy path behavior-identical.
- id: resolver-parity-drift
  domain: readiness
  criterion: architecture_compliance
  description: Pure inventory resolver and preflight helpers mirror resolve_loop_path
    and runner checks as a parallel pathway that can drift.
- id: wide-multi-module-sweep
  domain: outcome
  criterion: complexity
  description: About 15 change sites across next_arena, cli, loader, config, schema
    and docs.
---

# FEAT-3769: ll-next resolve-blocker and run-loop generators

## Summary

Add the `resolve-blocker` and `run-loop` generators to the landed `ll-next` core (FEAT-3561, done): root-blocker recommendations over its dependency graph and runnable-loop recommendations over configured definitions and filesystem run history. This slice owns captured loop loading, runner-order input resolution, logical-name history joins and the limited loop fingerprint. Extend the existing registry, config, output Schema and `ProjectState`; add no `history.db` access, writes or history DB schema bump. Advance the output Schema version under the core's published-contract rule. FEAT-3721's database reader is independent of this slice.

## Current Behavior

The landed arena recommends `implement-issue` and `refine-issue` only. `ll-loop next-loop` scores loop runs independently with uncapped legacy curves and an unquoted shell builder; no arena verb recommends a root blocker. The core already owns the dependency graph, saturated fan-out summaries and the leverage axis. Its assessor, action serializers and explain lookup currently assume issue targets and slash actions; registration alone does not extend those consumers.

## Expected Behavior

`ll-next` assesses eligible root blockers (`resolve-blocker`) and existing valid, fully resolved runnable loops (`run-loop`), with the core's assessment-first, gate/coverage and explain behavior. Each bucket ranks by its own weighted utility; selection offers its best remaining target after the core's target deduplication. A root already selected by implement/refine appears as an alternate with its blocker significance rather than a duplicate recommendation. Each verb is advisory and write-free; loop history comes from captured filesystem run records. Register at the shared registry's canonical positions (`implement-issue`, `refine-issue`, `resolve-blocker`, `run-loop`, then FEAT-3713's verbs); duplicate no closed verb list.

## Motivation

Root-blocker and loop recommendations round out the issue-centric core, but neither is needed to decide whether the arena is useful (ENH-3771's optional usefulness review). Building them after the core lands lets that review, if run, inform loop-definition capture, resolution-order replication and history joins. The graph and refinement/implementation adapters they consume already exist in the core.

## Proposed Solution

### Verbs, sources and actions

| Verb | Candidate source / required action |
|---|---|
| `resolve-blocker` | An actionable non-EPIC root with satisfied own prerequisites and at least one proven reachable remaining `open`/`blocked` non-EPIC dependent. Run the unchanged ordered per-issue refinement adapter first; emit a genuine applicable step, otherwise apply the complete implementation gates. Distinguish direct prerequisite satisfaction from downstream reachability; report bounded samples and saturated counts. |
| `run-loop` | Existing valid definition runnable as `ll-loop run -- TARGET` **without supplied input or context arguments**, including never-run project-local public loops (never-run built-in/draft/non-public definitions are not offered until a qualifying run exists; see Coverage, cold start); history cannot resurrect deleted definitions. YAML/parameter defaults, captured steering/config and actually available runtime seeds must satisfy the runner's required-context/`required_inputs` checks; otherwise retain an `unresolved_input` exclusion. |

`resolve-blocker` emits the core's slash action variant (it reuses the core refinement and implementation adapters, caps and `refine_cap`). `run-loop` registers a new tagged `action_spec` variant `loop` (core pins the `variant` discriminator, schema `oneOf` shape and project-relative fingerprint-material rule; this issue defines the loop variant's fields). Candidate identity is `(action_type, target_key)` with `loop:NAME` target keys for loops and the core's `issue:ID` keys for blockers. Gates are the core's policy, unchanged: the root-blocker target must have satisfied dependencies, its displayed implementation step requires the same readiness/outcome checks, an explicit `status: blocked` or true `decision_needed` rejects the implementation step until resolved, and a dependency cycle yields diagnostics rather than an invented root blocker. Retain a genuinely needed core refinement action; if none applies, explain the implementation veto without inventing an action.

Zero fan-out, terminal/EPIC-only dependents, dangling-only declarations or paths proven only through ambiguous nodes cannot establish a root blocker. A known reachable dependent may establish qualification when other fan-out is unknown; retain the core's missing/count-saturation evidence. Refinement-cap exhaustion never falls through to implementation. A format/verify step can apply even when numeric readiness passes; reuse `next_refine_step` rather than defining a second meaning of "unready".

Fan-out is affected downstream reachability, not proof that completing the target immediately makes every descendant implementable. A direct dependent is prerequisite-satisfied by this target only when its **distinct unresolved prerequisite set equals `{target}`**, without unknown/ambiguous prerequisites or a relevant cycle; duplicate declarations count once. Retain independent status/readiness/decision vetoes. Build these bounded summaries in one graph pass, not a full-project scan per root. Carry a bounded blocker summary in alternate JSON/human output when implement/refine wins the same target; a multi-blocked or transitive descendant is never labeled immediately unlocked. Preserve single-pass/explicit-N fill and target dedup; the blocker bucket continues past duplicates and may contribute no separate recommendation.

### Loop definition identity and loading

Pin the loop definition facet's limited v1 scope as `fingerprint_scope="v1/top-level-bytes"`: it binds the exact zero-argument command target, resolved top-level source identity (project-relative or `builtin:`) and captured bytes, not the full executable definition or effective runtime context. `load_and_validate` expands `from:` parents and `import:` fragments, and may inspect child contracts; changing those sources, steering files or config can change an assessment while the limited fingerprint remains identical. Freshly expand/assess each invocation; add no dependency-manifest/hash framework. Fingerprint equality cannot cache gates/ranks, suppress a new offer or claim unchanged behavior. Target dedup remains confined to the current selection. Label the digest **top-level definition bytes** in output/schema/provenance. Dynamic sub-loops, scripts and future config remain outside the proof; copied commands load their current sources. FEAT-3711 acknowledges a fresh recorded `rec_id`/payload, not executable equivalence. Wider source proof remains FEAT-3722's revival prerequisite.

The required `LoopActionSpec` fields are `variant="loop"`, `target` (exact loop operand), `definition_source` (project-relative YAML path or `builtin:<relative-YAML-path>`), `definition_digest="sha256:<64 lowercase hex characters>"`, `fingerprint_scope="v1/top-level-bytes"`, and `working_directory` (the printed absolute project root). `action_key="run-loop"` is registered through the shared variant-aware key projection. Fingerprint all these fields **except `working_directory`**, using the core's canonical JSON/SHA-256 convention; display quoting, absolute provenance paths, effective context, run IDs and timestamps are excluded. No supplied-input/context fields or input inference are modeled in v1; a later parameterized action requires an explicit compatible extension, never reinterpretation of this shape. Store logical-name history joins, shadowing and effective-context provenance in assessment evidence rather than the action spec.

Capture each unique top-level source's bytes and draft metadata once at collection, and parse/hash/validate that same buffer with its original source path/reference base. Adapt `load_and_validate` to reuse captured parsed content through the existing inheritance/flow/fragment/validation passes, keeping legacy path loading unchanged. Do not independently call the catalog's `is_runnable_loop`, draft-name reader or metadata loader and then reparse the same source. A four-draft probe of the current `resolve_loop_path` produced 16 parses from internal-name lookups alone; source selection must use the captured inventory rather than live resolver scans per candidate. Read/decode/validation failures retain diagnostics without a top-level reread. The one-read/parse bound covers **arena discovery/captured top-level ingestion**; existing parent/import/child-contract validation and artifact-output reference-warning catalog scans may separately revisit a source, never replacing the candidate's captured bytes/digest. This proves assessment/digest agreement only, not atomic external-source capture or future execution.

Validation runs in the **collection** phase, once per discovered definition, and stores an immutable `LoopDefinitionRecord` in `ProjectState.loop_definitions`; `assess_run_loops` reads only those records, so "no live I/O during assessment" holds literally (the parent/import/child reads happen at collection). Call the captured-content `load_and_validate` variant with the runner's validation policy: `cmd_run` passes no `orchestration_request_path`, `host_cli` or `model_hints`, so do not thread those project-config overrides into arena validation. Its captured-content/resolution seam must reproduce execution from the printed project root for **all** cwd-sensitive lookups, including `from:` parents and static child/`with:` checks; an absolute top-level path alone does not establish this. Preserve each source's original directory as the inheritance/import/reference fallback base and preserve the legacy path API's default behavior. Use explicit resolution-root context rather than process-global `chdir`. Root-versus-nested-cwd fixtures must exercise both a direct child and an inherited parent operand present only at the root. Use `raise_on_error=False`: any ERROR-severity violation means invalid (the runner's `ValueError` path) and WARNING-severity violations become per-definition `Diagnostic` evidence. `raise_on_error=True` emits every warning through `logger.warning` (probe: 83 lines over the 120 built-in definitions), which must never reach `ll-next` output. Contain `FileNotFoundError`/`yaml.YAMLError`/`ValueError` and any other per-definition exception as an explainable exclusion, and capture `resolve_loop_path`'s duplicate-draft stderr `Note:` (also reached through child validation) as a diagnostic. Text and `--json` output keep the core's stdout/stderr contract.

Use the catalog's filesystem shapes: recursive project/built-in `*.yaml`, excluding project `runs/` except direct `runs/*/workflow.yaml` drafts. Fragment-only/non-runnable sources are excluded; visibility remains metadata under this issue's resolver-runnable scope, rather than silently inheriting `ll-loop list`'s public-only filter. Cold-start visibility is the **effective post-inheritance** value, normalized like `cli/loop/info.py::_load_loop_meta`: unset/null/empty/unrecognized values become public, with any validation warning retained; draft provenance remains draft regardless of inherited visibility. Derive effective visibility from the same loading pass, without a separate metadata reread. A child with no raw visibility can inherit `internal`/`example` and must not become a public fallback. Each definition has one canonical command target: its relative name with the full `.fsm.yaml`/`.yaml` suffix stripped, the equivalent built-in name, or a draft's instance-folder name. Do not emit additional internal-logical-name aliases for the same source. A pure inventory resolver mirrors runtime precedence from **the printed project root**, not the caller's nested cwd: direct path, compiled FSM, project YAML, built-in, draft folder, then latest-mtime internal-name fallback. Capture existence/type for the direct `project_root/TARGET` operand too, including non-YAML files/directories outside loop-source discovery; such a collision must not silently fall through to a project/built-in definition. It records shadowing evidence and offers a definition only if its canonical target resolves back to that captured source. One `(run-loop, loop:TARGET)` assessment represents the effective resolution, retaining shadowed-source evidence; explain must not select a competing shadowed-source assessment by enumeration order. Test parity against `resolve_loop_path` from that root, including project/built-in, compiled/project, duplicate draft logical names and direct-path collisions. Unsupported sources/targets remain excluded; add no source-selection flag. Different draft folders are distinct targets even if they share a logical name. Discover under `config.get_loops_dir()` resolved from the printed root; an absolute or out-of-root `loops.loops_dir` yields a diagnostic exclusion, since `definition_source` must be project-relative.

Capture the runner's steering file once: `program.md` in that root's `.ll` directory, when present; absence supplies no steering sections. For zero-argument eligibility, preserve YAML-context literals, seed optional parameter defaults with `setdefault`, apply steering sections (which **overwrite** a matching YAML literal or seeded default, as `cmd_run` assigns them) and then the runner's config/runtime defaults through pure helpers. Required template context uses the existing membership/suffix parser; fallback/nullable references are optional. `required_inputs` uses the runner's truthiness check, so false/zero/empty required inputs fail even when a template key exists. Model generated `run_dir` availability symbolically without creating an instance ID/directory. The runner also always binds `design_tokens_context` and `design_guidance_context` (possibly empty), so model their presence symbolically without loading design files. Preserve known opt-out/existing-context behavior; a `required_inputs` truthiness check depending on unknown loaded design values remains an `unresolved_input` exclusion, while a known preserved truthy literal can satisfy it. Conditional seeds remain conditional: `input_hash` only follows a string `input`, `max_iterations` requires a value, and `include` requires a configured default unless already bound. Preserve confidence defaults, guaranteed design-key presence and per-key availability provenance; they are eligibility evidence, not captured token values, fingerprint material or emitted overrides. Never run `cmd_run`, reopen config in pure assessment, call legacy `_resolve_params`, reuse historical inputs or invent a user's input. Extract/share the current preflight checks with behavior-parity tests if needed; introduce no runner policy change. `fsm/context_seed.py::inject_design_context` is an I/O helper even when passed config; the arena must not call it or the design-token loader during collection or assessment. Symbolic presence supplies template membership without design-file reads or loader notices; it does not assert a truthy design value.

Keep the effective loop command target separate from the validated expanded `FSMLoop.name`. `PersistentExecutor` stores filesystem history under that logical name, which need not equal the filename stem, direct-path operand or generator-draft folder. Join the arena's qualified filesystem run records using the persisted logical name, not the displayed command target. Expose `history_join_key` and its logical-name provenance in loop evidence; retain command/source identity for target dedup and the limited action fingerprint. Different effective definitions sharing that logical name share name-based history, so disclose that source/version attribution is unknown rather than treating it as the assessed definition's record. A filename/name mismatch alone is valid and must not become a new eligibility veto. Fixtures cover filename/logical-name mismatch, a draft-folder alias and two definitions sharing a logical name without changing legacy next-loop behavior.

Render as `ll-loop run -- TARGET` through the core shell-argv grammar (`shlex.join`); test the real runner's argument parsing without invoking its execution/telemetry path. Every emitted action passes the zero-argument preflight availability checks. Always emit explicit `run`, since a leading bare loop name triggers CLI subcommand insertion.

### Axes × verbs matrix (initial defaults)

Weights are initial defaults pinned by fixtures and overridable only through keyed `next` config (FEAT-3681/FEAT-3561 own the foundation; this issue adds consumed per-verb entries for these two verbs). Each verb's default weights **sum to 1.0**. `—` means inapplicable.

| Axis (source) | resolve-blocker | run-loop |
|---|---|---|
| priority (canonical filename, then frontmatter) | 0.25 | — |
| leverage / fan-out (dependency graph) | 0.50 | — |
| effort, inverse (Impact-section `Effort` field, strict map) | 0.15 | — |
| staleness (capture date) | 0.05 | — |
| momentum (Session Log timestamps in the issue file) | 0.05 | — |
| frequency / recency / success (`next-loop` history) | — | 0.50 / 0.30 / 0.20 |

### Lower-bounded loop curves

The core's lower-bounded `lerp(lo, 1, x)` policy and worst/best-factor property apply unchanged. Loop axes:

| Axis | Raw value and bounded curve |
|---|---|
| loop frequency | `x = min(1, log1p(run_count) / log1p(50))` from valid filesystem run records; score `lerp(0.4, 1, x)`. A loop with no valid run records has **all three loop axes missing** (cold start), never a present zero. |
| loop recency | `x = exp(-log(2) * age_days / 7)` for the latest valid run start at/before `as_of`; score `lerp(0.2, 1, x)`. |
| loop success | `x` = fraction of recognized terminal runs (`completed`, `failed`, `timed_out`) with `status == completed`; score `lerp(0.2, 1, x)`. Unknown/in-flight/resumable (`interrupted`, `awaiting_continuation`) statuses do not count as failures. No recognized terminal runs means missing. |

The run-loop verb **reuses FEAT-3681's pure curve primitives** as a thin adapter, then applies the bounded mapping above; it must not become a second independent curve/scorer implementation. Its input qualification is intentionally arena-specific: legacy `_score_loop` counts every run in its success denominator and selects dates lexically, whereas the arena normalizes dates, filters at `as_of`, and uses recognized terminal runs only. Do not reuse that legacy aggregate or its precomputed success rate as arena evidence. Retain the raw run records in ProjectState and test the two policies side by side without changing legacy behavior. `as_of` qualifies run starts for frequency/recency and the success cohort; terminal success uses the status captured from the current filesystem record. This does not reconstruct which terminal status was known at an earlier `as_of`: legacy `_scan_history` retains `status`/`started_at` but no terminal observation time, and `updated_at` is mutable. Historical injected states must supply their actually observed statuses; no event traversal or terminal-time reconstruction is added.

Discover archived records under the configured loops directory's `.history` only, using the persistence folder parser; `.running` is not a second history source. Capture each `state.json` at most once in one batched pass. A qualifying run needs a readable JSON mapping and a valid normalized `started_at <= as_of` under the core UTC/date policy. Missing files, nonmapping JSON, invalid dates and future starts supply diagnostics rather than counts or invented zero scores. Otherwise unknown/missing/non-string statuses may still supply frequency/recency, but only recognized string terminal statuses enter success. Do not reuse `_scan_history` unchecked: a JSON `[]` record currently raises `AttributeError`, while malformed dates/statuses are retained. Preserve excluded-record reasons and raw captured provenance independently of eligibility. A missing `.history` directory is collected empty; an existing non-directory, unreadable directory or failed enumeration yields unavailable history and a loop-domain diagnostic, without aborting issue recommendations or loop explain. Discard an incomplete enumeration batch rather than scoring it as complete; history axes are missing, while valid local-public definitions may still use the existing fallback. No qualifying evidence means no qualifying captured record, not proof that a loop never ran; unreadable/invalid/unavailable history must not make that claim. Add no deadline or history-coverage framework.

The worst/best-factor property uses the **nominal default weights on a complete axis set**, including loop frequency's `0.4` floor (`0.4^0.5 ≈ 0.632`). Missing-axis renormalization and user weight overrides can increase an axis's effective influence; report the effective weights in explain rather than claiming the `0.6` factor holds for those cases. All non-gate curves still have a positive floor.

### Coverage, cold start and minimum evidence

Cold start is **per verb** (core contract): a never-run valid **project-local public** definition (source under the configured loops directory, effective catalog-normalized `visibility` public, not a `runs/*/workflow.yaml` draft) has no resolved history axes, so it is a gate-passing `utility=null` fallback candidate that sorts after scored loops in its own bucket even when issue buckets have data. A built-in, draft or non-public (`internal`/`example`) definition with **no** qualifying run record is still assessed and explainable but fails an explained `cold_start_scope` gate, and is scored normally once a qualifying run exists. Otherwise a project with no history would lead its default output with the alphabetically first built-in (probe 2026-10-07: 57 of the 120 built-in definitions are zero-argument runnable, including 6 `internal` and 4 `example`; `adopt-third-party-api` would win). Visibility is otherwise metadata, not `ll-loop list`'s public-only filter.

| Verb | Minimum evidence for numeric utility after eligibility gates |
|---|---|
| resolve-blocker | Valid priority metadata plus at least one resolved **positive-weight** non-priority axis (core issue-verb rule). |
| run-loop | At least one resolved positive-weight history axis. |

### Extension contract

Extend, never duplicate, the core registry: add both verbs at their canonical positions, their consumed `next.verbs.<verb>` weights/caps (`next.verbs.resolve-blocker.weights.*`, `next.verbs.run-loop.weights.*`, caps default 2) through the shared `NextConfig` root allowlist/schema, and the output-Schema `loop` variant branch (claim the next output `schema_version`; `loop` moves from `RESERVED_VARIANTS` to `ACTION_VARIANTS`, `sprint`/`scan` stay reserved, and `spec_from_dict` dispatches per variant instead of assuming the slash key set). Preserve the landed consumer boundary: legacy `resolve_loop_history_weights` validates `next.loop_history`; the arena validates **all registered `next.verbs` entries**, including under `--type`. Neither consumes the other's weight subtree; per-selected-verb sibling isolation is not added. Extend `ProjectState` with immutable `loop_definitions` and raw qualified/excluded `loop_history` evidence; scoring/generation performs no live I/O. The core's no-`history.db`/no-write invariants, `--help`/error paths and `--no-record` handoff remain.

**Scope-aware loop collection.** Loop targets (`loop:NAME`) never share a `target_key` with issue targets, so collect the loop domain only when a loop verb is in scope: no `--type`, `--type` naming `run-loop`, or `--explain run-loop TARGET`. When not collected, `ProjectState.loop_definitions`/`loop_history` are `None` (distinct from an empty tuple for "collected, none found"), `assess_run_loops` returns no assessments and no empty-source diagnostic, and issue-domain assessments, within-bucket ranks and alternates are invariant to loop capture. Compare recommendations using the **same requested bucket order and `top`**, and compare issue-domain diagnostic projections (or full capture rendered under that same issue-only scope). An unrestricted full pass can legitimately spend a global `--top` slot on a loop and include loop diagnostics; entire envelopes need not match. Diagnostic filtering must respect candidate domain as well as target spelling, including a loop and issue both named `FEAT-001`; preserve landed rendered issue-diagnostic shapes/subjects and the core's all-registered-verb config-error policy. Measured 2026-10-07 on this repository: `ll-next --type implement-issue` takes about 5.6 s today, validating the 120 runnable definitions about 2.0 s, with 1,357 archived history folders. A default full pass absorbing roughly +2 s is recorded as information, not a budget; add no lazy top-N validation, since every candidate needs validated context for eligibility. Replace `_rank_verb`'s hard-coded cold-start `selection_reason` ("ordered by priority then target") with verb-aware wording, since loops carry no priority.

`CONFIGURATION.md` states that `next.loop_history.weights` (legacy `ll-loop next-loop`) does not affect the `run-loop` verb of `ll-next`, whose defaults are the same 0.50/0.30/0.20 but tuned through `next.verbs.run-loop.weights`, and that `next.verbs` does not affect `ll-loop next-loop`.

Route each registered generator to its own candidate domain and minimum-evidence policy: loop candidates do not need issue priority and do not acquire phantom issue/refinement assessments. Generalize the existing `ActionSpec` union, serializers, action-key/fingerprint projection and output-Schema builders to the registered variants. `--explain resolve-blocker ID` retains `issue:ID`; `--explain run-loop TARGET` uses the exact command operand and `loop:TARGET`, with verb-aware help, missing-target and empty-source diagnostics. A discovered invalid/unresolved loop remains explainable with exit 0; an absent target returns 1 under the core policy. Existing `--explain run-loop TARGET` syntax must accept exact option-looking operands such as `-foo` and `--json` on every supported Python version, including 3.11; a `./` alias changes identity and is not a substitute. Actual output flags following the target retain their meaning, and conflicting modes remain usage errors. Add no new CLI flags. Explain diagnostics are domain-aware: a loop named like an issue ID never receives that issue's diagnostics or alternates.

## Scope Boundaries

- **In scope:** the two generators with explicit no-candidate cases, loop identity/loading/resolution/history-join contracts, loop curves/axes, consumed config/registry/Schema extension, loop-history perf extensions, docs.
- **Out of scope:** redesigning the core's scoring/fill policy, database reader/events (FEAT-3721, FEAT-3711), sprint/scan verbs (FEAT-3713), supplied loop input/context inference or new CLI flags, `--execute`, executor/loader behavior changes, legacy `next-loop` changes, cross-definition loop-version history matching, pressure/automatic attribution (FEAT-3722), and modeling running instances or singleton/scope-lock conflicts (`LockManager`): the runner may refuse or queue a loop that is already running, so a running loop can still be recommended (state this in the docs). Pure capture/preflight extraction and domain/variant CLI wiring are required extensions, not runner behavior changes.

## Integration Map

### Files to Modify

- `scripts/little_loops/next_arena/{registry,state,candidates,axes,actions,render}.py`: registry, captured evidence, domain-aware `assess_candidates`, per-verb minimum evidence, `ActionSpec` union/key/serialization/fingerprint dispatch, alternate blocker summaries and generated output Schema. Keep `selection.py`'s fill/dedup policy; extend its fixtures rather than changing that policy. New loop/blocker generator and axis-adapter modules may isolate the source-specific work.
- `scripts/little_loops/cli/next.py::main_next` and `_build_parser`: verb-aware explain target keys/help and existing exit/error behavior. Regenerate `scripts/little_loops/next_arena/output-schema.json` through `python -m little_loops.next_arena.render --write-schema`; do not hand-edit it.
- Captured-content loop-loading seam around `fsm/validation/structural_rules.py::load_and_validate`, `fsm/validation/reachability.py` and `fsm/fragments.py`; reuse their expansion/validation passes, printed-root lookup semantics and original source directory without a second top-level read or a dependency-manifest framework. Loop discovery around `fsm/loop_paths.py::resolve_loop_path`; filesystem run-record qualification adapting `cli/loop/next_loop.py` helpers without changing the old command's policy or output.
- `scripts/little_loops/cli/loop/{info,run}.py` and `fsm/context_seed.py`: reuse discovery patterns and extract/share pure preflight/context helpers as needed; preserve catalog/runner behavior. Capture program/config inputs at collection, and model guaranteed design-key availability without design-token I/O before pure assessment. Retain `fsm/persistence.py`'s archived-folder/logical-name convention.
- `scripts/little_loops/config-schema.json` and `config/{features,core,__init__}.py` for the consumed `next.verbs.{resolve-blocker,run-loop}` entries; `docs/reference/CLI.md`, `CONFIGURATION.md`, `API.md`.
- Tests for both candidate sources, loop identity/loading/join fixtures, curves/property test extension, schema drift, cross-consumer config fixtures and the loop extensions of the structural/`perf` gates.
- CLI-only: the skills/`ll-adapt` mirror gates do not apply; docs and README/loop-count wiring follow FEAT-3561's checklist if counts change.

## Program Design

### Types

- Extend immutable `ProjectState` with captured loop-source inventory/steering evidence, `loop_definitions` and raw qualified/excluded `loop_history` (both `None` when the loop domain is not collected). `LoopDefinitionRecord` (frozen, built at collection) holds the canonical command target, source identity (project-relative or `builtin:`), effective normalized visibility and draft metadata, captured-bytes digest, the validated `FSMLoop` or an exclusion reason, warning `Diagnostic`s, shadowing evidence and the zero-argument context inputs. Reuse `AxisScore`, `GateResult`, `CandidateAssessment` and `Candidate`. `LoopActionSpec` has the six required fields and registered projection defined above; candidate/assessment action specs accept the shared union rather than `SlashActionSpec` alone.

### Signatures

- `collect_loop_definitions(project_root: Path, *, config: BRConfig) -> tuple[LoopDefinitionRecord, ...]` — collection-phase discovery under the configured loops directory and built-ins, single-buffer capture, `load_and_validate(raise_on_error=False)` with runner-equivalent validation policy and printed-root resolution context, and resolver/steering capture; the arena discovery/captured-ingestion entry point, run only when a loop verb is in scope; preserved collection-validation reads are accounted separately.
- `assess_resolve_blockers(state: ProjectState, *, settings: ArenaSettings) -> list[CandidateAssessment]` — retains blocker eligibility, gate and affected-dependent evidence for selection and explain.
- `assess_run_loops(state: ProjectState, *, settings: ArenaSettings) -> list[CandidateAssessment]` — retains each effective source/digest, zero-argument effective-context provenance, history joins, gates and exclusions, including unresolved required inputs. The shared dispatcher passes resolved settings; helpers never reopen config or source files.

### Call Path

Existing `resolve_loop_path` / `load_and_validate` / `cmd_next_loop` source paths and FEAT-3561's dependency graph → new collection-phase `collect_loop_definitions` (loop verbs in scope only) → new `assess_resolve_blockers` and `assess_run_loops` within the core's shared `assess_candidates` pass (gate/axis evidence and FEAT-3681 utility/coverage/within-verb ranks once) → eligible projection through core `generate_candidates` → core `select_candidates` round-robin fill → rendering. Explain reuses those assessments and ranks; no separate scoring path or event write is added.

## Implementation Steps

1. FEAT-3561 is done: consume its landed registry/Schema/`ProjectState` seams; proceed independently of FEAT-3721. Preserve the dependency edge as prerequisite provenance.
2. Add `resolve-blocker` over the core graph and ordered action adapter, with root qualification, direct/reachable summaries and dedup alternate evidence.
3. Add the captured discovery/validation seam, resolution-order/context snapshot and logical-name history join; register the concrete `loop` action variant and thin history-axis adapters. Validate at collection into `LoopDefinitionRecord`s with runner-equivalent validation policy and printed-root resolution context (`raise_on_error=False`), capturing warnings and resolver notes as diagnostics.
4. Wire domain-aware assessment/minimum-evidence/explain dispatch, scope-aware loop collection, the `cold_start_scope` gate and consumed config/Schema/registry. Update intentional two-verb/global-envelope assertions; preserve implement/refine assessments, actions, fingerprints and within-bucket ranks under explicit verb selection.
5. Extend structural operation counts and the opt-in in-memory `perf` gate, then CLI/config/API docs. Run focused arena/loop regression tests and `python -m pytest scripts/tests/`.

## Impact

- **Priority:** P3 — completes the four-verb core after the core lands.
- **Effort:** Large — two generators plus captured discovery/loading/context/history seams and the core's first non-issue action/target extension. Implement in the bounded stages above; no additional issue or framework is needed.
- **Risk:** Medium — wrong source/definition attribution or incomplete domain dispatch can yield an unrunnable, mis-joined or unexplainable recommendation; mitigated by captured-source parity, typed actions and mixed-domain fixtures.
- **Compatibility:** `ll-next` intentionally advances its published output version for the new verbs/variant; existing standalone `next-*` CLIs, including `ll-loop next-loop`, retain their contracts.

## Use Case

With the core landed, a user running `ll-next` can see a ranked root blocker (or its blocker significance beside an implement/refine action) and a runnable loop worth repeating or considering as a cold-start fallback, each with shared explain evidence.

## Acceptance Criteria

- [ ] `resolve-blocker` and `run-loop` register at their canonical positions; per-verb config/matrix defaults are pinned with weights summing to 1.0. Update intentional two-verb/config/Schema/global-output assertions; preserve implement/refine axis/gate/action/fingerprint/within-bucket-rank fixtures under explicit type selection. Domain-aware dispatch supplies no phantom cross-domain assessments; loop minimum evidence never requires issue priority. The shared action-key vocabulary admits `run-loop` while the seven slash mappings remain unchanged.
- [ ] Root-blocker actions reuse the core's all-status inventory checks (`ambiguous_issue_id`, numeric-source uniqueness, `unsupported_issue_filename`); a prerequisite or one-sided `blocks` declaration through an ambiguous node cannot make a blocker look root or satisfied. No modeled issue-reference loop inputs are introduced in this zero-argument slice.
- [ ] Both verbs have explicit empty-source behavior. Root qualification excludes zero/terminal-only/EPIC-only/dangling-only/ambiguity-only fan-out and reuses satisfied-dependency/lifecycle gates. The unchanged ordered refinement adapter takes precedence when applicable, including format/verify despite passing numeric scores; cap exhaustion cannot fall through to implementation. Otherwise complete implementation gates apply, including true `decision_needed`, with explained exclusions. Direct-prerequisite summaries deduplicate declarations, exclude multi-blocked/cyclic dependents, and retain independent vetoes. Chain/diamond fixtures distinguish reachability from immediate prerequisite satisfaction.
- [ ] Target dedup remains unchanged: a root selected by implement/refine retains bounded blocker evidence in human/JSON alternates; the blocker bucket continues to its next distinct target or exhausts without a duplicate. `--type resolve-blocker` uses that bucket's utility rank rather than promising maximum fan-out alone.
- [ ] Loop curves are lower-bounded as specified; the nominal-default-weight property test (`(worst/best)^w ≥ 0.6`, weights summing to 1.0) covers resolve-blocker and run-loop axes including frequency's `0.4` floor; a loop with no valid run records has all three history axes missing; legacy next-loop curves/output are unchanged and tested side by side.
- [ ] Loop identity pins the six-field variant, `run-loop` action key and `v1/top-level-bytes` projection. Changing a parent/fragment/steering file under fixed top-level bytes and command target freshly changes assessment while the limited fingerprint may remain equal; equality never caches or suppresses an offer. Generated runtime directory values/absolute provenance never enter identity; relocation with identical relative sources retains it. Make no whole-definition/future-execution equivalence claim.
- [ ] Loop-history fixtures separate command target from expanded logical name for a filename mismatch and draft alias: qualified runs join on the persisted `FSMLoop.name`, with `history_join_key` provenance. Shared-logical-name definitions disclose source/version uncertainty; no run history is invented from a command spelling or represented as exact definition evidence.
- [ ] A top-level replacement between collection and assessment/hash cannot mix definitions: parsing, expansion inputs and the digest consume the same captured buffer with the original reference base. Read/decode/validation failures remain explainable exclusions; the legacy path loader is behavior-identical and no atomic imported-source snapshot is claimed.
- [ ] Source inventory/resolver parity covers project/built-in, compiled/project, duplicate draft logical names and direct-path collisions from the printed root, including invocation from a nested cwd. One canonical target per definition prevents alias duplicates; shadowed/invalid sources remain diagnosed. Never-run project-local public zero-argument loops use per-bucket fallback; missing inputs exclude them. Preflight parity covers YAML/parameter/steering precedence (a steering section overwriting a YAML `context:` literal; a `required_inputs` key satisfied only by steering is eligible), required-key membership versus false/zero/empty required-input rejection, suffixes and conditional runtime seeds without writes/instance-ID allocation.
- [ ] Inherited visibility fixtures exclude a history-free child inheriting `internal`/`example`, while invalid visibility follows catalog public normalization with its warning retained and no second metadata read. Root-versus-nested-cwd loading fixtures cover direct child and inherited-parent references, preserve source-relative import/fallback behavior, and keep legacy path-loading behavior unchanged. Design-key fixtures cover symbolic template membership, preserved known opt-out/existing-context values and an explained exclusion for required-input truthiness depending on unknown loaded values. Assert zero design-token loader calls/file reads and quiet text/JSON output.
- [ ] Cold-start scope: with no run history only never-run project-local public definitions are fallback candidates; built-in, draft and `internal`/`example` definitions without a qualifying run are assessed, explainable and excluded by the `cold_start_scope` gate, and score normally once a qualifying run exists. A project with no project-local loops and no history shows an explained empty `run-loop` bucket, not an arbitrary built-in.
- [ ] Validation emission and scope: validity uses runner-equivalent `load_and_validate` policy with printed-root resolution context and any ERROR-severity violation means invalid; warnings and resolver notes surface only as diagnostics (`capfd`/`caplog` over a built-in definition that warns: empty stderr, clean `--json` stdout). Issue-only scopes (`--type` without `run-loop`, `--explain` of an issue verb) perform zero loop source reads, validations and history reads, with `loop_definitions`/`loop_history` `None`, invariant issue assessments/ranks/alternates, and matching recommendations under the same issue-only bucket order/`top` plus matching issue-domain diagnostic projections. Fixtures include a scored loop, malformed loop/history and explicit `--top` so they cannot equate an unrestricted full envelope with an issue-only envelope.
- [ ] Explain uses verb-aware target identity and shared assessments for selected, invalid/unresolved and missing loop targets; exits retain the core found/absent policy. Complete zero-argument loop specs round-trip through serialization/deserialization/fingerprint and the runner's pure argument grammar; leading-dash targets remain literal operands in both run and explain grammar, including option-looking names on Python 3.11, actual trailing output flags, and found/excluded/absent exit cases. A loop and issue sharing an ID spelling keep their explain diagnostics/alternates separate, with a golden assertion preserving existing issue-diagnostic rendering. Loop deserialization rejects missing/extra fields, wrong types, malformed digest, unsupported scope and absolute/traversing source identities; the core's existing reserved/unknown-variant rejection fixtures remain passing. Pin one literal canonical loop fingerprint material/digest golden independently of the projection helper. Shadowing fixtures explain the effective source through one assessment per verb/target. No legacy parameter resolver or historical input inference is used.
- [ ] History qualification fixtures cover missing/unreadable/nonmapping/malformed/future records, normalized UTC/offset/date starts, unknown/non-string/in-flight statuses and no terminal cohort. Invalid evidence never crashes sibling assessment or turns into present-zero history; qualifying nonterminal runs can score frequency/recency only. Legacy next-loop policy/output stays unchanged.
- [ ] History enumeration failures (non-directory, permission/read error, failure after a partial batch) produce unavailable/missing history axes and scoped diagnostics without aborting siblings; incomplete batches are not scored. A genuinely absent directory is collected empty. Local-public fallback remains available on missing history evidence, with no claim that unavailable/invalid history proves a loop never ran.
- [ ] Cross-consumer fixtures preserve legacy `next.loop_history.weights` validation/output alongside registered but invalid arena-only settings, and arena validation alongside invalid unconsumed legacy weights. Root/schema allowlists and the output `schema_version` stay synchronized.
- [ ] Structural checks cover one arena-discovery/top-level ingestion read/parse per unique discovered source, one history-state read per discovered record, a single batched history pass, and one direct-dependent graph-summary pass; no per-candidate arena-owned discovery/history rescan. Existing parent/import/child-contract and artifact-output reference-warning catalog reads are separate collection-validation I/O and cannot replace captured bytes/digest. Count/disclose them separately; the ingestion bound is not a total physical source-read bound. An `artifact_output` fixture covers the preserved catalog scan/warnings. Include a small filesystem smoke test and deterministic operation counts without network access. The opt-in `perf` gate uses injected in-memory evidence at 10,000 issues / 20,000 edges / 200 definitions / 10,000 run records, serially as in the core; this is not a fixed filesystem byte/deadline budget. No git subprocess is introduced.
- [ ] Legacy `ll-issues next-issue`, `next-issues`, `next-action` and `ll-loop next-loop` retain their policy/output. `ll-next` intentionally extends to four verbs/new output version. `python -m pytest scripts/tests/` passes.

## Related

- EPIC-3710 (parent). FEAT-3561 (done core; retained hard prerequisite). FEAT-3711 and FEAT-3713 wait on this slice's four verbs and settled `loop` payload; FEAT-3713 adds the final two verbs and both arrival orders are tested. FEAT-3721 (reader) proceeds independently. FEAT-3681 (done scorer/config foundation). FEAT-3714 and FEAT-3722 remain deferred.

ENH-3771's usefulness review is optional and non-gating.

## Review Notes

- 2026-10-07 (follow-up source/parity review): Confirmed nested-cwd child/parent lookup drift, inherited visibility, design-loader notices, artifact-output catalog rereads, `.history` non-directory failure, scope/`--top` parity limits and diagnostic name collisions. Corrected those contracts and added loop payload negatives/golden coverage. `/ll:advise --signal user_requested --host claude-code --model opus` recommended proceeding after narrowed edits (0.80). Adopted symbolic design-key presence instead of design-token capture, effective catalog visibility, explicit root lookup context with no process-global cwd change, scoped diagnostics, unavailable-history fallback and accurate ingestion-count limits. Retained exact option-looking explain support: Python 3.12 probes disambiguate a literal `--json` target from a trailing output flag by position, whereas supported Python 3.11 rejects that grammar today; this is part of the planned CLI extension. The earlier speculative nested-cwd caveat is now reproduced. No new flag/framework/child issue or implementation; confidence scores remain unchanged. Risks: root-context propagation, preservation of issue-diagnostic rendering, and temporary loss of scored loop history after enumeration errors.

- 2026-10-07 (landed-core implementation review on `main`): FEAT-3561 is done. Source/probes confirmed issue-only dispatch/explain, slash-only serialization/action-key Schema, all-registered-verb config validation, zero fan-out as a present axis, two-verb fixture assertions, 16 YAML parses for four draft-alias lookups, and a nonmapping history-record crash. Corrected root qualification/action precedence/dedup evidence, domain/variant wiring, config/parity/perf wording and the stale Medium effort estimate. `/ll:advise --signal user_requested --host claude-code --model opus` supported all findings (0.80), recommending a zero-argument loop cut instead of inventing user inputs: adopted that boundary, concrete six-field payload, `v1/top-level-bytes` scope and one canonical target per source. Retained `action_key="run-loop"` through the shared vocabulary and the printed absolute project root as execution provenance; corrected the advisor's unconditional runtime-placeholder suggestion to match conditional seeds. Risks remain limited loop coverage, resolver/preflight drift and blocker dedup overlap; parity/empty-source fixtures expose them. No implementation, readiness rescore, new child or history framework. Related deferred source-proof prose is synchronized without revival.

- 2026-10-07: Created by the EPIC-3710 pre-implementation review (`/ll:advise --signal user_requested --host claude-code --model opus`, "CONDITIONAL GO", 0.75). The FEAT-3561 go/pause checkpoint needs only implement/refine/explain, yet whole-issue completion front-loaded the loop-specific work; an in-issue milestone is only prose, while `blocked_by` is machine-enforced. Moved the resolve-blocker and run-loop contracts here verbatim (loop fingerprint scope, same-buffer capture, resolution order, logical-name join, loop curves/axes, fan-out wording); added only the `variant` discriminator/project-relative fingerprint-material cross-reference and the explicit-`run` note. No contract was weakened.

- 2026-10-07 (dispatch/domain review): Reuse the core flag-backed `decision_unresolved` veto for the root-blocker implementation branch, preserving genuinely needed refinement actions and explained exclusions. A temporary `_scan_history` probe retained a post-`as_of` completed status for a pre-`as_of` run start while dropping its observation timestamp; clarified current captured-status success rather than historical knowledge reconstruction. Opus recommended "CONVERGE" (0.86); these are source-backed corrections/limitations within the frozen scope, not a new history framework or implementation evidence.

- 2026-10-07 (pre-implementation review against `main` @ bb71716f3): repo probes plus `/ll:advise --signal user_requested --host claude-code --model opus` ("GO after edits", 0.80). Probes: `load_and_validate(raise_on_error=True)` logged 83 warnings over the 120 built-in definitions; validating them takes about 2.0 s against a 5.6 s `ll-next` baseline; 57 built-ins are zero-argument runnable (6 `internal`, 4 `example`), so a history-free cold-start bucket would have led with an arbitrary built-in. Added: the `cold_start_scope` gate (never-run built-in/draft/non-public definitions are not offered), collection-phase validation into `LoopDefinitionRecord` with the runner's argument set and `raise_on_error=False` (also silences the warning log), scope-aware loop collection (`None` vs empty), steering-overwrite wording and fixtures, `get_loops_dir()` discovery, the `RESERVED_VARIANTS` move, verb-aware cold-start reason text, a running-instance/lock non-goal and the `next.loop_history` vs `next.verbs` docs clause. Skipped as speculative: case-insensitive-FS probe wording, nested-cwd child-resolution caveat, legacy nested `.history` layout disclosure, lazy top-N validation. Dissent: narrowing cold start edits the earlier "including never-run loops" line (kept for project-local public loops); scope-aware collection is optional if +2 s is judged acceptable. No rescore; outcome confidence is unchanged until implementation.

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-10-07_

**Readiness Score**: 90/100 → PROCEED
**Outcome Confidence**: 63/100 → MODERATE

### Outcome Risk Factors
- Broad enumeration across ~15 sites (next_arena, cli, loader, config, schema, docs) with moderate-to-deep per-site complexity.
- Generalizing the `ActionSpec` union, serializers, fingerprint projection and output Schema is a shared-contract change; keep implement/refine fixtures as the regression guard.
- `load_and_validate` is referenced by 14 modules; the captured-content seam must leave the legacy path behavior-identical.
- Preflight-helper extraction is conditional ("if needed") and module boundaries are left to judgment; resolver/preflight parity tests are the drift guard.

### Risk Factor Delta
- Baseline: none recorded

## Status

**Open** | Created: 2026-10-07 | Priority: P3


## Session Log
- `/ll:confidence-check` - 2026-10-08T03:41:48 - `093e63bf-756e-4410-88e8-a06b0543ee58.jsonl`
- `/ll:advise` - 2026-10-08T03:18:40 - `ff81089f-a893-4a61-a9f8-54ef605c3a0e.jsonl`
- `/ll:refine-issue` - 2026-10-08T03:18:40 - `ff81089f-a893-4a61-a9f8-54ef605c3a0e.jsonl`
- `/ll:confidence-check` - 2026-10-08T01:38:36 - `343c9913-3cee-46b9-ac51-07d359eb143a.jsonl`
- `/ll:advise` - 2026-10-08T02:55:13 - `ff81089f-a893-4a61-a9f8-54ef605c3a0e.jsonl`
