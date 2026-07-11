---
id: ENH-2592
title: Add Claude Code PreToolUse hook for `.ll/decisions.yaml` corruption
type: ENH
status: done
priority: P2
parent: ENH-2587
discovered_date: '2026-07-10'
discovered_by: user-report
captured_at: '2026-07-10T22:15:00Z'
completed_at: '2026-07-11T00:36:38Z'
decision_needed: false
labels:
- decisions
- data-integrity
- tooling
- claude-code
- hook
size: Small
learning_tests_required:
- claude-code-hooks
- pyyaml
confidence_score: 96
outcome_confidence: 83
score_complexity: 19
score_test_coverage: 23
score_ambiguity: 19
score_change_surface: 22
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

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

### Files to Modify

- `hooks/scripts/check-decisions-yaml.sh` — new Claude Code `PreToolUse` wrapper. Mirror `hooks/scripts/check-duplicate-issue-id.sh:15-31` for the allow-response helper and stdin JSON extraction, but strengthen the issue sketch so validation runs against the candidate Write/Edit content rather than only the currently-on-disk file.
- `hooks/hooks.json:40-74` — append a new `PreToolUse` group with `matcher: "Write|Edit"`, command `bash ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/check-decisions-yaml.sh`, `timeout: 5`, and a status message near the existing duplicate-ID and learning-test `Write|Edit` entries.
- `scripts/tests/test_check_decisions_yaml_hook.py` — new focused subprocess test file. Reuse the hook-stdin pattern from `scripts/tests/test_hooks_integration.py:1457-1647` and the skip-when-validator-missing pattern from `scripts/tests/test_decisions_yaml_gate.py:47-60`.
- `docs/guides/DECISIONS_LOG_GUIDE.md:485-515` — expand the existing ENH-2592 bullet in the Load-Time Validation section with hook path, fire conditions, and the relationship to ENH-2590/ENH-2591.

### Existing Entrypoints and Dependencies

- `scripts/little_loops/cli/verify_decisions.py:37-61` — `_resolve_log_path()` maps `--config-root` to `<root>/.ll/decisions.yaml`; `_run()` catches `yaml.YAMLError`, `KeyError`, and `ValueError`, returning exit code `1` plus a single-line `ERROR:` message.
- `scripts/pyproject.toml:89` — publishes the `ll-verify-decisions` console script, so the hook should call `command -v ll-verify-decisions` before invoking it.
- `scripts/little_loops/decisions.py:264-282` — `load_decisions()` is the canonical validation surface; it returns cleanly for absent/empty files and raises on unknown entry types or schema drift.
- `hooks/adapters/claude-code/pre-tool-use.sh:7-13` — documents the Claude Code `PreToolUse` exit contract (`0 = allow`, `2 = block`). Do not rely on a bare validator exit code `1` being interpreted as a blocking decision.

### Similar Patterns

- `hooks/scripts/check-duplicate-issue-id.sh:15-31` — standard allow JSON response, stdin JSON read, `tool_name`/`tool_input.file_path` extraction, and fast allow for irrelevant tools/paths.
- `hooks/scripts/check-duplicate-issue-id.sh:118-125` — blocking feedback shape with a `[little-loops]` reason; use the same user-facing prefix if the validator reports corruption.
- `scripts/tests/test_decisions_yaml_pre_commit_gate.py:35-47` and `scripts/tests/test_decisions_yaml_gate.py:38-44` — inline `OTHE_203_PAYLOAD` locally in each test file rather than importing a shared fixture.
- `scripts/tests/test_hooks_integration.py:2703-2714` — unconditional structural assertion pattern for ensuring `hooks/hooks.json` still registers a required script.

### Tests

- Add clean and OTHE-203 cases that synthesize Claude Code tool input JSON. For `Write`, include `tool_input.content` containing the candidate `.ll/decisions.yaml`; for `Edit`, include `old_string`/`new_string` if candidate reconstruction is supported. This is the only way a `PreToolUse` hook can prove it catches corruption before disk mutation.
- Add a non-target-path case (for example `.ll/learning-tests/example.md`) that exits 0 without invoking the validator.
- Add a missing-validator case by clearing `PATH` or shadowing lookup behavior, asserting the script prints a concise skip message and exits 0.
- Add a `hooks/hooks.json` shape test asserting a `PreToolUse` `Write|Edit` group invokes `check-decisions-yaml.sh` with `timeout: 5`.

### Documentation

- Document that this hook is a Claude Code host-layer belt: it fires for Claude `Write`/`Edit` operations, complements the git pre-commit hook and pytest gate, and does not cover non-Claude editors.

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/BUILTIN_HOOKS_GUIDE.md:22-57` (Lifecycle-at-a-Glance table) and `:184-234` (`## PreToolUse` section) — add a row and a sibling subsection for the new `check-decisions-yaml.sh` so users discover it next to `check-duplicate-issue-id.sh`; row description: "Blocks writing a corrupt `.ll/decisions.yaml`". [Agent 2 finding]
- `docs/reference/CONFIGURATION.md:784-795` — alongside the existing "Integrity gate (ENH-2591)" paragraph, add a sentence noting that the Claude-side host hook (ENH-2592) is a sibling belt and that only the pre-commit + pytest gates fire for non-Claude editors. [Agent 2 finding]
- `docs/ARCHITECTURE.md:715-731` — under `### Decisions Log: .ll/decisions.yaml`, add a sentence listing the three transport-layer integrations (ENH-2590 pre

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

## Proposed Solution

### Recommended Implementation

Implement `check-decisions-yaml.sh` as a thin Claude Code `PreToolUse` guard around `ll-verify-decisions`, but resolve two codebase-discovered ambiguities before coding:

1. **Validate proposed content, not just the current file.** A `PreToolUse` hook runs before Claude mutates disk, so `ll-verify-decisions --config-root <repo>` against the existing `.ll/decisions.yaml` would miss a corrupt `Write` payload when the current file is still valid. For `Write`, write `tool_input.content` to a temporary `<tmp>/.ll/decisions.yaml` and run `ll-verify-decisions --config-root <tmp>`. For `Edit`, reconstruct the candidate by applying `old_string` → `new_string` (respecting `replace_all` if present) to the current file, then validate the temp copy. If reconstruction is impossible, allow the host Edit failure to proceed naturally rather than hand-parsing partial edits.
2. **Use the Claude Code blocking contract.** `ll-verify-decisions` returns `1` on corruption, but `hooks/adapters/claude-code/pre-tool-use.sh:7-13` documents `exit 2` as the host-level block signal. Convert validator failure into either `exit 2` with the validator's single-line `ERROR:` on stderr, or a sibling-style `permissionDecision: deny` JSON response. To preserve the current acceptance criterion ("exits non-zero when corrupted"), prefer `exit 2`.
3. **Keep fail-open behavior for missing tooling.** If `ll-verify-decisions` is absent, print one concise skip line to stderr and exit 0, matching the sibling graceful-degrade pattern.
4. **Keep path matching narrow.** Ignore all paths except `.ll/decisions.yaml` and absolute paths ending in `/.ll/decisions.yaml`. The existing Claude adapter passes JSON on stdin; supporting `$CLAUDE_TOOL_INPUT` as a fallback is harmless but should not replace stdin handling.

This keeps the hook small, uses the existing validator as the single source of truth, and makes the negative OTHE-203 test meaningful for the pre-write layer.

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

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- Treat the shell snippet above as a starting sketch, not the final implementation: by validating the on-disk repo root only, it cannot catch a corrupt `tool_input.content` before a `Write` happens. The implemented script should stage candidate content in a temporary config root and validate that temp root with `ll-verify-decisions`.
- The `Edit` tool path needs explicit handling because the candidate content is split across `old_string`, `new_string`, and optional `replace_all`; tests should include at least one Edit reconstruction case or explicitly document why ENH-2592 only validates Write candidate content plus current-file sanity for Edit.
- The hook should not require `jq` if Python is used for JSON parsing. Existing sibling hooks use `jq`, but this repository already assumes Python for Claude hook adapters (`hooks/adapters/claude-code/pre-tool-use.sh:11-13`).

## Notes

- The hook is **optional** per ENH-2587 step 5 — the git + pytest gate trio
  may suffice. This child ships it because defense-in-depth at the host layer
  is cheap and prevents repeated agent corruption incidents.
- The hook runs on every `.ll/decisions.yaml` Write or Edit Claude makes.
  If false-positives become a problem, restrict with a more specific matcher
  (e.g. `matcher: "Write" + includePaths=["/.ll/decisions\\.yaml$"]` if
  supported).

## Session Log
- `/ll:ready-issue` - 2026-07-11T00:20:06 - `479dba81-a372-4f33-948e-17754ac86539.jsonl`
- `/ll:refine-issue` - 2026-07-11T00:05:59 - `a5ea7d8c-7d19-4643-8a06-5f0fb2a4728d.jsonl`
- `/ll:issue-size-review` - 2026-07-10T22:15:00 - `61c51949-414d-4865-b102-91b1bc365edd.jsonl`
- `/ll:confidence-check` - 2026-07-11T00:14:20 - `55f026ff-12e8-427e-adf2-8e795627dceb.jsonl`
- `/ll:manage-issue` - 2026-07-11T00:36:09 - `bfc762d0-6be3-4730-9221-e38b7e394e78.jsonl`
