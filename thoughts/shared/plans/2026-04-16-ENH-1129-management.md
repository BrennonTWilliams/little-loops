# ENH-1129 Implementation Plan

## Issue
`scratch-pad-redirect.sh` PreToolUse hook — rewrites oversized `Bash` commands to tee+tail and denies oversized `Read` calls with an actionable Bash scratch-pad suggestion. Active only in automation contexts (`permission_mode == "bypassPermissions"`) when `scratch_pad.enabled: true`.

## Phase 0: Write Tests (Red)

New `TestScratchPadRedirect` class appended to `scripts/tests/test_hooks_integration.py`.

Fixtures:
- `hook_script` → `hooks/scripts/scratch-pad-redirect.sh`
- `enabled_config(tmp_path)` → writes `.ll/ll-config.json` with `scratch_pad.enabled: true` and defaults from schema.

Cases (one test each):
1. `test_disabled_noop` — config `enabled: false` → allow, no `updatedInput`
2. `test_non_automation_noop` — enabled, no `permission_mode` → allow unchanged
3. `test_bash_under_threshold_allow` — enabled + bypassPermissions + allowlist cmd, but not in allowlist match (non-allowlist bash like `git status`) → allow unchanged
4. `test_bash_rewritten` — enabled + bypassPermissions + `pytest scripts/tests/` → `updatedInput.command` contains `.loops/tmp/scratch/` and `tail -20`
5. `test_read_denied_over_threshold` — enabled + bypassPermissions + large `.txt` Read → deny, reason mentions `cat >` and scratch path
6. `test_read_small_file_allow` — enabled + bypassPermissions + small `.py` Read → allow (no deny)
7. `test_bash_non_allowlist_allow` — enabled + bypassPermissions + `git status` → allow unchanged

Each test `os.chdir(tmp_path)` in try/finally, writes `.ll/ll-config.json`, runs hook via `subprocess.run([str(hook_script)], input=json.dumps(...), capture_output=True, text=True, timeout=5)`, asserts JSON output shape.

## Phase 1: Implement scratch-pad-redirect.sh (Green)

Structure (based on `check-duplicate-issue-id.sh:1-129` and `context-monitor.sh:45-47`):

```bash
#!/bin/bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/lib/common.sh"

allow_response() {
    if [ $# -gt 0 ]; then echo "$1"; else
        echo '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"allow"}}'
    fi
    exit 0
}

command -v jq &>/dev/null || allow_response

INPUT=$(cat)
IFS=$'\t' read -r TOOL_NAME CMD FILE_PATH PERM_MODE <<< \
    "$(echo "$INPUT" | jq -r '[(.tool_name // ""),(.tool_input.command // ""),(.tool_input.file_path // ""),(.permission_mode // "")] | @tsv' 2>/dev/null)"

ll_resolve_config
ll_feature_enabled "scratch_pad.enabled" || allow_response

AUTO_ONLY=$(ll_config_value "scratch_pad.automation_contexts_only" "true")
if [ "$AUTO_ONLY" = "true" ] && [ "$PERM_MODE" != "bypassPermissions" ]; then
    allow_response
fi

THRESHOLD=$(ll_config_value "scratch_pad.threshold_lines" "200")
TAIL_LINES=$(ll_config_value "scratch_pad.tail_lines" "20")

case "$TOOL_NAME" in
    Bash)
        [ -n "$CMD" ] || allow_response
        FIRST_TOKEN=$(echo "$CMD" | awk '{print $1}')
        # Strip path prefix so `/usr/bin/pytest` still matches `pytest`
        FIRST_BASE=$(basename "$FIRST_TOKEN" 2>/dev/null || echo "$FIRST_TOKEN")
        ALLOWLIST=$(jq -r '.scratch_pad.command_allowlist // [] | .[]' "$LL_CONFIG_FILE" 2>/dev/null || echo "")
        MATCH=0
        while IFS= read -r cmd; do
            [ -z "$cmd" ] && continue
            if [ "$FIRST_BASE" = "$cmd" ] || [ "$FIRST_TOKEN" = "$cmd" ]; then
                MATCH=1; break
            fi
        done <<< "$ALLOWLIST"
        [ "$MATCH" = "1" ] || allow_response

        # Sanitize scratch name from first token (alphanumeric only)
        SCRATCH_NAME=$(echo "$FIRST_BASE" | tr -cd '[:alnum:]_-')
        SCRATCH_NAME="${SCRATCH_NAME:-cmd}-$(date +%s%N | tail -c 7)"
        SCRATCH_PATH=".loops/tmp/scratch/${SCRATCH_NAME}.txt"
        mkdir -p .loops/tmp/scratch 2>/dev/null || true
        NEW_CMD="${CMD} > ${SCRATCH_PATH} 2>&1; tail -${TAIL_LINES} ${SCRATCH_PATH}"
        jq -nc --arg new "$NEW_CMD" --arg ctx "Output redirected to ${SCRATCH_PATH} (last ${TAIL_LINES} lines shown)." \
            '{hookSpecificOutput:{hookEventName:"PreToolUse",permissionDecision:"allow",updatedInput:{command:$new},additionalContext:$ctx}}'
        exit 0
        ;;
    Read)
        [ -n "$FILE_PATH" ] || allow_response
        [ -f "$FILE_PATH" ] || allow_response

        EXT_MATCH=0
        EXTS=$(jq -r '.scratch_pad.file_extension_filters // [] | .[]' "$LL_CONFIG_FILE" 2>/dev/null || echo "")
        while IFS= read -r ext; do
            [ -z "$ext" ] && continue
            if [[ "$FILE_PATH" == *"$ext" ]]; then EXT_MATCH=1; break; fi
        done <<< "$EXTS"
        [ "$EXT_MATCH" = "1" ] || allow_response

        LINES=$(wc -l < "$FILE_PATH" 2>/dev/null || echo 0)
        if [ "${LINES:-0}" -lt "$THRESHOLD" ] 2>/dev/null; then
            allow_response
        fi

        SCRATCH_NAME=$(basename "$FILE_PATH" | tr -cd '[:alnum:]._-')
        SCRATCH_PATH=".loops/tmp/scratch/${SCRATCH_NAME}"
        REASON="[scratch-pad] ${FILE_PATH} has ${LINES} lines (threshold ${THRESHOLD}). Use Bash instead: cat \"${FILE_PATH}\" > ${SCRATCH_PATH} && tail -${TAIL_LINES} ${SCRATCH_PATH}"
        jq -nc --arg r "$REASON" \
            '{hookSpecificOutput:{hookEventName:"PreToolUse",permissionDecision:"deny",permissionDecisionReason:$r}}'
        exit 0
        ;;
    *)
        allow_response
        ;;
esac
```

Key notes:
- `allow_response` is locally defined per research (common.sh does not export it)
- Fail-open at every boundary (no jq → allow; no config → allow; empty path → allow)
- `PERM_MODE != "bypassPermissions"` is the automation gate
- `command_allowlist` and `file_extension_filters` are read inline via `jq` with `|.[]` to iterate

## Phase 2: Register in hooks.json

Append a second object to the `PreToolUse` array with `matcher: "Bash|Read"`, `timeout: 5`, command `bash ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/scratch-pad-redirect.sh`, statusMessage `Redirecting oversized output to scratch...`.

## Phase 3: Documentation updates

- `docs/ARCHITECTURE.md:90` — insert `scratch-pad-redirect.sh` between `precompact-state.sh` and `session-cleanup.sh` (alphabetical)
- `docs/development/TROUBLESHOOTING.md:754` — add `chmod +x hooks/scripts/scratch-pad-redirect.sh` to the chmod block

## Success Criteria (automated)

- [ ] `scripts/tests/test_hooks_integration.py::TestScratchPadRedirect` — 7/7 pass
- [ ] `python -m pytest scripts/tests/test_hooks_integration.py` — all pass
- [ ] `ruff check scripts/` — clean
- [ ] `python -m mypy scripts/little_loops/` — clean (tests dir excluded from mypy target)
- [ ] `bash hooks/scripts/scratch-pad-redirect.sh` with no input (empty stdin) → exits 0 with `allow`
