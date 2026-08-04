---
id: EPIC-2789
title: Module Decomposition and Layering
type: EPIC
priority: P2
status: open
captured_at: '2026-07-25T02:35:31Z'
discovered_date: 2026-07-25
discovered_by: create-epics-from-unparented
relates_to:
- ENH-2773
- ENH-2774
- ENH-2775
- ENH-2776
- ENH-2890
- ENH-2891
---

# EPIC-2789: Module Decomposition and Layering

## Summary

Group of 5 related issues concerning splitting oversized modules along concern
boundaries and correcting layering inversions between the `fsm` and `cli`
packages. Includes: ENH-2772 (Split session_store.py god module into a
subpackage), ENH-2773 (Fix fsm→cli layering inversion), ENH-2774 (Split
fsm/validation.py by rule family), ENH-2775 (Split history_reader.py and
fsm/executor.py along concern boundaries), ENH-2776 (Dissolve
cli/loop/_helpers.py grab-bag into named modules).

## Children

- **ENH-2772** — Split session_store.py god module into a subpackage
- **ENH-2773** — Fix fsm→cli layering inversion (move resolve_loop_path out of cli/loop/_helpers)
- **ENH-2774** — Split fsm/validation.py by rule family
- **ENH-2775** — Split history_reader.py and fsm/executor.py along concern boundaries
- **ENH-2776** — Dissolve cli/loop/_helpers.py grab-bag into named modules

## Related Key Documentation

- `docs/ARCHITECTURE.md` — this EPIC is exactly the module-placement and
  fsm/cli layering-boundary question the architecture doc describes.
- `docs/reference/API.md` — documents `session_store`, `fsm/validation`,
  `fsm/executor`, and `history_reader`, the specific modules being split.

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): ENH-2784 declares `parent: EPIC-2789`, but this epic's Summary/Children list above does not enumerate it — ENH-2784 covers extracting coercion helpers in `issue_parser.py`, which is a distinct in-file dedup concern rather than the module-decomposition/layering-inversion theme this epic tracks. Confirm whether ENH-2784 genuinely belongs here (and add it to Children if so) or re-parent it to a more fitting issue.


## Session Log
- `/ll:audit-issue-conflicts` - 2026-08-04T20:31:44 - `ec47aff0-f647-498d-ad44-7606e8c8054f.jsonl`
