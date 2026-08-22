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

**Exit 2 is not a new code for these commands — argparse already uses it.** Verified 2026-08-22:
`ll-issues check-flag` with a missing positional exits **2** (argparse `parser.error` →
`SystemExit(2)`). That is the same "I could not evaluate this" class as an unresolvable ID, so
choosing 2 aligns the not-found case with a signal the family already emits rather than
introducing a new one. It also means `on_error` is **already reachable** from these gate sites
today — see § *Dependent Files → already-live error reachability*.

### Scope Boundary — what this does *not* close

The fix closes the **not-found** half of "cannot evaluate", not the class. Verified 2026-08-22: an
issue file that *resolves* but whose frontmatter fails to parse still exits **1** —
`parse_frontmatter` degrades gracefully (no exception, no traceback), so `check-flag` reports the
field as absent and returns a genuine-looking negative. Same for a resolvable file missing the
queried field entirely. Those remain exit 1 by design here; do not write acceptance criteria that
claim the conflation is eliminated, only that the unresolvable-ID case is separated.

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
- No `EXIT_*` constant, enum, or shared exit-code helper exists anywhere in `cli/issues/` or `fsm/` today — every exit code in every one of the seven probes is a raw inline `return N`. The not-found guard is identical across all seven: `_resolve_issue_id(...) is None` → `print(f"Error: Issue '{id}' not found.", file=sys.stderr)` → `return 1`. The not-found sites — the ONLY lines that change — are exactly one per file: check_decidable.py:32, check_open_questions.py:56, check_design.py:36, check_flag.py:29, check_acceptance_criteria.py:102, check_verify_verdict.py:84, check_readiness.py:140. Every other `return 1` in these files (check_decidable.py:60, check_open_questions.py:81, check_design.py:39, check_flag.py:33, check_acceptance_criteria.py:118, check_verify_verdict.py:97,107,118, check_readiness.py:142) is a genuine negative verdict and must stay 1.

_Added by `/ll:refine-issue` — 2026-08-22 — based on codebase analysis:_

- No shared "resolve-or-exit" helper/decorator exists for the `_resolve_issue_id(...) is None` guard across `cli/issues/`; every one of the seven probes re-implements the check-and-return inline after importing `_resolve_issue_id` from `show.py` (evidence: `check_decidable.py:26-32`, `check_open_questions.py:47-56`, `check_flag.py:23-29`). BUG-3278's own spec for the new sibling command states the same method explicitly — "Model on `check_open_questions.py`, diverging on the exit codes" — i.e. copy-and-diverge, not extract-and-share, is the codebase's stated convention even for a brand-new file in this family.
- Recent family-wide fixes in this codebase extract a new shared function only when the underlying data model changes (e.g. BUG-3278's `DecisionGroup`/`locate_unresolved_decisions`), not to deduplicate a repeated exit-code literal. No precedent exists for extracting a helper purely to unify this guard.
- No iterable registry exists for the check-* subcommand family to drive a parametrized guard test: `cli/issues/__init__.py:1015-1029` dispatches via a flat `if`-chain, not a data structure a test could introspect. The nearest analog, `test_builtin_loop_hardcode_gate.py` (glob-derived parametrize + hand-maintained `_EXEMPT` set), does not transfer directly — a family-wide guard test here needs a hand-maintained subcommand list, mirroring that file's `_HARDCODE_PATTERNS` tuple. **(Superseded — see § Tests: glob `cli/issues/check_*.py` for the family list; only per-probe extra argv is hand-maintained.)**
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

Six resolve the ID via `_resolve_issue_id` from `cli/issues/show.py` directly; `check_readiness.py`
resolves through the `readiness_status()` helper and guards on `status is None` (`:139-140`). The
fix in all seven is the CLI-layer return value only — do NOT change `readiness_status()` itself,
which `issue_manager.py:796` also imports and whose `None` contract must stay intact.

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

- **New failure mode — states with no `on_error` at all**: `autodev.yaml:611` `decide_current`,
  `autodev.yaml:1393` `check_missing_artifacts`, `spike-gate.yaml:34` `check_spike_needed`,
  `spike-gate.yaml:42` `check_spike_completed`. `fsm/executor.py:2776-2792` returns `None` rather
  than falling back to `on_no` (the fallback runs only in the other direction — a `no` verdict with
  no `on_no` *does* fall through to `on_error`, `executor.py:2772-2773`).

  **The consequence is a run abort, not an unrouted no-op.** `_route()` → `None` reaches
  `executor.py:767-774`, which calls `_finish("error", error="No valid transition")` — the entire
  loop run terminates. So at these four states a bad ID goes from a graceful `on_no` detour today
  to a dead run post-fix. That makes the Wiring Phase `on_error` additions a **prerequisite** of
  the exit-code change, not a companion cleanup: land them first, or land both in one commit.

- **Already-live error reachability** (corrects the assumption that these states have never seen a
  nonzero-but-not-1 exit): `ll-issues check-flag` exits **2** from argparse when a positional is
  missing (verified 2026-08-22). `decide_current` (`autodev.yaml:622`) and both spike-gate states
  interpolate a bare `${...issue_id}` into the command line, so an empty interpolation shifts the
  field name into the ID slot and argparse errors with 2 — aborting the run today, with no
  not-found involved. The `on_error` gap is a live defect independent of this issue's fix.

- **Sites where the exit code never reaches `shell_exit` at all** — the probe is invoked inside
  shell control flow, which collapses every nonzero to one branch. The audit framing ("record what
  `on_error` does at each of the 44 sites") does not apply here, because these have no reachable
  `on_error` for the probe's own verdict:

  | Loop file | State | Shape | Effect of a not-found ID |
  |---|---|---|---|
  | autodev.yaml:1267 | `recheck_scores` | `if ! ll-issues check-design "$ID"; then touch …-design-gate-failed-$ID; fi` | marker touched — same as a genuine design failure |
  | autodev.yaml:1799 | `regate_after_atomic_remediation` | `if ll-issues check-design "$ID"; then DESIGN_FAIL=false; else DESIGN_FAIL=true; touch …; fi` | same |
  | autodev.yaml:2026 | `recheck_after_size_review` | same shape as `:1799` | same |

  Bash `if` sees only zero/nonzero, so exit 2 is indistinguishable from exit 1 and the state's
  overall exit code is decided by later logic in the same action. **These three sites get no
  improvement from the fix.** The marker they touch is consumed at `autodev.yaml:1829` and `:2066`
  to select `design_gate_failed` as the deferral reason — so an unresolvable ID is recorded as a
  Program Design defect on an issue that does not exist. Either add an explicit discriminator
  (`ll-issues check-design "$ID"; rc=$?; if [ "$rc" -ge 2 ]; then …` — a distinct branch that does
  *not* touch the marker) or declare it a stated residual with a follow-up issue. Do not leave it
  unremarked; it is the same silent-miss shape this issue exists to close.

  `recheck_scores`'s trailing `&&` chain (`:1272-1274`) is a separate case: `&&` *does* propagate
  the nonzero, so that half of the action routes normally (`on_error` there equals `on_no`, so it
  is routing-inert).

  Note also the `||` chain at `oracles/resolve-decision.yaml:62-63` — `check-open-questions ||
  check-decidable`. Both probes share the same resolver and the same ID, so a not-found ID yields 2
  from both and the chain's exit is 2. Convergent; no masking in this instance.
- `skills/confidence-check/SKILL.md:141` — a non-loop caller: `ll-issues check-design ... && echo "" || echo "yes"`. Bash `&&`/`||` already collapses any nonzero to the same branch, so this site is confirmed **convergent** (no behavior change) — included for audit completeness since it sits outside the "44 loop gate sites" the audit scope names.
- `scripts/little_loops/cli/issues/locate_options.py:36` — a related but **out-of-scope** CLI command (not one of the seven) whose own test docstring (`test_issues_locate_options.py:5,181`) explicitly asserts parity with "check-decidable's contract" on exit 1 for not-found. Once the seven move to exit 2, this file becomes the new single inconsistent outlier the Motivation section warns about — flagged for awareness, not added to *Files to Modify* since it is outside this issue's named family.

### Tests

- Per-command CLI test asserting exit **2** on an unresolvable ID, alongside the existing
  genuine-negative exit-1 case. `scripts/tests/test_ll_issues_check_decidable.py` has the
  `_write_issue()` / `_invoke()` subprocess-fixture shape to extend
- A guard test enumerating the family — assert every `check-*` subcommand returns 2 for a
  nonexistent ID, so a newly added probe cannot reintroduce the conflation. This is the test that
  makes the convention durable rather than a one-time sweep.

  **Derive the family list by glob, not by hand.** Earlier research here concluded a
  hand-maintained subcommand list was the only option because `cli/issues/__init__.py` dispatches
  through a flat `if`-chain with no introspectable registry. That understates what is available:
  the family is one module per probe (`cli/issues/check_*.py`, seven files, exactly the seven in
  scope), and the subcommand name is the module stem with `_`→`-`. Globbing that directory gives a
  registry that cannot drift when an eighth probe lands — which is the entire point of the guard
  test, and is lost the moment the list is hand-maintained. This also matches the
  `test_builtin_loop_hardcode_gate.py` precedent more closely than the hand-maintained
  `_HARDCODE_PATTERNS` half of it does: that file globs its *subjects* and hand-maintains only its
  *exemptions*. Do the same — glob the probes, hand-maintain only per-probe extra argv (e.g.
  `check-flag` needs a trailing field name, `check-readiness` needs its thresholds)

_Wiring pass added by `/ll:wire-issue`:_

- The six existing not-found tests to flip from `returncode == 1` to `== 2` (exact anchors):
  `test_ll_issues_check_decidable.py:307-311` `test_missing_issue_exits_one`,
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
- `skills/decide-issue/SKILL.md:488-490` — **does carry an exit-code claim** (an earlier pass in
  this issue recorded "no exit-code claim to correct" — that was wrong): *"exit 0 means 'decide has
  something to act on', exit 1 routes the loop through …"*. That enumeration becomes incomplete
  once 2 exists; add the not-found case. Line `:547` is a plain invocation with no claim.
  Tracked mirrors of this file carry the same prose and need the same edit (or a regeneration):
  `.qwen/skills/decide-issue/SKILL.md`, `.kimi-code/skills/decide-issue/SKILL.md`,
  `.gemini/skills/decide-issue/SKILL.md`
- `commands/ready-issue.md:237` — not previously listed: `ll-issues check-design [ID]` *"exits
  non-zero … surface only, never block"*. Convergent (any nonzero takes the same advisory path), so
  no behavior change, but the prose should not imply non-zero means a design gap
- `commands/refine-issue.md:488` — mentions `ll-issues check-decidable <ID>` in step text; same
  re-check note

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-22 — based on codebase analysis:_

- Existing tests for four of the seven probes (`check_decidable`, `check_open_questions`, `check_design`, `check_acceptance_criteria`) share one verbatim `_cli()` / `temp_project_dir` / `_write_issue()` / `_invoke()` fixture quartet, duplicated per-file rather than imported from a shared module, plus an identically-shaped `test_missing_issue_exits_one` test (`returncode == 1`, id-in-stderr, "not found"/"Error" in stderr). `test_check_readiness.py` is the outlier: a different fixture shape (`_run_check_readiness`, no `_invoke`) and a differently-named not-found test (`test_unresolvable_issue_exits_1`) — a new exit-2 test for `check_readiness` should follow its own existing local shape, not the quartet.
- No existing test enumerates the check-* family under one shared parametrized invariant. The nearest structural analog, `test_builtin_loop_hardcode_gate.py`, parametrizes over a glob-derived list of loop YAML files with a hand-maintained exemption set — but CLI subcommand registration here (`cli/issues/__init__.py`, ~708-751 registration, ~1015-1029 dispatch) is a flat per-command `if`-chain with no iterable registry a test could introspect. A family-wide guard test here would need a hand-maintained subcommand list (mirroring that same file's hand-maintained `_HARDCODE_PATTERNS` tuple), not a glob. **(Superseded — see § Tests: the family IS glob-derivable from `cli/issues/check_*.py`; the flat dispatch `if`-chain only rules out introspecting the argparse registry, not globbing the modules.)**

_Pre-implementation review — 2026-08-22 — claims re-verified against the tree:_

- All seven `return 1` not-found sites confirmed present; `_resolve_issue_id` is a thin delegation
  to `issue_parser.resolve_issue_path` (`cli/issues/show.py:39-60`) and returns `None` for every
  unresolvable form, so one guard covers the whole family.
- Gate-site count reproduced exactly: 44 across 6 loop files — `refine-to-ready-issue.yaml` 17,
  `autodev.yaml` 16, `oracles/resolve-decision.yaml` 4, `spike-gate.yaml` 3, `rn-remediate.yaml` 3,
  `recursive-refine.yaml` 1.
- **No Python consumer** branches on these exit codes: the only cross-module import from the family
  is `issue_manager.py:796` → `check_readiness.readiness_status` (a helper, not `cmd_*`), and the
  MCP server exposes no `check-*` tool. The blast radius is shell callers only.
- Exit codes measured directly: `ll-issues check-decidable 999999` → 1; `ll-issues check-flag`
  (missing positional) → 2; `check-flag` against a file with malformed frontmatter → 1, no
  traceback.
- The four no-`on_error` states and the three shell-swallowing sites were read in full and are
  recorded in *Dependent Files*.

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

## Pre-Decided Routing (outcome-risk mitigation — 2026-08-22)

_The 44-site audit is complete (buckets and tables in § Dependent Files). What remained open was
per-site judgment; that judgment is exercised HERE, so implementation executes recorded decisions
rather than making new ones._

### The 4 missing `on_error` clauses — targets decided

The governing convention, already live and test-pinned in autodev (`test_autodev_decision_gate.py`
stubs exit 2 and asserts fall-through; cf. `check_passed.on_error: detect_children`,
`triage_outcome_failure.on_error: detect_children`, confidence-recheck `on_error: enqueue_or_skip`):
**a probe that cannot evaluate degrades open to the pipeline's fall-through state** — the gate is
an optimization, not a correctness barrier, and downstream states have their own failure handling.

| State | Add | Rationale |
|---|---|---|
| `autodev.yaml` `decide_current` | `on_error: implement_current` | Same as `on_no` (degrade open). A bad ID fails again inside `implement_current`'s `ll-auto --only`, which has its own triage path (`check_impl_auth` → drain/abort) — the right place to handle it. |
| `autodev.yaml` `check_missing_artifacts` | `on_error: detect_children` | Same as `on_no`; its own comment says it "mirrors check_decision_before_size_review logic", and the size-review path is the safe fall-through. |
| `spike-gate.yaml` `check_spike_needed` | `on_error: run_impl` | Preserves today's degrade-open not-found behavior (exit 1 → `run_impl`) instead of converting it to a hard stop; also fixes the pre-existing argparse-exit-2 run abort. |
| `spike-gate.yaml` `check_spike_completed` | `on_error: run_impl` | Same rationale; reachable only after `check_spike_needed` succeeded, so an error here is transient — degrade open. |

All four are routing-inert relative to `on_no` **by design** — the purpose is eliminating the
run-abort (`executor.py:774`), not adding new routing semantics. This also means the exit-code flip
produces **zero behavior change at these four sites** beyond un-breaking the abort.

### The 7 routing-divergence sites — reviewed and signed off, no YAML edits needed

Each `on_error` destination was reviewed for the not-found case (2026-08-22); all seven are correct
as they stand. The new behavior at each is the *intended* fix, not an open question:

- `check_passed` → `detect_children`: degrade-open convention; already reachable via argparse 2.
- `refine-to-ready-issue.yaml` `check_verify_verdict` → `check_hedges`, `check_hedges` →
  `check_placeholders`, `check_ac_automatable` → `confidence_check`, `check_design` →
  `confidence_check`: all skip a remediation step and continue the chain — correct for an issue
  that cannot be evaluated (remediating a nonexistent issue is the bug being fixed).
- `resolve-decision.yaml` `check_decision_decidable` → `run_decide`: acceptable — `run_decide`
  fails on its own against a bad ID, and the detour is marker-bounded.
- `resolve-decision.yaml` `assert_decision_cleared` → `failed`: the highest-value flip — a
  not-found ID stops terminating the sub-loop as success. The state's own comment already
  documents `on_error: failed` as the conservative-unresolved choice.

### Bucket (d) — decided: add the `rc` discriminator

At the three shell-swallowed `check-design` sites (`autodev.yaml:1267`, `:1799`, `:2026`), use
`ll-issues check-design "$ID"; rc=$?; if [ "$rc" -eq 1 ]; then <touch marker>; fi` so exit ≥2 no
longer files a Program Design defect against a nonexistent issue. Not the "stated residual" option
— the discriminator is three small, identical edits and closes the silent-miss fully.

## Implementation Steps

_Land as two phases — **Phase A first, as its own commit, suite green, before any exit code
changes**. Phase A is purely additive (new clauses, new tests pinning current behavior), so it
cannot regress anything; it converts "code and safety net land in the same pass" into "safety net
pre-exists the change"._

### Phase A — safety net (no behavior change to the probes)

1. Add the 4 `on_error` clauses per the *Pre-Decided Routing* table above.
2. Create `scripts/tests/test_ll_issues_check_flag.py` (sibling `_cli()`/`temp_project_dir`/
   `_write_issue()`/`_invoke()` quartet) covering the genuine yes/no contract of the
   highest-traffic probe. (The not-found exit-2 assertion lands in Phase B with the flip.)
3. Pin `on_error` targets in `test_builtin_loops.py` for all 6 currently-unpinned states:
   `check_passed`, `check_ac_automatable`, `decide_current`, `check_missing_artifacts`,
   `check_spike_needed`, `check_spike_completed`.
4. Run the full suite; commit Phase A.

### Phase B — the flip

5. Change the seven not-found returns to 2 (exact lines in § Codebase Research Findings — one line
   per file; every other `return 1` is a genuine negative and stays).
6. Flip the six existing not-found tests to `== 2`, add the `check-flag` not-found test, and add
   the glob-derived family guard test (§ Tests).
7. Add the `rc -eq 1` discriminator at the three bucket-(d) `autodev.yaml` sites per the decision
   above.
8. Update `docs/reference/CLI.md` with the family-wide exit-code convention (0 = yes, 1 = no,
   2 = cannot evaluate — including argparse usage errors, 3 reserved for abstain), and note the
   scope boundary: a resolvable-but-unparseable file still returns 1. Plus the other doc/skill
   touchpoints in § Documentation.
9. Re-run the full suite — with Phase A's pins in place, any surprise routing change surfaces as a
   named test failure, not a silent behavior shift.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Add an explicit `on_error` clause to the 4 states that currently have none, so an "error" verdict
  (now reachable via not-found) doesn't hit the unrouted `None` fallthrough in `fsm/executor.py` —
  which is **not** a benign fallthrough: it terminates the run with `error: No valid transition`
  (`executor.py:767-774`). Sites: `decide_current` and `check_missing_artifacts` in `autodev.yaml`;
  `check_spike_needed` and `check_spike_completed` in `spike-gate.yaml`. **Targets are now
  decided — see § Pre-Decided Routing**; the spike-gate hazard flagged here (naive `on_error:
  failed` converting degrade-open into a hard stop) is resolved by choosing `on_error: run_impl`.
- Review the 7 confirmed routing-divergence states (table in Dependent Files) individually — each
  is a live behavior change, not just an audit item. **Done — all seven reviewed and signed off,
  no YAML edits needed; see § Pre-Decided Routing**, including `assert_decision_cleared`'s
  success→failure flip, which is the intended fix.
- Create `scripts/tests/test_ll_issues_check_flag.py` — no dedicated test file exists for the
  highest-traffic probe; add not-found coverage asserting exit 2, following the sibling quartet
  pattern.
- Flip the six existing not-found tests from `returncode == 1` to `== 2` (exact anchors listed
  under Tests above), including `test_check_readiness.py`'s in-process-return-value variant.
- Update `test_ll_issues_check_design.py`'s module docstring to stop conflating "gate failed" and
  "issue not found" under exit 1.
- Add `on_error`-target tests for `check_passed` and `check_ac_automatable` (currently unpinned),
  plus the 4 newly-added `on_error` clauses above.
- Resolve the three exit-code-swallowing `check-design` sites in `autodev.yaml` (`recheck_scores`
  `:1267`, `regate_after_atomic_remediation` `:1799`, `recheck_after_size_review` `:2026`) — see the
  table in *Dependent Files*. **Decided: the `rc` discriminator (see § Pre-Decided Routing →
  Bucket (d))** — as they stand a not-found ID is filed as a Program Design defect
  (`autodev-design-gate-failed-$ID` → `design_gate_failed` deferral at `:1829`/`:2066`) on an
  issue that does not exist.
- Update `docs/reference/CLI.md:1972` and the `docs/guides/LOOPS_REFERENCE.md` routing prose. State
  the convention as 0/1/2/3 with 2 covering both not-found *and* argparse usage errors.
- Correct `skills/decide-issue/SKILL.md:488-490`'s two-outcome exit-code enumeration (and its three
  tracked host mirrors under `.qwen/`, `.kimi-code/`, `.gemini/`); re-check
  `commands/ready-issue.md:237`'s "exits non-zero" advisory wording.
- Note (no action required): `skills/confidence-check/SKILL.md:141`'s `&&`/`||` check-design
  invocation is confirmed convergent; `scripts/little_loops/cli/issues/locate_options.py` is a
  related but out-of-scope command that will become the new inconsistent outlier — flagged for a
  future issue, not this one's scope. Likewise the resolvable-but-unparseable case (§ *Expected
  Behavior → Scope Boundary*) stays exit 1.

## Impact

- **Priority**: P3 — no live incident is attributable to it, and the one traced instance
  (`resolve-decision.yaml`) is bounded to a wasted pass. It is filed for the silent-miss class and
  because BUG-3278 is about to make the family inconsistent, not because something is on fire
- **Effort**: Small change, Medium audit — the seven returns are trivial; step 1 is the work
- **Risk**: Medium — a shared CLI contract with 44 consumers, several of which will newly reach
  `on_error`. Bounded by the audit and by the fact that the new branch is only reachable on an
  unresolvable ID, which is already a broken state. The sharpest edge is bucket (c): four states
  have no `on_error`, and an unrouted error verdict aborts the whole loop run
  (`executor.py:767-774`), so shipping the exit-code change without those clauses trades a wasted
  pass for a dead run
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
- `/ll:ready-issue` - 2026-08-22T22:18:19 - `afe857fc-f796-4b11-9d6a-872028bfc380.jsonl`
- `/ll:confidence-check` - 2026-08-22T22:13:39 - `4a645ef4-53d6-431a-b186-5f97907a3395.jsonl`
- `/ll:confidence-check` - 2026-08-22T21:49:34 - `9ed67f71-7303-474d-bf20-c4416e27aef4.jsonl`
- `/ll:confidence-check` - 2026-08-22T21:25:43 - `0c7d6c76-7efe-4d29-9902-6a8bb3eb75f1.jsonl`
- `/ll:wire-issue` - 2026-08-22T21:07:33 - `ad82b3b7-2da4-479e-b70b-43a0d95a179c.jsonl`
- `/ll:decide-issue` - 2026-08-22T20:54:26 - `2cdeacc1-78a3-4957-91ac-395ad2547996.jsonl`
- `/ll:decide-issue` - 2026-08-22T20:51:53 - `bc6653b6-fcc0-4790-89ae-8782900fae6c.jsonl`
- `/ll:refine-issue` - 2026-08-22T20:51:02 - `2cdeacc1-78a3-4957-91ac-395ad2547996.jsonl`
- `/ll:refine-issue` - 2026-08-22T20:50:54 - `bc6653b6-fcc0-4790-89ae-8782900fae6c.jsonl`
- `/ll:refine-issue` - 2026-08-22T20:44:27 - `e5cf24d5-a696-446d-94d8-837adc15685c.jsonl`
