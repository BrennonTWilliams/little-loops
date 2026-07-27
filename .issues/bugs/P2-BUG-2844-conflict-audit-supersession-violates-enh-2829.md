---
id: BUG-2844
type: BUG
priority: P2
status: done
discovered_date: 2026-07-26
discovered_by: manual-review
labels:
- audit-issue-conflicts
- issue-status
- supersession
relates_to:
- FEAT-2842
- ENH-2845
confidence_score: 94
outcome_confidence: 68
score_complexity: 15
score_test_coverage: 21
score_ambiguity: 12
score_change_surface: 20
completed_at: '2026-07-27T01:13:15Z'
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

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **`cancelled_reason` does not exist as a dedicated field.** `scripts/little_loops/cli/issues/set_status.py:79-82` writes a `cancelled` transition's `--reason` value into the shared `closed_reason` key — the same key used for `done` (lines 74-78). There is no separate `--cancelled-reason` flag or `cancelled_reason` frontmatter key, unlike `deferred`'s dedicated `deferred_by`/`deferred_reason`/`deferred_date` triple (lines 83-88). This answers Implementation Step 3: use `ll-issues set-status <ID> cancelled --reason superseded` and expect `closed_reason: superseded` in frontmatter, not a `cancelled_reason` key. `superseded` is not currently in `_CLOSED_REASON_CODES` (`set_status.py:23`, currently `frozenset({"already_fixed"})`) — it will need to be added there or the `--reason` validation at lines 108-123 will reject it.
- **`ll-issues link --supersedes` does not exist yet.** No `link` subcommand exists under `scripts/little_loops/cli/issues/`. The only `--supersedes` flag in the codebase is `decisions.py:135-138`, scoped to `decisions add --type=rule` entries — unrelated to issue frontmatter. `show.py:254,451,593` only reads/displays an issue's `supersedes:` field; nothing writes it. This confirms **FEAT-2842** (`.issues/features/P2-FEAT-2842-ll-issues-link-dependency-edge-writer.md`, already in `relates_to:`) is the correct prerequisite/companion for the writer half of this fix — BUG-2844's `Expected Behavior` example command (`ll-issues link <KEPT-ID> --supersedes <CLOSED-ID>`) does not exist today and depends on FEAT-2842 landing first, or must be done via a direct `Edit`/`update_frontmatter` call to `supersedes:` in the interim.
- **Exact current text to replace** (`skills/audit-issue-conflicts/SKILL.md:332-346`, Phase 4b `merge/deprecate`):
  - Step 4 (lines 332-344) appends a `## Resolution` section with `- **Status**: Closed - Superseded`, `- **Completed**: YYYY-MM-DD`, `- **Reason**: Superseded by [KEPT-ID] via conflict resolution audit`, `- **Proposed change**: [proposed_change from conflict record]` (idempotency guard at line 332 skips if `## Resolution` already present — preserve this guard).
  - Step 5 (line 346): `Update the closed issue's frontmatter status: done using the Edit tool.`
- **Test assertion style** (`scripts/tests/test_audit_issue_conflicts_skill.py`): existing tests slice `SKILL.md` into phase-scoped substrings (e.g. `phase4b_text`) and assert plain substring containment/absence, e.g. lines 67-69 and 100-102 (`assert "..." in phase4b_text`, `assert "..." not in phase4b_text`). Implementation Step 4's new test should follow this pattern: assert `"Closed - Superseded"` and a bare `status: done`-for-superseded instruction are absent from `phase4b_text`, and that a `cancelled`/`supersedes:` instruction is present.
- **Sweep result (Implementation Step 5): zero mis-closed issues found.** A repo-wide grep for `status: done` combined with `Closed - Superseded` in the body matched only this issue file itself (BUG-2844, describing the bug pattern in prose, `status: open`) — no other issue file has both. The backfill sweep acceptance criterion is already satisfied trivially; no corrective edits are needed.

## Integration Map

### Files to Modify

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/issues/__init__.py:774-792` — the `--reason` argparse `choices=[...]` list on the `set-status` subparser is a **separate, harder validation gate** from `_CLOSED_REASON_CODES`. It hardcodes the full accepted list and does not include `"superseded"`. If not updated in lockstep with `set_status.py:23`, `--reason superseded` is rejected by argparse with `SystemExit(2)` before `cmd_set_status()` ever runs, making the `_CLOSED_REASON_CODES` frozenset check unreachable. Both lists duplicate the same vocabulary with no shared constant.
- `docs/reference/CLI.md:1684` — the `--reason <code>` table row states closure codes are currently only `already_fixed`; needs a `superseded` mention.
- `docs/reference/CLI.md:1694` — the only closure-code usage example (`ll-issues set-status BUG-731 done --reason already_fixed`); add a parallel `cancelled --reason superseded` example matching existing doc conventions.

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/frontmatter.py:243` (`update_frontmatter(content, updates)`) — the existing generic frontmatter-merge helper already used by `set_status.py` itself (`:127`, `:204`). This is the established interim direct-write mechanism for `supersedes:` on the kept issue since `ll-issues link --supersedes` does not exist (see below).
- **FEAT-2842 scope gap**: `.issues/features/P2-FEAT-2842-ll-issues-link-dependency-edge-writer.md` (status: open) only scopes `--blocked-by`, `--depends-on`, `--relates-to` in its own Summary — it does **not** currently include a `--supersedes` flag. Landing FEAT-2842 as currently scoped would NOT unblock `Expected Behavior`'s `ll-issues link <KEPT-ID> --supersedes <CLOSED-ID>` example command. Either FEAT-2842 must be re-scoped to add `--supersedes`, or this issue proceeds with the interim `update_frontmatter()`/raw Edit path.
- `scripts/little_loops/issue_parser.py:1432` (`superseded_by()`) — read-only reverse-edge deriver for `show.py` display; no write coupling, confirmed unaffected by this fix.
- `.ll/decisions.d/c11b55bb-dc43-435f-b903-a6f7aceb9b5f.json` (ENH-2749 decision) — documents the precedent two-location pattern (argparse `choices` + `_CLOSED_REASON_CODES` frozenset) used when `already_fixed` was added; a new decision fragment following this pattern would be consistent with project convention when `superseded` is added (not test-enforced).

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_set_status_cli.py` — `test_set_status_done_stamps_closed_reason` (line 430-465) is parametrized over `["done", "cancelled"]` and is the closest existing pattern to copy for a new assertion: invoke `set-status BUG-001 cancelled --reason superseded` and assert `parse_frontmatter(...).get("closed_reason") == "superseded"`. `test_set_status_invalid_reason_rejected` (line 525-554) and `test_set_status_deferral_reason_rejected_on_done` (line 556+) confirm the `choices=[...]`/frozenset validation shape a new test should follow.
- `scripts/tests/test_audit_issue_conflicts_skill.py` — no existing test currently pins the literal `"Closed - Superseded"` or `"status: done"` strings in Phase 4b (grep confirmed), so nothing in the existing suite breaks from removing them, but Implementation Step 4's new test is a pure coverage gap, not a regression fix. Follow the existing `_phase(start_header, end_header)` slicing helper (used in `TestAuditIssueConflictsEpicScoping`) or the `phase4b_text = content[phase4b_start:phase5_start]` pattern (lines 84-102) to scope assertions tightly to Phase 4b only — a bare `"status: done" not in phase4b_text` assertion is safe within that slice but would be too broad unscoped (collides with legitimate `status: done` mentions elsewhere in the file).
- `scripts/tests/test_show.py` (`test_superseded_by_derived_from_reverse_edge`, line ~391-405) — already covers the **read/display** side of `supersedes:`/`superseded_by()`; not a gap for this issue, but the literal-string issue-file-write pattern it uses (`(enh_dir / "P3-ENH-5111-new.md").write_text("---\nstatus: open\nsupersedes:\n- ENH-5110\n---\n...")`) is the closest existing analog for asserting the kept issue's frontmatter round-trips correctly after the skill's raw `supersedes:` Edit — no test currently exercises that write path directly (a new-test gap belonging in `test_audit_issue_conflicts_skill.py`, not `test_show.py`).

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

7. Update `scripts/little_loops/cli/issues/__init__.py:774-792` — add `"superseded"` to the `--reason` argparse `choices=[...]` list on the `set-status` subparser (a separate gate from `_CLOSED_REASON_CODES`; missing this makes the frozenset update unreachable — argparse rejects first with `SystemExit(2)`).
8. Update `docs/reference/CLI.md:1684` and `:1694` — document `superseded` as a valid closure reason code and add a `cancelled --reason superseded` usage example.
9. Confirm FEAT-2842's scope before relying on `ll-issues link --supersedes` — as currently scoped it does not include a `--supersedes` flag; use `update_frontmatter()` (`scripts/little_loops/frontmatter.py:243`) via a direct Edit as the interim/actual write path for `supersedes:` on the kept issue if FEAT-2842 isn't re-scoped first.
10. Add a `cancelled`+`superseded` parametrize case (or dedicated test) to `test_set_status_cli.py` following `test_set_status_done_stamps_closed_reason`'s pattern.

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

## Session Log
- `ll-auto` - 2026-07-27T01:13:15 - `a46aa22c-4f7a-46b6-9f1b-e4ed2c3fd842.jsonl`
- `/ll:wire-issue` - 2026-07-27T00:59:30 - `99b50f04-217b-4cc2-bd4b-f19c6151201e.jsonl`
- `/ll:refine-issue` - 2026-07-27T00:52:45 - `3fe2fd3d-c1bb-47f8-a81d-47b5216c7e25.jsonl`
- `/ll:confidence-check` - 2026-07-26T00:00:00 - `3cf18979-1478-4dda-a8c3-1916d606b997.jsonl`

---

## Status

open
