---
id: ENH-3283
type: ENH
title: capture-issue writes evidence quotes without checking them against the cited
  artifact
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-08-21'
captured_at: '2026-08-21T17:30:17Z'
labels:
- capture-issue
- skills
- evidence
- hallucination
relates_to:
- BUG-3282
- BUG-3278
- ENH-3291
---

# ENH-3283: capture-issue writes evidence quotes without checking them against the cited artifact

## Summary

`/ll:capture-issue` writes `## Current Behavior` and `## Steps to Reproduce` containing quoted
lines attributed to specific files, with no step that confirms those lines exist there. It is the
write-time half of the gap BUG-3282 closes at verify time.

## Current Behavior

The skill's Phase 1 extracts a title, type, priority, and description; Phase 2 checks for
duplicates; Phase 4 writes the file via `ll-issues create`. No phase validates the *content* of
the body it writes. When capture reconstructs evidence from conversation context rather than from
a file read, a plausible-but-nonexistent quote is written verbatim into the issue and inherits the
authority of the surrounding accurate citations.

Observed on BUG-3278: `git show baa553d9` (2026-08-21 10:56) is the capture output. Its
`## Current Behavior` attributes to ENH-3277 a `- **(a) Make the documented override real.**`
bullet and a `**DECISION — pick one before step 4 touches this file:**` directive. Neither exists
in any committed revision of ENH-3277 — its second decision point is prose. The capture also
derived a `bullet`-tier attribution, a span-exclusion fix proposal, and an `--all-tiers` CLI
alternative from that invented shape. All of it was present 31 minutes before the
`refine-to-ready-issue` loop started; no loop pass introduced it, and none removed it.

## Expected Behavior

Before Phase 4's `ll-issues create` write, every quoted span in the drafted body that is
attributed to a named file or issue ID is checked against that artifact (`grep -F` or a direct
read). A span that verifies is written as-is. A span that does not is never written: it is
either re-read from the artifact and quoted correctly, or dropped and replaced with a prose
description of the evidence. Evidence that genuinely came from uncommitted or transient state
(a working-tree edit, a loop run directory) is labeled as such instead of being attributed to
the file. A capture like BUG-3278's — quoting a decision block that exists in no revision of
ENH-3277 — fails the check at write time and is corrected before the issue file ever exists.

## Motivation

Capture is where an issue's evidence enters the pipeline, and it is the cheapest place to check
it — one `grep -F` per quote against a file that is usually already open. Everything downstream
compounds instead of correcting: on BUG-3278, `refine_issue` and `wire_issue` built ~150 lines of
Integration Map, docs inventory, and test wiring on the fabricated mechanism, and two
`verify_issue` passes certified it `VALID` at confidence 98.

BUG-3282 adds the verify-time gate, which is the backstop. This issue adds the write-time gate,
which is the one that prevents the wasted downstream work rather than detecting it afterward.

**Amended 2026-08-22 — there is no backstop.** BUG-3282's gate shipped but was demoted to
advisory, and ENH-3291's measurement (0.070 precision, CI [0.018, 0.122]) settled that it will
not re-arm. `EVIDENCE_UNVERIFIED` is now detected, persisted, and logged, but routes nowhere.
That makes this issue's write-time check the only enforcing point for fabricated evidence, and
it removes the "BUG-3282 catches it anyway" argument for deferring it.

## Scope Boundaries

**In scope**: one new pre-write step in `skills/capture-issue/SKILL.md` Phase 4, a provenance line
in Conversation Mode so that step knows which spans are memory-sourced, and a structural test.

**Out of scope**:

- **Wiring `ll-verify-evidence` into this phase.** Ruled out on measurement, not on convenience —
  see the amendment below. This is the boundary most likely to be crossed by a future pass acting
  on the issue's original text, which explicitly invited that call once the CLI existed.
- **Re-arming BUG-3282's verify-time gate.** Settled by ENH-3291; this issue does not reopen it,
  and shipping a write-time check is not an argument for reconsidering it.
- **Improving `ll-verify-evidence`'s attribution or span extraction.** That is the only live route
  to making the CLI usable anywhere, but it is a change to the checker, not to capture, and
  belongs in its own issue.

## Proposed Solution

Add a self-check before the Phase 4 `ll-issues create` write:

1. Identify quoted spans in the drafted body that are attributed to a named file or issue ID.
2. For each, read or `grep -F` the cited artifact and confirm the span appears in it.
3. On a miss, either drop the quote and describe the evidence in prose, or read the artifact and
   quote it correctly — never write the unverified span.
4. When the evidence genuinely came from an uncommitted or transient state (a working-tree edit, a
   loop run directory), say so explicitly in the issue rather than attributing it to the file.

> **Amended 2026-08-22 — do *not* call `ll-verify-evidence` here.** This section previously said
> that once BUG-3282 landed its checker as a CLI, this phase should call it rather than
> reimplementing span extraction. BUG-3282 has since shipped `ll-verify-evidence` and is `done`,
> so that condition is met — but ENH-3291 measured the checker at **0.070 precision**
> (95% CI [0.018, 0.122]), and its two dominant false-positive classes are **mis-attribution**
> (49%) and **not-a-quote** (38%). A freshly-captured `## Current Behavior` / `## Steps to
> Reproduce` is *dense* in exactly those shapes: command output, run-log excerpts, and
> reproduction steps that name an issue as the run argument. Capture time is therefore the
> **worst** place to put that checker, not an upgrade over prose.
>
> The check below stays self-contained, and it is better-targeted than the CLI for a reason the
> CLI cannot replicate: step 2 records whether each quote came from a *fresh file read* or from
> *conversation memory*, and only memory-sourced spans need verifying. That provenance is the
> actual signal — `ll-verify-evidence` has no access to it and must guess attribution from
> surrounding prose, which is precisely where its precision goes.

## Integration Map

### Files to Modify

- `skills/capture-issue/SKILL.md` — new pre-write validation step in Phase 4

`skills/capture-issue/SKILL.md` is the **only** file to modify. An earlier revision listed
"the evidence checker from BUG-3282, if it ships as a CLI — call site, no new logic" as a second
target; that is struck (see Proposed Solution → Amended 2026-08-22). `ll-verify-evidence` now
exists but must not be wired in here.

### Tests

- `scripts/tests/` skill-prose assertions following the existing structural-test convention for
  LLM-executed skills (see `test_decide_issue_skill.py`): assert the pre-write check phrase and
  its "drop or correct, never write unverified" instruction are present

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_capture_issue_skill.py` — the existing structural-test file for this skill
  (currently only `TestCaptureIssueNearDuplicateCheck`, covering Phase 2). Add a new test class
  here for the Phase 4 evidence-quote check — this is the file to update, not a new file, and
  should follow its own `_phase_text()`-style heading-slice helper (bound the assertion to the
  Phase 4 slice so it doesn't accidentally match elsewhere in the file) [Agent 3 finding].
- Style precedent beyond the `testable` scan already cited: `skills/decide-issue/SKILL.md`'s
  Phase 2.5/Phase 3b inline gates (`TestPhase3bInlineProvisionalScan` /
  `TestOptionsMissing` in `test_decide_issue_skill.py`) show the same
  "self-contained prose check with an explicit exit-cleanly escape hatch" shape and can be
  used alongside the `testable` gate as a second reference pattern [Agent 2 finding].
- Confirmed clean (no action needed): no test asserts on Phase 4's step count or order, so
  inserting a new step does not break `test_feat1896_skill_bridges.py::TestCaptureIssueDecisionsBridge`
  or any other existing test [Agent 2, Agent 3 finding].

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-21 — based on codebase analysis:_

- Insertion point confirmed: `skills/capture-issue/SKILL.md` Phase 4 "Action: Create New Issue" — the new pre-write check lands as a new step between step 2 (`testable` keyword-scan gate, lines 233–238) and step 3 (the `ll-issues create` write, lines 239–248). Step 2 is the closest existing precedent inside the same phase for a content-level gate before the write.
- ~~No existing span/quote-verification utility exists in `scripts/little_loops/` to call~~ — true when written (2026-08-21), **superseded 2026-08-22**: BUG-3282 shipped `ll-verify-evidence` (`scripts/little_loops/cli/verify_evidence.py`, entry point `ll-verify-evidence`), which does exactly this span extraction and artifact matching. The original search (`grep_capable_files|verify_evidence|check_quote|_check_evidence_quotes`) predated it. The conclusion nonetheless stands for a different reason: the check must be self-contained skill prose **not because nothing exists, but because what exists measures 0.070 precision and is mis-targeted for capture-time input** (ENH-3291; see Proposed Solution → Amended 2026-08-22).
- Conversation Mode (`SKILL.md:108-157`) is the exact path BUG-3278 was captured through: it instructs extracting "Source context (brief quote or summary...)" from conversation history rather than a fresh file read — this is where an unverified quote enters `$ISSUE_SUMMARY` before Phase 4 ever runs.
- `commands/verify-issues.md:69-72,126-130` is the only existing quote-check in the codebase, and it is scoped to source-code snippets only (`"Validate code snippets": Does quoted code match current code?`), not evidence attributed to another `.issues/` file — confirming there is no existing evidence-quote pattern to mirror beyond this narrower code-only precedent.

## Program Design

### Types
N/A — no new data shape introduced; the check operates on strings already present in `$ISSUE_SUMMARY`.

### Signatures
- `cmd_create(args) -> int` — the handler behind Phase 4's write call; reads the body from stdin when `--body-file -` is passed (`create.py:540`, stdin read at `:554`)
- `create_issue(spec) -> Path` — writes the file via exclusive-create; called by `cmd_create` (`create.py:406`, exclusive-create at `:458`)

Neither signature inspects quoted content against an external artifact — confirming the gap: nothing on this call path can catch an unverified quote before the write.

### Call Path
`SKILL.md Phase 1` (title/description extraction) -> `SKILL.md Phase 4 step 2` (`testable` keyword-scan gate) -> new pre-write evidence check (this issue) -> `SKILL.md Phase 4 step 3` (`ll-issues create --body-file -`) -> `cmd_create` -> `create_issue`

### Decision Rules
- **Gap kind**: pre-write evidence-quote check, gating the Phase 4 step 3 write.
- **Trigger**: a **memory-sourced** quoted span (fenced block or inline backticks) in the drafted `$ISSUE_SUMMARY` that is attributed to a named file or issue ID. Narrowed 2026-08-22: spans recorded by step 2 as coming from a fresh file read are already verified by construction and are not re-checked. Scoping the trigger by provenance rather than by shape is what keeps this check precise where `ll-verify-evidence` is not.
- **Escape hatch**: on a miss, drop the quote and describe the evidence in prose, or re-read the artifact and quote it correctly — never write the unverified span (per Proposed Solution step 3). When evidence came from uncommitted/transient state, say so explicitly rather than attributing it to the file (step 4).
- **Confirmed dependency status (revised 2026-08-22)**: BUG-3282 is `done` and `ll-verify-evidence` ships as a CLI, so the dependency this issue was waiting on is **resolved** — but the resolution does **not** change the design. ENH-3291 measured that checker at 0.070 precision with mis-attribution (49%) and not-a-quote (38%) as its dominant false-positive classes, both of which capture-time input is unusually rich in. This step stays self-contained skill prose as a **deliberate choice**, not a workaround for a missing tool. The prior revision's note that "a follow-up pass can replace it with a CLI call once BUG-3282 lands one" is withdrawn.

## Implementation Steps

1. Author the pre-write check as a new step in `skills/capture-issue/SKILL.md` Phase 4, inserted
   between step 2 (the `testable` keyword-scan gate, `:233-238`) and step 3 (the
   `ll-issues create --body-file -` write, `:239-248`): identify quoted spans in `$ISSUE_SUMMARY`
   attributed to a named file or issue ID, verify each with `grep -F` against the cited artifact,
   and apply the drop-or-correct rule — never write an unverified span; label transient-state
   evidence explicitly. Self-contained skill prose, no CLI dependency — a deliberate choice, not
   a gap (see Program Design → Decision Rules: `ll-verify-evidence` exists but is mis-targeted
   for this input at 0.070 precision).
2. Add a provenance line to Conversation Mode (`SKILL.md:108-157`), where the quote enters
   `$ISSUE_SUMMARY`: when extracting "Source context", record whether each quote came from a
   fresh file read or from conversation memory, so the Phase 4 check knows which spans need
   verification rather than re-checking everything.
3. Add a structural test class to `scripts/tests/test_capture_issue_skill.py` (per the wiring
   pass): bound the assertion to the Phase 4 heading slice via its `_phase_text()`-style helper,
   and assert the check phrase and the "drop or correct, never write unverified" instruction are
   present.
4. Verify `python -m pytest scripts/tests/` exits 0.

Step 5 of the prior revision — "when BUG-3282 lands its checker as a CLI, replace step 1's prose
grep instructions with a call site" — is **withdrawn** (2026-08-22). The checker landed; swapping
to it would be a regression. See Proposed Solution → Amended.

## Impact

- **Priority**: P3 — raised in practical importance since capture (2026-08-22): BUG-3282's
  verify-time gate was demoted to **advisory** and will not re-arm (ENH-3291), so it no longer
  blocks anything. This write-time check is now the only enforcing point for the class, not
  merely the one that saves the wasted refine/wire work in between. Left at P3 because it is
  small and the class is rare, but it is no longer backstopped.
- **Effort**: Small-Medium — standalone skill prose. The "Small if BUG-3282's checker exists"
  branch no longer applies: the checker exists and is deliberately not used here.
- **Risk**: Low — the check can only suppress or correct a quote
- **Breaking Change**: No

## Related Key Documentation

- BUG-3282 (`done`) — verify-time detection of the same invariant. It does **not** share a
  checker with this issue, and its gate is advisory only, so it does not backstop this one
- ENH-3291 (`done`) — the precision measurement that settled the advisory posture and rules
  `ll-verify-evidence` out as this phase's implementation
- BUG-3278 — the capture whose fabricated evidence propagated through a full refine loop
- `skills/capture-issue/SKILL.md` Phase 4 — where the check lands

## Status

**Open** | Created: 2026-08-21 | Priority: P3


## Session Log
- `/ll:wire-issue` - 2026-08-21T18:16:11 - `3f6ddaa1-8943-4e02-80c6-991ae42bf623.jsonl`
- `/ll:refine-issue` - 2026-08-21T17:43:40 - `aee80426-6ab1-4a8c-814d-a6f459361121.jsonl`
- `/ll:capture-issue` - 2026-08-21T17:30:51 - `fa57a84b-34e0-4018-9e9e-dd57ed7ef3f3.jsonl`
