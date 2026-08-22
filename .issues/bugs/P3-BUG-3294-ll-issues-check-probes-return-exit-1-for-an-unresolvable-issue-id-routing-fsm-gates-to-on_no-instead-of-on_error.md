---
id: BUG-3294
type: BUG
title: ll-issues check-* probes return exit 1 for an unresolvable issue ID, routing
  FSM gates to on_no instead of on_error
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-08-22'
decision_needed: false
size: Medium
relates_to:
- BUG-3278
- BUG-3293
captured_at: '2026-08-22T20:37:10Z'
labels:
- cli
- fsm
- exit-codes
- issues
confidence_score: 100
outcome_confidence: 52
score_complexity: 9
score_test_coverage: 18
score_ambiguity: 25
score_change_surface: 0
---

# BUG-3294: ll-issues check-* probes return exit 1 for an unresolvable issue ID, routing FSM gates to on_no instead of on_error

## Summary

Every `ll-issues check-*` probe returns exit **1** when the issue ID cannot be resolved — the same
code it returns for a genuine negative verdict. Under the FSM `shell_exit` evaluator
(`fsm/evaluators.py:255-259`: 0→`on_yes`, 1→`on_no`, 2+→`on_error`), an unresolvable ID is therefore
indistinguishable from a real "no" and routes to the remediation branch instead of the error branch.

Verified across all seven probes (2026-08-22): `check-decidable`, `check-open-questions`,
`check-design`, `check-flag`, `check-acceptance-criteria`, `check-verify-verdict`,
`check-readiness` — all `return 1` on not-found.

This is a **family-wide convention, not a one-command slip**, which is what makes it worth filing:
**BUG-3278 part 4 deliberately breaks it** for its new `check-unresolved-decisions` (exit 2 for
not-found), citing this exact routing hazard. Once that lands, the new command is the only member
of the family with the correct behavior, and the convention is silently inconsistent.

## Current Behavior

```
$ ll-issues check-decidable 999999
Error: Issue '999999' not found.
$ echo $?
1
```

The same code as a real negative:

```
$ ll-issues check-decidable 3293
OPTIONS_MISSING: 3293 — decision_needed is true but no enumerable alternatives were found ...
$ echo $?
1
```

Consumers can only distinguish the two by parsing stderr, which no FSM gate does — `shell_exit`
branches on the exit code alone.

Concrete routing today: `resolve-decision.yaml`'s `check_decision_decidable` (`:47-67`) chains
`check-open-questions || check-decidable`, with `on_no: deposit_options`. A typo'd or renumbered
issue ID therefore reaches `deposit_options` — "run `/ll:refine-issue --auto` to deposit option
blocks" — on an issue that does not exist. `on_error: run_decide` is never taken.

**Severity is bounded, and should be stated honestly rather than inflated.** In this instance the
detour is marker-bounded to one retry before falling through to `run_decide`, so the failure mode
is a wasted pass and a misleading log line, not a stall. The general hazard is not bounded by
anything in the CLI layer, though — it depends on each caller having independently added a bound,
and there are 44 `ll-issues check-*` gate invocations across 6 loop files
(`check-flag` 18, `check-readiness` 7, `check-design` 7, `check-verify-verdict` 5,
`check-open-questions` 3, `check-decidable` 2, `check-acceptance-criteria` 2). Each would need
auditing to know whether its `on_no` branch is safe to reach with a nonexistent issue.

## Expected Behavior

An unresolvable issue ID exits with a code that routes to `on_error`, not `on_no` — exit **2**,
matching the divergence BUG-3278 part 4 specifies for `check-unresolved-decisions` and the
`fsm/evaluators.py` contract. A genuine negative verdict keeps exit 1.

Exit **3** must be avoided throughout: `shell_exit` does not set `abstain_on_exit_3`, so 3 lands on
`on_error` today but is reserved for the abstain semantics and would change meaning if a caller
ever enabled it.

## Motivation

These probes exist to give FSM loops a deterministic, non-LLM verdict. A probe that cannot say "I
could not evaluate this" is not deterministic in the way its callers assume — it silently converts
an infrastructure failure (bad ID, deleted file, renamed issue) into a substantive verdict about
issue content, and the loop then acts on that verdict.

The failure is invisible by construction: the loop takes a plausible branch, does plausible
remediation work, and logs nothing that reads as an error. That is the same silent-miss shape as
BUG-3293 and BUG-3278 — the pipeline proceeds confidently on a fact it never established.

BUG-3278 part 4 already reasoned this through for one new command and wrote the divergence into its
spec. Filing this makes the rest of the family reachable rather than leaving a single inconsistent
outlier behind.

## Proposed Solution

Change the not-found return from 1 to 2 across the seven probes, and document the convention.

**This is a behavior change to a shared CLI contract, so it needs an audit, not just a
find-and-replace.** Before changing any of them:

1. Enumerate every consumer of each probe — the 44 loop gate sites above, plus any skill or script
   shelling out to them.
2. For each, determine what `on_error` does today. A caller whose `on_error` routes to `failed`
   will start failing on a bad ID where it previously did remediation — which is the *point*, but
   it is a live behavior change in loops that currently "work."
3. Land the exit-code change and the caller review together.

**Sequencing against BUG-3278.** That issue's `check-unresolved-decisions` should ship with exit 2
regardless — it is new, so it has no callers to audit and no back-compat surface. This issue then
brings the existing seven into line. Landing in the other order is also fine; they do not conflict.

**`check-flag` scope — decided.** `check-flag` is in scope. See § *Program Design → Decision
Rules* for the selected option and rationale.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-22 — based on codebase analysis:_

- The stated precedent, `check-unresolved-decisions` (BUG-3278 part 4), has not landed: `scripts/little_loops/cli/issues/check_unresolved_decisions.py` is absent from disk, and BUG-3278 is still `status: open`. Its spec (BUG-3278 lines 314-348) describes the exit-2 divergence as an inline `if path is None: ... return 2` at the same resolution guard the other seven probes already use for `return 1` — Implementation Step 4 there says "Model on `check_open_questions.py`, diverging on the exit codes," i.e. copy-and-diverge, not extract-and-share. There is no shared helper or landed code to import from; each of the seven probes will get its own inline literal change.
- No `EXIT_*` constant, enum, or shared exit-code helper exists anywhere in `cli/issues/` or `fsm/` today — every exit code in every one of the seven probes is a raw inline `return N`. The not-found guard is identical across all seven: `_resolve_issue_id(...) is None` → `print(f"Error: Issue '{id}' not found.", file=sys.stderr)` → `return 1` (sites: check_decidable.py:32,52; check_open_questions.py:56,81; check_design.py:36,39; check_flag.py:29,33; check_acceptance_criteria.py:102,118; check_verify_verdict.py:84,97,107,118; check_readiness.py:140,142).

_Added by `/ll:refine-issue` — 2026-08-22 — based on codebase analysis:_

- No shared "resolve-or-exit" helper/decorator exists for the `_resolve_issue_id(...) is None` guard across `cli/issues/`; every one of the seven probes re-implements the check-and-return inline after importing `_resolve_issue_id` from `show.py` (evidence: `check_decidable.py:26-32`, `check_open_questions.py:47-56`, `check_flag.py:23-29`). BUG-3278's own spec for the new sibling command states the same method explicitly — "Model on `check_open_questions.py`, diverging on the exit codes" — i.e. copy-and-diverge, not extract-and-share, is the codebase's stated convention even for a brand-new file in this family.
- Recent family-wide fixes in this codebase extract a new shared function only when the underlying data model changes (e.g. BUG-3278's `DecisionGroup`/`locate_unresolved_decisions`), not to deduplicate a repeated exit-code literal. No precedent exists for extracting a helper purely to unify this guard.
- No iterable registry exists for the check-* subcommand family to drive a parametrized guard test: `cli/issues/__init__.py:1015-1029` dispatches via a flat `if`-chain, not a data structure a test could introspect. The nearest analog, `test_builtin_loop_hardcode_gate.py` (glob-derived parametrize + hand-maintained `_EXEMPT` set), does not transfer directly — a family-wide guard test here needs a hand-maintained subcommand list, mirroring that file's `_HARDCODE_PATTERNS` tuple.
- Named exit-code constants do exist elsewhere in the codebase — `fsm/types.py:17-25` (`FAILURE_TERMINAL_EXIT_CODE = 2`) and `cli/loop/_helpers.py:69-80` (`EXIT_CODES: dict[str, int]`) — but the FSM evaluator this issue targets, `evaluate_exit_code()` (`fsm/evaluators.py:238-264`), itself compares against bare literals with no named constant for 0/1/2/3, and none exists anywhere in `cli/issues/` today.

## Integration Map

### Files to Modify

- `scripts/little_loops/cli/issues/check_decidable.py` — not-found return (`:30-32`)
- `scripts/little_loops/cli/issues/check_open_questions.py` — not-found return
- `scripts/little_loops/cli/issues/check_design.py` — not-found return
- `scripts/little_loops/cli/issues/check_acceptance_criteria.py` — not-found return
- `scripts/little_loops/cli/issues/check_verify_verdict.py` — not-found return
- `scripts/little_loops/cli/issues/check_readiness.py` — not-found return
- `scripts/little_loops/cli/issues/check_flag.py` — not-found return (in scope — see § *Program Design → Decision Rules*)

Each resolves the ID via `_resolve_issue_id` from `cli/issues/show.py`, so the shape of the change
is identical in all seven.

### Dependent Files (Callers/Importers)

- `scripts/little_loops/loops/` — 44 `ll-issues check-*` gate invocations across 6 files; each
  `on_error` branch needs review per *Proposed Solution* step 2
- `scripts/little_loops/loops/oracles/resolve-decision.yaml:47-67` — the worked example above
- `scripts/little_loops/fsm/evaluators.py:255-259` — the `shell_exit` polarity this issue is
  written against; **unchanged**

_Wiring pass added by `/ll:wire-issue`:_

- The 6 loop files are confirmed by name (issue text did not enumerate them):
  `scripts/little_loops/loops/autodev.yaml`, `refine-to-ready-issue.yaml`, `rn-remediate.yaml`,
  `spike-gate.yaml`, `recursive-refine.yaml`, `oracles/resolve-decision.yaml`.
- **Routing-divergence table** (`on_no` vs `on_error` target differs — a real behavior change once
  not-found starts reaching `on_error`; states where they match are routing-inert):

  | Loop file | State | on_no | on_error |
  |---|---|---|---|
  | autodev.yaml:601-609 | `check_passed` | `triage_outcome_failure` | `detect_children` |
  | refine-to-ready-issue.yaml:346-353 | `check_verify_verdict` | `check_evidence_unverified` | `check_hedges` |
  | refine-to-ready-issue.yaml:399-408 | `check_hedges` | `check_hedge_attempts` | `check_placeholders` |
  | refine-to-ready-issue.yaml:462-469 | `check_ac_automatable` | `check_reconcile_limit` | `confidence_check` |
  | refine-to-ready-issue.yaml:471-482 | `check_design` | `check_refine_limit` | `confidence_check` |
  | oracles/resolve-decision.yaml:58-67 | `check_decision_decidable` | `deposit_options` | `run_decide` |
  | oracles/resolve-decision.yaml:196-204 | `assert_decision_cleared` | `done` (terminal, success) | `failed` (terminal, failure) — highest-impact: a not-found ID currently terminates this sub-loop as **success** |

- **New failure mode — states with no `on_error` at all** (an "error" verdict has no route today
  per `fsm/executor.py:2776-2792`, which returns `None` rather than falling back to `on_no`; these
  never received a nonzero-but-not-1 exit before, so the gap was latent):
  `autodev.yaml:611` `decide_current`, `autodev.yaml:1393` `check_missing_artifacts`,
  `spike-gate.yaml:34` `check_spike_needed`, `spike-gate.yaml:42` `check_spike_completed`.
- `skills/confidence-check/SKILL.md:141` — a non-loop caller: `ll-issues check-design ... && echo "" || echo "yes"`. Bash `&&`/`||` already collapses any nonzero to the same branch, so this site is confirmed **convergent** (no behavior change) — included for audit completeness since it sits outside the "44 loop gate sites" the audit scope names.
- `scripts/little_loops/cli/issues/locate_options.py:36` — a related but **out-of-scope** CLI command (not one of the seven) whose own test docstring (`test_issues_locate_options.py:5,181`) explicitly asserts parity with "check-decidable's contract" on exit 1 for not-found. Once the seven move to exit 2, this file becomes the new single inconsistent outlier the Motivation section warns about — flagged for awareness, not added to *Files to Modify* since it is outside this issue's named family.

### Tests

- Per-command CLI test asserting exit **2** on an unresolvable ID, alongside the existing
  genuine-negative exit-1 case. `scripts/tests/test_ll_issues_check_decidable.py` has the
  `_write_issue()` / `_invoke()` subprocess-fixture shape to extend
- A guard test enumerating the family — assert every `check-*` subcommand returns 2 for a
  nonexistent ID, so a newly added probe cannot reintroduce the conflation. This is the test that
  makes the convention durable rather than a one-time sweep

_Wiring pass added by `/ll:wire-issue`:_

- The six existing not-found tests to flip from `returncode == 1` to `== 2` (exact anchors):
  `test_ll_issues_check_decidable.py:278-282` `test_missing_issue_exits_one`,
  `test_ll_issues_check_open_questions.py:213-217` `test_missing_issue_exits_one`,
  `test_ll_issues_check_design.py:184-188` `test_missing_issue_exits_one`,
  `test_ll_issues_check_acceptance_criteria.py:177-181` `test_missing_issue_exits_one`,
  `test_ll_issues_check_verify_verdict.py:253-258` `test_missing_issue_exits_one` (this test file
  exists but was not named anywhere in the issue's prior research), `test_check_readiness.py:79-81`
  `test_unresolvable_issue_exits_1` — outlier shape, in-process `_run_check_readiness()` return
  value rather than subprocess `returncode`.
- **`check_flag.py` has no dedicated test file at all** — `scripts/tests/test_ll_issues_check_flag.py`
  does not exist. A new file is needed to give the highest-traffic probe (18 gate sites) direct
  not-found coverage; follow the `_cli()`/`temp_project_dir`/`_write_issue()`/`_invoke()` quartet
  used by its five siblings, asserting `returncode == 2` for `check-flag FEAT-9999 decision_needed`.
- `test_ll_issues_check_design.py` module docstring (lines 1-5) states "0 = gate passes / 1 = gate
  failed or issue not found" — conflates the two 1-cases the same way the code being fixed does;
  update alongside the assertion change.
- FSM structural tests asserting `on_error` targets for the routing-divergence states above need no
  change (they assert the YAML shape, not runtime exit-code behavior) but the 4 no-`on_error` states
  have **no existing test coverage of that gap** — `check_passed.on_error` itself is also unpinned
  (`test_builtin_loops.py:6982` only covers `on_no`) and `check_ac_automatable`'s `on_error` is
  likewise unpinned (`test_builtin_loops.py:1635-1646` only covers `on_yes`/`on_no`). New tests
  should pin `on_error` for: `check_passed`, `check_ac_automatable`, `decide_current`,
  `check_missing_artifacts` (autodev.yaml), `check_spike_needed`, `check_spike_completed`
  (spike-gate.yaml) — once those two loop files gain `on_error` clauses per the Wiring Phase below.
- `scripts/tests/test_autodev_decision_gate.py` (`test_check_flag_error_falls_through_to_refine_current`,
  `test_check_flag_error_falls_through_to_run_size_review`) already stubs `exit_code: 2` for
  check-flag/check-readiness not-found — confirmatory, no change needed.

### Documentation

- `docs/reference/CLI.md` — each probe's exit-code table, plus a stated family-wide convention:
  0 = yes, 1 = no, 2 = cannot evaluate, 3 reserved
- `docs/reference/HOST_COMPATIBILITY.md` / FSM docs if they describe `shell_exit` polarity

_Wiring pass added by `/ll:wire-issue`:_

- `docs/reference/CLI.md:1972` — explicit stale example: `check-design BUG-9999   # Exit 1 — issue
  not found`, becomes exit 2
- `docs/guides/LOOPS_REFERENCE.md` — prose stating `check_verify_verdict`, `check_ac_automatable`,
  and `check_design` route "on_no/exit-1 ... independently of the confidence scores" describes only
  the genuine-failure case post-fix; needs a caveat that a not-found ID now takes the (different)
  `on_error` path instead, per the routing-divergence table above
- `skills/decide-issue/SKILL.md:488,547` — documents `ll-issues check-decidable <ID>` as a
  verification step; no exit-code claim to correct, but is a doc-coupling site to re-check
- `commands/refine-issue.md:488` — mentions `ll-issues check-decidable <ID>` in step text; same
  re-check note

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-22 — based on codebase analysis:_

- Existing tests for four of the seven probes (`check_decidable`, `check_open_questions`, `check_design`, `check_acceptance_criteria`) share one verbatim `_cli()` / `temp_project_dir` / `_write_issue()` / `_invoke()` fixture quartet, duplicated per-file rather than imported from a shared module, plus an identically-shaped `test_missing_issue_exits_one` test (`returncode == 1`, id-in-stderr, "not found"/"Error" in stderr). `test_check_readiness.py` is the outlier: a different fixture shape (`_run_check_readiness`, no `_invoke`) and a differently-named not-found test (`test_unresolvable_issue_exits_1`) — a new exit-2 test for `check_readiness` should follow its own existing local shape, not the quartet.
- No existing test enumerates the check-* family under one shared parametrized invariant. The nearest structural analog, `test_builtin_loop_hardcode_gate.py`, parametrizes over a glob-derived list of loop YAML files with a hand-maintained exemption set — but CLI subcommand registration here (`cli/issues/__init__.py`, ~708-751 registration, ~1015-1029 dispatch) is a flat per-command `if`-chain with no iterable registry a test could introspect. A family-wide guard test here would need a hand-maintained subcommand list (mirroring that same file's hand-maintained `_HARDCODE_PATTERNS` tuple), not a glob.

## Program Design

### Types

N/A — no data structures. The change is a return value in seven functions.

### Signatures

- `cmd_check_decidable(config: BRConfig, args: argparse.Namespace) -> int` and its six siblings —
  signatures unchanged; only the not-found return value moves 1 → 2
- `_resolve_issue_id(config, issue_id) -> Path | None` — `cli/issues/show.py` — unchanged; the
  shared resolver whose `None` return is the trigger in all seven

### Call Path

`<FSM state action>` → `ll-issues check-<probe> <ID>` → `cmd_check_<probe>` → `_resolve_issue_id`
→ `None` → **exit 2** (was 1) → `fsm/evaluators.py` `shell_exit` → `on_error` (was `on_no`).

### Decision Rules

One decision: **is `check-flag` in scope?** It carries 18 of the 44 gate sites — more than the
other six combined — and the thinnest semantics, so it is the most disruptive to change and the
least conceptually improved by changing. Options: include all seven for a uniform convention;
exclude `check-flag` and document why.

> **Selected:** Include `check-flag` — uniform convention across all seven probes.

### Decision Rationale

**Selected**: Include `check-flag` in the exit-1→2 fix, alongside the other six probes.

**Reasoning**: "Thinnest semantics" cuts toward inclusion, not exclusion — a boolean
frontmatter-flag check has the simplest, most predictable `on_no`/`on_error` gate shape of
the seven, which makes its 18 call sites *easier* to audit per-site, not riskier. The actual
code change is a one-line literal (`return 1` → `return 2`) regardless of scope; the real
cost is the caller audit, which the other 26 sites already require. Auditing 18 more sites
of the identical `_resolve_issue_id(...) is None` guard shape is additional volume, not
additional risk. Excluding `check-flag` would also leave the exact conflation this issue
exists to fix standing in the family's highest-traffic member — recreating, in reverse, the
"single inconsistent outlier" problem the Motivation section cites as the reason to file
this issue at all.

| Option | Blast radius | Conceptual gain | Outcome |
|---|---|---|---|
| Include `check-flag` | 18 additional sites, same shape as the other 26 | Closes the conflation family-wide, no asymmetric exception to remember | **Selected** |
| Exclude `check-flag` | Smaller immediate diff | Leaves the highest-traffic probe inconsistent; requires documenting a carve-out with no principled rationale | Rejected |

## Implementation Steps

1. Audit all 44 gate sites: for each, record what `on_error` does today and whether reaching it on
   a bad ID is an improvement or a new failure.
2. `check-flag` scope is decided — in scope (§ *Program Design → Decision Rules*). Include its 18
   sites in the step-1 audit.
3. Change the not-found return to 2 across all seven commands.
4. Add the per-command exit-2 tests and the family-wide guard test.
5. Update `docs/reference/CLI.md` with the family-wide exit-code convention.
6. Re-run the full suite — the loop-level FSM tests are where an unreviewed `on_error` branch will
   surface.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Add an explicit `on_error` clause to the 4 states that currently have none, so an "error" verdict
  (now reachable via not-found) doesn't hit the unrouted `None` fallthrough in `fsm/executor.py`:
  `decide_current` and `check_missing_artifacts` in `autodev.yaml`; `check_spike_needed` and
  `check_spike_completed` in `spike-gate.yaml`. Decide each target deliberately — this is new
  routing, not a mechanical copy of `on_no`.
- Review the 7 confirmed routing-divergence states (table in Dependent Files) individually — each
  is a live behavior change, not just an audit item — and confirm the new `on_error` destination is
  correct for a not-found ID, especially `oracles/resolve-decision.yaml`'s `assert_decision_cleared`
  (flips a not-found ID from terminal success to terminal failure).
- Create `scripts/tests/test_ll_issues_check_flag.py` — no dedicated test file exists for the
  highest-traffic probe; add not-found coverage asserting exit 2, following the sibling quartet
  pattern.
- Flip the six existing not-found tests from `returncode == 1` to `== 2` (exact anchors listed
  under Tests above), including `test_check_readiness.py`'s in-process-return-value variant.
- Update `test_ll_issues_check_design.py`'s module docstring to stop conflating "gate failed" and
  "issue not found" under exit 1.
- Add `on_error`-target tests for `check_passed` and `check_ac_automatable` (currently unpinned),
  plus the 4 newly-added `on_error` clauses above.
- Update `docs/reference/CLI.md:1972` and the `docs/guides/LOOPS_REFERENCE.md` routing prose.
- Note (no action required): `skills/confidence-check/SKILL.md:141`'s `&&`/`||` check-design
  invocation is confirmed convergent; `scripts/little_loops/cli/issues/locate_options.py` is a
  related but out-of-scope command that will become the new inconsistent outlier — flagged for a
  future issue, not this one's scope.

## Impact

- **Priority**: P3 — no live incident is attributable to it, and the one traced instance
  (`resolve-decision.yaml`) is bounded to a wasted pass. It is filed for the silent-miss class and
  because BUG-3278 is about to make the family inconsistent, not because something is on fire
- **Effort**: Small change, Medium audit — the seven returns are trivial; step 1 is the work
- **Risk**: Medium — a shared CLI contract with 44 consumers, several of which will newly reach
  `on_error`. Bounded by the audit and by the fact that the new branch is only reachable on an
  unresolvable ID, which is already a broken state
- **Breaking Change**: Yes, narrowly — any external consumer branching on exit 1 to mean
  "not found or no" sees 2 for the not-found half. No such consumer is known in-repo

## Steps to Reproduce

1. `ll-issues check-decidable 999999` → `Error: Issue '999999' not found.`, exit **1**.
2. `ll-issues check-flag 999999 decision_needed` → exit **1**, same as a `false` flag.
3. Compare with a genuine negative on a real issue — also exit 1, no distinguishable signal.
4. Trace `resolve-decision.yaml:47-67`: exit 1 → `on_no` → `deposit_options`, i.e. remediation is
   attempted against an issue that does not exist.

## Root Cause

- **File**: `scripts/little_loops/cli/issues/check_decidable.py` and six siblings
- **Anchor**: `the _resolve_issue_id(...) is None guard in each cmd_check_* function`
- **Cause**: Each probe was written with a binary yes/no contract and reused the "no" code for the
  unresolvable-input case, before `shell_exit`'s three-way polarity (0/1/2+) made the distinction
  load-bearing. The convention then propagated by copy across all seven as the family grew — no
  single decision introduced it, which is why it has not been noticed as a defect.

## Related Key Documentation

- **BUG-3278** part 4 — specifies exit 2 for the new `check-unresolved-decisions` on exactly this
  reasoning (*"reusing 1 for 'not found' would make an unresolvable ID indistinguishable from a
  genuine residual and route it to `done`"*), and notes the exit-3 hazard. That issue is the
  precedent; this one generalizes it to the existing family
- **BUG-3293** § *Proposed Solution → Part 3* — the adjacent reporting defect in the same file,
  scoped out to here
- `scripts/little_loops/fsm/evaluators.py:255-259` — the `shell_exit` polarity contract

## Status

**Open** | Created: 2026-08-22 | Priority: P3

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-08-22_

**Readiness Score**: 100/100 → PROCEED
**Outcome Confidence**: 52/100 → LOW

### Outcome Risk Factors
- Wide blast radius: 44 existing `ll-issues check-*` gate invocations across 6 loop files, each requiring individual `on_error`-branch review before the exit-code change is safe to land family-wide (Pattern A blast radius, not a uniform mechanical sweep).
- Per-site behavioral judgment: 7 of the 44 sites have differing `on_no`/`on_error` targets (a real routing change) and 4 states need brand-new `on_error` clauses decided from scratch — implementation requires judgment at each site, not text substitution.
- Coverage gaps built concurrently: `check_flag.py` (highest-traffic probe, 18 sites) has no existing test file, and 6 FSM routing states currently have no test pinning their `on_error` target — both the code change and its safety net are being created in the same pass.


## Session Log
- `/ll:confidence-check` - 2026-08-22T21:25:43 - `0c7d6c76-7efe-4d29-9902-6a8bb3eb75f1.jsonl`
- `/ll:wire-issue` - 2026-08-22T21:07:33 - `ad82b3b7-2da4-479e-b70b-43a0d95a179c.jsonl`
- `/ll:decide-issue` - 2026-08-22T20:54:26 - `2cdeacc1-78a3-4957-91ac-395ad2547996.jsonl`
- `/ll:decide-issue` - 2026-08-22T20:51:53 - `bc6653b6-fcc0-4790-89ae-8782900fae6c.jsonl`
- `/ll:refine-issue` - 2026-08-22T20:51:02 - `2cdeacc1-78a3-4957-91ac-395ad2547996.jsonl`
- `/ll:refine-issue` - 2026-08-22T20:50:54 - `bc6653b6-fcc0-4790-89ae-8782900fae6c.jsonl`
- `/ll:refine-issue` - 2026-08-22T20:44:27 - `e5cf24d5-a696-446d-94d8-837adc15685c.jsonl`
