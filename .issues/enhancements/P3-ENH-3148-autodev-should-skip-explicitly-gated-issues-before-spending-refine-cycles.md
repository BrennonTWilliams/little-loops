---
id: ENH-3148
type: ENH
title: autodev should skip explicitly gated issues before spending refine cycles
priority: P3
status: done
verify_verdict: VALID
testable: true
reconcile_attempted: true
discovered_by: ll-issues-create
discovered_date: '2026-08-10'
captured_at: '2026-08-10T23:10:04Z'
completed_at: '2026-08-11T07:08:58Z'
labels:
- loops
- autodev
relates_to:
- BUG-3146
- BUG-3147
size: Very Large
confidence_score: 92
outcome_confidence: 68
score_complexity: 16
score_test_coverage: 22
score_ambiguity: 10
score_change_surface: 20
---

# ENH-3148: autodev should skip explicitly gated issues before spending refine cycles

## Summary

`autodev` currently discovers that an issue is un-implementable only *after*
running the full remediation ladder. Run `.loops/runs/autodev-20260810T171140/`
spent 36 iterations / 38m 37s / ~$4.48 on FEAT-3145 — 8 `refine_current`
invocations, `run_size_review`, `resolve_decision_direct`, `reconcile_current`
and two confidence re-runs — before deferring it `low_readiness` at readiness
65/85.

None of that work could have succeeded. FEAT-3145's first body heading is
`## ⚠ Gated — do not implement before the tier-3 evidence gate opens`; its
Acceptance Criteria are the literal placeholder "(To be settled when the gate
opens — captured now only as intent.)"; and its own confidence-check concluded
"Wait for (or deliberately trigger) the tier-3 evidence gate — this is the
dominant blocker; **further research does not resolve it**." The readiness score
was capped by a policy decision recorded in the parent EPIC, not by any
information a refine pass could supply.

Proposal: add a cheap deterministic pre-dequeue check that recognizes an
explicitly gated issue (gate language in the body, and/or placeholder
Acceptance Criteria) and defers it immediately with a distinct reason code
(e.g. `blocked_by_gate`) instead of entering the remediation ladder. This keeps
the deferral honest — the current `low_readiness` code is technically true but
misleading, since it implies more refinement would help.

Design questions to settle:
- Reason-code choice, and whether it needs a `docs/reference/DEFERRAL_CODES.md`
  entry.
- Detection signal: reuse/share the gate-phrase matcher from BUG-3147 rather
  than adding a third independent regex for the same concept.
- Whether an unopened parent-EPIC gate should be readable structurally (a
  frontmatter field on the EPIC) instead of by grepping prose — prose matching
  is what BUG-3147 shows to be fragile.


## Current Behavior

Every dequeued issue enters the full remediation ladder. An issue that is gated
by policy — not by missing information — is discovered to be un-implementable
only at the terminal `low_readiness` branch, after refine / size-review /
decide / reconcile passes have all run and been paid for.

## Expected Behavior

A gated issue is recognized before the ladder starts and deferred immediately
with a distinct, honest reason code. `low_readiness` is reserved for issues
where more refinement genuinely could have helped.

## Motivation

Two costs, both measured on run `.loops/runs/autodev-20260810T171140/`:

- **Money and time**: ~$4.48 and 38m37s across 36 iterations, all of it
  unable to change the outcome.
- **Honest reporting**: the issue was deferred `low_readiness`, which reads as
  "needs more refinement". The truthful reason is "blocked on an external
  evidence gate that no amount of refinement opens" — the issue's own
  confidence-check says exactly this.

## Proposed Solution

Add a deterministic pre-dequeue check (no LLM in the routing chain, per MR-1)
that recognizes a gated issue and defers with a distinct reason code such as
`blocked_by_gate`, bypassing the remediation ladder.

Detection signals, in preference order:
1. **Structural** — an unopened gate declared in frontmatter on the issue or
   its parent EPIC. Preferred: machine-readable and unambiguous.
2. **Prose** — gate-phrase matching over the body, sharing BUG-3147's matcher
   rather than adding a third copy of the same regex.
3. **Placeholder ACs** — an `## Acceptance Criteria` section consisting only of
   a deferral note ("To be settled when...") is independently disqualifying,
   since the gate cannot be verified either way.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/autodev.yaml` — new check on the dequeue path,
  before the remediation ladder
- `docs/reference/DEFERRAL_CODES.md` — register the new reason code
- No shared gate-matcher location exists to reference: BUG-3147 kept `GATE_MARKER`
  inline (`autodev.yaml:2059-2062`) rather than extracting it, and named this
  issue's landing — conditioned on choosing prose matching — as the trigger for
  extraction, not a prerequisite already done. If prose matching is chosen, reuse
  the regex verbatim inline; if this issue is the one that finally extracts it,
  that extraction is new work here, not a location to cite from BUG-3147.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/issue_lifecycle.py` — add `BLOCKED_BY_GATE = "blocked_by_gate"` to the `DeferReason` enum (lines 65-88); this is the actual registration point, not just a narrative reference [Agent 1/2 finding]
- `scripts/little_loops/cli/issues/deferred_triage.py` — register `blocked_by_gate` in `_REASON_RANK` (lines 15-36) for correct triage sort order; safe to omit (falls to `_DEFAULT_REASON_RANK = 8`) but breaks the "every prior code was added there" convention [Agent 1 finding]

### Dependent Files (Callers/Importers)
- Deferred-triage consumers that switch on `deferred_reason` will see a new
  code; check for exhaustive matches over the existing set.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/issues/set_status.py:18-122` — `_DEFERRAL_REASON_CODES` frozenset is derived from `DeferReason`, so it self-updates; no edit needed, but confirms this is the "exhaustive match" surface the existing bullet gestures at [Agent 1/2 finding]
- `scripts/little_loops/cli/issues/__init__.py:862` — generates `ll-issues set-status --reason` argparse choices from `sorted(_DEFERRAL_REASON_CODES | _CLOSED_REASON_CODES)`; picks up the new code automatically once `DeferReason` is updated, no edit needed [Agent 1 finding]
- `scripts/little_loops/cli/issues/show.py:435` — displays `deferred_reason` in `ll-issues show --json`; no code change needed, but confirms the new code surfaces there automatically [Agent 1 finding]

### Similar Patterns
- The existing `design_gate_failed` / `decision_unresolved` /
  `readiness_stagnated` branches in `recheck_after_size_review` are the
  precedent for a distinct-reason deferral with its own code.

### Tests
- `scripts/tests/test_builtin_loops.py` — assert a gated issue defers with the
  new code without entering refine.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_builtin_loops.py::test_check_blockers_at_dequeue_routing` (line 5228) — **will break**: currently asserts `on_no`/`on_error` both target `refine_current`; once the new gate-check state is spliced in, both must retarget the new state's name [Agent 3 finding]
- `scripts/tests/test_builtin_loops.py::test_check_decision_at_dequeue_routes_to_check_blockers_at_dequeue` (line 5212) — clone this graph-edge pattern for a new test asserting the new state is correctly wired between `check_blockers_at_dequeue` and `refine_current` [Agent 3 finding]
- `scripts/tests/test_builtin_loops.py::test_mark_gate_blocked_defers_via_set_status` / `test_mark_gate_blocked_advances_queue_without_failing` (lines 5824, 5811) — clone this trio (deferral-via-set-status assertion, ledger-write assertion, `next`-target assertion) for the new state's `--reason blocked_by_gate` write [Agent 3 finding]
- `scripts/tests/test_autodev_loop.py::test_marker_literals_present_in_action` (line 689) — clone if the new state reuses the `GATE_MARKER` phrase list, pointed at the new state's action text instead of `recheck_after_size_review`'s [Agent 3 finding]
- `scripts/tests/test_set_status_cli.py::test_set_status_deferred_stamps_autodev_reason_codes` (parametrize list, lines 337-345) — **gap, not break**: hand-maintained literal list of reason codes, not enum-derived; `blocked_by_gate` must be added explicitly or this CLI-acceptance guard never exercises it [Agent 2/3 finding]
- `scripts/tests/test_issue_lifecycle.py` — `TestDeferReasonEnum` class (line 1977) — add a new member-exists assertion for `DeferReason.BLOCKED_BY_GATE`, mirroring `test_design_gate_failed_member_exists_with_expected_value` [Agent 1/3 finding]

### Documentation
- `docs/reference/DEFERRAL_CODES.md`

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md:2385-2388` — `ll-issues deferred-triage` section documents the literal rank order of reason codes in prose; needs a `blocked_by_gate` slot if it's registered in `_REASON_RANK` [Agent 2 finding]
- `docs/reference/API.md:4280-4288` — near-identical rank-order prose, independently maintained (no shared source of truth with CLI.md) [Agent 2 finding]
- `docs/guides/LOOPS_REFERENCE.md` — dequeue-chain state table/diagram (~lines 468-486, 1059-1065) documents the FSM state sequence the new gate-check state is inserted into; analogous to how rn-implement's pre-dequeue gate (ENH-2406) is documented there [Agent 2 finding]

### Configuration
- Possibly an opt-out, if skipping gated issues should be defeasible.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-11 — based on codebase analysis:_

- **Dequeue chain** (`scripts/little_loops/loops/autodev.yaml`): `dequeue_next` (line 84) → `check_status_at_dequeue` (line 169) → `check_decision_at_dequeue` (line 234) → `check_blockers_at_dequeue` (lines 249-360, `on_no`/fallthrough → `skip_blocked` at line 360) → `refine_current` (line 376, first remediation-ladder state). The natural insertion point is a new state chained between `check_blockers_at_dequeue` and `refine_current`, mirroring that state's own three-gate shape (deterministic shell/python predicate, `fragment: shell_exit`, `on_yes`/`on_no`/`on_error`).
- **Deferral-write precedent**: `recheck_after_size_review` (state body at lines 1901-2105) is the current sole emitter of `low_readiness`/`design_gate_failed`/`decision_unresolved`/`readiness_stagnated`. Every deferral write follows the same idiom (not a shared helper — copied per site): `echo "$ID  <reason>" >> ${context.run_dir}/autodev-skipped.txt`, `rm -f ${context.run_dir}/autodev-inflight`, `ll-issues set-status "$ID" deferred --by automation --reason <reason> 2>/dev/null || true`, `exit 1`. Some sites (`mark_gate_blocked` line 925-947, `record_decision_unresolved` line 656-679) additionally re-check `status` isn't already `done|completed|cancelled` before deferring (the "BUG-2729 postmortem" guard); the shorter branches inside `recheck_after_size_review` (lines 1995-1998, 2016-2019, 2021-2025, 2097-2100) omit that re-check.
- **`GATE_MARKER` matcher** (`autodev.yaml:2059-2062`): `grep -qiE 'do not start otherwise|measurement \(gate\)|pre-implementation measurement|⚠ Gated|do not implement before|evidence gate|gate opens|is explicitly gated' "$ISSUE_FILE"`. It currently only biases `recheck_after_size_review`'s remedy selector (spike vs. reconcile) — it does not itself defer or bypass the ladder. **BUG-3147 (done, direct predecessor) explicitly decided to keep this matcher inline rather than extract it to a shared Python helper**, citing 7+ existing inline-`grep -qiE`-against-`$ISSUE_FILE` call sites as the established idiom across five loop YAMLs, and named this issue's landing as "the concrete trigger point for extraction — not before" if it commits to prose matching as its detection signal.
- **No structural gate field exists**: no `gate:`/`gated:`/`blocked_until:` frontmatter property in `scripts/little_loops/config-schema.json`, no matching `FLAG_RULES` entry in `scripts/little_loops/cli/issues/set_flags.py`, and no such key found in any `.issues/` frontmatter. Gate declaration today is prose-only (e.g. FEAT-3145's `## ⚠ Gated — ...` heading). Detection signal #1 (structural) in this issue's own Proposed Solution is therefore not implementable without first adding that frontmatter field — it does not yet exist to read.
- **`deferred_reason` enum**: `DeferReason` in `scripts/little_loops/issue_lifecycle.py:65-88`. Existing members include `GATE_BLOCKED = "gate_blocked"` (line 77) — **already taken by a different concept**: it's emitted by `mark_gate_blocked` (`autodev.yaml:925-947`) for a *post-implementation* learning-gate block (unproven external-API deps found during `ll-auto --only`), not this issue's pre-dequeue evidence/AC-placeholder gate. This issue's proposed code `blocked_by_gate` is a distinct string and does not collide, but the near-identical name is worth flagging explicitly to avoid confusion during implementation/review.
- **Reason-code validation**: `scripts/little_loops/cli/issues/set_status.py:18-122` derives `_DEFERRAL_REASON_CODES` from `DeferReason` (comment at lines 18-19: "derived from `DeferReason` so the two can't drift out of lockstep") but only cross-validates *known* codes against target status — an unregistered new string like `blocked_by_gate` would be silently accepted by `ll-issues set-status` today without adding it to the enum. Registering it in `DeferReason` is nonetheless the established convention (every prior code was added there).
- **`docs/reference/DEFERRAL_CODES.md`** is pure documentation (a manually maintained `| Code | Emitted by | Meaning |` table, lines 14-25) — no code parses or validates against it. No automated test enforces the table stays in sync with actually-emitted codes.
- **`_REASON_RANK`** in `scripts/little_loops/cli/issues/deferred_triage.py:15-36` is a second place a new code should (not must — falls through to `_DEFAULT_REASON_RANK = 8`) be registered for correct triage sort order.
- **Placeholder-AC detection**: no existing helper detects "Acceptance Criteria section containing only placeholder/deferral prose." `scripts/little_loops/cli/issues/check_acceptance_criteria.py`'s `_find_manual_criteria()` (lines 57-86) only scans checkbox items (`- [ ]`/`- [x]`) for manual-verification verbs — it would not match a bare parenthetical placeholder sentence with no checkbox prefix, and it's wired only into `refine-to-ready-issue.yaml`'s post-refine gate, not autodev's pre-dequeue path. `issue_parser.py`'s `_OPEN_QUESTION_SIGNAL_RE` (lines 1444-1462, includes `\bTBD\b`) is scoped to `_OPEN_QUESTION_SECTIONS` (lines 1469-1477), which does **not** include "Acceptance Criteria."

_Added by `/ll:refine-issue` — 2026-08-11 — based on codebase analysis:_

- **`DeferReason` enum members are inline `NAME = "value"` in insertion order with an inline comment citing the originating issue ID** (`issue_lifecycle.py:65-88`) — the convention a `BLOCKED_BY_GATE = "blocked_by_gate"` addition follows exactly.
- **`_REASON_RANK` registration and CLI-acceptance coverage are two independently hand-maintained lists, not derived from the enum** — `deferred_triage.py:15-36`'s dict and `test_set_status_cli.py:337-345`'s parametrize list both require an explicit new entry; `_DEFERRAL_REASON_CODES` (`set_status.py:20`) is the only one of the three that auto-derives (`frozenset(r.value for r in DeferReason)`, asserted by `test_design_gate_failed_is_derived_into_set_status_reason_codes`, `test_issue_lifecycle.py:1985-1992`). Omitting the other two silently under-registers the new code without any test failing to say so.
- **Existing FSM-wiring test shapes to clone**: graph-edge assertions read `on_yes`/`on_no`/`on_error` off the raw parsed YAML dict (`test_check_decision_at_dequeue_routes_to_check_blockers_at_dequeue`, `test_builtin_loops.py:5212-5226`); deferral-write assertions split into a ledger/message-content check and a `set-status` shape check as two separate test functions (`test_mark_gate_blocked_advances_queue_without_failing` / `test_mark_gate_blocked_defers_via_set_status`, `test_builtin_loops.py:5811-5830`); enum-member tests pair a value-exists assertion with a derivation assertion inside one `TestDeferReasonEnum`-style class per addition batch, docstring citing the issue ID (`test_issue_lifecycle.py:1977-1992`).
- **No FSM-execution trace test exists in this codebase for "state X was never entered."** The only precedent is a string-index ordering proxy on the compiled action text (`test_gate_check_precedes_ambiguity_fallback`, `test_autodev_loop.py:703-707` — asserts one sentinel's `str.index()` precedes another's within the same action block). A test for "a gated issue defers without any `refine_current` invocation" (this issue's own Success Metric) will need either this same index-ordering proxy applied to the new state's position in the compiled graph, or a new FSM-execution harness — no existing test exercises actual state transitions.
- **Placeholder-AC detection confirmed absent, with the closest near-miss ruled out by scope, not by phrase vocabulary**: `_OPEN_QUESTION_SIGNAL_RE` (`issue_parser.py:1444-1462`) already contains phrases that would textually match FEAT-3145's placeholder ("to be determined"-family alternatives), but `_OPEN_QUESTION_SECTIONS` (`issue_parser.py:1469-1477`) — the tuple scoping where that regex is allowed to fire — does not include `Acceptance Criteria`. Extending that tuple is not sufficient on its own since `_find_manual_criteria()` (`check_acceptance_criteria.py:57-86`) and the open-question regex are two separate, unconnected code paths with no shared call site combining `_section_body(content, "Acceptance Criteria")` with either.

## Program Design

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-11 — based on codebase analysis:_

_Added by `/ll:refine-issue` — 2026-08-11 — based on codebase analysis:_

- **Sibling dequeue-gate state templates** — three shapes coexist in `autodev.yaml` for a deterministic predicate state, and a new gate state matches one of them, not something novel: `check_decision_at_dequeue` (`autodev.yaml:234-247`) uses `fragment: shell_exit` (exit-code evaluate, defined `loops/lib/common.yaml:15-21`) for a single-command boolean; `check_blockers_at_dequeue` (`autodev.yaml:249-358`) uses `action_type: shell` + `evaluate: {type: output_contains, pattern: "BLOCKED"}` with a sentinel string printed by an inline `python3` heredoc, plus `capture: blockers_status`; `mark_gate_blocked` (`autodev.yaml:925-947`) is the closest template for a state that both matches a gate condition *and* writes `deferred` status in the same action body.
- **Fail-open is the binding contract, not a convention to weigh** — every existing predicate state's doc comment states it explicitly (`check_status_at_dequeue` lines 191-194, `check_blockers_at_dequeue` lines 265-267: "an unresolvable ID, missing status, or parse error yields PROCESS/READY so a gate error never blocks the queue"), and every `on_error` routes to the "proceed" edge, never to a skip/defer edge. A new gate state's `on_error` must route to `refine_current`, matching this pattern exactly, not just "mirror the shape" loosely.
- **`GATE_MARKER`'s existing use is a biasing input inside a multi-branch remedy dispatcher, not a standalone boolean** — at `autodev.yaml:2059-2062` it feeds `recheck_after_size_review`'s remedy selector (`autodev.yaml:2067-2083`) only as a lower-priority `elif` behind `spike_attempted`/`reconcile_attempted`/`CONTRA_ONLY` checks, all of which presuppose the ladder has already run. The bare `grep -qiE '...'` regex pattern list is reusable verbatim in a new pre-dequeue state's own action; the surrounding FIRED-guard and priority-ordering control flow is not, since nothing has been attempted yet at pre-dequeue time.
- **Two deferral-write idioms disagree on the BUG-2729 status-recheck guard, and no test forces either** — `mark_gate_blocked` (`autodev.yaml:925-947`) and `record_decision_unresolved` (`autodev.yaml:656-679`) re-read `ll-issues show --json` status and skip the `set-status` mutation if already `done`/`completed`/`cancelled` before deferring; the four `recheck_after_size_review` branches (lines 1995-1998, 2016-2019, 2021-2025, 2097-2100) write `set-status ... deferred` directly with no re-check. Since a pre-dequeue gate state runs immediately after `check_status_at_dequeue` has already filtered `done`/`cancelled`/`deferred` upstream, and before any remediation state that could race the issue to `done` in the same pass, no existing precedent forces the guard here — but it remains available to copy if the implementer wants defense against `in_progress`/`blocked` issues (statuses `check_status_at_dequeue` does not filter).
- **No code path anywhere in `autodev.yaml`'s dequeue chain reads a parent EPIC's frontmatter.** The only `epic` references inside the dequeue region are `check_blockers_at_dequeue`'s `.issues/epics` glob directory (used to locate the *current* issue's own file when it is itself an epic — line 290), and unrelated decomposition-bookkeeping states (`check_parent_resolved`, ~lines 1029-1030, 1356) that run after `refine_current`, not before it. `issue_lifecycle.py` has zero EPIC awareness. The only EPIC-frontmatter-aware CLI paths repo-wide are `epic_progress.py` and `epic_consistency.py`, neither invoked from autodev's dequeue chain. A structural EPIC-gate-propagation mechanism (Design Questions, item 2) has no adjacent code to extend from — it is new territory, not a wiring gap.

### Types

- `DeferReason` (`scripts/little_loops/issue_lifecycle.py:65-88`) — closed str enum; a new `BLOCKED_BY_GATE = "blocked_by_gate"` member is the registration point for the new reason code (see `set_status.py`'s frozenset derivation, `deferred_triage.py`'s `_REASON_RANK`).

### Signatures

- `design_gate_failed(gaps: FormatGaps) -> bool`
  Existing analogous predicate (`scripts/little_loops/issue_parser.py:322-336`) — precedent for a single-owner boolean predicate consumed via a `ll-issues` CLI subcommand rather than reimplemented inline in YAML. Note the codebase's dominant convention for phrase-matching (per BUG-3147's decision) is the opposite: inline `grep -qiE '...' "$ISSUE_FILE"`, not a Python helper. Both idioms are live precedent; which one the new gate check follows is the load-bearing choice this issue's own "Design Questions" section flags as unresolved.
- `cmd_set_status(args: Namespace) -> int`
  `scripts/little_loops/cli/issues/set_status.py:105-122` — the write every existing deferral state invokes via the `ll-issues set-status "$ID" deferred --by automation --reason <CODE>` shell call; a new pre-dequeue gate state would call this identically with `--reason blocked_by_gate`.

### Call Path

`DeferReason` (`scripts/little_loops/issue_lifecycle.py:65-88`) -> `cmd_set_status` (`scripts/little_loops/cli/issues/set_status.py:105-122`) -> `_DEFERRAL_REASON_CODES` (`set_status.py:18-19`, derived from `DeferReason` for validation)

FSM-level (new identifiers, not required to resolve): `check_blockers_at_dequeue` (`autodev.yaml:249`) -> [new pre-dequeue gate state] -> `on_yes`: new deferral state (writes `ll-issues set-status ... --reason blocked_by_gate`, mirrors `mark_gate_blocked` at `autodev.yaml:925-947`) -> `dequeue_next` (`autodev.yaml:84`); `on_no`/`on_error`: `refine_current` (`autodev.yaml:376`, unchanged fallthrough — fail-open matches the three existing dequeue gates' posture).

### Decision Rules

- **Gate kind**: a pre-dequeue deferral gate that recognizes an issue is explicitly gated by policy (prose gate-language and/or placeholder Acceptance Criteria) rather than by missing information.
- **Inputs**: the issue's resolved file content (`$ISSUE_FILE`, same variable the existing `GATE_MARKER` matcher at `autodev.yaml:2059` already resolves) and, per Detection signal #3, the parsed `## Acceptance Criteria` section body.
- **Literal values — prose signal**: not yet decided by this issue. The existing `GATE_MARKER` alternation (`autodev.yaml:2059-2062`, 8 phrases as of commit `033c6c28`) is available to reuse verbatim (inline, per BUG-3147's precedent) or to extract as this issue's own trigger for that extraction — Design Questions leaves this open.
- **Literal values — placeholder-AC signal**: no existing detector or literal pattern in the codebase matches this (see Integration Map finding). `_OPEN_QUESTION_SIGNAL_RE` (`issue_parser.py:1444-1462`) contains `\bTBD\b` and similar alternatives but is scoped away from the Acceptance Criteria section.
- **Escape hatch / dismissal**: none specified yet — this issue's own "Configuration" row in Integration Map notes "Possibly an opt-out, if skipping gated issues should be defeasible" as unresolved.
- **Reason-code collision to avoid**: the new code must be a distinct string from the existing `gate_blocked` (`issue_lifecycle.py:77`), which denotes a different, post-implementation learning-gate condition. This issue's proposed `blocked_by_gate` already avoids the collision by name, but the near-identical spelling is a live footgun during implementation and review.

## Implementation Steps

1. Decide the detection signal (the load-bearing choice, see Design Questions).
   These are not two equally-weighted options: no `gate:`/`gated:`/
   `blocked_until:` frontmatter property exists anywhere today (schema,
   `set_flags.py`'s `FLAG_RULES`, or any `.issues/` file), so choosing
   structural detection means adding that field first — new schema surface,
   not a read of something that already exists. Prose matching can reuse the
   existing `GATE_MARKER` regex (`autodev.yaml:2059-2062`) verbatim inline,
   per BUG-3147's precedent of keeping it inline and naming this issue as the
   trigger point for extraction if prose matching is chosen.
2. Add the pre-dequeue check and reason code; register it in
   `DEFERRAL_CODES.md`.
3. Add a regression test asserting no refine states run for a gated issue;
   verify with `python -m pytest scripts/tests/`.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Add `BLOCKED_BY_GATE = "blocked_by_gate"` to `DeferReason` (`scripts/little_loops/issue_lifecycle.py:65-88`)
- Register `blocked_by_gate` in `_REASON_RANK` (`scripts/little_loops/cli/issues/deferred_triage.py:15-36`)
- Update `test_check_blockers_at_dequeue_routing` (`scripts/tests/test_builtin_loops.py:5228`) — retarget `on_no`/`on_error` from `refine_current` to the new gate-check state's name
- Add a graph-edge wiring test cloning `test_check_decision_at_dequeue_routes_to_check_blockers_at_dequeue` (`test_builtin_loops.py:5212`) for the new state
- Add deferral-write tests cloning `test_mark_gate_blocked_defers_via_set_status` / `test_mark_gate_blocked_advances_queue_without_failing` (`test_builtin_loops.py:5824`, `5811`) for `--reason blocked_by_gate`
- Add `blocked_by_gate` to the parametrize list in `test_set_status_deferred_stamps_autodev_reason_codes` (`scripts/tests/test_set_status_cli.py:337-345`)
- Add a member-exists assertion for `DeferReason.BLOCKED_BY_GATE` in `TestDeferReasonEnum` (`scripts/tests/test_issue_lifecycle.py:1977`)
- Update the rank-order prose in `docs/reference/CLI.md:2385-2388` and `docs/reference/API.md:4280-4288`
- Update the dequeue-chain state diagram in `docs/guides/LOOPS_REFERENCE.md` (~lines 468-486, 1059-1065)

## Design Questions

- Reason-code name, and its `docs/reference/DEFERRAL_CODES.md` entry.
- Should an unopened parent-EPIC gate be structural (a frontmatter field on the
  EPIC) rather than grepped prose? BUG-3147 is direct evidence that prose
  matching for this exact concept is fragile.
- Is `deferred` the right terminal state, given it is non-terminal for
  dependency edges? A gated issue should become workable the moment the gate
  opens.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-11 — based on codebase analysis:_

- **On "should the gate matcher be shared with BUG-3147's" — resolved by BUG-3147 itself.** BUG-3147 (now `done`) already adjudicated this exact question in its Decision Rationale: it kept the `GATE_MARKER` matcher inline (`autodev.yaml:2059-2062`), scored inline-widen 12/12 vs. extract-to-module 5/12, and named *this issue's landing* as "the concrete trigger point for extraction — not before," conditioned on this issue committing to prose matching as its detection signal. So the question is no longer open in the abstract — it is scoped to whether ENH-3148 chooses prose matching at all.
- **On "should an unopened parent-EPIC gate be structural" — no frontmatter mechanism exists today to make it structural.** No `gate:`/`gated:`/`blocked_until:` property exists in `scripts/little_loops/config-schema.json`, `set_flags.py`'s `FLAG_RULES`, or any `.issues/` frontmatter observed. Choosing the structural signal (Detection signal #1 in Proposed Solution) means adding that field first — it is new schema surface, not a read of something that already exists.
- **No existing test asserts "state X was never entered" via FSM execution.** `test_autodev_loop.py`/`test_builtin_loops.py`'s only precedent for this kind of assertion is string-index ordering on the compiled YAML action text (e.g. `test_gate_check_precedes_ambiguity_fallback`, `test_design_branch_precedes_readiness_stagnated_branch`) — asserting one sentinel string's index precedes another's within the same action block, not a state-machine trace. The Success Metric "a gated issue defers without any refine_current invocation" will need either this same index-ordering proxy (assert the gate state's `on_yes` deferral path precedes `refine_current` in the compiled state graph) or a new FSM-execution-based test harness, whichever the implementer judges more reliable.

## Impact

- **Priority**: P3 - Pure waste-avoidance; no incorrect state is produced today,
  only misleading reason codes and spend.
- **Effort**: Medium - The check is small, but the detection-signal choice and
  the reason-code registration make it more than a one-liner.
- **Risk**: Medium - A false positive silently skips a workable issue. The
  detection predicate needs to be conservative and tested.
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-08-10 | Priority: P3

## Scope Boundaries

**In scope**: the pre-dequeue gate check, its reason code, and registration in
`DEFERRAL_CODES.md`.

**Out of scope**: fixing the downstream remedy dispatcher (BUG-3146), widening
the gate-phrase matcher itself (BUG-3147), and any change to how gates are
declared on EPICs beyond reading one if it already exists.

## Success Metrics

- A gated issue defers without any `refine_current` invocation.
- Its `deferred_reason` names the gate, not readiness.
- Re-running `autodev` on FEAT-3145 costs a small fraction of the $4.48
  baseline.

## Verification Notes

_Added by `/ll:verify-issues` — 2026-08-11:_

Two factual inaccuracies found in the Codebase Research Findings; the rest of
the issue's file/line citations (autodev.yaml states, issue_lifecycle.py,
set_status.py's `_DEFERRAL_REASON_CODES`, deferred_triage.py, test files,
docs) verified accurate as of commit `033c6c28`.

- **"Sole emitter" claim is wrong** (Integration Map → Similar Patterns, and
  Codebase Research Findings → "Deferral-write precedent"): `recheck_after_size_review`
  is not the sole emitter of `design_gate_failed` and `decision_unresolved`.
  `design_gate_failed` is also emitted at `autodev.yaml:1747` inside
  `regate_after_atomic_remediation` (starts line 1689); `decision_unresolved`
  is also emitted at `autodev.yaml:674` inside the separate state
  `record_decision_unresolved` (starts line 656). Only `low_readiness`
  (line 2099) and `readiness_stagnated` (line 2024) are exclusive to
  `recheck_after_size_review`.
- **`cmd_set_status` signature/location is wrong** (Program Design →
  Signatures): stated as `cmd_set_status(args: Namespace) -> int` at
  `set_status.py:105-122`. Actual signature is
  `cmd_set_status(config: BRConfig, args: argparse.Namespace) -> int`,
  defined at `set_status.py:25` (lines 105-122 are mid-function body, not
  the def).

Neither error changes the load-bearing proposal (new pre-dequeue gate check
+ `blocked_by_gate` reason code); both are precedent/signature citations an
implementer should not copy verbatim.

## Session Log
- `/ll:manage-issue` - 2026-08-11T07:08:34 - `30f3d184-494a-43b1-b8f0-2a71460e0abc.jsonl`
- `/ll:confidence-check` - 2026-08-11T06:29:49 - `5402ef28-337b-4847-b8ea-f4e072605f7f.jsonl`
- `/ll:reconcile-issue` - 2026-08-11T06:27:45 - `55769025-f551-43b6-b9eb-04c7c5f62978.jsonl`
- `/ll:verify-issues` - 2026-08-11T06:22:31 - `c50720b1-ba32-48c9-8306-a598431a781c.jsonl`
- `/ll:refine-issue` - 2026-08-11T06:17:57 - `b8decc79-2b71-4607-8370-f37905868963.jsonl`
- `/ll:verify-issues` - 2026-08-11T06:12:15 - `3161b79e-fe92-46f6-b061-dca2d7ba89c8.jsonl`
- `/ll:wire-issue` - 2026-08-11T06:07:52 - `4541bfae-8423-4fc5-8634-dac4fb11e6b9.jsonl`
- `/ll:refine-issue` - 2026-08-11T05:59:57 - `e2b907d5-f52e-43ba-afec-5c900fdf6135.jsonl`
- `/ll:capture-issue` - 2026-08-10T23:10:11 - `81255c48-5bc6-4004-a8cd-3f14858f5cb5.jsonl`
