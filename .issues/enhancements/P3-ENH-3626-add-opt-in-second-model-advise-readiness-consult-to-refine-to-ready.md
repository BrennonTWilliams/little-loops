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
- `/ll:format-issue` - 2026-09-27T03:56:23 - `0b26d35d-ec12-419a-9599-7aa7bcfe4ed1.jsonl`
- `/ll:capture-issue` - 2026-09-27T01:56:21 - `282c1e7b-289d-4b4c-9b06-d9e617a5b759.jsonl`
