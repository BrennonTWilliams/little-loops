---
id: ENH-2242
title: Auto-invoke explore-api at learning test gate
type: ENH
priority: P3
status: open
captured_at: "2026-06-20T05:38:22Z"
discovered_date: "2026-06-20"
discovered_by: capture-issue
---

# ENH-2242: Auto-invoke explore-api at learning test gate

## Summary

When `ready-issue` or `confidence-check` encounters a `missing` or `refuted` learning test target, they currently block and instruct the user to manually run `/ll:explore-api "<target>"`. This is unnecessary friction — both skills have access to the `Skill` tool and can invoke `explore-api` themselves, then re-check the gate.

## Motivation

Users must manually break out of the gate flow to run `/ll:explore-api` when a target is unproven or refuted, then re-run the original skill. Auto-provisioning removes that round-trip: the skill resolves the assumption inline, and the gate only surfaces a hard block when re-exploration still can't prove the target.

## Implementation Steps

### 1. `commands/ready-issue.md` — Learning Test Gate (lines 182–183)

Replace the `refuted` and `missing` bullet text. `stale` (line 181) is a WARN that doesn't block — leave it unchanged.

**Current:**
```
- `status: refuted` → **Set verdict to NOT_READY**: `❌ Refuted assumption: "<target>" — see registry for refutation details`
- Record not found (None returned) → **Set verdict to NOT_READY**: `❌ Unproven assumption: "<target>" — run /ll:explore-api "<target>"`
```

**New:**
```
- `status: refuted` → **Auto-invoke** `Skill("explore-api", "<target>")` to re-explore the assumption, then re-run `ll-learning-tests check "<target>"`. If still `refuted`: `❌ Refuted assumption: "<target>" — see registry for refutation details` + **Set verdict to NOT_READY**. If now `proven` or `stale`: apply that status and continue.
- Record not found (None returned) → **Auto-invoke** `Skill("explore-api", "<target>")` to create the proof record, then re-run `ll-learning-tests check "<target>"` and apply the refreshed status. If still `missing` after exploration: `❌ Unproven assumption: "<target>"` + **Set verdict to NOT_READY**.
```

### 2. `skills/confidence-check/rubric.md` — Phase 1.5 (after line 143)

After the exit-semantics paragraph (the line ending `"…loses the distinction needed for differential scoring."`), insert a new **Auto-provision** step before the "When `LT_ROWS` is non-empty" paragraph:

```markdown
**Auto-provision**: If any target's status is `missing` or `refuted` after the script above, invoke `Skill("explore-api", "<target>")` for each such target before proceeding. After each invocation completes, re-run `ll-learning-tests check "<target>"` and update that target's row in `LT_ROWS` with the refreshed status and notes. Re-evaluate `LT_STOP`: reset to `false`, then set to `true` only if any target is still `missing` or `refuted` after provisioning.
```

`SKILL.md` line 275 ("Learning Test Hard Override: if Phase 1.5 found any `missing` or `refuted` target…") remains accurate — it triggers only if the re-check after auto-provision still fails.

## Out of Scope

- `skills/scope-epic/SKILL.md` and `skills/create-loop/loop-types.md` also reference "run /ll:explore-api" in learning-test contexts, but those are proposal/display strings, not blocking gate logic. Leave for a follow-up.
- The `stale` WARN path in both files is unchanged (non-blocking, existing text is informational).

## Acceptance Criteria

1. Create a test issue with `learning_tests_required: ["some-target"]` and no existing `.ll/learning-tests/` record.
2. Run `/ll:ready-issue <issue-id>` — auto-invokes `explore-api "some-target"` without prompting, then re-checks and resolves the gate.
3. Run `/ll:confidence-check <issue-id>` — same auto-provision occurs in Phase 1.5 before the scoring table.
4. For refuted: manually create a refuted record, re-run both skills — re-explores and either resolves or surfaces NOT_READY cleanly.
5. Confirm stale targets still produce a WARN row without triggering auto-invoke.

## Session Log
- `/ll:capture-issue` - 2026-06-20T05:38:22Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fd8f142e-9c8f-4d85-8bfd-0333f0b18482.jsonl`
