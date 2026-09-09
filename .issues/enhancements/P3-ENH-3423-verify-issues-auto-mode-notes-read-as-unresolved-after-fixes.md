---
id: ENH-3423
type: ENH
title: verify-issues notes read as unresolved after same-pass fixes
priority: P3
status: done
discovered_by: ll-issues-create
discovered_date: '2026-09-09'
captured_at: '2026-09-09T19:06:51Z'
completed_at: '2026-09-09T20:14:11Z'
program_design_not_applicable: true
confidence_score: 100
outcome_confidence: 85
score_complexity: 25
score_test_coverage: 10
score_ambiguity: 25
score_change_surface: 25
---

# ENH-3423: verify-issues notes read as unresolved after same-pass fixes

## Summary

`/ll:verify-issues` (`commands/verify-issues.md`) has no guidance for how the persisted
`## Verification Notes` section should be worded when a run both diagnoses a defect and applies
the fix in the same pass. This happens in **both** non-check modes: `--auto` (section 3 skipped,
section 4 applies non-destructive fixes without prompting) and interactive (section 3 gets
approval, section 4 applies the same fixes). Only `--check` mode never applies fixes.

Observed running `/ll:verify-issues ENH-3421 --auto`: the command found drifted `file:line`
anchors and one self-contradictory claim in the issue, applied the corrections per section 4,
then wrote a Verification Notes section that opened with `Verdict: NEEDS_UPDATE` — using the raw
verdict-table label from `#### C. Determine Verdict` as the section lead. Read after the fact,
that reads as an outstanding action item even though the same edit had already resolved
everything it describes. The user had to ask "does it still need update after your changes?
shouldn't the verdict reflect this?" before it was reworded to "Verdict at time of check:
NEEDS_UPDATE (corrections below applied in the same pass...)".

The same staleness exists one layer down in the frontmatter. Section 2.5 writes
`verify_verdict:` only in `--check` mode; a later non-check pass that fixes every finding leaves
a prior `verify_verdict: NON_VALID` in place. 32 issues under `.issues/` currently carry that
value, and nothing distinguishes the ones a subsequent fix pass already resolved.

Root cause: section 2.5 ("Check Mode Behavior") defines exactly how the verdict is persisted,
but only for `--check` mode, which never applies fixes — so its labels always describe the
file's true current state. Section 4 ("Update Issue Files") says to "document what changed or
needs correction" but gives no framing rule for the fix-applying modes, where verification and
remediation happen in the same pass and a bare verdict label goes stale the instant it's written.

## Current Behavior

When `/ll:verify-issues` (`commands/verify-issues.md` section 4) detects a defect and applies
the fix in the same pass — in `--auto` or interactive mode — the persisted
`## Verification Notes` section opens with the bare verdict-table label (e.g.
`Verdict: NEEDS_UPDATE`), reusing the raw verdict enum values from `#### C. Determine Verdict`
as prose — an emergent convention section 4 never actually instructs, not something copied from
section 2.5 (which only governs the `verify_verdict:` frontmatter field). Because the fix has
already landed by the time the note is written, the label describes a state that no longer
exists — a later reader sees "NEEDS_UPDATE" next to corrected content and reasonably reads it
as an unresolved action item. 221 existing issue files under `.issues/` carry a bare
`Verdict:` label of this shape.

Separately, if the issue's frontmatter already holds a `verify_verdict:` value from an earlier
`--check` run, the non-check pass leaves it untouched even after fixing everything it flagged.

## Expected Behavior

Whenever section 4 applies corrections in the same pass as detection (any non-`--check` mode),
the Verification Notes text must distinguish "verdict at detection" from "state after fix",
using the section 2C verdict value as the label, in one of two shapes:

- **Fully resolved**: `Verdict at time of check: NEEDS_UPDATE (corrections below applied in
  this pass; issue is now accurate)`
- **Partially resolved**: the same lead line, followed by an explicit `Remaining:` line listing
  each finding the pass did not correct (e.g. a decision that needs human input, or a
  destructive change that auto mode is not allowed to make)

A bare `Verdict: X` label is never written by a fix-applying pass.

If the frontmatter already carries a `verify_verdict:` field, the same pass rewrites it to
reflect the post-fix state: `VALID` when nothing remains, otherwise the section 2.5 mapping of
the residual verdict. The field is not inserted if absent — that stays `--check` mode's job.

## Motivation

A stale-looking verdict label on an already-fixed issue causes readers (including the user, in
the observed case) to ask whether the issue still needs action, forcing a manual re-read of the
diff to confirm nothing is actually pending. This directly undermines the purpose of persisting
Verification Notes — a durable, trustworthy record of what verification found and did — and the
ambiguity recurs on every fix-applying run that finds and fixes a defect in the same pass, not
just this one instance.

The two-branch shape matters for the opposite failure: a "corrections applied; issue is now
accurate" line with no `Remaining:` clause would hide real pending work just as the bare label
invented fake pending work.

## Proposed Solution

Add a numbered subsection `### 4.1` under section 4 ("Update Issue Files") of
`commands/verify-issues.md`, parallel to section 2.5's `--check`-mode labeling rule, that
governs how a fix-applying pass phrases the verdict. Specifically:

1. **Label source**: reuse the verdict value from the `#### C. Determine Verdict` table
   (`commands/verify-issues.md:234-248`) — `VALID`, `NEEDS_UPDATE`, `OUTDATED`, etc. — not the
   collapsed `VALID`/`NON_VALID` frontmatter enum from section 2.5. Only the surrounding
   phrasing changes: prefix the label with "Verdict at time of check:" and append a
   parenthetical noting that corrections were applied in this pass.
2. **Two-branch template**: fully-resolved vs. partially-resolved with a mandatory `Remaining:`
   line, as in Expected Behavior. Formalize the ENH-3421 precedent wording
   (`.issues/enhancements/P3-ENH-3421-*.md:459-461`) as the fully-resolved form rather than
   inventing new phrasing.
3. **Applicability**: the rule fires whenever section 4 edited the section(s) the note
   describes, in any non-`--check` mode. `--check` mode is unaffected (it never reaches
   section 4's content edits).
4. **Frontmatter sync**: if `verify_verdict:` already exists in the frontmatter, rewrite it in
   place per Expected Behavior. Do not insert it when absent.

## Integration Map

### Files to Modify
- `commands/verify-issues.md` — section 4 ("Update Issue Files"), adding the `### 4.1`
  fix-applying-pass phrasing rule alongside the existing section 2.5 `--check`-mode labeling
  rule; section 4's opening "For issues needing updates" bullets should point at 4.1

### Dependent Files (Callers/Importers)
- N/A — `commands/verify-issues.md` is invoked directly as `/ll:verify-issues`; no other file
  imports or calls into it

_Wiring pass added by `/ll:wire-issue`:_
- `.gemini/commands/verify-issues.toml` — host-mirror carrying the full section 4 body
  (`### 4. Update Issue Files` at line 334, `Add a `## Verification Notes` section` at line 337);
  goes stale the moment `commands/verify-issues.md` changes [Agent 1 finding]
- `.qwen/commands/ll/verify-issues.md` — same host-mirror pattern, lines 335/338 [Agent 1 finding]
- `.kimi-code/skills/ll-verify-issues/SKILL.md` — same host-mirror pattern, lines 352/355
  [Agent 1 finding]
- `skills/ll-verify-issues/SKILL.md` (codex stub) — unaffected; it's a pointer stub that doesn't
  duplicate section 4 body text, confirmed not to drift [Agent 2 finding]

### Similar Patterns
- Section 2.5 ("Check Mode Behavior") already defines the verdict-labeling convention this issue
  extends; the new subsection should sit next to it in spirit and cite the section 2C table
  for the label value and the section 2.5 mapping for the frontmatter rewrite

### Tests
- N/A for parsing/assertion coverage — no test parses `## Verification Notes` body prose or
  asserts on a bare `Verdict:` label; confirmed via repo-wide search of `scripts/tests/` and
  `scripts/little_loops/` [Agent 3 finding]

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_wiring_skills_and_commands.py::test_host_artifacts_are_not_stale[commands-gemini]`,
  `[commands-qwen]`, `[commands-kimi-code]` — will FAIL after editing `commands/verify-issues.md`
  until the three host mirrors above are regenerated; the test content-compares `ll-adapt`'s fresh
  output against the on-disk mirror and asserts `adapted == 0` [Agent 2 finding]

### Documentation
- N/A — the fix is the command file itself; no separate docs describe this wording convention

### Configuration
- N/A

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-09 — based on codebase analysis:_

- Section 2.5 ("Check Mode Behavior") spans `commands/verify-issues.md:287-336`; it labels only the `verify_verdict:` frontmatter field (an enum collapse — `OUTDATED`/`RESOLVED`/`INVALID`/`NEEDS_UPDATE`/`REGRESSION_LIKELY`/`POSSIBLE_REGRESSION`/`DEP_ISSUES`/`DECISIONS_VIOLATION` all → `NON_VALID`, while `VALID`/`EVIDENCE_UNVERIFIED`/`PROPOSAL_UNSOUND` stay distinct) — it never mandates any `Verdict: X` prose string, only the frontmatter value.
- Section 4 ("Update Issue Files") is the entire block at `commands/verify-issues.md:351-360` today — two unlettered bullet groups, no subsection numbering, and no wording template for `## Verification Notes` prose.
- `commands/verify-issues.md:362` already defines `### 4.5 Append Session Log Entries` as the next sibling heading, so a new subsection under section 4 must be numbered `4.1`-`4.4` (`4.5` is taken) or inserted as an unlettered block ahead of it.
- The bare `Verdict: X` prose convention this issue describes is emergent, not instructed: it reuses the raw verdict-table labels from `#### C. Determine Verdict` (`commands/verify-issues.md:234-248`) as prose, with no section-4 rule connecting the two. Existing instances: `.issues/epics/P5-EPIC-1463-track-deferred-codex-cli-interop-gaps.md:305`, `.issues/epics/P2-EPIC-1867-orchestrator-fsm-decomposition.md:218`, `.issues/features/P2-FEAT-2551-code-run-gate-oracle-asset.md:725`.
- Live precedent for the proposed fix already exists, hand-written after user pushback in the sibling issue this one was captured from: `.issues/enhancements/P3-ENH-3421-*.md:459-461` reads "Verdict at time of check: **NEEDS_UPDATE** (corrections below applied in the same pass, so the issue as it now reads is up to date — this section is a record of what was wrong and fixed, not an outstanding action item)." The new subsection should formalize this exact wording as the instruction rather than invent new phrasing.
- Confirmed no overlap risk with `commands/ready-issue.md`: its three verdict tables (`ready-issue.md:319-330`, `:347-352`, `:541-551`) use a disjoint 7-value enum (`READY`/`CORRECTED`/`BLOCKED`/`NOT_READY`/`CLOSE`/`REGRESSION_LIKELY`/`POSSIBLE_REGRESSION`) and never write a persisted `Verdict: X` body-text label — they route in-session automation only, so the new subsection has no cross-command wording collision to reconcile.

_Added by review — 2026-09-09:_

- Mode flags at `commands/verify-issues.md:38-47`: `--auto` sets `AUTO_MODE`; `--check` sets both `CHECK_MODE` and `AUTO_MODE`. Section 3 (`:338-349`) is skipped only under `AUTO_MODE`; section 4 runs in every mode except `--check`. So interactive runs reach section 4's fix path too — the rule cannot be scoped to `--auto` alone.
- The only automated caller, `refine-to-ready-issue.yaml`, invokes `/ll:verify-issues <id> --check --auto` and reads `verify_verdict:` immediately afterward. The new rule never fires inside that loop, and the frontmatter-sync step does not interact with its gate because `--check` always rewrites the field before the gate reads it.
- Counts at HEAD: 221 bare `Verdict:` labels across `.issues/` (excluding "Verdict at time of check" forms); 179 issues carry `verify_verdict:` and 32 of those hold `NON_VALID`. Neither set is backfilled by this issue.

## Implementation Steps

1. Read `commands/verify-issues.md` sections 2C (`:234-248`), 2.5 (`:287-336`), and 4
   (`:351-360`) to confirm the exact verdict table, the `--check`-mode frontmatter mapping, and
   the current section 4 wording
2. Insert `### 4.1 Verdict Phrasing When Fixes Are Applied in the Same Pass` between section 4's
   bullets and `### 4.5 Append Session Log Entries`, containing:
   - the applicability rule (any non-`--check` mode, whenever section 4 edited the section(s)
     the note describes)
   - the label-source rule (section 2C value, never the collapsed section 2.5 enum)
   - the two-branch template (fully resolved / partially resolved with `Remaining:`)
   - the frontmatter-sync rule (rewrite `verify_verdict:` in place if present; never insert)
3. Update section 4's "For issues needing updates" bullets to reference 4.1 for the note's
   opening line
4. Regenerate host mirrors (see Wiring Phase) and run the three `test_host_artifacts_are_not_stale`
   params
5. Verify by re-running `/ll:verify-issues <ID> --auto` against an issue with a known drifted
   anchor and confirming the resulting Verification Notes opens with "Verdict at time of check:"
   and, when something is left unfixed, carries a `Remaining:` line

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-09 — based on codebase analysis:_

- The new subsection numbers as `4.1` (section 4 currently has no numbered subsections, and `4.5 Append Session Log Entries` at `commands/verify-issues.md:362` already occupies the next sibling slot) — do not reuse `4.5` or leave it unnumbered if other section-4 subsections get added later.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Regenerate host mirrors after editing `commands/verify-issues.md`: run `ll-adapt --host gemini
  --apply`, `ll-adapt --host qwen --apply`, and `ll-adapt --host kimi-code --apply` so
  `.gemini/commands/verify-issues.toml`, `.qwen/commands/ll/verify-issues.md`, and
  `.kimi-code/skills/ll-verify-issues/SKILL.md` pick up the new subsection
- Confirm `scripts/tests/test_wiring_skills_and_commands.py::test_host_artifacts_are_not_stale[commands-gemini]`,
  `[commands-qwen]`, and `[commands-kimi-code]` pass after regeneration (they fail on the raw
  `commands/verify-issues.md` edit alone)

## Impact

- **Priority**: P3 - Wording-only defect in a command's persisted output; no functional
  breakage, but recurs on every fix-applying pass and causes real reader confusion
- **Effort**: Small - Single markdown subsection added to `commands/verify-issues.md` plus
  mirror regeneration; no code changes
- **Risk**: Low - Prompt-instruction change only; no behavior change to detection or fix logic.
  The frontmatter-sync step only rewrites a field that already exists and only in modes the
  automated loop never uses.
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-09 | Priority: P3

## Success Metrics

- A fresh `/ll:verify-issues <ID> --auto` (or interactive) run that both detects and fixes a
  defect produces Verification Notes text starting with "Verdict at time of check:" rather than
  a bare verdict label, whenever the fix touched the same section the note describes.
- When the same run leaves any finding uncorrected, the note carries an explicit `Remaining:`
  line naming it.
- If the issue's frontmatter already had `verify_verdict:`, its value after the run matches the
  post-fix state rather than the pre-fix detection.

## Scope Boundaries

- Does not change the `--check`-mode verdict labeling in section 2.5 — that path never applies
  fixes, so the bare label already stays accurate
- Does not add or rename any verdict enum values (section 2C table and section 2.5 mapping stay
  as-is)
- Does not change detection or auto-fix logic itself — only the wording of the note describing
  an already-applied fix, and the value of an already-present `verify_verdict:` field
- Does **not** backfill the 221 existing bare `Verdict:` labels or the 32 existing
  `verify_verdict: NON_VALID` fields under `.issues/`; those are left as-is
- Does not insert `verify_verdict:` into frontmatter that lacks it — that remains `--check`
  mode's responsibility
- Does not address the duplicate `## Session Log` heading pattern (55 issue files at HEAD,
  including this one); that is a separate defect in the verify-issues write path or
  `ll-issues append-log` and should be captured on its own

## Backwards Compatibility

Existing Verification Notes and frontmatter values are untouched. Consumers of
`verify_verdict:` (the `check_verify_verdict` gate in `refine-to-ready-issue.yaml`) only read
the field after a `--check` run that has just rewritten it, so the non-check sync cannot change
what the gate sees.

## API/Interface

N/A — prompt-instruction change only.


## Verification Notes

_Added by `/ll:verify-issues` — 2026-09-09:_

Verdict at time of check: **VALID**. All claims about the current state of
`commands/verify-issues.md` were checked against HEAD and confirmed accurate: section 2.5 spans
lines 287-336 exactly as cited, section 4 is the unlettered two-bullet-group block at lines
351-361 with no wording rule for `## Verification Notes` prose, `4.5` occupies the next sibling
heading so a new subsection must number `4.1`, and the ENH-3421 precedent quote at
`.issues/enhancements/P3-ENH-3421-*.md:459-461` matches verbatim.

`ll-verify-evidence` initially flagged the **Current Behavior** section (line 49): it had
attributed `Verdict: NEEDS_UPDATE` as "copied verbatim from the `--check`-mode labeling rule in
section 2.5" — but section 2.5 only mandates a `verify_verdict:` **frontmatter** value
(`NON_VALID`/`VALID`/etc.), never a `Verdict: X` **prose** string, so that exact framing was
inaccurate. Corrected in place: the sentence now attributes the bare-label convention to reuse of
the `#### C. Determine Verdict` enum table as prose, matching this issue's own Codebase Research
Findings (line 126), which already identified the convention as "emergent, not instructed." The
tool still flags the `Verdict: NEEDS_UPDATE` span after the fix — this is the known low-precision
detector behavior BUG-3282 documented (0.13-0.20 precision, advisory-only): it can't distinguish
an "e.g." illustrative example of runtime output from a literal file-content quote, and the
sentence no longer claims the span is copied from file source text. Manual review confirms this
is not fabricated evidence.

_Review pass — 2026-09-09:_ Rewrote the issue to (1) fix the Proposed Solution's enum reference
(it cited section 2.5's collapsed `VALID`/`NON_VALID` set; the prose label must come from the
section 2C table), (2) widen applicability from `--auto` to every non-`--check` mode since
interactive runs reach section 4's fix path too, (3) add the partially-resolved `Remaining:`
branch, (4) add the `verify_verdict:` frontmatter-sync rule, and (5) state explicitly that
existing bare labels and stale frontmatter are not backfilled.

## Resolution

Added `### 4.1 Verdict Phrasing When Fixes Are Applied in the Same Pass` to
`commands/verify-issues.md` between section 4's bullets and `### 4.5 Append Session Log
Entries`, exactly as scoped in Implementation Steps: applicability rule (any
non-`--check` mode reaching section 4's content edits), label-source rule (section 2C
verdict value, never the collapsed 2.5 enum), the two-branch template (fully resolved
/ partially resolved with a mandatory `Remaining:` line), and the `verify_verdict:`
frontmatter-sync rule (rewrite in place if present, never insert). Section 4's opening
bullet now points at 4.1. Regenerated the three host mirrors
(`.gemini/commands/verify-issues.toml`, `.qwen/commands/ll/verify-issues.md`,
`.kimi-code/skills/ll-verify-issues/SKILL.md`) via `ll-adapt --host <host> --apply`;
all three `test_host_artifacts_are_not_stale` params pass. Full suite run:
23685 passed, 5 pre-existing failures unrelated to this change (confirmed via
`git stash` against unmodified `main`: `test_referenced_env_names_are_covered`,
`test_no_unallowlisted_raw_priority_regex`, `test_allowlist_entries_still_exist`,
`test_no_new_unverifiable_evidence`, `test_no_prose_dependency_drift_in_repo`).

**Fix Commit**: (pending commit)
**Files Changed**: `commands/verify-issues.md`, `.gemini/commands/verify-issues.toml`,
`.qwen/commands/ll/verify-issues.md`, `.kimi-code/skills/ll-verify-issues/SKILL.md`

## Session Log
- `/ll:manage-issue` - 2026-09-09T20:13:25 - `92944602-18f5-4634-9223-31cdecc34ddb.jsonl`
- `/ll:confidence-check` - 2026-09-09T19:37:47 - `0feb3751-5c38-412d-892d-09fae075ee5e.jsonl`
- `/ll:wire-issue` - 2026-09-09T19:21:35 - `ebf18a6f-ed36-4252-9599-87c271309793.jsonl`
- `/ll:refine-issue` - 2026-09-09T19:14:29 - `42196ace-6931-433b-9da5-c194d57bddf7.jsonl`
- `/ll:format-issue` - 2026-09-09T19:10:19 - `6825e935-9173-4255-b699-a7e303deae32.jsonl`
- `/ll:capture-issue` - 2026-09-09T19:06:59 - `095aaa45-5f8e-445a-8993-2ec43b515f28.jsonl`
- `/ll:confidence-check` - 2026-09-09T19:30:24 - `d938b9b6-8e93-4345-bba5-d4048a09c843.jsonl`
- `/ll:verify-issues` - 2026-09-09T19:25:31 - `4abbc21b-fe6c-468c-baf1-354ba4916426.jsonl`
