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
confidence_score: 98
outcome_confidence: 91
score_complexity: 23
score_test_coverage: 20
score_ambiguity: 24
score_change_surface: 24
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
attributed to a named file or issue ID is checked against that artifact (via the `Grep` tool or a
direct read — not shell `grep`, which this skill is not granted; see Proposed Solution → Tooling
note). Spans matching the documented non-trigger shapes — command output, reproduction-step
arguments, proposed text, bare symbol/path references — are skipped rather than checked. A span
that verifies is written as-is. A span that does not is never written: it is
either re-read from the artifact and quoted correctly, or dropped and replaced with a prose
description of the evidence. Evidence that genuinely came from uncommitted or transient state
(a working-tree edit, a loop run directory) is labeled as such instead of being attributed to
the file. A capture like BUG-3278's — quoting a decision block that exists in no revision of
ENH-3277 — fails the check at write time and is corrected before the issue file ever exists.

## Motivation

Capture is where an issue's evidence enters the pipeline, and it is the cheapest place to check
it — one `Grep` call per quote against a file that is usually already open. Everything downstream
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

**In scope**: one new pre-write step in `skills/capture-issue/SKILL.md` Phase 4, an explicit
non-trigger list so the check does not inherit `ll-verify-evidence`'s false-positive classes, an
`allowed-tools` frontmatter change so the check can actually run, and a structural test.

**Out of scope**:

- **A provenance-tracking mechanism.** Dropped 2026-08-22 — see Proposed Solution → *Provenance
  narrowing withdrawn*. The check verifies every attributed span rather than trying to
  distinguish memory-sourced from fresh-read ones.
- **Instrumenting Direct Mode.** Both modes are now treated identically (verify every attributed
  span), so there is nothing mode-specific left to instrument. Covered, not skipped.
- **Syncing the `.qwen` / `.gemini` / `.kimi-code` host-mirror copies of this SKILL.** They are
  hand-maintained snapshots that already differ from source, with no generating tooling and no
  parity test — see Codebase Research Findings. Re-syncing them is a separate concern.
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

1. Identify quoted spans in the drafted body that are attributed to a named file or issue ID —
   **excluding the non-trigger shapes listed below**.
2. For each, confirm the span appears in the cited artifact, using the **`Grep` tool** (see the
   tooling note below — `grep -F` via Bash is not permitted to this skill). For a span attributed
   to an issue ID rather than a path, resolve the path first with `ll-issues show <ID> --json`,
   which is already permitted by `Bash(ll-issues:*)`. Check the **current working-tree file
   only** — that is sufficient for the motivating case and avoids a `git log -S` sweep.
3. On a miss, either drop the quote and describe the evidence in prose, or read the artifact and
   quote it correctly — never write the unverified span.
4. When the evidence genuinely came from an uncommitted or transient state (a working-tree edit, a
   loop run directory), say so explicitly in the issue rather than attributing it to the file.

### Non-triggers — do not attempt to verify these

> **Added 2026-08-22.** Without this list, the check inherits the exact false-positive classes it
> cites to disqualify `ll-verify-evidence`. ENH-3291 measured that checker at 0.070 precision with
> **mis-attribution (49%)** and **not-a-quote (38%)** as the dominant classes, and this issue's own
> argument is that a freshly-captured `## Current Behavior` / `## Steps to Reproduce` is *dense* in
> those shapes. That argument does not stop applying because the extraction moved from Python into
> skill prose: provenance-free prose extraction has the same failure modes. An unguarded
> drop-or-correct rule would therefore delete real evidence at a comparable rate.
>
> Skip, without verifying:
>
> - **Command output and run-log excerpts** — a pasted traceback, pytest summary, or FSM state
>   transition is not a quotation *of* the file it mentions.
> - **Reproduction steps that name an artifact as an argument** — `` `ll-issues show ENH-3277` ``
>   cites the issue as an input, not as a source of quoted text.
> - **Proposed text** — a snippet the issue is suggesting be *written* (a new config key, a
>   replacement line, a diff's `+` side) is by definition absent from the artifact today.
> - **Symbol and path names in backticks** — `` `create_issue` ``, `` `create.py:406` `` are
>   references, not spans. Only prose or code *quoted as appearing in* the artifact triggers.
>
> When it is ambiguous whether a span is a quotation or one of the above, **leave it alone**. A
> missed fabrication is the failure this issue already tolerated for months; a deleted true quote
> is a new harm this issue would introduce.

### Tooling note — `grep -F` is not available to this skill

`skills/capture-issue/SKILL.md`'s frontmatter grants `Read, Glob, Grep, Write,
Bash(ll-issues:*, git:*), Bash(ll-session:*)`. There is no `Bash(grep:*)`, so the `grep -F`
phrasing used throughout earlier revisions of this issue would dead-end on a permission prompt
in the field. Use the **`Grep` tool**, which is already granted. If a future revision genuinely
needs shell `grep`, it must add `Bash(grep:*)` to the frontmatter in the same change — and the
structural test in Implementation Step 3 asserts the granted tooling matches what the prose
prescribes, precisely so this cannot silently regress.

### Provenance narrowing withdrawn — 2026-08-22

> An earlier revision added a fifth step: tag each span as fresh-read or memory-sourced in
> Conversation Mode, verify only the memory-sourced ones, and treat an absent marker as
> memory-sourced so Direct Mode stays covered. **That design hooks a surface that does not
> exist.**
>
> - **`$ISSUE_SUMMARY` is never constructed anywhere in the skill.** It appears exactly twice,
>   both as a consumer — `SKILL.md:245` (the `ll-issues create --body-file -` heredoc) and
>   `:280`. No phase drafts it. There is no step to attach provenance to.
> - **The field the provenance line would have tagged is the wrong one.** Conversation Mode's
>   "Source context (brief quote or summary of what prompted it)" (`SKILL.md:117`) feeds the
>   *user-facing selection table* at `:126-143` (`- **Context**: [Brief quote from
>   conversation]`). It is not the source of `## Current Behavior` or `## Steps to Reproduce` —
>   the sections BUG-3278's fabricated decision block actually lived in. Those are filled from
>   the template variant with no named authoring step.
>
> So the narrowing would have tracked provenance for a presentation field while leaving the
> defect's actual surface unmarked, and the absent-provenance default would have fired on
> everything anyway. **Resolution: drop the narrowing and verify every attributed span in both
> modes.** The cost is some redundant checking of spans that were freshly read; the benefit is a
> mechanism that hooks the body being written rather than a field beside it. The non-trigger list
> above is what keeps the unnarrowed check from being noisy — it is doing the work provenance was
> supposed to do, on the surface that actually carries the defect.

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
> ~~The check stays self-contained, and it is better-targeted than the CLI for a reason the CLI
> cannot replicate: step 2 records whether each quote came from a *fresh file read* or from
> *conversation memory*, and only memory-sourced spans need verifying. That provenance is the
> actual signal — `ll-verify-evidence` has no access to it and must guess attribution from
> surrounding prose, which is precisely where its precision goes.~~
>
> **The provenance half of that argument is withdrawn (2026-08-22)** — see *Provenance narrowing
> withdrawn* above; there is no drafting step to record provenance at, so the check has no more
> access to it than the CLI does. **The conclusion is unchanged**, but it now rests on the
> non-trigger list rather than on provenance: skill prose can be told, in the same breath, which
> shapes are not quotations at all, and can leave ambiguous spans alone — a judgment call the CLI
> has no way to express. Note this leaves the check facing the same 49%/38% classes it cites
> against the CLI, which is exactly why the non-trigger list is an implementation step and not a
> caveat.

## Integration Map

### Files to Modify

- `skills/capture-issue/SKILL.md` — new pre-write validation step in Phase 4 (body), **and** its
  `allowed-tools:` frontmatter block (`:6-12`) if the authored prose ends up prescribing any tool
  beyond the currently granted `Read, Glob, Grep, Write, Bash(ll-issues:*, git:*),
  Bash(ll-session:*)`. As specified today it does not — the check uses `Grep` and
  `ll-issues show`, both already granted — so this is a no-op in the expected path and a required
  edit in any variant that reaches for shell `grep`

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
  (41 lines; currently only `TestCaptureIssueNearDuplicateCheck`, covering Phase 2). Add a new
  test class here for the Phase 4 evidence-quote check — this is the file to update, not a new
  file, and should follow its own `_phase_text()`-style heading-slice helper (bound the assertion
  to the Phase 4 slice so it doesn't accidentally match elsewhere in the file) [Agent 3 finding].
  - **`_phase_text` is a class method, not a reusable function — "retarget it" costs a small
    refactor. Noted 2026-08-22.** Implementation Step 3 says to "reuse the existing `_phase_text()`
    helper (`:14-19`) retargeted to `### Phase 4: Execute Action`", and the "one helper, one
    convention" framing implies that is free. It is not: `_phase_text` is a private method on
    `TestCaptureIssueNearDuplicateCheck` with `"### Phase 2: Duplicate Detection"` hardcoded in its
    body. **Do this:** lift it to a module-level `_phase_text(heading: str) -> str`, update the
    existing Phase 2 class to call it with its own heading, and have the new class call it with
    `"### Phase 4: Execute Action"`. Three lines moved, one call site updated. The alternative —
    copying the method into the new class — is what produces the fourth divergent heading-slice
    helper the refine pass was already complaining about.
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
  - **Corrected 2026-08-22**: the causal story is right, the mechanism named is not. "Source context" (`:117`) is consumed by the user-facing selection table at `:126-143` (`- **Context**: [Brief quote from conversation]`), and `$ISSUE_SUMMARY` is never assigned anywhere in the file — it appears only at `:245` and `:280`, both as a consumer. Conversation Mode is where the *unverified habit* enters, but there is no named step where a quote is written into the issue body, which is why the provenance design that was built on this bullet had nothing to hook. See Proposed Solution → *Provenance narrowing withdrawn*.
- `commands/verify-issues.md:69-72,126-130` is the only existing quote-check in the codebase, and it is scoped to source-code snippets only (`"Validate code snippets": Does quoted code match current code?`), not evidence attributed to another `.issues/` file — confirming there is no existing evidence-quote pattern to mirror beyond this narrower code-only precedent.

_Added by `/ll:refine-issue` — 2026-08-22 — based on codebase analysis:_

- Test-boundary convention **disagreement**, relevant to Implementation Step 3's structural test: three `_phase_text()`-style heading-slice helpers exist across the skill-prose test suite and they compute the end boundary differently — a generic "next `### ` heading of any name" scan (`test_capture_issue_skill.py:14-19`, `TestCaptureIssueNearDuplicateCheck`) vs. a hardcoded literal next-phase heading string (`test_decide_issue_skill.py:63-70`, `TestOptionExtractionPatterns`) vs. a hardcoded-but-`.find()`-based next-phase string (`test_decide_issue_skill.py:233-238`, `TestPhase3bInlineProvisionalScan`). For `skills/capture-issue/SKILL.md` specifically: `### Phase 4: Execute Action` (`:218`) is immediately followed by `### Phase 4b: Link Relevant Documents` (`:299`) before any other heading, so a generic same-level-heading scan and a hardcoded `"### Phase 4b"` end-string happen to land at the same offset in this file — a coincidence specific to this section, not a codebase-wide guarantee, so the new test class should state which strategy it picked rather than relying on the coincidence silently.
  - **PICKED 2026-08-22: reuse the existing generic-scan helper**, `test_capture_issue_skill.py:14-19` (`TestCaptureIssueNearDuplicateCheck._phase_text`), retargeted from `"### Phase 2: Duplicate Detection"` to `"### Phase 4: Execute Action"`. The non-obvious reason it is safe: that helper searches for `"\n### "` — **h3 only** — so the `#### Action: Create New Issue` (`:220`) and sibling `#### Action:` h4 subheadings inside Phase 4 do *not* terminate the slice, and it lands on `### Phase 4b` (`:299`) as intended. A naive "next heading of any level" scan would instead stop at `:220` and match nothing, silently passing the test. One helper, one convention, already in the target file.
- A third precedent for the "self-contained prose check with an explicit escape hatch" shape exists beyond the two the issue already cites (`testable` keyword-scan gate, decide-issue Phase 2.5/3b): the qualitative-skip guard in `skills/issue-size-review/SKILL.md:166-170` — same shape (field-presence precondition, threshold, explicit "field absent → fall through to normal behavior" escape hatch).
- Contrast precedent: `skills/wire-issue/prose-dependency-gate.md` (`skills/wire-issue/SKILL.md:144`) is a phase-level content gate whose detection logic lives in Python (`ll-issues format-check --format json`), not skill prose — the opposite shape from the self-contained-prose convention this issue follows. Confirms both conventions coexist in the codebase; the issue's Amended note is a precision-driven argument for the self-contained shape in this specific case, not a claim that CLI-delegated gates are unprecedented.
- `create_issue`'s full-body merge path (`_is_full_body`/`_merge_full_body_content`, `create.py:138,221`) matches caller-supplied `##` sections by heading name only, not by content — confirms `create.py` needs no change for this check: the merge logic cannot see, and therefore cannot help verify, quoted content inside a section.
- Host-mirror copies of `skills/capture-issue/SKILL.md` exist at `.qwen/skills/capture-issue/SKILL.md`, `.kimi-code/skills/capture-issue/SKILL.md`, and `.gemini/skills/capture-issue/SKILL.md` (not gitignored). ~~whether these mirrors are generated from it or hand-maintained separately was not determined by this research pass.~~ **Determined 2026-08-22 — they are hand-maintained and already stale; leave them alone.** All three are git-tracked, byte-identical to one another, dated 2026-08-19, and **already differ from** the live `skills/capture-issue/SKILL.md`. No generation or sync tooling exists anywhere in `scripts/little_loops/`, and no test under `scripts/tests/` asserts mirror-to-source parity. So they are drifted snapshots, not build outputs: this issue does **not** update them, and re-syncing them is a separate concern that should not be smuggled in here. The Integration Map's "only file to modify" is correct as written — recorded explicitly so a later pass reads it as a decision rather than an oversight and edits four files.
- No file under `skills/*/SKILL.md` or `commands/*.md` currently calls `ll-verify-evidence` as a functional call site (the only two appearances are `allowed-tools:` entries with no invocation in the body) — confirms the codebase has no existing wiring for this checker to conflict with or be consolidated into.

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
- **Trigger**: a quoted span (fenced block or inline backticks) in the drafted body that is attributed to a named file or issue ID, in **either** capture mode, **minus** the non-trigger shapes enumerated in Proposed Solution → *Non-triggers*. Precision comes from the non-trigger list, not from provenance.
- ~~**Trigger narrowed by provenance**: only **memory-sourced** spans are checked; spans recorded by the Conversation Mode provenance line as coming from a fresh file read are already verified by construction. **Default when provenance is absent → treat as memory-sourced and verify**, which is what extends the check to Direct Mode (`SKILL.md:90`).~~
  **Withdrawn 2026-08-22 — the hook surface does not exist.** `$ISSUE_SUMMARY` is never constructed anywhere in `SKILL.md` (two occurrences, `:245` and `:280`, both consumers), so there is no drafting step to attach a provenance marker to; and Conversation Mode's "Source context" field (`:117`) feeds the user-facing selection table at `:126-143`, not the `## Current Behavior` / `## Steps to Reproduce` sections where BUG-3278's fabrication actually lived. The narrowing would have tagged a presentation field and left the defect's surface unmarked. Full reasoning in Proposed Solution → *Provenance narrowing withdrawn*. The former "absent-provenance default" is now simply the rule: verify every attributed span.
  - The naming-collision note this bullet used to carry (Implementation Step 2 vs. Phase 4's own step 2) is moot — there is no longer an Implementation Step 2 that adds a provenance line.
- **Escape hatch**: on a miss, drop the quote and describe the evidence in prose, or re-read the artifact and quote it correctly — never write the unverified span (per Proposed Solution step 3). When evidence came from uncommitted/transient state, say so explicitly rather than attributing it to the file (step 4). On *ambiguity about whether a span is a quotation at all*, leave it untouched — see the non-trigger list's closing rule.
- **Tooling**: the `Grep` tool, plus `ll-issues show <ID> --json` to resolve an issue ID to a path. Shell `grep` is **not** available — `allowed-tools` (`SKILL.md:6-12`) grants `Bash` only for `ll-issues`, `git`, and `ll-session`. Any revision that reverts to `grep -F` prose must add `Bash(grep:*)` in the same change.
- **Confirmed dependency status (revised 2026-08-22)**: BUG-3282 is `done` and `ll-verify-evidence` ships as a CLI, so the dependency this issue was waiting on is **resolved** — but the resolution does **not** change the design. ENH-3291 measured that checker at 0.070 precision with mis-attribution (49%) and not-a-quote (38%) as its dominant false-positive classes, both of which capture-time input is unusually rich in. This step stays self-contained skill prose as a **deliberate choice**, not a workaround for a missing tool. The prior revision's note that "a follow-up pass can replace it with a CLI call once BUG-3282 lands one" is withdrawn.

## Implementation Steps

1. Author the pre-write check as a new step in `skills/capture-issue/SKILL.md` Phase 4, inserted
   between step 2 (the `testable` keyword-scan gate, `:233-238`) and step 3 (the
   `ll-issues create --body-file -` write, `:239-248`): identify quoted spans in the drafted body
   attributed to a named file or issue ID, verify each against the cited artifact with the
   **`Grep` tool** (resolving an issue ID to a path via `ll-issues show <ID> --json` first), and
   apply the drop-or-correct rule — never write an unverified span; label transient-state evidence
   explicitly. Check the current working-tree file only. Self-contained skill prose, no CLI
   dependency — a deliberate choice, not a gap (see Program Design → Decision Rules:
   `ll-verify-evidence` exists but is mis-targeted for this input at 0.070 precision).
   **Do not write `grep -F`**: this skill has no `Bash(grep:*)` grant (see Proposed Solution →
   Tooling note).
2. **Author the non-trigger list into the same step** (Proposed Solution → *Non-triggers*):
   command output and run-log excerpts, reproduction steps naming an artifact as an argument,
   proposed/replacement text, and bare symbol or path references are skipped without checking;
   ambiguous spans are left alone. This is load-bearing, not a caveat — without it the check
   reproduces the mis-attribution (49%) and not-a-quote (38%) failure classes that ENH-3291
   measured on `ll-verify-evidence`, and the drop-or-correct rule turns those false positives
   into deleted true evidence.
   - *(Replaces the prior Step 2, "add a provenance line to Conversation Mode", withdrawn
     2026-08-22 — see Program Design → Decision Rules. It hooked `$ISSUE_SUMMARY`, which no phase
     constructs, via a field that feeds the user-facing selection table rather than the issue
     body. Nothing mode-specific remains: both modes verify every attributed span.)*
3. Add a structural test class to `scripts/tests/test_capture_issue_skill.py` (per the wiring
   pass), bounding the assertion to the Phase 4 heading slice. First lift `_phase_text` from a
   private method on `TestCaptureIssueNearDuplicateCheck` (`:14-19`) to a module-level
   `_phase_text(heading: str)` and update that class's call site — it cannot simply be
   "retargeted" in place (see the wiring note). It matches `"\n### "` (h3 only), so Phase 4's
   `#### Action:` subheadings do not truncate the slice; `### Phase 4b` (`:299`) is the terminator.
   Assert within that slice:
   - the check phrase is present;
   - the "drop or correct, never write unverified" instruction is present;
   - **at least one non-trigger class is named** — the assertion that stops a later edit from
     quietly reducing this to an unguarded verify-everything rule;
   - **the frontmatter grants every tool the Phase 4 prose prescribes** — read `allowed-tools`
     and assert the check does not reference a Bash command outside the granted set. This is the
     guard against the `grep -F` regression, and it belongs in the test rather than only in prose.
4. Verify `python -m pytest scripts/tests/` exits 0.

Step 5 of an earlier revision — "when BUG-3282 lands its checker as a CLI, replace step 1's prose
grep instructions with a call site" — is **withdrawn** (2026-08-22). The checker landed; swapping
to it would be a regression. See Proposed Solution → Amended.

## Impact

- **Priority**: P3 — raised in practical importance since capture (2026-08-22): BUG-3282's
  verify-time gate was demoted to **advisory** and will not re-arm (ENH-3291), so it no longer
  blocks anything. This write-time check is now the only enforcing point for the class, not
  merely the one that saves the wasted refine/wire work in between. Left at P3 because it is
  small and the class is rare, but it is no longer backstopped.
- **Effort**: Small-Medium — standalone skill prose. The "Small if BUG-3282's checker exists"
  branch no longer applies: the checker exists and is deliberately not used here. Dropping the
  provenance mechanism (2026-08-22) removes one implementation step; the non-trigger list adds
  roughly the same amount of prose back.
- **Risk**: **Low-Medium — revised 2026-08-22.** The prior reading ("Low — the check can only
  suppress or correct a quote") treated suppression as free. It is not: suppressing a *correct*
  quote destroys real evidence at the write point, with no downstream recovery, and the issue's
  own cited measurement puts the not-a-quote false-positive class at 38% for automated span
  extraction on this kind of input. The non-trigger list plus the leave-ambiguous-spans-alone
  rule is what buys this back down; without them the risk would exceed the benefit. Rated
  Low-Medium **as specified**, and the structural test's non-trigger assertion is what keeps it
  there.
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
- `/ll:confidence-check` - 2026-08-22T19:22:18 - `26eb7292-b430-4fe4-a2ae-90652d09d843.jsonl`
- `/ll:review-issue (manual)` - 2026-08-22T18:08:45 - `8e5158e7-e170-4b3d-ab1f-2afbae53a801.jsonl`
- `/ll:refine-issue` - 2026-08-22T16:48:02 - `0189866f-e38b-421c-a800-383e0d98aaa2.jsonl`
- `/ll:wire-issue` - 2026-08-21T18:16:11 - `3f6ddaa1-8943-4e02-80c6-991ae42bf623.jsonl`
- `/ll:refine-issue` - 2026-08-21T17:43:40 - `aee80426-6ab1-4a8c-814d-a6f459361121.jsonl`
- `/ll:capture-issue` - 2026-08-21T17:30:51 - `fa57a84b-34e0-4018-9e9e-dd57ed7ef3f3.jsonl`
