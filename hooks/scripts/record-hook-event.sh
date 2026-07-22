#!/usr/bin/env bash
#
# record-hook-event.sh
# Bash-only hook telemetry shim (ENH-2506): records one hook_events row for
# host events that never reach the Python dispatcher (Stop today — hooks.json
# binds it directly to raw bash scripts, never through main_hooks()).
#
# Usage: record-hook-event.sh <event_name> <script_path>
# Reads the host's hook JSON from stdin (for session_id) same as every other
# adapter. Never fails the calling hook: any error here is swallowed so
# telemetry can never be the reason a hook's exit code changes.
#
# Note: each hooks.json entry is an independent subprocess invocation with no
# visibility into a sibling entry's exit code, so this records "the shim ran"
# rather than the paired script's outcome (Decision-Point Option A trade-off,
# ENH-2506).

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/lib/common.sh"

EVENT_NAME="${1:-Unknown}"
SCRIPT_PATH="${2:-}"

ll_resolve_config

# No config at all → no analytics.enabled → nothing to record (matches the
# Python dispatcher's _hooks_telemetry_enabled(), which also requires a
# resolvable config). analytics.capture.hooks defaults to true when a config
# IS present but omits the key (forward-compat for configs written before
# ENH-2506) — only an explicit "false" disables it there.
if [ -z "$LL_CONFIG_FILE" ] || ! command -v jq &> /dev/null; then
    exit 0
fi
if [ "$(jq -r '.analytics.enabled == true' "$LL_CONFIG_FILE" 2>/dev/null)" != "true" ]; then
    exit 0
fi
if [ "$(jq -r '.analytics.capture.hooks == false' "$LL_CONFIG_FILE" 2>/dev/null)" = "true" ]; then
    exit 0
fi

START_MS=$(($(date +%s%N 2>/dev/null || echo 0) / 1000000))
INPUT=$(cat 2>/dev/null || echo "{}")
SESSION_ID=""
if command -v jq &> /dev/null; then
    SESSION_ID=$(echo "$INPUT" | jq -r '.session_id // empty' 2>/dev/null || echo "")
fi
END_MS=$(($(date +%s%N 2>/dev/null || echo 0) / 1000000))
DURATION_MS=$((END_MS - START_MS))

ARGS=(--event-name "$EVENT_NAME" --exit-code 0 --duration-ms "$DURATION_MS")
[ -n "$SESSION_ID" ] && ARGS+=(--session-id "$SESSION_ID")
[ -n "$SCRIPT_PATH" ] && ARGS+=(--script "$SCRIPT_PATH")

if command -v ll-session >/dev/null 2>&1; then
    ll-session record-hook-event "${ARGS[@]}" >/dev/null 2>&1 || true
fi

exit 0
