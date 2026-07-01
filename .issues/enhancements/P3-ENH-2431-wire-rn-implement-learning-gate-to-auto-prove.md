---
id: ENH-2431
title: Wire `rn-implement`'s pre-dequeue learning gate to auto-prove instead of dead-ending
type: ENH
priority: P3
status: open
captured_at: '2026-07-01T19:10:34Z'
discovered_date: '2026-07-01'
discovered_by: capture-issue
depends_on:
- ENH-2430
relates_to:
- ENH-2406
- ENH-2319
labels:
- learning-tests
- rn-implement
- automation
confidence_score: 95
outcome_confidence: 78
score_complexity: 21
score_test_coverage: 22
score_ambiguity: 15
score_change_surface: 20
---

# ENH-2431: Wire `rn-implement`'s pre-dequeue learning gate to auto-prove instead of dead-ending

## Summary

`ENH-2430` adds a target-addressed `ll-learning-tests prove <target>` verb,
but adding the verb doesn't by itself change `rn-implement`'s behavior —
something still has to call it. This issue is the actual behavior change:
make `check_learning_ready`/`mark_learning_blocked`
(`scripts/little_loops/loops/rn-implement.yaml:464,1063`) attempt proving via
the new verb before giving up, closing the automation-coverage regression
described in `ENH-2430`'s Current Behavior (an unproven target now dead-ends
`rn-implement` at a terminal `mark_learning_blocked` state with no same-run
re-enqueue, requiring a manual `/ll:explore-api` + re-run round-trip that the
pre-ENH-2406 baseline didn't need).

## Current Behavior

`check_learning_ready` only ever calls `ll-learning-tests check <target>
--stale-aware` (`rn-implement.yaml:495-560`). On any unproven target it
routes to `mark_learning_blocked`, which is terminal (`next: dequeue_next`,
no re-enqueue) and just logs the `LEARNING_GATE_BLOCKED_PRE_DEQUEUE` tag with
a "prove with /ll:explore-api" message. Nothing in `rn-implement` ever
attempts to resolve the target itself.

## Expected Behavior

On an unproven target, before routing to the terminal blocked state,
`rn-implement` calls `ll-learning-tests prove <target>` (from `ENH-2430`) for
each unproven target. If proving succeeds, continue to `check_depth` as
though the target had always been proven. If proving still fails (refuted or
still unresolved), route to `mark_learning_blocked` as today — the terminal
path remains for genuinely un-provable targets.

## Motivation

Closes the gap `ENH-2430` documents: `rn-implement` is currently *less*
automated than the pre-ENH-2406 baseline for issues that fail the cheap
pre-dequeue check, since the in-`ll-auto` auto-proving choke point
(`ENH-2319`) is unreachable once `mark_learning_blocked` terminates the run.
This wiring restores that capability at the point where it's cheapest to
apply it (pre-dequeue, before any remediation budget is spent) rather than
only inside `ll-auto --only`.

## Proposed Solution

1. Extend `check_learning_ready`'s Python heredoc (`rn-implement.yaml:495`)
   so that, instead of just collecting unproven targets, it optionally
   attempts `ll-learning-tests prove <target>` per unproven entry — gated by
   a context flag (working name `auto_prove_learning_gate`, mirroring the
   existing `skip_learning_gate` knob's shape) so callers can opt in/out
   without changing the default fail-open-to-block behavior until this has
   run in practice.
2. Settle the open design question `ENH-2430`'s Scope Boundaries left
   unresolved: does this default on, default off, or is it unconditional
   with no flag? Recommend defaulting **off** initially (opt-in via the new
   context flag) so budget-conscious callers aren't surprised by
   `rn-implement` spawning proving agents on every cold-registry issue;
   revisit defaulting on once real usage data exists.
3. Update `mark_learning_blocked`'s reason text/tag to distinguish
   "attempted-and-still-unproven" from "not-attempted" outcomes in
   `failures.txt`, so `report`'s tallies stay diagnostic.
4. Update `docs/guides/RECURSIVE_LOOPS_GUIDE.md` and
   `docs/guides/LOOPS_REFERENCE.md`'s `rn-implement` gate-order sections
   (already touched by `ENH-2406`) to describe the new auto-prove branch.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **No new FSM states needed**: unlike `ENH-2406` (which added
  `check_blocked_by` + `route_blocked_by`, +2 states), this change lives
  entirely inside `check_learning_ready`'s existing Python heredoc
  (`rn-implement.yaml:495-560`) — the per-target loop at lines 547-556 gains a
  prove-attempt branch, while `route_learning_ready` (`:573-583`) and
  `mark_learning_blocked` (`:1063-1086`) keep their existing shape (only
  `mark_learning_blocked`'s reason text changes, per step 3).
  `test_state_count_is_orchestrator_sized`
  (`scripts/tests/test_rn_implement.py:587`) should **not** need a count bump
  for this issue.
- **Timeout mismatch to watch**: the existing per-target `check` subprocess
  call (`rn-implement.yaml:549-552`) uses `timeout=30`, fine for a cheap
  registry read. `ll-learning-tests prove <target>` (`ENH-2430`) internally
  runs `ll-loop run proof-first-task` — an LLM-driven proving loop that can
  run for minutes. Reusing `timeout=30` for the new `prove` call would
  spuriously kill in-progress proving; size the new subprocess call's timeout
  independently rather than copying the `check` call's constant.
- **Prior art for target-addressed proving**: `run_learning_gate_for_issue()`
  (`scripts/little_loops/learning_tests/gate.py:76-123`) is the
  issue-addressed sibling this issue's target-addressed `prove` call
  parallels — it already shells to `ll-loop run proof-first-task --context
  issue_file=<path>` and reads the terminal state via `_read_loop_final_state`
  (`gate.py:59-73`). `ENH-2430`'s `prove` verb wraps the same underlying
  mechanism; this issue only needs to call the resulting CLI, not touch
  `gate.py` directly.
- **Reason-text precedent for step 3**: `mark_learning_blocked` already
  distinguishes gate sites via a tag suffix rather than reusing an existing
  tag (`LEARNING_GATE_BLOCKED_PRE_DEQUEUE` vs. `record_learning_gate_blocked`'s
  plain `LEARNING_GATE_BLOCKED`, comment at `rn-implement.yaml:1071-1073`) —
  the new attempted-vs-not-attempted axis should follow the same
  additive-suffix idiom rather than introducing an unrelated tag scheme.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in
the implementation:_

5. Update the `report` state's grep-based tally logic (`rn-implement.yaml`)
   so `LEARNING_GATE_BLOCKED_TOTAL - LEARNING_GATE_BLOCKED_PRE_DEQUEUE` and
   the `summary.json` keys stay correct once step 3's tag split lands —
   either a third counting bucket, or keep both new tag variants as
   substring supersets of `LEARNING_GATE_BLOCKED_PRE_DEQUEUE`
6. Review/update `scripts/tests/test_builtin_loops.py::TestLearningGateConsistency`
   (`test_rn_implement_pre_dequeue_tag_does_not_double_count`,
   `test_rn_implement_record_state_tags_and_advances`) alongside the
   `test_rn_implement.py` changes from step 3
7. Correct `skills/explore-api/SKILL.md`'s stale "CLI Surface Reminder"
   subcommand table (currently omits `orphans`/`prove`)

## API/Interface

```
ll-loop run rn-implement <issue> --context auto_prove_learning_gate=1
```

- `auto_prove_learning_gate` (context flag, default unset/off): when set,
  `check_learning_ready` (`rn-implement.yaml:495`) attempts
  `ll-learning-tests prove <target>` for each unproven target before routing
  to `mark_learning_blocked`, mirroring the existing `skip_learning_gate`
  knob's shape (`rn-implement.yaml:37-38,489`) but opt-in rather than
  opt-out.
- No new CLI-level flag — this is an FSM `context.*` parameter passed via
  `--context` to `ll-loop run rn-implement`, same mechanism as
  `skip_learning_gate`.
- `mark_learning_blocked`'s emitted tag/reason text gains a second axis
  (attempted-and-still-unproven vs. not-attempted) so `report`'s
  `failures.txt` tallies stay diagnostic; exact tag values are an
  implementation detail of Proposed Solution step 3.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/rn-implement.yaml` — `check_learning_ready`
  (`rn-implement.yaml:495`) gains the gated auto-prove branch;
  `mark_learning_blocked` (`rn-implement.yaml:1063`) reason text/tag
  distinguishes attempted-and-still-unproven from not-attempted

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/loops/rn-implement.yaml` — the `report` state's
  grep-based tally logic (`LEARNING_GATE_BLOCKED_PRE_DEQUEUE` /
  `LEARNING_GATE_BLOCKED_TOTAL` counters and the `summary.json` keys
  `learning_gate_blocked` / `learning_gate_blocked_pre_dequeue`) must be
  updated alongside `mark_learning_blocked`'s tag split from step 3 — either
  add a third counting bucket for the attempted-vs-not-attempted axis, or
  keep both new tag variants as substring supersets of
  `LEARNING_GATE_BLOCKED_PRE_DEQUEUE` so the existing subtraction arithmetic
  (`LEARNING_GATE_BLOCKED_TOTAL - LEARNING_GATE_BLOCKED_PRE_DEQUEUE`) doesn't
  silently double-count or drop the split [wiring pass finding]
- `skills/explore-api/SKILL.md` — "CLI Surface Reminder" section
  (~lines 234-244) states `ll-learning-tests` exposes only `check`/`list`/
  `mark-stale` and explicitly denies a further subcommand; already stale
  against the real 5-subcommand CLI (`check`, `list`, `mark-stale`,
  `orphans`, `prove`) and becomes more consequential once `rn-implement`
  calls `prove` directly — correct the subcommand table [wiring pass finding]

### Dependent Files (Callers/Importers)
- `ll-learning-tests prove <target>` (`ENH-2430`) — the verb this issue's new
  branch calls; blocked on that issue shipping first
- `report`'s `failures.txt` tally reader — consumes `mark_learning_blocked`'s
  reason/tag text (Proposed Solution step 3)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/loops/ready-to-implement-gate.yaml` — the sub-loop
  `ll-learning-tests prove <target>` shells to internally (per `cmd_prove` in
  `scripts/little_loops/cli/learning_tests.py`). This is a **different**
  sub-loop chain than `mark_learning_blocked`'s sibling remediation-time gate,
  which uses `proof-first-task` via `run_learning_gate_for_issue()`
  (`gate.py:76-123`) — no direct edit needed here, but implementers should
  not conflate the two chains when tracing behavior [wiring pass finding]

### Similar Patterns
- `skip_learning_gate` context flag (`rn-implement.yaml:37-38,489`) — shape
  the new `auto_prove_learning_gate` flag mirrors (opt-in here vs. that
  knob's opt-out)

_Wiring pass added by `/ll:wire-issue`:_
- `.ll/decisions.yaml`'s standing rule (~line 3376-3384) — "a context
  variable added at A must be explicitly threaded into each inner call" —
  was established for `skip_learning_gate`'s `rn-implement` → `rn-remediate`
  threading and is checked by
  `test_rn_implement_threads_skip_to_remediate` (`test_builtin_loops.py`).
  `auto_prove_learning_gate` deliberately does **not** follow this pattern:
  it's consumed entirely inside `check_learning_ready`'s own heredoc (a
  pre-dequeue check) and is never threaded to `run_remediation`. Call this
  divergence out explicitly during implementation/review so it isn't
  mistaken for a missed threading step [wiring pass finding]

### Tests
- `scripts/tests/test_rn_implement.py` — add coverage for
  `check_learning_ready`'s auto-prove branch (flag on/off, prove
  succeeds/fails) and `mark_learning_blocked`'s updated reason/tag text

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_builtin_loops.py::TestLearningGateConsistency` —
  `test_rn_implement_pre_dequeue_tag_does_not_double_count` and
  `test_rn_implement_record_state_tags_and_advances` assert the literal
  `LEARNING_GATE_BLOCKED_PRE_DEQUEUE` substring in both
  `mark_learning_blocked`'s action and `report`'s tally arithmetic — review
  and update alongside the tag-text change from step 3 [wiring pass finding]

#### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `scripts/tests/test_rn_implement.py:870` — `TestLearningReadyGate` is the
  existing test class to extend. Existing tests likely needing updates
  alongside new ones: `test_check_learning_ready_short_circuits_on_skip_flag`,
  `test_route_learning_ready_routes_on_unproven`,
  `test_mark_learning_blocked_uses_distinct_tag` — all assert against the raw
  parsed YAML action text / routing dict via the file's `_load_loop()` helper
  rather than live FSM execution; new tests should follow the same
  string/dict assertion style.

### Documentation
- `docs/guides/RECURSIVE_LOOPS_GUIDE.md`, `docs/guides/LOOPS_REFERENCE.md` —
  see Related Key Documentation below

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LEARNING_TESTS_GUIDE.md` — "Using Learning Tests in Loops" /
  Gate Entry Points table (~lines 178-226) already lists
  `ready-to-implement-gate`, `assumption-firewall`, `proof-first-task`, etc.
  as gate entry points; add `rn-implement`'s pre-dequeue gate as a new
  `prove`-consumer entry once this issue ships [wiring pass finding]

### Configuration
- N/A

## Success Metrics

- With `auto_prove_learning_gate=1` set and a target `ll-learning-tests
  prove` can resolve, `rn-implement` no longer terminates at
  `mark_learning_blocked` (`rn-implement.yaml:1063`) — it proceeds to
  `check_depth` in the same run.
- With the flag unset (default) or a target `prove` can't resolve, behavior
  is unchanged: routes to `mark_learning_blocked` exactly as today.

## Scope Boundaries

- Blocked on `ENH-2430` shipping the `prove` verb first — this issue only
  covers the `rn-implement.yaml` wiring and the flag/default decision.
- Out of scope: changing `ll-auto`/`ll-sprint`/`ll-parallel`'s existing gate
  behavior — unaffected by this issue.
- Out of scope: retrying/looping proof attempts within a single run beyond
  one attempt per unproven target — a target that fails proving once still
  routes to the terminal `mark_learning_blocked` path.

## Impact

- **Priority**: P3 — same tier as `ENH-2406`/`ENH-2430`; closes an
  automation gap with a known manual workaround.
- **Effort**: Small — one gated branch in an existing FSM state, plus a
  flag-default decision; no new subprocess mechanics (those live in
  `ENH-2430`).
- **Risk**: Low–Medium — changes default behavior of a gate on the primary
  automated-implementation path if the flag defaults on; recommend
  defaulting off to keep risk low at first landing.
- **Breaking Change**: No.

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `docs/guides/RECURSIVE_LOOPS_GUIDE.md` | Documents `rn-implement`'s gate order (touched by `ENH-2406`); needs an update describing the new auto-prove branch |
| `docs/guides/LOOPS_REFERENCE.md` | Documents `rn-implement`'s gate order (touched by `ENH-2406`); needs an update describing the new auto-prove branch |

## Labels

`learning-tests`, `rn-implement`, `automation`

## Confidence Check Notes

_Updated by `/ll:confidence-check` on 2026-07-01 (supersedes the 2026-07-01T19:35:00Z run below)_

**Readiness Score**: 95/100 → PROCEED
**Outcome Confidence**: 78/100 → MODERATE

The prior blocking gap is resolved: `ENH-2430` shipped (commit `84298f5f`,
status `done`) and `ll-learning-tests prove <target>` is present and
functional in the CLI (verified via `ll-learning-tests --help` and reading
`cmd_prove` in `scripts/little_loops/cli/learning_tests.py`). No gaps remain
that block starting implementation. The two previously-noted open specifics
(the `auto_prove_learning_gate` default and the exact attempted-vs-not tag
text) are non-blocking — the issue already gives a strong recommendation
(default off) and an established suffix idiom to follow, so they're
resolvable during implementation rather than pre-conditions.

## Session Log
- `/ll:confidence-check` - 2026-07-01T20:30:00Z - `9f72aea4-af69-42bd-a3f6-ecb65eb7d68f.jsonl`
- `/ll:wire-issue` - 2026-07-01T20:08:16 - `71fbe4b5-3dfe-4d6b-85d7-58fab369564d.jsonl`
- `/ll:confidence-check` - 2026-07-01T19:35:00Z - `825773cc-f3c3-4e72-b818-2f6802981cbb.jsonl`
- `/ll:refine-issue` - 2026-07-01T19:26:03 - `f533de3e-378e-4044-a87e-70e8db7623de.jsonl`
- `/ll:format-issue` - 2026-07-01T19:17:23 - `02a6a246-e204-434b-b8fb-b3ee17de8fac.jsonl`
- `/ll:capture-issue` - 2026-07-01T19:10:34Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4e438ec0-2ef6-4d50-87d6-3f113b79ec61.jsonl`

## Status

**Open** | Created: 2026-07-01 | Priority: P3
