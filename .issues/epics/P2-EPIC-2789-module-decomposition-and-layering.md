---
id: EPIC-2789
title: Module Decomposition and Layering
type: EPIC
priority: P2
status: open
captured_at: '2026-07-25T02:35:31Z'
discovered_date: 2026-07-25
discovered_by: create-epics-from-unparented
verify_verdict: NON_VALID
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
fsm/validation.py by rule family), ENH-2775 (Split history_reader.py into a
subpackage — the fsm/executor.py half was rescoped into ENH-3359, deferred),
ENH-2776 (Dissolve cli/loop/_helpers.py grab-bag into named modules).

## Children

- ~~**ENH-2772** — Split session_store.py god module into a subpackage~~ **done**
- ~~**ENH-2773** — Fix fsm→cli layering inversion (move resolve_loop_path out of cli/loop/_helpers)~~ **done**
- ~~**ENH-2774** — Split fsm/validation.py by rule family~~ **done**
- ~~**ENH-2775** — Split history_reader.py into a subpackage (rescoped 2026-08-29; executor half moved to ENH-3359)~~ **done**
- ~~**ENH-2776** — Dissolve cli/loop/_helpers.py grab-bag into named modules~~ **done**
- ~~**ENH-2784** — Extract coercion helpers in issue_parser.py~~ **done**
- ~~**ENH-2890** — Split session_store.py production code into a subpackage~~ **done**
- ~~**ENH-2891** — Split test_session_store.py into per-module test files~~ **done**
- **ENH-3359** — Extract `_prepatch_*`/`_tamper_guard_*` collaborators from fsm/executor.py (deferred; split out of ENH-2775)

## Related Key Documentation

- `docs/ARCHITECTURE.md` — this EPIC is exactly the module-placement and
  fsm/cli layering-boundary question the architecture doc describes.
- `docs/reference/API.md` — documents `session_store`, `fsm/validation`,
  `fsm/executor`, and `history_reader`, the specific modules being split.

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): ENH-2784 declares `parent: EPIC-2789`, but this epic's Summary/Children list above does not enumerate it — ENH-2784 covers extracting coercion helpers in `issue_parser.py`, which is a distinct in-file dedup concern rather than the module-decomposition/layering-inversion theme this epic tracks. Confirm whether ENH-2784 genuinely belongs here (and add it to Children if so) or re-parent it to a more fitting issue.


## Session Log
- `/ll:audit-issue-conflicts` - 2026-09-08T02:29:09 - `68b61242-b6be-4235-b2f6-614f534d7caf.jsonl`
- `/ll:verify-issues` - 2026-09-03T17:42:02 - `b50c8ee7-ec9c-45b3-9179-235a02273d8c.jsonl`
- `/ll:audit-issue-conflicts` - 2026-08-21T19:06:53 - `8c9f6596-f570-42d1-a2a2-c4e750b706f8.jsonl`
- `/ll:verify-issues` - 2026-08-16T16:40:24 - `688cfc38-322a-447f-94a0-315f2c2aee33.jsonl`
- `/ll:verify-issues` - 2026-08-13T03:04:15 - `10ce6a50-a4a8-4b29-a122-e05a925e303c.jsonl`
- `/ll:audit-issue-conflicts` - 2026-08-10T18:52:50 - `ffa08fd4-dce7-4108-91f7-6bb57e5df4c8.jsonl`
- `/ll:audit-issue-conflicts` - 2026-08-05T00:25:07 - `2f3f7bc8-367e-4fba-936b-eaf8049da3c4.jsonl`
- `/ll:audit-issue-conflicts` - 2026-08-04T20:31:44 - `ec47aff0-f647-498d-ad44-7606e8c8054f.jsonl`

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): This epic's ENH-2776 ("Dissolve `cli/loop/_helpers.py` grab-bag into named modules") restructures `scripts/little_loops/cli/loop/`. EPIC-2938 lands new subcommands (ENH-2943, FEAT-2948, ENH-2949) into the same directory. Sequence ENH-2776 before EPIC-2938's `cli/loop/*` additions, or have whichever lands second rebase onto the other's resulting module layout, to avoid divergent restructurings of the same package.

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): This epic's deferred `ENH-3359` ("Extract `_prepatch_*`/`_tamper_guard_*` collaborators from fsm/executor.py") must target the post-EPIC-2856 shape of `fsm/executor.py` — EPIC-2856's `ENH-2933`/`ENH-2934` already landed tamper-guard core and FSM-adapter code (the `_tamper_guard_*` collaborators) in that same file. When ENH-3359 resumes, sequence/verify it against the landed tamper-guard adapter rather than the pre-tamper-guard shape assumed at ENH-2775's original split.

## Verification Notes (2026-08-12)

_Added by `/ll:verify-issues`._ Verdict: **NON_VALID (NEEDS_UPDATE)**. The frontmatter `blocked_by: [EPIC-2616, EPIC-2791]` was stale — both epics are now `status: done`, so this epic is unblocked. The `blocked_by` field has been removed.

- 2026-08-16: ENH-2772/2773/2774 are now done but the Children list above didn't reflect that — updated below. ENH-2775/2776 are still correctly open. Also ENH-2784 (`parent: EPIC-2789`, status open) was missing from the Children list entirely — added it below. Verdict: NEEDS_UPDATE.
- 2026-09-03: ENH-2775, ENH-2776, and ENH-2784 are now `done` but still shown open/unmarked. ENH-2890 and ENH-2891 (both `done`, `parent: EPIC-2789`) were missing from Children entirely — added. ENH-3359 confirmed still `deferred`. 8/9 children now resolved.
