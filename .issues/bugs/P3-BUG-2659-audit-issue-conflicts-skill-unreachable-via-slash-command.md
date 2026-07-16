---
discovered_date: 2026-07-16 00:00:00+00:00
discovered_by: user-report
confidence_score: 100
outcome_confidence: 100
status: done
completed_at: '2026-07-16T18:34:55Z'
---

# BUG-2659: `audit-issue-conflicts` skill unreachable via `/ll:` slash command (disable-model-invocation flag blocks user invocation)

## Summary

Typing `/ll:audit-issue-conflicts` in an interactive Claude Code session fails
immediately with `Skill ll:audit-issue-conflicts cannot be used with Skill tool
due to disable-model-invocation`. The skill's frontmatter sets
`disable-model-invocation: true`, which the Skill tool rejects for *all* calls
regardless of origin — including user-typed slash commands. The skill has no
underlying CLI wrapper, so there is no alternate entry point; the frontmatter
flag was the only thing keeping it unreachable.

## Location

- **File**: `skills/audit-issue-conflicts/SKILL.md`
- **Line(s)**: 4
- **Anchor**: YAML frontmatter `disable-model-invocation:` field
- **Code** (before fix):
```yaml
disable-model-invocation: true
```

## Current Behavior

User runs `/ll:audit-issue-conflicts` in a Claude Code session. The slash
command dispatcher routes through the Skill tool; the Skill tool rejects the
call with:

```
Error: Skill ll:audit-issue-conflicts cannot be used with Skill tool due to disable-model-invocation
```

No fallback fires. The skill body is the only implementation — there is no
Python module, CLI command, or plugin entry point that wraps it (verified by
grepping `scripts/little_loops/**/*.py` for `audit_issue_conflicts` /
`audit-issue-conflicts`, and confirming the skill's `allowed-tools` block
contains only `Read`, `Glob`, `Edit`, `Task`, `AskUserQuestion`, `Bash(git:*)`,
`Bash(ll-issues:*)`). The skill is fully prompt-driven.

The wiring for this skill was tracked by **FEAT-1029** ("audit-issue-conflicts
— Wiring, Docs, and Tests", status `done`, completed 2026-05-10); that issue
covered registry and test wiring, not the dispatch-flag interaction.

## Expected Behavior

`/ll:audit-issue-conflicts` (with or without args: `--auto`, `--dry-run`,
`--cross-theme`, or an optional EPIC scope) enters the skill body and runs
Phases 0–6 as documented. The slash command dispatcher should reach user-
invoked skills even when they set `disable-model-invocation: true` — that flag
is meant to gate *Claude-originated* invocations from inside FSM loops or
other skill compositions, not user-typed slash commands.

## Steps to Reproduce

1. Open an interactive Claude Code session in the little-loops project.
2. Type `/ll:audit-issue-conflicts` (with no flags, or with any combination of `--auto`, `--dry-run`, `--cross-theme`, or an optional EPIC id positional).
3. Observe: the session immediately surfaces `Error: Skill ll:audit-issue-conflicts cannot be used with Skill tool due to disable-model-invocation` and the skill body never loads.
4. Inspect `skills/audit-issue-conflicts/SKILL.md` line 4 — confirm `disable-model-invocation: true`.

Expected: the slash command enters Phase 0 (flag parsing) and proceeds into Phase 1 (loading issues). Actual: dispatch is rejected at the Skill-tool gate.

## Root Cause

- **File**: `skills/audit-issue-conflicts/SKILL.md`
- **Line(s)**: 4 (frontmatter)
- **Anchor**: `disable-model-invocation: true`
- **Cause**: `disable-model-invocation: true` instructs the Skill tool to
  refuse every invocation regardless of caller. The slash command dispatcher
  goes through the same Skill-tool surface, so user-typed `/ll:audit-issue-conflicts`
  fails identically to a model-originated call. There is no alternate dispatch
  path.

## Proposed Solution

Set `disable-model-invocation: false` on the skill's frontmatter so the Skill
tool will accept user-typed slash commands. The trade-off is that the skill
becomes invocable from inside other skills / FSM loops; given the skill's
purpose (interactive conflict audit with optional destructive file edits
backed by `AskUserQuestion`), that risk is low, and the current `true` value
makes the skill entirely unreachable.

```diff
- disable-model-invocation: true
+ disable-model-invocation: false
```

If a stricter guarantee is later desired, the long-term fix is in the harness
slash-command dispatcher: distinguish user-typed vs Claude-originated
invocations and gate `disable-model-invocation` only on the latter. That is
out of scope for this issue.

## Implementation Steps

1. Edit `skills/audit-issue-conflicts/SKILL.md:4` — change `disable-model-invocation: true` to `disable-model-invocation: false`.
2. Re-run `/ll:audit-issue-conflicts --dry-run` to confirm the skill now dispatches into Phase 0.

## Impact

- **Priority**: P3 — Skill is entirely unreachable from any user session; impact limited to the one skill; risk-free fix (single-line frontmatter change)
- **Effort**: Trivial — One-line YAML edit
- **Risk**: Low — The flag flip only re-enables a path; it does not change skill behavior. The latent concern is inadvertent model-originated invocation, mitigated by the skill's interactive prompts (`AskUserQuestion`) on destructive actions
- **Breaking Change**: No

## Related Key Documentation

- `.claude/CLAUDE.md` — Skills & Commands section lists `/ll:audit-issue-conflicts` as a registered command; that command is currently unreachable until this fix lands

## Labels

`bug`, `skills`, `dispatch`, `completed`

## Session Log
- `hook:posttooluse-status-done` - 2026-07-16T18:34:39 - `579e8681-20c5-456b-a323-adda7601eaf3.jsonl`
- `/ll:audit-issue-conflicts` - 2026-07-16T00:00:00Z - dispatch failure reproduced (`disable-model-invocation` flag mismatch)
- `codebase-locator` - 2026-07-16T00:00:00Z - confirmed no underlying CLI wrapper
- `codebase-pattern-finder` - 2026-07-16T00:00:00Z - confirmed skill is prompt-driven, `allowed-tools` block enumerated
- `manage-issue` - 2026-07-16T00:00:00Z - `current.jsonl`

## Resolution

**Fixed** | Resolved: 2026-07-16

Flipped `disable-model-invocation: true` → `false` on line 4 of
`skills/audit-issue-conflicts/SKILL.md`. The single-line change re-enables
dispatch through the Skill tool for user-typed slash commands; no other
files modified. The skill remains fully prompt-driven (no CLI extraction).

## Status

**Completed** | Created: 2026-07-16 | Priority: P3
