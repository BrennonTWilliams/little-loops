---
id: BUG-2812
type: BUG
priority: P1
status: done
captured_at: '2026-07-25T22:08:07Z'
completed_at: '2026-07-26T02:18:21Z'
discovered_date: 2026-07-25
discovered_by: capture-issue
labels:
- fsm
- loops
- validator
- interpolation
confidence_score: 100
outcome_confidence: 93
score_complexity: 22
score_test_coverage: 24
score_ambiguity: 22
score_change_surface: 25
---

# BUG-2812: Three built-in loops crash on the sub-loop capture namespace (`captured.<var>` vs `captured.<state>.<var>`)

## Summary

Three built-in FSM loops — `integrate-sdk`, `adopt-third-party-api`, and
`proof-first-task` — reference sub-loop captures at the wrong namespace path and
abort the entire run with `InterpolationError`. Two of the three suppressed the
validator rule that would have caught it via `capture_reachability_ok: true`.
Empirically reproduced against the installed `little_loops.fsm.interpolation`
module (audit §1.6, `thoughts/builtin-loops-audit-2026-07-24.md`).

## Current Behavior

Executor facts (verified at source):

- A child loop's captures merge into the parent **under the parent state's
  name**: `self.captured[self.current_state] = child_executor.captured`
  (`fsm/executor.py:1008-1010`) — and only when the state sets
  `context_passthrough` / `with:`. They are **never flattened**.
- A sub-loop state's own `capture:` key stores the child's **event stream** as
  `{"output": <jsonl>, "exit_code": None}` (`fsm/executor.py:1000-1006`) — not
  the child's captures.
- A missing `${captured.*}` path with no `:default=` raises `InterpolationError`,
  which aborts the run as `terminated_by="error"` (`fsm/executor.py:788-795`).

Three loops get this wrong (all reproduced with `RAISES: Path ... not found in captured`):

| Loop | Site | Bug |
|---|---|---|
| `integrate-sdk` | `:145` — `PROVEN SURFACES: ${captured.targets.output}` | Real path is `captured.prove.targets.output`. Crashes the **success path of every run**, right after the oracle succeeds. The header comment (`:14-17`, attributed to ENH-2748) claims the sub-loop "injects" a flat `targets` capture — factually wrong per `executor.py:1008-1010` — and `capture_reachability_ok: true` (`:17`) silences the rule. (`:202-203` survive only because they carry `:default=not-reached`.) |
| `adopt-third-party-api` | `:81` and `:110` — `${captured.enumeration.output}` | Same defect on **both** post-oracle branches (success and partial); real path is `captured.prove.enumeration.output`. Suppressed by `capture_reachability_ok: true` at `:11`. Loop is unusable beyond enumeration. |
| `proof-first-task` | `:54` — `${captured.gate_result.extracted.output}` | `gate_result` is the `gate` state's own `capture:` — the event-stream dict with only `output`/`exit_code` keys — while assumption-firewall's `extracted` capture lands at `captured.gate.extracted`. Crashes the **`on_failure` branch the state exists to discriminate**; whenever the firewall reports failure the loop aborts `error`. Distinct from the known empty-task/`input_hash` bug. |

**Validator gap**: the capture-reachability rule checks only the *top-level*
captured variable name. `proof-first-task` passes it honestly (top-level
`gate_result` **is** captured); the other two suppressed it. Nested-path
correctness is checked nowhere.

## Expected Behavior

- All three loops resolve their sub-loop captures at the correct nested path and
  complete their success/failure branches without `InterpolationError`.
- The capture-reachability validator rule is nested-path-aware: it knows a
  sub-loop `capture:` value exposes only `output`/`exit_code`, and that merged
  child captures live under the parent **state name**.
- Every `capture_reachability_ok: true` suppression in the corpus carries a
  factually-true justifying comment.

## Root Cause

Author mental model treats sub-loop captures as flattened into the parent
namespace. The executor namespaces them under the invoking state's name
(`executor.py:1008-1010`), and the state's own `capture:` holds the child's
event stream rather than its captures (`:1000-1006`). The validator's
reachability rule only checks the top-level segment, so the nested-path error is
invisible — and where it would have fired, `capture_reachability_ok: true` was
set with an incorrect rationale.

The correct idiom already exists in-tree: `examples-miner.yaml:152` —
`${captured.run_optimizer.gradient.output}`.

## Proposed Solution

1. Correct the three references:
   - `integrate-sdk.yaml:145` → `${captured.prove.targets.output}`
   - `adopt-third-party-api.yaml:81,:110` → `${captured.prove.enumeration.output}`
   - `proof-first-task.yaml:54` → `${captured.gate.extracted.output}`
2. Remove/correct the false header comment at `integrate-sdk.yaml:14-17` and drop
   the now-unneeded `capture_reachability_ok: true` at `:17` and
   `adopt-third-party-api.yaml:11`.
3. Make the capture-reachability rule in `fsm/validation.py` nested-path-aware.
4. Audit all five loops carrying `capture_reachability_ok: true`
   (`adopt-third-party-api`, `autodev`, `examples-miner`, `goal-cluster`,
   `integrate-sdk`) — two of five were hiding real crashes.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- The five `capture_reachability_ok: true` justification comments are **not**
  all the same shape — only three (`adopt-third-party-api.yaml:8-11`,
  `integrate-sdk.yaml:14-17`, and `examples-miner.yaml:19-21`, the last of
  which is factually correct and should be kept) claim a sub-loop-namespace
  injection matching this bug's root cause. `autodev.yaml:21-25` justifies the
  flag on an unrelated static-reachability concern (a runtime marker-file gate
  bypassing `check_guard2_verdict`'s dominance analysis, not a captured-var
  namespace mismatch), and `goal-cluster.yaml:19-22` justifies it as a
  "capture injected by the parent loop via a fragment contract" — a different
  mechanism again. Item 4's audit should verify each flag's stated mechanism
  against the actual reference shape rather than assuming all five are the same
  sub-loop-namespace defect; `autodev.yaml`'s and `goal-cluster.yaml`'s flags
  may be legitimate and unrelated to this bug's fix.
- The two child loops whose inner `capture:` names are referenced without the
  parent state-name prefix: `scripts/little_loops/loops/oracles/enumerate-and-prove.yaml`
  (`capture: enumeration` at line 54, `capture: targets` at line 72) is shared
  by both `integrate-sdk.yaml`'s `prove` state and `adopt-third-party-api.yaml`'s
  `prove` state. `scripts/little_loops/loops/assumption-firewall.yaml` (captures
  include `extracted` at line 76) is used by `proof-first-task.yaml`'s `gate`
  state.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/integrate-sdk.yaml`
- `scripts/little_loops/loops/adopt-third-party-api.yaml`
- `scripts/little_loops/loops/proof-first-task.yaml`
- `scripts/little_loops/fsm/validation.py` (capture-reachability rule)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/fsm/executor.py:998-1010` (capture merge semantics — read-only reference)
- `scripts/little_loops/fsm/interpolation.py` (raise path)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/fsm/validation.py:156` — `_CAPTURED_REF_RE = re.compile(r"\$\{captured\.(\w+)")` conflates a sub-loop delegate state name with a captured-var name by only extracting the first path segment; this is the exact regex the nested-path-aware rewrite must fix. Shared helper `_unguarded_captured_refs()` (`:168-182`) and `_CAPTURED_REF_FULL_RE` (`:165`) also read only the first segment.
- `scripts/little_loops/cli/loop/config_cmds.py` — `cmd_validate()` calls `load_and_validate()`/`validate_fsm()`; renders this rule's WARNING/ERROR output for `ll-loop validate`.
- `scripts/little_loops/cli/loop/run.py` — `cmd_run()` calls `load_and_validate(raise_on_error=True)`; ERROR-severity findings from this rule block a run.
- `scripts/little_loops/cli/loop/info.py`, `scripts/little_loops/cli/loop/_helpers.py`, `scripts/little_loops/cli/loop/edit_routes.py`, `scripts/little_loops/cli/doctor.py` — secondary `load_and_validate()` consumers; unaffected in shape, just re-exercise the tightened rule.
- `scripts/little_loops/fsm/__init__.py` — re-exports `load_and_validate`, `validate_fsm`, `ValidationError` (public surface, no signature change expected).

### Similar Patterns
- `scripts/little_loops/loops/examples-miner.yaml:152` — correct idiom, use as the positive test fixture

### Tests
- `scripts/tests/test_builtin_loops.py` — add a nested-capture-path structural check
- New validator unit test: nested path against a sub-loop `capture:` (only `output`/`exit_code` valid)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_builtin_loops.py::TestBuiltinLoopFiles::test_all_validate_as_valid_fsm` (`:46-54`) — sweeps every built-in loop via ERROR-only assertions; this is the primary end-to-end regression gate and will newly fail on `integrate-sdk.yaml`/`adopt-third-party-api.yaml`/`proof-first-task.yaml` until their YAML fixes land (it passes today only because the flat-only regex can't see the bug).
- `scripts/tests/test_builtin_loops.py::TestValidatorWarningBudget` (`CATEGORY_PATTERNS["capture-ordering"]` ~`:11150`, `ALLOWLIST` ~`:11166`, `test_deterministic_warning_categories_do_not_regrow` ~`:11194`, `test_allowlist_entries_are_not_stale` ~`:11208`) — a **corpus-wide** ratchet over all `BUILTIN_LOOPS_DIR` loops, not just the 3 primary files. Making the rule nested-path-aware can flip classification (WARNING→no-finding, or vice versa) for *any* loop with a `${captured.<state>.<var>}`-shaped reference; must be re-run against the full tree before landing, not spot-checked. `autodev.yaml`/`goal-cluster.yaml` are shielded by their retained `capture_reachability_ok: true`, but unflagged loops are not.
- `scripts/tests/test_fsm_validation.py::TestCaptureReachabilityValidation::test_missing_capture_in_sub_loop_context_emits_warning` (~`:2978`), `::test_capture_from_sub_loop_skipped` (~`:2956`), `::test_captured_var_present_locally_no_warning_with_sub_loop` (~`:3008`) — encode the current first-path-segment-is-the-var semantics; none currently exercise the qualified `${captured.<state>.<var>.<field>}` form, so a nested-aware rewrite must preserve these (e.g. `typo_var` must stay a genuine undefined-var WARNING, not get reclassified as a valid nested ref) while adding new coverage for the qualified shape.
- Helper `_fsm_with_capture_and_ref` (`test_fsm_validation.py:2697-2740`) only builds the flat `${captured.<var>.output}` form — a new nested-path test cannot reuse it as-is; follow the manual `FSMLoop`-construction pattern used by `test_missing_capture_in_sub_loop_context_emits_warning` (~`:2978`) instead.
- Positive-fixture gap: no test currently asserts `examples-miner.yaml:152`'s `${captured.run_optimizer.gradient.output}` (the one already-correct nested reference in the corpus) — add a structural assertion following the `test_report_references_captured_report_path` pattern (`test_builtin_loops.py:734-737`) so the fix doesn't regress it.
- Secondary tests to re-run for regressions (no changes expected, but exercise the touched code paths): `scripts/tests/test_fsm_interpolation.py`, `scripts/tests/test_builtin_loop_interpolation.py`, `scripts/tests/test_fsm_executor.py`, `scripts/tests/test_ll_loop_commands.py`, `scripts/tests/test_cli_doctor.py`, `scripts/tests/test_cli_doctor_full.py`, `scripts/tests/test_goal_cluster.py`, `scripts/tests/test_autodev_decision_gate.py`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `scripts/tests/test_fsm_validation.py`, `class TestCaptureReachabilityValidation`
  (~line 2692-3400) is the existing test class to extend. Model a new
  nested-capture-path test after the sub-loop cases already there:
  `test_capture_from_sub_loop_skipped` (~line 2956),
  `test_missing_capture_in_sub_loop_context_emits_warning` (~line 2978),
  `test_captured_var_present_locally_no_warning_with_sub_loop` (~line 3008),
  and the suppression-flag tests `test_bypass_warning_suppressed_by_capture_reachability_ok`
  (~line 3335), `test_capture_reachability_ok_runs_via_validate_fsm` (~line 3351),
  `test_capture_reachability_ok_recognized_as_top_level_key` (~line 3368) — assert
  these still pass after the nested-path change. The helper
  `_fsm_with_capture_and_ref(...)` (~line 2697-2740) builds the minimal
  `start → capture_state → ref_state → done` FSM used by these tests; a new test
  would extend it to also inject a `loop=`-delegating state whose name is the
  first dotted segment of the reference.

### Documentation
- `docs/generalized-fsm-loop.md` — document the sub-loop capture namespace explicitly

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md:754` — full prose description of the capture-reachability rule ("dominance analysis... Sub-loop exception..."); does not mention `capture_reachability_ok` or the nested-path form, both need adding to keep this description accurate post-fix.
- `.claude/CLAUDE.md` MR table, `capture-reachability` row (~`:164`) — current description ("a `${captured.*}` reference whose capturing state doesn't dominate it... or references a never-captured var") doesn't mention nested-path validation; needs a clause distinguishing `${captured.<var>}` same-loop refs from `${captured.<subloop-state>.<var>}` sub-loop refs.
- `.issues/enhancements/P3-ENH-2748-suppress-flag-for-capture-reachability-warning.md` — its Motivation/Resolution sections assert all 5 `capture_reachability_ok: true` loops (including `integrate-sdk`, `adopt-third-party-api`) are legitimate suppressions. This issue reclassifies those two as actual bugs, not false positives — the ENH-2748 text becomes factually stale once this fix lands and should get a note/update.

### Configuration
- N/A

## Implementation Steps

1. Reproduce all three crashes (interpolation module, direct).
2. Fix the three YAML references; delete the two suppression flags.
3. Extend the capture-reachability rule to validate nested segments.
4. Re-run `ll-loop validate` across the corpus; confirm no new errors and that
   the previously-suppressed loops now pass honestly.
5. Add regression tests.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

6. Fix `_CAPTURED_REF_RE`/`_CAPTURED_REF_FULL_RE`/`_unguarded_captured_refs()` (`fsm/validation.py:156-182`) to extract nested paths instead of only the first segment.
7. Re-run `scripts/tests/test_builtin_loops.py::TestValidatorWarningBudget` against the **full** loop corpus (not just the 3 primary files) — confirm no unallowlisted `capture-ordering` findings appear or disappear elsewhere.
8. Add a positive-fixture assertion for `examples-miner.yaml:152`'s already-correct nested reference, following `test_report_references_captured_report_path` (`test_builtin_loops.py:734-737`).
9. Update `docs/reference/CLI.md:754` and the `.claude/CLAUDE.md` MR table `capture-reachability` row (~`:164`) to describe nested-path handling and the `capture_reachability_ok` flag.
10. Note the now-stale claim in `.issues/enhancements/P3-ENH-2748-suppress-flag-for-capture-reachability-warning.md` that all 5 flagged loops are legitimate suppressions.

## Impact

- **Severity**: High — `integrate-sdk` and `adopt-third-party-api` crash on
  *every* successful run; `proof-first-task` (79 recorded runs) crashes on the
  discriminating failure branch.
- Two loops are effectively non-functional as shipped.
- The validator gap means the class can recur silently.

## Related Key Documentation

| Document | Relevance |
|---|---|
| `thoughts/builtin-loops-audit-2026-07-24.md` §1.6, §3.2, rec #1 | Source finding, reproduction trail |
| `docs/generalized-fsm-loop.md` | Authoring conventions to update |

## Steps to Reproduce

1. `ll-loop run integrate-sdk "<some sdk>"` — the run aborts
   `terminated_by="error"` immediately after the `prove` oracle succeeds.
2. Or reproduce directly against the interpolation module: build a `captured`
   dict shaped like the executor's post-sub-loop merge
   (`{"prove": {"targets": {...}}}`) and interpolate
   `${captured.targets.output}` → `InterpolationError: Path ... not found in
   captured`.
3. `adopt-third-party-api`: same, on both post-oracle branches (`:81`, `:110`).
4. `proof-first-task`: drive the `gate` state to an assumption-firewall
   *failure* so the `on_failure` branch at `:54` is taken → abort instead of the
   intended blocked/run_impl discrimination.

## Resolution

Fixed all three YAML references and made the capture-reachability rule
nested-path-aware:

- `integrate-sdk.yaml`: `scaffold_integration` and `diagnose_and_block` now
  reference `${captured.prove.targets.output}` / `${captured.prove.enumeration.output}`
  (the sub-loop-delegating `prove` state's own name); removed the false
  ENH-2748 header comment and `capture_reachability_ok: true`.
- `adopt-third-party-api.yaml`: `build_playbook` and `build_playbook_partial`
  now reference `${captured.prove.enumeration.output}`; removed the
  `capture_reachability_ok: true` suppression.
- `proof-first-task.yaml`: `check_gate_blocked` now references
  `${captured.gate.extracted.output}` (the `gate` state's name), not
  `${captured.gate_result.extracted.output}` (the state's own event-stream
  `capture:` name, which only exposes `output`/`exit_code`).
- `fsm/validation.py`'s `_validate_capture_reachability` (and its
  `_unguarded_captured_refs` helper) now parse the full dotted `${captured.*}`
  path instead of only the first segment. It distinguishes the correct
  `${captured.<sub_loop_state_name>.<var>...}` form (validated against
  dominance of the delegating state) from an invalid reference to a
  sub-loop-delegating state's own `capture:` name plus a nested field beyond
  `.output`/`.exit_code` (now an ERROR, since that name only ever resolves to
  the child's event-stream dict).
- Audited all 5 `capture_reachability_ok: true` loops per the plan's item 4:
  `autodev.yaml` and `goal-cluster.yaml` justify the flag on unrelated,
  legitimate mechanisms and keep it; `examples-miner.yaml`'s flag was already
  the correct nested form and keeps it too (still needed — its
  `run_optimizer` sub-loop capture isn't otherwise locally captured).
- Added regression tests: 4 new `TestCaptureReachabilityValidation` unit
  tests (qualified sub-loop-state reference, invalid own-capture-name nested
  field as ERROR, valid own-capture `.output` field), structural assertions
  in `test_builtin_loops.py` for all three fixed loops plus a positive
  fixture for `examples-miner.yaml`'s already-correct reference, and updated
  `docs/reference/CLI.md` / `.claude/CLAUDE.md`'s capture-reachability rows.
  Noted the now-stale claim in ENH-2748 that all 5 suppressions were
  legitimate false positives.

Verified: `python -m pytest scripts/tests/` (16301 passed, 38 skipped),
`ruff check scripts/` clean, `python -m mypy scripts/little_loops/` clean for
the touched files (pre-existing `ruamel` stub-typing noise elsewhere,
unrelated). `ll-loop validate` confirms all three fixed loops are valid with
no capture-reachability findings.

## Session Log
- `/ll:manage-issue` - 2026-07-26T02:17:38Z - see current session
- `/ll:wire-issue` - 2026-07-26T02:03:18 - `dce6ca0e-5663-4c86-a2e2-fdf0eaf1f64f.jsonl`
- `/ll:refine-issue` - 2026-07-26T01:57:48 - `5215e850-5686-492d-8826-81f41a85494a.jsonl`
- `/ll:capture-issue` - 2026-07-25T22:08:07Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8a36a68e-d365-4ea1-9394-a9e5904b5739.jsonl`

---

## Status

- **Current**: open
