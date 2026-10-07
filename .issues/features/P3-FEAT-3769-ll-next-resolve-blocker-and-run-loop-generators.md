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
- ENH-3771
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

Add the `resolve-blocker` and `run-loop` generators to the `ll-next` core (FEAT-3561): root-blocker recommendations over the core's dependency graph and runnable-loop recommendations over configured loop definitions and filesystem run history. Split out of FEAT-3561 by the 2026-10-07 pre-implementation review so the epic's go/pause checkpoint (implement-issue + refine-issue + `--explain`) happens **before** the most specialized work: the captured-buffer loop-loading seam in `fsm/validation/structural_rules.py`, runner-order context resolution, the persisted-logical-name history join, the limited loop fingerprint scope and the loop history axes. These contracts moved here verbatim from FEAT-3561; none was weakened. This slice extends the core's registry, config, output Schema and `ProjectState`; it reads filesystem loop run records but adds no `history.db` access, writes or history DB schema bump. Its output Schema version advances under the core's published-contract rule.

## Current Behavior

After FEAT-3561 the arena recommends `implement-issue` and `refine-issue` only. `ll-loop next-loop` scores loop runs independently with uncapped legacy curves and an unquoted shell builder; no arena verb recommends a root blocker. The core already owns the dependency graph, saturated fan-out summaries and the leverage axis that root-blocker selection reuses.

## Expected Behavior

`ll-next` also offers the highest-leverage root blocker (`resolve-blocker`) and an existing valid, fully resolved runnable loop (`run-loop`), with the same assessment-first, gate/coverage and explain behavior as the core verbs. Each is advisory and write-free; loop history comes from captured filesystem run records, with no `history.db` access. Both register in the core's shared verb registry at their pre-declared canonical positions (`implement-issue`, `refine-issue`, `resolve-blocker`, `run-loop`, then FEAT-3713's verbs); no closed verb list is duplicated.

## Motivation

Root-blocker and loop recommendations round out the issue-centric core, but neither is needed to decide whether the arena is useful (the ENH-3771 checkpoint). Building them after a recorded "go" avoids paying for loop-definition capture, resolution-order replication and history joins if the checkpoint says pause. The graph and refinement/implementation adapters they consume already exist in the core.

## Proposed Solution

### Verbs, sources and actions

| Verb | Candidate source / required action |
|---|---|
| `resolve-blocker` | Root blocker of remaining active leaf issues. The target itself must have no unresolved dependencies. Recommend its per-issue refinement step if unready, otherwise the complete implementation invocation; distinguish direct prerequisite satisfaction from downstream reachability; report bounded affected-dependent samples and saturated counts. |
| `run-loop` | Existing valid runnable definition from configured loop sources, including never-run loops; history alone cannot resurrect deleted definitions. Resolve and validate every `required_inputs`/required-context value before emission; unresolved inputs exclude the candidate with a diagnostic. |

`resolve-blocker` emits the core's slash action variant (it reuses the core refinement and implementation adapters, caps and `refine_cap`). `run-loop` registers a new tagged `action_spec` variant `loop` (core pins the `variant` discriminator, schema `oneOf` shape and project-relative fingerprint-material rule; this issue defines the loop variant's fields). Candidate identity is `(action_type, target_key)` with `loop:NAME` target keys for loops and the core's `issue:ID` keys for blockers. Gates are the core's policy, unchanged: the root-blocker target must have satisfied dependencies, its displayed implementation step requires the same readiness/outcome checks, an explicit `status: blocked` rejects the implementation step until that status is resolved, and a dependency cycle yields diagnostics rather than an invented root blocker.

Fan-out is affected downstream reachability, not proof that completing the target immediately makes every descendant implementable. Report direct dependents whose entire pending prerequisite set is this target separately; retain independent status/readiness vetoes. Alternate-action/blocker annotations must not call a multi-blocked or transitive descendant immediately unlocked.

### Loop definition identity and loading

Pin the loop definition facet's limited v1 scope in the registered `loop` variant as `fingerprint_scope="v1/top-level-bytes+resolved-inputs"`: it binds the resolved top-level YAML path (project-relative, or a `builtin:` form for built-ins; the absolute spelling is provenance only) and bytes plus resolved input/context arguments, not the full executable definition. `load_and_validate` expands `from:` parents and `import:` fragments, and may inspect child contracts; changing those files can change an assessment while the top-level digest and resolved arguments remain identical. Snapshot/validate the current expanded definition at the loading boundary for each invocation, but do not add a dependency-manifest/hash framework in this slice. The top-level fingerprint cannot replace assessment, justify a cached gate/rank, suppress a new offer, or claim that an inherited/imported definition is unchanged. Target-key dedup remains confined to the current selection; a later invocation is independently assessed. Record the scope in output/schema/provenance and label the digest as **top-level definition bytes**. Dynamic sub-loops, scripts and later config are also outside this identity proof; copied commands load their current sources when run. FEAT-3711 acknowledges its recorded invocation/payload by fresh `rec_id`, not executable equivalence. Wider offer/producer source proof is a revival precondition of deferred FEAT-3722.

Preserve a loop's resolved input/context, effective definition source and SHA-256 content digest in the typed action specification; canonicalize keyed context in sorted key order while retaining meaningful positional/list argument order; exclude display quoting, ephemeral run IDs and timestamps from the fingerprint. Running the same loop name with different or unrecorded inputs is not exact acceptance.

Read the effective top-level loop bytes once at the collection boundary and parse/hash that same captured buffer. The current `load_and_validate(path)` opens the file itself; calling it and separately hashing a later `path.read_bytes()` can attach a different definition's digest to the assessment. Factor/adapt its loading seam to accept captured top-level content and its original source path, reusing the existing inheritance/flow/fragment and validation passes with the same relative-reference base. Keep legacy path-loading behavior unchanged. Decode/read/validation failures retain an excluded assessment with diagnostics; do not reread the live top-level path to recover it. This guarantees only assessment/digest agreement for those captured bytes, not atomicity of imported sources or future execution.

For loops, snapshot the runtime's actual resolution order (`fsm.loop_paths.resolve_loop_path`: direct path, compiled `.fsm.yaml`, project YAML, built-in, then generator draft). Assess at most one effective definition per command target and report shadowed definitions; never validate one source and emit a name that invokes another. Use the effective command target selected by that resolver and retain its resolved path/digest as provenance. Do not emit a shadowed definition or invent a source-selection flag; unsupported/unrepresentable targets remain excluded. Resolve effective context in the runner's order (parameter defaults, positional input, injected `program.md`, explicit context, config/runtime defaults); share/adapt pure helpers rather than launching `cmd_run` or its write-capable loaders. Required context with interpolation fallback/nullable suffixes is optional under the existing parser. Fixture a project/built-in collision, compiled/project collision, duplicate drafts and a direct-path collision from the stated working directory. v1 does not match archived run records to a definition content version; name-based historical evidence is labeled as such, not proof of the current definition's success.

Keep the effective loop command target separate from the validated expanded `FSMLoop.name`. `PersistentExecutor` stores filesystem history under that logical name, which need not equal the filename stem, direct-path operand or generator-draft folder. Join the arena's qualified filesystem run records using the persisted logical name, not the displayed command target. Expose `history_join_key` and its logical-name provenance in loop evidence; retain command/source identity for target dedup and the limited action fingerprint. Different effective definitions sharing that logical name share name-based history, so disclose that source/version attribution is unknown rather than treating it as the assessed definition's record. A filename/name mismatch alone is valid and must not become a new eligibility veto. Fixtures cover filename/logical-name mismatch, a draft-folder alias and two definitions sharing a logical name without changing legacy next-loop behavior.

Render loop actions with the core's shell-argv grammar (`shlex.join`, modeled options before `--`, positionals after). Every emitted loop action has its required arguments resolved or is excluded; test that invariant rather than assuming `ll-loop run NAME` is always runnable. `ll-loop` inserts `run` for a leading bare name, so always emit the explicit `run` subcommand.

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

The run-loop verb **reuses FEAT-3681's pure curve primitives** as a thin adapter, then applies the bounded mapping above; it must not become a second independent curve/scorer implementation. Its input qualification is intentionally arena-specific: legacy `_score_loop` counts every run in its success denominator and selects dates lexically, whereas the arena normalizes dates, filters at `as_of`, and uses recognized terminal runs only. Do not reuse that legacy aggregate or its precomputed success rate as arena evidence. Retain the raw run records in ProjectState and test the two policies side by side without changing legacy behavior.

The worst/best-factor property uses the **nominal default weights on a complete axis set**, including loop frequency's `0.4` floor (`0.4^0.5 ≈ 0.632`). Missing-axis renormalization and user weight overrides can increase an axis's effective influence; report the effective weights in explain rather than claiming the `0.6` factor holds for those cases. All non-gate curves still have a positive floor.

### Coverage, cold start and minimum evidence

Cold start is **per verb** (core contract): a never-run valid loop has no resolved history axes, so it is a gate-passing `utility=null` fallback candidate that sorts after scored loops in its own bucket even when issue buckets have data.

| Verb | Minimum evidence for numeric utility after eligibility gates |
|---|---|
| resolve-blocker | Valid priority metadata plus at least one resolved **positive-weight** non-priority axis (core issue-verb rule). |
| run-loop | At least one resolved positive-weight history axis. |

### Extension contract

Extend, never duplicate, the core registry: add both verbs at their canonical positions, their consumed `next.verbs.<verb>` weights/caps (`next.verbs.resolve-blocker.weights.*`, `next.verbs.run-loop.weights.*`, caps default 2) through the shared `NextConfig` root allowlist/schema, and the output-Schema `loop` variant branch (claim the next output `schema_version`). Reuse the core's cross-consumer isolation: the legacy `resolve_loop_history_weights` and arena consumers each validate only their own subtree, and neither validates an unconsumed registered sibling. Extend `ProjectState` with `loop_definitions` and `loop_history` (immutable captured evidence, no live I/O in scoring/generation). The core's no-`history.db`/no-write invariants, `--help`/error-path behavior and `--no-record` handoff are unchanged.

## Scope Boundaries

- **In scope:** the two generators with explicit no-candidate cases, loop identity/loading/resolution/history-join contracts, loop curves/axes, consumed config/registry/Schema extension, loop-history perf extensions, docs.
- **Out of scope:** the core snapshot/scoring/CLI (FEAT-3561), history reader/events (FEAT-3721, FEAT-3711), sprint/scan verbs (FEAT-3713), `--execute`, executor/loader behavior changes, changing the legacy `next-loop` policy/output, cross-definition loop-version history matching, pressure/automatic attribution (FEAT-3722).

## Integration Map

### Files to Modify

- Core arena modules from FEAT-3561 (registry, `ProjectState`, selection, generated output Schema) extended in place; new loop/blocker generator and axis-adapter modules.
- Captured-content loop-loading seam around `fsm/validation/structural_rules.py::load_and_validate`; reuse its expansion/validation passes and original source directory without a second top-level read or a dependency-manifest framework. Loop discovery around `fsm/loop_paths.py::resolve_loop_path`; filesystem run-record qualification adapting `cli/loop/next_loop.py` helpers without changing the old command's policy or output.
- `scripts/little_loops/config-schema.json` and `config/{features,core,__init__}.py` for the consumed `next.verbs.{resolve-blocker,run-loop}` entries; `docs/reference/CLI.md`, `CONFIGURATION.md`, `API.md`.
- Tests for both candidate sources, loop identity/loading/join fixtures, curves/property test extension, schema drift, cross-consumer config fixtures and the loop extensions of the structural/`perf` gates.
- CLI-only: the skills/`ll-adapt` mirror gates do not apply; docs and README/loop-count wiring follow FEAT-3561's checklist if counts change.

## Program Design

### Types

- Extends FEAT-3561's immutable `ProjectState` with `loop_definitions` and `loop_history` fields and reuses `AxisScore`, `GateResult`, `CandidateAssessment` and `Candidate`; adds the typed `loop` action-spec variant with its registered fingerprint projection.

### Signatures

- `assess_resolve_blockers(state: ProjectState) -> list[CandidateAssessment]` — retains blocker eligibility, gate and affected-dependent evidence for selection and explain.
- `assess_run_loops(state: ProjectState) -> list[CandidateAssessment]` — retains each effective definition's source/digest, resolved inputs, gates and exclusion reasons, including loops with unresolved inputs.

### Call Path

Existing `resolve_loop_path` / `load_and_validate` / `cmd_next_loop` source paths and FEAT-3561's dependency graph → new `assess_resolve_blockers` and `assess_run_loops` (dispatched from FEAT-3561's `assess_candidates` / `generate_candidates`) → FEAT-3681's utility scorer → core `select_candidates` → rendering. No event is written.

## Implementation Steps

1. Implement after FEAT-3561 and ENH-3771's recorded "go" decision (this issue is `blocked_by` ENH-3771); consume its registry/Schema/`ProjectState` extension seams.
2. Add `resolve-blocker` over the core graph/adapters with its fan-out/reachability evidence.
3. Add the captured-buffer loop-loading seam, resolution-order/context snapshot, logical-name history join and `loop` action variant, then the loop axes/curves.
4. Extend consumed config/Schema/registry and cross-consumer fixtures; extend the structural perf checks and the opt-in `perf` gate with loop definitions and run records.
5. Re-run the core's fixed fixtures to prove no change to implement/refine behavior, then docs and mirrors.

## Impact

- **Priority:** P3 — completes the four-verb core after the checkpoint.
- **Effort:** Medium — two generators and the loop-specific loading/identity/history contracts.
- **Risk:** Medium — wrong source/definition attribution would make a persuasive but unrunnable or mis-joined loop recommendation; mitigated by captured-buffer hashing, fail-closed resolution and explicit name-based labeling.
- **Breaking Change:** No; existing `next-*` CLIs, including `ll-loop next-loop`, are untouched.

## Use Case

After the checkpoint records "go", a user running `ll-next` also sees the root blocker that unlocks the most remaining work and a loop worth running again (or a never-run loop as a fallback), each with the same explain evidence as issue actions.

## Acceptance Criteria

- [ ] `resolve-blocker` and `run-loop` register at their canonical registry positions; per-verb `next.verbs.*` entries and the matrix defaults are in `config-schema.json`, pinned by fixtures, with default weights summing to 1.0 per verb. No closed verb list is duplicated, and the registry/Schema/config extension leaves FEAT-3561's implement/refine fixtures unchanged.
- [ ] Root-blocker actions, and any modeled issue-reference loop input that uses the issue-path resolver, call the core's all-status inventory check (`ambiguous_issue_id`, numeric-source uniqueness, `unsupported_issue_filename`; moved here from FEAT-3561, which tests only its implement/refine actions) and own fixtures for those consumers; a prerequisite or one-sided `blocks` declaration through an ambiguous node cannot make a blocker look root or satisfied.
- [ ] Both verbs have tested candidate sources and explicit empty-source behavior. Deleted/invalid loops and unresolved inputs never emit runnable commands; never-run valid loops use per-bucket fallback; every emitted loop action has its required arguments resolved. Root-blocker targets require satisfied dependencies and recommend the refinement step when unready; direct-prerequisite satisfaction is distinguished from downstream reachability, with bounded samples/saturated counts and no "immediately unlocked" claim for multi-blocked or transitive descendants.
- [ ] Loop curves are lower-bounded as specified; the nominal-default-weight property test (`(worst/best)^w ≥ 0.6`, weights summing to 1.0) covers resolve-blocker and run-loop axes including frequency's `0.4` floor; a loop with no valid run records has all three history axes missing; legacy next-loop curves/output are unchanged and tested side by side.
- [ ] Loop identity includes the declared top-level fingerprint scope. A fixture changes an inherited parent/imported fragment while leaving top-level bytes and resolved arguments fixed: the fresh expanded assessment changes, the limited fingerprint may remain equal, and no cached assessment or offer suppression follows from that equality. Output/docs make no whole-definition or future-execution equivalence claim. Fingerprint material contains no absolute paths (project-relative or `builtin:` form only).
- [ ] Loop-history fixtures separate command target from expanded logical name for a filename mismatch and draft alias: qualified runs join on the persisted `FSMLoop.name`, with `history_join_key` provenance. Shared-logical-name definitions disclose source/version uncertainty; no run history is invented from a command spelling or represented as exact definition evidence.
- [ ] A top-level replacement between collection and assessment/hash cannot mix definitions: parsing, expansion inputs and the digest consume the same captured buffer with the original reference base. Read/decode/validation failures remain explainable exclusions; the legacy path loader is behavior-identical and no atomic imported-source snapshot is claimed.
- [ ] Resolution-order fixtures cover project/built-in collision, compiled/project collision, duplicate drafts and a direct-path collision from the stated working directory; effective context follows the runner's order; at most one effective definition per command target is assessed and shadowed definitions are reported.
- [ ] Explain uses the shared assessment path for rejected gates and unresolved loop inputs; selected recommendations always have complete actions; loop actions render through the core's shell-argv grammar with leading-dash names/inputs unable to become flags.
- [ ] Cross-consumer fixtures preserve legacy `next.loop_history.weights` validation/output alongside registered but invalid arena-only settings, and arena validation alongside invalid unconsumed legacy weights. Root/schema allowlists and the output `schema_version` stay synchronized.
- [ ] The default-suite structural checks extend to loop discovery/history (one parse per definition, bounded run-record reads, deterministic operation counts, small filesystem smoke test) without network access; the off-by-default `perf` gate adds 200 loop definitions / 10,000 run records to the core's 10,000-issue / 20,000-edge scale. No git subprocess is introduced.
- [ ] The core's four existing `next-*` CLIs remain behavior-identical; `python -m pytest scripts/tests/` passes.

## Related

- EPIC-3710 (parent). FEAT-3561 (core; prerequisite) and ENH-3771 (checkpoint owner; this issue's `blocked_by`), FEAT-3711 and FEAT-3713 (follow-ons blocked by this slice so four landed verbs and the `loop` action variant are settled; FEAT-3713 adds the final two verbs and both arrival orders are tested), FEAT-3721 (reader; independent of this slice). FEAT-3681 (done; scorer/config foundation). FEAT-3714, FEAT-3722 (deferred).

## Review Notes

- 2026-10-07: Created by the EPIC-3710 pre-implementation review (`/ll:advise --signal user_requested --host claude-code --model opus`, "CONDITIONAL GO", 0.75). The FEAT-3561 go/pause checkpoint needs only implement/refine/explain, yet whole-issue completion front-loaded the loop-specific work; an in-issue milestone is only prose, while `blocked_by` is machine-enforced. Moved the resolve-blocker and run-loop contracts here verbatim (loop fingerprint scope, same-buffer capture, resolution order, logical-name join, loop curves/axes, fan-out wording); added only the `variant` discriminator/project-relative fingerprint-material cross-reference and the explicit-`run` note. No contract was weakened.

## Status

**Open** | Created: 2026-10-07 | Priority: P3
