---
id: 3185
title: Add an abstention verdict and a fixed verdict grammar to LLM-judged gates
type: ENH
priority: P2
status: open
discovered_date: '2026-08-15'
labels:
- verification
- fsm
---

## Summary

Every LLM-judged gate in the stack forces a binary outcome. `verify-issue-loop` criteria mode, FSM LLM predicates, and `ll-harness` semantic criteria all require the judge to answer pass or fail, with no way to report that the check as written could not be evaluated from what the judge could see. An under-specified or unobservable criterion therefore resolves to whichever way the model leans, and that coin flip is persisted and acted on as a real verdict — a loop advances, an issue is marked verified, a quality trend absorbs a number that means nothing.

Add a third verdict, `CANNOT JUDGE`, as a first-class outcome alongside pass and fail, and specify the output contract that carries it.

## Design

A judge evaluating N checks in one pass emits a fixed, numbered block — one line per check, each `PASS`, `FAIL`, or `CANNOT JUDGE`, followed by a single line of reason — so every check is individually parseable rather than collapsing into one prose judgment and one boolean per FSM state.

Callers decide what abstention means for them:

- An FSM predicate treats it as no-transition, rather than as a false branch.
- `ll-harness` reports it separately from failures instead of folding it into the failure count.
- `.ll/history.db` persists it per check, so abstention rate becomes a visible signal.

A criterion that is abstained on repeatedly is a badly written criterion. That is information the current binary shape destroys.

## Relationship to adjacent work

This is the LLM-judge counterpart to the deterministic question of what exit code 124 means — timeout is ignorance, not a verdict. It is distinct from requiring a gate to declare its scope at authoring time: that is a statement about the gate, this is a statement about one run of one check.

Where a check is abstained on because the judge lacked the artifact rather than because the criterion was vague, that is a harness bug, and the signal will surface it.

## Acceptance Criteria

- `CANNOT JUDGE` is a first-class verdict in the grammar, not a parse failure.
- The multi-check output block is fixed-format and individually parseable per check.
- Each of the three consumers above handles abstention distinctly from failure, with the behaviour tested.
- Abstention is persisted per check and queryable as a rate.
- A judge that emits a verdict outside the grammar fails loudly rather than being coerced to pass or fail.
