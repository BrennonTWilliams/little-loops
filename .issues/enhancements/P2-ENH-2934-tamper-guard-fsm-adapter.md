---
id: ENH-2934
title: Tamper guard FSM adapter - state-level tamper_guard key
type: ENH
priority: P2
status: done
discovered_date: 2026-07-30
completed_at: '2026-07-31T04:36:52Z'
epic: EPIC-2856
parent: EPIC-2856
blocked_by:
- ENH-2933
labels:
- rework
- verification
relates_to:
- ENH-2854
decision_needed: false
confidence_score: 96
outcome_confidence: 77
score_complexity: 15
score_test_coverage: 22
score_ambiguity: 18
score_change_surface: 22
---

# ENH-2934: Tamper guard FSM adapter - state-level tamper_guard key

## Parent Issue

Decomposed from ENH-2854: Guard against agent edits to test files during
verification. This child covers the FSM half of the guard's surface — the
declarative `tamper_guard:` state key, its lint rule, and the `executor.py`
hook. ENH-2933 (the guard core) has landed (`3c8135a3`), unblocking this
issue.

## Summary

Wire the tamper guard core (ENH-2933) into the FSM executor via a
state-level `tamper_guard: revert | fail | allow` key (with an optional
loop-level default), so any loop can opt a verification state into
tamper detection declaratively, exactly like `model:`, `session_mode:`, and
`pruning_profile:` today.

## Motivation

See ENH-2854 for the full origin. This piece specifically closes the gap for
loops (`rn-implement.yaml`, `autodev.yaml`, `code-run-gate.yaml`) whose
verification steps gate a transition on a green test suite — without this
adapter, the guard core exists but no loop can actually use it.

## Proposed Solution

1. **Schema**: declare `tamper_guard: str | None` on `StateConfig`
   (`scripts/little_loops/fsm/schema.py`, alongside `pruning_profile`/
   `session_mode`), and the matching property in
   `scripts/little_loops/fsm/fsm-loop-schema.json` (state-level ~L567-572,
   loop-level default + `_ok` suppression flag ~L354-358). A loop-level
   default that states inherit is allowed (same pattern as
   `pruning_profile`); the executor resolves state-over-loop.
2. **Lint**: a WARN validator on an unrecognized `tamper_guard` value,
   following `_validate_session_mode_evaluator_inheritance()`
   (`scripts/little_loops/fsm/validation/evaluator_rules.py:450-496`) as the
   exact recipe — declare the field, enforce the enum only at the
   validation layer, gate behind a `tamper_guard_ok` suppression flag
   registered in `scripts/little_loops/fsm/validation/_base.py`
   (~L120-122), wired the way `_validate_pruning_profile()` is wired in
   `scripts/little_loops/fsm/validation/structural_rules.py` (~L1082), and
   registered for import in `scripts/little_loops/fsm/validation/__init__.py`
   (which also maintains the MR-rule-code docstring registry — add an entry
   there).
3. **Executor hook**: resolve the state-level key (state over loop
   default) and hook snapshot-on-entry / compare-on-exit around the guarded
   state's execution, calling `run_tamper_guard` (ENH-2933) at each edge.
   The stall-detector integration
   (`scripts/little_loops/fsm/executor.py` ~L1408-1439:
   `self._stall_detector.record`/`.check()` → abort-or-route, a side-channel
   check independent of the main evaluator verdict) is the structural
   analog to follow; the main action-result → verdict wiring is
   ~L1326-1420, L1954-2010.
4. **`fail` policy enforcement**: when the guard's `TamperReport.passed` is
   `False` under `fail`, the transition must not proceed — route the same
   way an evaluator failure routes today.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Anchor confirmation**: all `Files to Modify` line anchors were re-verified
  against the current tree and are accurate to within a line or two
  (`schema.py` state fields 677-690, `executor.py` stall-detector side
  channel 1408-1440, `_validate_session_mode_evaluator_inheritance()`
  exactly at `evaluator_rules.py:450-496`, `evaluate_diff_stall()` exactly
  at `evaluators.py:594-687`, `_validate_pruning_profile()` call site
  exactly at `structural_rules.py:1082`, `fsm-loop-schema.json`
  `pruning_profile` state/loop keys exactly at 567/354). One correction:
  `executor.py`'s main verdict dispatcher `_evaluate()` starts at line
  1955, not 1954.
- **`_validate_pruning_profile()` is defined in `evaluator_rules.py:251`,
  not `structural_rules.py`** — `structural_rules.py:1082` only imports and
  calls it. Point 2's phrasing is ambiguous on this; the new
  `tamper_guard` validator should live in `evaluator_rules.py` alongside
  it and `_validate_session_mode_evaluator_inheritance()`.
- **`session_mode` has zero entries in `fsm-loop-schema.json`** (confirmed
  via grep — no matches at all), despite being declared on both
  `StateConfig` and `FSMLoop` in Python. The issue's schema line
  references (`~L354-358`, `~L567-572`) are `pruning_profile`'s locations
  (an object `$ref`), not a precedent for a bare string enum like
  `tamper_guard`/`session_mode`. See the Option A/B decision below.
- **Loop-level default + suppression flag need two separate additions**,
  not one: (1) `FSMLoop.tamper_guard: str | None` and
  `FSMLoop.tamper_guard_ok: bool = False` dataclass fields in
  `schema.py` (~L1300-1335 region, alongside `pruning_profile`/
  `session_mode` and their `_ok` siblings, each with a one-line
  issue-code comment per existing convention), and (2) the
  `"tamper_guard"`/`"tamper_guard_ok"` string-literal pair added to the
  `KNOWN_TOP_LEVEL_KEYS` frozenset in `validation/_base.py` (lines 79-135,
  `pruning_profile`/`session_mode` pairs at 119-122) so unknown-loop-key
  validation doesn't flag them.
- **Resolution-helper placement precedent is split**: `_effective_pruning_profile()`
  lives in `evaluator_rules.py:244-248`; `_effective_session_mode()` lives
  in `validation/_base.py:184-192`. The *executor's own* runtime
  resolution doesn't call either helper — it duplicates the
  state-then-loop precedence inline (`executor.py:1696`:
  `_pruning_profile_cfg = state.pruning_profile or self.fsm.pruning_profile`).
  Follow that inline-duplication shape for the executor hook's runtime
  resolution, and add a `_effective_tamper_guard(fsm, state)` helper in
  `evaluator_rules.py` (next to `_effective_pruning_profile`) purely for
  the validator's use.
- **`evaluate_diff_stall()`'s cross-call `.loops/tmp/` file persistence
  idiom is a partial mismatch, not a direct template**: it exists to
  survive *separate Python-process invocations* across FSM iterations.
  The tamper guard's snapshot-on-entry/compare-on-exit instead brackets a
  *single* `_execute_state()` call (entry action dispatch → exit), so an
  in-memory local variable inside that one method call is sufficient —
  no cache-key file needed. Only `evaluate_diff_stall()`'s cache-key
  hashing shape (`hashlib.md5("|".join(sorted(scope))...)`) is worth
  reusing, not its on-disk storage mechanism. This also sidesteps MR-3
  (`.claude/CLAUDE.md`), which flags new bare-`.loops/tmp/` artifacts.
- **The guard should bracket `_run_action`/`_run_action_or_route()`
  (state.action dispatch, ~`executor.py:1377`), not just the
  exception-routing wrapper** — a tamper-relevant file change can happen
  regardless of whether the action raised, so snapshot-before must
  precede the action call and compare-after must run even on an action
  exception.
- **`fail`-policy "must not proceed" has two established precedents** in
  `_execute_state()` to choose between: (a) force `verdict` to
  `"no"`/`"error"` before the `_route()` call at line 1558 so the
  existing `on_no`/`on_error` shorthand (lines 2090-2091) fires
  naturally, or (b) return an early forced target the way the stall
  detector's `stall_route_target` does (set ~line 1440, honored at
  1532-1533, pre-empting `_route()` entirely). Either is a legitimate
  choice; (b) more closely matches the "side-channel check independent
  of the main evaluator verdict" framing already in this issue's
  Program Design → Call Path.
- **No exact "reject an unrecognized enum value" WARN-validator precedent
  exists.** The closest analog is MR-14's `_validate_evaluate_unknown_keys()`
  (`structural_rules.py:1483-1536`), which takes the pre-parse `raw_data`
  dict as an explicit second argument — necessary because the dataclass
  loader silently accepts any string into `tamper_guard: str | None` with
  no built-in rejection, the same trap MR-14 exists to catch for unknown
  mapping keys. `_validate_session_mode_evaluator_inheritance()` (the
  issue's stated template) checks *inheritance shape* for specific
  evaluator types, not *value validity* — the new validator needs both
  shapes: iterate all states with a `tamper_guard` value (state or
  inherited loop default) and flag any value outside
  `{"revert", "fail", "allow"}`.
- **`test_tamper_guard.py`'s landed API** (ENH-2933, already merged at
  `3c8135a3`): `run_tamper_guard(before: TamperSnapshot, changed_files:
  list[str], config: BRConfig, policy: TamperPolicy, repo_root: Path) ->
  TamperReport` is the single call the hook needs post-action. Per the
  module's own docstring (lines 1-9), **the adapter (this issue) owns
  step timing**: call `snapshot_test_paths(paths, repo_root)` itself
  immediately before the guarded state's action runs (paths = test files
  via `filter_test_files()` ∪ `resolved_pytest_config_paths(repo_root)`),
  then call `run_tamper_guard(before, changed_files, config, policy,
  repo_root)` after, with `changed_files` sourced from a post-action
  `git diff` the executor runs itself — `test_tamper_guard.py` never
  calls into the adapter.

### Codebase Research Findings — Schema Shape Decision

> **Selected:** Option A — explicit JSON-schema properties for `tamper_guard`, matching the `pruning_profile` pattern; `tamper_guard`'s planned enum-validity validator (unlike `session_mode`'s inheritance-only check) justifies schema-level documentation, and stacking a second silently-invisible field on top of `session_mode`'s existing gap is avoided.

**Option A**: Add explicit JSON-schema properties for `tamper_guard` —
state-level near where `pruning_profile`'s object property sits
(`fsm-loop-schema.json:567-572`), loop-level default + `tamper_guard_ok`
near its loop-level property (`~L354-358`) — enforcing the value shape at
the schema layer the same way `pruning_profile`'s `$ref` object does.

**Option B**: Follow `session_mode`'s existing precedent — declare the
field only in the Python dataclasses (`StateConfig.tamper_guard`,
`FSMLoop.tamper_guard`) with **no** corresponding `fsm-loop-schema.json`
property at all. `session_mode` has zero JSON-schema entries today despite
the file enforcing `additionalProperties: false` elsewhere, and nothing in
the codebase has broken as a result.

**Recommended**: Option A — this issue's own design already commits to a
dedicated WARN lint validator for `tamper_guard` (unlike `session_mode`,
which has no equivalent validator), so treating the field as
schema-significant is consistent with that intent. An explicit schema
property also gives editor/IDE-level JSON-schema validation as an
independent surface, and avoids adding a second silently-schema-invisible
field on top of `session_mode`'s existing gap.

### Decision Rationale

**Selected: Option A** — explicit `fsm-loop-schema.json` properties for
`tamper_guard` (state-level, loop-level default, `tamper_guard_ok`
suppression flag), following the `pruning_profile` shape.

**Scoring:**

| Option | Consistency | Simplicity | Testability | Risk | Total |
|---|---|---|---|---|---|
| A — explicit JSON-schema properties | 3 | 2 | 3 | 2 | 10/12 |
| B — dataclass-only (`session_mode` precedent) | 2 | 3 | 2 | 2 | 9/12 |

**Key evidence:**
- `pruning_profile` is a direct structural template for Option A: loop-level
  `$ref` default + state-level `$ref` override + co-located `_ok`
  suppression flag (`fsm-loop-schema.json:354-362`, `567-570`,
  `376` definition) — the exact shape proposed for `tamper_guard`/
  `tamper_guard_ok`.
- Both the loop-level object and `stateConfig` set `additionalProperties:
  false` (`fsm-loop-schema.json:374`, `821`), and the codebase already
  treats dataclass/schema drift as a real bug class: the ENH-2896 lockstep
  test (`test_fsm_schema.py:261-277`,
  `test_schema_json_evaluate_config_properties_match_dataclass_fields`)
  exists specifically because a field (`line`) was once accepted by the
  Python loader but rejected by the schema, or vice versa.
- Countervailing evidence for Option B: no code in `scripts/little_loops/`
  actually invokes the `jsonschema` library against `fsm-loop-schema.json`
  at runtime — the file functions only as an editor/IDE `$schema` hint plus
  the narrow `evaluateConfig`-only lockstep test. `session_mode` has zero
  schema entries today (confirmed via grep) and nothing has broken as a
  result, so Option B is a lower-effort, equally-precedented path.
- The deciding factor: `tamper_guard` is getting a dedicated WARN validator
  that checks *value validity* (enum membership), unlike `session_mode`'s
  validator (`_validate_session_mode_evaluator_inheritance()`,
  `evaluator_rules.py:450-496`), which only checks inheritance shape. A
  field with real enum semantics benefits more from schema-level
  documentation/IDE validation than one with none, and avoids compounding
  `session_mode`'s known documentation gap with a second invisible field.

## Design Notes

- Presence of the `tamper_guard:` key on a state is what marks it as
  guarded — no new FSM-level "verify-step start" event, no inference from
  action content.
- With `commands.tdd_mode: true`, the implement phase legitimately writes
  tests before code. The snapshot is taken at *this guarded state's entry*,
  never at issue start — a TDD run whose implement phase added tests must
  not trip the guard on the (separate) verify state.
- `evaluate_diff_stall()` (`scripts/little_loops/fsm/evaluators.py`
  L594-686) is the persistence idiom to copy for caching a prior snapshot
  under a key derived from scope — same shape, but hashing test-file
  *content* instead of `git diff --stat` output.

## Program Design

### Types

Reuses `TamperPolicy`, `TamperReport` from ENH-2933's
`scripts/little_loops/test_tamper_guard.py`. No new types beyond the
`StateConfig.tamper_guard: str | None` field.

### Call Path

`StateConfig.tamper_guard` → `executor._execute_state` (snapshot on state
entry) → ... state action runs ... → `executor._execute_state` (compare on
state exit) → `run_tamper_guard` (ENH-2933) → `apply_tamper_policy` → on
`fail` with `passed=False`, route as a failed transition; otherwise proceed,
attaching the `TamperReport` to run evidence.

## Files to Modify

- `scripts/little_loops/fsm/schema.py` (~L677-690) — declare `tamper_guard` on `StateConfig`.
- `scripts/little_loops/fsm/fsm-loop-schema.json` (state-level ~L567-572, loop-level default ~L354-358).
- `scripts/little_loops/fsm/executor.py` (~L1398-1439 region) — snapshot-on-entry / compare-on-exit hook, `fail`-policy transition routing.
- `scripts/little_loops/fsm/validation/evaluator_rules.py` — new WARN validator for unrecognized `tamper_guard` values.
- `scripts/little_loops/fsm/validation/_base.py` (~L120-122) — register `tamper_guard_ok` suppression flag.
- `scripts/little_loops/fsm/validation/structural_rules.py` (~L1082-adjacent) / `scripts/little_loops/fsm/validation/__init__.py` — wire the new validator in; add its entry to the MR-rule-code registry.
- `docs/guides/LOOPS_GUIDE.md` (near `pruning_profile:` L606-636, `session_mode:` L640-662) — new `tamper_guard:` subsection with a YAML example and validator cross-reference.
- `docs/reference/CLI.md:761-787` (`ll-loop validate` rule catalog) and its suppression-flag sentence (~L779) — new entry for the tamper-guard validator and `tamper_guard_ok`.
- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md:313,326` — fold the new validator into the MR-rule-code summary (or explicitly leave it un-coded, matching `session-mode-eval`/`pruning_profile`).

### Tests
- FSM-schema test for the new `tamper_guard:` state key — follow the existing per-key state-field tests around `fsm/schema.py`'s schema tests.
- `scripts/little_loops/fsm/fsm-loop-schema.json`'s `stateConfig` sets `additionalProperties: false`; add a lockstep test (matching `test_fsm_schema.py:261-277`'s `test_schema_json_evaluate_config_properties_match_dataclass_fields` pattern) asserting `tamper_guard` is present in both `StateConfig` and `stateConfig.properties`.
- `scripts/tests/test_fsm_executor.py:8680`, `TestStallDetector` — copy template for the executor hook: drive a real `FSMExecutor.run()` through a minimal `FSMLoop`/`StateConfig` fixture with a `MockActionRunner`, assert on `result.terminated_by`/routed events for each policy.
- `scripts/tests/test_fsm_validation_evaluator_rules.py:540`, `TestSessionModeEvaluatorInheritance` — copy template for the new WARN validator's test class: `_fsm(...)` fixture, `test_fires_for_*`/`test_does_not_fire_for_*`, `test_suppressed_by_tamper_guard_ok`, `test_wired_into_validate_fsm`.
- `scripts/tests/test_fsm_evaluators.py:TestDiffStallEvaluator` (~L1461-1610) — template for the two-invocation "baseline call, then compare call" pattern, if the snapshot caching is implemented as an evaluator-adjacent mechanism.
- `scripts/tests/test_builtin_loops.py:TestCodeRunGateOracle`, `TestCodeRunGateOracleWiring`, `TestVerifyStateConfigReadShell` — update if the guard's hook rewrites the `verify`/`code-run-gate` state `action` strings these tests assert on literally.

## Scope Boundaries

**In scope:** the `tamper_guard:` state key and its schema/lint, the
`executor.py` snapshot-on-entry/compare-on-exit hook and `fail`-policy
transition routing, and the state-over-loop-default resolution.

**Out of scope:**
- The guard core itself (`snapshot_test_paths`, `compare_snapshots`,
  `apply_tamper_policy`, `run_tamper_guard`) — ENH-2933, consumed here.
- The non-FSM verification path (`ll-auto`/`ll-parallel`/`ll-sprint`,
  `work_verification.py`) and the project-global config default key —
  ENH-2935.
- `project.test_patterns` — ENH-2973.

## Acceptance Criteria

- [x] `tamper_guard: revert | fail | allow` is a valid `StateConfig` field, with an optional loop-level default; state wins when both are set.
- [x] `ll-loop validate` warns on an unrecognized `tamper_guard` value; the warning is suppressible via `tamper_guard_ok`.
- [x] A `tamper_guard`-bearing state snapshots test files (via ENH-2933) on entry and compares on exit; a state without the key gets no guard.
- [x] A TDD-mode run (`commands.tdd_mode: true`) whose implement phase writes tests does not trip the guard on a later, separate verify state — the snapshot is taken at the guarded state's own entry, never at issue/run start.
- [x] Under `fail`, a tripped guard fails the transition and the touched files are visible in routed evidence.
- [x] Under `revert`, pre-existing test files are restored before scoring proceeds; a newly-added test file is never deleted.
- [x] Under `allow`, the transition proceeds and findings are still recorded in run evidence.
- [x] The guard makes no LLM calls in this adapter (delegates entirely to ENH-2933's core).
- [x] `docs/guides/LOOPS_GUIDE.md`, `docs/reference/CLI.md`, and `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` are updated per Files to Modify.
- [x] Precedence: within the FSM, an explicit state-level `tamper_guard:` always wins over a loop-level default — a test covers this level winning.

## Impact

- **Priority (P2)**: inherited from ENH-2854.
- **Effort**: Medium — schema + validator + executor hook, following the `pruning_profile`/`session_mode`/stall-detector structural analogs closely.
- **Risk**: Low-Moderate — the executor hook touches a hot path (`_execute_state`); the stall-detector side-channel precedent bounds the risk.

## Confidence Check Notes

**Readiness: 96/100 | Outcome Confidence: 77/100 | Recommendation: STOP — ADDRESS GAPS (Program Design hard override)**

### Gaps to Address
- Program Design: no signature-shaped line found in Types/Signatures — `ll-issues format-check` flags the `## Program Design` → `### Types` section as non-specific despite naming `StateConfig.tamper_guard: str | None`. Remedy: run `/ll:refine-issue` or `/ll:reconcile-issue` to add a repo-resolvable signature line the linter recognizes, or set `program_design_not_applicable: true` if this is judged genuinely trivial (not recommended here — the change touches schema, executor hot path, and validation).
- `format-check` also reports `Current Behavior` and `Expected Behavior` sections as missing (informational; not part of the hard override).

## Resolution

Implemented per the Program Design's Call Path exactly: `StateConfig.tamper_guard`
(+ `FSMLoop.tamper_guard`/`tamper_guard_ok` loop-level default and suppression
flag) resolved state-over-loop in `executor.py`'s new
`_effective_tamper_guard_policy()`. `_execute_state()` snapshots candidate
test/pytest-config paths on entry (`_tamper_guard_candidate_paths()`, git
ls-files-based) and compares on exit (`_tamper_guard_changed_files()` +
`run_tamper_guard`), bracketing the action dispatch per the design notes. Under
`fail` with a tripped guard, the eval verdict is force-overridden to
`on_no`/`on_error`'s target (Design Notes' approach (a)) before `_route()`
runs, so existing routing shorthand fires naturally — no new routing config
needed. A new `_validate_tamper_guard()` WARN rule (evaluator_rules.py) flags
an unrecognized value at either the loop or state level, wired into
`validate_fsm()` and gated by `tamper_guard_ok`. Schema declared on both sides
(`StateConfig`/`FSMLoop` dataclasses + `fsm-loop-schema.json`, Option A per the
issue's decision). Docs updated: `LOOPS_GUIDE.md` (new "Tamper Guard"
subsection), `CLI.md` (validator catalog entry), `HARNESS_OPTIMIZATION_GUIDE.md`
(new un-numbered `tamper-guard` row, matching the `policy-table`/
`terminal-action-ok` precedent for rules with no MR-number).

Tests added: `TestTamperGuard` (test_fsm_schema.py, round-trip + precedence +
schema-json presence), `TestTamperGuardValidation`
(test_fsm_validation_evaluator_rules.py, WARN firing/suppression/wiring), and
`TestTamperGuardExecutorHook` (test_fsm_executor.py, real `FSMExecutor.run()`
over a git-repo fixture exercising fail/allow/revert/no-guard/TDD-separation
scenarios).

Full suite: `python -m pytest scripts/tests/` — 17354 passed, 42 skipped, 1
pre-existing failure unrelated to this issue
(`test_no_prose_dependency_drift_in_repo`, confirmed present on a clean stash
of this branch — stale prose drift on ENH-2923/ENH-2935, not touched here).
`ruff check scripts/` and `python -m mypy scripts/little_loops/` both clean.

## Status

**Done** | Created: 2026-07-30 | Priority: P2

## Session Log
- `/ll:manage-issue improve` - 2026-07-31T00:00:00 - `a20a5180-113b-464f-8891-790652a6ff6a.jsonl`
- `/ll:ready-issue` - 2026-07-31T04:11:12 - `07fcd37a-c5df-40ab-809b-16bc468c2c76.jsonl`
- `/ll:confidence-check` - 2026-07-31T04:09:36 - `198cf520-6a84-4bcf-9e07-5be68cdc663f.jsonl`
- `/ll:decide-issue` - 2026-07-31T04:07:38 - `384f82bd-5d85-4834-b179-66c02cfc215b.jsonl`
- `/ll:refine-issue` - 2026-07-31T04:03:33 - `fff4a152-1c81-41b1-bea3-e3eeec642fe3.jsonl`
- `/ll:issue-size-review` - 2026-07-31T03:22:37 - `8a99a216-98a4-4273-8b35-65acee67e859.jsonl`
