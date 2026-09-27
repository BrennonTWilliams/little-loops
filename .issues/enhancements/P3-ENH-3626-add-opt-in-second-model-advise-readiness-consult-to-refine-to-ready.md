---
id: ENH-3626
type: ENH
title: Add opt-in second-model advise readiness consult to refine-to-ready
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-27'
captured_at: '2026-09-27T01:56:15Z'
relates_to:
- ENH-3590
- ENH-3623
blocks:
- ENH-3590
decision_needed: false
---

# ENH-3626: Add opt-in second-model advise readiness consult to refine-to-ready

## Summary

Add an opt-in `ll-advise` (second-model) readiness consult as the last gate on
`refine-to-ready-issue`'s done path, between `check_proof_before_done` and
`write_done_record`. Every caller gets it: `prepare-issue` (and so autodev),
`recursive-refine`, and rn-refine. The consult is veto-only and fails open. Scope also
includes a shared Python helper that runs `ll-advise`, persists the payload, and maps it
to PROCEED/VETO/SKIPPED, so ENH-3590 reuses it instead of carrying a second copy.

## Current Behavior

`refine-to-ready-issue.yaml` declares an issue ready on deterministic gates only:
`confidence_check` (the `oracles/verify-confidence-scores` sub-loop) →
`route_score_obligation` (`ll-issues next-obligation` against the readiness/outcome
thresholds) → `check_decision_before_done` → `check_proof_before_done` →
`write_done_record` → `done`. The confidence scores come from the default model; no
state consults a stronger or different model before the issue is handed back as ready.

## Expected Behavior

- With the context flag empty (the default), the done path is unchanged and `ll-advise`
  is never invoked.
- With the flag set, an issue that has cleared every deterministic gate gets one
  `ll-advise --json` consult before `write_done_record`.
  - **PROCEED** or **SKIPPED** → `write_done_record` → `done`, as today.
  - **VETO** → the issue does not reach `done`. `record_advisor_veto` writes the existing
    `gate_unmet` legacy class (→ `deferred`, per the Option B decision) and echoes an
    `[ADVISOR_VETO]` line carrying the advisor's `recommendation`; the full payload stays in
    `<run_dir>/advise-<ID>.json`.
- Any `ll-advise` failure (any non-zero exit, including budget exhaustion and an unreadable
  `--context-file`; advisor rate limit; advisor auth failure; unreadable output) is SKIPPED:
  logged, then treated exactly as if the flag were off. The loop never waits on a 429 retry
  for the advisor.
- **One consult per run.** The done chain can be re-entered after `run_spike` or a decide
  re-score; a per-run marker (`${context.run_dir}/advise-consulted-<ID>`) makes the gate skip
  a second consult, so an issue is never consulted twice in one run. **Scope note:** a child
  loop inherits the parent's `run_dir` (`fsm/executor.py:1151-1152`, `setdefault`), so under
  `recursive-refine`/`prepare-issue` the marker lives in the parent's run directory and the
  guarantee is "once per issue per top-level run". This is intended (the ID-keyed marker never
  crosses issues) and is pinned by a test.

## Motivation

ENH-3590 adds a second-model veto only where go-no-go waives the outcome threshold. That
covers issues that *fail* the threshold and get let through anyway; those issues never
reach refine-to-ready's done edge (a sub-threshold outcome routes to
`check_decision_needed`, not `done`). Issues that *pass* the thresholds get no
second-model review at all. This issue covers that complementary, common path. The two
are not redundant.

## Proposed Solution

**Shared helper (land first).** A Python entry point, `ll-issues advise-consult <ID> --run-dir <dir>`, that:

1. Runs `ll-advise --signal refine_ready --question <q> --context-file <issue> --json` with
   `LL_ISSUE_ID=<ID>` so it bills the per-issue budget bucket, under a hard subprocess
   timeout (default 120s, `--timeout` override). A timeout kills the child and maps to
   SKIPPED (`rc` file records `timeout`).
   **Question text (pinned; the mapping depends on it):** _"Is this issue ready to implement
   as written? Begin your answer with exactly one word, PROCEED or VETO, then give the
   reason. VETO only for a concrete defect that would make implementation fail or be
   wasted; otherwise PROCEED."_ ENH-3590 passes its own signal/question via `--signal` /
   `--question` overrides.
2. Writes `<run_dir>/advise-<ID>.{json,err,rc}`.
3. Maps the result to PROCEED/VETO/SKIPPED: missing or non-zero rc, or missing or
   unparseable JSON → SKIPPED (log the skip reason; emit a WARNING line for
   `not_configured`; log `timeout`); the leading word of `recommendation`, uppercased with punctuation
   stripped, equal to `VETO` → VETO; anything else → PROCEED. `confidence` and `dissent`
   are logged but never routed on.
4. Always exits 0 and prints a single routing token (`PROCEED`/`VETO`/`SKIPPED`) that the
   loop routes with `classify` + a `route:` table (the `next-obligation --format token`
   shape). It never propagates the advisor's exit code, so executor-side 429 interception
   (which fires only on non-zero exit) cannot stall the loop. The loop never parses the
   advisor's own stdout.

ENH-3590's consult (a policy step once ENH-3623 lands) calls the same helper with its own
`--signal`/`--question`.

**Loop wiring in `refine-to-ready-issue.yaml`:**

```
check_proof_before_done --on_no/on_error--> check_advise_ready_enabled   # was write_done_record
check_advise_ready_enabled --on_no/on_error--> write_done_record          # flag `advise_ready` empty, or already consulted this run
                           --on_yes--> run_advise_ready   # touches advise-consulted-<ID> first
run_advise_ready --PROCEED/SKIPPED--> write_done_record
                 --VETO--> record_advisor_veto  # writes gate_unmet, echoes [ADVISOR_VETO], next: failed
```

State names are proposals. The flag is the empty-string context key `advise_ready` (autodev's
`skip_learning_gate: ""` idiom, gated with `[ -n ... ]`), declared in every loop that
passes it down.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-27 — based on codebase analysis:_

**Corrections to the premises above (from this pass's research):**
- Only 5 of the 7 skip reasons are reachable through `ll-advise`: `manual=True` makes `disabled` and `trigger_not_allowed` unreachable. Exit 2 also covers an unreadable `--context-file` (not a skip reason) and argparse errors. The helper must treat every non-zero rc as SKIPPED regardless.
- The per-issue budget bucket is billed only if `LL_ISSUE_ID` is exported: no loop YAML sets it (only `issue_manager.py` and `parallel/worker_pool.py` do). Without it, `resolve_task_key()` falls to `LL_LOOP_RUN_ID` (kind `loop_run`), so the helper itself must set `LL_ISSUE_ID` on the child process for the "shared with `confidence_gate`/`pre_done`" budget claim to hold.
- "No stdout parsing (MR-1)" mislabels the rule: MR-1 concerns pairing LLM evaluators with non-LLM ones and permits `classify`. Existing routing helpers use two shapes — exit-code (`check-flag`, `check-verify-verdict`, via `shell_exit`) and stdout token with exit 0 (`next-obligation --format token`, `run-record read --format token`, via `classify` + `route:` table). A three-way PROCEED/VETO/SKIPPED result fits either; the shape is a design decision.
- `.rc`/`.err` persistence has no precedent (existing loops read exit codes via `${captured.<state>.exit_code}`; only `vega-viz.yaml` writes an ad-hoc error file), so the `advise-<ID>.{json,err,rc}` layout is new convention, not a followed one.

**Option A**: New run-record class `advisor_veto` mapped to a `blocked` outcome, with its own token in `RUN_RECORD_TOKENS`, a recording state in `refine-to-ready-issue.yaml`, a `forward_stop` case in `prepare-issue.yaml`, and an explicit `route_refine_outcome` route in `autodev.yaml`. Distinguishes vetoes in telemetry and lets each caller route them independently; widens a closed vocabulary across five files.

**Option B**: Reuse an existing legacy class (e.g. `gate_unmet` → `deferred`, or `quality` → `blocked`) with the advisor recommendation carried in the session log only. No vocabulary change and callers already handle it; a veto becomes indistinguishable from other gate failures in run records.

> **Selected:** Option B — reuses the existing `gate_unmet`/`quality` legacy classes; no closed-vocabulary change.

**Recommended**: Option B for v1 — the consult is opt-in and veto-only, and the closed-vocabulary change is the highest-cost, highest-blast-radius part of this issue; promote to Option A if veto telemetry proves needed.

### Decision Rationale

**Selected option:** Option B — reuse an existing legacy run-record class.

**Reasoning:** `RUN_RECORD_TOKENS` is a closed 12-member tuple (`run_record.py:143`) and unrecognized tokens collapse to `MISSING`; Option A widens it across `run_record.py`, `refine-to-ready-issue.yaml:classify_terminal`, `prepare-issue.yaml:forward_stop`, `autodev.yaml:route_refine_outcome`, and `test_run_record.py`. Option B reuses `gate_unmet` (→ `deferred`) or `quality` (→ `blocked`), already mapped in `outcome_from_legacy_class` and already handled by every caller. The feature is opt-in and veto-only, so the loss of veto telemetry is acceptable for v1.

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| A — new `advisor_veto` class | 2 | 1 | 2 | 1 | 6/12 |
| B — reuse legacy class | 3 | 3 | 2 | 3 | 11/12 |

**Key evidence:** `run_record.py:46-50,215-217` (existing `gate_unmet`/`quality` mapping); `autodev.yaml:685` (classify table enumerates the full closed vocabulary); the issue's own **Recommended** marker for Option B.

**`record_advisor_veto` contract (mirror `record_gate_unmet`, `refine-to-ready-issue.yaml:1136-1148`):**
1. `printf 'gate_unmet' > ${context.run_dir}/refine-terminal-class` — required: autodev's
   MISSING fallback reads this file, so omitting it loses the class.
2. `ll-issues run-record write <ID> --run-dir ... --writer refine-to-ready-issue --legacy-class gate_unmet || true`.
3. Echo `[ADVISOR_VETO] <ID> - <recommendation>`.
4. **Make the veto actionable:** append the advisor's recommendation to the issue file as an
   `## Advisor Veto` note (replace any prior one; `ll-issues` writer or the helper's
   `--write-note`), so a human or the next refine pass sees why. The issue already passed every
   deterministic gate, so re-refining without this note changes nothing.
5. `next: failed`, `on_error: failed`.

**Follow-through (resolved in review):** the class is `gate_unmet` (→ deferred). `record_gate_unmet` itself is not reused: its message is specific to structure gates. A new `record_advisor_veto` state writes the same `gate_unmet` legacy class with an accurate `[ADVISOR_VETO]` message, then `next: failed`. No vocabulary change.

**Accepted fail-open on re-runs:** autodev re-refines a deferred issue, and each pass consults again against the per-issue budget (`max_consults_per_task=3`). Once spent, `ll-advise` exits 2 → SKIPPED → the issue passes, so a veto can be outwaited by repeated runs. Accepted for v1: the consult is opt-in and veto-only. The one-shot marker is per run (`run_dir` is per instance), so a prior veto does not force a re-consult beyond what the budget allows.

## Program Design

### Types

- `AdviseVerdict`: `Literal["PROCEED", "VETO", "SKIPPED"]`

### Signatures

- `map_advise_verdict(rc_text: str | None, payload_text: str | None) -> tuple[AdviseVerdict, str]` — pure mapping of persisted `.rc`/`.json` to a verdict plus a log reason
- `cmd_advise_consult(config: BRConfig, args: argparse.Namespace) -> int` — runs `ll-advise --json`, persists `advise-<ID>.{json,err,rc}`, returns the routing code (never the advisor's own exit code)

### Call Path

`refine-to-ready-issue.yaml:check_proof_before_done` -> `check_advise_ready_enabled` -> `run_advise_ready` -> `cmd_advise_consult` -> (subprocess `ll-advise`) `main_advise` -> `consult_for_trigger`

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` — new gate/consult/veto states on the done path (`check_advise_ready_enabled`, `run_advise_ready`, `record_advisor_veto`); bump `max_steps` (currently 100) for the two extra hops and record it in the history comment
- `scripts/little_loops/loops/recursive-refine.yaml` — declare the flag in `context:` and pass it to `refine-to-ready-issue` (pass-through only; it does not read run records)
- `scripts/little_loops/loops/prepare-issue.yaml` — no declaration needed (`context_passthrough: true`); no veto handling needed, `gate_unmet` → deferred is already handled by `forward_stop`
- `scripts/little_loops/loops/autodev.yaml` — declare the flag in `context:` (`""`) and let it pass to `prepare-issue`; no `route_refine_outcome` change
- `scripts/little_loops/cli/issues/` — new helper subcommand (location TBD)

### Dependent Files (Callers/Importers)
- `ll-advise` CLI (`little_loops.cli.advise.main_advise`; exit 0 on success, 2 on the 7 skip reasons)
- `little_loops.advisor.consult_for_trigger` — per-issue budget (`max_consults_per_task=3`) shared with the `confidence_gate` and `pre_done` consults

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/issues/__init__.py` — four registration sites for the new subcommand: lazy import block, epilog listing (next to `next-obligation`/`run-record`), `add_*_parser(subs)` block, `args.command` dispatch [Agent 1/2 finding]
- `scripts/little_loops/cli/issues/next_obligation.py` (`register(subs)`), `check_verify_verdict.py`, `run_record.py` — sibling helper modules; models for the new module's `add_<name>_parser`/`cmd_<name>` shape [Agent 1 finding]
- `scripts/little_loops/run_record.py` (`outcome_from_legacy_class`, `LEGACY_CLASSES`) — Option B reuses `gate_unmet` → deferred; no vocabulary edit, but this is the mapping the veto route depends on. The new `record_advisor_veto` writer state is a new writer of that class, so `test_run_record.py` sets need entries [Agent 1 finding, corrected in review]
- `scripts/little_loops/loops/rn-build.yaml:582`, `sprint-build-and-validate.yaml:82,181`, `issue-refinement.yaml:21` — call `recursive-refine`; inherit the empty default, need edits only if they should forward the flag [Agent 2 finding]
- `scripts/little_loops/loops/rn-remediate.yaml`, `auto-refine-and-implement.yaml`, `oracles/resolve-decision.yaml` — other `refine-to-ready-issue` callers; confirm they pass no `context:` that would shadow the flag, and that the flag-off path is unchanged for them [Agent 1 finding]
- `scripts/little_loops/hooks/pre_done.py` — existing `consult_for_trigger` consumer; shares the per-issue budget the new consult draws from [Agent 1 finding]

### Documentation
_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_REFERENCE.md` — "Score dispatch (ENH-3604)" `NONE` bullet lists `check_decision_before_done` → `write_done_record` → `done`, omitting `check_proof_before_done`; add the proof gate and the opt-in advise hop. Also the `refine-to-ready-issue` table row (~line 84) [Agent 2 finding]
- `docs/reference/CLI.md` — new `#### \`ll-issues <name>\`` section and subcommand-table entry; cross-reference from `### ll-advise` [Agent 2 finding]
- `docs/reference/API.md` — new row in the `little_loops.cli.issues.*` module table (next to the `run-record` row) [Agent 2 finding]
- `docs/reference/DEFERRAL_CODES.md` — VETO → `gate_unmet` → deferred; add a row if the veto records a new `--reason` code [Agent 2 finding]
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` header comment (done-path diagram, ~line 48) — update to include `check_proof_before_done` and the new gate; record any `max_steps` change in the history comment (~lines 120-132) [Agent 2 finding]

### Configuration
_Wiring pass added by `/ll:wire-issue`:_
- No `config-schema.json` change: `ll-advise` always passes `manual=True`, so a new `--signal` name needs no `advisor.triggers` entry. `docs/reference/CONFIGURATION.md` `### advisor` (`max_consults_per_task`) is the budget the consult shares [Agent 2 finding]

### Tests
- `scripts/tests/test_builtin_loops.py` — chain-shape pins, default-off, stub-`ll-advise` execution
- New helper tests — verdict mapping over fixture `.json`/`.rc`/`.err` sets

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_autodev_decision_gate.py::TestChildDecisionInvariant.test_decision_gate_routes` — asserts `check_proof_before_done` `on_no`/`on_error == "write_done_record"`; will break, retarget to `check_advise_ready_enabled` [Agent 3 finding]
- `scripts/tests/test_autodev_proof_reentry.py` (`STATE = CHILD["check_proof_before_done"]`, lines ~207-208) — same two edge assertions; will break, update [Agent 3 finding]
- `scripts/tests/test_autodev_decision_gate.py::TestChildDecisionInvariant.test_only_gate_write_done_record_and_class_writers_reach_done` — inbound-edges-to-`done` check; should survive, re-verify [Agent 3 finding]
- `scripts/tests/test_builtin_loops.py` (`max_steps == 100` assertion, ~line 1872) — update if the two extra hops force a `max_steps` bump [Agent 3 finding]
- `scripts/tests/test_fsm_topology.py` (state-count asserts at ~lines 291, 322) — unconfirmed whether they cover `refine-to-ready-issue`; read before editing the loop [Agent 3 finding]
- `scripts/tests/test_run_record.py` (`LEGACY_CLASS_STATES`, `TERMINAL_BEARING_STATES`, and the done-path gate sets) — `record_advisor_veto` is a new writer of `gate_unmet`: add it to the class-writer sets, and add the new gate/consult states to whichever done-path sets apply [Agent 3 finding, corrected in review]
- `scripts/tests/test_builtin_loops.py` (`skip_learning_gate` block, ~lines 18023-18264; registry tuples ~lines 20599-20763, e.g. `("loops/autodev.yaml", "context.skip_learning_gate", "ENH-3358")`) — model for the flag's empty-default and pass-through pins; a new `context.<flag>` reference likely needs a matching registry row [Agent 3 finding]
- `scripts/tests/test_wiring_reference_docs.py` (tuple table, ~lines 256-264) — add `("docs/reference/CLI.md", "#### \`ll-issues <name>\`", "ENH-3626")` and the `API.md` row, or the docs gate fails [Agent 3 finding]
- New `scripts/tests/test_ll_issues_<name>.py` — model on `test_ll_issues_next_obligation.py::TestCli` (`_cli()` helper, `--help` registration, exit codes) and `test_run_record.py::TestRecordToken` (parametrized `map_advise_verdict` cases); no existing test stubs `ll-advise` on `PATH`, so use the `chmod(0o755)` stub pattern from `test_builtin_loops.py` [Agent 3 finding]
- `scripts/tests/test_fsm_validation_shell_safety.py` (MR-11) and `test_fsm_validation_evaluator_rules.py` (MR-10) — the new state's shell action must escape `$${...}` and must not swallow a JSON parse failure with exit 0 [Agent 3 finding]

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-27 — based on codebase analysis:_

- Nothing proposed exists yet: no `check_advise_ready_enabled`/`run_advise_ready`/`record_advisor_veto`/`advisor_veto` outside `.issues/`, no `ll-advise` reference in any loop YAML, no advise-flavored `ll-issues` subcommand.
- Done chain today: `route_score_obligation` (classify on `ll-issues next-obligation --format token`; `NONE` → `check_decision_before_done`) → `check_proof_before_done` (`fragment: shell_exit`; `on_no`/`on_error` → `write_done_record`) → `done`. `check_missing_artifacts.on_yes` also feeds `check_decision_before_done`, so a gate placed after `check_proof_before_done` covers both done edges.
- `refine-to-ready-issue.yaml` `context:` holds only `max_refine_count`; thresholds are seeded at launch and must not be declared (BUG-2767). The empty-string flag needs a declaration site per loop chain: `autodev.yaml` `context:` (as `skip_learning_gate: ""`); `recursive-refine.yaml` `context:`; `refine-to-ready-issue.yaml` `context:`. `prepare-issue.yaml` declares no `context:` and receives everything via `context_passthrough: true`, so it needs no declaration. `rn-remediate.yaml` uses `parameters.<k>.default` instead of `context:` (BUG-3425) — a third convention.
- Callers: `autodev.yaml:refine_current` → `prepare-issue` → `run_refine_to_ready` → `refine-to-ready-issue` (all `context_passthrough: true`); `recursive-refine.yaml:run_refine` → `refine-to-ready-issue`. A sub-loop reaching `done` is success; `failed` takes the failure path. `recursive-refine` does not read run records — it routes on the sub-loop terminal then `check_passed`.
- Veto outcome plumbing (if a new run-record class is chosen): `run_record.py` (`LEGACY_CLASSES`, `outcome_from_legacy_class`, `RUN_RECORD_TOKENS` — a closed 12-member tuple, unrecognized → `MISSING`), `refine-to-ready-issue.yaml` `classify_terminal`, `prepare-issue.yaml:forward_stop`, `autodev.yaml:route_refine_outcome` (classify table enumerating the closed vocabulary), `test_run_record.py` (`TestOutcomeMapping.CASES`, `LEGACY_CLASS_STATES`).
- `ll-issues` subcommand wiring is three-site: module in `scripts/little_loops/cli/issues/` with `add_<name>_parser`/`cmd_<name>(config, args) -> int`; lazy import + `add_*_parser(subs)` + `args.command` dispatch + epilog line in `cli/issues/__init__.py`; docs anchors pinned by `scripts/tests/test_wiring_reference_docs.py`.
- 429 handling is executor-side: `fsm/executor.py:_intercept_transient_failure` fires only when `exit_code != 0` AND output classifies as transient rate-limit/quota; a zero exit is never intercepted. It is inert on `loop:` states. The helper's always-routing-code contract must therefore avoid propagating the advisor's non-zero exit and avoid emitting rate-limit text on a state that returns non-zero.
- `ll-advise` (`cli/advise.py:main_advise`/`cmd_invoke`) always passes `manual=True`, which bypasses the `advisor.enabled` switch and the `advisor.triggers` allowlist: `--signal` is a free string, so a new signal name needs no config or code change, and the budget (`max_consults_per_task`) still applies.

## Implementation Steps

1. Build and test the shared helper `ll-issues advise-consult` (verdict mapping, persistence, always-exit-0 token contract, `LL_ISSUE_ID` on the child env, unreadable `--context-file` → SKIPPED, subprocess timeout → SKIPPED, pinned question text).
2. (Decided) Veto class = `gate_unmet` via a new `record_advisor_veto` state that writes `refine-terminal-class`, the run-record (`|| true`), the `[ADVISOR_VETO]` echo, and an `## Advisor Veto` note on the issue; add the state to `LEGACY_CLASS_STATES`/`TERMINAL_BEARING_STATES` in `test_run_record.py`.
3. Wire `check_advise_ready_enabled` (flag + one-shot marker), `run_advise_ready` (`classify` + `route:`), and `record_advisor_veto` into `refine-to-ready-issue.yaml`; bump `max_steps` and update the header diagram/history; add the `advise_ready: ""` flag to `autodev.yaml` and `recursive-refine.yaml` `context:` and `refine-to-ready-issue.yaml` `context:`.
4. Tests: budget exhausted (`ll-advise` exit 2) → SKIPPED → `write_done_record`; helper timeout → SKIPPED; marker scope (same ID twice under a shared `run_dir` → one consult; two IDs → two); veto writes `refine-terminal-class`; veto adds the note; default-off chain reaches `write_done_record` without invoking `ll-advise`; VETO/PROCEED/SKIPPED routing; failure = flag off; second done-chain pass does not re-consult; subprocess env carries `LL_ISSUE_ID`; existing callers treat the veto as deferred.
5. `ll-loop validate` for every touched loop.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Register the new subcommand in `scripts/little_loops/cli/issues/__init__.py` — lazy import, epilog line, `add_*_parser(subs)`, `args.command` dispatch
- Update `scripts/tests/test_autodev_decision_gate.py` and `scripts/tests/test_autodev_proof_reentry.py` — retarget the `check_proof_before_done` `on_no`/`on_error` assertions to the new gate state
- Check `scripts/tests/test_builtin_loops.py` `max_steps == 100` and `scripts/tests/test_fsm_topology.py` state counts; bump if the extra hops require it
- Add `context.<flag>` registry rows and empty-default/pass-through pins in `scripts/tests/test_builtin_loops.py`, modelled on `skip_learning_gate`
- Add `scripts/tests/test_wiring_reference_docs.py` rows plus `docs/reference/CLI.md` and `docs/reference/API.md` entries for the new subcommand
- Update `docs/guides/LOOPS_REFERENCE.md` (Score dispatch `NONE` bullet, `refine-to-ready-issue` row) and the `refine-to-ready-issue.yaml` header diagram comment
- Confirm the other `refine-to-ready-issue` / `recursive-refine` callers (`rn-remediate`, `auto-refine-and-implement`, `oracles/resolve-decision`, `rn-build`, `sprint-build-and-validate`, `issue-refinement`) are unaffected by the empty default

## Impact

- **Priority**: P3 - opt-in quality improvement, not blocking
- **Effort**: Medium - one helper, three loop states, flag pass-through; no new run-record class
- **Risk**: Low - off by default, fail-open
- **Breaking Change**: No

## Scope Boundaries

- **In scope**: the shared helper; the opt-in done-path gate in `refine-to-ready-issue`
  with a one-shot-per-run marker; a `record_advisor_veto` state reusing the `gate_unmet`
  class; context-flag pass-through.
- **Out of scope (added in review)**: a new run-record class or `RUN_RECORD_TOKENS` change
  (Option B); caller edits for veto handling; cross-run veto persistence.
- **Out of scope**: the go-no-go waiver veto (ENH-3590); letting a consult grant
  readiness or override a failing gate; routing on `confidence`/`dissent`; enabling the
  consult by default; changing `ll-advise` internals.

## Open Questions

_None outstanding._ Resolved in review:

- **Where does a veto route?** `record_advisor_veto` writes the existing `gate_unmet` class
  (→ deferred) and goes to `failed`; existing callers already handle it (Option B).
- **Does a veto persist across passes?** No. The one-shot marker is per run. A later run
  re-consults until the per-issue budget is spent, after which the consult is SKIPPED
  (accepted fail-open; see Decision Rationale).

## Acceptance Criteria

- [ ] With the flag empty (default), the done path reaches `write_done_record` without invoking `ll-advise`
- [ ] With the flag set, a threshold-passing issue gets exactly one consult per run (including when the done chain is re-entered after `run_spike` or a decide re-score), billed to the per-issue budget via `LL_ISSUE_ID` set by the helper on the child process
- [ ] The payload, stderr, and exit code are persisted to `<run_dir>/advise-<ID>.{json,err,rc}` and mapped by the shared helper; the loop routes on the helper's token, never on the advisor's stdout
- [ ] VETO keeps the issue out of `done`, records `gate_unmet` (→ deferred) via `record_advisor_veto`, echoes an `[ADVISOR_VETO]` line with the recommendation, and existing callers handle it with no edits
- [ ] Any `ll-advise` failure (non-zero exit, timeout, budget exhaustion, unparseable output) behaves exactly like the flag being off; the loop never halts or waits on an advisor rate limit
- [ ] `record_advisor_veto` writes `refine-terminal-class` = `gate_unmet` and appends an `## Advisor Veto` note carrying the recommendation
- [ ] The consult question text is pinned in the helper and a fixture test maps the real `ll-advise --json` output shape to PROCEED/VETO
- [ ] ENH-3590 can reuse the helper unchanged

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-27 | Priority: P3


## Session Log
- `/ll:wire-issue` - 2026-09-27T04:18:11 - `b81845df-148e-4cb8-8d11-cc360743e07f.jsonl`
- `/ll:decide-issue` - 2026-09-27T04:03:27 - `4b1c5ade-bd97-4871-b4cf-1f3dcd7cc5d1.jsonl`
- `/ll:refine-issue` - 2026-09-27T04:01:53 - `b9726386-58c1-4c65-8485-76e226017a2f.jsonl`
- `/ll:format-issue` - 2026-09-27T03:56:23 - `0b26d35d-ec12-419a-9599-7aa7bcfe4ed1.jsonl`
- `/ll:capture-issue` - 2026-09-27T01:56:21 - `282c1e7b-289d-4b4c-9b06-d9e617a5b759.jsonl`

## Tests

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-27 — based on codebase analysis:_

- Conventions in force: helper verdict mapping is a pure function separate from `cmd_*` and returns a safe token for unrecognized input (`check_verify_verdict.classify_verify_verdict`, `run_record.record_token`); tests parametrize over cases (`test_run_record.py::TestOutcomeMapping.CASES`) and add a subprocess exit-code test (`test_ll_issues_next_obligation.py::TestCli`). Advisor CLI tests patch `sys.argv` and call `main_advise()` (`test_cli_advise.py::TestMainAdvise`).
- Loop tests pin chain shape with static edge assertions on the loaded YAML plus stub-binary execution (`test_builtin_loops.py`: stub `ll-issues`/`ll-advise` on `PATH`, textual `${context.run_dir}` substitution, `"${" not in script`, `$${` restored to `${`). Default-off flags are pinned as `parameters.<k>.default == ""` / `context` value `== ""`. Sub-loop states must not carry `on_no` or `timeout` (`TestSubLoopStateTimeoutAudit`).
- Any new `ll-issues` subcommand needs a `test_wiring_reference_docs.py` entry (`docs/reference/CLI.md` heading and `docs/reference/API.md` row) or the docs gate fails.
