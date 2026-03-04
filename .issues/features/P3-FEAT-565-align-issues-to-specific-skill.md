---
discovered_commit: ce1f6277bf5cf527716a37cb7d0bb8a3bc22a638
discovered_branch: main
discovered_date: 2026-03-04T17:00:33Z
discovered_by: capture-issue
---

# FEAT-565: Add skill-based alignment option to `align-issues`

## Summary

Extend `/ll:align-issues` to support aligning issues against a specific skill (e.g., `/ll:align-issues skill capture-issue`). Currently the command aligns issues against key documents in configured categories. This feature adds a parallel path that uses a skill's `SKILL.md` as the alignment reference, so users can check whether an issue is well-scoped for a particular skill to implement.

## Motivation

Users sometimes want to verify that an issue is correctly described relative to what a specific skill is capable of — for example, checking that a `capture-issue` issue accurately references the skill's input handling, duplicate detection logic, or template behavior. Key documents cover architecture and specs, but skills represent executable capability; aligning issues to skills gives a tighter feedback loop for issue-to-implementation readiness.

## Use Case

A user has an issue that will be implemented via `/ll:manage-issue` using a specific skill. Before scheduling it, they run:

```
/ll:align-issues skill capture-issue P3-FEAT-565-align-issues-to-specific-skill.md
```

The command loads `skills/capture-issue/SKILL.md`, extracts the skill's purpose, phases, inputs, and outputs, then evaluates whether the issue accurately describes work the skill can perform.

## Expected Behavior

- **New invocation form**: `/ll:align-issues skill <skill-name> [issue-id-or-glob]`
- The command resolves `skills/<skill-name>/SKILL.md` (or `commands/<skill-name>.md` as a fallback)
- Alignment checks evaluate:
  - Does the issue describe work within the skill's documented scope?
  - Are inputs/outputs referenced in the issue consistent with the skill's interface?
  - Are any issue steps or acceptance criteria contradicted by the skill's documented behavior?
- Output follows the same format as document-based alignment (aligned / partially aligned / misaligned + rationale)

## Implementation Steps

1. Parse the new `skill` subcommand in the align-issues command entrypoint (`commands/align-issues.md`)
2. Resolve skill path: check `skills/<name>/SKILL.md`, fallback to `commands/<name>.md`
3. Extract relevant sections from `SKILL.md` (summary, phases, inputs, outputs, examples)
4. Reuse or adapt existing document-based alignment scoring logic with skill content as the reference
5. Emit alignment report in the existing format

## API / Interface

```
/ll:align-issues skill <skill-name>                   # align all active issues
/ll:align-issues skill <skill-name> <issue-id>        # align specific issue
```

The `skill` subcommand is mutually exclusive with category-based alignment (e.g., `architecture`, `product`).

## Acceptance Criteria

- [ ] `skill <name>` subcommand is documented in the command's help/examples
- [ ] Skill file is resolved correctly; error surfaced if skill does not exist
- [ ] Alignment report matches format of existing document-based alignment output
- [ ] Works for both individual issues and batch (all active issues)
- [ ] Fallback to `commands/<name>.md` when `skills/<name>/SKILL.md` is absent

## Session Log
- `/ll:capture-issue` - 2026-03-04T17:00:33Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/`
