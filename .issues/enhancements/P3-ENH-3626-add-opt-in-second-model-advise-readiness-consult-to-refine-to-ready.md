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
  - **VETO** → the issue does not reach `done`. It routes to a new non-done outcome
    (see Open Questions) with the advisor's `recommendation` logged to the session log.
- Any `ll-advise` failure (exit 2 with any of the 7 skip reasons, advisor rate limit,
  advisor auth failure, unreadable output) is SKIPPED: logged, then treated exactly as if
  the flag were off. The loop never waits on a 429 retry for the advisor.

## Motivation

ENH-3590 adds a second-model veto only where go-no-go waives the outcome threshold. That
covers issues that *fail* the threshold and get let through anyway; those issues never
reach refine-to-ready's done edge (a sub-threshold outcome routes to
`check_decision_needed`, not `done`). Issues that *pass* the thresholds get no
second-model review at all. This issue covers that complementary, common path. The two
are not redundant.

## Proposed Solution

**Shared helper (land first).** A Python entry point (e.g. an `ll-issues` subcommand;
name TBD) that:

1. Runs `ll-advise --signal <signal> --question <q> --context-file <issue> --json` with
   `LL_ISSUE_ID=<ID>` so it bills the per-issue budget bucket.
2. Writes `<run_dir>/advise-<ID>.{json,err,rc}`.
3. Maps the result to PROCEED/VETO/SKIPPED: missing or non-zero rc, or missing or
   unparseable JSON → SKIPPED (log the skip reason; emit a WARNING line for
   `not_configured`); the leading word of `recommendation`, uppercased with punctuation
   stripped, equal to `VETO` → VETO; anything else → PROCEED. `confidence` and `dissent`
   are logged but never routed on.
4. Always exits with a routing code the loop reads (no stdout parsing, MR-1), and never
   propagates the advisor's exit code, so executor-side 429 interception cannot stall
   the loop.

ENH-3590's consult (a policy step once ENH-3623 lands) calls the same helper with its own
signal and question.

**Loop wiring in `refine-to-ready-issue.yaml`:**

```
check_proof_before_done --on_no/on_error--> check_advise_ready_enabled   # was write_done_record
check_advise_ready_enabled --on_no/on_error--> write_done_record          # flag off: today's path
                           --on_yes--> run_advise_ready
run_advise_ready --PROCEED/SKIPPED--> write_done_record
                 --VETO--> record_advisor_veto
```

State names are proposals. The flag is an empty-string context key (autodev's
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

**Follow-through:** Pick the concrete legacy class (`gate_unmet` → deferred is the likelier fit, since a veto is a gate not met rather than a quality failure) during implementation step 2.

## Program Design

### Types

- `AdviseVerdict`: `Literal["PROCEED", "VETO", "SKIPPED"]`

### Signatures

- `map_advise_verdict(rc_text: str | None, payload_text: str | None) -> tuple[AdviseVerdict, str]` — pure mapping of persisted `.rc`/`.json` to a verdict plus a log reason
- `cmd_advise_consult(config: BRConfig, args: argparse.Namespace) -> int` — runs `ll-advise --json`, persists `advise-<ID>.{json,err,rc}`, returns the routing code (never the advisor's own exit code)

### Call Path

`refine-to-ready-issue.yaml:check_proof_before_done` -> `check_advise_ready_enabled` -> `run_advise_ready` -> `cmd_advise_consult` -> `main_advise` -> `consult_for_trigger`

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` — new gate/consult/veto states on the done path
- `scripts/little_loops/loops/prepare-issue.yaml`, `scripts/little_loops/loops/recursive-refine.yaml` — declare and pass through the flag; handle the veto outcome
- `scripts/little_loops/loops/autodev.yaml` — declare and pass the flag to `prepare-issue`
- `scripts/little_loops/cli/issues/` — new helper subcommand (location TBD)

### Dependent Files (Callers/Importers)
- `ll-advise` CLI (`little_loops.cli.advise.main_advise`; exit 0 on success, 2 on the 7 skip reasons)
- `little_loops.advisor.consult_for_trigger` — per-issue budget (`max_consults_per_task=3`) shared with the `confidence_gate` and `pre_done` consults

### Tests
- `scripts/tests/test_builtin_loops.py` — chain-shape pins, default-off, stub-`ll-advise` execution
- New helper tests — verdict mapping over fixture `.json`/`.rc`/`.err` sets

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

1. Build and test the shared helper (verdict mapping, persistence, exit contract).
2. Decide the veto outcome's run-record class and how each caller routes it.
3. Wire the gate/consult/veto states into `refine-to-ready-issue.yaml`; add the flag to every loop in the pass-through chain.
4. Tests: default-off chain reaches `write_done_record` without invoking `ll-advise`; VETO/PROCEED/SKIPPED routing; failure = flag off; callers handle the veto class.
5. `ll-loop validate` for every touched loop.

## Impact

- **Priority**: P3 - opt-in quality improvement, not blocking
- **Effort**: Medium - one helper, a few states, a new outcome class across callers
- **Risk**: Low - off by default, fail-open
- **Breaking Change**: No

## Scope Boundaries

- **In scope**: the shared helper; the opt-in done-path gate in `refine-to-ready-issue`;
  a veto outcome and its handling in callers; context-flag pass-through.
- **Out of scope**: the go-no-go waiver veto (ENH-3590); letting a consult grant
  readiness or override a failing gate; routing on `confidence`/`dissent`; enabling the
  consult by default; changing `ll-advise` internals.

## Open Questions

- **Where does a veto route?** A threshold-passing issue that the advisor vetoes needs a
  non-done outcome. Likely a new run-record class (e.g. `advisor_veto`), which
  `prepare-issue`/autodev and `recursive-refine` must each handle (defer? send back to
  refine with the advisor's risks?).
- **Does a veto persist across passes?** If the issue is re-refined later, should a prior
  veto force another consult, or is one consult per pass enough?

## Acceptance Criteria

- [ ] With the flag empty (default), the done path reaches `write_done_record` without invoking `ll-advise`
- [ ] With the flag set, a threshold-passing issue gets exactly one consult, billed to the per-issue budget
- [ ] The payload, stderr, and exit code are persisted to `<run_dir>/advise-<ID>.{json,err,rc}` and mapped by the shared helper, with no stdout parsing
- [ ] VETO keeps the issue out of `done`, logs the advisor's recommendation, and every caller handles the new outcome
- [ ] Any `ll-advise` failure behaves exactly like the flag being off; the loop never halts or waits on an advisor rate limit
- [ ] ENH-3590 can reuse the helper unchanged

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-27 | Priority: P3


## Session Log
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
