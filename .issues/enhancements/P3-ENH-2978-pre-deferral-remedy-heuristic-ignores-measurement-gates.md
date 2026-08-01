---
id: ENH-2978
title: dispatch_pre_deferral_remedy spike-vs-reconcile heuristic ignores unresolved measurement gates
type: ENH
priority: P3
status: open
captured_at: "2026-08-01T20:40:01Z"
discovered_date: 2026-08-01
discovered_by: capture-issue
testable: true
relates_to:
- ENH-2965
- ENH-2569
decision_needed: true
labels:
- autodev
- loop-quality
---

# ENH-2978: dispatch_pre_deferral_remedy spike-vs-reconcile heuristic ignores unresolved measurement gates

## Summary

`autodev.yaml`'s `dispatch_pre_deferral_remedy` state (BUG-2803,
`scripts/little_loops/loops/autodev.yaml:1858-1874`) chooses between arming
`run_spike` and `reconcile_current` as the one-shot pre-deferral remedy using a
single signal: whether `score_ambiguity` is the strictly weakest of the four
outcome-confidence subscores (`amb < min(others)`). This proxy misses the case
where an issue's readiness gap is caused by an **unresolved empirical
precondition** (a "do not start otherwise" measurement gate written into the
issue body) rather than by design ambiguity — routing to `reconcile`, a
text-rewrite remedy that cannot produce the missing data, so readiness never
moves and the issue deadlocks into `readiness_stagnated`.

## Context

Observed on a live `ll-loop run autodev ENH-2965` run
(`.loops/runs/autodev-20260801T150345/`). ENH-2965's "Proposed Solution" step 0
requires replaying a corpus of completed issues to measure an attributable-only
hit rate before implementation may begin, explicitly warning "Do not start
otherwise." No hit rate was ever recorded in the file — this is the single
largest readiness gap (the issue says so itself, at the tail of its own body).

`score_ambiguity` was 18/25; `score_complexity` was 14/25 (the strictly
weakest subscore). Per the current heuristic, `18 < 14` is false, so the
dispatcher armed `reconcile` instead of `spike`. `reconcile_current` rewrote
issue prose across the run's `refine_current`/`reconcile_current` states, but
none of that work executes code or gathers data, so the unresolved measurement
gate was untouched, `confidence_score` stayed at 80 (below the 85 threshold),
and after `autodev-repair-cycle-count.txt` reached 3 the run correctly (per its
own stagnation backstop) deferred the issue as `readiness_stagnated` — a dead
end that a `/ll:spike` run would very plausibly have resolved, since spike's
whole purpose is to prove an unproven internal mechanism via an isolated code
run.

## Current Behavior

`dispatch_pre_deferral_remedy`'s Python routing block
(`autodev.yaml:1865-1874`) only inspects the four outcome-confidence
subscores:

```python
amb = int(d.get('score_ambiguity') or 0)
others = [int(d.get(k) or 0) for k in
          ('score_complexity', 'score_test_coverage', 'score_change_surface')]
print('spike' if (amb and amb < min(others)) else 'reconcile')
```

This treats "ambiguity is the weakest outcome subscore" as the only signal
for "this issue needs a spike." It has no visibility into the issue body text
at all, so an issue with a clearly-stated, unresolved measurement/proof
precondition — but a subscore profile where some other outcome dimension
happens to be weaker — is routed to `reconcile` regardless.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- This routing block is one branch of five inside `recheck_after_size_review`
  (`autodev.yaml:1722-1892`, action body starting `:1748`). The branches run
  in this order, gated by the shared `${context.run_dir}/autodev-pre-deferral-remedy-fired`
  marker: `resolved_by_subloop` (already done/cancelled) → **Program Design
  gate failure** (`:1807-1828`, ENH-2870 — hardcoded to `reconcile`, *not*
  this heuristic) → `decision_unresolved` (`:1829-1846`) → `readiness_stagnated`
  stagnation backstop (`:1847-1852`, FEAT-2751) → the BUG-2803 general remedy
  branch this issue targets (`:1853-1887`). The `REMEDY` computation itself is
  at `:1864-1874` (one line off the issue's `1865-1874` citation — the
  `python3 -c "` opening line is `:1864`).
- `dispatch_pre_deferral_remedy` (`:1915-1939`) consumes `REMEDY` via
  `on_yes: run_spike` / `on_no: reconcile_current` / `on_error: reconcile_current`
  — any value other than the exact string `"spike"` (including malformed
  output) silently falls through to `reconcile`, so a body-text check that
  fails open must still emit exactly `"spike"` or `"reconcile"`, never
  something else.
- **A parallel, more capable spike-arming mechanism already exists and is not
  consulted here.** `check_spike_needed` (`autodev.yaml:1181-1213`, ENH-2640)
  routes to `run_spike` by reading a `spike_needed` frontmatter flag from
  `ll-issues show --json`, guarded by `spike_needed == 'true' and
  spike_attempted != 'true'`. That flag is set by `/ll:confidence-check`
  Phase 4.10 (`skills/confidence-check/SKILL.md`, added by ENH-2569, done
  2026-07-14), which scans Outcome Risk Factors prose for signal phrases
  ("no precedent", "unprecedented", "untested mechanism", "novel mechanism",
  "unproven approach", "no test coverage of the", …), confirms with a score
  condition (`score_test_coverage <= 10` OR Criterion A Depth
  Moderate/Deep), and suppresses when the risk factor names a third-party
  API (routes to `learning_tests_required`/`/ll:explore-api` instead).
  **ENH-2569's signal-phrase list does not include "do not start otherwise"
  or "measurement (gate)" style phrasing** — a grep confirms this: no FSM
  YAML, skill, or Python module in the repo currently matches on that
  language. This is the source of a genuine two-way decision point on where
  the fix belongs — see Proposed Solution below.
- Grep-based body-text marker detection inside a `shell_exit`-fragment
  `action:` block (resolve path via `ll-issues path "$ID"`, then `grep -q`/`grep -qiE`
  against the file) is an established idiom elsewhere in this codebase, not
  a new pattern this fix would introduce: `recursive-refine.yaml:557-564`
  (`check_decision_needed`, matching `decision_needed: true`),
  `autodev.yaml:920-921` and `:1307-1308` (parent/decomposition detection,
  same `grep -qE ... || grep -qE ...` shape reused verbatim in two places),
  and case-insensitive body matching in `cua-agent-desktop.yaml:350,869,884`
  and `lib/common.yaml:318`. `dispatch_pre_deferral_remedy`/
  `recheck_after_size_review` themselves are JSON-only today (no `grep` on
  the issue file) — a body-text check would be new *to this state*, not new
  to the codebase.

## Expected Behavior

The dispatcher should also check for an explicit unresolved measurement/proof
gate in the issue body (e.g. a "Pre-implementation measurement (gate)"-style
section, or frontmatter/body language equivalent to "do not start otherwise")
and route to `spike` whenever such a gate exists and has not been satisfied —
independent of which outcome subscore is weakest. The ambiguity-subscore check
should remain as a secondary/fallback signal for issues with no such explicit
gate.

## Motivation

Outcome-confidence subscores and readiness criteria are separate rubrics
(`skills/confidence-check/rubric.md`); using one outcome subscore as a proxy
for a readiness-criterion problem is a category mismatch that can silently
misroute the one remedy attempt BUG-2803 grants each issue. Since the
pre-deferral remedy is a single one-shot dispatch per issue per run (gated by
`autodev-pre-deferral-remedy-fired`), a wrong choice here means the issue
gets no second attempt in the same run — it goes straight to
`readiness_stagnated` next time `recheck_after_size_review` sees it, wasting
the refine/reconcile/decide/size_review cycles already spent and requiring a
human to notice and manually run `/ll:spike`.

## Proposed Solution

Add a body-text check to the routing block in `dispatch_pre_deferral_remedy`
(`autodev.yaml:1865-1874`) that greps the issue file for an explicit
unresolved-gate marker before falling back to the ambiguity-subscore
comparison — for example, a heading match on `measurement (gate)` /
`Pre-implementation measurement` (case-insensitive) combined with the absence
of a recorded outcome near it, or a simpler `grep -qi 'do not start
otherwise'` style marker that issue authors already use for this pattern (as
seen in ENH-2965's own Proposed Solution step 0). If found, force
`REMEDY=spike` before evaluating the subscore fallback.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

Research surfaced that a related, more general mechanism already exists
(`spike_needed`, ENH-2569/ENH-2640 — see Current Behavior above) and does not
yet cover this phrasing. Two viable resolutions follow from that:

**Option A**: Add a standalone `grep -qiE 'do not start otherwise|measurement
\(gate\)|pre-implementation measurement'`-style check directly inside
`dispatch_pre_deferral_remedy`'s (or `recheck_after_size_review`'s) routing
block, resolving the issue file path via `ll-issues path "$ID"` first —
mirrors the existing `recursive-refine.yaml:557-564` /
`autodev.yaml:920-921` grep idiom. Localized to the one state that has the
bug; no change to `/ll:confidence-check` or the `spike_needed` flag's
semantics.

**Option B**: Extend `/ll:confidence-check` Phase 4.10's signal-phrase list
(`skills/confidence-check/SKILL.md`) to also match measurement-gate phrasing,
so `spike_needed` gets set upstream for these issues too, and have
`dispatch_pre_deferral_remedy` read the same `spike_needed`/`spike_attempted`
flags `check_spike_needed` already reads (`autodev.yaml:1181-1213`) instead
of re-implementing a second, narrower body-text check. Consolidates all
"unproven mechanism" detection behind one flag and one skill, at the cost of
touching a shared, already-tested skill (`test_confidence_check_skill.py`)
for a routing bug local to one FSM state, and a `/ll:confidence-check` re-run
being required before the flag takes effect on already-scored issues (the
ENH-2965 incident issue would not be immediately fixed without a rerun).

**Recommended**: Option A for this issue — it is the minimal, localized fix
for the reported bug and matches the issue's own stated scope (routing block
only, `autodev.yaml:1865-1874`). Option B is a legitimate follow-on
consolidation (flagged via `relates_to: ENH-2569`) but expands this issue's
surface into a shared skill and is better scoped as its own enhancement if
pursued.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/autodev.yaml` — `dispatch_pre_deferral_remedy` state, routing block at `:1865-1874`

### Dependent Files (Callers/Importers)
- `check_pre_deferral_remedy` (`autodev.yaml:1898-1913`) — dispatches to this state's armed remedy; no signature change needed
- `recheck_after_size_review` (`autodev.yaml:1847-1892`) — arms the remedy handshake file this state consumes; unaffected

### Similar Patterns
- `check_spike_needed`'s `on_yes: run_spike` routing (`autodev.yaml:1181-1213`) — the loop's other spike-arming path, for comparison on how spike preconditions are framed elsewhere in this loop

### Tests
- `scripts/tests/test_builtin_loops.py` — add/extend coverage asserting `dispatch_pre_deferral_remedy` routes to `spike` when an issue body contains an unresolved measurement-gate marker, even when `score_ambiguity` is not the weakest subscore

### Documentation
- N/A

### Configuration
- N/A

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

> ⚠ The `REMEDY` computation this issue targets is actually inside
> `recheck_after_size_review`'s action body (`autodev.yaml:1864-1874`), not
> inside `dispatch_pre_deferral_remedy` (`:1915-1939`) — the latter only
> consumes the already-armed `REMEDY` value from
> `autodev-pre-deferral-remedy.txt` and routes `on_yes: run_spike` /
> `on_no: reconcile_current`. The fix belongs in `recheck_after_size_review`.

- Related mechanism (Option B territory, see Proposed Solution): `skills/confidence-check/SKILL.md`
  Phase 4.10 (ENH-2569) — sets `spike_needed` from Outcome Risk Factors
  signal-phrase scanning; does not yet cover measurement-gate phrasing.
- Existing test precedents for this exact state family, to model new/extended
  coverage on (`scripts/tests/test_builtin_loops.py`):
  - `test_pre_deferral_remedy_dispatch_routing` (`:5552-5565`) — asserts on
    `dispatch_pre_deferral_remedy`'s action-string substrings and
    `on_yes`/`on_no`/`on_error` routing, no FSM execution.
  - `test_recheck_after_size_review_arms_remedy_before_low_readiness`
    (`:5567-5587`) — asserts substrings (`autodev-pre-deferral-remedy-fired`,
    `spike_attempted`, `reconcile_attempted`, `score_ambiguity`) are present
    in the action **and** enforces ordering via
    `action.index("autodev-pre-deferral-remedy-fired") < action.index("--reason low_readiness")`
    — the established pattern for testing "X happens before Y" in one shell
    action string. A new test for the body-text gate should follow this
    ordering-assertion shape (gate check runs before the subscore fallback).
  - `test_check_spike_needed_predicate_reads_both_flags` (`:5725-5731`) —
    asserts both `spike_needed` and `spike_attempted` substrings are present,
    i.e. tests that a routing predicate reads all its intended signals — the
    analogous assertion here would confirm the new grep/marker substring is
    present in `recheck_after_size_review`'s action alongside the existing
    `score_ambiguity` substring.

## Program Design

### Signatures

No new Python functions — this is a shell/inline-Python change inside an
existing FSM state's `action:` block.

### Call Path

`recheck_after_size_review` -> `check_pre_deferral_remedy` ->
`dispatch_pre_deferral_remedy` (routing block gains a body-text gate check)
-> `run_spike` | `reconcile_current`

## Session Log
- `/ll:refine-issue` - 2026-08-01T20:46:41 - `12a4183d-577a-4213-855b-508a653b37c5.jsonl`
- `/ll:capture-issue` - 2026-08-01T20:40:46 - `7bdcd321-6d37-4867-b143-d41a1b34670a.jsonl`

- `/ll:capture-issue` - 2026-08-01T20:40:01 - conversation
