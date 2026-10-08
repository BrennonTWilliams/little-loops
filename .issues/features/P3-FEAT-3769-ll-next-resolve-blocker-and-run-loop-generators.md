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
| `run-loop` | Existing valid definition runnable as `ll-loop run -- TARGET` **without supplied input or context arguments**, including never-run loops; history cannot resurrect deleted definitions. YAML/parameter defaults, captured steering/config and actually available runtime seeds must satisfy the runner's required-context/`required_inputs` checks; otherwise retain an `unresolved_input` exclusion. |

`resolve-blocker` emits the core's slash action variant (it reuses the core refinement and implementation adapters, caps and `refine_cap`). `run-loop` registers a new tagged `action_spec` variant `loop` (core pins the `variant` discriminator, schema `oneOf` shape and project-relative fingerprint-material rule; this issue defines the loop variant's fields). Candidate identity is `(action_type, target_key)` with `loop:NAME` target keys for loops and the core's `issue:ID` keys for blockers. Gates are the core's policy, unchanged: the root-blocker target must have satisfied dependencies, its displayed implementation step requires the same readiness/outcome checks, an explicit `status: blocked` or true `decision_needed` rejects the implementation step until resolved, and a dependency cycle yields diagnostics rather than an invented root blocker. Retain a genuinely needed core refinement action; if none applies, explain the implementation veto without inventing an action.

Zero fan-out, terminal/EPIC-only dependents, dangling-only declarations or paths proven only through ambiguous nodes cannot establish a root blocker. A known reachable dependent may establish qualification when other fan-out is unknown; retain the core's missing/count-saturation evidence. Refinement-cap exhaustion never falls through to implementation. A format/verify step can apply even when numeric readiness passes; reuse `next_refine_step` rather than defining a second meaning of "unready".

Fan-out is affected downstream reachability, not proof that completing the target immediately makes every descendant implementable. A direct dependent is prerequisite-satisfied by this target only when its **distinct unresolved prerequisite set equals `{target}`**, without unknown/ambiguous prerequisites or a relevant cycle; duplicate declarations count once. Retain independent status/readiness/decision vetoes. Build these bounded summaries in one graph pass, not a full-project scan per root. Carry a bounded blocker summary in alternate JSON/human output when implement/refine wins the same target; a multi-blocked or transitive descendant is never labeled immediately unlocked. Preserve single-pass/explicit-N fill and target dedup; the blocker bucket continues past duplicates and may contribute no separate recommendation.

### Loop definition identity and loading

Pin the loop definition facet's limited v1 scope as `fingerprint_scope="v1/top-level-bytes"`: it binds the exact zero-argument command target, resolved top-level source identity (project-relative or `builtin:`) and captured bytes, not the full executable definition or effective runtime context. `load_and_validate` expands `from:` parents and `import:` fragments, and may inspect child contracts; changing those sources, steering files or config can change an assessment while the limited fingerprint remains identical. Freshly expand/assess each invocation; add no dependency-manifest/hash framework. Fingerprint equality cannot cache gates/ranks, suppress a new offer or claim unchanged behavior. Target dedup remains confined to the current selection. Label the digest **top-level definition bytes** in output/schema/provenance. Dynamic sub-loops, scripts and future config remain outside the proof; copied commands load their current sources. FEAT-3711 acknowledges a fresh recorded `rec_id`/payload, not executable equivalence. Wider source proof remains FEAT-3722's revival prerequisite.

The required `LoopActionSpec` fields are `variant="loop"`, `target` (exact loop operand), `definition_source` (project-relative YAML path or `builtin:<relative-YAML-path>`), `definition_digest="sha256:<hex>"`, `fingerprint_scope="v1/top-level-bytes"`, and `working_directory` (the printed absolute project root). `action_key="run-loop"` is registered through the shared variant-aware key projection. Fingerprint all these fields **except `working_directory`**, using the core's canonical JSON/SHA-256 convention; display quoting, absolute provenance paths, effective context, run IDs and timestamps are excluded. No supplied-input/context fields or input inference are modeled in v1; a later parameterized action requires an explicit compatible extension, never reinterpretation of this shape. Store logical-name history joins, shadowing and effective-context provenance in assessment evidence rather than the action spec.

Capture each unique top-level source's bytes and draft metadata once at collection, and parse/hash/validate that same buffer with its original source path/reference base. Adapt `load_and_validate` to reuse captured parsed content through the existing inheritance/flow/fragment/validation passes, keeping legacy path loading unchanged. Do not independently call the catalog's `is_runnable_loop`, draft-name reader or metadata loader and then reparse the same source. A four-draft probe of the current `resolve_loop_path` produced 16 parses from internal-name lookups alone; source selection must use the captured inventory rather than live resolver scans per candidate. Read/decode/validation failures retain diagnostics without a top-level reread. The one-read/parse bound covers **arena discovery/captured top-level ingestion**; existing parent/import/child-contract validation may separately revisit a source, never replacing the candidate's captured bytes/digest. This proves assessment/digest agreement only, not atomic external-source capture or future execution.

Use the catalog's filesystem shapes: recursive project/built-in `*.yaml`, excluding project `runs/` except direct `runs/*/workflow.yaml` drafts. Fragment-only/non-runnable sources are excluded; visibility remains metadata under this issue's resolver-runnable scope, rather than silently inheriting `ll-loop list`'s public-only filter. Each definition has one canonical command target: its relative name with the full `.fsm.yaml`/`.yaml` suffix stripped, the equivalent built-in name, or a draft's instance-folder name. Do not emit additional internal-logical-name aliases for the same source. A pure inventory resolver mirrors runtime precedence from **the printed project root**, not the caller's nested cwd: direct path, compiled FSM, project YAML, built-in, draft folder, then latest-mtime internal-name fallback. Capture existence/type for the direct `project_root/TARGET` operand too, including non-YAML files/directories outside loop-source discovery; such a collision must not silently fall through to a project/built-in definition. It records shadowing evidence and offers a definition only if its canonical target resolves back to that captured source. Test parity against `resolve_loop_path` from that root, including project/built-in, compiled/project, duplicate draft logical names and direct-path collisions. Unsupported sources/targets remain excluded; add no source-selection flag. Different draft folders are distinct targets even if they share a logical name.

Capture the runner's steering file once: `program.md` in that root's `.ll` directory, when present; absence supplies no steering sections. For zero-argument eligibility, preserve YAML-context literals, seed optional parameter defaults with `setdefault`, apply steering sections and then the runner's config/runtime defaults through pure helpers. Required template context uses the existing membership/suffix parser; fallback/nullable references are optional. `required_inputs` uses the runner's truthiness check, so false/zero/empty required inputs fail even when a template key exists. Model generated `run_dir` availability symbolically without creating an instance ID/directory. Conditional seeds remain conditional: `input_hash` only follows a string `input`, `max_iterations` requires a value, and `include` requires a configured default unless already bound. Preserve confidence/design-context defaults and per-key provenance; they are eligibility evidence, not fingerprint material or emitted overrides. Never run `cmd_run`, reopen config in pure assessment, call legacy `_resolve_params`, reuse historical inputs or invent a user's input. Extract/share the current preflight checks with behavior-parity tests if needed; introduce no runner policy change.

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

Discover archived records under the configured loops directory's `.history` only, using the persistence folder parser; `.running` is not a second history source. Capture each `state.json` at most once in one batched pass. A qualifying run needs a readable JSON mapping and a valid normalized `started_at <= as_of` under the core UTC/date policy. Missing files, nonmapping JSON, invalid dates and future starts supply diagnostics rather than counts or invented zero scores. Otherwise unknown/missing/non-string statuses may still supply frequency/recency, but only recognized string terminal statuses enter success. Do not reuse `_scan_history` unchecked: a JSON `[]` record currently raises `AttributeError`, while malformed dates/statuses are retained. Preserve excluded-record reasons and raw captured provenance independently of eligibility.

The worst/best-factor property uses the **nominal default weights on a complete axis set**, including loop frequency's `0.4` floor (`0.4^0.5 ≈ 0.632`). Missing-axis renormalization and user weight overrides can increase an axis's effective influence; report the effective weights in explain rather than claiming the `0.6` factor holds for those cases. All non-gate curves still have a positive floor.

### Coverage, cold start and minimum evidence

Cold start is **per verb** (core contract): a never-run valid loop has no resolved history axes, so it is a gate-passing `utility=null` fallback candidate that sorts after scored loops in its own bucket even when issue buckets have data.

| Verb | Minimum evidence for numeric utility after eligibility gates |
|---|---|
| resolve-blocker | Valid priority metadata plus at least one resolved **positive-weight** non-priority axis (core issue-verb rule). |
| run-loop | At least one resolved positive-weight history axis. |

### Extension contract

Extend, never duplicate, the core registry: add both verbs at their canonical positions, their consumed `next.verbs.<verb>` weights/caps (`next.verbs.resolve-blocker.weights.*`, `next.verbs.run-loop.weights.*`, caps default 2) through the shared `NextConfig` root allowlist/schema, and the output-Schema `loop` variant branch (claim the next output `schema_version`). Preserve the landed consumer boundary: legacy `resolve_loop_history_weights` validates `next.loop_history`; the arena validates **all registered `next.verbs` entries**, including under `--type`. Neither consumes the other's weight subtree; per-selected-verb sibling isolation is not added. Extend `ProjectState` with immutable `loop_definitions` and raw qualified/excluded `loop_history` evidence; scoring/generation performs no live I/O. The core's no-`history.db`/no-write invariants, `--help`/error paths and `--no-record` handoff remain.

Route each registered generator to its own candidate domain and minimum-evidence policy: loop candidates do not need issue priority and do not acquire phantom issue/refinement assessments. Generalize the existing `ActionSpec` union, serializers, action-key/fingerprint projection and output-Schema builders to the registered variants. `--explain resolve-blocker ID` retains `issue:ID`; `--explain run-loop TARGET` uses the exact command operand and `loop:TARGET`, with verb-aware help, missing-target and empty-source diagnostics. A discovered invalid/unresolved loop remains explainable with exit 0; an absent target returns 1 under the core policy.

## Scope Boundaries

- **In scope:** the two generators with explicit no-candidate cases, loop identity/loading/resolution/history-join contracts, loop curves/axes, consumed config/registry/Schema extension, loop-history perf extensions, docs.
- **Out of scope:** redesigning the core's scoring/fill policy, database reader/events (FEAT-3721, FEAT-3711), sprint/scan verbs (FEAT-3713), supplied loop input/context inference or new CLI flags, `--execute`, executor/loader behavior changes, legacy `next-loop` changes, cross-definition loop-version history matching, pressure/automatic attribution (FEAT-3722). Pure capture/preflight extraction and domain/variant CLI wiring are required extensions, not runner behavior changes.

## Integration Map

### Files to Modify

- `scripts/little_loops/next_arena/{registry,state,candidates,axes,actions,render}.py`: registry, captured evidence, domain-aware `assess_candidates`, per-verb minimum evidence, `ActionSpec` union/key/serialization/fingerprint dispatch, alternate blocker summaries and generated output Schema. Keep `selection.py`'s fill/dedup policy; extend its fixtures rather than changing that policy. New loop/blocker generator and axis-adapter modules may isolate the source-specific work.
- `scripts/little_loops/cli/next.py::main_next` and `_build_parser`: verb-aware explain target keys/help and existing exit/error behavior. Regenerate `scripts/little_loops/next_arena/output-schema.json` through `python -m little_loops.next_arena.render --write-schema`; do not hand-edit it.
- Captured-content loop-loading seam around `fsm/validation/structural_rules.py::load_and_validate`; reuse its expansion/validation passes and original source directory without a second top-level read or a dependency-manifest framework. Loop discovery around `fsm/loop_paths.py::resolve_loop_path`; filesystem run-record qualification adapting `cli/loop/next_loop.py` helpers without changing the old command's policy or output.
- `scripts/little_loops/cli/loop/{info,run}.py` and `fsm/context_seed.py`: reuse discovery patterns and extract/share pure preflight/context helpers as needed; preserve catalog/runner behavior. Capture program/config/design inputs at collection, before pure assessment. Retain `fsm/persistence.py`'s archived-folder/logical-name convention.
- `scripts/little_loops/config-schema.json` and `config/{features,core,__init__}.py` for the consumed `next.verbs.{resolve-blocker,run-loop}` entries; `docs/reference/CLI.md`, `CONFIGURATION.md`, `API.md`.
- Tests for both candidate sources, loop identity/loading/join fixtures, curves/property test extension, schema drift, cross-consumer config fixtures and the loop extensions of the structural/`perf` gates.
- CLI-only: the skills/`ll-adapt` mirror gates do not apply; docs and README/loop-count wiring follow FEAT-3561's checklist if counts change.

## Program Design

### Types

- Extend immutable `ProjectState` with captured loop-source inventory/steering evidence, `loop_definitions` and raw qualified/excluded `loop_history`; reuse `AxisScore`, `GateResult`, `CandidateAssessment` and `Candidate`. `LoopActionSpec` has the six required fields and registered projection defined above; candidate/assessment action specs accept the shared union rather than `SlashActionSpec` alone.

### Signatures

- `assess_resolve_blockers(state: ProjectState, *, settings: ArenaSettings) -> list[CandidateAssessment]` — retains blocker eligibility, gate and affected-dependent evidence for selection and explain.
- `assess_run_loops(state: ProjectState, *, settings: ArenaSettings) -> list[CandidateAssessment]` — retains each effective source/digest, zero-argument effective-context provenance, history joins, gates and exclusions, including unresolved required inputs. The shared dispatcher passes resolved settings; helpers never reopen config or source files.

### Call Path

Existing `resolve_loop_path` / `load_and_validate` / `cmd_next_loop` source paths and FEAT-3561's dependency graph → new `assess_resolve_blockers` and `assess_run_loops` within the core's shared `assess_candidates` pass (gate/axis evidence and FEAT-3681 utility/coverage/within-verb ranks once) → eligible projection through core `generate_candidates` → core `select_candidates` round-robin fill → rendering. Explain reuses those assessments and ranks; no separate scoring path or event write is added.

## Implementation Steps

1. FEAT-3561 is done: consume its landed registry/Schema/`ProjectState` seams; proceed independently of FEAT-3721. Preserve the dependency edge as prerequisite provenance.
2. Add `resolve-blocker` over the core graph and ordered action adapter, with root qualification, direct/reachable summaries and dedup alternate evidence.
3. Add the captured discovery/validation seam, resolution-order/context snapshot and logical-name history join; register the concrete `loop` action variant and thin history-axis adapters.
4. Wire domain-aware assessment/minimum-evidence/explain dispatch and consumed config/Schema/registry. Update intentional two-verb/global-envelope assertions; preserve implement/refine assessments, actions, fingerprints and within-bucket ranks under explicit verb selection.
5. Extend structural operation counts and the opt-in in-memory `perf` gate, then CLI/config/API docs. Run focused arena/loop regression tests and `python -m pytest scripts/tests/`.

## Impact

- **Priority:** P3 — completes the four-verb core after the core lands.
- **Effort:** Large — two generators plus captured discovery/loading/context/history seams and the core's first non-issue action/target extension. Implement in the bounded stages above; no additional issue or framework is needed.
- **Risk:** Medium — wrong source/definition attribution or incomplete domain dispatch can yield an unrunnable, mis-joined or unexplainable recommendation; mitigated by captured-source parity, typed actions and mixed-domain fixtures.
- **Breaking Change:** No; existing `next-*` CLIs, including `ll-loop next-loop`, are untouched.

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
- [ ] Source inventory/resolver parity covers project/built-in, compiled/project, duplicate draft logical names and direct-path collisions from the printed root, including invocation from a nested cwd. One canonical target per definition prevents alias duplicates; shadowed/invalid sources remain diagnosed. Never-run valid zero-argument loops use per-bucket fallback; missing inputs exclude them. Preflight parity covers YAML/parameter/steering precedence, required-key membership versus false/zero/empty required-input rejection, suffixes and conditional runtime seeds without writes/instance-ID allocation.
- [ ] Explain uses verb-aware target identity and shared assessments for selected, invalid/unresolved and missing loop targets; exits retain the core found/absent policy. Complete zero-argument loop specs round-trip through serialization/deserialization/fingerprint and the runner's pure argument grammar; leading-dash targets remain literal operands. No legacy parameter resolver or historical input inference is used.
- [ ] History qualification fixtures cover missing/unreadable/nonmapping/malformed/future records, normalized UTC/offset/date starts, unknown/non-string/in-flight statuses and no terminal cohort. Invalid evidence never crashes sibling assessment or turns into present-zero history; qualifying nonterminal runs can score frequency/recency only. Legacy next-loop policy/output stays unchanged.
- [ ] Cross-consumer fixtures preserve legacy `next.loop_history.weights` validation/output alongside registered but invalid arena-only settings, and arena validation alongside invalid unconsumed legacy weights. Root/schema allowlists and the output `schema_version` stay synchronized.
- [ ] Structural checks cover one arena-discovery/top-level ingestion read/parse per unique discovered source, one history-state read per discovered record, a single batched history pass, and one direct-dependent graph-summary pass; no per-candidate source/history rescan. Existing external parent/import/child-contract validation reads are separate from the captured-ingestion count and cannot replace its bytes/digest. Include a small filesystem smoke test and deterministic operation counts without network access. The opt-in `perf` gate uses injected in-memory evidence at 10,000 issues / 20,000 edges / 200 definitions / 10,000 run records, serially as in the core; this is not a fixed filesystem byte/deadline budget. No git subprocess is introduced.
- [ ] Legacy `ll-issues next-issue`, `next-issues`, `next-action` and `ll-loop next-loop` retain their policy/output. `ll-next` intentionally extends to four verbs/new output version. `python -m pytest scripts/tests/` passes.

## Related

- EPIC-3710 (parent). FEAT-3561 (done core; retained hard prerequisite). FEAT-3711 and FEAT-3713 wait on this slice's four verbs and settled `loop` payload; FEAT-3713 adds the final two verbs and both arrival orders are tested. FEAT-3721 (reader) proceeds independently. FEAT-3681 (done scorer/config foundation). FEAT-3714 and FEAT-3722 remain deferred.

ENH-3771's usefulness review is optional and non-gating.

## Review Notes

- 2026-10-07 (landed-core implementation review on `main`): FEAT-3561 is done. Source/probes confirmed issue-only dispatch/explain, slash-only serialization/action-key Schema, all-registered-verb config validation, zero fan-out as a present axis, two-verb fixture assertions, 16 YAML parses for four draft-alias lookups, and a nonmapping history-record crash. Corrected root qualification/action precedence/dedup evidence, domain/variant wiring, config/parity/perf wording and the stale Medium effort estimate. `/ll:advise --signal user_requested --host claude-code --model opus` supported all findings (0.80), recommending a zero-argument loop cut instead of inventing user inputs: adopted that boundary, concrete six-field payload, `v1/top-level-bytes` scope and one canonical target per source. Retained `action_key="run-loop"` through the shared vocabulary and the printed absolute project root as execution provenance; corrected the advisor's unconditional runtime-placeholder suggestion to match conditional seeds. Risks remain limited loop coverage, resolver/preflight drift and blocker dedup overlap; parity/empty-source fixtures expose them. No implementation, readiness rescore, new child or history framework. Related deferred source-proof prose is synchronized without revival.

- 2026-10-07: Created by the EPIC-3710 pre-implementation review (`/ll:advise --signal user_requested --host claude-code --model opus`, "CONDITIONAL GO", 0.75). The FEAT-3561 go/pause checkpoint needs only implement/refine/explain, yet whole-issue completion front-loaded the loop-specific work; an in-issue milestone is only prose, while `blocked_by` is machine-enforced. Moved the resolve-blocker and run-loop contracts here verbatim (loop fingerprint scope, same-buffer capture, resolution order, logical-name join, loop curves/axes, fan-out wording); added only the `variant` discriminator/project-relative fingerprint-material cross-reference and the explicit-`run` note. No contract was weakened.

- 2026-10-07 (dispatch/domain review): Reuse the core flag-backed `decision_unresolved` veto for the root-blocker implementation branch, preserving genuinely needed refinement actions and explained exclusions. A temporary `_scan_history` probe retained a post-`as_of` completed status for a pre-`as_of` run start while dropping its observation timestamp; clarified current captured-status success rather than historical knowledge reconstruction. Opus recommended "CONVERGE" (0.86); these are source-backed corrections/limitations within the frozen scope, not a new history framework or implementation evidence.

## Status

**Open** | Created: 2026-10-07 | Priority: P3
