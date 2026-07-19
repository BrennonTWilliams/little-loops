---
id: ENH-2689
title: 'autodev: add reconcile step for stale issue-body sections after spike/refine
  plateau'
type: ENH
priority: P2
status: done
captured_at: '2026-07-19T04:38:59Z'
completed_at: '2026-07-19T16:06:20Z'
discovered_date: 2026-07-19
discovered_by: capture-issue
relates_to:
- FEAT-2672
labels:
- loops
- autodev
- refine-issue
confidence_score: 98
outcome_confidence: 75
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 18
decision_needed: false
size: Very Large
deferred_by: automation
deferred_date: '2026-07-19T13:49:48Z'
deferred_reason: low_readiness
---

# ENH-2689: autodev: add reconcile step for stale issue-body sections after spike/refine plateau

## Summary

`autodev.yaml`'s refine/spike/re-confidence-check cycle can plateau: `/ll:refine-issue`
only **appends** new "Codebase Research Findings" bullets when it discovers a
correction, but never rewrites the issue's own Implementation Steps /
Acceptance Criteria / Files to Modify sections to match. When those sections
contradict the accumulated findings, `/ll:confidence-check` re-flags the same
Concern every pass and the Readiness score never moves — the loop eventually
exhausts its remedies (`run_spike`, `run_wire`, `run_decide`) and defers the
issue via `low_readiness`, even though the underlying technical/architectural
blocker was already resolved.

## Motivation

Observed directly on `FEAT-2672` (`ll-loop run autodev FEAT-2672`, 2026-07-18):
six consecutive `/ll:confidence-check` passes reported the identical Concern —
"Implementation Steps 1-3 and AC bullet 2 still describe the superseded 'stub
emission + on-demand resolution' framing instead of the corrected mechanism
... Rewrite both sections before implementation" — while multiple
`/ll:refine-issue` passes (including a successful `/ll:spike` that proved the
corrected mechanism against the installed SDK) kept appending new research
findings that explained the correction without ever editing the stale
sections themselves. Readiness stayed pinned at 78/100 across the whole run;
the loop exhausted `run_spike` → `rerun_confidence_after_spike` →
`recheck_after_size_review` and deferred the issue as `low_readiness` after
25m49s / 35 iterations, even though the spike had already retired the
"novel mechanism" risk that was the issue's real architectural blocker.

This wastes an entire autodev run on an issue that a single targeted rewrite
of three sections would have unblocked, and produces a `deferred_reason:
low_readiness` state that mischaracterizes the issue as under-researched
when it was actually over-researched but never reconciled back into its own
body.

## Current Behavior

In `scripts/little_loops/loops/autodev.yaml`, after `run_spike` proves (or
attempts) an unproven mechanism, `rerun_confidence_after_spike` re-runs
`/ll:confidence-check` and routes straight to `enqueue_or_skip` →
`check_spike_needed_before_skip` → `recheck_after_size_review`, which does a
final `ll-issues check-readiness` and defers the issue on failure
(`P[...]:842-867`). There is no comparison between the pre-spike and
post-spike Concerns text/score, and no state that asks `/ll:refine-issue` (or
an equivalent) to reconcile the issue body's Implementation
Steps/AC/Files-to-Modify against the Codebase Research Findings that have
already been appended.

## Expected Behavior

When a confidence-check pass's Readiness score is unchanged (or its Concerns
text substantially repeats) from the immediately preceding pass in the same
run, the loop should recognize this as a "findings accumulated but body not
reconciled" plateau and route to a reconcile step that rewrites the stale
sections from the latest research findings — not append another finding —
before falling through to the existing spike/wire/size-review remedies or
`low_readiness` deferral.

## Proposed Solution

> **Selected: Option C** (2026-07-19, supersedes the earlier Option-A-only
> decision `a8043ad0`). The A/B framing conflated two separable layers.
> **Split them:** `autodev.yaml` keeps the plateau *detection + routing*
> (Option A's orchestration half — loop-owned, reuses `score_stall_gate` +
> the `spike_attempted` guard), and the targeted *reconcile rewrite* becomes a
> new `/ll:reconcile-issue` skill called from the `reconcile_current` state and
> independently user-invocable. See [Option C](#option-c-split-plateau-detection-in-autodev--reconcile-issue-skill)
> and [Decision Rationale](#decision-rationale) below.

### Option C (SELECTED): split — plateau detection in `autodev` + `/ll:reconcile-issue` skill

Decompose the feature along its natural seam:

1. **Detection + routing stays in `autodev.yaml`** (Option A's correct half).
   The plateau guard (`reconcile_attempted` one-shot, mirroring
   `check_spike_needed`'s two-field predicate at `:689`, duplicated at `:816`)
   and the pre/post-spike Readiness comparison (reusing `score_stall_gate` /
   `diff_stall_gate` from `lib/common.yaml:148-203`) live in the loop. A new
   `reconcile_current` state is spliced into the
   `run_spike → rerun_confidence_after_spike → enqueue_or_skip` chain, and
   guarded at the second re-entry point
   `check_spike_needed_before_skip → recheck_after_size_review`.

2. **The rewrite operation becomes a new `/ll:reconcile-issue` skill.** Its
   contract: *targeted, in-place rewrite of Implementation Steps / Acceptance
   Criteria / Files to Modify from the issue's own accumulated Codebase
   Research Findings / Wiring Phase sections; preserve human-authored prose
   (Proposed Solution) and all other sections untouched.* `reconcile_current`
   calls it via `action_type: slash_command`; the state owns no rewrite logic.

**Why the split beats both A and B:**
- The reconcile *operation* is a cross-cutting capability, not an
  autodev-specific one — `autodev.yaml:423-427`, `rn-remediate.yaml:639-684`,
  and `refine-to-ready-issue.yaml:115-120` **all** independently tiptoe around
  the same missing "correct the directive sections without bulldozing
  wiring/prose" primitive (they only have additive `--gap-analysis` or
  destructive `--full-rewrite`). A skill is reusable by all of them; an inline
  autodev state (A) is reusable by none.
- A skill is **user-invocable** (`/ll:reconcile-issue FEAT-2672`), directly
  serving the "do targeted edits on an issue to make corrections" goal. An
  inline state is not; a `refine-issue` flag (B) drags in refine-issue's
  additive-research contract and a 7+-site blast radius.
- Aligns with `.claude/CLAUDE.md` § Development Preferences ("Prefer Skills
  over Agents — simpler, more composable, invocable directly by users or
  other components").
- **Safety / "don't lose important work":** the "only these 3 sections,
  preserve human prose, cite evidence from findings" contract is codified once
  in the skill body and unit-testable in isolation, rather than exercised only
  through a full autodev run. The skill mirrors `/ll:ready-issue`'s output
  contract — a `## CORRECTIONS_MADE` ledger (new `[reconcile]` category),
  `## VALIDATED_FILE`, verdict, and `ll-issues append-log` — so every rewritten
  section is audited, never silently dropped.
- Does **not** touch the shared `/ll:refine-issue` command, sidestepping
  Option B's entire objection.

Cost is Option A's cost (7 routing assertions in
`test_builtin_loops.py::TestAutodevLoop`, 2 ASCII diagrams) **plus** one new
skill file + companion command + its own isolated test
(`test_reconcile_issue_*.py`) — but the skill is the file that makes the
capability real everywhere instead of trapped in one loop.

### Option A (superseded): `reconcile_current` state spliced into `autodev.yaml`

> **Superseded by Option C.** Retained the plateau-detection half; the rewrite
> logic it inlined into the state moves to the `/ll:reconcile-issue` skill so
> it is reusable and user-invocable.

Add a new FSM state (plus a `reconcile_attempted` one-shot guard, mirroring
`check_spike_needed`'s pattern at `autodev.yaml:689`) into the
`run_spike → rerun_confidence_after_spike → enqueue_or_skip` chain, and
duplicate the guard at the second re-entry point
`check_spike_needed_before_skip → recheck_after_size_review`. The
plateau-detection and reconcile logic lives entirely inside the loop;
`/ll:refine-issue` itself is untouched.

- Reuses `score_stall_gate`/`diff_stall_gate` fragments in
  `scripts/little_loops/loops/lib/common.yaml:148-203`, an existing
  append-only history-file + N-consecutive-non-improving-rounds primitive
  already consumed by `oracles/generator-evaluator.yaml`.
- Mirrors the existing `spike_attempted` two-field inline-Python guard
  pattern used at both `check_spike_needed` (`:689`) and
  `check_spike_needed_before_skip` (`:816`).
- Cost: touches all 7 hardcoded `next`/`on_yes`/`on_no`/`on_error` routing
  assertions in `test_builtin_loops.py::TestAutodevLoop` (`:4007`–`:4272`)
  and both copies of the ASCII FSM diagram (`docs/reference/API.md` +
  `docs/guides/LOOPS_REFERENCE.md`).

### Option B (rejected): new `--reconcile` flag on `/ll:refine-issue`

Add a third mode alongside the existing `--gap-analysis` (additive) and
`--full-rewrite` (wholesale) modes — a targeted rewrite of just
Implementation Steps/AC/Files-to-Modify, leaving other sections (e.g.
human-authored Proposed Solution prose) untouched. `autodev.yaml` would call
`/ll:refine-issue --reconcile` from a new state rather than owning the
rewrite logic itself.

- Confirmed no existing mode does a targeted section rewrite today —
  `refine-issue.md` only has the binary additive-vs-wholesale split.
- `autodev.yaml`'s `run_refine` state deliberately avoids `--full-rewrite`
  today ("could bulldoze the wiring changes this branch exists to apply"),
  which is evidence *against* introducing another broad-rewrite-shaped mode
  whose blast radius isn't yet proven safe — this cuts against Option B.
- Cost: needs flag parsing in `commands/refine-issue.md` Step 0 (mirroring
  `--gap-analysis`/`--full-rewrite`), a new numbered section analogous to
  Step 5c, mirrored changes in `skills/ll-refine-issue/SKILL.md`, and a new
  test class in `test_refine_issue_command.py`.

### Decision Rationale

Initial call by `/ll:decide-issue` on 2026-07-19 (Option A). **Revised to
Option C** the same day after a design discussion surfaced a third option the
A/B framing had excluded, plus a `ready-issue` overlap check. Recorded as
decision `1dbf0c23`, superseding `a8043ad0`.

**Selected**: Option C — split: `autodev.yaml` keeps plateau detection
(Option A's orchestration half); the reconcile rewrite becomes a new
`/ll:reconcile-issue` skill.

**Reasoning**: The A/B question conflated two separable layers — **WHERE** the
plateau is detected and routed (pure orchestration; loop-owned; reuses
`score_stall_gate` + the `spike_attempted` guard — Option A was right about
this) and **WHAT** performs the targeted rewrite (a cross-cutting capability).
`/ll:decide-issue` inherited the either/or verbatim from Implementation
Step 1's parenthetical, so the skill option was never scored — it did not lose,
it was never entered. Evidence that reconcile is cross-cutting, not
autodev-specific: `autodev.yaml:423-427`, `rn-remediate.yaml:639-684`, and
`refine-to-ready-issue.yaml:115-120` all independently avoid the same missing
"correct the directive sections without bulldozing wiring/prose" primitive.
An inline autodev state (A) makes that capability non-reusable and
non-user-invocable; a `refine-issue` flag (B) drags in the wrong
additive-research contract and a 7+-site blast radius. A skill is the
composable, user-invocable home (per `.claude/CLAUDE.md` "Prefer Skills over
Agents").

**`ready-issue` overlap check (why not a mode of `/ll:ready-issue`)**: adjacent
but the wrong home. `ready-issue` reconciles *issue ↔ codebase* (accuracy drift
— `[line_drift]`/`[file_moved]`/`[content_fix]` against external truth);
reconcile needs *issue ↔ itself* (directive sections contradicting the issue's
own accumulated findings). In the actual FEAT-2672 plateau `ready-issue` would
**pass** — paths exist, lines are accurate, sections present — so it would
never fire on the condition. It is also a gate (product = verdict) that
`ll-auto`/`ll-parallel` run on *every* issue before implementation; a
findings→directives rewrite must not run on everything (that is the very
"constant re-writes / lose work" hazard this issue guards against). The check
still paid off: the new skill **mirrors `ready-issue`'s output contract** — a
`## CORRECTIONS_MADE` ledger (new `[reconcile]` category), `## VALIDATED_FILE`,
verdict, and `ll-issues append-log` — for auditability.

#### Scoring Summary

Re-scored on the same rubric with two dimensions the A/B table omitted
(Reusable across loops; User-invocable):

| Option | Consistency | Simplicity | Testability | Risk | Reusable | User-invocable | Total |
|--------|-------------|------------|-------------|------|----------|----------------|-------|
| **Option C: split (detect in autodev + skill)** | 3/3 | 2/3 | 3/3 | 3/3 | ✅ | ✅ | **11/12** |
| Option A: inline `reconcile_current` state | 3/3 | 1/3 | 2/3 | 2/3 | ❌ | ❌ | 8/12 |
| Option B: `--reconcile` flag on refine-issue | 1/3 | 1/3 | 2/3 | 1/3 | ⚠️ wrong contract | ✅ | 5/12 |

Option C beats A on the very axes A was picked for: **Risk** (rewrite-safety
contract codified once in the skill body + isolated unit test, not exercised
only through a full autodev run) and **Testability** (skill tested standalone).
The only thing C gives up vs. A is one extra file — the file that makes the
capability real everywhere instead of trapped in one loop.

**Key evidence**:
- Option C detection half = Option A's proven mechanism:
  `autodev.yaml:271-299`'s `check_open_question_progress` already consumes the
  `open_question_stall_gate` fragment family in this exact FSM; the
  `check_spike_needed` two-field guard (`:689`, duplicated `:816`) is the
  direct template for `reconcile_attempted`.
- Option C skill half: `autodev.yaml:423-427`, `rn-remediate.yaml:639-684`,
  `refine-to-ready-issue.yaml:115-120` all independently avoid non-additive
  rewrites of the same three sections — a cross-loop missing primitive a skill
  fills and an inline state cannot.
- Option A (superseded): correct about detection, wrong to inline the rewrite —
  a state is reusable by no other loop and not user-invocable.
- Option B (rejected): no mode in `commands/refine-issue.md` does selective
  multi-section rewrite, and the command is called from 7+ sites carrying
  explicit "could bulldoze"/"destructive" warnings.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/autodev.yaml` — insert the plateau-detection
  and `reconcile_current` states in the `run_spike` (`:710`) →
  `rerun_confidence_after_spike` (`:726`) → `enqueue_or_skip` (`:762`) chain,
  and mirror the guard at the second re-entry point
  `check_spike_needed_before_skip` (`:816`) → `recheck_after_size_review`
  (`:842`), the same way `spike_attempted` is checked at both sites today.
- `commands/refine-issue.md` — if the reconcile mechanism is implemented as
  a new `--reconcile` flag (Implementation Step 1's alternative), add flag
  parsing (Step 0, mirroring `--gap-analysis`/`--full-rewrite` at lines
  47-65) and a new numbered section analogous to Step 5c that rewrites
  Implementation Steps/Acceptance Criteria/Files-to-Modify in place instead
  of appending.

### Dependent Files (no prior-pass state currently exists)
- `skills/confidence-check/SKILL.md` Phase 4.5 "Findings Write-Back" —
  confirmed it **always appends** a fresh `## Confidence Check Notes` block
  before `## Session Log` on every pass; it has no logic to detect or diff
  against a block from a prior pass, so repeated passes accumulate multiple
  such sections rather than comparing them.
- `scripts/little_loops/cli/issues/check_readiness.py` `cmd_check_readiness()`
  — reads only the *current* `confidence_score`/`outcome_confidence`
  frontmatter fields; stateless threshold comparison, no history read.
- `scripts/little_loops/cli/issues/set_scores.py` — always overwrites score
  fields; no versioned/history array is persisted anywhere in the codebase
  (confirmed via grep — no `readiness_history`/`concerns_history` exists).

### Similar Patterns (existing plateau-detection building blocks)
- `scripts/little_loops/loops/lib/common.yaml:148-203` — `score_stall_gate`
  / `diff_stall_gate` / `open_question_stall_gate` fragments are a
  general-purpose "compare current value to an append-only history file,
  detect N-consecutive non-improving rounds" building block, already
  consumed via `evaluate.history_file`/`evaluate.epsilon`/`evaluate.max_stall`
  by `oracles/generator-evaluator.yaml`'s `record_score` (`:129`) /
  `check_stall` (`:148`) states and several viz-generation loops. This is a
  strong reuse candidate instead of hand-rolling new plateau-comparison
  logic for Concerns/Readiness.
- `scripts/little_loops/loops/autodev.yaml` `snap_and_size_review` (`:389`)
  → `enqueue_or_skip` (`:762`) — the existing "stash current issue IDs to a
  `${context.run_dir}/` file, then `comm -13` diff against it later" idiom
  is the established pattern for stashing a pre-spike Readiness
  score/Concerns snapshot to compare against the post-spike pass, if a
  purpose-built history-file fragment isn't used instead.
- `scripts/little_loops/loops/autodev.yaml` `check_spike_needed` (`:689`) —
  the `spike_needed == 'true' AND spike_attempted != 'true'` two-field
  inline-Python guard (needed because `ll-issues check-flag` can't express
  an AND-of-two-fields in one call) is the template for the new
  `reconcile_attempted` one-shot guard; note it is duplicated verbatim at
  `check_spike_needed_before_skip` (`:816`) rather than shared, since that
  is the second re-entry point.
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` `refine_issue`
  (`:183` area, first pass) vs. `refine_followup` (retry pass) — the
  existing precedent for a caller selecting between `--auto` (default,
  budget-consuming) and `--auto --gap-analysis` (additive, budget-exempt)
  based on which pass it is; a new `--reconcile` mode would need the same
  kind of caller-side selection logic if added to `refine-issue.md`.

### Tests
- `scripts/tests/test_builtin_loops.py` — validates all built-in loop YAMLs
  (including `autodev.yaml`) parse and pass FSM validation; the new states
  must pass this gate.
- `scripts/tests/test_autodev_decision_gate.py` — uses `MockActionRunner`
  to test autodev FSM routing in isolation (BUG-2513 precedent); model
  plateau-detection routing tests after this file's structure.
- `scripts/tests/test_confidence_check_skill.py` — covers Phase 4.5
  write-back behavior; would need a new case for repeated-Concerns
  detection if that logic moves into the skill rather than the loop.

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_builtin_loops.py` `TestAutodevLoop` — **will break**,
  not just needs new coverage: it hardcodes literal `next`/`on_yes`/`on_no`/
  `on_error` targets for the exact states this issue inserts states between.
  Confirmed present at: `test_enqueue_or_skip_on_no_routes_to_recheck_after_size_review`
  (`:4007`), `test_recheck_after_size_review_on_yes_routes_to_decide_current`
  (`:4085`), `test_recheck_after_size_review_on_no_routes_to_dequeue_next`
  (`:4093`), `test_rerun_confidence_after_spike_routing` (`:4239`),
  `test_enqueue_or_skip_on_no_routes_to_decide_path_spike_gate` (`:4249`),
  `test_decide_path_spike_gate_routes_to_run_spike` (`:4259`),
  `test_decide_path_spike_gate_falls_through_to_low_readiness_skip`
  (`:4272`). Any `reconcile_current`/plateau-guard state spliced into the
  `run_spike → rerun_confidence_after_spike → enqueue_or_skip` or
  `check_spike_needed_before_skip → recheck_after_size_review` chains must
  update every one of these literal-target assertions in the same commit.
- `scripts/little_loops/issue_lifecycle.py` `class DeferReason(Enum)`
  (`:58-71`) — the single source-of-truth enum for automation deferral
  reason codes (`blocked_by_unmet`, `remediation_stalled`, `low_readiness`,
  `gate_blocked`, `decision_unresolved`). **Only needs a new member if**
  reconcile-exhaustion introduces a *distinct* deferred-reason code rather
  than falling through to `recheck_after_size_review`'s existing
  `low_readiness` write (Implementation Step 3 implies the latter — confirm
  before touching this file).
- `scripts/little_loops/cli/issues/deferred_triage.py` `_REASON_RANK` /
  `_DEFAULT_REASON_RANK` (`:15-22`) — hardcoded priority ordering over the
  same reason-code strings; needs a new rank entry only if a new reason code
  is added per the conditional above.
- `scripts/tests/test_set_status_cli.py`
  `test_set_status_deferred_stamps_autodev_reason_codes`
  (`@pytest.mark.parametrize("reason_code", [...])`, `:300-306`) — extend
  the parametrize list only if a new reason code is added.
- `scripts/tests/test_refine_issue_command.py` — structural, string-slice
  test style (`content.index("### heading")` then substring assertions);
  needs a new test class analogous to its existing flag-doc coverage if
  `--reconcile` is added to `commands/refine-issue.md`. No existing test
  currently asserts on `--full-rewrite`/`--gap-analysis` specifically, so
  this is a new class, not an edit.
- `skills/ll-refine-issue/SKILL.md` — may mirror `commands/refine-issue.md`'s
  flag set for description parity; add `--reconcile` here too if the
  command doc is updated, to avoid the two drifting (this repo has no
  single-source mechanism for that duplication today).

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md` `### autodev` section — contains a complete ASCII
  FSM flow diagram naming the exact chain this issue modifies
  (`check_spike_needed → ... → run_spike → rerun_confidence_after_spike →
  enqueue_or_skip → dequeue_next` and `check_spike_needed_before_skip → ...
  → recheck_after_size_review`), plus narrative paragraphs for prior
  routing changes (e.g. "**Decide-path spike parity (BUG-2654)**") as the
  precedent to follow for a new paragraph, and a "Diagram omissions" list
  that may need a new entry for the plateau-detection guard's abbreviation.
- `docs/guides/LOOPS_REFERENCE.md` — contains a **duplicate copy** of the
  same ASCII diagram (confirmed matching text/line structure against
  API.md); this repo does not single-source it, so both copies need the
  same edit or they will drift.
- `docs/reference/API.md` `deferred-triage` CLI subsection (`:~3726-3733`)
  — enumerates autodev's not-ready exits by literal name
  (`mark_gate_blocked`, `record_decision_unresolved`,
  `recheck_after_size_review`) and states the `_REASON_RANK` priority order
  in prose; update only if a new reason code is introduced (same
  conditional as the `DeferReason` enum above).
- `.claude/CLAUDE.md` "Issue File Format" → "Deferral discriminator
  (ENH-2664)" section — separately enumerates the same automation reason
  codes; update in lockstep with `DeferReason` if a new code is added
  (conditional).

### Constraints (not files to modify, but binding on implementation)
- `scripts/little_loops/fsm/validation.py` MR-1 (non-LLM-evaluator
  requirement) — if the plateau-detection guard is implemented as an LLM
  judgment rather than reusing `score_stall_gate`'s numeric `score_stall`
  evaluator (per Implementation Step 2's own recommendation), `ll-loop
  validate` and `test_builtin_loops.py`'s MR-1 regression gate will fail
  the new state. Reusing `score_stall_gate`/`diff_stall_gate` as suggested
  sidesteps this.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- Confirmed the issue's core claim: no code path anywhere in the repo
  currently stores or diffs a "previous pass" Readiness score or Concerns
  text — `ll-issues check-readiness`/`set-scores` are both stateless
  overwrite-only, and confidence-check's write-back is append-only. The
  plateau-detection logic described in Implementation Step 2 is genuinely
  new, not a currently-broken existing mechanism.
- `refine-issue.md` currently has only a binary additive-vs-wholesale-rewrite
  split (`--gap-analysis` / default `--auto` vs. `--full-rewrite`) — there is
  no existing mode that selectively rewrites *specific* stale sections
  (Implementation Steps/AC/Files-to-Modify) while leaving others (e.g.
  human-authored Proposed Solution prose) untouched. A new `--reconcile`
  mode, per Implementation Step 1's parenthetical alternative, would be a
  third, more targeted mode — not a variant of `--full-rewrite`.
- `autodev.yaml`'s `run_refine` state deliberately avoids `--full-rewrite`
  today ("could bulldoze the wiring changes this branch exists to apply"),
  which suggests the same caution should apply when choosing between
  routing to a general `--full-rewrite` pass vs. a purpose-built
  `reconcile_current`/`--reconcile` step for this issue.

## Implementation Steps

1. **(Decided — Option C, two parts.)**
   a. Create a new `/ll:reconcile-issue` skill (`skills/ll-reconcile-issue/`
      + `commands/reconcile-issue.md` bridge) that rewrites Implementation
      Steps, Acceptance Criteria, and Files to Modify **in place** from the
      issue's own accumulated "Codebase Research Findings" / "Wiring Phase"
      sections, rather than appending another finding bullet. Contract:
      touch only those three directive sections; preserve human-authored
      prose (Proposed Solution) and every other section. Mirror
      `/ll:ready-issue`'s output contract — `## VALIDATED_FILE`, verdict, a
      `## CORRECTIONS_MADE` ledger with a new `[reconcile]` category, and
      `ll-issues append-log <file> /ll:reconcile-issue` — so every rewritten
      section is audited. `disable-model-invocation: true` (invoked
      explicitly by the loop or the user, not auto-fired).
   b. Add a `reconcile_current` state to `autodev.yaml` that calls
      `/ll:reconcile-issue ${context.issue_id}` via
      `action_type: slash_command`. The state owns no rewrite logic — only
      the call, the `reconcile_attempted` guard, and routing.
2. Detect the plateau condition: compare the Readiness score (and/or
   Concerns text) from the confidence-check pass before `run_spike` against
   the one from `rerun_confidence_after_spike`. If unchanged, route to
   `reconcile_current` instead of falling straight through to
   `enqueue_or_skip`. Consider reusing the `score_stall_gate`/
   `diff_stall_gate` fragments in `scripts/little_loops/loops/lib/common.yaml:148-203`
   (an append-only history-file + N-consecutive-non-improving-rounds
   primitive already used by `oracles/generator-evaluator.yaml`) instead of
   hand-rolling new comparison logic.
3. After `reconcile_current`, re-run `/ll:confidence-check` once more before
   continuing to the existing `enqueue_or_skip` / `low_readiness` path, so a
   successful reconciliation gets one more chance to cross the readiness
   threshold.
4. Guard against infinite reconcile loops the same way `check_spike_needed`
   guards `run_spike` (a one-shot flag, e.g. `reconcile_attempted`, checked
   before routing) — see `autodev.yaml:689` for the exact two-field
   inline-Python predicate shape to mirror, and note it must be duplicated
   at `check_spike_needed_before_skip` (`:816`) as well, matching how the
   existing `spike_attempted` guard is checked at both re-entry points.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included
in the implementation:_

5. Update every literal `next`/`on_yes`/`on_no`/`on_error` assertion in
   `scripts/tests/test_builtin_loops.py::TestAutodevLoop` that names a state
   adjacent to the new insertion points (`:4007`, `:4085`, `:4093`, `:4239`,
   `:4249`, `:4259`, `:4272` — see Dependent Files above for the exact test
   names) so they route through the new `reconcile_current`/plateau-guard
   states instead of failing on an unexpected intermediate hop.
6. Add `TestReconcileStructural`/`TestReconcileRouting`-style classes to
   `scripts/tests/test_autodev_decision_gate.py`, mirroring
   `TestSpikeTriageStructural`/`TestAssertDecisionClearedRouting`'s
   dual-flag-predicate + mini-FSM + `_StubRunner` pattern, to cover the new
   `reconcile_attempted`/plateau guard's routing in isolation.
7. Decide whether reconcile-exhaustion reuses `recheck_after_size_review`'s
   existing `low_readiness` deferral (per Implementation Step 3 — no schema
   change needed) or introduces a new distinct reason code. If the latter,
   add the member to `DeferReason` (`issue_lifecycle.py:58-71`), a rank
   entry to `_REASON_RANK` (`deferred_triage.py:15-22`), extend the
   `test_set_status_cli.py` parametrize list, and update the `.claude/CLAUDE.md`
   and `docs/reference/API.md` `deferred-triage` enumerations to match.
8. Update the ASCII FSM flow diagram for autodev in **both**
   `docs/reference/API.md` and `docs/guides/LOOPS_REFERENCE.md` (duplicate,
   not single-sourced) to show the new state(s) in the modified chains.
9. New `/ll:reconcile-issue` skill wiring (Step 1a): create
   `commands/reconcile-issue.md` (full prompt body) + `skills/ll-reconcile-issue/SKILL.md`
   (Codex bridge, mirroring `skills/ll-ready-issue/SKILL.md`'s bridge shape),
   register it in `.claude/CLAUDE.md`'s command catalog under Issue
   Refinement, and add an isolated `scripts/tests/test_reconcile_issue_command.py`
   in the string-slice/anchor-heading style of `test_refine_issue_command.py`
   asserting: only the three directive sections are rewritten, human prose is
   preserved, and the `## CORRECTIONS_MADE` `[reconcile]` ledger is emitted.
   Run `ll-verify-skill-budget` / `ll-verify-skills` / `ll-verify-triggers`
   for the new skill.

## Acceptance Criteria

- [x] An issue whose confidence-check Concerns repeat verbatim (or Readiness
      score is bit-identical) across the pre-spike and post-spike passes
      routes to a reconcile step instead of immediately falling to
      `low_readiness`. — `check_reconcile_needed.on_yes → reconcile_current`.
- [x] The reconcile step measurably rewrites (not just appends to) the
      stale Implementation Steps/AC/Files-to-Modify sections. — codified in
      the `/ll:reconcile-issue` contract.
- [x] Reconcile runs at most once per issue per autodev run (one-shot guard,
      mirroring `check_spike_needed`'s `spike_attempted` pattern). —
      `reconcile_attempted` frontmatter flag.
- [x] Existing `run_spike`/`run_wire`/`low_readiness` remedy paths are
      unaffected for issues that don't hit the plateau condition. —
      `check_reconcile_needed.on_no/on_error → recheck_after_size_review`.

## Related Key Documentation

None linked — `documents.enabled` scan did not surface a match for this
loop-internals change; see `docs/generalized-fsm-loop.md` and
`docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` if wiring this by hand.

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-07-19_

**Readiness Score**: 90/100 → READY
**Outcome Confidence**: 61/100 → below threshold

### Outcome Risk Factors
- Deep per-site complexity: Implementation Step 1 leaves an unresolved
  either/or on the core mechanism — a `reconcile_current` state spliced into
  `autodev.yaml`'s two hardcoded routing chains, **or** a new `--reconcile`
  mode on `/ll:refine-issue`. This is an open decision point that should be
  resolved before implementing, since Steps 7 and 9 branch conditionally on
  which option is chosen.
- Broad enumeration across sites: 7 named test assertions in
  `test_builtin_loops.py::TestAutodevLoop` hardcode literal `next`/`on_yes`/
  `on_no` routing targets for the exact states this issue splices between,
  plus a duplicated ASCII FSM diagram in both `docs/reference/API.md` and
  `docs/guides/LOOPS_REFERENCE.md` that must be updated in lockstep.

## Session Log
- `/ll:manage-issue` - 2026-07-19T16:06:20 - `51294082-3486-485e-8258-2646fa614805.jsonl`
- `/ll:confidence-check` - 2026-07-19T15:20:00 - `ad448797-4a95-4c8e-85fe-70f1c22b1af1.jsonl`
- `/ll:decide-issue` - 2026-07-19T15:11:15 - `bdc7a718-e90d-48bf-9aca-651964e561d6.jsonl`
- `/ll:decide-issue` - 2026-07-19T15:10:44 - `bdc7a718-e90d-48bf-9aca-651964e561d6.jsonl`
- `/ll:decide-issue` - 2026-07-19T15:00:44 - `b103a49d-8bb0-489f-b75c-2dd55399009d.jsonl`
- `/ll:decide-issue` - 2026-07-19T13:46:47 - `48a58d9b-f092-4ccb-aea8-5309de16aa8f.jsonl`
- `/ll:confidence-check` - 2026-07-19T14:00:00Z - `12af38e2-8da7-4694-9396-9884588d42f0.jsonl`
- `/ll:wire-issue` - 2026-07-19T13:42:04 - `6f201992-cec5-4e3b-9cba-53f350c0b513.jsonl`
- `/ll:refine-issue` - 2026-07-19T13:36:22 - `7cf9279a-28a4-479f-ad9b-9c2aa28f89f9.jsonl`
- `/ll:capture-issue` - 2026-07-19T04:38:59Z - captured from conversation diagnosing why `FEAT-2672` was deferred (`ll-loop run autodev FEAT-2672`, 2026-07-18)

## Resolution

Implemented **Option C** (`/ll:manage-issue enhancement improve ENH-2689`, 2026-07-19).

**Detection + routing (autodev.yaml):** Rather than splicing into the
`run_spike → rerun_confidence_after_spike → enqueue_or_skip` chain (Option A's
7-edge blast radius), the plateau gate was interposed at the **single point both
the spike-triage and decide/size-review paths funnel through before the
`low_readiness` deferral** — `check_spike_needed_before_skip.on_no`. This cut the
breaking-test surface from the wired 7 assertions to 3.
- `check_spike_needed` / `check_spike_needed_before_skip` now snapshot the
  pre-spike `confidence_score` to `${context.run_dir}/autodev-pre-spike-readiness.txt`
  on the spike branch.
- New `check_reconcile_needed` (shell_exit, non-LLM → MR-1 clean): fires when the
  snapshot is bit-identical to the post-spike Readiness AND `reconcile_attempted`
  is not set; else falls through to `recheck_after_size_review` unchanged.
- New `reconcile_current` (`/ll:reconcile-issue`, slash_command) →
  `rerun_confidence_after_reconcile` (`/ll:confidence-check`) →
  `recheck_after_size_review`. Reconcile-exhaustion reuses the existing
  `low_readiness` deferral — **no new `DeferReason`** (Wiring Step 7 conditional
  resolved to "reuse").

**Rewrite operation (new `/ll:reconcile-issue` skill):** `commands/reconcile-issue.md`
+ `skills/ll-reconcile-issue/` (SKILL.md bridge + `agents/openai.yaml`), registered
in `.claude/CLAUDE.md`. Targeted in-place rewrite of the three directive sections
from the issue's own findings; mirrors `/ll:ready-issue`'s output contract with a
new `[reconcile]` CORRECTIONS_MADE category; sets `reconcile_attempted: true`
(one-shot guard, surfaced via `show.py --json`). `disable-model-invocation: true`.

**Docs:** Only `docs/guides/LOOPS_REFERENCE.md` carried the autodev ASCII diagram
(diagram + narrative updated). Wiring analysis claimed a duplicate in
`docs/reference/API.md`; verified by grep that **no such diagram exists there** —
the claim was stale, so API.md needed no edit.

**Tests:** updated 3 breaking routing assertions (`test_builtin_loops.py` ×2,
`test_autodev_decision_gate.py` ×1); added reconcile structural + mini-FSM routing
coverage in both loop test files; new `test_reconcile_issue_command.py`; new
`reconcile_attempted` cases in `test_show.py`. Full suite: 15,473 passed (the lone
failure, `test_context_fallbacks_match_selector_defaults`, is pre-existing and
unrelated — it concerns `refine-to-ready-issue.yaml`'s `outcome_threshold`).

## Status

**Done** | Created: 2026-07-19 | Completed: 2026-07-19 | Priority: P2
