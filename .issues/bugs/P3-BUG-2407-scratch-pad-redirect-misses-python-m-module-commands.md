---
id: BUG-2407
title: scratch-pad-redirect hook misses `python -m <module>` commands
type: BUG
priority: P3
status: open
captured_at: '2026-06-30T21:29:50Z'
completed_at: 2026-06-30T21:58:37Z
discovered_date: 2026-06-30
discovered_by: capture-issue
labels:
- scratch-hook
- tooling
- automation
- allowlist
confidence_score: 100
outcome_confidence: 89
score_complexity: 21
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 25
---
# BUG-2407: scratch-pad-redirect hook misses `python -m <module>` commands

## Summary

The `scratch-pad-redirect` PreToolUse hook (`hooks/scripts/scratch-pad-redirect.sh`)
matches a Bash command against `scratch_pad.command_allowlist` using only the
command's **first token**. The project's canonical test and type commands are
`python -m pytest` and `python -m mypy` (the configured `project.test_cmd` /
`project.type_cmd` and the examples in `.claude/CLAUDE.md`). Their first token is
`python`, which is not in the allowlist (`pytest`/`mypy` are), so these commands
are never auto-redirected to scratch — defeating the feature for its primary
intended use case in automation contexts.

## Motivation

This bug matters because it defeats the scratch-pad-redirect feature for its
primary documented use case:
- `.claude/CLAUDE.md` § Automation: Scratch Pad explicitly tells agents to run
  `python -m pytest ...` / `python -m mypy ...` and expect auto-redirect to
  scratch — that promise silently fails for exactly these two commands.
- Automation contexts (`ll-auto`, `ll-parallel`, `ll-sprint`) run test/type
  commands non-interactively; without redirect, large `python -m pytest`
  output lands in conversation context uncapped, the bloat the feature exists
  to prevent.
- Low immediate severity (a documented manual workaround exists), hence P3 —
  but the gap is silent and easy to miss until context bloat is observed.

## Current Behavior

In `scratch-pad-redirect.sh` the allowlist check is:

```bash
FIRST_TOKEN=$(echo "$CMD" | awk '{print $1}')          # "python -m pytest" -> "python"
FIRST_BASE=$(basename "$FIRST_TOKEN" ...)               # -> "python"
# compares FIRST_BASE / FIRST_TOKEN against each command_allowlist entry
```

For `python -m pytest scripts/tests/`, `FIRST_BASE` is `python`. The default
allowlist is `["cat","pytest","mypy","ruff","ls","grep","find"]`, so there is no
match and the hook returns `allow_response` unchanged — no redirect, and (because
the `mkdir -p .loops/tmp/scratch` only runs inside the redirect branch) the scratch
directory is not created either. A direct `pytest ...` / `mypy ...` invocation IS
matched and redirected; only the `python -m <module>` form slips through.

This was observed live in an interactive (bypass-permissions) session: a `grep`
command was redirected as expected, while `python -m pytest ...` was not, and a
manual `> .loops/tmp/scratch/...` redirect then failed because the directory did
not exist (a bare `>` does not create parent dirs). BUG-2357 already noted in
passing (line 45) that `python3` is not in the allowlist, but that was incidental
reasoning for a different fix and the gap was never filed on its own.

## Expected Behavior

The hook should auto-redirect the project's documented `python -m pytest` /
`python -m mypy` commands the same way it redirects direct `pytest` / `mypy`
invocations — i.e. the allowlist match should "see through" a `python -m <module>`
wrapper and match on `<module>`.

## Steps to Reproduce

1. In an interactive (or automation) session with the `scratch-pad-redirect`
   PreToolUse hook active, run a Bash command using the `python -m <module>`
   form, e.g. `python -m pytest scripts/tests/` or
   `python -m mypy scripts/little_loops/`.
2. Observe that the hook's `FIRST_BASE` allowlist check resolves to `python`
   (not `pytest`/`mypy`), so the `command_allowlist` membership check fails
   and `allow_response` is returned unchanged — no redirect occurs.
3. Compare against a direct invocation of the same tool, e.g.
   `pytest scripts/tests/` — this IS matched and redirected to scratch as
   expected.
4. Note that because the redirect branch never fires for the
   `python -m <module>` form, `mkdir -p .loops/tmp/scratch` is also skipped,
   so a subsequent manual `> .loops/tmp/scratch/...` redirect fails (no
   parent directory created).

## Root Cause

First-token allowlist matching in `scratch-pad-redirect.sh` does not unwrap
interpreter-prefixed invocations (`python -m <module>`, `python3 -m <module>`).
The effective command being run is `<module>`, but the matcher only inspects the
literal first token (`python`).

## Proposed Solution

Add a small interpreter-unwrap step before the allowlist loop: if `FIRST_BASE`
matches a known interpreter (`python`, `python3`, `python3.NN`) and the command
contains `-m <module>`, use the last path component of `<module>` as the
effective name for allowlist matching. Keep it conservative — only unwrap the
`-m <module>` form, leave everything else as-is.

```bash
# After computing FIRST_BASE:
EFFECTIVE_NAME="$FIRST_BASE"
case "$FIRST_BASE" in
    python|python3|python3.*)
        # Extract the module after `-m` (e.g. `python -m pytest ...` -> `pytest`)
        MOD=$(echo "$CMD" | sed -nE 's/.*[[:space:]]-m[[:space:]]+([A-Za-z0-9_.]+).*/\1/p')
        [ -n "$MOD" ] && EFFECTIVE_NAME="${MOD##*.}"   # `little_loops.cli` -> `cli`; `pytest` -> `pytest`
        ;;
esac
# Then match EFFECTIVE_NAME (and FIRST_BASE) against command_allowlist.
```

Alternative (lower-effort, less precise): add `python` / `python3` to the default
`command_allowlist`. Rejected — it would redirect ALL python invocations (incl.
short one-liners and REPL-ish calls), which is broader than intended.

## Integration Map

### Files to Modify
- `hooks/scripts/scratch-pad-redirect.sh` — add the interpreter-unwrap step
  before the `command_allowlist` match loop

### Dependent Files (Callers/Importers)
- `hooks/hooks.json` — registers `scratch-pad-redirect.sh` as the PreToolUse
  hook for Bash; no change needed, invocation contract is unchanged
- `.ll/ll-config.json` — supplies `scratch_pad.command_allowlist`; no change
  needed, the unwrap step only affects how `FIRST_BASE` is computed before
  matching against the existing allowlist

### Similar Patterns
- N/A — this is the only first-token allowlist matcher in the hook scripts

### Tests
- `scripts/tests/` test file covering `TestScratchPadRedirect` (existing
  seven cases) — add `python -m pytest ...` / `python -m mypy ...` cases per
  Implementation Steps

### Documentation
- `.claude/CLAUDE.md` § Automation: Scratch Pad — already documents the
  `python -m pytest` / `python -m mypy` examples as the canonical commands;
  no doc change needed once the hook honors them

### Configuration
- N/A — no config schema changes; default `command_allowlist` values are
  unchanged

## Impact

- **Automation contexts** (`ll-auto`, `ll-parallel`, `ll-sprint`): large
  `python -m pytest` output is not redirected, so it lands in conversation context
  uncapped — the exact bloat the scratch-pad feature exists to prevent. Mitigated
  today only by the agent manually redirecting per the `.claude/CLAUDE.md` guidance.
- Low blast radius and a documented manual workaround exist, hence P3.

## Implementation Steps

1. Add the interpreter-unwrap step in `hooks/scripts/scratch-pad-redirect.sh`
   before the `command_allowlist` match loop.
2. Add a `TestScratchPadRedirect` case asserting `python -m pytest ...` is
   rewritten to redirect to scratch (and `python -m mypy ...`), alongside the
   existing seven cases.
3. Confirm direct `pytest`/`mypy` and non-allowlisted commands (`git status`)
   behavior is unchanged.

## Session Log
- `/ll:manage-issue` - 2026-06-30T21:58:37Z - `179157a9-47d5-4949-8717-94d31f6968b3.jsonl`
- `/ll:ready-issue` - 2026-06-30T21:53:48 - `db8a63e4-7a92-44b4-8cb8-4028c95d7b8b.jsonl`
- `/ll:confidence-check` - 2026-06-30T21:50:19Z - `a69cdcc2-dcb8-4c8c-8d25-8101c9563e35.jsonl`
- `/ll:format-issue` - 2026-06-30T21:33:41 - `df65d7ca-2f4e-4eb3-8e1b-7c78f7a751a8.jsonl`
- `/ll:capture-issue` - 2026-06-30T21:29:50Z - conversation mode (scratch-pad hook discussion)

---

## Resolution

- **Action**: fix
- **Completed**: 2026-06-30
- **Status**: Completed

### Changes Made
- `hooks/scripts/scratch-pad-redirect.sh`: added an interpreter-unwrap step
  before the `command_allowlist` match loop — when `FIRST_BASE` is
  `python`/`python3`/`python3.NN`, extract the module after `-m` and use its
  last dotted component (`EFFECTIVE_NAME`) as an additional match candidate,
  so `python -m pytest ...` / `python -m mypy ...` redirect the same way
  direct `pytest`/`mypy` invocations do.
- `scripts/tests/test_hooks_integration.py`: added three `TestScratchPadRedirect`
  cases — `python -m pytest` and `python3 -m mypy` redirect as expected, and
  a non-allowlisted module (`python -m http.server`) is left unchanged.

### Verification Results
- Tests: PASS (`python -m pytest scripts/tests/`)
- Lint: PASS (`ruff check scripts/`)
- Types: N/A (bash-only change)
- Run: N/A
- Integration: PASS (no duplication; reuses existing allowlist loop and config helpers)

## Status

**Done** | Created: 2026-06-30 | Completed: 2026-06-30 | Priority: P3
