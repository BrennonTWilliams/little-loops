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
- ENH-2991
labels:
- rework
- verification
testable: true
size: Large
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

## Proposed Change

1. Add the pre-patch-check key to `fsm/schema.py` at both loop level (near `:690`)
   and state level (near `:1311`), following `tamper_guard`'s declaration shape.
2. In `fsm/executor.py`, extend the guarded-window mechanism
   (`:1295-1384`) so a guarded state's exit hook resolves
   `(base_sha, base_dirty)` via `history_reader.read_base_sha(issue_id)` plus
   ENH-2991's `base_dirty` reader, computes the step diff, and calls
   `run_prepatch_check()`.
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
  (near `:690`) and state level (near `:1311`), following `tamper_guard`.
- `scripts/little_loops/fsm/executor.py` — guarded-window entry/exit hook
  extending `:1295-1384`; base resolution, core invocation, `ctx.context` record,
  run-dir bundle write, token-channel export.
- `scripts/little_loops/fsm/validation.py` — lint rule mirroring ENH-2854's.
- `scripts/little_loops/fsm/validation/_base.py` — add the new loop-level key
  (and its `_ok` suppress flag) to `KNOWN_TOP_LEVEL_KEYS` (`:79-134`), or the
  separate unknown-top-level-key check flags the new key itself.
- `scripts/little_loops/loops/oracles/code-run-gate.yaml` — **no state added**;
  left unmodified. Listed only to make the non-change explicit.

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

### Related Issues

- `ENH-2991` (blocking) — the gate core this hosts.
- `ENH-2998` (dependent) — non-FSM adapter and the harness consumer that reads
  the bundle this host writes.
- `ENH-2854` (peer) — supplies the guarded-window mechanism; ordering constraint
  documented above.

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

## Program Design

### Call Path

FSM host: executor guarded-window exit hook -> `read_base_sha` -> `run_prepatch_check` -> `collect_candidate_nodeids` -> `filter_test_files`

The host resolves `(base_sha, base_dirty)` and passes them in; the core is
database-free. The host records its verdict in `ctx.context` following ENH-2854's
`_tamper_guard` record shape and writes the full `PrePatchEvidence` bundle under
`${context.run_dir}/` (MR-3).

## Scope Boundaries

- **Not this issue**: the check itself — `prepatch_check.py`,
  `setup_prepatch_worktree()`, and the `base_dirty` reader are ENH-2991.
- **Not this issue**: the non-FSM `work_verification.py` adapter, `cli/harness.py`
  evidence surfacing, or `skills/verify-issue-loop/` documentation — all ENH-2998.
- **Not this issue**: adding a state to `oracles/code-run-gate.yaml`. The
  superseded 2026-07-30 oracle-state placement is explicitly rejected; that file
  is left unmodified.
- **Not this issue**: replacing or removing the existing LLM-judged semantic
  criteria in verification loops.

## Acceptance Criteria

- [ ] The check is hosted on the executor's guarded-window mechanism (the shape ENH-2854 established at `fsm/executor.py:1295-1384`), not as a state inside `oracles/code-run-gate.yaml` and not inside `cli/harness.py`.
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

## Status

**Open** | Created: 2026-08-02 | Priority: P2

## Session Log
- `/ll:refine-issue` - 2026-08-02T15:22:31 - `1a6be5be-a3c2-4f65-a811-ac343eeaa258.jsonl`
- `/ll:issue-size-review` - 2026-08-02T13:48:44 - `14957793-c5a3-42c3-8c4e-e15ef7fbe208.jsonl`

## Related Key Documentation

- `docs/ARCHITECTURE.md` — describes the FSM loop engine at a high level; this issue extends the executor's guarded-window mechanism, a core piece of that engine.
- `docs/reference/API.md` — documents `fsm/executor`, `fsm/schema`, and `fsm/validation` directly; this issue's new first-class guard key and lint rule are additions to those exact modules.
