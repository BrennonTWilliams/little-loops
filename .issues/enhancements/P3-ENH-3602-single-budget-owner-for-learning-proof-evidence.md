---
id: ENH-3602
type: ENH
title: Single budget owner for learning-proof evidence
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-25'
captured_at: '2026-09-25T18:51:59Z'
decision_needed: false
relates_to:
- ENH-3601
- ENH-3577
- FEAT-3598
parent: EPIC-3565
---

# ENH-3602: Single budget owner for learning-proof evidence

## Summary

Give learning-proof evidence (learning tests, spike proofs) a single budget owner. Today
confidence-check, ready-issue and the `ll-auto` learning gate each consult it and each
treat refuted/stale records their own way. Step E of the ENH-3577 decomposition (Proposed
Solution item 4, first half). **Needs a decision on the owner.**

## Current Behavior

Learning-proof logic is read in at least three places:

- `skills/confidence-check/SKILL.md` + `rubric.md` — caps outcome confidence on unproven mechanisms (BUG-3591)
- `commands/ready-issue.md` — readiness verdict references learning evidence
- `little_loops.issue_manager` (`process_issue_inplace`) — prints `LEARNING_GATE_BLOCKED` in `ll-auto`, which autodev
  detects in `check_learning_gate` / `check_learning_gate_infra` *after* implementation is attempted
- the Learning Test Registry (`little_loops.learning_tests`)

Nothing owns the spend (how many spike/explore-api attempts per issue per run), and a
record can be treated as stale by one consumer and valid by another.

## Expected Behavior

One component decides whether learning proof is sufficient, stale or refuted, and owns the
per-issue attempt budget. Other consumers read its verdict and do not re-derive it.

## Proposed Solution

### Option A: Registry owns it

> **Selected:** Option A — registry already holds `is_record_stale`/`describe_staleness`/`run_learning_gate_for_issue`; deterministic and consumable by B/C-style callers.

`little_loops.learning_tests` exposes `assess_proof(issue_id) -> ProofVerdict`
(`proven | stale | refuted | absent`, plus budget remaining). Confidence-check, ready-issue
and the `ll-auto` gate all call it. Deterministic; one staleness rule.

### Option B: Confidence-check owns it

Confidence-check is the only place proof sufficiency is judged; it writes the verdict to
frontmatter, and ready-issue / the `ll-auto` gate read that field. Keeps judgment in one
skill, but staleness becomes as fresh as the last scoring run.

### Option C: Preparation controller owns it

The ENH-3577 child controller owns the proof budget and emits `PROOF` via
`ll-issues next-obligation`; the `ll-auto` gate becomes a pure assertion that should never
fire after a `ready` outcome.

### Decision Rationale

**Selected:** Option A (Registry owns it).

Scoring (0–3 each): 

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| A | 3 | 2 | 3 | 2 | 10/12 |
| B | 1 | 2 | 1 | 1 | 5/12 |
| C | 1 | 1 | 2 | 1 | 5/12 |

Key evidence: `learning_tests/gate.py` already owns staleness (`is_record_stale`, `describe_staleness`) and
`issue_manager` already calls `run_learning_gate_for_issue`, so A extends an existing seam. B makes a
deterministic fact depend on an LLM scoring run's freshness. C depends on unbuilt FEAT-3598/ENH-3577 and
still needs a verdict source; the controller (C) can consume A's `assess_proof` to emit `PROOF`.

## Integration Map

### Files to Modify
- `skills/confidence-check/SKILL.md`, `skills/confidence-check/rubric.md`
- `commands/ready-issue.md`
- `scripts/little_loops/issue_manager.py`
- `scripts/little_loops/learning_tests/`

### Tests
- `scripts/tests/test_confidence_check_skill.py`, `test_spike_verdict.py`, `test_spike_skill.py`
- New: one staleness/refutation fixture yields the same verdict from every consumer

## Impact

- **Priority**: P3 - child of ENH-3577 (EPIC-3565 consolidation)
- **Effort**: Medium - one verdict API/field and three consumers moved onto it
- **Risk**: Medium - changes when learning gates fire
- **Breaking Change**: No

## Scope Boundaries

- No change to how learning tests are authored (`/ll:explore-api`).
- Program Design is written after the owner is selected (`/ll:decide-issue`).

## Acceptance Criteria

- [ ] Owner option selected and recorded
- [ ] One function/field is the source of truth for proof sufficiency and budget
- [ ] Confidence-check, ready-issue and the `ll-auto` learning gate agree on a shared stale and refuted fixture
- [ ] A `ready` preparation outcome never hits `LEARNING_GATE_BLOCKED` for a reason the controller could have detected

## Parent Issue

Decomposed from ENH-3577: Consolidate autodev issue preparation into a single controller loop

## Status

**Open** | Created: 2026-09-25 | Priority: P3


## Session Log
- `/ll:audit-issue-conflicts` - 2026-09-25T19:09:20 - `dcfdf31c-be65-47ce-9e6e-5b65d63239f2.jsonl`
- `/ll:decide-issue` - 2026-09-25T19:02:00 - `ccfdabfd-5c2e-49a6-bfd7-abb914a90640.jsonl`

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): The AC 'A `ready` preparation outcome never hits `LEARNING_GATE_BLOCKED` for a reason the controller could have detected' depends on ENH-3601's controller. Test this issue via the shared stale/refuted fixture yielding the same verdict from `assess_proof` and the `ll-auto` gate; the controller-level AC belongs to ENH-3601.
