---
id: BUG-2520
title: autodev `deposit_options` falls through to `run_decide` without observing whether Option A/B/C blocks were actually deposited
type: BUG
status: cancelled
priority: P3
captured_at: '2026-07-07T14:50:00Z'
discovered_date: '2026-07-07'
discovered_by: capture-issue
relates_to:
- BUG-2513
- BUG-2501
- ENH-2443
labels:
- loops
- fsm
- autodev
- decide-issue
- deposit-options
- defense-in-depth
confidence_score: 78
outcome_confidence: 60
score_complexity: 14
score_test_coverage: 17
score_ambiguity: 22
score_change_surface: 16
decision_needed: false
---

# BUG-2520: autodev `deposit_options` falls through to `run_decide` without observing whether Option A/B/C blocks were actually deposited

## Summary

In `scripts/little_loops/loops/autodev.yaml`, the `deposit_options` state
(action: `/ll:refine-issue ${captured.input.output} --auto`, line 218)
is intended to deposit Option A/B/C blocks into the issue's
`## Proposed Solution` section so that `run_decide` can enumerate them.
The state is bounded by the `autodev-decide-options-deposited` marker,
but the *post-condition* — that `## Proposed Solution` actually gained
Option A/B/C blocks — is **not observed**. If the refine call returns
non-partial without depositing (e.g., refine succeeds but the body
doesn't insert Option A/B/C markers, or refine returns a marker-clean
success), `run_decide` runs anyway with no enumerable options, leaving
`decision_needed: true` unchanged. The next caller (after the user
runs `/ll:decide-issue` interactively, or the upstream
`check_decision_at_dequeue` gate fires on re-dequeue) sees the same
`decision_needed: true` flag and re-enters the same path.

This is the "Mode C" failure mode named in `autodev-bug2501-kill-analysis.md`
(lines 175-188). The trace ruled out Mode C for the killed BUG-2501 run
(zero `/ll:decide-issue` invocations across 200 sessions in the kill
window), but the *underlying defect* the analysis describes — that
`deposit_options` doesn't observe its own post-condition — is real
and self-contained.

## Codebase Research Findings

_Added by `/ll:refine-issue BUG-2520 --auto` based on direct reads of the
referenced YAML, CLI, parser, and tests:_

### ⚠ Discrepancy: "Current Behavior" / "Root Cause" claims contradict the actual code

The bug claim that `deposit_options` "advances unconditionally to `run_decide`"
without observing whether Option A/B/C blocks were deposited is **inaccurate**
against the current `scripts/little_loops/loops/autodev.yaml`. The
defense-in-depth described as "missing" is in fact **already implemented** via
a `record_options_deposited` marker state that the issue does not mention.

**Actual `deposit_options` state** (autodev.yaml:225-237):

```yaml
deposit_options:
  # Bounded retry: refine --auto may deposit Option A/B/C blocks that
  # run_decide can then score. Write-once marker prevents infinite loops if
  # refine also can't deposit options — falls through to run_decide with no
  # enumerable options; the existing decision_needed gate remains the safety net.
  fragment: with_rate_limit_handling
  action_type: slash_command
  action: "/ll:refine-issue ${captured.input.output} --auto"
  on_yes: record_options_deposited
  on_no: run_decide
  on_partial: record_options_deposited
  on_error: run_decide
  on_rate_limit_exhausted: done
```

There is **no `next:` directive**; each outcome is routed explicitly. On
success or partial (`on_yes`/`on_partial`) the next hop is
`record_options_deposited`, NOT `run_decide`.

**Actual `record_options_deposited` state** (autodev.yaml:239-245):

```yaml
record_options_deposited:
  action_type: shell
  action: |
    printf '1' > ${context.run_dir}/autodev-decide-options-deposited
  next: check_decision_decidable
```

**Actual `check_decision_decidable` state** (autodev.yaml:207-223) — the
marker check is the **first** line of the action, before the CLI call:

```yaml
check_decision_decidable:
  action: |
    if [ -f ${context.run_dir}/autodev-decide-options-deposited ]; then
      exit 0
    fi
    ll-issues check-decidable ${captured.input.output}
  fragment: shell_exit
  on_yes: run_decide
  on_no: deposit_options
  on_error: run_decide
```

So the marker IS observed — it short-circuits the decidability check to
exit 0, which routes straight to `run_decide` without re-running
`check-decidable` (the comment at lines 213-214 explicitly documents this as
"marker-bounded: once deposit_options has run once this iteration, skip
re-validation and go straight to run_decide").

**Actual routing chain for `decision_needed: true` with 0 enumerable options**:

1. `check_decision_decidable` runs `check-decidable`; exits 1 → `on_no: deposit_options` (line 222).
2. `deposit_options` runs `/ll:refine-issue` (line 232).
3a. **Success/partial path** → `record_options_deposited` writes the marker (line 244) → loops back to `check_decision_decidable` (line 245) → marker check passes → exits 0 → `on_yes: run_decide` (line 221).
3b. **Failure/error path** → `run_decide` directly (lines 234, 236); marker is NOT written; on the next dequeue, `check_decision_at_dequeue` (BUG-2513 path, line 102) re-routes the issue through `run_decide`. The comment at lines 226-229 explicitly documents this as the bounded-retry safety net.

The bug's claim that the marker is "set on the success of the *next* state
(`check_decision_decidable.on_yes`)" is incorrect — the marker is written by
the dedicated `record_options_deposited` state BEFORE the FSM re-enters
`check_decision_decidable`, and the gate honors the marker by short-circuiting
to exit 0 (lines 216-218). `check_decision_decidable.on_yes` only routes the
FSM; it does not write the file.

### Implications for the proposed fix

The fix proposed in `## Proposed Solution` (insert a `check_options_deposited`
post-state between `deposit_options` and `run_decide`) would either:

1. **Duplicate** the existing `record_options_deposited` pattern (if added
   after `record_options_deposited` already runs), making it a no-op for the
   common case; or
2. **Conflict** with the existing pattern (if added directly after
   `deposit_options.on_yes`/`on_partial`, replacing `record_options_deposited`),
   regressing the bounded-retry semantics.

The proposed `## Expected Behavior` ("`deposit_options` only advances to
`run_decide` when the post-condition … actually held") is the current behavior
of `deposit_options.on_no`/`on_error` (which already go directly to
`run_decide` without setting the marker) — except those branches are
intentional fail-open paths per the comment at lines 226-229, not defect
sites.

### Recommendation

Before implementing, re-validate the bug premise by running
`/ll:verify-issues BUG-2520` (or `/ll:ready-issue BUG-2520`) with deep mode
against `autodev.yaml:225-245` and the `_StubRunner` test fixture at
`scripts/tests/test_autodev_decision_gate.py:38-70`. Three plausible paths
forward:

- **Path A (cancel/no-op)**: The bug as filed describes behavior the code
  does not exhibit; the `record_options_deposited` pattern is the
  defense-in-depth the issue says is missing. Close as `cancelled` and link
  to `autodev-bug2501-kill-analysis.md` Mode C discussion as the original
  observation that prompted the file.
- **Path B (narrow scope)**: The remaining real defect is narrower — e.g.,
  `deposit_options.on_error: run_decide` (line 236) and
  `deposit_options.on_no: run_decide` (line 234) do NOT write the marker,
  so a transient refine failure skips the marker-bounded skip on the next
  dequeue. The fix would route these branches through
  `record_options_deposited` (with a flag saying "deposit was attempted,
  do not retry") rather than introducing a new `check_options_deposited`
  state.
- **Path C (rn-remediate parity)**: `scripts/little_loops/loops/rn-remediate.yaml:285-308`
  has a parallel `deposit_options`/`check_decision_decidable` pair (per the
  pattern-finder findings, rn-remediate.yaml:280 already invokes
  `ll-issues check-decidable`). The note at line 217 of the issue flags
  rn-remediate as a follow-on — the same investigation should be run
  against rn-remediate before either fix is committed.

The decision in `## Proposed Solution > ### Decision` (Option C — use
existing `ll-issues check-decidable`) was made on 2026-07-07 based on the
issue's `## Current Behavior` claim; that claim does not match the code.
Re-running `/ll:decide-issue` against the corrected `## Current Behavior`
is recommended before implementing.

### Anchor references (verified)

- `deposit_options` — `scripts/little_loops/loops/autodev.yaml:225-237`
- `record_options_deposited` — `scripts/little_loops/loops/autodev.yaml:239-245`
- `check_decision_decidable` — `scripts/little_loops/loops/autodev.yaml:207-223`
- `run_decide` — `scripts/little_loops/loops/autodev.yaml:247-258`
- `dequeue_next` (clears both markers per iteration) — autodev.yaml:63-99 (lines 83-84)
- `check_decision_at_dequeue` (BUG-2513 fix) — autodev.yaml:102-126
- `ll-issues check-decidable` CLI — `scripts/little_loops/cli/issues/check_decidable.py:19-45`
- `count_enumerable_options` — `scripts/little_loops/issue_parser.py:271-284`
- `_OPTION_PATTERNS` — `scripts/little_loops/issue_parser.py:250-257`
- `_OPTION_FALLBACK_SECTIONS` — `scripts/little_loops/issue_parser.py:259`
- `_StubRunner` — `scripts/tests/test_autodev_decision_gate.py:38-70`
- `TestCheckDecisionAtDequeueRouting` — `scripts/tests/test_autodev_decision_gate.py:187-279`
- `count_enumerable_options` unit tests — `scripts/tests/test_decide_issue_skill.py:476-529`
- Parallel sibling — `scripts/little_loops/loops/rn-remediate.yaml:263-283` (`check_decision_decidable`) and 285-308 (`deposit_options`)

## Motivation

- **Real defect, self-contained**: Even though the killed run did not
  exhibit this mode, the defect is structurally present in the
  current YAML. A future refine-body change that fails to deposit
  Option A/B/C blocks will silently bypass the option-enumeration
  check, leaving `decision_needed: true` permanently set and
  routing the issue back to the decide chain indefinitely.
- **Defense-in-depth on the just-fixed decision gate (BUG-2513)**:
  BUG-2513 added `check_decision_at_dequeue` upstream of
  `refine_current`, which catches every pre-refine `decision_needed:
  true` issue. But the decide chain (`run_decide → mark_decide_ran →
  rerun_confidence_after_decide → recheck_after_decide`) still
  invokes `deposit_options` when the issue has zero enumerable
  options. If `deposit_options` falls through to `run_decide`
  without depositing, the user sees the same `decision_needed: true`
  flag on the next dequeue — the fix from BUG-2513 would route it
  back through the same `run_decide` chain, and the loop recurs.
- **Silent failure mode**: No error is raised; the loop just
  continues refining without making progress on the decision.
- **P3 priority**: Defense-in-depth; no live reproducer. The defect
  is real but the only documented trace (killed BUG-2501 run)
  exhibits Mode B, not Mode C.

## Current Behavior

`deposit_options.on_yes / on_no / on_partial` (autodev.yaml:218) all
route to `run_decide` regardless of whether the post-condition
(`## Proposed Solution` gained Option A/B/C blocks) actually held.

```yaml
deposit_options:
  action: "/ll:refine-issue ${captured.input.output} --auto"
  next: run_decide    # ← unconditionally advances
  on_error: run_decide
```

The marker `autodev-decide-options-deposited` is set on success of
the *next* state (`check_decision_decidable.on_yes`), not on success
of `deposit_options` itself. So the marker does not guard against
`deposit_options` returning a non-partial-without-depositing outcome.

## Expected Behavior

`deposit_options` only advances to `run_decide` when the post-condition
(`## Proposed Solution` contains Option A/B/C blocks) actually held.
If the post-condition fails:

- The state routes to a new `check_options_deposited` state (or
  equivalent) that re-reads the issue file and asserts the markers
  exist.
- On `on_no` (markers absent), route to `triage_outcome_failure` or
  a new `deposit_options_failed` state that records the failure
  and re-enters `dequeue_next` rather than silently advancing.
- On `on_error`, fail-open to `run_decide` (preserving the current
  error tolerance) but log a warning.

`ll-loop validate autodev` passes; no dead `no` / `partial` ends in
the new routing.

## Steps to Reproduce

1. Create a fixture issue with `decision_needed: true` and
   `## Proposed Solution` empty (no Option A/B/C blocks).
2. Hand-edit `/ll:refine-issue --auto`'s behavior (or stub it) so
   the refine call returns success (exit 0, partial=N/A) without
   depositing the markers.
3. Run `ll-loop run autodev --input <FIXTURE_ID> --max-steps 30`.
4. Observe: `deposit_options` returns "success", routes to
   `run_decide`. `run_decide` invokes `/ll:decide-issue` with zero
   enumerable options. `decision_needed: true` is unchanged.
5. The next dequeue sees `decision_needed: true`, routes back to
   `run_decide` (via `check_decision_at_dequeue`), and the loop
   recurs indefinitely.

## Root Cause

- **File**: `scripts/little_loops/loops/autodev.yaml`
- **Anchor**: `deposit_options` state (around line 218) and its
  outbound `next: run_decide` routing
- **Cause**: The state's `next` is unconditional. The marker
  `autodev-decide-options-deposited` is set downstream, not as
  the state's own post-condition check. The state does not
  observe whether `## Proposed Solution` actually gained
  Option A/B/C blocks before advancing.

## Proposed Solution

Add a `check_options_deposited` state between `deposit_options`
and `run_decide` that re-reads the issue file and asserts the
post-condition held:

```yaml
deposit_options:
  action: "/ll:refine-issue ${captured.input.output} --auto"
  next: check_options_deposited
  on_error: run_decide   # fail-open on refine error (preserve tolerance)

check_options_deposited:
  comment: |
    Verify that `deposit_options` actually deposited Option A/B/C
    blocks. If not, route to `deposit_options_failed` rather than
    silently advancing to `run_decide`.
  action: "grep -cE '^### Option [A-Z]' ${captured.input.path} || true"
  on_yes: run_decide
  on_no: deposit_options_failed
  on_error: run_decide   # fail-open on grep error (e.g. file missing)

deposit_options_failed:
  comment: |
    `deposit_options` did not deposit Option A/B/C blocks. Skip
    the issue rather than re-running `run_decide` with zero
    enumerable options.
  next: skip_inflight    # or dequeue_next, depending on intent
```

### Alternative — check via `ll-issues` (preferred)

Instead of `grep` directly, use `ll-issues check-flag` with a new
synthetic flag or a custom predicate. Cleaner abstraction but
requires a new CLI surface.

### Decision

**Selected**: Use the existing `ll-issues check-decidable <ID>` CLI
(scripts/little_loops/cli/issues/check_decidable.py:19) — wrapping
`count_enumerable_options` from scripts/little_loops/issue_parser.py:271,
which is the same canonical 4-pattern predicate the upstream
`check_decision_decidable` gate already invokes at autodev.yaml:219.
Add a new `check_options_deposited` state that mirrors the
`check_decision_decidable` shape (shell_exit fragment, on_yes →
run_decide, on_no → deposit_options_failed, on_error → run_decide
fail-open), and route `deposit_options.on_no` and `on_error` through
it instead of straight to `run_decide`. Zero new CLI surface, zero
new frontmatter convention, reuses battle-tested Python.

> **Selected:** Use existing `ll-issues check-decidable` — reuses
> the canonical 4-pattern option counter the upstream gate already
> calls; no new CLI surface or synthetic flag required.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-07-07.

**Selected**: Use existing `ll-issues check-decidable` for the post-condition check (Option C).

**Reasoning**: The codebase already ships a deterministic CLI that answers BUG-2520's post-condition question exactly. `ll-issues check-decidable <ID>` (`scripts/little_loops/cli/issues/check_decidable.py:19`) wraps `count_enumerable_options` (`scripts/little_loops/issue_parser.py:271-284`), which implements the 4-pattern Option A/B/C detection (`^### Option [A-Z]`, `**Option X**`, `1. **Option X**`, `- (a) ...`) plus 2 fallback sections (`## Codebase Research Findings`, `## Implementation Status`). This is the same predicate the upstream `check_decision_decidable` gate uses at `autodev.yaml:219` — the post-condition check is the same question, asked after `deposit_options` runs. The grep option (A) duplicates that logic as a strict subset (Pattern 1 only) and inherits an MR-9 `${captured.input.path}` brace-escape hazard. The `check-flag`-with-synthetic-flag option (B) misuses `check-flag` (it reads frontmatter booleans, not body content) and requires a new `ll-issues set-flag` writer plus a writer in `/ll:refine-issue` (BUG-1416:44 confirms no writer exists).

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| A — grep-based `check_options_deposited` (`grep -cE '^### Option [A-Z]'`) | 1/3 | 2/3 | 2/3 | 1/3 | **6/12** |
| B — `ll-issues check-flag` with new synthetic flag | 1/3 | 1/3 | 1/3 | 1/3 | **4/12** |
| **C — `ll-issues check-decidable` (existing CLI)** | **3/3** | **3/3** | **3/3** | **3/3** | **12/12** |

**Key evidence**:
- **Option A**: 27 grep-based sites exist across FSM loops (e.g. `vega-viz.yaml:519`, `rn-build.yaml:105,147`), but the proposed pattern is Pattern-1-only and would silently miss options deposited in `**Option A**` or numbered/bulleted formats that `count_enumerable_options` handles. Bare `${captured.input.path}` in the YAML action triggers an MR-9 brace-escape hazard (existing autodev pattern at line 380 quotes the path *after* interpolation to avoid this).
- **Option B**: `check-flag` (`scripts/little_loops/cli/issues/check_flag.py:13-33`) reads frontmatter booleans only (`fm.get(args.field)`); no `set-flag` writer exists (BUG-1416); would require extending `ll-issues` with new writer plus a writer in `/ll:refine-issue`.
- **Option C**: `ll-issues check-decidable` is already registered (`__init__.py:632-638`), dispatched (`__init__.py:843-844`), epilog-documented (`__init__.py:88`), called from `autodev.yaml:219` and `rn-remediate.yaml:280`. The proposed state mirrors `check_decision_decidable` exactly (`autodev.yaml:207-223`), and `count_enumerable_options` is unit-tested at `test_decide_issue_skill.py:476-529`. Test scaffolding (`_StubRunner` at `test_autodev_decision_gate.py:38-70`) is directly applicable.

**Note**: The same fix likely applies to `scripts/little_loops/loops/rn-remediate.yaml:285-308` (parallel `deposit_options`/`check_decision_decidable` pair without the post-condition check). The fix scope was autodev-only per the issue's Files to Modify section, but follow-on tracking should cover rn-remediate.

## Implementation Steps

1. **Add the post-condition check**: insert `check_options_deposited`
   between `deposit_options` and `run_decide` in
   `scripts/little_loops/loops/autodev.yaml`.
2. **Add `deposit_options_failed`** (or reuse `skip_inflight`) to
   route on `on_no`.
3. **Verify `ll-loop validate autodev`** passes.
4. **Add a pytest** in `scripts/tests/test_autodev_decision_gate.py`
   that drives a fixture issue with `decision_needed: true` and
   an empty `## Proposed Solution`, stubs the refine call to return
   success without depositing, and asserts the routing reaches
   `deposit_options_failed` (or `skip_inflight`) rather than
   `run_decide`.
5. **Verify** `python -m pytest scripts/tests/ -k autodev` passes.

### Codebase Research Findings

_Added by `/ll:refine-issue BUG-2520 --auto` — implementation steps are based
on the issue's "Current Behavior" claim that contradicts the actual code:_

Steps 1-2 above would either duplicate the existing
`record_options_deposited` state (autodev.yaml:239-245) or replace it,
regressing the bounded-retry semantics documented at autodev.yaml:226-229
and 240-241. Before implementing these steps, see `## Codebase Research
Findings` at the top of this file for the corrected understanding and
the recommended Path A / B / C paths forward. The pytest in Step 4 is
still applicable (it would exercise the existing
`record_options_deposited` → `check_decision_decidable` cycle) but the
assertion in Step 4 ("routing reaches `deposit_options_failed` rather
than `run_decide`") already holds on `on_no`/`on_error` paths in the
current code (lines 234, 236).

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/autodev.yaml` — add `check_options_deposited`
  and `deposit_options_failed` states (or reuse `skip_inflight`).
- `scripts/tests/test_autodev_decision_gate.py` — add the new pytest.

### Codebase Research Findings

_Added by `/ll:refine-issue BUG-2520 --auto` — actual line numbers for the
referenced states:_

The states the proposed fix would touch already exist at:
- `deposit_options` — autodev.yaml:225-237 (not line 218 as the issue
  describes)
- `check_decision_decidable` — autodev.yaml:207-223 (not line 219)
- `record_options_deposited` — autodev.yaml:239-245 (not mentioned in the
  issue; this is the state that actually writes the marker)
- `run_decide` — autodev.yaml:247-258

Any change to add `check_options_deposited` would need to either replace
`record_options_deposited` (regression risk) or slot in after it (no-op
for the common case). See `## Codebase Research Findings` at the top of
this file for the corrected analysis.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` — sub-loop
  delegate; unchanged contract (the post-condition check is in the
  parent, not the sub-loop).
- `scripts/little_loops/fsm/executor.py` — runs FSM states; no change
  needed (the new state reuses the existing `grep` or `check-flag`
  evaluator type).
- `scripts/little_loops/loops/refine-issue` skill — called by
  `deposit_options`; unchanged contract.

### Similar Patterns
- **BUG-2513** (just-closed) — added `check_decision_at_dequeue`
  to observe `decision_needed` upstream of `refine_current`. This
  issue is the structural analog for `deposit_options` observing its
  own post-condition. Same defense-in-depth shape.
- **ENH-2443** — `decide-issue rn-remediate robust to
  decision_needed no enumerable options`. The related but distinct
  issue is what `run_decide` does when there are zero enumerable
  options; BUG-2520 is what `deposit_options` does when its
  pre-condition for *creating* those options fails.

### Tests
- New pytest in `scripts/tests/test_autodev_decision_gate.py`
  covering the stubbed-refine-without-depositing fixture scenario.

### Documentation
- `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` § "Decision gates"
  — link this issue as a follow-on to BUG-2513, documenting the
  defense-in-depth shape.
- `autodev-bug2501-kill-analysis.md` (repo root) — link this issue
  as the Mode C write-up is formalized into a tracked defect.

### Configuration
- N/A — no `ll-config.json` or schema changes.

## Impact

- **Priority**: P3 — defense-in-depth on a real-but-unobserved defect.
  No live reproducer; the killed BUG-2501 run exhibited Mode B (the
  post-refine-gate bypass), not Mode C.
- **Effort**: Small — one new state plus a focused pytest.
- **Risk**: Low — the change adds a post-condition check *before*
  `run_decide`; existing paths are unchanged when the post-condition
  holds (the common case).
- **Breaking Change**: No — for the common case (deposit_options
  successfully deposits markers), the routing is unchanged.

## Status

**Cancelled** | Created: 2026-07-07 | Cancelled: 2026-07-07 | Priority: P3

Closed via `/ll:verify-issues BUG-2520 --deep` (verdict: INVALID). The
issue's `## Current Behavior` claim does not match the current code; the
defense-in-depth described as missing is already implemented via the
`record_options_deposited` state (`scripts/little_loops/loops/autodev.yaml:239-245`)
plus the marker short-circuit in `check_decision_decidable`
(`scripts/little_loops/loops/autodev.yaml:207-223`). The codebase research
findings inside the issue file (added by `/ll:refine-issue BUG-2520 --auto`)
already document this discrepancy and recommend Path A: close as
`cancelled`. All 16 anchor references in the issue (file paths, line
numbers, code excerpts) verified accurate. See `## Verification Notes`
below for details.

## Verification Notes

_Added by `/ll:verify-issues BUG-2520 --deep` on 2026-07-07._

### Verdict

**INVALID** — issue description does not match current code. Closed as
`cancelled` per Path A (the codebase research findings above already
recommended this path).

### Evidence

1. **Code excerpt at issue file lines 237-242 is stale.** It shows
   `deposit_options` with `next: run_decide` (unconditional). The actual
   state at `scripts/little_loops/loops/autodev.yaml:225-237` has no
   `next:` directive — each outcome routes explicitly:
   - `on_yes: record_options_deposited` (line 233)
   - `on_partial: record_options_deposited` (line 235)
   - `on_no: run_decide` (line 234)
   - `on_error: run_decide` (line 236)
   - `on_rate_limit_exhausted: done` (line 237)

2. **Marker write is NOT on `check_decision_decidable.on_yes`** (as the
   issue claims) — it's written by the dedicated `record_options_deposited`
   state at `autodev.yaml:239-245`:
   ```yaml
   record_options_deposited:
     action_type: shell
     action: |
       printf '1' > ${context.run_dir}/autodev-decide-options-deposited
     next: check_decision_decidable
   ```

3. **Marker short-circuit IS the defense-in-depth.** `check_decision_decidable`
   at `autodev.yaml:207-223` checks the marker FIRST (lines 216-218) and
   exits 0 if present, skipping the `ll-issues check-decidable` call and
   routing straight to `run_decide` via `on_yes` (line 221). The comment
   at lines 213-214 explicitly documents this: "marker-bounded: once
   `deposit_options` has run once this iteration, skip re-validation and go
   straight to `run_decide`".

4. **`on_no` / `on_error` fail-open is intentional.** The comment at
   `autodev.yaml:226-229` documents that transient refine failures fall
   through to `run_decide` with no enumerable options, and the existing
   `decision_needed` gate remains the safety net.

### Anchor References Verified (16/16 accurate)

| Reference | Verified |
|-----------|----------|
| `deposit_options` — autodev.yaml:225-237 | ✓ |
| `record_options_deposited` — autodev.yaml:239-245 | ✓ |
| `check_decision_decidable` — autodev.yaml:207-223 | ✓ |
| `run_decide` — autodev.yaml:247-258 | ✓ |
| `dequeue_next` clears marker — autodev.yaml:83-84 | ✓ |
| `check_decision_at_dequeue` (BUG-2513) — autodev.yaml:102-114 | ✓ |
| `cmd_check_decidable` — check_decidable.py:19-45 | ✓ |
| `count_enumerable_options` — issue_parser.py:271-284 | ✓ |
| `_OPTION_PATTERNS` — issue_parser.py:250-257 | ✓ |
| `_OPTION_FALLBACK_SECTIONS` — issue_parser.py:259 | ✓ |
| `_StubRunner` — test_autodev_decision_gate.py:38-70 | ✓ |
| `TestCheckDecisionAtDequeueRouting` — test_autodev_decision_gate.py:187-279 | ✓ |
| `count_enumerable_options` tests — test_decide_issue_skill.py:472-529 | ✓ |
| rn-remediate `check_decision_decidable` — rn-remediate.yaml:263-283 | ✓ |
| rn-remediate `deposit_options` — rn-remediate.yaml:285-298 | ✓ |
| rn-remediate `record_options_deposited` — rn-remediate.yaml:300-308 | ✓ |

### Related Issues Confirmed

- **BUG-2513** (`autodev-decision-gate-bypassed-on-refine-non-success`) — `done` ✓
- **ENH-2443** (`decide-issue rn-remediate robust to decision_needed no enumerable options`) — `done` ✓
- **BUG-2501** (`autodev killed run`) — `done`; Mode C discussion at `autodev-bug2501-kill-analysis.md:175-188` accurately quoted in the issue ✓

### Decisions Log

```
$ ll-issues decisions list --type rule --enforcement required --active-only
(no entries)
```

No active required rules → no `DECISIONS_VIOLATION`.

### Why Path B / Path C also do not apply

- **Path B** (route `on_no`/`on_error` through `record_options_deposited`):
  Fail-open on these branches is intentional per `autodev.yaml:226-229`.
  Since `on_no`/`on_error` go straight to `run_decide`, the next dequeue
  hits `check_decision_at_dequeue` (BUG-2513 fix at autodev.yaml:102-114)
  which sees `decision_needed: true` and routes to `run_decide` (line 112),
  bypassing the decidability gate entirely. The "missing marker" on these
  branches is by design, not defect.
- **Path C** (rn-remediate parity): The same `record_options_deposited`
  pattern exists at `rn-remediate.yaml:300-308`, mirroring autodev. No
  parity defect.

### No Code Changes Applied

The proposed `check_options_deposited` state would either duplicate
`record_options_deposited` (no-op for common case) or replace it
(regression of bounded-retry semantics documented at autodev.yaml:226-229
and 240-241).

## Session Log
- `/ll:verify-issues` - 2026-07-07T16:59:49 - `5f1bb73e-2cb2-4ade-9dfd-1f8e46c3e890.jsonl`
- `/ll:refine-issue` - 2026-07-07T16:51:37 - `d17cb40a-812f-4dec-b05a-f65a61da3a03.jsonl`
- `/ll:decide-issue` - 2026-07-07T16:45:32 - `d00f1e04-c320-4c63-9f81-b355d20cf883.jsonl`
- `/ll:capture-issue` - 2026-07-07T14:50:00Z - `183e7df6-0517-4eb0-83d7-ab914af56328.jsonl`