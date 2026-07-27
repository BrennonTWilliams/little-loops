---
id: ENH-2845
type: ENH
priority: P3
status: open
discovered_date: 2026-07-26
discovered_by: manual-review
labels:
- audit-issue-conflicts
- skills
- permissions
relates_to:
- FEAT-2842
- BUG-2844
---

# ENH-2845: `/ll:audit-issue-conflicts` — non-persistent bash state, under-declared tools, contradictory auto mode

## Summary

Three correctness-adjacent defects in the skill's scaffolding, none of which
change what conflicts are *detected* but all of which make what happens
*afterward* unreliable: bash arrays used as cross-phase state that cannot
persist, `allowed-tools` that omits the interpreters the skill's own guards run
on, and an auto-mode specification that contradicts itself.

## Current Behavior

### 1. Bash arrays used as cross-phase state

The skill declares and mutates shell variables across separate phases:

- `ISSUE_FILES` — Phase 1 (`SKILL.md:105`, populated at `:113-141`)
- `MODIFIED_FILES` / `SKIPPED_INACTIVE_COUNT` — Phase 4b (`:309-310`), appended
  to at `:351`, `:373`, `:398`
- Consumed in Phase 5 (`:409-411`) and Phase 6 (`:429`)

Shell state does not persist between separate `Bash` tool invocations. Phase 4b's
appends and Phase 5's `for f in "${MODIFIED_FILES[@]}"; do git add "$f"; done`
run in different calls, so the loop iterates an empty array and **stages
nothing** — silently, with Phase 6 still printing "All changes staged".

The write-side guards have the same problem from the other direction: Phase 4b
specifies membership checks against "the ISSUE_FILES list **from Phase 1
context**" (`:318`, `:368`, `:384`) — i.e. the model's memory, not the variable
the surrounding bash implies. The code and the prose disagree about where the
state lives.

`test_phase5_stages_only_modified_files` asserts the instruction text is
present; it cannot catch that the mechanism does not work.

### 2. `allowed-tools` omits required interpreters

Declared (`SKILL.md:7-14`): `Read`, `Glob`, `Edit`, `Task`, `AskUserQuestion`,
`Bash(git:*)`, `Bash(ll-issues:*)`.

Actually invoked:

| Phase | Command | Covered? |
|---|---|---|
| 0 (`:78`) | `python3 -c` (EPIC validation) | **No** |
| 1 (`:116`) | `python3 -c` (status filter) | **No** |
| 1 (`:135`) | `awk` (frontmatter status parse) | **No** |
| 1 (`:131-141`) | shell `for` loop over globs | **No** |
| 4b (`:318`, `:368`, `:384`) | `awk` TOCTOU status re-check | **No** |

Under `--auto` / `LL_NON_INTERACTIVE` / `--dangerously-skip-permissions` — the
modes Phase 0 auto-enables — these are denied. The TOCTOU re-check that guards
every write is therefore the most likely thing to fail silently.

### 3. Auto mode contradicts itself

Phase 4 (`:293`): "Apply **all** recommendations without prompting."
Phase 6 (`:445`): "no action needed (low severity, **skipped in auto mode**)".

Low-severity conflicts have undefined behavior in the mode that runs
unattended.

## Expected Behavior

- Cross-phase state is tracked in one place with one mechanism. Either the skill
  keeps a run-scoped file (`${run_dir}/modified-files.txt`, appended by each
  write and read by Phase 5) or it drops the bash-array framing entirely and
  states plainly that the model tracks the list — but not both.
- `allowed-tools` covers every command the skill runs, or the skill stops
  shelling out for things `ll-issues` can already answer (`ll-issues list
  --json` already returns `status` and `path`, which removes most of the `awk`
  and `python3` usage outright — including all three TOCTOU re-checks).
- Auto mode has one stated policy for low-severity conflicts.

## Root Cause

The skill was written in a bash-pseudocode style that reads as executable but is
partly model-directed narration. Where the two are mixed inside one document,
neither the model nor a test can tell which lines are contracts and which are
illustration. `allowed-tools` was declared against the skill's *intent*
(`git`, `ll-issues`) rather than its literal command surface, and drifted as
guard logic was added in later revisions.

## Implementation Steps

1. Replace the `awk`/`python3` status parsing in Phases 1 and 4b with
   `ll-issues list --json` / `ll-issues show --json` — already permitted, and
   removes the need to widen `allowed-tools` for those call sites.
2. For anything still needing a shell interpreter, add explicit `allowed-tools`
   entries.
3. Pick one state mechanism for `MODIFIED_FILES` / `SKIPPED_INACTIVE_COUNT` /
   `ISSUE_FILES` and apply it consistently; if a run-scoped file, define the
   path and have Phase 5/6 read it.
4. Resolve the auto-mode contradiction — state whether low-severity
   recommendations are applied in `--auto`, and align Phase 4 and Phase 6.
5. Strengthen the existing skill tests: assert `allowed-tools` covers every
   `Bash(...)`-invoked binary appearing in fenced blocks. This is a generalizable
   check — consider a repo-wide lint over `skills/*/SKILL.md` rather than a
   single-skill test.
6. Re-check `ll-issues show --json` status casing before writing guard
   comparisons — it is display-cased (`"Completed"`), so comparisons must
   lowercase first.

## Scope Boundaries

**In scope**: the skill's scaffolding — cross-phase state tracking,
`allowed-tools` coverage, and the auto-mode low-severity contradiction.

**Out of scope**: what the audit writes. The `add_dependency` frontmatter-write
mechanism is FEAT-2842; the supersession status/edge defect is BUG-2844. Conflict
*detection* quality (Phase 2 batching, the Phase 2b fingerprint thresholds, the
prompt template) is untouched here.

## Acceptance Criteria

- [ ] Every command in a `SKILL.md` fenced block is covered by `allowed-tools`.
- [ ] Phase 5 stages exactly the files Phase 4b modified, verified by a test that
      does not merely assert the instruction text is present.
- [ ] Phase 4 and Phase 6 agree on low-severity handling under `--auto`.
- [ ] `python -m pytest scripts/tests/` passes.

## Impact

- **Users**: audit changes may be applied but never staged, contradicting the
  final report; write-side safety guards may not execute at all in the
  unattended mode where they matter most.
- **Risk**: Low-Medium. No data loss, but the skill reports success for work it
  did not do.
- **Effort**: Small-Medium.

## Related Key Documentation

| Document | Relevance |
|---|---|
| `skills/audit-issue-conflicts/SKILL.md` | All three defects |
| `scripts/tests/test_audit_issue_conflicts_skill.py` | Existing assertion style to extend |
| `.claude/CLAUDE.md` § Development Preferences | Skill-over-agent conventions |

## Context

Found while auditing `/ll:audit-issue-conflicts` for reliable frontmatter
writing.

---

## Status

open
