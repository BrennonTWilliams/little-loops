---
id: BUG-3294
type: BUG
title: ll-issues check-* probes return exit 1 for an unresolvable issue ID, routing
  FSM gates to on_no instead of on_error
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-08-22'
decision_needed: true
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

**Open question for the decision pass** — whether `check-flag` should be included. It is the
highest-traffic member (18 sites) and its semantics are the thinnest ("is this frontmatter field
`true`"), so it has the widest blast radius for the least conceptual gain. Deciding it out is
defensible; deciding it out *silently* is not.

## Integration Map

### Files to Modify

- `scripts/little_loops/cli/issues/check_decidable.py` — not-found return (`:30-32`)
- `scripts/little_loops/cli/issues/check_open_questions.py` — not-found return
- `scripts/little_loops/cli/issues/check_design.py` — not-found return
- `scripts/little_loops/cli/issues/check_acceptance_criteria.py` — not-found return
- `scripts/little_loops/cli/issues/check_verify_verdict.py` — not-found return
- `scripts/little_loops/cli/issues/check_readiness.py` — not-found return
- `scripts/little_loops/cli/issues/check_flag.py` — not-found return, **pending the scope decision**

Each resolves the ID via `_resolve_issue_id` from `cli/issues/show.py`, so the shape of the change
is identical in all seven.

### Dependent Files (Callers/Importers)

- `scripts/little_loops/loops/` — 44 `ll-issues check-*` gate invocations across 6 files; each
  `on_error` branch needs review per *Proposed Solution* step 2
- `scripts/little_loops/loops/oracles/resolve-decision.yaml:47-67` — the worked example above
- `scripts/little_loops/fsm/evaluators.py:255-259` — the `shell_exit` polarity this issue is
  written against; **unchanged**

### Tests

- Per-command CLI test asserting exit **2** on an unresolvable ID, alongside the existing
  genuine-negative exit-1 case. `scripts/tests/test_ll_issues_check_decidable.py` has the
  `_write_issue()` / `_invoke()` subprocess-fixture shape to extend
- A guard test enumerating the family — assert every `check-*` subcommand returns 2 for a
  nonexistent ID, so a newly added probe cannot reintroduce the conflation. This is the test that
  makes the convention durable rather than a one-time sweep

### Documentation

- `docs/reference/CLI.md` — each probe's exit-code table, plus a stated family-wide convention:
  0 = yes, 1 = no, 2 = cannot evaluate, 3 reserved
- `docs/reference/HOST_COMPATIBILITY.md` / FSM docs if they describe `shell_exit` polarity

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
exclude `check-flag` and document why. Decide it against the step-2 caller audit rather than in
the abstract, and record the outcome either way.

## Implementation Steps

1. Audit all 44 gate sites: for each, record what `on_error` does today and whether reaching it on
   a bad ID is an improvement or a new failure.
2. Decide the `check-flag` scope question against that audit (§ *Program Design → Decision Rules*).
3. Change the not-found return to 2 in the in-scope commands.
4. Add the per-command exit-2 tests and the family-wide guard test.
5. Update `docs/reference/CLI.md` with the family-wide exit-code convention.
6. Re-run the full suite — the loop-level FSM tests are where an unreviewed `on_error` branch will
   surface.

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
