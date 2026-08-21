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

[What should happen instead]

## Motivation

Capture is where an issue's evidence enters the pipeline, and it is the cheapest place to check
it — one `grep -F` per quote against a file that is usually already open. Everything downstream
compounds instead of correcting: on BUG-3278, `refine_issue` and `wire_issue` built ~150 lines of
Integration Map, docs inventory, and test wiring on the fabricated mechanism, and two
`verify_issue` passes certified it `VALID` at confidence 98.

BUG-3282 adds the verify-time gate, which is the backstop. This issue adds the write-time gate,
which is the one that prevents the wasted downstream work rather than detecting it afterward.

## Proposed Solution

Add a self-check before the Phase 4 `ll-issues create` write:

1. Identify quoted spans in the drafted body that are attributed to a named file or issue ID.
2. For each, read or `grep -F` the cited artifact and confirm the span appears in it.
3. On a miss, either drop the quote and describe the evidence in prose, or read the artifact and
   quote it correctly — never write the unverified span.
4. When the evidence genuinely came from an uncommitted or transient state (a working-tree edit, a
   loop run directory), say so explicitly in the issue rather than attributing it to the file.

If BUG-3282 lands the deterministic checker as a CLI, this phase should call it rather than
reimplementing span extraction in skill prose.

## Integration Map

### Files to Modify

- `skills/capture-issue/SKILL.md` — new pre-write validation step in Phase 4
- The evidence checker from BUG-3282, if it ships as a CLI — call site, no new logic

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
- No existing span/quote-verification utility exists in `scripts/little_loops/` to call — searched for `grep_capable_files|verify_evidence|check_quote|_check_evidence_quotes` and fence/citation-checking helpers; only `fence_spans`/`in_fence` (`text_utils.py`, used by `create.py`'s body-merge logic for section placement, not content verification) turned up. The check must be self-contained skill prose for now (see Program Design → Decision Rules).
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
- **Trigger**: a quoted span (fenced block or inline backticks) in the drafted `$ISSUE_SUMMARY` that is attributed to a named file or issue ID — same span-extraction shape BUG-3282 proposes for verify-time, per that issue's own note that this phase should call BUG-3282's checker "rather than reimplementing span extraction" if it ships as a CLI.
- **Escape hatch**: on a miss, drop the quote and describe the evidence in prose, or re-read the artifact and quote it correctly — never write the unverified span (per Proposed Solution step 3). When evidence came from uncommitted/transient state, say so explicitly rather than attributing it to the file (step 4).
- **Confirmed dependency status**: BUG-3282 (`status: open`) has no implemented checker as of this pass — its own Proposed Solution frames the CLI-vs-prose shape as an open sub-question, and no `ll-verify-*` evidence/span-checking entry point exists in `scripts/pyproject.toml` or `scripts/little_loops/cli/`. This step must therefore be authored as self-contained skill prose (grep-and-verify instructions) now; a follow-up pass can replace it with a CLI call once BUG-3282 lands one.

## Implementation Steps

1. [Major phase 1]
2. [Major phase 2]
3. [Verification approach]

## Impact

- **Priority**: P3 — BUG-3282 catches the same class at verify time; this one saves the wasted
  refine/wire work in between
- **Effort**: Small if BUG-3282's checker exists; Small-Medium standalone
- **Risk**: Low — the check can only suppress or correct a quote
- **Breaking Change**: No

## Related Key Documentation

- BUG-3282 — verify-time enforcement of the same invariant; shares the checker
- BUG-3278 — the capture whose fabricated evidence propagated through a full refine loop
- `skills/capture-issue/SKILL.md` Phase 4 — where the check lands

## Status

**Open** | Created: 2026-08-21 | Priority: P3


## Session Log
- `/ll:wire-issue` - 2026-08-21T18:16:11 - `3f6ddaa1-8943-4e02-80c6-991ae42bf623.jsonl`
- `/ll:refine-issue` - 2026-08-21T17:43:40 - `aee80426-6ab1-4a8c-814d-a6f459361121.jsonl`
- `/ll:capture-issue` - 2026-08-21T17:30:51 - `fa57a84b-34e0-4018-9e9e-dd57ed7ef3f3.jsonl`
