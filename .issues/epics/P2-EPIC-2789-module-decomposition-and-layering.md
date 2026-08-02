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
