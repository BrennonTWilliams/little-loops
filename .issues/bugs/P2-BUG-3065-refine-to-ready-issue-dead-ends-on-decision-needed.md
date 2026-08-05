---
id: BUG-3065
title: refine-to-ready-issue dead-ends on decision_needed instead of resolving it
type: BUG
priority: P2
status: open
discovered_by: capture-issue
discovered_date: 2026-08-05
captured_at: '2026-08-05T20:05:24Z'
relates_to:
- BUG-3063
- BUG-2528
- BUG-1366
- BUG-2595
- BUG-1416
- ENH-2443
- ENH-2446
- FEAT-937
labels:
- loops
- fsm
- decision-gate
testable: true
decision_needed: false
---

# BUG-3065: `refine-to-ready-issue` dead-ends on `decision_needed` instead of resolving it

## Summary

`refine-to-ready-issue.yaml` has three `decision_needed` gates that all route `on_yes: done`. That
routing is a **sub-loop handoff contract** — exit clean, let a parent loop run `/ll:decide-issue`,
then re-enter. The contract no longer has a counterparty: nothing invokes `refine-to-ready-issue`
as a sub-loop today. Run it on an issue whose refine pass sets `decision_needed: true` and it exits
`done` after four states, having silently skipped `/ll:wire-issue`, `/ll:verify-issues`, and
`/ll:confidence-check` — with no signal to the operator that the readiness pipeline never ran.

## Steps to Reproduce

1. Pick an issue whose `/ll:refine-issue --auto` pass deposits competing options and sets
   `decision_needed: true` (observed on BUG-3063).
2. `ll-loop run refine-to-ready-issue BUG-3063`
3. Observe the run reports `Loop completed: done` — a success terminal.
4. `ll-issues show 3063` — `History:` lists only `/ll:refine-issue, /ll:capture-issue`; no wire, no
   confidence scores.

Observed trace (`.loops/.history/2026-08-05T193536-refine-to-ready-issue/events.jsonl`):

```
resolve_issue → check_epic_id (no) → check_lifetime_limit (yes)
  → refine_issue → check_decision_mid_refine (yes) → done
```

## Current Behavior

Three gates exit via `done` on `decision_needed: true`:

| State | Location | Introduced by |
|-------|----------|---------------|
| `check_decision_mid_refine` | `scripts/little_loops/loops/refine-to-ready-issue.yaml:171-181` | BUG-2528 |
| `check_decision_mid_wire` | `scripts/little_loops/loops/refine-to-ready-issue.yaml:211-221` | BUG-2528 |
| `check_decision_needed` | `scripts/little_loops/loops/refine-to-ready-issue.yaml:369-378` | BUG-1366 |

Each was correct when `auto-refine-and-implement` invoked `refine-to-ready-issue` as a sub-loop.
That caller switched to `recursive-refine` (CHANGELOG.md:2697), and `recursive-refine` does not
resolve the decision either — its own `check_decision_needed`
(`scripts/little_loops/loops/recursive-refine.yaml:556-568`) **skips the issue entirely**, appending
it to `recursive-refine-skipped-decision.txt`. Only `autodev.yaml` carries `run_decide` machinery.

Net effect: a `decision_needed` issue dead-ends in both loops, and the operator must notice the
truncated run and invoke `/ll:decide-issue` by hand.

## Expected Behavior

`refine-to-ready-issue` resolves the decision inline and continues to wire + confidence, so a single
`ll-loop run refine-to-ready-issue <ID>` drives the issue to ready without operator intervention.

`/ll:decide-issue --auto` is fully autonomous — `skills/decide-issue/SKILL.md` documents `--auto` as
"Non-interactive mode: write decision without prompting" — and `rn-remediate.yaml:635` already calls
it inline as a plain `slash_command` state. There is precedent; nothing about the decision requires
a human.

Ordering must match `autodev`: decide **before** wire/confidence, so the confidence score is computed
against the resolved decision rather than the ambiguity the decision removes (`autodev` routes
`run_decide` → `rerun_confidence_after_decide`, `autodev.yaml:679`).

## Motivation

Two loops silently under-deliver on their stated contract. `refine-to-ready-issue`'s own description
is "Drives a single issue from backlog to ready-state" — it reports `done` having done roughly a
third of that. The failure is invisible: a success terminal, no warning, no skip ledger. The cost is
paid by the operator every time, and only if they happen to check `ll-issues show` afterward.

## Proposed Solution

### The naive fix is wrong

`check_decision_mid_refine.on_yes: run_decide` → `check_wire_done` reintroduces regressions this
repo has already paid for:

- **BUG-1416 / BUG-2595** — `decide-issue` silently no-ops when `## Proposed Solution` holds no
  enumerable options, leaving `decision_needed` armed. The issue then scores confidence against
  unresolved ambiguity, or reaches `/ll:manage-issue` Phase 2.3 and halts there with its failure
  misclassified.
- **ENH-2443** — which is precisely why `autodev` guards `run_decide` on *both* sides.

### The correct cluster (~5 states)

Liftable near-verbatim from `autodev.yaml`:

| # | State | Source | Role |
|---|-------|--------|------|
| 1 | `check_decision_decidable` | `autodev.yaml:529-548` | Marker short-circuit, then `ll-issues check-open-questions \|\| ll-issues check-decidable` — deterministic non-LLM decidability probe. ENH-2446 chains open-questions first to catch the mixed case (resolved options + free-form open questions). |
| 2 | `deposit_options` | `autodev.yaml:550-565` | Bounded single retry via `/ll:refine-issue --auto` to deposit Option A/B/C blocks. |
| 3 | `record_options_deposited` | `autodev.yaml:567-573` | Write-once marker preventing infinite deposit↔decide cycles. |
| 4 | `run_decide` | `autodev.yaml:610-624` | `/ll:decide-issue --auto`, `pruning_profile: decide-issue-auto`. |
| 5 | `assert_decision_cleared` | `autodev.yaml:685-697` (BUG-2595) | Re-verify the flag *after* decide; still-armed means decide no-opped. |

All three `refine-to-ready-issue` gates retarget their `on_yes` to the cluster entry.

Step budget is fine: `max_steps: 30` (refine-to-ready-issue.yaml:31) against a ~12-state happy path.

### Decision needed: how to share the cluster

FSM fragments **cannot** express this. `scripts/little_loops/fsm/fragments.py` merges a named partial
state definition into exactly one state (module docstring lines 1-29; `_deep_merge` at line 43) — a
5-state cluster has no fragment representation. So:

**Option A — duplicate the cluster into `refine-to-ready-issue`.**
Smaller, self-contained, no `autodev` changes. Cost: two copies of a guard cluster whose every state
exists because of a distinct prior bug (BUG-1416, BUG-2595, ENH-2443, ENH-2446) — exactly the kind of
logic that must not drift. FEAT-937 (shared fragment libraries for cross-loop state reuse) exists
because this class of duplication is already recognized as a problem.

**Option B — extract as a sub-loop, and convert `autodev` to call it.**

> **Selected:** Option B — extract as a sub-loop — matches the proven `oracles/` sub-loop precedent (`verify-confidence-scores`) and eliminates the drift risk that duplication (Option A) has already caused once (BUG-1416/BUG-2595).

Invoke via a `loop:` state — the shape `confidence_check` already uses at
`refine-to-ready-issue.yaml:277-289` (`loop: oracles/verify-confidence-scores` with `with:` params).
Both loops call one implementation; drift is structurally impossible.

The seam is clean because the cluster core (probe → deposit → decide → assert) is caller-agnostic;
only **terminal routing** differs:

- `autodev` on failure → `record_decision_unresolved` (`autodev.yaml:700-724`), which defers the
  issue via `ll-issues set-status ... --reason decision_unresolved` and dequeues the next one.
- `refine-to-ready-issue` on failure → exit via `done`.

So the sub-loop should return success/failure and let each caller own its terminal routing. The
differing capture names (`autodev`'s `${captured.input.output}` vs `refine-to-ready-issue`'s
`${captured.issue_id.output}`) are already handled by sub-loop `with:` params.

**Recommendation: Option B.** The `autodev` conversion is the point, not incidental overhead — it is
what prevents a second copy of five bug-fix-derived guards from drifting out of sync.

### Decision Rationale

**Selected: Option B — extract as a sub-loop, and convert `autodev` to call it.**

Codebase evidence from two parallel `ll:codebase-pattern-finder` passes:

- **Option A (duplicate)** is mechanically consistent with the codebase's *current* de facto
  pattern — the same cluster is already duplicated between `autodev.yaml` and
  `rn-remediate.yaml`, with manual "parity" cross-reference comments. But that existing 2-copy
  duplication is the documented cause of a real shipped bug (BUG-1416, surfaced via BUG-2595) and
  two dedicated remediation issues (ENH-2443, ENH-2446). A third copy in
  `refine-to-ready-issue.yaml` extends a pattern the codebase has already had to patch around, not
  one it treats as safe.
- **Option B (sub-loop)**'s mechanism — `with:` params, `done`/`failed` terminal contract,
  `oracles/<name>` path resolution, caller-side `on_success`/`on_failure` routing — is not
  speculative; it is the exact pattern already running in production for `confidence_check` in
  `refine-to-ready-issue.yaml` (`loop: oracles/verify-confidence-scores`). `fsm/executor.py`'s
  `_execute_sub_loop` (~line 820) confirms full support for this contract. `fsm/fragments.py` was
  independently confirmed to have no construct for importing a multi-state cluster, ruling out a
  lighter-weight fragment-based alternative for either option.

| Option | Consistency | Simplicity | Testability | Risk | Total |
|---|---|---|---|---|---|
| A — duplicate cluster | 1 | 2 | 2 | 1 | 6/12 |
| B — extract sub-loop | 3 | 2 | 1 | 1 | 7/12 |

Option B scores higher on Consistency — the deciding dimension per the tiebreaker rule — because
its sub-loop mechanics are a proven, already-precedented pattern, whereas Option A's duplication
is a pattern the codebase has already been burned by. Option B's lower Testability score reflects
real near-term cost: `scripts/tests/test_autodev_decision_gate.py` (1211 lines) asserts exact
inline state names and ordering for the cluster inside `autodev.yaml`, and extracting the cluster
into a sub-loop will require rewriting those assertions — a cost the issue's own "Behavior Parity"
table already scopes for, and one paid once rather than compounding with every future drift the
duplicated copy would risk.

## Integration Map

### Files to Modify

- `scripts/little_loops/loops/refine-to-ready-issue.yaml` — retarget the three `decision_needed`
  gates' `on_yes` from `done` to the decision cluster/sub-loop call.
- `scripts/little_loops/loops/autodev.yaml` — (Option B) replace the inline cluster at lines 529-573,
  610-624, 685-697 with a `loop:` call; keep `record_decision_unresolved` as autodev's own terminal
  routing.
- `scripts/little_loops/loops/oracles/` — (Option B) new sub-loop YAML for the decision cluster.

### Behavior Parity

Option B delegates `autodev.yaml`'s inline decision cluster to a sub-loop. Every behavior below
must survive the move — each exists because of a named prior bug.

| Behavior (autodev.yaml) | Artifact | Status |
|---|---|---|
| Marker short-circuit skips re-validation once options were deposited (`:539-542`) | sub-loop | Preserved |
| `check-open-questions \|\| check-decidable` probe order (ENH-2446, `:543-544`) | sub-loop | Preserved |
| `deposit_options` bounded single retry via `/ll:refine-issue --auto` (`:550-565`) | sub-loop | Preserved |
| Write-once `autodev-decide-options-deposited` marker (`:567-573`) | sub-loop | Preserved — marker path must move to the sub-loop's `run_dir` (context_passthrough) |
| `run_decide` `/ll:decide-issue --auto` + `decide-issue-auto` pruning profile (`:610-624`) | sub-loop | Preserved |
| `assert_decision_cleared` post-decide flag re-verify (BUG-2595, `:685-697`) | sub-loop | Preserved |
| `check_decision_after_decide_error` short-circuit on still-armed flag (ENH-2717, `:627-640`) | autodev | Preserved — stays caller-side (routes to autodev's own terminal) |
| `mark_decide_ran` → `autodev-decide-ran` marker consumed by `decide_current` (ENH-1415) | autodev | Preserved — autodev-specific queue state, not part of the cluster contract |
| `record_decision_unresolved` defer + `DECISION_UNRESOLVED` ledger (`:700-724`) | autodev | Preserved — caller-side terminal routing; `auto-refine-and-implement.yaml:840` reads this ledger |
| `rerun_confidence_after_decide` re-score after decide (`:679`) | autodev | Preserved — caller-side |
| `fragment: with_rate_limit_handling` / `on_rate_limit_exhausted` on `run_decide` + `deposit_options` | sub-loop | **Changed** — rate-limit handling must be re-expressed at the sub-loop level; verify `on_rate_limit_exhausted: done` semantics still reach the caller |

### Dependent Files (Callers/Importers)

- `scripts/little_loops/loops/auto-refine-and-implement.yaml` — consumes autodev's
  `DECISION_UNRESOLVED` ledger (line 840); must keep working after the autodev refactor.
- `scripts/little_loops/loops/rn-remediate.yaml:635` — independent inline `/ll:decide-issue` call;
  a candidate future consumer, out of scope here.

### Similar Patterns

- `scripts/little_loops/loops/recursive-refine.yaml:556-568` — same dead-end, skips instead of
  resolving. **Follow-up, not a requirement of this issue.**

### Tests

- TBD — identify the loop-validation/topology tests covering `refine-to-ready-issue` and `autodev`
  routing; `ll-loop validate` must pass for both after the change.

### Documentation

- `CHANGELOG.md`
- TBD — check whether `docs/` documents the decision-gate handoff contract.

### Configuration

- N/A

## Program Design

The deliverable is loop YAML, not Python — no new modules, types, or functions. What the design
must pin down is which *existing* engine path the change rides on, and the sub-loop's terminal
contract.

### Types

- `StateConfig.loop: str` — sub-loop reference, already carried on the state (the field
  `confidence_check` sets at `refine-to-ready-issue.yaml:278`)
- `StateConfig.with_: dict[str, str]` — sub-loop params, how `issue_id` crosses the boundary
  regardless of each caller's local capture name

### Signatures

- `_execute_sub_loop(self, state: StateConfig, ctx: InterpolationContext) -> str | None`
  (`scripts/little_loops/fsm/executor.py:820`) — the existing engine entry point Option B uses;
  unchanged by this issue, listed because its capture shape constrains the contract
- `resolve_loop_path(name_or_path: str, loops_dir: Path) -> Path`
  (`scripts/little_loops/fsm/loop_paths.py:19`) — resolves `oracles/<decision-cluster>`

Sub-loop terminal contract: `done` = `decision_needed` cleared; `failed` = still armed after
decide (caller routes its own recovery).

### Call Path

`_execute_sub_loop` → `resolve_loop_path` → the decision-cluster loop

At the YAML layer, both callers enter that engine path from their existing gates:
`refine-to-ready-issue.check_decision_mid_refine` and `autodev.check_decision_after_refine` →
sub-loop → `check_wire_done` / (`rerun_confidence_after_decide` | `record_decision_unresolved`).

## Implementation Steps

1. Resolve the Option A / Option B decision (`/ll:decide-issue BUG-3065`).
2. (Option B) Extract the decision cluster from `autodev.yaml` into a sub-loop under
   `scripts/little_loops/loops/oracles/`, parameterized by issue id via `with:`.
3. (Option B) Convert `autodev.yaml` to call the sub-loop, preserving `record_decision_unresolved`
   routing and the `DECISION_UNRESOLVED` ledger `auto-refine-and-implement.yaml:840` reads.
4. Retarget all three `refine-to-ready-issue` gates to the cluster, ordered before wire/confidence.
5. Verify: `ll-loop validate` on both loops; re-run `ll-loop run refine-to-ready-issue BUG-3063` and
   confirm it proceeds through wire + confidence rather than exiting at 5 states.

## Impact

- **Priority**: P2 — silent under-delivery on two loops' core contract, with a success terminal
  masking it. Not P1: a workaround exists (run `/ll:decide-issue` manually) once the operator knows.
- **Effort**: Medium — Option A is small; Option B adds a sub-loop extraction plus an `autodev`
  conversion touching a heavily-guarded routing path.
- **Risk**: Medium — `autodev`'s decision cluster encodes five distinct prior bug fixes; the
  refactor must preserve every guard and the `DECISION_UNRESOLVED` ledger contract.
- **Breaking Change**: No

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `.claude/CLAUDE.md` | § Loop Authoring — meta-loop rules and `ll-loop validate` enforcement |
| `docs/ARCHITECTURE.md` | FSM loop execution and sub-loop invocation model |

## Session Log
- `/ll:decide-issue` - 2026-08-05T20:38:36 - `e519a35e-42e1-44db-b9f7-ccbf4a7b1a4e.jsonl`
- `/ll:capture-issue` - 2026-08-05T20:06:47 - `69895b45-2950-4e3c-a99c-2ecfbf7e5e1f.jsonl`

## Status

- [ ] Not started
