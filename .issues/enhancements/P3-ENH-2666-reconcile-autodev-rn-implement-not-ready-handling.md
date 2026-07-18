---
id: ENH-2666
type: ENH
priority: P3
status: open
captured_at: '2026-07-18T02:50:02Z'
discovered_date: '2026-07-18'
discovered_by: capture-issue
parent: EPIC-2663
relates_to:
- ENH-2664
- FEAT-2665
blocked_by:
- FEAT-2665
labels:
- loops
- orchestration
confidence_score: 95
outcome_confidence: 68
score_complexity: 14
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 18
decision_needed: false
size: Very Large
---

# ENH-2666: Reconcile autodev vs rn-implement "not ready" handling

## Summary

The two autonomous processing paths handle the same conceptual event — "this
issue isn't ready to implement" — with opposite outcomes. Decide on and
implement a consistent policy so behavior is predictable regardless of which
orchestrator runs.

## Motivation

- `autodev.yaml` never sets `deferred`: a low-readiness issue is appended to a
  ledger file (`autodev-skipped.txt` reason `low_readiness` at 849-850, or
  `-gate-blocked.txt` at 507-509, `-decision-unresolved.txt` at 379-381) and its
  status is **left `open`** — so it's retried next run.
- `rn-implement.yaml` sets `status: deferred` (`mark_deferred`, 1330-1357) — the
  issue leaves active selection and is **not retried**.

Same input, divergent lifecycle. A user switching between `ll-auto` and
`rn-implement` gets surprising, inconsistent backlog behavior. Once ENH-2664
(reason discriminator) and FEAT-2665 (resurfacing) land, the two paths should
converge on a single documented policy for not-ready issues.

## Current Behavior

See Motivation — the two ledgers/status transitions above.

## Proposed Behavior

**Decision: align `autodev.yaml` to `rn-implement.yaml`'s existing model**, not the
reverse. Every not-ready exit in `autodev.yaml` (`low_readiness`,
`gate-blocked`, `decision-unresolved`, and the `decomposed` skips) transitions
the issue to `status: deferred` via the same `deferred_by: automation` /
`deferred_reason` fields ENH-2664 introduced for `rn-implement.yaml`'s
`mark_decomposed` state, using one reason code per ledger category. Visibility
is provided by FEAT-2665's triage surface, not by retrying every run.

Rejected alternative: leaving both paths `open` + ledgered with a new
retry-cap circuit-breaker. That would require building net-new persistent
retry-count tracking across runs, and would make the ENH-2664 reason-code
fields moot for the majority of not-ready exits (autodev is the higher-volume
path). It also burns an LLM invocation re-evaluating the same not-ready issue
every run until the cap trips, which the `deferred` transition avoids
entirely.

**Dependency**: this issue is `blocked_by: [FEAT-2665]`. Converting autodev's
ledger skips to `deferred` recreates the ENH-2464/2465/2466 invisibility bug
for the (higher-volume) autodev path unless the triage surface exists first.
Do not implement this issue before FEAT-2665 ships.

## Implementation Steps

1. Enumerate every not-ready exit in `autodev.yaml` (`low_readiness` @849-850,
   `gate-blocked` @507-509, `decision-unresolved` @379-381, `decomposed` @585,
   @792) and map each to a `deferred_reason` code (new codes as needed,
   alongside `rn-implement.yaml`'s existing `blocked_by_unmet` /
   `remediation_stalled`).
2. Replace each ledger-append + `status: open` exit in `autodev.yaml` with a
   `set-status <ID> deferred --by automation --reason <code>` transition,
   mirroring `rn-implement.yaml`'s `mark_deferred` state.
3. Decide whether the ledger files (`autodev-skipped.txt` etc.) are retired or
   kept as a same-run summary alongside the status transition — they're
   redundant with FEAT-2665's triage surface for cross-run visibility but may
   still be useful for the current run's end-of-run report.
4. Document the unified policy in `.claude/CLAUDE.md` § Issue File Format
   (extend the ENH-2664 deferral-discriminator entry to note autodev now uses
   the same transition).
5. Tests: parity fixtures asserting `autodev.yaml` and `rn-implement.yaml`
   produce the same lifecycle (`status: deferred` + matching field shape) for
   an equivalent not-ready issue.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in
the implementation:_

6. Fix `scripts/tests/test_autodev_decision_gate.py` — update the
   `"autodev-decision-unresolved.txt" in action` assertion (line 632) and
   the adjacent `/ll:decide-issue` hint assertion (line 636) in
   `test_record_decision_unresolved_advances_queue_without_failing` to match
   the new `set-status ... deferred --reason decision_unresolved` action
   body; reword the "writing low_readiness" docstrings at lines 426/468.
7. Fix `scripts/tests/test_builtin_loops.py`'s
   `test_mark_gate_blocked_advances_queue_without_failing` (~3712-3723) to
   match `mark_gate_blocked`'s new action body if the ledger write is
   replaced rather than supplemented.
8. Extend `scripts/tests/test_set_status_cli.py`'s deferral discriminator
   tests (~226-359) to cover the three new reason codes, cloning
   `test_set_status_deferred_stamps_automation_reason` (260-298); add a
   negative test for rejected `--reason` values following
   `test_set_status_invalid_by_rejected`'s pattern (336-359).
9. (Optional, consistency) Extend `deferred_triage.py`'s `_REASON_RANK`
   (line 14) with the three new codes so they get intentional triage
   priority instead of the default lowest-rank fallback.
10. Update `docs/reference/CLI.md`, `docs/reference/API.md`, and
    `docs/guides/ISSUE_MANAGEMENT_GUIDE.md` per the Documentation subsection
    of the Integration Map above.
11. Resolve the `skip_inflight`/`refine_failed` scope flag (Integration Map
    Tests subsection) before or during step 1 — confirm whether it's a
    fourth qualifying not-ready exit or deliberately out of scope.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Blocker status confirmed clear**: FEAT-2665 has shipped
  (`.issues/features/P2-FEAT-2665-...md` frontmatter `status: done`,
  `completed_at: '2026-07-18T04:04:15Z'`, commit `a2f127d7`). The
  `ll-issues deferred-triage` CLI (`scripts/little_loops/cli/issues/deferred_triage.py`)
  is live, so this issue's `blocked_by: [FEAT-2665]` gate is satisfied.
- **`decomposed` exits are not like the other three** — `enqueue_children`
  (`autodev.yaml:568-596`) and `check_broke_down` (`autodev.yaml:611-808`,
  ledger write @792) both call `ll-issues finalize-decomposition <ID>
  --children-file ...` before the `autodev-skipped.txt` append, which already
  sets the parent issue to `status: done` (a closure, not a re-surfacing
  candidate). Converting these two to `deferred` per step 1 would regress
  that closure — scope step 1's per-exit reason-code mapping to the three
  genuinely-open exits (`low_readiness`, `gate-blocked`,
  `decision-unresolved`); leave the `decomposed` ledger writes as same-run
  summary lines only, or drop them from this issue's scope entirely.
- **`DeferReason` enum is not the only place codes are declared** —
  `scripts/little_loops/issue_lifecycle.py:46-67` defines `DeferBy`/
  `DeferReason`, but `scripts/little_loops/cli/issues/__init__.py`'s
  `set-status` subparser hardcodes its own `--reason` `choices=[...]` list
  (~line 775) with only `blocked_by_unmet`/`remediation_stalled` — the two
  are **not kept in sync automatically**. Step 1's new codes (e.g.
  `low_readiness`, `gate_blocked`, `decision_unresolved`) must be added to
  *both* the enum and the CLI `choices=` list, or `set-status ... --reason
  low_readiness` will be rejected by argparse before it reaches
  `_status_updates()` (`cli/issues/set_status.py:38-63`).
- **`deferred_triage.py` needs no change for new codes** — `_REASON_RANK` in
  `deferred_triage.py:14` falls back to `_DEFAULT_REASON_RANK` (lowest sort
  priority) for any unranked code, and `_collect_rows()` reads
  `deferred_reason` as an opaque string. New autodev codes render correctly
  once they're `set-status`-writable (see enum/choices gap above);
  `deferred_triage.py` itself is not on the implementation path.
- **Template for step 2** — the exact block to mirror is
  `rn-implement.yaml`'s `mark_deferred` state (lines 1330-1366): branches on
  a `REASON`/`REASON_CODE` pair, appends a human-readable line to
  `deferred.txt`, writes a `deferred_reason_<ID>.txt` sidecar (consumed by
  the `report` state's `deferred_automation` breakdown at lines 1591-1607),
  then runs `ll-issues set-status "$ID" deferred --by automation --reason
  "$REASON_CODE" 2>/dev/null || true`. Each of autodev's three qualifying
  exits should follow this shape rather than inventing a new one — note the
  `$${ID}`-style brace-escaping needed for FSM shell interpolation.
- **`autodev.yaml`'s `done` state (858-900) needs updating alongside step 3**
  — it currently reads back `autodev-passed.txt`/`autodev-skipped.txt`/
  `autodev-gate-blocked.txt`/`autodev-decision-unresolved.txt` via `grep -c`
  for its plain-text summary, with no `summary.json` write. If the sidecar
  pattern above is adopted, this state should glob `deferred_reason_*.txt`
  and build a `deferred_automation` breakdown the same way
  `rn-implement.yaml`'s `report` state does, for parity.
- **Test scaffolding to extend for step 5** — `scripts/tests/test_rn_implement.py`
  has a `_load_loop()` helper (lines 22-25) and state-shape assertions on
  `mark_deferred` (e.g. `test_mark_deferred_stamps_automation_discriminator`,
  ~lines 1022-1131) that assert on `action` substrings
  (`"--by automation"`, `"--reason"`, reason-code strings) rather than
  executing the loop. `scripts/tests/test_builtin_loops.py`'s
  `TestAutodevLoop` class (line ~3424, `data` fixture ~3429-3432) already has
  an analogous test for `mark_gate_blocked`
  (`test_mark_gate_blocked_advances_queue_without_failing`, ~3712-3723) to
  model the new deferred-transition assertions after. No existing test
  asserts cross-loop parity between `autodev.yaml` and `rn-implement.yaml` —
  step 5's parity fixture is net-new.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/autodev.yaml` — `record_decision_unresolved`
  (372-384), `mark_gate_blocked` (501-512), `recheck_after_size_review`
  (836-856): replace ledger-append + implicit `status: open` with a
  `mark_deferred`-style `set-status <ID> deferred --by automation --reason
  <code>` action. `done` (858-900): update the end-of-run summary to read
  `deferred_reason_*.txt` sidecars if that pattern is adopted (see Codebase
  Research Findings above).
- `scripts/little_loops/issue_lifecycle.py:46-67` — extend `DeferReason` enum
  with the new autodev codes (`low_readiness`, `gate_blocked`,
  `decision_unresolved`).
- `scripts/little_loops/cli/issues/__init__.py` (~line 775) — `set-status`
  subparser's hardcoded `--reason` `choices=[...]` list must gain the same
  new codes or `set-status` will reject them via argparse.
- `.claude/CLAUDE.md` § Issue File Format — extend the ENH-2664 deferral
  discriminator entry per step 4.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/issues/deferred_triage.py:14` (`_REASON_RANK`) —
  upgrade from "no change" (see Dependent Files below) to a recommended
  update: extend with `low_readiness`/`gate_blocked`/`decision_unresolved` so
  the three new codes get intentional triage-priority ordering instead of
  silently falling back to `_DEFAULT_REASON_RANK` (lowest priority). Not
  required for correctness (confirmed no crash either way), but the issue's
  own consistency goal argues for it.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/issues/set_status.py:38-63`
  (`_status_updates()`) — reason-code-agnostic; no change needed, but is the
  function the new `--reason` values flow through.
- `scripts/little_loops/cli/issues/deferred_triage.py:14`
  (`_REASON_RANK`) — falls back gracefully for unranked codes; no change
  required, confirmed via research. (See Files to Modify above for a
  wiring-pass recommendation to extend it anyway.)
- `scripts/little_loops/loops/auto-refine-and-implement.yaml` — orchestrates
  both `autodev.yaml` and `rn-implement.yaml`; behavior change is internal to
  each loop's not-ready exits, no wiring change expected here but worth a
  smoke check.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/issues/show.py` — renders `deferred_reason`/
  `deferred_by`/`deferred_date` generically from frontmatter (line ~202,
  ~335, ~390 JSON key); no allowlist gate, so no code change needed, but new
  codes flow through this display path — confirmed via wiring pass.

### Similar Patterns
- `scripts/little_loops/loops/rn-implement.yaml:1330-1366` (`mark_deferred`
  state) — the exact template to mirror for autodev's three qualifying
  exits, including the `deferred_reason_<ID>.txt` sidecar consumed by
  `report` (1591-1607).

### Tests
- `scripts/tests/test_rn_implement.py` — `_load_loop()` helper (22-25) and
  `mark_deferred` state-shape assertions (~1022-1131) to model new autodev
  assertions after.
- `scripts/tests/test_builtin_loops.py` — `TestAutodevLoop` class (~3424),
  `data` fixture (~3429-3432), existing `mark_gate_blocked` test
  (~3712-3723) as the closest current autodev not-ready-exit test.
- Net-new: a cross-loop parity fixture (step 5) — no existing test asserts
  `autodev.yaml` and `rn-implement.yaml` produce matching lifecycles.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_set_status_cli.py` — "Deferral discriminator tests
  (ENH-2664)" section (~226-359). `test_set_status_deferred_stamps_automation_reason`
  (260-298) is the exact template to clone/parametrize for the three new
  reason codes (`low_readiness`, `gate_blocked`, `decision_unresolved`).
  `test_set_status_invalid_by_rejected` (336-359) is the pattern to follow
  for a new negative test (`test_set_status_invalid_reason_rejected`
  doesn't currently exist) proving stale/bogus `--reason` values are
  rejected by argparse `choices=`.
- `scripts/tests/test_autodev_decision_gate.py` — **will break**:
  `test_record_decision_unresolved_advances_queue_without_failing` (line
  624) hard-asserts `"autodev-decision-unresolved.txt" in action` (line
  632) and a `/ll:decide-issue` hint (line 636) on `record_decision_unresolved`'s
  action string. These must be updated once that state's action is replaced
  by a `set-status <ID> deferred --by automation --reason decision_unresolved`
  call. Docstrings at lines 426 and 468 (`TestDecidePathSpikeGate`) also
  describe `recheck_after_size_review`'s current ledger-write mechanism as
  "writing low_readiness" — reword once the mechanism becomes a status
  transition (the reason-code string itself is unaffected).
- `scripts/tests/test_builtin_loops.py` — additionally (beyond the
  `TestAutodevLoop`/`mark_gate_blocked` test already listed above),
  `test_mark_gate_blocked_advances_queue_without_failing` (~3712-3723)
  asserts `"autodev-gate-blocked.txt" in action` and
  `state.get("next") == "dequeue_next"` — will break/need updating if the
  ledger write is replaced rather than supplemented by the `set-status`
  call.
- `scripts/tests/test_issues_cli.py` — integration-level coverage for
  `set-status --by`/`--reason`; check whether the three new codes need a
  parallel assertion here in addition to the unit-level
  `test_set_status_cli.py` coverage above.
- **Scope flag (not a code change)**: `autodev.yaml`'s `skip_inflight` state
  (~line 160) also writes to `autodev-skipped.txt` with reason
  `"refine_failed"` — a fourth not-ready category not mentioned anywhere in
  this issue's Motivation/Implementation Steps. Confirm during
  implementation whether `refine_failed` is in-scope for step 1's
  reason-code mapping or deliberately excluded like the `decomposed` exits.

### Documentation
- `.claude/CLAUDE.md` § Issue File Format (deferral discriminator entry).
- `docs/guides/LOOPS_REFERENCE.md` — may warrant a note on the unified
  not-ready policy.

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md` (lines ~1150, ~1633-1634, ~1688-1705) — the
  `--reason <blocked_by_unmet|remediation_stalled>` help-text table row and
  the `deferred-triage`/`dt` command reference (including its
  `--format json` example) hardcode the current closed set of reason codes
  in prose, not generated from the enum; extend with `low_readiness`/
  `gate_blocked`/`decision_unresolved`.
- `docs/reference/API.md` (lines ~3714, ~3723-3726) — `deferred-triage`
  reference entry describes the same closed reason-code set as CLI.md.
- `docs/guides/ISSUE_MANAGEMENT_GUIDE.md` (lines ~127-128) — the
  deferral-stamping description is currently scoped to rn-implement's
  remediation circuit-breaker only; broaden (or cross-reference) to note
  autodev as a second automation-deferral producer once this issue ships.

## Impact

- **Priority**: P3 — consistency/cleanup; the acute drop is fixed by FEAT-2665.
- **Effort**: Medium.
- **Risk**: Medium — removes autodev's auto-retry for not-ready issues in favor
  of deferral; mitigated by requiring FEAT-2665 (triage surface) to land first.
- **Breaking Change**: No (behavioral alignment, documented).

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-07-18; re-verified 2026-07-18 —
FEAT-2665 blocker re-confirmed `done`, all cited line references re-checked
against current code, scores unchanged._

**Readiness Score**: 95/100 → PROCEED
**Outcome Confidence**: 68/100 → MODERATE

### Outcome Risk Factors
- Two secondary scope decisions remain open: whether `skip_inflight`'s
  `refine_failed` ledger exit (autodev.yaml ~line 160) is a fourth qualifying
  not-ready category alongside the three in scope, and whether the ledger
  files (`autodev-skipped.txt` etc.) are retired or kept as a same-run
  summary. Both are flagged in the issue body as an open question to resolve
  during step 1/step 3 — low blocking risk, but worth deciding upfront to
  avoid mid-implementation rework.
- Broad enumeration across roughly 13 change sites (loop YAML states, the
  `DeferReason` enum, the CLI `--reason` choices list, three test files, and
  four docs) — each site is templated/mechanical (mirrors `mark_deferred`
  closely), so per-site risk is low, but completion requires touching many
  files without missing one; the net-new cross-loop parity fixture (step 5)
  has no existing pattern to copy exactly.

## Session Log
- `/ll:confidence-check` - 2026-07-18T05:15:00Z - `e634cd43-9a17-411a-8d29-8448876726d3.jsonl`
- `/ll:decide-issue` - 2026-07-18T05:09:11 - `5558c7a3-aade-40dd-b6e2-1228b92927da.jsonl`
- `/ll:confidence-check` - 2026-07-18T00:00:00Z - `af7a2ca3-74d3-42ed-b8ca-3d1b31ba58a1.jsonl`
- `/ll:wire-issue` - 2026-07-18T05:03:57 - `3c07e49f-6e81-4014-85ac-10eda8641953.jsonl`
- `/ll:refine-issue` - 2026-07-18T04:58:22 - `2e2d89a6-dd70-473e-8d6b-264030f39eaf.jsonl`
- `/ll:capture-issue` - 2026-07-18T02:50:02Z

---

## Status

- **Current**: open
- **Last Updated**: 2026-07-18
