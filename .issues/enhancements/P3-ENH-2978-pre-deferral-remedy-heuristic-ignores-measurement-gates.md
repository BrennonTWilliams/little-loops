---
id: ENH-2978
title: dispatch_pre_deferral_remedy spike-vs-reconcile heuristic ignores unresolved
  measurement gates
type: ENH
priority: P3
status: done
captured_at: '2026-08-01T20:40:01Z'
completed_at: '2026-08-01T21:55:20Z'
discovered_date: 2026-08-01
discovered_by: capture-issue
testable: true
relates_to:
- ENH-2965
- ENH-2569
decision_needed: false
labels:
- autodev
- loop-quality
program_design_not_applicable: true
confidence_score: 95
outcome_confidence: 96
score_complexity: 21
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
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

> **Selected:** Option A — minimal, localized fix; reuses an established
> body-text grep idiom and fixes the reported incident without touching
> shared skill infrastructure.

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

### Decision Rationale

**Selected: Option A** — standalone grep-based measurement-gate check added
directly inside `recheck_after_size_review`'s REMEDY block.

**Reasoning**: Option A reuses an idiom already established twice in this
codebase (`recursive-refine.yaml:557-564`'s `check_decision_needed`, and the
duplicated `grep -qE ... || grep -qE ...` parent/decomposition check at
`autodev.yaml:911-925` and `:1298-1312`), all following the same
`ll-issues path "$ID"` → `[ -n "$FILE" ] && grep -q[iE] "<pattern>" "$FILE"`
shape. It is localized to the one state with the bug, requires no change to
`dispatch_pre_deferral_remedy` (which already treats `REMEDY` as an opaque
string), fits the existing substring/ordering test style used by
`test_recheck_after_size_review_arms_remedy_before_low_readiness`, and fixes
the reported incident (ENH-2965) on the very next autodev pass — it reads the
issue body directly rather than depending on a frontmatter flag set by a
prior `/ll:confidence-check` run. Option B, by contrast, requires extending a
shared, already-tested skill (`skills/confidence-check/SKILL.md` Phase 4.10)
whose signal-phrase list has never been incrementally extended before, adds a
second subsystem to touch (the autodev routing would still need to be wired
to consult `spike_needed` instead of/alongside the ambiguity heuristic), and
would not retroactively fix already-scored issues like ENH-2965 without a
manual `/ll:confidence-check` re-run.

| Dimension | Option A | Option B |
|---|---|---|
| Consistency | 3 | 2 |
| Simplicity | 3 | 1 |
| Testability | 3 | 1 |
| Risk | 3 | 1 |
| **Total** | **12/12** | **5/12** |

**Key evidence**:
- Established grep idiom precedent: `recursive-refine.yaml:557-564`,
  `autodev.yaml:911-925`, `autodev.yaml:1298-1312`
- `dispatch_pre_deferral_remedy` (`autodev.yaml:1915-1939`) already consumes
  `REMEDY` as an opaque string — no change needed there under Option A
- Option B's Phase 4.10 signal-phrase list (`skills/confidence-check/SKILL.md:440-466`)
  has been static since ENH-2569 (2026-07-14) with no incremental-extension
  precedent, and its consuming autodev gate (`check_spike_needed`,
  `autodev.yaml:1152-1179`) is functionally disjoint from the BUG-2803 remedy
  block this issue targets — consolidating them is real follow-on work, not a
  drop-in fix
- Option B would leave the ENH-2965 incident issue unfixed without a manual
  `/ll:confidence-check` re-run, per its own re-run mechanism analysis
  (`rerun_confidence_after_spike`/`rerun_confidence_after_wire` only fire
  post-spike/post-wire, not on-demand for phrase-list changes)

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

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_builtin_loops.py::TestAutodevLoop::test_recheck_after_size_review_arms_remedy_before_low_readiness` (`:5567-5587`) — update: extend with an `action.index(...)` ordering assertion proving the new measurement-gate grep check runs before the existing `score_ambiguity` subscore fallback, mirroring this test's existing `autodev-pre-deferral-remedy-fired` vs `--reason low_readiness` ordering assertion [Agent 3 finding]
- `scripts/tests/test_builtin_loops.py::TestAutodevLoop::test_child_detection_matches_parent_frontmatter` (`:5313-5324`) — pattern to model a new dedicated test on: asserts the grep marker/pattern substrings are present in a state's action string; new test should assert the measurement-gate marker literal(s) (e.g. `"do not start otherwise"`, `"measurement (gate)"`) appear in `recheck_after_size_review`'s action [Agent 3 finding]
- `scripts/tests/test_autodev_loop.py::TestRecheckAfterSizeReviewStagnationBackstop::test_stagnated_write_precedes_low_readiness_write` (`:363-370`) — regression check only, not modified: asserts `readiness_stagnated` write precedes the `low_readiness` write in the same action string; verify this ordering still holds once the new gate-check code is inserted [Agent 2 finding]
- `scripts/tests/test_autodev_loop.py::TestRecheckAfterSizeReviewDesignGateBranch::test_design_branch_hardcodes_reconcile_remedy` (`:438-446`) — regression check only, not modified: asserts `"score_ambiguity" not in branch` for the design-gate slice of the action (`:1807-1828`), disjoint from the BUG-2803 remedy block (`:1864-1874`) this issue touches; confirm no overlap after the edit [Agent 2 finding]

_Second wiring pass (`/ll:wire-issue`, 2026-08-01) — no existing test executes the REMEDY-selection Python snippet or the new marker check; all cited tests above are static substring/ordering assertions on the YAML action string, not fixture execution [Agent 3 finding]:_
- New test needed: extract the embedded Python one-liner (`autodev.yaml:1866-1874`) and run it via `subprocess` with synthetic stdin JSON, asserting the REMEDY outcome for: (a) marker present + ambiguity NOT the weakest subscore → still `spike` (the precedence case this issue exists to fix), (b) marker absent + ambiguity strictly weakest → `spike` (existing fallback, regression), (c) marker absent + ambiguity not weakest → `reconcile` (existing fallback, regression)
- New test needed, modeled on `test_autodev_loop.py::TestRecheckAfterSizeReviewDesignGateBranch::test_design_branch_hardcodes_reconcile_remedy` (`:438-446`)'s "hardcodes" pattern: assert the new marker-check branch forces `REMEDY=spike` and does not itself reference `score_ambiguity`/`others` (mirrors that test's `"score_ambiguity" not in branch` shape, applied to the new branch's slice instead of the design-gate branch's)
- New test needed, modeled on `test_builtin_loops.py::TestAutodevLoop::test_child_detection_matches_parent_frontmatter` (`:5313-5324`)'s per-literal assertion style: confirm each measurement-gate marker literal (`"do not start otherwise"`, `"measurement (gate)"`, `"pre-implementation measurement"`) is individually present in the grep pattern
- Regression sanity check only, not modified: `test_autodev_loop.py::TestRecheckAfterSizeReviewDesignGateBranch::test_design_branch_precedes_readiness_stagnated_branch` (`:428`) and `test_autodev_loop.py::test_decision_branch_ordered_after_design_gate_before_stagnation` (`:492`) both do `action.index(...)` ordering across multiple branch markers — re-run after implementation to confirm inserting the new marker-check code at `:1864` doesn't shift these orderings

### Documentation
- N/A

_Wiring pass added by `/ll:wire-issue`:_
- `.claude/CLAUDE.md` (~line 209, "Pre-deferral remedy guarantee (BUG-2803)" paragraph in the Issue File Format section) — states the current heuristic verbatim ("spike when `score_ambiguity` is the strictly weakest subscore, else reconcile"); must be updated to describe the new measurement-gate precedence or it will misdescribe shipped behavior [Agent 2 finding]

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

## Scope Boundaries

- Out of scope: extending `/ll:confidence-check` Phase 4.10's signal-phrase
  list to cover measurement-gate phrasing (Option B, tracked as related
  follow-on work via `relates_to: ENH-2569`).
- Out of scope: changes to `check_spike_needed`'s `spike_needed`/
  `spike_attempted` frontmatter-flag mechanism (`autodev.yaml:1181-1213`).
- Out of scope: changes to `dispatch_pre_deferral_remedy`'s `on_yes`/`on_no`/
  `on_error` routing (`autodev.yaml:1915-1939`) — it already consumes
  `REMEDY` as an opaque string and needs no edit under Option A.

## Impact

- **Priority**: P3 - Localized FSM routing bug in a one-shot pre-deferral
  remedy dispatch; not on the critical path but causes affected issues to
  deadlock into `readiness_stagnated` with no automatic recovery, requiring a
  human to notice and manually run `/ll:spike`.
- **Effort**: Small - a single grep-based condition added to an existing
  shell `action:` block, reusing an idiom already established twice
  elsewhere in this codebase (`recursive-refine.yaml:557-564`,
  `autodev.yaml:911-925`/`:1298-1312`).
- **Risk**: Low - change is localized to `recheck_after_size_review`'s
  `REMEDY` computation (`autodev.yaml:1864-1874`); downstream consumers
  (`dispatch_pre_deferral_remedy`) already treat `REMEDY` as an opaque
  string, so no signature or contract change propagates outward.
- **Breaking Change**: No

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-08-01_

**Readiness Score**: 95/100 → STOP — ADDRESS GAPS (Program Design hard override)
**Outcome Confidence**: 96/100 → HIGH CONFIDENCE

### Gaps to Address
- Program Design gate (ENH-2852) fails: `ll-issues format-check ENH-2978 --format json` reports `program_design_nonspecific`: "no signature-shaped line found in Types/Signatures; no call-path anchor resolves against the repo: recheck_after_size_review, check_pre_deferral_remedy, dispatch_pre_deferral_remedy, run_spike, reconcile_current". The `## Program Design` section's Call Path names FSM state identifiers, which the linter's anchor resolution does not recognize as repo-resolvable symbols (it expects Python signatures/call paths). Remedy: either add a concrete signature-shaped line describing the inline Python/shell block being added (e.g. the `REMEDY = ...` assignment or the grep condition it depends on) so the linter finds a resolvable anchor, or set `program_design_not_applicable: true` in frontmatter if this FSM-state-only edit is judged out of scope for the gate.

## Session Log
- `/ll:manage-issue` - 2026-08-01T21:54:56 - `b2bfd5a3-5550-443c-acd1-9f59cf5a7c3a.jsonl`
- `/ll:ready-issue` - 2026-08-01T21:48:18 - `ba23eb0c-9675-4487-be35-a68b2c48fd0c.jsonl`
- `/ll:confidence-check` - 2026-08-01T21:32:58 - `81202fd6-c61f-4d4d-a599-fc5de22c4b09.jsonl`
- `/ll:wire-issue` - 2026-08-01T21:29:50 - `ddf85c02-adc5-41f4-b252-16c06a0e5d2e.jsonl`
- `/ll:confidence-check` - 2026-08-01T21:04:26 - `18e44701-3ef7-47f6-98f5-75f5ccda0086.jsonl`
- `/ll:wire-issue` - 2026-08-01T21:00:48 - `5c8fbd72-1a78-4d02-b25a-9c0903ac4399.jsonl`
- `/ll:decide-issue` - 2026-08-01T20:55:18 - `05bd6867-c199-4858-9bd1-c9a38d40b01d.jsonl`
- `/ll:refine-issue` - 2026-08-01T20:46:41 - `12a4183d-577a-4213-855b-508a653b37c5.jsonl`
- `/ll:capture-issue` - 2026-08-01T20:40:46 - `7bdcd321-6d37-4867-b143-d41a1b34670a.jsonl`

- `/ll:capture-issue` - 2026-08-01T20:40:01 - conversation

## Status

**Open** | Created: 2026-08-01 | Priority: P3
