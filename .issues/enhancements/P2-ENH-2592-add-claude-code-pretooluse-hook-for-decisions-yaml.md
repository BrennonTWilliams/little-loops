---
id: ENH-2592
title: Add Claude Code PreToolUse hook for `.ll/decisions.yaml` corruption
type: ENH
status: open
priority: P2
parent: ENH-2587
discovered_date: '2026-07-10'
discovered_by: user-report
captured_at: '2026-07-10T22:15:00Z'
decision_needed: false
labels:
  - decisions
  - data-integrity
  - tooling
  - claude-code
  - hook
size: Small
---

# ENH-2592: Add Claude Code PreToolUse hook for `.ll/decisions.yaml` corruption

## Summary

Add a Claude Code host PreToolUse hook (`hooks/scripts/check-decisions-yaml.sh`)
that fires whenever Claude's Write or Edit tools touch `.ll/decisions.yaml`,
catching agent-induced corruption before it can be committed. Mirrors the
shape of `hooks/scripts/check-duplicate-issue-id.sh:1-50`.

This is the **Claude-side belt** to ENH-2590 (pre-commit hook) and ENH-2591
(pytest CI gate). It does **not** fire when developers edit the file outside
Claude Code.

## Parent Issue

Decomposed from ENH-2587: "Guard `.ll/decisions.yaml` with a load-time validation
check on commit/CI"

## Why This Child Exists Standalone

Claude Code host hooks are a separately configurable subsystem — the
`hooks/hooks.json` schema, the `matcher` field, and `timeout` semantics are
distinct from git hooks and pytest gates. This child ships the bash script
and the `hooks.json` registration as a self-contained integration.

## Acceptance Criteria

- `hooks/scripts/check-decisions-yaml.sh` exists and:
  - Exits 0 when `.ll/decisions.yaml` is valid.
  - Exits non-zero when the file is corrupted (OTHE-203 fixture).
  - Runs `ll-verify-decisions --config-root <path>` with the path extracted
    from the tool input JSON (`$CLAUDE_TOOL_INPUT` or stdin).
  - Has a hard 5-second timeout at the call site (the host enforces the
    `timeout: 5` field; the script should not sleep / wait).
- `hooks/hooks.json` registers the hook under `PreToolUse` with
  - `matcher: Write|Edit`
  - `timeout: 5`
- The hook does NOT regress when `ll-verify-decisions` is missing (skip with
  echo rather than spam failures — match the sibling's graceful-degrade
  pattern).
- A short hook-shape test exists under `scripts/tests/` that shells out to
  the bash script with a synthesized `CLAUDE_TOOL_INPUT` JSON for valid and
  corrupted cases.

## Files to Modify

- `hooks/scripts/check-decisions-yaml.sh` (new) — bash hook mirroring
  `hooks/scripts/check-duplicate-issue-id.sh:1-50`. Read tool input from
  stdin or `$CLAUDE_TOOL_INPUT` env; extract file path; run
  `ll-verify-decisions`; propagate exit code.
- `hooks/hooks.json` — register under `PreToolUse` with
  `matcher: "Write|Edit"` and `timeout: 5` (sibling entry has the same
  shape; mirror its exact JSON placement).
- `docs/guides/DECISIONS_LOG_GUIDE.md` — one paragraph explaining the
  Claude Code host hook exists, what it fires on, and that it complements
  (does not replace) the pre-commit hook and pytest CI gate.
- `scripts/tests/test_check_decisions_yaml_hook.py` (new) — bash script
  subprocess test for valid/corrupted cases; skip when bash is unavailable.

## Depends On

- **ENH-2589** — `ll-verify-decisions` CLI must exist on `PATH`.

## Blocks

Nothing.

## Implementation Steps

1. Read `hooks/scripts/check-duplicate-issue-id.sh:1-50` to extract the
   canonical template (matcher input parsing, exit-code propagation, error
   message format).
2. Create `hooks/scripts/check-decisions-yaml.sh`:
   ```bash
   #!/usr/bin/env bash
   # PreToolUse hook for Claude Code: validate .ll/decisions.yaml before write.
   # Mirrors check-duplicate-issue-id.sh; timeout enforced by host (5s).
   set -euo pipefail
   
   INPUT="${CLAUDE_TOOL_INPUT:-$(cat)}"
   FILE_PATH=$(printf '%s' "$INPUT" | python3 -c 'import json,sys; print(json.loads(sys.stdin.read()).get("file_path",""))')
   
   if [[ "$FILE_PATH" != */.ll/decisions.yaml && "$FILE_PATH" != ".ll/decisions.yaml" ]]; then
       exit 0  # not the target file
   fi
   
   if ! command -v ll-verify-decisions >/dev/null 2>&1; then
       echo "ll-verify-decisions not installed; skipping decisions.yaml validation" >&2
       exit 0  # graceful degrade
   fi
   
   exec ll-verify-decisions --config-root "$(dirname "$FILE_PATH")/.."
   ```
3. Make the script executable: `chmod +x hooks/scripts/check-decisions-yaml.sh`.
4. Register in `hooks/hooks.json` under `PreToolUse` with matcher `Write|Edit`
   and timeout 5.
5. Add a paragraph to `docs/guides/DECISIONS_LOG_GUIDE.md` describing the
   Claude-side hook.
6. Create `scripts/tests/test_check_decisions_yaml_hook.py` with positive
   and negative OTHE-203 cases.
7. Run `python -m pytest scripts/tests/`.

## Notes

- The hook is **optional** per ENH-2587 step 5 — the git + pytest gate trio
  may suffice. This child ships it because defense-in-depth at the host layer
  is cheap and prevents repeated agent corruption incidents.
- The hook runs on every `.ll/decisions.yaml` Write or Edit Claude makes.
  If false-positives become a problem, restrict with a more specific matcher
  (e.g. `matcher: "Write" + includePaths=["/.ll/decisions\\.yaml$"]` if
  supported).

## Session Log
- `/ll:issue-size-review` - 2026-07-10T22:15:00 - `61c51949-414d-4865-b102-91b1bc365edd.jsonl`
