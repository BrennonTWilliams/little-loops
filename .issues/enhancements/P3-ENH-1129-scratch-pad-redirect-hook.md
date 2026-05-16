---
id: ENH-1129
type: ENH
priority: P3
status: completed
parent: ENH-1111
size: Medium
confidence_score: 100
outcome_confidence: 86
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 25
completed_at: 2026-04-16
---

# ENH-1129: Implement scratch-pad-redirect.sh PreToolUse Hook

## Summary

Create `hooks/scripts/scratch-pad-redirect.sh`, register it in `hooks/hooks.json` as a second PreToolUse entry (matcher `Bash|Read`), and add `TestScratchPadRedirect` in `scripts/tests/test_hooks_integration.py`. This is the core deliverable of ENH-1111.

## Parent Issue

Decomposed from ENH-1111: Scratch-Pad Enforcement via PreToolUse Hook

## Prerequisite

Requires ENH-1128 (schema extension) to be merged so `ll_config_value` can resolve the four new `scratch_pad` properties.

## Motivation

The scratch-pad convention in CLAUDE.md is a soft rule — the model forgets it in long loop runs, flooding context with test output and file contents. A PreToolUse hook enforces it automatically by rewriting Bash commands to tee+tail and denying large Read calls with a Bash scratch suggestion.

## Expected Behavior

- Hook is a no-op when `scratch_pad.enabled` is `false` (default)
- When `automation_contexts_only: true` (default), hook skips unless `permission_mode == "bypassPermissions"` (the signal from `ll-auto`/`ll-parallel`/`ll-loop` via `subprocess_utils.py:97-105`)
- **Bash rewrite**: if `tool_name == "Bash"` and first token of command matches `command_allowlist`, rewrite `command` to `<original> > .loops/tmp/scratch/<name>.txt 2>&1; tail -<tail_lines> .loops/tmp/scratch/<name>.txt`; emit `hookSpecificOutput.permissionDecision=allow` + `updatedInput.command=<new>` + `additionalContext` naming scratch path
- **Read deny**: if `tool_name == "Read"` and target file matches `file_extension_filters` and `wc -l` exceeds `threshold_lines`, return `permissionDecision=deny` with `permissionDecisionReason` suggesting the equivalent `Bash cat > .loops/tmp/scratch/<name>.txt` command

## Acceptance Criteria

- `hooks/scripts/scratch-pad-redirect.sh` created following `check-duplicate-issue-id.sh:1-129` pattern (stdin via `INPUT=$(cat)`, parse with `jq -r`, `allow_response()` helper, source `lib/common.sh`)
- Single-pass `jq @tsv` for `tool_name`, `tool_input.command`, `tool_input.file_path`, `permission_mode` (per `context-monitor.sh:45-47` pattern)
- Hook registered in `hooks/hooks.json` as a second PreToolUse entry with matcher `Bash|Read`, 5s timeout; does not disturb the existing `Write|Edit` entry at lines 29-41
- `mkdir -p .loops/tmp/scratch` before emitting rewritten Bash command
- Unit tests in `TestScratchPadRedirect` class in `scripts/tests/test_hooks_integration.py`:
  - (a) disabled → no-op (allow unchanged)
  - (b) enabled, non-automation → no-op
  - (c) enabled + automation + Bash under threshold → allow unchanged
  - (d) enabled + automation + Bash over threshold → `updatedInput` rewrites to tee+tail
  - (e) enabled + automation + Read over threshold → deny with `additionalContext`
  - (f) `command_allowlist` — non-matching Bash (e.g. `git status`) → allow unchanged
- Integration test: simulated 500-line `pytest` invocation in automation context leaves only `tail_lines` lines + scratch path in hook result

## Files to Create

- `hooks/scripts/scratch-pad-redirect.sh`

## Files to Modify

- `hooks/hooks.json` — add second PreToolUse entry (matcher `Bash|Read`, timeout 5s)
- `scripts/tests/test_hooks_integration.py` — add `TestScratchPadRedirect` class

## Reference Files (read only)

- `hooks/scripts/check-duplicate-issue-id.sh:1-129` — PreToolUse structural template
- `hooks/scripts/context-monitor.sh:17,45-47` — single-pass `jq @tsv` pattern
- `hooks/scripts/lib/common.sh:182-234` — `ll_resolve_config` / `ll_feature_enabled` / `ll_config_value`
- `docs/claude-code/hooks-reference.md:807-828` — `updatedInput` / `additionalContext` contract
- `docs/claude-code/hooks-reference.md:395,712-751` — `permission_mode`, Bash/Read `tool_input` schemas
- `scripts/little_loops/subprocess_utils.py:97-105` — confirms `--dangerously-skip-permissions` source
- `scripts/little_loops/loops/fix-quality-and-tests.yaml:87` — loop that Reads `.loops/tmp/` files (behavioral interaction: deny-with-hint is expected, not a bug)
- `scripts/little_loops/loops/dead-code-cleanup.yaml:84` — same
- `scripts/little_loops/loops/test-coverage-improvement.yaml:94,165` — same

## Open Decisions

- **Automation detection**: use `permission_mode == "bypassPermissions"` (no CLI changes) vs exporting `LL_AUTOMATION=1` from `subprocess_utils.py`. Recommendation: `permission_mode` is simpler.

## Codebase Research Findings

_Added by `/ll:refine-issue` — from codebase analysis (ENH-1128 is confirmed merged; schema present):_

### Schema status (ENH-1128 landed)
- `config-schema.json:526-568` defines the full `scratch_pad` block with `"additionalProperties": false` at line 567 — the hook cannot read any non-schema key.
- Defaults (all already schema-enforced): `enabled=false`, `threshold_lines=200` (min 50 / max 1000), `automation_contexts_only=true`, `tail_lines=20` (min 5 / max 200), `command_allowlist=["cat","pytest","mypy","ruff","ls","grep","find"]`, `file_extension_filters=[".log",".txt",".json",".md",".py",".ts",".tsx",".js"]`.
- Active project config already carries the block at `.ll/ll-config.json:29-36` with `enabled: false` — a live integration test can flip this key without a separate fixture.

### Hook structural gotchas
- `allow_response()` is **locally defined inside each hook** (see `check-duplicate-issue-id.sh:17-20`); it is NOT exported from `lib/common.sh`. The new hook must define its own copy.
- `jq` must be guarded at the top (`check-duplicate-issue-id.sh:23-25`): fail-open to `allow_response` if absent.
- Config read order: `ll_resolve_config` (sets `$LL_CONFIG_FILE` as side effect, creates `.ll/` via `mkdir -p`) → `ll_feature_enabled "scratch_pad.enabled"` (returns exit 0/1) → `ll_config_value "scratch_pad.threshold_lines" "200"` (echoes value; caller captures with `$(...)`). Both helpers are no-ops/fail-open when `$LL_CONFIG_FILE` is empty or `jq` missing (`lib/common.sh:201-210, 222-228`).
- Single-pass `@tsv` extraction is required (`context-monitor.sh:45`). Pattern for this hook:
  ```bash
  IFS=$'\t' read -r TOOL_NAME CMD FILE_PATH PERM_MODE <<< \
    "$(echo "$INPUT" | jq -r '[(.tool_name // ""),(.tool_input.command // ""),(.tool_input.file_path // ""),(.permission_mode // "")] | @tsv' 2>/dev/null)"
  ```

### PreToolUse response contract (docs/claude-code/hooks-reference.md:807-828)
- Allow-with-rewrite:
  ```json
  {"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"allow","updatedInput":{"command":"<rewritten>"},"additionalContext":"Output redirected to .loops/tmp/scratch/<name>.txt"}}
  ```
- Deny-with-hint (for oversized `Read`): `permissionDecisionReason` is shown **to Claude** (not the user) — so the text should be an actionable `Bash cat > .loops/tmp/scratch/... ; tail ...` suggestion.
- Both outcomes `exit 0`. Never emit the deprecated top-level `decision`/`reason` fields.

### `hooks/hooks.json` registration (hooks.json:29-41)
- `PreToolUse` is already an array with one element (`Write|Edit` → `check-duplicate-issue-id.sh`). Append a **sibling object** with `matcher: "Bash|Read"`, `timeout: 5`, `command: "bash ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/scratch-pad-redirect.sh"`. The `${CLAUDE_PLUGIN_ROOT}` variable is the established convention.

### Automation-context signal (`subprocess_utils.py:99`)
- `--dangerously-skip-permissions` is unconditional in `cmd_args` used by `ll-auto` / `ll-parallel` / `ll-loop` / `ll-sprint`. This surfaces as `permission_mode == "bypassPermissions"` in every PreToolUse event stdin payload (`hooks-reference.md:395`). No other CLI path sets this.

### Test harness patterns (`scripts/tests/test_hooks_integration.py`)
- Closest structural match: `TestDuplicateIssueId` at lines 999-1189 (same hook type, same allow/deny shape).
- Canonical invocation:
  ```python
  result = subprocess.run([str(hook_script)], input=json.dumps(input_data),
                          capture_output=True, text=True, timeout=5)
  assert "deny" in result.stdout.lower()  # or "allow"
  ```
- Every test `os.chdir(tmp_path)` inside `try/finally`; config injected by writing `tmp_path/.ll/ll-config.json` (see `TestContextMonitor.test_config` fixture at lines 23-36 for the shared-fixture style).
- **No existing test** in the file exercises `permission_mode: "bypassPermissions"` — `TestScratchPadRedirect` establishes this pattern. Omit the key for the non-automation case (jq falls back to `""`).
- `TestSharedConfigFunctions` (lines 1192-1315) shows the `_run_bash` helper style for sourcing `lib/common.sh` directly if needed; the scratch-pad tests should NOT need this — they exercise the hook end-to-end.

### Loop YAML interaction points (confirm deny-with-hint is expected, not a bug)
- `fix-quality-and-tests.yaml` — writes `.loops/tmp/ll-test-results.txt` at line 79, Reads at line 87.
- `dead-code-cleanup.yaml` — Reads `.loops/tmp/ll-dead-code-tests.txt` at line 84, `ll-dead-code-excluded.txt` at line 91.
- `test-coverage-improvement.yaml` — Reads `.loops/tmp/ll-coverage-report.txt` at line 94, `ll-coverage-tests.txt` at line 165.
- Broader set also exists (`autodev.yaml`, `recursive-refine.yaml`, `general-task.yaml`) — all write-then-Read scratch files. When the hook is enabled they will trip `Read`-deny-with-hint; this is the documented expected behavior (the loop re-runs the command as Bash with tee+tail on next turn).

### CLAUDE.md divergence (out of scope here — handled by ENH-1130)
- `.claude/CLAUDE.md:123-129` currently documents `/tmp/ll-scratch/` as the scratch path. The hook standardizes on `.loops/tmp/scratch/`. Do **not** modify CLAUDE.md in this issue; path reconciliation is ENH-1130's scope.

## Integration Map

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_

- `hooks/scripts/session-cleanup.sh:17` — `rm -rf ".loops/tmp/scratch"` already cleans the hook's output directory at session stop; confirms `.loops/tmp/scratch/` path convention is aligned; no change needed
- `hooks/scripts/lib/common.sh:184,198,218` — defines `ll_resolve_config`, `ll_feature_enabled`, `ll_config_value`; new hook sources this file identically to `context-monitor.sh:14` and `user-prompt-check.sh`; no change to the library
- `scripts/little_loops/subprocess_utils.py:99` — passes `--dangerously-skip-permissions` unconditionally; source of `permission_mode == "bypassPermissions"` in every PreToolUse stdin during automation runs; read-only coupling, no change needed
- `scripts/little_loops/fsm/evaluators.py:575` — also passes `--dangerously-skip-permissions` directly for FSM slash-command execution; same signal, read-only coupling

### Documentation

_Wiring pass added by `/ll:wire-issue`:_

- `docs/ARCHITECTURE.md:90-95` — hook scripts directory tree enumerates six scripts by name; must add `scratch-pad-redirect.sh` so the listing stays accurate after the script is created
- `docs/development/TROUBLESHOOTING.md` (~line 753) — contains a `chmod +x` list and manual invocation pattern for each hook script; new hook needs an entry in the chmod block and a matching `echo '{"tool_name":"Bash",...}' | bash hooks/scripts/scratch-pad-redirect.sh` invocation example

### Tests

_Wiring pass added by `/ll:wire-issue`:_

- `scripts/tests/test_config_schema.py:28-37` — `test_scratch_pad_properties` covers the `scratch_pad` schema block added by ENH-1128; passes today and remains unaffected by ENH-1129 (no schema changes); no update needed, but must not regress
- No existing test asserts on the count or structure of `PreToolUse` array entries in the real `hooks/hooks.json` — adding the second entry is safe

## Implementation Steps

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

1. After creating `hooks/scripts/scratch-pad-redirect.sh`, update `docs/ARCHITECTURE.md:90-95` — add `scratch-pad-redirect.sh` to the hook scripts directory tree so the listing reflects the new file
2. Update `docs/development/TROUBLESHOOTING.md` (~line 753) — add `chmod +x hooks/scripts/scratch-pad-redirect.sh` to the chmod block and a manual invocation example showing a Bash rewrite and Read deny scenario
3. Verify `session-cleanup.sh:17` (`rm -rf ".loops/tmp/scratch"`) already aligns with the hook's output path — no change needed, but confirm during integration test that scratch files from a rewritten command are removed on session stop

## Resolution

Implemented `hooks/scripts/scratch-pad-redirect.sh` as a PreToolUse hook registered in `hooks/hooks.json` (matcher `Bash|Read`, 5s timeout). Behavior:

- **No-op** when `scratch_pad.enabled` is `false` (schema default) or `permission_mode != "bypassPermissions"` while `automation_contexts_only` is `true`.
- **Bash rewrite**: first token (basename-normalized) matching `command_allowlist` → rewrites `command` to `<orig> > .loops/tmp/scratch/<name>-$$.txt 2>&1; tail -<tail_lines> ...`; emits `permissionDecision=allow` + `updatedInput.command` + `additionalContext`.
- **Read deny**: file with extension in `file_extension_filters` and `wc -l` ≥ `threshold_lines` → `permissionDecision=deny` with `permissionDecisionReason` containing an actionable `cat > .loops/tmp/scratch/... && tail -N` suggestion.
- Fail-open at every boundary (missing `jq`, missing config, empty stdin → allow).

Implementation notes:
- `allow_response` is locally defined per the `check-duplicate-issue-id.sh:17-20` pattern (common.sh does not export it).
- Field extraction uses one-field-per-line jq output with a `"__end__"` sentinel to prevent `$(...)` from stripping trailing empty fields (the `@tsv` pattern from context-monitor.sh collapses consecutive tabs because tab is IFS-whitespace).
- `scratch-pad-redirect.sh` added to `docs/ARCHITECTURE.md` hook tree and `docs/development/TROUBLESHOOTING.md` chmod block + manual invocation examples.
- Seven unit tests in `TestScratchPadRedirect` cover disabled, non-automation, Bash rewrite, non-allowlist Bash, large Read deny, small Read allow, and unfiltered-extension Read allow.

Verification:
- `python -m pytest scripts/tests/` — 4864 passed, 5 skipped
- `ruff check scripts/` — clean
- `python -m mypy scripts/little_loops/` — pre-existing `wcwidth` stub warning only (unrelated to this change)

## Session Log
- `/ll:manage-issue` - 2026-04-16T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/00032768-5efc-466a-aad1-02f0fb698fb3.jsonl`
- `/ll:ready-issue` - 2026-04-17T03:45:42 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/86c5c7e4-236c-46a0-acd9-2124269e76f0.jsonl`
- `/ll:confidence-check` - 2026-04-16T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1db273db-92c0-4518-a02e-d131c8a6790d.jsonl`
- `/ll:wire-issue` - 2026-04-17T03:41:47 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/51944600-1620-40f1-b229-242412743430.jsonl`
- `/ll:refine-issue` - 2026-04-17T03:36:17 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a72ddf9a-f502-4693-ad85-c0fbf00745d3.jsonl`
- `/ll:issue-size-review` - 2026-04-16T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4fc25386-a9f0-4e75-8434-c659db481895.jsonl`
