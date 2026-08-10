---
id: ENH-2997
title: Host the pre-patch check on the executor's guarded window
type: ENH
priority: P2
status: open
discovered_date: 2026-08-02
epic: EPIC-2856
parent: ENH-2853
blocked_by:
- ENH-3142
labels:
- rework
- verification
testable: true
size: Large
verify_verdict: VALID
confidence_score: 80
outcome_confidence: 71
score_complexity: 10
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 18
reconcile_attempted: true
deferred_by: automation
deferred_date: '2026-08-10T09:58:02Z'
deferred_reason: readiness_stagnated
---

# ENH-2997: Host the pre-patch check on the executor's guarded window

## Summary

Make ENH-2991's pre-patch check reachable from every green-suite transition in
the `rn-*` loop family by hosting it on the FSM executor's guarded-window
mechanism — the same entry/exit bracket ENH-2854 established for `tamper_guard` —
rather than as a state inside `oracles/code-run-gate.yaml`.

## Parent Issue

Decomposed from ENH-2853: Deterministic pre-patch test-failure check in
verification loops. Covers Integration Map Layer 2 (executor half) and the
placement Design Notes.

## Current Behavior

ENH-2991 ships `run_prepatch_check()` as a host-agnostic core that nothing calls.
No FSM mechanism invokes it, so no verification transition is gated by it.

## Expected Behavior

A first-class FSM key (settable loop-level and state-level, mirroring
`tamper_guard`) causes the executor to bracket a guarded state's entry and exit,
compute the step diff, resolve the base state, invoke `run_prepatch_check()`, and
record the verdict in `ctx.context` following ENH-2854's `_tamper_guard` record
shape — with the full `PrePatchEvidence` bundle written under
`${context.run_dir}/` per MR-3. When the key is absent (no state override, no
loop default), the guarded window short-circuits to SKIP rather than failing.

## Motivation — why the executor, not an oracle state

The 2026-07-30 placement review on ENH-2853 correctly ruled out `cli/harness.py`
and `/ll:verify-issue-loop` as owners:

- **No orchestrator invokes `ll-harness`.** A repo-wide grep for `ll-harness`
  across `scripts/little_loops/` returns only its own CLI (`cli/harness.py`), the
  shared `runner_spec.py` abstraction, telemetry readers
  (`history_reader.py:2797+`), and a permission string in `init/writers.py:70`.
  Nothing in `ll-auto`, `ll-parallel`, `ll-sprint`, or any `loops/*.yaml` calls it
  — it is a hand-run one-shot tool.
- **`/ll:verify-issue-loop` is a generator.** A check emitted there exists only
  inside per-issue loop YAML someone chose to generate, never in a standing path.

But that review's *positive* prescription — an additive state in
`oracles/code-run-gate.yaml` reached via the token channel — predates ENH-2854
landing on 2026-07-31, which solved the identical reachability problem for the
identical class of gate a different way:

- ENH-2854 shipped `tamper_guard` as a **first-class FSM key**, settable
  loop-level and state-level (`fsm/schema.py:690` and `:1311`), enforced by the
  executor as snapshot-on-entry / compare-on-exit
  (`fsm/executor.py:1295-1384`), with findings accumulated across guarded states
  in `ctx.context["_tamper_guard"]`, plus a dedicated validation lint rule.
- `code-run-gate.yaml:50` already declares `tamper_guard: fail` at loop level —
  the sibling mechanism is already active in the very file the 07-30 review
  proposed adding a state to.
- **Decisive on the merits, not just on consistency:** this check's input is *the
  diff of the verification step*. A state sitting alongside `run_test` has no
  natural access to that; the executor's entry/exit bracket computes exactly it.

The actual chokepoint for "did these tests prove anything" is
`oracles/code-run-gate.yaml`'s `run_test` state, delegated to by
`rn-refine.yaml:483`, `rn-remediate.yaml:543`, and `rn-implement`'s
`run_code_gate` (`loops/README.md:64`). `code-run-gate.yaml` inherits this check
via the loop-level guard key it already carries — **no state is added to it**.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-10 — based on codebase analysis:_

- **Token-channel idiom, verified current** (`loops/oracles/code-run-gate.yaml`): `subloop_outcome_<ID>.txt` is a plain-text single-token verdict file, one per issue ID — written by shell `echo VERDICT > "subloop_outcome_${context.issue_id}.txt"` (placeholder at `:184-186`, final verdict from the `aggregate` state at `:449-451`, failure paths at `:538`,`:566`), read by shell `cat`/`grep -qxF` in the parent loop (`rn-implement.yaml:772,1182,1271`) or by Python glob + stem-slicing (`rn-implement.yaml:1575-1577`, `run_dir.glob("subloop_outcome_*.txt")`). It carries only a short enum-like verdict string — any richer evidence bundle (this issue's `PrePatchEvidence`) is a separate artifact under `${context.run_dir}/`, referenced alongside the token file, not inside it.
- **Testing convention confirmed**: this codebase's guard-key tests split into two independently-named test classes, one per layer — an executor-integration tier (`TestTamperGuardExecutorHook`, `scripts/tests/test_fsm_executor.py:11225`, builds a real git repo via `tests.helpers.copy_git_template` and a real `FSMExecutor.run()`, no mocked FSM layer, individually named tests per policy value) and a lint-rule tier (`TestTamperGuardValidation`, `scripts/tests/test_fsm_validation_evaluator_rules.py:1242`, builds `FSMLoop`/`StateConfig` objects directly via a `_fsm()` helper, plus one dedicated YAML-round-trip test — `test_tamper_guard_recognized_as_top_level_key` — that exercises the `KNOWN_TOP_LEVEL_KEYS` registration specifically). A `prepatch_check` key should get one test class per tier, mirroring this exact split rather than one combined test file.

## Proposed Change

1. Add the pre-patch-check key to `fsm/schema.py` at both loop level (near
   `:1323,1325`, alongside `tamper_guard`/`tamper_guard_ok`) and state level
   (near `:698`), following `tamper_guard`'s declaration shape.
2. In `fsm/executor.py`, extend the guarded-window mechanism (resolver
   `:1344-1361`, entry snapshot `:1499-1507`, exit-compare/checker
   `:1385-1455`, invoked from both call sites `:1534-1538` and `:1587-1591`)
   so a guarded state's exit hook resolves `(base_sha, base_dirty)` via
   `history_reader.read_base_sha(issue_id)` plus ENH-3142's `base_dirty`
   reader, computes the step diff, and calls `run_prepatch_check()`.
3. Record the verdict in `ctx.context` following ENH-2854's `_tamper_guard`
   record shape, accumulating findings across guarded states.
4. Write the full `PrePatchEvidence` bundle under `${context.run_dir}/` (MR-3),
   and expose it through the parent↔sub-loop token channel (the
   `subloop_outcome_<ID>.txt` idiom `code-run-gate` already uses) so a delegating
   parent loop can read the result.
5. Resolve an absent key to SKIP, exactly as `fsm/executor.py:1305` resolves
   `tamper_guard`'s absence to "not guarded". This is the same short-circuit as
   ENH-2991's config off-switch, at a different layer — it must never resolve to
   a failure.
6. Add a validation lint rule mirroring ENH-2854's, so misuse is caught by
   `ll-loop validate`.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Update `scripts/little_loops/fsm/fsm-loop-schema.json` — declare
  `prepatch_check`/`prepatch_check_ok` at loop level and `prepatch_check` at
  state level, mirroring the existing `tamper_guard` entries.
- Register the new lint rule in
  `scripts/little_loops/fsm/validation/structural_rules.py` alongside
  `_validate_tamper_guard`'s registration.
- Add `TestPrePatchCheckExecutorHook` (`scripts/tests/test_fsm_executor.py`)
  and `TestPrePatchCheckValidation`
  (`scripts/tests/test_fsm_validation_evaluator_rules.py`), each mirroring its
  tamper-guard sibling class method-for-method.
- Add `KNOWN_TOP_LEVEL_KEYS` membership tests and a schema-round-trip test for
  `prepatch_check`, following `test_feat3033_idle_timeout.py:60-61` and
  `test_fsm_schema.py:4571-4579`.
- Update `docs/guides/LOOPS_GUIDE.md` (new `### Pre-Patch Check` section after
  the "Tamper Guard" section), `docs/reference/CLI.md` (new `ll-loop validate`
  rule bullet), `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` (new Design Rules
  table row), and `docs/reference/loops.md` (add the evidence bundle to the
  MR-3 run-dir artifact enumeration).

## Design Notes

- **Skip convention.** Absent key (no state override, no loop default) means "not
  guarded." The knob must short-circuit to a SKIP pass-through, never to a
  failure — a gate that fails closed on an unconfigured loop would break every
  existing loop on upgrade.
- **`code-run-gate.yaml` is left unmodified.** It already declares
  `tamper_guard: fail` at loop level (`:50`); it inherits this check the same way.
  Adding a state there would duplicate a mechanism that already exists.
- **Evidence-bundle transport follows the host.** With the check hosted by the
  executor rather than `ll-harness`, `PrePatchEvidence` cannot ride a
  harness-local `HarnessEvalOutcome`. It reaches the parent through the existing
  token channel with the full bundle under `${context.run_dir}/`, and/or persisted
  to `.ll/history.db`. ENH-2998's harness path reads that same artifact rather
  than producing its own.
- **The host owns base resolution; the core stays DB-free.**
  `history_reader.read_base_sha(issue_id, *, run_id=None, db=DEFAULT_DB_PATH)`
  (`:1816-1821`) is keyed by issue ID, never raises, returns `None` when
  unstamped, and deliberately does not implement the merge-base fallback (which
  ENH-2991 owns). `run_id` is a process-local uuid4 never exported to env,
  run-dir, or argv, so this out-of-process consumer must omit it and take the
  most-recent-stamped-row path. Note `code-run-gate.yaml` already declares
  `issue_id` as a required parameter, so the identifier is available on that path.
- **Ordering against ENH-2854.** ENH-2854's tamper-guard `revert` policy must run
  *after* this check has read the step's diff — stated as a constraint on
  ENH-2854 rather than a blocking edge. Confirm the ordering when wiring both
  into the same guarded window.

## Integration Map

### Files to Modify / Create

- `scripts/little_loops/fsm/schema.py` — new first-class key at loop level
  (near `:1323,1325`, alongside `tamper_guard`/`tamper_guard_ok`) and state
  level (near `:698`), following `tamper_guard`.
- `scripts/little_loops/fsm/executor.py` — guarded-window entry/exit hook
  mirroring `tamper_guard`'s current shape (resolver `:1344-1361`, entry
  snapshot `:1499-1507`, exit-compare/checker `:1385-1455`, invoked from both
  call sites `:1534-1538` and `:1587-1591`); base resolution, core invocation,
  `ctx.context` record, run-dir bundle write, token-channel export.
- `scripts/little_loops/fsm/validation/evaluator_rules.py` — lint rule
  mirroring ENH-2854's `_validate_tamper_guard` (`:368-421`), registered in
  `fsm/validation/structural_rules.py:49,1109`.
- `scripts/little_loops/fsm/validation/_base.py` — add the new loop-level key
  (and its `_ok` suppress flag) to `KNOWN_TOP_LEVEL_KEYS` (`:79-134`), or the
  separate unknown-top-level-key check flags the new key itself.
- `scripts/little_loops/loops/oracles/code-run-gate.yaml` — **no state added**;
  left unmodified. Listed only to make the non-change explicit.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/fsm/fsm-loop-schema.json` — separate JSON Schema (not
  `fsm/schema.py`) that independently declares `tamper_guard`/`tamper_guard_ok`
  at loop level (`:368-377`, inside `properties` whose `additionalProperties:
  false` closes at `:389`) and `tamper_guard` at state level
  (`definitions.stateConfig.properties`, `:591-595`). An unregistered key here
  fails schema validation independently of the Python-side
  `KNOWN_TOP_LEVEL_KEYS` check — a new `prepatch_check`/`prepatch_check_ok`
  pair needs the same entries or schema-based tooling rejects the key.
- `scripts/little_loops/fsm/validation/structural_rules.py` — registers the new
  lint rule (mirrors `_validate_tamper_guard`'s registration at `:49,1109`,
  confirmed current call site `:1111`).

### Similar Patterns to Follow

- `scripts/little_loops/test_tamper_guard.py` + `fsm/executor.py:1295-1384` +
  `fsm/schema.py:690` / `:1311` (ENH-2854, landed 2026-07-31) — **the primary
  template**: the same class of gate, hosted on the executor's guarded window.
- `oracles/code-run-gate.yaml`'s `subloop_outcome_<ID>.txt` token channel — the
  existing parent↔sub-loop result transport.

### Tests

- A test asserting a guarded loop (`rn-implement` / `rn-remediate` / `rn-refine`,
  transitively via `code-run-gate`) actually runs the check — this is the
  reachability claim the whole issue exists to satisfy, so it must be asserted,
  not assumed.
- A test asserting an absent key short-circuits to SKIP rather than failing.
- A test asserting the bundle lands under `${context.run_dir}/` and the
  `ctx.context` record follows the `_tamper_guard` shape.
- `scripts/tests/test_builtin_loops.py` — `code-run-gate.yaml` must remain
  byte-unchanged and valid.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_fsm_executor.py` — new `TestPrePatchCheckExecutorHook`
  class (place near `TestTamperGuardExecutorHook`, `:11225`), one test per
  parity target: `test_fail_policy_routes_to_on_no_when_...`,
  `test_allow_policy_proceeds_despite_...`, `test_no_guard_when_key_absent`,
  `test_tdd_mode_does_not_trip_guard_on_separate_verify_state`,
  `test_fail_policy_blocks_convergent_routing`,
  `test_fail_policy_blocks_next_chained_state`,
  `test_evidence_accumulates_across_guarded_states` — adapted for
  `read_base_sha()` / `run_prepatch_check()` / `ctx.context["_prepatch_check"]`
  / `PrePatchEvidence` in place of the tamper-guard equivalents.
- `scripts/tests/test_fsm_validation_evaluator_rules.py` — new
  `TestPrePatchCheckValidation` class (place near `TestTamperGuardValidation`,
  `:1242`), mirroring `test_fires_for_state_with_unrecognized_value`,
  `test_fires_for_unrecognized_loop_level_default`,
  `test_does_not_fire_for_recognized_values`, `test_does_not_fire_when_unset`,
  `test_suppressed_by_..._ok`, `test_wired_into_validate_fsm`, and a
  `prepatch_check` analog of `test_tamper_guard_recognized_as_top_level_key`
  (`:1318`).
- `scripts/tests/test_feat3033_idle_timeout.py:60-61` —
  `test_default_idle_timeout_is_known_top_level_key` is the membership-check
  template (`assert "default_idle_timeout" in KNOWN_TOP_LEVEL_KEYS`) to mirror
  for `test_prepatch_check_is_known_top_level_key` / `..._ok`; no existing test
  does full set-equality on `KNOWN_TOP_LEVEL_KEYS`, so nothing else breaks.
- `scripts/tests/test_fsm_schema.py:4571-4579` —
  `test_schema_json_declares_state_and_loop_level_tamper_guard` is the
  round-trip template for a parallel assertion (or extension) confirming
  `prepatch_check` is declared in `fsm-loop-schema.json` at both levels.
- Confirmed safe / no change needed: `scripts/tests/test_builtin_loops.py`
  has no byte/hash-level assertion on `code-run-gate.yaml`, `rn-implement.yaml`,
  `rn-remediate.yaml`, or `rn-refine.yaml` — all references parse structural
  fields, not raw content, so leaving those YAMLs unmodified needs no test
  update.

### Related Issues

- `ENH-2991` (blocking) — the gate core this hosts.
- `ENH-2998` (dependent) — non-FSM adapter and the harness consumer that reads
  the bundle this host writes.
- `ENH-2854` (peer) — supplies the guarded-window mechanism; ordering constraint
  documented above.

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_GUIDE.md` § "Tamper Guard" (`:666-704`) — the actual
  user-facing FSM-YAML authoring section for `tamper_guard:` (worked YAML
  example, policy-value table, entry-snapshot-timing note, `ll-loop validate`
  cross-reference). A parallel `### Pre-Patch Check` section belongs
  immediately after it. `docs/ARCHITECTURE.md` and `docs/reference/API.md`
  (cited generically elsewhere in this issue) currently contain zero mentions
  of `tamper_guard` or the guarded-window mechanism — this file, not those, is
  the precise existing anchor to mirror.
- `docs/reference/CLI.md` — under `#### \`ll-loop validate <loop>\`` (`:786`),
  the validation-rules bullet list has a dedicated tamper-guard bullet
  ("Tamper-guard value validity (WARNING)", `:814`) in a uniform
  severity/suppress-flag/issue-ID format. The new lint rule needs a sibling
  bullet here.
- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` § "The Design Rules" table — has
  a dedicated `tamper-guard` row (`:111`, severity + suppress flag
  `tamper_guard_ok: true`). `.claude/CLAUDE.md` § Loop Authoring points readers
  here as "the full rule table" — the new lint rule needs a parallel row, not
  just the CLI.md bullet.
- `docs/guides/RECURSIVE_LOOPS_GUIDE.md` — § "How They Connect" → "1.
  Outcome-token handoff" (`:240-254`) documents the
  `${run_dir}/subloop_outcome_<ID>.txt` sidecar contract this issue's AC
  requires exposing the bundle through; the `summary.json` `per_issue` record
  shape (`:400-405`) is the schema to extend if the bundle needs to surface
  through per-issue aggregation rather than sitting alongside as a separate
  run-dir artifact.
- `docs/reference/loops.md:860` — MR-3's enumerated list of required
  `${context.run_dir}/` artifacts for `code-run-gate.yaml`
  (`commands.json`, `build.txt`, ..., `subloop_outcome_<ID>.txt`). The new
  `PrePatchEvidence` bundle path is a natural addition to this enumeration —
  documentation of the run-dir contract, not a change to the loop file itself
  (which stays unmodified per this issue's Scope Boundaries).
- FYI, no change expected: `skills/audit-loop-run/SKILL.md:341,344` pattern-
  matches on whether a shared next-state's action "contains
  `subloop_outcome_`" for its laundering-mitigation heuristic — a consumer of
  the token channel's presence, not content. Relevant only if the bundle's
  exposure mechanism changes how the token string itself is written, which
  this issue's design (bundle "alongside" the token file) does not do.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Missing file in the Integration Map**: `scripts/little_loops/fsm/validation/_base.py:79-134`
  declares `KNOWN_TOP_LEVEL_KEYS`, the allow-list a loop-level key must join or a
  separate "unknown top-level key" structural check flags the new key itself as
  unrecognized (`"tamper_guard"`/`"tamper_guard_ok"` are already listed at
  `:121-122`). There is no equivalent state-level key allowlist in this codebase
  (a state-level key needs no such registration).
- **The guarded-window bracket is two coordinated call sites, not one wrapper.**
  In `_execute_state`, the entry snapshot is taken once
  (`fsm/executor.py:1450-1458`, gated on `_tamper_policy is not None and
  state.action and self._action_mode(state) != "contract"`), but the exit
  compare (`_check_tamper_guard`) is invoked from *two* independent spots that
  must both be extended: inside the `state.next:`-chained branch
  (`executor.py:1481-1488`, before exit-code routing) and in the non-`next:`
  path after `self._evaluate(...)` (`executor.py:1534-1541`). This split exists
  because an earlier version only guarded one shape (BUG-2962); a state with a
  bare `next:` and no `on_yes`/`on_no` (e.g. `resolve_commands`) only goes
  through the first path.
- **The absent-means-skip resolver is duplicated, not shared, across two
  layers** — `_effective_tamper_guard_policy` in `fsm/executor.py:1295-1312`
  (runtime resolution: `state.tamper_guard or self.fsm.tamper_guard`, any
  unrecognized value silently returns `None`) and a second, independent
  `_effective_tamper_guard` in `fsm/validation/evaluator_rules.py:371-375`
  (lint-time resolution, same precedence, no shared helper function). A new
  key following this template needs both resolvers written, each in its own
  layer.
- **Lint severity convention**: `_validate_tamper_guard`
  (`fsm/validation/evaluator_rules.py:368-421`, registered at
  `fsm/validation/structural_rules.py:49,1109`) emits
  `ValidationSeverity.WARNING`, not `ERROR` — an unrecognized guard value is
  caught but doesn't block load. It checks the loop-level default once and each
  state's own override only (never a state's *inherited* value, which would
  duplicate one bad loop-level default across every non-overriding state).
- **`rn-implement`'s reachability to `code-run-gate` is transitive, not
  direct.** `rn-implement.yaml` has no `run_code_gate` state and does not
  reference `code-run-gate`/`run_code_gate` by name anywhere except one code
  comment (`:993`). It delegates to `rn-remediate` via a `loop: rn-remediate`
  sub-loop state (`~:755`), and `rn-remediate.yaml`'s own `run_code_gate` state
  (`:529-546`) is what delegates to `oracles/code-run-gate.yaml` (`:543`). The
  Motivation section's phrase "`rn-implement`'s `run_code_gate`" should be read
  as this transitive path, not a state literally inside `rn-implement.yaml`.
- **Existing test coverage to extend, beyond `test_tamper_guard.py`**:
  `scripts/tests/test_fsm_executor.py`'s `TestTamperGuardExecutorHook` class
  (`~:10702`) is the executor-integration test tier — it builds a real git repo
  and a real `FSMExecutor.run()` (no mocked FSM layer), with dedicated,
  individually-named tests for the absent-key skip
  (`test_no_guard_when_key_absent`) and for `ctx.context` record-shape
  accumulation (`test_evidence_accumulates_across_guarded_states`, asserting a
  list of length 2 with per-entry `"state"`/`"findings"`/`"passed"` keys).
  `scripts/tests/test_fsm_validation_evaluator_rules.py`'s
  `TestTamperGuardValidation` class (`~:1242`) is the lint-rule test tier,
  including `test_tamper_guard_recognized_as_top_level_key` — a YAML-round-trip
  test asserting the key doesn't trip the `KNOWN_TOP_LEVEL_KEYS` check above. A
  new key should get one test class per tier, mirroring this split.

_Added by `/ll:refine-issue` — 2026-08-10 — based on codebase analysis:_

- **Blocking dependency has changed since this issue was last refined (2026-08-02).** ENH-2991 (the check this issue hosts) is now `status: done`, but its own `## Resolution` records `**Status**: Decomposed` — it shipped no code (`Glob **/prepatch_check.py` returns no matches). The actual work landed in two new, still-`open` children: ENH-3141 (`setup_prepatch_worktree()`) and ENH-3142 (`prepatch_check.py` core, `depends_on: [ENH-3141]`). `blocked_by` has been updated from ENH-2991 to ENH-3142 to reflect the live blocker; ENH-2997 cannot be implemented until ENH-3142 ships `run_prepatch_check()`.
- **Stale line numbers (verified 2026-08-10, `fsm/executor.py` changed 2026-08-09 after this issue's last refine):**
  - `_effective_tamper_guard_policy` — now `fsm/executor.py:1344-1361` (was cited as part of `1295-1384`).
  - `_check_tamper_guard` — now `fsm/executor.py:1385-1455`.
  - Entry snapshot call site — now `fsm/executor.py:1499-1507` (was `~1450-1458`).
  - Exit compare call sites — now `fsm/executor.py:1534-1538` (`next:`-chained branch) and `fsm/executor.py:1587-1591` (non-`next:` path after `self._evaluate(...)`) (were `~1481-1488` and `~1534-1541`).
  - `ctx.context["_tamper_guard"]` accumulation — `fsm/executor.py:1433` (`ctx.context.setdefault("_tamper_guard", []).append(tamper_record)`).
  - State-level `tamper_guard` field — now `fsm/schema.py:698` (was cited as `:1311`).
  - Loop-level `tamper_guard`/`tamper_guard_ok` fields — now `fsm/schema.py:1323,1325` (was cited as `:690`).
  - `TestTamperGuardExecutorHook` — now `scripts/tests/test_fsm_executor.py:11225` (was `~:10702`).
  - `TestTamperGuardValidation` — confirmed current at `scripts/tests/test_fsm_validation_evaluator_rules.py:1242`.
- **`_tamper_guard_candidate_paths`/`_tamper_guard_changed_files`** (`fsm/executor.py:1363-1372`, `:1374-1383`) are thin delegators into `little_loops.test_tamper_guard`'s shared `tamper_guard_candidate_paths()`/`tamper_guard_changed_files()` — the diff-computation primitives are already shared between the FSM executor and the non-FSM `work_verification.py` hook (ENH-2998's territory). A new `prepatch_check` key's diff computation should reuse this same shared layer rather than reimplementing it.
- **`work_verification.py`** (`scripts/little_loops/work_verification.py`) is the non-FSM parallel to this issue's executor hook — its own `_effective_tamper_guard_policy(config: BRConfig)` (line 60) and `_run_non_fsm_tamper_guard(...)` (line 76) are architecturally analogous but out of this issue's scope (ENH-2998 owns that host).

_Added by `/ll:refine-issue` — 2026-08-10 — based on codebase analysis:_

- **A third and fourth example of the loop+state+`_ok`+lint-rule shape exist beyond `tamper_guard`** — `session_mode` (`fsm/schema.py:1329,1331`, resolver `_effective_session_mode` at `fsm/validation/_base.py:187-195`, lint rule `_validate_session_mode_evaluator_inheritance` at `fsm/validation/evaluator_rules.py:506-548`, `KNOWN_TOP_LEVEL_KEYS` entries at `fsm/validation/_base.py:124-125`) and `pruning_profile` (`fsm/schema.py:1320`). Both share tamper_guard's loop-level-default/state-level-override/`_ok`-suppression/paired-lint-rule shape, but their executor enforcement is a **value read at read-time** to gate continuity/prompt behavior (`fsm/executor.py:1799,1801,2084,2112`), not a **snapshot-on-entry/compare-on-exit bracket**. `tamper_guard` remains the only prior example of the entry/exit-bracket shape this issue needs — the other two do not suggest a different convention for a check that must diff a guarded state's action.
- **No shared FSM-fixture/`_fsm()` test helper exists across guard-key test suites** — each test class defines its own local `_fsm()` builder scoped to its own construction needs (`TestTamperGuardExecutorHook._fsm`, `test_fsm_executor.py:11295`; `TestSessionModeEvaluatorInheritance._fsm`, `test_fsm_validation_evaluator_rules.py:547`; `TestHostGuardConfig._fsm`, `test_host_guard.py:602`; others at `test_fsm_executor.py:201,295,7069,7253`). A new `prepatch_check` test class should define its own `_fsm()` following this per-class convention, not attempt to reuse or extract a shared one.
- **`KNOWN_TOP_LEVEL_KEYS` membership testing has two co-existing, non-superseding shapes**: (a) a bare `assert "key" in KNOWN_TOP_LEVEL_KEYS` (`test_feat3033_idle_timeout.py:60-61`) — confirmed as the only membership-assert example in the suite, and already the lightest possible form; (b) a fuller pair for `tamper_guard` specifically — a YAML-round-trip test asserting no unknown-key warning fires (`test_tamper_guard_recognized_as_top_level_key`, `test_fsm_validation_evaluator_rules.py:1318-1338`) plus a JSON-schema-dict-membership assertion (`test_schema_json_declares_state_and_loop_level_tamper_guard`, `test_fsm_schema.py:4571-4579`). No test performs full set-equality on `KNOWN_TOP_LEVEL_KEYS`.
- **Spec-only forward reference to `run_prepatch_check()` has no in-repo staging precedent** — a repo-wide grep for `run_prepatch_check` returns zero hits under `scripts/` (issue-file mentions only). No stub function, `NotImplementedError` placeholder, or feature flag precedent exists anywhere in `fsm/`, `scripts/little_loops/`, or `scripts/tests/` for building an executor hook against a not-yet-existing function. This issue chain's own answer, already encoded in its frontmatter, is hard `blocked_by` sequencing rather than any code-level staging artifact — consistent with keeping this issue blocked on ENH-3142 rather than landing partial/stubbed code ahead of it.

## Program Design

### Call Path

FSM host: executor guarded-window exit hook -> `read_base_sha` -> `run_prepatch_check` -> `collect_candidate_nodeids` -> `filter_test_files`

The host resolves `(base_sha, base_dirty)` and passes them in; the core is
database-free. The host records its verdict in `ctx.context` following ENH-2854's
`_tamper_guard` record shape and writes the full `PrePatchEvidence` bundle under
`${context.run_dir}/` (MR-3).

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-10 — based on codebase analysis:_

_Added by `/ll:refine-issue` — 2026-08-10 — based on codebase analysis:_

- **Failure-routing contract for `_check_prepatch_check` to replicate**: `_check_tamper_guard` (`fsm/executor.py:1447-1455`) does not use a single lookup — it chains three tiers: (1) `state.on_no` if `state.on_no in get_failure_states()` (`fsm/schema.py:1618-1627`, a `{name for name, state in self.states.items() if state.failure}` comprehension); (2) else `sorted(get_failure_states())[0]` — the lexicographically-first failure-flagged state in the whole FSM, not a semantic "closest" one; (3) else bare `state.on_no` (may be `None`). A new prepatch-check checker must replicate all three tiers, not just tier 1, to cover both loops with a per-state `on_no` failure target and loops with only a shared `failure: true` terminal.
- **Return-value contract**: both call sites (`fsm/executor.py:1534-1538`, `:1587-1591`) do `if _tamper_next is not None: return _tamper_next` — an unconditional early `return` from `_execute_state` that skips all subsequent bookkeeping in that function (exit-code branching, `_evaluate`, `prev_result`/stall-detector updates at `:1596-1674` for the non-`next:` path). The returned string flows straight through the run loop (`fsm/executor.py:689,748-763,766-798`) with no membership check against `self.fsm.states` at assignment time — it relies on load-time validation (`fsm/validation/structural_rules.py:970-982`, `get_referenced_states()` includes `on_no`) to guarantee the target exists; a new checker inherits this same guarantee only if it returns exclusively `state.on_no` or a member of `get_failure_states()`, never a hand-constructed string.
- **`_tamper_guard` record shape to mirror** (`fsm/executor.py:1423-1433`): `{"state": str, "policy": Literal["revert","fail","allow"], "passed": bool, "findings": [{"path": str, "kind": str, "is_config": bool}, ...], "reverted": list[str]}`, appended via `ctx.context.setdefault("_tamper_guard", []).append(record)` — one record per guarded-state execution, list never overwritten. A `"_prepatch_check"` accumulator follows the identical `setdefault(KEY, []).append(record)` shape under its own key to coexist without collision.
- **No existing timeout-config surface for this call site**: `_check_tamper_guard`'s call chain has no timeout handling of its own — the only subprocess boundary (`test_tamper_guard.py:572-586`'s `_git()` helper) wraps a module-level `_GIT_TIMEOUT = 10` constant with `except subprocess.TimeoutExpired: return None`, not FSM-config-driven. The executor's `state.timeout`/`state.idle_timeout` knobs (`fsm/executor.py:2208-2223,2800-2826`) are wired only to the action-runner subprocess, not this guard path. `run_prepatch_check(..., timeout_s: int)` therefore introduces a new timeout-config surface into this call site rather than reusing an existing knob — closest existing precedent for "swallow timeout, degrade safely" is `_git()`'s catch-and-return-None idiom, not the action-runner's `ActionResult(exit_code=124, timeout_kind=...)` idiom.

### Types

- `PrePatchEvidence` — the dataclass `run_prepatch_check()` returns; specified but not yet implemented (ENH-3142 § Program Design § Types). Not present in the codebase today — `Glob` for `**/prepatch_check.py` returns no matches.

### Signatures

- `run_prepatch_check(step_diff: str, base_sha: str | None, base_dirty: bool | None, timeout_s: int) -> PrePatchEvidence` — the target call the executor hook would make, per ENH-3142 § Program Design § Signatures (spec only; module does not exist yet).
- `history_reader.read_base_sha(issue_id: str, *, run_id: str | None = None, db: Path | str = DEFAULT_DB_PATH) -> str | None` (`scripts/little_loops/history_reader.py:1816-1869`) — current and verified. Never raises (DB-open failure or `sqlite3.Error` both caught, return `None`); returns `None` when unstamped; implements no merge-base fallback (docstring assigns that to the consumer).
- A `base_dirty` reader alongside `read_base_sha` does not exist yet — only a `base_dirty` column/field exists on the write side (`session_store/writers.py::record_orchestration_run()`). The additive reader is scoped into ENH-3142, unimplemented.
- `_effective_tamper_guard_policy(self, state: StateConfig) -> Literal["revert", "fail", "allow"] | None` (`fsm/executor.py:1344-1361`) — the resolver shape a new `_effective_prepatch_check_policy()` would mirror: `state.<key> or self.fsm.<key>`, any unrecognized value collapses to `None`.
- `_check_tamper_guard(self, state, ctx, tamper_before, tamper_policy, repo_root) -> str | None` (`fsm/executor.py:1385-1455`) — the compare-on-exit/record/route-on-fail shape a new `_check_prepatch_check()` would mirror.

### Call Path (current, verified 2026-08-10 — supersedes the issue's original stale citations)

`_execute_state` entry (`fsm/executor.py:1499-1507`, resolves `_effective_tamper_guard_policy`, snapshots before action runs) -> action executes -> exit compare from one of two call sites: `next:`-chained branch (`fsm/executor.py:1534-1538`) or non-`next:` path after `self._evaluate(...)` (`fsm/executor.py:1587-1591`) -> `_check_tamper_guard` (`fsm/executor.py:1385-1455`) appends to `ctx.context["_tamper_guard"]` (`:1433`) and, on `policy: fail` with a finding, routes to `state.on_no` or the FSM's failure terminal.

A `prepatch_check` key would follow the identical two-call-site bracket, with its own resolver/checker pair calling into `history_reader.read_base_sha()` + the not-yet-existing `base_dirty` reader, then `run_prepatch_check()` once ENH-3142 ships it.

### Schema Anchors (current, verified 2026-08-10 — supersedes the issue's original stale `:690`/`:1311` citations)

- State-level `tamper_guard` field (the template to mirror): `StateConfig.tamper_guard: str | None = None`, `fsm/schema.py:698` (declaration), `:801-802` (`to_dict`), `:911` (`from_dict`).
- Loop-level `tamper_guard` field + suppression companion: `FSMLoop.tamper_guard: str | None = None` and `tamper_guard_ok: bool = False`, `fsm/schema.py:1323,1325` (declaration), `:1445-1448` (`to_dict`), `:1577-1578` (`from_dict`).
- `KNOWN_TOP_LEVEL_KEYS` entries for the loop-level key + its `_ok` companion: `fsm/validation/_base.py:79-134` (currently lists `"tamper_guard"`/`"tamper_guard_ok"`; a new loop-level key needs the same pair added here).

### Decision Rules

N/A — no new decision logic; this issue extends an existing skip/guard mechanism with a new key, it does not introduce a new gap kind, gate, keyword list, or threshold.

## Scope Boundaries

- **Not this issue**: the check itself — `prepatch_check.py`'s core is
  ENH-3142, `setup_prepatch_worktree()` is ENH-3141, and the `base_dirty`
  reader is scoped into ENH-3142 (ENH-2991 shipped no code; it was decomposed
  into these two children).
- **Not this issue**: the non-FSM `work_verification.py` adapter, `cli/harness.py`
  evidence surfacing, or `skills/verify-issue-loop/` documentation — all ENH-2998.
- **Not this issue**: adding a state to `oracles/code-run-gate.yaml`. The
  superseded 2026-07-30 oracle-state placement is explicitly rejected; that file
  is left unmodified.
- **Not this issue**: replacing or removing the existing LLM-judged semantic
  criteria in verification loops.

## Acceptance Criteria

- [ ] The check is hosted on the executor's guarded-window mechanism (the shape ENH-2854 established in `fsm/executor.py`: resolver `:1344-1361`, entry snapshot `:1499-1507`, exit-compare/checker `:1385-1455`, invoked from call sites `:1534-1538` and `:1587-1591`), not as a state inside `oracles/code-run-gate.yaml` and not inside `cli/harness.py`.
- [ ] `oracles/code-run-gate.yaml` is left unmodified; a test asserts it.
- [ ] A first-class FSM key is settable at loop level and state level, mirroring `tamper_guard`'s declaration in `fsm/schema.py`.
- [ ] The check is reachable from the `rn-*` family's green-suite transitions; a test asserts a guarded loop (`rn-implement` / `rn-remediate` / `rn-refine`, transitively via `code-run-gate`) actually runs the check.
- [ ] The host records its verdict in `ctx.context` following ENH-2854's `_tamper_guard` record shape, accumulating findings across guarded states.
- [ ] The full `PrePatchEvidence` bundle is written under `${context.run_dir}/` (MR-3) rather than only inside an in-memory record, and is exposed through the existing parent↔sub-loop token channel.
- [ ] When the check's key is absent (no state override, no loop default), the guarded window short-circuits to SKIP rather than failing the gate; a test covers it.
- [ ] The host resolves the base via `history_reader.read_base_sha(issue_id)` plus the `base_dirty` reader and passes both in as arguments; a test asserts the core still performs no database access on this path.
- [ ] A `ll-loop validate` lint rule mirroring ENH-2854's catches misuse of the new key.
- [ ] ENH-2854's tamper-guard `revert` policy runs after this check has read the step's diff when both are active on the same window.

## Impact

- **Priority**: P2 — without this, ENH-2991's core is unreachable from any
  production verification path and the hole stays open.
- **Effort**: Medium — the mechanism already exists; this extends it.
- **Risk**: Medium — touches the FSM executor's guarded-window path, which
  `tamper_guard` shares. The SKIP-when-absent convention is what keeps existing
  loops unaffected.
- **Breaking Change**: No — new optional key, absent means unguarded.

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-08-10_

**Readiness Score**: 80/100 → STOP — ADDRESS GAPS (dependency hard override)
**Outcome Confidence**: 71/100 → MODERATE

### Gaps to Address
- Blocking dependency `ENH-3142` (`prepatch_check.py` core, `run_prepatch_check()`) is still `status: open` — this issue's host cannot call a function that does not exist yet. Wait for ENH-3142 to ship, or reprioritize it, before starting implementation here.

### Outcome Risk Factors
- Moderate cross-module depth: the guarded-window extension touches `fsm/executor.py`'s two independent exit-compare call sites plus `fsm/schema.py`, `fsm/validation/_base.py`, and `fsm-loop-schema.json` in lockstep — a multi-file, shared-state change even though each site individually mirrors an existing `tamper_guard` template.
- The `PrePatchEvidence` type and `run_prepatch_check()` signature this issue calls are spec-only (owned by ENH-3142) — until that lands, the exact shape of the host's integration point cannot be verified against real code.

## Status

**Open** | Created: 2026-08-02 | Priority: P2

## Session Log
- `/ll:confidence-check` - 2026-08-10T09:57:39 - `40b2e08b-9835-4e53-8675-e53c294cbfce.jsonl`
- `/ll:reconcile-issue` - 2026-08-10T09:55:49 - `b5382982-7500-4b49-9d05-5f4f4a33c4aa.jsonl`
- `/ll:confidence-check` - 2026-08-10T09:51:48 - `de80fea3-8c54-460f-b1ea-12e8ab77b5be.jsonl`
- `/ll:refine-issue` - 2026-08-10T09:47:54 - `3b2bc154-0af6-4e2e-9a39-37d002e7241d.jsonl`
- `/ll:confidence-check` - 2026-08-10T09:41:22 - `300fd485-89f6-4889-8737-0a649a723a68.jsonl`
- `/ll:verify-issues` - 2026-08-10T09:38:57 - `0b97f898-84d2-461d-8674-160d8b6584bc.jsonl`
- `/ll:wire-issue` - 2026-08-10T09:35:20 - `25755245-dbb7-4d56-9480-5e59248a3c94.jsonl`
- `/ll:refine-issue` - 2026-08-10T09:25:37 - `ac54a579-51fd-4f94-9e74-9f64d18f429b.jsonl`
- `/ll:refine-issue` - 2026-08-02T15:22:31 - `1a6be5be-a3c2-4f65-a811-ac343eeaa258.jsonl`
- `/ll:issue-size-review` - 2026-08-02T13:48:44 - `14957793-c5a3-42c3-8c4e-e15ef7fbe208.jsonl`

## Related Key Documentation

- `docs/ARCHITECTURE.md` — describes the FSM loop engine at a high level; this issue extends the executor's guarded-window mechanism, a core piece of that engine.
- `docs/reference/API.md` — documents `fsm/executor`, `fsm/schema`, and `fsm/validation` directly; this issue's new first-class guard key and lint rule are additions to those exact modules.
