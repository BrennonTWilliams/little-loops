---
id: BUG-2806
title: "Issue ID resolver matches filename substring before frontmatter id (EPIC-2456 resolved to ENH-2719)"
type: BUG
priority: P2
status: open
captured_at: '2026-07-25T18:20:00Z'
discovered_date: 2026-07-25
discovered_by: capture-issue
labels:
- issues
- cli
---

# BUG-2806: Issue ID resolver matches filename substring before frontmatter id

## Summary

`ll-issues set-status EPIC-2456 done` and `ll-issues path EPIC-2456` both
resolved to `.issues/enhancements/P2-ENH-2719-epic-2456-realized-savings-verification-and-closure-gate.md`
(frontmatter `id: ENH-2719`) instead of
`.issues/epics/P2-EPIC-2456-token-cost-reduction.md` (frontmatter
`id: EPIC-2456`). The ENH's filename contains the lowercase substring
`epic-2456`, and the resolver apparently matches on filename substring
before (or instead of) the frontmatter `id:` field.

## Reproduction

Observed 2026-07-25 with both files present:

```
$ ll-issues set-status EPIC-2456 done
EPIC-2456: done → done          # actually re-stamped ENH-2719 (already done)
$ ll-issues path EPIC-2456
.issues/enhancements/P2-ENH-2719-epic-2456-realized-savings-verification-and-closure-gate.md
```

The epic file itself still had `status: open` afterward and had to be edited
manually.

## Impact

Silent wrong-file writes: any issue whose slug embeds another issue's ID
(a common pattern for closure-gate / follow-up issues named after their
parent) can shadow that ID for every `ll-issues` ID-based operation —
`set-status`, `path`, `show`, likely others sharing the resolver. Automation
(autodev's `mark_deferred`/`set-status` states) would corrupt the wrong
issue's status without any error.

## Expected Behavior

ID resolution must match the frontmatter `id:` field exactly (or the
filename's structured `[TYPE]-[NNN]` segment with type equality), never a
bare substring of the slug. `EPIC-2456` must resolve only to the file whose
frontmatter says `id: EPIC-2456`; if no such file exists, error — not
fall back to a slug substring match.

## Root Cause (suspected)

The shared file-lookup helper in `scripts/little_loops/` issue tooling
(used by `set-status`/`path`/`show`) globs for `*{issue_id.lower()}*` in
filenames rather than parsing frontmatter `id:`. Not yet confirmed —
locate the resolver and confirm before fixing.

## Session Log
- `/ll:capture-issue` - 2026-07-25T18:20:00Z

---

## Status
- Status: open
