---
id: ENH-3423
type: ENH
title: verify-issues auto-mode notes read as unresolved after fixes
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-09'
captured_at: '2026-09-09T19:06:51Z'
program_design_not_applicable: true
---

# ENH-3423: verify-issues auto-mode notes read as unresolved after fixes

## Summary

`/ll:verify-issues` (`commands/verify-issues.md`) has no guidance for how the persisted
`## Verification Notes` section should be worded when `--auto` mode both diagnoses a defect
and applies the fix in the same pass.

Observed running `/ll:verify-issues ENH-3421 --auto`: the command found drifted `file:line`
anchors and one self-contradictory claim in the issue, applied the corrections per section 4's
auto-mode instructions, then wrote a Verification Notes section that opened with
`Verdict: NEEDS_UPDATE` — using the raw verdict-table label as the section lead. Read after the
fact, that reads as an outstanding action item even though the same edit had already resolved
everything it describes. The user had to ask "does it still need update after your changes?
shouldn't the verdict reflect this?" before it was reworded to "Verdict at time of check:
NEEDS_UPDATE (corrections below applied in the same pass...)".

Root cause: section 2.5 ("Check Mode Behavior") defines exactly how the verdict is persisted,
but only for `--check` mode, which never applies fixes — so its `verify_verdict: NON_VALID` /
`VALID` labels always describe the file's true current state. Section 4 ("Update Issue Files")
says to "document what changed or needs correction" but gives no comparable framing rule for
plain `--auto` mode, where verification and remediation happen in the same pass and a bare
verdict label goes stale the instant it's written.

Proposed fix: section 4 (or a new subsection) should instruct that when auto-mode applies
corrections in the same pass as detection, the Verification Notes text must distinguish
"verdict at detection" from "state after auto-fix" — e.g. requiring phrasing like "Verdict at
time of check: X (corrections below applied in this pass; issue is now accurate)" rather than a
bare verdict label, whenever non-destructive fixes were actually applied to the same sections
the note describes.


## Current Behavior

When `/ll:verify-issues --auto` (`commands/verify-issues.md` section 4) detects a defect and
applies the fix in the same pass, the persisted `## Verification Notes` section opens with the
bare verdict-table label (e.g. `Verdict: NEEDS_UPDATE`), reusing the raw verdict enum values from
`#### C. Determine Verdict` as prose — an emergent convention section 4 never actually instructs,
not something copied from section 2.5 (which only governs the `verify_verdict:` frontmatter
field). Because the fix has already landed by the time the note is written, the label describes a
state that no longer exists — a later reader sees "NEEDS_UPDATE" next to corrected content and
reasonably reads it as an unresolved action item.

## Expected Behavior

When auto-mode applies non-destructive corrections in the same pass as detection, section 4
must instruct that the Verification Notes text distinguish "verdict at detection" from "state
after auto-fix" — e.g. `Verdict at time of check: NEEDS_UPDATE (corrections below applied in
this pass; issue is now accurate)` — rather than the bare verdict label section 2.5 defines for
`--check` mode (where no fix is ever applied, so the label stays accurate).

## Motivation

A stale-looking verdict label on an already-fixed issue causes readers (including the user, in
the observed case) to ask whether the issue still needs action, forcing a manual re-read of the
diff to confirm nothing is actually pending. This directly undermines the purpose of persisting
Verification Notes — a durable, trustworthy record of what verification found and did — and the
ambiguity recurs on every `--auto` run that finds and fixes a defect in the same pass, not just
this one instance.

## Proposed Solution

Add a subsection to `commands/verify-issues.md` section 4 ("Update Issue Files"), parallel to
section 2.5's `--check`-mode labeling rule, that governs how `--auto` mode phrases the verdict
when fixes are applied in the same pass. Reuse the verdict enum already defined in section 2.5
(`VALID` / `NON_VALID` variants) rather than inventing new labels — only the surrounding phrasing
changes: prefix the label with "Verdict at time of check:" and append a parenthetical noting
that corrections were applied in this pass, whenever the same pass edited the section(s) the note
describes.

## Integration Map

### Files to Modify
- `commands/verify-issues.md` — section 4 ("Update Issue Files"), adding the auto-mode phrasing
  rule alongside the existing section 2.5 `--check`-mode labeling rule

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
  extends; the new auto-mode rule should sit next to it and reuse the same verdict enum

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

## Implementation Steps

1. Read `commands/verify-issues.md` sections 2.5 and 4 to confirm the exact verdict enum and
   existing `--check`-mode labeling instructions
2. Add a new subsection under section 4 specifying the "Verdict at time of check: X (corrections
   below applied in this pass; issue is now accurate)" phrasing rule, scoped to `--auto` runs
   that both detect and fix in the same pass
3. Verify by re-running `/ll:verify-issues <ID> --auto` against an issue with a known drifted
   anchor and confirming the resulting Verification Notes no longer reads as an open action item

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
  breakage, but recurs on every auto-fix pass and causes real reader confusion
- **Effort**: Small - Single markdown subsection added to `commands/verify-issues.md`; no code
  changes
- **Risk**: Low - Prompt-instruction change only; no behavior change to detection or fix logic,
  only to how the already-applied fix is described
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-09 | Priority: P3

## Success Metrics

A fresh `/ll:verify-issues <ID> --auto` run that both detects and fixes a defect produces
Verification Notes text starting with "Verdict at time of check:" rather than a bare verdict
label, whenever the fix touched the same section the note describes.

## Scope Boundaries

- Does not change the `--check`-mode verdict labeling in section 2.5 — that path never applies
  fixes, so the bare label already stays accurate
- Does not add or rename any verdict enum values (`VALID` / `NON_VALID` variants stay as-is)
- Does not change detection or auto-fix logic itself — only the wording of the note describing
  an already-applied fix

## Backwards Compatibility

## API/Interface

```python
# Example interface/signature
```


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

## Session Log
- `/ll:wire-issue` - 2026-09-09T19:21:35 - `ebf18a6f-ed36-4252-9599-87c271309793.jsonl`
- `/ll:refine-issue` - 2026-09-09T19:14:29 - `42196ace-6931-433b-9da5-c194d57bddf7.jsonl`
- `/ll:format-issue` - 2026-09-09T19:10:19 - `6825e935-9173-4255-b699-a7e303deae32.jsonl`
- `/ll:capture-issue` - 2026-09-09T19:06:59 - `095aaa45-5f8e-445a-8993-2ec43b515f28.jsonl`


## Session Log
- `/ll:verify-issues` - 2026-09-09T19:25:31 - `4abbc21b-fe6c-468c-baf1-354ba4916426.jsonl`
