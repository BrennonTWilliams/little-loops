---
id: ENH-875
type: ENH
priority: P3
status: open
discovered_date: 2026-03-24
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 93
---

# ENH-875: Add --auto flag to commit skill

## Summary

The `/ll:commit` skill should accept an `--auto` flag that suppresses all user interactivity and makes the best decision it can autonomously — staging files, writing commit messages, and executing without prompting.

## Current Behavior

`/ll:commit` always pauses to present its plan to the user and ask for gitignore approval before executing any git operations. There is no way to run it non-interactively.

## Expected Behavior

When invoked with `--auto`, the skill skips all `AskUserQuestion` prompts and proceeds with the best available decision:
- Skips the gitignore suggestions step (or silently applies obvious patterns)
- Stages and commits without presenting a plan for approval
- Outputs a summary of what it did after the fact

## Motivation

Automation contexts (`ll-auto`, `ll-parallel`, `ll-sprint`, FSM loops) need to commit changes without human approval gates. Today these pipelines cannot use `/ll:commit` at all — they either call raw `git` commands or skip committing entirely. An `--auto` flag would make the skill usable as a building block in fully automated workflows.

## Proposed Solution

`commands/commit.md` has no argument-parsing block today — no `arguments:` frontmatter, no `$ARGUMENTS` check, no flag parsing section of any kind. The implementation must add this from scratch.

The command should use the `$ARGUMENTS`-based pattern (Pattern B from `skills/confidence-check/SKILL.md:37-69`) since `commit.md` has no named positional arguments to conflict with:

```bash
### 0. Parse Flags

AUTO_MODE=false

# Auto-enable in automation contexts
if [[ "$ARGUMENTS" == *"--dangerously-skip-permissions"* ]] || [[ -n "${DANGEROUSLY_SKIP_PERMISSIONS:-}" ]]; then
    AUTO_MODE=true
fi

if [[ "$ARGUMENTS" == *"--auto"* ]]; then AUTO_MODE=true; fi
```

The only `AskUserQuestion` call is the gitignore approval block at `commit.md:33-44`. In auto mode this block should be skipped entirely (the issue permits silently skipping gitignore suggestions). The plan-presentation step at `commit.md:56-59` is a **narrative step**, not an approval gate — no `AskUserQuestion` is used there — so it needs no guard; it can remain as-is or be made quieter in auto mode.

## Integration Map

### Files to Modify
- `commands/commit.md` — add `--auto` flag parsing and conditional branching around `AskUserQuestion` calls

### Dependent Files (Callers/Importers)

Loop files that invoke `/ll:commit` bare (no flags) — all could benefit from passing `--auto` in automation contexts:
- `loops/issue-refinement.yaml:97-100` — `action: /ll:commit` (bare)
- `loops/issue-discovery-triage.yaml:71-76` — `Run /ll:commit` in prompt action
- `loops/issue-size-split.yaml:55-60` — `Run /ll:commit` in prompt action
- `loops/docs-sync.yaml:58-63` — `Run /ll:commit` in prompt action
- `loops/dead-code-cleanup.yaml:93-96` — `Run /ll:commit` in prompt action
- `loops/backlog-flow-optimizer.yaml:125-128` — `Run /ll:commit` in prompt action
- `loops/issue-staleness-review.yaml:66-69` — `Run /ll:commit` in prompt action
- `loops/sprint-build-and-validate.yaml:107-110` — `Run /ll:commit` in prompt action

Skills that reference `/ll:commit` as a next-step recommendation:
- `skills/format-issue/SKILL.md:350,405,422`
- `skills/audit-docs/SKILL.md:162,285,330`
- `skills/capture-issue/SKILL.md:376`
- `skills/map-dependencies/SKILL.md:182`
- `skills/issue-size-review/SKILL.md:335`

### Similar Patterns
- `skills/confidence-check/SKILL.md:37-69` — canonical `$ARGUMENTS`-based `--auto` parsing with `--dangerously-skip-permissions` detection (Pattern B — use this one)
- `commands/verify-issues.md:31-46` — `$FLAGS`-based parsing in a command with named frontmatter args (Pattern A — alternative if named arg preferred)
- `commands/prioritize-issues.md:40-46` — minimal pattern: env-var check only + `$FLAGS` check
- `skills/confidence-check/SKILL.md:406-413` — `AskUserQuestion` bypass guard: `**Auto mode bypass**: When AUTO_MODE is true, skip AskUserQuestion and proceed automatically`
- `skills/format-issue/SKILL.md:236-250` — section-level guard: `**Skip this entire section if AUTO_MODE is true.**`

### Tests
- No dedicated test file exists for `commands/commit.md`
- `scripts/tests/test_subprocess_mocks.py` — mentions commit in subprocess mock context
- `scripts/tests/test_cli_e2e.py` — E2E tests mentioning commit
- `scripts/tests/test_issue_lifecycle.py` — lifecycle tests mentioning commit
- No new test file is needed for this change (the command file itself is tested by manual/E2E, not unit tests)

### Documentation
- `commands/commit.md:82-86` — update Examples section to show `--auto` usage
- `docs/reference/COMMANDS.md` — update one-liner description for `/ll:commit` to mention `--auto` flag

### Configuration
- N/A

## Implementation Steps

1. Add a `### 0. Parse Flags` section at the top of `commands/commit.md` using the `$ARGUMENTS`-based pattern from `skills/confidence-check/SKILL.md:37-69`:
   ```bash
   AUTO_MODE=false
   if [[ "$ARGUMENTS" == *"--dangerously-skip-permissions"* ]] || [[ -n "${DANGEROUSLY_SKIP_PERMISSIONS:-}" ]]; then AUTO_MODE=true; fi
   if [[ "$ARGUMENTS" == *"--auto"* ]]; then AUTO_MODE=true; fi
   ```
   Note: `commit.md` currently has **no** flag-parsing block at all — this must be added from scratch. There is no existing `--quick` flag in this file.

2. Wrap the gitignore `AskUserQuestion` block at `commit.md:33-44` with a guard:
   ```
   **Skip step 1.5b if `AUTO_MODE` is true.** In auto mode, silently skip gitignore suggestions without prompting.
   ```
   (The `suggest_gitignore_patterns()` call at line 23 can still run to detect patterns; just skip the `AskUserQuestion` and the `add_patterns_to_gitignore()` call.)

3. The plan-presentation step at `commit.md:56-59` is a **narrative step only** — it uses no `AskUserQuestion` and has no approval gate. It does not need guarding; the model narrates then proceeds to step 4 regardless.

4. Update the `Examples` section at `commit.md:82-86` to show `--auto` usage:
   ```bash
   # Non-interactive commit from automation context
   /ll:commit --auto
   ```

5. Update `docs/reference/COMMANDS.md` description for `/ll:commit` to mention `--auto` flag.

## API/Interface

```bash
# Non-interactive commit from automation context
/ll:commit --auto
```

## Impact

- **Priority**: P3 - Useful for automation but no existing workflows are broken without it
- **Effort**: Small - One command file, pattern already established by other `--auto` flags
- **Risk**: Low - Auto mode is opt-in; existing interactive behavior unchanged
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`enhancement`, `commit-skill`, `automation`, `captured`

## Status

**Open** | Created: 2026-03-24 | Priority: P3

---

## Session Log
- `/ll:confidence-check` - 2026-03-24T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/15148437-fb49-4726-959b-9737cdcdbbb3.jsonl`
- `/ll:refine-issue` - 2026-03-24T19:12:21 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/72a47170-0c22-4892-ab2d-b86daed6ab09.jsonl`
- `/ll:capture-issue` - 2026-03-24T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1c23589c-5619-4975-90e9-77c587e90773.jsonl`
