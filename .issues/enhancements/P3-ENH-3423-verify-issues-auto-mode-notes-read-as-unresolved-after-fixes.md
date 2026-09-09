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
bare verdict-table label (e.g. `Verdict: NEEDS_UPDATE`), copied verbatim from the `--check`-mode
labeling rule in section 2.5. Because the fix has already landed by the time the note is
written, the label describes a state that no longer exists — a later reader sees "NEEDS_UPDATE"
next to corrected content and reasonably reads it as an unresolved action item.

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

### Similar Patterns
- Section 2.5 ("Check Mode Behavior") already defines the verdict-labeling convention this issue
  extends; the new auto-mode rule should sit next to it and reuse the same verdict enum

### Tests
- N/A — this is prompt-instruction wording for a Claude Code command, not executable code; no
  pytest coverage applies (see `.claude/CLAUDE.md` § Testing & CI Policy scope)

### Documentation
- N/A — the fix is the command file itself; no separate docs describe this wording convention

### Configuration
- N/A

## Implementation Steps

1. Read `commands/verify-issues.md` sections 2.5 and 4 to confirm the exact verdict enum and
   existing `--check`-mode labeling instructions
2. Add a new subsection under section 4 specifying the "Verdict at time of check: X (corrections
   below applied in this pass; issue is now accurate)" phrasing rule, scoped to `--auto` runs
   that both detect and fix in the same pass
3. Verify by re-running `/ll:verify-issues <ID> --auto` against an issue with a known drifted
   anchor and confirming the resulting Verification Notes no longer reads as an open action item

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


## Session Log
- `/ll:format-issue` - 2026-09-09T19:10:19 - `6825e935-9173-4255-b699-a7e303deae32.jsonl`
- `/ll:capture-issue` - 2026-09-09T19:06:59 - `095aaa45-5f8e-445a-8993-2ec43b515f28.jsonl`
