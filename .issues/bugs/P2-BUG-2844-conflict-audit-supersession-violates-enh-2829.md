---
id: BUG-2844
type: BUG
priority: P2
status: open
discovered_date: 2026-07-26
discovered_by: manual-review
labels:
- audit-issue-conflicts
- issue-status
- supersession
relates_to:
- FEAT-2842
- ENH-2845
---

# BUG-2844: `/ll:audit-issue-conflicts` supersession writes `status: done` and never records `supersedes:`

## Summary

The `merge/deprecate` branch closes a superseded issue by hand-editing its
frontmatter to `status: done` and appending a `## Resolution` section reading
`**Status**: Closed - Superseded`. Per ENH-2829 a superseded issue must be
`cancelled`, and the supersession relationship is a graph edge — `supersedes:
[ID]` declared on the **replacement** issue. The skill writes neither. Merges
therefore lose the supersession edge entirely and inflate the completed-work
count with work that was never done.

## Current Behavior

`skills/audit-issue-conflicts/SKILL.md` Phase 4b, `merge/deprecate` branch:

- **Step 4** appends to the closed issue:

  ```markdown
  ## Resolution

  - **Status**: Closed - Superseded
  - **Completed**: YYYY-MM-DD
  - **Reason**: Superseded by [KEPT-ID] via conflict resolution audit
  ```

- **Step 5**: "Update the closed issue's frontmatter `status: done` using the
  Edit tool."

Three distinct defects:

1. **Wrong terminal status.** `.claude/CLAUDE.md` § Issue File Format
   (ENH-2829): "there is no `superseded` status value. A superseded issue is
   marked `cancelled` (optionally with `cancelled_reason`)". Writing `done`
   means every downstream consumer of completion — `ll-history`,
   `epic-progress`, release notes — counts superseded duplicates as shipped
   work.
2. **The supersession edge is never written.** ENH-2829: "declare `supersedes:
   [ID, ...]` on the replacement issue, and `ll-issues show` derives the reverse
   `Superseded by` row via `issue_parser.superseded_by()`". The skill records the
   relationship only as English prose inside `## Resolution`, so
   `show.py:254`/`:593`'s `supersedes` handling finds nothing and the
   `Superseded by` row never appears on the closed issue.
3. **Raw `Edit` instead of `ll-issues set-status`.** The status write bypasses
   the canonical writer, so nothing normalizes the value or stamps closure
   context. `Bash(ll-issues:*)` is already in the skill's `allowed-tools` — the
   CLI was available and simply not used.

The prose `**Status**: Closed - Superseded` also plants a non-canonical status
synonym in the issue body, where a body-scanning reader can pick it up.

## Expected Behavior

For an approved `merge/deprecate`:

```bash
ll-issues set-status <CLOSED-ID> cancelled --reason superseded
ll-issues link <KEPT-ID> --supersedes <CLOSED-ID>     # FEAT-2842
```

- Closed issue ends at `status: cancelled`, not `done`.
- The replacement carries `supersedes: [CLOSED-ID]` in frontmatter, so
  `ll-issues show <CLOSED-ID>` derives the `Superseded by` row.
- The `## Resolution` section stays as human narrative but drops the
  `**Status**: Closed - Superseded` line, which duplicates frontmatter in a
  non-canonical vocabulary.

## Root Cause

The skill's merge branch was authored against the older "close as done with a
Resolution note" convention and was not revisited when ENH-2829 made
supersession a derived graph edge with `cancelled` as the terminal status.
Nothing tests the skill's status-write instruction against the documented
status vocabulary.

## Implementation Steps

1. Rewrite `SKILL.md` Phase 4b `merge/deprecate` steps 4-5 to use
   `ll-issues set-status ... cancelled` and to write `supersedes:` on the kept
   issue.
2. Remove the `**Status**: Closed - Superseded` line from the `## Resolution`
   template; keep `**Reason**` and `**Proposed change**`.
3. Verify whether `ll-issues set-status` accepts a `cancelled_reason` — the
   `--by`/`--reason` flags are documented for the `deferred` transition
   (ENH-2664); if `cancelled` has no equivalent, either extend it or write
   `cancelled_reason:` via the FEAT-2842 writer.
4. Add a test asserting `SKILL.md` contains no instruction to write
   `status: done` for a superseded issue, and does instruct a `supersedes:`
   write — matching the existing assertion style in
   `scripts/tests/test_audit_issue_conflicts_skill.py`.
5. Sweep for already-mis-closed issues: any issue with `status: done` whose body
   contains `Closed - Superseded` should be corrected to `cancelled` with the
   edge backfilled.
6. Check the sibling skills (`/ll:tradeoff-review-issues`, `/ll:ready-issue`)
   for the same stale close-as-done-superseded pattern.

## Acceptance Criteria

- [ ] An approved merge leaves the closed issue at `status: cancelled`.
- [ ] The kept issue carries `supersedes: [CLOSED-ID]` and `ll-issues show
      <CLOSED-ID>` renders a `Superseded by` row.
- [ ] No `Edit`-the-frontmatter status instruction remains in the skill.
- [ ] A test in `scripts/tests/test_audit_issue_conflicts_skill.py` pins both.
- [ ] Existing mis-closed issues found by step 5 are corrected (or the sweep
      reports zero).

## Impact

- **Users**: completed-work metrics and release notes silently include work that
  was never implemented. The supersession trail — the thing that lets a reader
  find where a closed issue's scope went — is lost to prose.
- **Risk**: Medium. Data-integrity defect in a write path that runs in `--auto`
  mode across the whole backlog.
- **Effort**: Small. Mostly skill-text correction plus a backfill sweep.

## Steps to Reproduce

1. Run `/ll:audit-issue-conflicts --auto` on a backlog containing a
   merge-recommended conflict pair.
2. Inspect the closed issue: `status: done`, body contains
   `**Status**: Closed - Superseded`.
3. Inspect the kept issue: no `supersedes:` key.
4. `ll-issues show <CLOSED-ID>` — no `Superseded by` row.

## Related Key Documentation

| Document | Relevance |
|---|---|
| `.claude/CLAUDE.md` § Issue File Format | ENH-2829 supersession policy — `cancelled` + `supersedes:` edge |
| `skills/audit-issue-conflicts/SKILL.md:315-364` | The `merge/deprecate` branch to correct |
| `scripts/little_loops/cli/issues/show.py:254,451,593` | Derived `supersedes` / `Superseded by` rendering |
| `scripts/little_loops/cli/issues/set_status.py` | The canonical status writer that should be used |

## Context

Found while auditing `/ll:audit-issue-conflicts` for reliable frontmatter
writing.

---

## Status

open
