---
id: EPIC-2663
type: EPIC
priority: P2
status: open
captured_at: '2026-07-18T02:50:02Z'
discovered_date: '2026-07-18'
discovered_by: capture-issue
relates_to: [ENH-2664, FEAT-2665, ENH-2666, ENH-2533, ENH-2008]
labels:
- loops
- orchestration
- issue-lifecycle
- observability
---

# EPIC-2663: Make automation deferral visible and recoverable

## Summary

Automation (`rn-implement`) sets issues to `status: deferred` when they fail a
readiness/remediation gate, but `deferred` is excluded from active selection
(`sprint.py:15`) and default listings (`issue_parser.py:1250`), and the only
auto-resurfacing (`re_enqueue_unblocked`, rn-implement.yaml:782) fires *within a
single run* and *only* for `blocked_by` deps. The result is a roach-motel state:
issues automation sets aside never return to human attention across runs.
Important issues (ENH-2464, ENH-2465, ENH-2466 from run
`rn-implement-20260717T165621`) were silently dropped this way.

This EPIC makes automation deferral a **reversible, visible** action rather than
a black hole, without removing the legitimate circuit-breaker behavior that
stops the engine from re-attempting an issue that keeps failing readiness.

## Goal

`deferred` set by automation is always (a) distinguishable from a human's
intentional "not now," and (b) resurfaced back to a human for triage across
runs. No issue that fails an automated gate disappears without a review path.

## Motivation

The `deferred` transition acts as a circuit-breaker — it stops `rn-implement`
from re-picking an issue that fails readiness every run, which is correct. The
defect is not that it stops retrying; it's that deferral is invisible and
irreversible in practice. Two root problems:

1. **Semantic overloading** — `deferred` means both "a human chose to set this
   aside" and "automation gave up this run." These want different downstream
   treatment. The `blocked_by` case has a return path; the "remediation stalled /
   decomposition declined" case (which needs *more* human attention) gets the
   quietest possible state.
2. **No resurfacing loop** — nothing lists automation-deferred issues for review.
   ENH-2533 (done) added *within-run* per-issue outcomes to `summary.json`, but
   there is no *cross-run* sweep.

## Scope

**In scope:**
- Frontmatter reason discriminator on deferral (ENH-2664)
- Cross-run resurfacing / triage of automation-deferred issues (FEAT-2665)
- Reconciling autodev vs rn-implement not-ready handling (ENH-2666)

**Out of scope:**
- Removing or weakening the deferral circuit-breaker itself
- Changing how `blocked_by` dependency resolution works
- The within-run `summary.json` reporting already delivered by ENH-2533

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/rn-implement.yaml` — `mark_deferred` state (1330-1357), `re_enqueue_unblocked` (782)
- `scripts/little_loops/issue_lifecycle.py` — `defer_issue()` (794-857)
- `scripts/little_loops/issue_parser.py` — default status skip (1250-1251)
- `scripts/little_loops/sprint.py` — `_ACTIVE_STATUSES` (15)

### Dependent Files (Callers/Importers)
- TBD — grep for `set-status`/`deferred` consumers and any triage/report surface

### Tests
- `scripts/tests/test_builtin_loops.py`, issue-lifecycle tests — TBD

### Documentation
- `.claude/CLAUDE.md` § Issue File Format (status semantics)

## Impact

- **Priority**: P2 — silently drops important backlog issues; erodes trust in autonomous runs.
- **Effort**: Medium — spans loop YAML, issue-lifecycle, and a new triage surface across three children.
- **Risk**: Medium — touches shared status-selection code paths used by sprint/auto/rn.
- **Breaking Change**: No — additive frontmatter + new surfacing; existing `deferred` semantics preserved.

## Children

- **ENH-2664** — Tag automation deferral with a reason discriminator (`deferred_by`/`deferred_reason`).
- **FEAT-2665** — Cross-run resurfacing/triage sweep for automation-deferred issues (the ENH-2464 fix).
- **ENH-2666** — Reconcile autodev vs rn-implement "not ready" handling.

## Success Metrics

- Every automation-set `deferred` carries `deferred_by: automation` + a reason code.
- A single command/report lists all automation-deferred issues with reasons across runs.
- A run that defers issues surfaces them to the human; no silent drop of the ENH-2464 class.

## Session Log
- `/ll:capture-issue` - 2026-07-18T02:50:02Z

---

## Status

- **Current**: open
- **Last Updated**: 2026-07-18
