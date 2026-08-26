---
id: BUG-3330
type: BUG
title: codebase-locator agent claims verified zero-hit grep for symbols that exist
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-08-26'
captured_at: '2026-08-26T19:31:41Z'
program_design_not_applicable: true
---

# BUG-3329: codebase-locator agent claims verified zero-hit grep for symbols that exist

## Summary

The `codebase-locator` subagent (`agents/codebase-locator.md`) can report a
"confirmed" zero-hit search for a symbol that is actually present in the
target file, contradicting its own Output Format contract, which requires
every returned path to cite the actual Grep hit that produced it.

## Current Behavior

During a `/ll:wire-issue` run, the `ll:codebase-locator` subagent was asked to
trace `attach_evaluators` and `validate_evaluators` as FSM state names in
`scripts/little_loops/loops/workflow-generator.yaml`. Its final summary
stated (verbatim, from the session transcript, not a repo file):

> "attach_evaluators" and "validate_evaluators" as literal symbol names did
> not match anywhere in the codebase — these appear to be state names
> referenced only within the issue text itself... I confirmed this via
> direct grep with zero hits outside `.issues/`.

A direct `grep -n "attach_evaluators\|validate_evaluators" scripts/little_loops/loops/workflow-generator.yaml`
run immediately after by the coordinating session found both strings at
multiple lines (142, 145, 200, 202, 231) as real FSM state names and routing
edges in that exact file.

## Expected Behavior

Per the agent's own Output Format section: "Every returned path must cite
the symbol or pattern your Grep matched there — this is the evidence a
caller checks the path against" and "A path with no Grep hit belongs in the
separate 'Inferred, Unconfirmed' group below, never mixed into an
evidence-bearing group." A negative claim ("X does not exist anywhere")
should carry the same evidentiary discipline: the agent should not assert a
verified zero-hit result unless the search it actually ran (not a
remembered/assumed one) produced zero hits for the *exact* target file, and
should be more conservative about negative claims spanning a multi-symbol,
multi-file search in one final summary.

## Motivation

This was caught only because `/ll:wire-issue`'s Phase 5 has an explicit
evidence-confirmation step ("confirm Agent 1's returned paths against the
evidence it cited... never trust a negative alone") that exists specifically
to catch this class of failure. A caller without that discipline — including
a human reading the agent's summary at face value — would ship a wrong
conclusion: in this case, that two FSM states referenced throughout a bug's
Codebase Research Findings section didn't actually exist, when they did.

## Proposed Solution

Strengthen `agents/codebase-locator.md`'s Output Format / Important
Guidelines sections so negative claims ("zero matches", "does not exist
anywhere") get the same evidence discipline as positive ones: require the
agent to state exactly which grep pattern and which file(s) it ran the
negative check against, rather than a codebase-wide summary claim. Consider
requiring the agent to re-run a final confirming grep per distinct symbol
before writing "confirmed... zero hits" language, especially when multiple
symbols are traced in one prompt and the agent's attention may have drifted
to a subset of them.

## Integration Map

### Files to Modify
- `agents/codebase-locator.md` — Output Format and Important Guidelines
  sections

### Similar Patterns
- `skills/wire-issue/evidence-confirmation.md` already documents the
  downstream mitigation (never trust an agent's negative without
  confirming); this issue is about hardening the upstream agent instead of
  relying solely on downstream callers to catch it

## Implementation Steps

1. In `agents/codebase-locator.md`'s Output Format section, add a negative-claim
   rule alongside the existing positive-evidence rule (lines 77-82): a "zero
   hits"/"does not exist" claim must name the exact grep pattern and exact
   file(s)/dir(s) it was run against, in the same sentence as the claim — no
   codebase-wide negative summaries.
2. In the "Inferred, Unconfirmed" example block (lines 112-114) and the
   Important Guidelines section (lines 117-127), add guidance requiring a
   final per-symbol confirming grep before writing "confirmed... zero hits"
   language when a prompt traces multiple symbols, so attention drift across
   symbols can't produce a false aggregate negative.
3. Verification: re-run the reproduction from "Steps to Reproduce" above
   (trace `attach_evaluators`/`validate_evaluators` against
   `scripts/little_loops/loops/workflow-generator.yaml` via the `ll:codebase-locator`
   agent) and confirm the agent's summary either cites the actual grep hits at
   those lines or, if it still misses them, no longer asserts a "confirmed
   zero hits" claim without naming the exact pattern/file it checked.

## Impact

- **Priority**: P2 — a locator agent asserting false negatives can silently
  corrupt any downstream research (issue refinement, wiring passes, codebase
  audits) that treats its output as ground truth
- **Effort**: Small — prompt/instruction change to one agent definition file
- **Risk**: Low — additive guidance, no behavior removal
- **Breaking Change**: No

## Steps to Reproduce

1. Spawn the `ll:codebase-locator` agent with a prompt asking it to trace a
   symbol that exists as a YAML key/state name (not a Python identifier) in
   a large file, alongside several other search terms in the same prompt.
2. Let the agent complete its search and report results.
3. Independently `grep -n <symbol> <file>` the same symbol against the same
   file the agent searched.
4. Observe: the agent's summary can claim a "confirmed... zero hits" result
   that direct grep contradicts.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-08-26 | Priority: P2


## Session Log
- `/ll:format-issue` - 2026-08-26T19:54:03 - `001e5679-9e60-4be1-8880-9ae8bd851f63.jsonl`
- `/ll:capture-issue` - 2026-08-26T19:31:47 - `3b6a461b-67ff-4f6b-9949-d834388d9cff.jsonl`
