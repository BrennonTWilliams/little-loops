---
id: ENH-2992
status: open
priority: P2
captured_at: '2026-08-02T13:43:01Z'
discovered_date: 2026-08-02
discovered_by: capture-issue
relates_to:
- ENH-2995
- ENH-2993
confidence_score: 90
outcome_confidence: 45
score_complexity: 10
score_test_coverage: 25
score_ambiguity: 10
score_change_surface: 0
missing_artifacts: true
---

# Route reconcile-issue on contradiction, not only on readiness plateau

## Summary

`/ll:reconcile-issue` exists specifically to rewrite an issue's directive
sections when they contradict its own accumulated research findings. It is
almost never invoked: **1,703 issues have been refined, 19 have been
reconciled**. The gate that triggers it — `check_reconcile_needed` in
`autodev.yaml` — fires only on a *readiness-score plateau*, at most once per
issue. A contradiction that does not happen to stall the confidence score never
reaches the remedy. Reconcile is also absent from `/ll:refine-issue`'s own
pipeline diagram and Next Steps block, so no human path leads to it either.

Trigger reconcile on the condition it was built for — detected contradiction —
in addition to the existing plateau predicate.

## Current Behavior

`commands/reconcile-issue.md` states the problem it solves, verbatim:

> Over a long refine/spike/confidence-check cycle, `/ll:refine-issue` and
> `/ll:confidence-check` only **append** new "Codebase Research Findings"
> bullets — they never rewrite the issue's own Implementation Steps /
> Acceptance Criteria / Files to Modify to match.

But the only automated route in is `check_reconcile_needed`
(`scripts/little_loops/loops/autodev.yaml:1406-1458`), whose predicate is a
readiness plateau — the score failing to improve against a pre-refine snapshot
— and which is armed as a **one-shot per issue** via a `reconcile_attempted`
marker (`autodev.yaml:1418`). Secondary entries at `autodev.yaml:1684` and
`autodev.yaml:1964` are fallbacks from other states, not contradiction
detection.

Measured across `.issues/` (2026-08-02):

| Signal | Count |
|---|---|
| Issues with a `/ll:refine-issue` session-log entry | 1,703 |
| Issues with a `/ll:reconcile-issue` session-log entry | 19 |
| Issues whose research-findings blocks contain correction language | 316 |

So ~316 issues carry the exact condition reconcile was written to fix, and 19
have been through it.

Additionally, `/ll:refine-issue` never mentions reconcile:
- Pipeline diagram (`commands/refine-issue.md:791`):
  `capture-issue → format-issue → refine-issue → decide-issue → wire-issue → ready-issue → manage-issue`
- `## NEXT STEPS` output block (`commands/refine-issue.md:753-758`) lists
  decide-issue, wire-issue, ready-issue, manage-issue, and issue-size-review —
  not reconcile-issue.

A user who reads refine's own output has no way to learn reconcile exists.

## Expected Behavior

1. **Contradiction is a trigger.** When a refine (or confidence-check) pass
   deposits findings that refute a directive section, `check_reconcile_needed`
   routes to `reconcile_current` regardless of whether the readiness score
   plateaued.
2. **The one-shot arms per contradiction, not per issue.** A second, distinct
   contradiction discovered on a later pass is eligible for a second reconcile.
   (Retain a bounded cap so this cannot loop.)
3. **The human path exists.** refine-issue's pipeline diagram and Next Steps
   block name `/ll:reconcile-issue` when the pass emitted correction language.

## Motivation

The append-only design is deliberate and correct — it protects human prose.
Reconcile is the designed release valve. A release valve that opens 1% of the
time it is needed is a design that has one half installed. The cost is paid by
headless implementers reading contradictory directive sections (see ENH-2995
for the measured shape of that).

This is cheap to fix relative to its reach: the detection signal is already
being written into the issue in plain text by refine itself.

## Proposed Solution

Two changes, independent:

**A. Widen the automated gate.** In `check_reconcile_needed`
(`autodev.yaml:1406-1458`), add a contradiction predicate OR'd with the
existing plateau predicate. `commands/reconcile-issue.md` already supports
`--check`, which "report[s] the plateau verdict without writing, for FSM
evaluators" — extend or reuse that as the detection call so the predicate is
computed in Python rather than judged by an LLM (MR-1: this state needs a
non-LLM evaluator in its routing chain).

Detection candidates, cheapest first:
- A Python check over the issue's directive sections vs its
  `### Codebase Research Findings` blocks. This is plausibly a new
  `ll-issues` subcommand rather than prose in a skill —
  `ll-verify-skill-prose` will flag a prose reimplementation of a
  string-matching algorithm.
- If ENH-2995 lands first, the superseded markers it writes are a direct,
  unambiguous signal: presence of a marker in a directive section ⇒
  reconcile-eligible. Prefer this if available; it removes the heuristic
  entirely.

**B. Surface the human path.** In `commands/refine-issue.md`:
- Add reconcile to the pipeline diagram (line 791) at its real position —
  after refine, conditional.
- Add a Next Steps entry (lines 753-758): when this pass deposited findings
  that refute an existing directive section, run `/ll:reconcile-issue [ID]`.

Change B is independently shippable and near-zero-risk.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/autodev.yaml` — `check_reconcile_needed` state
  (lines 1406-1458): add the contradiction predicate; revisit the
  `reconcile_attempted` one-shot arming (line 1418)
- `commands/refine-issue.md` — pipeline diagram (line 791) and `## NEXT STEPS`
  output block (lines 753-758)
- `commands/reconcile-issue.md` — if `--check` is extended to report a
  contradiction verdict alongside the plateau verdict

### Dependent Files (Callers/Importers)
- TBD — use grep to find references

_Wiring pass added by `/ll:wire-issue`:_
- **Clarifying finding**: `commands/reconcile-issue.md`'s `--check` mode is
  documented as an FSM-evaluator contract (exit 0 = `NEEDED`, exit 1 = `CLEAN`)
  but currently has **zero callers** — `check_reconcile_needed` in
  `autodev.yaml` (~1406-1460) never invokes `/ll:reconcile-issue --check`; it
  runs a self-contained inline-Python predicate over `ll-issues show --json`
  snapshots instead. Proposed Solution's "extend `--check`" framing therefore
  means either (a) newly wiring a slash-command evaluator into
  `check_reconcile_needed` (bigger structural change than "widen the gate"),
  or (b) adding the contradiction predicate as a second inline-Python check
  alongside the existing one, leaving `--check`'s still-consumer-less contract
  untouched. Resolve this explicitly before implementation.
- `scripts/tests/test_autodev_loop.py` — `_run_reconcile_predicate()` helper
  (subprocess-execs the state's action) backs a `TestCheckReconcileNeeded*`
  suite; also `check_atomic_design_remedy`/selector tests (~439-455) that
  hardcode `reconcile_attempted` as a boolean gate in a **sibling** state, and
  `test_dispatcher_routes_pending_remedy_to_reconcile_current` (~657) — another
  routing edge into `reconcile_current` sharing the same one-shot guard.
- `scripts/tests/test_builtin_loops.py` (`TestAutodevLoop`, ~4127-6411) —
  structural assertions on `check_reconcile_needed`'s action/routing:
  `test_reconcile_states_exist` (5824), `test_check_reconcile_needed_fires_for_fresh_below_threshold`
  (5613, **will break** — pins the literal `"plateau or fresh_below"` boolean
  expression), `test_check_reconcile_needed_routes_through_guard2_verdict`
  (5152), `test_check_reconcile_needed_predicate_reads_snapshot_and_guard`
  (5846), `test_check_reconcile_needed_routing` (5860), `test_reconcile_current_invokes_reconcile_skill`
  (5870), `test_rerun_confidence_after_reconcile_routing` (5884),
  `test_recheck_after_size_review_arms_remedy_before_low_readiness` (5569),
  `test_recheck_after_size_review_measurement_gate_precedes_ambiguity_fallback`
  (5591), `test_pre_deferral_remedy_gate_routing` / `test_pre_deferral_remedy_dispatch_routing`
  (5544/5554) — all read `reconcile_attempted` as a sibling consumer.
- `scripts/tests/test_reconcile_issue_command.py` — `TestReconcileCheckModeCoverage`
  (159-181, slices between `"### 7. Check Mode Behavior"` and `"## Output Format"`)
  and `TestReconcileGuardAndOutput.test_arms_reconcile_attempted_guard` (64).
- `.ll/decisions.d/995f5144-debd-4e55-a188-b10445796f56.json` — existing
  decision-log entry already tracking this issue; close/annotate via
  `ll-issues decisions outcome` on completion.

### Similar Patterns
- `autodev.yaml:1684` and `autodev.yaml:1964` — existing fallback routes into
  `reconcile_current`; the new predicate should compose with these, not
  duplicate them
- FEAT-2751's `autodev-repair-cycle-count.txt` mechanism — the established
  pattern for bounding repeated repair-class attempts within a cycle; reuse it
  rather than inventing a new cap

### Tests
- TBD — identify test files to update. `scripts/tests/test_builtin_loops.py`
  holds the autodev structural test class.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_builtin_loops.py::TestAutodevLoop` — update
  `test_check_reconcile_needed_fires_for_fresh_below_threshold` (~5613, exact
  break — pins `"plateau or fresh_below"`), `test_check_reconcile_needed_predicate_reads_snapshot_and_guard`
  (~5846, extend to also assert the new contradiction marker), and
  `test_reconcile_states_exist` (~5824, add a name if a cap-tracking state is
  introduced). Routing pins (`test_check_reconcile_needed_routing` ~5860,
  `test_reconcile_current_invokes_reconcile_skill` ~5870,
  `test_rerun_confidence_after_reconcile_routing` ~5884) only break if
  `on_yes`/`on_no`/`next` targets themselves change.
- `scripts/tests/test_autodev_loop.py` — extend the `_run_reconcile_predicate()`-backed
  `TestCheckReconcileNeeded*` suite (~46-292) with cases exercising the new
  contradiction predicate independent of plateau; new test if the one-shot cap
  becomes a distinct counter state (follow the `count_repair_cycle_*` pattern
  used for FEAT-2751).
- `scripts/tests/test_reconcile_issue_command.py::TestReconcileCheckModeCoverage`
  (~159-181) — add assertions for a generalized contradiction verdict if
  `--check` is extended.
- New test needed (no existing coverage): `commands/refine-issue.md`'s
  pipeline diagram / NEXT STEPS block has zero test coverage today. Add a
  `("commands/refine-issue.md", "/ll:reconcile-issue", "ENH-2992")` tuple to
  `scripts/tests/test_wiring_skills_and_commands.py`'s `DOC_STRINGS_PRESENT`
  table (existing convention, e.g. line 26's ENH-1550 entry) to lock in
  Change B once shipped.

### Documentation
- TBD — docs that need updates

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_REFERENCE.md` — ASCII routing diagram (~1034-1035:
  `check_reconcile_needed → [pre-spike Readiness == post-spike AND NOT
  reconcile_attempted?] (ENH-2689)`) and the "Post-spike reconcile plateau
  (ENH-2689)" prose paragraph (~1051) both need a contradiction OR-branch
  clause and updated one-shot-arming description.
- `docs/reference/COMMANDS.md` — `### /ll:reconcile-issue` section (~279-292),
  specifically the `--check` flag line (~284) and "When to run" (~288).
- `.claude/CLAUDE.md` § Issue File Format — the FEAT-2751/ENH-2666/BUG-2803
  paragraph narrating `check_reconcile_needed`'s plateau predicate and
  stagnation backstop is the canonical mechanism narrative other issues layer
  onto; needs a companion clause for the contradiction branch.

### Configuration
- N/A

## Implementation Steps

TBD — requires codebase analysis

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

1. Resolve the `--check` wiring ambiguity first (see Dependent Files note
   above): decide whether the contradiction predicate becomes a second
   inline-Python check in `check_reconcile_needed` (matches today's
   zero-caller reality, lowest structural risk) or a genuinely-wired
   slash-command evaluator call to `/ll:reconcile-issue --check`.
2. Update `scripts/little_loops/loops/autodev.yaml`'s `check_reconcile_needed`
   state (~1406-1458) with the OR'd contradiction predicate, and revisit the
   `reconcile_attempted` one-shot arming (~1418) using the FEAT-2751
   `count_repair_cycle_reconcile` counter pattern for a bounded second-fire cap.
3. Update `commands/refine-issue.md` — pipeline diagram (~line 791) and
   `## NEXT STEPS` block (~lines 753-758) to name `/ll:reconcile-issue`.
4. Update `scripts/tests/test_builtin_loops.py::TestAutodevLoop` and
   `scripts/tests/test_autodev_loop.py` per the Tests subsection above —
   `test_check_reconcile_needed_fires_for_fresh_below_threshold` (~5613) will
   need its literal predicate string updated, not just extended.
5. Update `docs/guides/LOOPS_REFERENCE.md` and `docs/reference/COMMANDS.md`
   per the Documentation subsection above.
6. Add the new `DOC_STRINGS_PRESENT` entry to
   `scripts/tests/test_wiring_skills_and_commands.py` locking in Change B.
7. Update `.claude/CLAUDE.md` § Issue File Format's plateau-gate paragraph
   with the contradiction-branch clause.

## Impact

- Closes the loop between the problem refine creates and the skill built to
  fix it.
- Affects ~316 existing issues and every future refine pass.
- Change B alone makes reconcile discoverable to humans at zero risk.

## Success Metrics

- Reconcile invocation rate rises from 1% of refined issues to approximately
  the contradiction rate (~24%), without a corresponding rise in autodev
  cycle count per issue.
- `ll-loop validate autodev` stays clean — in particular MR-1 (the new
  predicate must have a non-LLM evaluator in its routing chain).

## Scope Boundaries

- Does **not** change what reconcile rewrites — its Contract section
  (rewrite-eligible vs preserve-untouched) is unchanged.
- Does **not** amend the Preservation Rule; that is ENH-2995.
- Does **not** make reconcile unbounded — a per-issue cap remains.

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `commands/reconcile-issue.md` | Defines the remedy and its `--check` mode |
| `scripts/little_loops/loops/autodev.yaml` | Contains the gate being widened |
| `.claude/CLAUDE.md` § Loop Authoring | MR-1 constrains the new predicate's evaluator |

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-08-02_

**Readiness Score**: 90/100 → PROCEED (overridden — see below)
**Outcome Confidence**: 45/100 → LOW

### Concerns
- `--check` wiring ambiguity is explicitly unresolved in the issue's own
  Dependent Files section: whether the contradiction predicate becomes a
  second inline-Python check (matches today's zero-caller reality) or a
  genuinely-wired `/ll:reconcile-issue --check` evaluator call. The issue says
  to "resolve this explicitly before implementation" but does not resolve it.
- Architecture Compliance is 15/20, not 20/20, for the same reason — the
  proposed solution names two structurally different implementations without
  picking one.

### Gaps to Address
- Program Design gate is armed (`.ll/program-design-cutover.json`, cutover
  2026-07-30) and this issue was captured 2026-08-02 — after cutover, so it is
  not grandfathered. `## Program Design` is absent. This is a **hard override**:
  regardless of the computed readiness score (90/100), the recommendation is
  **STOP — ADDRESS GAPS** until either a `## Program Design` section with
  concrete types/signatures/call path is added (run `/ll:refine-issue` or
  `/ll:reconcile-issue`), or `program_design_not_applicable: true` is set in
  frontmatter if genuinely inapplicable.

### Outcome Risk Factors
- Very wide blast radius on the routing edge being changed: 11+ existing tests
  across `test_builtin_loops.py`, `test_autodev_loop.py`, and
  `test_reconcile_issue_command.py` hardcode or pin the current
  `check_reconcile_needed` predicate string, routing targets, and the
  `reconcile_attempted` one-shot guard. Any change to the predicate or the
  one-shot arming risks breaking several of these simultaneously — verify each
  named test individually rather than relying on a single suite run to catch
  regressions.
- Ambiguity risk from the unresolved `--check` wiring decision (see Concerns)
  carries into implementation: picking the wrong option after starting could
  mean redoing the core state's structure.

## Session Log
- `/ll:refine-issue` - 2026-08-02T15:26:31 - `0a208318-6b67-47ba-88f1-23b17a2f5884.jsonl`
- `/ll:confidence-check` - 2026-08-02T15:25:07 - `cc770090-bce7-4043-b70f-eaa9a130277c.jsonl`
- `/ll:wire-issue` - 2026-08-02T15:21:04 - `ced002cf-1c4b-4fb0-81ad-841dca8598ba.jsonl`
- `/ll:refine-issue` - 2026-08-02T15:14:35 - `674c1fcd-abda-4e29-9d3f-07a624c63f75.jsonl`
- `/ll:issue-size-review` - 2026-08-02T13:48:44 - `14957793-c5a3-42c3-8c4e-e15ef7fbe208.jsonl`
- `/ll:capture-issue` - 2026-08-02T13:45:56 - `fac7dff4-61c1-4496-95b8-7bd1993d2971.jsonl`

## Status

- **Status**: open
