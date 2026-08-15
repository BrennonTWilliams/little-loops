---
id: BUG-3170
type: BUG
title: check_hedges has no attempt limit, so a second hedge failure decomposes the
  issue
priority: P2
status: open
discovered_by: bug-3169-review
discovered_date: '2026-08-14'
captured_at: '2026-08-14T00:00:00Z'
relates_to:
- BUG-3169
- ENH-3031
- ENH-2446
testable: true
confidence_score: 100
outcome_confidence: 84
score_complexity: 19
score_test_coverage: 22
score_ambiguity: 21
score_change_surface: 22
---

# BUG-3170: check_hedges has no attempt limit, so a second hedge failure decomposes the issue

## Summary

`refine-to-ready-issue`'s `check_hedges` gate
(`scripts/little_loops/loops/refine-to-ready-issue.yaml:298`) routes `on_no`
straight to `check_refine_limit`, which is shared with three sibling gates
against `target: 2` — one loopback per run, total. So the gate gets exactly two
measurements, and if the second one is still red it spends the last of the
shared budget and the run falls through to `breakdown_issue`, with
`confidence_check` never reached. A correctly-sized issue gets decomposed
because a deterministic prose scan was still nonzero on its second reading.

The scan is `ll-issues check-open-questions`, whose exit-0 condition is an
absolute zero (`check_open_questions.py:62`). Its hedge vocabulary
(`issue_parser.py:1469`, widened by ENH-2446 and ENH-3031) has no
answer/hedge distinction, so it fires on ordinary resolution prose. A residual
nonzero count is therefore the normal steady state for a well-refined issue,
not a signal that refinement is incomplete.

The gate is worth keeping: forcing **one** refine pass on a red scan is cheap
and sometimes catches real gaps. What is not defensible is that a second red
reading — the expected outcome, given the false positives — triggers
decomposition. `check_hedges` needs an attempt limit, not a stricter or looser
count comparison.

BUG-3169 fixed one instance of the false-positive family (the `open question`
alternative firing on citations). It was 1 of 15 alternatives. This issue is
about what the gate does with a nonzero count, which survives that fix.

## Steps to Reproduce

**The count fires on resolution prose.** Verified against the current parser:

```python
>>> from little_loops.issue_parser import count_open_questions_in_sections
>>> count_open_questions_in_sections("""## Program Design

- Verified the transport pin (worth confirming, and now confirmed): `build_server()` takes no params.
- Prior note said TBD; resolved by grep sweep — no ContextVar usage anywhere.
""")
2
```

Neither item is unresolved; both read as answers. `worth confirming`,
`worth checking`, `should be considered`, `needs confirmation`, `TBD`, and
`to be determined` all have this citation/report form, and
`_RESOLVED_QUESTION_MARKER_RE` does not exclude them because refine writes prose
findings, not `✅ RESOLVED`-marked bullets.

**The routing then decomposes the issue.** With a residual count, the state
sequence is:

```
check_hedges (red) → check_refine_limit (N=1, 1<2 → yes) → refine_followup → ... → check_hedges
check_hedges (red) → check_refine_limit (N=2, 2<2 → no)  → breakdown_issue
```

The observed end-to-end failure is recorded in BUG-3169 (FEAT-3168,
`.loops/runs/refine-to-ready-issue-20260814T180315/`): the event log shows
`check_hedges → check_refine_limit` at iterations 12→13 and 19→20, with
`check_verify_verdict` passing both times. `check_hedges` spent the entire
shared budget by itself — two refine passes and two verify passes burned
(~$2.36, 19m46s) — then entered `breakdown_issue`.

## Current Behavior

`check_hedges` treats every red reading identically and has no memory of how
many times it has already fired. Its second failure is indistinguishable from
its first, so it consumes the shared loopback and routes to decomposition.

### Measured trajectories

An earlier draft of this issue assumed the count is monotonically rising
("every `--gap-analysis` pass is additive by construction"), and proposed a
count-comparison fix on that basis. That premise is wrong, and the measurement
is what motivates the attempt-limit shape instead.

Method: 250 issue files with ≥3 revisions were sampled from the last four
months of git history; the current parser was run over every historical
revision; consecutive revision pairs were filtered to refine-shaped passes
(file grew >20%) where the gate would be red (prior count > 0). n=27:

| trajectory across a refine pass | share | clears `count < prev` | clears `count <= prev` |
|---|---|---|---|
| count fell | 52% | yes | yes |
| count flat | 37% | no  | yes |
| count rose | 11% | no  | no  |
| | | **52% pass** | **89% pass** |

Observed rises are all small (4→6, 2→4, 1→2). Separately, 14 of 254 clean
(count-0) files went nonzero after a growth pass.

Two conclusions:

1. Refine does resolve and delete hedged prose — the count falls more often
   than it does anything else. The additive-ratchet premise does not hold.
2. No count comparison reaches 100%. `<` leaves 48% of runs decomposing, `<=`
   leaves 11%. Both residuals are the failure this issue exists to remove.

Sample-size caveat: n=27 is small, and the population is refine-shaped edits
rather than verified refine-loop passes. It is decisive against "can only
rise" (52% fell), and directionally sufficient for the rest.

### Why a count comparison is the wrong axis

The decisive point is what the red branch actually buys. By the time the second
measurement happens, the first failure has already incremented
`check_refine_limit` to 1. A second red reading therefore does **not** purchase
another refine pass — it exhausts the budget and routes to `breakdown_issue`.
So "still red → fail" does not mean "refine harder"; it means "decompose this
issue". Applied to a 1→2 rise caused by refine writing `TBD` into a research
note, that is precisely the defect described above.

The gate is also not the last line of defense. A permissive pass hands off to
`check_ac_automatable` → `confidence_check` → `check_readiness`, each with its
own rubric. A wrong fail costs a full refine budget plus a structurally wrong
decomposition; a wrong pass costs one extra hop to gates that can still catch
the issue. The asymmetry argues for bounding attempts rather than tightening
counts.

## Expected Behavior

- Count 0 → pass immediately (unchanged).
- First red reading in a run → force one refine pass (unchanged).
- Second red reading in a run → proceed to `check_ac_automatable`, leaving the
  shared refine budget for the sibling gates and letting the chain reach
  `confidence_check`.

The hedge gate may spend at most one refine pass per run, and never causes
`breakdown_issue` on its own.

## Program Design

### Types

No new Python types. The change is one new FSM state plus two routing edits in
`refine-to-ready-issue.yaml`; the counter is a run-scoped file holding a single
ASCII integer, the same representation the three sibling counters already use.

### Signatures

- `check_hedge_attempts.action -> stdout: int` (new FSM state) — post-increment
  read-modify-write of the run-scoped counter file, echoing the new value for
  `output_numeric` to evaluate. Byte-for-byte the shape of `check_refine_limit`
  (`refine-to-ready-issue.yaml:456-465`), including `2>/dev/null || echo 0` for
  an absent file.
- `check_hedge_attempts.evaluate -> yes | no` — `output_numeric` with
  `operator: lt`, `target: 2`. First entry echoes `1` (yes, spend a refine);
  second entry echoes `2` (no, proceed past the gate).
- `check_hedges.on_no -> check_hedge_attempts` — retargeted from
  `check_refine_limit`; every other field of the state is unchanged.

No change to `check_open_questions.py`, `issue_parser.py`, or any CLI surface.

### Call Path

`check_hedges` (`:298`) → CLI exit 1 → `check_hedge_attempts` (new) →
first entry: `check_refine_limit` (`:456`) → `refine_followup`; second entry:
`check_ac_automatable` (`:310`) → `confidence_check`.

### State definition

```yaml
  check_hedges:
    action: "ll-issues check-open-questions ${captured.issue_id.output}"
    fragment: shell_exit
    on_yes: check_ac_automatable   # exit 0 = no hedges (unchanged)
    on_no: check_hedge_attempts    # was check_refine_limit
    on_error: check_ac_automatable # unchanged

  check_hedge_attempts:
    # BUG-3170: bound how many refine passes the hedge scan may force. The scan
    # is an absolute-zero probe over vocabulary with no answer/hedge
    # distinction, so a residual count is the steady state for a well-refined
    # issue. One forced refine is worth its cost; a second red reading must not
    # spend the shared budget and decompose the issue.
    action: |
      FILE="${context.run_dir}/refine-to-ready-hedge-attempts"
      N=$(cat "$FILE" 2>/dev/null || echo 0)
      N=$((N + 1))
      printf '%s' "$N" > "$FILE"
      echo "$N"
    action_type: shell
    capture: check_hedge_attempts
    # target: 2 → one hedge-forced refine per run (mirrors check_refine_limit)
    evaluate:
      type: output_numeric
      operator: lt
      target: 2
    on_yes: check_refine_limit
    on_no: check_ac_automatable
    on_error: check_ac_automatable
```

### The counter is a pre-filter, not a second budget

`on_yes` routes to `check_refine_limit`, so the shared budget stays
authoritative — this state decides only whether the hedge gate is *allowed to
ask* for a refine, never whether one is granted. Routing `on_yes` directly to
`refine_followup` would give hedges a private budget on top of the shared one
and raise the loop's worst-case cost; it is deliberately not done.

### `on_error` fails open, matching the gate it guards

`check_hedges` already has `on_error: check_ac_automatable`, so a broken probe
skips past the gate rather than stalling. The counter inherits that convention.
A counter file that cannot be written degrades to today's behavior for that run
(the gate can still reach `check_refine_limit`), bounded by the shared budget,
with no spin risk. `check_refine_limit` uses `on_error: diagnose` instead, which
is right for a state that owns the budget and wrong here: an unwritable file
under `${context.run_dir}` does not warrant an LLM diagnose cycle.

### Seeding in `resolve_issue` is correct here

`resolve_issue` (`:78-81`) seeds its sibling counters with `printf '0' >`, and
the hedge counter joins them:

```yaml
      printf '0' > ${context.run_dir}/refine-to-ready-hedge-attempts &&
```

Zero attempts-so-far is the semantically correct initial value, and the action
already tolerates an absent file, so the seed is for run-dir uniformity rather
than correctness. (This is the opposite of the count-baseline design considered
below, where a `0` seed would have welded the gate shut — a difference worth
noting, since the two files would sit side by side.)

### Budget and isolation

`${context.run_dir}` is already in `scope:` (`:33-35`) and already
`mkdir -p`'d by `resolve_issue`, so no `scope:` edit is needed. The new state
adds at most 2 steps per run (one per hedge failure) against `max_steps: 40`
(`:50`), which the BUG-3065 note sizes at roughly 28 worst case — headroom is
sufficient and the cap does not change.

## Proposed Solution

Add `check_hedge_attempts` exactly as specified above, retarget
`check_hedges.on_no` to it, seed the counter in `resolve_issue`, and update the
routing summary in the file header (`:13-15`) plus
`docs/guides/LOOPS_REFERENCE.md:142`, which currently asserts that all three
claim-verification gates route `on_no` to `check_refine_limit`.

No CLI, parser, or Python change. `ll-issues check-open-questions` keeps its
absolute-zero contract for every caller, including
`oracles/resolve-decision.yaml:62`, which chains it as
`check-open-questions || check-decidable`.

## Alternatives Considered

- **Give the CLI a `--baseline-file` and pass when the count is at or below the
  best seen this run (`<=`).** The previous draft of this issue. Measured at 89%
  pass, so it leaves 11% of runs decomposing — the same defect, less often. It
  also costs a new flag with a split exit-code contract, a min-seen ratchet,
  empty/negative/unparseable handling, a tolerated-vs-clean stdout split, and
  docs across three surfaces, all to preserve a "count rose → fail" signal whose
  only effect in this loop is to trigger decomposition (see
  [Why a count comparison is the wrong axis](#why-a-count-comparison-is-the-wrong-axis)).
- **Require a strict decrease (`count < baseline`).** Measured at 52% pass;
  fails the majority-case trajectory nearly half the time.
- **Reuse the `open_question_stall` evaluator** (`fsm/evaluators.py:783`,
  fragment `open_question_stall_gate` in `loops/lib/common.yaml:196`, already
  wired in `oracles/resolve-decision.yaml:138`). It is the closest existing
  primitive and tracks a running minimum, but it encodes *strict decrease with
  patience*, not tolerance: progress is `count < best - epsilon`, and
  `max_stall` buys additional rounds rather than loosening the comparison. This
  loop has one loopback to spend, so with `max_stall: 1` the evaluator reduces
  to the 52% `<` gate. The `epsilon: -1` trick that would encode `<=` is
  rejected at validate time (`fsm/validation/structural_rules.py:193-199`,
  "epsilon must be >= 0"). Its routing polarity is also inverted for this use —
  `on_yes` means "still improving, keep refining", which would send the 52%
  improving case back through refine and into `breakdown_issue`. Adopting it
  would additionally require a zero-count fast path in front of it (rounds < 2
  returns `yes` regardless of count), a way to emit the count (the CLI prints it
  only inside human-readable stderr prose; `resolve-decision.yaml:113-133`
  works around this with an embedded `python3` heredoc that re-implements the
  count), and separation of the two count terms it sums. BUG-3065 records this
  gate's silent-inert failure mode when `history_file` is undeclared. **Revisit
  if `check_refine_limit`'s `target: 2` is ever raised or split per-gate** — with
  several refine passes available, "keep refining while improving, stop once
  plateaued" is a good policy and this evaluator implements it exactly.
- **Keep pruning the hedge vocabulary.** Each pass guesses at authorial intent
  and costs a false negative (BUG-3169's first draft silently stopped counting
  wrapped and imperative numbered questions). Does not change what a red reading
  does.
- **Exclude the refine-deposited sections again.** Reverts ENH-3031, which was
  added because real hedges accumulate in exactly those sections.
- **Have refine emit a structured count of what it resolved.** Larger surface,
  relies on the LLM to self-report, and the deterministic probe exists
  specifically to not do that.

## Impact

- **Priority**: P2 — burns a full refine budget per affected issue and pushes
  correctly-sized issues into `breakdown_issue`.
- **Effort**: Small — one new FSM state, two routing edits, one seed line, two
  doc updates, and loop-structure tests. No Python change.
- **Risk**: Low. The gate keeps its first-failure behavior exactly; only the
  second failure's destination changes, and it changes toward the downstream
  gates rather than around them. The residual is that a genuinely
  under-specified issue gets one forced refine instead of a decomposition, and
  is then judged by `confidence_check` / `check_readiness` on their own rubrics.
- **Breaking Change**: No. No CLI or config surface moves.

## Acceptance Criteria

- [ ] `refine-to-ready-issue.yaml` defines `check_hedge_attempts` with
      `action_type: shell`, `capture: check_hedge_attempts`, and
      `evaluate: {type: output_numeric, operator: lt, target: 2}`.
- [ ] Its counter path is `${context.run_dir}/refine-to-ready-hedge-attempts`
      (run-scoped, not a bare `.loops/tmp/` path), and the action tolerates an
      absent file via `2>/dev/null || echo 0`.
- [ ] `check_hedges.on_no == "check_hedge_attempts"`; its `on_yes`
      (`check_ac_automatable`), `on_error` (`check_ac_automatable`), `action`,
      and `fragment` are unchanged. The existing
      `test_check_hedges_state_routing` (`test_builtin_loops.py:1521-1531`)
      is updated for the new `on_no` and keeps asserting the other fields.
- [ ] `check_hedge_attempts.on_yes == "check_refine_limit"` (pre-filter, not a
      private budget), `on_no == "check_ac_automatable"`, and
      `on_error == "check_ac_automatable"` (fail-open, matching `check_hedges`).
- [ ] A test executes the counter action twice against a temp run dir and
      asserts it emits `1` then `2`, and that `output_numeric lt 2` therefore
      yields `yes` then `no` — i.e. exactly one hedge-forced refine per run.
- [ ] A test asserts the counter file is per-run: two different `run_dir` values
      each start from `1`.
- [ ] `resolve_issue` seeds `refine-to-ready-hedge-attempts` with `printf '0'`
      alongside its three sibling counters.
- [ ] `check_hedge_attempts` is listed in the `diagnose` prompt's captured-stderr
      block (`:604-613`) and its exit-code / failure-type printf blocks
      (`:654`, `:663`), matching the BUG-2726 treatment of `check_refine_limit`.
- [ ] The file-header routing summary (`:13-15`) shows
      `check_hedges → (on_no) check_hedge_attempts` and the two onward branches.
- [ ] `docs/guides/LOOPS_REFERENCE.md:142` no longer claims all three
      claim-verification gates route `on_no` to `check_refine_limit`; it
      describes the hedge gate's one-attempt bound.
- [ ] **No Python changes**: `check_open_questions.py` and `issue_parser.py` are
      untouched, and `test_ll_issues_check_open_questions.py` passes unmodified.
- [ ] `ll-loop validate refine-to-ready-issue` exits 0 (enforced by
      `test_builtin_loops.py::test_all_validate_as_valid_fsm`).
- [ ] `python -m pytest scripts/tests/` exits 0.

## Out of Scope

- The false positives themselves. Reducing them (the unnumbered "see Open
  Questions" pointer shape noted in BUG-3169, the `worth confirming`-in-answer
  shape shown above) remains worthwhile but is a separate axis; this issue
  bounds the cost of a red reading rather than making readings more accurate.
- Making the gate count-aware in any form. The measured trajectories show no
  comparison reaches the goal, and the design rationale above explains why the
  signal a comparison preserves is not one this loop can act on.
- `check_ac_automatable` and `check_verify_verdict`. They sit in the same chain
  and share the same budget, and neither is an absolute-zero prose scan, so
  neither obviously wants the same treatment. If a sibling turns out to have the
  same recurrence profile, the state added here is the pattern to copy.
- The shared `check_refine_limit` budget. Four gates increment one counter
  against `target: 2`, so a run where a sibling spends the loopback first still
  reaches `breakdown_issue` on a subsequent hedge failure. Re-examining
  `target: 2` or giving each gate its own budget is a separate change — and the
  precondition for reconsidering `open_question_stall`.
- `unresolved_options` semantics, which stay owned by `check_decision_needed` /
  `/ll:decide-issue`.

## Integration Map

- `scripts/little_loops/loops/refine-to-ready-issue.yaml:298-308` —
  `check_hedges`, whose `on_no` is retargeted; `:456-472` —
  `check_refine_limit`, the counter-state shape to mirror and the target of the
  new state's `on_yes`; `:310` — `check_ac_automatable`, the new state's `on_no`
  and `on_error`; `:78-81` — `resolve_issue`'s counter seeding, extended by one
  line; `:33-35` — `scope:`, already covering `${context.run_dir}` (no edit);
  `:50` — `max_steps: 40`, unchanged; `:13-15` — the routing summary comment;
  `:604-613`, `:654`, `:663` — the `diagnose` capture blocks.
- `scripts/tests/test_builtin_loops.py:1521-1531` —
  `test_check_hedges_state_routing`, which asserts the old `on_no` and must be
  updated; `:49` — `test_all_validate_as_valid_fsm`, which already enforces
  `ll-loop validate` over every builtin loop.
- `docs/guides/LOOPS_REFERENCE.md:142` — the gate-chain description.
- `scripts/little_loops/cli/issues/check_open_questions.py:62` — the
  absolute-zero exit condition, cited as the source of the red readings and
  deliberately left unchanged; `scripts/little_loops/issue_parser.py:1469` —
  the hedge vocabulary, likewise unchanged.
- `scripts/little_loops/loops/oracles/resolve-decision.yaml:62` — the other
  caller of the CLI, unaffected because the CLI does not change.
- `scripts/little_loops/fsm/evaluators.py:783` and
  `scripts/little_loops/loops/lib/common.yaml:196` — the `open_question_stall`
  primitive evaluated and rejected in Alternatives Considered.

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-08-14_

**Readiness Score**: 100/100 → STOP — ADDRESS GAPS (Program Design hard override)
**Outcome Confidence**: 84/100 → High

### Gaps to Address
- Program Design gate (`ll-issues check-design BUG-3170`) fails: "no
  signature-shaped line found in Types, Signatures, Call Path, or the section
  preamble; no call-path anchor resolves against the repo: check_hedges,
  check_hedge_attempts, check_refine_limit, refine_followup,
  check_ac_automatable, confidence_check". The issue's Program Design section
  is substantively detailed (explicit signatures, call path, full state YAML),
  but the gate's signature/call-path regex does not recognize FSM state-key
  notation (`check_hedge_attempts.action -> stdout: int`) as signature-shaped,
  and can't resolve YAML state names as repo call-path anchors the way it
  resolves Python symbols. This reads as a linter false positive on
  FSM-loop-shaped issues rather than an actual specification gap — no
  content change is indicated pending gate-side confirmation; if the gate is
  in fact correctly flagging a real gap, the fix would be to reformat the
  Signatures block into a form the regex accepts, or set
  `program_design_not_applicable: true` is not appropriate here since real
  design content exists.

### Outcome Risk Factors
- None — all four outcome dimensions score in the high band (isolated
  single-file change, existing pattern to mirror, explicit test coverage
  requirements in the AC, no unresolved ambiguity).

## Status

**Open** | Created: 2026-08-14 | Priority: P2


## Session Log
- `/ll:confidence-check` - 2026-08-15T00:50:48 - `3e7c9d5c-db6b-4056-8147-8c79e66b7bc7.jsonl`
- `/ll:confidence-check` - 2026-08-15T00:02:16 - `f2a7b3a1-13a3-4789-a189-b1a33c413ed6.jsonl`
- `/ll:format-issue` - 2026-08-15T00:00:21 - `89d8e25e-eb7d-4616-8513-9b90d6e3e96f.jsonl`
