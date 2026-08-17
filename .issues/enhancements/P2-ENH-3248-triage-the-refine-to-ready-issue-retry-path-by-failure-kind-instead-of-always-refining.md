---
id: ENH-3248
type: ENH
title: Triage the refine-to-ready-issue retry path by failure kind instead of always
  refining
priority: P2
status: open
testable: true
discovered_by: ll-issues-create
discovered_date: '2026-08-17'
captured_at: '2026-08-17T19:30:10Z'
blocked_by:
- ENH-3244
relates_to:
- BUG-3245
- ENH-3238
depends_on: []
confidence_score: 75
outcome_confidence: 68
score_complexity: 14
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 18
---

# ENH-3248: Triage the refine-to-ready-issue retry path by failure kind instead of always refining

## Summary

`check_refine_limit` routes every gate failure to a single remedy, `refine_followup`
(`/ll:refine-issue --auto --gap-analysis`), which is additive-only. Two of the four gates that reach
it need content *removed* or *rewritten*, so their remedy is structurally incapable of clearing
them. Route by failure kind: deterministic normalize, then self-referential reconcile, then
re-research refine.

## Current Behavior

Four gates in `scripts/little_loops/loops/refine-to-ready-issue.yaml` route to `check_refine_limit`
(`:482-502`), which routes uniformly to `refine_followup` (`:177-191`):

| Gate | Line | Failure means | Needs | `--gap-analysis` can do it |
|---|---|---|---|---|
| `check_verify_verdict` | `:289-299` | claims don't match the codebase | re-research | ✅ |
| `check_readiness` | `:360-390` | confidence below threshold | re-research | ✅ |
| `check_hedges` | `:301-310` | unresolved hedges / template debris | answer or **delete** | ❌ |

`check_hedges` conflates two failure kinds today: it counts `count_open_questions_in_sections` +
`locate_unresolved_options` (`scripts/little_loops/cli/issues/check_open_questions.py:59-62`), and
`\bTBD\b` is still a term in `_OPEN_QUESTION_SIGNAL_RE`, so a literal template placeholder and a
genuine prose hedge are indistinguishable at the gate. ENH-3244 performs that split; this issue
cannot triage the two kinds apart before it lands (see Blocked By).
| `check_ac_automatable` | `:335-344` | manual-verification ACs | **rewrite ACs** | ❌ |

`refine_followup` is additive-only by contract (`:177-181`): *"Gap-analysis is additive-only (never
removes content) and does not consume max_refine_count."*

Observed on the ENH-3238 run
(`.loops/.history/2026-08-17T183652-refine-to-ready-issue/events.jsonl`, 27 routes):

```
refine_issue → wire_issue → verify_issue → VALID → check_hedges NO → hedge_attempts=1 → refine_followup
             → check_wire_done(=1) → verify_issue → VALID → check_hedges NO → hedge_attempts=2 → PROCEED
             → check_ac_automatable → confidence_check → done
```

`check_hedges` failed on template placeholders. Its remedy could not delete them. The retry produced
no improvement, `check_hedges` failed again, `check_hedge_attempts` hit its cap, and the loop
proceeded to `done` with the debris intact — plus new debris the additive retry itself created
(BUG-3245).

## Expected Behavior

A gate failure routes to a remedy capable of fixing that kind of failure, escalating cheapest-first:

```
normalize (deterministic, no LLM)  →  reconcile (self-referential)  →  refine (re-research)
```

- **Repairable structural debris** → `ll-issues format-check --fix --apply` (ENH-3247). No model.
  "Repairable" is not a judgment call: it is exactly the key set of `_REPAIR_DISPATCH`
  (`scripts/little_loops/cli/issues/format_check.py:281-286`) — `prose_dep_drift`,
  `duplicate_findings_block`, `duplicate_heading`, `empty_provenance_stub`. A gap class with no
  entry in that table is **not** routable to this rung.
- **Stale directive sections / non-automatable ACs** → `/ll:reconcile-issue` (ENH-3246). Reads the
  issue's own findings; no codebase research. Bounded by reconcile's own contract — see Decision
  Rules › Reconcile's mandate is the routing boundary.
- **Claim/codebase mismatch, low readiness** → `refine_followup`. Unchanged.
- **Missing/failing Program Design (BUG-3249's new `check_design` gate)** → `refine_followup`
  **directly**, skipping both cheaper rungs. See Decision Rules › Design-gap exception.
- **Template placeholders (ENH-3244's signal)** → split by what the placeholder *is*, not by where
  it sits. See Decision Rules › The placeholder class is two kinds:
  - **Derivable/deletable** (`[P0-P5]`, `[Small/Medium/Large]`, `[Low/Medium/High]`, `[Yes/No]`,
    `[YYYY-MM-DD]`) → `reconcile_issue` when inside reconcile's rewrite scope; `refine_followup`
    otherwise.
  - **Research-shaped** (`TBD - requires codebase analysis`, `TBD - use grep to find references`,
    `[Major phase 1]`, `[Verification approach]`, …) → `refine_followup` **directly**. These are
    *absent research*, structurally identical to the design gap; no deterministic or
    self-referential rung can produce their content.

A retry escalates to `refine_followup` only when the cheaper remedies cannot clear the gate — except
for the design-gap and research-shaped-placeholder kinds, where the cheaper rungs are
known-incapable rather than merely untried.

## Motivation

The uniform remedy is the defect — not the BUG-3170 cap, and not `--gap-analysis`, which is correct
for the two research-shaped failures. Half the triggers get a remedy that cannot fix them, so their
retry is guaranteed waste: it spends the shared refine budget, produces no progress toward the gate
it was invoked for, and (per BUG-3245) actively degrades the file.

Cost matters here. On the observed run `refine_issue` billed ~$0.65 and `refine_followup` ~$0.43,
against a total run cost of ~$2.53 for 22 minutes. A deterministic normalize is effectively free and
a reconcile pass is a bounded rewrite with no codebase research. Ordering cheapest-first converts the
most common failure kinds into the cheapest remedies.

## Proposed Solution

1. **Add a `normalize_structure` state** running `ll-issues format-check ${issue_id} --fix --apply`
   (ENH-3247). Deterministic, no LLM, unconditional after `refine_issue` / `refine_followup` /
   `wire_issue`. **It is a pass-through, not a gate**: `cmd_format_check` returns 1 whenever *any*
   gap remains — including the many classes `--fix` cannot repair (`format_check.py:398`,
   `:576-579`) — so its exit code carries no routing signal here. The action must therefore end in
   `|| true`, or `on_error` must point at the same successor as `next`; otherwise
   `executor.py:1834-1835` (a shell state with both `next:` and `on_error:` routes to `on_error` on
   non-zero exit) sends nearly every run down the error path. No `evaluate:`, no `on_yes`/`on_no`.
2. **Add a `reconcile_issue` state** invoking `/ll:reconcile-issue ${issue_id}`, with a
   `pruning_profile` matching the other slash-command states in this loop.
3. **Retarget the mismatched gates, by remedy capability**:
   - `check_ac_automatable.on_no` → `reconcile_issue` (ACs are in reconcile's unconditional rewrite
     list) instead of `check_refine_limit`.
   - ENH-3244's placeholder gate → `normalize_structure` **only for the gap classes present in
     `_REPAIR_DISPATCH`**, then `reconcile_issue` for derivable/deletable placeholders inside
     reconcile's rewrite scope, escalating to `check_refine_limit` if the gate still fails.
     Research-shaped placeholders route **straight to `check_refine_limit`** (Decision Rules › The
     placeholder class is two kinds).
   - `check_hedges`, post-ENH-3244, measures genuine prose hedges only. Those are answerable only by
     research, so its routing to `check_refine_limit` / `check_hedge_attempts` is **unchanged** —
     the earlier revision of this issue sent it to `normalize_structure`, which cannot clear it.
4. **Leave `check_verify_verdict` and `check_readiness` routing unchanged** — `refine_followup` is
   the correct remedy for both.
5. **Bound `reconcile_issue`** with a per-run attempt counter in `${context.run_dir}`, mirroring
   `check_refine_limit` (`:482-502`) and `check_hedge_attempts` (`:312-333`), so a gate a reconcile
   cannot clear escalates rather than spinning. **`normalize_structure` gets no counter**: it is
   deterministic, idempotent, and has no loopback into itself, so a counter would add a state and
   per-cycle steps for no bound.
6. **Raise `max_steps` 40 → 50**, with the arithmetic recorded in a comment as the file already does
   for ENH-3031 (`:38-43`) and BUG-3065 (`:44-51`). Budget: `normalize_structure` adds 1 step per
   refine/wire pass (≤3 passes = 3), and a `reconcile_issue` cycle costs ~6 (counter →
   `reconcile_issue` → `verify_issue` → the three gates), bounded at one cycle by its counter —
   ~9 over the BUG-3065 worst case, rounded to 50.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` — the two new states, the retargeted
  gates, the attempt counters, `max_steps`, and the routing-summary comment block (`:4-33`), which
  is maintained as documentation and must be updated to match.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/loops/refine-to-ready-issue.yaml:78-90` — `resolve_issue` initializes the
  per-run counter files; new counters must be initialized there too.
- `scripts/little_loops/loops/refine-to-ready-issue.yaml:606-766` — the `diagnose` /
  `write_failure_evidence` / `classify_terminal` chain enumerates captured states by name. New
  states with `capture:` must be added to those blocks or their failures will be invisible in the
  evidence file.
- `scripts/little_loops/loops/autodev.yaml` — nests this loop; a changed step budget and terminal
  behavior affect it. The `refine-broke-down` / `refine-terminal-class` artifacts it reads must keep
  their current meaning.
- `scripts/little_loops/fsm/validation/` — `ll-loop validate` must pass on the modified YAML.

### Similar Patterns
- `autodev.yaml:1557-1608` (`check_reconcile_needed`) and `:1921` (`reconcile_current`) — the
  existing reconcile call state, including its `pruning_profile` shape and one-shot guard. Model the
  new `reconcile_issue` state on it.
- `check_hedge_attempts` (`:312-333`) — the per-run attempt-counter idiom to mirror for the new
  bounds.

### Tests
- `scripts/tests/` — `ll-loop validate refine-to-ready-issue` exits 0 (MR-1..MR-14 plus routing
  reachability); every state named in the `diagnose` / `write_failure_evidence` blocks exists; the
  routing-summary comment matches the actual `on_yes`/`on_no` targets.
- A routing test asserting `check_ac_automatable.on_no` reaches `reconcile_issue` and that
  `check_verify_verdict.on_no`, `check_readiness.on_no`, and `check_hedges.on_no` all still reach
  `check_refine_limit` / `check_hedge_attempts` unchanged. Update
  `test_check_ac_automatable_state_routing` (`scripts/tests/test_builtin_loops.py:1630-1639`,
  currently asserting `on_no == "check_refine_limit"` at `:1637`) **in place**, matching how
  ENH-3031/BUG-3170 handled prior retargets.
- A test asserting `normalize_structure` carries no `evaluate:`/`on_yes`/`on_no` and cannot strand
  the run on a non-zero `format-check` exit — either its action ends in `|| true` or its `on_error`
  equals its `next` (Proposed Solution step 1).
- A test pinning the capability invariant: every gap class `normalize_structure` is routed to has a
  key in `format_check._REPAIR_DISPATCH`. This is the guard against re-introducing an incapable
  rung when a future gap class is added.

### Documentation
- The in-file routing summary (`:4-33`) is the authoritative description and must be updated.

### Configuration
- N/A — new counters are run-scoped files under `${context.run_dir}`, not config.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-17 — based on codebase analysis:_

- **Slash-command state shape in this file**: every existing slash-command state in `refine-to-ready-issue.yaml` (`refine_issue` `:157-175`, `wire_issue` `:231-239`, `verify_issue` `:279-287`, `breakdown_issue` `:550-566`) uses a plain shape — `action`, `action_type: slash_command`, `pruning_profile` (`name:` = skill-slug + mode suffix, e.g. `-repair`/`-auto`), `capture`, `next`, `on_error` — with no `on_yes`/`on_no`. Completion is read back afterward by a separate write-verdict/read-verdict gate state (`check_decision_mid_refine` `:193-204`, `check_verify_verdict` `:289-299`, explicitly named as "the write-verdict/read-verdict shape used throughout this file" in `check_verify_verdict`'s own comment `:290-294`).
- **Contested precedent for `reconcile_issue`**: `autodev.yaml`'s `reconcile_current` (`:1913-1929`, the state this issue's Similar Patterns cites as the model) additionally carries `fragment: with_rate_limit_handling` and `on_rate_limit_exhausted: done` — neither key appears on any existing state in `refine-to-ready-issue.yaml` itself. The two examples disagree on whether the new `reconcile_issue` state needs the rate-limit fragment/route or should follow the plainer file-native shape above.
- **Attempt-counter idiom**: a counter is a plain integer file under `${context.run_dir}`, initialized to `'0'` in `resolve_issue`'s single chained `mkdir -p ... && printf '0' > ... && ...` action (`:78-89`), then read-increment-write-echo'd by its own `action_type: shell` state with `capture:` and `evaluate: {type: output_numeric, operator: lt, target: N}` — see `check_hedge_attempts` (`:312-333`) and `check_refine_limit` (`:482-502`), which are structurally identical scripts.
- **Contested counter convention**: `autodev.yaml`'s `count_repair_cycle_reconcile` (`:1931-1966`, cited by this issue as the reconcile-bound model) layers a *shared* cross-repair-class counter on top of a scoped counter, guarded by a consume-once marker file. `refine-to-ready-issue.yaml`'s existing counters (`check_hedge_attempts`, `check_refine_limit`) are each single, independent, scoped counters with no shared backstop. This issue's Decision Rules (`:190-192`) commits only to "a per-run counter" per new state — it does not say whether the new counters need the shared-ceiling layering `autodev.yaml` uses.
- **Four-block registration order**: a capturing state gets one line appended (not inserted alphabetically) to each of `resolve_issue`'s init chain, `diagnose`'s prompt bullets (`:630-637`), `write_failure_evidence`'s three per-state sub-blocks — exit codes, `classify_failure` verdicts, and (only for the highest-signal states, currently `refine_issue`/`refine_followup`/`breakdown_issue`) a stderr-tail block (`:676-712`) — and `classify_terminal`'s two `for` loops (`:750-763`). No test enforces the four blocks' relative order, but every existing entry follows roughly the order states are first reached on the happy path.
- **`max_steps` comment convention**: each budget change gets its own comment block directly above `max_steps:`, shaped `# <ISSUE-ID>: <old> -> <new>.` followed by prose naming the added states/routes, their per-cycle step cost, the worst-case new total, and why the added cycle cannot spin — appended below prior entries, never replacing them. Evidence: the ENH-3031 and BUG-3065 blocks at `:38-51`.
- **Routing-test convention**: one test class per loop file in `scripts/tests/test_builtin_loops.py` (`TestRefineToReadyIssueSubLoop`, `:1366-1374`), with a `data` fixture that `yaml.safe_load`s the file directly (no FSM executor) and asserts `state.get("on_yes")`/`state.get("on_no")` via plain dict comparison. `test_check_ac_automatable_state_routing` (`:1630-1639`) currently asserts `check_ac_automatable.on_no == "check_refine_limit"` — retargeting that route means updating this existing assertion in place, matching how prior retargets (ENH-3031/BUG-3170) updated rather than duplicated it. `check_hedge_attempts` has its own counter-test pattern (`_run_check_hedge_attempts` helper `:1590-1597`, executes the state's bash `action` via `subprocess.run` against a `tmp_path` run_dir; see `test_check_hedge_attempts_counts_up_and_gates_at_two` `:1599-1615` and `test_check_hedge_attempts_counter_is_per_run` `:1617-1628`) — the model for testing the new attempt counters this issue adds.
- **MR rule scope**: MR-1..MR-6 (`scripts/little_loops/fsm/validation/meta_rules.py:1-5`) fire only on loops whose state `action` strings match meta-loop patterns (editing `loops/*.yaml`, `skills/*/SKILL.md`, `agents/*.md`, `commands/*.md`, `.claude/CLAUDE.md`). `refine-to-ready-issue.yaml`'s states act on `.issues/` files only (per its own `scope:` block `:35-37`), so MR-1..MR-6 do not fire on this file regardless of the new states added. The broadly-applicable checks relevant to this change live in `scripts/little_loops/fsm/validation/reachability.py` (capture-reachability — relevant to wiring the new states' `capture:` into `diagnose`/`write_failure_evidence`) and `shell_safety.py` (MR-9 shell over-escaping — relevant to the new bash counter states).

## Program Design

### Call Path

`check_ac_automatable` -> `reconcile_current` -> `cmd_format_check`

- `check_ac_automatable` (`refine-to-ready-issue.yaml:335-344`) currently routes `on_no` to
  `check_refine_limit`; retargeted to the new `reconcile_issue` state.
- `reconcile_current` (`scripts/little_loops/loops/autodev.yaml:1921`) is the existing reconcile call
  state whose shape the new state copies.
- `cmd_format_check` (`scripts/little_loops/cli/issues/format_check.py:383`) backs the new
  `normalize_structure` state via `--fix --apply` (ENH-3247), dispatching through
  `_REPAIR_DISPATCH` (`:281-286`).

### Decision Rules

- **Escalation order**: deterministic → self-referential → re-research. Never invoke a more expensive
  remedy before a cheaper one that can address the same failure kind.
- **Remedy-capability match**: a gate routes to a remedy only if that remedy can perform the
  operation the failure requires (delete / rewrite / research). This is the invariant the current
  design violates.
- **Design-gap exception: cheapest-first is subordinate to remedy-capability.** BUG-3249 adds a
  `check_design` gate to this loop. Its failure kind routes **straight to `refine_followup`**, not
  through `normalize_structure` or `reconcile_issue`. This is not a violation of the escalation order
  — it is the capability rule taking precedence, and two completed issues make it a fact rather than
  a judgment call:
  - **BUG-3002** (done) — *"autodev routes `design_gate_failed` to reconcile-issue, whose contract
    excludes the Program Design section"*. Reconcile **cannot** write `## Program Design`. Sending a
    design-gap failure down the reconcile rung re-creates a bug that was already fixed once.
  - **BUG-3001** (done) — *"refine-issue never populates `## Program Design` despite being the
    prescribed remedy for the gate"*. Now fixed, so refine is the capable remedy.

  A missing design section is *absent research*, not *stale or malformed text*, so no deterministic
  normalize and no self-referential rewrite can produce it. Generalized: **the ladder is ordered by
  cost only among remedies that are capable; an incapable rung is skipped, not tried.**
- **The placeholder class is two kinds.** ENH-3244 emits one signal (`placeholder_count` /
  `template_placeholders`) over a literal-string list, but that list mixes two failure kinds and
  they take different rungs:
  - *Derivable/deletable* — `[P0-P5]`, `[Small/Medium/Large]`, `[Low/Medium/High]`, `[Yes/No]`,
    `[YYYY-MM-DD]`. The correct value is already determinable from the issue itself, so a
    self-referential rewrite suffices → `reconcile_issue`, subject to the mandate boundary below.
  - *Research-shaped* — `TBD - requires codebase analysis`, `TBD - use grep to find references`,
    `[Major phase 1]`, `[Verification approach]`. These are **absent research**, exactly the shape
    the design-gap exception covers. No deterministic normalize and no self-referential rewrite can
    produce their content → straight to `check_refine_limit`.
- **`normalize_structure`'s eligible set is `_REPAIR_DISPATCH`'s keys, nothing more.**
  `format-check --fix` repairs `prose_dep_drift`, `duplicate_findings_block`, `duplicate_heading`,
  and `empty_provenance_stub` (`format_check.py:281-286`) — and ENH-3244 ships **detection only**,
  adding no repair function for placeholders. Routing a gate to this rung without a matching
  `_REPAIR_DISPATCH` entry re-commits the exact defect this issue exists to fix: a remedy
  structurally incapable of clearing the gate that invoked it. If a future issue wants placeholders
  deterministically normalized, the capable owner is either a new `_REPAIR_DISPATCH` entry or
  `/ll:format-issue --auto` (the skill that owns template structure) — **not** today's
  `format-check --fix`.
- **Reconcile's mandate is the routing boundary.** `commands/reconcile-issue.md` binds the rewrite
  to `## Implementation Steps`, `## Acceptance Criteria`, the whole `## Integration Map`, plus a
  conditional `## Scope Boundaries` carve-out and `⚠ Superseded` marker clearing. Debris outside
  those sections — a placeholder in `## Summary`, `## Current Behavior`, or `## Impact` — is
  **out of contract**, so routing it to `reconcile_issue` produces a no-op pass. Only failures
  located inside the rewrite scope take this rung; everything else escalates.
- **Escalation is mandatory, never discretionary**: `reconcile_issue` is bounded by a per-run counter and
  falls through to `check_refine_limit`, so a failure the cheap remedies cannot fix still reaches
  refine and ultimately `breakdown_issue`. `normalize_structure` is a counter-free pass-through
  (Proposed Solution step 5) — it never loops back into itself, so it needs no bound.
- **Unchanged routing**: `check_verify_verdict` and `check_readiness` keep `refine_followup`.

### Signatures
- `cmd_format_check(config: BRConfig, args: argparse.Namespace) -> int` — backs the new
  `normalize_structure` state; defined at `scripts/little_loops/cli/issues/format_check.py:383`.
  Returns 1 when **any** gap remains, fixable or not (`:398`, `:576-579`), so its exit code is
  **not** a usable gate signal for this state — see Proposed Solution step 1 for the
  pass-through shape that requires.
- `_REPAIR_DISPATCH: dict[str, Callable]` — the gap-class → repair-function table at
  `scripts/little_loops/cli/issues/format_check.py:281-286`. Its key set is the authoritative
  definition of what `normalize_structure` can clear.

## Implementation Steps

1. ENH-3247 (`format-check --fix` structural repairs) and ENH-3246 (widened reconcile mandate) are
   both `done`. **ENH-3244 is still open and is a hard prerequisite** — without it there is no
   placeholder signal to route and `\bTBD\b` remains in the hedge regex, so `check_hedges` cannot
   be triaged apart from placeholders. See Blocked By.
2. Add `normalize_structure` (pass-through shape, step 1) and `reconcile_issue` states with
   `capture:` and pruning profiles.
3. Initialize the `reconcile_issue` attempt counter in `resolve_issue`. No counter for
   `normalize_structure`.
4. Retarget `check_ac_automatable.on_no` and the placeholder path per the capability split; leave
   `check_hedges`, verify, and readiness routing untouched.
5. Add the new states to the `diagnose`, `write_failure_evidence`, and `classify_terminal` blocks.
6. Recompute `max_steps` and update the routing-summary comment.
7. `ll-loop validate refine-to-ready-issue` exits 0; add the routing tests.
8. `python -m pytest scripts/tests/` exits 0.

## Impact

- **Priority**: P2 - Eliminates a guaranteed-waste retry for half the gates that trigger one, and
  cuts cost by matching remedy to failure. Not P1: the loop still terminates correctly today, just
  with unfixed debris and a wasted pass.
- **Effort**: Medium - two states, counter plumbing, four enumeration blocks to keep in sync,
  `max_steps` arithmetic, and validation. The FSM's diagnose/evidence blocks make every state
  addition wider than it first appears.
- **Risk**: Medium - routing changes in a 40-step FSM with a stall-detection circuit
  (`circuit.repeated_failure`, `:72-75`). New cycles risk phantom convergence if the attempt
  counters are wrong. Mitigated by mirroring the existing counter idiom and by `ll-loop validate`.
- **Breaking Change**: No - external artifacts (`refine-broke-down`, `refine-terminal-class`) keep
  their meaning.

## Scope Boundaries

**This does not fix the substantive-error class.** ENH-3238's two real defects — a wrong edit site
and a wrong generated-file claim — required *probing the codebase*, which only `verify_issue` does.
No amount of retry triage catches them; that is ENH-3238's subject. This issue is about not wasting
a pass on failures the retry cannot fix.

**Not touching BUG-3170's cap.** The cap on genuine prose hedges is correct and stays. This issue
changes what a retry *does*, not how many are allowed.

**Not making `--gap-analysis` destructive.** Its additive-only contract is deliberate and is what
makes it safe to run repeatedly. Removal capability comes from the other two remedies.

## Blocked By

- `ENH-3244` — supplies the `placeholder_count` / `template_placeholders` signal this issue's
  placeholder routing consumes, and removes `\bTBD\b` from `_OPEN_QUESTION_SIGNAL_RE`. Until it
  lands, `check_hedges` conflates placeholders with prose hedges (`check_open_questions.py:59-62`)
  and there is no distinct signal to triage. Previously listed only as `relates_to`; promoted to a
  hard edge because Proposed Solution step 3 routes a gate that does not yet exist.

Previously blocked on `ENH-3246` (reconcile permitted to rewrite the Integration Map subsections)
and `ENH-3247` (`format-check --fix` able to repair structural debris) — both now `done`; see
Related Issues.

## Related Issues

- ENH-3244 — **supplies the placeholder signal this triage routes, and nothing more** (now a hard
  `blocked_by`; see Blocked By). ENH-3244 is detection-only by decision: it adds the `format-check`
  gap class and JSON key — **no repair function**, so its class is absent from `_REPAIR_DISPATCH`
  and is not normalize-clearable — and this issue owns every `refine-to-ready-issue.yaml` edit. Both
  previously proposed adding a gate to that file, which would have been a merge collision in the
  same sprint wave.
- BUG-3249 — adds the `check_design` gate to this loop. Sequenced **after** this issue, and its
  failure kind takes the design-gap exception in Decision Rules (straight to `refine_followup`).
- BUG-3245 — removes the debris the current additive retry creates.
- BUG-3001, BUG-3002 (both done) — the evidence behind the design-gap exception.
- ENH-3238 — the run that surfaced this.
- ENH-3246, ENH-3247 (both done) — the former blockers; see Blocked By.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._


## Blocks

- BUG-3249
- ENH-3250

## Status

**Open** | Created: 2026-08-17 | Priority: P2


## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-08-17_

**Readiness Score**: 75/100 → STOP — ADDRESS GAPS (hard override; would otherwise be PROCEED WITH CAUTION)
**Outcome Confidence**: 68/100 → MODERATE

### Concerns
- `blocked_by: ENH-3244` is still `open`, not `done`/`cancelled` — Implementation Steps itself
  calls it "a hard prerequisite": without it there is no `placeholder_count` signal to route and
  `\bTBD\b` remains in the hedge regex, so `check_hedges` cannot be triaged apart from placeholders.

### Gaps to Address
- Land ENH-3244 (split template-placeholder detection out of the hedge scan) before the
  placeholder-routing split (Proposed Solution step 3) has a signal to consume.

### Outcome Risk Factors
- Moderate complexity: the change is concentrated in one file
  (`scripts/little_loops/loops/refine-to-ready-issue.yaml`) but touches many distinct locations
  (two new states, two retargeted gates, counter init, four enumeration blocks, `max_steps`
  arithmetic), with real risk of phantom convergence against the existing
  `circuit.repeated_failure` stall detector if the new attempt counters are wired incorrectly.

## Session Log
- `/ll:confidence-check` - 2026-08-17T23:16:18 - `650587c4-5e3f-4515-a253-8c3aba6c3210.jsonl`
- `/ll:refine-issue` - 2026-08-17T22:57:39 - `383f19f2-e8c0-43aa-9cdd-d1c166fe7608.jsonl`
- `/ll:confidence-check` - 2026-08-17T21:35:01 - `878d0e98-a6e4-41e7-80a9-53a56e3db6f7.jsonl`
- `/ll:audit-issue-conflicts` - 2026-08-17T20:25:54 - `fe71c380-6bd8-44e2-9c73-d0617456c6e4.jsonl`
- `/ll:audit-issue-conflicts` - 2026-08-17T20:13:03 - `ffec4b47-4ed9-4eda-baf1-3dc49ac82fa1.jsonl`
- `/ll:capture-issue` - 2026-08-17T19:29:38 - `3ce34465-00fd-4ba7-a470-b61774849ebd.jsonl`
