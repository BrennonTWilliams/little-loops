---
id: ENH-3633
type: ENH
title: Wire opt-in advise_ready consult gate into refine-to-ready-issue done path
priority: P3
status: done
discovered_by: ll-issue-size-review
discovered_date: '2026-09-27'
completed_at: '2026-09-28T03:18:48Z'
parent: ENH-3626
relates_to:
- ENH-3590
- ENH-3623
decision_needed: false
confidence_score: 100
outcome_confidence: 82
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 25
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
`record_advisor_veto` contract, accepted fail-open on re-runs). The helper itself is ENH-3632
(done — `ll-issues advise-consult` exists). Wiring is intentionally kept with the loop change
(TDD mode): the loop-level tests here drive the wiring.

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
    (`preparation_policy.after_child` → `child_stop` → `apply` writes a `refine_failed` row,
    `preparation_policy.py:411-415, 1248-1256`). The run record carries
    `evidence_refs: [advise-<ID>.json]`, so a veto is distinguishable from any other
    `gate_unmet`.
  - recursive-refine lists a vetoed issue as **skipped** (`recursive-refine-skipped-vetoed.txt`
    + `recursive-refine-skipped.txt`), never as passed, and never size-reviews it.
- Helper failure of any kind is SKIPPED: treated as if the flag were off; the loop never waits
  on an advisor 429. A timeout of the consult state is also fail-open.
- One consult per issue per top-level run; a replayed verdict never bypasses a veto (helper's
  replay under a shared `run_dir`, `fsm/executor.py:1151-1152`).

## Proposed Solution

**Loop wiring in `refine-to-ready-issue.yaml`** (state names are proposals):

```
check_proof_before_done --on_no/on_error--> check_advise_ready_enabled   # was write_done_record
check_advise_ready_enabled --on_no/on_error--> write_done_record          # flag `advise_ready` empty
                           --on_yes--> run_advise_ready
run_advise_ready --PROCEED/SKIPPED--> write_done_record
                 --_ / _error (empty/unknown token, non-zero rc, timeout)--> write_done_record  # fail-open
                 --VETO--> record_advisor_veto
```

`run_advise_ready` calls `ll-issues advise-consult ${captured.issue_id.output:shell} --run-dir
${context.run_dir} --write-note` and routes with `evaluate: {type: classify}` + a `route:` table
with exactly the keys `PROCEED`, `SKIPPED`, `VETO`, `_`, `_error` (the `route_score_obligation`
shape, `refine-to-ready-issue.yaml:883-889`). The consult blocks up to
`advisor.timeout_seconds` (default 180s) plus host startup, so the state sets an explicit
`timeout:` (300) and a timeout must land on `write_done_record`, never `diagnose`/`failed`.

`check_advise_ready_enabled` checks only the flag: `action: "[ -n ${context.advise_ready:shell} ]"`
with `fragment: shell_exit` (the `:shell` idiom from `resolve_issue`, line 205; no MR-11
suppression marker). Replay lives in the helper, so no refine-to-ready-issue state reads a
marker; `record_advisor_veto` writes one only for recursive-refine (below).

**Why the helper, not the native `advisor_consult` evaluator** (`fsm/evaluators.py:1839`): the
helper persists the verdict per `run_dir` so a VETO sticks on replay, writes/removes the
`## Advisor Veto` note, and preflights `advisor.host` without spending budget (ENH-3632). The
native evaluator does none of these.

**`record_advisor_veto` contract** (mirror `record_gate_unmet`,
`refine-to-ready-issue.yaml:1188-1201`; Option B, reuse `gate_unmet`, no `RUN_RECORD_TOKENS`
change):
1. `printf 'gate_unmet' > ${context.run_dir}/refine-terminal-class` (autodev's MISSING fallback reads it).
2. Resolve the canonical ID. The helper keys its files by frontmatter `id`
   (`advise_consult.py:230`), but `captured.issue_id` is the raw `context.input` (`3633`,
   `ENH-3633` and `P3-ENH-3633` are all possible). Derive `CID` via `ll-issues show "$ID" --json`
   (fall back to `$ID` on failure).
3. `ll-issues run-record write "$ID" --run-dir ... --writer refine-to-ready-issue --legacy-class
   gate_unmet --evidence-refs "advise-$CID.json" || true`.
4. `printf '%s\n' "$ID" >> ${context.run_dir}/advisor-vetoed` — the raw captured ID, which
   under `context_passthrough` equals recursive-refine's `captured.input.output`.
5. Echo `[ADVISOR_VETO] <ID> - <recommendation>`, reading `recommendation` from
   `${context.run_dir}/advise-$CID.json` (the helper prints only the token). A missing or
   unreadable file echoes the line without a recommendation, never fails. Say the
   `## Advisor Veto` note the helper wrote is uncommitted in the working tree. Any embedded
   Python reads the path from the environment, not a literal (MR-11 widening, ENH-3342).
6. `next: failed`, `on_error: failed`.

**recursive-refine veto gate.** Without it, recursive-refine counts a vetoed issue as PASSED:
`run_refine` on_failure → `gate_recursion` → `detect_children` (no children) →
`size_review_snap` → `check_broke_down` → `recheck_scores` (`recursive-refine.yaml:499-540`),
and a veto only fires after the scores pass, so `recheck_scores` always appends the issue to
`recursive-refine-passed.txt`. Add:

```
run_refine --on_failure/on_error--> check_advisor_veto        # was gate_recursion
check_advisor_veto --on_yes--> skip_advisor_veto --next--> dequeue_next
                   --on_no/on_error--> gate_recursion          # fail-open to today's path
```

`check_advisor_veto`: `grep -qxF -- ${captured.input.output:shell} ${context.run_dir}/advisor-vetoed`
(`fragment: shell_exit`). `skip_advisor_veto` appends the ID to
`recursive-refine-skipped-vetoed.txt` and `recursive-refine-skipped.txt` (so the SKIPPED summary
count includes it) and echoes `Skipped: <ID> (advisor veto)`. It never runs
`run_size_review`: a veto is not a scope signal. The marker is harmless when the flag is off
(never written).

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
CONFIGURATION.md note). The budget file (`.ll/advisor-budget/<kind>-<value>.json`) never
expires, so once an issue has had 3 consults from any call site (including PROCEEDs and
`confidence_gate` consults), this gate is permanently SKIPPED for that issue. The
`LOOPS_REFERENCE.md` flag note says so.

## Program Design

### Types
- `advise_ready: str` — loop parameter/context flag; empty = off, non-empty = on

### Signatures
- `cmd_advise_consult(config: BRConfig, args: argparse.Namespace) -> int` — ENH-3632 helper; prints one `PROCEED`/`VETO`/`SKIPPED` token, always returns 0
- `check_advise_ready_enabled` / `run_advise_ready` / `record_advisor_veto` — new states in `refine-to-ready-issue.yaml`
- `check_advisor_veto` / `skip_advisor_veto` — new states in `recursive-refine.yaml`

### Call Path
`check_proof_before_done` -> `check_advise_ready_enabled` -> `run_advise_ready` -> `cmd_advise_consult`; VETO -> `record_advisor_veto` -> `failed`, otherwise `write_done_record`. In recursive-refine: `run_refine` (failed) -> `check_advisor_veto` -> `skip_advisor_veto` -> `dequeue_next`, otherwise `gate_recursion`

### Deviations

- 2026-09-27: the `record_advisor_veto` contract's step 1 (`printf 'gate_unmet' >
  ${context.run_dir}/refine-terminal-class`, "autodev's MISSING fallback reads it")
  was dropped. Between this issue's drafting and implementation,
  `feat(autodev): retire the refine-terminal-class preparation handshake sentinel`
  (same-day commit) removed that sentinel file entirely (ENH-3600) — the
  `--legacy-class gate_unmet` argument on the `run-record write` call (contract
  step 3) now carries the outcome on its own, with no separate sentinel writer/
  reader left in any loop (`test_autodev_loop.py::TestRetiredPreparationHandshakeMarkers`
  asserts no loop contains the string `refine-terminal-class`). `record_advisor_veto`
  never wrote that file; steps 2-6 are implemented as specified.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` — new states `check_advise_ready_enabled`, `run_advise_ready`, `record_advisor_veto`; retarget `check_proof_before_done` `on_no`/`on_error` (currently `write_done_record`, lines 931-932); bump `max_steps` 110 → 113 (BUG-3637 already bumped 100 → 110 same day — base off the current value, not 100), append a new history-comment entry after the existing BUG-3637 entry (~lines 136-142); update the header done-path diagram (line 52) to insert the advise hop after `check_proof_before_done`; add a new `parameters:` block (the loop has none today) with `advise_ready.default: ""`
- `scripts/little_loops/loops/recursive-refine.yaml` — `parameters.advise_ready` (already has `parameters:` and `context:`; pin it absent from `context:`); new states `check_advisor_veto` / `skip_advisor_veto`; retarget `run_refine` `on_failure`/`on_error` (currently `gate_recursion`) to `check_advisor_veto`
- `scripts/little_loops/loops/autodev.yaml` — `context: advise_ready: ""`; no `route_refine_outcome` change
- `scripts/little_loops/loops/prepare-issue.yaml` — none; a `failed` child terminal is already a `child_stop` (`preparation_policy.after_child`, `preparation_policy.py:411-415`), and `apply` forwards the `DEFERRED:gate_unmet` record and writes a `refine_failed` row (`:1248-1256`)

### Dependent Files
- `rn-build.yaml:582`, `sprint-build-and-validate.yaml:82,181` — call `recursive-refine` with `context_passthrough: true`; flag reaches it, and so does the shared `run_dir` holding the `advisor-vetoed` marker
- `issue-refinement.yaml:21` — calls `recursive-refine` with `with_:` and no passthrough; does **not** forward the flag. Unsupported in v1: run `recursive-refine` directly with `--context advise_ready=1`; document this
- `rn-remediate.yaml`, `auto-refine-and-implement.yaml`, `oracles/resolve-decision.yaml`, `rn-refine.yaml` — none invokes `refine-to-ready-issue`; no edit
- `scripts/little_loops/run_record.py` (`outcome_from_legacy_class`, `LEGACY_CLASSES`) — `gate_unmet` → deferred mapping the veto relies on; no vocabulary edit

### Documentation
- `docs/guides/LOOPS_REFERENCE.md` — "Score dispatch (ENH-3604)" `NONE` bullet omits `check_proof_before_done`; add it and the opt-in advise hop; also the `refine-to-ready-issue` row (~line 84); document the flag, that `advisor.host` is required, that the lifetime per-issue budget can make the gate permanently SKIPPED, that recursive-refine reports vetoed issues as skipped, and that `issue-refinement` does not forward the flag
- `docs/reference/DEFERRAL_CODES.md` — VETO → `gate_unmet` → deferred; add a row only if a new `--reason` code is recorded

### Tests
- `scripts/tests/test_builtin_loops.py` — chain-shape pins; `recursive-refine` `advise_ready` in `parameters:` and absent from `context:`; `run_advise_ready` default route → `write_done_record`; default-off; flag propagation parent → child (fails if a child `context:` literal shadows it); stub-`ll-issues advise-consult` execution for VETO/PROCEED/SKIPPED routing plus `_`/`_error`/timeout → `write_done_record`; `run_advise_ready` route keys are exactly `{PROCEED, SKIPPED, VETO, _, _error}` and it declares a `timeout:`; `record_advisor_veto` execution with a non-canonical input ID (`3633`) still finds `advise-<canonical>.json`, passes `--evidence-refs`, appends to `advisor-vetoed`, and echoes without a recommendation when the JSON is missing; recursive-refine `run_refine` `on_failure`/`on_error` → `check_advisor_veto`, and a stubbed vetoed ID lands in `recursive-refine-skipped-vetoed.txt` + `recursive-refine-skipped.txt`, never `recursive-refine-passed.txt`, with `run_size_review` unreached; update the `max_steps == 110  # BUG-3637: ...` assertion/comment at line 1872 to `113` with an appended `# ENH-3633: 110 -> 113 for advise_ready gate` comment (not the stale `100` this issue originally described); `skip_learning_gate` block (~lines 18023-18264) and registry tuples (~lines 20599-20763) as models, adding a `context.advise_ready` registry row
- `scripts/tests/test_autodev_decision_gate.py::TestChildDecisionInvariant.test_decision_gate_routes` — retarget `check_proof_before_done` `on_no`/`on_error` to `check_advise_ready_enabled`; re-verify `test_only_gate_write_done_record_and_class_writers_reach_done`
- `scripts/tests/test_autodev_proof_reentry.py` (~lines 207-208) — same edge assertions
- `scripts/tests/test_run_record.py` — add `record_advisor_veto` to `LEGACY_CLASS_STATES`, `TERMINAL_BEARING_STATES`, and the done-path gate sets
- `scripts/tests/test_fsm_topology.py` (~lines 291, 322) — read before editing; state-count asserts may cover refine-to-ready-issue or recursive-refine
- `scripts/tests/test_fsm_validation_shell_safety.py` (MR-11) / `test_fsm_validation_evaluator_rules.py` (MR-10) — new shell actions escape `$${...}` and don't swallow failures with exit 0
- Existing recursive-refine tests that pin `run_refine.on_failure == "gate_recursion"` — grep `test_builtin_loops.py` and retarget them

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-27 — based on codebase analysis:_

- **Header diagram correction**: `refine-to-ready-issue.yaml:52` already reads `NONE → check_decision_before_done (ENH-3610) → check_proof_before_done (ENH-3611) → write_done_record → done` — `check_proof_before_done` is not missing there (added by ENH-3611). The diagram still needs editing to insert the new `check_advise_ready_enabled` → `run_advise_ready` → (`record_advisor_veto` | `write_done_record`) hop, but not because a state is "missing".
- **Opt-in flag threading convention confirmed** (`skip_learning_gate` precedent): a top-level loop declares the flag `""` in `context:`; each delegating child threads it via `with: { flag: "${context.flag}" }`; tests pin three things per hop. Evidence: `test_builtin_loops.py:18250-18266` (`test_skip_flag_threads_through_sprint_chain`, chains sprint-refine-and-implement → auto-refine-and-implement → autodev), `:18117-18123` (`test_rn_remediate_threads_skip_flag`, pins the literal CLI flag string in the shell action and confirms a non-top-level loop keeps the flag out of `context:`), registry tuples at `:20599`, `:20739`, `:20763` (shape `(loop_file, "context.flag", issue_id)`).
- **`max_steps` bump convention**: a single hardcoded equality with an inline comment naming the issue and added state — `test_builtin_loops.py:1872` currently reads `assert data["max_steps"] == 110  # BUG-3637: 100 -> 110 for the claim-correction cycle` (BUG-3637 landed same-day, after this issue was drafted, and already moved the value off the 100 baseline this issue originally cited). The ENH-3633 bump should follow the same comment shape but base off 110: `assert data["max_steps"] == 113  # ENH-3633: 110 -> 113 for advise_ready gate`. <!-- ll-evidence-ok: quote is test_builtin_loops.py at the time of this 2026-09-27 research note (misattributed to BUG-3637 by proximity -- BUG-3637 is the cited reason for the prior bump, not the source file); this issue's own implementation has since bumped the line to 113, superseding the quoted 110 text -->
- **Stub `ll-issues` test precedent for the new loop states**: `test_autodev_proof_reentry.py:25-73`'s `_Stub` class (dispatches on `$1` subcommand, logs calls, exposes `.flag()`/`.put()`/`.calls()`, substitutes `${...}` via regex before invoking bash with `PATH` prefixed) is the closer model for stubbing `ll-issues advise-consult` than the lighter `test_builtin_loops.py:3228-3247` `_run_pre_action` (single-command `echo "$@"` stub). No existing stub targets `advise-consult` (the subcommand now exists via ENH-3632; the stub is still new work).
- **Done-path retargeting pins are duplicated, not shared**: `test_autodev_decision_gate.py:733-743` and `test_autodev_proof_reentry.py:200-210` each independently assert the same three `check_proof_before_done` edges (`on_yes`/`on_no`/`on_error`) rather than sharing one assertion helper — both need the retarget edit.
- **`LEGACY_CLASS_STATES`/`TERMINAL_BEARING_STATES` is a fixed enumeration, not a corpus scan** (`test_run_record.py:30-49`): `record_advisor_veto` must be added to both dicts/tuples plus the parametrized checks at `:528-531` and `:533-540`, or the new state's `run-record write --legacy-class gate_unmet` call goes unverified.
- **Sub-loop audit scope**: `TestSubLoopStateTimeoutAudit` (`test_builtin_loops.py:20873-20900`) audits only `timeout` on `loop:`-type states. Every new state here is a shell state, so the explicit `timeout:` on `run_advise_ready` is allowed (the stale Tests bullet claiming otherwise was removed).

## Implementation Steps

1. ~~Confirm ENH-3632 has landed~~ — confirmed (`ll-issues advise-consult --help` resolves).
2. Add `record_advisor_veto` (mirroring `record_gate_unmet`, plus canonical-ID resolution, `--evidence-refs`, the `advisor-vetoed` marker, and the recommendation echo) and register it in `test_run_record.py` sets.
3. Add `check_advise_ready_enabled` and `run_advise_ready` (explicit route keys + `timeout:`); retarget `check_proof_before_done`; bump `max_steps`; update header diagram and history comment.
4. Add `check_advisor_veto` / `skip_advisor_veto` to `recursive-refine.yaml`; retarget `run_refine` `on_failure`/`on_error`.
5. Declare the flag: `context:` in `autodev.yaml`; `parameters:` in `refine-to-ready-issue.yaml` and `recursive-refine.yaml`. Never in a child loop's `context:`.
6. Update the affected pins (`test_autodev_decision_gate.py`, `test_autodev_proof_reentry.py`, `test_builtin_loops.py`, `test_fsm_topology.py`) and add the new tests listed above.
7. `ll-loop validate` for every touched loop; update `LOOPS_REFERENCE.md`.
8. Manual smoke (optional; not an AC): this repo's `.ll/ll-config.json` sets `advisor.model` but no `advisor.host`, so the gate always SKIPs here. The acceptance criteria are verified with the stubbed helper; a live check needs `advisor.host` set via `.ll/ll.local.md`.

## Acceptance Criteria

- [x] With the flag empty (default), the done path reaches `write_done_record` without invoking the helper
- [x] A flag set on a parent (`autodev --context advise_ready=1` → prepare-issue → refine-to-ready-issue; `recursive-refine --context advise_ready=1` → refine-to-ready-issue) reaches the child gate as `1`; no child loop declares `advise_ready` in `context:`
- [x] With the flag set, a threshold-passing issue gets at most one consult per top-level run
- [x] A replayed VETO (second invocation, same ID, same `run_dir`) routes to `record_advisor_veto`, never `write_done_record`
- [x] VETO keeps the issue out of `done`, records `gate_unmet` (run-record outcome `deferred`; issue `status:` unchanged) with `evidence_refs` naming `advise-<ID>.json` via `record_advisor_veto`, and echoes `[ADVISOR_VETO]` with the recommendation (looked up by canonical ID, so a `3633`-style input works); autodev/prepare-issue handle it with no edits
- [x] `record_advisor_veto` records `gate_unmet` via `--legacy-class gate_unmet` on the run-record write (not a `refine-terminal-class` sentinel — that mechanism was retired by same-day ENH-3600; see Program Design → Deviations) and appends the ID to `advisor-vetoed`; the `## Advisor Veto` section is already in the issue file, and a later PROCEED removes it
- [x] recursive-refine lists a vetoed issue in `recursive-refine-skipped.txt` (and `-skipped-vetoed.txt`), never in `recursive-refine-passed.txt`, and never runs `run_size_review` for it
- [x] Any helper failure (empty/unknown token, non-zero rc, no route, state timeout) behaves exactly like the flag being off
- [x] `ll-loop validate` passes for every touched loop; existing callers' tests pass with only the retargeted edge assertions changed

## Impact

- **Priority**: P3 - opt-in quality improvement, not blocking
- **Effort**: Medium - three refine-to-ready-issue states, two recursive-refine states, flag pass-through across four loops, and several retargeted test pins; no new run-record class
- **Risk**: Low - off by default and fail-open; VETO reuses the existing `gate_unmet` path that callers already handle
- **Breaking Change**: No

## Scope Boundaries

- **In scope**: the done-path gate/consult/veto states, the recursive-refine veto skip, flag declaration and pass-through, `max_steps`, loop tests, `LOOPS_REFERENCE.md`.
- **Out of scope**: the helper (ENH-3632); a new run-record class or `RUN_RECORD_TOKENS` change (Option B); veto-handling edits in autodev/prepare-issue; generalizing recursive-refine's failure path to skip on every `gate_unmet` (today's pass-if-scores-pass fallback for other terminal classes is unchanged); cross-run veto persistence; forwarding the flag through `issue-refinement`; the go-no-go waiver veto (ENH-3590); enabling the consult by default.

## Resolution

- **Action**: improve
- **Completed**: 2026-09-28
- **Status**: Completed

### Changes Made
- `scripts/little_loops/loops/refine-to-ready-issue.yaml`: new `parameters.advise_ready` (default `""`); retargeted `check_proof_before_done.on_no`/`.on_error` to the new `check_advise_ready_enabled`; added `check_advise_ready_enabled` / `run_advise_ready` / `record_advisor_veto`; bumped `max_steps` 110 → 113; updated the header done-path diagram
- `scripts/little_loops/loops/recursive-refine.yaml`: new `parameters.advise_ready`; added `check_advisor_veto` / `skip_advisor_veto`; retargeted `run_refine.on_failure`/`.on_error` to `check_advisor_veto`
- `scripts/little_loops/loops/autodev.yaml`: `context.advise_ready: ""`
- `scripts/tests/test_advise_ready_gate.py` (new): stub-`ll-issues` coverage of the new states' routing and shell logic in both loops
- `scripts/tests/test_autodev_decision_gate.py`, `test_autodev_proof_reentry.py`, `test_builtin_loops.py`, `test_run_record.py`: retargeted the `check_proof_before_done` edge pins, `max_steps` pin, and `LEGACY_CLASS_STATES`/MR-11 marker allowlist for the new states
- `docs/guides/LOOPS_REFERENCE.md`: documented the flag, its fail-open behavior, the advisor budget interaction, and `issue-refinement`'s non-forwarding
- **Deviation**: dropped the `refine-terminal-class` sentinel write from `record_advisor_veto` — that mechanism was retired same-day by ENH-3600 (see the issue's Program Design → Deviations note)

## Status

**Open** | Created: 2026-09-27 | Priority: P3


## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-09-27_

**Readiness Score**: 70/100 → STOP — ADDRESS GAPS
**Outcome Confidence**: 75/100 → MODERATE

### Gaps to Address
- Resolved — ENH-3632 has landed; `ll-issues advise-consult` and `ll-issues advise-consult --help` now resolve, so the `stale_cli_flag` gap this note originally flagged no longer applies.
- Criterion 4 (Issue Well-Specified) was capped at 10/20 by that same `stale_cli_flag` gap; re-verify with `/ll:confidence-check` now that ENH-3632 has landed.
- Stale: the scores above (and `confidence_score`/`outcome_confidence` in frontmatter) predate the 2026-09-27 pre-implementation review, which added the recursive-refine veto skip, canonical-ID recommendation lookup, `--evidence-refs`, explicit route keys, and a consult timeout. Re-run `/ll:confidence-check`.

## Session Log
- `/ll:manage-issue` - 2026-09-28T03:17:53 - `e3ba6c17-e945-4049-81cb-561b43c91031.jsonl`
- `/ll:ready-issue` - 2026-09-28T02:47:21 - `ee876d51-704c-4cd3-ad43-f4694282e83a.jsonl`
- `/ll:confidence-check` - 2026-09-28T00:03:10 - `83cc6850-d1e9-4d1d-9048-aea88b662846.jsonl`
- `/ll:confidence-check` - 2026-09-27T05:50:16 - `80466a09-7d06-47fd-a22c-3c9fa3353587.jsonl`
- `/ll:refine-issue` - 2026-09-27T05:30:09 - `aae621bb-c067-4881-b3ce-b0e08bc3edb0.jsonl`
- `/ll:format-issue` - 2026-09-27T05:18:24 - `456ac708-7949-4003-8fee-84b53705067e.jsonl`
- `/ll:issue-size-review` - 2026-09-27T05:15:41 - `682a095a-efe4-40ac-8619-962c00f444e7.jsonl`
