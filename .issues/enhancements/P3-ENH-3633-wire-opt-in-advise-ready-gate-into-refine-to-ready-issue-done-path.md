---
id: ENH-3633
type: ENH
title: Wire opt-in advise_ready consult gate into refine-to-ready-issue done path
priority: P3
status: open
discovered_by: ll-issue-size-review
discovered_date: '2026-09-27'
parent: ENH-3626
blocked_by:
- ENH-3632
relates_to:
- ENH-3590
- ENH-3623
decision_needed: false
confidence_score: 70
outcome_confidence: 75
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 18
---

# ENH-3633: Wire opt-in advise_ready consult gate into refine-to-ready-issue done path

## Summary

Add an opt-in `advise_ready` gate as the last step on `refine-to-ready-issue`'s done path,
between `check_proof_before_done` and `write_done_record`, calling the ENH-3632 helper
(`ll-issues advise-consult`). Every caller gets it: `prepare-issue` (and so autodev) and
`recursive-refine`, the only two loops that invoke `refine-to-ready-issue`
(`prepare-issue.yaml:38`, `recursive-refine.yaml:237`). The consult is veto-only and fails open.

## Parent Issue

Decomposed from ENH-3626: Add opt-in second-model advise readiness consult to refine-to-ready.
Covers parent Implementation Steps 3-6 (Proposed Solution: "Loop wiring", "Flag declaration",
`record_advisor_veto` contract, accepted fail-open on re-runs). The helper itself is ENH-3632;
this issue is blocked by it. Wiring is intentionally kept with the loop change (TDD mode): the
loop-level tests here drive the wiring.

## Current Behavior

`refine-to-ready-issue.yaml` declares an issue ready on deterministic gates only:
`confidence_check` → `route_score_obligation` → `check_decision_before_done` →
`check_proof_before_done` → `write_done_record` → `done`. No state consults a second model
before the issue is handed back as ready.

## Expected Behavior

- Flag `advise_ready` empty (default): done path unchanged, no consult.
- Flag set (`ll-loop run refine-to-ready-issue --context advise_ready=1`, or inherited from
  autodev → prepare-issue, or recursive-refine): an issue that cleared every deterministic gate
  gets one consult before `write_done_record`.
  - **PROCEED / SKIPPED** → `write_done_record` → `done`.
  - **VETO** → `record_advisor_veto` writes `gate_unmet` (run-record outcome `deferred`; issue
    `status:` stays `open`, nothing calls `set-status deferred`), echoes `[ADVISOR_VETO] <ID> -
    <recommendation>`, then `failed`. autodev ledgers it as a child stop
    (`ledger_child_stop` / `skip_inflight`).
- Helper failure of any kind is SKIPPED: treated as if the flag were off; the loop never waits
  on an advisor 429.
- One consult per issue per top-level run; a replayed verdict never bypasses a veto (helper's
  replay under a shared `run_dir`, `fsm/executor.py:1151-1152`).

## Proposed Solution

**Loop wiring in `refine-to-ready-issue.yaml`** (state names are proposals):

```
check_proof_before_done --on_no/on_error--> check_advise_ready_enabled   # was write_done_record
check_advise_ready_enabled --on_no/on_error--> write_done_record          # flag `advise_ready` empty
                           --on_yes--> run_advise_ready
run_advise_ready --PROCEED/SKIPPED--> write_done_record
                 --default (empty/unknown token, no_route, error)--> write_done_record  # fail-open
                 --VETO--> record_advisor_veto
```

`run_advise_ready` calls `ll-issues advise-consult <ID> --run-dir ${context.run_dir}
--write-note` and routes with `classify` + a `route:` table (the `next-obligation --format
token` shape). The gate checks only the flag (`[ -n ${context.advise_ready} ]`, escaped per
MR-11). Replay lives in the helper, so no loop state reads or writes a marker.

**`record_advisor_veto` contract** (mirror `record_gate_unmet`,
`refine-to-ready-issue.yaml:1136-1148`; Option B, reuse `gate_unmet`, no `RUN_RECORD_TOKENS`
change):
1. `printf 'gate_unmet' > ${context.run_dir}/refine-terminal-class` (autodev's MISSING fallback reads it).
2. `ll-issues run-record write <ID> --run-dir ... --writer refine-to-ready-issue --legacy-class gate_unmet || true`.
3. Echo `[ADVISOR_VETO] <ID> - <recommendation>`; say the `## Advisor Veto` note the helper wrote
   is uncommitted in the working tree.
4. `next: failed`, `on_error: failed`.

Dirty-tree safety (resolved in review): autodev snapshots the pre-existing dirty set into
`$QDIR/<ID>.base-dirty` before each `ll-auto` run (`autodev.yaml:1228-1229`) and subtracts it
(`autodev.yaml:1305-1309`); issue-file commits stage explicit paths only (`issue_lifecycle.py:641`,
`parallel/orchestrator.py:1354,2027`); `rn-refine.yaml:615` (`git add -A`) never reaches this gate.

**Flag declaration: only top-level loops put it in `context:`.** With `context_passthrough` the
executor merges `{**parent, **captured, **child_fsm.context}` (`fsm/executor.py:1160`), so a
child's `context:` literal overrides the inherited value (BUG-2767 trap). Therefore:
- `autodev.yaml`: `context: advise_ready: ""` (same idiom as `skip_learning_gate: ""`).
- `refine-to-ready-issue.yaml`, `recursive-refine.yaml`: `parameters: advise_ready: {type:
  string, required: false, default: ""}` only, never in `context:`. `seed_parameter_defaults`
  (BUG-3425) uses `setdefault`; `--context` on a `parameters:`-only key works (`cli/loop/run.py:198`
  seeds defaults before `--context`; sub-loop path seeds after the passthrough merge,
  `fsm/executor.py:1172`).
- `prepare-issue.yaml`: nothing (no `context:` block, passes everything through).

**Accepted for v1:** fail-open on re-runs (a vetoed issue stays `open`; repeated runs can wait out
a veto once `max_consults_per_task=3` is spent → `budget_exhausted` → SKIPPED). Budget contention
with `pre_done` / `confidence_gate` consults is documented next to the flag (in ENH-3632's
CONFIGURATION.md note).

## Program Design

### Types
- `advise_ready: str` — loop parameter/context flag; empty = off, non-empty = on

### Signatures
- `cmd_advise_consult(config: BRConfig, args: argparse.Namespace) -> int` — ENH-3632 helper; prints one `PROCEED`/`VETO`/`SKIPPED` token, always returns 0
- `check_advise_ready_enabled` / `run_advise_ready` / `record_advisor_veto` — new states in `refine-to-ready-issue.yaml`

### Call Path
`check_proof_before_done` -> `check_advise_ready_enabled` -> `run_advise_ready` -> `cmd_advise_consult`; VETO -> `record_advisor_veto` -> `failed`, otherwise `write_done_record`

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` — new states `check_advise_ready_enabled`, `run_advise_ready`, `record_advisor_veto`; retarget `check_proof_before_done` `on_no`/`on_error`; bump `max_steps` 100 → 103, record in the history comment (~lines 120-132); update header done-path diagram (~line 48, also add the missing `check_proof_before_done`); declare `parameters.advise_ready.default: ""`
  > ⚠ Superseded — check_proof_before_done already in diagram, not missing
- `scripts/little_loops/loops/recursive-refine.yaml` — `parameters.advise_ready` only (already has `parameters:` and `context:`; pin it absent from `context:`)
- `scripts/little_loops/loops/autodev.yaml` — `context: advise_ready: ""`; no `route_refine_outcome` change
- `scripts/little_loops/loops/prepare-issue.yaml` — none; `gate_unmet` → deferred already handled by `forward_stop`

### Dependent Files
- `rn-build.yaml:582`, `sprint-build-and-validate.yaml:82,181` — call `recursive-refine` with `context_passthrough: true`; flag reaches it
- `issue-refinement.yaml:21` — calls `recursive-refine` with `with_:` and no passthrough; does **not** forward the flag. Unsupported in v1: run `recursive-refine` directly with `--context advise_ready=1`; document this
- `rn-remediate.yaml`, `auto-refine-and-implement.yaml`, `oracles/resolve-decision.yaml`, `rn-refine.yaml` — none invokes `refine-to-ready-issue`; no edit
- `scripts/little_loops/run_record.py` (`outcome_from_legacy_class`, `LEGACY_CLASSES`) — `gate_unmet` → deferred mapping the veto relies on; no vocabulary edit

### Documentation
- `docs/guides/LOOPS_REFERENCE.md` — "Score dispatch (ENH-3604)" `NONE` bullet omits `check_proof_before_done`; add it and the opt-in advise hop; also the `refine-to-ready-issue` row (~line 84); document the flag and that `advisor.host` is required
- `docs/reference/DEFERRAL_CODES.md` — VETO → `gate_unmet` → deferred; add a row only if a new `--reason` code is recorded

### Tests
- `scripts/tests/test_builtin_loops.py` — chain-shape pins; `recursive-refine` `advise_ready` in `parameters:` and absent from `context:`; `run_advise_ready` default route → `write_done_record`; default-off; flag propagation parent → child (fails if a child `context:` literal shadows it); stub-`ll-issues advise-consult` execution for VETO/PROCEED/SKIPPED routing; update `max_steps == 100` assertion (~line 1872); `skip_learning_gate` block (~lines 18023-18264) and registry tuples (~lines 20599-20763) as models, adding a `context.advise_ready` registry row
- `scripts/tests/test_autodev_decision_gate.py::TestChildDecisionInvariant.test_decision_gate_routes` — retarget `check_proof_before_done` `on_no`/`on_error` to `check_advise_ready_enabled`; re-verify `test_only_gate_write_done_record_and_class_writers_reach_done`
- `scripts/tests/test_autodev_proof_reentry.py` (~lines 207-208) — same edge assertions
- `scripts/tests/test_run_record.py` — add `record_advisor_veto` to `LEGACY_CLASS_STATES`, `TERMINAL_BEARING_STATES`, and the done-path gate sets
- `scripts/tests/test_fsm_topology.py` (~lines 291, 322) — read before editing; state-count asserts may cover this loop
- `scripts/tests/test_fsm_validation_shell_safety.py` (MR-11) / `test_fsm_validation_evaluator_rules.py` (MR-10) — new shell actions escape `$${...}` and don't swallow failures with exit 0
- Sub-loop states must not carry `on_no` or `timeout` (`TestSubLoopStateTimeoutAudit`)

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-27 — based on codebase analysis:_

- **Header diagram correction**: `refine-to-ready-issue.yaml:48` already reads `NONE → check_decision_before_done (ENH-3610) → check_proof_before_done (ENH-3611) → write_done_record → done` — `check_proof_before_done` is not missing there (added by ENH-3611). The diagram still needs editing to insert the new `check_advise_ready_enabled` → `run_advise_ready` → (`record_advisor_veto` | `write_done_record`) hop, but not because a state is "missing" — see the marker on the Files to Modify bullet above.
- **Opt-in flag threading convention confirmed** (`skip_learning_gate` precedent): a top-level loop declares the flag `""` in `context:`; each delegating child threads it via `with: { flag: "${context.flag}" }`; tests pin three things per hop. Evidence: `test_builtin_loops.py:18250-18266` (`test_skip_flag_threads_through_sprint_chain`, chains sprint-refine-and-implement → auto-refine-and-implement → autodev), `:18117-18123` (`test_rn_remediate_threads_skip_flag`, pins the literal CLI flag string in the shell action and confirms a non-top-level loop keeps the flag out of `context:`), registry tuples at `:20599`, `:20739`, `:20763` (shape `(loop_file, "context.flag", issue_id)`).
- **`max_steps` bump convention**: a single hardcoded equality with an inline comment naming the issue and added state — `test_builtin_loops.py:1872`: `assert data["max_steps"] == 100  # ENH-3611: 90 -> 100 for check_proof_before_done`. The ENH-3633 bump should follow the same comment shape (`# ENH-3633: 100 -> 103 for advise_ready gate`).
- **Stub `ll-issues` test precedent for the new loop states**: `test_autodev_proof_reentry.py:25-73`'s `_Stub` class (dispatches on `$1` subcommand, logs calls, exposes `.flag()`/`.put()`/`.calls()`, substitutes `${...}` via regex before invoking bash with `PATH` prefixed) is the closer model for stubbing `ll-issues advise-consult` than the lighter `test_builtin_loops.py:3228-3247` `_run_pre_action` (single-command `echo "$@"` stub). No existing stub targets `advise-consult` — it doesn't exist yet.
- **Done-path retargeting pins are duplicated, not shared**: `test_autodev_decision_gate.py:733-743` and `test_autodev_proof_reentry.py:200-210` each independently assert the same three `check_proof_before_done` edges (`on_yes`/`on_no`/`on_error`) rather than sharing one assertion helper — both need the retarget edit.
- **`LEGACY_CLASS_STATES`/`TERMINAL_BEARING_STATES` is a fixed enumeration, not a corpus scan** (`test_run_record.py:30-49`): `record_advisor_veto` must be added to both dicts/tuples plus the parametrized checks at `:528-531` and `:533-540`, or the new state's `run-record write --legacy-class gate_unmet` call goes unverified.
- **Correction to the Tests section's sub-loop claim**: `TestSubLoopStateTimeoutAudit` (`test_builtin_loops.py:20873-20900`) audits only `timeout` on `loop:`-type states, not `on_no` — no test or validator enforces an `on_no` prohibition on sub-loop states. The new states here are shell (`ll-issues advise-consult`), not `loop:`-type, so this doesn't block ENH-3633, but the Tests bullet overstates existing coverage.

## Implementation Steps

1. Confirm ENH-3632 has landed (`ll-issues advise-consult --help`).
2. Add `record_advisor_veto` (mirroring `record_gate_unmet`) and register it in `test_run_record.py` sets.
3. Add `check_advise_ready_enabled` and `run_advise_ready`; retarget `check_proof_before_done`; bump `max_steps`; update header diagram and history comment.
4. Declare the flag: `context:` in `autodev.yaml`; `parameters:` in `refine-to-ready-issue.yaml` and `recursive-refine.yaml`. Never in a child loop's `context:`.
5. Update the affected pins (`test_autodev_decision_gate.py`, `test_autodev_proof_reentry.py`, `test_builtin_loops.py`, `test_fsm_topology.py`) and add the new tests listed above.
6. `ll-loop validate` for every touched loop; update `LOOPS_REFERENCE.md`.

## Acceptance Criteria

- [ ] With the flag empty (default), the done path reaches `write_done_record` without invoking the helper
- [ ] A flag set on a parent (`autodev --context advise_ready=1` → prepare-issue → refine-to-ready-issue; `recursive-refine --context advise_ready=1` → refine-to-ready-issue) reaches the child gate as `1`; no child loop declares `advise_ready` in `context:`
- [ ] With the flag set, a threshold-passing issue gets at most one consult per top-level run
- [ ] A replayed VETO (second invocation, same ID, same `run_dir`) routes to `record_advisor_veto`, never `write_done_record`
- [ ] VETO keeps the issue out of `done`, records `gate_unmet` (run-record outcome `deferred`; issue `status:` unchanged) via `record_advisor_veto`, echoes `[ADVISOR_VETO]` with the recommendation, and existing callers handle it with no edits
- [ ] `record_advisor_veto` writes `refine-terminal-class` = `gate_unmet`; the `## Advisor Veto` section is already in the issue file, and a later PROCEED removes it
- [ ] Any helper failure (empty/unknown token, non-zero rc, no route) behaves exactly like the flag being off
- [ ] `ll-loop validate` passes for every touched loop; existing callers' tests pass with only the retargeted edge assertions changed

## Impact

- **Priority**: P3 - opt-in quality improvement, not blocking
- **Effort**: Medium - three loop states, flag pass-through across four loops, and several retargeted test pins; no new run-record class
- **Risk**: Low - off by default and fail-open; VETO reuses the existing `gate_unmet` path that callers already handle
- **Breaking Change**: No

## Scope Boundaries

- **In scope**: the done-path gate/consult/veto states, flag declaration and pass-through, `max_steps`, loop tests, `LOOPS_REFERENCE.md`.
- **Out of scope**: the helper (ENH-3632); a new run-record class or `RUN_RECORD_TOKENS` change (Option B); caller edits for veto handling; cross-run veto persistence; forwarding the flag through `issue-refinement`; the go-no-go waiver veto (ENH-3590); enabling the consult by default.

## Status

**Open** | Created: 2026-09-27 | Priority: P3


## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-09-27_

**Readiness Score**: 70/100 → STOP — ADDRESS GAPS
**Outcome Confidence**: 75/100 → MODERATE

### Gaps to Address
- Blocked by ENH-3632 (open) — the `ll-issues advise-consult` helper this issue wires in does not exist yet; format-check confirms both `ll-issues advise-consult` and `ll-issues advise-consult --help` as `stale_cli_flag` (no such subcommand). Land ENH-3632 first.
- Criterion 4 (Issue Well-Specified) capped at 10/20 by the same `stale_cli_flag` gap — expected given the blocking dependency, not a specification defect; re-verify once ENH-3632 lands and the subcommand resolves.

## Session Log
- `/ll:confidence-check` - 2026-09-27T05:50:16 - `80466a09-7d06-47fd-a22c-3c9fa3353587.jsonl`
- `/ll:refine-issue` - 2026-09-27T05:30:09 - `aae621bb-c067-4881-b3ce-b0e08bc3edb0.jsonl`
- `/ll:format-issue` - 2026-09-27T05:18:24 - `456ac708-7949-4003-8fee-84b53705067e.jsonl`
- `/ll:issue-size-review` - 2026-09-27T05:15:41 - `682a095a-efe4-40ac-8619-962c00f444e7.jsonl`
