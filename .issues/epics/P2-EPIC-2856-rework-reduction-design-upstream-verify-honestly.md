---
id: EPIC-2856
title: "Rework reduction \u2014 design upstream, verify honestly"
type: EPIC
status: open
priority: P2
captured_at: '2026-07-27T00:00:00Z'
discovered_date: 2026-07-27
relates_to:
- ENH-2852
- ENH-2853
- FEAT-2855
- ENH-2973
- ENH-2866
- FEAT-2867
- ENH-2870
- ENH-2871
- FEAT-2878
- ENH-2933
- ENH-2934
- ENH-2935
labels:
- epic
- rework
- verification
- refinement
- observability
---

# EPIC-2856: Rework reduction — design upstream, verify honestly

## Summary

little-loops' batch instruments (`ll-auto`, `ll-parallel`, `ll-sprint`) optimize
for how much work can be pushed through the queue. Nothing in the system
measures or reduces the share of that work that has to be redone.

This epic attacks rework from both ends: make an issue commit to its
program-level shape *before* an agent starts, and make a loop's "verified"
signal impossible to fake once it has.

The children are independently shippable and share one premise: throughput
without a quality-adjustment term is a misleading number, and the cheapest
quality wins are deterministic, not model-graded.

## Motivation

Two failure modes recur in unattended batch runs:

1. **Design decided mid-implementation.** The refinement chain
   (`/ll:refine-issue` → `/ll:wire-issue` → `/ll:confidence-check`) researches
   the codebase and names integration points, but never forces an issue to
   state the types, method signatures, and call path a change will follow. The
   most rework-prone decisions get made by an agent under implementation
   pressure, with no human review of the plan.

2. **Verification that verifies nothing.** A loop that treats a green test
   suite as a transition predicate can be satisfied by a test that already
   passed before the change, or by an agent editing the test out of the way.
   Both are cheap to detect deterministically and neither is currently
   detected.

The observability child exists because neither fix is provable without a
measurement: rework rate (FEAT-2867) is the quantity that tells you whether any
of this worked; the maintainability trend (FEAT-2855) is a second, complementary
dimension.

## Goal

A batch run's output can be trusted without reading every line: each issue
entered implementation with its program design already fixed, each verification
claim survives a deterministic integrity check, and codebase health under
sustained agent activity is measurable.

## Scope

**In scope:** a program-design stage in the refinement chain and its confidence
gate; deterministic pre-patch test-failure checking; test-file tamper detection
during verification; the shared substrate both verification checks need
(test-file identification, dequeue-time SHA stamping); rework-rate metrics over
issue/commit attribution; maintainability-trend metrics over repo history joined
with `.ll/history.db`.

**Out of scope:** replacing semantic/LLM criteria in `ll-harness` — these checks
sit alongside them, not instead of them; new event transports; hosted or
multi-tenant reporting.

## Children

**Substrate**

- **ENH-2973** — Shared test-file identification module and `project.test_patterns`
  config key
- **ENH-2866** — Record dequeue-time commit SHA at orchestrator dequeue and
  worktree creation

**Verification**

- **ENH-2853** — Deterministic pre-patch test-failure check in verification
  loops *(consumes both substrate children)*
- **ENH-2854** — Guard against agent edits to test files during verification
  *(consumes the identification module)*

**Design**

- **ENH-2852** — Add a program-design stage to issue refinement naming types,
  signatures, and call path

**Measurement**

- **FEAT-2867** — Measure rework rate as the quality-adjustment term on batch
  throughput
- **FEAT-2855** — Track codebase maintainability trend as an observability
  dimension
- **FEAT-2878** — Trace-level assertions in the eval harness, with optional
  multi-host divergence runs

### Revisions from the 2026-07-27 epic review

- **ENH-2853 was oversized and is split.** It carried eight workstreams; the two
  that were independently landable and independently useful — the shared
  test-file identification substrate and the dequeue-SHA stamp — are now
  ENH-2973 and ENH-2866. The stamp in particular had to come first: without it,
  ENH-2853's primary base-state path is dead code and every run silently takes
  the merge-base fallback.
- **The ENH-2853 ↔ ENH-2854 dependency was circular and is removed.** ENH-2853
  declared a hard `blocked_by: ENH-2854` while ENH-2854's `revert` policy
  depended on ENH-2853's semantics, and both proposed introducing the same
  config key. Both now depend on ENH-2973 and on nothing from each other; their
  only remaining interaction is an ordering constraint stated in ENH-2854
  (`revert` runs after the pre-patch check has read the step's diff), and each
  must be functional with the other absent.
- **FEAT-2867 is new — the epic had no measurement of its own subject.** The
  epic opens on "the share of work that has to be redone" and promises
  quality-adjusted throughput, but FEAT-2855 measures *codebase
  maintainability*, a different quantity. Rework itself was unmeasured. It is
  also the cheapest item in the set — joins and ratios over `commit_events`
  attribution that already exists, with no `git log` parsing — which is why it
  sequences first rather than last.

### Suggested order

1. **FEAT-2867** — establishes the baseline the rest are measured against. Cheap,
   read-only, no dependencies.
2. **ENH-2973, ENH-2866** — small substrate, unblocks both verification children.
3. **ENH-2853, ENH-2854** — now genuinely parallel; together they close the two
   cheapest holes in the verification story.
4. **ENH-2852** — the design gate, whose effect FEAT-2867 can then detect either
   side of its cutover stamp.
5. **FEAT-2855** — largest, and benefits from the others being in place to
   measure.

**Baseline before intervention** (revised 2026-07-27): FEAT-2855's signals are
computed from `git log`, which is immutable — the tool can retroactively
compute any pre-intervention window once it ships. No manual signal sampling is
needed up front. What ENH-2852 must record before its gate is enabled is the
**cutover point**: `.ll/program-design-cutover.json` with the SHA/date at which the
interventions begin (plus the caveat that `.ll/history.db` attribution for old
windows depends on manual retention). "Did any of this work" is then answered
by FEAT-2867 comparing rework windows either side of that stamp, with FEAT-2855
supplying the maintainability dimension of the same comparison.

## Success Metrics

- `/ll:confidence-check` fails an issue that has no specific program-design
  section, and passes one that names concrete types, signatures, and a call
  path.
- A verification loop rejects a newly added test that passes against the
  pre-patch tree.
- A verification step that modified a test file either reverts the modification
  before scoring or fails the transition, and reports which files were touched.
- A maintainability trend is reportable across ≥2 sampling points from repo
  history without LLM judgment.
- Rework rate is reportable per window alongside raw closed-issue count, so
  throughput and quality-adjusted throughput are visibly different numbers — and
  the design gate's effect is answerable by comparing windows either side of its
  cutover stamp.

## Integration Map

- Refinement chain — `/ll:refine-issue`, `/ll:wire-issue`,
  `/ll:confidence-check`
- Verification — `ll-harness`, `/ll:verify-issue-loop`, embedded verification in
  FSM transitions, the verification escalation ladder, the verification-evidence
  bundle
- Observability — `.ll/history.db`, existing agent-quality reporting

## Impact

Converts batch throughput from a volume metric into a quality-adjusted one, and
closes the two cheapest holes in the verification story. Both verification
children are small, deterministic, and testable — the highest
confidence-per-effort items in the set.

## Status

**Open** | Created: 2026-07-27 | Priority: P2


## Related Key Documentation

- `.claude/CLAUDE.md` — the Testing & CI Policy section is the operative
  contract this epic's deterministic pre-patch/tamper-detection children
  (ENH-2853, ENH-2854) must satisfy without introducing hosted CI.
- `CONTRIBUTING.md` — documents the test-running and mutation-testing
  workflow this epic's verification-integrity children extend.

## Session Log
- `/ll:audit-issue-conflicts` - 2026-07-27T19:42:09 - `e2303183-4e52-4649-af90-4b53254bbda4.jsonl`
